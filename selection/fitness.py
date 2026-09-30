"""Fitness components.

Correctness is a binary gate. Resource efficiency, reuse, and explainability
are stored separately and cannot create a positive score when the gate fails
or when an anti-gaming check zeros that attempt.

Resource efficiency compares an attempt's consumption with the median
consumption of successful attempts in the same generation. The ratio is
capped by ``resource_cap`` so an extreme spend or an extreme saving cannot
outrank the other components. Unsampled artifacts use
``explainability_unsampled`` (benefit of the doubt). Weights are fixed for a
run; they are copied into SQLite at the start and not changed afterward.

Agents are not shown this formula.

consumption =
    token_weight * min(1, tokens / token_budget)
    + tool_weight * min(1, tool_calls / tool_budget)
    + wall_weight * min(1, wall_seconds / wall_budget)

median = median(consumption of successful, non-gamed training attempts)

ratio = resource_cap                          if consumption == 0
      = 0                                     if median == 0 and consumption > 0
      = median / consumption                  otherwise

resource_efficiency = clamp(ratio, 0, resource_cap) / resource_cap

fitness = 0                                   if correctness < 1 or gamed
        = base_pass
          + resource_weight * resource_efficiency
          + reuse_weight * reuse
          + explainability_weight * explainability
"""

import math
from dataclasses import asdict, dataclass

from env.limits import Limits


@dataclass(frozen=True)
class FitnessConfig:
    base_pass: float = 0.60
    resource_weight: float = 0.15
    reuse_weight: float = 0.15
    explainability_weight: float = 0.10
    resource_cap: float = 2.0
    explainability_every: int = 10
    explainability_unsampled: float = 1.0
    consumption_token_weight: float = 0.5
    consumption_tool_weight: float = 0.3
    consumption_wall_weight: float = 0.2

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


DEFAULT_FITNESS = FitnessConfig()


def _frac(used: float, budget: float) -> float:
    if budget <= 0:
        return 1.0
    return min(1.0, max(0.0, used / budget))


def consumption(tokens: int, tool_calls: int, wall_s: float, limits: Limits, cfg: FitnessConfig) -> float:
    value = (
        cfg.consumption_token_weight * _frac(tokens, limits.max_tokens)
        + cfg.consumption_tool_weight * _frac(tool_calls, limits.max_tool_calls)
        + cfg.consumption_wall_weight * _frac(wall_s, limits.max_wall_s)
    )
    return round(value, 6)


def median(values: list[float]) -> float:
    """Deterministic median. Even counts average the two central values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return round(float(ordered[mid]), 6)
    return round((float(ordered[mid - 1]) + float(ordered[mid])) / 2.0, 6)


def resource_efficiency(used: float, median_consumption: float, cfg: FitnessConfig) -> float:
    cap = cfg.resource_cap
    if cap <= 0:
        raise ValueError("resource_cap must be > 0")
    if used <= 0:
        ratio = cap
    elif median_consumption <= 0:
        ratio = 0.0
    else:
        ratio = median_consumption / used
    capped = min(cap, max(0.0, ratio))
    return round(capped / cap, 6)


def reuse_score(distinct_later_episodes: int) -> float:
    if distinct_later_episodes <= 0:
        return 0.0
    return 1.0 - math.exp(-distinct_later_episodes / 2.0)


def explainability_value(sampled: bool, score: float | None, cfg: FitnessConfig) -> float:
    if not sampled or score is None:
        return min(1.0, max(0.0, cfg.explainability_unsampled))
    return min(1.0, max(0.0, score))


def combine(
    correctness: float,
    resource: float,
    reuse: float,
    explainability: float,
    cfg: FitnessConfig,
    gamed: bool = False,
) -> float:
    if gamed or correctness < 1.0:
        return 0.0
    resource = min(1.0, max(0.0, resource))
    reuse = min(1.0, max(0.0, reuse))
    explainability = min(1.0, max(0.0, explainability))
    return round(
        cfg.base_pass
        + cfg.resource_weight * resource
        + cfg.reuse_weight * reuse
        + cfg.explainability_weight * explainability,
        6,
    )
