"""SVG figure of the chemical table and the fossil measurements.

The table is drawn from the element dataset. No software fossil is placed in
a cell. The fossil panel uses task, residence, source form, generation, and
the zero reuse count.
"""

from __future__ import annotations

BLOCKS = {"s": "#c5d8ee", "p": "#f0d7b5", "d": "#e3cfe6", "f": "#cfe3d4"}
RESIDENT = "#1f6b4a"
READLINE = "#2f5f8a"
FAIL = "#8a4b3c"
HELD = "#3d6b99"
QUIET = "#8a8175"
PAPER = "#f6f3ee"
INK = "#1c1917"


def esc(value: object) -> str:
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(document: dict, elements: list[dict]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="1560" viewBox="0 0 1180 1560">',
        f'<rect width="1180" height="1560" fill="{PAPER}"/>',
        '<g font-family="ui-sans-serif, system-ui, sans-serif" fill="#1c1917">',
    ]
    parts.append(_title(document))
    parts.append(_table(elements))
    parts.append(_fossils(document))
    parts.append("</g></svg>")
    return "\n".join(parts) + "\n"


def _title(document: dict) -> str:
    decision = document["elemental"]["decision"]
    run = document["run_id"]
    return f"""
    <text x="36" y="36" font-size="22" font-weight="600">Experiment 2 fossil layer</text>
    <text x="36" y="58" font-size="13" fill="{QUIET}">{esc(run)}</text>
    <rect x="760" y="22" width="384" height="44" rx="6" fill="#fff" stroke="#cfc6ba"/>
    <text x="776" y="40" font-size="12">Computed elemental assignment</text>
    <text x="776" y="56" font-size="14" font-weight="600">decision {esc(decision)} — representation none</text>
    """


def _table(elements: list[dict]) -> str:
    size, gap, ox, oy = 30, 3, 36, 100
    parts = [
        f'<text x="36" y="92" font-size="14" font-weight="600">Chemical substrate. 0 of 118 cells hold a software fossil.</text>'
    ]
    by_z = {row["atomic_number"]: row for row in elements}
    for z, element in by_z.items():
        if element["series"] == "lanthanide":
            col, row = 2 + (z - 57), 8
        elif element["series"] == "actinide":
            col, row = 2 + (z - 89), 9
        else:
            col, row = element["group"] - 1, element["period"] - 1
        x = ox + col * (size + gap)
        y = oy + row * (size + gap)
        if row >= 8:
            y += 18
        color = BLOCKS[element["block"]]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="3" fill="{color}" stroke="#fff"/>'
            f'<text x="{x + size / 2}" y="{y + 19}" text-anchor="middle" font-size="9">{esc(element["symbol"])}</text>'
        )
    for period, label in ((6, "57–71"), (7, "89–103")):
        x = ox + 2 * (size + gap)
        y = oy + (period - 1) * (size + gap)
        parts.append(
            f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="3" fill="none" stroke="#b7aea3" stroke-dasharray="2 2"/>'
            f'<text x="{x + size / 2}" y="{y + 18}" text-anchor="middle" font-size="7" fill="{QUIET}">{label}</text>'
        )
    legend_y = oy + 10 * (size + gap) + 28
    parts.append(
        f'<text x="36" y="{legend_y}" font-size="11" fill="{QUIET}">'
        "Blocks, left to right in the legend, are s, p, d, f. "
        "La–Lu and Ac–Lr are the two rows under the main table. Group 3 of periods 6 and 7 points at those rows and is not an extra element. "
        "Element names are not measurements of the specimen."
        "</text>"
    )
    x = 700
    for block, color in BLOCKS.items():
        parts.append(
            f'<rect x="{x}" y="{legend_y - 12}" width="14" height="14" fill="{color}" stroke="#fff"/>'
            f'<text x="{x + 18}" y="{legend_y}" font-size="11">{block}</text>'
        )
        x += 48
    return "\n".join(parts)


def _fossils(document: dict) -> str:
    structure = document["structure"]
    parts = ['<text x="36" y="520" font-size="14" font-weight="600">What the specimen actually varies on</text>']
    zeros = ", ".join(structure["dimensions"]["always_zero"]) or "none"
    varying = ", ".join(structure["dimensions"]["varying"])
    parts.append(
        f'<text x="36" y="542" font-size="12">Always zero: {esc(zeros)}</text>'
        f'<text x="36" y="560" font-size="12">More than one value: {esc(varying)}</text>'
    )
    parts.append(_bars(structure["outcomes"]))
    parts.append(_failure_note(document))
    parts.append(_timeline(document))
    parts.append(_sources(document))
    parts.append(_footer(document))
    return "\n".join(parts)


