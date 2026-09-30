"""Generation loop.

Episodes in a generation run one after another so the specimen history stays
linear. Agents are not told how survival or reuse is scored.
"""

import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agents.prompts import SYSTEM_PROMPT, tool_message, user_message
from agents.provider import make_provider, parse_action
from env.limits import Limits, clip
from env.runner import make_sandbox
from lattice.artifacts import evaluator_targets
from lattice.observe import (
    classify_command,
    diff_records,
    import_dependencies,
    snapshot_tree,
    touched_paths,
)
from lattice.git import Repo, git_date
from lattice.lineage import refresh_reuse_fitness, source_episode
from ledger.db import Ledger
from selection.antigaming import audit
from selection.attribution import counterfactual_passes
from selection.keepset import candidate_attributable
from selection.archive import archive_paths, load_archive_texts
from selection.evaluator import evaluate, quality_notes
from selection.explainability import explain, is_sampled, sample_key
from selection.fitness import FitnessConfig, consumption, median, resource_efficiency
from selection.novelty import novelty_of
from shocks.rename_tool import make_shock
from tasks.pool import load_ecology, task_id_for, training_schedule


@dataclass
class ExperimentConfig:
    seed: int
    generations: int = 50
    n_agents: int = 3
    shock_generation: int = 25
    heldout_every: int = 10
    provider: str = "scripted"
    runner: str = "local"
    shock: str = "rename_tool"
    shock_fallback_path: str = "fallback-artifact"
    task_ids: tuple[str, ...] | None = None
    ecology: str = "exp2"
    limits: Limits = field(default_factory=Limits)
    fitness: FitnessConfig = field(default_factory=FitnessConfig)

    def __post_init__(self) -> None:
        if self.generations < 1 or self.n_agents < 1:
            raise ValueError("generations and n_agents must be >= 1")
        if self.shock_generation < 0 or self.heldout_every < 1:
            raise ValueError("shock_generation must be >= 0 and heldout_every must be >= 1")
        if self.ecology not in {"exp2", "exp3"}:
            raise ValueError(f"unknown ecology: {self.ecology}")
        if isinstance(self.task_ids, list):
            self.task_ids = tuple(self.task_ids)
        if not isinstance(self.limits, Limits):
            self.limits = Limits(**self.limits)
        if not isinstance(self.fitness, FitnessConfig):
            self.fitness = FitnessConfig(**self.fitness)

    def to_json(self) -> str:
        payload = asdict(self)
        if payload.get("task_ids") is not None:
            payload["task_ids"] = list(payload["task_ids"])
        return json.dumps(payload, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "ExperimentConfig":
        return cls(**json.loads(text))


def run_experiment(config: ExperimentConfig, runs_root: Path, provider=None) -> str:
    runs_root.mkdir(parents=True, exist_ok=True)
    run_id = _new_run_id(config.seed, runs_root)
    folder = runs_root / run_id
    folder.mkdir(parents=True)
    repo = Repo.create(folder / "specimen", git_date(config.seed, 0, 0, 0))
    ledger = Ledger(folder / "ledger.sqlite")
    ledger.create_run(
        run_id,
        config.to_json(),
        seed=config.seed,
        provider=config.provider,
        runner=config.runner,
        generations=config.generations,
        n_agents=config.n_agents,
        shock_generation=config.shock_generation,
        heldout_every=config.heldout_every,
    )
    _store_settings(ledger, run_id, config)
    _announce(config, run_id)
    try:
        _advance(config, ledger, repo, folder, run_id, 1, provider or make_provider(config.provider), [])
        ledger.set_status(run_id, "complete")
        path = write_report_file(ledger, folder)
        print(f"report {path}", flush=True)
    except BaseException:
        ledger.set_status(run_id, "interrupted")
        raise
    finally:
        ledger.close()
    return run_id


def resume_experiment(
    run_id: str,
    runs_root: Path,
    provider=None,
    generations: int | None = None,
) -> str:
    folder = runs_root / run_id
    ledger_path = folder / "ledger.sqlite"
    if not ledger_path.exists():
        raise FileNotFoundError(f"no run {run_id} in {runs_root}")
    ledger = Ledger(ledger_path)
    try:
        row = ledger.get_run(run_id)
        if row is None:
            raise FileNotFoundError(f"no run {run_id}")
        config = ExperimentConfig.from_json(row["config_json"])
        if generations is not None:
            if generations < row["completed_generations"]:
                raise ValueError("generations is below the generations already finished")
            config.generations = generations
            ledger.set_generations(run_id, generations, config.to_json())
            row = ledger.get_run(run_id)
        if row["status"] == "complete" and row["completed_generations"] >= row["generations"]:
            print(f"run {run_id} is already complete", flush=True)
            return run_id
        repo = Repo.open(folder / "specimen")
        _recover(ledger, repo, folder, run_id, config)
        texts = load_archive_texts(folder / "archive")
        start = int(ledger.get_run(run_id)["completed_generations"]) + 1
        _announce(config, run_id)
        _advance(
            config,
            ledger,
            repo,
            folder,
            run_id,
            start,
            provider or make_provider(config.provider),
            texts,
        )
        ledger.set_status(run_id, "complete")
        path = write_report_file(ledger, folder)
        print(f"report {path}", flush=True)
    except BaseException:
        ledger.set_status(run_id, "interrupted")
        raise
    finally:
        ledger.close()
    return run_id


def _announce(config: ExperimentConfig, run_id: str) -> None:
    print(
        f"pegmatite run {run_id} seed {config.seed} "
        f"provider {config.provider} runner {config.runner}",
        flush=True,
    )
    if config.provider == "scripted":
        print("scripted provider is an offline stand-in, not a model result", flush=True)
    if config.provider == "openai" and config.runner == "local":
        print(
            "warning: model commands will execute on the host; prefer --runner docker",
            file=sys.stderr,
            flush=True,
        )


def _new_run_id(seed: int, runs_root: Path) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    base = f"{seed}-{stamp}"
    candidate = base
    suffix = 2
    while (runs_root / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _store_settings(ledger: Ledger, run_id: str, config: ExperimentConfig) -> None:
    formula = (
        "efficiency = clamp(median_consumption / consumption, 0, resource_cap) / resource_cap; "
        "consumption 0 uses the cap; median is the even-aware median of successful "
        "non-gamed training attempts in the generation"
    )
    mapping = {key: json.dumps(value) for key, value in config.fitness.as_dict().items()}
    mapping["shock_generation"] = json.dumps(config.shock_generation)
    mapping["shock_fallback_path"] = json.dumps(config.shock_fallback_path)
    mapping["resource_formula"] = json.dumps(formula)
    ledger.insert_settings(run_id, mapping)


def _recover(ledger: Ledger, repo: Repo, folder: Path, run_id: str, config: ExperimentConfig) -> None:
    work = folder / "work"
    if work.exists():
        for child in list(work.iterdir()):
            repo.remove_worktree(child)
    open_gen = ledger.open_generation(run_id)
    if not open_gen:
        return
    generation = int(open_gen["generation"])
    shas = [
        row["commit_sha"]
        for row in ledger.rows(
            "SELECT commit_sha FROM commits WHERE run_id = ? AND generation = ?",
            (run_id, generation),
        )
    ]
    repo.hard_reset(open_gen["start_sha"])
    ledger.delete_generation(run_id, generation)
    archive = folder / "archive"
    for sha in shas:
        dest = archive / sha
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
    refresh_reuse_fitness(ledger, run_id, config.fitness)


def _advance(config, ledger, repo, folder, run_id, start_gen, provider, archive_texts) -> None:
    training, heldout = load_ecology(config.ecology)
    if config.task_ids:
        wanted = set(config.task_ids)
        training = tuple(task for task in training if task.id in wanted)
        if {task.id for task in training} != wanted:
            missing = sorted(wanted - {task.id for task in training})
            raise ValueError(f"unknown task ids: {missing}")
    by_id = {task.id: task for task in training}
    schedule = training_schedule(config.seed, training)
    shock = make_shock(config.shock)
    home = folder / "agent-home"

    def sandbox_factory():
        return make_sandbox(config.runner, config.limits, home)

    for generation in range(start_gen, config.generations + 1):
        ledger.mark_generation_start(run_id, generation, repo.head())
        if config.shock_generation and generation == config.shock_generation:
            _apply_shock(shock, repo, ledger, config, run_id, generation)
        for index in range(config.n_agents):
            task = by_id[task_id_for(schedule, generation, index, config.n_agents)]
            run_episode(
                config,
                ledger,
                repo,
                sandbox_factory,
                provider,
                folder,
                run_id,
                generation,
                f"a{index}",
                index,
                task,
                "train",
                archive_texts,
                record_archive=True,
            )
        _score_generation(
            config, ledger, repo, provider, sandbox_factory, run_id, generation, "train"
        )
        if generation % config.heldout_every == 0:
            for task in heldout:
                dest = folder / "work" / f"g{generation}-{task.id}"
                repo.add_worktree(dest)
                probe = Repo.open(dest)
                try:
                    run_episode(
                        config,
                        ledger,
                        probe,
                        sandbox_factory,
                        provider,
                        folder,
                        run_id,
                        generation,
                        "probe",
                        90,
                        task,
                        "heldout",
                        archive_texts,
                        record_archive=False,
                    )
                finally:
                    repo.remove_worktree(dest)
            _score_generation(
                config, ledger, repo, provider, sandbox_factory, run_id, generation, "heldout"
            )
        ledger.mark_generation_finished(run_id, generation)
        print(f"generation {generation} checkpoint", flush=True)


def _apply_shock(shock, repo, ledger, config, run_id, generation) -> None:
    plan = shock.plan(
        repo,
        ledger,
        run_id,
        generation,
        config.seed,
        config.shock_fallback_path,
    )
    # The row is committed before the rename and before this generation's agents run.
    row_id = ledger.insert_shock(
        run_id=run_id,
        shock_id=plan["shock_id"],
        generation=generation,
        shock_type=plan["shock_type"],
        old_path=plan["old_path"],
        new_path=plan["new_path"],
        origin_commit=plan["origin_commit"],
        commit_sha=None,
        applied=0,
        reason=plan["reason"],
        detail_json=json.dumps(plan),
    )
    sha = shock.execute(repo, plan, git_date(config.seed, generation, 80, 0))
    if sha:
        ledger.update_shock(row_id, sha, 1)
        meta = repo.commit_meta(sha)
        ledger.insert_commit(
            run_id=run_id,
            generation=generation,
            agent_id="shock",
            commit_sha=meta["sha"],
            parent_sha=meta["parent_sha"],
            task_id=None,
            episode_id=None,
            timestamp=meta["timestamp"],
            token_usage=0,
            wall_time_s=0.0,
            fitness=None,
            message=meta["message"],
        )
        ledger.commit()
        print(f"shock {plan['shock_id']} {plan['old_path']} -> {plan['new_path']}", flush=True)
    else:
        ledger.commit()
        print(f"shock {plan['shock_id']} not applied ({plan['reason']})", flush=True)


def _record_observations(
    ledger,
    repo,
    run_id,
    generation,
    episode_id,
    agent_id,
    task_id,
    parent,
    commands,
    touched,
) -> None:
    """Availability, inspection, invocation, modification, dependency, and checker execution.

    Only an agent import or an agent invocation of a file that already existed
    counts toward reuse. The harness running ENTRY does not.
    """
    for path in repo.tracked_at(parent):
        ledger.insert_observation(
            run_id=run_id,
            generation=generation,
            episode_id=episode_id,
            role="availability",
            path=path,
            evidence="present at episode start",
            blob_sha=repo._git("rev-parse", f"{parent}:{path}", check=False).stdout.strip(),
            counts_as_reuse=0,
        )
    for command in commands:
        for role, path, evidence in classify_command(command):
            if role == "invocation":
                if not path or not repo.exists_at(parent, path):
                    continue
                source = source_episode(ledger, repo, run_id, parent, path, episode_id)
                if source is None:
                    continue
                ledger.insert_reuse(
                    run_id=run_id,
                    generation=generation,
                    consumer_agent=agent_id,
                    consumer_episode=episode_id,
                    consumer_task=task_id,
                    producer_episode=source["episode_id"],
                    producer_commit=source["commit_sha"],
                    producer_path=path,
                    evidence=evidence,
                    kind="invocation",
                )
                ledger.insert_observation(
                    run_id=run_id,
                    generation=generation,
                    episode_id=episode_id,
                    role="invocation",
                    path=path,
                    evidence=evidence,
                    producer_episode=source["episode_id"],
                    producer_commit=source["commit_sha"],
                    counts_as_reuse=1,
                )
                continue
            ledger.insert_observation(
                run_id=run_id,
                generation=generation,
                episode_id=episode_id,
                role=role,
                path=path,
                evidence=evidence,
                counts_as_reuse=0,
            )
    for path, evidence in import_dependencies(repo, parent, sorted(touched)):
        source = source_episode(ledger, repo, run_id, parent, path, episode_id)
        if source is None:
            continue
        ledger.insert_reuse(
            run_id=run_id,
            generation=generation,
            consumer_agent=agent_id,
            consumer_episode=episode_id,
            consumer_task=task_id,
            producer_episode=source["episode_id"],
            producer_commit=source["commit_sha"],
            producer_path=path,
            evidence=evidence,
            kind="dependency",
        )
        ledger.insert_observation(
            run_id=run_id,
            generation=generation,
            episode_id=episode_id,
            role="dependency",
            path=path,
            evidence=evidence,
            producer_episode=source["episode_id"],
            producer_commit=source["commit_sha"],
            counts_as_reuse=1,
        )
    entry = repo.file_at(repo.head(), "ENTRY") or ""
    first = next((line.strip() for line in entry.splitlines() if line.strip()), "")
    for path in evaluator_targets(entry) or ([""] if first else []):
        ledger.insert_observation(
            run_id=run_id,
            generation=generation,
            episode_id=episode_id,
            role="evaluator_execution",
            path=path,
            evidence=first,
            counts_as_reuse=0,
        )


def run_episode(
    config,
    ledger,
    repo,
    sandbox_factory,
    provider,
    folder: Path,
    run_id: str,
    generation: int,
    agent_id: str,
    agent_index: int,
    task,
    phase: str,
    archive_texts: list[str],
    record_archive: bool,
) -> int:
    parent = repo.head()
    episode_id = ledger.begin_episode(
        run_id=run_id,
        generation=generation,
        agent_id=agent_id,
        task_id=task.id,
        phase=phase,
        parent_sha=parent,
    )
    date = git_date(config.seed, generation, agent_index, 1)
    repo.set_author(agent_id)
    sandbox = sandbox_factory()
    commands: list[str] = []
    tokens = 0
    tool_calls = 0
    started = time.perf_counter()
    provider_error = None
    limits = config.limits
    try:
        sandbox.start(repo.path, agent_id, date)
        before_tree = snapshot_tree(repo.path)
        parent_entry = repo.file_at(parent, "ENTRY") or ""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_message(
                    agent_id, generation, task.id, task.public_text(), limits
                ),
            },
        ]
        corrected = False
        while True:
            elapsed = time.perf_counter() - started
            if tool_calls >= limits.max_tool_calls or tokens >= limits.max_tokens or elapsed >= limits.max_wall_s:
                break
            try:
                completion = provider.complete(messages, max_tokens=max(1, limits.max_tokens - tokens))
            except Exception as exc:
                provider_error = str(exc)
                print(f"{agent_id} provider error: {provider_error}", flush=True)
                break
            tokens += completion.tokens_in + completion.tokens_out
            ledger.insert_llm(
                run_id=run_id,
                episode_id=episode_id,
                tokens=completion.tokens_in + completion.tokens_out,
                request_json=json.dumps(messages),
                response_text=completion.text,
            )
            messages.append({"role": "assistant", "content": completion.text})
            action = parse_action(completion.text)
            if action is None or action.get("tool") not in {"shell", "done"}:
                if not corrected:
                    corrected = True
                    messages.append({"role": "user", "content": "Respond with one JSON object only."})
                    continue
                break
            if action["tool"] == "done":
                break
            command = action.get("cmd")
            if not isinstance(command, str) or not command.strip() or len(command) > 20_000:
                break
            remaining = limits.max_wall_s - (time.perf_counter() - started)
            if remaining <= 0:
                break
            tool_calls += 1
            result = sandbox.run(command, timeout=min(limits.tool_timeout_s, max(0.2, remaining)))
            commands.append(command)
            ledger.insert_tool(
                episode_id=episode_id,
                seq=tool_calls,
                cmd=command,
                exit_code=result.exit_code,
                stdout_excerpt=clip(result.stdout, 2000),
                stderr_excerpt=clip(result.stderr, 2000),
            )
            messages.append(
                {
                    "role": "user",
                    "content": tool_message(
                        result.exit_code,
                        clip(result.stdout, limits.max_output_chars),
                        clip(result.stderr, limits.max_output_chars),
                    ),
                }
            )
        sandbox.run(
            "git add -A && (git diff --cached --quiet || git commit --allow-empty-message -m '')",
            timeout=limits.tool_timeout_s,
        )
        evaluation = evaluate(sandbox, task, limits)
        head = repo.head()
        notes = quality_notes(repo, parent, head, evaluation.detail)
        if provider_error:
            notes["provider_error"] = provider_error[:500]
    finally:
        sandbox.stop()

    after_tree = snapshot_tree(repo.path)
    touched = touched_paths(before_tree, after_tree)
    for command in commands:
        for role, path, _evidence in classify_command(command):
            if role == "modification" and path:
                touched.add(path)

    wall = time.perf_counter() - started
    head = repo.head()
    changed = repo.changed(parent, head)
    contributed = "\n".join((repo.file_at(head, path) or "") for path in changed)
    novel = novelty_of(contributed, archive_texts)
    used = consumption(tokens, tool_calls, wall, limits, config.fitness)
    hit = None
    if phase == "train":
        hit = audit(repo, task, limits, sandbox_factory, evaluation.correctness >= 1.0)
    gamed = hit is not None
    if hit:
        notes["gaming"] = hit
    attributable = False
    inherited = False
    if not gamed and phase == "train" and evaluation.correctness >= 1.0:
        if config.ecology == "exp3":
            attributable, closure = candidate_attributable(
                repo, parent, parent_entry, touched, commands, task, limits, sandbox_factory
            )
            notes["stale_entry"] = closure.stale_entry
            notes["keep"] = sorted(closure.keep)
            notes["routed_existing"] = list(closure.routed_existing)
        else:
            attributable = counterfactual_passes(
                repo, parent_entry, touched, task, limits, sandbox_factory
            )
        inherited = not attributable
    elif not gamed and phase != "train":
        attributable = evaluation.correctness >= 1.0
    notes["touched"] = sorted(touched)
    notes["attributable"] = attributable
    notes["inherited_executable"] = inherited
    survived = evaluation.correctness >= 1.0 and attributable and not gamed
    new_commits = repo.commits_since(parent)
    commit_sha = new_commits[-1]["sha"] if new_commits else None
    ledger.finish_episode(
        episode_id,
        token_usage=tokens,
        tool_calls=tool_calls,
        wall_time_s=round(wall, 6),
        commit_sha=commit_sha,
        tests_passed=evaluation.passed,
        tests_total=evaluation.total,
        correctness=evaluation.correctness,
        consumption=used,
        resource_score=None,
        reuse_score=0.0,
        novelty_score=novel,
        fitness=0.0,
        fitness_at_birth=None,
        survived=int(survived),
        gamed=int(gamed),
        attributable=int(attributable),
        quality_json=json.dumps(notes),
    )
    if hit:
        ledger.insert_antigaming(
            run_id=run_id,
            generation=generation,
            episode_id=episode_id,
            commit_sha=commit_sha,
            trigger=hit["trigger"],
            reason=hit["reason"],
        )
    for meta in new_commits:
        ledger.insert_commit(
            run_id=run_id,
            generation=generation,
            agent_id=agent_id,
            commit_sha=meta["sha"],
            parent_sha=meta["parent_sha"],
            task_id=task.id,
            episode_id=episode_id,
            timestamp=meta["timestamp"],
            token_usage=tokens,
            wall_time_s=round(wall, 6),
            fitness=0.0,
            message=meta["message"],
        )
    for path in changed:
        full = repo.path / path
        if not full.is_file():
            continue
        ledger.insert_artifact(
            run_id=run_id,
            episode_id=episode_id,
            commit_sha=commit_sha or head,
            path=path,
            blob_sha=repo.blob_sha(path),
            generation=generation,
            agent_id=agent_id,
            task_id=task.id,
            archived=0,
            pruned=0 if survived else 1,
        )
    if survived and record_archive and commit_sha:
        archive_paths(
            repo,
            folder / "archive",
            run_id,
            commit_sha,
            changed,
            archive_texts,
        )
        ledger.conn.execute(
            "UPDATE artifacts SET archived = 1 WHERE episode_id = ? AND pruned = 0",
            (episode_id,),
        )
    if not survived:
        restored = repo.restore_tree(parent, "harness", git_date(config.seed, generation, agent_index, 7))
        if restored:
            meta = repo.commit_meta(restored)
            ledger.insert_commit(
                run_id=run_id,
                generation=generation,
                agent_id="harness",
                commit_sha=meta["sha"],
                parent_sha=meta["parent_sha"],
                task_id=None,
                episode_id=None,
                timestamp=meta["timestamp"],
                token_usage=0,
                wall_time_s=0.0,
                fitness=None,
                message=meta["message"],
            )
    _record_observations(
        ledger,
        repo,
        run_id,
        generation,
        episode_id,
        agent_id,
        task.id,
        parent,
        commands,
        touched,
    )
    added, deleted, files = diff_records(repo, parent, touched)
    ledger.insert_episode_diff(
        episode_id=episode_id,
        run_id=run_id,
        start_commit=parent,
        end_commit=commit_sha or head,
        parent_commit=parent,
        files_changed=len(files),
        lines_added=added,
        lines_deleted=deleted,
        attributable=int(attributable),
        inherited_executable=int(inherited),
        diff_json=json.dumps(files),
    )
    ledger.commit()
    refresh_reuse_fitness(ledger, run_id, config.fitness)
    print(
        f"gen {generation} {phase} {agent_id} {task.id} "
        f"pass {evaluation.passed}/{evaluation.total} "
        f"gamed {int(gamed)} attributable {int(attributable)} survive {int(survived)}",
        flush=True,
    )
    return episode_id


