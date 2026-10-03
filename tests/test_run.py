import base64
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import cli
from agents.loop import ExperimentConfig, resume_experiment, run_experiment
from agents.provider import Completion, ScriptedProvider
from lattice.git import Repo
from ledger.db import Ledger
from ledger.report import compare_runs
from selection.fitness import FitnessConfig

ROOT = Path(__file__).resolve().parents[1]


class BadProvider:
    name = "bad"

    def complete(self, messages, max_tokens):
        blob = json.dumps(messages)
        if "Tool result" not in blob:
            command = (
                "printf '%s\\n' 'print(123)' > bad.py && "
                "printf '%s\\n' 'python bad.py' > ENTRY && "
                "git add -A && git commit -m bad"
            )
            text = json.dumps({"tool": "shell", "cmd": command})
            return Completion(text, 10, 10)
        return Completion(json.dumps({"tool": "done"}), 4, 4)


def test_failed_episode_is_reverted_and_kept_in_history(tmp_path):
    config = ExperimentConfig(
        seed=1,
        generations=1,
        n_agents=1,
        shock_generation=0,
        heldout_every=99,
        provider="bad",
    )
    run_id = run_experiment(config, tmp_path, provider=BadProvider())
    repo = Repo.open(tmp_path / run_id / "specimen")
    assert "bad.py" not in repo.tracked()
    log = repo._git("log", "--format=%s").stdout
    assert "bad" in log.splitlines()
    ledger = Ledger(tmp_path / run_id / "ledger.sqlite")
    try:
        episode = ledger.rows("SELECT * FROM episodes")[0]
        assert episode["correctness"] == 0
        assert episode["fitness"] == 0
        assert episode["survived"] == 0
    finally:
        ledger.close()


def test_later_reuse_raises_fitness_without_moving_birth(tmp_path):
    config = ExperimentConfig(
        seed=42,
        generations=2,
        n_agents=2,
        shock_generation=0,
        heldout_every=99,
    )
    run_id = run_experiment(config, tmp_path)
    ledger = Ledger(tmp_path / run_id / "ledger.sqlite")
    try:
        first = ledger.rows(
            """
            SELECT * FROM episodes
            WHERE phase = 'train' AND generation = 1 AND agent_id = 'a0'
            """
        )[0]
        assert first["reuse_score"] > 0
        assert first["fitness"] > first["fitness_at_birth"]
        assert first["resource_score"] is not None
        assert first["consumption"] is not None
        assert ledger.rows("SELECT COUNT(*) AS n FROM reuse_events")[0]["n"] >= 1
    finally:
        ledger.close()


def test_rename_shock_runs_before_generation_agents(tmp_path):
    config = ExperimentConfig(
        seed=42,
        generations=2,
        n_agents=2,
        shock_generation=2,
        heldout_every=99,
    )
    run_id = run_experiment(config, tmp_path)
    folder = tmp_path / run_id
    repo = Repo.open(folder / "specimen")
    tracked = set(repo.tracked())
    assert "helper.py" in tracked
    assert "helper.r2.py" in tracked
    assert "sum_even.py" not in tracked
    ledger = Ledger(folder / "ledger.sqlite")
    try:
        shock = ledger.rows("SELECT * FROM shocks")[0]
        assert shock["generation"] == 2
        assert shock["applied"] == 1
        assert shock["old_path"] == "helper.py"
        assert shock["new_path"] == "helper.r2.py"
        assert shock["shock_id"] == "rename-42-2"
        origin = shock["origin_commit"]
        assert origin
        assert repo._git("merge-base", "--is-ancestor", origin, "HEAD", check=False).returncode == 0
        mark = ledger.rows(
            "SELECT start_sha FROM generation_marks WHERE generation = 2"
        )[0]["start_sha"]
        assert shock["commit_sha"]
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
    finally:
        ledger.close()
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert "helper.r2.py" in report
    assert "Fitness" in report


