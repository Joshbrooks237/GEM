from shocks.rename_tool import ArchiveCandidate, renamed, select_shock_target


def test_most_reused_archive_artifact_wins_ties_by_path_then_sha():
    candidates = [
        ArchiveCandidate("b.py", "bbb", 1, 3),
        ArchiveCandidate("a.py", "aaa", 1, 3),
        ArchiveCandidate("c.py", "ccc", 2, 1),
    ]
    chosen = select_shock_target(candidates, {"a.py", "b.py", "c.py"}, "fallback-artifact")
    assert chosen == {
        "applied": True,
        "reason": "most_reused",
        "path": "a.py",
        "origin_commit": "aaa",
    }


def test_missing_reuse_uses_the_fixed_fallback_only_when_present():
    candidates = [ArchiveCandidate("helper.py", "abc", 1, 0)]
    absent = select_shock_target(candidates, {"helper.py"}, "fallback-artifact")
    assert absent["applied"] is False
    assert absent["reason"] == "fallback_absent"
    assert absent["path"] == "fallback-artifact"
    present = select_shock_target(
        [ArchiveCandidate("fallback-artifact", "fff", 1, 0)],
        {"fallback-artifact"},
        "fallback-artifact",
    )
    assert present["reason"] == "fallback"
    assert present["origin_commit"] == "fff"


def test_renamed_is_stable():
    assert renamed("helper.py", 25, set()) == "helper.r25.py"
    assert renamed("helper.py", 25, {"helper.r25.py"}) == "helper.r25.2.py"


def test_entry_is_not_a_shock_target():
    chosen = select_shock_target(
        [ArchiveCandidate("ENTRY", "eee", 1, 9)],
        {"ENTRY"},
        "fallback-artifact",
    )
    assert chosen["applied"] is False
