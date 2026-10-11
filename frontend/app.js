const API_BASE = (new URLSearchParams(window.location.search).get("api") || "http://localhost:8000").replace(/\/+$/, "");
const PREDICTION_TIMEOUT_MS = 90_000;
const $ = (selector) => document.querySelector(selector);
const portal = $("#portal");
const projectEntry = $("#project-entry");
const postResultView = $("#post-result-view");
const readingScreen = $("#reading-screen");
const tabButtons = [...document.querySelectorAll("[data-tab]")];
const panels = [...document.querySelectorAll("[data-panel]")];
const modeButtons = [...document.querySelectorAll("[data-mode]")];
const formModes = [...document.querySelectorAll("[data-form-mode]")];
const loadedSections = { wins: false, proof: false };

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function asPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : "n/a";
}

function safeURL(value) {
  try {
    const url = new URL(String(value));
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch {
    return "";
  }
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("The Oracle took too long to respond. Please try again.");
    }
    throw new Error(`Could not reach ${API_BASE}. Check that the Oracle backend is running.`);
  }

  const contentType = response.headers.get("content-type") || "";
  let body;
  if (contentType.includes("application/json")) {
    body = await response.json();
  } else {
    body = await response.text();
  }
  if (!response.ok) {
    const detail = typeof body === "object" && body !== null ? body.detail : body;
    throw new Error(detail || `The Oracle returned HTTP ${response.status}.`);
  }
  if (typeof body !== "object" || body === null) {
    throw new Error("The Oracle returned an unexpected response.");
  }
  return body;
}

function setExpanded(expanded = true) {
  portal.classList.toggle("is-expanded", expanded);
}

function setReading(reading) {
  portal.classList.toggle("is-reading", reading);
}

function selectTab(name, options = {}) {
  const { focus = false } = options;
  tabButtons.forEach((button) => {
    const selected = button.dataset.tab === name;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    if (selected && focus) button.focus();
  });
  panels.forEach((panel) => {
    const selected = panel.dataset.panel === name;
    panel.hidden = !selected;
    panel.classList.toggle("is-active", selected);
  });
  setExpanded(true);
  if (name === "wins") loadInsights();
  if (name === "proof") loadMetrics();
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => selectTab(button.dataset.tab));
  button.addEventListener("keydown", (event) => {
    const currentIndex = tabButtons.indexOf(button);
    let nextIndex;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabButtons.length;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabButtons.length) % tabButtons.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabButtons.length - 1;
    if (nextIndex !== undefined) {
      event.preventDefault();
      selectTab(tabButtons[nextIndex].dataset.tab, { focus: true });
    }
  });
});

