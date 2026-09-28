import pytest

from src.retry import with_retry


def test_with_retry_succeeds_after_transient_failures():
    calls = {"count": 0}
    sleeps = []

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ValueError("boom")
        return "ok"

    result = with_retry(flaky, retry_on=(ValueError,), max_attempts=3, base_delay=1.0, sleep=sleeps.append)

    assert result == "ok"
    assert calls["count"] == 3
    assert sleeps == [1.0, 2.0]


def test_with_retry_raises_after_exhausting_attempts():
    def always_fails():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        with_retry(always_fails, retry_on=(ValueError,), max_attempts=2, base_delay=0.1, sleep=lambda s: None)


def test_with_retry_does_not_catch_unrelated_exceptions():
    def raises_type_error():
        raise TypeError("unrelated")

    with pytest.raises(TypeError):
        with_retry(raises_type_error, retry_on=(ValueError,), max_attempts=3, base_delay=0.1, sleep=lambda s: None)
