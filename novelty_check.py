"""新颖性核查：这条候选，全库里有没有人已经做过很接近的？

这个模块解决一个具体的失败：选题工坊给出的候选，分数是「本地预估」——
它衡量的是一条题**结构上完不完整、角度新不新**，而不是「世界上有没有人做过」。
两者会被当成一件事，是本工具最容易被误用的地方。

做法（两层，各自回答不同的问题）：
  近邻层  向量最近邻，回答「最像的那几篇有多像」。只看相似度，
          不要求词命中 —— 考的是语义。
  词层    多关键词交集，回答「这个概念组合被原样写下来的有多少篇」。
          词命中最硬的证据：标题里同时出现 B 和 A 的做法，基本就是撞题。

判档看的是**两层的组合**，不是单一分数：
  高风险  top1 ≥ 0.80，或 top1 ≥ 0.70 且近 2 年有 ≥3 篇 —— 别人已经在做
  中风险  top1 ≥ 0.62 —— 邻域很挤，得说清你哪里不一样
  低风险  其余 —— 没查到近邻，但这**不等于**没人做过（CS 之外的论文、
          未上 arXiv 的工作、我们没建的索引，都查不到）

上限必须写在界面上：索引是 arXiv cs 近三年 53.8 万篇。
CVPR/ICCV/NeurIPS 的正会论文、期刊、工业界内部工作不在里面；
一篇 CVPR 论文可能根本没有 arXiv 版本。所以「低风险」的正确读法是
「在我们能看到的范围内没查到」，不是「这是空白」。
"""
import re
import time

import kb_vector

# 判档门槛。调过一轮：0.86 太高（几乎所有候选都落低风险，等于没查），
# 0.70 又把「同一大方向下的正常近邻」全判成高风险，用户会当噪音关掉。
TOP_HIGH = 0.80
TOP_MID = 0.62
RECENT_DAYS = 730          # 「近两年」按 730 天算，跨年更好解释
RECENT_HIGH = 3            # 近两年撞车 3 篇以上，就算 top1 差一点也够呛

LEVEL_LABEL = {
    "high": ("撞车风险高", "ERR"),
    "mid": ("邻域较挤", "WARN"),
    "low": ("没查到近邻", "OK"),
}

# 中文角度名 → 检索词。用 `angle_key` 而不是 label 作键：
# label 会随文案改，key 是稳定的英文短名。
_ANGLE_TERMS = {
    "跨域泛化": "domain generalization",
    "开放词汇": "open-vocabulary",
    "轻量化": "lightweight efficient",
    "小样本": "few-shot",
    "自监督": "self-supervised",
    "可解释": "interpretability",
    "评测": "benchmark evaluation",
    "鲁棒": "robustness adversarial",
    "多尺度": "multi-scale",
    "分割": "segmentation",
    "跟踪": "tracking",
    "视频": "video",
    "多模态": "multi-modal",
    "三维": "3d",
    "扩散": "diffusion model",
    "语言": "language model",
    "事件相机": "event camera",
    "范式": "paradigm",
    "机理": "mechanism analysis",
    "新任务": "new task",
    "理论": "theoretical analysis",
    "复现": "reproducibility benchmark",
}

_STOP = {
    "的", "与", "和", "及", "或", "用", "在", "对", "把", "被", "从", "向", "为",
    "一", "个", "种", "基于", "通过", "面向", "一种", "研究", "方法", "问题",
}


def _split_title(title):
    """把候选标题拆成「主干词」。

    标题都是中文模板拼出来的（「用扩散模型解决红外小目标检测中的开放词汇扩展问题」），
    里面夹着英文方法名和中文方向名。要拿去查全库，得先变成词，
    而且**不能只取最后一个词** —— 「开放词汇扩展」和「红外小目标检测」
    分别是「角度」和「方向」，两个都得查。
    """
    t = (title or "").strip()
    if not t:
        return []
    # 先按中文虚词切，再按标点切
    parts = re.split(r"[，,。;；:：、—\-/（）()「」《》\s]+", t)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # 英文/数字片段单独成词（扩散模型这类中文仍走整段翻译）
        for m in re.finditer(r"[A-Za-z][A-Za-z0-9\-]{1,}", p):
            out.append(m.group(0))
        zh = re.sub(r"[A-Za-z0-9\-]+", " ", p).strip()
        if zh:
            out.append(zh)
    return [x for x in out if x and x not in _STOP]


