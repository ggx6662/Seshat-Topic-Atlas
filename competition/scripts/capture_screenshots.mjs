import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.SITE_URL || "http://127.0.0.1:4173/";
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "screenshots");
const PORT = 9333;

mkdirSync(OUT, { recursive: true });
const profile = mkdtempSync(join(tmpdir(), "xtzk-shot-"));
const chrome = spawn(CHROME, [
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  "--window-size=1440,1000",
  "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForChrome() {
  for (let i = 0; i < 80; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (res.ok) return;
    } catch { /* retry */ }
    await sleep(150);
  }
  throw new Error("Chrome DevTools endpoint did not start");
}

await waitForChrome();
const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const target = targets.find((t) => t.type === "page");
if (!target) throw new Error("No page target");

const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolveOpen, rejectOpen) => {
  ws.addEventListener("open", resolveOpen, { once: true });
  ws.addEventListener("error", rejectOpen, { once: true });
});

let seq = 0;
const pending = new Map();
const problems = [];
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve: done, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(msg.error.message));
    else done(msg.result);
    return;
  }
  if (msg.method === "Runtime.exceptionThrown") {
    problems.push(msg.params.exceptionDetails?.exception?.description || msg.params.exceptionDetails?.text || "exception");
  }
  if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
    problems.push(msg.params.entry.text);
  }
});

function send(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((done, reject) => pending.set(id, { resolve: done, reject }));
}

async function evaluate(expression, awaitPromise = true) {
  const res = await send("Runtime.evaluate", {
    expression,
    awaitPromise,
    returnByValue: true,
    userGesture: true,
  });
  if (res.exceptionDetails) throw new Error(res.exceptionDetails.text || "evaluate failed");
  return res.result?.value;
}

async function viewport(width, height, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", {
    width, height, deviceScaleFactor: 1, mobile,
    screenWidth: width, screenHeight: height,
  });
}

async function goto(url, wait = 900) {
  await send("Page.navigate", { url });
  await sleep(wait);
  await evaluate(`new Promise(r => {
    if (document.readyState === 'complete') r(true);
    else addEventListener('load', () => r(true), { once: true });
  })`);
}

async function shot(name, fullPage = false) {
  if (fullPage) {
    const width = await evaluate("window.innerWidth");
    const metrics = await send("Page.getLayoutMetrics");
    const height = Math.min(metrics.cssContentSize.height, 6000);
    await viewport(width, height);
    await sleep(350);
    const { data } = await send("Page.captureScreenshot", { format: "png" });
    const file = join(OUT, `${name}.png`);
    writeFileSync(file, Buffer.from(data, "base64"));
    console.log(`${name}: ${file}`);
    await viewport(width, 1000);
    await sleep(150);
    return;
  }
  const { data } = await send("Page.captureScreenshot", { format: "png" });
  const file = join(OUT, `${name}.png`);
  writeFileSync(file, Buffer.from(data, "base64"));
  console.log(`${name}: ${file}`);
}

async function run(label, fn) {
  try {
    await fn();
  } catch (err) {
    problems.push(`${label}: ${err.message}`);
    console.error(`${label} FAILED: ${err.message}`);
  }
}

await send("Page.enable");
await send("Runtime.enable");
await send("Log.enable");

await run("desktop-intro", async () => {
  await viewport(1440, 1000);
  await goto(BASE, 2200);
  await shot("desktop-intro");
});

await run("desktop-home", async () => {
  await viewport(1440, 1000);
  await goto(`${BASE}#/workshop`, 1400);
  await shot("desktop-home");
});

await run("desktop-workshop-suggest", async () => {
  await viewport(1440, 1000);
  await goto(`${BASE}#/workshop`, 1200);
  await evaluate(`(() => {
    const i = document.querySelector('#directionInput');
    i.focus();
    i.value = '医学图像';
    i.dispatchEvent(new Event('input', { bubbles: true }));
  })()`);
  await sleep(300);
  await shot("desktop-workshop-suggest");
});

await run("desktop-cat-chip", async () => {
  await goto(`${BASE}#/workshop`, 900);
  await evaluate(`document.querySelector('[data-action="intake-mode"][data-mode="search"]')?.click()`);
  await sleep(250);
  await evaluate(`Array.from(document.querySelectorAll('[data-action="discover-cat"]')).find(c => c.dataset.cat === '计算机视觉')?.click()`);
  await sleep(500);
  await shot("desktop-cat-chip");
  await goto(`${BASE}#/workshop`, 900);
});

