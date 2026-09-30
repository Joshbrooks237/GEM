"""Run hidden cases against the command in ENTRY.

Cases are not part of the agent prompt. A partial pass is still a failed gate.
"""

import ast
from dataclasses import dataclass

from env.limits import Limits
from lattice.git import Repo
from tasks.task import Task


@dataclass(frozen=True)
class EvalResult:
    passed: int
    total: int
    correctness: float
    detail: str


def evaluate(sandbox, task: Task, limits: Limits) -> EvalResult:
    listing = sandbox.run("test -f ENTRY && cat ENTRY", timeout=limits.test_timeout_s)
    if listing.exit_code != 0 or not listing.stdout.strip():
        return EvalResult(0, len(task.cases), 0.0, "ENTRY missing")
    command = listing.stdout.strip().splitlines()[0].strip()
    if not command:
        return EvalResult(0, len(task.cases), 0.0, "ENTRY empty")
    passed = 0
    failures: list[str] = []
    for index, case in enumerate(task.cases):
        result = sandbox.run(command, stdin=case.stdin, timeout=limits.test_timeout_s)
        actual = result.stdout.replace("\r\n", "\n")
        expect = case.stdout.replace("\r\n", "\n")
        if result.exit_code == 0 and actual == expect:
            passed += 1
        else:
            failures.append(
                f"case {index}: exit {result.exit_code} got {actual!r} want {expect!r}"
            )
    total = len(task.cases)
    correctness = 1.0 if total and passed == total else 0.0
    detail = "ok" if correctness == 1.0 else "; ".join(failures[:3])
    return EvalResult(passed, total, correctness, detail)


def quality_notes(repo: Repo, parent_sha: str, head_sha: str, eval_detail: str) -> dict:
    """Observations that are stored and deliberately left out of fitness."""
    changed = repo.changed(parent_sha, head_sha)
    syntax_errors = 0
    py_files = 0
    for path in changed:
        if not path.endswith(".py"):
            continue
        py_files += 1
        text = repo.file_at(head_sha, path)
        if text is None:
            continue
        try:
            ast.parse(text)
        except SyntaxError:
            syntax_errors += 1
    return {
        "eval": eval_detail[:500],
        "changed": changed,
        "py_files": py_files,
        "py_syntax_errors": syntax_errors,
    }
