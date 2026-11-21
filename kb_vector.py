"""arXiv 全库向量化：TF-IDF + TruncatedSVD，零依赖（numpy + sklearn）。

为什么不用 bge / 神经嵌入
------------------------
本地 343 篇用 TF-IDF+SVD 实测「拿标题前几个词当查询、Top1 回到原论文」命中 89.7%
（Top3 97.1%，310 条可评，评测脚本 `.tmp/eval_local_top3.py`），够用；45 万篇用神经模型
需要 GPU 跑好几个小时，且要下 400MB~2GB 模型。先用能跑通的方案，
召回不够再升级 —— 升级时只需替换 `embed()`，外部接口不变。

产物（`G:\\kb-vector\\index\\`）
------------------------------
* `meta.bin`  : ids / titles / dates / cats 的**定长+堆**混合包（见 _pack_field）
* `emb.npy`   : float16 (N, 180) 归一化后的稠密向量（按 mmap 打开，不入堆）
* `tfidf.pkl` : TfidfVectorizer（约 60–120MB）
* `svd.pkl`   : TruncatedSVD
* `index.json`: 构建信息（时间、篇数、词表大小、耗时）
* `meta.npz`  : **旧格式**，仅用于兼容读取，新构建不再写

为什么换了存储格式（2026-11-14）
--------------------------------
旧的 `np.savez(meta.npz, titles=np.array(titles))` 有两个问题，
合起来让索引常驻内存 1.2 GB、冷启动 9.5 秒：

1. `np.savez` **不压缩**，835 MB 落盘就是 835 MB 读进内存；
2. `np.array(list_of_str)` 推出来的 dtype 是**定长 `<U250`** ——
   538189 × 250 × 4 字节 = 513 MB，而标题平均只有 ~80 个字符，
   **约 700 MB 是零填充**（cats 用 `<U131`，同样问题）。

改成「定长数组（短字段）+ 拼接大 bytes + 偏移表（长字段）」后
titles 513→46 MB、cats 269→10.5 MB，实测整包 782 MB→56.7 MB。
外面读到的是 `_Packed`，`d["titles"][i]` 这种写法不用改。

同时 `emb.npy` 改用 `mmap_mode="r"`：搜索里 `E @ zv` 会分块读，
不再需要把 184 MB float16 整块 `astype(float32)` 成 387 MB 再丢掉。

用法
----
    python kb_vector.py --build                # 全量构建
    python kb_vector.py --build --limit 100000 # 先用 10 万篇试
    python kb_vector.py --search "红外小目标检测" -k 10
    python kb_vector.py --eval                 # 召回验证
"""
import argparse
import glob
import json
import os
import pickle
import re
import struct
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

def _base_dir():
    """arXiv 索引的存放根。优先级：

    1. 环境变量 `KB_VECTOR_DIR`（换电脑、放移动硬盘时最省事）；
    2. config.json 里的 `kb_vector_path`（界面「设置与数据」可改）；
    3. 原来的 `G:\\kb-vector`（老机器保持不变，不必搬家）。

    索引约 1.5 GB，不进 git、也不跟程序走，所以单独定根目录而不是放进仓库。
    """
    v = os.environ.get("KB_VECTOR_DIR", "").strip()
    if v:
        return Path(v)
    try:
        import kb_widget
        cfg = kb_widget.load_config() or {}
        c = (cfg.get("kb_vector_path") or "").strip()
        if c:
            return Path(c)
    except Exception:
        pass
    return Path(r"G:\kb-vector")


BASE = _base_dir()
OUT = BASE / "index"
SRC = BASE / "arxiv_cs"

DIMS = 180
MIN_DF = 2           # 只出现 1 次的词不可能是好特征，且把词表从百万级压到十万级
MAX_FEATURES = 200000

# 检索时的中→英映射：复用 arxiv_latest 的 220 条词表，避免两处维护
try:
    import arxiv_latest as _AL
    _CN2EN = _AL.CN2EN
except Exception:
    _CN2EN = {}

_STOP = set("""a an the of for with and or to in on at by from as is are was were be been
this that these those we our it its their they them can may could would should will
using used use based via toward towards into within under over between among which who
while when where how what such more most less least very also than then there here
paper propose proposed approach method methods result results show shows showing
new novel first two three both each other some any all not no but if so do does did
have has had one two three""".split())


