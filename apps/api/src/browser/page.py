"""What a bot sees of a page (ADR 0017 §4): its address, title, visible text, and a numbered list
of the things it can click or type into, like browser-use's element list. The numbers are set
on the page itself (`data-botdesk-ref`), so the next tool call finds the same element.

All pure apart from the JavaScript, which runs in the page (`SNAPSHOT_JS`, `INSPECT_JS`).
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

MAX_ELEMENTS = 120
TEXT_CHARS = 6_000

_INTERACTIVE = (
    "a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], "
    "[role=tab], [role=menuitem], [role=checkbox], [role=radio], [role=switch], [role=combobox], "
    "[role=searchbox], [role=textbox], [contenteditable=''], [contenteditable=true]"
)

# One element, as both scripts describe it.
_DESCRIBE = """
const describe = (el, ref) => {
  const tag = el.tagName.toLowerCase();
  const form = el.form || el.closest('form');
  // How Enter would send the form: its default button's own method wins over the form's.
  const submitter = form && form.querySelector(
    'button:not([type]), button[type=submit], input[type=submit], input[type=image]');
  const name = (el.getAttribute('aria-label') || (el.labels && el.labels[0] && el.labels[0].innerText)
    || el.getAttribute('placeholder') || el.innerText || (tag === 'input' ? el.value : '')
    || el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('name') || '')
    .replace(/\\s+/g, ' ').trim().slice(0, 80);
  return {
    ref, tag, name,
    type: (el.getAttribute('type') || '').toLowerCase(),
    role: (el.getAttribute('role') || '').toLowerCase(),
    href: tag === 'a' ? el.href : '',
    formMethod: form
      ? ((submitter && submitter.getAttribute('formmethod')) || form.getAttribute('method') || 'get').toLowerCase()
      : '',
  };
};
"""

SNAPSHOT_JS = (
    "(maxElements) => {"
    + _DESCRIBE
    + f"""
  document.querySelectorAll('[data-botdesk-ref]').forEach((el) => el.removeAttribute('data-botdesk-ref'));
  const shown = (el) => {{
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  }};
  const elements = [];
  for (const el of document.querySelectorAll("{_INTERACTIVE}")) {{
    if (elements.length >= maxElements) break;
    if (el.disabled || !shown(el)) continue;
    const ref = elements.length + 1;
    el.setAttribute('data-botdesk-ref', String(ref));
    elements.push(describe(el, ref));
  }}
  const text = ((document.body && document.body.innerText) || '').replace(/\\n{{3,}}/g, '\\n\\n').trim();
  return {{ url: location.href, title: document.title, text, elements }};
}}"""
)

INSPECT_JS = (
    "(ref) => {"
    + _DESCRIBE
    + """
  const el = document.querySelector(`[data-botdesk-ref="${ref}"]`);
  return el ? describe(el, ref) : null;
}"""
)


@dataclass(frozen=True)
class Element:
    ref: int
    tag: str
    name: str
    type: str = ""
    role: str = ""
    href: str = ""
    form_method: str = ""

    @classmethod
    def from_js(cls, raw: dict[str, Any]) -> "Element":
        return cls(
            ref=int(raw["ref"]),
            tag=str(raw.get("tag", "")),
            name=str(raw.get("name", "")),
            type=str(raw.get("type", "")),
            role=str(raw.get("role", "")),
            href=str(raw.get("href", "")),
            form_method=str(raw.get("formMethod", "")),
        )

    @property
    def kind(self) -> str:
        """What people would call it: link, button, search box, text box, password field…"""
        if self.is_password:
            return "password field"
        if self.is_link:
            return "link"
        if self.is_search_box:
            return "search box"
        if self.tag == "select" or self.role == "combobox":
            return "dropdown"
        if self.tag == "textarea" or self.role == "textbox" or (self.tag == "input" and self.type in _TEXT_INPUTS):
            return "text box"
        if self.type in ("checkbox", "radio") or self.role in ("checkbox", "radio", "switch"):
            return self.type or self.role
        return "button"

    @property
    def is_link(self) -> bool:
        """A plain link to another page: following it only reads."""
        return self.tag == "a" and urlsplit(self.href).scheme in ("http", "https")

    @property
    def is_search_box(self) -> bool:
        """A box whose Enter only searches: a text or search box in a form that sends with GET (its
        default button's method included). A box outside a form is left to `browser.type`: what
        its page does on Enter is up to the page's scripts."""
        box = self.role == "searchbox" or (self.tag == "input" and self.type in ("", "text", "search"))
        return box and self.form_method == "get"

    @property
    def is_password(self) -> bool:
        return self.tag == "input" and self.type == "password"

    def line(self) -> str:
        label = f' "{self.name}"' if self.name else ""
        where = f" → {self.href}" if self.is_link else ""
        return f"[{self.ref}] {self.kind}{label}{where}"

    def matches(self, what: str) -> bool:
        """Whether `what` (the bot's words for it, shown on the approval card) names this element:
        it holds the element's whole label, ignoring case and spacing ('the "Send now" button').
        An element with no label matches nothing: people couldn't tell what they approve."""
        mine = _plain(self.name)
        return bool(mine) and mine in _plain(what)


_TEXT_INPUTS = ("", "text", "email", "tel", "url", "number", "search", "date", "time")


def _plain(text: str) -> str:
    return " ".join(text.lower().replace('"', " ").replace("'", " ").split())


@dataclass(frozen=True)
class PageView:
    url: str
    title: str
    text: str
    elements: tuple[Element, ...]

    @classmethod
    def from_js(cls, raw: dict[str, Any]) -> "PageView":
        elements = tuple(Element.from_js(item) for item in raw.get("elements", []))
        return cls(
            url=str(raw.get("url", "")),
            title=str(raw.get("title", "")),
            text=str(raw.get("text", "")),
            elements=elements,
        )

    def result(self, *, start: int = 0) -> dict[str, Any]:
        """The tool result: text a part at a time, and the elements (with the first part only)."""
        part = self.text[start : start + TEXT_CHARS]
        result: dict[str, Any] = {"url": self.url, "title": self.title, "text": part}
        if start + TEXT_CHARS < len(self.text):
            result["more_text_from"] = start + TEXT_CHARS
        if start == 0:
            result["elements"] = [element.line() for element in self.elements]
            if len(self.elements) >= MAX_ELEMENTS:
                result["note"] = f"Only the first {MAX_ELEMENTS} things to click are listed."
        return result
