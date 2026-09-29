import queue
import threading
from typing import Callable, Iterator


class JobAlreadyRunningError(Exception):
    pass


class JobRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def start(self, name: str, target: Callable[[Callable[[str], None]], None]) -> None:
        with self._lock:
            existing = self._jobs.get(name)
            if existing and existing["running"]:
                raise JobAlreadyRunningError(f"o job '{name}' já está em execução")

            job_queue: queue.Queue = queue.Queue()
            state = {"queue": job_queue, "running": True}
            self._jobs[name] = state

        def log(line: str) -> None:
            job_queue.put(line)

        def runner() -> None:
            try:
                target(log)
            except Exception as exc:
                # Without this, an exception here (disk full, permission
                # error, etc.) kills the thread silently: the `finally`
                # below still pushes the SSE sentinel, so the stream just
                # stops with no "Concluído" line and no error line -- the
                # user can't tell a crash from a completed run.
                log(f"erro inesperado no job '{name}': {exc}")
            finally:
                job_queue.put(None)
                with self._lock:
                    state["running"] = False

        threading.Thread(target=runner, daemon=True).start()

    def is_running(self, name: str) -> bool:
        with self._lock:
            job = self._jobs.get(name)
            return bool(job and job["running"])

    def stream(self, name: str) -> Iterator[str]:
        job = self._jobs.get(name)
        if job is None:
            return

        job_queue = job["queue"]
        while True:
            try:
                line = job_queue.get(timeout=0.1)
            except queue.Empty:
                with self._lock:
                    if not job["running"]:
                        return
                continue

            if line is None:
                return
            yield line
