"""把 PDF 全文里能提取的元数据写进 paper_meta.json，供界面读取。

背景：文献库原本只有 name / cat / path 三个字段，371 条记录 title 全空。
界面只能拿文件名当标题，出现 "1"、"ICCV2025-36" 这种无意义条目。
pdf_text_index.json 已有全文（每篇前 6 页），元数据就在里面。

产出 paper_meta.json：
    {
      "version": 1,
      "built_at": "...",
      "papers": {
         "<path>": {"title":..., "authors":..., "abstract":..., "year":...,
                    "venue":..., "is_survey":..., "title_src": "pdf"|"filename"}
      }
    }

标题来源策略（互补）：
    1. pdf 正文首个合理行 —— 最准，但双栏 PDF 常把作者混进来
    2. 文件名还原 —— 文件名往往是标题的 slug
       如 "Scalpel-SAM_A_Semi-Supervised_Paradigm_for_Adapting_SAM.pdf"
    优先用 pdf，pdf 明显不对时（含作者名、被截断）退回文件名。

用法：
    python build_paper_meta.py            # 增量（按 mtime）
    python build_paper_meta.py --force    # 全量重建
"""
import json
import os
import re
import sys
import time

import paper_meta

HERE = os.path.dirname(os.path.abspath(__file__))
TEXT_INDEX = os.path.join(HERE, "pdf_text_index.json")
OUT = os.path.join(HERE, "paper_meta.json")

# 文件名里这些不是标题（作者投稿模板 / 会议编号）
_JUNK_STEM = re.compile(
    r"^(?:\d+|ICCV\d{4}-\d+|CVPR\d{4}-\d+|ICLR\d{4}-\d+|PaperID-\d+|"
    r"paper|main|final|camera[_\- ]?ready|\d{4}\.\d{4,5}v\d)$",
    re.IGNORECASE,
)


