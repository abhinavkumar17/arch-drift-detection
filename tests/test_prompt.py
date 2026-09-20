import pytest

from core.prompt import prepare_prompt


TEMPLATE = "Rules:\n{{ARCHITECTURE_GUIDELINES}}\nChanges:\n{{ANNOTATED_DIFF}}"
DIFF = """diff --git a/Main.kt b/Main.kt
--- a/Main.kt
+++ b/Main.kt
@@ -1 +1 @@
-old
+new
"""


def test_assembly_preserves_annotations_and_template_text():
    result = prepare_prompt(TEMPLATE, "Keep boundaries clear.", DIFF, 10000)
    assert result.fits
    assert result.text.startswith("Rules:\nKeep boundaries clear.\nChanges:\n")
    assert "Main.kt" in result.text
    assert "[OLD:L1]" in result.text
    assert "[NEW:L1]" in result.text
    assert "{{ANNOTATED_DIFF}}" not in result.text


def test_budget_counts_whole_text_and_accepts_equality():
    # Empty diff leaves six characters: two estimated tokens.
    template = "{{ARCHITECTURE_GUIDELINES}}\n\n{{ANNOTATED_DIFF}}"
    result = prepare_prompt(template, "abcd", "", 2)
    assert result.text == "abcd\n\n"
    assert result.estimated_tokens == 2
    assert result.fits
    assert not prepare_prompt(template, "abcd", "", 1).fits


def test_over_budget_retains_all_annotated_blocks():
    second = DIFF.replace("Main.kt", "Other.kt")
    result = prepare_prompt(TEMPLATE, "Rules", DIFF + second, 1)
    assert not result.fits
    assert "Main.kt" in result.text
    assert "Other.kt" in result.text
    assert result.text.count("[NEW:L1]") == 2


def test_inserted_content_is_not_processed_as_template():
    raw = DIFF.replace("+new", "+{{ARCHITECTURE_GUIDELINES}}")
    result = prepare_prompt(TEMPLATE, "Literal {{ANNOTATED_DIFF}}", raw, 10000)
    assert "Literal {{ANNOTATED_DIFF}}" in result.text
    assert "{{ARCHITECTURE_GUIDELINES}}" in result.text


@pytest.mark.parametrize("slot", ["{{ARCHITECTURE_GUIDELINES}}", "{{ANNOTATED_DIFF}}"])
@pytest.mark.parametrize("count", [0, 2])
def test_invalid_placeholder_count_is_rejected(slot, count):
    template = TEMPLATE.replace(slot, slot * count)
    with pytest.raises(ValueError, match="exactly one"):
        prepare_prompt(template, "Rules", DIFF, 100)


@pytest.mark.parametrize("budget", [0, -1])
def test_nonpositive_budget_is_rejected(budget):
    with pytest.raises(ValueError, match="positive"):
        prepare_prompt(TEMPLATE, "Rules", DIFF, budget)


def test_blank_guidelines_are_rejected():
    with pytest.raises(ValueError, match="must not be empty"):
        prepare_prompt(TEMPLATE, "  \n", DIFF, 100)
