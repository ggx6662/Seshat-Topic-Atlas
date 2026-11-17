#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从本地文献库提炼「研究空白」——为创新点提供真实依据。

为什么需要这个
--------------
原来的候选选题是这样生成的：
    基础方向「红外小目标检测」+ 策略词「轻量化与实时部署」
    → 「红外小目标检测的轻量化与实时部署」
18 个候选的「理由」和「验证问题」完全一样，是模板套话。

真正能支撑创新点的，是**你手上这批论文里反复出现什么、缺什么**。
本模块直接读知识库的 343 篇 PDF 标题，做三件事：

  1. 方法共现分析：哪些方法被反复用在哪些任务上 → 已经被做烂的组合
  2. 空白组合：方法 × 任务的组合里，有的组合文献很少 → 潜在空白
  3. 规模与变化：近两年 vs 更早的主题分布变化 → 哪些方向在升温

所有结论都标注**依据的文献**，不编造。
"""

import os
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 方法词 / 任务词 / 模态词：从真实论文标题里学到的（见 learn_from_kb.py）
METHODS = {
    "mamba": "Mamba/状态空间",
    "state space": "Mamba/状态空间",
    "transformer": "Transformer",
    "diffusion": "扩散模型",
    "gan": "GAN",
    "cnn": "CNN",
    "yolo": "YOLO",
    "sam": "SAM/分割基础模型",
    "clip": "CLIP/视觉语言",
    "nerf": "NeRF",
    "gaussian": "3DGS",
    "distill": "知识蒸馏",
    "prun": "剪枝",
    "quantiz": "量化",
    "contrastive": "对比学习",
    "self-supervised": "自监督",
    "federated": "联邦学习",
    "reinforcement": "强化学习",
}
TASKS = {
    "detection": "检测",
    "segment": "分割",
    "tracking": "跟踪",
    "recognition": "识别",
    "classification": "分类",
    "fusion": "融合",
    "registration": "配准",
    "enhancement": "增强",
    "super-resolution": "超分",
    "estimation": "估计",
    "retrieval": "检索",
    "generation": "生成",
    "prediction": "预测",
}
MODALS = {
    "infrared": "红外",
    "thermal": "红外",
    "rgb-t": "RGB-T",
    "rgb-ir": "RGB-T",
    "multispectral": "多光谱",
    "hyperspectral": "高光谱",
    "point cloud": "点云",
    "medical": "医学",
    "remote sensing": "遥感",
    "uav": "无人机",
    "video": "视频",
    "3d": "三维",
}
ISSUES = {
    "small object": "小目标",
    "small target": "小目标",
    "low-light": "低光",
    "night": "夜间",
    "occlusion": "遮挡",
    "few-shot": "小样本",
    "zero-shot": "零样本",
    "open-vocabulary": "开放词汇",
    "domain": "跨域",
    "real-time": "实时",
    "efficient": "高效",
    "lightweight": "轻量",
    "robust": "鲁棒",
    "adversarial": "对抗",
    "privacy": "隐私",
    "long sequence": "长序列",
    "multi-task": "多任务",
    "cross-modal": "跨模态",
    "cross-spectral": "跨光谱",
}


def _papers():
    """读取知识库里的 PDF 标题与年份。"""
    out = []
    try:
        import kb_widget as kb
        inv = kb._inventory()
        files = inv.get("files", []) if isinstance(inv, dict) else []
    except Exception:
        files = []
    for row in files:
        path = str(row[2]) if isinstance(row, (tuple, list)) and len(row) >= 3 else str(row)
        if not path.lower().endswith(".pdf"):
            continue
        name = os.path.splitext(os.path.basename(path))[0]
        title = re.sub(r"[_+]+", " ", name)
        year = None
        m = re.search(r"(20[12]\d)", title)
        if m:
            year = int(m.group(1))
        out.append({"title": title, "text": title.lower(), "year": year, "path": path})
    return out


def _hit(text, table):
    return [label for key, label in table.items() if key in text]


# 明显不合理的「方法 × 任务」组合：不必列出来，否则噪音太大
_IMPLAUSIBLE = {
    # YOLO 是目标检测器，跨到其他任务属降级/误用，不是真正的研究空白
    ("YOLO", "分类"), ("YOLO", "生成"), ("YOLO", "增强"),
    ("YOLO", "检索"), ("YOLO", "配准"), ("YOLO", "跟踪"),
    ("YOLO", "识别"), ("YOLO", "分割"), ("YOLO", "估计"),
    ("扩散模型", "跟踪"), ("扩散模型", "配准"), ("扩散模型", "识别"),
    ("NeRF", "检测"), ("NeRF", "分类"), ("NeRF", "识别"),
    ("3DGS", "检测"), ("3DGS", "分类"),
}


def _plausible(method, task):
    return (method, task) not in _IMPLAUSIBLE


# 中文方向词 → 英文检索词。知识库里的论文标题都是英文，
# 直接拿「红外」去匹配会得到 0 篇，必须先翻译。
CN2EN = {
    "红外": ["infrared", "thermal"],
    "可见光": ["visible", "rgb"],
    "小目标": ["small object", "small target"],
    "目标检测": ["detection"],
    "检测": ["detection"],
    "分割": ["segment"],
    "跟踪": ["tracking", "track"],
    "融合": ["fusion", "fuse", "fuser"],
    "多模态": ["multimodal", "multi-modal", "multi modal"],
    "医学": ["medical", "clinical", "mri", "ct "],
    "遥感": ["remote sensing", "aerial", "satellite"],
    "无人机": ["uav", "drone"],
    "三维重建": ["reconstruction", "nerf", "gaussian"],
    "深度估计": ["depth"],
    "生成": ["generation", "generative", "diffusion"],
    "扩散": ["diffusion"],
    "分割模型": ["sam", "segment anything"],
    "对比学习": ["contrastive"],
    "自监督": ["self-supervised"],
    "对抗": ["adversarial", "attack"],
}


def _expand_keyword(kw):
    """把中文方向词翻译成可匹配的英文词表。"""
    low = kw.lower().strip()
    terms = [low]
    for cn, ens in CN2EN.items():
        if cn in kw:
            terms.extend(ens)
    return [t for t in dict.fromkeys(terms) if t]


def _gap_query(g):
    """把「方法 × 任务」翻成干净的英文检索式。

    不能直接拿中文标签去查：`SAM/分割基础模型` 里有斜杠，
    `split_cn` 会把它拆成 `segmentation + foundation model + segment anything + / + tracking`，
    每个词都要 AND，于是 18 篇（实际是「斜杠出现过」的偶然命中），
    看着像「真空白」，其实是查询自己写错了。
    """
    m = (g.get("method") or "").strip()
    t = (g.get("task") or "").strip()
    fixed = {
        "SAM/分割基础模型": "segment anything",
        "Mamba/状态空间": "mamba",
        "CLIP/视觉语言": "clip vision language",
        "知识蒸馏": "knowledge distillation",
        "对比学习": "contrastive learning",
        "自监督": "self-supervised",
        "联邦学习": "federated learning",
        "强化学习": "reinforcement learning",
        "分割基础模型": "foundation segmentation model",
        "扩散模型": "diffusion model",
        "超分": "super-resolution",
        "三维": "3d",
    }
    m2 = fixed.get(m, m)
    t2 = fixed.get(t, t)
    if "/" in m2:
        m2 = " ".join(x for x in m2.split("/") if x and x.strip() != "/")
    if "/" in t2:
        t2 = " ".join(x for x in t2.split("/") if x and x.strip() != "/")
    return ("%s %s" % (m2, t2)).strip()


# 方法/任务标签 → 完整的英文检索拼写。
# 为什么不能只取第一个词：`contrastive` 单独查是 2,875 篇，`contrastive learning` 是 2,061 篇 ——
# 前者混进了 contrastive 预热、contrastive 正则化等无关论文，那个数不能当「这个方向有多热」。
# 所以这里给的是经过人工确认的完整写法，不再做二次截断。
_LABEL_EN = {
    "对比学习": "contrastive learning",
    "自监督": "self-supervised learning",
    "半监督": "semi-supervised learning",
    "无监督": "unsupervised learning",
    "扩散模型": "diffusion model",
    "知识蒸馏": "knowledge distillation",
    "联邦学习": "federated learning",
    "强化学习": "reinforcement learning",
    "图神经网络": "graph neural network",
    "元学习": "meta-learning",
    "注意力": "attention mechanism",
    "量化": "quantization",
    "剪枝": "pruning",
    "轻量化": "lightweight model",
    "多模态": "multimodal",
    "跨模态": "cross-modal",
    "开放词汇": "open-vocabulary",
    "零样本": "zero-shot",
    "小样本": "few-shot",
    "微调": "fine-tuning",
    "蒸馏": "distillation",
    "检测": "object detection",
    "分割": "image segmentation",
    "跟踪": "object tracking",
    "识别": "recognition",
    "分类": "classification",
    "融合": "image fusion",
    "配准": "registration",
    "增强": "image enhancement",
    "超分": "super-resolution",
    "估计": "estimation",
    "检索": "retrieval",
    "生成": "image generation",
    "预测": "prediction",
    "重建": "reconstruction",
    "定位": "localization",
    "计数": "counting",
    "匹配": "matching",
    "去雾": "dehazing",
    "去噪": "denoising",
    "超分辨率": "super-resolution",
}

# 「A/B」这种双名标签，取斜杠前那个（`Mamba/状态空间` → Mamba）。
_ALIAS_HEAD = {
    "Mamba": "mamba",
    "SAM": "segment anything",
    "CLIP": "clip",
    "YOLO": "yolo",
    "Transformer": "transformer",
    "CNN": "convolutional neural network",
    "GAN": "generative adversarial",
    "NeRF": "nerf",
    "3DGS": "gaussian splatting",
}


def _to_en_label(s):
    """把方法/任务标签翻成完整英文写法；翻不出来返回空串。

    返回空串意味着「这个标签我们不知道怎么查」—— 上位函数会跳过核实，
    而不是用一个拼错的中文查询去得一个 0 篇的假空白。
    """
    s = (s or "").strip()
    if not s:
        return ""
    if s in _LABEL_EN:
        return _LABEL_EN[s]
    head = s.split("/")[0].strip()
    if head in _LABEL_EN:
        return _LABEL_EN[head]
    if head in _ALIAS_HEAD:
        return _ALIAS_HEAD[head]
    low = head.lower()
    # 已经是纯英文（`Mamba`、`Transformer`）就直接用
    try:
        en = kb_vector.to_english(low)
    except Exception:
        en = low
    if any("\u4e00" <= ch <= "\u9fff" for ch in en):
        return ""
    return en or ""


def _gap_query(g):
    """把「方法 × 任务」拼成干净的英文交集检索式。

    不能直接拿中文标签去查：`SAM/分割基础模型` 里有斜杠和中文，
    `split_cn` 会把它拆成一堆碎片词，每个都要 AND，偶然命中 18 篇 ——
    看着像「真空白」，其实是查询自己写错了。
    """
    m = _to_en_label(g.get("method"))
    t = _to_en_label(g.get("task"))
    return ("%s %s" % (m, t)).strip()


# 模态（中文）→ 英文检索词。和上面的 _LABEL_EN 分开，因为「医学」当模态查
# 要用 medical imaging，当关键词查可能只该用 medical。
_MODAL_EN = {
    "红外": "infrared",
    "RGB-T": "rgb-thermal",
    "多光谱": "multispectral",
    "高光谱": "hyperspectral",
    "点云": "point cloud",
    "医学": "medical imaging",
    "遥感": "remote sensing",
    "无人机": "uav",
    "视频": "video",
    "三维": "3d",
}

# 失效场景（中文）→ 英文检索词。
# 这些词在论文里出现得很不统一：「小目标」可能写成 small object / small target /
# tiny object，「实时」写成 real-time / efficient。所以每条给多个写法，
# 由 search_and 的同义组去合并；这里只保证至少不会翻成空。
_ISSUE_EN = {
    "小目标": "small object",
    "夜间": "nighttime",
    "遮挡": "occlusion",
    "低光": "low-light",
    "小样本": "few-shot",
    "实时": "real-time",
    "跨域": "domain shift",
    "对抗": "adversarial",
    "低照度": "low illumination",
    "雨雾": "rain and fog",
    "模糊": "blur",
    "长尾": "long-tailed",
}


def _issue_query(g):
    """「模态 × 问题」→ 英文交集检索式（如 `medical imaging occlusion`）。"""
    d = _MODAL_EN.get(g.get("modal")) or _to_en_label(g.get("modal"))
    i = _ISSUE_EN.get(g.get("issue")) or _to_en_label(g.get("issue"))
    return ("%s %s" % (d, i)).strip()


def _count_global(q):
    """跑一次交集过滤，只取篇数（不排序）—— 我们要的是「有多少篇」，不是「哪几篇最好」。"""
    import kb_vector
    r = kb_vector.search_and(q, k=1)
    return int(r.get("count") or 0), (r.get("terms") or [])


# 模态在全库至少要有这么多篇，才有资格谈「这个场景没人做」。
# 低于这个量级不是「空白」，是「我们还不知道」—— 报出来会误导用户去追一个
# 可能根本不成立的赛道。
_MODAL_MIN = 300


def _verdict(n):
    if n < 20:
        return "真空白", "全库都很少见，值得优先深挖"
    if n < 200:
        return "稀疏", "有人做过，需要讲清你的差异化"
    return "拥挤", "已是很热的方向，别再当创新点"


def _pick_issues(items, local_gaps=None, per_modal=1):
    """同一个模态的问题维度空白不能霸屏。

    local_gaps 里已经有 4 条（全是医学），核实之后如果 4 个模态都够活跃，
    应该每条各出一个代表；只有医学够活跃时，才允许它多占几条。
    """
    by_modal = defaultdict(list)
    for c in items:
        by_modal[c["modal"]].append(c)
    # 每个模态内部：先「稀疏」，再「真空白」，最后「拥挤」
    # （拥挤几乎不能当创新点，不该排在最前面抢占名额）
    rank = {"稀疏": 0, "真空白": 1, "拥挤": 2}
    for m in by_modal:
        by_modal[m].sort(key=lambda c: rank.get(c["level"], 3))
    out = []
    for rnd in range(per_modal or 1):
        for m in by_modal:
            if rnd < len(by_modal[m]):
                out.append(by_modal[m][rnd])
    # 同一模态还剩的条目按顺序补在后面（避免条目被静默丢掉）
    for m in by_modal:
        for c in by_modal[m][per_modal or 0:]:
            if c not in out:
                out.append(c)
    return out[:4]


def _global_check(scope, data, max_check=3):
    """把本地「空白」拿到 arXiv 全库核实一遍。

    为什么必须做
    ------------
    本地库只有 343 篇 —— 是「我收藏了什么」，不是「学界做了什么」。
    「对比学习 × 检测在本地库里 0 篇」很可能是误判（实测全库 603 篇），
    实际上是我们的方法词表没识别出来。
    不核实就把空白当创新点，等于用收藏夹的缺口冒充学术缺口。

    两类空白都核：
      gaps       方法 × 任务，key 用 `kind=method`
      issue_gaps 模态 × 问题，key 用 `kind=issue`
    两类分开返回在同一个列表里，靠 kind 字段区分 —— 页面上能直接对上号。

    结论三档：
        真空白   全库 < 20 篇          值得深挖
        稀疏     20–200 篇             有新意但要找到差异化
        拥挤     > 200 篇              别当创新点

    arXiv 索引不存在时返回空列表 —— 宁可不说，也不瞎说。
    """
    try:
        import kb_vector
        if not kb_vector.stats().get("docs"):
            return []
    except Exception:
        return []

    out = []
    for g in (data.get("gaps") or [])[:max_check]:
        q = _gap_query(g)
        if not q.strip():
            continue
        try:
            n, terms = _count_global(q)
        except Exception:
            continue
        level, note = _verdict(n)
        out.append({
            "kind": "method",
            "method": g["method"], "task": g["task"],
            "query": q, "count": n, "level": level, "note": note, "terms": terms,
        })

    # 问题维度空白：模态很活跃但某个失效场景没人研究。
    # 这条通常比方法组合更有价值 —— 它对应真实的失败现场。
    # 问题维度空白：模态本身要「在库里够活跃」才有资格谈缺口。
    # 本地库只有 343 篇，「医学」17 篇连模态排序都进不了前几，却霸占了全部四条
    # 空白 —— 这是拿收藏夹的厚度冒充研究热度。所以先拿全库核一下模态本身的量级，
    # 太冷门的模态直接不出空白（不是没有缺口，是我们没资格断言）。
    out_issue = []
    for g in (data.get("issue_gaps") or [])[:6]:
        q = _issue_query(g)
        if not q.strip():
            continue
        mq = _MODAL_EN.get(g.get("modal")) or _to_en_label(g.get("modal"))
        try:
            mn = _count_global(mq)[0] if mq.strip() else 0
        except Exception:
            mn = 0
        if mn < _MODAL_MIN:
            continue
        try:
            n, terms = _count_global(q)
        except Exception:
            continue
        level, note = _verdict(n)
        out_issue.append({
            "kind": "issue",
            "modal": g["modal"], "issue": g["issue"],
            "modal_count": mn,
            "query": q, "count": n, "level": level, "note": note, "terms": terms,
        })
    out.extend(_pick_issues(out_issue, data.get("issue_gaps") or []))
    return out


def analyze(keyword=None, limit=8):
    """分析文献库，返回研究空白报告。

    keyword 用于聚焦某个方向（如「红外」「mamba」），为空则做全库分析。
    中文关键词会自动翻译成英文再匹配（论文标题都是英文）。
    """
    papers = _papers()
    if keyword:
        terms = _expand_keyword(keyword)
        papers = [p for p in papers if any(t in p["text"] for t in terms)]
    if not papers:
        return {"scope": keyword or "全库", "total": 0, "papers": [],
                "combos": [], "gaps": [], "rising": [],
                "notes": ["该方向在本地文献库里没有匹配到论文。"
                          "可换一个说法，或先到「文献库」抓取相关论文。"],
                "methods": [], "tasks": [], "modals": []}

    method_cnt = Counter()
    task_cnt = Counter()
    modal_cnt = Counter()
    issue_cnt = Counter()
    # 方法 × 任务 的共现
    pair = Counter()
    pair_papers = defaultdict(list)
    # 模态 × 问题
    modal_issue = Counter()
    modal_issue_papers = defaultdict(list)
    year_topics = defaultdict(Counter)

    for p in papers:
        ms = _hit(p["text"], METHODS)
        ts = _hit(p["text"], TASKS)
        ds = _hit(p["text"], MODALS)
        iss = _hit(p["text"], ISSUES)
        # 隐含语义：某些方法名本身已经说明任务。
        # YOLO 就是检测器、SAM 就是分割模型；标题里常不写 detection/segmentation，
        # 不补这一步会把「YOLO-Mamba」误判成「YOLO 没做过检测」。
        if "YOLO" in ms and "检测" not in ts:
            ts.append("检测")
        if "SAM/分割基础模型" in ms and "分割" not in ts:
            ts.append("分割")
        for m in set(ms):
            method_cnt[m] += 1
        for t in set(ts):
            task_cnt[t] += 1
        for d in set(ds):
            modal_cnt[d] += 1
        for i in set(iss):
            issue_cnt[i] += 1
        for m in set(ms):
            for t in set(ts):
                k = (m, t)
                pair[k] += 1
                pair_papers[k].append(p["title"])
        for d in set(ds):
            for i in set(iss):
                k = (d, i)
                modal_issue[k] += 1
                modal_issue_papers[k].append(p["title"])
        if p["year"]:
            for tag in set(ms + ds + iss):
                year_topics[p["year"]][tag] += 1

    # 1) 已被做烂的组合：方法×任务 出现 >= 3 次
    combos = []
    for (m, t), n in pair.most_common(limit):
        if n < 2:
            continue
        combos.append({"method": m, "task": t, "count": n,
                       "examples": pair_papers[(m, t)][:2]})

    # 2) 空白候选：方法在库里出现 >= 2 次，但与该任务组合为 0
    #    必须加可信度判断，否则会给出「YOLO × 分类」这种明显不搭的组合。
    #    判据：该方法与该任务在同一篇论文的**上下文词**里越接近，组合越可信。
    gaps = []
    hot_methods = [m for m, n in method_cnt.most_common() if n >= 3]
    hot_tasks = [t for t, n in task_cnt.most_common() if n >= 3]
    for m in hot_methods:
        for t in hot_tasks:
            if pair.get((m, t), 0) != 0:
                continue
            # 可信度：两者都在库里活跃，且都不是小众标签
            mf, tf = method_cnt[m], task_cnt[t]
            combo_score = mf + tf
            # 排除明显不合理的组合（检测类方法 × 生成类任务 等）
            if not _plausible(m, t):
                continue
            gaps.append({
                "method": m, "task": t,
                "m_count": mf, "t_count": tf,
                "method_freq": mf, "task_freq": tf,
                "plausibility": combo_score,
                "why": "库里「%s」出现 %d 次、「%s」出现 %d 次，但没有一篇同时涉及两者"
                       % (m, mf, t, tf),
            })
    gaps.sort(key=lambda g: -g["plausibility"])
    # 去重：同一个方法只保留可信度最高的 2 条，避免整栏都是「对比学习 × X」
    seen_method = Counter()
    deduped = []
    for g in gaps:
        if seen_method[g["method"]] >= 2:
            continue
        seen_method[g["method"]] += 1
        deduped.append(g)
    gaps = deduped[:limit]

    # 4) 问题维度空白：某个模态很活跃，但某个具体问题（小目标/夜间/遮挡…）
    #    在库里几乎没被研究 —— 这类空白往往比「方法组合」更有研究价值。
    #    但要配对合理：医学影像关心小目标/遮挡，不关心「夜间」「低光」。
    ISSUE_APPLIES = {
        "红外": {"小目标", "夜间", "低光", "遮挡", "实时", "跨域"},
        "RGB-T": {"小目标", "夜间", "低光", "遮挡", "跨域"},
        "遥感": {"小目标", "遮挡", "实时", "跨域"},
        "无人机": {"小目标", "实时", "遮挡", "跨域"},
        "医学": {"小目标", "小样本", "遮挡", "跨域"},
        "点云": {"遮挡", "实时", "跨域"},
        "视频": {"小目标", "遮挡", "实时"},
    }
    issue_gaps = []
    for modal, mn in modal_cnt.most_common(6):
        if mn < 5:
            continue
        allowed = ISSUE_APPLIES.get(modal)
        for issue in ("小目标", "夜间", "遮挡", "低光", "小样本", "实时", "跨域", "对抗"):
            if allowed is not None and issue not in allowed:
                continue
            n = modal_issue.get((modal, issue), 0)
            if n == 0 and issue_cnt.get(issue, 0) <= 2:
                issue_gaps.append({
                    "modal": modal, "issue": issue,
                    "modal_freq": mn,
                    "why": "库里「%s」相关文献 %d 篇，但没有一篇涉及「%s」问题"
                           % (modal, mn, issue),
                })
    issue_gaps.sort(key=lambda g: -g["modal_freq"])
    issue_gaps = issue_gaps[:4]

    # 4b) 同一条空白按「模态 × 问题」核实要用到的本地计数（弹给用户看证据）
    for g in issue_gaps:
        g["mn_count"] = g["modal_freq"]
        g["issue_count"] = issue_cnt.get(g["issue"], 0)

    # 3) 近年升温：2024 之后出现、更早没有的主题
    rising = []
    years = sorted(year_topics)
    if len(years) >= 2:
        mid = years[len(years) // 2]
        early = Counter()
        late = Counter()
        for y in years:
            target = early if y < mid else late
            for tag, n in year_topics[y].items():
                target[tag] += n
        for tag, n in late.most_common():
            if n >= 2 and early.get(tag, 0) == 0:
                rising.append({"topic": tag, "recent": n, "before": 0,
                               "why": "%d 年及以后出现 %d 次，更早的文献里没有" % (mid, n)})
        rising = rising[:6]

    notes = []
    if len(papers) < 10:
        notes.append("当前范围只有 %d 篇文献，结论仅供参考；建议先扩充文献库再分析。"
                     % len(papers))
    if not rises_ok(year_topics):
        notes.append("部分文件名没有年份，趋势分析的样本有限。")

    return {
        "scope": keyword or "全库",
        "total": len(papers),
        "methods": method_cnt.most_common(8),
        "tasks": task_cnt.most_common(8),
        "modals": modal_cnt.most_common(8),
        "issues": issue_cnt.most_common(8),
        "combos": combos,
        "gaps": gaps,
        "issue_gaps": issue_gaps,
        "rising": rising,
        "notes": notes,
        # 全库核实：本地库缺口 ≠ 学界缺口，这一步是硬性校正。
        # 不放这里 —— 它要读 53.8 万篇正文，30 秒起步，会卡住整页；
        # 页面先拿本地结论渲染，再调 global_check() 异步补上。
        "global_check": [],
    }


def global_check(data, max_check=3):
    """页面异步核实入口：输入 analyze() 的结果，返回核实列表。"""
    try:
        return _global_check(data.get("scope"), data, max_check=max_check)
    except Exception:
        return []


def rises_ok(year_topics):
    return len(year_topics) >= 3


def gap_to_idea(gap):
    """把「空白组合」转成可编辑的选题草案。"""
    return {
        "title": "%s 用于%s的可行性研究" % (gap["method"], gap["task"]),
        "desc": ("背景：%s。\n"
                 "拟研究：把 %s 的方法引入%s任务，重点看它在该任务的关键失效场景下"
                 "是否比现有方法更稳。\n"
                 "需要补：最强 baseline、数据集与划分、主指标与失败判据、消融设计。"
                 % (gap["why"], gap["method"], gap["task"])),
        "type": "方法创新",
        "source": "文献空白分析",
    }