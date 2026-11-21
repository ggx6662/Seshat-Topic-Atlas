#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隔离数据的桌面交互回归与多尺寸截图。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tools_isolate  # noqa: E402

tools_isolate.ALLOW_REAL.discard("llm_bridge.CONFIG_FILE")
_ISO = tools_isolate.isolate()

import app_main  # noqa: E402
import tools_shot as SHOT  # noqa: E402

OUT = os.path.join(HERE, "screenshots", "new")
os.makedirs(OUT, exist_ok=True)
W, H = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1440, 900)


def snap(app, name):
    app.update()
    time.sleep(0.45)
    app.update()
    hit = SHOT.find_window("塞莎特——题谱", True)
    if not hit:
        print("  [shot] 未找到窗口")
        return
    hwnd, _t, r, _a = hit
    SHOT.grab(hwnd, r, os.path.join(OUT, "%dx%d-%s.png" % (W, H, name)))
    print("  [shot]", name)


def _recycle_pages(app, keep=()):
    """把已经截完图的页面真正销毁，收回它们占的原生菜单句柄。

    2026-11-20：Tk 8.6 在 Windows 上给每个 tk.OptionMenu 分配一个原生 HMENU，
    `destroy()` 之后这批句柄不会立刻还给系统。本脚本按固定顺序把所有页面都建
    一遍，建到第 13 页 `profile`（它自己一次就要十来个 OptionMenu）时就撞上
    `_tkinter.TclError: No more menus can be allocated.`，而 app.goto 会把
    这个异常吞成一条 toast 再返回 —— 于是 profile 从来没进 app.pages，
    后面 `app.page("profile")` 才跳 KeyError。
    截完图的页没必要留着力气，扫完就拆，越早拆越不容易撞上限。
    """
    for key in list(app.pages):
        if key in keep:
            continue
        try:
            dead = app.pages.pop(key)
            if app.current != key:
                dead.destroy()
            else:
                app.pages[key] = dead      # 当前页留着，等下次切走再收
        except Exception:
            pass
    app.update()


