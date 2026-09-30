"""A shock is an environmental change, not an instruction to the agents."""

from typing import Protocol

from lattice.git import Repo


class Shock(Protocol):
    name: str

    def apply(self, repo: Repo, ledger, run_id: str, generation: int, date: str) -> dict:
        """Change the specimen. Return a JSON-ready description."""
