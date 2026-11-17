#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 OpenAlex 构建全国院校与导师索引（公开出版数据）。

产物:
  institutions_cn.json              全国教育机构（OpenAlex CN education）
  advisor_directory_generated.json  研究型院校的 CS 作者与主题映射

用法:
  python build_advisor_index.py --institutions 200 --authors 20
  python build_advisor_index.py --institutions 50 --authors 10

说明: OpenAlex 作者是“公开出版活跃研究者”，不等于当前在职导师/招生导师；
使用前请以院校官网核验。
"""
import argparse
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.openalex.org"
HEADERS = {
    "User-Agent": "kb-monitor/0.2 (research index; local)",
    "mailto": "local@example.com",
}
INSTITUTIONS_FILE = HERE / "institutions_cn.json"
GENERATED_FILE = HERE / "advisor_directory_generated.json"


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    last = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            time.sleep(1.5)
    raise last


def fetch_institutions():
    out, page = [], 1
    while True:
        params = {
            "filter": "country_code:CN,type:education",
            "per-page": "100",
            "sort": "works_count:desc",
            "page": str(page),
            "mailto": "local@example.com",
        }
        data = get_json(API + "/institutions?" + urllib.parse.urlencode(params))
        results = data.get("results", [])
        for item in results:
            geo = item.get("geo") or {}
            topics = [t.get("display_name") for t in item.get("topics", [])[:3]]
            out.append({
                "name": item.get("display_name", ""),
                "id": item.get("id", ""),
                "city": geo.get("city", ""),
                "region": geo.get("region", ""),
                "country": geo.get("country", "China"),
                "homepage": item.get("homepage_url", ""),
                "works_count": item.get("works_count", 0),
                "topics": topics,
            })
        if len(results) < 100:
            break
        page += 1
        time.sleep(0.4)
    return out


def load_taxonomy_fields():
    base = json.loads((HERE / "directions_library.json").read_text(encoding="utf-8"))
    try:
        ext = json.loads((HERE / "research_taxonomy_extended.json").read_text(encoding="utf-8"))
    except Exception:
        ext = {}
    try:
        comp = json.loads((HERE / "research_taxonomy_comprehensive.json").read_text(encoding="utf-8"))
    except Exception:
        comp = {}
    try:
        aliases = json.loads((HERE / "direction_aliases.json").read_text(encoding="utf-8")).get("aliases", [])
    except Exception:
        aliases = []
    alias_map = {}
    for entry in aliases:
        alias_map.setdefault((entry.get("category"), entry.get("field")), []).extend(entry.get("terms", []))
    fields = []
    sources = list(base.items()) + list(ext.get("categories", {}).items())
    sources += list(comp.get("categories", {}).items())
    # 同一领域可能同时出现在主库和补充总表里。
    # 以前遇到重复就跳过，导致后来补进补充表的关键词被整条忽略
    # （「单目与双目深度估计」就因此一直匹配不到 Stereo Matching 等主题）。
    # 现在改为合并：关键词与别名取并集。
    merged = {}
    order = []
    for cat, entry in sources:
        for sub in entry.get("subs", []):
            key = (cat, sub.get("name", ""))
            kws = [k.lower() for k in sub.get("keywords", []) if k]
            als = [a.lower() for a in
                   alias_map.get(key, []) + list(sub.get("aliases", [])) if a]
            if key not in merged:
                merged[key] = {"keywords": [], "aliases": []}
                order.append(key)
            bucket = merged[key]
            for k in kws:
                if k not in bucket["keywords"]:
                    bucket["keywords"].append(k)
            for a in als:
                if a not in bucket["aliases"]:
                    bucket["aliases"].append(a)
    for cat, name in order:
        bucket = merged[(cat, name)]
        fields.append({
            "category": cat,
            "name": name,
            "keywords": bucket["keywords"],
            "aliases": bucket["aliases"],
        })
    return fields


def _term_hit(term, text):
    """词条是否命中主题名。

    英文缩写（如 ics / ar / gpu）必须按「独立单词」匹配：
    旧实现用 `term in text` 子串匹配，导致 `ics` 命中 Robotics、Graphics、
    Semantics…… 于是「工业控制系统」被匹配了 2588 次；
    `ar` 命中 robotics/grammar/… 让「VR与AR」被匹配了 9502 次，
    使得 47% 的导师被贴上错误的标签。

    规则：
      * 英文且长度 <= 4 的词条（缩写）→ 必须单词边界独立出现
      * 英文且长度 > 4            → 允许词内出现（如 transformer 在
                                     "vision transformer for detection" 里）
      * 中文词条                 → 子串匹配即可
    """
    if not term or not text:
        return False
    if term.isascii():
        if len(term) <= 4:
            return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])",
                             text) is not None
        return term in text
    return term in text


def map_topic_candidates(topic, fields, limit=4):
    text = topic.lower()
    ranked = []
    for field in fields:
        score = 0
        matched_length = 0
        if _term_hit(field["name"].lower(), text):
            score += 6
            matched_length = max(matched_length, len(field["name"]))
        for kw in field["keywords"]:
            if _term_hit(kw, text):
                score += 3
                matched_length = max(matched_length, len(kw))
        for alias in field.get("aliases", []):
            if _term_hit(alias, text):
                score += 4
                matched_length = max(matched_length, len(alias))
        if score:
            ranked.append((score, matched_length, field))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["name"]))
    if not ranked:
        return []
    best_score = ranked[0][0]
    best = [item[2] for item in ranked if item[0] == best_score]
    return best[:max(1, limit)]


def map_topic(topic, fields):
    matches = map_topic_candidates(topic, fields, limit=1)
    return matches[0] if matches else None


def fetch_authors(inst, per_page, fields):
    short_id = inst["id"].replace("https://openalex.org/", "")
    params = {
        "filter": "last_known_institutions.id:" + short_id + ",topics.field.id:fields/17",
        "sort": "cited_by_count:desc",
        "per-page": str(per_page),
    }
    data = get_json(API + "/authors?" + urllib.parse.urlencode(params), timeout=35)
    rows = []
    for author in data.get("results", []):
        topics = [t.get("display_name", "") for t in author.get("topics", [])[:5]]
        mapped = []
        for topic in topics:
            for field in map_topic_candidates(topic, fields):
                if field not in mapped:
                    mapped.append(field)
        if not mapped:
            continue
        counts = {}
        for item in mapped:
            counts[item["category"]] = counts.get(item["category"], 0) + 1
        category = max(counts, key=counts.get)
        categories = sorted(counts, key=lambda name: (-counts[name], name))
        names = []
        for item in mapped:
            if item["name"] not in names:
                names.append(item["name"])
        rows.append({
            "name": author.get("display_name", ""),
            "institution": inst["name"],
            "lab": "",
            "category": category,
            "categories": categories[:5],
            "fields": names[:8],
            "keywords": topics,
            "works_count": author.get("works_count", 0),
            "cited_by_count": author.get("cited_by_count", 0),
            "homepage": author.get("homepage_url", ""),
            "source": "OpenAlex",
            "verified": False,
            "institution_id": inst["id"],
            "province": inst.get("region", ""),
            "city": inst.get("city", ""),
        })
    return rows


def enrich_advisor_mapping(advisors, fields):
    enriched = []
    for advisor in advisors:
        mapped = []
        for topic in advisor.get("keywords", []):
            for field in map_topic_candidates(topic, fields):
                if field not in mapped:
                    mapped.append(field)
        counts = {}
        for item in mapped:
            counts[item["category"]] = counts.get(item["category"], 0) + 1
        categories = []
        for category in sorted(counts, key=lambda name: (-counts[name], name)):
            if category and category not in categories:
                categories.append(category)
        names = []
        for item in mapped:
            if item["name"] not in names:
                names.append(item["name"])
        row = dict(advisor)
        row["categories"] = categories[:6]
        row["category"] = categories[0] if categories else advisor.get("category", "")
        row["fields"] = names[:10]
        enriched.append(row)
    return enriched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--institutions", type=int, default=200,
                    help="参与导师索引的院校数（按 OpenAlex works_count 排序）")
    ap.add_argument("--authors", type=int, default=20,
                    help="每所院校最多抓取的 CS 作者数")
    ap.add_argument("--min-works", type=int, default=5)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--refresh-institutions",
        action="store_true",
        help="重新抓取全国教育机构；默认复用已有 institutions_cn.json",
    )
    ap.add_argument(
        "--remap-only",
        action="store_true",
        help="不联网，仅用现有作者主题重新映射新方向",
    )
    args = ap.parse_args()

    if args.remap_only:
        if not GENERATED_FILE.exists():
            raise SystemExit("缺少 advisor_directory_generated.json")
        existing = json.loads(GENERATED_FILE.read_text(encoding="utf-8"))
        fields = load_taxonomy_fields()
        advisors = enrich_advisor_mapping(existing.get("advisors", []), fields)
        existing["advisors"] = advisors
        existing["advisor_count"] = len(advisors)
        existing["remapped_at"] = datetime.datetime.now().isoformat(timespec="minutes")
        GENERATED_FILE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("remapped advisors:", len(advisors), flush=True)
        print("saved:", GENERATED_FILE, flush=True)
        return

    if args.refresh_institutions or not INSTITUTIONS_FILE.exists():
        print("Fetching CN education institutions from OpenAlex...", flush=True)
        institutions = fetch_institutions()
        INSTITUTIONS_FILE.write_text(json.dumps({
            "source": "OpenAlex",
            "generated_at": datetime.datetime.now().isoformat(timespec="minutes"),
            "count": len(institutions),
            "institutions": institutions,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        institution_data = json.loads(INSTITUTIONS_FILE.read_text(encoding="utf-8"))
        institutions = institution_data.get("institutions", [])
        print("Reusing CN education institution catalog:", len(institutions), flush=True)
    print("institutions:", len(institutions), flush=True)

    selected = institutions[:args.institutions]
    fields = load_taxonomy_fields()
    advisors, errors = [], []

    def work(inst):
        try:
            return inst, fetch_authors(inst, args.authors, fields)
        except Exception as exc:
            return inst, exc

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(work, inst) for inst in selected]
        for fut in as_completed(futures):
            inst, result = fut.result()
            done += 1
            if isinstance(result, Exception):
                errors.append((inst.get("name", ""), str(result)))
            else:
                advisors.extend([a for a in result if a.get("works_count", 0) >= args.min_works])
            if done % 20 == 0:
                print("processed", done, "/", len(selected), "advisors", len(advisors), flush=True)

    dedup = {}
    for a in advisors:
        key = (a.get("name", "").strip().lower(), a.get("institution", "").strip().lower())
        if key not in dedup:
            dedup[key] = a
    advisors = sorted(dedup.values(), key=lambda x: (-x.get("cited_by_count", 0),
                                                     -x.get("works_count", 0)))
    GENERATED_FILE.write_text(json.dumps({
        "source": "OpenAlex",
        "generated_at": datetime.datetime.now().isoformat(timespec="minutes"),
        "institution_count": len(selected),
        "advisor_count": len(advisors),
        "errors": errors[:30],
        "advisors": advisors,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("advisors:", len(advisors), "errors:", len(errors), flush=True)
    print("saved:", GENERATED_FILE, flush=True)


if __name__ == "__main__":
    main()
