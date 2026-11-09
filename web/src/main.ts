import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-mono/latin-600.css";
import "uplot/dist/uPlot.min.css";
import "./style.css";

import { createEditor, type EditorApi } from "./editor";
import { Engine } from "./engine";
import { DEFAULT_EXAMPLE, EXAMPLES, findExample } from "./examples";
import { columns, csvFileName, defaultVisible, eng, groupSignals, num, opRows, toCsv } from "./format";
import { decodeShare, encodeShare } from "./hash";
import { drawGroup, type Extra, type PlotHandle } from "./plots";
import { loadReference, overlayFor, type Overlay } from "./reference";
import type { Analysis, RunOk, RunResult, Warn } from "./types";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const el = <K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, ...kids: (Node | string)[]) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...kids);
  return node;
};

// ---------------------------------------------------------------- state
const engine = new Engine((message) => setBoot(message));
let editor: EditorApi;
let currentExample: string | null = null; // set while the editor text equals a bundled example
let running = false;
let rerunRequested = false;
let result: RunOk | null = null;
let activeTab = 0;
let showReference = false;
let overlay: Map<number, Overlay> = new Map();
const views = new Map<number, "plot" | "table">();
let handles: PlotHandle[] = [];
const isMac = /Mac|iPhone|iPad/.test(navigator.platform);

// ---------------------------------------------------------------- small helpers
function toast(text: string) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 1800);
}

function setStatus(text: string) {
  $("status").textContent = text;
}

function setBoot(message: string | null) {
  const boot = $("boot");
  if (message === null) return void (boot.hidden = true);
  boot.hidden = false;
  boot.replaceChildren(
    el("strong", {}, "Starting the Python runtime"),
    el("span", {}, message),
    el("div", { class: "bar-indet", "aria-hidden": "true" }),
    el("span", { class: "note" }, "The first visit downloads about 30 MB (Python, numpy, scipy); your browser caches it, so later visits start in seconds."),
  );
}

// ---------------------------------------------------------------- theme
type ThemeMode = "system" | "light" | "dark";
function applyTheme(mode: ThemeMode) {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-theme");
  else root.dataset.theme = mode;
  try {
    if (mode === "system") localStorage.removeItem("spicelite-theme");
    else localStorage.setItem("spicelite-theme", mode);
  } catch {
    /* storage may be blocked: the theme just will not persist */
  }
  const label = { system: "Auto", light: "Light", dark: "Dark" }[mode];
  $("theme-label").textContent = `Theme: ${label}`;
  $("theme").setAttribute("aria-label", `Color theme: ${mode === "system" ? "follow system" : mode}. Press to change.`);
  redrawPlots();
}
function currentTheme(): ThemeMode {
  const t = document.documentElement.dataset.theme;
  return t === "light" || t === "dark" ? t : "system";
}

// ---------------------------------------------------------------- results
function clearResults() {
  handles.forEach((h) => h.destroy());
  handles = [];
  $("results").replaceChildren();
}

function showMessages(res: RunResult) {
  const box = $("messages");
  box.replaceChildren();
  if (!res.ok) {
    const { message, line } = res.error;
    const err = el("div", { class: "msg err", role: "alert" }, el("strong", {}, "Error"), message);
    if (line !== null) {
      const jump = el("button", { type: "button" }, `go to line ${line}`);
      jump.addEventListener("click", () => editor.goToLine(line));
      err.append(jump);
    }
    box.append(err);
    return;
  }
  const warnings: Warn[] = [...res.warnings, ...res.analyses.flatMap((a) => a.meta.warnings.map((w) => ({ ...w, message: `.${a.type}: ${w.message}` })))];
  if (!warnings.length) return;
  const list = el("ul");
  for (const w of warnings) list.append(el("li", {}, el("code", {}, w.type), " \u2014 ", w.message));
  const details = el("details", { class: "msg warn", role: "status" }, el("summary", {}, `${warnings.length} warning${warnings.length > 1 ? "s" : ""} (the results are still shown)`), list);
  details.open = true;
  box.append(details);
}

function tabLabel(a: Analysis): string {
  return a.type === "dc" ? `.dc ${a.x?.name ?? ""}` : `.${a.type}`;
}

