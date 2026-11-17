"""The tool snapshot (ADR 0012 §2, §4): an MCP server's tools as BotDesk pins them.

    entries = snapshot(await client.list_tools(server))   # what `mcp_servers.tools` stores
    tool_hash(info)                                       # SHA-256 of what the model would read

Pure functions, no I/O. Each entry keeps the server's own name (what a call sends), the local
name (what BotDesk and the model call it: `[a-z0-9_]`, unique within the server, short enough that
`mcp-<id>__<local>` fits 64 characters) and the hash of the definition the admin trusted.
Annotations are kept to show people, never to set risk.
"""

import hashlib
import json
import re
from typing import Any

from src.mcp.client import McpToolInfo

MAX_LOCAL_NAME = 48  # "mcp-" + 8 hex + "__" + 48 = 62, under the providers' 64
MAX_SCHEMA_BYTES = 64 * 1024


def tool_hash(tool: McpToolInfo) -> str:
    """SHA-256 of the canonical JSON of the tool's name, title, description and schemas."""
    definition = {
        "name": tool.name,
        "title": tool.title,
        "description": tool.description,
        "inputSchema": tool.input_schema,
        "outputSchema": tool.output_schema,
    }
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def local_name(server_name: str, taken: set[str]) -> str:
    """The server's tool name made safe: lower case, `[a-z0-9]` words joined by single
    underscores, starting with a letter, at most 48 characters, and not one of `taken` (a short
    hash of the server's name is added when it would be)."""
    words = [word for word in re.split(r"[^a-z0-9]+", server_name.lower()) if word]
    name = "_".join(words) or "tool"
    if not name[0].isalpha():
        name = f"tool_{name}"
    if len(name) <= MAX_LOCAL_NAME and name not in taken:
        return name
    base = name[: MAX_LOCAL_NAME - 7].rstrip("_")
    digest = hashlib.sha256(server_name.encode()).hexdigest()
    for start in range(0, len(digest) - 5):  # a different slice of the hash in the rare case it's taken too
        candidate = f"{base}_{digest[start : start + 6]}"
        if candidate not in taken:
            return candidate
    raise ValueError(f"No free local name for {server_name!r}")


def snapshot(tools: list[McpToolInfo]) -> list[dict[str, Any]]:
    """The entries to store, in the server's order. A tool whose schemas are over 64 KB is left out."""
    entries: list[dict[str, Any]] = []
    taken: set[str] = set()
    for tool in tools:
        schemas = json.dumps([tool.input_schema, tool.output_schema], ensure_ascii=False)
        if len(schemas.encode()) > MAX_SCHEMA_BYTES:
            continue
        name = local_name(tool.name, taken)
        taken.add(name)
        entries.append(
            {
                "name": tool.name,
                "localName": name,
                "title": tool.title,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "outputSchema": tool.output_schema,
                "annotations": tool.annotations,
                "hash": tool_hash(tool),
            }
        )
    return entries


def snapshot_hash(entries: list[dict[str, Any]]) -> str:
    """One hash for the whole list, to tell at a glance whether anything changed."""
    joined = "\n".join(sorted(f"{entry['name']}:{entry['hash']}" for entry in entries))
    return hashlib.sha256(joined.encode()).hexdigest()
