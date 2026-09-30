from tests.exp3_reference import HELD, PROMPTS, TRAINING, cases_for, solve
from tasks.pool import load_ecology


def test_exp3_pool_matches_the_contracts_and_hides_sentinels():
    training, heldout = load_ecology("exp3")
    assert [task.id for task in training] == sorted(TRAINING)
    assert [task.id for task in heldout] == sorted(HELD)
    public = "\n".join(task.public_text() for task in training)
    for sentinel in ("quill", "moss", "bramble", "scribe", "years=0", "years=4", "years=5", "years=17"):
        assert sentinel not in public
    for task in training:
        assert task.public_text() == PROMPTS[task.id]
        assert [(case.stdin, case.stdout) for case in task.cases] == [
            (item["stdin"], item["stdout"]) for item in cases_for(task.id)
        ]
        for case in task.cases:
            assert solve(task.id, case.stdin) == case.stdout
    for task in heldout:
        for case in task.cases:
            assert solve(task.id, case.stdin) == case.stdout


def test_default_ecology_remains_experiment_2():
    training, heldout = load_ecology("exp2")
    assert len(training) == 7
    assert len(heldout) == 3
    assert "parse" not in {task.id for task in training}
