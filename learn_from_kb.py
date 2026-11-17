#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用知识库真实论文标题，反向补充方向关键词。

为什么这样做
------------
按学科目录补词，补出来的是「教科书上的方向」；
按你自己的 343 篇论文补词，补出来的是「你真正在做的方向」。

实测：89 个有效论文标题里只有 70 个能映射到 387 个领域。
未映射的高频词集中在 **Mamba / 状态空间模型**（Mamba-YOLO、MTMamba、
Meteor Mamba、MambaMorph、GraspMamba …），这正是方向库该有却没有的。

用法
----
python learn_from_kb.py            # 分析并给出建议
python learn_from_kb.py --apply    # 直接写入 directions_library.json 的 keywords
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kb_widget as kb        # noqa: E402
import build_advisor_index as B  # noqa: E402

LIBRARY = HERE / "directions_library.json"

# 从真实论文里学到的「领域 → 应补关键词」映射。
# 每条都注明来源论文，便于核对。
LEARNED = [
    ("人工智能", "深度学习架构",
     ["mamba", "state space model", "mamba-yolo", "mtmamba", "vision mamba",
      "vmunet", "mamba2"],
     "Mamba-YOLO-World / MTMamba++ / Meteor Mamba / Motion Mamba（知识库内 20+ 篇）"),
    ("计算机视觉", "目标检测",
     ["yolo", "yolov8", "yolov12", "rt-detr", "open-vocabulary detection",
      "small object detection"],
     "Reckless Status Calculation by Using Yolo / Mamba-YOLO-World"),
    ("计算机视觉", "红外与低光视觉",
     ["infrared small target", "infrared pedestrian", "rgb-t fusion",
      "cross-spectral fusion", "thermal-infrared"],
     "MambaST Cross-Spectral Fuser / Adv-Camou Infrared Adversarial Patch"),
    ("交叉与AI4Science", "医学影像",
     ["medical image registration", "mr-ct registration", "deformable registration",
      "medical segmentation"],
     "MambaMorph: Mamba-based Medical MR-CT Deformable Registration"),
    ("机器人与具身智能", "机器人学习",
     ["imitation learning", "grasp detection", "language-driven grasp",
      "decision transformer"],
     "MaIL: Improving Imitation Learning with Mamba / GraspMamba"),
    ("计算机视觉", "视频理解",
     ["video depth", "text-video retrieval", "video understanding", "long sequence video"],
     "Video Depth Anything / MUSE: Text-video Retrieval"),
    ("计算机视觉", "人体与动作理解",
     ["micro-expression", "pedestrian attribute", "action recognition",
      "expression recognition"],
     "Boosting Micro-Expression Recognition / Mamba-based Pedestrian Attribute Recognition"),
    # —— 系统方向：OpenAlex 主题名（Advanced Database Systems and Queries 等）
    #    与方向库词表对不上，实测大量漏配，导致数据库/存储/编译几乎没人。
    ("数据库与数据管理", "查询优化",
     ["database systems", "query processing", "database management", "sql",
      "transaction processing"],
     "OpenAlex 主题 Advanced Database Systems and Queries（216 人次）"),
    ("系统与网络", "存储系统",
     ["data storage technologies", "storage system", "file system", "key-value store"],
     "OpenAlex 主题 Advanced Data Storage Technologies（60 人次）"),
    ("体系结构与高性能计算", "并行与分布式计算",
     ["distributed and parallel computing", "parallel computing systems",
      "distributed computing"],
     "OpenAlex 主题 Distributed and Parallel Computing Systems（174 人次）"),
    ("系统与网络", "容错与崩溃一致性",
     ["fault tolerance", "high availability"],
     "OpenAlex 主题 Distributed systems and fault tolerance（79 人次）"),
    ("编程语言与编译", "程序分析",
     ["compiler design", "programming languages", "type system", "code optimization"],
     "编译器/程序语言方向的主题名"),
    # —— 深度估计：OpenAlex 的主题名很少直接写 monocular depth，
    #    常写成 stereo matching / disparity / 3D reconstruction from images，
    #    导致「单目与双目深度估计」这个方向几乎没有学者。
    ("计算机视觉", "单目与双目深度估计",
     ["monocular depth", "stereo matching", "disparity", "depth from images",
      "self-supervised depth", "video depth", "metric depth", "depth completion"],
     "Video Depth Anything 等论文；OpenAlex 主题深度估计标注稀疏"),
    ("计算机视觉", "深度与3D检测",
     ["depth estimation", "rgb-d", "light field", "structure from motion"],
     "OpenAlex 主题 Depth Estimation / RGB-D"),
]

