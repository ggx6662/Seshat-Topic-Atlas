"""按研究方向抓 arXiv 最新论文，喂给选题工坊与创新点库。

为什么单独做，不复用 kbscan：
    kbscan 是「定时抓完整 PDF 入库」的批处理，一次要下几篇到几百篇，
    有下载队列、去重、落盘。这里要的是「看个大概」——只要标题、摘要、
    作者、链接，30 篇一批，秒级返回，不落 PDF。

    arXiv 官方要求请求间隔 >= 3 秒，所以这里做了节流 + 本地缓存：
    同一方向 6 小时内不重复请求，用户反复点也不会打爆。

中文方向名的处理：
    arXiv 里没有中文，直接搜「红外小目标检测」得 0 条。所以要把中文
    方向名翻成英文检索式：
        ① 先用本地 CN2EN 词表（零延迟、离线可用）
        ② 若用户在设置里配了大模型，可以让模型改写检索式（更准）
"""
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "arxiv_latest_cache.json")
ARXIV_API = "https://export.arxiv.org/api/query"

_lock = threading.Lock()
_last_req = [0.0]
MIN_INTERVAL = 3.2          # arXiv 官方建议 >= 3 秒
CACHE_TTL = 6 * 3600        # 6 小时

# ── 中文方向名 → 英文检索式（本地兜底，离线可用）──
# 顺序无关：to_english 按 key 长度从长到短匹配，所以「目标检测」会先于「检测」。
# 要注意的坑：如果「语义分割」和「分割」都在表里，长词优先，这是对的；
# 但如果只有「分割」，「语义」会被丢掉——所以复合词尽量都列全。
CN2EN = {
    # 视觉任务
    "红外": "infrared", "热红外": "thermal infrared", "可见光": "visible",
    "小目标": "small object", "小物体": "small object", "微小目标": "tiny object",
    "目标检测": "object detection", "检测": "detection", "识别": "recognition",
    "语义分割": "semantic segmentation", "实例分割": "instance segmentation",
    "全景分割": "panoptic segmentation", "分割": "segmentation",
    "多目标跟踪": "multi-object tracking", "目标跟踪": "visual tracking",
    "跟踪": "tracking", "姿态估计": "pose estimation", "人体姿态": "human pose",
    "深度估计": "depth estimation", "单目深度": "monocular depth",
    "立体匹配": "stereo matching", "三维重建": "3d reconstruction",
    "点云": "point cloud", "SLAM": "SLAM", "超分辨率": "super-resolution",
    "超分": "super-resolution", "去噪": "denoising", "去雾": "dehazing",
    "去雨": "deraining", "增强": "enhancement", "融合": "fusion",
    "计数": "counting", "抠图": "matting", "修复": "inpainting",
    "生成": "generation", "编辑": "editing", "渲染": "rendering",
    "重识别": "re-identification", "ReID": "re-identification", "行人": "pedestrian",
    "人脸": "face", "表情": "expression", "视线": "gaze", "手势": "hand gesture",
    "动作识别": "action recognition", "行为识别": "action recognition",
    "时序动作": "temporal action", "视频理解": "video understanding",
    "视频生成": "video generation", "动作": "action",
    # 模态
    "多模态": "multimodal", "跨模态": "cross-modal", "跨域": "cross-domain",
    "融合多模态": "multimodal fusion", "文本": "text", "语言": "language",
    "语音": "speech", "音频": "audio", "三维": "3d", "深度图": "depth map",
    "RGBD": "RGB-D", "激光雷达": "LiDAR", "毫米波": "millimeter wave",
    "雷达": "radar", "高光谱": "hyperspectral", "事件相机": "event camera",
    "脉冲相机": "spike camera", "单光子": "single photon", "偏振": "polarization",
    "合成孔径": "synthetic aperture", "内窥": "endoscopic",
    # 领域
    "遥感": "remote sensing", "医学图像": "medical imaging", "医学": "medical imaging",
    "医疗": "medical", "病理": "pathology", "内镜": "endoscopy", "CT": "CT", "MRI": "MRI",
    "超声": "ultrasound", "X光": "X-ray", "细胞": "cell", "显微": "microscopy",
    "卫星": "satellite", "航拍": "aerial", "无人机": "UAV", "地面": "ground",
    "农业": "agriculture", "工业": "industrial", "缺陷": "defect", "质检": "quality inspection",
    "电力": "power line", "建筑": "building", "交通": "traffic", "驾驶": "driving",
    "自动驾驶": "autonomous driving", "机器人": "robot", "抓取": "grasping",
    "导航": "navigation", "水下": "underwater", "安防": "surveillance",
    "人脸识": "face recognition", "行人重": "person re-identification",
    # 方法
    "对比学习": "contrastive learning", "自监督": "self-supervised",
    "半监督": "semi-supervised", "无监督": "unsupervised", "弱监督": "weakly supervised",
    "全监督": "fully supervised", "知识蒸馏": "knowledge distillation",
    "蒸馏": "distillation", "剪枝": "pruning", "量化": "quantization",
    "轻量化": "lightweight", "注意力": "attention", "Transformer": "transformer",
    "扩散模型": "diffusion model", "扩散": "diffusion",
    "生成对抗": "generative adversarial", "GAN": "GAN",
    "状态空间": "state space model", "Mamba": "mamba", "RNN": "recurrent",
    "图神经网络": "graph neural network", "GNN": "graph neural network",
    "大模型": "foundation model", "基础模型": "foundation model",
    "视觉语言": "vision-language", "VLM": "vision language model",
    "CLIP": "CLIP", "SAM": "segment anything", "提示学习": "prompt learning",
    "微调": "fine-tuning", "适配器": "adapter", "LoRA": "LoRA",
    "零样本": "zero-shot", "小样本": "few-shot", "少样本": "few-shot",
    "开放词汇": "open-vocabulary", "开放集": "open-set",
    "神经辐射场": "nerf", "NeRF": "nerf", "高斯泼溅": "gaussian splatting",
    "3DGS": "gaussian splatting", "隐式表示": "implicit representation",
    "物理信息": "physics-informed", "神经算子": "neural operator",
    "强化学习": "reinforcement learning", "模仿学习": "imitation learning",
    "联邦学习": "federated learning", "持续学习": "continual learning",
    "元学习": "meta-learning", "迁移学习": "transfer learning",
    "域适应": "domain adaptation", "泛化": "generalization",
    "多任务": "multi-task", "联合学习": "joint learning",
    "模型压缩": "model compression", "加速": "acceleration",
    "实时": "real-time", "高效": "efficient", "边缘": "edge device",
    "硬件": "hardware", "部署": "deployment", "推理": "inference",
    # 鲁棒/安全/评测
    "对抗攻击": "adversarial attack", "对抗样本": "adversarial example",
    "后门": "backdoor", "投毒": "poisoning", "鲁棒": "robust", "可解释": "interpretable",
    "不确定性": "uncertainty", "校准": "calibration", "公平": "fairness",
    "隐私": "privacy", "水印": "watermark", "版权": "copyright",
    "异常检测": "anomaly detection", "分布外": "out-of-distribution",
    "长尾": "long-tailed", "不平衡": "imbalanced",
    "评测": "benchmark", "基准": "benchmark", "数据集": "dataset",
    # 其他
    "数据增强": "data augmentation", "合成数据": "synthetic data",
    "标注": "annotation", "主动学习": "active learning",
    "视频": "video", "图像": "image", "视觉": "vision", "压缩": "compression",
    "编码": "coding", "检索": "retrieval", "推荐": "recommendation",
    "问答": "question answering", "对话": "dialogue", "推理链": "chain of thought",
    # 更泛的词放在最后（to_english 按长度排序，这里顺序不影响匹配，只是阅读方便）
    "机器学习": "machine learning", "深度学习": "deep learning",
    "神经网络": "neural network", "量子": "quantum", "量子计算": "quantum computing",
    "统计学习": "statistical learning", "优化": "optimization",
    "概率": "probabilistic", "贝叶斯": "Bayesian", "因果": "causal",
    "科学计算": "scientific computing", "物理": "physics",
    "时序": "time series", "时间序列": "time series", "预测": "forecasting",
    "音频识别": "audio recognition", "信号": "signal",
    "编码器": "encoder", "解码器": "decoder", "架构": "architecture",
    "数据集构建": "dataset construction", "工具": "tool",
    # ---- 第二轮补词（来源：53.8 万篇向量检索实测失败的方向，见 kb_vector 评估）----
    # 「弱光」原来查不到，因为整个词表只有「低照度」，而低照度也不在表里
    "弱光": "low-light", "低光": "low-light", "暗光": "low-light",
    "低照度": "low-light", "低光照": "low-light", "夜视": "night vision",
    "夜间": "nighttime", "黑夜": "nighttime",
    # 图像复原一组：原来只有「去雾」「去雨」，缺的都在这里
    "去雾霾": "haze removal", "去模糊": "deblurring",
    "去雪": "desnowing", "去反射": "reflection removal",
    "低光照增强": "low-light enhancement", "光照不均匀": "illumination",
    # 红外一组：只写 infrared 时排名会被普通检测论文挤掉
    "长波红外": "long-wave infrared",
    "近红外": "near-infrared",
    # 深度与三维
    "双目": "stereo", "立体视觉": "stereo vision",
    # 2026-11-15 由 tools_cold_terms.py 找出来的真实缺口。
    # 判断依据：用户在日志里反复搜这些词、结果为零，而论文里它们其实有固定写法。
    # 「热成像」不能翻成 imaging —— 那样会命中所有成像论文；必须带 thermal。
    "热成像": "thermal imaging", "红外成像": "infrared imaging",
    "光场": "light field", "光场相机": "light field camera",
    "偏振成像": "polarization imaging", "高动态": "high dynamic range",
    "结构光": "structured light", "ToF": "time-of-flight",
    "目标分割": "object segmentation", "实例跟踪": "instance tracking",
    "单目标跟踪": "single object tracking",
    "视频目标分割": "video object segmentation", "语义理解": "semantic understanding",
}

