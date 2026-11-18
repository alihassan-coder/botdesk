"""Characters an approval card can't show honestly.

A person approves what the card shows. Some characters show as nothing (a zero-width space, a
soft hyphen, the "tag" characters a model can read but a person can't see) and some reorder the
text around them (a right-to-left override), so a card holding them could read differently from
what is sent, or carry hidden text past the person. Plugins refuse them in what they send
(`hidden_characters`), and BotDesk shows any that reach a card as `[U+202E]` (`show_hidden`).

Real writing keeps what it needs: emoji variation selectors (U+FE0E, U+FE0F) right after a
symbol or a keycap's digit, and the joiners U+200D / U+200C between emoji or between letters of
scripts that use them (Persian, Hindi, ...). Anywhere else they would only hide something. So
does a pile of combining marks: more than `MAX_MARKS` in a row count too.
This file uses character codes only, never the characters themselves.
"""

import unicodedata

# Control, format (bidi controls, zero-width characters, tags...), surrogate, private use,
# unassigned, line and paragraph separators.
_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
# Letters and marks that render as nothing.
_BLANKS = frozenset(
    chr(code)
    for code in (
        0x034F,  # combining grapheme joiner
        0x115F,  # Hangul choseong filler
        0x1160,  # Hangul jungseong filler
        0x17B4,  # Khmer vowel inherent aq
        0x17B5,  # Khmer vowel inherent aa
        0x2800,  # Braille pattern blank
        0x3164,  # Hangul filler
        0xFFA0,  # halfwidth Hangul filler
    )
)
_LAYOUT = frozenset({chr(0x09), chr(0x0A), chr(0x0D)})  # tab, line feed, carriage return
_PRESENTATION = frozenset({chr(0xFE0E), chr(0xFE0F)})  # text / emoji style of what comes before
_ZWNJ, _ZWJ = chr(0x200C), chr(0x200D)
_KEYCAP = chr(0x20E3)
_KEYCAP_BASES = frozenset("#*0123456789")
_FIRST_NON_LATIN = 0x0370  # Greek: letters from here on belong to scripts that may use joiners
# Combining marks one letter may carry (accents, vowel points, a virama...). Real writing stays
# within this; past it, a pile of marks hides or strikes out the text underneath.
MAX_MARKS = 4


def _hidden(char: str) -> bool:
    code = ord(char)
    return (
        unicodedata.category(char) in _HIDDEN_CATEGORIES
        or char in _BLANKS
        or 0xFE00 <= code <= 0xFE0F  # variation selectors
        or 0xE0100 <= code <= 0xE01EF  # variation selectors supplement
        or 0x180B <= code <= 0x180F  # Mongolian variation selectors and vowel separator
    )


def _symbol(char: str) -> bool:
    """An emoji or other symbol (So; Sk covers the skin tone modifiers)."""
    return bool(char) and unicodedata.category(char) in ("So", "Sk")


def _script_letter(char: str) -> bool:
    return bool(char) and ord(char) >= _FIRST_NON_LATIN and unicodedata.category(char)[0] in "LM" and not _hidden(char)


def hidden_characters(text: str, *, layout: bool = False) -> list[int]:
    """Where `text` holds characters a card can't show honestly (their indexes; empty: none).
    `layout`: tabs and line breaks are fine (a body), not only spaces (a subject, a name)."""
    found: list[int] = []
    marks = 0  # combining marks in a row so far
    for index, char in enumerate(text):
        if unicodedata.category(char) in ("Mn", "Me") and not _hidden(char):
            marks += 1
            if marks > MAX_MARKS:  # a pile of them smears or strikes out the text it sits on
                found.append(index)
            continue
        marks = 0
        if (layout and char in _LAYOUT) or not _hidden(char):
            continue
        # The character right before, if it was let through (one hidden character never vouches
        # for the next), the one before that, and the one after.
        before = text[index - 1] if index and (not found or found[-1] != index - 1) else ""
        before_that = text[index - 2] if index >= 2 else ""
        after = text[index + 1] if index + 1 < len(text) else ""
        if not _part_of_writing(char, before, before_that, after):
            found.append(index)
    return found


def _part_of_writing(char: str, before: str, before_that: str, after: str) -> bool:
    """Whether a hidden `char` is one real writing needs, where it stands."""
    if char in _PRESENTATION:
        return _symbol(before) or (before in _KEYCAP_BASES and after == _KEYCAP)
    if char == _ZWJ:
        emoji_before = _symbol(before) or (before in _PRESENTATION and _symbol(before_that))
        return (emoji_before and _symbol(after)) or (_script_letter(before) and _script_letter(after))
    if char == _ZWNJ:
        return _script_letter(before) and _script_letter(after)
    return False


def describe_character(char: str) -> str:
    """ "U+202E RIGHT-TO-LEFT OVERRIDE", for an error message."""
    return f"U+{ord(char):04X} {unicodedata.name(char, '(no name)')}"


def show_hidden(text: str) -> str:
    """`text` with each character a card can't show honestly written as `[U+202E]`. Tabs and line
    breaks stay as they are."""
    hidden = set(hidden_characters(text, layout=True))
    if not hidden:
        return text
    return "".join(f"[U+{ord(char):04X}]" if index in hidden else char for index, char in enumerate(text))
