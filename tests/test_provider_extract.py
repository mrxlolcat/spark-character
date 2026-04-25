"""Provider response extraction tests."""

from __future__ import annotations

from spark_character.provider import _extract_text, _strip_think_blocks


def test_strip_complete_think_block() -> None:
    text = "<think>The user is asking about TVL</think>TVL is Total Value Locked."
    assert _strip_think_blocks(text) == "TVL is Total Value Locked."


def test_strip_multiline_think_block() -> None:
    text = "<think>\nLet me reason through this.\nStep 1: ...\n</think>\n\nShip it."
    assert _strip_think_blocks(text) == "Ship it."


def test_strip_open_only_think_when_no_close() -> None:
    text = "<think>I'm reasoning here without closing.\n\nThe answer is yes."
    cleaned = _strip_think_blocks(text)
    assert "<think" not in cleaned.lower()


def test_passthrough_when_no_think() -> None:
    text = "TVL is Total Value Locked."
    assert _strip_think_blocks(text) == text


def test_extract_text_strips_think_in_content() -> None:
    body = {
        "choices": [
            {"message": {"content": "<think>reasoning</think>Final answer here.", "role": "assistant"}}
        ]
    }
    assert _extract_text(body) == "Final answer here."


def test_extract_text_falls_back_to_reasoning_content() -> None:
    body = {
        "choices": [
            {"message": {"content": "", "reasoning_content": "Here is the reply.", "role": "assistant"}}
        ]
    }
    assert _extract_text(body) == "Here is the reply."


def test_extract_text_handles_missing_choices() -> None:
    assert _extract_text({}) == ""
    assert _extract_text({"choices": []}) == ""
