#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导师与院校页：按研究方向匹配全国院校里的研究者。

数据：advisor_directory.json（人工样本）+ advisor_directory_generated.json（OpenAlex
抓取的 5767 位研究者）。中文院校名与省份来自 institution_localization.json。

重要：匹配只依据公开出版索引，不代表在职身份、招生名额或导师意愿，联系前必须官网核验。
"""
import re
import threading
import tkinter as tk

import app_theme as T
import ui_parts as U
import ui_kit as UK
import advisor_index
import name_match
import kb_widget as kb

PAGE_HINT = "公开出版索引匹配 · 联系前到院校官网核验"

MENTOR_HELP = """\
名单只放「画像能核验」的学者：有机构、有方向、有发表记录。缺一项就不进主表——
这是为了避免把同名的人、空壳记录推荐给你。

一、数据从哪来
· OpenAlex 的作者与机构数据（公开出版索引）+ arXiv 近三年的作者频次倒推补充。
· 省份来自我们自己的院校库（3178 所）；机构名做了归一，Stanford CS 和 Stanford University 会算成同一所。
· 引用数和论文数来自 OpenAlex 的统计口径，不是实时数据。

二、三条必须知道的限制
1. 匹配度高 ≠ 他在招人。这是研究方向词的重合度，不是招生意愿，也不代表他现在还有名额。
2. 引用数高 ≠ 好导师。高被引可能来自一篇多年前的综述；带学生的质量、是否放养、push 程度，这个库一概不知道。
3. 学者可能已经转行、退休、换学校，或者同名不同人。所有信息在联系之前都请到院校官网个人页核对一遍。

