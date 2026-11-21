import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COMP = path.resolve(HERE, "..");
const DATA = path.join(COMP, "site", "data");
const CACHE_DIR = path.join(HERE, ".cache");
const OUT = path.join(CACHE_DIR, "cached_institution_geo.json");
const HOMEPAGES = path.join(CACHE_DIR, "institution_homepages.json");
// 原来是写死的本机路径；改成相对仓库根，换电脑也能跑
const CACHE_SOURCE = path.resolve(HERE, "..", "..", ".cache_advisors.json");
const MAILTO = process.env.OPENALEX_MAILTO || "topic-atlas@example.com";
const CONCURRENCY = Number(process.env.GEO_CONCURRENCY || 5);

const read = (file, fallback) => {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
};
const write = (file, data) => fs.writeFileSync(file, JSON.stringify(data));
const norm = (value) => String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
const bareId = (url) => String(url || "").split("/").filter(Boolean).pop() || "";
const orcidBare = (value) => {
  const match = String(value || "").match(/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])/i);
  return match ? match[1].toUpperCase() : "";
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchJson(url) {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const res = await fetch(url, { headers: { "User-Agent": "topic-atlas-advisor-expansion/1.0" } });
      if (res.ok) return await res.json();
      if (res.status !== 429) return null;
    } catch {}
    await sleep(1200 * (attempt + 1));
  }
  return null;
}

function pickResult(name, results) {
  const target = norm(name);
  const exact = results.find((row) => norm(row.display_name) === target);
  if (exact) return exact;
  const alt = results.find((row) => (row.display_name_acronyms || []).some((word) => norm(word) === target));
  if (alt) return alt;
  const close = results.find((row) => {
    const display = norm(row.display_name);
    return display && (display.includes(target) || target.includes(display));
  });
  return close || null;
}

async function lookup(name) {
  const url = `https://api.openalex.org/institutions?search=${encodeURIComponent(name)}&per-page=5&mailto=${encodeURIComponent(MAILTO)}`;
  const json = await fetchJson(url);
  const hit = pickResult(name, json?.results || []);
  if (!hit) return { error: "not_found" };
  return {
    id: bareId(hit.id),
    name: hit.display_name || name,
    url: hit.homepage_url || "",
    city: hit.geo?.city || "",
    region: hit.geo?.region || "",
    countryCode: hit.country_code || hit.geo?.country_code || "",
    country: hit.geo?.country || "",
    lat: hit.geo?.latitude ?? null,
    lon: hit.geo?.longitude ?? null,
    ror: bareId(hit.ids?.ror),
  };
}

async function main() {
  const rows = read(CACHE_SOURCE, { rows: [] }).rows || [];
  const advisors = read(path.join(DATA, "advisors.json"), []);
  const keys = new Set();
  for (const row of advisors) {
    const id = orcidBare(row.orcid);
    if (id) keys.add(`orcid:${id}`);
    keys.add(`name:${norm(row.name)}|inst:${norm(row.institution)}`);
  }
  const missing = new Map();
  for (const row of rows) {
    const id = orcidBare(row.orcid);
    const key = id ? `orcid:${id}` : `name:${norm(row.name)}|inst:${norm(row.institution)}`;
    if (keys.has(key)) continue;
    const inst = norm(row.institution);
    if (!inst) continue;
    if (!missing.has(inst)) missing.set(inst, { name: row.institution, count: 0 });
    missing.get(inst).count += 1;
  }

  const cache = read(OUT, {});
  const homepages = read(HOMEPAGES, {}) || {};
  const targets = [...missing.values()].filter((item) => !cache[norm(item.name)]);
  console.log(`[geo] ${missing.size} institutions · ${targets.length} to lookup`);

  let index = 0;
  let done = 0;
  let resolved = 0;
  async function worker() {
    while (index < targets.length) {
      const item = targets[index];
      index += 1;
      const key = norm(item.name);
      const geo = await lookup(item.name);
      cache[key] = geo;
      if (geo?.id) {
        resolved += 1;
        homepages[geo.id] = { name: geo.name, url: geo.url || "" };
      }
      done += 1;
      if (done % 40 === 0) {
        write(OUT, cache);
        write(HOMEPAGES, homepages);
        console.log(`[geo] ${done} / ${targets.length} · resolved ${resolved}`);
      }
      await sleep(70);
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  write(OUT, cache);
  write(HOMEPAGES, homepages);

  const known = [...missing.keys()].filter((key) => cache[key] && !cache[key].error).length;
  console.log(JSON.stringify({ institutions: missing.size, lookedUp: targets.length, resolved, known, cache: OUT }, null, 2));
}

main().catch((err) => { console.error(err); process.exit(1); });
