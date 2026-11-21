#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 paper_meta.json / pdf_text_index.json 的绝对路径键改写成 {kb}/ 相对键。

为什么
------
这两个文件原来拿 `G:\\相关内容\\AuthorKit27\\知识库\\新论文\\xxx.pdf` 当键。
换一台电脑、或者知识库换个盘，文件都在、列表也照常，但标题、摘要、作者、
全文检索会静默全部对不上。改成 `{kb}/新论文/xxx.pdf` 之后，换机器只要在
config.json 里改 kb_path，别的一个都不用动。

不会重新解析 PDF：只是改写字典的键，正文与元数据原样保留。

用法
----
    python tools_rebase_index.py            # 预览，不改文件
    python tools_rebase_index.py --apply    # 真的写回（自动备份 .pre-rebase）
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kb_paths  # noqa: E402

TARGETS = ("paper_meta.json", "pdf_text_index.json")


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print("  读不了 %s：%s" % (path.name, e))
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真的写回文件")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = kb_paths.kb_root()
    print("知识库根：%s" % root)
    if root is None:
        print("读不到 kb_path，先确认 config.json 存在。")
        return 2

    total_changed = 0
    for name in TARGETS:
        p = HERE / name
        if not p.exists():
            print("%s：不存在，跳过" % name)
            continue
        doc = load(p)
        if doc is None:
            continue
        papers = doc.get("papers") or {}
        keys = list(papers)
        abs_keys = [k for k in keys if kb_paths.is_absolute(k)]
        new, changed = kb_paths.rebase(papers)
        rest = [k for k in new if kb_paths.is_absolute(k)]
        print("%s：%d 条，绝对路径 %d 条 → 可改写 %d 条，改写后仍是绝对路径 %d 条"
              % (name, len(keys), len(abs_keys), changed, len(rest)))
        if rest:
            for k in rest[:3]:
                print("    仍在外面的：%s" % k)
        total_changed += changed
        if not args.apply or changed == 0:
            continue
        backup = p.with_suffix(p.suffix + ".pre-rebase")
        if not backup.exists():
            shutil.copy2(p, backup)
            print("    已备份 %s" % backup.name)
        doc["papers"] = new
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
        print("    已写回 %s（%.1f MB）" % (p.name, p.stat().st_size / 1048576))

    if args.apply and total_changed:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print("完成：共改写 %d 条键。（%s）" % (total_changed, stamp))
    elif not args.apply:
        print("预览结束。加 --apply 才会真的写回（会先备份 .pre-rebase）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())