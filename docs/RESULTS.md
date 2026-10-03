# Pegmatite results

Three live runs are on disk, all seed 42, all recorded as finished at generation 50 of 50. One of them applied the rename shock at generation 25. One recorded the shock and did not apply it. One was started with the shock turned off. The model name and any dollar cost are absent from the ledgers. These runs are one seed. That is an anecdote, not a pattern.

`report.md` and `ledger.sqlite` agree on generation count for every run below. Charts of the same numbers are in [index.html](index.html).

## Inventory

Scripted runs are harness checks. They are not evidence.

- `42-20260930T173348`: scripted harness check. Ledger `completed_generations` 50 of 50, 307,315 tokens, scripted completions stored in `llm_calls`. Older schema (`shock_every` 10, five shock rows).
- `42-20260930T175718`: scripted harness check. Ledger 50 of 50, 307,439 tokens, scripted completions stored. `shock_generation` 25, one shock row with `applied` 1.

Live runs (`runs.provider = 'openai'`):

| run | model | generations | tokens | completions stored | shock at the configured generation |
| --- | --- | --- | --- | --- | --- |
| `42-20260930T181703` | not recorded | 50 finished / 50 planned | 293,513 | 757/757 `response_text` rows non-empty | yes. `shock_generation` 25, row `rename-42-25`, `applied` 1, `echo_reverse.py` → `echo_reverse.r25.py` |
| `42-20260930T190140` | not recorded | 50 finished / 50 planned | 309,886 | 790/790 non-empty | no. `shock_generation` 25, row exists, `applied` 0, reason `fallback_absent` |
| `42-20260930T221506` | not recorded | 50 finished / 50 planned | 497,207 | 781/781 non-empty | no. `shock_generation` 0, `shocks` is empty |

Generation count is the same three ways in each ledger: `runs.completed_generations`, 50 `generation_marks` rows with `finished = 1`, and 50 distinct values in `episodes.generation`. Token sums match: `SUM(episodes.token_usage) = SUM(llm_calls.tokens)`.

## Setup

All three live runs used seed 42, 3 agents, 50 generations, provider `openai`, runner `docker`, held-out every 10 generations. Limits stored in `config_json`: 4,000 tokens, 16 tool calls, 90 seconds wall per episode. Fitness weights stored in `settings`: base pass 0.60, resource 0.15, reuse 0.15, explainability 0.10, resource cap 2.0. Unsampled explainability is stored as 1.0.

`42-20260930T181703` and `42-20260930T190140` have `shock_generation` 25 and no `ecology` field. Their training tasks are the small stdin/stdout set (`echo_reverse`, `kv_get`, `max_int`, and the rest of that list). `42-20260930T221506` has `ecology` `exp3` and `shock_generation` 0. Its tasks are the JSON/record set (`serialize`, `filter_dev`, `raw_dev_count`, and the rest).

The model id is not in `config_json`, `settings`, or `llm_calls`. `request_json` is the message list (`role`, `content`) only.

## What the harness records

Each training generation is three episodes, one per agent (`a0`, `a1`, `a2`), in order. Held-out probes use agent `probe` and are not merged. A hidden-test gate sets `correctness` to 1 only when every hidden case passes. Fitness is 0 when that gate fails. Resource, reuse, and explainability are stored on the episode anyway.

On these runs every generation has at most one gate pass. The resource score of every survived episode is 0.50. With one success, the generation median consumption is that episode, the ratio is 1, and efficiency is `1 / resource_cap` = 0.50. An unsampled survivor with reuse 0 then scores `0.60 + 0.15 * 0.50 + 0.10 * 1.0` = 0.775. Many survived rows are exactly that number.

`reuse_score` sits on the episode that produced the file and rises when later episodes import or invoke it. A lower mean `reuse_score` after generation 25 can mean those producers had fewer later consumers, which is true of any late episode. Reuse *events* are the rows in `reuse_events`, dated by the consumer's generation. Those two numbers answer different questions.

