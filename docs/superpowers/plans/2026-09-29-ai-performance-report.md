# AI Performance Report Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a second CLI script (`analyze.py`) that reads the videos already extracted by `main.py`, computes channel-wide averages, and uses the Claude API to write a Markdown performance report per selected video in `reports/`.

**Architecture:** Two new pure-logic modules (`src/report_data.py` for loading/averaging, `src/ai_report.py` for prompt-building and the Claude API call) plus a thin CLI entrypoint (`analyze.py`) that mirrors `main.py`'s existing structure and reuses `src/selection.py` as-is.

**Tech Stack:** Python 3.10+, `anthropic` (Claude API SDK), `python-dotenv`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-29-ai-performance-report-design.md`

## Global Constraints

- Model is always `claude-opus-5` — no cheaper substitution.
- This script only reads files under `output/por_video/` that `main.py` already produced — it never calls the YouTube APIs itself.
- One Markdown file per video at `reports/<video_id>.md` — no combined single-file report.
- `ANTHROPIC_API_KEY` is loaded via `.env` (through `python-dotenv`) or a real environment variable; `.env` must stay in `.gitignore` and is never committed.
- A report-generation failure for one video during a "todos" batch must not abort the rest of the batch.

## Review Focus

- No extracted videos found (`output/por_video/` missing or empty) — the script must print a clear message telling the user to run `main.py` first and must not prompt for a selection. (Task 3)
- The user types garbage at the video-selection prompt — the script must reject it with a clear message and ask again, not crash. (Task 3, reusing `src/selection.py`)
- One video's report generation fails during a "todos" batch (rate limit, refusal, network error) — the other videos must still be processed and saved, and the run must finish with a summary naming the failure. (Task 3)
- Every video's report generation fails (e.g. a missing or invalid `ANTHROPIC_API_KEY`) — the run must still print a summary (0 processed, N failed) instead of crashing or silently producing nothing. (Task 3)
- Exactly one video has been extracted — computing the channel average must not divide by zero or crash, and should return that video's own numbers rather than erroring. (Task 1)

---

### Task 1: Report data loading and channel averages

**Files:**
- Modify: `requirements.txt`
- Create: `src/report_data.py`
- Test: `tests/test_report_data.py`

**Interfaces:**
- Consumes: `CORE_METRICS` from `src/reports.py` (already exists: `["views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes", "comments", "shares", "subscribersGained", "subscribersLost"]`).
- Produces: `load_video_documents(output_dir: Path) -> list[dict]`, `compute_channel_averages(documents: list[dict]) -> dict`. Used by Task 3 (`analyze.py`).

- [ ] **Step 1: Add new dependencies to `requirements.txt`**

```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
pytest>=7.4.0
anthropic>=0.40.0
python-dotenv>=1.0.0
```

- [ ] **Step 2: Install the new dependencies**

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: install completes with no errors.

- [ ] **Step 3: Write the failing tests**

```python
# tests/test_report_data.py
import json

from src.report_data import compute_channel_averages, load_video_documents


def test_load_video_documents_reads_all_json_files(tmp_path):
    por_video = tmp_path / "por_video"
    por_video.mkdir()
    (por_video / "vid1.json").write_text(json.dumps({"video": {"id": "vid1"}}), encoding="utf-8")
    (por_video / "vid2.json").write_text(json.dumps({"video": {"id": "vid2"}}), encoding="utf-8")

    documents = load_video_documents(tmp_path)

    assert len(documents) == 2
    assert {d["video"]["id"] for d in documents} == {"vid1", "vid2"}


def test_load_video_documents_returns_empty_list_when_directory_missing(tmp_path):
    assert load_video_documents(tmp_path) == []


def test_compute_channel_averages_averages_core_metrics_across_videos():
    documents = [
        {
            "totals": {
                "views": 100,
                "estimatedMinutesWatched": 500,
                "averageViewDuration": 30,
                "averageViewPercentage": 40.0,
                "likes": 10,
                "comments": 2,
                "shares": 1,
                "subscribersGained": 3,
                "subscribersLost": 0,
            }
        },
        {
            "totals": {
                "views": 300,
                "estimatedMinutesWatched": 1500,
                "averageViewDuration": 50,
                "averageViewPercentage": 60.0,
                "likes": 30,
                "comments": 6,
                "shares": 3,
                "subscribersGained": 9,
                "subscribersLost": 2,
            }
        },
    ]

    averages = compute_channel_averages(documents)

    assert averages["views"] == 200
    assert averages["subscribersLost"] == 1


