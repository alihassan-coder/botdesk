"""Taking over a bot's browser over HTTP (ADR 0017 §5): a person opens a page in it, sees the
screen, clicks and types (to sign in), and makes it forget its sign-ins. Needs Chrome."""

import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from src.browser.local import NOT_INSTALLED
from tests.conftest import sign_up

SIGN_IN = """<!doctype html><title>Sign in</title>
<form action="/done.html" method="get"><input name="user" aria-label="Email" autofocus>
<button>Continue</button></form>"""


@pytest.fixture
def site(tmp_path: Path) -> Iterator[str]:
    (tmp_path / "index.html").write_text(SIGN_IN, encoding="utf-8")
    (tmp_path / "done.html").write_text("<!doctype html><title>Signed in</title>", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def test_a_member_takes_over_the_bots_browser_to_sign_in(client: httpx.AsyncClient, site: str) -> None:
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{org}/bots", json={"name": "Inbox Manager"})).json()
    browser = f"{org}/bots/{bot['id']}/browser"

    closed = (await client.get(browser)).json()
    assert (closed["available"], closed["open"]) == (True, False)
    assert (await client.get(f"{browser}/screen")).status_code == 400  # nothing to show yet

    opened = await client.post(f"{browser}/input", json={"kind": "open", "url": f"{site}/index.html"})
    if opened.status_code == 400 and opened.json()["detail"] == NOT_INSTALLED:
        pytest.skip("No Chrome on this machine")
    assert opened.status_code == 200, opened.text
    assert (opened.json()["open"], opened.json()["title"]) == (True, "Sign in")

    screen = await client.get(f"{browser}/screen")
    assert (screen.headers["content-type"], screen.content[:2]) == ("image/jpeg", b"\xff\xd8")

    await client.post(f"{browser}/input", json={"kind": "type", "text": "ali@acme.dev"})
    done = (await client.post(f"{browser}/input", json={"kind": "key", "key": "Enter"})).json()
    assert done["title"] == "Signed in"

    assert (await client.delete(browser)).status_code == 204
    assert (await client.get(browser)).json()["open"] is False


async def test_take_over_input_is_checked(client: httpx.AsyncClient) -> None:
    me = await sign_up(client)
    org = f"/api/v1/orgs/{me['organizations'][0]['id']}"
    bot = (await client.post(f"{org}/bots", json={"name": "Scout"})).json()
    browser = f"{org}/bots/{bot['id']}/browser"
    assert (await client.post(f"{browser}/input", json={"kind": "key", "key": "Control+W"})).status_code == 422
    assert (await client.post(f"{browser}/input", json={"kind": "click", "x": 5000, "y": 1})).status_code == 422
    other = f"{org}/bots/00000000-0000-0000-0000-000000000000/browser"
    assert (await client.get(other)).status_code == 404
