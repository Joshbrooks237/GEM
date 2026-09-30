from agents.provider import HELPER, SOLUTIONS
from env.limits import Limits
from env.runner import LocalSandbox
from selection.evaluator import evaluate
from tasks.pool import load_pool


def test_scripted_solutions_pass_their_hidden_cases(tmp_path):
    training, heldout = load_pool()
    for task in (*training, *heldout):
        root = tmp_path / task.id
        root.mkdir()
        (root / "helper.py").write_text(HELPER, encoding="utf-8")
        (root / f"{task.id}.py").write_text(SOLUTIONS[task.id], encoding="utf-8")
        (root / "ENTRY").write_text(f"python {task.id}.py\n", encoding="utf-8")
        box = LocalSandbox(Limits(), root / "home")
        box.start(root, "t", "1577836800 +0000")
        result = evaluate(box, task, Limits())
        assert result.correctness == 1.0, result.detail
