import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = join(import.meta.dirname, "..");
const DATA = join(ROOT, "site", "data");
const CACHE = join(ROOT, ".cache_orcid");
const ROR_CACHE = join(CACHE, "_ror.json");
const SUFFIX = process.env.OUT_SUFFIX || "";
const OUT = join(DATA, `orcid${SUFFIX}.json`);
const PAPERS = join(DATA, `papers${SUFFIX}.json`);

const LIMIT = Number(process.env.LIMIT || 0);
const CONCURRENCY = Number(process.env.CONCURRENCY || 6);
const DELAY = Number(process.env.DELAY || 120);
const CHECKED_AT = "2026-11-18";
const CACHE_VERSION = 1;

mkdirSync(CACHE, { recursive: true });

const readJson = (file, fallback = null) => {
  try { return JSON.parse(readFileSync(file, "utf8")); } catch { return fallback; }
};
const writeJson = (file, value) => writeFileSync(file, JSON.stringify(value));

function orcidId(url) {
  const m = String(url || "").match(/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])/i);
  return m ? m[1].toUpperCase() : "";
}

const advisors = readJson(join(DATA, "advisors.json"), []);
if (!Array.isArray(advisors)) throw new Error("advisors.json is not an array");

const directionFiles = readdirSync(join(DATA, "directions")).filter((f) => f.endsWith(".json"));
const orcidDirections = new Map();
const byOrcid = new Map();
const directionAdvisor = new Map();

for (const file of directionFiles) {
  const d = readJson(join(DATA, "directions", file));
  if (!d) continue;
  for (const a of d.advisors || []) {
    const id = orcidId(a.orcid);
    if (!id) continue;
    if (!directionAdvisor.has(id)) directionAdvisor.set(id, { ...a, category: a.category || d.category || "" });
    if (!orcidDirections.has(id)) orcidDirections.set(id, []);
    const list = orcidDirections.get(id);
    if (d.name && !list.includes(d.name) && list.length < 6) list.push(d.name);
  }
}

for (const a of advisors) {
  const id = orcidId(a.orcid);
  if (id && !byOrcid.has(id)) byOrcid.set(id, a);
}

for (const [id, a] of directionAdvisor) {
  if (!byOrcid.has(id)) byOrcid.set(id, { ...a, source: "direction" });
}
const advisorNameCount = new Map();
for (const advisor of byOrcid.values()) {
  const key = norm(cleanAdvisorName(advisor.name));
  advisorNameCount.set(key, (advisorNameCount.get(key) || 0) + 1);
}
let targets = [...byOrcid.keys()];
targets.sort((a, b) => a.localeCompare(b));
const ONLY = (process.env.ONLY || "").split(",").map(orcidId).filter(Boolean);
if (ONLY.length) targets = ONLY.filter((id) => byOrcid.has(id));
if (process.env.REVERSE === "1") targets.reverse();
if (process.env.MISSING_ONLY === "1") targets = targets.filter((id) => !existsSync(join(CACHE, `${id}.json`)));
const SKIP = Number(process.env.SKIP || 0);
if (SKIP) targets = targets.slice(SKIP);
if (LIMIT) targets = targets.slice(0, LIMIT);
console.log(`[orcid] targets ${targets.length} (direction ${orcidDirections.size}, directory ${advisors.length})`);

function yearOf(date) {
  return Number(date?.year?.value) || 0;
}