_ARXIV_CATS = ("cs.CV", "cs.LG", "cs.AI", "cs.RO", "cs.MM", "eess.IV", "cs.CL")

# 方法/任务类短语：出现时用 abs:"..." 精确短语匹配，比逐词 AND 更准。
# 例如「红外小目标检测」→ abs:"small object" AND abs:infrared，
# 而不是 abs:small AND abs:object AND abs:infrared（后者会命中 "small ... object" 的散装组合）。
_PHRASE = frozenset((
    "object detection", "small object", "small target", "medical imaging",
    "contrastive learning", "self-supervised", "semi-supervised",
    "weakly supervised", "knowledge distillation", "point cloud",
    "depth estimation", "monocular depth", "3d reconstruction",
    "super-resolution", "remote sensing", "anomaly detection",
    "diffusion model", "generative adversarial", "state space model",
    "graph neural network", "foundation model", "vision-language",
    "vision language model", "prompt learning", "domain adaptation",
    "action recognition", "re-identification", "person re-identification",
    "open-vocabulary", "adversarial attack", "reinforcement learning",
    "federated learning", "data augmentation", "synthetic data",
    "pose estimation", "edge device", "monocular depth estimation",
    "image fusion", "multi-modal", "small object detection",
    # 补上的：这些词拆成 abs:a AND abs:b 会招一堆噪音
    # （"machine AND learning" 会命中任何写了 machine 和 learning 的论文）
    "machine learning", "deep learning", "neural network", "neural networks",
    "semantic segmentation", "instance segmentation", "panoptic segmentation",
    "event camera", "event cameras", "thermal infrared", "quantum computing",
    "quantum machine learning", "time series", "causal inference",
    "vision transformer", "large language model", "large language models",
    "segment anything", "gaussian splatting", "implicit representation",
    "neural radiance field", "model compression", "long-tailed",
    "out-of-distribution", "multi-object tracking", "visual tracking",
    "human pose", "video understanding", "video generation",
    "image generation", "image restoration", "low-light",
    "adversarial example", "uncertainty estimation", "continual learning",
    "transfer learning", "active learning", "multi-task learning",
    "medical image", "medical images", "remote sensing image",
    "point clouds", "stereo matching", "hyperspectral image",
    "autonomous driving", "power line", "underwater image",
))


