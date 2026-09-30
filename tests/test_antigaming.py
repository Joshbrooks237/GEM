from env.limits import Limits
from env.runner import LocalSandbox
from selection.antigaming import audit, find_marker
from tasks.task import Case, Task


def _box_factory(home):
    def factory():
        return LocalSandbox(Limits(), home)

    return factory


def test_marker_detects_evaluator_paths_and_ignores_ordinary_programs():
    assert find_marker("python sol.py", ["print(1)\n"]) is None
    assert find_marker("python sol.py", ["open('tasks/hidden/sum_ints.json')\n"]) == "tasks/hidden"
    assert find_marker("cat ../ledger.sqlite", []) == "path_escape"


def test_isolated_rerun_does_not_use_the_construction_directory(tmp_path):
    (tmp_path / "sol.py").write_text(
        "import pathlib, sys\n"
        "sibling = pathlib.Path('secret.txt')\n"
        "print('yes' if sibling.exists() else 'no')\n",
        encoding="utf-8",
    )
    (tmp_path / "ENTRY").write_text("python sol.py\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("leak\n", encoding="utf-8")

    class Repo:
        path = tmp_path

        def tracked(self):
            return ["sol.py", "ENTRY", "secret.txt"]

    task = Task("t", "public", (Case("", "yes\n"),))
    # The construction directory contains secret.txt, so a check there would pass.
    # The isolated copy includes tracked files, so this fixture still copies secret.txt.
    # Drop it from the tracked set to show the isolated tree is only what we copy.
    Repo.tracked = lambda self: ["sol.py", "ENTRY"]
    hit = audit(Repo(), task, Limits(), _box_factory(tmp_path / "home"), construction_passed=True)
    assert hit is not None
    assert hit["trigger"] == "isolated_rerun_failed"
    assert (tmp_path / "secret.txt").exists()


def test_clean_program_is_not_flagged(tmp_path):
    (tmp_path / "sol.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "ENTRY").write_text("python sol.py\n", encoding="utf-8")

    class Repo:
        path = tmp_path

        def tracked(self):
            return ["sol.py", "ENTRY"]

    task = Task("t", "public", (Case("", "ok\n"),))
    assert audit(Repo(), task, Limits(), _box_factory(tmp_path / "home"), True) is None
