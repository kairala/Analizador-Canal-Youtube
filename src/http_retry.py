import time

from googleapiclient.errors import HttpError

from src.retry import with_retry


class NonRetryableApiError(Exception):
    pass


def _is_retryable(exc: HttpError) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status is None:
        return False
    return status in (403, 429) or status >= 500


def call_with_http_retry(fn, sleep=time.sleep):
    def _guarded():
        try:
            return fn()
        except HttpError as exc:
            if _is_retryable(exc):
                raise
            raise NonRetryableApiError(str(exc)) from exc

    return with_retry(_guarded, retry_on=(HttpError,), sleep=sleep)
