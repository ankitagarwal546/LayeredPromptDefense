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
let lastRun = null;  // the document text and instruction of the test being run (fixed at "Run test")
let lastExtractHidden = [];  // passages the last file upload flagged as hidden (tiny, white or hidden text)
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
  E2v4: "NEW, not evaluated: safer instructions v4 (nonce fence explained to the model plus strict scope binding).",
  E5v2: "NEW, not evaluated: word rules v2, checker prompt v2, safer instructions v4 and the output guard. Designed after the study's results were seen.",
};

function shortPreset(name) {
  return { E0: "no protection", E1: "word rules (block)", E1b: "word rules (clean)", E2: "safer instructions",
    E3: "AI checker", E4: "word rules + safer instr.", E5: "all layers", E2v4: "safer instructions v4 (new)",
    E5v2: "all improved layers (new)" }[name] || "";
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
  const logged = new Set(config.logged_presets || Object.keys(config.presets));
  for (const name of Object.keys(config.presets)) $("preset").append(el("option", { value: name, text: `${name} · ${shortPreset(name)}${logged.has(name) ? "" : " · not evaluated"}` }));
  fillSelect($("p-heuristic"), config.policies.heuristic, (v) => `policy: ${v}`);
  fillSelect($("p-classifier"), config.policies.classifier, (v) => `policy: ${v}`);
  fillSelect($("p-variant"), config.structural_variants, (v) => `prompt wording ${v}`);
  $("preset").value = config.default_defense_preset === "E0" ? "E2" : config.default_defense_preset;
  applyPreset($("preset").value);

  // One option per real model the server offers (LLM_MODEL, then LLM_EXTRA_MODELS); value "real:<name>".
  const real = config.real_model, reals = config.real_models || (real ? [real] : []);
  for (const m of reals) $("model").append(el("option", { value: `real:${m.name}`, text: `Real model: ${m.name} (${m.is_local ? "on this computer" : "remote provider"})` }));
  if (!reals.length) $("model").append(el("option", { value: "real:", text: "Real model (not configured)", disabled: "" }));
  if (config.default_model_mode === "real" && real) $("model").value = `real:${real.name}`;
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
  pill.lastChild.textContent = real ? `${reals.map((m) => m.name).join(" / ")} · ${real.is_local ? "local" : "remote"}` : "real model not configured";
  pill.firstChild.classList.toggle("on", Boolean(real));
  document.querySelectorAll(".nav-item").forEach((item) => item.addEventListener("click", () => switchTab(item.dataset.tab)));
  $("menu-btn").addEventListener("click", () => setNav(!$("app").classList.contains("nav-open")));
  document.querySelectorAll(".seg").forEach((b) => b.addEventListener("click", () => { findingsModel = b.dataset.model; renderFindings(); }));
  $("doc").addEventListener("input", () => { updateCount(); clearExample(); lastExtractHidden = []; });
  $("file").addEventListener("change", onFile);
  $("model").addEventListener("change", updateModelNote);
  $("preset").addEventListener("change", () => applyPreset($("preset").value));
  $("form").addEventListener("submit", onSubmit);
  document.querySelectorAll("#task-chips .task-chip").forEach((c) => c.addEventListener("click", () => { $("instruction").value = c.textContent; syncChips(); }));
  $("instruction").addEventListener("input", syncChips);
  syncChips();
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
  // Mouse parallax: the pointer sets a target tilt; a requestAnimationFrame loop eases toward it (--tilt-x / --tilt-y).
  const tilt = { x: 0, y: 0, tx: 0, ty: 0 };
  $("intro").addEventListener("pointermove", (e) => {
    tilt.tx = (e.clientX / innerWidth - 0.5) * 30;
    tilt.ty = -(e.clientY / innerHeight - 0.5) * 20;
  });
  const ease = () => {
    tilt.x += (tilt.tx - tilt.x) * 0.08;
    tilt.y += (tilt.ty - tilt.y) * 0.08;
    stack.style.setProperty("--tilt-x", `${tilt.x.toFixed(2)}deg`);
    stack.style.setProperty("--tilt-y", `${tilt.y.toFixed(2)}deg`);
    if (!$("intro").classList.contains("hidden")) requestAnimationFrame(ease);
    else setTimeout(() => requestAnimationFrame(ease), 500);
  };
  if (!REDUCED_MOTION) requestAnimationFrame(ease);
  // The nonce shield: a fresh random fence code every few seconds, intercepting the red (hidden) line.
  const shield = document.querySelector(".nonce-shield");
  const relabel = () => {
    $("nonce-label").textContent = `<<<DOCUMENT_${randomHex(8)}>>>`;
    shield.classList.remove("flash"); void shield.offsetWidth; shield.classList.add("flash");
  };
  relabel();
  if (!REDUCED_MOTION) setInterval(() => { if (!$("intro").classList.contains("hidden")) relabel(); }, 2600);

  // Typed line under the button.
  const lines = ["scanning document for hidden orders…", "L1 word rules · L2 AI checker · L3 safer instructions", "75 real attacks · 2 local models · human-reviewed"];
  let li = 0, ci = 0;
  const typed = $("typed");
  const type = () => {
    if ($("intro").classList.contains("hidden")) { setTimeout(type, 1000); return; }  // paused while the dashboard is shown
    const line = lines[li];
    typed.textContent = line.slice(0, ++ci);
    if (ci < line.length) setTimeout(type, 38);
    else setTimeout(() => { ci = 0; li = (li + 1) % lines.length; type(); }, 1800);
  };
  setTimeout(type, 2200);

  // The landing page is always shown on load. Scrolling it sets --p (hero progress, 0..1) and --sp (whole page, 0..1).
  const intro = $("intro"), hero = $("hero");
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  intro.scrollTop = 0;
  intro.addEventListener("scroll", () => {
    const span = hero.offsetHeight - intro.clientHeight, total = intro.scrollHeight - intro.clientHeight;
    intro.style.setProperty("--p", (span > 0 ? Math.min(1, intro.scrollTop / span) : 0).toFixed(3));
    intro.style.setProperty("--sp", (total > 0 ? intro.scrollTop / total : 0).toFixed(3));
    intro.classList.toggle("scrolled", intro.scrollTop > 10);
  }, { passive: true });
  intro.focus({ preventScroll: true });  // so arrow keys, Page Down and Space scroll it too

  // Section headings rise word by word.
  intro.querySelectorAll(".split").forEach((h) => {
    const words = h.textContent.split(" ");
    h.setAttribute("aria-label", h.textContent);
    h.replaceChildren(...words.flatMap((w, i) => {
      const span = el("span", { class: "wd", "aria-hidden": "true", text: w });
      span.style.setProperty("--i", i);
      return i < words.length - 1 ? [span, document.createTextNode(" ")] : [span];
    }));
  });

  // Reveal on scroll, and replay each time an element comes back into view. The KPI and chart animations
  // replay too, by redrawing that part of the overview when it enters the screen.
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      e.target.classList.toggle("in", e.isIntersecting);
      if (e.isIntersecting && (e.target.id === "ov-kpis" || e.target.id === "ov-chart")) drawOverview(e.target.id === "ov-kpis" ? "kpis" : "chart");
    }
  }, { root: intro, threshold: 0.25 });
  intro.querySelectorAll(".reveal, .split, .takeaways, #ov-kpis, #ov-chart, #layer-cards").forEach((n) => io.observe(n));

  intro.querySelectorAll("[data-scroll]").forEach((b) => b.addEventListener("click", () => scrollLanding(b.dataset.scroll)));
  intro.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.goto)));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !intro.classList.contains("hidden") && !e.target.closest("button")) switchTab("summarize");
  });
}

