import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PAPER_TITLES, PAPER_LINKS } from "./paper_sources.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.resolve(HERE, "..", "site", "data");
const CACHE = path.join(HERE, ".arxiv_cache.json");
const BENCH = path.join(DATA, "benchmarks.json");

const bench = JSON.parse(fs.readFileSync(BENCH, "utf8"));
const cache = fs.existsSync(CACHE) ? JSON.parse(fs.readFileSync(CACHE, "utf8")) : {};

const norm = (value) =>
  value
    .toLowerCase()
    .replace(/&amp;/g, "&")
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, " ")
    .trim();
const tokens = (value) => new Set(norm(value).split(" ").filter(Boolean));
const coverage = (target, found) => {
  const a = tokens(target);
  const b = tokens(found);
  let hit = 0;
  for (const token of a) if (b.has(token)) hit += 1;
  return a.size ? hit / a.size : 0;
};

const pending = [];
for (const item of bench.datasets) {
  if (item.paperUrl) continue;
  if (PAPER_LINKS[item.name]) {
    const [title, url] = PAPER_LINKS[item.name];
    item.paperTitle = title;
    item.paperUrl = url;
    continue;
  }
  const title = item.paperTitle || PAPER_TITLES[item.name];
  if (!title) continue;
  if (cache[title]) {
    item.paperTitle = cache[title].title;
    item.paperUrl = cache[title].url;
    continue;
  }
  pending.push({ item, title });
}

const batches = [];
for (let i = 0; i < pending.length; i += 6) batches.push(pending.slice(i, i + 6));

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let matched = 0;
const unmatched = [];

for (const batch of batches) {
  const query = batch.map((row) => `ti:"${row.title.replace(/"/g, "")}"`).join(" OR ");
  const url = `https://export.arxiv.org/api/query?search_query=${encodeURIComponent(query)}&max_results=40`;
  let xml = "";
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(30000) });
    xml = await res.text();
  } catch (error) {
    unmatched.push(...batch.map((row) => `${row.item.name}: 请求失败 ${error.message}`));
    continue;
  }
  const entries = xml
    .split("<entry>")
    .slice(1)
    .map((block) => {
      const id = (block.match(/<id>https?:\/\/arxiv\.org\/abs\/([^<]+)<\/id>/) || [])[1] || "";
      const rawTitle = (block.match(/<title>([\s\S]*?)<\/title>/) || [])[1] || "";
      return { id, title: rawTitle.replace(/\s+/g, " ").trim() };
    })
    .filter((entry) => entry.id && entry.title);

  for (const row of batch) {
    let best = null;
    let bestScore = 0;
    for (const entry of entries) {
      const score = coverage(row.title, entry.title);
      if (score > bestScore && score >= 0.82) {
        best = entry;
        bestScore = score;
      }
    }
    if (!best) {
      unmatched.push(row.item.name);
      continue;
    }
    const paperUrl = `https://arxiv.org/abs/${best.id.replace(/v\d+$/, "")}`;
    row.item.paperTitle = best.title;
    row.item.paperUrl = paperUrl;
    cache[row.title] = { title: best.title, url: paperUrl };
    matched += 1;
  }
  fs.writeFileSync(CACHE, JSON.stringify(cache, null, 2));
  await sleep(2200);
}

fs.writeFileSync(BENCH, JSON.stringify(bench));
const missing = bench.datasets.filter((item) => !item.paperUrl);
console.log(
  JSON.stringify(
    {
      matched,
      unresolved: unmatched.length,
      unresolvedNames: unmatched,
      total: bench.datasets.length,
      withPaper: bench.datasets.length - missing.length,
      missing: missing.length,
    },
    null,
    2
  )
);
