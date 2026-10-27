"use strict";
// All untrusted text (documents, summaries, explanations) is inserted with textContent only,
// never innerHTML: a malicious document can make the model emit markup.

const $ = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";
let config = null;
let lastResults = null;
let examples = [];
let currentExample = null;
let findings = null;
let findingsModel = "1B";

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

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
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
  if (d && typeof d === "object") return d.message || d.error || `HTTP ${status}`;
  return d ? String(d) : `HTTP ${status}`;
}

function showError(message) {
  const box = $("error");
  box.textContent = message || "";
  box.classList.toggle("hidden", !message);
}

const pct = (k, n) => (n ? (100 * k) / n : null);
const fmtPct = (v) => (v === null ? "n/a" : `${v.toFixed(1)}%`);

// ---------- plain-language content ----------
const PRESET_TEXT = {
  E0: "No protection. The document goes straight to the AI. This is the baseline everything is compared with.",
  E1: "Word rules (L1) scan for attack phrases and block the document if they find any.",
  E1b: "Word rules (L1), but instead of blocking they cut out the suspicious lines and continue.",
  E2: "Safer instructions (L3): the AI is told the document is only data to summarize, never orders to follow.",
  E3: "AI checker (L2): an extra AI call first judges whether the document contains an attack.",
  E4: "Word rules (L1) + safer instructions (L3).",
  E5: "Everything: word rules (L1), AI checker (L2) and safer instructions (L3).",
};

const PIPELINE = [
  { id: "doc", title: "Document", sub: "untrusted input", layer: false,
    what: "The text you want summarized: pasted, picked from the examples, or extracted from a PDF/DOCX/TXT file.",
    why: "It may come from anyone, so the app treats it as untrusted. An attacker can hide an instruction anywhere in it." },
  { id: "L1", title: "L1 Word rules", sub: "heuristic detector", layer: true,
    what: "Looks for known attack phrases (such as \"ignore previous instructions\") using weighted rules. When the score reaches 1.0 the document is flagged, and the preset decides: block it, cut out the matching lines, or only warn.",
    good: "Fast, free, explainable: it shows exactly which rule matched.",
    bad: "Only catches wording it already knows. Rephrased or polite attacks slip past.",
    found: "Caught 0 of 150 externally written attacks in the independent test (they contain no override words). In the earlier tests it caught 72.7% of attack styles it was built for, but only 8.3% of unseen styles." },
  { id: "L2", title: "L2 AI checker", sub: "model classifier", layer: true,
    what: "A separate call to the AI model reads the document and answers: \"suspicious or not?\", with a confidence from 0 to 1.",
    good: "Can understand meaning, not just exact words.",
    bad: "Costs an extra model call and the checker itself can be fooled or can wrongly flag security articles.",
    found: "Flagged 8 of 146 attacked documents on the small 1B model and 0 of 146 on the 8B model." },
  { id: "L3", title: "L3 Safer instructions", sub: "structural separation", layer: true,
    what: "Wraps the document between unique markers and tells the AI: everything between the markers is data to summarize, and any instruction inside it must be ignored.",
    good: "Needs no extra call and helps even against attacks with no suspicious words.",
    bad: "The AI still reads one stream of text and can still be persuaded; sometimes it even made new attacks work.",
    found: "The only layer that clearly helped: attack success fell from 44.0% to 30.0% (1B) and from 39.9% to 20.0% (8B). It stopped 31 (1B) and 38 (8B) attacks but let 12 and 8 new ones through." },
  { id: "model", title: "AI model", sub: "writes the summary", layer: false,
    what: "A local Llama model (1B or 8B, run with Ollama) writes the summary. For testing the app there is also a mock model: a fake stand-in that is not an AI.",
    why: "With no defense, 56% (1B) and 60% (8B) of attacks already failed on their own: the model ignored them. Defenses only get credit for the attacks they actually changed." },
  { id: "L4", title: "L4 Output check", sub: "validation", layer: true,
    what: "Checks the finished answer for signs that the attack worked, e.g. \"the answer is in French\" or \"the attacker's link appears\".",
    good: "Looks at what actually came out, not at guesses about the input.",
    bad: "Only possible when the attack's goal is known in advance, so it is used for scoring evaluations, not for your own documents.",
    found: "Used as the scoring tool in the study; unclear answers were checked by a human." },
  { id: "result", title: "Result", sub: "allow / warn / block", layer: false,
    what: "ALLOW: nothing was flagged. WARN: a summary was produced but something was flagged, cleaned, or a layer could not run. BLOCK: no summary was delivered.",
    why: "Every result also shows how many model calls were made and how long it took, because protection has a cost." },
];