def to_english(q):
    """中文查询转英文关键词。长词优先，避免「目标检测」被「检测」先替换掉。"""
    if not q:
        return ""
    out = q
    for cn in sorted(_CN2EN, key=len, reverse=True):
        if cn in out:
            en = _CN2EN[cn]
            en = en[0] if isinstance(en, (list, tuple)) else str(en)
            out = out.replace(cn, " " + en + " ")
    out = re.sub(r"[^\x00-\x7f]+", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def _iter_records():
    for f in sorted(glob.glob(str(SRC / "*.jsonl"))):
        with open(f, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    yield json.loads(ln)
                except Exception:
                    continue


def _doc_text(r):
    t = r.get("title") or ""
    a = r.get("abstract") or ""
    # 标题重复两遍抬高权重
    return (t + " " + t + " " + a).lower()


META_MAGIC = b"KBVMETA1"
META_FILE = "meta.bin"


class _Packed:
    """定长字段 + 拼接字符串堆，支持 `x[i]` 随机访问。

    为什么不用 numpy 定长 `<U250`：见模块 docstring —— 定长会在短标题上
    填充大量零字节，538189 条标题就吃掉 513 MB，而这些零字节**照样占内存**。
    这里把 N 条字符串首尾拼成一个大 bytes，另存一个 N+1 长的 int64 偏移表，
    单条访问就是一次切片 + decode，成本可以忽略。
    """

    __slots__ = ("_blob", "_off", "_n")

    def __init__(self, blob, off):
        self._blob = blob
        self._off = off
        self._n = len(off) - 1

    def __len__(self):
        return self._n

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(self._n))]
        if i < 0:
            i += self._n
        if not 0 <= i < self._n:
            raise IndexError(i)
        return self._blob[self._off[i]:self._off[i + 1]].decode("utf-8", "replace")

    def __iter__(self):
        for i in range(self._n):
            yield self[i]

    @property
    def nbytes(self):
        return len(self._blob) + self._off.nbytes


def _pack_field(values):
    """把字符串序列打成 (blob, off)。空序列也给合法的 N=0 结构。"""
    enc = [("" if v is None else str(v)).encode("utf-8") for v in values]
    off = np.zeros(len(enc) + 1, dtype=np.int64)
    if enc:
        np.cumsum(np.fromiter((len(b) for b in enc), dtype=np.int64,
                              count=len(enc)), out=off[1:])
    return b"".join(enc), off


def _save_meta(path, fields):
    """写 meta.bin：magic + json 头 + 每个字段的 (blob, off)。"""
    header = {}
    body = []
    pos = 0
    for name, values in fields.items():
        blob, off = _pack_field(values)
        header[name] = {"offset": pos, "blob": len(blob),
                        "off_bytes": int(off.nbytes), "n": int(len(off) - 1)}
        body.append(blob)
        pos += len(blob)
        body.append(off.tobytes())
        pos += off.nbytes
    head = json.dumps(header, ensure_ascii=False).encode("utf-8")
    with open(path, "wb") as f:
        f.write(META_MAGIC)
        f.write(struct.pack("<I", len(head)))
        f.write(head)
        for b in body:
            f.write(b)


def _load_meta(path):
    """读 meta.bin，返回 {name: _Packed}。"""
    raw = Path(path).read_bytes()
    if not raw.startswith(META_MAGIC):
        raise RuntimeError("meta.bin 格式不对（magic 不匹配）")
    p = len(META_MAGIC)
    (hlen,) = struct.unpack("<I", raw[p:p + 4])
    p += 4
    header = json.loads(raw[p:p + hlen].decode("utf-8"))
    base = p + hlen
    out = {}
    for name, spec in header.items():
        start = base + spec["offset"]
        blob = raw[start:start + spec["blob"]]
        off_start = start + spec["blob"]
        # 必须显式给 count：只给 offset 让它读到文件尾，长度不是 8 的倍数就报
        # `buffer size must be a multiple of element size`（实测踩到）。
        # 用 .copy() 让它脱离只读 bytes —— 后面的切片是纯读，但 copy
        # 也顺手把偏移表变成可写的普通数组，避免将来改字段时踩坑。
        off = np.frombuffer(raw, dtype=np.int64, count=spec["n"] + 1,
                            offset=off_start).copy()
        out[name] = _Packed(blob, off)
    return out


def _load_meta_legacy(path):
    """读旧的 meta.npz。只为兼容 —— 用户机器上已有的索引不必强制重建。"""
    m = np.load(path, allow_pickle=True)
    return {k: _Packed(*_pack_field(m[k])) for k in ("ids", "titles", "dates", "cats")}