function scrollLanding(id, behavior = "smooth") {
  $("intro").scrollTo({ top: id === "hero" ? 0 : $(id).offsetTop - 50, behavior });
}

// Landing page <-> dashboard.
function landingOpen() { return !$("intro").classList.contains("hidden"); }

function enterDashboard() {
  if (!landingOpen()) return;
  $("intro").classList.add("leaving");
  $("app").classList.remove("hidden");
  setTimeout(() => $("intro").classList.add("hidden"), 600);
}

function openLanding(target) {
  const intro = $("intro");
  intro.classList.remove("hidden");
  $("app").classList.add("hidden");
  afterPaint(() => intro.classList.remove("leaving"));
  scrollLanding(target, "instant");
  intro.focus({ preventScroll: true });
  document.title = "Prompt-Injection Defense Lab";
  setNav(false);
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

const PAGE_TITLES = { summarize: "Test a document", findings: "Results", learn: "How it works", results: "Evaluations" };

function switchTab(name) {
  if (name === "overview") { openLanding("ov-land"); return; }
  enterDashboard();
  document.querySelectorAll(".nav-item").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  // Morph between pages: the old one fades and lifts away, the new one slides in (see .pane-leave / .tabpane).
  const target = $(`tab-${name}`);
  const current = document.querySelector(".tabpane:not(.hidden)");
  const show = () => { for (const pane of Object.keys(PAGE_TITLES)) $(`tab-${pane}`).classList.toggle("hidden", name !== pane); };
  if (current && current !== target && !REDUCED_MOTION) {
    current.classList.add("pane-leave");
    setTimeout(() => { current.classList.remove("pane-leave"); show(); }, 170);
  } else show();
  $("page-title").textContent = PAGE_TITLES[name];
  document.title = `${PAGE_TITLES[name]} · Defense Lab`;
  if (name === "results") loadRuns();
  if (name === "findings" && findings) renderFindings();
  setNav(false);
  window.scrollTo({ top: 0 });
}

function applyPreset(name) {
  const p = config.presets[name];
  $("d-heuristic").checked = p.heuristic; $("p-heuristic").value = p.heuristic_policy;
  $("d-classifier").checked = p.classifier && config.classifier_available; $("p-classifier").value = p.classifier_policy;
  $("d-structural").checked = p.structural; $("p-variant").value = p.structural_variant;
  $("d-output").checked = p.output_validation; $("d-failclosed").checked = p.fail_closed_on_detector_error;
  $("v-heuristic").value = p.heuristic_rules || "v1"; $("v-sanitize").value = p.sanitize_marker || "redacted";
  $("v-classifier").value = p.classifier_prompt || "v1";
  $("d-guard").checked = Boolean(p.runtime_guard); $("p-guard").value = p.runtime_guard_policy || "flag_only";
  $("preset-desc").textContent = PRESET_TEXT[name] || "";
}

function currentDefenses() {
  const d = {
    name: $("preset").value,
    heuristic: $("d-heuristic").checked, heuristic_policy: $("p-heuristic").value,
    classifier: $("d-classifier").checked, classifier_policy: $("p-classifier").value,
    structural: $("d-structural").checked, structural_variant: $("p-variant").value,
    output_validation: $("d-output").checked,
    fail_closed_on_detector_error: $("d-failclosed").checked,
    heuristic_rules: $("v-heuristic").value, sanitize_marker: $("v-sanitize").value,
    classifier_prompt: $("v-classifier").value,
    runtime_guard: $("d-guard").checked, runtime_guard_policy: $("p-guard").value,
  };
  // Say so when the layers no longer match the chosen preset, so results are never shown under a preset's name.
  const preset = config.presets[d.name];
  const needs = { heuristic_policy: "heuristic", heuristic_rules: "heuristic", sanitize_marker: "heuristic", classifier_policy: "classifier",
    classifier_prompt: "classifier", structural_variant: "structural", runtime_guard_policy: "runtime_guard" };
  const relevant = (k) => (needs[k] ? d[needs[k]] : true);
  if (preset && Object.keys(d).some((k) => k !== "name" && relevant(k) && preset[k] !== d[k])) d.name = `${d.name} (custom)`;
  return d;
}

function updateCount() {
  const n = $("doc").value.length, max = config ? config.limits.max_document_chars : 50000;
  $("doc-count").textContent = `${n.toLocaleString()} / ${max.toLocaleString()} characters`;
}

// The model select holds "mock" or "real:<name>".
function chosenModel() {
  const value = $("model").value;
  return value === "mock" ? { mode: "mock", name: null } : { mode: "real", name: value.slice(5) || null };
}

function updateModelNote() {
  const note = $("model-note"), real = config && config.real_model;
  if (chosenModel().mode === "mock") {
    note.textContent = "Not an AI: it copies sentences and obeys obvious \"ignore previous instructions\" lines. Good for seeing how the app works, not for judging AI safety.";
    return;
  }
  note.textContent = real && real.is_local
    ? "Runs on this computer through Ollama (start it with `ollama serve`). Nothing leaves the machine."
    : "Privacy notice: your document text will be sent to the external model provider configured for this app.";
  if (config.classifier_available && config.classifier_model) {
    note.textContent += ` The AI checker (L2) always uses ${config.classifier_model}, whichever model writes the answer.`;
  }
  const lim = config.ui_limits;
  if (lim) note.textContent += ` Answers can be up to ${lim.max_tokens.toLocaleString()} tokens (about ${Math.round(lim.max_tokens * 0.75).toLocaleString()} words); a test gives up after ${lim.timeout_s} s.`;
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
  lastExtractHidden = [];
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
    lastExtractHidden = result.hidden_text || [];
    note.replaceChildren(document.createTextNode(`Extracted ${result.chars.toLocaleString()} characters from the ${result.format.toUpperCase()} file. The text above is exactly what will be sent. ${(result.warnings || []).join(" ")}`));
    if (lastExtractHidden.length) {
      note.append(el("ul", { class: "hidden-list" }, ...lastExtractHidden.map((h) => el("li", {}, el("q", { text: h })))));
    }
    note.classList.toggle("alert", lastExtractHidden.length > 0 || (result.removed_invisible_chars || 0) > 0);
    note.classList.remove("hidden");
  } catch (err) {
    note.classList.add("hidden");
    showError(err.message);
  }
}

