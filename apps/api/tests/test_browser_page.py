"""What a bot sees of a page and which tool may touch which element (ADR 0017 §4), and the Local
browser's address rules (§6). No browser needed."""

import pytest

from src.browser.browsers import file_name
from src.browser.guard import NOT_WEB, PRIVATE, AddressGuard
from src.browser.page import TEXT_CHARS, Element, PageView


def element(**fields: str) -> Element:
    return Element(ref=1, tag=fields.pop("tag", "button"), name=fields.pop("name", ""), **fields)


def test_links_and_search_boxes_only_read_everything_else_is_a_button() -> None:
    assert element(tag="a", href="https://acme.dev/pricing").is_link
    assert not element(tag="a", href="javascript:buy()").is_link
    assert element(tag="input", type="search", form_method="get").is_search_box
    assert element(tag="input", type="text", form_method="get").is_search_box
    assert not element(tag="input", type="text", form_method="post").is_search_box
    assert not element(tag="input", type="search").is_search_box  # no form: Enter does what the page likes
    assert element(tag="input", type="password").kind == "password field"
    assert element(tag="button", name="Send").kind == "button"
    assert element(tag="div", role="button").kind == "button"


def test_the_words_on_an_approval_card_must_fit_the_element() -> None:
    send = element(name="Send now")
    assert send.matches('the "Send now" button')
    assert send.matches("send  NOW")
    assert not send.matches("send")  # part of a label could hide the rest ("Delete account" as "e")
    assert not send.matches("the Cancel button")
    assert not element(name="").matches("the icon button")  # nothing to check it against


def test_a_page_is_shown_a_part_at_a_time_with_its_elements_first() -> None:
    page = PageView(
        url="https://acme.dev/",
        title="Acme",
        text="x" * (TEXT_CHARS + 10),
        elements=(Element(ref=1, tag="a", name="Pricing", href="https://acme.dev/pricing"),),
    )
    first = page.result()
    assert first["elements"] == ['[1] link "Pricing" → https://acme.dev/pricing']
    assert first["more_text_from"] == TEXT_CHARS
    rest = page.result(start=TEXT_CHARS)
    assert (rest["text"], "elements" in rest, "more_text_from" in rest) == ("x" * 10, False, False)


async def _resolve(host: str) -> list[str]:
    return {"acme.dev": ["93.184.215.14"], "intranet.acme.dev": ["10.0.0.7"]}[host]


@pytest.mark.parametrize(
    ("url", "why"),
    [
        ("https://acme.dev/", None),
        ("https://intranet.acme.dev/", PRIVATE),
        ("http://127.0.0.1:8000/", PRIVATE),
        ("http://[::1]/", PRIVATE),
        ("file:///etc/passwd", NOT_WEB),
        ("chrome://settings", NOT_WEB),
    ],
)
async def test_the_local_browser_only_opens_public_web_pages(url: str, why: str | None) -> None:
    assert await AddressGuard(allow_private=False, resolve=_resolve).why_not(url) == why


async def test_a_page_may_load_its_own_data_but_not_private_addresses() -> None:
    guard = AddressGuard(allow_private=False, resolve=_resolve)
    assert await guard.allows("data:image/png;base64,AAAA")
    assert not await guard.allows("http://10.1.2.3/admin")
    assert await AddressGuard(allow_private=True, resolve=_resolve).allows("http://10.1.2.3/admin")


@pytest.mark.parametrize(
    ("disposition", "url", "name"),
    [
        ('attachment; filename="Q3 report.pdf"', "https://acme.dev/dl?id=7", "Q3 report.pdf"),
        ("attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf", "https://acme.dev/x", "résumé.pdf"),
        ("", "https://acme.dev/files/q3.csv", "q3.csv"),
        ('attachment; filename="../../etc/passwd"', "https://acme.dev/x", "etc_passwd"),
        ("", "https://acme.dev/", "download"),
    ],
)
def test_downloads_get_a_safe_file_name(disposition: str, url: str, name: str) -> None:
    assert file_name(disposition, url) == name
