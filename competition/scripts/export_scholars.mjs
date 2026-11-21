import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COMP = path.resolve(HERE, "..");
const ROOT = path.resolve(COMP, "..");
const CACHE = path.join(HERE, ".cache");
const OUT = process.env.ADVISOR_OUT || path.join(COMP, "site", "data", "advisors.json");
const SOURCE = process.env.ADVISOR_SOURCE || path.join(ROOT, "advisor_directory_full.json");
const LOCALIZATION = process.env.INSTITUTION_LOCALIZATION || path.join(ROOT, "institution_localization.json");

const OPENALEX_MAILTO = process.env.OPENALEX_MAILTO || "topic-atlas@example.com";
const ORCID_CONCURRENCY = Number(process.env.ORCID_CONCURRENCY || 10);

fs.mkdirSync(CACHE, { recursive: true });

function readJSON(file, fallback = null) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
}

function writeJSON(file, data) {
  fs.writeFileSync(file, JSON.stringify(data));
}

function normalize(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "");
}

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? url.href.replace(/\/+$/, "") : "";
  } catch { return ""; }
}

function orcidBare(value) {
  const match = String(value || "").match(/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])/i);
  return match ? match[1].toUpperCase() : "";
}

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function fetchJSON(url, tries = 3) {
  let last;
  for (let attempt = 0; attempt < tries; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json", "User-Agent": "topic-atlas-scholar-export/1.0" },
      });
      if (response.status === 429) {
        await sleep(1200 * (attempt + 1));
        last = new Error("429");
        continue;
      }
      if (!response.ok) throw new Error(String(response.status));
      return await response.json();
    } catch (err) {
      last = err;
      if (attempt < tries - 1) await sleep(400 * (attempt + 1));
    }
  }
  throw last || new Error("fetch failed");
}

async function loadInstitutionHomepages() {
  const cacheFile = path.join(CACHE, "institution_homepages.json");
  const cache = readJSON(cacheFile, {}) || {};
  const source = readJSON(SOURCE);
  const ids = [...new Set((source?.advisors || []).map((a) => {
    const match = String(a.institution_id || "").match(/openalex\.org\/(I\d+)/);
    return match ? match[1] : "";
  }).filter(Boolean))];
  const missing = ids.filter((id) => !(id in cache));
  if (missing.length) {
    console.log(`[institutions] fetching ${missing.length} / ${ids.length}`);
    for (let i = 0; i < missing.length; i += 50) {
      const batch = missing.slice(i, i + 50);
      const filter = `ids.openalex:${batch.join("|")}`;
      const url = `https://api.openalex.org/institutions?filter=${encodeURIComponent(filter)}&per-page=50&select=id,display_name,homepage_url&mailto=${OPENALEX_MAILTO}`;
      try {
        const data = await fetchJSON(url, 4);
        for (const item of data.results || []) {
          const id = String(item.id || "").split("/").pop();
          cache[id] = { name: item.display_name || "", url: safeUrl(item.homepage_url) };
        }
      } catch (err) {
        console.warn(`[institutions] batch ${i / 50 + 1} failed: ${err.message}`);
      }
      if (i % 500 === 0) {
        writeJSON(cacheFile, cache);
        console.log(`[institutions] ${Math.min(i + 50, missing.length)} / ${missing.length}`);
      }
      await sleep(110);
    }
    writeJSON(cacheFile, cache);
  }
  for (const id of ids) if (!cache[id]) cache[id] = { name: "", url: "" };
  return cache;
}

async function loadCsrankings() {
  const cacheFile = path.join(CACHE, "csrankings.json");
  const cached = readJSON(cacheFile, null);
  if (cached?.byOrcid) return cached;
  const byOrcid = {};
  const letters = "abcdefghijklmnopqrstuvwxyz".split("");
  for (const letter of letters) {
    const url = `https://csrankings.org/csrankings-${letter}.csv`;
    try {
      const response = await fetch(url, { headers: { "User-Agent": "topic-atlas-scholar-export/1.0" } });
      if (!response.ok) throw new Error(String(response.status));
      const text = await response.text();
      for (const line of text.trim().split(/\r?\n/).slice(1)) {
        const [name, affiliation, homepage, scholarid, orcid] = line.split(",");
        const oid = orcidBare(orcid);
        if (!oid || !homepage) continue;
        byOrcid[oid] = { name, affiliation, homepage: safeUrl(homepage), scholarid };
      }
      console.log(`[csrankings] ${letter}: ${Object.keys(byOrcid).length}`);
    } catch (err) {
      console.warn(`[csrankings] ${letter} failed: ${err.message}`);
    }
    await sleep(80);
  }
  const output = { generatedAt: new Date().toISOString(), byOrcid };
  writeJSON(cacheFile, output);
  return output;
}