Explainability was almost unused. `42-20260930T181703` has 11 `explainability` rows and 0 sampled. `42-20260930T190140` has 6 rows and 0 sampled. `42-20260930T221506` has one sampled row: generation 16, episode 51, path `ENTRY`, score 0.0. The stored explanation begins with a Python traceback. That survivor's fitness is 0.734, which is the 0.775 figure with the 0.10 explainability term removed.

`antigaming` has 0 rows on all three live runs.

The report's held-out "pass" column is `tests_passed/tests_total` for one probe episode. It is not an agent pass rate. Held-out gate passes (`correctness` 1) are 2/15, 2/15, and 0/15. Mean held-out correctness in the reports is 0.133, 0.133, and 0.000, matching `AVG(correctness)`.

## Before and after generation 25

The shock is applied at the start of its generation, before that generation's agents. "Before" is training generations 1–24 (72 episodes). "After" is 25–50 (78 episodes). Only `42-20260930T181703` has an applied rename in that slot. The other two splits are the same cut through runs where no rename happened.

### `42-20260930T181703`: rename applied

Shock row `rename-42-25`, generation 25, `applied` 1, reason `most_reused`. `echo_reverse.py` → `echo_reverse.r25.py`. Origin commit `2b683472b275` (generation 10, agent `a1`, message `Add echo_reverse program`). Rename commit `408f770c3076`, author `shock`, empty message. The specimen diff is a rename with 0 insertions and 0 deletions.

Training episodes, from the ledger:

| | episodes | gate passes | survived | mean fitness | mean correctness | mean resource | mean reuse_score | mean novelty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| generations 1–24 | 72 | 11 | 11 | 0.131 | 0.153 | 0.268 | 0.086 | 0.645 |
| generations 25–50 | 78 | 7 | 7 | 0.071 | 0.090 | 0.165 | 0.013 | 0.617 |
| all training | 150 | 18 | 18 | 0.100 | 0.120 | 0.214 | 0.048 | 0.631 |

All 18 survived episodes have `task_id` `echo_reverse`. The other tasks in this run did not survive. Generation 25 itself is 0/3.

Reuse events: 56, every one `kind = invocation`, `producer_path = echo_reverse.py`, `evidence = python3 echo_reverse.py`. 26 of those events are in generations 1–24 and 30 are in generations 25–50. None name `echo_reverse.r25.py`.

Mean fitness is lower after generation 25 mostly because fewer episodes pass (11/72 versus 7/78). The 11 survived episodes before the cut have fitness from 0.775 to 0.913. The 7 after it are 0.925 once (generation 26) and 0.775 six times. The 0.775 rows are the no-reuse formula above. Later producers have had less time to collect reuse credit.

Files after the rename, from the specimen Git history (read-only):

- Commits after the rename that change `echo_reverse.py`: `5ec38a598bdd` (generation 26, `a2`), `4616617eb3b5` (generation 29, `a0`), `3f46758305e5` (generation 38, `a1`), `b7a8a820ecde` (generation 40, `a2`), `23bfa6f904ee` (generation 50, `a0`). That is the file history. It is not a finding that the agents repaired the rename.
- HEAD contains `ENTRY`, `echo_reverse.py`, `echo_reverse.r25.py`, and `output.txt`.
- `ENTRY` is the line `python3 echo_reverse.py`.
- `echo_reverse.py` and `echo_reverse.r25.py` are the same one-liner: `import sys; print(sys.stdin.read().strip()[::-1])`.

8 of the 18 survived episodes have `commit_sha` NULL (episodes 8, 22, 77, 101, 108, 139, 146, 153). They are inside the 18 and inside the fitness means. On each of those eight episodes `git commit` exited 1 with `nothing to commit, working tree clean`. Episode 8's tools rewrote `echo_reverse.py` and `ENTRY` before that commit, and `quality_json` has `changed` `[]`. This ledger has no `attributable` column and no `touched` field, so the same-byte reading is from those tool rows and the empty diff, not from an attribution flag.

This is one run. It shows what this seed did around one rename. It does not show that a habit persisted.

### `42-20260930T190140`: shock row, rename not applied

Same flags as the run above, including `shock_generation` 25. The shock row names `fallback-artifact` → `fallback-artifact.r25`, `applied` 0, reason `fallback_absent`, and both commit columns are NULL. The specimen history has no author `shock`.

