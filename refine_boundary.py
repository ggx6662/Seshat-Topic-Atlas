#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用真实发表 venue 做学科边界的最终裁决。

为什么需要这一步
----------------
关键词判据做了两轮，实测都有明显错误：

  第一版（按主题占比）：误删 Songtao Liu（YOLOX 作者）等 24%
  第二版（强信号优先）：仍误删
    - Yang Yu   → IEEE Euro S&P / TRNG 硬件安全，是计算机安全
    - Fang Wang → IEEE TFS / T-Cybernetics，是智能控制/神经网络

**论文发在哪，比主题名靠谱得多**。所以最终判据：

  1. 先按关键词初判（快，但会错）
  2. 对「准备剔除」的人，用 ORCID 拉真实发表 venue
  3. 若 venue 里出现明确的计算机 venue → **翻案，保留**
  4. 拉不到数据的 → 保守保留（宁可多留，不可误删）

依赖 OpenAlex API（设置 OPENALEX_API_KEY）。不联网时退化为纯关键词判据。

用法
----
python refine_boundary.py --limit 100     # 先跑 100 个看效果
python refine_boundary.py                 # 全量（约 800+ 次请求）
python refine_boundary.py --dry-run       # 只统计，不写文件
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import remap_advisors as R  # noqa: E402

FULL = HERE / "advisor_directory_full.json"
BACKUP = HERE / "backup" / "advisor_directory_full.json.bak"
API = "https://api.openalex.org"
API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()

# 明确的计算机 venue：出现任一即判定「这人做计算机」
# 注意：不能放 "computational" 这类宽泛词 —— 它会把
# Polish Journal of Environmental Studies、Computational Economics
# 之类的非计算机期刊也算成计算机。必须用具体 venue 名。
CS_VENUE_PATTERNS = [
    # 视觉 / 学习 / NLP 顶会
    " cvpr", "cvpr ", "iccv", "eccv", "neurips", "nips ", "icml", "iclr",
    "aaai", "ijcai", " acl", "emnlp", "naacl", "coling", "conll",
    "sigir", "sigdial", "kdd", "wsdm", "cikm", "recsys", "www ",
    # 系统 / 安全 / 软件 顶会
    "sosp", "osdi", "nsdi", "sigcomm", "mobicom", " infocom",
    "computer security", "usenix security", "ndss", "ieee symposium on security",
    "eurosp", "euros&p", "ccs ", "acm ccs",
    "pldi", "popl", "oopsla", "icse", "fse", "ase ", "issta",
    "sigmod", "vldb", "icde", "micro", "isca", "asplos", "hpca",
    "siggraph", " chi", " chi ", "uist", "cscw",
    # 明确带计算机学科名的期刊
    "pattern analysis and machine intelligence", "pattern recognition",
    "computer vision", "image processing", "neural networks",
    "ieee transactions on neural", "ieee transactions on cybernetics",
    "ieee transactions on fuzzy", "artificial intelligence",
    "knowledge and data engineering", "information systems",
    "information retrieval", "natural language", "machine learning",
    "computational intelligence", "neurocomputing", "expert systems",
    "software engineering", "programming languages", "operating systems",
    "computer networks", "computer communications", "computer-aided",
    "computers & security", "computers and security", "computer journal",
    "digital signal processing", "signal processing letters",
    "multimedia", "image and vision computing", "computing and",
    "informatica", "journal of systems and software",
    "empirical software engineering", "automated software engineering",
    "computer standards", "future generation computer",
    "concurrency and computation", "parallel and distributed",
    "distributed computing", "cloud computing", "big data",
    "engineering informatics", "computing and informatics", "applied intelligence",
    "intelligent systems", "information sciences", "data & knowledge",
]

# 这些词出现时，「CS_VENUE_PATTERNS」的匹配不算数（硬件/光学/材料领域的同名期刊）
FALSE_FRIEND = [
    "optical", "photonic", "laser", "optics", "optoelectronic", "semiconductor",
    "circuits and systems ii", "materials", "physics", "environmental",
    "economics", "metrology", "measurement science",
]


def _clean(venue):
    return (venue or "").lower()


def venue_is_cs(venues):
    """venue 列表里是否出现明确的计算机发表场所。"""
    for v in venues:
        low = _clean(v)
        if not low:
            continue
        if any(ff in low for ff in FALSE_FRIEND):
            continue
        if any(p in low for p in CS_VENUE_PATTERNS):
            return True
    return False


