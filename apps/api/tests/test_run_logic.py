"""Pure run logic: @mentions, run limits, token batching and the prompt. No database needed."""

import asyncio

import pytest

from src.core.handles import mentioned_handles
from src.runtime.limits import RunLimits, limit_reached
from src.runtime.prompt import HistoryLine, build_prompt
from src.runtime.token_batcher import BackgroundSender, TokenBatcher


def test_mentions_are_found_lowercased_once_each_in_order() -> None:
    text = "@Scout can you ask @inbox-manager? Thanks @scout"
    assert mentioned_handles(text) == ["scout", "inbox-manager"]


def test_email_addresses_are_not_mentions() -> None:
    assert mentioned_handles("write to ali@acme.dev please") == []


def test_mention_stops_at_punctuation() -> None:
    assert mentioned_handles("(@release-notes), and @qa.") == ["release-notes", "qa"]


def test_no_limit_is_reached_inside_the_budget() -> None:
    assert limit_reached(RunLimits(max_steps=25, max_seconds=900), steps_used=0, elapsed_seconds=1.0) is None


def test_the_step_limit_stops_a_run_with_a_clear_message() -> None:
    message = limit_reached(RunLimits(max_steps=2, max_seconds=900), steps_used=2, elapsed_seconds=1.0)
    assert message == "This run reached its limit of 2 model steps."


def test_the_time_limit_stops_a_run_with_a_clear_message() -> None:
    message = limit_reached(RunLimits(max_steps=25, max_seconds=60), steps_used=0, elapsed_seconds=61.0)
    assert message == "This run reached its time limit of 1 minute."


def test_tokens_wait_until_enough_time_has_passed() -> None:
    batcher = TokenBatcher(max_wait=0.05, max_chars=100)
    assert batcher.add("Hel", now=0.00) is None
    assert batcher.add("lo", now=0.02) is None
    assert batcher.add(" world", now=0.06) == "Hello world"
    assert batcher.add("!", now=0.07) is None
    assert batcher.flush() == "!"
    assert batcher.flush() is None


def test_a_long_burst_of_tokens_is_sent_before_the_timer() -> None:
    batcher = TokenBatcher(max_wait=10.0, max_chars=5)
    assert batcher.add("abc", now=0.0) is None
    assert batcher.add("def", now=0.0) == "abcdef"


def test_the_prompt_has_instructions_memories_and_the_chat_in_order() -> None:
    prompt = build_prompt(
        bot_name="Scout",
        instructions="Be brief.",
        memories=["Ali prefers bullet points"],
        history=[HistoryLine(from_this_bot=False, text="Hi"), HistoryLine(from_this_bot=True, text="Hello!")],
    )
    assert [m.type for m in prompt] == ["system", "human", "ai"]
    system = str(prompt[0].content)
    assert "You are Scout" in system
    assert "Be brief." in system
    assert "Things you remember:\n- Ali prefers bullet points" in system
    assert [m.content for m in prompt[1:]] == ["Hi", "Hello!"]


def test_the_prompt_skips_the_memory_section_when_there_is_nothing_to_remember() -> None:
    prompt = build_prompt(bot_name="Scout", instructions="", memories=[], history=[])
    assert "remember" not in str(prompt[0].content)


async def test_batches_merge_while_a_slow_write_is_in_flight() -> None:
    sent: list[str] = []

    async def slow_send(text: str) -> None:
        await asyncio.sleep(0.05)  # a database far away
        sent.append(text)

    async with BackgroundSender(slow_send) as sender:
        sender.send("a")  # never waits for the database
        await asyncio.sleep(0.01)  # "a" is being written now
        for piece in ["b", "c", "d"]:
            sender.send(piece)

    assert sent == ["a", "bcd"]  # in order, nothing lost, fewer writes


async def test_a_failed_write_is_raised_when_the_sender_closes() -> None:
    async def broken_send(text: str) -> None:
        raise RuntimeError("database gone")

    with pytest.raises(RuntimeError, match="database gone"):
        async with BackgroundSender(broken_send) as sender:
            sender.send("a")
