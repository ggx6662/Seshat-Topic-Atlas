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
import ui_kit as UK


class _PlanMeta(tk.Frame):
    """紧凑元信息；保留原指标控件的读写接口，不评价计划。"""

    def __init__(self, parent):
        super().__init__(parent, bg=T.BG)
        self._vals = {}
        self._summary = tk.Label(self, text="", bg=T.BG, fg=T.TXT3,
                                 font=T.T_CAPTION(), anchor="w", justify="left",
                                 wraplength=1)
        self._summary.pack(fill="x", pady=(0, T.sp(4)))
        T.fill_wrap(self._summary, pad=4)

    def set_values(self, values):
        self._vals.update({str(k): str(v) for k, v in values.items()})
        # 四项之间用不换行空格（U+00A0）连起来，让 Tk 的折行只在
        # 「项与项之间」断开。用普通空格的话，「8 小时」会被拆成
        # 「…每周投入 8」/「小时」，1080 宽下实测就是这一行。
        # 分隔符本身用 ·，两侧各留一个 NBSP，断行点落在 · 上最自然。
        self._summary.config(text="\u00a0·\u00a0".join(
            "%s\u00a0%s" % (key, self._vals.get(key, "—"))
            for key in ("当前阶段", "待办", "已过期", "每周投入")))

    def values(self):
        return dict(self._vals)

    @property
    def expanded(self):
        return False


