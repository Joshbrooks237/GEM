"""Which measured dimensions vary, and whether an element can name them.

The decision function does not assign an element. A software number and a
chemical number are not the same quantity, and 48 of the 118 CIAAW cells do
not even have a single atomic weight.
"""

from __future__ import annotations

from analysis.measure import NUMERIC_KEYS

STRUCTURAL_KEYS = (
    "tests_passed",
    "tests_total",
    "survived",
    "syntax_ok",
    "function_count",
    "class_count",
    "import_count",
    "source_bytes",
    "source_lines",
    "reuse_events",
    "shared_tree_resident",
    "source_form",
    "entry_form",
)

FORMULAS = {
    "source_bytes": "len(utf-8 bytes of the recovered source). Observed when the bytes come from git show. Derived when they are reconstructed from an echo command.",
    "source_lines": "len(str.splitlines()) on those bytes. Derived.",
    "syntax_ok": "1 if ast.parse accepts the source, else 0. Derived. Null when no source was recovered.",
    "function_count": "number of module-level ast.FunctionDef nodes. Derived. Null when the source does not parse.",
    "class_count": "number of module-level ast.ClassDef nodes. Derived.",
    "import_count": "number of ast.Import and ast.ImportFrom nodes. Derived.",
    "source_form": "exact text match to the one-liner or the readline program, else literal backslash-n, else a function that is never called, else another parseable program. Derived label, not a fitness input.",
    "entry_form": "class of the ENTRY bytes. python_command if the line starts with python or python3; bare_filename if it is only a .py name; empty; other; absent. Observed bytes from the episode commit when that commit exists, otherwise reconstructed from echo redirects. Derived label.",
    "shared_tree_resident": "1 only when phase is train and the ledger survived flag is 1. Held-out episodes run in a worktree the harness deletes, so a held-out pass is not residence. Derived.",
    "same_blob_as_an_earlier_commit": "the commit's blob for the path occurs in an ancestor and is not the parent blob. Derived from git rev-parse. This is not reuse and not transmission.",
    "copied_from_existing_artifact": "false when that episode's inspect commands, executions of a path that already existed, and dependency observations are all zero. Derived. cultural_transmission stays not_established.",
    "median": "even-count median: average of the two central values. Same definition as selection.fitness.median, reimplemented here so this layer does not import fitness.",
    "elemental_representation": "constant 'none'. No axis of the measurement is an atomic weight, a period, or a group.",
}


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(float(ordered[mid]), 6)
    return round((float(ordered[mid - 1]) + float(ordered[mid])) / 2, 6)


def _numbers(rows: list[dict], key: str) -> list[float]:
    return [row[key] for row in rows if row.get(key) is not None]


def _summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "min": None, "max": None, "median": None, "n_unique": 0}
    return {
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "median": median(values),
        "n_unique": len(set(values)),
    }


def _ranges_overlap(left: dict, right: dict) -> bool | None:
    if not left["n"] or not right["n"]:
        return None
    return not (left["max"] < right["min"] or right["max"] < left["min"])


def _side_by_side(rows: list[dict], left_name: str, right_name: str, left_rows: list[dict], right_rows: list[dict]) -> dict:
    compared = {}
    for key in NUMERIC_KEYS:
        left = _summary(_numbers(left_rows, key))
        right = _summary(_numbers(right_rows, key))
        compared[key] = {
            left_name: left,
            right_name: right,
            "ranges_overlap": _ranges_overlap(left, right),
        }
    return compared


def dimensional_report(episodes: list[dict]) -> dict:
    columns = {}
    constant = []
    always_zero = []
    varying = []
    for key in NUMERIC_KEYS:
        values = [row.get(key) for row in episodes]
        present = [value for value in values if value is not None]
        unique = len(set(present))
        info = {
            "n": len(episodes),
            "n_measured": len(present),
            "n_missing": len(values) - len(present),
            "n_unique": unique,
            "min": min(present) if present else None,
            "max": max(present) if present else None,
        }
        columns[key] = info
        if unique <= 1 and present:
            constant.append(key)
        if present and all(value == 0 for value in present) and len(present) == len(episodes):
            always_zero.append(key)
        if unique > 1:
            varying.append(key)
    redundant = []
    keys = list(NUMERIC_KEYS)
    for i, left in enumerate(keys):
        for right in keys[i + 1 :]:
            if [row.get(left) for row in episodes] == [row.get(right) for row in episodes]:
                redundant.append([left, right])
    train = [row for row in episodes if row["phase"] == "train"]
    survivors = [row for row in train if row["survived"] == 1]
    failures = [row for row in train if row["survived"] == 0]
    echo = [row for row in train if row["task_id"] == "echo_reverse"]
    other = [row for row in train if row["task_id"] != "echo_reverse"]
    return {
        "columns": columns,
        "varying": varying,
        "constant": constant,
        "always_zero": always_zero,
        "redundant_equal_columns": redundant,
        "survivor_vs_failure": _side_by_side(episodes, "survivor", "failure", survivors, failures),
        "echo_reverse_vs_other_training": _side_by_side(episodes, "echo_reverse", "other", echo, other),
        "distinct_numeric_profiles": len({tuple(row.get(key) for key in NUMERIC_KEYS) for row in episodes}),
    }