function parseRecord(rec) {
  const person = rec?.person || {};
  const name = person.name || {};
  const given = name["given-names"]?.value || "";
  const family = name["family-name"]?.value || "";
  const credit = name["credit-name"]?.value || "";
  const display = credit || [given, family].filter(Boolean).join(" ").trim();

  const employments = [];
  for (const group of rec?.["activities-summary"]?.employments?.["affiliation-group"] || []) {
    for (const summary of group.summaries || []) {
      const e = summary["employment-summary"];
      if (!e) continue;
      employments.push({
        org: e.organization?.name || "",
        dept: e["department-name"] || "",
        city: e.organization?.address?.city || "",
        region: e.organization?.address?.region || "",
        country: e.organization?.address?.country || "",
        start: yearOf(e["start-date"]),
        end: yearOf(e["end-date"]),
      });
    }
  }

  const urls = (person["researcher-urls"]?.["researcher-url"] || [])
    .map((u) => String(u.url?.value || "").trim())
    .filter(Boolean);

  const works = [];
  for (const group of rec?.["activities-summary"]?.works?.group || []) {
    const w = (group["work-summary"] || [])[0];
    if (!w) continue;
    const title = String(w.title?.title?.value || "").replace(/\s+/g, " ").trim();
    if (!title) continue;
    const year = yearOf(w["publication-date"]);
    const doi = (w["external-ids"]?.["external-id"] || [])
      .find((x) => String(x["external-id-type"] || "").toLowerCase() === "doi")?.["external-id-value"] || "";
    works.push({
      title,
      year,
      venue: String(w["journal-title"]?.value || "").trim(),
      type: String(w.type || "").trim(),
      doi: String(doi).trim(),
      url: String(w.url?.value || "").trim(),
    });
  }

  return { display, given, family, employments, urls, works };
}

async function fetchJson(url, tries = 5) {
  let last;
  for (let attempt = 0; attempt < tries; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json", "User-Agent": "topic-compass-competition/1.0" },
        signal: AbortSignal.timeout(30000),
      });
      if (response.status === 404 || response.status === 409) return null;
      if (response.status === 429) {
        const retry = Number(response.headers.get("retry-after")) || 0;
        await new Promise((r) => setTimeout(r, retry ? retry * 1000 : 2500 * (attempt + 1)));
        last = new Error("429");
        continue;
      }
      if (!response.ok) throw new Error(String(response.status));
      return await response.json();
    } catch (err) {
      last = err;
      await new Promise((r) => setTimeout(r, 700 * (attempt + 1)));
    }
  }
  throw last;
}

async function getRecord(id) {
  const file = join(CACHE, `${id}.json`);
  const cached = readJson(file);
  if (cached && cached.v === CACHE_VERSION && cached.parsed) return cached;
  let parsed = null;
  try {
    const raw = await fetchJson(`https://pub.orcid.org/v3.0/${id}/record`);
    if (raw) parsed = parseRecord(raw);
  } catch (err) {
    console.log(`[orcid] ${id} failed: ${err?.message || err}`);
  }
  const value = { v: CACHE_VERSION, fetchedAt: CHECKED_AT, parsed };
  writeJson(file, value);
  return value;
}

let cursor = 0;
let done = 0;
async function worker() {
  while (cursor < targets.length) {
    const id = targets[cursor];
    cursor += 1;
    await getRecord(id);
    done += 1;
    if (done % 50 === 0) console.log(`[orcid] ${done}/${targets.length}`);
    await new Promise((r) => setTimeout(r, DELAY));
  }
}
const started = Date.now();
await Promise.all(Array.from({ length: CONCURRENCY }, worker));
console.log(`[orcid] fetched ${targets.length} in ${Math.round((Date.now() - started) / 1000)}s`);

function norm(s) {
  return String(s || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, " ").replace(/\s+/g, " ").trim();
}
function cleanAdvisorName(name) {
  return String(name || "").replace(/\s+\d{4}$/, "").replace(/\s*\([^)]*\)\s*$/, "").trim();
}
function nameMatch(advisorName, parsed) {
  const parts = norm(cleanAdvisorName(advisorName)).split(" ").filter(Boolean);
  if (!parts.length) return false;
  const tokens = new Set(parts);
  const family = norm(parsed?.family);
  const given = norm(parsed?.given);
  const display = norm(parsed?.display);
  const familyTokens = family.split(" ").filter(Boolean);
  const givenTokens = given.split(" ").filter(Boolean);
  if (familyTokens.length) {
    if (familyTokens.some((t) => !tokens.has(t))) return false;
    if (givenTokens.length) {
      if (givenTokens.every((t) => tokens.has(t))) return true;
      if (givenTokens[0] === parts[0]) return true;
      return givenTokens[0][0] === parts[0][0];
    }
    return true;
  }
  if (display) {
    const displayTokens = display.split(" ").filter(Boolean);
    if (displayTokens.length >= 2 && displayTokens.every((t) => tokens.has(t))) return true;
    if (displayTokens.length === 1 && displayTokens[0].length >= 4 && tokens.has(displayTokens[0])) return true;
  }
  return false;
}

