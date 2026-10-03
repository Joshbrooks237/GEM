# Pegmatite

## Status

Pegmatite runs coding agents in one shared Git repository under a token budget and a time budget, and writes each episode to a ledger. Three live runs on seed 42 are stored as complete at generation 50 of 50; the two scripted runs are harness checks and are not evidence. The charts and the write-up are in [docs/index.html](docs/index.html) and [docs/RESULTS.md](docs/RESULTS.md).

Known issues in those ledgers, with the SQL in [docs/RESULTS.md](docs/RESULTS.md):

- The model id is not stored. Explainability was sampled once, on the exp3 run, score 0.0, and the text is a traceback. The anti-gaming table is empty on every live run.
- Every survivor has `resource_score` 0.50. Each generation has at most one gate pass, so that episode is the median.
- Many survivors have `commit_sha` NULL. The tools rewrote a file to the same bytes, `git commit` printed `nothing to commit, working tree clean`, and the row is still counted as survived. On `42-20260930T181703` that is 8 of 18 survivors; on `42-20260930T190140`, 12 of 17; on `42-20260930T221506`, episode 127.
- Episode 107 on `42-20260930T221506` is a scoring bug inside that null-commit count. All four shell commands failed with a syntax error, and a `> ENTRY` in the command text was still treated as a touch, so the existing program was credited (fitness 0.775). The published "4 survivors" includes this row.
- Four other episodes on that run passed every hidden test and scored fitness 0 because `attributable` is 0. That is the exp3 keep-set rule: an inherited `ENTRY` target that the episode did not touch does not score. Mean correctness counts them; mean fitness and `survived` do not.
- Every stored run uses seed 42. One seed is an anecdote.

Pegmatite is a reproducible scarcity experiment. Coding agents share one Git repository and solve small programs under a hard token budget and a hard time budget. The question is not how to design a language. The question is which habits survive.

> Given the same initial conditions, task distribution, resource constraints, model, and shocks, what software conventions spontaneously persist?

The name is the rock. Pegmatite grows unusually large crystals when a melt cools under the right pressure. This harness does the same job for code: it applies pressure, keeps the lineage, and refuses to hand the agents a style guide.

Agents may inspect the shared repository and reuse whatever they find. They are not told the fitness formula, and they are not required to adopt a framework, a naming scheme, a commit format, or a documentation style. If a convention shows up, it showed up because it was useful under the budget.

## Run

Python 3.11 or newer.

```bash
python -m pip install -r requirements.txt
python cli.py run --seed 42
python cli.py resume <run_id>
python cli.py report <run_id>
python cli.py compare <run_a> <run_b>
```

The default run is 3 agents and 50 generations. `--provider scripted` needs no API key. It is a fixed offline stand-in so the harness can be checked. A scripted run is not evidence that a convention emerged.

A live model uses an OpenAI-compatible endpoint. The Docker sandbox is the default for that provider: it mounts only the specimen, drops network access, and does not receive the API key.

```bash
export PEGMATITE_API_KEY=...
export PEGMATITE_MODEL=gpt-4o-mini   # optional
python cli.py run --seed 42 --provider openai
```

`PEGMATITE_BASE_URL` overrides `https://api.openai.com/v1`. `--runner local` executes model commands on the host. Do not use it for an untrusted model.

Knobs: `--generations`, `--agents`, `--shock-generation` (default 25; `0` turns the shock off), `--heldout-every`, `--run-dir`. Fitness weights are per-run flags (`--base-pass`, `--resource-weight`, `--reuse-weight`, `--explainability-weight`, `--resource-cap`). The values used for a run are written down at the start and do not change afterward.

## What is held fixed

Only the apparatus is fixed:

- tasks are stdin in, stdout out, checked by hidden cases the agent does not see
- a one-line `ENTRY` command tells the checker what to run
- token and wall-clock budgets are hard caps
- Git is the history of the specimen
- one rename shock fires at generation 25, before that generation's agents run
- held-out tasks run in a detached worktree and are not merged back

Everything else is for the agents to invent: file layout, names, commit messages, helpers, and whether anything is reused at all. Reuse is measured afterward from imports and invocations. Leaving a file in the repository does not count.

## How a run is scored

Each attempt stores its components separately. A failed hidden-test gate scores 0. Resource use, reuse, and explainability cannot rescue a failure.

| component | role |
| --- | --- |
| correctness | 1 only when every hidden case passes |
| resource | consumption compared with the median of successful attempts in that generation, then capped |
| reuse | saturates as later episodes import or invoke the artifact |
| explainability | a seeded sample of about one archived artifact in ten, read by an agent that did not write it |
| novelty | distance from the archive; recorded, not scored |

The default, fixed for a run, is:

`fitness = 0.60 + 0.15 * resource + 0.15 * reuse + 0.10 * explainability`

when the gate passes and the attempt is not gaming the checker. Resource efficiency is `clamp(median / consumption, 0, 2) / 2`. An attempt that spends nothing is treated as fully efficient, up to that cap. Artifacts that were not sampled for explainability get the benefit of the doubt. A gamed attempt scores 0. The rest of the generation stays.

Later reuse can raise fitness. It does not move `fitness_at_birth`, which is sealed when the generation is scored.

Failed attempts stay in `git log` and leave the worktree by a later commit (`author=harness`). The shock commits as `author=shock`. Agent commit messages are stored as written.

## The shock

At generation 25 the harness renames the most-reused surviving artifact that is still in the worktree. If nothing has been reused, it uses a fixed fallback path when that path exists. The old path, the new path, the origin commit, and the shock id are recorded before the agents of that generation run. Git history is not rewritten. The point is to see whether the population can adapt when an established dependency breaks, not to tell it how to repair one.

## What a run leaves behind

`runs/<run_id>/` is local and is not part of this repository.

- `specimen/` — the lattice, a Git repository (`/commons` inside Docker)
- `ledger.sqlite` — episodes, component scores, commits, artifacts, reuse events, shocks, explainability samples, anti-gaming hits, prompts
- `archive/` — files from attempts that passed
- `report.md` — written when the run completes

Within a generation the agents run one after another, so the specimen history stays a straight line. The seed fixes the task order, the shock, and, for the scripted provider, the commit timestamps. Two scripted runs with the same seed produce the same specimen. Live completions are stored. `resume` continues a killed run and does not repeat a finished generation.

## Tests

```bash
python -m pytest
```

Docker is required only for `--runner docker`.

## License

MIT. See [LICENSE](LICENSE).
