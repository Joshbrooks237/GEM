"""Task records. Hidden cases stay out of the agent prompt."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    stdin: str
    stdout: str


@dataclass(frozen=True)
class Task:
    id: str
    visible: str
    cases: tuple[Case, ...]
    heldout: bool = False

    def public_text(self) -> str:
        return self.visible
