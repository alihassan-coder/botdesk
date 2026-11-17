"""Turning Gmail messages into text a model may read (ADR 0011 §4).

- Only selected headers survive (`KEPT_HEADERS`), each capped.
- The body is plain text: `text/plain` when the message has it, otherwise its HTML converted
  with the standard library's parser, dropping scripts, styles, hidden elements and zero-width
  filler, showing no images, links as `text (url)`, numbered lists as `1.`, table cells as
  `a | b` and quotes as `> ` lines.
- Quoted earlier mail at the end of a reply ("On … wrote:" and the `> ` lines after it) is left
  out; BotDesk says so outside the email block. A forward, or a message that is only a quote,
  is kept whole.
- Caps: `MESSAGE_CAP` characters per message and `RESULT_CAP` per result, with a `[cut: …]`
  note BotDesk writes outside the email block.
- Email text goes inside `<email>` … `</email>`. A sender can't end the block early (or the
  pipeline's `<untrusted-content>` wrapper): those tags inside the text are defused.

Attachments are listed (name, type, size and the part that holds them); `attachment_text` reads
one when it is text.
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


def kept_headers(headers: Any, names: tuple[str, ...] = KEPT_HEADERS) -> dict[str, str]:
    """The headers a model may see (`names`), by their usual names; repeated ones joined with ", "."""
    canonical = {name.lower(): name for name in names}
    kept: dict[str, list[str]] = {}
    for header in headers if isinstance(headers, list) else []:
        name = canonical.get(str(header.get("name", "")).lower()) if isinstance(header, dict) else None
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
    quoted: int = 0  # characters of quoted earlier mail left out of `text`


def body_of(payload: Any) -> Body:
    """A message's text and its attachments' metadata, from a `format=full` payload."""
    plain: list[str] = []
    rich: list[str] = []
    body = Body()
    for part in _leaves(payload):
        mime = str(part.get("mimeType", "")).lower()
        filename = str(part.get("filename") or "")
        content: dict[str, Any] = part["body"] if isinstance(part.get("body"), dict) else {}
        if is_attachment(part):
            body.attachments.append(
                {
                    "part": defuse(str(part.get("partId", ""))),
                    "name": defuse(filename) or "(no name)",
                    "type": defuse(mime),
                    "size": int(content.get("size") or 0),
                }
            )
        elif mime == "text/plain":
            plain.append(decode(content.get("data"), charset_of(part)))
        elif mime == "text/html":
            rich.append(html_to_text(decode(content.get("data"), charset_of(part))))
    chosen = [text for text in plain if text.strip()] or rich
    body.text, body.quoted = without_quoted_mail(_tidy("\n\n".join(chosen)))
    return body


_ATTRIBUTION_END = re.compile(r"\bwrote:\s*$", re.IGNORECASE)


def without_quoted_mail(text: str) -> tuple[str, int]:
    """`text` without the quoted earlier mail at its end, and how many characters that was.

    Only a trailing quote counts, introduced by an "On … wrote:" line (Gmail and most clients
    wrap it over two lines at most). Anything else is kept: a forward, inline answers between
    quoted lines, or a message that is nothing but a quote."""
    lines = text.split("\n")
    end = len(lines)
    while end and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith(">")):
        end -= 1
    if end == len(lines) or not _ATTRIBUTION_END.search(lines[end - 1] if end else ""):
        return text, 0
    start = end - 1
    if start and not _starts_on(lines[start]) and _starts_on(lines[start - 1]):
        start -= 1
    kept = "\n".join(lines[:start]).rstrip()
    if not kept:
        return text, 0
    return kept, len("\n".join(lines[start:]).strip())


def _starts_on(line: str) -> bool:
    return line.lstrip().lower().startswith("on ")


def is_attachment(part: Mapping[str, Any]) -> bool:
    content = part.get("body")
    return bool(part.get("filename")) or (isinstance(content, dict) and bool(content.get("attachmentId")))


def attachment_part(payload: Any, part_id: str) -> dict[str, Any] | None:
    """The attachment in part `part_id` ("1", "0.2") of a `format=full` payload, or None."""
    return next((leaf for leaf in _leaves(payload) if leaf.get("partId") == part_id and is_attachment(leaf)), None)


def _leaves(part: Any) -> Iterator[dict[str, Any]]:
    if not isinstance(part, dict):
        return
    children = part.get("parts")
    if isinstance(children, list) and children:
        for child in children:
            yield from _leaves(child)
    else:
        yield part


def charset_of(part: Mapping[str, Any]) -> str:
    for header in part.get("headers") or []:
        if isinstance(header, dict) and str(header.get("name", "")).lower() == "content-type":
            match = re.search(r'charset\s*=\s*"?([\w.:-]+)', str(header.get("value", "")), re.IGNORECASE)
            if match:
                return match.group(1)
    return "utf-8"


def decode(data: Any, charset: str) -> str:
    """Gmail's base64url `data`, as text in `charset` (UTF-8 when unknown)."""
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


# Invisible characters newsletters pad their preview text with (not U+200D, which joins emoji).
_ZERO_WIDTH = re.compile("[\u00ad\u034f\u061c\u200b\u200c\u200e\u200f\u2060\ufeff]")


def _tidy(text: str) -> str:
    text = _ZERO_WIDTH.sub("", text)
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
    items: int = 0  # an <ol>'s items so far


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
        if tag == "li" and not hidden:
            self.out.append(self._bullet())
        elif tag in _BLOCKS and not hidden:
            self.out.append("\n")
        elif tag in ("td", "th") and not hidden:
            self._cell()
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
            if open_.tag == "blockquote" and not open_.hidden:
                self._quote(open_)
            # A list item or table row starts on a new line; the next one does too.
            if open_.tag in _BLOCKS and open_.tag not in ("li", "tr") and not open_.hidden:
                self.out.append("\n")
            if open_.tag == tag:
                return

    def handle_data(self, data: str) -> None:
        if self.hidden:
            return
        inside_pre = any(open_.tag == "pre" for open_ in self.stack)
        self.out.append(data if inside_pre else re.sub(r"\s+", " ", data))

    def _nearest(self, *tags: str) -> _Open | None:
        return next((open_ for open_ in reversed(self.stack) if open_.tag in tags), None)

    def _bullet(self) -> str:
        listing = self._nearest("ol", "ul")
        if listing is None or listing.tag == "ul":
            return "\n- "
        listing.items += 1
        return f"\n{listing.items}. "

    def _cell(self) -> None:
        """Cells of a row read as `a | b`; empty ones (layout spacers) add nothing."""
        row = self._nearest("tr", "table")
        if row is not None and row.tag == "tr" and "".join(self.out[row.start :]).strip():
            self.out.append(" | ")

    def _quote(self, open_: _Open) -> None:
        lines = (" ".join(line.split()) for line in "".join(self.out[open_.start :]).split("\n"))
        del self.out[open_.start :]
        self.out.append("".join(f"\n> {line}" for line in lines if line) + "\n")

    def _link(self, open_: _Open) -> None:
        url = (open_.href or "").strip()
        if not re.match(r"(?:https?|mailto):", url, re.IGNORECASE):
            return  # javascript:, data:, relative: nothing worth showing
        shown = "".join(self.out[open_.start :]).strip()
        if not shown:
            return  # an image or an empty link: no text to attach the address to
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
    text = _ZERO_WIDTH.sub("", "".join(parser.out))
    lines = (" ".join(line.split()) for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def plain_snippet(snippet: Any) -> str:
    """Gmail sends snippets HTML-escaped ("don&#39;t")."""
    return html.unescape(str(snippet or ""))
