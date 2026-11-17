# -*- coding: utf-8 -*-
"""按「作者名 + 上标数字」的强信号切掉标题尾巴。

信号：标题中途出现 `Word Word1` / `Word Word1*` / `Word Word1,2` 形态，
且后面还跟着更多文字 —— 那基本就是作者块的开头。
只在**标题主体已经包含冒号或长度 ≥20 字符**时才动，避免把
`... using 3D Prototypes Tom Fischer1` 这种先切坏。

另外处理 `Mind the Hitch ... 摘要与表格文字` 这类超长（>200）的：
截到最后一个能看出是标题边界的词。
"""
import json
import io
import re

P = "paper_meta.json"
TITLE_MAX = 200          # 超过这个长度几乎一定粘了作者或摘要

# 作者块起点：两个词 + 上标数字（可带 * † 或 ,2）
AUTHOR_START = re.compile(
    r"\s+(?P<name>[A-Z][a-z]+(?:-[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)+"
    r"\s?(?:1|2|3|1\*|2\*|\d,\d)[\*†\u2020]?)")

# 版权/团队声明，从这里往后全是垃圾
BOILER = re.compile(
    r"\s+(?:WorldBench|Equal Contributions|Project Lead|Corresponding Author|"
    r"These authors|Work done|Under review|Preprint|Accepted)\b", re.I)


def clean(t):
    t = (t or "").strip()
    if not t:
        return t, False
    orig = t

    # 1) 版权/团队声明之后全部丢弃
    m = BOILER.search(t)
    if m and m.start() >= 12:
        t = t[:m.start()].rstrip(" ,;:-")

    # 2) 作者块起点（至少 2 个 Title Case 词 + 上标数字）
    if len(t) > 20:
        m = AUTHOR_START.search(t)
        if m and m.start() >= 15:
            head = t[:m.start()].rstrip(" ,;:-")
            # 切完必须仍像标题：≥3 个词，且不以虚词结尾
            if len(head.split()) >= 3 and head.split()[-1].lower() not in {
                "and", "or", "of", "for", "in", "on", "at", "to", "via", "with",
                "by", "from", "into", "as", "the", "a", "an", "using"}:
                t = head

    # 3) 仍然超长：按句号/分号断，取第一段
    if len(t) > TITLE_MAX:
        for sep in (". ", "; ", "? "):
            if sep in t[:TITLE_MAX + 40]:
                cand = t.split(sep)[0]
                if len(cand) >= 15:
                    t = cand
                    break
        t = t[:TITLE_MAX].rsplit(" ", 1)[0].rstrip(" ,;:-")

    return t, t != orig


def main():
    d = json.load(io.open(P, encoding="utf-8"))
    ps = d["papers"]
    n = 0
    for v in ps.values():
        new, ch = clean(v.get("title"))
        if ch:
            v["title"] = new
            n += 1
    if n:
        json.dump(d, io.open(P, "w", encoding="utf-8"), ensure_ascii=False,
                  separators=(",", ":"))
    print("改写:", n)
    for v in list(ps.values()):
        t = v.get("title") or ""
        if len(t) > 160 or re.search(r"[A-Z][a-z]+ [A-Z][a-z]+\s?\d", t):
            print("  仍疑:", t[:150])


if __name__ == "__main__":
    main()