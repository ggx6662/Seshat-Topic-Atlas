#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨领域选题融合 —— 把两个（或更多）研究方向拼成可执行的交叉课题。

为什么要做
----------
选题工坊原来只接受一个方向。但真实的交叉课题（「用扩散模型做红外小目标检测」）
从来不是一个词，而是 **方向 × 方法 × 邻域** 三块拼起来的：

    A 研究方向   你熟悉的领域，候选池的主体        例：红外小目标检测
    B 方法/技术  从别的领域借过来的手段            例：扩散模型
    C 邻接领域   想把成果推广到的下游方向          例：医学影像

用户只输 A 时，我们只能猜 B；把 B 明确说出来，候选才真的"是他的题"。

做法
----
对每个角度（topic_gen.ANGLES 里的 22 个）配一个融合类型：

    技术驱动  A 的问题 + B 的手段        「用 B 解 A」
    下游迁移  A 的方法 → C 的新场景      「A 搬到 C」
    共通抽象  两边共享的难点             「A 与 C 的共同痛点」
    反向借鉴  C 已成熟的思路 → A 的领域  「C 的办法救 A」
    三方交叉  A 的问题 + B 的手段 + C 的评测/场景

绝不硬拼
--------
「医药 × 肝脏病理 × 区块链」这种组合看起来新颖，实际上没有可验证的连接点。
所以每条候选都要过一道 `plausible()`：组合必须有「共同的失效场景」或
「方法确实能处理这类型数据」才算通过。过不了的不给你看，也不给你一个
看起来漂亮的假标题。