await run("desktop-tags", async () => {
  await evaluate(`document.querySelector('[data-action="intake-mode"][data-mode="tags"]')?.click()`);
  await sleep(350);
  await evaluate(`document.querySelector('[data-action="toggle-app"][data-id="med-imaging"]')?.click()`);
  await sleep(450);
  await shot("desktop-tags");
});

await run("desktop-browse", async () => {
  await evaluate(`document.querySelector('[data-action="intake-mode"][data-mode="browse"]')?.click()`);
  await sleep(350);
  await evaluate(`(() => {
    const cats = Array.from(document.querySelectorAll('.browse-cat'));
    cats.find((btn, i) => i > 0 && !btn.disabled)?.click();
  })()`);
  await sleep(350);
  await shot("desktop-browse");
  await goto(`${BASE}#/workshop`, 1200);
});

await run("desktop-results", async () => {
  await goto(`${BASE}?v=results#/workshop`, 1200);
  await evaluate(`(() => {
    const i = document.querySelector('#directionInput');
    i.value = '红外小目标检测';
    i.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('#generateBtn').click();
  })()`);
  await sleep(1200);
  await shot("desktop-review");
  await evaluate(`document.querySelector('[data-action="confirm-direction"]')?.click()`);
  await sleep(2600);
  await shot("desktop-results");
});

await run("desktop-detail", async () => {
  await viewport(1440, 1200);
  await evaluate(`(() => {
    document.querySelector('[data-action="tab"][data-tab="card"]')?.click();
    const detail = document.querySelector('#detailPanel');
    const body = document.querySelector('.detail-body');
    const bench = document.querySelector('.bench-cards');
    if (detail) window.scrollTo({ top: detail.getBoundingClientRect().top + window.scrollY - 72, behavior: 'instant' });
    if (body && bench) {
      const bodyRect = body.getBoundingClientRect();
      const benchRect = bench.getBoundingClientRect();
      body.scrollTop += benchRect.top - bodyRect.top - 60;
    }
  })()`);
  await sleep(350);
  await shot("desktop-detail");
  await viewport(1440, 1000);
});

await run("desktop-diagnosis", async () => {
  await evaluate(`document.querySelector('[data-action="tab"][data-tab="diagnosis"]').click()`);
  await sleep(250);
  await evaluate(`document.querySelector('[data-action="load-sample"]').click()`);
  await sleep(2600);
  await viewport(1440, 1200);
  await evaluate(`(() => {
    const detail = document.querySelector('#detailPanel');
    const body = document.querySelector('.detail-body');
    const target = document.querySelector('.diag-result');
    if (!detail || !body || !target) return;
    window.scrollTo({ top: detail.getBoundingClientRect().top + window.scrollY - 72, behavior: 'instant' });
    const bodyRect = body.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    body.scrollTop += targetRect.top - bodyRect.top - 8;
  })()`);
  await sleep(300);
  await shot("desktop-diagnosis");
  await viewport(1440, 1000);
});

await run("desktop-plan", async () => {
  await evaluate(`document.querySelector('[data-action="tab"][data-tab="card"]').click()`);
  await sleep(200);
  await evaluate(`document.querySelector('[data-action="save-idea"]').click()`);
  await sleep(2600);
  await evaluate(`location.hash = '#/plan'`);
  await sleep(900);
  await shot("desktop-plan", true);
});

await run("desktop-advisors", async () => {
  await evaluate(`location.hash = '#/advisors'`);
  await sleep(1200);
  await shot("desktop-advisors", true);
});

await run("desktop-advisor-modal", async () => {
  await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="search"]')?.click()`);
  await sleep(700);
  await evaluate(`(() => {
    const input = document.querySelector('#scholarQuery');
    if (input) {
      input.value = 'Zisserman';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  })()`);
  await sleep(400);
  await evaluate(`(() => {
    const card = Array.from(document.querySelectorAll('.advisor-card')).find((c) => c.querySelector('.advisor-name')?.textContent.includes('Zisserman'));
    card?.click();
  })()`);
  await sleep(600);
  await shot("desktop-advisor-modal");
  await evaluate(`(() => {
    const panel = document.querySelector('.advisor-modal-panel');
    if (panel) panel.scrollTop = panel.scrollHeight;
  })()`);
  await sleep(350);
  await shot("desktop-advisor-links");
});

