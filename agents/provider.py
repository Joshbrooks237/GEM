"""Model calls.

`scripted` is a fixed offline stand-in so the harness can run without a
network. It is not an experimental result. `openai` talks to an
OpenAI-compatible chat endpoint.
"""

import base64
import json
import os
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass

HELPER = textwrap.dedent(
    """\
    def rev(s):
        return s[::-1]

    def add(xs):
        return sum(xs)

    def words(s):
        return s.split()

    def uniq(xs):
        seen = set()
        out = []
        for x in xs:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def maximum(xs):
        return max(xs)

    def kv_map(lines):
        table = {}
        for line in lines:
            if "=" in line:
                key, value = line.split("=", 1)
                table[key] = value
        return table

    def evens_sum(xs):
        return sum(x for x in xs if x % 2 == 0)

    def line_count(s):
        if s == "":
            return 0
        return len(s.splitlines())

    def keys_sorted(lines):
        return sorted(kv_map(lines))
    """
)

SOLUTIONS = {
    "echo_reverse": textwrap.dedent(
        """\
        import sys
        from helper import rev
        data = sys.stdin.read()
        if data.endswith("\\n"):
            print(rev(data[:-1]))
        else:
            sys.stdout.write(rev(data))
        """
    ),
    "sum_ints": textwrap.dedent(
        """\
        import sys
        from helper import add
        print(add(int(x) for x in sys.stdin.read().split()))
        """
    ),
    "count_words": textwrap.dedent(
        """\
        import sys
        from helper import words
        print(len(words(sys.stdin.read())))
        """
    ),
    "unique_keep": textwrap.dedent(
        """\
        import sys
        from helper import uniq
        print(" ".join(uniq(sys.stdin.read().split())))
        """
    ),
    "is_palindrome": textwrap.dedent(
        """\
        import sys
        from helper import rev
        text = sys.stdin.read().strip()
        print("yes" if text == rev(text) else "no")
        """
    ),
    "max_int": textwrap.dedent(
        """\
        import sys
        from helper import maximum
        print(maximum(int(x) for x in sys.stdin.read().split()))
        """
    ),
    "kv_get": textwrap.dedent(
        """\
        import sys
        from helper import kv_map
        lines = sys.stdin.read().splitlines()
        key = lines[0] if lines else ""
        print(kv_map(lines[1:]).get(key, "missing"))
        """
    ),
    "sum_even": textwrap.dedent(
        """\
        import sys
        from helper import evens_sum
        print(evens_sum(int(x) for x in sys.stdin.read().split()))
        """
    ),
    "count_lines": textwrap.dedent(
        """\
        import sys
        from helper import line_count
        print(line_count(sys.stdin.read()))
        """
    ),
    "kv_keys": textwrap.dedent(
        """\
        import sys
        from helper import keys_sorted
        print("\\n".join(keys_sorted(sys.stdin.read().splitlines())))
        """
    ),
}


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int


def _estimate(text: str) -> int:
    return max(1, len(text) // 4)


def parse_action(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _task_id(messages: list[dict]) -> str:
    for message in messages:
        for line in message.get("content", "").splitlines():
            if line.startswith("Task: "):
                return line.split(":", 1)[1].strip()
    raise RuntimeError("task id missing from the prompt")


def _write_command(task_id: str) -> str:
    solution = SOLUTIONS.get(task_id)
    if solution is None:
        raise RuntimeError(f"scripted stand-in has no solution for {task_id}")
    files = {
        "helper.py": HELPER,
        f"{task_id}.py": solution,
        "ENTRY": f"python {task_id}.py\n",
    }
    encoded_files = {
        name: base64.b64encode(body.encode("utf-8")).decode("ascii")
        for name, body in files.items()
    }
    script = (
        "import base64, pathlib\n"
        f"files = {encoded_files!r}\n"
        "helper = pathlib.Path('helper.py')\n"
        "if not helper.exists():\n"
        "    helper.write_bytes(base64.b64decode(files['helper.py']))\n"
        f"for name in ({task_id!r} + '.py', 'ENTRY'):\n"
        "    pathlib.Path(name).write_bytes(base64.b64decode(files[name]))\n"
    )
    wrapped = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return (
        f"python -c \"import base64; exec(base64.b64decode('{wrapped}'))\" "
        f"&& git add -A && (git diff --cached --quiet || git commit -m 't {task_id}')"
    )


class ScriptedProvider:
    """Deterministic policy used when no live model is selected."""

    name = "scripted"

    def complete(self, messages: list[dict], max_tokens: int) -> Completion:
        task_id = _task_id(messages)
        tool_results = sum(
            1
            for message in messages
            if message.get("role") == "user" and message.get("content", "").startswith("Tool result")
        )
        if tool_results == 0:
            command = "git status --porcelain && git log --oneline -n 5"
        elif tool_results == 1:
            command = _write_command(task_id)
        else:
            command = None
        if command is None:
            text = json.dumps({"tool": "done"})
        else:
            text = json.dumps({"tool": "shell", "cmd": command})
        tokens_in = _estimate("\n".join(message.get("content", "") for message in messages))
        return Completion(text=text, tokens_in=tokens_in, tokens_out=_estimate(text))


class OpenAIProvider:
    name = "openai"

    def __init__(self):
        self.key = os.environ.get("PEGMATITE_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not self.key:
            raise RuntimeError("set PEGMATITE_API_KEY or OPENAI_API_KEY")
        self.base = os.environ.get("PEGMATITE_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("PEGMATITE_MODEL", "gpt-4o-mini")

    def complete(self, messages: list[dict], max_tokens: int) -> Completion:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max(16, min(int(max_tokens), 1024)),
            "messages": messages,
        }
        request = urllib.request.Request(
            f"{self.base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"model HTTP {exc.code}: {detail}") from exc
        text = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage") or {}
        tokens_in = int(usage.get("prompt_tokens") or _estimate(json.dumps(messages)))
        tokens_out = int(usage.get("completion_tokens") or _estimate(text))
        return Completion(text=text, tokens_in=tokens_in, tokens_out=tokens_out)


def make_provider(name: str):
    if name == "scripted":
        return ScriptedProvider()
    if name == "openai":
        return OpenAIProvider()
    raise ValueError(f"unknown provider {name}")
