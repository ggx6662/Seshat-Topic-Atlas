#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""研究计划页：阶段 / 截止 / 待办 / 每周投入。

为什么单独一页
--------------
总览页原来有四列卡片流（我的选题 / 最近入库 / 导师候选 / 下一步），
用户 2026-11-15 明确说「这块我不需要，我认为不太科学，看的不舒服」。
四列的毛病在于：它把**四类不同性质的东西**并排成同一种卡片，读的人
必须先自己判断「哪一列现在跟我有关」。计划这件事有明确的先后和期限，
它值得一整页，也需要能勾选、能改、能挂到选题上 —— 卡片流给不了这些。

这一页做四件事（用户指定的粒度）
  1. 阶段 + 截止日期：上方的横条，横条长度 = 阶段之间天数的比例
  2. 待办：可勾选，可挂阶段，可挂选题/方向
  3. 与选题/方向挂钩：加待办时可以从「创新点库」挑一条
  4. 每周投入：这周还剩几小时（只看该做多少条，不预测工期）

刻意不做的事
  · 不给「完成度 %」这种分数 —— 计划不是简历，不需要一个数字评价你
  · 不自动排期 —— 没有真实工期数据，排出来的日期是编的
  · 不推送、不提醒 —— 桌面程序弹窗提醒属于打扰；过期的事情用红色标出来就够
"""
import tkinter as tk

from datetime import date, timedelta

import app_theme as T
from ui_parts import WrapRow   # 会自动折行的按钮排
import plan_store as PS
import ui_parts as U

PAGE_HINT = "阶段与截止 · 待办勾选 · 挂选题 · 每周投入"

PLAN_HELP = """\
这里是你自己排的科研进度，和左边那几个页面不是一回事：那些页面给你材料，这一页排你的时间。

一、上方的阶段横条
· 每个阶段一个方块，宽度按「到截止日还有多久」的比例画，所以越靠右越远。
· 颜色只表状态：灰色还没到、黄色 7 天内、红色已经过期。已经勾完成的画成实心。
· 横条只做减法 —— 拿截止日期减今天。系统**不预测**你几天能做完，因为没有任何数据支撑。

二、待办
· 勾一下就完成，再点一次撤销。没有「归档」，勾掉的会留在原位并淡化。
· 待办可以挂到某个阶段下（右侧详情里能改），也可以不挂。
· 可以挂到一条选题或一个研究方向，之后在总览页和选题页能对上。

三、每周投入
· 填你平均一周能拿出几小时。它只用来算「这周还剩几小时」，不会被拿来评价进度。
· 剩余小时按「未完成待办数 ÷ 每周小时数」估算，是**提醒**不是承诺。