def _score_generation(config, ledger, repo, provider, sandbox_factory, run_id, generation, phase) -> None:
    del sandbox_factory
    rows = ledger.rows(
        """
        SELECT * FROM episodes
        WHERE run_id = ? AND generation = ? AND phase = ? AND finished_at IS NOT NULL
        """,
        (run_id, generation, phase),
    )
    if phase == "train":
        successes = [
            row
            for row in rows
            if row["correctness"] >= 1 and row["attributable"] and not row["gamed"]
        ]
        med = median([float(row["consumption"] or 0.0) for row in successes])
        _sample_explanations(config, ledger, repo, provider, run_id, generation)
    else:
        stored = ledger.rows(
            """
            SELECT median_consumption FROM generation_stats
            WHERE run_id = ? AND generation = ? AND phase = 'train'
            """,
            (run_id, generation),
        )
        med = float(stored[0]["median_consumption"]) if stored else 0.0
        successes = [
            row
            for row in rows
            if row["correctness"] >= 1 and row["attributable"] and not row["gamed"]
        ]
    ledger.insert_generation_stat(
        run_id=run_id,
        generation=generation,
        phase=phase,
        success_count=len(successes),
        median_consumption=med,
    )
    for row in rows:
        ledger.set_resource(
            row["id"],
            resource_efficiency(float(row["consumption"] or 0.0), med, config.fitness),
        )
    ledger.commit()
    refresh_reuse_fitness(ledger, run_id, config.fitness)
    ledger.seal_birth(run_id, generation, phase)
    ledger.commit()


