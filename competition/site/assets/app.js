import {
  loadIndex, loadDirectionData, loadAdvisors, loadVenues,
  loadApplications, loadBenchmarks, loadRegions, loadMaterials,
  loadOrcid, loadPapers,
  matchDirection, suggestDirections, confidenceLabel, buildCandidates,
  scaffoldDescription, SAMPLE_DESCRIPTION, diagnose,
  loadIdeas, saveIdeas, rememberDirection, lastDirection,
  escapeHtml, fmtInt, fmtDate, todayISO, addDaysISO, daysLeft,
  cleanText, copyText, isMeaningfulDirectionQuery,
  detectApplications, appsByIds, appsForDirection, TAG_TASKS,
  recommendDirections, taskLabel,
} from "./core.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const view = $("#view");
const toastEl = $("#toast");
const sidebar = $("#sidebar");
const scrim = $("#scrim");

const ROUTES = {
  intro: { title: "开场", crumb: "塞莎特——题谱 / 开场" },
  workshop: { title: "选题工坊", crumb: "塞莎特——题谱 / 选题工坊" },
  materials: { title: "素材库", crumb: "塞莎特——题谱 / 素材库" },
  advisors: { title: "导师与院校", crumb: "塞莎特——题谱 / 导师与院校" },
  papers: { title: "论文库", crumb: "塞莎特——题谱 / 论文库" },
  venues: { title: "期刊会议", crumb: "塞莎特——题谱 / 期刊会议" },
  methods: { title: "科研方法论", crumb: "塞莎特——题谱 / 科研方法论" },
  plan: { title: "研究计划", crumb: "塞莎特——题谱 / 研究计划" },
  about: { title: "关于与数据范围", crumb: "塞莎特——题谱 / 关于与数据范围" },
};

const ROUTE_META = {
  intro: { index: "00", section: "开场" },
  workshop: { index: "01", section: "选题与研究" },
  materials: { index: "02", section: "选题与研究" },
  advisors: { index: "03", section: "选题与研究" },
  papers: { index: "04", section: "选题与研究" },
  venues: { index: "05", section: "选题与研究" },
  methods: { index: "06", section: "方法与落地" },
  plan: { index: "07", section: "方法与落地" },
  about: { index: "08", section: "数据与边界" },
};

const DIAG_ORDER = ["problem", "mechanism", "baseline", "data", "metric", "ablation", "budget", "stop", "scope"];
const DIAG_LABEL = {
  problem: "问题具体", mechanism: "机制可检验", baseline: "baseline 点名",
  data: "数据与划分", metric: "指标定义", ablation: "消融设计",
  budget: "资源估算", stop: "止损条件", scope: "范围收敛",
};
const PLAN_STAGES = ["问题收敛", "最小实验", "完整实验", "写作与核查"];
const METHOD_STAGES = [
  ["topic", "选题定位", "把兴趣收敛成 2–4 个可检验的候选问题"],
  ["lit", "文献调研", "建立检索式、纳入排除与技术分叉表"],
  ["design", "方案设计", "写清 baseline、机制、消融与指标"],
  ["run", "实验实施", "先跑最小实验，记录失败与异常"],
  ["write", "写作投稿", "按结构写正文，并核对引用与图表"],
];
const METHOD_DEGREES = ["本科毕业设计", "硕士", "博士", "博士后 / 青年教师"];
const METHOD_PAPERS = ["期刊论文", "会议论文", "学位论文 / 开题", "综述", "项目申请书"];
const METHOD_PREP = [
  ["scope", "已把方向缩到一个具体场景"],
  ["lit", "已读 10 篇以上核心文献并做过对比"],
  ["data", "已找到可获取的数据与划分方式"],
  ["baseline", "已确认可复现的 baseline 与指标"],
  ["compute", "算力、周期与人力预算已明确"],
  ["advisor", "导师或团队方向与选题一致"],
  ["ethics", "数据合规、伦理与保密限制已确认"],
  ["result", "已有初步结果或 pilot 实验"],
];
const METHOD_STAGE_TASKS = {
  topic: [
    "给出 3–5 个候选问题，每个写成「场景 + 失效点 + 可量化差距 + 可证伪假设」。",
    "用 7 个维度做对比：新颖性、可行性、数据可得性、算力需求、周期、失败风险、写作空间。",
    "给出排序与取舍理由，明确指出哪些候选只是换术语、没有真正差异。",
    "为每个候选列出 2–3 篇最近邻工作（题名 / 作者 / 年份，标注待核验），并写出差异句。",
  ],
  lit: [
    "给出中英文检索式，分别适配 Google Scholar、Web of Science、Scopus 与 arXiv 的语法。",
    "写清纳入 / 排除标准与时间窗，并说明为什么这样切。",
    "识别 2–3 条技术分叉，说明各分叉解决了什么、遗留了什么。",
    "输出代表工作表：问题、方法、数据、指标、结论、局限；没有原文依据的字段留空并标注。",
  ],
  design: [
    "画出「研究问题 → 机制假设 → 模块 → 对照实验 → 指标」的对应表。",
    "指定至少 2 个 baseline、1 个主指标与 2 个辅助指标，写清计算方式与数据划分。",
    "设计消融与泄漏检查，说明每个消融想排除哪种解释。",
    "估算算力、标注与调试时间，并写出失败判据与止损点。",
    "给出 1 周内可完成的最小实验，以及它能回答/不能回答的问题。",
  ],
  run: [
    "把实验拆成有顺序的清单：假设、变量、对照、记录字段、完成标准。",
    "给出结果表与失败记录模板，要求保留异常、随机种子与版本信息。",
    "列出 3 个最常见的实现错误与自检方法。",
    "规定何时停止、何时转向：用数据而不是情绪做判断。",
  ],
  write: [
    "给出论文骨架：摘要、引言、相关工作、方法、实验、讨论、局限、结论。",
    "提炼 3 条贡献，每条都要能被实验或分析支撑，避免「首次」「显著提升」这类空话。",
    "列出图表清单，说明每张图要证明什么。",
    "做一次审稿人预演：3 个最可能的拒稿理由与对应补强。",
    "给出引用核验清单与目标 venue 的匹配理由（不臆测影响因子或接收率）。",
  ],
};
const METHOD_READINESS_HINT = {
  scope: "先把方向缩到一个具体场景，否则候选会漂移。",
  lit: "先补 10 篇核心文献的对比表，确认不是重复工作。",
  data: "先确认数据可得性与划分方式，避免实验做到一半才发现拿不到数据。",
  baseline: "先锁定可复现的 baseline 与指标，否则结果无法比较。",
  compute: "先估算算力与周期，砍掉跑不完的实验。",
  advisor: "先和导师确认方向与资源，避免选题与团队脱节。",
  ethics: "先确认数据合规、伦理与保密限制，再开始收集数据。",
  result: "没有 pilot 结果也可以开始，但要把第一阶段定位为可行性验证。",
};
const PAPER_TYPE_LABEL = {
  "journal-article": "期刊论文",
  "conference-paper": "会议论文",
  "book-chapter": "书章",
  "preprint": "预印本",
  "working-paper": "工作论文",
  "book": "专著",
  review: "综述",
};

const state = {
  index: null,
  appsData: null,
  benchmarks: null,
  regions: null,
  route: "workshop",
  phase: "intake",
  intakeMode: "search",
  pending: null,
  pendingLaunch: "",
  query: "",
  inputValue: "",
  direction: null,
  matched: false,
  confidence: "none",
  directionData: null,
  candidates: [],
  selectedApps: [],
  tagTask: "",
  activeApps: [],
  browseCat: "",
  browseQuery: "",
  advisorDetail: null,
  selected: null,
  filter: "all",
  detailTab: "card",
  desc: "",
  drafts: new Map(),
  diagnosis: null,
  diagnosisStale: false,
  saved: [],
  activeIdeaId: null,
  advisorMode: "direction",
  advisorProvince: "",
  advisorInstitution: "",
  institutionQuery: "",
  institutionLimit: 80,
  advisorLayout: "grid",
  advisorLimit: 60,
  scholarQuery: "",
  scholars: null,
  scholarsLoading: false,
  scholarsError: "",
  orcid: null,
  orcidLoading: false,
  orcidError: "",
  papers: null,
  papersLoading: false,
  papersError: "",
  paperQuery: "",
  paperYear: "",
  paperType: "",
  paperCategory: "",
  paperScholar: "",
  paperLimit: 40,
  materials: null,
  materialsLoading: false,
  materialsError: "",
  materialsQuery: "",
  materialsCat: "",
  materialsApp: "",
  materialsSelected: "",
  materialsLimit: 36,
  venues: null,
  venuesLoading: false,
  venuesError: "",
  venueDetail: null,
  venueMode: "rec",
  venueCcf: "",
  venueType: "",
  venueField: "",
  venueQuery: "",
  venueLayout: "grid",
  openSkill: null,
  method: null,
};

let toastTimer = 0;

function icon(name) {
  return `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

function toast(message) {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toastEl.classList.remove("show"), 2400);
}

function safeUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
  } catch { return ""; }
}

function currentRoute() {
  const raw = location.hash.replace(/^#\/?/, "").split("?")[0];
  if (!raw || raw === "intro") return "intro";
  return ROUTES[raw] ? raw : "workshop";
}

function navigate(route) {
  if (state.route === route && location.hash === `#/${route}`) {
    render();
    return;
  }
  location.hash = `#/${route}`;
}

// ---------- 开场页 ----------
let introEntering = false;

function enterSystem() {
  if (introEntering) return;
  introEntering = true;
  const screen = $("#introScreen");
  screen?.classList.add("is-leaving");
  window.setTimeout(() => { location.hash = "#/workshop"; }, 430);
  window.setTimeout(() => { introEntering = false; }, 900);
}

function startIntro({ restart = false } = {}) {
  document.documentElement.dataset.intro = "1";
  const screen = $("#introScreen");
  if (!screen) return;
  screen.classList.remove("is-leaving");
  if (restart) { screen.classList.remove("is-active"); void screen.offsetWidth; }
  screen.classList.add("is-active");
  document.title = "塞莎特——题谱 · 从研究方向到可核查选题";
  hydrateIntroStats();
}

function stopIntro() {
  document.documentElement.dataset.intro = "0";
  const screen = $("#introScreen");
  screen?.classList.remove("is-active", "is-leaving");
}

function hydrateIntroStats() {
  const stats = state.index?.stats;
  if (!stats) return;
  const map = {
    directions: stats.directions,
    datasets: stats.datasets || stats.curatedDatasets,
    scholars: stats.scholars_exported || stats.scholars_indexed,
    venues: stats.venues,
  };
  $$("[data-intro-stat]").forEach((el) => {
    const value = map[el.dataset.introStat];
    if (value) el.textContent = fmtInt(value);
  });
  const indexNote = $("[data-intro-index]");
  if (indexNote && stats.orcid_papers && stats.schools_exported) {
    indexNote.textContent = `ORCID ${fmtInt(stats.orcid_papers)} 篇 · 院校 ${fmtInt(stats.schools_exported)} 所`;
  }
}

function bindIntro() {
  $("#introEnter")?.addEventListener("click", (event) => {
    if (currentRoute() !== "intro") return;
    event.preventDefault();
    enterSystem();
  });
  $("#introScreen")?.addEventListener("click", (event) => {
    if (currentRoute() !== "intro") return;
    if (!window.matchMedia("(max-width: 620px)").matches) return;
    if (event.target.closest("a, button")) return;
    enterSystem();
  });
  document.addEventListener("keydown", (event) => {
    if (currentRoute() !== "intro" || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === "Enter") {
      event.preventDefault();
      enterSystem();
    }
  });
}

function openSidebar() {
  sidebar?.classList.add("open");
  if (scrim) scrim.hidden = false;
}

function closeSidebar() {
  sidebar?.classList.remove("open");
  if (scrim) scrim.hidden = true;
}

function updateNav(route) {
  $$(".nav-item, .mobile-nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
}

function updateSavedCount() {
  const badge = $("#savedCount");
  if (!badge) return;
  badge.textContent = String(state.saved.length);
  badge.hidden = state.saved.length === 0;
}

function directionLabel() {
  if (!state.direction) return state.query || "未命名方向";
  if (state.direction.aliasOf) return `${state.query}（映射：${state.direction.aliasOf}）`;
  return state.query || state.direction.name || "未命名方向";
}

function ideaId(candidate) {
  return `${state.query || state.direction?.name || "未命名"}::${candidate?.title || "未命名"}`;
}

function activeIdea() {
  return state.saved.find((x) => x.id === state.activeIdeaId) || state.saved[0] || null;
}

function stageToPlan(diag) {
  if (!diag) return PLAN_STAGES[0];
  return [PLAN_STAGES[0], PLAN_STAGES[0], PLAN_STAGES[1], PLAN_STAGES[2], PLAN_STAGES[3]][diag.stageNum] || PLAN_STAGES[0];
}

// ---------- 启动 ----------
async function boot() {
  bindShell();
  try {
    const [index, appsData, benchmarks, regions] = await Promise.all([
      loadIndex(), loadApplications(), loadBenchmarks(), loadRegions(),
    ]);
    state.index = index;
    state.appsData = appsData;
    state.benchmarks = benchmarks;
    state.regions = regions;
    state.saved = loadIdeas();
    updateSavedCount();
    hydrateStats();
    await restoreLast();
    applyRouteDefaults();
    render({ animate: true });
  } catch (err) {
    renderError(err);
  }
}

function hydrateStats() {
  const stats = state.index?.stats;
  if (!stats) return;
  const set = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = fmtInt(value); };
  set("footDirections", stats.directions);
  set("footPapers", stats.papers);
  hydrateIntroStats();
}

async function applyRouteDefaults() {
  const route = currentRoute();
  if (route === "advisors" && !state.directionData && state.advisorMode === "direction") state.advisorMode = "search";
  if (route === "methods" && !state.openSkill) state.openSkill = state.index?.skills?.[0]?.id || null;
  if (route === "plan" && !state.activeIdeaId && state.saved[0]) state.activeIdeaId = state.saved[0].id;
}

async function restoreLast() {
  const last = lastDirection();
  if (!last?.id) return;
  const entry = state.index.directions.find((d) => d.id === last.id);
  if (!entry) return;
  state.direction = entry;
  state.matched = true;
  state.confidence = "exact";
  state.query = last.name || entry.name;
  state.inputValue = state.query;
  state.directionData = await loadDirectionData(entry);
  state.activeApps = appsForDirection(state.appsData, entry.aliasOf || entry.name);
  state.candidates = buildCandidates(state.index, state.query, {
    data: state.directionData, benchmarks: state.benchmarks, apps: state.activeApps, entry,
  });
  state.selected = state.candidates[0] || null;
  state.desc = state.selected ? scaffoldDescription(state.selected, state.query, state.directionData?.benchmark) : "";
  if (state.selected) state.drafts.set(state.selected.title, state.desc);
}

function currentTheme() {
  const explicit = document.documentElement.dataset.theme;
  if (explicit === "light" || explicit === "dark") return explicit;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function bindTheme() {
  const button = $("#themeToggle");
  if (!button) return;
  button.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("xtzk.v1.theme", next); } catch {}
    button.setAttribute("aria-label", next === "dark" ? "切换到浅色主题" : "切换到深色主题");
  });
  button.setAttribute("aria-label", currentTheme() === "dark" ? "切换到浅色主题" : "切换到深色主题");
}

function bindClock() {
  const clock = $("#topClock");
  const timeEl = $("#clockTime");
  const dateEl = $("#clockDate");
  if (!clock || !timeEl || !dateEl) return;
  const pad = (n) => String(n).padStart(2, "0");
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const tick = () => {
    const now = new Date();
    timeEl.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    dateEl.textContent = `${now.getFullYear()}.${pad(now.getMonth() + 1)}.${pad(now.getDate())} ${weekdays[now.getDay()]}`;
    clock.dateTime = now.toISOString();
  };
  tick();
  window.setInterval(tick, 1000);
}

function bindShell() {
  bindClock();
  $("#menuBtn")?.addEventListener("click", openSidebar);
  $("#sidebarClose")?.addEventListener("click", closeSidebar);
  scrim?.addEventListener("click", closeSidebar);
  $$("#sidebar a[href^='#/']").forEach((a) => a.addEventListener("click", closeSidebar));
  bindTheme();
  bindIntro();

  window.addEventListener("hashchange", () => {
    closeSidebar();
    applyRouteDefaults();
    render({ animate: true });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeSidebar();
      hideSuggestions();
      if (state.advisorDetail || state.venueDetail) {
        state.advisorDetail = null;
        state.venueDetail = null;
        render();
      }
    }
    if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "")) {
      e.preventDefault();
      if (state.route !== "workshop") navigate("workshop");
      window.setTimeout(() => $("#directionInput")?.focus(), 60);
    }
  });

  view.addEventListener("click", onViewClick);
  view.addEventListener("input", onViewInput);
  view.addEventListener("change", onViewChange);
  view.addEventListener("keydown", onViewKeydown);
  const suggestTargets = {
    directionInput: ["suggestBox", "suggest"],
    advisorDirectionInput: ["advisorSuggestBox", "advisor-suggest"],
    venueDirectionInput: ["venueSuggestBox", "venue-suggest"],
  };
  view.addEventListener("focusin", (event) => {
    const config = suggestTargets[event.target.id];
    if (config) updateInputSuggestions(event.target, config[0], config[1]);
  });
  view.addEventListener("click", (event) => {
    const input = event.target.closest(Object.keys(suggestTargets).map((id) => `#${id}`).join(","));
    if (!input) return;
    const config = suggestTargets[input.id];
    if (config) updateInputSuggestions(input, config[0], config[1]);
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".suggest-wrap")) hideSuggestions();
  });
}

function render(opts = {}) {
  state.route = currentRoute();
  if (state.route === "intro") {
    const screen = $("#introScreen");
    if (!screen?.classList.contains("is-active")) startIntro({ restart: true });
    return;
  }
  stopIntro();
  const meta = ROUTES[state.route];
  document.title = `${meta.title} · 塞莎特——题谱`;
  $("#crumb").textContent = meta.crumb;
  updateNav(state.route);
  updateSavedCount();

  let body = "";
  switch (state.route) {
    case "materials": body = materialsView(); break;
    case "advisors": body = advisorsView(); break;
    case "papers": body = papersView(); break;
    case "venues": body = venuesView(); break;
    case "methods": body = methodsView(); break;
    case "plan": body = planView(); break;
    case "about": body = aboutView(); break;
    default: body = workshopView();
  }
  view.innerHTML = `<div class="${opts.animate ? "view-enter" : ""}">${body}</div>${advisorModalHtml()}${venueModalHtml()}`;
  if (state.route === "methods") updateStudioPreview();
  if (opts.animate) {
    requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0, behavior: "instant" }));
  }
  if (state.route === "workshop" && state.pendingLaunch) {
    const launch = state.pendingLaunch;
    state.pendingLaunch = "";
    setTimeout(() => generateDirection(launch), 0);
  }
}

function renderError(err) {
  view.innerHTML = `
    <div class="view-enter">
      <div class="page-head"><div><div class="eyebrow">${icon("alert")} 读取失败</div><h1>数据没有加载成功</h1></div></div>
      <div class="card">
        <div class="empty">
          <div class="empty-icon">${icon("alert")}</div>
          <strong>无法读取本地索引</strong>
          <p>${escapeHtml(err?.message || err)}。请确认通过 HTTP 打开本站，而不是直接双击 index.html；静态资源需要由服务器提供。</p>
          <button class="btn btn-primary" data-action="reload">重新加载</button>
        </div>
      </div>
    </div>`;
}

// ---------- 通用片段 ----------
function pageHead(title) {
  return `<h1 class="sr-only">${title}</h1>`;
}

function emptyBlock(iconName, title, desc, actions = "") {
  return `
    <div class="empty">
      <div class="empty-icon">${icon(iconName)}</div>
      <strong>${title}</strong>
      <p>${desc}</p>
      ${actions}
    </div>`;
}

function chips(names, action = "example", extra = "") {
  return `<div class="chip-row">${names.map((name) => `<button type="button" class="chip" data-action="${action}" data-name="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("")}${extra}</div>`;
}

function barList(rows, emptyText = "暂无匹配数据") {
  if (!rows?.length) return `<p class="small muted">${emptyText}</p>`;
  const max = Math.max(...rows.map(([, n]) => Number(n) || 0), 1);
  return `<div class="bar-list">${rows.slice(0, 8).map(([name, n]) => `
    <div class="bar-row">
      <span class="bl-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
      <span class="bl-track"><span class="bl-fill" style="width:${Math.max(3, (Number(n) / max) * 100)}%"></span></span>
      <span class="bl-num">${fmtInt(n)}</span>
    </div>`).join("")}</div>`;
}

function ccfBadge(rank) {
  const r = String(rank || "").trim();
  if (["A", "B", "C"].includes(r)) return `<span class="ccf ccf-${r}">${r}</span>`;
  return `<span class="ccf ccf-none">—</span>`;
}

function safeExternal(url, label, cls = "link-quiet") {
  const href = safeUrl(url);
  if (!href) return "";
  return `<a class="${cls}" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)} ${icon("external")}</a>`;
}

// ---------- 选题工坊 ----------
function workshopView() {
  const body = state.phase === "review" && state.pending
    ? reviewHtml()
    : state.direction ? workshopResultsHtml() : workshopIntroHtml();
  return `
    ${pageHead(
      "选题工坊",
      "输入研究方向，确认识别结果后生成可核查的候选；候选数量随方向关键词的关联强度变化。",
      `<a class="btn" href="#/methods">${icon("route")} 方法论帮助</a>`
    )}
    ${heroHtml()}
    ${body}
  `;
}

function heroHtml() {
  const stats = state.index?.stats || {};
  const intake = state.phase === "intake";
  const mode = state.intakeMode || "search";
  return `
    <section class="query-panel ${state.phase === "review" || state.direction ? "is-compact" : ""}">
      <div class="query-brief">
        <div class="query-kicker"><span>DIRECTION INTAKE</span><b>01</b></div>
        <h2>从一个研究方向，<br><em>走到可核查的问题。</em></h2>
        <p>输入方向，或按应用场景与任务标签组合。确认方向后生成候选，并附上可核查的数据集、指标与基线。</p>
        <figure class="atlas-map" aria-hidden="true">
          <svg viewBox="0 0 420 154" role="presentation">
            <path class="atlas-arc arc-a" d="M34 98C104 34 176 128 238 78S342 20 392 64"/>
            <path class="atlas-arc arc-b" d="M48 52C126 118 232 30 298 100S370 122 398 92"/>
            <g class="atlas-edge">
              <path d="M74 96 150 62 232 84 310 54 352 94"/>
              <path d="M150 62 196 112 310 54"/>
            </g>
            <g class="atlas-node">
              <circle cx="74" cy="96" r="5.5"/>
              <circle cx="150" cy="62" r="4.5"/>
              <circle cx="196" cy="112" r="4.5"/>
              <circle cx="310" cy="54" r="4.5"/>
              <circle cx="352" cy="94" r="5"/>
            </g>
            <g class="atlas-core">
              <circle cx="232" cy="84" r="16"/>
              <text x="232" y="89" text-anchor="middle">题</text>
            </g>
          </svg>
          <span class="map-chip chip-a">应用场景</span>
          <span class="map-chip chip-b">公开基准</span>
        </figure>
        <div class="query-stats">
          <div><b>${fmtInt(stats.directions || 501)}</b><span>研究方向</span></div>
          <div><b>${fmtInt(stats.applicationTags || 37)}</b><span>应用标签</span></div>
          <div><b>${fmtInt(stats.curatedDatasets || 502)}</b><span>公开基准</span></div>
          <div><b>${fmtInt(stats.papers || 345)}</b><span>本地文献</span></div>
          <div><b>${fmtInt(stats.scholars_exported || stats.scholars_indexed)}</b><span>可浏览学者</span></div>
        </div>
      </div>
      <div class="query-form">
        ${intake ? intakeTabsHtml() : ""}
        ${intake && mode === "tags" ? tagsPanelHtml()
          : intake && mode === "browse" ? browsePanelHtml()
          : searchFormHtml()}
        <div class="flow">
          <span class="flow-step on"><b>1</b>${intake && mode === "tags" ? "组合标签" : intake && mode === "browse" ? "选择方向" : "输入方向"}</span><span class="sep">→</span>
          <span class="flow-step ${state.phase === "review" || state.direction ? "on" : ""}"><b>2</b>确认方向</span><span class="sep">→</span>
          <span class="flow-step ${state.candidates.length ? "on" : ""}"><b>3</b>挑候选</span><span class="sep">→</span>
          <span class="flow-step ${state.diagnosis ? "on" : ""}"><b>4</b>结构体检</span>
        </div>
      </div>
    </section>`;
}

function intakeTabsHtml() {
  const tabs = [
    ["search", "搜索方向", "输入名称或术语"],
    ["tags", "标签组合", "应用场景 × 任务"],
    ["browse", "全部方向", `${fmtInt(state.index?.stats?.directions || 501)} 个`],
  ];
  return `
    <div class="intake-tabs" role="tablist" aria-label="选择研究方向的方式">
      ${tabs.map(([key, label, hint]) => `
        <button type="button" class="intake-tab ${state.intakeMode === key ? "active" : ""}" data-action="intake-mode" data-mode="${key}" role="tab" aria-selected="${state.intakeMode === key}">
          <b>${label}</b><small>${hint}</small>
        </button>`).join("")}
    </div>`;
}