四、这里不做的事
不打分，不排期，不弹窗提醒。过期的东西标红，剩下的由你自己决定。"""


def _fmt_days(st, days):
    if st == "none":
        return "没填截止日"
    if st == "over":
        return "已过期 %d 天" % (-days)
    if days == 0:
        return "今天到期"
    return "还剩 %d 天" % days


def _state_color(st):
    return {"over": T.ERR, "soon": T.WARN}.get(st, T.TXT3)


class PlanPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.sel_todo = None
        self.sel_stage = None
        self._build()
        self.reload()

    # ------------------------------------------------------------ 布局
    def _build(self):
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        self._hint = U.Hint(top, PLAN_HELP, summary="怎么用这一页", bg=T.BG)
        self._hint.pack(side="left", fill="x", expand=True)
        T.Btn(top, "加待办", self.add_todo, "primary").pack(side="right")
        # 「加阶段」在空计划状态下不挂出来：空态卡里已经有「用推荐阶段起步」，
        # 两个按钮并排会让用户以为必须先建阶段才能加待办。有阶段后再出现。
        self._stage_btn = T.Btn(top, "加阶段", self.add_stage)
        self._stage_btn.pack(side="right", padx=(0, 6))

        self.metric_row = tk.Frame(self, bg=T.BG)
        self.metric_row.pack(fill="x", padx=T.PAD)
        self._metrics = U.FoldMetrics(
            self.metric_row,
            [("当前阶段", "—"), ("待办", "0 / 0"), ("已过期", "0"), ("每周投入", "—")],
            bg=T.BG, cols=4)
        self._metrics.pack(fill="x")

        # 阶段横条
        self.stage_card = T.Card(self, pad=12, fill_y=False)
        self.stage_card.pack(fill="x", padx=T.PAD, pady=(10, 8))
        T.card_head(self.stage_card.body, "阶段", "宽度按到截止日的远近画", bg=T.CARD)
        self.stage_box = tk.Frame(self.stage_card.body, bg=T.CARD)
        self.stage_box.pack(fill="x")

        # 主体两栏：待办（左）+ 详情（右）
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        body.grid_columnconfigure(0, weight=5, uniform="c")
        body.grid_columnconfigure(1, weight=5, uniform="c")
        body.grid_rowconfigure(0, weight=1)
        self._body = body

        left = T.Card(body, pad=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._left = left
        head = tk.Frame(left.body, bg=T.CARD)
        head.pack(fill="x", pady=(0, 6))
        tk.Label(head, text="待办", bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(),
                 anchor="w").pack(side="left")
        self.todo_count = tk.Label(head, text="", bg=T.CARD, fg=T.TXT4,
                                   font=T.T_CAPTION(), anchor="e")
        self.todo_count.pack(side="right")
        self.todo_scroll = T.ScrollArea(left.body, bg=T.CARD)
        self.todo_scroll.pack(fill="both", expand=True)

        right = T.Card(body, pad=14)
        right.grid(row=0, column=1, sticky="nsew")
        self._right = right
        self.detail_head = tk.Label(right.body, text="选一条待办或一个阶段",
                                    bg=T.CARD, fg=T.TXT, font=T.T_BODY(), anchor="w",
                                    justify="left", wraplength=430)
        self.detail_head.pack(fill="x")
        self.detail_sub = tk.Label(right.body, text="", bg=T.CARD, fg=T.TXT3,
                                   font=T.T_CAPTION(), anchor="w", justify="left",
                                   wraplength=430)
        self.detail_sub.pack(fill="x", pady=(2, 8))
        self.detail_scroll = T.ScrollArea(right.body, bg=T.CARD)
        self.detail_scroll.pack(fill="both", expand=True)
        self.detail_box = tk.Frame(self.detail_scroll.inner, bg=T.CARD)
        self.detail_box.pack(fill="both", expand=True)

        # 空态：计划完全是空的时候，两栏收起，只留引导
        self._welcome = tk.Frame(self, bg=T.BG)

    # ------------------------------------------------------------ 数据
    def reload(self):
        self.plan = PS.load()
        self._render_metrics()
        self._render_stages()
        self._render_todos()
        self._render_detail()

    def _render_metrics(self):
        p = PS.progress()
        cur = p.get("current")
        if cur:
            name = str(cur.get("name") or "")
            if len(name) > 14:
                name = name[:13] + "…"
            cur_txt = name
        else:
            cur_txt = "—"
        self._metrics.set_values({
            "当前阶段": cur_txt,
            "待办": "%d / %d" % (p["todos_done"], p["todos_total"]),
            "已过期": str(p["overdue"]),
            "每周投入": ("%g 小时" % p["weekly_hours"]) if p["weekly_hours"] else "—",
        })

    # ------------------------------------------------------------ 阶段横条
    def _render_stages(self):
        for w in self.stage_box.winfo_children():
            w.destroy()
        stages = self.plan.get("stages") or []
        if not stages:
            self.stage_box.pack_forget()
            self.stage_card.pack_forget()
            return
        if not self.stage_card.winfo_ismapped():
            self.stage_card.pack(fill="x", padx=T.PAD, pady=(10, 8),
                                 after=self.metric_row)
        if not self.stage_box.winfo_ismapped():
            self.stage_box.pack(fill="x")

        # 每个阶段一个方块，**权重按天数** —— 这样时间轴是等比例的，
        # 不需要画刻度线就能看出「哪一段最长」。
        open_stages = [s for s in stages if not s.get("done")]
        weights = []
        for s in stages:
            st, days = PS.due_state(s.get("due"))
            if st == "none":
                weights.append(10.0)
            else:
                weights.append(min(120.0, max(6.0, float(abs(days) + 1))))
        row = tk.Frame(self.stage_box, bg=T.CARD)
        row.pack(fill="x")
        for i, s in enumerate(stages):
            row.grid_columnconfigure(i, weight=int(weights[i] * 4), uniform="")
            st, days = PS.due_state(s.get("due"))
            active = self.sel_stage == s["id"]
            if s.get("done"):
                bgc, fgc = T.CARD_HI, T.TXT3
            elif active:
                bgc, fgc = T.ACCENT_D, T.ACCENT
            else:
                bgc, fgc = T.tint(_state_color(st), 0.16, T.CARD), _state_color(st)

            box = tk.Frame(row, bg=bgc, cursor="hand2")
            box.grid(row=0, column=i, sticky="nsew",
                     padx=(0 if i == 0 else 4, 0))
            kind = "done" if s.get("done") else "open"
            if kind == "done" or active:
                # 选中 / 已完成 → 上方一条色带
                bar = tk.Frame(box, bg=(T.ACCENT if active else T.TXT3), height=2)
                bar.pack(fill="x")
            else:
                tk.Frame(box, bg=bgc, height=2).pack(fill="x")
            name = str(s.get("name") or "")
            # 阶段名里带「·」（"读文献 · 摸清现状"），窄方块里会被断成
            # 「读文献·」+「摸清现状」两行，看着像结巴。这里拆成两段：
            # 主名一行（必要时省略），补充说明小一号字跟在下面。
            main, _, tail = name.partition(" · ")
            nl = tk.Label(box, text=main or name, bg=bgc, fg=fgc,
                          font=T.T_LABEL(), anchor="w", justify="left")
            nl.pack(fill="x", padx=7, pady=(4, 0))
            T.fill_wrap(nl, pad=20)
            if tail:
                tl = tk.Label(box, text=tail, bg=bgc,
                              fg=(T.TXT3 if s.get("done") else fgc),
                              font=T.T_CAPTION(), anchor="w", justify="left")
                tl.pack(fill="x", padx=7, pady=(1, 0))
                T.fill_wrap(tl, pad=20)
            tk.Label(box, text=_fmt_days(st, days), bg=bgc,
                     fg=(T.TXT3 if s.get("done") else fgc),
                     font=T.T_CAPTION(), anchor="w").pack(fill="x", padx=7, pady=(1, 6))
            for w in (box, *box.winfo_children()):
                w.bind("<Button-1>", lambda e, sid=s["id"]: self.pick_stage(sid))

        if self.stage_card.body.winfo_ismapped():
            try:
                self.stage_card.sync_now()
            except Exception:
                pass

    # ------------------------------------------------------------ 待办列表
    def _render_todos(self):
        self.todo_scroll.clear()
        todos = self.plan.get("todos") or []
        if not todos:
            self.todo_scroll.pack_forget()
            for c in (self._left, self._right):
                try:
                    c.grid_remove()
                    c._fill_y, c._fill_y_pinned = False, True
                except Exception:
                    pass
            self._body.grid_rowconfigure(0, weight=0)
            # 空态时把整个两栏区拿掉 —— 只 grid_remove 两栏不够：
            # body 自己是一个 pack(expand=True) 的 Frame，高度会吃满剩余空间
            # （实测 h=409、reqh=1），空态就被顶到页面下半屏去了。
            try:
                self._body.pack_forget()
            except Exception:
                pass
            for w in self._welcome.winfo_children():
                w.destroy()
            U.EmptyState(
                self._welcome, "还没有任何计划",
                "阶段是这条研究的骨架：读文献 → 定题 → 最小验证 → 完整实验 → 写稿。"
                "点「用推荐阶段起步」会按推荐天数把截止日铺好，之后每个日期都能改。",
                action=self.seed_defaults, action_text="用推荐阶段起步",
                extra=("直接加一条待办", self.add_todo), bg=T.BG).pack(fill="x")
            if not self._welcome.winfo_ismapped():
                # anchor="n" + 只 fill="x"：不传 expand 的话这块按自然高度
                # 贴在上方。给 EmptyState 传 expand=True 时 Tk 撑的是它自己
                # 的高度，空态会飘到页面中间去（踩过）。
                self._welcome.pack(fill="x", anchor="n", padx=T.PAD, pady=(8, 0))
            # 空计划时不摆「0 / 0」「已过期 0」——一串零看起来像系统算错了。
            # 指标行整体收起，等真有计划再出现。
            try:
                self._metrics.pack_forget()
            except Exception:
                pass
            try:
                self._stage_btn.pack_forget()
            except Exception:
                pass
            self.todo_count.config(text="")
            return

        if self._welcome.winfo_ismapped():
            self._welcome.pack_forget()
        for c in (self._left, self._right):
            try:
                if not c.winfo_ismapped():
                    c.grid()
                c.grid_configure(sticky="nsew")
                c._fill_y, c._fill_y_pinned = True, True
            except Exception:
                pass
        self._body.grid_rowconfigure(0, weight=1)
        if not self.todo_scroll.winfo_ismapped():
            self.todo_scroll.pack(fill="both", expand=True)
        if not self._metrics.winfo_ismapped():
            self._metrics.pack(fill="x")
        if not self._stage_btn.winfo_ismapped():
            try:
                self._stage_btn.pack(side="right", padx=(0, 6))
            except Exception:
                pass
        if not self._body.winfo_ismapped():
            # 与空态里的 pack_forget 配对：有数据时把两栏区重新挂回
            # （放在 metric_row 之后，位置与 _build 时一致）
            self._body.pack(fill="both", expand=True, padx=T.PAD,
                            pady=(0, 14), after=self.metric_row)

        done = sum(1 for t in todos if t.get("done"))
        self.todo_count.config(text="%d / %d 已完成" % (done, len(todos)))

        # 未完成排在前，已完成的沉到下面并淡化 —— 不删掉，让用户看得见
        # 自己做过什么（这是唯一一处「心理激励」，且不带分数）
        ordered = ([t for t in todos if not t.get("done")] +
                   [t for t in todos if t.get("done")])
        for t in ordered:
            self._todo_row(t)
        try:
            self.todo_scroll.refresh()
        except Exception:
            pass

    def _todo_row(self, t):
        st, days = PS.due_state(t.get("due"))
        active = self.sel_todo == t["id"]
        is_done = bool(t.get("done"))
        bg = T.ACCENT_D if active else T.CARD_HI
        f = tk.Frame(self.todo_scroll.inner, bg=bg, cursor="hand2")
        f.pack(fill="x", pady=2)

        row = tk.Frame(f, bg=bg)
        row.pack(fill="x", padx=8, pady=5)

        # 元信息（阶段 · 挂钩 · 剩余天数）**必须先 pack 右侧**。
        # 反过来让正文先 expand，Tk 会先把剩余宽度分给正文，元信息被挤到
        # 正文上面去 —— 2026-11-15 截图里就是「把 KITTI」和「…写试验」叠在
        # 一起。UNWRAP 到第二行（meta 放 row 下方独立一行）更稳：
        # 左侧列宽会随窗口变，正文要么被截断要么和 meta 抢位置。
        meta = []
        stg = self._stage_name(t.get("stage"))
        if stg:
            meta.append(stg)
        lt = PS.link_text(t.get("link"))
        if lt:
            meta.append(lt)
        if st != "none":
            meta.append(_fmt_days(st, days))

        top = tk.Frame(row, bg=bg)
        top.pack(fill="x")

        # 勾选框：用 Canvas 画，避免 Checkbutton 的白色系统底
        box = tk.Canvas(top, width=16, height=16, bg=bg, highlightthickness=0,
                        bd=0, cursor="hand2")
        box.pack(side="left", padx=(0, 8))
        if is_done:
            box.create_rectangle(1, 1, 15, 15, fill=T.OK, outline=T.OK)
            box.create_line(4, 8, 7, 11, 12, 5, fill=bg, width=2, capstyle="round")
        else:
            box.create_rectangle(1, 1, 15, 15, fill=bg, outline=T.TXT4)
        box.bind("<Button-1>", lambda e, tid=t["id"]: self.toggle(tid))

        txt = str(t.get("text") or "")
        lab = tk.Label(top, text=txt, bg=bg,
                       fg=(T.TXT3 if is_done else (T.TXT if active else T.TXT2)),
                       font=T.T_BODY_SM(), anchor="w", justify="left")
        # 正文换行跟随列表实际宽度（不要用 T.wrap —— 它会乘 DPI 缩放，
        # 在窄栏里必然溢出）
        lab.pack(side="left", fill="x", expand=True)
        T.fill_wrap(lab, pad=34)

        # 元信息单独一行，缩进对齐正文，不与标题抢宽度
        if meta:
            mrow = tk.Frame(row, bg=bg)
            mrow.pack(fill="x", padx=(24, 0), pady=(2, 0))
            tk.Label(mrow, text=" · ".join(meta), bg=bg,
                     fg=(T.TXT4 if is_done else _state_color(st)),
                     font=T.T_CAPTION(), anchor="w", justify="left").pack(
                side="left", fill="x", expand=True)

        for w in (f, row, top, lab):
            w.bind("<Button-1>", lambda e, tid=t["id"]: self.select(tid))

    # ------------------------------------------------------------ 详情
    def _render_detail(self):
        for w in self.detail_box.winfo_children():
            w.destroy()
        if self.sel_todo:
            self._todo_detail()
        elif self.sel_stage:
            self._stage_detail()
        else:
            self.detail_head.config(text="选一条待办或一个阶段")
            self.detail_sub.config(
                text="左边点待办可以改内容、挂阶段、挂选题；"
                     "上方点阶段可以改截止日期、标记完成。")
        try:
            self.detail_scroll.refresh()
        except Exception:
            pass

    def _get_todo(self, tid):
        for t in self.plan.get("todos") or []:
            if t["id"] == tid:
                return t
        return None

    def _get_stage(self, sid):
        for s in self.plan.get("stages") or []:
            if s["id"] == sid:
                return s
        return None

    def _stage_name(self, sid):
        s = self._get_stage(sid) if sid else None
        return str(s.get("name") or "") if s else ""

    def _todo_detail(self):
        t = self._get_todo(self.sel_todo)
        if not t:
            self.sel_todo = None
            return
        st, days = PS.due_state(t.get("due"))
        self.detail_head.config(text=str(t.get("text") or ""))
        sub = []
        if t.get("due"):
            sub.append("%s（%s）" % (t["due"], _fmt_days(st, days)))
        else:
            sub.append("没填截止日")
        sn = self._stage_name(t.get("stage"))
        if sn:
            sub.append("阶段：" + sn)
        lt = PS.link_text(t.get("link"))
        if lt:
            sub.append(lt)
        self.detail_sub.config(text=" · ".join(sub))

        box = self.detail_box
        T.Btn(box, "标记完成" if not t.get("done") else "撤销完成",
              lambda: self.toggle(t["id"]),
              "primary" if not t.get("done") else "ghost").pack(anchor="w", pady=(0, 10))

        self._kv(box, "内容", t.get("text") or "", edit=lambda: self.edit_text(t))
        self._kv(box, "截止", t.get("due") or "（没填）",
                 edit=lambda: self.edit_due_todo(t))
        stages = self.plan.get("stages") or []
        self._kv(box, "所属阶段", sn or "（不挂）",
                 edit=lambda: self.edit_stage_of_todo(t),
                 note=("共 %d 个阶段可挂" % len(stages)) if stages else "还没有阶段")

        row = U.WrapRow(box, bg=T.CARD)
        row.pack(fill="x", pady=(2, 6))
        row.add(T.Btn(row, "挂到选题", lambda: self.link_idea(t)))
        if t.get("link"):
            row.add(T.Btn(row, "解除挂钩",
                          lambda: self.unlink(t), "ghost"))

        T.Btn(box, "删除这条待办", lambda: self.del_todo(t["id"]), "danger").pack(
            anchor="w", pady=(12, 0))

    def _stage_detail(self):
        s = self._get_stage(self.sel_stage)
        if not s:
            self.sel_stage = None
            return
        st, days = PS.due_state(s.get("due"))
        self.detail_head.config(text=str(s.get("name") or ""))
        self.detail_sub.config(
            text=(s.get("due") or "没填截止日") + "  ·  " + _fmt_days(st, days))

        box = self.detail_box
        T.Btn(box, "标记完成" if not s.get("done") else "撤销完成",
              lambda: self.toggle_stage(s["id"]),
              "primary" if not s.get("done") else "ghost").pack(anchor="w", pady=(0, 10))
        self._kv(box, "阶段名", s.get("name") or "",
                 edit=lambda: self.edit_stage(s, "name", "改阶段名", "阶段名"))
        self._kv(box, "截止日", s.get("due") or "（没填）",
                 edit=lambda: self.edit_stage(s, "due", "截止日期", "到期日 YYYY-MM-DD"))

        todos = [t for t in (self.plan.get("todos") or []) if t.get("stage") == s["id"]]
        if todos:
            tk.Label(box, text="这个阶段的待办（%d 条）" % len(todos), bg=T.CARD,
                     fg=T.TXT3, font=T.T_CAPTION(), anchor="w").pack(
                fill="x", pady=(10, 4))
            for t in todos:
                mark = "✓ " if t.get("done") else "· "
                tk.Label(box, text=mark + str(t.get("text") or ""), bg=T.CARD,
                         fg=(T.TXT3 if t.get("done") else T.TXT2),
                         font=T.T_BODY_SM(), anchor="w", justify="left",
                         wraplength=T.wrap(380)).pack(fill="x")
        else:
            tk.Label(box, text="这个阶段下还没有待办。点上面的「加待办」，"
                               "在详情里把它挂到本阶段即可。",
                     bg=T.CARD, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                     justify="left", wraplength=T.wrap(380)).pack(fill="x", pady=(10, 0))

        r2 = tk.Frame(box, bg=T.CARD)
        r2.pack(fill="x", pady=(12, 0))
        T.Btn(r2, "在这个阶段加待办", lambda: self.add_todo(self.sel_stage)).pack(
            side="left")
        T.Btn(r2, "删除阶段", lambda: self.del_stage(s["id"]), "danger").pack(
            side="left", padx=(6, 0))

    def _kv(self, parent, key, val, edit=None, note=""):
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x", pady=(0, 6))
        tk.Label(row, text=key, bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(),
                 width=7, anchor="w").pack(side="left")
        tk.Label(row, text=val, bg=T.CARD, fg=T.TXT2, font=T.T_BODY_SM(),
                 anchor="w", justify="left", wraplength=T.wrap(280)).pack(
            side="left", fill="x", expand=True)
        if edit:
            b = T.Btn(row, "改", edit, "ghost")
            b.pack(side="right")
        return row

    # ------------------------------------------------------------ 交互
    def select(self, tid):
        self.sel_todo = tid
        self.sel_stage = None
        self._render_todos()
        self._render_stages()
        self._render_detail()

    def pick_stage(self, sid):
        self.sel_stage = sid
        self.sel_todo = None
        self._render_todos()
        self._render_stages()
        self._render_detail()

    def toggle(self, tid):
        PS.toggle_todo(tid)
        self.reload()

    def toggle_stage(self, sid):
        s = self._get_stage(sid)
        if not s:
            return
        PS.update_stage(sid, done=not s.get("done"))
        self.reload()

    def add_todo(self, stage=None):
        text = T.ask_text(self, "加待办", "这条待办要做什么？（一句话）", "")
        if not text:
            return
        due = T.ask_text(self, "加待办", "截止日期（YYYY-MM-DD，留空则不设）",
                         date.today().isoformat())
        tid = PS.add_todo(text, stage=stage or "", due=_norm_date(due))
        self.reload()
        self.select(tid)

    def add_stage(self):
        name = T.ask_text(self, "加阶段", "阶段名（如「最小验证」）", "")
        if not name:
            return
        # 默认给「今天 + 30 天」，用户嫌不对就改 —— 空白输入框更让人无从下手
        due = T.ask_text(self, "加阶段", "截止日期（YYYY-MM-DD）",
                         (date.today() + timedelta(days=30)).isoformat())
        sid = PS.add_stage(name, due=_norm_date(due))
        self.reload()
        self.pick_stage(sid)

    def seed_defaults(self):
        PS.seed_defaults()
        self.reload()
        self.app.toast("已按推荐铺好 5 个阶段，截止日期可以逐条改", T.OK)

    def edit_text(self, t):
        v = T.ask_text(self, "改内容", "这条待办要做什么？", t.get("text") or "")
        if v is None:
            return
        v = v.strip()
        if not v:
            return
        PS.set_todo(t["id"], text=v)
        self.reload()

    def edit_due_todo(self, t):
        v = T.ask_text(self, "改截止日期", "YYYY-MM-DD（留空 = 不设）",
                       t.get("due") or "")
        if v is None:
            return
        PS.set_todo(t["id"], due=_norm_date(v))
        self.reload()

    def edit_stage(self, s, field, title, prompt):
        v = T.ask_text(self, title, prompt, s.get(field) or "")
        if v is None:
            return
        if field == "due":
            v = _norm_date(v)
        elif not v.strip():
            return
        PS.update_stage(s["id"], **{field: v})
        self.reload()

    def edit_stage_of_todo(self, t):
        stages = self.plan.get("stages") or []
        if not stages:
            self.app.toast("还没有阶段，先点「加阶段」", T.WARN)
            return
        names = ["（不挂阶段）"] + [str(s.get("name") or "") for s in stages]
        cur = self._stage_name(t.get("stage"))
        idx = names.index(cur) if cur in names else 0

        dlg = tk.Toplevel(self)
        dlg.title("挂到哪个阶段")
        dlg.configure(bg=T.BG)
        dlg.transient(self.winfo_toplevel())
        var = tk.StringVar(value=names[idx])
        tk.Label(dlg, text="选一个阶段：", bg=T.BG, fg=T.TXT2,
                 font=T.T_BODY_SM()).pack(anchor="w", padx=18, pady=(16, 6))
        om = tk.OptionMenu(dlg, var, *names)
        om.config(bg=T.CARD_HI, fg=T.TXT, relief="flat", highlightthickness=0,
                  font=T.T_BODY_SM(), activebackground=T.CARD_HI,
                  activeforeground=T.TXT, bd=0)
        try:
            om["menu"].config(bg=T.CARD, fg=T.TXT, font=T.T_BODY_SM(),
                              activebackground=T.ACCENT_D, activeforeground=T.TXT)
        except Exception:
            pass
        om.pack(fill="x", padx=18)

        def ok(_=None):
            v = var.get()
            sid = "" if v == "（不挂阶段）" else next(
                (s["id"] for s in stages if str(s.get("name") or "") == v), "")
            PS.set_todo(t["id"], stage=sid)
            dlg.destroy()
            self.reload()

        row = tk.Frame(dlg, bg=T.BG)
        row.pack(fill="x", padx=18, pady=14)
        T.Btn(row, "确定", ok, "primary").pack(side="right")
        T.Btn(row, "取消", dlg.destroy).pack(side="right", padx=(0, 8))
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        try:
            dlg.grab_set()
        except Exception:
            pass

    def link_idea(self, t):
        """挂到一条选题。选项从创新点库实时读 —— 不从缓存读，
        因为用户很可能刚在另一页新增了一条。"""
        try:
            import kb_widget as kb
            ideas = list(kb.load_research_memory().get("ideas") or [])
        except Exception:
            ideas = []
        titles = [str(i.get("title") or "").strip() for i in ideas]
        titles = [x for x in titles if x]
        if not titles:
            # 选题库空着也不锁死：允许直接写一个研究方向
            v = T.ask_text(self, "挂到研究方向", "写一个研究方向（如「红外小目标检测」）", "")
            if v and v.strip():
                PS.set_todo(t["id"], link=PS.link_of_field(v.strip()))
                self.reload()
            return

        dlg = tk.Toplevel(self)
        dlg.title("挂到选题")
        dlg.configure(bg=T.BG)
        dlg.transient(self.winfo_toplevel())
        tk.Label(dlg, text="选一条创新点库里的选题：", bg=T.BG, fg=T.TXT2,
                 font=T.T_BODY_SM()).pack(anchor="w", padx=18, pady=(16, 6))
        var = tk.StringVar(value=titles[0])
        om = tk.OptionMenu(dlg, var, *titles)
        om.config(bg=T.CARD_HI, fg=T.TXT, relief="flat", highlightthickness=0,
                  font=T.T_BODY_SM(), activebackground=T.CARD_HI,
                  activeforeground=T.TXT, bd=0)
        try:
            om["menu"].config(bg=T.CARD, fg=T.TXT, font=T.T_BODY_SM(),
                              activebackground=T.ACCENT_D, activeforeground=T.TXT)
        except Exception:
            pass
        om.pack(fill="x", padx=18)

        def ok(_=None):
            PS.set_todo(t["id"], link=PS.link_of_idea(var.get()))
            dlg.destroy()
            self.reload()

        row = tk.Frame(dlg, bg=T.BG)
        row.pack(fill="x", padx=18, pady=14)
        T.Btn(row, "确定", ok, "primary").pack(side="right")
        T.Btn(row, "取消", dlg.destroy).pack(side="right", padx=(0, 8))
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        try:
            dlg.grab_set()
        except Exception:
            pass

    def unlink(self, t):
        PS.set_todo(t["id"], link=None)
        self.reload()

    def del_todo(self, tid):
        t = self._get_todo(tid)
        if not t:
            return
        if not T.ask_yes(self, "删除待办",
                         "确定删除「%s」？没有回收站。" % str(t.get("text") or "")[:40]):
            return
        PS.remove_todo(tid)
        if self.sel_todo == tid:
            self.sel_todo = None
        self.reload()

    def del_stage(self, sid):
        s = self._get_stage(sid)
        if not s:
            return
        n = sum(1 for t in (self.plan.get("todos") or [])
                if t.get("stage") == sid)
        msg = "确定删除阶段「%s」？" % str(s.get("name") or "")[:30]
        if n:
            msg += "它下面的 %d 条待办不会删，只是不再挂在这个阶段上。" % n
        if not T.ask_yes(self, "删除阶段", msg):
            return
        PS.remove_stage(sid)
        if self.sel_stage == sid:
            self.sel_stage = None
        self.reload()

    def set_weekly(self):
        cur = (self.plan.get("weekly") or {}).get("hours") or 0
        v = T.ask_text(self, "每周投入", "平均每周能拿出几小时做研究？（0 = 不设）",
                       ("%g" % cur) if cur else "10")
        if v is None:
            return
        PS.set_weekly(v)
        self.reload()
        self.app.toast("已记录每周投入", T.OK)


def _norm_date(s):
    """把用户随手写的日期收敛成 YYYY-MM-DD；认不出来就返回空串。

    接受的写法：2026-12-31 / 2026/12/31 / 20261231 / 12-31（补今年）。
    认不出来时**返回空串而不是报错** —— 截止日不是必填项。
    """
    if s is None:
        return ""
    t = str(s).strip().replace("/", "-").replace(".", "-").replace("年", "-")
    t = t.replace("月", "-").replace("日", "").strip()
    if not t:
        return ""
    parts = [p for p in t.split("-") if p]
    try:
        if len(parts) == 3:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            y, m, d = date.today().year, int(parts[0]), int(parts[1])
        elif len(parts) == 1 and len(parts[0]) == 8:
            v = parts[0]
            y, m, d = int(v[:4]), int(v[4:6]), int(v[6:])
        else:
            return ""
        return date(y, m, d).isoformat()
    except Exception:
        return ""