function renderLearn() {
  const pipe = $("pipeline");
  PIPELINE.forEach((step, i) => {
    if (i) pipe.append(el("span", { class: "pipe-arrow", "aria-hidden": "true", text: "→" }));
    const b = el("button", { type: "button", class: `pipe-step${step.layer ? " layer" : ""}`, role: "listitem" },
      document.createTextNode(step.title), el("small", { text: step.sub }));
    b.addEventListener("click", () => selectStep(step.id));
    b.dataset.step = step.id;
    pipe.append(b);
  });
  selectStep("doc");

  const cards = $("preset-cards");
  for (const name of Object.keys(config.presets)) {
    const p = config.presets[name];
    const card = el("div", { class: "preset-card" }, el("b", { text: name }), el("br"));
    for (const [on, label] of [[p.heuristic, "L1"], [p.classifier, "L2"], [p.structural, "L3"]]) {
      card.append(el("span", { class: `chip${on ? "" : " off"}`, text: label }));
    }
    card.append(el("div", { class: "muted", text: PRESET_TEXT[name] || "" }));
    cards.append(card);
  }
}

function selectStep(id) {
  const step = PIPELINE.find((s) => s.id === id);
  document.querySelectorAll(".pipe-step").forEach((b) => b.classList.toggle("selected", b.dataset.step === id));
  const box = $("pipeline-detail");
  box.replaceChildren(el("h3", { text: `${step.title} (${step.sub})` }), el("p", { text: step.what }));
  if (step.good) box.append(el("p", {}, el("b", { text: "Strength: " }), document.createTextNode(step.good)));
  if (step.bad) box.append(el("p", {}, el("b", { text: "Weakness: " }), document.createTextNode(step.bad)));
  if (step.found) box.append(el("p", {}, el("b", { text: "What the study found: " }), document.createTextNode(step.found)));
  if (step.why) box.append(el("p", { class: "muted", text: step.why }));
}

// ---------- meters ----------
// Semicircle gauge. value in [0, 1] (null = n/a); tick = optional threshold in [0, 1].
function gauge({ label, value, text, sub, kind = "mid", tick = null }) {
  const arc = "M 10 60 A 50 50 0 0 1 110 60";
  const color = { bad: "var(--bad)", good: "var(--good)", mid: "var(--accent)", warn: "var(--warn)" }[kind];
  const v = value === null ? 0 : Math.max(0, Math.min(1, value));
  const g = svg("svg", { viewBox: "0 0 120 72", role: "img", "aria-label": `${label}: ${text}` },
    svg("path", { d: arc, fill: "none", stroke: "var(--track)", "stroke-width": "12", "stroke-linecap": "round" }),
    svg("path", { d: arc, fill: "none", stroke: color, "stroke-width": "12", "stroke-linecap": "round",
      pathLength: "100", "stroke-dasharray": `${(v * 100).toFixed(2)} 200`, opacity: value === null || v < 0.01 ? "0" : "1" }),
    svg("text", { x: "60", y: "56", "text-anchor": "middle", "font-size": "17", "font-weight": "700", fill: "currentColor", text }));
  if (tick !== null) {
    const a = Math.PI * tick, c = Math.cos(a), s = Math.sin(a);
    g.append(svg("line", { x1: String(60 - 41 * c), y1: String(60 - 41 * s), x2: String(60 - 59 * c), y2: String(60 - 59 * s),
      stroke: "currentColor", "stroke-width": "2" }));
  }
  return el("div", { class: "gauge" }, g, el("div", { class: "g-label", text: label }), el("div", { class: "g-sub", text: sub || "" }));
}