class _StageStrip(tk.Frame):
    """截止权重分配宽度；窄屏分行并给完整文字留出阅读下限。"""

    def __init__(self, parent):
        super().__init__(parent, bg=T.CARD, height=1)
        self.entries = []
        self._job = None
        self.bind("<Configure>", self._request_layout)

    def _request_layout(self, _event=None):
        if self._job is None:
            self._job = self.after_idle(self._layout)

    def _layout(self):
        self._job = None
        width = self.winfo_width()
        if width <= 1 or not self.entries:
            return
        gap = T.sp(6)
        minimum = T.sp(132)
        cols = max(1, min(len(self.entries), (width + gap) // (minimum + gap)))
        rows = []
        for start in range(0, len(self.entries), cols):
            entries = self.entries[start:start + cols]
            avail = width - gap * (len(entries) - 1)
            # 先按原截止权重分配，过窄的块锁到阅读下限，其余继续按权重分。
            floor = min(minimum, avail // len(entries))
            sizes = [0] * len(entries)
            pending = list(range(len(entries)))
            remaining = avail
            while pending:
                total = sum(entries[i][1] for i in pending)
                small = [i for i in pending
                         if remaining * entries[i][1] / total < floor]
                if not small:
                    for i in pending:
                        sizes[i] = int(remaining * entries[i][1] / total)
                    sizes[pending[-1]] += remaining - sum(sizes[i] for i in pending)
                    break
                for i in small:
                    sizes[i] = floor
                    remaining -= floor
                    pending.remove(i)
            x = 0
            for (box, _weight, labels), size in zip(entries, sizes):
                for label in labels:
                    label.config(wraplength=max(1, size - T.sp(18)))
                box.place(x=x, y=0, width=size)
                x += size + gap
            rows.append((entries, sizes))
        self._job = self.after_idle(lambda: self._finish_layout(rows, width, gap))

    def _finish_layout(self, rows, width, gap):
        self._job = None
        if width != self.winfo_width():
            self._request_layout()
            return
        y = 0
        for entries, sizes in rows:
            height = max(box.winfo_reqheight() for box, _, _ in entries)
            x = 0
            for (box, _, _), size in zip(entries, sizes):
                box.place(x=x, y=y, width=size, height=height)
                x += size + gap
            y += height + gap
        wanted = max(1, y - gap)
        if self.winfo_height() != wanted:
            self.config(height=wanted)

    def destroy(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        super().destroy()

PAGE_HINT = "阶段与截止 · 待办勾选 · 挂选题 · 每周投入"

PLAN_HELP = """\
这里是你自己排的科研进度，和左边那几个页面不是一回事：那些页面给你材料，这一页排你的时间。

一、上方的阶段横条
· 每个阶段一个方块，宽度按截止日与今天的天数差分配；窄屏保留阅读下限并分行。
· 颜色只表状态：灰色还没到、黄色 7 天内、红色已经过期。已完成的淡化，选中的浅棕强调。
· 横条只做减法 —— 拿截止日期减今天。系统**不预测**你几天能做完，因为没有任何数据支撑。

二、待办
· 勾一下就完成，再点一次撤销。没有「归档」，勾掉的会留在原位并淡化。
· 待办可以挂到某个阶段下（右侧详情里能改），也可以不挂。
· 可以挂到一条选题或一个研究方向，之后在总览页和选题页能对上。

三、每周投入
· 点「每周投入」记录平均一周能拿出几小时，也可以设为 0 表示不设。
· 这里只展示投入，不根据待办条数估算工期，也不拿它评价进度。

四、这里不做的事
不打分，不排期，不弹窗提醒。过期的东西标红，剩下的由你自己决定。"""


def _fmt_days(st, days):
    if st == "none":
        return "没填截止日"
    if st == "over":
        return "已逾期 %d 天" % (-days)
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
        top.pack(fill="x", padx=T.PAD, pady=(T.sp(8), T.sp(10)))
        title_row = tk.Frame(top, bg=T.BG)
        title_row.pack(fill="x")
        actions = WrapRow(title_row, bg=T.BG, gap=T.sp(6))
        actions.config(width=T.sp(360))
        actions.pack(side="right", anchor="n")
        tk.Label(title_row, text="研究计划", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE(), anchor="w").pack(side="left")
        actions.add(T.Btn(actions, "加待办", self.add_todo, "primary"))
        # 单独的宿主可隐藏，不从 WrapRow 的控件列表里销毁或摘除按钮。
        self._stage_action = tk.Frame(actions, bg=T.BG)
        self._stage_btn = T.Btn(self._stage_action, "加阶段", self.add_stage)
        self._stage_btn.pack()
        actions.add(self._stage_action)
        actions.add(T.Btn(actions, "每周投入", self.set_weekly))
        self._hint = U.Hint(top, PLAN_HELP,
                            summary="由你安排阶段与截止，不自动排期 · 使用说明", bg=T.BG)
        self._hint.pack(fill="x", pady=(4, 0))
        T.fill_wrap(self._hint._detail, pad=4)

        # 这个宿主始终保留，作为阶段横条与正文重新 pack 时的顺序锚点。
        self.metric_row = tk.Frame(self, bg=T.BG)
        self.metric_row.pack(fill="x", padx=T.PAD)
        self._metrics = _PlanMeta(self.metric_row)
        self._metrics.pack(fill="x")

        self.stage_card = T.Card(self, pad=T.sp(12), fill_y=False)
        self.stage_card.pack(fill="x", padx=T.PAD, pady=(T.sp(8), T.sp(10)))
        # 2026-11-20：卡头单独存引用 —— 空间极紧时要把它收起来。
        # 1080×680 + xlarge 字号档（_FS=1.3）下，这一行「阶段与截止 ·
        # 点击修改」连 pady 要 45px，收起来正好够待办露出第一条。
        self._stage_head = tk.Label(
            self.stage_card.body, text="阶段与截止 · 点击修改", bg=T.CARD,
            fg=T.TXT3, font=T.T_CAPTION(), anchor="w")
        self._stage_head.pack(fill="x", pady=(0, 6))
        self.stage_scroll = T.ScrollArea(self.stage_card.body, bg=T.CARD, height=T.sp(128))
        self.stage_scroll.pack(fill="x")
        # 记住卡头被收起来之前的位置 —— pack_forget 之后想放回去必须给 before=，
        # 否则它会跑到 stage_scroll 后面去（实测放回一次阶段条就沉到卡片底下）。
        self._stage_head_before = self.stage_scroll
        self._stage_scroll_ref = self.stage_scroll
        self.stage_box = self.stage_scroll.inner
        # 2026-11-20：窗口最小尺寸 1080×680 时，阶段卡要吃掉 214px 里的大半，
        # 而下面的待办列表和计划详情是真正要操作的东西 —— 阶段条占 128 之后
        # 待办只剩 73px（两行都看不全）。改成按页高收阶段条：矮窗里压到 96，
        # 阶段仍然能滚，但把空间还给待办。
        self.bind("<Configure>", self._fit_stage_height, add="+")
        # 首帧 <Configure> 不一定还会来（PagePlan 是 pack(expand=True) 的，
        # 父容器高度定下来以后它自己的高度就没再变过，实测 _stage_h 一直是
        # None、阶段条停在 147）。所以建完先排一次，reload 之后再排一次。
        self.after_idle(self._fit_stage_height)

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, T.sp(14)))
        body.grid_columnconfigure(0, weight=2, minsize=T.sp(260), uniform="plan")
        body.grid_columnconfigure(1, weight=3, minsize=T.sp(320), uniform="plan")
        body.grid_rowconfigure(0, weight=1)
        self._body = body

        left = T.Card(body, pad=T.sp(12))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, T.sp(10)))
        self._left = left
        UK.eyebrow(left.body, "TO DO", "02").pack(fill="x")
        head = tk.Frame(left.body, bg=T.CARD)
        head.pack(fill="x", pady=(4, 8))
        self.todo_count = tk.Label(head, text="", bg=T.CARD, fg=T.TXT3,
                                   font=T.T_CAPTION(), anchor="e")
        self.todo_count.pack(side="right")
        tk.Label(head, text="待办清单", bg=T.CARD, fg=T.TXT, font=T.T_SECTION(),
                 anchor="w").pack(side="left")
        self.todo_scroll = T.ScrollArea(left.body, bg=T.CARD)
        self.todo_scroll.pack(fill="both", expand=True)

        right = T.Card(body, pad=T.sp(16))
        right.grid(row=0, column=1, sticky="nsew")
        self._right = right
        UK.eyebrow(right.body, "PLAN DETAIL", "03").pack(fill="x", pady=(0, 8))
        # 标题、挂钩和操作全部在同一个滚动正文中，长内容不会挤掉编辑区。
        self.detail_scroll = T.ScrollArea(right.body, bg=T.CARD)
        self.detail_scroll.pack(fill="both", expand=True)
        self.detail_head = tk.Label(self.detail_scroll.inner, text="选一条待办或一个阶段",
                                    bg=T.CARD, fg=T.TXT, font=T.T_SECTION(), anchor="w",
                                    justify="left", wraplength=1)
        self.detail_head.pack(fill="x")
        T.fill_wrap(self.detail_head, pad=4)
        self.detail_sub = tk.Label(self.detail_scroll.inner, text="", bg=T.CARD, fg=T.TXT3,
                                   font=T.T_CAPTION(), anchor="w", justify="left",
                                   wraplength=1)
        self.detail_sub.pack(fill="x", pady=(4, 12))
        T.fill_wrap(self.detail_sub, pad=4)
        self.detail_box = tk.Frame(self.detail_scroll.inner, bg=T.CARD)
        self.detail_box.pack(fill="x")
        self._welcome = tk.Frame(self, bg=T.BG)
        for area in (self.stage_scroll, self.todo_scroll, self.detail_scroll):
            area.canvas.bind("<Configure>", lambda e, a=area:
                             a.canvas.itemconfigure(a._win, height=0), add="+")

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
        cur_txt = str(cur.get("name") or "") if cur else "—"
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
            self.stage_card.pack_forget()
            return
        if not self.stage_card.winfo_manager():
            self.stage_card.pack(fill="x", padx=T.PAD, pady=(T.sp(8), T.sp(10)),
                                 after=self.metric_row)

        row = _StageStrip(self.stage_box)
        row.pack(fill="x")
        for s in stages:
            st, days = PS.due_state(s.get("due"))
            # 2026-11-20：权重改成「越紧急越宽」。
            # 旧公式 min(120, max(6, abs(days)+1)) 让「还剩 40 天」拿到 41、
            # 「已逾期 3 天」只有 4 —— 差 10 倍，1080 下第三块独占 466px
            # 而前两块被地板锁在 132，于是「已逾期」那一格最窄、日期和
            # 「还剩 N 天」被折成两行往下溢出。现在按状态给档：
            # 逾期 3.0、7 天内 2.4、较远 1.6、没填 1.2，彼此差距不超过
            # 2.5 倍，宽度大致均匀，紧急的那块略宽一眼能看出来。
            weight = {"over": 3.0, "soon": 2.4, "none": 1.2}.get(st, 1.6)
            if s.get("done"):
                weight = 1.0  # 已完成的最窄，把空间让给还没做的
            active = self.sel_stage == s["id"]
            if s.get("done"):
                bgc, fgc = T.CARD_HI, T.TXT3
            elif active:
                bgc, fgc = T.tint(T.ACCENT, 0.10, T.CARD), T.ACCENT
            else:
                bgc, fgc = T.tint(_state_color(st), 0.08, T.CARD), _state_color(st)
            box = tk.Frame(row, bg=bgc, cursor="hand2")
            tk.Frame(box, bg=T.ACCENT if active else (T.TXT3 if s.get("done") else bgc),
                     height=2).pack(fill="x")
            main, _, tail = str(s.get("name") or "").partition(" · ")
            labels = []
            nl = tk.Label(box, text=main, bg=bgc, fg=fgc, font=T.T_LABEL(),
                          anchor="w", justify="left", wraplength=1)
            nl.pack(fill="x", padx=T.sp(7), pady=(T.sp(6), 0))
            labels.append(nl)
            if tail:
                tl = tk.Label(box, text=tail, bg=bgc, fg=fgc, font=T.T_CAPTION(),
                              anchor="w", justify="left", wraplength=1)
                tl.pack(fill="x", padx=T.sp(7), pady=(2, 0))
                labels.append(tl)
            due = s.get("due") or "未设截止"
            status = "已完成" if s.get("done") else _fmt_days(st, days)
            dl = tk.Label(box, text=due + "\n" + status, bg=bgc, fg=fgc,
                          font=T.T_CAPTION(), anchor="w", justify="left", wraplength=1)
            dl.pack(fill="x", padx=T.sp(7), pady=(4, T.sp(7)))
            labels.append(dl)
            row.entries.append((box, weight, labels))
            for w in (box, *box.winfo_children()):
                w.bind("<Button-1>", lambda e, sid=s["id"]: self.pick_stage(sid))
                self.stage_scroll._bind_wheel(w)
        row._request_layout()
        self.stage_scroll.canvas.itemconfigure(self.stage_scroll._win, height=0)
        self.stage_scroll.refresh(defer=True)
        # 2026-11-20：阶段方块宽度是按截止状态分配的，要等 _StageStrip
        # 的 after_idle 布局跑完，inner 的 reqheight 才是真实值（首帧会报
        # 265/332 这种虚高值）。所以这里排一次延迟重算：150ms 足够让
        # place 布局与 wraplength 重折走完，届时 need 稳定在 149。
        self.after(150, self._fit_stage_height)

        if self.stage_card.body.winfo_ismapped():
            try:
                self.stage_card.sync_now()
            except Exception:
                pass

    # ------------------------------------------------------------ 待办列表
    def _fit_stage_height(self, e=None):
        """矮窗里收阶段横条，把高度让给待办列表。

        1080×680（窗口最小尺寸）下页面只有 594px：页头 + 页签 + 阶段卡
        之后，留给「待办 / 详情」两栏的只剩约 180px。阶段条按 128 固定
        高度取走后待办只剩 73px，一条完整待办都看不全。

        判据用**剩余高度**而不是页面总高：选中某条待办后详情区会长出来，
        页面总高不变但两栏变矮，用总高分档会把阶段条重新撑回去。
        """
        try:
            page_h = int(e.height) if e is not None else self.winfo_height()
            if page_h <= 1:
                return
            # 固定开销只算「页头」和「页签」：它们恒在页面上、高度稳定。
            # 不能遍历页面子件求和 —— 欢迎块在有数据时是 pack_forget 的，
            # reqheight 仍会被内容撑到 340，加进来 fixed 就上千、body_room
            # 变成负数（实测 838 / -244、1082 / -488）。
            # 页头 = 第一个 pack 的 Frame；页签 = metric_row 之前的那个。
            fixed = 0
            for ch in self.winfo_children():
                if ch in (self.stage_card, getattr(self, "_body", None),
                          getattr(self, "_welcome", None)):
                    continue
                if not ch.winfo_ismapped():
                    continue
                # 只认**已经量出实际高度**的块：截图把窗口顶到前台之后，
                # 有些容器会短暂回到「可见但高度 1、reqh 上千」的状态
                # （实测出现过 reqh=1241、h=1 的 Frame），把它的 reqh 加进
                # fixed 会把 room 算成 144，阶段条被误压到 73。
                hh = int(ch.winfo_height())
                if hh <= 1:
                    continue
                if int(ch.winfo_reqheight()) > T.sp(160):
                    # 高于 160 的可见块不是页头/页签（那是正文），跳过。
                    continue
                fixed += hh
            fixed += int(self.stage_card.winfo_height()) \
                if int(self.stage_card.winfo_height()) > 1 \
                else int(self.stage_card.winfo_reqheight())
            self._stage_fixed_parts = []
            for ch in self.winfo_children():
                if ch in (self.stage_card, getattr(self, "_body", None),
                          getattr(self, "_welcome", None)):
                    continue
                self._stage_fixed_parts.append(
                    (ch.winfo_class(), ch.winfo_ismapped(),
                     int(ch.winfo_reqheight()), int(ch.winfo_height())))
            body_room = page_h - fixed
            # 2026-11-20：上面按子件加总的 fixed 只用于日志与兜底。
            # 真正稳定的判据是 **_body 的实际高度** —— 它直接就是
            # 「阶段条 + 待办/详情两栏」能分到的空间，不依赖页头/页签
            # 的量测时机。截图把窗口顶到前台时，容器会短暂回到
            # 「可见、h=1、reqh=1241」的中间态，把 reqh 加进 fixed 会把
            # room 算成 144（实测），阶段条就被误压到 73。
            try:
                bh = int(getattr(self, "_body", None).winfo_height())
                if bh > 1:
                    body_room = bh
            except Exception:
                pass
            self._stage_dbg = (page_h, fixed, body_room)
            # 2026-11-20：先看阶段条**按内容需要多高**，够就照给。
            # 阶段方块里是两行字（阶段名 + 状态），两行都放得下才叫「不裁」。
            # 旧实现无条件先减一个「给待办留 104」再夹到 56，于是 1080 下
            # 阶段条被压到 64、第二行「消融与停止条件」被切掉，而同一屏里
            # 待办区还有 150px 空着 —— 两头都不对。
            need = T.sp(128)
            try:
                # 2026-11-20：**不能**用 stage_card.winfo_reqheight() 当 need。
                # canvas 一被设高，卡片的 reqheight 立刻跟着涨到同一个数
                # （反馈环：330 → reqh 330 → need 330 → want 330 ……），
                # 实测三档全被撑爆、待办只剩 8~22px。
                # 改成自己按零件拼：卡头 Label + 6 + 滚动区内容 + 卡内边距。
                # 这几个量都跟 canvas 多高无关，是真正的「按内容需要多高」。
                head_h = 0
                for ch in self.stage_card.body.winfo_children():
                    if ch is self.stage_scroll:
                        continue
                    # 2026-11-20：pack_forget() 之后 winfo_height() 仍保留
                    # 旧值，必须按 ismapped 过滤，否则卡头收起来之后还按
                    # 33+6 计入 need，阶段条白占 40px。
                    if not ch.winfo_ismapped():
                        continue
                    hh = int(ch.winfo_height())
                    if hh > 1:
                        head_h += hh
                if head_h:
                    head_h += 6          # 卡头 Label 的 pady=(0, 6)
                strip_h = 0
                for ch in self.stage_box.winfo_children():
                    hh = int(ch.winfo_height())
                    if hh > 1:
                        strip_h = max(strip_h, hh)
                if strip_h <= 0:
                    strip_h = int(self.stage_scroll.inner.winfo_reqheight())
                if strip_h > 1:
                    need = max(T.sp(72), head_h + strip_h
                               + int(T.sp(12)) * 2)
            except Exception:
                pass
            # 待办栏的卡内固定开销：卡边距 + eyebrow + 「待办清单」标题行 ≈ 60。
            # 用常量而不是 left 高度减 todo_scroll 高度 —— left 本身由
            # todo_scroll 撑出来，那样是自引用，一改就两头一起缩。
            todo_fixed = T.sp(60)
            # 2026-11-20：判据必须在**与阶段条高度无关**的量上做。
            # body_room 取的是 _body 的实际高度，而 _body 与 stage_card 是
            # 同一层的兄弟，pack 共享纵向空间 —— 阶段条一涨 body_room 就跌，
            # 反过来把 want 压小，来回打架（实测 1080 下阶段条被算成 265，
            # 用完 332 的旧 need，把待办挤到 22px）。
            # 所以这里改用「页面总高 − 页头页签 − 页间距」= 两栏能分到的
            # 总高度，再从中划分阶段条与待办，二者互不反馈。
            page_fixed = 0
            for ch in self.winfo_children():
                if ch in (self.stage_card, getattr(self, "_body", None),
                          getattr(self, "_welcome", None)):
                    continue
                if not ch.winfo_ismapped():
                    continue
                hh = int(ch.winfo_height())
                if hh > 1:
                    # 2026-11-20：以前这里有个 `reqheight <= T.sp(160)` 的过滤，
                    # 本意是跳过「可见但还没排版」的正文块。但页签 Frame
                    # 的 reqheight 也会随内容涨（实测 41 能过、再长一点就
                    # 被跳过），于是 page_fixed 只统计到页头 111，space
                    # 多算了 60 多像素，判据永远偏宽松、卡头永远收不起来。
                    # 现在只认**已经量出真实高度**的块，不看 reqheight。
                    page_fixed += hh
            # 2026-11-20：shared 用「阶段卡实际高 + 两栏实际高」。
            # 这两个都是 pack 分出来的真实高度，二者之和在 page_h 不变时
            # 是**不变量** —— 阶段条涨多少，两栏就少多少，总和恒定。
            # 所以拿它当等式右边是安全的闭式解，不会像 body_room 那样
            # 形成反馈环。
            # 不能用 page_h 减常量：回归里先跑完其它页面再进计划页时，
            # 页面可用高度会少 60px 左右（353 vs 415），固定常量立刻失准。
            try:
                sz = int(self.stage_card.winfo_height())
                bz = int(getattr(self, "_body", None).winfo_height())
                shared = (sz + bz) if (sz > 1 and bz > 1) else 0
            except Exception:
                shared = 0
            fresh = getattr(self, "_stage_body_fresh", 0)
            if fresh:
                # 两栏刚 pack 回来，尺寸是旧值，这两轮一律走兜底。
                shared = 0
                self._stage_body_fresh = fresh - 1
            if shared <= 0:
                shared = page_h - int(T.sp(179))
            if shared <= 0:
                return
            self._stage_shared = shared
            self._stage_fixed_parts = page_fixed   # 只留作日志
            todo_need = T.sp(104) + todo_fixed    # 待办栏体面可用的高度
            # ----------------------------------------------------------
            # 2026-11-20 重写这一段。之前的版本有几个互相打架的量：
            #   · need 随「卡头收没收」变化（head_h 用 ismapped 过滤）；
            #   · tight 又拿 shared 判，而 shared = 卡片高 + 两栏高，
            #     卡头一收卡片就变矮、shared 跟着变，判据于是变松，
            #     下一轮又把卡头放回去 —— 来回翻，待办停在 41px。
            #
            # 现在把三件事解耦：
            #   ① head_full 恒按 reqheight 算（收没收都一样），是常量；
            #   ② 判据用**空间账**，不用控件实测高度：
            #        space = page_h − 页头页签 page_fixed − 卡片外距 − 卡内边距
            #      这是一个只跟窗口尺寸有关的数，卡头收放不影响它；
            #   ③ want 只由 space 与 todo_need 决定，写完下一轮读回同一个值。
            # 「卡片外距」= stage_card 的 pack pady 上下之和（8 + 10 设计像素）。
            # ----------------------------------------------------------
            head_full = 0
            try:
                head_full = int(self._stage_head.winfo_reqheight()) + int(T.sp(6))
            except Exception:
                head_full = 0
            pad_in = int(T.sp(12)) * 2          # 阶段卡的上下内边距
            card_gap = int(T.sp(8)) + int(T.sp(10))
            strip_need = max(105, int(need) - (head_full + pad_in))
            # space：阶段卡 + 两栏能分到的总高度（与卡头无关）
            # 2026-11-20：用实测的 shared（stage_card + _body）而不是
            # page_h − page_fixed − card_gap 的账面值。账面上乘漏算了
            # 页头/页签/卡片之间的三处 pady，实测 space 比真值多 47px，
            # 判据于是永远偏宽松、卡头永远收不起来，待办停在 44px。
            # shared 是 pack 分出来的真实高度之和，卡头收放会改变它，
            # 但这里只用它做**一次**判断，用完就按固定规则写 canvas 高度，
            # 写完之后 shared 的变化方向与 want 的变化方向一致，不会再翻。
            space = shared if shared > 0 else (page_h - page_fixed - card_gap)
            if space <= 0:
                space = page_h - int(T.sp(179))
            want_with_head = int(need)
            want_without_head = strip_need + pad_in
            # 2026-11-20：判据里只有 want_with_head 一项，没有 todo_need。
            # 之前写成 `space - want_with_head >= todo_need + pad_in`，等于
            # 要求「阶段条按满高给完以后，待办还能有 213+24」，1080×680 下
            # 永远不可能成立，于是 tight 恒为 True，可卡头又不收（收不收的
            # 判据和 want 的算法用了两套不同的空间账）。
            # 现在的口径统一成一句话：**卡头只在「留了它，待办就低于体面高度」
            # 时才收**；收不收都用同一个 space。
            if space - want_with_head >= todo_need:
                tight = False                  # 留卡头也够
            else:
                tight = True                   # 收卡头，把 45px 让给待办
            try:
                # 2026-11-20：判据统一用 winfo_manager()，不能用 winfo_ismapped()。
                # 页面刚建好、还没真正映射到屏幕时 ismapped() 返回 0，可卡头其实
                # 是 pack 着的 —— 于是 `tight and ismapped()` 为假、`not tight` 也为假，
                # 两个分支都不走，卡头永远收不起来。实测 1080×680 全页回归里
                # 连续九轮都是 (True, 353, 105, 'pack')，卡片白占 44px，待办卡在 58px。
                _mgr = self._stage_head.winfo_manager()
                if tight and _mgr:
                    self._stage_head.pack_forget()
                elif not tight and not _mgr:
                    self._stage_head.pack(fill="x", pady=(0, 6),
                                          before=self._stage_scroll_ref)
            except Exception:
                pass
            # want 是 canvas 的高度（不含卡内边距）
            # 2026-11-20：tight 时 cap 不能再等于 strip_need（阶段条内容原高）。
            # 那样 canvas 正好放得下内容，scrollregion 与可视高度相等，
            # 阶段条就退化成一根不可滚的静态条 —— 阶段多到五六块时后面几块
            # 直接看不见。这里留一行的滚动余量（strip_need - sp(30)），
            # 保证任何档位下阶段区都真的能滚。
            cap = (max(105, strip_need - int(T.sp(30))) if tight
                   else max(105, int(need) - pad_in))
            # 2026-11-20：给待办留的最低高度是「体面高度」与「一条待办」
            # 之间的保守值。真实回归（1080×680、跑完十几张截图之后）里
            # space 会从 372 掉到 353，按 todo_need=213 卡出来的 want 让
            # 待办只剩 58px —— 差 2px 就低于 60 的断言线，而 58px 本来
            # 也放不下一条完整待办（实测单条要 66px）。
            # 所以这里不再用 todo_need 当硬指标，而是取两者较小值：
            # 空间富裕时按 todo_need 划分，空间紧张时保证待办至少能露出一条。
            one_row = int(T.sp(56))           # 一条完整待办（两行字 + 内距）
            reserve = min(int(todo_need), max(one_row, int(todo_need)))
            room = space - pad_in - reserve
            if room >= cap:
                want = int(cap)
            else:
                want = int(max(105, min(cap, room)))
            self._stage_dbg2 = (page_h, shared, need, todo_fixed,
                                T.sp(104), want)
            self._stage_dbg3 = (tight, head_full, page_fixed, space, pad_in, want)
            # 2026-11-20：取消「只降不升」。它当初是为了防抖动，但真正造成抖动的
            # 量测已经改成自然高度了；留着它反而会把一次正确的大值锁死在
            # 一次错误的中间态上（实测 1240 下算对 130 之后被压回 73 就再
            # 也不上去了）。
            self._stage_pg = page_h
            self._stage_room = shared
            # 记录每一轮 tight 的取值序列（排查「卡头来回翻」用）
            try:
                _hist = getattr(self, "_stage_hist", None)
                if _hist is None:
                    _hist = self._stage_hist = []
                _hist.append((tight, space, want, self._stage_head.winfo_manager() or "-"))
                if len(_hist) > 24:
                    del _hist[:-24]
            except Exception:
                pass
            _bh_now = int(getattr(self, "_body", None).winfo_height())
            _sh_now = int(self.stage_card.winfo_height())
            # 2026-11-20：只要 _body 量到了真实高度就允许改布局。
            # **不要**把 stage_card 的实际高度也算进这个判据：卡片高度本来
            # 就随着我们写进去的 want 变化，拿它做守门条件会让这个函数
            # 自己把自己判成「不可信」，于是每轮 after_idle 重排一次，
            # 实测 1080×680 特大字档下会无限抖（todo 19px、CPU 打满）。
            self._stage_dbg3 = (page_h, _sh_now, _bh_now, want, need,
                                page_fixed, space, head_full)
            # 2026-11-20：缓存键必须带上 need。首帧量 inner 时布局还没跑完，
            # reqheight 会报 265/332 这种虚高值；算出的 want 也被放大并写进
            # _stage_h，之后 need 回落到真实值 149，但 want 换算下来仍是
            # 同一个数，短路 return 就把虚高的高度永远锁死了（实测 1440
            # 下阶段条停在 265、待办只剩 108）。带上 need 后，内容一稳定
            # 就会重算并收回多余高度。
            # 2026-11-20：缓存键要带上「卡头此刻显示与否」。只按 (want, need)
