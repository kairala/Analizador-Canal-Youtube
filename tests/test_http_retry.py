import pytest
from googleapiclient.errors import HttpError

from src.http_retry import NonRetryableApiError, call_with_http_retry


class _FakeResp:
    def __init__(self, status):
        self.status = status
        self.reason = "error"


def _http_error(status):
    return HttpError(_FakeResp(status), b"error body")


def test_call_with_http_retry_retries_on_429_then_succeeds():
    calls = {"count": 0}
    sleeps = []

    def flaky():
        calls["count"] += 1
        if calls["count"] < 2:
            raise _http_error(429)
        return "ok"

    result = call_with_http_retry(flaky, sleep=sleeps.append)

    assert result == "ok"
    assert calls["count"] == 2
    assert sleeps == [1.0]


def test_call_with_http_retry_retries_on_5xx():
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 2:
            raise _http_error(503)
        return "ok"

    result = call_with_http_retry(flaky, sleep=lambda s: None)

    assert result == "ok"
    assert calls["count"] == 2


def test_call_with_http_retry_raises_immediately_on_non_retryable_400():
    calls = {"count": 0}
    sleeps = []

    def always_bad_request():
        calls["count"] += 1
        raise _http_error(400)

    with pytest.raises(NonRetryableApiError):
        call_with_http_retry(always_bad_request, sleep=sleeps.append)

    assert calls["count"] == 1
    assert sleeps == []


def test_call_with_http_retry_raises_after_exhausting_retryable_attempts():
    def always_rate_limited():
        raise _http_error(429)

    with pytest.raises(HttpError):
        call_with_http_retry(always_rate_limited, sleep=lambda s: None)