function searchFormHtml() {
  return `
    <label class="query-label" for="directionInput">研究方向 <span>RESEARCH DIRECTION</span></label>
    <div class="suggest-wrap">
      <div class="input-row">
        <input id="directionInput" class="input input-lg" type="text" maxlength="80"
          placeholder="输入研究方向，例如：红外小目标检测" autocomplete="off"
          value="${escapeHtml(state.inputValue || state.query)}" aria-label="研究方向">
        <button type="button" class="btn btn-primary" data-action="generate" id="generateBtn">识别方向 ${icon("search")}</button>
      </div>
      <div class="suggest" id="suggestBox" hidden></div>
    </div>
    <p class="query-hint" id="queryHint" role="status" hidden></p>
    <div class="query-examples">
      <span class="query-examples-label">示例</span>
      ${chips(state.index.examples || [], "example")}
    </div>
    <div class="quick-cats">
      <span class="query-examples-label">不确定方向</span>
      ${(state.index.categories || []).slice(0, 8).map((cat) => `<button type="button" class="chip" data-action="discover-cat" data-cat="${escapeHtml(cat.name)}" title="写入「${escapeHtml(cat.name)}」并展开该大类方向">${escapeHtml(cat.name)} <em>${cat.count} 个方向</em></button>`).join("")}
      <button type="button" class="chip chip-more" data-action="intake-mode" data-mode="browse">浏览全部大类 ${icon("arrow")}</button>
    </div>`;
}

function tagsPanelHtml() {
  const groups = state.appsData?.groups || [];
  const selected = appsByIds(state.appsData, state.selectedApps);
  const recs = recommendDirections(state.index, state.appsData, state.selectedApps, state.tagTask, 10);
  const taskChips = TAG_TASKS.map((task) => `
    <button type="button" class="tag-chip ${state.tagTask === task.key ? "active" : ""}" data-action="tag-task" data-task="${task.key}">${task.label}</button>`).join("");
  return `
    <div class="tags-panel">
      <div class="tags-head">
        <div>
          <div class="query-label">应用场景 <span>APPLICATION DOMAIN</span></div>
          <p class="tags-hint">先选场景，再选任务偏好。系统只在方向库与人工整理的应用映射里组合，不做语义检索。</p>
        </div>
        <span class="badge">${selected.length ? `已选 ${selected.length} 个` : "可多选"}</span>
      </div>
      <div class="tag-groups">
        ${groups.map((group) => `
          <div class="tag-group">
            <span class="tag-group-label">${escapeHtml(group.name)}</span>
            <div class="tag-row">
              ${(group.apps || []).map((app) => `
                <button type="button" class="tag-chip ${state.selectedApps.includes(app.id) ? "active" : ""}" data-action="toggle-app" data-id="${escapeHtml(app.id)}" title="${escapeHtml(app.note || "")}">
                  ${escapeHtml(app.name)}
                </button>`).join("")}
            </div>
          </div>`).join("")}
      </div>
      <div class="tag-task">
        <span class="tag-group-label">任务偏好</span>
        <div class="tag-row">${taskChips}</div>
      </div>
      <div class="tag-selected">
        <span>${selected.length ? selected.map((a) => escapeHtml(a.name)).join(" · ") : "尚未选择场景"}</span>
        ${selected.length || state.tagTask ? `<button type="button" class="rb-link" data-action="clear-tags">清空</button>` : ""}
      </div>
      <div class="tag-results">
        <div class="tag-results-head"><b>推荐方向</b><span>${recs.length ? `${recs.length} 个组合结果` : "选择场景后出现"}</span></div>
        ${recs.length ? `<div class="tag-result-list">
          ${recs.map(({ entry, score, reasons }) => `
            <button type="button" class="tag-result" data-action="tag-direction" data-name="${escapeHtml(entry.name)}">
              <span class="tag-result-main"><b>${escapeHtml(entry.name)}</b><small>${escapeHtml(entry.category)}</small></span>
              <span class="tag-result-reasons">${reasons.slice(0, 3).map((r) => `<em>${escapeHtml(r)}</em>`).join("")}</span>
              <span class="tag-result-score">${score}</span>
            </button>`).join("")}
        </div>` : `<p class="tags-empty">选 1 个以上应用场景，或点一个任务偏好。</p>`}
      </div>
    </div>`;
}

let TERM_COUNTS = null;
let MAX_ASSOCIATION = 1;

function buildTermCounts() {
  TERM_COUNTS = new Map();
  for (const entry of state.index?.directions || []) {
    const terms = new Set([...(entry.keywords || []), ...(entry.terms || [])].map((t) => String(t).toLowerCase()).filter(Boolean));
    for (const term of terms) TERM_COUNTS.set(term, (TERM_COUNTS.get(term) || 0) + 1);
  }
  MAX_ASSOCIATION = 1;
  for (const entry of state.index?.directions || []) {
    const score = associationOf(entry, false);
    if (score > MAX_ASSOCIATION) MAX_ASSOCIATION = score;
  }
}

function associationOf(entry) {
  if (!TERM_COUNTS) buildTermCounts();
  const terms = new Set([...(entry.keywords || []), ...(entry.terms || [])].map((t) => String(t).toLowerCase()).filter(Boolean));
  let score = 0;
  for (const term of terms) score += Math.max(0, (TERM_COUNTS.get(term) || 1) - 1);
  return score;
}

function associationLabel(score) {
  const ratio = score / Math.max(1, MAX_ASSOCIATION);
  if (ratio >= 0.55) return { label: "强关联", cls: "strong" };
  if (ratio >= 0.22) return { label: "中关联", cls: "mid" };
  return { label: "弱关联", cls: "weak" };
}

function browsePanelHtml() {
  const categories = state.index?.categories || [];
  const q = state.browseQuery.trim().toLowerCase();
  const matches = (entry) => {
    if (q && !`${entry.name} ${entry.category} ${(entry.keywords || []).join(" ")} ${(entry.terms || []).join(" ")}`.toLowerCase().includes(q)) return false;
    return !entry.aliasOf;
  };
  const allRows = state.index.directions.filter(matches);
  const catCount = new Map();
  for (const entry of allRows) catCount.set(entry.category, (catCount.get(entry.category) || 0) + 1);
  const rows = state.browseCat ? allRows.filter((entry) => entry.category === state.browseCat) : [];
  rows.sort((a, b) => associationOf(b) - associationOf(a) || b.papers - a.papers || a.name.localeCompare(b.name));
  const activeCat = state.browseCat || "";
  return `
    <div class="browse-panel">
      <div class="browse-controls">
        <div class="suggest-wrap">
          <input id="browseQuery" class="input" type="text" value="${escapeHtml(state.browseQuery)}" placeholder="${activeCat ? `在「${escapeHtml(activeCat)}」内筛选关键词或术语` : "筛选方向、关键词或术语"}" autocomplete="off" aria-label="筛选方向">
        </div>
        ${activeCat ? `<span class="browse-active-cat" title="当前大类">${escapeHtml(activeCat)}</span>` : ""}
        <button type="button" class="btn" data-action="browse-clear">清空</button>
      </div>
      <div class="browse-layout">
        <div class="browse-cats-list" role="list" aria-label="研究方向大类">
          <button type="button" class="browse-cat ${!activeCat ? "active" : ""}" data-action="browse-cat" data-cat="">
            <span>全部大类</span><b>${fmtInt(allRows.length)}</b>
          </button>
          ${categories.map((cat) => {
            const count = catCount.get(cat.name) || 0;
            return `<button type="button" class="browse-cat ${activeCat === cat.name ? "active" : ""}" data-action="browse-cat" data-cat="${escapeHtml(cat.name)}" ${count ? "" : "disabled"}>
              <span>${escapeHtml(cat.name)}</span><b>${fmtInt(count)}</b>
            </button>`;
          }).join("")}
        </div>
        <div class="browse-sub">
          ${activeCat ? `
            <div class="browse-sub-head">
              <div><b>${escapeHtml(activeCat)}</b><small>${fmtInt(rows.length)} 个方向 · 按关键词关联强度排序</small></div>
              <span class="badge">大类 → 小类</span>
            </div>
            <div class="browse-items">
              ${rows.length ? rows.map((entry) => {
                const score = associationOf(entry);
                const level = associationLabel(score);
                return `<button type="button" class="browse-item browse-entry" data-action="browse-direction" data-name="${escapeHtml(entry.name)}">
                  <span class="browse-entry-main"><b>${escapeHtml(entry.name)}</b><small>${escapeHtml((entry.keywords || []).slice(0, 3).join(" · ") || "关键词待补充")}</small></span>
                  <span class="browse-assoc ${level.cls}"><i style="width:${Math.max(8, Math.round((score / Math.max(1, MAX_ASSOCIATION)) * 100))}%"></i><em>${level.label}</em></span>
                  <span class="browse-entry-arrow">${icon("arrow")}</span>
                </button>`;
              }).join("") : `<p class="tags-empty">该大类下没有匹配方向。</p>`}
            </div>` : `
            <div class="browse-empty">
              <div class="empty-icon">${icon("route")}</div>
              <b>先选择一个研究大类</b>
              <p>左侧列出 ${fmtInt((state.index.categories || []).length)} 个大类。点击后查看该大类下的小方向，并按知识库关键词的关联强度排序。</p>
              ${q ? `<div class="browse-items" style="margin-top:var(--sp-3)">${allRows.slice(0, 12).map((entry) => `<button type="button" class="browse-item" data-action="browse-direction" data-name="${escapeHtml(entry.name)}">${escapeHtml(entry.name)} <small>${escapeHtml(entry.category)}</small></button>`).join("")}</div>` : ""}
            </div>`}
        </div>
      </div>
    </div>`;
}

function workshopIntroHtml() {
  return `
    <div class="start-strip">
      <div><span>01</span><b>识别方向</b><small>方向名、术语或关键词</small></div>
      <div><span>02</span><b>确认场景</b><small>可叠加应用标签</small></div>
      <div><span>03</span><b>生成候选</b><small>数量随关联强度变化</small></div>
      <div><span>04</span><b>结构体检</b><small>9 项可核查条件</small></div>
    </div>`;
}

function scoreConfidence(score) {
  return score >= 120 ? "exact" : score >= 85 ? "strong" : "near";
}

function matchedTerms(entry, query) {
  const q = String(query || "").toLowerCase().replace(/\s+/g, "");
  if (!q) return [];
  const out = [];
  const push = (raw, kind) => {
    const label = String(raw || "").trim();
    const normalized = label.toLowerCase().replace(/\s+/g, "");
    if (normalized.length < 2) return;
    if (!q.includes(normalized) && !normalized.includes(q)) return;
    if (out.some((item) => item.label === label)) return;
    out.push({ label, kind });
  };
  push(entry?.name, "方向名");
  (entry?.terms || []).forEach((term) => push(term, "术语"));
  (entry?.keywords || []).forEach((term) => push(term, "关键词"));
  push(entry?.category, "大类");
  return out.slice(0, 6);
}

function reviewHtml() {
  const pending = state.pending;
  if (!pending) return "";
  const { query, entry, confidence, best = [] } = pending;
  const matched = Boolean(entry);
  const directionName = entry ? (entry.aliasOf || entry.name) : query;
  const category = entry?.category || "未归类";
  const terms = entry ? matchedTerms(entry, query) : [];
  const alternatives = best
    .filter((row) => row.entry && row.entry.name !== entry?.name)
    .slice(0, 4);
  const near = confidence === "near";
  const apps = pending.apps || [];
  const altHtml = alternatives.length
    ? `<div class="review-block">
        <span class="review-label">相邻方向</span>
        <div class="review-alts">
          ${alternatives.map((row) => `
            <button type="button" class="review-alt" data-action="choose-direction" data-name="${escapeHtml(row.entry.name)}">
              <span>${escapeHtml(row.entry.aliasOf || row.entry.name)}</span>
              <small>${escapeHtml(row.entry.category || "未归类")}</small>
            </button>`).join("")}
        </div>
      </div>`
    : "";

  return `
    <section class="review-panel" aria-live="polite">
      <div class="review-head">
        <div class="review-kicker"><span>DIRECTION REVIEW</span><b>02</b></div>
        <h2>${matched ? "确认方向后生成候选。" : "方向库中没有这个说法。"}</h2>
        <p>${matched
          ? "确认这次识别的方向与应用场景。候选数量会随方向关键词的关联强度变化。"
          : "可以改选最接近的方向，或使用全库数据继续生成。"}</p>
      </div>

      <div class="review-grid is-single">
        <div class="review-main">
          <div class="review-block">
            <span class="review-label">你的输入</span>
            <p class="review-query">${escapeHtml(query)}</p>
          </div>

          <div class="review-block">
            <span class="review-label">识别结果</span>
            <div class="review-match">
              <div>
                <strong>${escapeHtml(directionName)}</strong>
                <span class="review-cat">${escapeHtml(category)}</span>
              </div>
              <span class="badge ${matched ? "badge-accent" : "badge-warn"}">${matched ? (pending.source === "tags" ? "标签组合命中" : pending.source === "browse" ? "目录选择" : confidenceLabel(confidence)) : "未命中方向库"}</span>
            </div>
            ${entry?.aliasOf ? `<p class="review-alias">方向库中对应：${escapeHtml(entry.name)}</p>` : ""}
            ${near ? `<p class="review-warn">${icon("alert")} 近似匹配，请确认方向是否正确。</p>` : ""}
          </div>

          ${apps.length ? `
          <div class="review-block">
            <span class="review-label">应用场景</span>
            <div class="review-terms">
              ${apps.map((app) => `<span class="badge badge-accent">${escapeHtml(app.name)}<em>${escapeHtml(app.group || "")}</em></span>`).join("")}
            </div>
          </div>` : ""}

          <div class="review-block">
            <span class="review-label">匹配依据</span>
            <div class="review-terms">
              ${terms.length
                ? terms.map((item) => `<span class="badge">${escapeHtml(item.label)}<em>${escapeHtml(item.kind)}</em></span>`).join("")
                : `<span class="review-empty">${matched ? "按方向名直接匹配" : "没有可展示的匹配词"}</span>`}
            </div>
          </div>

          <div class="review-block review-next">
            <span class="review-label">下一步</span>
            <p>按方向关键词与场景标签生成可核查的候选，并附上数据集、指标与基线。数据关系可在素材库单独核对。</p>
            <button type="button" class="btn btn-quiet" data-action="go-materials">${icon("book")} 在素材库查看数据与基线</button>
          </div>

          ${altHtml}
        </div>
      </div>

      <div class="review-actions">
        ${matched
          ? `<button type="button" class="btn btn-primary" data-action="confirm-direction">确认方向，生成候选 ${icon("arrow")}</button>`
          : `<button type="button" class="btn btn-primary" data-action="confirm-direction" data-mode="fallback">仍然用「${escapeHtml(query)}」生成候选 ${icon("arrow")}</button>`}
        <button type="button" class="btn" data-action="reset-direction">${matched ? "重新输入" : "换一个方向"}</button>
        <span class="review-action-note">确认后仍可改选候选、改写描述并做结构体检。</span>
      </div>
    </section>`;
}

function workshopResultsHtml() {
  const d = state.directionData;
  const terms = state.matched && state.direction ? matchedTerms(state.direction, state.query) : [];
  const matcher = state.matched
    ? `<span class="badge badge-accent">${confidenceLabel(state.confidence)}</span>
       <span class="rb-key">领域</span><span class="rb-val">${escapeHtml(state.direction.category || "未归类")}</span>
       <span class="rb-key">方向</span><span class="rb-val">${escapeHtml(state.direction.aliasOf || state.direction.name)}</span>
       ${terms.length ? `<span class="rb-key">依据</span><span class="rb-val rb-terms">${terms.slice(0, 3).map((item) => escapeHtml(item.label)).join(" / ")}</span>` : ""}`
    : `<span class="badge badge-warn">未命中方向库</span><span class="rb-val">${escapeHtml(state.query)}</span><span class="rb-key">候选可生成，导师 / 期刊 / 证据使用全库数据</span>`;

  return `
    <div class="recognize-bar">
      ${matcher}
      ${state.activeApps?.length ? `<span class="rb-sep"></span><span class="rb-key">场景</span><span class="rb-val rb-terms">${state.activeApps.slice(0, 3).map((a) => escapeHtml(a.name)).join(" / ")}${state.activeApps.length > 3 ? ` +${state.activeApps.length - 3}` : ""}</span>` : ""}
      <span class="rb-right">
        <button type="button" class="rb-link" data-action="go-materials">${icon("book")} 素材库</button>
        <button type="button" class="rb-link" data-action="edit-direction">${icon("arrow-left")} 调整方向</button>
      </span>
    </div>
    ${d?.loadError ? `<div class="notice warn" style="margin-top:var(--sp-2)">${icon("alert")}<div>方向数据读取失败，已回退到全库数据：${escapeHtml(d.loadError)}</div></div>` : ""}
    <div class="workshop-grid">
      <div>
        <div class="candidate-head">
          <div class="candidate-head-main">
            <div class="candidate-kicker">CANDIDATE SET</div>
            <div class="candidate-head-row"><strong>候选选题</strong><span class="count" id="candidateCount">${fmtInt(filteredCandidates().length)} / ${fmtInt(state.candidates.length)} 条</span><span id="savedInline">${savedInlineHtml()}</span></div>
            <div class="candidate-policy">${escapeHtml(state.candidates[0]?.candidateMeta?.policy || "按方向关键词关联动态生成")}</div>
          </div>
          <div class="filter-row">
            ${["all", "稳健邻接", "跨领域迁移", "高风险高回报"].map((key) => {
              const count = key === "all" ? state.candidates.length : state.candidates.filter((c) => c.strategy === key).length;
              return `<button type="button" class="chip ${state.filter === key ? "active" : ""}" data-action="filter" data-filter="${key}">${key === "all" ? "全部" : key} ${count}</button>`;
            }).join("")}
          </div>
        </div>
        <div class="candidate-list" id="candidateList">${candidateListHtml(filteredCandidates())}</div>
      </div>
      <div class="card detail" id="detailPanel">${detailHtml()}</div>
    </div>`;
}

function filteredCandidates() {
  return state.filter === "all" ? state.candidates : state.candidates.filter((c) => c.strategy === state.filter);
}

function savedInlineHtml() {
  if (!state.saved.length) return "";
  return `<button type="button" class="candidate-plan-link" data-action="go-plan">${icon("calendar")} 已加入 ${fmtInt(state.saved.length)} 个 · 查看计划</button>`;
}

function candidateListHtml(list) {
  if (!list.length) return emptyBlock("filter", "这个筛选下没有候选", "换一个角度分类试试。");
  return list.map((c, i) => {
    const selected = c.title === state.selected?.title;
    const saved = state.saved.some((x) => x.id === ideaId(c));
    return `
      <div class="candidate-row" style="--i:${i}">
        <button type="button" class="candidate ${selected ? "selected" : ""}" data-action="candidate"
          data-title="${escapeHtml(c.title)}" aria-pressed="${selected}">
          <span class="candidate-index">${String(i + 1).padStart(2, "0")}</span>
          <span class="candidate-main">
            <span class="candidate-top">
              <span class="candidate-title">${escapeHtml(c.title)}</span>
              <span class="candidate-score" title="综合分只由角度与方向计算">${c.score}</span>
            </span>
            <span class="candidate-meta">
              <span class="badge">${escapeHtml(c.strategy)}</span>
              <span class="badge">${escapeHtml(c.angle)}</span>
            </span>
            <span class="candidate-reason clamp-2">${escapeHtml(c.reason)}</span>
            ${c.datasets?.length ? `<span class="candidate-data">${icon("book")} 数据 ${escapeHtml(c.datasets.slice(0, 2).map((d) => d.name).join(" / "))}</span>` : ""}
            <span class="candidate-foot">
              <span class="cf-dim"><i class="cf-track"><b style="width:${c.relevance}%"></b></i>相关 ${c.relevance}</span>
              <span class="cf-dim"><i class="cf-track nov"><b style="width:${c.novelty}%"></b></i>新颖 ${c.novelty}</span>
              <span class="cf-dim"><i class="cf-track fea"><b style="width:${c.feasibility}%"></b></i>可行 ${c.feasibility}</span>
            </span>
          </span>
        </button>
        <button type="button" class="candidate-add ${saved ? "is-saved" : ""}" data-action="quick-add" data-title="${escapeHtml(c.title)}"
          aria-label="${saved ? "取消加入研究计划" : "加入研究计划"}" aria-pressed="${saved}" title="${saved ? "再次点击取消加入" : "加入研究计划"}">
          ${saved
            ? `<span class="ca-saved">${icon("check")}已加入</span><span class="ca-unsave">${icon("x")}取消</span>`
            : `${icon("plus")}<span>加入</span>`}
        </button>
      </div>`;
  }).join("");
}

function detailHtml() {
  const c = state.selected;
  if (!c) return emptyBlock("target", "从左侧挑一条候选", "点击任意候选，这里会展开理由、验证问题与结构体检。");
  const d = state.directionData;
  const idx = Math.max(0, state.candidates.findIndex((x) => x.title === c.title)) + 1;
  const tabs = [
    ["card", "选题卡"],
    ["diagnosis", "结构体检"],
    ["advisors", `导师 ${d?.advisors?.length || 0}`],
    ["venues", `期刊 ${d?.venues?.length || 0}`],
    ["evidence", "证据"],
  ];
  const saved = state.saved.some((x) => x.id === ideaId(c));
  return `
    <div class="detail-kicker"><span>RESEARCH BRIEF</span><span>NO. ${String(idx).padStart(2, "0")}</span></div>
    <div class="detail-head">
      <div class="row between">
        <span class="badge badge-accent">${escapeHtml(c.strategy)}</span>
        <span class="small muted">综合 ${c.score} 分 · 本地估算</span>
      </div>
      <h2 class="detail-title">${escapeHtml(c.title)}</h2>
      <div class="detail-meta">
        <span class="badge">${escapeHtml(c.angle)}</span>
        <span class="badge">相关 ${c.relevance}</span>
        <span class="badge">新颖 ${c.novelty}</span>
        <span class="badge">可行 ${c.feasibility}</span>
        ${saved ? `<span class="badge badge-ok">${icon("check")} 已加入计划</span>` : ""}
      </div>
    </div>
    <div class="tabs" role="tablist">
      ${tabs.map(([key, label]) => `<button type="button" class="tab ${state.detailTab === key ? "active" : ""}" data-action="tab" data-tab="${key}" role="tab" aria-selected="${state.detailTab === key}">${label}${key === "diagnosis" && !state.diagnosis ? '<span class="dot"></span>' : ""}</button>`).join("")}
    </div>
    <div class="detail-body">
      ${
        state.detailTab === "diagnosis" ? diagnosisTabHtml(c)
        : state.detailTab === "advisors" ? advisorsTabHtml()
        : state.detailTab === "venues" ? venuesTabHtml()
        : state.detailTab === "evidence" ? evidenceTabHtml()
        : detailCardHtml(c)
      }
    </div>`;
}

function detailCardHtml(c) {
  const saved = state.saved.some((x) => x.id === ideaId(c));
  const apps = c.applicationNames?.length ? c.applicationNames : (state.activeApps || []).map((a) => a.name);
  return `
    <div class="detail-section">
      <div class="section-label">${icon("spark")} 选题说明</div>
      <div class="brief-grid">
        <div><span>应用场景</span><b>${escapeHtml(apps.length ? apps.join(" / ") : (state.direction?.category || "通用"))}</b></div>
        <div><span>切入角度</span><b>${escapeHtml(c.angle)}</b></div>
        <div><span>需要证明</span><b>${escapeHtml(c.questions?.[0] || "机制成立时，哪个指标会怎么变？")}</b></div>
        <div><span>第一件事</span><b>${escapeHtml(c.minExperiment)}</b></div>
      </div>
    </div>
    <div class="detail-section">
      <div class="section-label">${icon("bulb")} 为什么值得做</div>
      <p class="body-text">${escapeHtml(c.reason)}</p>
    </div>
    <div class="detail-section">
      <div class="section-label">${icon("book")} 可参考的数据集与评测</div>
      ${benchmarkHtml(c)}
    </div>
    <div class="detail-section">
      <div class="section-label">${icon("filter")} 三个维度（同组对比）</div>
      ${dimensionChartHtml(c)}
      <p class="small muted" style="margin-top:var(--sp-2)">三个分只由方向与切入角度计算，不代表文献新颖性，也不是评审结论。虚线是本次 ${fmtInt(state.candidates.length)} 条候选的中位数，条形越长不代表越值得做。</p>
    </div>
    <div class="detail-actions">
      <button type="button" class="btn ${saved ? "is-saved" : "btn-primary"}" data-action="save-idea" aria-pressed="${saved}"
        title="${saved ? "再次点击取消加入" : "加入研究计划"}">
        ${saved ? `${icon("x")} 取消加入` : `${icon("plus")} 加入计划`}
      </button>
      ${saved ? `<button type="button" class="btn" data-action="go-plan">${icon("calendar")} 查看计划</button>` : ""}
      <button type="button" class="btn" data-action="tab" data-tab="diagnosis">${icon("target")} 开始结构体检</button>
      <button type="button" class="btn btn-quiet" data-action="copy-idea">${icon("copy")} 复制选题</button>
    </div>`;
}

function benchmarkHtml(c) {
  const datasets = c.datasets || [];
  const metrics = c.metrics || [];
  const baselines = c.baselines || [];
  return `
    ${datasets.length ? `<div class="bench-cards">
      ${datasets.map((ds) => {
        const url = safeUrl(ds.url);
        const body = `
          <b>${escapeHtml(ds.name)}</b>
          <small>${escapeHtml(ds.task || "任务未标注")}</small>
          <span>${escapeHtml(ds.note || "使用前核对官方划分与许可。")}</span>`;
        return url
          ? `<a class="bench-card" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${body}<em>${icon("external")} 数据集主页</em></a>`
          : `<div class="bench-card">${body}<em class="muted">暂无官方链接，请检索名称</em></div>`;
      }).join("")}
    </div>` : `<p class="small muted">该方向暂无整理好的数据集条目。不要直接把这里当成数据可得性结论。</p>`}
    <div class="bench-facts">
      <div><span>主指标</span><p>${metrics.length ? metrics.map(escapeHtml).join(" · ") : "待按任务确定"}</p></div>
      <div><span>代表基线</span><p>${baselines.length ? baselines.map(escapeHtml).join(" · ") : "待点名 1–2 个最强对手"}</p></div>
    </div>
    ${c.benchmarkNote ? `<p class="small muted" style="margin-top:var(--sp-2)">${escapeHtml(c.benchmarkNote)}</p>` : ""}`;
}