const BAD_HOSTS = [
  "scholar.google.", "researchgate.net", "linkedin.com", "facebook.com", "twitter.com", "x.com",
  "youtube.com", "youtu.be", "wikipedia.org", "scopus.com", "webofscience.com", "semanticscholar.org",
  "dblp.org", "arxiv.org", "doi.org", "orcid.org", "google.com", "bing.com", "baidu.com",
];

function classifyHomepage(raw, source) {
  const url = safeUrl(raw);
  if (!url) return null;
  let host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch { return null; }
  if (BAD_HOSTS.some((bad) => host.includes(bad))) return null;
  const pathName = (() => { try { return new URL(url).pathname.toLowerCase(); } catch { return ""; } })();
  const academic = /(^|\.)(edu|ac)\.[a-z]{2,}$/.test(host) || /\.edu\./.test(host) || /\.ac\./.test(host);
  const profileLike = /(~|homepage|home-page|people|person|profile|faculty|staff|member|group|lab|team|index)/.test(pathName);
  if (pathName === "/" && !profileLike && !/(lab|group|home|page|site)/.test(host)) return null;
  const personalDomain = !/^(www\.)?(github\.io|gitlab\.io|netlify\.app|vercel\.app)$/.test(host);
  if (!academic && !profileLike && !personalDomain) return null;
  const label = /(group|lab|team|centre|center)/.test(`${host} ${pathName}`) ? "课题组主页" : "个人主页";
  return { url, label, source };
}

async function loadOrcidHomepages(orcidIds) {
  const cacheFile = path.join(CACHE, "orcid_urls.json");
  const cache = readJSON(cacheFile, {}) || {};
  const missing = orcidIds.filter((id) => !(id in cache));
  if (!missing.length) return cache;
  console.log(`[orcid] fetching ${missing.length} / ${orcidIds.length} (concurrency ${ORCID_CONCURRENCY})`);
  let index = 0;
  let done = 0;
  let found = 0;
  const started = Date.now();
  async function worker() {
    while (index < missing.length) {
      const id = missing[index];
      index += 1;
      let item = { urls: [] };
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const data = await fetchJSON(`https://pub.orcid.org/v3.0/${id}/researcher-urls`);
          item.urls = (data?.["researcher-url"] || [])
            .map((row) => ({ name: row?.["url-name"] || "", url: safeUrl(row?.url?.value) }))
            .filter((row) => row.url);
          break;
        } catch (err) {
          if (attempt === 2) item.error = String(err?.message || err);
          else await sleep(600 * (attempt + 1));
        }
      }
      cache[id] = item;
      done += 1;
      if (item.urls.length) found += 1;
      if (done % 250 === 0) {
        writeJSON(cacheFile, cache);
        const minutes = ((Date.now() - started) / 60000).toFixed(1);
        console.log(`[orcid] ${done} / ${missing.length} · urls ${found} · ${minutes} min`);
      }
      if (!item.error) await sleep(40);
    }
  }
  await Promise.all(Array.from({ length: Math.max(1, ORCID_CONCURRENCY) }, worker));
  writeJSON(cacheFile, cache);
  console.log(`[orcid] done ${done} · urls ${found}`);
  return cache;
}

function cleanList(list, limit = 6) {
  return [...new Set((list || []).map((x) => String(x || "").trim()).filter(Boolean))].slice(0, limit);
}

function cleanScholarName(name) {
  return String(name || "").replace(/\s+\d{4}$/, "").trim();
}

