#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build Chinese display names for advisor institutions and provinces.

The original English names remain the matching keys.  This file is a display
layer only, sourced from OpenAlex institution alternatives plus a small,
explicit map for well-known non-Chinese research groups.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "institution_localization.json"
API = "https://api.openalex.org/institutions"
HEADERS = {
    "User-Agent": "kb-monitor/0.3 (local display localization)",
    "mailto": "local@example.com",
}

PROVINCES = {
    "Anhui": "安徽",
    "Beijing": "北京",
    "Chongqing": "重庆",
    "Fujian": "福建",
    "Gansu": "甘肃",
    "Guangdong": "广东",
    "Guangxi": "广西",
    "Guizhou": "贵州",
    "Hainan": "海南",
    "Hebei": "河北",
    "Heilongjiang": "黑龙江",
    "Henan": "河南",
    "Hubei": "湖北",
    "Hunan": "湖南",
    "Inner Mongolia": "内蒙古",
    "Jiangsu": "江苏",
    "Jiangxi": "江西",
    "Jilin": "吉林",
    "Liaoning": "辽宁",
    "Ningxia": "宁夏",
    "Qinghai": "青海",
    "Shaanxi": "陕西",
    "Shandong": "山东",
    "Shanghai": "上海",
    "Shanxi": "山西",
    "Sichuan": "四川",
    "Tianjin": "天津",
    "Tibet": "西藏",
    "Xizang": "西藏",
    "Xinjiang": "新疆",
    "Yunnan": "云南",
    "Zhejiang": "浙江",
    "Hong Kong": "香港",
    "Macau": "澳门",
    "Macao": "澳门",
    "Taiwan": "台湾",
}

MANUAL = {
    "Stanford CS": "斯坦福大学计算机科学系",
    "Stanford University": "斯坦福大学",
    "UC Berkeley EECS": "加州大学伯克利分校电气工程与计算机科学系",
    "CMU SCS": "卡内基梅隆大学计算机科学学院",
    "MIT CSAIL": "麻省理工学院计算机科学与人工智能实验室",
    "ETH Zurich D-INFK": "苏黎世联邦理工学院计算机科学系",
    "Oxford CS": "牛津大学计算机科学系",
    "Cambridge CS": "剑桥大学计算机科学系",
    "UCLA CS": "加州大学洛杉矶分校计算机科学系",
    "Princeton CS": "普林斯顿大学计算机科学系",
    "UIUC CS": "伊利诺伊大学厄巴纳-香槟分校计算机科学系",
    "University of Washington CSE": "华盛顿大学计算机科学与工程系",
    "University of Michigan CSE": "密歇根大学计算机科学与工程系",
    "EPFL CS": "洛桑联邦理工学院计算机科学系",
    "HKUST CSE": "香港科技大学计算机科学与工程系",
    "NUS Computing": "新加坡国立大学计算学院",
    "Peking University CS": "北京大学计算机学院",
    "Tsinghua CS": "清华大学计算机科学与技术系",
    "Shanghai Jiao Tong CS": "上海交通大学计算机科学与工程系",
    "Fudan CS": "复旦大学计算机科学技术学院",
    "Zhejiang University CS": "浙江大学计算机科学与技术学院",
    "Michigan CSE": "密歇根大学计算机科学与工程系",
    "University of Toronto CS": "多伦多大学计算机科学系",
    "Microsoft Research Asia": "微软亚洲研究院",
    "Max Planck Institute for Intelligent Systems": "马克斯·普朗克智能系统研究所",
    "Wuhan Textile University": "武汉纺织大学",
    "China Jiliang University": "中国计量大学",
    "Shenyang Pharmaceutical University": "沈阳药科大学",
    "Shenyang Agricultural University": "沈阳农业大学",
    "Jiaxing University": "嘉兴大学",
    "Henan Institute of Science and Technology": "河南科技学院",
    "Chengdu University": "成都大学",
    "Shanxi Normal University": "山西师范大学",
    "Hunan University of Technology": "湖南工业大学",
    "Heilongjiang University of Chinese Medicine": "黑龙江中医药大学",
    "Shenyang Ligong University": "沈阳理工大学",
    "Shantou University Medical College": "汕头大学医学院",
}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    last = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            time.sleep(1.5)
    raise last  # type: ignore[misc]


def chinese_alternative(values: list[str]) -> str:
    candidates = []
    for value in values:
        value = (value or "").strip()
        if value and re.search(r"[\u4e00-\u9fff]", value):
            suffix = 3 if value.endswith(("大学", "学院", "学校", "医院")) else 0
            candidates.append((suffix, len(value), value))
    return max(candidates)[2] if candidates else ""


def collect_records() -> list[dict]:
    records = {}
    for filename in (
        "advisor_directory_generated.json",
        "advisor_directory.json",
        "research_taxonomy_extended.json",
        "research_taxonomy.json",
    ):
        path = HERE / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("advisors", [])
        if not rows:
            rows = [
                {"institution": source.get("name", ""), "institution_id": ""}
                for source in data.get("sources", [])
            ]
        for row in rows:
            name = (row.get("institution") or "").strip()
            if not name:
                continue
            item = records.setdefault(name, {"name": name, "id": ""})
            if row.get("institution_id"):
                item["id"] = row["institution_id"]
    return list(records.values())


def fetch_alternatives(records: list[dict]) -> dict:
    out = {}
    with_id = [item for item in records if item.get("id")]
    for offset in range(0, len(with_id), 40):
        batch = with_id[offset:offset + 40]
        ids = [item["id"].replace("https://openalex.org/", "") for item in batch]
        params = {
            "filter": "ids.openalex:" + "|".join(ids),
            "per-page": "50",
            "select": "id,display_name,display_name_alternatives,display_name_acronyms,geo",
        }
        data = get_json(API + "?" + urllib.parse.urlencode(params))
        by_id = {
            item.get("id", "").replace("https://openalex.org/", ""): item
            for item in data.get("results", [])
        }
        for item in batch:
            short_id = item["id"].replace("https://openalex.org/", "")
            api_item = by_id.get(short_id, {})
            alternatives = api_item.get("display_name_alternatives", [])
            zh = chinese_alternative(alternatives)
            if zh:
                geo = api_item.get("geo") or {}
                out[item["name"]] = {
                    "zh": zh,
                    "aliases": alternatives,
                    "acronyms": api_item.get("display_name_acronyms", []),
                    "province": geo.get("region", ""),
                    "province_zh": PROVINCES.get(geo.get("region", ""), ""),
                    "source": "OpenAlex",
                }
        print("localized", min(offset + len(batch), len(with_id)), "/", len(with_id), flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if OUTPUT.exists() and not args.refresh:
        print("exists:", OUTPUT, "(use --refresh to rebuild)")
        return 0

    records = collect_records()
    institutions = fetch_alternatives(records)
    missing = [item["name"] for item in records if item["name"] not in institutions]
    for name in missing:
        if name in MANUAL:
            institutions[name] = {
                "zh": MANUAL[name],
                "aliases": [name],
                "acronyms": [],
                "province": "",
                "province_zh": "",
                "source": "manual",
            }
    payload = {
        "generated_at": datetime.datetime.now().isoformat(timespec="minutes"),
        "source": "OpenAlex display_name_alternatives + explicit manual map",
        "provinces": PROVINCES,
        "institutions": institutions,
        "coverage": {
            "records": len(records),
            "localized": len(institutions),
            "missing": [item["name"] for item in records if item["name"] not in institutions],
        },
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("saved:", OUTPUT)
    print("coverage:", len(institutions), "/", len(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
