#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 全文索引：让搜索能搜到正文，而不只是文件名。

现状
----
文献库里 343 篇 PDF，之前搜索只能匹配**文件名**。
但论文的关键信息（方法名、数据集、结论）都在正文里 ——
搜「small target」「MOT17」这类词，按文件名一个都搜不到。

做法
----
用 PyMuPDF（fitz）提取每篇 PDF 的前 N 页文本，建立本地索引：
    pdf_text_index.json  { 路径: {mtime, chars, text} }

只取前 6 页：摘要、引言、方法已经包含绝大部分可检索信息，
全文提取会让索引膨胀到几十 MB，收益不大。

索引是增量的：只处理新增或修改过的 PDF。

用法
----
python build_text_index.py              # 增量建立/更新
python build_text_index.py --rebuild    # 全部重建
python build_text_index.py --pages 10   # 每篇取前 10 页
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

INDEX = HERE / "pdf_text_index.json"

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


def pdf_paths():
    """列出知识库里的全部 PDF（含路径与修改时间）。"""
    try:
        import kb_widget as kb
        inv = kb._inventory()
        files = inv.get("files", []) if isinstance(inv, dict) else []
    except Exception:
        files = []
    out = []
    for row in files:
        p = str(row[2]) if isinstance(row, (tuple, list)) and len(row) >= 3 else str(row)
        if not p.lower().endswith(".pdf"):
            continue
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        out.append((p, mt))
    return out


def extract_text(path, pages=6, max_chars=60000):
    """提取 PDF 前若干页的文本。"""
    if fitz is None:
        return ""
    try:
        doc = fitz.open(path)
        parts = []
        for i, page in enumerate(doc):
            if i >= pages:
                break
            parts.append(page.get_text())
        doc.close()
        text = "\n".join(parts)
        # 压掉多余空白，减小索引体积
        text = " ".join(text.split())
        return text[:max_chars]
    except Exception:
        return ""


def load_index():
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "papers": {}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--pages", type=int, default=6)
    args = ap.parse_args()

    if fitz is None:
        print("PyMuPDF 不可用，无法建立全文索引。")
        print("安装：pip install pymupdf")
        return 1

    idx = {"version": 1, "papers": {}} if args.rebuild else load_index()
    papers = idx.setdefault("papers", {})

    targets = pdf_paths()
    todo = [(p, mt) for p, mt in targets
            if p not in papers or papers[p].get("mtime") != mt]
    # 清理已删除的文件
    alive = {p for p, _ in targets}
    for p in list(papers):
        if p not in alive:
            del papers[p]

    print("PDF 总数:", len(targets), "| 待处理:", len(todo), flush=True)
    if not todo:
        print("索引已是最新。")
        return 0

    t0 = time.time()
    ok = fail = 0
    for n, (p, mt) in enumerate(todo, 1):
        text = extract_text(p, args.pages)
        if text:
            papers[p] = {"mtime": mt, "chars": len(text), "text": text}
            ok += 1
        else:
            papers[p] = {"mtime": mt, "chars": 0, "text": ""}
            fail += 1
        if n % 25 == 0:
            print("  进度 %d/%d  成功 %d  空 %d  已用 %.0fs"
                  % (n, len(todo), ok, fail, time.time() - t0), flush=True)
            INDEX.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")

    INDEX.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    size = os.path.getsize(INDEX) / 1048576
    print("完成。成功 %d / 空 %d | 耗时 %.0fs | 索引 %.1f MB"
          % (ok, fail, time.time() - t0, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())