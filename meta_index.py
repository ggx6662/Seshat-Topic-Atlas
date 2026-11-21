"""读取 build_paper_meta.py 产出的 paper_meta.json。

为什么单独一个模块：app 启动时不该等这个索引（条目多、每次都要读 JSON）。
这里做懒加载 + 进程内缓存，第一次访问时才读盘。

接口：
    get(path)          -> dict | None      单篇元数据
    all_meta()         -> dict             全部（首次调用读盘）
    title_of(path)     -> str | None       已清洗的标题
    abstract_of(path)  -> str | None
    display_title(path, fallback) -> str   界面用：元数据标题 → 退到 fallback
    stats()            -> dict             覆盖统计
    invalidate()       清缓存（重建索引后调用）
"""
import json
import os
import re
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(HERE, "paper_meta.json")

# 标题尾部常见的 arXiv 编号残留，形如 "… 2610 36750v1" / "… arXiv:2610.36750"。
# 来自 PDF 页眉或文件名，混进标题里既占宽度又没信息，统一在读的时候剥掉。
_TAIL_ID = [
    re.compile(r"\s+\d{4}\s+\d{4,5}v?\d*\s*$"),
    re.compile(r"\s+arXiv:\s*\S+\s*$", re.I),
    re.compile(r"\s+[A-Za-z]{2,}-?20\d{2}-?\d+\s*$"),
]


def clean_title(t):
    t = (t or "").strip()
    if not t:
        return ""
    # 引文格式：`Int J Imaging Syst Tech - 2024 - Huang - 真标题`
    # 这是 EndNote/Zotero 导出的条目名，前四段是期刊/年份/作者，第五段才是标题。
    # 只在「前段里没有冒号」时替换 —— 真标题本身绝不会以 `期刊 - 年 - 姓 - ` 开头。
    m = re.match(r"^[A-Za-z][A-Za-z .&]{2,34}\s+-\s+(?:19|20)\d{2}\s+-\s+"
                 r"[A-Z][A-Za-z\-']{1,24}\s+-\s+(.{6,})$", t)
    if m:
        t = m.group(1).strip()
        # 双栏 PDF 断词常把词尾留在下一列，导出后成了 `... Mamba-`
        t = re.sub(r"[\-\u2010\u2011\u2013\u2014]\s*$", "", t).strip()
    for _ in range(2):           # 有的标题尾部堆了两段
        before = t
        for rx in _TAIL_ID:
            t = rx.sub("", t).strip()
        if t == before:
            break
    return t

_lock = threading.Lock()
_cache = None
_cache_mtime = None


def _load():
    global _cache, _cache_mtime
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        data = {}
        try:
            mt = os.path.getmtime(META_PATH)
            with open(META_PATH, encoding="utf-8") as f:
                d = json.load(f)
            data = d.get("papers", {}) or {}
            _cache_mtime = mt
        except Exception:
            data = {}
        _cache = data
        return _cache


def invalidate():
    """重建索引后清缓存。"""
    global _cache, _cache_mtime
    with _lock:
        _cache = None
        _cache_mtime = None


def all_meta():
    return _load()


def get(path):
    """按路径取元数据。

    认两种键：老文件里的绝对路径，以及 `{kb}/...` 相对键（换电脑/换盘后仍然对得上）。
    路径大小写不敏感兜底（Windows）。
    """
    d = _load()
    if not d:
        return None
    if path in d:
        return d[path]
    try:
        import kb_paths
    except Exception:
        kb_paths = None
    if kb_paths is not None:
        v, _k = kb_paths.lookup(d, path)
        if v is not None:
            return v
    # Windows 路径大小写差异兜底
    low = path.lower()
    for k, vv in d.items():
        if k.lower() == low:
            return vv
    return None


def title_of(path):
    v = get(path)
    if not v:
        return None
    t = clean_title(v.get("title"))
    return t or None


def abstract_of(path):
    v = get(path)
    if not v:
        return None
    a = (v.get("abstract") or "").strip()
    return a or None


def display_title(path, fallback=""):
    """界面显示用标题：优先元数据，其次 fallback（文件名等）。"""
    t = title_of(path)
    if t:
        return t
    return fallback or os.path.basename(path or "")


def stats():
    d = _load()
    n = len(d)
    if not n:
        return {"count": 0, "title": 0, "abstract": 0, "authors": 0,
                "pct_title": 0, "pct_abstract": 0, "pct_authors": 0}
    nt = sum(1 for v in d.values() if v.get("title"))
    na = sum(1 for v in d.values() if v.get("abstract"))
    nu = sum(1 for v in d.values() if v.get("authors"))
    return {
        "count": n, "title": nt, "abstract": na, "authors": nu,
        "pct_title": round(100 * nt / n),
        "pct_abstract": round(100 * na / n),
        "pct_authors": round(100 * nu / n),
    }