/* CLEETS-CHAT static site: the Python question-answering code (docs/py/*.py) runs in the
   browser through Pyodide against a JSON snapshot of the knowledge-graph indexes
   (docs/data/kg_snapshot.json), both produced by build_site.py. */
"use strict";

const REPO_URL = (() => {
  const meta = document.querySelector('meta[name="repo"]')?.content;
  if (meta) return meta;
  const h = location.hostname, seg = location.pathname.split("/").filter(Boolean)[0];
  return h.endsWith(".github.io") && seg ? `https://github.com/${h.split(".")[0]}/${seg}` : "https://github.com/";
})();
const $ = (id) => document.getElementById(id);
const state = { meta: null, py: null, mode: "prediction", family: "auto", lastAnswer: null, dataset: null,
                map: null, markers: [], selectedLads: new Set(), customMetric: null, pyReady: false };

// ----------------------------------------------------------------------------- helpers
function fmt(v) {
  if (v === null || v === undefined || v === "") return "n/a";
  if (typeof v !== "number") return String(v);
  if (Number.isInteger(v)) return v.toLocaleString("en-GB");
  return Math.abs(v) >= 1 ? v.toLocaleString("en-GB", { maximumFractionDigits: 2 }) : v.toPrecision(4);
}
function md(text) {
  const html = marked.parse(text || "", { gfm: true, breaks: false });
  const clean = DOMPurify.sanitize(html, { ADD_ATTR: ["target"] });
  const div = document.createElement("div");
  div.innerHTML = clean;
  div.querySelectorAll("a").forEach((a) => { a.target = "_blank"; a.rel = "noopener"; });
  return div.innerHTML;
}
function chip(label, value) {
  return `<span class="chip"><span style="opacity:.85">${label} </span><b>${value}</b></span>`;
}
function status(id, text, warn = false) { const el = $(id); el.textContent = text; el.classList.toggle("warn", warn); }
function csvOf(rows) {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v) => { const s = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}
function download(name, text, type = "text/csv") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
}

