#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""选题的「硬约束」检查：这条题你到底做不做得动。

和 topic_gen.apply_profile 的分工要说清楚，否则两套分数会互相打架：

    apply_profile  管「偏好」—— 你时间紧、你对某角度感兴趣、你以前挑过这类。
                   它是软加权，最多 ±12 分，方向错了也只是排得靠后。
    topic_constraint 管「能力」—— 你没算力却选了要 8 卡训练的方法、
                   你只剩三个月却选了要重建评测协议的工作。
                   这类不是偏好问题，是「根本做不完」，所以单独标出来，
                   并且不硬压分数（压了用户会以为只是不推荐，而不是做不成）。

为什么不做成全自动过滤：见过太多「我算力不够但其实我要用的方法很轻」的情况。
系统只负责标出冲突点和它依据的规则，删不删由用户定。
"""

import re

# ---------------------------------------------------------------- 候选的算力/时间画像
# 每条角度需要的资源档位：0=笔记本可做 1=单卡消费级 2=单卡24G 3=多卡
# 判据来自这些工作最典型的实验配置，不是拍脑袋：
#   复现/评测要求同时跑好几个方法；扩散训练比判别式贵一个量级；
#   理论推导不需要算力但需要长周期；论文里报的 SOTA 结果通常是 8 卡跑一个月。
_ANGLE_NEED = {
    "轻量化": (1, "剪枝/蒸馏本身便宜，但要在同一硬件上测完整精度-速度曲线"),
    "鲁棒": (1, "扰动实验是推理层面的，不需要重训"),
    "小样本": (2, "要固定骨干做多次对比，每种设置至少三次重复"),
    "自监督": (3, "预训练是整件事里最贵的一步，而且收益要靠多档数据量验证"),
    "扩散": (3, "扩散模型的训练成本比判别式高一个量级"),
    "三维": (2, "三维数据比二维大得多，单次训练显存吃紧"),
    "事件相机": (1, "数据规模小，但格式特殊、预处理要自己写"),
    "视频": (2, "时序建模的序列长度把显存吃满，batch 只能开很小"),
    "多模态": (2, "两个编码器同时驻留显存"),
    "语言": (2, "接视觉语言模型至少要能推理 7B"),
    "分割": (2, "像素级标注加分割网络，通常比检测贵一倍"),
    "跟踪": (1, "现成检测器接简单关联就能先看数字"),
    "开放词汇": (2, "要接 CLIP 这类大模型做零样本"),
    "跨域泛化": (1, "只做测试不训练即可先量掉点"),
    "多尺度": (1, "分桶统计，主要是分析工作"),
    "评测": (1, "复现 3–5 个方法，推理为主"),
    "可解释": (1, "可视化与失败预测，推理为主"),
    "复现": (2, "要严格按原文设置重跑，通常就是原文的配置"),
    "机理": (2, "要做大量失败样本分析与消融"),
    "范式": (1, "主要是定义与讨论，实验量小"),
    "新任务": (2, "要建数据与评测，但可以先小规模验证"),
    "理论": (0, "推导为主，几乎不需要 GPU"),
}

# 融合类型额外的资源要求（叠加在上面的角度之上）
_KIND_NEED = {
    "三方交叉": (2, "三方都要各跑一遍，实验量是单方的两倍以上"),
    "技术驱动": (1, "把 B 接进 A 至少要把 B 跑通"),
    "下游迁移": (1, "先只做测试，成本低"),
    "共通抽象": (1, "取失败样本做分析"),
    "反向借鉴": (1, "最小化验证一步即可"),
}

# 周期：一年以下做不完的角度
_ANGLE_MONTHS = {
    "自监督": 1, "扩散": 1, "复现": 1, "理论": 2, "新任务": 1,
    "评测": 1, "三方交叉": 1,
}
_KIND_MONTHS = {"三方交叉": 2}

# 偏工程 / 偏理论
_THEORY_ANGLES = {"理论", "机理", "范式"}
_ENGINEER_ANGLES = {"轻量化", "跟踪", "视频", "三维", "事件相机", "多尺度"}

# 禁词命中要能区分「死在实现上」的危险品和「只是提了一句」的擦边。
# 只查标题与理由，不查全文半篇论文 —— 查全文几乎每条都会命中。
_AVOID_HIT_WEIGHT = 1.0


def _norm(text):
    return re.sub(r"[\s\-_/·、，,（）()]+", "", str(text or "")).lower()


def _levelopts(text):
    """把自由文本里的算力描述映射成档位。认不出来就当没填。"""
    t = _norm(text)
    if not t:
        return None
    if any(k in t for k in ("无算力", "没有算力", "只有cpu", "cpu", "笔记本", "核显")):
        return 0
    if any(k in t for k in ("多卡", "集群", "8卡", "4卡", "a100", "h100", "多张")):
        return 3
    if re.search(r"(24|32|40|48)g", t) or any(k in t for k in ("4090", "3090", "a6000")):
        return 2
    if re.search(r"(8|10|12|16)g", t) or any(k in t for k in ("3060", "4060", "2080", "1660")):
        return 1
    return None


def _monthopt(text):
    t = _norm(text)
    if not t:
        return None
    if any(k in t for k in ("一年", "1年", "两年", "2年", "长期")):
        return 2
    if any(k in t for k in ("半年", "6个月", "六个月", "八个月", "10个月")):
        return 1
    if any(k in t for k in ("3个月", "三个月", "两个月", "2个月", "一个月", "几周", "马上")):
        return 0
    return None


def check(cand, cons):
    """检查单个候选与硬约束的冲突。

    返回 {"level": "ok"|"warn"|"block", "reasons": [(级别, 文案)], "need": {...}}
    级别含义：
        block  按现有条件基本做不完（缺的是一次训练，不是一次调参）
        warn   能做，但要挑做法/加宽周期
        ok     没发现冲突（注意：这不代表一定做得了，只是没查到明显矛盾）
    """
    cons = cons or {}
    need_c = _ANGLE_NEED.get(cand.get("angle_key") or cand.get("angle") or "")
    need_k = _KIND_NEED.get(cand.get("kind") or "", (0, ""))
    angle = cand.get("angle_key") or cand.get("angle") or ""
    months = _ANGLE_MONTHS.get(angle, 0)
    months = max(months, _KIND_MONTHS.get(cand.get("kind") or "", 0))

    level = 0
    why_res = [x[1] for x in (need_c, need_k) if x and x[1]]
    need_c_lv = need_c[0] if need_c else 1
    need_k_lv = need_k[0] if need_k else 0
    need_lv = max(need_c_lv, need_k_lv)

    reasons = []
    has_c = _levelopts(cons.get("compute"))
    if has_c is not None and need_lv > has_c:
        gap = need_lv - has_c
        head = ("这条至少需要「%s」档算力，你填的是「%s」"
                % (_level_name(need_lv), cons.get("compute")))
        detail = why_res[0] if why_res else ""
        reasons.append(("block" if gap >= 2 else "warn",
                        (head + "：" + detail).rstrip("：")))
        level = 2 if gap >= 2 else max(level, 1)

    has_m = _monthopt(cons.get("months"))
    if has_m is not None and months > has_m:
        head = ("这条通常要半年以上，你填的是「%s」" % cons.get("months"))
        # 冒号后面跟一整句话会在窄栏里断成「你填的是『3 / 个月内』」——
        # 引号里的词被换行切开，读者第一眼会以为填错了
        reasons.append(("warn" if months - has_m == 1 else "block",
                        head + "，这类角度要重训模型或重建评测，赶不出来"))
        level = max(level, 1)

    style = cons.get("style") or ""
    if style == "偏理论" and angle in _ENGINEER_ANGLES:
        reasons.append(("warn", "这条偏工程实现（%s），你填的是偏理论" % angle))
        level = max(level, 1)
    elif style == "偏工程" and angle in _THEORY_ANGLES:
        reasons.append(("warn", "这条偏理论推导（%s），你填的是偏工程" % angle))
        level = max(level, 1)

    blob = _norm((cand.get("title") or "") + " " + (cand.get("reason") or "")
                 + " " + (cand.get("strategy") or ""))
    for word in cons.get("avoid") or []:
        w = _norm(word)
        if w and w in blob:
            reasons.append(("warn", "命中了你的禁忌方向「%s」" % word))
            level = max(level, 1)
            break

    lvl = "block" if level >= 2 else ("warn" if level == 1 else "ok")
    return {"level": lvl, "reasons": reasons,
            "need": {"compute": need_lv, "months": months, "angle": angle}}


def _level_name(lv):
    return {0: "无算力", 1: "单卡消费级", 2: "单卡 24G", 3: "多卡集群"}.get(lv, "未知")


def annotate(cands, cons):
    """批量标注，就地写入 cand["cfit"]，并把 block 的候选排到末尾。

    为什么把 block 沉底而不是删：用户可能是「其实我有学校集群但没填」，
    直接删掉他会以为系统找不出这类题。
    """
    if not cons or not any(cons.get(k) for k in ("compute", "months", "style")):
        if not (cons or {}).get("avoid"):
            return 0
    blocked = warn = 0
    for c in cands:
        r = check(c, cons)
        c["cfit"] = r
        if r["level"] == "block":
            blocked += 1
        elif r["level"] == "warn":
            warn += 1
    # 稳定排序：先按 block 下沉，再维持原有分数顺序
    cands.sort(key=lambda x: 1 if (x.get("cfit") or {}).get("level") == "block" else 0)
    return blocked


def summary(cands):
    """一行说明，给界面顶部用。没有冲突时返回空串（不占版面）。"""
    blocked = [c for c in cands if (c.get("cfit") or {}).get("level") == "block"]
    warn = [c for c in cands if (c.get("cfit") or {}).get("level") == "warn"]
    if not blocked and not warn:
        return ""
    bits = []
    if blocked:
        bits.append("%d 条按你填的条件做不完" % len(blocked))
    if warn:
        bits.append("%d 条要挑做法" % len(warn))
    return "；".join(bits) + "（已沉到底部，仍可查看）"