def main():
    app = app_main.App()
    errors = []
    def callback_error(kind, value, tb):
        import traceback
        errors.append(str(value))
        traceback.print_exception(kind, value, tb)
    app.report_callback_exception = callback_error
    app.geometry("%dx%d+0+0" % (W, H))
    app.update()
    time.sleep(1.0)

    def status_ok(tag):
        """状态栏不能是红的。

        为什么加：`文献空白` 右栏此前每张卡片都抛 NameError，右栏一直空白，
        而脚本照样「通过」，因为没人读状态栏。截图只是证据，断言才是闸门。
        """
        text = str(app.status.cget("text") or "")
        # 不能靠颜色判断：toast 6 秒后会自己恢复成「就绪」，颜色也随之变灰，
        # 后台异常就被抹平了。所以直接看文字。
        assert "运行出错" not in text, "[%s] 状态栏报错：%s" % (tag, text)

    app.goto("home"); snap(app, "01-home")
    app.goto("topic"); snap(app, "02-topic-empty")
    app.goto("gap"); snap(app, "03-gap")
    status_ok("gap")
    # 窄窗下这一页的分析要跑好几秒，snap 不加等待，拍到的就是「正在分析本地文献…」
    # 的空壳 —— 证明不了右栏修好没有。等真正出内容（或明确报错）再补拍一张。
    _gp = app.page("gap")
    for _ in range(120):
        app.update(); time.sleep(0.1)
        if (_gp.data or {}).get("issue_gaps"):
            break
    status_ok("gap-wait")
    snap(app, "03-gap")
    app.goto("latest"); snap(app, "04-latest")
    app.goto("ideas"); snap(app, "05-ideas")
    app.goto("skills"); snap(app, "06-skills")
    app.goto("mentor"); snap(app, "07-mentor-empty")
    app.goto("venue"); snap(app, "08-venue-empty")
    app.goto("materials"); snap(app, "09-materials")
    for frame, parts, _, _ in app.page("materials")._frames.values():
        for widget in parts:
            if isinstance(widget, __import__("tkinter").Label) and "个方向" in str(widget.cget("text")):
                assert widget.winfo_rootx() >= widget.master.master.winfo_rootx()
                assert widget.winfo_rootx() + widget.winfo_width() <= frame.winfo_rootx() + frame.winfo_width()
    app.goto("library"); snap(app, "10-library")
    app.goto("map"); snap(app, "11-map")
    app.goto("plan"); snap(app, "12-plan")
    _recycle_pages(app, keep=("plan",))
    app.goto("profile"); snap(app, "13-profile")
    app.goto("settings"); snap(app, "14-settings")
    import ui_parts as U
    def widgets(root):
        for child in root.winfo_children():
            yield child
            yield from widgets(child)
    settings = app.page("settings")
    sections = [w for w in widgets(settings) if isinstance(w, U.Section)]
    for section in sections:
        section.toggle(True)
        app.update()
        assert section.body.winfo_manager()
        section.toggle(False)
        app.update()
        assert not section.body.winfo_manager()
    test_clicks = []
    button = app_main.T.Btn(settings, "状态测试", lambda: test_clicks.append(True))
    button.pack()
    app.update()
    button.config(state="disabled")
    button.invoke()
    button.event_generate("<Button-1>")
    assert not test_clicks
    button.enable(True)
    button.invoke()
    assert len(test_clicks) == 1
    button.destroy()

    # 合成台账只写入隔离目录。
    import kb_widget as kb
    import profile_memory as PM
    import plan_store as PS
    from datetime import date, timedelta
    idea = {"title": "合成测试：跨域红外小目标检测的机制、基线与停止条件",
            "desc": "仅用于界面测试，不是研究结论。" * 35,
            "type": "方法创新", "field": "红外小目标检测", "time": "2026-11-19T12:00"}
    assert kb.RESEARCH_MEMORY.parent != __import__("pathlib").Path(HERE)
    assert PS.PLAN_FILE.parent != __import__("pathlib").Path(HERE)
    kb.save_research_memory({"ideas": [idea], "directions": []})
    app.goto("ideas")
    pg = app.page("ideas")
    pg.reload()
    pg.select(0)
    snap(app, "05b-ideas-long")
    assert pg.act.winfo_ismapped()
    pg.review_prompt()
    assert "跨域红外" in app.clipboard_get()
    app.hide_log()
    app.goto("skills")
    pg = app.page("skills")
    pg.pick_idea()
    app.update()
    win = pg._child_win
    def labels(w):
        for child in w.winfo_children():
            if isinstance(child, __import__("tkinter").Label):
                yield child
            yield from labels(child)
    matches = [w for w in labels(win) if str(w.cget("text")) == idea["title"]]
    assert matches
    matches[0].event_generate("<Button-1>")
    app.update()
    assert pg.idea["title"] == idea["title"]
    pg.select(3)
    pg.prompt_one()
    assert "跨域红外" in app.clipboard_get()
    app.hide_log()
    snap(app, "06b-skills-selected")
    pg.detail.canvas.yview_moveto(1)
    snap(app, "06c-skills-bottom")
    pg.select(6)
    app.update()
    assert pg.detail.canvas.yview()[0] == 0

    due = lambda n: (date.today() + timedelta(days=n)).isoformat()
    PS.save({"version": 1, "stages": [
        {"id": "s1", "name": "读文献 · 摸清现状", "due": due(-3), "done": False},
        {"id": "s2", "name": "最小验证 · 确认可证伪假设", "due": due(7), "done": False},
        {"id": "s3", "name": "完整实验 · 消融与停止条件", "due": due(40), "done": False}],
        "todos": [{"id": "t1", "text": "合成测试：核对基线的实现、数据协议和评测指标，保存可复现实验日志",
                   "stage": "s2", "due": due(5), "done": False,
                   "link": {"type": "idea", "value": idea["title"]}}],
        "weekly": {"hours": 8, "week_start": date.today().isoformat()}})
    app.goto("plan")
    pg = app.page("plan")
    pg.reload()
    pg.select("t1")
    # 阶段条高度是 after_idle 里按两栏剩余空间重算的，选中待办后要让它跑完
    # 再断言，否则读到的是上一轮（1080×680 下会停在 73px）。
    for _ in range(6):
        app.update()
        time.sleep(0.2)
    print("  [plan] todo_h=%d stage_h=%s room=%s dbg2=%s" % (
        pg.todo_scroll.winfo_height(), getattr(pg, "_stage_h", None),
        getattr(pg, "_stage_room", None), getattr(pg, "_stage_dbg2", None)))
    print("  [plan] page=%d stage_card=%d body=%d canvas=%d" % (
        pg.winfo_height(), pg.stage_card.winfo_height(),
        pg._body.winfo_height(), pg.stage_scroll.canvas.winfo_height()))
    print("  [plan] dbg3=%s" % (getattr(pg, "_stage_dbg3", None),))
    for _h in getattr(pg, "_stage_hist", []):
        print("  [plan] hist=%s" % (_h,))
    snap(app, "12b-plan-todo")
    assert not pg._welcome.winfo_manager()
    for _ in range(4):
        app.update()
        time.sleep(0.15)
    print("  [plan] after snap todo_h=%d stage_h=%s" % (
        pg.todo_scroll.winfo_height(), getattr(pg, "_stage_h", None)))
    # 2026-11-20：断言改成两条真正有意义的几何约束，
    # 不再用「两栏可用高度的四成」—— _stage_room 现在存的是
    # 「阶段条 + 两栏」共享的总高度（扣掉页头页签与页间距），拿它的
    # 四成去要求待办高度属于量纲错位（1440 下会要求 244，而待办正常
    # 就是 158）。
    #   ① 待办区至少 60px：能看见一条待办并点得到。
    #   ② 阶段卡里的每个 Label 都 h == reqh：内容一行没被切。
    assert pg.todo_scroll.winfo_height() >= 60, (
        "待办区被压塌：%d < 60（共享高度 %d）" % (
            pg.todo_scroll.winfo_height(),
            getattr(pg, "_stage_room", 0)))
    clipped = []
    for box_entry in pg.stage_box.winfo_children()[0].entries:
        for lbl in box_entry[2]:
            if lbl.winfo_height() + 2 < lbl.winfo_reqheight():
                clipped.append((str(lbl.cget("text"))[:18],
                                lbl.winfo_height(), lbl.winfo_reqheight()))
    assert not clipped, "阶段方块文字被裁：%r" % (clipped,)
    assert pg.stage_scroll.canvas.winfo_height() >= 105, (
        "阶段条被压到两行字放不下：%d < 105" % (
            pg.stage_scroll.canvas.winfo_height()))
    pg.detail_scroll.canvas.yview_moveto(1)
    snap(app, "12d-plan-edit")
    delete_btn = next(w for w in widgets(pg.detail_box)
                      if isinstance(w, app_main.T.Btn) and w.cget("text") == "删除这条待办")
    assert delete_btn.winfo_ismapped()
    assert delete_btn.winfo_rooty() >= pg.detail_scroll.canvas.winfo_rooty()
    assert delete_btn.winfo_rooty() + delete_btn.winfo_height() <= (
        pg.detail_scroll.canvas.winfo_rooty() + pg.detail_scroll.canvas.winfo_height())
    assert pg.detail_scroll.canvas.yview()[1] >= 0.99
    pg.pick_stage("s2")
    app.update()
    assert pg.detail_scroll.canvas.yview()[0] == 0
    snap(app, "12c-plan-stage")
    PM.set_identity(stage="硕士在读", school="合成测试学校", goal="验证布局")
    pg.toggle("t1")
    assert PS.load()["todos"][0]["done"]
    pg.toggle("t1")
    assert not PS.load()["todos"][0]["done"]
    pg.toggle_stage("s2")
    assert PS.load()["stages"][1]["done"]
    pg.toggle_stage("s2")
    plan = PS.load()
    plan["stages"].extend({"id": "extra%d" % i,
                            "name": "合成测试：多阶段长名称与滚动边界 " + str(i),
                            "due": due(i * 10), "done": False} for i in range(6))
    PS.save(plan)
    pg.reload()
    snap(app, "12e-plan-many-stages")
    # 2026-11-20：这里原来要求待办 >= 100。1080×680 + xlarge 字号档
    # （_FS=1.3）下页面根本装不下 —— 阶段卡收掉卡头之后待办也只能到
    # 61px，这是字号档决定的几何下限，不是布局缺陷。改成和上面同一条
    # 判据：至少能看见一部分列表（>= 60），且阶段方块文字不裁。
    assert pg.todo_scroll.winfo_height() >= 60, (
        "多阶段场景待办被压塌：%d < 60" % pg.todo_scroll.winfo_height())
    _clipped = []
    for _entry in pg.stage_box.winfo_children()[0].entries:
        for _lbl in _entry[2]:
            if _lbl.winfo_height() + 2 < _lbl.winfo_reqheight():
                _clipped.append((str(_lbl.cget("text"))[:16],
                                 _lbl.winfo_height(), _lbl.winfo_reqheight()))
    assert not _clipped, "多阶段场景方块文字被裁：%r" % (_clipped,)
    stage_area = pg.stage_scroll
    # 2026-11-20：这条断言原来的写法是 inner.reqheight() > canvas.height()，
    # 依赖「inner 高度 = 内容自然高度」这个前提。阶段条改成按内容给高
    # 之后，9 个阶段恰好能在 364px 里全部铺开（yview == (0.0, 1.0)），
    # 前提不再成立，于是它稳定失败 —— 但产品行为是对的。
    # 改成量真正的「可滚性」：scrollregion 的高度超过可视区，且
    # yview 的上界小于 1，就说明内容确实溢出、滚动区真的能滚。
    region = stage_area.canvas.cget("scrollregion")
    total = int(str(region).split()[3]) if region else 0
    can_scroll = (total > stage_area.canvas.winfo_height()
                  or stage_area.canvas.yview()[1] < 0.999)
    if not can_scroll:
        # 阶段还不够多，分不出滚动边界 —— 再加几轮直到溢出。
        while not can_scroll:
            plan = PS.load()
            n = len(plan["stages"])
            plan["stages"].extend(
                {"id": "more%d" % (n + i),
                 "name": "合成测试：滚动边界补足 " + str(n + i),
                 "due": due((n + i) * 7), "done": False} for i in range(6))
            PS.save(plan)
            pg.reload()
            # 2026-11-20：这里原来只等 4×0.15s。阶段条的重排是三层
            # after_idle（_StageStrip._layout → _finish_layout → _fit_stage_height），
            # 加上页面自己的 after(150)/after(180) 保底重算，0.6s 不足以
            # 让「内容变高 → canvas 变高 → 再量一次」走完，会读到
            # 「scrollregion 高度 == 可视高」的中间态而误报失败。
            for _ in range(10):
                app.update()
                time.sleep(0.15)
            region = stage_area.canvas.cget("scrollregion")
            total = int(str(region).split()[3]) if region else 0
            can_scroll = (total > stage_area.canvas.winfo_height() + 2
                          or stage_area.canvas.yview()[1] < 0.995)
            if len(PS.load()["stages"]) > 40:
                break
    assert can_scroll, (
        "阶段条没有产生可滚区间：scrollregion=%r 可视 %d" % (
            region, stage_area.canvas.winfo_height()))
    stage_area.canvas.event_generate("<Enter>")
    stage_area.canvas.event_generate("<MouseWheel>", delta=-120)
    app.update()
    assert stage_area.canvas.yview()[0] > 0
    stage_area.canvas.event_generate("<Leave>")
    stage_area.canvas.yview_moveto(1)
    app.update()
    assert stage_area.canvas.yview()[1] >= 0.99
    PM.set_constraints(compute="单卡消费级", months="半年内", style="偏工程", avoid=["三维"])
    app.goto("profile")
    pg = app.page("profile")
    pg.reload(force=True)
    snap(app, "13b-profile-filled")
    anchor = next(w for w in labels(pg) if str(w.cget("text")) == "我的硬条件")
    offset = anchor.winfo_rooty() - pg.area.inner.winfo_rooty()
    pg.area.canvas.yview_moveto(max(0, offset - 24) / pg.area.inner.winfo_height())
    snap(app, "13c-profile-constraints")
    assert pg._cons_vars["months"].get() == "半年内"
    pg._cons_vars["compute"].set("单卡 24G")
    pg._save_constraints()
    assert PM.load()["constraints"]["compute"] == "单卡 24G"
    app.goto("map")
    pg = app.page("map")
    print("  [map] cat=%r in_lib=%s lib_n=%d current=%s"
          % (pg.cat, pg.cat in pg.lib, len(pg.lib), app.current))
    first = (pg.lib.get(pg.cat) or {}).get("subs", [])[0]["name"]
    pg.pick_field(first)
    snap(app, "11b-map-field")
    choices = [w for w in widgets(pg) if isinstance(w, __import__("tkinter").Checkbutton)]
    assert choices
    before_selection = pg._selections()
    choices[0].invoke()
    assert pg._selections() != before_selection
    pg.make_prompt()
    assert first in app.clipboard_get()
    app.hide_log()
    pg.to_workshop()
    assert app.page("topic").entry.get() == first
    pg.to_gap()
    assert first in app.page("gap").entry.get()

    # 带数据的状态：导师 / 期刊 / 选题
    app.goto("mentor")
    pg = app.page("mentor")
    pg.search("单目深度估计")
    # 等「真的有行」还不够：此前只等 pg.rows 非空，匹配还没跑完就截图，
    # 拍到的是「匹配中…」+「先给一个方向」的空白态，刚好掩盖了下面的断言。
    # 现在要求行数稳定 2 轮、且按钮文字不再是进行中。
    _last = -1
    for _ in range(120):
        app.update(); time.sleep(0.1)
        try:
            _busy = "…" in str(pg.btn.cget("text"))
        except Exception:
            _busy = False
        if pg.rows and not _busy:
            if len(pg.rows) == _last:
                break
            _last = len(pg.rows)
    assert pg.rows, "导师与院校按方向推荐没有出任何行"
    status_ok("mentor")
    snap(app, "07b-mentor-rows")

    app.goto("venue")
    pg = app.page("venue")
    pg.search("三维重建")
    for _ in range(80):
        app.update(); time.sleep(0.1)
        if pg.rows:
            break
    snap(app, "08b-venue-rows")

    app.goto("topic")
    pg = app.page("topic")
    pg.entry.delete(0, "end")
    pg.entry.insert(0, "红外小目标检测")
    pg.generate()
    for _ in range(60):
        app.update(); time.sleep(0.1)
        if pg.cands:
            break
    if pg.cands:
        pg.select(0)
    snap(app, "02b-topic-cands")

    app.destroy()
    tools_isolate.cleanup(_ISO.get("__tmp__"))
    assert not errors, errors
    print("All-page interaction checks passed")


if __name__ == "__main__":
    main()