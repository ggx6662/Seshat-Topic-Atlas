#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多源数据融合：用 arXiv 补齐 OpenAlex 的主题盲区。

问题
----
OpenAlex 把「单目/双目深度估计、立体匹配、三维重建」整片研究压成
一个主题 `Advanced Vision and Imaging`，导致 387 个方向里有 200+ 个是 0 人。

OpenAlex 的主题分类改不了，但可以从**另一个源**拿到这个方向的真实研究者。

做法
----
1. 对每个「0 人」的方向，用它的关键词去 arXiv 搜论文（arXiv 无需 key）
2. 取最近的 N 篇论文的作者名
3. 用 OpenAlex 按作者名反查机构与引用量（补齐画像）
4. 写入 advisor_arxiv.json，与主索引合并

这样补进来的人，研究方向是**按 arXiv 论文主题判定的**，
可信度不比 OpenAlex 的主题标签差。

用法
----
python fetch_arxiv_advisors.py --limit 20      # 先试 20 个空方向
python fetch_arxiv_advisors.py                 # 全部空方向（约 200 个，需 1-2 小时）
python fetch_arxiv_advisors.py --field 单目与双目深度估计
"""

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

OUT = HERE / "advisor_arxiv.json"
API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
ARXIV = "http://export.arxiv.org/api/query"
OPENALEX = "https://api.openalex.org"

_lock_last = [0.0]
ARXIV_INTERVAL = 3.0        # arXiv 要求每次请求间隔 >= 3 秒


def _throttle():
    now = time.time()
    wait = ARXIV_INTERVAL - (now - _lock_last[0])
    if wait > 0:
        time.sleep(wait)
    _lock_last[0] = time.time()


def arxiv_search(query, max_results=40):
    """搜 arXiv，返回 [{title, authors, year}]。"""
    _throttle()
    q = urllib.parse.quote(query)
    url = "%s?search_query=%s&max_results=%d&sortBy=submittedDate&sortOrder=descending" % (
        ARXIV, q, max_results)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "kb-research-local/1.0 (mailto:kb-local@example.com)"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            xml = resp.read().decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    for block in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        year = re.search(r"<published>(\d{4})", block)
        authors = re.findall(r"<name>(.*?)</name>", block)
        out.append({
            "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else "",
            "authors": [a.strip() for a in authors if a.strip()],
            "year": int(year.group(1)) if year else None,
        })
    return out


def openalex_lookup(name, expect_terms=None, retries=4):
    """按姓名在 OpenAlex 反查作者，返回最可信的一条。

    姓名歧义很常见（「Wei Zhou」可能是完全不同的人）。所以：
      1. 姓名必须完全一致
      2. 引用量不低于 20（过滤学生与同名者）
      3. 若给出 expect_terms，其 OpenAlex 主题必须与研究方向有语义交集

    遇到 429 会退避重试 —— 早期版本直接返回 None，
    导致限流期间所有方向都被判为「补 0 人」，白白跑完 150 个方向。
    """
    if not API_KEY:
        return None
    params = {
        "filter": "display_name.search:" + name,
        "sort": "cited_by_count:desc",
        "per-page": "5",
        "api_key": API_KEY,
        "mailto": "kb-local@example.com",
    }
    url = OPENALEX + "/authors?" + urllib.parse.urlencode(params)
    data = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "kb-research-local (mailto:kb-local@example.com)"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == 429:
                # 限流：退避后重试，不能当成「查无此人」
                time.sleep(3 * (i + 1))
                continue
            return None
    if data is None:
        return None
    terms = [t.lower() for t in (expect_terms or []) if t]
    for a in data.get("results", []):
        if (a.get("display_name") or "").lower() != name.lower():
            continue
        insts = a.get("last_known_institutions") or []
        if not insts:
            continue
        inst = insts[0].get("display_name", "") or ""
        country = insts[0].get("country_code", "") or ""
        topics = [t.get("display_name", "") for t in (a.get("topics") or [])[:5]]
        if terms:
            hay = " ".join(topics).lower()
            # 语义匹配即可，不要求字面出现方向名。
            # OpenAlex 把深度估计标成 "Advanced Vision and Imaging"，
            # 苛求 depth 字样会把真正的深度估计学者（Tosi、Poggi）排除掉。
            sem = ["vision", "imaging", "depth", "image", "point cloud", "3d",
                   "reconstruction", "stereo", "geometry", "visual", "rendering",
                   "camera", "scene", "slam", "optical", "segmentation"]
            if not (any(t in hay for t in terms) or any(s in hay for s in sem)):
                continue
        return {
            "name": a.get("display_name", ""),
            "institution": inst,
            "country": country,
            "cited_by_count": a.get("cited_by_count", 0),
            "works_count": a.get("works_count", 0),
            "orcid": a.get("orcid") or "",
            "topics": topics,
        }
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--field", default="", help="只补某个方向")
    ap.add_argument("--per-field", type=int, default=40, help="每个方向取多少篇论文")
    args = ap.parse_args()

    import build_advisor_index as B
    import advisor_index as A

    fields = B.load_taxonomy_fields()
    rows = A.load_all()
    used = {}
    for a in rows:
        for f in (a.get("fields") or []):
            used[f] = used.get(f, 0) + 1

    empty = [f for f in fields if used.get(f["name"], 0) == 0]
    if args.field:
        empty = [f for f in empty if f["name"] == args.field]
    if args.limit:
        empty = empty[:args.limit]
    print("待补方向:", len(empty), flush=True)

    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    store = existing.get("advisors", [])
    done = set(existing.get("done_fields", []))
    # 上次补到 0 人的方向：可能是限流造成，本轮重试
    failed = set()

    for n, f in enumerate(empty, 1):
        name = f["name"]
        if name in done:
            continue
        kws = (f.get("keywords") or [])[:2] or [name]
        query = ' OR '.join('all:"%s"' % k for k in kws)
        papers = arxiv_search(query, args.per_field)
        if not papers:
            print("  [%d/%d] %s：arXiv 无结果" % (n, len(empty), name), flush=True)
            done.add(name)
            continue

        # 统计作者出现频次：同一方向反复出现的更可能是主力研究者
        freq = {}
        for p in papers:
            for a in p["authors"]:
                freq[a] = freq.get(a, 0) + 1
        top = sorted(freq.items(), key=lambda x: -x[1])[:12]

        added = 0
        # 用方向关键词做同名校验：作者的 OpenAlex 主题必须与之有交集
        expect = [k.lower() for k in kws] + [name.lower()]
        # 并发反查作者：单次 OpenAlex 查询约 1.7 秒，
        # 12 个作者串行要 20 秒，206 个方向要 1 小时以上。并发后快 8 倍。
        lookup_targets = [a for a, _c in top][:12]
        infos = {}
        # 并发从 8 降到 4：8 路会打满 OpenAlex 每秒上限，
        # 触发 429 后被当成「查无此人」，静默丢数据。
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(openalex_lookup, a, expect): a for a in lookup_targets}
            for fut in as_completed(futs):
                who = futs[fut]
                try:
                    infos[who] = fut.result()
                except Exception:
                    infos[who] = None

        for author, cnt in top:
            info = infos.get(author)
            if not info:
                continue
            if (info.get("cited_by_count") or 0) < 20:
                continue
            # 必须有机构：没有机构的学者画像不完整，会被界面过滤掉，
            # 存进来也是死数据
            if not info.get("institution"):
                continue
            store.append({
                "name": info["name"],
                "institution": info["institution"],
                "country": info.get("country", ""),
                "category": f["category"],
                "categories": [f["category"]],
                "fields": [name],
                "keywords": info.get("topics") or [],
                "cited_by_count": info["cited_by_count"],
                "works_count": info["works_count"],
                "orcid": info["orcid"],
                "source": "arXiv + OpenAlex",
                "evidence": "arxiv_hits=%d" % cnt,
            })
            added += 1
        done.add(name)
        # 失败与成功区分记录：查无结果的方向如果补到 0 人，
        # 很可能是限流造成的，下次应该重试，而不是永久标记完成。
        if added == 0:
            failed.add(name)
            done.discard(name)
        print("  [%d/%d] %s：%d 篇论文 → 补 %d 人%s"
              % (n, len(empty), name, len(papers), added,
                 "（0 人，待重试）" if added == 0 else ""), flush=True)

        OUT.write_text(json.dumps({
            "source": "arXiv(主题) + OpenAlex(机构与引用)",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M"),
            "done_fields": sorted(done),
            "failed_fields": sorted(failed),
            "advisor_count": len(store),
            "advisors": store,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("完成。补充学者:", len(store), "| 成功方向:", len(done),
          "| 待重试:", len(failed))


if __name__ == "__main__":
    main()