function selectMode(name) {
  modeButtons.forEach((button) => {
    const selected = button.dataset.mode === name;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  formModes.forEach((pane) => {
    const selected = pane.dataset.formMode === name;
    pane.classList.toggle("is-hidden", !selected);
    pane.setAttribute("aria-hidden", String(!selected));
  });
  if (!postResultView.hidden) return;
  setExpanded(name === "manual");
}

modeButtons.forEach((button) => {
  button.addEventListener("click", () => selectMode(button.dataset.mode));
});

function setButtonBusy(button, busy, busyLabel, idleLabel) {
  button.disabled = busy;
  button.querySelector("span:first-child").textContent = busy ? busyLabel : idleLabel;
}

function setStatus(element, message, isError = false) {
  element.innerHTML = message
    ? `<div class="reading-status${isError ? " is-error" : ""}" role="${isError ? "alert" : "status"}">${escapeHTML(message)}</div>`
    : "";
}

function renderPrediction(result) {
  const probability = Math.max(0, Math.min(1, Number(result.win_prob) || 0));
  const reasons = Array.isArray(result.top_reasons) ? result.top_reasons : [];
  const similar = Array.isArray(result.similar_winners) ? result.similar_winners : [];
  const reasonMarkup = reasons.length
    ? reasons.map((item) => {
      const effect = item.effect === "helps" ? "helps" : "hurts";
      return `<li><span>${escapeHTML(item.factor)}</span><span class="reason-effect ${effect}">${effect}</span></li>`;
    }).join("")
    : `<li><span>No individual signals were returned for this project.</span></li>`;
  const similarMarkup = similar.length
    ? similar.map((item) => {
      const url = safeURL(item.url);
      const title = escapeHTML(item.title || "Past winner");
      const titleMarkup = url
        ? `<a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : title;
      return `<li><span class="similar-main">${titleMarkup}<span class="similar-detail">${escapeHTML(item.hackathon)}${item.prizes ? ` · ${escapeHTML(String(item.prizes).split("|").join(", "))}` : ""}</span></span><span class="similarity">${asPercent(item.similarity)} match</span></li>`;
    }).join("")
    : `<li><span>No close past winners found.</span></li>`;

  $("#prediction-output").innerHTML = `
    <article class="prediction-result">
      <div class="prediction-topline">
        <div class="prediction-title"><span class="section-index">THE ORACLE HAS SPOKEN</span><h3>${escapeHTML(result.title || "Your project")}</h3></div>
        <div class="probability">${asPercent(probability)}<span> chance</span></div>
      </div>
      <div class="probability-track" role="img" aria-label="${asPercent(probability)} chance of winning"><span style="width:${probability * 100}%"></span></div>
      <div class="prediction-meta"><span>Chance of winning at least one prize</span><span class="track-chip">Best shot: ${escapeHTML(result.best_track || "Not available")}</span></div>
      <div class="result-grid">
        <section class="result-card"><h3>Signals in your favor</h3><ul class="reasons-list">${reasonMarkup}</ul></section>
        <section class="result-card"><h3>Similar past winners</h3><ul class="similar-list">${similarMarkup}</ul></section>
      </div>
    </article>`;
}

/* Gemini judge: optional rubric feedback, loads after the prediction and never blocks it. */
async function runJudge(payload) {
  const article = $("#prediction-output .prediction-result");
  if (!article) return;
  const box = document.createElement("section");
  box.className = "result-card judge-card";
  box.innerHTML = `<h3>Gemini judge</h3><p class="loading-note">Gemini is reading the write-up…</p>`;
  article.appendChild(box);
  let judged;
  try {
    judged = await api("/judge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    judged = { available: false, reason: error.message };
  }
  if (!judged || !judged.available) {
    box.innerHTML = `<h3>Gemini judge</h3><p class="field-note">Off: ${escapeHTML((judged && judged.reason) || "unavailable")}</p>`;
    return;
  }
  const scores = (judged.scores || []).map((item) =>
    `<li><span>${escapeHTML(item.criterion)}</span><span class="similarity">${escapeHTML(item.score)}/10</span></li>`).join("");
  const list = (items) => (items || []).map((item) => `<li><span>${escapeHTML(item)}</span></li>`).join("");
  box.innerHTML = `
    <span class="section-index">RUBRIC FEEDBACK · ${escapeHTML(judged.model)} · NOT PART OF THE WIN %</span>
    <h3>Gemini judge: ${escapeHTML(judged.overall ?? "n/a")} / 10</h3>
    <p class="field-note">${escapeHTML(judged.verdict)}</p>
    <div class="result-grid">
      <section class="result-card"><h3>Rubric</h3><ul class="reasons-list">${scores}</ul></section>
      <section class="result-card"><h3>Strengths</h3><ul class="reasons-list">${list(judged.strengths)}</ul><h3>Fix before judging</h3><ul class="reasons-list">${list(judged.fixes)}</ul></section>
    </div>`;
}

const wait = (duration) => new Promise((resolve) => window.setTimeout(resolve, duration));

async function finishReading(result, error) {
  readingScreen.classList.add("is-dissipating");
  await wait(850);
  readingScreen.hidden = true;
  readingScreen.classList.remove("is-dissipating");
  setReading(false);

  if (error) {
    projectEntry.hidden = false;
    postResultView.hidden = true;
    portal.classList.add("is-entry");
    setExpanded($(".mode-button[data-mode='manual']").classList.contains("is-active"));
    $("#prediction-error").textContent = error.message;
    return;
  }

  renderPrediction(result);
  projectEntry.hidden = true;
  postResultView.hidden = false;
  portal.classList.remove("is-entry");
  setExpanded(true);
  selectTab("results");
}

$("#prediction-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorOutput = $("#prediction-error");
  const button = $("#predict-button");
  const isDevpost = !$(".mode-button[data-mode='manual']").classList.contains("is-active");
  const payload = isDevpost
    ? { url: $("#devpost-url").value.trim() }
    : {
      title: $("#project-title").value.trim(),
      tagline: $("#project-tagline").value.trim(),
      description: $("#project-description").value.trim(),
      built_with: $("#project-tech").value.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean).join("|"),
      team_size: Number.parseInt($("#team-size").value, 10) || 1,
      has_video: $("#has-video").checked ? 1 : 0,
      has_github: $("#has-github").checked ? 1 : 0,
      n_sections: $("#project-description").value.trim()
        ? ($("#project-description").value.match(/\n\s*\n/g) || []).length + 1
        : 0,
    };

    errorOutput.textContent = "";
    if (!payload.url && !payload.title) {
    errorOutput.textContent = isDevpost ? "Add a Devpost project link to continue." : "Give your project at least a title.";
    (isDevpost ? $("#devpost-url") : $("#project-title")).focus();
    return;
  }

  projectEntry.hidden = true;
  postResultView.hidden = true;
  portal.classList.add("is-entry");
  readingScreen.hidden = false;
  readingScreen.classList.remove("is-dissipating");
  setExpanded(false);
  setReading(true);
  setButtonBusy(button, true, "READING THE PROJECT…", "REVEAL MY ODDS");
  const minimumReading = wait(2400);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), PREDICTION_TIMEOUT_MS);
  try {
    const [result] = await Promise.all([
      api("/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      }),
      minimumReading,
    ]);
    await finishReading(result);
    runJudge(payload);
  } catch (error) {
    await minimumReading;
    await finishReading(null, error);
  } finally {
    window.clearTimeout(timeoutId);
    setButtonBusy(button, false, "READING THE PROJECT…", "REVEAL MY ODDS");
  }
});

$("#edit-project").addEventListener("click", () => {
  postResultView.hidden = true;
  projectEntry.hidden = false;
  portal.classList.add("is-entry");
  setExpanded(false);
  selectMode($("#devpost-url").value.trim() ? "devpost" : "manual");
  const field = $("#devpost-url").value.trim() ? $("#devpost-url") : $("#project-title");
  field.focus();
});

$("#leaderboard-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const gallery = $("#gallery-url").value.trim();
  const output = $("#leaderboard-output");
  const status = $("#leaderboard-status");
  const button = $("#leaderboard-button");
  output.innerHTML = "";
  status.innerHTML = "";
  if (!gallery) {
    setStatus(status, "Enter a public Devpost gallery URL first.", true);
    $("#gallery-url").focus();
    return;
  }

  setExpanded(true);
  setReading(true);
  setButtonBusy(button, true, "SCORING PROJECTS…", "RANK THE GALLERY");
  setStatus(status, "Collecting and scoring projects. The first gallery run may take a couple of minutes.");
  try {
    const result = await api(`/leaderboard?gallery=${encodeURIComponent(gallery)}`);
    if (!Array.isArray(result.projects)) throw new Error("The leaderboard response did not contain a project list.");
    renderLeaderboard(result.projects, output);
    setStatus(status, `${result.projects.length.toLocaleString()} projects ranked from this gallery.`);
  } catch (error) {
    setStatus(status, error.message, true);
  } finally {
    setReading(false);
    setButtonBusy(button, false, "SCORING PROJECTS…", "RANK THE GALLERY");
  }
});

function renderLeaderboard(projects, output) {
  if (projects.length === 0) {
    output.innerHTML = `<div class="reading-status">No projects were returned for this gallery.</div>`;
    return;
  }
  const max = Math.max(...projects.map((project) => Number(project.win_prob) || 0), 0);
  const rows = projects.map((project, index) => {
    const probability = Math.max(0, Math.min(1, Number(project.win_prob) || 0));
    const title = escapeHTML(project.title || "Untitled project");
    const url = safeURL(project.url);
    const link = url ? `<a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">${title}</a>` : title;
    const bar = max > 0 ? (probability / max) * 100 : 0;
    return `<tr><td>${escapeHTML(project.rank ?? index + 1)}</td><td class="leaderboard-project">${link}</td><td class="leaderboard-prob">${asPercent(probability)}</td><td class="leaderboard-bar"><div class="mini-track"><span style="width:${bar}%"></span></div></td><td class="leaderboard-track">${escapeHTML(project.best_track || "—")}</td></tr>`;
  }).join("");
  output.innerHTML = `<div class="leaderboard-table-wrap"><table class="data-table"><thead><tr><th>#</th><th>Project</th><th>Win chance</th><th aria-label="Relative win chance"></th><th>Best track</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function chartCard(title, data, labels = {}) {
  const entries = Object.entries(data || {}).filter(([, value]) => Number.isFinite(Number(value)));
  const maximum = Math.max(...entries.map(([, value]) => Number(value)), 0);
  const bars = entries.map(([key, value]) => {
    const numericValue = Number(value);
    const width = maximum > 0 ? Math.max(0, Math.min(100, (numericValue / maximum) * 100)) : 0;
    return `<div class="chart-row"><span class="chart-label">${escapeHTML(labels[key] || key)}</span><div class="chart-track"><span style="width:${width}%"></span></div><span class="chart-value">${asPercent(numericValue)}</span></div>`;
  }).join("");
  return `<section class="insight-card"><h3>${escapeHTML(title)}</h3>${bars || `<p class="field-note">No figures available.</p>`}</section>`;
}

async function loadInsights() {
  if (loadedSections.wins) return;
  loadedSections.wins = true;
  const output = $("#insights-output");
  output.innerHTML = `<p class="loading-note">Gathering the signals…</p>`;
  try {
    const data = await api("/insights");
    const charts = [
      chartCard("Write-up length", data.writeup_length),
      chartCard("Team size", data.team_size, { "1": "Solo", "2": "2 people", "3": "3 people", "4": "4 people" }),
      chartCard("Technologies listed", data.n_tech),
      chartCard("Demo video", data.video, { with: "Has video", without: "No video" }),
      chartCard("AI / machine learning", data.ai, { uses_ai: "Uses AI", no_ai: "No AI" }),
      chartCard("Hardware", data.hardware, { uses_hardware: "Uses hardware", no_hardware: "Software only" }),
      chartCard("GitHub link", data.github, { with: "Has GitHub", without: "No GitHub" }),
    ].filter(Boolean).join("");
    output.innerHTML = `
      <div class="stats-strip">
        <div class="stat-item"><div class="stat-number">${Number(data.n_projects || 0).toLocaleString()}</div><div class="stat-label">PROJECTS ANALYZED</div></div>
        <div class="stat-item"><div class="stat-number">${escapeHTML(data.n_hackathons ?? "—")}</div><div class="stat-label">HACKATHONS</div></div>
        <div class="stat-item"><div class="stat-number">${asPercent(data.overall_win_rate)}</div><div class="stat-label">WIN AT LEAST ONE PRIZE</div></div>
      </div>
      <div class="insights-grid">${charts}</div>
      <p class="accuracy-note">Historical win rates show association, not a guarantee of future results.</p>`;
  } catch (error) {
    loadedSections.wins = false;
    output.innerHTML = `<p class="error-message" role="alert">Couldn’t load the project insights: ${escapeHTML(error.message)} <button class="edit-button" type="button" data-retry="wins">TRY AGAIN</button></p>`;
  }
}

async function loadMetrics() {
  if (loadedSections.proof) return;
  loadedSections.proof = true;
  const output = $("#metrics-output");
  output.innerHTML = `<p class="loading-note">Reading the record…</p>`;
  try {
    const metrics = await api("/metrics");
    const model = metrics.cross_validation?.[metrics.chosen_model];
    if (!model) throw new Error("Validation metrics for the selected model are missing.");
    const backtest = metrics.backtest;
    const topRows = Array.isArray(backtest?.top_10) ? backtest.top_10 : [];
    const rows = topRows.map((item, index) => {
      const won = Boolean(item.actually_won);
      return `<tr><td>${index + 1}</td><td>${escapeHTML(item.title || "Untitled project")}</td><td>${asPercent(item.prob)}</td><td class="${won ? "won" : "lost"}">${won ? `Yes${item.prizes ? ` · ${escapeHTML(String(item.prizes).split("|").join(", "))}` : ""}` : "No"}</td></tr>`;
    }).join("");
    output.innerHTML = `
      <div class="metrics-strip">
        <div class="metric-card"><div class="stat-number">${asPercent(model.precision_at_k)}</div><div class="metric-caption">of top picks won a prize, compared with ${asPercent(model.base_rate)} across the field.</div></div>
        <div class="metric-card"><div class="stat-number">${Number.isFinite(Number(model.mean_auc_per_hackathon)) ? Number(model.mean_auc_per_hackathon).toFixed(2) : "n/a"}</div><div class="metric-caption">average ranking score across unseen hackathons. 0.5 is a coin flip; 1.0 is perfect ranking.</div></div>
      </div>
      ${backtest ? `<section class="backtest-card"><h3>Backtest: ${escapeHTML(backtest.hackathon || "Hackathon")}</h3><p>Trained without this event, then tested on ${escapeHTML(backtest.n_projects)} projects. ${escapeHTML(backtest.winners_in_our_top_k)} of ${escapeHTML(backtest.n_winners)} winners appeared in the top ${escapeHTML(backtest.n_winners)} predictions; random selection would find about ${Math.round((Number(backtest.n_winners) || 0) ** 2 / (Number(backtest.n_projects) || 1))}. Best Overall ranked #${escapeHTML(backtest.best_overall_rank)}.</p><div class="backtest-table-wrap"><table class="data-table"><thead><tr><th>#</th><th>Project</th><th>Predicted</th><th>Actually won?</th></tr></thead><tbody>${rows}</tbody></table></div></section>` : ""}
      <p class="accuracy-note">These results describe historical validation. Predictions are estimates, not promises, and should not replace the judges’ criteria.</p>`;
  } catch (error) {
    loadedSections.proof = false;
    output.innerHTML = `<p class="error-message" role="alert">Couldn’t load the validation metrics: ${escapeHTML(error.message)} <button class="edit-button" type="button" data-retry="proof">TRY AGAIN</button></p>`;
  }
}

document.addEventListener("click", (event) => {
  const retryButton = event.target.closest("[data-retry]");
  if (!retryButton) return;
  if (retryButton.dataset.retry === "wins") loadInsights();
  if (retryButton.dataset.retry === "proof") loadMetrics();
});