def test_compute_channel_averages_handles_missing_or_empty_totals():
    documents = [{"totals": {"views": 100}}, {"totals": {}}]

    averages = compute_channel_averages(documents)

    assert averages["views"] == 50
    assert averages["likes"] == 0


def test_compute_channel_averages_returns_zeros_for_no_documents():
    averages = compute_channel_averages([])

    assert averages["views"] == 0
    assert averages["likes"] == 0


def test_compute_channel_averages_with_single_video_returns_its_own_totals():
    documents = [{"totals": {"views": 42, "likes": 5}}]

    averages = compute_channel_averages(documents)

    assert averages["views"] == 42
    assert averages["likes"] == 5
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_report_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.report_data'`

- [ ] **Step 5: Write minimal implementation**

```python
# src/report_data.py
import json
from pathlib import Path

from src.reports import CORE_METRICS


def load_video_documents(output_dir: Path) -> list[dict]:
    por_video_dir = output_dir / "por_video"
    if not por_video_dir.is_dir():
        return []

    documents = []
    for path in sorted(por_video_dir.glob("*.json")):
        documents.append(json.loads(path.read_text(encoding="utf-8")))
    return documents


def compute_channel_averages(documents: list[dict]) -> dict:
    if not documents:
        return {metric: 0 for metric in CORE_METRICS}

    sums = {metric: 0 for metric in CORE_METRICS}
    for document in documents:
        totals = document.get("totals") or {}
        for metric in CORE_METRICS:
            sums[metric] += totals.get(metric, 0) or 0

    count = len(documents)
    return {metric: sums[metric] / count for metric in CORE_METRICS}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_report_data.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/report_data.py tests/test_report_data.py
git commit -m "feat: add report data loading and channel averages"
```

---

### Task 2: Claude API report generation

**Files:**
- Create: `src/ai_report.py`
- Test: `tests/test_ai_report.py`

