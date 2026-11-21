import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SOURCE = join(ROOT, "advisor_directory_full.json");
const ADVISORS = join(ROOT, "competition", "site", "data", "advisors.json");
const OUT = join(ROOT, "competition", "site", "data", "institution_regions.json");
const CACHE = join(ROOT, "competition", "scripts", ".cache", "institution_geo.json");
const MAILTO = process.env.OPENALEX_MAILTO || "research@example.org";
const CONCURRENCY = 6;
const DRY = process.argv.includes("--dry-run");

const provinceZh = {
  Anhui: "安徽", Beijing: "北京", Chongqing: "重庆", Fujian: "福建", Gansu: "甘肃", Guangdong: "广东",
  Guangxi: "广西", Guizhou: "贵州", Hainan: "海南", Hebei: "河北", Heilongjiang: "黑龙江", Henan: "河南",
  Hubei: "湖北", Hunan: "湖南", "Inner Mongolia": "内蒙古", "Nei Mongol": "内蒙古", Jiangsu: "江苏",
  Jiangxi: "江西", Jilin: "吉林", Liaoning: "辽宁", Ningxia: "宁夏", Qinghai: "青海", Shaanxi: "陕西",
  Shandong: "山东", Shanghai: "上海", Shanxi: "山西", Sichuan: "四川", Tianjin: "天津", Tibet: "西藏",
  Xizang: "西藏", Xinjiang: "新疆", Yunnan: "云南", Zhejiang: "浙江",
  "Hong Kong": "香港", "Hong Kong SAR": "香港", Macau: "澳门", Macao: "澳门", "Macao SAR": "澳门", Taiwan: "台湾",
};

const countryZh = {
  China: "中国", "United States": "美国", "United Kingdom": "英国", Germany: "德国", Canada: "加拿大",
  Australia: "澳大利亚", Singapore: "新加坡", Japan: "日本", "South Korea": "韩国", Korea: "韩国",
  France: "法国", Switzerland: "瑞士", Netherlands: "荷兰", Sweden: "瑞典", Italy: "意大利",
  Spain: "西班牙", Belgium: "比利时", Denmark: "丹麦", Norway: "挪威", Finland: "芬兰",
  Austria: "奥地利", Israel: "以色列", India: "印度", Brazil: "巴西", "New Zealand": "新西兰",
  Ireland: "爱尔兰", Poland: "波兰", Portugal: "葡萄牙", Greece: "希腊", Turkey: "土耳其",
  Russia: "俄罗斯", Mexico: "墨西哥", Argentina: "阿根廷", Chile: "智利", "South Africa": "南非",
  Malaysia: "马来西亚", Thailand: "泰国", Indonesia: "印度尼西亚", Vietnam: "越南", Pakistan: "巴基斯坦",
  "Saudi Arabia": "沙特阿拉伯", "United Arab Emirates": "阿联酋", Egypt: "埃及", Iran: "伊朗",
  Czechia: "捷克", "Czech Republic": "捷克", Hungary: "匈牙利", Romania: "罗马尼亚", Ukraine: "乌克兰",
  "Hong Kong": "香港", Taiwan: "台湾", Macau: "澳门", Macao: "澳门",
};

const norm = (s) => String(s || "").trim().toLowerCase().replace(/\s+/g, " ");
const bareId = (url) => String(url || "").split("/").filter(Boolean).pop() || "";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function readJson(path, fallback) {
  try { return JSON.parse(await readFile(path, "utf8")); } catch { return fallback; }
}

async function writeJson(path, data) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, JSON.stringify(data));
}

async function fetchJson(url) {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const res = await fetch(url, { headers: { "User-Agent": "topic-atlas-region-enrichment/1.0" } });
    if (res.ok) return res.json();
    if (res.status !== 429 || attempt === 3) return { __error: `HTTP ${res.status}` };
    await sleep(3000 * (attempt + 1));
  }
  return { __error: "retry exhausted" };
}

async function fetchInstitution(id) {
  const url = `https://api.openalex.org/institutions/${encodeURIComponent(id)}?mailto=${encodeURIComponent(MAILTO)}`;
  const j = await fetchJson(url);
  if (!j || j.__error) return { error: j?.__error || "fetch failed" };
  return {
    name: j.display_name || "",
    city: j.geo?.city || "",
    region: j.geo?.region || "",
    countryCode: j.country_code || j.geo?.country_code || "",
    country: j.geo?.country || "",
    lat: j.geo?.latitude ?? null,
    lon: j.geo?.longitude ?? null,
    ror: bareId(j.ids?.ror),
  };
}

