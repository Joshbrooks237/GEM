"""Read-only measurements of one finished specimen.

Every quantity is either copied from the ledger or Git, or computed from
those copies by a function in this file. Nothing here writes Git or SQLite.
"""

from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import subprocess
from pathlib import Path

SURVIVOR_PREFIXES = (
    "5097ce52d2e0",
    "fdbbdd1642b8",
    "86c142a5cfbb",
    "ce2c9f3210ed",
    "996d6470ce42",
)

ONELINER = "import sys; print(sys.stdin.read().strip()[::-1])"
READLINE = "import sys\nline = sys.stdin.readline().strip()\nprint(line[::-1])"

_INSPECT = {"ls", "find", "pwd", "cat", "head", "tail", "sed", "less", "more", "nl", "od", "wc", "stat"}
_GIT_INSPECT = {"show", "log", "diff", "status", "ls-files", "grep"}
_GIT_ALLOWED = {"rev-parse", "show", "diff-tree", "rev-list", "cat-file", "merge-base", "log"}

NUMERIC_KEYS = (
    "generation",
    "tests_passed",
    "tests_total",
    "survived",
    "attributable",
    "token_usage",
    "tool_calls",
    "wall_time_s",
    "reuse_score",
    "reuse_events",
    "inspection_events",
    "invocation_events",
    "dependency_events",
    "modification_events",
    "evaluator_executions",
    "commit_present",
    "shell_commands",
    "inspect_commands",
    "executions_of_existing",
    "executions_of_new",
    "source_bytes",
    "source_lines",
    "syntax_ok",
    "function_count",
    "class_count",
    "import_count",
    "shared_tree_resident",
)


def ledger_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def connect_ledger(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    if not args or args[0] not in _GIT_ALLOWED:
        raise RuntimeError(f"refusing git command {args!r}")
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_PAGER"] = "cat"
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "safe.directory=*", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def specimen_head(repo: Path) -> str:
    result = git(repo, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "rev-parse HEAD failed")
    return result.stdout.strip()


def blob_at(repo: Path, sha: str, path: str) -> str | None:
    result = git(repo, "rev-parse", f"{sha}:{path}")
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def file_bytes(repo: Path, sha: str, path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "safe.directory=*", "show", f"{sha}:{path}"],
        check=False,
        capture_output=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_PAGER": "cat"},
    )
    if result.returncode != 0:
        return None
    return result.stdout


def path_exists(repo: Path, sha: str, path: str) -> bool:
    result = git(repo, "cat-file", "-e", f"{sha}:{path}")
    return result.returncode == 0


def commit_numstat(repo: Path, sha: str) -> list[dict]:
    result = git(repo, "diff-tree", "--root", "--no-commit-id", "--numstat", "-r", sha)
    rows = []
    if result.returncode != 0:
        return rows
    for line in result.stdout.splitlines():
        added, deleted, path = line.split("\t", 2)
        rows.append(
            {
                "path": path,
                "lines_added": None if added == "-" else int(added),
                "lines_deleted": None if deleted == "-" else int(deleted),
            }
        )
    return rows


def earlier_blobs(repo: Path, parent: str, path: str) -> list[str]:
    listed = git(repo, "rev-list", parent)
    if listed.returncode != 0:
        return []
    shas = [line for line in listed.stdout.splitlines() if line]
    if not shas:
        return []
    payload = "".join(f"{sha}:{path}\n" for sha in shas)
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_PAGER"] = "cat"
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "safe.directory=*", "cat-file", "--batch-check"],
        input=payload.encode(),
        check=False,
        capture_output=True,
        env=env,
    )
    found = []
    if result.returncode != 0:
        return found
    for line in result.stdout.decode().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "blob" and parts[0] not in found:
            found.append(parts[0])
    return found