**Interfaces:**
- Consumes: nothing beyond plain dicts and an injected `client`.
- Produces: `SYSTEM_PROMPT: str`, `build_report_prompt(video_document: dict, channel_averages: dict) -> str`, `generate_report(client, video_document: dict, channel_averages: dict, model: str = "claude-opus-5") -> str` (raises on `stop_reason == "refusal"`). Used by Task 3 (`analyze.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ai_report.py
import pytest

from src.ai_report import build_report_prompt, generate_report


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


class FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        return _StreamContext(self._response)


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def test_build_report_prompt_includes_video_and_averages_json():
    video_document = {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}}
    channel_averages = {"views": 50}

    prompt = build_report_prompt(video_document, channel_averages)

    assert "vid1" in prompt
    assert "Video 1" in prompt
    assert '"views": 100' in prompt
    assert '"views": 50' in prompt


def test_generate_report_returns_text_from_response():
    response = FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])
    client = FakeClient(response)
    video_document = {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}}
    channel_averages = {"views": 50}

    result = generate_report(client, video_document, channel_averages)

    assert "Resumo de desempenho" in result
    assert client.messages.last_kwargs["model"] == "claude-opus-5"
    assert client.messages.last_kwargs["thinking"] == {"type": "adaptive"}
    assert client.messages.last_kwargs["output_config"] == {"effort": "medium"}
    assert client.messages.last_kwargs["max_tokens"] >= 8192
    assert isinstance(client.messages.last_kwargs["system"], str)
    assert client.messages.last_kwargs["system"]
    assert client.messages.last_kwargs["messages"] == [
        {"role": "user", "content": build_report_prompt(video_document, channel_averages)}
    ]


def test_generate_report_raises_on_refusal():
    response = FakeResponse([], stop_reason="refusal")
    client = FakeClient(response)
    video_document = {"video": {"id": "vid1"}, "totals": {}}

    with pytest.raises(RuntimeError):
        generate_report(client, video_document, {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ai_report'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ai_report.py
import json

SYSTEM_PROMPT = (
    "Você é um analista de dados de YouTube. Com base nos dados fornecidos, "
    "escreva um relatório em Markdown, em português, com exatamente estas "
    "seções: '## Resumo de desempenho', '## Comparação com a média do canal' "
    "e '## Recomendações acionáveis'. Seja específico e cite os números "
    "relevantes dos dados fornecidos."
)


def build_report_prompt(video_document: dict, channel_averages: dict) -> str:
    video_json = json.dumps(video_document, ensure_ascii=False, indent=2)
    averages_json = json.dumps(channel_averages, ensure_ascii=False, indent=2)
    return (
        "Dados completos do vídeo (metadados + métricas extraídas do YouTube Analytics):\n"
        f"```json\n{video_json}\n```\n\n"
        "Médias do canal (calculadas a partir de todos os vídeos já extraídos, "
        "para efeito de comparação):\n"
        f"```json\n{averages_json}\n```"
    )


def generate_report(
    client,
    video_document: dict,
    channel_averages: dict,
    model: str = "claude-opus-5",
) -> str:
    prompt = build_report_prompt(video_document, channel_averages)

    with client.messages.stream(
        model=model,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("a análise foi recusada pelo modelo (stop_reason=refusal)")

    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ai_report.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ai_report.py tests/test_ai_report.py
git commit -m "feat: add Claude API report generation"
```

---

### Task 3: CLI orchestration

**Files:**
- Create: `analyze.py`
- Modify: `.gitignore` (add `reports/`)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `load_video_documents`/`compute_channel_averages` (Task 1), `generate_report` (Task 2), `parse_selection` from `src/selection.py` (already exists: `parse_selection(raw: str, total: int) -> list[int]`).
- Produces: `select_videos(documents, input_fn=input, print_fn=print) -> list[dict]`, `run(client, output_dir: Path, reports_dir: Path, input_fn=input, print_fn=print) -> None`, `main() -> None`. Final integration point — nothing depends on it.

- [ ] **Step 1: Add `reports/` to `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
client_secret.json
token.json
output/
.pytest_cache/
.env
reports/
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_analyze.py
import json

import pytest

from analyze import run, select_videos


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


def _write_document(por_video_dir, video_id, title, views=100):
    document = {"video": {"id": video_id, "title": title}, "totals": {"views": views}}
    (por_video_dir / f"{video_id}.json").write_text(json.dumps(document), encoding="utf-8")


def _always_ok_responder(_kwargs):
    return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])


def test_select_videos_returns_chosen_subset():
    documents = [
        {"video": {"id": "v1", "title": "A"}},
        {"video": {"id": "v2", "title": "B"}},
        {"video": {"id": "v3", "title": "C"}},
    ]
    inputs = iter(["1,3"])

    selected = select_videos(documents, input_fn=lambda _p: next(inputs), print_fn=lambda _m: None)

    assert selected == [documents[0], documents[2]]


def test_select_videos_retries_on_invalid_input():
    documents = [{"video": {"id": "v1", "title": "A"}}]
    inputs = iter(["not-a-number", "1"])
    messages = []

    selected = select_videos(documents, input_fn=lambda _p: next(inputs), print_fn=messages.append)

    assert selected == [documents[0]]
    assert any("inválida" in m for m in messages)


def test_run_generates_reports_for_all_selected_videos(tmp_path):
    output_dir = tmp_path / "output"
    por_video = output_dir / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _write_document(por_video, "vid2", "Video 2")

    client = ScriptedClient(_always_ok_responder)
    reports_dir = tmp_path / "reports"

    run(client, output_dir, reports_dir, input_fn=lambda _p: "todos", print_fn=lambda _m: None)

    assert (reports_dir / "vid1.md").exists()
    assert (reports_dir / "vid2.md").exists()
    assert "Resumo de desempenho" in (reports_dir / "vid1.md").read_text(encoding="utf-8")


def test_run_continues_when_one_video_fails(tmp_path):
    output_dir = tmp_path / "output"
    por_video = output_dir / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _write_document(por_video, "vid2", "Video 2")

    def responder(kwargs):
        if "vid1" in kwargs["messages"][0]["content"]:
            raise RuntimeError("rate limited")
        return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])

    client = ScriptedClient(responder)
    reports_dir = tmp_path / "reports"
    messages = []

    run(client, output_dir, reports_dir, input_fn=lambda _p: "todos", print_fn=messages.append)

    assert not (reports_dir / "vid1.md").exists()
    assert (reports_dir / "vid2.md").exists()
    assert any("erro" in m.lower() and "vid1" in m for m in messages)


def test_run_prints_summary_even_when_all_videos_fail(tmp_path):
    output_dir = tmp_path / "output"
    por_video = output_dir / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _write_document(por_video, "vid2", "Video 2")

    def always_fails(_kwargs):
        raise RuntimeError("no api key")

    client = ScriptedClient(always_fails)
    reports_dir = tmp_path / "reports"
    messages = []

    run(client, output_dir, reports_dir, input_fn=lambda _p: "todos", print_fn=messages.append)

    assert not (reports_dir / "vid1.md").exists()
    assert not (reports_dir / "vid2.md").exists()
    summary = [m for m in messages if "Concluído" in m]
    assert summary and "0 relatório(s) gerado(s)" in summary[0] and "2 com erro" in summary[0]


def test_run_handles_no_documents_found(tmp_path):
    output_dir = tmp_path / "output"
    reports_dir = tmp_path / "reports"
    messages = []

    run(
        ScriptedClient(_always_ok_responder),
        output_dir,
        reports_dir,
        input_fn=lambda _p: pytest.fail("should not prompt when there are no videos"),
        print_fn=messages.append,
    )

    assert any("Nenhum vídeo" in m for m in messages)
    assert not reports_dir.exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_analyze.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analyze'`

- [ ] **Step 4: Write minimal implementation**

```python
# analyze.py
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.ai_report import generate_report
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

    processed = 0
    failed_ids = []
    for document in selected:
        video = document.get("video", {})
        video_id = video.get("id", "desconhecido")
        print_fn(f"Analisando '{video.get('title', video_id)}' ({video_id})...")
        try:
            report_text = generate_report(client, document, channel_averages)
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / f"{video_id}.md").write_text(report_text, encoding="utf-8")
            processed += 1
        except Exception as exc:
            print_fn(f"  erro ao analisar {video_id}, pulando: {exc}")
            failed_ids.append(video_id)

    print_fn(f"Concluído: {processed} relatório(s) gerado(s), {len(failed_ids)} com erro.")
    if failed_ids:
        print_fn(f"Vídeos com erro: {', '.join(failed_ids)}")


def main():
    load_dotenv()
    client = anthropic.Anthropic()
    run(client, Path("output"), Path("reports"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_analyze.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every module PASS.

- [ ] **Step 7: Commit**

```bash
git add analyze.py .gitignore tests/test_analyze.py
git commit -m "feat: wire CLI orchestration for AI performance reports"
```

---

### Task 4: README updates

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: user-facing setup and usage guide for the new script. Nothing depends on this.

- [ ] **Step 1: Append a new section to `README.md`**

Add this section after the existing "## 5. Rodando os testes" section (keep that section as-is, add the new one after it):

```markdown

## 6. Gerar relatórios de performance com IA

Depois de extrair os dados com `python main.py`, você pode gerar relatórios
de performance escritos por IA (Claude) para os vídeos já extraídos.

### Configurar a chave da Anthropic

1. Crie uma chave em https://console.anthropic.com/ (seção "API Keys").
2. Crie um arquivo `.env` na raiz do projeto (se ainda não existir) com:
   ```
   ANTHROPIC_API_KEY=sua-chave-aqui
   ```
   `.env` já está no `.gitignore` — nunca é commitado.

### Rodar o script

```bash
python analyze.py
```

O script lista os vídeos já extraídos (em `output/por_video/`), você escolhe
um, vários (`1,4,7`) ou `todos`, e para cada um gera um relatório em Markdown
comparando o desempenho do vídeo com a média do canal, com recomendações.

Os relatórios ficam em `reports/<video_id>.md`.

**Custo**: cada vídeo analisado é uma chamada paga à API da Anthropic
(modelo Claude Opus). Rodar `todos` em um canal com muitos vídeos já
extraídos gera um custo proporcional ao número de vídeos.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document AI performance report setup and usage"
```
