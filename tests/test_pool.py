from tasks.pool import load_pool, task_id_for, training_schedule


def test_hidden_cases_are_not_in_the_public_text():
    training, heldout = load_pool()
    assert len(training) == 7
    assert len(heldout) == 3
    public = "\n".join(task.public_text() for task in training)
    assert "xylophone" not in public
    assert "9 9 9" not in public
    assert "even integers" not in public
    assert any("even integers" in task.public_text() for task in heldout)


def test_schedule_is_a_function_of_the_seed():
    training, _ = load_pool()
    assert training_schedule(42, training) == training_schedule(42, training)
    assert training_schedule(42, training) != training_schedule(7, training)
    order = training_schedule(42, training)
    assert task_id_for(order, 1, 0, 3) == order[0]
    assert task_id_for(order, 1, 2, 3) == order[2]
