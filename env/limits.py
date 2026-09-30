"""Hard budgets for one agent episode."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_tokens: int = 4000
    max_wall_s: float = 90.0
    max_tool_calls: int = 16
    max_output_chars: int = 4000
    test_timeout_s: float = 2.0
    tool_timeout_s: float = 20.0
    docker_memory: str = "256m"
    docker_cpus: str = "1.0"


def clip(text: str | None, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"
