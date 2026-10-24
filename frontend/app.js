"use strict";
// All untrusted text (documents, summaries, explanations) is inserted with textContent only,
// never innerHTML: a malicious document can make the model emit markup.

const $ = (id) => document.getElementById(id);
let config = null;
let lastResults = null;

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c);
  return node;
}

async function api(path, options) {
  const response = await fetch(path, options);
  let body = null;
  try { body = await response.json(); } catch { /* non-JSON (csv) */ }
  if (!response.ok) {
    const err = new Error(describeError(body, response.status));
    err.status = response.status; err.body = body;
    throw err;
  }
  return body;
}

function describeError(body, status) {
  const d = body && (body.detail || body);
  if (Array.isArray(d)) return d.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("\n");
  if (d && typeof d === "object") return [d.error, d.message].filter(Boolean).join(": ") || `HTTP ${status}`;
  return d ? String(d) : `HTTP ${status}`;
}

function showError(message) {
  const box = $("error");
  box.textContent = message || "";
  box.classList.toggle("hidden", !message);
}

// ---------- setup ----------
async function init() {
  config = await api("/config");
  for (const name of Object.keys(config.presets)) $("preset").append(el("option", { value: name, text: name }));
  fillSelect($("p-heuristic"), config.policies.heuristic, (v) => `policy: ${v}`);
  fillSelect($("p-classifier"), config.policies.classifier, (v) => `policy: ${v}`);
  fillSelect($("p-variant"), config.structural_variants, (v) => `prompt wording ${v}`);
  $("preset").value = config.default_defense_preset;
  applyPreset(config.default_defense_preset);

  const real = config.real_model;
  $("real-option").textContent = real ? `Real model: ${real.name} (${real.is_local ? "local" : "remote provider"})` : "Real model (not configured)";
  $("real-option").disabled = !real;
  if (config.default_model_mode === "real" && real) $("model").value = "real";
  $("clf-state").textContent = config.classifier_available ? "" : "(unavailable: no classifier configured)";
  $("d-classifier").disabled = !config.classifier_available;
  updateModelNote();

  const exps = $("ev-exps");
  for (const name of Object.keys(config.presets)) {
    const box = el("input", { type: "checkbox", value: name });
    box.checked = ["E0", "E1", "E2", "E4"].includes(name);
    exps.append(el("label", { class: "check" }, box, ` ${name}`));
  }
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => switchTab(tab.dataset.tab)));
  $("doc").addEventListener("input", updateCount);
  $("file").addEventListener("change", onFile);
  $("model").addEventListener("change", updateModelNote);
  $("preset").addEventListener("change", () => applyPreset($("preset").value));
  $("form").addEventListener("submit", onSubmit);
  $("ev-run").addEventListener("click", runEvaluation);
  $("runs-refresh").addEventListener("click", loadRuns);
  updateCount();
}

function fillSelect(select, values, label) {
  for (const v of values) select.append(el("option", { value: v, text: label(v) }));
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $("tab-summarize").classList.toggle("hidden", name !== "summarize");
  $("tab-results").classList.toggle("hidden", name !== "results");
  if (name === "results") loadRuns();
}

function applyPreset(name) {
  const p = config.presets[name];
  $("d-heuristic").checked = p.heuristic; $("p-heuristic").value = p.heuristic_policy;
  $("d-classifier").checked = p.classifier && config.classifier_available; $("p-classifier").value = p.classifier_policy;
  $("d-structural").checked = p.structural; $("p-variant").value = p.structural_variant;
  $("d-output").checked = p.output_validation; $("d-failclosed").checked = p.fail_closed_on_detector_error;
}

function currentDefenses() {
  return {
    name: "ui",
    heuristic: $("d-heuristic").checked, heuristic_policy: $("p-heuristic").value,
    classifier: $("d-classifier").checked, classifier_policy: $("p-classifier").value,
    structural: $("d-structural").checked, structural_variant: $("p-variant").value,
    output_validation: $("d-output").checked,
    fail_closed_on_detector_error: $("d-failclosed").checked,
  };
}

function updateCount() {
  const n = $("doc").value.length, max = config ? config.limits.max_document_chars : 50000;
  $("doc-count").textContent = `${n.toLocaleString()} / ${max.toLocaleString()} characters`;
}

function updateModelNote() {
  const note = $("model-note"), real = config && config.real_model;
  if ($("model").value === "mock") {
    note.textContent = "Mock mode makes no model calls. Its output demonstrates the application flow only and says nothing about real LLM behavior.";
  } else if (real && real.is_local) {
    note.textContent = "Your text will be sent to the local model server configured for this app.";
  } else {
    note.textContent = "Privacy notice: your document text will be sent to the external model provider configured for this app.";
  }
}

