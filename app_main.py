#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库助手 · 科研选题版 —— 主程序。

把原来贴在桌面上的 520px 小卡片，升级成一个正常的多页桌面应用：
  左侧导航 + 主页仪表盘 + 6 个科研工作页 + 全局搜索 + 带标签的日志面板。

所有科研能力（方向识别、候选生成、选题体检、导师 / venue 匹配、arXiv 抓取）
全部复用 kb_widget.py 里的既有引擎，本文件只负责「组织与呈现」。

用法：
  pythonw app_main.py     日常启动（桌面快捷方式走这里）
  python  app_main.py     调试启动（带控制台）
"""
import datetime
import ctypes
import os
import queue
import re
import sys
import threading
import tkinter as tk


def _clip_title(text, max_lines=2, px=210):
    """按「一行约能放多少汉字」粗算并截断。

    不做真正的 textwrap：中英混排按半角算宽度会差很多，这里只求
    「高度对齐」，所以按「汉字 1、其余 0.55」折算宽度，超了就加 …。

    **宽度必须跟随字号**：第 12 版字号随 DPI 缩放（正文 15→19px），
    原来写死的 26 是 13px 字下的容量，放大后会截得过早或过晚。
    """
    if not text:
        return ""
    # 每行能放多少个「汉字宽度」的单位：px / 字号
    try:
        size = abs(T.T_BODY_SM()[1]) or 15
    except Exception:
        size = 15
    per_line = max(6.0, float(px) / float(size))
    cap = max_lines * per_line * 1.55      # 1.55 ≈ 汉字相对字号的宽度系数
    w = 0.0
    for i, ch in enumerate(text):
        w += 1.0 if ord(ch) > 127 else 0.55
        if w > cap:
            return text[:i].rstrip() + "…"
    return text


def _follow_width(opts, pad=8):
    """让一串 Label 的 wraplength 跟随父容器实际宽度。

    Tk 没有 CSS 的 `width:100%`，Label 的 wraplength 是**绝对像素**。
    卡片流里的列宽按权重分配（4 列时宽列 ~364px、窄列 ~250px），
    而字号又随 DPI 缩放，写死的数字必然对不上——要么截断，要么留白。

    opts: [(owner_widget, label_widget), ...]，owner 的宽度变化时同步
    更新 label 的 wraplength。
    """
    for owner, lbl in opts:
        def _sync(e=None, _o=owner, _l=lbl):
            try:
                w = _o.winfo_width()
                if w > 40:
                    _l.configure(wraplength=max(60, w - pad))
            except Exception:
                pass
        try:
            owner.bind("<Configure>", _sync, add="+")
            _sync()
        except Exception:
            pass


from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import app_theme as T          # noqa: E402
import app_icons as I          # noqa: E402
import ui_parts as U           # noqa: E402
import ui_kit as UK            # noqa: E402
import app_widgets as widgets  # noqa: E402
import app_diagnose_view as diag_view  # noqa: E402
import research_diagnose as RD  # noqa: E402
import kb_widget as kb         # noqa: E402
import kb_download as KB       # noqa: E402
from page_library import LibraryPage   # noqa: E402
from page_materials import MaterialsPage, load_materials  # noqa: E402
from page_topic import TopicPage       # noqa: E402
from page_ideas import IdeasPage       # noqa: E402
from page_map import MapPage           # noqa: E402
from page_mentor import MentorPage     # noqa: E402
from page_skills import SkillsPage     # noqa: E402
from page_gap import GapPage           # noqa: E402
from page_latest import LatestPage     # noqa: E402
from page_venue import VenuePage, SettingsPage  # noqa: E402
from page_profile import ProfilePage  # noqa: E402
from page_plan import PlanPage        # noqa: E402

APP_TITLE = "塞莎特——题谱"
# 侧栏只放得下主名，女神名单独一行（见 _build_sidebar 的品牌块）。
APP_TITLE_SHORT = "题谱"
APP_SUB = "科研选题工作台"
VERSION = "v4.0"

# 侧栏用的 logo 尺寸：由 make_logo.py 一起生成，缺失时回退到 48 那份
_HERE = Path(__file__).resolve().parent
_LOGO_40 = _HERE / "logo_48.png"
# 2026-11 第 7 版侧栏顶部收窄到 26 逻辑像素左右，改用 32px 分档图。
# 2026-11-16 第 6 版 logo 起：母图换成 128px，**显示前必须经 _load_logo() 预缩**，
# 不能把文件路径直接交给 tk.PhotoImage（Tk 不缩放，原图多大就贴多大）。
_LOGO_UI = _HERE / "logo_128.png"


def _load_logo(logical_px=32):
    """按设备像素预缩 logo 母图后返回 Tk 图像（实现见 app_theme.load_bitmap）。

    Tk 的 PhotoImage 不缩放：给多大就贴多大。125% 缩放下侧栏要 32 逻辑像素
    = 40 物理像素，直接塞 32px 会被摆在大方框里（看着小一号），塞 128px
    会被裁。母图取 128px，不同缩放档都能干净地缩过去。
    """
    src = _LOGO_UI if _LOGO_UI.exists() else _LOGO_32_FALLBACK
    return T.load_bitmap(src, logical_px)


_LOGO_32_FALLBACK = _HERE / "logo_32.png"


def _bind_ellipsis(lbl, full_text, font):
    """让 Label 按**像素宽度**自动省略，而不是按字符数硬截。

    Tk 的 Label 没有 text-overflow: ellipsis，宽度不够时中文会被直接切掉
    半个字（看着像乱码）。这里监听 <Configure>：拿到控件真实分配宽度，
    用 tkinter.font.Font.measure 逐字累加，超出就补「…」。

    2026-11-15：首页论文标题原来是 `if len(name) > 52: name = name[:50] + "…"`。
    中英混排下 52 个字符可能只占 400px、也可能占 900px，和可用宽度毫无关系，
    所以总是一半标题被提前截断、另一半仍然溢出。改成按像素量。
    """
    try:
        from tkinter import font as tkfont
        fobj = tkfont.Font(font=font)
    except Exception:
        return

    state = {"full": str(full_text or ""), "w": 0}

    def _apply(width):
        w = int(width) - 4          # 留一点内边距，别贴着边框
        if w <= 0 or w == state["w"]:
            return
        state["w"] = w
        s = state["full"]
        if fobj.measure(s) <= w:
            lbl.config(text=s)
            return
        # 二分找最长能放下的前缀，再补省略号
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fobj.measure(s[:mid] + "…") <= w:
                lo = mid
            else:
                hi = mid - 1
        lbl.config(text=(s[:lo] + "…") if lo > 0 else "…")

    def _on_conf(ev):
        _apply(ev.width)

    lbl.bind("<Configure>", _on_conf, add="+")
    # 首次布局前先粗放一遍，避免闪一下完整长标题
    root = lbl.winfo_toplevel()
    root.after(30, lambda: _apply(lbl.winfo_width() or 0))


class StatCard(tk.Frame):
    def __init__(self, parent, label, value, hint="", color=T.ACCENT, cmd=None):
        super().__init__(parent, bg=T.CARD, cursor="hand2" if cmd else "arrow")
        self.cmd = cmd
        self.config(bg=T.CARD)
        pad = tk.Frame(self, bg=T.CARD)
        pad.pack(fill="both", expand=True, padx=14, pady=10)
        tk.Label(pad, text=label, bg=T.CARD, fg=T.TXT3, font=T.F(9),
                 anchor="w").pack(fill="x")
        self.val = tk.Label(pad, text=str(value), bg=T.CARD, fg=color,
                            font=T.T_METRIC(), anchor="w")
        self.val.pack(fill="x")
        self.hint = tk.Label(pad, text=hint, bg=T.CARD, fg=T.TXT4, font=T.F(8),
                             anchor="w", justify="left", wraplength=T.wrap(200))
        self.hint.pack(fill="x")
        if cmd:
            self.bind("<Button-1>", lambda e: cmd())
            for w in (pad, self.val):
                w.bind("<Button-1>", lambda e: cmd())

    def set(self, v, hint=None, color=None):
        self.val.config(text=str(v))
        if hint is not None:
            self.hint.config(text=hint)
        if color:
            self.val.config(fg=color)


class HomePage(tk.Frame):
    """仪表盘：一眼看到「现在该做什么」。"""

    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        # 不再 after(120, self.reload)：goto 建好页面后本来就会调一次 reload，
        # 两遍叠起来等于首屏渲染两次（实测首次 571ms → 303ms 的差就在这里）。
        self.reload()

    @staticmethod
    def _sig():
        """页面内容真正依赖的东西：PDF 清单、选题台账、arXiv 去重记录。

        三者任一变化都要重画；都没变就把整页重建省掉 —— 切回总览时
        原来无条件 destroy 再重建，实测每切一次 339ms。
        """
        parts = []
        for p in (kb.RESEARCH_MEMORY, kb._DATA("seen_ids.json")):
            try:
                st = Path(p).stat()
                parts.append((st.st_mtime_ns, st.st_size))
            except Exception:
                parts.append(None)
        try:
            parts.append(len(kb._inventory().get("pdfs") or []))
        except Exception:
            parts.append(None)
        return tuple(parts)

    def reload(self, force=False):
        if not force and getattr(self, "_built", False):
            sig = self._sig()
            if sig == getattr(self, "_sig_val", None):
                return
        self._sig_val = self._sig()
        self._built = True
        for w in self.winfo_children():
            w.destroy()
        self._page_box = T.ScrollArea(self, bg=T.BG)
        self._page_box.pack(fill="both", expand=True)
        page = self._page_box.inner

        self._build_hero(page)
        self._build_plan(page)
        self._build_kpi(page)
        self._build_modules(page)

        try:
            self._page_box.refresh()
        except Exception:
            pass

    # ------------------------------------------------------------ 顶部
    def _build_kpi(self, page):
        """五个主指标横排 + 一行过程指标。

        之前的版本是 7 行表格，把「知识库文献 344 / 已提取标题 340 /
        语义索引 343」这些**几乎同源的数字**平铺在同一条垂直线上，占掉半屏，
        读者要自己判断哪个才是重要的 —— 这才是「粗糙」的观感来源：
        所有东西一样大、一样重，等于没有层级。

        现在分两层：
          - 主层：真正会变的那五个数（我的选题 / 知识库 / 导师 / 方向 / 素材库）
          - 细节层：其余过程指标压成一行小字，需要时才看
        数字用一个 Metric 风格的块（大数字 + 单位 + 名称），不再拉成七行。
        """
        card = T.Card(page, pad=0)
        card.pack(fill="x", padx=T.PAD, pady=(0, 12))

        head = tk.Frame(card.body, bg=T.CARD)
        head.pack(fill="x", padx=16, pady=(12, 10))
        tk.Label(head, text="数据概览（本地实时计算）", bg=T.CARD, fg=T.TXT3,
                 font=T.T_CAPTION(), anchor="w").pack(side="left")
        T.Btn(head, "刷新", lambda: self.reload(force=True)).pack(side="right")

        main, detail = self._kpi_rows()

        strip = tk.Frame(card.body, bg=T.CARD)
        strip.pack(fill="x", padx=16, pady=(0, 10))
        for i in range(len(main)):
            strip.grid_columnconfigure(i, weight=1, uniform="kpi")
        for i, (name, value, unit, color) in enumerate(main):
            cell = tk.Frame(strip, bg=T.CARD)
            cell.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            if i:
                # 列间竖线画在 cell 内部左缘（grid 的 cell 不能直接放一条线）
                tk.Frame(cell, bg=T.LINE_SOFT, width=1).pack(side="left", fill="y",
                                                              padx=(0, 8))
            box = tk.Frame(cell, bg=T.CARD)
            box.pack(side="left", fill="both", expand=True)
            # 名称在上、数字在下：先告诉读者「这是哪个数」，数字才有意义。
            # 反过来（大数字在上、名称在下）读起来像倒装，且四个数字字号一样大时
            # 视线先被数字拽走，反而不知道在看什么。
            tk.Label(box, text=name, bg=T.CARD, fg=T.TXT3,
                     font=T.T_CAPTION(), anchor="w").pack(anchor="w")
            row = tk.Frame(box, bg=T.CARD)
            row.pack(anchor="w", pady=(2, 0))
            # 数字 → 单位，单位更小更弱，贴着数字底边而不是居中
            tk.Label(row, text=str(value), bg=T.CARD, fg=color or T.TXT,
                     font=T.T_METRIC()).pack(side="left")
            if unit:
                tk.Label(row, text=unit, bg=T.CARD, fg=T.TXT4,
                         font=T.T_CAPTION()).pack(side="left", padx=(4, 0),
                                                  pady=(8, 0))

        if detail:
            lb = tk.Label(card.body, text=detail, bg=T.CARD, fg=T.TXT4,
                          font=T.T_CAPTION(), anchor="w", justify="left")
            lb.pack(fill="x", padx=16, pady=(0, 12))
            T.fill_wrap(lb, pad=32)

        try:
            card.sync_now()
        except Exception:
            pass

    def _kpi_rows(self):
        """返回 `(主指标列表, 细节一行)`；主指标是 `(名称, 数字, 单位, 颜色)`。

        全部带 try —— 任何一项数据源缺失都不该让总览页打不开。
        缺数据的写「—」而不是 0：0 是一个结论（真的没有），「—」是没查。
        """
        def _n(fn, default=None):
            try:
                return fn()
            except Exception:
                return default

        st = _n(lambda: kb.kb_stats(), {}) or {}
        pdf = st.get("total_pdf")
        mem = _n(lambda: kb.load_research_memory(), {}) or {}
        ideas = mem.get("ideas") or []
        dirs = mem.get("directions") or []
        seen = _n(lambda: kb.seen_count(), None)
        sem = _n(lambda: __import__("semantic_search").stats(), {}) or {}
        av = _n(lambda: __import__("advisor_index").stats(), {}) or {}
        lib = _n(lambda: kb.load_direction_library(), {}) or {}
        meta = _n(lambda: __import__("meta_index").stats(), {}) or {}
        mats = _n(lambda: load_materials(), {}) or {}

        n_field = sum(len((v or {}).get("subs") or []) for v in lib.values()) if lib else None
        n_idea = len(ideas)
        n_adv = av.get("complete_advisors") if av else None
        n_data = len(mats.get("datasets") or []) or None

        # 主层：四个真正会变、且用户会拿来判断「我该干什么」的数。
        # 「我的选题 0 条」用警示色 —— 0 在这一页是唯一一个「你该去做点什么」的信号。
        main = [
            ("我的选题", n_idea, "条", T.WARN if n_idea == 0 else T.TXT),
            ("知识库文献", pdf if pdf is not None else "—", "篇", T.TXT),
            ("导师名单", n_adv if n_adv is not None else "—", "人", T.TXT),
            ("研究方向", n_field if n_field is not None else "—", "个", T.TXT),
            ("素材库", n_data if n_data is not None else "—", "个", T.TXT),
        ]

        bits = []
        if ideas:
            bits.append("关注 %d 个方向" % len(dirs))
        else:
            bits.append("选题还没存档，去「选题工坊」生成")
        if meta:
            bits.append("标题已识别 %s/%s" % (meta.get("title", "—"), meta.get("count", "—")))
        if seen is not None:
            bits.append("arXiv 已见 %d 篇" % seen)
        if sem:
            bits.append("语义索引 %s 维" % sem.get("dims", "—"))
        if lib:
            bits.append("%d 个大类下分 %s 个方向" % (len(lib), n_field if n_field is not None else "—"))
        detail = " · ".join(bits)
        return main, detail

    # ------------------------------------------------------------ 顶部
    def _build_hero(self, page):
        """一句引导 + 一个输入框。

        参考图的抬头只有标题和一行元信息，没有「hero 大标语」。页头已经有
        30px 的「总览」了，下面再放一个 30px 的「下午好，今天想找什么问题？」
        等于两个同样响的标题叠在一起，谁都不是重点。所以问候降成正文大小，
        让步给输入框和数据表。
        """
        top = tk.Frame(page, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        tk.Label(top, text="总览", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE()).pack(side="left")
        note = tk.Label(page, text="从研究方向到候选、证据与实验；计划由你决定，工具只提供线索。",
                        bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w", justify="left")
        note.pack(fill="x", padx=T.PAD, pady=(0, 8))
        T.fill_wrap(note)
        card = T.Card(page, pad=14, fill_y=False)
        card.pack(fill="x", padx=T.PAD, pady=(0, 12))
        UK.eyebrow(card.body, "从方向开始", "01").pack(fill="x", pady=(0, 6))
        start = tk.Frame(card.body, bg=T.CARD)
        start.pack(fill="x")
        e = tk.Entry(start, bg=T.CARD_HI, fg=T.TXT, insertbackground=T.ACCENT,
                     relief="flat", font=T.T_BODY(), width=1)
        T.fix_highlight(e, T.card_edge(T.LINE, T.CARD))
        e.insert(0, "输入研究方向，例如：红外小目标检测")
        e.config(fg=T.TXT4)
        self._hero_entry = e

        def focus_in(_):
            if e.get().startswith("输入研究方向"):
                e.delete(0, "end")
                e.config(fg=T.TXT)

        def go(_=None):
            v = e.get().strip()
            if not v or v.startswith("输入研究方向"):
                self.app.toast("请先输入研究方向", T.WARN)
                return
            self.app.goto("topic")
            tp = self.app.page("topic")
            tp.entry.delete(0, "end")
            tp.entry.insert(0, v)
            tp.generate()

        e.bind("<FocusIn>", focus_in)
        e.bind("<Return>", go)
        T.Btn(start, "开始选题", go, "primary").pack(side="right", padx=(10, 0))
        e.pack(side="left", fill="x", expand=True, ipady=6)

    # ------------------------------------------------------------ 宫格
    def _module_tiles(self):
        """「我要做什么」这一组：每格跳到一页，角标是这一页眼下有多少东西。"""
        try:
            n_pdf = int(kb.kb_stats().get("total_pdf") or 0)
        except Exception:
            n_pdf = 0
        try:
            n_idea = len(kb.load_research_memory().get("ideas") or [])
        except Exception:
            n_idea = 0
        try:
            import meta_index
            n_abs = int(meta_index.stats().get("abstract") or 0)
        except Exception:
            n_abs = 0
        try:
            n_seen = int(kb.seen_count() or 0)
        except Exception:
            n_seen = 0
        try:
            import semantic_search
            sem = semantic_search.stats()
            n_vec = int(sem.get("indexed") or 0)
        except Exception:
            n_vec = 0
        try:
            import research_skills
            n_skill = len(research_skills.SKILLS)
        except Exception:
            n_skill = 0
        try:
            av = __import__("advisor_index").stats()
            n_adv = int(av.get("complete_advisors") or av.get("advisors") or 0)
            n_inst = int(av.get("institutions") or 0)
        except Exception:
            n_adv = n_inst = 0
        try:
            lib = kb.load_direction_library()
            n_field = sum(len((v or {}).get("subs") or []) for v in lib.values())
            n_cat = len(lib)
        except Exception:
            n_field = n_cat = 0

        A = self.app
        return [
            ("topic", "选题工坊", "输方向，生成角度不同的候选", "%d 方向" % n_field,
             lambda: A.goto("topic")),
            ("gap", "文献空白", "哪些方法×任务还没人做", "",
             lambda: A.goto("gap")),
            ("latest", "最新研究", "按方向追 arXiv 新论文", "%d 篇" % n_seen,
             lambda: A.goto("latest")),
            ("ideas", "创新点库", "候选存档，按结构体检", "%d 条" % n_idea,
             lambda: A.goto("ideas")),
            ("skills", "科研方法论", "七步流程，不会做时看", "%d 套" % n_skill,
             lambda: A.goto("skills")),
            ("mentor", "导师与院校", "谁在做、在哪所学校", "%d 人" % n_adv,
             lambda: A.goto("mentor")),
            ("venue", "期刊会议", "该投哪里、什么级别", "",
             lambda: A.goto("venue")),
            ("library", "文献库", "本地 PDF 与语义检索", "%d 篇" % n_pdf,
             lambda: A.goto("library")),
            ("map", "方向图谱", "%d 类 %d 个方向" % (n_cat, n_field), "",
             lambda: A.goto("map")),
            ("profile", "个人画像", "方向偏好与约束", "",
             lambda: A.goto("profile")),
            ("settings", "设置与数据", "接模型、主题、目录", "",
             lambda: A.goto("settings")),
        ]

    def _open_search(self):
        try:
            self.app.show_search()
        except Exception:
            pass

    # ------------------------------------------------------------ 个人计划
    def _build_plan(self, page):
        """总览的「个人计划」摘要区。

        2026-11-15 用户否掉了原来的四列卡片流（我的选题 / 最近入库 /
        导师候选 / 下一步），原话是「这块我不需要，我认为不太科学，
        看的不舒服」。复盘原因：那四列把**四种不同性质的东西**并排成
        同一种卡片，读的人必须先自己判断「哪一列现在跟我有关」；
        而且「下一步」是系统猜的，猜得越像建议越像指令。

        换成一块计划摘要后，总览回答的是同一个问题 ——「我现在该做什么」——
        但答案来自**用户自己排的计划**，系统只负责把剩余时间和待办摆出来。
        """
        try:
            import plan_store as PS
        except Exception:
            return
        try:
            p = PS.progress()
        except Exception:
            return

        card = T.Card(page, pad=14, fill_y=False)
        card.pack(fill="x", padx=T.PAD, pady=(0, 12))

        head = tk.Frame(card.body, bg=T.CARD)
        head.pack(fill="x")
        tk.Label(head, text="研究计划", bg=T.CARD, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(side="left")
        T.Btn(head, "打开研究计划", lambda: self.app.goto("plan")).pack(side="right")

        if p.get("empty"):
            # 没有计划时不摆空表格，只给一句能立刻做的事。
            # 这里**不显示 0/0** —— 一串零会让人以为系统算错了。
            note = tk.Label(card.body,
                            text="还没有排计划。阶段与截止日期由你填写，不自动预测工期。",
                            bg=T.CARD, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                            justify="left")
            note.pack(fill="x", pady=(8, 6))
            T.fill_wrap(note)
            try:
                card.sync_now()
            except Exception:
                pass
            return

        cur = p.get("current")
        if cur:
            row = tk.Frame(card.body, bg=T.CARD)
            row.pack(fill="x", pady=(8, 2))
            st, days = p.get("current_state"), p.get("current_days")
            if st == "over":
                txt, col = "已过期 %d 天" % (-days), T.ERR
            elif st == "none":
                txt, col = "没填截止日", T.TXT3
            elif days == 0:
                txt, col = "今天到期", T.WARN
            elif days <= 7:
                txt, col = "还剩 %d 天" % days, T.WARN
            else:
                txt, col = "还剩 %d 天" % days, T.TXT3
            T.Pill(row, txt, col, bg=T.CARD).pack(side="right", padx=(10, 0))
            label = tk.Label(row, text=str(cur.get("name") or ""), bg=T.CARD, fg=T.TXT,
                             font=T.T_BODY(), anchor="w", justify="left")
            label.pack(side="left", fill="x", expand=True)
            T.fill_wrap(label)

        # 三条最近待办：勾选框是只读的，点一下回到计划页 ——
        # 总览是「看」的地方，在这里改数据会让两处状态不同步。
        try:
            ups = PS.upcoming(3)
        except Exception:
            ups = []
        if ups:
            box = tk.Frame(card.body, bg=T.CARD)
            box.pack(fill="x", pady=(6, 0))
            for t in ups:
                r = tk.Frame(box, bg=T.CARD)
                r.pack(fill="x", pady=1)
                tk.Label(r, text="·", bg=T.CARD, fg=T.TXT4,
                         font=T.T_BODY_SM()).pack(side="left", padx=(0, 6))
                meta = []
                lt = PS.link_text(t.get("link"))
                if lt:
                    meta.append(lt)
                _st, _d = PS.due_state(t.get("due"))
                if _st != "none":
                    meta.append("已过期 %d 天" % (-_d) if _st == "over"
                                else ("今天到期" if _d == 0 else "还剩 %d 天" % _d))
                tk.Label(r, text=" · ".join(meta), bg=T.CARD,
                         fg=(T.ERR if _st == "over" else T.TXT4),
                         font=T.T_CAPTION(), anchor="e").pack(side="right")
                tk.Label(r, text=str(t.get("text") or ""), bg=T.CARD, fg=T.TXT2,
                         font=T.T_BODY_SM(), anchor="w", justify="left",
                         wraplength=T.wrap(600)).pack(side="left", fill="x",
                                                      expand=True)
        else:
            tk.Label(card.body, text="所有待办都勾完了。",
                     bg=T.CARD, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w").pack(
                fill="x", pady=(8, 0))

        line = ""
        try:
            line = PS.summary_line()
        except Exception:
            line = ""
        if line:
            lb = tk.Label(card.body, text=line, bg=T.CARD, fg=T.TXT4,
                          font=T.T_CAPTION(), anchor="w", justify="left")
            lb.pack(fill="x", pady=(8, 0))
            _follow_width([(card.body, lb)], pad=16)
        try:
            card.sync_now()
        except Exception:
            pass

    def _build_modules(self, page):
        card = T.Card(page, pad=14)
        card.pack(fill="x", padx=T.PAD, pady=(0, 12))
        # 与首页「数据概览」用同一个卡头写法：淡色小字 + 括号说明
        T.card_head(card.body, "科研导航", "点任意一格进入对应模块", bg=T.CARD)
        grid = U.TileGrid(card.body, self._module_tiles(), bg=T.CARD,
                          min_w=176, gap=6, cols_max=4)
        grid.pack(fill="x")
        try:
            card.sync_now()
        except Exception:
            pass

    # ------------------------------------------------------------ 最近
    def _build_recent(self, page):
        """最近入库：一行一条，最多 8 条，右边给「全部文献」。"""
        card = T.Card(page, pad=14)
        card.pack(fill="x", padx=T.PAD, pady=(0, 18))
        head = tk.Frame(card.body, bg=T.CARD)
        head.pack(fill="x")
        tk.Label(head, text="最近入库（最近读过的 8 篇）", bg=T.CARD, fg=T.TXT3,
                 font=T.T_CAPTION(), anchor="w").pack(side="left")
        T.Btn(head, "全部文献", lambda: self.app.goto("library")).pack(side="right")
        items = []
        try:
            items = kb.recent_pdfs(3650, 8)
        except Exception:
            pass
        if not items:
            tk.Label(card.body, text="知识库里还没有 PDF。点「文献库 → 抓取新论文」开始。",
                     bg=T.CARD, fg=T.TXT4, font=T.T_BODY_SM(), anchor="w",
                     justify="left").pack(fill="x", pady=(10, 4))
            return
        for it in items:
            f = tk.Frame(card.body, bg=T.CARD, cursor="hand2")
            f.pack(fill="x", pady=1)
            # 右侧放「年份 + 会议」这类有判断价值的信息。
            # 原来放的是文件夹名（"根目录" / "Mamba多模态" / "2026 paper"），
            # 那是用户自己建的抽屉名，对着标题念一遍并没有增加信息。
            mt = {}
            try:
                import meta_index
                mt = meta_index.get(it["path"]) or {}
            except Exception:
                pass
            tags = []
            if mt.get("year"):
                tags.append(str(mt["year"]))
            if mt.get("venue"):
                tags.append(str(mt["venue"]))
            if mt.get("is_survey"):
                tags.append("综述")
            if tags:
                tk.Label(f, text=" · ".join(tags), bg=T.CARD, fg=T.TXT4,
                         font=T.T_CAPTION(), anchor="e").pack(side="right", padx=(8, 4))
            # 标题：meta 里常带尾部的 arXiv id（"… 2610 36750v1"），交给
            # meta_index.clean_title 统一剥掉（各页共用一套规则）
            import meta_index as _MI
            name = _MI.clean_title(mt.get("title"))
            if not name:
                name = os.path.splitext(os.path.basename(it["path"]))[0].replace("_", " ")
            lb = tk.Label(f, text=name, bg=T.CARD, fg=T.TXT2, font=T.T_BODY_SM(),
                          anchor="w")
            lb.pack(side="left", fill="x", expand=True, pady=2)
            _bind_ellipsis(lb, name, T.T_BODY_SM())
            for w in (f, lb):
                w.bind("<Button-1>", lambda e, p=it["path"]: os.startfile(p))
                w.bind("<Enter>", lambda e, fr=f: fr.config(bg=T.LINE_SOFT))
                w.bind("<Leave>", lambda e, fr=f: fr.config(bg=T.CARD))


    def _layout_stats(self):
        """按当前宽度把四张指标卡排成 4 列或 2×2。

        宽度小于 1100px 时，四张卡横排会各自按提示文字的自然宽度撑开，
        加起来超过可用宽度，最后一张被挤出右缘（实测 1094px 窗口就是这个现象）。
        改成两行两列后每张都有一半宽度，提示文字再长也放得下。
        """
        row = self._stat_row
        data = self._stat_cards_data
        try:
            row.update_idletasks()
            avail = row.winfo_width()
        except Exception:
            avail = 0
        if avail < 300:                      # 首帧还没布局，按 1320 基准估算
            avail = 1320 - T.SIDEBAR_W - T.PAD * 2
        cols = 4 if avail >= 1100 else 2
        self._stat_cols = cols
        self._stat_cards = []
        for i, (lb, v, h, c, cmd) in enumerate(data):
            card = StatCard(row, lb, v, h, c, cmd)
            if cols == 4:
                card.grid(row=0, column=i, sticky="nsew",
                          padx=(0 if i == 0 else 10, 0))
            else:
                card.grid(row=i // 2, column=i % 2, sticky="nsew",
                          padx=(0 if i % 2 == 0 else 10, 0),
                          pady=(0 if i < 2 else 10, 0))
            # 浅色主题下卡片不画描边（靠页面灰底 + 卡片白底分层，见 T.card_outline），
            # 深色主题才保留 1px 细线。
            _edge = T.card_outline(T.LINE, T.CARD)
            if _edge:
                T.fix_highlight(card, _edge)
            else:
                try:
                    card.configure(highlightthickness=0, bd=0)
                except Exception:
                    pass
            self._stat_cards.append(card)
        for cidx in range(cols):
            row.grid_columnconfigure(cidx, weight=1, uniform="stat")
        for cidx in range(cols, 4):
            row.grid_columnconfigure(cidx, weight=0, uniform="")

    def _on_stats_resize(self, event):
        """窗口跨过 1100px 阈值时重排指标卡，避免每次 Configure 都重建。"""
        want = 4 if event.width >= 1100 else 2
        if want == getattr(self, "_stat_cols", None):
            return
        for c in getattr(self, "_stat_cards", []):
            try:
                c.destroy()
            except Exception:
                pass
        self._layout_stats()

    def _build_trend(self, host):
        """入库概况：一行一句，不用图表。

        2026-11-15 用户要求「可视化表去除」——主页原来有两张图（入库时间轴、
        技术词 Top）。这两张图的信息其实一句话就能说完，而且图占掉 160px
        把下面的最新入库挤得只剩一条缝。现在改成两行文字：
        第一行说入库节奏，第二行说读得集不集中。
        数据仍全部来自本地（PDF 的 mtime + paper_meta 的标题），不联网。
        """
        try:
            inv = kb._inventory()
        except Exception:
            return
        pdfs = inv.get("pdfs") or []
        if not pdfs:
            return

        # ── 按月统计（最近 12 个月）────────────────────────────────
        try:
            buckets = {}
            for mtime, _size, _p in pdfs:
                d = datetime.datetime.fromtimestamp(mtime)
                buckets[d.strftime("%Y-%m")] = buckets.get(d.strftime("%Y-%m"), 0) + 1
            keys = sorted(buckets)[-12:]
            vals = [buckets[k] for k in keys]
            this_month = buckets.get(datetime.date.today().strftime("%Y-%m"), 0)
            if vals:
                busiest = keys[vals.index(max(vals))]
                quiet = [k for k, v in zip(keys, vals) if v == 0]
                rhythm = ("入库节奏：近 12 个月共 %d 篇，本月 %d 篇，"
                          "最多的一个月是 %s（%d 篇）"
                          % (sum(vals), this_month, busiest, max(vals)))
                if quiet:
                    rhythm += "；%d 个月没有新入库" % len(quiet)
        except Exception:
            rhythm = ""

        # ── 技术词 Top：标题里出现最多的英文技术词 ────────────────
        words = {}
        try:
            import meta_index
            stop = {"with", "from", "using", "based", "for", "and", "the",
                    "via", "towards", "toward", "into", "under", "your",
                    "this", "that", "its", "our", "are", "not", "new",
                    "a", "an", "of", "in", "on", "to", "by", "at", "is"}
            for p in [str(t[2]) for t in pdfs]:
                mt = meta_index.get(p) or {}
                title = (mt.get("title") or "").lower()
                for w in set(re.findall(r"[a-z][a-z\-]{2,}", title)):
                    if w in stop:
                        continue
                    words[w] = words.get(w, 0) + 1
        except Exception:
            words = {}

        lines = []
        if rhythm:
            lines.append(rhythm)
        top = sorted(words.items(), key=lambda kv: -kv[1])[:6]
        if top:
            lines.append("标题高频词：" + " · ".join("%s %d" % (w, n) for w, n in top)
                         + "（只统计本地 PDF 标题，用来看「读得集不集中」）")
        if not lines:
            return

        box = tk.Frame(host, bg=T.BG)
        box.pack(fill="x", padx=T.PAD, pady=(0, 8))
        for txt in lines:
            tk.Label(box, text=txt, bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(),
                     anchor="w", justify="left",
                     wraplength=T.wrap(980)).pack(fill="x", pady=(0, 2))
        try:
            self._page_box.refresh()
        except Exception:
            pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        # 字体与字号**必须最先定**：每个 Label 建立时就把 (family, size)
        # 写进了自己的 font 选项，建完再改常量不会回头影响它们。
        # 原来 _apply_font_scale 放在 main() 里、App() 之后调用，
        # 等于只改了 Tk 内置字体，页面控件的字号与字体族一直是默认值。
        try:
            _apply_font_scale(self)
        except Exception:
            pass
        # 主题要在建控件之前定：控件建立时就把颜色写死了
        # 2026-11-15 第 11 版：默认改成浅色（用户指定的参考图是浅色界面），
        # 暗色仍可在设置页或 Ctrl+Shift+L 切换，切换结果会写回 config.json。
        try:
            _mode = kb.load_config().get("theme") or "light"
        except Exception:
            _mode = "light"
        try:
            T.apply_mode(_mode)
        except Exception:
            pass
        # 字号档位也要在建控件之前定。默认「标准」，25 岁的人和 55 岁的人
        # 用同一个字号是不合理的 —— 设置页里四档可选，Ctrl+= / Ctrl+- 也能调。
        # 2026-11 第 31 版：默认改为「自动」—— 2560 屏上还按 15px 正文排，
        # 整页缩在中间一小块，用户第一反应就是「为什么没有适配大屏」。
        # 手动选档位即关闭自动（见 set_font_step）。
        try:
            _cfg = kb.load_config()
        except Exception:
            _cfg = {}
        self._font_auto = bool(_cfg.get("font_auto", True))
        _step = _cfg.get("font_step") or "normal"
        if self._font_auto:
            try:
                _step = T.step_for_width(self.winfo_screenwidth())
            except Exception:
                _step = "normal"
        try:
            T.set_font_step(_step)
            T.SIDEBAR_W = max(210, int(round(210 * T.font_scale() ** 0.85)))
        except Exception:
            pass
        self.configure(bg=T.BG)
        # 档次越高，窗口默认开得越大：超特大档下 1320px 只放得下两栏，
        # 与其让人一进来就去拉窗口，不如按档位给一个合适的初始尺寸。
        try:
            _fs = T.font_scale()
            _w, _h = int(round(1320 * (1 + 0.18 * (_fs - 1)))), \
                     int(round(860 * (1 + 0.12 * (_fs - 1))))
            _sw, _sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry("%dx%d" % (min(_w, int(_sw * 0.94)),
                                     min(_h, int(_sh * 0.90))))
        except Exception:
            self.geometry("1320x860")
        self.minsize(min(1080, self.winfo_screenwidth() - 80),
                     min(680, self.winfo_screenheight() - 120))
        # wrap() 的上限：内容区比这更宽也没有意义（参见 app_theme.set_maxw）
        try:
            T.set_maxw(self.winfo_screenwidth() - T.SIDEBAR_W - T.PAD * 2)
        except Exception:
            pass
        try:
            self.iconbitmap(str(kb.ICON))
        except Exception:
            pass
        self.report_callback_exception = kb._log_exc
        self.q = queue.Queue()
        self.pages = {}
        self.current = None
        self._log_lines = []
        self._closing = False
        try:
            widgets.init(self)
        except Exception:
            pass
        self._build()
        self.after(60, self._poll)
        self.goto("home")
        self.after(200, self._reload_home)
        # 延后 4 秒再预热：启动瞬间先让首屏画出来，
        # 预热是后台线程，不抢 UI 线程，但会抢 CPU/磁盘
        self.after(4000, self._warm_search)

    # ------------------------------------------------------------ 框架
    def _header(self, main, key, name):
        """细顶栏，对齐网页版 .topbar。

        网页版顶栏只有一行：左边「塞莎特——题谱 / 选题工坊」，右边时钟与图标；
        页面的大标题、说明、统计都属于内容区的英雄卡。桌面端原来把
        32px 大标题和「版本 · 路径 · 状态」两行元信息堆在顶栏，每次
        换页都先吃掉 100px 高度，和网页版的疏朗感正好相反。
        """
        bg = T.BG
        head = tk.Frame(main, bg=bg)
        self._header_frame = head
        head.pack(side="top", fill="x", padx=T.PAD + 4, pady=(T.sp(8), T.sp(2)))
        left = tk.Frame(head, bg=bg)
        left.pack(side="left", fill="x", expand=True)

        def _icon(txt, cmd, tip, color=T.TXT3, side="left"):
            w = tk.Label(left, text=txt, bg=bg, fg=color, font=T.F(11),
                         cursor="hand2", padx=T.sp(5))
            w.pack(side=side, padx=(0, T.sp(2)))
            w.bind("<Button-1>", lambda e: cmd())
            w.bind("<Enter>", lambda e: w.config(fg=T.TXT))
            w.bind("<Leave>", lambda e: w.config(fg=color))
            try:
                self._tip(w, tip)
            except Exception:
                pass
            return w

        self.btn_back = _icon("‹", self.nav_back, "返回（Alt + ←）")
        self.btn_fwd = _icon("›", self.nav_forward, "前进（Alt + →）")
        self.crumb = tk.Label(left, text=APP_TITLE + " / " + (name or "总览"), bg=bg,
                              fg=T.TXT3, font=T.T_BODY_SM(), anchor="w")
        self.crumb.pack(side="left", padx=(T.sp(6), 0))

        right = tk.Frame(head, bg=bg)
        right.pack(side="right")

        def _ricon(txt, cmd, tip, color=T.TXT3):
            w = tk.Label(right, text=txt, bg=bg, fg=color, font=T.F(11),
                         cursor="hand2", padx=T.sp(5))
            w.pack(side="right", padx=(0, T.sp(2)))
            w.bind("<Button-1>", lambda e: cmd())
            w.bind("<Enter>", lambda e: w.config(fg=T.TXT))
            w.bind("<Leave>", lambda e: w.config(fg=color))
            try:
                self._tip(w, tip)
            except Exception:
                pass
            return w

        # 时钟：网页版顶栏右侧的「10:16 + 日期」，是很强的一个「在本地运行」信号。
        # 时间与日期同排：顶栏要薄，两行堆叠会把整条栏撑到 60px。
        clock = tk.Frame(right, bg=bg)
        clock.pack(side="right", padx=(T.sp(10), T.sp(4)))
        self.clock_time = tk.Label(
            clock, text="--:--", bg=bg, fg=T.TXT,
            font=(T.MONO, -max(15, int(round(16 * T.font_scale()))), "bold"),
            anchor="e")
        self.clock_time.pack(side="left")
        self.clock_date = tk.Label(clock, text="", bg=bg, fg=T.TXT4,
                                   font=T.T_CAPTION(), anchor="e")
        self.clock_date.pack(side="left", padx=(T.sp(8), 0), pady=(T.sp(4), 0))
        self._tick_clock()

        _ricon("◐" if T.MODE == "light" else "◑", self.toggle_theme,
               "切换明暗（Ctrl + Shift + L）", T.ACCENT)
        _ricon("⌕", self.show_search, "搜索文献（Ctrl + K）")
        self.busy = tk.Label(right, text="", bg=bg, fg=T.TXT3, font=T.T_CAPTION())
        self.busy.pack(side="right", padx=(0, T.sp(8)))

    def _tick_clock(self):
        if getattr(self, "_closing", False):
            return
        try:
            now = datetime.datetime.now()
            self.clock_time.config(text=now.strftime("%H:%M"))
            wd = "一二三四五六日"[now.weekday()]
            self.clock_date.config(text="%s 周%s" % (now.strftime("%Y.%m.%d"), wd))
            self.after(20000, self._tick_clock)
        except Exception:
            pass

    def set_page_tip(self, text):
        """旧接口：网页版顶栏没有提示行，这里只保留调用兼容。"""
        self._page_tip_text = text

    def _tip(self, widget, text):
        """极轻的悬停提示。只给图标按钮用 —— 有文字的按钮不需要。"""
        state = {"win": None}

        def show(_e=None):
            if state["win"]:
                return
            try:
                x = widget.winfo_rootx() + 8
                y = widget.winfo_rooty() + widget.winfo_height() + 6
            except Exception:
                return
            win = tk.Toplevel(self)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            tk.Label(win, text=text, bg=T.OVERLAY, fg=T.TXT2, font=T.F(8),
                     padx=8, pady=4, bd=0,
                     highlightbackground=T.LINE, highlightthickness=1).pack()
            win.geometry("+%d+%d" % (x, y))
            state["win"] = win

        def hide(_e=None):
            w = state.get("win")
            state["win"] = None
            if w:
                try:
                    w.destroy()
                except Exception:
                    pass

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")

    def toggle_theme(self):
        """明暗切换。**整窗重建**：Tk 里没有 CSS 变量，几十个控件各自记着
        建立时的颜色字符串，逐个改必漏。重建一次 0.2 秒，比漏改可靠。"""
        want = "light" if T.MODE == "dark" else "dark"
        try:
            self._save_theme(want)
        except Exception:
            pass
        self.apply_theme(want)

    def _save_theme(self, mode):
        try:
            import app_paths
            cfg = kb.load_config()
            cfg["theme"] = mode
            path = app_paths.DATA / "config.json"
            import json
            path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def set_font_step(self, key):
        """切换字号档位并整窗重建。

        与主题切换同一个套路：Tk 没有 CSS 变量，每个控件建的时候就把字号
        写进了 font 选项，只能重建。重建约 0.2 秒，比漏改几十个控件可靠。
        """
        key = T.set_font_step(key)
        self._font_auto = False
        try:
            import app_paths
            import json
            cfg = kb.load_config()
            cfg["font_step"] = key
            cfg["font_auto"] = False
            (app_paths.DATA / "config.json").write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        T.SIDEBAR_W = max(210, int(round(210 * T.font_scale() ** 0.85)))
        self._rebuild_window()
        name = dict((k, n) for k, n, _f, _d in T.FONT_STEPS).get(key, key)
        try:
            self.toast("字号：%s（已退出自动适配）" % name, T.OK)
        except Exception:
            pass

    def set_font_auto(self):
        """回到「按屏幕自动选档」：手动选过档位后仍可一键恢复。"""
        self._font_auto = True
        try:
            key = T.step_for_width(self.winfo_screenwidth())
        except Exception:
            key = "normal"
        T.set_font_step(key)
        try:
            import app_paths
            import json
            cfg = kb.load_config()
            cfg["font_auto"] = True
            cfg["font_step"] = key
            (app_paths.DATA / "config.json").write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        T.SIDEBAR_W = max(210, int(round(210 * T.font_scale() ** 0.85)))
        self._rebuild_window()
        try:
            name = dict((k, n) for k, n, _f, _d in T.FONT_STEPS).get(key, key)
            self.toast("字号：自动适配（当前 %s）" % name, T.OK)
        except Exception:
            pass

    def font_auto(self):
        return bool(getattr(self, "_font_auto", True))

    def step_font(self, direction):
        """Ctrl++ / Ctrl+- 在四档之间上下一格（不循环，到顶就是到顶）。"""
        keys = [s[0] for s in T.FONT_STEPS]
        try:
            i = keys.index(T.font_step())
        except ValueError:
            i = 0
        j = max(0, min(len(keys) - 1, i + int(direction)))
        if j != i:
            self.set_font_step(keys[j])

    def _rebuild_window(self):
        """把整个窗口拆掉重建，保留当前位置与历史。"""
        cur = self.current or "home"
        hist, pos = list(self.history), self.hist_pos
        kw = self.history[pos][1] if 0 <= pos < len(self.history) else {}
        try:
            T.close_child(self)
        except Exception:
            pass
        for w in list(self.winfo_children()):
            if isinstance(w, tk.Toplevel):
                continue
            try:
                w.destroy()
            except Exception:
                pass
        self.pages = {}
        self.current = None
        self.configure(bg=T.BG)
        self._build()
        self.history, self.hist_pos = hist, pos
        self.goto(cur, _record=False, **kw)
        self._set_nav(cur)
        self._update_nav_ui(cur, kw)

    def apply_theme(self, mode):
        """保留当前位置与历史，把整个窗口拆掉重建。

        2026-11-15：**记住所选主题的写盘也在这里做**。
        以前只有 toggle_theme 会存，任何直接调 apply_theme("light") 的地方
        （截图脚本、测试）都不会落盘 —— 结果再开一个新 App 又变回深色，
        而 T.CARD 已经是浅色的 #f7f8f9，深色界面里冒出一堆浅色块。
        存盘失败不影响切换本身，所以吞掉异常。
        """
        try:
            self._save_theme(mode)
        except Exception:
            pass
        T.apply_mode(mode)
        # 全局堵住 Tk 的默认聚焦环色。Windows 上 Frame/Entry 的默认
        # `highlightcolor` 是系统色名 SystemWindowFrame，浅色主题下渲染成
        # 一条 (217,223,229) 的灰线，和任何主题色都对不上 —— 2026-11-15
        # 用户截图上那种「莫名其妙的粗灰框」就是它。Tk 的 option 默认值
        # 一改，之后新建的所有控件都跟着走，不用逐个控件补。
        try:
            self.option_add("*highlightColor", T.LINE)
            self.option_add("*HighlightColor", T.LINE)
        except Exception:
            pass
        self._rebuild_window()

    def _build(self):
        shell = tk.Frame(self, bg=T.SIDEBAR, width=T.SIDEBAR_W)
        shell.pack(side="left", fill="y")
        shell.pack_propagate(False)

        # 2026-11 第 7 版：侧栏顶部不再是「大 logo + 两行字」的横幅。
        # 参考图的侧栏顶部只有一块很小的标识，导航条目占满整栏 —— 侧栏是
        # 导航工具，不是产品首页。这里缩到 26px logo + 一行 14px 名字。
        #
        # 2026-11-16 第 19 版「侧栏太拥挤」：用户截图里导航区是
        # 「品牌 → 搜索占位 → 12 个条目挤在 110px 一段」。三处一起改：
        #   ① 搜索从**一条独立行**改成一个图标，塞进品牌行右侧 ——
        #      「搜索文献」四个字和下面 12 个条目抢同一块垂直空间，不划算；
        #   ② 导航区改为 fill="both" + expand，剩下的高度留给导航，
        #      而不是把全部条目堆在顶部、底部一整片空白；
        #   ③ 行高 34 → 30，组间距 16 → 10（34px 行 × 12 条在 860 高的窗口里
        #      要吃掉 432px，比内容区一半还多）。
        brand = tk.Frame(shell, bg=T.SIDEBAR)
        self.brand_box = brand
        brand.pack(fill="x", padx=T.sp(16), pady=(T.sp(16), T.sp(8)))
        # 品牌块对齐网页版：圆标 + 「塞莎特——题谱」+ 一行英文副标。
        # 副标是网页版侧栏最有辨识度的一处，也是「这是一个成品应用」的信号。
        try:
            self.logo = _load_logo(34)
            tk.Label(brand, image=self.logo, bg=T.SIDEBAR).pack(
                side="left", padx=(0, T.sp(9)))
        except Exception:
            tk.Label(brand, text="◆", bg=T.SIDEBAR, fg=T.ACCENT,
                     font=T.F(13)).pack(side="left", padx=(0, T.sp(9)))
        # 搜索入口只在顶栏（⌕ / Ctrl+K）；侧栏品牌行不再放第二个放大镜，
        # 那 30px 会让英文副标被截成「RESEARCH A…」。
        names = tk.Frame(brand, bg=T.SIDEBAR)
        names.pack(side="left", fill="x", expand=True)
        # 品牌名排成一整行「塞莎特 —— 题谱」，三段字号递减：
        #   女神名最小、破折号同号、主名大一档（主名大是这里唯一的层级信号）。
        # 2026-11-19 改：原来是**两行**（「塞莎特」/「— 题谱」），两行都顶着
        # 左边界，视觉上像一句被硬折断的话，主名反而比页内条目小。
        # 现在一字排开。**字号不能写死**：这台机器 _SCALE=1.25（系统 DPI）
        # 与 _FS=1.15（字号档）叠乘，13px 声明会落到 19px，而侧栏同时被放大
        # 到 236 宽 —— 两边都在变，写死像素必然溢出。所以字号按 `names`
        # 这个容器的**真实宽度**现算（_brand_segments），宽度变了再算一次。
        row = tk.Frame(names, bg=T.SIDEBAR)
        row.pack(fill="x")
        self._brand_segs = ("塞莎特", " —— ", APP_TITLE_SHORT)
        self._brand_labels = []
        for i, txt in enumerate(self._brand_segs):
            # bd/padx/highlightthickness 全部清零：默认值会给每个 Label
            # 白加 6px（bd=2 + padx=1），三个字块就是 18px —— 这正是
            # 「按 measure() 算够了、实际却溢出被裁」的来源。
            lb = tk.Label(row, text=txt, bg=T.SIDEBAR, bd=0, padx=0,
                          highlightthickness=0,
                          fg=(T.TXT if i == 2 else T.TXT4), anchor="w")
            lb.pack(side="left")
            self._brand_labels.append(lb)
        # 副标用小号等宽字，左缘与品牌名对齐（不缩进）。
        self.brand_sub = tk.Label(names, text="RESEARCH ATLAS", bg=T.SIDEBAR,
                                  fg=T.TXT4, anchor="w")
        self.brand_sub.pack(fill="x")
        # 首帧 names 还没被布局（宽度是 1），所以先按侧栏宽度估一档，
        # 等 <Configure> 带来真实宽度再用 _fit_brand 重排。
        self._fit_brand(max(80, T.SIDEBAR_W - 2 * T.sp(16) - 34 - T.sp(9)))
        names.bind("<Configure>",
                   lambda e: self._fit_brand(e.width), add="+")

        # 搜索框只在聚焦时出现 —— 常驻一个输入框会把侧栏压成「两个区域」，
        # 而它在 99% 的时间里是空的。点放大镜或按 Ctrl+K 才落下来。
        self.search_wrap = tk.Frame(shell, bg=T.SIDEBAR)
        box = tk.Frame(self.search_wrap, bg=T.CARD_HI, highlightthickness=0)
        box.pack(fill="x")
        self.search = tk.Entry(box, bg=T.CARD_HI, fg=T.TXT, insertbackground=T.ACCENT,
                               relief="flat", font=T.F(9), width=14,
                               highlightthickness=0, bd=0)
        self.search.pack(side="left", fill="x", expand=True, ipady=5, padx=(10, 6))
        self.search.insert(0, "搜索文献")
        self.search.config(fg=T.TXT4)
        self.search.bind("<FocusIn>", self._s_in)
        self.search.bind("<FocusOut>", self._s_out)
        self.search.bind("<Return>", lambda e: self.global_search())
        self.search.bind("<Escape>", lambda e: self.hide_search())

        # 导航区吃掉剩余高度，底部的空白留给「下一屏还没到」的感觉，而不是把
        # 12 个条目挤成一团。
        self.nav_box = tk.Frame(shell, bg=T.SIDEBAR)
        # 导航不再立刻 pack：底部索引卡先占位，nav_box 再吃剩下的高度。
        # 反过来 pack 时，expand 的导航区会把底卡挤出窗口下沿。
        self.nav_box.bind("<Configure>",
                          lambda e: self.after(30, self._fit_nav), add="+")
        self.nav_items = {}
        # 组标题控件留给 _fit_nav() 改上留白（见 _nav_group_pad）。
        self._nav_group_labels = []
        # 导航项不再用「一个 Unicode 字形冒充图标」—— 那是把这套界面做虚的主要原因。
        #
        # 2026-11-15 第 7 版按参考图重排：
        #   · 分组保留（12 项一列到底确实难扫），但组标题更小更弱、段前距从 22 收到 16；
        #   · 条目左侧一个 4px 小圆点，文字缩进 22px，组标题与文字左对齐；
        #   · 侧栏宽 200（原 216），内边距 8，行高 34。
        groups = (
            (None, (("home", "总览"),)),
            ("选题与研究", (("topic", "选题工坊"), ("gap", "文献空白"),
                            ("latest", "最新研究"), ("ideas", "创新点库"))),
            ("方法与资源", (("skills", "科研方法论"), ("mentor", "导师与院校"),
                            ("venue", "期刊会议"))),
            ("知识资产", (("materials", "素材库"), ("library", "文献库"),
                          ("map", "方向图谱"))),
            ("个人", (("plan", "研究计划"), ("profile", "个人画像"),
                     ("settings", "设置与数据"))),
        )
        for label, items in groups:
            if label:
                # 组标题 11px 小字 + 上方 12px 留白：靠「小 + 弱 + 留白」
                # 分层，不靠拉大字号（那会和下面的条目抢视线）。
                # 第 20 版「分散开一些」：留白只加在分组之间（上 12 / 下 2），
                # 行高则交给 _fit_nav() 按窗口余量自适应 —— 往行高里塞间距
                # 会把 13 行撑出窗口，最后一行被页脚压住。
                _gl = tk.Label(self.nav_box, text=label, bg=T.SIDEBAR, fg=T.TXT4,
                               font=(T.BASE, -14), anchor="w")
                _gl.pack(fill="x", padx=12, pady=(T.sp(9), 0))
                # 记下紧接着要创建的那一行，矮窗口隐藏组标题后靠它恢复顺序
                _gl._nav_after = None
                self._nav_group_labels.append(_gl)
            for key, name in items:
                cv = self._nav_item(key, name)
                # 本组第一行就是最近那个还在等后继的组标题的后继
                for gl in self._nav_group_labels:
                    if getattr(gl, "_nav_after", "x") is None:
                        gl._nav_after = cv
                        break

        # 侧栏底部索引卡（网页版 .sidebar-foot）：两个规模数字 + 运行状态。
        # 数字在后台线程里数一遍，数不到就保持「—」，不拖慢启动。
        # 卡片只做「索引」，不抢导航高度：数字 18px、说明 13px，
        # 整卡控制在 110px 左右，1440×900 下也放得下 14 个条目。
        self.foot_card = T.Card(shell, bg=T.CARD, border=T.LINE_SOFT,
                                radius=T.RADIUS, pad=T.sp(10))
        self.foot_card.pack(side="bottom", fill="x", padx=T.sp(12),
                            pady=(T.sp(8), T.sp(12)))
        fb = self.foot_card.body
        grid = tk.Frame(fb, bg=T.CARD)
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1, uniform="fs")
        grid.grid_columnconfigure(1, weight=1, uniform="fs")
        self._foot_dir = self._foot_stat(grid, 0, "—", "个方向")
        self._foot_pap = self._foot_stat(grid, 1, "—", "篇本地文献")
        T.hsep(fb, color=T.LINE_SOFT, pad=(0, T.sp(5)))
        line = tk.Frame(fb, bg=T.CARD)
        line.pack(fill="x")
        dot = tk.Canvas(line, width=T.sp(6), height=T.sp(6), bg=T.CARD,
                        highlightthickness=0, bd=0)
        dot.pack(side="left", pady=(T.sp(3), 0))
        dot.create_oval(0, 0, T.sp(6), T.sp(6), fill=T.OK, outline="")
        tk.Label(line, text="LOCAL INDEX · 离线计算", bg=T.CARD, fg=T.TXT4,
                 font=(T.BASE, -13)).pack(side="left", padx=(T.sp(5), 0))
        tk.Label(fb, text="%s · 桌面版" % VERSION, bg=T.CARD, fg=T.TXT4,
                 font=(T.BASE, -13), anchor="w").pack(fill="x",
                                                      pady=(T.sp(2), 0))
        self.nav_box.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        self.after(900, self._warm_foot_stats)

        # 右侧主体
        main = tk.Frame(self, bg=T.BG)
        main.pack(side="left", fill="both", expand=True)
        self.main = main
        # 页脚状态条先 pack，保证它永远在最下面（pack 顺序 = 屏幕顺序）
        self.status = tk.Label(main, text="就绪", bg=T.BG, fg=T.TXT4, font=T.F(8), anchor="e")
        self.status.pack(side="bottom", fill="x", padx=14, pady=(0, 3))
        self.status_bar = tk.Frame(main, bg=T.LINE_SOFT, height=1)
        self.status_bar.pack(side="bottom", fill="x", padx=0)

        self._header(main, None, "")
        self.host = tk.Frame(main, bg=T.BG)
        self.host.pack(fill="both", expand=True, after=self._header_frame)

        # 导航历史：侧边栏只能「跳」，跳多了就回不去。
        # 每次 goto 记一条 (key, kw)，工具栏的 ← / → 在这里走。
        self.history = []
        self.hist_pos = -1
        self._hist_quiet = False
        self._title_of = {
            "home": "总览", "topic": "选题工坊", "gap": "文献空白",
            "latest": "最新研究", "ideas": "创新点库", "skills": "科研方法论",
            "mentor": "导师与院校", "venue": "期刊会议", "materials": "素材库",
            "library": "文献库",
            "map": "方向图谱", "plan": "研究计划",
            "profile": "个人画像", "settings": "设置与数据",
        }
        # 鼠标侧键也能后退/前进（键盘 Alt+← / Alt+→ 同理）
        try:
            self.bind_all("<Button-4>", lambda e: self.nav_back())
            self.bind_all("<Button-5>", lambda e: self.nav_forward())
            self.bind_all("<Alt-Left>", lambda e: self.nav_back())
            self.bind_all("<Alt-Right>", lambda e: self.nav_forward())
            self.bind_all("<Control-Shift-KeyPress-L>", lambda e: self.toggle_theme())
            self.bind_all("<Control-KeyPress-k>", lambda e: self.show_search())
            # 字号：Ctrl+= 放大一格，Ctrl+- 缩小一格。用 bind_all 是因为焦点
            # 常在输入框里，不绑到全局就只在那几个控件上有效。
            for seq, d in (("<Control-equal>", 1), ("<Control-plus>", 1),
                           ("<Control-KP_Add>", 1), ("<Control-minus>", -1),
                           ("<Control-KP_Subtract>", -1)):
                self.bind_all(seq, lambda e, _d=d: (self.step_font(_d), "break")[1])
        except Exception:
            pass

        # 日志抽屉
        self.log_frame = tk.Frame(main, bg=T.CARD, height=0)
        self.log_title = tk.Frame(self.log_frame, bg=T.CARD)
        self.log_title.pack(fill="x")
        tk.Label(self.log_title, text="运行日志", bg=T.CARD, fg=T.TXT3, font=T.F(8, True)).pack(
            side="left", padx=10, pady=3)
        close = tk.Label(self.log_title, text="收起 ✕", bg=T.CARD, fg=T.TXT4, font=T.F(8),
                         cursor="hand2")
        close.pack(side="right", padx=10)
        close.bind("<Button-1>", lambda e: self.hide_log())
        self.log_text = tk.Text(self.log_frame, height=7, bg=T.CARD, fg=T.TXT2, relief="flat",
                                font=T.M(8), padx=10, pady=4, wrap="word",
                                insertbackground=T.ACCENT)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_config("ok", foreground=T.OK)
        self.log_text.tag_config("err", foreground=T.ERR)
        self.log_text.tag_config("warn", foreground=T.WARN)
        self.log_text.config(state="disabled")
        self._log_open = False

    def _foot_stat(self, grid, col, value, label):
        box = tk.Frame(grid, bg=T.CARD)
        box.grid(row=0, column=col, sticky="w")
        v = tk.Label(box, text=value, bg=T.CARD, fg=T.TXT,
                     font=(T.MONO, -18, "bold"), anchor="w")
        v.pack(anchor="w")
        tk.Label(box, text=label, bg=T.CARD, fg=T.TXT4,
                 font=(T.BASE, -13), anchor="w").pack(anchor="w")
        return v

    def _warm_foot_stats(self):
        """侧栏索引卡的数字：方向总数 / 本地 PDF 数，后台数完再填。"""
        def work():
            nd = None
            np_ = None
            try:
                lib = kb.load_direction_library() or {}
                nd = sum(len(v.get("subs") or []) for v in lib.values())
            except Exception:
                pass
            try:
                inv = kb._inventory()
                files = (inv.get("files", []) if isinstance(inv, dict)
                         else (inv or []))
                np_ = 0
                for f in files:
                    if isinstance(f, (tuple, list)) and len(f) >= 3:
                        p = str(f[2])
                    elif isinstance(f, dict):
                        p = str(f.get("path", ""))
                    else:
                        continue
                    if p.lower().endswith(".pdf"):
                        np_ += 1
            except Exception:
                pass

            def apply():
                try:
                    if nd:
                        self._foot_dir.config(text="{:,}".format(nd))
                    if np_ is not None:
                        self._foot_pap.config(text="{:,}".format(np_))
                except Exception:
                    pass
            self.post(apply)
        threading.Thread(target=work, daemon=True).start()

    def _fit_brand(self, avail):
        """按品牌名容器的真实宽度，给三段挑一档放得下的字号。

        2026-11-19：品牌名从两行改成一整行后，宽度是真的会溢出的 ——
        Tk 的 Label 没有省略号，超出的字直接消失（「塞莎特——题」少了「谱」）。
        而这台机器上 `_SCALE`（系统 DPI 1.25）和 `_FS`（字号档 1.15）会叠乘，
        声明 13px 实际落到 19px，侧栏同时被放大到 236 —— 两边都在动，
        写死任何像素数都不安全。所以**先量再挑**：主名从大往小试，
        第一个三段合计放得下的就用它；女神名比主名小三档，不低于 13px 下限。
        同一档位不重复重排（<Configure> 会反复来）。
        """
        try:
            from tkinter import font as _tkfont
            avail = int(avail)
            if avail <= 60:
                return
            base = int(round(15 * T._FS))
            pick = None
            for main_px in range(base + 4, 9, -1):
                name_px = max(13, main_px - 3)
                f_main = _tkfont.Font(family=T.SERIF, size=-main_px, weight="bold")
                f_name = _tkfont.Font(family=T.SERIF, size=-name_px, weight="bold")
                w = (f_name.measure("塞莎特") + f_name.measure(" —— ")
                     + f_main.measure(APP_TITLE_SHORT))
                if w <= avail:
                    pick = (name_px, main_px)
                    break
            if pick is None:
                # 极小窗口/超大系统字号：退回两行时代的尺寸，
                # 至少保证主名完整可读。
                pick = (13, 15)
            sub_px = 11
            while sub_px > 8:
                if _tkfont.Font(family=T.MONO,
                                size=-sub_px).measure("RESEARCH ATLAS") <= avail:
                    break
                sub_px -= 1
            if pick == getattr(self, "_brand_px", None) and abs(
                    avail - getattr(self, "_brand_avail", -999)) < 2:
                return
            self._brand_px = pick
            self._brand_avail = avail
            for i, lb in enumerate(self._brand_labels):
                px = pick[1] if i == 2 else pick[0]
                lb.configure(font=(T.SERIF, -px, "bold"))
            self.brand_sub.configure(font=(T.MONO, -sub_px))
        except Exception:
            pass

    def _fit_nav(self):
        """按 nav_box 的实际高度把导航行高与组间距拉开（窗口尺寸明显变化时才重排）。

        2026-11-19：布局改动（行高、组标题显隐、组间距）统一在这里执行一次，
        不在 `_nav_metrics` 里边算边改 —— 那样下一轮读到的还是旧的映射状态，
        组标题会一半显示一半隐藏（实测 1152×740 下只剩 1 个标题）。
        """
        try:
            h, pad = self._nav_metrics()
            want_heads = bool(getattr(self, "_nav_want_heads", True))
        except Exception:
            return
        heads = getattr(self, "_nav_group_labels", []) or []
        heads_now = any(gl.winfo_ismapped() for gl in heads) if heads else True
        if (h == getattr(self, "_nav_h", None)
                and pad == getattr(self, "_nav_pad", None)
                and want_heads == heads_now):
            return
        self._nav_h = h
        self._nav_pad = pad
        self._set_group_head_visible(want_heads)
        for key, (cv, lb, icon, bar) in list(getattr(self, "nav_items", {}).items()):
            try:
                cv.configure(height=h)
                # 文字与图标都靠 _paint_nav 重画（它按 cv 当前高度算圆心）
                self._paint_nav(key)
            except Exception:
                pass
        if want_heads:
            for gl in heads:
                try:
                    gl.pack_configure(pady=(pad, 0))
                except Exception:
                    pass

    def _nav_metrics(self):
        """一次算出行高与组间距，返回 `(row_h, group_pad)`。

        2026-11-19：原来行高与组间距分别读对方的输出，形成循环依赖 ——
        改行高 → 间距变 → 行高再变，实测在 1440 下算出 684 > 655，
        最后一行被压成 7px。现在**一个函数算两件事**，只读真实控件尺寸，
        不回头读自己写出去的值。

        分配顺序（余量按这个优先级给）：
          1. 行高先到 33px 这个舒适值，不够就往下压（最低 24）；
          2. 剩下的余量平均分给 4 个组标题的上留白（最低 6px，最高 26）；
          3. 还剩下就都给行高（封顶 38）。
        """
        try:
            nb = self.nav_box.winfo_height()
        except Exception:
            nb = 0
        rows = len(getattr(self, "nav_items", {}) or range(14))
        groups = len(getattr(self, "_nav_group_labels", []) or range(4))
        try:
            head = max(int(gl.winfo_reqheight())
                       for gl in self._nav_group_labels)
        except Exception:
            head = 26
        rows = max(1, rows)
        groups = max(1, groups)
        if nb <= 60:                       # 首帧还没布局
            return self._nav_base(), T.sp(9)
        # 2026-11-19 修：上一版把 pady 算了两遍（先 -2 再 +2），
        # 加上组标题的上留白漏算，1440 下算出 672 > 655，最后一行被压成 17px。
        # 现在直接解方程：nb = rows*(row_h + ROW_PAD) + groups*(head + pad) + BREATH
        ROW_PAD = 2      # cv.pack(pady=1) 上下各 1
        BREATH = 8       # 底部留一点，不贴住状态栏
        gap_min = T.sp(6)
        # 矮窗口放不下「组标题 + 间距」这一套时的降级：隐藏组标题，只靠留白分组。
        # 1080×680（应用的最小尺寸）nav_box 只有 435px，14 行 × 24 就要
        # 336，加 4 个组标题 128 已经 464 —— 装不下，必须降级。
        # 注意：**这里只算数，不改布局**。改布局放在 _fit_nav 里一次做完，
        # 否则在算的过程中 pack/pack_forget，下一轮读到的还是旧的映射状态，
        # 组标题会一半显示一半隐藏。
        self._nav_want_heads = (nb >= rows * (24 + ROW_PAD)
                                + groups * (head + gap_min) + BREATH)
        if not self._nav_want_heads:
            room = nb - BREATH
            row_h = max(22, min(38, int(room / float(rows)) - ROW_PAD))
            return row_h, T.sp(4)
        # 第一轮：间距取下限，把剩下的全给行高
        room = nb - BREATH - groups * (head + gap_min)
        row_h = max(24, min(38, int(room / float(rows)) - ROW_PAD))
        # 第二轮：行高封顶后，把真正的余量平均分给组间距
        spare = nb - BREATH - rows * (row_h + ROW_PAD) - groups * head
        pad = gap_min + max(0, min(int(spare / float(groups)) - 0, T.sp(20)))
        # 再校一次：总高不能超过 nb，超了就把间距压回去
        while groups * pad > 0 and (rows * (row_h + ROW_PAD)
                                    + groups * (head + pad) + BREATH) > nb:
            pad -= 1
        return row_h, max(gap_min, pad)

    def _set_group_head_visible(self, on):
        """矮窗口下隐藏分组标题，改用留白分组。

        2026-11-19：**不要用状态缓存**。上一版用 `_nav_head_on` 记状态，
        但第一次调用时 `_nav_group_labels` 还没填满（构建过程中就会调到这里），
        结果只隐藏了一部分，后续又因为缓存命中直接 return，
        1152×740 下第一组标题一直留在里面，reqh 600 > nav_box 495。
        现在每次都按「实际是否已映射」校正，幂等且不怕半途状态。
        """
        labels = getattr(self, "_nav_group_labels", []) or []
        for gl in labels:
            try:
                shown = bool(gl.winfo_ismapped()) and gl.winfo_manager() == "pack"
                if on and not shown:
                    # 恢复到「紧跟上一组最后一行之后」的位置：用记下的后继锚点
                    nxt = getattr(gl, "_nav_after", None)
                    if nxt is not None and nxt.winfo_exists():
                        gl.pack(fill="x", padx=12, pady=(T.sp(9), 0),
                                before=nxt)
                    else:
                        gl.pack(fill="x", padx=12, pady=(T.sp(9), 0))
                elif not on and gl.winfo_manager() == "pack" and shown:
                    gl.pack_forget()
            except Exception:
                pass

    def _nav_base(self):
        """首帧还没有容器尺寸时用的保底行高。"""
        return 34 if T.font_scale() <= 1.0 else 36

    def _nav_row_height(self):
        """导航行高（单一数据源：`_nav_metrics`）。"""
        return self._nav_metrics()[0]

    def _nav_group_pad(self):
        """组标题上方留白（单一数据源：`_nav_metrics`）。"""
        return self._nav_metrics()[1]

    def _nav_text_x(self):
        """条目文字的左边界：留出 10px 边距 + 16px 图标 + 8px 间隔。"""
        return 38 if not getattr(self, "_nav_compact", False) else 34

    def _nav_item(self, key, name):
        """一个导航项：整行 34px，选中/悬停是一整块圆角浅灰底。

        2026-11-15 参照用户给的 DSH 侧栏截图重做：
          · 去掉左侧 2px 强调竖条 —— 一列里十几条竖线在选中项上只露一根，
            眼睛要靠「线」去定位，扫视成本高；
          · 选中改为整块圆角底（不反白、不改字色权重），靠「块」定位，
            和 GitHub / Linear / DSH 的侧栏一致；
          · 行高 30 → 34，行间留 2px，组间距 18 → 22。
        圆角用 Canvas 画：Tk 的 Frame 只能画直角，而直角块在 34px 的行高上
        会显得生硬；Canvas 的 `_round_rect` 是现成的（主题切换时重建即可）。
        """
        # 第 20 版「分散开一些」：建窗口时 nav_box 还没分配高度，
        # 这里先用保底行高；高度定下来后再由 _fit_nav() 一次性重排，
        # 不然量到的是 1px，永远落到最低档。
        row_h = self._nav_row_height()
        cv = tk.Canvas(self.nav_box, bg=T.SIDEBAR, height=row_h,
                       highlightthickness=0, bd=0, cursor="hand2")
        cv.pack(fill="x", pady=1)
        # 2026-11 第 7 版：项目符号换成**画出来的图标**（app_icons）。
        # 图标放在同一个 Canvas 上，由 _paint_nav 一并重画/重着色；
        # 这样悬停和选中时图标能和文字一起变亮，不需要管理额外的控件。
        lb = cv.create_text(self._nav_text_x(), row_h // 2, text=name, anchor="w",
                            fill=T.TXT2, font=T.F(10))
        self.nav_items[key] = (cv, lb, key, None)
        cv.bind("<Button-1>", lambda e, k=key: self.goto(k))
        cv.bind("<Enter>", lambda e, k=key: self._nav_hover(k, True))
        cv.bind("<Leave>", lambda e, k=key: self._nav_hover(k, False))
        # 宽度变化时重画：圆角块的右边界要跟着容器走
        cv.bind("<Configure>", lambda e, k=key: self._paint_nav(k))
        self._paint_nav(key, fresh=True)
        return cv          # 供外层记录组标题的恢复锚点

    def _paint_nav(self, key, fresh=False):
        """按当前状态重画一行：底色块 + 图标 + 文字。状态取自 self.current。"""
        item = self.nav_items.get(key)
        if not item:
            return
        cv, lb, icon_name, _bar = item
        # 2026-11 第 7 版：选中态改成**品牌色浅底**（参考图里就是蓝色浅块）。
        # 上一版用中性灰块，在一片灰的界面里，选中和悬停几乎分不出来。
        # 蓝色浅底在深色下是「暗蓝」，在浅色下是「淡蓝」，两套都由 tint() 按
        # 当前主题从 ACCENT 推出来，不会撞色。
        try:
            w = cv.winfo_width()
            if w <= 1:
                # 首帧 Canvas 还没被布局，winfo_width() 返回 1。不能拿
                # SIDEBAR_W 当宽度 —— nav_box 自己还有 padx=8，算出来会多出
                # 16px，圆角块直接画到侧栏外面。
                w = max(60, T.SIDEBAR_W - 16)
            h = int(cv.cget("height"))
            on = (key == self.current)
            hover = bool(getattr(self, "_hover_key", None) == key)
            # 清掉上一次画的色块和图标图元（文字和图标都是本行自己的，
            # 图标每次重画，所以除了文字全删）
            for i in cv.find_all():
                if i != lb:
                    cv.delete(i)
            cv.coords(lb, self._nav_text_x(), h // 2)
            fg = T.ACCENT if on else (T.TXT2 if hover else T.TXT3)
            if on or hover:
                # 网页版选中项是「暖白圆角块 + 细描边」，没有左侧竖条；
                # 悬停项是同色系浅底。桌面端照此重画。
                if on:
                    fill, line = T.CARD, T.LINE
                else:
                    fill = T.tint(T.ACCENT, 0.08, T.SIDEBAR)
                    line = fill
                ids = T._round_rect(cv, 0, 1, w - 1, h - 2, 10,
                                    fill=fill, outline=line)
                for i in ids:
                    cv.tag_lower(i)
            # 图标：18px，垂直居中，左边距 10
            I.draw_on(cv, icon_name, size=17,
                      fg=(T.ACCENT if on else fg),
                      x=12, y=(h - 17) // 2)
            # 选中时文字用正文色（不是品牌色），保证对比度与扫视清晰度
            cv.itemconfig(lb, fill=(T.TXT if on else T.TXT2),
                          font=(T.F(10, True) if on else T.F(10)))
        except Exception as exc:
            import sys
            print("[nav] %s 画失败：%r" % (key, exc), file=sys.stderr)

    def _nav_hover(self, key, on):
        if key == self.current:
            return
        self._hover_key = key if on else None
        self._paint_nav(key)

    def _set_nav(self, key):
        for k in self.nav_items:
            self._paint_nav(k)
        try:
            name = self._title_of.get(key, key)
            self.crumb.config(text=APP_TITLE + " / %s" % name)
        except Exception:
            pass

    # ------------------------------------------------------------ 页面切换
    def page(self, key):
        if key not in self.pages:
            factory = {
                "home": lambda: HomePage(self.host, self),
                "topic": lambda: TopicPage(self.host, self),
                "ideas": lambda: IdeasPage(self.host, self),
                "gap": lambda: GapPage(self.host, self),
                "latest": lambda: LatestPage(self.host, self),
                "skills": lambda: SkillsPage(self.host, self),
                "map": lambda: MapPage(self.host, self),
                "mentor": lambda: MentorPage(self.host, self),
                "venue": lambda: VenuePage(self.host, self),
                "materials": lambda: MaterialsPage(self.host, self),
                "library": lambda: LibraryPage(self.host, self),
                "plan": lambda: PlanPage(self.host, self),
                "profile": lambda: ProfilePage(self.host, self),
                "settings": lambda: SettingsPage(self.host, self),
            }[key]
            self.pages[key] = factory()
            # 各页的竖向边距是历史遗留的手写值，这里统一收敛到 4px 网格
            try:
                T.normalize_page_spacing(self.pages[key])
            except Exception:
                pass
        return self.pages[key]

    def goto(self, key, _record=True, **kw):
        try:
            pg = self.page(key)
        except Exception as exc:
            self.toast("页面加载失败：" + str(exc), T.ERR)
            kb._log_exc(type(exc), exc, exc.__traceback__)
            return
        if _record and (not self.history or key != self.current):
            # 只在「真的换了页」时记历史：同一个页面刷新参数不该产生重复条目
            self.history = self.history[:self.hist_pos + 1]
            self.history.append((key, dict(kw)))
            self.hist_pos = len(self.history) - 1
            if len(self.history) > 60:
                self.history.pop(0)
                self.hist_pos -= 1
        # 联想下拉是置顶的独立窗口，不随页面隐藏，切页统一收起
        try:
            import app_suggest
            app_suggest.close_all()
        except Exception:
            pass
        for k, p in self.pages.items():
            if k != key:
                p.pack_forget()
                # 离开页面时把它弹出的二级窗口一并收掉 —— 否则窗口还在，
                # 底下那个页面已经看不见了，点它的「确定」全是副作用。
                T.close_child(p)
                T.close_child(p, "_search_win")
                T.close_child(p, "_child_win")
        pg.pack(fill="both", expand=True)
        # 必须先落 current 再重画导航：_paint_nav 是按 self.current 判断
        # 选中态的，早先写的是先 _set_nav 后 self.current = key，画出来的
        # 永远是「上一页」高亮（截图里停在导师页时侧栏还亮着总览）。
        self.current = key
        self._set_nav(key)
        if key == "home" and hasattr(pg, "reload"):
            pg.reload()
        if key == "ideas" and hasattr(pg, "reload"):
            pg.reload()
        if key == "profile" and hasattr(pg, "reload"):
            # 记忆随时可能被别处写入（存创新点时、手势埋点），切回来要重读
            pg.reload()
        if key == "mentor" and kw.get("field"):
            pg.set_context(kw.get("cat", ""), kw["field"])
        if key == "venue" and kw.get("field"):
            pg.set_context(kw.get("cat", ""), kw["field"])
        # 有些页在 reload 里会把主体重新 pack 一遍（例如 ideas 的空态与列表
        # 互换），那会把创建时对齐好的 pady 又改回去，所以切页后再对齐一次。
        try:
            T.normalize_page_spacing(pg)
        except Exception:
            pass
        self._update_nav_ui(key, kw)

    # ------------------------------------------------------------ 前进 / 后退
    def _update_nav_ui(self, key, kw):
        """顶栏面包屑：`塞莎特——题谱 / 选题工坊`，多层跳转时只留最近三步。"""
        try:
            stack = [self._title_of.get(k, k)
                     for k, _ in self.history[:self.hist_pos + 1]]
            if len(stack) > 3:
                stack = ["…"] + stack[-2:]
            self.crumb.config(text=APP_TITLE + " / " + " / ".join(stack))
            can_back = self.hist_pos > 0
            can_fwd = self.hist_pos < len(self.history) - 1
            self.btn_back.config(fg=T.TXT2 if can_back else T.TXT4,
                                 cursor="hand2" if can_back else "arrow")
            self.btn_fwd.config(fg=T.TXT2 if can_fwd else T.TXT4,
                                cursor="hand2" if can_fwd else "arrow")
        except Exception:
            pass

    def nav_back(self):
        if self.hist_pos <= 0:
            return
        self.hist_pos -= 1
        key, kw = self.history[self.hist_pos]
        self.goto(key, _record=False, **kw)

    def nav_forward(self):
        if self.hist_pos >= len(self.history) - 1:
            return
        self.hist_pos += 1
        key, kw = self.history[self.hist_pos]
        self.goto(key, _record=False, **kw)

    def _reload_home(self):
        if self.current == "home" and "home" in self.pages:
            self.pages["home"].reload()

    def mark_dirty(self, key):
        if key in self.pages and hasattr(self.pages[key], "reload"):
            self.pages[key].reload()

    # ------------------------------------------------------------ 搜索
    def _s_in(self, _e=None):
        if self.search.get() == "搜索文献":
            self.search.delete(0, "end")
            self.search.config(fg=T.TXT)

    def _s_out(self, _e=None):
        if not self.search.get().strip():
            self.search.delete(0, "end")
            self.search.insert(0, "搜索文献")
            self.search.config(fg=T.TXT4)

    def show_search(self):
        """把搜索框放下来（替换掉占位那一行），并聚焦。"""
        try:
            # 搜索按钮现在在品牌行里，**不能** pack_forget —— 它一消失标题就会左移。
            self.search_wrap.pack(fill="x", padx=10, pady=(2, 4),
                                  after=self.brand_box)
            self.search.focus_set()
            self.search.select_range(0, "end")
        except Exception:
            pass

    def hide_search(self):
        try:
            if not self.search.get().strip() or self.search.get() == "搜索文献":
                self.search_wrap.pack_forget()
        except Exception:
            pass

    def global_search(self):
        q = self.search.get().strip()
        if not q or q == "搜索文献":
            return
        try:
            # 先从文件名搜（快），再补全文搜（能搜到正文里的方法名、数据集）
            name_hits = kb.search_kb(q, limit=2000)
            full_hits = []
            try:
                import fulltext
                full_hits = fulltext.search(q, limit=2000)
            except Exception:
                full_hits = []
        except Exception as exc:
            self.toast("搜索失败：" + str(exc), T.ERR)
            return

        # 合并去重：文件名命中的优先，正文命中的作为补充
        seen = set()
        hits = []
        for h in name_hits:
            p = h.get("path")
            if p in seen:
                continue
            seen.add(p)
            hits.append({"path": p, "name": h.get("name", ""),
                         "cat": h.get("cat", ""), "where": "文件名", "snippet": ""})
        for h in full_hits:
            p = h.get("path")
            if p in seen:
                continue
            seen.add(p)
            hits.append({"path": p, "name": h.get("name", ""),
                         "cat": h.get("cat", ""), "where": h.get("where", "正文"),
                         "snippet": h.get("snippet", "")})
        # 文件名命中的排前面
        hits.sort(key=lambda x: 0 if x["where"] == "文件名" else 1)

        T.close_child(self, "_search_win")
        win = T.child_window(self, "搜索 · " + q, "900x640")
        self._search_win = win
        tk.Label(win, text="搜索「%s」" % q, bg=T.BG, fg=T.TXT,
                 font=T.T_TITLE()).pack(anchor="w", padx=18, pady=(16, 2))
        n_name = sum(1 for h in hits if h["where"] == "文件名")
        n_text = len(hits) - n_name
        tk.Label(win, text="共 %d 篇（文件名 %d · 正文 %d），点击打开 PDF"
                 % (len(hits), n_name, n_text),
                 bg=T.BG, fg=T.TXT3, font=T.F(9)).pack(anchor="w", padx=18, pady=(0, 10))
        sa = T.ScrollArea(win)
        sa.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        if not hits:
            tk.Label(sa.inner, text="没有命中。可以换关键词，或到文献库用分类筛选。",
                     bg=T.BG, fg=T.TXT4, font=T.F(10)).pack(pady=36)

        shown = [0]
        BATCH = 60

        def render_next():
            start = shown[0]
            end = min(len(hits), start + BATCH)
            for h in hits[start:end]:
                f = tk.Frame(sa.inner, bg=T.CARD, cursor="hand2")
                f.pack(fill="x", pady=1)
                # 先放右侧固定宽度的标记，再让标题占剩余空间。
                # 反过来（标题 expand 在前）会把标记挤出可视区。
                colr = T.ACCENT if h["where"] == "文件名" else T.PURPLE
                tk.Label(f, text=h["where"], bg=T.CARD, fg=colr, font=T.F(8),
                         padx=6, anchor="e").pack(side="right")
                cat = h.get("cat", "") or ""
                if len(cat) > 8:
                    cat = cat[:7] + "…"
                tk.Label(f, text=cat, bg=T.CARD, fg=T.TXT3, font=T.F(8),
                         padx=4, anchor="w").pack(side="right", padx=(0, 6))
                inner = tk.Frame(f, bg=T.CARD)
                inner.pack(side="left", fill="x", expand=True, padx=10, pady=5)
                tk.Label(inner, text=h.get("name", ""), bg=T.CARD, fg=T.TXT2,
                         font=T.F(9), anchor="w").pack(fill="x")
                if h.get("snippet"):
                    tk.Label(inner, text=h["snippet"], bg=T.CARD, fg=T.TXT4,
                             font=T.F(8), anchor="w", justify="left").pack(fill="x")
                f.bind("<Button-1>", lambda e, p=h["path"]: os.startfile(p))
            shown[0] = end
            if btn[0] is not None:
                btn[0].destroy()
                btn[0] = None
            if end < len(hits):
                btn[0] = T.Btn(sa.inner, "加载更多（已显示 %d / %d）" % (end, len(hits)),
                               render_next, "ghost")
                btn[0].pack(pady=10)
            sa.refresh(defer=True)

        btn = [None]
        render_next()

    # ------------------------------------------------------------ 工具
    def log(self, msg, color=None, force_open=False):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        tag = ""
        if color == T.OK:
            tag = "ok"
        elif color == T.ERR:
            tag = "err"
        elif color == T.WARN:
            tag = "warn"
        self._log_lines.append((ts, msg, tag))
        self.log_text.config(state="normal")
        first = "\n" if self.log_text.index("end-1c") != "1.0" else ""
        self.log_text.insert("end", first + "%s  %s" % (ts, msg), tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        if force_open:
            self.show_log()

    def show_log(self):
        if self._log_open:
            return
        self.log_frame.pack(side="bottom", fill="x")
        self.log_frame.config(height=150)
        self._log_open = True

    def hide_log(self):
        self.log_frame.pack_forget()
        self._log_open = False

    def toast(self, msg, color=T.ACCENT):
        try:
            self.status.config(text="● " + str(msg)[:160], fg=color)
            self.after(6000, lambda: self.status.config(text="● 就绪", fg=T.TXT4))
        except Exception:
            pass

    def idle(self, msg=""):
        """往状态栏写一条「常驻」进度（检索中… 之类），不自动消失。

        给长任务的中间状态用：toast 6 秒就恢复「就绪」，
        而「正在全库检索」可能持续几十秒，中途被重置成「就绪」会让人以为点空了。
        传空字符串表示清除。
        """
        try:
            if msg:
                self.status.config(text="○ " + str(msg)[:160], fg=T.TXT3)
            else:
                self.status.config(text="● 就绪", fg=T.TXT4)
        except Exception:
            pass

    def copy(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def open_url(self, url):
        try:
            kb.webbrowser.open(url)
        except Exception as exc:
            self.toast("打开失败：" + str(exc), T.ERR)

    def post(self, fn):
        """后台线程把 UI 更新丢回主线程。

        窗口已关闭时直接丢弃：否则会在已销毁的 Tk 上执行回调，
        退出时抛 "application has been destroyed"。
        """
        if getattr(self, "_closing", False):
            return
        try:
            self.q.put(fn)
        except Exception:
            pass

    def _warm_search(self):
        """按用户真实搜索频率记录「常用词」，但不主动加载索引。

        历史：这段本来是「启动后把用户最常用的几条查询跑一遍，让索引驻留内存」。
        当时索引冷启动要 9.5 秒、常驻 1.2 GB，预热确实能省下用户第一次点击的等待。

        2026-11-14 换了索引存储格式（打包 meta.bin + mmap emb）之后，
        冷启动降到 0.2 秒、常驻 400 MB 左右，预热的收益已经小于它本身的代价：
        开机 4 秒后就在后台吃掉 400 MB，只为了「用户可能马上要搜」。
        现在改成什么都不做，只留这个方法名和调用点，
        真要恢复预热改 return 下面两行即可。

        真正还能用搜索习惯改进检索的地方是 `cold_terms()`
        （搜了但查不到的词 → 词表缺口），那属于索引构建期的事，不在这里做。
        """
        return
        # ---- 以下为旧的预热逻辑，保留作参考 ----
        try:
            import search_log
            warm = search_log.warm_terms(n=4)
        except Exception:
            return
        if not warm:
            return

        def work():
            try:
                import kb_vector
            except Exception:
                return
            for w in warm:
                # 多词交集模式走的是另一条路径（要加载全库正文），
                # 预热它会把内存顶到 100MB 以上，只在真的用过时才做
                if w["mode"] not in ("semantic", "file"):
                    continue
                try:
                    kb_vector.search(w["term"], k=3)
                except Exception:
                    continue

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        if getattr(self, "_closing", False):
            return
        try:
            while True:
                fn = self.q.get_nowait()
                try:
                    fn()
                except Exception as exc:
                    kb._log_exc(type(exc), exc, exc.__traceback__)
                    self.toast("运行出错：" + str(exc), T.ERR)
        except queue.Empty:
            pass
        # 窗口已销毁时不要再排下一轮，否则后台线程的任务会在
        # 已销毁的 Tk 上执行，退出时报 "application has been destroyed"
        try:
            if self.winfo_exists():
                self._poll_id = self.after(50, self._poll)
        except Exception:
            pass

    def destroy(self):
        """先停掉轮询和后台回调，再销毁窗口。

        不取消 after 定时器的话，Tk 会在销毁后仍触发一次 _poll，
        报 bgerror: invalid command name "..._poll"。
        """
        self._closing = True
        pid = getattr(self, "_poll_id", None)
        if pid:
            try:
                self.after_cancel(pid)
            except Exception:
                pass
            self._poll_id = None
        # 把队列里剩下的一次性回调丢掉：它们可能引用已销毁的控件
        try:
            while True:
                self.q.get_nowait()
        except Exception:
            pass
        try:
            super().destroy()
        except Exception:
            pass


def _detect_scale():
    """读取系统真实显示缩放（1.0 / 1.25 / 1.5 …）。

    注意：本进程未必声明了 DPI 感知，GetDpiForSystem 可能返回逻辑值 96，
    所以改读注册表里的 AppliedDPI（Windows 实际使用的缩放）。
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Control Panel\Desktop\WindowMetrics") as k:
            applied, _ = winreg.QueryValueEx(k, "AppliedDPI")
            return max(1.0, float(applied) / 96.0)
    except Exception:
        pass
    try:
        import ctypes
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi:
            return max(1.0, dpi / 96.0)
    except Exception:
        pass
    return 1.0


