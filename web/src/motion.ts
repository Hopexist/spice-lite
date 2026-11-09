// Motion that explains a state change, never decoration (DECISIONS D50). CSS does what CSS can (style.css); this
// module holds the few motions that need numbers: the first-load stage, the plot reveal, the .op number ticker.
// Everything here checks prefers-reduced-motion and then ends in the same final state, only without movement.

/** The worker's first-load messages, in order (worker.ts). A known stage makes the loading bar determinate. */
export const BOOT_STAGES = ["Downloading the Python runtime", "Loading numpy and scipy", "Installing spicelite"];

/** 1-based stage of a worker progress message, or 0 if it is not one of the known stages. */
export function stageOf(message: string): number {
  return BOOT_STAGES.findIndex((s) => message.startsWith(s)) + 1;
}

/** Strong ease-out (the curve of --ease-out, cubic-bezier(0.23, 1, 0.32, 1)) approximated as 1 - (1 - t)^4. */
export function easeOut(t: number): number {
  const c = Math.min(Math.max(t, 0), 1);
  return 1 - (1 - c) ** 4;
}

export function reducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** The one authored moment: a new result's traces draw in, left to right, by sliding a mask off the plot area. Only
 * the plotting area (uPlot's .u-over) is masked, so the axes and labels are readable from the first frame. */
export function revealPlot(host: HTMLElement): void {
  if (reducedMotion()) return;
  const over = host.querySelector<HTMLElement>(".u-over");
  if (!over) return;
  const mask = document.createElement("div");
  mask.className = "reveal-mask";
  mask.setAttribute("aria-hidden", "true");
  over.append(mask);
  mask.addEventListener("animationend", () => mask.remove(), { once: true });
}

/** Roll a number from `from` to `to` (300 ms, ease-out), writing format(v) each frame and format(to) last. */
export function tick(el: HTMLElement, from: number, to: number, format: (v: number) => string, ms = 300): void {
  if (reducedMotion() || from === to) {
    el.textContent = format(to);
    return;
  }
  const t0 = performance.now();
  const frame = (now: number) => {
    const p = (now - t0) / ms;
    el.textContent = format(p >= 1 ? to : from + (to - from) * easeOut(p));
    if (p < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

/** A value changed by a re-run: a short signal-tinted wash that fades out (colour only, so it stays under reduced motion). */
export function flash(el: HTMLElement): void {
  el.classList.remove("changed");
  void el.offsetWidth; // restart the animation if the same cell changes twice in a row
  el.classList.add("changed");
}
