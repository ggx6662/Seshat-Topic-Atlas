#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索日志：记住用户实际用了哪些词，用来改进检索。

为什么要记
----------
词表是人拍脑袋写的，用户真用的词才是准的。三条落地价值：

1. **发现词表缺口** —— 用户搜「红外小目标」查到 2 篇，说明同义组缺 SE 写法。
   日志按「查询 + 命中数」排，命中数长期为 0 或极少的词就是缺口的候选。
2. **冷启动预热** —— 出现 ≥3 次的查询，下次启动后台预跑一次，
   把向量、正文索引提前拉进内存，用户点下去就是秒出。
3. **抓取关键词** —— 抓 arXiv 新论文的 queries 可以按高频词补，不再只靠配置文件。

文件
----
`search_log.json`：小、可删（删了只丢统计，不影响任何检索结果）。
结构：{"version": 1, "queries": {mode: {词: {...}}}, "totals": {...}}

一次查询记一条聚合，不记流水 —— 流水会长到几 MB，聚合永远是几千条以内。
"""
import json
import os
import threading
import time

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "search_log.json")
MAX_TERMS = 4000           # 最多记 4000 个不同的词，超了淘汰最久没用的
WARM_MIN_COUNT = 3         # 出现这么多次才值得预热
_LOCK = threading.Lock()
_CACHE = {"data": None, "mtime": 0.0}


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _empty():
    return {"version": 1, "queries": {}, "totals": {}}


def _load():
    """读盘（带 mtime 缓存）。

    这是被动日志，任何异常都不能影响检索本身 —— 读坏了就当空的重建。
    """
    try:
        st = os.stat(LOG_FILE)
    except OSError:
        return _empty()
    if _CACHE["data"] is not None and st.st_mtime <= _CACHE["mtime"]:
        return _CACHE["data"]
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict) or "queries" not in d:
            d = _empty()
    except Exception:
        d = _empty()
    d.setdefault("version", 1)
    d.setdefault("queries", {})
    d.setdefault("totals", {})
    _CACHE["data"] = d
    _CACHE["mtime"] = st.st_mtime
    return d


def _prune(d):
    """按 last 时间淘汰，保留最近用过的 MAX_TERMS 个词。"""
    flat = []
    for mode, terms in d["queries"].items():
        for term, rec in terms.items():
            flat.append((rec.get("last", ""), mode, term))
    if len(flat) <= MAX_TERMS:
        return
    flat.sort()
    drop = flat[:len(flat) - MAX_TERMS]
    for _, mode, term in drop:
        d["queries"].get(mode, {}).pop(term, None)


def log_query(mode, terms, hits, took_ms=0):
    """记一次检索。

    mode  : "file" 文件名筛选 / "semantic" 本地语义 / "and" 多词交集 / "web" 网络
    terms : 字符串或列表
    hits  : 命中数
    """
    if isinstance(terms, (list, tuple)):
        terms = " ".join([str(t) for t in terms if t])
    terms = (terms or "").strip().lower()
    if not terms:
        return
    key = terms[:120]
    try:
        with _LOCK:
            d = _load()
            bucket = d["queries"].setdefault(mode, {})
            rec = bucket.get(key) or {"count": 0, "hits": 0, "zero": 0,
                                      "first": _now(), "last": _now()}
            rec["count"] = int(rec.get("count", 0)) + 1
            rec["hits"] = int(rec.get("hits", 0)) + int(hits or 0)
            if not hits:
                rec["zero"] = int(rec.get("zero", 0)) + 1
            rec["last"] = _now()
            rec["last_hits"] = int(hits or 0)
            if took_ms:
                rec["last_ms"] = int(took_ms)
            bucket[key] = rec
            tot = d["totals"].get(mode) or {"count": 0, "hits": 0}
            tot["count"] = int(tot.get("count", 0)) + 1
            tot["hits"] = int(tot.get("hits", 0)) + int(hits or 0)
            d["totals"][mode] = tot
            _prune(d)
            tmp = LOG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, LOG_FILE)
            _CACHE["data"] = d
            try:
                _CACHE["mtime"] = os.stat(LOG_FILE).st_mtime
            except OSError:
                pass
    except Exception:
        pass   # 日志失败绝不能影响检索


def top_terms(mode=None, n=20):
    """最常被搜的词。返回 [{term, mode, count, hits, zero, last}]。"""
    d = _load()
    modes = [mode] if mode else list(d["queries"].keys())
    out = []
    for m in modes:
        for term, rec in (d["queries"].get(m) or {}).items():
            out.append({"term": term, "mode": m,
                        "count": int(rec.get("count", 0)),
                        "hits": int(rec.get("hits", 0)),
                        "zero": int(rec.get("zero", 0)),
                        "last": rec.get("last", "")})
    out.sort(key=lambda r: (-r["count"], r["term"]))
    return out[:n]


def cold_terms(mode=None, n=20, min_count=2):
    """「搜了但几乎查不到」的词 —— 词表缺口的线索。

    排序：先看零命中次数，再看命中/次数的比例低的。
    """
    d = _load()
    modes = [mode] if mode else list(d["queries"].keys())
    out = []
    for m in modes:
        for term, rec in (d["queries"].get(m) or {}).items():
            c = int(rec.get("count", 0))
            if c < min_count:
                continue
            h = int(rec.get("hits", 0))
            z = int(rec.get("zero", 0))
            if z == 0 and h >= c * 3:
                continue
            out.append({"term": term, "mode": m, "count": c, "hits": h,
                        "zero": z, "avg": round(h / float(c), 1)})
    out.sort(key=lambda r: (-r["zero"], r["avg"]))
    return out[:n]


def warm_terms(n=8):
    """值得启动时预热的词：出现 ≥WARM_MIN_COUNT 次且确实查到过东西。"""
    out = []
    for r in top_terms(n=200):
        if r["count"] >= WARM_MIN_COUNT and r["hits"] > 0:
            out.append(r)
        if len(out) >= n:
            break
    return out


def stats():
    d = _load()
    terms = sum(len(v) for v in d["queries"].values())
    return {
        "file": LOG_FILE,
        "exists": os.path.exists(LOG_FILE),
        "terms": terms,
        "modes": {m: len(v) for m, v in d["queries"].items()},
        "totals": d.get("totals", {}),
    }


def reset():
    """清空日志（界面上要提示：只丢统计，不影响检索结果）。"""
    global _CACHE
    with _LOCK:
        _CACHE = {"data": None, "mtime": 0.0}
        try:
            if os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
    for r in top_terms(n=10):
        print("%-8s %-24s ×%d  平均命中 %.1f" % (r["mode"], r["term"], r["count"], r["hits"] / max(1, r["count"])))