"""Build the fossil document for one finished run."""

from __future__ import annotations

import json
from pathlib import Path

from analysis.elements import build_table, dataset_document, write_dataset
from analysis.measure import measure_run
from analysis.render import render
from analysis.structure import summarize

ELEMENTAL = {
    "representation": "none",
    "nearest_element": None,
    "distance": None,
    "status": "computed_decision",
}


def build_document(run_dir: Path) -> dict:
    elements = build_table()
    measured = measure_run(Path(run_dir))
    for episode in measured["episodes"]:
        episode["elemental"] = dict(ELEMENTAL)
    structure = summarize(measured, elements)
    return {
        "kind": "pegmatite_fossil_layer",
        "run_id": measured["run_id"],
        "element_dataset": dataset_document()["source"],
        "integrity": measured["integrity"],
        "episodes": measured["episodes"],
        "survivor_commits": measured["survivor_commits"],
        "echo_reverse_timeline": measured["echo_reverse_timeline"],
        "shocks": measured["shocks"],
        "modification_by_path": measured["modification_by_path"],
        "observation_role_totals": measured["observation_role_totals"],
        "structure": structure,
        "elemental": structure["decision"],
    }


def write_record(run_dir: Path, out_dir: Path) -> dict:
    write_dataset()
    document = build_document(run_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    (out_dir / "fossils.json").write_text(text, encoding="utf-8")
    (out_dir / "fossil.svg").write_text(render(document, build_table()), encoding="utf-8")
    return document
