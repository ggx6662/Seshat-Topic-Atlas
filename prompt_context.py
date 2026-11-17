"""把画像变成提示词里的一段上下文。

为什么单独一个模块
------------------
提示词分散在 `research_skills`、`page_topic`、`page_skills`、`page_ideas` 四处，
每个地方各拼一遍「我的情况」，很快就会拼出四种不同说法。更糟的是
**画像为空时拼出来的不是空，而是废话**（「你目前没有特殊偏好」），
模型会照着这句话编理由。

所以这里的规矩是：**没有信息就不输出整段**。宁可提示词短，也不要有损信息
占位。每一条都能追溯到画像里的一个真实字段，用户点一下就能对着改。

和 `profile_brief()` 的分工：
  · `profile_brief()` 是给"聊天的模型"读的散文，带情绪和回忆
  · 这里是给"任务型提示词"用的结构化约束块，只放会影响该次任务执行的字段
"""
import re


def _clean_list(xs, limit=6):
    out = []
    for x in xs or []:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _top(prefs, key, n=3, floor=1):
    """取偏好里权重最高的几个。低于 floor 的一律不要 —— 存过 1 次不代表偏好。"""
    d = (prefs or {}).get(key) or {}
    if not isinstance(d, dict):
        return []
    got = [(k, v) for k, v in d.items()
           if isinstance(v, (int, float)) and v >= floor and str(k).strip()]
    got.sort(key=lambda kv: -kv[1])
    return got[:n]


def _mood_line(state):
    """当前状态只写会影响判断的那几个维度，不写「今天心情不错」。

    注意 `tilt_inputs()` 返回的是**扁平**结构（urgency / interest / mood 直接
    在顶层），`state` 这个嵌套键并不存在。以前只读嵌套键，结果一个人把
    紧迫度拉到 85、心境改成「焦虑」，提示词里一个字都没体现 —— 校验时
    那一刻才发现。这里两种结构都认。
    """
    state = dict(state or {})
    inner = state.get("state")
    if isinstance(inner, dict):
        merged = dict(inner)
        merged.update({k: v for k, v in state.items() if k != "state"})
        state = merged
    urg = state.get("urgency")
    mood = (state.get("mood") or "").strip()
    parts = []
    if isinstance(urg, (int, float)):
        if urg >= 80:
            parts.append("离截止很近（%d/100）" % int(urg))
        elif urg >= 60:
            parts.append("时间偏紧（%d/100）" % int(urg))
        elif urg <= 25:
            parts.append("时间宽裕（%d/100）" % int(urg))
    if mood and mood not in ("平静",):
        parts.append("当前状态：%s" % mood)
    return "；".join(parts)


def _constraints(c):
    """硬约束是「做不做得到」的边界，必须原样告诉模型，不能改写。"""
    if not c:
        return []
    out = []
    for key, label in (("compute", "算力"), ("months", "期限"), ("style", "偏好")):
        v = str(c.get(key) or "").strip()
        if v:
            out.append("%s：%s" % (label, v))
    avoid = _clean_list(c.get("avoid"), limit=5)
    if avoid:
        out.append("不碰：" + "、".join(avoid))
    return out


