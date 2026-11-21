import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.join(path.resolve(HERE, ".."), "site", "data");
const read = (name) => JSON.parse(fs.readFileSync(path.join(DATA, name), "utf8"));

const index = read("index.json");
const advisors = read("advisors.json");
const papers = read("papers.json");
const benchmarks = read("benchmarks.json");
const materials = read("materials.json");
const applications = read("applications.json");
const orcid = read("orcid.json");
const venues = read("venues.json");

const pages = Array.isArray(papers) ? papers : papers.papers || [];
const datasets = benchmarks.datasets || [];
const appCount = (applications.groups || []).reduce(
  (sum, group) => sum + (group.items || group.apps || []).length,
  0,
);
const directionCategories = (index.categories || []).filter((cat) => cat.name !== "应用领域").length;
// index.directions 里混着 x1..x5 这类示例别名（带 aliasOf，指向真实方向，没有
// 自己的方向文件）。真实方向数必须排除它们，且要与 materials.json 实际收录数
// 一致。历史 bug：这里曾直接取数组长度得 536，而素材库报 534、实际收录 531，
// 三个数同时出现在页面上。口径定义见 AGENTS.md「数字必须真实计算」。
const realDirections = (index.directions || []).filter((d) => !d.aliasOf);
const directionCount = realDirections.length;
if (materials.stats?.directions && materials.stats.directions !== directionCount) {
  console.warn(
    `[sync_web_stats] 方向数不一致：index 真实方向=${directionCount}，` +
    `materials.stats.directions=${materials.stats.directions}。请重跑 build_materials.mjs。`
  );
}
const orcidId = (id) => String(id || "").replace(/^https?:\/\/orcid\.org\//, "").toUpperCase();
const records = orcid.records || {};
const schools = new Set();
for (const row of advisors) {
  const record = records[orcidId(row.orcid)];
  const name = record?.nameMatch && record.institution ? record.institution : row.institution || row.institutionZh || "";
  const key = String(name).trim().toLowerCase();
  if (key) schools.add(key);
}

const directionCounts = {};
for (const d of index.directions || []) {
  if (d.aliasOf) continue;
  if (d.category) directionCounts[d.category] = (directionCounts[d.category] || 0) + 1;
}
for (const cat of index.categories || []) {
  if (directionCounts[cat.name] != null) cat.count = directionCounts[cat.name];
}

index.stats = {
  ...index.stats,
  directions: directionCount,
  directionAliases: (index.directions || []).length - directionCount,
  categories: directionCategories,
  applications: appCount,
  applicationTags: appCount,
  datasets: datasets.length,
  curatedDatasets: datasets.length,
  papers: materials.stats.papers,
  orcid_papers: pages.length,
  venues: venues.length,
  scholars_exported: advisors.length,
  schools_exported: schools.size,
};

fs.writeFileSync(path.join(DATA, "index.json"), `${JSON.stringify(index, null, 2)}\n`);
console.log(JSON.stringify(index.stats, null, 2));
