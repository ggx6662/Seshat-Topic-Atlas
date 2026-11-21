import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COMP = path.resolve(HERE, "..");
const ROOT = path.resolve(COMP, "..");
const CACHE = path.join(HERE, ".cache");
const SOURCE = path.join(ROOT, "advisor_directory_full.json");
// 原来是写死的本机路径；改成相对仓库根，换电脑也能跑
const CACHED = path.resolve(HERE, "..", "..", ".cache_advisors.json");
const GEO = path.join(CACHE, "cached_institution_geo.json");
const OUT = path.join(CACHE, "advisor_source_combined.json");

const read = (file, fallback) => {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
};
const norm = (value) => String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
const orcidBare = (value) => {
  const match = String(value || "").match(/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])/i);
  return match ? match[1].toUpperCase() : "";
};

const provinceZh = {
  Anhui: "安徽", Beijing: "北京", Chongqing: "重庆", Fujian: "福建", Gansu: "甘肃", Guangdong: "广东",
  Guangxi: "广西", Guizhou: "贵州", Hainan: "海南", Hebei: "河北", Heilongjiang: "黑龙江", Henan: "河南",
  Hubei: "湖北", Hunan: "湖南", "Inner Mongolia": "内蒙古", "Nei Mongol": "内蒙古", Jiangsu: "江苏",
  Jiangxi: "江西", Jilin: "吉林", Liaoning: "辽宁", Ningxia: "宁夏", Qinghai: "青海", Shaanxi: "陕西",
  Shandong: "山东", Shanghai: "上海", Shanxi: "山西", Sichuan: "四川", Tianjin: "天津", Tibet: "西藏",
  Xizang: "西藏", Xinjiang: "新疆", Yunnan: "云南", Zhejiang: "浙江",
  "Hong Kong": "香港", "Hong Kong SAR": "香港", Macau: "澳门", Macao: "澳门", "Macao SAR": "澳门", Taiwan: "台湾",
};
const cnRegions = new Set(Object.values(provinceZh));

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
const codeZh = {
  CN: "中国", US: "美国", GB: "英国", DE: "德国", CA: "加拿大", AU: "澳大利亚", SG: "新加坡",
  JP: "日本", KR: "韩国", FR: "法国", CH: "瑞士", NL: "荷兰", SE: "瑞典", IT: "意大利",
  ES: "西班牙", BE: "比利时", DK: "丹麦", NO: "挪威", FI: "芬兰", AT: "奥地利", IL: "以色列",
  IN: "印度", BR: "巴西", NZ: "新西兰", IE: "爱尔兰", PL: "波兰", PT: "葡萄牙", GR: "希腊",
  TR: "土耳其", RU: "俄罗斯", MX: "墨西哥", AR: "阿根廷", CL: "智利", ZA: "南非", MY: "马来西亚",
  TH: "泰国", ID: "印度尼西亚", VN: "越南", PK: "巴基斯坦", SA: "沙特阿拉伯", AE: "阿联酋",
  EG: "埃及", IR: "伊朗", CZ: "捷克", HU: "匈牙利", RO: "罗马尼亚", UA: "乌克兰", HK: "香港",
  TW: "台湾", MO: "澳门",
};

