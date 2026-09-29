# Local Web App + Packaged Binary — Design

- Date: 2026-09-29
- Status: Approved

## Purpose

The extractor (`main.py`) and AI report generator (`analyze.py`) are today
two separate terminal scripts, each driven by `input()` prompts, requiring a
Python environment (`.venv` + `pip install -r requirements.txt`) to run.
This project wraps both flows in a single local web UI, served from a
packaged, double-clickable binary — no Python install, no terminal.

Success = double-clicking the app on macOS (or Windows), getting a native
app window, walking through: first-run credential setup → pick videos to
extract → watch live progress → pick extracted videos to generate AI
reports for → watch live progress → browse the extracted metrics and
generated reports, all without touching a terminal or a `.json`/`.md` file
directly.

## Scope

Included:
- A local FastAPI server exposing the extractor and analyzer as HTTP
  endpoints, reusing their existing `run()` orchestration functions with
  minimal changes (see Architecture).
- A first-run Setup screen to enter Google OAuth `client_secret.json`
  contents and the Anthropic API key, persisted to a per-user app data
  directory (not the project folder, since a packaged binary's own folder
  may not be writable).
- An Extract screen: lists channel videos (triggers the existing Google
  OAuth browser consent flow on first use, unchanged), lets the user check
  one/several/all videos, and streams live progress while extraction runs.
- An Analyze screen: lists already-extracted videos, lets the user check
  one/several/all, shows the number of Claude API calls that selection will
  make before confirming, and streams live progress while report
  generation runs.
- A Browse screen: lists videos that have been extracted and/or analyzed,
  and shows a given video's extracted metrics (from
  `output/por_video/<id>.json`) and its generated report (from
  `reports/<id>.md`) side by side.
- A `pywebview` desktop shell that starts the FastAPI server in a
  background thread, opens a native app window pointed at it, and shuts the
  server down when the window closes.
