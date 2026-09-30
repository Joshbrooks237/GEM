"""SQLite ledger. One database per run."""

import sqlite3
from pathlib import Path


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self.conn.executescript(schema)

    def close(self) -> None:
        self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    def rows(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def create_run(self, run_id: str, config_json: str, **fields) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO runs (
                run_id, seed, created_at, updated_at, status, provider, runner,
                generations, n_agents, shock_generation, heldout_every,
                completed_generations, config_json
            ) VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                run_id,
                fields["seed"],
                now,
                now,
                fields["provider"],
                fields["runner"],
                fields["generations"],
                fields["n_agents"],
                fields["shock_generation"],
                fields["heldout_every"],
                config_json,
            ),
        )
        self.commit()

    def insert_settings(self, run_id: str, mapping: dict) -> None:
        for key, value in mapping.items():
            self.conn.execute(
                """
                INSERT INTO settings (run_id, key, value) VALUES (?, ?, ?)
                ON CONFLICT(run_id, key) DO NOTHING
                """,
                (run_id, key, value),
            )
        self.commit()

    def get_run(self, run_id: str) -> dict | None:
        found = self.rows("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        return found[0] if found else None

    def set_status(self, run_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
            (status, utc_now(), run_id),
        )
        self.commit()

    def set_generations(self, run_id: str, generations: int, config_json: str) -> None:
        self.conn.execute(
            """
            UPDATE runs
            SET generations = ?, config_json = ?, updated_at = ?, status = 'running'
            WHERE run_id = ?
            """,
            (generations, config_json, utc_now(), run_id),
        )
        self.commit()

    def set_completed(self, run_id: str, generation: int) -> None:
        self.conn.execute(
            """
            UPDATE runs
            SET completed_generations = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (generation, utc_now(), run_id),
        )
        self.commit()

    def mark_generation_start(self, run_id: str, generation: int, start_sha: str) -> None:
        self.conn.execute(
            """
            INSERT INTO generation_marks (run_id, generation, start_sha, finished)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(run_id, generation) DO UPDATE SET
                start_sha = excluded.start_sha,
                finished = 0
            """,
            (run_id, generation, start_sha),
        )
        self.commit()

    def mark_generation_finished(self, run_id: str, generation: int) -> None:
        self.conn.execute(
            """
            UPDATE generation_marks SET finished = 1
            WHERE run_id = ? AND generation = ?
            """,
            (run_id, generation),
        )
        self.set_completed(run_id, generation)

    def open_generation(self, run_id: str) -> dict | None:
        found = self.rows(
            """
            SELECT * FROM generation_marks
            WHERE run_id = ? AND finished = 0
            ORDER BY generation
            """,
            (run_id,),
        )
        return found[0] if found else None

    def begin_episode(self, **fields) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO episodes (
                run_id, generation, agent_id, task_id, phase, started_at, parent_sha
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["generation"],
                fields["agent_id"],
                fields["task_id"],
                fields["phase"],
                utc_now(),
                fields["parent_sha"],
            ),
        )
        self.commit()
        return int(cur.lastrowid)

    def finish_episode(self, episode_id: int, **fields) -> None:
        self.conn.execute(
            """
            UPDATE episodes SET
                finished_at = ?,
                token_usage = ?,
                tool_calls = ?,
                wall_time_s = ?,
                commit_sha = ?,
                tests_passed = ?,
                tests_total = ?,
                correctness = ?,
                consumption = ?,
                resource_score = ?,
                reuse_score = ?,
                novelty_score = ?,
                fitness = ?,
                fitness_at_birth = ?,
                survived = ?,
                gamed = ?,
                attributable = ?,
                quality_json = ?
            WHERE id = ?
            """,
            (
                utc_now(),
                fields["token_usage"],
                fields["tool_calls"],
                fields["wall_time_s"],
                fields["commit_sha"],
                fields["tests_passed"],
                fields["tests_total"],
                fields["correctness"],
                fields["consumption"],
                fields["resource_score"],
                fields["reuse_score"],
                fields["novelty_score"],
                fields["fitness"],
                fields["fitness_at_birth"],
                fields["survived"],
                fields["gamed"],
                fields["attributable"],
                fields["quality_json"],
                episode_id,
            ),
        )
        self.commit()

    def set_reuse_only(self, episode_id: int, reuse: float) -> None:
        self.conn.execute(
            "UPDATE episodes SET reuse_score = ? WHERE id = ?",
            (reuse, episode_id),
        )

    def set_resource(self, episode_id: int, resource_score: float) -> None:
        self.conn.execute(
            "UPDATE episodes SET resource_score = ? WHERE id = ?",
            (resource_score, episode_id),
        )

    def set_explainability(self, episode_id: int, sampled: int, score: float | None) -> None:
        self.conn.execute(
            """
            UPDATE episodes
            SET explainability_sampled = ?, explainability_score = ?
            WHERE id = ?
            """,
            (sampled, score, episode_id),
        )

    def seal_birth(self, run_id: str, generation: int, phase: str) -> None:
        self.conn.execute(
            """
            UPDATE episodes
            SET fitness_at_birth = fitness
            WHERE run_id = ? AND generation = ? AND phase = ? AND fitness_at_birth IS NULL
            """,
            (run_id, generation, phase),
        )

    def set_fitness(self, episode_id: int, reuse: float, fitness: float) -> None:
        self.conn.execute(
            "UPDATE episodes SET reuse_score = ?, fitness = ? WHERE id = ?",
            (reuse, fitness, episode_id),
        )
        self.conn.execute(
            "UPDATE commits SET fitness = ? WHERE episode_id = ?",
            (fitness, episode_id),
        )

    def insert_commit(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO commits (
                run_id, generation, agent_id, commit_sha, parent_sha, task_id,
                episode_id, timestamp, token_usage, wall_time_s, fitness, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["generation"],
                fields["agent_id"],
                fields["commit_sha"],
                fields.get("parent_sha"),
                fields.get("task_id"),
                fields.get("episode_id"),
                fields["timestamp"],
                fields.get("token_usage"),
                fields.get("wall_time_s"),
                fields.get("fitness"),
                fields.get("message"),
            ),
        )

    def insert_artifact(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT INTO artifacts (
                run_id, episode_id, commit_sha, path, blob_sha, generation,
                agent_id, task_id, archived, pruned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields.get("episode_id"),
                fields["commit_sha"],
                fields["path"],
                fields.get("blob_sha"),
                fields["generation"],
                fields["agent_id"],
                fields.get("task_id"),
                int(fields.get("archived", 0)),
                int(fields.get("pruned", 0)),
            ),
        )

    def insert_observation(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT INTO observations (
                run_id, generation, episode_id, role, path, evidence, blob_sha,
                producer_episode, producer_commit, counts_as_reuse
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["generation"],
                fields["episode_id"],
                fields["role"],
                fields.get("path"),
                fields.get("evidence"),
                fields.get("blob_sha"),
                fields.get("producer_episode"),
                fields.get("producer_commit"),
                int(fields.get("counts_as_reuse", 0)),
            ),
        )

    def insert_episode_diff(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT INTO episode_diffs (
                episode_id, run_id, start_commit, end_commit, parent_commit,
                files_changed, lines_added, lines_deleted, attributable,
                inherited_executable, diff_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["episode_id"],
                fields["run_id"],
                fields["start_commit"],
                fields.get("end_commit"),
                fields.get("parent_commit"),
                fields["files_changed"],
                fields["lines_added"],
                fields["lines_deleted"],
                int(fields["attributable"]),
                int(fields["inherited_executable"]),
                fields["diff_json"],
            ),
        )

    def insert_reuse(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT INTO reuse_events (
                run_id, generation, consumer_agent, consumer_episode, consumer_task,
                producer_episode, producer_commit, producer_path, evidence, kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["generation"],
                fields["consumer_agent"],
                fields["consumer_episode"],
                fields["consumer_task"],
                fields["producer_episode"],
                fields["producer_commit"],
                fields["producer_path"],
                fields["evidence"],
                fields["kind"],
            ),
        )

    def insert_shock(self, **fields) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO shocks (
                run_id, shock_id, generation, shock_type, old_path, new_path,
                origin_commit, commit_sha, applied, reason, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["shock_id"],
                fields["generation"],
                fields["shock_type"],
                fields.get("old_path"),
                fields.get("new_path"),
                fields.get("origin_commit"),
                fields.get("commit_sha"),
                int(fields.get("applied", 0)),
                fields.get("reason"),
                fields["detail_json"],
            ),
        )
        self.commit()
        return int(cur.lastrowid)

    def update_shock(self, row_id: int, commit_sha: str | None, applied: int) -> None:
        self.conn.execute(
            "UPDATE shocks SET commit_sha = ?, applied = ? WHERE id = ?",
            (commit_sha, applied, row_id),
        )

    def insert_explainability(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT INTO explainability (
                run_id, generation, episode_id, commit_sha, path, sampled,
                sample_key, explainer, explanation, score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["generation"],
                fields["episode_id"],
                fields["commit_sha"],
                fields["path"],
                int(fields["sampled"]),
                fields["sample_key"],
                fields["explainer"],
                fields.get("explanation"),
                fields.get("score"),
            ),
        )

    def insert_antigaming(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT INTO antigaming (
                run_id, generation, episode_id, commit_sha, trigger, reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["generation"],
                fields["episode_id"],
                fields.get("commit_sha"),
                fields["trigger"],
                fields["reason"],
            ),
        )

    def insert_generation_stat(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO generation_stats (
                run_id, generation, phase, success_count, median_consumption
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["generation"],
                fields["phase"],
                fields["success_count"],
                fields["median_consumption"],
            ),
        )

    def insert_llm(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT INTO llm_calls (run_id, episode_id, tokens, request_json, response_text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                fields["run_id"],
                fields["episode_id"],
                fields["tokens"],
                fields["request_json"],
                fields["response_text"],
            ),
        )

    def insert_tool(self, **fields) -> None:
        self.conn.execute(
            """
            INSERT INTO tool_calls (episode_id, seq, cmd, exit_code, stdout_excerpt, stderr_excerpt)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fields["episode_id"],
                fields["seq"],
                fields["cmd"],
                fields["exit_code"],
                fields["stdout_excerpt"],
                fields["stderr_excerpt"],
            ),
        )

    def latest_artifact(self, run_id: str, path: str, before_episode: int) -> dict | None:
        found = self.rows(
            """
            SELECT * FROM artifacts
            WHERE run_id = ? AND path = ? AND pruned = 0 AND episode_id < ?
            ORDER BY generation DESC, id DESC
            LIMIT 1
            """,
            (run_id, path, before_episode),
        )
        return found[0] if found else None

    def delete_generation(self, run_id: str, generation: int) -> None:
        ep_ids = [
            row["id"]
            for row in self.rows(
                "SELECT id FROM episodes WHERE run_id = ? AND generation = ?",
                (run_id, generation),
            )
        ]
        if ep_ids:
            marks = ",".join("?" * len(ep_ids))
            self.conn.execute(
                f"DELETE FROM tool_calls WHERE episode_id IN ({marks})",
                ep_ids,
            )
            self.conn.execute(
                f"DELETE FROM llm_calls WHERE episode_id IN ({marks})",
                ep_ids,
            )
            self.conn.execute(
                f"DELETE FROM reuse_events WHERE consumer_episode IN ({marks}) OR producer_episode IN ({marks})",
                ep_ids + ep_ids,
            )
            self.conn.execute(
                f"DELETE FROM explainability WHERE episode_id IN ({marks})",
                ep_ids,
            )
            self.conn.execute(
                f"DELETE FROM antigaming WHERE episode_id IN ({marks})",
                ep_ids,
            )
            self.conn.execute(
                f"DELETE FROM observations WHERE episode_id IN ({marks})",
                ep_ids,
            )
            self.conn.execute(
                f"DELETE FROM episode_diffs WHERE episode_id IN ({marks})",
                ep_ids,
            )
            self.conn.execute(
                f"DELETE FROM artifacts WHERE episode_id IN ({marks})",
                ep_ids,
            )
            self.conn.execute(
                f"DELETE FROM commits WHERE episode_id IN ({marks})",
                ep_ids,
            )
        self.conn.execute(
            "DELETE FROM commits WHERE run_id = ? AND generation = ?",
            (run_id, generation),
        )
        self.conn.execute(
            "DELETE FROM artifacts WHERE run_id = ? AND generation = ?",
            (run_id, generation),
        )
        self.conn.execute(
            "DELETE FROM episodes WHERE run_id = ? AND generation = ?",
            (run_id, generation),
        )
        self.conn.execute(
            "DELETE FROM shocks WHERE run_id = ? AND generation = ?",
            (run_id, generation),
        )
        self.conn.execute(
            "DELETE FROM generation_stats WHERE run_id = ? AND generation = ?",
            (run_id, generation),
        )
        self.conn.execute(
            "DELETE FROM generation_marks WHERE run_id = ? AND generation = ?",
            (run_id, generation),
        )
        self.commit()