function bar(label, k, n, kind, extra = "") {
  const v = pct(k, n);
  const fill = el("div", { class: `fill ${kind}` });
  fill.style.width = `${v ?? 0}%`;
  return el("div", { class: "bar" }, el("span", { text: label }), el("div", { class: "track" }, fill),
    el("span", { text: v === null ? "n/a" : `${fmtPct(v)} (${k}/${n})${extra}` }));
}

// ---------- setup ----------
async function init() {
  config = await api("/config");
  for (const name of Object.keys(config.presets)) $("preset").append(el("option", { value: name, text: `${name}: ${shortPreset(name)}` }));
  fillSelect($("p-heuristic"), config.policies.heuristic, (v) => `policy: ${v}`);
  fillSelect($("p-classifier"), config.policies.classifier, (v) => `policy: ${v}`);
  fillSelect($("p-variant"), config.structural_variants, (v) => `prompt wording ${v}`);
  $("preset").value = config.default_defense_preset === "E0" ? "E2" : config.default_defense_preset;
  applyPreset($("preset").value);

  const real = config.real_model;
  $("real-option").textContent = real ? `Real model: ${real.name} (${real.is_local ? "runs on this computer" : "remote provider"})` : "Real model (not configured)";
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
  renderLearn();
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => switchTab(tab.dataset.tab)));
  document.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.goto)));
  document.querySelectorAll(".seg").forEach((b) => b.addEventListener("click", () => { findingsModel = b.dataset.model; renderFindings(); }));
  $("doc").addEventListener("input", () => { updateCount(); clearExample(); });
  $("file").addEventListener("change", onFile);
  $("model").addEventListener("change", updateModelNote);
  $("preset").addEventListener("change", () => applyPreset($("preset").value));
  $("form").addEventListener("submit", onSubmit);
  $("ev-run").addEventListener("click", runEvaluation);
  $("runs-refresh").addEventListener("click", loadRuns);
  updateCount();
  loadExamples();
}

function shortPreset(name) {
  return { E0: "no protection", E1: "word rules (block)", E1b: "word rules (clean)", E2: "safer instructions",
    E3: "AI checker", E4: "word rules + safer instr.", E5: "all layers" }[name] || "";
}

function fillSelect(select, values, label) {
  for (const v of values) select.append(el("option", { value: v, text: label(v) }));
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  for (const pane of ["learn", "summarize", "findings", "results"]) $(`tab-${pane}`).classList.toggle("hidden", name !== pane);
  if (name === "results") loadRuns();
  if (name === "findings") loadFindings();
  window.scrollTo({ top: 0 });
}

function applyPreset(name) {
  const p = config.presets[name];
  $("d-heuristic").checked = p.heuristic; $("p-heuristic").value = p.heuristic_policy;
  $("d-classifier").checked = p.classifier && config.classifier_available; $("p-classifier").value = p.classifier_policy;
  $("d-structural").checked = p.structural; $("p-variant").value = p.structural_variant;
  $("d-output").checked = p.output_validation; $("d-failclosed").checked = p.fail_closed_on_detector_error;
  $("preset-desc").textContent = PRESET_TEXT[name] || "";
}

function currentDefenses() {
  return {
    name: $("preset").value,
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
    note.textContent = "The mock model is a fake stand-in: it makes no AI calls and simply copies sentences (and obeys obvious \"ignore previous instructions\" lines). Use it to see how the app works, not to judge real AI safety.";
  } else if (real && real.is_local) {
    note.textContent = "Your text is sent to the AI model running on this computer (Ollama). It must be running: start it with `ollama serve`.";
  } else {
    note.textContent = "Privacy notice: your document text will be sent to the external model provider configured for this app.";
  }
}

// ---------- demo examples ----------
async function loadExamples() {
  const root = $("examples");
  try {
    const data = await api("demo_examples.json");
    examples = data.examples;
  } catch { root.append(el("div", { class: "muted", text: "Examples could not be loaded; paste your own text." })); return; }
  for (const ex of examples) {
    const b = el("button", { type: "button", class: "example" },
      el("span", { class: `tag ${ex.kind}`, text: ex.kind === "attack" ? "CONTAINS ATTACK" : "CLEAN" }), el("br"),
      el("b", { text: ex.title }), el("div", { class: "muted", text: `Suggested: compare ${ex.suggested_compare.join(" vs ")}` }));
    b.dataset.example = ex.id;
    b.addEventListener("click", () => pickExample(ex));
    root.append(b);
  }
  root.append(el("div", { class: "muted", text: "Demo-only texts written for this page; they are not part of any test set." }));
}

