"""Upgrade and rollback demo for the Helm release.

Demo A: a broken upgrade (a Woo MCP image tag that does not exist) with --atomic. Helm waits, gives up
        and rolls back by itself. While it happens, two watchers poll the storefront (every second) and the
        gateway's view of the Woo MCP server (every 3 seconds) to show that nothing went down.
Demo B: a working upgrade (CHAT_MAX_STEPS 6 -> 3), then a manual `helm rollback`.

The release ends in the state it started in.

Usage (from the repository root):
  $env:ADMIN_PASSWORD = "<admin password>"
  .\\.venv\\Scripts\\python.exe .\\scripts\\upgrade_demo.py
"""

import json
import os
import subprocess
import sys
import threading
import time

import httpx

BASE = "http://app.localtest.me"
STORE = "http://store.localtest.me"
RELEASE = "urumi"
NS = "urumi"
VALUES = ["-f", "charts/urumi/values.yaml", "-f", "charts/urumi/values-local.yaml"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    sys.exit("Set the admin password first: $env:ADMIN_PASSWORD = '...'")

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + label + ("" if condition or not detail else f"  -> {detail}"))
    if not condition:
        failures.append(label)


def run(command: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def helm_release() -> dict:
    out = run(["helm", "list", "-n", NS, "-o", "json", "--filter", f"^{RELEASE}$"]).stdout
    return json.loads(out)[0]


def revision() -> int:
    return int(helm_release()["revision"])


def jsonpath(deployment: str, expression: str) -> str:
    result = run(["kubectl", "-n", NS, "get", f"deploy/{deployment}", "-o", f"jsonpath={expression}"])
    return result.stdout.strip()


def woo_image() -> str:
    return jsonpath("urumi-woo-mcp", "{.spec.template.spec.containers[0].image}")


def chat_max_steps() -> str:
    return jsonpath("urumi-gateway", "{.spec.template.spec.containers[0].env[?(@.name=='CHAT_MAX_STEPS')].value}")


def show_history(rows: int = 6) -> None:
    print(run(["helm", "history", RELEASE, "-n", NS, "--max", str(rows)]).stdout)


def upgrade(extra: list[str], timeout: str) -> subprocess.CompletedProcess:
    command = ["helm", "upgrade", RELEASE, "charts/urumi", "-n", NS, *VALUES, *extra, "--wait", "--timeout", timeout, "--no-hooks"]
    return run(command, timeout=900)


class Watcher(threading.Thread):
    """Runs a check in a loop. Records every problem, the number of samples and the slowest sample."""

    def __init__(self, name: str, check_fn, interval: float) -> None:
        super().__init__(daemon=True)
        self.label = name
        self.check_fn = check_fn
        self.interval = interval
        self.stop_flag = threading.Event()
        self.samples = 0
        self.max_seconds = 0.0
        self.problems: list[str] = []

    def run(self) -> None:
        while not self.stop_flag.is_set():
            started = time.monotonic()
            try:
                problem = self.check_fn()
            except Exception as exc:  # noqa: BLE001
                problem = f"{type(exc).__name__}: {exc}"
            self.max_seconds = max(self.max_seconds, time.monotonic() - started)
            self.samples += 1
            if problem:
                self.problems.append(problem)
            self.stop_flag.wait(self.interval)

    def summary(self) -> str:
        return f"{self.label}: {self.samples} samples, slowest {self.max_seconds:.1f}s, {len(self.problems)} problems"


def storefront_check() -> str | None:
    code = httpx.get(f"{STORE}/shop/", timeout=20).status_code
    return None if code == 200 else f"storefront returned HTTP {code}"


def make_gateway_check(client: httpx.Client):
    def gateway_check() -> str | None:
        servers = client.get("/api/servers", params={"refresh": "true"}).json()
        woo = next(s for s in servers if s["name"] == "woocommerce")
        return None if woo["status"] == "connected" else f"woocommerce was {woo['status']}: {woo['error']}"

    return gateway_check


def wait_rollout(deployment: str) -> None:
    run(["kubectl", "-n", NS, "rollout", "status", f"deploy/{deployment}", "--timeout=180s"])


def main() -> None:
    print("Starting point:")
    show_history(3)
    start_rev = revision()
    start_image = woo_image()
    start_steps = chat_max_steps()
    check("the release is deployed", helm_release()["status"] == "deployed", helm_release()["status"])

    client = httpx.Client(base_url=BASE, timeout=30)
    login = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if login.status_code != 200:
        sys.exit(f"Admin login failed: {login.status_code} {login.text}")

    print("\n=== Demo A: a broken upgrade is rolled back by Helm (--atomic) ===")
    print("Upgrading the Woo MCP server to an image tag that does not exist. This takes about 2 minutes.")
    watchers = [
        Watcher("storefront", storefront_check, 1.0),
        Watcher("gateway -> woo-mcp", make_gateway_check(client), 3.0),
    ]
    for watcher in watchers:
        watcher.start()
    result = upgrade(["--set", "wooMcp.image=urumi/woo-mcp:does-not-exist", "--atomic"], "90s")
    for watcher in watchers:
        watcher.stop_flag.set()
    for watcher in watchers:
        watcher.join(timeout=30)
    print((result.stdout + result.stderr).strip()[-600:])
    wait_rollout("urumi-woo-mcp")

    check("Helm refused the broken upgrade (non-zero exit)", result.returncode != 0)
    check("the release is back in the deployed state", helm_release()["status"] == "deployed", helm_release()["status"])
    check("the Woo MCP server runs its old image again", woo_image() == start_image, f"{woo_image()} vs {start_image}")
    for watcher in watchers:
        print("      " + watcher.summary())
    check(
        "no storefront or gateway request failed during the whole upgrade",
        all(not w.problems for w in watchers),
        "; ".join(p for w in watchers for p in w.problems[:2]),
    )
    check(
        "the watchers sampled throughout (enough samples to mean something)",
        watchers[0].samples >= 20 and watchers[1].samples >= 5,
        "; ".join(w.summary() for w in watchers),
    )
    print(f"\nRevisions after Demo A (started at {start_rev}):")
    show_history(4)

    print("=== Demo B: a working upgrade, then a manual rollback ===")
    before_b = revision()
    result = upgrade(["--set", "chat.maxSteps=3"], "5m")
    check("the upgrade to CHAT_MAX_STEPS=3 succeeded", result.returncode == 0, (result.stdout + result.stderr)[-300:])
    check("the gateway now runs with CHAT_MAX_STEPS=3", chat_max_steps() == "3", chat_max_steps())
    check("the upgrade created a new revision", revision() == before_b + 1, f"{revision()} vs {before_b + 1}")

    rollback = run(["helm", "rollback", RELEASE, str(before_b), "-n", NS, "--wait", "--timeout", "5m"])
    print(rollback.stdout.strip())
    check("helm rollback succeeded", rollback.returncode == 0, rollback.stderr[-300:])
    wait_rollout("urumi-gateway")
    check(f"the gateway is back to CHAT_MAX_STEPS={start_steps}", chat_max_steps() == start_steps, chat_max_steps())
    check("the rollback itself is a new revision", revision() == before_b + 2, f"{revision()} vs {before_b + 2}")
    check("the gateway answers after the rollback", httpx.get(f"{BASE}/api/openapi.json", timeout=30).status_code == 200)

    print("\nFinal history:")
    show_history(6)
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    print("All checks pass. The release is back in the state it started in.")


main()