"use strict";
// All untrusted text (documents, summaries, explanations) is inserted with textContent only,
// never innerHTML: a malicious document can make the model emit markup.

const $ = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";
const REDUCED_MOTION = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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

// Run `fn` after the element has been painted once, so CSS transitions animate from the start value.
const afterPaint = (fn) => requestAnimationFrame(() => requestAnimationFrame(fn));

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
  E0: "No protection. The document goes straight to the AI. The baseline everything is compared with.",
  E1: "Word rules scan for attack phrases and block the document if they find any.",
  E1b: "Word rules, but instead of blocking they cut out the suspicious lines and carry on.",
  E2: "Safer instructions: the AI is told the document is only data to summarize, never orders to follow.",
  E3: "AI checker: an extra AI call first judges whether the document contains an attack.",
  E4: "Word rules plus safer instructions.",
  E5: "Everything: word rules, AI checker and safer instructions.",
};

function shortPreset(name) {
  return { E0: "no protection", E1: "word rules (block)", E1b: "word rules (clean)", E2: "safer instructions",
    E3: "AI checker", E4: "word rules + safer instr.", E5: "all layers" }[name] || "";
}

const PIPELINE = [
  { id: "doc", node: "DOC", title: "Document", sub: "untrusted input", layer: false,
    what: "The text you want summarized: pasted, picked from the examples, or extracted from a PDF, DOCX or TXT file.",
    good: "Nothing to configure: every document is treated as untrusted.",
    bad: "An attacker can hide an instruction anywhere in it, in any wording.",
    found: "We hid 75 instructions written by other researchers at the start, middle or end of ordinary articles." },
  { id: "L1", node: "L1", title: "Word rules", sub: "heuristic detector", layer: true,
    what: "Looks for known attack phrases, such as \"ignore previous instructions\", using weighted rules. At a score of 1.0 the document is flagged; the preset decides whether to block it, cut out the lines, or only warn.",
    good: "Fast, free and explainable: it shows exactly which rule matched.",
    bad: "Only catches wording it already knows. Rephrased or polite attacks slip past, and articles that merely quote an attack get flagged.",
    found: "Caught 0 of 150 externally written attacks. Earlier, it caught 72.7% of the attack styles it was built for but only 8.3% of unseen styles." },
  { id: "L2", node: "L2", title: "AI checker", sub: "model classifier", layer: true,
    what: "A separate call to the AI model reads the document and answers \"suspicious or not?\", with a confidence from 0 to 1.",
    good: "Can judge meaning, not just exact words.",
    bad: "Costs an extra model call per document, and the checker itself can be fooled.",
    found: "Flagged 8 of 146 attacked documents with the 1B model and 0 of 146 with the 8B model." },
  { id: "L3", node: "L3", title: "Safer instructions", sub: "structural separation", layer: true,
    what: "Wraps the document between unique markers and tells the AI: everything between them is data to summarize; any instruction inside must be ignored.",
    good: "No extra call, and it works even against attacks with no suspicious words.",
    bad: "The AI still reads one stream of text and can still be persuaded; sometimes it even made a new attack work.",
    found: "The only layer that clearly helped: attack success fell from 44.0% to 30.0% (1B) and from 39.9% to 20.0% (8B). It stopped 31 and 38 attacks, but let 12 and 8 new ones through." },
  { id: "model", node: "AI", title: "AI model", sub: "writes the summary", layer: false,
    what: "A local Llama model (1B or 8B, run with Ollama) writes the answer. For testing the app there is also a mock model: a fake stand-in, not an AI.",
    good: "Runs on this computer: no document leaves the machine.",
    bad: "Small models are easier to confuse than large hosted ones.",
    found: "With no defense, 56% (1B) and 60% (8B) of attacks already failed: the model ignored them on its own." },
  { id: "L4", node: "L4", title: "Output check", sub: "validation", layer: true,
    what: "Checks the finished answer for signs the attack worked, e.g. \"the answer is in French\" or \"the attacker's link appears\".",
    good: "Judges what actually came out, not guesses about the input.",
    bad: "Needs to know the attack's goal in advance, which a real user doesn't. So it is used to score experiments.",
    found: "Used as the scoring tool; every answer it could not decide was checked by a person." },
  { id: "result", node: "✓", title: "Result", sub: "allow · warn · block", layer: false,
    what: "ALLOW: nothing was flagged. WARN: an answer was produced but something was flagged, cleaned, or a layer could not run. BLOCK: no answer was delivered.",
    good: "Every result shows the model calls and time taken: protection has a cost.",
    bad: "\"Allow\" does not mean safe; it only means no layer noticed anything.",
    found: "With the best preset, about 1 in 5 attacks (8B) and 3 in 10 (1B) still worked." },
];

function renderLearn() {
  const pipe = $("pipeline");
  for (const step of PIPELINE) {
    const b = el("button", { type: "button", class: `pipe-step${step.layer ? " layer" : ""}`, role: "listitem" },
      el("span", { class: "node", text: step.node }), el("b", { text: step.title }), el("small", { text: step.sub }));
    b.dataset.step = step.id;
    b.addEventListener("click", () => selectStep(step.id));
    pipe.append(b);
  }
  selectStep("L3");

  const body = $("preset-cards");
  for (const name of Object.keys(config.presets)) {
    const p = config.presets[name];
    const tr = el("tr", {}, el("td", {}, el("span", { class: "pname", text: name })));
    for (const on of [p.heuristic, p.classifier, p.structural]) {
      tr.append(el("td", { class: "c" }, el("span", { class: on ? "on" : "off", title: on ? "on" : "off" })));
    }
    tr.append(el("td", { class: "muted", text: PRESET_TEXT[name] || "" }));
    body.append(tr);
  }
}

