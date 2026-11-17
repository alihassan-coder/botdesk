"""Turning Gmail messages into text a model may read (ADR 0011 §4).

- Only selected headers survive (`KEPT_HEADERS`), each capped.
- The body is plain text: `text/plain` when the message has it, otherwise its HTML converted
  with the standard library's parser, dropping scripts, styles and hidden elements, showing no
  images and links as `text (url)`.
- Caps: `MESSAGE_CAP` characters per message and `RESULT_CAP` per result, with a `[cut: …]`
  note BotDesk writes outside the email block.
- Email text goes inside `<email>` … `</email>`. A sender can't end the block early (or the
  pipeline's `<untrusted-content>` wrapper): those tags inside the text are defused.

Attachments are listed (name, type, size), never read.
"""

import base64
import binascii
import codecs
import html
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

MESSAGE_CAP = 20_000  # characters of one message's text
RESULT_CAP = 60_000  # characters of all messages' text in one result
HEADER_CAP = 1_000  # characters of one header value
URL_CAP = 300

KEPT_HEADERS = ("From", "To", "Cc", "Date", "Subject", "Message-ID", "In-Reply-To", "References")
_CANONICAL = {name.lower(): name for name in KEPT_HEADERS}

# What replaces the "<" of a delimiter tag in outside text: a single left angle quote, so a
# sender's "</email>" still reads as such but closes nothing.
DEFUSED = chr(0x2039)
_DELIMITER = re.compile(r"<(\s*/?\s*)(email|untrusted-content)", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def defuse(text: str) -> str:
    """Outside text, safe to put between delimiters: no tag that opens or closes an `<email>` or
    `<untrusted-content>` block, and no control characters."""
    return _DELIMITER.sub(DEFUSED + r"\1\2", _CONTROL.sub("", text))


def email_block(text: str) -> str:
    return f"<email>\n{defuse(text)}\n</email>"


def kept_headers(headers: Any) -> dict[str, str]:
    """The headers a model may see, by their usual names; repeated ones joined with ", "."""
    kept: dict[str, list[str]] = {}
    for header in headers if isinstance(headers, list) else []:
        name = _CANONICAL.get(str(header.get("name", "")).lower()) if isinstance(header, dict) else None
        if name is not None:
            kept.setdefault(name, []).append(str(header.get("value", "")))
    return {name: _cap_header(", ".join(values)) for name, values in kept.items()}


def _cap_header(value: str) -> str:
    value = defuse(" ".join(value.split()))
    return value if len(value) <= HEADER_CAP else value[:HEADER_CAP] + "…"


# The body


@dataclass
class Body:
    text: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)


def body_of(payload: Any) -> Body:
    """A message's text and its attachments' metadata, from a `format=full` payload."""
    plain: list[str] = []
    rich: list[str] = []
    body = Body()
    for part in _leaves(payload):
        mime = str(part.get("mimeType", "")).lower()
        filename = str(part.get("filename") or "")
        content: dict[str, Any] = part["body"] if isinstance(part.get("body"), dict) else {}
        if filename or content.get("attachmentId"):
            body.attachments.append(
                {"name": defuse(filename) or "(no name)", "type": mime, "size": int(content.get("size") or 0)}
            )
        elif mime == "text/plain":
            plain.append(_decode(content.get("data"), _charset(part)))
        elif mime == "text/html":
            rich.append(html_to_text(_decode(content.get("data"), _charset(part))))
    chosen = [text for text in plain if text.strip()] or rich
    body.text = _tidy("\n\n".join(chosen))
    return body


def _leaves(part: Any) -> Iterator[dict[str, Any]]:
    if not isinstance(part, dict):
        return
    children = part.get("parts")
    if isinstance(children, list) and children:
        for child in children:
            yield from _leaves(child)
    else:
        yield part