// ---------- summarize ----------
// general_task: the instruction may be any task (answer questions, list points, ...), not only "summarize".
async function summarize(defenses) {
  return api("/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_text: lastRun.doc,
      instruction: lastRun.instruction,
      model: chosenModel().mode,
      model_name: chosenModel().name,
      general_task: true,
      include_prompt: true,
      defenses,
    }),
  });
}

function syncChips() {
  document.querySelectorAll("#task-chips .task-chip").forEach((c) => c.classList.toggle("picked", c.textContent === $("instruction").value.trim()));
}

// ---------- live run view ----------
// Walks the document through the layers while the request runs. Steps before the model are paced so they can be
// read; the LLM step waits for the server's real reply, and then every station is coloured from that reply, one by
// one (so where the document stopped, and why, is real, not animation). Stage labels follow the pipeline order; the
// server reports only once it has finished.
const STEP_MS = REDUCED_MOTION ? 120 : 850;
const REVEAL_MS = REDUCED_MOTION ? 30 : 150;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const LOCK_ICON = "M7 11V8a5 5 0 0 1 10 0v3M6 11h12v9H6z";

const STATIONS = {
  doc: { label: "Extract", icon: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5",
    head: "Extract · reading the document", text: "The text is loaded and treated as untrusted: any sentence in it could be a hidden order." },
  heuristic: { label: "L1 Regex", icon: "M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0zM20 20l-4.5-4.5",
    head: "L1 · scanning for attack wording", text: "Word rules look for phrases such as “ignore previous instructions” or “you are now”." },
  classifier: { label: "L2 Classifier", icon: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    head: "L2 · asking the AI checker", text: "A second model reads the document and answers one question: is any of it aimed at the AI?" },
  structural: { label: "L3 Nonce fence", icon: "M8 4H5v16h3M16 4h3v16h-3",
    head: "L3 · fencing the payload with a 16-hex nonce", text: "The document is wrapped in markers with a fresh random code and labelled as data; the task is restated after it." },
  model: { label: "LLM", icon: "M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4", head: "", text: "" },
  output: { label: "L4 Validator", icon: "M4 6h10M4 12h10M4 18h6M15 16l2.5 2.5L22 14",
    head: "L4 · checking against the attack's goal", text: "Experiment scorer: compares the answer with what the attack wanted (only possible when that is known)." },
  guard: { label: "L4 Guard", icon: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
    head: "L4 · checking the answer", text: "Looks for a leaked reference code, links that are not in the document, and language or topic drift." },
  answer: { label: "Answer", icon: "M4 5h16v11H9l-5 4z", head: "", text: "" },
};