`reuse_events` has 0 rows. Mean reuse is 0.000 on both sides of generation 25.

| | episodes | gate passes | survived | mean fitness | mean correctness | mean resource | mean reuse_score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| generations 1–24 | 72 | 9 | 9 | 0.097 | 0.125 | 0.226 | 0.000 |
| generations 25–50 | 78 | 8 | 8 | 0.079 | 0.103 | 0.167 | 0.000 |
| all training | 150 | 17 | 17 | 0.088 | 0.113 | 0.196 | 0.000 |

All 17 survived episodes are `echo_reverse`, and each has fitness 0.775 (resource 0.50, reuse 0, explainability unsampled). The generation-mean fitness moves with the pass rate only. 12 of those 17 have `commit_sha` NULL. Their `quality_json` lists `touched` as `ENTRY` and `echo_reverse.py`, `changed` is `[]`, and `episode_diffs` has `lines_added` 0 and `lines_deleted` 0 with `start_commit` equal to `end_commit`. Episode 8's `git commit` stdout is `nothing to commit, working tree clean`. Those 12 rows stay in the survived count and in the 0.775 fitness.

HEAD is `ENTRY` (`python3 echo_reverse.py`) and `echo_reverse.py` (the same one-liner as the other run). The shock row did not rename a file.

### `42-20260930T221506`: shock turned off

`shock_generation` is 0 and `shocks` has no rows. A cut at generation 25 is not a before/after shock. For the record, training generations 1–24 had 2 gate passes and 1 survivor (mean fitness 0.010). Generations 25–50 had 6 gate passes and 3 survivors (mean fitness 0.030). The whole run is 8 gate passes and 4 survivors out of 150, mean fitness 0.020, mean correctness 0.053, mean reuse 0.003.

The ledger counts 4 survivors, all `raw_dev_count`. Two of them have `commit_sha` NULL. Episode 127 rewrote `raw_dev_count.py` and `ENTRY` with the same bytes: `git commit` printed `nothing to commit, working tree clean`, `touched` is those two paths, and `lines_added` is 0. Episode 107 is different: all four shell commands exited 2 with a bash syntax error, the redirects to `ENTRY` did not run, and `commit_sha` is NULL. `touched` is still `['ENTRY']` because the command text contains `> ENTRY`. `routed_existing` is `raw_dev_count.py`, `attributable` is 1, and fitness is 0.775. That row is what the ledger stored. These runs predate the exit-code check. See Corrected for episode 107.

Four other episodes passed all 4 hidden tests and still have fitness 0 and `survived` 0: episodes 61, 117, 150, and 160 (generations 20, 36, 46, and 50). Their `quality_json` has `stale_entry` true and `attributable` 0, and `commit_sha` is NULL. Episodes 61, 150, and 160 have no tool calls and `touched` `[]`. Episode 117's commands also failed to parse; the classifier marked `program.sh`, which is not the `ENTRY` target, and the keep-set stayed empty. The report's generation row can show mean correctness 0.333 and mean fitness 0.000 at the same time. That is these four rows. Fitness uses attributable correctness; the `correctness` column keeps the raw gate.

One reuse event: generation 23, agent `a1`, task `raw_dev_count`, path `raw_dev_count.py`, kind `invocation`. The evidence text is 240 characters and starts `echo 'import sys`.

### Corrected for episode 107

The counts above are the stored ledger values. Those runs predate the fix: a command now counts as modifying a path only when it exits 0, so a failed redirect no longer adds `ENTRY` to `touched`. Applying that rule to episode 107 drops its fitness 0.775. Survivors become 3 of 150. Training mean fitness becomes 0.015 (`(3.059 - 0.775) / 150`). Generations 25–50 become 2 survivors and mean fitness 0.020 (`(2.325 - 0.775) / 78`). Generations 1–24 stay 1 survivor and mean fitness 0.010. Mean correctness stays 0.053, because the hidden tests on that episode still passed.

## What the agents wrote

Observations from these three runs only. One seed. Not a claim that a convention emerged or persisted.

Flat trees. HEAD of each live specimen is a handful of files in the repo root. No subdirectory.