def to_english(direction):
    """把中文方向名转成英文检索词。

    先按长度从长到短匹配（「目标检测」优先于「检测」），
    剩余中文丢弃（arXiv 认不出），英文原词保留。
    """
    d = (direction or "").strip()
    if not d:
        return ""
    terms = []
    rest = d
    for cn in sorted(CN2EN, key=len, reverse=True):
        if cn in rest:
            terms.append(CN2EN[cn])
            rest = rest.replace(cn, " ")
    # 残留英文（图神经网络写的 GNN、用户直接输英文方向）
    for w in re.findall(r"[A-Za-z][A-Za-z0-9\-\+]{1,}", rest):
        terms.append(w)
    out = []
    for t in terms:
        if t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return " ".join(out)


def build_query(direction, extra="", loose=False):
    """组装 arXiv 检索式。

    踩过的坑：
    ① 最初用 `all:object AND all:detection AND all:infrared`，结果「红外小目标
       检测」返回一堆天文学论文——ultra-luminous infrared galaxies。因为
       all:infrared 命中了天体物理里的"红外"。修法：加 cat:cs.* 分类限定。
    ② `abs:"object detection" AND abs:detection` 自重复，arXiv 会大幅缩减结果。
       修法：短语覆盖的词不再单独出现。
    ③ loose 想做成"少一个条件"，但「红外小目标检测」本来就只有 2 个条件
       （领域词 + 任务词），截到 1 个就只剩 abs:infrared——fNIRS 脑成像、
       晶格场理论、卫星天气锋全进来了，因为只要正文写了 infrared 就中。
       结论：**2 条件的严格式已经是这个方向的最优解，loose 在这里没有意义**。
       真正有用的是时间窗（days_back），见 fetch()。

    查准比查全重要：用户要看的是"这个方向最近的 CS 论文"。
    """
    en = to_english(direction)
    if extra:
        en = (en + " " + extra).strip()
    if not en:
        return ""

    # 先按短语组切分，再去重
    parts = []
    words = en.split()
    i = 0
    while i < len(words):
        matched = None
        for n in (3, 2):
            cand = " ".join(words[i:i + n]).lower()
            if cand in _PHRASE:
                matched = cand
                break
        if matched:
            n = len(matched.split())
            parts.append(('phrase', matched))
            i += n
        else:
            parts.append(('word', words[i]))
            i += 1

    covered = set()
    for kind, val in parts:
        if kind == "phrase":
            covered.update(val.split())
    conds = []
    for kind, val in parts:
        if kind == "phrase":
            conds.append(('phrase', val, 'abs:"%s"' % val))
        elif val.lower() not in covered:
            conds.append(('word', val, "abs:%s" % val))
    if not conds:
        return ""
    if loose:
        # 真正的"放宽"= 领域词必须中 + 通用词任选其一。
        # 直接砍条件会退化成"只要写了 infrared 就算"，实测 fNIRS/晶格场理论全进来。
        dom = [c for c in conds if _is_domain_term(c[1])]
        gen = [c for c in conds if not _is_domain_term(c[1])]
        pieces = [c[2] for c in dom[:2]]
        if gen:
            pieces.append("(%s)" % " OR ".join(c[2] for c in gen[:3]))
        if not pieces:
            pieces = [c[2] for c in conds[:1]]
        field = " AND ".join(pieces)
    else:
        field = " AND ".join(c[2] for c in conds[:4])
    cats = " OR ".join("cat:" + c for c in _ARXIV_CATS)
    return "(%s) AND (%s)" % (field, cats)


