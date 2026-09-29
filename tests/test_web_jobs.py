import threading

import pytest

from src.web.jobs import JobAlreadyRunningError, JobRegistry


def test_stream_yields_logged_lines_in_order_then_stops():
    registry = JobRegistry()

    def job(print_fn):
        print_fn("linha 1")
        print_fn("linha 2")

    registry.start("extract", job)

    lines = list(registry.stream("extract"))

    assert lines == ["linha 1", "linha 2"]
    assert registry.is_running("extract") is False


def test_start_raises_when_job_already_running():
    registry = JobRegistry()
    release = threading.Event()

    def slow_job(print_fn):
        release.wait(timeout=2)

    registry.start("extract", slow_job)
    try:
        with pytest.raises(JobAlreadyRunningError):
            registry.start("extract", lambda print_fn: None)
    finally:
        release.set()
        list(registry.stream("extract"))  # drena e espera o job terminar


def test_start_allowed_again_after_previous_job_finished():
    registry = JobRegistry()

    registry.start("extract", lambda print_fn: print_fn("primeiro"))
    list(registry.stream("extract"))

    registry.start("extract", lambda print_fn: print_fn("segundo"))
    lines = list(registry.stream("extract"))

    assert lines == ["segundo"]


def test_streaming_an_already_finished_job_again_returns_immediately():
    registry = JobRegistry()

    registry.start("extract", lambda print_fn: print_fn("linha única"))
    first_read = list(registry.stream("extract"))  # drena por completo, incluindo o sentinel

    second_read = list(registry.stream("extract"))

    assert first_read == ["linha única"]
    assert second_read == []


def test_stream_of_unknown_job_name_returns_immediately():
    registry = JobRegistry()

    assert list(registry.stream("does-not-exist")) == []


def test_an_exception_in_the_job_is_logged_instead_of_ending_the_stream_silently():
    # Before the fix, runner() had no except clause: an exception (disk
    # full, permission error, ...) killed the thread, the `finally` still
    # pushed the SSE sentinel, and the stream just stopped with no
    # "Concluído" line and no error line -- indistinguishable from a
    # completed run.
    registry = JobRegistry()

    def failing_job(print_fn):
        print_fn("linha 1")
        raise RuntimeError("disco cheio")

    registry.start("extract", failing_job)

    lines = list(registry.stream("extract"))

    assert lines[0] == "linha 1"
    assert any("disco cheio" in line for line in lines[1:])
    assert registry.is_running("extract") is False
