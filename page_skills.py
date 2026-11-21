#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科研方法论页：把 SKILL 当成可执行手册，而不是一堆建议。

左侧是七个方法的清单，右侧是所选方法的完整步骤、产出要求和常见错误；
底部可以针对「当前选中的课题」生成串起来的改进计划提示词。
"""
import tkinter as tk

import app_theme as T
import ui_kit as K
from ui_parts import WrapRow
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

    @staticmethod
    def _wrap(label):
        """按文字控件的实际宽度换行，序号和外边距不再靠估算扣除。"""
        label.configure(wraplength=T.sp(240))

        def sync(e):
            width = max(1, e.width - 2 * label.winfo_pixels(label.cget("padx")) - T.sp(4))
            if e.width > 1 and label.winfo_pixels(label.cget("wraplength")) != width:
                label.configure(wraplength=width)

        label.bind("<Configure>", sync, add="+")
        return label

    def _build(self):
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(T.sp(4), T.sp(12)))
        T.Btn(top, "选择课题", self.pick_idea, "primary").pack(
            side="right", anchor="n", padx=(T.sp(12), 0))
        intro = tk.Frame(top, bg=T.BG)
        intro.pack(side="left", fill="x", expand=True)
        K.eyebrow(intro, "RESEARCH METHODS · 方法手册", bg=T.BG).pack(fill="x")
        self._wrap(tk.Label(intro, text="科研方法论", bg=T.BG, fg=T.TXT,
                            font=T.T_PAGE_TITLE(), anchor="w", justify="left")).pack(
                                fill="x", pady=(T.sp(4), T.sp(4)))
        self._wrap(tk.Label(intro, text=PAGE_HINT, bg=T.BG, fg=T.TXT3,
                            font=T.T_BODY_SM(), anchor="w", justify="left")).pack(fill="x")

        # 上下文保持紧凑；长标题和说明完整换行，通过滚动查看，不挤占方法动作。
        context = T.Card(self, pad=T.sp(12), height=T.sp(114), fill_y=True)
        context.pack(fill="x", padx=T.PAD, pady=(0, T.sp(12)))
        K.Chip(context.body, "当前课题", font=T.T_CAPTION()).pack(
            anchor="w", pady=(0, T.sp(4)))
        self._context_scroll = T.ScrollArea(context.body, bg=T.CARD)
        self._context_scroll.pack(fill="both", expand=True)
        self._context_scroll.canvas.bind(
            "<Configure>", lambda e: self._context_scroll.canvas.itemconfigure(
                self._context_scroll._win, height=0), add="+")
        self.idea_lbl = self._wrap(tk.Label(
            self._context_scroll.inner, text="尚未选择课题", bg=T.CARD, fg=T.TXT,
            font=T.T_LABEL(), anchor="w", justify="left"))
        self.idea_lbl.pack(fill="x")
        self.idea_desc = self._wrap(tk.Label(
            self._context_scroll.inner,
            text="可先阅读方法手册；选择创新点库中的课题后，生成针对它的提示词。",
            bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(), anchor="w", justify="left"))
        self.idea_desc.pack(fill="x", pady=(T.sp(4), 0))
        for label in (self.idea_lbl, self.idea_desc):
            self._context_scroll._bind_wheel(label)

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, T.sp(14)))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0, minsize=T.sp(240))
        body.grid_columnconfigure(1, weight=1)

        left = T.Card(body, pad=T.sp(10))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, T.sp(12)))
        K.eyebrow(left.body, "方法顺序", "%02d" % len(SK.SKILLS)).pack(
            fill="x", pady=(T.sp(2), T.sp(8)))
        self._wrap(tk.Label(left.body, text="按想法成熟度推进", bg=T.CARD,
                            fg=T.TXT3, font=T.T_CAPTION(), anchor="w",
                            justify="left")).pack(fill="x", pady=(0, T.sp(8)))
        self.list_scroll = T.ScrollArea(left.body, bg=T.CARD)
        self.list_scroll.pack(fill="both", expand=True)
        self.list_box = self.list_scroll.inner

        right = T.Card(body, pad=T.sp(16))
        right.grid(row=0, column=1, sticky="nsew")
        # 先保留底部动作的空间，再让详情占据余下高度。
        act = tk.Frame(right.body, bg=T.CARD)
        act.pack(side="bottom", fill="x", pady=(T.sp(12), 0))
        K.divider(act, pady=(0, T.sp(10)))
        self._prompt_row = WrapRow(act, gap=T.sp(8), rowgap=T.sp(6))
        self._prompt_row.pack(fill="x")
        self._prompt_row.add(T.Btn(self._prompt_row, "生成这一步的提示词",
                                   self.prompt_one, "primary"))
        self._prompt_row.add(T.Btn(self._prompt_row, "生成完整改进计划",
                                   self.prompt_plan))
        self.detail = T.ScrollArea(right.body, bg=T.CARD)
        self.detail.pack(fill="both", expand=True)
        # 本页的文字会随宽度增高，内容窗口保持自然高度，避免旧视口高度裁掉末段。
        self.detail.canvas.bind("<Configure>", self._natural_detail_height, add="+")
        self.select(0)

    def _natural_detail_height(self, _e=None):
        self.detail.canvas.itemconfigure(self.detail._win, height=0)

    def _item(self, i, s):
        active = self.sel == i
        item_bg = T.tint(T.ACCENT, 0.07, T.CARD) if active else T.CARD
        outer = tk.Frame(self.list_box, bg=T.CARD, cursor="hand2")
        outer.pack(fill="x", pady=T.sp(2))
        bar = tk.Frame(outer, bg=T.ACCENT if active else T.CARD, width=T.sp(3))
        bar.pack(side="left", fill="y")
        row = tk.Frame(outer, bg=item_bg, cursor="hand2")
        row.pack(side="left", fill="x", expand=True)
        num = tk.Label(row, text="%02d" % (i + 1), bg=item_bg,
                       fg=T.ACCENT if active else T.TXT4, font=T.M(8))
        num.pack(side="left", anchor="n", padx=(T.sp(8), T.sp(6)), pady=T.sp(10))
        name = self._wrap(tk.Label(
            row, text=s["name"], bg=item_bg, fg=T.TXT if active else T.TXT2,
            font=T.T_LABEL() if active else T.T_BODY_SM(), anchor="w", justify="left"))
        name.pack(side="left", fill="x", expand=True,
                  padx=(0, T.sp(8)), pady=T.sp(10))
        for w in (outer, bar, row, num, name):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda e, idx=i: self.select(idx))
            self.list_scroll._bind_wheel(w)

    def select(self, i):
        self.sel = i
        for w in self.list_box.winfo_children():
            w.destroy()
        for j, skill in enumerate(SK.SKILLS):
            self._item(j, skill)
        s = SK.SKILLS[i]
        self.detail.clear()
        self.detail.scroll_to_top()
        box = self.detail.inner
        bg = T.CARD
        # 使用可销毁的内容容器，切换方法不会在 ScrollArea.inner 上累积绑定。
        content = tk.Frame(box, bg=bg)
        content.pack(fill="x")
        K.eyebrow(content, s["en"], "%02d / %02d" % (i + 1, len(SK.SKILLS))).pack(
            fill="x", pady=(0, T.sp(6)))
        self._wrap(tk.Label(content, text=s["name"], bg=bg, fg=T.TXT,
                            font=T.T_SECTION(), anchor="w", justify="left")).pack(fill="x")
        self._wrap(tk.Label(content, text="适用时机：" + s["when"], bg=bg, fg=T.TXT3,
                            font=T.T_CAPTION(), anchor="w", justify="left")).pack(
                                fill="x", pady=(T.sp(4), T.sp(12)))

        goal_bg = T.tint(T.ACCENT, 0.07, bg)
        goal = tk.Frame(content, bg=goal_bg)
        goal.pack(fill="x", pady=(0, T.sp(16)))
        self._wrap(tk.Label(goal, text="这一步的目标", bg=goal_bg, fg=T.ACCENT,
                            font=T.T_LABEL(), anchor="w", justify="left")).pack(
                                fill="x", padx=T.sp(12), pady=(T.sp(10), 0))
        self._wrap(tk.Label(goal, text=s["goal"], bg=goal_bg, fg=T.TXT,
                            font=T.T_BODY(), anchor="w", justify="left")).pack(
                                fill="x", padx=T.sp(12), pady=(T.sp(4), T.sp(10)))

        cols = tk.Frame(content, bg=bg)
        cols.pack(fill="x")
        cols.grid_columnconfigure(0, weight=1)
        steps_col = tk.Frame(cols, bg=bg)
        steps_col.grid(row=0, column=0, sticky="nsew")
        side_col = tk.Frame(cols, bg=bg)
        side_col.grid(row=1, column=0, sticky="nsew", pady=(T.sp(16), 0))
        two_cols = False

        def layout(e):
            nonlocal two_cols
            wide = e.width >= T.sp(880)
            if wide == two_cols:
                return
            two_cols = wide
            cols.grid_columnconfigure(0, weight=1, uniform="skills" if wide else "")
            cols.grid_columnconfigure(1, weight=1 if wide else 0,
                                      uniform="skills" if wide else "")
            steps_col.grid_configure(padx=(0, T.sp(16) if wide else 0))
            side_col.grid_configure(row=0 if wide else 1, column=1 if wide else 0,
                                    pady=(0 if wide else T.sp(16), 0))
            self._natural_detail_height()

        cols.bind("<Configure>", layout, add="+")
        self._wrap(tk.Label(steps_col, text="操作步骤", bg=bg, fg=T.TXT,
                            font=T.T_SECTION(), anchor="w", justify="left")).pack(
                                fill="x", pady=(0, T.sp(8)))
        for k, step in enumerate(s["steps"], 1):
            row = tk.Frame(steps_col, bg=bg)
            row.pack(fill="x", pady=T.sp(4))
            tk.Label(row, text="%02d" % k, bg=T.tint(T.ACCENT, 0.08, bg),
                     fg=T.ACCENT, font=T.M(8), padx=T.sp(5), pady=T.sp(2)).pack(
                         side="left", anchor="n")
            self._wrap(tk.Label(row, text=step, bg=bg, fg=T.TXT2,
                                font=T.T_BODY_SM(), anchor="w", justify="left")).pack(
                                    side="left", fill="x", expand=True, padx=(T.sp(10), 0))

        for title, text, color, amount in (
                ("产出要求", s["output"], T.OK, 0.06),
                ("常见错误", s["pitfall"], T.WARN, 0.08)):
            panel_bg = T.tint(color, amount, bg)
            panel = tk.Frame(side_col, bg=panel_bg)
            panel.pack(fill="x", pady=(0, T.sp(12)))
            self._wrap(tk.Label(panel, text=title, bg=panel_bg, fg=color,
                                font=T.T_LABEL(), anchor="w", justify="left")).pack(
                                    fill="x", padx=T.sp(12), pady=(T.sp(10), 0))
            self._wrap(tk.Label(panel, text=text, bg=panel_bg, fg=T.TXT2,
                                font=T.T_BODY_SM(), anchor="w", justify="left")).pack(
                                    fill="x", padx=T.sp(12), pady=(T.sp(4), T.sp(10)))

        self._wrap(tk.Label(side_col, text="下一步", bg=bg, fg=T.TXT3,
                            font=T.T_CAPTION(), anchor="w", justify="left")).pack(
                                fill="x", pady=(T.sp(2), T.sp(6)))
        if i + 1 < len(SK.SKILLS):
            nxt = SK.SKILLS[i + 1]
            card = tk.Frame(side_col, bg=T.CARD_HI, cursor="hand2")
            card.pack(fill="x", pady=(0, T.sp(6)))
            label = self._wrap(tk.Label(
                card, text="%02d  %s" % (i + 2, nxt["name"]), bg=T.CARD_HI,
                fg=T.ACCENT, font=T.T_LABEL(), anchor="w", justify="left", cursor="hand2"))
            label.pack(fill="x", padx=T.sp(10), pady=T.sp(10))
            for w in (card, label):
                w.bind("<Button-1>", lambda e, idx=i + 1: self.select(idx))
            next_text = nxt.get("when", "")
        else:
            next_text = "这是最后一步。回看「问题收敛」留下的问题陈述，检查它有没有被实验结果推翻。"
        self._wrap(tk.Label(side_col, text=next_text, bg=bg, fg=T.TXT3,
                            font=T.T_CAPTION(), anchor="w", justify="left")).pack(fill="x")

        K.divider(content, pady=(T.sp(16), T.sp(10)))
        self._wrap(tk.Label(
            content, text="没配大模型也能用：生成提示词后，复制到任意 AI。"
                          "方法手册不替代文献核查与真实实验，也不保证投稿录用。",
            bg=bg, fg=T.TXT3, font=T.T_CAPTION(), anchor="w", justify="left")).pack(fill="x")
        self._hint = U.Hint(content, SKILLS_HELP, summary="这七个方法怎么用", bg=bg)
        self._hint.pack(fill="x", pady=(T.sp(8), 0))
        self._wrap(self._hint._detail)
        self._hint._lbl.configure(cursor="hand2")
        self._hint._lbl.bind("<Button-1>", lambda e: self._hint.toggle())
        tk.Frame(content, bg=bg, height=T.sp(14)).pack(fill="x")
        widgets = [content]
        while widgets:
            widget = widgets.pop()
            self.detail._bind_wheel(widget)
            widgets.extend(widget.winfo_children())
        self._natural_detail_height()
        self.detail.refresh(defer=True)
        self.list_scroll.refresh(defer=True)

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
                 font=T.T_PAGE_TITLE()).pack(anchor="w", padx=T.sp(18),
                                             pady=(T.sp(16), T.sp(8)))
        sa = T.ScrollArea(win)
        sa.pack(fill="both", expand=True, padx=T.sp(18), pady=(0, T.sp(16)))
        sa.canvas.bind("<Configure>", lambda e: sa.canvas.itemconfigure(sa._win, height=0),
                       add="+")
        for it in reversed(ideas):
            f = tk.Frame(sa.inner, bg=T.CARD, cursor="hand2")
            f.pack(fill="x", pady=T.sp(2))
            title = self._wrap(tk.Label(
                f, text=str(it.get("title") or "（无标题）"), bg=T.CARD, fg=T.TXT,
                font=T.T_LABEL(), anchor="w", justify="left", cursor="hand2"))
            title.pack(fill="x", padx=T.sp(10), pady=(T.sp(8), 0))
            desc = self._wrap(tk.Label(
                f, text=str(it.get("desc") or ""), bg=T.CARD, fg=T.TXT3,
                font=T.T_CAPTION(), anchor="w", justify="left", cursor="hand2"))
            desc.pack(fill="x", padx=T.sp(10), pady=(T.sp(4), T.sp(8)))
            for w in (f, title, desc):
                w.bind("<Button-1>", lambda e, x=it: self._set_idea(x, win))
                sa._bind_wheel(w)

    def _set_idea(self, it, win):
        self.idea = {"title": it.get("title", ""), "desc": it.get("desc", ""),
                     "type": it.get("type", "")}
        self.idea_lbl.config(text=str(it.get("title") or "（无标题）"), fg=T.TXT)
        self.idea_desc.config(text=str(it.get("desc") or "未填写课题说明；提示词仅带入已有信息。"))
        self._context_scroll.scroll_to_top()
        self._context_scroll.refresh(defer=True)
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