const provinceTokens = [
  ["shaanxi", "陕西"], ["shanxi", "山西"], ["inner mongolia", "内蒙古"], ["nei mongol", "内蒙古"],
  ["heilongjiang", "黑龙江"], ["liaoning", "辽宁"], ["jilin", "吉林"], ["hebei", "河北"],
  ["henan", "河南"], ["hubei", "湖北"], ["hunan", "湖南"], ["jiangsu", "江苏"], ["jiangxi", "江西"],
  ["anhui", "安徽"], ["fujian", "福建"], ["shandong", "山东"], ["guangdong", "广东"],
  ["guangxi", "广西"], ["hainan", "海南"], ["sichuan", "四川"], ["guizhou", "贵州"],
  ["yunnan", "云南"], ["xizang", "西藏"], ["tibet", "西藏"], ["gansu", "甘肃"], ["qinghai", "青海"],
  ["ningxia", "宁夏"], ["xinjiang", "新疆"], ["beijing", "北京"], ["shanghai", "上海"],
  ["tianjin", "天津"], ["chongqing", "重庆"], ["hong kong", "香港"], ["macau", "澳门"], ["taiwan", "台湾"],
];
const cityTokens = [
  ["beijing", "北京"], ["shanghai", "上海"], ["tianjin", "天津"], ["chongqing", "重庆"],
  ["nanjing", "江苏"], ["suzhou", "江苏"], ["soochow", "江苏"], ["wuxi", "江苏"], ["xuzhou", "江苏"],
  ["yangzhou", "江苏"], ["zhenjiang", "江苏"], ["changzhou", "江苏"], ["nantong", "江苏"],
  ["hangzhou", "浙江"], ["ningbo", "浙江"], ["wenzhou", "浙江"], ["jiaxing", "浙江"], ["huzhou", "浙江"],
  ["shaoxing", "浙江"], ["taizhou", "浙江"], ["wuhan", "湖北"], ["jianghan", "湖北"], ["yichang", "湖北"],
  ["xiangyang", "湖北"], ["jingzhou", "湖北"], ["guangzhou", "广东"], ["shenzhen", "广东"],
  ["shantou", "广东"], ["foshan", "广东"], ["zhongkai", "广东"], ["dongguan", "广东"], ["zhuhai", "广东"],
  ["chengdu", "四川"], ["mianyang", "四川"], ["xian", "陕西"], ["xi'an", "陕西"], ["changsha", "湖南"],
  ["zhuzhou", "湖南"], ["xiangtan", "湖南"], ["hengzhou", "湖南"], ["heng yang", "湖南"],
  ["harbin", "黑龙江"], ["daqing", "黑龙江"], ["dalian", "辽宁"], ["shenyang", "辽宁"], ["jinzhou", "辽宁"],
  ["qingdao", "山东"], ["jinan", "山东"], ["yantai", "山东"], ["weifang", "山东"], ["qufu", "山东"],
  ["zhengzhou", "河南"], ["luoyang", "河南"], ["hefei", "安徽"], ["wuhu", "安徽"], ["bengbu", "安徽"],
  ["anqing", "安徽"], ["fuzhou", "福建"], ["xiamen", "福建"], ["quanzhou", "福建"], ["nanchang", "江西"],
  ["ganzhou", "江西"], ["jiujiang", "江西"], ["kunming", "云南"], ["dali", "云南"], ["lijiang", "云南"],
  ["guiyang", "贵州"], ["zunyi", "贵州"], ["lanzhou", "甘肃"], ["taiyuan", "山西"], ["shijiazhuang", "河北"],
  ["baoding", "河北"], ["tangshan", "河北"], ["qinhuangdao", "河北"], ["handan", "河北"],
  ["changchun", "吉林"], ["yanbian", "吉林"], ["guilin", "广西"], ["nanning", "广西"], ["haikou", "海南"],
  ["sanya", "海南"], ["xining", "青海"], ["yinchuan", "宁夏"], ["urumqi", "新疆"], ["karamay", "新疆"],
  ["hohhot", "内蒙古"], ["baotou", "内蒙古"], ["chifeng", "内蒙古"], ["shantou", "广东"],
];

function cnProvinceFromName(name) {
  const value = ` ${norm(name)} `;
  for (const [token, province] of provinceTokens) {
    if (value.includes(` ${token} `)) return province;
  }
  for (const [token, province] of cityTokens) {
    if (value.includes(` ${token} `)) return province;
  }
  return "";
}

