#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向图谱页：24 大类 / 300+ 研究领域的可浏览目录 + 多维组合调研。

方向库与维度定义来自 kb_widget（directions_library / research_taxonomy /
research_relations），本页负责把它变成一个可点、可选、能出结论的界面。
"""
import threading
import tkinter as tk


import app_theme as T
from ui_parts import WrapRow   # 会自动折行的按钮排
import ui_parts as U
import kb_widget as kb
import ui_kit as UK


class _DimensionOptions(tk.Frame):
    """维度词表只建一次；缩放仅重排，完整标签按单元格宽度折行。"""

    def __init__(self, parent, options, strong, command):
        super().__init__(parent, bg=T.CARD)
        self.vars = {}
        self._checks = []
        self._cols = 0
        self._width = 0
        for opt in options:
            var = tk.BooleanVar(value=opt in strong)
            self.vars[opt] = var
            cb = tk.Checkbutton(
                self, text=opt, variable=var, command=command,
                bg=T.CARD, fg=T.TXT2, activebackground=T.CARD,
                activeforeground=T.TXT, selectcolor=T.tint(T.ACCENT, 0.12, T.CARD),
                font=T.T_BODY_SM(), anchor="w", justify="left", wraplength=1,
                relief="flat", bd=0, highlightthickness=0, padx=2, pady=3)
            self._checks.append(cb)
        self.bind("<Configure>", self._layout)

    def _layout(self, event):
        if event.width <= 1 or event.width == self._width:
            return
        self._width = event.width
        cols = max(1, min(3, event.width // T.sp(210)))
        for col in range(max(cols, self._cols)):
            self.grid_columnconfigure(col, weight=1 if col < cols else 0,
                                      minsize=0, uniform="options" if col < cols else "")
        self._cols = cols
        wrap = max(1, event.width // cols - T.sp(38))
        for i, cb in enumerate(self._checks):
            cb.config(wraplength=wrap)
            cb.grid(row=i // cols, column=i % cols, sticky="ew", padx=(0, 4), pady=1)

PAGE_HINT = "学科大类与研究领域 · 场景 / 方法 / 任务 / 模态组合"

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
所以细分方向可能查不到人。列表人数仅代表当前导师索引的覆盖情况。
想找这类方向的导师，直接去导师页按名字搜，或者按相邻方向查。

三、它的边界
词表以人工整理的学科与方向为主，也包含自定义方向；当前数量见页头统计，允许交叉。
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
        # 2026-11-20：以前是 self.after(80, self.reload) —— 词表加载被推迟到
        # 80ms 后。这一页被重建时（例如测试脚本截完图回收页面、或以后真做了
        # 懒加载），`app.goto("map")` 是同步返回的，调用方紧接着读
        # `pg.lib` / `pg.cat` 会拿到空的初始值，看起来像「方向库没加载」。
        # 词表是本地静态 JSON，读一次 0.05s，直接同步读完更稳。
        try:
            self.reload()
        except Exception:
            self.after(80, self.reload)

    # ------------------------------------------------------------ 布局
    def _build(self):
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(T.sp(8), T.sp(10)))
        tk.Label(top, text="方向图谱", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE(), anchor="w").pack(fill="x", pady=(4, 4))
        self.count_lbl = tk.Label(top, text="正在加载方向词表…", bg=T.BG, fg=T.TXT3,
                                  font=T.T_CAPTION(), anchor="w", justify="left", wraplength=1)
        self.count_lbl.pack(fill="x")
        T.fill_wrap(self.count_lbl, pad=4)

        self._hint = U.Hint(top, MAP_HELP, summary="选学科 → 选领域 → 组合调研 · 图谱说明", bg=T.BG)
        self._hint.pack(fill="x", pady=(4, 0))
        T.fill_wrap(self._hint._detail, pad=4)

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, T.sp(14)))
        body.grid_rowconfigure(0, weight=1)
        for col, weight, minimum in ((0, 2, 180), (1, 3, 240), (2, 4, 320)):
            body.grid_columnconfigure(col, weight=weight, minsize=T.sp(minimum),
                                      uniform="atlas")

        c1 = T.Card(body, pad=T.sp(12))
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, T.sp(10)))
        UK.eyebrow(c1.body, "DISCIPLINES", "01").pack(fill="x")
        tk.Label(c1.body, text="学科大类", bg=T.CARD, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(fill="x", pady=(4, 8))
        self.cat_scroll = T.ScrollArea(c1.body, bg=T.CARD)
        self.cat_scroll.pack(fill="both", expand=True)

        c2 = T.Card(body, pad=T.sp(12))
        c2.grid(row=0, column=1, sticky="nsew", padx=(0, T.sp(10)))
        UK.eyebrow(c2.body, "RESEARCH FIELDS", "02").pack(fill="x")
        tk.Label(c2.body, text="研究领域", bg=T.CARD, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(fill="x", pady=(4, 8))
        self.field_head = tk.Label(c2.body, text="", bg=T.CARD, fg=T.TXT3,
                                   font=T.T_CAPTION(), anchor="w", justify="left", wraplength=1)
        self.field_head.pack(fill="x", pady=(0, 8))
        T.fill_wrap(self.field_head, pad=4)
        self.field_scroll = T.ScrollArea(c2.body, bg=T.CARD)
        self.field_scroll.pack(fill="both", expand=True)
        # 空态挂在持久的宿主，clear() 不会留下已销毁控件的实例引用。
        self.field_empty = UK.EmptyPanel(
            c2.body, "先选学科大类", "左栏选择后，这里列出完整的细分方向。",
            bg=T.CARD, height=T.sp(250))

        c3 = T.Card(body, pad=T.sp(14))
        c3.grid(row=0, column=2, sticky="nsew")
        UK.eyebrow(c3.body, "RESEARCH COMBINATIONS", "03").pack(fill="x")
        tk.Label(c3.body, text="多维组合", bg=T.CARD, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(fill="x", pady=(4, 8))
        self._combo_host = c3.body
        # 固定动作区必须先占底部空间，滚动正文只能拿余下的高度。
        self._act = tk.Frame(c3.body, bg=T.CARD)
        self._act.pack(side="bottom", fill="x", pady=(T.sp(8), 0))
        UK.divider(self._act, pady=(0, T.sp(8)))
        self._act_row = WrapRow(self._act, bg=T.CARD, gap=T.sp(6))
        self._act_row.pack(fill="x")
        self._act_row.add(T.Btn(self._act_row, "生成调研提示词", self.make_prompt, "primary"))
        self._act_row.add(T.Btn(self._act_row, "推荐导师", self.to_advisors))
        self._act_row.add(T.Btn(self._act_row, "推荐期刊会议", self.to_venues))
        self._act_row.add(T.Btn(self._act_row, "去选题工坊", self.to_workshop))
        self._act_row.add(T.Btn(self._act_row, "查文献空白", self.to_gap))
        self.combo_scroll = T.ScrollArea(c3.body, bg=T.CARD)
        self.combo_scroll.pack(fill="both", expand=True)
        self.combo_title = tk.Label(self.combo_scroll.inner, text="", bg=T.CARD, fg=T.TXT,
                                    font=T.T_SECTION(), anchor="w", justify="left", wraplength=1)
        self.combo_title.pack(fill="x", pady=(0, 6))
        T.fill_wrap(self.combo_title, pad=4)
        self.relation_lbl = tk.Label(self.combo_scroll.inner, text="", bg=T.CARD, fg=T.TXT3,
                                     font=T.T_CAPTION(), anchor="w", justify="left", wraplength=1)
        self.relation_lbl.pack(fill="x", pady=(0, 8))
        T.fill_wrap(self.relation_lbl, pad=4)
        self._combo_body = tk.Frame(self.combo_scroll.inner, bg=T.CARD)
        self._combo_body.pack(fill="x")
        self.combo_empty = UK.EmptyPanel(
            c3.body, "先选一个具体领域", "点中间一栏的方向，再勾选四个维度，组成调研问题。",
            bg=T.CARD, height=T.sp(260))
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
        self.count_lbl.config(text="%d 个大类 · %d 个领域 · 静态词表与关系导航，非实时研究前沿" %
                              (len(self.lib), n_fields))
        if self.cat not in self.lib:
            self.cat = None
            self.field = None
        self._render_cats()
        # 第 8 版简化：首次进入自动选第一个大类（候选最多的那个），
        # 让用户一进页面就能看见领域列表，而不是对着「先在左侧点一个学科大类」。
        if self.cat is None and self.lib:
            best = max(self.lib.items(), key=lambda kv: len(kv[1].get("subs", []) or []))[0]
            self.pick_cat(best)
        else:
            self._render_fields()
            if not self.cat:
                self._render_empty_combo()

    def _directory_row(self, parent, name, meta, active, command):
        bg = T.tint(T.ACCENT, 0.09, T.CARD) if active else T.CARD
        row = tk.Frame(parent, bg=bg, cursor="hand2")
        row.pack(fill="x")
        line = tk.Frame(row, bg=T.LINE_SOFT, height=1)
        line.pack(side="bottom", fill="x")
        label = tk.Label(row, text=name, bg=bg, fg=T.TXT if active else T.TXT2,
                         font=T.T_LABEL() if active else T.T_BODY_SM(),
                         anchor="w", justify="left", wraplength=1)
        label.pack(fill="x", padx=T.sp(8), pady=(T.sp(7), 2))
        T.fill_wrap(label, pad=T.sp(16))
        count = tk.Label(row, text=meta, bg=bg, fg=T.ACCENT if active else T.TXT3,
                         font=T.T_CAPTION(), anchor="w", justify="left", wraplength=1)
        count.pack(fill="x", padx=T.sp(8), pady=(0, T.sp(7)))
        T.fill_wrap(count, pad=T.sp(16))
        for widget in (row, line, label, count):
            widget.bind("<Button-1>", lambda e, nm=name: command(nm))
        return row

    def _render_cats(self):
        self.cat_scroll.clear()
        if not self.lib:
            UK.EmptyPanel(self.cat_scroll.inner, "方向词表为空", "加载后可从学科大类开始浏览。",
                          bg=T.CARD, height=T.sp(250)).pack(fill="x", pady=(4, 0))
        for name, data in self.lib.items():
            self._directory_row(self.cat_scroll.inner, name,
                                "%d 个领域" % len(data.get("subs", [])),
                                self.cat == name, self.pick_cat)
        self.cat_scroll.refresh(defer=True)

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
        """各具体方向在导师库里的学者数（用于在列表上标注）。

        首次调用**不再同步读 1.8 万条导师库**：那一下要 1–2 秒，整页卡死，
        用户看到的就是「点一下半天没反应」。现在缓存为空时先返回 None 并
        起一个后台线程算，算完再把当前领域列表重画一次；期间列表照常可点。
        """
        if getattr(self, "_counts_cache", None) is not None:
            return self._counts_cache
        if not getattr(self, "_counts_loading", False):
            self._counts_loading = True

            def work():
                counts = {}
                try:
                    import advisor_index as AI
                    for a in AI.load_all():
                        if not a.get("_complete", True):
                            continue
                        for f in (a.get("fields") or []):
                            counts[f] = counts.get(f, 0) + 1
                except Exception:
                    counts = {}
                self.app.post(lambda: self._counts_ready(counts))

            threading.Thread(target=work, daemon=True).start()
        return None

    def _counts_ready(self, counts):
        self._counts_cache = counts
        self._counts_loading = False
        if self.cat:
            try:
                self._render_fields()
            except Exception:
                pass

    def _render_fields(self):
        self.field_scroll.clear()
        data = self.lib.get(self.cat, {}) if self.cat else {}
        subs = data.get("subs") or []
        if not self.cat or not subs:
            self.field_head.config(text=self.cat or "")
            self.field_scroll.pack_forget()
            self.field_empty.pack(fill="x", anchor="n", pady=(4, 0))
            return
        self.field_empty.pack_forget()
        if not self.field_scroll.winfo_manager():
            self.field_scroll.pack(fill="both", expand=True)
        self.field_head.config(text="%s · %d 个领域\n选中后在右栏查看投稿线索与组合。" %
                               (self.cat, len(subs)))
        counts = self._field_counts()
        for sub in subs:
            name = sub.get("name", "")
            n = counts.get(name, 0) if counts is not None else 0
            if counts is None:
                meta = "学者索引统计中…"
            elif n:
                meta = "%d 位学者" % n
            else:
                meta = "暂无学者 · 索引未覆盖，不代表无人研究"
            self._directory_row(self.field_scroll.inner, name, meta,
                                self.field == name, self.pick_field)
        self.field_scroll.refresh(defer=True)

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
        """固定动作区先占底部；未选领域时禁用，不重新排列滚动正文。"""
        for button in self._act_row.items():
            button.enable(on)

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

    def _clear_combo(self):
        # 整个分组（含折行容器）一起销毁，绝不只销毁 WrapRow 的 items。
        self.vars = {}
        for child in list(self._combo_body.winfo_children()):
            child.destroy()

    def _render_empty_combo(self):
        self._show_actions(False)
        self.combo_title.config(text="")
        self.relation_lbl.config(text="", fg=T.TXT3)
        self._clear_combo()
        self.combo_scroll.pack_forget()
        self.combo_empty.pack(fill="x", anchor="n", pady=(4, 0))
        self._resync_card()

    def _render_combo(self):
        if not self.field:
            self._render_empty_combo()
            return
        self.combo_empty.pack_forget()
        if not self.combo_scroll.winfo_manager():
            self.combo_scroll.pack(fill="both", expand=True)
        self._show_actions(True)
        self._clear_combo()
        self.combo_scroll.scroll_to_top()
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
        data = self.lib.get(self.cat, {})
        entry = next((s for s in data.get("subs", []) if s.get("name") == self.field), {})
        keywords = entry.get("keywords") or []
        if keywords:
            self._combo_note("领域关键词：" + " · ".join(keywords))
        venues = data.get("venues") or []
        self._combo_note("投稿线索：" + " · ".join(venues) if venues
                         else "交叉领域的投稿线索请按具体方向检索。")
        self._combo_note("默认勾选来自静态关系词表，可自由调整；组合相关度不是新颖性或可行性结论。")
        dims = (("scenario", "应用场景", "scenarios"), ("method", "技术方法", "methods"),
                ("task", "研究任务", "tasks"), ("modality", "数据模态", "modalities"))
        for number, (key, label, fld) in enumerate(dims, 1):
            group = tk.Frame(self._combo_body, bg=T.CARD)
            group.pack(fill="x", pady=(T.sp(10), T.sp(6)))
            UK.divider(group, pady=(0, T.sp(8)))
            UK.eyebrow(group, key.upper(), "%02d" % number).pack(fill="x")
            tk.Label(group, text=label, bg=T.CARD, fg=T.TXT,
                     font=T.T_SECTION(), anchor="w").pack(fill="x", pady=(4, 4))
            strong = set(profile.get(fld, []) or [])
            opts = [o.get("name") for o in (self.tax.get(fld, []) or []) if o.get("name")]
            options = _DimensionOptions(group, opts, strong, self.update_relation)
            options.pack(fill="x")
            self.vars[key] = options.vars
            if not opts:
                self._combo_note("该维度暂未收录词条。", parent=group)
        self.update_relation()
        self._resync_card()

    def _combo_note(self, text, parent=None):
        label = tk.Label(parent or self._combo_body, text=text, bg=T.CARD, fg=T.TXT3,
                         font=T.T_CAPTION(), anchor="w", justify="left", wraplength=1)
        label.pack(fill="x", pady=(0, 6))
        T.fill_wrap(label, pad=4)
        return label

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
                "、".join(sel.get("scenario", [])), sel.get("method", []), sel.get("task", []),
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

    def to_workshop(self):
        if not self.field:
            self.app.toast("先选择一个领域", T.WARN)
            return
        self.app.goto("topic", cat=self.cat, field=self.field)
        page = self.app.page("topic")
        page.entry.delete(0, "end")
        page.entry.insert(0, self.field)
        page.entry.focus_set()
        self.app.toast("方向已带入工坊，可补充具体问题后生成候选", T.OK)

    def to_gap(self):
        if not self.field:
            self.app.toast("先选择一个领域", T.WARN)
            return
        selections = self._selections()
        # 仅带入用户选择的检索词，不把关系分数当成文献空白结论。
        terms = [self.field]
        for key in ("scenario", "method", "task", "modality"):
            terms.extend(selections.get(key, []))
        query = " ".join(dict.fromkeys(terms))
        self.app.goto("gap", cat=self.cat, field=self.field)
        page = self.app.page("gap")
        page.entry.delete(0, "end")
        page.entry.insert(0, query)
        page.entry.focus_set()
        self.app.toast("组合已带入文献空白，点击分析核查本地文献", T.OK)
