import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COMP = path.resolve(HERE, "..");
const ROOT = path.resolve(COMP, "..");
const DATA = path.join(COMP, "site", "data");
const DIRS = path.join(DATA, "directions");
const CACHE = path.join(HERE, ".cache");

const read = (file, fallback = null) => {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
};
const write = (file, data) => fs.writeFileSync(file, JSON.stringify(data));
const normalize = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "");
const safeUrl = (value) => {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? url.href.replace(/\/+$/, "") : "";
  } catch { return ""; }
};

const BAD_HOSTS = [
  "scholar.google.", "researchgate.net", "linkedin.com", "facebook.com", "twitter.com", "x.com",
  "youtube.com", "youtu.be", "wikipedia.org", "scopus.com", "webofscience.com", "semanticscholar.org",
  "dblp.org", "arxiv.org", "doi.org", "orcid.org", "google.com", "bing.com", "baidu.com",
];

function classifyHomepage(raw) {
  const url = safeUrl(raw);
  if (!url) return null;
  let host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch { return null; }
  if (BAD_HOSTS.some((bad) => host.includes(bad))) return null;
  const pathName = (() => { try { return new URL(url).pathname.toLowerCase(); } catch { return ""; } })();
  const academic = /(^|\.)(edu|ac)\.[a-z]{2,}$/.test(host) || /\.edu\./.test(host) || /\.ac\./.test(host);
  const profileLike = /(~|homepage|home-page|people|person|profile|faculty|staff|member|group|lab|team|index)/.test(pathName);
  if (pathName === "/" && !profileLike && !/(lab|group|home|page|site)/.test(host)) return null;
  if (!academic && !profileLike) return null;
  return url;
}

async function main() {
  const directions = fs.readdirSync(DIRS).filter((f) => f.endsWith(".json"));
  const names = new Set();
  for (const file of directions) {
    const d = read(path.join(DIRS, file));
    for (const a of d?.advisors || []) if (a.institution) names.add(a.institution);
  }

  const source = read(path.join(ROOT, "advisor_directory_full.json"))?.advisors || [];
  const instCache = read(path.join(CACHE, "institution_homepages.json"), {}) || {};
  const instByName = {};
  for (const a of source) {
    const id = String(a.institution_id || "").split("/").pop();
    const url = safeUrl(instCache?.[id]?.url);
    if (a.institution && url) instByName[normalize(a.institution)] = url;
  }

  let institutionFilled = 0;

  const full = read(path.join(DATA, "advisors.json"), []) || [];
  const byName = new Map();
  for (const a of full) {
    const key = normalize(a.name);
    if (!key) continue;
    if (!byName.has(key)) byName.set(key, []);
    byName.get(key).push(a);
  }
  const cs = read(path.join(CACHE, "csrankings.json"))?.byOrcid || {};
  const csByName = new Map();
  for (const [orcid, row] of Object.entries(cs)) {
    const key = normalize(row?.name);
    if (!key) continue;
    if (!csByName.has(key)) csByName.set(key, []);
    csByName.get(key).push({ ...row, orcid });
  }

  let homepageFilled = 0;
  let orcidFilled = 0;
  const instSimilar = (a, b) => {
    const x = normalize(a); const y = normalize(b);
    return Boolean(x && y && (x === y || x.includes(y) || y.includes(x)));
  };
  const pickFull = (name, institution) => {
    const rows = byName.get(normalize(name)) || [];
    return rows.find((r) => instSimilar(r.institution, institution)) || null;
  };
  const pickCs = (name, institution) => {
    const rows = csByName.get(normalize(name)) || [];
    return rows.find((r) => instSimilar(r.affiliation, institution)) || (rows.length === 1 ? rows[0] : null);
  };
  const academicRoot = (raw) => {
    let host = "";
    try { host = new URL(raw).hostname.toLowerCase(); } catch { return ""; }
    const labels = host.split(".");
    const edu = labels.lastIndexOf("edu");
    if (edu > 0) return labels.slice(edu - 1).join(".");
    const ac = labels.lastIndexOf("ac");
    if (ac > 0 && ac < labels.length - 1) return labels.slice(ac - 1).join(".");
    return "";
  };

  for (const file of directions) {
    const filePath = path.join(DIRS, file);
    const d = read(filePath);
    let changed = false;
    for (const a of d?.advisors || []) {
      if (!a.institutionUrl) {
        const url = instByName[normalize(a.institution)];
        if (url) { a.institutionUrl = url; institutionFilled += 1; changed = true; }
      }
      const matched = pickFull(a.name, a.institution);
      if (!a.institutionUrl && matched?.institutionUrl) {
        a.institutionUrl = matched.institutionUrl;
        institutionFilled += 1;
        changed = true;
      }
      if (!a.homepage) {
        const csHit = pickCs(a.name, a.institution);
        const csUrl = csHit ? classifyHomepage(csHit.homepage) : "";
        if (csUrl) {
          a.homepage = csUrl; a.homepageSource = "CSRankings"; homepageFilled += 1; changed = true;
        } else if (matched?.homepage) {
          a.homepage = matched.homepage; a.homepageSource = matched.homepageSource || "ORCID"; homepageFilled += 1; changed = true;
        }
      }
      if (!a.orcid && matched?.orcid) {
        a.orcid = matched.orcid; orcidFilled += 1; changed = true;
      }
      if (!a.institutionUrl && a.homepage && a.homepageSource === "CSRankings") {
        const root = academicRoot(a.homepage);
        if (root) { a.institutionUrl = `https://${root}`; institutionFilled += 1; changed = true; }
      }
    }
    if (changed) fs.writeFileSync(filePath, JSON.stringify(d, null, 2));
  }

  console.log(JSON.stringify({ institutionFilled, homepageFilled, orcidFilled }, null, 2));
}

main();
