"""Checks that run apart from the agent's construction sandbox.

A hit zeros that attempt's fitness contribution. It does not roll back any
other attempt, and it does not rewrite Git history.
"""

import shutil
import tempfile
from pathlib import Path

from selection.evaluator import evaluate

MARKERS = ("tasks/hidden", "tasks/heldout", "ledger.sqlite", "report.md")


def find_marker(entry: str, texts: list[str]) -> str | None:
    blob = "\n".join([entry, *texts])
    if "../" in entry or entry.strip().startswith("/"):
        return "path_escape"
    for marker in MARKERS:
        if marker in blob:
            return marker
    return None


def audit(repo, task, limits, sandbox_factory, construction_passed: bool) -> dict | None:
    """Return a trigger record, or None when the attempt is not gaming."""
    texts: list[str] = []
    for path in repo.tracked():
        full = repo.path / path
        if path == "ENTRY" or not full.is_file():
            continue
        texts.append(full.read_text(encoding="utf-8", errors="replace"))
    entry_path = repo.path / "ENTRY"
    entry = entry_path.read_text(encoding="utf-8", errors="replace") if entry_path.is_file() else ""
    marker = find_marker(entry, texts)
    if marker:
        trigger = "path_escape" if marker == "path_escape" else "evaluator_reference"
        return {
            "trigger": trigger,
            "reason": f"construction referenced {marker}",
        }
    if not construction_passed:
        return None
    dest = Path(tempfile.mkdtemp(prefix="peg-audit-"))
    try:
        for path in repo.tracked():
            src = repo.path / path
            if not src.is_file():
                continue
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        sandbox = sandbox_factory()
        sandbox.start(dest, "audit", "1577836800 +0000")
        try:
            result = evaluate(sandbox, task, limits)
        finally:
            sandbox.stop()
    finally:
        shutil.rmtree(dest, ignore_errors=True)
    if result.correctness < 1.0:
        return {
            "trigger": "isolated_rerun_failed",
            "reason": result.detail[:500],
        }
    return None
