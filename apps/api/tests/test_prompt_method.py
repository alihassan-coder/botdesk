"""How bots work (ADR 0020 §7): every bot gets the working method; a bot with a cloud computer
also gets the computer's habits."""

from src.runtime.prompt import COMPUTER, WORKING_METHOD, build_prompt


def system(**options: object) -> str:
    return str(build_prompt(bot_name="Codi", instructions="", memories=[], history=[], **options)[0].content)  # type: ignore[arg-type]


def test_every_bot_checks_instead_of_guessing_and_ends_with_evidence() -> None:
    text = system()
    assert WORKING_METHOD in text
    assert "never invent results" in text and "evidence" in text


def test_only_a_bot_with_a_computer_is_told_how_to_work_on_it() -> None:
    assert COMPUTER not in system()
    with_computer = system(has_computer=True)
    assert COMPUTER in with_computer
    for habit in ("computer__inspect", "computer__run", "non-interactive", "exit code", "Never print secrets"):
        assert habit in with_computer