def _bars(outcomes: list[dict]) -> str:
    parts = ['<text x="36" y="592" font-size="13" font-weight="600">Episodes by task</text>']
    y = 608
    scale = 8
    for row in outcomes:
        parts.append(f'<text x="36" y="{y + 12}" font-size="11">{esc(row["task_id"])}</text>')
        x = 170
        for key, color in (
            ("shared_tree_resident", RESIDENT),
            ("train_failed", FAIL),
            ("heldout_passed_not_resident", HELD),
            ("heldout_failed", "#c4b8a8"),
        ):
            width = row[key] * scale
            if width:
                parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="14" fill="{color}"/>')
                parts.append(
                    f'<text x="{x + width + 4}" y="{y + 11}" font-size="10" fill="{QUIET}">{row[key]}</text>'
                )
            x += width + 28
        y += 22
    parts.append(
        f'<text x="170" y="{y + 8}" font-size="11" fill="{QUIET}">'
        f'<tspan fill="{RESIDENT}">resident survivor</tspan>  '
        f'<tspan fill="{FAIL}">training failure</tspan>  '
        f'<tspan fill="{HELD}">held-out pass, not in the specimen</tspan>  '
        "held-out failure"
        "</text>"
    )
    return "\n".join(parts)


def _failure_note(document: dict) -> str:
    train_fail = [row for row in document["episodes"] if row["phase"] == "train" and row["survived"] == 0]
    sources: dict[str, int] = {}
    entries: dict[str, int] = {}
    for row in train_fail:
        sources[row["source_form"]] = sources.get(row["source_form"], 0) + 1
        entries[row["entry_form"]] = entries.get(row["entry_form"], 0) + 1
    source_text = ", ".join(f"{key} {value}" for key, value in sorted(sources.items()))
    entry_text = ", ".join(f"{key} {value}" for key, value in sorted(entries.items()))
    return (
        f'<text x="36" y="856" font-size="12">Training-failure source forms: {esc(source_text)}</text>'
        f'<text x="36" y="874" font-size="12">Training-failure ENTRY forms: {esc(entry_text)}</text>'
    )


def _timeline(document: dict) -> str:
    forms = {}
    for commit in document["survivor_commits"]:
        observed = commit.get("observed") or {}
        derived = commit.get("derived") or {}
        if observed.get("blob_sha"):
            forms[observed["blob_sha"]] = derived.get("source_form")
    colors = {"oneliner_stdin_read": RESIDENT, "readline_reverse": READLINE}
    failed = {
        row["generation"]
        for row in document["episodes"]
        if row["task_id"] == "echo_reverse" and row["phase"] == "train" and row["survived"] == 0
    }
    rewrites = {
        row["generation"]
        for row in document["episodes"]
        if row["task_id"] == "echo_reverse" and row["shared_tree_resident"] == 1 and row["commit_present"] == 0
    }
    shock_gens = {row["generation"] for row in document["shocks"]}
    parts = [
        '<text x="36" y="900" font-size="13" font-weight="600">echo_reverse.py at each generation start</text>',
        f'<text x="36" y="918" font-size="11" fill="{QUIET}">Color is the blob. A ring is a same-byte rewrite with no new commit. A red tick is a failed attempt that the harness restored. Generation 25 is the shock record.</text>',
    ]
    starts = [point for point in document["echo_reverse_timeline"] if point["at"] == "generation_start"]
    for point in starts:
        gen = point["generation"]
        x = 36 + (gen - 1) * 22
        blob = point["echo_reverse_blob"]
        color = colors.get(forms.get(blob), "#d9d3cb" if blob is None else "#7d6b58")
        parts.append(f'<rect x="{x}" y="932" width="18" height="18" fill="{color}"/>')
        if gen in rewrites:
            parts.append(f'<rect x="{x + 3}" y="935" width="12" height="12" fill="none" stroke="#fff" stroke-width="1.5"/>')
        if gen in failed:
            parts.append(f'<rect x="{x + 7}" y="954" width="4" height="8" fill="{FAIL}"/>')
        if gen in shock_gens:
            parts.append(f'<path d="M{x + 9} 928 l4 4 l-4 4 l-4 -4 z" fill="#8a6a12"/>')
        if gen in (1, 10, 15, 17, 25, 43, 45, 50):
            parts.append(f'<text x="{x}" y="978" font-size="9" fill="{QUIET}">{gen}</text>')
    y = 1000
    for commit in document["survivor_commits"]:
        if not commit.get("commit_sha"):
            continue
        derived = commit["derived"]
        earlier = "earlier bytes, not the parent blob" if derived["same_blob_as_an_earlier_commit"] else "new or parent blob"
        parts.append(
            f'<text x="36" y="{y}" font-size="11">G{commit["generation"]} {esc(commit["commit_sha"][:12])} '
            f'{esc(derived["source_form"])}; {esc(earlier)}; transmission {esc(derived["cultural_transmission"])}</text>'
        )
        y += 16
    return "\n".join(parts)


