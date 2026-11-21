#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""选题工坊页：一个选题从「方向」到「可执行」的完整链路。

  1  研究方向识别      infer_category_field + field_profile
  2  候选选题          expand_direction_candidates（稳健邻接/跨域迁移/高风险高回报）
  3  三维体检          evaluate_idea_local（机制 / 证据 / 风险）
  4  周边资源          recommend_venues + recommend_advisors
  5  落库与交接        保存为创新点 + 生成交接提示词（复制到剪贴板）

引擎全部来自 kb_widget，本页只负责把结果组织成可操作的工作流。
"""
import threading
import tkinter as tk

import webbrowser

import app_theme as T
import ui_kit as UK            # noqa: E402
import ui_parts as U             # noqa: E402
from ui_parts import WrapRow   # 会自动折行的按钮排
import app_diagnose_view as diag_view
import advisor_index
import llm_bridge as L
import profile_memory as PM
import novelty_check
import topic_constraint
import topic_fusion
_card_head = T.card_head
import topic_gen
import kb_widget as kb

PAGE_HINT = "方向识别 → 候选选题 → 三维体检 → venue / 导师 → 落库"

# 跨领域（交叉）模式：A 研究方向 + B 方法/技术 + C 邻接领域。
# 为什么要有它：真实交叉课题从来不是一个词，而是「方向 × 方法 × 邻域」拼起来的。
# 只给 A 时系统只能猜 B，候选就变成通用的；把 B 明说出来，候选才真的是他的题。
FUSION_KINDS = ("自动", "借方法", "搬场景", "找共性", "反向借鉴", "三方交叉")
_KIND_ALIAS = {"借方法": "技术驱动", "搬场景": "下游迁移", "找共性": "共通抽象",
               "反向借鉴": "反向借鉴", "三方交叉": "三方交叉"}


def _cfm(lb):
    """候选卡标题 / 小字在**每次重排时**重算换行宽度。

    `_cand_row` 只在生成那一刻量一次 `cand_scroll.canvas.winfo_width()`；
    三栏在空态时是收起状态（宽度 1），若用户先拉窄窗口再生成，
    量到的就是旧宽度，标题会被折成两行 —— 这正是截图里出现过的样子。
    """
    def _fit(e=None):
        try:
            w = lb.master.master.winfo_width()
            if w > 60:
                lb.config(wraplength=max(120, w - 16))
        except Exception:
            pass
    lb.bind("<Configure>", _fit, add="+")



def _draw_direction_graph(cv, w, h):
    """英雄卡里的方向示意图：虚线轨迹 + 节点 + 中心「题」。

    网页版这里是一张手绘风的方向网络；桌面上用 Canvas 画同样的语言，
    比嵌位图更稳（缩放、深色模式、DPI 都不会糊）。
    """
    cv.delete("all")
    if w < 120 or h < 60:
        return
    line = T.tint(T.ACCENT, 0.38, T.CARD)
    soft = T.tint(T.ACCENT, 0.22, T.CARD)
    x0, x1 = T.sp(14), w - T.sp(14)
    y = h * 0.58
    pts = (x0, y + h * 0.06, x0 + (x1 - x0) * 0.22, y - h * 0.24,
           x0 + (x1 - x0) * 0.48, y + h * 0.10,
           x0 + (x1 - x0) * 0.74, y - h * 0.20, x1, y - h * 0.02)
    cv.create_line(pts, smooth=True, splinesteps=24, dash=(3, 5),
                   fill=soft, width=1)
    pts2 = (x0, y - h * 0.12, x0 + (x1 - x0) * 0.20, y + h * 0.18,
            x0 + (x1 - x0) * 0.50, y - h * 0.16,
            x0 + (x1 - x0) * 0.78, y + h * 0.16, x1, y - h * 0.06)
    cv.create_line(pts2, smooth=True, splinesteps=24, fill=line, width=1)
    for _fx, _fy, _r in ((0.16, 0.22, 3), (0.37, 0.72, 3),
                         (0.62, 0.30, 3), (0.84, 0.74, 3)):
        _x, _y = x0 + (x1 - x0) * _fx, h * _fy
        cv.create_oval(_x - _r, _y - _r, _x + _r, _y + _r,
                       fill=T.CARD, outline=T.ACCENT, width=1)
    cx, cy, r = w / 2.0, y - h * 0.05, T.sp(17)
    cv.create_oval(cx - r, cy - r, cx + r, cy + r,
                   fill=T.ACCENT, outline="")
    cv.create_text(cx, cy, text="题", fill=T.on_primary_fg(),
                   font=(T.SERIF, -max(14, int(round(16 * T.font_scale()))), "bold"))
    for _tx, _ty, _label in ((x0 - T.sp(2), y + h * 0.22, "应用场景"),
                             (x1 - T.sp(58), y - h * 0.34, "公开基准")):
        _tw = max(T.sp(52), T.sp(10) * len(_label))
        cv.create_rectangle(_tx, _ty - T.sp(9), _tx + _tw, _ty + T.sp(9),
                            fill=T.tint(T.ACCENT, 0.08, T.CARD),
                            outline=T.tint(T.ACCENT, 0.22, T.CARD))
        cv.create_text(_tx + _tw / 2.0, _ty, text=_label, fill=T.TXT3,
                       font=(T.BASE, -13))


class TopicPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.cands = []
        self.sel = None
        self.ctx = {}
        self._bullets = []
        self._ai_box = None
        self._ai_running = False
        self._build()

    # ------------------------------------------------------------ 布局
    def _build(self):
        # 结果态顶栏（网页版 .recognize-bar）：方向识别摘要 + 调整方向。
        # 空态整块隐藏，输入框在英雄卡里；生成之后英雄卡让位给三栏工作台，
        # 这条栏负责告诉用户「系统把你的输入理解成了什么」。
        self._result_bar = T.Card(self, bg=T.CARD, border=T.LINE_SOFT,
                                  radius=T.RADIUS, pad=T.sp(12))
        rb = self._result_bar.body
        row = tk.Frame(rb, bg=T.CARD)
        row.pack(fill="x")
        # 按钮先占住右端：方向名动辄二三十个字，若标题先 pack，
        # 它会一路顶到按钮底下，截图里三个按钮只剩半个「素」字。
        right = tk.Frame(row, bg=T.CARD)
        right.pack(side="right")
        T.Btn(right, "素材库", lambda: self.app.goto("materials"), "ghost").pack(
            side="right", padx=(T.sp(6), 0))
        T.Btn(right, "调整方向", self.reset_direction, "ghost").pack(side="right")
        T.Btn(right, "方法论帮助", self.show_help, "ghost").pack(
            side="right", padx=(0, T.sp(6)))
        self.result_title = tk.Label(row, text="", bg=T.CARD, fg=T.TXT,
                                     font=T.T_SECTION(), anchor="w", justify="left")
        self.result_title.pack(side="left", fill="x", expand=True)
        self.result_meta = tk.Label(rb, text="", bg=T.CARD, fg=T.TXT3,
                                    font=T.T_CAPTION(), anchor="w", justify="left")
        self.result_meta.pack(fill="x", pady=(T.sp(2), 0))

        # 「换个角度」一行：首屏不建控件，第一次生成后才铺。
        self.mode = tk.StringVar(value=kb.DIRECTION_MODES[0])
        self.fuse_kind = tk.StringVar(value=FUSION_KINDS[0])
        self.tweak = tk.Frame(self, bg=T.BG)
        self.fuse_bar = tk.Frame(self, bg=T.BG)
        self._fuse_open = False
        self._tweak_ready = False
        self.entry_b = None
        self.entry_c = None

        def _mk_fuse_entry(parent):
            e = tk.Entry(parent, bg=T.CARD, fg=T.TXT, insertbackground=T.ACCENT,
                         relief="flat", highlightbackground=T.LINE,
                         highlightthickness=1, font=T.T_BODY_SM(), width=13)
            e.bind("<Return>", lambda ev: self.generate())
            e.bind("<KeyRelease>", lambda ev: self._peek_b() if e is self.entry_b
                   else self._peek_c())
            return e

        def _build_tweak():
            """把「换个角度」这一行铺出来（只在第一次生成之后调一次）。"""
            if self._tweak_ready:
                return
            self._tweak_ready = True
            # 这里只建控件：此刻 _under_wrap 还没 pack，
            # 真正的安放在 _set_cards_visible(True) 里统一做。
            tk.Label(self.tweak, text="换个角度", bg=T.BG, fg=T.TXT3,
                     font=T.T_CAPTION()).pack(side="left", padx=(0, 8))
            om = tk.OptionMenu(self.tweak, self.mode, *kb.DIRECTION_MODES)
            om.config(bg=T.CARD, fg=T.TXT, activebackground=T.ACCENT_D,
                      activeforeground=T.ACCENT, relief="flat", bd=0,
                      highlightthickness=0, font=T.T_CAPTION(), width=9)
            om["menu"].config(bg=T.CARD, fg=T.TXT, activebackground=T.ACCENT_D,
                              activeforeground=T.ACCENT, bd=0, font=T.T_CAPTION())
            om.pack(side="left", padx=(0, 6))
            T.Btn(self.tweak, "重新生成", self.generate, "ghost").pack(side="left")
            self.fuse_btn = T.Btn(self.tweak, "＋ 跨领域组合", self._toggle_fuse, "ghost")
            self.fuse_btn.pack(side="left", padx=(6, 0))

            tk.Label(self.fuse_bar, text="借来的方法", bg=T.BG, fg=T.TXT3,
                     font=T.T_CAPTION()).pack(side="left", padx=(0, 6))
            self.entry_b = _mk_fuse_entry(self.fuse_bar)
            self.entry_b.pack(side="left", padx=(0, 10))
            tk.Label(self.fuse_bar, text="推广到", bg=T.BG, fg=T.TXT3,
                     font=T.T_CAPTION()).pack(side="left", padx=(0, 6))
            self.entry_c = _mk_fuse_entry(self.fuse_bar)
            self.entry_c.pack(side="left", padx=(0, 10))
            fk = tk.OptionMenu(self.fuse_bar, self.fuse_kind, *FUSION_KINDS)
            fk.config(bg=T.CARD, fg=T.TXT, activebackground=T.ACCENT_D,
                      activeforeground=T.ACCENT, relief="flat", bd=0,
                      highlightthickness=0, font=T.T_CAPTION(), width=9)
            fk["menu"].config(bg=T.CARD, fg=T.TXT, activebackground=T.ACCENT_D,
                              activeforeground=T.ACCENT, bd=0, font=T.T_CAPTION())
            fk.pack(side="left")
            for e in (self.entry_b, self.entry_c):
                try:
                    import app_suggest
                    app_suggest.attach(e)
                except Exception as exc:
                    print("联想词挂载失败:", exc)
        self._build_tweak = _build_tweak

        # 画像理解条（第 16 版收成一行 + 可展开）
        # 第 15 版这里有三条独立信息带：画像条 / 硬条件 / 新颖性汇总，
        # 生成候选后合计占 90px，而它们讲的是「系统怎么理解你刚才那句话」——
        # 看过一次就够了。现在默认只留一行摘要，其余折进「理解详情」。
        self._under_wrap = tk.Frame(self, bg=T.BG)
        # 不在这里 pack：这行讲的是「系统怎么理解你的输入」，
        # 空态还没有输入可解释，先让英雄卡占满视线；有结果时再插到顶栏下面。
        _ur = tk.Frame(self._under_wrap, bg=T.BG)
        _ur.pack(fill="x")
        self.profile_lbl = tk.Label(_ur, text="输入方向后回车，或从下方示例开始。",
                                    bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                                    justify="left")
        self.profile_lbl.pack(side="left", fill="x", expand=True)
        T.fill_wrap(self.profile_lbl, pad=8)
        self._expanded = False
        self._nov_text = ""
        self._under_btn = T.Btn(_ur, "理解详情", self._toggle_under, "ghost")
        self._under = tk.Frame(self, bg=T.BG)
        # 展开区里放「硬条件 / 回退说明」和「新颖性汇总」两块，
        # 拆成多个 Frame 是因为它们的显示时机不同（新颖性是后台核完才出来）。
        self.profile_sub = tk.Frame(self._under, bg=T.BG)
        self.nov_lbl = tk.Label(self._under, text="", bg=T.BG, fg=T.TXT3,
                                font=T.T_BODY_SM(), anchor="w", justify="left")

        # 兼容旧锚点：部分显隐逻辑会遍历 examples，真正的示例标签
        # 已经搬进英雄卡的右栏（网页版就是这样放的）。
        self.examples = tk.Frame(self, bg=T.BG)

        # 三栏（第 10 版）
        # 第 7 版把卡片从「撑满整屏」改成跟随内容，但三张卡各自独立定高，
        # 结果中栏比左栏长 60px、右栏又短一截，底边参差不齐，看着像没对齐。
        # 现在三栏统一走「等高单元格」：外层 grid 把三列都设 weight=1 且
        # rowconfigure(0, weight=1)，卡片 sticky="nsew" 一起拉伸；
        # 内容不足时由 scroll 的 height 下限兜住，不会缩成一条线。
        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        self._body = body
        body.grid_rowconfigure(0, weight=1)
        # 不能带 uniform="c"：uniform 会把组内各列的最小宽度一律取成
        # 「组内最大值 × 该列 weight」，右栏那串 venue 名（不可折行的英文）
        # 会把基准撑高，结果是左栏变宽、中栏反而被挤窄。
        body.grid_columnconfigure(0, weight=3, uniform="")
        body.grid_columnconfigure(1, weight=4, uniform="")
        body.grid_columnconfigure(2, weight=3, uniform="")

        # ---- 左：候选
        left = T.Card(body, pad=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._cards = []
        self._cards.append(left)
        UK.eyebrow(left.body, "CANDIDATE SET", bg=T.CARD).pack(fill="x")
        _lh = tk.Frame(left.body, bg=T.CARD)
        _lh.pack(fill="x", pady=(T.sp(4), T.sp(2)))
        tk.Label(_lh, text="候选选题", bg=T.CARD, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(side="left")
        self.cand_count = tk.Label(_lh, text="", bg=T.CARD, fg=T.TXT4,
                                   font=T.T_CAPTION(), anchor="e")
        self.cand_count.pack(side="right")
        _sub = tk.Label(left.body, text="分数是本地预筛，不是结论", bg=T.CARD,
                        fg=T.TXT4, font=T.T_CAPTION(), anchor="w")
        _sub.pack(fill="x", pady=(0, T.sp(6)))
        T.fill_wrap(_sub, pad=6)
        self.cand_scroll = T.ScrollArea(left.body, bg=T.CARD, height=120)
        self.cand_scroll.pack(fill="both", expand=True)

        # ---- 中：详情 + 体检
        mid = T.Card(body, pad=12)
        mid.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        self._cards.append(mid)
        self._mid_wrap = 430
        _mh = tk.Frame(mid.body, bg=T.CARD)
        _mh.pack(fill="x")
        UK.eyebrow(_mh, "RESEARCH BRIEF", bg=T.CARD).pack(
            side="left", fill="x", expand=True)
        self.detail_idx = tk.Label(_mh, text="", bg=T.CARD, fg=T.TXT4,
                                   font=T.T_CAPTION(), anchor="e")
        self.detail_idx.pack(side="right")
        self.detail_head = tk.Label(mid.body, text="未选择候选", bg=T.CARD, fg=T.TXT,
                                    font=T.T_SECTION(), anchor="w", justify="left",
                                    wraplength=self._mid_wrap)
        self.detail_head.pack(fill="x", pady=(T.sp(2), 0))
        self.detail_meta = tk.Label(mid.body, text="在左侧点选一个候选，这里显示它的验证问题与体检结果。",
                                    bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(), anchor="w",
                                    justify="left", wraplength=self._mid_wrap)
        self.detail_meta.pack(fill="x", pady=(2, 6))
        # 中间栏宽度随窗口变化，包一层按实际宽度重设 wraplength
        mid.body.bind("<Configure>", self._on_mid_resize)
        self.detail_scroll = T.ScrollArea(mid.body, bg=T.CARD, height=120)
        self.detail_scroll.pack(fill="both", expand=True)
        self.detail_box = tk.Frame(self.detail_scroll.inner, bg=T.CARD)
        self.detail_box.pack(fill="both", expand=True)

        # 动作条（第 10 版）：
        # 原来这里是四个平级按钮「存为创新点 / AI 挑刺 / 生成交接提示词 / 复制清单」，
        # 用户得自己判断「下一步该按哪个」。实际上这四件事有明确先后：
        #   ① 认下这条（存进创新点库）——主路径，一个按钮
        #   ② 交出去做（提示词 / 清单）——生成后要复制走
        #   ③ 挑刺（本地体检已在详情里，AI 只是补充）
        # 所以拆成「主按钮 + 更多」两层：默认只看见两件事，其余收进弹出菜单。
        act = U.WrapRow(mid.body)
        self._act = act      # 选中候选后才 pack（空态不摆用不了的按钮）
        # 三个放得下就一行：中栏再窄也够（三个按钮合计约 300px），
        # gap 调小一点，超大字时也只是把「更多」挤到第二行，不会变成一块一块的台阶。
        act._gap = 4
        self.btn_save = T.Btn(act, "存为创新点", self.save_idea, "primary")
        act.add(self.btn_save)
        self.btn_prompt = T.Btn(act, "交接提示词", self.make_prompt, "ok")
        act.add(self.btn_prompt)
        self.btn_more = T.Btn(act, "更多", self._more_menu, "ghost")
        act.add(self.btn_more)
        # 125% DPI + 大字号下三个按钮合计会顶到 387px，中栏只有 338px，
        # 第三个被折到第二行、占掉详情区一半高度。只收窄这三个的左右内边距
        # （12→4），合计约 327px，一屏内排得下，文案不动。
        for _b in (self.btn_save, self.btn_prompt, self.btn_more):
            _b.config(padx=T.sp(4))
        # 大模型挑刺：没配置时也留着，点了引导去设置页，藏起来反而让人以为没这功能
        self.btn_ai = T.Btn(act, "AI 挑刺", self.ai_critique)
        # 存入结果就地留一行：toast 两秒就消失，用户根本没看见「存了没有、存了几条」，
        # 连点两下也看不出区别。按钮文案同步改，状态才能一直挂在眼前。
        self._save_note = tk.Label(mid.body, text="", bg=T.CARD, fg=T.TXT3,
                                   font=T.T_CAPTION(), anchor="w", justify="left",
                                   wraplength=self._mid_wrap)

        # ---- 右：资源
        right = T.Card(body, pad=12)
        right.grid(row=0, column=2, sticky="nsew")
        self._cards.append(right)
        UK.eyebrow(right.body, "SUPPORTING INDEX", bg=T.CARD).pack(fill="x")
        tk.Label(right.body, text="投稿与导师", bg=T.CARD, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(fill="x",
                                                      pady=(T.sp(4), 0))
        _rnote = tk.Label(right.body, text="公开索引匹配，官网核验", bg=T.CARD,
                          fg=T.TXT4, font=T.T_CAPTION(), anchor="w")
        _rnote.pack(fill="x", pady=(0, T.sp(6)))
        T.fill_wrap(_rnote, pad=6)
        self.side_scroll = T.ScrollArea(right.body, bg=T.CARD, height=120)
        self.side_scroll.pack(fill="both", expand=True)

        self._hint(self.cand_scroll.inner, "还没有候选。\n在上方输入研究方向后点「生成候选」。")
        self._hint(self.side_scroll.inner, "选择候选后显示会议 / 期刊与导师。")

        # 空态英雄区（对齐网页版 workshop-intro）：
        # 左边讲「这是一个什么入口」，右边就是输入面板本身。
        # 原来是一整块白卡 + 两列文字，窗口一宽右半屏全空；
        # 现在左栏有衬线大标题、方向图与规模数字，右栏是真正能操作的表单。
        self._welcome = tk.Frame(self, bg=T.BG)
        self._welcome_card = T.Card(self._welcome, pad=T.sp(22), fill_y=True)
        self._welcome_card.pack(fill="both", expand=True)
        wb = self._welcome_card.body

        # ---- 右：输入面板（定宽；先打包，保证左栏拿到剩余宽度）
        # 网页版英雄卡是「一张大圆角卡，内部一条竖线分左右」，
        # 右栏本身不再叠一层圆角。
        rc = tk.Frame(wb, bg=T.CARD_HI, highlightbackground=T.LINE_SOFT,
                      highlightthickness=1, width=T.sp(460))
        rc.pack(side="right", fill="y")
        rc.pack_propagate(False)
        rp = tk.Frame(rc, bg=T.CARD_HI)
        rp.pack(fill="both", expand=True, padx=T.sp(16), pady=T.sp(14))
        self._hero_wb = wb
        self._hero_right = rc
        self._hero_side = "full"    # "full"=常规左右分栏；"slim"=窄右栏
        self._hero_job = None

        # ---- 左：标题 + 方向图 + 规模
        left = tk.Frame(wb, bg=T.CARD)
        left.pack(side="left", fill="both", expand=True, padx=(0, T.sp(26)))
        self._hero_left_col = left
        lhead = tk.Frame(left, bg=T.CARD)
        lhead.pack(fill="x")
        UK.eyebrow(lhead, "DIRECTION INTAKE", bg=T.CARD).pack(
            side="left", fill="x", expand=True)
        T.Btn(lhead, "方法论", self.show_help, "ghost").pack(side="right")

        _hero_title = tk.Label(
            left, text="从一个研究方向，\n走到可核查的问题。",
            bg=T.CARD, fg=T.TXT, font=T.T_HERO(), anchor="w", justify="left")
        _hero_title.pack(fill="x", pady=(T.sp(6), T.sp(6)))
        _hero_lead = tk.Label(
            left,
            text="输入方向，或按应用场景与任务标签组合；确认后生成候选，"
                 "并附上可核查的选题理由、最小验证与投稿导师。",
            bg=T.CARD, fg=T.TXT2, font=T.T_BODY_SM(), anchor="w", justify="left")
        _hero_lead.pack(fill="x")
        T.fill_wrap(_hero_lead, pad=6)
        self._hero_lead = _hero_lead

        self._hero_graph = tk.Canvas(left, bg=T.CARD, height=T.sp(96),
                                     highlightthickness=0, bd=0)
        self._hero_graph.pack(fill="x", pady=(T.sp(6), T.sp(8)))
        self._hero_graph.bind(
            "<Configure>",
            lambda e: _draw_direction_graph(self._hero_graph, e.width, e.height))

        stats = tk.Frame(left, bg=T.CARD)
        # 先占底部再挂其余内容：pack 按顺序分配，晚装的控件在空间不足时
        # 会被裁掉下半截。1240×800 + 大字号下四个数字卡就曾被卡在卡片底边。
        stats.pack(fill="x", side="bottom", before=self._hero_graph)
        self._hero_stats = []
        self._stat_tiles = []
        self._stat_labs = []
        for _i, _lab in enumerate(("研究方向", "素材条目", "本地文献", "应用领域")):
            stats.grid_columnconfigure(_i, weight=1, uniform="hs")
            _tile = tk.Frame(stats, bg=T.CARD, highlightbackground=T.LINE_SOFT,
                             highlightthickness=1)
            _tile.grid(row=0, column=_i, sticky="nsew",
                       padx=(0 if _i == 0 else T.sp(6), 0))
            _val = tk.Label(_tile, text="—", bg=T.CARD, fg=T.TXT,
                            font=(T.MONO, -20, "bold"), anchor="w")
            _val.pack(fill="x", padx=T.sp(4), pady=(T.sp(6), 0))
            _cap = tk.Label(_tile, text=_lab, bg=T.CARD, fg=T.TXT4,
                            font=T.T_CAPTION(), anchor="w")
            _cap.pack(fill="x", padx=T.sp(4), pady=(0, T.sp(6)))
            self._hero_stats.append(_val)
            self._stat_tiles.append(_tile)
            self._stat_labs.append(_cap)
        self._stat_box = stats
        self._stat_cell_need = 0
        # 2026-11-19：四格横排在窄窗口下装不下。1080×680 时这一栏只有
        # 382px，而每格请求 98px（「研究方向」在 T_CAPTION 下要 86px +
        # 左右 padx），4×98 + 3×7 = 413 —— 差 31px，四个中文标签全被切掉
        # 半个字（扫描器报「需要86 只有74」）。这里按实际可用宽度在
        # 「1 行 4 列」和「2 行 2 列」之间切，不靠写死断点。
        stats.bind("<Configure>",
                   lambda e, s=stats: self._layout_stats(e.width), add="+")

        self._hero_strip = tk.Frame(rp, bg=T.CARD,
                                   highlightbackground=T.LINE_SOFT,
                                   highlightthickness=1)
        strip = self._hero_strip
        strip.pack(fill="x")
        for _k, _v in (("搜索方向", "名称或术语"),
                       ("标签组合", "场景 × 任务"),
                       ("全部方向", "方向库")):
            _cell = tk.Frame(strip, bg=T.CARD)
            _cell.pack(side="left", fill="both", expand=True,
                       padx=T.sp(10), pady=T.sp(7))
            tk.Label(_cell, text=_k, bg=T.CARD, fg=T.TXT,
                     font=T.T_LABEL(), anchor="w").pack(fill="x")
            tk.Label(_cell, text=_v, bg=T.CARD, fg=T.TXT4,
                     font=T.T_CAPTION(), anchor="w").pack(fill="x")

        qrow = tk.Frame(rp, bg=T.CARD_HI)
        qrow.pack(fill="x", pady=(T.sp(11), T.sp(5)))
        self._hero_qrow = qrow
        tk.Label(qrow, text="研究方向", bg=T.CARD_HI, fg=T.TXT,
                 font=T.T_LABEL(), anchor="w").pack(side="left")
        tk.Label(qrow, text="RESEARCH DIRECTION", bg=T.CARD_HI, fg=T.TXT4,
                 font=T.T_EYEBROW(), anchor="e").pack(side="right")

        in_box = tk.Frame(rp, bg=T.CARD, highlightbackground=T.LINE,
                          highlightthickness=1)
        in_box.pack(fill="x")
        self.entry = tk.Entry(in_box, bg=T.CARD, fg=T.TXT,
                              insertbackground=T.ACCENT, relief="flat",
                              highlightthickness=0, bd=0, font=T.T_BODY(),
                              width=1)
        self.entry.pack(side="left", fill="x", expand=True,
                        ipady=T.sp(9), padx=(T.sp(11), 0))
        self.entry.bind("<Return>", lambda e: self.generate())
        try:
            import app_suggest
            app_suggest.attach(self.entry)
        except Exception as exc:
            print("联想词挂载失败:", exc)
        self.go_btn = T.Btn(in_box, "生成候选", self.generate, "primary")
        self.go_btn.pack(side="left", padx=T.sp(4), pady=T.sp(4))

        tk.Label(rp, text="示例", bg=T.CARD_HI, fg=T.TXT4,
                 font=T.T_CAPTION(), anchor="w").pack(
            fill="x", pady=(T.sp(8), T.sp(3)))
        _ex = U.WrapRow(rp, gap=T.sp(5), rowgap=T.sp(4), bg=T.CARD_HI)
        _ex.pack(fill="x")
        self._hero_ex = _ex
        for _txt in ("单目深度估计", "红外小目标检测", "大语言模型高效推理",
                     "联邦学习隐私保护"):
            _ex.add(UK.Chip(_ex, _txt, bg=T.CARD_HI,
                            command=lambda t=_txt: self.use_example(t)))

        self._hero_catblock = tk.Frame(rp, bg=T.CARD_HI)
        self._hero_catblock.pack(fill="x")
        T.hsep(self._hero_catblock, T.LINE_SOFT, (T.sp(9), T.sp(6)))
        crow = tk.Frame(self._hero_catblock, bg=T.CARD_HI)
        crow.pack(fill="x")
        _cat_hint = tk.Label(crow, text="不确定方向", bg=T.CARD_HI, fg=T.TXT3,
                             font=T.T_CAPTION(), anchor="w")
        _cat_hint.pack(side="left")
        _cat_btn = T.Btn(crow, "浏览全部大类 →", lambda: self.app.goto("map"),
                         "ghost")
        _cat_btn.pack(side="right")
        self._cat_hint, self._cat_btn = _cat_hint, _cat_btn
        self._cat_holder = tk.Frame(self._hero_catblock, bg=T.CARD_HI)
        self._cat_holder.pack(fill="x", pady=(T.sp(4), 0))
        self._cat_loading = tk.Label(self._cat_holder, text="正在统计方向库…",
                                     bg=T.CARD_HI, fg=T.TXT4,
                                     font=T.T_CAPTION(), anchor="w")
        self._cat_loading.pack(fill="x")

        # 流程说明只保留卡下方那四张 01–04；右栏里再排一遍会在窄宽度下被截尾。

        # ---- 英雄卡下方：四步说明（网页版的 01–04 卡片）
        self._welcome_steps = tk.Frame(self._welcome, bg=T.BG)
        self._welcome_steps.pack(fill="x", pady=(T.sp(10), 0))
        for _i, (_t, _d) in enumerate((
                ("识别方向", "方向名、术语或关键词"),
                ("确认场景", "叠加应用与任务标签"),
                ("生成候选", "数量随关联强度变化"),
                ("结构体检", "交代清楚才值得动手"))):
            self._welcome_steps.grid_columnconfigure(_i, weight=1, uniform="ws")
            _sc = tk.Frame(self._welcome_steps, bg=T.CARD,
                           highlightbackground=T.LINE_SOFT, highlightthickness=1)
            _sc.grid(row=0, column=_i, sticky="nsew",
                     padx=(0 if _i == 0 else T.sp(8), 0))
            _sb = tk.Frame(_sc, bg=T.CARD)
            _sb.pack(fill="x", padx=T.sp(12), pady=T.sp(9))
            tk.Label(_sb, text="%02d" % (_i + 1), bg=T.CARD, fg=T.TXT4,
                     font=T.M(8), anchor="w").pack(fill="x")
            _st = tk.Label(_sb, text=_t, bg=T.CARD, fg=T.TXT,
                           font=T.T_LABEL(), anchor="w", justify="left")
            _st.pack(fill="x", pady=(T.sp(2), 0))
            T.fill_wrap(_st, pad=10)
            _sd = tk.Label(_sb, text=_d, bg=T.CARD, fg=T.TXT4,
                           font=T.T_CAPTION(), anchor="w", justify="left")
            _sd.pack(fill="x")
            T.fill_wrap(_sd, pad=10)

        wb.bind("<Configure>", self._schedule_hero_layout)
        # 窗口高度变化时 wb 的宽度可能不变，只绑 wb 会让「矮窗收装饰」不生效；
        # 反过来刚 map 时高度还没定稿，也可能误收。两边都监听。
        self._welcome.bind("<Configure>", self._schedule_hero_layout)
        self._load_hero_data()
        self._set_cards_visible(False)
        self.after(200, self._hero_layout)

    def _schedule_hero_layout(self, e=None):
        try:
            if self._hero_job:
                self.after_cancel(self._hero_job)
            self._hero_job = self.after(120, self._hero_layout)
        except Exception:
            pass

    def _hero_layout(self, e=None):
        """英雄卡随窗口宽度/高度换挡。

        1440 宽时是网页版的左右分栏（左文案 + 方向图，右输入面板）；
        1240×800 这类小窗里，定宽右栏会把左栏挤到只剩两百多像素，
        标题和四步说明都被截字。这里按卡宽取右栏比例，并在矮窗里
        收起「三格提示条 / 方向大类 / 方向图」这三块装饰性内容，
        保证输入框、示例与规模数字始终完整。
        """
        self._hero_job = None
        try:
            w = self._hero_wb.winfo_width()
            h = self._welcome.winfo_height()
        except Exception:
            return
        if w <= 1:
            return
        # 2026-11-19：判据从「卡宽 < 760」改成「左栏还剩多少」。
        # 原来 1080×680 下 w=762 刚好在阈值上沿，没进 compact，右栏照样
        # 拿走 350px，左栏只剩 382px —— 而底部四格规模数字要 420px，
        # 四个中文标签全被切掉半个字。只比总宽差 2px 就换挡太脆，
        # 直接按「右栏拿走后还剩多少」判断，留 20px 余量。
        GAP = T.sp(26)              # 左栏右边的间距
        right = max(T.sp(300), min(T.sp(460), int(w * 0.46)))
        compact = (w - right - GAP < T.sp(440)) or h < T.sp(430)
        try:
            if compact:
                # 2026-11-19：1080×680 下右栏占 350px、左栏只剩 382px，
                # 而底部四格规模数字要 420px，四个中文标签全被切掉半个字。
                # 不能改成上下排（窗口只有 521px 高，右栏占去整行后左栏
                # 被压到 0 高），只能把右栏压窄 —— 但 pack 里 side="right"
                # 的非 expand 子项拿的是自己的请求宽度，单独改 width 会在
                # 下一次排布弹回去，所以要连 expand 一起给：右栏 expand，
                # 左栏也 expand，pack 才会按两者比例分配。
                if self._hero_side:
                    self._hero_right.pack_configure(side="right", fill="y",
                                                    expand=1)
                    self._hero_left_col.pack_configure(expand=1)
                    self._hero_side = "slim"
                want = max(T.sp(268), w - GAP - T.sp(440))
                if abs(want - self._hero_right.winfo_width()) > 6:
                    self._hero_right.configure(width=want)
                self._hero_right.pack_propagate(False)
                # 2026-11-19：右栏压到 308px 后，「不确定方向」和
                # 「浏览全部大类 →」横排放不下（需要 164+193），按钮文字
                # 被切。窄栏里改成上下两行，各自占满一行。
                try:
                    self._cat_btn.pack_configure(side="top", fill="x",
                                                 pady=(T.sp(4), 0))
                    self._cat_hint.pack_configure(side="top", fill="x")
                except Exception:
                    pass
            else:
                if self._hero_side != "full":
                    self._hero_right.pack_configure(side="right", fill="y",
                                                    expand=0)
                    self._hero_left_col.pack_configure(expand=1)
                    self._hero_side = "full"
                if abs(right - self._hero_right.winfo_width()) > 6:
                    self._hero_right.configure(width=right)
                try:
                    self._cat_hint.pack_configure(side="left", fill="none")
                    self._cat_btn.pack_configure(side="right", fill="none",
                                                 pady=0)
                except Exception:
                    pass
            if compact:
                if self._hero_strip.winfo_manager():
                    self._hero_strip.pack_forget()
                if self._welcome_steps.winfo_manager():
                    self._welcome_steps.pack_forget()
                if not self._hero_catblock.winfo_manager():
                    self._hero_catblock.pack(fill="x", after=self._hero_ex)
                if not self._hero_graph.winfo_manager():
                    self._hero_graph.pack(fill="x", pady=(T.sp(6), T.sp(8)),
                                          after=self._hero_lead)
            else:
                if not self._hero_strip.winfo_manager():
                    self._hero_strip.pack(fill="x", before=self._hero_qrow)
                if not self._hero_catblock.winfo_manager():
                    self._hero_catblock.pack(fill="x", after=self._hero_ex)
                if not self._hero_graph.winfo_manager():
                    self._hero_graph.pack(fill="x", pady=(T.sp(6), T.sp(8)),
                                          after=self._hero_lead)
                if not self._welcome_steps.winfo_manager():
                    self._welcome_steps.pack(fill="x", pady=(T.sp(10), 0))
            # 宽度换了以后示例 chip 的折行要重算（place 不参与请求宽度，
            # 容器的 Configure 可能早于 rp 真正变宽）
            try:
                self._hero_ex._flush(force=True)
            except Exception:
                pass
        except Exception as exc:
            print("英雄区自适应失败:", exc)

    def _layout_stats(self, width=None):
        """规模数字：够宽就一排四格，不够就折成两排两格。

        2026-11-19：四格各要 98px（「研究方向」在 T_CAPTION 下 86px + padx），
        加三处 7px 间距共 413px。1080×680 时这一栏只有 382px，
        四个中文标签全被切掉半个字（扫描器「需要86 只有74」×4）。
        这里按真实可用宽度决定排法：每格至少 78px 才敢横排。
        """
        try:
            w = int(width or self._stat_box.winfo_width())
            if w <= 1:
                return
            # 判据用「单格需求」，不用容器的 reqwidth：容器一旦切成两列，
            # reqwidth 就跟着变小，再也判不回四列（曾把窗口拉宽也不复原）。
            if not self._stat_cell_need:
                self._stat_cell_need = max(
                    t.winfo_reqwidth() for t in self._stat_tiles) or 98
            need4 = self._stat_cell_need * 4 + 3 * T.sp(6)
            cols = 4 if w >= need4 - 2 else 2
            if getattr(self, "_stat_cols", None) == cols:
                return
            self._stat_cols = cols
            for i, tile in enumerate(self._stat_tiles):
                r, c = (0, i) if cols == 4 else (i // 2, i % 2)
                tile.grid_configure(row=r, column=c,
                                    padx=(0 if c == 0 else T.sp(6),
                                          T.sp(6) if cols == 2 and c == 0 else 0),
                                    pady=(0 if r == 0 else T.sp(6), 0))
        except Exception:
            pass

    def _load_hero_data(self):
        """英雄卡的规模数字与方向大类：后台数，回主线程填。

        方向库要合并三个 JSON，素材库还要读 552 条目录；放在首帧里
        会让空态白屏半秒，而它们只是「这个入口有多少东西」的背景信息。
        """
        def work():
            lib = {}
            try:
                lib = kb.load_direction_library() or {}
            except Exception:
                lib = {}
            total = sum(len(v.get("subs") or []) for v in lib.values())
            cats = sorted(((k, len(v.get("subs") or [])) for k, v in lib.items()),
                          key=lambda x: -x[1])[:4]
            mats = 0
            try:
                from page_materials import load_materials
                mats = len((load_materials() or {}).get("datasets") or [])
            except Exception:
                pass
            pdfs = 0
            try:
                inv = kb._inventory()
                files = inv.get("files", []) if isinstance(inv, dict) else (inv or [])
                for f in files:
                    if isinstance(f, (tuple, list)) and len(f) >= 3:
                        p = str(f[2])
                    elif isinstance(f, dict):
                        p = str(f.get("path", ""))
                    else:
                        continue
                    if p.lower().endswith(".pdf"):
                        pdfs += 1
            except Exception:
                pass

            def apply():
                try:
                    if total:
                        self._hero_stats[0].config(text="{:,}".format(total))
                    if mats:
                        self._hero_stats[1].config(text="{:,}".format(mats))
                    if pdfs:
                        self._hero_stats[2].config(text="{:,}".format(pdfs))
                    if lib:
                        self._hero_stats[3].config(text="{:,}".format(len(lib)))
                    if not cats:
                        return
                    for w in self._cat_holder.winfo_children():
                        w.destroy()
                    row = U.WrapRow(self._cat_holder, gap=T.sp(5),
                                    rowgap=T.sp(4), bg=T.CARD_HI)
                    row.pack(fill="x")
                    for name, n in cats:
                        row.add(UK.Chip(
                            row, name, count=str(n), bg=T.CARD_HI,
                            command=lambda t=name: self._fill_direction(t)))
                except Exception:
                    pass
            self.app.post(apply)
        threading.Thread(target=work, daemon=True).start()

    def _fill_direction(self, name):
        """点大类只把名字填进输入框，不直接开跑 —— 大类太粗，先让人补一个具体方向。"""
        try:
            self.entry.delete(0, "end")
            self.entry.insert(0, name)
            self.entry.focus_set()
        except Exception:
            pass

    def reset_direction(self):
        """从结果回到空态：清掉候选，把输入框和英雄卡还回来。"""
        self.cands = []
        self.sel = None
        self.ctx = {}
        try:
            self.profile_lbl.config(text="输入方向后回车，或从下方示例开始。",
                                    fg=T.TXT3)
            if self.tweak.winfo_manager():
                self.tweak.pack_forget()
            if self.fuse_bar.winfo_manager():
                self.fuse_bar.pack_forget()
            self._fuse_open = False
            if self._expanded:
                self._expanded = False
                self._under.pack_forget()
        except Exception:
            pass
        self._set_cards_visible(False)
        try:
            self.entry.focus_set()
            self.entry.select_range(0, "end")
        except Exception:
            pass

    def _sync_under(self):
        """决定「理解详情」按钮出不出现、展开区要不要收起。

        展开区里可能同时有「硬条件说明」和「新颖性汇总」两块，任何一块有内容
        才给按钮；两块都空就把按钮和展开区一起收掉 —— 空按钮比没有按钮更扰人。
        """
        try:
            has_sub = bool(self.profile_sub.winfo_children())
            has_nov = bool((self._nov_text or "").strip())
            if has_sub or has_nov:
                if not self._under_btn.winfo_manager():
                    self._under_btn.pack(side="right", padx=(8, 0))
            else:
                if self._under_btn.winfo_manager():
                    self._under_btn.pack_forget()
                if self._expanded:
                    self._expanded = False
                    self._under.pack_forget()
                return
            if self._expanded:
                self._under_btn.config(text="收起")
                if not self._under.winfo_manager():
                    # 锚点必须是**已经 pack 过**的控件，否则 Tk 报
                    # `window ... isn't packed` 并整段放弃（展开区就不见了）。
                    anchor = None
                    for w in (self._body, self._welcome, self.examples):
                        if w.winfo_manager():
                            anchor = w
                            break
                    if anchor is not None:
                        self._under.pack(fill="x", padx=T.PAD + 8, pady=(2, 4),
                                         before=anchor)
                    else:
                        self._under.pack(fill="x", padx=T.PAD + 8, pady=(2, 4))
                self._resync()
            else:
                self._under_btn.config(text="理解详情")
        except Exception as exc:
            print("[topic] 理解详情区同步失败：%r" % (exc,))

    def _toggle_under(self):
        self._expanded = not getattr(self, "_expanded", False)
        self._sync_under()

    def _resync(self):
        """折叠区开合后让外层卡片与页面重新量一次高度。

        Card 不会因为 pack 里多了一个 Frame 就自动长高（它的高度靠 body 的
        Configure 事件驱动），区块一动就得显式通知，否则展开的内容被裁掉。
        """
        for w in (self._under, self._under_wrap):
            try:
                T.resync(w)
            except Exception:
                pass

    def _set_cards_visible(self, on):
        """空态只显示引导卡；有候选时铺开三栏。

        踩过的坑（两次都表现为「候选生成了但界面还是空的」）：
        ① 三栏用 grid，不能 pack_forget，要 grid_remove()/grid() 才记住位置；
        ② 光 grid() 卡片不够 —— `body` 这个容器自己在空态时被 pack_forget 了，
           卡片即便 grid() 回来，父容器没显示，winfo_ismapped() 仍是 0。
           必须先 pack body，再 grid 卡片。
        """
        try:
            if on:
                self._welcome.pack_forget()
                # 顶栏讲「系统怎么理解这句输入」，它和三栏是一组，空态不露面。
                if not self._result_bar.winfo_manager():
                    self._result_bar.pack(fill="x", padx=T.PAD, pady=(T.sp(6), T.sp(6)))
                if not self._under_wrap.winfo_manager():
                    self._under_wrap.pack(fill="x", padx=T.PAD + 8, pady=(0, T.sp(2)),
                                          after=self._result_bar)
                # 「换个角度」一行要在结果态、且排在三栏之前
                if (getattr(self, "_tweak_ready", False)
                        and not self.tweak.winfo_manager()):
                    self.tweak.pack(fill="x", padx=T.PAD, pady=(0, 4),
                                    before=self._under_wrap)
                # 顺序很重要：父容器先回来，子控件才有地方显示
                if not self._body.winfo_ismapped():
                    self._body.pack(fill="both", expand=True, padx=T.PAD,
                                    pady=(0, 14))
                for c in self._cards:
                    c.grid()
                self._body.grid_rowconfigure(0, weight=1)
            else:
                for c in self._cards:
                    c.grid_remove()
                self._body.grid_rowconfigure(0, weight=0)
                # 空态时整个三栏容器收起（不是让它空着撑满一屏）
                self._body.pack_forget()
                if self._result_bar.winfo_manager():
                    self._result_bar.pack_forget()
                if self._under_wrap.winfo_manager():
                    self._under_wrap.pack_forget()
                if not self._welcome.winfo_ismapped():
                    self._welcome.pack(fill="both", expand=True, padx=T.PAD,
                                       pady=(T.sp(6), T.sp(14)))
            # 让布局当下结算一次，否则紧随其后的测量拿到的是旧几何
            self._body.update_idletasks()
        except Exception as exc:
            print("三栏显隐失败:", exc)
        # 键盘上下键换候选：生成 18 条时用鼠标在左栏里点选很烦，
        # 而「看下一条」是这个页面做得最多的一件事。
        for w in (self.cand_scroll.canvas, self, self.entry):
            w.bind("<Down>", lambda e: self._step(1), add="+")
            w.bind("<Up>", lambda e: self._step(-1), add="+")

    def _step(self, d):
        """在当前候选前后移动一格；到边界就不动（不循环，循环会让人迷路）。"""
        if not self.cands:
            return "break"
        i = 0 if self.sel is None else self.sel + d
        i = max(0, min(len(self.cands) - 1, int(i)))
        self.select(i)
        try:
            # 让选中的那条滚进可视区：18 条里第 12 条在下面时，只换详情不动列表，
            # 用户会觉得「怎么没反应」
            frac = float(i) / max(1, len(self.cands))
            self.cand_scroll.canvas.yview_moveto(max(0.0, frac - 0.15))
        except Exception:
            pass
        return "break"

    def _hint(self, parent, text):
        # 空态不需要换行符——让 Label 自己按父容器宽度折行，
        # 免得左栏窄的时候「还没有候选。↵在上方输入…」挤成两行贴在一起。
        # 空态是「还没开始时唯一看得见的东西」，用 TXT4 会淡到像禁用态，
        # 用户会以为这块坏了。用 TXT3，并给足内边距让它不像裸文字。
        lbl = tk.Label(parent, text=text.replace("\n", " "), bg=parent.cget("bg"),
                       fg=T.TXT3, font=T.T_BODY_SM(), justify="left", anchor="w")
        lbl.pack(fill="x", pady=14, padx=10)
        # 折行跟随容器；收窄时重新算，否则文字会被裁掉
        def _fit(ev, w=lbl):
            try:
                w.config(wraplength=max(120, ev.width - 16))
            except Exception:
                pass
        parent.bind("<Configure>", lambda ev, w=lbl: _fit(ev, w), add="+")

    def _on_mid_resize(self, e):
        w = max(220, e.width - 30)
        if abs(w - self._mid_wrap) < 8:
            return
        self._mid_wrap = w
        self.detail_head.config(wraplength=w)
        self.detail_meta.config(wraplength=w)
        try:
            self._save_note.config(wraplength=w)
        except Exception:
            pass
        self._wrap_bullets(self.detail_box, w)

    def use_example(self, t):
        self.entry.delete(0, "end")
        self.entry.insert(0, t)
        self.generate()

    # ------------------------------------------------------------ 跨领域
    def _toggle_fuse(self):
        """展开/收起 B、C 输入栏。折叠时不留空白，避免把候选区往下挤。"""
        if self._fuse_open:
            self.fuse_bar.pack_forget()
            self.fuse_btn.config(text="＋ 跨领域组合")
        else:
            self.fuse_bar.pack(fill="x", padx=T.PAD, pady=(0, 4),
                               before=self.profile_lbl)
            self.fuse_btn.config(text="－ 收起跨领域组合")
        self._fuse_open = not self._fuse_open

    def _peek_b(self):
        """B 里填的东西如果根本不是方向（是方法名），提示它更适合放 B。

        这一条很关键：把「扩散模型」填进 A 会得到「扩散模型的跨域泛化方案」
        这种空题，但用户不会意识到自己填错了格子。
        """
        txt = self.entry_b.get().strip()
        if len(txt) < 2:
            return
        try:
            info = topic_fusion.check_direction(txt)
        except Exception:
            return
        if not info.get("ok"):
            self.app.toast("「%s」更像通用方法，放 B 正合适" % txt[:12], T.TXT4)

    def _peek_c(self):
        txt = self.entry_c.get().strip()
        if len(txt) < 2:
            return
        try:
            info = topic_fusion.check_direction(txt)
        except Exception:
            return
        if not info.get("ok"):
            self.app.toast("「%s」没识别成计算机领域，仍会生成但要自己把关" % txt[:12], T.WARN)

    def _fusion_args(self):
        # 「换个角度」那一行首屏没建，entry_b/entry_c 在用户真去点之前是 None。
        if self.entry_b is None or self.entry_c is None:
            return ("", "")
        return (self.entry_b.get().strip(), self.entry_c.get().strip())

    # ------------------------------------------------------------ 生成
    def generate(self):
        direction = self.entry.get().strip()
        if not direction:
            self.app.toast("请先输入研究方向", T.WARN)
            return
        self.go_btn.config(text="生成中…")
        mode = self.mode.get()
        eb, ec = self._fusion_args()
        kind_filter = _KIND_ALIAS.get(self.fuse_kind.get(), "")

        def work():
            try:
                cat, field, conf = kb.infer_category_field(direction)
                rels = kb.load_research_relations()
                profile_key = kb.field_profile(cat, field, rels) if (cat and field) else ""
                profile = (rels.get("profiles", {}) or {}).get(profile_key, {})
                # 用新的候选生成器：每个候选带针对性理由、验证问题与最小实验。
                # 旧版 kb.expand_direction_candidates 的 18 个候选共用同一句理由。
                # 画像只影响排序，不影响候选的有无；没建画像时 tilt_inputs() 返回 None。
                try:
                    tilt = PM.tilt_inputs()
                except Exception:
                    tilt = None
                note = ""
                cands = []
                if eb or ec:
                    # 跨领域模式：A×B×C 拼出来的候选，和单方向候选是两套逻辑，
                    # 不混着排 —— 混排会让「用扩散模型做红外检测」和「红外检测的
                    # 轻量化」抢同一个位置，而它们的可执行性根本不可比。
                    cands = topic_fusion.build(direction, eb, ec, limit=18)
                    if cands and cands[0].get("error"):
                        note = cands[0]["error"]
                        cands = []
                if not cands:
                    if eb or ec:
                        note = note or "交叉组合没有找到可验证的连接点，改用单方向候选"
                    cands = topic_gen.build(direction, mode, 18, profile=tilt)
                if not cands:
                    cands = kb.expand_direction_candidates(direction, mode, 18)
                if kind_filter:
                    only = [c for c in cands if c.get("kind") == kind_filter]
                    if only:
                        cands = only
                    else:
                        note = (note + "；" if note else "") + \
                               "该组合类型下没有可用的角度，已显示全部类型"
                # 补上方向归类的信息，供右侧 venue/导师检索使用
                for c in cands:
                    c.setdefault("category", cat)
                    c.setdefault("field", field)
                    c.setdefault("profile", profile_key)
                if tilt and any(c.get("combo") for c in cands):
                    # 画像排序对交叉候选同样生效（只重排，不删）
                    try:
                        topic_gen.apply_profile(cands, tilt)
                        cands.sort(key=lambda x: -x.get("score", 0))
                    except Exception:
                        pass
                # 硬约束放在最后一步：它要把「做不动」的候选沉底，
                # 而 apply_profile 的软加权不该再把它们顶回来
                cfit_note = ""
                try:
                    cons = PM.constraints()
                    if any(cons.values()):
                        topic_constraint.annotate(cands, cons)
                        cfit_note = topic_constraint.summary(cands)
                except Exception as exc:
                    print("约束检查失败:", exc)
                # 新颖性核查放最后、且**先出界面**：
                # 一次全库核查 8 条要二十多秒，卡在生成里用户会以为卡死。
                # 所以先生成（1 秒内），把候选推上界面，再在同一个后台线程里
                # 逐条核查，每核完一条就回主线程刷一次 —— 用户能看到进度。
                self.app.post(lambda n=note, cf=cfit_note: self._apply(
                    direction, cat, field, conf, profile_key, profile, cands, n, cf))
                # 2026-11-15：新颖性核查改为「按视口惰性核」。
                # 原来生成时一口气核前 8 条，每条要跑一次向量检索 +
                # 一次全库 AND 检索（1–3 秒），生成完还要等 20 多秒，
                # 而用户经常只看排第一的那条。现在不在这里核，
                # 改成 select() 里对「当前正在看的那条」单独核。
                # 代价：候选列表上不再一开始就有新颖性徽章——
                # 但那个徽章本来就只覆盖前 8 条，容易让人误以为都核过了。
            except Exception as exc:
                self.app.post(lambda e=exc: self._fail(e))
        threading.Thread(target=work, daemon=True).start()

    def _fail(self, exc):
        self.go_btn.config(text="生成候选")
        self.app.toast("生成失败：" + str(exc), T.ERR)

    def _apply(self, direction, cat, field, conf, profile_key, profile, cands,
               note="", cfit_note=""):
        self.go_btn.config(text="生成候选")
        # 第一次生成完成后才把「换个角度」一行铺出来 —— 首屏不摆用不上的控件
        try:
            self._build_tweak()
        except Exception as exc:
            print("换个角度一行没建起来:", exc)
        eb_c = self._fusion_args()
        self.ctx = dict(direction=direction, cat=cat, field=field, conf=conf,
                        profile_key=profile_key, profile=profile, note=note,
                        b=eb_c[0], c=eb_c[1])
        self.cands = cands or []
        # 结果顶栏：把「输入 → 理解结果」摆在一行，用户随时能确认系统没跑偏
        try:
            self.result_title.config(text=direction)
            if cat and field:
                self.result_meta.config(
                    text="→ 大类 %s · 领域 %s · 置信度 %d%%" % (cat, field, conf))
            else:
                self.result_meta.config(text="→ 未稳定识别学科目录，候选按全库兜底")
        except Exception:
            pass
        self._set_cards_visible(bool(self.cands))
        fused = [c for c in self.cands if c.get("combo")]
        if cat and field:
            extra = []
            if profile.get("label"):
                extra.append("画像 " + profile["label"])
            if fused:
                cmb = fused[0]["combo"]
                parts = [cmb.get("a")]
                if cmb.get("b"):
                    parts.append("方法 " + cmb["b"])
                if cmb.get("c"):
                    parts.append("邻域 " + cmb["c"])
                extra.append("交叉：" + " × ".join(parts))
            extra.append("本地预筛 %d 条候选" % len(self.cands))
            self.profile_lbl.config(text=" · ".join(extra), fg=T.TXT3)
        else:
            self.profile_lbl.config(
                text="未稳定识别学科目录；仍会生成通用候选，建议到「方向图谱」手动校正。",
                fg=T.WARN)
        # 画像条曾经把「大类/领域/交叉/硬条件」全拼成一行，窗口一窄尾巴就被
        # 裁掉（截图里「6 条要挑做法（已沉到…」直接断在可视区外）。
        # 拆成两行：第一行说明「这条查询被理解成什么」，第二行才是结论。
        detail = []
        if cfit_note:
            detail.append(("硬条件：" + cfit_note, T.WARN))
        if note:
            detail.append((note, T.WARN))
        # 「候选已就绪。分数是本地预估，不是结论。」这句不再显示：
        # 卡片头已经写了「分数是本地预筛，不是结论」，再说一遍纯占行。
        # 只有真的存在硬条件冲突 / 回退说明时才填 profile_sub。
        for _w in self.profile_sub.winfo_children():
            _w.destroy()
        for _i, (line, color) in enumerate(detail):
            if _i:
                tk.Frame(self.profile_sub, bg=T.BG, height=1).pack(fill="x")
            lb = tk.Label(self.profile_sub, text=line, bg=T.BG, fg=color,
                          font=T.T_BODY_SM(), anchor="w", justify="left")
            lb.pack(fill="x")
            T.fill_wrap(lb, pad=8)
        self._sync_under()
        self._render_cands()
        if self.cands:
            self.select(0)

    def _apply_novelty(self):
        """后台核完一条候选后回主线程刷新候选卡（列表 + 详情）。

        不整页重绘：`_render_cands()` 会丢掉滚动位置和当前选中项。
        只重画候选列表，选中项和详情保持不动，除非用户正看着刚核完的那条。
        """
        try:
            self._render_cands()
        except Exception as exc:
            print("新颖性刷新失败:", exc)

    def _set_novelty_note(self, text):
        """顶栏结论：几条撞车、几条挤、几条没查到。

        `before=` 要指向**已经 pack 过**的控件，否则 TclError。
        profile_sub 只在有额外结论时才 pack，所以这里按实际 pack 状态
        选锚点：优先插在 profile_sub 前，它没出来就插在 examples 前。
        """
        try:
            self._nov_text = text or ""
            self.nov_lbl.config(text=self._nov_text)
            if self.nov_lbl.winfo_manager():
                return                                   # 已在展开区里，改文字即可
            self.nov_lbl.pack(fill="x", pady=(2, 0))
            T.fill_wrap(self.nov_lbl, pad=8)
            self._sync_under()
        except Exception as exc:
            print("新颖性汇总行显示失败:", exc)

    def _render_cands(self):
        self.cand_scroll.clear()
        try:
            self.cand_count.config(text=("%d 条" % len(self.cands)) if self.cands else "")
        except Exception:
            pass
        if not self.cands:
            self._hint(self.cand_scroll.inner, "没有生成候选。换一个更常见的领域描述试试。")
            self._show_actions(False)
            self.cand_scroll.refresh()
            return
        for i, c in enumerate(self.cands):
            self._cand_row(c, i)
        self.cand_scroll.refresh()

    def _cand_row(self, c, i):
        active = (self.sel == i)
        bg = T.ACCENT_D if active else T.CARD_HI
        f = tk.Frame(self.cand_scroll.inner, bg=bg, cursor="hand2")
        f.pack(fill="x", pady=2)
        head = tk.Frame(f, bg=bg)
        head.pack(fill="x", padx=8, pady=(6, 0))
        # 序号 + 两种标记放同一行左侧，策略名放最右。
        # 早期版本标记 pack 在 side="right" 的策略名之后，被它挤出了可视区 ——
        # 现象是「候选明明标了要挑做法，卡片上却什么都没有」。
        tk.Label(head, text=str(i + 1).zfill(2), bg=bg, fg=T.TXT4,
                 font=T.M(8)).pack(side="left", padx=(0, 6))
        fit = c.get("cfit") or {}
        if fit.get("level") == "block":
            tk.Label(head, text="做不动", bg=bg, fg=T.ERR,
                     font=T.F(8)).pack(side="left", padx=(0, 6))
        elif fit.get("level") == "warn":
            tk.Label(head, text="要挑做法", bg=bg, fg=T.WARN,
                     font=T.F(8)).pack(side="left", padx=(0, 6))
        # 交叉候选要标出「这条是怎么拼的」，否则读者只看到标题里两个名词并排，
        # 分不清哪个是手段、哪个是问题。
        if c.get("kind"):
            tk.Label(head, text=c["kind"], bg=bg, fg=T.OK,
                     font=T.F(8)).pack(side="left", padx=(0, 6))
        # 新颖性徽章也放左侧：核过的才显示，没核完的不占位
        nv = c.get("nov") or {}
        if nv.get("level") in ("high", "mid"):
            col = T.ERR if nv["level"] == "high" else T.WARN
            tk.Label(head, text="撞车风险高" if nv["level"] == "high" else "邻域较挤",
                     bg=bg, fg=col, font=T.F(8)).pack(side="left", padx=(0, 6))
        tk.Label(head, text=c.get("strategy", ""), bg=bg,
                 fg=T.PURPLE if "跨领域" in c.get("strategy", "") else T.ACCENT,
                 font=T.F(8)).pack(side="right")
        title = c.get("title", "")
        # 标题宽度跟随容器，字号放大后固定 300 会把文字挤成一团。
        # 扣掉卡片左右 padx(8+8) 与圆角留白，避免末字贴边。
        try:
            avail = max(150, self.cand_scroll.canvas.winfo_width() - 34)
        except Exception:
            avail = 280
        lb = tk.Label(f, text=title, bg=bg, fg=T.TXT if active else T.TXT2, font=T.F(9),
                      anchor="w", wraplength=avail, justify="left")
        lb.pack(fill="x", padx=8, pady=(3, 3))
        _cfm(lb)
        # 一行小字：三个预筛分 + 画像调整理由（如果有）。
        scores = "相关 %s · 新颖 %s · 可行 %s" % (
            c.get("relevance", "—"), c.get("novelty", "—"), c.get("feasibility", "—"))
        tilt_txt = ""
        if c.get("tilt_reason"):
            # 用「↑」代替「排序：」前缀：窄栏里逗号会被挤到下一行开头
            # （「排序：你时间还宽松↵，这条…」），换成中点分隔后可以在
            # 空格处断行，前导标点就不会单独占一行。
            reason = str(c["tilt_reason"]).replace("，", " · ").replace(",", " · ")
            tilt_txt = "\n↑ " + reason
        meta = (scores + tilt_txt).strip()
        tk.Label(f, text=meta, bg=bg, fg=T.TXT3, font=T.T_CAPTION(),
                 anchor="w", wraplength=avail, justify="left").pack(
            fill="x", padx=8, pady=(0, 6))
        for w in (f, head, lb):
            w.bind("<Button-1>", lambda e, idx=i: self.select(idx))

    def _lazy_novelty(self, idx):
        """选中某条候选时，在后台核它的新颖性；核完只刷这一条。

        用 idx 而不是对象引用来回主线程：候选列表可能在核查期间被替换。
        再核一次前先看 `nov` 是否已经有结论，避免用户来回点重复跑检索。
        """
        try:
            cands = self.cands or []
            if idx < 0 or idx >= len(cands):
                return
            c = cands[idx]
            if not isinstance(c, dict) or c.get("error"):
                return
            nv = c.get("nov")
            if isinstance(nv, dict) and nv.get("level"):
                return
            if c.get("_nov_busy"):
                return
            c["_nov_busy"] = True
            direction = (self.ctx or {}).get("direction") or ""
        except Exception:
            return

        def work():
            try:
                novelty_check.annotate_one(c, direction=direction)
            except Exception as exc:
                print("新颖性核查失败:", exc)
            self.app.post(lambda: self._novelty_done(idx))
        threading.Thread(target=work, daemon=True).start()

    def _novelty_done(self, idx):
        """一条核完后：更新顶栏结论，并且只有用户还在看这条时才重画详情。"""
        cands = self.cands or []
        if idx < 0 or idx >= len(cands):
            return
        c = cands[idx]
        if isinstance(c, dict):
            c.pop("_nov_busy", None)
        try:
            note = novelty_check.summary(cands)
            if note:
                self._set_novelty_note(note)
        except Exception:
            pass
        # 只有当前选中的正是核完的这条，才需要重画详情；
        # 否则会打扰用户正在读的另一条。
        try:
            if getattr(self, "sel", None) == idx:
                self._render_cands()
                self.select(idx, recheck=False)
        except Exception as exc:
            print("新颖性刷新失败:", exc)

    def _render_novelty(self, c):
        """详情面板里的「有没有人做过」区块。

        三级信息量，按用户实际关心顺序：
          ① 一句话结论（撞车风险高 / 邻域较挤 / 没查到近邻）
          ② 依据：命中了多少篇、最像的那篇叫什么、近两年多少篇
          ③ 证据：最近邻列表（前 3 条，带 arXiv 链接，能当场点开看）
        最后一行永远写上索引范围 —— 不然「没查到近邻」会被读成
        「这是空白」，那是这个功能最危险的误读。
        """
        bg = T.CARD
        nv = c.get("nov")
        if nv is None:
            tk.Label(self.detail_box, text="新颖性核查", bg=bg, fg=T.TXT4,
                     font=T.F(9, True), anchor="w").pack(fill="x", pady=(8, 2))
            if c.get("_nov_busy"):
                self._bullet(self.detail_box,
                             "正在核这条（首次核查要把论文正文读进内存，约 7 秒；"
                             "之后再核别的候选只要 1 秒）",
                             color=T.TXT4)
            else:
                self._bullet(self.detail_box,
                             "这条没有核查（选中它时会自动核）", color=T.TXT4)
            return
        if not nv.get("available", True):
            tk.Label(self.detail_box, text="新颖性核查", bg=bg, fg=T.TXT4,
                     font=T.F(9, True), anchor="w").pack(fill="x", pady=(8, 2))
            self._bullet(self.detail_box, nv.get("reason") or "索引不可用",
                         color=T.TXT4)
            return
        label, color_name = novelty_check.LEVEL_LABEL.get(
            nv.get("level"), ("未判定", "TXT4"))
        col = getattr(T, color_name, T.TXT3)
        head = tk.Frame(self.detail_box, bg=bg)
        head.pack(fill="x", pady=(10, 3))
        tk.Label(head, text="新颖性核查", bg=bg, fg=T.TXT2,
                 font=T.T_LABEL()).pack(side="left")
        # 判档用同字号但只上颜色，不再加粗 —— 一行里两个粗体在抢注意力
        tk.Label(head, text=label, bg=bg, fg=col,
                 font=T.T_BODY_SM()).pack(side="left", padx=(8, 0))
        self._bullet(self.detail_box, nv.get("reason", ""), color=col)
        # 证据列表：点得开才是证据，只给数字等于让人信我
        for p in (nv.get("near") or [])[:3]:
            row = tk.Frame(self.detail_box, bg=bg)
            row.pack(fill="x", pady=(1, 0))
            tk.Label(row, text="　%.2f" % (p.get("score") or 0), bg=bg,
                     fg=T.TXT4, font=T.F(8)).pack(side="left")
            tk.Label(row, text=(p.get("date") or "")[:7], bg=bg, fg=T.TXT4,
                     font=T.M(8)).pack(side="left", padx=(4, 6))
            link = tk.Label(row, text=(p.get("title") or "")[:60], bg=bg,
                            fg=T.ACCENT, font=T.F(8), anchor="w",
                            cursor="hand2", justify="left",
                            wraplength=max(160, self._mid_wrap - 80))
            link.pack(side="left", fill="x", expand=True)
            url = p.get("url")
            if url:
                link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        self._bullet(self.detail_box,
                     "核查范围：arXiv cs 近三年 53.8 万篇。"
                     "没查到不等于没人做过 —— 会议正刊、期刊、工业界的工作不在里面。",
                     color=T.TXT4)

    def _grp(self, title):
        """换组时打一个弱色组标题；同组内的小节自己用 T.T_LABEL 小标题。"""
        if title == getattr(self, "_grp_txt", ""):
            return
        self._grp_txt = title
        tk.Label(self.detail_box, text=title, bg=T.CARD, fg=T.TXT3,
                 font=T.T_CAPTION(), anchor="w").pack(fill="x", pady=(12, 2))

    def _more_menu(self):
        """「更多 ▾」弹出次要动作。

        不把这些按钮常驻：四个平级按钮会让人以为要逐个点过去，
        而这四件的先后关系其实是「先认下 → 再交出去」。
        """
        self._popup(self.btn_more, [
            ("让 AI 挑刺这批候选", self.ai_critique),
            ("复制这一条的清单", self.copy_pack),
        ])

    def _popup(self, anchor, items):
        """在按钮下方弹一个小菜单（tk.Menu 原生弹出，比自绘轻）。"""
        try:
            m = tk.Menu(self, tearoff=0, bg=T.CARD, fg=T.TXT,
                        activebackground=T.ACCENT_D, activeforeground=T.ACCENT,
                        bd=0, relief="flat", font=T.T_BODY_SM())
            for label, cmd in items:
                m.add_command(label=label, command=cmd)
            m.tk_popup(anchor.winfo_rootx(),
                       anchor.winfo_rooty() + anchor.winfo_height() + 2)
        except Exception as exc:
            print("弹出菜单失败:", exc)

    def _show_actions(self, on):
        """动作条只在选中候选后出现。

        空态摆一排「存为创新点 / AI 挑刺 / 生成交接提示词」，点了只会弹
        「先选一个候选」，纯属噪音。
        """
        if on and not self._act.winfo_ismapped():
            # 先占底部、再让滚动区吃剩余高度：pack 按顺序分配请求尺寸，
            # 滚动区若先拿到 120px 下限，动作条在矮窗里就会被挤到卡片外裁掉
            # （1240×800 + 大字号实测只剩半行按钮）。
            self._act.pack(side="bottom", fill="x", pady=(8, 0),
                           before=self.detail_scroll)
        elif not on and self._act.winfo_ismapped():
            self._act.pack_forget()

    def select(self, i, recheck=True):
        self.sel = i
        self.sel_idx = i
        self._show_actions(True)
        # 换一条就把上一条的存入回执收掉，否则会误以为是这一条刚存的
        try:
            self.btn_save.config(text="存为创新点")
            self._save_note.config(text="")
            if self._save_note.winfo_manager():
                self._save_note.pack_forget()
        except Exception:
            pass
        self._render_cands()
        c = self.cands[i]
        if recheck:
            # 随手选中就核：这条没核过的话，1–3 秒后详情里会自己长出结论
            self._lazy_novelty(i)
        # 详情面板的抬头改成「第几条 / 共几条」，让人知道自己看到哪儿了 ——
        # 原来只有一个孤立标题，切候选时没有位置感。
        c2 = c.get("title", "") or "（无标题）"
        try:
            self.detail_idx.config(text="%02d / %02d" % (i + 1, len(self.cands)))
        except Exception:
            pass
        self.detail_head.config(text=c2)
        # 画像把它往前挪过就在标题下面说清楚，否则用户看不出为什么它排第一
        if c.get("kind"):
            # 第一行放「怎么拼的」，第二行才是策略/角度 —— 交叉候选的信息量
            # 主要在组合本身，不能埋到第二行
            head = "%s  ·  %s  ·  策略 %s  ·  切入角度 %s" % (
                c["kind"],
                " × ".join(x for x in (c.get("combo", {}).get("a"),
                                       c.get("combo", {}).get("b"),
                                       c.get("combo", {}).get("c")) if x),
                c.get("strategy", ""), c.get("angle", ""))
            if c.get("tilt_reason"):
                head += "\n排序依据：%s（本地分 %s → %s）" % (
                    c["tilt_reason"], c.get("base_score", "—"), c.get("score", "—"))
            self.detail_meta.config(text=head)
        elif c.get("tilt_reason"):
            # 一行放不下：策略单独一行，排序依据换行，否则中间栏宽度不够会被截断
            head = ("策略 %s  ·  切入角度 %s" % (c.get("strategy", ""), c.get("angle"))
                    if c.get("angle") else "策略 %s" % c.get("strategy", ""))
            self.detail_meta.config(
                text="%s\n排序依据：%s（本地分 %s → %s）" % (
                    head, c["tilt_reason"],
                    c.get("base_score", "—"), c.get("score", "—")))
        elif c.get("angle"):
            self.detail_meta.config(
                text="策略 %s  ·  切入角度 %s" % (c.get("strategy", ""), c.get("angle")))
        else:
            self.detail_meta.config(
                text="策略 %s" % c.get("strategy", ""))
        for w in self.detail_box.winfo_children():
            w.destroy()
        self._bullets = []
        self._ai_box = None
        bg = T.CARD
        # 三级分节（第 16 版）：结论 → 证据 → 接下来。
        # 第 15 版把六个小节统一成同一样式的粗体标题，视觉上平了，
        # 但读者仍看不出哪些是「这条能不能做」的判断、哪些是支撑材料。
        # 现在只在换组时打一个弱色组标题，组内小节用普通正文色。
        self._grp_txt = ""
        self._grp("结论：这条能不能做")
        # 为什么这个角度值得做 —— 每个候选有自己的论证，不是通用套话
        fit = c.get("cfit") or {}
        if fit.get("reasons"):
            col = T.ERR if fit.get("level") == "block" else T.WARN
            tk.Label(self.detail_box, text="和你的条件冲突", bg=bg, fg=col,
                     font=T.T_LABEL(), anchor="w").pack(fill="x", pady=(4, 3))
            for lvl, msg in fit["reasons"]:
                self._bullet(self.detail_box, msg)
            if fit.get("level") == "block":
                self._bullet(self.detail_box,
                             "要么换角度，要么去「个人画像 → 我的硬条件」更新实际情况")
        if c.get("reason"):
            tk.Label(self.detail_box, text="为什么值得做", bg=bg, fg=T.TXT2,
                     font=T.T_LABEL(), anchor="w").pack(fill="x", pady=(10, 3))
            self._bullet(self.detail_box, c["reason"])
        # 新颖性核查：说清「这个方向别人做没做过」。
        # 必须放在「为什么值得做」后面，因为用户先要理解这道题在讲什么，
        # 再问「有没有人做过」；顺序反了会变成先泼冷水。
        self._grp("证据：有没有人做过")
        self._render_novelty(c)
        # 两周内能跑完的最小验证：让建议可以直接执行
        self._grp("接下来：先做哪个实验")
        if c.get("min_experiment"):
            tk.Label(self.detail_box, text="最小验证", bg=bg, fg=T.TXT2,
                     font=T.T_LABEL(), anchor="w").pack(fill="x", pady=(10, 3))
            self._bullet(self.detail_box, c["min_experiment"])
        if c.get("questions"):
            tk.Label(self.detail_box, text="验证问题", bg=bg, fg=T.TXT2,
                     font=T.T_LABEL(), anchor="w").pack(fill="x", pady=(10, 3))
            for q in c["questions"]:
                self._bullet(self.detail_box, q)

        idea = {"title": c.get("title", ""), "desc": c.get("reason", ""),
                "type": kb.infer_innovation_type(c.get("title", ""), c.get("reason", ""))}
        self._grp("体检：选题结构完整吗")
        try:
            res = self._render_review(idea)
            self.ctx["review"] = res
        except Exception as exc:
            self._bullet(self.detail_box, "体检失败：" + str(exc), T.ERR)
        # 底部留白：滚动区最后一行贴着动作条时会被裁成半行
        tk.Frame(self.detail_box, bg=bg, height=T.gap(14)).pack(fill="x")

        self._render_side()

    def ai_critique(self):
        """让大模型以审稿人视角挑这批候选的刺。

        为什么不常驻自动调用：一次要几秒到几十秒，还会花钱。
        学生点一下才跑，跑完把结果留在中间栏，切候选就清掉
        （否则会拿上一批候选的评语去评价新候选，看着像胡说）。
        """
        if not self.cands:
            self.app.toast("先生成候选，再让 AI 挑刺", T.WARN)
            return
        if not L.is_ready():
            self.app.toast("还没配置大模型，去「设置与数据」里填一下", T.WARN)
            try:
                self.app.goto("settings")
            except Exception:
                pass
            return
        d = self.ctx.get("direction", "")
        self._ai_running = True
        self.btn_ai.config(state="disabled", text="审阅中…")
        self._render_ai_pending()

        def work():
            txt = L.critique_ideas(d, self.cands)
            self.app.post(lambda: self._ai_done(txt))
        threading.Thread(target=work, daemon=True).start()

    def _ai_done(self, txt):
        try:
            self.btn_ai.config(state="normal", text="AI 挑刺")
        except Exception:
            pass
        self._ai_running = False
        if not txt:
            self.app.toast("大模型没有返回内容，检查设置里的连接", T.WARN)
            if getattr(self, "_ai_box", None) is not None:
                self._ai_box.destroy()
                self._ai_box = None
            return
        self._render_ai(txt)

    def _render_ai_pending(self):
        if getattr(self, "_ai_box", None) is not None:
            self._ai_box.destroy()
        bg = T.CARD
        box = tk.Frame(self.detail_box, bg=bg)
        box.pack(fill="x", pady=(8, 0))
        tk.Label(box, text="审稿人视角（AI）", bg=bg, fg=T.PURPLE,
                 font=T.F(9, True), anchor="w").pack(fill="x")
        tk.Label(box, text="正在让大模型读这批候选…", bg=bg, fg=T.TXT4,
                 font=T.F(9), anchor="w").pack(fill="x", pady=(2, 0))
        self._ai_box = box
        self.detail_scroll.refresh()

    def _render_ai(self, txt):
        if getattr(self, "_ai_box", None) is not None:
            self._ai_box.destroy()
        bg = T.CARD
        box = tk.Frame(self.detail_box, bg=bg)
        box.pack(fill="x", pady=(8, 0))
        head = tk.Frame(box, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text="审稿人视角（AI）", bg=bg, fg=T.PURPLE,
                 font=T.F(9, True), anchor="w").pack(side="left")
        tk.Label(head, text="大模型生成 · 判断权在你", bg=bg, fg=T.TXT4,
                 font=T.F(8), anchor="e").pack(side="right")
        lb = tk.Label(box, text=txt, bg=bg, fg=T.TXT2, font=T.F(9),
                      anchor="w", justify="left",
                      wraplength=max(200, self._mid_wrap - 20))
        lb.pack(fill="x", pady=(4, 0))
        self._bullets.append(lb)
        self._ai_box = box
        self.detail_scroll.refresh()

    def _clear_ai(self):
        """切候选时清掉上一批的 AI 评语，避免张冠李戴。"""
        b = getattr(self, "_ai_box", None)
        if b is not None:
            try:
                b.destroy()
            except Exception:
                pass
            self._ai_box = None

    def _nowrap(self, s):
        """把会被误读的短语用不换行空格粘起来，防止窄栏断在词中间。

        Tk 的 Label 换行只认空格与中日韩字边界，所以「「3 个月内」」会被断成
        「「3」/「个月内」」—— 引号里的内容被切开，读者会以为填错了值。
        这里把引号内容里的空格换成 U+00A0，Tk 便不会在那里断行。
        """
        import re as _re
        if not s:
            return s
        s = _re.sub(r"「([^」]*)」",
                    lambda m: "「" + m.group(1).replace(" ", "\u00a0") + "」", s)
        # 数字被断行：Tk 在中文段里会把「0.54」断成「0」/「54」（." 附近
        # 是它认出的小数点断点）。截图上写成「最像 0\n54」会被读成两个数。
        # 用 WORD JOINER（U+2060，零宽、不可断）把小数粘起来。
        return _re.sub(r"(\d)\.(\d)", "\\1\u2060.\u2060\\2", s)

    def _bullet(self, parent, text, color=None):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=1)
        tk.Label(row, text="·", bg=row.cget("bg"), fg=T.ACCENT,
                 font=T.F(10)).pack(side="left", padx=(2, 6), anchor="n")
        lb = tk.Label(row, text=self._nowrap(text), bg=row.cget("bg"),
                      fg=color or T.TXT2, font=T.F(9),
                      anchor="w", justify="left",
                      wraplength=max(160, self._mid_wrap - 30))
        lb.pack(side="left", fill="x", expand=True)
        self._bullets.append(lb)

    def _wrap_bullets(self, box, width):
        for lb in getattr(self, "_bullets", []):
            try:
                lb.config(wraplength=max(160, width - 30))
            except Exception:
                pass

    def _render_review(self, idea):
        """结构诊断：只列「交代了什么 / 没交代什么」，不显示分数。"""
        bg = T.CARD
        box = self.detail_box
        T.hsep(box, T.LINE, (6, 8))
        head = tk.Frame(box, bg=bg)
        head.pack(fill="x", pady=(2, 2))
        tk.Label(head, text="选题结构诊断", bg=bg, fg=T.TXT,
                 font=T.F(10, True)).pack(side="left")
        tk.Label(head, text="  核查交代完整度，不是质量评分", bg=bg, fg=T.TXT4,
                 font=T.F(8)).pack(side="left")
        wrap = tk.Frame(box, bg=bg)
        wrap.pack(fill="x", pady=(4, 0))
        res = diag_view.render(wrap, idea, compact=True, wrap=self._mid_wrap)
        # 诊断完直接给出口：不知道「怎么补」时，跳到方法论页生成改进计划
        row = tk.Frame(box, bg=bg)
        row.pack(fill="x", pady=(6, 0))
        T.Btn(row, "用方法论改进这个选题",
              lambda: self._goto_skills(idea), "ok").pack(side="left")
        return res

    def _goto_skills(self, idea):
        pg = self.app.page("skills")
        pg.idea = dict(idea)
        pg.idea_lbl.config(text="当前课题：" + idea.get("title", "")[:40], fg=T.OK)
        self.app.goto("skills")
        self.app.toast("已带入课题，选一个方法生成提示词", T.OK)

    # ------------------------------------------------------------ 右侧资源
    def _render_side(self):
        c = self.cands[self.sel]
        cat = self.ctx.get("cat") or ""
        field = self.ctx.get("field") or self.ctx.get("direction", "")
        prof = self.ctx.get("profile") or {}
        scenario = (prof.get("scenarios") or [""])[0] or ""
        methods = prof.get("methods", [])[:2]
        tasks = prof.get("tasks", [])[:2]
        modalities = prof.get("modalities", [])[:2]
        self.side_scroll.clear()
        try:
            venues = kb.recommend_venues(cat, field, scenario, methods, tasks, modalities, top=6)
        except Exception as exc:
            kb._log_exc(type(exc), exc, exc.__traceback__)
            venues = []
        try:
            advisors = advisor_index.recommend(cat, field, scenario, methods, tasks,
                                               modalities, top=6)
        except Exception as exc:
            kb._log_exc(type(exc), exc, exc.__traceback__)
            advisors = []

        bg = T.CARD
        tk.Label(self.side_scroll.inner, text="推荐投稿", bg=bg, fg=T.ACCENT,
                 font=T.F(9, True), anchor="w").pack(fill="x", pady=(2, 2))
        if not venues:
            self._hint(self.side_scroll.inner, "该方向暂无 venue 规则。")
        for v in venues:
            row = tk.Frame(self.side_scroll.inner, bg=T.CARD_HI, cursor="hand2")
            row.pack(fill="x", pady=1)
            head = tk.Frame(row, bg=T.CARD_HI)
            head.pack(fill="x", padx=8, pady=(4, 0))
            tk.Label(head, text=v.get("name", ""), bg=T.CARD_HI, fg=T.TXT,
                     font=T.F(9, True), anchor="w").pack(side="left")
            if v.get("url"):
                tk.Label(head, text="↗", bg=T.CARD_HI, fg=T.ACCENT,
                         font=T.F(9)).pack(side="right")
                row.bind("<Button-1>", lambda e, u=v["url"]: self.app.open_url(u))
            if v.get("reasons"):
                _vr = tk.Label(row, text=" · ".join(v["reasons"])[:30],
                               bg=T.CARD_HI, fg=T.TXT4, font=T.F(8),
                               anchor="w", justify="left")
                _vr.pack(fill="x", padx=8, pady=(0, 4))
                T.fill_wrap(_vr, pad=8)

        T.hsep(self.side_scroll.inner, T.LINE, (4, 6))
        tk.Label(self.side_scroll.inner, text="相关导师", bg=bg, fg=T.PURPLE,
                 font=T.F(9, True), anchor="w").pack(fill="x", pady=(2, 2))
        _an = tk.Label(self.side_scroll.inner,
                       text="按公开出版索引匹配，不代表在职或招生名额",
                       bg=bg, fg=T.TXT4, font=T.F(8), anchor="w", justify="left")
        _an.pack(fill="x", pady=(0, 4))
        T.fill_wrap(_an, pad=6)
        if not advisors:
            self._hint(self.side_scroll.inner, "暂无匹配导师，可到「导师与院校」按方向检索。")
        for a in advisors:
            adv = a.get("advisor", {})
            row = tk.Frame(self.side_scroll.inner, bg=T.CARD_HI, cursor="hand2")
            row.pack(fill="x", pady=1)
            _al = tk.Frame(row, bg=T.CARD_HI)
            _al.pack(fill="x", padx=8, pady=(4, 0))
            tk.Label(_al, text=adv.get("name", ""), bg=T.CARD_HI, fg=T.TXT,
                     font=T.F(9), anchor="w").pack(side="left")
            tk.Label(_al, text="匹配 %s" % a.get("score", ""), bg=T.CARD_HI,
                     fg=T.OK, font=T.M(8)).pack(side="right")
            inst = adv.get("institution", "")
            zh = ""
            try:
                # institution_zh 查不到时会返回英文原名，这里必须判等，
                # 否则会显示成「英文 英文」重复一遍
                zh = kb.institution_zh(inst) or ""
                if zh == inst:
                    zh = ""
            except Exception:
                zh = ""
            tk.Label(row, text=(zh + "  " + inst) if zh else inst, bg=T.CARD_HI, fg=T.TXT4,
                     font=T.F(8), anchor="w", wraplength=T.wrap(250),
                     justify="left").pack(fill="x", padx=8, pady=(0, 4))


        tk.Frame(self.side_scroll.inner, bg=bg, height=T.sp(6)).pack(fill="x")

    # ------------------------------------------------------------ 动作
    def save_idea(self):
        if self.sel is None:
            self.app.toast("请先选择一个候选", T.WARN)
            return
        c = self.cands[self.sel]
        ev = self.ctx.get("review") or {}
        mem = kb.load_research_memory()
        ideas = mem.setdefault("ideas", [])
        title = (c.get("title") or "").strip()
        # 去重：同一个命题连点两下就存两条，台账里会出现两条一模一样的记录，
        # 后面统计、排序全跟着失真。按标题判等（存进来的候选标题不会变）。
        for it in ideas:
            if (it.get("title") or "").strip() == title:
                self._saved_feedback(False, len(ideas), it.get("time", ""))
                self.app.toast("这条已经在创新点库里了，没有重复保存", T.OK)
                return
        idea_type = c.get("type") or kb.infer_innovation_type(c.get("title", ""), c.get("reason", ""))
        ideas.append({
            "time": kb.datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "title": c.get("title", ""),
            "desc": c.get("reason", ""),
            "type": idea_type,
            "category": self.ctx.get("cat", ""),
            "field": self.ctx.get("field", ""),
            "stage": ev.get("stage", ""),
            "structure": ev.get("count", {}),
            "source": "选题工坊",
            # 交叉候选把拼法一起存下来：回头翻创新点库时才知道这条题是
            # 「哪三样拼的」，否则两个月后只剩一个看不懂的标题
            "combo": c.get("combo") or None,
            "fusion": c.get("kind") or "",
        })
        kb.save_research_memory(mem)
        # 记进画像：同一个角度被存得越多，下次排得越前（≥3 次才起作用）
        try:
            import profile_hooks as PH
            PM.bump_pref("angle", c.get("angle_key") or c.get("angle") or "")
            PM.bump_pref("strategy", c.get("strategy") or "")
            PM.remember("把候选存进创新点库：%s" % c.get("title", ""),
                        tags=["选题", c.get("angle", "")], kind="daily",
                        ref=c.get("title", ""), source="选题工坊")
            # 存了哪条题，说明这个方向你真在做 —— 这是比「看过」强得多的信号
            PH.see_field((self.ctx or {}).get("direction") or c.get("field")
                         or c.get("direction") or "", source="选题工坊")
        except Exception:
            pass
        self._saved_feedback(True, len(ideas))
        self.app.toast("已存入创新点库：" + c.get("title", "")[:20], T.OK)
        self.app.mark_dirty("ideas")

    def _saved_feedback(self, saved, total, when=""):
        """把「存了没有、存了几条」留在按钮旁边。

        之前只有 toast，两秒后什么都不剩：用户连点两下，看到两次同款提示，
        也不知道台账里是不是多了一条。现在按钮文案 + 一行回执常驻，直到换候选。
        """
        try:
            now = kb.datetime.datetime.now().strftime("%H:%M")
            if saved:
                self.btn_save.config(text="已存入 ✓")
                text = "已存入创新点库 · %s · 共 %d 条（在「创新点库」里可查看）" % (now, total)
                color = T.OK
            else:
                self.btn_save.config(text="已在库中 ✓")
                when_txt = (" · 原记录 %s" % when) if when else ""
                text = "这条已经在库里了%s · 共 %d 条，本次没有重复保存" % (when_txt, total)
                color = T.TXT2
            self._save_note.config(text=text, fg=color)
            if not self._save_note.winfo_manager():
                # 回执贴在按钮下方、同样从底部占位，避免把动作条顶出卡片
                _anchor = self._act if self._act.winfo_manager() else self.detail_scroll
                self._save_note.pack(side="bottom", fill="x", pady=(4, 0),
                                     before=_anchor)
        except Exception:
            pass

    def make_prompt(self):
        if self.sel is None:
            self.app.toast("请先选择一个候选", T.WARN)
            return
        c = self.cands[self.sel]
        try:
            import prompt_context as PC
            ctx = PC.block(want="task")
        except Exception:
            ctx = ""
        try:
            text = kb.expanded_direction_prompt(self.ctx.get("direction", ""), self.cands, [c],
                                                context=ctx)
        except Exception:
            text = kb.direction_prompt(self.ctx.get("direction", ""), [c.get("title", "")])
        path = kb.save_prompt("选题工坊", text)
        self.app.copy(text)
        self.app.toast("提示词已复制到剪贴板，并存于 exports/prompts/", T.OK)
        self.app.log("已生成交接提示词：" + str(path), T.OK, force_open=True)

    def copy_pack(self):
        if self.sel is None:
            self.app.toast("请先选择一个候选", T.WARN)
            return
        c = self.cands[self.sel]
        lines = ["研究方向：" + self.ctx.get("direction", ""),
                 "候选选题：" + c.get("title", "")]
        if c.get("combo"):
            cmb = c["combo"]
            lines.append("交叉组合：" + " × ".join(
                x for x in (cmb.get("a"), cmb.get("b"), cmb.get("c")) if x))
            lines.append("融合类型：" + c.get("kind", ""))
        lines += ["策略：" + c.get("strategy", ""),
                  "理由：" + c.get("reason", ""),
                 "最小验证：" + (c.get("min_experiment") or "（未给出）"), "",
                 "验证问题："]
        lines += ["  - " + q for q in c.get("questions", [])]
        ev = self.ctx.get("review") or {}
        if ev:
            cnt = ev.get("count", {})
            lines += ["", "结构诊断：%s（已具备 %s/%s 项）"
                      % (ev.get("stage", ""), cnt.get("passed", "-"), cnt.get("total", "-")),
                      "说明：" + str(ev.get("stage_hint", ""))]
            if ev.get("missing"):
                lines.append("尚未交代：")
                lines += ["  - " + m["label"] + "：" + m["fix"] for m in ev["missing"][:5]]
            if ev.get("warnings"):
                lines += ["注意：" + w for w in ev["warnings"]]
        self.app.copy("\n".join(lines))
        self.app.toast("清单已复制", T.OK)

    def show_help(self):
        T.close_child(self)
        win = T.child_window(self, "选题方法论", "640x520")
        self._child_win = win
        sa = T.ScrollArea(win)
        sa.pack(fill="both", expand=True, padx=18, pady=16)
        txt = tk.Text(sa.inner, wrap="word", bg=T.BG, fg=T.TXT2, relief="flat",
                      font=T.F(10), padx=6, pady=6, spacing1=3, spacing3=4,
                      height=24, insertbackground=T.ACCENT)
        txt.pack(fill="both", expand=True)
        txt.insert("end", "选一个题目，本质上是在回答四个问题\n\n", ("h",))
        for t, d in (
            ("1  问题是否真实", "有没有人真的需要它？在真实数据、真实场景里，现状差在哪一步。"),
            ("2  差异是否可验证", "你的机制和最强 baseline 有什么可测的差别？差别要能被实验抓住，而不只是文字描述。"),
            ("3  证据是否够硬", "主指标、失败指标、消融、跨域或部署约束。证据门槛越高，工作越站得住。"),
            ("4  投入是否值得", "三个月内能做完的最小实验是什么？做不出来，这个题就不该继续。"),
        ):
            txt.insert("end", t + "  ", ("k",))
            txt.insert("end", d + "\n\n")
        txt.insert("end", "\n本页的体检分只检查「表述是否具备可验证结构」，", ("m",))
        txt.insert("end", "不代替真实检索、实验与同行评审。", ("m",))
        txt.tag_config("h", foreground=T.TXT, font=T.F(13, True))
        txt.tag_config("k", foreground=T.ACCENT, font=T.F(10, True))
        txt.tag_config("m", foreground=T.WARN)
        txt.config(state="disabled")