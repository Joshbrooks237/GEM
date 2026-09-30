"""Regression tests for the Experiment 3 keep-set patch.

These do not touch a specimen and do not start a run.
"""

from selection.keepset import build_candidate, closure_passes

PARSE = "def parse(text):\n    return text\n"
HELPER = "def helper():\n    return 1\n"
FILTER = "from parse import parse\n"
PIPELINE = "from parse import parse\n"
PARSE_WITH_HELPER = "from helper import helper\n" + PARSE


def _passes(closure, required):
    return closure_passes(closure, required)


def test_stale_entry_cannot_produce_attribution():
    closure = build_candidate(
        parent_entry="python3 parse.py\n",
        touched=set(),
        sources={"ENTRY": "python3 parse.py\n", "parse.py": PARSE},
        existing={"ENTRY", "parse.py"},
    )
    assert closure.stale_entry is True
    assert "parse.py" not in closure.keep
    assert "ENTRY" not in closure.keep
    assert closure.reuse == ()
    assert _passes(closure, {"ENTRY", "parse.py"}) is False


def test_unrelated_touched_file_cannot_preserve_stale_entry():
    closure = build_candidate(
        parent_entry="python3 parse.py\n",
        touched={"unrelated.py"},
        sources={
            "ENTRY": "python3 parse.py\n",
            "parse.py": PARSE,
            "unrelated.py": "print('no')\n",
        },
        existing={"ENTRY", "parse.py"},
    )
    assert closure.stale_entry is True
    assert closure.keep == frozenset()
    assert _passes(closure, {"ENTRY", "parse.py"}) is False


def test_same_byte_rewrite_remains_attributable():
    closure = build_candidate(
        parent_entry="python3 parse.py\n",
        touched={"parse.py"},
        sources={"ENTRY": "python3 parse.py\n", "parse.py": PARSE},
        existing={"ENTRY", "parse.py"},
    )
    assert closure.stale_entry is False
    assert {"ENTRY", "parse.py"} <= set(closure.keep)
    assert _passes(closure, {"ENTRY", "parse.py"}) is True
    assert all(path != "parse.py" for _kind, path, _evidence in closure.reuse)


def test_new_program_retains_an_untouched_import():
    closure = build_candidate(
        parent_entry="python3 old.py\n",
        touched={"ENTRY", "raw_dev_count.py"},
        new_entry="python3 raw_dev_count.py\n",
        sources={"raw_dev_count.py": "from parse import parse\n"},
        existing={"parse.py", "old.py"},
    )
    assert {"ENTRY", "raw_dev_count.py", "parse.py"} <= set(closure.keep)
    assert "old.py" not in closure.keep
    assert ("imported", "parse.py", "from parse import parse") in closure.reuse
    assert _passes(closure, {"ENTRY", "raw_dev_count.py", "parse.py"}) is True


def test_transitive_import_is_retained():
    closure = build_candidate(
        parent_entry="python3 old.py\n",
        touched={"ENTRY", "pipeline.py"},
        new_entry="python3 pipeline.py\n",
        sources={
            "pipeline.py": PIPELINE,
            "parse.py": PARSE_WITH_HELPER,
            "helper.py": HELPER,
        },
        existing={"parse.py", "helper.py", "old.py"},
    )
    assert {"pipeline.py", "parse.py", "helper.py", "ENTRY"} <= set(closure.keep)
    assert ("imported", "parse.py", "from parse import parse") in closure.reuse
    assert ("imported_via", "helper.py", "via parse.py") in closure.reuse
    assert _passes(closure, {"ENTRY", "pipeline.py", "parse.py", "helper.py"}) is True


def test_execution_is_retained_only_when_the_candidate_needs_it():
    used = build_candidate(
        parent_entry="python3 parse.py\n",
        touched=set(),
        sources={"ENTRY": "python3 parse.py\n", "parse.py": PARSE},
        existing={"ENTRY", "parse.py"},
        executed={"parse.py"},
    )
    assert "parse.py" in used.keep
    assert ("executed", "parse.py", "python3 parse.py") in used.reuse
    assert _passes(used, {"ENTRY", "parse.py"}) is True

    unused = build_candidate(
        parent_entry="python3 parse.py\n",
        touched={"ENTRY", "filter.py"},
        new_entry="python3 filter.py\n",
        sources={"filter.py": FILTER},
        existing={"parse.py", "other.py"},
        executed={"other.py"},
    )
    assert "other.py" not in unused.keep
    assert ("executed", "other.py", "python3 other.py") in unused.reuse
    assert ("imported", "parse.py", "from parse import parse") in unused.reuse


def test_availability_and_inspection_do_not_create_attribution():
    closure = build_candidate(
        parent_entry="python3 old.py\n",
        touched={"ENTRY", "filter.py"},
        new_entry="python3 filter.py\n",
        sources={"filter.py": "print('dev')\n", "parse.py": PARSE},
        existing={"parse.py", "old.py"},
        inspected={"parse.py"},
    )
    assert "parse.py" not in closure.keep
    assert closure.reuse == ()
    assert _passes(closure, {"ENTRY", "filter.py"}) is True
    assert _passes(closure, {"ENTRY", "filter.py", "parse.py"}) is False


def test_evaluator_execution_cannot_create_reuse():
    closure = build_candidate(
        parent_entry="python3 parse.py\n",
        touched={"unrelated.py"},
        sources={"ENTRY": "python3 parse.py\n", "parse.py": PARSE},
        existing={"ENTRY", "parse.py"},
        evaluator_executed={"parse.py"},
    )
    assert closure.reuse == ()
    assert "parse.py" not in closure.keep
    assert closure.stale_entry is True


def test_routing_an_existing_file_is_not_reuse():
    closure = build_candidate(
        parent_entry="python3 old.py\n",
        touched={"ENTRY"},
        new_entry="python3 parse.py\n",
        sources={"parse.py": PARSE},
        existing={"parse.py", "old.py"},
    )
    assert {"ENTRY", "parse.py"} <= set(closure.keep)
    assert "old.py" not in closure.keep
    assert closure.reuse == ()
    assert closure.routed_existing == ("parse.py",)
    assert _passes(closure, {"ENTRY", "parse.py"}) is True


def test_failed_closure_rejects_a_hidden_stale_dependency():
    closure = build_candidate(
        parent_entry="python3 parse.py\n",
        touched={"unrelated.py"},
        sources={
            "ENTRY": "python3 parse.py\n",
            "parse.py": PARSE,
            "unrelated.py": "from parse import parse\n",
        },
        existing={"ENTRY", "parse.py"},
    )
    assert "parse.py" not in closure.keep
    assert closure.reuse == ()
    assert _passes(closure, {"ENTRY", "parse.py"}) is False