function dimensionChartHtml(c) {
  const dims = [
    { key: "relevance", label: "相关性", value: c.relevance, color: "rel" },
    { key: "novelty", label: "新颖性", value: c.novelty, color: "nov" },
    { key: "feasibility", label: "可行性", value: c.feasibility, color: "fea" },
  ];
  const medianOf = (key) => {
    const values = state.candidates.map((x) => Number(x[key]) || 0).sort((a, b) => a - b);
    if (!values.length) return 0;
    const mid = Math.floor(values.length / 2);
    return values.length % 2 ? values[mid] : Math.round((values[mid - 1] + values[mid]) / 2);
  };
  const total = state.candidates.length || 1;
  const rows = dims.map((d) => {
    const median = medianOf(d.key);
    const rank = 1 + state.candidates.filter((x) => x[d.key] > d.value).length;
    const delta = d.value - median;
    const deltaText = delta === 0 ? "持平" : `${delta > 0 ? "+" : ""}${delta}`;
    return `
      <div class="dim-row">
        <span class="dim-label">${d.label}</span>
        <span class="dim-track"><i class="dim-fill ${d.color}" style="width:${d.value}%"></i><i class="dim-median" style="left:${median}%"></i></span>
        <b class="dim-value">${d.value}</b>
        <span class="dim-delta ${delta > 0 ? "up" : delta < 0 ? "down" : ""}">${deltaText}<small> vs 中位</small></span>
        <span class="dim-rank">第 ${rank} / ${total}</span>
      </div>`;
  }).join("");
  const read = c.relevance >= 80
    ? "相关性强，适合作为该方向的主线候选。"
    : "相关性偏低，更像一次跨领域迁移，需要额外证明问题仍然成立。";
  const novelty = c.novelty >= 80
    ? "角度较新，但要用更强的失败证据支撑。"
    : c.novelty <= 60 ? "角度常见，评审会追问与已有工作的差别。" : "新颖性中等，关键是给出可复现的差异。";
  const feasible = c.feasibility >= 80
    ? "可行性高，适合先做两周最小验证。"
    : c.feasibility <= 55 ? "可行性偏低，数据、算力或评测门槛较高，先确认资源。" : "可行性中等，建议把范围缩到一个场景。";
  return `
    <div class="dim-chart">
      <div class="dim-scale"><span>0</span><span>50</span><span>100</span></div>
      ${rows}
    </div>
    <p class="dim-read">${escapeHtml(`${read}${novelty}${feasible}`)}</p>`;
}

function diagnosisTabHtml(c) {
  return `
    <div class="notice quiet">
      ${icon("info")}
      <div><strong>只列可核查项，不打质量分。</strong>「消融」两个字不等于设计了消融，「指标」两个字不等于定义了指标。请用完整句子描述场景、机制、对比与失败判据。</div>
    </div>
    <div class="field" style="margin-top:var(--sp-3)">
      <label for="ideaDesc">研究简述（标题自动带入：${escapeHtml(c.title)}）</label>
      <textarea id="ideaDesc" class="textarea" maxlength="1200" placeholder="在什么场景下，现有方法哪一步失效、差多少？你改变了什么、为什么会导致可测结果？用什么数据、基线、指标验证？">${escapeHtml(state.desc)}</textarea>
    </div>
    <div class="row" style="margin-top:var(--sp-2)">
      <button type="button" class="btn btn-primary" data-action="diagnose">${icon("target")} 体检这版描述</button>
      <button type="button" class="btn" data-action="load-sample">载入示例（红外场景）</button>
      <button type="button" class="btn btn-quiet" data-action="clear-desc">清空</button>
    </div>
    ${state.diagnosis ? diagnosisResultHtml(state.diagnosis) : `
      <div class="diag-empty">
        ${icon("info")}
        <div>还没有体检结果。填写后点「体检这版描述」，系统会逐项核查 9 个结构条件；也可以用示例先看规则。</div>
      </div>`}`;
}

function diagnosisResultHtml(diag) {
  const all = [...diag.passed, ...diag.missing].sort((a, b) => DIAG_ORDER.indexOf(a.key) - DIAG_ORDER.indexOf(b.key));
  const passedKeys = new Set(diag.passed.map((p) => p.key));
  return `
    <div class="diag-result">
      <div class="diag-stage">
        <span class="stage-num">${diag.stageNum}</span>
        <div class="stage-main">
          <div class="stage-label">STRUCTURE AUDIT</div>
          <div class="stage-name">${escapeHtml(diag.stage)}</div>
          <div class="stage-hint">${escapeHtml(diag.stageHint)}</div>
        </div>
        <span class="badge ${diag.count.passed >= 7 ? "badge-ok" : diag.count.passed >= 4 ? "badge-warn" : "badge-bad"}">${diag.count.passed} / 9 项可核查</span>
      </div>
      <div class="diag-dots">
        ${all.map((item, i) => `<div class="diag-dot ${passedKeys.has(item.key) ? "pass" : ""}" title="${escapeHtml(item.fix || "")}"><span class="diag-index">${String(i + 1).padStart(2, "0")}</span><span class="dot"></span>${escapeHtml(DIAG_LABEL[item.key] || item.label)}</div>`).join("")}
      </div>
      ${diag.warnings?.length ? `<div class="notice warn diag-warn">${icon("alert")}<div>${diag.warnings.map(escapeHtml).join("<br>")}</div></div>` : ""}
      <div class="notice warn diag-warn ${state.diagnosisStale ? "" : ""}" id="diagStale" ${state.diagnosisStale ? "" : "hidden"}>
        ${icon("alert")}<div>描述已修改，下面的结果可能过期，请重新体检。</div>
      </div>
      ${diag.missing.length ? `
        <div class="detail-section">
          <div class="section-label">${icon("alert")} 还缺什么</div>
          <div class="diag-missing">
            ${diag.missing.map((m) => `<div class="missing-item"><div class="mi-head">${icon("plus")}${escapeHtml(m.label)}</div><div class="mi-fix">${escapeHtml(m.fix)}</div></div>`).join("")}
          </div>
        </div>` : ""}
      <div class="detail-section">
        <div class="section-label">${icon("arrow")} 下一步</div>
        <ul class="bullet-list">${diag.next.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>
      </div>
      <p class="small muted">结构体检不是质量分，也不判断想法是否真的新。它只回答：按现在的描述，别人能不能核查你说的问题、机制与实验。</p>
    </div>`;
}

function advisorsTabHtml() {
  const advisors = state.directionData?.advisors || [];
  if (!advisors.length) {
    return emptyBlock("users", "该方向暂无匹配学者", "OpenAlex 主题颗粒度有限；可以到导师页浏览全部收录学者。", `<button class="btn" data-action="go-advisors">${icon("search")} 去看学者</button>`);
  }
  return `
    <div class="mini-list">
      ${advisors.slice(0, 5).map((a) => `
        <div class="mini-item">
          <div class="avatar">${escapeHtml(initials(a.name))}</div>
          <div class="mini-main">
            <div class="mini-title">${escapeHtml(a.name)}</div>
            <div class="mini-sub">${escapeHtml(a.institutionZh || a.institution || "机构未标注")}${a.province ? ` · ${escapeHtml(a.province)}` : ""}</div>
            <div class="mini-sub">引用 ${fmtInt(a.cited)} · 论文 ${fmtInt(a.works)}${a.fields?.length ? ` · ${escapeHtml(a.fields.join(" / "))}` : ""}</div>
          </div>
          ${a.orcid ? `<a class="mini-num" href="${escapeHtml(safeUrl(a.orcid))}" target="_blank" rel="noopener noreferrer" title="ORCID">${icon("external")}</a>` : ""}
        </div>`).join("")}
    </div>
    <div class="detail-actions">
      <button class="btn" data-action="go-advisors">${icon("users")} 查看全部 ${advisors.length} 位</button>
      <span class="small muted" style="align-self:center">按大类 / 领域 / 关键词匹配，ORCID 可核验</span>
    </div>`;
}

function venuesTabHtml() {
  const venues = state.directionData?.venues || [];
  if (!venues.length) {
    return emptyBlock("award", "该方向暂无 venue 推荐", "可以到期刊会议页按 CCF 等级与领域筛选。", `<button class="btn" data-action="go-venues">${icon("search")} 去期刊会议</button>`);
  }
  return `
    <div class="mini-list">
      ${venues.slice(0, 5).map((v) => `
        <div class="mini-item">
          ${ccfBadge(v.ccf)}
          <div class="mini-main">
            <div class="mini-title">${escapeHtml(v.name)} <span class="small muted">${escapeHtml(v.type || "")}${v.country ? ` · ${escapeHtml(v.country)}` : ""}</span></div>
            <div class="mini-sub">${escapeHtml(v.intro || "")}</div>
          </div>
          ${safeExternal(v.url, "主页", "mini-num")}
        </div>`).join("")}
    </div>
    <div class="detail-actions">
      <button class="btn" data-action="go-venues">${icon("award")} 查看全部 ${venues.length} 个</button>
      <span class="small muted" style="align-self:center">CCF 分级按 2026 年第七版目录，不含影响因子</span>
    </div>`;
}

function evidenceTabHtml() {
  const d = state.directionData;
  if (!d) return emptyBlock("gap", "暂无证据", "先生成一个方向。");
  const scope = d.scope || {};
  const gap = d.gap || {};
  return `
    <div class="notice quiet">
      ${icon("gap")}
      <div><strong>${escapeHtml(scope.gapSource === "本方向" ? "本方向证据" : "全库证据")}</strong>：${escapeHtml(scope.note || "")} 本地直接匹配 ${fmtInt(scope.localTotal || 0)} 篇。</div>
    </div>
    <div class="detail-section">
      <div class="section-label">${icon("filter")} 方法 / 任务频次</div>
      ${barList(gap.methods, "本方向暂无方法词频")}
      <div style="height:var(--sp-2)"></div>
      ${barList(gap.tasks, "本方向暂无任务词频")}
    </div>
    ${gap.combos?.length ? `
      <div class="detail-section">
        <div class="section-label">${icon("gap")} 已被做过的组合</div>
        <div class="mini-list">
          ${gap.combos.slice(0, 4).map((c) => `<div class="mini-item"><div class="mini-main"><div class="mini-title">${escapeHtml(c.method)} × ${escapeHtml(c.task)}</div><div class="mini-sub">${fmtInt(c.count)} 篇${c.examples?.[0] ? ` · ${escapeHtml(String(c.examples[0]).slice(0, 76))}` : ""}</div></div></div>`).join("")}
        </div>
      </div>` : ""}
    ${gap.gaps?.length ? `
      <div class="detail-section">
        <div class="section-label">${icon("bulb")} 候选空白</div>
        <div class="mini-list">
          ${gap.gaps.slice(0, 3).map((g) => `<div class="mini-item"><div class="mini-main"><div class="mini-title">${escapeHtml(g.method)} × ${escapeHtml(g.task)}</div><div class="mini-sub">${escapeHtml(g.why || "")}</div></div></div>`).join("")}
        </div>
      </div>` : ""}
    <div class="notice warn" style="margin-top:var(--sp-3)">
      ${icon("alert")}
      <div><strong>别把“本地没共现”当成“学界没人做”。</strong>Web 版只统计 345 篇文献标题；完整版会用 53.8 万篇 arXiv 向量做近邻核查。这里的结果是选题线索，不是新颖性证明。</div>
    </div>`;
}

function initials(name) {
  const text = String(name || "").trim();
  if (!text) return "?";
  if (/^[A-Za-z]/.test(text)) {
    return text.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  }
  return text.slice(0, 1);
}

// ---------- 素材库 ----------
function ensureMaterials() {
  if (state.materials || state.materialsLoading) return;
  state.materialsLoading = true;
  state.materialsError = "";
  loadMaterials()
    .then((data) => { state.materials = data; })
    .catch((err) => { state.materialsError = String(err?.message || err); })
    .finally(() => {
      state.materialsLoading = false;
      if (state.route === "materials") render();
    });
}

function materialDatasets() {
  const rows = state.materials?.datasets || [];
  const q = state.materialsQuery.trim().toLowerCase();
  return rows.filter((ds) => {
    if (state.materialsCat && !(ds.categories || []).includes(state.materialsCat)) return false;
    if (state.materialsApp && !(ds.applications || []).includes(state.materialsApp)) return false;
    if (!q) return true;
    const hay = [
      ds.name, ds.task, ds.note,
      ...(ds.categories || []),
      ...(ds.applications || []),
      ...(ds.directions || []).map((d) => d.name),
    ].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(q);
  });
}

function materialsView() {
  if (!state.materials && !state.materialsLoading && !state.materialsError) ensureMaterials();
  if (state.materialsError) {
    return `<div class="card"><div class="notice warn">${icon("alert")}<div>素材库读取失败：${escapeHtml(state.materialsError)}</div></div><div class="detail-actions"><button class="btn" data-action="retry-materials">重试</button></div></div>`;
  }
  if (!state.materials) {
    return `${pageHead("素材库", "把方向、公开数据集、评测指标与基线放在同一张关系索引里。", "")}
      <div class="card"><div class="skeleton" style="height:44px;margin-bottom:var(--sp-3)"></div><div class="skeleton" style="height:220px"></div></div>`;
  }
  const m = state.materials;
  const datasets = materialDatasets();
  const selected = datasets.find((ds) => ds.name === state.materialsSelected) || datasets[0] || null;
  const shown = datasets.slice(0, state.materialsLimit);
  const stats = m.stats || {};
  return `
    ${pageHead(
      "素材库",
      "方向、公开数据集与评测协议的关系索引。选题前先确认数据是否存在、指标是否可测、基线是否点名。",
      `<a class="btn" href="#/workshop">${icon("spark")} 去选题工坊</a>`
    )}
    <section class="material-hero">
      <div class="material-hero-copy">
        <div class="query-kicker"><span>MATERIAL ATLAS</span><b>02</b></div>
        <h2>先看素材，<br><em>再定问题。</em></h2>
        <p>${fmtInt(stats.directions)} 个方向、${fmtInt(stats.datasets)} 个公开数据集、${fmtInt(stats.categories)} 个已挂数据集的研究大类。这里展示的是项目整理的关系，不是最新 SOTA 榜单。</p>
      </div>
      <div class="material-stats">
        <div><b>${fmtInt(stats.directions)}</b><span>研究方向</span></div>
        <div><b>${fmtInt(stats.datasets)}</b><span>公开数据集</span></div>
        <div><b>${fmtInt(stats.venues)}</b><span>期刊会议</span></div>
        <div><b>${fmtInt(stats.papers)}</b><span>本地文献</span></div>
        <div><b>${fmtInt(stats.scholars)}</b><span>可浏览学者</span></div>
        <div><b>${fmtInt(stats.withPaper)}</b><span>数据集含论文出处</span></div>
      </div>
    </section>
    <div class="material-relation" aria-label="素材关系">
      <div class="material-node"><span>方向</span><b>${fmtInt(stats.directions)}</b><small>决定问题与场景</small></div>
      <span class="material-arrow">${icon("arrow")}</span>
      <div class="material-node"><span>数据集</span><b>${fmtInt(stats.datasets)}</b><small>决定数据与划分</small></div>
      <span class="material-arrow">${icon("arrow")}</span>
      <div class="material-node"><span>指标 / 基线</span><b>${fmtInt((m.directions || []).filter((d) => d.metrics?.length).length)}</b><small>个方向已挂基准卡</small></div>
    </div>
    <div class="card material-toolbar">
      <div class="material-search">
        <label class="query-label" for="materialQuery">检索数据集、方向或任务</label>
        <div class="input-row">
          <input id="materialQuery" class="input" type="text" value="${escapeHtml(state.materialsQuery)}" placeholder="例如：红外、医学影像、检测、KITTI" autocomplete="off">
          <button type="button" class="btn" data-action="material-clear">清空</button>
        </div>
      </div>
      <div class="material-filters">
        <div class="material-filter-row">
          <span class="material-filter-label">研究大类 <small>数字 = 数据集数</small></span>
          <div class="material-cats" role="group" aria-label="按研究大类筛选">
            <button type="button" class="chip ${!state.materialsCat ? "active" : ""}" data-action="material-cat" data-cat="">全部 ${fmtInt(stats.datasets)}</button>
            ${(m.categories || []).map((cat) => `<button type="button" class="chip ${state.materialsCat === cat.name ? "active" : ""}" data-action="material-cat" data-cat="${escapeHtml(cat.name)}" title="${fmtInt(cat.datasetCount)} 个数据集 · ${fmtInt(cat.directionCount)} 个方向">${escapeHtml(cat.name)} <em>${fmtInt(cat.datasetCount)}</em></button>`).join("")}
          </div>
        </div>
        <div class="material-filter-row">
          <span class="material-filter-label">应用场景 <small>数字 = 数据集数 · 可叠加</small></span>
          <div class="material-cats" role="group" aria-label="按应用场景筛选">
            <button type="button" class="chip ${!state.materialsApp ? "active" : ""}" data-action="material-app" data-app="">全部场景</button>
            ${(m.applications || []).map((app) => `<button type="button" class="chip ${state.materialsApp === app.name ? "active" : ""}" data-action="material-app" data-app="${escapeHtml(app.name)}">${escapeHtml(app.name)} <em>${fmtInt(app.count)}</em></button>`).join("")}
          </div>
        </div>
      </div>
      <div class="search-meta"><span>${fmtInt(datasets.length)} 个数据集${state.materialsCat ? ` · ${escapeHtml(state.materialsCat)}` : ""}${state.materialsApp ? ` · ${escapeHtml(state.materialsApp)}` : ""}</span><span>${datasets.length > shown.length ? `已显示 ${fmtInt(shown.length)} / ${fmtInt(datasets.length)} 个数据集` : "已全部显示"}</span></div>
    </div>
    <div class="material-grid">
      <div class="material-list">
        ${shown.length ? shown.map((ds) => materialCardHtml(ds, selected?.name === ds.name)).join("") : `<div class="card">${emptyBlock("search", "没有匹配的数据集", "换一个关键词或大类；也可以清空筛选查看全部。")}</div>`}
        ${datasets.length > shown.length ? `<div class="load-more"><button type="button" class="btn" data-action="material-more">显示更多数据集</button></div>` : ""}
      </div>
      <aside class="material-detail" id="materialDetail">${materialDetailHtml(selected)}</aside>
    </div>
    <div class="notice quiet" style="margin-top:var(--sp-3)">
      ${icon("info")}
      <div><strong>怎么读这些数字：</strong>大类与场景胶囊上的数字都是“当前筛选池中归属于该项的数据集数量”，不是方向数量，也不是标签总数；同一数据集可归入多个大类与场景，因此分类合计会大于 ${fmtInt(stats.datasets)} 个数据集。当前 ${fmtInt(stats.datasets)} 个条目全部附官方主页，其中 ${fmtInt(stats.withPaper)} 个另附可核对的来源或代表论文；其余多为长期维护的数据仓库、竞赛数据或行业轨迹，以官方数据说明为准，页面会直接写明，而不是虚构引用。链接与许可请以官方页面为准；素材库不声称覆盖全部公开数据，也不替代论文查新。</div>
    </div>`;
}

function materialCardHtml(ds, active) {
  return `
    <button type="button" class="material-card ${active ? "active" : ""}" data-action="material-select" data-name="${escapeHtml(ds.name)}">
      <span class="material-card-head">
        <b>${escapeHtml(ds.name)}</b>
        <em>${ds.directionCount ? `${fmtInt(ds.directionCount)} 个方向` : "通用基准"}</em>
      </span>
      <span class="material-task">${escapeHtml(ds.task || "任务未标注")}</span>
      <span class="material-tags">${(ds.categories || []).slice(0, 2).map((c) => `<i>${escapeHtml(c)}</i>`).join("")}${(ds.applications || []).slice(0, 2).map((a) => `<i>${escapeHtml(a)}</i>`).join("")}</span>
      <span class="material-foot">
        <span>${escapeHtml((ds.metrics || []).slice(0, 3).join(" · ") || "指标待按任务确定")}</span>
        <span>查看 ${icon("arrow")}</span>
      </span>
    </button>`;
}

function materialDetailHtml(ds) {
  if (!ds) return `<div class="material-detail-empty">${icon("book")}<b>选择一个数据集</b><p>查看它关联的方向、常用指标、代表基线与官方入口。</p></div>`;
  const directions = ds.directions || [];
  return `
    <div class="material-detail-head">
      <div>
        <div class="material-detail-kicker">DATASET RELATION</div>
        <h3>${escapeHtml(ds.name)}</h3>
        <p>${escapeHtml(ds.task || "任务未标注")}</p>
      </div>
      <div class="material-detail-links">
        ${safeUrl(ds.url) ? `<a class="btn btn-soft" href="${escapeHtml(safeUrl(ds.url))}" target="_blank" rel="noopener noreferrer">${icon("external")} 数据集主页</a>` : `<span class="badge">暂无官方链接</span>`}
        ${safeUrl(ds.paperUrl) ? `<a class="btn btn-quiet" href="${escapeHtml(safeUrl(ds.paperUrl))}" target="_blank" rel="noopener noreferrer">${icon("book")} 来源论文</a>` : ""}
      </div>
    </div>
    <p class="material-note">${escapeHtml(ds.note || "使用前核对官方划分与许可。")}${ds.usedIn ? ` · ${escapeHtml(ds.usedIn)}` : ""}</p>
    <div class="material-source">
      ${ds.paperTitle ? `<span><b>论文出处</b>${safeUrl(ds.paperUrl) ? `<a href="${escapeHtml(safeUrl(ds.paperUrl))}" target="_blank" rel="noopener noreferrer">${escapeHtml(ds.paperTitle)} ${icon("external")}</a>` : escapeHtml(ds.paperTitle)}</span>` : `<span><b>论文出处</b>该条目以官方数据集页为准；未检索到可核对的单独论文。此类条目常见于长期维护的数据仓库、竞赛数据或行业轨迹。</span>`}
      <span><b>链接口径</b>官方主页用于确认版本、划分与许可；页面不转载论文全文。</span>
    </div>
    <div class="material-facts">
      <div><span>关联方向</span><b>${fmtInt(directions.length)}</b></div>
      <div><span>常见指标</span><b>${fmtInt((ds.metrics || []).length)}</b></div>
      <div><span>代表基线</span><b>${fmtInt((ds.baselines || []).length)}</b></div>
    </div>
    <div class="material-section">
      <div class="section-label">${icon("filter")} 常用指标</div>
      <div class="chip-row">${(ds.metrics || []).length ? ds.metrics.map((x) => `<span class="badge">${escapeHtml(x)}</span>`).join("") : `<span class="review-empty">该数据集暂未标注指标</span>`}</div>
    </div>
    <div class="material-section">
      <div class="section-label">${icon("award")} 代表基线</div>
      <div class="chip-row">${(ds.baselines || []).length ? ds.baselines.map((x) => `<span class="badge">${escapeHtml(x)}</span>`).join("") : `<span class="review-empty">该数据集暂未标注基线</span>`}</div>
    </div>
    <div class="material-section">
      <div class="section-label">${icon("route")} 关联方向</div>
      <div class="material-directions">
        ${directions.slice(0, 12).map((dir) => `
          <button type="button" class="material-direction" data-action="material-direction" data-name="${escapeHtml(dir.name)}">
            <span><b>${escapeHtml(dir.name)}</b><small>${escapeHtml(dir.category || "")}</small></span>
            ${icon("arrow")}
          </button>`).join("") || `<span class="review-empty">暂无关联方向</span>`}
      </div>
      ${directions.length > 12 ? `<p class="small muted" style="margin-top:var(--sp-2)">还有 ${fmtInt(directions.length - 12)} 个方向使用该数据集；可在左侧检索方向名。</p>` : ""}
    </div>`;
}

function renderMaterialsOnly() {
  if (state.route !== "materials") return;
  const query = $("#materialQuery");
  const caret = document.activeElement === query ? query.selectionStart : null;
  render();
  if (caret != null) {
    const next = $("#materialQuery");
    next?.focus();
    try { next.setSelectionRange(caret, caret); } catch {}
  }
}

// ---------- 导师与院校 ----------
const REGION_PENDING = "地区待核验";

function normalizeProvince(name) {
  const raw = String(name || "").trim();
  return state.regions?.aliases?.[raw] || raw;
}

function regionOf(a) {
  const province = normalizeProvince(a?.province);
  if (province) return province;
  const country = String(a?.country || "").trim();
  return country || REGION_PENDING;
}

function institutionKey(a) {
  return String(a?.institution || a?.institutionZh || "").trim().toLowerCase();
}

function institutionLabel(a) {
  return a?.institutionZh || a?.institution || "机构待核验";
}

let institutionCache = null;

function institutionData() {
  if (!state.scholars) return { entries: [], rowsByKey: new Map(), rows: [] };
  if (institutionCache && institutionCache.source === state.scholars && institutionCache.orcid === state.orcid) return institutionCache;
  const rowsByKey = new Map();
  const entries = new Map();
  const rows = [];
  for (const raw of state.scholars) {
    const a = mergedScholar(raw);
    const key = institutionKey(a);
    if (!key) continue;
    rows.push(a);
    if (!rowsByKey.has(key)) rowsByKey.set(key, []);
    rowsByKey.get(key).push(a);
    let entry = entries.get(key);
    if (!entry) {
      entry = { key, zh: a.institutionZh || "", en: a.institution || "", region: regionOf(a), count: 0 };
      entries.set(key, entry);
    }
    entry.count += 1;
    if (entry.region === REGION_PENDING && regionOf(a) !== REGION_PENDING) entry.region = regionOf(a);
  }
  const list = [...entries.values()].sort((a, b) => b.count - a.count || (a.zh || a.en).localeCompare(b.zh || b.en, "zh"));
  institutionCache = { source: state.scholars, orcid: state.orcid, entries: list, rowsByKey, rows };
  return institutionCache;
}

