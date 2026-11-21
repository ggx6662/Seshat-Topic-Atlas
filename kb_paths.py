#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库路径的可迁移化：把「绝对路径」换成「相对知识库根」的键。

背景
----
`paper_meta.json` 与 `pdf_text_index.json` 都是拿**绝对路径**当键的，
例如 `G:\\相关内容\\AuthorKit27\\知识库\\新论文\\xxx.pdf`。
换一台电脑、或者把知识库换个盘，文件其实都在、列表也照常，
但标题、摘要、作者、全文检索会**静默全部丢失** —— 因为一个键都对不上。

这里定一个不依赖盘符的键格式：

    {kb}/新论文/xxx.pdf

- `PREFIX` 是固定标记，和知识库放在哪无关；
- 反斜杠统一成 `/`，大小写仍然宽松匹配（Windows 习惯）；
- 老文件里遗留的绝对路径键在查询时自动换算，所以**不重建也能用**，
  想彻底干净再跑一次 `tools_rebase_index.py`。
"""

import os
import re
from pathlib import Path

PREFIX = "{kb}/"

_WIN_ABS = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_ABS = re.compile(r"^\\\\[^\\/]+[\\/]")


def norm(s):
    """统一分隔符与小写，只用于比较，不用于显示。"""
    return str(s or "").replace("\\", "/").strip().lower()


def is_absolute(s):
    t = str(s or "")
    return bool(_WIN_ABS.match(t) or _UNC_ABS.match(t) or t.startswith("/"))


def kb_root():
    """当前配置里的知识库根目录。读不到配置就返回 None（不猜路径）。"""
    try:
        import kb_widget
        return Path(kb_widget.kb_root())
    except Exception:
        return None


def to_key(path, root=None):
    """绝对路径 → `{kb}/...` 键。不在知识库根下的原样返回（相对分隔符）。"""
    root = Path(root) if root is not None else kb_root()
    p = str(path or "")
    if not p:
        return p
    if p.replace("\\", "/").startswith(PREFIX):
        return p.replace("\\", "/")
    if root is None or not is_absolute(p):
        return p.replace("\\", "/")
    try:
        rel = os.path.relpath(p, str(root))
    except (ValueError, OSError):
        return p.replace("\\", "/")
    if rel.startswith(".."):
        return p.replace("\\", "/")
    return PREFIX + rel.replace("\\", "/")


def to_abs(key, root=None):
    """`{kb}/...` 键 → 当前机器上的绝对路径。不是键就原样返回。"""
    k = str(key or "").replace("\\", "/")
    if not k.startswith(PREFIX):
        return str(key or "")
    root = Path(root) if root is not None else kb_root()
    if root is None:
        return str(key or "")
    return str(root / k[len(PREFIX):])


def lookup(d, path, root=None):
    """在「以路径为键」的字典里查一条，绝对路径与 `{kb}/` 键两种写法都认。

    返回 (值, 命中的键)；查不到返回 (None, None)。
    """
    if not d or not path:
        return None, None
    cands = []
    raw = str(path)
    cands.append(raw)
    key = to_key(raw, root)
    if key != raw:
        cands.append(key)
    # 反过来：传进来的是键，需要还原成绝对路径再试一次
    if raw.replace("\\", "/").startswith(PREFIX):
        back = to_abs(raw, root)
        if back and back != raw:
            cands.append(back)

    seen = set()
    for c in cands:
        n = norm(c)
        if n in seen:
            continue
        seen.add(n)
        if c in d:
            return d[c], c

    # 大小写 / 分隔符不敏感的兜底（Windows 习惯），只建一次映射
    idx = _INDEXES.get(id(d))
    if idx is None or idx[0] is not d:
        idx = (d, {norm(k): k for k in d})
        _INDEXES[id(d)] = idx
    for c in cands:
        hit = idx[1].get(norm(c))
        if hit is not None:
            return d[hit], hit
    return None, None


# 只缓存「同一个字典对象」的归一化映射，字典一换就重建；
# 用弱引用避免把大字典一直留在内存里。
_INDEXES = {}


def rebase(mapping, root=None):
    """一次性把字典的所有键从绝对路径改写成 `{kb}/`。返回 (新字典, 改写数)。"""
    out = {}
    changed = 0
    for k, v in (mapping or {}).items():
        nk = to_key(k, root)
        if nk != k:
            changed += 1
        out[nk] = v
    return out, changed


if __name__ == "__main__":
    r = kb_root()
    print("kb_root:", r)
    # 自检用：拿当前知识库根和几个假想位置试一遍换算
    root = Path(r) if r else Path("D:/某台电脑/知识库")
    samples = [str(root / "新论文" / "a.pdf"),
               r"D:\另一台电脑\知识库\新论文\b.pdf",
               "{kb}/新论文/c.pdf",
               r"\\nas\share\kb\d.pdf"]
    for s in samples:
        print("  %-56s -> %s" % (s, to_key(s, r)))