"""A fake Orgo for tests (its API as in docs/research/orgo-api.md): keeps computers, apps and links,
records every call, and answers like Orgo, root password and raw address included, so tests can
check BotDesk never passes them on. Nothing here reaches orgo.ai."""

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any

import httpx

HOST = "www.orgo.ai"
KEY = "sk_live_fake_orgo_key_9876"
ROOT_PASSWORD = "vnc-root-password-0000"
RAW_ADDRESS = "203.0.113.7"
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
PNG = b"\x89PNG\r\n\x1a\nfake-png"

BashAnswer = Callable[[str], dict[str, Any] | httpx.Response]


class FakeOrgo:
    def __init__(self, key: str = KEY) -> None:
        self.key = key
        self.calls: list[tuple[str, str, Any]] = []
        self.idempotency_keys: list[str] = []
        self.workspaces: list[dict[str, Any]] = [{"id": "ws-prod", "name": "production", "computers": []}]
        self.computers: dict[str, dict[str, Any]] = {}
        self.apps: dict[str, list[dict[str, Any]]] = {}
        self.previews: dict[str, list[dict[str, Any]]] = {}
        self.commands: list[str] = []
        self.bash: BashAnswer = lambda _command: {"output": "ok\n", "exit_code": 0, "success": True}
        self.refuse: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}  # (method, path end) → answer
        self.boot_gets = 0  # GETs a starting computer answers "starting" before it runs
        self.create_seconds = 0.0
        self.actions: list[tuple[str, Any]] = []  # clicks, typing, keys, scrolls
        self._made = 0
        self._by_key: dict[str, str] = {}

    def made(self) -> int:
        return sum(1 for method, path, _ in self.calls if (method, path) == ("POST", "/computers"))

    def called(self, method: str, path: str) -> int:
        return sum(1 for call in self.calls if call[:2] == (method, path))

    async def handle_slowly(self, request: httpx.Request) -> httpx.Response:
        """As `handle`, with making a computer taking `create_seconds` (two callers race)."""
        if (request.method, request.url.path) == ("POST", "/api/computers"):
            await asyncio.sleep(self.create_seconds)
        return self.handle(request)

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path.removeprefix("/api")
        self.calls.append((request.method, path, body))
        if request.headers.get("authorization") != f"Bearer {self.key}":
            return httpx.Response(401, json={"error": "Invalid API key"})
        for (method, end), (status, answer) in self.refuse.items():
            if request.method == method and path.endswith(end):
                return httpx.Response(status, json=answer)
        return self._route(request, path, body)

    def _route(self, request: httpx.Request, path: str, body: Any) -> httpx.Response:
        method = request.method
        if (method, path) == ("GET", "/me"):
            return httpx.Response(200, json={"id": "acct-1", "email": "ali@acme.dev", "tier": "free"})
        if path == "/workspaces":
            if method == "GET":
                return httpx.Response(200, json={"workspaces": self.workspaces})
            made = {"id": f"ws-{len(self.workspaces) + 1}", "name": body["name"], "computers": []}
            self.workspaces.append(made)
            return httpx.Response(201, json=made)
        if (method, path) == ("POST", "/computers"):
            return self._create(request, body)
        found = re.fullmatch(r"/computers/([^/]+)(/.*)?", path)
        if not found:
            return httpx.Response(404, json={"error": "Not found"})
        remote_id, action = found.group(1), found.group(2) or ""
        computer = self.computers.get(remote_id)
        if computer is None:
            return httpx.Response(
                404, json={"error": "Computer not found (computer_not_found).", "code": "computer_not_found"}
            )
        return self._act(request, computer, action, body)

    def _create(self, request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        key = request.headers.get("idempotency-key", "")
        self.idempotency_keys.append(key)
        if key and key in self._by_key and self._by_key[key] in self.computers:
            return httpx.Response(201, json=self.computers[self._by_key[key]])
        if any(c["name"] == body["name"] for c in self.computers.values()):
            return httpx.Response(409, json={"error": "That name is taken.", "code": "NAME_TAKEN"})
        self._made += 1
        computer = {
            "id": f"pc-{self._made}",
            "name": body["name"],
            "project_id": body["workspace_id"],
            "os": body.get("os", "linux"),
            "ram": body.get("ram"),
            "cpu": body.get("cpu"),
            "region": "us",
            "status": "starting" if self.boot_gets else "running",
            "gets": 0,
            "vnc_password": ROOT_PASSWORD,
            "url": RAW_ADDRESS,
            "connection_url": f"vnc://{RAW_ADDRESS}:5900",
        }
        self.computers[computer["id"]] = computer
        self._by_key[key] = computer["id"]
        return httpx.Response(201, json=computer)

    def _act(self, request: httpx.Request, computer: dict[str, Any], action: str, body: Any) -> httpx.Response:
        method, remote_id = request.method, computer["id"]
        if action == "" and method == "GET":
            if computer["status"] == "starting":
                computer["gets"] += 1
                if computer["gets"] > self.boot_gets:
                    computer["status"] = "running"
            return httpx.Response(200, json=computer)
        if action == "" and method == "DELETE":
            del self.computers[remote_id]
            return httpx.Response(200, json={"success": True})
        if action == "/start":
            computer["status"], computer["gets"] = ("starting" if self.boot_gets else "running"), 0
            return httpx.Response(202, json={"id": remote_id, "status": "starting", "operation_id": "op-1"})
        if action == "/stop":
            computer["status"] = "stopped"
            return httpx.Response(202, json={"id": remote_id, "status": "stopping", "operation_id": "op-2"})
        if computer["status"] != "running":
            return httpx.Response(400, json={"error": "Desktop instance not available"})
        if action == "/bash":
            self.commands.append(body["command"])
            answer = self.bash(body["command"])
            return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)
        if action == "/screenshot":
            image = request.url.params.get("format", "png")
            return httpx.Response(
                200, content=JPEG if image == "jpeg" else PNG, headers={"content-type": f"image/{image}"}
            )
        if action in ("/click", "/type", "/key", "/scroll"):
            self.actions.append((action.strip("/"), body))
            return httpx.Response(200, json={"success": True})
        return self._apps_and_links(method, computer, action, body, request)

    def _apps_and_links(
        self, method: str, computer: dict[str, Any], action: str, body: Any, request: httpx.Request
    ) -> httpx.Response:
        remote_id = computer["id"]
        apps = self.apps.setdefault(remote_id, [])
        if action == "/services" and method == "GET":
            return httpx.Response(200, json={"supported": True, "services": apps})
        if action == "/services" and method == "POST":
            if any(app["name"] == body["name"] for app in apps):
                return httpx.Response(409, json={"error": "Name taken", "code": "NAME_TAKEN"})
            app = {"id": f"app-{len(apps) + 1}-{body['name']}", "status": "running", "port": None, **body}
            apps.append(app)
            return httpx.Response(201, json=app)
        logs = re.fullmatch(r"/services/([^/]+)/logs", action)
        if logs:
            lines = request.url.params.get("lines")
            return httpx.Response(200, json={"id": logs.group(1), "log": f"listening ({lines} lines asked)\n"})
        one = re.fullmatch(r"/services/([^/]+)", action)
        if one and method == "DELETE":
            self.apps[remote_id] = [app for app in apps if app["id"] != one.group(1)]
            return httpx.Response(200, json={"deleted": True, "apply": {"state": "applied"}})
        links = self.previews.setdefault(remote_id, [])
        if action == "/public-urls" and method == "GET":
            return httpx.Response(200, json={"enabled": True, "public_urls": links})
        if action == "/public-urls" and method == "POST":
            link = {
                "id": f"url-{len(links) + 1}",
                "url": f"https://{computer['name']}-a2b3.web.orgo.dev",
                "hostname": f"{computer['name']}-a2b3.web.orgo.dev",
                "label": f"{computer['name']}-a2b3",
                "port": body["port"],
                "created_at": "2026-11-27T12:00:00Z",
                "protected": True,
                "access": "team",
            }
            links.append(link)
            return httpx.Response(201, json=link)
        return httpx.Response(404, json={"error": "Not found"})
