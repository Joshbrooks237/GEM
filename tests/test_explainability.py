from selection.explainability import fresh_messages, is_sampled, sample_key, scripted_explanation
from selection.fitness import FitnessConfig


def test_sampling_is_deterministic_and_near_one_in_ten():
    every = FitnessConfig().explainability_every
    first = [is_sampled(42, f"sha-{i}", "a.py", every) for i in range(500)]
    second = [is_sampled(42, f"sha-{i}", "a.py", every) for i in range(500)]
    assert first == second
    assert sample_key(42, "sha-1", "a.py") == sample_key(42, "sha-1", "a.py")
    rate = sum(first) / len(first)
    assert 0.05 < rate < 0.16


def test_scripted_reading_flags_minified_text_and_not_short_programs():
    assert scripted_explanation("def add(xs):\n    return sum(xs)\n") == (1.0, "readable")
    assert scripted_explanation("x" * 241)[0] == 0.0
    assert scripted_explanation("print(1)\n\0")[0] == 0.0


def test_fresh_prompt_does_not_ask_for_a_documentation_style():
    messages = fresh_messages("print(1)\n", "\n")
    blob = "\n".join(message["content"] for message in messages).lower()
    for banned in ("comment", "docstring", "readme", "naming", "style"):
        assert banned not in blob
    assert "you did not write" in blob
