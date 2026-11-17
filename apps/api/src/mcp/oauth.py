"""OAuth 2.1 for MCP servers, the protocol half (ADR 0012 §3, slice 7.3). No database here.

    challenge = parse_challenge(www_authenticate)                 # from the server's 401
    found = await discover(http, server_url, challenge, guard)    # PRM (RFC 9728) → AS metadata (RFC 8414)
    client = await register(http, found, redirect_uri, guard)     # dynamic registration, when no client id
    url = authorize_url(found, client_id, redirect_uri, state=…, challenge=…)
    response = await token_request(http, found, client, form, guard)   # code or refresh_token grant

- **Discovery**: the 401's `resource_metadata` (else the well-known Protected Resource Metadata
  addresses, path first) names the authorization server; its metadata is read from the RFC 8414 /
  OpenID addresses in the MCP spec's order. Its `issuer` must be the address it was read for, and
  it must offer PKCE S256. The metadata's `resource` must be the server's own origin and a prefix
  of its path: that's the `resource` (RFC 8707) sent with every authorization and token request.
  A server with no PRM (the 2025-03-26 spec) gets its origin as the authorization server.
- **Every address is guarded** (`guard`): https only (unless the network allows http: tests), no
  user info, and every address the host resolves to must be public unless ALLOW_PRIVATE_MCP_URLS.
  The HTTP client underneath is the SSRF guard's transport (the IP checked is the IP connected
  to) and never follows redirects.
- **Errors** are `McpSignInError` with a sentence people can act on; never the server's own words.
"""

import base64
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx

from src.core.errors import BadRequest

MAX_METADATA_BYTES = 256 * 1024
Guard = Callable[[str], Awaitable[str]]  # an address → the same address, or McpSignInError


class McpSignInError(BadRequest):
    """Signing in to an MCP server can't go ahead. The message is safe to show people."""


@dataclass(frozen=True)
class Challenge:
    """What a 401's `WWW-Authenticate: Bearer …` told us (RFC 9728 §5.1, RFC 6750 §3)."""

    resource_metadata: str | None = None
    scope: str | None = None
    error: str | None = None


_PARAM = re.compile(r'([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^\s,]+))')


def parse_challenge(header: str | None) -> Challenge:
    """The Bearer challenge's parameters; an empty `Challenge` for anything else."""
    if not header or not header.strip().lower().startswith("bearer"):
        return Challenge()
    params = {match[1].lower(): (match[2] if match[2] is not None else match[3]) for match in _PARAM.finditer(header)}
    return Challenge(
        resource_metadata=params.get("resource_metadata") or None,
        scope=params.get("scope") or None,
        error=params.get("error") or None,
    )


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _path(url: str) -> str:
    return urlsplit(url).path.rstrip("/")


async def _get_json(http: httpx.AsyncClient, url: str, guard: Guard) -> dict[str, Any] | None:
    """A metadata document, or None when there isn't one at `url` (any non-200, or not JSON)."""
    response = await http.get(await guard(url), headers={"Accept": "application/json"})
    if response.status_code != 200 or len(response.content) > MAX_METADATA_BYTES:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


async def discover(http: httpx.AsyncClient, server_url: str, challenge: Challenge, guard: Guard) -> dict[str, Any]:
    """What signing in to `server_url` needs, as stored in `mcp_servers.oauth` (no secrets):
    `issuer`, `authorizationEndpoint`, `tokenEndpoint`, `registrationEndpoint`, `resource`,
    `scopes`, `issParameter` (RFC 9207 `iss` required) and the token endpoint's auth methods."""
    server_url = server_url.strip()
    origin, path = _origin(server_url), _path(server_url)
    candidates = [challenge.resource_metadata] if challenge.resource_metadata else []
    if path:
        candidates.append(f"{origin}/.well-known/oauth-protected-resource{path}")
    candidates.append(f"{origin}/.well-known/oauth-protected-resource")
    prm: dict[str, Any] | None = None
    for candidate in candidates:
        if prm := await _get_json(http, candidate, guard):
            break

    if prm is not None:
        servers = prm.get("authorization_servers")
        issuer = _str(servers[0]) if isinstance(servers, list) and servers else None
        if issuer is None:
            raise McpSignInError("This MCP server's sign-in details name no authorization server.")
        resource = _str(prm.get("resource")) or server_url
        if _origin(resource) != origin or not (path + "/").startswith(_path(resource) + "/"):
            raise McpSignInError("This MCP server's sign-in details are for another address.")
        supported = prm.get("scopes_supported")
        scopes = [s for s in supported if isinstance(s, str)] if isinstance(supported, list) else []
    else:  # the 2025-03-26 spec: the server's origin is its own authorization server
        issuer, resource, scopes = origin, server_url, []
    if challenge.scope:
        scopes = challenge.scope.split()

    metadata = await _authorization_server(http, issuer.rstrip("/"), guard)
    methods = metadata.get("token_endpoint_auth_methods_supported")
    return {
        "issuer": issuer.rstrip("/"),
        "authorizationEndpoint": await guard(str(metadata["authorization_endpoint"])),
        "tokenEndpoint": await guard(str(metadata["token_endpoint"])),
        "registrationEndpoint": _str(metadata.get("registration_endpoint")),
        "resource": resource,
        "scopes": scopes,
        "issParameter": metadata.get("authorization_response_iss_parameter_supported") is True,
        "tokenAuthMethods": [m for m in methods if isinstance(m, str)] if isinstance(methods, list) else [],
    }