function runView(title) {
  const status = el("span", { class: "run-status running", text: "RUNNING" });
  const clock = el("span", { class: "run-clock", text: "0.0 s" });
  const conduit = el("div", { class: "conduit" });
  const xray = el("div", { class: "doc-xray scanning", "aria-hidden": "true" }, el("pre", { class: "doc-text", text: lastRun.doc.slice(0, 4000) }), el("span", { class: "xray-line" }));
  const scene = el("div", { class: "scene-box", "aria-hidden": "true" });
  const say = el("div", { class: "say" });
  const micro = el("div", { class: "micro" });
  const log = el("ul", { class: "run-log" });
  const node = el("div", { class: "card run", role: "status", "aria-live": "polite" },
    el("div", { class: "run-head" }, el("h3", { text: title }), el("div", { class: "run-meta" }, status, clock)), conduit,
    el("div", { class: "stage" }, xray, el("div", { class: "stage-right" }, scene, say, micro)), log);
  const started = performance.now();
  const timer = setInterval(() => { clock.textContent = `${((performance.now() - started) / 1000).toFixed(1)} s`; }, 100);
  return { node, status, conduit, xray, scene, say, micro, log, stations: [], segments: [], stop: () => clearInterval(timer) };
}

function setTrack(view, keys) {
  const n = keys.length;
  const lines = svg("svg", { class: "conduit-lines", viewBox: "0 0 100 10", preserveAspectRatio: "none", "aria-hidden": "true" });
  view.segments = [];
  for (let i = 0; i < n - 1; i++) {
    const x1 = ((i + 0.5) / n) * 100, x2 = ((i + 1.5) / n) * 100;
    const base = svg("line", { x1, y1: 5, x2, y2: 5, class: "seg-base", "vector-effect": "non-scaling-stroke" });
    const flow = svg("line", { x1, y1: 5, x2, y2: 5, class: "seg-flow", "vector-effect": "non-scaling-stroke" });
    lines.append(base, flow);
    view.segments.push(flow);
  }
  const packet = el("div", { class: "packet" }, el("i"), el("i"), el("i"));
  const nodes = el("div", { class: "conduit-nodes" });
  nodes.style.setProperty("--n", n);
  view.stations = keys.map((k) => {
    const s = el("div", { class: `station st-${k}` },
      el("span", { class: "st-dot" }, el("span", { class: "orbit" }), svg("svg", { viewBox: "0 0 24 24" }, svg("path", { d: STATIONS[k].icon }))),
      el("span", { class: "st-label", text: STATIONS[k].label }));
    nodes.append(s);
    return s;
  });
  view.conduit.replaceChildren(lines, nodes, packet);
  view.conduit.style.setProperty("--n", n);
  view.packet = packet;
}

function moveTo(view, i, { flowing = true } = {}) {
  const n = view.stations.length;
  view.packet.style.left = `${((i + 0.5) / n) * 100}%`;
  view.stations.forEach((s, j) => { s.classList.toggle("now", j === i); s.classList.toggle("passed", j < i); });
  view.segments.forEach((seg, j) => {
    seg.classList.toggle("done", j < i - 1 || (!flowing && j < i));
    seg.classList.toggle("active", flowing && j === i - 1);
  });
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
    case "classifier": return [miniPage(), el("div", { class: "bot" }, el("i")), el("div", { class: "bubble", text: "aimed at the AI?" })];
    case "structural": return [el("div", { class: "fence" }, miniPage()), el("div", { class: "fence-tag", text: `<<<DOCUMENT_${randomHex(4)}…>>>` })];
    case "model": return [el("div", { class: "chip" }, el("i")), el("div", { class: "wave" }, ...Array.from({ length: 9 }, (_, i) => { const b = el("i"); b.style.setProperty("--k", i); return b; }))];
    case "output": case "guard": return [el("div", { class: "ans" }, ...[0, 1, 2].map(() => el("div", {}, el("i"), el("b", { text: "✓" }))))];
    default: return [el("div", { class: `ball ${tone}`, text: { allow: "✓", warn: "!", block: "✕", unchecked: "–" }[tone] })];
  }
}

