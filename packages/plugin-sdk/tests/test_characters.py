"""Characters an approval card can't show honestly: invisible ones, and ones that reorder the text
around them. A plugin refuses them in what it sends (`hidden_characters`); BotDesk shows the rest
on the card as `[U+...]` (`show_hidden`), so a person never approves text that reads differently
from what goes out. (Escapes only in this file: never the characters themselves.)"""

import pytest

from botdesk_plugin_sdk import describe_character, hidden_characters, show_hidden


@pytest.mark.parametrize(
    "text",
    [
        "Pay \u202eolleh",  # right-to-left override: the rest reads backwards
        "a\u202ab",  # left-to-right embedding
        "a\u2066b\u2069",  # isolates
        "pass\u200bword",  # zero-width space
        "a\u2060b",  # word joiner
        "a\ufeffb",  # byte order mark mid-text
        "a\u00adb",  # soft hyphen
        "secret\U000e0041\U000e0042",  # tag characters: invisible text a model can still read
        "a\u2028b",  # line separator
        "a\u2029b",  # paragraph separator
        "a\x85b",  # next line (C1)
        "a\x1bb",  # escape
        "a\u200eb",  # left-to-right mark
        "a\u3164b",  # Hangul filler
        "a\ue000b",  # private use
        "a\U000e0100b",  # variation selector 17: can smuggle a byte after any letter
        "Hi\ufe0f there",  # emoji presentation after a letter: hides a bit, shows nothing
        "1\ufe0f",  # after a digit only as part of a keycap
        "Hel\u200dlo",  # a joiner between Latin letters joins nothing
        "don\u2019\ufe0ft",  # after a curly quote, too
        "\u200d\U0001f4bb",  # a joiner with nothing before it
        "\U0001f469\u200d\u200d\U0001f4bb",  # two in a row
    ],
)
def test_hidden_characters_are_found(text: str) -> None:
    assert hidden_characters(text)


@pytest.mark.parametrize(
    "text",
    [
        "Plain text, \u201cquotes\u201d, dashes \u2014 and caf\u00e9.",
        "Launch \U0001f389 at 3 PM",
        "\u2764\ufe0f and \u263a\ufe0e",  # emoji and text presentation after a symbol
        "\U0001f469\u200d\U0001f4bb",  # woman technologist: a joiner between emoji
        "\U0001f3f3\ufe0f\u200d\U0001f308",  # rainbow flag: selector, then joiner
        "\U0001f44d\U0001f3fd",  # skin tone modifier
        "1\ufe0f\u20e3",  # keycap one
        "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",  # Persian: a non-joiner between letters
        "\u0915\u094d\u200d\u0937",  # Devanagari: a joiner after a virama
        "\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd",  # right-to-left text needs no control characters
        "\u00a0non-breaking\u2009thin spaces",  # spaces show as spaces
    ],
)
def test_real_writing_is_left_alone(text: str) -> None:
    assert hidden_characters(text) == []


def test_line_breaks_and_tabs_count_only_when_asked() -> None:
    assert hidden_characters("one\ntwo\tthree\r\n") == [3, 7, 13, 14]
    assert hidden_characters("one\ntwo\tthree\r\n", layout=True) == []


def test_show_hidden_makes_each_one_visible_and_keeps_the_rest() -> None:
    assert show_hidden("Pay \u202eolleh\u200b \U0001f389") == "Pay [U+202E]olleh[U+200B] \U0001f389"
    assert show_hidden("one\ntwo\tthree") == "one\ntwo\tthree"  # line breaks stay line breaks on a card
    assert show_hidden("\U0001f469\u200d\U0001f4bb") == "\U0001f469\u200d\U0001f4bb"
    assert show_hidden("secret\U000e0041") == "secret[U+E0041]"


def test_describe_character_names_it() -> None:
    assert describe_character("\u202e") == "U+202E RIGHT-TO-LEFT OVERRIDE"
    assert describe_character("\ue000") == "U+E000 (no name)"


def test_a_pile_of_combining_marks_is_found_but_real_accents_are_not() -> None:
    base = "Pay 100"
    piled = base + chr(0x0336) * 6  # stacked strokes: text that reads as struck out or smeared
    assert hidden_characters(piled) == [11, 12]  # the fifth and sixth in a row
    assert hidden_characters("e" + chr(0x0302) + chr(0x0301)) == []  # Vietnamese: two marks
    assert hidden_characters(chr(0x05E9) + chr(0x05BC) + chr(0x05C1) + chr(0x05B8)) == []  # Hebrew: three
    assert show_hidden(piled).endswith("[U+0336][U+0336]")
