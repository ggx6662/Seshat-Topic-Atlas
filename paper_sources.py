"""按方向抓最新论文——多源聚合。

为什么不是只用 arXiv：
    arXiv 只有预印本，而且是"先挂上、后来才中会议"。用户要的是"这个方向
    最近在发生什么"，那么期刊（Pattern Recognition / TIP）和会议
    （CVPR/ICCV）也得算进来。实测同一个方向「红外小目标检测」：
        arXiv      最新 2026-11-04
        OpenAlex   最新 2026-11-11，122 篇里很多是期刊正式发表
    只用 arXiv 会漏掉一整个月的正式发表。

各源实测可用性（2026-11，无 key 状态）：
    arXiv        OK   672ms   Atom XML
    OpenAlex     OK   2.3s    JSON，必须用 filter= 而不是 search= 才不 429
    Crossref     OK   7.1s    JSON，慢，只在需要期刊时用
    EuropePMC    OK   2.4s    JSON，偏生物医学，CS 方向上价值有限
    DOAJ         OK  12.8s    JSON，慢

    Semantic Scholar  429（无 key 必限流）
    DBLP              500（服务端错误）
    CORE              429（需 key）

设计取舍：
    ① 每个源独立 try，一个失败不影响其他（返回 errors 列表，界面如实显示）
    ② 统一成同一个 paper 字典结构，字段缺失就是空串，不造数据
    ③ 同一篇论文可能同时出现在 arXiv 和 OpenAlex（预印本 vs 正式版），
       用标题归一化去重，优先保留有 DOI 的那条
    ④ 缓存 6 小时，key 含方向名 + 各源开关
"""
import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

import arxiv_latest

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "paper_sources_cache.json")
UA = "kb-research-local/1.0 (mailto:kb-local@example.com)"

_lock = threading.Lock()
_last = {}
CACHE_TTL = 6 * 3600

ALL_SOURCES = ("arxiv", "openalex", "europepmc")

SOURCE_LABEL = {
    "arxiv": "arXiv",
    "openalex": "OpenAlex",
    "europepmc": "Europe PMC",
}


_NOISE_TITLE = re.compile(
    r"^\s*(correction|erratum|retraction|retracted|corrigendum|addendum|"
    r"editorial|editor's note|expression of concern|publisher correction|"
    r"reply to|response to|comment on|review of)\b", re.I)

# OpenAlex 的 type 字段里这些不是研究论文
_BAD_TYPES = {"paratext", "editorial", "erratum", "libguides", "letter",
              "peer-review", "supplementary-materials", "grant", "dataset"}


def _is_noise(title, typ=""):
    """过滤勘误/撤稿/编辑部声明。

    实测坑：OpenAlex 把 "Correction: Hjort-YOLO: a lightweight and
    explainable computer vision framework..." 当成一篇正常 work 返回，
    摘要是一段 "Check all grant numbers and funding information..." 的模板文字，
    排在时间线第二位，非常干扰。它不是研究进展，必须挡在外面。
    """
    if typ and typ in _BAD_TYPES:
        return True
    return bool(_NOISE_TITLE.match(title or ""))


