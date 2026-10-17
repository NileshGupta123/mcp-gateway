"""NetworkPolicy ka end-to-end check: jo raaste allowed hain wo chalte hain, baaki sab band hain.

Usage (repo root se):
  .\\.venv\\Scripts\\python.exe .\\scripts\\netpol_test.py

Is cluster ka policy controller rok di gayi connection ko "refuse" karta hai (timeout nahi), isliye
"blocked" ka matlab hai timeout YA connection refused. Refused kisi band port se bhi aa sakta hai, isliye
har blocked check ke saath ek control hai: wahi target kisi allowed jagah se "open" hona chahiye.
"""

import subprocess
import sys
import time
import uuid

import httpx

NS = "urumi"
failures: list[str] = []
results: dict[str, str] = {}


def check(label: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + label + ("" if condition or not detail else f"  -> {detail}"))
    if not condition:
        failures.append(label)


PY_PROBE = """import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    socket.create_connection((host, port), timeout=4).close()
    print("open")
except (TimeoutError, socket.timeout):
    print("blocked:timeout")
except ConnectionRefusedError:
    print("blocked:refused")
except Exception as exc:
    print("error:" + type(exc).__name__)
"""

# WordPress image mein python nahi hai, php hai; ye control sirf wordpress -> mariadb ke liye hai
PHP_PROBE = "<?php $s = @fsockopen('urumi-mariadb', 3306, $errno, $errstr, 4); echo $s ? 'open' : 'blocked:' . $errno;"


def run_exec(deploy: str, command: list[str], stdin: str) -> str:
    """Deployment ke pod ke andar command chalata hai. kubectl exec kabhi kabhi transport error deta hai, isliye retry."""
    last = ""
    for _ in range(3):
        r = subprocess.run(
            ["kubectl", "-n", NS, "exec", "-i", f"deploy/{deploy}", "--", *command],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = r.stdout.strip()
        if out:
            return out
        last = "error:" + r.stderr.strip()[:200]
        time.sleep(3)
    return last


def probe(deploy: str, host: str, port: int) -> str:
    return run_exec(deploy, ["python", "-", host, str(port)], PY_PROBE)


def probe_new_pod(namespace: str, url: str) -> str:
    """Naya (bina kisi allow rule wala) pod bana ke url pe curl chalata hai. curl ka exit code se wajah pata chalti hai."""
    name = "netpol-probe-" + uuid.uuid4().hex[:6]
    r = subprocess.run(
        [
            "kubectl", "-n", namespace, "run", name, "--rm", "-i", "--quiet", "--restart=Never",
            "--image=curlimages/curl", "--", "curl", "-s", "-m", "4", "-o", "/dev/null",
            "-w", "%{http_code}:%{exitcode}", url,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = r.stdout.strip()
    code = out.rsplit(":", 1)[-1] if ":" in out else ""
    if code in ("7", "28"):  # 7 = connection refused, 28 = timeout
        return "blocked"
    if code == "0":
        return "open"
    return "error:" + (out or r.stderr.strip()[:150])


print("== Allowed paths (should be open) ==")
allowed = [
    ("gateway -> woo-mcp", "urumi-gateway", "urumi-woo-mcp", 8000),
    ("gateway -> notes-mcp", "urumi-gateway", "urumi-notes-mcp", 8000),
    ("gateway -> time-mcp", "urumi-gateway", "urumi-time-mcp", 8000),
    ("gateway -> postgres", "urumi-gateway", "urumi-postgres", 5432),
    ("gateway -> LLM provider (api.groq.com:443)", "urumi-gateway", "api.groq.com", 443),
    ("woo-mcp -> wordpress", "urumi-woo-mcp", "urumi-wordpress", 80),
]
for label, deploy, host, port in allowed:
    results[label] = probe(deploy, host, port)
    check(label, results[label] == "open", results[label])

results["wordpress -> mariadb"] = run_exec("urumi-wordpress", ["php"], PHP_PROBE)
check("wordpress -> mariadb", results["wordpress -> mariadb"] == "open", results["wordpress -> mariadb"])

print("\n== Blocked paths (should be refused or time out) ==")
# (label, source deployment, host, port, control: ek allowed check ka naam jisme wahi target open hona chahiye)
blocked = [
    ("woo-mcp cannot reach postgres", "urumi-woo-mcp", "urumi-postgres", 5432, "gateway -> postgres"),
    ("woo-mcp cannot reach the store database", "urumi-woo-mcp", "urumi-mariadb", 3306, "wordpress -> mariadb"),
    ("notes-mcp cannot reach woo-mcp", "urumi-notes-mcp", "urumi-woo-mcp", 8000, "gateway -> woo-mcp"),
    ("time-mcp has no internet egress (1.1.1.1:443)", "urumi-time-mcp", "1.1.1.1", 443,
     "gateway -> LLM provider (api.groq.com:443)"),
    ("gateway cannot reach cloud metadata (169.254.169.254)", "urumi-gateway", "169.254.169.254", 80, None),
    ("gateway cannot reach the store database", "urumi-gateway", "urumi-mariadb", 3306, "wordpress -> mariadb"),
    ("gateway cannot reach WordPress directly", "urumi-gateway", "urumi-wordpress", 80, "woo-mcp -> wordpress"),
]
for label, deploy, host, port, control in blocked:
    out = probe(deploy, host, port)
    control_ok = control is None or results.get(control) == "open"
    detail = out if control_ok else f"{out} (control '{control}' was not open, so this proves nothing)"
    check(label, out.startswith("blocked") and control_ok, detail)

print("\n== Unknown pods cannot reach the internals ==")
pod_checks = [
    ("new pod in the same namespace -> woo-mcp", NS, f"http://urumi-woo-mcp.{NS}.svc:8000/healthz"),
    ("new pod in the same namespace -> wordpress", NS, f"http://urumi-wordpress.{NS}.svc/"),
    ("pod from another namespace -> woo-mcp", "default", f"http://urumi-woo-mcp.{NS}.svc:8000/healthz"),
    ("pod from another namespace -> gateway", "default", f"http://urumi-gateway.{NS}.svc:8000/healthz"),
]
for label, namespace, url in pod_checks:
    out = probe_new_pod(namespace, url)
    check(label, out == "blocked", out)

print("\n== Public paths still work through the ingress ==")
for label, url in [
    ("dashboard", "http://app.localtest.me/"),
    ("gateway API", "http://app.localtest.me/api/openapi.json"),
    ("storefront", "http://store.localtest.me/shop/"),
]:
    try:
        status = httpx.get(url, timeout=30, follow_redirects=True).status_code
    except httpx.HTTPError as exc:
        status = type(exc).__name__
    check(f"{label} is reachable ({url})", status == 200, str(status))

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    sys.exit(1)
print("Saare checks pass.")