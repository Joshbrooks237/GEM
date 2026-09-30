import ast
import hashlib
import inspect
import os
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from analysis.elements import build_table, dataset_document, load_dataset, parse_weight
from analysis.layer import build_document
from analysis.measure import ONELINER, extract_echo_write, is_inspect, reconstruct_writes, specimen_head
from analysis.render import render
from analysis.structure import median
from selection.fitness import combine
from selection.fitness import median as fitness_median

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "42-20260930T190140"
EXPERIMENT_ROOTS = ("agents", "selection", "ledger", "lattice", "shocks", "tasks", "env")


def test_dataset_file_matches_the_builder():
    assert load_dataset() == dataset_document()


def test_table_has_118_ordered_elements():
    rows = build_table()
    assert len(rows) == 118
    assert [row["atomic_number"] for row in rows] == list(range(1, 119))
    assert len({row["symbol"] for row in rows}) == 118
    assert rows[0]["symbol"] == "H"
    assert rows[-1]["symbol"] == "Og"


def test_known_ciaaw_weights_and_layout():
    rows = {row["atomic_number"]: row for row in build_table()}
    hydrogen = rows[1]["atomic_weight"]
    assert hydrogen["kind"] == "interval"
    assert hydrogen["low"] == pytest.approx(1.00784)
    assert hydrogen["high"] == pytest.approx(1.00811)
    helium = rows[2]["atomic_weight"]
    assert helium["value"] == pytest.approx(4.002602)
    assert helium["uncertainty"] == pytest.approx(0.000002)
    assert rows[2]["group"] == 18 and rows[2]["block"] == "s"
    assert rows[64]["atomic_weight"]["value"] == pytest.approx(157.249)
    assert rows[71]["atomic_weight"]["value"] == pytest.approx(174.96669)
    assert rows[118]["atomic_weight"]["kind"] == "none"
    assert rows[118]["group"] == 18 and rows[118]["period"] == 7
    lanthanides = [row["atomic_number"] for row in rows.values() if row["series"] == "lanthanide"]
    actinides = [row["atomic_number"] for row in rows.values() if row["series"] == "actinide"]
    assert lanthanides == list(range(57, 72))
    assert actinides == list(range(89, 104))
    assert rows[57]["group"] is None and rows[57]["block"] == "f" and rows[57]["period"] == 6
    assert rows[71]["series"] == "lanthanide"
    assert rows[72]["group"] == 4 and rows[72]["series"] is None
    assert rows[103]["series"] == "actinide" and rows[103]["group"] is None
    assert rows[104]["group"] == 4
    assert rows[26]["group"] == 8  # iron
    for row in rows.values():
        assert row["group"] is None or 1 <= row["group"] <= 18
        assert row["block"] in {"s", "p", "d", "f"}
        assert 1 <= row["period"] <= 7


def test_em_dash_is_not_given_a_mass_number():
    parsed = parse_weight("—")
    assert parsed == {"kind": "none", "published": "—"}
    assert "value" not in parsed


def test_echo_reconstruction_and_inspection_classifier():
    write = extract_echo_write(
        "echo 'import sys; print(sys.stdin.read().strip()[::-1])' > echo_reverse.py"
    )
    assert write["kind"] == "write"
    assert write["body"] == ONELINER + "\n"
    broken = extract_echo_write(
        "echo 'import sys\\nprint(sys.stdin.read()[::-1], end=\"\")' > echo_reverse.py"
    )
    assert broken["kind"] == "write"
    assert "\\n" in broken["body"]
    assert extract_echo_write("echo 'def' | rev > echo_reverse.py")["kind"] == "pipeline"
    assert is_inspect("ls") is True
    assert is_inspect("git show HEAD:echo_reverse.py") is True
    assert is_inspect("git commit -m 'Add max_int program to find the maximum'") is False
    files = reconstruct_writes(
        [
            "echo 'sum_ints.py' > ENTRY && echo 'import sys' > sum_ints.py && "
            "echo 'print(sum(map(int, sys.stdin.read().split())))' >> sum_ints.py"
        ]
    )
    assert files["ENTRY"] == "sum_ints.py\n"
    assert files["sum_ints.py"] == "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n"


def test_median_matches_the_experiment_definition_without_importing_it_at_runtime():
    samples = [[], [1.0], [1.0, 3.0], [4.0, 1.0, 9.0, 2.0]]
    for sample in samples:
        assert median(sample) == fitness_median(sample)
    assert "element" not in inspect.signature(combine).parameters


def test_experiment_code_does_not_import_the_fossil_layer():
    files = [ROOT / "cli.py"]
    for name in EXPERIMENT_ROOTS:
        files.extend((ROOT / name).rglob("*.py"))
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not alias.name.split(".")[0] == "analysis" for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "analysis"
    for path in (ROOT / "analysis").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in {"selection", "agents", "ledger"}