// ----------------------------------------------------------------------------- map
const SCALES = {
  YlOrRd: ["#ffffcc", "#fed976", "#fd8d3c", "#e31a1c", "#800026"], OrRd: ["#fff7ec", "#fdd49e", "#fc8d59", "#d7301f", "#7f0000"],
  Blues: ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"], Purples: ["#f2f0f7", "#cbc9e2", "#9e9ac8", "#756bb1", "#54278f"],
  YlGnBu: ["#ffffcc", "#a1dab4", "#41b6c4", "#2c7fb8", "#253494"], Greens: ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"],
  Oranges: ["#feedde", "#fdbe85", "#fd8d3c", "#e6550d", "#a63603"], Teal: ["#e0f2f1", "#80cbc4", "#26a69a", "#00897b", "#004d40"],
  Reds: ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"], RdYlGn: ["#d73027", "#fdae61", "#ffffbf", "#a6d96a", "#1a9850"],
  RdBu: ["#b2182b", "#f4a582", "#f7f7f7", "#92c5de", "#2166ac"], Viridis: ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
};
function colour(scale, t) {
  const cols = SCALES[scale] || SCALES.Viridis;
  const x = Math.max(0, Math.min(1, t)) * (cols.length - 1);
  const i = Math.floor(x), f = x - i;
  const a = cols[i], b = cols[Math.min(i + 1, cols.length - 1)];
  const hex = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
  const [r1, g1, b1] = hex(a), [r2, g2, b2] = hex(b);
  return `rgb(${Math.round(r1 + (r2 - r1) * f)},${Math.round(g1 + (g2 - g1) * f)},${Math.round(b1 + (b2 - b1) * f)})`;
}
function initMap() {
  state.map = L.map("map", { scrollWheelZoom: true }).setView([52.42, -3.85], 8);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(state.map);
  const sel = $("map-metric");
  for (const [key, m] of Object.entries(state.meta.map_metrics)) sel.add(new Option(m.label, key));
  sel.add(new Option("Custom dataset column (use 'Plot on map' in the dataset panel)", "custom"));
  sel.value = "pred_keepership_central";
  sel.addEventListener("change", () => drawMetric(sel.value));
  drawMetric(sel.value);
}
function drawMetric(key) {
  const m = key === "custom" ? state.customMetric : state.meta.map_metrics[key];
  state.markers.forEach((mk) => mk.remove()); state.markers = [];
  if (!m) { $("map-legend").textContent = key === "custom" ? "Build a dataset and press 'Plot on map' to colour the map by one of its columns." : ""; return; }
  const entries = Object.entries(m.values).filter(([, v]) => v[0] !== null && v[0] !== undefined && !Number.isNaN(v[0]));
  const vals = entries.map(([, v]) => v[0]);
  const lo = Math.min(...vals), hi = Math.max(...vals), amax = Math.max(...vals.map(Math.abs)) || 1;
  const diverging = m.scale === "RdBu";
  for (const [lad, [v, period]] of entries) {
    const c = state.meta.centroids[lad]; if (!c) continue;
    const t = diverging ? (v / amax + 1) / 2 : (hi > lo ? (v - lo) / (hi - lo) : 0.5);
    const r = 7 + 13 * (Math.abs(v) / amax);
    const mk = L.circleMarker(c, { radius: r, color: "#fff", weight: 1, fillColor: colour(m.scale, t), fillOpacity: 0.85 })
      .bindTooltip(`<b>${lad}</b><br>${m.label}<br><b>${fmt(v)}</b> ${m.unit || ""} (${period || ""})<br><i>Click to ask about ${lad}</i>`)
      .on("click", () => onLadClick(lad)).addTo(state.map);
    const label = L.marker(c, { icon: L.divIcon({ className: "lad-label", html: lad, iconAnchor: [lad.length * 3, r + 14] }), interactive: false }).addTo(state.map);
    state.markers.push(mk, label);
  }
  $("map-legend").innerHTML = `<b>${m.label}</b>: ${fmt(lo)} to ${fmt(hi)} ${m.unit || ""}. Marker size and colour scale with the value.`;
}
function onLadClick(lad) {
  toggleLad(lad);
  $("question").value = state.mode === "prediction"
    ? `What is ${lad}'s predicted EV keepership in ${state.meta.forecast_year} under the central scenario?`
    : `What do you know about ${lad}?`;
}

// ----------------------------------------------------------------------------- controls
function renderAbout() {
  const a = state.meta.about;
  if (!a) return;
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const cols = ["Dataset", "Publisher", "Licence", "Role", "Measures supplied", "Coverage"];
  const table = `<div class="scroll"><table class="datasets"><thead><tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
    a.datasets.map((r) => `<tr><td title="${esc(r.Title)}">${r["Landing page"] ? `<a href="${esc(r["Landing page"])}" target="_blank" rel="noopener">${esc(r.Dataset)}</a>` : esc(r.Dataset)}</td>` +
      cols.slice(1).map((c) => `<td>${esc(r[c])}</td>`).join("") + "</tr>").join("") + "</tbody></table></div>";
  $("about").innerHTML = `<p class="lead">${esc(a.lead)}</p>` + a.sections.map(([title, text]) =>
    `<h3>${esc(title)}</h3><p>${esc(text)}</p>${title.startsWith("Datasets") ? table : ""}`).join("");
}

function renderChips() {
  const c = state.meta.counts;
  $("chips").innerHTML = [
    chip("Welsh LADs", c.lads), chip("Observed triples", c.observed_triples.toLocaleString("en-GB")),
    chip("Observations", c.observations.toLocaleString("en-GB")), chip("Quarterly forecasts", c.forecasts.toLocaleString("en-GB")),
    chip("Prediction types", c.families), chip("Scenarios", c.scenarios.join(" / ")), chip("Horizon", `${c.years[0]}–${c.years[1]}`),
    `<span class="chip" id="chip-runtime"><span style="opacity:.85">Runtime </span><b>loading…</b></span>`,
  ].join("");
}
function renderHelp() {
  const groups = state.meta.question_groups[state.mode];
  $("help-panel").innerHTML = Object.entries(groups).map(([h, qs]) =>
    `<h4>${h}</h4>` + qs.map((q) => `<button type="button" data-q="${q.replace(/"/g, "&quot;")}">${q}</button>`).join("")).join("");
  $("help-panel").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { $("question").value = b.dataset.q; }));
  $("mode-description").textContent = state.meta.mode_description[state.mode];
  $("family-block").classList.toggle("hidden", state.mode !== "prediction");
}
function renderFamilies() {
  const opts = [{ key: "auto", label: "Auto (from the question)" }, ...state.meta.families];
  $("family-switch").innerHTML = opts.map((f) => `<label><input type="radio" name="family" value="${f.key}" ${f.key === "auto" ? "checked" : ""}> ${f.label}</label>`).join("");
  $("family-switch").querySelectorAll("input").forEach((i) => i.addEventListener("change", () => { state.family = i.value; }));
  const sel = $("methods-family");
  for (const f of state.meta.families) sel.add(new Option(f.label, f.key));
  sel.addEventListener("change", () => showMethods(sel.value, true));
}
function renderDatasetControls() {
  $("ds-columns").innerHTML = state.meta.dataset_columns.map(([k, l]) =>
    `<label><input type="checkbox" value="${k}" ${state.meta.default_columns.includes(k) ? "checked" : ""}> ${l}</label>`).join("");
  $("ds-lads").innerHTML = state.meta.lads.map((n) => `<button type="button" data-lad="${n}">${n}</button>`).join("");
  $("ds-lads").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => toggleLad(b.dataset.lad)));
}
function toggleLad(lad) {
  if (state.selectedLads.has(lad)) state.selectedLads.delete(lad); else state.selectedLads.add(lad);
  $("ds-lads").querySelectorAll("button").forEach((b) => b.classList.toggle("on", state.selectedLads.has(b.dataset.lad)));
}