# 论文标题里出现、但方向库完全没有的「方法词」
METHOD_TERMS = {
    "mamba": ("人工智能", "深度学习架构"),
    "state space": ("人工智能", "深度学习架构"),
    "diffusion": ("人工智能", "生成模型"),
    "nerf": ("计算机视觉", "三维重建与神经渲染"),
    "gaussian splatting": ("计算机视觉", "三维重建与神经渲染"),
    "sam": ("计算机视觉", "图像分割"),
    "clip": ("计算机视觉", "视觉语言与开放词汇视觉"),
    "yolo": ("计算机视觉", "目标检测"),
}


def paper_titles():
    out = []
    try:
        for row in kb._inventory().get("files", []):
            p = str(row[2]) if isinstance(row, (tuple, list)) else str(row)
            if not p.lower().endswith(".pdf"):
                continue
            name = os.path.splitext(os.path.basename(p))[0]
            if re.fullmatch(r"[\w\-]*\d+[\w\-]*", name):
                continue          # 纯编号文件
            if len(name) < 15:
                continue
            out.append(re.sub(r"[_+]+", " ", name))
    except Exception:
        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写入 directions_library.json")
    args = ap.parse_args()

    fields = B.load_taxonomy_fields()
    titles = paper_titles()
    unmapped = [t for t in titles if not B.map_topic_candidates(t, fields)]

    print("知识库有效论文标题: %d" % len(titles))
    print("其中无法映射到领域: %d (%.0f%%)" % (
        len(unmapped), 100.0 * len(unmapped) / max(1, len(titles))))
    print()

    # 统计未映射标题里的高频技术词
    vocab = Counter()
    for t in unmapped:
        for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", t.lower()):
            vocab[w] += 1
    print("未映射标题中的高频词（前 20）:")
    for w, n in vocab.most_common(20):
        print("   %-24s %d" % (w, n))
    print()

    print("建议补充的领域关键词:")
    for cat, field, terms, src in LEARNED:
        print("  %s / %s" % (cat, field))
        print("     补: %s" % "、".join(terms))
        print("     依据: %s" % src)

    if not args.apply:
        print("\n(未写入；加 --apply 生效)")
        return

    # 领域可能位于三张表的任意一张：主库 / 扩展表 / 补充总表。
    # 只写一张会漏 —— 「单目与双目深度估计」就在扩展表里，之前一直没补上。
    files = [LIBRARY,
             HERE / "research_taxonomy_extended.json",
             HERE / "research_taxonomy_comprehensive.json"]
    added = 0
    for path in files:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        # 主库结构 {大类: {subs}}，补充表结构 {categories: {大类: {subs}}}
        cats = data if "categories" not in data else data["categories"]
        changed = 0
        for cat, field, terms, _src in LEARNED:
            entry = cats.get(cat)
            if not entry:
                continue
            for sub in entry.get("subs", []):
                if sub.get("name") != field:
                    continue
                kws = sub.setdefault("keywords", [])
                existing = {k.lower() for k in kws}
                for t in terms:
                    if t.lower() not in existing:
                        kws.append(t)
                        existing.add(t.lower())
                        changed += 1
                break
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            print("  写入 %s：%d 个关键词" % (path.name, changed))
        added += changed
    print("\n共写入 %d 个关键词" % added)


if __name__ == "__main__":
    main()