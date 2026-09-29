# AI Performance Report Generator — Design

- Date: 2026-09-29
- Status: Approved

## Purpose

The user already has a working extractor (`main.py`) that pulls YouTube
Analytics data into `output/por_video/<id>.json`. This project adds a second,
independent script that reads that already-extracted data and uses the
Claude API to write a human-readable performance report per video: what the
numbers say, how the video compares to the channel's own average, and
concrete recommendations.

Success = running `python analyze.py`, picking one/several/all videos that
have already been extracted, and getting a Markdown report per video in
`reports/` that a human can read to understand and act on that video's
performance.

## Scope

Included:
- Reading previously extracted per-video JSON from `output/por_video/*.json`
  (produced by the existing extractor — this script never talks to the
  YouTube APIs).
- Computing channel-wide averages across all extracted videos, to give the
  AI a baseline for "did this video over/under-perform".
- Interactive selection of which extracted videos to analyze (reusing the
  extractor's existing `parse_selection` — one video, several by comma, or
  "todos"/"all").
- One Claude API call per selected video, asking for a Markdown report
  covering: performance summary, comparison to the channel average, and
  actionable recommendations.
- Saving one Markdown file per video to `reports/<video_id>.md`.
- Loading `ANTHROPIC_API_KEY` from a local `.env` file via `python-dotenv`,
  in addition to a real environment variable.
- Continuing past a single video's failure during a "todos" batch (a report
  generation failure for one video must not abort the rest).

Out of scope (YAGNI for now):
- Talking to the YouTube APIs — this script only reads files the extractor
  already produced.
- A single combined report across all videos (user chose one-file-per-video).
- Any non-Anthropic AI provider.
- Caching/re-using a previous report — every run regenerates from scratch
  for the videos selected.
- A cost/budget confirmation prompt before a large "todos" batch — documented
  as a cost consideration in the README instead (see Non-goals rationale
  below); can be added later if it turns out to be needed.

## Architecture

A second standalone Python script (`analyze.py`), sitting alongside the
existing `main.py` in the same project, reusing `src/selection.py` from the
extractor. New code lives in two new modules under `src/`.

```
yt_data_extractor/
├── analyze.py              # new — CLI entrypoint for report generation
├── main.py                 # existing — extractor, untouched
├── src/
│   ├── selection.py         # existing — reused as-is
│   ├── report_data.py       # new — load extracted JSON + compute channel averages
│   ├── ai_report.py         # new — build prompt + call Claude API
│   └── ...                  # existing extractor modules, untouched
└── reports/                 # generated at runtime, git-ignored
```

### Components

**`src/report_data.py`**
- `load_video_documents(output_dir: Path) -> list[dict]`: reads every
  `output/por_video/*.json` file and returns their parsed contents. Pure I/O,
  no network.
- `compute_channel_averages(documents: list[dict]) -> dict`: given the loaded
  video documents, averages the core metrics from each video's `totals`
  block (views, estimatedMinutesWatched, averageViewDuration,
  averageViewPercentage, likes, comments, shares, subscribersGained,
  subscribersLost) across all videos. Pure function, no I/O — easy to unit
  test with hand-built fixtures. Returns an empty-safe result (zeros) if
  given zero documents, so a single-video channel doesn't crash.

**`src/ai_report.py`**
- `build_report_prompt(video_document: dict, channel_averages: dict) -> str`:
  pure function that formats the video's full JSON document and the channel
  averages into the user-turn text sent to Claude. No network.
- `generate_report(client, video_document: dict, channel_averages: dict, model: str = "claude-opus-5") -> str`:
  calls the Anthropic Messages API (via `client.messages.stream(...)`,
  adaptive thinking, `claude-opus-5`) with a system prompt establishing the
  analyst role and the user prompt from `build_report_prompt`, and returns
  the report's Markdown text. `client` is injected so tests can pass a fake
  that mimics the SDK's `.messages.stream(...).get_final_message()` shape,
  matching the fake-client pattern already used for the YouTube API clients
  in this project.

**`analyze.py` (CLI/orchestration)**
- Loads `.env` via `python-dotenv`'s `load_dotenv()` before constructing the
  Anthropic client, so `ANTHROPIC_API_KEY` can come from a local `.env` file
  or a real environment variable.
- Loads all video documents from `output/por_video/`. If none are found,
  prints a clear message telling the user to run the extractor first, and
  exits without prompting.
