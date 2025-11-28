from src.scheduler import FIFOScheduler, LIFOScheduler


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
