import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.join(path.resolve(HERE, ".."), "site", "data");
const CATALOGUE = path.join(HERE, "ccf2026_catalogue.json");
const VENUES = path.join(DATA, "venues.json");

const read = (file, fallback) => {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
};
const norm = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "");
const stripPrefix = (name) => String(name || "").replace(/^(ieee\/acm|ieee|acm)\s+/i, "");

const OFFICIAL = {
  AAAI: "https://aaai.org/conference/aaai/",
  NeurIPS: "https://neurips.cc/",
  ICML: "https://icml.cc/",
  ICLR: "https://iclr.cc/",
  CVPR: "https://cvpr.thecvf.com/",
  ICCV: "https://iccv.thecvf.com/",
  ECCV: "https://eccv.ecva.net/",
  ACL: "https://www.aclweb.org/",
  EMNLP: "https://emnlp.org/",
  NAACL: "https://naacl.org/",
  IJCAI: "https://www.ijcai.org/",
  AISTATS: "https://aistats.org/",
  UAI: "https://www.auai.org/",
  COLT: "https://www.learningtheory.org/",
  SIGIR: "https://sigir.org/",
  SIGKDD: "https://kdd.org/",
  KDD: "https://kdd.org/",
  SIGMOD: "https://sigmod.org/",
  VLDB: "https://www.vldb.org/",
  ICDE: "https://icde.ieee.org/",
  WWW: "https://www.thewebconf.org/",
  WSDM: "https://www.wsdm-conference.org/",
  CIKM: "https://www.cikmconference.org/",
  RecSys: "https://recsys.acm.org/",
  CHI: "https://chi.acm.org/",
  UIST: "https://uist.acm.org/",
  CSCW: "https://cscw.acm.org/",
  "SIGGRAPH": "https://www.siggraph.org/",
  "SIGGRAPH Asia": "https://asia.siggraph.org/",
  "ACM MM": "https://www.acmmm.org/",
  ICRA: "https://www.ieee-ras.org/conferences-workshops/fully-sponsored/icra",
  IROS: "https://iros.org/",
  ISCA: "https://iscaconf.org/",
  MICRO: "https://www.microarch.org/",
  HPCA: "https://hpca-conf.org/",
  ASPLOS: "https://asplos-conference.org/",
  SC: "https://sc-conference.org/",
  PPoPP: "https://ppopp.org/",
  FAST: "https://www.usenix.org/conference/fast",
  OSDI: "https://www.usenix.org/conference/osdi",
  SOSP: "https://sosp.org/",
  EuroSys: "https://www.eurosys.org/",
  NSDI: "https://www.usenix.org/conference/nsdi",
  SIGCOMM: "https://www.sigcomm.org/",
  MobiCom: "https://www.sigmobile.org/mobicom/",
  INFOCOM: "https://infocom.ieee.org/",
  CCS: "https://www.sigsac.org/ccs.html",
  "S&P": "https://www.ieee-security.org/TC/SP-Index.html",
  "USENIX Security": "https://www.usenix.org/conference/usenixsecurity",
  NDSS: "https://www.ndss-symposium.org/",
  CRYPTO: "https://iacr.org/conferences/crypto/",
  EUROCRYPT: "https://iacr.org/conferences/eurocrypt/",
  ICSE: "https://conf.researchr.org/series/icse",
  FSE: "https://conf.researchr.org/series/fse",
  ASE: "https://conf.researchr.org/series/ase",
  ISSTA: "https://conf.researchr.org/series/issta",
  OOPSLA: "https://oopsla.acm.org/",
  PLDI: "https://pldi.net/",
  POPL: "https://popl.sigplan.org/",
  ICFP: "https://icfpconference.org/",
  CAV: "http://i-cav.org/",
  TACAS: "https://tacas.evolver.ch/",
  STOC: "https://acm-stoc.org/",
  FOCS: "https://focs.computer.org/",
  SODA: "https://www.siam.org/conferences/cm/conference/soda",
  ICALP: "https://icalp.org/",
  LICS: "https://lics.siglog.org/",
  DAC: "https://www.dac.com/",
  DATE: "https://www.date-conference.com/",
  ICCAD: "https://iccad.com/",
  FPGA: "https://www.fpga.org/",
  CGO: "https://cgo-conference.org/",
  PACT: "https://pactconf.org/",
  IPDPS: "https://ipdps.org/",
  HPDC: "https://www.hpdc.org/",
  ICDCS: "https://icdcs.org/",
  SIGMETRICS: "https://www.sigmetrics.org/",
  VEE: "https://veekonf.org/",
  RTSS: "https://rtss.org/",
  EMSOFT: "https://esweek.org/",
  HSCC: "https://hscc-conference.org/",
  ICCPS: "https://iccps.acm.org/",
  IPSN: "https://ipsn.acm.org/",
  MobiSys: "https://www.sigmobile.org/mobisys/",
  SenSys: "https://sensys.acm.org/",
  IMC: "https://conferences.sigcomm.org/imc/",
  CoNEXT: "https://conferences2.sigcomm.org/co-next/",
  HotNets: "https://hotnets.sigcomm.org/",
  PODC: "https://www.podc.org/",
  SPAA: "https://spaa.acm.org/",
  DISC: "https://www.disc-conference.org/",
  TPAMI: "https://www.computer.org/csdl/journal/tp",
  IJCV: "https://link.springer.com/journal/11263",
  JMLR: "https://www.jmlr.org/",
  AI: "https://www.sciencedirect.com/journal/artificial-intelligence",
  JAIR: "https://www.jair.org/",
  TNNLS: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=5962385",
  TIP: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=83",
  TMI: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=42",
  TVCG: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=2945",
  TOG: "https://dl.acm.org/journal/tog",
  TOSEM: "https://dl.acm.org/journal/tosem",
  TSE: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=32",
  TC: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=12",
  TPDS: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=71",
  TKDE: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=69",
  VLDBJ: "https://link.springer.com/journal/778",
  TOIS: "https://dl.acm.org/journal/tois",
  TIST: "https://dl.acm.org/journal/tist",
  TOPS: "https://dl.acm.org/journal/tops",
  TACO: "https://dl.acm.org/journal/taco",
  TOCS: "https://dl.acm.org/journal/tocs",
  TOS: "https://dl.acm.org/journal/tos",
  TCAD: "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=43",
};

