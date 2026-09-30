"""Recompute reuse credit and walk recorded ancestry."""

from selection.fitness import FitnessConfig, combine, explainability_value, reuse_score


def refresh_reuse_fitness(ledger, run_id: str, cfg: FitnessConfig) -> None:
    """Update reuse and fitness. Leave attempts unscored until resource_score exists.

    fitness_at_birth is sealed separately and is not moved by later reuse.
    A gamed attempt stays at fitness 0; its other component columns are kept.
    """
    episodes = ledger.rows(
        """
        SELECT id, correctness, resource_score, explainability_score,
               explainability_sampled, gamed, attributable
        FROM episodes
        WHERE run_id = ?
        """,
        (run_id,),
    )
    counts = {
        row["producer_episode"]: row["n"]
        for row in ledger.rows(
            """
            SELECT producer_episode, COUNT(DISTINCT consumer_episode) AS n
            FROM reuse_events
            WHERE run_id = ?
            GROUP BY producer_episode
            """,
            (run_id,),
        )
    }
    for episode in episodes:
        reuse = reuse_score(int(counts.get(episode["id"], 0)))
        if episode["resource_score"] is None:
            ledger.set_reuse_only(episode["id"], reuse)
            continue
        explainability = explainability_value(
            bool(episode["explainability_sampled"]),
            episode["explainability_score"],
            cfg,
        )
        correctness = episode["correctness"] if episode["attributable"] else 0.0
        fitness = combine(
            correctness,
            episode["resource_score"],
            reuse,
            explainability,
            cfg,
            gamed=bool(episode["gamed"]),
        )
        ledger.set_fitness(episode["id"], reuse, fitness)
    ledger.commit()


def source_episode(ledger, repo, run_id: str, parent_sha: str, path: str, dst_episode: int) -> dict | None:
    """Credit the survived training episode that last produced `path`."""
    if not repo.exists_at(parent_sha, path):
        return None
    for sha in repo.file_history(parent_sha, path):
        found = ledger.rows(
            """
            SELECT c.episode_id, c.commit_sha, e.survived, e.phase
            FROM commits c
            LEFT JOIN episodes e ON e.id = c.episode_id
            WHERE c.run_id = ? AND c.commit_sha = ?
            """,
            (run_id, sha),
        )
        if not found:
            continue
        row = found[0]
        episode_id = row["episode_id"]
        if not episode_id or episode_id == dst_episode:
            continue
        if row["phase"] != "train" or not row["survived"]:
            continue
        return row
    return None


def ancestry(ledger, run_id: str, commit_sha: str) -> list[dict]:
    commits = ledger.rows("SELECT * FROM commits WHERE run_id = ?", (run_id,))
    by_sha = {row["commit_sha"]: row for row in commits}
    chain: list[dict] = []
    sha = commit_sha
    seen: set[str] = set()
    while sha and sha in by_sha and sha not in seen:
        seen.add(sha)
        chain.append(by_sha[sha])
        sha = by_sha[sha].get("parent_sha")
    return chain


def descendants(ledger, run_id: str, commit_sha: str) -> list[str]:
    commits = ledger.rows("SELECT commit_sha, parent_sha FROM commits WHERE run_id = ?", (run_id,))
    children: dict[str, list[str]] = {}
    for row in commits:
        parent = row.get("parent_sha")
        if parent:
            children.setdefault(parent, []).append(row["commit_sha"])
    output: list[str] = []
    stack = list(children.get(commit_sha, []))
    seen: set[str] = set()
    while stack:
        sha = stack.pop()
        if sha in seen:
            continue
        seen.add(sha)
        output.append(sha)
        stack.extend(children.get(sha, []))
    return output