function randomHex(bytes) {
  const a = new Uint8Array(bytes);
  (window.crypto || {}).getRandomValues ? crypto.getRandomValues(a) : a.forEach((_, i) => { a[i] = Math.floor(Math.random() * 256); });
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

function narrate(view, key, head, text, tone = "") {
  view.scene.className = `scene-box s-${key}`;
  view.scene.replaceChildren(...sceneFor(key, tone));
  view.say.replaceChildren(el("h4", { text: head }), el("p", { text }));
}

function blockKey(d) {
  return { heuristic: "heuristic", classifier: "classifier", output_validation: "output", runtime_guard: "guard" }[d.blocked_by] || "answer";
}

function stationState(key, d) {
  if (key === "heuristic" || key === "classifier") {
    const det = d.detections.find((x) => x.layer === key);
    if (!det) return "skip";
    if (det.status !== "evaluated") return "warn";
    return !det.flagged ? "ok" : det.policy_action === "blocked" ? "block" : "warn";
  }
  if (key === "structural") return d.reached_model ? "applied" : "skip";  // a prompt change, not a check
  if (key === "model") return d.reached_model ? "ok" : "skip";
  if (key === "output") return !d.output_validation ? "skip" : d.output_validation.outcome === "indicator_matched" ? "block" : "ok";
  if (key === "guard") return !d.runtime_guard ? "skip" : !d.runtime_guard.flagged ? "ok" : d.runtime_guard.policy_action === "withheld" ? "block" : "warn";
  if (key === "answer") return { block: "block", warn: "warn" }[d.enforcement_decision] || "ok";
  return "ok";
}

// Rotating status lines while the server works (in pipeline order; not live telemetry).
function microSteps(d) {
  const steps = [];
  if (d.classifier) steps.push("L2 · local checker model is reading the document…");
  if (d.structural) steps.push(`Fencing payload with 16-hex nonce <<<DOCUMENT_${randomHex(8)}>>>…`);
  steps.push(`Awaiting local ${chosenModel().name || "model"} inference…`, "The model is writing its answer (long tasks on 8B can take a minute)…");
  return steps;
}

async function playRun(view, run) {
  const d = run.defenses;
  const keys = ["doc", ...["heuristic", "classifier", "structural"].filter((k) => d[k]), "model",
    ...(d.output_validation ? ["output"] : []), ...(d.runtime_guard ? ["guard"] : []), "answer"];
  setTrack(view, keys);
  const texts = {
    model: [`LLM · “${lastRun.instruction}”`, d.structural ? "The model gets your task plus the fenced document and works on it."
      : "The document goes straight into the model's instructions, so a hidden order looks just like yours."],
  };
  const say = (k) => texts[k] || [STATIONS[k].head, STATIONS[k].text];

  let data = null, failure = null, settled = false;
  const request = summarize(run.payload).then((r) => { data = r; }, (e) => { failure = e; }).finally(() => { settled = true; });
  const modelAt = keys.indexOf("model");
  for (let i = 0; i <= modelAt; i++) {
    moveTo(view, i);
    narrate(view, keys[i], ...say(keys[i]));
    await sleep(STEP_MS);
    if (failure) throw failure;
    if (data && !data.reached_model && keys.indexOf(blockKey(data)) <= i) break;  // stopped before the model
  }
  if (!settled) {
    view.stations[modelAt].classList.add("busy");
    const steps = microSteps(d);
    let k = 0;
    const tick = () => { view.micro.replaceChildren(el("span", { class: "micro-step", text: steps[k % steps.length] })); k++; };
    tick();
    const rotate = setInterval(tick, 1800);
    await request;
    clearInterval(rotate);
    view.stations[modelAt].classList.remove("busy");
  }
  view.micro.replaceChildren();
  if (failure) throw failure;
  for (const k of ["output", "guard"]) {
    if (data.reached_model && keys.includes(k)) {
      moveTo(view, keys.indexOf(k));
      narrate(view, k, ...say(k));
      await sleep(STEP_MS * 0.7);
    }
  }

  // Verdict cascade: reveal each station's real state in order, then where the document ended up.
  const { tone, head, body } = verdictOf(data);
  const stopAt = keys.indexOf(blockKey(data));
  const last = stopAt < 0 ? keys.length - 1 : stopAt;
  view.xray.classList.remove("scanning");
  for (const [j, k] of keys.entries()) {
    if (j > last && stationState(k, data) !== "skip") continue;
    const state = stationState(k, data);
    view.stations[j].classList.remove("now", "busy");
    view.stations[j].classList.add("final", state);
    if (state === "block") view.stations[j].querySelector(".st-dot").append(svg("svg", { class: "lock", viewBox: "0 0 24 24" }, svg("path", { d: LOCK_ICON })));
    if (j <= last) moveTo(view, j, { flowing: false });
    await sleep(REVEAL_MS);
  }
  keys.forEach((k, j) => { if (!view.stations[j].classList.contains("final")) view.stations[j].classList.add("final", "skip"); });
  view.packet.classList.add(tone);
  view.status.className = `run-status ${data.enforcement_decision}`;
  view.status.textContent = data.blocked_by ? `BLOCK · ${STATIONS[blockKey(data)].label}` : data.enforcement_decision.toUpperCase();
  if (data.blocked_by) view.node.classList.add("tripped");
  narrate(view, "result", head, body, tone);
  if (data.blocked_by) view.say.append(el("p", { class: "small", text: `Stopped at ${STATIONS[blockKey(data)].label}: ${blockReason(data)}` }));
  const where = data.reached_model ? `answer ${data.enforcement_decision === "allow" ? "delivered" : data.enforcement_decision === "warn" ? "delivered with a warning" : "withheld"}` : `stopped at ${STATIONS[blockKey(data)].label}`;
  view.log.append(el("li", { class: tone }, el("b", { text: run.title }), document.createTextNode(` · ${where} · ${(data.latency_ms / 1000).toFixed(1)} s`)));
  return data;
}

// One-line, plain-language reason for a blocked result, from what the blocking layer reported.
function blockReason(d) {
  if (d.blocked_by === "output_validation") return "the answer matched what the attack wanted, so it was withheld.";
  if (d.blocked_by === "runtime_guard") return `the output guard found: ${(d.runtime_guard?.findings || []).map((f) => f.detail).join("; ") || "a problem"}.`;
  const det = d.detections.find((x) => x.layer === d.blocked_by);
  if (!det) return "a layer stopped it.";
  const name = det.layer === "heuristic" ? "L1 word rules" : "L2, the AI checker,";
  if (det.status !== "evaluated") return `${name} could not run, and “Block if a detector fails” is on.`;
  return det.layer === "heuristic"
    ? `the word rules found attack-like wording (score ${Number(det.score).toFixed(1)}; the block line is 1.0).`
    : `the AI checker judged it suspicious (${Math.round(det.score * 100)}% sure)${det.explanation ? `: “${det.explanation}”` : "."}`;
}

// The "Why it was blocked" box: the reason, the evidence the layer gave, and a way to run the test again.
function whyBlocked(d) {
  const box = el("div", { class: "why" }, el("h5", {}, svg("svg", { class: "why-lock", viewBox: "0 0 24 24" }, svg("path", { d: LOCK_ICON })), document.createTextNode("Why it was blocked")));
  const det = d.detections.find((x) => x.layer === d.blocked_by);
  box.append(el("p", { text: `Stopped at ${STATIONS[blockKey(d)].label}: ${blockReason(d)}` }));
  if (det && det.status === "evaluated" && det.layer === "heuristic") {
    const list = el("ul");
    for (const m of det.matched_rules) {
      const quotes = m.spans.slice(0, 2).map(([a, b]) => lastRun.doc.slice(a, b).trim()).filter(Boolean)
        .map((s) => el("q", { text: s.length > 120 ? `${s.slice(0, 120)}…` : s }));
      list.append(el("li", {}, el("b", { text: m.description }), document.createTextNode(` (weight ${m.weight}) `), ...quotes));
    }
    box.append(el("p", { text: "Wording it matched in your document (also highlighted in the document card above):" }), list,
      el("p", { text: "Word rules only look at wording, so a document that talks about attacks can match without being one." }));
  } else if (det && det.status === "evaluated") {
    box.append(el("p", { text: `The checker (${det.model_name || "a model"}) is itself a small AI and makes mistakes. Documents full of ordinary instructions, such as exam questions, code or how-to steps, can look like orders to it. In the study the 1B checker wrongly flagged 2 of 50 clean documents. Checker prompt v2 (Customize layers) separates reader exercises from AI-directed text.` }));
  }
  if (!det && d.blocked_by !== "runtime_guard") return box;
  const fix = d.blocked_by === "runtime_guard"
    ? { label: "Run again with the guard on warn only", apply: () => { $("p-guard").value = "flag_only"; } }
    : det.status !== "evaluated"
      ? { label: "Run again, don't block on errors", apply: () => { $("d-failclosed").checked = false; } }
      : { label: "Run again with this layer on warn only", apply: () => { $(det.layer === "heuristic" ? "p-heuristic" : "p-classifier").value = "flag_only"; } };
  const again = el("button", { type: "button", class: "btn sm", text: fix.label });
  again.addEventListener("click", () => {
    fix.apply();
    document.querySelector("#form details.more fieldset").closest("details").open = true;
    $("form").requestSubmit();
  });
  box.append(el("p", { text: "If you trust this document, you can run it again with this layer only warning instead of blocking: the AI then answers, and the warning stays visible." }),
    el("div", { class: "row" }, again));
  return box;
}

async function onSubmit(event) {
  event.preventDefault();
  showError("");
  lastRun = { doc: $("doc").value, instruction: $("instruction").value.trim() || "Summarize this document.", hidden: lastExtractHidden };
  const button = $("submit");
  button.disabled = true; button.textContent = "Testing…";
  $("form").classList.add("busy");
  const defenses = currentDefenses();
  const runs = [{ title: `Defended · ${defenses.name}`, payload: defenses, defenses }];
  if ($("compare").checked) runs.unshift({ title: "Undefended · E0", payload: { name: "E0" }, defenses: {} });
  const views = runs.map((r) => runView(r.title));
  const arena = el("div", { class: runs.length > 1 ? "arena" : "arena single" }, ...views.map((v) => v.node));
  $("results").replaceChildren(arena);
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    // Both runs start together so their animations are synchronized; the server may still process them in turn.
    const data = await Promise.all(runs.map((run, i) => playRun(views[i], run)));
    await sleep(REDUCED_MOTION ? 200 : 1400);
    lastResults = runs.map((run, i) => ({ title: run.title, data: data[i] }));
    renderResults(lastResults);
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    $("results").replaceChildren();
    showError(err.message);
  } finally {
    views.forEach((v) => v.stop());
    $("form").classList.remove("busy");
    button.disabled = false; button.textContent = "Run test";
  }
}

