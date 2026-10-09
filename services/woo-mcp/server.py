"""WooCommerce MCP server (Streamable HTTP).

Ye server WooCommerce REST API (/wp-json/wc/v3) ke upar ek patla MCP layer hai.
Sirf cluster ke andar reachable hota hai; gateway hi isse call karta hai.

Env vars:
  WOO_BASE_URL         store ka in-cluster URL, e.g. http://urumi-wordpress
  WOO_CONSUMER_KEY     WooCommerce REST API key (Kubernetes Secret se)
  WOO_CONSUMER_SECRET  WooCommerce REST API secret (Kubernetes Secret se)
  WOO_HOST_HEADER      (optional) public store host, e.g. store.localtest.me
  STORE_TZ             (optional) "aaj" ki definition ke liye timezone, default Asia/Kolkata
  PORT                 (optional) default 8000
"""

import os
from datetime import datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


WOO_BASE_URL = _require_env("WOO_BASE_URL").rstrip("/")
WOO_CONSUMER_KEY = _require_env("WOO_CONSUMER_KEY")
WOO_CONSUMER_SECRET = _require_env("WOO_CONSUMER_SECRET")
WOO_HOST_HEADER = os.environ.get("WOO_HOST_HEADER", "").strip()
STORE_TZ = ZoneInfo(os.environ.get("STORE_TZ", "Asia/Kolkata"))
PORT = int(os.environ.get("PORT", "8000"))

OrderStatus = Literal[
    "pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed"
]
OrderStatusFilter = Literal[
    "any", "pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed"
]
ProductStatusFilter = Literal["any", "publish", "draft", "pending", "private"]

# WooCommerce Basic Auth sirf HTTPS pe chalti hai. Cluster ke andar HTTP hai, isliye
# X-Forwarded-Proto: https bhejte hain; WordPress ke wp-config mein ye header dekhke
# HTTPS=on set hota hai (chart ke WORDPRESS_CONFIG_EXTRA mein).
_headers = {"Accept": "application/json", "X-Forwarded-Proto": "https"}
if WOO_HOST_HEADER:
    _headers["Host"] = WOO_HOST_HEADER

_client = httpx.AsyncClient(
    base_url=f"{WOO_BASE_URL}/wp-json/wc/v3",
    auth=(WOO_CONSUMER_KEY, WOO_CONSUMER_SECRET),
    headers=_headers,
    timeout=httpx.Timeout(15.0, connect=5.0),
)

mcp = FastMCP(
    "woocommerce",
    instructions="Tools to manage one WooCommerce store: products and orders.",
    host="0.0.0.0",
    port=PORT,
    # Stateless + JSON responses: har request independent hai, to gateway ke
    # multiple replicas ke peeche bhi session-affinity ki zaroorat nahi.
    stateless_http=True,
    json_response=True,
)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


async def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None):
    """WooCommerce ko call karta hai. Errors mein credentials kabhi nahi aate."""
    try:
        resp = await _client.request(method, path, params=params, json=json)
    except httpx.TimeoutException:
        raise RuntimeError("WooCommerce store did not respond in time")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach the WooCommerce store ({type(exc).__name__})")
    if resp.status_code >= 400:
        try:
            message = resp.json().get("message", resp.text[:200])
        except ValueError:
            message = resp.text[:200]
        raise RuntimeError(f"WooCommerce API error {resp.status_code}: {message}")
    return resp.json()


def _clamp(limit: int) -> int:
    return max(1, min(limit, 100))


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _product(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "status": p["status"],
        "type": p["type"],
        "price": p.get("price"),
        "regular_price": p.get("regular_price"),
        "sale_price": p.get("sale_price"),
        "stock_status": p.get("stock_status"),
        "stock_quantity": p.get("stock_quantity"),
        "url": p.get("permalink"),
    }