def build(limit=0, log=print):
    t0 = time.time()
    ids, titles, dates, cats, docs = [], [], [], [], []
    for r in _iter_records():
        txt = _doc_text(r)
        if len(txt) < 80:
            continue
        ids.append(r["id"])
        titles.append(r.get("title") or "")
        dates.append(r.get("created") or "")
        cats.append(r.get("categories") or "")
        docs.append(txt)
        if limit and len(docs) >= limit:
            break
    log("读到 %d 篇，用时 %.1fs" % (len(docs), time.time() - t0))

    t1 = time.time()
    vec = TfidfVectorizer(
        stop_words="english", ngram_range=(1, 2), sublinear_tf=True,
        min_df=MIN_DF, max_features=MAX_FEATURES, dtype=np.float32,
    )
    X = vec.fit_transform(docs)
    log("TF-IDF 矩阵 %s，词表 %d，用时 %.1fs"
        % (X.shape, len(vec.vocabulary_), time.time() - t1))

    t2 = time.time()
    svd = TruncatedSVD(n_components=DIMS, random_state=0, algorithm="randomized")
    Z = svd.fit_transform(X).astype(np.float32)
    log("SVD %s，解释方差 %.3f，用时 %.1fs"
        % (Z.shape, svd.explained_variance_ratio_.sum(), time.time() - t2))

    n = np.linalg.norm(Z, axis=1, keepdims=True)
    n[n == 0] = 1.0
    Z = (Z / n).astype(np.float16)

    OUT.mkdir(parents=True, exist_ok=True)
    np.save(OUT / "emb.npy", Z)
    # 新格式：定长+堆打包。旧 meta.npz 不再写，但 load() 仍能读它
    _save_meta(OUT / META_FILE,
               {"ids": ids, "titles": titles, "dates": dates, "cats": cats})
    log("meta.bin %.1f MB（旧 meta.npz 会是 %.1f MB）"
        % ((OUT / META_FILE).stat().st_size / 1048576,
           (len(ids) * (16 + 250 + 10 + 131) * 4) / 1048576))
    with open(OUT / "tfidf.pkl", "wb") as f:
        pickle.dump(vec, f, protocol=4)
    with open(OUT / "svd.pkl", "wb") as f:
        pickle.dump(svd, f, protocol=4)
    info = {
        "built": time.strftime("%Y-%m-%d %H:%M:%S"),
        "docs": len(ids), "dims": DIMS, "vocab": len(vec.vocabulary_),
        "explained": float(svd.explained_variance_ratio_.sum()),
        "seconds": round(time.time() - t0, 1),
    }
    with open(OUT / "index.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    log("完成：%s" % json.dumps(info, ensure_ascii=False))
    return info


_CACHE = {}


def load(log=None):
    if _CACHE:
        return _CACHE
    meta_bin = OUT / META_FILE
    meta_legacy = OUT / "meta.npz"
    for name, path in (("emb", OUT / "emb.npy"), ("tfidf", OUT / "tfidf.pkl"),
                       ("svd", OUT / "svd.pkl")):
        if not path.exists():
            raise RuntimeError("索引不完整，缺 %s（先跑 --build）" % path)
    if not meta_bin.exists() and not meta_legacy.exists():
        raise RuntimeError("索引不完整，缺 %s（先跑 --build）" % meta_bin)
    t0 = time.time()
    # mmap 而不是整块读入：搜索里 `E @ zv` 会分块，没必要把 184 MB 全驻留；
    # 而且旧的 `astype(float32)` 每次要临时分配 387 MB，纯属浪费。
    _CACHE["emb"] = np.load(OUT / "emb.npy", mmap_mode="r")
    if meta_bin.exists():
        m = _load_meta(meta_bin)
        _CACHE["meta_format"] = "bin"
    else:
        # 兼容：用户机器上可能还是旧索引。读一次缩成打包格式放进内存，
        # 下次 --build 就会写成 meta.bin。
        m = _load_meta_legacy(meta_legacy)
        _CACHE["meta_format"] = "npz-legacy"
    _CACHE["ids"] = m["ids"]
    _CACHE["titles"] = m["titles"]
    _CACHE["dates"] = m["dates"]
    _CACHE["cats"] = m["cats"]
    with open(OUT / "tfidf.pkl", "rb") as f:
        _CACHE["tfidf"] = pickle.load(f)
    with open(OUT / "svd.pkl", "rb") as f:
        _CACHE["svd"] = pickle.load(f)
    if log:
        log("索引载入 %.1fs，%d 篇" % (time.time() - t0, _CACHE["emb"].shape[0]))
    return _CACHE


def _emb():
    """嵌入矩阵的访问器。

    以前三处搜索都写 E = d["emb"].astype(np.float32) —— 每次搜索把
    184 MB float16 整块转成 387 MB float32，用完即弃。矩阵乘本身
    loat16 @ float32 会自动提升，结果精度与先转换再乘一致，
    但省掉了每轮几百 MB 的分配与释放。
    """
    return load()["emb"]


def _query_vec(q):
    d = load()
    en = to_english(q).lower()
    terms = [w for w in en.split() if w not in _STOP]
    # 未登录词缺失时退成二元组，尽量命中
    text = " ".join(terms) if terms else (q or "").lower()
    X = d["tfidf"].transform([text])
    if X.nnz == 0 and terms:
        X = d["tfidf"].transform([terms[0]])
    z = d["svd"].transform(X).astype(np.float32)[0]
    n = float(np.linalg.norm(z))
    if n <= 0:
        return np.zeros(Z_DIMS(), dtype=np.float32)
    return z / n


def Z_DIMS():
    return load()["emb"].shape[1]


# ---------------------------------------------------------------------------
# 分段查询
# ---------------------------------------------------------------------------
# 为什么不能整句翻成英文再查
# --------------------------
# 「红外小目标检测」按长词优先替换会先命中『目标检测』→ `object detection`，
# 『小目标』里的『小』被吃掉，只剩 `object detection infrared`。
# `object detection` 是大类词（全库几万篇），SVD 里它的载荷远大于 `infrared`，
# 结果排出来全是普通检测论文，红外这条线完全丢了。
#
# 正确做法：按『修饰在前、中心词在后』切段，每段单独取向量，再按段的特异性加权合并。
# `infrared` / `small target` 这种词 idf 高（6.9 / 8.7），`object detection` 只有 5.5，
# 天然就该权重不同 —— 用 tfidf 词频模拟「这段话里出现多少次才算命中」。

# 中心词（段尾）：这类词是「大品类」，权重最低
_HEAD_CN = ("检测", "分割", "识别", "跟踪", "分类", "重建", "融合", "估计",
            "生成", "检索", "匹配", "配准", "定位", "预测", "增强", "去噪")
# 修饰词（段头）：领域、模态、约束，区分度最高
_MOD_CN = ("红外", "可见光", "热成像", "多光谱", "高光谱", "遥感", "医学", "手术",
           "工业", "无人机", "卫星", "SAR", "雷达", "点云", "深度", "事件相机",
           "小目标", "微小", "遮挡", "低照度", "弱光", "低光", "夜间", "水下", "内窥镜",
           "去雾", "去雨", "去雪", "去噪", "去模糊", "去反射")
# 方法词：插在中间的技法名
_METHOD_CN = ("对比学习", "自监督", "半监督", "无监督", "扩散模型", "扩散",
              "Transformer", "Mamba", "状态空间", "知识蒸馏", "蒸馏", "量化",
              "剪枝", "轻量化", "注意力", "图神经网络", "强化学习", "元学习",
              "开放词汇", "零样本", "少样本", "小样本", "多模态", "跨模态", "提示学习")
# 抽象任务词：既不是大品类也不是强区分度，权重居中
_TASK_CN = ("去雾", "超分辨率", "显著性", "抠图", "计数", "姿态", "深度估计",
            "图像质量", "异常", "缺陷", "outlier", "对抗")

_W_HEAD = 0.55
_W_MOD = 1.6
_W_METHOD = 1.3
_W_TASK = 1.0

# 单段英文词 → 经验上更好检索的短语
# `low light` 单独查会撞上 low-rank；加上 image 才能锚定到成像领域
_SEG_FIX = {
    "low light": "low-light image",
    "low_light": "low-light image",
    "lowlight": "low-light image",
    "dehazing": "dehazing",
    "dark": "low-light image",
    "night": "nighttime image",
    "detection": "object detection",
    "segmentation": "image segmentation",
    "enhancement": "image enhancement",
    "restoration": "image restoration",
    # 单写 infrared 时，向量会被"普通 RGB 检测"拉走；加 shot 相关词把它钉在红外成像上
    "infrared": "infrared thermal",
}


# 段内同义扩展：把区分度最高的那一段扩成同义词并集，再取平均向量。
# 原因：`small object` 在库里多半指 RGB 小目标，「红外小目标」在论文里常写成
# `infrared small target` / `dim small target`。只用一个词会漏掉后两种写法。
_SYN = {
    "small object": ["small target", "tiny object", "dim small target"],
    "infrared thermal": ["thermal infrared", "long-wave infrared", "infrared image"],
    "dehazing": ["haze removal", "hazy image", "atmospheric scattering"],
    "low-light image": ["low-light enhancement", "dark image", "illumination enhancement"],
    "event camera": ["event-based camera", "neuromorphic camera", "event sensor"],
    "image fusion": ["multi-modal fusion", "infrared and visible fusion"],
    "point cloud": ["point cloud segmentation", "3d point cloud"],
}


def _fix_seg(en):
    return _SEG_FIX.get(en.strip().lower(), en)


def _seg_vec_expanded(en, w):
    """段向量 = 该短语与同义扩展的**并集**。

    不能用平均（上一轮的错误）：把 infrared 平均成
    (thermal infrared + long-wave infrared + infrared image)/3 之后，
    向量长度降到 1/√3，权重 1.6 被摊薄，[红外小目标检测] 从 3/5 掉到 1/5。
    并集取「逐维最大值」可以保留每一个变体的强向量的同时不稀释，
    再用相位对齐（谁和主词的余弦为负就翻转）避免不同说法的符号冲突。
    """
    base = _seg_vec(_fix_seg(en))
    if base is None:
        return None
    syns = _SYN.get(_fix_seg(en), [])
    if not syns:
        return base
    acc = base.copy()
    for t in syns:
        vb = _seg_vec(_fix_seg(t))
        if vb is None:
            continue
        if float(base @ vb) < 0:
            vb = -vb
        acc = np.maximum(acc, vb)
    n = float(np.linalg.norm(acc))
    return acc / n if n > 0 else base


def split_cn(q):
    """把中文方向名切成 [(中文段, 英文, 权重)]。长词优先吞掉，不重复匹配。"""
    s = q or ""
    segs = []

    def take(pool, weight):
        nonlocal s
        for term in sorted(pool, key=len, reverse=True):
            if term in s and term in _CN2EN:
                en = _CN2EN[term]
                en = en[0] if isinstance(en, (list, tuple)) else str(en)
                segs.append((term, en, weight))
                s = s.replace(term, " ")

    # 顺序：先修饰（含领域）、再方法、再中心、最后抽象任务
    take(_MOD_CN, _W_MOD)
    take(_METHOD_CN, _W_METHOD)
    take(_HEAD_CN, _W_HEAD)
    take(_TASK_CN, _W_TASK)
    # 剩余中文逐字过一遍 CN2EN（罕见方向名，比如「量子机器学习」）
    for cn in sorted(_CN2EN, key=len, reverse=True):
        if cn in s and len(s) >= 2:
            en = _CN2EN[cn]
            en = en[0] if isinstance(en, (list, tuple)) else str(en)
            segs.append((cn, en, 1.0))
            s = s.replace(cn, " ")
    rest_en = re.sub(r"[^\x00-\x7f]+", " ", s).strip()
    if rest_en:
        segs.append((rest_en, rest_en, 1.0))
    return [x for x in segs if x[1]]


def _seg_vec(text):
    """单段英文 → 归一化 180 维。命中不到词表时返回 None。"""
    d = load()
    X = d["tfidf"].transform([text.lower()])
    if X.nnz == 0:
        return None
    z = d["svd"].transform(X).astype(np.float32)[0]
    n = float(np.linalg.norm(z))
    if n <= 0:
        return None
    return z / n


def _query_vec(q):
    """加权合并各段向量。返回 (向量, 分段说明)。

    第二轮（本轮）修正：加了「必需词」判定。
    首轮把每段各自投影后加权相加，结果「小目标」的向量把「红外」稀释掉了 ——
    [红外小目标检测] Top5 只有 3 篇沾红外，[图像去雾] 0 篇、
    [弱光图像增强] 0 篇，原因是 `dehazing`/`low-light` 单独投影后向量很「中性」。
    改法：先求全体段的合成向量，再对**区分度高的段**（权重 ≥ _REQ_W）做一次余弦门控，
    不含该段的文档直接扣分。这不改变排序主体，只是把明显跑题的打下去。
    """
    d = load()
    segs = split_cn(q)
    if not segs:
        vb = _seg_vec(to_english(q) or q)
        return (vb if vb is not None else np.zeros(Z_DIMS(), np.float32)), []

    acc = np.zeros(Z_DIMS(), dtype=np.float32)
    used = []
    part = []
    for cn, en, w in segs:
        vb = _seg_vec_expanded(en, w)
        if vb is None:
            continue
        acc += w * vb
        used.append({"cn": cn, "en": en, "w": w})
        if w >= _REQ_W:
            part.append((cn, vb))
    n = float(np.linalg.norm(acc))
    if n > 0:
        acc = acc / n

    # 记录必需段，供 search() 做门控
    _query_vec.last_required = part
    _query_vec.last_parts = [vb for _, vb in part]
    return acc, used


_REQ_W = 1.5          # 权重达到这个值的段视为「必需」（领域/模态词）
_REQ_FLOOR = 0.35     # 起始门槛，search() 里按每次查询自适应上调
_REQ_TOP_N = 3        # 拿合成向量的前 N 篇去校准「什么叫命中这个领域」


def search(q, k=10):
    d = load()
    zv, used = _query_vec(q)
    req = getattr(_query_vec, "last_required", [])
    E = _emb()
    scores = E @ zv
    if req:
        # 取候选池（k 的 20 倍），对跑题的做惩罚后再排序
        pool_n = min(max(k * 20, 400), len(scores))
        pool = np.argpartition(-scores, pool_n - 1)[:pool_n]
        # 门槛用「过约束」校准：**所有**必需段同时命中的向量。
        # 原因：单段门槛持续低估 —— `dehazing` 向量只有 0.659（连自己家最好的论文都不高），
        # 拿它当标尺，去噪论文能轻易混过去。用交集向量，真命中才高、跑题才低，区分度大得多。
        # 门槛取交集里最好的那一篇的 70%，并留 0.30 下限防全库都没有时误杀。
        comb = None
        for vb in _query_vec.last_parts:
            co = E[pool] @ vb
            comb = co if comb is None else np.minimum(comb, co)
        pen = np.ones(len(pool), dtype=np.float32)
        if comb is not None:
            floor = max(0.30, float(np.max(comb)) * 0.70)
            pen = np.where(comb < floor, 0.35, 1.0)
        scores = scores.copy()
        scores[pool] = scores[pool] * pen
    idx = np.argpartition(-scores, min(k * 5, len(scores) - 1))[:max(k * 5, k)]
    idx = idx[np.argsort(-scores[idx])][:k]
    out = []
    for i in idx:
        out.append({
            "id": str(d["ids"][i]),
            "title": str(d["titles"][i]),
            "date": str(d["dates"][i]),
            "cats": str(d["cats"][i]),
            "score": round(float(scores[i]), 4),
            "url": "https://arxiv.org/abs/" + str(d["ids"][i]),
        })
    return out


def explain(q):
    """给界面用：这条查询被拆成了什么。"""
    return _query_vec(q)[1]


# ---------------------------------------------------------------------------
# 多关键词 AND 检索
# ---------------------------------------------------------------------------
# 用户要的能力：「红外 + 小目标 + 检测」这种词与词的组合，光靠向量相加不够 ——
# 相加是「这些词整体像谁」，会漏掉「同时包含这三个词」的论文。
# 所以补一层显式的交集过滤：每个关键词必须真实出现在标题或摘要里。
# 这是 Wikipedia/矢量库之外的传统做法，但对「查重/查空白」比纯向量更可靠。


BODIES_CACHE = OUT / "bodies.z"


def _load_bodies_fast():
    """从 bodies.z 一次读出全部正文；失败返回 None。

    2026-11-15 加：原来每次新进程都要把 157 个 jsonl（825MB）
    逐行 json.loads 一遍，实测 6.68 秒 —— 新颖性核查一点就卡这么久。
    现在先试压缩缓存（解压 + split 约 3.2 秒），没有或对不上号再退回原来的路。
    缓存由 build_bodies_cache.py 生成，源数据变了会按签名自动重建。
    """
    import zlib
    try:
        if not BODIES_CACHE.exists():
            return None
        with open(BODIES_CACHE, "rb") as fh:
            head = json.loads(fh.readline().decode("utf-8"))
            comp = fh.read()
        raw = zlib.decompress(comp).decode("utf-8")
        rows = raw.split("\n")
        if len(rows) != int(head.get("n") or -1):
            return None
        d = load()
        # 缓存里每行是「id\t正文」。按 load() 的 ids 顺序对回去：
        # 向量索引和正文必须一一对齐，错一位「像不像」就全废。
        cell = {}
        for r in rows:
            parts = r.split("\t", 1)
            if len(parts) == 2:
                cell[parts[0]] = parts[1]
        bodies = [cell.get(str(i), "") for i in d["ids"]]
        return bodies
    except Exception as exc:
        print("bodies 缓存不可用，退回逐文件读取：", exc)
        return None


def load_bodies():
    """懒加载全部标题+摘要正文（约 700MB 内存），供 AND 过滤用。"""
    import glob
    if "bodies" in _CACHE:
        return _CACHE["bodies"]
    fast = _load_bodies_fast()
    if fast is not None:
        _CACHE["bodies"] = fast
        return fast
    d = load()
    id_map = {str(x): i for i, x in enumerate(d["ids"])}
    bodies = [""] * len(d["ids"])
    for f in sorted(glob.glob(str(SRC / "*.jsonl"))):
        with open(f, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                i = id_map.get(str(r.get("id")))
                if i is None:
                    continue
                bodies[i] = ((r.get("title") or "") + " " + (r.get("abstract") or "")).lower()
    _CACHE["bodies"] = bodies
    return bodies


def _as_terms(terms):
    """把用户的词（中或英）统一翻成英文检索词列表。

    支持排除词：`-xxx` / `-xxx+yyy` / `-+xxx`。排除词不在这里处理，
    由 `parse_terms()` 先拆走，传进来的 terms 里已经不含排除部分。
    """
    if isinstance(terms, str):
        terms = [t for t in re.split(r"[,，;；\s]+", terms) if t]
    out = []
    for t in terms:
        t = (t or "").strip()
        if not t:
            continue
        segs = split_cn(t)
        if segs:
            out.extend([s[1] for s in segs])
        else:
            en = to_english(t) or t
            for w in re.split(r"\s+", en.strip()):
                if w:
                    out.append(w)
    seen = []
    for t in out:
        if t.lower() not in [x.lower() for x in seen]:
            seen.append(t)
    return seen


_TERM_SPLIT = re.compile(r"[,，;；\s]+")


def _split_plus(s):
    """`a+b+c` 这种「同时命中」写法拆成多个词；普通词原样返回。"""
    s = (s or "").strip()
    if not s:
        return []
    parts = [x.strip() for x in s.split("+") if x.strip()]
    return parts or [s]


def parse_terms(terms):
    """把用户输入拆成 (必须有, 必须没有)。

    语法（很小，够用就行，不搞完整查询语言）：
        a b            两个词都要出现
        a, b           同上（中英文逗号都行）
        a+b            同上（「红外+小目标」这种连写）
        -x             不要出现 x
        -x+y           不要出现 x，也不要出现 y
        -+x            同上（习惯把加号写在前面）

    为什么需要排除词：实测「去雾 + 图像」Top10 只有 6 条真讲去雾，
    其余是通用图像恢复（diffusion / restoration 占了位）；
    「小样本 + 检测」掺进了大量 anomaly detection。
    用户加一个 `-anomaly` 就能清掉，比我们猜语料更有用。
    """
    if isinstance(terms, str):
        raw = _TERM_SPLIT.split(terms)
    else:
        raw = []
        for t in terms:
            raw.extend(_TERM_SPLIT.split(str(t or "")))
    pos, neg = [], []
    for tok in raw:
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("-"):
            body = tok[1:].lstrip("+")
            neg.extend(_split_plus(body))
        else:
            pos.extend(_split_plus(tok))
    # 排除词如果和必须有词是同一个（含同义），以「必须有」为准，否则必然空结果
    pos_set = set(p.lower() for p in pos)
    neg = [x for x in neg if x.lower() not in pos_set]
    return pos, neg


# 领域词的同义写法组：AND 检索时「任一同义写法命中即算这个词命中」。
# 为什么必须有：53.8 万篇里同时写 infrared 和 small object 的只有 18 篇 ——
# 真论文用的是 thermal / LWIR / dim small target / IRSTD 这些写法。
# 只按一个写法做 AND，等于把大半个领域排除在外。
_SYN_GROUP = {
    "infrared": ["infrared", "thermal", "lwir", "long-wave infrared", "ir image", "ir imaging"],
    "small object": ["small object", "small target", "dim small target",
                     "tiny object", "tiny target", "small-scale"],
    "dehazing": ["dehazing", "dehaze", "haze removal", "hazy", "atmospheric scattering"],
    "low-light": ["low-light", "low light", "lowlight", "dark image", "nighttime"],
    "event camera": ["event camera", "event-based camera", "event sensor",
                     "neuromorphic camera", "event stream"],
    "point cloud": ["point cloud", "pointcloud", "lidar", "3d point"],
    "medical imaging": ["medical image", "medical imaging", "clinical", "radiology",
                        "ct ", "mri", "pathology"],
    # 这两组必须窄。实测：lightweight 组加进 efficient/real-time/mobile/flops 后，
    # 「轻量化+检测」交集从 2,981 篇暴涨到 16,667 篇，Top10 相关度从 7/10 掉到 1/10，
    # 因为这几词在每个检测论文里都有。同理 few-shot 加 meta-learning 会掺进异常检测。
    "lightweight": ["lightweight", "light-weight", "low computational cost"],
    "few-shot": ["few-shot", "few shot", "low-shot", "few-sample", "few sample"],
    "self-supervised": ["self-supervised", "self supervised", "contrastive",
                        "unsupervised pretraining"],
    "diffusion model": ["diffusion model", "diffusion-based", "ddpm", "score-based"],
    "detection": ["detection", "detector", "detect"],
    "segmentation": ["segmentation", "segment", "mask"],
    "fusion": ["fusion", "fuse", "fused"],
    "generation": ["generation", "generative", "synthesis"],
    "tracking": ["tracking", "tracker", "track"],
    "image": ["image", "imagery", "visual"],
}


def _group_of(term):
    """给一个英文词找它的同义组；找不到就返回 [自身]。"""
    t = term.strip().lower()
    for head, group in _SYN_GROUP.items():
        if t == head or t in group:
            return group
    return [t]


def _density(body, groups):
    """交集词在该篇里的密度：出现总次数 / 长度（每千字符）。"""
    n = 0
    for g in groups:
        n += sum(body.count(x) for x in g)
    return n / (1.0 + len(body) / 1000.0)


# 预筛池缓存。同一批候选用的是同一个方向 hint，`count_and` 每次都要
# 重新做一次 tfidf→svd→全库打分，单次 6 秒；六条候选就是三十六秒。
# 缓存 (hint, pool) → 下标数组，第二次起直接复用。
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _has_cjk(s):
    return bool(_CJK_RE.search(s or ""))


_POOL_CACHE = {}


def _prescreen(hint, pool):
    """按 hint 取相似度最高的 pool 篇下标；失败返回 None（调用方退回全量）。"""
    key = (hint, pool)
    if key in _POOL_CACHE:
        return _POOL_CACHE[key]
    try:
        # hint 常常是中文（「红外小目标检测」），`_seg_vec` 走的是英文
        # tf-idf 词表，直接喂中文 nnz=0 返回 None —— 那样就会静默退化成
        # 全量扫描，每次 2.2 秒。必须先过分段/翻译，再算向量。
        zv = None
        if _has_cjk(hint):
            zv, _parts = _query_vec(hint)
        else:
            zv = _seg_vec(hint)
        if zv is None:
            return None
        d = load()
        E = _emb()
        sc = E @ zv
        n = min(pool, len(sc))
        cand = np.argpartition(-sc, n - 1)[:n]
        cand = cand[np.argsort(-sc[cand])]
    except Exception:
        return None
    # 只留最近 4 个 hint 的池，别让字典无限涨（每个池 6 万 int32 ≈ 240KB）
    if len(_POOL_CACHE) > 4:
        _POOL_CACHE.clear()
    _POOL_CACHE[key] = cand
    return cand


_ZIB_CACHE = {}


def _count_and_bytes(groups, cand):
    """在压缩缓存上做字节级 AND 计数；缓存不可用返回 None。"""
    try:
        import zlib
        if not BODIES_CACHE.exists():
            return None
        st = os.stat(BODIES_CACHE)
        key = (st.st_size, int(st.st_mtime))
        ent = _ZIB_CACHE.get(key)
        if ent is None:
            with open(BODIES_CACHE, "rb") as fh:
                head = json.loads(fh.readline().decode("utf-8"))
                comp = fh.read()
            body_off = len(json.dumps(head).encode("utf-8")) + 1
            starts = [0]
            total = 0
            CH = 1 << 20
            while total < len(comp):
                piece = comp[total:total + CH]
                total += len(piece)
                d = zlib.decompressobj()
                d.decompress(piece)
                starts.append(total - len(d.unused_data))
            ent = (comp, body_off, starts)
            if len(_ZIB_CACHE) > 1:
                _ZIB_CACHE.clear()
            _ZIB_CACHE[key] = ent
        comp, body_off, starts = ent
        nblk = len(starts) - 1
        # 词必须是小写：缓存里的正文建的时候就 .lower() 过
        pats = [tuple(x.encode("utf-8") for x in g) for g in groups]
        if not pats:
            return None
        hit = 0
        for i in cand:
            i = int(i)
            blk = min(i * 8 // 10000, nblk - 1)
            a = body_off + starts[blk]
            try:
                raw = zlib.decompress(comp[a:body_off + starts[blk + 1]])
            except Exception:
                return None
            ok = True
            for pset in pats:
                if not any(p in raw for p in pset):
                    ok = False
                    break
            if ok:
                hit += 1
        return hit
    except Exception:
        return None


def count_and(terms, vec_hint=None, pool=60000):
    """只要命中篇数，不要排序结果 —— 快得多。

    为什么不直接用 `search_and(terms, k=1)["count"]`：那条路会先把
    53.8 万篇正文全扫一遍做交集，单次 4–5 秒；新颖性核查一条候选要跑
    两次（分子一次、分母一次），九条候选就是一分多钟，用户等不了。

    这里先用向量预筛：用 `vec_hint` 的向量取相似度最高的 `pool` 篇，
    只在这个子集上做 AND 计数。代价是「极不相似的漏网」，但新颖性核查
    问的本来就是「像不像」，不像的东西漏掉不影响结论；
    而且 pool 默认 6 万篇，占比 11%，对占比类判断足够。

    `vec_hint` 为空时退回全量扫描（正确但慢）。
    """
    pos, _neg = parse_terms(terms)
    need = _as_terms(pos)
    if not need:
        return 0
    groups = [_group_of(t) for t in need]
    groups = [g for g in groups if g]
    if not groups:
        return 0
    # ── 免解压直扫（2026-11-15 加）──
    # 计数只需要「这篇论文里有没有这几个词」，不需要正文本身。
    # 所以直接扫压缩缓存的 bytes：每篇在压缩流里的字节区间是固定的，
    # 只要「解压这段区间的全部字节」必然包含这篇的全部字节，
    # 就在这段上做字节匹配 —— 结论和逐篇解压完全一致，但没命中就跳过，
    # 比把 700MB 正文全解压成字符串快一倍多。
    cand = _prescreen(vec_hint, pool) if vec_hint else None
    if cand is not None:
        got = _count_and_bytes(groups, cand)
        if got is not None:
            return got

    bodies = load_bodies()
    if cand is None:
        cand = range(len(bodies))
    # 每组先挑出最长的词：in 判断的开销和模式长度正相关，
    # 长词更容易不命中，先试它能让大多数论文在第一次就短路。
    lead = [max(g, key=len) for g in groups]
    full = [tuple(g) for g in groups]
    hit = 0
    for i in cand:
        b = bodies[int(i)]
        if not b:
            continue
        ok = True
        for k in range(len(lead)):
            if lead[k] not in b and not any(x in b for x in full[k]):
                ok = False
                break
        if ok:
            hit += 1
    return hit


def search_and(terms, k=20, vec_terms=None):
    """多关键词交集检索（支持排除词）。

    terms     : 必须全部出现的词（中英文都行，会自动翻译成同义组）；
                `-词` 表示必须不出现
    vec_terms : 用于向量排序的词，默认就用 terms
    返回 dict：{"terms", "groups", "negatives", "count", "count_before_exclude", "papers"}

    每个词展开成一个同义组：**组内任一写法命中即算命中**，组间是 AND。
    """
    d = load()
    pos, neg = parse_terms(terms)
    need = _as_terms(pos)
    if not need:
        return {"terms": [], "groups": [], "negatives": [], "count": 0,
                "count_before_exclude": 0, "papers": []}
    neg_en = _as_terms(neg) if neg else []
    bodies = load_bodies()

    # 1) 交集过滤：同义组内 OR，组间 AND；排除组内任一命中即淘汰
    groups = [_group_of(t) for t in need]
    groups = [g for g in groups if g]
    # 排除词不加同义组，但要展开自己的常见派生写法，否则 `-anomaly` 挡不住 anomalies
    neg_groups = [[t, t + "s", t + "ies"] if t.endswith("y") else [t, t + "s"]
                  for t in neg_en]
    import array
    keep = array.array("i")
    before = 0
    for i, b in enumerate(bodies):
        if not b:
            continue
        ok = True
        for g in groups:
            if not any(x in b for x in g):
                ok = False
                break
        if not ok:
            continue
        before += 1
        if neg_groups and any(any(x in b for x in g) for g in neg_groups):
            continue
        keep.append(i)
    if not keep:
        return {"terms": need, "groups": groups, "negatives": neg_en,
                "count": 0, "count_before_exclude": before, "papers": []}

    # 2) 排序：向量相关性 × 词密度
    # 只用向量不行：180 维 SVD 把「轻量化」压成了「检测类通用词」，
    # 排出来 10 条里 1 条真讲轻量化。密度（交集词出现次数/长度）能纠正它，
    # 但也偏爱关键词堆砌的长摘要 —— 两者相乘，谁也压不死谁。
    vq = " ".join(vec_terms if vec_terms else need)
    zv = _query_vec(vq)[0]
    E = _emb()
    idx = np.array(list(keep), dtype=np.int64)
    sc = E[idx] @ zv
    dens = np.array([_density(bodies[int(i)], groups) for i in idx], dtype=np.float32)
    if dens.size and dens.max() > 0:
        dens = dens / dens.max()
    final = sc * (0.5 + 0.5 * dens)
    order = idx[np.argsort(-final)][:k]
    smap = {int(i): float(s) for i, s in zip(idx, final)}
    out = []
    for i in order:
        out.append({
            "id": str(d["ids"][i]),
            "title": str(d["titles"][i]),
            "date": str(d["dates"][i]),
            "cats": str(d["cats"][i]),
            "score": round(smap.get(int(i), 0.0), 4),
            "url": "https://arxiv.org/abs/" + str(d["ids"][i]),
        })
    return {"terms": need, "groups": groups, "negatives": neg_en,
            "count": len(keep), "count_before_exclude": before, "papers": out}


def stats():
    p = OUT / "index.json"
    if not p.exists():
        return {"built": False}
    return json.loads(p.read_text(encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--search", default="")
    ap.add_argument("-k", type=int, default=10)
    args = ap.parse_args(argv)
    if args.build:
        build(limit=args.limit)
    if args.search:
        for p in search(args.search, args.k):
            print("%.3f  %s  %s  %s" % (p["score"], p["date"], p["cats"][:28], p["title"][:90]))
    if not args.build and not args.search:
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())