def persistence(measured: dict) -> dict:
    counts: dict[str, int] = {}
    for point in measured["echo_reverse_timeline"]:
        if point["at"] != "generation_start":
            continue
        key = point["echo_reverse_blob"] or "absent"
        counts[key] = counts.get(key, 0) + 1
    forms = {}
    for commit in measured["survivor_commits"]:
        if not commit.get("commit_sha"):
            continue
        forms[commit["observed"]["blob_sha"]] = commit["derived"]["source_form"]
    final = measured["echo_reverse_timeline"][-1]
    return {
        "generation_starts": len(counts) and sum(counts.values()),
        "blob_at_generation_start": [
            {"blob_sha": blob, "generation_starts": n, "source_form_from_a_survivor_commit": forms.get(blob)}
            for blob, n in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "final_head_blob": final["echo_reverse_blob"],
        "final_head_commit": final["commit"],
        "final_head_author": final.get("author"),
        "final_head_subject": final.get("subject"),
    }


def outcome_counts(episodes: list[dict]) -> list[dict]:
    tasks = []
    seen = []
    for row in episodes:
        if row["task_id"] not in seen:
            seen.append(row["task_id"])
    for task in seen:
        rows = [row for row in episodes if row["task_id"] == task]
        tasks.append(
            {
                "task_id": task,
                "episodes": len(rows),
                "shared_tree_resident": sum(row["shared_tree_resident"] for row in rows),
                "train_failed": sum(row["phase"] == "train" and row["survived"] == 0 for row in rows),
                "heldout_passed_not_resident": sum(row["ledger_survived_not_resident"] for row in rows),
                "heldout_failed": sum(row["phase"] == "heldout" and row["survived"] == 0 for row in rows),
                "source_forms": _tally(row["source_form"] for row in rows),
                "entry_forms": _tally(row["entry_form"] for row in rows),
            }
        )
    return tasks


def _tally(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def elemental_decision(elements: list[dict], episodes: list[dict]) -> dict:
    kinds: dict[str, int] = {}
    for element in elements:
        kind = element["atomic_weight"]["kind"]
        kinds[kind] = kinds.get(kind, 0) + 1
    without_single = kinds.get("none", 0) + kinds.get("interval", 0)
    profiles = len({tuple(row.get(key) for key in NUMERIC_KEYS) for row in episodes})
    structural = len({tuple(row.get(key) for key in STRUCTURAL_KEYS) for row in episodes})
    return {
        "representation": "none",
        "decision": "D",
        "nearest_element": None,
        "distance": None,
        "reason": (
            "No measured software quantity is an atomic weight, a period, or a group. "
            f"{without_single} of 118 CIAAW cells have no single atomic weight "
            f"({kinds.get('none', 0)} em dashes, {kinds.get('interval', 0)} intervals), "
            "so a nearest-element distance over the whole table is undefined unless those cells are given an invented number. "
            f"All {profiles} episodes are numerically distinct once generation and resource use are included. "
            f"The structural columns collapse to {structural} profiles. "
            "Neither count is a chemical coordinate. "
            "Chemical blocks are not the task, survival, source-form, or ENTRY-form categories in the ledger."
        ),
        "distinct_structural_profiles": structural,
        "weight_kinds": kinds,
        "elements_without_a_single_atomic_weight": without_single,
        "distinct_numeric_profiles": profiles,
        "rejected": {
            "A_coordinate": "Rejected. Mapping bytes or survival onto period or group would choose the axis. The data do not.",
            "B_nearest_neighbor": "Rejected. Distance needs one number per element. Intervals and em dashes do not have one.",
            "C_category_buckets": "Rejected. s/p/d/f and alkali/noble-gas are chemical classes. The fossil classes are task, source form, and residence.",
        },
    }


def summarize(measured: dict, elements: list[dict]) -> dict:
    episodes = measured["episodes"]
    train_echo = [
        row for row in episodes if row["phase"] == "train" and row["task_id"] == "echo_reverse" and row["survived"] == 1
    ]
    return {
        "formulas": FORMULAS,
        "dimensions": dimensional_report(episodes),
        "outcomes": outcome_counts(episodes),
        "persistence": persistence(measured),
        "reuse": {
            "reuse_event_total": measured["reuse_event_total"],
            "episodes_with_reuse_events": sum(row["reuse_events"] > 0 for row in episodes),
            "episodes_with_inspect_commands": sum(row["inspect_commands"] > 0 for row in episodes),
            "episodes_executing_an_existing_path": sum(row["executions_of_existing"] > 0 for row in episodes),
            "dependency_events": sum(row["dependency_events"] for row in episodes),
            "evaluator_executions": sum(row["evaluator_executions"] for row in episodes),
        },
        "echo_reverse_residents": {
            "n": len(train_echo),
            "with_commit": sum(row["commit_present"] for row in train_echo),
            "null_commit": sum(row["commit_present"] == 0 for row in train_echo),
            "source_forms": _tally(row["source_form"] for row in train_echo),
            "rewrote_parent_text": sum(row["same_reconstructed_text_as_parent"] is True for row in train_echo),
        },
        "decision": elemental_decision(elements, episodes),
    }
