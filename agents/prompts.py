"""What an agent is told.

The prompt states the task and the hard budget. It does not state the
fitness formula, and it does not say that reuse will be rewarded.
"""

from env.limits import Limits

SYSTEM_PROMPT = (
    "You solve one programming task in a shared git repository.\n"
    "The repository is the current working directory.\n"
    "Solve the assigned task within your resource budget.\n"
    "You may inspect and reuse anything available in the lattice.\n"
    "You may run shell commands, including git status, git diff, git log, "
    "git show, git add, and git commit.\n"
    "The program you leave behind must read stdin and write stdout.\n"
    "Put the exact command that runs that program into a file named ENTRY, "
    "as a single line.\n"
    "Commit your changes, then stop.\n"
    "\n"
    "Each response must be one JSON object and nothing else.\n"
    'To run a command: {"tool": "shell", "cmd": "<command>"}\n'
    'To stop: {"tool": "done"}\n'
)


def user_message(agent_id: str, generation: int, task_id: str, visible: str, limits: Limits) -> str:
    return (
        f"Agent: {agent_id}\n"
        f"Generation: {generation}\n"
        f"Task: {task_id}\n"
        f"Token budget: {limits.max_tokens}\n"
        f"Tool-call budget: {limits.max_tool_calls}\n"
        f"Wall-clock budget seconds: {limits.max_wall_s}\n"
        "\n"
        f"{visible.rstrip()}\n"
    )


def tool_message(exit_code: int, stdout: str, stderr: str) -> str:
    return f"Tool result exit={exit_code}\nstdout:\n{stdout}\nstderr:\n{stderr}"