def build_query(cand, direction=""):
    """候选 → 两组检索词。

    返回 {"phrase": 给向量用的整句, "terms": 给 AND 用的词, "angle": 角度词}

    为什么 AND 那边要砍掉一部分词：词越多交集越小，四个词 AND 起来
    经常是 0 篇，那不能证明新，只能证明我们查得太死。
    取「角度词 + 主体方向词」两三个就够，多出来的是模板里的修饰语。
    """
    title = cand.get("title") or ""
    combo = cand.get("combo") or {}
    # 踩过的坑：单方向生成的候选**没有 combo**（combo 只在跨领域组合时才有）。
    # 第一版直接从 combo 取词，A 是空的，查询退化成只剩角度词
    # 「domain generalization」—— 查出来是数学拓扑，还给了 0.80 的高分。
    # 一定要有 direction 兜底，而且它比角度词重要：没有主体，
    # 任何角度词都会飘到别的学科去。
    a = (combo.get("a") or "").strip() or (direction or "").strip()
    b = (combo.get("b") or "").strip()
    c = (combo.get("c") or "").strip()
    angle_key = cand.get("angle_key") or ""
    angle = _ANGLE_TERMS.get(angle_key, "")

    if a:
        terms = [a]
        for t in (b, c, angle):
            if t and t not in terms:
                terms.append(t)
        phrase = " ".join([x for x in (a, b, c) if x] + ([angle] if angle else []))
    else:
        # 连方向都没有，只能拿标题兜底，质量差，判档要保守
        terms = _split_title(title)[:3]
        phrase = title
    return {"phrase": phrase, "terms": terms, "angle": angle_key}


def _recent_cutoff():
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - RECENT_DAYS * 86400))


def _judge(top1, recent_n, hit_n, and_ok, base_n=0):
    """由「语义近邻」定档，词层只做一种有限修正。

    为什么不让词层单独判 high：试过，判不准。
    红外小目标检测 × 跨域泛化，词层 24/987 = 2%，语义 top1 只有 0.54；
    医学图像分割 × 跨域泛化，词层 681/18499 = 4%，语义 top1 0.82。
    两者词层占比差不多（2% vs 4%），语义却差一大截 —— 说明占比
    分辨不出「检测论文顺口提一句跨域」和「真在跨域做医学分割」。
    词层的价值在另一件事：**同一批候选内部比较谁更挤**，
    以及「两三个概念被原样写在一起的篇数」这个可展示的证据。
    所以档位交给向量层，词层只在语义已经偏挤时给一点点加成。
    """
    if top1 >= TOP_HIGH or (top1 >= TOP_MID + 0.08 and recent_n >= RECENT_HIGH):
        return "high"
    if top1 >= TOP_MID or recent_n >= RECENT_HIGH * 2:
        return "mid"
    # 语义上不算近，但同名概念组合已经有一小撮论文（且不是零头占比），
    # 那也不是「没查到」，至少算「邻域较挤」
    if and_ok and base_n and hit_n >= _HIT_STRONG and (hit_n / base_n) >= _HIT_RATIO:
        return "mid"
    return "low"


def _reason(level, top1, recent_n, hit_n, near, and_ok=True, base_n=0):
    if level == "high":
        if and_ok and hit_n >= _HIT_STRONG and (hit_n / max(1, base_n)) >= _HIT_RATIO:
            return ("标题/摘要里同时写清这两个概念的已有 %d 篇，最像的一篇 %.2f —— "
                    "别人已经在做，得说清你哪里不一样" % (hit_n, top1))
        head = "最像的一篇已经像到 %.2f" % top1
        if near:
            head += "（%s）" % (near[0].get("title", "")[:46])
        sub = "近两年同类 %d 篇" % recent_n if recent_n else ""
        return " ".join(x for x in (head, sub) if x) + " —— 别人在做，得说清你哪里不一样"
    if level == "mid":
        return ("邻域里已经有 %d 篇近两年工作（最像 %.2f），"
                "不算空白，要把差异化写在题里" % (recent_n, top1))
    if and_ok and hit_n:
        return ("按词精确查只有 %d 篇、语义上最近 %.2f —— 查得到的范围里算新的"
                % (hit_n, top1))
    if and_ok:
        return ("按词精确查 0 篇、语义上最近 %.2f —— 查得到的范围里算新的，"
                "但 0 篇也可能是我们的词没对上人家写法" % top1)
    return "语义上没查到近邻（最近 %.2f），可以当方向继续，但要自己再查一次" % top1