def title_from_filename(path):
    """从文件名还原标题。

    例：Scalpel-SAM_A_Semi-Supervised_Paradigm_for_Adapting_SAM_to_Infrared.pdf
        → Scalpel-SAM A Semi-Supervised Paradigm for Adapting SAM to Infrared
    文件名里 _ 和 - 都是空格；连续大写缩写（SAM/YOLO）保留。
    """
    if not path:
        return None
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"^\d{4}-\s*", "", stem)          # 2024-XXX
    if _JUNK_STEM.match(stem.strip()):
        return None
    # arXiv 编号 2512.12345v1 不是标题
    if re.fullmatch(r"\d{4}\.\d{4,5}v\d", stem.strip()):
        return None

    s = stem.replace("_", " ")
    # 连字符：两侧都是字母时当空格（Res-CBAM 保留，Semi-Supervised 保留）
    s = re.sub(r"(?<=[a-z])\-(?=[A-Z][a-z])", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -")

    # 文件名尾部常带 arXiv 编号（下载器拼上去的），形如
    #   ..._for_I_2610_22434v1  →  "... for I 2610 22434v1"
    #   ..._CVPRF_2026_paper    →  "... CVPRF 2026 paper"
    # 不剥掉就会当成标题内容，界面上看就是「标题后面跟一串数字」。
    s = re.sub(r"\s+\d{4}\s+\d{4,5}v\d*\s*$", "", s)
    s = re.sub(r"\s+[A-Z]{2,}[A-Z]?_?\s?\d{4}\s+paper\s*$", "", s)
    s = re.sub(r"\s+paper\s*$", "", s, flags=re.I).strip()

    if len(s) < 8:
        return None
    # 至少含 3 个英文单词
    if len(re.findall(r"[A-Za-z]{2,}", s)) < 3:
        return None
    # 全大写说明是缩写堆叠，不像是标题
    if s.isupper() and len(s) < 20:
        return None
    return s[:300]


_JUNK_TITLE = re.compile(
    r"^(?:ICCV|CVPR|ICLR|AAAI|NeurIPS|NIPS|ECCV|ICML|WACV|BMVC|ACCV|IJCAI|"
    r"TPAMI|MICCAI|ACMMM|ACM MM)\s*\d{4}[\-_]?\d*$|"     # ICCV2025-36 / CVPR2024
    r"^\d{4}\.\d{4,5}v\d*$|"                             # arXiv 编号 2509.19733v1
    r"^\d{1,4}$|"                                        # 纯数字
    r"^NO\.?\s*[A-Z]?\d{6,}$|"                           # 专利号 NO.D2025400429
    r"^[A-Z]{2,}[\-_][A-Z]*\d{4,}[\-_]?\d*$|"            # TSP_CMC_52582 / 投稿编号
    r"^[a-z]{4,}\d{8}[\-_]\d*$|"                         # ojapps20241412_122312887
    r"^[a-z]\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)+$",            # "g Michigan State" 这类残片
    re.I,
)

# pdf-low 里最糟的情况：标题从作者行中间开始，形如
#   "5*, Jin Gao1,2, Weiming Hu1,2,5,6, Zhipeng Zhang3,4† 1State Key"
_AUTHOR_LINE = re.compile(r"^\d+\s*[\*∗†‡§⋆]?\s*,")


def _looks_like_author_line(t):
    """标题像不像是「从作者行中间截出来的」。"""
    if not t:
        return True
    if _AUTHOR_LINE.match(t.strip()):
        return True
    # 前 30 字符里有上标数字+逗号组合，且没有人话（大小写混杂的长词序列少）
    head = t[:40]
    if re.search(r"\d[,;]\s*[A-Z]", head) and re.search(r"[∗†‡§⋆]", head):
        return True
    return False


def _is_junk_title(t):
    """标题是不是「编号 / 残片」这类对读者毫无意义的东西。"""
    if not t:
        return True
    s = t.strip()
    if len(s) < 12:
        return True
    return bool(_JUNK_TITLE.match(s))


_LEAD_BOILER = re.compile(
    r"^\s*(?:we\s+(?:present|propose|introduce|show|argue|study|describe|report|"
    r"develop|design|demonstrate)\b"
    r"|in\s+this\s+(?:paper|work|article|letter)\s*,?\s*"
    r"|this\s+(?:paper|work|article|letter)\s+(?:presents?|proposes?|introduces?|studies)\b\s*,?\s*"
    # "We introduce Stereo Anywhere, a novel stereo-matching framework…"
    # → 只要后面那个专名。用惰性匹配吃到逗号，且要求首字母大写才算专名。
    r"|(?:we|this\s+work)\s+(?:introduces?|presents?|proposes?)\s+(?=[A-Z])"
    r"|recently\s*,?\s*|in\s+recent\s+years\s*,?\s*|over\s+the\s+past\s+\w+\s+years\s*,?\s*"
    r"|as\s+a\s+result\s*,?\s*|"
    r"deep\s+learning\s+has\s+)\s*",
    re.I)

# 摘要首句后面常跟「Recently, …」把主题隔开；这里也当分隔点
_LEAD_SPLIT = re.compile(r"(?:[,.;]\s*)(?:recently\b|more\s+recently\b|in\s+recent\s+years\b)", re.I)

# 剥离后开头的「纯叙述性短语」，它们后面跟的才是主题
_MID_NOISE = re.compile(
    r"^\s*(?:the\s+first\s+(?:work|study|attempt|method)\s+(?:to\s+)?"
    r"(?:demonstrating|showing|proving|proposing|that|which)\s*(?:that\s+)?"
    r"|a\s+novel\s+|an\s+effective\s+|the\s+first\s+|"
    r"aims?\s+to\s+|is\s+a\s+|for\s+the\s+first\s+time\s*,?\s*)",
    re.I)


def _title_from_abstract(abs_):
    """没有可信标题时，用摘要里的关键词短语当标题。

    **不要直接用摘要首句**：首句多半是 "We present the first work demonstrating
    that…"，那是行文套话不是主题，摆在列表里比文件名还难读。
    这里先把套话剥掉，再取「主体名词短语」，并限制在 ~56 字符。

    连剥完都不像一个主题（"Accurate …" / "This paper has been accepted …"），
    就返回 None —— 让上层退回文件名，那至少还能看出是哪篇。
    """
    s = (abs_ or "").strip()
    if len(s) < 40:
        return None
    # 出版声明不是摘要内容
    if re.match(r"\s*(?:this\s+(?:paper|work)\s+has\s+been\s+(?:accepted|published)|"
                r"accepted\s+(?:at|to)\s+the|published\s+as|copyright\s)", s, re.I):
        return None
    for _ in range(3):
        s2 = _LEAD_BOILER.sub("", s)
        if s2 == s:
            break
        s = s2
    s = _MID_NOISE.sub("", s)
    head = re.split(r"(?<=[.])\s", s, maxsplit=1)[0]
    head = _LEAD_SPLIT.split(head, maxsplit=1)[0]
    if len(head) > 56:
        head = re.split(r",\s", head, maxsplit=1)[0]
    if len(head) > 56:
        p = head.rfind(" ", 0, 56)
        head = head[:p if p > 26 else 56]
    head = head.strip(" .,;:—-")
    if len(head) < 8:
        return None
    words = head.split()
    # 「Accurate」这种单个形容词不是主题；要有具体名词（>=2 词或含大写专名）
    if len(words) < 2:
        return None
    if len(words) < 3 and not any(w[:1].isupper() for w in words):
        return None
    return head[0].upper() + head[1:] + " …"


def _title_quality(t):
    if not t:
        return 0
    score = 0
    n = len(t)
    if 25 <= n <= 160:
        score += 3
    elif 15 <= n <= 220:
        score += 1
    if re.search(r"[A-Za-z]{3,}", t):
        score += 1
    # 末尾是介词/冠词，说明句子被截断了
    if re.search(r"\b(?:on|of|for|in|at|to|with|via|the|a|an|and|by|from)$", t, re.I):
        score -= 3
    # 含上标符号，说明作者混进来了
    if re.search(r"[∗†‡§⋆]|\d,", t):
        score -= 4
    # 含邮箱
    if "@" in t:
        score -= 5
    # 以数字开头（页码/章节号）
    if re.match(r"^\d+\s", t):
        score -= 2
    return score


def build(force=False):
    if not os.path.exists(TEXT_INDEX):
        print("缺少 pdf_text_index.json，请先运行 build_text_index.py")
        return False
    idx = json.load(open(TEXT_INDEX, encoding="utf-8"))
    papers = idx.get("papers", {})

    old = {}
    if not force and os.path.exists(OUT):
        try:
            od = json.load(open(OUT, encoding="utf-8"))
            old = od.get("papers", {})
            print(f"已有索引 {len(old)} 条，按 mtime 增量更新")
        except Exception:
            old = {}

    out = {}
    done = 0
    t0 = time.time()
    for path, rec in papers.items():
        # 键可能是 `{kb}/...` 相对形式（换电脑也能用），解析 PDF 要用本机绝对路径；
        # 元数据字典的键与全文索引保持一致，方便两边对照。
        try:
            import kb_paths
            real = kb_paths.to_abs(path)
        except Exception:
            real = path
        text = rec.get("text", "") or ""
        mt = rec.get("mtime", 0)

        # 增量：mtime 与已存一致就复用
        prev = old.get(path)
        if prev and abs(prev.get("_mtime", -1) - mt) < 1e-6:
            prev.pop("_mtime", None)
            out[path] = prev
            continue

        r = paper_meta.extract(real, text)
        t_pdf = r["title"]
        t_file = title_from_filename(real)

        q = _title_quality(t_pdf)
        if q >= 3:
            title, src = t_pdf, "pdf"
        elif t_file:
            title, src = t_file, "filename"
        elif t_pdf:
            title, src = t_pdf, "pdf-low"
        else:
            title, src = None, "none"
            # 两路都失败时，至少给个可读的（文件名去扩展名）
            stem = os.path.splitext(os.path.basename(real))[0]
            if len(stem) >= 3:
                title, src = stem, "stem"

        # ── 兜底：标题仍是 "ICCV2025-36" 这种编号时，用摘要首句代替 ──
        # 用户看到编号完全无法判断这是什么论文，看到摘要首句至少能认出来。
        # 这类文件多是 ICCV/CVPR 投稿编号，PDF 首行提取失败（双栏拼接问题）。
        # 语义检索靠摘要，不受标题影响。
        if src in ("stem", "none", "filename") and _is_junk_title(title):
            sub = _title_from_abstract(r.get("abstract") or "")
            if sub:
                title, src = sub, "abstract"
        # pdf-low 有两种坏法：编号残片、从作者行中间截出来。后者更常见。
        elif src == "pdf-low" and (_is_junk_title(title) or _looks_like_author_line(title)):
            sub = _title_from_abstract(r.get("abstract") or "")
            if sub:
                title, src = sub, "abstract"
        # pdf / filename 也可能整段是摘要正文（双栏拼接把 Abstract 之后的内容
        # 当成了标题）。_GARBAGE_TITLE 现在会认「We present / This paper…」，
        # 但这里要先判、再降级，否则坏标题会一路通过。
        if title and src in ("pdf", "pdf-low", "filename", "stem"):
            try:
                import paper_meta as _PM
                if _PM._is_garbage_title(title):
                    sub = _title_from_abstract(r.get("abstract") or "")
                    if sub:
                        title, src = sub, "abstract"
                    else:
                        title, src = None, "none"
            except Exception:
                pass

        out[path] = {
            "title": title,
            "title_src": src,
            "authors": r["authors"],
            "abstract": r["abstract"],
            "year": r["year"],
            "venue": r["venue"],
            "is_survey": r["is_survey"],
            "has_text": r["has_text"],
            "_mtime": mt,
        }
        # 2026-11-15 修：作者串必须用**最终标题**重新定位一次。
        # 上面 r["authors"] 是按 paper_meta.extract_title() 抽到的标题切出来的，
        # 而最终写进 title 的往往来自文件名或摘要（extract_title 返回 None 时）。
        # 那一路没有标题可用，extract_authors 会退化成「从正文 25% 处开始找」，
        # 于是标题尾巴被当成作者名 —— 实测 343 篇里 3 篇出
        # "Mamba Andong Lu, ..." / "Applications Bhawna Goyal, ..." 这种脏数据。
        if title and r.get("authors"):
            try:
                re_au = paper_meta.extract_authors(text, title)
                if re_au:
                    out[path]["authors"] = re_au
            except Exception:
                pass
        done += 1
        if done % 50 == 0:
            print(f"  已处理 {done} 篇…")

    # 清理 _mtime（对外不暴露内部字段）
    for v in out.values():
        v.pop("_mtime", None)

    payload = {
        "version": 1,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(out),
        "papers": out,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    # ── 统计 ──
    n = len(out)
    has_t = sum(1 for v in out.values() if v.get("title"))
    has_a = sum(1 for v in out.values() if v.get("abstract"))
    has_u = sum(1 for v in out.values() if v.get("authors"))
    from collections import Counter
    srcs = Counter(v.get("title_src") for v in out.values())

    print()
    print("=" * 56)
    print(f"写入 {OUT}")
    print(f"  条目 {n} 篇   新增/更新 {done}   耗时 {time.time()-t0:.1f}s")
    print(f"  标题 {has_t} ({100*has_t/max(n,1):.0f}%)   摘要 {has_a} ({100*has_a/max(n,1):.0f}%)   作者 {has_u} ({100*has_u/max(n,1):.0f}%)")
    print(f"  标题来源: " + "  ".join(f"{k}={v}" for k, v in srcs.most_common()))
    print("=" * 56)
    return True


if __name__ == "__main__":
    build(force="--force" in sys.argv)