def _fallback_query(direction):
    """严格式一篇都没中时的兜底：保留领域词，去掉任务词。

    场景：「事件相机语义分割」这种细分方向 arXiv 上可能一个月没人写，
    严格式返回 0 篇。退成只搜领域词，至少能看到这个领域的脉动。

    踩过的坑：最初用 `[w for w in en.split() if w not in _GENERIC_TERMS]`，
    结果「事件相机语义分割」的英文是 "event camera semantic segmentation"，
    只有 event/camera 留下，拼成 abs:event OR abs:camera，召回一堆无关的
    ——所以宁可保留全部词，用 OR 连起来。OR 召回宽但至少不离题。
    """
    en = to_english(direction)
    if not en:
        return ""
    toks = [w for w in en.split() if len(w) > 1]
    if not toks:
        return ""
    # 短语优先（"event camera" 比 "event" OR "camera" 精确得多）
    phrases = []
    i = 0
    while i < len(toks):
        hit = None
        for n in (3, 2):
            if i + n <= len(toks) and " ".join(toks[i:i + n]).lower() in _PHRASE:
                hit = " ".join(toks[i:i + n]).lower()
                break
        if hit:
            phrases.append('abs:"%s"' % hit)
            i += len(hit.split())
        else:
            phrases.append("abs:%s" % toks[i])
            i += 1
    dom = " OR ".join(phrases[:3])
    cats = " OR ".join("cat:" + c for c in _ARXIV_CATS)
    return "((%s)) AND (%s)" % (dom, cats)


