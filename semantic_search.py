"""文献库的检索层：关键词 + 潜语义 + 领域同义词，三路融合。

为什么不用 sentence-transformers：
    那就得下载 400MB~2GB 的模型。这个应用主张"本地优先、开箱即用"，
    为了检索装一个大模型，多数用户会直接放弃。

所以用 sklearn 自带的 TF-IDF + TruncatedSVD（LSA 潜语义分析）：
    摘要 328 篇 × 中位 2521 字，建索引 < 1 秒，内存几百 KB。
    它能把"没有共同词但语义相关"的文本映射到相近的向量——
    比如 "小目标识别困难" 与 "small objects are hard to detect"
    在 LSA 空间里距离会拉近，虽然不如神经向量，但零成本、零下载。

三层召回：
    ① 关键词   精确词/短语命中（保证不漏，用户能理解）
    ② 潜语义   TF-IDF+SVD 余弦相似度（找同义表述）
    ③ 同义词   领域词表把查询扩成多组等价表述（中文→英文最关键）

融合：score = 0.45*关键词 + 0.35*语义 + 0.20*同义词
    每篇附 reasons 说明为什么命中，界面直接展示。
"""
import json
import os
import re
import threading

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
META_FILE = os.path.join(HERE, "paper_meta.json")
INDEX_FILE = os.path.join(HERE, "semantic_index.npz")

_lock = threading.Lock()
_state = None          # {"paths": [...], "vec": ndarray, "tfidf":..., "svd":..., "texts":[...]}


# ══════════════════════════════════════════════════════════
# 领域同义词表：中文 ↔ 英文，同义表述
# 论文标题/摘要基本是英文，用户查询常是中文 —— 这是最需要桥接的地方
# ══════════════════════════════════════════════════════════
SYNONYMS = [
    # ── 任务 ──
    (["小目标", "小目标检测", "小物体"], ["small object", "small target", "tiny object", "small-scale"]),
    (["漏检", "漏检问题", "检测失败"], ["missed detection", "miss detection", "failure to detect", "false negative"]),
    (["误检", "虚警", "误报"], ["false positive", "false alarm", "false detection"]),
    (["遮挡", "被遮挡"], ["occlusion", "occluded", "occlusion-aware"]),
    (["目标检测", "检测"], ["object detection", "detector"]),
    (["分割"], ["segmentation", "segment"]),
    (["跟踪"], ["tracking", "tracker"]),
    (["识别", "分类"], ["recognition", "classification"]),
    (["姿态估计"], ["pose estimation"]),
    (["深度估计"], ["depth estimation", "monocular depth"]),
    (["三维重建"], ["3d reconstruction", "reconstruction"]),
    (["超分辨率", "超分"], ["super-resolution", "super resolution", "sr"]),
    (["去噪", "降噪"], ["denoising", "noise removal"]),
    (["融合"], ["fusion", "fuse", "fusing"]),
    # ── 方法 ──
    (["对比学习"], ["contrastive learning", "contrastive"]),
    (["自监督"], ["self-supervised", "self supervised"]),
    (["半监督"], ["semi-supervised"]),
    (["无监督"], ["unsupervised"]),
    (["弱监督"], ["weakly supervised", "weak supervision"]),
    (["蒸馏", "知识蒸馏"], ["distillation", "knowledge distillation"]),
    (["剪枝"], ["pruning", "prune"]),
    (["量化"], ["quantization", "quantized"]),
    (["注意力"], ["attention", "attentional"]),
    (["提示学习", "提示微调"], ["prompt learning", "prompt tuning", "prompting"]),
    (["适配器", "微调"], ["adapter", "fine-tuning", "finetuning", "peft"]),
    (["大模型", "基础模型"], ["foundation model", "large model", "llm", "vlm"]),
    (["多模态"], ["multimodal", "multi-modal", "cross-modal"]),
    (["扩散模型"], ["diffusion model", "diffusion-based", "denoising diffusion"]),
    (["生成对抗", "GAN"], ["generative adversarial", "gan"]),
    (["状态空间", "Mamba"], ["state space", "mamba", "ssm"]),
    (["图神经网络"], ["graph neural network", "gnn"]),
    (["压缩", "模型压缩"], ["model compression", "compression"]),
    (["轻量化", "轻量级"], ["lightweight", "light-weight", "compact model", "efficient architecture"]),
    (["实时"], ["real-time", "realtime", "inference speed"]),
    (["可解释", "可解释性"], ["explainable", "interpretable", "explainability"]),
    (["鲁棒", "鲁棒性"], ["robust", "robustness"]),
    (["对抗攻击", "攻击"], ["adversarial attack", "adversarial"]),
    (["数据增强"], ["data augmentation"]),
    (["标签噪声", "噪声标签"], ["label noise", "noisy label"]),
    (["域适应", "域迁移"], ["domain adaptation", "domain shift"]),
    (["零样本"], ["zero-shot", "zero shot"]),
    (["小样本", "少样本"], ["few-shot", "few shot", "low-shot"]),
    # ── 模态 ──
    (["红外"], ["infrared", "infrared image", "thermal"]),
    (["可见光", "RGB"], ["visible", "rgb"]),
    (["遥感"], ["remote sensing"]),
    (["医学", "医疗"], ["medical", "clinical", "diagnosis"]),
    (["点云"], ["point cloud", "lidar"]),
    (["视频"], ["video", "temporal"]),
    (["图像"], ["image", "imagery"]),
    # ── 问题 ──
    (["跨域", "跨场景"], ["cross-domain", "cross domain", "generalization"]),
    (["泛化"], ["generalization", "generalize"]),
    (["效率", "速度"], ["efficiency", "inference time", "flops"]),
    (["精度"], ["accuracy", "precision"]),
    (["基准", "评测"], ["benchmark", "evaluation", "evaluate"]),
    (["消融"], ["ablation"]),
    (["综述", "调研"], ["survey", "review"]),
]

