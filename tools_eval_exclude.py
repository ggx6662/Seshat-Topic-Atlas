"""排除词效果实测：同一组关键词，加 -排除词 前后 Top10 相关度。

判定：标题含判定词即算相关（和 tools_eval_and 同一口径）。
"""
import sys

import kb_vector as V

# (查询串, 判定词)  查询串里带 - 就是排除词写法
CASES = [
    ("去雾 图像", ["dehaz", "haze", "fog", "mist"]),
    ("去雾 图像 -restoration", ["dehaz", "haze", "fog", "mist"]),
    ("小样本 检测", ["few-shot", "few shot", "low-shot"]),
    ("小样本 检测 -anomaly", ["few-shot", "few shot", "low-shot"]),
    ("轻量化 检测", ["lightweight", "efficient", "mobile"]),
    ("轻量化 检测 -anomaly", ["lightweight", "efficient", "mobile"]),
    ("自监督 分割", ["self-supervised", "self supervised", "unsupervised"]),
    ("自监督 分割 -medical -mri -ct", ["self-supervised", "self supervised", "unsupervised"]),
]


def hit(title, keys):
    t = (title or "").lower()
    return any(k.lower() in t for k in keys)


def main():
    has_cache = "bodies" in V._CACHE
    print("正文缓存：%s（首次加载约 30 秒）\n" % ("已在内存" if has_cache else "需加载"))
    for q, keys in CASES:
        r = V.search_and(q, k=10)
        ps = r["papers"]
        h = sum(1 for p in ps if hit(p["title"], keys))
        print("%-34s 命中 %6d  排除前 %6d  Top10 %d/%d"
              % (q, r["count"], r["count_before_exclude"], h, len(ps)))
        if q.count("-") == 0 and h < len(ps):
            for p in ps:
                if not hit(p["title"], keys):
                    print("       漏网：%s" % p["title"][:80])
    return 0


if __name__ == "__main__":
    sys.exit(main())