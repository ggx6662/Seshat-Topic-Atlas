#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科研方法论页：把 SKILL 当成可执行手册，而不是一堆建议。

左侧是七个方法的清单，右侧是所选方法的完整步骤、产出要求和常见错误；
底部可以针对「当前选中的课题」生成串起来的改进计划提示词。
"""
import tkinter as tk


import app_theme as T
from ui_parts import WrapRow   # 会自动折行的按钮排
import kb_widget as kb
import research_diagnose as RD
import research_skills as SK
import ui_parts as U

PAGE_HINT = "七个可执行方法 · 每步都有产出要求 · 可生成改进计划"

SKILLS_HELP = (
    "这七个方法按「想法成熟度」排好了顺序，不要跳着用。\n\n"
    "  01 问题收敛 —— 只有一个模糊兴趣时用（「我对红外检测感兴趣」）\n"
    "  02 新颖性核查 —— 已经有一句话问题陈述，想知道别人做没做过\n"
    "  03 可证伪假设 —— 确定了机制差异，要把它写成能被推翻的形式\n"
    "  04 最小实验设计 —— 有假设还没写代码，先定好数据/指标/消融/停止条件\n"
    "  05 证据门槛 —— 最小实验有效果，但还不足 GAP 支撑整篇论文\n"
    "  06 审稿人视角 —— 课题基本成形，准备投稿或申请\n"
    "  07 开题/投稿结构 —— 实验有结果，要写开题报告或论文\n\n"
    "每一页右侧都有「操作步骤 / 产出要求 / 常见错误」三块。"
    "底部两个按钮会生成**可以直接粘给大模型**的完整提示词：\n"
    "  · 生成这一步的提示词 —— 只针对当前这一步，短、聚焦\n"
    "  · 生成完整改进计划 —— 自动诊断当前课题缺哪几项，把缺的几个方法串成一条流水线\n\n"
    "**注意**：提示词只写「要做什么」，不替你想内容；也不保证照做就能发论文。\n"
    "生成时会带上你在个人画像里填的身份、算力、周期和最近记忆 —— "
    "画像为空时这一段整段不出现，而不是编一堆通用建议。"
)


class SkillsPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.sel = 0
        self.idea = {}
        self._build()

    def _build(self):
        # 顶部行：Hint（说明）+ 右侧主按钮；按钮不参与 expand，
        # 说明文字占满剩余宽度，字号放大也不会互相挤压。
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        T.Btn(top, "选择课题", self.pick_idea, "primary").pack(
            side="right", anchor="n")
        self._hint = U.Hint(top, SKILLS_HELP, summary="这七个方法怎么用", bg=T.BG)
        self._hint.pack(side="left", fill="x", expand=True, padx=(0, 10))

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=3, uniform="c")
        body.grid_columnconfigure(1, weight=7, uniform="c")

        # 左：方法列表
        left = T.Card(body, pad=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        T.card_head(left.body, "方法论清单", "按成熟度排",
                    bg=T.CARD).pack_configure(padx=6, pady=(2, 8))
        self.list_box = tk.Frame(left.body, bg=T.CARD)
        self.list_box.pack(fill="both", expand=True, padx=2)
        for i, s in enumerate(SK.SKILLS):
            self._item(i, s)

        # 右：详情
        right = T.Card(body, pad=14)
        right.grid(row=0, column=1, sticky="nsew")
        self.detail = T.ScrollArea(right.body, bg=T.CARD)
        self.detail.pack(fill="both", expand=True)
        act = tk.Frame(right.body, bg=T.CARD)
        act.pack(fill="x", pady=(10, 0))
        self._prompt_row = U.WrapRow(act)
        self._prompt_row.pack(fill="x")
        self._prompt_row.add(T.Btn(self._prompt_row, "生成这一步的提示词",
                                   self.prompt_one, "primary"))
        self._prompt_row.add(T.Btn(self._prompt_row, "生成完整改进计划",
                                   self.prompt_plan))
        self.idea_lbl = tk.Label(act, text="未选择课题", bg=T.CARD, fg=T.TXT3,
                                 font=T.T_CAPTION(), anchor="e")
        self.idea_lbl.pack(side="right")

        self.select(0)

    def _item(self, i, s):
        """一行一项：序号 + 名称 + 右侧小箭头；选中时加左侧品牌色竖条。

        以前每项两行（名称 + when 摘要），7 项就是 14 行，左栏比右栏的
        详情还长；而 when 在详情面板的副标题里已经有了，列表里重复一遍
        只是噪音。参考图的列表项都是单行 + 一个小元信息。
        """
        active = self.sel == i
        outer = tk.Frame(self.list_box, bg=T.CARD, cursor="hand2")
        outer.pack(fill="x", pady=1)
        # 选中竖条：3px 宽的小 Frame，未选中时用卡片底色（占位不跳动）
        bar = tk.Frame(outer, bg=T.ACCENT if active else T.CARD, width=3)
        bar.pack(side="left", fill="y")
        f = tk.Frame(outer, bg=T.CARD_HI if active else T.CARD, cursor="hand2")
        f.pack(side="left", fill="x", expand=True)
        row = tk.Frame(f, bg=f.cget("bg"))
        row.pack(fill="x", padx=(8, 8), pady=5)
        tk.Label(row, text="%02d" % (i + 1), bg=row.cget("bg"),
                 fg=T.ACCENT if active else T.TXT4,
                 font=T.T_CAPTION()).pack(side="left", padx=(0, 8))
        tk.Label(row, text=s["name"], bg=row.cget("bg"),
                 fg=T.TXT if active else T.TXT2,
                 font=T.T_LABEL() if active else T.T_BODY_SM(),
                 anchor="w").pack(side="left")
        for w in (outer, f, row, bar):
            w.bind("<Button-1>", lambda e, idx=i: self.select(idx))
        for c in row.winfo_children():
            c.bind("<Button-1>", lambda e, idx=i: self.select(idx))
            c.configure(cursor="hand2")

    def select(self, i):
        self.sel = i
        for w in self.list_box.winfo_children():
            w.destroy()
        for j, s in enumerate(SK.SKILLS):
            self._item(j, s)
        s = SK.SKILLS[i]
        self.detail.clear()
        box = self.detail.inner
        bg = T.CARD
        tk.Label(box, text=s["name"], bg=bg, fg=T.TXT, font=T.T_SECTION(),
                 anchor="w").pack(fill="x")
        tk.Label(box, text=s["en"] + "  ·  适用时机：" + s["when"], bg=bg, fg=T.TXT3,
                 font=T.T_CAPTION(), anchor="w").pack(fill="x", pady=(2, 10))

        tk.Label(box, text="这一步要解决什么", bg=bg, fg=T.TXT2, font=T.T_LABEL(),
                 anchor="w").pack(fill="x", pady=(2, 4))
        _g = tk.Label(box, text=s["goal"], bg=bg, fg=T.TXT, font=T.T_BODY(),
                      anchor="w", justify="left")
        T.fill_wrap(_g)
        _g.pack(fill="x", pady=(0, 12))

        tk.Label(box, text="操作步骤", bg=bg, fg=T.TXT2, font=T.T_LABEL(),
                 anchor="w").pack(fill="x", pady=(2, 6))
        for k, step in enumerate(s["steps"], 1):
            row = tk.Frame(box, bg=bg)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=" %d " % k, bg=T.CARD_HI, fg=T.OK, font=T.M(8, True)).pack(
                side="left", anchor="n", pady=1)
            _st = tk.Label(row, text=step, bg=bg, fg=T.TXT2,
                           font=T.T_BODY_SM(), anchor="w", justify="left")
            T.fill_wrap(_st, pad=40)      # 让出左边序号徽章的位置
            _st.pack(side="left", fill="x", expand=True, padx=(10, 0))

        T.hsep(box, T.LINE, (8, 8))
        tk.Label(box, text="产出要求", bg=bg, fg=T.TXT2, font=T.T_LABEL(),
                 anchor="w").pack(fill="x")
        _o = tk.Label(box, text=s["output"], bg=bg, fg=T.TXT,
                      font=T.T_BODY_SM(), anchor="w", justify="left")
        T.fill_wrap(_o)
        _o.pack(fill="x", pady=(4, 10))

        warn_bg = T.tint(T.WARN, 0.14, T.CARD)
        warn = tk.Frame(box, bg=warn_bg)
        warn.pack(fill="x", pady=(0, 6))
        tk.Label(warn, text="常见错误", bg=warn_bg, fg=T.WARN,
                 font=T.T_LABEL()).pack(anchor="w", padx=12, pady=(8, 0))
        _p = tk.Label(warn, text=s["pitfall"], bg=warn_bg, fg=T.WARN,
                      font=T.T_BODY_SM(), anchor="w", justify="left")
        T.fill_wrap(_p, pad=48)      # 让出左右各 12 的内边距
        _p.pack(fill="x", padx=12, pady=(2, 8))

        # ---- 下一步：把右栏下方的空白填成可操作的内容
        idx = next((k for k, x in enumerate(SK.SKILLS) if x.get("id") == s.get("id")),
                   None)
        nxt = SK.SKILLS[idx + 1] if (idx is not None and idx + 1 < len(SK.SKILLS)) else None
        hd = tk.Frame(box, bg=bg)
        hd.pack(fill="x", pady=(14, 4))
        tk.Label(hd, text="做完这一步通常接着做", bg=bg, fg=T.TXT,
                 font=T.T_LABEL()).pack(side="left")
        if nxt:
            card = tk.Frame(box, bg=T.CARD_HI, cursor="hand2")
            card.pack(fill="x", pady=(0, 4))
            inner = tk.Frame(card, bg=T.CARD_HI)
            inner.pack(fill="x", padx=10, pady=8)
            tk.Label(inner, text="%02d" % (idx + 2), bg=T.CARD_HI, fg=T.ACCENT,
                     font=T.T_CAPTION()).pack(side="left", padx=(0, 8))
            tk.Label(inner, text=nxt["name"], bg=T.CARD_HI, fg=T.TXT,
                     font=T.T_LABEL()).pack(side="left")
            tk.Label(inner, text="→", bg=T.CARD_HI, fg=T.TXT3,
                     font=T.T_BODY_SM()).pack(side="right")
            _nw = tk.Label(box, text=nxt.get("when", ""), bg=bg, fg=T.TXT3,
                           font=T.T_CAPTION(), anchor="w", justify="left")
            T.fill_wrap(_nw)
            _nw.pack(fill="x", pady=(0, 8))
            nxt_idx = idx + 1
            for w in (card, inner):
                w.bind("<Button-1>", lambda e, k=nxt_idx: self.select(k))
            for c in inner.winfo_children():
                c.bind("<Button-1>", lambda e, k=nxt_idx: self.select(k))
                c.configure(cursor="hand2")
        else:
            _ls = tk.Label(box, text="这是最后一步。做完之后回头看看「问题收敛」"
                                     "那一步留下的问题陈述有没有被实验结果推翻。",
                           bg=bg, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                           justify="left")
            T.fill_wrap(_ls)
            _ls.pack(fill="x", pady=(0, 8))

        tip = tk.Frame(box, bg=bg)
        tip.pack(fill="x", pady=(6, 0))
        _tp = tk.Label(tip, text="没配大模型也能用：点上面的「生成这一步的提示词」，"
                                 "把结果粘到任意 AI 里问。",
                       bg=bg, fg=T.TXT3, font=T.T_CAPTION(), anchor="w",
                       justify="left")
        T.fill_wrap(_tp)
        _tp.pack(fill="x")

    # ------------------------------------------------------------ 课题与提示词
    def pick_idea(self):
        mem = kb.load_research_memory()
        ideas = list(mem.get("ideas", []))
        if not ideas:
            self.app.toast("创新点库还是空的，先去选题工坊存一条", T.WARN)
            return
        T.close_child(self)
        win = T.child_window(self, "选择课题", "640x520", modal=True)
        self._child_win = win
        tk.Label(win, text="选择要改进的课题", bg=T.BG, fg=T.TXT,
                 font=T.T_TITLE()).pack(anchor="w", padx=18, pady=(16, 8))
        sa = T.ScrollArea(win)
        sa.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        for it in reversed(ideas):
            f = tk.Frame(sa.inner, bg=T.CARD, cursor="hand2")
            f.pack(fill="x", pady=2)
            tk.Label(f, text=str(it.get("title", "（无标题）")), bg=T.CARD, fg=T.TXT,
                     font=T.F(9), anchor="w", justify="left",
                     wraplength=560).pack(fill="x", padx=10, pady=(6, 0))
            tk.Label(f, text=str(it.get("desc", ""))[:90], bg=T.CARD, fg=T.TXT4,
                     font=T.F(8), anchor="w").pack(fill="x", padx=10, pady=(0, 6))
            f.bind("<Button-1>", lambda e, x=it: self._set_idea(x, win))

    def _set_idea(self, it, win):
        self.idea = {"title": it.get("title", ""), "desc": it.get("desc", ""),
                     "type": it.get("type", "")}
        self.idea_lbl.config(text="当前课题：" + str(it.get("title", ""))[:40], fg=T.OK)
        win.destroy()
        # 挑中哪条课题要改，说明这条你真在做 —— 记进画像
        try:
            import profile_hooks as PH
            PH.note("决定改进课题：%s" % str(it.get("title", ""))[:80],
                    tags=["选题", "方法论"], kind="daily",
                    ref=str(it.get("title", ""))[:80], source="科研方法论")
            PH.see_field(it.get("direction") or it.get("field") or "",
                         source="科研方法论")
        except Exception:
            pass

    def _ctx(self):
        """一次取齐画像 / 约束 / 记忆，供两个提示词生成函数共用。"""
        try:
            import prompt_context as PC
            g = PC.gather()
            return g["profile"], g["constraints"], g["memories"]
        except Exception:
            return None, None, None

    def prompt_one(self):
        if not self.idea:
            self.app.toast("先点右上「选择课题」", T.WARN)
            return
        s = SK.SKILLS[self.sel]
        prof, cons, mem = self._ctx()
        text = SK.skill_prompt(s["id"], self.idea, profile=prof,
                               constraints=cons, memories=mem)
        path = kb.save_prompt("方法论-" + s["name"], text)
        self.app.copy(text)
        self.app.toast("提示词已复制，存档：" + path.name, T.OK)
        self.app.log("已生成方法论提示词：" + str(path), T.OK, force_open=True)

    def prompt_plan(self):
        if not self.idea:
            self.app.toast("先点右上「选择课题」", T.WARN)
            return
        diag = RD.diagnose(self.idea)
        prof, cons, mem = self._ctx()
        text = SK.pipeline_prompt(self.idea, diag, profile=prof,
                                  constraints=cons, memories=mem)
        path = kb.save_prompt("改进计划", text)
        self.app.copy(text)
        self.app.toast("改进计划已复制，存档：" + path.name, T.OK)
        self.app.log("已生成改进计划：" + str(path), T.OK, force_open=True)