def _blank():
    return {"title": "", "abstract": "", "authors": [], "published": "",
            "url": "", "doi": "", "venue": "", "source": "", "cited": 0,
            "oa": "", "arxiv_id": ""}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _throttle(src, gap):
    """每个源单独限流，互不阻塞。"""
    with _lock:
        now = time.time()
        wait = gap - (now - _last.get(src, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last[src] = time.time()


def _abstract_from_inverted(idx, limit=900):
    """OpenAlex 的摘要存成了倒排索引 {word: [pos,...]}，要还原成正文。"""
    if not idx:
        return ""
    pos = []
    for w, ps in idx.items():
        for p in ps:
            pos.append((p, w))
    pos.sort()
    txt = " ".join(w for _, w in pos)
    if len(txt) > limit:
        txt = txt[:limit].rsplit(" ", 1)[0] + " …"
    return txt


# ── 各源抓取 ──────────────────────────────────────────────

def _fetch_arxiv(direction, limit, query_override=""):
    q = (query_override or "").strip() or arxiv_latest.build_query(direction)
    if not q:
        return []
    arxiv_latest._throttle()
    params = {"search_query": q, "start": 0, "max_results": min(100, limit),
              "sortBy": "submittedDate", "sortOrder": "descending"}
    url = arxiv_latest.ARXIV_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        xml = r.read().decode("utf-8", "ignore")
    out = []
    for p in arxiv_latest._parse_xml(xml):
        d = _blank()
        d.update(title=p["title"], abstract=p["abstract"],
                 authors=p["authors"][:6], published=p["published"],
                 url=p["url"], arxiv_id=p["arxiv_id"], source="arxiv",
                 venue="arXiv " + p.get("primary_cat", ""))
        out.append(d)
    return out


def _fetch_openalex(direction, limit, days_back=180, query_override=""):
    en = arxiv_latest.to_english(direction)
    if not en:
        return []
    import datetime
    since = (datetime.date.today() -
             datetime.timedelta(days=days_back)).isoformat()
    # 注意两个坑：
    #   ① 用 search= 参数会走慢通道并被限流 429，必须用 filter=
    #   ② title_and_abstract.search 里**必须显式写 AND**。只写
    #      `infrared small target detection` 会被当成 OR/短语，实测
    #      「silica nanoparticles 的热行为」这种完全不相关的论文也会进来。
    #      加 AND 之后同一个方向从 1781 篇散装结果收敛到 225 篇精确结果。
    words = [w for w in re.split(r"\s+", en) if w]
    # 多词短语用引号包住，OpenAlex 支持 "object detection" 这种精确短语
    terms = []
    i = 0
    raw = en.split()
    while i < len(raw):
        hit = None
        for n in (3, 2):
            if i + n <= len(raw) and " ".join(raw[i:i + n]).lower() in arxiv_latest._PHRASE:
                hit = " ".join(raw[i:i + n])
                break
        if hit:
            terms.append('"%s"' % hit)
            i += len(hit.split())
        else:
            terms.append(raw[i])
            i += 1
    if not terms:
        return []
    query = " AND ".join(terms[:4])
    filt = "from_publication_date:%s,title_and_abstract.search:%s" % (since, query)
    params = {"filter": filt, "per-page": min(100, limit),
              "sort": "publication_date:desc", "mailto": "kb-local@example.com"}
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    _throttle("openalex", 1.0)
    d = _get(url)
    out = []
    for w in d.get("results", []):
        t = (w.get("title") or "").strip()
        if not t:
            continue
        if _is_noise(t, w.get("type") or ""):
            continue
        src = (w.get("primary_location") or {}).get("source") or {}
        p = _blank()
        p.update(title=t,
                 abstract=_abstract_from_inverted(w.get("abstract_inverted_index")),
                 authors=[a["author"]["display_name"]
                          for a in (w.get("authorships") or [])[:6]
                          if (a.get("author") or {}).get("display_name")],
                 published=w.get("publication_date") or "",
                 url=w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or "",
                 doi=(w.get("doi") or "").replace("https://doi.org/", ""),
                 venue=src.get("display_name") or "",
                 source="openalex",
                 cited=w.get("cited_by_count") or 0,
                 oa=(w.get("open_access") or {}).get("oa_url") or "")
        out.append(p)
    return out


def _fetch_europepmc(direction, limit, query_override=""):
    en = arxiv_latest.to_english(direction)
    if not en:
        return []
    # Europe PMC 的 query 默认是 OR 语义，而且会搜全文。
    # 「infrared AND object AND detection」直接给 26473 条，第一条是
    # 木寡糖对甲烷合成的影响——因为它全文里出现了这几个词。
    # 必须限定到 TITLE_ABS: 字段，同一个方向从 26473 → 272 条且相关。
    toks = [w for w in en.split() if w]
    terms = []
    i = 0
    while i < len(toks):
        hit = None
        for n in (3, 2):
            if i + n <= len(toks) and " ".join(toks[i:i + n]).lower() in arxiv_latest._PHRASE:
                hit = " ".join(toks[i:i + n])
                break
        if hit:
            terms.append('TITLE_ABS:"%s"' % hit)
            i += len(hit.split())
        else:
            terms.append("TITLE_ABS:%s" % toks[i])
            i += 1
    if not terms:
        return []
    query = " AND ".join(terms[:4])
    _throttle("europepmc", 1.0)
    params = {"query": query, "format": "json", "pageSize": min(50, limit),
              "sort": "P_PDATE_D desc", "resultType": "lite"}
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
           + urllib.parse.urlencode(params))
    d = _get(url, timeout=45)
    out = []
    for it in (d.get("resultList") or {}).get("result", []):
        t = (it.get("title") or "").strip().rstrip(".")
        if not t:
            continue
        if _is_noise(t):
            continue
        p = _blank()
        p.update(title=t,
                 abstract=(it.get("abstractText") or "")[:900],
                 authors=[a.get("fullName", "").strip()
                          for a in (it.get("authorList") or {}).get("author", [])[:6]],
                 published=it.get("firstPublicationDate") or "",
                 url=("https://europepmc.org/article/%s/%s"
                      % (it.get("source", "MED"), it.get("id", ""))),
                 doi=it.get("doi") or "",
                 venue=it.get("journalTitle") or "",
                 source="europepmc",
                 cited=it.get("citedByCount") or 0)
        out.append(p)
    return out


_FETCHERS = {
    "arxiv": _fetch_arxiv,
    "openalex": _fetch_openalex,
    "europepmc": _fetch_europepmc,
}


# ── 去重与排序 ────────────────────────────────────────────

def _norm_title(t):
    """标题归一化用于跨源去重：arXiv 版和期刊版标题常常只差大小写/标点。"""
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _dedupe(papers):
    """同一篇论文出现在多个源时只留一条，优先有 DOI 的（正式版）。

    预印本和正式版标题基本一致，但作者列表可能不同，所以取"信息更全"的那条：
    DOI > 摘要长度 > 引用数。
    """
    best = {}
    order = []
    for p in papers:
        k = _norm_title(p.get("title"))
        if not k:
            continue
        prev = best.get(k)
        if prev is None:
            best[k] = p
            order.append(k)
            continue
        def score(x):
            return ((1 if x.get("doi") else 0) * 3
                    + min(len(x.get("abstract") or ""), 900) / 900.0
                    + (1 if x.get("venue") else 0))
        if score(p) > score(prev):
            # 保留来源信息，方便界面看出这条来自哪
            p["also_in"] = sorted(set((prev.get("also_in") or []) +
                                      [prev.get("source", "")]) - {""})
            best[k] = p
        else:
            prev["also_in"] = sorted(set((prev.get("also_in") or []) +
                                         [p.get("source", "")]) - {""})
    return [best[k] for k in order]


def _rank(papers, days_back=180):
    """排序：新发表的优先，同一天内有 DOI/有摘要的优先。

    不按引用排——最新论文引用都是 0，按引用排等于只给老论文。
    """
    def key(p):
        d = p.get("published") or "0000-00-00"
        return (d, 1 if p.get("doi") else 0, len(p.get("abstract") or ""))
    return sorted(papers, key=key, reverse=True)


# ── 对外接口 ──────────────────────────────────────────────

def _load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("items", {}) if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_cache(items):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"version": 1,
                       "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "items": items}, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_all(direction, sources=ALL_SOURCES, limit=25, days_back=180,
              use_cache=True, override_query=""):
    """按方向从多个源抓最新论文。

    返回：
        {"direction", "papers":[...], "by_source": {源: 条数},
         "errors": [("crossref", "原因"), ...], "cached": bool}

    override_query：用给定的 arXiv 检索式**替代**自动生成的式子，
        且此时只查 arXiv（另外两个源不认 arXiv 语法，硬塞进去只会乱）。
        给大模型改写检索式用——本地词表的 220 条覆盖不了所有组合。
    """
    d = (direction or "").strip()
    if not d:
        return {"direction": "", "papers": [], "by_source": {}, "errors": [],
                "cached": False}
    oq = (override_query or "").strip()
    if oq:
        sources = ("arxiv",)
    srcs = tuple(s for s in sources if s in _FETCHERS)
    key = "%s|%s|%d|%d|%s" % (d, ",".join(srcs), limit, days_back, oq)
    cache = _load_cache()
    rec = cache.get(key)
    if use_cache and rec and time.time() - rec.get("ts", 0) < CACHE_TTL:
        out = dict(rec.get("data") or {})
        out["cached"] = True
        return out

    collected = []
    by_source = {}
    errors = []
    for s in srcs:
        try:
            got = _FETCHERS[s](d, limit, query_override=oq)
            by_source[s] = len(got)
            collected.extend(got)
        except Exception as e:
            by_source[s] = 0
            errors.append((s, "%s: %s" % (type(e).__name__, str(e)[:80])))

    papers = _rank(_dedupe(collected), days_back)
    if days_back > 0:
        import datetime
        cut = (datetime.date.today() -
               datetime.timedelta(days=days_back)).isoformat()
        papers = [p for p in papers if (p.get("published") or "") >= cut]

    data = {"direction": d, "papers": papers, "by_source": by_source,
            "errors": errors, "cached": False}
    cache[key] = {"ts": time.time(), "data": data}
    _save_cache(cache)
    return data


def brief(result, n=8):
    """给界面/提示词用的一行行文本。"""
    out = []
    for p in (result.get("papers") or [])[:n]:
        ven = p.get("venue") or ""
        out.append("%s | %s%s" % (p.get("published", ""),
                                  p.get("title", "")[:90],
                                  (" | " + ven) if ven else ""))
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    ds = sys.argv[1:] or ["红外小目标检测"]
    for d in ds:
        r = fetch_all(d, limit=15)
        print("方向：", d, "| 缓存" if r["cached"] else "")
        print("  各源：", r["by_source"])
        if r["errors"]:
            for s, e in r["errors"]:
                print("  失败 %-12s %s" % (s, e))
        print("  去重后 %d 篇" % len(r["papers"]))
        for p in r["papers"][:8]:
            also = ("+" + "/".join(p["also_in"])) if p.get("also_in") else ""
            print("    %s [%s%s] %s" % (p["published"], p["source"], also,
                                        p["title"][:56]))