import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.SITE_URL || "http://127.0.0.1:4173/";
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9334;
const profile = mkdtempSync(join(tmpdir(), "xtzk-check-"));
const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--window-size=1440,1000", "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const failures = [];

for (let i = 0; i < 80; i += 1) {
  try {
    if ((await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok) break;
  } catch { /* retry */ }
  await sleep(150);
}
const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((resolveOpen, rejectOpen) => {
  ws.addEventListener("open", resolveOpen, { once: true });
  ws.addEventListener("error", rejectOpen, { once: true });
});

let seq = 0;
const pending = new Map();
const consoleErrors = [];
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve: done, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(msg.error.message));
    else done(msg.result);
    return;
  }
  if (msg.method === "Runtime.exceptionThrown") consoleErrors.push(msg.params.exceptionDetails?.exception?.description || msg.params.exceptionDetails?.text || "exception");
  if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") consoleErrors.push(msg.params.entry.text);
});

function send(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((done, reject) => pending.set(id, { resolve: done, reject }));
}

async function evaluate(expression) {
  const res = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, userGesture: true });
  if (res.exceptionDetails) {
    const detail = res.exceptionDetails.exception?.description || res.exceptionDetails.text || "evaluate failed";
    throw new Error(`${detail}\nEXPR: ${expression.slice(0, 300)}`);
  }
  return res.result?.value;
}

async function viewport(width, height, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile, screenWidth: width, screenHeight: height });
}

async function goto(url, wait = 900) {
  await send("Page.navigate", { url });
  await sleep(wait);
  await evaluate(`new Promise(r => document.readyState === 'complete' ? r(true) : addEventListener('load', () => r(true), { once: true }))`);
}

async function waitFor(fn, timeout = 4000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const value = await evaluate(`(${fn.toString()})()`);
    if (value) return value;
    await sleep(100);
  }
  return null;
}