def _apply_font_scale(app):
    """按系统缩放调整全局字号，并按实际安装情况挑字体。

    **必须在建任何控件之前调用**：字号与字体在 Label 创建时就被写进
    控件的 font 选项，事后再改常量不会影响已经建好的控件。
    """
    factor = _detect_scale()
    T.set_scale(factor)
    # 字体族实测挑选：写死的等线/雅黑在本机并不存在，Tk 会静默回退，
    # 导致字形与字号度量不匹配、笔画发灰（浅色下尤其明显）。
    try:
        fams = T.pick_fonts(app)
        if fams:
            print("[font] 使用 %s / %s，可用字体 %d 个"
                  % (T.BASE, T.MONO, len(fams)))
    except Exception:
        pass
    # 让 Tk 内置控件（菜单、滚动条、Entry 默认字体）也用同一套像素字号
    try:
        import tkinter.font as tkfont
        for name, pt, bold in (("TkDefaultFont", 10, False),
                               ("TkTextFont", 10, False),
                               ("TkMenuFont", 10, False),
                               ("TkHeadingFont", 10, True)):
            try:
                f = tkfont.nametofont(name, root=app)
                f.configure(family=T.BASE, size=T.px(pt),
                            weight="bold" if bold else "normal")
            except Exception:
                pass
    except Exception:
        pass
    # 缩放变化后窗口最小尺寸也要跟着走，否则小屏上控件会挤在一起
    try:
        app.minsize(int(1080 * factor), int(680 * factor))
    except Exception:
        pass
    return factor


def main():
    # 打包态首次启动：把 config / research_memory 等可写文件从 _internal/seed
    # 拷到 exe 旁边，否则用户第一次存的选题会写进临时解压目录、退出即丢。
    # 开发态这里什么都不做（app_paths.DATA == 项目目录）。
    try:
        import app_paths
        app_paths.ensure_data()
    except Exception:
        pass
    try:
        kb._enable_dpi()
    except Exception:
        pass
    sys.excepthook = kb._log_exc
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())