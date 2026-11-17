#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向图谱页：24 大类 / 300+ 研究领域的可浏览目录 + 多维组合调研。

方向库与维度定义来自 kb_widget（directions_library / research_taxonomy /
research_relations），本页负责把它变成一个可点、可选、能出结论的界面。
"""
import tkinter as tk


import app_theme as T
from ui_parts import WrapRow   # 会自动折行的按钮排
import ui_parts as U
import app_widgets as widgets
import kb_widget as kb

PAGE_HINT = "24 大类 · 300+ 领域 · 场景 / 方法 / 任务 / 模态组合"

MAP_HELP = """\
这是一张静态的方向地图，不是实时的研究前沿。它回答的是「这个学科领域之间怎么挂靠」，
不回答「哪个最近在涨」。

一、三栏怎么用
· 左栏大类 → 中栏细分方向 → 右栏该方向下的场景 / 方法 / 任务 / 模态组合。
· 点一个细分方向，会给出去选题工坊和推荐导师的入口；点一个组合，会直接拿去文献空白页查。
· 「生成调研提示词」把这一整块打包成一段可复制的提问，丢给大模型让它替你梳理脉络。

二、为什么有些方向写「暂无学者」
不是没人做。是我们取学者时依赖 OpenAlex 的主题分类和 arXiv 的近三年倒推，
这两个来源的主题粒度很粗（比如把整片 3D/深度估计压成一个主题），
所以冷门细分会查不到人。387 个方向里大约有 50 个是这种情况。
想找这类方向的导师，直接去导师页按名字搜，或者按相邻方向查。

