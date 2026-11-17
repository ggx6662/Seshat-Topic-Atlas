"""检索日志里的冷门词 → 词表缺口清单（给出可直接粘的补丁）。

为什么要这个脚本
----------------
`search_log.cold_terms()` 会记下「用户搜了、但几乎查不到」的词。这些词
要么是用户拼错了，要么是词表真的缺。前者不能进词表（会把错误固化），
后者进词表能立刻改善检索。这个脚本把一次人工复核变成一件十秒钟的事：

  python tools_cold_terms.py            # 看清单 + 可直接粘进代码的补丁
  python tools_cold_terms.py --json     # 给脚本用

判断规则（保守，宁可漏也不误加）：
  · 整句已在中文键里                     → 标记「已有」，说明是检索排序问题
  · 能拆成「已知的前缀/后缀 + 未知的词」   → 给出要补的具体词，不做整句硬翻译
      「红外小目标跟踪」= 红外 ✓ + 小目标 ✓ + 跟踪 ✓，整句 0 命中
      说明缺的不是词，而是「多段查询的组合方式」—— 这种不补词表
  · 未知部分是中文字符串（≥2 字）         → 列入「待补 CN2EN」
  · 纯英文、单/双词、不在同义组里         → 列入「待补 _SYN」

**不自动改代码。** 词表是手工维护的常量表，自动追加会破坏可读性，
也容易把一次误输入永久固化。这个脚本只负责把该补的挑出来。
"""
import json
import re
import sys

import arxiv_latest as A
import kb_vector
import search_log


def _cn_keys():
    try:
        return [k for k in A.CN2EN if re.search(r"[\u4e00-\u9fff]", k)]
    except Exception:
        return []


def _segment(term, keys):
    """把中文查询切成「已知键 / 未知片段」，返回未知片段列表。

    用最长匹配：`红外小目标跟踪` 在 红外/小目标/跟踪 都在表里时应该切干净，
    而不是因为「红外小」不在表里就把整句当未知。
    """
    keys = sorted(keys, key=len, reverse=True)
    unknown = []
    i = 0
    while i < len(term):
        hit = None
        for k in keys:
            if term.startswith(k, i):
                hit = k
                break
        if hit:
            i += len(hit)
        else:
            j = i + 1
            while j < len(term) and not any(term.startswith(k, j) for k in keys):
                j += 1
            unknown.append(term[i:j])
            i = j
    return unknown


def analyze(min_count=2, n=40):
    cold = search_log.cold_terms(n=n, min_count=min_count)
    cn_keys = _cn_keys()
    syn_keys = set(kb_vector._SYN) | set(kb_vector._SYN_GROUP)
    out = []
    for r in cold:
        term = (r.get("term") or "").strip()
        if not term:
            continue
        row = dict(r)
        if re.search(r"[\u4e00-\u9fff]", term):
            if len(term) < 2:
                row["suggest"], row["why"], row["add"] = "skip", "单字查询，多半是手滑", ""
            elif term in A.CN2EN:
                row["suggest"] = "exists"
                row["why"] = "整句已是中文键，说明是检索排序问题，不是词表缺"
                row["add"] = ""
            else:
                unknown = _segment(term, cn_keys)
                if not unknown:
                    row["suggest"] = "combo"
                    row["why"] = "每个词都在表里，缺的是多段组合方式（不建议补词表）"
                    row["add"] = ""
                elif all(len(u) >= 2 for u in unknown):
                    row["suggest"] = "cn"
                    row["why"] = "词表里没有：" + " / ".join(unknown)
                    row["add"] = unknown[0]
                else:
                    row["suggest"] = "skip"
                    row["why"] = "切出单字碎片 " + " / ".join(unknown) + "，多半是拼接词"
                    row["add"] = ""
        else:
            words = [w for w in re.split(r"[\s\-_]+", term.lower()) if w]
            if not words:
                row["suggest"], row["why"], row["add"] = "skip", "空查询", ""
            elif len(words) > 2:
                row["suggest"] = "phrase"
                row["why"] = "长短语，先拆词再查"
                row["add"] = ""
            elif any(w in k for k in syn_keys for w in words):
                row["suggest"] = "exists"
                row["why"] = "同义组里已有这个词"
                row["add"] = ""
            else:
                row["suggest"] = "en"
                row["why"] = "英文词不在同义组里"
                row["add"] = words[0]
        out.append(row)
    return out


def main():
    rows = analyze()
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        st = search_log.stats()
        if not st.get("exists") or not st.get("terms"):
            print("检索日志还是空的 —— 先在软件里搜几次，再回来看这里。")
        else:
            print("暂时没有需要补的冷门词：日志里有 %d 个词，但都还没到「搜得多、查得少」的门槛（%d 次）。"
                  % (st["terms"], search_log.WARM_MIN_COUNT))
            top = search_log.top_terms(n=8)
            if top:
                print("当前搜得最多的：")
                for r in top:
                    avg = r.get("hits", 0) / float(max(1, r.get("count", 0)))
                    print("  %-20s 搜 %2d 次 · 平均命中 %.0f 条"
                          % (r["term"], r["count"], avg))
        return
    order = {"cn": 0, "en": 1, "phrase": 2, "combo": 3, "exists": 4, "skip": 5}
    rows.sort(key=lambda r: (order.get(r["suggest"], 9), -r["count"]))
    tag = {"cn": "[补中文]", "en": "[补英文]", "phrase": "[拆词]",
           "combo": "[组合]", "exists": "[已有]", "skip": "[跳过]"}
    for r in rows:
        print("%-7s %-22s 搜 %2d 次 · 命中 %3d · 零结果 %2d   %s"
              % (tag.get(r["suggest"], "?"), r["term"], r["count"],
                 r["hits"], r["zero"], r["why"]))
    todo = [r for r in rows if r["suggest"] in ("cn", "en")]
    if todo:
        print("\n可直接追加到词表（自己挑，别全加）：")
        for r in todo:
            if r["suggest"] == "cn":
                print('  CN2EN["%s"] = ""      # 检索 %d 次 / 零结果 %d'
                      % (r["add"], r["count"], r["zero"]))
            else:
                print('  _SYN["%s"] = []         # 检索 %d 次 / 零结果 %d'
                      % (r["add"], r["count"], r["zero"]))
        print("\n补完请跑 python tools_cold_terms.py 确认这一项变成 [已有]。")


if __name__ == "__main__":
    main()