await run("desktop-advisor-orcid", async () => {
  await evaluate(`document.querySelector('[data-action="advisor-papers"]')?.click()`);
  await sleep(2200);
  await shot("desktop-papers");
  await evaluate(`document.querySelector('[data-action="paper-clear-scholar"]')?.click()`);
  await sleep(600);
  await shot("desktop-papers-all");
});

await run("desktop-advisors-list", async () => {
  await evaluate(`location.hash = '#/advisors'`);
  await sleep(1400);
  await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="search"]')?.click()`);
  await sleep(700);
  await evaluate(`(() => {
    const input = document.querySelector('#scholarQuery');
    if (input) {
      input.value = '';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  })()`);
  await sleep(300);
  await evaluate(`document.querySelector('[data-action="advisor-layout"][data-layout="list"]')?.click()`);
  await sleep(350);
  await shot("desktop-advisors-list", true);
  await evaluate(`document.querySelector('[data-action="advisor-layout"][data-layout="grid"]')?.click()`);
  await sleep(200);
});

await run("desktop-advisor-expanded", async () => {
  await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="search"]')?.click()`);
  await sleep(500);
  await evaluate(`(() => {
    const input = document.querySelector('#scholarQuery');
    if (input) {
      input.value = 'Yuanqing Xia';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  })()`);
  await sleep(450);
  await evaluate(`(() => {
    const card = Array.from(document.querySelectorAll('.advisor-card')).find((c) => c.querySelector('.advisor-name')?.textContent.includes('Yuanqing Xia') && c.querySelector('.advisor-inst')?.textContent.includes('北京理工'));
    card?.click();
  })()`);
  await sleep(600);
  await shot("desktop-advisor-expanded");
  await evaluate(`document.querySelector('[data-action="advisor-close"]')?.click()`);
  await sleep(300);
});

await run("desktop-advisors-institutions", async () => {
  await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="institution"]')?.click()`);
  await sleep(700);
  await shot("desktop-advisors-institutions", true);
});

await run("desktop-advisor-school", async () => {
  await evaluate(`(() => {
    const input = document.querySelector('#institutionQuery');
    if (input) {
      input.value = '中国科学技术大学';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  })()`);
  await sleep(500);
  await evaluate(`document.querySelector('.institution-row')?.click()`);
  await sleep(600);
  await shot("desktop-advisors-school");
});

await run("desktop-venues", async () => {
  await evaluate(`location.hash = '#/venues'`);
  await sleep(700);
  await evaluate(`document.querySelector('[data-action="venue-mode"][data-mode="all"]')?.click()`);
  await sleep(800);
  await shot("desktop-venues");
});

await run("desktop-venues-rec", async () => {
  await evaluate(`document.querySelector('[data-action="venue-mode"][data-mode="rec"]')?.click()`);
  await sleep(400);
  await evaluate(`(() => {
    const input = document.querySelector('#venueDirectionInput');
    if (!input) return;
    input.value = '红外小目标检测';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('[data-action="venue-search-direction"]')?.click();
  })()`);
  await sleep(1200);
  await shot("desktop-venues-rec");
});

await run("desktop-venues-list", async () => {
  await evaluate(`document.querySelector('[data-action="venue-mode"][data-mode="all"]')?.click()`);
  await sleep(700);
  await evaluate(`document.querySelector('[data-action="venue-layout"][data-layout="list"]')?.click()`);
  await sleep(400);
  await shot("desktop-venues-list");
  await evaluate(`document.querySelector('[data-action="venue-layout"][data-layout="grid"]')?.click()`);
  await sleep(250);
});

await run("desktop-venue-modal", async () => {
  await evaluate(`document.querySelector('.venue-card')?.click()`);
  await sleep(600);
  await shot("desktop-venue-modal");
  await evaluate(`document.querySelector('.venue-modal [data-action="venue-close"]')?.click()`);
  await sleep(300);
});