function render(res: RunResult) {
  handles.forEach((h) => h.destroy());
  handles = [];
  editor.setError(res.ok ? null : res.error.line);
  showMessages(res);
  const root = $("results");
  root.replaceChildren();
  if (!res.ok) {
    result = null;
    setStatus("Fix the error above and run again.");
    root.append(el("p", { class: "placeholder" }, "No results: the netlist did not run."));
    return;
  }
  result = res;
  activeTab = Math.min(activeTab, res.analyses.length - 1);
  const total = res.analyses.reduce((s, a) => s + a.meta.runtime_ms, 0);
  setStatus(`${res.title || "Untitled"} \u00b7 ${res.analyses.length} analysis${res.analyses.length > 1 ? "es" : ""} in ${total < 10 ? total.toFixed(1) : Math.round(total)} ms`);
  const tabs = el("div", { class: "tabs", role: "tablist", "aria-label": "Analyses" });
  res.analyses.forEach((a, i) => {
    const tab = el("button", { class: "tab", role: "tab", id: `tab-${i}`, "aria-controls": `panel-${i}`, type: "button" }, tabLabel(a));
    tab.addEventListener("click", () => selectTab(i));
    tab.addEventListener("keydown", (e) => {
      const n = res.analyses.length;
      const next = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i + n - 1) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
      if (next >= 0) {
        e.preventDefault();
        selectTab(next);
        $(`tab-${next}`).focus();
      }
    });
    tabs.append(tab);
  });
  root.append(tabs);
  res.analyses.forEach((a, i) => root.append(buildPanel(a, i)));
  selectTab(activeTab);
}

function selectTab(index: number) {
  activeTab = index;
  document.querySelectorAll<HTMLElement>(".tab").forEach((t, i) => {
    t.setAttribute("aria-selected", String(i === index));
    t.tabIndex = i === index ? 0 : -1;
  });
  document.querySelectorAll<HTMLElement>(".panel").forEach((p, i) => (p.hidden = i !== index));
  drawPanel(index);
}

function buildPanel(a: Analysis, i: number): HTMLElement {
  const panel = el("div", { class: "panel", role: "tabpanel", id: `panel-${i}`, "aria-labelledby": `tab-${i}` });
  const m = a.meta;
  const chips = [`${m.points} point${m.points === 1 ? "" : "s"}`, `${m.runtime_ms < 10 ? m.runtime_ms.toFixed(1) : Math.round(m.runtime_ms)} ms`];
  if (a.type === "tran") chips.push(`${m.method === "be" ? "backward Euler" : "trapezoidal"}`, m.step_control === "adaptive" ? `adaptive, ${m.rejected ?? 0} rejected` : "fixed step");
  else if (m.method) chips.push(String(m.method));
  panel.append(el("p", { class: "metaline" }, ...chips.map((c) => el("span", {}, c))));

  const toolbar = el("div", { class: "toolbar" });
  if (a.type !== "op") {
    const plot = el("button", { type: "button", "aria-pressed": "true" }, "Plot");
    const table = el("button", { type: "button", "aria-pressed": "false" }, "Table");
    const set = (mode: "plot" | "table") => {
      views.set(i, mode);
      plot.setAttribute("aria-pressed", String(mode === "plot"));
      table.setAttribute("aria-pressed", String(mode === "table"));
      drawPanel(i);
    };
    plot.addEventListener("click", () => set("plot"));
    table.addEventListener("click", () => set("table"));
    toolbar.append(el("div", { class: "seg", role: "group", "aria-label": "View" }, plot, table));
  }
  const csv = el("button", { class: "btn small", type: "button" }, "Download CSV");
  csv.addEventListener("click", () => downloadCsv(a));
  toolbar.append(csv);
  const ref = overlay.get(i);
  if (ref) {
    const box = el("input", { type: "checkbox", id: `ref-${i}` }) as HTMLInputElement;
    box.checked = showReference;
    box.addEventListener("change", () => {
      showReference = box.checked;
      redrawPlots();
    });
    toolbar.append(el("label", { class: "check", for: `ref-${i}`, title: "Precomputed offline with ngspice 41 for this exact bundled example; not a live ngspice run" }, box, "ngspice reference (precomputed)"));
  }
  panel.append(toolbar, el("div", { class: "body", id: `body-${i}` }));
  return panel;
}