# 词层的组数上限。**AND 每多一组都是指数级收窄**，实测：
#   infrared 4387 篇 → +open-vocabulary 14 篇 → +small object 89 篇
#   → 三者同时 0 篇。0 篇不代表新，只代表我们查得太死。
# 所以词层只判两三项，不把方向自己拆成红外/小目标/检测三组。
_MAX_AND_GROUPS = 3

# 词层要**方向的两个特征 + 角度**才算撞车证据。
# 只 AND「中心词 + 角度」是没用的：detection × domain generalization
# 有 1279 篇、detection × open-vocabulary 有 536 篇 —— 那是「检测器与
# 某个大方向」的通用拥挤，几乎每条候选都会触发，全判 high 等于没查。
# 必须是「红外 + 小目标 + 跨域泛化」这种带区分度的组合。
_HIT_STRONG = 3

# 词层占比阈值：命中的篇数相对「中心词自身」的篇数。
# detection 全库几万篇，1279/几万 ≈ 没什么；但红外 ∩ 小目标 ∩ 开放词汇
# 若真有几十篇，占比就压不住了。用占比而不是绝对数，避免大方向先天吃亏。
_HIT_RATIO = 0.02


def check(cand, k=5, direction=""):
    """核查一条候选。返回 dict，**永不抛异常**（索引缺失时给 available=False）。

    字段：
      level      "high" / "mid" / "low"
      top1       最像那篇的相似度
      recent_n   近两年、相似度 ≥ 0.62 的篇数
      hit_n      词层命中的篇数；配合 and_ok 才有意义
      base_n     中心词自身在全库的篇数（算占比的分母）
      and_ok     词层是否真的跑成一个有意义的 AND
      near       最近邻列表（每条 title/date/url/score）
      query      实际拿去查的句子与词
      reason     一句话结论
      available  索引在不在
    """
    q = build_query(cand, direction)
    try:
        near = kb_vector.search(q["phrase"], k=k) or []
    except Exception as exc:
        return {"available": False, "error": str(exc), "level": "unknown",
                "top1": 0.0, "recent_n": 0, "hit_n": 0, "base_n": 0,
                "and_ok": False, "near": [], "query": q,
                "reason": "向量索引不可用，没法核查"}
    top1 = float(near[0]["score"]) if near else 0.0
    cutoff = _recent_cutoff()
    recent_n = sum(1 for p in near if p.get("date", "") >= cutoff and p["score"] >= TOP_MID)

    # 词层：方向特征 + 角度。方向翻成英文后可能有多个词
    # （红外小目标检测 → small object / infrared / detection），
    # 全用会把 AND 收窄到 0；只留一个又变成通用拥挤。
    # 取法：保留「中心词」+ 一个「区分度最高的修饰语」。
    hit_n, base_n, and_ok = 0, 0, False
    probe, base_probe = [], []
    try:
        a_en = kb_vector._as_terms([q["terms"][0]]) if q["terms"] else []
        angle_en = _ANGLE_TERMS.get(q["angle"], "")
        if a_en:
            center = a_en[-1]
            mods = [t for t in a_en[:-1] if len(t.split()) == 1]
            # 修饰语优先选不常见的长词（infrared 比 detection 有区分度）
            mods.sort(key=len, reverse=True)
            probe = [center] + mods[:1] + ([angle_en] if angle_en else [])
            probe = probe[:_MAX_AND_GROUPS]
            # 分母必须是**方向自身**的篇数，不是中心词的。
            # 拿 detection 的 62166 当分母，分子永远是个零头，
            # 什么组合都判不成撞车 —— 实测「医学图像分割 × 跨域泛化」
            # 681 篇本该是 high，被 62166 一除变成 1%，白查。
            base_probe = [center] + mods[:1]
            # count_and 用向量预筛把扫描面缩到 6 万篇，单次从 2.5 秒降到 0.7 秒；
            # 新颖性核查一条要跑两次（分母一次、分子一次），九条候选
            # 全量扫要一分多钟，用户等不了。少的那部分篇数极不相似，
            # 对「像不像」这个判断没有影响。
            # 预筛词必须用**方向本身**，不能用 phrase：phrase 含角度词，
            # 会让预筛池偏向「讲这个角度」的论文，把本校「红外小目标」
            # 的基础文献漏掉 —— 实测分母从 987 掉到 171，占比虚高。
            hint = q["terms"][0] if q["terms"] else q["phrase"]
            if len(base_probe) >= 2:
                base_n = int(kb_vector.count_and(base_probe, vec_hint=hint) or 0)
            if len(probe) >= 2:
                hit_n = int(kb_vector.count_and(probe, vec_hint=hint) or 0)
                and_ok = True
    except Exception:
        hit_n, base_n, and_ok = 0, 0, False

    level = _judge(top1, recent_n, hit_n, and_ok, base_n)
    return {
        "available": True,
        "level": level,
        "top1": round(top1, 4),
        "recent_n": recent_n,
        "hit_n": hit_n,
        "base_n": base_n,
        "and_ok": and_ok,
        "near": [{"title": p.get("title", ""), "date": p.get("date", ""),
                  "url": p.get("url", ""), "score": p.get("score", 0)} for p in near],
        "query": q,
        "reason": _reason(level, top1, recent_n, hit_n, near, and_ok, base_n),
        "cutoff": cutoff,
    }


