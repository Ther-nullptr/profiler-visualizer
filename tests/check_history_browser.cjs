/* Optional browser smoke test; provide installed Playwright and Chromium paths. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

async function main() {
  const [htmlPath, outputDir] = process.argv.slice(2);
  if (!htmlPath || !outputDir || !process.env.PLAYWRIGHT_MODULE || !process.env.CHROMIUM_PATH) {
    throw new Error("Provide HTML, screenshot directory, PLAYWRIGHT_MODULE, and CHROMIUM_PATH");
  }
  const { chromium } = require(process.env.PLAYWRIGHT_MODULE);
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH,
    args: ["--no-sandbox", "--disable-gpu"],
  });
  await fs.mkdir(outputDir, { recursive: true });
  const observations = [];
  try {
    for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(pathToFileURL(path.resolve(htmlPath)).href);
      assert.equal(await page.locator(".cohort:visible").count(), 1);
      assert.equal(await page.locator(".cohort:visible .history-row").count() > 0, true);
      const sizes = await page.evaluate(() => ({
        viewport: innerWidth,
        document: document.documentElement.scrollWidth,
        bars: Array.from(document.querySelectorAll(".cohort:not([hidden]) .track span"))
          .map(bar => ({ width: bar.getBoundingClientRect().width, height: bar.getBoundingClientRect().height })),
      }));
      assert.ok(sizes.document <= sizes.viewport + 1, JSON.stringify(sizes));
      assert.ok(sizes.bars.every(bar => bar.width > 0 && bar.height > 0));
      await page.screenshot({ path: path.join(outputDir, `${name}.png`), fullPage: true });
      await page.screenshot({ path: path.join(outputDir, `${name}-viewport.png`) });
      await page.locator(".cohort:visible .history-row a").last().click();
      await page.locator(".cohort:visible details[open]").waitFor({ state: "visible" });
      assert.equal(await page.locator(".cohort:visible details[open]").count(), 1);
      await page.locator(".cohort:visible details[open] summary").click();
      await page.locator(".cohort:visible .history-row a").last().click();
      await page.locator(".cohort:visible details[open]").waitFor({ state: "visible" });
      const images = page.locator(".cohort:visible details[open] img");
      for (const image of await images.all()) {
        await image.evaluate(img => img.decode());
        assert.ok(await image.evaluate(img => img.naturalWidth > 0 && img.naturalHeight > 0));
      }
      await page.screenshot({ path: path.join(outputDir, `${name}-evidence.png`), fullPage: true });
      const groups = await page.locator("#cohort option").count();
      if (groups > 1) {
        await page.selectOption("#cohort", "0");
        assert.equal(await page.locator(".cohort:visible").getAttribute("data-cohort"), "0");
        await page.selectOption("#cohort", String(groups - 1));
        assert.equal(await page.locator(".cohort:visible").getAttribute("data-cohort"), String(groups - 1));
      }
      assert.deepEqual(errors, []);
      observations.push({ name, width, height, groups, bars: sizes.bars.length, errors });
      await page.close();
    }
  } finally {
    await browser.close();
  }
  await fs.writeFile(path.join(outputDir, "browser-check.json"), JSON.stringify(observations, null, 2));
  process.stdout.write(JSON.stringify(observations, null, 2) + "\n");
}

main().catch(error => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });
