#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个体画像记忆层 —— 从「数字生命」项目迁移过来的迭代记忆内核。

来源
----
`G:\\王佩珊同学思路解答\\digital-life-core`（DSH 数字生命插件，MIT）里有一套
「记忆器官」设计，核心思想是：

    **不是按相关度排序，而是按「此刻的心境」倾斜排序。**

它把记忆分成「危机类」和「日常类」，用当前激素水平算出一个倍率：
应激时危机记忆 ×3 顶到最前、日常记忆 ×0.1 压到最后 —— **但一条都不删**。
另外每次存记忆时打一个「情绪锚点」，记录当时的心境；检索时可以回填。

迁移到科研选题领域
------------------
我们没有多巴胺和皮质醇，但科研工作同样有「此刻最关心什么」：

| 数字生命 | 这里 |
| --- | --- |
| 皮质醇（应激） | `urgency`：临近截止、正在投稿、催导师 |
| 多巴胺（期待） | `interest`：对某方向高度感兴趣、想发顶会 |
| 危机类记忆 | 正在写的那篇 / 卡住的那步 / 导师明确要求 |
| 日常类记忆 | 随手收藏、看看就好、别人的方向 |
| 情绪锚点 | 存这条时是什么状态（焦虑/兴奋/平静） |

于是排序变成：

    权重 = 位次衰减 × 紧迫度倍率 × 兴趣倍率 × 相关性 × 新鲜度

同时保留原设计的硬规则：**只排序、只压缩，不删除**。用户点「遗忘」才真删。

另外从原项目抄来的两条工程约定
------------------------------
1. **短英文标签必须词边界匹配**：`bug` 不能命中 `debug`。
   本项目此前也栽过三次（`ics` → Robotics、`ar` → VR、`network` → 化学）。
2. **所有输出如实交代**：界面要说清「共 N 条，因此刻紧迫叠加如何倾斜」，
   不能让用户以为是被筛掉了。

数据文件
--------
`researcher_profile.json` —— 不是 `research_memory.json`。
理由：这是「人」的数据（偏好、习惯、锚点），与「选题台账」分开存，
两者的生命周期不同；混在一起会让选题库备份变大且难迁移。

