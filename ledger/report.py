"""Scientist-facing report. This file is not mounted into the specimen."""

from pathlib import Path

from lattice.git import Repo
from lattice.lineage import ancestry, descendants
import json


def _settings_lines(ledger, run_id: str) -> list[str]:
    rows = ledger.rows(
        "SELECT key, value FROM settings WHERE run_id = ? ORDER BY key",
        (run_id,),
    )
    if not rows:
        return ["No run settings were recorded."]
    lines = ["Recorded run settings:"]
    for row in rows:
        lines.append(f"- {row['key']}: {row['value']}")
    return lines


def write_report(ledger, folder: Path) -> Path:
    text = render_report(ledger, folder)
    path = folder / "report.md"
    path.write_text(text, encoding="utf-8")
    return path


def render_report(ledger, folder: Path) -> str:
    run_id = folder.name
    run = ledger.get_run(run_id)
    if run is None:
        raise FileNotFoundError(run_id)
    train = ledger.rows(
        """
        SELECT * FROM episodes
        WHERE run_id = ? AND phase = 'train' AND finished_at IS NOT NULL
        ORDER BY generation, id
        """,
        (run_id,),
    )
    held = ledger.rows(
        """
        SELECT * FROM episodes
        WHERE run_id = ? AND phase = 'heldout' AND finished_at IS NOT NULL
        ORDER BY generation, id
        """,
        (run_id,),
    )
    shocks = ledger.rows(
        "SELECT * FROM shocks WHERE run_id = ? ORDER BY generation, id",
        (run_id,),
    )
    reuse = ledger.rows(
        "SELECT * FROM reuse_events WHERE run_id = ? ORDER BY id",
        (run_id,),
    )
    artifacts = ledger.rows(
        """
        SELECT a.path, a.generation, a.agent_id, a.task_id, a.pruned, e.fitness, e.reuse_score
        FROM artifacts a
        JOIN episodes e ON e.id = a.episode_id
        WHERE a.run_id = ? AND e.phase = 'train'
        ORDER BY a.generation, a.id
        """,
        (run_id,),
    )
    messages = ledger.rows(
        """
        SELECT message, COUNT(*) AS n
        FROM commits
        WHERE run_id = ? AND agent_id NOT IN ('harness', 'shock')
        GROUP BY message
        ORDER BY n DESC, message
        """,
        (run_id,),
    )
    specimen = folder / "specimen"
    tracked = Repo.open(specimen).tracked() if (specimen / ".git").exists() else []
    lines = [
        f"# Pegmatite report `{run_id}`",
        "",
        "Given the same initial conditions, task distribution, resource constraints, model, and shocks, what software conventions spontaneously persist?",
        "",
        "## Run",
        "",
        f"- seed: {run['seed']}",
        f"- status: {run['status']}",
        f"- provider: {run['provider']}",
        f"- runner: {run['runner']}",
        f"- generations: {run['completed_generations']}/{run['generations']}",
        f"- agents per generation: {run['n_agents']}",
        f"- shock generation: {run['shock_generation']}",
        f"- held-out every: {run['heldout_every']}",
        "",
        "## Fitness",
        "",
        "Components stay in their own columns. A failed hidden-test gate scores 0.",
        "Resource efficiency is the attempt's consumption divided into the generation median, then capped.",
        "Reuse counts imports and invocations only. Explainability is a seeded sample.",
        "A gamed attempt scores 0 and does not erase other attempts. Agents are not shown this formula.",
        "",
        *_settings_lines(ledger, run_id),
        "",
        _metrics_block(train),
        "",
        "## Fitness by generation",
        "",
        "| gen | episodes | mean correctness | mean resource | mean reuse | mean fitness | survived |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for generation, rows in _grouped(train):
        lines.append(
            "| {g} | {n} | {c:.3f} | {r:.3f} | {u:.3f} | {f:.3f} | {s}/{n} |".format(
                g=generation,
                n=len(rows),
                c=_mean(rows, "correctness"),
                r=_mean(rows, "resource_score"),
                u=_mean(rows, "reuse_score"),
                f=_mean(rows, "fitness"),
                s=sum(int(row["survived"]) for row in rows),
            )
        )
    lines.extend(["", "## Held-out probes", ""])
    lines.append(
        "Probes run in a detached worktree after that generation's training episodes. They are not merged into the specimen."
    )
    lines.append("")
    if not held:
        lines.append("No held-out probes in this run.")
    else:
        lines.extend(
            [
                "| gen | task | pass | correctness | fitness |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in held:
            lines.append(
                f"| {row['generation']} | {row['task_id']} | {row['tests_passed']}/{row['tests_total']} | {row['correctness']:.3f} | {row['fitness']:.3f} |"
            )
        lines.append("")
        lines.append(f"Mean held-out correctness: {_mean(held, 'correctness'):.3f}")
    lines.extend(["", "## Shocks", ""])
    if not shocks:
        lines.append("No shocks recorded.")
    else:
        for row in shocks:
            lines.append(
                f"- `{row['shock_id']}` generation {row['generation']}: "
                f"`{row['old_path']}` -> `{row['new_path']}` "
                f"origin `{row['origin_commit'] or '-'}` "
                f"rename `{row['commit_sha'] or '-'}` "
                f"applied {row['applied']} ({row['reason']})"
            )
    lines.extend(["", "## Specimen at HEAD", ""])
    if tracked:
        for path in tracked:
            lines.append(f"- `{path}`")
    else:
        lines.append("The worktree has no tracked files.")
    lines.extend(["", "## Artifacts introduced by training episodes", ""])
    if not artifacts:
        lines.append("None.")
    else:
        lines.extend(
            [
                "| path | gen | agent | task | pruned | fitness | reuse |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in artifacts:
            lines.append(
                f"| `{row['path']}` | {row['generation']} | {row['agent_id']} | {row['task_id']} | {row['pruned']} | {row['fitness']:.3f} | {row['reuse_score']:.3f} |"
            )
    lines.extend(["", "## Reuse events", ""])
    if not reuse:
        lines.append("No dependence on an earlier surviving artifact was detected.")
    else:
        lines.append(f"{len(reuse)} event(s). Credit goes to the survived training episode that produced the file, including across a rename.")
        lines.append("")
        for row in reuse[:40]:
            lines.append(
                f"- gen {row['generation']}: {row['consumer_agent']} task {row['consumer_task']} {row['kind']} `{row['producer_path']}` from episode {row['producer_episode']} evidence `{row['evidence']}`"
            )
        if len(reuse) > 40:
            lines.append(f"- … {len(reuse) - 40} more")
    lines.extend(["", "## Commit messages", ""])
    lines.append("Messages are quoted as left by the author. Harness and shock commits are omitted here.")
    lines.append("")
    if not messages:
        lines.append("No agent commit messages.")
    else:
        for row in messages[:30]:
            shown = row["message"] if row["message"] else "(empty)"
            lines.append(f"- {row['n']}× `{shown}`")
    lines.extend(["", "## Lineage sample", ""])
    lines.append(_lineage_sample(ledger, run_id, train))
    lines.extend(
        [
            "",
            "## Reading this",
            "",
            "The rename shock is applied at the start of its generation, before that generation's agents. Held-out probes run after training.",
            "A failed gate is reverted with a later commit so the attempt stays in git history and leaves the worktree.",
            "Commit timestamps for the scripted provider are a function of the seed, so the specimen hash can be compared across machines. Live model output is stored in the ledger and is not regenerated.",
            "",
        ]
    )
    return "\n".join(lines)


def compare_runs(runs_root: Path, run_a: str, run_b: str) -> str:
    left = _load(runs_root, run_a)
    right = _load(runs_root, run_b)
    lines = [
        f"# Compare `{run_a}` and `{run_b}`",
        "",
        "| | " + run_a + " | " + run_b + " |",
        "| --- | --- | --- |",
    ]
    for label, key in (
        ("seed", "seed"),
        ("provider", "provider"),
        ("runner", "runner"),
        ("status", "status"),
    ):
        lines.append(f"| {label} | {left['run'][key]} | {right['run'][key]} |")
    for label in (
        "train episodes",
        "mean fitness",
        "mean correctness",
        "mean resource",
        "mean reuse",
        "mean novelty",
        "survival rate",
        "held-out correctness",
        "reuse events",
        "shocks applied",
    ):
        lines.append(f"| {label} | {left['stats'][label]} | {right['stats'][label]} |")
    only_a = sorted(left["paths"] - right["paths"])
    only_b = sorted(right["paths"] - left["paths"])
    both = sorted(left["paths"] & right["paths"])
    lines.extend(["", "## Paths at HEAD", ""])
    lines.append(f"Shared ({len(both)}): " + (", ".join(f"`{p}`" for p in both) or "none"))
    lines.append("")
    lines.append(f"Only `{run_a}` ({len(only_a)}): " + (", ".join(f"`{p}`" for p in only_a) or "none"))
    lines.append("")
    lines.append(f"Only `{run_b}` ({len(only_b)}): " + (", ".join(f"`{p}`" for p in only_b) or "none"))
    lines.append("")
    return "\n".join(lines)


def _load(runs_root: Path, run_id: str) -> dict:
    folder = runs_root / run_id
    ledger_path = folder / "ledger.sqlite"
    if not ledger_path.exists():
        raise FileNotFoundError(f"no run {run_id} in {runs_root}")
    from ledger.db import Ledger

    ledger = Ledger(ledger_path)
    try:
        run = ledger.get_run(run_id)
        if run is None:
            raise FileNotFoundError(run_id)
        train = ledger.rows(
            """
            SELECT * FROM episodes
            WHERE run_id = ? AND phase = 'train' AND finished_at IS NOT NULL
            """,
            (run_id,),
        )
        held = ledger.rows(
            """
            SELECT correctness FROM episodes
            WHERE run_id = ? AND phase = 'heldout' AND finished_at IS NOT NULL
            """,
            (run_id,),
        )
        reuse_n = ledger.rows("SELECT COUNT(*) AS n FROM reuse_events WHERE run_id = ?", (run_id,))[0]["n"]
        shocks = ledger.rows(
            "SELECT applied FROM shocks WHERE run_id = ?",
            (run_id,),
        )
        applied = sum(int(row["applied"]) for row in shocks)
        survived = sum(int(row["survived"]) for row in train)
        stats = {
            "train episodes": str(len(train)),
            "mean fitness": f"{_mean(train, 'fitness'):.3f}",
            "mean correctness": f"{_mean(train, 'correctness'):.3f}",
            "mean resource": f"{_mean(train, 'resource_score'):.3f}",
            "mean reuse": f"{_mean(train, 'reuse_score'):.3f}",
            "mean novelty": f"{_mean(train, 'novelty_score'):.3f}",
            "survival rate": f"{(survived / len(train)) if train else 0:.3f}",
            "held-out correctness": f"{_mean(held, 'correctness'):.3f}",
            "reuse events": str(reuse_n),
            "shocks applied": str(applied),
        }
        specimen = folder / "specimen"
        paths = set(Repo.open(specimen).tracked()) if (specimen / ".git").exists() else set()
        return {"run": run, "stats": stats, "paths": paths}
    finally:
        ledger.close()


def _lineage_sample(ledger, run_id: str, train: list[dict]) -> str:
    if not train:
        return "No training episodes."
    chosen = max(train, key=lambda row: (row["fitness"], row["id"]))
    sha = chosen.get("commit_sha")
    if not sha:
        return f"Episode {chosen['id']} ({chosen['agent_id']} / {chosen['task_id']}) has no commit."
    chain = ancestry(ledger, run_id, sha)
    kids = descendants(ledger, run_id, sha)
    reuse = ledger.rows(
        "SELECT * FROM reuse_events WHERE run_id = ? AND producer_episode = ?",
        (run_id, chosen["id"]),
    )
    lines = [
        f"Highest current fitness is episode {chosen['id']} "
        f"({chosen['agent_id']} / {chosen['task_id']}, fitness {chosen['fitness']:.3f}).",
        "",
        "Ancestry (newest first):",
    ]
    for row in chain:
        lines.append(
            f"- `{row['commit_sha'][:12]}` agent {row['agent_id']} "
            f"gen {row['generation']} task {row['task_id'] or '-'} "
            f"fitness {row['fitness'] if row['fitness'] is not None else '-'}"
        )
    lines.append("")
    lines.append(f"Descendant commits recorded from this one: {len(kids)}")
    lines.append(f"Later episodes that depended on it: {len({row['consumer_episode'] for row in reuse})}")
    return "\n".join(lines)


def _grouped(rows: list[dict]):
    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(int(row["generation"]), []).append(row)
    return sorted(groups.items())


def _mean(rows: list[dict], key: str) -> float:
    if not rows:
        return 0.0
    return sum(float(row[key] or 0.0) for row in rows) / len(rows)


def _metrics_block(train: list[dict]) -> str:
    if not train:
        return "No finished training episodes."
    survived = sum(int(row["survived"]) for row in train)
    return (
        f"Training episodes: {len(train)}. "
        f"Survived: {survived}. "
        f"Mean fitness: {_mean(train, 'fitness'):.3f}. "
        f"Mean correctness: {_mean(train, 'correctness'):.3f}. "
        f"Mean resource: {_mean(train, 'resource_score'):.3f}. "
        f"Mean reuse: {_mean(train, 'reuse_score'):.3f}."
    )