// ---------- document card with highlights, prompt inspector ----------
function highlighted(text, ranges) {
  const merged = [];
  for (const r of [...ranges].sort((a, b) => a.start - b.start)) {
    const prev = merged[merged.length - 1];
    if (prev && r.start <= prev.end) { prev.end = Math.max(prev.end, r.end); prev.kinds.add(r.kind); prev.titles.add(r.title); }
    else merged.push({ start: r.start, end: r.end, kinds: new Set([r.kind]), titles: new Set([r.title]) });
  }
  const nodes = [];
  let cursor = 0;
  for (const m of merged) {
    if (m.start > cursor) nodes.push(document.createTextNode(text.slice(cursor, m.start)));
    const mark = document.createElement("mark");
    mark.className = [...m.kinds].join(" ");
    mark.title = [...m.titles].join("; ");
    mark.textContent = text.slice(m.start, m.end);
    nodes.push(mark);
    cursor = m.end;
  }
  if (cursor < text.length) nodes.push(document.createTextNode(text.slice(cursor)));
  return nodes;
}

function documentCard(results) {
  const ranges = [];
  for (const r of results) {
    const det = r.data.detections.find((x) => x.layer === "heuristic");
    for (const m of det ? det.matched_rules : []) for (const [start, end] of m.spans) ranges.push({ start, end, kind: "rule", title: `L1: ${m.description}` });
  }
  const lower = lastRun.doc.toLowerCase();
  for (const h of lastRun.hidden || []) {
    const probe = h.replace(/…$/, "").slice(0, 80).toLowerCase();
    const at = probe ? lower.indexOf(probe) : -1;
    if (at >= 0) ranges.push({ start: at, end: at + probe.length, kind: "hidden", title: "Looks hidden from a human reader (tiny, white or hidden text)" });
  }
  const legend = el("div", { class: "legend" }, el("span", {}, el("i", { class: "sw rule" }), document.createTextNode("L1 word-rule match")),
    el("span", {}, el("i", { class: "sw hidden-sw" }), document.createTextNode("hidden text in the file")));
  const pre = el("pre", { class: "doc-text full" }, ...highlighted(lastRun.doc, ranges));
  const details = el("details", { class: "section doc-card" }, el("summary", { text: `Your document${ranges.length ? ` · ${ranges.length} highlighted passage(s)` : " · nothing highlighted"}` }), legend, pre);
  details.open = ranges.length > 0;
  return details;
}

