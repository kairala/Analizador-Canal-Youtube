const state = {
  extractVideos: [],
  analyzableVideos: [],
};

function $(id) {
  return document.getElementById(id);
}

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_e) {
    // resposta não era JSON (ex.: erro 500 sem handler, HTML de proxy, etc.)
  }
  if (!response.ok) {
    throw new Error((data && data.detail) || text || `HTTP ${response.status}`);
  }
  return data;
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
  try {
    const status = await fetchJSON("/api/setup/status");
    if (!status.client_secret_configured || !status.anthropic_key_configured) {
      showTab("setup");
    } else {
      showTab("extract");
    }
    return status;
  } catch (error) {
    $("setup-error").textContent = error.message || "erro ao verificar configuração";
    showTab("setup");
    return null;
  }
}

async function submitSetup(event) {
  event.preventDefault();
  const payload = {
    client_secret_json: $("client-secret-input").value,
    anthropic_api_key: $("anthropic-key-input").value,
  };
  try {
    await fetchJSON("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    $("setup-error").textContent = error.message || "erro ao salvar configuração";
    return;
  }
  $("setup-error").textContent = "";
  await refreshSetupStatus();
}

async function loadVideos() {
  $("extract-error").textContent = "";
  $("extract-status").textContent =
    "Abrindo o navegador para autorizar acesso ao Google (isso pode levar alguns minutos)…";
  try {
    const data = await fetchJSON("/api/videos");
    state.extractVideos = data.videos;
    renderVideoCheckboxes("extract-video-list", data.videos, "extract-video");
    $("extract-status").textContent = "";
  } catch (error) {
    $("extract-error").textContent = error.message || "erro ao carregar vídeos";
    $("extract-status").textContent = "";
  }
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
    log.textContent += "\n[conexão perdida antes de concluir]\n";
    source.close();
  };
}

async function startExtract() {
  $("extract-error").textContent = "";
  const videoIds = selectedIds("extract-video");
  try {
    await fetchJSON("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_ids: videoIds }),
    });
  } catch (error) {
    $("extract-error").textContent = error.message || "erro ao iniciar extração";
    return;
  }
  streamJob("/api/extract/stream", "extract-log");
}

async function loadAnalyzable() {
  $("analyze-error").textContent = "";
  try {
    const data = await fetchJSON("/api/analyzable");
    state.analyzableVideos = data.videos;
    renderVideoCheckboxes("analyze-video-list", data.videos, "analyze-video");
    updateAnalyzeCallCount();
  } catch (error) {
    $("analyze-error").textContent = error.message || "erro ao carregar vídeos analisáveis";
  }
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
  try {
    await fetchJSON("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_ids: videoIds }),
    });
  } catch (error) {
    $("analyze-error").textContent = error.message || "erro ao iniciar análise";
    return;
  }
  streamJob("/api/analyze/stream", "analyze-log");
}

async function loadResults() {
  $("browse-error").textContent = "";
  try {
    const data = await fetchJSON("/api/results");
    const container = $("results-list");
    container.innerHTML = "";
    data.results.forEach((result) => {
      const item = document.createElement("button");
      item.className = "result-item";
      item.textContent = `${result.video_id} ${result.has_extraction ? "[dados]" : ""} ${result.has_report ? "[relatório]" : ""}`;
      item.onclick = () => showResult(result.video_id);
      container.appendChild(item);
    });
  } catch (error) {
    $("browse-error").textContent = error.message || "erro ao carregar resultados";
  }
}

async function showResult(videoId) {
  $("browse-error").textContent = "";
  try {
    const data = await fetchJSON(`/api/results/${videoId}`);
    $("result-json").textContent = data.extraction
      ? JSON.stringify(data.extraction, null, 2)
      : "(sem dados extraídos)";
    $("result-report").textContent = data.report || "(sem relatório gerado)";
  } catch (error) {
    $("browse-error").textContent = error.message || "erro ao carregar resultado";
  }
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