async function pressKey(key, code, vk, wait = 140) {
  await send("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
  await sleep(wait);
}

function check(condition, label) {
  if (condition) console.log(`PASS ${label}`);
  else { failures.push(label); console.log(`FAIL ${label}`); }
}

await send("Page.enable");
await send("Runtime.enable");
await send("Log.enable");

await viewport(1440, 1000);
await goto(BASE, 1800);
const introState = await evaluate(`({
  visible: getComputedStyle(document.querySelector('#introScreen')).display !== 'none',
  appHidden: getComputedStyle(document.querySelector('.app')).display === 'none',
  herald: Boolean(document.querySelector('.intro-herald')),
  art: document.querySelector('.ih-art')?.getAttribute('src') || '',
  artLoaded: (document.querySelector('.ih-art')?.naturalWidth || 0) > 0,
  caption: Boolean(document.querySelector('.intro-caption')),
  overlays: document.querySelectorAll('.ih-tag, .ih-plate, .ih-legend').length,
  footer: Boolean(document.querySelector('.intro-foot')),
  watermarkSvg: Boolean(document.querySelector('.intro-watermark svg')),
  techSvg: Boolean(document.querySelector('.intro-tech svg')),
  techVisible: (() => { const el = document.querySelector('.intro-tech'); if (!el) return false; const s = getComputedStyle(el); return s.display !== 'none' && Number(s.opacity) > 0; })(),
  dial: Boolean(document.querySelector('.ih-dial')),
  lines: document.querySelectorAll('.intro-line').length,
  quote: document.querySelector('.intro-copy h1')?.textContent?.trim() || '',
  button: document.querySelector('#introEnter')?.textContent?.includes('进入系统') || false,
  skip: Boolean(document.querySelector('#introSkip')),
  navStart: Boolean(document.querySelector('.nav-item[data-route="start"]')),
  overflow: document.documentElement.scrollWidth - window.innerWidth
})`);
check(introState.visible && introState.appHidden && introState.herald && introState.art.includes('seshat-atlas.webp') && introState.artLoaded && !introState.caption && introState.overlays === 0 && !introState.footer && introState.watermarkSvg && introState.techSvg && introState.techVisible && introState.dial && introState.lines === 3 && introState.quote.includes('巴别塔') && introState.quote.includes('桥梁') && introState.button && !introState.skip && !introState.navStart && introState.overflow <= 1, `开场页为无边框线稿插画，背景为 logo 水印与科技线层 (${introState.art})`);
await evaluate(`document.querySelector('#introEnter').click()`);
await sleep(900);
const enteredState = await evaluate(`({
  hash: location.hash,
  appVisible: getComputedStyle(document.querySelector('.app')).display !== 'none',
  introHidden: getComputedStyle(document.querySelector('#introScreen')).display === 'none',
  heading: document.querySelector('.query-brief h2')?.textContent?.trim() || ''
})`);
check(enteredState.hash === "#/workshop" && enteredState.appVisible && enteredState.introHidden && enteredState.heading.includes('可核查'), "点击「进入系统」后进入选题工坊");

const topbar = await evaluate(`({
  time: document.querySelector('#clockTime')?.textContent?.trim() || '',
  date: document.querySelector('#clockDate')?.textContent?.trim() || '',
  datetime: document.querySelector('#topClock')?.getAttribute('datetime') || '',
  theme: Boolean(document.querySelector('#themeToggle')),
  actions: document.querySelectorAll('.top-actions > *').length,
  links: document.querySelectorAll('.topbar a').length
})`);
check(/^\d{2}:\d{2}:\d{2}$/.test(topbar.time) && /^20\d{2}\.\d{2}\.\d{2} 周/.test(topbar.date) && topbar.datetime && topbar.theme && topbar.actions === 2 && topbar.links === 0, `顶栏只保留时钟与主题，时钟持续走时 (${topbar.time} · ${topbar.date})`);
// 品牌名是「塞莎特——题谱」：侧栏、面包屑、文档标题三处都要带全名，
// 且侧栏不能被截断（多出来的字 Tkinter / flex 都会直接裁掉，没有省略号）。
const brand = await evaluate(`({
  sidebar: document.querySelector(".brand-text strong")?.textContent?.trim() || "",
  intro: document.querySelector(".intro-brand-text strong")?.textContent?.trim() || "",
  crumb: document.querySelector("#crumb")?.textContent?.trim() || "",
  title: document.title,
  fits: (() => {
    const el = document.querySelector(".brand-text");
    const box = el?.parentElement;
    if (!el || !box) return false;
    return el.scrollWidth <= el.clientWidth + 1 && el.scrollWidth <= box.clientWidth + 1;
  })()
})`);
const BRAND = "塞莎特——题谱";
check(brand.sidebar === BRAND && brand.intro === BRAND && brand.crumb.startsWith(BRAND) && brand.title.includes(BRAND), `品牌名统一为「${BRAND}」(侧栏 ${brand.sidebar} / 面包屑 ${brand.crumb})`);
check(brand.fits, "侧栏品牌名在 1440 宽下未被截断");
const themeBefore = await evaluate(`document.documentElement.dataset.theme || ''`);
await evaluate(`document.querySelector('#themeToggle').click()`);
await sleep(200);
const themeAfter = await evaluate(`document.documentElement.dataset.theme || ''`);
await evaluate(`document.querySelector('#themeToggle').click()`);
await sleep(200);
check(themeAfter && themeAfter !== themeBefore, `主题切换按钮生效 (${themeBefore || "auto"} → ${themeAfter})`);
await goto(`${BASE}#/start`, 1200);
const legacyHome = await evaluate(`({
  crumb: document.querySelector("#crumb")?.textContent?.trim() || "",
  heading: document.querySelector(".query-brief h2")?.textContent?.trim() || "",
  appVisible: getComputedStyle(document.querySelector(".app")).display !== "none"
})`);
check(legacyHome.appVisible && legacyHome.crumb.includes("选题工坊") && legacyHome.heading.includes("可核查"), "旧版 #/start 地址自动回到选题工坊");
await viewport(390, 844, true);
await goto(BASE, 1600);
const introMobile = await evaluate(`({
  visible: getComputedStyle(document.querySelector('#introScreen')).display !== 'none',
  overflow: document.documentElement.scrollWidth - window.innerWidth,
  lines: document.querySelectorAll('.intro-line').length,
  quote: document.querySelector('.intro-copy h1')?.textContent?.trim() || '',
  topHidden: getComputedStyle(document.querySelector('.intro-top')).display === 'none',
  leadHidden: getComputedStyle(document.querySelector('.intro-lead')).display === 'none',
  proofHidden: getComputedStyle(document.querySelector('.intro-proof')).display === 'none',
  visualHidden: getComputedStyle(document.querySelector('.intro-visual')).display === 'none',
  footerAbsent: !document.querySelector('.intro-foot'),
  titleWidth: Math.round(document.querySelector('.intro-copy h1').getBoundingClientRect().width),
  wrapOk: [...document.querySelectorAll('.intro-line > span')].every((s) => s.getClientRects().length === 1),
  titleFits: document.querySelector('.intro-copy h1').scrollWidth <= document.querySelector('.intro-copy h1').clientWidth + 1,
  enterText: document.querySelector('#introEnter')?.textContent?.replace(/\\s+/g, ' ').trim() || '',
  enterVisible: getComputedStyle(document.querySelector('#introEnter')).display !== 'none',
  hintText: document.querySelector('.intro-mobile-hint')?.textContent?.trim() || '',
  hintVisible: getComputedStyle(document.querySelector('.intro-mobile-hint')).display !== 'none'
})`);
check(introMobile.visible && introMobile.overflow <= 1 && introMobile.lines === 3 && introMobile.quote.includes('巴别塔') && introMobile.quote.includes('桥梁') && introMobile.topHidden && introMobile.leadHidden && introMobile.proofHidden && introMobile.visualHidden && introMobile.footerAbsent && introMobile.wrapOk && introMobile.titleFits, `手机端开场页三行标题不拆字 (${introMobile.titleWidth}px)`);
check(introMobile.enterVisible && introMobile.enterText.includes('进入系统') && introMobile.hintVisible && introMobile.hintText.includes('轻触'), "手机端提供进入按钮与轻触提示");
await evaluate(`document.querySelector('#introEnter').click()`);
await sleep(900);
const mobileEntered = await evaluate(`({
  hash: location.hash,
  appVisible: getComputedStyle(document.querySelector('.app')).display !== 'none',
  introHidden: getComputedStyle(document.querySelector('#introScreen')).display === 'none'
})`);
check(mobileEntered.hash === "#/workshop" && mobileEntered.appVisible && mobileEntered.introHidden, "手机端点击「进入系统」进入选题工坊");
await goto(BASE, 1400);
await evaluate(`document.querySelector('.intro-copy h1').click()`);
await sleep(900);
const mobileTapped = await evaluate(`({
  hash: location.hash,
  appVisible: getComputedStyle(document.querySelector('.app')).display !== 'none'
})`);
check(mobileTapped.hash === "#/workshop" && mobileTapped.appVisible, "手机端轻触标题段也可进入选题工坊");

for (const [width, height, mobile] of [[1440, 1000, false], [1024, 900, false], [390, 844, true]]) {
  await viewport(width, height, mobile);
  await goto(`${BASE}#/workshop`, 1200);
  await evaluate("localStorage.clear()");
  await goto(`${BASE}#/workshop`, 1200);
  const overflow = await evaluate("document.documentElement.scrollWidth - window.innerWidth");
  check(overflow <= 1, `${width}px 工坊无横向溢出 (${overflow}px)`);
  for (const route of ["materials", "advisors", "papers", "venues", "methods", "plan", "about"]) {
    await evaluate(`location.hash = '#/${route}'`);
    await sleep(800);
    if (route === "papers") await waitFor(() => document.querySelectorAll(".paper-row").length > 0, 9000);
    if (route === "advisors") await waitFor(() => document.querySelector(".advisor-card"), 6000);
    const state = await evaluate(`({
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      heading: document.querySelector('#view h1')?.textContent?.trim() || '',
      header: Boolean(document.querySelector('#view .page-head')),
      error: document.body.innerText.includes('数据没有加载成功')
    })`);
    check(state.heading && !state.header && !state.error, `${width}px #/${route} 无页头且渲染正常 (${state.heading})`);
    check(state.overflow <= 1, `${width}px #/${route} 无横向溢出 (${state.overflow}px)`);
  }
}

await viewport(1440, 1000);
await goto(`${BASE}#/workshop`, 1200);
await evaluate(`(() => {
  const i = document.querySelector('#directionInput');
  i.value = '';
  i.focus();
  i.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await sleep(300);
const suggestState = await evaluate(`(() => {
  const box = document.querySelector('#suggestBox');
  if (!box || box.hidden) return { visible: false };
  const rect = box.getBoundingClientRect();
  const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + 18);
  return {
    visible: true,
    rows: box.querySelectorAll('button').length,
    overflow: getComputedStyle(document.querySelector('.query-panel')).overflow,
    hitInside: Boolean(hit?.closest('#suggestBox')),
    bottomVisible: rect.bottom <= window.innerHeight
  };
})()`);
check(suggestState.visible && suggestState.rows >= 5 && suggestState.overflow === "visible" && suggestState.hitInside && suggestState.bottomVisible, `联想下拉浮在页面上方、不被容器裁切 (${suggestState.rows} 条)`);
await evaluate(`(() => {
  const i = document.querySelector('#directionInput');
  i.value = '计算机视觉';
  i.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await sleep(250);
const broadSuggest = await evaluate(`(() => {
  const box = document.querySelector('#suggestBox');
  return {
    rows: box.querySelectorAll('button').length,
    header: box.querySelector('.suggest-head')?.textContent?.replace(/\\s+/g, " ") || '',
    scrollable: box.scrollHeight > box.clientHeight + 2
  };
})()`);
check(broadSuggest.rows >= 20 && broadSuggest.header.includes("↑↓ 选择") && broadSuggest.scrollable, `大类查询展示完整方向列表并可滚动 (${broadSuggest.rows} 条)`);

await evaluate(`document.querySelector('#directionInput').focus()`);
await pressKey("ArrowDown", "ArrowDown", 40);
const keyFirst = await evaluate(`({
  active: document.querySelectorAll('#suggestBox button.is-active').length,
  text: document.querySelector('#suggestBox button.is-active')?.textContent?.trim() || '',
  focusInput: document.activeElement?.id === 'directionInput'
})`);
await pressKey("ArrowDown", "ArrowDown", 40);
const keySecond = await evaluate(`document.querySelector('#suggestBox button.is-active')?.textContent?.trim() || ''`);
await pressKey("ArrowUp", "ArrowUp", 38);
const keyBack = await evaluate(`document.querySelector('#suggestBox button.is-active')?.textContent?.trim() || ''`);
check(keyFirst.active === 1 && keyFirst.text && keyFirst.focusInput && keySecond && keySecond !== keyFirst.text && keyBack === keyFirst.text, `方向联想支持 ↑↓ 循环高亮 (${keyFirst.text?.replace(/\s+/g, ' ').slice(0, 12)} · active ${keyFirst.active} · 2nd ${keySecond?.replace(/\s+/g, ' ').slice(0, 8)})`);
await pressKey("Escape", "Escape", 27);
const keyClosed = await evaluate(`({
  hidden: document.querySelector('#suggestBox')?.hidden !== false,
  focus: document.activeElement?.id || ''
})`);
check(keyClosed.hidden && keyClosed.focus === "directionInput", "Escape 关闭联想并把焦点还给输入框");
await pressKey("ArrowDown", "ArrowDown", 40);
const keyPick = await evaluate(`document.querySelector('#suggestBox button.is-active')?.dataset.name || ''`);
await pressKey("Enter", "Enter", 13, 700);
const keyEntered = await evaluate(`({
  value: document.querySelector('#directionInput')?.value || '',
  hidden: document.querySelector('#suggestBox')?.hidden !== false,
  review: Boolean(document.querySelector('.review-panel'))
})`);
check(keyPick && keyEntered.value === keyPick && keyEntered.hidden && keyEntered.review, `Enter 选中高亮方向并进入识别 (${keyEntered.value})`);
await evaluate(`document.querySelector('[data-action="reset-direction"]')?.click()`);
await sleep(400);
await evaluate(`document.querySelector('#directionInput').blur()`);
await evaluate(`(() => {
  const i = document.querySelector('#directionInput');
  i.value = '12';
  i.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('#generateBtn').click();
})()`);
await sleep(300);
const invalidQuery = await evaluate(`({
  review: Boolean(document.querySelector('.review-panel')),
  candidates: document.querySelectorAll('.candidate').length,
  hint: document.querySelector('#queryHint')?.textContent?.trim() || '',
  hintVisible: !document.querySelector('#queryHint')?.hidden,
  hintIsError: Boolean(document.querySelector('#queryHint')?.classList.contains('is-error')),
  suggestHidden: document.querySelector('#suggestBox')?.hidden !== false
})`);
check(!invalidQuery.review && invalidQuery.candidates === 0, "纯数字「12」不进入识别页也不生成候选");
check(invalidQuery.hintVisible && invalidQuery.hintIsError && invalidQuery.hint.includes("不像一个研究方向") && invalidQuery.suggestHidden, `短数字输入给出明确提示且不出联想 (${invalidQuery.hint.slice(0, 24)}…)`);
await evaluate("localStorage.clear()");
await goto(`${BASE}#/workshop`, 1000);
const exampleNames = ["单目深度估计", "红外小目标检测", "大语言模型高效推理", "联邦学习隐私保护", "蛋白质结构预测"];
for (const name of exampleNames) {
  await evaluate(`(() => {
    const i = document.querySelector('#directionInput');
    i.value = ${JSON.stringify(name)};
    i.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('#generateBtn').click();
  })()`);
  await sleep(700);
  const review = await evaluate(`(() => {
    const panel = document.querySelector('.review-panel');
    return {
      visible: Boolean(panel),
      direction: panel?.querySelector('.review-match strong')?.textContent?.trim() || '',
      category: panel?.querySelector('.review-cat')?.textContent?.trim() || '',
      terms: Array.from(panel?.querySelectorAll('.review-terms .badge') || []).map((el) => el.textContent.trim()),
      confirm: Boolean(panel?.querySelector('[data-action="confirm-direction"]')),
    };
  })()`);
  check(review.visible && review.confirm, `示例「${name}」先进入方向识别页`);
  if (name === exampleNames[0]) {
    check(Boolean(review.direction) && Boolean(review.category) && review.terms.length > 0, `识别页展示方向 / 领域 / 匹配依据 (${review.direction} · ${review.category})`);
  }
  await evaluate(`document.querySelector('[data-action="confirm-direction"]')?.click()`);
  await sleep(1100);
  const state = await evaluate(`(() => {
    const bar = document.querySelector('.recognize-bar');
    const title = document.querySelector('.detail-title')?.textContent || '';
    return bar && title.includes(${JSON.stringify(name)}) ? {
      recognized: bar.innerText.replace(/\\s+/g, " ").slice(0, 120),
      candidates: document.querySelectorAll('.candidate').length,
      rawCounts: /本地文献|导师\\s*\\d|venue\\s*\\d/.test(bar.innerText),
      error: Boolean(document.querySelector('.notice.warn')),
    } : null;
  })()`);
  check(state?.candidates >= 12 && state?.candidates <= 22, `示例「${name}」按关联强度生成 ${state?.candidates} 条候选`);
  if (state) check(!state.error && !state.rawCounts, `示例「${name}」结果栏不展示原始库计数`);
}

await evaluate(`(() => {
  const i = document.querySelector('#directionInput');
  i.value = '量子咖啡拉花感知';
  i.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('#generateBtn').click();
})()`);
await sleep(700);
const noMatchReview = await evaluate(`(() => {
  const panel = document.querySelector('.review-panel');
  return {
    badge: panel?.querySelector('.review-match .badge')?.textContent?.trim() || '',
    alternatives: panel?.querySelectorAll('.review-alt').length || 0,
    fallback: Boolean(panel?.querySelector('[data-action="confirm-direction"][data-mode="fallback"]')),
  };
})()`);
check(noMatchReview.badge.includes("未命中") && noMatchReview.fallback, `未命中方向时先说明边界并提供全库兜底 (${noMatchReview.alternatives} 个近似方向)`);
await evaluate(`document.querySelector('[data-action="reset-direction"]')?.click()`);
await sleep(400);

await evaluate(`location.hash = '#/workshop'`);
await sleep(600);
await evaluate(`(() => {
  const i = document.querySelector('#directionInput');
  i.value = '红外小目标检测';
  i.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('#generateBtn').click();
})()`);
await sleep(700);
await evaluate(`document.querySelector('[data-action="confirm-direction"]')?.click()`);
await sleep(900);
await evaluate(`document.querySelector('[data-action="tab"][data-tab="card"]')?.click()`);
await sleep(200);
await evaluate(`document.querySelector('[data-action="save-idea"]')?.click()`);
await sleep(700);
await evaluate(`location.hash = '#/plan'`);
await sleep(900);
const planSaved = await evaluate(`({
  items: document.querySelectorAll('.saved-item').length,
  title: document.querySelector('.plan-main h2')?.textContent?.trim() || '',
  stage: document.querySelector('.plan-summary .ps-item b')?.textContent?.trim() || ''
})`);
check(planSaved.items === 1 && planSaved.title.includes("红外小目标检测") && Boolean(planSaved.stage), `存入研究计划的选题可在计划页查看 (${planSaved.title})`);

const planOverview = await evaluate(`({
  overview: Boolean(document.querySelector('.plan-overview')),
  stats: document.querySelectorAll('.po-stat').length,
  next: document.querySelector('.po-next')?.textContent?.replace(/\\s+/g, ' ').trim() || '',
  track: Boolean(document.querySelector('.po-track')),
  milestones: document.querySelectorAll('.milestone').length,
  statuses: [...document.querySelectorAll('.milestone')].map((m) => m.classList.contains('current') ? 'current' : m.classList.contains('done') ? 'done' : 'next'),
  timeline: document.querySelector('.timeline-meta')?.textContent?.replace(/\\s+/g, ' ').trim() || ''
})`);
check(planOverview.overview && planOverview.stats === 4 && planOverview.track && planOverview.next.length > 0, `研究计划总览给出待办与下一步 (${planOverview.next.slice(0, 30)}…)`);
check(planOverview.milestones === 4 && planOverview.statuses.includes('current') && planOverview.timeline.includes('时间进度') && planOverview.timeline.includes('剩余'), `计划阶段时间线区分已完成 / 当前 / 下一步 (${planOverview.timeline})`);

const savedState = await evaluate(`({
  badge: document.querySelector('#savedCount')?.textContent?.trim() || '',
  toolbar: Boolean(document.querySelector('.plan-toolbar [data-action="go-workshop"]')),
  navKbd: Boolean(document.querySelector('.nav-item[data-route="workshop"] .nav-kbd'))
})`);
check(savedState.badge === "1" && savedState.toolbar && !savedState.navKbd, `计划计数紧跟导航且提供返回候选入口 (${savedState.badge} 个)`);
await evaluate(`document.querySelector('.plan-toolbar [data-action="go-workshop"]')?.click()`);
await sleep(800);
const returnedSearch = await evaluate(`({
  hash: location.hash,
  direction: document.querySelector('.recognize-bar')?.textContent?.includes('红外小目标检测') || false,
  candidates: document.querySelectorAll('.candidate-row').length,
  badge: document.querySelector('#savedCount')?.textContent?.trim() || '',
  inline: document.querySelector('#savedInline')?.textContent?.trim() || ''
})`);
check(returnedSearch.hash === "#/workshop" && returnedSearch.direction && returnedSearch.candidates >= 12 && returnedSearch.badge === "1" && returnedSearch.inline.includes("已加入 1 个"), `计划页返回后保留同一次检索 (${returnedSearch.candidates} 条候选)`);

await evaluate(`location.hash = '#/methods'`);
await sleep(900);
const studioInit = await evaluate(`({
  exists: Boolean(document.querySelector('#methodStudio')),
  readiness: document.querySelector('.studio-readiness b')?.textContent?.replace(/\\s+/g, '') || '',
  prep: document.querySelectorAll('.prep-grid input[data-prep]').length,
  stages: document.querySelectorAll('#msStage option').length,
  skills: document.querySelectorAll('#msSkill option').length,
  preview: document.querySelector('#msPreview')?.textContent || '',
  meta: document.querySelector('#msMeta')?.textContent?.trim() || ''
})`);
check(studioInit.exists && studioInit.prep === 8 && studioInit.stages === 5 && studioInit.skills > 0 && studioInit.readiness.includes('/8'), `方法论页提供阶段、学历与 8 项准备清单 (${studioInit.readiness})`);
check(studioInit.preview.includes("【工作规则】") && studioInit.preview.includes("【科研准备状态】") && studioInit.preview.includes("待补") && studioInit.meta.includes("含待补项"), `提示词按未完成准备写入待补与限制 (${studioInit.meta})`);

await evaluate(`document.querySelector('.prep-grid input[data-prep]:not(:checked)')?.click()`);
await sleep(300);
const studioPrep = await evaluate(`({
  readiness: document.querySelector('.studio-readiness b')?.textContent?.replace(/\\s+/g, '') || '',
  done: document.querySelectorAll('.prep-grid .prep-item.is-done').length,
  preview: document.querySelector('#msPreview')?.textContent || '',
  meta: document.querySelector('#msMeta')?.textContent?.trim() || ''
})`);
check(studioPrep.readiness !== studioInit.readiness && studioPrep.done === Number(studioPrep.readiness.split('/')[0]) && studioPrep.preview.includes("[已完成]") && studioPrep.meta.includes("准备"), `勾选准备项后准备度与提示词同步更新 (${studioPrep.readiness})`);

await evaluate(`(() => {
  const s = document.querySelector('#msStage');
  s.value = 'run';
  s.dispatchEvent(new Event('change', { bubbles: true }));
})()`);
await sleep(300);
const studioStage = await evaluate(`({
  value: document.querySelector('#msStage')?.value || '',
  preview: document.querySelector('#msPreview')?.textContent || '',
  meta: document.querySelector('#msMeta')?.textContent?.trim() || ''
})`);
check(studioStage.value === 'run' && studioStage.preview.includes("实验实施") && studioStage.meta.includes("字"), `切换研究阶段后提示词即时重写 (${studioStage.meta})`);

await evaluate(`(() => {
  const t = document.querySelector('#msConstraints');
  t.value = '只有一张 4090，数据需审批';
  t.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await sleep(300);
const studioConstraint = await evaluate(`document.querySelector('#msPreview')?.textContent || ''`);
check(studioConstraint.includes('只有一张 4090') && studioConstraint.includes('数据需审批'), "研究约束写入提示词并持久化");

await evaluate(`location.hash = '#/workshop'`);
await sleep(700);
await evaluate(`document.querySelectorAll('.candidate-add:not(.is-saved)')[0]?.click()`);
await sleep(500);
const quickAdded = await evaluate(`({
  hash: location.hash,
  badge: document.querySelector('#savedCount')?.textContent?.trim() || '',
  added: document.querySelectorAll('.candidate-add.is-saved').length,
  inline: document.querySelector('#savedInline')?.textContent?.trim() || ''
})`);
check(quickAdded.hash === "#/workshop" && quickAdded.badge === "2" && quickAdded.added === 2 && quickAdded.inline.includes("已加入 2 个"), `候选列表可直接加入第二条且不离开检索页 (${quickAdded.added} 条已加入)`);

await evaluate(`document.querySelector('.candidate-add.is-saved')?.click()`);
await sleep(400);
const quickRemoved = await evaluate(`({
  badge: document.querySelector('#savedCount')?.textContent?.trim() || '',
  added: document.querySelectorAll('.candidate-add.is-saved').length,
  inline: document.querySelector('#savedInline')?.textContent?.trim() || '',
  hint: document.querySelector('.candidate-add.is-saved')?.getAttribute('title') || ''
})`);
check(quickRemoved.badge === "1" && quickRemoved.added === 1 && quickRemoved.inline.includes("已加入 1 个") && quickRemoved.hint.includes("取消"), `再次点击已加入按钮可取消加入 (${quickRemoved.added} 条已加入)`);

await evaluate(`document.querySelector('.candidate-add.is-saved')?.click()`);
await sleep(400);
const allRemoved = await evaluate(`({
  hidden: document.querySelector('#savedCount')?.hidden ?? false,
  inline: document.querySelector('#savedInline')?.textContent?.trim() || '',
  added: document.querySelectorAll('.candidate-add.is-saved').length
})`);
check(allRemoved.hidden && allRemoved.added === 0 && allRemoved.inline === "", "取消全部加入后计划计数与提示同步消失");

await evaluate(`location.hash = '#/workshop'`);
await sleep(700);
await evaluate(`(() => {
  const i = document.querySelector('#directionInput');
  i.value = '12';
  i.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('#generateBtn').click();
})()`);
await sleep(400);
const staleCleared = await evaluate(`({
  candidates: document.querySelectorAll('.candidate').length,
  bar: Boolean(document.querySelector('.recognize-bar')),
  review: Boolean(document.querySelector('.review-panel')),
  hint: document.querySelector('#queryHint')?.textContent?.trim() || '',
  hintIsError: Boolean(document.querySelector('#queryHint')?.classList.contains('is-error'))
})`);
check(staleCleared.candidates === 0 && !staleCleared.bar && !staleCleared.review && staleCleared.hintIsError, "已有结果时输入无效方向会清掉旧结果并给出提示");

await evaluate(`location.hash = '#/workshop'`);
await sleep(600);
await evaluate(`(() => {
  const i = document.querySelector('#directionInput');
  i.value = '红外小目标检测';
  i.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('#generateBtn').click();
})()`);
await sleep(700);
await evaluate(`document.querySelector('[data-action="confirm-direction"]')?.click()`);
await sleep(1100);
const beforeMaterials = await evaluate(`({
  candidates: document.querySelectorAll('.candidate').length,
  detail: document.querySelector('.detail-title')?.textContent?.trim() || '',
  bar: document.querySelector('.recognize-bar')?.innerText?.replace(/\\s+/g, ' ') || ''
})`);
check(beforeMaterials.candidates >= 12, `选题结果保留候选集 (${beforeMaterials.candidates} 条)`);
await evaluate(`location.hash = '#/materials'`);
await sleep(1200);
const materialsState = await evaluate(`({
  heading: document.querySelector('#view h1')?.textContent?.trim() || '',
  cards: document.querySelectorAll('.material-card').length,
  detail: document.querySelector('.material-detail h3')?.textContent?.trim() || '',
  directions: document.querySelectorAll('.material-direction').length,
  relation: document.querySelector('.material-relation')?.innerText?.replace(/\\s+/g, ' ') || '',
  overflow: document.documentElement.scrollWidth - window.innerWidth
})`);
check(materialsState.heading.includes("素材库") && materialsState.cards > 0 && materialsState.detail && materialsState.directions > 0, `素材库展示数据集与方向关系 (${materialsState.cards} 个数据集)`);
check(materialsState.relation.includes("数据集") && materialsState.relation.includes("指标"), `素材库给出方向→数据集→指标关系 (${materialsState.relation.slice(0, 50)})`);
check(materialsState.overflow <= 1, "素材库无横向溢出");
await evaluate(`document.querySelectorAll('[data-action="material-cat"]')[1]?.click()`);
await sleep(300);
const materialsFiltered = await evaluate(`({
  cards: document.querySelectorAll('.material-card').length,
  active: document.querySelector('.material-cats .chip.active')?.textContent?.trim() || ''
})`);
check(materialsFiltered.cards > 0 && materialsFiltered.active, `素材库大类筛选生效 (${materialsFiltered.active})`);
await evaluate(`location.hash = '#/workshop'`);
await sleep(700);
const afterMaterials = await evaluate(`({
  candidates: document.querySelectorAll('.candidate').length,
  detail: document.querySelector('.detail-title')?.textContent?.trim() || '',
  bar: document.querySelector('.recognize-bar')?.innerText?.replace(/\\s+/g, ' ') || '',
  review: Boolean(document.querySelector('.review-panel'))
})`);
check(!afterMaterials.review && afterMaterials.candidates === beforeMaterials.candidates && afterMaterials.detail === beforeMaterials.detail && afterMaterials.bar.includes("红外"), `从素材库返回选题工坊保留方向与候选 (${afterMaterials.detail} · ${afterMaterials.candidates} 条)`);

await evaluate("localStorage.clear()");
await goto(`${BASE}?fresh=1#/advisors`, 1500);
const directAdvisors = await evaluate(`({
  active: document.querySelector('.tabs .tab.active')?.textContent?.trim(),
  hasInput: Boolean(document.querySelector('#scholarQuery'))
})`);
check(directAdvisors.active.includes("全部") && directAdvisors.hasInput, "无方向直达导师页默认全部学者");
await evaluate("location.hash = '#/venues'");
await sleep(800);
const directVenues = await evaluate(`({
  active: document.querySelector('.tabs .tab.active')?.textContent?.trim(),
  input: Boolean(document.querySelector('#venueDirectionInput')),
  button: Boolean(document.querySelector('[data-action="venue-search-direction"]')),
  count: document.querySelectorAll('.venue-card').length
})`);
check(directVenues.active.includes("按方向推荐") && directVenues.input && directVenues.button, `期刊页默认提供方向推荐入口 (${directVenues.count} 个结果)`);
await evaluate(`document.querySelector('[data-action="venue-mode"][data-mode="all"]')?.click()`);
await sleep(900);
const directVenuesAll = await evaluate(`({
  count: document.querySelectorAll('.venue-card').length,
  toggle: Boolean(document.querySelector('.layout-toggle'))
})`);
check(directVenuesAll.count === 701 && directVenuesAll.toggle, `期刊全部目录可切换平铺/列表 (${directVenuesAll.count} 个)`);
const firstVenue = await evaluate(`document.querySelector('.venue-card')?.dataset.name || ''`);
await evaluate(`document.querySelector('.venue-card')?.click()`);
await sleep(500);
const venueModal = await evaluate(`({
  open: Boolean(document.querySelector('.venue-modal')),
  title: document.querySelector('#venueModalTitle')?.textContent?.trim() || '',
  sections: document.querySelectorAll('.venue-modal .advisor-modal-section').length,
  stats: document.querySelectorAll('.venue-modal-stats div').length,
  site: Boolean(document.querySelector('.venue-modal .link-grid a[href^="https://"]')),
  papers: Boolean(document.querySelector('.venue-modal [data-action="venue-papers"]')),
  focusable: document.querySelectorAll('.venue-card[role="button"][tabindex="0"]').length,
  overflow: document.documentElement.scrollWidth - window.innerWidth
})`);
check(venueModal.open && venueModal.title === firstVenue && venueModal.sections >= 4 && venueModal.stats === 4 && venueModal.site && venueModal.papers && venueModal.focusable === 701 && venueModal.overflow <= 1, `点击期刊卡片打开详情说明 (${venueModal.title} · ${venueModal.sections} 段)`);
await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))`);
await sleep(300);
const venueClosed = await evaluate(`!document.querySelector('.venue-modal')`);
check(venueClosed, "Esc 关闭期刊详情");
await evaluate(`document.querySelector('.venue-card')?.click()`);
await sleep(400);
await evaluate(`document.querySelector('.venue-modal [data-action="venue-papers"]')?.click()`);
await sleep(1800);
const venuePapers = await evaluate(`({ hash: location.hash, query: document.querySelector('#paperQuery')?.value || '' })`);
check(venuePapers.hash === "#/papers" && venuePapers.query === firstVenue, `期刊详情可跳到论文库并带上名称 (${venuePapers.query})`);
await evaluate(`location.hash = '#/venues'`);
await sleep(700);
await evaluate(`document.querySelector('[data-action="venue-mode"][data-mode="all"]')?.click()`);
await sleep(900);

await viewport(390, 844, true);
await goto(`${BASE}#/workshop`, 900);
await send("Page.reload", { ignoreCache: true });
await sleep(600);
await waitFor(() => Boolean(document.querySelector('#directionInput')), 6000);
const mobileLabels = await evaluate(`(() => {
  const labels = Array.from(document.querySelectorAll('.query-label')).map((l) => l.textContent.replace(/\\s+/g, ' ').trim());
  return { count: labels.length, labels };
})()`);
check(mobileLabels.count === 1, `手机端方向输入标签只出现一次 (${mobileLabels.count})`);
await evaluate(`(() => {
  const i = document.querySelector('#directionInput');
  i.value = '红外小目标检测';
  i.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('#generateBtn').click();
})()`);
await sleep(700);
await evaluate(`document.querySelector('[data-action="confirm-direction"]')?.click()`);
await sleep(1200);
const mobileOrder = await evaluate(`(() => {
  const detail = document.querySelector('#detailPanel').getBoundingClientRect();
  const list = document.querySelector('.candidate-list').getBoundingClientRect();
  return { order: getComputedStyle(document.querySelector('#detailPanel')).order, detailTop: detail.top, listTop: list.top };
})()`);
check(mobileOrder.order === "-1" && mobileOrder.detailTop < mobileOrder.listTop, "移动端详情面板位于候选列表上方");
await evaluate(`document.querySelectorAll('.candidate')[1].click()`);
await sleep(600);
const mobileSelect = await evaluate(`({
  title: document.querySelector('.detail-title')?.textContent?.trim(),
  selected: document.querySelectorAll('.candidate.selected').length,
  detailTop: document.querySelector('#detailPanel').getBoundingClientRect().top
})`);
check(mobileSelect.title && mobileSelect.selected === 1 && mobileSelect.detailTop < 220, "移动端点候选后滚到对应详情");
await evaluate(`location.hash = '#/advisors'`);
await sleep(2600);
await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="institution"]')?.click()`);
await sleep(700);
const mobileInstitution = await evaluate(`({
  overflow: document.documentElement.scrollWidth - window.innerWidth,
  rows: document.querySelectorAll('.institution-row').length,
  clipped: Array.from(document.querySelectorAll('.institution-row')).some((row) => row.getBoundingClientRect().right > window.innerWidth + 1)
})`);
check(mobileInstitution.rows > 0 && mobileInstitution.overflow <= 1 && !mobileInstitution.clipped, `手机端院校目录无横向溢出 (${mobileInstitution.overflow}px · ${mobileInstitution.rows} 行)`);

await evaluate(`location.hash = '#/venues'`);
await sleep(700);
await evaluate(`document.querySelector('[data-action="venue-mode"][data-mode="rec"]')?.click()`);
await sleep(500);
const mobileVenue = await evaluate(`({
  overflow: document.documentElement.scrollWidth - window.innerWidth,
  input: Boolean(document.querySelector('#venueDirectionInput')),
  toggle: Boolean(document.querySelector('[data-action="venue-layout"]')),
  cards: document.querySelectorAll('.venue-card').length
})`);
check(mobileVenue.input && mobileVenue.toggle && mobileVenue.overflow <= 1, `手机端期刊页提供方向搜索与视图切换 (${mobileVenue.cards} 个)`);
await evaluate(`document.querySelector('[data-action="venue-layout"][data-layout="list"]')?.click()`);
await sleep(350);
const mobileVenueList = await evaluate(`({
  isList: Array.from(document.querySelectorAll('.venue-grid')).some((el) => el.classList.contains('is-list')),
  overflow: document.documentElement.scrollWidth - window.innerWidth,
  clipped: Array.from(document.querySelectorAll('.venue-card')).some((card) => card.getBoundingClientRect().right > window.innerWidth + 1)
})`);
check(mobileVenueList.isList && mobileVenueList.overflow <= 1 && !mobileVenueList.clipped, `手机端期刊列表无横向溢出 (${mobileVenueList.overflow}px)`);
await evaluate(`document.querySelector('.venue-card')?.click()`);
await sleep(600);
const mobileVenueModal = await evaluate(`(() => {
  const panel = document.querySelector('.venue-modal .advisor-modal-panel');
  const r = panel?.getBoundingClientRect();
  return {
    open: Boolean(panel),
    within: Boolean(r) && r.left >= 0 && r.right <= window.innerWidth + 1,
    cols: getComputedStyle(document.querySelector('.venue-modal-stats')).gridTemplateColumns.split(' ').length,
    overflow: document.documentElement.scrollWidth - window.innerWidth
  };
})()`);
check(mobileVenueModal.open && mobileVenueModal.within && mobileVenueModal.cols === 2 && mobileVenueModal.overflow <= 1, `手机端期刊详情为底部抽屉且数据条 2×2 (${mobileVenueModal.cols} 列)`);
await evaluate(`document.querySelector('.venue-modal [data-action="venue-close"]')?.click()`);
await sleep(300);
await evaluate(`document.querySelector('[data-action="venue-layout"][data-layout="grid"]')?.click()`);
await sleep(250);

await viewport(1440, 1000);
await goto(`${BASE}#/workshop`, 1200);
await evaluate(`localStorage.clear()`);
await send("Page.reload", { ignoreCache: true });
await sleep(1600);
await evaluate(`document.querySelector('[data-action="intake-mode"][data-mode="tags"]')?.click()`);
await sleep(400);
const tagInitial = await evaluate(`({
  tabs: document.querySelectorAll('.intake-tab').length,
  chips: document.querySelectorAll('.tag-chip').length,
  results: document.querySelectorAll('.tag-result').length
})`);
check(tagInitial.tabs === 3 && tagInitial.chips >= 37, `标签组合入口可用 (${tagInitial.chips} 个标签)`);
await evaluate(`document.querySelector('[data-action="toggle-app"][data-id="med-imaging"]')?.click()`);
await sleep(350);
const tagPicked = await evaluate(`({
  active: document.querySelectorAll('.tag-chip.active').length,
  results: document.querySelectorAll('.tag-result').length,
  first: document.querySelector('.tag-result b')?.textContent?.trim() || '',
  score: document.querySelector('.tag-result-score')?.textContent?.trim() || ''
})`);
check(tagPicked.active >= 1 && tagPicked.results >= 1 && tagPicked.first && Number(tagPicked.score) > 0, `选择应用场景后给出组合方向 (${tagPicked.first} / ${tagPicked.score})`);
await evaluate(`document.querySelector('.tag-result')?.click()`);
await sleep(900);
const tagReview = await evaluate(`(() => {
  const panel = document.querySelector('.review-panel');
  const text = panel?.innerText || '';
  return {
    visible: Boolean(panel),
    badge: panel?.querySelector('.review-match .badge')?.textContent?.trim() || '',
    apps: Array.from(panel?.querySelectorAll('.badge-accent') || []).map((el) => el.textContent.trim()).join(' '),
    bench: panel?.querySelectorAll('.review-bench-item').length || 0,
    sideCards: panel?.querySelectorAll('.review-side').length || 0,
    demoCopy: text.includes('这次不做什么') || text.includes('生成后会得到'),
    next: Boolean(panel?.querySelector('.review-next'))
  };
})()`);
check(tagReview.visible && tagReview.badge.includes("标签组合命中") && tagReview.apps.includes("医学影像") && tagReview.next, `标签组合进入识别页并保留场景 (${tagReview.apps.slice(0, 30)})`);
check(tagReview.bench === 0 && tagReview.sideCards === 0 && !tagReview.demoCopy, "识别页已去除演示基准卡与测试说明");
await evaluate(`document.querySelector('[data-action="confirm-direction"]')?.click()`);
await sleep(1100);
const tagResult = await evaluate(`(() => {
  const candidates = document.querySelectorAll('.candidate');
  const dims = Array.from(document.querySelectorAll('.dim-row')).map((row) => ({
    label: row.querySelector('.dim-label')?.textContent?.trim(),
    value: row.querySelector('.dim-value')?.textContent?.trim(),
    delta: row.querySelector('.dim-delta')?.textContent?.trim(),
    rank: row.querySelector('.dim-rank')?.textContent?.trim(),
    width: row.querySelector('.dim-fill')?.style.width,
    median: row.querySelector('.dim-median')?.style.left
  }));
  return { candidates: candidates.length, dims };
})()`);
const widths = tagResult.dims.map((d) => d.width);
const medians = tagResult.dims.map((d) => d.median);
check(tagResult.dims.length === 3 && tagResult.dims.every((d) => d.value && d.rank.includes("/") && d.delta.includes("中位")) && new Set(widths).size > 1 && new Set(medians).size > 1, `三维度给出组内排名、中位差与不同刻度 (${widths.join(" / ")})`);

await evaluate(`document.querySelector('[data-action="edit-direction"]')?.click()`);
await sleep(400);
const backToReview = await evaluate(`(() => {
  const panel = document.querySelector('.review-panel');
  return {
    visible: Boolean(panel),
    apps: panel?.querySelectorAll('.review-terms .badge-accent').length || 0,
    query: panel?.querySelector('.review-query')?.textContent?.trim() || '',
  };
})()`);
check(backToReview.visible && backToReview.query.length > 0, `结果页可回到方向确认并保留输入 (${backToReview.query})`);
await evaluate(`document.querySelector('[data-action="reset-direction"]')?.click()`);
await sleep(400);
await evaluate(`document.querySelector('[data-action="intake-mode"][data-mode="browse"]')?.click()`);
await sleep(400);
await evaluate(`(() => {
  const cats = Array.from(document.querySelectorAll('.browse-cat'));
  const target = cats.find((btn, i) => i > 0 && !btn.disabled);
  target?.click();
})()`);
await sleep(350);
const browseState = await evaluate(`({
  cats: document.querySelectorAll('.browse-cat').length,
  items: document.querySelectorAll('.browse-entry').length,
  active: document.querySelector('.browse-cat.active')?.textContent?.replace(/\\s+/g, ' ').trim() || '',
  assoc: Array.from(document.querySelectorAll('.browse-assoc em')).map((el) => el.textContent.trim()),
  subhead: document.querySelector('.browse-sub-head')?.innerText?.replace(/\\s+/g, ' ') || ''
})`);
check(browseState.cats >= 20 && browseState.items > 0 && browseState.active && browseState.subhead.includes("关联强度"), `全库目录支持大类→小类双层浏览 (${browseState.active} · ${browseState.items} 个方向)`);
check(browseState.assoc.length === browseState.items && browseState.assoc.every((x) => ["强关联", "中关联", "弱关联"].includes(x)), `方向按关键词关联强度标注 (${browseState.assoc.slice(0, 3).join(" / ")})`);
await evaluate(`document.querySelector('[data-action="browse-cat"][data-cat=""]')?.click()`);
await sleep(250);
await evaluate(`(() => {
  const input = document.querySelector('#browseQuery');
  input.focus();
  input.value = '医学';
  input.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await sleep(350);
const browseFiltered = await evaluate(`({
  items: document.querySelectorAll('.browse-item').length,
  value: document.querySelector('#browseQuery')?.value,
  focused: document.activeElement?.id
})`);
check(browseFiltered.items > 0 && browseFiltered.value === "医学" && browseFiltered.focused === "browseQuery", `目录筛选保留输入焦点 (${browseFiltered.items} 个结果)`);
await evaluate(`document.querySelector('.browse-item')?.click()`);
await sleep(900);
const browseReview = await evaluate(`document.querySelector('.review-match .badge')?.textContent?.trim() || ''`);
check(browseReview.includes("目录选择"), `目录选择进入识别页 (${browseReview})`);
await evaluate(`document.querySelector('[data-action="confirm-direction"]')?.click()`);
await sleep(1000);
await evaluate(`location.hash = '#/advisors'`);
await sleep(1200);
const regionState = await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  const groups = select ? Array.from(select.querySelectorAll('optgroup')).map((g) => g.label) : [];
  const options = select ? select.querySelectorAll('option').length : 0;
  return { groups, options, cards: document.querySelectorAll('.advisor-card').length };
})()`);
check(regionState.groups.length >= 9 && regionState.options >= 30 && regionState.cards > 0, `导师地区目录覆盖完整省份与海外 (${regionState.groups.length} 组 / ${regionState.options} 项)`);
await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  if (!select) return;
  select.value = '美国';
  select.dispatchEvent(new Event('change', { bubbles: true }));
})()`);
await sleep(300);
const usFilter = await evaluate(`({
  selected: document.querySelector('#advisorProvince')?.value,
  meta: document.querySelector('#advisorMeta')?.textContent?.trim() || '',
  overflow: document.documentElement.scrollWidth - window.innerWidth
})`);
check(usFilter.selected === "美国" && usFilter.meta.includes("美国") && usFilter.overflow <= 1, `导师地区筛选按完整目录生效 (${usFilter.meta})`);
await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="institution"]')?.click()`);
await sleep(600);
const schoolDirectory = await evaluate(`(() => {
  const rows = Array.from(document.querySelectorAll('.institution-row'));
  const select = document.querySelector('#advisorProvince');
  const pending = select ? Array.from(select.options).find((opt) => opt.value === '__unknown') : null;
  const withRegion = rows.filter((row) => {
    const small = row.querySelector('.institution-main small')?.textContent.replace(/\\s+/g, ' ').trim() || '';
    return small && !/地区待核验/.test(small);
  }).length;
  return {
    active: document.querySelector('[data-action="advisor-mode"][data-mode="institution"]')?.classList.contains('active') || false,
    rows: rows.length,
    first: rows[0]?.textContent.replace(/\\s+/g, ' ').trim() || '',
    meta: document.querySelector('#institutionMeta')?.textContent?.trim() || '',
    options: select ? select.querySelectorAll('option').length : 0,
    pending: Boolean(pending),
    withRegion
  };
})()`);
check(schoolDirectory.active && schoolDirectory.rows >= 20 && schoolDirectory.meta.includes("所院校") && schoolDirectory.pending && schoolDirectory.withRegion >= Math.min(20, schoolDirectory.rows), `院校目录按校址归档并保留待核验分组 (${schoolDirectory.meta} · ${schoolDirectory.rows} 行)`);
await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  if (select) { select.value = '北京'; select.dispatchEvent(new Event('change', { bubbles: true })); }
})()`);
await sleep(500);
const regionSchools = await evaluate(`({
  meta: document.querySelector('#institutionMeta')?.textContent?.trim() || '',
  rows: document.querySelectorAll('.institution-row').length,
  regions: Array.from(document.querySelectorAll('.institution-main small')).map((el) => el.textContent.replace(/\\s+/g, ' ').trim())
})`);
check(regionSchools.meta.includes("北京") && regionSchools.rows > 0 && regionSchools.regions.every((t) => /北京/.test(t)), `院校目录可按院校所在地区筛选 (${regionSchools.meta} · ${regionSchools.rows} 所)`);
await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  if (select) { select.value = ''; select.dispatchEvent(new Event('change', { bubbles: true })); }
})()`);
await sleep(400);
const schoolSearch = await evaluate(`(() => {
  const input = document.querySelector('#institutionQuery');
  if (!input) return null;
  input.value = '中国科学技术大学';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()`);
