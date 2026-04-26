"""Voice-rule post-processors for LLM output.

These run after generation, before delivery. Use them when the model
won't honor a rule from the system prompt no matter how loudly we ask.

Currently scoped to safe typography fixes: em-dash family substitution
and paired Markdown emphasis removal. Production telemetry showed these
leaks despite explicit persona rules. Prompt-layer correction has been
insufficient, so we apply deterministic post-output fixes at the runtime
boundary.

Other voice violations (plumbing leaks, reset openers, hedge openers)
require regeneration rather than substitution, so they are not handled
here. Leave those to the critic.
"""

from __future__ import annotations

import re
import unicodedata

EM_DASH_FAMILY = (
    "\u2014",  # em dash
    "\u2013",  # en dash
    "\u2012",  # figure dash
    "\u2015",  # horizontal bar
    "\u2212",  # minus sign (rare in prose, but models do emit it)
)


def is_dash_punctuation(ch: str) -> bool:
    return unicodedata.category(ch) == "Pd" or ch == "\u2212"


def strip_format_controls(text: str) -> str:
    """Remove Unicode format controls such as bidi and zero-width marks."""
    if not text:
        return text
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def replace_em_dashes(text: str, replacement: str = " - ") -> str:
    """Replace Unicode dash punctuation with a plain hyphen separator.

    Default replacement is " - " (space-hyphen-space) to match the
    typographic role an em dash usually plays as a parenthetical
    separator. The function then collapses any double spaces this
    introduces, so existing single-spaced "word — word" becomes
    "word - word", not "word  -  word".
    """
    if not text:
        return text
    out = unicodedata.normalize("NFKD", text)
    out = "".join(replacement if is_dash_punctuation(ch) else ch for ch in out)
    while "  " in out:
        out = out.replace("  ", " ")
    return out


def strip_markdown_emphasis(text: str) -> str:
    """Remove paired bold/italic emphasis markers while preserving bullets."""
    if not text:
        return text
    out = re.sub(r"\*\*\*([^*\n][\s\S]*?[^*\n])\*\*\*", r"\1", text)
    out = re.sub(r"\*\*([^*\n][\s\S]*?[^*\n])\*\*", r"\1", out)
    out = re.sub(r"__([^_\n][\s\S]*?[^_\n])__", r"\1", out)
    return out


def sanitize_voice_output(text: str) -> str:
    """Apply all voice post-processors that are safe to run in production."""
    return strip_markdown_emphasis(replace_em_dashes(strip_format_controls(text)))
