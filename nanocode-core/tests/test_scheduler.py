from src.scheduler import FIFOScheduler, LIFOScheduler, RandomScheduler


def test_fifo_scheduler_preserves_insertion_order():
    scheduler = FIFOScheduler()

    for term_id in ("T1", "T2", "T3"):
        scheduler.push(term_id)

    assert scheduler.pop() == "T1"
    assert scheduler.pop() == "T2"
    assert scheduler.pop() == "T3"
    assert scheduler.pop() is None


def test_lifo_scheduler_reverses_insertion_order():
    scheduler = LIFOScheduler()

    for term_id in ("T1", "T2", "T3"):
        scheduler.push(term_id)

    assert scheduler.pop() == "T3"
    assert scheduler.pop() == "T2"
    assert scheduler.pop() == "T1"
    assert scheduler.pop() is None


def test_random_scheduler_is_seeded_and_reproducible():
    first = RandomScheduler(seed=7)
    second = RandomScheduler(seed=7)

    for term_id in ("T1", "T2", "T3", "T4"):
        first.push(term_id)
        second.push(term_id)

    first_order = [first.pop() for _ in range(4)]
    second_order = [second.pop() for _ in range(4)]

    assert first_order == second_order
    assert sorted(first_order) == ["T1", "T2", "T3", "T4"]


def test_random_scheduler_state_round_trip():
    scheduler = RandomScheduler(seed=2)
    for term_id in ("T1", "T2", "T3"):
        scheduler.push(term_id)

    first_pop = scheduler.pop()
    state = scheduler.state()
    remaining = scheduler.pending()

    rehydrated = RandomScheduler(seed=scheduler.seed, state=state)
    for term_id in remaining:
        rehydrated.push(term_id)

    assert rehydrated.pop() == scheduler.pop()
