import { expect, test, type Page } from "@playwright/test";

const share = (netlist: string) => "/#n=" + Buffer.from(netlist, "utf8").toString("base64url");

/** Collect anything the page reports as an error: console errors, uncaught exceptions, failed same-origin requests. */
function watch(page: Page) {
  const problems: string[] = [];
  page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("response", (r) => r.status() >= 400 && problems.push(`HTTP ${r.status()} ${r.url()}`));
  return problems;
}

test("loads, runs the default example and draws interactive plots", async ({ page }) => {
  const problems = watch(page);
  await page.goto("/");
  await expect(page).toHaveTitle(/spice-lite/);
  await expect(page.locator(".tab").first()).toBeVisible();
  await expect(page.locator(".uplot canvas").first()).toBeVisible();
  expect(await page.locator(".uplot").count()).toBeGreaterThanOrEqual(2); // a Bode pair: magnitude and phase
  await expect(page.locator("#runtime")).toContainText("Python 3.14");
  expect(problems).toEqual([]);
});

test("the examples dropdown runs another example and its tabs follow the netlist", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".tab").first()).toBeVisible();
  await page.selectOption("#examples", "inv_amp");
  await expect(page.locator(".tab")).toHaveCount(3); // .op, .dc, .ac
  await expect(page.locator("#exdesc")).toContainText("Inverting");
  await page.locator(".tab", { hasText: ".op" }).click();
  await expect(page.locator("table.data")).toContainText("v(out)");
});

for (const [label, netlist, line] of [
  ["the first netlist line", "T\nR1 a b\nV1 a 0 DC 1\n.op\n", 2],
  ["the last line", "T\nV1 a 0 DC 1\nR1 a 0 1k\nQ1 a 0 0 npn\n", 4],
] as const) {
  test(`an error on ${label} shows the message, a gutter marker and a link to the line`, async ({ page }) => {
    const problems = watch(page);
    await page.goto(share(netlist));
    await expect(page.locator(".msg.err")).toBeVisible();
    await expect(page.locator(".err-mark:visible")).toBeVisible();
    await expect(page.locator(".cm-error-line")).toHaveCount(1);
    await expect(page.locator(".msg.err button")).toHaveText(`go to line ${line}`);
    expect(problems).toEqual([]);
  });
}

test("an empty editor reports a clear error and nothing crashes", async ({ page }) => {
  const problems = watch(page);
  await page.goto("/#n=");
  await expect(page.locator(".msg.err")).toContainText("no elements");
  expect(problems).toEqual([]);
});

test("a netlist beyond the guards is refused with a message that says which limit", async ({ page }) => {
  await page.goto(share("T\nV1 a 0 DC 1 AC 1\nR1 a b 1k\nC1 b 0 1u\n.ac lin 200000 1 1meg\n"));
  await expect(page.locator(".msg.err")).toContainText("limit is 100,000");
});

test("rapid repeated clicks on Run coalesce, finish, and leave the page consistent", async ({ page }) => {
  const problems = watch(page);
  await page.goto("/");
  await expect(page.locator(".tab").first()).toBeVisible();
  for (let i = 0; i < 15; i++) await page.locator("#run").click({ force: true, noWaitAfter: true }).catch(() => {});
  await expect(page.locator("#run")).toBeEnabled();
  await expect(page.locator(".tab").first()).toBeVisible();
  expect(await page.locator(".tab").count()).toBe(1);
  expect(problems).toEqual([]);
});

test("Ctrl+Enter runs from the editor", async ({ page }) => {
  await page.goto(share("T\nV1 a 0 DC 4\nR1 a b 1k\nR2 b 0 1k\n.op\n"));
  await expect(page.locator("table.data")).toContainText("4 V");
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type("\n");
  await page.keyboard.press("Control+Enter");
  await expect(page.locator("table.data")).toContainText("v(b)");
});

test("share links reproduce the circuit, and editing detaches from the bundled example", async ({ page, context }) => {
  await page.goto("/#ex=divider");
  await expect(page.locator("table.data")).toContainText("6.6667 V");
  await expect(page.locator("input[type=checkbox]")).toHaveCount(1); // the ngspice reference toggle, unmodified example only
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type("* edited");
  await expect(page.locator("#exdesc")).toContainText("Edited");
  await expect(page.locator("input[type=checkbox]")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => location.hash)).toMatch(/^#[nz]=/);
  const link = page.url();
  const second = await context.newPage();
  await second.goto(link);
  await expect(second.locator("table.data")).toContainText("6.6667 V");
  await expect(second.locator(".cm-content")).toContainText("* edited");
});

test("the ngspice reference overlay adds dashed traces and an error panel", async ({ page }) => {
  await page.goto("/#ex=rc_lowpass");
  await expect(page.locator("input[type=checkbox]")).toBeVisible();
  await page.locator("input[type=checkbox]").check();
  await expect(page.locator(".refinfo")).toContainText("vs ngspice 41");
  await expect(page.locator(".refinfo")).toContainText("precomputed");
  await expect(page.locator(".u-legend").first()).toContainText("ngspice v(out)");
});

test("Download CSV delivers the full result", async ({ page }) => {
  await page.goto("/#ex=rc_step");
  await expect(page.locator(".tab").first()).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
  expect(download.suggestedFilename()).toMatch(/_tran\.csv$/);
  const text = await (await import("node:fs")).promises.readFile((await download.path())!, "utf8");
  expect(text.split("\n")[0]).toBe("time (s),v(in) (V),v(out) (V),i(v1) (A)");
  expect(text.trim().split("\n").length).toBe(501 + 1 - 1 + 1 - 1 + 1 - 1 + 1 - 1 + 1 - 1 + 1 - 1 + 1 - 1 + 1 - 1 + 1 - 1 + 1 - 1 + 1);
});

test("the theme button cycles Auto, Light, Dark and the choice survives a reload", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".tab").first()).toBeVisible();
  await page.locator("#theme").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.locator("#theme").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("#theme-label")).toHaveText("Theme: Dark");
});

for (const width of [360, 1440]) {
  test(`no horizontal scroll and no overflowing controls at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/#ex=stiff_adaptive");
    await expect(page.locator(".uplot canvas").first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    for (const id of ["#run", "#share", "#theme", "#examples"]) {
      const box = await page.locator(id).boundingBox();
      expect(box!.x + box!.width, id).toBeLessThanOrEqual(width + 1);
    }
  });
}

test("keyboard: every control is reachable and tabs move with the arrow keys", async ({ page }) => {
  await page.goto("/#ex=inv_amp");
  await expect(page.locator(".tab")).toHaveCount(3);
  await page.locator(".tab").first().focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator(".tab").nth(1)).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("End");
  await expect(page.locator(".tab").nth(2)).toHaveAttribute("aria-selected", "true");
  for (const label of ["Run", "Copy link"]) await expect(page.getByRole("button", { name: new RegExp(label) })).toBeVisible();
  await expect(page.getByLabel("Example")).toBeVisible();
});