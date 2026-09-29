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
