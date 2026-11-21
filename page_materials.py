#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""素材库页：数据集目录，按大类 / 应用筛选，单条看指标、基线与官网。

数据来自竞赛 Web 版导出的 materials.json（competition/site/data/），
与网页素材库同一份快照；桌面端只做只读浏览，不下载数据、不调用外部接口。
"""
import json
import tkinter as tk
from pathlib import Path

import app_paths as P
import app_theme as T
import ui_kit as UK


def _label_px(font):
    """一个单行 Label 在给定字体下实际占的高度。

    实测（1440×900、125% 缩放）：T.T_LABEL() 的 Label `winfo_reqheight()`
    是 33，其中 linespace 28 + 默认 bd(2×2)=4 + pady(1×2)=2 —— 已经含在
    Tk 的几何里，所以这里只补 bd 与 pady，不额外加行间距余量，否则行高会
    虚高到 81（实测），列表一行能看出明显的空档。
    """
    import tkinter.font as tkfont
    f = tkfont.Font(root=tk._default_root, font=font)
    return f.metrics("linespace") + 4 + 2
import ui_parts as U
from page_venue import _Combo

HERE = Path(__file__).resolve().parent

PAGE_HINT = "公开数据集目录 · 按分类与应用筛选 · 单条看指标、基线、来源论文与官网"

MATERIALS_HELP = """\
这一页是离线数据集目录，回答「这个方向大家拿什么数据做实验」。

一、能查什么
· 按名称、任务、用途搜，或按 24 个分类、37 个应用领域筛。
· 每条给出任务、常用指标、常见基线、相关研究方向、来源论文与官网。

二、数字怎么来的
· 552 个数据集来自公开基准与论文整理，全部带官网地址；其中 401 个有
  来源论文链接，72 个只记录论文标题，79 个只有官方页面。
· 分类与应用计数按当前筛选池实时计算，不是全库固定值。

