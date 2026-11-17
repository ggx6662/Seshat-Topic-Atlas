"""在 5 万篇样本上对比 bge 中文向量 vs TF-IDF+SVD，判定要不要全量重建。

判定标准（写死，不允许事后改）：同一套 10 个查询，Top5 标题命中率。
  ≥ 85%  → 全量重建
  70~85% → 只对高频方向重建，其余保留
  < 70%  → 不换，承认这条路也不行

bge 的用法要点
--------------
* bge-zh 检索时必须给查询加指令前缀「为这个句子生成表示以用于检索相关文章：」，
  文档端不加。不加前缀召回会明显掉（官方 README 明写）。
* 53.8 万篇 CPU 编码约 1.5–2 小时，所以先用 5 万篇做判据。
"""
import json
import sys
import time

import numpy as np

from tools_eval_vector import CASES, hit

BGE_DIR = r"G:\kb-vector\models\bge-small-zh-v1.5"
PREFIX = "为这个句子生成表示以用于检索相关文章："
SAMPLE = 50000


def load_sample(n=SAMPLE):
    """分层抽样：按 157 个时间窗口等量抽样，保证覆盖全部 3 年、全部 cs 子类。

    为什么不能用等间隔抽样
    --------------------
    538k 条是按窗口文件顺序排列的，等间隔取 1/10 等于只取最早那段窗口 ——
    实测抽出来全是 2023-11 的数学/拓扑论文，查「红外小目标检测」得 0/5。
    那个 10% 是抽样错误，不是模型成绩。
    """
    import glob

    import kb_vector as V
    files = sorted(glob.glob(str(V.SRC / "*.jsonl")))
    per = max(1, n // max(1, len(files)))
    docs, idxs = [], []
    # 用全库 id 顺序做下标，方便和 TF-IDF 层对照
    id_map = {str(x): i for i, x in enumerate(V.load()["ids"])}
    for f in files:
        buf = []
        with open(f, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = __import__("json").loads(ln)
                except Exception:
                    continue
                buf.append(r)
                if len(buf) >= per * 7:      # 够抽就停，文件很大时省时间
                    break
        step = max(1, len(buf) // per)
        for r in buf[::step][:per]:
            i = id_map.get(str(r["id"]))
            if i is None:
                continue
            title = str(V.load()["titles"][i])
            docs.append(title + " " + title)
            idxs.append(i)
    return np.array(idxs), docs


def main():
    t0 = time.time()
    import kb_vector as V
    print("索引：%s" % V.stats(), flush=True)
    idx, docs = load_sample()
    print("抽样 %d 篇（全库 %d）" % (len(docs), len(V.load()["ids"])), flush=True)

    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(BGE_DIR, device="cpu")
    dim = m.get_sentence_embedding_dimension()
    print("模型载入 %.1fs，维度 %d" % (time.time() - t0, dim), flush=True)

    t1 = time.time()
    E = m.encode(docs, batch_size=64, normalize_embeddings=True,
                 show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
    print("编码 %d 篇 %.1f 分钟（%.0f 篇/分）"
          % (len(docs), (time.time() - t1) / 60, len(docs) / ((time.time() - t1) / 60)),
          flush=True)

    # 全量 53.8 万篇的预计耗时
    est_h = 538189 / (len(docs) / max(1e-6, (time.time() - t1))) / 3600
    print("推算全量 538,189 篇编码约 %.1f 小时" % est_h, flush=True)

    titles = [str(V.load()["titles"][i]) for i in idx]
    total_hit = 0
    total_n = 0
    rows = []
    # 同时跑一版「英文查询」，用来区分「跨语言失败」和「模型失败」
    try:
        import arxiv_latest as AL
    except Exception:
        AL = None
    for q, keys in CASES:
        qv = m.encode([PREFIX + q], normalize_embeddings=True)[0].astype(np.float32)
        sc = E @ qv
        top = np.argsort(-sc)[:5]
        h = sum(1 for i in top if hit(titles[i], keys))
        total_hit += h
        total_n += 5
        rows.append((q, h, [titles[i][:76] for i in top]))
        print("\n[%s] bge Top5 命中 %d/5" % (q, h), flush=True)
        for i in top:
            mark = "✓" if hit(titles[i], keys) else " "
            print("   %s %.3f %s" % (mark, sc[i], titles[i][:80]), flush=True)
        if AL is not None:
            en = AL.to_english(q)
            qe = m.encode([PREFIX + en], normalize_embeddings=True)[0].astype(np.float32)
            sce = E @ qe
            tope = np.argsort(-sce)[:5]
            he = sum(1 for i in tope if hit(titles[i], keys))
            print("   [英文查询 %r] 命中 %d/5  首条：%s"
                  % (en, he, titles[tope[0]][:60] if len(tope) else "-"), flush=True)

    pct = 100.0 * total_hit / total_n
    print("\n=== bge 总体 Top5 精确率：%d/%d = %.0f%% ===" % (total_hit, total_n, pct))
    print("对照：TF-IDF+SVD 在全库上为 70%%")
    verdict = ("全量重建" if pct >= 85 else
               ("只对高频方向重建，其余保留" if pct >= 70 else "不换，这条路也不行"))
    print("判据结论：%s" % verdict)

    out = {"sample": len(docs), "dims": dim, "top5_pct": pct,
           "est_full_hours": round(est_h, 2), "verdict": verdict,
           "cases": [{"q": q, "hit": h} for q, h, _ in rows]}
    with open(r"G:\kb-vector\index\eval_bge.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())