三、它的边界
词表是人工整理的 24 类 / 387 个细分 / 231 个三级组合，覆盖计算机为主、允许交叉。
它不会自动更新，也不会告诉你哪个方向正在变热——那要看文献最新页和文献空白页。"""


class MapPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.lib = {}
        self.tax = {}
        self.rels = {}
        self.cat = None
        self.field = None
        self.vars = {}
        self._build()
        self.after(80, self.reload)

    # ------------------------------------------------------------ 布局
    def _build(self):
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        self._hint = U.Hint(top, MAP_HELP, summary="这张图谱怎么用", bg=T.BG)
        self._hint.pack(side="left", fill="x", expand=True)
        self.count_lbl = tk.Label(top, text="", bg=T.BG, fg=T.TXT3,
                                  font=T.T_CAPTION())
        self.count_lbl.pack(side="right")

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=3, uniform="c")
        body.grid_columnconfigure(1, weight=3, uniform="c")
        body.grid_columnconfigure(2, weight=4, uniform="c")

        # 大类
        c1 = T.Card(body, pad=10)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        T.card_head(c1.body, "学科大类", "", bg=T.CARD).pack_configure(padx=2)
        self.cat_scroll = T.ScrollArea(c1.body, bg=T.CARD)
        self.cat_scroll.pack(fill="both", expand=True)

        # 领域
        c2 = T.Card(body, pad=10)
        c2.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        T.card_head(c2.body, "研究领域", "", bg=T.CARD).pack_configure(padx=2)
        self.field_head = tk.Label(c2.body, text="", bg=T.CARD, fg=T.ACCENT, font=T.T_BODY_SM(),
                                   anchor="w")
        self.field_head.pack(fill="x", padx=2, pady=(0, 4))
        self.field_scroll = T.ScrollArea(c2.body, bg=T.CARD)
        self.field_scroll.pack(fill="both", expand=True)
        # 未选大类时的空态：空面板比一句引导更让人以为「坏了」
        self.field_empty = tk.Label(self.field_scroll.inner,
                                    text="先在左侧点一个学科大类。", bg=T.CARD, fg=T.TXT3,
                                    font=T.T_BODY_SM(), anchor="w")

        # 组合
        c3 = T.Card(body, pad=12)
        c3.grid(row=0, column=2, sticky="nsew")
        # 卡头用「名称（一句话说明）」的统一格式：右栏是这一页唯一产出的地方，
        # 卡头写清它产出什么，比写「多维组合」四个字有用。
        T.card_head(c3.body, "多维组合", "选出场景 / 方法 / 任务 / 模态，生成调研问法",
                    bg=T.CARD).pack(fill="x", pady=(0, 6))
        self.combo_title = tk.Label(c3.body, text="", bg=T.CARD, fg=T.TXT2,
                                    font=T.T_BODY_SM(), anchor="w",
                                    justify="left", wraplength=T.wrap(340))
        self.combo_title.pack(fill="x", pady=(0, 4))
        self.relation_lbl = tk.Label(c3.body, text="", bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(),
                                     anchor="w", justify="left", wraplength=T.wrap(340))
        self.relation_lbl.pack(fill="x", pady=(0, 6))
        self.combo_scroll = T.ScrollArea(c3.body, bg=T.CARD)
        self.combo_scroll.pack(fill="both", expand=True)
        # 空态：一句「下一步点哪里」，点开哪个领域它自己就消失。
        # 原来是「一整片黑 + 中间一行灰字」，看着像页面坏了。
        # 注意：必须挂在 c3.body 上，不能挂 combo_scroll.inner ——
        # _render_combo() 会 combo_scroll.clear() 销毁 inner 的全部子控件，
        # 挂在里面的话空态第一次渲染后就永久消失（冒烟报 bad window path name）。
        self.combo_empty = U.EmptyState(
            c3.body, "先选一个具体领域",
            "在中间一栏点任意一个方向，这里会出现这个方向的场景 / 方法 / 任务 / 模态，"
            "勾选后右下角能生成调研问题。",
            bg=T.CARD)
        self.field_empty.pack(fill="x", pady=(2, 0), padx=2)
        self._act = tk.Frame(c3.body, bg=T.CARD)
        self._act_row = U.WrapRow(self._act)
        self._act_row.pack(fill="x")
        self._act_row.add(T.Btn(self._act_row, "生成调研提示词",
                                self.make_prompt, "primary"))
        self._act_row.add(T.Btn(self._act_row, "推荐导师", self.to_advisors))
        self._act_row.add(T.Btn(self._act_row, "推荐期刊会议", self.to_venues))
        # 一开始没有领域 → 先显示空态（而不是让右栏彻底空着）
        self._render_empty_combo()

    # ------------------------------------------------------------ 数据
    def reload(self):
        try:
            self.lib = kb.load_direction_library() or {}
            self.tax = kb.load_research_taxonomy() or {}
            self.rels = kb.load_research_relations() or {}
        except Exception as exc:
            self.app.toast("加载方向库失败：" + str(exc), T.ERR)
            return
        n_fields = sum(len(v.get("subs", [])) for v in self.lib.values())
        self.count_lbl.config(text="%d 个大类 · %d 个领域" % (len(self.lib), n_fields))
        self._render_cats()
        # 第 8 版简化：首次进入自动选第一个大类（候选最多的那个），
        # 让用户一进页面就能看见领域列表，而不是对着「先在左侧点一个学科大类」。
        if self.cat is None and self.lib:
            best = max(self.lib.items(), key=lambda kv: len(kv[1].get("subs", []) or []))[0]
            self.pick_cat(best)

    def _render_cats(self):
        self.cat_scroll.clear()
        for name, data in self.lib.items():
            n = len(data.get("subs", []))
            active = self.cat == name
            # 选中态：左侧 3px 品牌色竖条 + 浅底。与科研方法论页一致 ——
            # 整块染成 ACCENT_D 是旧的蓝色强调，现在全界面只有这里一根蓝条，
            # 看着像没跟上主题的旧控件。
            outer = tk.Frame(self.cat_scroll.inner, bg=T.CARD, cursor="hand2")
            outer.pack(fill="x", pady=1)
            bar = tk.Frame(outer, bg=T.ACCENT if active else T.CARD, width=3)
            bar.pack(side="left", fill="y")
            f = tk.Frame(outer, bg=T.CARD_HI if active else T.CARD, cursor="hand2")
            f.pack(side="left", fill="x", expand=True)
            lb = tk.Label(f, text=name, bg=f.cget("bg"),
                          fg=T.TXT if active else T.TXT2,
                          font=T.T_LABEL() if active else T.T_BODY_SM(),
                          anchor="w")
            lb.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=5)
            n_lb = tk.Label(f, text="%d 个领域" % n, bg=f.cget("bg"), fg=T.TXT3,
                            font=T.T_CAPTION())
            n_lb.pack(side="right", padx=(0, 8))
            for w in (outer, f, lb, n_lb):
                w.bind("<Button-1>", lambda e, nm=name: self.pick_cat(nm))

    def pick_cat(self, name):
        self.cat = name
        self.field = None
        self._render_cats()
        self._render_fields()
        # 换了学科大类，右栏的旧领域组合必须清掉，否则显示的是上一个领域的
        # 勾选状态（第 10 版之前就是这样，用户会以为点错了）。
        self.vars = {}
        self._show_actions(False)
        self._render_empty_combo()

    def _field_counts(self):
        """各具体方向在导师库里的学者数（用于在列表上标注）。"""
        if getattr(self, "_counts_cache", None) is not None:
            return self._counts_cache
        counts = {}
        try:
            import advisor_index as AI
            rows = AI.load_all()
            for a in rows:
                if not a.get("_complete", True):
                    continue
                for f in (a.get("fields") or []):
                    counts[f] = counts.get(f, 0) + 1
        except Exception:
            counts = {}
        self._counts_cache = counts
        return counts

    def _render_fields(self):
        self.field_scroll.clear()
        if not self.cat:
            tk.Label(self.field_scroll.inner, text="先在左侧点一个学科大类。", bg=T.CARD,
                     fg=T.TXT4, font=T.T_BODY_SM()).pack(pady=8, padx=2, anchor="w")
            return
        data = self.lib.get(self.cat, {})
        self.field_head.config(text="推荐投稿：" + " · ".join(data.get("venues", [])[:6]))
        counts = self._field_counts()
        for sub in data.get("subs", []):
            name = sub.get("name", "")
            active = self.field == name
            n = counts.get(name, 0)
            outer = tk.Frame(self.field_scroll.inner, bg=T.CARD, cursor="hand2")
            outer.pack(fill="x", pady=1)
            bar = tk.Frame(outer, bg=T.ACCENT if active else T.CARD, width=3)
            bar.pack(side="left", fill="y")
            f = tk.Frame(outer, bg=T.CARD_HI if active else T.CARD, cursor="hand2")
            f.pack(side="left", fill="x", expand=True)
            # 显示该领域在导师库里的学者数：0 人时提前提示，
            # 避免用户点进去发现「推荐导师」是空的还以为功能坏了
            lb = tk.Label(f, text=name, bg=f.cget("bg"),
                          fg=(T.TXT if active else (T.TXT2 if n else T.TXT4)),
                          font=T.T_LABEL() if active else T.T_BODY_SM(), anchor="w")
            lb.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=5)
            if n:
                cnt = tk.Label(f, text="%d 人" % n, bg=f.cget("bg"), fg=T.TXT3,
                               font=T.T_CAPTION())
            else:
                cnt = tk.Label(f, text="暂无学者", bg=f.cget("bg"), fg=T.TXT4,
                               font=T.T_CAPTION())
            cnt.pack(side="right", padx=(0, 8))
            for w in (outer, f, lb, cnt):
                w.bind("<Button-1>", lambda e, nm=name: self.pick_field(nm))

    def pick_field(self, name):
        self.field = name
        self._show_actions(True)
        self._render_fields()
        self._render_combo()
        # 在方向图谱里点开一个细分方向，是最直接的「我在看这个」信号
        try:
            import profile_hooks as PH
            PH.see_field(name, source="方向图谱")
            PH.see_category(self.cat, source="方向图谱")
        except Exception:
            pass

    def _show_actions(self, on):
        """三个跳转按钮只在选定领域后出现（没选时点了只会提示「先选一个」）。"""
        if on and not self._act.winfo_ismapped():
            self._act.pack(fill="x", pady=(8, 0))
        elif not on and self._act.winfo_ismapped():
            self._act.pack_forget()

    # ------------------------------------------------------------ 组合
    def _resync_card(self):
        """pack/pack_forget 之后让卡片重新量高度（Card 不会自己长高）。"""
        def job():
            try:
                self.combo_scroll.refresh()
            except Exception:
                pass
        try:
            self.after(30, job)
        except Exception:
            pass

    def _render_empty_combo(self):
        """没选领域时右栏的形态：一句「点哪里」，不要整片留黑。

        第 10 版之前右栏只有一个空滚动区，看着像页面没加载完；
        三个动作按钮又藏着，用户不知道该干什么。
        """
        self.combo_title.config(text="")
        self.relation_lbl.config(text="")
        self.combo_scroll.clear()
        if self.combo_scroll.winfo_ismapped():
            self.combo_scroll.pack_forget()
        # 空态用自然高度、anchor="n" 贴住上方。
        # 不能给它 expand=True：Tk 撑的是 Frame 自身高度，内部即使 grid 顶对齐，
        # 整块看起来还是悬在这一栏的正中间（截图实测）。
        if not self.combo_empty.winfo_ismapped():
            # before= 把空态卡钉在滚动区**之前**：滚动区 pack_forget 之后，
            # 新控件默认排到所有兄弟之后（= 栏底），截图里就悬在 3/4 高度。
            try:
                self.combo_empty.pack(fill="x", anchor="n", padx=2, pady=(2, 0),
                                      before=self.combo_scroll)
            except Exception:
                self.combo_empty.pack(fill="x", anchor="n", padx=2, pady=(2, 0))
        self._resync_card()

    def _render_combo(self):
        if self.combo_empty.winfo_ismapped():
            self.combo_empty.pack_forget()
        if not self.combo_scroll.winfo_ismapped():
            # 先 pack 滚动区再让出空态空间：pack 按调用顺序分配
            self.combo_scroll.pack(fill="both", expand=True)
        self.combo_scroll.clear()
        self.combo_title.config(text="%s  /  %s" % (self.cat, self.field))
        profile_key = ""
        try:
            profile_key = kb.field_profile(self.cat, self.field, self.rels)
        except Exception:
            pass
        profile = (self.rels.get("profiles") or {}).get(profile_key, {})
        self.relation_lbl.config(
            text="画像 %s · 维度重要性 场景%.0f%% 方法%.0f%% 任务%.0f%% 模态%.0f%%" % (
                profile.get("label", profile_key or "—"),
                *(100 * profile.get("importance", {}).get(k, 0)
                  for k in ("scenario", "method", "task", "modality"))))
        self.vars = {}
        dims = (("scenario", "应用场景", "scenarios"), ("method", "技术方法", "methods"),
                ("task", "研究任务", "tasks"), ("modality", "数据模态", "modalities"))
        for key, label, fld in dims:
            group = tk.Frame(self.combo_scroll.inner, bg=T.CARD)
            group.pack(fill="x", pady=(2, 6))
            head = tk.Frame(group, bg=T.CARD)
            head.pack(fill="x")
            tk.Label(head, text=label, bg=T.CARD, fg=T.TXT2, font=T.T_LABEL(),
                     anchor="w").pack(side="left")
            strong = set(profile.get(fld, []) or [])
            tk.Label(head, text="  ★ 强相关", bg=T.CARD, fg=T.OK,
                     font=T.T_CAPTION()).pack(side="left")
            opts = [o.get("name") for o in (self.tax.get(fld, []) or []) if o.get("name")]
            vars_map = {}
            wrap = tk.Frame(group, bg=T.CARD)
            wrap.pack(fill="x", pady=(2, 0))
            for i, opt in enumerate(opts):
                v = tk.BooleanVar(value=(opt in strong))
                vars_map[opt] = v
                is_strong = opt in strong
                cb = widgets.check(
                    wrap, ("★ " if is_strong else "○ ") + opt, v,
                    command=self.update_relation, strong=is_strong)
                cb.grid(row=i // 2, column=i % 2, sticky="w", padx=2, pady=1)
            self.vars[key] = vars_map
        self.update_relation()

    def _selections(self):
        out = {}
        for key, vm in self.vars.items():
            out[key] = [k for k, v in vm.items() if v.get()]
        return out

    def update_relation(self):
        try:
            profile_key = kb.field_profile(self.cat, self.field, self.rels)
        except Exception:
            return
        sel = self._selections()
        try:
            rel = kb.evaluate_combo(profile_key, sel, self.rels)
        except Exception:
            rel = None
        if rel is None:
            return
        score = rel.get("score", rel.get("relation_score", 0))
        strong = rel.get("strong_axes") or []
        weak = rel.get("weak") or []
        bits = ["组合相关度 %d%%" % score,
                "画像 " + str(rel.get("profile", "—"))]
        if strong:
            bits.append("强相关维度：" + "、".join(strong))
        if weak:
            bits.append("弱相关维度：" + "、".join(weak))
        col = T.OK if score >= 60 else (T.WARN if score >= 40 else T.ERR)
        self.relation_lbl.config(text="  ·  ".join(bits), fg=col)

    # ------------------------------------------------------------ 动作
    def make_prompt(self):
        if not self.field:
            self.app.toast("先选择一个领域", T.WARN)
            return
        sel = self._selections()
        try:
            entry = next(s for s in self.lib[self.cat]["subs"] if s.get("name") == self.field)
        except Exception:
            entry = {}
        try:
            text = kb.taxonomy_prompt(
                self.cat, self.field, entry, self.lib[self.cat].get("venues", []),
                sel.get("scenario", []), sel.get("method", []), sel.get("task", []),
                sel.get("modality", []), self.tax.get("sources", []),
                kb.evaluate_combo(kb.field_profile(self.cat, self.field, self.rels),
                                  sel, self.rels))
        except Exception as exc:
            self.app.toast("生成失败：" + str(exc), T.ERR)
            return
        path = kb.save_prompt("多维方向调研", text)
        self.app.copy(text)
        self.app.toast("调研提示词已复制，存档：" + path.name, T.OK)
        self.app.log("已生成调研提示词：" + str(path), T.OK, force_open=True)

    def to_advisors(self):
        if not self.field:
            self.app.toast("先选择一个领域", T.WARN)
            return
        self.app.goto("mentor", cat=self.cat, field=self.field)

    def to_venues(self):
        if not self.field:
            self.app.toast("先选择一个领域", T.WARN)
            return
        self.app.goto("venue", cat=self.cat, field=self.field)