def echo_e(body: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            code = body[i + 1]
            out.append({"n": "\n", "t": "\t", "\\": "\\"}.get(code, body[i : i + 2]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def extract_echo_write(cmd: str) -> dict | None:
    """Recover a simple `echo ... > path` body. Pipelines are not recovered."""
    if not cmd.startswith("echo"):
        return None
    i = 4
    interpret = False
    trailing_newline = True
    while True:
        while i < len(cmd) and cmd[i] in " \t":
            i += 1
        flag = cmd[i : i + 2]
        if flag in {"-e", "-n", "-E"} and (i + 2 == len(cmd) or cmd[i + 2] in " \t"):
            interpret = interpret or flag == "-e"
            trailing_newline = trailing_newline and flag != "-n"
            i += 2
            continue
        break
    if i >= len(cmd) or cmd[i] not in "'\"":
        return {"kind": "unparsed"}
    quote = cmd[i]
    i += 1
    if quote == "'":
        end = cmd.find("'", i)
        if end < 0:
            return {"kind": "unparsed"}
        body = cmd[i:end]
        rest = cmd[end + 1 :]
    else:
        chars: list[str] = []
        while i < len(cmd):
            if cmd[i] == "\\" and i + 1 < len(cmd):
                chars.append(cmd[i : i + 2])
                i += 2
                continue
            if cmd[i] == '"':
                break
            chars.append(cmd[i])
            i += 1
        else:
            return {"kind": "unparsed"}
        body = "".join(chars)
        rest = cmd[i + 1 :]
    head, sep, tail = rest.partition(">")
    if "|" in head:
        return {"kind": "pipeline"}
    if not sep:
        return {"kind": "unparsed"}
    append = tail.startswith(">")
    if append:
        tail = tail[1:]
    path = tail.strip().split()
    if not path:
        return {"kind": "unparsed"}
    if interpret:
        body = echo_e(body)
    if trailing_newline:
        body += "\n"
    return {"kind": "write", "path": path[0], "body": body, "append": append}


def split_shell(cmd: str) -> list[str]:
    """Split on && and ; outside quotes. This is enough for the commands in the ledger."""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if cmd.startswith("&&", i) or ch == ";":
            parts.append("".join(buf).strip())
            buf = []
            i += 2 if cmd.startswith("&&", i) else 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return [part for part in parts if part]


def reconstruct_writes(commands: list[str]) -> dict[str, str]:
    files: dict[str, str] = {}
    for cmd in commands:
        for segment in split_shell(cmd):
            extracted = extract_echo_write(segment)
            if not extracted or extracted.get("kind") != "write":
                continue
            path = extracted["path"]
            if extracted["append"]:
                files[path] = files.get(path, "") + extracted["body"]
            else:
                files[path] = extracted["body"]
    return files


def entry_form(text: str | None) -> str:
    if text is None:
        return "absent"
    line = text.strip()
    if not line:
        return "empty"
    if line.startswith("python3 ") or line.startswith("python "):
        return "python_command"
    if " " not in line and line.endswith(".py"):
        return "bare_filename"
    return "other"


def classify_source(text: str) -> str:
    stripped = text.strip("\n")
    if stripped == ONELINER:
        return "oneliner_stdin_read"
    if stripped == READLINE:
        return "readline_reverse"
    metrics = python_metrics(text)
    if metrics["syntax_ok"] == 0 and "\\n" in text:
        return "literal_backslash_n"
    if metrics["syntax_ok"] == 0:
        return "syntax_error"
    if metrics["uncalled_functions"]:
        return "defined_not_called"
    return "other_program"


def python_metrics(text: str) -> dict:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {
            "syntax_ok": 0,
            "function_count": None,
            "class_count": None,
            "import_count": None,
            "uncalled_functions": [],
        }
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return {
        "syntax_ok": 1,
        "function_count": len(functions),
        "class_count": len(classes),
        "import_count": len(imports),
        "uncalled_functions": sorted(set(functions) - called),
    }


def is_inspect(cmd: str) -> bool:
    parts = cmd.split()
    if not parts:
        return False
    if parts[0] in _INSPECT:
        return True
    return parts[0] == "git" and len(parts) > 1 and parts[1] in _GIT_INSPECT


def python_script(cmd: str) -> str | None:
    parts = cmd.split()
    if not parts or parts[0] not in {"python", "python3"}:
        return None
    for part in parts[1:]:
        if part.startswith("-"):
            continue
        return part if part.endswith(".py") else None
    return None


def source_record(text: str | None, origin: str) -> dict:
    if text is None:
        form = "pipeline_unrecovered" if origin == "pipeline_unrecovered" else "unrecovered"
        return {
            "origin": origin,
            "bytes_status": None,
            "source_bytes": None,
            "source_lines": None,
            "syntax_ok": None,
            "function_count": None,
            "class_count": None,
            "import_count": None,
            "source_form": form,
            "text": None,
        }
    metrics = python_metrics(text)
    status = "observed" if origin == "git_blob" else "derived"
    return {
        "origin": origin,
        "bytes_status": status,
        "source_bytes": len(text.encode("utf-8")),
        "source_lines": len(text.splitlines()),
        "syntax_ok": metrics["syntax_ok"],
        "function_count": metrics["function_count"],
        "class_count": metrics["class_count"],
        "import_count": metrics["import_count"],
        "source_form": classify_source(text),
        "text": text if len(text) <= 800 else text[:800],
        "text_truncated": len(text) > 800,
    }


def _commands_for(conn: sqlite3.Connection) -> dict[int, list[sqlite3.Row]]:
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in conn.execute("select episode_id, seq, cmd, exit_code from tool_calls order by episode_id, seq"):
        grouped.setdefault(row["episode_id"], []).append(row)
    return grouped


def _counts(conn: sqlite3.Connection, sql: str, key: str) -> dict[int, int]:
    return {row[key]: row["n"] for row in conn.execute(sql)}


def measure_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    ledger_path = run_dir / "ledger.sqlite"
    repo = run_dir / "specimen"
    before_hash = ledger_sha256(ledger_path)
    before_head = specimen_head(repo)
    conn = connect_ledger(ledger_path)
    try:
        document = _measure(conn, repo, run_dir.name)
    finally:
        conn.close()
    after_hash = ledger_sha256(ledger_path)
    after_head = specimen_head(repo)
    if before_hash != after_hash or before_head != after_head:
        raise RuntimeError("analysis changed the ledger or the specimen HEAD")
    document["integrity"] = {
        "ledger_sha256": before_hash,
        "specimen_head": before_head,
        "ledger_unchanged": True,
        "specimen_head_unchanged": True,
    }
    return document


def _measure(conn: sqlite3.Connection, repo: Path, run_id: str) -> dict:
    commands = _commands_for(conn)
    role_counts: dict[int, dict[str, int]] = {}
    for row in conn.execute(
        "select episode_id, role, count(*) n from observations group by episode_id, role"
    ):
        role_counts.setdefault(row["episode_id"], {})[row["role"]] = row["n"]
    reuse_counts = _counts(
        conn,
        "select consumer_episode episode_id, count(*) n from reuse_events group by consumer_episode",
        "episode_id",
    )
    episodes = []
    for row in conn.execute(
        """
        select id, generation, agent_id, task_id, phase, tests_passed, tests_total,
               survived, attributable, gamed, token_usage, tool_calls, wall_time_s,
               reuse_score, commit_sha, parent_sha, quality_json
        from episodes order by id
        """
    ):
        episodes.append(_episode(repo, row, commands.get(row["id"], []), role_counts.get(row["id"], {}), reuse_counts.get(row["id"], 0)))

    commits = []
    for prefix in SURVIVOR_PREFIXES:
        resolved = git(repo, "rev-parse", "--verify", prefix)
        if resolved.returncode != 0:
            commits.append({"prefix": prefix, "resolved": False})
            continue
        sha = resolved.stdout.strip()
        match = next((ep for ep in episodes if ep["commit_sha"] == sha), None)
        commits.append(_commit_record(repo, sha, match))

    marks = [
        {"generation": row["generation"], "start_sha": row["start_sha"]}
        for row in conn.execute(
            "select generation, start_sha from generation_marks order by generation"
        )
    ]
    head = specimen_head(repo)
    timeline = []
    for mark in marks:
        timeline.append(
            {
                "generation": mark["generation"],
                "at": "generation_start",
                "commit": mark["start_sha"],
                "echo_reverse_blob": blob_at(repo, mark["start_sha"], "echo_reverse.py"),
            }
        )
    author = git(repo, "log", "-1", "--format=%an", head)
    subject = git(repo, "log", "-1", "--format=%s", head)
    timeline.append(
        {
            "generation": None,
            "at": "final_head",
            "commit": head,
            "author": author.stdout.strip() if author.returncode == 0 else None,
            "subject": subject.stdout.strip() if subject.returncode == 0 else None,
            "echo_reverse_blob": blob_at(repo, head, "echo_reverse.py"),
        }
    )
    shocks = [dict(row) for row in conn.execute("select shock_id, generation, old_path, new_path, applied, reason, origin_commit, commit_sha from shocks")]
    modification_by_path = [
        {"path": row["path"], "count": row["n"]}
        for row in conn.execute(
            """
            select path, count(*) n from observations
            where role = 'modification' group by path order by n desc, path
            """
        )
    ]
    role_totals = {
        row["role"]: row["n"]
        for row in conn.execute("select role, count(*) n from observations group by role order by role")
    }
    return {
        "run_id": run_id,
        "episodes": episodes,
        "survivor_commits": commits,
        "echo_reverse_timeline": timeline,
        "shocks": shocks,
        "modification_by_path": modification_by_path,
        "observation_role_totals": role_totals,
        "reuse_event_total": conn.execute("select count(*) n from reuse_events").fetchone()["n"],
    }


def _episode(repo: Path, row: sqlite3.Row, calls: list[sqlite3.Row], roles: dict[str, int], reuse_n: int) -> dict:
    pipelines = 0
    inspects = 0
    existing = 0
    fresh = 0
    git_commit_exit = None
    command_text = []
    for call in calls:
        cmd = call["cmd"]
        command_text.append(cmd)
        if is_inspect(cmd):
            inspects += 1
        script = python_script(cmd)
        if script and row["parent_sha"]:
            if path_exists(repo, row["parent_sha"], script):
                existing += 1
            else:
                fresh += 1
        if cmd.startswith("git commit"):
            git_commit_exit = call["exit_code"]
        for segment in split_shell(cmd):
            extracted = extract_echo_write(segment)
            if extracted and extracted.get("kind") == "pipeline":
                pipelines += 1
    rebuilt = reconstruct_writes(command_text)
    source = None
    origin = "absent"
    if row["commit_sha"]:
        names = commit_numstat(repo, row["commit_sha"])
        py = [item["path"] for item in names if item["path"].endswith(".py")]
        if py:
            raw = file_bytes(repo, row["commit_sha"], py[-1])
            if raw is not None:
                source = raw.decode("utf-8")
                origin = "git_blob"
    py_rebuilt = {path: body for path, body in rebuilt.items() if path.endswith(".py")}
    if source is None and py_rebuilt:
        source = py_rebuilt[sorted(py_rebuilt)[-1]]
        origin = "tool_log_reconstruction"
    elif source is None and pipelines:
        origin = "pipeline_unrecovered"
    entry_text = None
    entry_origin = "absent"
    if row["commit_sha"]:
        entry_raw = file_bytes(repo, row["commit_sha"], "ENTRY")
        if entry_raw is not None:
            entry_text = entry_raw.decode("utf-8")
            entry_origin = "git_blob"
    if entry_text is None and "ENTRY" in rebuilt:
        entry_text = rebuilt["ENTRY"]
        entry_origin = "tool_log_reconstruction"
    measured = source_record(source, origin if source is not None else origin)
    same_as_parent = None
    if row["task_id"] == "echo_reverse" and row["parent_sha"] and source is not None:
        parent_raw = file_bytes(repo, row["parent_sha"], "echo_reverse.py")
        same_as_parent = parent_raw is not None and parent_raw.decode("utf-8") == source
    resident = 1 if row["phase"] == "train" and row["survived"] == 1 else 0
    record = {
        "episode_id": row["id"],
        "generation": row["generation"],
        "agent_id": row["agent_id"],
        "task_id": row["task_id"],
        "phase": row["phase"],
        "tests_passed": row["tests_passed"],
        "tests_total": row["tests_total"],
        "survived": row["survived"],
        "attributable": row["attributable"],
        "gamed": row["gamed"],
        "token_usage": row["token_usage"],
        "tool_calls": row["tool_calls"],
        "wall_time_s": row["wall_time_s"],
        "reuse_score": row["reuse_score"],
        "reuse_events": reuse_n,
        "inspection_events": roles.get("inspection", 0),
        "invocation_events": roles.get("invocation", 0),
        "dependency_events": roles.get("dependency", 0),
        "modification_events": roles.get("modification", 0),
        "evaluator_executions": roles.get("evaluator_execution", 0),
        "commit_present": 1 if row["commit_sha"] else 0,
        "commit_sha": row["commit_sha"],
        "parent_sha": row["parent_sha"],
        "shell_commands": len(calls),
        "inspect_commands": inspects,
        "executions_of_existing": existing,
        "executions_of_new": fresh,
        "git_commit_exit": git_commit_exit,
        "source_origin": measured["origin"],
        "source_bytes_status": measured["bytes_status"],
        "source_bytes": measured["source_bytes"],
        "source_lines": measured["source_lines"],
        "syntax_ok": measured["syntax_ok"],
        "function_count": measured["function_count"],
        "class_count": measured["class_count"],
        "import_count": measured["import_count"],
        "source_form": measured["source_form"],
        "shared_tree_resident": resident,
        "ledger_survived_not_resident": 1 if row["survived"] == 1 and resident == 0 else 0,
        "same_reconstructed_text_as_parent": same_as_parent,
        "entry_origin": entry_origin,
        "entry_form": entry_form(entry_text),
        "entry_bytes": None if entry_text is None else len(entry_text.encode("utf-8")),
    }
    interesting = row["task_id"] in {
        "echo_reverse",
        "kv_get",
        "max_int",
        "is_palindrome",
        "count_lines",
        "sum_even",
        "kv_keys",
        "sum_ints",
    }
    if interesting:
        record["detail"] = {
            "source_text": measured["text"],
            "entry_text": None if entry_text is None else entry_text[:200],
            "commands": [
                {"seq": call["seq"], "exit_code": call["exit_code"], "cmd": call["cmd"][:500]}
                for call in calls
            ],
        }
    return record


def _commit_record(repo: Path, sha: str, episode: dict | None) -> dict:
    numstat = commit_numstat(repo, sha)
    py_paths = [item["path"] for item in numstat if item["path"].endswith(".py")]
    path = py_paths[-1] if py_paths else "echo_reverse.py"
    raw = file_bytes(repo, sha, path)
    text = raw.decode("utf-8") if raw is not None else None
    measured = source_record(text, "git_blob" if text is not None else "absent")
    parent = episode["parent_sha"] if episode else None
    blob = blob_at(repo, sha, path)
    parent_blob = blob_at(repo, parent, path) if parent else None
    prior = earlier_blobs(repo, parent, path) if parent else []
    return {
        "commit_sha": sha,
        "artifact": path,
        "episode_id": episode["episode_id"] if episode else None,
        "generation": episode["generation"] if episode else None,
        "agent_id": episode["agent_id"] if episode else None,
        "task_id": episode["task_id"] if episode else None,
        "parent_sha": parent,
        "files_in_commit": numstat,
        "observed": {
            "source_bytes": measured["source_bytes"],
            "source_lines": measured["source_lines"],
            "files_changed": len(numstat),
            "reuse_events": episode["reuse_events"] if episode else None,
            "inspection_events": episode["inspection_events"] if episode else None,
            "invocation_events": episode["invocation_events"] if episode else None,
            "tests_passed": episode["tests_passed"] if episode else None,
            "tests_total": episode["tests_total"] if episode else None,
            "survived": episode["survived"] if episode else None,
            "blob_sha": blob,
            "parent_blob_sha": parent_blob,
        },
        "derived": {
            "source_form": measured["source_form"],
            "syntax_ok": measured["syntax_ok"],
            "function_count": measured["function_count"],
            "class_count": measured["class_count"],
            "import_count": measured["import_count"],
            "same_blob_as_parent": blob is not None and blob == parent_blob,
            "same_blob_as_an_earlier_commit": blob is not None and blob in prior and blob != parent_blob,
            "copied_from_existing_artifact": False
            if episode and episode["inspect_commands"] == 0 and episode["executions_of_existing"] == 0 and episode["dependency_events"] == 0
            else None,
            "cultural_transmission": "not_established",
        },
        "elemental": {
            "representation": "none",
            "nearest_element": None,
            "distance": None,
        },
        "source_text": measured["text"],
    }
