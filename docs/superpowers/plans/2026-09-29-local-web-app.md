# Local Web App + Packaged Binary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing YouTube extractor (`main.py`) and AI report generator (`analyze.py`) in a local FastAPI web UI running inside a native `pywebview` window, and package it as a double-clickable binary for macOS and Windows via PyInstaller.

**Architecture:** A new `src/web/` FastAPI backend exposes the extractor/analyzer as HTTP + SSE endpoints, reusing their core per-video loops — extracted into `src/extract_core.py` and `src/analyze_core.py` — unchanged in behavior. A plain HTML/CSS/JS frontend under `static/` talks to those endpoints. `desktop.py` starts the server in a background thread and opens a `pywebview` window pointed at it. PyInstaller + a GitHub Actions matrix produce the macOS and Windows binaries.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, pywebview, platformdirs, PyInstaller, plain HTML/CSS/JS (no frontend build step), pytest + FastAPI `TestClient`/httpx.

**Spec:** `docs/superpowers/specs/2026-09-29-local-web-app-design.md`

## Global Constraints

- Packaged-app credentials (`client_secret.json`, `token.json`, the Anthropic key) live in the platform user-data directory via `platformdirs.user_data_dir("yt-data-extractor")` — never the project root. The CLI scripts (`main.py`/`analyze.py`) keep reading from the project root, unchanged.
- PyInstaller cannot cross-compile — the macOS binary is built on a macOS runner, the Windows binary on a Windows runner (CI matrix), never cross-built.
- No frontend build step or UI framework — `static/` is plain HTML/CSS/JS served as-is.
- Only one job of a given kind (`extract` or `analyze`) may run at a time. A second start attempt while one is in-flight is rejected with a clear error, never silently queued or allowed to race.
- The web layer reuses `main.run()`'s and `analyze.run()`'s existing per-video loop bodies via `src/extract_core.py`/`src/analyze_core.py` rather than reimplementing extraction/analysis logic. After the refactor, `main.py` and `analyze.py` keep working exactly as before — their existing test suites must still pass.

## Review Focus

- Reconnecting to an SSE stream (e.g. browser refresh) after that job already finished must return immediately instead of hanging forever on an already-drained queue. (Task 4)
- Submitting the Setup form with a blank Anthropic API key must not be reported as "configured" — a blank key saved to `.env` would silently break every later analyze call without the user noticing at setup time. (Task 3)
- Selecting a mix of valid and invalid video ids for extraction must process only the valid ones, not silently drop the whole batch or error out entirely. (Task 6)
- Browsing a `video_id` that has extraction data but no generated report yet (or vice versa) must render the half that exists instead of 404ing or crashing. (Task 8)
- Starting a second extract/analyze job while one of the same kind is already running must be rejected with a clear "already running" response, not silently queued or allowed to race two loops writing the same files. (Task 4, Task 6)

---

### Task 1: Extract shared per-video extraction loop into `src/extract_core.py`

**Files:**
- Create: `src/extract_core.py`
- Modify: `main.py`
- Modify: `tests/test_main.py`
- Test: `tests/test_extract_core.py`

**Interfaces:**
- Consumes: `analytics_date_range` (`src/date_ranges.py`, exists), `run_report`/`shape_report_result` (`src/youtube_analytics.py`, exists), `assemble_video_document`/`save_video_report` (`src/storage.py`, exists), `REPORTS` (`src/reports.py`, exists).
- Produces: `extract_video(analytics_service, video, today, report_defs=REPORTS, print_fn=print) -> dict`, `extract_selected_videos(analytics_service, output_dir: Path, today: date, selected_videos: list[dict], print_fn=print, report_defs=REPORTS) -> tuple[list[dict], list[str]]`. Used by Task 6 (`src/web/extract_routes.py`) and re-exported from `main.py` for backward compatibility.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_extract_core.py
from datetime import date

from src.extract_core import extract_selected_videos, extract_video


class ScriptedAnalyticsService:
    """Fake analytics client whose response/behavior depends on the query kwargs."""

    def __init__(self, responder):
        self._responder = responder
        self._kwargs = None

    def reports(self):
        return self

    def query(self, **kwargs):
        self._kwargs = kwargs
        return self

    def execute(self):
        return self._responder(self._kwargs)


def _always_empty_responder(_kwargs):
    return {"columnHeaders": [], "rows": []}


def test_extract_video_keeps_going_when_one_report_fails_or_is_empty():
    def responder(kwargs):
        if "insightTrafficSourceType" in kwargs.get("dimensions", ""):
            raise RuntimeError("quota exceeded")
        if kwargs.get("dimensions") == "day":
            return {"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": []}
        if not kwargs.get("dimensions"):
            return {"columnHeaders": [{"name": "views"}], "rows": [[100]]}
        return {"columnHeaders": [{"name": kwargs["dimensions"]}], "rows": [["x"]]}

    service = ScriptedAnalyticsService(responder)
    video = {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}
    messages = []

    result = extract_video(service, video, date(2024, 2, 1), print_fn=messages.append)

    assert result["totals"] == {"views": 100}
    assert result["daily"] == []
    assert result["traffic_sources"] == []
    assert any("traffic_sources" in message for message in messages)
    assert result["errors"] == {"traffic_sources": "quota exceeded"}


def test_extract_selected_videos_saves_each_and_returns_documents(tmp_path):
    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z"},
    ]
    service = ScriptedAnalyticsService(_always_empty_responder)

    documents, failed_ids = extract_selected_videos(
        service, tmp_path, date(2024, 2, 1), videos, print_fn=lambda _m: None
    )

    assert len(documents) == 2
    assert failed_ids == []
    assert (tmp_path / "por_video" / "vid1.json").exists()
    assert (tmp_path / "por_video" / "vid2.json").exists()


def test_extract_selected_videos_continues_when_saving_one_video_fails(tmp_path, monkeypatch):
    import src.extract_core as extract_core_module

    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z"},
    ]
    service = ScriptedAnalyticsService(_always_empty_responder)

    real_save = extract_core_module.save_video_report

    def flaky_save(output_dir, video_id, document):
        if video_id == "vid1":
            raise OSError("disk full")
        return real_save(output_dir, video_id, document)

    monkeypatch.setattr(extract_core_module, "save_video_report", flaky_save)

    documents, failed_ids = extract_selected_videos(
        service, tmp_path, date(2024, 2, 1), videos, print_fn=lambda _m: None
    )

    assert failed_ids == ["vid1"]
    assert len(documents) == 1
    assert documents[0]["video"]["id"] == "vid2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extract_core.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.extract_core'`

- [ ] **Step 3: Write the implementation**

```python
# src/extract_core.py
from datetime import date
from pathlib import Path

from src.date_ranges import analytics_date_range
from src.reports import REPORTS
from src.storage import assemble_video_document, save_video_report
from src.youtube_analytics import run_report, shape_report_result


def extract_video(analytics_service, video, today, report_defs=REPORTS, print_fn=print):
    start_date, end_date = analytics_date_range(video["published_at"], today)
    shaped = {}
    errors = {}
    for report_def in report_defs:
        try:
            rows = run_report(analytics_service, video["id"], start_date, end_date, report_def)
        except Exception as exc:
            print_fn(f"  aviso: falha ao extrair '{report_def.name}' para {video['id']}: {exc}")
            rows = []
            errors[report_def.name] = str(exc)
        shaped[report_def.name] = shape_report_result(report_def, rows)
    if errors:
        shaped["errors"] = errors
    return shaped


def extract_selected_videos(
    analytics_service,
    output_dir: Path,
    today: date,
    selected_videos: list[dict],
    print_fn=print,
    report_defs=REPORTS,
) -> tuple[list[dict], list[str]]:
    documents = []
    failed_ids = []
    for video in selected_videos:
        print_fn(f"Processando '{video['title']}' ({video['id']})...")
        try:
            shaped_reports = extract_video(analytics_service, video, today, report_defs, print_fn=print_fn)
            document = assemble_video_document(video, shaped_reports)
            save_video_report(output_dir, video["id"], document)
            documents.append(document)
        except Exception as exc:
            print_fn(f"  erro ao processar {video['id']}, pulando: {exc}")
            failed_ids.append(video["id"])
    return documents, failed_ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extract_core.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Update `main.py` to reuse the extracted functions**

Replace `main.py`'s current `extract_video` definition and `run()` body with:

```python
# main.py
from datetime import date
from pathlib import Path