def annotate(cands, k=5, top_n=8, log=None, direction=""):
    """给一批候选打分并写回 `cand["nov"]`。

    只核前 top_n 条：每条要跑一次向量检索 + 一次 AND 检索，
    全文库 AND 单次 1–2 秒，18 条全核要三十秒以上，用户等不了。
    排序靠后的候选本来就不太可能被选，先核最可能被选的。
    被核过但排在后八条之后的候选会带 `nov: None`，界面上显示「未核查」。
    """
    done = 0
    for c in (cands or [])[:top_n]:
        if not isinstance(c, dict) or c.get("error"):
            continue
        c["nov"] = check(c, k=k, direction=direction)
        done += 1
        if log:
            log(c)
    for c in (cands or [])[top_n:]:
        if isinstance(c, dict) and not c.get("error"):
            c.setdefault("nov", None)
    return done


def annotate_one(cand, k=5, direction=""):
    """核一条，结果写回 `cand["nov"]`。

    2026-11-15 新增：生成时不再一口气核前 8 条（那条路要二十多秒，
    而且用户可能一条都不看）。现在改成「谁被选中就核谁」——
    打开详情的那一刻开始核，1–3 秒出结果，用户几乎无感。
    已被核过的候选直接返回，不重复跑检索。
    """
    if not isinstance(cand, dict) or cand.get("error"):
        return None
    old = cand.get("nov")
    if isinstance(old, dict) and old.get("level"):
        return old
    try:
        cand["nov"] = check(cand, k=k, direction=direction)
    except Exception:
        cand["nov"] = {"available": False, "reason": "核查失败"}
    return cand["nov"]


def summary(cands):
    """界面顶栏用的一句话结论。"""
    n = {"high": 0, "mid": 0, "low": 0, "unknown": 0}
    for c in cands or []:
        nv = c.get("nov") or {}
        n[nv.get("level") or "unknown"] = n.get(nv.get("level") or "unknown", 0) + 1
    checked = n["high"] + n["mid"] + n["low"]
    if not checked:
        return ""
    parts = []
    if n["high"]:
        parts.append("%d 条撞车风险高" % n["high"])
    if n["mid"]:
        parts.append("%d 条邻域较挤" % n["mid"])
    if n["low"]:
        parts.append("%d 条没查到近邻" % n["low"])
    # 2026-11-15 起「只核你点开的那几条」，所以这里要说「你点开的」，
    # 否则「已核 3 条」会被读成「18 条里只核了 3 条，其余有问题」。
    tail = "（只核了你点开的 %d 条；索引只含 arXiv cs 近三年，不是全世界的论文）" % checked
    return "、".join(parts) + tail