def _commit(repo: Path, name: str, text: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "fossil-test",
            "GIT_AUTHOR_EMAIL": "fossil-test@example.com",
            "GIT_COMMITTER_NAME": "fossil-test",
            "GIT_COMMITTER_EMAIL": "fossil-test@example.com",
        }
    )
    (repo / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", name], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "add"], cwd=repo, check=True, env=env)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True, env=env)
    return sha.stdout.strip()


def test_analysis_is_deterministic_and_does_not_touch_git_or_sqlite(tmp_path: Path):
    repo = tmp_path / "specimen"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    head = _commit(repo, "note.txt", "note\n")
    ledger = tmp_path / "ledger.sqlite"
    conn = sqlite3.connect(ledger)
    conn.executescript((ROOT / "ledger" / "schema.sql").read_text(encoding="utf-8"))
    conn.execute(
        """
        insert into runs (run_id, seed, created_at, updated_at, status, provider, runner,
                          generations, n_agents, shock_generation, heldout_every, config_json)
        values ('synthetic', 1, 't', 't', 'complete', 'none', 'local', 1, 1, 0, 10, '{}')
        """
    )
    conn.execute(
        """
        insert into episodes (run_id, generation, agent_id, task_id, phase, started_at,
                              parent_sha, tests_passed, tests_total, survived)
        values ('synthetic', 1, 'a0', 'echo_reverse', 'train', 't', ?, 2, 2, 1)
        """,
        (head,),
    )
    conn.execute(
        "insert into generation_marks (run_id, generation, start_sha) values ('synthetic', 1, ?)",
        (head,),
    )
    conn.execute(
        "insert into tool_calls (episode_id, seq, cmd, exit_code) values (1, 1, ?, 0)",
        ("echo 'import sys; print(sys.stdin.read().strip()[::-1])' > echo_reverse.py",),
    )
    conn.commit()
    conn.close()
    before_db = hashlib.sha256(ledger.read_bytes()).hexdigest()
    before_head = specimen_head(repo)
    run = tmp_path
    # measure_run looks for run_dir/ledger.sqlite and run_dir/specimen, which is tmp_path.
    first = build_document(run)
    second = build_document(run)
    assert first == second
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before_db
    assert specimen_head(repo) == before_head
    assert first["elemental"]["decision"] == "D"
    assert first["elemental"]["nearest_element"] is None
    assert first["episodes"][0]["elemental"]["representation"] == "none"
    assert first["episodes"][0]["source_form"] == "oneliner_stdin_read"
    render(first, build_table())


@pytest.mark.skipif(not (RUN / "ledger.sqlite").exists(), reason="local experiment record")
def test_experiment_2_fossil_layer_matches_the_ledger():
    ledger = RUN / "ledger.sqlite"
    before_db = hashlib.sha256(ledger.read_bytes()).hexdigest()
    before_head = specimen_head(RUN / "specimen")
    document = build_document(RUN)
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before_db
    assert specimen_head(RUN / "specimen") == before_head
    assert document["elemental"]["representation"] == "none"
    assert document["elemental"]["nearest_element"] is None
    assert "5097ce70fd10" not in __import__("json").dumps(document)
    shas = [row["commit_sha"] for row in document["survivor_commits"]]
    assert [sha[:12] for sha in shas] == list(
        ("5097ce52d2e0", "fdbbdd1642b8", "86c142a5cfbb", "ce2c9f3210ed", "996d6470ce42")
    )
    by_gen = {row["generation"]: row for row in document["survivor_commits"]}
    assert by_gen[1]["derived"]["source_form"] == "oneliner_stdin_read"
    assert by_gen[15]["derived"]["source_form"] == "readline_reverse"
    assert by_gen[17]["derived"]["same_blob_as_an_earlier_commit"] is True
    assert by_gen[17]["derived"]["copied_from_existing_artifact"] is False
    assert by_gen[17]["derived"]["cultural_transmission"] == "not_established"
    assert by_gen[45]["derived"]["same_blob_as_an_earlier_commit"] is True
    residents = document["structure"]["echo_reverse_residents"]
    assert residents["n"] == 17
    assert residents["null_commit"] == 12
    assert document["structure"]["reuse"]["reuse_event_total"] == 0
    assert document["structure"]["reuse"]["episodes_with_inspect_commands"] == 0
    assert all(row["elemental"]["representation"] == "none" for row in document["episodes"])
    xml = render(document, build_table())
    assert "decision D" in xml
    assert "0 of 118" in xml
    ET.fromstring(xml.encode("utf-8"))