def _sample_explanations(config, ledger, repo, provider, run_id, generation) -> None:
    artifacts = ledger.rows(
        """
        SELECT a.path, a.commit_sha, a.episode_id
        FROM artifacts a
        JOIN episodes e ON e.id = a.episode_id
        WHERE a.run_id = ? AND a.generation = ? AND a.archived = 1 AND a.pruned = 0
          AND e.phase = 'train' AND e.survived = 1 AND e.gamed = 0
        """,
        (run_id, generation),
    )
    every = config.fitness.explainability_every
    worst: dict[int, float] = {}
    for artifact in artifacts:
        sampled = is_sampled(config.seed, artifact["commit_sha"], artifact["path"], every)
        score = None
        explanation = ""
        if sampled:
            body = repo.file_at(artifact["commit_sha"], artifact["path"]) or ""
            _used, score, explanation = explain(provider, body, "", None, config.fitness)
            episode_id = artifact["episode_id"]
            worst[episode_id] = score if episode_id not in worst else min(worst[episode_id], score)
        ledger.insert_explainability(
            run_id=run_id,
            generation=generation,
            episode_id=artifact["episode_id"],
            commit_sha=artifact["commit_sha"],
            path=artifact["path"],
            sampled=int(sampled),
            sample_key=sample_key(config.seed, artifact["commit_sha"], artifact["path"]),
            explainer="fresh",
            explanation=explanation,
            score=score,
        )
    for episode_id, score in worst.items():
        ledger.set_explainability(episode_id, 1, score)


def write_report_file(ledger: Ledger, folder: Path):
    from ledger.report import write_report

    return write_report(ledger, folder)