const CN_PROVINCES = [
  ["shaanxi", "陕西"], ["shanxi", "山西"], ["inner mongolia", "内蒙古"], ["nei mongol", "内蒙古"],
  ["heilongjiang", "黑龙江"], ["liaoning", "辽宁"], ["jilin", "吉林"], ["hebei", "河北"],
  ["henan", "河南"], ["hubei", "湖北"], ["hunan", "湖南"], ["jiangsu", "江苏"], ["jiangxi", "江西"],
  ["anhui", "安徽"], ["fujian", "福建"], ["shandong", "山东"], ["guangdong", "广东"],
  ["guangxi", "广西"], ["hainan", "海南"], ["sichuan", "四川"], ["guizhou", "贵州"],
  ["yunnan", "云南"], ["xizang", "西藏"], ["tibet", "西藏"], ["gansu", "甘肃"], ["qinghai", "青海"],
  ["ningxia", "宁夏"], ["xinjiang", "新疆"], ["beijing", "北京"], ["shanghai", "上海"],
  ["tianjin", "天津"], ["chongqing", "重庆"], ["hong kong", "香港"], ["macau", "澳门"], ["taiwan", "台湾"],
  ["beijing", "北京"], ["nanjing", "江苏"], ["suzhou", "江苏"], ["wuxi", "江苏"], ["xuzhou", "江苏"],
  ["hangzhou", "浙江"], ["ningbo", "浙江"], ["wenzhou", "浙江"], ["wuhan", "湖北"], ["guangzhou", "广东"],
  ["shenzhen", "广东"], ["shantou", "广东"], ["foshan", "广东"], ["chengdu", "四川"], ["xian", "陕西"],
  ["changsha", "湖南"], ["harbin", "黑龙江"], ["dalian", "辽宁"], ["shenyang", "辽宁"], ["qingdao", "山东"],
  ["jinan", "山东"], ["zhengzhou", "河南"], ["hefei", "安徽"], ["fuzhou", "福建"], ["xiamen", "福建"],
  ["nanchang", "江西"], ["kunming", "云南"], ["guiyang", "贵州"], ["lanzhou", "甘肃"], ["taiyuan", "山西"],
  ["shijiazhuang", "河北"], ["changchun", "吉林"], ["guilin", "广西"], ["haikou", "海南"],
  ["xining", "青海"], ["yinchuan", "宁夏"], ["urumqi", "新疆"], ["hohhot", "内蒙古"],
];

function provinceFromInstitution(name) {
  const cleaned = String(name || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, " ").replace(/\s+/g, " ").trim();
  const value = ` ${cleaned} `;
  for (const [token, province] of CN_PROVINCES) {
    if (value.includes(` ${token} `)) return province;
  }
  return "";
}