function visibleInstitutionEntries() {
  let list = institutionData().entries;
  if (state.advisorProvince) {
    list = list.filter((e) => state.advisorProvince === "__unknown" ? e.region === REGION_PENDING : e.region === state.advisorProvince);
  }
  const q = state.institutionQuery.trim().toLowerCase();
  if (q) list = list.filter((e) => [e.zh, e.en, e.key, e.region].filter(Boolean).join(" ").toLowerCase().includes(q));
  return list;
}

function regionSelectHtml(rows, totalRows = rows.length) {
  const counts = {};
  let pending = 0;
  for (const a of rows) {
    const region = regionOf(a);
    if (region === REGION_PENDING) pending += 1;
    else counts[region] = (counts[region] || 0) + 1;
  }
  const groups = state.regions?.groups || [];
  const known = new Set(groups.flatMap((g) => g.regions));
  const extras = Object.keys(counts).filter((p) => !known.has(p)).sort((a, b) => a.localeCompare(b, "zh"));
  return `
    <option value="">全部地区（${fmtInt(totalRows)} 位）</option>
    ${pending ? `<optgroup label="待核验"><option value="__unknown" ${state.advisorProvince === "__unknown" ? "selected" : ""}>${REGION_PENDING}（${fmtInt(pending)}）</option></optgroup>` : ""}
    ${groups.map((group) => `
      <optgroup label="${escapeHtml(group.name)}">
        ${group.regions.map((p) => `<option value="${escapeHtml(p)}" ${state.advisorProvince === p ? "selected" : ""}>${escapeHtml(p)}（${fmtInt(counts[p] || 0)}）</option>`).join("")}
      </optgroup>`).join("")}
    ${extras.length ? `<optgroup label="其他">${extras.map((p) => `<option value="${escapeHtml(p)}" ${state.advisorProvince === p ? "selected" : ""}>${escapeHtml(p)}（${fmtInt(counts[p] || 0)}）</option>`).join("")}</optgroup>` : ""}`;
}

function activityBarsHtml(activity) {
  if (!activity?.years) return "";
  const years = Object.entries(activity.years).map(([y, n]) => [Number(y), Number(n) || 0]);
  const max = Math.max(1, ...years.map(([, n]) => n));
  const label = years.map(([y, n]) => `${y} 年 ${n} 篇`).join("，");
  return `<div class="activity-chart" role="img" aria-label="${escapeHtml(label)}">
    ${years.map(([y, n]) => `<div class="activity-col"><span class="activity-n">${n || ""}</span><i style="height:${Math.max(3, Math.round((n / max) * 64))}px"></i><em>${y}</em></div>`).join("")}
  </div>`;
}

function advisorModalHtml() {
  const a = state.advisorDetail;
  if (!a) return "";
  const nameQ = encodeURIComponent(displayName(a.name));
  const orcidId = normalizeOrcid(a.orcid);
  const orcid = orcidId ? `https://orcid.org/${orcidId}` : "";
  const homepage = safeUrl(a.homepage);
  const institutionUrl = safeUrl(a.institutionUrl);
  const ror = safeUrl(a.ror) || (a.institutionRor ? `https://ror.org/${a.institutionRor}` : "");
  const regionLabel = regionOf(a);
  const links = [];
  if (homepage) links.push(["个人主页", homepage, a.homepageSource === "CSRankings" ? "CSRankings 收录" : "ORCID 收录"]);
  if (institutionUrl) links.push([a.institutionZh || "院校官网", institutionUrl, "院校官方站点"]);
  const orcidLinkNote = !a.orcidVerified
    ? "身份核验"
    : a.employmentVerified
      ? "身份与任职已核验"
      : a.employmentScope === "unknown"
        ? "仅姓名与作品匹配"
        : "身份与作品已匹配";
  if (orcid) links.push(["ORCID", orcid, orcidLinkNote]);
  if (ror) links.push(["ROR 机构记录", ror, "机构唯一标识"]);
  links.push(["DBLP", `https://dblp.org/search?q=${nameQ}`, "论文列表"]);
  links.push(["Google Scholar", `https://scholar.google.com/scholar?q=${nameQ}`, "引用检索"]);
  const institutionLines = (a.institutionNames || []).filter(Boolean);
  const works = (a.recentWorks || []).slice(0, 3);
  const coverageNote = a.orcidVerified
    ? a.employmentVerified
      ? `ORCID 身份与任职记录核验于 ${escapeHtml(a.orcidCheckedAt || "2026-11-18")}。`
      : a.employmentScope === "china"
        ? `ORCID 姓名与公开作品匹配于 ${escapeHtml(a.orcidCheckedAt || "2026-11-18")}；公开记录包含中国院校任职，具体任职机构仍采用目录归档。`
        : a.employmentScope === "unknown"
          ? `ORCID 姓名与公开作品匹配于 ${escapeHtml(a.orcidCheckedAt || "2026-11-18")}；该记录未公开任职信息，任职机构采用目录归档，建议结合 ORCID 原页核对身份。`
          : `ORCID 身份与公开作品匹配于 ${escapeHtml(a.orcidCheckedAt || "2026-11-18")}；任职与机构采用目录中的院校归档。`
    : a.orcidNameMismatch
      ? a.orcidMismatchReason === "overseasEmployment"
        ? "该 ORCID 公开记录中的任职机构均在海外，与目录中的中国院校不一致，可能是同名学者，未自动合并，因此不展示发表活跃度与近期论文；可在 ORCID 原页核对。"
        : a.orcidMismatchReason === "weakMatch"
          ? "该 ORCID 记录的姓名与目录仅部分匹配，且任职机构无法与目录对应，可能是同名学者，未自动合并，因此不展示发表活跃度与近期论文；可在 ORCID 原页核对。"
          : "该 ORCID 公开记录中的姓名与目录不一致，未自动合并，因此不展示发表活跃度与近期论文；可在 ORCID 原页核对身份。"
      : a.orcid
        ? "该学者的 ORCID 标识已收录，但公开记录快照尚未覆盖，因此不展示发表活跃度与近期论文；可在 ORCID 原页核对。"
        : "该学者暂无 ORCID 标识，发表活跃度与近期论文暂不可用；引用与论文数来自 OpenAlex。";
  return `
    <div class="advisor-modal" role="dialog" aria-modal="true" aria-labelledby="advisorModalTitle">
      <div class="advisor-modal-backdrop" data-action="advisor-close"></div>
      <div class="advisor-modal-panel">
        <button type="button" class="advisor-modal-close" data-action="advisor-close" aria-label="关闭">${icon("x")}</button>
        <div class="advisor-modal-head">
          <div class="avatar">${escapeHtml(initials(displayName(a.name)))}</div>
          <div>
            <div class="advisor-modal-kicker">SCHOLAR PROFILE · ${a.employmentVerified ? "ORCID VERIFIED" : a.orcidVerified ? "ORCID MATCHED" : "INDEXED"}</div>
            <h3 id="advisorModalTitle">${escapeHtml(displayName(a.name))}</h3>
            <p>${escapeHtml(a.institutionZh || a.institution || "机构未标注")}${a.institutionZh && a.institution && a.institutionZh !== a.institution ? ` · ${escapeHtml(a.institution)}` : ""}</p>
            <div class="chip-row">
              ${a.employmentVerified
                ? `<span class="badge badge-accent">${icon("check")} ORCID 已核验</span>`
                : a.orcidVerified
                  ? `<span class="badge badge-accent">${icon("check")} ORCID 已匹配</span>`
                  : ""}
              <span class="badge${regionLabel === REGION_PENDING ? " badge-pending" : ""}">${escapeHtml(regionLabel)}</span>
              ${a.category ? `<span class="badge">${escapeHtml(a.category)}</span>` : ""}
              ${a.reasons?.slice(0, 2).map((r) => `<span class="badge badge-accent">${escapeHtml(r)}</span>`).join("") || ""}
            </div>
          </div>
        </div>
        <div class="advisor-modal-stats">
          <div><b>${fmtInt(a.cited)}</b><span>引用 · OpenAlex</span></div>
          <div><b>${fmtInt(a.works)}</b><span>论文 · OpenAlex</span></div>
          ${a.orcidVerified ? `<div><b>${fmtInt(a.worksTotal || 0)}</b><span>ORCID 收录</span></div>` : ""}
          <div><b>${escapeHtml(regionLabel)}</b><span>地区</span></div>
        </div>
        <div class="advisor-modal-section">
          <span class="section-label">研究方向</span>
          <p>${a.fields?.length ? a.fields.map(escapeHtml).join(" · ") : "方向未标注"}</p>
          ${a.keywords?.length ? `<p class="muted small">${a.keywords.map(escapeHtml).join(" · ")}</p>` : ""}
          ${institutionLines.length > 1 ? `<p class="muted small">关联机构：${institutionLines.map(escapeHtml).join(" · ")}${a.matchedInstitutions > institutionLines.length ? ` 等 ${a.matchedInstitutions} 处` : ""}</p>` : ""}
        </div>
        ${a.orcidVerified && a.activity ? `
        <div class="advisor-modal-section">
          <span class="section-label">发表活跃度 · 2021–2026</span>
          ${a.activity.total ? activityBarsHtml(a.activity) : `<p class="small muted">该 ORCID 记录中暂无公开作品条目。</p>`}
          <p class="small muted">${a.activity.total
            ? `ORCID 记录去重后 ${fmtInt(a.worksTotal || a.activity.total || 0)} 篇；近五年 ${fmtInt(a.activity.recent5 || 0)} 篇，最近发表 ${a.activity.latest || "—"} 年。只统计该 ORCID 下的公开作品，不代表全部成果。`
            : "可在 ORCID 原页继续核对；这里不推断未收录的作品。"}</p>
        </div>` : ""}
        ${works.length ? `
        <div class="advisor-modal-section">
          <span class="section-label">近期论文 · ORCID</span>
          <ol class="work-list">
            ${works.map((w) => {
              const url = safeUrl(w.url) || (w.doi ? `https://doi.org/${w.doi}` : "");
              const meta = [w.year || "", w.venue || PAPER_TYPE_LABEL[w.type] || w.type || ""].filter(Boolean).map(escapeHtml).join(" · ");
              return `<li>${url
                ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(w.title)}${icon("external")}</a>`
                : `<span class="work-title-plain">${escapeHtml(w.title)}</span>`}<small>${meta}${w.doi ? ` · DOI ${escapeHtml(w.doi)}` : ""}</small></li>`;
            }).join("")}
          </ol>
          ${a.papersIndexed !== false
            ? `<button type="button" class="btn btn-quiet" data-action="advisor-papers" data-name="${escapeHtml(a.name)}">${icon("book")} 在论文库查看这位学者</button>`
            : `<p class="small muted">近期作品来自 ORCID；论文库目前只收录推荐学者的公开作品，因此这位学者暂未纳入论文库。</p>`}
        </div>` : ""}
        <div class="advisor-modal-section">
          <span class="section-label">主页与作者入口</span>
          <div class="link-grid">
            ${links.map(([label, url, note]) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}<small>${escapeHtml(note)}</small>${icon("external")}</a>`).join("")}
          </div>
          <p class="small muted" style="margin-top:var(--sp-2)">${homepage
            ? "个人主页只采用 CSRankings 或 ORCID 公开链接；机构官网与 ROR 标识来自 ROR 机构库。"
            : institutionUrl
              ? "暂未收录经过核验的个人主页，因此不提供搜索跳转；可先访问院校官方站点，再用 ORCID 与 DBLP 核对身份和论文。"
              : "暂未收录经过核验的个人主页或院校官网，因此不提供搜索跳转；可先用 ORCID、DBLP 核对身份与论文。"} ${coverageNote}</p>
        </div>
      </div>
    </div>`;
}

function advisorsInstitutionHtml(rows) {
  if (state.scholarsError) {
    return `<div class="card"><div class="notice warn">${icon("alert")}<div>学者数据读取失败：${escapeHtml(state.scholarsError)}</div></div><div class="detail-actions"><button class="btn" data-action="retry-scholars">重试</button></div></div>`;
  }
  if (!state.scholars) {
    return `<div class="card">
      <div class="skeleton" style="height:42px;margin-bottom:var(--sp-3)"></div>
      <div class="institution-list">${Array.from({ length: 6 }).map(() => `<div class="skeleton" style="height:64px"></div>`).join("")}</div>
    </div>`;
  }
  if (!state.advisorInstitution) {
    const list = visibleInstitutionEntries();
    const shown = Math.min(state.institutionLimit, list.length);
    return `
      <div class="card">
        <div class="filter-bar">
          <div class="field wide">
            <label for="institutionQuery">院校名称</label>
            <input id="institutionQuery" class="input" type="text" value="${escapeHtml(state.institutionQuery)}" placeholder="例如：清华大学、University of Oxford" autocomplete="off">
          </div>
          <div class="field">
            <label for="advisorProvince">院校所在地区</label>
            <select id="advisorProvince" class="select" data-change="advisor-province">
              ${regionSelectHtml(institutionData().rows, institutionData().rows.length)}
            </select>
          </div>
        </div>
        <div class="search-meta">
          <span id="institutionMeta">${institutionMetaText()}</span>
          <span class="advisor-tools"><span>共 ${fmtInt(institutionData().entries.length)} 所院校 · 按收录人数排序</span></span>
        </div>
        <div class="institution-list" id="institutionList">${institutionListHtml()}</div>
        <div class="load-more" id="institutionMore">${institutionMoreHtml()}</div>
      </div>`;
  }
  const entry = institutionData().entries.find((e) => e.key === state.advisorInstitution);
  const schoolRows = institutionData().rowsByKey.get(state.advisorInstitution) || [];
  return `
    <div class="card">
      <div class="institution-head">
        <button type="button" class="btn btn-quiet" data-action="advisor-institution-back">${icon("arrow-left")} 返回院校列表</button>
        <div class="institution-head-main">
          <span class="section-label">院校</span>
          <b>${escapeHtml(entry?.zh || entry?.en || state.advisorInstitution)}</b>
          <small>${escapeHtml([entry?.en && entry?.en !== entry?.zh ? entry.en : "", entry?.region || "", `${fmtInt(schoolRows.length)} 位学者`].filter(Boolean).join(" · "))}</small>
        </div>
      </div>
      <div class="filter-bar">
        <div class="field">
          <label for="advisorProvince">院校内地区</label>
          <select id="advisorProvince" class="select" data-change="advisor-province">
            ${regionSelectHtml(schoolRows, schoolRows.length)}
          </select>
        </div>
      </div>
      <div class="search-meta">
        <span id="advisorMeta">${advisorMetaText()}</span>
        <span class="advisor-tools">
          <span>${icon("users")} 按院校浏览</span>
          ${advisorLayoutToggleHtml()}
        </span>
      </div>
      <div class="${advisorGridClass()}" id="advisorList">${advisorListHtml()}</div>
      <div class="load-more" id="advisorMore">${advisorMoreHtml()}</div>
    </div>`;
}

function institutionMetaText() {
  const list = visibleInstitutionEntries();
  const shown = Math.min(state.institutionLimit, list.length);
  const region = state.advisorProvince === "__unknown" ? REGION_PENDING : state.advisorProvince;
  return `${region ? `${region} · ` : ""}找到 ${fmtInt(list.length)} 所院校${list.length > shown ? ` · 已显示 ${fmtInt(shown)}` : ""}`;
}

function institutionListHtml() {
  const list = visibleInstitutionEntries();
  if (!list.length) {
    return emptyBlock(
      "search",
      "没有匹配的院校",
      "换一个校名或地区；也可以清除地区筛选，查看全部院校。",
      `<div class="detail-actions"><button type="button" class="btn" data-action="institution-region-all">查看全部地区院校</button></div>`
    );
  }
  return list.slice(0, state.institutionLimit).map((e) => `
    <button type="button" class="institution-row" data-action="advisor-institution" data-key="${escapeHtml(e.key)}">
      <span class="institution-main">
        <b>${escapeHtml(e.zh || e.en)}</b>
        <small>${escapeHtml([e.en && e.en !== e.zh ? e.en : "", e.region].filter(Boolean).join(" · "))}</small>
      </span>
      <span class="institution-count">${fmtInt(e.count)} 位</span>
      ${icon("arrow")}
    </button>`).join("");
}

function institutionMoreHtml() {
  const total = visibleInstitutionEntries().length;
  const shown = Math.min(state.institutionLimit, total);
  if (shown >= total) return total ? `<span class="small muted">已显示全部 ${fmtInt(total)} 所院校</span>` : "";
  return `<button class="btn" data-action="institution-more">${icon("chevron")} 再加载 ${fmtInt(Math.min(80, total - shown))} 所（已显示 ${fmtInt(shown)} / ${fmtInt(total)}）</button>`;
}

function renderInstitutionOnly() {
  const list = $("#institutionList");
  if (!list) return;
  const input = $("#institutionQuery");
  const caret = document.activeElement === input ? input.selectionStart : null;
  list.innerHTML = institutionListHtml();
  const meta = $("#institutionMeta");
  if (meta) meta.textContent = institutionMetaText();
  const more = $("#institutionMore");
  if (more) more.innerHTML = institutionMoreHtml();
  if (caret != null) {
    const next = $("#institutionQuery");
    next?.focus();
    try { next.setSelectionRange(caret, caret); } catch {}
  }
}

function advisorsView() {
  if (!state.scholars && !state.scholarsLoading && !state.scholarsError) {
    ensureScholars();
  }
  if (!state.orcid && !state.orcidLoading && !state.orcidError) ensureOrcid();
  const directionAdvisors = (state.directionData?.advisors || []).map(mergedScholar);
  const rows = state.advisorMode === "direction" ? directionAdvisors : (state.scholars || []);
  const allCount = state.scholars?.length || state.index.stats.scholars_exported || state.index.stats.scholars_indexed;
  const instData = state.scholars ? institutionData() : { entries: [], rows: [] };
  const schoolCount = instData.entries.length;
  const pendingCount = instData.rows.filter((a) => regionOf(a) === REGION_PENDING).length;
  const verifiedCount = state.orcid ? Object.values(state.orcid.records || {}).filter((r) => r.nameMatch).length : 0;
  const employmentCount = state.orcid ? Object.values(state.orcid.records || {}).filter((r) => r.nameMatch && r.employmentVerified).length : 0;
  return `
    ${pageHead(
      "导师与院校",
      "按方向匹配学者，或浏览全部收录学者；也可以按院校查看每一所学校对应的导师。支持平铺与列表两种视图，点开可查看 ORCID 匹配后的身份、发表活跃度与近期论文。",
      `<a class="btn" href="#/workshop">${icon("spark")} 换方向</a>`
    )}
    <div class="tabs" style="margin-bottom:var(--sp-3)">
      <button class="tab ${state.advisorMode === "direction" ? "active" : ""}" data-action="advisor-mode" data-mode="direction">按方向推荐</button>
      <button class="tab ${state.advisorMode === "search" ? "active" : ""}" data-action="advisor-mode" data-mode="search">全部学者 ${fmtInt(allCount)}</button>
      <button class="tab ${state.advisorMode === "institution" ? "active" : ""}" data-action="advisor-mode" data-mode="institution">院校${schoolCount ? ` ${fmtInt(schoolCount)}` : ""}</button>
    </div>
    ${state.advisorMode === "direction" ? advisorsDirectionHtml(rows) : state.advisorMode === "institution" ? advisorsInstitutionHtml(rows) : advisorsSearchHtml(rows)}
    <div class="notice quiet" style="margin-top:var(--sp-3)">
      ${icon("info")}
      <div><strong>范围说明：</strong>收录 ${fmtInt(allCount)} 位去重后的学者，按 ORCID 合并同一人在多所机构的记录。${verifiedCount ? `其中 ${fmtInt(verifiedCount)} 位的姓名与 2021–2026 年发表活跃度已按 ORCID 公开记录匹配${employmentCount ? `，${fmtInt(employmentCount)} 位同时核验了任职机构` : ""}；公开记录仅含海外任职的同名记录不自动合并，详情页会标注具体匹配范围与已收录的近期论文。` : ""}地区按院校所在机构库（OpenAlex 机构地理字段与 ROR）归档到省市或国家：${pendingCount ? `仍有 ${fmtInt(pendingCount)} 位没有可核验地区，归入「${REGION_PENDING}」，仍可在该分组内查看和筛选` : `全部 ${fmtInt(allCount)} 位均已按院校所在地归档`}；院校视图列出 ${fmtInt(schoolCount)} 所学校，每所学校显示所在地区与人数，点进任一学校即可查看该校学者。未覆盖 ORCID 快照、姓名不一致或任职记录不一致的学者，仍展示 OpenAlex 引用、论文、方向与院校 / DBLP 入口，详情页会直接标注活跃度与近期论文暂不可用的原因。个人主页只使用 CSRankings 与 ORCID 的公开链接；未收录时不提供搜索跳转，改由院校官网、ORCID 与 ROR 机构记录核验。匹配依据是大类、领域与关键词，不是论文全文。</div>
    </div>`;
}

function advisorsDirectionHtml(rows) {
  return `
    <div class="card">
      <div class="filter-bar">
        <div class="field wide suggest-wrap">
          <label for="advisorDirectionInput">研究方向</label>
          <input id="advisorDirectionInput" class="input" type="text" value="${escapeHtml(state.query)}" placeholder="例如：红外小目标检测" autocomplete="off" aria-autocomplete="list" aria-controls="advisorSuggestBox">
          <div class="suggest" id="advisorSuggestBox" hidden></div>
        </div>
        <div class="field">
          <label for="advisorProvince">地区</label>
          <select id="advisorProvince" class="select" data-change="advisor-province">
            ${regionSelectHtml(rows)}
          </select>
        </div>
        <button class="btn btn-primary" data-action="advisor-search-direction">${icon("search")} 查询方向</button>
      </div>
      ${state.directionData ? `
        <div class="search-meta">
          <span id="advisorMeta">${advisorMetaText()}</span>
          <span class="advisor-tools">
            <span>${escapeHtml(state.directionData.category)} · ${escapeHtml(state.directionData.name)}</span>
            ${advisorLayoutToggleHtml()}
          </span>
        </div>
        <div class="${advisorGridClass()}" id="advisorList">${advisorListHtml()}</div>
        <div class="load-more"><button class="btn btn-quiet" data-action="advisor-open-all">${icon("users")} 在全部学者中查看相近方向</button></div>
      ` : `
        <div class="empty">
          <div class="empty-icon">${icon("users")}</div>
          <strong>先给一个方向</strong>
          <p>输入方向后，系统会按大类、领域与关键词匹配学者；也可以直接切到「全部学者」浏览。</p>
          <div class="chip-row">${(state.index.examples || []).slice(0, 3).map((name) => `<button class="chip" data-action="example-advisor" data-name="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("")}</div>
        </div>`}
    </div>`;
}

function advisorsSearchHtml(rows) {
  if (state.scholarsError) {
    return `<div class="card"><div class="notice warn">${icon("alert")}<div>学者数据读取失败：${escapeHtml(state.scholarsError)}</div></div><div class="detail-actions"><button class="btn" data-action="retry-scholars">重试</button></div></div>`;
  }
  if (!state.scholars) {
    return `<div class="card">
      <div class="skeleton" style="height:42px;margin-bottom:var(--sp-3)"></div>
      <div class="advisor-grid">${Array.from({ length: 6 }).map(() => `<div class="skeleton" style="height:150px"></div>`).join("")}</div>
    </div>`;
  }
  return `
    <div class="card">
      <div class="filter-bar">
        <div class="field wide">
          <label for="scholarQuery">姓名 / 机构 / 关键词</label>
          <input id="scholarQuery" class="input" type="text" value="${escapeHtml(state.scholarQuery)}" placeholder="例如：Tsinghua、红外、detection" autocomplete="off">
        </div>
        <div class="field">
          <label for="advisorProvince">地区</label>
          <select id="advisorProvince" class="select" data-change="advisor-province">
            ${regionSelectHtml(rows)}
          </select>
        </div>
      </div>
      <div class="search-meta">
        <span id="advisorMeta">${advisorMetaText()}</span>
        <span class="advisor-tools">
          <span>全部收录学者</span>
          ${advisorLayoutToggleHtml()}
        </span>
      </div>
      <div class="${advisorGridClass()}" id="advisorList">${advisorListHtml()}</div>
      <div class="load-more" id="advisorMore">${advisorMoreHtml()}</div>
    </div>`;
}

function matchesRegion(a) {
  if (!state.advisorProvince) return true;
  const region = regionOf(a);
  if (state.advisorProvince === "__unknown") return region === REGION_PENDING;
  return region === state.advisorProvince;
}

function scholarRows() {
  if (state.advisorMode === "direction") {
    let rows = (state.directionData?.advisors || []).map(mergedScholar);
    return state.advisorProvince ? rows.filter(matchesRegion) : rows;
  }
  if (state.advisorMode === "institution") {
    if (!state.advisorInstitution) return [];
    let rows = institutionData().rowsByKey.get(state.advisorInstitution) || [];
    if (state.advisorProvince) rows = rows.filter(matchesRegion);
    return rows;
  }
  const q = state.scholarQuery.trim().toLowerCase();
  let rows = (state.scholars || []).map(mergedScholar);
  if (state.advisorProvince) rows = rows.filter(matchesRegion);
  if (q) {
    rows = rows.filter((a) => [a.name, a.institution, a.institutionZh, a.category, ...(a.fields || []), ...(a.keywords || [])]
      .filter(Boolean).join(" ").toLowerCase().includes(q));
  }
  return rows;
}

function displayName(name) {
  return String(name || "").replace(/\s+\d{4}$/, "");
}

function normalizeOrcid(value) {
  const m = String(value || "").match(/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])/i);
  return m ? m[1].toUpperCase() : "";
}

function applyOrcid(a) {
  const id = normalizeOrcid(a?.orcid);
  const rec = id ? state.orcid?.records?.[id] : null;
  if (!rec) return a;
  if (!rec.nameMatch) return { ...a, orcidNameMismatch: true, orcidMismatchReason: rec.nameMatchReason || "" };
  const out = { ...a, orcidVerified: true, orcidCheckedAt: rec.checkedAt || "" };
  if (rec.employmentScope) out.employmentScope = rec.employmentScope;
  if (rec.institution) {
    out.institution = rec.institution;
    out.institutionZh = rec.institutionZh || "";
    out.institutionUrl = rec.institutionUrl || "";
    out.institutionNames = [rec.institution];
    out.matchedInstitutions = 1;
  }
  if (rec.province) out.province = rec.province;
  if (rec.country) out.country = rec.country;
  if (rec.ror) out.ror = rec.ror;
  if (rec.homepage) {
    out.homepage = rec.homepage;
    out.homepageSource = rec.homepageSource || "ORCID";
  }
  if (rec.activity) out.activity = rec.activity;
  if (rec.works?.length) out.recentWorks = rec.works;
  if (rec.worksTotal) out.worksTotal = rec.worksTotal;
  if (rec.employmentVerified !== undefined) out.employmentVerified = rec.employmentVerified;
  if (rec.papersIndexed !== undefined) out.papersIndexed = rec.papersIndexed;
  return out;
}

function mergedScholar(a) {
  if (!a) return a;
  if (a.homepage !== undefined && a.institutionUrl !== undefined) return applyOrcid(a);
  const pool = state.scholars || [];
  const matches = pool.filter((s) => s.name === a.name);
  if (!matches.length) return applyOrcid(a);
  const inst = String(a.institution || "").toLowerCase();
  const zh = String(a.institutionZh || "");
  const best = matches.find((s) => (inst && String(s.institution || "").toLowerCase() === inst) || (zh && s.institutionZh === zh)) || matches[0];
  return applyOrcid({ ...a, ...best, reasons: a.reasons || best.reasons });
}

function advisorGridClass() {
  return `advisor-grid ${state.advisorLayout === "list" ? "is-list" : "is-grid"}`;
}

function advisorLayoutToggleHtml() {
  return `<span class="layout-toggle" role="group" aria-label="切换展示方式">
    <button type="button" class="${state.advisorLayout === "grid" ? "active" : ""}" data-action="advisor-layout" data-layout="grid" aria-pressed="${state.advisorLayout === "grid"}">${icon("grid")} 平铺</button>
    <button type="button" class="${state.advisorLayout === "list" ? "active" : ""}" data-action="advisor-layout" data-layout="list" aria-pressed="${state.advisorLayout === "list"}">${icon("list")} 列表</button>
  </span>`;
}

function advisorMoreHtml() {
  if (state.advisorMode !== "search" && !(state.advisorMode === "institution" && state.advisorInstitution)) return "";
  const total = scholarRows().length;
  const shown = Math.min(state.advisorLimit, total);
  if (shown >= total) return total ? `<span class="small muted">已显示全部 ${fmtInt(total)} 位</span>` : "";
  return `<button class="btn" data-action="advisor-more">${icon("chevron")} 再加载 ${fmtInt(Math.min(60, total - shown))} 位（已显示 ${fmtInt(shown)} / ${fmtInt(total)}）</button>`;
}

function advisorListHtml() {
  const rows = scholarRows();
  if (!rows.length) {
    if ((state.advisorMode === "direction" || state.advisorMode === "institution") && state.advisorProvince) {
      const region = escapeHtml(state.advisorProvince === "__unknown" ? REGION_PENDING : state.advisorProvince);
      return `<div style="grid-column:1/-1">${emptyBlock(
        "search",
        `当前范围中没有「${region}」的学者`,
        state.advisorMode === "institution" ? "这所学校在该地区没有记录。可以清除地区筛选，查看该校全部学者。" : "这里只展示该方向的推荐学者。可以清除地区筛选，到全部学者中继续浏览。",
        `<div class="detail-actions"><button type="button" class="btn" data-action="advisor-region-all">查看全部地区学者</button></div>`
      )}</div>`;
    }
    return `<div style="grid-column:1/-1">${emptyBlock("search", "没有匹配的学者", "换一个方向、地区或关键词；也可以切到另一套检索方式。")}</div>`;
  }
  const limit = state.advisorMode === "direction" ? rows.length : state.advisorLimit;
  return rows.slice(0, limit).map((a) => `
    <article class="advisor-card" data-action="advisor-detail" data-name="${escapeHtml(a.name)}" tabindex="0" role="button" aria-label="查看 ${escapeHtml(displayName(a.name))} 的详细信息">
      <div class="advisor-top">
        <div class="avatar">${escapeHtml(initials(displayName(a.name)))}</div>
        <div class="grow">
          <div class="advisor-name">${escapeHtml(displayName(a.name))}${a.orcidVerified ? `<span class="verified-mark" title="${a.employmentVerified ? "ORCID 已核验" : "ORCID 已匹配"}">${icon("check")}</span>` : ""}</div>
          <div class="advisor-inst">${escapeHtml(a.institutionZh || a.institution || "机构未标注")}${a.institutionZh && a.institution && a.institutionZh !== a.institution ? ` · ${escapeHtml(a.institution)}` : ""}</div>
        </div>
        <span class="badge ${regionOf(a) === REGION_PENDING ? "badge-pending" : ""}">${escapeHtml(regionOf(a))}</span>
      </div>
      <div class="advisor-stats"><span>引用 <b>${fmtInt(a.cited)}</b></span><span>论文 <b>${fmtInt(a.works)}</b></span>${a.category ? `<span>${escapeHtml(a.category)}</span>` : ""}</div>
      <div class="advisor-kw">${[a.fields?.join(" / "), a.keywords?.slice(0, 2).join(" / ")].filter(Boolean).map(escapeHtml).join(" · ") || "方向关键词未标注"}</div>
      ${a.reasons?.length ? `<div class="chip-row">${a.reasons.slice(0, 3).map((r) => `<span class="badge badge-accent">${escapeHtml(r)}</span>`).join("")}</div>` : ""}
      <div class="advisor-foot">
        <span class="small muted">${a.orcidVerified
          ? `${a.employmentVerified ? "ORCID 已核验" : a.employmentScope === "unknown" ? "ORCID 姓名匹配 · 未公开任职" : "ORCID 已匹配"}${a.activity?.recent5 ? ` · 近五年 ${a.activity.recent5} 篇` : ""}`
          : a.orcidNameMismatch
            ? (a.orcidMismatchReason === "overseasEmployment" ? "ORCID 任职不一致" : a.orcidMismatchReason === "weakMatch" ? "ORCID 匹配不足" : "ORCID 姓名不一致")
            : a.homepage ? "个人主页已收录" : a.institutionUrl ? "院校官网已收录" : a.orcid ? "ORCID 可核验" : "仅索引记录"}</span>
        <span class="advisor-open">查看详情 ${icon("arrow")}</span>
      </div>
    </article>`).join("");
}

function advisorMetaText() {
  const rows = scholarRows();
  const region = state.advisorProvince === "__unknown" ? REGION_PENDING : state.advisorProvince;
  if (state.advisorMode === "direction") {
    return `匹配 ${rows.length} 位${region ? ` · ${region}` : ""}`;
  }
  if (state.advisorMode === "institution" && state.advisorInstitution) {
    const shown = Math.min(state.advisorLimit, rows.length);
    return `该院校 ${fmtInt(rows.length)} 位${region ? ` · ${region}` : ""}${rows.length > shown ? ` · 已显示 ${fmtInt(shown)}` : ""}`;
  }
  const shown = Math.min(state.advisorLimit, rows.length);
  return `找到 ${fmtInt(rows.length)} 位${region ? ` · ${region}` : ""}${rows.length > shown ? ` · 已显示 ${fmtInt(shown)}` : ""}`;
}

function renderAdvisorListOnly() {
  const list = $("#advisorList");
  const meta = $("#advisorMeta");
  const more = $("#advisorMore");
  if (!list) return;
  list.className = advisorGridClass();
  list.innerHTML = advisorListHtml();
  if (meta) meta.textContent = advisorMetaText();
  if (more) more.innerHTML = advisorMoreHtml();
  $$(".layout-toggle button").forEach((btn) => {
    const active = btn.dataset.layout === state.advisorLayout;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
}

async function ensureScholars() {
  state.scholarsLoading = true;
  state.scholarsError = "";
  try {
    state.scholars = await loadAdvisors();
  } catch (err) {
    state.scholarsError = String(err?.message || err);
  }
  state.scholarsLoading = false;
  if (state.route === "advisors") render();
}

async function ensureOrcid() {
  state.orcidLoading = true;
  state.orcidError = "";
  try {
    state.orcid = await loadOrcid();
  } catch (err) {
    state.orcidError = String(err?.message || err);
  }
  state.orcidLoading = false;
  if (state.route === "advisors" || state.route === "papers") render();
}

async function ensurePapers() {
  state.papersLoading = true;
  state.papersError = "";
  try {
    state.papers = await loadPapers();
  } catch (err) {
    state.papersError = String(err?.message || err);
  }
  state.papersLoading = false;
  if (state.route === "papers") render();
}

// ---------- 论文库 ----------
function paperRows() {
  const list = state.papers?.papers || [];
  const q = state.paperQuery.trim().toLowerCase();
  return list.filter((p) => {
    if (state.paperYear && String(p.year) !== state.paperYear) return false;
    if (state.paperType && p.type !== state.paperType) return false;
    if (state.paperCategory && p.category !== state.paperCategory) return false;
    if (state.paperScholar && p.scholar !== state.paperScholar) return false;
    if (!q) return true;
    return [p.title, p.venue, p.scholar, p.doi].filter(Boolean).join(" ").toLowerCase().includes(q);
  });
}

function paperMetaText() {
  const rows = paperRows();
  const shown = Math.min(state.paperLimit, rows.length);
  return `匹配 ${fmtInt(rows.length)} 篇${rows.length > shown ? ` · 已显示 ${fmtInt(shown)}` : ""}`;
}

function paperMoreHtml() {
  const total = paperRows().length;
  const shown = Math.min(state.paperLimit, total);
  if (shown >= total) return total ? `<span class="small muted">已显示全部 ${fmtInt(total)} 篇</span>` : "";
  return `<button class="btn" data-action="paper-more">${icon("chevron")} 再加载 ${fmtInt(Math.min(40, total - shown))} 篇（已显示 ${fmtInt(shown)} / ${fmtInt(total)}）</button>`;
}

function paperRowsHtml() {
  const rows = paperRows();
  if (!rows.length) {
    return emptyBlock("book", "没有匹配的论文", "换一个关键词、年份、类型或领域；也可以清除学者筛选。", state.paperScholar
      ? `<button class="btn" data-action="paper-clear-scholar">清除学者筛选</button>` : "");
  }
  const shown = Math.min(state.paperLimit, rows.length);
  return rows.slice(0, shown).map((p) => {
    const url = safeUrl(p.url) || (p.doi ? `https://doi.org/${p.doi}` : "");
    const type = PAPER_TYPE_LABEL[p.type] || p.type || "";
    return `
    <article class="paper-row">
      <div class="paper-main">
        ${url
          ? `<a class="paper-title" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(cleanText(p.title))}${icon("external")}</a>`
          : `<span class="paper-title">${escapeHtml(cleanText(p.title))}</span>`}
        <div class="paper-meta">
          <span class="paper-year">${p.year || "年份未标注"}</span>
          ${p.venue ? `<span>${escapeHtml(p.venue)}</span>` : ""}
          ${type ? `<span class="paper-type">${escapeHtml(type)}</span>` : ""}
          ${p.doi ? `<span class="paper-doi">DOI ${escapeHtml(p.doi)}</span>` : ""}
        </div>
      </div>
      <div class="paper-side">
        <button type="button" class="paper-scholar" data-action="paper-scholar" data-name="${escapeHtml(p.scholar || "")}" title="只看这位学者的论文">${escapeHtml(displayName(p.scholar))}</button>
        <small>${escapeHtml(p.institution || p.category || "")}</small>
      </div>
    </article>`;
  }).join("");
}

