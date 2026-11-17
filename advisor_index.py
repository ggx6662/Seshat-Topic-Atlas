#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导师索引合并层：把旧索引与全量索引合在一起对外提供。

为什么不直接改 kb_widget
------------------------
kb_widget.py 是原桌面卡片的入口，改动它风险大且两边耦合。
这里做一层只增不改的包装，两套界面都能用上新数据：

  advisor_directory.json             人工整理的 58 位代表性学者（优先）
  advisor_directory_generated.json   OpenAlex 前 400 所院校（旧）
  advisor_directory_full.json        全量院校扩充（新，可能还在抓取中）

同一位学者在多份文件里出现时，保留信息更完整的那条。
"""

import json
import math
import re
import threading
import time
from pathlib import Path

try:
    import topic_neighbors
except Exception:          # 单独运行该模块调试时可能没有路径
    topic_neighbors = None

HERE = Path(__file__).resolve().parent
try:
    import app_paths as P
    _RES = P.res        # 只读资源：打包后在 _MEIPASS
    _DATA = P.data      # 可写数据：打包后在 exe 旁边
except Exception:       # 单独跑构建脚本时也不至于炸
    _RES = lambda n: HERE / n
    _DATA = lambda n: HERE / n
CURATED = _RES("advisor_directory.json")
GENERATED = _RES("advisor_directory_generated.json")
FULL = _RES("advisor_directory_full.json")
# arXiv 补充源：OpenAlex 主题颗粒度太粗，用它补齐细分方向（见 fetch_arxiv_advisors.py）
ARXIV = _RES("advisor_arxiv.json")

_lock = threading.Lock()
_cache = {"sig": None, "rows": None, "full_count": 0, "inst_count": 0}


def _sig(*paths):
    out = []
    for p in paths:
        try:
            out.append(p.stat().st_mtime_ns)
        except OSError:
            out.append(0)
    return tuple(out)


def _score(a):
    """信息完整度：字段是否齐全优先，其次看学术影响力。"""
    filled = sum(1 for k in ("homepage", "orcid", "lab", "province", "cited_by_count")
                 if a.get(k))
    return (
        filled,
        1 if a.get("cited_by_count") else 0,
        1 if a.get("homepage") else 0,
        len(a.get("fields") or []),
        a.get("cited_by_count") or 0,
    )


def _merge(rows):
    """去重并合并字段。

    去重键优先级：ORCID > 「姓名 + 引用量」> 「姓名 + 院校」。

    —— 为什么加「姓名 + 引用量」这一档 ——
    OpenAlex 会把同一位学者（尤其是没填 ORCID 的）重复挂到多所院校下，
    这些记录的引用量、论文数**完全相同**，是同一条数据的复制。
    实测「Yi Zhou」有 10 条记录引用量都是 1354，分散在 10 所学校；
    只按姓名+院校去重，推荐结果里同一个人会连着出现 10 次。
    引用量完全相同 + 同名，基本可判定为同一人的重复记录。

    保留一条代表记录（信息最全的那条），并把院校列表并存到
    `institutions_all`，不丢信息。
    """
    best = {}
    order = []
    insts = {}

    def key_of(a):
        name = " ".join((a.get("name") or "").split()).lower()
        if not name:
            return None
        orcid = (a.get("orcid") or "").strip().lower()
        if orcid:
            return ("orcid", orcid)
        cited = a.get("cited_by_count")
        works = a.get("works_count")
        if cited and works:
            # 同名 + 同引用 + 同论文数 → 同一人的重复记录
            return ("cited", name, int(cited), int(works))
        iid = (a.get("institution_id") or "").strip()
        inst = " ".join((a.get("institution") or "").split()).lower()
        return (name, iid or inst)

    for a in rows:
        k = key_of(a)
        if not k:
            continue
        if k not in best:
            best[k] = dict(a)
            order.append(k)
            insts[k] = set()
        if a.get("institution"):
            insts[k].add(a["institution"])
        cur = best[k]
        # 同一 ORCID 的多个记录：保留信息最全的那条做主体，
        # 但院校/省份必须与引用量来自同一条记录，不能交叉拼接
        # （否则会出现「同济的 Gang Li 被填上武汉的省份」）
        is_orcid_key = k[0] == "orcid"
        if is_orcid_key:
            # 同一 ORCID 的多条记录通常来自不同抓取批次（院校可能已变更）。
            # 选引用量最高的一条做主体 —— 那通常是他任职最久/最主要的单位。
            # 这里只用三个标量比较，不再调用 _score()：
            # 实测 2.6 万次 rank() 里大部分开销来自反复遍历字典求完整度。
            if (a.get("cited_by_count") or 0, a.get("works_count") or 0) > \
               (cur.get("cited_by_count") or 0, cur.get("works_count") or 0):
                merged = dict(a)
                for kk, vv in cur.items():
                    if not merged.get(kk) and vv:
                        merged[kk] = vv
                best[k] = merged
            else:
                for kk, vv in a.items():
                    if not cur.get(kk) and vv:
                        cur[kk] = vv
        else:
            for kk, vv in a.items():
                if not cur.get(kk) and vv:
                    cur[kk] = vv

    out = []
    for k in order:
        item = best[k]
        names = insts.get(k) or set()
        if len(names) > 1:
            item["institutions_all"] = sorted(names)
        out.append(item)

    # 最后一道收口：同名 + 同院校 的重复（数据来自不同批次/不同索引）。
    # 实测有 1266 组，会让推荐列表里同一个人重复出现。
    final = {}
    final_order = []
    for a in out:
        key = (" ".join((a.get("name") or "").split()).lower(),
               " ".join((a.get("institution") or "").split()).lower())
        if key not in final:
            final[key] = a
            final_order.append(key)
        else:
            cur = final[key]
            # 保留引用量更高的那条（通常是最新、最完整的一次抓取）
            if (a.get("cited_by_count") or 0) > (cur.get("cited_by_count") or 0):
                for kk, vv in cur.items():
                    if not a.get(kk) and vv:
                        a[kk] = vv
                final[key] = a
            else:
                for kk, vv in a.items():
                    if not cur.get(kk) and vv:
                        cur[kk] = vv
    return [final[k] for k in final_order]


def _institution_regions():
    """机构名 → 省级地区。用于修复源数据里 province 为空的导师记录。"""
    try:
        data = json.loads((_RES("institutions_cn.json")).read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for inst in data.get("institutions", []):
        name = (inst.get("name") or "").strip()
        region = inst.get("region")
        if name and region:
            out[name] = region
    return out


def _normalize_institution(name):
    """把带院系后缀的院校名归一到母体。

    人工样本里写的是 "Stanford CS"、"Tsinghua CS"、"UC Berkeley EECS"，
    而 OpenAlex 里是 "Stanford University"、"Tsinghua University"。
    不归一的话，同一所学校会被拆成两所，
    按院校筛选、按院校统计都会算错。
    """
    if not name:
        return name
    n = name.strip()
    rules = [
        ("Stanford CS", "Stanford University"),
        ("Stanford University", "Stanford University"),
        ("Tsinghua CS", "Tsinghua University"),
        ("Peking University CS", "Peking University"),
        ("Princeton CS", "Princeton University"),
        ("Shanghai Jiao Tong CS", "Shanghai Jiao Tong University"),
        ("UC Berkeley EECS", "University of California, Berkeley"),
        ("UIUC CS", "University of Illinois Urbana-Champaign"),
        ("University of Washington CSE", "University of Washington"),
        ("HKUST CSE", "Hong Kong University of Science and Technology"),
        ("Oxford CS", "University of Oxford"),
        ("Cambridge CS", "University of Cambridge"),
        ("EPFL CS", "École Polytechnique Fédérale de Lausanne"),
        ("MIT CSAIL", "Massachusetts Institute of Technology"),
        # 院系/校区级缩写 → 母体院校（人工样本里常见）
        ("CMU SCS", "Carnegie Mellon University"),
        ("CMU", "Carnegie Mellon University"),
        ("ETH Zurich D-INFK", "ETH Zurich"),
        ("ETH Zurich", "ETH Zurich"),
        ("NUS Computing", "National University of Singapore"),
        ("NUS", "National University of Singapore"),
        ("NTU", "Nanyang Technological University"),
        ("HKUST", "The Hong Kong University of Science and Technology"),
        ("CUHK", "The Chinese University of Hong Kong"),
        ("HKU", "The University of Hong Kong"),
        ("PolyU", "The Hong Kong Polytechnic University"),
        ("CityU", "City University of Hong Kong"),
        ("KAUST", "King Abdullah University of Science and Technology"),
        ("TUM", "Technische Universität München"),
        ("UCL", "University College London"),
        ("Imperial College", "Imperial College London"),
        ("Caltech", "California Institute of Technology"),
        ("MIT", "Massachusetts Institute of Technology"),
        ("Stanford", "Stanford University"),
        ("Berkeley", "University of California, Berkeley"),
        ("Columbia", "Columbia University"),
        ("Princeton", "Princeton University"),
        ("Yale", "Yale University"),
        ("Harvard", "Harvard University"),
        ("Oxford", "University of Oxford"),
        ("Cambridge", "University of Cambridge"),
        ("Tsinghua", "Tsinghua University"),
        ("Peking University", "Peking University"),
    ]
    for suffix, full in rules:
        if n == suffix:
            return full
    return n


def _normalize_cn_name(name):
    """修正中文姓名的「名 姓」倒序写法。

    OpenAlex 对中文作者常输出 "茜 王"（名在前、姓在后，中间空格），
    正确写法应是 "王茜"。实测有 45 条。
    只处理「纯中文 + 单个空格分隔」的情况，英文名一律不动。
    """
    if not name:
        return name
    m = re.fullmatch(r"([\u4e00-\u9fff]{1,3})\s+([\u4e00-\u9fff]{1,2})", name.strip())
    if m:
        given, surname = m.group(1), m.group(2)
        return surname + given
    return name


# 归一化后的境外院校没有省份（它们不在中国院校目录里），
# 但因为「可推荐学者」要求有省份，会导致斯坦福、MIT 这类顶级学者被过滤掉。
# 这里给常见境外院校补上国家/地区标识。
FOREIGN_REGIONS = {
    "Stanford University": "美国",
    "University of California, Berkeley": "美国",
    "Massachusetts Institute of Technology": "美国",
    "Carnegie Mellon University": "美国",
    "Princeton University": "美国",
    "University of Washington": "美国",
    "University of Illinois Urbana-Champaign": "美国",
    "Cornell University": "美国",
    "Georgia Institute of Technology": "美国",
    "University of Michigan": "美国",
    "University of Texas at Austin": "美国",
    "University of Maryland": "美国",
    "University of California, San Diego": "美国",
    "University of California, Los Angeles": "美国",
    "University of Southern California": "美国",
    "The University of Hong Kong": "香港",
    "Hong Kong University of Science and Technology": "香港",
    "Chinese University of Hong Kong": "香港",
    "City University of Hong Kong": "香港",
    "University of Oxford": "英国",
    "University of Cambridge": "英国",
    "Imperial College London": "英国",
    "University College London": "英国",
    "University of Edinburgh": "英国",
    "ETH Zurich D-INFK": "瑞士",
    "École Polytechnique Fédérale de Lausanne": "瑞士",
    "Max Planck Institute for Intelligent Systems": "德国",
    "Technische Universität München": "德国",
    "University of Toronto": "加拿大",
    "University of Waterloo": "加拿大",
    "McGill University": "加拿大",
    "National University of Singapore": "新加坡",
    "Nanyang Technological University": "新加坡",
    "The University of Tokyo": "日本",
    "Kyoto University": "日本",
    "Seoul National University": "韩国",
    "KAIST": "韩国",
    "University of Sydney": "澳大利亚",
    "University of Melbourne": "澳大利亚",
    "Monash University": "澳大利亚",
    "University of New South Wales": "澳大利亚",
}


# 两位国家代码 → 中文地区名（arXiv 补充的境外学者用这个兜底）
COUNTRY_ZH = {
    "CN": "中国", "US": "美国", "GB": "英国", "DE": "德国", "FR": "法国",
    "CH": "瑞士", "CA": "加拿大", "AU": "澳大利亚", "JP": "日本", "KR": "韩国",
    "SG": "新加坡", "HK": "香港", "TW": "台湾", "MO": "澳门", "IT": "意大利",
    "ES": "西班牙", "NL": "荷兰", "SE": "瑞典", "NO": "挪威", "DK": "丹麦",
    "FI": "芬兰", "AT": "奥地利", "BE": "比利时", "IE": "爱尔兰", "IL": "以色列",
    "IN": "印度", "RU": "俄罗斯", "BR": "巴西", "NZ": "新西兰", "PT": "葡萄牙",
}


_DISK_CACHE = _DATA(".cache_advisors.json")


def _disk_cache_load(sig):
    """读合并结果的磁盘缓存。

    合并 4 个文件（约 25 MB、2.7 万条）要 0.34 秒，而结果只在源文件变化时才变。
    把合并后的结果缓存到磁盘，启动时直接读 —— 实测从 0.34s 降到 0.03s。
    缓存失效条件：任一源文件或院校目录的修改时间变化。
    """
    try:
        raw = json.loads(_DISK_CACHE.read_text(encoding="utf-8"))
        if raw.get("sig") == list(sig):
            return raw.get("rows")
    except Exception:
        pass
    return None


def _disk_cache_save(sig, rows):
    try:
        # 只存必要字段，避免把 _kw_blob 这类派生值也写进去
        slim = []
        for a in rows:
            slim.append({k: v for k, v in a.items()
                         if not k.startswith("_") or k == "_complete"})
        _DISK_CACHE.write_text(json.dumps(
            {"sig": list(sig), "rows": slim}, ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        pass


def load_all():
    """返回合并后的全部导师（含全量索引）。

    顺带做一次地区回填：OpenAlex 有 618 所院校缺 region 字段，
    这些院校的导师 province 为空，会从按省份筛选里漏掉。
    院校目录已用城市→省份补齐，这里按机构名回填到导师记录上。

    同时在每条记录上预计算两项派生字段，避免在推荐循环里重复判断：
      _complete  画像是否完整（可推荐）
      _kw_blob   关键词小写拼接（用于标签可信度检查）
    """
    sig = _sig(CURATED, GENERATED, FULL, ARXIV, _RES("institutions_cn.json"))
    with _lock:
        if _cache["sig"] == sig:
            return _cache["rows"]

    # 先试磁盘缓存：合并 4 个文件要 0.34 秒，结果只在源文件变化时才变
    cached_rows = _disk_cache_load(sig)
    if cached_rows:
        with _lock:
            _cache.update(sig=sig, rows=cached_rows, full_count=0, inst_count=0)
        return cached_rows

    rows = []
    for p, key in ((CURATED, "advisors"), (GENERATED, "advisors"),
                   (FULL, "advisors"), (ARXIV, "advisors")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            rows.extend(data.get(key, []) or [])
        except Exception:
            continue

    # 院校名归一必须放在合并**之前**：
    # "Stanford CS" 与 "Stanford University" 是同一所学校，
    # 先去重再归一，会把同一位学者的两条记录当成两个人。
    for a in rows:
        a["institution"] = _normalize_institution(a.get("institution"))

    merged = _merge(rows)
    # 省份一律以院校目录为准（城市→省份已人工补齐过）。
    # 旧索引里存在错误省份（同济的 Gang Li 被记成湖北），
    # 不能让它覆盖院校目录的正确值。
    regions = _institution_regions()
    try:
        import check_profile as CP
    except Exception:
        CP = None

    # 只遍历一次：省份回填、姓名归一、关键词拼接、完整度判断、
    # 统计聚合（地区/院校集合/可推荐数）全部在同一次循环里完成。
    #
    # 完整度判断内联展开，不调用 check_profile.is_complete()：
    # 实测 1.8 万次调用加 5 次字段检查共 0.28 秒，是冷启动第二大开销。
    prov_set = set()
    inst_set = set()
    complete = 0
    for a in merged:
        inst = a.get("institution", "")
        r = regions.get(inst)
        if r:
            a["province"] = r
        elif not a.get("province"):
            # 境外院校：先查固定表，再用两位国家代码兜底
            if inst in FOREIGN_REGIONS:
                a["province"] = FOREIGN_REGIONS[inst]
            elif a.get("country"):
                a["province"] = COUNTRY_ZH.get(
                    str(a["country"]).upper(), a["country"])
        # 中文姓名倒序修正（"茜 王" → "王茜"）
        a["name"] = _normalize_cn_name(a.get("name"))
        # 预计算：推荐循环里会用到，放在这里只算一次
        a["_kw_blob"] = " ".join(a.get("keywords") or []).lower()

        # 画像完整：姓名 / 院校 / 省份 / 大类 / 方向 / 发表记录。
        # 发表记录的判定与 check_profile 保持一致：看引用量（cited_by_count > 0），
        # 不看论文数 —— 否则引用为 0、只有 1 篇论文的人也会被算作「完整」，
        # 两边口径不一致会让界面数字对不上（实测差 509 人）。
        ok = bool(
            a.get("name") and a.get("institution") and a.get("province")
            and a.get("category") and (a.get("fields") or [])
            and (a.get("cited_by_count") or 0) > 0
        )
        a["_complete"] = ok
        if ok:
            complete += 1

        if a.get("province"):
            prov_set.add(a["province"])
        if inst:
            inst_set.add(inst)

    with _lock:
        _cache.update(sig=sig, rows=merged, full_count=0, inst_count=0)
        # 统计结果与数据同源，直接缓存，避免 stats() 再遍历一遍
        _stats_cache["sig"] = sig
        _stats_cache["data"] = {
            "advisors": len(merged),
            "complete_advisors": complete,
            "provinces": len(prov_set),
            "institutions": len(inst_set),
            "full_index_ready": FULL.exists(),
        }
    # 合并结果写盘，下次启动直接读（省下 0.34 秒）
    _disk_cache_save(sig, merged)
    return merged


_stats_cache = {"sig": None, "data": None}
_COVERAGE_CACHE = {}


def stats():
    """学者库统计。结果在 load_all 里一次遍历算好并缓存 ——
    页面切换会反复调用，重复遍历 1.8 万条记录要 0.15–0.5 秒。"""
    sig = _sig(CURATED, GENERATED, FULL, ARXIV, _RES("institutions_cn.json"))
    with _lock:
        cached = _stats_cache["data"]
        if _stats_cache["sig"] == sig and cached:
            return _fill_coverage(dict(cached))

    rows = load_all()
    # load_all 里已算好基础统计，这里只在极端情况下兜底重算
    provinces = set()
    insts = set()
    complete = 0
    for a in rows:
        if a.get("province"):
            provinces.add(a["province"])
        if a.get("institution"):
            insts.add(a["institution"])
        if a.get("_complete"):
            complete += 1

    data = {
        "advisors": len(rows),
        "complete_advisors": complete,
        "provinces": len(provinces),
        "institutions": len(insts),
        "full_index_ready": FULL.exists(),
    }
    with _lock:
        _stats_cache["sig"] = sig
        _stats_cache["data"] = data
    return _fill_coverage(dict(data))


_COVERAGE_FIELDS = {}


def field_coverage():
    """每个研究方向真正有几位学者（完整画像 / 全部）。

    为什么要这个：recommend() 查不到足够的人时，会用「大类匹配」兜底把
    列表填满 60 条 —— 用户看到的 60 位里可能只有 3 位真做这个方向。
    不给恢复数据的话，用户根本分不清「这个方向人少」和「这个方向人多但都不合」。
    """
    global _COVERAGE_FIELDS
    sig = _sig(CURATED, GENERATED, FULL, ARXIV)
    cached = _COVERAGE_FIELDS.get("data")
    if cached and _COVERAGE_FIELDS.get("sig") == sig:
        return cached

    rows = load_all()
    all_c = {}
    ok_c = {}
    for a in rows:
        complete = bool(a.get("_complete"))
        for f in (a.get("fields") or []):
            all_c[f] = all_c.get(f, 0) + 1
            if complete:
                ok_c[f] = ok_c.get(f, 0) + 1
    data = {"all": all_c, "complete": ok_c, "total": len(rows)}
    _COVERAGE_FIELDS = {"sig": sig, "data": data}
    return data


def field_count(field):
    """某个方向的学者数：(完整画像数, 全部数)。查不到返回 (0, 0)。"""
    fc = field_coverage()
    f = (field or "").strip()
    return int((fc["complete"] or {}).get(f, 0)), int((fc["all"] or {}).get(f, 0))


def _fill_coverage(data):
    """补齐「已抓取院校 / 全国院校总数」两项（覆盖进度）。

    这两个值只在数据文件变化时才变，缓存起来 ——
    原来每次调用都要重新解析 15 MB 的 advisor_directory_full.json，约 0.24 秒。
    """
    if data.get("catalog_institutions"):
        return data
    global _COVERAGE_CACHE
    sig = _sig(FULL, _RES("institutions_cn.json"))
    if _COVERAGE_CACHE.get("sig") != sig:
        covered = 0
        try:
            d = json.loads(FULL.read_text(encoding="utf-8"))
            covered = int(d.get("institution_count", 0) or 0)
        except Exception:
            covered = 0
        try:
            full_total = int(json.loads(
                (_RES("institutions_cn.json")).read_text(encoding="utf-8")).get("count", 0) or 0)
        except Exception:
            full_total = 0
        _COVERAGE_CACHE.update(sig=sig, covered=covered, total=full_total)
    data["covered_institutions"] = _COVERAGE_CACHE.get("covered", 0)
    data["catalog_institutions"] = _COVERAGE_CACHE.get("total", 0)
    data["complete"] = bool(data["catalog_institutions"]
                            and data["covered_institutions"] >= data["catalog_institutions"])
    return data


def full_index_exists():
    return FULL.exists()


def reload_cache():
    with _lock:
        _cache["sig"] = None
        _cache["rows"] = None
        _stats_cache["sig"] = None
        _stats_cache["data"] = None
    _COVERAGE_CACHE.clear()
    try:
        _DISK_CACHE.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------- 推荐
# 标签可信度检查用的计算机词表（预编译，避免在循环里反复 re.escape）
_CS_WORD_RE = None


def _cs_word_pattern():
    global _CS_WORD_RE
    if _CS_WORD_RE is None:
        words = ["computer", "neural", "learning", "vision", "image", "language",
                 "data", "algorithm", "networks", "network", "signal", "detection",
                 "models", "model", "information", "computing", "software",
                 "artificial intelligence", "deep"]
        _CS_WORD_RE = re.compile(
            r"(?<![a-z])(?:" + "|".join(re.escape(w) for w in words) + r")(?![a-z])")
    return _CS_WORD_RE


def _has_cs_word(text):
    return bool(_cs_word_pattern().search(text))


def recommend(category, field, scenario, methods, tasks, modalities, top=40,
              complete_only=True):
    """按方向匹配导师。

    打分规则与原版一致（大类 20 / 领域 35 / 关键词命中 4 分…），
    区别：
      1. 数据源是合并后的全量索引，新扩充的院校也能被检索到
      2. 默认只返回**画像完整**的学者（有院校、省份、方向、发表记录）
         —— 只给一个名字无法核验，反而制造噪音
    """
    import kb_widget as kb
    import check_profile as CP

    rows = load_all()
    if complete_only:
        rows = [a for a in rows if a.get("_complete", True)]
    try:
        rels = kb.load_research_relations()
    except Exception:
        rels = {}
    related_links = rels.get("category_related", {}) or {}
    thin = set(rels.get("thin_categories", []) or [])
    related_categories = set(related_links.get(category, []) or [])

    tokens = [category, field, scenario] + list(methods) + list(tasks) + list(modalities)
    seen, toks = set(), []
    for t in tokens:
        t = (t or "").strip() if isinstance(t, str) else ""
        if t and t.lower() not in seen:
            seen.add(t.lower())
            toks.append(t)

    out = []
    # 近邻方向：目标方向在库里没人标时，扩展到相邻方向
    near_fields = []
    if field and topic_neighbors:
        try:
            near_fields = topic_neighbors.neighbors(field)
        except Exception:
            near_fields = []
    for adv in rows:
        score = 0
        reasons = []
        cats = set(adv.get("categories") or [])
        cats.add(adv.get("category", ""))
        if category in cats and category not in thin:
            score += 20
            reasons.append("大类匹配")
        elif cats & related_categories:
            score += 18
            reasons.append("相近大类: " + sorted(cats & related_categories)[0])
        fields = adv.get("fields") or []
        if field and field in fields:
            # 领域在列表中的位置也是信号：排在第一位说明这是他的主方向。
            # 旧实现只看「在不在里面」，导致主方向大模型的人
            # 和把大模型排在第七位的人同分。
            pos = fields.index(field)
            score += 35 if pos == 0 else (30 if pos <= 2 else (24 if pos <= 4 else 18))
            reasons.append("领域匹配" if pos <= 2 else "领域匹配（次级）")
        elif near_fields and any(n in fields for n in near_fields):
            # 近邻方向命中：目标方向本身没人标（OpenAlex 颗粒度太粗时常见），
            # 就找相邻方向的人，并明确标注是「相邻方向」
            hit = next(n for n in near_fields if n in fields)
            score += 20
            reasons.append("相邻方向：" + hit)
        elif field and any(f and (field in f or f in field) for f in fields):
            score += 14
            reasons.append("领域相近")

        # 标签可信度：若原始主题与计算机毫无关系（如化学合成、粒子物理），
        # 说明方向标签是数据噪声，整体下调权重，
        # 避免「做有机化学的人」因为一个误标的目标检测标签排到真正的 CV 学者前面。
        #
        # 必须用**词边界**匹配。实测子串匹配会误判：
        #   "network" 命中 "Axially Chiral" 里的 "work"
        #   "model"   命中化学文献里的普通词
        kw_blob = adv.get("_kw_blob")
        if kw_blob is None:
            kw_blob = " ".join(adv.get("keywords") or []).lower()
        if kw_blob and not _has_cs_word(kw_blob):
            score = int(score * 0.5)
            reasons.append("注意：主题与计算机关联弱")
        hay = " ".join(list(fields) + list(adv.get("keywords") or [])).lower()
        hits = 0
        for tok in toks:
            low = tok.lower()
            if low and low in hay:
                # 关键词命中权重下调（原 4 → 2）：
                # OpenAlex 的 keyword 噪声很大，一个人只挂了个 "Speech Recognition"
                # 也能吃到这分，反而把真正做 NLP 的学者比下去。
                score += 2
                hits += 1
                if len(reasons) < 5:
                    reasons.append(tok)
        if hits >= 3:
            score += 3
            reasons.append("多维度匹配(%d)" % hits)
        if score >= 18:
            out.append({"advisor": adv, "score": min(99, score),
                        "reasons": reasons[:6],
                        "cited": adv.get("cited_by_count") or 0,
                        "works": adv.get("works_count") or 0})

    # 排序：匹配度分档（每 5 分一档），档内按学术影响力。
    #
    # 为什么不分档而直接比总分：
    #   实测出现「引用 33024 的学者排在引用 101 的人后面」——
    #   只因后者多命中一个关键词。关键词命中受 OpenAlex 标签噪声影响很大，
    #   而引用量是更难伪造的信号。所以 5 分以内的差距视为同一档，
    #   同档内以影响力排序。
    def rank_key(x):
        a = x["advisor"]
        cited = a.get("cited_by_count") or 0
        works = a.get("works_count") or 0
        impact = math.log1p(max(0, cited)) * 2.0 + math.log1p(max(0, works)) * 0.5
        tier = -(x["score"] // 5)     # 每 5 分一档
        return (tier, -impact, a.get("name", ""))

    out.sort(key=rank_key)
    return out[:top]