await sleep(400);
const schoolHit = await evaluate(`({
  rows: document.querySelectorAll('.institution-row').length,
  first: document.querySelector('.institution-row')?.textContent.replace(/\\s+/g, ' ').trim() || '',
  meta: document.querySelector('#institutionMeta')?.textContent?.trim() || ''
})`);
check(Boolean(schoolSearch) && schoolHit.rows >= 1 && schoolHit.first.includes("中国科学技术大学"), `院校目录支持校名检索 (${schoolHit.meta})`);
await evaluate(`document.querySelector('.institution-row')?.click()`);
await sleep(500);
const schoolView = await evaluate(`({
  head: document.querySelector('.institution-head-main')?.textContent.replace(/\\s+/g, ' ').trim() || '',
  meta: document.querySelector('#advisorMeta')?.textContent?.trim() || '',
  cards: document.querySelectorAll('.advisor-card').length,
  back: Boolean(document.querySelector('[data-action="advisor-institution-back"]'))
})`);
check(schoolView.head.includes("中国科学技术大学") && schoolView.meta.includes("该院校") && schoolView.cards > 0 && schoolView.back, `点进院校查看对应导师 (${schoolView.meta} · ${schoolView.cards} 位)`);
await evaluate(`document.querySelector('[data-action="advisor-institution-back"]')?.click()`);
await sleep(400);
await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="search"]')?.click()`);
await sleep(500);
const pendingScholars = await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  const badges = document.querySelectorAll('.advisor-card .badge').length;
  const pendingBadges = document.querySelectorAll('.advisor-card .badge-pending').length;
  return {
    meta: document.querySelector('#advisorMeta')?.textContent?.trim() || '',
    cards: document.querySelectorAll('.advisor-card').length,
    badges,
    pendingBadges,
    hasPendingOption: Boolean(select && Array.from(select.options).some((opt) => opt.value === '__unknown'))
  };
})()`);
check(pendingScholars.cards > 0 && pendingScholars.badges > 0 && pendingScholars.hasPendingOption, `导师目录保留待核验分组并显式标注 (${pendingScholars.meta})`);
await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  if (select) { select.value = '__unknown'; select.dispatchEvent(new Event('change', { bubbles: true })); }
})()`);
await sleep(500);
const pendingOnly = await evaluate(`({
  meta: document.querySelector('#advisorMeta')?.textContent?.trim() || '',
  cards: document.querySelectorAll('.advisor-card').length,
  pendingBadges: document.querySelectorAll('.advisor-card .badge-pending').length
})`);
check(pendingOnly.cards > 0 && pendingOnly.pendingBadges === pendingOnly.cards && pendingOnly.meta.includes("待核验"), `待核验分组可筛选并逐卡标注 (${pendingOnly.meta} · ${pendingOnly.cards} 位)`);
await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  if (select) { select.value = ''; select.dispatchEvent(new Event('change', { bubbles: true })); }
})()`);
await sleep(400);
await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="direction"]')?.click()`);
await sleep(500);
const emptyRegion = await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  if (!select) return "";
  const options = Array.from(select.options).filter((opt) => opt.value && opt.value !== '__unknown' && /（0）/.test(opt.textContent));
  const option = options.find((opt) => ["加拿大", "日本", "新加坡", "澳大利亚"].includes(opt.value)) || options[0];
  if (!option) return "";
  select.value = option.value;
  select.dispatchEvent(new Event('change', { bubbles: true }));
  return option.value;
})()`);
await sleep(350);
const emptyState = await evaluate(`({
  cards: document.querySelectorAll('.advisor-card').length,
  button: Boolean(document.querySelector('[data-action="advisor-region-all"]'))
})`);
check(Boolean(emptyRegion) && emptyState.cards === 0 && emptyState.button, `方向内无该地区学者时给出全部索引入口 (${emptyRegion})`);
await evaluate(`document.querySelector('[data-action="advisor-region-all"]')?.click()`);
await sleep(1800);
const usAll = await evaluate(`({
  mode: document.querySelector('[data-action="advisor-mode"][data-mode="search"]')?.classList.contains('active') || false,
  meta: document.querySelector('#advisorMeta')?.textContent?.trim() || '',
  cards: document.querySelectorAll('.advisor-card').length
})`);
check(usAll.mode && usAll.cards > 0 && !usAll.meta.includes(emptyRegion), `空地区可清空筛选转到全部学者 (${usAll.meta} · ${usAll.cards} 位)`);
await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  if (!select) return;
  select.value = '';
  select.dispatchEvent(new Event('change', { bubbles: true }));
})()`);
await sleep(300);
const initialCards = await evaluate(`document.querySelectorAll('.advisor-card').length`);
await evaluate(`document.querySelector('[data-action="advisor-layout"][data-layout="list"]')?.click()`);
await sleep(250);
const listLayout = await evaluate(`({
  isList: document.querySelector('.advisor-grid')?.classList.contains('is-list'),
  cards: document.querySelectorAll('.advisor-card').length,
  active: document.querySelector('.layout-toggle button.active')?.textContent?.trim() || ''
})`);
check(listLayout.isList && listLayout.cards === initialCards && listLayout.active.includes("列表"), `导师页支持平铺/列表切换 (列表 ${listLayout.cards} 位)`);
const moreBefore = await evaluate(`document.querySelectorAll('.advisor-card').length`);
await evaluate(`document.querySelector('[data-action="advisor-more"]')?.click()`);
await sleep(300);
const moreAfter = await evaluate(`({
  cards: document.querySelectorAll('.advisor-card').length,
  meta: document.querySelector('#advisorMeta')?.textContent?.trim() || '',
  more: Boolean(document.querySelector('[data-action="advisor-more"]'))
})`);
check(moreAfter.cards > moreBefore && moreAfter.meta.includes("已显示"), `导师列表可继续加载全部学者 (${moreBefore} → ${moreAfter.cards})`);
await evaluate(`document.querySelector('[data-action="advisor-layout"][data-layout="grid"]')?.click()`);
await sleep(200);
await evaluate(`(() => {
  const select = document.querySelector('#advisorProvince');
  if (select) { select.value = ''; select.dispatchEvent(new Event('change', { bubbles: true })); }
})()`);
await sleep(300);
const pickedAdvisor = await evaluate(`(() => {
  const cards = Array.from(document.querySelectorAll('.advisor-card'));
  const target = cards.find((card) => /已收录/.test(card.querySelector('.advisor-foot .small.muted')?.textContent || '')) || cards[0];
  const name = target?.querySelector('.advisor-name')?.textContent?.trim() || '';
  target?.click();
  return name;
})()`);
await sleep(500);
const modalState = await evaluate(`(() => {
  const modal = document.querySelector('.advisor-modal');
  const links = Array.from(modal?.querySelectorAll('.link-grid a') || []).map((a) => ({
    href: a.getAttribute('href') || '',
    text: a.textContent.replace(/\\s+/g, ' ').trim()
  }));
  return {
    visible: Boolean(modal),
    title: modal?.querySelector('#advisorModalTitle')?.textContent?.trim() || '',
    links,
    orcid: links.some((l) => l.href.includes('orcid.org')),
    bing: links.some((l) => l.href.includes('bing.com')),
    realHome: links.some((l) => l.text.includes('个人主页')),
    institution: links.some((l) => l.text.includes('院校官方站点')),
    note: modal?.querySelector('.advisor-modal-section:last-child p')?.textContent?.trim() || '',
    overflow: document.documentElement.scrollWidth - window.innerWidth
  };
})()`);
check(modalState.visible && modalState.title === pickedAdvisor && modalState.links.length >= 3 && !modalState.bing, `导师卡片可点开真实主页与作者入口 (${modalState.title} · ${modalState.links.length} 个入口)`);
check(modalState.institution || modalState.realHome, `导师详情提供院校官网或个人主页 (${modalState.institution ? "院校官网" : "个人主页"})`);
check(modalState.note.includes("未收录") || modalState.realHome, "未收录个人主页时不提供搜索跳转");
check(modalState.overflow <= 1, "导师详情弹窗无横向溢出");
await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))`);
await sleep(350);
const modalClosed = await evaluate(`!document.querySelector('.advisor-modal')`);
check(modalClosed, "导师详情支持 Escape 关闭");

// ---- ORCID 扩面：原先只有标识的学者也有活跃度与近期论文 ----
await evaluate(`location.hash = '#/advisors'`);
await sleep(500);
await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="search"]')?.click()`);
await waitFor(() => document.querySelector("#scholarQuery"), 5000);
await evaluate(`(() => {
  const input = document.querySelector('#scholarQuery');
  input.value = 'Yuanqing Xia';
  input.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await waitFor(() => Array.from(document.querySelectorAll(".advisor-card")).some((c) => c.querySelector(".advisor-name")?.textContent.includes("Yuanqing Xia") && c.querySelector(".advisor-inst")?.textContent.includes("北京理工")), 6000);
await evaluate(`(() => {
  const card = Array.from(document.querySelectorAll('.advisor-card')).find((c) => c.querySelector('.advisor-name')?.textContent.includes('Yuanqing Xia') && c.querySelector('.advisor-inst')?.textContent.includes('北京理工'));
  card?.click();
})()`);
await waitFor(() => document.querySelector(".advisor-modal"), 5000);
const expandedState = await evaluate(`(() => {
  const modal = document.querySelector('.advisor-modal');
  return {
    title: modal?.querySelector('#advisorModalTitle')?.textContent?.trim() || '',
    bars: modal?.querySelectorAll('.activity-col').length || 0,
    works: modal?.querySelectorAll('.work-list li').length || 0,
    papersBtn: Boolean(modal?.querySelector('[data-action="advisor-papers"]')),
    verified: /ORCID 已核验/.test(modal?.textContent || ''),
    note: modal?.textContent || ''
  };
})()`);
check(expandedState.title.includes("Yuanqing Xia") && expandedState.bars === 6 && expandedState.works >= 1, `新纳入 ORCID 快照的学者展示活跃度与近期论文 (${expandedState.works} 篇)`);
check(/公开记录包含中国院校任职/.test(expandedState.note) && !expandedState.verified && !expandedState.papersBtn, "新增覆盖学者标注为姓名与作品匹配，且不显示空论文库入口");
await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))`);
await sleep(300);