function selectStep(id) {
  const step = PIPELINE.find((s) => s.id === id);
  document.querySelectorAll(".pipe-step").forEach((b) => b.classList.toggle("selected", b.dataset.step === id));
  const box = $("pipeline-detail");
  const fresh = box.cloneNode(false);  // re-trigger the entrance animation
  fresh.append(el("h3", { text: `${step.title} · ${step.sub}` }), el("p", { class: "what", text: step.what }),
    el("p", { class: "pt" }, el("b", { text: "Strength" }), document.createTextNode(step.good)),
    el("p", { class: "pt" }, el("b", { text: "Weakness" }), document.createTextNode(step.bad)),
    el("p", { class: "pt found" }, el("b", { text: "What the study found" }), document.createTextNode(step.found)));
  box.replaceWith(fresh);
}

// ---------- meters ----------
// Semicircle gauge. value in [0, 1] (null = n/a); tick = optional threshold in [0, 1].
function gauge({ label, value, text, sub, kind = "mid", tick = null }) {
  const arc = "M 10 60 A 50 50 0 0 1 110 60";
  const color = { bad: "var(--danger)", good: "var(--success)", mid: "var(--primary)", warn: "var(--warn)" }[kind];
  const v = value === null ? 0 : Math.max(0, Math.min(1, value));
  const fill = svg("path", { class: "arc", d: arc, fill: "none", stroke: color, "stroke-width": "10", "stroke-linecap": "round",
    pathLength: "100", "stroke-dasharray": "0 200", opacity: v < 0.01 ? "0" : "1" });
  const g = svg("svg", { viewBox: "0 0 120 70", role: "img", "aria-label": `${label}: ${text}` },
    svg("path", { d: arc, fill: "none", stroke: "var(--track)", "stroke-width": "10", "stroke-linecap": "round" }), fill,
    svg("text", { class: "g-val", x: "60", y: "58", "text-anchor": "middle", text }));
  if (tick !== null) {
    const a = Math.PI * tick, c = Math.cos(a), s = Math.sin(a);
    g.append(svg("line", { x1: String(60 - 42 * c), y1: String(60 - 42 * s), x2: String(60 - 58 * c), y2: String(60 - 58 * s),
      stroke: "var(--text)", "stroke-width": "2" }));
  }
  afterPaint(() => fill.setAttribute("stroke-dasharray", `${(v * 100).toFixed(2)} 200`));
  return el("div", { class: "gauge" }, g, el("div", { class: "g-label", text: label }), el("div", { class: "g-sub", text: sub || "" }));
}

function bar(label, k, n, kind) {
  const v = pct(k, n);
  const fill = el("div", { class: `fill ${kind}` });
  afterPaint(() => { fill.style.width = `${v ?? 0}%`; });
  return el("div", { class: "bar" }, el("span", { text: label }), el("div", { class: "track" }, fill),
    el("span", { text: v === null ? "n/a" : `${fmtPct(v)}  (${k}/${n})` }));
}