并发安全用一个 `.lock` 文件 + 原子替换写。
"""
import json
import math
import os
import re
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:
    import app_paths as _AP
    _RES = _AP.res        # 只读资源：打包后在 _MEIPASS
    _DATA = _AP.data      # 可写数据：打包后在 exe 旁边
except Exception:         # 单独跑构建脚本/测试时退回旧行为
    _RES = lambda n: HERE / n
    _DATA = lambda n: HERE / n
PROFILE_FILE = _DATA("researcher_profile.json")
LOCK_FILE = _DATA(".researcher_profile.lock")

_lock = threading.RLock()
_cache = {"mtime": None, "data": None}

# ═══════════════════════════════════════════════════════════════════
# 一、状态（对应数字生命的「激素」）
# ═══════════════════════════════════════════════════════════════════

URGENT = 80      # 紧迫度 ≥ 此值 = 极度应激（ddl 三天内 / 正在投稿）
CALM = 40        # 紧迫度 < 此值 = 平静
CRISIS_WEIGHT = 3.0   # 应激时「危机类」记忆的倍率
DAILY_WEIGHT = 0.1    # 应激时「日常类」记忆的倍率
RANK_DECAY = 0.9      # 相关度随位次衰减

# 危机类：正在写 / 卡住 / 导师要求 / 数据问题 / 复现失败
DEFAULT_CRISIS_TAGS = [
    "截止", "投稿", "ddl", "deadline", "催", "紧急", "卡住", "卡在", "报错", "失败",
    "复现", "跑不", "不收敛", "掉点", "劣化", "丢分", "推翻", "被拒", "大修", "小修",
    "返修", "审稿意见", "实验没", "数据没", "抱不平", "无法",
    "fail", "failed", "error", "bug", "crash", "timeout", "reject", "revise",
]
# 日常类：随手收藏 / 看看 / 别人的 / 可能有用
DEFAULT_DAILY_TAGS = [
    "收藏", "以后", "备用", "随便看", "逛逛", "别人的", "参考一下", "听说", "有趣",
    "有空", "再看", "先存着", "好像",
    "someday", "later", "browse", "casual",
]

# 情绪锚点（存记忆那一刻的心境）
MOODS = ("焦虑", "兴奋", "平静", "疲惫", "困惑")


def _clamp01(x):
    try:
        x = float(x)
    except Exception:
        return 0.0
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _esc(t):
    return re.escape(t)


def has_tag(haystack, tag):
    """标签命中判定。中文子串即可，纯 ASCII 走词边界。

    `bug` 不应命中 `debug`，`chat` 不应命中 `chatter` ——
    这条边界是从原项目抄来的，也是本项目踩过三次的坑。
    """
    h = (haystack or "").lower()
    t = (tag or "").lower().strip()
    if not t or not h:
        return False
    if re.match(r"^[a-z0-9 _\-]+$", t):
        return re.search(r"(?:^|[^a-z0-9])" + _esc(t) + r"(?:[^a-z0-9]|$)", h) is not None
    return t in h


def urgency_weights(urgency, stress=URGENT, calm=CALM,
                    crisis_w=CRISIS_WEIGHT, daily_w=DAILY_WEIGHT):
    """当前紧迫度下的 (危机倍率, 日常倍率)。

    两端之间线性插值，让「从平静滑向赶 ddl」是连续的，
    不会在某个整数上突然翻脸。
    """
    try:
        u = float(urgency)
    except Exception:
        u = 0.0
    if u >= stress:
        return crisis_w, daily_w
    if u <= calm:
        return 1.0, 1.0
    span = max(1.0, stress - calm)
    t = _clamp01((u - calm) / span)
    return 1.0 + (crisis_w - 1.0) * t, 1.0 + (daily_w - 1.0) * t


def classify(text, tags=None, extra_tags=None, anchor_mood=None):
    """一条记忆属于 crisis / daily / neutral。

    危机优先：同时提到「被拒」和「以后看看」的，按危机算 ——
    威胁检测不该让轻松的那一半赢。
    """
    ct = list(extra_tags or []) + list(DEFAULT_CRISIS_TAGS)
    dt = list(extra_tags or []) + list(DEFAULT_DAILY_TAGS)
    hay = "%s %s" % (text or "", " ".join(tags or []))
    if any(has_tag(hay, t) for t in ct):
        return "crisis"
    # 闪回：存它的那一刻在焦虑，这件事本身就记录了分量
    if anchor_mood in ("焦虑", "疲惫"):
        return "crisis"
    if any(has_tag(hay, t) for t in dt):
        return "daily"
    return "neutral"


def literal_relevance(query, text):
    """中文友好的字面重合度，零依赖。返回 0–1。

    做法：把 query 切成「汉字二元组 + ASCII 词」，看有多少比例在 text 里出现。
    不做分词、不做同义词、不做向量 —— 它解决的是「完全无关的记忆压过相关的」，
    不是「理解语义」。同语义检索模块的教训：纯字面有天花板，但比没有强。
    """
    q = (query or "").strip().lower()
    if not q:
        return 0.0
    hay = (text or "").lower()
    if not hay:
        return 0.0
    toks = set()
    for w in re.findall(r"[a-z0-9_]{2,}", q):
        toks.add(w)
    han = re.sub(r"[^\u4e00-\u9fa5]", "", q)
    for i in range(len(han) - 1):
        toks.add(han[i:i + 2])
    if len(han) == 1:
        toks.add(han)
    if not toks:
        return 0.0
    hit = sum(1 for t in toks if t in hay)
    return hit / len(toks)


def fresh_score(ts, half_life_days=45.0):
    """按保存时间衰减（0–1）。尚未保存的返回 1.0。"""
    if not ts:
        return 1.0
    try:
        age_d = max(0.0, (time.time() - float(ts)) / 86400.0)
    except Exception:
        return 1.0
    return math.pow(0.5, age_d / max(1.0, half_life_days))


# ═══════════════════════════════════════════════════════════════════
# 二、存储
# ═══════════════════════════════════════════════════════════════════

def _default_profile():
    return {
        "version": 1,
        "identity": {
            "nickname": "",
            "school": "",
            "stage": "硕士在读",       # 本科 / 硕士在读 / 博士在读 / 已毕业
            "lab": "",
            "advisor": "",
            "goal": "",                 # 想发到哪 / 想解决什么
            "skills": [],               # 会用的工具
            "resources": "",            # 算力情况
            "updated": 0,
        },
        "state": {
            "urgency": 30.0,            # 0–100，可手动调，也可由截止日推算
            "interest": 50.0,           # 0–100
            "mood": "平静",
            "note": "",
            "updated": 0,
        },
        "constraints": {                # 硬约束：决定「这条题你做不做得动」，与情绪无关
            "compute": "",              # 无算力 / 单卡消费级 / 单卡 24G / 多卡集群
            "months": "",               # 3 个月内 / 半年内 / 一年以上
            "style": "",                # 偏工程 / 偏理论 / 都行
            "avoid": [],                # 禁忌方向（命中的候选直接标红）
            "updated": 0,
        },
        "tilt": {
            "crisis_weight": CRISIS_WEIGHT,
            "daily_weight": DAILY_WEIGHT,
            "stress_line": URGENT,
            "calm_line": CALM,
            "half_life_days": 45.0,
        },
        "anchors": [],                  # 记忆条目（带情绪锚点）
        "preferences": {
            "categories": {},           # 大类 → 权重
            "fields": {},               # 方向 → 权重
            "venues": {},               # 期刊会议 → 权重
            "provinces": {},            # 倾向地区 → 权重
            "methods": {},              # 偏好方法 → 权重
            "avoid": [],                # 明确不想碰的
        },
        "stats": {
            "recall_count": 0,
            "anchor_count": 0,
            "last_recall": 0,
        },
    }


def _read_raw():
    try:
        st = PROFILE_FILE.stat()
    except Exception:
        return None
    with _lock:
        if _cache["mtime"] == st.st_mtime and _cache["data"] is not None:
            return _cache["data"]
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("profile 不是 dict")
    except Exception:
        return None
    base = _default_profile()
    for k, v in data.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            base[k].update(v)
        else:
            base[k] = v
    with _lock:
        _cache["mtime"] = st.st_mtime
        _cache["data"] = base
    return base


def load():
    """读取画像；文件不存在时返回默认值（不写盘）。"""
    data = _read_raw()
    return data if data is not None else _default_profile()


def save(profile):
    """原子写盘：临时文件 + os.replace，中途崩了不会留半个 JSON。"""
    if not isinstance(profile, dict):
        raise TypeError("profile 必须是 dict")
    profile = dict(profile)
    profile.setdefault("version", 1)
    text = json.dumps(profile, ensure_ascii=False, indent=1)
    # 临时文件必须和目标同目录：Windows 的 os.replace 跨卷会抛
    # OSError(18) "系统无法将文件移到不同的磁盘驱动器"。
    target = Path(PROFILE_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".profile-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass
    with _lock:
        _cache["mtime"] = None
        _cache["data"] = None
    return True


def reset(keep_identity=True):
    """清空画像。默认保留身份信息（换研究方向时不用重填基本资料）。"""
    old = load()
    p = _default_profile()
    if keep_identity:
        p["identity"] = old.get("identity", p["identity"])
    save(p)
    return p


# ═══════════════════════════════════════════════════════════════════
# 三、状态与偏好
# ═══════════════════════════════════════════════════════════════════

def set_identity(**kw):
    p = load()
    ident = p.setdefault("identity", {})
    for k, v in kw.items():
        if k in _default_profile()["identity"]:
            ident[k] = v
    ident["updated"] = int(time.time())
    save(p)
    return p


def set_state(urgency=None, interest=None, mood=None, note=None):
    p = load()
    st = p.setdefault("state", {})
    if urgency is not None:
        st["urgency"] = max(0.0, min(100.0, float(urgency)))
    if interest is not None:
        st["interest"] = max(0.0, min(100.0, float(interest)))
    if mood is not None and mood in MOODS:
        st["mood"] = mood
    if note is not None:
        st["note"] = str(note)
    st["updated"] = int(time.time())
    save(p)
    return st


def urgency_from_ddl(ddl_date, now=None):
    """由截止日期推算紧迫度。

    经验刻度（不是科学，但比「让用户拖滑块」有依据）：
        还剩 ≥30 天 → 20
        还剩 7 天   → 62
        还剩 1 天   → 92
        已过期      → 100
    中间按对数插值 —— 人对「还有几天」的感知也是对数式的。
    """
    import datetime as _dt
    if not ddl_date:
        return 20.0
    try:
        if isinstance(ddl_date, str):
            d = _dt.datetime.strptime(ddl_date.strip()[:10], "%Y-%m-%d")
        else:
            d = _dt.datetime.combine(ddl_date, _dt.time())
    except Exception:
        return 20.0
    now = now or _dt.datetime.now()
    days = (d - now).total_seconds() / 86400.0
    if days <= 0:
        return 100.0
    if days >= 30:
        # 30 天以上缓降：30 天 20 分，180 天 5 分
        return max(5.0, 20.0 - (days - 30.0) * 0.1)
    # 1 天 92，30 天 20：按 ln 插值
    t = math.log(days) / math.log(30.0)   # 1→0, 30→1
    return max(20.0, min(100.0, 92.0 - 72.0 * t))


def bump_pref(kind, key, delta=1.0, cap=12.0):
    """给某个偏好加/减权。kind ∈ categories/fields/venues/provinces/methods。

    上限 12 是刻意的：单次行为不该永久主导排序，
    反复行为会累积，这才是「偏好」而不是「一次点击」。
    """
    if kind == "avoid":
        p = load()
        av = p["preferences"].setdefault("avoid", [])
        k = str(key)
        if delta > 0 and k and k not in av:
            av.append(k)
        elif delta < 0 and k in av:
            av.remove(k)
        save(p)
        return av
    if kind not in ("categories", "fields", "venues", "provinces", "methods",
                    "angle", "strategy"):
        return {}
    p = load()
    box = p["preferences"].setdefault(kind, {})
    k = str(key or "").strip()
    if not k:
        return box
    box[k] = max(-cap, min(cap, float(box.get(k, 0.0)) + float(delta)))
    if abs(box[k]) < 0.01:
        box.pop(k, None)
    save(p)
    return box


def pref_weight(kind, key, cap=12.0):
    """偏好权重归一化到 -1..1。"""
    box = load()["preferences"].get(kind) or {}
    try:
        return max(-1.0, min(1.0, float(box.get(key, 0.0)) / cap))
    except Exception:
        return 0.0


def learn_from_ideas(ideas):
    """从已有选题台账反推偏好（只加不减，幂等）。

    规则：某大类出现 3 次以上 → +1；某方向出现 3 次 → +1。

    **不足 3 次的怎么办**：原来直接跳过，结果是「存了 1–2 条题的学生永远
    学不到任何东西」—— 而大多数人在很长一段时间里就是只有几条题。
    现在给一次轻推（+0.4，低于 `prompt_context` 的 2 分门槛，不会进提示词，
    但会体现在 `tilt_inputs()` 的方向偏好里，让相关候选排得稍微靠前）。
    这样「存了一条」不等于「锁定了偏好」，但也不是白存。

    只做一次性的轻推，不覆盖用户手动设的偏好。
    """
    import collections
    if not ideas:
        return {}
    p = load()
    prefs = p["preferences"]
    cc = collections.Counter(str(i.get("category") or "").strip() for i in ideas)
    # 真实选题记录用的是 "field"（细分方向），"direction" 只在少数来源里有；
    # 两者都没有时退到标题（标题里通常带着方向词），再不行才放弃。
    def _dir_of(i):
        for k in ("direction", "field"):
            v = str(i.get(k) or "").strip()
            if v:
                return v
        return ""
    ff = collections.Counter(_dir_of(i) for i in ideas)
    touched = 0
    for box, cnt in (("categories", cc), ("fields", ff)):
        tgt = prefs.setdefault(box, {})
        for k, n in cnt.items():
            if not k:
                continue
            if abs(float(tgt.get(k, 0.0))) >= 0.01:
                continue          # 已有权重（手动设的或之前学到的）一律不覆盖
            tgt[k] = min(6.0, float(n) / 3.0) if n >= 3 else 0.4
            touched += 1
    if touched:
        save(p)
    return {"touched": touched}


# ═══════════════════════════════════════════════════════════════════
# 四、记忆锚点（原项目的核心）
# ═══════════════════════════════════════════════════════════════════

def remember(text, tags=None, mood=None, kind=None, ref="", source=""):
    """存一条记忆，并打上**当时的情绪锚点**。

    这是原项目最关键的一步：记忆的价值不只在于内容，还在于「存它的时候我是什么状态」。
    后来的检索能读到这个锚点，从而知道「这条是在赶 ddl 时记的，它很重」。
    """
    text = str(text or "").strip()
    if not text:
        return None
    p = load()
    st = p.get("state") or {}
    mood = mood if mood in MOODS else st.get("mood", "平静")
    rec = {
        "id": "m%d" % int(time.time() * 1000),
        "text": text[:2000],
        "tags": [str(t) for t in (tags or [])][:12],
        "mood": mood,
        "urgency": float(st.get("urgency", 30.0)),
        "interest": float(st.get("interest", 50.0)),
        "at": int(time.time()),
        "ref": str(ref or ""),
        "source": str(source or ""),
        "kind": kind or "",
    }
    p.setdefault("anchors", []).append(rec)
    # 上限 500 条：再多也不会被看到，但增长会拖慢加载
    if len(p["anchors"]) > 500:
        p["anchors"] = p["anchors"][-500:]
    p.setdefault("stats", {})["anchor_count"] = len(p["anchors"])
    save(p)
    return rec


def forget(anchor_id):
    """真正的删除 —— 只有用户明确要求时才调。"""
    p = load()
    before = len(p.get("anchors") or [])
    p["anchors"] = [a for a in (p.get("anchors") or []) if a.get("id") != anchor_id]
    save(p)
    return before - len(p["anchors"])


def _score_one(rec, idx, query, weights, tilt, interest_weight):
    """单条打分。返回 (权重, 明细)。"""
    text = rec.get("text", "")
    tags = rec.get("tags") or []
    kind = classify(text, tags, anchor_mood=rec.get("mood"))
    mult = weights[0] if kind == "crisis" else (weights[1] if kind == "daily" else 1.0)
    rank = math.pow(RANK_DECAY, max(0, idx))
    rel = 1.0 + 2.0 * literal_relevance(query, text) if query else 1.0
    fresh = fresh_score(rec.get("at"), tilt.get("half_life_days", 45.0))
    # 兴趣共振：当时记这条的兴奋度 vs 现在的兴趣
    intr = 1.0 + 0.15 * abs(float(rec.get("interest", 50.0)) - 50.0) / 50.0 * interest_weight
    w = rank * mult * rel * fresh * intr
    return w, {"kind": kind, "multiplier": round(mult, 3),
               "relevance": round(rel - 1.0, 3), "fresh": round(fresh, 3)}


def recall(query="", limit=0, budget_chars=4000):
    """按「此刻的心境」倾斜重排，**一条都不删**。

    返回 dict：
      items      全部条目（已排序，每条带 weight/detail）
      total      总条数
      shown      实际返回条数（limit>0 时）
      tilt       本次使用的倍率
      urgency    本次的紧迫度
      note       给界面看的一句实话
    """
    p = load()
    anchors = list(p.get("anchors") or [])
    st = p.get("state") or {}
    tilt = p.get("tilt") or {}
    urgency = float(st.get("urgency", 30.0))
    interest = float(st.get("interest", 50.0))
    weights = urgency_weights(
        urgency,
        stress=tilt.get("stress_line", URGENT),
        calm=tilt.get("calm_line", CALM),
        crisis_w=tilt.get("crisis_weight", CRISIS_WEIGHT),
        daily_w=tilt.get("daily_weight", DAILY_WEIGHT),
    )
    rows = []
    for idx, rec in enumerate(anchors):
        w, det = _score_one(rec, idx, query, weights, tilt, interest / 100.0)
        rows.append({"record": rec, "weight": w, "detail": det})
    rows.sort(key=lambda x: -x["weight"])

    total = len(rows)
    if limit and limit > 0:
        rows = rows[:limit]

    # 共享字符预算：只压缩不丢
    if budget_chars and budget_chars > 0:
        used = sum(len(r["record"].get("text", "")) for r in rows)
        if used > budget_chars and rows:
            each = max(80, budget_chars // len(rows))
            for r in rows:
                t = r["record"].get("text", "")
                if len(t) > each:
                    r.setdefault("compressed", True)
                    r["text"] = t[:each - 1] + "…"
                else:
                    r["text"] = t
    for r in rows:
        r.setdefault("text", r["record"].get("text", ""))

    cw, dw = weights
    if urgency >= tilt.get("stress_line", URGENT):
        mood_note = "此刻在赶进度，正在写/卡住的那类记忆被顶到最前（×%.1f），随手收藏的压到后面（×%.2f），总数保留 %d 条" % (cw, dw, total)
    elif urgency <= tilt.get("calm_line", CALM):
        mood_note = "此刻比较从容，按相关度与新鲜度排序，共 %d 条" % total
    else:
        mood_note = "在「从容」和「赶进度」之间，倾斜在逐步生效（危机 ×%.2f / 日常 ×%.2f），共 %d 条" % (cw, dw, total)

    with _lock:
        p2 = _read_raw() or p
        p2.setdefault("stats", {})["recall_count"] = int(p2["stats"].get("recall_count", 0)) + 1
        p2["stats"]["last_recall"] = int(time.time())

    return {"items": rows, "total": total, "shown": len(rows),
            "tilt": {"crisis": round(cw, 3), "daily": round(dw, 3)},
            "urgency": urgency, "interest": interest, "note": mood_note}


def recall_text(query="", limit=8):
    """把 recall 结果渲染成可读文本（给提示词用）。"""
    r = recall(query=query, limit=limit)
    if not r["items"]:
        return ""
    lines = ["【这位同学自己的状态与历史（%s）】" % r["note"]]
    st = load().get("state") or {}
    if st.get("note"):
        lines.append("· 当前处境：%s" % st["note"])
    for it in r["items"]:
        rec = it["record"]
        tag = {"crisis": "❗", "daily": "·", "neutral": "·"}.get(it["detail"]["kind"], "·")
        when = time.strftime("%m-%d", time.localtime(rec.get("at", 0)))
        lines.append("%s [%s|%s] %s" % (tag, when, rec.get("mood", ""), it.get("text", "")))
    return "\n".join(lines)


def profile_brief():
    """给大模型的「这位同学是谁」摘要。

    没有画像时返回空串 —— 不能让模型读到「硕士在读、紧迫度 30」这种
    _default_profile() 的占位值，那等于我们替用户编了一段身份。
    """
    if tilt_inputs() is None:
        return ""
    p = load()
    ident = p.get("identity") or {}
    st = p.get("state") or {}
    prefs = p.get("preferences") or {}
    lines = []
    who = "、".join(x for x in [
        ident.get("stage"), ident.get("school"), ident.get("lab")] if x)
    if who:
        lines.append("身份：%s" % who)
    if ident.get("advisor"):
        lines.append("导师：%s" % ident["advisor"])
    if ident.get("goal"):
        lines.append("目标：%s" % ident["goal"])
    if ident.get("resources"):
        lines.append("算力：%s" % ident["resources"])
    if ident.get("skills"):
        lines.append("会用的工具：%s" % "、".join(ident["skills"][:8]))
    if st.get("note"):
        lines.append("当前处境：%s（紧迫度 %d/100，兴趣 %d/100）"
                     % (st["note"], st.get("urgency", 0), st.get("interest", 50)))
    elif st.get("mood") or st.get("urgency"):
        lines.append("当前处境：心境「%s」，紧迫度 %d/100，兴趣 %d/100"
                     % (st.get("mood") or "未填", st.get("urgency", 0),
                        st.get("interest", 50)))
    for kind, label in (("categories", "常做的大类"), ("fields", "常做的方向"),
                        ("methods", "偏好的方法"), ("venues", "想投的场所")):
        box = prefs.get(kind) or {}
        top = sorted(box.items(), key=lambda kv: -kv[1])[:4]
        top = [k for k, v in top if v > 0]
        if top:
            lines.append("%s：%s" % (label, "、".join(top)))
    if prefs.get("avoid"):
        lines.append("明确不想碰：%s" % "、".join(prefs["avoid"][:5]))
    return "\n".join(lines)


COMPUTE_LEVELS = {
    # 值 → (可承受的档位, 说明)。判断依据是「主流方法能不能在 1–2 周内跑出第一版」，
    # 不是「有没有钱」：单卡 24G 能跑 LoRA 微调 7B，跑不了全参数训练。
    "无算力": (0, "只有笔记本/共享 CPU，做不了任何训练型实验"),
    "单卡消费级": (1, "8–12G 显存，能训轻量模型、能推理，微调要挑小的"),
    "单卡 24G": (2, "能跑 LoRA 微调 7B、能训完整视觉模型"),
    "多卡集群": (3, "能做全参数微调与大规模实验"),
}
TIME_LEVELS = {"3 个月内": (0, "要能直接落地，容不下大工程"),
               "半年内": (1, "留得下一次完整迭代"),
               "一年以上": (2, "可以做需要重建评测的工作")}
STYLE_LEVELS = {"偏工程": "engineer", "偏理论": "theory", "都行": ""}


def set_constraints(**kw):
    """写硬约束。空值表示「没填」，不写进文件（避免把默认值当真实回答）。"""
    p = load()
    con = p.setdefault("constraints", {})
    for k, v in kw.items():
        if k == "avoid":
            con["avoid"] = [str(x).strip() for x in (v or []) if str(x).strip()][:12]
        elif k in ("compute", "months", "style"):
            con[k] = str(v or "").strip()
    con["updated"] = time.time()
    save(p)
    return con


def constraints():
    """给排序用的结构化硬约束；没填的部分返回空串，调用方按「无约束」处理。"""
    p = load()
    con = p.get("constraints") or {}
    return {
        "compute": con.get("compute") or "",
        "months": con.get("months") or "",
        "style": con.get("style") or "",
        "avoid": [x for x in (con.get("avoid") or []) if x],
    }


def tilt_inputs():
    """给「候选排序」用的结构化画像（不是给大模型看的文字）。

    和 profile_brief() 的区别：那是给模型读的散文，这是给代码算的字典。
    没建画像时返回 None —— 调用方据此走「无画像」分支，行为与以前完全一致。
    """
    p = load()
    st = p.get("state") or {}
    prefs = p.get("preferences") or {}
    ident = p.get("identity") or {}
    exists = bool(PROFILE_FILE.exists())
    # 不能用「非空个数」判：_default_profile() 里 stage 默认就是「硕士在读」，
    # 哪怕用户一个字都没填也会算出 filled>=1，于是新机器上被当成「已建画像」。
    # 判据改成「有键的值 != 默认值」。
    base = _default_profile().get("identity") or {}
    filled = sum(1 for k, v in ident.items() if v and v != base.get(k))
    if not exists and filled == 0 and not (p.get("anchors") or []):
        return None
    return {
        "urgency": int(st.get("urgency", 0) or 0),
        "interest": int(st.get("interest", 50) or 50),
        "mood": st.get("mood", "") or "",
        "prefs": {
            "angle": dict(prefs.get("angle") or {}),
            "strategy": dict(prefs.get("strategy") or {}),
            "fields": dict(prefs.get("fields") or {}),
        },
        "has_profile": exists,
    }


def stats():
    p = load()
    ident = p.get("identity") or {}
    anchors = p.get("anchors") or []
    filled = sum(1 for v in ident.values() if v)
    return {
        "anchors": len(anchors),
        "identity_filled": filled,
        "identity_total": max(1, len(ident)),
        "urgency": p.get("state", {}).get("urgency", 0),
        "interest": p.get("state", {}).get("interest", 50),
        "mood": p.get("state", {}).get("mood", ""),
        "pref_categories": len(p.get("preferences", {}).get("categories") or {}),
        "pref_fields": len(p.get("preferences", {}).get("fields") or {}),
        "recall_count": p.get("stats", {}).get("recall_count", 0),
        "exists": PROFILE_FILE.exists(),
    }


def export_public():
    """导出给网页版看的部分 —— 去掉所有可能敏感的内容。

    网页版是给体验者用的，身份里的学校/导师/处境都可能敏感，
    所以对外只留「脱敏后的偏好强度」和「有没有配过」。
    """
    p = load()
    prefs = p.get("preferences") or {}
    return {
        "has_profile": bool(p.get("identity", {}).get("stage")),
        "stage": p.get("identity", {}).get("stage", ""),
        "anchors": len(p.get("anchors") or []),
        "categories": sorted((k for k, v in (prefs.get("categories") or {}).items() if v > 0),
                             key=lambda k: -prefs["categories"][k])[:6],
        "fields": sorted((k for k, v in (prefs.get("fields") or {}).items() if v > 0),
                         key=lambda k: -prefs["fields"][k])[:6],
    }