// ---- 同名但海外任职的 ORCID 不自动合并 ----
await evaluate(`(() => {
  const input = document.querySelector('#scholarQuery');
  input.value = 'Ling Sun';
  input.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await waitFor(() => Array.from(document.querySelectorAll(".advisor-card")).some((c) => c.querySelector(".advisor-name")?.textContent.includes("Ling Sun") && c.querySelector(".advisor-inst")?.textContent.includes("山东")), 6000);
await evaluate(`(() => {
  const card = Array.from(document.querySelectorAll('.advisor-card')).find((c) => c.querySelector('.advisor-name')?.textContent.includes('Ling Sun') && c.querySelector('.advisor-inst')?.textContent.includes('山东'));
  card?.click();
})()`);
await waitFor(() => document.querySelector(".advisor-modal"), 5000);
const overseasState = await evaluate(`(() => {
  const modal = document.querySelector('.advisor-modal');
  return {
    title: modal?.querySelector('#advisorModalTitle')?.textContent?.trim() || '',
    bars: modal?.querySelectorAll('.activity-col').length || 0,
    works: modal?.querySelectorAll('.work-list li').length || 0,
    note: modal?.textContent || ''
  };
})()`);
check(overseasState.title.includes("Ling Sun") && overseasState.bars === 0 && overseasState.works === 0 && /任职机构均在海外/.test(overseasState.note), "同名但仅有海外任职的 ORCID 不合并、不展示其论文");
await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))`);
await sleep(300);

