"""Smallest full path: 2 agents, 3 generations, 1 task, one rename shock."""

import json

from agents.loop import ExperimentConfig, run_experiment
from lattice.git import Repo
from ledger.db import Ledger
from selection.explainability import is_sampled
from selection.fitness import FitnessConfig, combine, explainability_value


def test_two_agents_three_generations_one_task_and_a_shock(tmp_path):
    config = ExperimentConfig(
        seed=11,
        generations=3,
        n_agents=2,
        shock_generation=2,
        heldout_every=99,
        task_ids=("sum_ints",),
    )
    run_id = run_experiment(config, tmp_path)
    folder = tmp_path / run_id
    repo = Repo.open(folder / "specimen")
    ledger = Ledger(folder / "ledger.sqlite")
    cfg = FitnessConfig()
    try:
        train = ledger.rows(
            """
            SELECT * FROM episodes
            WHERE phase = 'train' AND finished_at IS NOT NULL
            ORDER BY id
            """
        )
        assert len(train) == 6
        for row in train:
            assert row["consumption"] is not None
            assert row["resource_score"] is not None
            assert row["reuse_score"] is not None
            assert row["fitness_at_birth"] is not None
            expected = combine(
                row["correctness"],
                row["resource_score"],
                row["reuse_score"],
                explainability_value(
                    bool(row["explainability_sampled"]),
                    row["explainability_score"],
                    cfg,
                ),
                cfg,
                gamed=bool(row["gamed"]),
            )
            assert row["fitness"] == expected
        stats = ledger.rows(
            "SELECT * FROM generation_stats WHERE phase = 'train' ORDER BY generation"
        )
        assert [row["generation"] for row in stats] == [1, 2, 3]
        settings = {
            row["key"]: json.loads(row["value"])
            for row in ledger.rows("SELECT key, value FROM settings")
        }
        assert settings["base_pass"] == 0.6
        assert settings["resource_weight"] == 0.15
        assert settings["reuse_weight"] == 0.15
        assert settings["explainability_weight"] == 0.1
        assert settings["resource_cap"] == 2.0
        assert settings["shock_generation"] == 2
        shock = ledger.rows("SELECT * FROM shocks")[0]
        assert shock["generation"] == 2
        assert shock["applied"] == 1
        assert shock["shock_id"] == "rename-11-2"
        assert repo._git(
            "merge-base", "--is-ancestor", shock["origin_commit"], "HEAD", check=False
        ).returncode == 0
        mark = ledger.rows(
            "SELECT start_sha FROM generation_marks WHERE generation = 2"
        )[0]["start_sha"]
        parent = repo._git("rev-parse", f"{shock['commit_sha']}^").stdout.strip()
        assert parent == mark
        agent_parent = ledger.rows(
            """
            SELECT parent_sha FROM commits
            WHERE generation = 2 AND agent_id = 'a0'
            ORDER BY rowid
            LIMIT 1
            """
        )[0]["parent_sha"]
        assert agent_parent == shock["commit_sha"]
        samples = ledger.rows("SELECT * FROM explainability")
        assert samples
        for sample in samples:
            assert bool(sample["sampled"]) == is_sampled(
                config.seed, sample["commit_sha"], sample["path"], cfg.explainability_every
            )
    finally:
        ledger.close()
