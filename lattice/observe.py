"""Separate what was available from what the agent did.

The harness running ENTRY is not reuse. Writing a command into ENTRY is not
an invocation. These records are evidence. They are not an interpretation
of why the agent did it.
"""

import hashlib
import os
import shlex
from pathlib import Path

from lattice.artifacts import IMPORT_RE, evaluator_targets
from lattice.git import Repo

INSPECT_CMDS = {"ls", "find", "cat", "head", "tail", "sed", "less", "more", "nl", "od", "wc", "stat"}
GIT_INSPECT = {"show", "log", "diff", "status", "ls-files", "grep"}
EXEC_CMDS = {"python", "python3", "bash", "sh"}


def snapshot_tree(root: Path) -> dict[str, tuple[int, int, str]]:
    found: dict[str, tuple[int, int, str]] = {}
    if not root.exists():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for name in filenames:
            full = Path(dirpath) / name
            if not full.is_file():
                continue
            rel = full.relative_to(root).as_posix()
            st = full.stat()
            digest = hashlib.sha256(full.read_bytes()).hexdigest()
            found[rel] = (st.st_mtime_ns, st.st_size, digest)
    return found


def touched_paths(before: dict[str, tuple[int, int, str]], after: dict[str, tuple[int, int, str]]) -> set[str]:
    paths = set(before) | set(after)
    touched: set[str] = set()
    for path in paths:
        if before.get(path) != after.get(path):
            touched.add(path)
    return touched


def _segments(command: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if command.startswith("&&", i) or ch in {";", "|"}:
            parts.append("".join(buf).strip())
            buf = []
            i += 2 if command.startswith("&&", i) else 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


def _normalize(path: str) -> str:
    path = path.strip().strip("'\"")
    if path.startswith("./"):
        path = path[2:]
    return path


def classify_command(command: str) -> list[tuple[str, str, str]]:
    """Return (role, path, evidence) for one agent command.

    Roles are inspection, invocation, or modification. Quoted text that is
    only being written to a file is not an invocation.
    """
    found: list[tuple[str, str, str]] = []
    evidence = command.strip()[:240]
    for segment in _segments(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        if not tokens:
            continue
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in {">", ">>"} and i + 1 < len(tokens):
                found.append(("modification", _normalize(tokens[i + 1]), evidence))
                i += 2
                continue
            if token == "tee" and i + 1 < len(tokens):
                found.append(("modification", _normalize(tokens[i + 1]), evidence))
                i += 2
                continue
            i += 1
        cmd = tokens[0]
        if cmd in INSPECT_CMDS:
            paths = [_normalize(tok) for tok in tokens[1:] if not tok.startswith("-")]
            if not paths:
                found.append(("inspection", "", evidence))
            for path in paths:
                found.append(("inspection", path, evidence))
        elif cmd == "git" and len(tokens) > 1 and tokens[1] in GIT_INSPECT:
            paths = [_normalize(tok) for tok in tokens[2:] if not tok.startswith("-")]
            if not paths:
                found.append(("inspection", "", evidence))
            for path in paths:
                found.append(("inspection", path, evidence))
        elif cmd in EXEC_CMDS and len(tokens) > 1 and not tokens[1].startswith("-"):
            found.append(("invocation", _normalize(tokens[1]), evidence))
    return found


def removal_set(parent_entry: str, touched: set[str]) -> set[str]:
    """Pre-existing executable files this episode did not itself rewrite.

    The counterfactual deletes these and re-runs the tests. A rewritten file,
    including one rewritten with the same bytes, stays.
    """
    targets = evaluator_targets(parent_entry)
    remove = {path for path in targets if path not in touched}
    if "ENTRY" not in touched and not any(path in touched for path in targets):
        if parent_entry.strip():
            remove.add("ENTRY")
    return remove


def diff_records(repo: Repo, parent: str, touched: set[str]) -> tuple[int, int, list[dict]]:
    """Changed files against the parent commit, plus same-byte rewrites."""
    completed = repo._git("diff", "--numstat", parent, "HEAD", check=False)
    added = deleted = 0
    files: list[dict] = []
    seen: set[str] = set()
    parent_blobs = {
        path: repo._git("rev-parse", f"{parent}:{path}", check=False).stdout.strip()
        for path in repo.tracked_at(parent)
    }
    parent_blob_set = {blob for blob in parent_blobs.values() if blob}
    if completed.returncode == 0:
        for line in completed.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            plus, minus, path = parts
            if plus != "-":
                added += int(plus)
            if minus != "-":
                deleted += int(minus)
            blob = repo.blob_sha(path) or ""
            prior = parent_blobs.get(path, "")
            files.append(
                {
                    "path": path,
                    "change": "modified" if prior else "added",
                    "blob_sha": blob,
                    "prior_blob": prior,
                    "blob_reused": bool(blob and blob in parent_blob_set),
                    "modified": path in touched or bool(prior),
                }
            )
            seen.add(path)
    for path in sorted(touched - seen):
        blob = repo.blob_sha(path) or ""
        prior = parent_blobs.get(path, "")
        files.append(
            {
                "path": path,
                "change": "equivalent_rewrite" if prior else "added",
                "blob_sha": blob,
                "prior_blob": prior,
                "blob_reused": bool(blob and blob in parent_blob_set),
                "modified": True,
            }
        )
    return added, deleted, files


def import_dependencies(repo: Repo, parent: str, paths: list[str]) -> list[tuple[str, str]]:
    """Imports in files this episode wrote, including a same-byte rewrite.

    A git diff misses a rewrite that leaves the blob unchanged. The file the
    episode touched still shows whether it imports something older.
    """
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    interesting = list(dict.fromkeys([*repo.changed(parent, repo.head()), *paths]))
    for path in interesting:
        text = ""
        full = repo.path / path
        if full.is_file():
            text = full.read_text(encoding="utf-8", errors="replace")
        else:
            text = repo.file_at(repo.head(), path) or ""
        for line in text.splitlines():
            match = IMPORT_RE.match(line)
            if not match:
                continue
            module = match.group(1).replace(".", "/") + ".py"
            if module in seen or module == "ENTRY":
                continue
            if not repo.exists_at(parent, module):
                continue
            seen.add(module)
            found.append((module, line.strip()))
    return found
