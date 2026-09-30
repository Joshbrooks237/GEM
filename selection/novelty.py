"""Distance from artifacts already kept in the archive.

Novelty is recorded for the scientist. It is not a fitness term and it is
not shown to agents.
"""


def _tokens(text: str) -> set[str]:
    return set(text.split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def novelty_of(text: str, prior_texts: list[str]) -> float:
    tokens = _tokens(text)
    if not tokens:
        return 0.0
    if not prior_texts:
        return 1.0
    nearest = max(jaccard(tokens, _tokens(other)) for other in prior_texts)
    return 1.0 - nearest
