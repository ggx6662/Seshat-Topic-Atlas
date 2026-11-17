#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创新点库页：所有候选选题的台账 + 选题体检（单条深审与批量对比）。

数据存在 research_memory.json 的 ideas 字段里（与旧版共用，不迁移不丢失）。
"""
import threading
import tkinter as tk

import app_theme as T
import ui_parts as U
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
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        self._hint = U.Hint(top, IDEAS_HELP, summary="怎么用这一页", bg=T.BG)
        self._hint.pack(side="left", fill="x", expand=True)
        T.Btn(top, "新建选题", self.new_idea, "primary").pack(side="right")
        T.Btn(top, "打开选题工坊", lambda: self.app.goto("topic")).pack(side="right", padx=(0, 6))

        self.metric_row = tk.Frame(self, bg=T.BG)
        self.metric_row.pack(fill="x", padx=T.PAD)
        self._metrics = U.FoldMetrics(
            self.metric_row,
            [("选题总数", "0"), ("可进入实验", "0"), ("需补证据", "0"), ("过早", "0")],
            bg=T.BG, cols=4)
        self._metrics.pack(fill="x")

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(10, 14))
        body.grid_columnconfigure(0, weight=4, uniform="c")
        body.grid_columnconfigure(1, weight=6, uniform="c")
        self._body = body

        left = T.Card(body, pad=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._left_card = left
        self.list_scroll = T.ScrollArea(left.body, bg=T.CARD)
        self.list_scroll.pack(fill="both", expand=True)

        right = T.Card(body, pad=14)
        right.grid(row=0, column=1, sticky="nsew")
        self._right_card = right
        self.detail_head = tk.Label(right.body, text="未选择选题", bg=T.CARD, fg=T.TXT,
                                    font=T.T_BODY(), anchor="w", justify="left",
                                    wraplength=520)
        self.detail_head.pack(fill="x")
        self.detail_sub = tk.Label(right.body, text="在左侧点选一条，查看它的体检结论与待补足项。",
                                   bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(), anchor="w",
                                   justify="left", wraplength=520)
        self.detail_sub.pack(fill="x", pady=(2, 8))
        self.detail_scroll = T.ScrollArea(right.body, bg=T.CARD)
        self.detail_scroll.pack(fill="both", expand=True)
        self.detail_box = tk.Frame(self.detail_scroll.inner, bg=T.CARD)
        self.detail_box.pack(fill="both", expand=True)
        # 对话面板放在滚动区**外面**的固定槽位：滚进去的控件在可视区外
        # 不会分配几何（mapped=0、w/h 恒为 1），滚到底也画不出来。放在
        # 动作条上方、始终可见，也符合「边看诊断边追问」的使用顺序。
        self._chat_slot = tk.Frame(right.body, bg=T.CARD)
        # 动作条：只有选中一条后才出现（空态不摆用不了的按钮）
        # 第 10 版：五个按钮按「做这条选题的先后」分层。
        # 审查提示词是主路径（不花钱、立刻能把结构问题交出去问），
        # AI 审稿 / 继续聊要配 Key，复制摘要与删除是零星动作 ——
        # 后三件收进「更多 ▾」。删除原来是个红按钮常驻在最右，
        # 离其他按钮只有几个像素，误点一次就没了，不能这么放。
        self.act = tk.Frame(right.body, bg=T.CARD)
        T.Btn(self.act, "生成审查提示词", self.review_prompt, "primary").pack(
            side="left", padx=(0, 6))
        T.Btn(self.act, "和模型继续聊", self.open_chat, "ok").pack(
            side="left", padx=(0, 6))
        self.btn_more = T.Btn(self.act, "更多 ▾", self._more_menu, "ghost")
        self.btn_more.pack(side="left")

        # 空态引导卡：一条选题都没有时，两栏网格整体隐去，只留这一块。
        # 放在 body 之后单独 pack，空态时 body 会 pack_forget，
        # 所以它不会跑到页面底部。
        self._welcome = tk.Frame(self, bg=T.BG)

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
        try:
            mem = kb.load_research_memory()
            self.ideas = list(mem.get("ideas", []))
        except Exception:
            self.ideas = []
        self.ideas.reverse()      # 新的在上
        self._render_metrics()
        self._render_list()
        if self.sel is not None and self.sel < len(self.ideas):
            self.select(self.sel)

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
        self._metrics.set_values({
            "选题总数": str(len(self.ideas)),
            "可进入实验": str(adv),
            "需补证据": str(mid),
            "过早": str(low),
        })

    def _render_list(self):
        self.list_scroll.clear()
        if not self.ideas:
            # 空态：两栏都收起，只留一块引导卡。
            # 第 10 版之前是两栏都撑开、左栏塞空态、右栏显示「未选择选题」——
            # 结果是两块一高一矮的空卡片并排，比一处空更乱。
            self.list_scroll.pack_forget()
            for c in (self._left_card, self._right_card):
                try:
                    c.grid_remove()
                    c._fill_y, c._fill_y_pinned = False, True
                except Exception:
                    pass
            self._body.grid_rowconfigure(0, weight=0)
            for w in self._welcome.winfo_children():
                w.destroy()
            U.EmptyState(self._welcome,
                         "还没有选题",
                         "在「选题工坊」生成候选后点「存为创新点」，"
                         "或者手写一条：标题 + 一个问题 + 你想验证什么。",
                         action=self.new_idea, action_text="新建选题", bg=T.BG).pack(
                             fill="x")
            if not self._welcome.winfo_ismapped():
                self._welcome.pack(fill="x", padx=T.PAD, pady=(8, 0))
            return
        if self._welcome.winfo_ismapped():
            self._welcome.pack_forget()
        for c in (self._left_card, self._right_card):
            try:
                if not c.winfo_ismapped():
                    c.grid()
                c.grid_configure(sticky="nsew")
                c._fill_y, c._fill_y_pinned = True, True
            except Exception:
                pass
        self._body.grid_rowconfigure(0, weight=1)
        if not self.list_scroll.winfo_ismapped():
            self.list_scroll.pack(fill="both", expand=True)
        for i, it in enumerate(self.ideas):
            try:
                res = RD.diagnose(_norm(it))
                rank, stage = RD.stage_rank(res["stage"]), res["stage"]
                cnt = res["count"]
            except Exception:
                rank, stage, cnt = 0, "", {"passed": 0, "total": 9}
            active = self.sel == i
            bg = T.ACCENT_D if active else T.CARD_HI
            f = tk.Frame(self.list_scroll.inner, bg=bg, cursor="hand2")
            f.pack(fill="x", pady=2)
            head = tk.Frame(f, bg=bg)
            head.pack(fill="x", padx=8, pady=(6, 0))
            col = diag_view.stage_color(stage)
            tk.Label(head, text=" %d " % rank, bg=col, fg="#061220",
                     font=T.M(8, True)).pack(side="left")
            tk.Label(head, text="  " + str(it.get("type") or "未标注"), bg=bg, fg=T.TXT4,
                     font=T.F(8)).pack(side="left")
            tk.Label(head, text="%d/%d 项  " % (cnt["passed"], cnt["total"]), bg=bg,
                     fg=T.TXT3, font=T.M(8)).pack(side="right")
            title = str(it.get("title") or "（无标题）")
            tk.Label(f, text=title, bg=bg, fg=T.TXT if active else T.TXT2, font=T.F(9),
                     anchor="w", wraplength=T.wrap(330), justify="left").pack(fill="x", padx=8,
                                                                      pady=(2, 6))
            for w in (f, head):
                w.bind("<Button-1>", lambda e, idx=i: self.select(idx))

    # ------------------------------------------------------------ 选中
    def select(self, i):
        self.sel = i
        self._render_list()
        it = self.ideas[i]
        self.detail_head.config(text=str(it.get("title") or "（无标题）"))
        sub = "  ·  ".join(str(x) for x in (
            it.get("type") or "", it.get("category") or "", it.get("field") or "",
            it.get("time") or "") if x)
        self.detail_sub.config(text=sub)
        for w in self.detail_box.winfo_children():
            w.destroy()
        self._ai_box = None
        bg = T.CARD
        desc = str(it.get("desc") or "").strip()
        tk.Label(self.detail_box, text=desc or "（没有描述。建议补一句：改了什么机制、与谁比、拿什么证据。）",
                 bg=bg, fg=T.TXT2 if desc else T.TXT4, font=T.F(9), anchor="w",
                 justify="left", wraplength=520).pack(fill="x", pady=(0, 8))
        box = self.detail_box
        T.hsep(box, T.LINE, (2, 8))
        head = tk.Frame(box, bg=bg)
        head.pack(fill="x", pady=(0, 2))
        tk.Label(head, text="选题结构诊断", bg=bg, fg=T.TXT,
                 font=T.F(10, True)).pack(side="left")
        tk.Label(head, text="  核查的是「有没有交代」，不是「好不好」", bg=bg, fg=T.TXT4,
                 font=T.F(8)).pack(side="left")
        try:
            diag_view.render(box, _norm(it), compact=False, wrap=500)
        except Exception as exc:
            tk.Label(box, text="诊断失败：" + str(exc), bg=bg, fg=T.ERR,
                     font=T.F(9)).pack(anchor="w")
        self._show_actions(True)
        self.detail_scroll.refresh()

    def _show_actions(self, on):
        """动作条只在选中一条时出现——空态摆一排点了会提示"先选一条"的按钮纯属噪音。"""
        if on and not self.act.winfo_ismapped():
            self.act.pack(fill="x", pady=(8, 0))
        elif not on and self.act.winfo_ismapped():
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

        def work():
            txt = L.critique_ideas(direction, [cand])
            self.app.post(lambda: self._ai_done(txt))
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
        tk.Label(head, text="AI 审稿意见", bg=bg, fg=T.PURPLE,
                 font=T.F(10, True)).pack(side="left")
        tk.Label(head, text="大模型生成 · 判断权在你", bg=bg, fg=T.TXT4,
                 font=T.F(8), anchor="e").pack(side="right")
        tk.Label(box, text=txt, bg=bg, fg=T.TXT2, font=T.F(9),
                 anchor="w", justify="left", wraplength=510).pack(fill="x", pady=(4, 0))
        self._ai_box = box
        self.detail_scroll.refresh()

    def _render_ai_pending(self):
        self._clear_ai()
        box = tk.Frame(self.detail_box, bg=T.CARD)
        box.pack(fill="x", pady=(10, 0))
        tk.Label(box, text="AI 审稿意见", bg=T.CARD, fg=T.PURPLE,
                 font=T.F(10, True), anchor="w").pack(fill="x")
        tk.Label(box, text="正在让大模型读这条选题…", bg=T.CARD, fg=T.TXT4,
                 font=T.F(9), anchor="w").pack(fill="x", pady=(2, 0))
        self._ai_box = box
        self.detail_scroll.refresh()

    def _clear_ai(self):
        b = getattr(self, "_ai_box", None)
        if b is not None:
            try:
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
        panel.pack(fill="x", pady=(10, 0))
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
        tk.Label(row, text=text, bg=T.CARD, fg=color or T.TXT2, font=T.F(9), anchor="w",
                 justify="left", wraplength=500).pack(side="left", fill="x", expand=True)

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
        mem = kb.load_research_memory()
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