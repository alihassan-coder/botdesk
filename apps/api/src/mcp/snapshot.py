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


# Review (slice 7.4): what an admin approved, and what changed since.

# The risks an admin may give an MCP tool on the review screen (never below `read`).
REVIEW_RISKS = ("read", "write-internal", "write-external", "external-send", "destructive")
DEFAULT_RISK = "external-send"
_DEFINITION = ("title", "description", "inputSchema", "outputSchema")
# A tool no admin has approved yet: off, at the default risk, until the review.
_WAITING: dict[str, Any] = {"state": "pending", "enabled": False, "risk": DEFAULT_RISK, "approvedHash": None}


def normalized(entry: dict[str, Any]) -> dict[str, Any]:
    """An entry with its review fields. Entries saved before reviews existed (slice 7.2) were
    trusted as they were: approved, offered, `external-send`."""
    return {
        **entry,
        "state": entry.get("state", "approved"),
        "enabled": entry.get("enabled", True),
        "risk": entry.get("risk", DEFAULT_RISK),
        "approvedHash": entry.get("approvedHash", entry["hash"] if "state" not in entry else None),
    }


def offered(entry: dict[str, Any]) -> bool:
    """Bots are offered a tool only when an admin approved it as it is now, and left it on."""
    entry = normalized(entry)
    return bool(entry["state"] == "approved" and entry["enabled"] and entry["approvedHash"] == entry["hash"])


def review_diff(old: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The snapshot to store after listing the tools again (`fresh`, from `snapshot`), given the
    one stored (`old`). The first snapshot is all `pending`: nothing is offered to a bot before an
    admin's review (ADR 0012 §4). After that:

    - unchanged: kept as the admin left it (on or off, its risk);
    - **changed** (hash differs from the approved one): not offered; `previous` keeps what was approved;
    - **new** (or never approved yet): `pending`, off, until an admin approves it;
    - **removed**: kept as `removed` to show in the diff (a tool never approved is just dropped).
      If it comes back as it was approved, it is approved again; changed, it waits like any change.

    A tool's local name never changes across refreshes (bindings and approvals name it)."""
    if not old:
        return [{**entry, **_WAITING} for entry in fresh]
    before = {entry["name"]: normalized(entry) for entry in old}
    taken = {entry["localName"] for entry in before.values()}
    result: list[dict[str, Any]] = []
    for entry in fresh:
        known = before.pop(entry["name"], None)
        if known is None:
            name = local_name(entry["name"], taken)
            taken.add(name)
            result.append({**entry, "localName": name, **_WAITING})
            continue
        merged = {**entry, "localName": known["localName"], "enabled": known["enabled"], "risk": known["risk"]}
        merged["approvedHash"] = known["approvedHash"]
        if known["approvedHash"] is None:
            merged["state"] = "pending"
        elif entry["hash"] == known["approvedHash"]:
            merged["state"] = "approved"
        else:
            merged["state"] = "changed"
            merged["previous"] = known.get("previous") or {key: known.get(key) for key in _DEFINITION}
        result.append(merged)
    for gone in before.values():  # no longer listed by the server
        if gone["approvedHash"] is not None:  # `previous` stays: what was approved, should it come back
            result.append({**gone, "state": "removed"})
    return result


def approve(entry: dict[str, Any], *, enabled: bool, risk: str) -> dict[str, Any]:
    """The entry as an admin approved it now: offered (if `enabled`) at `risk`."""
    approved = {k: v for k, v in normalized(entry).items() if k != "previous"}
    return {**approved, "state": "approved", "enabled": enabled, "risk": risk, "approvedHash": entry["hash"]}