`ENTRY` is one line naming a Python file: `python3 echo_reverse.py` on the first two runs, `python3 raw_dev_count.py` on the third.

Most paths in the artifacts table are the task id plus an extension. Some names differ, and those rows were pruned. On `42-20260930T181703` the artifacts table has 6 rows for `palindrome.py` (kept 0) beside 15 for `is_palindrome.py` (kept 0). On `42-20260930T190140` those counts are 7 and 14, all pruned. On `42-20260930T221506`, `aggregate_years.sh` has 10 rows, all pruned, next to Python files such as `validate.py` and `filter_dev.py`. `helper.py` does not appear in the live artifact tables.

Commit subjects, agent authors only (`agent_id` not `harness` or `shock`):

- `42-20260930T181703`: repeated sentence subjects, including 14× `Add word counting program`, 14× `Add palindrome checker`, 8× `Add echo_reverse program`. Wording is not stable (`Add word count program` also appears 7 times).
- `42-20260930T190140`: 18× `Add palindrome checker`, 13× `Add word counting program`, 13× `Implement unique_keep function to output distinct tokens in order`.
- `42-20260930T221506`: 31 commits with an empty message, then 15× `Add filter_dev script to filter JSON objects by role`, 14× `Add JSON validation script`, 13× `Add aggregate_years script`.

Harness commits are the majority on every live run (109, 115, and 95 rows). Those are the harness, not an agent style.

## Cost

No dollar amount is stored. No model id is stored, so these tokens are not converted to a price here.

| run | all episodes | training | held-out | training tokens per episode |
| --- | --- | --- | --- | --- |
| `42-20260930T181703` | 293,513 | 272,318 | 21,195 | 272,318 / 150 = 1,815 |
| `42-20260930T190140` | 309,886 | 287,734 | 22,152 | 287,734 / 150 = 1,918 |
| `42-20260930T221506` | 497,207 | 441,767 | 55,440 | 441,767 / 150 = 2,945 |

Per agent across 50 training episodes: on `42-20260930T181703`, `a0` 92,352, `a1` 89,224, `a2` 90,742. On `42-20260930T190140`, `a0` 93,416, `a1` 89,105, `a2` 105,213. On `42-20260930T221506`, `a0` 154,310, `a1` 139,530, `a2` 147,927. Held-out tokens are extra, on generations 10, 20, 30, 40, and 50.

Episode `wall_time_s` sums to 1,195.3, 1,002.6, and 1,447.9 seconds. `runs.created_at` to `updated_at` spans about 22, 19, and 26 minutes.

Training tokens by generation did not climb steadily. Mean training tokens in generations 1–10 versus 41–50: 5,326 versus 5,136 on the first live run, 5,356 versus 6,214 on the second (about 16% higher), 8,714 versus 8,158 on the exp3 run.

A new 50-generation run with the same 3 agents and the same small-task setup as the first two live runs has a measured band of 293,513 to 309,886 tokens if it behaves like those two. If every generation cost what generations 41–50 cost on `42-20260930T190140`, training alone would be about `6,214 * 50 = 310,700`, and with held-out on the order of the 22,152 already seen the total would still sit near the top of that band. Stretching the higher full-run total by that same 16% is about `309,886 * 1.16 ≈ 360,000`. That 16% is one run's late-versus-early gap, not a fitted growth curve. The exp3 run (497,207 tokens) is a different task set and is not the estimate for the small-task setup.

A 12-generation run, using the tokens actually spent in generations 1–12 of the two small-task live runs (training plus the generation-10 probe): 70,014 and 69,952. Those generations were still before a generation-25 shock, so they estimate a short run only if early-generation token use repeats. Applying the 16% allowance gives about 81,000. The exp3 generations 1–12 cost 115,201 tokens.

## Known issues

These are limits of the ledgers and of the scoring rules. The tables above still match the stored rows.

