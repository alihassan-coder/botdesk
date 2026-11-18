"""OAuth 2.1 for MCP servers, the protocol half (ADR 0012 §3, slice 7.3). No database here.

    challenge = parse_challenge(www_authenticate)                 # from the server's 401
    found = await discover(http, server_url, challenge, guard)    # PRM (RFC 9728) → AS metadata (RFC 8414)
    client = await register(http, found, redirect_uri, guard)     # dynamic registration (the fallback)
    document = client_metadata_document(client_id, redirect_uri)  # or a Client ID Metadata Document
    url = authorize_url(found, client_id, redirect_uri, state=…, challenge=…)
    response = await token_request(http, found, client, form, guard)   # code or refresh_token grant
    await revoke(http, found, client_id, secret, token, guard)    # RFC 7009, best effort

- **Discovery**: the 401's `resource_metadata` (else the well-known Protected Resource Metadata
  addresses, path first) names the authorization server; its metadata is read from the RFC 8414 /
  OpenID addresses in the MCP spec's order. Its `issuer` must be the address it was read for, and
  it must offer PKCE S256. The metadata's `resource` must be the server's own origin and a prefix
  of its path: that's the `resource` (RFC 8707) sent with every authorization and token request.
  A server with no PRM (the 2025-03-26 spec) gets its origin as the authorization server.
- **Client registration**, in the MCP spec's order: a client the admin pasted; a **Client ID
  Metadata Document** (the client id is an https address the API serves, when the authorization
  server says it reads them and the API's own address is public https); else dynamic registration
  (RFC 7591), the fallback the spec keeps for older servers.
- **Every address is guarded** (`guard`): https only (unless the network allows http: tests), no
  user info, and every address the host resolves to must be public unless ALLOW_PRIVATE_MCP_URLS.
  The HTTP client underneath is the SSRF guard's transport (the IP checked is the IP connected
  to) and never follows redirects. Every answer is read with a size cap (`MAX_METADATA_BYTES`).
- **Scopes** from the server (its metadata, a 401 or 403 challenge) are kept only when they are
  RFC 6749 scope tokens, at most `MAX_SCOPES` of them.
- **Errors** are `McpSignInError` with a sentence people can act on; never the server's own words.
"""

import base64
import ipaddress
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx

from src.core.errors import BadRequest

MAX_METADATA_BYTES = 256 * 1024  # any answer from a sign-in address: metadata, registration, tokens
MAX_SCOPES = 30
CLIENT_NAME = "BotDesk"
Guard = Callable[[str], Awaitable[str]]  # an address → the same address, or McpSignInError
_SCOPE = re.compile(r"^[\x21\x23-\x5b\x5d-\x7e]{1,200}$")  # RFC 6749 §3.3 scope-token: no space, " or \


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


def safe_scopes(scopes: Iterable[object]) -> list[str]:
    """The scope tokens among `scopes`, in order, each once, at most `MAX_SCOPES`. A server's
    scopes go into the sign-in address and onto the Reconnect screen: nothing else gets through."""
    kept: list[str] = []
    for scope in scopes:
        if isinstance(scope, str) and _SCOPE.match(scope) and scope not in kept:
            kept.append(scope)
    return kept[:MAX_SCOPES]


def is_public_https(url: str) -> bool:
    """Is this our own address as the world sees it (https, a real host name or a public IP)?
    A Client ID Metadata Document is only any use when the authorization server can fetch it."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or host == "localhost" or host.endswith((".localhost", ".local", ".test")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host  # a name; the authorization server resolves it, not us


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _path(url: str) -> str:
    return urlsplit(url).path.rstrip("/")


async def _send(http: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """One request to a sign-in address, its answer read up to `MAX_METADATA_BYTES` (a server
    can't make BotDesk hold an endless body in memory). The answer comes back already read."""
    request = http.build_request(method, url, **kwargs)
    response = await http.send(request, stream=True)
    try:
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_METADATA_BYTES:
                raise McpSignInError("This MCP server's sign-in answered with far more data than expected.")
    finally:
        await response.aclose()
    # The body is decoded already: drop the headers that describe the encoded one.
    headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in _BODY_HEADERS]
    return httpx.Response(response.status_code, headers=headers, content=bytes(body), request=request)


_BODY_HEADERS = {"content-encoding", "content-length", "transfer-encoding"}


