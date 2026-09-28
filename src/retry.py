import time


def with_retry(fn, *, retry_on=(Exception,), max_attempts=3, base_delay=1.0, sleep=time.sleep):
    attempt = 0
    while True:
        try:
            return fn()
        except retry_on:
            attempt += 1
            if attempt >= max_attempts:
                raise
            sleep(base_delay * (2 ** (attempt - 1)))