function pickExample(ex) {
  currentExample = ex;
  $("doc").value = ex.text;
  updateCount();
  document.querySelectorAll(".example").forEach((b) => b.classList.toggle("selected", b.dataset.example === ex.id));
  const [, defended] = ex.suggested_compare;
  $("preset").value = defended; applyPreset(defended);
  $("compare").checked = true;
  const hint = $("example-hint");
  hint.textContent = `What to look for: ${ex.what_to_look_for}`;
  hint.classList.remove("hidden");
}

function clearExample() {
  if (!currentExample || $("doc").value === currentExample.text) return;
  currentExample = null;
  document.querySelectorAll(".example").forEach((b) => b.classList.remove("selected"));
  $("example-hint").classList.add("hidden");
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
    updateCount(); clearExample();
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
  $("results").replaceChildren(el("div", { class: "card placeholder muted", text: "Running… a real model can take 5 to 20 seconds per answer." }));
  try {
    const defended = await summarize(currentDefenses());
    const results = [{ title: `With protection: ${defended.defenses.name}`, data: defended }];
    if ($("compare").checked) {
      const baseline = await summarize({ name: "E0" });
      results.unshift({ title: "No protection: E0", data: baseline });
    }
    lastResults = results;
    renderResults(results);
  } catch (err) {
    $("results").replaceChildren();
    showError(err.message);
  } finally {
    button.disabled = false; button.textContent = "Run";
  }
}

function badge(text, cls) { return el("span", { class: `badge ${cls}`, text }); }

function renderResults(results) {
  const root = $("results");
  root.replaceChildren();
  if (currentExample) {
    root.append(el("div", { class: "note" }, el("b", { text: `Example: ${currentExample.title}. ` }), document.createTextNode(currentExample.what_to_look_for)));
  }
  const cols = el("div", { class: "cols" });
  for (const r of results) cols.append(renderResult(r.title, r.data));
  root.append(cols);
  root.append(el("div", { class: "note", text: "How to judge the answers: the app cannot automatically know whether a free-form answer obeyed a hidden instruction (that needs the attack's goal, which only the evaluations have). Read each summary: does it describe the document, or does it do what the hidden text asked (another language, a link, an unrelated reply)?" }));
  const exportBtn = el("button", { type: "button", class: "secondary", text: "Download result JSON" });
  exportBtn.addEventListener("click", () => download("result.json", JSON.stringify(lastResults, null, 2), "application/json"));
  root.append(exportBtn);
}

const VERDICT = {
  allow: ["Summary delivered: nothing suspicious found", "No layer flagged the document. This does not prove it is safe; quiet attacks are often missed."],
  warn: ["Summary delivered, with a warning", "Something was flagged or cleaned, or a layer could not run. Read the summary with care."],
  block: ["Blocked: no summary delivered", "A defense stopped the document before the AI answered, so the attack could not work (but you got no summary either)."],
};