// ----------------------------------------------------------------------------- python runtime
async function loadPython() {
  const t0 = performance.now();
  const py = await loadPyodide();
  const [snap, ...mods] = await Promise.all([
    fetch("data/kg_snapshot.json").then((r) => r.text()),
    ...["kg_service.py", "qa_with_humanization.py", "qa.py", "methods.py"].map((n) => fetch("py/" + n).then((r) => r.text())),
  ]);
  ["kg_service.py", "qa_with_humanization.py", "qa.py", "methods.py"].forEach((n, i) => py.FS.writeFile("/home/pyodide/" + n, mods[i]));
  py.FS.writeFile("/home/pyodide/kg_snapshot.json", snap);
  await py.runPythonAsync(`
import sys, json
sys.path.insert(0, "/home/pyodide")
from kg_service import CLEETSKG
import qa
KG = CLEETSKG.from_snapshot(open("/home/pyodide/kg_snapshot.json").read())

def _answer(q, mode, family):
    fam = None if family in (None, "", "auto") else family
    try:
        r = qa.answer_question_rich(KG, q, mode=mode, humanize=False, family=fam)
    except Exception as exc:
        r = {"markdown": f"### Query error\\n\\n\`{type(exc).__name__}: {exc}\`", "kind": "error", "family": None, "table": None, "columns": None}
    return json.dumps(r, default=str)

def _methods(family):
    return qa.methods_text(KG, family)

def _dataset(cols_json, lads_json, year):
    cols = json.loads(cols_json); lads = json.loads(lads_json) or None
    rows = KG.dataset_table(cols, lads=lads, year=int(year) if year else None)
    return json.dumps({"rows": rows, "sources": KG.dataset_sources(cols)}, default=str)
`);
  state.py = py; state.pyReady = true;
  const secs = ((performance.now() - t0) / 1000).toFixed(1);
  status("runtime-status", `Ready: knowledge graph loaded in ${secs} s (${String(py.runPython("repr(KG)"))}).`);
  $("chip-runtime").innerHTML = `<span style="opacity:.85">Runtime </span><b>ready (${secs} s)</b>`;
  ["ask", "show-inventory", "ds-build"].forEach((id) => { $(id).disabled = false; });
}
function pyCall(fn, ...args) {
  const f = state.py.globals.get(fn);
  const out = f(...args);
  f.destroy?.();
  return out;
}

