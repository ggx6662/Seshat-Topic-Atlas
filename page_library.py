#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文献库页：本地 PDF 台账 + arXiv 新论文抓取。

复用 kb_widget 既有引擎（_inventory / kb_categories / kb_stats / seen_count /
task_status / run_preview / kbscan），不重复造轮子。
"""
import datetime
import os
import re
import threading
import time
import tkinter as tk

import app_theme as T

import kb_widget as kb
import kb_vector
import meta_index
import search_log
import semantic_search
import ui_parts as U
import ui_kit as UK

PAGE_HINT = "本地 PDF 全文台账 · 按方向抓 arXiv · 语义检索"

# 展开后的完整说明（默认只显示 "怎么用这一页 ?"）
LIB_HELP = (
    "这一页管的是「你手上已经有的 PDF」和「怎么再抓新的」。\n\n"
    "三件事：\n"
    "  1. 台账：下面是本地知识库目录里的全部 PDF，标题是从论文正文里抽出来的，"
    "不是文件名；作者/会议/年份来自同一次抽取，抽不到就留空而不是瞎猜。\n"
    "  2. 抓新论文：顶部「抓取新论文」按设置里的检索式去 arXiv / OpenAlex / Europe PMC 抓，"
    "先「抓取预演」看会抓什么再真抓。已经抓过的会按 arXiv id 去重，不会重复下载。\n"
    "  3. 两套检索（输入框在这里）：\n"
    "       · 文件名筛选 —— 只在本地 PDF 的文件名/标题/摘要里找，秒出结果\n"
    "       · 全库语义检索 / 多词交集 —— 查的是 arXiv cs 近三年 53.8 万篇的向量索引，"
    "首次要加载索引（几秒到半分钟），能搜到本地没有的论文\n\n"
    "**重要限制**：「语义检索」用的是 TF-IDF + SVD 降维（180 维），不是神经嵌入。"
    "它对「红外小目标检测」这类领域词很准，但对「去雾」这类低频方法词会退化 —— "
    "实测 10 条测试查询里 76% 找得到对的领域，去雾那条 0/5。"
    "所以我另外做了「多词交集」：每个词都必须出现，宁可少给也不给错。"
)

# 折叠成一行时用的短标签（展开后是完整提示）
METRIC_UNITS = {"pdf": "篇", "week": "篇", "seen": "条", "index": "篇", "query": "组"}


class _MetricProxy(object):
    """把 `Metric.set()` 的调用转写到顶部那行省略版概况。

    页面里多处写着 `self._m["pdf"].set(n)`。改成一行小字之后，如果每处都去改，
    很容易漏掉一处。这里保留同样的 `set()` 接口，内部攒够以后统一刷进 Label，
    这样原有调用一处都不用动。

    2026-11-15 第 9 版：原来是折叠成卡片条的，用户反馈「信息太多」——
    这些数字看一遍就够，占一整行不值得。现在是「220 篇 · 本周 0 · arXiv 4 · 索引 343」。
    """

    ORDER = [("pdf", "库内", " 篇"), ("week", "本周", " 篇"), ("seen", "arXiv", " 条"),
             ("index", "索引", " 篇"), ("query", "检索", " 组")]

    def __init__(self, page, key, label, unit):
        self._page, self._key, self._label, self._unit = page, key, label, unit
        self._val = None

    def set(self, value):
        self._val = value
        self._page._refresh_stats()

COLS = (("论文", 0), ("分类", 128), ("大小", 78), ("修改", 112))


def _cols():
    """三列的最小宽度，按当前字号等比放大。

    COLS 里的数字是「标准」字号下量出来的像素，字号调到 1.5 倍后
    「修改时间」四个字本身就比 112px 宽，会把整页撑出窗口。
    """
    fs = T.font_scale()
    return ((COLS[0][0], 0),) + tuple(
        (txt, int(round(w * fs))) for txt, w in COLS[1:])




class _Tile(tk.Frame):
    """紧凑指标块：一行大号数字 + 说明，不套 Card（网格里会互相撑高）。"""

    def __init__(self, parent, value, label, bg):
        super().__init__(parent, bg=bg)
        self._v = tk.Label(self, text=str(value), bg=bg, fg=T.TXT,
                           font=T.T_METRIC(), anchor="w")
        self._v.pack(fill="x")
        self._l = tk.Label(self, text=str(label), bg=bg, fg=T.TXT4,
                           font=T.T_CAPTION(), anchor="w")
        self._l.pack(fill="x", pady=(T.sp(1), 0))

    def set(self, value, label=None):
        self._v.config(text=str(value))
        if label is not None:
            self._l.config(text=str(label))

class LibraryPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.rows = []
        self.cats = []
        self.filter_cat = "全部"
        self.filter_text = ""
        self._busy = False
        self._m = {}
        self._filtered = []
        self._shown = 0
        self._more_btn = None
        self.search_mode = False
        self._mode = "filter"
        self._query = ""
        self._build()
        # 先用手上的台账（meta_index 走的是内存缓存）把列表铺出来，
        # 后台线程随后补「分类计数 / 入库节奏 / 语义索引」这些附加信息。
        self.after(10, self._quick_list)
        self.after(120, self.reload)

    # ------------------------------------------------------------ 布局
    def _build(self):
        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=T.PAD, pady=(4, 0))
        acts = tk.Frame(head, bg=T.BG)
        acts.pack(side="right")
        T.Btn(acts, "打开知识库目录", lambda: self._open(kb.kb_root())).pack(
            side="left", padx=(6, 0))
        T.Btn(acts, "抓取预演", self.do_preview).pack(side="left", padx=(6, 0))
        self.scan_btn = T.Btn(acts, "抓取新论文", self.do_scan, "primary")
        self.scan_btn.pack(side="left", padx=(6, 0))
        tk.Label(head, text="论文库", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE(), anchor="w").pack(side="left")

        _cap = tk.Label(self, text="本地 PDF 知识库：点行打开原文，右键看作者与摘要；"
                                   "抓取时才联网。",
                        bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                        justify="left")
        _cap.pack(fill="x", padx=T.PAD, pady=(2, 0))
        T.fill_wrap(_cap, pad=4)

        # ---- 指标条（网页版统计块）
        self._fold = None
        self._m = {}
        self._tiles = {}
        stats = T.Card(self, fill_y=False, pad=T.sp(8))
        stats.pack(fill="x", padx=T.PAD, pady=(6, 6))
        trow = tk.Frame(stats.body, bg=T.CARD)
        trow.pack(fill="x")
        for i, (key, label, unit) in enumerate(_MetricProxy.ORDER):
            trow.grid_columnconfigure(i, weight=1, uniform="stat")
            self._m[key] = _MetricProxy(self, key, label, unit)
            tile = _Tile(trow, "—", label + unit, T.CARD)
            tile.grid(row=0, column=i, sticky="nsew",
                      padx=(0, T.sp(6)) if i < 4 else 0)
            self._tiles[key] = tile

        # ---- 筛选卡：搜索行 + 分类胶囊
        fcard = T.Card(self, fill_y=False, pad=10)
        fcard.pack(fill="x", padx=T.PAD, pady=(0, 6))
        self._fcard = fcard
        fbody = fcard.body
        srch = tk.Frame(fbody, bg=T.CARD)
        srch.pack(fill="x")
        self._srch = srch
        self.clear_btn = T.Btn(srch, "清除", self.clear_filter)
        self.clear_btn.pack(side="right", padx=(6, 0))
        T.Btn(srch, "搜索", self.smart_search, "primary").pack(
            side="right", padx=(8, 0))
        self.entry = tk.Entry(srch, bg=T.CARD_HI, fg=T.TXT,
                              insertbackground=T.ACCENT, relief="flat",
                              font=T.T_BODY())
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        T.fix_highlight(self.entry, T.card_edge(T.LINE, T.CARD))
        self._ph = "输入想找的内容，支持中文，如「红外小目标漏检」"
        self.entry.insert(0, self._ph)
        self.entry.config(fg=T.TXT4)
        self.entry.bind("<FocusIn>", self._ph_in)
        self.entry.bind("<FocusOut>", self._ph_out)
        self.entry.bind("<Return>", lambda e: self.smart_search())
        try:
            import app_suggest
            app_suggest.attach(self.entry)
        except Exception as exc:
            print("联想词挂载失败:", exc)

        self.cat_box = U.WrapRow(fbody, gap=6, rowgap=6, bg=T.CARD)
        self.cat_box.pack(fill="x", pady=(8, 0))
        self._cats_open = True
        self._pace_lbl = tk.Label(fbody, text="", bg=T.CARD, fg=T.TXT3,
                                  font=T.T_BODY_SM(), anchor="w", justify="left")
        T.fill_wrap(self._pace_lbl, pad=8)
        self._pace_open = False
        self._pace_text = ""

        # ---- 结论行
        meta = tk.Frame(self, bg=T.BG)
        meta.pack(fill="x", padx=T.PAD, pady=(0, 4))
        self._pace_btn = UK.Chip(meta, "入库节奏", command=self._toggle_pace,
                                 bg=T.BG, height=T.sp(26),
                                 font=T.T_CAPTION())
        self._pace_btn.pack(side="right", pady=(2, 2))
        self.count_lbl = tk.Label(meta, text="", bg=T.BG, fg=T.TXT3,
                                  font=T.T_CAPTION(), anchor="w", justify="left")
        self.count_lbl.pack(side="left", fill="x", expand=True)

        def _wrap(_e=None):
            w = self.count_lbl.winfo_width()
            if w > 80:
                self.count_lbl.configure(wraplength=w - 4)
        self.count_lbl.bind("<Configure>", _wrap)

        self.vis = tk.Frame(self, bg=T.BG)

        # ---- 列表
        lcard = T.Card(self, pad=0)
        lcard.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        self._lcard = lcard
        hrow = tk.Frame(lcard.body, bg=T.CARD)
        hrow.pack(fill="x", padx=0, pady=(2, 0))
        hrow.grid_columnconfigure(0, weight=1)
        for i, (_, w) in enumerate(_cols()[1:], start=1):
            hrow.grid_columnconfigure(i, minsize=w, weight=0)
        tk.Label(hrow, text="论文", bg=T.CARD, fg=T.TXT4,
                 font=T.T_CAPTION(), anchor="w").grid(
                     row=0, column=0, sticky="ew", padx=(10, 6))
        for i, (txt, _w) in enumerate(_cols()[1:], start=1):
            tk.Label(hrow, text=txt, bg=T.CARD, fg=T.TXT4,
                     font=T.T_CAPTION(),
                     anchor=("e" if i in (1, 3) else "w")).grid(
                         row=0, column=i,
                         sticky=("e" if i in (1, 3) else "w"),
                         padx=(0, 18 if i == 1 else (10 if i == 3 else 0)))
        tk.Frame(lcard.body, bg=T.LINE_SOFT, height=1).pack(
            fill="x", pady=(4, 0))
        self.scroll = T.ScrollArea(lcard.body, bg=T.CARD)
        self.scroll.pack(fill="both", expand=True, padx=0, pady=0)

    # ------------------------------------------------------------ 占位符
    def _ph_in(self, _e=None):
        if self.entry.get() == self._ph:
            self.entry.delete(0, "end")
            self.entry.config(fg=T.TXT)

    def _ph_out(self, _e=None):
        if not self.entry.get().strip():
            self.entry.insert(0, self._ph)
            self.entry.config(fg=T.TXT4)

    # ------------------------------------------------------------ 数据
    def _quick_list(self):
        """不碰 _inventory（它会 stat 整个知识库目录），只用内存里的元数据。"""
        try:
            if getattr(self, "_quick_done", False):
                return
            self._quick_done = True
            self._build_rows_and_apply(quick=True)
        except Exception as exc:
            print("[library] 快速列表失败：%r" % (exc,))

    def _inventory_files(self):
        inv = kb._inventory()
        return inv.get("files", []) if isinstance(inv, dict) else (inv or [])

    def _build_rows_and_apply(self, quick=False):
        """把 _inventory 的文件列表整理成行并刷新界面。

        quick=True 时只用内存里的元数据，不去问 _inventory（它会 stat 整个
        知识库目录，345 个文件在机械盘上要几十毫秒到半秒）；分类计数、
        入库节奏、语义索引这些附加信息留给后台线程的那一趟。
        """
        rows = []
        try:
            files = self._inventory_files()
        except Exception:
            files = []
        for it in files:
            if isinstance(it, (tuple, list)) and len(it) >= 3:
                mtime, size, p = it[0], it[1], str(it[2])
            elif isinstance(it, dict):
                p = str(it.get("path", ""))
                mtime, size = it.get("mtime", 0), it.get("size", 0)
            else:
                continue
            if not p.lower().endswith(".pdf"):
                continue
            rel = os.path.relpath(p, str(kb.kb_root()))
            cat = rel.split(os.sep)[0] if os.sep in rel else "未分类(根目录)"
            name = os.path.basename(p)
            stem = re.sub(r"_+", " ", os.path.splitext(name)[0]).strip()
            mt = meta_index.get(p) or {}
            rows.append({
                "name": name,
                "title": (mt.get("title") or "").strip() or stem,
                "title_src": mt.get("title_src", ""),
                "abstract": (mt.get("abstract") or "").strip(),
                "authors": (mt.get("authors") or "").strip(),
                "year": mt.get("year"),
                "venue": mt.get("venue") or "",
                "is_survey": bool(mt.get("is_survey")),
                "cat": cat,
                "path": p,
                "size": size or 0,
                "mtime": mtime or 0,
                "arxiv": kb._arxiv_code(name),
            })
        rows.sort(key=lambda r: r["mtime"] or 0, reverse=True)
        now = datetime.datetime.now().timestamp()
        week = sum(1 for r in rows if r["mtime"] and now - r["mtime"] < 7 * 86400)
        data = dict(rows=rows, cats=kb.kb_categories(), stats=kb.kb_stats(),
                    seen=kb.seen_count(), sem={}, cfg=kb.load_config(), week=week,
                    quick=quick)
        if quick:
            self._apply(data)
        else:
            self.app.post(lambda: self._apply(data))

    def reload(self):
        threading.Thread(target=self._build_rows_and_apply, daemon=True).start()

    def _apply(self, d):
        self.rows = d["rows"]
        self.cats = d["cats"]
        self._m["pdf"].set(d["stats"].get("total_pdf", len(self.rows)))
        self._m["week"].set(d["week"])
        self._m["seen"].set(d["seen"])
        # quick 那一趟不带语义索引信息，别把已经有数字的指标冲成 0
        if d.get("quick") and (d.get("sem") or {}):
            pass
        elif d.get("quick"):
            self._m["pdf"].set(d["stats"].get("total_pdf", len(self.rows)))
        else:
            self._m["index"].set(int((d.get("sem") or {}).get("indexed") or 0))
        self._m["query"].set(len(d["cfg"].get("queries", [])))
        self._render_cats()
        self._render_vis()
        self._refresh_stats()
        # 台账落地后立即出列表：行是按滚动现建的，不必等后台线程。
        # 切走再切回时这条路径会重走一遍，实测能省掉整整一个线程往返（约 0.1 秒）。
        self.apply_filter()

    # ------------------------------------------------------------ 概况
    def _render_vis(self):
        """一句话概况：入库节奏 + 最近一条。分类分布不再重复 —— 分类条上已经带计数了。

        2026-11-15 第 9 版：原来两行（分类分布 + 入库节奏）常驻，
        而分类条上「Track 106」这样的数字已经说了一遍，重复。
        现在只留「入库节奏」，并且只有「没筛没搜」时才显示
        —— 筛过之后这行讲的是全库，帮不上忙，白占一行。
        """
        for w in self.vis.winfo_children():
            w.destroy()
        rows = getattr(self, "rows", None) or []
        if not rows:
            return
        months = {}
        for r in rows:
            t = r.get("mtime") or 0
            if not t:
                continue
            try:
                key = datetime.datetime.fromtimestamp(t).strftime("%Y-%m")
            except Exception:
                continue
            months[key] = months.get(key, 0) + 1
        if not months:
            return
        keys = sorted(months)[-4:]
        pace = " · ".join("%s %d" % (k[2:], months.get(k, 0)) for k in keys)
        # 第 19 版：这一行原来还要展示「入库节奏」，超大字下被挤成三行，
        # 把表头都顶出去了。节奏只在概况行（_stat_text）里给「最近入库」，
        # 完整节奏挪进 tooltip 式的 _vis_text，保留给其它调用点。
        self._vis_text = "入库节奏：" + pace + "；最近一条 " + max(months)

    def _vis_line(self, text):
        # 保留接口（老调用点用），实际不单独占行
        self._vis_text = text

    def _toggle_pace(self):
        """把「入库节奏」摊到分类条上面 —— 平时不占行，点开才看。"""
        try:
            if getattr(self, "_pace_open", False):
                self._pace_lbl.pack_forget()
                self._pace_open = False
                self._pace_btn.set_text("入库节奏")
                return
            self._pace_lbl.config(text=getattr(self, "_vis_text", "") or "暂无入库记录")
            self._pace_lbl.pack(fill="x", pady=(8, 0),
                                after=self.cat_box)
            self._pace_open = True
            self._pace_btn.set_text("收起")
        except Exception:
            pass

    def _refresh_stats(self):
        """把指标铺到统计块上；还没回来的项保留「—」。"""
        for key, short, unit in _MetricProxy.ORDER:
            p = self._m.get(key)
            v = getattr(p, "_val", None) if p else None
            tile = (self._tiles or {}).get(key)
            if tile is None:
                continue
            try:
                if v is None:
                    tile.set("—", short + unit)
                else:
                    tile.set(str(v), short + unit)
            except Exception:
                pass

    def _stat_text(self, only=None):
        """把概况拼成一句，不落盘（供 _refresh_stats 与测试复用）。"""
        parts = []
        for key, short, unit in _MetricProxy.ORDER:
            if only and key not in only:
                continue
            p = self._m.get(key)
            v = getattr(p, "_val", None) if p else None
            if v is None:
                continue
            # 短名带上单位，避免出现「篇 345 篇」这种重复
            parts.append("%s %s%s" % (short, v, unit))
        return "  ·  ".join(parts)

    def _render_cats(self):
        """分类条：横向铺一排胶囊，一行放得下就一行。

        原来是左侧一列 11 项的竖排树，常驻 196px 宽 —— 只有在点分类的那一下有用，
        其余时间都在抢正文宽度。改成横向胶囊后，正文多出近 200px
        （1320 窗口下标题能多显示 20 多个字符）。
        """
        old = getattr(self, "cat_box", None)
        if old is not None:
            old.destroy()
        self.cat_box = U.WrapRow(self._fcard.body, gap=6, rowgap=6, bg=T.CARD)
        self.cat_box.pack(fill="x", pady=(8, 0), after=self._srch)
        items = [("全部", len(self.rows))] + [(c["name"], c["count"]) for c in self.cats]
        for name, n in items:
            self.cat_box.add(UK.Chip(
                self.cat_box, name, count=n,
                active=(self.filter_cat == name),
                command=lambda nm=name: self._pick_cat(nm),
                bg=T.CARD, height=T.sp(26), font=T.T_CAPTION()))

    def _pick_cat(self, name):
        self.filter_cat = name
        self._render_cats()
        self.apply_filter()

    def apply_filter(self):
        txt = "" if self.entry.get() == self._ph else self.entry.get().strip().lower()
        self.filter_text = txt
        out = [r for r in self.rows
               if (self.filter_cat == "全部" or r["cat"] == self.filter_cat)
               and (not txt or txt in r["name"].lower())]
        if txt:
            search_log.log_query("file", txt, len(out))
        self._render_list(out)

    def smart_search(self):
        """一个入口，按输入自动决定怎么查（第 8 版简化）。

        原来界面并排放着四种检索按钮，用户得先知道它们差在哪才能按：
        「文件名筛选 / 语义检索 / 全库语义检索 / 多词交集检索」。实际上
        哪条路径合适，从输入本身就能判断：

            带空格或逗号、且 ≥2 个词  → 多词交集（每个词都得出现）
            单个英文短词              → 本地语义 + arXiv 全库语义
            中文 / 长描述             → 本地语义 + arXiv 全库语义

        用户只要写想找的东西、回车。arXiv 那条是后台补的，先出本地结果。
        """
        txt = "" if self.entry.get() == self._ph else self.entry.get().strip()
        if not txt:
            self.apply_filter()
            self._say()
            return
        # 判断是否走「多词交集」：词数 ≥2 且都不长（长句是描述，不是词）
        try:
            pos, neg = kb_vector.parse_terms(txt)
        except Exception:
            pos, neg = ([], [])
        words = [w for w in pos if w]
        if len(words) >= 2 and max(len(w) for w in words) <= 18:
            self.and_search()
        else:
            self.vector_search()
        # 本地库那一路也走一遍：本地 PDF 只有几百篇，几百毫秒就回来，
        # 先让用户看到自己库里的命中，arXiv 全库那条在后台接着跑。
        self._local_search(txt)

    def _local_search(self, txt):
        """本地语义检索（原「语义检索」按钮那条路），不阻塞界面。"""
        self.filter_text = txt
        self.search_mode = True
        try:
            hits = semantic_search.search(txt, limit=300)
        except Exception as e:
            self._search_failed(txt, str(e))
            return
        by_path = {r["path"]: r for r in self.rows}
        out = []
        for h in hits:
            r = by_path.get(h["path"]) or by_path.get(os.path.normcase(h["path"]))
            if r is None:
                for k, rr in by_path.items():
                    if os.path.normcase(k) == os.path.normcase(h["path"]):
                        r = rr
                        break
            if r is None:
                continue
            rr = dict(r)
            rr["_score"] = h["score"]
            rr["_reasons"] = h["reasons"]
            out.append(rr)
        self._apply_search(txt, out)
        self.filter_text = txt
        self.count_lbl.config(text="正在检索「%s」…" % txt)
        self.search_mode = True

        def work():
            try:
                hits = semantic_search.search(txt, limit=300)
                by_path = {r["path"]: r for r in self.rows}
                out = []
                for h in hits:
                    r = by_path.get(h["path"]) or by_path.get(
                        os.path.normcase(h["path"]))
                    if r is None:
                        # 索引里的路径与当前扫描路径大小写/斜杠不一致时兜底
                        for k, rr in by_path.items():
                            if os.path.normcase(k) == os.path.normcase(h["path"]):
                                r = rr
                                break
                    if r is None:
                        continue
                    rr = dict(r)
                    rr["_score"] = h["score"]
                    rr["_reasons"] = h["reasons"]
                    out.append(rr)
                self.app.post(lambda: self._apply_search(txt, out))
            except Exception as e:
                self.app.post(lambda: self._search_failed(txt, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _apply_search(self, q, out):
        # 分类筛选仍然生效
        if self.filter_cat != "全部":
            out = [r for r in out if r["cat"] == self.filter_cat]
        search_log.log_query("semantic", q, len(out))
        # 搜不到才值得记（画像有 500 条上限，正常命中不记）
        try:
            import profile_hooks as PH
            PH.search(q, "semantic", len(out), source="文献库")
        except Exception:
            pass
        self._render_list(out, mode="search", query=q)

    # ------------------------------------------------- arXiv 全库检索
    def _entry_text(self):
        t = self.entry.get()
        return "" if t == self._ph else t.strip()

    def vector_search(self):
        """arXiv 全库语义检索：一句话描述你的方向。"""
        q = self._entry_text()
        if not q:
            self._say("先在输入框里写一句想找的方向")
            return
        self._arx_start("全库语义检索")
        t0 = time.time()

        def work():
            try:
                hits = kb_vector.search(q, k=40)
                ms = int((time.time() - t0) * 1000)
                search_log.log_query("web", q, len(hits), ms)
                try:
                    import profile_hooks as PH
                    PH.search(q, "vector", len(hits), source="文献库")
                except Exception:
                    pass
                self.app.post(lambda: self._arx_render("vec", q, hits, ms, ""))
            except Exception as e:
                self.app.post(lambda: self._arx_fail(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def and_search(self):
        """多词交集检索：输入框里的每个词都必须出现（支持 -排除词）。"""
        q = self._entry_text()
        if not q:
            self._say("先在输入框里写几个词，空格或逗号分隔")
            return
        pos, neg = kb_vector.parse_terms(q)
        if len(pos) < 1:
            self._say("至少要一个「必须有」的词；- 开头的词不能单独用")
            return
        if len(pos) < 2 and not neg:
            self._say("多词交集至少要两个词；单查请用「全库语义检索」")
            return
        self._arx_start("多词交集检索")
        t0 = time.time()

        def work():
            try:
                r = kb_vector.search_and(q, k=40)
                ms = int((time.time() - t0) * 1000)
                search_log.log_query("and", q, r["count"], ms)
                try:
                    import profile_hooks as PH
                    PH.search(q, "and", r["count"], source="文献库")
                except Exception:
                    pass
                self.app.post(lambda: self._arx_render("and", q, r, ms, ""))
            except Exception as e:
                self.app.post(lambda: self._arx_fail(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _arx_start(self, what):
        self._say("%s中…（首次要加载索引，约 5–35 秒）" % what)
        self.count_lbl.config(text="%s中…" % what)

    def _arx_fail(self, err):
        self._say("检索失败：%s" % err)
        self.count_lbl.config(text="arXiv 全库检索失败")
        tk.Label(self.scroll.inner, text="检索失败：%s\n\n"
                                        "如果提示索引不完整，先跑一次：\n"
                                        "    python kb_vector.py --build" % err,
                 bg=T.BG, fg=T.WARN, font=T.F(10), justify="left",
                 anchor="w").pack(pady=30, padx=10, fill="x")
        self.scroll.refresh(defer=True)

    def _arx_render(self, mode, q, data, ms, note):
        """把 arXiv 结果画进同一个列表区（用卡片，不用台账列）。"""
        self.scroll.clear()
        self._filtered = []
        self._shown = 0
        self._mode = "arxiv"
        self._query = q
        self._more_btn = None
        # 收起概况行，把高度让给结果
        try:
            self.vis.pack_forget()
        except Exception:
            pass

        if mode == "and":
            papers = data["papers"]
            count = data["count"]
            terms = data["terms"]
            groups = data.get("groups") or []
            negs = data.get("negatives") or []
            before = data.get("count_before_exclude") or count
            head = "多词交集：「%s」  →  %s" % (q, " + ".join(terms))
            if negs:
                head += "   排除：" + " / ".join(negs)
            if negs and before != count:
                self.count_lbl.config(
                    text="命中 %d 篇（排除 %d 篇，原 %d 篇；同义写法已合并）  ·  %.1f 秒"
                         % (count, before - count, before, ms / 1000.0))
            else:
                self.count_lbl.config(
                    text="命中 %d 篇（同义写法已合并）  ·  %.1f 秒" % (count, ms / 1000.0))
            self._say("每个词都必须出现；同义写法内部算命中；- 开头的词必须不出现")
            # 把「你输入的词 → 实际等价于哪些写法」写出来。
            # 用户看不懂为什么「红外小目标」查不出东西时，这一行就是答案。
            if groups:
                box = tk.Frame(self.scroll.inner, bg=T.CARD_ALT if hasattr(T, "CARD_ALT") else T.CARD_HI)
                box.pack(fill="x", pady=(0, 8))
                for g in groups:
                    tk.Label(box, text="  ·  " + " / ".join(g[:6]),
                             bg=box["bg"], fg=T.TXT3, font=T.M(8),
                             anchor="w", justify="left").pack(fill="x", padx=8, pady=1)
        else:
            papers = data
            self.count_lbl.config(text="语义检索 Top%d  ·  %.1f 秒"
                                       % (len(papers), ms / 1000.0))
            self._say("按整句语义排序，和它意思接近的都会被找出来")
            head = "语义检索：「%s」" % q
        tk.Label(self.scroll.inner, text=head, bg=T.BG, fg=T.TXT2,
                 font=T.F(9, True), anchor="w").pack(fill="x", pady=(0, 4))

        if not papers:
            tk.Label(self.scroll.inner,
                     # 不手写 \n：Tk 在「有 \n 却没 wraplength」时会按最长行算
                     # 请求宽度，被容器压窄后各行仍按单行高排版，文字会叠起来。
                     text="一篇都没命中。多词交集查空通常是词太刁："
                          "换更通用的领域词（「红外」→「thermal」）；"
                          "去掉限定词只留两个核心词；或改用「全库语义检索」，"
                          "它不要求字面出现。",
                     bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), justify="left",
                     anchor="w", wraplength=T.wrap(680)).pack(
                         pady=30, padx=10, fill="x")
            self.scroll.refresh(defer=True)
            return

        for i, p in enumerate(papers[:20]):
            self._arx_row(p, i)
        if len(papers) > 20:
            tk.Label(self.scroll.inner, text="已显示 20 / %d 篇，要更多请收窄关键词"
                     % len(papers), bg=T.BG, fg=T.TXT4, font=T.M(8),
                     anchor="w").pack(fill="x", padx=10, pady=8)
        self.scroll.refresh(defer=True)
        self.scroll.scroll_to_top()

    def _arx_row(self, p, i):
        card = T.Card(self.scroll.inner, pad=10)
        card.pack(fill="x", pady=(0, 6))
        b = card.body
        top = tk.Frame(b, bg=T.CARD)
        top.pack(fill="x")
        # 先放右侧固定列，再让标题 expand —— 反了的话标题会把日期挤出去
        tk.Label(top, text="匹配 %.2f" % p.get("score", 0), bg=T.CARD,
                 fg=T.ACCENT if p.get("score", 0) > 0.5 else T.TXT3,
                 font=T.F(8, True)).pack(side="right")
        tk.Label(top, text=str(p.get("date", ""))[:10], bg=T.CARD, fg=T.TXT4,
                 font=T.M(8)).pack(side="right", padx=(0, 10))
        tk.Label(top, text=p.get("title", ""), bg=T.CARD, fg=T.TXT,
                 font=T.F(10, True), anchor="w", justify="left",
                 wraplength=T.wrap(760)).pack(side="left", fill="x", expand=True)

        sub = tk.Frame(b, bg=T.CARD)
        sub.pack(fill="x", pady=(3, 0))
        tk.Label(sub, text=str(p.get("cats", ""))[:40], bg=T.CARD, fg=T.TXT4,
                 font=T.M(8)).pack(side="left")
        T.Btn(sub, "打开 arXiv", lambda pid=p.get("id"): self._open(
            "https://arxiv.org/abs/" + str(pid)), "ghost").pack(side="right")
        T.Btn(sub, "复制标题", lambda t=p.get("title", ""): self._copy(t),
              "ghost").pack(side="right", padx=(0, 6))
        self._arx_cache = getattr(self, "_arx_cache", {})
        self._arx_cache[i] = p

    def _search_failed(self, q, err):
        self.count_lbl.config(text="检索失败：%s" % err)
        self.apply_filter()

    def clear_filter(self):
        self.filter_cat = "全部"
        self.search_mode = False
        self.entry.delete(0, "end")
        self.entry.insert(0, self._ph)
        self.entry.config(fg=T.TXT4)
        self._render_cats()
        self.apply_filter()

    def _render_list(self, rows, mode="filter", query=""):
        self.scroll.clear()
        self._filtered = rows
        self._shown = 0
        self._mode = mode
        self._query = query
        if mode == "search":
            bits = ["匹配 %d 篇" % len(rows), "语义检索：「%s」" % query]
        else:
            bits = ["共 %d 篇" % len(rows)]
        if self.filter_cat != "全部":
            bits.append("分类：" + self.filter_cat)
        if mode != "search" and self.filter_text:
            bits.append("关键词：" + self.filter_text)
        # 没筛没搜时顺手带上「最近入库」—— 那时它讲的就是眼前这批论文；
        # 筛过之后它讲的是全库，帮不上忙，不再重复。
        # 第 19 版：只报最近一条的时间，不再塞「26-06 24 · 26-07 125 …」整串
        # （超大字下那一串会把表头挤成三行）。
        bare = (self.filter_cat == "全部" and mode != "search"
                and not self.filter_text)
        # 不塞入库节奏：那一串在超大字下会把表头折成三行。节奏由
        # _stat_text() 的「本周 N 篇 / 索引 N 篇」体现；另在搜索行右侧常驻
        # 一个「节奏」按钮，点开才把这些月份摊出来（见 _toggle_pace）。
        self.count_lbl.config(text="  ·  ".join(bits),
                              wraplength=max(80, T.sp(160) - 24))
        if not rows:
            body = ("换个说法试试，支持中文，例如「红外小目标漏检」。"
                    if mode == "search" else
                    "点搜索右侧「清除」回到全部，或抓取新论文。")
            UK.EmptyPanel(self.scroll.inner, "没有匹配的论文", body,
                          icon="search", bg=T.CARD,
                          height=164).pack(fill="x", pady=(6, 0))
            self.scroll._on_inner()
            self.scroll.refresh(defer=True)
            return
        self._more_btn = None
        self._setup_lazy()
        self._lazy.reset(len(rows))
        self._lazy.set_count(len(rows))
        self.scroll.scroll_to_top()
        self.scroll.refresh()

    ROW_H = None

    def _row_h(self):
        if LibraryPage.ROW_H is None:
            LibraryPage.ROW_H = max(22, T.sp(28))
        return LibraryPage.ROW_H

    def _setup_lazy(self):
        """长列表的宿主（行按滚动位置现建，见 ui_parts.LazyList）。

        345 行一次性建完要 0.9 秒，而且切走再切回来还得重建一遍。
        """
        self._lazy = None
        self.scroll._lazy = None
        self._lazy = U.LazyList(self.scroll, 0, self._build_row,
                                row_h=self._row_h(), bg=T.CARD)
        for w in (self.scroll.canvas, self.scroll.inner):
            w.bind("<Configure>", lambda e: self._lazy.fill(), add="+")
        self.scroll.canvas.bind("<MouseWheel>",
                                lambda e: self._lazy.after(1, self._lazy.fill),
                                add="+")

    def _build_row(self, parent, i):
        rows = getattr(self, "_filtered", [])
        if not (0 <= i < len(rows)):
            return None
        f = tk.Frame(parent, bg=T.BG, height=self._row_h())
        self._row(rows[i], i, _outside=False, host=f)
        return f

    def _load_more(self):
        """兼容保留：列表已改成按滚动位置现建（`ui_parts.LazyList`），这里只补一次。

        以前是「先出 50 行 + 加载更多按钮」，切走再切回还得重来一遍；
        现在视口里滚动到哪就建到哪，页面上不再有「加载更多」。
        """
        lazy = getattr(self, "_lazy", None)
        if lazy is not None:
            lazy.fill()
        return
    def _row(self, r, idx, _outside=True, host=None):
        """一条一行：标题 + 会议/年份 + 分类 + 大小 + 时间。

        2026-11-15 第 9 版：原来是两行（标题一行、作者/会议一行）。
        实测 344 条里只有约一半有作者，没有作者的那一半第二行仍要占位，
        1320×880 一屏只能放 14 条。压成一行后能放 20 条以上。
        作者/摘要移到右键菜单的「查看详情」和打开 PDF 之后去看，
        扫标题本来就是这一页最常做的动作。
        """
        bg = T.CARD
        if _outside or host is None:
            f = tk.Frame(self.scroll.inner, bg=bg, cursor="hand2")
            f.pack(fill="x", pady=0)
        else:
            f = host
            f.configure(bg=bg, cursor="hand2")
        # 每行自己也要声明右侧三列的最小宽度：
        # 表头那个 Frame 上的 minsize 管不到这里，缺了它 grid 会按内容自然宽度
        # 分配，标题列只拿到「请求宽度 + 剩余量」，右侧会空出一大截却没人用。
        f.grid_columnconfigure(0, weight=1)
        for i, (_, w) in enumerate(_cols()[1:], start=1):
            f.grid_columnconfigure(i, minsize=w, weight=0)
        inner = tk.Frame(f, bg=bg)
        inner.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=4)
        inner.grid_columnconfigure(0, weight=1, minsize=80)

        title = r["title"]
        # 语义检索命中时给一个匹配度，放在标题前面比放第二行更省地方
        score = r.get("_score")
        if score is not None:
            title = "%d%%  %s" % (int(score * 100), title)
        lb = tk.Label(inner, text=title, bg=bg, fg=T.TXT, font=T.F(9), anchor="w",
                      justify="left")
        lb.grid(row=0, column=0, sticky="ew")
        # 会议 / 年份作为一条弱色小尾巴，跟在标题后面；列 0 weight=1 会吃掉余量，
        # 标题 Label 的宽度因此是「整行减尾巴」，截断才有意义。
        tail = "  ".join(b for b in ((r.get("venue") or ""),
                                     str(r.get("year") or ""),
                                     "综述" if r.get("is_survey") else "") if b)
        tail_lb = None
        if tail:
            tail_lb = tk.Label(inner, text="  " + tail, bg=bg, fg=T.TXT3,
                               font=T.T_CAPTION(), anchor="e")
            tail_lb.grid(row=0, column=1, sticky="e")
        # 按像素截断：建控件这一刻 winfo_width() 还是 1，先排一次 after 等布局完成；
        # 之后 Label 变宽变窄都重截（窗口缩放时靠它）。
        lb.after(0, lambda w=lb, t=title: self._fit_text(w, t))
        lb.bind("<Configure>", lambda e, w=lb, t=title: self._fit_text(w, t))

        if r.get("cat"):
            # 分类来自文件夹名，长短差很多（「新论文」4 字、「未分类(根目录)」7 字）。
            # 固定宽 + 弱色，超长按像素截断 —— 之前宽度不够会压到大小列上。
            cat_lb = tk.Label(f, text=r["cat"], bg=bg, fg=T.TXT3, font=T.T_CAPTION(),
                              anchor="e")
            cat_lb.grid(row=0, column=1, sticky="e", padx=(0, 18))
            cat_lb.bind("<Configure>",
                        lambda e, w=cat_lb, t=r["cat"]: self._fit_text(w, t))
        size_lb = tk.Label(f, text="%.1f MB" % (r["size"] / 1048576),
                           bg=bg, fg=T.TXT3, font=T.M(8), anchor="w", width=7)
        size_lb.grid(row=0, column=2, sticky="w")
        # 只显示「月-日 时:分」：这一列现在 118px，带年份会少最后一位。
        # 年份在右键「查看详情」和打开 PDF 时都能看到，不值得为它占 4 个字符。
        mt = (datetime.datetime.fromtimestamp(r["mtime"]).strftime("%m-%d %H:%M")
              if r["mtime"] else "—")
        mt_lb = tk.Label(f, text=mt, bg=bg, fg=T.TXT3, font=T.M(8), anchor="e",
                         width=11)
        mt_lb.grid(row=0, column=3, sticky="e", padx=(0, 10))
        if r["mtime"]:
            self.app._tip(mt_lb, datetime.datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M"))
        line = tk.Frame(f, bg=T.LINE_SOFT, height=1)
        line.place(relx=0, rely=1.0, relwidth=1, anchor="sw")
        parts = [f, inner, lb, size_lb, mt_lb, line]
        if r.get("cat"):
            parts.append(cat_lb)
        if tail_lb is not None:
            parts.append(tail_lb)
        for w in parts:
            w.bind("<Button-1>", lambda e, p=r["path"]: self._open_file(p))
            w.bind("<Button-3>", lambda e, p=r["path"]: self._row_menu(e, p))
        hover = T.tint(T.ACCENT, 0.06, T.CARD)

        def _paint(on):
            col = hover if on else bg
            for w in parts:
                try:
                    w.config(bg=col if w is not line else T.LINE_SOFT)
                except Exception:
                    pass
            if on:
                line.config(bg=T.tint(T.ACCENT, 0.35, bg))
        for w in (f, inner, lb, size_lb, mt_lb, tail_lb):
            if w is None:
                continue
            w.bind("<Enter>", lambda e: _paint(True), add="+")
            w.bind("<Leave>", lambda e: _paint(False), add="+")

    def _bind_ellipsis(self, lb, full=None):
        """按可用像素宽度截断文字，而不是按字符数。

        中英文混排时字符数和像素宽度不成比例（实测同一行里中文占 2 倍宽），
        按字符数截会出现「有的很早就断开、有的顶出可视区」。
        """
        text = full if full is not None else lb.cget("text")
        lb.bind("<Configure>", lambda e: self._fit_text(lb, text))

    @staticmethod
    def _fit_text(lb, text, slack=14):
        """把 text 截到 lb 当前宽度放得下为止，末尾补省略号。

        2026-11-19：可用宽度要扣掉 Label 自己的 bd 与左右 padx。原来直接拿
        `winfo_width()` 和 `font.measure()` 比，而 measure 只算字宽 ——
        默认 bd=2 + padx=1 会再吃掉 6px，于是「需要 786、只有 782」这种
        差几个像素的标题判断成「放得下」，尾巴就被切掉一两个字母。
        """
        try:
            w = lb.winfo_width()
            if w <= 1:
                return
            try:
                inset = (int(str(lb.cget("bd")) or 0)
                         + int(str(lb.cget("padx")) or 0)) * 2
            except Exception:
                inset = 6
            w = max(20, w - inset)
            font = lb.cget("font")
            if lb.tk.call("font", "measure", font, text) <= w:
                if lb.cget("text") != text:
                    lb.config(text=text)
                return
            # 二分找能放下的最长前缀
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if lb.tk.call("font", "measure", font, text[:mid]) <= w - slack:
                    lo = mid
                else:
                    hi = mid - 1
            lb.config(text=text[:max(1, lo)] + "…")
        except Exception:
            pass

    def _row_menu(self, e, path):
        # 作者/摘要不占正文行了，右键这里补一个「查看详情」
        m = tk.Menu(self, tearoff=0, bg=T.CARD, fg=T.TXT, activebackground=T.ACCENT_D,
                    activeforeground=T.ACCENT, bd=0, font=T.F(9))
        m.add_command(label="打开 PDF", command=lambda: self._open_file(path))
        m.add_command(label="查看详情（作者 / 摘要）",
                      command=lambda: self._show_detail(path))
        m.add_command(label="在资源管理器中显示", command=lambda: _reveal(path))
        m.add_command(label="复制文件名", command=lambda: self._copy(os.path.basename(path)))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _show_detail(self, path):
        """一条论文的完整信息：作者 / 会议 / 年份 / 摘要前几行。"""
        row = None
        for r in (getattr(self, "rows", None) or []):
            if r.get("path") == path:
                row = r
                break
        if not row:
            self.app.toast("找不到这条记录", T.ERR)
            return
        top = tk.Toplevel(self)
        top.title("论文详情")
        top.configure(bg=T.BG)
        top.geometry("620x420")
        box = tk.Frame(top, bg=T.BG)
        box.pack(fill="both", expand=True, padx=18, pady=14)
        tk.Label(box, text=row.get("title") or "", bg=T.BG, fg=T.TXT,
                 font=T.T_SECTION(), wraplength=T.wrap(540), anchor="w",
                 justify="left").pack(fill="x")
        meta = "  ·  ".join(b for b in ((row.get("venue") or ""),
                                        str(row.get("year") or ""),
                                        row.get("cat") or "",
                                        "综述" if row.get("is_survey") else "",
                                        "arXiv " + row["arxiv"] if row.get("arxiv") else "")
                           if b)
        tk.Label(box, text=meta or "—", bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(),
                 anchor="w").pack(fill="x", pady=(4, 8))
        if row.get("authors"):
            tk.Label(box, text="作者：" + row["authors"], bg=T.BG, fg=T.TXT2,
                     font=T.T_BODY_SM(), wraplength=T.wrap(560), anchor="w",
                     justify="left").pack(fill="x", pady=(0, 8))
        abst = row.get("abstract") or "（这篇没有抽到摘要）"
        txt = tk.Text(box, bg=T.CARD, fg=T.TXT2, relief="flat", wrap="word",
                      font=T.T_BODY_SM(), bd=0, padx=10, pady=8,
                      highlightthickness=1, highlightbackground=T.LINE)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", abst)
        txt.config(state="disabled")
        T.Btn(box, "打开 PDF", lambda: self._open_file(path)).pack(anchor="e", pady=(8, 0))

    def _row_menu(self, e, path):
        m = tk.Menu(self, tearoff=0, bg=T.CARD, fg=T.TXT, activebackground=T.ACCENT_D,
                    activeforeground=T.ACCENT, bd=0, font=T.F(9))
        m.add_command(label="打开 PDF", command=lambda: self._open_file(path))
        m.add_command(label="在资源管理器中显示", command=lambda: _reveal(path))
        m.add_command(label="复制文件名", command=lambda: self._copy(os.path.basename(path)))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _copy(self, s):
        self.app.toast("已复制：" + s[:40])

    def _open_file(self, p):
        try:
            os.startfile(p)
        except Exception as exc:
            self.app.toast("打开失败：" + str(exc), T.ERR)

    def _open(self, p):
        try:
            os.startfile(str(p))
        except Exception as exc:
            self.app.toast("打开失败：" + str(exc), T.ERR)

    # ------------------------------------------------------------ 抓取
    def do_scan(self):
        if self._busy:
            self.app.toast("已有任务在运行", T.WARN)
            return
        self._busy = True
        self.scan_btn.config(text="抓取中…")
        self.app.log("开始抓取 arXiv 新论文（近 %d 天）" % kb.load_config().get("days_back", 7),
                     force_open=True)

        def work():
            try:
                proc = kb.subprocess.run(
                    [kb._pythonw_exe(), str(kb.KBSCAN)],
                    capture_output=True, cwd=str(kb.HERE), timeout=60 * 30,
                    **_hidden())
                out = kb._decode_bytes(proc.stdout) + "\n" + kb._decode_bytes(proc.stderr)
                lines = [ln for ln in out.splitlines() if ln.strip()]
                tail = "\n".join(lines[-6:]) or "本轮无新增"
                fail = out.count("QUERY FAIL")
                total = max(1, len(kb.load_config().get("queries", [])))
                ok = fail < total
                msg = ("✔ 抓取完成" if ok else "✘ 查询全部失败（网络或 arXiv 不可达）") + "\n" + tail
            except Exception as exc:
                ok, msg = False, "✘ 抓取失败：" + str(exc)
            self.app.post(lambda: self._scan_done(ok, msg))
        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, ok, msg):
        self._busy = False
        self.scan_btn.config(text="抓取新论文")
        self.app.log(msg, T.OK if ok else T.ERR, force_open=True)
        self.reload()

    def do_preview(self):
        if self._busy:
            self.app.toast("已有任务在运行", T.WARN)
            return
        self._busy = True
        self.preview_btn.config(text="查询中…")
        self.app.log("抓取预演：只查询、不下载", force_open=True)

        def work():
            try:
                items = kb.run_preview()
            except Exception as exc:
                items = []
                self.app.post(lambda e=exc: self.app.log("预演失败：" + str(e), T.ERR, force_open=True))
            self.app.post(lambda: self._preview_done(items))
        threading.Thread(target=work, daemon=True).start()

    def _preview_done(self, items):
        self._busy = False
        self.preview_btn.config(text="抓取预演")
        T.close_child(self)
        win = T.child_window(self, "抓取预演 · 只列候选，不下载", "980x640")
        self._child_win = win
        tk.Label(win, text="抓取预演", bg=T.BG, fg=T.TXT,
                 font=T.F(15, True)).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(win, text="arXiv 当前候选 %d 篇。点击任意一行在浏览器打开 arXiv 核对，确认后回文献库点「抓取新论文」即可入库。"
                 % len(items), bg=T.BG, fg=T.TXT3, font=T.F(9)).pack(anchor="w", padx=18, pady=(0, 10))
        sa = T.ScrollArea(win)
        sa.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        if not items:
            tk.Label(sa.inner, text="没有候选。可能时间窗口内没有新论文，或网络不可达。",
                     bg=T.BG, fg=T.TXT4, font=T.F(10)).pack(pady=40)
        for it in items:
            f = tk.Frame(sa.inner, bg=T.CARD, cursor="hand2")
            f.pack(fill="x", pady=2)
            tk.Label(f, text=it.get("title", ""), bg=T.CARD, fg=T.TXT, font=T.F(9),
                     anchor="w", wraplength=T.wrap(880), justify="left").pack(
                fill="x", padx=10, pady=(7, 0))
            meta = " · ".join(str(x) for x in (it.get("id", ""), it.get("published", ""),
                                               it.get("query", "")) if x)
            tk.Label(f, text=meta, bg=T.CARD, fg=T.TXT3, font=T.M(8),
                     anchor="w").pack(fill="x", padx=10, pady=(0, 7))
            url = it.get("url") or (kb.ARXIV_ABS_URL + str(it.get("id", "")))
            f.bind("<Button-1>", lambda e, u=url: self.app.open_url(u))


def _hidden():
    try:
        return kb._hidden_kwargs()
    except Exception:
        return {"creationflags": 0x08000000} if os.name == "nt" else {}


def _reveal(path):
    """在资源管理器中选中该文件。"""
    try:
        kb.subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except Exception:
        try:
            os.startfile(os.path.dirname(path))
        except Exception:
            pass