三、边界
· 目录不含许可证、下载量、最新榜单排名，也不替你下载数据。
· 官网链接可能随机构改版失效；使用前以官方页面为准。
· 指标与基线只是常见做法，不代表你的任务一定适用。"""


class _Tile(tk.Frame):
    """紧凑指标块：大号数字 + 说明；网格里不套 Card，避免互相撑高。"""

    def __init__(self, parent, value, label, bg):
        super().__init__(parent, bg=bg)
        self._v = tk.Label(self, text=str(value), bg=bg, fg=T.TXT,
                           font=T.F(13, True), anchor="w")
        self._v.pack(fill="x")
        self._l = tk.Label(self, text=str(label), bg=bg, fg=T.TXT4,
                           font=T.T_CAPTION(), anchor="w")
        self._l.pack(fill="x", pady=(T.sp(1), 0))

    def set(self, value, label=None):
        self._v.config(text=str(value))
        if label is not None:
            self._l.config(text=str(label))


def load_materials():
    """读素材库快照。打包态读 site_data/，开发态读 competition/site/data/。"""
    for path in (P.RES / "site_data" / "materials.json",
                 P.RES / "competition" / "site" / "data" / "materials.json",
                 HERE / "competition" / "site" / "data" / "materials.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("datasets"):
                return data
        except Exception:
            continue
    return {"datasets": [], "categories": [], "applications": [], "stats": {}}


def _fmt(n):
    try:
        return "{:,}".format(int(n))
    except Exception:
        return str(n)


class MaterialsPage(tk.Frame):
    ROW_H = None

    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.data = {}
        self.rows = []
        self.sel = -1
        self._lazy = None
        self._frames = {}
        self._tiles = {}
        self.cat = ""
        self.app_tag = ""
        self._build()
        self.after(80, self.reload)

    # ------------------------------------------------------------ 布局
    def _build(self):
        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=T.PAD, pady=(4, 0))
        T.Btn(head, "去选题工坊", lambda: self.app.goto("workshop")).pack(
            side="right")
        tk.Label(head, text="素材库", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE(), anchor="w").pack(side="left")

        cap = tk.Label(self,
                       text="方向、公开数据集与评测协议的关系索引；先确认数据存在、"
                            "指标可测、基线点名。",
                       bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                       justify="left")
        cap.pack(fill="x", padx=T.PAD, pady=(2, 0))
        T.fill_wrap(cap, pad=4)

        stats = T.Card(self, fill_y=False, pad=T.sp(8))
        stats.pack(fill="x", padx=T.PAD, pady=(6, 6))
        trow = tk.Frame(stats.body, bg=T.CARD)
        trow.pack(fill="x")
        for i, (key, label) in enumerate((("datasets", "公开数据集"),
                                          ("directions", "研究方向"),
                                          ("categories", "研究大类"),
                                          ("withPaper", "含来源论文"))):
            trow.grid_columnconfigure(i, weight=1, uniform="mat")
            tile = _Tile(trow, "—", label, T.CARD)
            tile.grid(row=0, column=i, sticky="nsew",
                      padx=(0, T.sp(6)) if i < 3 else 0)
            self._tiles[key] = tile

        fcard = T.Card(self, fill_y=False, pad=10)
        fcard.pack(fill="x", padx=T.PAD, pady=(0, 6))
        bar = tk.Frame(fcard.body, bg=T.CARD)
        bar.pack(fill="x")
        bar.grid_columnconfigure(0, weight=1)
        reset_btn = T.Btn(bar, "重置", self.reset)
        reset_btn.grid(row=0, column=3, padx=(8, 0))
        cat_f, self.cat_combo = self._pair(bar, "大类", 8)
        cat_f.grid(row=0, column=1, sticky="w", padx=(8, 0))
        app_f, self.app_combo = self._pair(bar, "场景", 8)
        app_f.grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.entry = tk.Entry(bar, bg=T.CARD_HI, fg=T.TXT,
                              insertbackground=T.ACCENT, relief="flat",
                              font=T.T_BODY())
        self.entry.grid(row=0, column=0, sticky="ew", ipady=6)
        T.fix_highlight(self.entry, T.card_edge(T.LINE, T.CARD))
        self._ph = "搜数据集、任务、方向，如「红外」"
        self.entry.insert(0, self._ph)
        self.entry.config(fg=T.TXT4)
        self.entry.bind("<FocusIn>", self._ph_in)
        self.entry.bind("<FocusOut>", self._ph_out)
        self.entry.bind("<KeyRelease>", lambda e: self.apply())
        self.entry.bind("<Return>", lambda e: self.apply())


        meta = tk.Frame(self, bg=T.BG)
        meta.pack(fill="x", padx=T.PAD, pady=(0, 4))
        self.count_lbl = tk.Label(meta, text="", bg=T.BG, fg=T.TXT4,
                                  font=T.T_CAPTION())
        self.count_lbl.pack(side="right")
        self.ctx_lbl = tk.Label(meta, text="", bg=T.BG, fg=T.TXT3,
                                font=T.T_CAPTION(), anchor="w", justify="left")
        self.ctx_lbl.pack(side="left", fill="x", expand=True)
        T.fill_wrap(self.ctx_lbl, pad=8)

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        body.grid_columnconfigure(0, weight=3, uniform="matbody")
        body.grid_columnconfigure(1, weight=2, uniform="matbody",
                                  minsize=T.sp(300))
        body.grid_rowconfigure(0, weight=1)

        self.card = T.Card(body, pad=0)
        self.card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        hrow = tk.Frame(self.card.body, bg=T.CARD)
        hrow.pack(fill="x", padx=0, pady=(2, 0))
        tk.Label(hrow, text="数据集", bg=T.CARD, fg=T.TXT4,
                 font=T.T_CAPTION(), anchor="w").pack(side="left",
                                                      padx=(12, 0))
        tk.Label(hrow, text="关联方向", bg=T.CARD, fg=T.TXT4,
                 font=T.T_CAPTION(), anchor="e").pack(side="right",
                                                       padx=(0, 14))
        tk.Frame(self.card.body, bg=T.LINE_SOFT, height=1).pack(
            fill="x", pady=(4, 0))
        self.scroll = T.ScrollArea(self.card.body, bg=T.CARD)
        self.scroll.pack(fill="both", expand=True)

        self.detail = T.Card(body, pad=14)
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.detail_box = T.ScrollArea(self.detail.body, bg=T.CARD)
        self.detail_box.pack(fill="both", expand=True)
        self._render_detail(None)

    def _pair(self, parent, label, width):
        f = tk.Frame(parent, bg=T.CARD)
        tk.Label(f, text=label, bg=T.CARD, fg=T.TXT3,
                 font=T.T_CAPTION()).pack(side="left", padx=(0, 5))
        cmd = self._set_cat if label == "大类" else self._set_app
        combo = _Combo(f, "", [("全部" + label, "")], cmd, width=width,
                       bg=T.CARD)
        combo.btn.pack(side="left")
        return f, combo

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
    def reload(self):
        self.data = load_materials()
        cats = [("全部分类", "")] + [
            (c.get("name") or "—", c.get("name") or "")
            for c in self.data.get("categories") or []
        ]
        apps = [("全部应用", "")] + [
            (a.get("name") or "—", a.get("name") or "")
            for a in self.data.get("applications") or []
        ]
        if hasattr(self, "cat_combo"):
            self.cat_combo.options = cats
            self.cat_combo.btn.config(text=self.cat_combo.label())
            self.app_combo.options = apps
            self.app_combo.btn.config(text=self.app_combo.label())
        stats = self.data.get("stats") or {}
        n_all = len(self.data.get("datasets") or [])
        n_paper = sum(1 for d in self.data.get("datasets") or []
                      if d.get("paperUrl"))
        vals = (("datasets", n_all),
                ("directions", stats.get("directions")),
                ("categories", stats.get("categories")),
                ("withPaper", n_paper))
        for key, v in vals:
            tile = self._tiles.get(key)
            if tile is not None:
                tile.set(_fmt(v) if v is not None else "—")
        self.apply()

    def _set_cat(self, value):
        self.cat = value
        self.apply()

    def _set_app(self, value):
        self.app_tag = value
        self.apply()

    def reset(self):
        self.entry.delete(0, "end")
        self.entry.insert(0, self._ph)
        self.entry.config(fg=T.TXT4)
        self.cat = ""
        self.app_tag = ""
        self.cat_combo.set("")
        self.app_combo.set("")
        self.apply()

    def _query(self):
        txt = self.entry.get() if self.entry.get() != self._ph else ""
        return (txt or "").strip().lower()

    def _match(self, d, q):
        if self.cat and self.cat not in (d.get("categories") or []):
            return False
        if self.app_tag and self.app_tag not in (d.get("applications") or []):
            return False
        if not q:
            return True
        blob = " ".join([
            d.get("name") or "", d.get("task") or "", d.get("note") or "",
            d.get("usedIn") or "", " ".join(d.get("categories") or []),
            " ".join(d.get("applications") or []),
            " ".join((x or {}).get("name") or "" for x in d.get("directions") or []),
        ]).lower()
        return q in blob

    def apply(self):
        q = self._query()
        data = self.data or load_materials()
        self.rows = [d for d in data.get("datasets") or [] if self._match(d, q)]
        n_all = len(data.get("datasets") or [])
        n_paper = sum(1 for d in self.rows if d.get("paperUrl"))
        self.count_lbl.config(text="%s / %s 个数据集" % (
            _fmt(len(self.rows)), _fmt(n_all)))
        if q or self.cat or self.app_tag:
            cond = " · ".join(x for x in (self.cat, self.app_tag) if x)
            bits = ["筛选出 %s 个" % _fmt(len(self.rows))]
            if cond:
                bits.append(cond)
        else:
            bits = ["全库 %s 个数据集" % _fmt(n_all)]
        bits.append("其中 %s 个有来源论文" % _fmt(n_paper))
        self.ctx_lbl.config(text=" · ".join(bits))
        self.render()
        if self.rows:
            self.select(0)
        else:
            self.sel = -1
            self._render_detail(None)

    # ------------------------------------------------------------ 列表
    def _row_h(self):
        if MaterialsPage.ROW_H is None:
            # 行高必须按**真实字高**算，不能只拍一个 sp(52)。
            # 行里竖着排两行字（数据集名 + 任务标签），Tk 给每个 Label 的
            # 请求高度都含 bd(2×2) 与 pady(1×2)；再加 mid 的 pady(sp(4))。
            # T.sp() 只乘字号档 _FS，不乘系统 DPI 的 _SCALE，而文字渲染时会乘 ——
            # 1920×1080@125% 下实测每行字要 33px，两行 66 + 上下 8 = 74，
            # 而原来算出来的 60 只够 1.5 行，第二行「图像分类 / 预训练」被压成
            # 16px、下半截直接消失。这里直接测字体行高，避免再靠猜。
            h = 0
            for font in (T.T_LABEL(), T.F(9)):
                try:
                    h += _label_px(font)
                except Exception:
                    h += T.sp(22)
            MaterialsPage.ROW_H = max(T.sp(52), h + T.sp(8) + 2)
        return MaterialsPage.ROW_H

    def render(self):
        try:
            if getattr(self, "_lazy", None) is not None:
                self._lazy.destroy()
        except Exception:
            pass
        self._lazy = None
        self._frames = {}
        self.scroll._lazy = None
        self.scroll.clear()
        if not self.rows:
            UK.EmptyPanel(self.scroll.inner, "没有匹配的数据集",
                          "换关键词或大类，或点重置。",
                          icon="search", bg=T.CARD, height=220,
                          cta="重置筛选", cta_cmd=self.reset).pack(
                              fill="x", pady=(6, 0))
            self.scroll.refresh()
            return
        lazy = U.LazyList(self.scroll, 0, self._build_row,
                          row_h=self._row_h(), bg=T.CARD)
        self._lazy = lazy
        lazy.pack(fill="x")
        lazy.bind("<Configure>", lambda e: lazy.fill(), add="+")
        try:
            self.scroll.canvas.bind("<Configure>",
                                    lambda e: lazy.fill(), add="+")
            self.scroll.canvas.bind(
                "<MouseWheel>", lambda e: lazy.after(1, lazy.fill), add="+")
            self.scroll.inner.bind("<Configure>",
                                   lambda e: lazy.fill(), add="+")
        except Exception:
            pass
        lazy.reset(len(self.rows))
        lazy.set_count(len(self.rows))
        self.scroll.refresh()
        self.scroll._on_inner()

    def _build_row(self, parent, i):
        if not (0 <= i < len(self.rows)):
            return None
        d = self.rows[i]
        f = tk.Frame(parent, bg=T.CARD, cursor="hand2",
                     height=self._row_h())
        f.pack_propagate(False)
        bar = tk.Frame(f, bg=T.CARD, width=3)
        bar.pack(side="left", fill="y")
        right = tk.Frame(f, bg=T.CARD, width=T.sp(76))
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        mid = tk.Frame(f, bg=T.CARD)
        mid.pack(side="left", fill="both", expand=True, padx=(8, 6),
                 pady=T.sp(4))

        name = tk.Label(mid, text=d.get("name") or "—", bg=T.CARD,
                        fg=T.TXT, font=T.T_LABEL(), anchor="w")
        name.pack(fill="x")
        task = (d.get("task") or "").strip() or "任务未标注"
        task_lb = tk.Label(mid, text=task, bg=T.CARD, fg=T.TXT3,
                           font=T.F(9), anchor="w")
        task_lb.pack(fill="x", pady=(1, 0))
        task_lb.bind("<Configure>",
                     lambda e, w=task_lb, t=task: self._fit_text(w, t))

        n_dir = int(d.get("directionCount") or len(d.get("directions") or []))
        meta = tk.Frame(right, bg=T.CARD)
        meta.place(relx=1.0, rely=0.5, anchor="e")
        meta.bind("<Configure>", lambda e: right.config(width=e.width + T.sp(8)))
        tk.Label(meta, text=("%d 个方向" % n_dir) if n_dir else "通用基准",
                 bg=T.CARD, fg=T.TXT3, font=T.F(9),
                 anchor="e").pack(side="top", anchor="e")

        line = tk.Frame(f, bg=T.LINE_SOFT, height=1)
        line.place(relx=0, rely=1.0, relwidth=1, anchor="sw")
        parts = [f, mid, name, task_lb, right, meta, bar, line]
        parts.extend(meta.winfo_children())
        self._frames[i] = (f, parts, line, bar)

        def pick(_e, idx=i):
            self.select(idx)

        for w in parts:
            w.bind("<Button-1>", pick)

        def hover(on):
            f._hover = on
            self._style(i)

        for w in (f, mid, name, task_lb, right, meta):
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", lambda e: hover(False), add="+")
        self._style(i)
        return f

    def _style(self, i):
        rec = self._frames.get(i)
        if not rec:
            return
        f, parts, line, bar = rec
        try:
            if not f.winfo_exists():
                return
        except Exception:
            return
        sel = (i == self.sel)
        hov = bool(getattr(f, "_hover", False))
        if sel:
            bg = T.tint(T.ACCENT, 0.10, T.CARD)
        elif hov:
            bg = T.tint(T.ACCENT, 0.05, T.CARD)
        else:
            bg = T.CARD
        for w in parts:
            try:
                if w is line:
                    w.config(bg=T.LINE_SOFT)
                elif w is bar:
                    w.config(bg=T.ACCENT if sel else bg)
                else:
                    w.config(bg=bg)
            except Exception:
                pass

    def select(self, i):
        if not (0 <= i < len(self.rows)):
            return
        old = self.sel
        self.sel = i
        if old != i:
            self._style(old)
        self._style(i)
        self._render_detail(self.rows[i])

    # ------------------------------------------------------------ 详情
    def _sec(self, parent, text):
        tk.Label(parent, text=text, bg=T.CARD, fg=T.TXT2, font=T.T_LABEL(),
                 anchor="w").pack(fill="x", padx=4, pady=(10, 2))

    def _para(self, parent, text, color=None):
        lb = tk.Label(parent, text=text, bg=T.CARD, fg=color or T.TXT2,
                      font=T.T_BODY_SM(), anchor="w", justify="left")
        lb.pack(fill="x", padx=6)
        T.fill_wrap(lb, pad=8)

    def _link(self, parent, text, url):
        lb = tk.Label(parent, text=text, bg=T.CARD, fg=T.ACCENT,
                      font=T.T_BODY_SM(), anchor="w", cursor="hand2",
                      justify="left")
        lb.pack(fill="x", padx=6)
        T.fill_wrap(lb, pad=8)
        lb.bind("<Button-1>", lambda e, u=url: self.app.open_url(u))

    def _chips(self, parent, names):
        row = U.WrapRow(parent, gap=6, rowgap=6, bg=T.CARD)
        row.pack(fill="x", padx=6, pady=(2, 0))
        # 高度不要写死 T.sp(24)：sp() 只乘字号档 _FS，不乘系统 DPI 的 _SCALE，
        # 而 Tk 渲染文字时会乘 _SCALE（1.25）—— 1920×1080 缩放下 24 实际只给到
        # 28px，文字却要 33px，「图像分类 / 预训练」这类标签被压扁、下半截裁掉。
        # hit_min() 正好是「最小可点高度」，已经考虑了档位，直接用它。
        for name in names:
            row.add(UK.Chip(row, name, bg=T.CARD, height=T.hit_min(),
                            font=T.T_CAPTION()))

    def _facts(self, parent, d):
        tint = T.tint(T.ACCENT, 0.05, T.CARD)
        box = tk.Frame(parent, bg=tint)
        box.pack(fill="x", padx=4, pady=(8, 2))
        vals = (("关联方向", len(d.get("directions") or [])),
                ("常用指标", len(d.get("metrics") or [])),
                ("代表基线", len(d.get("baselines") or [])))
        for i, (label, n) in enumerate(vals):
            box.grid_columnconfigure(i, weight=1, uniform="fact")
            cell = tk.Frame(box, bg=tint)
            cell.grid(row=0, column=i, sticky="nsew", padx=8, pady=6)
            tk.Label(cell, text=_fmt(n), bg=tint, fg=T.TXT,
                     font=T.F(12, True), anchor="w").pack(fill="x")
            tk.Label(cell, text=label, bg=tint, fg=T.TXT4,
                     font=T.T_CAPTION(), anchor="w").pack(fill="x")

    def _render_detail(self, d):
        box = self.detail_box
        box.clear()
        inner = box.inner
        if not d:
            UK.EmptyPanel(inner, "选中一个数据集",
                          "查看关联方向、指标、基线与官网入口。",
                          icon="search", bg=T.CARD, height=210).pack(
                              fill="x", pady=(6, 0))
            box.refresh()
            return

        UK.eyebrow(inner, "素材库 / DATASET RELATION", "02").pack(
            fill="x", padx=4, pady=(2, 4))
        tk.Label(inner, text=d.get("name") or "—", bg=T.CARD, fg=T.TXT,
                 font=T.T_TITLE(), anchor="w", justify="left").pack(
            fill="x", padx=4)
        task = (d.get("task") or "").strip()
        if task:
            self._para(inner, task, color=T.TXT3)

        chips = ((d.get("categories") or [])[:2]
                 + (d.get("applications") or [])[:2])
        if chips:
            self._chips(inner, chips)

        self._facts(inner, d)

        note = (d.get("note") or "").strip()
        if note:
            self._sec(inner, "简介")
            self._para(inner, note)

        used = (d.get("usedIn") or "").strip()
        if used:
            self._sec(inner, "常见使用场景")
            self._para(inner, used)

        metrics = d.get("metrics") or []
        if metrics:
            self._sec(inner, "常用指标")
            self._chips(inner, [str(x) for x in metrics])

        baselines = d.get("baselines") or []
        if baselines:
            self._sec(inner, "常见基线")
            self._chips(inner, [str(x) for x in baselines])

        dirs = d.get("directions") or []
        if dirs:
            names = [x.get("name") for x in dirs if x.get("name")]
            total = int(d.get("directionCount") or len(names))
            shown = names[:8]
            text = "、".join(shown)
            if total > len(shown):
                text += " 等 %d 个方向" % total
            self._sec(inner, "相关研究方向")
            self._para(inner, text, color=T.TXT3)

        self._sec(inner, "官网")
        url = (d.get("url") or "").strip()
        if url:
            self._link(inner, (d.get("name") or url) + " ↗", url)
            tip = tk.Label(inner, text=url, bg=T.CARD, fg=T.TXT4,
                           font=T.T_CAPTION(), anchor="w", justify="left")
            tip.pack(fill="x", padx=6)
            T.fill_wrap(tip, pad=8)
        else:
            self._para(inner, "没有收录官网地址。", color=T.TXT4)

        paper = (d.get("paperUrl") or "").strip()
        if paper:
            self._sec(inner, "来源论文")
            self._link(inner, (d.get("paperTitle") or paper) + " ↗", paper)

        foot = tk.Label(inner, text="许可、榜单与下载方式请以官网为准；"
                                   "这里的指标与基线只是常见做法。",
                        bg=T.CARD, fg=T.TXT4, font=T.T_CAPTION(),
                        anchor="w", justify="left")
        foot.pack(fill="x", padx=6, pady=(10, 8))
        T.fill_wrap(foot, pad=8)
        box.refresh()

    @staticmethod
    def _fit_text(lb, text, slack=10):
        """按像素宽度截断，末尾补省略号（中英文混排按字符截会忽长忽短）。"""
        try:
            w = lb.winfo_width()
            if w <= 1:
                return
            font = lb.cget("font")
            if lb.tk.call("font", "measure", font, text) <= w:
                if lb.cget("text") != text:
                    lb.config(text=text)
                return
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