import time

from app.core.limiter import SlidingWindowCounter


def test_sliding_window_enforces_limit():
    counter = SlidingWindowCounter()
    key = "unit:rl:10.0.0.1"
    for i in range(3):
        allowed, remaining = counter.check(key, 3, 60)
        assert allowed is True
        assert remaining == 2 - i
    allowed, remaining = counter.check(key, 3, 60)
    assert allowed is False
    assert remaining == 0


def test_sliding_window_keys_are_independent():
    counter = SlidingWindowCounter()
    assert counter.check("unit:rl:a", 1, 60) == (True, 0)
    allowed, remaining = counter.check("unit:rl:b", 1, 60)
    assert allowed is True
    assert remaining == 0


def test_sliding_window_prunes_old_entries():
    counter = SlidingWindowCounter()
    key = "unit:rl:prune"
    assert counter.check(key, 1, 0)[0] is True
    time.sleep(0.01)
    # window=0 prunes every prior timestamp, so the slot frees up
    allowed, remaining = counter.check(key, 1, 0)
    assert allowed is True
    assert remaining == 0