// ----------------------------------------------------------------------------- ask / answer
async function ask(questionOverride) {
  if (!state.pyReady) return;
  const q = (questionOverride ?? $("question").value).trim();
  if (!q) { $("answer").innerHTML = "<p>Please enter a question.</p>"; return; }
  const t0 = performance.now();
  $("answer").innerHTML = "<p class='muted'>Retrieving…</p>";
  await new Promise((r) => setTimeout(r, 10));
  const r = JSON.parse(pyCall("_answer", q, state.mode, state.family));
  const secs = ((performance.now() - t0) / 1000).toFixed(2);
  const source = state.mode === "actual" ? "CLEETS-KG-Enriched" : "CLEETS Prediction KG";
  $("answer").innerHTML = md(`${r.markdown}\n\n---\n\n*Mode: ${source}. Templated answer, computed in your browser in ${secs} seconds.*`);
  state.lastAnswer = { question: q, mode: state.mode, family: r.family, kind: r.kind, answer: r.markdown };
  if (r.family) { $("methods-bar").classList.remove("hidden"); $("methods-family").value = r.family; $("methods-box").classList.add("hidden"); }
  else { $("methods-bar").classList.add("hidden"); $("methods-box").classList.add("hidden"); }
  if (r.kind === "table" && r.table) setDataset(r.table, r.sources || [], r.markdown.split("\n")[0].replace(/^#+\s*/, ""));
}
function showMethods(family, keepOpen = false) {
  const box = $("methods-box");
  const open = keepOpen ? !box.classList.contains("hidden") : box.classList.contains("hidden");
  if (!open) { box.classList.add("hidden"); return; }
  box.innerHTML = md(pyCall("_methods", family));
  box.classList.remove("hidden");
}

// ----------------------------------------------------------------------------- dataset
function setDataset(rows, sources, title) {
  state.dataset = { rows, sources, title };
  const show = rows.length ? Object.keys(rows[0]).filter((c) => !c.endsWith(" period")) : [];
  $("ds-table").innerHTML = rows.length ? `<table><thead><tr>${show.map((c) => `<th data-col="${c}">${c}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${show.map((c) => `<td>${fmt(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>` : "<p class='muted'>No rows.</p>";
  $("ds-table").querySelectorAll("th").forEach((th) => th.addEventListener("click", () => sortDataset(th.dataset.col)));
  const numeric = show.filter((c) => c !== "LAD" && c !== "LAD code" && rows.filter((r) => typeof r[c] === "number").length >= 3);
  const sel = $("ds-plot-column"); sel.innerHTML = numeric.map((c) => `<option>${c}</option>`).join("");
  $("ds-plot").disabled = !numeric.length; $("ds-download").disabled = !rows.length;
  $("ds-sources").innerHTML = sources.length ? "Sources: " + sources.map((s) => `<a href="${s.url}" target="_blank" rel="noopener">${s.label}</a>`).join(" · ") + ' · <a href="https://w3id.org/def/cleets" target="_blank" rel="noopener">CLEETS knowledge graph</a>' : "";
  status("ds-status", `${title} (${rows.length} rows). Download or plot below.`);
}
function sortDataset(col) {
  if (!state.dataset) return;
  const rows = [...state.dataset.rows];
  const asc = state.dataset.sortCol === col ? !state.dataset.asc : true;
  rows.sort((a, b) => { const x = a[col], y = b[col]; if (x === y) return 0; if (x === null || x === undefined) return 1; if (y === null || y === undefined) return -1; return (x > y ? 1 : -1) * (asc ? 1 : -1); });
  setDataset(rows, state.dataset.sources, state.dataset.title); state.dataset.sortCol = col; state.dataset.asc = asc;
}
function buildDataset() {
  if (!state.pyReady) return;
  const cols = [...$("ds-columns").querySelectorAll("input:checked")].map((i) => i.value);
  if (!cols.length) { status("ds-status", "Choose at least one column.", true); return; }
  const lads = [...state.selectedLads]; const year = $("ds-year").value;
  const r = JSON.parse(pyCall("_dataset", JSON.stringify(cols), JSON.stringify(lads), year || ""));
  const scope = lads.length ? `${r.rows.length} selected LAD${r.rows.length !== 1 ? "s" : ""}` : `${r.rows.length} LADs`;
  setDataset(r.rows, r.sources, `Custom dataset: ${scope}, ${cols.length} column${cols.length !== 1 ? "s" : ""}${year ? `, year ${year}` : ""}`);
}
function plotColumn() {
  if (!state.dataset) return;
  const col = $("ds-plot-column").value; if (!col) return;
  const values = {};
  for (const r of state.dataset.rows) if (typeof r[col] === "number") values[r.LAD] = [r[col], r[`${col} period`] || "custom dataset"];
  state.customMetric = { label: col, unit: "", scale: "Viridis", values };
  $("map-metric").value = "custom"; drawMetric("custom");
  $("map").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ----------------------------------------------------------------------------- feedback (local)
function loadFeedback() { try { return JSON.parse(localStorage.getItem("cleets_feedback") || "[]"); } catch { return []; } }
function submitFeedback() {
  if (!state.lastAnswer) { status("feedback-status", "Ask a question first, then score the answer.", true); return; }
  const list = loadFeedback();
  list.push({ timestamp: new Date().toISOString(), question: state.lastAnswer.question, score: Number($("feedback-score").value), mode: state.lastAnswer.mode,
              family: state.lastAnswer.family || "", notes: $("feedback-notes").value.trim(), answer: state.lastAnswer.answer.slice(0, 2000) });
  try { localStorage.setItem("cleets_feedback", JSON.stringify(list)); } catch { /* storage unavailable */ }
  $("feedback-notes").value = "";
  status("feedback-status", `Saved in this browser: ${$("feedback-score").value}/10 (${list.length} score${list.length !== 1 ? "s" : ""} stored). Thank you.`);
}

// ----------------------------------------------------------------------------- boot
function styleLogo() {
  // The logo sits in a white card so it shows on the blue banner (data-card="0" on the <img> disables the card).
  const logo = $("logo");
  if (logo && logo.dataset.card !== "0") logo.classList.add("card");
}

async function boot() {
  styleLogo();
  state.meta = await fetch("data/site_meta.json").then((r) => r.json());
  $("title").textContent = state.meta.title; document.title = state.meta.title;
  $("repo-link").href = REPO_URL;
  renderAbout(); renderChips(); renderHelp(); renderFamilies(); renderDatasetControls(); initMap();
  $("question").value = state.meta.question_groups.prediction[Object.keys(state.meta.question_groups.prediction)[0]][0];
  $("foot").textContent = `CLEETS-KG-Enriched (${state.meta.counts.observed_triples.toLocaleString("en-GB")} triples) and CLEETS Prediction KG (${state.meta.counts.prediction_triples.toLocaleString("en-GB")} triples, ${state.meta.counts.families} prediction types) · Knowledge graph: https://w3id.org/def/cleets · Static build: the Python QA engine runs in your browser via Pyodide.`;

  $("mode-switch").querySelectorAll("input").forEach((i) => i.addEventListener("change", () => { state.mode = i.value; renderHelp(); }));
  $("help-toggle").addEventListener("click", () => $("help-panel").classList.toggle("hidden"));
  $("ask").addEventListener("click", () => ask());
  $("show-inventory").addEventListener("click", () => ask("Show me the data you have"));
  $("question").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ask(); });
  $("methods-toggle").addEventListener("click", () => showMethods($("methods-family").value));
  $("ds-build").addEventListener("click", buildDataset);
  $("ds-download").addEventListener("click", () => { if (state.dataset) download(`cleets_dataset_${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}.csv`, csvOf(state.dataset.rows)); });
  $("ds-plot").addEventListener("click", plotColumn);
  $("feedback-score").addEventListener("input", () => { $("feedback-score-value").textContent = $("feedback-score").value; });
  $("feedback-submit").addEventListener("click", submitFeedback);
  $("feedback-export").addEventListener("click", () => download("cleets_feedback_export.csv", csvOf(loadFeedback())));

  try { await loadPython(); }
  catch (e) { status("runtime-status", `The Python runtime could not be loaded (${e}). Check your connection and reload.`, true); $("chip-runtime").innerHTML = `<span style="opacity:.85">Runtime </span><b>failed</b>`; }
}
boot();