function regionFor(row, geo) {
  if (geo?.countryCode === "CN" || row.country === "CN") {
    const fromGeo = provinceZh[geo?.region] || provinceZh[geo?.city] || "";
    const raw = String(row.province || "").trim();
    const fromRow = provinceZh[raw] || (cnRegions.has(raw) ? raw : "");
    return { province: fromGeo || fromRow || cnProvinceFromName(row.institution), country: "中国" };
  }
  const country = countryZh[geo?.country] || countryZh[row.country] || codeZh[row.country] || "";
  const raw = String(row.province || "").trim();
  const rowCountry = countryZh[raw] || codeZh[raw] || "";
  if (country || rowCountry) return { province: country || rowCountry, country: country || rowCountry };
  const province = cnProvinceFromName(row.institution);
  if (province) return { province, country: "中国" };
  return { province: "", country: "" };
}

function main() {
  const source = read(SOURCE);
  const cached = read(CACHED, { rows: [] }).rows || [];
  const geoCache = read(GEO, {});
  const regionFile = read(path.join(COMP, "site", "data", "institution_regions.json"), { entries: [] });
  const knownRegions = {};
  for (const entry of regionFile.entries || []) {
    for (const name of [entry.institution, entry.institutionZh]) {
      if (name) knownRegions[norm(name)] = { province: entry.province || "", country: entry.country || "中国" };
    }
  }
  if (!source?.advisors?.length) throw new Error("advisor_directory_full.json missing");
  if (!cached.length) throw new Error("cached advisors missing");

  const keys = new Set();
  for (const row of source.advisors) {
    const id = orcidBare(row.orcid);
    if (id) keys.add(`orcid:${id}`);
    keys.add(`name:${norm(row.name)}|inst:${norm(row.institution)}`);
  }

  const added = [];
  const seen = new Set();
  for (const row of cached) {
    const id = orcidBare(row.orcid);
    const key = id ? `orcid:${id}` : `name:${norm(row.name)}|inst:${norm(row.institution)}`;
    if (keys.has(key) || seen.has(key)) continue;
    seen.add(key);
    const geo = geoCache[norm(row.institution)];
    let region = regionFor(row, geo);
    if (!region.province && knownRegions[norm(row.institution)]) region = knownRegions[norm(row.institution)];
    const categories = Array.isArray(row.categories) ? row.categories.filter(Boolean) : [];
    const category = row.category || categories[0] || "";
    added.push({
      name: row.name,
      institution: row.institution,
      lab: row.lab || "",
      category,
      categories: categories.length ? categories : category ? [category] : [],
      fields: Array.isArray(row.fields) ? row.fields.filter(Boolean) : [],
      keywords: Array.isArray(row.keywords) ? row.keywords.filter(Boolean) : [],
      works_count: Number(row.works_count) || 0,
      cited_by_count: Number(row.cited_by_count) || 0,
      homepage: "",
      source: row.source || "arXiv + OpenAlex",
      verified: false,
      institution_id: geo?.id ? `https://openalex.org/${geo.id}` : "",
      institution_homepage: geo?.url || "",
      province: region.province,
      city: geo?.city || "",
      orcid: row.orcid || "",
      mapping: "",
      _complete: Boolean(row._complete),
    });
  }

  const combined = { ...source, advisors: [...source.advisors, ...added] };
  fs.writeFileSync(OUT, JSON.stringify(combined));

  const countries = added.reduce((map, row) => {
    const key = row.province || "待核验";
    map[key] = (map[key] || 0) + 1;
    return map;
  }, {});
  const top = [...added].sort((a, b) => b.cited_by_count - a.cited_by_count).slice(0, 15)
    .map((row) => `${row.name} · ${row.institution} · ${row.cited_by_count}`);
  console.log(JSON.stringify({
    source: source.advisors.length,
    cached: cached.length,
    added: added.length,
    combined: combined.advisors.length,
    withGeo: added.filter((row) => row.institution_id).length,
    countries: Object.entries(countries).sort((a, b) => b[1] - a[1]).slice(0, 25),
    top,
    output: OUT,
    bytes: fs.statSync(OUT).size,
  }, null, 2));
}

main();