三、怎么用最省事
先按方向筛出 10 到 20 人，再用「按姓名查找」确认目标（支持中文名，输入「孙茂松」也能找到 Maosong Sun），
导出 CSV 之后拿去逐个人肉核验——发邮件之前至少看完他最近两年的三篇代表作。"""


def _fmt_cited(n):
    try:
        n = int(n)
    except Exception:
        return "—"
    if n >= 10000:
        return "%.1fw" % (n / 10000.0)
    if n >= 1000:
        return "%.1fk" % (n / 1000.0)
    return str(n)


def _fmt_int(n):
    try:
        return "{:,}".format(int(n))
    except Exception:
        return str(n)


class MentorPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.rows = []
        self.ctx = {}
        self._all = []
        self._mode = "direction"          # direction / search / school
        self._layout = "grid"             # grid / list
        self._school = None               # 院校视图里已打开的院校
        self._sel = -1
        self._limit = 60
        self._found_rows = []
        self._found_total = 0
        self._last_query = ""
        self._dir_rows = None
        self._dir_meta = ""
        self._meta_txt = ""
        self._loaded = False
        self._build()
        self.after(120, self._load_index)

    # ------------------------------------------------------------ 骨架
    def _build(self):
        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=T.PAD, pady=(6, 2))
        cover = tk.Frame(head, bg=T.BG)
        cover.pack(side="right", anchor="n", padx=(12, 0))
        self.coverage = tk.Label(cover, text="索引加载中…", bg=T.BG, fg=T.TXT2,
                                 font=T.T_CAPTION(), anchor="e", justify="right")
        self.coverage.pack(anchor="e")
        self._cov2 = tk.Label(cover, text="", bg=T.BG, fg=T.TXT4,
                              font=T.T_CAPTION(), anchor="e", justify="right")
        self._cov2.pack(anchor="e")

        tk.Label(head, text="导师与院校", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE(), anchor="w").pack(
            side="left", anchor="s", pady=(0, 2))

        hint_row = tk.Frame(self, bg=T.BG)
        hint_row.pack(fill="x", padx=T.PAD, pady=(0, 2))
        self._hint = U.Hint(hint_row, MENTOR_HELP,
                            summary="数据来源与限制：公开出版索引，联系前到院校官网核验",
                            bg=T.BG)
        self._hint.pack(fill="x")

        tabsrow = tk.Frame(self, bg=T.BG)
        tabsrow.pack(fill="x", padx=T.PAD, pady=(4, 6))
        self.tabs = UK.Segmented(
            tabsrow,
            [("direction", "按方向推荐"), ("search", "全部学者"), ("school", "院校")],
            value="direction", command=self._set_mode)
        self.tabs.pack(side="left")

        # ---- 筛选卡：输入 + 地区胶囊（网页版的 filter-bar）
        fcard = T.Card(self, pad=10, fill_y=False)
        fcard.pack(fill="x", padx=T.PAD, pady=(0, 6))
        bar = tk.Frame(fcard.body, bg=T.CARD)
        bar.pack(fill="x")
        self._field_lbl = tk.Label(bar, text="研究方向", bg=T.CARD, fg=T.TXT3,
                                   font=T.T_CAPTION(), anchor="w")
        self._field_lbl.pack(side="left", padx=(2, 8))
        self.entry = tk.Entry(bar, bg=T.CARD_HI, fg=T.TXT,
                              insertbackground=T.ACCENT, relief="flat",
                              highlightbackground=T.LINE, highlightcolor=T.ACCENT,
                              highlightthickness=1, font=T.T_BODY_SM())
        self.entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.entry.bind("<Return>", lambda e: self._on_action())
        try:
            import app_suggest
            app_suggest.attach(self.entry)
        except Exception as exc:
            print("联想词挂载失败:", exc)
        self.btn = T.Btn(bar, "匹配导师", self._on_action, "primary")
        self.btn.pack(side="right", padx=(8, 0))

        prow = tk.Frame(fcard.body, bg=T.CARD)
        prow.pack(fill="x", pady=(8, 0))
        tk.Label(prow, text="地区", bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION()).pack(
            side="left", padx=(2, 8))
        self._prov_holder = prow
        self.province = tk.StringVar(value="全部")
        self._prov_all = ["全部"]
        self.prov_box = U.WrapRow(prow, bg=T.CARD)
        self.prov_box.pack(side="left", fill="x", expand=True)
        self._render_prov_chips()

        # ---- 结果行：一句统计 + 平铺/列表 + 导出
        meta = tk.Frame(self, bg=T.BG)
        self._meta_row = meta
        self._meta_right = tk.Frame(meta, bg=T.BG)
        self._meta_right.pack(side="right")
        self._toggle = UK.Segmented(self._meta_right, [("grid", "平铺"), ("list", "列表")],
                                    value="grid", command=self._set_layout,
                                    font=T.T_CAPTION())
        self.btn_export = T.Btn(self._meta_right, "导出", self.export_csv, "ghost")
        self.btn_copy = T.Btn(self._meta_right, "复制", self._copy_list, "ghost")
        self._tip(self.btn_export, "把当前清单导出为 CSV")
        self._tip(self.btn_copy, "复制当前清单")
        self.meta_lbl = tk.Label(meta, text="", bg=T.BG, fg=T.TXT3,
                                 font=T.T_CAPTION(), anchor="w", justify="left")
        self.meta_lbl.pack(side="left", fill="x", expand=True)

        def _meta_wrap(_e=None):
            try:
                w = self.meta_lbl.winfo_width()
                if w > 80:
                    self.meta_lbl.configure(wraplength=w - 4)
            except Exception:
                pass
        self.meta_lbl.bind("<Configure>", _meta_wrap)
        self.btn_back = T.Btn(meta, "← 全部院校", self._school_back, "ghost")

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 12))
        self.body = body
        body.grid_rowconfigure(0, weight=1)
        # uniform：按 3:2 强制分栏。不加时 Tk 先满足两栏的「请求宽度」，
        # 详情卡里的长句子会把左栏挤到只剩一条 —— 2026-11-19 实测左栏 304px。
        body.grid_columnconfigure(0, weight=3, uniform="mentor")
        body.grid_columnconfigure(1, weight=2, uniform="mentor", minsize=T.sp(300))

        self.card = T.Card(body, pad=10)
        self.card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.scroll = T.ScrollArea(self.card.body, bg=T.CARD)
        self.scroll.pack(fill="both", expand=True)

        self.detail_card = T.Card(body, pad=14)
        self.detail_card.grid(row=0, column=1, sticky="nsew")
        self.detail = T.ScrollArea(self.detail_card.body, bg=T.CARD)
        self.detail.pack(fill="both", expand=True)
        self._detail_empty()

        self._card_frames = []
        self._row_frames = []
        self._school_frames = []
        self._school_host = None
        self._school_more_wrap = None
        self._school_cache = []
        self._school_limit = self._SCHOOL_PAGE
        self._flow_layout = None
        self._empty_card = None
        self._showing_list = False
        self.card.grid_remove()
        self.detail_card.grid_remove()
        self._show_empty(
            "先给一个方向",
            "输入研究方向后按大类、领域与关键词匹配；也可以切到「全部学者」浏览检索，"
            "或按「院校」逐校查看。",
            ("单目深度估计", "红外小目标检测", "联邦学习隐私保护", "蛋白质结构预测"))

    # ------------------------------------------------------------ 地区胶囊
    _COMMON_PROV = ("北京", "上海", "江苏", "浙江", "广东", "湖北")

    def _render_prov_chips(self):
        # WrapRow 内部还留着旧控件的引用，直接销毁子控件再复用会去 place
        # 一个已死的窗口路径；整条换新。
        try:
            self.prov_box.destroy()
        except Exception:
            pass
        self.prov_box = U.WrapRow(self._prov_holder, bg=T.CARD)
        self.prov_box.pack(side="left", fill="x", expand=True)
        names = list(getattr(self, "_prov_all", ["全部"]))
        common = ["全部"] + [p for p in self._COMMON_PROV if p in names]
        for p in common:
            on = (self.province.get() == p)
            self.prov_box.add(UK.Chip(
                self.prov_box, p, active=on, font=T.T_CAPTION(),
                command=lambda _p=p: self._pick_province(_p)))
        others = [p for p in names if p not in common]
        if others:
            self.prov_box.add(UK.Chip(
                self.prov_box, "更多地区 ▾", font=T.T_CAPTION(),
                command=lambda: self._more_province(others)))

    def _pick_province(self, name):
        if name == self.province.get():
            return
        self.province.set(name)
        self._render_prov_chips()
        if self._mode == "direction":
            if self._last_query:
                self.search(self._last_query)
        elif self._mode == "search":
            if self._all:
                self._apply_search(reset_limit=True)
        elif self._mode == "school":
            if self._school:
                self._open_school(self._school)
            else:
                self._render_schools()

    def _more_province(self, names):
        m = tk.Menu(self, tearoff=0, bg=T.CARD, fg=T.TXT,
                    activebackground=T.ACCENT_D, activeforeground=T.ACCENT,
                    font=T.T_BODY_SM(), bd=0)
        for p in names:
            m.add_command(label=p, command=lambda _p=p: self._pick_province(_p))
        try:
            chip = self.prov_box.items()[-1]
            m.tk_popup(chip.winfo_rootx(),
                       chip.winfo_rooty() + chip.winfo_height() + 2)
        except Exception:
            pass

    # ------------------------------------------------------------ 模式切换
    def _set_mode(self, mode):
        if mode == self._mode:
            return
        self._mode = mode
        self._school = None
        self._sel = -1
        self.rows = []
        self._meta_txt = ""
        self.scroll.clear()
        if mode == "direction":
            self._field_lbl.config(text="研究方向")
            self.btn.config(text="匹配导师")
            self._put_entry(self._last_query)
            if self._dir_rows:
                self.rows = list(self._dir_rows)
                self._meta_txt = self._dir_meta
                self._render()
            else:
                self._show_empty(
                    "先给一个方向",
                    "输入研究方向后按大类、领域与关键词匹配；也可以切到「全部学者」浏览检索，"
                    "或按「院校」逐校查看。",
                    ("单目深度估计", "红外小目标检测", "联邦学习隐私保护",
                     "蛋白质结构预测"))
        elif mode == "search":
            self._field_lbl.config(text="姓名 / 机构 / 关键词")
            self.btn.config(text="筛选学者")
            self._put_entry("")
            if self._all:
                self._apply_search(reset_limit=True)
            else:
                self._show_empty("索引载入中", "学者索引还在读取，稍后会自动出现在这里。")
        else:
            self._field_lbl.config(text="院校名")
            self.btn.config(text="筛选院校")
            self._put_entry("")
            if self._all:
                self._render_schools()
            else:
                self._show_empty("索引载入中", "院校索引还在读取，稍后会自动出现在这里。")

    def _put_entry(self, text):
        self.entry.delete(0, "end")
        if text:
            self.entry.insert(0, text)

    def _on_action(self):
        if self._mode == "direction":
            self.search()
        elif self._mode == "search":
            self._apply_search(reset_limit=True)
        else:
            if self._school:
                self._open_school(self._school)
            else:
                self._render_schools()

    def _set_layout(self, value):
        if value == self._layout:
            return
        self._layout = value
        cap = 180 if value == "list" else 60
        if self._limit > cap:
            self._limit = cap
        if self._found_rows and len(self._found_rows) > cap:
            self.rows = self._found_rows[:cap]
        elif self.rows and self._found_rows:
            self.rows = self._found_rows[:self._limit]
        if self.rows and not (self._mode == "school" and not self._school):
            self._render_rows()
            idx = self._sel if 0 <= self._sel < len(self.rows) else 0
            self._select_row(idx)
            self._after_build()

    # ------------------------------------------------------------ 索引信息
    def _load_index(self):
        def work():
            try:
                adv = advisor_index.load_all()
            except Exception:
                adv = []
            provs = sorted({a.get("province") for a in adv if a.get("province")})
            zh = []
            seen = set()
            for p in provs:
                try:
                    z = kb.province_zh(p) or p
                except Exception:
                    z = p
                # 省库没映射到的原始代码（AE / BD / GR…）不是地区名，
                # 放进胶囊只会让筛选栏看起来像坏数据。只保留中文地区名。
                if not re.fullmatch(r"[\u4e00-\u9fff]{2,6}", z or ""):
                    continue
                if z not in seen:
                    seen.add(z)
                    zh.append(z)
            st = advisor_index.stats()
            self.app.post(lambda: self._fill(adv, zh, st))
        threading.Thread(target=work, daemon=True).start()

    def _fill(self, adv, provs, st=None):
        self._all = adv
        self._loaded = True
        self._prov_all = ["全部"] + list(provs)
        try:
            self._render_prov_chips()
        except Exception:
            pass
        st = st or {}
        total = st.get("complete_advisors") or st.get("advisors") or len(adv)
        total_all = st.get("advisors") or len(adv)
        insts = st.get("institutions", 0)
        self.coverage.config(
            text="可推荐 %s 位 · %s 所院校 · %d 个地区"
                 % (_fmt_int(total), _fmt_int(insts), len(provs)))
        covered = st.get("covered_institutions", 0)
        catalog = st.get("catalog_institutions", 0)
        # 只在索引没跑完时说话：覆盖满 100% 时这行长期挂着只是噪音。
        if catalog and covered < catalog:
            self._cov2.config(
                text="索引仍在扩充：已覆盖 %d / %d 所院校" % (covered, catalog),
                fg=T.WARN)
        else:
            self._cov2.config(text="", fg=T.TXT4)
        try:
            self.tabs.set_items([
                ("direction", "按方向推荐"),
                ("search", "全部学者", _fmt_int(total_all)),
                ("school", "院校", _fmt_int(self._school_count())),
            ])
        except Exception:
            pass
        if self._mode == "search":
            self._apply_search(reset_limit=True)
        elif self._mode == "school":
            self._render_schools()

    # ------------------------------------------------------------ 检索
    def search(self, preset=None):
        if self._mode != "direction":
            self._mode = "direction"
            self._school = None
            self._field_lbl.config(text="研究方向")
            self.btn.config(text="匹配导师")
            try:
                self.tabs.set_value("direction", notify=False)
            except Exception:
                pass
        text = (preset or self.entry.get()).strip()
        if not text:
            self.app.toast("请输入研究内容", T.WARN)
            return
        if preset:
            self._put_entry(preset)
        self._last_query = text
        self.btn.config(text="匹配中…")
        prov = self.province.get()
        self._sel = -1

        # 若输入的是人名（中文姓名或英文姓名），走「按学者查找」而不是方向匹配。
        # 学生常听说某位老师，想确认他在不在库里。
        if self._looks_like_name(text):
            self._search_by_name(text, prov)
            return

        def work():
            try:
                cat, field, conf = kb.infer_category_field(text)
                rels = kb.load_research_relations()
                pk = kb.field_profile(cat, field, rels) if (cat and field) else ""
                prof = (rels.get("profiles") or {}).get(pk, {})
                # 注意：kb.recommend_advisors 的 scenario 参数只接受单个字符串
                scen = (prof.get("scenarios") or [""])[0]
                meth = prof.get("methods", [])[:3]
                task = prof.get("tasks", [])[:2]
                mod = prof.get("modalities", [])[:2]
                rows = advisor_index.recommend(cat, field, scen, meth, task, mod, top=60)
                if prov and prov != "全部":
                    want = None
                    for a in self._all:
                        if (kb.province_zh(a.get("province", "")) or "") == prov:
                            want = a.get("province")
                            break
                    if want:
                        rows = [r for r in rows
                                if (r.get("advisor") or {}).get("province") == want]
                self.app.post(lambda: self._apply(text, cat, field, conf, rows, prov))
            except Exception as exc:
                self.app.post(lambda e=exc: self._fail(e))
            else:
                # 查过哪些方向，就是你对什么感兴趣——记下来，选题时用得上。
                try:
                    import profile_hooks as PH
                    if cat:
                        PH.see_category(cat, source="导师与院校")
                    if field or text:
                        PH.see_field(field or text, source="导师与院校")
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()

    def _looks_like_name(self, text):
        """启发式判断输入是否像人名。

        人名：2–4 个汉字，或 2–4 个英文单词且首字母大写（如 "Maosong Sun"）。
        研究内容通常带「研究 / 检测 / 学习 / 方向」等词，或长度更长。
        """
        t = text.strip()
        if not t:
            return False
        if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", t):
            # 排除明显是方向词的中文短语（如「目标检测」「深度估计」）
            stop = ("检测", "分割", "跟踪", "学习", "识别", "估计", "重建", "生成",
                    "推荐", "检索", "分析", "优化", "计算", "视觉", "语言", "网络",
                    "安全", "系统", "数据", "方法", "方向", "研究", "技术", "模型")
            return not any(s in t for s in stop)
        if re.fullmatch(r"[A-Za-z][a-zA-Z\-\.]{1,20}(\s+[A-Za-z][a-zA-Z\-\.]{1,20}){1,3}", t):
            # 英文姓名：多单词且不像技术词
            tech = ("learning", "vision", "detection", "network", "model", "data",
                    "system", "neural", "image")
            return not any(w.lower() in tech for w in t.split())
        return False

    def _search_by_name(self, text, prov):
        """按姓名查找学者。

        支持中英文互查：库里存的多是英文名（Maosong Sun），
        学生常输中文（孙茂松）—— 用 name_match 做拼音匹配。
        """
        def work():
            try:
                key = text.lower().strip()
                cn_query = bool(text) and all("\u4e00" <= ch <= "\u9fff" for ch in text)
                hits = []
                for a in self._all:
                    name = (a.get("name") or "")
                    low = name.lower()
                    matched = False
                    score = 80
                    if key in low:
                        matched = True
                        score = 99 if low == key else 85
                    elif cn_query and name_match.match_cn_query(text, name):
                        # 中文名 → 英文名的拼音匹配，置信度略低
                        matched = True
                        score = 78
                    if matched:
                        hits.append({"advisor": a, "score": score,
                                     "reasons": ["姓名匹配"],
                                     "cited": a.get("cited_by_count") or 0})
                if prov and prov != "全部":
                    hits = [h for h in hits
                            if (kb.province_zh((h["advisor"] or {}).get("province", "")) or "") == prov]
                self.app.post(lambda: self._apply_name(text, hits, prov))
            except Exception as exc:
                self.app.post(lambda e=exc: self._fail(e))
        threading.Thread(target=work, daemon=True).start()

    def _apply_name(self, text, hits, prov):
        self.btn.config(text="匹配导师")
        # 精确同名优先，其次引用量高的
        hits.sort(key=lambda h: (-h["score"], -(h.get("cited") or 0)))
        self.rows = hits
        self.ctx = dict(text=text, cat="", field="")
        self._dir_rows = hits
        self._meta_txt = "按姓名查找「%s」 · 命中 %d 位%s" % (
            text, len(hits), (" · " + prov) if prov != "全部" else "")
        self._dir_meta = self._meta_txt
        self._render()

    def _fail(self, exc):
        self.btn.config(text="匹配导师")
        self.app.toast("匹配失败：" + str(exc), T.ERR)

    def _apply(self, text, cat, field, conf, rows, prov):
        self.btn.config(text="匹配导师")
        self.rows = rows or []
        self.ctx = dict(text=text, cat=cat, field=field)
        parts = []
        if cat and field:
            parts.append("%s / %s" % (cat, field))
        else:
            parts.append("关键词匹配")
        parts.append("匹配 %d 位" % len(self.rows))
        insts = {(r.get("advisor") or {}).get("institution") or "未知"
                 for r in self.rows}
        parts.append("%d 所院校" % len(insts))
        if prov and prov != "全部":
            parts.append(prov)
        self._meta_txt = " · ".join(parts)
        self._dir_rows = list(self.rows)
        self._dir_meta = self._meta_txt
        self._render()

    def _apply_search(self, reset_limit=False):
        if reset_limit:
            self._limit = 60
        q = (self.entry.get() if self._mode == "search" else "").strip().lower()
        prov = self.province.get()
        rows = []
        for a in self._all:
            if not self._in_region(a, prov):
                continue
            if q:
                zh = ""
                try:
                    zh = kb.institution_zh(a.get("institution", "")) or ""
                except Exception:
                    pass
                hay = " ".join([
                    str(a.get("name") or ""), str(a.get("institution") or ""), zh,
                    str(a.get("category") or ""), " ".join(a.get("fields") or []),
                    " ".join(a.get("keywords") or []),
                ]).lower()
                if q not in hay:
                    continue
            rows.append({"advisor": a, "score": 0, "reasons": [],
                         "cited": a.get("cited_by_count") or 0})
        rows.sort(key=lambda r: -(r.get("cited") or 0))
        self._found_rows = rows
        self._found_total = len(rows)
        self.rows = rows[:self._limit]
        head = "找到 %s 位" % _fmt_int(self._found_total)
        if self._found_total > len(self.rows):
            head += " · 已显示 %d" % len(self.rows)
        if prov and prov != "全部":
            head += " · " + prov
        self._meta_txt = head
        self._render()

    def _load_more(self):
        cap = 180 if self._layout == "list" else 60
        self._limit = min(self._limit + 60, cap)
        self.rows = self._found_rows[:self._limit]
        head = "找到 %s 位" % _fmt_int(self._found_total)
        if self._found_total > len(self.rows):
            head += " · 已显示 %d" % len(self.rows)
        prov = self.province.get()
        if prov and prov != "全部":
            head += " · " + prov
        self._meta_txt = head
        self._render_rows()
        idx = self._sel if 0 <= self._sel < len(self.rows) else 0
        self._select_row(idx)
        self._after_build()

    def set_context(self, cat, field):
        """由「方向图谱」跳转进来时预填方向。"""
        self._put_entry(field)
        # 用命名方法而不是 lambda：窗口在 60ms 内被销毁时，
        # Tk 会报 invalid command name "…<lambda>"（截图脚本踩过）。
        self.after(60, self._search_now)

    def _search_now(self):
        try:
            if self.winfo_exists():
                self.search()
        except Exception:
            pass

    # ------------------------------------------------------------ 院校
    def _province_of(self, adv):
        try:
            return kb.province_zh(adv.get("province", "")) or ""
        except Exception:
            return ""

    def _in_region(self, adv, region):
        return (not region) or region == "全部" or self._province_of(adv) == region

    def _inst_zh(self, inst):
        try:
            return kb.institution_zh(inst) or ""
        except Exception:
            return ""

    def _schools(self):
        """{(院校英文名, 中文名, 省份): 人数}，按人数降序。"""
        groups = {}
        for a in self._all:
            inst = (a.get("institution") or "").strip()
            if not inst:
                continue
            zh = self._inst_zh(inst)
            key = (inst, zh)
            g = groups.get(key)
            if g is None:
                g = groups[key] = {"inst": inst, "zh": zh or inst,
                                   "prov": self._province_of(a), "n": 0}
            g["n"] += 1
        return list(groups.values())

    def _school_count(self):
        try:
            return len(self._schools())
        except Exception:
            return 0

    def _school_entries(self):
        prov = self.province.get()
        q = (self.entry.get() if self._mode == "school" else "").strip().lower()
        out = []
        for g in self._schools():
            if prov and prov != "全部" and g["prov"] != prov:
                continue
            if q and q not in (g["zh"] + " " + g["inst"]).lower():
                continue
            out.append(g)
        out.sort(key=lambda g: (-g["n"], g["zh"]))
        return out

    def _open_school(self, inst):
        self._school = inst
        self._put_entry("")
        prov = self.province.get()
        rows = []
        for a in self._all:
            if (a.get("institution") or "") != inst:
                continue
            if not self._in_region(a, prov):
                continue
            rows.append({"advisor": a, "score": 0, "reasons": [],
                         "cited": a.get("cited_by_count") or 0})
        rows.sort(key=lambda r: (-(r.get("cited") or 0),
                                 (r["advisor"].get("name") or "")))
        self.rows = rows
        self._sel = -1
        zh = self._inst_zh(inst) or inst
        self._meta_txt = "%s · %d 位%s" % (
            zh, len(rows), (" · " + prov) if prov != "全部" else "")
        self._render()

    def _school_back(self):
        self._school = None
        self.rows = []
        self._meta_txt = ""
        self._put_entry("")
        self._render_schools(keep=True)

    # ------------------------------------------------------------ 渲染
    def _render(self):
        if self._mode == "school" and not self._school:
            self._render_schools()
            return
        if not self.rows:
            if self._mode == "school" and self._school:
                self._show_empty("这所院校没有可展示的学者",
                                 "换一个地区筛选，或回到院校列表看其他学校。",
                                 meta=self._meta_txt)
            elif self._mode == "search":
                self._show_empty("没有匹配的学者",
                                 "换一个姓名、机构或关键词；也可以清除地区筛选再试。",
                                 meta=self._meta_txt)
            else:
                self._show_empty("没有命中",
                                 "换一个更常见的方向描述，或在「方向图谱」里选定领域后点「推荐导师」。",
                                 ("单目深度估计", "红外小目标检测", "联邦学习隐私保护",
                                  "蛋白质结构预测"),
                                 meta=self._meta_txt)
            self._sel = -1
            return
        self._show_list()
        self._paint_meta()
        self._render_rows()
        idx = self._sel if 0 <= self._sel < len(self.rows) else 0
        self._select_row(idx)
        self._after_build()

    def _show_meta_row(self, show):
        if show:
            if not self._meta_row.winfo_manager():
                self._meta_row.pack(fill="x", padx=T.PAD, pady=(0, 4),
                                    before=self.body)
        else:
            self._meta_row.pack_forget()

    def _show_list(self):
        if self._empty_card is not None:
            self._empty_card.grid_remove()
        self._show_meta_row(True)
        self._showing_list = True
        if not self.card.winfo_ismapped():
            self.card.grid()
        self.card.grid_configure(columnspan=1, padx=(0, 10))
        if not self.detail_card.winfo_ismapped():
            self.detail_card.grid(row=0, column=1, sticky="nsew")

    def _show_schools_layout(self):
        if self._empty_card is not None:
            self._empty_card.grid_remove()
        self._show_meta_row(True)
        self._showing_list = True
        if not self.card.winfo_ismapped():
            self.card.grid()
        self.card.grid_configure(columnspan=2, padx=0)
        self.detail_card.grid_remove()

    def _show_empty(self, title, body, examples=(), meta=""):
        self._ensure_empty()
        self._empty_title.config(text=title)
        self._empty_body.config(text=body)
        for w in list(self._empty_chip_host.winfo_children()):
            w.destroy()
        if examples:
            row = U.WrapRow(self._empty_chip_host, bg=T.CARD)
            row.pack(fill="x")
            for ex in examples:
                row.add(UK.Chip(row, ex, font=T.T_CAPTION(),
                                command=lambda t=ex: self._try_example(t)))
        self.card.grid_remove()
        self.detail_card.grid_remove()
        self._showing_list = False
        self.scroll.clear()
        self._empty_card.grid(row=0, column=0, columnspan=2, sticky="new")
        self._show_meta_row(False)
        self.meta_lbl.config(text=meta or "")
        self._sync_meta_buttons(False)
        self.btn_back.pack_forget()
        if self._mode == "school" and self._school:
            self.btn_back.pack(side="left", padx=(10, 0))
        try:
            self._empty_card.sync_now()
        except Exception:
            pass

    def _ensure_empty(self):
        if self._empty_card is not None:
            return
        card = T.Card(self.body, pad=14, fill_y=False)
        ins = card.body
        self._empty_title = tk.Label(ins, text="", bg=T.CARD, fg=T.TXT,
                                     font=T.T_SECTION(), anchor="w", justify="left")
        self._empty_title.pack(fill="x")
        self._empty_body = tk.Label(ins, text="", bg=T.CARD, fg=T.TXT2,
                                    font=T.T_BODY_SM(), anchor="w", justify="left",
                                    wraplength=T.sp(520))
        self._empty_body.pack(fill="x", pady=(4, 0))
        T.fill_wrap(self._empty_body, pad=6)
        self._empty_chip_host = tk.Frame(ins, bg=T.CARD)
        self._empty_chip_host.pack(fill="x", pady=(10, 2))
        self._empty_card = card

    def _paint_meta(self):
        self.meta_lbl.config(text=self._meta_txt or "")
        scholar_view = bool(self.rows) and not (self._mode == "school" and not self._school)
        self._sync_meta_buttons(scholar_view)
        if self._mode == "school" and self._school:
            if not self.btn_back.winfo_manager():
                self.btn_back.pack(side="left", padx=(10, 0))
        else:
            self.btn_back.pack_forget()

    def _sync_meta_buttons(self, show):
        for b in (self._toggle, self.btn_export, self.btn_copy):
            try:
                b.pack_forget()
            except Exception:
                pass
        if not show:
            return
        self._toggle.pack(side="right")
        self.btn_export.pack(side="right", padx=(0, 6))
        self.btn_copy.pack(side="right", padx=(0, 6))
        try:
            self._toggle.set_value(self._layout)
        except Exception:
            pass

    def _render_rows(self):
        self.scroll.clear()
        self._card_frames = []
        self._row_frames = []
        self._flow_layout = None
        if self._layout == "grid":
            self._render_cards()
        else:
            self._render_list()
        if self._mode == "search" and self._found_total > len(self.rows):
            wrap = tk.Frame(self.scroll.inner, bg=T.CARD)
            wrap.pack(fill="x", pady=(8, 4))
            cap = 180 if self._layout == "list" else 60
            if len(self.rows) >= cap:
                tk.Label(wrap, text="平铺每页 60 位 · 切到「列表」可继续加载",
                         bg=T.CARD, fg=T.TXT4, font=T.T_CAPTION()).pack()
            else:
                T.Btn(wrap, "再加载 %d 位（已显示 %d / %s）" % (
                    min(60, self._found_total - len(self.rows)), len(self.rows),
                    _fmt_int(self._found_total)), self._load_more, "ghost").pack()

    # ---- 平铺卡片
    def _render_cards(self):
        host = tk.Frame(self.scroll.inner, bg=T.CARD)
        host.pack(fill="x")
        for i, a in enumerate(self.rows):
            self._card_frames.append(self._advisor_card(host, a, i))
        self._flow(host, self._card_frames, min_card=T.sp(230), max_cols=3)

    def _advisor_card(self, parent, a, idx):
        adv = a.get("advisor") or {}
        bg = T.CARD_HI
        card = tk.Frame(parent, bg=bg, cursor="hand2", highlightthickness=1,
                        highlightbackground=T.LINE_SOFT, highlightcolor=T.LINE_SOFT)
        inner = tk.Frame(card, bg=bg)
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        # 底栏先占位：网格里同一行的卡片会被拉成等高，脚注才能贴住底部
        foot = tk.Frame(inner, bg=bg)
        foot.pack(side="bottom", fill="x", pady=(8, 0))
        tk.Frame(foot, bg=T.LINE_SOFT, height=1).pack(fill="x", pady=(0, 6))
        frow = tk.Frame(foot, bg=bg)
        frow.pack(fill="x")
        tk.Label(frow, text=self._verify_note(adv), bg=bg, fg=T.TXT4,
                 font=T.T_CAPTION(), anchor="w").pack(side="left")
        tk.Label(frow, text="查看详情 →", bg=bg, fg=T.ACCENT,
                 font=T.T_CAPTION(), anchor="e").pack(side="right")

        top = tk.Frame(inner, bg=bg)
        top.pack(fill="x")
        UK.Avatar(top, adv.get("name") or "?", size=T.sp(32), bg=bg).pack(
            side="left", anchor="n")
        info = tk.Frame(top, bg=bg)
        info.pack(side="left", fill="x", expand=True, padx=(8, 0))
        nrow = tk.Frame(info, bg=bg)
        nrow.pack(fill="x")
        tk.Label(nrow, text=adv.get("name") or "—", bg=bg, fg=T.TXT,
                 font=T.T_LABEL(), anchor="w").pack(side="left")
        if (adv.get("orcid") or "").strip():
            mark = tk.Label(nrow, text="✓", bg=bg, fg=T.OK, font=T.T_CAPTION(),
                            padx=4)
            mark.pack(side="left")
            self._tip(mark, "有 ORCID 记录，可到 orcid.org 核验")
        prov = self._province_of(adv)
        if prov:
            tk.Label(nrow, text=prov, bg=T.tint(T.ACCENT, 0.12, bg), fg=T.ACCENT,
                     font=T.T_CAPTION(), padx=6).pack(side="right")
        inst = adv.get("institution") or ""
        zh = self._inst_zh(inst)
        inst_txt = (zh + " · " + inst) if (zh and zh != inst) else (zh or inst or "机构未标注")
        _inst = tk.Label(info, text=inst_txt, bg=bg, fg=T.TXT3,
                         font=T.T_CAPTION(), anchor="w", justify="left",
                         wraplength=T.sp(230))
        _inst.pack(fill="x", pady=(1, 0))
        T.fill_wrap(_inst, pad=2)

        stats = tk.Frame(inner, bg=bg)
        stats.pack(fill="x", pady=(6, 0))
        cited = a.get("cited") or adv.get("cited_by_count") or 0
        works = adv.get("works_count") or 0
        tk.Label(stats, text="引用 %s · 论文 %s" % (_fmt_cited(cited), _fmt_int(works)),
                 bg=bg, fg=T.TXT4, font=T.M(8), anchor="w").pack(side="left")

        fields = adv.get("fields") or []
        kw = [str(x) for x in (adv.get("keywords") or []) if len(str(x)) <= 18]
        kw_txt = " / ".join([str(x) for x in fields[:3]] + kw[:2])
        if kw_txt:
            _kw = tk.Label(inner, text=kw_txt, bg=bg, fg=T.TXT3,
                           font=T.T_CAPTION(), anchor="w", justify="left",
                           wraplength=T.sp(240))
            _kw.pack(fill="x", pady=(4, 0))
            T.fill_wrap(_kw, pad=2)

        reasons = a.get("reasons") or []
        if reasons:
            weak = any("关联弱" in r for r in reasons)
            rrow = U.WrapRow(inner, bg=bg)
            rrow.pack(fill="x", pady=(6, 0))
            for r in reasons[:3]:
                color = T.WARN if weak else T.ACCENT
                lbl = tk.Label(rrow, text=r, bg=T.tint(color, 0.10, bg),
                               fg=color, font=T.T_CAPTION(), padx=6, pady=1)
                rrow.add(lbl)

        self._bind_click(card, idx, card)
        return card

    def _verify_note(self, adv):
        if (adv.get("orcid") or "").strip():
            return "ORCID 可核验"
        if (adv.get("url") or adv.get("homepage") or "").strip():
            return "个人主页已收录"
        return "仅索引记录"

    # ---- 列表行
    def _render_list(self):
        for i, a in enumerate(self.rows):
            self._row_frames.append(self._advisor_row(self.scroll.inner, a, i))

    def _advisor_row(self, parent, a, idx):
        adv = a.get("advisor") or {}
        outer = tk.Frame(parent, bg=T.CARD, highlightthickness=1,
                         highlightbackground=T.LINE_SOFT, highlightcolor=T.LINE_SOFT,
                         cursor="hand2")
        outer.pack(fill="x", pady=2)
        inner = tk.Frame(outer, bg=T.CARD_HI)
        inner.pack(fill="x", padx=10, pady=8)
        top = tk.Frame(inner, bg=T.CARD_HI)
        top.pack(fill="x")
        tk.Label(top, text=adv.get("name") or "—", bg=T.CARD_HI, fg=T.TXT,
                 font=T.T_LABEL(), anchor="w").pack(side="left")
        if (adv.get("orcid") or "").strip():
            tk.Label(top, text="✓", bg=T.CARD_HI, fg=T.OK,
                     font=T.T_CAPTION(), padx=4).pack(side="left")
        score = int(a.get("score") or 0)
        if score:
            col = T.OK if score >= 70 else (T.WARN if score >= 50 else T.TXT3)
            tk.Label(top, text="%d 分" % score, bg=T.CARD_HI, fg=col,
                     font=T.M(8, True)).pack(side="left", padx=(4, 0))
        cited = a.get("cited") or adv.get("cited_by_count") or 0
        if cited:
            tk.Label(top, text="引用 " + _fmt_cited(cited), bg=T.CARD_HI, fg=T.TXT4,
                     font=T.M(8)).pack(side="left", padx=(8, 0))
        prov = self._province_of(adv)
        if prov:
            tk.Label(top, text=prov, bg=T.CARD_HI, fg=T.TXT4,
                     font=T.T_CAPTION()).pack(side="right")
        inst = adv.get("institution") or ""
        zh = self._inst_zh(inst)
        inst_txt = (zh + " · " + inst) if (zh and zh != inst) else (zh or inst)
        line2 = "  ·  ".join(x for x in (inst_txt, adv.get("lab", "")) if x)
        if line2:
            _l2 = tk.Label(inner, text=line2, bg=T.CARD_HI, fg=T.TXT2,
                           font=T.T_CAPTION(), anchor="w", justify="left",
                           wraplength=T.sp(520))
            _l2.pack(fill="x", pady=(2, 0))
            T.fill_wrap(_l2, pad=22)
        fields = adv.get("fields") or []
        kw = adv.get("keywords") or []
        meta = "  ·  ".join([str(x) for x in fields[:4]] or
                            [str(x) for x in kw[:3]])
        if meta:
            _mt = tk.Label(inner, text=meta, bg=T.CARD_HI, fg=T.TXT4,
                           font=T.T_CAPTION(), anchor="w", justify="left",
                           wraplength=T.sp(520))
            _mt.pack(fill="x")
            T.fill_wrap(_mt, pad=22)
        reasons = a.get("reasons") or []
        if reasons:
            weak = any("关联弱" in r for r in reasons)
            _rt = tk.Label(inner, text="匹配依据：" + "、".join(reasons[:3]),
                           bg=T.CARD_HI, fg=(T.WARN if weak else T.ACCENT),
                           font=T.T_CAPTION(), anchor="w", justify="left",
                           wraplength=T.sp(520))
            _rt.pack(fill="x", pady=(2, 0))
            T.fill_wrap(_rt, pad=22)
        self._bind_click(outer, idx, outer)
        return outer

    # ---- 院校列表
    # Tk 的绘制坐标是 16 位，内容高于 32767px 后子控件直接不画；
    # 一张卡约 169px、三四列，360 张约 2 万像素，留足余量。
    _SCHOOL_PAGE = 120
    _SCHOOL_MAX = 360

    def _render_schools(self, keep=False):
        self.rows = []
        self._show_schools_layout()
        self.scroll.clear()
        self._card_frames = []
        self._row_frames = []
        self._school_host = None
        self._school_more_wrap = None
        if not keep:
            self._school_limit = self._SCHOOL_PAGE
        entries = self._school_entries() if self._all else []
        self._school_cache = entries
        prov = self.province.get()
        head = "共 %s 所院校" % _fmt_int(len(entries))
        if prov and prov != "全部":
            head += " · " + prov
        if self.entry.get().strip():
            head += " · 「%s」" % self.entry.get().strip()
        self._meta_txt = head
        self.meta_lbl.config(text=head)
        self._sync_meta_buttons(False)
        self.btn_back.pack_forget()

        if not entries:
            UK.EmptyPanel(self.scroll.inner, "没有匹配的院校",
                          "换一个院校名或地区试试；索引里只有带机构的学者才会出现在这里。",
                          icon="search", height=T.sp(200)).pack(fill="x", pady=(4, 0))
            self._after_build()
            return

        host = tk.Frame(self.scroll.inner, bg=T.CARD)
        host.pack(fill="x")
        self._school_host = host
        shown = entries[:self._school_limit]
        frames = []
        for g in shown:
            frames.append(self._school_card(host, g))
        self._school_frames = frames
        self._flow(host, frames, min_card=T.sp(220), max_cols=4)
        self._school_more()
        self._after_build()

    def _school_more(self):
        host = self._school_host
        if host is None:
            return
        if self._school_more_wrap is not None:
            try:
                self._school_more_wrap.destroy()
            except Exception:
                pass
            self._school_more_wrap = None
        total = len(getattr(self, "_school_cache", []) or [])
        shown = len(self._school_frames)
        if shown >= total:
            return
        wrap = tk.Frame(self.scroll.inner, bg=T.CARD)
        wrap.pack(fill="x", pady=(10, 4))
        self._school_more_wrap = wrap
        if shown >= self._SCHOOL_MAX:
            tk.Label(wrap, text="已显示前 %d 所 · 用地区或校名继续筛选" % shown,
                     bg=T.CARD, fg=T.TXT4, font=T.T_CAPTION()).pack()
            return
        T.Btn(wrap, "再加载 %d 所（已显示 %d / %s）" % (
            min(self._SCHOOL_PAGE, total - shown), shown, _fmt_int(total)),
            self._load_more_schools, "ghost").pack()

    def _load_more_schools(self):
        host = getattr(self, "_school_host", None)
        cache = getattr(self, "_school_cache", None)
        if host is None or not cache:
            return
        start = len(self._school_frames)
        end = min(start + self._SCHOOL_PAGE, len(cache), self._SCHOOL_MAX)
        if start >= end:
            return
        for g in cache[start:end]:
            self._school_frames.append(self._school_card(host, g))
        self._flow(host, self._school_frames, min_card=T.sp(220), max_cols=4)
        self._school_more()
        self._after_build()

    def _school_card(self, parent, g):
        bg = T.CARD_HI
        card = tk.Frame(parent, bg=bg, cursor="hand2", highlightthickness=1,
                        highlightbackground=T.LINE_SOFT, highlightcolor=T.LINE_SOFT)
        inner = tk.Frame(card, bg=bg)
        inner.pack(fill="both", expand=True, padx=12, pady=10)
        _zh = tk.Label(inner, text=g["zh"], bg=bg, fg=T.TXT, font=T.T_LABEL(),
                       anchor="w", justify="left", wraplength=T.sp(240))
        _zh.pack(fill="x")
        T.fill_wrap(_zh, pad=2)
        if g["inst"] and g["inst"] != g["zh"]:
            _en = tk.Label(inner, text=g["inst"], bg=bg, fg=T.TXT4,
                           font=T.T_CAPTION(), anchor="w", justify="left",
                           wraplength=T.sp(240))
            _en.pack(fill="x", pady=(2, 0))
            T.fill_wrap(_en, pad=2)
        bottom = tk.Frame(inner, bg=bg)
        bottom.pack(fill="x", side="bottom", pady=(8, 0))
        meta = " · ".join(x for x in (g["prov"] or "地区待补", "%d 位" % g["n"]))
        tk.Label(bottom, text=meta, bg=bg, fg=T.TXT3,
                 font=T.T_CAPTION(), anchor="w").pack(side="left")
        tk.Label(bottom, text="查看学者 →", bg=bg, fg=T.ACCENT,
                 font=T.T_CAPTION(), anchor="e").pack(side="right")
        self._bind_school(card, g["inst"])
        return card

    def _bind_school(self, w, inst):
        def walk(x):
            x.bind("<Button-1>", lambda e, _i=inst: self._open_school(_i))
            for c in x.winfo_children():
                walk(c)
        walk(w)

    def _bind_click(self, w, idx, frame):
        def enter(_e=None):
            col = T.ACCENT if idx == self._sel else T.ACCENT_D
            try:
                frame.configure(highlightbackground=col, highlightcolor=col)
            except Exception:
                pass

        def leave(_e=None):
            col = T.ACCENT if idx == self._sel else T.LINE_SOFT
            try:
                frame.configure(highlightbackground=col, highlightcolor=col)
            except Exception:
                pass

        def walk(x):
            x.bind("<Button-1>", lambda e, i=idx: self._select_row(i))
            x.bind("<Enter>", enter)
            x.bind("<Leave>", leave)
            for c in x.winfo_children():
                walk(c)
        walk(w)

    def _flow(self, host, frames, min_card, max_cols):
        state = {"cols": 0}

        def layout(_e=None):
            try:
                w = host.winfo_width()
            except Exception:
                return
            if w <= 1:
                return
            cols = int((w + 8) // (min_card + 8))
            cols = max(1, min(max_cols, cols))
            if cols == state["cols"]:
                return
            state["cols"] = cols
            for i in range(max_cols):
                host.grid_columnconfigure(
                    i, weight=(1 if i < cols else 0),
                    uniform=("flow" if i < cols else ""))
            for i, f in enumerate(frames):
                r, c = divmod(i, cols)
                f.grid_configure(
                    row=r, column=c, sticky="nsew",
                    padx=(0 if c == 0 else 8, 0),
                    pady=(0 if r == 0 else 8, 0))
        host.bind("<Configure>", layout)
        self._flow_layout = layout
        layout()

    def _after_build(self):
        """内容重建后重新量一次高度，否则 Canvas 会停在高度变化前的尺寸。"""
        self.update_idletasks()
        fn = self._flow_layout
        if fn:
            try:
                fn()
            except Exception:
                pass
        try:
            self.scroll._on_inner()
        except Exception:
            pass
        self.after(30, self.scroll._on_inner)

    # ------------------------------------------------------------ 详情
    def _select_row(self, i):
        if not (0 <= i < len(self.rows)):
            return
        self._sel = i
        frames = self._card_frames if self._layout == "grid" else self._row_frames
        for j, f in enumerate(frames):
            col = T.ACCENT if j == i else T.LINE_SOFT
            try:
                f.configure(highlightbackground=col, highlightcolor=col)
            except Exception:
                pass
        self._detail_show(self.rows[i])

    def _detail_empty(self):
        self.detail.clear()
        UK.EmptyPanel(self.detail.inner, "选中一位学者查看完整档案",
                      "左侧是按匹配度排的候选导师。单击任意一位，这里会显示院校、省份、"
                      "研究方向、引用量、匹配依据，以及能直接核验的 ORCID / 主页入口。",
                      icon="users", height=T.sp(230)).pack(fill="x")

    def _detail_show(self, a):
        adv = a.get("advisor", {})
        inst = adv.get("institution", "")
        zh = self._inst_zh(inst)
        prov = self._province_of(adv)
        score = int(a.get("score") or 0)
        self.detail.clear()
        box = self.detail.inner
        bg = T.CARD

        UK.eyebrow(box, "学者档案 / PROFILE", bg=bg).pack(fill="x")
        top = tk.Frame(box, bg=bg)
        top.pack(fill="x", pady=(8, 6))
        UK.Avatar(top, adv.get("name") or "?", size=T.sp(42), bg=bg).pack(
            side="left", anchor="n")
        info = tk.Frame(top, bg=bg)
        info.pack(side="left", fill="x", expand=True, padx=(10, 0))
        nrow = tk.Frame(info, bg=bg)
        nrow.pack(fill="x")
        tk.Label(nrow, text=adv.get("name") or "—", bg=bg, fg=T.TXT,
                 font=T.T_TITLE(), anchor="w").pack(side="left")
        if (adv.get("orcid") or "").strip():
            mark = tk.Label(nrow, text="✓", bg=bg, fg=T.OK, font=T.T_BODY_SM(),
                            padx=4)
            mark.pack(side="left")
            self._tip(mark, "有 ORCID 记录，可到 orcid.org 核验")

        inst_txt = (zh + " · " + inst) if (zh and zh != inst) else (zh or inst)
        if inst_txt:
            _in = tk.Label(info, text=inst_txt, bg=bg, fg=T.TXT2,
                           font=T.T_BODY_SM(), anchor="w", justify="left",
                           wraplength=T.sp(300))
            _in.pack(fill="x", pady=(2, 0))
            T.fill_wrap(_in, pad=2)
        sub = " · ".join(x for x in (prov, adv.get("lab", "")) if x)
        if sub:
            _sub = tk.Label(info, text=sub, bg=bg, fg=T.TXT4,
                            font=T.T_CAPTION(), anchor="w", justify="left",
                            wraplength=T.sp(300))
            _sub.pack(fill="x")
            T.fill_wrap(_sub, pad=2)

        # 三个数字
        nums = tk.Frame(box, bg=bg)
        nums.pack(fill="x", pady=(8, 2))
        cells = [("引用", _fmt_cited(a.get("cited") or adv.get("cited_by_count") or 0)),
                 ("论文", _fmt_int(adv.get("works_count") or 0))]
        if score:
            cells.append(("匹配", str(score)))
        for j in range(len(cells)):
            nums.grid_columnconfigure(j, weight=1, uniform="nm")
        for j, (k, v) in enumerate(cells):
            UK.StatTile(nums, v, k, bg=T.CARD_HI,
                        pad=T.sp(9)).grid(
                row=0, column=j, sticky="nsew", padx=(0 if j == 0 else 6, 0))
        note = "引用为 OpenAlex 口径" + ("，匹配分为方向关联度" if score else "")
        tk.Label(box, text=note, bg=bg, fg=T.TXT4, font=T.T_CAPTION(),
                 anchor="w").pack(fill="x", pady=(0, 6))

        fields = adv.get("fields") or []
        if fields:
            tk.Label(box, text="研究方向", bg=bg, fg=T.TXT3, font=T.T_CAPTION(),
                     anchor="w").pack(fill="x", pady=(2, 0))
            tagrow = U.WrapRow(box, bg=bg)
            tagrow.pack(fill="x", pady=(4, 6))
            for x in fields[:8]:
                lbl = tk.Label(tagrow, text=x, bg=T.tint(T.ACCENT, 0.12, T.CARD),
                               fg=T.ACCENT, font=T.T_CAPTION(), padx=8, pady=2)
                tagrow.add(lbl)
        kw = adv.get("keywords") or []
        if kw:
            _kw = tk.Label(box, text="关键词：" + " · ".join(str(x) for x in kw[:8]),
                           bg=bg, fg=T.TXT4, font=T.T_CAPTION(), anchor="w",
                           justify="left", wraplength=T.sp(300))
            _kw.pack(fill="x", pady=(0, 6))
            T.fill_wrap(_kw)

        if a.get("reasons"):
            tk.Label(box, text="为什么推荐他", bg=bg, fg=T.TXT2,
                     font=T.T_LABEL(), anchor="w").pack(fill="x", pady=(4, 2))
            for r in a["reasons"][:5]:
                color = T.WARN if "关联弱" in r else T.TXT2
                _r = tk.Label(box, text="·  " + r, bg=bg, fg=color,
                              font=T.T_BODY_SM(), anchor="w", justify="left",
                              wraplength=T.sp(300))
                _r.pack(fill="x")
                T.fill_wrap(_r)

        orcid = (adv.get("orcid") or "").strip()
        homepage = (adv.get("url") or adv.get("homepage") or "").strip()
        acts = U.WrapRow(box, bg=bg)
        acts.pack(fill="x", pady=(12, 4))
        if orcid:
            u = orcid if orcid.startswith("http") else "https://orcid.org/" + orcid
            acts.add(T.Btn(acts, "打开 ORCID", lambda _u=u: self.app.open_url(_u),
                           "primary"))
        if homepage:
            acts.add(T.Btn(acts, "打开个人主页",
                           lambda _u=homepage: self.app.open_url(_u)))
        q = (zh or inst) + " " + (adv.get("name") or "")
        acts.add(T.Btn(acts, "按院校 + 姓名检索",
                       lambda _q=q: self.app.open_url(
                           "https://www.bing.com/search?q=" + kb.quote_plus(_q))))
        acts.add(T.Btn(acts, "复制资料",
                       lambda _a=a: self._copy_advisor(_a)))

        note_bg = T.tint(T.WARN, 0.10, T.CARD)
        note = tk.Frame(box, bg=note_bg)
        note.pack(fill="x", pady=(12, 0))
        tk.Frame(note, bg=T.WARN, width=2).pack(side="left", fill="y")
        _n = tk.Label(note,
                      text="公开出版索引，不代表团籍、在职身份或招生名额。"
                           "发邮件前请看完最近两年的三篇代表作，并在官网核对。",
                      bg=note_bg, fg=T.TXT3, font=T.T_CAPTION(),
                      anchor="w", justify="left", wraplength=T.sp(300))
        _n.pack(fill="x", padx=10, pady=8)
        T.fill_wrap(_n, pad=20)
        try:
            self.detail._on_inner()
        except Exception:
            pass

    # ------------------------------------------------------------ 工具
    def _try_example(self, text):
        self._put_entry(text)
        self.search()

    def _target_url(self, a):
        adv = a.get("advisor", {})
        orcid = (adv.get("orcid") or "").strip()
        homepage = (adv.get("url") or adv.get("homepage") or "").strip()
        if orcid:
            return orcid if orcid.startswith("http") else "https://orcid.org/" + orcid
        if homepage:
            return homepage
        inst = adv.get("institution", "")
        zh = self._inst_zh(inst) or inst
        return "https://www.bing.com/search?q=" + kb.quote_plus(
            zh + " " + (adv.get("name") or ""))

    def _open_target(self, a):
        try:
            self.app.open_url(self._target_url(a))
        except Exception:
            pass

    def _copy_advisor(self, a):
        adv = a.get("advisor", {})
        inst = adv.get("institution", "")
        zh = self._inst_zh(inst)
        lines = ["姓名：" + (adv.get("name") or ""),
                 "院校：" + (zh + "（" + inst + "）" if zh and zh != inst else inst),
                 "省份：" + self._province_of(adv),
                 "实验室：" + (adv.get("lab") or "—"),
                 "方向：" + "、".join(str(x) for x in (adv.get("fields") or [])[:6]),
                 "引用：" + str(adv.get("cited_by_count") or "—"),
                 "匹配：" + str(a.get("score") or ""),
                 "依据：" + "、".join(a.get("reasons") or []),
                 "核验：" + (adv.get("orcid") or adv.get("url") or "无链接，按院校+姓名检索")]
        self.app.copy("\n".join(lines))
        self.app.toast("已复制该学者的资料", T.OK)

    def _tip(self, widget, text):
        """轻量提示：鼠标停留时在状态栏显示，不弹窗打扰。"""
        widget.bind("<Enter>", lambda e: self.app.toast(text, T.TXT3), add="+")

    def _copy_list(self):
        lines = []
        for a in self.rows:
            adv = a.get("advisor", {})
            inst = adv.get("institution", "")
            lines.append("%s · %s（%s）· %s 分 / %s" % (
                adv.get("name", ""), self._inst_zh(inst) or inst, inst,
                a.get("score", ""), adv.get("lab", "")))
        self.app.copy("\n".join(lines))
        self.app.toast("已复制 %d 位导师清单" % len(lines), T.OK)

    def export_csv(self):
        """导出为 CSV（带 BOM，Excel 直接打开不乱码）。

        学生常需要把候选导师清单发给导师、同学，或存进自己的表格。
        """
        if not self.rows:
            self.app.toast("还没有结果可导出", T.WARN)
            return
        import csv
        import datetime
        import os
        rows = []
        for a in self.rows:
            adv = a.get("advisor", {})
            inst = adv.get("institution", "")
            rows.append({
                "姓名": adv.get("name", ""),
                "中文名": adv.get("name_zh", ""),
                "院校": self._inst_zh(inst),
                "英文校名": inst,
                "省份": self._province_of(adv),
                "研究方向": "、".join(str(x) for x in (adv.get("fields") or [])[:5]),
                "引用量": adv.get("cited_by_count") or 0,
                "论文数": adv.get("works_count") or 0,
                "匹配分": a.get("score", ""),
                "匹配依据": "、".join(a.get("reasons") or []),
                "ORCID": adv.get("orcid") or "",
                "数据来源": "OpenAlex 公开出版索引（需官网核验）",
            })
        out_dir = kb.HERE / "exports"
        out_dir.mkdir(exist_ok=True)
        name = "导师清单-%s.csv" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = out_dir / name
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        except Exception as exc:
            self.app.toast("导出失败：" + str(exc), T.ERR)
            return
        self.app.toast("已导出 %d 位：%s" % (len(rows), name), T.OK)
        self.app.log("导师清单已导出：" + str(path), T.OK, force_open=True)
        try:
            os.startfile(str(path))
        except Exception:
            pass