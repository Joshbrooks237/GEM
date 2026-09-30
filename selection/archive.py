"""Copy surviving contribution files out of the specimen."""

import json
from pathlib import Path

from lattice.git import Repo


def archive_paths(
    repo: Repo,
    archive_root: Path,
    run_id: str,
    commit_sha: str,
    paths: list[str],
    texts: list[str],
) -> list[str]:
    archive_root.mkdir(parents=True, exist_ok=True)
    manifest = archive_root / "manifest.jsonl"
    saved: list[str] = []
    with manifest.open("a", encoding="utf-8") as handle:
        for path in paths:
            full = repo.path / path
            if not full.is_file():
                continue
            data = full.read_bytes()
            dest = archive_root / commit_sha / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if b"\0" not in data:
                texts.append(data.decode("utf-8", "replace"))
            saved.append(path)
            handle.write(
                json.dumps({"run_id": run_id, "commit": commit_sha, "path": path}) + "\n"
            )
    return saved


def load_archive_texts(archive_root: Path) -> list[str]:
    if not archive_root.exists():
        return []
    texts: list[str] = []
    for path in sorted(archive_root.rglob("*")):
        if not path.is_file() or path.name == "manifest.jsonl":
            continue
        data = path.read_bytes()
        if b"\0" in data or len(data) > 65_536:
            continue
        texts.append(data.decode("utf-8", "replace"))
    return texts
