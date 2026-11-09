// The landing band (a live demo drawn from real simulation data) and the "Supported elements" spec sheets.
// Demo, after StageShow's rules (DECISIONS D51): one story in four beats (Run is pressed, the traces draw, the RC time
// constant is marked, the result holds), a loop that resets with a visible cause (Run again), a poster frame that tells
// the story alone (shown under reduced motion), paused off screen and by a button.
import sheets from "./element-sheets.json";
import { reducedMotion } from "./motion";
import { loadReference } from "./reference";
import { SYMBOLS } from "./symbols";

const W = 400, H = 170, PAD_L = 34, PAD_B = 22; // the figure's plot area, in SVG units
const NETLIST = ["RC pulse response, tau = 1 ms", "V1 in 0 DC 0 PULSE(0 1 0 10u 10u 2.5m 5m)", "R1 in out 1k", "C1 out 0 1u", ".tran 10u 5m"];

function polyline(xs: number[], ys: (number | null)[], xmax: number): string {
  const step = Math.max(1, Math.floor(xs.length / 160)); // ~160 points draw the 5 ms smoothly
  const pts: string[] = [];
  for (let k = 0; k < xs.length; k += step) {
    const y = ys[k];
    if (y === null) continue;
    pts.push(`${(PAD_L + (xs[k] / xmax) * (W - PAD_L - 6)).toFixed(1)},${(H - PAD_B - y * (H - PAD_B - 14)).toFixed(1)}`);
  }
  return pts.join(" ");
}

/** Draw the demo into `host` from the committed ngspice reference of examples/rc_step.cir (real simulation output). */
export async function renderDemo(host: HTMLElement, pauseButton: HTMLButtonElement): Promise<void> {
  const ref = await loadReference("rc_step").catch(() => null);
  const tran = ref?.analyses.find((a) => a.type === "tran");
  const vin = tran?.signals.find((s) => s.name === "v(in)");
  const vout = tran?.signals.find((s) => s.name === "v(out)");
  if (!tran || !vin || !vout) {
    host.hidden = true; // no data, no demo: never a fake curve
    pauseButton.hidden = true;
    return;
  }
  const xmax = tran.x[tran.x.length - 1];
  const tauX = PAD_L + (1e-3 / xmax) * (W - PAD_L - 6);
  const tauY = H - PAD_B - (1 - Math.exp(-1)) * (H - PAD_B - 14);
  const ticks = [0, 1, 2, 3, 4, 5].map((ms) => {
    const x = PAD_L + ((ms * 1e-3) / xmax) * (W - PAD_L - 6);
    return `<line x1="${x}" y1="${H - PAD_B}" x2="${x}" y2="${H - PAD_B + 4}" class="d-axis"/><text x="${x}" y="${H - 6}" class="d-tick" text-anchor="middle">${ms}${ms === 5 ? " ms" : ""}</text>`;
  }).join("");
  host.innerHTML = `
    <div class="d-window" role="img" aria-label="Demo: the rc_step netlist is run; v(out) charges toward 1 V and passes 63.2 % at t = RC = 1 ms, then discharges when the pulse ends.">
      <div class="d-chrome"><span class="d-title">rc_step.cir</span><span class="d-run">Run</span></div>
      <div class="d-body">
        <pre class="d-netlist">${NETLIST.map((l, i) => `<span class="${i === 0 ? "d-t" : ""}">${l}</span>`).join("\n")}</pre>
        <figure class="d-fig">
          <figcaption>Figure 1. Node voltages (V)</figcaption>
          <svg viewBox="0 0 ${W} ${H}" class="d-svg" aria-hidden="true">
            <line x1="${PAD_L}" y1="8" x2="${PAD_L}" y2="${H - PAD_B}" class="d-axis"/>
            <line x1="${PAD_L}" y1="${H - PAD_B}" x2="${W - 6}" y2="${H - PAD_B}" class="d-axis"/>
            <text x="${PAD_L - 6}" y="18" class="d-tick" text-anchor="end">1</text>
            <text x="${PAD_L - 6}" y="${H - PAD_B + 4}" class="d-tick" text-anchor="end">0</text>
            ${ticks}
            <g class="d-traces">
              <polyline points="${polyline(tran.x, vin.values, xmax)}" class="d-vin"/>
              <polyline points="${polyline(tran.x, vout.values, xmax)}" class="d-vout"/>
            </g>
            <g class="d-note">
              <line x1="${tauX}" y1="${tauY}" x2="${tauX}" y2="${H - PAD_B}" class="d-lead"/>
              <line x1="${PAD_L}" y1="${tauY}" x2="${tauX}" y2="${tauY}" class="d-lead"/>
              <circle cx="${tauX}" cy="${tauY}" r="3.5" class="d-dot"/>
              <text x="${tauX + 10}" y="${tauY + 34}" class="d-label">63.2 % at t = RC = 1 ms</text>
            </g>
          </svg>
          <p class="d-legend"><span class="k k-in"></span>v(in) <span class="k k-out"></span>v(out) <span class="d-src">ngspice 41 data; spicelite agrees to 1.1e-5 of peak</span></p>
        </figure>
      </div>
    </div>`;
  const stage = host.querySelector<HTMLElement>(".d-window")!;
  if (reducedMotion()) {
    stage.classList.add("poster"); // the final frame, with the annotation: the whole story at rest
    pauseButton.hidden = true;
    return;
  }
  stage.classList.add("playing");
  let userPaused = false;
  let visible = true;
  const apply = () => stage.classList.toggle("paused", userPaused || !visible || document.hidden);
  pauseButton.addEventListener("click", () => {
    userPaused = !userPaused;
    pauseButton.textContent = userPaused ? "Play demo" : "Pause demo";
    pauseButton.setAttribute("aria-pressed", String(userPaused));
    apply();
  });
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; apply(); }).observe(stage); // nonessential loops stop off screen
  document.addEventListener("visibilitychange", apply);
}

interface Sheet { name: string; code: string; symbol: string; syntax: string; params: string[][]; stamp: string; example: string }

/** One monochrome spec sheet per element letter (Dimensional Drawing house rules: line weight, not colour). */
export function renderSheets(host: HTMLElement): void {
  const entries = Object.entries(sheets as unknown as Record<string, Sheet | string>).filter(([k]) => !k.startsWith("_")) as [string, Sheet][];
  host.innerHTML = entries.map(([letter, s], i) => `
    <article class="sheet" id="sheet-${letter}" aria-labelledby="sheet-${letter}-h">
      <header class="sheet-title">
        <span class="sheet-code">${s.code}</span>
        <h3 id="sheet-${letter}-h">${s.name}</h3>
        <span class="sheet-no">SL-EL-${String(i + 1).padStart(2, "0")}</span>
      </header>
      <div class="sheet-draw">${SYMBOLS[s.symbol] ?? ""}</div>
      <p class="sheet-syntax"><code>${escapeHtml(s.syntax)}</code></p>
      <table class="sheet-params"><thead><tr><th>Parameter</th><th>Unit</th><th>Default</th></tr></thead>
        <tbody>${s.params.map(([p, u, d]) => `<tr><td>${p}</td><td>${u}</td><td>${d}</td></tr>`).join("")}</tbody></table>
      <p class="sheet-note"><span class="nb">1</span>${escapeHtml(s.stamp)}</p>
      <p class="sheet-eg">e.g. <code>${escapeHtml(s.example)}</code></p>
    </article>`).join("");
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
