"""Sampled readability check.

About one eligible artifact in ten is shown to an agent that did not write
it. The sample is a function of the run seed. Unsampled artifacts are not
punished. The check flags binary or minified text; it does not score
comments, names, or documentation.
"""

import hashlib

from selection.fitness import FitnessConfig

OPAQUE_LINE = 240


def sample_key(seed: int, commit_sha: str, path: str) -> str:
    return hashlib.sha256(f"{seed}:{commit_sha}:{path}".encode("utf-8")).hexdigest()


def is_sampled(seed: int, commit_sha: str, path: str, every: int) -> bool:
    if every < 1:
        raise ValueError("explainability_every must be >= 1")
    bucket = int(sample_key(seed, commit_sha, path)[:8], 16) % every
    return bucket == 0


def scripted_explanation(text: str) -> tuple[float, str]:
    if "\0" in text or any(len(line) > OPAQUE_LINE for line in text.splitlines()):
        return 0.0, "opaque"
    return 1.0, "readable"


def fresh_messages(artifact_text: str, stdin_text: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You did not write the artifact below. "
                "Predict the stdout it produces for the given stdin. "
                "Reply with that stdout only."
            ),
        },
        {
            "role": "user",
            "content": f"STDIN:\n{stdin_text}\n\nARTIFACT:\n{artifact_text[:8000]}",
        },
    ]


def explain(provider, artifact_text: str, stdin_text: str, actual_stdout: str | None, cfg: FitnessConfig) -> tuple[bool, float | None, str]:
    """Return sampled flag is handled by the caller. This scores one fresh reading."""
    del cfg
    if getattr(provider, "name", "") == "scripted":
        score, text = scripted_explanation(artifact_text)
        return True, score, text
    completion = provider.complete(fresh_messages(artifact_text, stdin_text), max_tokens=256)
    predicted = (completion.text or "").replace("\r\n", "\n")
    if actual_stdout is None:
        return True, 0.0, predicted
    score = 1.0 if predicted == actual_stdout.replace("\r\n", "\n") else 0.0
    return True, score, predicted