function renderResult(title, d) {
  const card = el("div", { class: "result" });
  card.append(el("h3", { text: title }));
  const unchecked = d.enforcement_decision === "allow" && !d.defenses.heuristic && !d.defenses.classifier;
  const [head, body] = unchecked
    ? ["Summary delivered: no detector checked it", d.defenses.structural ? "Only the safer instructions were used; nothing scans the document, so read the answer yourself." : "No protection at all: whatever the document says goes straight to the AI."]
    : VERDICT[d.enforcement_decision];
  card.append(el("div", { class: `verdict ${d.enforcement_decision}` }, el("b", { text: head }), el("span", { text: body })));
  const badges = el("div", { class: "badges" });
  badges.append(badge(d.enforcement_decision.toUpperCase(), d.enforcement_decision));
  badges.append(d.model.is_mock ? badge("MOCK MODEL", "mock") : badge(`REAL: ${d.model.name}`, "real"));
  badges.append(badge(d.reached_model ? "reached model" : "blocked before model", d.reached_model ? "real" : "block"));
  card.append(badges);
  for (const w of d.warnings || []) card.append(el("div", { class: "note", text: w }));

  const meters = el("div", { class: "gauges" });
  const heur = d.detections.find((x) => x.layer === "heuristic");
  const clf = d.detections.find((x) => x.layer === "classifier");
  if (heur && heur.status === "evaluated") {
    meters.append(gauge({ label: "Word-rule suspicion", value: Math.min(heur.score / 3, 1), tick: 1 / 3,
      text: heur.score.toFixed(1), sub: "tick = flag line (1.0)", kind: heur.flagged ? "bad" : "good" }));
  }
  if (clf && clf.status === "evaluated") {
    meters.append(gauge({ label: `AI checker: ${clf.flagged ? "suspicious" : "looks clean"}`, value: clf.score,
      text: `${Math.round(clf.score * 100)}%`, sub: "how sure the checker is", kind: clf.flagged ? "bad" : "good" }));
  }
  const on = [d.defenses.heuristic, d.defenses.classifier, d.defenses.structural].filter(Boolean).length;
  meters.append(gauge({ label: "Protection layers on", value: on / 3, text: `${on} / 3`, sub: "L1, L2, L3", kind: "mid" }));
  meters.append(gauge({ label: "Time taken", value: Math.min(d.latency_ms / 20000, 1), text: `${(d.latency_ms / 1000).toFixed(1)} s`,
    sub: `${d.model_calls} model call(s)`, kind: "warn" }));
  card.append(meters);

  card.append(el("h3", { text: "What happened, step by step" }));
  card.append(timeline(d));

  card.append(el("h3", { text: "Answer" }));
  card.append(el("pre", { class: "summary", text: d.summary === null ? `(no summary delivered; blocked by ${d.blocked_by})` : d.summary }));

  const details = el("details", {}, el("summary", { text: "Technical details" }));
  if (d.detections.length) {
    const table = el("table");
    table.append(rowOf(["layer", "status", "flagged", "score", "policy action", "explanation"], "th"));
    for (const det of d.detections) {
      const tr = rowOf([det.layer, det.status, String(det.flagged), det.score ?? "-", det.policy_action, det.explanation], "td");
      tr.lastChild.className = "wrap";
      table.append(tr);
    }
    details.append(table);
    const rules = d.detections.flatMap((x) => x.matched_rules.map((m) => `${m.rule_id} (weight ${m.weight}, ${m.spans.length}×): ${m.description}`));
    if (rules.length) details.append(el("div", { class: "muted", text: "Matched rules: " + rules.join(" | ") }));
  }
  if (d.output_validation) details.append(el("div", { class: "muted", text: `Output validation: ${d.output_validation.outcome}. ${d.output_validation.explanation}` }));
  const kv = el("dl", { class: "kv" });
  const add = (k, v) => { kv.append(el("dt", { text: k }), el("dd", { text: String(v) })); };
  add("request id", d.request_id);
  add("model", `${d.model.provider} / ${d.model.name}`);
  add("model calls", d.model_calls);
  add("latency", `${d.latency_ms} ms`);
  add("layers run", d.layers_run.join(", ") || "none (baseline)");
  add("stage timings", Object.entries(d.timings_ms).map(([k, v]) => `${k} ${v} ms`).join(", ") || "-");
  add("defenses", d.defenses.name + ": " + (d.defenses.structural ? `structural ${d.defenses.structural_variant}, ` : "") + (["heuristic", "classifier", "output_validation"].filter((x) => d.defenses[x]).join(", ") || "no detectors"));
  details.append(kv);
  card.append(details);
  return card;
}

