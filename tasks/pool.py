"""Load the task distribution and sample it from the run seed."""

import json
import random
from pathlib import Path

from tasks.task import Case, Task


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases(data: dict) -> tuple[Case, ...]:
    return tuple(Case(item["stdin"], item["stdout"]) for item in data["cases"])


def load_ecology(name: str = "exp2") -> tuple[tuple[Task, ...], tuple[Task, ...]]:
    """exp2 is the original pool. exp3 is the compositional pool and is opt-in."""
    base = Path(__file__).resolve().parent
    if name == "exp2":
        return load_pool(base)
    if name == "exp3":
        return load_pool(base / "exp3")
    raise ValueError(f"unknown ecology: {name}")


def load_pool(root: Path | None = None) -> tuple[tuple[Task, ...], tuple[Task, ...]]:
    root = root or Path(__file__).resolve().parent
    visible = {path.stem: _read(path) for path in sorted((root / "visible").glob("*.json"))}
    hidden = {path.stem: _read(path) for path in sorted((root / "hidden").glob("*.json"))}
    if set(visible) != set(hidden):
        mismatch = set(visible) ^ set(hidden)
        raise RuntimeError(f"visible and hidden task ids differ: {sorted(mismatch)}")
    training = tuple(
        Task(
            task_id,
            visible[task_id]["visible"],
            _cases(hidden[task_id]),
            False,
        )
        for task_id in sorted(visible)
    )
    heldout = tuple(
        Task(data["id"], data["visible"], _cases(data), True)
        for data in (_read(path) for path in sorted((root / "heldout").glob("*.json")))
    )
    return training, heldout


def training_schedule(seed: int, tasks: tuple[Task, ...]) -> tuple[str, ...]:
    ids = sorted(task.id for task in tasks)
    rng = random.Random(seed)
    rng.shuffle(ids)
    return tuple(ids)


def task_id_for(schedule: tuple[str, ...], generation: int, agent_index: int, n_agents: int) -> str:
    index = ((generation - 1) * n_agents + agent_index) % len(schedule)
    return schedule[index]