function papersView() {
  if (!state.papers && !state.papersLoading && !state.papersError) ensurePapers();
  if (!state.orcid && !state.orcidLoading && !state.orcidError) ensureOrcid();
  if (state.papersError) {
    return `${pageHead("论文库", "按 ORCID 公开记录整理的推荐学者论文，可按题目、学者、年份、类型与领域筛选，并跳转 DOI。")}
      <div class="card"><div class="notice warn">${icon("alert")}<div>论文数据读取失败：${escapeHtml(state.papersError)}</div></div><div class="detail-actions"><button class="btn" data-action="retry-papers">重试</button></div></div>`;
  }
  if (!state.papers) {
    return `${pageHead("论文库", "按 ORCID 公开记录整理的推荐学者论文。")}
      <div class="card"><div class="skeleton" style="height:120px;margin-bottom:var(--sp-3)"></div>${Array.from({ length: 6 }).map(() => `<div class="skeleton" style="height:64px;margin-bottom:10px"></div>`).join("")}</div>`;
  }
  const all = state.papers.papers || [];
  const scholarCount = new Set(all.map((p) => p.orcid || p.scholar)).size;
  const categories = Object.keys(state.papers.categories || {}).sort((a, b) => (state.papers.categories[b] || 0) - (state.papers.categories[a] || 0));
  const years = [...new Set(all.map((p) => p.year).filter(Boolean))].sort((a, b) => b - a);
  const types = [...new Set(all.map((p) => p.type).filter(Boolean))];
  const rows = paperRows();
  return `
    ${pageHead(
      "论文库",
      "把推荐学者的 ORCID 公开作品整理成可筛选列表：题目、年份、来源、类型与 DOI 都可核对；点学者名可查看他的任职机构与活跃度。",
      `<a class="btn" href="#/advisors">${icon("users")} 去导师目录</a>`
    )}
    <div class="paper-hero">
      <div class="paper-stats">
        <div><b>${fmtInt(all.length)}</b><span>篇论文</span></div>
        <div><b>${fmtInt(scholarCount)}</b><span>位学者</span></div>
        <div><b>${fmtInt(categories.length)}</b><span>个领域</span></div>
        <div><b>${escapeHtml(state.papers.generatedAt || "2026-11-18")}</b><span>ORCID 快照日期</span></div>
      </div>
      <p>来源：ORCID 公开作品记录，按 DOI / 标题去重，只保留期刊、会议、书章、预印本等学术类型；晚于快照年份（2027 及以后）的提前登记记录不计入。不是全站论文检索，也不含全文。</p>
    </div>
    <div class="card paper-panel">
      <div class="filter-bar">
        <div class="field wide">
          <label for="paperQuery">题目 / 学者 / 期刊 / DOI</label>
          <input id="paperQuery" class="input" type="text" value="${escapeHtml(state.paperQuery)}" placeholder="例如：remote sensing、Zisserman、10.1109" autocomplete="off">
        </div>
        <div class="field">
          <label for="paperYear">年份</label>
          <select id="paperYear" class="select" data-change="paper-year">
            <option value="">全部年份</option>
            ${years.map((y) => `<option value="${y}" ${state.paperYear === String(y) ? "selected" : ""}>${y}</option>`).join("")}
          </select>
        </div>
        <div class="field">
          <label for="paperType">类型</label>
          <select id="paperType" class="select" data-change="paper-type">
            <option value="">全部类型</option>
            ${types.map((t) => `<option value="${escapeHtml(t)}" ${state.paperType === t ? "selected" : ""}>${escapeHtml(PAPER_TYPE_LABEL[t] || t)}</option>`).join("")}
          </select>
        </div>
        <div class="field">
          <label for="paperCategory">领域</label>
          <select id="paperCategory" class="select" data-change="paper-category">
            <option value="">全部领域</option>
            ${categories.map((c) => `<option value="${escapeHtml(c)}" ${state.paperCategory === c ? "selected" : ""}>${escapeHtml(c)}（${fmtInt(state.papers.categories[c])}）</option>`).join("")}
          </select>
        </div>
      </div>
      ${state.paperScholar ? `<div class="active-filter">学者筛选：<b>${escapeHtml(displayName(state.paperScholar))}</b><button type="button" data-action="paper-clear-scholar" aria-label="清除学者筛选">${icon("x")} 清除</button></div>` : ""}
      <div class="search-meta">
        <span id="paperMeta">${paperMetaText()}</span>
        <span class="small muted">点击题目跳转 DOI / ORCID 记录</span>
      </div>
      <div class="paper-list" id="paperList">${paperRowsHtml()}</div>
      <div class="load-more" id="paperMore">${paperMoreHtml()}</div>
    </div>
    <div class="notice quiet" style="margin-top:var(--sp-3)">
      ${icon("info")}
      <div><strong>覆盖范围：</strong>论文库只覆盖 ${fmtInt(state.index.stats.directions || 501)} 个方向的推荐学者中能与 ORCID 公开记录匹配的 ${fmtInt(scholarCount)} 位，不是全部 ${fmtInt(state.scholars?.length || state.index.stats.scholars_exported || state.index.stats.scholars_indexed)} 位学者的完整发表清单。年份、来源与类型取自 ORCID，可能不完整；引用与 h-index 类指标不在此处给出。</div>
    </div>`;
}

function renderPapersOnly() {
  const list = $("#paperList");
  const meta = $("#paperMeta");
  const more = $("#paperMore");
  if (!list) return;
  list.innerHTML = paperRowsHtml();
  if (meta) meta.textContent = paperMetaText();
  if (more) more.innerHTML = paperMoreHtml();
}

async function ensureVenues() {
  state.venuesLoading = true;
  state.venuesError = "";
  try {
    state.venues = await loadVenues();
  } catch (err) {
    state.venuesError = String(err?.message || err);
  }
  state.venuesLoading = false;
  if (state.route === "venues") render();
}

// ---------- 期刊会议 ----------
function venuesView() {
  if (state.venueMode === "all" && !state.venues && !state.venuesLoading && !state.venuesError) ensureVenues();
  return `
    ${pageHead(
      "期刊会议",
      "在这里输入方向即可推荐 venue，也可按 CCF 等级、类型、国家、领域筛完整目录；支持平铺与列表两种视图。不写影响因子，不猜中科院分区。",
      `<a class="btn" href="#/workshop">${icon("spark")} 换方向</a>`
    )}
    <div class="tabs" style="margin-bottom:var(--sp-3)">
      <button class="tab ${state.venueMode === "rec" ? "active" : ""}" data-action="venue-mode" data-mode="rec">按方向推荐</button>
      <button class="tab ${state.venueMode === "all" ? "active" : ""}" data-action="venue-mode" data-mode="all">全部 ${fmtInt(state.index.stats.venues)} 个</button>
    </div>
    ${state.venueMode === "rec" ? venuesRecHtml() : venuesAllHtml()}
    <div class="notice quiet" style="margin-top:var(--sp-3)">
      ${icon("info")}
      <div><strong>CCF 分级：</strong>按《中国计算机学会推荐国际学术会议和期刊目录》2026 年第七版录入，只覆盖 A/B/C 三档；目录外留空。简介是项目自写的一句话，不是官方描述。方向推荐在 ${fmtInt(state.index.stats.venues)} 个 venue 与 ${fmtInt(state.index.stats.directions)} 个方向的关键词、类别之间匹配，不是投稿难度预测。</div>
    </div>`;
}

function venueGridClass() {
  return `venue-grid ${state.venueLayout === "list" ? "is-list" : ""}`;
}

function venueLayoutToggleHtml() {
  return `<span class="layout-toggle" role="group" aria-label="切换展示方式">
    <button type="button" class="${state.venueLayout === "grid" ? "active" : ""}" data-action="venue-layout" data-layout="grid" aria-pressed="${state.venueLayout === "grid"}">${icon("grid")} 平铺</button>
    <button type="button" class="${state.venueLayout === "list" ? "active" : ""}" data-action="venue-layout" data-layout="list" aria-pressed="${state.venueLayout === "list"}">${icon("list")} 列表</button>
  </span>`;
}

function venuesRecHtml() {
  const venues = state.directionData?.venues || [];
  const hasDirection = Boolean(state.direction);
  return `
    <div class="card">
      <div class="filter-bar">
        <div class="field wide suggest-wrap">
          <label for="venueDirectionInput">研究方向</label>
          <input id="venueDirectionInput" class="input" type="text" value="${escapeHtml(state.query)}" placeholder="例如：红外小目标检测、医学影像组学" autocomplete="off" aria-autocomplete="list" aria-controls="venueSuggestBox">
          <div class="suggest" id="venueSuggestBox" hidden></div>
        </div>
        <button class="btn btn-primary" data-action="venue-search-direction">${icon("search")} 推荐 venue</button>
      </div>
      <div class="search-meta">
        <span id="venueRecMeta">${hasDirection ? `${escapeHtml(state.direction.category)} · ${escapeHtml(state.direction.name)} · 推荐 ${fmtInt(venues.length)} 个` : "输入方向，按方向关键词与类目推荐"}</span>
        <span class="advisor-tools">
          <span class="badge badge-accent">方向匹配</span>
          ${venueLayoutToggleHtml()}
        </span>
      </div>
      ${hasDirection
        ? (venues.length
          ? `<div class="${venueGridClass()}" id="venueRecList">${venues.map((v) => venueCardHtml(v)).join("")}</div>`
          : emptyBlock("award", "该方向暂未匹配到 venue", `可以切到「全部 ${fmtInt(state.index.stats.venues)} 个」按 CCF 等级与领域筛选，或换一个更常见的方向说法。`, `<button class="btn" data-action="venue-mode" data-mode="all">${icon("award")} 看全部</button>`))
        : emptyBlock("search", "先输入一个研究方向", "例如「红外小目标检测」「医学影像组学」；系统只按方向名、术语、关键词与类目匹配，不预测投稿难度。")}
    </div>`;
}

