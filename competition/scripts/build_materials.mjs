import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COMP = path.resolve(HERE, "..");
const DATA = path.join(COMP, "site", "data");
const OUT = path.join(DATA, "materials.json");

const read = (file) => JSON.parse(fs.readFileSync(file, "utf8"));
const index = read(path.join(DATA, "index.json"));
const benchmarks = read(path.join(DATA, "benchmarks.json"));
const applicationsFile = read(path.join(DATA, "applications.json"));
const advisors = read(path.join(DATA, "advisors.json"));
const venues = read(path.join(DATA, "venues.json"));

const datasetMap = new Map();
for (const item of benchmarks.datasets || []) {
  datasetMap.set(item.name, {
    name: item.name,
    task: item.task || "",
    categories: item.categories || [],
    applications: item.applications || [],
    url: item.url || "",
    note: item.note || "",
    usedIn: item.usedIn || "",
    paperTitle: item.paperTitle || "",
    paperUrl: item.paperUrl || "",
    declaredDirections: item.directions || [],
    directions: [],
    metrics: [],
    baselines: [],
  });
}

const directionByName = new Map((index.directions || []).map((entry) => [entry.name, entry]));
const directions = [];
for (const entry of index.directions || []) {
  const file = path.join(DATA, "directions", `${entry.id}.json`);
  if (!fs.existsSync(file)) continue;
  const detail = read(file);
  const benchmark = detail.benchmark || {};
  const names = (benchmark.datasets || []).map((ds) => ds.name).filter(Boolean);
  directions.push({
    id: entry.id,
    name: entry.name,
    category: entry.category,
    apps: entry.apps || [],
    datasets: names,
    metrics: benchmark.metrics || [],
    baselines: benchmark.baselines || [],
    note: benchmark.note || "",
  });
  for (const name of names) {
    if (!datasetMap.has(name)) {
      datasetMap.set(name, {
        name,
        task: "",
        categories: [],
        applications: [],
        url: "",
        note: "方向基准中引用的数据集；请核对官方主页与许可。",
        usedIn: "",
        paperTitle: "",
        paperUrl: "",
        declaredDirections: [],
        directions: [],
        metrics: [],
        baselines: [],
      });
    }
    const ds = datasetMap.get(name);
    if (!ds.directions.some((row) => row.id === entry.id)) {
      ds.directions.push({ id: entry.id, name: entry.name, category: entry.category });
    }
    ds.metrics = [...new Set([...(ds.metrics || []), ...(benchmark.metrics || [])])].slice(0, 6);
    ds.baselines = [...new Set([...(ds.baselines || []), ...(benchmark.baselines || [])])].slice(0, 6);
  }
}

for (const ds of datasetMap.values()) {
  for (const name of ds.declaredDirections || []) {
    const entry = directionByName.get(name);
    if (!entry || ds.directions.some((row) => row.id === entry.id)) continue;
    ds.directions.push({ id: entry.id, name: entry.name, category: entry.category });
  }
  if (!ds.categories.length) {
    ds.categories = [...new Set(ds.directions.map((d) => d.category).filter((c) => c && c !== "应用领域"))];
  }
}

const datasets = [...datasetMap.values()]
  .filter((ds) => ds.url)
  .map(({ declaredDirections, ...ds }) => ({ ...ds, directionCount: ds.directions.length }))
  .sort((a, b) => b.directionCount - a.directionCount || a.name.localeCompare(b.name));

const categoryMap = new Map();
for (const entry of index.directions || []) {
  // 别名条目（x1..x5）不属于任何真实类目的方向计数，跳过，否则类目的
  // directionCount 会虚高，跟 index.stats.directions 的口径再次打架。
  if (entry.aliasOf) continue;
  if (!categoryMap.has(entry.category)) categoryMap.set(entry.category, { name: entry.category, directionCount: 0, datasetCount: 0 });
  categoryMap.get(entry.category).directionCount += 1;
}
for (const ds of datasets) {
  for (const name of ds.categories || []) {
    if (!categoryMap.has(name)) categoryMap.set(name, { name, directionCount: 0, datasetCount: 0 });
    categoryMap.get(name).datasetCount += 1;
  }
}
const categories = [...categoryMap.values()]
  .filter((cat) => cat.datasetCount > 0 && cat.name !== "应用领域")
  .sort((a, b) => b.datasetCount - a.datasetCount || b.directionCount - a.directionCount);

const appCount = new Map();
for (const ds of datasets) {
  for (const name of ds.applications || []) appCount.set(name, (appCount.get(name) || 0) + 1);
}
const applicationCounts = [...appCount.entries()]
  .map(([name, count]) => ({ name, count }))
  .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "zh"));

const appGroups = (applicationsFile.groups || []).map((group) => ({
  name: group.name,
  count: (group.apps || []).length,
  apps: (group.apps || []).map((app) => app.name),
}));

const payload = {
  version: new Date().toISOString().slice(0, 10),
  note: "素材库由方向库、公开基准目录与学者索引离线汇总。方向与数据集的关系来自每个方向的基准条目；新增数据集按官方主页与来源论文整理，未核验论文出处的条目会明确标注。分类计数为数据集数量，同一数据集可归入多个大类。这里展示的是可核对的数据关系，不代表最新 SOTA 排名。",
  stats: {
    // directions 这里统计的是“真正收录进来、且能挂基准卡的方向”= 本轮成功读到
    // data/directions/{id}.json 的条目数。index.json 的 directions 数组里还混着
    // x1..x5 这类示例别名（有 dataId/aliasOf，没有自己的方向文件），不能算进来。
    // 这个数必须等于 index.stats.directions，两边对不上说明数据没同步，直接报错。
    directions: directions.length,
    directionAliases: (index.directions || []).filter((e) => e.aliasOf).length,
    datasets: datasets.length,
    categories: categories.length,
    applications: applicationCounts.length,
    papers: index.stats?.papers || 345,
    venues: venues.length,
    scholars: advisors.length,
    withHomepage: advisors.filter((a) => a.homepage).length,
    withPaper: datasets.filter((d) => d.paperUrl).length,
  },
  categories,
  applications: applicationCounts,
  datasets,
  directions,
  applicationGroups: appGroups,
};

fs.writeFileSync(OUT, JSON.stringify(payload));

// 口径一致性自检：素材库与 index.json 报的方向数必须相同。历史上这里
// 出现过 index 报 536、素材库报 534、实际收录 531 三个数并存的情况，
// 就是没有这一步校验。数字口径见 AGENTS.md「数字必须真实计算」。
const expectDirections = index.stats?.directions;
if (typeof expectDirections === "number" && expectDirections !== payload.stats.directions) {
  console.error(
    `[build_materials] 方向数口径不一致：index.stats.directions=${expectDirections}，` +
    `素材库实际收录=${payload.stats.directions}。` +
    `请先重跑 export_web_data.py 让 index.json 与 directions/ 同步。`
  );
  process.exitCode = 1;
}

console.log(JSON.stringify({
  output: OUT,
  bytes: fs.statSync(OUT).size,
  stats: payload.stats,
  topDatasets: datasets.slice(0, 8).map((d) => `${d.name}:${d.directionCount}`),
}, null, 2));
