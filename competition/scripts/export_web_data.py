"""把桌面版真实数据导出为参赛 Web 版所需的静态 JSON。

只读原引擎与本地数据，不写入用户数据。运行：
    D:\\miniconda3\\python.exe competition/scripts/export_web_data.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = Path(__file__).resolve().parents[1] / "site"
DATA = SITE / "data"
sys.path.insert(0, str(ROOT))

import advisor_index  # noqa: E402
import kb_widget  # noqa: E402
import research_gap  # noqa: E402
import research_skills  # noqa: E402
import topic_gen  # noqa: E402


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def compact(text: str, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit] if limit else text


def write_json(path: Path, payload) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(raw, encoding="utf-8")
    return len(raw.encode("utf-8"))


def main() -> None:
    started = time.time()
    DATA.mkdir(parents=True, exist_ok=True)

    library = kb_widget.load_direction_library() or {}
    aliases = load("direction_aliases.json").get("aliases", [])
    inst_loc = load("institution_localization.json")
    inst_map = inst_loc.get("institutions", {})
    prov_map = inst_loc.get("provinces", {})
    venue_meta_all = load("venue_meta.json")
    venue_meta = venue_meta_all.get("venues", {})
    venue_alias = venue_meta_all.get("alias", {})

    alias_by_field: dict[tuple[str, str], list[str]] = {}
    for row in aliases:
        key = (row.get("category", ""), row.get("field", ""))
        alias_by_field.setdefault(key, []).extend(row.get("terms") or [])

    # ---------- 方向索引 ----------
    directions = []
    field_to_dir: dict[tuple[str, str], dict] = {}
    for cat, conf in library.items():
        for sub in conf.get("subs", []):
            name = sub.get("name") if isinstance(sub, dict) else str(sub)
            kws = (sub.get("keywords") or []) if isinstance(sub, dict) else []
            terms = []
            for term in [name, *kws, *alias_by_field.get((cat, name), [])]:
                term = compact(term, 80)
                if term and term.lower() not in {t.lower() for t in terms}:
                    terms.append(term)
            entry = {
                "id": f"d{len(directions) + 1:03d}",
                "name": name,
                "category": cat,
                "keywords": [compact(k, 80) for k in kws[:12]],
                "terms": terms[:32],
            }
            directions.append(entry)
            field_to_dir[(cat, name)] = entry

    def find_field(cat_part: str, field_part: str) -> dict:
        for (cat, field), entry in field_to_dir.items():
            if cat_part in cat and field_part in field:
                return entry
        for (cat, field), entry in field_to_dir.items():
            if field_part in field:
                return entry
        raise SystemExit(f"找不到方向：{cat_part} / {field_part}")

    examples = [
        ("单目深度估计", find_field("计算机视觉", "3D与几何视觉")),
        ("红外小目标检测", find_field("计算机视觉", "红外与低光视觉")),
        ("大语言模型高效推理", find_field("自然语言处理", "大语言模型")),
        ("联邦学习隐私保护", find_field("安全与隐私", "隐私计算")),
        ("蛋白质结构预测", find_field("交叉与AI4Science", "生物信息")),
    ]
    for idx, (name, target) in enumerate(examples, 1):
        directions.append({
            "id": f"x{idx}",
            "name": name,
            "category": target["category"],
            "keywords": [name],
            "terms": [name],
            "dataId": target["id"],
            "aliasOf": target["name"],
        })

    global_gap = research_gap.analyze(None, limit=160)
    compact_gap = {
        "scope": "全库",
        "total": global_gap.get("total", 0),
        "methods": global_gap.get("methods", []),
        "tasks": global_gap.get("tasks", []),
        "modals": global_gap.get("modals", []),
        "issues": global_gap.get("issues", []),
        "combos": global_gap.get("combos", [])[:60],
        "gaps": global_gap.get("gaps", [])[:80],
        "issue_gaps": global_gap.get("issue_gaps", []),
        "rising": global_gap.get("rising", []),
        "notes": global_gap.get("notes", []),
    }

    skills = research_skills.SKILLS
    rows = advisor_index.load_all() or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    rows = [r for r in rows if isinstance(r, dict)]

    # directions 数组后面还会追加 x1..x5 这类“示例别名”，它们通过 dataId/aliasOf
    # 指向已经存在的真实方向，本身没有独立的方向文件、也挂不了基准卡。
    # 统计口径必须是真实方向数（= len(field_to_dir)），不能取数组长度，
    # 否则开场页会报 536、素材库页报 531，两个数打架。见 AGENTS.md 数字口径。
    statistics = {
        "directions": len(field_to_dir),
        "directionAliases": len(directions) - len(field_to_dir),
        "categories": len(library),
        "papers": compact_gap["total"],
        "venues": len(venue_meta),
        "scholars_indexed": len(rows),
        "scholars_recommendable": sum(1 for r in rows if r.get("_complete")),
        "per_direction_advisors": 12,
    }

    index_payload = {
        "version": "2026-11-17",
        "product": "塞莎特——题谱",
        "tagline": "从研究方向到可核查的问题",
        "stats": statistics,
        "categories": [
            {"name": cat, "count": len(conf.get("subs", []))}
            for cat, conf in library.items()
        ],
        "directions": directions,
        "examples": [name for name, _ in examples],
        "angles": topic_gen.ANGLES,
        "fallback": topic_gen.FALLBACK,
        "skills": skills,
        "gap": compact_gap,
        "dataNote": "方向、导师、期刊与文献共现均由桌面版引擎离线计算；未调用任何在线接口。",
    }

    venues_payload = []
    for key, row in venue_meta.items():
        venues_payload.append({
            "name": row.get("name") or key,
            "type": row.get("type", ""),
            "ccf": row.get("ccf", ""),
            "country": row.get("country_cn", ""),
            "field": row.get("field_cn", ""),
            "intro": compact(row.get("intro", ""), 160),
            "url": row.get("url", ""),
        })
    venues_payload.sort(key=lambda v: (v["field"], v["name"]))
    write_json(DATA / "venues.json", venues_payload)
    print(f"venues.json {len(venues_payload)} venues")

    # ---------- 全量学者（前 2000 位，按引用） ----------
    rows.sort(key=lambda r: -(r.get("cited_by_count") or 0))
    top = []
    seen_name = set()
    for r in rows:
        name = compact(r.get("name"), 80)
        if not name or name in seen_name:
            continue
        seen_name.add(name)
        inst = compact(r.get("institution"), 120)
        loc = inst_map.get(inst, {})
        top.append({
            "name": name,
            "institution": inst,
            "institutionZh": compact(loc.get("zh") or inst, 120),
            "province": compact(loc.get("province_zh") or prov_map.get(r.get("province", "")) or r.get("province"), 40),
            "country": "中国" if r.get("country") == "CN" else compact(r.get("country"), 20),
            "category": compact(r.get("category"), 40),
            "fields": [compact(x, 60) for x in (r.get("fields") or [])[:2]],
            "keywords": [compact(x, 70) for x in (r.get("keywords") or [])[:3]],
            "cited": int(r.get("cited_by_count") or 0),
            "works": int(r.get("works_count") or 0),
            "orcid": compact(r.get("orcid"), 100),
        })
        if len(top) >= 2000:
            break
    write_json(DATA / "advisors.json", top)
    print(f"advisors.json {len(top)} scholars")

    # ---------- 每个方向的数据 ----------
    total_bytes = 0
    empty_advisors = 0
    fallback_gap = 0
    for i, entry in enumerate([d for d in directions if not d.get("dataId")], 1):
        cat, field = entry["category"], entry["name"]
        advice = advisor_index.recommend(cat, field, "", [], [], [], top=12)
        advisors = []
        for row in advice:
            a = row.get("advisor") or {}
            inst = compact(a.get("institution"), 120)
            loc = inst_map.get(inst, {})
            advisors.append({
                "name": compact(a.get("name"), 80),
                "institution": inst,
                "institutionZh": compact(loc.get("zh") or inst, 120),
                "province": compact(loc.get("province_zh") or prov_map.get(a.get("province", "")) or a.get("province"), 40),
                "country": "中国" if a.get("country") == "CN" else compact(a.get("country"), 20),
                "cited": int(row.get("cited") or 0),
                "works": int(row.get("works") or 0),
                "fields": [compact(x, 60) for x in (a.get("fields") or [])[:2]],
                "keywords": [compact(x, 70) for x in (a.get("keywords") or [])[:2]],
                "orcid": compact(a.get("orcid"), 100),
                "score": row.get("score", 0),
                "reasons": [compact(x, 40) for x in (row.get("reasons") or [])[:3]],
            })
        if not advisors:
            empty_advisors += 1

        venue_rows = kb_widget.recommend_venues(cat, field, "", [], [], [], top=8) or []
        venues = []
        for v in venue_rows:
            name = v.get("name", "")
            meta_key = venue_alias.get(name, name)
            meta = venue_meta.get(meta_key, {})
            venues.append({
                "name": name,
                "type": meta.get("type") or v.get("type", ""),
                "ccf": meta.get("ccf", ""),
                "country": meta.get("country_cn", ""),
                "field": meta.get("field_cn", ""),
                "intro": compact(meta.get("intro") or "；".join(v.get("reasons") or []), 160),
                "url": v.get("url") or meta.get("url", ""),
            })

        local = research_gap.analyze(field, limit=10)
        scope_used = field
        if local.get("total", 0) < 3 and entry["keywords"]:
            alt = research_gap.analyze(entry["keywords"][0], limit=10)
            if alt.get("total", 0) > local.get("total", 0):
                local = alt
                scope_used = entry["keywords"][0]
        entry["papers"] = local.get("total", 0)
        gap_data = local
        gap_note = "本地文献范围内的方法 × 任务共现。"
        if local.get("total", 0) < 3 or not local.get("gaps"):
            gap_data = compact_gap
            fallback_gap += 1
            gap_note = f"本方向在本地库直接匹配 {local.get('total', 0)} 篇，以下空白候选来自全库 {compact_gap['total']} 篇文献。"

        examples_out = []
        source_combos = (gap_data.get("combos") or [])[:3]
        for combo in source_combos:
            for title in (combo.get("examples") or [])[:1]:
                title = compact(title, 140)
                if title and title not in examples_out:
                    examples_out.append(title)
        papers = [{"title": t, "source": "本地文献库标题"} for t in examples_out[:3]]

        payload = {
            "id": entry["id"],
            "name": field,
            "category": cat,
            "scope": {
                "localTotal": local.get("total", 0),
                "scopeKeyword": scope_used,
                "gapSource": "本方向" if gap_data is local else "全库",
                "note": gap_note,
            },
            "advisors": advisors,
            "venues": venues,
            "gap": {
                "scope": gap_data.get("scope", ""),
                "total": gap_data.get("total", 0),
                "methods": gap_data.get("methods", []),
                "tasks": gap_data.get("tasks", []),
                "combos": gap_data.get("combos", [])[:16],
                "gaps": gap_data.get("gaps", [])[:8],
                "issueGaps": gap_data.get("issue_gaps", []),
                "rising": gap_data.get("rising", []),
            },
            "localGap": {
                "scope": local.get("scope", ""),
                "total": local.get("total", 0),
                "methods": local.get("methods", []),
                "tasks": local.get("tasks", []),
                "combos": local.get("combos", [])[:16],
                "gaps": local.get("gaps", [])[:8],
                "issueGaps": local.get("issue_gaps", []),
                "rising": local.get("rising", []),
            },
            "papers": papers,
        }
        total_bytes += write_json(DATA / "directions" / f"{entry['id']}.json", payload)
        if i % 40 == 0:
            print(f"  directions {i}/387  {time.time() - started:.0f}s")

    by_id = {entry["id"]: entry for entry in directions if not entry.get("dataId")}
    for entry in directions:
        if entry.get("dataId"):
            target = by_id.get(entry["dataId"])
            entry["papers"] = target.get("papers", 0) if target else 0

    size = write_json(DATA / "index.json", index_payload)
    print(f"index.json {size / 1024:.1f} KB, directions={len(directions)}")

    # 未匹配方向时的通用数据
    general = {
        "id": "general",
        "name": "通用",
        "category": "",
        "scope": {"localTotal": 0, "scopeKeyword": "", "gapSource": "全库",
                  "note": f"未匹配到方向库，以下为全库 {compact_gap['total']} 篇文献的共现结果。"},
        "advisors": [],
        "venues": [
            {"name": "NeurIPS", "type": "会议", "ccf": "A", "country": "国际",
             "field": "人工智能综合", "intro": "机器学习与计算神经科学主会", "url": "https://neurips.cc/"},
            {"name": "ICML", "type": "会议", "ccf": "A", "country": "国际",
             "field": "机器学习", "intro": "机器学习顶级会议", "url": "https://icml.cc/"},
            {"name": "AAAI", "type": "会议", "ccf": "A", "country": "美国",
             "field": "人工智能综合", "intro": "人工智能综合类顶会", "url": "https://aaai.org/"},
        ],
        "gap": {
            "scope": "全库", "total": compact_gap["total"],
            "methods": compact_gap["methods"], "tasks": compact_gap["tasks"],
            "combos": compact_gap["combos"][:16], "gaps": compact_gap["gaps"][:8],
            "issueGaps": compact_gap["issue_gaps"], "rising": compact_gap["rising"],
        },
        "papers": [{"title": t, "source": "本地文献库标题"}
                   for c in compact_gap["combos"][:3] for t in (c.get("examples") or [])[:1]],
    }
    write_json(DATA / "directions" / "general.json", general)

    print(f"direction files {total_bytes / 1024:.1f} KB, empty advisors={empty_advisors}, global gap fallback={fallback_gap}")
    print(f"done in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