await run("desktop-materials", async () => {
  await evaluate(`location.hash = '#/materials'`);
  await sleep(1500);
  await shot("desktop-materials", true);
});

await run("desktop-materials-detail", async () => {
  await evaluate(`document.querySelectorAll('.material-card')[3]?.click()`);
  await sleep(450);
  await shot("desktop-materials-detail");
});

await run("desktop-materials-filter", async () => {
  await evaluate(`(() => {
    const chip = Array.from(document.querySelectorAll('.material-filter-row .chip')).find(c => c.innerText.includes('计算机视觉'));
    chip?.click();
  })()`);
  await sleep(450);
  await shot("desktop-materials-filter");
});

await run("desktop-methods", async () => {
  await evaluate(`location.hash = '#/methods'`);
  await sleep(900);
  await shot("desktop-methods", true);
});

await run("desktop-about", async () => {
  await evaluate(`location.hash = '#/about'`);
  await sleep(900);
  await shot("desktop-about", true);
});

await run("desktop-dark", async () => {
  await send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-color-scheme", value: "dark" }],
  });
  await evaluate(`location.hash = '#/workshop'`);
  await sleep(700);
  await shot("desktop-dark");
  await send("Emulation.setEmulatedMedia", { features: [] });
});

await run("tablet-results", async () => {
  await viewport(1024, 900);
  await evaluate(`location.hash = '#/workshop'`);
  await sleep(700);
  await shot("tablet-results");
  await viewport(1440, 1000);
});

await run("mobile-intro", async () => {
  await evaluate("localStorage.clear()");
  await viewport(390, 844, true);
  await goto(BASE, 1800);
  await shot("mobile-intro");
});

await run("mobile-home", async () => {
  await viewport(390, 844, true);
  await goto(`${BASE}#/workshop`, 1200);
  await send("Page.reload", { ignoreCache: true });
  await sleep(1200);
  await shot("mobile-home");
});

await run("mobile-results", async () => {
  await evaluate(`(() => {
    const i = document.querySelector('#directionInput');
    i.value = '红外小目标检测';
    i.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('#generateBtn').click();
  })()`);
  await sleep(1200);
  await shot("mobile-review");
  await evaluate(`document.querySelector('[data-action="confirm-direction"]')?.click()`);
  await sleep(2600);
  await shot("mobile-results");
  await evaluate(`document.querySelector('#detailPanel')?.scrollIntoView({ block: 'start' })`);
  await sleep(400);
  await shot("mobile-detail");
  await evaluate(`document.querySelector('.candidate-head')?.scrollIntoView({ block: 'start' })`);
  await sleep(400);
  await shot("mobile-candidates");
});

await run("mobile-materials", async () => {
  await evaluate(`location.hash = '#/materials'`);
  await sleep(900);
  await shot("mobile-materials");
});

await run("mobile-methods", async () => {
  await evaluate(`location.hash = '#/methods'`);
  await sleep(700);
  await shot("mobile-methods");
});

await run("mobile-papers", async () => {
  await evaluate(`location.hash = '#/papers'`);
  await sleep(2600);
  await shot("mobile-papers");
  await evaluate(`document.querySelectorAll('.paper-row')[2]?.scrollIntoView({ block: 'start' })`);
  await sleep(350);
  await shot("mobile-papers-list");
});

await run("mobile-institutions", async () => {
  await evaluate(`location.hash = '#/advisors'`);
  await sleep(2600);
  await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="institution"]')?.click()`);
  await sleep(700);
  await shot("mobile-advisors-institutions");
});

await run("desktop-validation", async () => {
  await viewport(1440, 1000);
  await goto(`${BASE}#/workshop`, 1000);
  await evaluate("localStorage.clear()");
  await goto(`${BASE}#/workshop`, 1200);
  await evaluate(`(() => {
    const i = document.querySelector('#directionInput');
    i.value = '12';
    i.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('#generateBtn').click();
  })()`);
  await sleep(500);
  await shot("desktop-validation");
});

console.log(problems.length ? `PROBLEMS:\n${problems.join("\n")}` : "NO_BROWSER_ERRORS");
ws.close();
chrome.kill();
await sleep(400);
try { rmSync(profile, { recursive: true, force: true }); } catch { /* noop */ }
