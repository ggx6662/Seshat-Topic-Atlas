// 塞莎特——题谱 · 纯前端内核：数据加载、方向识别、候选生成、结构体检
const DATA_ROOT = "data/";

const cache = new Map();

export async function loadJSON(path) {
  if (cache.has(path)) return cache.get(path);
  const res = await fetch(DATA_ROOT + path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`读取 ${path} 失败（HTTP ${res.status}）`);
  const data = await res.json();
  cache.set(path, data);
  return data;
}

export async function loadIndex() {
  return loadJSON("index.json");
}

export async function loadDirectionData(entry) {
  const id = entry?.dataId || entry?.id || "general";
  try {
    const data = await loadJSON(`directions/${id}.json`);
    return { ...data, requestedName: entry?.name || data.name, mappedName: entry?.aliasOf || "" };
  } catch (err) {
    const general = await loadJSON("directions/general.json");
    return { ...general, requestedName: entry?.name || "通用", mappedName: "", loadError: String(err.message || err) };
  }
}

export async function loadAdvisors() {
  return loadJSON("advisors.json");
}

export async function loadOrcid() {
  return loadJSON("orcid.json");
}

export async function loadPapers() {
  return loadJSON("papers.json");
}

export async function loadMaterials() {
  return loadJSON("materials.json");
}

export async function loadVenues() {
  return loadJSON("venues.json");
}

export async function loadApplications() {
  return loadJSON("applications.json");
}

export async function loadBenchmarks() {
  return loadJSON("benchmarks.json");
}