- PyInstaller packaging producing one executable for macOS and one for
  Windows, built via a GitHub Actions matrix (PyInstaller cannot
  cross-compile, so each OS's binary must be built on that OS).

Out of scope (YAGNI for now):
- Linux packaging/binary (not requested).
- Multi-user/multi-channel support — one channel's credentials at a time,
  same as today.
- Editing or deleting extracted data/reports from the UI — browsing only.
- Any UI framework/build step (React, Vue, bundlers) — plain HTML/CSS/JS
  served as static files is enough for four simple screens.
- Auto-update mechanism for the packaged binary.
- Re-authenticating or rotating credentials from the UI after first setup
  (can be added later if needed; for now, re-running setup overwrites the
  stored files, same as re-placing `client_secret.json` today).

## Architecture

A new `src/web/` package holds the FastAPI app and job orchestration,
reusing the existing `src/` extractor/analyzer modules and the `run()`
functions in `main.py`/`analyze.py` unchanged in spirit (adapted to accept
a selection list directly and a log-sink callback instead of
`input_fn`/`print_fn` tied to a terminal). A new top-level `desktop.py` is
the packaged app's entry point.

```
yt_data_extractor/
├── desktop.py                 # new — app entry point: starts server + webview window
├── main.py                    # existing — CLI entrypoint, untouched
├── analyze.py                 # existing — CLI entrypoint, untouched
├── src/
│   ├── auth.py                 # existing — reused as-is (OAuth flow)
│   ├── selection.py             # existing — reused as-is
│   ├── storage.py               # existing — reused as-is
│   ├── report_data.py           # existing — reused as-is
│   ├── ai_report.py             # existing — reused as-is
│   ├── ...                      # other existing extractor modules, untouched
│   └── web/                     # new
│       ├── app.py               # FastAPI app factory + route registration
│       ├── jobs.py              # background job runner + log-line broadcast (SSE)
│       ├── setup.py             # credential setup endpoints + app-data-dir paths
│       ├── extract.py           # extract endpoints, thin wrapper over main.run()
│       ├── analyze_routes.py    # analyze endpoints, thin wrapper over analyze.run()
│       └── results.py           # browse/list endpoints over output/ and reports/
├── static/                    # new — plain HTML/CSS/JS frontend
│   ├── index.html
│   ├── app.js
│   └── app.css
└── build/                     # new — PyInstaller spec + CI workflow
    ├── desktop.spec
    └── (GitHub Actions workflow under .github/workflows/)
```

### Components

**`src/web/setup.py`**
- `app_data_dir() -> Path`: returns the platform user-data directory via
  `platformdirs.user_data_dir("yt-data-extractor")`, creating it if
  missing. All credential/token files live here instead of the project
  root when running as the packaged app.
- `GET /api/setup/status`: returns whether `client_secret.json` and an
  Anthropic key are already configured.
- `POST /api/setup`: accepts the pasted `client_secret.json` contents and
  the Anthropic API key, writes them to `app_data_dir()` as
  `client_secret.json` and `.env` (`ANTHROPIC_API_KEY=...`).

**`src/web/jobs.py`**
- A small in-memory job registry: starts a named job
  (`"extract"`/`"analyze"`) in a background thread, gives it a `log(line:
  str)` callback that appends to an `asyncio.Queue` (or thread-safe
  equivalent) consumed by an SSE endpoint, and records a final status
  (done/error + summary) when the thread finishes. One job of each kind can
  run at a time; starting a new one while one is in-flight is rejected with
  a clear error rather than allowed to race.

**`src/web/extract.py`**
- `GET /api/videos`: calls `src.auth.get_credentials` (unchanged — still
  pops the system browser for Google consent on first use, same as the CLI
  today) then `src.youtube_data.list_channel_videos`, returns the list for
  the UI to render as checkboxes.
- `POST /api/extract {video_ids: list[str]}`: starts an `"extract"`
  background job that loops the given videos through the same per-video
  logic `main.run()` already contains (`extract_video`,
  `assemble_video_document`, `save_video_report`, continue-on-error), using
  `jobs.log()` in place of `print_fn`. No terminal `input()` involved —
  selection comes from the request body, not a prompt.
- `GET /api/extract/stream`: SSE endpoint streaming the current/most recent
  extract job's log lines as they arrive, ending with a summary event.

**`src/web/analyze_routes.py`**
- `GET /api/analyzable`: lists already-extracted videos (via
  `report_data.load_video_documents`) for the UI to render as checkboxes,
  same data the CLI's `analyze.py` prints as a numbered list today.
- `POST /api/analyze {video_ids: list[str]}`: starts an `"analyze"`
  background job reusing `analyze.run()`'s per-video logic
  (`generate_report`, write `reports/<id>.md`, continue-on-error), logging
  through `jobs.log()`.
- `GET /api/analyze/stream`: SSE endpoint, same pattern as extract's.
- The UI computes and displays "this will make N Claude API calls" from
  `len(video_ids)` before the user confirms — no new backend endpoint
  needed for that, it's just the selection count.

**`src/web/results.py`**
- `GET /api/results`: lists every video id present under
  `output/por_video/` and/or `reports/`, with flags for which of the two
  exist for each.
- `GET /api/results/{video_id}`: returns the parsed
  `output/por_video/<id>.json` contents and the raw
  `reports/<id>.md` text (if present) for that video.

**`static/` (frontend)**
- `index.html` + `app.js` + `app.css`: no build step, fetches the JSON
  endpoints above and consumes the two SSE streams with `EventSource`.
  Four simple views (Setup, Extract, Analyze, Browse) switched client-side;
  Setup is shown first whenever `/api/setup/status` reports missing
  credentials.

**`desktop.py`**
- Starts the FastAPI app (via `uvicorn.Server` run in a background thread)
  bound to `127.0.0.1:0` (OS-assigned free port), reads back the assigned
  port, then opens a `webview.create_window(...)` pointed at
  `http://127.0.0.1:<port>` and calls `webview.start()`. On window close,
  signals the uvicorn server to shut down so no orphaned process remains.

**`build/desktop.spec` + CI**
- A PyInstaller spec bundling `desktop.py`, `static/`, and all `src/`
  modules into a single executable, run once on a macOS GitHub Actions
  runner and once on a Windows runner (matrix build), each uploading its
  platform's binary as a release artifact.

### Data flow

1. `desktop.py` starts the FastAPI server on a free local port and opens
   the pywebview window.
2. Frontend calls `GET /api/setup/status`. If credentials are missing, it
   shows Setup; `POST /api/setup` persists them to `app_data_dir()`.
3. Frontend calls `GET /api/videos` (Extract screen) → triggers OAuth
   browser popup on first use via the existing `src.auth.get_credentials`
   → user checks videos → `POST /api/extract` → frontend opens
   `GET /api/extract/stream` (SSE) and appends each log line live until the
   summary event arrives.
4. Frontend calls `GET /api/analyzable` (Analyze screen) → user checks
   videos, sees the call-count estimate, confirms → `POST /api/analyze` →
   `GET /api/analyze/stream` (SSE), same live-log pattern.
5. Frontend calls `GET /api/results` (Browse screen) → user picks a video →
   `GET /api/results/{id}` → UI renders the JSON metrics and the Markdown
   report.

### Reused vs. new code

`main.run()` and `analyze.run()`'s per-item loop bodies (the part that
calls `extract_video`/`generate_report`, saves output, and continues past
per-video errors) are extracted into small functions callable from both the
existing CLI entrypoints (unchanged behavior) and the new web job functions
— avoiding a second implementation of the same extraction/analysis loop.
The CLI scripts (`main.py`, `analyze.py`) keep working exactly as they do
today for terminal use; the web layer is additive, not a replacement.

