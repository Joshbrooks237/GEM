from env.limits import Limits
from selection.fitness import (
    FitnessConfig,
    combine,
    consumption,
    explainability_value,
    median,
    resource_efficiency,
    reuse_score,
)

CFG = FitnessConfig()


def test_failed_gate_and_gaming_contribute_nothing():
    assert combine(0.0, 1.0, 1.0, 1.0, CFG) == 0.0
    assert combine(0.5, 1.0, 1.0, 1.0, CFG) == 0.0
    assert combine(1.0, 1.0, 1.0, 1.0, CFG, gamed=True) == 0.0


def test_passing_is_worth_more_than_a_perfect_failure():
    opaque = combine(1.0, 0.0, 0.0, 0.0, CFG)
    full = combine(1.0, 1.0, 1.0, 1.0, CFG)
    assert opaque == 0.60
    assert full == 1.0
    assert opaque > combine(0.0, 1.0, 1.0, 1.0, CFG)


def test_weights_come_from_the_run_config():
    custom = FitnessConfig(base_pass=0.5, resource_weight=0.0, reuse_weight=0.0, explainability_weight=0.0)
    assert combine(1.0, 1.0, 1.0, 1.0, custom) == 0.5
    assert combine(1.0, 1.0, 1.0, 1.0, CFG) != combine(1.0, 1.0, 1.0, 1.0, custom)


def test_resource_efficiency_is_capped_against_the_generation_median():
    limits = Limits()
    cheap = consumption(10, 1, 0.1, limits, CFG)
    heavy = consumption(limits.max_tokens, limits.max_tool_calls, limits.max_wall_s, limits, CFG)
    assert cheap < heavy
    assert heavy == 1.0
    assert median([0.2, 0.4, 0.9]) == 0.4
    assert median([0.2, 0.4]) == 0.3
    at_median = resource_efficiency(0.4, 0.4, CFG)
    twice_as_efficient = resource_efficiency(0.2, 0.4, CFG)
    extreme = resource_efficiency(0.01, 0.4, CFG)
    wasteful = resource_efficiency(0.8, 0.4, CFG)
    assert at_median == 0.5
    assert twice_as_efficient == 1.0
    assert extreme == 1.0
    assert wasteful < at_median
    assert 0.0 <= wasteful <= 1.0


def test_unsampled_explainability_is_neutral():
    assert explainability_value(False, None, CFG) == 1.0
    assert explainability_value(True, 0.0, CFG) == 0.0
    assert explainability_value(True, 1.0, CFG) == 1.0


def test_reuse_score_saturates():
    assert reuse_score(0) == 0.0
    assert 0 < reuse_score(1) < reuse_score(4) < 1.0