// Colour-coded view of the exact prompt the server sent (system message, nonce markers, untrusted payload, task).
function promptInspector(d) {
  if (!d.prompt) return null;
  const seg = (cls, text) => el("span", { class: `pp ${cls}`, text });
  const system = el("pre", { class: "prompt-pre" });
  const canaryAt = d.prompt.system.indexOf("\n\nConfidential reference code");
  if (canaryAt >= 0) system.append(seg("sys", d.prompt.system.slice(0, canaryAt)), seg("canary", d.prompt.system.slice(canaryAt)));
  else system.append(seg("sys", d.prompt.system));
  const user = el("pre", { class: "prompt-pre" });
  const markers = [...d.prompt.user.matchAll(/<<<(?:END_)?[A-Z_]+_[0-9a-f]{16}>>>/g)];
  if (markers.length >= 2) {
    const [open, close] = [markers[0], markers[markers.length - 1]];
    const u = d.prompt.user;
    user.append(seg("task", u.slice(0, open.index)), seg("nonce", open[0]), seg("payload", u.slice(open.index + open[0].length, close.index)),
      seg("nonce", close[0]), seg("task restate", u.slice(close.index + close[0].length)));
  } else {
    const split = d.prompt.user.indexOf("\n\n");
    user.append(seg("task", split >= 0 ? d.prompt.user.slice(0, split + 2) : ""), seg("payload", split >= 0 ? d.prompt.user.slice(split + 2) : d.prompt.user));
  }
  const key = el("div", { class: "legend" }, ...[["sys", "system message"], ["nonce", "nonce markers"], ["payload", "untrusted document"], ["task", "your task / restatement"], ["canary", "guard reference code"]]
    .map(([c, label]) => el("span", {}, el("i", { class: `sw pp-${c}` }), document.createTextNode(label))));
  return el("details", { class: "tech prompt-drawer" }, el("summary", { text: "Inspect constructed prompt" }),
    el("div", { class: "drawer-body" }, key, el("h6", { text: "System message" }), system, el("h6", { text: "User message" }), user));
}