def test_hidden_cases_stay_out_of_training_prompts(tmp_path):
    config = ExperimentConfig(
        seed=42,
        generations=1,
        n_agents=1,
        shock_generation=0,
        heldout_every=1,
    )
    run_id = run_experiment(config, tmp_path)
    ledger = Ledger(tmp_path / run_id / "ledger.sqlite")
    try:
        train_prompts = "\n".join(
            row["request_json"]
            for row in ledger.rows(
                """
                SELECT c.request_json
                FROM llm_calls c
                JOIN episodes e ON e.id = c.episode_id
                WHERE e.phase = 'train'
                """
            )
        )
        assert "xylophone" not in train_prompts
        assert "9 9 9" not in train_prompts
        assert "even integers" not in train_prompts
        held_prompts = "\n".join(
            row["request_json"]
            for row in ledger.rows(
                """
                SELECT c.request_json
                FROM llm_calls c
                JOIN episodes e ON e.id = c.episode_id
                WHERE e.phase = 'heldout'
                """
            )
        )
        assert "even integers" in held_prompts
    finally:
        ledger.close()


def test_same_seed_reproduces_the_specimen(tmp_path):
    config = ExperimentConfig(
        seed=7,
        generations=1,
        n_agents=3,
        shock_generation=0,
        heldout_every=99,
    )
    left = run_experiment(config, tmp_path / "a")
    right = run_experiment(config, tmp_path / "b")
    head_a = Repo.open(tmp_path / "a" / left / "specimen").head()
    head_b = Repo.open(tmp_path / "b" / right / "specimen").head()
    assert head_a == head_b


def test_resume_continues_at_the_next_generation(tmp_path):
    config = ExperimentConfig(
        seed=3,
        generations=1,
        n_agents=1,
        shock_generation=0,
        heldout_every=99,
    )
    run_id = run_experiment(config, tmp_path)
    ledger = Ledger(tmp_path / run_id / "ledger.sqlite")
    try:
        stored = ExperimentConfig.from_json(ledger.get_run(run_id)["config_json"])
        stored.generations = 2
        ledger.set_generations(run_id, 2, stored.to_json())
    finally:
        ledger.close()
    resume_experiment(run_id, tmp_path)
    ledger = Ledger(tmp_path / run_id / "ledger.sqlite")
    try:
        count = ledger.rows(
            "SELECT COUNT(*) AS n FROM episodes WHERE phase = 'train' AND finished_at IS NOT NULL"
        )[0]["n"]
        assert count == 2
        assert ledger.get_run(run_id)["completed_generations"] == 2
        assert ledger.get_run(run_id)["status"] == "complete"
    finally:
        ledger.close()