// ---- ORCID 核验：Zisserman 的机构与真实链接 ----
await evaluate(`location.hash = '#/advisors'`);
await sleep(600);
await evaluate(`document.querySelector('[data-action="advisor-mode"][data-mode="search"]')?.click()`);
await waitFor(() => document.querySelector("#scholarQuery"), 5000);
await evaluate(`(() => {
  const input = document.querySelector('#scholarQuery');
  input.value = 'Zisserman';
  input.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await waitFor(() => Array.from(document.querySelectorAll(".advisor-name")).some((el) => el.textContent.includes("Zisserman")), 5000);
await evaluate(`(() => {
  const card = Array.from(document.querySelectorAll('.advisor-card')).find((c) => c.querySelector('.advisor-name')?.textContent.includes('Zisserman'));
  card?.click();
})()`);
await waitFor(() => document.querySelector(".advisor-modal"), 5000);
const zState = await evaluate(`(() => {
  const modal = document.querySelector('.advisor-modal');
  const links = Array.from(modal?.querySelectorAll('.link-grid a') || []).map((a) => a.getAttribute('href') || '');
  return {
    title: modal?.querySelector('#advisorModalTitle')?.textContent?.trim() || '',
    inst: modal?.querySelector('.advisor-modal-head p')?.textContent?.trim() || '',
    links,
    verified: /ORCID 已核验/.test(modal?.textContent || ''),
    bars: modal?.querySelectorAll('.activity-col').length || 0,
    works: modal?.querySelectorAll('.work-list li').length || 0,
    papersBtn: Boolean(modal?.querySelector('[data-action="advisor-papers"]')),
    ror: links.some((h) => h.includes('ror.org')),
    orcid: links.some((h) => h === 'https://orcid.org/0000-0002-8945-8573'),
    shanghai: /上海交通大学/.test(modal?.textContent || '')
  };
})()`);
check(zState.title.includes("Zisserman") && /Oxford/.test(zState.inst) && !zState.shanghai, `ORCID 修正学者机构 (${zState.inst})`);
check(zState.orcid && zState.ror, `导师详情给出 ORCID 与 ROR 机构链接 (${zState.links.length} 个入口)`);
check(zState.verified && zState.bars === 6, `导师详情展示 2021–2026 发表活跃度 (${zState.bars} 根柱)`);
check(zState.works >= 1 && zState.papersBtn, `导师详情展示 ORCID 近期论文并可进入论文库 (${zState.works} 篇)`);

await evaluate(`document.querySelector('[data-action="advisor-papers"]')?.click()`);
await waitFor(() => location.hash.includes("papers") && document.querySelectorAll(".paper-row").length > 0, 9000);
const fromAdvisor = await evaluate(`({
  hash: location.hash,
  filter: document.querySelector('.active-filter b')?.textContent?.trim() || '',
  rows: document.querySelectorAll('.paper-row').length,
  scholars: Array.from(document.querySelectorAll('.paper-scholar')).map((b) => b.textContent.trim()),
  meta: document.querySelector('#paperMeta')?.textContent?.trim() || ''
})`);
check(fromAdvisor.hash.includes("papers") && /Zisserman/.test(fromAdvisor.filter) && fromAdvisor.rows > 0 && fromAdvisor.scholars.every((s) => /Zisserman/.test(s)), `从导师详情进入论文库并按学者筛选 (${fromAdvisor.meta})`);

const allPapers = await evaluate(`(() => {
  document.querySelector('[data-action="paper-clear-scholar"]')?.click();
  return true;
})()`);
await waitFor(() => document.querySelectorAll(".paper-row").length >= 40, 5000);
const paperBase = await evaluate(`({
  rows: document.querySelectorAll('.paper-row').length,
  meta: document.querySelector('#paperMeta')?.textContent?.trim() || '',
  more: Boolean(document.querySelector('[data-action="paper-more"]')),
  totalText: document.querySelector('.paper-stats')?.textContent?.replace(/\\s+/g, ' ').trim() || ''
})`);
check(paperBase.rows === 40 && paperBase.more && /匹配/.test(paperBase.meta), `论文库展示分页列表 (${paperBase.meta})`);
check(/篇论文/.test(paperBase.totalText) && /位学者/.test(paperBase.totalText), `论文库给出总量与学者覆盖 (${paperBase.totalText.slice(0, 80)})`);

await evaluate(`(() => {
  const input = document.querySelector('#paperQuery');
  input.value = 'Zisserman';
  input.dispatchEvent(new Event('input', { bubbles: true }));
})()`);
await sleep(350);
const paperSearch = await evaluate(`({
  rows: document.querySelectorAll('.paper-row').length,
  meta: document.querySelector('#paperMeta')?.textContent?.trim() || '',
  scholars: Array.from(document.querySelectorAll('.paper-scholar')).map((b) => b.textContent.trim())
})`);
check(paperSearch.rows > 0 && paperSearch.rows < 40 && paperSearch.scholars.every((s) => /Zisserman/.test(s)), `论文库关键词检索命中学者论文 (${paperSearch.meta})`);

await evaluate(`(() => {
  const input = document.querySelector('#paperQuery');
  input.value = '';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  const cat = document.querySelector('#paperCategory');
  const opt = Array.from(cat.options).find((o) => o.value === '计算机视觉');
  if (opt) { cat.value = '计算机视觉'; cat.dispatchEvent(new Event('change', { bubbles: true })); }
})()`);
await sleep(350);
const paperCat = await evaluate(`({
  rows: document.querySelectorAll('.paper-row').length,
  meta: document.querySelector('#paperMeta')?.textContent?.trim() || '',
  selected: document.querySelector('#paperCategory')?.value || ''
})`);
check(paperCat.selected === "计算机视觉" && paperCat.rows > 0, `论文库按领域筛选生效 (${paperCat.meta})`);

const beforeMore = await evaluate(`document.querySelectorAll('.paper-row').length`);
await evaluate(`document.querySelector('[data-action="paper-more"]')?.click()`);
await sleep(300);
const afterMore = await evaluate(`document.querySelectorAll('.paper-row').length`);
check(afterMore > beforeMore, `论文库可继续加载更多 (${beforeMore} → ${afterMore} 篇)`);

const paperOverflow = await evaluate(`document.documentElement.scrollWidth - window.innerWidth`);
check(paperOverflow <= 1, `论文库无横向溢出 (${paperOverflow}px)`);

// ---- 期刊页：方向内推荐搜索与平铺/列表 ----
await evaluate(`location.hash = '#/venues'`);
await sleep(500);
await evaluate(`document.querySelector('[data-action="venue-mode"][data-mode="rec"]')?.click()`);
await waitFor(() => document.querySelector("#venueDirectionInput"), 5000);
await evaluate(`(() => {
  const input = document.querySelector('#venueDirectionInput');
  input.value = '红外小目标检测';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('[data-action="venue-search-direction"]')?.click();
})()`);
await waitFor(() => {
  const meta = document.querySelector('#venueRecMeta')?.textContent || '';
  return meta.includes("红外") && meta.includes("推荐") && document.querySelectorAll('.venue-card').length > 0;
}, 9000);
const venueRec = await evaluate(`({
  cards: document.querySelectorAll('.venue-card').length,
  meta: document.querySelector('#venueRecMeta')?.textContent?.trim() || '',
  value: document.querySelector('#venueDirectionInput')?.value || '',
  heading: document.querySelector('.tabs .tab.active')?.textContent?.trim() || ''
})`);
check(venueRec.heading.includes("按方向推荐") && venueRec.cards > 0 && venueRec.meta.includes("红外") && venueRec.value === "红外小目标检测", `期刊页可直接输入方向并推荐 venue (${venueRec.cards} 个 · ${venueRec.meta})`);
await evaluate(`document.querySelector('[data-action="venue-layout"][data-layout="list"]')?.click()`);
await waitFor(() => document.querySelector('#venueRecList')?.classList.contains('is-list'), 3000);
const venueRecList = await evaluate(`({
  isList: document.querySelector('#venueRecList')?.classList.contains('is-list') || false,
  cards: document.querySelectorAll('.venue-card').length,
  value: document.querySelector('#venueDirectionInput')?.value || '',
  active: document.querySelector('[data-action="venue-layout"][data-layout="list"]')?.classList.contains('active') || false
})`);
check(venueRecList.isList && venueRecList.active && venueRecList.cards === venueRec.cards && venueRecList.value === "红外小目标检测", `期刊方向推荐支持平铺/列表切换并保留输入 (${venueRecList.cards} 个)`);
await evaluate(`document.querySelector('[data-action="venue-mode"][data-mode="all"]')?.click()`);
await waitFor(() => document.querySelectorAll('.venue-card').length >= 701, 9000);
const venueAllLayout = await evaluate(`({
  isList: document.querySelector('#venueList')?.classList.contains('is-list') || false,
  cards: document.querySelectorAll('.venue-card').length,
  active: document.querySelector('[data-action="venue-layout"][data-layout="list"]')?.classList.contains('active') || false
})`);
check(venueAllLayout.isList && venueAllLayout.active && venueAllLayout.cards === 701, `期刊全部目录沿用列表视图 (${venueAllLayout.cards} 个)`);
await evaluate(`document.querySelector('[data-action="venue-layout"][data-layout="grid"]')?.click()`);
await sleep(250);
const venueBackGrid = await evaluate(`({
  isGrid: !document.querySelector('#venueList')?.classList.contains('is-list'),
  cards: document.querySelectorAll('.venue-card').length
})`);
check(venueBackGrid.isGrid && venueBackGrid.cards === 701, `期刊目录可切回平铺 (${venueBackGrid.cards} 个)`);

console.log(consoleErrors.length ? `CONSOLE_ERRORS:\n${consoleErrors.join("\n")}` : "NO_CONSOLE_ERRORS");
if (consoleErrors.length) failures.push("console errors");
console.log(failures.length ? `FAILURES ${failures.length}` : "ALL_CHECKS_PASSED");

ws.close();
chrome.kill();
await sleep(400);
try { rmSync(profile, { recursive: true, force: true }); } catch { /* noop */ }
process.exitCode = failures.length ? 1 : 0;
