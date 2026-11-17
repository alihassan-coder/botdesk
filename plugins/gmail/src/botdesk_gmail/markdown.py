"""A small, safe Markdown to HTML conversion for email bodies (`format="markdown"`).

The model never writes HTML: everything it writes is escaped first, then a few Markdown marks
become tags we choose. Supported: `#`/`##`/`###` headings, `-`/`*` and `1.` lists,
paragraphs (a single line break is `<br>`), `**bold**`, `*italic*`/`_italic_`, `` `code` ``
and `[text](url)` links for `http`, `https` and `mailto` only. Anything else stays text.
"""

import html
import re

_HEADING = re.compile(r"^(#{1,3})\s+(.+)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.+)$")
_NUMBERED = re.compile(r"^\s*\d{1,3}[.)]\s+(.+)$")
_LINK = re.compile(r"\[([^\]\n]+)\]\(((?:https?://|mailto:)[^\s()]+)\)", re.IGNORECASE)
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])|(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)")


def _inline(text: str) -> str:
    """One line's text, escaped, with code, links, bold and italic."""
    pieces = text.split("`")
    out: list[str] = []
    for index, piece in enumerate(pieces):
        escaped = html.escape(piece, quote=True)
        if index % 2 and index < len(pieces) - 1:  # between a pair of backticks
            out.append(f"<code>{escaped}</code>")
            continue
        if index % 2:  # an unpaired backtick: keep it as text
            escaped = "`" + escaped
        # Links first, and emphasis only outside their addresses (an `_` or `*` in a URL stays).
        position = 0
        for link in _LINK.finditer(escaped):
            out.append(_emphasis(escaped[position : link.start()]))
            out.append(f'<a href="{link.group(2)}">{_emphasis(link.group(1))}</a>')
            position = link.end()
        out.append(_emphasis(escaped[position:]))
    return "".join(out)


def _emphasis(escaped: str) -> str:
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    return _ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", escaped)


def markdown_to_html(source: str) -> str:
    """An HTML document for `source`, with only the tags this module writes."""
    blocks: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    list_tag = ""

    def close() -> None:
        nonlocal list_tag
        if paragraph:
            blocks.append("<p>" + "<br>\n".join(paragraph) + "</p>")
            paragraph.clear()
        if items:
            blocks.append(f"<{list_tag}>" + "".join(f"<li>{item}</li>" for item in items) + f"</{list_tag}>")
            items.clear()
            list_tag = ""

    for line in source.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        heading, bullet = _HEADING.match(line), _BULLET.match(line)
        item = bullet or _NUMBERED.match(line)
        if not line.strip():
            close()
        elif heading:
            close()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
        elif item:
            tag = "ul" if bullet else "ol"
            if paragraph or (items and list_tag != tag):
                close()
            list_tag = tag
            items.append(_inline(item.group(1).strip()))
        else:
            if items:
                close()
            paragraph.append(_inline(line.strip()))
    close()
    return "<!doctype html>\n<html><body>\n" + "\n".join(blocks) + "\n</body></html>\n"
