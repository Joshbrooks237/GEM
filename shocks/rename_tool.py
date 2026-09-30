"""Rename one surviving artifact before a configured generation.

The new name is an environmental fact. Agents are not told it happened.
ENTRY is the evaluator's handle and is not a candidate. Git history is not
rewritten; the rename is a new commit.
"""

from dataclasses import dataclass
from pathlib import PurePosixPath

from lattice.git import Repo


@dataclass(frozen=True)
class ArchiveCandidate:
    path: str
    commit_sha: str
    generation: int
    reuse_count: int


def select_shock_target(
    candidates: list[ArchiveCandidate],
    existing: set[str],
    fallback: str,
) -> dict:
    """Pick the most-reused archived path, else a fixed fallback if it exists."""
    present = [
        item
        for item in candidates
        if item.path in existing and item.path != "ENTRY" and not item.path.startswith(".git")
    ]
    reused = [item for item in present if item.reuse_count > 0]
    if reused:
        reused.sort(key=lambda item: (-item.reuse_count, item.path, item.commit_sha))
        chosen = reused[0]
        return {
            "applied": True,
            "reason": "most_reused",
            "path": chosen.path,
            "origin_commit": chosen.commit_sha,
        }
    for item in present:
        if item.path == fallback:
            return {
                "applied": True,
                "reason": "fallback",
                "path": item.path,
                "origin_commit": item.commit_sha,
            }
    return {
        "applied": False,
        "reason": "fallback_absent",
        "path": fallback,
        "origin_commit": None,
    }


def renamed(path: str, generation: int, existing: set[str]) -> str:
    parsed = PurePosixPath(path)
    parent = "" if str(parsed.parent) in ("", ".") else f"{parsed.parent}/"
    candidate = f"{parent}{parsed.stem}.r{generation}{parsed.suffix}"
    extra = 2
    while candidate in existing:
        candidate = f"{parent}{parsed.stem}.r{generation}.{extra}{parsed.suffix}"
        extra += 1
    return candidate


def shock_identifier(seed: int, generation: int) -> str:
    return f"rename-{seed}-{generation}"


def load_candidates(ledger, run_id: str) -> list[ArchiveCandidate]:
    counts = {
        (row["producer_commit"], row["producer_path"]): int(row["n"])
        for row in ledger.rows(
            """
            SELECT producer_commit, producer_path, COUNT(*) AS n
            FROM reuse_events
            WHERE run_id = ?
            GROUP BY producer_commit, producer_path
            """,
            (run_id,),
        )
    }
    rows = ledger.rows(
        """
        SELECT a.path, a.commit_sha, a.generation
        FROM artifacts a
        JOIN episodes e ON e.id = a.episode_id
        WHERE a.run_id = ? AND a.archived = 1 AND a.pruned = 0
          AND e.phase = 'train' AND e.survived = 1 AND e.gamed = 0
        """,
        (run_id,),
    )
    return [
        ArchiveCandidate(
            path=row["path"],
            commit_sha=row["commit_sha"],
            generation=int(row["generation"]),
            reuse_count=counts.get((row["commit_sha"], row["path"]), 0),
        )
        for row in rows
    ]


class RenameToolShock:
    name = "rename_tool"

    def plan(self, repo: Repo, ledger, run_id: str, generation: int, seed: int, fallback: str) -> dict:
        existing = set(repo.tracked())
        decision = select_shock_target(load_candidates(ledger, run_id), existing, fallback)
        return {
            "shock_id": shock_identifier(seed, generation),
            "shock_type": self.name,
            "generation": generation,
            "old_path": decision["path"],
            "new_path": renamed(decision["path"], generation, existing),
            "origin_commit": decision["origin_commit"],
            "applied": bool(decision["applied"]),
            "reason": decision["reason"],
        }

    def execute(self, repo: Repo, plan: dict, date: str) -> str | None:
        if not plan["applied"]:
            return None
        repo.move(plan["old_path"], plan["new_path"])
        return repo.commit_workdir("shock", date, message="")


def make_shock(name: str) -> RenameToolShock:
    if name != "rename_tool":
        raise ValueError(f"unknown shock {name}")
    return RenameToolShock()