def test_cli_run_report_and_compare(tmp_path):
    common = [
        sys.executable,
        str(ROOT / "cli.py"),
        "--run-dir",
        str(tmp_path),
    ]
    flags = ["--generations", "1", "--agents", "1", "--shock-generation", "0", "--heldout-every", "99"]
    first = subprocess.run(
        common + ["run", "--seed", "4", *flags],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    second = subprocess.run(
        common + ["run", "--seed", "5", *flags],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    run_a = first.stdout.strip().splitlines()[-1]
    run_b = second.stdout.strip().splitlines()[-1]
    reported = subprocess.run(
        common + ["report", run_a],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert reported.stdout.strip().endswith("report.md")
    compared = subprocess.run(
        common + ["compare", run_a, run_b],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert run_a in compared.stdout
    assert run_b in compared.stdout
    again = compare_runs(tmp_path, run_a, run_b)
    assert "mean fitness" in again


def test_default_shock_generation_is_25():
    assert ExperimentConfig(seed=1).shock_generation == 25


class _GamingOnSecond(ScriptedProvider):
    def complete(self, messages, max_tokens):
        agent = ""
        for message in messages:
            for line in message.get("content", "").splitlines():
                if line.startswith("Agent: "):
                    agent = line.split(":", 1)[1].strip()
        tool_results = sum(
            1
            for message in messages
            if message.get("role") == "user" and str(message.get("content", "")).startswith("Tool result")
        )
        if agent == "a1" and tool_results == 1:
            source = (
                "import sys\n"
                "print(sum(int(x) for x in sys.stdin.read().split()))\n"
                "# tasks/hidden\n"
            )
            encoded = base64.b64encode(source.encode()).decode()
            command = (
                "python -c \"import base64,pathlib; "
                f"pathlib.Path('sum_ints.py').write_bytes(base64.b64decode('{encoded}'))\" "
                "&& printf '%s\\n' 'python sum_ints.py' > ENTRY "
                "&& git add -A && git commit -m gamed"
            )
            return Completion(json.dumps({"tool": "shell", "cmd": command}), 8, 8)
        if agent == "a1" and tool_results == 0:
            return Completion(json.dumps({"tool": "shell", "cmd": "git status --porcelain"}), 4, 4)
        if agent == "a1":
            return Completion(json.dumps({"tool": "done"}), 2, 2)
        return super().complete(messages, max_tokens)


def test_one_gamed_attempt_does_not_erase_the_generation(tmp_path):
    config = ExperimentConfig(
        seed=8,
        generations=1,
        n_agents=2,
        shock_generation=0,
        heldout_every=99,
        task_ids=("sum_ints",),
        provider="scripted",
    )
    run_id = run_experiment(config, tmp_path, provider=_GamingOnSecond())
    repo = Repo.open(tmp_path / run_id / "specimen")
    log = repo._git("log", "--format=%s").stdout
    assert "gamed" in log.splitlines()
    ledger = Ledger(tmp_path / run_id / "ledger.sqlite")
    try:
        rows = ledger.rows(
            "SELECT * FROM episodes WHERE phase = 'train' ORDER BY id"
        )
        assert len(rows) == 2
        first, second = rows
        assert first["agent_id"] == "a0"
        assert first["survived"] == 1
        assert first["gamed"] == 0
        assert first["fitness"] > 0
        assert second["agent_id"] == "a1"
        assert second["correctness"] == 1
        assert second["gamed"] == 1
        assert second["fitness"] == 0
        assert second["survived"] == 0
        hits = ledger.rows("SELECT * FROM antigaming")
        assert len(hits) == 1
        assert hits[0]["episode_id"] == second["id"]
        assert hits[0]["trigger"] == "evaluator_reference"
        assert "tasks/hidden" in hits[0]["reason"]
    finally:
        ledger.close()


_RAW_DEV_COUNT = textwrap.dedent(
    """\
    import sys
    count = 0
    for raw in sys.stdin:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = {}
        for token in line.split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if key in {"name", "role", "years"}:
                fields[key] = value
        years = fields.get("years")
        if years is not None and not (
            years == "0" or (years.isdigit() and not (len(years) > 1 and years.startswith("0")))
        ):
            continue
        if fields.get("role") == "dev":
            count += 1
    print(f"count={count}")
    """
)


def _agent_and_tools(messages):
    agent = ""
    tool_results = 0
    for message in messages:
        content = str(message.get("content", ""))
        if message.get("role") == "user" and content.startswith("Tool result"):
            tool_results += 1
        for line in content.splitlines():
            if line.startswith("Agent: "):
                agent = line.split(":", 1)[1].strip()
    return agent, tool_results


class _Episode107Provider:
    """First agent plants a passing program. Second agent only runs a failing redirect."""

    name = "episode-107"

    def complete(self, messages, max_tokens):
        agent, tool_results = _agent_and_tools(messages)
        if agent == "a0" and tool_results == 0:
            encoded = base64.b64encode(_RAW_DEV_COUNT.encode()).decode()
            command = (
                "python -c \"import base64,pathlib; "
                f"pathlib.Path('raw_dev_count.py').write_bytes(base64.b64decode('{encoded}'))\" "
                "&& printf '%s\\n' 'python3 raw_dev_count.py' > ENTRY "
                "&& git add -A && git commit -m seed"
            )
            return Completion(json.dumps({"tool": "shell", "cmd": command}), 8, 8)
        if agent == "a0":
            return Completion(json.dumps({"tool": "done"}), 2, 2)
        if tool_results == 0:
            command = "echo 'x' > ENTRY ; ( ; true"
            return Completion(json.dumps({"tool": "shell", "cmd": command}), 4, 4)
        return Completion(json.dumps({"tool": "done"}), 2, 2)


def test_failing_redirect_does_not_add_entry_to_touched(tmp_path):
    config = ExperimentConfig(
        seed=107,
        generations=1,
        n_agents=2,
        shock_generation=0,
        heldout_every=99,
        ecology="exp3",
        task_ids=("raw_dev_count",),
        provider="scripted",
    )
    run_id = run_experiment(config, tmp_path, provider=_Episode107Provider())
    ledger = Ledger(tmp_path / run_id / "ledger.sqlite")
    try:
        rows = ledger.rows("SELECT * FROM episodes WHERE phase = 'train' ORDER BY id")
        assert [row["agent_id"] for row in rows] == ["a0", "a1"]
        planted, failed = rows
        assert planted["survived"] == 1
        failed_notes = json.loads(failed["quality_json"])
        tool = ledger.rows(
            "SELECT exit_code, cmd FROM tool_calls WHERE episode_id = ? ORDER BY seq",
            (failed["id"],),
        )[0]
        assert tool["exit_code"] == 2
        assert "> ENTRY" in tool["cmd"]
        assert "ENTRY" not in failed_notes["touched"]
        assert failed["tests_passed"] == failed["tests_total"]
        assert failed["correctness"] == 1
        assert failed["attributable"] == 0
        assert failed["survived"] == 0
        assert failed["fitness"] == 0
    finally:
        ledger.close()


class _DoneProvider:
    name = "done"

    def complete(self, messages, max_tokens):
        return Completion(json.dumps({"tool": "done"}), 1, 1)


def test_run_start_records_model_and_cli_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("PEGMATITE_MODEL", "from-env")
    config = ExperimentConfig(
        seed=9,
        generations=1,
        n_agents=1,
        provider="openai",
        runner="local",
        shock_generation=6,
        heldout_every=8,
        ecology="exp3",
        fitness=FitnessConfig(base_pass=0.5),
    )
    run_id = run_experiment(config, tmp_path, provider=_DoneProvider())
    ledger = Ledger(tmp_path / run_id / "ledger.sqlite")
    try:
        settings = {
            row["key"]: json.loads(row["value"])
            for row in ledger.rows("SELECT key, value FROM settings")
        }
        assert settings["model"] == "from-env"
        assert settings["cli_flags"] == {
            "seed": 9,
            "generations": 1,
            "agents": 1,
            "provider": "openai",
            "runner": "local",
            "shock-generation": 6,
            "ecology": "exp3",
            "heldout-every": 8,
            "base-pass": 0.5,
            "resource-weight": 0.15,
            "reuse-weight": 0.15,
            "explainability-weight": 0.1,
            "resource-cap": 2.0,
            "model": "from-env",
        }
        stored = ExperimentConfig.from_json(ledger.get_run(run_id)["config_json"])
        assert stored.model == "from-env"
    finally:
        ledger.close()


def test_cli_passes_model_and_flags_without_a_run(monkeypatch):
    seen = {}

    def capture(config, runs_root):
        seen["config"] = config
        seen["root"] = runs_root
        return "captured"

    monkeypatch.delenv("PEGMATITE_MODEL", raising=False)
    monkeypatch.setattr(cli, "run_experiment", capture)
    code = cli.main(
        [
            "--run-dir",
            "/tmp/pegmatite-not-a-run",
            "run",
            "--seed",
            "9",
            "--generations",
            "12",
            "--agents",
            "3",
            "--provider",
            "openai",
            "--runner",
            "local",
            "--shock-generation",
            "6",
            "--ecology",
            "exp3",
            "--heldout-every",
            "8",
            "--base-pass",
            "0.5",
        ]
    )
    assert code == 0
    assert "config" in seen
    config = seen["config"]
    assert config.model == "gpt-4o-mini"
    assert config.seed == 9
    assert config.generations == 12
    assert config.n_agents == 3
    assert config.provider == "openai"
    assert config.runner == "local"
    assert config.shock_generation == 6
    assert config.ecology == "exp3"
    assert config.heldout_every == 8
    assert config.fitness.base_pass == 0.5
    assert seen["root"] == Path("/tmp/pegmatite-not-a-run")
