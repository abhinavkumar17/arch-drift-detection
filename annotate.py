"""
annotate.py — the annotation pass for the architecture-drift reviewer.

What it does (this and nothing more):
    diff text  ->  a flat list of CHANGED lines, each with an address.

Each changed line becomes one AnnotatedLine:
    - path      : which file            (e.g. "MyRogers/ProfileViewController.swift")
    - line      : line number GitHub can anchor a comment to
    - change    : "added" or "deleted"
    - code      : the line's actual text

Unchanged "context" lines are dropped. That's the noise you don't pay tokens for.

Run it:
    python annotate.py sample.diff
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import unidiff


# Only these file types can violate an architecture rule, so only these are
# worth spending model tokens on. Everything else (docs, generated JSON/HTML,
# assets) is dropped before it ever reaches the model.
SOURCE_EXTENSIONS = (".swift", ".kt", ".kts")

# Architecture/layering rules apply to PRODUCTION code, not tests. A test that
# reaches across layers isn't a drift violation, so test files are dropped too.
# Matched against a lowercased path, so "Tests/" and "src/test/" both catch.
TEST_PATH_MARKERS = ("test/", "tests/", "/test", "spec/", "specs/")


@dataclass
class AnnotatedLine:
    path: str
    line: int
    change: str   # "added" or "deleted"
    code: str


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in TEST_PATH_MARKERS)


def _is_source_file(path: str) -> bool:
    if not path.endswith(SOURCE_EXTENSIONS):
        return False
    if _is_test_file(path):               # production only
        return False
    return True


def annotate(diff_text: str) -> list[AnnotatedLine]:
    """Turn raw unified-diff text into a list of addressed changed lines.

    Non-source files (docs, generated output, assets) are skipped entirely.
    """
    if not diff_text.strip():
        return []

    patch = unidiff.PatchSet(diff_text)
    out: list[AnnotatedLine] = []

    for patched_file in patch:
        path = patched_file.path              # the "new file" path

        if not _is_source_file(path):         # <-- the filter
            continue
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    # added lines live in the NEW file -> target line number
                    out.append(AnnotatedLine(path, line.target_line_no, "added", line.value.rstrip("\n")))
                elif line.is_removed:
                    # deleted lines live in the OLD file -> source line number
                    out.append(AnnotatedLine(path, line.source_line_no, "deleted", line.value.rstrip("\n")))
                # context lines (unchanged) are skipped on purpose

    return out


def line_range_map(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    """Build the map of which line ranges each file actually changed.

    Returns e.g. {"MyRogers/ProfileViewController.swift": [(40, 55), (120, 138)]}

    Same source data as annotate(), read a different way. Use this to VALIDATE
    the model's output: if the model reports a finding at a line that falls in
    none of a file's ranges, it hallucinated -> drop it before it becomes a
    PR comment.

    Ranges use NEW-file line numbers (hunk.target_start / target_length),
    because that's what GitHub anchors a review comment against.
    """
    if not diff_text.strip():
        return {}

    patch = unidiff.PatchSet(diff_text)
    ranges: dict[str, list[tuple[int, int]]] = {}

    for patched_file in patch:
        path = patched_file.path

        if not _is_source_file(path):         # same filter as annotate()
            continue

        for hunk in patched_file:
            start = hunk.target_start
            end = hunk.target_start + hunk.target_length - 1
            ranges.setdefault(path, []).append((start, end))

    return ranges


def is_in_diff(path: str, line: int, ranges: dict[str, list[tuple[int, int]]]) -> bool:
    """Did the diff actually touch this file at this line?

    This is the guard. Call it on every finding the model returns. False means
    the model pointed at a line the PR never changed -> drop the finding.
    """
    for start, end in ranges.get(path, []):
        if start <= line <= end:
            return True
    return False


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python annotate.py <diff-file>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        diff_text = f.read()

    lines = annotate(diff_text)

    for a in lines:
        sign = "+" if a.change == "added" else "-"
        print(f"{a.path}:{a.line:<4} {sign} {a.code}")

    print(f"\n{len(lines)} changed lines across "
          f"{len({a.path for a in lines})} file(s)")

    # the validation map: which line ranges each file actually changed
    ranges = line_range_map(diff_text)
    print("\n--- line-range map (the guard against hallucinated findings) ---")
    for path, spans in ranges.items():
        pretty = ", ".join(f"{s}-{e}" for s, e in spans)
        print(f"{path}: {pretty}")


if __name__ == "__main__":
    main()