function nameMatchStrict(advisorName, parsed) {
  const parts = norm(cleanAdvisorName(advisorName)).split(" ").filter(Boolean);
  if (!parts.length) return false;
  const last = parts[parts.length - 1];
  const first = parts[0][0];
  const familyTokens = norm(parsed?.family).split(" ").filter(Boolean);
  const givenTokens = norm(parsed?.given).split(" ").filter(Boolean);
  const displayTokens = norm(parsed?.display).split(" ").filter(Boolean);
  if (familyTokens.length) {
    if (!familyTokens.includes(last)) return false;
    return !givenTokens.length || givenTokens[0][0] === first;
  }
  if (displayTokens.length) return displayTokens.includes(last) && displayTokens[0][0] === first;
  return false;
}

function fullNameMatch(advisorName, parsed) {
  const tokens = new Set(norm(cleanAdvisorName(advisorName)).split(" ").filter(Boolean));
  const displayTokens = norm(parsed?.display).split(" ").filter(Boolean);
  return displayTokens.length >= 2 && displayTokens.every((t) => tokens.has(t));
}

const INST_STOP = new Set([
  "university", "of", "the", "and", "institute", "college", "school", "department", "dept",
  "faculty", "center", "centre", "national", "state", "key", "laboratory", "lab", "research",
  "science", "sciences", "technology", "engineering", "academy", "china", "chinese",
]);
function institutionKeys(value) {
  return norm(value).split(" ").filter((t) => t.length >= 4 && !INST_STOP.has(t)).map((t) => t.replace(/^southern$/, "south").replace(/^northern$/, "north").replace(/^eastern$/, "east").replace(/^western$/, "west"));
}
function sameInstitution(advisor, employments) {
  const names = [advisor.institution, ...(advisor.institutionNames || [])].filter(Boolean);
  const keys = new Set(names.flatMap(institutionKeys));
  if (!keys.size) return false;
  for (const employment of employments) {
    const org = String(employment?.org || "");
    if (!org) continue;
    const orgNorm = norm(org);
    if (names.some((name) => {
      const nameNorm = norm(name);
      return nameNorm && (nameNorm.includes(orgNorm) || orgNorm.includes(nameNorm));
    })) return true;
    if (institutionKeys(org).some((token) => keys.has(token))) return true;
  }
  return false;
}

const countryZh = {
  "United States": "美国", "United Kingdom": "英国", "Canada": "加拿大", "Australia": "澳大利亚",
  "Germany": "德国", "France": "法国", "Japan": "日本", "Singapore": "新加坡",
  "Switzerland": "瑞士", "Netherlands": "荷兰", "Sweden": "瑞典", "South Korea": "韩国",
  "Hong Kong": "中国香港", "China": "中国", "Taiwan": "中国台湾", "Macao": "中国澳门", "Macau": "中国澳门",
  "Italy": "意大利", "Spain": "西班牙", "Belgium": "比利时", "Denmark": "丹麦",
  "Norway": "挪威", "Finland": "芬兰", "Austria": "奥地利", "Israel": "以色列",
  "India": "印度", "Brazil": "巴西", "New Zealand": "新西兰", "Ireland": "爱尔兰",
};

