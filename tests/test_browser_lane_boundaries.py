from __future__ import annotations

from spark_character import chip_context_for


def test_spark_browser_synthetic_context_marks_legacy_extension_boundary() -> None:
    context = chip_context_for(["spark-browser"])

    assert "legacy browser extension path" in context
    assert "browser-use MCP lane" in context
    assert "provides live web browsing" not in context