// ---------- file upload ----------
async function onFile() {
  const file = $("file").files[0];
  if (!file) return;
  const note = $("extract-note");
  showError("");
  try {
    const form = new FormData();
    form.append("file", file);
    const result = await api("/extract", { method: "POST", body: form });
    $("doc").value = result.text;
    updateCount();
    note.textContent = `Extracted ${result.chars.toLocaleString()} characters from the ${result.format.toUpperCase()} file. The text above is exactly what will be sent. ${(result.warnings || []).join(" ")}`;
    note.classList.remove("hidden");
  } catch (err) {
    note.classList.add("hidden");
    showError(err.message);
  }
}

// ---------- summarize ----------
async function summarize(defenses) {
  return api("/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_text: $("doc").value,
      instruction: $("instruction").value,
      model: $("model").value,
      defenses,
    }),
  });
}

async function onSubmit(event) {
  event.preventDefault();
  showError("");
  const button = $("submit");
  button.disabled = true; button.textContent = "Working…";
  $("results").replaceChildren();
  try {
    const defended = await summarize(currentDefenses());
    const results = [{ title: "Defended configuration", data: defended }];
    if ($("compare").checked) {
      const baseline = await summarize({ name: "E0" });
      results.unshift({ title: "Undefended baseline (E0)", data: baseline });
    }
    lastResults = results;
    renderResults(results);
  } catch (err) {
    showError(err.message);
  } finally {
    button.disabled = false; button.textContent = "Summarize";
  }
}

function badge(text, cls) { return el("span", { class: `badge ${cls}`, text }); }

function renderResults(results) {
  const root = $("results");
  root.replaceChildren();
  const cols = el("div", { class: "cols" });
  for (const r of results) cols.append(renderResult(r.title, r.data));
  root.append(cols);
  const exportBtn = el("button", { type: "button", class: "secondary", text: "Download result JSON" });
  exportBtn.addEventListener("click", () => download("result.json", JSON.stringify(lastResults, null, 2), "application/json"));
  root.append(exportBtn);
}

function renderResult(title, d) {
  const card = el("div", { class: "result" });
  card.append(el("h3", { text: title }));
  const badges = el("div", { class: "badges" });
  badges.append(badge(d.enforcement_decision.toUpperCase(), d.enforcement_decision));
  badges.append(d.model.is_mock ? badge("MOCK MODEL", "mock") : badge(`REAL: ${d.model.name}`, "real"));
  badges.append(badge(d.reached_model ? "reached model" : "blocked before model", d.reached_model ? "real" : "block"));
  card.append(badges);
  for (const w of d.warnings || []) card.append(el("div", { class: "note", text: w }));

  card.append(el("h3", { text: "Summary" }));
  card.append(el("pre", { class: "summary", text: d.summary === null ? `(no summary delivered; blocked by ${d.blocked_by})` : d.summary }));

  if (d.detections.length) {
    card.append(el("h3", { text: "Detection layers" }));
    const table = el("table");
    table.append(rowOf(["layer", "status", "flagged", "score", "policy action", "explanation"], "th"));
    for (const det of d.detections) {
      const tr = rowOf([det.layer, det.status, String(det.flagged), det.score ?? "-", det.policy_action, det.explanation], "td");
      tr.lastChild.className = "wrap";
      table.append(tr);
    }
    card.append(table);
    const rules = d.detections.flatMap((x) => x.matched_rules.map((m) => `${m.rule_id} (weight ${m.weight}, ${m.spans.length}×): ${m.description}`));
    if (rules.length) card.append(el("div", { class: "muted", text: "Matched rules: " + rules.join(" | ") }));
  }
  if (d.output_validation) card.append(el("div", { class: "muted", text: `Output validation: ${d.output_validation.outcome}. ${d.output_validation.explanation}` }));

  const kv = el("dl", { class: "kv" });
  const add = (k, v) => { kv.append(el("dt", { text: k }), el("dd", { text: String(v) })); };
  add("request id", d.request_id);
  add("model", `${d.model.provider} / ${d.model.name}`);
  add("model calls", d.model_calls);
  add("latency", `${d.latency_ms} ms`);
  add("layers run", d.layers_run.join(", ") || "none (baseline)");
  add("stage timings", Object.entries(d.timings_ms).map(([k, v]) => `${k} ${v} ms`).join(", ") || "-");
  add("defenses", d.defenses.name + ": " + (d.defenses.structural ? `structural ${d.defenses.structural_variant}, ` : "") + (["heuristic", "classifier", "output_validation"].filter((x) => d.defenses[x]).join(", ") || "no detectors"));
  card.append(kv);
  return card;
}