from googleapiclient.discovery import build

from src.auth import SCOPES, get_credentials
from src.extract_core import extract_selected_videos, extract_video
from src.reports import REPORTS
from src.selection import parse_selection
from src.storage import save_channel_videos_snapshot, save_consolidated
from src.youtube_data import list_channel_videos


def select_videos(videos, input_fn=input, print_fn=print):
    print_fn("Vídeos encontrados:")
    for i, video in enumerate(videos, start=1):
        published_date = video.get("published_at", "")[:10]
        print_fn(f"[{i}] {video['title']} (publicado em {published_date}) - ID: {video['id']}")

    while True:
        raw = input_fn("Digite o número do vídeo, vários separados por vírgula, ou 'todos': ")
        try:
            indices = parse_selection(raw, len(videos))
            return [videos[i - 1] for i in indices]
        except ValueError as exc:
            print_fn(f"Entrada inválida: {exc}. Tente novamente.")


def run(
    youtube_service,
    analytics_service,
    output_dir: Path,
    today: date,
    input_fn=input,
    print_fn=print,
    report_defs=REPORTS,
):
    videos = list_channel_videos(youtube_service)
    save_channel_videos_snapshot(output_dir, videos)

    if not videos:
        print_fn("Nenhum vídeo encontrado no canal.")
        return

    selected = select_videos(videos, input_fn=input_fn, print_fn=print_fn)

    documents, failed_ids = extract_selected_videos(
        analytics_service, output_dir, today, selected, print_fn=print_fn, report_defs=report_defs
    )

    if documents:
        save_consolidated(output_dir, documents, today.isoformat())

    print_fn(f"Concluído: {len(documents)} vídeo(s) processado(s), {len(failed_ids)} com erro.")
    if failed_ids:
        print_fn(f"Vídeos com erro: {', '.join(failed_ids)}")


def main():
    client_secret_path = Path("client_secret.json")
    token_path = Path("token.json")
    credentials = get_credentials(client_secret_path, token_path, SCOPES)

    youtube_service = build("youtube", "v3", credentials=credentials)
    analytics_service = build("youtubeAnalytics", "v2", credentials=credentials)

    run(youtube_service, analytics_service, Path("output"), date.today())


if __name__ == "__main__":
    main()
```

Note: `extract_video` is imported (not redefined) so `from main import extract_video` in existing tests keeps working unchanged.

- [ ] **Step 6: Update `tests/test_main.py`'s two `save_video_report`-monkeypatching tests**

The loop that calls `save_video_report` now lives in `src/extract_core.py`, so patch it there instead of on `main_module`. In `tests/test_main.py`, replace:

```python
def test_run_continues_when_saving_one_video_fails(tmp_path, monkeypatch):
    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT1M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z", "duration": "PT2M"},
    ]
    youtube_service = FakeYouTubeService(videos)
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)

    real_save_video_report = main_module.save_video_report

    def flaky_save(output_dir, video_id, document):
        if video_id == "vid1":
            raise OSError("disk full")
        return real_save_video_report(output_dir, video_id, document)

    monkeypatch.setattr(main_module, "save_video_report", flaky_save)
```

with:

```python
def test_run_continues_when_saving_one_video_fails(tmp_path, monkeypatch):
    import src.extract_core as extract_core_module

    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT1M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z", "duration": "PT2M"},
    ]
    youtube_service = FakeYouTubeService(videos)
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)

    real_save_video_report = extract_core_module.save_video_report

    def flaky_save(output_dir, video_id, document):
        if video_id == "vid1":
            raise OSError("disk full")
        return real_save_video_report(output_dir, video_id, document)

    monkeypatch.setattr(extract_core_module, "save_video_report", flaky_save)
```

(the rest of that test function is unchanged). And replace:

```python
def test_run_prints_summary_and_failed_ids_even_when_all_videos_fail(tmp_path, monkeypatch):
    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT1M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z", "duration": "PT2M"},
    ]
    youtube_service = FakeYouTubeService(videos)
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)

    def always_fails(output_dir, video_id, document):
        raise OSError("disk full")

    monkeypatch.setattr(main_module, "save_video_report", always_fails)
    messages = []
```

with:

```python
def test_run_prints_summary_and_failed_ids_even_when_all_videos_fail(tmp_path, monkeypatch):
    import src.extract_core as extract_core_module

    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT1M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z", "duration": "PT2M"},
    ]
    youtube_service = FakeYouTubeService(videos)
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)

    def always_fails(output_dir, video_id, document):
        raise OSError("disk full")

    monkeypatch.setattr(extract_core_module, "save_video_report", always_fails)
    messages = []
```

(the rest of that test function is unchanged).

- [ ] **Step 7: Run the full test suite to confirm no regressions**

Run: `pytest -v`
Expected: all tests PASS, including every test in `tests/test_main.py` unchanged in behavior.

- [ ] **Step 8: Commit**

```bash
git add src/extract_core.py main.py tests/test_main.py tests/test_extract_core.py
git commit -m "refactor: extract shared per-video extraction loop into src/extract_core.py"
```

---

### Task 2: Extract shared per-video analysis loop into `src/analyze_core.py`

**Files:**
- Create: `src/analyze_core.py`
- Modify: `analyze.py`
- Test: `tests/test_analyze_core.py`

**Interfaces:**
- Consumes: `generate_report` (`src/ai_report.py`, exists).
- Produces: `analyze_selected_documents(client, selected_documents: list[dict], channel_averages: dict, reports_dir: Path, print_fn=print) -> tuple[list[str], list[str]]` (processed video ids, failed video ids). Used by Task 7 (`src/web/analyze_routes.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_analyze_core.py
import json

from src.analyze_core import analyze_selected_documents


class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _StreamContext:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self._response


class ScriptedMessages:
    def __init__(self, responder):
        self._responder = responder

    def stream(self, **kwargs):
        return _StreamContext(self._responder(kwargs))


class ScriptedClient:
    def __init__(self, responder):
        self.messages = ScriptedMessages(responder)


def _always_ok_responder(_kwargs):
    return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])


def test_analyze_selected_documents_writes_a_report_per_video(tmp_path):
    documents = [
        {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}},
        {"video": {"id": "vid2", "title": "Video 2"}, "totals": {"views": 200}},
    ]
    client = ScriptedClient(_always_ok_responder)
    reports_dir = tmp_path / "reports"

    processed_ids, failed_ids = analyze_selected_documents(
        client, documents, {"views": 150}, reports_dir, print_fn=lambda _m: None
    )

    assert processed_ids == ["vid1", "vid2"]
    assert failed_ids == []
    assert (reports_dir / "vid1.md").exists()
    assert "Resumo de desempenho" in (reports_dir / "vid1.md").read_text(encoding="utf-8")


def test_analyze_selected_documents_continues_when_one_video_fails(tmp_path):
    documents = [
        {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}},
        {"video": {"id": "vid2", "title": "Video 2"}, "totals": {"views": 200}},
    ]

    def responder(kwargs):
        if "vid1" in kwargs["messages"][0]["content"]:
            raise RuntimeError("rate limited")
        return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])

    client = ScriptedClient(responder)
    reports_dir = tmp_path / "reports"
    messages = []

    processed_ids, failed_ids = analyze_selected_documents(
        client, documents, {}, reports_dir, print_fn=messages.append
    )

    assert processed_ids == ["vid2"]
    assert failed_ids == ["vid1"]
    assert not (reports_dir / "vid1.md").exists()
    assert (reports_dir / "vid2.md").exists()
    assert any("erro" in m.lower() and "vid1" in m for m in messages)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyze_core.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.analyze_core'`