function drawPanel(i: number) {
  if (!result) return;
  const a = result.analyses[i];
  const body = $(`body-${i}`);
  if (!body) return;
  handles = handles.filter((h) => (h.destroy(), false));
  body.replaceChildren();
  const ref = showReference ? overlay.get(i) : undefined;
  if (a.type === "op" || views.get(i) === "table") {
    body.append(buildTable(a, ref));
    if (ref && a.type === "op") body.append(el("p", { class: "note" }, `ngspice reference (precomputed, ngspice 41): max difference ${ref.summary}.`));
    return;
  }
  const groups = groupSignals(a);
  const syncKey = a.type === "ac" ? `bode-${i}` : undefined;
  const refNote = ref ? el("p", { class: "note" }, `ngspice reference (precomputed, ngspice 41): max difference ${ref.summary}.`) : null;
  const currentBox = el("details", { class: "more" }, el("summary", {}, "Branch currents"));
  let anyCurrent = false;
  for (const g of groups) {
    const host = el("div", { class: "plotbox" });
    const figure = el("figure", { class: "plot" }, el("figcaption", {}, `${g.title} (${g.yLabel})`), host);
    (g.current ? currentBox : body).append(figure);
    anyCurrent ||= g.current;
    const extra: Extra[] = ref ? ref.extras.get(g.id) ?? [] : [];
    // a group that is only present once the box is open still needs a measurable width: draw after attaching
    queueMicrotask(() => handles.push(drawGroup(host, a.x!, g, defaultVisible(g.signals.length), { syncKey, height: g.phase ? 200 : 280, extra })));
  }
  if (anyCurrent) {
    body.append(currentBox);
    currentBox.addEventListener("toggle", () => currentBox.open && window.dispatchEvent(new Event("resize")));
  }
  if (refNote) body.append(refNote);
  if (groups.some((g) => g.signals.length > 8)) body.append(el("p", { class: "note" }, "Only the first 8 traces start visible; click a name in the legend to show or hide any trace. Drag on a plot to zoom, double-click to reset."));
  else body.append(el("p", { class: "note" }, "Drag on a plot to zoom, double-click to reset; click a name in the legend to hide a trace."));
}

function redrawPlots() {
  if (result) drawPanel(activeTab);
}

const MAX_ROWS = 600;
function buildTable(a: Analysis, ref?: Overlay): HTMLElement {
  const wrap = el("div", { class: "tablewrap", tabindex: "0", role: "region", "aria-label": `${tabLabel(a)} results table` });
  const table = el("table", { class: a.type === "op" ? "data op" : "data" });
  if (a.type === "op") {
    const head = ["Signal", "Kind", "Value", ...(ref ? ["ngspice (precomputed)", "difference"] : [])];
    table.append(el("thead", {}, el("tr", {}, ...head.map((h) => el("th", {}, h)))));
    const tbody = el("tbody");
    for (const r of opRows(a)) {
      const row = el("tr", {}, el("td", {}, r.name), el("td", {}, r.kind), el("td", { class: "num", title: String(r.raw) }, r.value));
      const unit = a.signals.find((s) => s.name === r.name)?.unit ?? "";
      const theirs = ref?.op.get(r.name);
      if (ref) row.append(el("td", { class: "num" }, theirs === undefined ? "\u2014" : eng(theirs, unit)), el("td", { class: "num" }, theirs === undefined || r.raw === null ? "\u2014" : eng(r.raw - theirs, unit, 3)));
      tbody.append(row);
    }
    table.append(tbody);
    wrap.append(table);
    return wrap;
  }
  const cols = columns(a);
  const rows = cols[0].values.length;
  table.append(el("thead", {}, el("tr", {}, ...cols.map((c) => el("th", {}, c.header)))));
  const tbody = el("tbody");
  const line = (r: number) => el("tr", {}, ...cols.map((c) => el("td", { class: "num" }, num(c.values[r]))));
  const shown = rows <= MAX_ROWS ? rows : MAX_ROWS / 2;
  for (let r = 0; r < shown; r++) tbody.append(line(r));
  if (rows > MAX_ROWS) {
    tbody.append(el("tr", { class: "gap" }, el("td", { colspan: String(cols.length) }, `\u2026 ${rows - MAX_ROWS} rows hidden \u2026 (Download CSV for all ${rows})`)));
    for (let r = rows - MAX_ROWS / 2; r < rows; r++) tbody.append(line(r));
  }
  table.append(tbody);
  wrap.append(table);
  return wrap;
}

