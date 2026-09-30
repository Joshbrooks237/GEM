"""Would this candidate still pass without an inherited executable?

The check runs in a copy. The specimen is not rewritten here.
"""

import shutil
import tempfile
from pathlib import Path

from lattice.observe import removal_set
from selection.evaluator import evaluate


def counterfactual_passes(repo, parent_entry: str, touched: set[str], task, limits, sandbox_factory) -> bool:
    """True when the episode's own files still pass after inherited executables are removed."""
    remove = removal_set(parent_entry, touched)
    if not remove:
        return True
    dest = Path(tempfile.mkdtemp(prefix="peg-candidate-"))
    try:
        for path in repo.tracked():
            src = repo.path / path
            if not src.is_file():
                continue
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        for path in remove:
            victim = dest / path
            if victim.is_file():
                victim.unlink()
        sandbox = sandbox_factory()
        sandbox.start(dest, "candidate", "1577836800 +0000")
        try:
            result = evaluate(sandbox, task, limits)
        finally:
            sandbox.stop()
    finally:
        shutil.rmtree(dest, ignore_errors=True)
    return result.correctness >= 1.0
