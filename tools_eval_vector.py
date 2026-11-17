"""在 53.8 万篇 arXiv 索引上评估中文查询的 Top5 精确率。

判定：标题里出现「领域词」才算命中。领域词按查询手工指定，
不看模型自评分 —— 自评分只能证明「向量像」，不能证明「论文对」。
"""
import sys

import kb_vector as V

# (查询, 标题命中判定关键词列表，任一命中即算对)
CASES = [
    ("红外小目标检测", ["infrared small target", "infrared target", "small target",
                   "infrared", "small object"]),
    ("医学图像分割", ["medical image segmentation", "medical imaging",
                 "medical segmentation", "medical"]),
    ("图像超分辨率", ["super-resolution", "super resolution", "sr"]),
    ("图像去雾", ["dehazing", "dehaze", "haze removal", "fog"]),
    ("事件相机", ["event camera", "event-based", "event stream", "neuromorphic"]),
    ("扩散模型生成", ["diffusion model", "diffusion-based", "diffusion"]),
    ("目标跟踪", ["object tracking", "tracking", "tracker"]),
    ("图像融合", ["image fusion", "fusion"]),
    ("弱光图像增强", ["low-light", "low light", "night", "dark"]),
    ("点云分割", ["point cloud segmentation", "point cloud"]),
]


def hit(title, keys):
    t = (title or "").lower()
    return any(k.lower() in t for k in keys)


def main():
    print("索引：%s" % V.stats())
    total = 0
    good = 0
    for q, keys in CASES:
        segs = V.explain(q)
        res = V.search(q, k=5)
        h = sum(1 for r in res if hit(r["title"], keys))
        total += len(res)
        good += h
        seg_txt = " + ".join("%s→%s(%.1f)" % (s["cn"][:8], s["en"][:22], s["w"]) for s in segs)
        print("\n[%s]  Top5 命中 %d/5" % (q, h))
        print("  分段: %s" % (seg_txt or "(无)"))
        for r in res:
            print("   %s %.3f %s %s" % ("✓" if hit(r["title"], keys) else " ", r["score"],
                                        r["date"], r["title"][:78]))
    print("\n总体 Top5 精确率：%d/%d = %.0f%%" % (good, total, 100.0 * good / total))
    return 0


if __name__ == "__main__":
    sys.exit(main())