const ALIASES = {
  kdd: "SIGKDD",
  "financial cryptography": "FC",
  "ieee s&p": "S&P",
  "ieee symposium on security and privacy": "S&P",
  "usenix atc": "ACM SIGOPS ATC",
  "ieee csf": "CSFW",
};

const SECTION_SHORT = new Map([
  ["计算机体系结构/并行与分布计算/存储系统", "体系结构/并行与存储"],
  ["计算机网络", "计算机网络"],
  ["网络与信息安全", "网络与信息安全"],
  ["软件工程/系统软件/程序设计语言", "软件工程/系统软件/PL"],
  ["数据库/数据挖掘/内容检索", "数据库/数据挖掘"],
  ["计算机科学理论", "计算机科学理论"],
  ["计算机图形学与多媒体", "图形学与多媒体"],
  ["人工智能", "人工智能"],
  ["人机交互与普适计算", "人机交互/普适计算"],
  ["交叉/综合/新兴", "交叉/综合/新兴"],
]);

const shortSection = (section) => {
  const raw = String(section || "").trim();
  return (SECTION_SHORT.get(raw) || raw).replace(/\s*\/\s*/g, " / ");
};
const linkLabel = (url) => (/dblp\./i.test(url) ? "DBLP 目录页" : "官网");
const officialFor = (record) => {
  if (record.abbr === "FSE" && /Fast Software Encryption/i.test(record.fullName)) return "https://fse.iacr.org/";
  return OFFICIAL[record.abbr] || OFFICIAL[record.fullName] || record.url || "";
};

