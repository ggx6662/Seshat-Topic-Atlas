import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PAPER_TITLES } from "./paper_sources.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BENCH = path.resolve(HERE, "..", "site", "data", "benchmarks.json");
const CACHE = path.join(HERE, ".crossref_cache.json");

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
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const pending = [];
for (const item of bench.datasets) {
  if (item.paperUrl) continue;
  const title = item.paperTitle || PAPER_TITLES[item.name];
  if (!title) continue;
  if (cache[title]) {
    item.paperTitle = cache[title].title;
    item.paperUrl = cache[title].url;
    continue;
  }
  pending.push({ item, title });
}

let matched = 0;
const unresolved = [];
for (const row of pending) {
  const url = `https://api.crossref.org/works?query.bibliographic=${encodeURIComponent(
    row.title
  )}&rows=3&select=title,DOI,URL`;
  let items = [];
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "topic-atlas-dataset-catalog/1.0 (research metadata lookup)" },
      signal: AbortSignal.timeout(30000),
    });
    const json = await res.json();
    items = json.message?.items || [];
  } catch (error) {
    unresolved.push(`${row.item.name}: ${error.message}`);
    await sleep(1000);
    continue;
  }
  let best = null;
  let bestScore = 0;
  for (const entry of items) {
    const found = (entry.title || [])[0] || "";
    const score = coverage(row.title, found);
    if (score > bestScore) {
      best = { ...entry, found };
      bestScore = score;
    }
  }
  if (!best || bestScore < 0.9 || !best.DOI) {
    unresolved.push(row.item.name);
    await sleep(900);
    continue;
  }
  const link = `https://doi.org/${best.DOI}`;
  row.item.paperTitle = best.found;
  row.item.paperUrl = link;
  cache[row.title] = { title: best.found, url: link };
  matched += 1;
  await sleep(900);
}

fs.writeFileSync(CACHE, JSON.stringify(cache, null, 2));
fs.writeFileSync(BENCH, JSON.stringify(bench));
const missing = bench.datasets.filter((item) => !item.paperUrl);
console.log(
  JSON.stringify(
    {
      matched,
      unresolved: unresolved.length,
      unresolvedNames: unresolved,
      withPaper: bench.datasets.length - missing.length,
      missing: missing.length,
      missingNames: missing.map((item) => item.name),
    },
    null,
    2
  )
);
