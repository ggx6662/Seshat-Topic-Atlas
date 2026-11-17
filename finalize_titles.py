# -*- coding: utf-8 -*-
"""标题清洗收尾：先尽力切掉作者块，切不掉或明显是版权的回退成文件名。

原则：**宁可回退成文件名，也不要留一段看着像标题其实是版权的文字**。
文件名至少是用户自己起的，能认出来是哪篇。
"""
import json
import io
import re

import build_paper_meta as B
import fix_titles as F

_OK_END = F._OK_END

P = "paper_meta.json"

# 版权页 / 期刊抬头 / 页码行 —— 命中就直接判死，不尝试修补
JUNK = re.compile(
    r"^(?:©|\(c\)|copyright|contents lists|available online|available at|"
    r"vol\.|volume|scientific reports|information sciences|the visual computer|"
    r"neurocomputing|image and vision computing|\d+\s+vol\.|"
    r"this is a pdf file|downloaded from|preprint|under review|"
    r"1\s+vol\.|available\s+online\s+at)", re.I)

# 作者块起点：**至少两个连续的 Title Case 人名**，末尾那人后紧跟
# 上标数字 / † / *。`Real-time Open-Vocabulary Object Detection Yehao Lu1*` 里
# 作者块从 `Yehao Lu1*` 开始 —— 所以要从后往前找第一个能接上的位置，
# 而不是从前往后（从前往后会停在 `Real-time` 后面）。
_TITLE_WORD = r"[A-Z][a-z]+(?:[-'][A-Za-z]+)*"
_AUTHOR_BLOCK = re.compile(
    r"((?:" + _TITLE_WORD + r"\s+){1,3}" + _TITLE_WORD +
    r"\s?[1-9](?:,[0-9])*[\*\u2020\u2021]?)")

BOILER = re.compile(
    r"\s+(?:WorldBench|Equal Contributions|Project Lead|Corresponding Author|"
    r"These authors|Work done|Dept\.|Department|University|Institute|"
    r"School of|College of|Laboratory)\b", re.I)

_DANGLING = set("""and or of for in on at to via with without using by from into
as the a an its their our is are be""".split())


def salvage(t):
    """尽力切出标题主体；判不准就返回 None（由调用方回退成文件名）。"""
    t = (t or "").strip()
    # 只剥「页码式」的前导数字（1 个或 2 个数字 + 空格后接大写字母），
    # 不能剥 `3D-MOOD` / `3M-TI` 这种本身就是标题一部分的数字。
    t = re.sub(r"^\d{1,2}\s+(?=[A-Z])", "", t).strip()
    if not t or JUNK.search(t):
        return None

    # 1) 版权/单位声明之后全丢弃
    m = BOILER.search(t)
    if m and m.start() >= 12:
        t = t[:m.start()].rstrip(" ,;:-")

    # 2) 作者块（≥2 个 Title Case 词 + 上标数字）
    #    只认「切点前一个词是学术名词」的位置 —— 标题的正常结尾词就是这些，
    #    作者名前面必然是它们之一。没有这条约束会把 `... 3D Detection` 切成 `... 3D`。
    if len(t) > 20:
        for m in _AUTHOR_BLOCK.finditer(t):
            if m.start() < 15:
                continue
            head = t[:m.start()].rstrip(" ,;:-")
            ws = head.split()
            if len(ws) < 4:
                continue
            last = ws[-1].strip(".,;:").lower()
            if last in _OK_END or head.endswith(":") or last.isdigit():
                t = head
                break

    # 2b) 命中失败时再扫一遍：作者块起点那两个字若白词是学术名词，说明正则
    #     把标题尾词吃进了人名（`Detection Olivier Moliner1` → 从 Detection 起算）。
    #     这种情况把切点往前挪一个词再试。
    if len(t) > 20 and _AUTHOR_BLOCK.search(t):
        for m in _AUTHOR_BLOCK.finditer(t):
            first = m.group(0).split()[0].lower().strip(".,;:")
            if first in _OK_END and m.start() < 15:
                continue
        # 找 `学术名词 + 人名 + 上标` 的精确位置
        m2 = re.search(r"\s(" + _TITLE_WORD + r"\s+" + _TITLE_WORD +
                       r"\s?[1-9](?:,[0-9])*[\*\u2020\u2021]?)", t)
        if m2 and m2.start() >= 15:
            prev = t[:m2.start()].split()
            if prev and prev[-1].strip(".,;:").lower() in _OK_END:
                t = t[:m2.start()].rstrip(" ,;:-")

    # 3) 仍然太长：在句号处断开
    if len(t) > 180:
        head = re.split(r"\.\s|;\s", t)[0]
        if len(head) >= 15:
            t = head

    ws = t.split()
    if len(ws) < 4 or len(t) < 14:
        return None
    # 全大写 + 很短 = 缩写碎片
    if t.isupper() and len(ws) < 6:
        return None
    # 以虚词结尾 = 切坏了
    if ws[-1].strip(".,;:").lower() in _DANGLING:
        return None
    # 小写开头 = 作者名残段
    if t[0].islower():
        return None
    return t[:180].rstrip(" ,;:-")


def main():
    d = json.load(io.open(P, encoding="utf-8"))
    ps = d["papers"]
    fixed = fallback = kept = 0
    samples_f = []
    samples_b = []
    for path, v in ps.items():
        old = (v.get("title") or "").strip()
        new = salvage(old)
        if new and new != old:
            v["title"] = new
            fixed += 1
            if len(samples_f) < 8:
                samples_f.append((old[:80], new[:80]))
        elif not new:
            fb = B.title_from_filename(path) or ""
            if fb and fb != old:
                v["title"] = fb
                v["title_src"] = "filename"
                fallback += 1
                if len(samples_b) < 10:
                    samples_b.append((old[:70], fb[:70]))
            else:
                kept += 1
        else:
            kept += 1
    json.dump(d, io.open(P, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))
    print("切掉作者:", fixed, " 回退文件名:", fallback, " 未动:", kept)
    print("\n切作者示例:")
    for a, b in samples_f:
        print("  -", a, " => ", b)
    print("\n回退示例:")
    for a, b in samples_b:
        print("  -", a, " => ", b)


if __name__ == "__main__":
    main()