export async function loadRegions() {
  return loadJSON("regions.json");
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

export function fmtInt(n) {
  const num = Number(n || 0);
  return new Intl.NumberFormat("zh-CN").format(Number.isFinite(num) ? num : 0);
}

export function fmtDate(iso) {
  if (!iso) return "未设置";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

export function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export function addDaysISO(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function daysLeft(iso) {
  if (!iso) return null;
  const target = new Date(`${iso}T23:59:59`).getTime();
  if (Number.isNaN(target)) return null;
  return Math.ceil((target - Date.now()) / 86400000);
}

export function cleanText(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

export function isMeaningfulDirectionQuery(value) {
  const q = cleanText(value);
  if ([...q.replace(/\s/g, "")].length < 2) return false;
  if (!/[\u4e00-\u9fffA-Za-z]/.test(q)) return false;
  if (/^[\d\s.,;:!?+\-*/%()]+$/.test(q)) return false;
  return true;
}

function normalize(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[\s\-_·—–,，。；;：:、！!？?/\\()（）\[\]【】"'“”‘’]/g, "");
}

function allApplications(appsData) {
  return (appsData?.groups || []).flatMap((group) =>
    (group.apps || []).map((app) => ({ ...app, group: group.name })));
}

export function detectApplications(appsData, text) {
  const q = normalize(text);
  if (!q) return [];
  const out = [];
  for (const app of allApplications(appsData)) {
    const hit = [app.name, ...(app.terms || [])]
      .map(normalize)
      .filter((t) => t.length >= 2)
      .some((t) => q.includes(t) || (t.length >= 4 && t.includes(q)));
    if (hit) out.push(app);
  }
  return out;
}

export function appsByIds(appsData, ids = []) {
  const set = new Set(ids);
  return allApplications(appsData).filter((app) => set.has(app.id));
}

export function appsForDirection(appsData, directionName) {
  return allApplications(appsData).filter((app) => (app.directions || []).includes(directionName));
}

export const TAG_TASKS = [
  { key: "detect", label: "检测与识别", terms: ["检测", "识别", "分割", "跟踪", "定位", "分类"] },
  { key: "generate", label: "生成与合成", terms: ["生成", "合成", "重建", "渲染", "扩散", "增强"] },
  { key: "predict", label: "预测与决策", terms: ["预测", "决策", "推荐", "规划", "控制", "推理", "优化"] },
  { key: "system", label: "系统与部署", terms: ["系统", "推理服务", "部署", "加速", "边缘", "芯片", "编译"] },
  { key: "evaluate", label: "评测与解释", terms: ["评测", "基准", "可解释", "鲁棒", "安全", "对齐", "公平"] },
];

export function recommendDirections(index, appsData, selectedIds = [], taskKey = "", limit = 12) {
  const selected = appsByIds(appsData, selectedIds);
  if (!selected.length && !taskKey) return [];
  const task = TAG_TASKS.find((t) => t.key === taskKey);
  const rows = [];
  for (const entry of index.directions || []) {
    if (entry.aliasOf) continue;
    let score = 0;
    const reasons = [];
    for (const app of selected) {
      if ((app.directions || []).includes(entry.name)) {
        score += 42;
        reasons.push(app.name);
      } else if ((app.categories || []).includes(entry.category)) {
        score += 7;
      }
    }
    if (entry.category === "应用领域" && selected.length) score += 6;
    if (task) {
      const hay = [entry.name, ...(entry.keywords || []), ...(entry.terms || [])].join(" ");
      const hit = task.terms.find((term) => hay.includes(term));
      if (hit) { score += 18; reasons.push(task.label); }
    }
    if (score > 0) rows.push({ entry, score, reasons: [...new Set(reasons)] });
  }
  rows.sort((a, b) => b.score - a.score || a.entry.name.length - b.entry.name.length);
  return rows.slice(0, limit);
}

export function taskLabel(key) {
  return TAG_TASKS.find((t) => t.key === key)?.label || "";
}

export function benchmarkForDirection(data, benchmarks, directionName = "") {
  if (data?.benchmark?.datasets?.length) return data.benchmark;
  const explicit = benchmarks?.directions?.[directionName] || {};
  const cat = data?.category || "";
  return {
    datasets: [],
    metrics: explicit.metrics || benchmarks?.metrics?.[cat] || [],
    baselines: explicit.baselines || benchmarks?.baselines?.[cat] || [],
    note: explicit.note || "该方向暂无整理好的公开基准，请按任务检索官方数据集与评测协议。",
  };
}

function termScore(term, query) {
  const t = normalize(term);
  const q = normalize(query);
  if (!t || !q) return 0;
  if (t === q) return 110;
  if (t.length >= 2 && q.includes(t)) return 62 + Math.min(18, t.length * 2);
  if (q.length >= 2 && t.includes(q)) return 52 + Math.min(18, q.length * 2);
  return 0;
}

export function scoreDirection(entry, query) {
  const q = normalize(query);
  if (!q) return 0;
  const name = normalize(entry.name);
  let score = 0;
  if (name === q) score = 130;
  else if (name.length >= 2 && q.includes(name)) score = 100;
  else if (q.length >= 2 && name.includes(q)) score = 92;
  for (const term of entry.terms || []) score = Math.max(score, termScore(term, query));
  for (const kw of entry.keywords || []) score = Math.max(score, termScore(kw, query) * 0.82);
  if (entry.category && normalize(entry.category) && q.includes(normalize(entry.category))) score += 4;
  if (entry.aliasOf && score >= 92) score += 3;
  return score;
}

function appBoost(entry, apps = []) {
  if (!apps.length) return 0;
  let boost = 0;
  for (const app of apps) {
    if ((entry.apps || []).includes(app.id)) boost += 18;
    else if ((app.directions || []).includes(entry.name)) boost += 14;
    else if ((app.categories || []).includes(entry.category)) boost += 3;
  }
  return Math.min(36, boost);
}

export function matchDirection(index, query, appsData = null) {
  const direction = cleanText(query).slice(0, 80);
  if (!direction || !isMeaningfulDirectionQuery(direction)) return { entry: null, score: 0, confidence: "none", best: [], apps: [] };
  const detected = detectApplications(appsData, direction);
  const scored = index.directions
    .map((entry) => ({ entry, score: scoreDirection(entry, direction) + appBoost(entry, detected) }))
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      if (!!b.entry.aliasOf !== !!a.entry.aliasOf) return b.entry.aliasOf ? 1 : -1;
      return a.entry.name.length - b.entry.name.length;
    });
  const top = scored[0];
  const best = scored.filter((row) => row.score > 0).slice(0, 8);
  if (!top || top.score < 42) return { entry: null, score: top?.score || 0, confidence: "none", best, apps: detected };
  const confidence = top.score >= 120 ? "exact" : top.score >= 85 ? "strong" : "near";
  return { entry: top.entry, score: top.score, confidence, best, apps: detected };
}

export function suggestDirections(index, query, limit = 60, appsData = null) {
  const q = cleanText(query);
  if (q && !isMeaningfulDirectionQuery(q)) return [];
  const detected = detectApplications(appsData, q);
  const scored = index.directions
    .map((entry) => ({ entry, score: scoreDirection(entry, q) + appBoost(entry, detected) }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || (a.entry.aliasOf ? -1 : 1));
  if (!q) {
    const examples = index.directions.filter((d) => d.aliasOf).slice(0, 5);
    return examples.map((entry) => ({ entry, score: 1 }));
  }
  return scored.slice(0, limit);
}

export function confidenceLabel(confidence) {
  return { exact: "精确命中", strong: "方向库命中", near: "近似匹配", none: "未命中" }[confidence] || "未命中";
}

// 候选数量由方向关键词与场景标签的关联强度决定，不再固定为 18 条。
const GROUP_ANGLE_BOOST = {
  "医疗与生命健康": ["分割", "小样本", "多模态", "可解释"],
  "交通、制造与物流": ["三维", "跟踪", "鲁棒", "轻量化"],
  "地球、环境与空间": ["多尺度", "跨域泛化", "多模态", "自监督"],
  "商业、社会与教育": ["语言", "可解释", "评测", "多模态"],
  "安全、科学与基础设施": ["鲁棒", "评测", "复现", "范式"],
};

function angleContextScore(key, label, hay) {
  const tokens = `${key} ${label}`.toLowerCase().split(/[\s/、,，]+/).filter((token) => token.length >= 2);
  let hits = 0;
  for (const token of tokens) if (hay.includes(token)) hits += 1;
  return hits;
}

export function buildCandidates(index, direction, options = {}) {
  const groups = ["稳健邻接", "跨领域迁移", "高风险高回报"];
  const angles = [];
  for (const group of groups) {
    for (const item of index.angles?.[group] || []) angles.push([group, ...item]);
  }
  const effective = direction || "该方向";
  const entry = options.entry || {};
  const benchmark = benchmarkForDirection(options.data, options.benchmarks, direction);
  const apps = options.apps || [];
  const appNames = apps.map((a) => a.name).filter(Boolean);
  const datasets = (benchmark.datasets || []).slice(0, 4);
  const metrics = (benchmark.metrics || []).slice(0, 4);
  const baselines = (benchmark.baselines || []).slice(0, 4);
  const hay = [
    effective,
    entry.category,
    ...(entry.keywords || []),
    ...(entry.terms || []),
    ...appNames,
  ].filter(Boolean).join(" ").toLowerCase();
  const appBoostAngles = new Set(apps.flatMap((app) => GROUP_ANGLE_BOOST[app.group] || []));

  const scored = [];
  const seen = new Set();
  for (let i = 0; i < angles.length; i += 1) {
    const [strategy, key, label, reason, question, minExperiment, novelty, feasibility] = angles[i];
    const title = candidateTitle(effective, strategy, label);
    if (seen.has(title)) continue;
    seen.add(title);
    const contextHits = angleContextScore(key, label, hay);
    const appHit = appBoostAngles.has(key) || appBoostAngles.has(label);
    let relevance = 62 + Math.min(20, contextHits * 8) + (appHit ? 7 : 0);
    relevance -= strategy === "高风险高回报" ? 5 : Math.max(0, Math.round(i * 0.5));
    relevance = Math.max(42, Math.min(95, relevance));
    const selection = relevance * 0.55 + novelty * 0.25 + feasibility * 0.2 + (appHit ? 4 : 0);
    const score = Math.round(0.45 * relevance + 0.3 * novelty + 0.25 * feasibility);
    scored.push({
      title,
      strategy,
      angle: label,
      angleKey: key,
      reason: cleanText(reason),
      questions: [cleanText(question)],
      minExperiment: cleanText(minExperiment),
      relevance,
      novelty,
      feasibility,
      score,
      contextHits,
      appHit,
      selection,
      datasets,
      metrics,
      baselines,
      applicationNames: appNames,
      benchmarkNote: benchmark.note || "",
    });
  }

  const contextTotal = scored.reduce((sum, item) => sum + item.contextHits, 0);
  const appHits = scored.filter((item) => item.appHit).length;
  const strength = contextTotal >= 6 ? "较强" : contextTotal >= 2 ? "中等" : "较弱";
  const target = Math.max(12, Math.min(scored.length, 12 + Math.min(7, contextTotal) + Math.min(3, appHits > 0 ? Math.ceil(apps.length / 2) : 0)));
  const byScore = [...scored].sort((a, b) => b.selection - a.selection || b.score - a.score);
  const picked = [];
  const add = (item) => {
    if (item && picked.length < target && !picked.some((row) => row.title === item.title)) picked.push(item);
  };
  for (const group of groups) {
    for (const item of byScore.filter((row) => row.strategy === group).slice(0, 3)) add(item);
  }
  for (const item of byScore) add(item);
  picked.sort((a, b) => b.score - a.score);
  return picked.map(({ selection, ...item }) => ({
    ...item,
    candidateMeta: {
      count: picked.length,
      contextTotal,
      appHits,
      policy: `按方向关键词${strength}关联${apps.length ? `与 ${apps.length} 个场景标签` : ""}动态生成`,
    },
  }));
}

function candidateTitle(direction, strategy, label) {
  if (label.includes("评测") || label.includes("基准")) return `${direction}的统一评测与失败分析`;
  if (label.includes("定义")) return `重新定义${direction}的问题边界`;
  if (label.includes("机理")) return `${direction}的失效机理分析`;
  if (label.includes("理论")) return `${direction}的理论解释与适用边界`;
  if (label.includes("复现")) return `${direction}的大规模复现与偏差分析`;
  if (strategy === "跨领域迁移") return `${direction}：借鉴${label}`;
  return `${direction}的${label}`;
}

export function scaffoldDescription(candidate, direction, benchmark = null) {
  if (!candidate) return "";
  const question = candidate.questions?.[0] || "机制成立时，哪个指标会怎么变？";
  const datasets = (candidate.datasets || benchmark?.datasets || []).slice(0, 3).map((d) => d.name || d).filter(Boolean);
  const metrics = (candidate.metrics || benchmark?.metrics || []).slice(0, 3);
  const baselines = (candidate.baselines || benchmark?.baselines || []).slice(0, 3);
  const appText = candidate.applicationNames?.length ? `${candidate.applicationNames.join(" / ")}场景的` : "";
  return [
    `围绕「${candidate.title}」，现有方法在${appText}____ 条件下存在 ____ 失效，${metrics[0] || "主指标"} 的差距为 ____。`,
    `我们假设：${candidate.reason}`,
    `若机制成立：${question}`,
    `最小验证：${candidate.minExperiment}${datasets.length ? `。建议先使用 ${datasets.join("、")}，按官方训练 / 验证 / 测试划分，确认没有测试集泄漏。` : "。"}`,
    `对比基线为 ${baselines.length ? baselines.join("、") : "____"}，数据集为 ${datasets.length ? datasets.join("、") : "____"}，按 ____ 划分；主指标为 ${metrics.length ? metrics.join("、") : "____"}，若 ${metrics[0] || "主指标"} 未超过 ____ 或代价上升超过 ____，判定失败。`,
  ].join("\n\n");
}

export const SAMPLE_DESCRIPTION = `在红外小目标检测中，现有方法在跨设备、低信噪比场景下漏检率明显升高，AP50 下降超过 5 个点。我们假设：分层频域先验与多尺度特征融合能抑制背景杂波，因为小目标的高频能量在频域中更集中。方法在 NUAA-SIRST 训练集上训练，在独立测试集 IRSTD-1k 上评估，主指标为 AP50 与虚警率，若 AP50 提升低于 2 个点或虚警率上升则判定失败。对比基线为 YOLOv8 与 DNANet 强基线；在同等参数量与算力下逐项消融频域分支、融合模块和多尺度分支。`;

// ---------- 结构体检：与 research_diagnose.py 的九项规则对齐 ----------
const METRIC_NAMES = ["ap50", "ap75", "map", "map50", " miou", "miou", "iou", "f1", "accuracy", "acc", "top-1", "top1", "top-5", "auc", "auroc", "pr-auc", "dice", "hd95", "c-index", "rmse", "mae", "mape", "em", "ndcg", "mrr", "spl", "nds", "mota", "idf1", "pass@", "psnr", "ssim", "lpips", "fid", "bleu", "rouge", "wer", "cer", "fps", "qps", "时延", "延迟", "吞吐", "召回", "精确率", "准确率", "成功率", "p95", "p99", "latency", "throughput", "recall", "precision"];
const DATA_NAMES = ["nuaa", "nudt", "coco", "imagenet", "kitti", "cityscapes", "voc", "mots", "visdrone", "brats", "luna", "sirius", "mvtec", "visa", "ade20k", "msrvtt", "squad", "mmlu", "gsm8k", "humaneval", "glue", "lvis", "nuscenes", "waymo", "movielens", "hotpotqa", "mimic", "chexpert", "isic", "tcga", "camelyon", "eth3d", "scannet", "era5", "instances", "样本", "例", "张"];
const MODEL_RE = /(yolo\w*|rt-?detr|detr|resnet\w*|vit\w*|swin\w*|deeplab\w*|unet|sam|clip|llama\w*|gpt\w*|bert\w*|mamba\w*|nerf|gaussian|diffusion|sd\w*|stable diffusion|transformer|faster[- ]?rcnn|mask[- ]?rcnn|deepsort|bytetrack|pointpillars|pointnet\w*|centerpoint|bev\w*|polynet|dncnn|xgboost|lstm|gru|t5|qwen|glm)/;
const QUANT_RE = /(\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*(?:个|点|倍|fps|ms|小时|天|周|gb|g))/;
const DATASET_RE = /[A-Z][A-Za-z\-]{2,}(?:-|_)[A-Za-z0-9\-]+/;
const PRIORITY = ["problem", "mechanism", "baseline", "data", "metric", "ablation", "budget", "stop", "scope"];

const has = (text, words) => words.some((word) => text.includes(word));

function sentences(text) {
  return String(text || "").split(/[。；;！!？?\n]/).filter((s) => s.trim());
}

function isSubstantive(text) {
  const raw = String(text || "").trim();
  if (!raw) return false;
  const punct = [...raw].filter((c) => "，。；：、！？,.;:!?\n".includes(c)).length;
  const cnChars = [...raw].filter((c) => c >= "\u4e00" && c <= "\u9fff").length;
  if (cnChars >= 60 && punct === 0) return false;
  const tokens = raw.split(/[\s、,，]+/).filter(Boolean);
  if (tokens.length >= 12) {
    const avgLen = tokens.reduce((sum, w) => sum + w.length, 0) / tokens.length;
    if (avgLen <= 3.2) return false;
  }
  const sents = sentences(raw).map((s) => s.trim()).filter((s) => s.length >= 8);
  if (sents.length >= 2) return sents.reduce((sum, s) => sum + s.length, 0) / sents.length >= 14;
  if (sents.length === 1 && sents[0].length >= 30) return true;
  return false;
}

const CHECKS = [
  ["problem", "问题具体", "在什么场景、哪一步失败、差多少", (t, d) => d.length >= 40 && has(t, ["失败", "漏检", "误检", "误差", "不准", "慢", "成本", "无法", "不足", "偏差", "退化", "瓶颈", "困难", "问题在于"]), "补一句：在什么数据/场景下，哪个环节具体不行，差多少"],
  ["mechanism", "机制可检验", "改变了什么 + 为什么会导致可测结果", (t) => has(t, ["因为", "从而", "机制", "通过", "约束", "目标函数", "信息流", "假设", "使", "导致"]) && (has(t, ["相比", "对比", "优于", "预期", "应该", "而不是"]) || QUANT_RE.test(t)), "写出可证伪假设：机制成立时哪个指标会怎么变；不成立会看到什么"],
  ["baseline", "baseline 点名", "能指名道姓的最强对手", (t) => MODEL_RE.test(t) || has(t, ["强基线"]), "点名 1–2 个具体模型/方法，并说明为什么它是最强对手"],
  ["data", "数据与划分", "数据集名称 + 训练测试如何划分", (t, d, raw) => (has(t, DATA_NAMES) || DATASET_RE.test(raw)) && has(t, ["划分", "测试集", "验证集", "跨集", "泄漏", "独立测试"]), "写清数据集名称、划分方式，以及如何避免测试集泄漏"],
  ["metric", "指标定义", "具体主指标 + 失败判据", (t) => has(t, METRIC_NAMES) && has(t, ["失败", "下降", "低于", "退化", "代价", "不能超过"]), "写清主指标（如 AP50、F1、p95 时延）+ 什么情况算失败"],
  ["ablation", "消融设计", "消融什么、与什么同等条件对比", (t) => has(t, ["消融", "ablation"]) && (/消融.{0,30}(分支|模块|项|部分|加|去|替换|同等|对照|参数)/.test(t) || has(t, ["逐项消融", "同等参数量", "同等算力", "消融实验设计"])), "说明消融哪些部分，并在同等参数量/算力下对照"],
  ["budget", "资源估算", "卡型、时长、预算", (t) => has(t, ["单卡", "gpu", "算力", "显存", "训练时间", "小时", "周", "预算"]) && (/\d/.test(t) || has(t, ["一天", "两天", "一周", "两周", "数周"])), "估算：需要什么卡、跑多久、最坏情况几周"],
  ["stop", "止损条件", "什么情况下承认失败并停下", (t) => has(t, ["停止条件", "止损", "失败则", "不成立则", "替代方案", "降级"]), "设定止损点：做到哪一步还没效果就换方向"],
  ["scope", "范围收敛", "一次只解决一个可完成的问题", (t, d) => d.length <= 800 && !has(t, ["统一所有", "彻底解决", "完全解决", "通用框架", "万物", "所有任务"]), "缩小范围：先做一个场景、一类失败、一个数据集"],
];

export function diagnose(idea = {}) {
  const title = cleanText(idea.title || "");
  const desc = cleanText(idea.desc || "");
  const raw = `${title} ${desc}`;
  const t = raw.toLowerCase();
  const substantive = isSubstantive(raw) && desc.length >= 40;

  let passed = [];
  let missing = [];
  for (const [key, label, why, fn, fix] of CHECKS) {
    let ok = false;
    try { ok = Boolean(fn(t, desc, raw)); } catch { ok = false; }
    const item = { key, label, why, fix };
    (ok ? passed : missing).push(item);
  }

  const keys = new Set(passed.map((p) => p.key));
  const warnings = [];
  if (!substantive) {
    let hollow = false;
    for (const key of ["problem", "mechanism", "baseline", "data", "metric", "ablation", "budget"]) {
      if (keys.has(key)) {
        keys.delete(key);
        hollow = true;
        const meta = CHECKS.find((c) => c[0] === key);
        passed = passed.filter((p) => p.key !== key);
        missing.unshift({ key, label: meta[1], why: meta[2], fix: "这段像关键词列表而不是描述，请用完整句子说明" });
      }
    }
    if (hollow) warnings.push("这段文字读起来像关键词列表：术语出现了，但没有说明具体是什么。「消融」两个字不等于设计了消融，「指标」两个字不等于定义了指标。");
  }
  if (desc.length >= 300 && !["problem", "mechanism", "baseline"].some((k) => keys.has(k))) {
    warnings.push("写得很多，但核心三件事（问题/机制/baseline）基本没说清。篇幅不等于深度。");
  }
  if (desc.length < 40) warnings.push("描述过短，当前判断基本只基于标题，仅供参考。");

  const core5 = ["problem", "mechanism", "baseline", "data", "metric"];
  const core6 = [...core5, "ablation"];
  const hasAll = (arr) => arr.every((k) => keys.has(k));
  let stage;
  let stageHint;
  let stageNum;
  if (hasAll(core6) && keys.size >= 8) {
    stage = "4 可写成文"; stageHint = "结构已齐，缺真实实验数据与写作"; stageNum = 4;
  } else if (hasAll(core5)) {
    stage = "3 可做完整实验"; stageHint = "五项核心条件齐备，可以开始跑实验"; stageNum = 3;
  } else if (hasAll(["problem", "mechanism"])) {
    stage = "2 可做最小实验"; stageHint = "问题与机制说清楚了，先做一个最小验证"; stageNum = 2;
  } else if (keys.has("problem")) {
    stage = "1 有问题，缺机制"; stageHint = "问题是真的，但还没说清你要改变什么"; stageNum = 1;
  } else {
    stage = "0 尚未成型"; stageHint = "还只是一句话，先补问题与机制"; stageNum = 0;
  }

  const order = Object.fromEntries(PRIORITY.map((k, i) => [k, i]));
  missing.sort((a, b) => (order[a.key] ?? 99) - (order[b.key] ?? 99));
  const next = missing.length
    ? missing.slice(0, 3).map((m) => `补：${m.label} —— ${m.fix}`)
    : ["结构已齐。接下来做真实实验，并如实记录失败结果"];
  next.push("先做最小验证：一个场景、一个基线、一个指标，两周内看到趋势");

  return {
    title, passed, missing, stage, stageNum, stageHint, next, warnings,
    count: { passed: passed.length, total: CHECKS.length },
    coverage: Math.round((100 * passed.length) / CHECKS.length),
  };
}

// ---------- 本地持久化 ----------
const IDEAS_KEY = "xtzk.v1.ideas";
const LAST_KEY = "xtzk.v1.lastDirection";

export function loadIdeas() {
  try {
    const raw = localStorage.getItem(IDEAS_KEY);
    const rows = raw ? JSON.parse(raw) : [];
    return Array.isArray(rows) ? rows : [];
  } catch { return []; }
}

export function saveIdeas(rows) {
  try {
    localStorage.setItem(IDEAS_KEY, JSON.stringify(rows.slice(0, 60)));
  } catch { /* 隐私模式下静默降级 */ }
}

export function rememberDirection(entry) {
  try { localStorage.setItem(LAST_KEY, JSON.stringify({ id: entry.id, name: entry.name, dataId: entry.dataId || "" })); } catch { /* noop */ }
}

export function lastDirection() {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fallback */ }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch { return false; }
}
