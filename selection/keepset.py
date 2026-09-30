"""Experiment 3 candidate keep-set.

The temporary copy is a scratch directory. The specimen is not written.


This is not the Experiment 2 removal rule. The episode loop still uses
``removal_set`` until an Experiment 3 run is started. Nothing here writes
the specimen.

A pre-existing file enters the temporary candidate only along the program
the episode actually submitted. Touching some other file does not recruit
the previous ENTRY target. Routing ENTRY at an existing file can make that
file part of the candidate, and that routing is not reuse.
"""

from __future__ import annotations

import shlex
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from lattice.artifacts import EXEC_RE, IMPORT_RE, evaluator_targets
from lattice.observe import _segments, classify_command


@dataclass(frozen=True)
class CandidateClosure:
    keep: frozenset[str]
    reuse: tuple[tuple[str, str, str], ...]
    routed_existing: tuple[str, ...]
    stale_entry: bool


def closure_passes(closure: CandidateClosure, required: set[str]) -> bool:
    """Hidden tests pass on the temporary copy only if every file they need was kept."""
    return set(required) <= set(closure.keep)


def build_candidate(
    *,
    parent_entry: str,
    touched: set[str],
    sources: dict[str, str],
    existing: set[str],
    executed: set[str] | None = None,
    copied: set[str] | None = None,
    inspected: set[str] | None = None,
    evaluator_executed: set[str] | None = None,
    new_entry: str | None = None,
) -> CandidateClosure:
    """Build the temporary-copy file set from what the episode itself submitted.

    ``inspected`` and ``evaluator_executed`` are accepted so callers can pass
    the full observation record. Neither one adds a file or a reuse event.
    """
    del inspected, evaluator_executed
    executed = set(executed or ())
    copied = set(copied or ())
    entry_touched = "ENTRY" in touched or new_entry is not None
    entry_text = new_entry if new_entry is not None else sources.get("ENTRY", "")
    parent_targets = set(evaluator_targets(parent_entry))

    seeds: set[str] = set()
    stale = False
    if entry_touched:
        seeds.add("ENTRY")
        seeds.update(evaluator_targets(entry_text))
    else:
        evidenced = {
            path
            for path in parent_targets
            if path in touched or path in executed or path in copied
        }
        if parent_targets and not evidenced:
            stale = True
        elif evidenced:
            seeds.add("ENTRY")
            seeds.update(evidenced)

    keep = _expand(seeds, sources, existing, touched)
    reuse = _reuse(keep, touched, sources, existing, executed, copied)
    reused_paths = {path for _kind, path, _evidence in reuse}
    routed = tuple(
        path
        for path in evaluator_targets(entry_text)
        if entry_touched and path in existing and path not in touched and path not in reused_paths
    )
    return CandidateClosure(
        keep=frozenset(keep),
        reuse=reuse,
        routed_existing=routed,
        stale_entry=stale,
    )


def _expand(seeds: set[str], sources: dict[str, str], existing: set[str], touched: set[str]) -> set[str]:
    keep = set(seeds)
    stack = list(seeds)
    while stack:
        path = stack.pop()
        if path == "ENTRY":
            continue
        for ref in _references(sources.get(path, "")):
            if ref in keep:
                continue
            if ref in existing or ref in touched:
                keep.add(ref)
                stack.append(ref)
    return keep


def _references(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        match = IMPORT_RE.match(line)
        if match:
            found.append(match.group(1).replace(".", "/") + ".py")
    for path in EXEC_RE.findall(text):
        if path != "ENTRY" and path not in found:
            found.append(path[2:] if path.startswith("./") else path)
    return found


def _reuse(
    keep: set[str],
    touched: set[str],
    sources: dict[str, str],
    existing: set[str],
    executed: set[str],
    copied: set[str],
) -> tuple[tuple[str, str, str], ...]:
    events: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, path: str, evidence: str) -> None:
        if not path or path == "ENTRY" or path not in existing:
            return
        key = (kind, path)
        if key in seen:
            return
        seen.add(key)
        events.append((kind, path, evidence))

    for path in sorted(executed):
        add("executed", path, f"python3 {path}")
    for path in sorted(copied):
        add("copied", path, f"cp {path}")
    for path in sorted(keep & touched):
        for line in sources.get(path, "").splitlines():
            match = IMPORT_RE.match(line)
            if not match:
                continue
            module = match.group(1).replace(".", "/") + ".py"
            if module in existing and module not in touched:
                add("imported", module, line.strip())
    for path in sorted(keep & existing - touched):
        for module in _imports_only(sources.get(path, "")):
            if module in existing and module in keep:
                add("imported_via", module, f"via {path}")
    return tuple(events)


def candidate_attributable(
    repo, parent_sha, parent_entry, touched, commands, task, limits, sandbox_factory
):
    """Return whether the hidden tests pass on the evidenced keep-set, and that closure.

    The copy is a scratch directory. ``repo`` is only read.
    """
    from selection.evaluator import evaluate

    existing = set(repo.tracked_at(parent_sha))
    sources: dict[str, str] = {}
    for path in existing:
        text = repo.file_at(parent_sha, path)
        if text is not None:
            sources[path] = text
    for path in repo.tracked():
        full = repo.path / path
        if full.is_file():
            sources[path] = full.read_text(encoding="utf-8", errors="replace")
    executed, copied = _agent_edges(commands, existing)
    new_entry = sources.get("ENTRY") if "ENTRY" in touched else None
    closure = build_candidate(
        parent_entry=parent_entry,
        touched=set(touched),
        sources=sources,
        existing=existing,
        executed=executed,
        copied=copied,
        new_entry=new_entry,
    )
    if "ENTRY" not in closure.keep:
        return False, closure
    dest = Path(tempfile.mkdtemp(prefix="peg-keep-"))
    try:
        for path in closure.keep:
            src = repo.path / path
            if not src.is_file():
                continue
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        sandbox = sandbox_factory()
        sandbox.start(dest, "candidate", "1577836800 +0000")
        try:
            result = evaluate(sandbox, task, limits)
        finally:
            sandbox.stop()
    finally:
        shutil.rmtree(dest, ignore_errors=True)
    return result.correctness >= 1.0, closure


def _agent_edges(commands: list[str], existing: set[str]) -> tuple[set[str], set[str]]:
    executed: set[str] = set()
    copied: set[str] = set()
    for command in commands:
        for role, path, _evidence in classify_command(command):
            if role == "invocation" and path in existing:
                executed.add(path)
        for segment in _segments(command):
            try:
                tokens = shlex.split(segment)
            except ValueError:
                continue
            if len(tokens) < 3 or tokens[0] != "cp":
                continue
            args = [token for token in tokens[1:] if not token.startswith("-")]
            if len(args) >= 2 and args[-2] in existing:
                copied.add(args[-2])
    return executed, copied


def _imports_only(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        match = IMPORT_RE.match(line)
        if match:
            found.append(match.group(1).replace(".", "/") + ".py")
    return found
