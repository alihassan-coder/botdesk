"""Calls to the Gmail REST API through `ctx.http`, and readable failures.

The credential is added by BotDesk, never here. A failure is a `GmailError` whose message says
what happened and what to do, in words safe for the model and for people: a status code and our
own text only, never Google's answer (which can quote the request) or a header.
"""

from typing import Any

from botdesk_plugin_sdk import HttpClient, HttpResponse
from botdesk_plugin_sdk.http import Params

GMAIL_HOST = "gmail.googleapis.com"
GMAIL_API = f"https://{GMAIL_HOST}"
USERS_ME = f"{GMAIL_API}/gmail/v1/users/me"


class GmailError(Exception):
    """Gmail said no, or answered something unreadable. The message is safe to show."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


async def get(http: HttpClient, path: str, *, what: str, account: str | None, params: Params | None = None) -> Any:
    """GET `users/me/{path}` and return its JSON. `what` names the thing for a 404 ("thread 18f0a0")."""
    return _answer(await http.request("GET", f"{USERS_ME}/{path}", params=params), what=what, account=account)


async def post(http: HttpClient, path: str, *, what: str, account: str | None, body: Any = None) -> Any:
    """POST `body` as JSON to `users/me/{path}`, once (no retry: a send must never happen twice),
    and return the JSON answer."""
    return _answer(await http.request("POST", f"{USERS_ME}/{path}", json=body), what=what, account=account)


def _answer(response: HttpResponse, *, what: str, account: str | None) -> Any:
    if not response.ok:
        raise GmailError(_failure(response, what=what, account=account), response.status_code)
    try:
        return response.json()
    except ValueError as error:
        raise GmailError("Gmail sent an answer BotDesk couldn't read. Try again.", response.status_code) from error


def _failure(response: HttpResponse, *, what: str, account: str | None) -> str:
    status = response.status_code
    mailbox = account or "this Gmail account"
    if status == 401:
        return f"Gmail didn't accept the sign-in for {mailbox}. Reconnect Gmail in Connect apps, then try again."
    if status == 403:
        return (
            f"Gmail refused this for {mailbox} (403). The connection may not have the access this needs, or the "
            "Gmail API isn't enabled in the server's Google project. Reconnecting Gmail in Connect apps may fix it."
        )
    if status == 404:
        return f"Gmail has no {what}. It may have been deleted, or the id is wrong."
    if status == 429:
        return "Gmail is limiting how fast this account can be read right now. Wait a minute and try again."
    if status >= 500:
        return f"Gmail had a problem on its side (status {status}). Try again in a little while."
    return f"Gmail didn't accept the request for {what} (status {status})."