- Model id is not recorded. `insert_llm` stores the message list, not the model field. A scan of `request_json` and `response_text` does not contain a model name. Do not treat the code default as the model that ran.
- Explainability was sampled once, on `42-20260930T221506`, episode 51, path `ENTRY`, score 0.0. The explanation is a traceback (`NameError: name 'print' is not defined` in `raw_dev_count.py`). That row is why this survivor's fitness is 0.734 rather than 0.775. The other live runs have `SUM(sampled) = 0` (11 rows and 6 rows).
- `antigaming` has 0 rows on all three live runs. An empty table is not a finding that no attempt matched a marker.
- Every survived training episode has `resource_score` 0.50 (18, 17, and 4 rows). Each generation has at most one gate pass, so that episode's consumption is the median, the ratio is 1, and `resource_efficiency` is `1 / resource_cap` with `resource_cap` 2.
- Survivors with `commit_sha` NULL are mostly an intended consequence of a same-byte rewrite. End-of-episode git skips the commit when the index matches HEAD (`git diff --cached --quiet`), and `commits_since` returns `[]` when `parent == HEAD`, so the ledger stores NULL. `42-20260930T181703`: 8 of 18 survivors (episodes 8, 22, 77, 101, 108, 139, 146, 153). `42-20260930T190140`: 12 of 17, with `touched` `ENTRY` and `echo_reverse.py`, `lines_added` 0, `start_commit = end_commit`. `42-20260930T221506` episode 127 is the same shape for `raw_dev_count.py`. Those rows are inside the survived counts and the fitness means. Reading "survived" as "a new commit" overstates how many new programs git stored. The first live ledger has no `attributable` or `touched` column; the same-byte reading there is the tool rows (`git commit` stdout `nothing to commit, working tree clean`) and `changed` `[]`.
- Episode 107 on `42-20260930T221506` is a stored scoring error from before the exit-code check. All four shell commands exited 2, the `> ENTRY` redirects did not run, and the command text was still treated as a touch, so the existing `raw_dev_count.py` was credited (fitness 0.775, `survived` 1). The published counts include that row. The adjusted survivor count and means are under Corrected for episode 107. Old runs were not rewritten.
- Episodes that pass every hidden test and still have fitness 0 because `attributable` is 0 are an intended exp3 rule, not a lost score. On `42-20260930T221506` that is episodes 61, 117, 150, and 160 (generations 20, 36, 46, 50): `correctness` 1, `tests` 4/4, `attributable` 0, `survived` 0, `fitness` 0, `commit_sha` NULL, `stale_entry` true. Three of them have no tool calls. `selection/keepset.py` `candidate_attributable` returns false when `ENTRY` is not in the keep set. `lattice/lineage.py` `refresh_reuse_fitness` then passes correctness 0 into `combine` while the `correctness` column stays 1. That is why generations 20, 36, 46, and 50 show mean correctness 0.333 and mean fitness 0.000, and why the run is "8 gate passes and 4 survivors." Mean correctness 0.053 counts all 8; mean fitness 0.020 and `survived` 4 do not. `42-20260930T190140` has no `correctness = 1` row with `attributable = 0`. `42-20260930T181703` has no `attributable` column.
- One seed only. Every run in `runs/` is seed 42. These comparisons are one anecdote.

```sql
-- (a) hidden tests all passed, fitness 0, attributable 0
SELECT id, generation, tests_passed, tests_total, correctness, attributable, survived, fitness, commit_sha
FROM episodes
WHERE phase = 'train' AND correctness >= 1 AND attributable = 0;

-- (b) survivors with no commit
SELECT id, generation, task_id, fitness, attributable, commit_sha
FROM episodes
WHERE phase = 'train' AND survived = 1 AND commit_sha IS NULL;
```

## Limitations

- One seed, 42, for every run in `runs/`.
- Three live runs, and they are not replicates. Two share the small-task setup and `shock_generation` 25. The third is `ecology` `exp3` with the shock off.
- The model name was not recorded, so these runs cannot be cited as a named model.
- Explainability was sampled once.
- Mean `reuse_score` across a generation cut is not a count of reuse events.
- On the exp3 run, a perfect hidden-test gate can still score fitness 0 when `attributable` is 0.
- A survived episode can have no commit.
- Scripted runs are listed above and are not used in these comparisons.

## Proposed next run

This command has not been run.

```bash
python cli.py run --seed 43 --provider openai --generations 12 --agents 3 --shock-generation 6
```