function badge(text, cls) { return el("span", { class: `badge ${cls}`, text }); }

function renderResults(results) {
  const root = $("results");
  root.replaceChildren(documentCard(results));
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
  block: ["Blocked. No answer delivered.", "A layer stopped this document. If it held an attack, the attack could not work; if it is a normal document, this is a false alarm. See why below."],
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
  if (d.blocked_by) card.append(whyBlocked(d));
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

  if (d.runtime_guard && d.runtime_guard.flagged && d.blocked_by !== "runtime_guard") {
    card.append(el("div", { class: "note guard-note" }, el("b", { text: "Output guard warning: " }),
      document.createTextNode(d.runtime_guard.findings.map((f) => f.detail).join("; "))));
  }
  card.append(el("h4", { text: "Step by step" }), timeline(d));
  card.append(el("h4", { text: "The AI's answer" }), el("p", { class: "task-line" }, document.createTextNode("Task: "), el("b", { text: lastRun.instruction })));
  card.append(el("pre", { class: `summary${d.summary === null ? " blocked" : ""}`,
    text: d.summary === null ? `No answer. Stopped at ${STATIONS[blockKey(d)].label}: ${blockReason(d)}` : d.summary }));

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
  const inspector = promptInspector(d);
  if (inspector) card.append(inspector);
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
  else step("applied", "+", "L3 Safer instructions: applied.", `The document was wrapped in markers and labelled as data only (wording ${d.defenses.structural_variant}). This changes what the AI is told; it does not check the document.`);
  if (d.reached_model) step("info", "AI", "Model answered:", `${d.model.is_mock ? "mock stand-in (not a real AI)" : d.model.name}, in ${((d.timings_ms.generation || 0) / 1000).toFixed(1)} s.`);
  else step("block", "✕", "Model:", "never reached; no answer was generated.");
  if (d.output_validation) step(d.output_validation.outcome === "indicator_matched" ? "block" : "ok", "✓", "L4 Output check:", d.output_validation.explanation);
  else if (!d.runtime_guard) step("off", "–", "L4 Output check:", "off (needs the attack's goal, known only in experiments).");
  if (d.runtime_guard) {
    const g = d.runtime_guard;
    step(!g.flagged ? "ok" : g.policy_action === "withheld" ? "block" : "warn", g.flagged ? "!" : "✓", "L4 Output guard:",
      g.flagged ? `${g.findings.map((f) => f.detail).join("; ")}. ${g.policy_action === "withheld" ? "The answer was withheld." : "Only flagged."}`
        : "no leaked code, no unexpected links, no language or topic drift found.");
  }
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

// Redraw one part of the landing overview ("kpis" or "chart"), which replays its animation.
function drawOverview(part) {
  if (!findings) return;
  const rows = findings.comparison.filter((r) => r.model === findingsModel);
  renderOverview(rows, Object.fromEntries(rows.map((r) => [r.config, r])), part);
}

function renderOverview(rows, by, part = "both") {
  const e0 = by.E0, e2 = by.E2, e3 = by.E3;
  const a0 = pct(e0.asr_k, e0.asr_n), a2 = pct(e2.asr_k, e2.asr_n);
  if (part !== "chart") $("ov-kpis").replaceChildren(
    kpi({ label: "Attacks that worked, no defense", value: a0, sub: `${e0.asr_k} of ${e0.asr_n} attempts`, tone: "danger", ring: a0 }),
    kpi({ label: "With safer instructions (E2)", value: a2, sub: `${e2.asr_k} of ${e2.asr_n} · ${(a0 - a2).toFixed(1)} points lower`, tone: "primary", ring: a2 }),
    kpi({ label: "Usable summaries with it", value: pct(e2.usable_k, e2.usable_n), sub: `vs ${fmtPct(pct(e0.usable_k, e0.usable_n))} with no defense`, tone: "success", ring: pct(e2.usable_k, e2.usable_n) }),
    kpi({ label: "AI checker caught", value: `${e3.detect_k}/${e3.detect_n}`, sub: "attacked documents flagged (E3)", tone: "", ring: pct(e3.detect_k, e3.detect_n) }),
  );
  if (part === "kpis") return;
  const chart = $("ov-chart");
  chart.replaceChildren();
  rows.forEach((r, i) => {
    const row = el("div", { class: "cfg-row" }, el("div", { class: "name", text: `${r.config} · ${shortPreset(r.config)}` }),
      el("div", {}, bar("", r.asr_k, r.asr_n, r.config === "E2" ? "mid" : "bad")));
    row.style.setProperty("--i", i);
    chart.append(row);
  });
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