- Computes channel averages once from all loaded documents.
- Prints a numbered list of the available (already-extracted) videos by
  title, reads the user's selection via the existing `parse_selection`.
- For each selected video: calls `generate_report`, writes the Markdown
  result to `reports/<video_id>.md`, and prints progress. A report-generation
  failure for one video is caught, logged, and does not stop the batch.
- Prints a final summary line (videos processed vs. failed), mirroring the
  extractor's existing summary behavior.

### Data flow

1. `load_dotenv()` → environment has `ANTHROPIC_API_KEY` (from `.env` or the
   real environment).
2. `report_data.load_video_documents(Path("output/por_video"))` → list of
   video documents (each the same shape the extractor already writes).
3. `report_data.compute_channel_averages(documents)` → one dict of channel
   averages.
4. CLI prints the numbered list (title + id, from each document's `video`
   block) and reads the selection via `selection.parse_selection`.
5. For each selected document: `ai_report.generate_report(client, document,
   channel_averages)` → Markdown string.
6. Write each result to `reports/<video_id>.json`'s sibling
   `reports/<video_id>.md`.
7. Print the summary line.

### Prompt content

The system prompt establishes the role ("Você é um analista de dados de
YouTube...") and the required Markdown structure (performance summary,
comparison to channel average, actionable recommendations), all in
Portuguese to match the rest of the tool's output. The user turn includes:
the video's full JSON document (metadata + all extracted reports:
totals, daily, traffic_sources, devices, geography, demographics,
retention, and any `errors` the extractor recorded) and the channel
averages dict, both as formatted JSON blocks — no pre-summarization on the
Python side; the model does the analytical work.

### Model configuration

- Model: `claude-opus-5` (the skill's non-negotiable default; no cheaper
  model substitution).
- `thinking: {"type": "adaptive"}` — report writing with cross-video
  comparison and recommendations is complex enough to benefit from it.
- Streamed via `client.messages.stream(...).get_final_message()`, per the
  skill's guidance to default to streaming for requests that may involve
  larger input and to avoid SDK timeout guards.
- `max_tokens` sized for a Markdown report (not a full codebase), not the
  large multi-tens-of-thousands ceiling used for coding tasks.

## Output format

`reports/<video_id>.md` — one Markdown file per analyzed video, human
readable, no fixed machine-parsed schema (unlike the extractor's JSON
output, this is meant to be read directly).

## Error handling

- No extracted videos found (`output/por_video/` empty or missing): print a
  clear message telling the user to run the extractor (`main.py`) first,
  and exit without prompting — mirrors the extractor's zero-videos handling.
- Invalid selection input at the prompt: rejected with a clear message,
  re-prompt — reuses the extractor's existing `parse_selection` behavior
  as-is.
- A Claude API failure for one video (rate limit, refusal, network error):
  caught, logged with the video id, and the batch continues with the next
  video — same resilience philosophy as the extractor's per-video handling.
- Missing `ANTHROPIC_API_KEY` (not in `.env` or the environment): the
  Anthropic SDK's own `AuthenticationError` surfaces; the script doesn't add
  a redundant pre-check beyond what the SDK already reports clearly.

## Credentials

`ANTHROPIC_API_KEY` is read from a local `.env` file (loaded via
`python-dotenv`) or a real environment variable — whichever is set. `.env`
is already in `.gitignore` and must never be committed. The README will
document how to get a key from the Anthropic Console and put it in `.env`.

## Cost consideration (non-goal rationale)

Each analyzed video is one paid Claude API call. Running "todos" on a
channel with many extracted videos incurs a proportional cost. This is
documented explicitly in the README rather than gated behind a confirmation
prompt, consistent with how the extractor's own "todos" already proceeds
without a confirmation step.

## Testing

Same philosophy as the extractor: pure logic
(`compute_channel_averages`, `build_report_prompt`) gets real unit tests
with hand-built fixtures; the Claude API call (`generate_report`) is tested
with a fake client matching the SDK's `.messages.stream(...)` shape (no real
network calls in tests, no mocking the SDK's internals); the end-to-end CLI
flow (`analyze.py`'s orchestration function) is tested with a fake client
and a temp directory of fixture JSON files, verifying continue-on-error and
the zero-videos-found path, mirroring `tests/test_main.py`'s approach in
this same project.