function countUp(node, target, suffix = "%") {
  if (REDUCED_MOTION) { node.textContent = `${target.toFixed(1)}${suffix}`; return; }
  const start = performance.now(), ms = 900;
  const tick = (now) => {
    const t = Math.min(1, (now - start) / ms), eased = 1 - Math.pow(1 - t, 3);
    node.textContent = `${(target * eased).toFixed(1)}${suffix}`;
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// ---------- setup ----------
async function init() {
  config = await api("/config");
  for (const name of Object.keys(config.presets)) $("preset").append(el("option", { value: name, text: `${name} · ${shortPreset(name)}` }));
  fillSelect($("p-heuristic"), config.policies.heuristic, (v) => `policy: ${v}`);
  fillSelect($("p-classifier"), config.policies.classifier, (v) => `policy: ${v}`);
  fillSelect($("p-variant"), config.structural_variants, (v) => `prompt wording ${v}`);
  $("preset").value = config.default_defense_preset === "E0" ? "E2" : config.default_defense_preset;
  applyPreset($("preset").value);

  const real = config.real_model;
  $("real-option").textContent = real ? `Real model: ${real.name} (${real.is_local ? "on this computer" : "remote provider"})` : "Real model (not configured)";
  $("real-option").disabled = !real;
  if (config.default_model_mode === "real" && real) $("model").value = "real";
  $("clf-state").textContent = config.classifier_available ? "" : "(not configured)";
  $("d-classifier").disabled = !config.classifier_available;
  updateModelNote();

  const exps = $("ev-exps");
  for (const name of Object.keys(config.presets)) {
    const box = el("input", { type: "checkbox", value: name });
    box.checked = ["E0", "E1", "E2", "E4"].includes(name);
    exps.append(el("label", { class: "check" }, box, ` ${name}`));
  }
  renderLearn();
  const pill = $("model-pill");
  pill.lastChild.textContent = real ? `${real.name} · ${real.is_local ? "local" : "remote"}` : "real model not configured";
  pill.firstChild.classList.toggle("on", Boolean(real));
  document.querySelectorAll(".nav-item").forEach((item) => item.addEventListener("click", () => switchTab(item.dataset.tab)));
  $("menu-btn").addEventListener("click", () => setNav(!$("app").classList.contains("nav-open")));
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
  loadFindings();
}

// ---------- theme, brand, intro, navigation ----------
// Site mark: a shield guarding a page. A scan beam sweeps the page and the hidden (red) line flashes when caught.
function logo() {
  return svg("svg", { viewBox: "0 0 32 32", class: "logo", "aria-hidden": "true" },
    svg("path", { class: "lg-shield", pathLength: "100", d: "M16 2.5 27 6.5V15c0 7-4.8 12-11 14.5C9.8 27 5 22 5 15V6.5Z" }),
    svg("rect", { class: "lg-page", x: "10.5", y: "9", width: "11", height: "13.5", rx: "1.6" }),
    svg("path", { class: "lg-line", d: "M13 12.5h6M13 18.8h4.5" }),
    svg("path", { class: "lg-bad", d: "M13 15.6h6" }),
    svg("path", { class: "lg-beam", d: "M9.5 10h13" }));
}

function setupBrand() {
  document.querySelectorAll(".logo-slot").forEach((slot) => slot.replaceWith(logo()));
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try { localStorage.setItem("theme", theme); } catch { /* private mode: theme just isn't remembered */ }
  const sun = "M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4";
  document.querySelectorAll(".theme-toggle").forEach((b) => {
    b.replaceChildren(theme === "dark"
      ? svg("svg", { viewBox: "0 0 24 24" }, svg("circle", { cx: "12", cy: "12", r: "4.5" }), svg("path", { d: sun }))
      : svg("svg", { viewBox: "0 0 24 24" }, svg("path", { d: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" })));
    b.title = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  });
}

function setupTheme() {
  setTheme(document.documentElement.getAttribute("data-theme") || "light");
  document.querySelectorAll(".theme-toggle").forEach((b) => b.addEventListener("click",
    () => setTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark")));
}

function setupIntro() {
  // Split the heading into per-letter spans (grouped by word so lines wrap between words).
  const title = $("intro-title"), words = title.textContent.split(" ");
  title.replaceChildren();
  let n = 0;
  words.forEach((word, wi) => {
    const w = el("span", { class: "w", "aria-hidden": "true" });
    for (const ch of word) {
      const span = el("span", { class: `ch${word.startsWith("orders") ? " accent" : ""}`, text: ch });
      span.style.animationDelay = `${0.25 + n++ * 0.035}s`;
      w.append(span);
    }
    title.append(w);
    if (wi < words.length - 1) title.append(document.createTextNode(" "));
  });

  // Particles orbiting the 3D document stack; one red = the hidden instruction.
  const stack = $("stack");
  for (let i = 0; i < 9; i++) {
    const p = el("span", { class: `particle${i === 4 ? " red" : ""}` });
    p.style.setProperty("--a", `${i * 40}deg`); p.style.animationDelay = `${-i * 0.66}s`;
    stack.append(p);
  }
  // Tilt the stack with the pointer.
  $("intro").addEventListener("pointermove", (e) => {
    const x = e.clientX / innerWidth - 0.5, y = e.clientY / innerHeight - 0.5;
    stack.style.setProperty("--rx", `${x * 30}deg`); stack.style.setProperty("--ry", `${-y * 20}deg`);
  });

  // Typed line under the button.
  const lines = ["scanning document for hidden orders…", "L1 word rules · L2 AI checker · L3 safer instructions", "75 real attacks · 2 local models · human-reviewed"];
  let li = 0, ci = 0;
  const typed = $("typed");
  const type = () => {
    if (!$("intro") || $("intro").classList.contains("hidden")) return;
    const line = lines[li];
    typed.textContent = line.slice(0, ++ci);
    if (ci < line.length) setTimeout(type, 38);
    else setTimeout(() => { ci = 0; li = (li + 1) % lines.length; type(); }, 1800);
  };
  setTimeout(type, 2200);

  const enter = () => {
    try { sessionStorage.setItem("introSeen", "1"); } catch { /* ignore */ }
    $("intro").classList.add("leaving");
    $("app").classList.remove("hidden");
    setTimeout(() => $("intro").classList.add("hidden"), 600);
  };
  $("enter").addEventListener("click", enter);
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" && !$("intro").classList.contains("hidden")) enter(); });
  let seen = false;
  try { seen = sessionStorage.getItem("introSeen") === "1"; } catch { /* ignore */ }
  if (seen) { $("intro").classList.add("hidden"); $("app").classList.remove("hidden"); }
}

function setNav(open) {
  $("app").classList.toggle("nav-open", open);
  const existing = document.querySelector(".scrim");
  if (open && !existing) {
    const scrim = el("div", { class: "scrim" });
    scrim.addEventListener("click", () => setNav(false));
    $("app").append(scrim);
  } else if (!open && existing) existing.remove();
}

function fillSelect(select, values, label) {
  for (const v of values) select.append(el("option", { value: v, text: label(v) }));
}

const PAGE_TITLES = { overview: "Overview", summarize: "Test a document", findings: "Results", learn: "How it works", results: "Evaluations" };

function switchTab(name) {
  document.querySelectorAll(".nav-item").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  for (const pane of Object.keys(PAGE_TITLES)) $(`tab-${pane}`).classList.toggle("hidden", name !== pane);
  $("page-title").textContent = PAGE_TITLES[name];
  document.title = `${PAGE_TITLES[name]} · Defense Lab`;
  if (name === "results") loadRuns();
  if ((name === "findings" || name === "overview") && findings) renderFindings();
  setNav(false);
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
    note.textContent = "Not an AI: it copies sentences and obeys obvious \"ignore previous instructions\" lines. Good for seeing how the app works, not for judging AI safety.";
  } else if (real && real.is_local) {
    note.textContent = "Runs on this computer through Ollama (start it with `ollama serve`). Nothing leaves the machine.";
  } else {
    note.textContent = "Privacy notice: your document text will be sent to the external model provider configured for this app.";
  }
}

// ---------- demo examples ----------
async function loadExamples() {
  const root = $("examples");
  try {
    examples = (await api("demo_examples.json")).examples;
  } catch { root.append(el("div", { class: "small", text: "Examples could not be loaded; paste your own text." })); return; }
  for (const ex of examples) {
    const b = el("button", { type: "button", class: "example" },
      el("span", { class: `dot ${ex.kind}`, title: ex.kind === "attack" ? "contains an attack" : "clean" }),
      el("span", { text: ex.title }),
      el("span", { class: "tag", text: ex.kind === "attack" ? "attack" : "clean" }));
    b.dataset.example = ex.id;
    b.addEventListener("click", () => pickExample(ex));
    root.append(b);
  }
  root.append(el("div", { class: "small", text: "Demo texts, not part of any test set." }));
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

// ---------- live run view ----------
// Walks the document through the layers while the request runs. Steps before the model are paced so they
// can be read; the model step waits for the server's real reply, and then every station is coloured from
// that reply (so where the document stopped, and why, is real, not animation).
const STEP_MS = REDUCED_MOTION ? 150 : 1150;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const STATIONS = {
  doc: { label: "Document", icon: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5",
    head: "Reading the document", text: "The text is loaded and treated as untrusted: any sentence in it could be a hidden order." },
  heuristic: { label: "L1 Words", icon: "M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0zM20 20l-4.5-4.5",
    head: "L1 · scanning for attack wording", text: "Fast word rules look for phrases such as “ignore previous instructions” or “you are now”." },
  classifier: { label: "L2 Checker", icon: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    head: "L2 · asking the AI checker", text: "A second AI reads the document and answers one question: does this look like an attack?" },
  structural: { label: "L3 Wrap", icon: "M8 4H5v16h3M16 4h3v16h-3",
    head: "L3 · fencing the document as data", text: "The text is wrapped in markers with a random code, and the AI is told that nothing inside them is an order." },
  model: { label: "AI model", icon: "M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4",
    head: "Asking the AI to summarize", text: "" },
  output: { label: "L4 Output", icon: "M4 6h10M4 12h10M4 18h6M15 16l2.5 2.5L22 14",
    head: "L4 · checking the answer", text: "The answer is compared with what the attack wanted, to see whether it slipped through." },
  answer: { label: "Answer", icon: "M4 5h16v11H9l-5 4z", head: "", text: "" },
};

function runView(total) {
  const title = el("h3"), clock = el("span", { class: "run-clock", text: "0.0 s" });
  const track = el("div", { class: "track" });
  const scene = el("div", { class: "scene-box", "aria-hidden": "true" });
  const say = el("div", { class: "say" });
  const log = el("ul", { class: "run-log" });
  const node = el("div", { class: "card run", role: "status", "aria-live": "polite" },
    el("div", { class: "run-head" }, title, clock), track, el("div", { class: "stage" }, scene, say), log);
  const started = performance.now();
  const timer = setInterval(() => { clock.textContent = `${((performance.now() - started) / 1000).toFixed(1)} s`; }, 100);
  return { node, title, track, scene, say, log, total, stations: [], stop: () => clearInterval(timer) };
}

function setTrack(view, keys) {
  const fill = el("div", { class: "track-fill" });
  const packet = el("div", { class: "packet" }, el("i"), el("i"), el("i"));
  view.track.replaceChildren(el("div", { class: "track-line" }, fill), packet);
  view.track.style.setProperty("--n", keys.length);
  view.stations = keys.map((k) => {
    const s = el("div", { class: "station" },
      el("span", { class: "st-dot" }, svg("svg", { viewBox: "0 0 24 24" }, svg("path", { d: STATIONS[k].icon }))),
      el("span", { class: "st-label", text: STATIONS[k].label }));
    view.track.append(s);
    return s;
  });
  Object.assign(view, { fill, packet });
}

function moveTo(view, i) {
  const n = view.stations.length;
  view.packet.style.left = `${((i + 0.5) / n) * 100}%`;
  view.fill.style.width = `${(i / (n - 1)) * 100}%`;
  view.stations.forEach((s, j) => { s.classList.toggle("now", j === i); s.classList.toggle("passed", j < i); });
}

// Small decorative scene for each step (aria-hidden; the text beside it says the same thing).
function miniPage() {
  const page = el("div", { class: "mp" });
  [88, 72, 94, 80, 66, 84].forEach((w, i) => { const line = el("i", { class: i === 3 ? "bad" : "" }); line.style.setProperty("--w", `${w}%`); page.append(line); });
  return page;
}

function sceneFor(key, tone) {
  switch (key) {
    case "doc": case "heuristic": return [miniPage(), ...(key === "heuristic" ? [el("div", { class: "lens" })] : [])];
    case "classifier": return [miniPage(), el("div", { class: "bot" }, el("i")), el("div", { class: "bubble", text: "attack?" })];
    case "structural": return [el("div", { class: "fence" }, miniPage()), el("div", { class: "fence-tag", text: "DATA ONLY" })];
    case "model": return [el("div", { class: "chip" }, el("i")), el("div", { class: "stream" }, el("i"), el("i"), el("i"))];
    case "output": return [el("div", { class: "ans" }, ...[0, 1, 2].map(() => el("div", {}, el("i"), el("b", { text: "✓" }))))];
    default: return [el("div", { class: `ball ${tone}`, text: { allow: "✓", warn: "!", block: "✕", unchecked: "–" }[tone] })];
  }
}

function narrate(view, key, head, text, tone = "") {
  view.scene.className = `scene-box s-${key}`;
  view.scene.replaceChildren(...sceneFor(key, tone));
  view.say.replaceChildren(el("h4", { text: head }), el("p", { text }));
}

function blockKey(d) {
  return { heuristic: "heuristic", classifier: "classifier", output_validation: "output" }[d.blocked_by] || "answer";
}

function stationState(key, d) {
  if (key === "heuristic" || key === "classifier") {
    const det = d.detections.find((x) => x.layer === key);
    if (!det) return "skip";
    if (det.status !== "evaluated") return "warn";
    return !det.flagged ? "ok" : det.policy_action === "blocked" ? "block" : "warn";
  }
  if (key === "structural" || key === "model") return d.reached_model ? "ok" : "skip";
  if (key === "output") return !d.output_validation ? "skip" : d.output_validation.outcome === "indicator_matched" ? "block" : "ok";
  if (key === "answer") return { block: "block", warn: "warn" }[d.enforcement_decision] || "ok";
  return "ok";
}

async function playRun(view, run, index) {
  const d = run.defenses;
  const keys = ["doc", ...["heuristic", "classifier", "structural"].filter((k) => d[k]), "model", ...(d.output_validation ? ["output"] : []), "answer"];
  view.title.textContent = `${view.total > 1 ? `Run ${index + 1} of ${view.total} · ` : ""}${run.title}`;
  setTrack(view, keys);
  STATIONS.model.text = d.structural
    ? "The AI gets your instruction plus the fenced document and writes the summary."
    : "The document goes straight into the AI's instructions, so a hidden order looks just like yours.";

  let data = null, failure = null, settled = false;
  const request = summarize(run.payload).then((r) => { data = r; }, (e) => { failure = e; }).finally(() => { settled = true; });
  const modelAt = keys.indexOf("model");
  for (let i = 0; i <= modelAt; i++) {
    moveTo(view, i);
    narrate(view, keys[i], STATIONS[keys[i]].head, STATIONS[keys[i]].text);
    await sleep(STEP_MS);
    if (failure) throw failure;
    if (data && !data.reached_model && keys.indexOf(blockKey(data)) <= i) break;  // stopped before the AI
  }
  if (!settled) {
    view.scene.classList.add("waiting");
    view.say.append(el("p", { class: "small", text: "Waiting for the server: the checks and the AI's answer run there. The stations are coloured from its real reply." }));
    await request;
  }
  if (failure) throw failure;
  if (data.reached_model && keys.includes("output")) {
    moveTo(view, keys.indexOf("output"));
    narrate(view, "output", STATIONS.output.head, STATIONS.output.text);
    await sleep(STEP_MS * 0.8);
  }

  // Reveal what really happened.
  const { tone, head, body } = verdictOf(data);
  const stopAt = keys.indexOf(blockKey(data));
  moveTo(view, stopAt < 0 ? keys.length - 1 : stopAt);
  view.packet.classList.add(tone);
  keys.forEach((k, j) => setTimeout(() => view.stations[j].classList.add("final", stationState(k, data)), j * 110));
  narrate(view, "result", head, body, tone);
  const stopper = data.detections.find((x) => x.layer === data.blocked_by);
  if (stopper) {
    view.say.append(el("p", { class: "small", text: `Stopped at ${STATIONS[blockKey(data)].label}: ${stopper.layer === "heuristic"
      ? `attack-like wording found (score ${Number(stopper.score).toFixed(1)}, flag line 1.0).` : `the checker judged it suspicious (${Math.round(stopper.score * 100)}% sure).`}` }));
  }
  const where = data.reached_model ? `answer ${data.enforcement_decision === "allow" ? "delivered" : data.enforcement_decision === "warn" ? "delivered with a warning" : "withheld"}` : `stopped at ${STATIONS[blockKey(data)].label}`;
  view.log.append(el("li", { class: tone }, el("b", { text: run.title }), document.createTextNode(` · ${where} · ${(data.latency_ms / 1000).toFixed(1)} s`)));
  await sleep(REDUCED_MOTION ? 300 : 1900);
  return data;
}

async function onSubmit(event) {
  event.preventDefault();
  showError("");
  const button = $("submit");
  button.disabled = true; button.textContent = "Testing…";
  const defenses = currentDefenses();
  const runs = [{ title: `With protection · ${defenses.name}`, payload: defenses, defenses }];
  if ($("compare").checked) runs.push({ title: "No protection · E0", payload: { name: "E0" }, defenses: {} });
  const view = runView(runs.length);
  $("results").replaceChildren(view.node);
  if (window.innerWidth < 1050) $("results").scrollIntoView({ behavior: "smooth" });
  try {
    const results = [];
    for (const [i, run] of runs.entries()) results.push({ title: run.title, data: await playRun(view, run, i) });
    lastResults = results.reverse();  // show "No protection" first, as before
    renderResults(lastResults);
  } catch (err) {
    $("results").replaceChildren();
    showError(err.message);
  } finally {
    view.stop();
    button.disabled = false; button.textContent = "Run test";
  }
}

function badge(text, cls) { return el("span", { class: `badge ${cls}`, text }); }

function renderResults(results) {
  const root = $("results");
  root.replaceChildren();
  const cols = el("div", { class: "cols" });
  for (const r of results) cols.append(renderResult(r.title, r.data));
  root.append(cols);
  const exportBtn = el("button", { type: "button", class: "btn ghost sm", text: "Download JSON" });
  exportBtn.addEventListener("click", () => download("result.json", JSON.stringify(lastResults, null, 2), "application/json"));
  root.append(el("div", { class: "how-judge" },
    el("span", { text: "Check the answer yourself: does it summarize the document, or do what the hidden text asked?" }), exportBtn));
}

const VERDICT = {
  allow: ["Answer delivered. Nothing flagged.", "No layer noticed anything. That does not prove the document is safe; quiet attacks are often missed."],
  warn: ["Answer delivered, with a warning.", "Something was flagged or cleaned, or a layer could not run. Read the answer with care."],
  block: ["Blocked. No answer delivered.", "A defense stopped the document before the AI answered, so the attack could not work, but you got no summary either."],
};

function verdictOf(d) {
  const unchecked = d.enforcement_decision === "allow" && !d.defenses.heuristic && !d.defenses.classifier;
  const [head, body] = unchecked
    ? ["Answer delivered. Nothing checked it.", d.defenses.structural ? "Only the safer instructions were used. Nothing scans the document, so judge the answer yourself." : "No protection at all: whatever the document says goes straight to the AI."]
    : VERDICT[d.enforcement_decision];
  return { tone: unchecked ? "unchecked" : d.enforcement_decision, head, body };
}

function renderResult(title, d) {
  const { tone, head, body } = verdictOf(d);
  const outer = el("article", { class: `result ${tone}` });
  const sym = { allow: "✓", warn: "!", block: "✕", unchecked: "–" }[tone];
  outer.append(el("div", { class: "result-head" }, el("span", { class: "v-icon", text: sym }),
    el("div", {}, el("div", { class: "cfg", text: title }), el("p", { class: "verdict", text: head }), el("p", { class: "verdict-sub", text: body }))));
  const card = el("div", { class: "result-body" });
  outer.append(card);
  const badges = el("div", { class: "badges" });
  badges.append(badge(d.enforcement_decision.toUpperCase(), d.enforcement_decision));
  badges.append(d.model.is_mock ? badge("MOCK MODEL", "mock") : badge(`REAL: ${d.model.name}`, "real"));
  badges.append(badge(d.reached_model ? "reached model" : "blocked before model", d.reached_model ? "" : "block"));
  card.append(badges);
  for (const w of d.warnings || []) card.append(el("div", { class: "note", text: w }));

  const meters = el("div", { class: "gauges" });
  const heur = d.detections.find((x) => x.layer === "heuristic");
  const clf = d.detections.find((x) => x.layer === "classifier");
  if (heur && heur.status === "evaluated") {
    meters.append(gauge({ label: "Word-rule score", value: Math.min(heur.score / 3, 1), tick: 1 / 3,
      text: heur.score.toFixed(1), sub: "mark = flag line 1.0", kind: heur.flagged ? "bad" : "good" }));
  }
  if (clf && clf.status === "evaluated") {
    meters.append(gauge({ label: `AI checker: ${clf.flagged ? "suspicious" : "clean"}`, value: clf.score,
      text: `${Math.round(clf.score * 100)}%`, sub: "how sure it is", kind: clf.flagged ? "bad" : "good" }));
  }
  const on = [d.defenses.heuristic, d.defenses.classifier, d.defenses.structural].filter(Boolean).length;
  meters.append(gauge({ label: "Layers on", value: on / 3, text: `${on}/3`, sub: "L1 · L2 · L3", kind: "mid" }));
  meters.append(gauge({ label: "Time", value: Math.min(d.latency_ms / 20000, 1), text: `${(d.latency_ms / 1000).toFixed(1)}s`,
    sub: `${d.model_calls} model call${d.model_calls === 1 ? "" : "s"}`, kind: "warn" }));
  card.append(meters);

  card.append(el("h4", { text: "Step by step" }), timeline(d));
  card.append(el("h4", { text: "The AI's answer" }));
  card.append(el("pre", { class: `summary${d.summary === null ? " blocked" : ""}`, text: d.summary === null ? `No answer: blocked by ${d.blocked_by}.` : d.summary }));

  const details = el("details", { class: "tech" }, el("summary", { text: "Technical details" }));
  if (d.detections.length) {
    const table = el("table", { class: "data" });
    table.append(rowOf(["layer", "status", "flagged", "score", "policy action", "explanation"], "th"));
    for (const det of d.detections) {
      const tr = rowOf([det.layer, det.status, String(det.flagged), det.score ?? "-", det.policy_action, det.explanation], "td");
      tr.lastChild.className = "wrap";
      table.append(tr);
    }
    details.append(table);
    const rules = d.detections.flatMap((x) => x.matched_rules.map((m) => `${m.rule_id} (weight ${m.weight}, ${m.spans.length}×): ${m.description}`));
    if (rules.length) details.append(el("div", { class: "small", text: "Matched rules: " + rules.join(" | ") }));
  }
  if (d.output_validation) details.append(el("div", { class: "small", text: `Output validation: ${d.output_validation.outcome}. ${d.output_validation.explanation}` }));
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
  return outer;
}

function timeline(d) {
  const list = el("ol", { class: "timeline" });
  const step = (icon, sym, title, text) => {
    const li = el("li", { class: icon === "off" ? "dim" : "" }, el("span", { class: `icon ${icon}`, text: sym }),
      el("div", {}, el("b", { text: title }), document.createTextNode(` ${text}`)));
    li.style.animationDelay = `${0.15 + list.children.length * 0.16}s`;
    list.append(li);
  };
  const action = { blocked: "The document was blocked.", sanitized: "The suspicious lines were cut out before the AI saw them.",
    flagged_only: "Only flagged (a warning), not stopped.", ignored_error: "The failure was ignored and processing continued.", none: "" };
  step("info", "i", "Document received.", `${$("doc").value.length.toLocaleString()} characters, treated as untrusted.`);
  for (const [layer, label] of [["heuristic", "L1 Word rules:"], ["classifier", "L2 AI checker:"]]) {
    const det = d.detections.find((x) => x.layer === layer);
    if (!d.defenses[layer]) { step("off", "–", label, "off."); continue; }
    if (!det) { step("off", "–", label, "skipped; an earlier layer already blocked the document."); continue; }
    if (det.status !== "evaluated") { step("warn", "!", label, `could not run. ${action[det.policy_action]}`); continue; }
    if (det.flagged) {
      const why = layer === "heuristic" ? `attack-like wording found (score ${det.score}, flag line 1.0).` : `judged it suspicious (${Math.round(det.score * 100)}% sure).`;
      step(det.policy_action === "blocked" ? "block" : "warn", "!", label, `${why} ${action[det.policy_action]}`);
    } else {
      step("ok", "✓", label, layer === "heuristic" ? "no known attack wording found." : `judged it clean (${Math.round(det.score * 100)}% sure).`);
    }
  }
  if (!d.defenses.structural) step("off", "–", "L3 Safer instructions:", "off; the document went straight into the AI's instructions.");
  else if (!d.reached_model) step("off", "–", "L3 Safer instructions:", "not needed; the document never reached the AI.");
  else step("ok", "✓", "L3 Safer instructions:", `on; wrapped in markers and labelled as data only (wording ${d.defenses.structural_variant}).`);
  if (d.reached_model) step("info", "AI", "Model answered:", `${d.model.is_mock ? "mock stand-in (not a real AI)" : d.model.name}, in ${((d.timings_ms.generation || 0) / 1000).toFixed(1)} s.`);
  else step("block", "✕", "Model:", "never reached; no answer was generated.");
  if (d.output_validation) step(d.output_validation.outcome === "indicator_matched" ? "block" : "ok", "✓", "L4 Output check:", d.output_validation.explanation);
  else step("off", "–", "L4 Output check:", "off (needs the attack's goal, known only in experiments).");
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

function kpi({ label, value, sub, tone, ring }) {
  const val = el("div", { class: "k-val", text: "0" });
  const box = el("div", { class: `kpi ${tone}` }, el("div", {}, el("div", { class: "k-label", text: label }), val, el("div", { class: "k-sub", text: sub })));
  if (ring !== undefined) {
    const color = { danger: "var(--danger)", success: "var(--success)", primary: "var(--primary)" }[tone] || "var(--text-3)";
    const fg = svg("circle", { class: "fg", cx: "27", cy: "27", r: "22", stroke: color, "stroke-dasharray": "0 200", pathLength: "100" });
    box.append(svg("svg", { class: "ring-mini", viewBox: "0 0 54 54", "aria-hidden": "true" }, svg("circle", { class: "bg", cx: "27", cy: "27", r: "22" }), fg));
    afterPaint(() => fg.setAttribute("stroke-dasharray", `${Math.max(0, Math.min(100, ring)).toFixed(1)} 200`));
  }
  typeof value === "number" ? countUp(val, value) : (val.textContent = value);
  return box;
}

function renderOverview(rows, by) {
  const e0 = by.E0, e2 = by.E2, e3 = by.E3;
  const a0 = pct(e0.asr_k, e0.asr_n), a2 = pct(e2.asr_k, e2.asr_n);
  $("ov-kpis").replaceChildren(
    kpi({ label: "Attacks that worked, no defense", value: a0, sub: `${e0.asr_k} of ${e0.asr_n} attempts`, tone: "danger", ring: a0 }),
    kpi({ label: "With safer instructions (E2)", value: a2, sub: `${e2.asr_k} of ${e2.asr_n} · ${(a0 - a2).toFixed(1)} points lower`, tone: "primary", ring: a2 }),
    kpi({ label: "Usable summaries with it", value: pct(e2.usable_k, e2.usable_n), sub: `vs ${fmtPct(pct(e0.usable_k, e0.usable_n))} with no defense`, tone: "success", ring: pct(e2.usable_k, e2.usable_n) }),
    kpi({ label: "AI checker caught", value: `${e3.detect_k}/${e3.detect_n}`, sub: "attacked documents flagged (E3)", tone: "", ring: pct(e3.detect_k, e3.detect_n) }),
  );
  const chart = $("ov-chart");
  chart.replaceChildren();
  for (const r of rows) {
    chart.append(el("div", { class: "cfg-row" }, el("div", { class: "name", text: `${r.config} · ${shortPreset(r.config)}` }),
      el("div", {}, bar("", r.asr_k, r.asr_n, r.config === "E2" ? "mid" : "bad"))));
  }
}

function renderFindings() {
  if (!findings) return;
  document.querySelectorAll(".seg").forEach((b) => b.classList.toggle("active", b.dataset.model === findingsModel));
  const rows = findings.comparison.filter((r) => r.model === findingsModel);
  const by = Object.fromEntries(rows.map((r) => [r.config, r]));
  const e0 = by.E0, e2 = by.E2, e5 = by.E5;

  renderOverview(rows, by);

  const resisted = e0.asr_n - e0.asr_k;
  $("f-gauges").replaceChildren(
    gauge({ label: "Usable summaries, no defense", value: pct(e0.usable_k, e0.usable_n) / 100, text: fmtPct(pct(e0.usable_k, e0.usable_n)),
      sub: `${e0.usable_k} of ${e0.usable_n} attacked documents`, kind: "good" }),
    gauge({ label: "Usable summaries, safer instructions", value: pct(e2.usable_k, e2.usable_n) / 100, text: fmtPct(pct(e2.usable_k, e2.usable_n)),
      sub: `${e2.usable_k} of ${e2.usable_n} attacked documents`, kind: "good" }),
    gauge({ label: "Ignored by the model itself", value: resisted / e0.asr_n, text: fmtPct(pct(resisted, e0.asr_n)),
      sub: `${resisted} of ${e0.asr_n} attacks failed with no defense`, kind: "mid" }),
    gauge({ label: "False alarms, all layers on", value: pct(e5.fpr_k, e5.fpr_n) / 100, text: fmtPct(pct(e5.fpr_k, e5.fpr_n)),
      sub: `${e5.fpr_k} of ${e5.fpr_n} clean documents (E5)`, kind: "bad" }),
  );

  const list = $("f-configs");
  list.replaceChildren();
  for (const r of rows) {
    const facts = [
      r.fpr_n ? `false alarms ${r.fpr_k}/${r.fpr_n}` : "no detector, so no false alarms possible",
      r.detect_n ? `detected ${r.detect_k}/${r.detect_n}` : null,
      `${(r.latency_mean_ms / 1000).toFixed(1)} s per answer`,
      r.asr_unresolved ? `${r.asr_unresolved} unresolved` : null,
    ].filter(Boolean);
    list.append(el("div", { class: "cfg-row" },
      el("div", {}, el("div", { class: "name", text: `${r.config} · ${shortPreset(r.config)}` }), el("div", { class: "desc", text: PRESET_TEXT[r.config] || "" })),
      el("div", {}, bar("attack worked", r.asr_k, r.asr_n, "bad"), bar("usable summary", r.usable_k, r.usable_n, "good"),
        el("div", { class: "facts", text: facts.join(" · ") }))));
  }

  const parts = [["success->fail", "var(--success)", "stopped"], ["success->success", "var(--danger)", "still worked"],
    ["fail->success", "var(--warn)", "new success"], ["fail->fail", "var(--track)", "failed both times"], ["unresolved", "var(--text-3)", "unresolved"]];
  const tr = $("f-transitions");
  tr.replaceChildren(el("div", { class: "legend" },
    ...parts.map(([, c, t]) => { const i = el("i"); i.style.background = c; return el("span", {}, i, document.createTextNode(t)); })));
  for (const r of rows) {
    if (r.config === "E0") continue;
    const t = findings.transitions_vs_E0[`${findingsModel}|${r.config}`] || {};
    const total = parts.reduce((s, [k]) => s + (t[k] || 0), 0) || 1;
    const stack = el("div", { class: "stack-bar", role: "img", "aria-label": `${r.config}: stopped ${t["success->fail"] || 0}, new successes ${t["fail->success"] || 0}` });
    for (const [k, c] of parts) {
      const seg = el("div", { title: `${k}: ${t[k] || 0}` }); seg.style.background = c; stack.append(seg);
      afterPaint(() => { seg.style.width = `${(100 * (t[k] || 0)) / total}%`; });
    }
    const stopped = t["success->fail"] || 0, induced = t["fail->success"] || 0;
    tr.append(el("div", { class: "cfg-row" }, el("div", { class: "name", text: `${r.config} · ${shortPreset(r.config)}` }),
      el("div", {}, stack, el("div", { class: "facts", text: stopped || induced
        ? `stopped ${stopped} · let ${induced} new ones through · net ${stopped - induced} fewer successes`
        : "changed nothing: exactly the same outcomes as no defense" }))));
  }

  const cat = $("f-categories");
  cat.replaceChildren();
  const fam = (cfg) => Object.fromEntries(findings.category.filter((c) => c.model === findingsModel && c.config === cfg).map((c) => [c.family, c]));
  const c0 = fam("E0"), c2 = fam("E2");
  const families = Object.keys(c0).sort((a, b) => c0[b].successes / (c0[b].decided || 1) - c0[a].successes / (c0[a].decided || 1));
  for (const f of families) {
    const a = c0[f], b = c2[f] || { successes: 0, decided: 0 };
    cat.append(el("div", { class: "cfg-row" }, el("div", { class: "name", text: prettyFamily(f) }),
      el("div", {}, bar("no defense", a.successes, a.decided, "bad"), bar("safer instr.", b.successes, b.decided, "mid"))));
  }
  cat.append(el("p", { class: "small", text: "Reverse Text is scored only by exact character reversal, so its result is probably an underestimate." }));
}

// ---------- evaluation results (advanced) ----------
async function loadRuns() {
  const root = $("runs");
  root.replaceChildren();
  try {
    const { runs } = await api("/results");
    if (!runs.length) { root.append(el("p", { class: "muted", text: "No saved runs yet. Run an evaluation above or use scripts/run_experiments.py." })); return; }
    const table = el("table", { class: "data" });
    table.append(rowOf(["run", "started", "model", "evidence status", "experiments", ""], "th"));
    for (const r of runs) {
      const open = el("button", { type: "button", class: "btn ghost small-btn", text: "Open" });
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
    const card = el("div", { class: "adv-card" });
    card.append(el("h2", { class: "section-title", text: `Run ${runId}` }));
    card.append(el("div", { class: "note", text: d.metadata.evidence_status }));
    const m = d.metadata;
    card.append(el("div", { class: "muted", text: `model ${m.model.name}; dataset ${m.case_set || "?"} (${m.dataset.n_cases} cases); repetitions ${m.repetitions}; ${d.pending_manual_review} outcome(s) awaiting manual review` }));
    const keys = d.summary.length ? Object.keys(d.summary[0]) : [];
    const table = el("table", { class: "data" });
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

setupBrand();
setupTheme();
setupIntro();
init().catch((err) => showError(`Could not load configuration: ${err.message}`));
