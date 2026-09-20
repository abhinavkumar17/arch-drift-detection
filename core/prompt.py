import re
from dataclasses import dataclass

from core.annotate import annotate, file_blocks
from core.pack import estimate_tokens


@dataclass
class PromptResult:
    text: str
    estimated_tokens: int
    input_budget: int

    @property
    def fits(self) -> bool:
        return self.estimated_tokens <= self.input_budget


def prepare_prompt(
    template: str,
    guidelines: str,
    raw_diff: str,
    input_budget: int,
) -> PromptResult:
    """Assemble and estimate a complete request without trimming files."""
    if input_budget <= 0:
        raise ValueError("Input budget must be positive.")
    if not guidelines.strip():
        raise ValueError("Architecture guidelines must not be empty.")

    guidelines_slot = "{{ARCHITECTURE_GUIDELINES}}"
    diff_slot = "{{ANNOTATED_DIFF}}"

    for slot in (guidelines_slot, diff_slot):
        if template.count(slot) != 1:
            raise ValueError(f"Template must contain exactly one {slot}.")

    blocks = file_blocks(annotate(raw_diff))
    annotated_diff = "\n\n".join(block.text for block in blocks)

    replacements = {
        guidelines_slot: guidelines,
        diff_slot: annotated_diff,
    }
    pattern = "|".join(re.escape(slot) for slot in replacements)
    text = re.sub(
        pattern,
        lambda match: replacements[match.group(0)],
        template,
    )

    return PromptResult(
        text=text,
        estimated_tokens=estimate_tokens(text),
        input_budget=input_budget,
    )