const provinceZh = {
  Anhui: "安徽", Beijing: "北京", Chongqing: "重庆", Fujian: "福建", Gansu: "甘肃", Guangdong: "广东",
  Guangxi: "广西", Guizhou: "贵州", Hainan: "海南", Hebei: "河北", Heilongjiang: "黑龙江", Henan: "河南",
  Hubei: "湖北", Hunan: "湖南", "Inner Mongolia": "内蒙古", Jiangsu: "江苏", Jiangxi: "江西", Jilin: "吉林",
  Liaoning: "辽宁", Ningxia: "宁夏", Qinghai: "青海", Shaanxi: "陕西", Shandong: "山东", Shanghai: "上海",
  Shanxi: "山西", Sichuan: "四川", Tianjin: "天津", Tibet: "西藏", Xinjiang: "新疆", Yunnan: "云南", Zhejiang: "浙江",
  "Hong Kong": "中国香港", Macau: "中国澳门", Macao: "中国澳门", Taiwan: "中国台湾",
};

const CHINA_COUNTRY = new Set(["CN", "CHN", "CHINA", "HK", "HKG", "HONG KONG", "MO", "MACAU", "MACAO", "TW", "TWN", "TAIWAN"]);
const CHINA_CITY = /beijing|shanghai|shenzhen|guangzhou|hangzhou|nanjing|wuhan|chengdu|xi'?an|tianjin|suzhou|hefei|changsha|qingdao|dalian|xiamen|jinan|zhengzhou|chongqing|harbin|shenyang|kunming|nanchang|fuzhou|ningbo|wuxi|zhuhai|hong kong|macau/i;
function isChinaEmployment(employment) {
  const country = String(employment?.country || "").trim().toUpperCase();
  if (CHINA_COUNTRY.has(country)) return true;
  const org = String(employment?.org || "");
  return /china|中国|university of science and technology of china|peking|tsinghua|zhejiang|fudan|shanghai jiao|jiao tong/i.test(org) || CHINA_CITY.test(org);
}

const localization = readJson(join(ROOT, "institution_localization.json"), {});
const localByAlias = new Map();
for (const [name, info] of Object.entries(localization?.institutions || {})) {
  for (const alias of new Set([name, ...(info.aliases || [])])) {
    if (alias) localByAlias.set(norm(alias), info);
  }
}

const rorCache = readJson(ROR_CACHE, {}) || {};
const rorQueue = new Map();
for (const id of targets) {
  if (!directionAdvisor.has(id)) continue;
  const cached = readJson(join(CACHE, `${id}.json`));
  const parsed = cached?.v === CACHE_VERSION ? cached.parsed : null;
  const advisor = byOrcid.get(id);
  if (!parsed || !advisor || !nameMatch(advisor.name, parsed)) continue;
  const pick = pickEmployment(parsed.employments);
  if (pick?.org && (!rorCache[norm(pick.org)] || !rorCache[norm(pick.org)].country)) rorQueue.set(norm(pick.org), pick.org);
}

function uniqueWorks(works) {
  const seen = new Set();
  const out = [];
  for (const w of works || []) {
    const key = w.doi ? `d:${w.doi.toLowerCase()}` : `t:${norm(w.title)}|${w.year}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(w);
  }
  return out;
}

const SCHOLARLY = new Set(["journal-article", "conference-paper", "book-chapter", "preprint", "working-paper", "book", "review"]);

function pickEmployment(list) {
  if (!list?.length) return null;
  const active = list.filter((e) => !e.end);
  const pool = active.length ? active : list;
  return [...pool].sort((a, b) => (b.start || 0) - (a.start || 0))[0] || null;
}

let rorDone = 0;
for (const [key, org] of rorQueue) {
  try {
    const data = await fetchJson(`https://api.ror.org/organizations?query=${encodeURIComponent(org)}`);
    const items = data?.items || [];
    let best = null;
    for (const item of items.slice(0, 5)) {
      const display = (item.names || []).find((n) => (n.types || []).includes("ror_display"))?.value
        || (item.names || [])[0]?.value || "";
      const keys = new Set([display, ...(item.names || []).map((n) => n.value), ...(item.acronyms || [])].map(norm).filter(Boolean));
      if (keys.has(norm(org))) { best = { item, display }; break; }
      if (!best && norm(display) && (norm(display).includes(norm(org)) || norm(org).includes(norm(display)))) {
        best = { item, display };
      }
    }
    if (best) {
      rorCache[key] = {
        id: best.item.id || "",
        name: best.display,
        website: (best.item.links || []).find((l) => l.type === "website")?.value || "",
        country: best.item.locations?.[0]?.geonames_details?.country_name || "",
        region: best.item.locations?.[0]?.geonames_details?.country_subdivision_name || "",
        city: best.item.locations?.[0]?.geonames_details?.name || "",
      };
    } else {
      rorCache[key] = null;
    }
  } catch (err) {
    console.log(`[ror] ${org}: ${err?.message || err}`);
    rorCache[key] = null;
  }
  rorDone += 1;
  if (rorDone % 50 === 0) console.log(`[ror] ${rorDone}/${rorQueue.size}`);
  await new Promise((r) => setTimeout(r, 160));
}
if (rorQueue.size) writeJson(ROR_CACHE, rorCache);
console.log(`[ror] resolved ${Object.values(rorCache).filter(Boolean).length} / ${Object.keys(rorCache).length}`);