def _sources(document: dict) -> str:
    commits = [row for row in document["survivor_commits"] if row.get("source_text")]
    oneliner = next((row for row in commits if row["derived"]["source_form"] == "oneliner_stdin_read"), None)
    readline = next((row for row in commits if row["derived"]["source_form"] == "readline_reverse"), None)
    parts = ['<text x="36" y="1100" font-size="13" font-weight="600">Two resident source texts. Same hidden-test result. Not the same bytes.</text>']
    parts.append(_card(36, 1116, "oneliner", oneliner))
    parts.append(_card(600, 1116, "readline", readline))
    lines = [
        "same hidden-test behavior",
        "same source bytes",
        "same source copied from an existing artifact",
        "cultural transmission",
    ]
    notes = [
        "both forms pass 2/2 where they survive",
        "the two texts differ",
        "inspect commands, existing-path executions, and dependency events are zero",
        "not established",
    ]
    y = 1288
    for i, (line, note) in enumerate(zip(lines, notes)):
        parts.append(f'<text x="36" y="{y}" font-size="13">{esc(line)}</text>')
        parts.append(f'<text x="520" y="{y}" font-size="12" fill="{QUIET}">{esc(note)}</text>')
        if i < len(lines) - 1:
            parts.append(f'<text x="36" y="{y + 16}" font-size="12" fill="{QUIET}">≠</text>')
        y += 32
    return "\n".join(parts)


def _card(x: int, y: int, title: str, commit: dict | None) -> str:
    if commit is None:
        body = "not in this run"
        meta = ""
    else:
        body = commit["source_text"].rstrip("\n")
        meta = f'{commit["observed"]["source_bytes"]} bytes · {commit["commit_sha"][:12]}'
    lines = "".join(
        f'<text x="{x + 12}" y="{y + 48 + i * 16}" font-size="12" font-family="ui-monospace, monospace">{esc(line)}</text>'
        for i, line in enumerate(body.splitlines())
    )
    return (
        f'<rect x="{x}" y="{y}" width="520" height="140" rx="6" fill="#fff" stroke="#cfc6ba"/>'
        f'<text x="{x + 12}" y="{y + 22}" font-size="12" font-weight="600">{esc(title)}</text>'
        f'<text x="{x + 12}" y="{y + 38}" font-size="11" fill="{QUIET}">{esc(meta)}</text>'
        f"{lines}"
    )


def _footer(document: dict) -> str:
    shock = document["shocks"][0] if document["shocks"] else {}
    reuse = document["structure"]["reuse"]
    mods = document["modification_by_path"][:6]
    mod_text = ", ".join(f"{row['path']} {row['count']}" for row in mods)
    residents = document["structure"]["echo_reverse_residents"]
    return f"""
    <text x="36" y="1436" font-size="13" font-weight="600">Reuse, shock, modification</text>
    <text x="36" y="1456" font-size="12">reuse events {reuse["reuse_event_total"]}; episodes that inspected the repo {reuse["episodes_with_inspect_commands"]}; executions of an existing path {reuse["episodes_executing_an_existing_path"]}; evaluator executions {reuse["evaluator_executions"]} (not reuse)</text>
    <text x="36" y="1474" font-size="12">shock {esc(shock.get("shock_id"))} generation {esc(shock.get("generation"))}: applied {esc(shock.get("applied"))}, reason {esc(shock.get("reason"))}, target {esc(shock.get("old_path"))}</text>
    <text x="36" y="1492" font-size="12">resident echo_reverse {residents["n"]}: {residents["with_commit"]} new commits, {residents["null_commit"]} same-byte rewrites with no new commit</text>
    <text x="36" y="1510" font-size="12">modification events: {esc(mod_text)}</text>
    <text x="36" y="1536" font-size="11" fill="{QUIET}">The full decision is in fossils.json. Element symbols on the table above are the chemical dataset, not names for these programs.</text>
    """
