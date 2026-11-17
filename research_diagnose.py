#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""选题结构诊断（research_diagnose）—— 替代原来的「关键词计数打分」。

为什么不给分数
--------------
旧版 evaluate_idea_local 本质是「命中多少个关键词就加多少分」。
实测一个毫无内容、只堆砌关键词的空壳能拿到 77 分并被判为「投稿候选」，
而一个描述朴素但真实的问题只有 30 分。分数会让人误以为得到了客观评估。

这里只输出两类东西，都不冒充「质量分」：

1. **结构清单**：可被第三方核查的事实条目。而且**不允许用裸词糊弄** ——
   "指标"两个字不算定义了指标，必须出现 AP50 / F1 / 时延 这样的具体名字；
   "消融"两个字不算设计了消融，必须说明消融什么、和什么比。

2. **证据承诺**：要变成能投稿的课题还缺哪些动作。是「待办」，不是「得分」。

成熟阶段用**硬条件**判定，不用加权平均 —— 加权平均允许用漂亮话补短板。
"""

import re

# ---------------------------------------------------------------- 归一化
def _norm(text):
    return re.sub(r"\s+", " ", (text or "").lower())


def _has(text, words):
    return any(w in text for w in words)


# 具体指标名（不是「指标」这两个字）
METRIC_NAMES = [
    "ap50", "ap75", "map", "map50", " miou", "miou", "iou", "f1", "accuracy", "acc",
    "top-1", "top1", "top-5", "auc", "psnr", "ssim", "lpips", "fid", "bleu", "rouge",
    "wer", "cer", "fps", "qps", "时延", "延迟", "吞吐", "召回", "精确率", "准确率",
    "p95", "p99", "latency", "throughput", "recall", "precision", "ndcg", "mrr",
]

# 具体数据集 / 具体数字
DATA_NAMES = ["nuaa", "nudt", "coco", "imagenet", "kitti", "cityscapes", "voc",
              "mots", "visdrone", "brats", "luna", "sirius", "mvtec", "ade20k",
              "msrvtt", "squad", "mmlu", "gsm8k", "instances", "样本", "例", "张"]

# 具体模型名（点名 baseline）
MODEL_NAMES = re.compile(
    r"(yolo\w*|rt-?detr|detr|resnet\w*|vit\w*|swin\w*|deeplab\w*|unet|sam|clip|"
    r"llama\w*|gpt\w*|bert\w*|mamba\w*|nerf|gaussian|diffusion|sd\w*|stable diffusion|"
    r"transformer|faster[- ]?rcnn|mask[- ]?rcnn|deepsort|bytetrack|pointpillars|"
    r"pointnet\w*|centerpoint|bev\w*|polynet|dncnn|xgboost|lstm|gru|t5|qwen|glm)")

# 量化目标（带百分号或数字的比较）
QUANT = re.compile(r"(\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*(?:个|点|倍|fps|ms|小时|天|周|gb|g))")


def _sentences(text):
    return [s for s in re.split(r"[。；;！!？?\n]", text) if s.strip()]


def _substantive(text):
    """判断这段文字是否「言之有物」，而不只是关键词列表。

    词堆的典型特征：空格/顿号隔开的短词很多，但几乎没有标点，
    平均每个词很短 —— 中文正常句子分词后的「词」会混有虚词和长词，
    而术语列表几乎都是 2–4 字的术语。
    """
    raw = text.strip()
    if not raw:
        return False
    # 标点密度：正常中文段落每 30 字至少有一个标点
    punct = sum(raw.count(c) for c in "，。；：、！？,.;:!?\n")
    cn_chars = sum(1 for c in raw if "\u4e00" <= c <= "\u9fff")
    if cn_chars >= 60 and punct == 0:
        return False          # 一大段中文却没有标点 → 词堆
    tokens = [w for w in re.split(r"[\s、,，]+", raw) if w]
    if len(tokens) >= 12:
        avg_len = sum(len(w) for w in tokens) / len(tokens)
        if avg_len <= 3.2:
            return False      # 大多是 2–3 字的短术语 → 词堆
    sents = [s.strip() for s in _sentences(raw) if len(s.strip()) >= 8]
    if len(sents) >= 2:
        return sum(len(s) for s in sents) / len(sents) >= 14
    if len(sents) == 1 and len(sents[0]) >= 30:
        return True
    return False


# ---------------------------------------------------------------- 结构检查
def _check_problem(t, d, raw):
    return len(d) >= 40 and _has(t, ["失败", "漏检", "误检", "误差", "不准", "慢", "成本",
                                    "无法", "不足", "偏差", "退化", "瓶颈", "困难", "问题在于"])


def _check_mechanism(t, d, raw):
    causal = _has(t, ["因为", "从而", "机制", "通过", "约束", "目标函数", "信息流", "假设",
                      "使", "导致"])
    diff = _has(t, ["相比", "对比", "优于", "预期", "应该", "而不是"]) or bool(QUANT.search(t))
    return causal and diff


def _check_baseline(t, d, raw):
    return bool(MODEL_NAMES.search(t)) or _has(t, ["强基线"])


def _check_data(t, d, raw):
    named = _has(t, DATA_NAMES) or bool(re.search(r"[A-Z][A-Za-z\-]{2,}(?:-|_)[A-Za-z0-9\-]+", raw))
    split = _has(t, ["划分", "测试集", "验证集", "跨集", "泄漏", "独立测试"])
    return named and split


def _check_metric(t, d, raw):
    named = _has(t, METRIC_NAMES)
    fail = _has(t, ["失败", "下降", "低于", "退化", "代价", "不能超过"])
    return named and fail


def _check_ablation(t, d, raw):
    # 必须说明消融什么 / 和什么比，而不是只出现「消融」二字
    if not _has(t, ["消融", "ablation"]):
        return False
    return bool(re.search(r"消融.{0,30}(分支|模块|项|部分|加|去|替换|同等|对照|参数)", t)) or \
        _has(t, ["逐项消融", "同等参数量", "同等算力", "消融实验设计"])


def _check_budget(t, d, raw):
    return _has(t, ["单卡", "gpu", "算力", "显存", "训练时间", "小时", "周", "预算"]) and \
        (bool(re.search(r"\d", t)) or _has(t, ["一天", "两天", "一周", "两周", "数周"]))


def _check_stop(t, d, raw):
    return _has(t, ["停止条件", "止损", "失败则", "不成立则", "替代方案", "降级"])


def _check_scope(t, d, raw):
    return len(d) <= 800 and not _has(t, ["统一所有", "彻底解决", "完全解决", "通用框架",
                                         "万物", "所有任务"])


CHECKS = [
    ("problem", "问题具体", "在什么场景、哪一步失败、差多少", _check_problem,
     "补一句：在什么数据/场景下，哪个环节具体不行，差多少"),
    ("mechanism", "机制可检验", "改变了什么 + 为什么会导致可测结果", _check_mechanism,
     "写出可证伪假设：机制成立时哪个指标会怎么变；不成立会看到什么"),
    ("baseline", "baseline 点名", "能指名道姓的最强对手", _check_baseline,
     "点名 1–2 个具体模型/方法，并说明为什么它是最强对手"),
    ("data", "数据与划分", "数据集名称 + 训练测试如何划分", _check_data,
     "写清数据集名称、划分方式，以及如何避免测试集泄漏"),
    ("metric", "指标定义", "具体主指标 + 失败判据", _check_metric,
     "写清主指标（如 AP50、F1、p95 时延）+ 什么情况算失败"),
    ("ablation", "消融设计", "消融什么、与什么同等条件对比", _check_ablation,
     "说明消融哪些部分，并在同等参数量/算力下对照"),
    ("budget", "资源估算", "卡型、时长、预算", _check_budget,
     "估算：需要什么卡、跑多久、最坏情况几周"),
    ("stop", "止损条件", "什么情况下承认失败并停下", _check_stop,
     "设定止损点：做到哪一步还没效果就换方向"),
    ("scope", "范围收敛", "一次只解决一个可完成的问题", _check_scope,
     "缩小范围：先做一个场景、一类失败、一个数据集"),
]

PRIORITY = ["problem", "mechanism", "baseline", "data", "metric", "ablation",
            "budget", "stop", "scope"]


def diagnose(idea):
    # 传入 None 也要能返回一份「未填」的诊断，而不是崩溃
    if not isinstance(idea, dict):
        idea = {}
    title = (idea.get("title") or "").strip()
    desc = (idea.get("desc") or "").strip()
    raw = title + " " + desc
    t = _norm(raw)

    substantive = _substantive(raw) and len(desc) >= 40

    passed, missing = [], []
    for key, label, why, fn, fix in CHECKS:
        try:
            ok = bool(fn(t, desc, raw))
        except Exception:
            ok = False
        item = {"key": key, "label": label, "why": why, "fix": fix}
        (passed if ok else missing).append(item)

    keys = {p["key"] for p in passed}
    # 关键校正：如果整体只是词堆，那些「关键词命中」不算数
    hollow = []
    if not substantive:
        for k in ("problem", "mechanism", "baseline", "data", "metric", "ablation", "budget"):
            if k in keys:
                keys.discard(k)
                item = next(c for c in CHECKS if c[0] == k)
                passed = [p for p in passed if p["key"] != k]
                missing.insert(0, {"key": item[0], "label": item[1], "why": item[2],
                                   "fix": "这段像关键词列表而不是描述，请用完整句子说明"})
                hollow.append(k)

    if {"problem", "mechanism", "baseline", "data", "metric", "ablation"} <= keys and len(keys) >= 8:
        stage, hint = "4 可写成文", "结构已齐，缺真实实验数据与写作"
    elif {"problem", "mechanism", "baseline", "data", "metric"} <= keys:
        stage, hint = "3 可做完整实验", "五项核心条件齐备，可以开始跑实验"
    elif {"problem", "mechanism"} <= keys:
        stage, hint = "2 可做最小实验", "问题与机制说清楚了，先做一个最小验证"
    elif "problem" in keys:
        stage, hint = "1 有问题，缺机制", "问题是真的，但还没说清你要改变什么"
    else:
        stage, hint = "0 尚未成型", "还只是一句话，先补问题与机制"

    warn = []
    if hollow:
        warn.append("这段文字读起来像关键词列表：术语出现了，但没有说明具体是什么。"
                    "「消融」两个字不等于设计了消融，「指标」两个字不等于定义了指标。")
    if len(desc) >= 300 and len(keys & {"problem", "mechanism", "baseline"}) <= 1:
        warn.append("写得很多，但核心三件事（问题/机制/baseline）基本没说清。"
                    "篇幅不等于深度。")
    if len(desc) < 40:
        warn.append("描述过短，当前判断基本只基于标题，仅供参考。")

    order = {k: i for i, k in enumerate(PRIORITY)}
    missing.sort(key=lambda m: order.get(m["key"], 99))
    nxt = ["补：" + m["label"] + " —— " + m["fix"] for m in missing[:3]]
    if not missing:
        nxt = ["结构已齐。接下来做真实实验，并如实记录失败结果"]
    else:
        nxt.append("先做最小验证：一个场景、一个基线、一个指标，两周内看到趋势")

    return {
        "title": title,
        "passed": passed,
        "missing": missing,
        "stage": stage,
        "stage_hint": hint,
        "next": nxt,
        "warnings": warn,
        "count": {"passed": len(passed), "total": len(CHECKS)},
        "coverage": round(100.0 * len(passed) / len(CHECKS)),
    }


def stage_rank(stage):
    m = re.match(r"(\d)", stage or "")
    return int(m.group(1)) if m else 0