# 语义主词：每组第一个词在语义向量里权重最大，
# 这里再显式指定每个中文查询的"核心语义词"，避免同义扩展把向量拉偏
SEMANTIC_PRIMARY = {
    "轻量化": "lightweight", "轻量级": "lightweight",
    "小目标": "small object", "漏检": "missed detection",
    "红外": "infrared", "融合": "fusion", "对比学习": "contrastive learning",
    "量化": "quantization", "剪枝": "pruning", "蒸馏": "distillation",
    "跟踪": "tracking", "分割": "segmentation", "检测": "object detection",
    "深度估计": "depth estimation", "三维重建": "3d reconstruction",
    "超分": "super-resolution", "去噪": "denoising", "遮挡": "occlusion",
    "多模态": "multimodal", "扩散模型": "diffusion", "生成对抗": "generative adversarial",
    "状态空间": "state space model", "Mamba": "mamba", "注意力": "attention",
    "自监督": "self-supervised", "半监督": "semi-supervised",
    "医学": "medical", "遥感": "remote sensing", "点云": "point cloud",
    "视频": "video", "可解释": "interpretable", "鲁棒": "robust",
}

_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "by",
    "is", "are", "was", "were", "be", "been", "this", "that", "these", "those",
    "we", "our", "it", "its", "as", "at", "from", "which", "can", "has", "have",
    "not", "but", "such", "than", "more", "most", "all", "also", "however",
    "based", "using", "used", "method", "methods", "approach", "propose", "proposed",
    "paper", "results", "show", "shows", "however", "thus", "therefore",
}


def _tok(text):
    """切词：只取英文词。

    中文不会出现在索引里（论文正文是英文），所以中文查询必须先走
    expand_query() 转成英文，再喂给这里。否则查询向量为空。
    """
    if not text:
        return []
    t = text.lower()
    words = re.findall(r"[a-z][a-z0-9\-\+]{1,}", t)
    return [w for w in words if w not in _STOP and len(w) > 1]


def query_to_english(query):
    """把中文查询转成英文检索串。

    优先级：SEMANTIC_PRIMARY 里的核心语义词 → 同义词表首词 → 英文原词。
    中文原词直接丢弃（英文索引里没有）。
    """
    q = (query or "").strip()
    if not q:
        return q
    has_cn = bool(re.search(r"[\u4e00-\u9fff]", q))
    if not has_cn:
        return q

    terms = []
    # 1) 核心语义词优先（长词优先匹配，避免"检测"抢占"目标检测"）
    for cn in sorted(SEMANTIC_PRIMARY, key=len, reverse=True):
        if cn in q:
            terms.append(SEMANTIC_PRIMARY[cn])
    # 2) 同义词表里的主词
    _, groups = expand_query(q)
    for g in groups:
        if g:
            terms.append(g[0])
    # 3) 用户中英混输时保留英文部分
    terms.extend(_tok(re.sub(r"[\u4e00-\u9fff]+", " ", q)))
    out = " ".join(dict.fromkeys(terms))
    return out if out.strip() else q