function main() {
  const catalogue = read(CATALOGUE, []);
  const current = read(VENUES, []);
  const base = current.filter((venue) => venue.metaSource !== "CCF 2026 catalogue");
  if (!Array.isArray(catalogue) || !catalogue.length) throw new Error("CCF 2026 catalogue missing");
  if (!Array.isArray(current) || !current.length) throw new Error("venues.json missing");

  const merged = new Map();
  for (const record of catalogue) {
    const key = `${norm(record.fullName)}|${record.type}`;
    if (!merged.has(key)) {
      merged.set(key, { ...record, sections: [record.section] });
    } else {
      const target = merged.get(key);
      if (!target.sections.includes(record.section)) target.sections.push(record.section);
    }
  }
  const records = [...merged.values()].map((record) => ({
    ...record,
    section: record.sections.map(shortSection).join(" / "),
  }));

  const byAbbr = new Map();
  const byFull = new Map();
  for (const record of records) {
    if (record.abbr) byAbbr.set(norm(record.abbr), record);
    byFull.set(norm(record.fullName), record);
  }

  function findRecord(venue) {
    const names = [venue.name, stripPrefix(venue.name)].filter(Boolean);
    for (const name of names) {
      const key = norm(name);
      const alias = ALIASES[String(name).toLowerCase().trim()];
      if (alias && byAbbr.has(norm(alias))) return byAbbr.get(norm(alias));
      if (byAbbr.has(key)) return byAbbr.get(key);
      if (byFull.has(key)) return byFull.get(key);
    }
    const target = norm(stripPrefix(venue.name));
    if (target.length >= 3) {
      for (const [full, record] of byFull) {
        if (full.startsWith(target) || target.startsWith(full)) return record;
      }
    }
    return null;
  }

  const used = new Set();
  const recordKey = (record) => `${record.abbr}|${record.fullName}|${record.type}|${record.section}`;
  let matched = 0;
  let corrected = 0;
  const unmatched = [];
  const matchedGroups = new Map();

  for (const venue of base) {
    const record = findRecord(venue);
    if (!record) {
      venue.ccf = "";
      venue.ccfEdition = "";
      venue.ccfNote = "未收录于 CCF 2026 推荐目录";
      delete venue.ccfSource;
      unmatched.push(venue.name);
      continue;
    }
    const key = recordKey(record);
    used.add(key);
    if (!matchedGroups.has(key)) matchedGroups.set(key, []);
    matchedGroups.get(key).push(venue);
    matched += 1;
    if (venue.ccf !== record.rank) corrected += 1;
    venue.ccf = record.rank;
    venue.ccfEdition = "2026";
    venue.ccfSource = "CCF 2026 推荐目录（第七版）";
    venue.fullName = record.fullName;
    venue.section = shortSection(record.section);
    venue.type = record.type || venue.type;
    delete venue.ccfNote;
    if (!venue.url && record.url) {
      venue.url = record.url;
    }
    if (venue.url) venue.linkLabel = linkLabel(venue.url);
  }

  const dropped = new Set();
  for (const group of matchedGroups.values()) {
    if (group.length < 2) continue;
    const ranked = [...group].sort((a, b) => {
      const aAdded = a.metaSource === "CCF 2026 catalogue" ? 1 : 0;
      const bAdded = b.metaSource === "CCF 2026 catalogue" ? 1 : 0;
      if (aAdded !== bAdded) return aAdded - bAdded;
      const aDblp = /dblp\./i.test(a.url) ? 1 : 0;
      const bDblp = /dblp\./i.test(b.url) ? 1 : 0;
      if (aDblp !== bDblp) return aDblp - bDblp;
      return String(a.name).length - String(b.name).length;
    });
    for (const venue of ranked.slice(1)) dropped.add(venue);
  }
  const keptCurrent = base.filter((venue) => !dropped.has(venue));

  const additions = [];
  for (const record of records) {
    if (used.has(recordKey(record))) continue;
    const name = record.abbr || record.fullName;
    const url = officialFor(record);
    const short = shortSection(record.section);
    additions.push({
      name,
      fullName: record.fullName,
      type: record.type,
      ccf: record.rank,
      ccfEdition: "2026",
      ccfSource: "CCF 2026 推荐目录（第七版）",
      country: "",
      field: short,
      section: short,
      intro: record.abbr
        ? `${record.fullName}。CCF 2026 推荐 ${record.rank} 类${record.type}，归入「${short}」。`
        : `CCF 2026 推荐 ${record.rank} 类${record.type}，归入「${short}」。`,
      url,
      linkLabel: url ? linkLabel(url) : "",
      metaSource: "CCF 2026 catalogue",
    });
  }

  const nameCount = new Map();
  for (const venue of [...keptCurrent, ...additions]) {
    const key = `${venue.name}|${venue.type}`;
    nameCount.set(key, (nameCount.get(key) || 0) + 1);
  }
  for (const venue of additions) {
    const key = `${venue.name}|${venue.type}`;
    if (nameCount.get(key) > 1) {
      venue.name = `${venue.name}（${venue.section}）`;
    }
  }

  const rankOrder = { A: 0, B: 1, C: 2, "": 3 };
  const rows = [...keptCurrent, ...additions].sort((a, b) =>
    (rankOrder[a.ccf] ?? 3) - (rankOrder[b.ccf] ?? 3)
    || String(a.type).localeCompare(String(b.type), "zh")
    || String(a.field).localeCompare(String(b.field), "zh")
    || String(a.name).localeCompare(String(b.name), "zh"),
  );

  fs.writeFileSync(VENUES, JSON.stringify(rows));
  const byRank = rows.reduce((map, row) => {
    const key = row.ccf || "none";
    map[key] = (map[key] || 0) + 1;
    return map;
  }, {});
  console.log(JSON.stringify({
    output: VENUES,
    total: rows.length,
    existing: keptCurrent.length,
    matched,
    corrected,
    added: additions.length,
    unmatched,
    byRank,
    byType: rows.reduce((map, row) => {
      map[row.type] = (map[row.type] || 0) + 1;
      return map;
    }, {}),
    dblpLinks: rows.filter((row) => /dblp\./i.test(row.url)).length,
  }, null, 2));
}

main();