def fetch_venues(orcid, limit=5, timeout=20, retries=3):
    if not API_KEY or not orcid:
        return []
    params = {
        "filter": "authorships.author.orcid:" + orcid.replace("https://orcid.org/", ""),
        "sort": "cited_by_count:desc",
        "per-page": str(limit),
        "select": "display_name,publication_year,primary_location",
        "api_key": API_KEY,
        "mailto": "kb-local@example.com",
    }
    url = API + "/works?" + urllib.parse.urlencode(params)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "kb-boundary (mailto:kb-local@example.com)"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out = []
            for w in data.get("results", []):
                loc = w.get("primary_location") or {}
                src = (loc.get("source") or {}).get("display_name", "") or ""
                out.append(src)
            return out
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == 429:
                time.sleep(2 * (i + 1))
                continue
            return []
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not API_KEY:
        print("⚠ 未设置 OPENALEX_API_KEY，无法做 venue 裁决。")
        print("  请先: $env:OPENALEX_API_KEY='你的密钥'")
        return

    # 用备份的原始数据做基准，避免在已剔除的数据上二次剔除
    src = BACKUP if BACKUP.exists() else FULL
    data = json.loads(src.read_text(encoding="utf-8"))
    advisors = data.get("advisors", [])
    print("基准数据:", src.name, "导师:", len(advisors))

    fields = None
    import build_advisor_index as B
    fields = B.load_topology_fields() if hasattr(B, "load_topology_fields") else B.load_taxonomy_fields()

    # 先按关键词判出「候选剔除者」
    candidates = [a for a in advisors if R._is_purely_non_cs(a.get("keywords") or [])]
    print("关键词初判的剔除候选:", len(candidates))
    if args.limit:
        candidates = candidates[:args.limit]
        print("本次只检查前", len(candidates), "个")

    rescued, confirmed, no_data = [], [], 0
    for i, a in enumerate(candidates, 1):
        orcid = a.get("orcid") or ""
        venues = fetch_venues(orcid)
        if not venues:
            no_data += 1
            rescued.append(a)          # 无数据 → 保守保留
        elif venue_is_cs(venues):
            rescued.append(a)
        else:
            confirmed.append(a)
        if i % 25 == 0:
            print("  已检查 %d/%d  翻案 %d  维持剔除 %d  无数据 %d"
                  % (i, len(candidates), len(rescued), len(confirmed), no_data),
                  flush=True)

    print()
    print("候选 %d → 翻案保留 %d / 维持剔除 %d / 无数据保守保留 %d"
          % (len(candidates), len(rescued) - no_data, len(confirmed), no_data))

    if args.dry_run:
        print("(dry-run，未写入)")
        return

    rescue_ids = {(a.get("name"), a.get("institution")) for a in rescued}
    # 从全量重新归类：初判要剔除、但被 venue 翻案的 → 强制归入交叉大类
    out = []
    stats = {"field": 0, "generic": 0, "unmapped": 0, "non_cs": 0, "excluded_non_cs": 0}
    for a in advisors:
        topics = a.get("keywords") or []
        if R._is_purely_non_cs(topics):
            if (a.get("name"), a.get("institution")) in rescue_ids:
                # 区分「有 venue 证据翻案」与「无证据保守保留」，
                # 后者不该被当成已确认的交叉学者
                has_evidence = bool(a.get("orcid"))
                out.append({**a, "category": "交叉与AI4Science",
                            "categories": ["交叉与AI4Science"],
                            "fields": [], 
                            "mapping": "rescued" if has_evidence else "rescued_no_evidence"})
                stats["non_cs"] += 1
            else:
                stats["excluded_non_cs"] += 1
            continue
        # 其余走正常映射
        mapped = []
        for t in topics:
            for f in B.map_topic_candidates(t, fields):
                if f not in mapped:
                    mapped.append(f)
        generic = []
        for t in topics:
            g = R._generic_hit(t) or R._cross_hit(t)
            if g and g not in generic:
                generic.append(g)
        if not mapped and not generic:
            out.append({**a, "category": "", "categories": [], "fields": [],
                        "mapping": "unmapped"})
            stats["unmapped"] += 1
            continue
        counts = {}
        for it in mapped:
            counts[it["category"]] = counts.get(it["category"], 0) + 1
        for cat, fld in generic:
            counts[cat] = counts.get(cat, 0) + 2
        cat = max(counts, key=counts.get)
        names = [f for _c, f in generic]
        for it in mapped:
            if it["name"] not in names:
                names.append(it["name"])
        out.append({**a, "category": cat,
                    "categories": sorted(counts, key=lambda n: -counts[n])[:5],
                    "fields": names[:8],
                    "mapping": "field" if mapped else "generic"})
        stats["field" if mapped else "generic"] += 1

    data["advisors"] = out
    data["advisor_count"] = len(out)
    data["mapping_stats"] = stats
    data["boundary_refined_at"] = __import__("datetime").datetime.now().isoformat(
        timespec="minutes")
    FULL.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已写入:", FULL, "| 最终导师:", len(out))
    print("统计:", stats)


if __name__ == "__main__":
    main()