function venuesAllHtml() {
  if (state.venuesError) {
    return `<div class="card"><div class="notice warn">${icon("alert")}<div>venue 数据读取失败：${escapeHtml(state.venuesError)}</div></div><div class="detail-actions"><button class="btn" data-action="retry-venues">重试</button></div></div>`;
  }
  if (!state.venues) {
    return `<div class="card"><div class="skeleton" style="height:42px;margin-bottom:var(--sp-3)"></div><div class="venue-grid">${Array.from({ length: 6 }).map(() => `<div class="skeleton" style="height:140px"></div>`).join("")}</div></div>`;
  }
  const fields = [...new Set(state.venues.map((v) => v.field).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh"));
  return `
    <div class="card">
      <div class="filter-bar">
        <div class="field wide"><label for="venueQuery">搜索名称 / 简介</label><input id="venueQuery" class="input" type="text" value="${escapeHtml(state.venueQuery)}" placeholder="例如：CVPR、NLP、多媒体" autocomplete="off"></div>
        <div class="field"><label for="venueCcf">CCF</label><select id="venueCcf" class="select" data-change="venue-ccf"><option value="">全部</option>${["A", "B", "C"].map((r) => `<option value="${r}" ${state.venueCcf === r ? "selected" : ""}>CCF ${r}</option>`).join("")}<option value="none" ${state.venueCcf === "none" ? "selected" : ""}>未收录</option></select></div>
        <div class="field"><label for="venueType">类型</label><select id="venueType" class="select" data-change="venue-type"><option value="">全部</option>${["会议", "期刊"].map((t) => `<option value="${t}" ${state.venueType === t ? "selected" : ""}>${t}</option>`).join("")}</select></div>
        <div class="field"><label for="venueField">领域</label><select id="venueField" class="select" data-change="venue-field"><option value="">全部</option>${fields.map((f) => `<option value="${escapeHtml(f)}" ${state.venueField === f ? "selected" : ""}>${escapeHtml(f)}</option>`).join("")}</select></div>
      </div>
      <div class="search-meta">
        <span id="venueMeta">${venueMetaText()}</span>
        <span class="advisor-tools"><span>CCF 2026 · 不含影响因子</span>${venueLayoutToggleHtml()}</span>
      </div>
      <div class="${venueGridClass()}" id="venueList">${venueListHtml()}</div>
    </div>`;
}

function filteredVenues() {
  let rows = state.venues || [];
  const q = state.venueQuery.trim().toLowerCase();
  if (state.venueCcf === "none") rows = rows.filter((v) => !v.ccf);
  else if (state.venueCcf) rows = rows.filter((v) => v.ccf === state.venueCcf);
  if (state.venueType) rows = rows.filter((v) => v.type === state.venueType);
  if (state.venueField) rows = rows.filter((v) => v.field === state.venueField);
  if (q) rows = rows.filter((v) => `${v.name} ${v.field} ${v.intro} ${v.country}`.toLowerCase().includes(q));
  return rows;
}

function venueListHtml() {
  const rows = filteredVenues();
  if (!rows.length) return `<div style="grid-column:1/-1">${emptyBlock("filter", "没有匹配的 venue", "放宽 CCF、类型或领域条件再试。")}</div>`;
  return rows.map((v) => venueCardHtml(v)).join("");
}

function venueMetaText() {
  const rows = filteredVenues();
  return `找到 ${fmtInt(rows.length)} 个 venue`;
}

function renderVenueListOnly() {
  const list = $("#venueList");
  const meta = $("#venueMeta");
  if (!list) return;
  list.className = venueGridClass();
  list.innerHTML = venueListHtml();
  if (meta) meta.textContent = venueMetaText();
  syncVenueLayoutButtons();
}

function syncVenueLayoutButtons() {
  $$(".layout-toggle button[data-action='venue-layout']").forEach((btn) => {
    const active = btn.dataset.layout === state.venueLayout;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
}

function venueCardHtml(v) {
  const href = safeUrl(v.url);
  return `
    <article class="venue-card" data-action="venue-detail" data-name="${escapeHtml(v.name)}" tabindex="0" role="button" aria-label="查看 ${escapeHtml(v.name)} 的详情">
      <div class="venue-top">
        ${ccfBadge(v.ccf)}
        <span class="venue-name">${escapeHtml(v.name)}</span>
        ${v.type ? `<span class="badge">${escapeHtml(v.type)}</span>` : ""}
        ${v.country ? `<span class="badge">${escapeHtml(v.country)}</span>` : ""}
      </div>
      <div class="venue-intro">${escapeHtml(v.intro || "暂无简介")}</div>
      <div class="venue-meta">${v.field ? `<span class="badge">${escapeHtml(v.field)}</span>` : ""}</div>
      <div class="advisor-foot">
        <span class="advisor-open">查看详情 ${icon("arrow")}</span>
        ${href ? `<a class="link-quiet venue-link" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" data-action="venue-site">${escapeHtml(v.linkLabel || "官网")} ${icon("external")}</a>` : ""}
      </div>
    </article>`;
}

function findVenue(name) {
  const pool = [...(state.directionData?.venues || []), ...(state.venues || [])];
  return pool.find((v) => v.name === name) || null;
}

function venueModalHtml() {
  const v = state.venueDetail;
  if (!v) return "";
  const href = safeUrl(v.url);
  let host = "";
  try { host = new URL(href).hostname.replace(/^www\./, ""); } catch {}
  const tier = v.ccf ? `CCF ${v.ccf} 类` : "目录外";
  const edition = v.ccfEdition || "2026";
  const tierLine = v.ccf
    ? `${v.name} 收录于 CCF ${edition} 推荐目录，等级为 ${v.ccf} 类。`
    : `${v.name} 未收录于 CCF ${edition} 推荐目录，等级留空，按「未收录」展示。`;
  const recVenues = state.venueMode === "rec" ? (state.directionData?.venues || []) : [];
  const directionHit = recVenues.some((x) => x.name === v.name);
  const directionName = directionHit ? (state.direction?.aliasOf || state.direction?.name || state.query) : "";
  return `
    <div class="advisor-modal venue-modal" role="dialog" aria-modal="true" aria-labelledby="venueModalTitle">
      <div class="advisor-modal-backdrop" data-action="venue-close"></div>
      <div class="advisor-modal-panel">
        <button type="button" class="advisor-modal-close" data-action="venue-close" aria-label="关闭">${icon("x")}</button>
        <div class="advisor-modal-head">
          <div class="venue-seal ${v.ccf ? `is-${escapeHtml(v.ccf)}` : "is-none"}">${escapeHtml(v.ccf || "—")}</div>
          <div>
            <div class="advisor-modal-kicker">VENUE PROFILE · CCF ${escapeHtml(edition)}</div>
            <h3 id="venueModalTitle">${escapeHtml(v.name)}</h3>
            <p>${escapeHtml(v.intro || "项目暂未为这个 venue 写一句话简介")}</p>
            <div class="chip-row">
              ${v.type ? `<span class="badge">${escapeHtml(v.type)}</span>` : ""}
              ${v.country ? `<span class="badge">${escapeHtml(v.country)}</span>` : ""}
              ${v.field ? `<span class="badge badge-accent">${escapeHtml(v.field)}</span>` : ""}
              <span class="badge">${escapeHtml(tier)}</span>
            </div>
          </div>
        </div>
        <div class="advisor-modal-stats venue-modal-stats">
          <div><b>${escapeHtml(v.ccf || "—")}</b><span>CCF ${escapeHtml(edition)} 等级</span></div>
          <div><b>${escapeHtml(v.type || "—")}</b><span>类型</span></div>
          <div><b>${escapeHtml(v.country || "未标注")}</b><span>国家 / 地区</span></div>
          <div><b>${escapeHtml(v.field || "未分类")}</b><span>领域</span></div>
        </div>
        <div class="advisor-modal-section">
          <span class="section-label">定位说明</span>
          <p>${escapeHtml(v.name)} 是${v.country ? ` ${escapeHtml(v.country)} 的` : ""}${escapeHtml(v.type || "刊物")}，属于「${escapeHtml(v.field || "未分类")}」领域。上方简介由塞莎特——题谱按目录字段整理，不是官方介绍。</p>
        </div>
        <div class="advisor-modal-section">
          <span class="section-label">CCF 等级意味着什么</span>
          <p>${escapeHtml(tierLine)}</p>
          <p class="small muted">CCF ${escapeHtml(edition)} 目录用 A / B / C 三档描述国际会议与期刊的相对位置：A 类为国际上极少数的顶级，B 类为国际上著名且非常重要，C 类为国际上重要并被国际学术界认可。等级是目录给出的结论，不代表投稿难度、录用概率，也不代表与本项目或某位导师的合作关系。</p>
        </div>
        <div class="advisor-modal-section">
          <span class="section-label">塞莎特如何推荐它</span>
          ${directionName ? `<p>当前方向「${escapeHtml(directionName)}」推荐了 ${escapeHtml(v.name)}，该方向共 ${fmtInt(recVenues.length)} 个 venue。</p>` : ""}
          <p>在「按方向推荐」中输入研究方向，塞莎特——题谱用方向库的关键词与类目，和 venue 的领域字段做匹配。推荐只说明关键词有交集，不代表该 venue 正在征稿、有专刊，或与某个课题组有合作。</p>
        </div>
        <div class="advisor-modal-section">
          <span class="section-label">数据来源与入口</span>
          <div class="link-grid">
            ${href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(v.linkLabel || "官方网站")}<small>${escapeHtml(host || "外部网站")}</small>${icon("external")}</a>` : ""}
            <button type="button" data-action="venue-papers" data-name="${escapeHtml(v.name)}">在论文库搜索<small>${escapeHtml(v.name)} 相关论文</small>${icon("arrow")}</button>
          </div>
          <p class="small muted" style="margin-top:var(--sp-2)">名称、类型、国家与 CCF 等级来自 CCF ${escapeHtml(edition)} 推荐目录；简介由项目自写。塞莎特——题谱不提供影响因子，也不推测中科院分区。${href ? "" : `该 venue 暂未收录官网地址，因此不提供外部跳转。`}</p>
        </div>
      </div>
    </div>`;
}

// ---------- 科研方法论 ----------
function methodSetup() {
  if (state.method) return state.method;
  const skills = state.index?.skills || [];
  const fallback = {
    skill: skills[0]?.id || "",
    stage: "topic",
    degree: "硕士",
    paperType: "期刊论文",
    prep: ["scope", "lit"],
    constraints: "",
  };
  try {
    const raw = JSON.parse(localStorage.getItem("xtzk.v1.methodSetup") || "null");
    if (raw && typeof raw === "object") {
      const merged = { ...fallback, ...raw };
      merged.skill = skills.some((s) => s.id === merged.skill) ? merged.skill : fallback.skill;
      merged.stage = METHOD_STAGES.some(([id]) => id === merged.stage) ? merged.stage : "topic";
      merged.degree = METHOD_DEGREES.includes(merged.degree) ? merged.degree : fallback.degree;
      merged.paperType = METHOD_PAPERS.includes(merged.paperType) ? merged.paperType : fallback.paperType;
      merged.prep = Array.isArray(merged.prep) ? merged.prep.filter((k) => METHOD_PREP.some(([id]) => id === k)) : [];
      merged.constraints = typeof merged.constraints === "string" ? merged.constraints.slice(0, 600) : "";
      state.method = merged;
      return merged;
    }
  } catch { /* use fallback */ }
  state.method = fallback;
  return fallback;
}

function saveMethodSetup() {
  try { localStorage.setItem("xtzk.v1.methodSetup", JSON.stringify(methodSetup())); } catch { /* ignore */ }
}

function methodReadiness() {
  const setup = methodSetup();
  const done = new Set(setup.prep);
  const missing = METHOD_PREP.filter(([id]) => !done.has(id));
  return { done: METHOD_PREP.length - missing.length, total: METHOD_PREP.length, missing };
}

function methodsView() {
  const skills = state.index.skills || [];
  if (!state.openSkill) state.openSkill = skills[0]?.id || "";
  const setup = methodSetup();
  const readiness = methodReadiness();
  const nextPrep = readiness.missing[0];
  const ideaTitle = state.selected?.title || activeIdea()?.title || "";
  const directionName = directionLabel();
  return `
    ${pageHead("科研方法论")}
    <section class="studio" id="methodStudio" aria-labelledby="studioTitle">
      <div class="studio-head">
        <div class="studio-intro">
          <span class="studio-eyebrow">PROMPT STUDIO · 本地拼装</span>
          <h2 id="studioTitle">按你的选题与准备，生成一条可执行的科研提示词</h2>
          <p>选定研究阶段、学历与目标产出，勾选已经完成的准备。塞莎特——题谱在浏览器内把方法步骤、阶段任务、质量门槛与输出格式拼成提示词；不上传、不调用模型，复制后交给任意大模型使用。</p>
        </div>
        <div class="studio-readiness ${readiness.done === readiness.total ? "is-ready" : ""}">
          <span>准备度</span>
          <b>${readiness.done}<em>/${readiness.total}</em></b>
          <small>${nextPrep ? METHOD_READINESS_HINT[nextPrep[0]] : "准备项已齐，可以把提示词用于真实执行。"}</small>
        </div>
      </div>
      <div class="studio-context">
        <div><span>方向</span><b>${escapeHtml(directionName)}</b></div>
        <div><span>候选</span><b class="${ideaTitle ? "" : "is-empty"}">${ideaTitle ? escapeHtml(ideaTitle) : "尚未选择候选，将只按方向生成"}</b></div>
      </div>
      <div class="studio-controls">
        <div class="field"><label for="msStage">研究阶段</label><select id="msStage" class="select" data-method="stage">${METHOD_STAGES.map(([id, label]) => `<option value="${id}" ${setup.stage === id ? "selected" : ""}>${label}</option>`).join("")}</select></div>
        <div class="field"><label for="msDegree">学历层次</label><select id="msDegree" class="select" data-method="degree">${METHOD_DEGREES.map((d) => `<option value="${d}" ${setup.degree === d ? "selected" : ""}>${d}</option>`).join("")}</select></div>
        <div class="field"><label for="msPaper">目标产出</label><select id="msPaper" class="select" data-method="paperType">${METHOD_PAPERS.map((p) => `<option value="${p}" ${setup.paperType === p ? "selected" : ""}>${p}</option>`).join("")}</select></div>
        <div class="field"><label for="msSkill">方法骨架</label><select id="msSkill" class="select" data-method="skill">${skills.map((s) => `<option value="${escapeHtml(s.id)}" ${setup.skill === s.id ? "selected" : ""}>${escapeHtml(s.name)}</option>`).join("")}</select></div>
      </div>
      <fieldset class="studio-prep">
        <legend>先完成的科研准备 <small>勾选已完成项；未勾选会写入提示词的「待补」，并限制结论强度</small></legend>
        <div class="prep-grid">
          ${METHOD_PREP.map(([id, label]) => `
            <label class="prep-item ${setup.prep.includes(id) ? "is-done" : ""}">
              <input type="checkbox" data-prep="${id}" ${setup.prep.includes(id) ? "checked" : ""}>
              <span>${escapeHtml(label)}</span>
            </label>`).join("")}
        </div>
      </fieldset>
      <div class="studio-extra">
        <label for="msConstraints">已有基础、约束或导师要求</label>
        <textarea id="msConstraints" class="textarea" rows="3" maxlength="600" placeholder="例如：只有一张 4090；数据需审批；导师要求可解释性；希望 6 个月内投会议。">${escapeHtml(setup.constraints)}</textarea>
      </div>
      <div class="studio-actions">
        <button type="button" class="btn btn-primary" data-action="method-refresh">${icon("spark")} 刷新提示词</button>
        <button type="button" class="btn" data-action="method-copy">${icon("copy")} 复制提示词</button>
        <span class="studio-meta" id="msMeta"></span>
      </div>
      <pre class="studio-preview" id="msPreview" aria-live="polite"></pre>
      <p class="studio-foot">${icon("lock")} 提示词只在本机拼装；复制后是否发送给外部模型由你决定。方法框架参考通用科研流程，不包含任何未核验的文献条目。</p>
    </section>

    <div class="pipeline">
      ${[
        ["1", "问题收敛", "把兴趣压成一句失败现场"],
        ["2", "近邻与查重", "证明你不是重复"],
        ["3", "机制与实验", "设计能杀死假设的实验"],
        ["4", "审稿人视角", "提前找出致命伤"],
      ].map(([n, name, desc]) => `<div class="pipe-step"><span class="ps-num">${n}</span><div class="ps-name">${name}</div><div class="ps-desc">${desc}</div></div>`).join("")}
    </div>
    <div class="method-list">
      ${skills.map((s, i) => skillHtml(s, i)).join("")}
    </div>
    <div class="notice quiet" style="margin-top:var(--sp-3)">
      ${icon("info")}
      <div>方法论内容来自桌面版 <strong>research_skills.py</strong> 的 7 套结构化 Skill，并参考通用的科研流程与写作规范；Web 版只展示与复制，不上传任何内容。</div>
    </div>`;
}

function skillHtml(skill, index) {
  const open = state.openSkill === skill.id;
  const active = methodSetup().skill === skill.id;
  return `
    <article class="method-card ${active ? "is-selected" : ""}">
      <button type="button" class="method-head" data-action="toggle-skill" data-id="${escapeHtml(skill.id)}" aria-expanded="${open}">
        <span class="method-num">${String(index + 1).padStart(2, "0")}</span>
        <span class="grow"><span class="method-name">${escapeHtml(skill.name)}</span><span class="method-when">${escapeHtml(skill.when || "")}</span></span>
        ${active ? `<span class="method-picked">当前方法</span>` : ""}
        <span class="small muted">${escapeHtml(skill.en || "")}</span>
        <span class="method-chev">${icon("chevron")}</span>
      </button>
      <div class="method-body" ${open ? "" : "hidden"}>
        <div class="method-goal"><strong>目标：</strong>${escapeHtml(skill.goal || "")}</div>
        <div class="method-cols">
          <div>
            <div class="section-label">${icon("route")} 步骤</div>
            <ol class="steps">${(skill.steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>
          </div>
          <div>
            <div class="out-box"><b>产出</b>${escapeHtml(skill.output || "")}</div>
            <div class="pit-box"><b>常见错误</b>${escapeHtml(skill.pitfall || "")}</div>
            <button type="button" class="btn btn-sm" style="margin-top:var(--sp-2)" data-action="copy-prompt" data-id="${escapeHtml(skill.id)}">${icon("copy")} 用当前设置生成该方法提示词</button>
          </div>
        </div>
      </div>
    </article>`;
}

function buildMethodPrompt(skillOverride = "") {
  const setup = methodSetup();
  const skills = state.index?.skills || [];
  const skill = skills.find((s) => s.id === (skillOverride || setup.skill)) || skills[0];
  const stage = METHOD_STAGES.find(([id]) => id === setup.stage) || METHOD_STAGES[0];
  const idea = state.selected?.title || activeIdea()?.title || "";
  const direction = state.query || state.direction?.name || "";
  const hours = activeIdea()?.plan?.hours || 8;
  const done = new Set(setup.prep);
  const prepDone = METHOD_PREP.filter(([id]) => done.has(id));
  const prepMissing = METHOD_PREP.filter(([id]) => !done.has(id));
  const lines = [
    "你是一位严格的科研导师，熟悉计算机科学与交叉学科的项目设计、实验与论文写作。请按下面的参数指导我，而不是给泛泛建议。",
    "",
    "【工作规则】",
    "1. 先用不超过 5 行复述你对我的方向、阶段与约束的理解；信息不足时先问我最多 3 个问题。",
    "2. 不编造论文、作者、DOI、数据集、指标数值或接收率。需要引用时给出可检索的题名 / 作者 / 年份，并标注「待核验」。",
    "3. 明确区分「事实」「推断」「建议」；不确定就说不确定，并说明如何验证。",
    "4. 每个建议都要落到可执行动作：产出物、耗时、完成标准。",
    "5. 不替我下结论；给出选项、依据与取舍，由我确认。",
    "",
    "【研究参数】",
    `- 领域方向：${direction || "尚未填写（请先问我）"}`,
    `- 当前候选：${idea || "尚未确定（先帮我收敛，不要假设已有方案）"}`,
    `- 当前阶段：${stage[1]} —— ${stage[2]}`,
    `- 学历层次：${setup.degree}`,
    `- 目标产出：${setup.paperType}`,
    `- 每周可投入：约 ${hours} 小时（如与实际情况不符，请先校准）`,
    `- 已有基础与限制：${setup.constraints || "未填写；请把「不知道」当作未知处理，不要补全"}`,
    "",
    "【科研准备状态】",
  ];
  if (prepDone.length) {
    lines.push("已完成：");
    prepDone.forEach(([, label]) => lines.push(`- [已完成] ${label}`));
  } else {
    lines.push("已完成：无（请先把我当作准备不足，优先安排补基础）。");
  }
  if (prepMissing.length) {
    lines.push("待补（在补齐前，相关结论只能作为假设，不得当作已验证事实）：");
    prepMissing.forEach(([id, label]) => lines.push(`- [待补] ${label}。${METHOD_READINESS_HINT[id]}`));
  }
  lines.push(
    "",
    `【本次方法：${skill?.name || "问题收敛"}】`,
    `目标：${skill?.goal || ""}`,
    "步骤：",
    ...(skill?.steps || []).map((step, i) => `${i + 1}. ${step}`),
    `期望产出：${skill?.output || ""}`,
    `必须避免：${skill?.pitfall || ""}`,
    "",
    `【本阶段任务：${stage[1]}】`,
    ...METHOD_STAGE_TASKS[stage[0]].map((task, i) => `${i + 1}. ${task}`),
    "",
    "【创新性检查】",
    "- 用 8 个维度说明差异：问题定义、场景、假设、机制、数据、训练方式、评测、系统实现。",
    "- 每个「新」必须对应一个「旧」：旧方法在什么条件下失效，我的改动为什么能修复，如何用实验证明。",
    "- 如果找不到真实差异，直接告诉我这只是组合或换术语。",
    "",
    "【质量门槛】",
    "- 问题写成「场景 + 失效点 + 可量化差距 + 可证伪假设」。",
    "- 每个方案至少有一个 baseline、一个主指标、一个对照或消融，以及失败判据。",
    "- 文献按「检索式 → 纳入/排除 → 技术分叉 → 代表工作表」组织，不写流水账。",
    "- 给出 3 个最可能被审稿人攻击的点，以及各自的补强实验。",
    "- 给出本周可启动的最小动作，控制在 2 小时内。",
    "",
    "【输出格式】",
    "1. 理解复述与缺失信息（≤5 行）",
    "2. 关键判断（3–5 条，标注「事实 / 推断 / 建议」与依据）",
    "3. 分步方案表：动作 / 产出 / 耗时 / 完成标准",
    "4. 风险、失败判据与止损条件",
    "5. 本周最小动作",
    "6. 需要我确认的选择（最多 3 个）",
    "",
    "最后再检查一次：哪些内容是未经核验的？请单独列出，不要混进结论。",
  );
  return lines.join("\n");
}

function updateStudioPreview() {
  const preview = $("#msPreview");
  if (!preview) return;
  const text = buildMethodPrompt();
  preview.textContent = text;
  const meta = $("#msMeta");
  if (meta) {
    const readiness = methodReadiness();
    meta.textContent = `${text.length} 字 · 准备 ${readiness.done}/${readiness.total}${readiness.missing.length ? " · 含待补项" : " · 准备项齐全"}`;
  }
}

function refreshStudioChrome() {
  const setup = methodSetup();
  const stageSelect = $("#msStage");
  if (stageSelect) stageSelect.value = setup.stage;
  const skillSelect = $("#msSkill");
  if (skillSelect) skillSelect.value = setup.skill;
  const readiness = methodReadiness();
  const box = $(".studio-readiness");
  if (box) {
    box.classList.toggle("is-ready", readiness.done === readiness.total);
    const b = box.querySelector("b");
    if (b) b.innerHTML = `${readiness.done}<em>/${readiness.total}</em>`;
    const small = box.querySelector("small");
    if (small) small.textContent = readiness.missing[0] ? METHOD_READINESS_HINT[readiness.missing[0][0]] : "准备项已齐，可以把提示词用于真实执行。";
  }
  $$(".prep-item").forEach((label) => {
    const input = label.querySelector("input[data-prep]");
    label.classList.toggle("is-done", Boolean(input?.checked));
  });
  $$(".method-card").forEach((card) => {
    const button = card.querySelector(".method-head");
    card.classList.toggle("is-selected", button?.dataset.id === setup.skill);
  });
  updateStudioPreview();
}

// ---------- 研究计划 ----------
function planView() {
  if (!state.saved.length) {
    return `
      ${pageHead("研究计划", "把候选存进来，按截止日期倒推阶段；所有内容只保存在本机浏览器。")}
      <div class="card plan-empty">
        ${emptyBlock("calendar", "还没有存入的选题", "先去选题工坊生成候选，点「存入研究计划」，这里会给出阶段、待办与倒计时。", `<button class="btn btn-primary" data-action="go-workshop">${icon("spark")} 去选题工坊</button>`)}
      </div>`;
  }
  const idea = activeIdea();
  if (!idea) return "";
  if (!state.activeIdeaId) state.activeIdeaId = idea.id;
  const plan = ensurePlan(idea);
  const left = state.saved.map((x) => {
    const stats = ideaTodoStats(x);
    const remain = daysLeft(x.plan?.deadline);
    return `
    <button type="button" class="saved-item ${x.id === idea.id ? "active" : ""}" data-action="select-saved" data-id="${escapeHtml(x.id)}">
      <div class="si-title clamp-2">${escapeHtml(x.title)}</div>
      <div class="si-meta"><span>${escapeHtml(x.direction || "")}</span><span>${escapeHtml(x.plan?.stage || PLAN_STAGES[0])}</span></div>
      <div class="si-progress" aria-hidden="true"><i style="width:${stats.pct}%"></i></div>
      <div class="si-foot"><span>${stats.done}/${stats.total} 待办</span><span>${remain === null ? "未设截止" : remain < 0 ? "已过期" : `还剩 ${remain} 天`}</span></div>
    </button>`;
  }).join("");
  const leftCount = daysLeft(plan.deadline);
  return `
    ${pageHead("研究计划")}
    <div class="plan-toolbar">
      <div class="plan-toolbar-copy"><b>已加入 ${fmtInt(state.saved.length)} 个选题</b><span>返回候选页会保留本次方向、筛选与候选列表，可以接着加入下一条。</span></div>
      <button class="btn" data-action="go-workshop">${icon("arrow-left")} 返回候选继续添加</button>
    </div>
    ${planOverviewHtml(idea)}
    <div class="plan-layout">
      <div class="card" style="padding:var(--sp-3)">
        <div class="card-head"><div class="card-title">已存选题</div><span class="badge">${state.saved.length}</span></div>
        <div class="saved-list">${left}</div>
        <div class="notice quiet" style="margin-top:var(--sp-3)">${icon("lock")}<div>本机 localStorage 保存，清理浏览器数据会丢失。</div></div>
      </div>
      <div class="plan-main">
        <div class="card">
          <div class="card-head">
            <div>
              <div class="small muted">${escapeHtml(idea.direction || "")}</div>
              <h2 class="card-title" style="margin-top:2px">${escapeHtml(idea.title)}</h2>
            </div>
            <button class="btn btn-danger btn-sm" data-action="delete-idea">${icon("trash")} 删除</button>
          </div>
          <div class="plan-summary">
            <div class="ps-item"><b>${leftCount === null ? "—" : leftCount < 0 ? "已过期" : leftCount}</b><span>${leftCount === null ? "未设置截止" : leftCount < 0 ? "截止日期已过" : "天后截止"}</span></div>
            <div class="ps-item"><b>${escapeHtml(plan.stage || PLAN_STAGES[0])}</b><span>当前阶段</span></div>
            <div class="ps-item"><b>${fmtInt(plan.hours || 8)}</b><span>小时 / 周</span></div>
            <div class="ps-item"><b>${idea.diagnosis ? `${idea.diagnosis.count.passed}/9` : "—"}</b><span>结构体检</span></div>
          </div>
          <div class="plan-form" style="margin-top:var(--sp-3)">
            <div class="field"><label for="planDeadline">截止日期</label><input id="planDeadline" class="input" type="date" value="${escapeHtml(plan.deadline || addDaysISO(56))}" data-plan="deadline"></div>
            <div class="field"><label for="planStage">当前阶段</label><select id="planStage" class="select" data-plan="stage">${PLAN_STAGES.map((s) => `<option value="${s}" ${plan.stage === s ? "selected" : ""}>${s}</option>`).join("")}</select></div>
            <div class="field"><label for="planHours">每周投入（小时）</label><input id="planHours" class="input" type="number" min="1" max="80" step="1" value="${fmtInt(plan.hours || 8)}" data-plan="hours"></div>
            <div class="field plan-note"><label for="planNote">备注 / 约束</label><textarea id="planNote" class="textarea" style="min-height:88px" data-plan="note" placeholder="例如：只有一张 4090，数据要等实验室审批。">${escapeHtml(plan.note || "")}</textarea></div>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><div class="card-title">倒推阶段</div><div class="card-sub">按截止日期平均切分，仅作规划参考</div></div>
          ${timelineHtml(idea)}
        </div>
        <div class="card">
          <div class="card-head"><div class="card-title">待办</div><div class="card-sub">勾选状态同样保存在本机</div></div>
          ${todosHtml(idea)}
        </div>
        <div class="card">
          <div class="card-head"><div class="card-title">结构体检摘要</div>${idea.diagnosis ? `<span class="badge badge-warn">${idea.diagnosis.count.passed}/9</span>` : `<span class="badge">未体检</span>`}</div>
          ${idea.diagnosis ? `
            <div class="row"><span class="badge badge-accent">${escapeHtml(idea.diagnosis.stage)}</span><span class="small muted">${escapeHtml(idea.diagnosis.stageHint)}</span></div>
            ${idea.diagnosis.missing?.length ? `<div class="diag-missing" style="margin-top:var(--sp-2)">${idea.diagnosis.missing.slice(0, 3).map((m) => `<div class="missing-item"><div class="mi-head">${icon("plus")}${escapeHtml(m.label)}</div><div class="mi-fix">${escapeHtml(m.fix)}</div></div>`).join("")}</div>` : `<p class="small muted" style="margin-top:var(--sp-2)">九项结构已齐，接下来做真实实验并记录失败。</p>`}
          ` : `<p class="small muted">还没有体检。回选题工坊，在「结构体检」里补全描述后再存一次。</p>`}
          <div class="detail-actions">
            <button class="btn" data-action="go-workshop">${icon("target")} 回选题工坊体检</button>
            <button class="btn btn-quiet" data-action="copy-saved-desc">${icon("copy")} 复制问题陈述</button>
          </div>
        </div>
        <p class="small muted">计划是辅助，不是承诺。截止日期与阶段由你自己定，系统只负责把剩余天数与待办摆出来。</p>
      </div>
    </div>`;
}

function ensurePlan(idea) {
  if (!idea.plan) idea.plan = { deadline: addDaysISO(56), stage: PLAN_STAGES[0], hours: 8, note: "", todos: {} };
  return idea.plan;
}

function planDateRange(start, end) {
  const day = (d) => `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
  return `${day(start)} – ${day(end)}`;
}

function todoRows(idea) {
  const fixed = [
    ["f0", "把问题陈述压成一句话：场景 + 失效点 + 量化差距"],
    ["f1", "找 3 篇最近邻工作，写下与它们的差别"],
    ["f2", "跑最小实验，并如实记录失败与异常"],
    ["f3", "按 9 项结构体检补齐缺项"],
  ];
  const missing = (idea.diagnosis?.missing || []).slice(0, 3).map((m, i) => [`m${i}`, `补：${m.label} —— ${m.fix}`]);
  return [...fixed, ...missing];
}

function ideaTodoStats(idea) {
  const plan = ensurePlan(idea);
  const rows = todoRows(idea);
  const done = rows.filter(([key]) => plan.todos?.[key]).length;
  return { done, total: rows.length, pct: rows.length ? Math.round((done / rows.length) * 100) : 0 };
}

function planNextAction(idea) {
  const plan = ensurePlan(idea);
  const next = todoRows(idea).find(([key]) => !plan.todos?.[key]);
  if (next) return next[1];
  if (idea.diagnosis?.missing?.length) return `结构仍有缺项：${idea.diagnosis.missing[0].label} —— ${idea.diagnosis.missing[0].fix}`;
  return "待办已清空：进入完整实验，补主实验、消融与失败分析。";
}

function planOverviewHtml(idea) {
  let done = 0;
  let total = 0;
  let nearest = null;
  state.saved.forEach((x) => {
    const stats = ideaTodoStats(x);
    done += stats.done;
    total += stats.total;
    const remain = daysLeft(x.plan?.deadline);
    if (remain !== null && (nearest === null || remain < nearest)) nearest = remain;
  });
  const pct = total ? Math.round((done / total) * 100) : 0;
  const stats = ideaTodoStats(idea);
  return `
    <section class="plan-overview">
      <div class="po-stats">
        <div class="po-stat"><b>${fmtInt(state.saved.length)}</b><span>已存选题</span></div>
        <div class="po-stat"><b>${done}<em>/${total}</em></b><span>待办完成</span></div>
        <div class="po-stat"><b>${nearest === null ? "—" : nearest < 0 ? "已过" : nearest}</b><span>${nearest === null ? "未设最近截止" : nearest < 0 ? "最近截止已过" : "天到最近截止"}</span></div>
        <div class="po-stat"><b>${pct}<em>%</em></b><span>整体待办进度</span></div>
      </div>
      <div class="po-track" aria-hidden="true"><i style="width:${pct}%"></i></div>
      <div class="po-next">
        <span class="po-next-icon">${icon("target")}</span>
        <div class="po-next-copy">
          <span>下一步 · ${escapeHtml(idea.title)}</span>
          <b>${escapeHtml(planNextAction(idea))}</b>
          <small>当前阶段「${escapeHtml(ensurePlan(idea).stage || PLAN_STAGES[0])}」 · 待办 ${stats.done}/${stats.total}</small>
        </div>
        <div class="po-next-actions">
          <button class="btn btn-sm btn-primary" data-action="go-methods">${icon("route")} 生成科研提示词</button>
          <button class="btn btn-sm btn-quiet" data-action="copy-saved-desc">${icon("copy")} 复制问题陈述</button>
        </div>
      </div>
    </section>`;
}

function timelineHtml(idea) {
  const plan = ensurePlan(idea);
  const rawEnd = new Date(`${plan.deadline || addDaysISO(56)}T23:59:59`);
  const created = new Date(idea.createdAt || Date.now());
  const now = Date.now();
  const start = new Date(Number.isNaN(created.getTime()) || created.getTime() > now ? now : created.getTime());
  const end = Number.isNaN(rawEnd.getTime())
    ? new Date(start.getTime() + 56 * 86400000)
    : (rawEnd.getTime() > start.getTime() ? rawEnd : new Date(start.getTime() + 86400000));
  const span = end.getTime() - start.getTime();
  const at = (f) => new Date(start.getTime() + span * f);
  const phases = [
    ["问题与证据", "一句话问题 + 3 篇近邻 + 失败现场", "先补齐最近邻与失败现场", 0, 0.25],
    ["最小实验", "一个场景、一个基线、一个指标，先看趋势", "跑通一个场景 + 一个 baseline", 0.25, 0.5],
    ["完整实验", "主实验 + 消融 + 失败分析", "补消融、泄漏检查与失败分析", 0.5, 0.75],
    ["写作与核查", "结构 9/9、图表、引用核查", "写正文、核对引用与图表", 0.75, 1],
  ];
  const elapsed = Math.min(1, Math.max(0, (now - start.getTime()) / span));
  const remain = Math.max(0, Math.ceil((end.getTime() - now) / 86400000));
  return `
    <div class="timeline-wrap">
      <div class="timeline-top">
        <div class="timeline-track" aria-hidden="true"><i style="width:${Math.round(elapsed * 100)}%"></i></div>
        <div class="timeline-meta"><span>时间进度 ${Math.round(elapsed * 100)}%</span><span>${end.getTime() < now ? "截止日期已过" : `剩余 ${remain} 天`}</span></div>
      </div>
      <div class="timeline">
        ${phases.map(([name, desc, action, a, b]) => {
          const from = at(a);
          const to = at(b);
          const status = now >= to.getTime() ? "done" : now >= from.getTime() ? "current" : "next";
          const statusLabel = status === "done" ? "已完成" : status === "current" ? "进行中" : "未开始";
          return `
          <div class="milestone ${status}">
            <div class="ms-when">${planDateRange(from, to)}</div>
            <div class="ms-title">${name}<span class="ms-status">${statusLabel}</span></div>
            <div class="ms-desc">${desc}</div>
            <div class="ms-action">${icon("arrow")}${action}</div>
          </div>`;
        }).join("")}
      </div>
    </div>`;
}

function todosHtml(idea) {
  const plan = ensurePlan(idea);
  return `<div class="todo-list">${todoRows(idea).map(([key, text]) => `
    <label class="todo ${plan.todos?.[key] ? "done" : ""}">
      <input type="checkbox" data-todo="${key}" ${plan.todos?.[key] ? "checked" : ""}>
      <span>${escapeHtml(text)}</span>
    </label>`).join("")}</div>`;
}

// ---------- 关于 ----------
function aboutView() {
  const stats = state.index.stats;
  // 2026-11-20：时间线原来写死成 2026-11-18。公开站数据实际是
  // 2026-11-18 导出的（orcid.json 核验、papers.json 快照），桌面端
  // 2026-11-20 才与它合并 —— 两个日期必须分开写，否则「数据更新」这句话
  // 会把一份 11-18 的快照说成 11-20 的。
  const SNAPSHOT = "2026-11-18";   // 本页 data/ 下 JSON 的导出日
  const MERGED = "2026-11-20";     // 桌面端并入公开站口径的日期
  return `
    ${pageHead(
      "关于与数据范围",
      "把“选题”从一句兴趣，拆到可以被第三方核查的问题、机制与实验。",
      `<a class="btn" href="#/workshop">${icon("spark")} 打开选题工坊</a>`
    )}
    <div class="about-grid">
      <div>
        <div class="card about-card">
          <h2>这是什么</h2>
          <p>塞莎特——题谱是一个面向高校师生的<strong>科研选题图谱与结构核查工作台</strong>。桌面版覆盖选题、素材、导师、venue、方法论与研究计划；本页是它的 Qoder 参赛 Web 版，打开即用，不需要安装 Python、配置路径或 API Key。</p>
          <p>它不替你写论文，也不假装评估“想法好坏”。它做的是把模糊方向拆成一组带理由的候选，再用 9 项结构清单检查：问题是否具体、机制是否可证伪、baseline/数据/指标/消融/资源/止损是否写清。候选数量随方向关键词的关联强度变化，而不是固定条数。</p>
        </div>
        <div class="card about-card">
          <h2>为什么做</h2>
          <p>常见的选题工具给你一个分数或一堆关键词。分数看起来客观，实际上很容易被“术语堆砌”骗过。这里刻意<strong>不打质量分</strong>：只列可核查的事实项，并把“本地没共现”与“学界没人做”分开说。</p>
          <p>另一个取舍是<strong>可解释</strong>：每条候选都能看到角度、理由、验证问题与最小实验；每个导师都有匹配理由与 ORCID；每个 venue 都标注 CCF 2026 等级，不写影响因子。</p>
        </div>
        <div class="card about-card">
          <h2>数据与局限</h2>
          <ul class="bullet-list">
            <li>方向库：<strong>${fmtInt(stats.categories)} 个类目、${fmtInt(stats.directions)} 个细分方向</strong>，来自桌面版的合并方向库；支持大类到小类的双层浏览。</li>
            <li>素材库：按方向汇总常用数据集、指标与基线，并给出官方数据页与相关方向；数据集计数与关系可在「素材库」逐项查看。</li>
            <li>导师：原始索引 <strong>${fmtInt(stats.scholars_indexed)} 条记录</strong>，Web 版按 ORCID 去重后全部可浏览；个人主页只使用 CSRankings 与 ORCID 公开链接，未收录时提供院校官网与 ORCID 核验，不用搜索页冒充主页。</li>
            <li>论文：把推荐学者的 ORCID 公开作品按 DOI / 标题去重后放进「论文库」，可按题目、学者、年份、类型与领域筛选；不是全站论文检索。</li>
            <li>ORCID 匹配：对目录内带 ORCID 的学者做公开记录离线快照，姓名匹配后展示 2021–2026 年发表与近期论文；目录内非方向推荐学者若公开任职记录仅含海外机构，则不自动合并，避免同名误配，其余记录区分「有中国任职」与「未公开任职」并标注匹配范围。方向推荐学者的 ORCID 额外核验任职机构与地区，再由 ROR 机构库解析官网与 ROR 标识。匹配与核验都不是在线实时查询，机构字段仍可能滞后。</li>
            <li>venue：<strong>${fmtInt(stats.venues)} 个</strong>，CCF 分级按 2026 年第七版目录，不含中科院分区与影响因子。</li>
            <li>本 Web 版<strong>不做</strong> 53.8 万篇 arXiv 向量的语义查重；桌面版才具备完整近邻核查。</li>
            <li>候选分数只由方向与切入角度计算，不代表文献新颖性，也不是评审结论。</li>
          </ul>
        </div>
        <div class="card about-card">
          <h2>Qoder 使用与原创性说明</h2>
          <p>桌面原型在迁入 Qoder 前已经存在。2026 年 11 月迁入 Qoder 工作区后，<strong>参赛 Web 版的数据导出管线、全部页面实现、浏览器验收与 Qoder Sites 部署均由 Qoder 完成</strong>。我们不把原有桌面代码声称为 Qoder 从零生成。</p>
          <div class="qoder-list">
            ${[
              ["route", "迁移与基线", "保留原项目不动，建立 Qoder 开发副本、运行环境说明与基线提交。"],
              ["filter", "数据导出", `用桌面引擎为 ${fmtInt(stats.directions)} 个方向预生成导师、venue、文献共现数据，并导出角度与方法论。`],
              ["spark", "Web 实现", "纯静态、自包含、无 API Key；复用桌面设计语言并实现 Nudge 变量契约。"],
              ["external", "验收与部署", "本地浏览器走通核心流程，再通过 Qoder Sites 发布公网链接。"],
            ].map(([ico, title, desc]) => `<div class="qoder-item"><span class="qi-icon">${icon(ico)}</span><div><b>${title}</b><span>${desc}</span></div></div>`).join("")}
          </div>
        </div>
        <div class="card about-card">
          <h2>隐私</h2>
          <p>本站没有账号、没有后端、没有统计脚本，不会把你的输入上传到任何服务器。已存选题、研究计划与勾选状态只写在本机浏览器的 localStorage 里；清理浏览器数据会丢失。</p>
        </div>
      </div>
      <div class="stack">
        <div class="card about-card">
          <div class="card-head"><div class="card-title">数据一览</div><span class="badge">${SNAPSHOT}</span></div>
          <div class="stat-grid">
            <div class="stat-tile"><b>${fmtInt(stats.directions)}</b><span>细分方向</span></div>
            <div class="stat-tile"><b>${fmtInt(state.scholars?.length || stats.scholars_exported || stats.scholars_indexed)}</b><span>可浏览学者</span></div>
            <div class="stat-tile"><b>${fmtInt(stats.venues)}</b><span>venue 目录</span></div>
          </div>
        </div>
        <div class="card about-card">
          <div class="card-head"><div class="card-title">数据来源</div></div>
          <ul class="bullet-list">
            <li>OpenAlex 学者、机构元数据与机构官网（CC0）。</li>
            <li>ORCID 公开记录：任职单位、公开作品与研究者链接（${SNAPSHOT} 快照）。</li>
            <li>ROR（Research Organization Registry）机构标识、官网与地区。</li>
            <li>CSRankings 与 ORCID 的公开个人主页链接。</li>
            <li>CCF 2026 推荐国际会议与期刊目录（第七版）；网络版 http://127.0.0.1:8765 的期刊会议页已同步这 ${fmtInt(stats.venues)} 条，并标出哪些入口是 DBLP 目录、哪些是官网。</li>
            <li>桌面版方向库、别名、数据集与 venue 规则。</li>
          </ul>
          <div class="detail-actions">
            ${safeExternal("https://openalex.org/", "OpenAlex")}
            ${safeExternal("https://orcid.org/", "ORCID")}
            ${safeExternal("https://ror.org/", "ROR")}
            ${safeExternal("https://www.ccf.org.cn/", "CCF")}
          </div>
        </div>
        <div class="card about-card">
          <div class="card-head"><div class="card-title">桌面版</div></div>
          <p>Python / Tkinter，零新增 pip 依赖，离线优先。包含 12 个页面、本地 PDF 语义检索、arXiv 最新论文、创新点库与个人画像。Web 版是参赛入口，桌面版是完整工作台。</p>
          <div class="chip-row" style="margin-top:var(--sp-2)">
            <span class="badge">离线优先</span><span class="badge">中文界面</span><span class="badge">无 API Key</span>
          </div>
        </div>
      </div>
    </div>
    <div class="about-foot">塞莎特——题谱 · Qoder 参赛 Web 版 · 公开站快照 ${SNAPSHOT} · 与桌面版合并 ${MERGED} · 打开即用，无账号</div>`;
}

// ---------- 交互 ----------
function startNamedDirection(name, source = "") {
  if (!name) return;
  const input = $("#directionInput");
  if (input) input.value = name;
  state.intakeMode = "search";
  generateDirection(name, false, source);
}

function findAdvisor(name) {
  const pool = [
    ...(state.directionData?.advisors || []),
    ...(state.scholars || []),
  ];
  const found = pool.find((a) => a.name === name) || null;
  return found ? mergedScholar(found) : null;
}

function renderTagsOnly() {
  const panel = $(".tags-panel");
  if (panel) panel.outerHTML = tagsPanelHtml();
}

function renderBrowseOnly() {
  const panel = $(".browse-panel");
  if (!panel) return;
  const input = $("#browseQuery");
  const hadFocus = document.activeElement === input;
  const caret = hadFocus ? input.selectionStart : null;
  panel.outerHTML = browsePanelHtml();
  if (hadFocus) {
    const next = $("#browseQuery");
    next?.focus();
    if (caret != null) {
      try { next.setSelectionRange(caret, caret); } catch {}
    }
  }
}

function onViewClick(event) {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  switch (action) {
    case "generate":
      generateDirection($("#directionInput")?.value || "");
      break;
    case "intake-mode":
      state.intakeMode = target.dataset.mode || "search";
      render();
      break;
    case "toggle-app": {
      const id = target.dataset.id || "";
      if (!id) break;
      state.selectedApps = state.selectedApps.includes(id)
        ? state.selectedApps.filter((x) => x !== id)
        : [...state.selectedApps, id];
      renderTagsOnly();
      break;
    }
    case "tag-task": {
      const task = target.dataset.task || "";
      state.tagTask = state.tagTask === task ? "" : task;
      renderTagsOnly();
      break;
    }
    case "clear-tags":
      state.selectedApps = [];
      state.tagTask = "";
      renderTagsOnly();
      break;
    case "tag-direction":
      startNamedDirection(target.dataset.name || "", "tags");
      break;
    case "discover-cat": {
      const cat = target.dataset.cat || "";
      if (!cat) break;
      state.inputValue = cat;
      state.query = cat;
      state.phase = "intake";
      state.intakeMode = "browse";
      state.browseCat = cat;
      state.browseQuery = "";
      render();
      toast(`已写入「${cat}」，并从该大类展开方向`);
      requestAnimationFrame(() => {
        const panel = $(".browse-sub");
        if (panel) window.scrollTo({ top: panel.getBoundingClientRect().top + window.scrollY - 96, behavior: "smooth" });
      });
      break;
    }
    case "browse-cat":
      state.browseCat = target.dataset.cat || "";
      renderBrowseOnly();
      break;
    case "browse-direction":
      startNamedDirection(target.dataset.name || "", "browse");
      break;
    case "browse-clear":
      state.browseCat = "";
      state.browseQuery = "";
      renderBrowseOnly();
      break;
    case "advisor-detail": {
      const advisor = findAdvisor(target.dataset.name || "");
      if (advisor) {
        state.advisorDetail = advisor;
        render();
      }
      break;
    }
    case "advisor-close":
      if (state.advisorDetail) {
        state.advisorDetail = null;
        render();
      }
      break;
    case "venue-detail": {
      const venue = findVenue(target.dataset.name || "");
      if (venue) {
        state.venueDetail = venue;
        render();
      }
      break;
    }
    case "venue-close":
      if (state.venueDetail) {
        state.venueDetail = null;
        render();
      }
      break;
    case "venue-papers":
      state.venueDetail = null;
      state.paperQuery = target.dataset.name || "";
      state.paperYear = "";
      state.paperType = "";
      state.paperCategory = "";
      state.paperScholar = "";
      navigate("papers");
      break;
    case "confirm-direction":
      confirmPendingDirection(target.dataset.mode || "match");
      break;
    case "choose-direction":
      choosePendingDirection(target.dataset.name || "");
      break;
    case "edit-direction":
      if (state.pending) {
        state.phase = "review";
        render();
        requestAnimationFrame(() => document.querySelector(".review-panel")?.scrollIntoView({ block: "start" }));
      }
      break;
    case "reset-direction":
      resetDirection();
      break;
    case "example":
    case "example-advisor":
      state.advisorMode = "direction";
      generateDirection(target.dataset.name || "");
      break;
    case "suggest":
      if ($("#directionInput")) $("#directionInput").value = target.dataset.name || "";
      generateDirection(target.dataset.name || "");
      break;
    case "advisor-suggest":
      if ($("#advisorDirectionInput")) $("#advisorDirectionInput").value = target.dataset.name || "";
      advisorSearchDirection();
      break;
    case "venue-suggest":
      if ($("#venueDirectionInput")) $("#venueDirectionInput").value = target.dataset.name || "";
      venueSearchDirection();
      break;
    case "filter":
      applyFilter(target.dataset.filter || "all");
      break;
    case "candidate":
      selectCandidate(target.dataset.title || "");
      break;
    case "tab":
      state.detailTab = target.dataset.tab || "card";
      renderDetailPanel();
      break;
    case "save-idea":
      saveSelected();
      break;
    case "quick-add": {
      const candidate = state.candidates.find((x) => x.title === target.dataset.title);
      toggleCandidate(candidate);
      break;
    }
    case "copy-idea":
      copySelected();
      break;
    case "diagnose":
      diagnoseSelected(false);
      break;
    case "load-sample":
      diagnoseSelected(true);
      break;
    case "clear-desc":
      state.desc = "";
      state.diagnosis = null;
      state.diagnosisStale = false;
      if (state.selected) state.drafts.set(state.selected.title, "");
      renderDetailPanel();
      break;
    case "go-advisors":
      state.advisorMode = "direction";
      navigate("advisors");
      break;
    case "go-venues":
      state.venueMode = "rec";
      navigate("venues");
      break;
    case "go-workshop":
      navigate("workshop");
      break;
    case "go-materials":
      navigate("materials");
      break;
    case "material-select":
      state.materialsSelected = target.dataset.name || "";
      render();
      break;
    case "material-cat":
      state.materialsCat = target.dataset.cat || "";
      state.materialsSelected = "";
      state.materialsLimit = 36;
      render();
      break;
    case "material-app":
      state.materialsApp = target.dataset.app || "";
      state.materialsSelected = "";
      state.materialsLimit = 36;
      render();
      break;
    case "material-clear":
      state.materialsQuery = "";
      state.materialsCat = "";
      state.materialsApp = "";
      state.materialsSelected = "";
      state.materialsLimit = 36;
      render();
      break;
    case "material-more":
      state.materialsLimit += 36;
      render();
      break;
    case "material-direction":
      startNamedDirection(target.dataset.name || "", "materials");
      break;
    case "retry-materials":
      state.materialsError = "";
      ensureMaterials();
      render();
      break;
    case "retry-papers":
      state.papersError = "";
      ensurePapers();
      break;
    case "paper-more":
      state.paperLimit += 40;
      renderPapersOnly();
      break;
    case "paper-scholar":
      state.paperScholar = target.dataset.name || "";
      state.paperLimit = 40;
      render();
      break;
    case "paper-clear-scholar":
      state.paperScholar = "";
      state.paperLimit = 40;
      render();
      break;
    case "advisor-papers":
      state.advisorDetail = null;
      state.paperScholar = target.dataset.name || "";
      state.paperQuery = "";
      state.paperYear = "";
      state.paperType = "";
      state.paperCategory = "";
      state.paperLimit = 40;
      navigate("papers");
      break;
    case "go-plan":
      navigate("plan");
      break;
    case "advisor-mode":
      state.advisorMode = target.dataset.mode || "direction";
      state.advisorProvince = "";
      state.advisorInstitution = "";
      state.institutionQuery = "";
      state.advisorLimit = 60;
      state.institutionLimit = 80;
      if (state.advisorMode !== "direction" && !state.scholars && !state.scholarsLoading && !state.scholarsError) ensureScholars();
      render();
      break;
    case "advisor-institution":
      state.advisorInstitution = target.dataset.key || "";
      state.advisorProvince = "";
      state.advisorLimit = 60;
      render();
      break;
    case "advisor-institution-back":
      state.advisorInstitution = "";
      state.advisorLimit = 60;
      render();
      break;
    case "institution-more":
      state.institutionLimit += 80;
      renderInstitutionOnly();
      break;
    case "institution-region-all":
      state.advisorProvince = "";
      state.institutionLimit = 80;
      render();
      break;
    case "advisor-region-all":
      state.advisorMode = "search";
      state.scholarQuery = "";
      state.advisorProvince = "";
      state.advisorInstitution = "";
      state.advisorLimit = 60;
      render();
      if (!state.scholars && !state.scholarsLoading && !state.scholarsError) ensureScholars();
      break;
    case "advisor-layout":
      state.advisorLayout = target.dataset.layout === "list" ? "list" : "grid";
      renderAdvisorListOnly();
      break;
    case "advisor-more":
      state.advisorLimit += 60;
      renderAdvisorListOnly();
      break;
    case "advisor-open-all":
      state.advisorMode = "search";
      state.scholarQuery = state.directionData?.name || state.query || "";
      state.advisorInstitution = "";
      state.advisorLimit = 60;
      render();
      if (!state.scholars && !state.scholarsLoading && !state.scholarsError) ensureScholars();
      break;
    case "venue-mode":
      state.venueMode = target.dataset.mode || "rec";
      render();
      if (state.venueMode === "all" && !state.venues && !state.venuesLoading && !state.venuesError) ensureVenues();
      break;
    case "venue-layout":
      state.venueLayout = target.dataset.layout === "list" ? "list" : "grid";
      if (state.venueMode === "rec") {
        const recList = $("#venueRecList");
        if (recList) { recList.className = venueGridClass(); syncVenueLayoutButtons(); }
        else render();
      } else {
        renderVenueListOnly();
      }
      break;
    case "venue-search-direction":
      venueSearchDirection();
      break;
    case "advisor-search-direction":
      advisorSearchDirection();
      break;
    case "retry-scholars":
      state.scholarsError = "";
      ensureScholars();
      break;
    case "retry-venues":
      state.venuesError = "";
      ensureVenues();
      break;
    case "toggle-skill":
      state.openSkill = state.openSkill === target.dataset.id ? "" : target.dataset.id;
      render();
      break;
    case "copy-prompt":
      copyPrompt(target.dataset.id || state.openSkill);
      break;
    case "method-refresh":
      refreshStudioChrome();
      toast("提示词已按当前设置刷新");
      break;
    case "method-copy":
      copyText(buildMethodPrompt()).then((ok) => toast(ok ? "科研提示词已复制" : "复制失败"));
      break;
    case "select-saved":
      state.activeIdeaId = target.dataset.id || "";
      render();
      break;
    case "delete-idea":
      deleteActiveIdea();
      break;
    case "copy-saved-desc":
      copySavedDesc();
      break;
    case "go-methods":
      navigate("methods");
      break;
    case "reload":
      window.location.reload();
      break;
    default:
      break;
  }
}

function onViewInput(event) {
  const target = event.target;
  if (target.id === "directionInput") {
    state.inputValue = target.value;
    const typed = cleanText(target.value);
    if (state.direction && typed && typed !== state.query) {
      showQueryHint(`输入已修改；下方仍是「${state.query}」的识别结果，点「识别方向」重新识别。`);
    } else {
      hideQueryHint();
    }
    updateSuggestions(target.value, true);
    return;
  }
  if (target.id === "advisorDirectionInput") {
    updateInputSuggestions(target, "advisorSuggestBox", "advisor-suggest");
    return;
  }
  if (target.id === "venueDirectionInput") {
    updateInputSuggestions(target, "venueSuggestBox", "venue-suggest");
    return;
  }
  if (target.id === "msConstraints") {
    methodSetup().constraints = target.value.slice(0, 600);
    saveMethodSetup();
    updateStudioPreview();
    return;
  }
  if (target.id === "ideaDesc") {
    state.desc = target.value;
    if (state.selected) state.drafts.set(state.selected.title, target.value);
    if (state.diagnosis && !state.diagnosisStale) {
      state.diagnosisStale = true;
      const stale = $("#diagStale");
      if (stale) stale.hidden = false;
    }
    return;
  }
  if (target.id === "scholarQuery") {
    state.scholarQuery = target.value;
    state.advisorLimit = 60;
    renderAdvisorListOnly();
    return;
  }
  if (target.id === "institutionQuery") {
    state.institutionQuery = target.value;
    state.institutionLimit = 80;
    renderInstitutionOnly();
    return;
  }
  if (target.id === "materialQuery") {
    state.materialsQuery = target.value;
    state.materialsLimit = 36;
    renderMaterialsOnly();
    return;
  }
  if (target.id === "paperQuery") {
    state.paperQuery = target.value;
    state.paperLimit = 40;
    renderPapersOnly();
    return;
  }
  if (target.id === "browseQuery") {
    state.browseQuery = target.value;
    renderBrowseOnly();
    return;
  }
  if (target.id === "venueQuery") {
    state.venueQuery = target.value;
    renderVenueListOnly();
  }
}

function onViewChange(event) {
  const target = event.target;
  if (target.matches("[data-method]")) {
    const setup = methodSetup();
    const field = target.dataset.method;
    if (field === "skill") {
      setup.skill = target.value;
      state.openSkill = target.value;
      saveMethodSetup();
      render();
      updateStudioPreview();
      return;
    }
    setup[field] = target.value;
    saveMethodSetup();
    refreshStudioChrome();
    return;
  }
  if (target.matches("[data-prep]")) {
    const setup = methodSetup();
    const key = target.dataset.prep;
    const set = new Set(setup.prep);
    if (target.checked) set.add(key); else set.delete(key);
    setup.prep = METHOD_PREP.map(([id]) => id).filter((id) => set.has(id));
    saveMethodSetup();
    refreshStudioChrome();
    return;
  }
  if (target.matches("[data-change='advisor-province']")) {
    state.advisorProvince = target.value;
    state.advisorLimit = 60;
    if (state.advisorMode === "institution" && !state.advisorInstitution) {
      state.institutionLimit = 80;
      render();
      return;
    }
    renderAdvisorListOnly();
    return;
  }
  if (target.matches("[data-change='venue-ccf']")) {
    state.venueCcf = target.value;
    renderVenueListOnly();
    return;
  }
  if (target.matches("[data-change='paper-year']")) {
    state.paperYear = target.value;
    state.paperLimit = 40;
    renderPapersOnly();
    return;
  }
  if (target.matches("[data-change='paper-type']")) {
    state.paperType = target.value;
    state.paperLimit = 40;
    renderPapersOnly();
    return;
  }
  if (target.matches("[data-change='paper-category']")) {
    state.paperCategory = target.value;
    state.paperLimit = 40;
    renderPapersOnly();
    return;
  }
  if (target.matches("[data-change='venue-type']")) {
    state.venueType = target.value;
    renderVenueListOnly();
    return;
  }
  if (target.matches("[data-change='venue-field']")) {
    state.venueField = target.value;
    renderVenueListOnly();
    return;
  }
  if (target.matches("[data-plan]")) {
    const idea = activeIdea();
    if (!idea) return;
    const plan = ensurePlan(idea);
    const field = target.dataset.plan;
    plan[field] = field === "hours" ? Math.max(1, Math.min(80, Number(target.value) || 8)) : target.value;
    saveIdeas(state.saved);
    if (field !== "note") render();
    else toast("备注已保存");
    return;
  }
  if (target.matches("[data-todo]")) {
    const idea = activeIdea();
    if (!idea) return;
    const plan = ensurePlan(idea);
    plan.todos = plan.todos || {};
    plan.todos[target.dataset.todo] = target.checked;
    saveIdeas(state.saved);
    target.closest(".todo")?.classList.toggle("done", target.checked);
  }
}

function onViewKeydown(event) {
  const target = event.target;
  if ((target.dataset?.action === "advisor-detail" || target.dataset?.action === "venue-detail") && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    target.click();
    return;
  }
  if (event.key === "Escape" && (state.advisorDetail || state.venueDetail)) {
    state.advisorDetail = null;
    state.venueDetail = null;
    render();
    return;
  }
  const suggestBox = target.closest?.(".suggest");
  if (suggestBox && event.key === "Escape") {
    event.preventDefault();
    hideSuggestions();
    const owner = { suggestBox: "directionInput", advisorSuggestBox: "advisorDirectionInput", venueSuggestBox: "venueDirectionInput" }[suggestBox.id];
    if (owner) document.getElementById(owner)?.focus();
    return;
  }
  if (suggestBox && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
    event.preventDefault();
    const items = suggestionButtons(suggestBox.id);
    if (!items.length) return;
    const current = Math.max(0, items.indexOf(target));
    const delta = event.key === "ArrowDown" ? 1 : -1;
    setActiveSuggestion(suggestBox.id, (current + delta + items.length) % items.length)?.focus();
    return;
  }
  if (target.id === "directionInput") {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      stepSuggestion("suggestBox", event.key === "ArrowDown" ? 1 : -1, () => updateSuggestions(target.value, true));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const active = activeSuggestion("suggestBox");
      if (active) active.click();
      else generateDirection(target.value);
    } else if (event.key === "Escape") {
      hideSuggestions();
    }
    return;
  }
  if (target.id === "advisorDirectionInput") {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      stepSuggestion("advisorSuggestBox", event.key === "ArrowDown" ? 1 : -1, () => updateInputSuggestions(target, "advisorSuggestBox", "advisor-suggest"));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const active = activeSuggestion("advisorSuggestBox");
      if (active) active.click();
      else advisorSearchDirection();
    } else if (event.key === "Escape") {
      hideSuggestions();
    }
    return;
  }
  if (target.id === "venueDirectionInput") {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      stepSuggestion("venueSuggestBox", event.key === "ArrowDown" ? 1 : -1, () => updateInputSuggestions(target, "venueSuggestBox", "venue-suggest"));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const active = activeSuggestion("venueSuggestBox");
      if (active) active.click();
      else venueSearchDirection();
    } else if (event.key === "Escape") {
      hideSuggestions();
    }
    return;
  }
  if ((target.id === "scholarQuery" || target.id === "venueQuery") && event.key === "Enter") {
    target.blur();
  }
}

async function generateDirection(raw, autoConfirm = false, source = "") {
  const query = cleanText(raw).slice(0, 80);
  if (!query) { toast("先输入一个研究方向"); return; }
  if (!isMeaningfulDirectionQuery(query)) {
    resetDirection(query);
    showQueryHint(`「${query}」不像一个研究方向：至少输入 2 个汉字，或一个完整术语（如 目标检测、SLAM）。`, "error");
    toast("输入太短或只有数字，无法识别方向");
    return;
  }
  hideSuggestions();
  hideQueryHint();
  const btn = $("#generateBtn");
  if (btn) { btn.disabled = true; btn.textContent = "正在识别…"; }

  const match = matchDirection(state.index, query, state.appsData);
  const activeApps = match.apps || [];
  const data = await loadDirectionData(match.entry || { id: "general", name: query });
  state.pending = {
    query,
    topic: query,
    entry: match.entry,
    confidence: match.confidence,
    best: match.best || [],
    data,
    apps: activeApps,
    source,
  };
  state.phase = "review";
  state.direction = null;
  state.directionData = null;
  state.candidates = [];
  state.selected = null;
  state.filter = "all";
  state.detailTab = "card";
  state.diagnosis = null;
  state.diagnosisStale = false;
  state.query = "";
  state.inputValue = query;
  render();
  toast(match.entry ? "已完成方向识别，请确认后生成候选" : "未命中方向库，请确认是否用全库兜底");
  if (!autoConfirm) {
    requestAnimationFrame(() => {
      const panel = $(".review-panel");
      if (panel) window.scrollTo({ top: panel.getBoundingClientRect().top + window.scrollY - 84, behavior: "smooth" });
    });
  }
  if (autoConfirm) await confirmPendingDirection(match.entry ? "match" : "fallback");
}

async function confirmPendingDirection(mode = "match") {
  const pending = state.pending;
  if (!pending) return;
  let entry = pending.entry;
  if (mode === "fallback" || !entry) {
    entry = { id: "", name: pending.query, category: "", terms: [], keywords: [] };
  }
  const query = pending.topic || entry.aliasOf || entry.name || pending.query;
  const data = entry.id === pending.entry?.id
    ? pending.data
    : await loadDirectionData(entry);
  state.matched = Boolean(entry.id);
  state.confidence = entry.id ? (entry.id === pending.entry?.id ? pending.confidence : "strong") : "none";
  state.direction = entry;
  state.query = query;
  state.inputValue = query;
  state.directionData = data;
  state.activeApps = appsForDirection(state.appsData, query);
  if (!state.activeApps.length && pending.apps?.length) state.activeApps = pending.apps;
  state.candidates = buildCandidates(state.index, query, {
    data,
    benchmarks: state.benchmarks,
    apps: state.activeApps,
    entry,
  });
  state.selected = state.candidates[0] || null;
  state.filter = "all";
  state.detailTab = "card";
  state.diagnosis = null;
  state.diagnosisStale = false;
  state.drafts = new Map();
  state.desc = state.selected ? scaffoldDescription(state.selected, query, data?.benchmark) : "";
  if (state.selected) state.drafts.set(state.selected.title, state.desc);
  if (entry.id) rememberDirection(entry);
  state.phase = "results";
  render();
  toast(entry.id ? `已生成 ${state.candidates.length} 条候选` : "已用全库数据生成候选");
  requestAnimationFrame(() => {
    const bar = $(".recognize-bar");
    if (bar) window.scrollTo({ top: bar.getBoundingClientRect().top + window.scrollY - 78, behavior: "smooth" });
  });
}

async function choosePendingDirection(name) {
  const pending = state.pending;
  if (!pending || !name) return;
  const match = matchDirection(state.index, name, state.appsData);
  if (!match.entry) return;
  const data = await loadDirectionData(match.entry);
  state.pending = {
    query: pending.query,
    topic: match.entry.aliasOf || match.entry.name,
    entry: match.entry,
    confidence: scoreConfidence(match.score),
    best: match.best || [],
    data,
    apps: appsForDirection(state.appsData, match.entry.aliasOf || match.entry.name),
    source: pending.source,
  };
  render();
  toast(`已改选：${match.entry.aliasOf || match.entry.name}`);
}

function resetDirection(keepValue = "") {
  state.phase = "intake";
  state.pending = null;
  state.query = "";
  state.inputValue = keepValue;
  state.direction = null;
  state.matched = false;
  state.confidence = "none";
  state.directionData = null;
  state.candidates = [];
  state.selected = null;
  state.filter = "all";
  state.detailTab = "card";
  state.diagnosis = null;
  state.diagnosisStale = false;
  state.desc = "";
  state.drafts = new Map();
  render();
  requestAnimationFrame(() => {
    const input = $("#directionInput");
    input?.focus();
    input?.select();
  });
}

function selectCandidate(title) {
  const c = state.candidates.find((x) => x.title === title);
  if (!c) return;
  if (state.selected) state.drafts.set(state.selected.title, state.desc);
  state.selected = c;
  state.detailTab = "card";
  state.desc = state.drafts.has(c.title) ? state.drafts.get(c.title) : scaffoldDescription(c, state.query, state.directionData?.benchmark);
  state.diagnosis = null;
  state.diagnosisStale = false;
  $$(".candidate").forEach((el) => {
    const on = el.dataset.title === c.title;
    el.classList.toggle("selected", on);
    el.setAttribute("aria-pressed", String(on));
  });
  renderDetailPanel();
  if (window.matchMedia("(max-width: 1180px)").matches) {
    $("#detailPanel")?.scrollIntoView({ block: "start", behavior: "smooth" });
  }
}

function renderDetailPanel() {
  const panel = $("#detailPanel");
  if (!panel) return;
  panel.innerHTML = detailHtml();
}

function applyFilter(filter) {
  state.filter = filter;
  const list = filteredCandidates();
  if (!list.some((c) => c.title === state.selected?.title)) {
    if (state.selected) state.drafts.set(state.selected.title, state.desc);
    const next = list[0] || null;
    state.selected = next;
    state.detailTab = "card";
    state.desc = next ? (state.drafts.get(next.title) || scaffoldDescription(next, state.query, state.directionData?.benchmark)) : "";
    state.diagnosis = null;
    state.diagnosisStale = false;
  }
  $$(".filter-row .chip").forEach((chip) => chip.classList.toggle("active", chip.dataset.filter === filter));
  const listEl = $("#candidateList");
  if (listEl) listEl.innerHTML = candidateListHtml(list);
  const countEl = $("#candidateCount");
  if (countEl) countEl.textContent = `${fmtInt(list.length)} / ${fmtInt(state.candidates.length)} 条`;
  renderDetailPanel();
}

function saveSelected() {
  const c = state.selected;
  if (!c) return;
  toggleCandidate(c);
}

function toggleCandidate(c) {
  if (!c) return;
  const id = ideaId(c);
  if (state.saved.some((x) => x.id === id)) {
    unsaveIdea(id);
    return;
  }
  saveCandidate(c);
}

function unsaveIdea(id) {
  const idea = state.saved.find((x) => x.id === id);
  if (!idea) return;
  state.saved = state.saved.filter((x) => x.id !== id);
  saveIdeas(state.saved);
  if (state.activeIdeaId === id) state.activeIdeaId = state.saved[0]?.id || null;
  refreshIdeaSurfaces();
  toast(`已取消加入 · 计划还剩 ${state.saved.length} 个`);
}

function refreshIdeaSurfaces() {
  updateSavedCount();
  const listEl = $("#candidateList");
  if (listEl) listEl.innerHTML = candidateListHtml(filteredCandidates());
  const inline = $("#savedInline");
  if (inline) inline.innerHTML = savedInlineHtml();
  if (state.selected) renderDetailPanel();
}

function saveCandidate(c) {
  if (!c) return;
  const id = ideaId(c);
  const existing = state.saved.find((x) => x.id === id);
  if (existing) {
    state.activeIdeaId = id;
    toast("已在计划中 · 可继续添加其他候选");
    refreshIdeaSurfaces();
    return;
  }
  const diag = state.diagnosis;
  state.saved.unshift({
    id,
    title: c.title,
    direction: directionLabel(),
    category: state.direction?.category || "",
    strategy: c.strategy,
    angle: c.angle,
    reason: c.reason,
    questions: c.questions,
    minExperiment: c.minExperiment,
    relevance: c.relevance,
    novelty: c.novelty,
    feasibility: c.feasibility,
    score: c.score,
    desc: state.desc,
    diagnosis: diag,
    createdAt: new Date().toISOString(),
    plan: { deadline: addDaysISO(56), stage: stageToPlan(diag), hours: 8, note: "", todos: {} },
  });
  saveIdeas(state.saved);
  state.activeIdeaId = id;
  refreshIdeaSurfaces();
  toast(`已加入计划 · 共 ${state.saved.length} 个，可继续添加`);
}

function diagnoseSelected(useSample) {
  const c = state.selected;
  if (!c) return;
  if (useSample) {
    state.desc = SAMPLE_DESCRIPTION;
    const area = $("#ideaDesc");
    if (area) area.value = SAMPLE_DESCRIPTION;
  } else {
    const area = $("#ideaDesc");
    if (area) state.desc = area.value;
  }
  state.drafts.set(c.title, state.desc);
  state.diagnosis = diagnose({ title: c.title, desc: state.desc });
  state.diagnosisStale = false;
  const existing = state.saved.find((x) => x.id === ideaId(c));
  if (existing) {
    existing.desc = state.desc;
    existing.diagnosis = state.diagnosis;
    saveIdeas(state.saved);
  }
  renderDetailPanel();
  toast(`体检完成：${state.diagnosis.count.passed}/9 项可核查`);
}

async function copySelected() {
  const c = state.selected;
  if (!c) return;
  const text = [
    `候选选题：${c.title}`,
    `方向：${directionLabel()}`,
    `角度：${c.strategy} / ${c.angle}`,
    `为什么值得做：${c.reason}`,
    `可证伪问题：${c.questions?.[0] || ""}`,
    `两周最小验证：${c.minExperiment}`,
  ].join("\n");
  const ok = await copyText(text);
  toast(ok ? "选题已复制" : "复制失败，请手动选择文本");
}

function copySavedDesc() {
  const idea = activeIdea();
  if (!idea) return;
  copyText(`选题：${idea.title}\n方向：${idea.direction || ""}\n\n${idea.desc || ""}`).then((ok) => toast(ok ? "问题陈述已复制" : "复制失败"));
}

function deleteActiveIdea() {
  const idea = activeIdea();
  if (!idea) return;
  if (!window.confirm(`确定删除「${idea.title}」吗？本机保存的计划也会一起删除。`)) return;
  state.saved = state.saved.filter((x) => x.id !== idea.id);
  saveIdeas(state.saved);
  updateSavedCount();
  state.activeIdeaId = state.saved[0]?.id || null;
  toast("已删除");
  render();
}

async function advisorSearchDirection() {
  const raw = $("#advisorDirectionInput")?.value || "";
  const query = cleanText(raw);
  if (!query) { toast("先输入一个方向"); return; }
  const match = matchDirection(state.index, query, state.appsData);
  if (!match.entry) { toast("方向库里没有匹配项，试试更常见的说法"); return; }
  state.direction = match.entry;
  state.matched = true;
  state.confidence = match.confidence;
  state.query = query;
  state.inputValue = query;
  state.directionData = await loadDirectionData(match.entry);
  state.activeApps = appsForDirection(state.appsData, state.directionData.name || query);
  state.candidates = buildCandidates(state.index, query, {
    data: state.directionData,
    benchmarks: state.benchmarks,
    apps: state.activeApps,
    entry: state.direction,
  });
  state.selected = state.candidates[0] || null;
  state.desc = state.selected ? scaffoldDescription(state.selected, query, state.directionData?.benchmark) : "";
  state.drafts = new Map();
  if (state.selected) state.drafts.set(state.selected.title, state.desc);
  state.advisorMode = "direction";
  state.advisorProvince = "";
  state.advisorInstitution = "";
  rememberDirection(match.entry);
  render();
}

async function venueSearchDirection() {
  const raw = $("#venueDirectionInput")?.value || "";
  const query = cleanText(raw).slice(0, 80);
  if (!query) { toast("先输入一个方向"); return; }
  if (!isMeaningfulDirectionQuery(query)) { toast("输入太短或只有数字，无法识别方向"); return; }
  const match = matchDirection(state.index, query, state.appsData);
  if (!match.entry) { toast("方向库里没有匹配项，试试更常见的说法"); return; }
  const btn = document.querySelector('[data-action="venue-search-direction"]');
  if (btn) { btn.disabled = true; btn.textContent = "正在匹配…"; }
  const pendingMeta = $("#venueRecMeta");
  if (pendingMeta) pendingMeta.textContent = `正在按「${query}」匹配方向…`;
  state.direction = match.entry;
  state.matched = true;
  state.confidence = match.confidence;
  state.query = query;
  state.inputValue = query;
  state.directionData = await loadDirectionData(match.entry);
  state.activeApps = appsForDirection(state.appsData, state.directionData.name || query);
  state.candidates = buildCandidates(state.index, query, {
    data: state.directionData,
    benchmarks: state.benchmarks,
    apps: state.activeApps,
    entry: state.direction,
  });
  state.selected = state.candidates[0] || null;
  state.desc = state.selected ? scaffoldDescription(state.selected, query, state.directionData?.benchmark) : "";
  state.drafts = new Map();
  if (state.selected) state.drafts.set(state.selected.title, state.desc);
  state.venueMode = "rec";
  rememberDirection(match.entry);
  render();
  toast(`已按「${state.direction.name}」推荐 venue`);
}

function suggestionHtml(query, action, headLabel = "匹配方向") {
  const rows = suggestDirections(state.index, query, 60, state.appsData);
  const typedQuery = cleanText(query);
  const head = rows.length
    ? `<div class="suggest-head"><span>${typedQuery ? headLabel : "示例方向"}</span><span>${rows.length} 个 · ↑↓ 选择 · Enter 确认</span></div>`
    : "";
  let html = head + rows.map(({ entry }) => `
    <button type="button" data-action="${action}" data-name="${escapeHtml(entry.name)}">
      <span>${escapeHtml(entry.name)}</span>
      <span class="s-cat">${escapeHtml(entry.category)}${entry.aliasOf ? " · 示例" : ""}</span>
    </button>`).join("");
  if (!rows.length && typedQuery) {
    html = `<button type="button" data-action="${action}" data-name="${escapeHtml(query)}"><span>直接生成「${escapeHtml(query)}」</span><span class="s-cat s-new">通用数据</span></button>`;
  }
  return html;
}

function fillSuggestBox(box, query, action, headLabel) {
  if (!box) return;
  const typed = cleanText(query);
  if (typed && !isMeaningfulDirectionQuery(typed)) { box.hidden = true; return; }
  const html = suggestionHtml(query, action, headLabel);
  if (!html) { box.hidden = true; return; }
  box.innerHTML = html;
  box.hidden = false;
}

function updateSuggestions(query, show) {
  const box = $("#suggestBox");
  if (!box) return;
  if (!show) { box.hidden = true; return; }
  fillSuggestBox(box, query, "suggest");
}

function updateInputSuggestions(input, boxId, action, headLabel = "匹配方向") {
  if (!input) return;
  fillSuggestBox(document.getElementById(boxId), input.value, action, headLabel);
}

function suggestionButtons(boxId) {
  const box = document.getElementById(boxId);
  if (!box || box.hidden) return [];
  return [...box.querySelectorAll("button")];
}

function setActiveSuggestion(boxId, index) {
  const items = suggestionButtons(boxId);
  if (!items.length) return null;
  items.forEach((item, i) => item.classList.toggle("is-active", i === index));
  const active = items[index] || null;
  active?.scrollIntoView({ block: "nearest" });
  return active;
}

function clearActiveSuggestions() {
  document.querySelectorAll(".suggest button.is-active").forEach((item) => item.classList.remove("is-active"));
}

function stepSuggestion(boxId, delta, ensureOpen) {
  let items = suggestionButtons(boxId);
  if (!items.length && ensureOpen) {
    ensureOpen();
    items = suggestionButtons(boxId);
  }
  if (!items.length) return null;
  const current = items.findIndex((item) => item.classList.contains("is-active"));
  const base = current >= 0 ? current : (delta > 0 ? -1 : 0);
  return setActiveSuggestion(boxId, (base + delta + items.length) % items.length);
}

function activeSuggestion(boxId) {
  return document.querySelector(`#${boxId} button.is-active`);
}

function hideSuggestions() {
  clearActiveSuggestions();
  document.querySelectorAll(".suggest").forEach((box) => { box.hidden = true; });
}

function showQueryHint(text, tone = "stale") {
  const hint = $("#queryHint");
  if (!hint) return;
  hint.textContent = text;
  hint.classList.toggle("is-error", tone === "error");
  hint.hidden = false;
}

function hideQueryHint() {
  const hint = $("#queryHint");
  if (hint) hint.hidden = true;
}

function copyPrompt(skillId) {
  const setup = methodSetup();
  if (skillId) {
    setup.skill = skillId;
    state.openSkill = skillId;
    saveMethodSetup();
  }
  if (state.route === "methods") {
    const select = $("#msSkill");
    if (select) select.value = setup.skill;
    refreshStudioChrome();
  }
  const skill = (state.index.skills || []).find((s) => s.id === setup.skill);
  copyText(buildMethodPrompt(setup.skill)).then((ok) => toast(ok ? `「${skill?.name || "科研"}」提示词已复制` : "复制失败"));
}

// ---------- 启动 ----------
if (currentRoute() === "intro") startIntro();
boot();
