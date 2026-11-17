#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个人研究计划：阶段、截止、待办、周投入。

为什么单独一个数据文件而不是塞进 research_memory.json
----------------------------------------------------
计划是「用户手写、按天变动」的东西，而 research_memory.json 是台账
（选题、方向），两者写入频率和语义都不同。更重要的是：**计划文件损坏
不能让台账跟着丢**。所以计划走自己的 `research_plan.json`，读失败就
当成空计划继续跑。

记录粒度（用户 2026-11-15 明确要的四项）
----------------------------------------
  stage     阶段 + 截止日期（如「最小验证 · 2026-12-31」）
  todo      待办条目，可勾选，可挂到某个阶段下
  links     和某条选题 / 某个研究方向挂钩
  weekly    每周投入小时数（用来算「这周还剩几小时」）

设计上刻意**不做**的两件事
--------------------------
1. 不给你算「你应该几天做完」——没有真实工期数据，算出来就是编的。
   剩余天数只按你自己填的截止日期直接减，过期的就标红。
2. 不自动往计划里塞任务。选题工坊、文献空白给出的是建议，
   要不要变成待办由你点「加到计划」决定。

文件格式
--------
```json
{
  "version": 1,
  "stages": [
    {"id": "s1", "name": "开题", "due": "2026-12-31", "done": false,
     "note": "", "link": {"type": "field", "value": "红外小目标检测"}}
  ],
  "todos": [
    {"id": "t1", "text": "跑通基线", "done": false, "stage": "s1",
     "due": "2026-12-10", "link": {"type": "idea", "value": "..."}}
  ],
  "weekly": {"hours": 10, "week_start": "2026-11-10"}
}
```
`weekly.hours` 是每周总投入；`week_start` 表示「从这一周算起」，
统计这周还剩多少小时时不看日期，只看本周勾掉了多少条。
"""
import json
import os
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "research_plan.json"

VERSION = 1

# 阶段默认名：第一次打开计划页时给一串可改的建议，不让用户对着空白发呆。
# 这几步对应科研流程，但**不是硬性模板** —— 用户可以直接改名或删掉。
DEFAULT_STAGES = (
    ("读文献 · 摸清现状", 14),
    ("定题 · 能一句话说清要做什么", 21),
    ("最小验证 · 跑通一个能出数的实验", 30),
    ("完整实验 · 把消融补齐", 45),
    ("写稿 · 先出骨架再填内容", 30),
)


# ---------------------------------------------------------------- 基础读写
def _empty():
    return {"version": VERSION, "stages": [], "todos": [],
            "weekly": {"hours": 0, "week_start": _week_start()}, "created": _now()}


def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def _today():
    return date.today()


def _week_start():
    """本周一（ISO 周的起点）。"""
    d = _today()
    return (d - timedelta(days=d.weekday())).isoformat()


def _nid(prefix):
    return "%s%s" % (prefix, uuid.uuid4().hex[:8])


def _as_date(s):
    """把 'YYYY-MM-DD' 解析成 date；解析不了返回 None（不抛）。"""
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _clean(obj):
    """把从磁盘读到的东西修成可信的形状。

    原则：**能救的救，救不了的丢掉，绝不抛异常**。计划文件是手写 JSON，
    用户手改出一个逗号错位是常事，不能因此让整个计划页打不开。
    """
    if not isinstance(obj, dict):
        return _empty()
    out = _empty()
    out.pop("created", None)

    stages = obj.get("stages")
    if isinstance(stages, list):
        seen = set()
        for s in stages:
            if not isinstance(s, dict):
                continue
            name = str(s.get("name") or "").strip()
            if not name:
                continue
            sid = str(s.get("id") or "") or _nid("s")
            while sid in seen:
                sid = _nid("s")
            seen.add(sid)
            link = s.get("link")
            out["stages"].append({
                "id": sid,
                "name": name[:80],
                "due": str(s.get("due") or "")[:10],
                "done": bool(s.get("done")),
                "note": str(s.get("note") or "")[:400],
                "link": link if isinstance(link, dict) else None,
            })

    todos = obj.get("todos")
    if isinstance(todos, list):
        seen = set()
        for t in todos:
            if not isinstance(t, dict):
                continue
            text = str(t.get("text") or "").strip()
            if not text:
                continue
            tid = str(t.get("id") or "") or _nid("t")
            while tid in seen:
                tid = _nid("t")
            seen.add(tid)
            link = t.get("link")
            out["todos"].append({
                "id": tid,
                "text": text[:200],
                "done": bool(t.get("done")),
                "stage": str(t.get("stage") or ""),
                "due": str(t.get("due") or "")[:10],
                "link": link if isinstance(link, dict) else None,
            })

    wk = obj.get("weekly")
    if isinstance(wk, dict):
        try:
            hours = float(wk.get("hours") or 0)
        except Exception:
            hours = 0.0
        out["weekly"] = {"hours": max(0.0, min(hours, 168.0)),
                         "week_start": str(wk.get("week_start") or _week_start())[:10]}
    return out


def load():
    """读计划。文件不存在 → 返回空计划（**不自动创建**，避免用户什么都没做
    就先落一个空文件，之后分不清是「没建过」还是「建过又清空了」）。"""
    try:
        raw = PLAN_FILE.read_text(encoding="utf-8")
    except Exception:
        return _empty()
    try:
        return _clean(json.loads(raw))
    except Exception:
        # 损坏的文件不覆盖、不删除：留一份 .bad 副本，下一次 save 才写新文件。
        try:
            bad = PLAN_FILE.with_suffix(".json.bad")
            bad.write_text(raw, encoding="utf-8")
        except Exception:
            pass
        return _empty()


def save(plan):
    """写盘。先写临时文件再替换，避免写到一半断电留下半截 JSON。"""
    data = _clean(plan)
    data["version"] = VERSION
    txt = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = PLAN_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(txt, encoding="utf-8")
        os.replace(str(tmp), str(PLAN_FILE))
    except Exception:
        # 替换失败退回直接写（比如跨卷或权限怪的时候）
        PLAN_FILE.write_text(txt, encoding="utf-8")
    return data


def exists():
    return PLAN_FILE.exists()


# ---------------------------------------------------------------- 阶段
def add_stage(name, due="", note="", link=None):
    plan = load()
    sid = _nid("s")
    plan["stages"].append({"id": sid, "name": str(name)[:80], "due": str(due)[:10],
                           "done": False, "note": str(note)[:400], "link": link})
    save(plan)
    return sid


def update_stage(sid, **kw):
    plan = load()
    for s in plan["stages"]:
        if s["id"] == sid:
            for k in ("name", "due", "note", "done", "link"):
                if k in kw:
                    s[k] = kw[k]
            break
    save(plan)
    return plan


def remove_stage(sid):
    """删阶段时**不连带删待办**，只把待办的 stage 置空 —— 待办是用户
    写下来的事，不该因为整理阶段顺序就消失。"""
    plan = load()
    plan["stages"] = [s for s in plan["stages"] if s["id"] != sid]
    for t in plan["todos"]:
        if t.get("stage") == sid:
            t["stage"] = ""
    save(plan)
    return plan


def seed_defaults():
    """第一次打开时铺一串建议阶段。已经用过的计划**不会**被覆盖。"""
    plan = load()
    if plan["stages"]:
        return plan
    base = _today()
    acc = 0
    for name, days in DEFAULT_STAGES:
        acc += days
        plan["stages"].append({
            "id": _nid("s"), "name": name,
            "due": (base + timedelta(days=acc)).isoformat(),
            "done": False, "note": "", "link": None,
        })
    return save(plan)


# ---------------------------------------------------------------- 待办
def add_todo(text, stage="", due="", link=None):
    plan = load()
    tid = _nid("t")
    plan["todos"].append({"id": tid, "text": str(text)[:200], "done": False,
                          "stage": stage or "", "due": str(due)[:10],
                          "link": link})
    save(plan)
    return tid


def toggle_todo(tid):
    plan = load()
    done = False
    for t in plan["todos"]:
        if t["id"] == tid:
            t["done"] = not t["done"]
            done = t["done"]
            break
    save(plan)
    return done


def set_todo(tid, **kw):
    plan = load()
    for t in plan["todos"]:
        if t["id"] == tid:
            for k in ("text", "done", "stage", "due", "link"):
                if k in kw:
                    t[k] = kw[k]
            break
    save(plan)
    return plan


def remove_todo(tid):
    plan = load()
    plan["todos"] = [t for t in plan["todos"] if t["id"] != tid]
    save(plan)
    return plan


# ---------------------------------------------------------------- 周投入
def set_weekly(hours):
    plan = load()
    try:
        h = float(hours)
    except Exception:
        h = 0.0
    plan["weekly"] = {"hours": max(0.0, min(h, 168.0)), "week_start": _week_start()}
    save(plan)
    return plan


def week_done(today=None):
    """本周已完成 / 总数。周界按 `week_start` 到最后勾选的时刻算不准，
    所以这里只看**当前仍存在的待办**的完成情况，不做历史归档 ——
    省掉一套「每周快照」的存储，也省掉「快照对不上」的困惑。"""
    plan = load()
    done = sum(1 for t in plan["todos"] if t.get("done"))
    total = len(plan["todos"])
    return done, total


# ---------------------------------------------------------------- 统计
def due_state(due, today=None):
    """返回 (状态, 天数)。状态：over 已过期 / soon 7 天内 / later / none 没填。

    这里**只做减法**，不预测工期 —— 见模块开头第 1 条。
    """
    d = _as_date(due)
    if not d:
        return "none", None
    t = today or _today()
    delta = (d - t).days
    if delta < 0:
        return "over", delta
    if delta <= 7:
        return "soon", delta
    return "later", delta


def progress(today=None):
    """给页面和总览用的一组数字。**不返回任何分数或评分**。"""
    plan = load()
    stages = plan["stages"]
    todos = plan["todos"]
    t = today or _today()

    s_done = sum(1 for s in stages if s.get("done"))
    t_done = sum(1 for s in todos if s.get("done"))

    # 最近一个未完成、且有截止日的阶段 = 「当前阶段」
    cur = None
    for s in stages:
        if s.get("done"):
            continue
        st, days = due_state(s.get("due"), t)
        if st == "none":
            continue
        cur = (s, st, days)
        break
    if cur is None:
        for s in stages:
            if not s.get("done"):
                cur = (s, "none", None)
                break

    overdue = [x for x in todos if not x.get("done")
               and due_state(x.get("due"), t)[0] == "over"]
    soon = [x for x in todos if not x.get("done")
            and due_state(x.get("due"), t)[0] == "soon"]

    wk = plan.get("weekly") or {}
    return {
        "stages_total": len(stages),
        "stages_done": s_done,
        "todos_total": len(todos),
        "todos_done": t_done,
        "todos_open": len(todos) - t_done,
        "current": cur[0] if cur else None,
        "current_state": cur[1] if cur else "none",
        "current_days": cur[2] if cur else None,
        "overdue": len(overdue),
        "soon": len(soon),
        "weekly_hours": wk.get("hours") or 0,
        "empty": not stages and not todos,
    }


def summary_line(today=None):
    """一行话，给总览页用。没有任何计划时返回空字符串 —— 绝不输出
    「暂无计划」这类占位文字去占版面。"""
    p = progress(today)
    if p["empty"]:
        return ""
    bits = []
    cur = p.get("current")
    if cur:
        st, days = p["current_state"], p["current_days"]
        if st == "over":
            bits.append("当前阶段「%s」已过期 %d 天" % (cur.get("name"), -days))
        elif st == "soon":
            bits.append("当前阶段「%s」还剩 %d 天" % (cur.get("name"), days))
        elif st == "later":
            bits.append("当前阶段「%s」还剩 %d 天" % (cur.get("name"), days))
        else:
            bits.append("当前阶段「%s」（没填截止日）" % cur.get("name"))
    if p["todos_total"]:
        bits.append("待办 %d/%d" % (p["todos_done"], p["todos_total"]))
    if p["overdue"]:
        bits.append("%d 条已过期" % p["overdue"])
    if p["weekly_hours"]:
        bits.append("每周 %g 小时" % p["weekly_hours"])
    return " · ".join(bits)


def upcoming(limit=3, today=None):
    """最近的几条未完成待办，按截止日排，没填日期的排最后。"""
    plan = load()
    t = today or _today()
    open_todos = [x for x in plan["todos"] if not x.get("done")]
    open_todos.sort(key=lambda x: (_as_date(x.get("due")) or date(2999, 1, 1)))
    return open_todos[:max(1, limit)]


# ---------------------------------------------------------------- 与其它模块的挂接
def link_of_idea(title):
    """给「选题」造一个 link 字典，形状与 research_plan.json 一致。"""
    return {"type": "idea", "value": str(title)[:80]}


def link_of_field(field):
    return {"type": "field", "value": str(field)[:80]}


def link_text(link):
    """link → 人能读的一小段。没有 link 返回空串。"""
    if not isinstance(link, dict):
        return ""
    v = str(link.get("value") or "").strip()
    if not v:
        return ""
    t = link.get("type")
    if t == "idea":
        return "选题：" + v
    if t == "field":
        return "方向：" + v
    return v


if __name__ == "__main__":
    p = load()
    print("计划文件：", PLAN_FILE, "存在" if exists() else "不存在")
    print(json.dumps(progress(), ensure_ascii=False, indent=2))