#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个人画像页 —— 「迭代记忆」的可视化前台。

这里只做三件事：
  1. 让你看见系统「记住」了什么（身份 / 情绪状态 / 注意力倾斜 / 记忆锚点 / 偏好）
  2. 让这些记忆能被管理（改身份、调状态、删锚点、导出/清空）
  3. 用图表把画像摊开 —— 记忆不是黑箱

数据层是 profile_memory.py，与 research_memory.json 分开存
（记忆是长期状态，选题台账是会被反复清空的工作数据，生命周期不同）。
"""
import datetime
import os
import re
import sys
import tkinter as tk


HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import app_theme as T           # noqa: E402
import ui_kit as UK             # noqa: E402
import profile_memory as PM     # noqa: E402
import ui_parts as U            # noqa: E402

# 展开后的完整说明：这一页是最容易被误解的一页（「0 条」到底正不正常）
PROFILE_HELP = (
    "这一页是「数字生命」的全部可见部分：它记住了什么、学到了什么、这些怎么影响别的页面。\n\n"
    "四块内容各自的作用：\n"
    "  · 我是谁 —— 学位阶段/学校/目标/算力。填得越全，选题建议越贴身；"
    "填了「算力资源」和「周期」之后，选题工坊会把做不动的候选直接标出来。\n"
    "  · 我的硬条件 —— 周期、算力、禁忌方向。这是**硬约束**，与心情无关，"
    "改动会立刻影响候选排序，不会被「你最近很焦虑」这类软状态覆盖。\n"
    "  · 我现在什么状态 —— 紧急度/兴趣/心境。这是**软旋钮**：紧急度高时，"
    "危机类记忆（离截止、卡住）会排到前面，日常类（随手收藏）会被压下去。\n"
    "  · 记忆锚点 —— 你做过的事。每条记忆都带着「存它时你是什么状态」，"
    "所以回头看能知道「这条是在赶 ddl 时记的，它很重」。\n\n"
    "**为什么可能一直是 0 条**：\n"
    "  只有四类动作会被记：新建选题、收藏/下载论文、查导师、把候选存进创新点库。"
    "单纯浏览页面不记 —— 否则 500 条上限几周就被正常浏览塞满，真正的线索反而被挤掉。"
    "所以刚开始用、或者只是一直在看论文，0 条是正常的，不是坏了。\n\n"
    "**它不做什么**：不联网、不上传、不训练模型。所有数据只在 "
    "researcher_profile.json 这一个文件里。想彻底清空，把那个文件删掉即可"
    "（删之前可以先退出应用）；「清空全部记忆」按钮已从页面上移走，"
    "因为它是这一页最容易误点的东西，而一年也用不到一次。"
)

IDENTITY_FIELDS = (
    ("stage", "学位阶段", "硕士在读 / 博士一年级"),
    ("school", "学校", "例如：东南大学"),
    ("lab", "课题组", "例如：智能视觉实验室"),
    ("advisor", "导师", "例如：张老师"),
    ("goal", "目标", "想投的会 / 想解决的问题"),
    ("resources", "算力资源", "例如：单卡 4090，跑得动 7B"),
)

STATUS_COLORS = {
    "焦虑": T.ERR, "兴奋": T.OK, "平静": T.ACCENT,
    "疲惫": T.WARN, "困惑": T.PURPLE,
}


class ProfilePage(tk.Frame):
    PAGE_HINT = "迭代记忆 · 记住你在做什么、卡在哪、更看重什么"

    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self._built = False
        self._build()
        # 页面一建好就渲染：不渲染的话切过来看到的是空白
        self.reload()

    # ------------------------------------------------------------ 骨架
    def _build(self):
        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=T.PAD, pady=(T.sp(8), T.sp(12)))
        title_row = tk.Frame(head, bg=T.BG)
        title_row.pack(fill="x")
        title_row.grid_columnconfigure(0, weight=1)
        title = tk.Label(title_row, text="个人画像", bg=T.BG, fg=T.TXT,
                         font=T.T_PAGE_TITLE(), anchor="w", justify="left", width=1)
        title.grid(row=0, column=0, sticky="ew")
        T.Btn(title_row, "刷新", lambda: self.reload(force=True)).grid(
            row=0, column=1, padx=(T.sp(12), 0))
        title.bind("<Configure>", lambda e: title.config(wraplength=max(1, e.width)))
        self._copy(head, "身份、状态与记忆只保存在本机；导出时去除可识别信息。",
                   bg=T.BG, pady=(T.sp(4), 0))
        self._hint = U.Hint(head, PROFILE_HELP, summary="了解记忆与隐私", bg=T.BG)
        self._hint.pack(fill="x")
        T.fill_wrap(self._hint._detail, pad=0)
        self._reset_host = head

        self.area = T.ScrollArea(self, bg=T.BG)
        self.area.pack(fill="both", expand=True)

    def _copy(self, parent, text, fg=None, font=None, bg=None, pady=(0, 0), padx=0):
        """正文按实际可用宽度折行，不让长内容撑大表单。"""
        label = tk.Label(parent, text=text, bg=bg or T.CARD, fg=fg or T.TXT3,
                         font=font or T.T_CAPTION(), anchor="w", justify="left",
                         width=1, wraplength=T.wrap(600))
        label.pack(fill="x", padx=padx, pady=pady)
        T.fill_wrap(label, pad=2 * padx)
        return label

    def _section_card(self, host, title, eyebrow, num, lead=""):
        card = T.Card(host, pad=T.sp(16), border=T.LINE)
        card.pack(fill="x", padx=T.PAD, pady=(0, T.sp(12)))
        UK.eyebrow(card.body, eyebrow, num, color=T.ACCENT).pack(fill="x")
        self._copy(card.body, title, fg=T.TXT, font=T.T_SECTION(),
                   pady=(T.sp(4), T.sp(4)))
        if lead:
            self._copy(card.body, lead, pady=(0, T.sp(8)))
        return card

    def _form_cell(self, grid, row, column, label, uniform):
        grid.grid_columnconfigure(column, weight=1, uniform=uniform)
        cell = tk.Frame(grid, bg=T.CARD)
        cell.grid(row=row, column=column, sticky="nsew",
                  padx=(0, T.sp(12)) if column == 0 else (T.sp(12), 0),
                  pady=(0, T.sp(12)))
        self._copy(cell, label, fg=T.TXT2, font=T.T_LABEL(),
                   pady=(0, T.sp(4)))
        return cell

    def _save_actions(self, parent, label, command, hint):
        actions = U.WrapRow(parent, bg=T.CARD)
        actions.pack(fill="x", pady=(T.sp(4), 0))
        actions.add(T.Btn(actions, label, command, "primary"))
        self._copy(parent, hint, pady=(T.sp(6), 0))

    # ------------------------------------------------------------ 渲染
    def reload(self, force=False):
        # 每次切回本页都会调 reload。记忆文件被别处写入（存创新点、AI 对话、
        # 手势埋点）时 mtime 一定变，所以用签名判断既能不漏更新，
        # 又能避免「切回来什么都没变却整页重建」的那 200 多毫秒。
        try:
            sig = (PM.PROFILE_FILE.stat().st_mtime_ns,)
        except Exception:
            sig = None
        if not force and sig is not None and sig == getattr(self, "_sig", None):
            return
        self._sig = sig
        for w in self.area.inner.winfo_children():
            w.destroy()
        try:
            prof = PM.load()
        except Exception as exc:
            tk.Label(self.area.inner, text="读取画像失败：" + str(exc),
                     bg=T.BG, fg=T.ERR, font=T.T_BODY()).pack(pady=30)
            self.area.refresh(defer=True)
            return
        host = self.area.inner
        self._render_summary(host, prof)
        self._render_identity(host, prof)
        self._render_constraints(host, prof)
        self._render_state(host, prof)
        self._render_tilt(host, prof)
        self._render_effect(host, prof)
        self._render_anchors(host, prof)
        self._render_prefs(host, prof)
        self._render_footer(host, prof)
        self.area.refresh(defer=True)

    # -------------------------------------------------- 顶部紧凑概要
    def _render_summary(self, host, prof):
        st = prof.get("state") or {}
        anchors = prof.get("anchors") or []
        ident = prof.get("identity") or {}
        count = sum(bool(ident.get(key)) for key, _, _ in IDENTITY_FIELDS)
        card = T.Card(host, pad=T.sp(12), border=T.LINE)
        card.pack(fill="x", padx=T.PAD, pady=(0, T.sp(12)))
        stats = tk.Frame(card.body, bg=T.CARD)
        stats.pack(fill="x")
        items = (
            ("身份已填", "%d / %d 项" % (count, len(IDENTITY_FIELDS))),
            ("记忆锚点", "%d 条" % len(anchors)),
            ("当前紧急度", "%.0f / 100" % float(st.get("urgency", 0))),
            ("当前心情", st.get("mood") or "平静"),
        )
        for column, (label, value) in enumerate(items):
            stats.grid_columnconfigure(column, weight=1, uniform="summary")
            cell = tk.Frame(stats, bg=T.CARD)
            cell.grid(row=0, column=column, sticky="nsew",
                      padx=(0, T.sp(8)) if column < 3 else 0)
            self._copy(cell, label)
            self._copy(cell, value, fg=T.ACCENT, font=T.T_BODY_SM(), pady=(T.sp(2), 0))
        identity = " · ".join(str(ident[k]) for k in ("stage", "school", "lab") if ident.get(k))
        self._copy(card.body, identity or "身份尚未填写；可以从学位阶段与研究目标开始。",
                   fg=T.TXT2, pady=(T.sp(8), 0))
        if ident.get("goal"):
            self._copy(card.body, "研究目标：" + str(ident["goal"]), pady=(T.sp(4), 0))
        if not anchors:
            self._copy(card.body,
                       "暂无锚点是正常的。新建选题、收藏或下载论文、查导师、"
                       "把候选存进创新点库会积累记忆；单纯浏览不会。",
                       pady=(T.sp(6), 0))

    # -------------------------------------------------- 身份
    def _render_identity(self, host, prof):
        card = self._section_card(host, "我是谁", "身份信息", "01",
                                  "决定候选方向与推荐语气的起点；各项均可留空。")
        ident = prof.get("identity") or {}
        grid = tk.Frame(card.body, bg=T.CARD)
        grid.pack(fill="x", pady=(T.sp(4), 0))
        self._ident_entries = {}
        for i, (key, label, hint) in enumerate(IDENTITY_FIELDS):
            r, c = divmod(i, 2)
            cell = self._form_cell(grid, r, c, label, "identity")
            e = tk.Entry(cell, bg=T.CARD_HI, fg=T.TXT, insertbackground=T.ACCENT,
                         relief="flat", font=T.T_BODY_SM(), width=1,
                         highlightthickness=1, highlightbackground=T.LINE,
                         highlightcolor=T.ACCENT)
            e.pack(fill="x", ipady=T.sp(6))
            val = str(ident.get(key, "") or "")
            if val:
                e.insert(0, val)
            else:
                # 占位提示：不填时输入框里给个浅色的例子，
                # 否则六个空框子分不出该填什么（提示行只有 label）
                e.insert(0, hint or "")
                e.config(fg=T.TXT4)
                e._placeholder = hint or ""
                e.bind("<FocusIn>", lambda ev: self._ph_clear(ev))
                e.bind("<FocusOut>", lambda ev: self._ph_restore(ev))
            self._ident_entries[key] = e

        self._save_actions(card.body, "保存身份", self._save_identity,
                           "留空表示不填；只存本机 researcher_profile.json。")

    def _ph_clear(self, ev):
        e = ev.widget
        if e.get() == getattr(e, "_placeholder", None):
            e.delete(0, "end")
            e.config(fg=T.TXT)

    def _ph_restore(self, ev):
        e = ev.widget
        ph = getattr(e, "_placeholder", None)
        if ph is not None and not e.get().strip():
            e.insert(0, ph)
            e.config(fg=T.TXT4)

    def _save_identity(self):
        data = {}
        for key, e in self._ident_entries.items():
            v = e.get().strip()
            if v and v != getattr(e, "_placeholder", None):
                data[key] = v
        try:
            PM.set_identity(**data)
            PM.remember("更新了个人身份信息", tags=["身份"], kind="profile")
            self.app.toast("身份已保存", T.OK)
            self.reload(force=True)
        except Exception as exc:
            self.app.toast("保存失败：" + str(exc), T.ERR)

    # -------------------------------------------------- 硬约束
    def _render_constraints(self, host, prof):
        """硬约束：和「我现在什么状态」分开，因为这一块会真影响候选的可行性判断。

        放这么多选项而不是自由文本，是因为自由文本没法参与计算 ——
        以前「算力资源」是一个输入框，用户写「4090」和写「没算力」对系统没区别。
        """
        con = prof.get("constraints") or {}
        card = self._section_card(host, "我的硬条件", "研究约束", "02",
                                  "用于判断候选是否可行，与心情无关。")
        grid = tk.Frame(card.body, bg=T.CARD)
        grid.pack(fill="x", pady=(T.sp(4), 0))
        self._cons_vars = {}
        self._cons_combos = {}

        def _opt(row, column, label, key, options):
            cell = self._form_cell(grid, row, column, label, "constraints")
            var = tk.StringVar(value=con.get(key) or options[0])
            # 2026-11-20：这里原来是 tk.OptionMenu。Windows 上每个 OptionMenu
            # 占一个原生 HMENU，destroy 后不立刻归还；本页一口气建十来个，
            # 于是「把所有页点一遍再回画像页」时 Tk 抛
            # `No more menus can be allocated.`，整页打不开。
            # 换成 ui_kit.Combo（Button + Toplevel，不占原生菜单）。
            combo = UK.Combo(cell, var.get(), options,
                             on_change=lambda v: var.set(v),
                             font=T.T_BODY_SM(), bg=T.CARD_HI)
            combo.pack(fill="x")
            self._cons_vars[key] = var
            self._cons_combos[key] = combo
            return var

        _opt(0, 0, "算力", "compute", ["未填"] + list(PM.COMPUTE_LEVELS))
        _opt(0, 1, "周期", "months", ["未填"] + list(PM.TIME_LEVELS))
        _opt(1, 0, "偏好", "style", ["未填", "偏工程", "偏理论", "都行"])
        cell = self._form_cell(grid, 1, 1, "禁忌方向", "constraints")
        self._avoid_var = tk.StringVar(value="、".join(con.get("avoid") or []))
        ae = tk.Entry(cell, textvariable=self._avoid_var, bg=T.CARD_HI, fg=T.TXT,
                      insertbackground=T.ACCENT, relief="flat", font=T.T_BODY_SM(),
                      width=1, highlightthickness=1, highlightbackground=T.LINE,
                      highlightcolor=T.ACCENT)
        ae.pack(fill="x", ipady=T.sp(6))
        self._copy(cell, "多个方向用顿号或逗号分隔。", pady=(T.sp(4), 0))

        # 条件填了才显示一行解释，让人知道系统拿它做什么判断
        hint = []
        if con.get("compute") in PM.COMPUTE_LEVELS:
            hint.append(PM.COMPUTE_LEVELS[con["compute"]][1])
        if con.get("months") in PM.TIME_LEVELS:
            hint.append(PM.TIME_LEVELS[con["months"]][1])
        if con.get("avoid"):
            hint.append("命中「%s」的候选会被标出来" % "、".join(con["avoid"]))
        if not hint:
            hint.append("填了以后，选题工坊会把做不动的候选沉到底部并写明原因")
        self._copy(card.body, "；".join(hint), pady=(T.sp(4), T.sp(8)))
        self._save_actions(card.body, "保存条件", self._save_constraints,
                           "只存本机，不上传；留「未填」表示不参与判断。")

    def _save_constraints(self):
        data = {}
        for key, var in getattr(self, "_cons_vars", {}).items():
            v = var.get().strip()
            data[key] = "" if v in ("", "未填") else v
        raw = getattr(self, "_avoid_var", None)
        if raw is not None:
            data["avoid"] = [x for x in re.split(r"[、,，;；\s]+", raw.get()) if x]
        try:
            PM.set_constraints(**data)
            PM.remember("更新了硬条件", tags=["身份"], kind="profile")
            self.app.toast("硬条件已保存", T.OK)
            self.reload(force=True)
        except Exception as exc:
            self.app.toast("保存失败：" + str(exc), T.ERR)

    # -------------------------------------------------- 状态
    def _render_state(self, host, prof):
        st = prof.get("state") or {}
        card = self._section_card(host, "我现在什么状态", "状态旋钮", "03",
                                  "紧急度与兴趣只调整注意力和候选顺序，不覆盖硬条件。")
        row = tk.Frame(card.body, bg=T.CARD)
        row.pack(fill="x", pady=(T.sp(4), 0))
        row.grid_columnconfigure(0, weight=1, uniform="state")
        row.grid_columnconfigure(1, weight=1, uniform="state")

        # 紧急度
        ucol = tk.Frame(row, bg=T.CARD)
        ucol.grid(row=0, column=0, sticky="nsew", padx=(0, T.sp(12)))
        self._u_lab = tk.Label(ucol, text="紧急度  %.0f" % st.get("urgency", 0), bg=T.CARD,
                               fg=T.TXT2, font=T.T_BODY_SM(), anchor="w")
        self._u_lab.pack(fill="x")
        self._u_var = tk.DoubleVar(value=float(st.get("urgency", 0)))
        sc = tk.Scale(ucol, from_=0, to=100, orient="horizontal", variable=self._u_var,
                      bg=T.CARD, fg=T.TXT3, troughcolor=T.CARD_HI, bd=0,
                      highlightthickness=0, showvalue=0, sliderrelief="flat",
                      sliderlength=18, width=8,
                      activebackground=T.ACCENT, command=self._on_urgency)
        sc.pack(fill="x")
        self._copy(ucol, "0 = 很闲 · 60 左右开始变化 · 80+ 视为危机")

        # 兴趣
        icol = tk.Frame(row, bg=T.CARD)
        icol.grid(row=0, column=1, sticky="nsew", padx=(T.sp(12), 0))
        self._i_lab = tk.Label(icol, text="兴趣  %.0f" % st.get("interest", 0), bg=T.CARD,
                               fg=T.TXT2, font=T.T_BODY_SM(), anchor="w")
        self._i_lab.pack(fill="x")
        self._i_var = tk.DoubleVar(value=float(st.get("interest", 0)))
        tk.Scale(icol, from_=0, to=100, orient="horizontal", variable=self._i_var,
                 bg=T.CARD, fg=T.TXT3, troughcolor=T.CARD_HI, bd=0,
                 highlightthickness=0, showvalue=0, sliderrelief="flat",
                 sliderlength=18, width=8,
                 activebackground=T.ACCENT, command=self._on_interest).pack(fill="x")
        self._copy(icol, "高 = 更愿意把「有意思但难」的候选排前面")

        # 心情与操作可随可用宽度折行。
        self._copy(card.body, "心情", font=T.T_LABEL(), pady=(T.sp(12), T.sp(4)))
        mrow = U.WrapRow(card.body, bg=T.CARD)
        mrow.pack(fill="x")
        for m in PM.MOODS:
            mrow.add(UK.Chip(mrow, m, active=(st.get("mood") == m),
                             command=lambda mm=m: self._set_mood(mm)))
        self._save_actions(card.body, "保存状态", self._commit_state,
                           "滑杆调整后保存；选择心情或套用截止日也会保存当前状态。")

        # 截止日 → 自动算紧急度
        self._copy(card.body, "按截止日自动计算", font=T.T_LABEL(),
                   pady=(T.sp(12), T.sp(4)))
        drow = U.WrapRow(card.body, bg=T.CARD)
        drow.pack(fill="x")
        self._ddl = tk.Entry(drow, bg=T.CARD_HI, fg=T.TXT,
                             insertbackground=T.ACCENT, relief="flat",
                             font=T.T_BODY_SM(), width=14, highlightthickness=1,
                             highlightbackground=T.LINE, highlightcolor=T.ACCENT)
        drow.add(self._ddl)
        self._ddl.insert(0, "2026-12-31")
        drow.add(T.Btn(drow, "套用", self._apply_ddl))
        self._copy(card.body, "格式 YYYY-MM-DD；离得越近，紧急度越高。",
                   pady=(T.sp(6), 0))

    def _on_urgency(self, v):
        try:
            self._u_lab.config(text="紧急度  %.0f" % float(v))
        except Exception:
            pass

    def _on_interest(self, v):
        try:
            self._i_lab.config(text="兴趣  %.0f" % float(v))
        except Exception:
            pass

    def _commit_state(self, **extra):
        try:
            PM.set_state(urgency=float(self._u_var.get()),
                         interest=float(self._i_var.get()), **extra)
            self.app.toast("状态已更新", T.OK)
            self.reload(force=True)
        except Exception as exc:
            self.app.toast("更新失败：" + str(exc), T.ERR)

    def _set_mood(self, mood):
        self._commit_state(mood=mood)

    def _apply_ddl(self):
        txt = self._ddl.get().strip()
        try:
            u = PM.urgency_from_ddl(txt)
        except Exception:
            self.app.toast("日期格式应为 YYYY-MM-DD", T.WARN)
            return
        self._u_var.set(u)
        self._commit_state(note="截止日 " + txt)

    # -------------------------------------------------- 注意力倾斜
    def _render_tilt(self, host, prof):
        st = prof.get("state") or {}
        u = float(st.get("urgency", 30.0))
        crisis_w, daily_w = _weights_full(u)
        card = self._section_card(host, "注意力倾斜曲线", "记忆权重", "04",
                                  "只调整「先想起谁」，不据此删除记忆；倍率来自现有权重算法。")

        two = tk.Frame(card.body, bg=T.CARD)
        two.pack(fill="x")
        two.grid_columnconfigure(0, weight=1, uniform="t")
        two.grid_columnconfigure(1, weight=1, uniform="t")

        left = tk.Frame(two, bg=T.CARD)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, T.sp(12)))
        self._copy(left, "危机类记忆 ×%.2f" % crisis_w,
                   fg=T.ACCENT, font=T.T_BODY())
        self._copy(left, "日常类记忆 ×%.2f" % daily_w, font=T.T_BODY(),
                   pady=(T.sp(4), 0))
        # 权重曲线：只在几个关键紧急度点上取值，写成一行
        # （2026-11-15 用户要求「可视化表去除」，原来的 2×26 色块矩阵
        #  换成 6 个采样点，读起来更快，也不占一屏）
        samples = [0, 30, 60, 80, 90, 100]
        pts = "  ".join(
            "u=%d → 危机×%.2f / 日常×%.2f" % (x, PM.urgency_weights(x)[0],
                                        PM.urgency_weights(x)[1])
            for x in samples)
        self._copy(left, "紧急度对应的记忆权重：" + pts, fg=T.TXT2,
                   pady=(T.sp(6), T.sp(2)))

        right = tk.Frame(two, bg=T.CARD)
        right.grid(row=0, column=1, sticky="nsew", padx=(T.sp(12), 0))
        self._copy(right, "这条曲线在说什么", font=T.T_LABEL())
        for txt in (
            "紧急度 60 以下：平静模式，两类记忆同权参与。",
            "60 → 80：线性拉升，危机类逐步靠前，不会在某个整数上突然翻脸。",
            "80 以上：危机 ×3.0、日常 ×0.1 —— 相当于「只有 deadline 存在」。",
            "所有条目仍全部交给模型，只是顺序变了，一条都没删。",
        ):
            self._copy(right, txt, fg=T.TXT2, pady=(T.sp(4), 0))

    # -------------------------------------------------- 画像对选题的实际影响
    def _render_effect(self, host, prof):
        """把「画像 → 选题排序」这一步摆出来，否则画像页看起来只是记账。"""
        import topic_gen
        st = prof.get("state") or {}
        urg = int(st.get("urgency", 0) or 0)
        interest = int(st.get("interest", 50) or 50)
        mood = st.get("mood", "") or ""

        card = self._section_card(host, "这个画像怎么影响选题", "排序示例", "05",
                                  "选题工坊按当前状态重排：只改顺序，不删候选，"
                                  "被挪动的候选会注明理由。以下是固定方向的试算，不是对你的评分。")

        # 用当前画像试算一次，直接展示前 4 名
        demo_dir = "红外小目标检测"
        tilt = {"urgency": urg, "interest": interest, "mood": mood,
                "prefs": {"angle": (prof.get("preferences") or {}).get("angle") or {},
                          "strategy": (prof.get("preferences") or {}).get("strategy") or {}}}
        try:
            cs = topic_gen.build(demo_dir, "自动混合", 18, profile=tilt)
        except Exception:
            cs = []
        if not cs:
            self._copy(card.body, "暂时算不出示例。")
        else:
            self._copy(card.body, "以「%s」为例，你现在会先看到：" % demo_dir,
                       pady=(0, T.sp(4)))
            for i, c in enumerate(cs[:4]):
                zebra = T.CARD_HI if i % 2 else T.CARD
                row = tk.Frame(card.body, bg=zebra)
                row.pack(fill="x", pady=T.sp(2))
                tk.Label(row, text=str(i + 1).zfill(2), bg=zebra, fg=T.TXT4,
                         font=T.M(8)).pack(side="left", anchor="n",
                                           padx=(T.sp(6), T.sp(8)), pady=T.sp(6))
                body = tk.Frame(row, bg=zebra)
                body.pack(side="left", fill="x", expand=True,
                          padx=(0, T.sp(8)), pady=T.sp(6))
                self._copy(body, c.get("angle", ""), bg=zebra,
                           fg=T.TXT if i == 0 else T.TXT2, font=T.T_BODY_SM())
                self._copy(body, "候选得分：%s" % c.get("score", "—"), bg=zebra)
                self._copy(body, c.get("tilt_reason") or "暂无状态重排理由", bg=zebra,
                           pady=(T.sp(2), 0))

        act = U.WrapRow(card.body, bg=T.CARD)
        act.pack(fill="x", pady=(T.sp(10), 0))
        act.add(T.Btn(act, "去选题工坊试一次", lambda: self.app.goto("topic")))

    # -------------------------------------------------- 记忆锚点
    def _render_anchors(self, host, prof):
        anchors = prof.get("anchors") or []
        card = self._section_card(host, "记忆锚点（%d 条）" % len(anchors),
                                  "事件记忆", "06", "保留事件全文与记录时的心情；可手动补充或删除。")
        actions = U.WrapRow(card.body, bg=T.CARD)
        actions.pack(fill="x")
        actions.add(T.Btn(actions, "手动记一条", self._add_anchor))

        if not anchors:
            empty = tk.Frame(card.body, bg=T.CARD_HI)
            empty.pack(fill="x", pady=(10, 0))
            self._copy(empty, "还没有任何记忆", bg=T.CARD_HI, fg=T.TXT2,
                       font=T.T_BODY_SM(), padx=T.sp(12), pady=(T.sp(10), T.sp(2)))
            self._copy(empty,
                       "在选题工坊、文献空白、最新研究页操作时，系统会把关键动作"
                       "写成一条带情绪的锚点。存的时候如果正处在高紧急度，"
                       "这条记忆会被标成「闪光灯记忆」，以后优先想起。",
                       bg=T.CARD_HI, padx=T.sp(12), pady=(0, T.sp(10)))
            return

        box = tk.Frame(card.body, bg=T.CARD)
        box.pack(fill="x", pady=(8, 0))
        for a in anchors[-12:][::-1]:
            self._anchor_row(box, a, compact=True)
        if len(anchors) > 12:
            self._copy(card.body, "只显示最近 12 条，共 %d 条" % len(anchors),
                       pady=(T.sp(4), 0))

    def _anchor_row(self, parent, a, compact=False):
        f = tk.Frame(parent, bg=T.CARD)
        f.pack(fill="x", pady=(T.sp(4), T.sp(8)))
        kind = a.get("kind") or "note"
        col = {"crisis": T.ERR, "daily": T.TXT3}.get(kind, T.ACCENT)
        meta = U.WrapRow(f, bg=T.CARD)
        meta.pack(fill="x")
        meta.add(tk.Label(meta, text={"crisis": "危机", "daily": "日常"}.get(kind, "记录"),
                          bg=T.CARD_HI, fg=col, font=T.T_CAPTION(),
                          padx=T.sp(6), pady=T.sp(2)))
        ts = a.get("at") or 0
        try:
            when = datetime.datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
        except Exception:
            when = "—"
        meta.add(tk.Label(meta, text=when, bg=T.CARD, fg=T.TXT4, font=T.T_CAPTION()))
        mood = a.get("mood")
        if mood:
            meta.add(tk.Label(meta, text=mood, bg=T.CARD,
                              fg=STATUS_COLORS.get(mood, T.TXT3), font=T.T_CAPTION()))
        meta.add(T.Btn(meta, "删除", lambda x=a.get("id"): self._del_anchor(x), "ghost"))
        self._copy(f, str(a.get("text") or ""), fg=T.TXT2, font=T.T_BODY_SM(),
                   pady=(T.sp(4), T.sp(8)))
        UK.divider(f)

    def _add_anchor(self):
        from app_theme import ask_text
        txt = ask_text(self, "记一条", "写下你正在做什么 / 卡在哪：", width=52)
        if not txt:
            return
        try:
            PM.remember(txt, tags=["手动"], kind="note", source="profile_page")
            self.app.toast("已记住", T.OK)
            self.reload(force=True)
        except Exception as exc:
            self.app.toast("记录失败：" + str(exc), T.ERR)

    def _del_anchor(self, aid):
        if not aid:
            return
        try:
            PM.forget(aid)
            self.reload(force=True)
        except Exception as exc:
            self.app.toast("删除失败：" + str(exc), T.ERR)

    # -------------------------------------------------- 偏好
    def _render_prefs(self, host, prof):
        prefs = prof.get("preferences") or {}
        cats = prefs.get("categories") or {}
        fields = prefs.get("fields") or {}
        card = self._section_card(host, "偏好统计", "选择记录", "07",
                                  "选择与收藏会累加；至少 3 次才参与排序，避免一次误点带偏。")
        if not cats and not fields:
            self._copy(card.body, "还没有偏好数据；使用选题工坊后会逐步积累。",
                       pady=(T.sp(6), 0))
            return
        # 偏好 Top6：文字列表而不是条形图
        # （2026-11-15 用户要求「可视化表去除」）
        def _top_line(title, data):
            top = sorted(data.items(), key=lambda kv: -kv[1])[:6]
            if not top:
                return
            box = tk.Frame(card.body, bg=T.CARD)
            box.pack(fill="x", pady=(4, 0))
            self._copy(box, title, font=T.T_LABEL())
            self._copy(box, " · ".join("%s %d" % (k, v) for k, v in top),
                       fg=T.TXT2, font=T.T_BODY_SM(), pady=(T.sp(4), T.sp(6)))

        _top_line("常看的领域", cats)
        _top_line("常看的方向", fields)

    # -------------------------------------------------- 底部操作
    def _render_footer(self, host, prof):
        card = self._section_card(host, "数据位置与管理", "本地隐私", "08")
        card.pack_configure(pady=(0, T.sp(18)))
        path = str(PM.PROFILE_FILE) if hasattr(PM, "PROFILE_FILE") else "researcher_profile.json"
        self._copy(card.body, path, font=T.M(12), pady=(T.sp(2), T.sp(8)))
        act = U.WrapRow(card.body, bg=T.CARD)
        act.pack(fill="x")
        act.add(T.Btn(act, "打开所在文件夹", self._open_dir))
        act.add(T.Btn(act, "导出脱敏画像", self._export, "ghost"))
        self._copy(card.body, "导出会去掉学校、导师等可识别字段，便于分享；原画像仍保留在本机。",
                   pady=(T.sp(6), 0))

    def _open_dir(self):
        try:
            os.startfile(HERE)
        except Exception as exc:
            self.app.toast("打开失败：" + str(exc), T.ERR)

    def _export(self):
        try:
            import json
            data = PM.export_public()
            d = os.path.join(HERE, "exports")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "profile_public_%s.json"
                             % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.app.toast("已导出：" + os.path.basename(p), T.OK)
        except Exception as exc:
            self.app.toast("导出失败：" + str(exc), T.ERR)

    def reset_all(self):
        from tkinter import messagebox
        if not messagebox.askyesno("确认", "清空全部个人记忆？\n"
                                          "身份、状态、锚点、偏好都会删除，不可恢复。\n"
                                          "（不影响文献库和选题台账）",
                                   parent=self):
            return
        try:
            PM.reset()
            self.app.toast("已清空", T.OK)
            self.reload(force=True)
        except Exception as exc:
            self.app.toast("清空失败：" + str(exc), T.ERR)


def _weights_full(urgency):
    """返回 (危机权重, 日常权重)。走 profile_memory 的实现，保证曲线和实际一致。"""
    try:
        r = PM.urgency_weights(urgency)
        if isinstance(r, (tuple, list)) and len(r) >= 2:
            return float(r[0]), float(r[1])
        if isinstance(r, dict):
            return float(r.get("crisis", 1.0)), float(r.get("daily", 1.0))
    except Exception:
        pass
    return 1.0, 1.0