async def _get_json(http: httpx.AsyncClient, url: str, guard: Guard) -> dict[str, Any] | None:
    """A metadata document, or None when there isn't one at `url` (any non-200, or not JSON)."""
    response = await _send(http, "GET", await guard(url), headers={"Accept": "application/json"})
    if response.status_code != 200:
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
    `issuer`, `authorizationEndpoint`, `tokenEndpoint`, `registrationEndpoint`,
    `revocationEndpoint`, `resource`, `scopes`, `issParameter` (RFC 9207 `iss` required),
    `metadataDocuments` (it reads Client ID Metadata Documents) and the token endpoint's auth methods."""
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
        scopes = safe_scopes(supported) if isinstance(supported, list) else []
    else:  # the 2025-03-26 spec: the server's origin is its own authorization server
        issuer, resource, scopes = origin, server_url, []
    if challenge.scope:
        scopes = safe_scopes(challenge.scope.split())

    metadata = await _authorization_server(http, issuer.rstrip("/"), guard)
    methods = metadata.get("token_endpoint_auth_methods_supported")
    revocation = _str(metadata.get("revocation_endpoint"))
    return {
        "issuer": issuer.rstrip("/"),
        "authorizationEndpoint": await guard(str(metadata["authorization_endpoint"])),
        "tokenEndpoint": await guard(str(metadata["token_endpoint"])),
        "registrationEndpoint": _str(metadata.get("registration_endpoint")),
        "revocationEndpoint": await guard(revocation) if revocation else None,
        "resource": resource,
        "scopes": scopes,
        "issParameter": metadata.get("authorization_response_iss_parameter_supported") is True,
        "metadataDocuments": metadata.get("client_id_metadata_document_supported") is True,
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


def _client_fields(redirect_uri: str) -> dict[str, Any]:
    """BotDesk as a public client using PKCE: what registration and the metadata document say."""
    return {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


def client_metadata_document(client_id: str, redirect_uri: str) -> dict[str, Any]:
    """The Client ID Metadata Document served at `client_id` (an https address of the API): the
    authorization server fetches it instead of a registration. Nothing in it is secret."""
    return {"client_id": client_id, **_client_fields(redirect_uri)}


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
    body = _client_fields(redirect_uri)
    if found.get("scopes"):
        body["scope"] = " ".join(found["scopes"])
    response = await _send(http, "POST", await guard(str(endpoint)), json=body, headers={"Accept": "application/json"})
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


def _client_auth(
    found: Mapping[str, Any], client_id: str, client_secret: str | None, data: dict[str, str]
) -> dict[str, str]:
    """Add the client to a token or revocation request: its id in the form, and its secret (when
    there is one) in a Basic header if the server doesn't take it in the form. Returns the headers."""
    headers = {"Accept": "application/json"}
    data["client_id"] = client_id
    if client_secret:
        methods = found.get("tokenAuthMethods") or []
        if methods and "client_secret_post" not in methods and "client_secret_basic" in methods:
            pair = f"{quote(client_id, safe='')}:{quote(client_secret, safe='')}".encode()  # RFC 6749 §2.3.1
            headers["Authorization"] = "Basic " + base64.b64encode(pair).decode()
        else:
            data["client_secret"] = client_secret
    return headers


async def token_request(
    http: httpx.AsyncClient,
    found: Mapping[str, Any],
    client_id: str,
    client_secret: str | None,
    form: Mapping[str, str],
    guard: Guard,
) -> httpx.Response:
    """POST the token endpoint with `form` plus the client and the `resource`."""
    data = {**form, "resource": str(found["resource"])}
    headers = _client_auth(found, client_id, client_secret, data)
    return await _send(http, "POST", await guard(str(found["tokenEndpoint"])), data=data, headers=headers)


async def revoke(
    http: httpx.AsyncClient,
    found: Mapping[str, Any],
    client_id: str,
    client_secret: str | None,
    token: str,
    guard: Guard,
    *,
    hint: str = "refresh_token",
) -> bool:
    """Ask the authorization server to forget `token` (RFC 7009). False when it has no
    revocation endpoint or didn't say yes; the caller treats this as best effort."""
    endpoint = found.get("revocationEndpoint")
    if not endpoint:
        return False
    data = {"token": token, "token_type_hint": hint}
    headers = _client_auth(found, client_id, client_secret, data)
    response = await _send(http, "POST", await guard(str(endpoint)), data=data, headers=headers)
    return response.status_code == 200
