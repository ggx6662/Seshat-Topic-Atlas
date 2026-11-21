import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { EXTRA_DATASETS, URL_FIXES } from "./dataset_expansion.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.resolve(HERE, "..", "site", "data");
const read = (name) => JSON.parse(fs.readFileSync(path.join(DATA, name), "utf8"));

const index = read("index.json");
const appsFile = read("applications.json");
const benchFile = read("benchmarks.json");

const categoryNames = new Set(index.directions.map((d) => d.category));
const directionNames = new Set(index.directions.map((d) => d.name));
const applicationNames = new Set(
  (appsFile.groups || []).flatMap((group) => (group.apps || []).map((app) => app.name))
);

const CATEGORY_ALIASES = {
  "多模态学习": "人工智能",
  "生物信息": "交叉与AI4Science",
};
const APPLICATION_ALIASES = {
  "安防与公共安全": "安全与隐私",
  "具身导航与交互": "机器人与具身",
  "体育计算与运动分析": "体育与运动",
  "养老与无障碍": "无障碍与老龄化",
  "软件工程": "企业服务与流程自动化",
  "广告与营销计算": "广告与营销",
  "平台治理": "内容与社交",
};

const issues = [];
const checked = EXTRA_DATASETS.map((item) => {
  const categories = [...new Set((item.categories || []).map((c) => CATEGORY_ALIASES[c] || c))];
  const applications = [...new Set((item.applications || []).map((a) => APPLICATION_ALIASES[a] || a))];
  const directions = [...new Set(item.directions || [])];
  for (const value of categories) {
    if (!categoryNames.has(value)) issues.push(`${item.name}: 未知大类 ${value}`);
  }
  for (const value of applications) {
    if (!applicationNames.has(value)) issues.push(`${item.name}: 未知应用 ${value}`);
  }
  for (const value of directions) {
    if (!directionNames.has(value)) issues.push(`${item.name}: 未知方向 ${value}`);
  }
  return {
    ...item,
    categories,
    applications,
    directions: directions.filter((name) => directionNames.has(name)),
  };
});

const duplicateNames = checked
  .map((d) => d.name)
  .filter((name, i, all) => all.indexOf(name) !== i);
if (duplicateNames.length) issues.push(`清单内重名：${[...new Set(duplicateNames)].join("、")}`);

if (issues.length) {
  console.error(issues.join("\n"));
  process.exit(1);
}

const datasets = benchFile.datasets.map((item) => {
  const categories = [...new Set((item.categories || []).map((c) => CATEGORY_ALIASES[c] || c))];
  const applications = [...new Set((item.applications || []).map((a) => APPLICATION_ALIASES[a] || a))];
  return { ...item, categories, applications };
});

const byName = new Map(datasets.map((item) => [item.name, item]));
let added = 0;
let updated = 0;

for (const item of checked) {
  const existing = byName.get(item.name);
  if (!existing) {
    datasets.push({ ...item });
    byName.set(item.name, datasets[datasets.length - 1]);
    added += 1;
    continue;
  }
  const next = {
    ...existing,
    task: existing.task || item.task,
    categories: [...new Set([...(existing.categories || []), ...item.categories])],
    applications: [...new Set([...(existing.applications || []), ...item.applications])],
    url: existing.url || item.url,
    usedIn: existing.usedIn || item.usedIn,
    note: existing.note || item.note,
    paperTitle: existing.paperTitle || item.paperTitle,
    paperUrl: existing.paperUrl || item.paperUrl,
  };
  if (item.directions.length) {
    next.directions = [...new Set([...(existing.directions || []), ...item.directions])];
  }
  if (JSON.stringify(next) !== JSON.stringify(existing)) updated += 1;
  Object.assign(existing, next);
}

for (const item of datasets) {
  if (!item.url && URL_FIXES[item.name]) item.url = URL_FIXES[item.name];
}

datasets.sort((a, b) => a.name.localeCompare(b.name, "en"));

benchFile.version = new Date().toISOString().slice(0, 10);
benchFile.note =
  "公开基准目录由项目人工整理，每条尽量同时给出数据集官方主页与可确认的来源论文；来源论文未核验的条目标注为待核验。目录反映相关方向论文常报告的公开基准，不代表最新 SOTA 排名。";
benchFile.datasets = datasets;
fs.writeFileSync(path.join(DATA, "benchmarks.json"), JSON.stringify(benchFile));

const missingUrl = datasets.filter((d) => !d.url);
const missingPaper = datasets.filter((d) => !d.paperUrl);
console.log(
  JSON.stringify(
    {
      total: datasets.length,
      added,
      updated,
      missingUrl: missingUrl.length,
      missingPaperUrl: missingPaper.length,
      missingUrlNames: missingUrl.map((d) => d.name),
    },
    null,
    2
  )
);