function timeline(d) {
  const list = el("ol", { class: "timeline" });
  const step = (icon, sym, title, text) => list.append(el("li", {}, el("span", { class: `icon ${icon}`, text: sym }),
    el("div", {}, el("b", { text: title }), document.createTextNode(` ${text}`))));
  const action = { blocked: "The document was blocked.", sanitized: "The suspicious lines were cut out before the AI saw them.",
    flagged_only: "It was only flagged (warning), not stopped.", ignored_error: "The failure was ignored and processing continued.", none: "" };
  step("info", "i", "Document received.", `${$("doc").value.length.toLocaleString()} characters, treated as untrusted.`);
  for (const [layer, label] of [["heuristic", "L1 Word rules:"], ["classifier", "L2 AI checker:"]]) {
    const det = d.detections.find((x) => x.layer === layer);
    if (!d.defenses[layer]) { step("off", "–", label, "off in this preset."); continue; }
    if (!det) { step("off", "–", label, "did not run (an earlier layer already blocked the document)."); continue; }
    if (det.status !== "evaluated") { step("warn", "!", label, `could not run. ${action[det.policy_action]}`); continue; }
    if (det.flagged) {
      const why = layer === "heuristic" ? `attack-like wording found (score ${det.score}, flag line 1.0).` : `judged the document suspicious (${Math.round(det.score * 100)}% sure).`;
      step(det.policy_action === "blocked" ? "block" : "warn", "!", label, `${why} ${action[det.policy_action]}`);
    } else {
      step("ok", "✓", label, layer === "heuristic" ? "no known attack wording found." : `judged the document clean (${Math.round(det.score * 100)}% sure).`);
    }
  }
  if (!d.defenses.structural) step("off", "–", "L3 Safer instructions:", "off; the document was pasted straight into the AI's instructions.");
  else if (!d.reached_model) step("off", "–", "L3 Safer instructions:", "not needed; the document never reached the AI.");
  else step("ok", "✓", "L3 Safer instructions:", `on; the document was wrapped in markers and the AI was told to treat it as data only (wording ${d.defenses.structural_variant}).`);
  if (d.reached_model) step("info", "AI", "Model answered:", `${d.model.is_mock ? "mock stand-in (not a real AI)" : d.model.name}, in ${((d.timings_ms.generation || 0) / 1000).toFixed(1)} s.`);
  else step("block", "✕", "Model:", "never reached; no AI answer was generated.");
  if (d.output_validation) step(d.output_validation.outcome === "indicator_matched" ? "block" : "ok", "✓", "L4 Output check:", d.output_validation.explanation);
  else step("off", "–", "L4 Output check:", "off (needs the attack's goal, which is only known in evaluations).");
  return list;
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

// ---------- research results (verified findings) ----------
async function loadFindings() {
  if (findings) return;
  try {
    findings = await api("/findings");
    renderFindings();
  } catch (err) {
    $("f-error").textContent = `Could not load the verified results: ${err.message}`;
    $("f-error").classList.remove("hidden");
  }
}

function prettyFamily(f) {
  return f.replace(/^bipia_/, "").split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");
}

function renderFindings() {
  if (!findings) return;
  document.querySelectorAll(".seg").forEach((b) => b.classList.toggle("active", b.dataset.model === findingsModel));
  const rows = findings.comparison.filter((r) => r.model === findingsModel);
  const by = Object.fromEntries(rows.map((r) => [r.config, r]));
  const e0 = by.E0, e2 = by.E2, e5 = by.E5;

  const resisted = e0.asr_n - e0.asr_k;
  $("f-gauges").replaceChildren(
    gauge({ label: "Attacks that worked, no defense", value: pct(e0.asr_k, e0.asr_n) / 100, text: fmtPct(pct(e0.asr_k, e0.asr_n)),
      sub: `${e0.asr_k} of ${e0.asr_n} attempts (E0)`, kind: "bad" }),
    gauge({ label: "Attacks that worked, safer instructions", value: pct(e2.asr_k, e2.asr_n) / 100, text: fmtPct(pct(e2.asr_k, e2.asr_n)),
      sub: `${e2.asr_k} of ${e2.asr_n} (E2)${e2.asr_unresolved ? `, ${e2.asr_unresolved} unresolved` : ""}`, kind: "bad" }),
    gauge({ label: "Usable summaries, safer instructions", value: pct(e2.usable_k, e2.usable_n) / 100, text: fmtPct(pct(e2.usable_k, e2.usable_n)),
      sub: `vs ${fmtPct(pct(e0.usable_k, e0.usable_n))} with no defense`, kind: "good" }),
    gauge({ label: "Attacks the model ignored by itself", value: resisted / e0.asr_n, text: fmtPct(pct(resisted, e0.asr_n)),
      sub: `${resisted} of ${e0.asr_n}, with no defense at all`, kind: "mid" }),
    gauge({ label: "False alarms on clean docs (all layers)", value: pct(e5.fpr_k, e5.fpr_n) / 100, text: fmtPct(pct(e5.fpr_k, e5.fpr_n)),
      sub: `${e5.fpr_k} of ${e5.fpr_n} clean runs (E5)`, kind: "bad" }),
  );

  const list = $("f-configs");
  list.replaceChildren();
  for (const r of rows) {
    const facts = [
      r.fpr_n ? `false alarms ${r.fpr_k}/${r.fpr_n}` : "false alarms: n/a (no detector)",
      r.detect_n ? `detected ${r.detect_k}/${r.detect_n} attacks` : "no detector",
      `avg ${(r.latency_mean_ms / 1000).toFixed(1)} s per answer`,
    ];
    if (r.asr_unresolved) facts.push(`${r.asr_unresolved} unresolved (left out)`);
    list.append(el("div", { class: "cfg-row" },
      el("div", {}, el("b", { text: `${r.config}: ${shortPreset(r.config)}` }), el("div", { class: "desc", text: PRESET_TEXT[r.config] || "" })),
      el("div", {}, bar("attack worked", r.asr_k, r.asr_n, "bad"), bar("usable summary", r.usable_k, r.usable_n, "good"),
        el("div", { class: "muted", text: facts.join(" · ") }))));
  }

  const tr = $("f-transitions");
  tr.replaceChildren(el("div", { class: "legend" },
    ...[["var(--good)", "stopped (worked before, failed now)"], ["var(--bad)", "still worked"], ["var(--warn)", "new success (failed before, worked now)"],
      ["var(--track)", "failed both times"], ["var(--muted)", "unresolved"]].map(([c, t]) => { const i = el("i"); i.style.background = c; return el("span", {}, i, document.createTextNode(t)); })));
  for (const r of rows) {
    if (r.config === "E0") continue;
    const t = findings.transitions_vs_E0[`${findingsModel}|${r.config}`] || {};
    const parts = [["success->fail", "var(--good)"], ["success->success", "var(--bad)"], ["fail->success", "var(--warn)"], ["fail->fail", "var(--track)"], ["unresolved", "var(--muted)"]];
    const total = parts.reduce((s, [k]) => s + (t[k] || 0), 0) || 1;
    const stack = el("div", { class: "stack", role: "img", "aria-label": `${r.config} transitions` });
    for (const [k, c] of parts) { const seg = el("div", { title: `${k}: ${t[k] || 0}` }); seg.style.width = `${(100 * (t[k] || 0)) / total}%`; seg.style.background = c; stack.append(seg); }
    tr.append(el("div", { class: "cfg-row" }, el("b", { text: `${r.config}: ${shortPreset(r.config)}` }),
      el("div", {}, stack, el("div", { class: "muted", text: `stopped ${t["success->fail"] || 0} · still worked ${t["success->success"] || 0} · new successes ${t["fail->success"] || 0} · net change ${(t["fail->success"] || 0) - (t["success->fail"] || 0)}` }))));
  }

  const cat = $("f-categories");
  cat.replaceChildren();
  const fam = (cfg) => Object.fromEntries(findings.category.filter((c) => c.model === findingsModel && c.config === cfg).map((c) => [c.family, c]));
  const c0 = fam("E0"), c2 = fam("E2");
  const families = Object.keys(c0).sort((a, b) => c0[b].successes / (c0[b].decided || 1) - c0[a].successes / (c0[a].decided || 1));
  for (const f of families) {
    const a = c0[f], b = c2[f] || { successes: 0, decided: 0 };
    cat.append(el("div", { class: "cfg-row" }, el("b", { text: prettyFamily(f) }),
      el("div", {}, bar("no defense", a.successes, a.decided, "bad"), bar("safer instr.", b.successes, b.decided, "mid"))));
  }
  cat.append(el("div", { class: "muted", text: "Reverse Text is scored only by exact character reversal, so its result is probably an underestimate." }));
}

// ---------- evaluation results (advanced) ----------
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
