"""
pack.py — Stage 4: context budget guard.

Packs annotated file blocks into a model payload under a fixed token budget.

    python pack.py pr.diff            # annotate + pack + evidence log

Design, per review feedback:
  - No category filtering. Nothing is excluded for being a lockfile, a doc,
    a test or generated output — annotate.py sends everything through. The
    only thing that removes a file here is size.
  - No tokenizer library. Token count is estimated from a character count
    using a fixed divisor, deliberately pessimistic.
  - Every decision is logged: per-file cost, running total, and why each
    excluded file was excluded. That log is the evidence.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field

from annotate import annotate, file_blocks

# --- budget ------------------------------------------------------------

CONTEXT_WINDOW_TOKENS = 1_000_000
BUDGET_FRACTION = 0.80          # reserve 20% for prompt template + response
CHARS_PER_TOKEN = 3.0           # pessimistic for code; real is ~3.3-3.6

BUDGET_TOKENS = int(CONTEXT_WINDOW_TOKENS * BUDGET_FRACTION)


def estimate_tokens(text: str) -> int:
    """Characters / CHARS_PER_TOKEN, rounded up.

    Deliberately over-estimates so the 20% reserve absorbs the error. No
    tokenizer dependency: this is the whole counter.
    """
    if not text:
        return 0
    return math.ceil(len(text) / CHARS_PER_TOKEN)


# --- results -----------------------------------------------------------

@dataclass
class FileCost:
    path: str
    tier: str
    chars: int
    tokens: int
    running_total: int
    included: bool
    reason: str = ""


@dataclass
class PackResult:
    included: list = field(default_factory=list)   # list[FileBlock]
    costs: list = field(default_factory=list)      # list[FileCost]
    total_tokens: int = 0
    budget_tokens: int = BUDGET_TOKENS
    stopped_early: bool = False

    @property
    def excluded(self):
        return [c for c in self.costs if not c.included]

    def payload(self) -> str:
        return "\n\n".join(b.text for b in self.included)


# --- packing -----------------------------------------------------------

def pack(blocks,
         budget_tokens: int = BUDGET_TOKENS,
         order=None,
         on_overflow: str = "stop",
         log=print) -> PackResult:
    """Fill the payload up to budget_tokens.

    order:
        None            keep the order given (GitHub's diff order).
        callable        sort key, e.g. lambda b: b.tier != "comment"
                        to put commentable source first.

    on_overflow:
        "stop"  halt at the first file that does not fit. Matches the
                literal instruction: "stop including any other files".
        "skip"  skip that file but keep testing later, smaller ones.

    Both are parameters rather than assumptions because the ordering
    question is still open — the answer changes config, not logic.
    """
    if on_overflow not in ("stop", "skip"):
        raise ValueError("on_overflow must be 'stop' or 'skip'")

    items = list(blocks)
    if order is not None:
        items = sorted(items, key=order)

    result = PackResult(budget_tokens=budget_tokens)
    running = 0

    log(f"budget: {budget_tokens:,} tokens "
        f"({BUDGET_FRACTION:.0%} of {CONTEXT_WINDOW_TOKENS:,}) "
        f"at {CHARS_PER_TOKEN} chars/token")
    log(f"{'file':<58} {'tier':<8} {'chars':>9} {'tokens':>8} {'total':>10}  status")

    for i, b in enumerate(items):
        chars = len(b.text or "")
        tokens = estimate_tokens(b.text)
        fits = running + tokens <= budget_tokens

        if fits:
            running += tokens
            result.included.append(b)
            result.costs.append(FileCost(b.path, b.tier, chars, tokens, running, True))
            status = "ok"
        else:
            result.costs.append(FileCost(b.path, b.tier, chars, tokens, running, False,
                                         reason="exceeds remaining budget"))
            status = "EXCLUDED"

        log(f"{b.path:<58} {b.tier:<8} {chars:>9,} {tokens:>8,} {running:>10,}  {status}")

        if not fits and on_overflow == "stop":
            result.stopped_early = True
            rest = items[i + 1:]
            for b2 in rest:
                result.costs.append(FileCost(
                    b2.path, b2.tier, len(b2.text or ""), estimate_tokens(b2.text),
                    running, False, reason="budget exhausted before reached"))
            if rest:
                log(f"-- stopped: {len(rest)} further file(s) not reached")
            break

    result.total_tokens = running

    log("")
    log(f"included: {len(result.included)} file(s), {running:,} tokens "
        f"({running / budget_tokens:.1%} of budget)")
    log(f"excluded: {len(result.excluded)} file(s)")
    for c in result.excluded:
        log(f"  {c.path}  ({c.tokens:,} tokens — {c.reason})")

    return result


# --- Stage 5: reduction evidence ---------------------------------------

def reduction_report(raw_diff: str, packed: str, log=print) -> dict:
    """Quantify what the annotation pass saved. Same estimator, both sides."""
    raw_t = estimate_tokens(raw_diff)
    out_t = estimate_tokens(packed)
    saved = raw_t - out_t
    pct = (saved / raw_t) if raw_t else 0.0

    log(f"raw diff:   {len(raw_diff):>10,} chars  {raw_t:>9,} tokens")
    log(f"packed:     {len(packed):>10,} chars  {out_t:>9,} tokens")
    log(f"reduction:  {saved:>9,} tokens ({pct:.1%})")

    return {"raw_tokens": raw_t, "packed_tokens": out_t,
            "saved_tokens": saved, "reduction_pct": pct}


# --- run ---------------------------------------------------------------

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print("usage: python pack.py <diff-file>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        raw = f.read()

    blocks = file_blocks(annotate(raw))
    result = pack(blocks)

    print()
    reduction_report(raw, result.payload())


if __name__ == "__main__":
    main()
