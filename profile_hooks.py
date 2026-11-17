"""界面行为的统一记录口。

为什么要单独一层
----------------
`profile_memory` 里的能力（remember / bump_pref / set_constraints）分散在十几个
页面里各写一遍 `try: import profile_memory ... except: pass`，有两个后果：

1. **漏记**：新加页面时忘了写，画像就永远停在旧数据。原来 12 个页面只有 4 个
   在记，文献库检索、文献空白、方法论、方向图谱完全没进画像。
2. **失败静默**：画像写盘失败被 `except: pass` 吞掉，界面上毫无察觉，
   用户以为在学，其实一条都没存。

所以这里做两件事：给出**统一的语义化记录函数**（看方向 / 查导师 / 检索文献 /
分析空白 / 生成提示词），并且把所有失败都记进一个进程内的计数表，
界面上可以读到「这次会话记了多少条、失败几条」。

设计原则：记录**只描述事实**，不替用户下结论。比如「检索了 X」是事实，
「你喜欢 X」是结论 —— 结论只能由 `bump_pref` 攒够次数后由 `topic_gen` 得出。
"""
import threading

FIELDS = "fields"          # 关注的研究方向
CATEGORIES = "categories"  # 关注的大类
ANGLE = "angle"            # 偏好哪种切入角度
STRATEGY = "strategy"      # 偏好哪类策略（稳健 / 跨领域 / 高风险）

_lock = threading.Lock()
_stats = {"ok": 0, "fail": 0, "last_error": ""}


def _pm():
    import profile_memory as PM
    return PM


def _guard(fn):
    """包一层：画像坏了也不能让界面崩。但失败必须被计数，不能静默。"""
    try:
        fn()
        with _lock:
            _stats["ok"] += 1
        return True
    except Exception as exc:
        with _lock:
            _stats["fail"] += 1
            _stats["last_error"] = "%s: %s" % (type(exc).__name__, exc)
        return False


# ---------------------------------------------------------------- 记录点
def see_field(field, source="", delta=1.0):
    """用户看/查/选了某个方向。四次调用以上，这个方向的偏好才开始影响排序。"""
    field = str(field or "").strip()
    if not field:
        return False
    def _do():
        PM = _pm()
        PM.bump_pref(FIELDS, field, delta=delta)
        PM.remember("关注方向：%s" % field[:80], tags=["方向", source or "浏览"],
                    kind="daily", ref=field[:80], source=source)
    return _guard(_do)


def see_category(cat, source="", delta=1.0):
    cat = str(cat or "").strip()
    if not cat:
        return False
    return _guard(lambda: _pm().bump_pref(CATEGORIES, cat, delta=delta))


def search(query, mode, hits, source=""):
    """记录一次检索。只有「搜了但没结果」才值得成为记忆锚点，命中就不记 —— 
    否则 500 条上限几周就被正常浏览塞满，真正的线索反而被挤掉。
    """
    q = str(query or "").strip()
    if not q:
        return False
    if hits:
        return False
    def _do():
        _pm().remember("搜「%s」没有结果" % q[:60], tags=["冷门", source or mode],
                       kind="daily", ref=q[:60], source=source or mode)
    return _guard(_do)


def analyze_gap(keyword, gaps):
    """分析了一个方向的文献空白。这代表在认真推进这个方向。"""
    kw = str(keyword or "").strip()
    return _guard(lambda: _pm().bump_pref(FIELDS, kw, delta=1.0)) if kw else False


def note(text, tags=None, kind="daily", source="", ref=""):
    """一条自由记忆（组会、卡点、决定、收藏）。"""
    text = str(text or "").strip()
    if not text:
        return False
    return _guard(lambda: _pm().remember(text, tags=tags or [], kind=kind,
                                         ref=ref, source=source))


def state(**kw):
    """更新当前状态（紧迫度 / 兴趣 / 心境）。"""
    return _guard(lambda: _pm().set_state(**kw))


def constraints(**kw):
    return _guard(lambda: _pm().set_constraints(**kw))


def learn_ideas(ideas):
    """把选题库里已有的条目折算成偏好。

    `profile_memory.learn_from_ideas()` 写好了但**从来没有被调用**过 ——
    用户在选题库里存了十几条，画像却当成什么都没发生。
    这个函数在选题库变化时调用一次即可（它是幂等的，看的是条目内容不是次数）。
    """
    ideas = list(ideas or [])
    if not ideas:
        return False
    return _guard(lambda: _pm().learn_from_ideas(ideas))


# ---------------------------------------------------------------- 状态查询
def stats():
    with _lock:
        return dict(_stats)


def reset_stats():
    with _lock:
        _stats.update({"ok": 0, "fail": 0, "last_error": ""})


def health():
    """画像是否真的在积累 —— 界面和自检都用这个，而不是猜。"""
    try:
        PM = _pm()
        st = PM.stats()
        s = stats()
        return {
            "exists": st.get("exists"),
            "anchors": st.get("anchors", 0),
            "fields": st.get("pref_fields", 0),
            "categories": st.get("pref_categories", 0),
            "identity_filled": st.get("identity_filled", 0),
            "identity_total": st.get("identity_total", 0),
            "constraints_set": any(v for v in (PM.constraints() or {}).values()),
            "record_ok": s["ok"],
            "record_fail": s["fail"],
            "last_error": s["last_error"],
            "active": bool(st.get("anchors") or st.get("pref_fields")
                           or st.get("pref_categories")),
        }
    except Exception as exc:
        return {"active": False, "error": "%s: %s" % (type(exc).__name__, exc)}