def _charset(part: Mapping[str, Any]) -> str:
    for header in part.get("headers") or []:
        if isinstance(header, dict) and str(header.get("name", "")).lower() == "content-type":
            match = re.search(r'charset\s*=\s*"?([\w.:-]+)', str(header.get("value", "")), re.IGNORECASE)
            if match:
                return match.group(1)
    return "utf-8"


def _decode(data: Any, charset: str) -> str:
    if not isinstance(data, str) or not data:
        return ""
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (binascii.Error, ValueError):
        return ""
    try:
        codecs.lookup(charset)
    except LookupError:
        charset = "utf-8"
    return raw.decode(charset, errors="replace")


def _tidy(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def cap(text: str, limit: int) -> tuple[str, int]:
    """`text` cut to `limit` characters, and how many were left out."""
    return (text, 0) if len(text) <= limit else (text[:limit], len(text) - limit)


# HTML to text

_SKIPPED = {"script", "style", "head", "title", "noscript", "template", "svg", "object", "iframe", "canvas"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_BLOCKS = {
    "address", "article", "aside", "blockquote", "div", "dl", "dt", "dd", "fieldset", "figure", "footer", "form",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "main", "nav", "ol", "p", "pre", "section", "table", "tr", "ul",
}  # fmt: skip
_HIDDEN_STYLE = re.compile(
    r"display:none|visibility:hidden|(?:font-size|max-height|max-width|opacity):0(?:\.0*)?(?:px|pt|em|rem|%)?(?:;|!|$)"
)


@dataclass
class _Open:
    tag: str
    hidden: bool
    href: str | None = None
    start: int = 0


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[_Open] = []

    @property
    def hidden(self) -> bool:
        return bool(self.stack) and self.stack[-1].hidden

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID:
            if tag in ("br", "hr") and not self.hidden:
                self.out.append("\n")
            return
        hidden = self.hidden or tag in _SKIPPED or _hides(dict(attrs))
        if tag in _BLOCKS and not hidden:
            self.out.append("\n- " if tag == "li" else "\n")
        href = dict(attrs).get("href") if tag == "a" else None
        self.stack.append(_Open(tag, hidden, href, len(self.out)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("br", "hr") and not self.hidden:
            self.out.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not any(open_.tag == tag for open_ in self.stack):
            return  # a stray end tag
        while self.stack:
            open_ = self.stack.pop()
            if open_.tag == "a" and not open_.hidden:
                self._link(open_)
            if open_.tag in _BLOCKS and open_.tag != "li" and not open_.hidden:
                self.out.append("\n")
            if open_.tag == tag:
                return

    def handle_data(self, data: str) -> None:
        if self.hidden:
            return
        inside_pre = any(open_.tag == "pre" for open_ in self.stack)
        self.out.append(data if inside_pre else re.sub(r"\s+", " ", data))

    def _link(self, open_: _Open) -> None:
        url = (open_.href or "").strip()
        if not re.match(r"(?:https?|mailto):", url, re.IGNORECASE):
            return  # javascript:, data:, relative: nothing worth showing
        shown = "".join(self.out[open_.start :]).strip()
        bare = url[len("mailto:") :] if url.lower().startswith("mailto:") else url
        if bare and bare != shown:
            self.out.append(f" ({url if len(url) <= URL_CAP else url[:URL_CAP] + '…'})")


def _hides(attrs: Mapping[str, str | None]) -> bool:
    if "hidden" in attrs:
        return True
    style = re.sub(r"\s+", "", (attrs.get("style") or "").lower())
    return bool(_HIDDEN_STYLE.search(style))


def html_to_text(markup: str) -> str:
    """Readable text from an email's HTML: no scripts, styles, hidden elements or images."""
    parser = _HtmlText()
    parser.feed(markup)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.out).split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def plain_snippet(snippet: Any) -> str:
    """Gmail sends snippets HTML-escaped ("don&#39;t")."""
    return html.unescape(str(snippet or ""))
