#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创新点库页：所有候选选题的台账 + 选题体检（单条深审与批量对比）。

数据存在 research_memory.json 的 ideas 字段里（与旧版共用，不迁移不丢失）。
"""
import threading
import tkinter as tk

import app_theme as T
import ui_parts as U
import ui_kit as UK
import app_diagnose_view as diag_view
import kb_widget as kb
import llm_bridge as L
import research_diagnose as RD
from chat_panel import ChatPanel

PAGE_HINT = "选题台账 · 成熟阶段 · 证据门槛 · 单条深审"

IDEAS_HELP = """\
这里是你亲手存下的每一个选题。左边是台账，右边是单条深审，两边不是一回事。

一、左边四个维度各自在说什么
· 成熟阶段：想法 → 假设 → 方案 → 实验 → 写作。它是你自己标的状态，系统不会替你改；标错阶段不影响任何计算，只会让你自己看走眼。
· 机制：这个想法靠什么起作用（比如「把频域特征接进主干」）。没写机制的选题，诊断里会被标出来。
· 证据类型：你现在拿什么支撑它（文献类比 / 消融数据 / 先导实验 / 纯推理）。这一栏决定系统对你的要求有多严。
· 风险类型：它最可能怎么死（新颖性不足 / 做不出来 / 评测说不清 / 没意义）。写清楚风险，审查提示词才会针对它提问。

二、右边三个按钮的区别
· 生成审查提示词：把这一个选题的结构、缺口、风险打包成一段话，你复制去任何大模型里问。不需要配 Key，也不需要联网。
· AI 审稿意见：直接调大模型要一份审稿意见。需要先在设置里配 API Key；没配就只给提示，不会失败。
· 和模型继续聊：就这一条选题开一段连续对话，可以追问。同样是配了 Key 才真正回话；每轮都会带上你画像里的方向和约束。
· 删除：真删，没有回收站。台账本体是 research_memory.json，删之前想要留档就先导出。

