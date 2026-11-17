#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学者画像完整度筛选。

口径（用户定义）
----------------
在本应用里，一位「可被推荐给学生的学者」必须同时具备：

  1. 姓名
  2. 所属院校（institution）
  3. 所在省份（province）—— 学生要能按地区筛选
  4. 研究大类（category）
  5. 具体研究方向（fields）
  6. 发表记录（cited_by_count / works_count）—— 证明这人在做研究
  7. ORCID —— 唯一身份标识，可核验

缺任何一项的，都不作为「完整学者」推荐。
理由：只给一个名字和学校，学生无法核实、无法判断是否值得联系，
反而制造噪音。

实现
----
`profile_score(advisor)` 返回 0–7 的完整度与缺失项清单。
`is_complete(advisor)` 判定是否达到可推荐标准。

用法
----
python check_profile.py            # 统计当前完整度
python check_profile.py --strict   # 严格模式（要求 ORCID）
"""

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 必备字段：缺一项就不算完整画像
REQUIRED = [
    ("name", "姓名"),
    ("institution", "院校"),
    ("province", "省份"),
    ("category", "研究大类"),
    ("fields", "具体方向"),
]
# 发表记录：任一有值即可（证明在做研究）
EVIDENCE = [("cited_by_count", "引用"), ("works_count", "论文数")]
# 身份标识：可核验性最强
IDENTITY = ("orcid", "ORCID")

TOTAL_CHECKS = len(REQUIRED) + 1 + 1   # 5 必备 + 1 证据 + 1 身份


def _has(adv, key):
    if not isinstance(adv, dict):
        return False
    v = adv.get(key)
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (int, float)):
        return v > 0
    return bool(v)


def profile_score(adv):
    """返回 (完整度 0-7, 缺失项列表)。"""
    if not isinstance(adv, dict):
        adv = {}
    missing = []
    score = 0
    for key, label in REQUIRED:
        if _has(adv, key):
            score += 1
        else:
            missing.append(label)
    if any(_has(adv, k) for k, _l in EVIDENCE):
        score += 1
    else:
        missing.append("发表记录")
    if _has(adv, IDENTITY[0]):
        score += 1
    else:
        missing.append(IDENTITY[1])
    return score, missing


def is_complete(adv, strict_orcid=False):
    """是否达到「可推荐学者」标准。

    默认 strict_orcid=False：核心五项 + 发表记录齐全即可推荐。
    ORCID 只作为加分项 —— 因为它覆盖率只有 53%，一刀切要求会把
    一半真正在做研究的学者排除掉。

    strict_orcid=True 时额外要求 ORCID（可核验性最强），用于需要严格核验的场景。
    """
    required = [k for k, _l in REQUIRED] + ["cited_by_count"]
    if strict_orcid:
        required.append("orcid")
    if not isinstance(adv, dict):
        return False
    return all(_has(adv, k) for k in required)


def completeness_badge(adv):
    """给界面用的徽章文字：完整 / 部分 / 不足。"""
    score, missing = profile_score(adv)
    if score >= TOTAL_CHECKS:
        return "完整", score, missing
    if score >= TOTAL_CHECKS - 2:
        return "部分", score, missing
    return "不足", score, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="要求 ORCID")
    args = ap.parse_args()

    import advisor_index as A
    A.reload_cache()
    rows = A.load_all()
    print("合并后学者: %d" % len(rows))
    print()

    print("=== 字段齐全率 ===")
    for key, label in REQUIRED + [IDENTITY] + EVIDENCE:
        n = sum(1 for a in rows if _has(a, key))
        print("  %-10s %6d (%.0f%%)" % (label, n, 100.0 * n / max(1, len(rows))))
    print()

    dist = collections.Counter()
    for a in rows:
        s, _ = profile_score(a)
        dist[s] += 1
    print("=== 完整度分布（满分 %d）===" % TOTAL_CHECKS)
    for s in range(TOTAL_CHECKS, -1, -1):
        if dist[s]:
            print("  %d/%d  %6d (%.0f%%)" % (s, TOTAL_CHECKS, dist[s],
                                            100.0 * dist[s] / len(rows)))
    print()

    ok = [a for a in rows if is_complete(a, strict_orcid=args.strict)]
    print("达到可推荐标准: %d / %d (%.0f%%)%s"
          % (len(ok), len(rows), 100.0 * len(ok) / max(1, len(rows)),
             "（严格：含 ORCID）" if args.strict else ""))

    # 缺失原因统计
    miss = collections.Counter()
    for a in rows:
        if is_complete(a, strict_orcid=args.strict):
            continue
        _s, m = profile_score(a)
        for x in m:
            miss[x] += 1
    if miss:
        print("\n未达标者的主要缺失:")
        for k, v in miss.most_common():
            print("  %-10s %6d" % (k, v))


if __name__ == "__main__":
    main()