async def _authorization_server(http: httpx.AsyncClient, issuer: str, guard: Guard) -> dict[str, Any]:
    origin, path = _origin(issuer), _path(issuer)
    if path:
        candidates = [
            f"{origin}/.well-known/oauth-authorization-server{path}",
            f"{origin}/.well-known/openid-configuration{path}",
            f"{origin}{path}/.well-known/openid-configuration",
        ]
    else:
        candidates = [f"{origin}/.well-known/oauth-authorization-server", f"{origin}/.well-known/openid-configuration"]
    for candidate in candidates:
        metadata = await _get_json(http, candidate, guard)
        if metadata is None:
            continue
        if str(metadata.get("issuer", "")).rstrip("/") != issuer:  # RFC 8414 §3.3: no mix-ups
            raise McpSignInError("This MCP server's authorization server describes itself as another one.")
        if not (_str(metadata.get("authorization_endpoint")) and _str(metadata.get("token_endpoint"))):
            raise McpSignInError("This MCP server's authorization server doesn't say where to sign in.")
        if "S256" not in (metadata.get("code_challenge_methods_supported") or []):
            raise McpSignInError("This MCP server's authorization server doesn't support PKCE, which BotDesk requires.")
        return metadata
    raise McpSignInError("Couldn't find this MCP server's authorization server.")


async def register(
    http: httpx.AsyncClient, found: Mapping[str, Any], redirect_uri: str, guard: Guard
) -> tuple[str, str | None]:
    """Dynamic client registration (RFC 7591): BotDesk as a public client using PKCE. Returns
    the client id and the secret if the server issued one anyway."""
    endpoint = found.get("registrationEndpoint")
    if not endpoint:
        raise McpSignInError(
            "This MCP server doesn't let BotDesk register itself. Create an OAuth client in its "
            "settings and paste the client ID (and secret) here."
        )
    body = {
        "client_name": "BotDesk",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if found.get("scopes"):
        body["scope"] = " ".join(found["scopes"])
    response = await http.post(await guard(str(endpoint)), json=body, headers={"Accept": "application/json"})
    try:
        answer = response.json() if response.status_code in (200, 201) else None
    except ValueError:
        answer = None
    client_id = _str(answer.get("client_id")) if isinstance(answer, dict) else None
    if client_id is None or not isinstance(answer, dict):
        raise McpSignInError("This MCP server refused to register BotDesk as a client.")
    return client_id, _str(answer.get("client_secret"))


def authorize_url(
    found: Mapping[str, Any], client_id: str, redirect_uri: str, *, state: str, code_challenge: str
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "resource": str(found["resource"]),
    }
    if found.get("scopes"):
        params["scope"] = " ".join(found["scopes"])
    endpoint = str(found["authorizationEndpoint"])
    return f"{endpoint}{'&' if '?' in endpoint else '?'}{urlencode(params)}"


async def token_request(
    http: httpx.AsyncClient,
    found: Mapping[str, Any],
    client_id: str,
    client_secret: str | None,
    form: Mapping[str, str],
    guard: Guard,
) -> httpx.Response:
    """POST the token endpoint with `form` plus the client and the `resource`. A client secret
    goes in a Basic header when the server doesn't take it in the form."""
    data = {**form, "client_id": client_id, "resource": str(found["resource"])}
    headers = {"Accept": "application/json"}
    if client_secret:
        methods = found.get("tokenAuthMethods") or []
        if methods and "client_secret_post" not in methods and "client_secret_basic" in methods:
            pair = f"{quote(client_id, safe='')}:{quote(client_secret, safe='')}".encode()  # RFC 6749 §2.3.1
            headers["Authorization"] = "Basic " + base64.b64encode(pair).decode()
        else:
            data["client_secret"] = client_secret
    return await http.post(await guard(str(found["tokenEndpoint"])), data=data, headers=headers)
