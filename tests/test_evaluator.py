from env.limits import Limits
from env.runner import LocalSandbox
from selection.evaluator import evaluate
from tasks.task import Case, Task


def _sandbox(tmp_path):
    box = LocalSandbox(Limits(), tmp_path / "home")
    box.start(tmp_path, "t", "1577836800 +0000")
    return box


def test_hidden_cases_must_all_pass(tmp_path):
    (tmp_path / "sol.py").write_text("import sys\nprint(sys.stdin.read().strip()[::-1])\n", encoding="utf-8")
    (tmp_path / "ENTRY").write_text("python sol.py\n", encoding="utf-8")
    task = Task("rev", "public", (Case("ab\n", "ba\n"), Case("zz\n", "zz\n")))
    result = evaluate(_sandbox(tmp_path), task, Limits())
    assert result.passed == 2
    assert result.correctness == 1.0


def test_partial_pass_is_still_a_failed_gate(tmp_path):
    (tmp_path / "sol.py").write_text("print('ba')\n", encoding="utf-8")
    (tmp_path / "ENTRY").write_text("python sol.py\n", encoding="utf-8")
    task = Task("rev", "public", (Case("ab\n", "ba\n"), Case("zz\n", "zz\n")))
    result = evaluate(_sandbox(tmp_path), task, Limits())
    assert result.passed == 1
    assert result.correctness == 0.0


def test_missing_entry_fails(tmp_path):
    task = Task("rev", "public", (Case("ab\n", "ba\n"),))
    result = evaluate(_sandbox(tmp_path), task, Limits())
    assert result.correctness == 0.0
    assert result.detail == "ENTRY missing"
