"""
annotate.py — the annotation pass for the architecture-drift reviewer.

    diff text  ->  addressed lines  ->  text the model can safely cite

Every line the model sees carries an address: which file, which line number,
and which side of the diff that number belongs to. Two numbering systems run
at once in a diff (the file before the change and the file after), so the side
is not optional — a bare line number is ambiguous.

    NEW:L#   added line     -> new-file numbering   -> GitHub side RIGHT
    OLD:L#   deleted line   -> old-file numbering   -> GitHub side LEFT
    CTX:L#   unchanged line -> context only         -> NOT commentable

The allow-list is built from the same pass, split by side. A finding is only
posted if its (path, line, side) appears in it.

Run it:
    python annotate.py sample.diff
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import unidiff


# Files whose changes can violate an architecture rule. The model may comment
# on these.
COMMENTABLE_EXTENSIONS = (".swift", ".kt", ".kts")

# Files the model may READ for context but never comment on. Tests earn their
# place here: a test reaching into an internal it shouldn't know about is one
# of the stronger drift signals available.
CONTEXT_EXTENSIONS = (".swift", ".kt", ".kts", ".md", ".yml", ".yaml", ".json")

# Never worth a token, in either tier.
NOISE_MARKERS = (
    "package-lock.json", "podfile.lock", "gemfile.lock", "yarn.lock",
    "/pods/", "/vendor/", "/build/", "/generated/", ".min.js", ".min.css",
    ".pbxproj", ".xcworkspacedata",
    "/docs/", "undocumented.json",
)

TEST_PATH_MARKERS = ("test/", "tests/", "/test", "spec/", "specs/")


@dataclass
class AnnotatedLine:
    path: str
    line: int
    change: str            # "added" | "deleted" | "context"
    side: str | None       # "RIGHT" | "LEFT" | None for context
    code: str
    commentable: bool      # False for context lines and context-tier files


def _is_noise(path: str) -> bool:
    # leading slash so "/pods/" matches both "Pods/x.swift" and "ios/Pods/x.swift"
    lowered = "/" + path.lower()
    return any(marker in lowered for marker in NOISE_MARKERS)


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in TEST_PATH_MARKERS)


def file_tier(path: str) -> str:
    """One of "comment", "context", "drop"."""
    if _is_noise(path):
        return "drop"
    if not path.endswith(CONTEXT_EXTENSIONS):
        return "drop"
    if path.endswith(COMMENTABLE_EXTENSIONS) and not _is_test_file(path):
        return "comment"
    return "context"


def annotate(diff_text: str) -> list[AnnotatedLine]:
    """Turn raw unified-diff text into addressed lines.

    Context lines are KEPT and tagged, so the model can read around a change.
    They are never commentable, so keeping them costs nothing in correctness.
    """
    if not diff_text.strip():
        return []

    patch = unidiff.PatchSet(diff_text)
    out: list[AnnotatedLine] = []

    for patched_file in patch:
        path = patched_file.path
        tier = file_tier(path)
        if tier == "drop":
            continue
        can_comment = tier == "comment"

        for hunk in patched_file:
            for line in hunk:
                code = line.value.rstrip("\n")
                if line.is_added:
                    # lives in the NEW file
                    out.append(AnnotatedLine(
                        path, line.target_line_no, "added", "RIGHT", code, can_comment))
                elif line.is_removed:
                    # lives in the OLD file
                    out.append(AnnotatedLine(
                        path, line.source_line_no, "deleted", "LEFT", code, can_comment))
                else:
                    # unchanged: readable, never commentable
                    out.append(AnnotatedLine(
                        path, line.target_line_no, "context", None, code, False))

    return out


def allow_list(lines: list[AnnotatedLine]) -> dict[str, dict[str, set[int]]]:
    """Exactly which (file, line, side) triples a comment may be posted on.

    Built from the annotated lines themselves, NOT from hunk headers — so the
    numbers here are guaranteed to be the same numbers annotate() handed the
    model. Split by side, because an old-file 40 and a new-file 40 are
    different places.

        {"MyRogers/Profile.swift": {"LEFT": {41, 42}, "RIGHT": {41, 44}}}
    """
    allowed: dict[str, dict[str, set[int]]] = {}
    for a in lines:
        if not a.commentable or a.side is None:
            continue
        allowed.setdefault(a.path, {"LEFT": set(), "RIGHT": set()})
        allowed[a.path][a.side].add(a.line)
    return allowed


def is_in_diff(path: str, line: int, side: str,
               allowed: dict[str, dict[str, set[int]]]) -> bool:
    """The guard. Call it on every finding the model returns.

    False means the model pointed somewhere the PR did not change, or somewhere
    it is not allowed to comment -> drop the finding before it becomes a PR
    comment.
    """
    return line in allowed.get(path, {}).get(side, set())


def render_for_model(lines: list[AnnotatedLine]) -> str:
    """The tagged text the model actually receives.

        MyRogers/Profile.swift
        [CTX:L10]   import Combine
        [NEW:L11] + import NetworkLayer
        [OLD:L11] - private var cancellables = Set<AnyCancellable>()
    """
    tag_for = {"added": "NEW", "deleted": "OLD", "context": "CTX"}
    sign_for = {"added": "+", "deleted": "-", "context": " "}

    chunks: list[str] = []
    current: str | None = None
    for a in lines:
        if a.path != current:
            current = a.path
            note = "" if file_tier(a.path) == "comment" else "   (context only, do not comment)"
            chunks.append(f"\n{a.path}{note}")
        tag = f"[{tag_for[a.change]}:L{a.line}]"
        chunks.append(f"{tag:<12} {sign_for[a.change]} {a.code}")
    return "\n".join(chunks).lstrip("\n")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print("usage: python annotate.py <diff-file>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        diff_text = f.read()

    lines = annotate(diff_text)
    allowed = allow_list(lines)

    print(render_for_model(lines))

    changed = [a for a in lines if a.change != "context"]
    print(f"\n{len(changed)} changed lines, {len(lines) - len(changed)} context lines, "
          f"across {len({a.path for a in lines})} file(s)")

    print("\n--- allow-list (the guard against misplaced comments) ---")
    for path, sides in allowed.items():
        left = ", ".join(str(n) for n in sorted(sides["LEFT"])) or "-"
        right = ", ".join(str(n) for n in sorted(sides["RIGHT"])) or "-"
        print(f"{path}\n    LEFT  (deleted): {left}\n    RIGHT (added):   {right}")


if __name__ == "__main__":
    main()