## Error handling

- **Per-video failures**: unchanged — caught, logged, and the batch
  continues, exactly as `main.run()`/`analyze.run()` already do. In the web
  UI this becomes a log line in the SSE stream plus an entry in the final
  summary instead of a printed line.
- **OAuth/credential problems**: a missing/invalid `client_secret.json`, an
  expired refresh token that fails to refresh, or a missing Anthropic key
  surface as a readable error (Setup screen message or a log line in the
  stream), never an unhandled crash. An expired-refresh case re-triggers
  the same browser consent popup the CLI already falls back to.
- **Port conflicts**: the server binds to port `0` (OS picks a free port),
  so it can never collide with something already running locally.
- **Concurrent job start**: starting a new extract/analyze job while one of
  the same kind is already running is rejected with a clear "already
  running" response rather than silently racing two loops writing to the
  same files.
- **Window close mid-job**: closing the app window while a job is running
  stops the server; the in-flight job's already-completed per-video files
  remain on disk (partial progress is not rolled back, matching the
  extractor's existing "continue and report what succeeded" philosophy).

## Credentials

Google `client_secret.json`/`token.json` and the Anthropic key move from
the project root (today's `.gitignore`'d files) to the platform user-data
directory (`platformdirs.user_data_dir("yt-data-extractor")`) when running
as the packaged app, entered once via the Setup screen. The CLI scripts
(`main.py`/`analyze.py`) are unaffected and keep reading from the project
root as they do today — the two entry points intentionally use different
storage locations since one runs from a source checkout and the other from
an installed binary.

## Testing

- Existing `tests/` suite is untouched — it tests `src/` logic directly,
  not either entrypoint's I/O shell.
- New tests for `src/web/`: FastAPI `TestClient` against each endpoint
  (setup status/persist, video listing with a fake YouTube client, job
  start/reject-if-running, results listing/reading), and an SSE stream test
  asserting log lines from a fake multi-video job arrive in order ending
  with a summary event — same fake-client philosophy already used for the
  YouTube/Anthropic API clients in this project, no real network calls.
- `desktop.py` and the PyInstaller packaging are verified manually (not
  unit tested): a full run of the packaged macOS binary through
  setup → extract → analyze → browse, plus a Windows build produced by CI
  and smoke-tested the same way, before considering the binary done.
