#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文献全文搜索：在 PDF 正文里找，而不只是文件名。

背景
----
之前搜「MOT17」「small target」「消融」，按文件名一个都搜不到 ——
这些词都在正文里。全文索引（build_text_index.py）建好后，这里负责查询。

匹配策略（从准到宽，结果分级返回）：
    3  文件名命中
    2  摘要（前 1500 字符）命中
    1  正文命中
"""

import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:
    import app_paths as _AP
    _RES = _AP.res        # 只读资源：打包后在 _MEIPASS
    _DATA = _AP.data      # 可写数据：打包后在 exe 旁边
except Exception:         # 单独跑构建脚本/测试时退回旧行为
    _RES = lambda n: HERE / n
    _DATA = lambda n: HERE / n
INDEX = _RES("pdf_text_index.json")
_INDEX_CACHE = {"sig": None, "data": None}


def available():
    """全文索引是否可用。"""
    return INDEX.exists()


def _load():
    try:
        sig = INDEX.stat().st_mtime_ns
    except OSError:
        return {}
    if _INDEX_CACHE["sig"] == sig and _INDEX_CACHE["data"] is not None:
        return _INDEX_CACHE["data"]
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8")).get("papers", {})
    except Exception:
        data = {}
    _INDEX_CACHE.update(sig=sig, data=data)
    return data


def _cat_of(path):
    """从路径推断分类（相对知识库根目录的第一级目录）。

    键可能是 `{kb}/新论文/xxx.pdf` 这种相对形式（换电脑也能用），
    所以先把键还原成当前机器上的绝对路径再算。
    """
    try:
        import kb_paths
        p = kb_paths.to_abs(path)
    except Exception:
        p = path
    try:
        import kb_widget as kb
        rel = os.path.relpath(p, str(kb.kb_root()))
        return rel.split(os.sep)[0] if os.sep in rel else "根目录"
    except Exception:
        return ""


def _snippet(text, query, width=90):
    """截取命中位置前后的文字，便于用户判断相关性。"""
    low = text.lower()
    q = query.lower()
    i = low.find(q)
    if i < 0:
        return ""
    start = max(0, i - width // 2)
    end = min(len(text), i + len(q) + width // 2)
    s = text[start:end]
    return ("…" if start > 0 else "") + s + ("…" if end < len(text) else "")


def search(query, limit=200):
    """在文件名与正文里搜索，返回按相关度分级的结果。"""
    q = (query or "").strip()
    if not q:
        return []
    papers = _load()
    ql = q.lower()
    out = []
    try:
        import kb_paths
    except Exception:
        kb_paths = None
    for path, meta in papers.items():
        # 键可能是 `{kb}/...` 相对形式（换电脑也能用），显示与推断都走绝对路径
        apath = kb_paths.to_abs(path) if kb_paths is not None else path
        name = os.path.basename(apath)
        title = os.path.splitext(name)[0].replace("_", " ")
        if ql in name.lower():
            out.append({"path": apath, "name": name, "title": title,
                        "cat": _cat_of(apath), "level": 3, "where": "文件名",
                        "snippet": "", "chars": meta.get("chars", 0)})
            continue
        text = meta.get("text") or ""
        if not text:
            continue
        low = text.lower()
        pos = low.find(ql)
        if pos < 0:
            continue
        in_abstract = pos < 1500
        out.append({"path": apath, "name": name, "title": title,
                    "cat": _cat_of(apath), "level": 2 if in_abstract else 1,
                    "where": "摘要" if in_abstract else "正文",
                    "snippet": _snippet(text, q), "chars": meta.get("chars", 0)})
    out.sort(key=lambda r: (-r["level"], r["title"]))
    return out[:limit]


def stats():
    papers = _load()
    total = len(papers)
    with_text = sum(1 for m in papers.values() if (m or {}).get("chars"))
    return {
        "available": available(),
        "papers": total,
        "with_text": with_text,
        "coverage": (100.0 * with_text / total) if total else 0.0,
    }