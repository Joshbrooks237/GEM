"""Run agent shell commands.

The local runner is a plain subprocess with a scrubbed environment. It is the
right runner for the offline stand-in. A live model should use the Docker
runner, which mounts only the specimen and has no network.
"""

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from env.limits import Limits

IMAGE = "pegmatite-sandbox:local"


@dataclass
class ProcResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def local_env(author: str, date: str, home: Path) -> dict[str, str]:
    """Environment for a sandbox process. Does not inherit API keys."""
    home.mkdir(parents=True, exist_ok=True)
    gitconfig = home / "gitconfig"
    if not gitconfig.exists():
        gitconfig.write_text("", encoding="utf-8")
    email = f"{author}@pegmatite.local"
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "HOME": str(home),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_EDITOR": ":",
        "GIT_PAGER": "cat",
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }


class LocalSandbox:
    def __init__(self, limits: Limits, home: Path):
        self.limits = limits
        self.home = home
        self.commons: Path | None = None
        self.env: dict[str, str] | None = None

    def start(self, commons: Path, author: str, date: str) -> None:
        self.commons = commons
        self.env = local_env(author, date, self.home)

    def run(self, cmd: str, stdin: str = "", timeout: float = 5.0) -> ProcResult:
        if self.commons is None or self.env is None:
            raise RuntimeError("sandbox is not started")
        try:
            completed = subprocess.run(
                ["bash", "-c", cmd],
                input=stdin,
                text=True,
                capture_output=True,
                timeout=timeout,
                cwd=self.commons,
                env=self.env,
            )
            return ProcResult(completed.returncode, completed.stdout, completed.stderr, False)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            return ProcResult(124, stdout, stderr + "\ntimeout", True)

    def stop(self) -> None:
        self.commons = None
        self.env = None


class DockerSandbox:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.cid: str | None = None

    def start(self, commons: Path, author: str, date: str) -> None:
        if shutil.which("docker") is None:
            raise RuntimeError("docker is not installed; use --runner local for the offline stand-in")
        ensure_image()
        name = f"pegmatite-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        email = f"{author}@pegmatite.local"
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "none",
            "--memory",
            self.limits.docker_memory,
            "--cpus",
            self.limits.docker_cpus,
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{commons.resolve()}:/commons",
            "-w",
            "/commons",
            "-e",
            "HOME=/tmp",
            "-e",
            "LANG=C.UTF-8",
            "-e",
            "LC_ALL=C.UTF-8",
            "-e",
            "PYTHONNOUSERSITE=1",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "GIT_CONFIG_NOSYSTEM=1",
            "-e",
            "GIT_TERMINAL_PROMPT=0",
            "-e",
            "GIT_EDITOR=:",
            "-e",
            "GIT_PAGER=cat",
            "-e",
            f"GIT_AUTHOR_NAME={author}",
            "-e",
            f"GIT_AUTHOR_EMAIL={email}",
            "-e",
            f"GIT_COMMITTER_NAME={author}",
            "-e",
            f"GIT_COMMITTER_EMAIL={email}",
            "-e",
            f"GIT_AUTHOR_DATE={date}",
            "-e",
            f"GIT_COMMITTER_DATE={date}",
            IMAGE,
            "sleep",
            "infinity",
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(detail or "docker run failed")
        self.cid = completed.stdout.strip()

    def run(self, cmd: str, stdin: str = "", timeout: float = 5.0) -> ProcResult:
        if not self.cid:
            raise RuntimeError("sandbox is not started")
        try:
            completed = subprocess.run(
                ["docker", "exec", "-i", self.cid, "bash", "-c", cmd],
                input=stdin,
                text=True,
                capture_output=True,
                timeout=timeout + 2,
            )
            return ProcResult(completed.returncode, completed.stdout, completed.stderr, False)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            return ProcResult(124, stdout, stderr + "\ntimeout", True)

    def stop(self) -> None:
        if not self.cid:
            return
        subprocess.run(["docker", "rm", "-f", self.cid], capture_output=True, text=True)
        self.cid = None


def ensure_image() -> None:
    inspect = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        capture_output=True,
        text=True,
    )
    if inspect.returncode == 0:
        return
    dockerfile = Path(__file__).resolve().parent / "Dockerfile"
    build = subprocess.run(
        ["docker", "build", "-t", IMAGE, "-f", str(dockerfile), str(dockerfile.parent)],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        tail = (build.stderr or build.stdout)[-2000:]
        raise RuntimeError(tail or "docker build failed")


def make_sandbox(kind: str, limits: Limits, home: Path):
    if kind == "local":
        return LocalSandbox(limits, home)
    if kind == "docker":
        return DockerSandbox(limits)
    raise ValueError(f"unknown runner {kind}")