三、这里不做的事
不给你打分，也不判断这个选题好不好。诊断只看结构完不完整——机制有没有说、基线有没有、消融怎么设计——缺什么就说什么，不缺就不说话。"""


class IdeasPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.ideas = []
        self.sel = None
        self._ai_box = None
        self._build()
        self.reload()

    # ------------------------------------------------------------ 布局
    def _build(self):
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(T.sp(4), T.sp(8)))
        top.grid_columnconfigure(0, weight=1)
        heading = tk.Frame(top, bg=T.BG)
        heading.grid(row=0, column=0, sticky="ew")
        UK.eyebrow(heading, "IDEA LEDGER · 选题台账", bg=T.BG).pack(fill="x")
        title = tk.Label(heading, text="创新点库", bg=T.BG, fg=T.TXT,
                         font=T.T_PAGE_TITLE(), anchor="w", justify="left")
        title.pack(fill="x", pady=(T.sp(4), T.sp(6)))
        T.fill_wrap(title, pad=0)
        tools = tk.Frame(top, bg=T.BG)
        tools.grid(row=0, column=1, sticky="ne", padx=(T.sp(12), 0))
        T.Btn(tools, "新建选题", self.new_idea, "primary").pack(side="right")
        T.Btn(tools, "打开选题工坊", lambda: self.app.goto("topic")).pack(
            side="right", padx=(0, T.sp(6)))
        self._hint = U.Hint(top, IDEAS_HELP,
                            summary="保存研究想法，核查结构缺口；不评价创新性或研究价值。",
                            bg=T.BG)
        self._hint.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._hint._lbl.pack_configure(fill="x", expand=True)
        T.fill_wrap(self._hint._lbl, pad=T.sp(36))
        T.fill_wrap(self._hint._detail, pad=0)

        self.metric_row = tk.Frame(self, bg=T.BG)
        self.metric_row.pack(fill="x", padx=T.PAD)
        self._metrics = tk.Label(self.metric_row, bg=T.BG, fg=T.TXT3,
                                 font=T.T_CAPTION(), anchor="w", justify="left")
        self._metrics.pack(fill="x")
        T.fill_wrap(self._metrics, pad=0)

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(T.sp(10), T.sp(14)))
        body.grid_columnconfigure(0, weight=4, uniform="c")
        body.grid_columnconfigure(1, weight=6, uniform="c")
        body.grid_rowconfigure(0, weight=1)
        self._body = body

        left = T.Card(body, pad=T.sp(12), fill_y=True)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, T.sp(10)))
        self._left_card = left
        UK.eyebrow(left.body, "全部选题", "01").pack(fill="x", pady=(0, T.sp(8)))
        self.list_scroll = T.ScrollArea(left.body, bg=T.CARD)
        self.list_scroll.pack(fill="both", expand=True)

        right = T.Card(body, pad=T.sp(14), fill_y=True)
        right.grid(row=0, column=1, sticky="nsew")
        self._right_card = right
        UK.eyebrow(right.body, "选题详情 · 结构核查", "02").pack(
            fill="x", pady=(0, T.sp(8)))
        self.detail_scroll = T.ScrollArea(right.body, bg=T.CARD)
        self.detail_scroll.pack(fill="both", expand=True)
        self.detail_head = tk.Label(self.detail_scroll.inner, text="未选择选题",
                                    bg=T.CARD, fg=T.TXT, font=T.T_SECTION(),
                                    anchor="w", justify="left", wraplength=T.sp(300))
        self.detail_head.pack(fill="x")
        self._wrap_text(self.detail_head)
        self.detail_sub = tk.Label(self.detail_scroll.inner,
                                   text="在左侧点选一条，查看结构缺口与待补足项。",
                                   bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(),
                                   anchor="w", justify="left", wraplength=T.sp(300))
        self.detail_sub.pack(fill="x", pady=(T.sp(4), T.sp(12)))
        self._wrap_text(self.detail_sub)
        self.detail_box = tk.Frame(self.detail_scroll.inner, bg=T.CARD)
        self.detail_box.pack(fill="x")
        self._chat_slot = tk.Frame(right.body, bg=T.CARD)
        self.act = U.WrapRow(right.body, padx=0, gap=T.sp(6), rowgap=T.sp(6), bg=T.CARD)
        self.act.add(T.Btn(self.act, "生成审查提示词", self.review_prompt, "primary"))
        self.act.add(T.Btn(self.act, "和模型继续聊", self.open_chat))
        self.btn_more = self.act.add(T.Btn(self.act, "更多 ▾", self._more_menu, "ghost"))
        self._welcome = tk.Frame(self, bg=T.BG)

    def _wrap_text(self, label):
        def fit(event):
            if event.width > 1:
                label.config(wraplength=max(1, event.width - T.sp(4)))
        label.bind("<Configure>", fit, add="+")
        self.detail_scroll._bind_wheel(label)
        return label

    def _detail_width(self):
        width = self.detail_scroll.canvas.winfo_width()
        if width <= 1:
            width = self._right_card.body.winfo_width()
        return max(T.sp(80), width - T.sp(8)) if width > 1 else T.sp(300)

    def _clear_selection(self):
        self.sel = None
        self._clear_ai()
        for w in self._chat_slot.winfo_children():
            w.destroy()
        self._chat_slot.pack_forget()
        self._chat = None
        for w in self.detail_box.winfo_children():
            w.destroy()
        self.detail_head.config(text="未选择选题")
        self.detail_sub.config(text="在左侧点选一条，查看结构缺口与待补足项。")
        self._show_actions(False)
        self.detail_scroll.scroll_to_top()
        self.detail_scroll.refresh()

    # ------------------------------------------------------------ 数据
    def _more_menu(self):
        """「更多 ▾」：AI 审稿 / 复制摘要 / 删除。

        删除单独放在最下面并用分隔线隔开，还要再确认一次 ——
        它挨着其他按钮时误点概率太高（真删、没有回收站）。
        """
        try:
            m = tk.Menu(self, tearoff=0, bg=T.CARD, fg=T.TXT,
                        activebackground=T.ACCENT_D, activeforeground=T.ACCENT,
                        bd=0, relief="flat", font=T.T_BODY_SM())
            m.add_command(label="让 AI 写一份审稿意见（需配置 Key）", command=self.ai_review)
            m.add_command(label="复制摘要", command=self.copy_summary)
            m.add_separator()
            m.add_command(label="删除这一条…", command=self._confirm_delete)
            m.tk_popup(self.btn_more.winfo_rootx(),
                       self.btn_more.winfo_rooty() + self.btn_more.winfo_height() + 2)
        except Exception as exc:
            print("弹出菜单失败:", exc)

    def _confirm_delete(self):
        """删之前问一句：台账真删，没有回收站。"""
        if self.sel is None or self.sel >= len(self.ideas):
            return
        title = (self.ideas[self.sel].get("title") or "")[:40]
        if not T.ask_yes(self, "删除选题", "「%s」会被真的删掉，没有回收站。\n"
                                          "确定要删吗？" % title):
            return
        self.delete_idea()

    def reload(self):
        # 每次切回本页都会调 reload，但只有台账真的变了才值得重画。
        # 用文件 mtime + 条数做签名：存档被别处（选题工坊存候选、AI 对话）改写时
        # mtime 一定变，所以不会漏更新，同时避免了无谓的整页重建。
        try:
            sig = (kb.RESEARCH_MEMORY.stat().st_mtime_ns,)
        except Exception:
            sig = None
        if sig is not None and sig == getattr(self, "_sig", None):
            return
        self._sig = sig
        selected = None
        if self.sel is not None and 0 <= self.sel < len(self.ideas):
            it = self.ideas[self.sel]
            selected = (it.get("time"), it.get("title"))
        try:
            mem = kb.load_research_memory()
            self.ideas = list(mem.get("ideas", []))
        except Exception:
            self.ideas = []
        self.ideas.reverse()      # 新的在上
        self.sel = next((i for i, it in enumerate(self.ideas)
                         if (it.get("time"), it.get("title")) == selected), None)
        self._render_metrics()
        if self.sel is not None:
            self.select(self.sel)
        else:
            self._clear_selection()
            self._render_list()

    def _render_metrics(self):
        ranks = []
        for it in self.ideas:
            try:
                ranks.append(RD.stage_rank(RD.diagnose(_norm(it))["stage"]))
            except Exception:
                ranks.append(0)
        adv = sum(1 for r in ranks if r >= 3)
        mid = sum(1 for r in ranks if r == 2)
        low = sum(1 for r in ranks if r <= 1)
        self._metrics.config(text="共 %d 条选题  ·  可进入实验 %d  ·  需补证据 %d  ·  过早 %d" %
                             (len(self.ideas), adv, mid, low))

    def _render_list(self):
        self.list_scroll.clear()
        if not self.ideas:
            self._clear_selection()
            self._body.pack_forget()
            for w in self._welcome.winfo_children():
                w.destroy()
            empty = UK.EmptyPanel(
                self._welcome, "还没有选题",
                "在选题工坊保存候选，或手写标题与想验证的问题。",
                icon="ideas", cta="新建选题", cta_cmd=self.new_idea,
                bg=T.BG, height=T.sp(240))
            empty.pack(fill="both", expand=True)
            empty._holder.bind("<Configure>", lambda e: empty._cv.config(
                height=max(T.sp(240), e.height + T.sp(32))), add="+")
            self._welcome.pack(fill="both", expand=True, padx=T.PAD,
                               pady=(T.sp(10), T.sp(14)))
            return
        self._welcome.pack_forget()
        self._body.pack(fill="both", expand=True, padx=T.PAD,
                        pady=(T.sp(10), T.sp(14)))
        for i, it in enumerate(self.ideas):
            try:
                res = RD.diagnose(_norm(it))
                stage, cnt = res["stage"], res["count"]
            except Exception:
                stage, cnt = "未诊断", {"passed": 0, "total": 9}
            active = self.sel == i
            bg = T.tint(T.ACCENT, 0.08, T.CARD) if active else T.CARD
            row = tk.Frame(self.list_scroll.inner, bg=bg, cursor="hand2")
            row.pack(fill="x", pady=(0, T.sp(4)))
            stripe = tk.Frame(row, bg=T.ACCENT if active else bg, width=T.sp(3))
            stripe.pack(side="left", fill="y")
            content = tk.Frame(row, bg=bg)
            content.pack(side="left", fill="x", expand=True,
                         padx=T.sp(10), pady=T.sp(8))
            title = tk.Label(content, text=str(it.get("title") or "（无标题）"),
                             bg=bg, fg=T.TXT, font=T.T_LABEL(), anchor="w",
                             justify="left", wraplength=T.sp(260))
            title.pack(fill="x")
            meta = " · ".join(str(x) for x in (
                it.get("type") or "未标注类型", it.get("category"), it.get("field")) if x)
            tags = tk.Label(content, text=meta, bg=bg, fg=T.TXT3,
                            font=T.T_CAPTION(), anchor="w", justify="left",
                            wraplength=T.sp(260))
            tags.pack(fill="x", pady=(T.sp(4), 0))
            status = tk.Label(content,
                              text="%s · 已具备 %d/%d 项" %
                                   (stage, cnt["passed"], cnt["total"]),
                              bg=bg, fg=T.ACCENT if active else T.TXT2,
                              font=T.T_CAPTION(), anchor="w", justify="left",
                              wraplength=T.sp(260))
            status.pack(fill="x", pady=(T.sp(4), 0))
            labels = [title, tags, status]
            stamp = " · ".join(str(x) for x in (it.get("time"), it.get("source")) if x)
            if stamp:
                date = tk.Label(content, text=stamp, bg=bg, fg=T.TXT4,
                                font=T.T_CAPTION(), anchor="w", justify="left",
                                wraplength=T.sp(260))
                date.pack(fill="x", pady=(T.sp(4), 0))
                labels.append(date)
            for label in labels:
                T.fill_wrap(label, pad=0)
            self._bind_idea_row(row, stripe, [row, content] + labels, i, bg, active)
        self.list_scroll.refresh()

    def _bind_idea_row(self, row, stripe, widgets, index, base, active):
        def hover(on):
            if not on:
                x, y = row.winfo_pointerxy()
                if (row.winfo_rootx() <= x < row.winfo_rootx() + row.winfo_width() and
                        row.winfo_rooty() <= y < row.winfo_rooty() + row.winfo_height()):
                    return
            color = base if active or not on else T.tint(T.ACCENT, 0.05, T.CARD)
            for widget in widgets:
                widget.config(bg=color)
            if not active:
                stripe.config(bg=color)
        for widget in widgets + [stripe]:
            widget.config(cursor="hand2")
            widget.bind("<Button-1>", lambda e: self.select(index))
            self.list_scroll._bind_wheel(widget)
            widget.bind("<Enter>", lambda e: hover(True), add="+")
            widget.bind("<Leave>", lambda e: hover(False), add="+")

    # ------------------------------------------------------------ 选中
    def select(self, i):
        if not 0 <= i < len(self.ideas):
            self._clear_selection()
            self._render_list()
            return
        self._clear_selection()
        self.sel = i
        self._render_list()
        it = self.ideas[i]
        self.detail_head.config(text=str(it.get("title") or "（无标题）"))
        sub = "  ·  ".join(str(x) for x in (
            it.get("type") or "", it.get("category") or "", it.get("field") or "",
            it.get("time") or "") if x)
        self.detail_sub.config(text=sub)
        bg = T.CARD
        wrap = self._detail_width()
        desc = str(it.get("desc") or "").strip()
        UK.eyebrow(self.detail_box, "原始描述").pack(fill="x", pady=(0, T.sp(4)))
        description = tk.Label(
            self.detail_box,
            text=desc or "没有描述。建议补一句：改了什么机制、与谁比、拿什么证据。",
            bg=bg, fg=T.TXT2 if desc else T.TXT4, font=T.T_BODY_SM(),
            anchor="w", justify="left", wraplength=wrap)
        description.pack(fill="x", pady=(0, T.sp(8)))
        self._wrap_text(description)
        T.hsep(self.detail_box, T.LINE_SOFT, (T.sp(4), T.sp(12)))
        tk.Label(self.detail_box, text="选题结构诊断", bg=bg, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(fill="x")
        note = tk.Label(self.detail_box, text="核查的是有没有交代，不是好不好。",
                        bg=bg, fg=T.TXT3, font=T.T_CAPTION(), anchor="w",
                        justify="left", wraplength=wrap)
        note.pack(fill="x", pady=(T.sp(4), T.sp(8)))
        self._wrap_text(note)
        box = tk.Frame(self.detail_box, bg=bg)
        box.pack(fill="x")
        try:
            diag_view.render(box, _norm(it), compact=False, wrap=wrap)
            stage_head = box.winfo_children()[0]
            badge, hint = stage_head.winfo_children()
            badge.pack_configure(side="top", fill="x", anchor="w")
            hint.pack_configure(side="top", fill="x", anchor="w", pady=(T.sp(4), 0))
            hint.config(anchor="w", justify="left", wraplength=wrap)
            self._wrap_diagnosis(box)
        except Exception as exc:
            error = tk.Label(box, text="诊断失败：" + str(exc), bg=bg, fg=T.ERR,
                             font=T.T_BODY_SM(), anchor="w", justify="left",
                             wraplength=wrap)
            error.pack(fill="x")
            self._wrap_text(error)
        self._show_actions(True)
        self.detail_scroll.scroll_to_top()
        self.detail_scroll.refresh()

    def _wrap_diagnosis(self, parent):
        for widget in parent.winfo_children():
            if isinstance(widget, tk.Label) and widget.winfo_pixels(widget.cget("wraplength")) > 0:
                self._wrap_text(widget)
            else:
                self.detail_scroll._bind_wheel(widget)
            self._wrap_diagnosis(widget)

    def _show_actions(self, on):
        if on:
            self.act.pack(side="bottom", fill="x", pady=(T.sp(12), 0),
                          before=self.detail_scroll)
        else:
            self.act.pack_forget()

    def ai_review(self):
        """让大模型写一份审稿意见。

        和"生成审查提示词"的区别：那个是**给你自己带出去问 AI** 的模板，
        这个是**就地让配好的模型直接写**。本地结构诊断查的是"有没有交代"，
        模型能说"这个理由站不站得住"，两者互补，都不能替代读文献。
        """
        if self.sel is None or self.sel >= len(self.ideas):
            self.app.toast("先在左侧选一条选题", T.WARN)
            return
        if not L.is_ready():
            self.app.toast("还没配置大模型，去「设置与数据」里填一下", T.WARN)
            try:
                self.app.goto("settings")
            except Exception:
                pass
            return
        it = self.ideas[self.sel]
        direction = str(it.get("field") or it.get("category") or "").strip()
        cand = {"title": str(it.get("title") or ""),
                "reason": str(it.get("desc") or "")}
        self._render_ai_pending()
        request = object()
        self._ai_request = request

        def work():
            txt = L.critique_ideas(direction, [cand])
            self.app.post(lambda: self._ai_done(txt)
                          if self._ai_request is request else None)
        threading.Thread(target=work, daemon=True).start()

    def _ai_done(self, txt):
        if not txt:
            self.app.toast("大模型没有返回内容，检查设置里的连接", T.WARN)
            self._clear_ai()
            return
        self._clear_ai()
        bg = T.CARD
        box = tk.Frame(self.detail_box, bg=bg)
        box.pack(fill="x", pady=(10, 0))
        head = tk.Frame(box, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text="AI 审稿意见", bg=bg, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(fill="x")
        tk.Label(head, text="大模型生成 · 判断权在你", bg=bg, fg=T.TXT3,
                 font=T.T_CAPTION(), anchor="w").pack(fill="x", pady=(T.sp(4), 0))
        review = tk.Label(box, text=txt, bg=bg, fg=T.TXT2, font=T.T_BODY_SM(),
                          anchor="w", justify="left", wraplength=self._detail_width())
        review.pack(fill="x", pady=(T.sp(8), 0))
        self._wrap_text(review)
        self._ai_box = box
        self.detail_scroll.refresh()

    def _render_ai_pending(self):
        self._clear_ai()
        box = tk.Frame(self.detail_box, bg=T.CARD)
        box.pack(fill="x", pady=(10, 0))
        tk.Label(box, text="AI 审稿意见", bg=T.CARD, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(fill="x")
        pending = tk.Label(box, text="正在让大模型读这条选题…", bg=T.CARD, fg=T.TXT3,
                           font=T.T_BODY_SM(), anchor="w", justify="left",
                           wraplength=self._detail_width())
        pending.pack(fill="x", pady=(T.sp(4), 0))
        self._wrap_text(pending)
        self._ai_box = box
        self.detail_scroll.refresh()

    def _clear_ai(self):
        self._ai_request = None
        b = getattr(self, "_ai_box", None)
        if b is not None:
            try:
                if b is self._chat_slot:
                    for w in b.winfo_children():
                        w.destroy()
                    b.pack_forget()
                    self._chat = None
                else:
                    b.destroy()
            except Exception:
                pass
            self._ai_box = None

    def open_chat(self):
        """就这条选题开一个对话面板。

        和「AI 审稿意见」的分工：那个是**一次性**要一段意见，说完就结束；
        这里可以追问（「第三条展开」「这个能不能用少量算力验证」），
        而且每一轮都会把画像里的方向与约束带上，模型不会答成通用建议。
        """
        if self.sel is None or self.sel >= len(self.ideas):
            self.app.toast("先在左侧选一条选题", T.WARN)
            return
        self._clear_ai()
        it = self.ideas[self.sel]
        title = str(it.get("title") or "未命名选题")
        direction = str(it.get("field") or it.get("category") or "").strip()
        desc = str(it.get("desc") or "").strip()

        panel = self._chat_slot
        for w in panel.winfo_children():
            w.destroy()
        panel.pack(side="bottom", fill="x", pady=(T.sp(10), 0),
                   before=self.detail_scroll)
        tk.Frame(panel, bg=T.LINE, height=1).pack(fill="x", pady=(0, 10))

        def ctx():
            lines = ["【这次要聊的对象】", "选题：" + title[:120]]
            if direction:
                lines.append("所属方向：" + direction)
            if desc:
                lines.append("我的原始想法：" + desc[:400])
            return "\n".join(lines) + "\n"

        self._ai_box = panel
        self._chat = ChatPanel(panel, self.app,
                               anchor="选题：" + title[:24],
                               context_fn=ctx,
                               suggestions=["这个选题最大风险是什么？",
                                            "用少量算力怎么做出最小验证？",
                                            "最容易被审稿人攻击哪一点？"],
                               fallback_cmd=self.review_prompt)
        self._chat.pack(fill="x")
        # 面板现在在滚动区外面（固定可见），不用再刷 detail_scroll；
        # 但仍要让它先完成一次布局，否则刚建出来的第一帧高度是 1。
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _bullet(self, parent, text, color=None):
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x", pady=1)
        tk.Label(row, text="·", bg=T.CARD, fg=T.ACCENT, font=T.F(10)).pack(side="left",
                                                                        padx=(2, 6), anchor="n")
        label = tk.Label(row, text=text, bg=T.CARD, fg=color or T.TXT2,
                         font=T.T_BODY_SM(), anchor="w", justify="left",
                         wraplength=self._detail_width())
        label.pack(side="left", fill="x", expand=True)
        self._wrap_text(label)

    def _bar(self, parent, label, val):
        try:
            val = int(val)
        except Exception:
            val = 0
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label, bg=T.CARD, fg=T.TXT3, font=T.F(8), width=9,
                 anchor="w").pack(side="left")
        track = tk.Frame(row, bg=T.LINE_SOFT, height=8)
        track.pack(side="left", fill="x", expand=True, padx=4)
        track.pack_propagate(False)
        col = T.OK if val >= 65 else (T.WARN if val >= 40 else T.ERR)
        tk.Frame(track, bg=col).place(x=0, y=0, relwidth=val / 100.0, relheight=1)
        tk.Label(row, text=str(val), bg=T.CARD, fg=col, font=T.M(8), width=3,
                 anchor="e").pack(side="left")

    # ------------------------------------------------------------ 动作
    def new_idea(self):
        title = T.ask_text(self, "新建选题", "选题标题（一句话说清改了什么）", "")
        if not title:
            return
        desc = T.ask_text(self, "新建选题", "选题描述：机制差异、对比 baseline、证据计划", "")
        self._add(title, desc or "")

    def _add(self, title, desc):
        title = (title or "").strip()
        if not title:
            return
        mem = kb.load_research_memory()
        # 标题就是这条选题的身份；重复新建只会让台账出现两条同名记录
        for it in mem.get("ideas") or []:
            if (it.get("title") or "").strip() == title:
                self.reload()
                for i, x in enumerate(self.ideas):
                    if (x.get("title") or "").strip() == title:
                        self.select(i)
                        break
                self.app.toast("这条已经在库里了，没有重复新建", T.OK)
                return
        idea = {
            "time": kb.datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "title": title, "desc": desc,
            "type": kb.infer_innovation_type(title, desc),
            "source": "手动新建",
        }
        mem.setdefault("ideas", []).append(idea)
        kb.save_research_memory(mem)
        # 记进画像：新建选题算「正在做的事」，归为危机类会让它在你忙时更靠前
        try:
            import profile_hooks as PH
            PH.note("新建选题：%s" % str(title)[:80],
                    tags=["选题"], kind="crisis", ref=str(title)[:80],
                    source="创新点库")
            # 选题库里每多一条，方向偏好就该跟着变；learn_from_ideas 幂等，
            # 每次增删后整体重算一次最稳妥
            PH.learn_ideas(mem.get("ideas") or [])
        except Exception:
            pass
        self.sel = None
        self.reload()
        self.app.toast("已新建选题", T.OK)

    def delete_idea(self):
        if self.sel is None or self.sel >= len(self.ideas):
            self.app.toast("请先选择一条", T.WARN)
            return
        it = self.ideas[self.sel]
        mem = kb.load_research_memory()
        ideas = mem.get("ideas", [])
        target = None
        for x in ideas:
            if x.get("time") == it.get("time") and x.get("title") == it.get("title"):
                target = x
                break
        if target is None:
            self.app.toast("未找到该条记录", T.WARN)
            return
        ideas.remove(target)
        kb.save_research_memory(mem)
        self.sel = None
        self.reload()
        self.app.toast("已删除", T.OK)

    def review_prompt(self):
        if self.sel is None:
            self.app.toast("请先选择一条", T.WARN)
            return
        try:
            text = kb.idea_review_prompt(_norm(self.ideas[self.sel]), "完整选题体检")
        except Exception as exc:
            self.app.toast("生成失败：" + str(exc), T.ERR)
            return
        path = kb.save_prompt("选题体检", text)
        self.app.copy(text)
        self.app.toast("审查提示词已复制并存档", T.OK)
        self.app.log("已生成选题体检提示词：" + str(path), T.OK, force_open=True)

    def copy_summary(self):
        if self.sel is None:
            self.app.toast("请先选择一条", T.WARN)
            return
        it = self.ideas[self.sel]
        res = RD.diagnose(_norm(it))
        cnt = res["count"]
        lines = [it.get("title", ""), it.get("desc", ""), "",
                 "结构诊断：%s（已具备 %d/%d 项）" % (res["stage"], cnt["passed"], cnt["total"]),
                 res["stage_hint"]]
        if res["passed"]:
            lines += ["", "已具备："] + ["  - " + p["label"] for p in res["passed"]]
        if res["missing"]:
            lines += ["", "尚未交代："]
            lines += ["  - " + m["label"] + "：" + m["fix"] for m in res["missing"]]
        if res["warnings"]:
            lines += ["", "注意："] + ["  - " + w for w in res["warnings"]]
        self.app.copy("\n".join(lines))
        self.app.toast("摘要已复制", T.OK)


def _norm(it):
    """把库里的记录整理成诊断函数认识的形状。"""
    return {
        "title": str(it.get("title") or ""),
        "desc": str(it.get("desc") or ""),
        "type": str(it.get("type") or ""),
    }