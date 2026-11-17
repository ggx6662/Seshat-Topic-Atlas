#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重新映射导师的研究方向（不重新抓取，纯本地计算）。

背景
----
`fetch_authors` 抓回来的每位导师带一组 OpenAlex 主题名（topics），
`map_topic_candidates` 把主题名映射到你的 387 个研究方向。

原映射用 `term in text` 子串匹配，导致两个缩写严重误伤：
  * `ics` 命中 Robotics / Graphics / Semantics → 「工业控制系统」虚高
  * `ar`  命中 robotics / grammar / …        → 「VR与AR」被匹配 9502 次
结果：**47% 的导师首个标签是错的**。

修复后（见 build_advisor_index._term_hit）英文短缩写改为按独立单词匹配。
本脚本用修复后的逻辑，在不联网的情况下重新计算全部导师的分类。

同时做两件事：
  1. 给通用主题补兜底规则（Advanced Neural Network Applications 等
     这类 OpenAlex 的宽泛主题名原本映射不到任何领域）
  2. 识别出「非计算机学科」的学者并单独标记，不强行塞进某个 CS 领域

用法
----
python remap_advisors.py            # 重新映射并写回
python remap_advisors.py --dry-run  # 只看统计，不写文件
"""

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_advisor_index as B  # noqa: E402

FULL = HERE / "advisor_directory_full.json"

# OpenAlex 的宽泛主题名 → (大类, 领域)。
# 实测：2848 个不同主题名里，只有 37% 能命中 387 个具体领域 —— 说明
# 方向库对「研究内容」的描述颗粒度，和 OpenAlex 的主题颗粒度不匹配，
# 大量真实主题（Topic Modeling、Face and Expression Recognition …）
# 在方向库里找不到对应词。下面按真实数据里出现频率最高的主题逐一兜底。
GENERIC_RULES = [
    # ---- 通用 AI / 神经网络（OpenAlex 最泛的一类，占比最大）
    (["advanced neural network applications", "neural networks and applications",
      "advanced memory and neural computing", "neural networks stability",
      "neural network models"],
     "人工智能", "深度学习架构"),
    (["topic modeling", "topic model"],
     "自然语言处理", "信息抽取"),
    (["natural language processing techniques", "natural language processing",
      "text mining", "text classification"],
     "自然语言处理", "大语言模型"),
    (["multimodal machine learning"],
     "人工智能", "多模态学习"),
    (["complex network analysis", "network analysis techniques"],
     "数据挖掘与信息检索", "图挖掘"),
    (["artificial intelligence in education", "educational technology",
      "online and blended learning", "online learning and analytics",
      "higher education and teaching methods", "efl/esl", "english language learning",
      "vocational education", "pedagogy"],
     "计算教育与专业实践", "AI辅助教育与学习"),

    # ---- 视觉
    (["advanced image and video retrieval", "image retrieval and classification",
      "content-based image retrieval"],
     "计算机视觉", "视频理解"),
    (["video surveillance and tracking"],
     "计算机视觉", "目标跟踪"),
    (["remote-sensing image classification", "remote sensing image"],
     "交叉与AI4Science", "遥感与地球观测"),
    (["generative adversarial networks and image synthesis", "image synthesis",
      "image generation"],
     "计算机视觉", "生成式视觉与扩散模型"),
    (["face and expression recognition", "facial expression"],
     "计算机视觉", "人脸与生物特征识别"),
    (["image enhancement techniques", "image enhancement", "image super-resolution"],
     "计算机视觉", "图像恢复与增强"),
    (["advanced steganography and watermarking", "digital watermarking"],
     "安全与隐私", "数字取证与事件响应"),
    (["medical image analysis", "medical imaging"],
     "交叉与AI4Science", "医学影像"),

    # ---- 检索 / 知识
    (["semantic web and ontologies", "ontology"],
     "数据挖掘与信息检索", "知识图谱"),
    (["biomedical text mining", "bioinformatics"],
     "交叉与AI4Science", "生物信息"),
    (["recommender systems", "recommendation systems"],
     "数据挖掘与信息检索", "推荐系统"),

    # ---- 系统 / 控制
    (["stability and control of uncertain systems", "adaptive control of nonlinear",
      "chaos control", "chaos-based image", "control systems", "nonlinear control"],
     "电子设计自动化与计算机工程", "数字逻辑与计算机组成"),
    (["wireless sensor networks", "sensor networks"],
     "网络与通信", "自组网与无线传感网"),
    (["software engineering and development"],
     "软件工程", "软件开发基础与程序设计"),
    (["data mining and knowledge discovery", "data mining"],
     "数据挖掘与信息检索", "数据流挖掘"),

    # ---- 农业 / 其他交叉
    (["smart agriculture", "agriculture"],
     "交叉与AI4Science", "生态与农业智能"),
]

# ---------------------------------------------------------------- 学科口径
# 定位：**以计算机为主，允许交叉融合**（AI4Science / 计算生物学 / 医学影像…），
# 但排除「只是用了计算机当工具、研究本身不属于计算机」的纯非计算机学科。
#
# 判别原则：
#   保留 —— 方法是计算机的（深度学习、视觉、NLP…），应用领域是别的
#           例：AI in cancer detection、EEG and Brain-Computer Interfaces
#   剔除 —— 研究对象本身是别的学科，计算机只是被借用的工具
#           例：Chinese history、Plant Pathogens、Optical measurement

# 纯非计算机：命中即剔除（不进入索引）
NON_CS_HINTS = [
    # 人文社科
    "chinese history", "socioeconomic", "ideological and political",
    "library science", "sociology", "philosophy",
    # 材料 / 化学 / 能源
    "battery materials", "electrocatalysts", "nanoparticle", "polymer",
    # 生物医学（非计算部分）
    "cancer immunotherapy", "plant pathogens", "fungal", "gut microbiota",
    "clinical trial", "nursing", "pharmacology",
    # 物理 / 光学 / 土木
    "fluid dynamics", "vibration analysis", "structural health monitoring",
    "optical measurement", "holography", "fiber optic", "metrology",
    "surface roughness", "photonics", "laser", "photonic", "wavefront",
    "adaptive optics", "random lasers", "scattering media", "optical imaging",
    "optical system design", "interference",
    # 数学（纯理论，非计算数学）
    "differential equations", "partial differential", "numerical methods in computational",
]

# 计算驱动的交叉主题：属于「交叉融合」，归到 AI4Science 或对应大类
CROSS_RULES = [
    (["eeg", "brain-computer", "brain computer", "neural dynamics"],
     "交叉与AI4Science", "计算神经科学"),
    (["emotion recognition", "emotion and mood", "affective computing"],
     "交叉与AI4Science", "计算神经科学"),
    (["ai in cancer", "cancer detection", "medical imaging", "biomedical"],
     "交叉与AI4Science", "医学影像"),
    (["gaze tracking", "eye tracking"],
     "计算机视觉", "人体与动作理解"),
    (["activity recognition"],
     "计算机视觉", "视频理解"),
    (["image and video quality assessment", "quality assessment"],
     "计算机视觉", "图像恢复与增强"),
    (["advanced vision and imaging", "vision and imaging", "imaging techniques"],
     "计算机视觉", "图像恢复与增强"),
    # OpenAlex 把「单目/双目深度估计、立体匹配、三维重建」整片研究
    # 统一压成一个主题 "Advanced Vision and Imaging"，没有更细的分类。
    # 结果「单目与双目深度估计」在库里是 0 人 —— 这不是缺数据，是主题颗粒度太粗。
    # 这里按几何视觉的典型主题名做个兜底归位。
    (["stereo matching", "disparity", "depth completion", "monocular depth",
      "metric depth", "rgb-d"],
     "计算机视觉", "单目与双目深度估计"),
    (["structure from motion", "multi-view stereo", "photogrammetry"],
     "计算机视觉", "立体视觉与SLAM"),
    (["fatigue and fracture", "fracture mechanics"],
     "交叉与AI4Science", "科学计算"),
    (["magnetic properties", "thin films"],
     "交叉与AI4Science", "材料与化学"),
    (["materials", "chemistry", "molecular"],
     "交叉与AI4Science", "材料与化学"),
    (["agriculture", "plant "],
     "交叉与AI4Science", "生态与农业智能"),
    (["sensor technology", "measurement system"],
     "嵌入式、物联网与CPS", "物联网系统与边缘感知"),
    (["software engineering methodologies", "software engineering"],
     "软件工程", "软件开发基础与程序设计"),
    (["digital media", "visual art"],
     "计算机图形学与多媒体", "多媒体内容理解"),
    (["technology adoption", "user behaviour", "user behavior"],
     "人机交互与图形学", "交互与可用性"),
    (["matrix theory and algorithms"],
     "数学与统计基础", "线性代数与矩阵计算"),
    (["web and library services", "context-aware"],
     "系统与网络", "分布式系统"),
]


def _generic_hit(topic):
    """单个主题名是否命中通用规则，返回 (category, field) 或 None。"""
    t = (topic or "").lower()
    for terms, cat, field in GENERIC_RULES:
        if any(term in t for term in terms):
            return cat, field
    return None


def _cross_hit(topic):
    """计算驱动的交叉主题，返回 (category, field) 或 None。"""
    t = (topic or "").lower()
    for terms, cat, field in CROSS_RULES:
        if any(term in t for term in terms):
            return cat, field
    return None


def _generic_match(topics):
    lowered = [t.lower() for t in topics]
    for terms, cat, field in GENERIC_RULES:
        for t in lowered:
            if any(term in t for term in terms):
                return cat, field
    return None


def _is_non_cs(topics):
    blob = " ".join(t.lower() for t in topics)
    return any(h in blob for h in NON_CS_HINTS)


def _is_purely_non_cs(topics):
    """判断是否「纯非计算机」。

    口径：以计算机为主、允许交叉融合。

    —— 基于 ORCID 真实发表 venue 的抽查校正（25 例）——
    第一版判据按「计算类主题是否占多数」，误删率约 24%：
      Songtao Liu（YOLOX 作者，CVPR/arXiv 的计算机视觉工作）
      主题是 [半导体激光, 光器件, 光纤激光, Advanced Neural Network Applications]
      —— 计算机主题排在最后一位，被「多数规则」忽略，于是被误删。
      Xuefeng Zhao（计算机辅助土木，发在 Computer-Aided Civil and Infrastructure）
      Zhimin Zhang（SIAM Journal on Scientific Computing，计算数学）

    修正原则：**只要主题里出现明确的计算机方法主题，就保留为交叉**，
    不管它排在第几位。宁可保留一个偏应用的人，也不能删掉一个真做计算机的人。
    """
    topics_l = [t.lower() for t in topics]
    if not topics_l:
        return False

    # 出现即保留的强信号（这些主题名本身就代表计算机方法）
    strong_cs = [
        "neural network", "deep learning", "machine learning", "computer vision",
        "natural language", "data mining", "image processing", "pattern recognition",
        "artificial intelligence", "reinforcement learning", "information retrieval",
        "computer graphics", "human-computer", "software engineering",
        "algorithm", "computational mathematics", "numerical analysis",
        "topic modeling", "image and video", "vision and imaging",
    ]
    if any(any(m in t for m in strong_cs) for t in topics_l):
        return False

    # 交叉计算线索（脑机接口、医学影像、土木信息化等，方法仍是计算的）
    if any(_cross_hit(t) for t in topics_l):
        return False

    # 到这里说明没有任何计算机方法线索：看有多少主题属于非计算机领域
    non_cs_like = sum(1 for t in topics_l if any(h in t for h in NON_CS_HINTS))
    # 只要有一条是纯非 CS 且没有计算方法 → 剔除
    # （纯光学、纯数学、纯人文的学者，主题列表里不会出现 CS 方法词）
    return non_cs_like > 0


def remap(advisors, fields):
    stats = collections.Counter()
    out = []
    for a in advisors:
        topics = a.get("keywords") or []

        # 0) 学科口径过滤：纯非计算机的直接剔除，不进入索引
        if _is_purely_non_cs(topics):
            stats["excluded_non_cs"] += 1
            continue

        # 1) 具体领域映射
        mapped = []
        for topic in topics:
            for f in B.map_topic_candidates(topic, fields):
                if f not in mapped:
                    mapped.append(f)

        # 2) 通用主题 + 交叉主题兜底，参与投票
        generic = []
        for topic in topics:
            g = _generic_hit(topic) or _cross_hit(topic)
            if g and g not in generic:
                generic.append(g)

        if not mapped and not generic:
            if _is_purely_non_cs(topics):
                # 理论上第 0 步已剔除，这里兜底
                stats["excluded_non_cs"] += 1
            elif _is_non_cs(topics):
                # 有交叉计算线索但没匹配到具体领域：
                # 按口径「以计算机为主、允许交叉」，归到 AI4Science 而不是抛弃
                out.append({**a, "category": "交叉与AI4Science",
                            "categories": ["交叉与AI4Science"],
                            "fields": [], "mapping": "non_cs"})
                stats["non_cs"] += 1
            else:
                out.append({**a, "category": "", "categories": [], "fields": [],
                            "mapping": "unmapped"})
                stats["unmapped"] += 1
            continue

        counts = {}
        for it in mapped:
            counts[it["category"]] = counts.get(it["category"], 0) + 1
        for cat, fld in generic:
            # 通用主题通常描述的是「主要研究方向」，权重略高于单个具体关键词
            counts[cat] = counts.get(cat, 0) + 2

        cat = max(counts, key=counts.get)
        cats = sorted(counts, key=lambda n: (-counts[n], n))
        names = []
        for cat2, fld in generic:
            if fld not in names:
                names.append(fld)
        for it in mapped:
            if it["name"] not in names:
                names.append(it["name"])
        out.append({**a, "category": cat, "categories": cats[:5],
                    "fields": names[:8],
                    "mapping": "field" if mapped else "generic"})
        stats["field" if mapped else "generic"] += 1
    return out, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fields = B.load_taxonomy_fields()
    data = json.loads(FULL.read_text(encoding="utf-8"))
    advisors = data.get("advisors", [])

    before = collections.Counter(a.get("category") for a in advisors)
    out, stats = remap(advisors, fields)
    after = collections.Counter(a.get("category") for a in out)

    print("映射方式分布:", dict(stats))
    print()
    print("%-26s %8s %8s" % ("大类", "修复前", "修复后"))
    for c in sorted(set(before) | set(after), key=lambda x: -after.get(x, 0)):
        print("%-26s %8d %8d" % (c or "(未分类)", before.get(c, 0), after.get(c, 0)))

    if args.dry_run:
        print("\n(dry-run，未写入)")
        return

    data["advisors"] = out
    data["advisor_count"] = len(out)
    data["remapped_at"] = __import__("datetime").datetime.now().isoformat(timespec="minutes")
    data["mapping_stats"] = dict(stats)
    FULL.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已写回:", FULL)


if __name__ == "__main__":
    main()