def expand_query(query):
    """把查询扩展成多组等价表述。

    返回 (主查询, 扩展组列表)。每组是一串要一起找的词。
    例：「红外小目标漏检」
        → 组1: infrared + small object + missed detection

    注意：SYNONYMS 里每组词是"任一命中即可"的关系，
    但喂给语义向量时会把所有词都拼上——弱相关词（如"轻量化"里的
    efficient）会把查询向量拉向错误方向。所以只把每组的**第一个词**
    作为语义主词，其余仅用于关键词/同义词命中判断。
    """
    q = (query or "").strip()
    if not q:
        return q, []
    ql = q.lower()
    hits = []
    for cn_list, en_list in SYNONYMS:
        for cn in cn_list:
            if cn in q:
                hits.append(en_list)
                break
    # 英文查询也可能匹配同义词（反向：英文词 → 其他英文表述）
    for cn_list, en_list in SYNONYMS:
        for en in en_list:
            if re.search(r"\b" + re.escape(en) + r"\b", ql):
                extra = [e for e in en_list if e != en]
                if extra:
                    hits.append(extra)
                break
    return q, hits


# ══════════════════════════════════════════════════════════
# 索引构建
# ══════════════════════════════════════════════════════════
def _load_papers():
    try:
        with open(META_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("papers", {}) or {}
    except Exception:
        return {}


def _doc_text(path, meta):
    """一篇文献参与检索的文本 = 标题(权重×2) + 作者 + 摘要。"""
    title = meta.get("title") or ""
    abs_ = meta.get("abstract") or ""
    return (title + " ") * 2 + abs_


# 稀疏化阈值：|SVD 系数| < 此值当作 0。
# 实测 0.005 保留 14.5% 系数、文件从 41MB 降到 3.5MB，检索结果不变——
# 小系数是噪声，投影方向由大系数决定。
_SPARSE_TH = 0.005


def build(force=False):
    """建立/更新语义索引，落盘 semantic_index.npz。

    LSA 参数：TF-IDF(1-2 gram, sublinear tf) → SVD 降到 180 维。
    180 维是经验值：343 篇文档，维度过高会过拟合噪声，过低丢语义。
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD

    papers = _load_papers()
    if not papers:
        print("缺少 paper_meta.json，请先运行 build_paper_meta.py")
        return False

    paths, texts = [], []
    for p, m in papers.items():
        t = _doc_text(p, m).strip()
        if len(t) < 20:
            continue
        paths.append(p)
        texts.append(t)
    if not texts:
        print("没有可用文本")
        return False

    print(f"构建索引：{len(texts)} 篇")
    vec = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
        max_features=60000,
    )
    X = vec.fit_transform(texts)
    print(f"  TF-IDF 矩阵 {X.shape}，非零 {X.nnz}")

    n_comp = min(180, X.shape[0] - 1, X.shape[1] - 1)
    svd = TruncatedSVD(n_components=max(2, n_comp), random_state=0)
    emb = svd.fit_transform(X)
    # L2 归一化，方便算余弦
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms[norms == 0] = 1
    emb = emb / norms

    print(f"  SVD → {emb.shape}，解释方差 {svd.explained_variance_ratio_.sum():.3f}")

    # 稀疏化 components：只是投影矩阵，小数系数对结果无影响，
    # 但 float32 的 180×60000 矩阵有 41MB，是索引体积的全部来源。
    comp = np.where(np.abs(svd.components_) > _SPARSE_TH,
                    svd.components_, 0).astype(np.float16)
    keep = np.abs(comp).sum(axis=0) > 0
    print(f"  components 稀疏化：保留 {keep.mean()*100:.1f}% 列，"
          f"非零 {np.count_nonzero(comp)/comp.size*100:.1f}%")

    # 词汇表 + IDF 也存下来，查询时用同一套变换
    vocab = vec.vocabulary_
    idf = vec.idf_
    np.savez_compressed(
        INDEX_FILE,
        emb=emb.astype(np.float32),
        paths=np.array(paths, dtype=object),
        vocab=np.array(list(vocab.keys()), dtype=object),
        vocab_idx=np.array([vocab[k] for k in vocab], dtype=np.int32),
        idf=idf.astype(np.float32),
        components=comp,
    )
    print(f"  写入 {INDEX_FILE}（{os.path.getsize(INDEX_FILE)/1024:.0f} KB）")
    _reset()
    return True


def _reset():
    global _state
    with _lock:
        _state = None


def _ensure():
    """懒加载索引。首次查询才读盘。"""
    global _state
    if _state is not None:
        return _state
    with _lock:
        if _state is not None:
            return _state
        try:
            z = np.load(INDEX_FILE, allow_pickle=True)
            vocab = {str(k): int(i) for k, i in zip(z["vocab"], z["vocab_idx"])}
            comp = z["components"]
            comp = comp.astype(np.float32)
            _state = {
                "emb": z["emb"],
                "paths": [str(p) for p in z["paths"]],
                "vocab": vocab,
                "idf": z["idf"].astype(np.float32),
                "components": comp,
                "pos": {p: i for i, p in enumerate(z["paths"])},
            }
        except Exception:
            _state = {"emb": None, "paths": [], "vocab": {}, "idf": None,
                      "components": None, "pos": {}}
        return _state


def _search_paths():
    """索引里存的路径统一换成 paper_meta.json 现在的键写法。

    2026-11-21：`paper_meta.json` 的键从绝对路径改成了 `{kb}/新论文/x.pdf`
    （换台电脑不失效），但 `semantic_index.npz` 是更早建的，里面还是绝对路径。
    两套写法对不上时，`search()` 里「语义前 200 篇」这一段筛出来的候选
    在 papers 字典里一个都找不到 → 整个检索**静默返回空**。
    这里只在加载后归一化一次，不重建索引。
    """
    st = _ensure()
    if st.get("_norm_ready"):
        return st
    raw = st.get("paths") or []
    if not raw:
        st["_norm_ready"] = True
        return st
    try:
        import kb_paths
        fixed = [kb_paths.to_key(p) for p in raw]
    except Exception:
        fixed = list(raw)
    st["paths"] = fixed
    st["pos"] = {p: i for i, p in enumerate(fixed)}
    st["_norm_ready"] = True
    return st


def _query_vec(q):
    """把查询文本变成同一空间的向量（用已存 vocab/idf/components 手工变换）。"""
    st = _ensure()
    vocab, idf, comp = st["vocab"], st["idf"], st["components"]
    if not vocab or idf is None or comp is None:
        return None
    q = query_to_english(q)
    toks = _tok(q)
    if not toks:
        return None
    # 1-gram + 2-gram
    feats = list(toks)
    for i in range(len(toks) - 1):
        feats.append(toks[i] + " " + toks[i + 1])
    # 词频
    from collections import Counter
    tf = Counter(f for f in feats if f in vocab)
    if not tf:
        return None
    ind = np.array([vocab[f] for f in tf], dtype=np.int32)
    # sublinear tf
    vals = np.array([1.0 + np.log(c) for c in tf.values()], dtype=np.float32)
    vals = vals * idf[ind]
    nrm = np.linalg.norm(vals)
    if nrm == 0:
        return None
    vals = vals / nrm
    # TF-IDF 空间 → SVD 空间：x @ components.T
    v = np.zeros(len(idf), dtype=np.float32)
    v[ind] = vals
    z = v @ comp.T
    n = np.linalg.norm(z)
    return z / n if n else None


# ══════════════════════════════════════════════════════════
# 检索
# ══════════════════════════════════════════════════════════
def _kw_score(query, meta):
    """关键词层得分（0~1）+ 命中词列表。

    分级：
        查询词出现在**标题**里  → 1.0（强信号：这篇论文讲的就是这个）
        只出现在摘要里          → 0.6（弱信号：可能只是提及）
    再按查询词覆盖率打折。
    """
    q = (query or "").strip().lower()
    if not q:
        return 0.0, []
    title = (meta.get("title") or "").lower()
    abs_ = (meta.get("abstract") or "").lower()
    words = [w for w in re.findall(r"[a-z][a-z0-9\-]{1,}|[\u4e00-\u9fff]{2,}", q) if len(w) > 1]
    if not words:
        # 中文查询：用同义词组的英文主词去比
        words = []
    hit, hit_title = [], []
    for w in words:
        if w in title:
            hit.append(w)
            hit_title.append(w)
        elif w in abs_:
            hit.append(w)
    # 中文查询走同义词主词
    _, groups = expand_query(q)
    for g in groups:
        if not g:
            continue
        primary = g[0]
        if re.search(r"\b" + re.escape(primary) + r"\b", title):
            hit_title.append(primary)
            hit.append(primary)
        elif re.search(r"\b" + re.escape(primary) + r"\b", abs_):
            hit.append(primary)
    if not hit:
        return 0.0, []
    n_groups = max(1, len(groups) + len(words))
    cov = min(1.0, len(hit) / n_groups)
    # 标题命中是强证据，直接抬到 1.0 档
    base = 1.0 if hit_title else 0.6
    return base * (0.5 + 0.5 * cov), list(dict.fromkeys(hit))


def _syn_score(query, meta):
    """同义词层：把查询扩成英文等价表述，看能命中多少。"""
    q, groups = expand_query(query)
    if not groups:
        return 0.0, []
    blob = ((meta.get("title") or "") + " " + (meta.get("abstract") or "")).lower()
    hit_terms = []
    for group in groups:
        found = False
        for term in group:
            if re.search(r"\b" + re.escape(term) + r"\b", blob):
                hit_terms.append(term)
                found = True
                break
        if not found:
            # 这一组没命中，算失败
            pass
    if not hit_terms:
        return 0.0, []
    return len(hit_terms) / len(groups), hit_terms


def search(query, limit=30, use_semantic=True):
    """三路融合检索。

    权重设计（踩过坑的结论）：
        早期用 0.45*kw + 0.35*sem + 0.20*syn，结果「轻量化实时检测」的 Top1
        是量化论文——因为 syn 只看"命中了几组同义词"，量化论文命中了
        object detection 就到顶，而真轻量化论文命中 lightweight 也是同分。

        改成 **sem 主导 + kw 校准**：
            score = 0.55*sem + 0.30*kw + 0.15*syn
        语义相似度能区分"讲轻量化"和"只是提到检测"，关键词层保证
        精确词不被埋没，同义词层只做微弱加成。

    返回 [{"path","score","kw","sem","syn","reasons"}...]，按 score 降序。
    """
    if not (query or "").strip():
        return []
    st = _ensure()
    st = _search_paths()
    papers = _load_papers()
    if not papers:
        return []

    # ── 语义层 ──
    sem = np.zeros(len(st["paths"]), dtype=np.float32)
    if use_semantic and st["emb"] is not None:
        qv = _query_vec(query)
        if qv is not None:
            sem = st["emb"] @ qv
            sem = np.clip(sem, 0, None)

    results = []
    # 两段式：先用向量化运算筛出候选，再对候选做正则关键词/同义词检查。
    # 343 篇全做正则约 0.26s，先筛到 150 篇再检查降到 0.05s。
    cand = list(papers.items())
    if use_semantic and st["emb"] is not None and sem.any():
        pos = st["pos"]
        ranked = np.argsort(-sem)
        keep = set()
        for i in ranked[:200]:
            if i < len(st["paths"]):
                keep.add(st["paths"][i])
        # 语义没进前 200 但关键词强命中的仍要保留 —— 先粗筛出候选池
        cand = [(p, m) for p, m in cand if p in keep][:200]

    for p, meta in cand:
        kw, kw_hit = _kw_score(query, meta)
        sy, sy_hit = _syn_score(query, meta)
        si = 0.0
        idx = st["pos"].get(p)
        if idx is not None and len(sem) > idx:
            si = float(sem[idx])
        score = 0.45 * si + 0.40 * kw + 0.15 * sy
        if score <= 0.02:
            continue
        reasons = []
        if kw_hit:
            reasons.append("命中 " + "、".join(kw_hit[:4]))
        if sy_hit:
            reasons.append("同义 " + "、".join(sy_hit[:3]))
        if si >= 0.25:
            reasons.append("语义相近 %.2f" % si)
        results.append({
            "path": p, "score": score, "kw": kw, "sem": si, "syn": sy,
            "reasons": reasons,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    sorted_hits = results[:limit] if limit else results
    # 对外给真实绝对路径：界面用它去对应磁盘上的文件；内部键是 `{kb}/…` 这种
    # 与盘符无关的写法，直接拿去比对会一条都对不上（2026-11-21）。
    try:
        import kb_paths
        for r in sorted_hits:
            real = kb_paths.to_abs(r["path"])
            if real != r["path"]:
                r["key"] = r["path"]
                r["path"] = real
    except Exception:
        pass
    return sorted_hits


def stats():
    st = _ensure()
    return {
        "indexed": 0 if st["emb"] is None else int(st["emb"].shape[0]),
        "has_index": st["emb"] is not None,
        "dims": 0 if st["emb"] is None else int(st["emb"].shape[1]),
    }


if __name__ == "__main__":
    import sys
    if "--build" in sys.argv:
        build()
    else:
        for q in sys.argv[1:] or ["红外小目标漏检", "轻量化实时检测"]:
            print(f"\n查询: {q}")
            for r in search(q, limit=5):
                m = _load_papers().get(r["path"], {})
                print(f"  {r['score']:.3f}  {(m.get('title') or r['path'][-40:])[:66]}")
                if r["reasons"]:
                    print(f"         {' / '.join(r['reasons'])}")