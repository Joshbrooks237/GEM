from lattice.artifacts import evaluator_targets
from lattice.observe import classify_command, removal_set, touched_paths


def test_writing_entry_is_not_an_invocation():
    events = classify_command("echo 'python3 echo_reverse.py' > ENTRY")
    assert ("modification", "ENTRY", "echo 'python3 echo_reverse.py' > ENTRY") in events
    assert all(role != "invocation" for role, _path, _evidence in events)


def test_running_an_existing_file_is_an_invocation_and_cat_is_inspection():
    events = classify_command("cat echo_reverse.py && python3 echo_reverse.py")
    assert ("inspection", "echo_reverse.py", "cat echo_reverse.py && python3 echo_reverse.py") in events
    assert ("invocation", "echo_reverse.py", "cat echo_reverse.py && python3 echo_reverse.py") in events
    listed = classify_command("ls")
    assert ("inspection", "", "ls") in listed
    shown = classify_command("git show helper.py")
    assert ("inspection", "helper.py", "git show helper.py") in shown


def test_untouched_entry_is_removed_and_a_rewrite_is_kept():
    parent = "python3 echo_reverse.py\n"
    assert removal_set(parent, set()) == {"echo_reverse.py", "ENTRY"}
    assert removal_set(parent, {"echo_reverse.py"}) == set()
    assert removal_set(parent, {"ENTRY"}) == {"echo_reverse.py"}
    assert removal_set("", {"ENTRY", "echo_reverse.py"}) == set()


def test_same_bytes_count_as_a_touch_when_mtime_changes():
    before = {"echo_reverse.py": (1, 4, "abc")}
    after = {"echo_reverse.py": (2, 4, "abc"), "output.txt": (3, 3, "cba")}
    assert touched_paths(before, after) == {"echo_reverse.py", "output.txt"}


def test_evaluator_targets_are_the_checker_command_only():
    assert evaluator_targets("python3 echo_reverse.py\n") == ["echo_reverse.py"]
    assert evaluator_targets("") == []
