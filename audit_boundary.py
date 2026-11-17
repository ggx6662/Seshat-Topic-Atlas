#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学科边界抽查：把「被我的判据剔除的人」和「保留为交叉的人」各抽 20 个，
连同他们的代表作与发表 venue 一起列出来，交由人来判断判据是否准确。

为什么要做这件事
----------------
现在的学科边界判定只看 OpenAlex 的**主题名**，看不到论文内容。
这必然存在两类风险：
  误删 —— 真正做计算机研究的人，主题名里没出现 CS 词
  误留 —— 用计算机当工具、但研究本身是别的学科的人

只靠调关键词无法解决，必须拿真实论文和发表 venue 来核对。
「论文发在哪」是最强的学科信号：
  CVPR / NeurIPS / TPAMI → 几乎一定是计算机研究
  Optics Express / Civil Engineering → 不是

用法
----
python audit_boundary.py              # 抽样 20 + 20，打印报告
python audit_boundary.py --n 30       # 自定义样本量
python audit_boundary.py --fetch      # 额外拉取代表作 venue（需联网/API key）
"""

import argparse
import json
import os
import random
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import remap_advisors as R  # noqa: E402

BACKUP = HERE / "backup" / "advisor_directory_full.json.bak"
CURRENT = HERE / "advisor_directory_full.json"
OUT_DIR = HERE / "exports"

API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
API = "https://api.openalex.org"

# 计算机领域的典型发表 venue（用于自动判定倾向）
CS_VENUES = [
    "cvpr", "iccv", "eccv", "neurips", "nips", "icml", "iclr", "aaai", "ijcai",
    "acl", "emnlp", "naacl", "coling", "sigir", "kdd", "www", "wsdm", "cikm",
    "chi", "uist", "cscw", "ubicomp", "siggraph", "sigmod", "vldb", "icde",
    "sosp", "osdi", "nsdi", "sigcomm", "ccs", "sp ", "usenix", "ndss", "pldi",
    "popl", "oopsla", "icse", "fse", "ase", "issta", "micro", "isca", "asplos",
    "hpca", "sc ", "tpami", "ijcv", "tip", "tmm", "tkde", "tois", "tacl",
    "tse", "tosem", "tcs", "jmlr", "tmi", "tmlr", "ieee transactions on pattern",
    "ieee transactions on image", "acm transactions on graphics",
    "computer vision", "machine learning", "pattern recognition", "artificial intelligence",
]
# 明显的非计算机 venue
NON_CS_VENUES = [
    "optics", "photonics", "applied optics", "optics express", "optics letters",
    "civil engineering", "structural", "mechanical", "materials science",
    "battery", "chemistry", "physics", "metrology", "measurement science",
    "nursing", "clinical", "medical journal", "humanities", "history",
    "education research", "library",
]


def load_backup():
    data = json.loads(BACKUP.read_text(encoding="utf-8"))
    return data.get("advisors", [])


def classify_excluded(all_advisors):
    """重新跑一遍判据，找出被剔除的人。"""
    return [a for a in all_advisors if R._is_purely_non_cs(a.get("keywords") or [])]


def venue_tendency(venues):
    """根据发表 venue 判断学科倾向。"""
    blob = " ".join(v.lower() for v in venues if v)
    cs = sum(1 for v in CS_VENUES if v in blob)
    non = sum(1 for v in NON_CS_VENUES if v in blob)
    if cs > non:
        return "计算机倾向", cs, non
    if non > cs:
        return "非计算机倾向", cs, non
    return "无法判断", cs, non


def fetch_venues(advisor, limit=5):
    """拉取该学者被引用最多的论文及其发表 venue。

    必须用**唯一标识**定位学者，不能用姓名：
    实测用姓名匹配会把「Songtao Liu」对到 YOLOX 作者、
    把「Hua Zhang」对到新冠论文作者——那是完全不同的人。
    优先级：ORCID > OpenAlex author id > 放弃（宁可没数据也不给错数据）
    """
    if not API_KEY:
        return []
    params = {
        "sort": "cited_by_count:desc",
        "per-page": str(limit),
    }
    orcid = (advisor.get("orcid") or "").strip()
    author_id = (advisor.get("author_id") or "").strip()
    if orcid:
        params["filter"] = "authorships.author.orcid:" + orcid.replace(
            "https://orcid.org/", "")
    elif author_id:
        params["filter"] = "authorships.author.id:" + author_id.replace(
            "https://openalex.org/", "")
    else:
        return []
    params["api_key"] = API_KEY
    params["mailto"] = "kb-local@example.com"
    params["select"] = "display_name,publication_year,cited_by_count,primary_location"
    url = API + "/works?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "kb-audit (mailto:kb-local@example.com)"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    out = []
    for w in data.get("results", []):
        loc = w.get("primary_location") or {}
        src = (loc.get("source") or {}).get("display_name", "") or ""
        out.append({
            "title": w.get("display_name", ""),
            "year": w.get("publication_year"),
            "cited": w.get("cited_by_count", 0),
            "venue": src,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--fetch", action="store_true", help="联网拉取代表作与 venue")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    all_adv = load_backup()
    excluded = classify_excluded(all_adv)
    current = json.loads(CURRENT.read_text(encoding="utf-8")).get("advisors", [])
    kept_cross = [a for a in current if a.get("mapping") == "non_cs"]

    print("总导师: %d" % len(all_adv))
    print("被剔除（判为纯非计算机）: %d" % len(excluded))
    print("保留为交叉但未匹配具体领域: %d" % len(kept_cross))
    print()

    samples = {
        "被剔除": random.sample(excluded, min(args.n, len(excluded))),
        "保留为交叉": random.sample(kept_cross, min(args.n, len(kept_cross))),
    }

    report = []
    for group, people in samples.items():
        print("=" * 78)
        print("【%s】%d 人" % (group, len(people)))
        print("=" * 78)
        for i, adv in enumerate(people, 1):
            line = {
                "group": group,
                "name": adv.get("name"),
                "institution": adv.get("institution"),
                "topics": adv.get("keywords"),
                "works": adv.get("works_count"),
                "cited": adv.get("cited_by_count"),
                "venues": [],
            }
            print("\n%2d. %s  @ %s" % (i, adv.get("name"), adv.get("institution")))
            print("    主题: %s" % " / ".join(adv.get("keywords") or [])[:150])
            if args.fetch:
                vs = fetch_venues(adv)
                line["venues"] = vs
                if vs:
                    tend, cs, non = venue_tendency([v["venue"] for v in vs])
                    line["tendency"] = tend
                    print("    代表作（发表 venue）:")
                    for v in vs[:3]:
                        print("      - [%s] %s  @ %s" % (v["year"], (v["title"] or "")[:60],
                                                         v["venue"] or "（无 venue）"))
                    print("    自动倾向: %s（计算机 venue %d / 非计算机 venue %d）"
                          % (tend, cs, non))
                else:
                    print("    代表作: （未取到）")
            report.append(line)

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "学科边界抽查.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n报告已保存:", out)


if __name__ == "__main__":
    main()