# 方法/任务类词：宽松检索时优先丢弃，因为它们太泛（object detection 有几十万篇）
_GENERIC_TERMS = frozenset((
    "object detection", "detection", "recognition", "segmentation", "classification",
    "tracking", "estimation", "learning", "model", "modeling", "network", "networks",
    "framework", "method", "approach", "algorithm", "transformer", "transformer-based",
    "attention", "benchmark", "dataset", "training",
))


def _is_domain_term(term):
    """领域词（红外/医学/遥感/小目标…）判断：不在通用词表里就算领域词。
    宁可多保留，因为丢掉领域词比多一个条件更伤相关性。"""
    return term.lower() not in _GENERIC_TERMS


def _throttle():
    with _lock:
        now = time.time()
        wait = MIN_INTERVAL - (now - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


def _parse_xml(xml):
    """解析 arXiv Atom 返回。用正则而不是 xml.etree —— Atom 里有命名空间，
    ElementTree 处理起来更啰嗦，这里字段固定、结构简单。"""
    out = []
    for block in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        def g(tag):
            m = re.search(r"<%s[^>]*>(.*?)</%s>" % (tag, tag), block, re.S)
            return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        title = g("title")
        if not title:
            continue
        summary = g("summary")
        authors = [a.strip() for a in re.findall(r"<name>(.*?)</name>", block)]
        pub = g("published")[:10]
        aid = g("id")
        # http://arxiv.org/abs/2512.12345v1 → 2512.12345
        m = re.search(r"abs/([0-9]+\.[0-9]+)", aid)
        code = m.group(1) if m else ""
        cats = re.findall(r'<category term="([^"]+)"', block)
        out.append({
            "title": title,
            "abstract": summary,
            "authors": authors,
            "published": pub,
            "arxiv_id": code,
            "url": "https://arxiv.org/abs/" + code if code else aid,
            "primary_cat": cats[0] if cats else "",
            "cats": cats,
        })
    return out


def fetch(direction, max_results=30, days_back=0, sort="submittedDate",
          use_cache=True, extra="", loose=False):
    """抓某个方向的最新论文。

    days_back > 0 时只保留最近 N 天（arXiv 的时间过滤是模糊的，
    这里在本地做精确过滤）。

    返回 {"direction":..., "query":..., "papers":[...], "cached":bool, "error":str}
    """
    d = (direction or "").strip()
    if not d:
        return {"direction": d, "query": "", "papers": [], "cached": False,
                "error": "方向名为空"}
    q = build_query(d, extra, loose=loose)
    if not q:
        return {"direction": d, "query": "", "papers": [], "cached": False,
                "error": "这个方向名翻译不出英文检索词，试试直接输英文"}

    key = "%s|%d|%s|%d" % (q, max_results, sort, days_back)
    cache = _load_cache()
    rec = cache.get(key)
    if use_cache and rec and time.time() - rec.get("ts", 0) < CACHE_TTL:
        papers = rec.get("papers", [])
        fb = rec.get("fallback", "")
        return {"direction": d, "query": q if not fb else fb, "papers": papers,
                "cached": True, "fallback": fb, "relaxed": bool(fb), "error": ""}

    _throttle()
    params = {
        "search_query": q,
        "start": 0,
        "max_results": max(1, min(100, max_results)),
        "sortBy": sort,
        "sortOrder": "descending",
    }
    url = ARXIV_API + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "kb-research-local/1.0 (mailto:kb-local@example.com)"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            xml = resp.read().decode("utf-8", "ignore")
    except Exception as e:
        # 失败不写缓存，下次重试
        return {"direction": d, "query": q, "papers": [], "cached": False,
                "error": "网络请求失败：%s" % e}

    papers = _parse_xml(xml)
    fallback = ""

    # 严格式 0 篇时的兜底：细分方向可能一两个月没人写（实测「事件相机语义
    # 分割」这类），但用户点一下什么都不出来体验很差。退成领域词 OR 检索，
    # 至少给出邻近工作；结果会标记 relaxed=True，界面必须如实告诉用户。
    if not papers:
        fb = _fallback_query(d)
        if fb and fb != q:
            _throttle()
            try:
                params2 = dict(params, search_query=fb)
                url2 = ARXIV_API + "?" + urllib.parse.urlencode(params2)
                req2 = urllib.request.Request(url2, headers={
                    "User-Agent": "kb-research-local/1.0 (mailto:kb-local@example.com)"})
                with urllib.request.urlopen(req2, timeout=40) as resp2:
                    papers = _parse_xml(resp2.read().decode("utf-8", "ignore"))
                fallback = fb
            except Exception:
                pass

    if days_back > 0:
        import datetime
        cut = (datetime.date.today() -
               datetime.timedelta(days=days_back)).isoformat()
        papers = [p for p in papers if (p.get("published") or "") >= cut]

    cache[key] = {"ts": time.time(), "papers": papers, "fallback": fallback}
    _save_cache(cache)
    return {"direction": d, "query": q, "papers": papers, "cached": False,
            "fallback": fallback, "relaxed": bool(fallback), "error": ""}


def _load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("items", {}) if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_cache(items):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"version": 1,
                       "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "items": items}, f, ensure_ascii=False)
    except Exception:
        pass


def summarize(papers, limit=5):
    """给界面用的紧凑摘要：这批论文在讲什么。"""
    if not papers:
        return ""
    from collections import Counter
    words = Counter()
    stop = {"the", "a", "an", "of", "and", "for", "in", "on", "with", "via",
            "to", "we", "our", "this", "that", "is", "are", "by", "from", "as",
            "based", "using", "propose", "novel", "method", "approach", "paper"}
    for p in papers[:limit]:
        for w in re.findall(r"[a-z][a-z\-]{2,}", (p.get("title") or "").lower()):
            if w not in stop:
                words[w] += 1
    return "、".join(w for w, _ in words.most_common(6))


def stats():
    c = _load_cache()
    return {"cached_queries": len(c),
            "last": max((v.get("ts", 0) for v in c.values()), default=0)}


if __name__ == "__main__":
    import sys
    args = sys.argv[1:] or ["红外小目标检测"]
    for d in args:
        print(f"方向：{d}")
        print(f"  检索式：{build_query(d)}")
        r = fetch(d, max_results=8)
        if r["error"]:
            print("  错误：", r["error"])
            continue
        print(f"  拿到 {len(r['papers'])} 篇{'（缓存）' if r['cached'] else ''}")
        for p in r["papers"][:6]:
            print(f"    {p['published']}  {p['title'][:62]}")
        s = summarize(r["papers"])
        if s:
            print("  高频词：", s)