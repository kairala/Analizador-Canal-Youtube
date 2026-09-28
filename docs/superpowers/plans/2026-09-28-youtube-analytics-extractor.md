# YouTube Analytics Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI script that lists a YouTube channel's videos, lets the user pick one/several/all, extracts a comprehensive set of YouTube Analytics reports per video, and saves everything to JSON files (per-video and consolidated) for offline analysis.

**Architecture:** A small set of focused modules under `src/` (auth, video listing, report definitions, analytics querying, storage) wired together by `main.py`. Every module that talks to a real Google API takes the API client as a parameter, so tests can substitute hand-written fakes instead of hitting the network. Pure logic (date ranges, menu parsing, retry, JSON shaping) is tested directly.

**Tech Stack:** Python 3.10+, `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-28-youtube-analytics-extractor-design.md`

## Global Constraints

- Output is JSON only — never write CSV/Excel (user chose JSON).
- `client_secret.json` and `token.json` must never be committed — both are in `.gitignore` from Task 1 onward.
- All Analytics queries are scoped to `channel==MINE` (the authenticated user's own channel only) — no multi-channel support.
- Batch ("todos") processing must continue past a single video's or a single report's failure — never abort the whole run because one item failed.
- Every function that calls a real Google API client takes that client as a parameter (never constructs it internally) so it can be tested with a fake.

## Review Focus

- A very recently published video has no analytics data yet (~48h lag) — the API returns empty rows; the script must save an empty result for that report instead of crashing. (Task 6, Task 10)
- The user types garbage at the video-selection prompt (letters, an out-of-range number, an empty line) — the script must reject it with a clear message and ask again, not crash. (Task 3, Task 10)
- One video (or one report for a video) fails during a "todos" batch — the other videos must still be processed and saved, and the run must finish with a summary. (Task 10)
- The saved OAuth token is present but its refresh token has been revoked — the script must fall back to a fresh login flow instead of crashing with an auth error. (Task 9)
- The channel has zero videos — the script must print a clear message and exit cleanly instead of crashing on an empty menu. (Task 10)

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `src/__init__.py`
- Create: `tests/` (directory, via first test file in Task 2)

**Interfaces:**
- Consumes: nothing.
- Produces: an installable, testable project skeleton every later task builds on.

- [ ] **Step 1: Create `requirements.txt`**

```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
pytest>=7.4.0
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
client_secret.json
token.json
output/
.pytest_cache/
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

- [ ] **Step 4: Create `src/__init__.py`**

```python
```

(empty file — makes `src` an importable package)

- [ ] **Step 5: Install dependencies**

Run: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
Expected: install completes with no errors.

- [ ] **Step 6: Verify pytest runs with no tests yet**

Run: `pytest`
Expected: `no tests ran` (exit code 0), no import errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore pyproject.toml src/__init__.py
git commit -m "chore: project scaffolding"
```

---

### Task 2: Date range helper

**Files:**
- Create: `src/date_ranges.py`
- Test: `tests/test_date_ranges.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `analytics_date_range(published_at: str, today: date) -> tuple[str, str]`, used by Task 10 (`extract_video`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_date_ranges.py
from datetime import date

from src.date_ranges import analytics_date_range


def test_analytics_date_range_from_iso_published_at():
    start, end = analytics_date_range("2024-05-01T12:00:00Z", date(2024, 6, 15))
    assert (start, end) == ("2024-05-01", "2024-06-15")


def test_analytics_date_range_same_day():
    start, end = analytics_date_range("2024-06-15T08:00:00Z", date(2024, 6, 15))
    assert (start, end) == ("2024-06-15", "2024-06-15")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_date_ranges.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.date_ranges'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/date_ranges.py
from datetime import date, datetime


def analytics_date_range(published_at: str, today: date) -> tuple[str, str]:
    published_date = datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
    start = published_date.isoformat()
    end = today.isoformat()
    return start, end
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_date_ranges.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/date_ranges.py tests/test_date_ranges.py
git commit -m "feat: add analytics date range helper"
```

---

### Task 3: Video selection parser

**Files:**
- Create: `src/selection.py`
- Test: `tests/test_selection.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_selection(raw: str, total: int) -> list[int]` (1-based indices, sorted, deduplicated; raises `ValueError` with a human-readable message on invalid input), used by Task 10 (`select_videos`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_selection.py
import pytest

from src.selection import parse_selection


def test_parse_single_number():
    assert parse_selection("2", total=5) == [2]


def test_parse_comma_separated_list():
    assert parse_selection(" 1, 3,5 ", total=5) == [1, 3, 5]


def test_parse_deduplicates_and_sorts():
    assert parse_selection("3,1,3", total=5) == [1, 3]


def test_parse_all_keyword_portuguese():
    assert parse_selection("todos", total=3) == [1, 2, 3]


def test_parse_all_keyword_english():
    assert parse_selection("ALL", total=3) == [1, 2, 3]


def test_parse_rejects_empty_input():
    with pytest.raises(ValueError):
        parse_selection("   ", total=3)


def test_parse_rejects_non_numeric_token():
    with pytest.raises(ValueError):
        parse_selection("abc", total=3)


def test_parse_rejects_out_of_range_number():
    with pytest.raises(ValueError):
        parse_selection("99", total=3)


def test_parse_rejects_when_no_videos_available():
    with pytest.raises(ValueError):
        parse_selection("1", total=0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.selection'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/selection.py
def parse_selection(raw: str, total: int) -> list[int]:
    if total <= 0:
        raise ValueError("nenhum vídeo disponível para seleção")

    normalized = raw.strip().lower()
    if not normalized:
        raise ValueError("entrada vazia")

    if normalized in ("todos", "all"):
        return list(range(1, total + 1))

    indices = []
    for part in normalized.split(","):
        part = part.strip()
        if not part.isdigit():
            raise ValueError(f"'{part}' não é um número válido")
        index = int(part)
        if index < 1 or index > total:
            raise ValueError(f"{index} está fora do intervalo (1-{total})")
        indices.append(index)

    return sorted(set(indices))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_selection.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/selection.py tests/test_selection.py
git commit -m "feat: add video selection parser"
```

---

### Task 4: Retry helper

**Files:**
- Create: `src/retry.py`
- Test: `tests/test_retry.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `with_retry(fn, *, retry_on=(Exception,), max_attempts=3, base_delay=1.0, sleep=time.sleep)`, used by Task 6 (`run_report`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_retry.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.retry'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/retry.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retry.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/retry.py tests/test_retry.py
git commit -m "feat: add retry-with-backoff helper"
```

---

### Task 5: Report definitions

**Files:**
- Create: `src/reports.py`
- Test: `tests/test_reports.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ReportDef` (dataclass with fields `name: str`, `dimensions: list[str]`, `metrics: list[str]`) and `REPORTS: list[ReportDef]`, used by Task 6, Task 8, and Task 10.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reports.py
from src.reports import REPORTS


def test_reports_have_expected_names_in_order():
    names = [r.name for r in REPORTS]
    assert names == [
        "totals",
        "daily",
        "traffic_sources",
        "devices",
        "geography",
        "demographics",
        "retention",
    ]


def test_every_report_has_metrics():
    for report_def in REPORTS:
        assert len(report_def.metrics) > 0


def test_totals_is_aggregate_and_daily_is_timeseries_with_same_metrics():
    by_name = {r.name: r for r in REPORTS}
    assert by_name["totals"].dimensions == []
    assert by_name["daily"].dimensions == ["day"]
    assert by_name["daily"].metrics == by_name["totals"].metrics


def test_breakdown_reports_have_expected_dimensions():
    by_name = {r.name: r for r in REPORTS}
    assert by_name["traffic_sources"].dimensions == ["insightTrafficSourceType"]
    assert by_name["devices"].dimensions == ["deviceType"]
    assert by_name["geography"].dimensions == ["country"]
    assert by_name["demographics"].dimensions == ["ageGroup", "gender"]
    assert by_name["retention"].dimensions == ["elapsedVideoTimeRatio"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reports.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.reports'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/reports.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ReportDef:
    name: str
    dimensions: list[str]
    metrics: list[str]


CORE_METRICS = [
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
    "subscribersLost",
    "impressions",
    "impressionsClickThroughRate",
]

REPORTS: list[ReportDef] = [
    ReportDef(name="totals", dimensions=[], metrics=CORE_METRICS),
    ReportDef(name="daily", dimensions=["day"], metrics=CORE_METRICS),
    ReportDef(
        name="traffic_sources",
        dimensions=["insightTrafficSourceType"],
        metrics=["views", "estimatedMinutesWatched"],
    ),
    ReportDef(
        name="devices",
        dimensions=["deviceType"],
        metrics=["views", "estimatedMinutesWatched"],
    ),
    ReportDef(
        name="geography",
        dimensions=["country"],
        metrics=["views", "estimatedMinutesWatched"],
    ),
    ReportDef(
        name="demographics",
        dimensions=["ageGroup", "gender"],
        metrics=["viewerPercentage"],
    ),
    ReportDef(
        name="retention",
        dimensions=["elapsedVideoTimeRatio"],
        metrics=["audienceWatchRatio", "relativeRetentionPerformance"],
    ),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reports.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/reports.py tests/test_reports.py
git commit -m "feat: define analytics report set"
```

---

### Task 6: YouTube Analytics querying

**Files:**
- Create: `src/youtube_analytics.py`
- Test: `tests/test_youtube_analytics.py`

**Interfaces:**
- Consumes: `ReportDef` from `src/reports.py` (Task 5), `with_retry` from `src/retry.py` (Task 4).
- Produces: `parse_analytics_response(response: dict) -> list[dict]`, `shape_report_result(report_def: ReportDef, rows: list[dict]) -> dict | list[dict]`, `run_report(analytics_service, video_id: str, start_date: str, end_date: str, report_def: ReportDef, sleep=time.sleep) -> list[dict]`. Used by Task 10 (`extract_video`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_youtube_analytics.py
from src.reports import ReportDef
from src.youtube_analytics import parse_analytics_response, run_report, shape_report_result


class FakeAnalyticsService:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def reports(self):
        return self

    def query(self, **kwargs):
        self.last_kwargs = kwargs
        return self

    def execute(self):
        return self._response


def test_parse_analytics_response_zips_headers_with_rows():
    response = {
        "columnHeaders": [{"name": "day"}, {"name": "views"}],
        "rows": [["2024-01-01", 10], ["2024-01-02", 5]],
    }
    assert parse_analytics_response(response) == [
        {"day": "2024-01-01", "views": 10},
        {"day": "2024-01-02", "views": 5},
    ]


def test_parse_analytics_response_handles_no_rows():
    response = {"columnHeaders": [{"name": "views"}], "rows": []}
    assert parse_analytics_response(response) == []


def test_shape_report_result_returns_single_dict_for_aggregate_report():
    report_def = ReportDef(name="totals", dimensions=[], metrics=["views"])
    assert shape_report_result(report_def, [{"views": 42}]) == {"views": 42}


def test_shape_report_result_returns_empty_dict_when_no_rows_for_aggregate_report():
    report_def = ReportDef(name="totals", dimensions=[], metrics=["views"])
    assert shape_report_result(report_def, []) == {}


def test_shape_report_result_returns_list_for_timeseries_report():
    report_def = ReportDef(name="daily", dimensions=["day"], metrics=["views"])
    rows = [{"day": "2024-01-01", "views": 10}]
    assert shape_report_result(report_def, rows) == rows


def test_run_report_builds_expected_query_and_parses_response():
    response = {
        "columnHeaders": [{"name": "day"}, {"name": "views"}],
        "rows": [["2024-01-01", 10]],
    }
    service = FakeAnalyticsService(response)
    report_def = ReportDef(name="daily", dimensions=["day"], metrics=["views"])

    result = run_report(service, "vid1", "2024-01-01", "2024-02-01", report_def)

    assert result == [{"day": "2024-01-01", "views": 10}]
    assert service.last_kwargs == {
        "ids": "channel==MINE",
        "startDate": "2024-01-01",
        "endDate": "2024-02-01",
        "metrics": "views",
        "filters": "video==vid1",
        "dimensions": "day",
    }


def test_run_report_omits_dimensions_key_for_aggregate_report():
    response = {"columnHeaders": [{"name": "views"}], "rows": [[42]]}
    service = FakeAnalyticsService(response)
    report_def = ReportDef(name="totals", dimensions=[], metrics=["views"])

    run_report(service, "vid1", "2024-01-01", "2024-02-01", report_def)

    assert "dimensions" not in service.last_kwargs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_youtube_analytics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.youtube_analytics'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/youtube_analytics.py
import time

from googleapiclient.errors import HttpError

from src.reports import ReportDef
from src.retry import with_retry


def parse_analytics_response(response: dict) -> list[dict]:
    headers = [h["name"] for h in response.get("columnHeaders", [])]
    rows = response.get("rows", []) or []
    return [dict(zip(headers, row)) for row in rows]


def shape_report_result(report_def: ReportDef, rows: list[dict]):
    if not report_def.dimensions:
        return rows[0] if rows else {}
    return rows


def run_report(
    analytics_service,
    video_id: str,
    start_date: str,
    end_date: str,
    report_def: ReportDef,
    sleep=time.sleep,
) -> list[dict]:
    params = {
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": ",".join(report_def.metrics),
        "filters": f"video=={video_id}",
    }
    if report_def.dimensions:
        params["dimensions"] = ",".join(report_def.dimensions)

    def _execute():
        return analytics_service.reports().query(**params).execute()

    response = with_retry(_execute, retry_on=(HttpError,), sleep=sleep)
    return parse_analytics_response(response)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_youtube_analytics.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/youtube_analytics.py tests/test_youtube_analytics.py
git commit -m "feat: add YouTube Analytics query and parsing"
```

---

### Task 7: Channel video listing

**Files:**
- Create: `src/youtube_data.py`
- Test: `tests/test_youtube_data.py`

**Interfaces:**
- Consumes: nothing beyond the injected `youtube_service`.
- Produces: `list_channel_videos(youtube_service, sleep=time.sleep) -> list[dict]`, where each dict has keys `id`, `title`, `published_at`, `duration`. Used by Task 10 (`run`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_youtube_data.py
from src.youtube_data import list_channel_videos


class FakeYouTubeService:
    def __init__(self, channel_response, playlist_pages, videos_response):
        self._channel_response = channel_response
        self._playlist_pages = playlist_pages
        self._videos_response = videos_response
        self._playlist_call_count = 0
        self._last_kwargs = {}

    def channels(self):
        return self

    def playlistItems(self):
        return self

    def videos(self):
        return self

    def list(self, **kwargs):
        self._last_kwargs = kwargs
        return self

    def execute(self):
        if "playlistId" in self._last_kwargs:
            page = self._playlist_pages[self._playlist_call_count]
            self._playlist_call_count += 1
            return page
        if "id" in self._last_kwargs:
            return self._videos_response
        return self._channel_response


def test_list_channel_videos_paginates_and_merges_durations():
    channel_response = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUxxxx"}}}]
    }
    playlist_pages = [
        {
            "items": [
                {
                    "contentDetails": {"videoId": "vid1"},
                    "snippet": {"title": "Video 1", "publishedAt": "2024-01-01T00:00:00Z"},
                }
            ],
            "nextPageToken": "TOKEN2",
        },
        {
            "items": [
                {
                    "contentDetails": {"videoId": "vid2"},
                    "snippet": {"title": "Video 2", "publishedAt": "2024-02-01T00:00:00Z"},
                }
            ]
        },
    ]
    videos_response = {
        "items": [
            {"id": "vid1", "contentDetails": {"duration": "PT5M"}},
            {"id": "vid2", "contentDetails": {"duration": "PT3M"}},
        ]
    }
    service = FakeYouTubeService(channel_response, playlist_pages, videos_response)

    videos = list_channel_videos(service)

    assert videos == [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT5M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-02-01T00:00:00Z", "duration": "PT3M"},
    ]


def test_list_channel_videos_returns_empty_list_for_channel_with_no_uploads():
    channel_response = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUxxxx"}}}]
    }
    playlist_pages = [{"items": []}]
    videos_response = {"items": []}
    service = FakeYouTubeService(channel_response, playlist_pages, videos_response)

    assert list_channel_videos(service) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_youtube_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.youtube_data'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/youtube_data.py
import time

from googleapiclient.errors import HttpError

from src.retry import with_retry


def list_channel_videos(youtube_service, sleep=time.sleep) -> list[dict]:
    channel_response = with_retry(
        lambda: youtube_service.channels().list(part="contentDetails", mine=True).execute(),
        retry_on=(HttpError,),
        sleep=sleep,
    )
    uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    items = []
    page_token = None
    while True:
        response = with_retry(
            lambda: youtube_service.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            .execute(),
            retry_on=(HttpError,),
            sleep=sleep,
        )
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    videos = [
        {
            "id": item["contentDetails"]["videoId"],
            "title": item["snippet"]["title"],
            "published_at": item["contentDetails"].get("videoPublishedAt")
            or item["snippet"]["publishedAt"],
        }
        for item in items
    ]

    durations = _fetch_durations(youtube_service, [v["id"] for v in videos], sleep)
    for video in videos:
        video["duration"] = durations.get(video["id"], "")

    return videos


def _fetch_durations(youtube_service, video_ids: list[str], sleep) -> dict[str, str]:
    durations = {}
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start : start + 50]
        if not batch:
            continue
        response = with_retry(
            lambda: youtube_service.videos().list(part="contentDetails", id=",".join(batch)).execute(),
            retry_on=(HttpError,),
            sleep=sleep,
        )
        for item in response.get("items", []):
            durations[item["id"]] = item["contentDetails"]["duration"]
    return durations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_youtube_data.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/youtube_data.py tests/test_youtube_data.py
git commit -m "feat: add channel video listing with pagination"
```

---

### Task 8: JSON storage

**Files:**
- Create: `src/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: nothing beyond plain dicts/lists.
- Produces: `assemble_video_document(video_meta: dict, shaped_reports: dict) -> dict`, `save_video_report(output_dir: Path, video_id: str, document: dict) -> Path`, `save_consolidated(output_dir: Path, documents: list[dict], generated_at: str) -> Path`, `save_channel_videos_snapshot(output_dir: Path, videos: list[dict]) -> Path`. Used by Task 10 (`run`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py
import json

from src.storage import (
    assemble_video_document,
    save_channel_videos_snapshot,
    save_consolidated,
    save_video_report,
)


def test_assemble_video_document_merges_meta_and_reports():
    video_meta = {"id": "vid1", "title": "Video 1"}
    shaped_reports = {"totals": {"views": 10}, "daily": [{"day": "2024-01-01", "views": 10}]}

    document = assemble_video_document(video_meta, shaped_reports)

    assert document == {
        "video": {"id": "vid1", "title": "Video 1"},
        "totals": {"views": 10},
        "daily": [{"day": "2024-01-01", "views": 10}],
    }


def test_save_video_report_writes_expected_file(tmp_path):
    document = {"video": {"id": "vid1"}, "totals": {"views": 10}}

    path = save_video_report(tmp_path, "vid1", document)

    assert path == tmp_path / "por_video" / "vid1.json"
    assert json.loads(path.read_text(encoding="utf-8")) == document


def test_save_consolidated_writes_expected_file(tmp_path):
    documents = [{"video": {"id": "vid1"}}, {"video": {"id": "vid2"}}]

    path = save_consolidated(tmp_path, documents, "2026-09-28")

    assert path == tmp_path / "consolidado.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "generated_at": "2026-09-28",
        "videos": documents,
    }


def test_save_channel_videos_snapshot_writes_expected_file(tmp_path):
    videos = [{"id": "vid1", "title": "Video 1"}]

    path = save_channel_videos_snapshot(tmp_path, videos)

    assert path == tmp_path / "channel_videos.json"
    assert json.loads(path.read_text(encoding="utf-8")) == videos
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.storage'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/storage.py
import json
from pathlib import Path


def assemble_video_document(video_meta: dict, shaped_reports: dict) -> dict:
    return {"video": video_meta, **shaped_reports}


def save_video_report(output_dir: Path, video_id: str, document: dict) -> Path:
    folder = output_dir / "por_video"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{video_id}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_consolidated(output_dir: Path, documents: list[dict], generated_at: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "consolidado.json"
    payload = {"generated_at": generated_at, "videos": documents}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_channel_videos_snapshot(output_dir: Path, videos: list[dict]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "channel_videos.json"
    path.write_text(json.dumps(videos, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/storage.py tests/test_storage.py
git commit -m "feat: add JSON storage for video reports"
```

---

### Task 9: OAuth2 authentication

**Files:**
- Create: `src/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: nothing beyond `client_secret_path` / `token_path` provided by the caller.
- Produces: `SCOPES: list[str]`, `get_credentials(client_secret_path: Path, token_path: Path, scopes: list[str] = SCOPES) -> Credentials`. Used by Task 10 (`main`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auth.py
from unittest.mock import MagicMock, patch

from src import auth


def test_get_credentials_returns_cached_valid_credentials(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    client_secret_path = tmp_path / "client_secret.json"

    cached_creds = MagicMock(valid=True)

    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=cached_creds) as loader, \
         patch.object(auth.InstalledAppFlow, "from_client_secrets_file") as flow_factory:
        result = auth.get_credentials(client_secret_path, token_path, ["scope1"])

    loader.assert_called_once_with(str(token_path), ["scope1"])
    flow_factory.assert_not_called()
    assert result is cached_creds


def test_get_credentials_refreshes_expired_token(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    client_secret_path = tmp_path / "client_secret.json"

    expired_creds = MagicMock(valid=False, expired=True, refresh_token="refresh-me")
    expired_creds.to_json.return_value = '{"refreshed": true}'

    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=expired_creds), \
         patch.object(auth.InstalledAppFlow, "from_client_secrets_file") as flow_factory:
        result = auth.get_credentials(client_secret_path, token_path, ["scope1"])

    expired_creds.refresh.assert_called_once()
    flow_factory.assert_not_called()
    assert result is expired_creds
    assert token_path.read_text(encoding="utf-8") == '{"refreshed": true}'


def test_get_credentials_falls_back_to_flow_when_refresh_fails(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    client_secret_path = tmp_path / "client_secret.json"

    expired_creds = MagicMock(valid=False, expired=True, refresh_token="revoked")
    expired_creds.refresh.side_effect = Exception("invalid_grant")

    new_creds = MagicMock()
    new_creds.to_json.return_value = '{"fresh": true}'
    flow = MagicMock()
    flow.run_local_server.return_value = new_creds

    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=expired_creds), \
         patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=flow) as flow_factory:
        result = auth.get_credentials(client_secret_path, token_path, ["scope1"])

    flow_factory.assert_called_once_with(str(client_secret_path), ["scope1"])
    flow.run_local_server.assert_called_once_with(port=0)
    assert result is new_creds
    assert token_path.read_text(encoding="utf-8") == '{"fresh": true}'


def test_get_credentials_runs_flow_when_no_token_file(tmp_path):
    token_path = tmp_path / "token.json"
    client_secret_path = tmp_path / "client_secret.json"

    new_creds = MagicMock()
    new_creds.to_json.return_value = '{"fresh": true}'
    flow = MagicMock()
    flow.run_local_server.return_value = new_creds

    with patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=flow) as flow_factory:
        result = auth.get_credentials(client_secret_path, token_path, ["scope1"])

    flow_factory.assert_called_once_with(str(client_secret_path), ["scope1"])
    assert result is new_creds
    assert token_path.read_text(encoding="utf-8") == '{"fresh": true}'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.auth'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/auth.py
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def get_credentials(client_secret_path: Path, token_path: Path, scopes: list[str] = SCOPES) -> Credentials:
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            creds = None

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "feat: add OAuth2 credential handling with refresh fallback"
```

---

### Task 10: CLI orchestration

**Files:**
- Create: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `analytics_date_range` (Task 2), `parse_selection` (Task 3), `REPORTS`/`ReportDef` (Task 5), `run_report` (Task 6), `list_channel_videos` (Task 7), `assemble_video_document`/`save_video_report`/`save_consolidated`/`save_channel_videos_snapshot` (Task 8), `get_credentials`/`SCOPES` (Task 9).
- Produces: `select_videos(videos, input_fn=input, print_fn=print) -> list[dict]`, `extract_video(analytics_service, video, today, report_defs=REPORTS, print_fn=print) -> dict`, `run(youtube_service, analytics_service, output_dir, today, input_fn=input, print_fn=print, report_defs=REPORTS) -> None`, `main() -> None`. This is the final integration point — no later task depends on it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main.py
from datetime import date
from pathlib import Path

import pytest

import main as main_module
from main import extract_video, run, select_videos
from src.reports import ReportDef


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


class FakeYouTubeService:
    def __init__(self, videos):
        self._videos = videos


def fake_list_channel_videos(_service):
    return _service._videos


# --- select_videos ---


def test_select_videos_returns_chosen_subset():
    videos = [{"id": "v1", "title": "A"}, {"id": "v2", "title": "B"}, {"id": "v3", "title": "C"}]
    inputs = iter(["1,3"])

    selected = select_videos(videos, input_fn=lambda _prompt: next(inputs), print_fn=lambda _msg: None)

    assert selected == [videos[0], videos[2]]


def test_select_videos_retries_on_invalid_input():
    videos = [{"id": "v1", "title": "A"}]
    inputs = iter(["not-a-number", "1"])
    messages = []

    selected = select_videos(videos, input_fn=lambda _prompt: next(inputs), print_fn=messages.append)

    assert selected == [videos[0]]
    assert any("inválida" in message for message in messages)


# --- extract_video ---


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


# --- run (end to end with fakes) ---


def _always_empty_responder(_kwargs):
    return {"columnHeaders": [], "rows": []}


def test_run_saves_all_videos_and_consolidated_file(tmp_path, monkeypatch):
    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT1M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z", "duration": "PT2M"},
    ]
    youtube_service = FakeYouTubeService(videos)
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)

    run(
        youtube_service,
        analytics_service,
        tmp_path,
        date(2024, 2, 1),
        input_fn=lambda _prompt: "todos",
        print_fn=lambda _msg: None,
    )

    assert (tmp_path / "por_video" / "vid1.json").exists()
    assert (tmp_path / "por_video" / "vid2.json").exists()
    assert (tmp_path / "consolidado.json").exists()
    assert (tmp_path / "channel_videos.json").exists()


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

    run(
        youtube_service,
        analytics_service,
        tmp_path,
        date(2024, 2, 1),
        input_fn=lambda _prompt: "todos",
        print_fn=lambda _msg: None,
    )

    assert not (tmp_path / "por_video" / "vid1.json").exists()
    assert (tmp_path / "por_video" / "vid2.json").exists()
    assert (tmp_path / "consolidado.json").exists()


def test_run_handles_channel_with_no_videos(tmp_path, monkeypatch):
    youtube_service = FakeYouTubeService([])
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)
    messages = []

    run(
        youtube_service,
        analytics_service,
        tmp_path,
        date(2024, 2, 1),
        input_fn=lambda _prompt: pytest.fail("should not prompt when there are no videos"),
        print_fn=messages.append,
    )

    assert any("Nenhum vídeo" in message for message in messages)
    assert not (tmp_path / "consolidado.json").exists()
    assert (tmp_path / "channel_videos.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Write minimal implementation**

```python
# main.py
from datetime import date
from pathlib import Path

from googleapiclient.discovery import build

from src.auth import SCOPES, get_credentials
from src.date_ranges import analytics_date_range
from src.reports import REPORTS
from src.selection import parse_selection
from src.storage import (
    assemble_video_document,
    save_channel_videos_snapshot,
    save_consolidated,
    save_video_report,
)
from src.youtube_analytics import run_report, shape_report_result
from src.youtube_data import list_channel_videos


def select_videos(videos, input_fn=input, print_fn=print):
    print_fn("Vídeos encontrados:")
    for i, video in enumerate(videos, start=1):
        print_fn(f"[{i}] {video['title']} (publicado em {video['published_at'][:10]}) - ID: {video['id']}")

    while True:
        raw = input_fn("Digite o número do vídeo, vários separados por vírgula, ou 'todos': ")
        try:
            indices = parse_selection(raw, len(videos))
            return [videos[i - 1] for i in indices]
        except ValueError as exc:
            print_fn(f"Entrada inválida: {exc}. Tente novamente.")


def extract_video(analytics_service, video, today, report_defs=REPORTS, print_fn=print):
    start_date, end_date = analytics_date_range(video["published_at"], today)
    shaped = {}
    for report_def in report_defs:
        try:
            rows = run_report(analytics_service, video["id"], start_date, end_date, report_def)
        except Exception as exc:
            print_fn(f"  aviso: falha ao extrair '{report_def.name}' para {video['id']}: {exc}")
            rows = []
        shaped[report_def.name] = shape_report_result(report_def, rows)
    return shaped


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

    documents = []
    for video in selected:
        print_fn(f"Processando '{video['title']}' ({video['id']})...")
        try:
            shaped_reports = extract_video(analytics_service, video, today, report_defs, print_fn=print_fn)
            document = assemble_video_document(video, shaped_reports)
            save_video_report(output_dir, video["id"], document)
            documents.append(document)
        except Exception as exc:
            print_fn(f"  erro ao processar {video['id']}, pulando: {exc}")

    if documents:
        save_consolidated(output_dir, documents, today.isoformat())
        print_fn(f"Concluído: {len(documents)} vídeo(s) processado(s).")


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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every module PASS.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: wire CLI orchestration for video selection and extraction"
```

---

### Task 11: Credential setup guide (README)

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: the user-facing setup and usage guide. Nothing later depends on this.

- [ ] **Step 1: Write `README.md`**

```markdown
# YouTube Analytics Extractor

Script de linha de comando que lista os vídeos do seu canal do YouTube,
permite escolher um vídeo, vários, ou todos, e extrai um conjunto amplo de
métricas do YouTube Analytics para arquivos JSON em `output/`.

## 1. Configurar credenciais no Google Cloud

1. Acesse https://console.cloud.google.com/ e crie um novo projeto (ou use um existente).
2. No menu "APIs e Serviços" > "Biblioteca", habilite:
   - **YouTube Data API v3**
   - **YouTube Analytics API**
3. Em "APIs e Serviços" > "Tela de consentimento OAuth":
   - Tipo de usuário: **Externo**.
   - Preencha nome do app e e-mail de contato.
   - Em "Usuários de teste", adicione a sua própria conta do Google (a mesma do canal).
4. Em "APIs e Serviços" > "Credenciais" > "Criar credenciais" > "ID do cliente OAuth":
   - Tipo de aplicativo: **App para computador (Desktop app)**.
   - Baixe o JSON gerado e salve como `client_secret.json` na raiz deste projeto.

`client_secret.json` e `token.json` nunca devem ser commitados — ambos já
estão no `.gitignore`.

## 2. Instalar dependências

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Rodar o script

```bash
python main.py
```

Na primeira execução, o navegador abrirá para você logar com a conta do
Google dona do canal e autorizar o acesso somente leitura ao YouTube e ao
YouTube Analytics. O token de acesso fica salvo em `token.json` e é reusado
(e renovado automaticamente) nas próximas execuções.

O script então lista os vídeos do canal. Digite:
- um número (ex: `3`) para extrair um único vídeo;
- vários números separados por vírgula (ex: `1,4,7`);
- `todos` (ou `all`) para extrair todos os vídeos do canal.

## 4. Onde ficam os dados

```
output/
├── channel_videos.json       # snapshot de todos os vídeos do canal
├── por_video/
│   └── <video_id>.json       # metadados + todas as métricas daquele vídeo
└── consolidado.json          # todos os vídeos processados nesta execução, em um único arquivo
```

Cada arquivo por vídeo contém: totais acumulados, série diária, fontes de
tráfego, dispositivos, geografia, demografia (faixa etária/gênero) e curva
de retenção de audiência.

## 5. Rodando os testes

```bash
pytest
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add setup and usage guide"
```