function rowOf(cells, tag) {
  const tr = el("tr");
  for (const c of cells) tr.append(el(tag, { text: String(c) }));
  return tr;
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el("a", { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------- evaluation results ----------
async function loadRuns() {
  const root = $("runs");
  root.replaceChildren();
  try {
    const { runs } = await api("/results");
    if (!runs.length) { root.append(el("p", { class: "muted", text: "No saved runs yet. Run an evaluation above or use scripts/run_experiments.py." })); return; }
    const table = el("table");
    table.append(rowOf(["run", "started", "model", "evidence status", "experiments", ""], "th"));
    for (const r of runs) {
      const open = el("button", { type: "button", class: "secondary", text: "Open" });
      open.addEventListener("click", () => loadRun(r.run_id));
      const tr = rowOf([r.run_id, r.started_at || "-", `${r.model}${r.model_is_mock ? " (mock)" : ""}`, r.evidence_status, r.experiments.join(", ")], "td");
      const td = el("td"); td.append(open); tr.append(td);
      table.append(tr);
    }
    root.append(table);
  } catch (err) { root.append(el("div", { class: "error", text: err.message })); }
}

async function loadRun(runId) {
  const root = $("run-detail");
  root.replaceChildren();
  try {
    const d = await api(`/results/${runId}`);
    const card = el("div", { class: "card" });
    card.append(el("h2", { text: `Run ${runId}` }));
    card.append(el("div", { class: "note", text: d.metadata.evidence_status }));
    const m = d.metadata;
    card.append(el("div", { class: "muted", text: `model ${m.model.name}; dataset ${m.case_set || "?"} (${m.dataset.n_cases} cases); repetitions ${m.repetitions}; ${d.pending_manual_review} outcome(s) awaiting manual review` }));
    const keys = d.summary.length ? Object.keys(d.summary[0]) : [];
    const table = el("table");
    table.append(rowOf(keys, "th"));
    for (const row of d.summary) table.append(rowOf(keys.map((k) => row[k] ?? "-"), "td"));
    card.append(table);
    for (const [name, o] of Object.entries(m.unavailable_experiments || {})) card.append(el("div", { class: "note", text: `${name}: NOT RUN. ${o}` }));
    card.append(el("a", { href: `/results/${runId}/table.csv`, text: "Download summary CSV" }), document.createTextNode(" · "),
      el("a", { href: `/results/${runId}/outcomes.csv`, text: "Download per-case outcomes CSV" }));
    root.append(card);
  } catch (err) { root.append(el("div", { class: "error", text: err.message })); }
}

async function runEvaluation() {
  const status = $("ev-status"), button = $("ev-run");
  const experiments = [...$("ev-exps").querySelectorAll("input:checked")].map((i) => i.value);
  const payload = { case_set: $("ev-set").value, model: $("ev-model").value, repetitions: Number($("ev-reps").value), experiments };
  status.classList.remove("hidden");
  if (!experiments.length) { status.textContent = "Select at least one experiment."; return; }
  if (payload.case_set === "final" || payload.case_set === "independent") {
    if (!confirm("This case set uses frozen test files. Running it spends them for tuning purposes. Continue?")) return;
    payload.final_run_acknowledged = true;
  }
  button.disabled = true;
  try {
    let job;
    try {
      job = await api("/evaluate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    } catch (err) {
      if (err.status === 409 && err.body && err.body.detail && err.body.detail.error === "confirmation_required") {
        const n = err.body.detail.estimated_model_calls;
        if (!confirm(`This will make up to ${n} calls to the configured real model. Continue?`)) { status.textContent = "Cancelled."; return; }
        job = await api("/evaluate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...payload, confirm_external_calls: true }) });
      } else throw err;
    }
    while (job.status === "running" || job.status === "queued") {
      status.textContent = `Running… ${job.done}/${job.total}`;
      await new Promise((r) => setTimeout(r, 700));
      job = await api(`/evaluate/${job.job_id}`);
    }
    status.textContent = job.status === "completed" ? `Finished run ${job.run_id}.` : `Failed: ${job.error}`;
    await loadRuns();
    if (job.run_id) await loadRun(job.run_id);
  } catch (err) { status.textContent = err.message; }
  finally { button.disabled = false; }
}

init().catch((err) => showError(`Could not load configuration: ${err.message}`));
