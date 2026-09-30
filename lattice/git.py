"""Specimen git repository.

Harness commands pass an explicit environment and `-c` flags so they do not
read or write the operator's global git config.
"""

import os
import shutil
import subprocess
from pathlib import Path

EPOCH = 1_577_836_800  # 2020-01-01 UTC


def git_date(seed: int, generation: int, agent_index: int, step: int) -> str:
    offset = (seed % 100_000) * 1_000_000 + generation * 10_000 + (agent_index + 5) * 100 + step
    return f"{EPOCH + offset} +0000"


def author_env(author: str, date: str) -> dict[str, str]:
    email = f"{author}@pegmatite.local"
    return {
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }


class Repo:
    def __init__(self, path: Path):
        self.path = path
        self.hooks = path.parent / "hooks"
        self.hooks.mkdir(parents=True, exist_ok=True)

    def _base_env(self) -> dict[str, str]:
        home = self.path.parent / "git-home"
        home.mkdir(parents=True, exist_ok=True)
        gitconfig = self.path.parent / "gitconfig"
        if not gitconfig.exists():
            gitconfig.write_text("", encoding="utf-8")
        return {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
            "HOME": str(home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_EDITOR": ":",
            "GIT_PAGER": "cat",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
        }

    def _git(
        self,
        *args: str,
        check: bool = True,
        extra_env: dict[str, str] | None = None,
        input: str | None = None,
    ) -> subprocess.CompletedProcess:
        env = self._base_env()
        if extra_env:
            env.update(extra_env)
        cmd = [
            "git",
            "-C",
            str(self.path),
            "-c",
            "safe.directory=*",
            "-c",
            f"core.hooksPath={self.hooks}",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.pager=cat",
            *args,
        ]
        completed = subprocess.run(
            cmd,
            input=input,
            text=True,
            capture_output=True,
            env=env,
        )
        if check and completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"git {' '.join(args)} failed ({completed.returncode}): {detail}")
        return completed

    @classmethod
    def create(cls, path: Path, date: str) -> "Repo":
        path.mkdir(parents=True, exist_ok=True)
        repo = cls(path)
        repo._git("init", "-b", "main")
        repo._git("config", "--local", "commit.gpgsign", "false")
        repo._git("config", "--local", "core.autocrlf", "false")
        repo.set_author("harness")
        repo._git(
            "commit",
            "--allow-empty",
            "--allow-empty-message",
            "-m",
            "",
            extra_env=author_env("harness", date),
        )
        return repo

    @classmethod
    def open(cls, path: Path) -> "Repo":
        return cls(path)

    def set_author(self, author: str) -> None:
        self._git("config", "--local", "user.name", author)
        self._git("config", "--local", "user.email", f"{author}@pegmatite.local")

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def commit_workdir(self, author: str, date: str, message: str = "") -> str | None:
        self.set_author(author)
        self._git("add", "-A")
        quiet = self._git("diff", "--cached", "--quiet", check=False)
        if quiet.returncode == 0:
            return None
        args = ["commit", "--allow-empty-message", "-m", message]
        completed = self._git(*args, extra_env=author_env(author, date), check=False)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(detail or "git commit failed")
        return self.head()

    def restore_tree(self, source_sha: str, author: str, date: str) -> str | None:
        """Add a commit whose tree matches `source_sha`, keeping history."""
        source_tree = self._git("rev-parse", f"{source_sha}^{{tree}}").stdout.strip()
        self._git("reset", "--hard", "HEAD")
        self._git("clean", "-fd")
        head_tree = self._git("rev-parse", "HEAD^{tree}").stdout.strip()
        if source_tree == head_tree:
            return None
        head = self.head()
        completed = self._git(
            "commit-tree",
            source_tree,
            "-p",
            head,
            "-m",
            "",
            extra_env=author_env(author, date),
            input="",
        )
        sha = completed.stdout.strip()
        self._git("reset", "--hard", sha)
        self._git("clean", "-fd")
        return sha

    def hard_reset(self, sha: str) -> None:
        self._git("reset", "--hard", sha)
        self._git("clean", "-fd")

    def changed(self, older: str, newer: str) -> list[str]:
        completed = self._git("diff", "--name-only", older, newer)
        return [line for line in completed.stdout.splitlines() if line]

    def tracked(self) -> list[str]:
        completed = self._git("ls-files")
        return [line for line in completed.stdout.splitlines() if line]

    def tracked_at(self, sha: str) -> list[str]:
        completed = self._git("ls-tree", "-r", "--name-only", sha)
        return [line for line in completed.stdout.splitlines() if line]

    def exists_at(self, sha: str, path: str) -> bool:
        completed = self._git("cat-file", "-e", f"{sha}:{path}", check=False)
        return completed.returncode == 0

    def file_at(self, sha: str, path: str) -> str | None:
        completed = self._git("show", f"{sha}:{path}", check=False)
        if completed.returncode != 0:
            return None
        return completed.stdout

    def blob_sha(self, path: str) -> str | None:
        full = self.path / path
        if not full.is_file():
            return None
        completed = self._git("hash-object", str(full))
        return completed.stdout.strip()

    def commits_since(self, parent: str) -> list[dict]:
        if parent == self.head():
            return []
        completed = self._git("rev-list", "--reverse", f"{parent}..HEAD")
        return [self.commit_meta(sha) for sha in completed.stdout.splitlines() if sha]

    def commit_meta(self, sha: str) -> dict:
        completed = self._git("show", "-s", "--format=%P%x1f%cI%x1f%B", sha)
        parent, timestamp, message = (completed.stdout.split("\x1f", 2) + ["", ""])[:3]
        parents = parent.split()
        return {
            "sha": sha,
            "parent_sha": parents[0] if parents else None,
            "timestamp": timestamp.strip(),
            "message": message.strip(),
        }

    def file_history(self, sha: str, path: str) -> list[str]:
        completed = self._git(
            "log",
            "--follow",
            "--format=%H",
            sha,
            "--",
            path,
            check=False,
        )
        if completed.returncode != 0:
            return []
        return [line for line in completed.stdout.splitlines() if line]

    def move(self, src: str, dst: str) -> None:
        self._git("mv", src, dst)

    def add_worktree(self, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "--detach", str(dest), "HEAD")

    def remove_worktree(self, dest: Path) -> None:
        self._git("worktree", "remove", "--force", str(dest), check=False)
        self._git("worktree", "prune", check=False)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
