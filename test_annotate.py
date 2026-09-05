"""
test_annotate.py — proofs for the annotation pass.

No AWS, no GitHub, no model. These are pure functions over a diff string.
Fixtures are real `git diff` output, because unidiff rejects hand-written
hunk headers whose line counts don't add up.

    pip install pytest unidiff
    pytest test_annotate.py -v
"""

from annotate import annotate, allow_list, is_in_diff, file_tier


# Old file is 10 lines, new file is 3. Deleted lines sit at OLD line numbers
# 3..10, which run past the end of the NEW file entirely. Any guard that
# checks an old-file number against a new-file range gets this wrong.
SHRINK_DIFF = """diff --git a/a.swift b/a.swift
index e63706e..07652d0 100644
--- a/a.swift
+++ b/a.swift
@@ -1,10 +1,3 @@
 alpha
 bravo
-charlie
-delta
-echo
-foxtrot
-golf
-hotel
-india
-juliet
+ZULU
"""

# Two hunks in one file. Counters must not carry over from the first.
TWO_HUNK_DIFF = """diff --git a/a.swift b/a.swift
index e63706e..c7e6cf0 100644
--- a/a.swift
+++ b/a.swift
@@ -2,3 +2,3 @@ alpha
 bravo
-charlie
+CHANGED1
 delta
@@ -7,3 +7,3 @@ foxtrot
 golf
-hotel
+CHANGED2
 india
"""


def test_deleted_lines_validate_against_their_own_numbering():
    """The regression. Every deleted line annotate() emits must pass the guard.

    Fails on the range-based version: deleted lines carry old-file numbers up
    to 10, while the hunk's new-file range stops at 3.
    """
    lines = annotate(SHRINK_DIFF)
    allowed = allow_list(lines)

    deleted = [a for a in lines if a.change == "deleted"]
    assert deleted, "fixture should contain deletions"

    for a in deleted:
        assert is_in_diff(a.path, a.line, a.side, allowed), (
            f"annotate() emitted {a.path}:{a.line} on {a.side} "
            f"but the guard rejects it"
        )

    # and specifically: old-file lines beyond the new file's length survive
    assert 10 in allowed["a.swift"]["LEFT"]


def test_context_lines_are_not_commentable():
    """Unchanged lines reach the model but never the allow-list."""
    lines = annotate(SHRINK_DIFF)
    allowed = allow_list(lines)

    context = [a for a in lines if a.change == "context"]
    assert context, "context lines should be kept, not dropped"

    for a in context:
        assert a.side is None
        assert not a.commentable
        assert not is_in_diff(a.path, a.line, "RIGHT", allowed)
        assert not is_in_diff(a.path, a.line, "LEFT", allowed)


def test_side_matches_change_type():
    """Deleted -> LEFT -> old numbering. Added -> RIGHT -> new numbering."""
    lines = annotate(SHRINK_DIFF)
    allowed = allow_list(lines)

    assert all(a.side == "LEFT" for a in lines if a.change == "deleted")
    assert all(a.side == "RIGHT" for a in lines if a.change == "added")

    # ZULU is the only addition and it is new-file line 3
    added = [a for a in lines if a.change == "added"]
    assert [a.line for a in added] == [3]
    assert allowed["a.swift"]["RIGHT"] == {3}

    # the same number on the other side is a different place
    assert not is_in_diff("a.swift", 3, "LEFT", allowed) or 3 in allowed["a.swift"]["LEFT"]


def test_counters_reset_across_hunks():
    """Second hunk's numbers come from its own @@ header, not a running total."""
    lines = annotate(TWO_HUNK_DIFF)
    allowed = allow_list(lines)

    assert allowed["a.swift"]["RIGHT"] == {3, 8}
    assert allowed["a.swift"]["LEFT"] == {3, 8}

    added = {a.code.strip(): a.line for a in lines if a.change == "added"}
    assert added == {"CHANGED1": 3, "CHANGED2": 8}


def test_file_tiers():
    """Production source is commentable, tests and docs are read-only, noise is dropped."""
    assert file_tier("MyRogers/ProfileViewController.swift") == "comment"
    assert file_tier("app/src/main/java/Repo.kt") == "comment"

    assert file_tier("MyRogersTests/ProfileTests.swift") == "context"
    assert file_tier("README.md") == "context"

    assert file_tier("Podfile.lock") == "drop"
    assert file_tier("Pods/Alamofire/Source/Session.swift") == "drop"
    assert file_tier("assets/logo.png") == "drop"


def test_findings_outside_the_diff_are_rejected():
    """The guard's actual job: drop a finding pointing at an untouched line."""
    allowed = allow_list(annotate(SHRINK_DIFF))

    assert not is_in_diff("a.swift", 999, "RIGHT", allowed)
    assert not is_in_diff("b.swift", 3, "RIGHT", allowed)


def test_empty_diff():
    assert annotate("") == []
    assert allow_list([]) == {}
