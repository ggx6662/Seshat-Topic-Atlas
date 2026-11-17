"""多关键词 AND 检索的精确率评估。

判定：Top10 里标题或摘要同时含「领域词」算命中。
比纯向量评估更严 —— 纯向量只看标题命中一个关键词就算对。
"""
import sys

import kb_vector as V

# (关键词组, 命中判定词)  命中判定词在标题里出现即算相关
CASES = [
    (["红外", "小目标"], ["infrared", "thermal", "ir"]),
    (["去雾", "图像"], ["dehaz", "haze", "fog", "mist"]),
    (["医学", "分割"], ["medical", "clinical", "lesion", "organ"]),
    (["点云", "分割"], ["point cloud", "lidar", "3d"]),
    (["事件相机"], ["event", "neuromorphic"]),
    (["图像", "融合", "红外"], ["fusion", "fus"]),
    (["扩散模型", "生成"], ["diffusion", "generative"]),
    (["小样本", "检测"], ["few-shot", "few shot", "low-shot"]),
    (["轻量化", "检测"], ["lightweight", "efficient", "mobile"]),
    (["自监督", "分割"], ["self-supervised", "self supervised", "unsupervised"]),
]


def hit(title, keys):
    t = (title or "").lower()
    return any(k.lower() in t for k in keys)


def main():
    print("索引：%s" % {k: v for k, v in V.stats().items() if k in ("docs", "dims")})
    total = 0
    good = 0
    for terms, keys in CASES:
        r = V.search_and(terms, k=10)
        papers = r["papers"]
        h = sum(1 for p in papers if hit(p["title"], keys))
        total += len(papers)
        good += h
        print("\n[%s]  交集 %d 篇  Top%d 命中 %d"
              % (" + ".join(terms), r["count"], len(papers), h))
        print("   译成：%s" % " + ".join(r["terms"]))
        for p in papers[:5]:
            mark = "✓" if hit(p["title"], keys) else " "
            print("   %s %.3f %s" % (mark, p["score"], p["title"][:76]))
    if total:
        print("\n=== AND 检索 Top10 精确率：%d/%d = %.0f%% ===" % (good, total, 100.0 * good / total))
    return 0


if __name__ == "__main__":
    sys.exit(main())