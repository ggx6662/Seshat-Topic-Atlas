#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补全院校中文名。

问题
----
导师库有 2233 所院校，其中只有 415 所有中文名（19%）。
界面上绝大多数院校只能显示英文名，对中文用户很不友好 ——
「Mudanjiang Normal University」很多人不能立刻反应是牡丹江师范学院。

做法
----
用 OpenAlex 的 `display_name_alternatives` 字段取机构的中文别名。
这个字段里通常含中文官方名（如 "华中师范大学"）。

输出合并进 institution_localization.json，不覆盖已有的人工映射。

用法
----
python localize_more.py            # 只补导师库里实际用到的院校
python localize_more.py --all      # 补全部 3178 所
python localize_more.py --limit 100
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

API = "https://api.openalex.org"
API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
LOC = HERE / "institution_localization.json"
INST = HERE / "institutions_cn.json"

_CJK = re.compile(r"[\u4e00-\u9fff]")


def _get(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "kb-localize (mailto:kb-local@example.com)"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if getattr(exc, "code", None) == 429:
                time.sleep(2 * (i + 1))
                continue
            return None
    return None


def fetch_chinese(institution_id):
    """取机构的中文别名（优先含「大学 / 学院 / 学校」的项）。"""
    short = institution_id.replace("https://openalex.org/", "")
    params = {"mailto": "kb-local@example.com"}
    if API_KEY:
        params["api_key"] = API_KEY
    url = API + "/institutions/" + short + "?" + urllib.parse.urlencode(params)
    data = _get(url)
    if not data:
        return []
    names = []
    for alt in (data.get("display_name_alternatives") or []):
        if isinstance(alt, str) and _CJK.search(alt):
            alt = alt.strip()
            if 4 <= len(alt) <= 30 and alt not in names:
                names.append(alt)
    # 优先带「大学/学院/学校/研究院」的
    names.sort(key=lambda x: (not any(w in x for w in ("大学", "学院", "学校",
                                                       "研究院", "研究所"))))
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    catalog = json.loads(INST.read_text(encoding="utf-8")).get("institutions", [])
    loc = json.loads(LOC.read_text(encoding="utf-8"))
    have = loc.setdefault("institutions", {})

    # 只处理导师库里实际出现的院校（省钱省时间）
    targets = catalog
    if not args.all:
        try:
            import advisor_index as A
            rows = A.load_all()
            used = {a.get("institution") for a in rows if a.get("institution")}
            targets = [i for i in catalog if i.get("name") in used]
        except Exception:
            pass

    todo = []
    for i in targets:
        name = i.get("name") or ""
        if name in have and have[name].get("zh"):
            continue
        todo.append(i)
    if args.limit:
        todo = todo[:args.limit]
    print("待补中文名:", len(todo), flush=True)

    added = 0
    for n, inst in enumerate(todo, 1):
        names = fetch_chinese(inst.get("id", ""))
        if names:
            entry = have.setdefault(inst["name"], {})
            entry.setdefault("zh", names[0])
            if len(names) > 1:
                entry["aliases"] = list(dict.fromkeys(
                    (entry.get("aliases") or []) + names))[:6]
            entry.setdefault("province", inst.get("region", ""))
            entry.setdefault("source", "OpenAlex display_name_alternatives")
            added += 1
        if n % 50 == 0:
            print("  进度 %d/%d  已补 %d" % (n, len(todo), added), flush=True)
            LOC.write_text(json.dumps(loc, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    LOC.write_text(json.dumps(loc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("完成。新增中文名:", added, "| 本地化总条数:", len(have))


if __name__ == "__main__":
    main()