async function fetchByName(name) {
  const url = `https://api.openalex.org/institutions?search=${encodeURIComponent(name)}&per-page=5&mailto=${encodeURIComponent(MAILTO)}`;
  const j = await fetchJson(url);
  if (!j || j.__error) return null;
  const exact = (j.results || []).find((r) => norm(r.display_name) === norm(name));
  if (!exact) return null;
  return fetchInstitution(bareId(exact.id));
}

function regionFromGeo(geo) {
  if (!geo || geo.error) return null;
  if (geo.countryCode === "CN") {
    const province = provinceZh[geo.region] || provinceZh[geo.city] || "";
    return province ? { province, country: "中国" } : null;
  }
  const country = countryZh[geo.country] || countryZh[geo.countryCode] || "其他国家/地区";
  return { province: "", country };
}

function main() {
  return (async () => {
    const source = await readJson(SOURCE, {});
    const advisors = await readJson(ADVISORS, []);
    if (!Array.isArray(advisors) || !advisors.length) throw new Error("advisors.json missing");

    const idByName = new Map();
    for (const a of source.advisors || []) {
      const key = norm(a.institution);
      const id = bareId(a.institution_id);
      if (key && id && !idByName.has(key)) idByName.set(key, id);
    }
    const zhByName = new Map();
    for (const a of source.advisors || []) {
      const key = norm(a.institution);
      if (key && !zhByName.has(key) && a.institution) zhByName.set(key, a.institution);
    }

    const missing = new Map();
    for (const a of advisors) {
      if (String(a.province || "").trim()) continue;
      const key = norm(a.institution);
      if (!key) continue;
      if (!missing.has(key)) missing.set(key, { key, name: a.institution, zh: a.institutionZh || "", count: 0 });
      missing.get(key).count += 1;
    }
    console.log(`[geo] ${advisors.length} advisors · ${missing.size} schools without region`);

    const cache = await readJson(CACHE, {});
    const targets = [...missing.values()];
    let done = 0;
    let resolved = 0;

    async function worker(queue) {
      while (queue.length) {
        const item = queue.shift();
        let geo = cache[item.key];
        if (geo?.error) geo = null;
        if (!geo) {
          const id = idByName.get(item.key);
          geo = id ? await fetchInstitution(id) : null;
          if (!geo) geo = await fetchByName(item.name);
          cache[item.key] = geo || { error: "not_found" };
          if (done % 25 === 0) await writeJson(CACHE, cache);
          await sleep(60);
        }
        const region = regionFromGeo(geo);
        if (region) {
          item.region = region;
          resolved += 1;
        }
        done += 1;
        if (done % 50 === 0) console.log(`[geo] ${done} / ${targets.length} · resolved ${resolved}`);
      }
    }
    const queue = [...targets];
    await Promise.all(Array.from({ length: CONCURRENCY }, () => worker(queue)));
    await writeJson(CACHE, cache);

    const resolvedByKey = new Map();
    for (const item of targets) if (item.region) resolvedByKey.set(item.key, item);

    let updated = 0;
    for (const a of advisors) {
      if (String(a.province || "").trim()) continue;
      const item = resolvedByKey.get(norm(a.institution));
      if (!item) continue;
      a.province = item.region.province || "";
      a.country = item.region.country || "";
      const geo = cache[item.key] || {};
      if (geo.city) a.institutionCity = geo.city;
      if (geo.ror) a.institutionRor = geo.ror;
      a.regionSource = "OpenAlex institution geo";
      updated += 1;
    }

    const out = {
      generatedAt: new Date().toISOString().slice(0, 10),
      source: "OpenAlex institutions (geo.region / geo.country / ROR)",
      checked: targets.length,
      resolved: resolvedByKey.size,
      entries: targets
        .filter((t) => t.region)
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
        .map((t) => ({
          institution: t.name,
          institutionZh: t.zh,
          province: t.region.province,
          country: t.region.country,
          city: cache[t.key]?.city || "",
          ror: cache[t.key]?.ror || "",
          advisors: t.count,
        })),
    };
    console.log(`[geo] resolved ${resolvedByKey.size} / ${targets.length} schools · ${updated} advisors updated`);
    if (DRY) return;
    await writeJson(ADVISORS, advisors);
    await writeJson(OUT, out);
    console.log(`[geo] wrote ${ADVISORS}`);
    console.log(`[geo] wrote ${OUT}`);
  })();
}

main().catch((e) => { console.error(e); process.exit(1); });