const BLOCK = /orcid\.org|scholar\.google|linkedin|researchgate|dblp\.|semanticscholar|github\.com|twitter\.com|x\.com|facebook\.com|youtube\.com|weibo\.com|zhihu\.com|loop\.frontiersin|scopus\.com|webofscience|publons/i;

function academicHomepage(urls) {
  const list = urls.filter((u) => /^https?:\/\//i.test(u) && !BLOCK.test(u));
  return list[0] || "";
}

const records = {};
const paperMap = new Map();
const stats = { checked: targets.length, nameMatched: 0, rejectedOverseas: 0, rejectedWeak: 0, countryMatched: 0, noEmployment: 0, withEmployment: 0, withHomepage: 0, withWorks: 0, correctedInstitution: 0 };
const usedOrcid = new Set();

for (const id of targets) {
  const cached = readJson(join(CACHE, `${id}.json`));
  const parsed = cached?.v === CACHE_VERSION ? cached.parsed : null;
  const advisor = byOrcid.get(id);
  if (!parsed || !advisor) continue;
  const strictMatch = nameMatchStrict(advisor.name, parsed);
  if (!strictMatch && !nameMatch(advisor.name, parsed)) {
    records[id] = { name: parsed.display, nameMatch: false, nameMatchReason: "name", checkedAt: CHECKED_AT };
    continue;
  }
  const isDirection = directionAdvisor.has(id);
  const employments = (parsed.employments || []).filter((e) => e.org);
  if (isDirection && !strictMatch) {
    const institutionMatch = employments.length && sameInstitution(advisor, employments);
    const uniqueFullName = !employments.length
      && fullNameMatch(advisor.name, parsed)
      && advisorNameCount.get(norm(cleanAdvisorName(advisor.name))) === 1;
    if (!institutionMatch && !uniqueFullName) {
      records[id] = { name: parsed.display, nameMatch: false, nameMatchReason: "weakMatch", checkedAt: CHECKED_AT };
      stats.rejectedWeak += 1;
      continue;
    }
  }
  if (!isDirection && employments.length && !employments.some(isChinaEmployment)) {
    records[id] = { name: parsed.display, nameMatch: false, nameMatchReason: "overseasEmployment", checkedAt: CHECKED_AT };
    stats.rejectedOverseas += 1;
    continue;
  }
  stats.nameMatched += 1;
  if (!isDirection) {
    if (employments.length) stats.countryMatched += 1;
    else stats.noEmployment += 1;
  }
  const pick = isDirection ? pickEmployment(parsed.employments) : null;
  let institution = advisor.institution || "";
  let institutionZh = advisor.institutionZh || "";
  let province = advisor.province || "";
  let country = "";
  let institutionUrl = advisor.institutionUrl || "";
  let ror = "";
  const employmentCurrent = Boolean(pick && !pick.end);
  const employmentVerified = Boolean(pick);

  if (isDirection && pick) {
    stats.withEmployment += 1;
    country = countryZh[rorCache[norm(pick.org)]?.country] || countryZh[pick.country] || rorCache[norm(pick.org)]?.country || pick.country || "";
    const local = localByAlias.get(norm(pick.org));
    const rorInfo = rorCache[norm(pick.org)];
    const nextName = rorInfo?.name || pick.org;
    if (employmentCurrent && nextName && norm(nextName) !== norm(institution)) {
      institution = nextName;
      institutionZh = local?.zh || "";
      province = local?.province_zh || provinceZh[pick.region] || countryZh[pick.country] || countryZh[rorInfo?.country] || pick.region || "";
      institutionUrl = rorInfo?.website || "";
      stats.correctedInstitution += 1;
    } else if (local) {
      institutionZh = local.zh || institutionZh;
      province = local.province_zh || province;
    }
    if (employmentCurrent && rorInfo?.id) ror = rorInfo.id;
    if (employmentCurrent && !institutionUrl && rorInfo?.website) institutionUrl = rorInfo.website;
  }

  let homepage = advisor.homepage || "";
  let homepageSource = advisor.homepageSource || "";
  if (!homepage) {
    const found = academicHomepage(parsed.urls);
    if (found) {
      homepage = found;
      homepageSource = "ORCID";
      stats.withHomepage += 1;
    }
  }

  const unique = uniqueWorks(parsed.works);
  const dated = unique.filter((w) => w.year >= 2015 && w.year <= 2026);
  const recent = dated.slice().sort((a, b) => b.year - a.year).slice(0, 12);
  const years = {};
  for (let y = 2021; y <= 2026; y += 1) years[y] = 0;
  for (const w of unique) if (years[w.year] !== undefined) years[w.year] += 1;
  const recent5 = dated.filter((w) => w.year >= 2022).length;
  const latest = Math.max(0, ...dated.map((w) => w.year));
  if (unique.length) stats.withWorks += 1;

  const record = {
    name: advisor.name,
    nameMatch: true,
    activity: { from: 2021, to: 2026, years, recent5, latest, total: unique.length },
    works: recent.slice(0, 3),
    worksTotal: unique.length,
    checkedAt: CHECKED_AT,
  };
  if (isDirection) {
    Object.assign(record, {
      institution, institutionZh, province, country, institutionUrl, ror, employmentVerified, employmentCurrent,
      category: advisor.category || "",
    });
  } else {
    record.employmentScope = employments.length ? "china" : "unknown";
  }
  if (homepage) {
    record.homepage = homepage;
    record.homepageSource = homepageSource;
  }
  records[id] = record;
  usedOrcid.add(id);

  if (!isDirection) continue;
  const category = advisor.category || "";
  for (const w of recent) {
    if (!SCHOLARLY.has(w.type)) continue;
    const doi = w.doi.toLowerCase();
    const key = doi ? `doi:${doi}` : `t:${norm(w.title)}|${w.year}`;
    if (!paperMap.has(key)) {
      paperMap.set(key, {
        title: w.title,
        year: w.year,
        venue: w.venue,
        type: w.type,
        doi: w.doi,
        url: w.doi ? `https://doi.org/${w.doi}` : (w.url || `https://orcid.org/${id}`),
        scholar: advisor.name,
        orcid: id,
        institution: institutionZh || institution,
        category,
      });
    }
  }
}

const papers = [...paperMap.values()].sort((a, b) => (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title));
const byCategory = {};
for (const p of papers) if (p.category) byCategory[p.category] = (byCategory[p.category] || 0) + 1;
const paperOrcids = new Set(papers.map((p) => p.orcid));
for (const [id, rec] of Object.entries(records)) {
  if (rec.nameMatch) rec.papersIndexed = paperOrcids.has(id);
}
stats.withPapers = paperOrcids.size;

writeJson(OUT, {
  generatedAt: CHECKED_AT,
  source: "ORCID public API v3.0",
  checked: stats.checked,
  records,
});
writeJson(PAPERS, {
  generatedAt: CHECKED_AT,
  source: "ORCID public works",
  count: papers.length,
  categories: byCategory,
  papers,
});

console.log(JSON.stringify({ ...stats, papers: papers.length, scholarsUsed: usedOrcid.size }, null, 1));