Expected tokens about 70,000 to 81,000 for the small-task setup, from the assumptions in the cost section. The ledger will still not store the model name or a dollar cost. Write the model down outside the ledger.

That is the cheapest setup that still has a before window and an after window with the same 3 agents as the runs already stored. Generations 1–5 run before the shock. Generations 6–12 run after it. Held-out fires once, at generation 10. Three agents matches the recorded runs, where a generation usually had one gate pass or none (18 generations with a pass out of 50 on the first live run, 17 out of 50 on the second). Fewer agents makes an empty side of the cut more likely.

What it can show: whether a rename is applied on a second seed, which path is renamed, and whether later commits and `reuse_events` still name the old path, over 12 generations.

What it cannot show: that any habit persists, that the generation-25 split on `42-20260930T181703` repeats, or a result for `ecology` `exp3`. On `42-20260930T190140` the configured shock did not apply, because nothing had been reused and `fallback-artifact` was not in the tree. The same outcome is possible here.

A full repeat of the 50-generation, shock-at-25 setup on seed 43 would be the closer replication. Its token band is the 293,513 to 309,886 already measured, with the 360,000 allowance above if you want a cushion. That command has not been run either:

```bash
python cli.py run --seed 43 --provider openai --generations 50 --agents 3 --shock-generation 25
```

## Queries

Run these against `runs/<run_id>/ledger.sqlite`. The first live run is shown; repeat for the other two.

```sql
SELECT provider, generations, completed_generations, status
FROM runs;

SELECT COUNT(*) AS marks, SUM(finished) AS finished,
       MIN(generation), MAX(generation)
FROM generation_marks;

SELECT COUNT(DISTINCT generation) AS episode_generations FROM episodes;

SELECT SUM(token_usage) AS episode_tokens FROM episodes;
SELECT COUNT(*) AS calls, SUM(tokens) AS llm_tokens,
       SUM(CASE WHEN response_text IS NOT NULL AND length(response_text) > 0
                THEN 1 ELSE 0 END) AS nonempty_responses
FROM llm_calls;

SELECT shock_id, generation, old_path, new_path, applied, reason,
       origin_commit, commit_sha
FROM shocks;

SELECT CASE WHEN generation < 25 THEN 'before' ELSE 'after' END AS side,
       COUNT(*) AS episodes,
       SUM(CASE WHEN correctness >= 1 THEN 1 ELSE 0 END) AS gate_passes,
       SUM(survived) AS survived,
       ROUND(AVG(fitness), 3) AS mean_fitness,
       ROUND(AVG(correctness), 3) AS mean_correctness,
       ROUND(AVG(resource_score), 3) AS mean_resource,
       ROUND(AVG(reuse_score), 3) AS mean_reuse,
       ROUND(AVG(novelty_score), 3) AS mean_novelty,
       SUM(token_usage) AS tokens
FROM episodes
WHERE phase = 'train'
GROUP BY 1;

SELECT CASE WHEN generation < 25 THEN 'before' ELSE 'after' END AS side,
       producer_path, kind, evidence, COUNT(*) AS n
FROM reuse_events
GROUP BY 1, 2, 3, 4;

SELECT COUNT(*) FROM antigaming;

SELECT generation, agent_id, task_id, commit_sha, fitness, survived
FROM episodes
WHERE phase = 'train' AND survived = 1
ORDER BY generation, agent_id;
```

Generation series used by the charts:

```sql
SELECT generation,
       ROUND(AVG(fitness), 3),
       ROUND(AVG(correctness), 3),
       ROUND(AVG(resource_score), 3),
       ROUND(AVG(reuse_score), 3),
       ROUND(AVG(novelty_score), 3),
       SUM(token_usage)
FROM episodes
WHERE phase = 'train'
GROUP BY generation
ORDER BY generation;
```

Commit subjects:

```sql
SELECT CASE WHEN message IS NULL OR message = '' THEN '(empty)' ELSE message END,
       COUNT(*)
FROM commits
WHERE agent_id NOT IN ('harness', 'shock')
GROUP BY 1
ORDER BY 2 DESC;
```