def block(profile=None, constraints=None, memories=None, want="task"):
    """生成「情况」段。没信息时返回空字符串（**不要返回占位文字**）。

    profile      `profile_memory.tilt_inputs()` 的返回值（扁平：urgency/mood/
                 prefs/identity），可为 None；也接受 {"identity": {...},
                 "state": {...}} 这种嵌套写法
    constraints  profile_memory.constraints()
    memories     [(标签, 正文)] 或 [str]，最近相关的几条
    want         "task" 用于具体任务提示词；"plan" 用于长期改进计划
    """
    lines = []
    prof = dict(profile or {})
    ident = prof.get("identity") if isinstance(prof.get("identity"), dict) else prof
    base_ident = {"stage": "硕士在读"}    # 见 profile_memory._default_profile
    stage = str(ident.get("stage") or "").strip()
    if stage == base_ident["stage"]:
        stage = ""      # 默认值不是用户填的，说了等于没说
    school = str(ident.get("school") or "").strip()
    goal = str(ident.get("goal") or "").strip()
    resources = str(ident.get("resources") or "").strip()
    who = []
    if school:
        who.append(school)
    if stage:
        who.append(stage)
    if who:
        lines.append("· 身份：" + " · ".join(who))
    if goal:
        lines.append("· 目标：" + goal)
    if resources:
        lines.append("· 已有条件：" + resources)

    # tilt_inputs() 是扁平的：urgency / mood 在顶层；嵌套写法在 .state 里
    state = _mood_line(prof.get("state") if isinstance(prof.get("state"), dict) else prof)
    if state:
        lines.append("· 时间与状态：" + state)

    for c in _constraints(constraints):
        lines.append("· " + c)

    prefs = (profile or {}).get("prefs") or (profile or {}).get("preferences") or {}
    fields = _top(prefs, "fields", 3, floor=2)
    if fields:
        lines.append("· 一直在看的方向：" + "、".join("%s(%g)" % (k, v) for k, v in fields))
    angles = _top(prefs, "angle", 3, floor=3)
    if angles:
        lines.append("· 以前多次选的角度：" + "、".join("%s(%g)" % (k, v) for k, v in angles))
    strats = _top(prefs, "strategy", 2, floor=3)
    if strats:
        lines.append("· 倾向的策略：" + "、".join("%s(%g)" % (k, v) for k, v in strats))

    mem = _clean_memories(memories, limit=5 if want == "plan" else 3)
    if mem:
        lines.append("· 最近的记录：" + "；".join(mem))

    if not lines:
        return ""
    head = "【我的情况】" if want == "task" else "【背景：这个人是谁】"
    tail = {
        "task": ["以上是我的实际情况。请让建议落在这个范围内；",
                 "如果我给的约束和你的建议冲突，直接说出来，不要绕过约束硬做。"],
        "plan": ["以上是这个人在做事的实际条件。计划要能在这个条件下执行；",
                 "如果某一步明显超出条件，请直接指出并给更小的替代方案。"],
    }.get(want, [])
    return "\n".join([head] + lines + [""] + tail + [""])


def _clean_memories(memories, limit=3):
    """记忆可能是 dict（profile_memory 的 anchor 记录）也可能是字符串。"""
    out = []
    for m in memories or []:
        if isinstance(m, dict):
            t = str(m.get("text") or "").strip()
        else:
            t = str(m or "").strip()
        if not t:
            continue
        t = re.sub(r"\s+", " ", t)[:80]
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def gather(profile=None, constraints=None, memories=None):
    """一次把三样取齐，任何一样取不到就退回空值而不是抛异常。

    提示词生成不应该因为画像文件坏了就不能用 —— 但要能看出「这段没加上」，
    所以返回的 raw 里带着每项的来源状态，界面可以据此提示用户去补。
    """
    got = {"profile": profile, "constraints": constraints,
           "memories": memories, "ok": True, "errors": []}
    if profile is None:
        try:
            import profile_memory as PM
            got["profile"] = PM.tilt_inputs()
        except Exception as exc:
            got["errors"].append("profile: %s" % exc)
    if constraints is None:
        try:
            import profile_memory as PM
            got["constraints"] = PM.constraints()
        except Exception as exc:
            got["errors"].append("constraints: %s" % exc)
    if memories is None:
        try:
            import profile_memory as PM
            # recall() 返回的是 dict（items/total/shown/tilt/...），不是列表。
            # 直接拿去喂 _clean_memories 会把键名当成记忆内容（踩过一次）。
            r = PM.recall(limit=5)
            if isinstance(r, dict):
                got["memories"] = [x.get("record") if isinstance(x, dict) else x
                                   for x in (r.get("items") or [])]
            else:
                got["memories"] = r
        except Exception as exc:
            got["errors"].append("memories: %s" % exc)
    got["ok"] = not got["errors"]
    return got