from agents.prompts import SYSTEM_PROMPT, user_message
from env.limits import Limits


def test_prompt_allows_reuse_and_does_not_teach_the_score():
    text = SYSTEM_PROMPT + user_message("a0", 1, "sum_ints", "Add numbers.", Limits())
    assert "You may inspect and reuse anything available in the lattice." in text
    lowered = text.lower()
    for banned in ("fitness", "survival", "selection", "shock", "held-out", "hidden test"):
        assert banned not in lowered