- [ ] **Step 3: Write the implementation**

```python
# src/analyze_core.py
from pathlib import Path

from src.ai_report import generate_report


def analyze_selected_documents(
    client,
    selected_documents: list[dict],
    channel_averages: dict,
    reports_dir: Path,
    print_fn=print,
) -> tuple[list[str], list[str]]:
    processed_ids = []
    failed_ids = []
    for document in selected_documents:
        video = document.get("video", {})
        video_id = video.get("id", "desconhecido")
        print_fn(f"Analisando '{video.get('title', video_id)}' ({video_id})...")
        try:
            report_text = generate_report(client, document, channel_averages)
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / f"{video_id}.md").write_text(report_text, encoding="utf-8")
            processed_ids.append(video_id)
        except Exception as exc:
            print_fn(f"  erro ao analisar {video_id}, pulando: {exc}")
            failed_ids.append(video_id)
    return processed_ids, failed_ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyze_core.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Update `analyze.py` to reuse the extracted function**

Replace `analyze.py`'s `run()` body:

```python
# analyze.py
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.analyze_core import analyze_selected_documents
from src.report_data import compute_channel_averages, load_video_documents
from src.selection import parse_selection


def select_videos(documents, input_fn=input, print_fn=print):
    print_fn("Vídeos já extraídos disponíveis para análise:")
    for i, document in enumerate(documents, start=1):
        video = document.get("video", {})
        print_fn(f"[{i}] {video.get('title', '(sem título)')} - ID: {video.get('id', '?')}")

    while True:
        raw = input_fn("Digite o número do vídeo, vários separados por vírgula, ou 'todos': ")
        try:
            indices = parse_selection(raw, len(documents))
            return [documents[i - 1] for i in indices]
        except ValueError as exc:
            print_fn(f"Entrada inválida: {exc}. Tente novamente.")


def run(client, output_dir: Path, reports_dir: Path, input_fn=input, print_fn=print):
    documents = load_video_documents(output_dir)

    if not documents:
        print_fn(
            f"Nenhum vídeo extraído encontrado em {output_dir / 'por_video'}. "
            "Rode 'python main.py' primeiro para extrair os dados."
        )
        return

    channel_averages = compute_channel_averages(documents)
    selected = select_videos(documents, input_fn=input_fn, print_fn=print_fn)

    processed_ids, failed_ids = analyze_selected_documents(
        client, selected, channel_averages, reports_dir, print_fn=print_fn
    )

    print_fn(f"Concluído: {len(processed_ids)} relatório(s) gerado(s), {len(failed_ids)} com erro.")
    if failed_ids:
        print_fn(f"Vídeos com erro: {', '.join(failed_ids)}")


