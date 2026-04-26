"""Persona + critic artifact loading tests."""

from __future__ import annotations

from spark_character import load_critic, load_persona
from spark_character.scoring import score_persona


def test_load_persona_v1() -> None:
    persona = load_persona("v1")
    assert persona.version == "v1"
    text = persona.system_prompt
    assert "Spark" in text
    assert "Never use em dashes" in text
    assert "researcher" in text.lower()


def test_load_critic_v1() -> None:
    critic = load_critic("v1")
    assert critic.version == "v1"
    text = critic.system_prompt
    assert "PASS" in text
    assert "em dash" in text.lower()
    assert "Avoid Markdown bold/italic emphasis" in text
    assert "paragraphs short" in text


def test_latest_persona_has_chat_scanning_rules() -> None:
    persona = load_persona()
    assert persona.version == "v8"
    text = persona.system_prompt
    assert "short paragraphs" in text
    assert "Avoid Markdown bold or italic emphasis" in text
    assert "Break dense answers into small chunks" in text


def test_persona_text_has_no_em_dash() -> None:
    """The persona spec itself must follow the no-em-dash rule it teaches.

    P3/P2 are deliberately not asserted here: the spec quotes example
    failure phrases ("How can I help today?", "researcher", "raw episode")
    so the scorers fire on the spec text by design. The point is that
    no generated reply passes through the spec scorer, only the model
    output does.
    """
    persona = load_persona("v1")
    score = score_persona(persona.system_prompt)
    assert score.p1_em_dash == 1.0
    assert score.p4_lead == 1.0