function downloadCsv(a: Analysis) {
  const blob = new Blob([toCsv(a)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: csvFileName(result?.title ?? "", a) });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------- running
async function execute(text: string): Promise<RunResult> {
  try {
    return await engine.run(text);
  } catch (err) {
    return { ok: false, error: { message: (err as Error).message, line: null } };
  }
}

async function run() {
  if (running) {
    rerunRequested = true; // rapid clicks coalesce into one more run with the latest text
    return;
  }
  running = true;
  const button = $<HTMLButtonElement>("run");
  button.disabled = true;
  button.classList.add("busy");
  do {
    rerunRequested = false;
    setStatus("Running\u2026");
    const text = editor.getText();
    const res = await execute(text);
    if (rerunRequested) continue;
    setBoot(null);
    overlay = new Map();
    if (res.ok && currentExample) {
      const ref = await loadReference(currentExample).catch(() => null);
      if (ref) overlay = overlayFor(ref, res);
    }
    render(res);
    $("runtime").textContent = engine.runtime || $("runtime").textContent;
  } while (rerunRequested);
  button.disabled = false;
  button.classList.remove("busy");
  running = false;
}

// ---------------------------------------------------------------- examples + share links
function loadText(text: string, example: string | null) {
  currentExample = example;
  editor.setText(text);
  $("exdesc").textContent = example ? (findExample(example)?.description ?? "") : "Your own netlist. The first line is the title.";
  $<HTMLSelectElement>("examples").value = example ?? "";
}

let hashTimer: ReturnType<typeof setTimeout> | undefined;
async function updateHash() {
  const shared = currentExample ? { kind: "example" as const, name: currentExample } : { kind: "netlist" as const, text: editor.getText() };
  history.replaceState(null, "", `#${await encodeShare(shared)}`);
}

function onEdit(text: string) {
  const ex = currentExample ? findExample(currentExample) : undefined;
  if (ex && text !== ex.text) {
    currentExample = null; // editing detaches from the bundled example: the reference overlay no longer applies
    $("exdesc").textContent = "Edited. The ngspice reference only exists for the unmodified bundled example.";
    $<HTMLSelectElement>("examples").value = "";
    overlay = new Map();
    showReference = false;
    redrawPlots();
    document.querySelectorAll(".check").forEach((c) => c.remove());
  }
  clearTimeout(hashTimer);
  hashTimer = setTimeout(updateHash, 400);
}

async function loadFromHash(): Promise<boolean> {
  const shared = await decodeShare(location.hash);
  if (!shared) return false;
  if (shared.kind === "example") {
    const ex = findExample(shared.name);
    if (!ex) return false;
    loadText(ex.text, ex.name);
  } else loadText(shared.text, null);
  return true;
}

async function copyLink() {
  clearTimeout(hashTimer);
  await updateHash();
  try {
    await navigator.clipboard.writeText(location.href);
    toast("Link copied to the clipboard");
  } catch {
    window.prompt("Copy this link", location.href);
  }
}

// ---------------------------------------------------------------- boot
async function main() {
  $("run-kbd").textContent = isMac ? "\u2318\u2009\u21b5" : "Ctrl\u2009\u21b5";
  const select = $<HTMLSelectElement>("examples");
  select.append(el("option", { value: "" }, "\u2014 your own netlist \u2014"));
  for (const ex of EXAMPLES) select.append(el("option", { value: ex.name }, ex.name));
  select.addEventListener("change", () => {
    const ex = findExample(select.value);
    if (!ex) return;
    loadText(ex.text, ex.name);
    void updateHash();
    void run();
  });
  editor = createEditor($("editor"), "", { onChange: onEdit, onRun: () => void run() });
  $("run").addEventListener("click", () => void run());
  $("share").addEventListener("click", () => void copyLink());
  $("theme").addEventListener("click", () => applyTheme(({ system: "light", light: "dark", dark: "system" } as const)[currentTheme()]));
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      void run();
    }
  });
  window.addEventListener("hashchange", async () => {
    if (await loadFromHash()) void run();
  });
  applyTheme(currentTheme());
  if (!(await loadFromHash())) {
    const ex = findExample(DEFAULT_EXAMPLE) ?? EXAMPLES[0];
    loadText(ex.text, ex.name);
  }
  setBoot("Downloading the Python runtime\u2026");
  setStatus("Loading the simulator\u2026");
  engine.start().then(
    () => {
      $("runtime").textContent = engine.runtime;
      void run();
    },
    (err: Error) => {
      setBoot(null);
      $("messages").replaceChildren(
        el("div", { class: "msg err", role: "alert" }, el("strong", {}, "Could not start"), `${err.message} The simulator needs to download Python from the jsdelivr CDN on the first visit; check your connection and reload.`),
      );
      setStatus("The simulator did not start.");
    },
  );
}

void main();