def _order(o: dict) -> dict:
    # Data minimisation: customer ka sirf naam, email/phone/address nahi
    billing = o.get("billing", {})
    customer = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
    return {
        "id": o["id"],
        "status": o["status"],
        "total": o["total"],
        "currency": o["currency"],
        "created_gmt": o.get("date_created_gmt"),
        "customer": customer or None,
        "payment_method": o.get("payment_method_title"),
        "items": [
            {"name": i["name"], "quantity": i["quantity"], "total": i["total"]}
            for i in o.get("line_items", [])
        ],
    }


@mcp.tool()
async def list_products(
    search: str | None = None,
    status: ProductStatusFilter = "any",
    limit: int = 20,
) -> list[dict]:
    """List products in the store. Optionally filter by a search term or status."""
    params: dict = {"per_page": _clamp(limit), "status": status}
    if search:
        params["search"] = search
    data = await _request("GET", "/products", params=params)
    return [_product(p) for p in data]


@mcp.tool()
async def create_product(
    name: str,
    price: float,
    description: str = "",
    status: Literal["publish", "draft"] = "publish",
    stock_quantity: int | None = None,
) -> dict:
    """Create a simple product with a name and regular price (in the store currency)."""
    if not name.strip():
        raise ValueError("name must not be empty")
    if price < 0:
        raise ValueError("price must not be negative")
    payload: dict = {
        "name": name.strip(),
        "type": "simple",
        "regular_price": f"{price:.2f}",
        "description": description,
        "status": status,
    }
    if stock_quantity is not None:
        payload["manage_stock"] = True
        payload["stock_quantity"] = stock_quantity
    return _product(await _request("POST", "/products", json=payload))


@mcp.tool()
async def update_product(
    product_id: int,
    name: str | None = None,
    price: float | None = None,
    sale_price: float | None = None,
    stock_quantity: int | None = None,
    status: Literal["publish", "draft", "private"] | None = None,
) -> dict:
    """Update a product's name, regular price, sale price (0 clears it), stock or status."""
    payload: dict = {}
    if name is not None:
        payload["name"] = name.strip()
    if price is not None:
        if price < 0:
            raise ValueError("price must not be negative")
        payload["regular_price"] = f"{price:.2f}"
    if sale_price is not None:
        payload["sale_price"] = "" if sale_price == 0 else f"{sale_price:.2f}"
    if stock_quantity is not None:
        payload["manage_stock"] = True
        payload["stock_quantity"] = stock_quantity
    if status is not None:
        payload["status"] = status
    if not payload:
        raise ValueError("Nothing to update: pass at least one field")
    return _product(await _request("PUT", f"/products/{product_id}", json=payload))


@mcp.tool()
async def list_orders(
    status: OrderStatusFilter = "any",
    today_only: bool = False,
    created_after: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List orders, newest first. Use today_only=true for orders placed today (store timezone),
    or created_after (ISO 8601, e.g. 2026-10-09T00:00:00) for a custom start time."""
    params: dict = {
        "per_page": _clamp(limit),
        "orderby": "date",
        "order": "desc",
        "status": status,
    }
    if today_only:
        start = datetime.combine(datetime.now(STORE_TZ).date(), time.min, tzinfo=STORE_TZ)
        params["after"] = _utc_iso(start)
        params["dates_are_gmt"] = "true"
    elif created_after:
        try:
            parsed = datetime.fromisoformat(created_after)
        except ValueError:
            raise ValueError("created_after must be ISO 8601, e.g. 2026-10-09T00:00:00")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=STORE_TZ)
        params["after"] = _utc_iso(parsed)
        params["dates_are_gmt"] = "true"
    data = await _request("GET", "/orders", params=params)
    return [_order(o) for o in data]


@mcp.tool()
async def get_order(order_id: int) -> dict:
    """Get one order by its numeric ID."""
    return _order(await _request("GET", f"/orders/{order_id}"))


@mcp.tool()
async def update_order_status(order_id: int, status: OrderStatus) -> dict:
    """Change an order's status (e.g. processing -> completed)."""
    return _order(await _request("PUT", f"/orders/{order_id}", json={"status": status}))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")