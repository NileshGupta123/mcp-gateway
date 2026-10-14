"""Notes MCP server (Streamable HTTP).

Chhota stateful upstream server: notes memory mein rehte hain.
Design choice: state ephemeral hai (pod restart pe chali jaati hai) aur replicas=1 rakhna
zaroori hai, kyunki memory replicas ke beech share nahi hoti. Demo ke liye kaafi hai.
"""

import itertools
import os
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

PORT = int(os.environ.get("PORT", "8000"))
MAX_NOTES = 500
MAX_TEXT_LENGTH = 2000

mcp = FastMCP(
    "notes",
    instructions="A small notebook: add, list, search and delete short text notes.",
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
    json_response=True,
)

_notes: dict[int, dict] = {}
_ids = itertools.count(1)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@mcp.tool()
async def server_info() -> dict:
    """Describe this server (name, version, purpose)."""
    return {
        "server": "notes",
        "version": "0.1.0",
        "description": "Short text notes kept in memory",
        "notes_stored": len(_notes),
    }


@mcp.tool()
async def add_note(text: str, tags: list[str] | None = None) -> dict:
    """Save a short note. Optionally attach tags."""
    text = text.strip()
    if not text:
        raise ValueError("text must not be empty")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"text is too long (max {MAX_TEXT_LENGTH} characters)")
    if len(_notes) >= MAX_NOTES:
        raise ValueError(f"note limit reached ({MAX_NOTES}); delete some notes first")
    note_id = next(_ids)
    note = {
        "id": note_id,
        "text": text,
        "tags": [t.strip() for t in (tags or []) if t.strip()],
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _notes[note_id] = note
    return note


@mcp.tool()
async def list_notes(limit: int = 20) -> list[dict]:
    """List the most recent notes, newest first."""
    limit = max(1, min(limit, 100))
    return sorted(_notes.values(), key=lambda n: n["id"], reverse=True)[:limit]


@mcp.tool()
async def search_notes(query: str) -> list[dict]:
    """Find notes whose text or tags contain the query (case-insensitive)."""
    q = query.strip().lower()
    if not q:
        raise ValueError("query must not be empty")
    hits = [
        n
        for n in _notes.values()
        if q in n["text"].lower() or any(q in t.lower() for t in n["tags"])
    ]
    return sorted(hits, key=lambda n: n["id"], reverse=True)[:50]


@mcp.tool()
async def delete_note(note_id: int) -> dict:
    """Delete a note by its ID."""
    if note_id not in _notes:
        raise ValueError(f"No note with id {note_id}")
    del _notes[note_id]
    return {"deleted": note_id}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")