设计原则（与 topic_gen 一致）：只给结构，不假装是结论。
"""

import itertools
import re

import topic_gen

# 跨领域候选里「新颖度」的权重（单方向是 0.30）。见 _rank()。
_NOVELTY_W = 0.40

# 角度 key → 融合类型。key 是 topic_gen.ANGLES 里的第一个元素，不是显示名
# （中文显示名会改，key 不会）。没列到的 key 才走默认逻辑。
_KIND = {
    # 借方法进来：B 的手段 + A 的问题
    "开放词汇": "技术驱动",
    "自监督": "技术驱动",
    "扩散": "技术驱动",
    "多模态": "技术驱动",
    "事件相机": "技术驱动",
    "三维": "技术驱动",
    "语言": "技术驱动",
    "分割": "技术驱动",
    "跟踪": "技术驱动",
    "视频": "技术驱动",
    # 把成果推出去：A 的方法 → C 的场景
    "跨域泛化": "下游迁移",
    "轻量化": "下游迁移",
    "小样本": "下游迁移",
    "鲁棒": "下游迁移",
    # 共同痛点
    "评测": "共通抽象",
    "可解释": "共通抽象",
    "复现": "共通抽象",
    # 反向借鉴
    "范式": "反向借鉴",
    "机理": "反向借鉴",
    "新任务": "反向借鉴",
    # 三方
    "理论": "三方交叉",
    "多尺度": "三方交叉",
}

# 没有左右搭配就说不成立的角度 —— 它们的价值全在「跟谁配」。
# 「小样本」单方向时照样是好候选（就是小样本学习），但「用扩散模型做小样本」
# 与「小样本搬去医学影像」是两回事，缺哪块就跳过哪类。
_NEED_B = ("开放词汇", "自监督", "扩散", "多模态", "事件相机", "三维", "语言",
           "分割", "跟踪", "视频")
_NEED_C = ("跨域泛化", "轻量化", "小样本", "鲁棒", "评测", "可解释", "复现",
           "范式", "机理", "新任务")
_NEED_BC = ("理论", "多尺度")

# 中文模板：每条都要在标题里明确写出「谁和谁结合」，不能只给一个名词堆。
# 用 {angle} 而不是直接替换成显示名，让读者自己判断这是"问题"还是"手段"。
_TPL = {
    "技术驱动": {
        "1": "用{b}解决{a}中的{angle}问题",
        "2": "{b}驱动的{a}：面向{angle}的方法设计",
        "3": "{a} × {b}：{angle}视角的重构",
    },
    "下游迁移": {
        "1": "{a}向{c}的迁移与适配：{angle}约束下的再设计",
        "2": "面向{c}的{a}：{angle}问题从哪里接着做",
        "3": "把{a}搬进{c}：{angle}会在哪一步失效",
    },
    "共通抽象": {
        "1": "{a}与{c}的{angle}共性机制与统一方案",
        "2": "{angle}驱动的跨域统一框架：{a} × {c}",
        "3": "同一种{angle}失败：{a}与{c}的联合分析",
    },
    "反向借鉴": {
        "1": "借{c}的思路重做{a}的{angle}",
        "2": "{c}中的{angle}经验对{a}的可用性考察",
        "3": "从{c}的{angle}做法反推{a}该改什么",
    },
    "三方交叉": {
        "1": "{b} × {a} × {c}：{angle}视角的三方研究",
        "2": "面向{c}的{b}+{a}协同{angle}方案",
    },
}

# 融合类型 → 额外的验证问题（和角度自带的问题互补，不是重复）
_KIND_Q = {
    "技术驱动": "B 的方法原设计约束（数据量 / 模态 / 算力）在 A 里成立吗？哪里不成立？",
    "下游迁移": "A 里的收益在 C 的数据分布上还成立吗？先在 C 的公开子集上跑 baseline。",
    "共通抽象": "两边真的是同一种失败，还是只是名字像？各自的失败判据要能对得上。",
    "反向借鉴": "C 的做法依赖的前提 A 有没有？缺哪个前提，这条就走不通。",
    "三方交叉": "三方都牵涉时，哪一方的收益是必要的？拆掉任意一方，结果会掉多少？",
}

# ---------------------------------------------------------------- 合理性校验
# 有些组合看着新颖、实际没有可验证的连接点。最常见的三类：
#   ① 不沾计算机的领域（医药/化学/法律）当方法用；
#   ② 两个都是"载体/模态"（红外 + 点云），拼起来没有共同任务；
#   ③ 一边是纯理论（数学证明），另一边是纯工程（嵌入式部署）。
_OFF_CS = ("医药", "制药", "化学合成", "法律条文", "临床试验", "农业种植", "文物修复")
_PURE_THEORY = ("数学证明", "形式化证明", "渐近理论", "复杂理论")
_PURE_ENGINEER = ("嵌入式部署", "芯片设计", "电路设计", "固件")

# 「载体类」方向：两个载体要拼必须有明确的任务词兜底（见 plausible 的 task 逻辑）
_CARRIER = ("红外", "可见光", "点云", "遥感", "多光谱", "高光谱", "SAR",
            "超声", "CT", "MRI", "内窥", "事件相机", "night", "夜间", "低光")


def _has(text, words):
    low = (text or "").lower()
    return any(w.lower() in low for w in words)


def plausible(a, b="", c=""):
    """判断这个组合有没有可验证的连接点。

    返回 (ok, reason)。不 ok 的时候 reason 说明为什么跳过 —— 界面上要能解释
    「为什么这个角度没出现」，而不是让用户以为我们漏了。
    """
    parts = [p for p in (a, b, c) if p]
    if len(parts) < 2:
        return False, "至少要有两个方向才能交叉"
    joined = " ".join(parts)
    if _has(joined, _OFF_CS):
        return False, "包含与本工具范围无关的学科（只做计算机为主的交叉）"
    if _has(b or a, _PURE_THEORY) and _has(c, _PURE_ENGINEER):
        return False, "纯理论与纯工程两端没有共同的验证指标"
    # 两个载体 + 没有任何任务词 → 「红外 × 点云」这种拼法没有共同任务
    carriers = [p for p in parts if _has(p, _CARRIER)]
    if len(carriers) >= 2 and not _has(joined, ("检测", "分割", "跟踪", "识别", "融合",
                                                "估计", "重建", "增强", "检索", "分类",
                                                "生成", "配准", "定位", "去噪", "超分")):
        return False, "两个都是数据载体，缺少共同任务（补上检测/融合/分割等任务词）"
    return True, ""


def _dedupe_titles(titles):
    """标题去重：去掉标点后完全相同的只留一条。"""
    seen, out = set(), []
    for t in titles:
        k = re.sub(r"[，,。:：;；\s\-—/]+", "", t)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def build(a, b="", c="", alpha=1.0, beta=0.6, gamma=0.5, limit=18):
    """生成跨领域候选。

    alpha/beta/gamma 是「贴近主方向」的权重：主方向相关度最高，方法其次，
    邻域第三。因为用户的主方向是他自己最熟的地方，候选必须首先还叫那个题。

    返回列表，条目字段和 topic_gen.build 一致（title/strategy/angle/reason/
    questions/min_experiment/relevance/novelty/feasibility/score），
    另外多一个 `combo` 字段：{"a","b","c","kind"}，供界面显示来源。
    """
    a = (a or "").strip()
    b = (b or "").strip()
    c = (c or "").strip()
    if not a:
        return []
    ok, why = plausible(a, b, c)
    if not ok:
        return [{"error": why}]

    combos = []   # (融合类型, 角度元组)
    for strategy, items in topic_gen.ANGLES.items():
        for item in items:
            key = item[0]
            kind = _KIND.get(key) or ("技术驱动" if b else "下游迁移")
            combos.append((kind, (strategy,) + item))
    if not combos:
        return []

    out, seen = [], set()
    order = 0
    for kind, tup in combos:
        strategy, key, label, reason, question, min_exp, novelty, feas = tup
        # 缺哪块就跳过哪类：没有 B 就不要「用 B 解 A」的标题，
        # 标题里写成「用跨领域方法解决…」是最典型的假候选。
        if key in _NEED_B and not b:
            continue
        if key in _NEED_C and not c:
            continue
        if key in _NEED_BC and not (b and c):
            continue
        tpls = _TPL.get(kind) or _TPL["技术驱动"]
        for seq in sorted(tpls, key=lambda s: int(s)):
                # 模板带 {c} 但没填 C 时，宁可不出这条 ——
                # 「A 向下游场景的迁移」是空话，不如少给一条
                tpl = tpls[seq]
                if "{c}" in tpl and not c:
                    continue
                if "{b}" in tpl and not b:
                    continue
                title = tpl.format(a=a, b=b or "跨领域方法", c=c or "下游场景",
                                   angle=label)
                k = re.sub(r"[，,。:：;；\s\-—/]+", "", title)
                if k in seen:
                    continue
                seen.add(k)
                # 相关度按「离主方向多远」衰减，方法越远相关越低
                relevance = 92 * alpha - min(26, order * 1.5)
                if b and b in title:
                    relevance = min(96, relevance + 2)
                out.append({
                    "title": title,
                    "strategy": strategy,
                    "angle": label,
                    "angle_key": key,
                    "kind": kind,
                    "combo": {"a": a, "b": b, "c": c},
                    "reason": _reason(kind, a, b, c, label, reason),
                    "questions": [topic_gen._clean(question), _KIND_Q.get(kind, "")],
                    "min_experiment": _min_exp(kind, a, b, c, min_exp),
                    "relevance": int(relevance),
                    "novelty": int(min(98, novelty * beta + 30
                                        + (8 if kind == "三方交叉" else 0))),
                    "feasibility": int(feas * gamma + 20),
                    "score": 0,
                })
                order += 1
                break   # 同一 (角度, 类型) 只留第一个骨架，别让三种句式挤满列表
        if len(out) >= limit * 3:
            break

    _rank(out)
    return _pick(out, limit)


# 跨领域候选的排序：新颖度权重比单方向高（_NOVELTY_W 定义在文件顶部）。
# 单方向生成时「相关」最重要（必须还叫那个题）；交叉生成时读者已经知道
# 主体是 A，真正的信息在「这个组合新不新」，所以新颖度从 0.30 提到 0.40。
def _rank(cands):
    for c in cands:
        c["score"] = int(round(0.40 * c["relevance"]
                               + _NOVELTY_W * c["novelty"]
                               + (1 - 0.40 - _NOVELTY_W) * c["feasibility"]))


def _pick(out, limit):
    """选哪些候选给用户看。

    三轮，按用户实际最该先看什么排：
      ① 每种融合类型至少一条 —— 借方法/搬场景/找共性/反向借/三方，
          技术驱动分数最低，不保底会被整类挤没。
      ② 每个具体组合一条 —— 跨域泛化向 A 迁移、自监督+扩散、评测×A×C…
          它们才是不同的题；同一组合换个说法的三条只留一条。
      ③ 每个角度一条 —— 补齐广度。

    为什么把①提到最前：A 固定时下游迁移类的标题骨架完全一样
    （A 向 C 的迁移与适配：X 约束下的再设计），单靠②③会把前六条填成
    同一句式的不同变体，读者看不出还有借方法、三方交叉这些拼法。
    """
    by_combo, by_angle, by_kind, lead = {}, {}, {}, []
    ranked = sorted(out, key=lambda x: -x['score'])

    def _push(cand):
        if cand not in lead and len(lead) < limit:
            lead.append(cand)

    for cand in ranked:
        if cand['kind'] not in by_kind:
            by_kind[cand['kind']] = cand
            _push(cand)
    for cand in _combo_round(ranked):
        _push(cand)
    for cand in ranked:
        k = cand.get('angle_key') or cand.get('angle')
        if k not in by_angle:
            by_angle[k] = cand
            _push(cand)
    rest = [c for c in out if c not in lead]
    return (lead + rest)[:limit]


def _combo_round(ranked):
    """每个角度×融合类型组合取分最高的一条，保持分数顺序输出。"""
    picked = {}
    for cand in ranked:
        k = (cand.get('angle_key'), cand['kind'])
        if k not in picked:
            picked[k] = cand
    return sorted(picked.values(), key=lambda x: -x['score'])


def _reason(kind, a, b, c, label, base):
    """在角度自带理由前面加一句「这次是怎么拼的」，两段都要有信息量。

    第一段必须把原料点破：读者看到「用扩散模型解决红外小目标检测中的开放
    词汇扩展问题」这种标题时，要知道后面那句话是 A、B、C 里哪两块拼的，
    否则它读起来仍然像随机名词堆。
    """
    b = b or ""
    c = c or ""
    head = {
        "技术驱动": "拼接：%s（手段）→ %s（问题），切入点是「%s」。" % (b, a, label),
        "下游迁移": "拼接：%s（已有方法）→ %s（新场景），切入点是「%s」。" % (a, c, label),
        "共通抽象": "拼接：%s 与 %s，共同难点是「%s」。" % (a, c, label),
        "反向借鉴": "拼接：%s（已有经验）→ %s（待改进），借的是「%s」。" % (c, a, label),
        "三方交叉": "拼接：%s 的手段、%s 的问题、%s 的场景，视角是「%s」。" % (b, a, c, label),
    }.get(kind, "")
    return re.sub(r"\s+", " ", (head + " " + (base or ""))).strip()


def _min_exp(kind, a, b, c, base):
    extra = {
        "技术驱动": "先在 %s 的公开数据上只替换 %s 模块，其他全不动，看它单独能带来多少。" % (a, b),
        "下游迁移": "把 %s 上已跑通的结果直接丢到 %s 的一个公开子集，先测「原样搬过去掉多少」。" % (a, c),
        "共通抽象": "两端的失败案例各取 20 个，人工标注失败类型，看重叠率是不是真的高。" % (),
        "反向借鉴": "把 %s 里成熟的一条做法最小化地搬一步，看能否复现它在那边的收益。" % (c,),
        "三方交叉": "先做两两组合（共三种），哪个两两组合都灵，才值得上三方。",
    }.get(kind, "")
    return re.sub(r"\s+", " ", (extra + " " + (base or ""))).strip()


# ---------------------------------------------------------------- 方向校验
def check_direction(text):
    """检查一个方向词到底该当 A/B/C 哪一块。

    用户经常把「扩散模型」也填成「研究方向」。这时把它当 A 会得到
    「扩散模型的跨域泛化方案」这种空题 —— 它本身不是研究领域，是方法。
    """
    import kb_widget as kb
    text = (text or "").strip()
    if not text:
        return {"ok": False, "role": "", "msg": "空"}
    cat, field, conf = kb.infer_category_field(text)
    if cat and field and conf >= 60:
        return {"ok": True, "role": "field", "cat": cat, "field": field, "conf": conf,
                "msg": "%s / %s（置信度 %d%%）" % (cat, field, conf)}
    return {"ok": False, "role": "method", "cat": cat, "field": field, "conf": conf,
            "msg": "没能识别到具体的计算机领域，可能是一个方法或技术名词 —— 把它填到 B 更合适"}


def suggest_companions(a, limit=8):
    """给主方向推荐可以搭配的 B/C。

    来源是本地的方向库：同大类下的其它细分领域（可当 B 的方法或 C 的邻域）。
    不猜「外部学科」，因为猜出来的组合大多不可验证。
    """
    import kb_widget as kb
    lib = kb.load_direction_library()
    info = check_direction(a)
    cat = info.get("cat") or ""
    pool = []
    def add(ci, name, why):
        if name and name != a and all(x[0] != name for x in pool):
            pool.append((name, ci, why))
    for ci, entry in lib.items():
        for sub in (entry.get("subs") or []):
            nm = sub.get("name") or ""
            if ci == cat:
                add(ci, nm, "同类目")
            elif ci in ("人工智能", "计算机视觉", "自然语言处理", "机器人与具身智能"):
                add(ci, nm, "可作方法")
    seen, out = set(), []
    for nm, ci, why in pool:
        if nm in seen:
            continue
        seen.add(nm)
        out.append({"name": nm, "cat": ci, "why": why})
        if len(out) >= limit:
            break
    return out