# 短路的话，某一轮算出的 want 恰好与上一轮相同、但卡头的显示状态被别的
# 路径（重新 pack、页面重建）改掉了，就会永远停在错的状态上 ——
# 实测 1080×680 回归里卡头一直显示，阶段卡白占 44px，待办卡在 58px。
            _key = (want, need, bool(self._stage_head.winfo_manager()))
            if getattr(self, "_stage_key", None) == _key:
                return
            self._stage_key = _key
            self._stage_h = want
            # 高度挂在 canvas 上：ScrollArea 是个 Frame，pack(fill="x") 时
            # 它的高度由内部 canvas 的请求高度决定，configure(height=) 改
            # Frame 自身并不会让可视区变矮（实测改了以后 canvas 仍是 147）。
            self.stage_scroll.canvas.configure(height=want)
            # 改完 canvas 的请求高度，stage_card 的 reqheight 才更新；
            # 这一轮的 body_room 是按旧值算的，下一轮 idle 再校正一次
            # （否则 1080 下两栏只有 180px，待办被压到 63px）。
            if not getattr(self, "_stage_pass", 0):
                self._stage_pass = 1
                self.after_idle(self._fit_stage_height)
            else:
                self._stage_pass = 0
        except Exception:
            pass

    def _render_todos(self):
        # 选中/清空待办都会改变两栏的高度关系，重新算一次阶段条。
        self.after_idle(self._fit_stage_height)
        # 2026-11-20：还要补一次「等布局稳定之后」的重算。窗口被顶到
        # 前台/截图之后 _body 会短暂量小（1080 下实测 144，真实 223），
        # 那一次算出来的 stage_h 会被写死，然后再没有任何事件触发重算。
        self.after(180, self._fit_stage_height)
        self.todo_scroll.clear()
        todos = self.plan.get("todos") or []
        if not todos and not (self.plan.get("stages") or []):
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
            UK.EmptyPanel(
                self._welcome, "从一条待办开始",
                "直接记录下一步，或用推荐阶段起步；所有截止日期都可以自行修改。",
                icon="calendar", cta="用推荐阶段起步", cta_cmd=self.seed_defaults,
                bg=T.BG, height=T.sp(250)).pack(fill="x", pady=(0, 8))
            T.Btn(self._welcome, "直接加一条待办", self.add_todo).pack(anchor="center")
            if not self._welcome.winfo_manager():
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
            self.todo_count.config(text="")
            return

        if self._welcome.winfo_manager():
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
        if not self._body.winfo_ismapped():
            # 与空态里的 pack_forget 配对：有数据时把两栏区重新挂回
            # （放在 metric_row 之后，位置与 _build 时一致）
            self._body.pack(fill="both", expand=True, padx=T.PAD,
                            pady=(0, T.sp(14)),
                            after=self.stage_card if self.stage_card.winfo_manager()
                            else self.metric_row)
            # 2026-11-20：刚挂回来的那一帧，_body 的高度还是收起前的旧值
            # （实测 1080 下 stage_card 214 + body 180 量出来只有 370，
            # 而真正可用是 394），用旧值算 shared 会把阶段条抬高、
            # 反过来把待办挤成 19px。这里打一个标记，让紧接的两次
            # 高度重算走 page_h 兜底，等布局稳定再切回实测值。
            self._stage_body_fresh = 2

        done = sum(1 for t in todos if t.get("done"))
        self.todo_count.config(text="%d / %d 已完成" % (done, len(todos)))

        # 未完成排在前，已完成的沉到下面并淡化 —— 不删掉，让用户看得见
        # 自己做过什么（这是唯一一处「心理激励」，且不带分数）
        ordered = ([t for t in todos if not t.get("done")] +
                   [t for t in todos if t.get("done")])
        for t in ordered:
            self._todo_row(t)
        if not todos:
            UK.EmptyPanel(
                self.todo_scroll.inner, "这个计划还没有待办",
                "先选阶段查看截止，或把下一步挂到这个阶段。",
                icon="calendar", cta="加待办", cta_cmd=lambda: self.add_todo(self.sel_stage),
                bg=T.CARD, height=T.sp(240)).pack(fill="x", pady=(8, 0))
        self.todo_scroll.canvas.itemconfigure(self.todo_scroll._win, height=0)
        self.todo_scroll.refresh(defer=True)

    def _todo_row(self, t):
        st, days = PS.due_state(t.get("due"))
        active = self.sel_todo == t["id"]
        is_done = bool(t.get("done"))
        bg = T.tint(T.ACCENT, 0.09, T.CARD) if active else T.CARD
        f = tk.Frame(self.todo_scroll.inner, bg=bg, cursor="hand2")
        f.pack(fill="x")
        tk.Frame(f, bg=T.LINE_SOFT, height=1).pack(side="bottom", fill="x")
        row = tk.Frame(f, bg=bg)
        row.pack(fill="x", padx=T.sp(6), pady=T.sp(7))

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
                       font=T.T_BODY_SM(), anchor="w", justify="left", wraplength=1)
        # 正文换行跟随列表实际宽度（不要用 T.wrap —— 它会乘 DPI 缩放，
        # 在窄栏里必然溢出）
        lab.pack(side="left", fill="x", expand=True)
        T.fill_wrap(lab, pad=34)

        # 元信息单独一行，缩进对齐正文，不与标题抢宽度
        if meta:
            mrow = tk.Frame(row, bg=bg)
            mrow.pack(fill="x", padx=(24, 0), pady=(2, 0))
            ml = tk.Label(mrow, text=" · ".join(meta), bg=bg,
                          fg=(T.TXT4 if is_done else _state_color(st)),
                          font=T.T_CAPTION(), anchor="w", justify="left", wraplength=1)
            ml.pack(fill="x")
            T.fill_wrap(ml, pad=4)
            for w in (mrow, ml):
                w.bind("<Button-1>", lambda e, tid=t["id"]: self.select(tid))

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
        self.detail_scroll.canvas.itemconfigure(self.detail_scroll._win, height=0)
        self.detail_scroll.refresh(defer=True)
        widgets = list(self.detail_scroll.inner.winfo_children())
        while widgets:
            widget = widgets.pop()
            self.detail_scroll._bind_wheel(widget)
            widgets.extend(widget.winfo_children())

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
                label = tk.Label(box, text=mark + str(t.get("text") or ""), bg=T.CARD,
                                 fg=(T.TXT3 if t.get("done") else T.TXT2),
                                 font=T.T_BODY_SM(), anchor="w", justify="left",
                                 wraplength=1, cursor="hand2")
                label.pack(fill="x", pady=(0, 4))
                T.fill_wrap(label, pad=4)
                label.bind("<Button-1>", lambda e, tid=t["id"]: self.select(tid))
        else:
            label = tk.Label(box, text="这个阶段下还没有待办。可以直接在本阶段加一条。",
                             bg=T.CARD, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                             justify="left", wraplength=1)
            label.pack(fill="x", pady=(10, 0))
            T.fill_wrap(label, pad=4)

        r2 = WrapRow(box, bg=T.CARD)
        r2.pack(fill="x", pady=(12, 0))
        r2.add(T.Btn(r2, "在这个阶段加待办", lambda: self.add_todo(s["id"])))
        r2.add(T.Btn(r2, "删除阶段", lambda: self.del_stage(s["id"]), "danger"))

    def _kv(self, parent, key, val, edit=None, note=""):
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x", pady=(0, T.sp(12)))
        head = tk.Frame(row, bg=T.CARD)
        head.pack(fill="x", pady=(0, 4))
        if edit:
            T.Btn(head, "修改", edit, "ghost").pack(side="right")
        tk.Label(head, text=key, bg=T.CARD, fg=T.TXT3,
                 font=T.T_CAPTION(), anchor="w").pack(side="left")
        label = tk.Label(row, text=val, bg=T.CARD, fg=T.TXT2, font=T.T_BODY_SM(),
                         anchor="w", justify="left", wraplength=1)
        label.pack(fill="x")
        T.fill_wrap(label, pad=4)
        if note:
            hint = tk.Label(row, text=note, bg=T.CARD, fg=T.TXT4,
                            font=T.T_CAPTION(), anchor="w", justify="left", wraplength=1)
            hint.pack(fill="x", pady=(3, 0))
            T.fill_wrap(hint, pad=4)
        UK.divider(row, pady=(8, 0))
        return row

    # ------------------------------------------------------------ 交互
    def select(self, tid):
        self.sel_todo = tid
        self.sel_stage = None
        self._render_todos()
        self._render_stages()
        self._render_detail()
        self.detail_scroll.scroll_to_top()

    def pick_stage(self, sid):
        self.sel_stage = sid
        self.sel_todo = None
        self._render_todos()
        self._render_stages()
        self._render_detail()
        self.detail_scroll.scroll_to_top()

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