def main():
    load_dotenv()
    client = anthropic.Anthropic()
    run(client, Path("output"), Path("reports"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `pytest -v`
Expected: all tests PASS, including every test in `tests/test_analyze.py` unchanged (it does not monkeypatch anything that moved).

- [ ] **Step 7: Commit**

```bash
git add src/analyze_core.py analyze.py tests/test_analyze_core.py
git commit -m "refactor: extract shared per-video analysis loop into src/analyze_core.py"
```

---

### Task 3: FastAPI app skeleton, app data directory, and credential setup endpoints

**Files:**
- Modify: `requirements.txt`
- Create: `src/web/__init__.py`
- Create: `src/web/paths.py`
- Create: `src/web/setup.py`
- Create: `src/web/app.py`
- Test: `tests/test_web_paths.py`
- Test: `tests/test_web_setup.py`

**Interfaces:**
- Produces: `app_data_dir() -> Path` (`src/web/paths.py`), a FastAPI `router` (`src/web/setup.py`) mounted at `/api/setup`, `create_app() -> FastAPI` (`src/web/app.py`). Used by Tasks 5-9.

- [ ] **Step 1: Add web dependencies to `requirements.txt`**

```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
pytest>=7.4.0
anthropic>=1.9.0
python-dotenv>=1.0.0
fastapi>=0.115.0
uvicorn>=0.30.0
platformdirs>=4.0.0
httpx>=0.27.0
```

- [ ] **Step 2: Install the new dependencies**

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: install completes with no errors.

- [ ] **Step 3: Create `src/web/__init__.py`**

```python
# src/web/__init__.py
```

- [ ] **Step 4: Write the failing test for `app_data_dir`**

```python
# tests/test_web_paths.py
from src.web.paths import app_data_dir


def test_app_data_dir_creates_and_returns_a_directory(monkeypatch, tmp_path):
    target = tmp_path / "yt-data-extractor"
    monkeypatch.setattr("platformdirs.user_data_dir", lambda _appname: str(target))

    result = app_data_dir()

    assert result == target
    assert result.is_dir()
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/test_web_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.web.paths'`

- [ ] **Step 6: Write `src/web/paths.py`**

```python
# src/web/paths.py
from pathlib import Path

import platformdirs


def app_data_dir() -> Path:
    path = Path(platformdirs.user_data_dir("yt-data-extractor"))
    path.mkdir(parents=True, exist_ok=True)
    return path
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_web_paths.py -v`
Expected: PASS (1 passed)

- [ ] **Step 8: Write the failing tests for the setup endpoints**

```python
# tests/test_web_setup.py
import json

from fastapi.testclient import TestClient

import src.web.setup as setup_module
from src.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_module, "app_data_dir", lambda: tmp_path)
    return TestClient(create_app())


def test_status_reports_not_configured_when_nothing_saved(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/setup/status")

    assert response.status_code == 200
    assert response.json() == {"client_secret_configured": False, "anthropic_key_configured": False}


def test_save_setup_persists_files_and_status_reflects_it(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {
        "client_secret_json": json.dumps({"installed": {"client_id": "abc"}}),
        "anthropic_api_key": "sk-test-123",
    }

    response = client.post("/api/setup", json=payload)

    assert response.status_code == 200
    assert (tmp_path / "client_secret.json").read_text(encoding="utf-8") == payload["client_secret_json"]
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=sk-test-123\n"

    status = client.get("/api/setup/status").json()
    assert status == {"client_secret_configured": True, "anthropic_key_configured": True}


def test_save_setup_rejects_invalid_json(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/setup", json={"client_secret_json": "not-json", "anthropic_api_key": "sk-test"}
    )

    assert response.status_code == 400
    assert not (tmp_path / "client_secret.json").exists()


def test_save_setup_rejects_blank_anthropic_key(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {
        "client_secret_json": json.dumps({"installed": {"client_id": "abc"}}),
        "anthropic_api_key": "   ",
    }

    response = client.post("/api/setup", json=payload)

    assert response.status_code == 400
    assert not (tmp_path / ".env").exists()

    status = client.get("/api/setup/status").json()
    assert status["anthropic_key_configured"] is False
```

- [ ] **Step 9: Run tests to verify they fail**

Run: `pytest tests/test_web_setup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.web.setup'` (and `src.web.app`)

- [ ] **Step 10: Write `src/web/setup.py`**

```python
# src/web/setup.py
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.web.paths import app_data_dir

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupPayload(BaseModel):
    client_secret_json: str
    anthropic_api_key: str


def _client_secret_path(data_dir: Path) -> Path:
    return data_dir / "client_secret.json"


def _env_path(data_dir: Path) -> Path:
    return data_dir / ".env"


@router.get("/status")
def get_status():
    data_dir = app_data_dir()
    return {
        "client_secret_configured": _client_secret_path(data_dir).exists(),
        "anthropic_key_configured": _env_path(data_dir).exists(),
    }


@router.post("")
def save_setup(payload: SetupPayload):
    data_dir = app_data_dir()

    try:
        json.loads(payload.client_secret_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"client_secret.json inválido: {exc}")

    api_key = payload.anthropic_api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="a chave da API Anthropic não pode ficar em branco")

    _client_secret_path(data_dir).write_text(payload.client_secret_json, encoding="utf-8")
    _env_path(data_dir).write_text(f"ANTHROPIC_API_KEY={api_key}\n", encoding="utf-8")
    return {"ok": True}
```

- [ ] **Step 11: Write `src/web/app.py`**

```python
# src/web/app.py
from fastapi import FastAPI

from src.web.setup import router as setup_router


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Analytics Extractor")
    app.include_router(setup_router)
    return app
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `pytest tests/test_web_setup.py -v`
Expected: PASS (4 passed)

- [ ] **Step 13: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 14: Commit**

```bash
git add requirements.txt src/web/__init__.py src/web/paths.py src/web/setup.py src/web/app.py tests/test_web_paths.py tests/test_web_setup.py
git commit -m "feat: add FastAPI app skeleton and credential setup endpoints"
```

---

### Task 4: Background job registry with SSE-friendly log streaming

**Files:**
- Create: `src/web/jobs.py`
- Test: `tests/test_web_jobs.py`

**Interfaces:**
- Produces: `JobAlreadyRunningError` (exception), `JobRegistry` with `.start(name: str, target: Callable[[Callable[[str], None]], None]) -> None`, `.is_running(name: str) -> bool`, `.stream(name: str) -> Iterator[str]`. Used by Tasks 6 and 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_jobs.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.web.jobs'`

- [ ] **Step 3: Write the implementation**

```python
# src/web/jobs.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_jobs.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/web/jobs.py tests/test_web_jobs.py
git commit -m "feat: add background job registry with SSE-friendly log streaming"
```

---

### Task 5: Service dependency providers (YouTube, Analytics, Anthropic clients)

**Files:**
- Create: `src/web/services.py`
- Test: `tests/test_web_services.py`

**Interfaces:**
- Consumes: `get_credentials`, `SCOPES` (`src/auth.py`, exists), `app_data_dir` (Task 3).
- Produces: `get_youtube_service()`, `get_analytics_service()`, `get_anthropic_client()` — plain callables usable directly or as FastAPI `Depends(...)` targets. Used by Tasks 6 and 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_services.py
import src.web.services as services_module


def test_get_youtube_service_uses_app_data_dir_paths_and_correct_api(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "app_data_dir", lambda: tmp_path)

    captured = {}

    def fake_get_credentials(client_secret_path, token_path, scopes):
        captured["client_secret_path"] = client_secret_path
        captured["token_path"] = token_path
        captured["scopes"] = scopes
        return "fake-creds"

    def fake_build(api_name, api_version, credentials):
        captured["api_name"] = api_name
        captured["api_version"] = api_version
        captured["credentials"] = credentials
        return f"{api_name}-{api_version}-service"

    monkeypatch.setattr(services_module, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(services_module, "build", fake_build)

    result = services_module.get_youtube_service()

    assert result == "youtube-v3-service"
    assert captured["client_secret_path"] == tmp_path / "client_secret.json"
    assert captured["token_path"] == tmp_path / "token.json"
    assert captured["credentials"] == "fake-creds"


def test_get_analytics_service_uses_youtubeanalytics_v2(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(services_module, "get_credentials", lambda *a, **k: "fake-creds")
    monkeypatch.setattr(
        services_module, "build", lambda api_name, api_version, credentials: (api_name, api_version)
    )

    result = services_module.get_analytics_service()

    assert result == ("youtubeAnalytics", "v2")


def test_get_anthropic_client_reads_api_key_from_app_data_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test-999\n", encoding="utf-8")
    monkeypatch.setattr(services_module, "app_data_dir", lambda: tmp_path)

    captured = {}

    class FakeAnthropic:
        def __init__(self, api_key=None):
            captured["api_key"] = api_key

    monkeypatch.setattr(services_module.anthropic, "Anthropic", FakeAnthropic)

    services_module.get_anthropic_client()

    assert captured["api_key"] == "sk-test-999"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_services.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.web.services'`

- [ ] **Step 3: Write the implementation**

```python
# src/web/services.py
import anthropic
from dotenv import dotenv_values
from googleapiclient.discovery import build

from src.auth import SCOPES, get_credentials
from src.web.paths import app_data_dir


def get_youtube_service():
    data_dir = app_data_dir()
    credentials = get_credentials(data_dir / "client_secret.json", data_dir / "token.json", SCOPES)
    return build("youtube", "v3", credentials=credentials)


def get_analytics_service():
    data_dir = app_data_dir()
    credentials = get_credentials(data_dir / "client_secret.json", data_dir / "token.json", SCOPES)
    return build("youtubeAnalytics", "v2", credentials=credentials)


def get_anthropic_client():
    data_dir = app_data_dir()
    env = dotenv_values(data_dir / ".env")
    return anthropic.Anthropic(api_key=env.get("ANTHROPIC_API_KEY"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_services.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/web/services.py tests/test_web_services.py
git commit -m "feat: add YouTube/Analytics/Anthropic service dependency providers"
```

---

### Task 6: Extract endpoints (list videos, start extraction, stream progress)

**Files:**
- Create: `src/web/extract_routes.py`
- Modify: `src/web/app.py`
- Test: `tests/test_web_extract.py`

**Interfaces:**
- Consumes: `extract_selected_videos` (Task 1), `save_channel_videos_snapshot`/`save_consolidated` (`src/storage.py`, exists), `list_channel_videos` (`src/youtube_data.py`, exists), `JobAlreadyRunningError` (Task 4), `get_youtube_service`/`get_analytics_service` (Task 5), `app_data_dir` (Task 3).
- Produces: FastAPI `router` mounted at `/api` exposing `GET /api/videos`, `POST /api/extract`, `GET /api/extract/stream`. Uses `request.app.state.extract_jobs` (a `JobRegistry`, set up in this task's `app.py` change). Used by Task 9 (frontend) and Task 10 (desktop shell, indirectly via `create_app()`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_extract.py
import threading

from fastapi.testclient import TestClient

import src.web.extract_routes as extract_routes_module
from src.web.app import create_app
from src.web.services import get_analytics_service, get_youtube_service


class ScriptedAnalyticsService:
    def __init__(self, responder):
        self._responder = responder
        self._kwargs = None

    def reports(self):
        return self

    def query(self, **kwargs):
        self._kwargs = kwargs
        return self

    def execute(self):
        return self._responder(self._kwargs)


class FakeYouTubeService:
    def __init__(self, videos):
        self._videos = videos


def _always_empty_responder(_kwargs):
    return {"columnHeaders": [], "rows": []}


def _client(tmp_path, monkeypatch, videos):
    monkeypatch.setattr(extract_routes_module, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(extract_routes_module, "list_channel_videos", lambda _service: videos)

    app = create_app()
    app.dependency_overrides[get_youtube_service] = lambda: FakeYouTubeService(videos)
    app.dependency_overrides[get_analytics_service] = lambda: ScriptedAnalyticsService(_always_empty_responder)
    return app, TestClient(app)


def test_get_videos_returns_channel_videos_and_saves_snapshot(tmp_path, monkeypatch):
    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    _app, client = _client(tmp_path, monkeypatch, videos)

    response = client.get("/api/videos")

    assert response.status_code == 200
    assert response.json() == {"videos": videos}
    assert (tmp_path / "output" / "channel_videos.json").exists()


def test_extract_stream_reports_progress_and_completion(tmp_path, monkeypatch):
    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z"},
    ]
    _app, client = _client(tmp_path, monkeypatch, videos)

    start_response = client.post("/api/extract", json={"video_ids": ["vid1", "vid2"]})
    assert start_response.status_code == 200

    with client.stream("GET", "/api/extract/stream") as response:
        body = "".join(response.iter_text())

    assert "Processando 'Video 1'" in body
    assert "Processando 'Video 2'" in body
    assert "Concluído: 2 vídeo(s) processado(s), 0 com erro." in body
    assert (tmp_path / "output" / "por_video" / "vid1.json").exists()
    assert (tmp_path / "output" / "por_video" / "vid2.json").exists()


def test_extract_processes_only_the_valid_ids_from_a_mixed_selection(tmp_path, monkeypatch):
    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    _app, client = _client(tmp_path, monkeypatch, videos)

    start_response = client.post("/api/extract", json={"video_ids": ["vid1", "does-not-exist"]})
    assert start_response.status_code == 200

    with client.stream("GET", "/api/extract/stream") as response:
        body = "".join(response.iter_text())

    assert "Processando 'Video 1'" in body
    assert "Concluído: 1 vídeo(s) processado(s), 0 com erro." in body
    assert (tmp_path / "output" / "por_video" / "vid1.json").exists()


def test_extract_rejects_when_no_valid_video_ids(tmp_path, monkeypatch):
    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    _app, client = _client(tmp_path, monkeypatch, videos)

    response = client.post("/api/extract", json={"video_ids": ["does-not-exist"]})

    assert response.status_code == 400


def test_extract_rejects_when_already_running(tmp_path, monkeypatch):
    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    app, client = _client(tmp_path, monkeypatch, videos)

    release = threading.Event()
    app.state.extract_jobs.start("extract", lambda print_fn: release.wait(timeout=2))

    try:
        response = client.post("/api/extract", json={"video_ids": ["vid1"]})
        assert response.status_code == 409
    finally:
        release.set()
        list(app.state.extract_jobs.stream("extract"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.web.extract_routes'`

- [ ] **Step 3: Write `src/web/extract_routes.py`**

```python
# src/web/extract_routes.py
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.extract_core import extract_selected_videos
from src.storage import save_channel_videos_snapshot, save_consolidated
from src.web.jobs import JobAlreadyRunningError
from src.web.paths import app_data_dir
from src.web.services import get_analytics_service, get_youtube_service
from src.youtube_data import list_channel_videos

router = APIRouter(prefix="/api", tags=["extract"])


class ExtractRequest(BaseModel):
    video_ids: list[str]


def _output_dir() -> Path:
    return app_data_dir() / "output"


@router.get("/videos")
def get_videos(youtube_service=Depends(get_youtube_service)):
    videos = list_channel_videos(youtube_service)
    save_channel_videos_snapshot(_output_dir(), videos)
    return {"videos": videos}


@router.post("/extract")
def start_extract(
    request: Request,
    body: ExtractRequest,
    youtube_service=Depends(get_youtube_service),
    analytics_service=Depends(get_analytics_service),
):
    all_videos = list_channel_videos(youtube_service)
    id_set = set(body.video_ids)
    selected = [video for video in all_videos if video["id"] in id_set]
    if not selected:
        raise HTTPException(status_code=400, detail="nenhum vídeo válido selecionado")

    output_dir = _output_dir()
    today = date.today()

    def job(print_fn):
        documents, failed_ids = extract_selected_videos(
            analytics_service, output_dir, today, selected, print_fn=print_fn
        )
        if documents:
            save_consolidated(output_dir, documents, today.isoformat())
        print_fn(f"Concluído: {len(documents)} vídeo(s) processado(s), {len(failed_ids)} com erro.")

    try:
        request.app.state.extract_jobs.start("extract", job)
    except JobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"started": True}


@router.get("/extract/stream")
def stream_extract(request: Request):
    def event_source():
        for line in request.app.state.extract_jobs.stream("extract"):
            yield f"data: {line}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
```

- [ ] **Step 4: Wire the router and job registry into `src/web/app.py`**

```python
# src/web/app.py
from fastapi import FastAPI

from src.web.extract_routes import router as extract_router
from src.web.jobs import JobRegistry
from src.web.setup import router as setup_router


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Analytics Extractor")
    app.state.extract_jobs = JobRegistry()
    app.include_router(setup_router)
    app.include_router(extract_router)
    return app
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_web_extract.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/web/extract_routes.py src/web/app.py tests/test_web_extract.py
git commit -m "feat: add extract endpoints with live progress streaming"
```

---

### Task 7: Analyze endpoints (list analyzable videos, start analysis, stream progress)

**Files:**
- Create: `src/web/analyze_routes.py`
- Modify: `src/web/app.py`
- Test: `tests/test_web_analyze.py`

**Interfaces:**
- Consumes: `analyze_selected_documents` (Task 2), `compute_channel_averages`/`load_video_documents` (`src/report_data.py`, exists), `JobAlreadyRunningError` (Task 4), `get_anthropic_client` (Task 5), `app_data_dir` (Task 3).
- Produces: FastAPI `router` mounted at `/api` exposing `GET /api/analyzable`, `POST /api/analyze`, `GET /api/analyze/stream`. Uses `request.app.state.analyze_jobs`. Used by Task 9.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_analyze.py
import json
import threading

from fastapi.testclient import TestClient

import src.web.analyze_routes as analyze_routes_module
from src.web.app import create_app
from src.web.services import get_anthropic_client


class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _StreamContext:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self._response


class ScriptedMessages:
    def __init__(self, responder):
        self._responder = responder

    def stream(self, **kwargs):
        return _StreamContext(self._responder(kwargs))


class ScriptedClient:
    def __init__(self, responder):
        self.messages = ScriptedMessages(responder)


def _always_ok_responder(_kwargs):
    return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])


def _write_document(por_video_dir, video_id, title, views=100):
    document = {"video": {"id": video_id, "title": title}, "totals": {"views": views}}
    (por_video_dir / f"{video_id}.json").write_text(json.dumps(document), encoding="utf-8")


def _client(tmp_path, monkeypatch, responder=_always_ok_responder):
    monkeypatch.setattr(analyze_routes_module, "app_data_dir", lambda: tmp_path)

    app = create_app()
    app.dependency_overrides[get_anthropic_client] = lambda: ScriptedClient(responder)
    return app, TestClient(app)


def test_get_analyzable_lists_extracted_videos(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _app, client = _client(tmp_path, monkeypatch)

    response = client.get("/api/analyzable")

    assert response.status_code == 200
    assert response.json() == {"videos": [{"id": "vid1", "title": "Video 1"}]}


def test_analyze_stream_reports_progress_and_completion(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _write_document(por_video, "vid2", "Video 2")
    _app, client = _client(tmp_path, monkeypatch)

    start_response = client.post("/api/analyze", json={"video_ids": ["vid1", "vid2"]})
    assert start_response.status_code == 200

    with client.stream("GET", "/api/analyze/stream") as response:
        body = "".join(response.iter_text())

    assert "Analisando 'Video 1'" in body
    assert "Concluído: 2 relatório(s) gerado(s), 0 com erro." in body
    assert (tmp_path / "reports" / "vid1.md").exists()
    assert (tmp_path / "reports" / "vid2.md").exists()


def test_analyze_rejects_when_no_valid_video_ids(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _app, client = _client(tmp_path, monkeypatch)

    response = client.post("/api/analyze", json={"video_ids": ["does-not-exist"]})

    assert response.status_code == 400


def test_analyze_rejects_when_already_running(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    app, client = _client(tmp_path, monkeypatch)

    release = threading.Event()
    app.state.analyze_jobs.start("analyze", lambda print_fn: release.wait(timeout=2))

    try:
        response = client.post("/api/analyze", json={"video_ids": ["vid1"]})
        assert response.status_code == 409
    finally:
        release.set()
        list(app.state.analyze_jobs.stream("analyze"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_analyze.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.web.analyze_routes'`

- [ ] **Step 3: Write `src/web/analyze_routes.py`**

```python
# src/web/analyze_routes.py
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.analyze_core import analyze_selected_documents
from src.report_data import compute_channel_averages, load_video_documents
from src.web.jobs import JobAlreadyRunningError
from src.web.paths import app_data_dir
from src.web.services import get_anthropic_client

router = APIRouter(prefix="/api", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    video_ids: list[str]


def _output_dir() -> Path:
    return app_data_dir() / "output"


def _reports_dir() -> Path:
    return app_data_dir() / "reports"


@router.get("/analyzable")
def get_analyzable():
    documents = load_video_documents(_output_dir())
    videos = [document.get("video", {}) for document in documents]
    return {"videos": videos}


@router.post("/analyze")
def start_analyze(request: Request, body: AnalyzeRequest, client=Depends(get_anthropic_client)):
    documents = load_video_documents(_output_dir())
    id_set = set(body.video_ids)
    selected = [document for document in documents if document.get("video", {}).get("id") in id_set]
    if not selected:
        raise HTTPException(status_code=400, detail="nenhum vídeo válido selecionado")

    channel_averages = compute_channel_averages(documents)
    reports_dir = _reports_dir()

    def job(print_fn):
        processed_ids, failed_ids = analyze_selected_documents(
            client, selected, channel_averages, reports_dir, print_fn=print_fn
        )
        print_fn(f"Concluído: {len(processed_ids)} relatório(s) gerado(s), {len(failed_ids)} com erro.")

    try:
        request.app.state.analyze_jobs.start("analyze", job)
    except JobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"started": True}


@router.get("/analyze/stream")
def stream_analyze(request: Request):
    def event_source():
        for line in request.app.state.analyze_jobs.stream("analyze"):
            yield f"data: {line}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
```

- [ ] **Step 4: Wire the router and job registry into `src/web/app.py`**

```python
# src/web/app.py
from fastapi import FastAPI

from src.web.analyze_routes import router as analyze_router
from src.web.extract_routes import router as extract_router
from src.web.jobs import JobRegistry
from src.web.setup import router as setup_router


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Analytics Extractor")
    app.state.extract_jobs = JobRegistry()
    app.state.analyze_jobs = JobRegistry()
    app.include_router(setup_router)
    app.include_router(extract_router)
    app.include_router(analyze_router)
    return app
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_web_analyze.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/web/analyze_routes.py src/web/app.py tests/test_web_analyze.py
git commit -m "feat: add analyze endpoints with live progress streaming"
```

---

### Task 8: Browse/results endpoints

**Files:**
- Create: `src/web/results.py`
- Modify: `src/web/app.py`
- Test: `tests/test_web_results.py`

**Interfaces:**
- Consumes: `app_data_dir` (Task 3).
- Produces: FastAPI `router` mounted at `/api` exposing `GET /api/results`, `GET /api/results/{video_id}`. Used by Task 9.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_results.py
import json

from fastapi.testclient import TestClient

import src.web.results as results_module
from src.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(results_module, "app_data_dir", lambda: tmp_path)
    return TestClient(create_app())


def test_list_results_is_empty_when_nothing_extracted_or_analyzed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results")

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_list_results_flags_extraction_and_report_presence(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    (por_video / "vid1.json").write_text(json.dumps({"video": {"id": "vid1"}}), encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "vid1.md").write_text("# relatório", encoding="utf-8")
    (reports_dir / "vid2.md").write_text("# relatório sem extração salva", encoding="utf-8")

    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results")

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"video_id": "vid1", "has_extraction": True, "has_report": True},
            {"video_id": "vid2", "has_extraction": False, "has_report": True},
        ]
    }


def test_get_result_returns_extraction_and_report_when_both_exist(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    document = {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}}
    (por_video / "vid1.json").write_text(json.dumps(document), encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "vid1.md").write_text("# relatório do vid1", encoding="utf-8")

    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results/vid1")

    assert response.status_code == 200
    assert response.json() == {"video_id": "vid1", "extraction": document, "report": "# relatório do vid1"}


def test_get_result_returns_only_extraction_when_report_is_missing(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    document = {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}}
    (por_video / "vid1.json").write_text(json.dumps(document), encoding="utf-8")

    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results/vid1")

    assert response.status_code == 200
    assert response.json() == {"video_id": "vid1", "extraction": document, "report": None}


def test_get_result_returns_404_when_video_id_is_unknown(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results/does-not-exist")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_results.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.web.results'`

- [ ] **Step 3: Write `src/web/results.py`**

```python
# src/web/results.py
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.web.paths import app_data_dir

router = APIRouter(prefix="/api", tags=["results"])


def _output_dir() -> Path:
    return app_data_dir() / "output"


def _reports_dir() -> Path:
    return app_data_dir() / "reports"


@router.get("/results")
def list_results():
    por_video_dir = _output_dir() / "por_video"
    reports_dir = _reports_dir()

    extracted_ids = {path.stem for path in por_video_dir.glob("*.json")} if por_video_dir.is_dir() else set()
    analyzed_ids = {path.stem for path in reports_dir.glob("*.md")} if reports_dir.is_dir() else set()

    all_ids = sorted(extracted_ids | analyzed_ids)
    return {
        "results": [
            {
                "video_id": video_id,
                "has_extraction": video_id in extracted_ids,
                "has_report": video_id in analyzed_ids,
            }
            for video_id in all_ids
        ]
    }


@router.get("/results/{video_id}")
def get_result(video_id: str):
    extraction_path = _output_dir() / "por_video" / f"{video_id}.json"
    report_path = _reports_dir() / f"{video_id}.md"

    if not extraction_path.exists() and not report_path.exists():
        raise HTTPException(status_code=404, detail="vídeo não encontrado")

    extraction = json.loads(extraction_path.read_text(encoding="utf-8")) if extraction_path.exists() else None
    report = report_path.read_text(encoding="utf-8") if report_path.exists() else None

    return {"video_id": video_id, "extraction": extraction, "report": report}
```

- [ ] **Step 4: Wire the router into `src/web/app.py`**

```python
# src/web/app.py
from fastapi import FastAPI

from src.web.analyze_routes import router as analyze_router
from src.web.extract_routes import router as extract_router
from src.web.jobs import JobRegistry
from src.web.results import router as results_router
from src.web.setup import router as setup_router


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Analytics Extractor")
    app.state.extract_jobs = JobRegistry()
    app.state.analyze_jobs = JobRegistry()
    app.include_router(setup_router)
    app.include_router(extract_router)
    app.include_router(analyze_router)
    app.include_router(results_router)
    return app
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_web_results.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/web/results.py src/web/app.py tests/test_web_results.py
git commit -m "feat: add browse/results endpoints"
```

---

### Task 9: Frontend UI (Setup, Extract, Analyze, Browse) and static file serving

**Files:**
- Create: `static/index.html`
- Create: `static/app.css`
- Create: `static/app.js`
- Modify: `src/web/app.py`
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: every `/api/*` endpoint from Tasks 3, 6, 7, 8.
- Produces: the served UI at `/`. Used by Task 10 (`desktop.py` opens a window pointed at this).

- [ ] **Step 1: Write the failing test for static serving**

```python
# tests/test_web_static.py
from fastapi.testclient import TestClient

from src.web.app import create_app


def test_index_page_is_served_at_root():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "YouTube Analytics Extractor" in response.text


def test_static_assets_are_served():
    client = TestClient(create_app())

    response = client.get("/static/app.js")

    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_static.py -v`
Expected: FAIL — `GET /` and `GET /static/app.js` return 404 (no static mount yet).

- [ ] **Step 3: Create `static/index.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <title>YouTube Analytics Extractor</title>
  <link rel="stylesheet" href="/static/app.css" />
</head>
<body>
  <nav>
    <button data-tab="setup">Configuração</button>
    <button data-tab="extract">Extrair</button>
    <button data-tab="analyze">Analisar</button>
    <button data-tab="browse">Navegar</button>
  </nav>

  <section class="tab" data-tab="setup">
    <h1>Configuração inicial</h1>
    <form id="setup-form">
      <label>
        Conteúdo do client_secret.json
        <textarea id="client-secret-input" rows="8" required></textarea>
      </label>
      <label>
        Chave da API Anthropic
        <input id="anthropic-key-input" type="password" required />
      </label>
      <button type="submit">Salvar</button>
    </form>
    <p class="error" id="setup-error"></p>
  </section>

  <section class="tab" data-tab="extract">
    <h1>Extrair dados do YouTube</h1>
    <button id="load-videos-button">Carregar vídeos do canal</button>
    <div id="extract-video-list"></div>
    <button id="start-extract-button">Extrair selecionados</button>
    <p class="error" id="extract-error"></p>
    <pre id="extract-log"></pre>
  </section>

  <section class="tab" data-tab="analyze">
    <h1>Gerar relatórios com IA</h1>
    <button id="load-analyzable-button">Carregar vídeos já extraídos</button>
    <div id="analyze-video-list"></div>
    <p id="analyze-call-count">Isso fará 0 chamada(s) à API da Anthropic.</p>
    <button id="start-analyze-button">Gerar relatórios</button>
    <p class="error" id="analyze-error"></p>
    <pre id="analyze-log"></pre>
  </section>

  <section class="tab" data-tab="browse">
    <h1>Navegar resultados</h1>
    <button id="load-results-button">Atualizar lista</button>
    <div id="results-list"></div>
    <h2>Dados extraídos</h2>
    <pre id="result-json"></pre>
    <h2>Relatório</h2>
    <pre id="result-report"></pre>
  </section>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create `static/app.css`**

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem;
}

nav {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

nav button.active {
  font-weight: bold;
  text-decoration: underline;
}

.tab {
  display: none;
}

.video-item {
  display: block;
  padding: 0.25rem 0;
}

.error {
  color: #b00020;
}

pre {
  background: #f5f5f5;
  padding: 0.75rem;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.result-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.5rem;
  margin-bottom: 0.25rem;
}
```

- [ ] **Step 5: Create `static/app.js`**

```javascript
const state = {
  extractVideos: [],
  analyzableVideos: [],
};

function $(id) {
  return document.getElementById(id);
}

function showTab(name) {
  document.querySelectorAll(".tab").forEach((el) => {
    el.style.display = el.dataset.tab === name ? "block" : "none";
  });
  document.querySelectorAll("nav button").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === name);
  });
}

async function refreshSetupStatus() {
  const response = await fetch("/api/setup/status");
  const status = await response.json();
  if (!status.client_secret_configured || !status.anthropic_key_configured) {
    showTab("setup");
  } else {
    showTab("extract");
  }
  return status;
}

async function submitSetup(event) {
  event.preventDefault();
  const payload = {
    client_secret_json: $("client-secret-input").value,
    anthropic_api_key: $("anthropic-key-input").value,
  };
  const response = await fetch("/api/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json();
    $("setup-error").textContent = error.detail || "erro ao salvar configuração";
    return;
  }
  $("setup-error").textContent = "";
  await refreshSetupStatus();
}

async function loadVideos() {
  $("extract-error").textContent = "";
  const response = await fetch("/api/videos");
  if (!response.ok) {
    const error = await response.json();
    $("extract-error").textContent = error.detail || "erro ao carregar vídeos";
    return;
  }
  const data = await response.json();
  state.extractVideos = data.videos;
  renderVideoCheckboxes("extract-video-list", data.videos, "extract-video");
}

function renderVideoCheckboxes(containerId, videos, inputName) {
  const container = $(containerId);
  container.innerHTML = "";
  videos.forEach((video) => {
    const label = document.createElement("label");
    label.className = "video-item";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = video.id;
    checkbox.name = inputName;
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(` ${video.title} (${video.id})`));
    container.appendChild(label);
  });
}

function selectedIds(inputName) {
  return Array.from(document.querySelectorAll(`input[name="${inputName}"]:checked`)).map((el) => el.value);
}

function streamJob(streamUrl, logElementId, onDone) {
  const log = $(logElementId);
  log.textContent = "";
  const source = new EventSource(streamUrl);
  source.onmessage = (event) => {
    log.textContent += event.data + "\n";
  };
  source.addEventListener("done", () => {
    source.close();
    if (onDone) onDone();
  });
  source.onerror = () => {
    source.close();
  };
}

async function startExtract() {
  $("extract-error").textContent = "";
  const videoIds = selectedIds("extract-video");
  const response = await fetch("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_ids: videoIds }),
  });
  if (!response.ok) {
    const error = await response.json();
    $("extract-error").textContent = error.detail || "erro ao iniciar extração";
    return;
  }
  streamJob("/api/extract/stream", "extract-log");
}

async function loadAnalyzable() {
  $("analyze-error").textContent = "";
  const response = await fetch("/api/analyzable");
  const data = await response.json();
  state.analyzableVideos = data.videos;
  renderVideoCheckboxes("analyze-video-list", data.videos, "analyze-video");
  updateAnalyzeCallCount();
}

function updateAnalyzeCallCount() {
  const count = selectedIds("analyze-video").length;
  $("analyze-call-count").textContent = `Isso fará ${count} chamada(s) à API da Anthropic.`;
}

async function startAnalyze() {
  $("analyze-error").textContent = "";
  const videoIds = selectedIds("analyze-video");
  if (videoIds.length === 0) {
    $("analyze-error").textContent = "selecione ao menos um vídeo";
    return;
  }
  if (!confirm(`Confirma gerar ${videoIds.length} relatório(s) via API da Anthropic?`)) {
    return;
  }
  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_ids: videoIds }),
  });
  if (!response.ok) {
    const error = await response.json();
    $("analyze-error").textContent = error.detail || "erro ao iniciar análise";
    return;
  }
  streamJob("/api/analyze/stream", "analyze-log");
}

async function loadResults() {
  const response = await fetch("/api/results");
  const data = await response.json();
  const container = $("results-list");
  container.innerHTML = "";
  data.results.forEach((result) => {
    const item = document.createElement("button");
    item.className = "result-item";
    item.textContent = `${result.video_id} ${result.has_extraction ? "[dados]" : ""} ${result.has_report ? "[relatório]" : ""}`;
    item.onclick = () => showResult(result.video_id);
    container.appendChild(item);
  });
}

async function showResult(videoId) {
  const response = await fetch(`/api/results/${videoId}`);
  const data = await response.json();
  $("result-json").textContent = data.extraction ? JSON.stringify(data.extraction, null, 2) : "(sem dados extraídos)";
  $("result-report").textContent = data.report || "(sem relatório gerado)";
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("nav button").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  });
  $("setup-form").addEventListener("submit", submitSetup);
  $("load-videos-button").addEventListener("click", loadVideos);
  $("start-extract-button").addEventListener("click", startExtract);
  $("load-analyzable-button").addEventListener("click", loadAnalyzable);
  $("start-analyze-button").addEventListener("click", startAnalyze);
  $("load-results-button").addEventListener("click", loadResults);
  document.addEventListener("change", (event) => {
    if (event.target.name === "analyze-video") updateAnalyzeCallCount();
  });

  refreshSetupStatus();
});
```

- [ ] **Step 6: Mount static files and serve `index.html` at `/` in `src/web/app.py`**

```python
# src/web/app.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.web.analyze_routes import router as analyze_router
from src.web.extract_routes import router as extract_router
from src.web.jobs import JobRegistry
from src.web.results import router as results_router
from src.web.setup import router as setup_router

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Analytics Extractor")
    app.state.extract_jobs = JobRegistry()
    app.state.analyze_jobs = JobRegistry()
    app.include_router(setup_router)
    app.include_router(extract_router)
    app.include_router(analyze_router)
    app.include_router(results_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_web_static.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 9: Manual browser verification**

Run: `source .venv/bin/activate && uvicorn src.web.app:app --reload --port 8000` from the project root, then open `http://127.0.0.1:8000` in a browser.

Walk through, using your real `client_secret.json` contents and Anthropic key:
1. Setup tab appears first (since nothing is configured yet in the app data directory) — paste the credentials, submit, confirm it switches to the Extract tab.
2. Extract tab: click "Carregar vídeos do canal" (this triggers the Google OAuth browser popup on first use, same as `python main.py` today), check a couple of videos, click "Extrair selecionados", confirm the log streams progress live and ends with a "Concluído" line.
3. Analyze tab: click "Carregar vídeos já extraídos", check a video, confirm the call-count text updates, click "Gerar relatórios", confirm the browser's confirmation dialog appears, accept it, confirm the log streams and ends with "Concluído".
4. Browse tab: click "Atualizar lista", click a video entry, confirm both the extracted JSON and the generated report render.

Fix any issue found before moving on. Stop the server (`Ctrl+C`) when done.

- [ ] **Step 10: Commit**

```bash
git add static/index.html static/app.css static/app.js src/web/app.py tests/test_web_static.py
git commit -m "feat: add web frontend for setup, extract, analyze, and browse"
```

---

### Task 10: Desktop shell entry point (`desktop.py`)

**Files:**
- Modify: `requirements.txt`
- Create: `desktop.py`
- Test: `tests/test_desktop.py`

**Interfaces:**
- Consumes: `create_app` (Task 9's `src/web/app.py`).
- Produces: `main()` — the packaged app's entry point, invoked directly when run as a script and by the PyInstaller build in Task 11.

- [ ] **Step 1: Add `pywebview` to `requirements.txt`**

```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
pytest>=7.4.0
anthropic>=1.9.0
python-dotenv>=1.0.0
fastapi>=0.115.0
uvicorn>=0.30.0
platformdirs>=4.0.0
httpx>=0.27.0
pywebview>=5.0
```

- [ ] **Step 2: Install the new dependency**

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: install completes with no errors.

- [ ] **Step 3: Write the failing test**

```python
# tests/test_desktop.py
from desktop import _free_port


def test_free_port_returns_a_usable_port_number():
    port = _free_port()

    assert isinstance(port, int)
    assert 1024 <= port <= 65535
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_desktop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'desktop'`

- [ ] **Step 5: Write `desktop.py`**

```python
# desktop.py
import socket
import threading

import uvicorn
import webview

from src.web.app import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    app = create_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    window = webview.create_window("YouTube Analytics Extractor", f"http://127.0.0.1:{port}")

    def on_closed():
        server.should_exit = True

    window.events.closed += on_closed

    webview.start()
    server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_desktop.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 8: Manual verification**

Run: `source .venv/bin/activate && python desktop.py` from the project root.

Confirm:
1. A native app window opens (not a browser tab) showing the Setup screen (or Extract screen, if you already completed setup during Task 9's manual test — the app data directory persists between runs).
2. The full Setup → Extract → Analyze → Browse flow from Task 9's manual test works identically inside this native window.
3. Closing the window ends the process — check with `ps aux | grep desktop.py` (macOS/Linux) or Task Manager (Windows) that no orphaned Python process remains a few seconds after closing.

Fix any issue found before moving on.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt desktop.py tests/test_desktop.py
git commit -m "feat: add desktop shell entry point with pywebview"
```

---

### Task 11: PyInstaller packaging and CI build matrix

**Files:**
- Modify: `requirements.txt`
- Create: `build/desktop.spec`
- Create: `.github/workflows/build-desktop.yml`

**Interfaces:**
- Consumes: `desktop.py` (Task 10), `static/` (Task 9).
- Produces: a `dist/` executable per OS when PyInstaller is run against `build/desktop.spec`; a manually-triggerable GitHub Actions workflow that builds both the macOS and Windows binaries and uploads them as artifacts.

- [ ] **Step 1: Add `pyinstaller` to `requirements.txt`**

```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
pytest>=7.4.0
anthropic>=1.9.0
python-dotenv>=1.0.0
fastapi>=0.115.0
uvicorn>=0.30.0
platformdirs>=4.0.0
httpx>=0.27.0
pywebview>=5.0
pyinstaller>=6.10.0
```

- [ ] **Step 2: Install the new dependency**

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: install completes with no errors.

- [ ] **Step 3: Write `build/desktop.spec`**

```python
# build/desktop.spec
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH).parent

a = Analysis(
    [str(project_root / "desktop.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(project_root / "static"), "static")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="yt-data-extractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
```

- [ ] **Step 4: Build locally on macOS and verify**

Run: `source .venv/bin/activate && pyinstaller build/desktop.spec --distpath dist`
Expected: build completes; `dist/yt-data-extractor` (or `dist/yt-data-extractor.app` on macOS) exists.

Run the produced binary directly (e.g. `open dist/yt-data-extractor.app` or `./dist/yt-data-extractor`) and repeat Task 10 Step 8's manual verification against this packaged binary instead of `python desktop.py`. This confirms the static assets and all dependencies were bundled correctly.

Fix any issue found (commonly: a missing `datas` entry, or a hidden import PyInstaller didn't detect) before moving on.

- [ ] **Step 5: Write `.github/workflows/build-desktop.yml`**

```yaml
name: Build desktop binaries

on:
  workflow_dispatch: {}

jobs:
  build:
    strategy:
      matrix:
        os: [macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pyinstaller build/desktop.spec --distpath dist
      - uses: actions/upload-artifact@v4
        with:
          name: yt-data-extractor-${{ matrix.os }}
          path: dist/
```

- [ ] **Step 6: Trigger the workflow and verify the Windows build**

Push this branch (or merge to the default branch, per the project's normal workflow), then run: `gh workflow run build-desktop.yml` (or trigger it from the GitHub Actions UI).

Once it completes, download the `yt-data-extractor-windows-latest` artifact on (or transfer it to) a Windows machine, run the executable, and repeat Task 10 Step 8's manual verification there. This is the only step that validates the Windows build — PyInstaller cannot cross-compile, so this cannot be checked from macOS.

Fix any issue found before moving on.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt build/desktop.spec .github/workflows/build-desktop.yml
git commit -m "build: add PyInstaller packaging and CI build matrix for macOS/Windows"
```

---

### Task 12: README updates

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: user-facing guide for running the app in dev mode and building the packaged binaries. Nothing depends on this.

- [ ] **Step 1: Append a new section to `README.md`**

Add this section after the existing "## 6. Gerar relatórios de performance com IA" section (keep everything before it as-is):

```markdown

## 7. App local com interface (binário)

Além dos scripts de linha de comando, o projeto tem uma versão com interface
web local, empacotável como um binário para rodar sem precisar instalar
Python.

### Rodar em modo desenvolvimento

```bash
source .venv/bin/activate
python desktop.py
```

Isso abre uma janela nativa do app. Na primeira execução, a aba de
Configuração pede o conteúdo do `client_secret.json` e a chave da API
Anthropic — diferente dos scripts `main.py`/`analyze.py`, essas credenciais
ficam salvas numa pasta de dados do usuário (fora da pasta do projeto), então
só precisam ser configuradas uma vez.

A partir daí, use as abas Extrair, Analisar e Navegar para rodar os mesmos
fluxos de `main.py`/`analyze.py` pela interface, com o progresso exibido ao
vivo.

### Gerar o binário

```bash
source .venv/bin/activate
pyinstaller build/desktop.spec --distpath dist
```

O executável fica em `dist/`. Como o PyInstaller não compila para outro
sistema operacional, o binário do Windows precisa ser gerado numa máquina
Windows — o workflow `.github/workflows/build-desktop.yml` faz isso
automaticamente numa matriz macOS + Windows via GitHub Actions
(`gh workflow run build-desktop.yml`).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document the local web app and how to build the binary"
```