async function main() {
  const source = readJSON(SOURCE);
  if (!source?.advisors?.length) throw new Error("advisor_directory_full.json missing");
  const localization = readJSON(LOCALIZATION, {}) || {};
  const institutions = localization.institutions || {};
  const provinces = localization.provinces || {};

  const [institutionPages, csrankings] = await Promise.all([
    loadInstitutionHomepages(),
    loadCsrankings(),
  ]);

  const orcidIds = [...new Set(source.advisors.map((a) => orcidBare(a.orcid)).filter(Boolean))];
  const orcidUrls = await loadOrcidHomepages(orcidIds);

  const groups = new Map();
  for (const raw of source.advisors) {
    const orcid = orcidBare(raw.orcid);
    const instKey = normalize(raw.institution);
    const key = orcid ? `orcid:${orcid}` : `name:${normalize(raw.name)}|${instKey}`;
    let group = groups.get(key);
    if (!group) {
      group = { key, orcid, name: raw.name, records: [] };
      groups.set(key, group);
    }
    group.records.push(raw);
  }

  const advisors = [];
  for (const group of groups.values()) {
    const records = group.records;
    const cs = group.orcid ? csrankings.byOrcid?.[group.orcid] : null;
    let primary = records[0];
    let institutionDetails = [];
    for (const raw of records) {
      const local = institutions[raw.institution] || {};
      const id = String(raw.institution_id || "").split("/").pop();
      institutionDetails.push({
        name: raw.institution || "",
        zh: local.zh || raw.institution || "",
        province: provinces[raw.province] || raw.province || local.province_zh || "",
        url: safeUrl(raw.institution_homepage) || safeUrl(institutionPages?.[id]?.url),
        id,
      });
    }
    if (cs?.affiliation) {
      const target = normalize(cs.affiliation);
      const exact = records.find((raw) => normalize(raw.institution) === target);
      const loose = records.find((raw) => normalize(raw.institution).includes(target) || target.includes(normalize(raw.institution)));
      if (exact || loose) primary = exact || loose;
    }
    const primaryIndex = records.indexOf(primary);
    const primaryLocal = institutions[primary.institution] || {};
    const primaryId = String(primary.institution_id || "").split("/").pop();
    const seenInst = new Set();
    const institutionsList = institutionDetails.filter((inst) => {
      const key = normalize(inst.name);
      if (!key || seenInst.has(key)) return false;
      seenInst.add(key);
      return true;
    });

    let homepage = "";
    let homepageSource = "";
    if (cs?.homepage) {
      const classified = classifyHomepage(cs.homepage, "CSRankings");
      if (classified) {
        homepage = classified.url;
        homepageSource = "CSRankings";
      }
    }
    if (!homepage && group.orcid) {
      const candidates = orcidUrls?.[group.orcid]?.urls || [];
      const ranked = candidates
        .map((row) => classifyHomepage(row.url, "ORCID"))
        .filter(Boolean)
        .sort((a, b) => {
          const score = (x) => {
            let n = 0;
            if (/\.edu|\.ac\./.test(x.url)) n += 3;
            if (/(faculty|people|profile|staff|homepage|~)/.test(x.url)) n += 2;
            if (x.label === "课题组主页") n += 1;
            return n;
          };
          return score(b) - score(a);
        });
      if (ranked[0]) {
        homepage = ranked[0].url;
        homepageSource = "ORCID";
      }
    }

    const first = records[0];
    const cited = Math.max(...records.map((r) => Number(r.cited_by_count) || 0));
    const works = Math.max(...records.map((r) => Number(r.works_count) || 0));
    const fields = cleanList(records.flatMap((r) => r.fields || []), 4);
    const keywords = cleanList(records.flatMap((r) => r.keywords || []), 4);
    const orderedInstitutions = [
      ...institutionsList.filter((inst) => normalize(inst.name) === normalize(primary.institution)),
      ...institutionsList.filter((inst) => normalize(inst.name) !== normalize(primary.institution)),
    ];
    const institutionNames = orderedInstitutions.slice(0, 3).map((inst) => inst.zh || inst.name).filter(Boolean);

    const province = provinces[primary.province] || primary.province || primaryLocal.province_zh || provinceFromInstitution(primary.institution) || "";
    advisors.push({
      name: cleanScholarName(cs?.name || group.name || first.name),
      institution: primary.institution || "",
      institutionZh: primaryLocal.zh || primary.institution || "",
      province,
      category: first.category || "",
      fields,
      keywords,
      cited,
      works,
      orcid: group.orcid ? `https://orcid.org/${group.orcid}` : "",
      homepage: homepage || "",
      homepageSource: homepageSource || "",
      institutionUrl: safeUrl(primary.institution_homepage) || safeUrl(institutionPages?.[primaryId]?.url) || institutionsList.find((inst) => inst.url)?.url || "",
      institutionNames,
      matchedInstitutions: records.length,
    });
  }

  advisors.sort((a, b) => b.cited - a.cited || b.works - a.works || a.name.localeCompare(b.name));

  writeJSON(OUT, advisors);
  const withHomepage = advisors.filter((a) => a.homepage).length;
  const withInstitution = advisors.filter((a) => a.institutionUrl).length;
  console.log(JSON.stringify({
    sourceRecords: source.advisors.length,
    uniqueScholars: advisors.length,
    withHomepage,
    withInstitution,
    bySource: {
      CSRankings: advisors.filter((a) => a.homepageSource === "CSRankings").length,
      ORCID: advisors.filter((a) => a.homepageSource === "ORCID").length,
    },
    output: OUT,
    bytes: fs.statSync(OUT).size,
  }, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
