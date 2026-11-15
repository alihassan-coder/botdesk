"""Mention routing (ADR 0009): which bots get a run for a message, at what hop, and why.

Pure: the caller loads the chat's bots and the organization's bots by handle; this decides.

- **A member's message in a group:** the bots in the chat it @mentions, in mention order; with
  no bot mentioned, the group's **lead** (nobody when it has none).
- **A member's message in a DM:** with no bot mentioned, the DM's own bot. A member who
  @mentions other bots of the organization pulls each in as a **guest** for one reply; the
  DM's bot then replies only if it is mentioned too (mentions pick who answers, as in a group).
- **A bot's reply:** the bots it @mentions that are already in the chat (a group's bots; in a
  DM, its bot and the guests pulled in before), never itself, one **hop** further on. A bot
  can't pull a new bot into a DM. A mention that would pass the hop limit starts nothing, and
  `chain_stopped` says so, so the chat can show why.

An email address is never a mention (`mentioned_handles`).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from src.core.handles import mentioned_handles
from src.models.thread import ThreadKind

ReplyReason = Literal["mention", "lead", "dm_bot", "guest"]


@dataclass(frozen=True)
class ChatBots:
    """What routing needs to know about a chat."""

    kind: ThreadKind
    # Bots another bot may mention here: a group's bots; a DM's own bot and its guests so far.
    bots: frozenset[uuid.UUID]
    # Who answers a member's message that mentions no bot: a group's lead, a DM's own bot.
    default_bot: uuid.UUID | None


@dataclass(frozen=True)
class BotAuthor:
    """The message is a bot's reply, written by a run at `hop`."""

    bot_id: uuid.UUID
    hop: int


@dataclass(frozen=True)
class Reply:
    bot_id: uuid.UUID
    hop: int
    reason: ReplyReason


@dataclass(frozen=True)
class Routing:
    replies: tuple[Reply, ...]
    chain_stopped: bool = False  # a bot's mention would have passed the hop limit


def route(
    chat: ChatBots,
    text: str,
    *,
    org_bots: Mapping[str, uuid.UUID],
    hop_limit: int,
    by_bot: BotAuthor | None = None,
) -> Routing:
    """`org_bots` maps @handles to the organization's bots (only the mentioned ones are needed).
    `by_bot` is set when a bot wrote the message; otherwise a member did."""
    mentioned = [org_bots[handle] for handle in mentioned_handles(text) if handle in org_bots]
    if by_bot is not None:
        return _bot_reply(chat, mentioned, by_bot, hop_limit)
    if chat.kind == "dm":
        if not mentioned:
            return _only(chat.default_bot, "dm_bot")
        return Routing(tuple(Reply(bot, 0, "dm_bot" if bot == chat.default_bot else "guest") for bot in mentioned))
    in_chat = [bot for bot in mentioned if bot in chat.bots]
    if not in_chat:
        return _only(chat.default_bot if chat.default_bot in chat.bots else None, "lead")
    return Routing(tuple(Reply(bot, 0, "mention") for bot in in_chat))


def _bot_reply(chat: ChatBots, mentioned: list[uuid.UUID], author: BotAuthor, hop_limit: int) -> Routing:
    targets = [bot for bot in mentioned if bot in chat.bots and bot != author.bot_id]
    if not targets:
        return Routing(())
    hop = author.hop + 1
    if hop > hop_limit:
        return Routing((), chain_stopped=True)
    return Routing(tuple(Reply(bot, hop, "mention") for bot in targets))


def _only(bot_id: uuid.UUID | None, reason: ReplyReason) -> Routing:
    return Routing((Reply(bot_id, 0, reason),) if bot_id else ())
