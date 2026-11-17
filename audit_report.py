#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成学科边界抽查的最终报告（给人看的版本）。

把「判据 → 误判 → 修正 → 复核」的完整链条写下来，
便于日后追溯：为什么这个人被剔除、依据是什么。
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import remap_advisors as R       # noqa: E402
import refine_boundary as FB     # noqa: E402

FULL = HERE / "advisor_directory_full.json"
BACKUP = HERE / "backup" / "advisor_directory_full.json.bak"
OUT = HERE / "exports" / "学科边界抽查报告.md"


def main():
    cur = json.loads(FULL.read_text(encoding="utf-8"))
    adv = cur.get("advisors", [])
    stats = cur.get("mapping_stats", {})
    back = json.loads(BACKUP.read_text(encoding="utf-8")).get("advisors", []) \
        if BACKUP.exists() else []

    rescued = [a for a in adv if a.get("mapping") == "rescued"]
    excluded = len(stats.get("excluded_non_cs", 0)) if isinstance(
        stats.get("excluded_non_cs"), list) else stats.get("excluded_non_cs", 0)

    lines = []
    lines.append("# 学科边界抽查报告\n")
    lines.append("> 口径：以计算机为主，允许交叉融合（AI4Science / 医学影像 / 脑机接口…），")
    lines.append("> 排除「只是用计算机当工具、研究本身不属于计算机」的学科。\n")

    lines.append("## 一、为什么要抽查\n")
    lines.append("学科边界判定只看了 OpenAlex 的**主题名**，看不到论文内容，")
    lines.append("必然存在两类风险：误删真做计算机的人、误留用计算机当工具的人。")
    lines.append("抽查的目的就是量化这个误差，而不是证明判据正确。\n")

    lines.append("## 二、抽查方法与结果\n")
    lines.append("从被判为「纯非计算机」的样本中随机抽取，用 **ORCID** 定位学者真实身份")
    lines.append("（不能用姓名——实测「Songtao Liu」会被匹配到 YOLOX 作者这类同名人），")
    lines.append("拉取其被引最高的论文及其发表 venue。\n")
    lines.append("| 轮次 | 样本 | 发现 | 修正 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| 第 1 轮（关键词判据 v1） | 25 人 | **约 24% 误删**，含 Songtao Liu（YOLOX 作者） | 改为「出现 CS 方法线索即保留」 |")
    lines.append("| 第 2 轮（关键词判据 v2） | 15 人 | 仍有误删：Yang Yu（IEEE EuroS&P）、Fang Wang（IEEE TFS） | **引入 venue 裁决** |")
    lines.append("| 第 3 轮（venue 裁决） | 833 个候选 | 406 个被翻案 | 收紧 venue 白名单 |")
    lines.append("| 第 4 轮（venue 白名单收紧） | 11 个边界用例 | 10/11 正确，补 1 条规则 | 当前版本 |\n")

    lines.append("## 三、最终判据\n")
    lines.append("```")
    lines.append("1. 关键词初判：主题里出现计算机方法线索 → 保留")
    lines.append("2. 对准备剔除的人，用 ORCID 拉真实发表 venue")
    lines.append("3. venue 命中计算机场所（CVPR/NeurIPS/TPAMI/TSE…）→ 翻案保留")
    lines.append("4. 拉不到数据的 → 保守保留（宁可多留，不可误删）")
    lines.append("```\n")

    lines.append("**关键教训**：`vente` 白名单里不能放 `computational` 这类宽泛词——")
    lines.append("它会把 *Polish Journal of Environmental Studies*、*SAGE Open* 也算成计算机。\n")

    lines.append("## 四、最终数据\n")
    lines.append("| 项目 | 数值 |")
    lines.append("| --- | --- |")
    lines.append("| 原始抓取 | %d 位 |" % len(back))
    lines.append("| 关键词初判剔除候选 | 833 位 |")
    lines.append("| venue 翻案保留 | %d 位 |" % len(rescued))
    lines.append("| 维持剔除 | %s 位 |" % excluded)
    lines.append("| 最终索引 | **%d 位** |" % len(adv))
    lines.append("")

    lines.append("## 五、复核方法（你可以自己核）\n")
    lines.append("```powershell")
    lines.append("# 抽样检查被剔除的人，看他们的代表作发表在哪个 venue")
    lines.append("python audit_boundary.py --n 20 --fetch")
    lines.append("")
    lines.append("# 对全部剔除候选重新做 venue 裁决")
    lines.append("python refine_boundary.py --dry-run")
    lines.append("```\n")
    lines.append("抽查结果保存在 `exports/学科边界抽查.json`。\n")

    if rescued:
        lines.append("## 六、被判据纠正回来的典型例子\n")
        random.seed(3)
        for a in random.sample(rescued, min(5, len(rescued))):
            lines.append("- **%s**（%s）：主题为 %s" % (
                a.get("name"), a.get("institution"),
                "、".join((a.get("keywords") or [])[:2]) or "—"))
        lines.append("")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("报告已生成:", OUT)


if __name__ == "__main__":
    main()