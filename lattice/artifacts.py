"""What an episode changed, and which older files it depended on."""

import re

from lattice.git import Repo

IMPORT_RE = re.compile(r"(?m)^\s*(?:from|import)\s+([A-Za-z_][\w.]*)")
PATH_RE = re.compile(r"(?<![\w/])([\w./-]+\.(?:py|sh|txt|md|json))")
EXEC_RE = re.compile(r"(?:python3?|bash|sh)\s+([^\s;&|]+)")


def dependencies(repo: Repo, parent_sha: str, commands: list[str]) -> list[tuple[str, str, str]]:
    """Imports of files that already existed. Agent commands are classified elsewhere.

    The harness ENTRY line is not an import and is not reuse.
    """
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    head = repo.head()

    def add(path: str, kind: str, evidence: str) -> None:
        if not path or path == "ENTRY" or path in seen:
            return
        if not repo.exists_at(parent_sha, path):
            return
        seen.add(path)
        found.append((path, kind, evidence.strip()))

    for path in repo.changed(parent_sha, head):
        text = repo.file_at(head, path) or ""
        for line in text.splitlines():
            match = IMPORT_RE.match(line)
            if not match:
                continue
            module = match.group(1)
            add(module.replace(".", "/") + ".py", "import", line.strip())

    del commands
    return found


def evaluator_targets(entry: str) -> list[str]:
    """Files the harness would run from ENTRY. This is not agent reuse."""
    found: list[str] = []
    for line in entry.splitlines():
        line = line.strip()
        if not line:
            continue
        for match in EXEC_RE.findall(line):
            if match not in found and match != "ENTRY":
                found.append(match)
        if not EXEC_RE.search(line):
            for match in PATH_RE.findall(line):
                if match not in found:
                    found.append(match)
        break
    return found
