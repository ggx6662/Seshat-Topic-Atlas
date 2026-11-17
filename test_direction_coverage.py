#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit every research direction against recognition, relations, venues, and advisors."""
from __future__ import annotations

import argparse
import collections
import datetime
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPORT_JSON = HERE / "exports" / "direction_coverage_report.json"
REPORT_MD = HERE / "exports" / "direction_coverage_report.md"


def load_widget():
    path = HERE / "kb_widget.py"
    spec = importlib.util.spec_from_file_location("kb_widget_coverage", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 kb_widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit(require_advisors: bool = True) -> dict:
    kb = load_widget()
    taxonomy = kb.load_research_taxonomy()
    relations = kb.load_research_relations()
    advisors = kb.load_advisors()
    kb.load_advisors = lambda: advisors

    field_locations = collections.defaultdict(list)
    category_without_venue = []
    fields = []
    for category, entry in taxonomy["categories"].items():
        if not entry.get("venues"):
            category_without_venue.append(category)
        for sub in entry.get("subs", []):
            name = sub.get("name", "")
            fields.append((category, name, sub))
            field_locations[name].append(category)

    duplicate_names = {
        name: categories
        for name, categories in field_locations.items()
        if len(categories) > 1
    }

    failures = collections.defaultdict(list)
    category_stats = {}
    direct_advisor_fields = 0
    category_advisor_fields = 0

    for category, name, entry in fields:
        stats = category_stats.setdefault(category, {
            "fields": 0,
            "alias_or_keyword": 0,
            "direct_advisor": 0,
            "advisor_via_category": 0,
            "venue": 0,
        })
        stats["fields"] += 1

        recognized = kb.infer_category_field(name)
        if recognized[:2] != (category, name):
            failures["classification"].append({
                "category": category,
                "field": name,
                "actual": list(recognized[:2]),
            })

        if not entry.get("keywords"):
            failures["missing_keywords"].append([category, name])
        if entry.get("aliases") or entry.get("keywords"):
            stats["alias_or_keyword"] += 1

        profile_key = kb.field_profile(category, name, relations)
        if profile_key not in relations.get("profiles", {}):
            failures["missing_relation_profile"].append(
                [category, name, profile_key])

        if not kb.recommend_venues(category, name, "", [], [], [], top=3):
            failures["missing_venue"].append([category, name])
        else:
            stats["venue"] += 1

        advisor_rows = kb.recommend_advisors(
            category, name, "", [], [], [], top=5)
        if advisor_rows:
            stats["advisor_via_category"] += 1
            category_advisor_fields += 1
            if any("领域匹配" in row.get("reasons", []) for row in advisor_rows):
                stats["direct_advisor"] += 1
                direct_advisor_fields += 1
        elif require_advisors:
            failures["missing_advisor"].append([category, name])

        institution_rows = kb.recommend_institutions(
            category, name, "", [], [], [], top=3)
        if not institution_rows and require_advisors:
            failures["missing_institution"].append([category, name])

    payload = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "basis": [
            "ACM/IEEE-CS/AAAI CS2023 knowledge areas",
            "CCF technical-committee research directions",
            "local public-publication advisor index",
        ],
        "totals": {
            "categories": len(taxonomy["categories"]),
            "fields": len(fields),
            "advisor_records": len(advisors),
            "category_advisor_linkage": category_advisor_fields,
            "direct_field_advisor_linkage": direct_advisor_fields,
        },
        "category_stats": category_stats,
        "duplicate_field_names": duplicate_names,
        "categories_without_venue": category_without_venue,
        "failures": dict(failures),
        "passed": not duplicate_names and not category_without_venue and not failures,
    }
    return payload


def write_reports(payload: dict) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# 计算机研究方向覆盖审计",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 大类：{payload['totals']['categories']}",
        f"- 研究方向：{payload['totals']['fields']}",
        f"- 导师记录：{payload['totals']['advisor_records']}",
        f"- 大类级导师关联：{payload['totals']['category_advisor_linkage']}",
        f"- 精确方向导师关联：{payload['totals']['direct_field_advisor_linkage']}",
        f"- 结果：{'通过' if payload['passed'] else '存在缺口'}",
        "",
        "## 分类审计",
        "",
        "| 大类 | 方向数 | 关键词/别名 | 导师可达 | 精确导师 | 期刊会议 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for category, stats in payload["category_stats"].items():
        lines.append(
            f"| {category} | {stats['fields']} | {stats['alias_or_keyword']} | "
            f"{stats['advisor_via_category']} | {stats['direct_advisor']} | "
            f"{stats['venue']} |"
        )
    failures = payload["failures"]
    lines.extend(["", "## 缺口", ""])
    if (not failures and not payload["duplicate_field_names"]
            and not payload["categories_without_venue"]):
        lines.append("没有发现未覆盖的方向。")
    else:
        for key, rows in failures.items():
            lines.append(f"- `{key}`：{len(rows)} 项")
        if payload["duplicate_field_names"]:
            lines.append(
                f"- `duplicate_field_names`：{len(payload['duplicate_field_names'])} 项")
        if payload["categories_without_venue"]:
            lines.append(
                f"- `categories_without_venue`：{len(payload['categories_without_venue'])} 项")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-missing-advisors",
        action="store_true",
        help="只审计 taxonomy，不把导师为空视为失败",
    )
    args = parser.parse_args()
    payload = audit(require_advisors=not args.allow_missing_advisors)
    write_reports(payload)
    print(json.dumps({
        "passed": payload["passed"],
        "totals": payload["totals"],
        "failure_counts": {
            key: len(value)
            for key, value in payload["failures"].items()
        },
        "duplicate_field_names": len(payload["duplicate_field_names"]),
        "categories_without_venue": len(payload["categories_without_venue"]),
        "report": str(REPORT_MD),
    }, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
