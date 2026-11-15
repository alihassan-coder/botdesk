"""Mention routing (ADR 0009): given a chat, who wrote a message and its text, which bots get a
run, at what hop, and whether a chain of bot replies stopped at the hop limit. Pure: no database."""

import uuid

import pytest

from src.services.mention_routing import BotAuthor, ChatBots, Reply, Routing, route

CHIEF, SCOUT, READER, WRITER, OUTSIDER = (uuid.uuid4() for _ in range(5))
ORG_BOTS = {"chief": CHIEF, "scout": SCOUT, "reader": READER, "writer": WRITER, "outsider": OUTSIDER}
NAMES = {CHIEF: "chief", SCOUT: "scout", READER: "reader", WRITER: "writer", OUTSIDER: "outsider"}
LIMIT = 3

# A group with Chief (the lead), Scout and Reader; Writer and Outsider are in the org, not the chat.
GROUP = ChatBots(kind="group", bots=frozenset({CHIEF, SCOUT, READER}), default_bot=CHIEF)
GROUP_NO_LEAD = ChatBots(kind="group", bots=frozenset({CHIEF, SCOUT, READER}), default_bot=None)
# Your DM with Chief; Reader was pulled in earlier, so it's a guest there.
DM = ChatBots(kind="dm", bots=frozenset({CHIEF, READER}), default_bot=CHIEF)


def _who(routing: Routing) -> list[tuple[str, int, str]]:
    return [(NAMES[reply.bot_id], reply.hop, reply.reason) for reply in routing.replies]


MEMBER_CASES = [
    # (name, chat, text, expected replies)
    ("group: no mention goes to the lead", GROUP, "what's new?", [("chief", 0, "lead")]),
    ("group: no mention and no lead: nobody", GROUP_NO_LEAD, "what's new?", []),
    (
        "group: mentions in mention order",
        GROUP,
        "@reader then @scout",
        [("reader", 0, "mention"), ("scout", 0, "mention")],
    ),
    ("group: a mention replaces the lead", GROUP, "@scout only", [("scout", 0, "mention")]),
    ("group: mentioning the lead is a mention", GROUP, "@chief hi", [("chief", 0, "mention")]),
    ("group: duplicate mentions reply once", GROUP, "@scout @Scout @scout", [("scout", 0, "mention")]),
    ("group: an email address is not a mention", GROUP, "mail scout@acme.dev", [("chief", 0, "lead")]),
    ("group: a bot outside the chat is ignored", GROUP, "@writer help", [("chief", 0, "lead")]),
    ("group: outside bots are skipped, inside ones reply", GROUP, "@writer @reader", [("reader", 0, "mention")]),
    ("group: an unknown handle is ignored", GROUP_NO_LEAD, "@nobody there?", []),
    ("dm: no mention: the DM's bot", DM, "hello", [("chief", 0, "dm_bot")]),
    ("dm: an email address is not a mention", DM, "write to writer@acme.dev", [("chief", 0, "dm_bot")]),
    ("dm: an unknown handle: the DM's bot", DM, "@nobody?", [("chief", 0, "dm_bot")]),
    ("dm: another org bot joins as a guest", DM, "@writer draft it", [("writer", 0, "guest")]),
    ("dm: an earlier guest can be pulled in again", DM, "@reader again", [("reader", 0, "guest")]),
    (
        "dm: the DM's bot replies too when mentioned, in mention order",
        DM,
        "@writer and @chief",
        [("writer", 0, "guest"), ("chief", 0, "dm_bot")],
    ),
    ("dm: duplicate guest mentions reply once", DM, "@writer @writer", [("writer", 0, "guest")]),
]


@pytest.mark.parametrize(
    ("chat", "text", "expected"), [case[1:] for case in MEMBER_CASES], ids=[c[0] for c in MEMBER_CASES]
)
def test_a_members_message(chat: ChatBots, text: str, expected: list[tuple[str, int, str]]) -> None:
    routing = route(chat, text, org_bots=ORG_BOTS, hop_limit=LIMIT)

    assert _who(routing) == expected
    assert routing.chain_stopped is False


BOT_CASES = [
    # (name, chat, author, author's hop, text, expected replies, chain stopped)
    ("group: no mention: nobody (the lead answers people only)", GROUP, SCOUT, 0, "done", [], False),
    ("group: a mention starts a run one hop on", GROUP, CHIEF, 0, "@scout look", [("scout", 1, "mention")], False),
    (
        "group: several mentions, in order",
        GROUP,
        CHIEF,
        1,
        "@reader @scout",
        [("reader", 2, "mention"), ("scout", 2, "mention")],
        False,
    ),
    ("group: a bot never triggers itself", GROUP, SCOUT, 0, "@scout here", [], False),
    ("group: itself skipped, others reply", GROUP, SCOUT, 0, "@scout @reader", [("reader", 1, "mention")], False),
    ("group: a bot outside the chat is ignored", GROUP, CHIEF, 0, "@writer help", [], False),
    ("group: an email address is not a mention", GROUP, CHIEF, 0, "reader@acme.dev", [], False),
    ("group: duplicate mentions reply once", GROUP, CHIEF, 0, "@scout @scout", [("scout", 1, "mention")], False),
    ("group: the last allowed hop", GROUP, CHIEF, LIMIT - 1, "@scout", [("scout", LIMIT, "mention")], False),
    ("group: past the hop limit: stopped", GROUP, CHIEF, LIMIT, "@scout", [], True),
    ("group: well past the limit: stopped", GROUP, CHIEF, LIMIT + 2, "@scout", [], True),
    ("group: at the limit with no mention: not a stop", GROUP, CHIEF, LIMIT, "all done", [], False),
    ("group: at the limit, only itself mentioned: not a stop", GROUP, CHIEF, LIMIT, "@chief", [], False),
    ("dm: the guest mentions the DM's bot", DM, READER, 0, "@chief over to you", [("chief", 1, "mention")], False),
    ("dm: the DM's bot mentions its guest", DM, CHIEF, 1, "@reader?", [("reader", 2, "mention")], False),
    ("dm: a bot can't pull a new bot in", DM, CHIEF, 0, "@writer help", [], False),
    ("dm: a bot never triggers itself", DM, CHIEF, 0, "@chief", [], False),
    ("dm: no mention: nobody", DM, READER, 0, "here you go", [], False),
    ("dm: past the hop limit: stopped", DM, READER, LIMIT, "@chief", [], True),
]


@pytest.mark.parametrize(
    ("chat", "author", "hop", "text", "expected", "stopped"),
    [case[1:] for case in BOT_CASES],
    ids=[c[0] for c in BOT_CASES],
)
def test_a_bots_reply(
    chat: ChatBots,
    author: uuid.UUID,
    hop: int,
    text: str,
    expected: list[tuple[str, int, str]],
    stopped: bool,
) -> None:
    routing = route(chat, text, org_bots=ORG_BOTS, by_bot=BotAuthor(bot_id=author, hop=hop), hop_limit=LIMIT)

    assert _who(routing) == expected
    assert routing.chain_stopped is stopped


def test_a_hop_limit_of_zero_means_bots_never_start_runs() -> None:
    routing = route(GROUP, "@scout", org_bots=ORG_BOTS, by_bot=BotAuthor(bot_id=CHIEF, hop=0), hop_limit=0)

    assert routing == Routing(replies=(), chain_stopped=True)


def test_replies_are_plain_values() -> None:
    routing = route(GROUP, "@scout", org_bots=ORG_BOTS, hop_limit=LIMIT)

    assert routing.replies == (Reply(bot_id=SCOUT, hop=0, reason="mention"),)
