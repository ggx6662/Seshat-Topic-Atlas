#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""期刊会议页：先按硬条件筛，再按方向找，最后看单条详情。

三种用法（对应页面上三个 tab）：
  1. 按条件筛 —— 我自己定：CCF 等级 / 会议还是期刊 / 哪个国家 / 哪个方向，
     直接给出符合的那份名单。不需要输入任何文字。
  2. 按方向找 —— 输入一个研究方向，交给 kb.recommend_venues 匹配，
     再按新加的硬条件过滤一遍。
  3. 单条详情 —— 点任何一个 venue，展开简介、为什么推荐、主办方与官网链接。

数据来自两个文件：
  venue_links.json  130 个 venue 的官网地址与链接文案
  venue_meta.json   CCF 等级 / 类型 / 国别 / 领域 / 一句话简介（make_venue_meta.py 生成）
"""
import json
import threading
import tkinter as tk

from tkinter import ttk
from pathlib import Path

import app_theme as T
from ui_parts import WrapRow   # 会自动折行的按钮排
import ui_parts as U
import ui_kit as UK
import kb_widget as kb
import kb_download as KB
import llm_bridge as L
import web_server as WS

HERE = Path(__file__).resolve().parent
META_FILE = HERE / "venue_meta.json"
LINKS_FILE = HERE / "venue_links.json"

PAGE_HINT = "按分区 / 国别 / 方向筛选 venue · 单条可展开看简介与官网"


def load_links():
    """读 venue_links.json['links']。缺文件或坏文件都返回空表，页面照常跑。

    2026-11-20：这张表从 130 条补到 705 条，并且每条多了 kind 字段，
    用来区分「组委会官网」和「DBLP 历年目录页」—— 后者点进去看不到
    截稿日期，界面上不能一律写成「官网」。
    """
    try:
        doc = json.loads(LINKS_FILE.read_text(encoding="utf-8"))
        links = doc.get("links") or {}
        return links if isinstance(links, dict) else {}
    except Exception:
        return {}


def _link_of(venues, links, name):
    """取一个 venue 的入口：优先 venue_meta 里的 url，其次链接表。

    返回 (url, label, kind)。kind 为 official / dblp / search / ""。
    """
    v = venues.get(name) or {}
    rec = links.get(name) or {}
    url = (v.get("url") or "").strip() or (rec.get("url") or "").strip()
    label = (v.get("label") or "").strip() or (rec.get("label") or "").strip()
    kind = (rec.get("kind") or "").strip()
    if not kind:
        u = url.lower()
        if not u:
            kind = ""
        elif "dblp." in u:
            kind = "search" if "/search" in u else "dblp"
        else:
            kind = "official"
    return url, label, kind


# DBLP 目录页不能叫「官网」：它只有历年论文集，没有截稿日期和模板。
_KIND_TAIL = {
    "official": "",
    "dblp": "（DBLP 目录，非官网）",
    "search": "（DBLP 检索，非官网）",
}


def _kind_tail(kind):
    return _KIND_TAIL.get(kind, "")


def _ellipsize(text, label, maxpx):
    """按 label 的实际字体宽度截断并补省略号（Tk Label 本身不会省略）。"""
    try:
        import tkinter.font as tkfont
        f = tkfont.Font(font=label.cget("font"))
        if f.measure(text) <= maxpx:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if f.measure(text[:mid] + "…") <= maxpx:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + "…"
    except Exception:
        return text

VENUE_HELP = """\
这一页只做三件事：筛出候选、告诉你为什么是它、给你官网入口。

一、筛选条件（「按条件筛」这一栏）
· CCF 等级：A / B / C 的来源是《中国计算机学会推荐国际学术会议和期刊目录》2022 版。
  「未收录」表示该 venue 不在那份目录里（例如 PRX Quantum、QIP、FIE），不代表它差。
· 国家/地区：按主办学会或出版社所在地归的（ACM/IEEE/USENIX 算美国，IACR 算国际）。
· 方向：这里的方向是 venue 自己的领域标签，不是你的研究方向。
· **没有中科院分区**。那套目录每年调整、没有公开的机器可读版，写死在软件里必然过期。
  需要分区请查中国科学院文献情报中心的当年度版本。同样没有影响因子与预警名单。

二、CCF 分级到底说明什么
它反映历史声誉，不反映录用难度。B 类里投不进去的比 A 类多的是——
按「A 类一定比 B 类难」来排序是会出错的。

三、匹配度是什么
「按方向找」给出的匹配分，是你的方向词与该 venue 征稿 scope 关键词的字面重合程度。
它说明「这个 venue 收不收这类工作」，不说明质量，也不说明录用概率。

四、建议的用法
选 3 个（1 个冲、1 个稳、1 个兜底），把它们的 scope 贴进「方法论 → 写作规范」，
让提示词按目标 venue 的语言习惯调整 framing。同一份工作换种说法，接收率差别很大。

五、细节一定回官网核对
截稿日期、模板、页数、版面费、特殊 issue 都可能临时变，软件里的链接直达官网，
以官网为准。"""

# 筛选下拉框的取值。键是内部值，值是显示文字。
_CCF_OPTS = [("全部等级", ""), ("CCF-A", "A"), ("CCF-B", "B"), ("CCF-C", "C"),
             ("未收录", "-")]
_TYPE_OPTS = [("会议+期刊", ""), ("只看会议", "会议"), ("只看期刊", "期刊")]


def load_meta():
    """读 venue_meta.json。文件不存在时返回空表，页面降级成「只有名称+链接」。"""
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"venues": {}, "fields": {}, "countries": {}, "note": ""}


class _Combo:
    """一个极简下拉框。

    没用 ttk.Combobox：它在深色主题下是系统原生控件，白底黑字完全融不进界面，
    而且 125% 缩放下高度对不齐。这里用 Button + Toplevel 菜单实现，
    颜色全部来自 token，两套主题都跟着走。
    """

    def __init__(self, parent, value, options, on_change, width=12, bg=None):
        self.options = list(options)
        self.value = value
        self.on_change = on_change
        self.btn = tk.Button(
            parent, text=self.label(), bg=bg or T.CARD, fg=T.TXT2,
            activebackground=T.CARD_HI, activeforeground=T.TXT,
            relief="flat", bd=0, font=T.T_BODY_SM(), cursor="hand2",
            anchor="w", padx=8, pady=4, width=width,
            highlightthickness=1, highlightbackground=T.card_edge(T.LINE, T.CARD or T.CARD))
        try:
            self.btn.config(highlightcolor=T.card_edge(T.LINE, T.CARD or T.CARD))
        except Exception:
            pass
        self.btn.config(command=self.popup)

    def label(self):
        for text, val in self.options:
            if val == self.value:
                return text
        return self.options[0][0] if self.options else "—"

    def set(self, value, notify=False):
        self.value = value
        self.btn.config(text=self.label())
        if notify and self.on_change:
            self.on_change(value)

    def popup(self):
        win = tk.Toplevel(self.btn)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=T.LINE)
        try:
            x = self.btn.winfo_rootx()
            y = self.btn.winfo_rooty() + self.btn.winfo_height() + 2
            win.geometry("+%d+%d" % (x, y))
        except Exception:
            pass
        box = tk.Frame(win, bg=T.CARD)
        box.pack(padx=1, pady=1)
        for text, val in self.options:
            fg = T.ACCENT if val == self.value else T.TXT2
            lb = tk.Label(box, text=text, bg=T.CARD, fg=fg, font=T.T_BODY_SM(),
                          anchor="w", padx=14, pady=5, cursor="hand2")
            lb.pack(fill="x")

            def pick(_e, v=val):
                win.destroy()
                self.set(v, notify=True)

            lb.bind("<Button-1>", pick)
            lb.bind("<Enter>", lambda e, w=lb: w.config(bg=T.CARD_HI))
            lb.bind("<Leave>", lambda e, w=lb: w.config(bg=T.CARD))
        win.bind("<FocusOut>", lambda e: win.destroy())
        try:
            win.focus_force()
        except Exception:
            pass


class VenuePage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.meta = load_meta()
        self.venues = self.meta.get("venues") or {}
        self.alias = self.meta.get("alias") or {}
        # 2026-11-20：入口链接表（含 kind，区分官网与 DBLP 目录）
        self.links = load_links()
        # 2026-11-20：方向→期刊会议是**大类级**的（见 _cat_covered）。实测
        # 24/25 个大类都登记了块级 venue，只有「应用领域」没有，问到
        # 「医疗影像」这类就只能退回全局热门。这一处要在页面上讲清楚，
        # 其他类不出这行字。
        self._cov = _cat_covered(self.venues, self.alias)
        self.rows = []
        self.mode = "filter"          # filter / match
        self.layout = "grid"
        self.sel = -1
        self._built = False
        self._mode_text = {"filter": "", "match": ""}
        self._grid_frames = []
        self._grid_host = None
        self._grid_token = 0
        self._grid_chunk = 18
        self._row_bars = {}
        self._build()
        self._built = True
        self._apply_filter()

    # ---------------------------------------------------------------- 布局
    def _coverage_text(self):
        n = len(self.venues)
        a = sum(1 for v in self.venues.values() if v.get("ccf") == "A")
        conf = sum(1 for v in self.venues.values() if v.get("type") == "会议")
        return "%d 个 venue · CCF-A %d 个 · %d 个会议" % (n, a, conf)

    def _build(self):
        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=T.PAD, pady=(4, 2))
        tk.Label(head, text=self._coverage_text(), bg=T.BG, fg=T.TXT3,
                 font=T.T_CAPTION(), anchor="e").pack(side="right")
        tk.Label(head, text="期刊会议", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE(), anchor="w").pack(side="left")
        U.Hint(self, VENUE_HELP,
               summary="数据来源与限制：CCF 2026 目录，不含影响因子与中科院分区",
               bg=T.BG).pack(fill="x", padx=T.PAD)

        self.tabs = UK.Segmented(
            self, [("filter", "全部", len(self.venues)), ("match", "按方向推荐")],
            value="filter", command=self.set_mode, bg=T.BG)
        self.tabs.pack(anchor="w", padx=T.PAD, pady=(8, 8))

        # 筛选卡：输入行 + 条件下拉 + 快捷胶囊
        self.fcard = T.Card(self, fill_y=False, pad=10)
        self.fcard.pack(fill="x", padx=T.PAD, pady=(0, 6))
        cb = self.fcard.body
        self._top = tk.Frame(cb, bg=T.CARD)
        self._top.pack(fill="x")
        self._entry_lbl = tk.Label(self._top, text="搜索名称 / 简介", bg=T.CARD,
                                   fg=T.TXT3, font=T.T_CAPTION())
        self._entry_lbl.pack(side="left", padx=(2, 8))
        self.entry = tk.Entry(self._top, bg=T.CARD_HI, fg=T.TXT,
                              insertbackground=T.ACCENT, relief="flat",
                              font=T.F(10))
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        T.fix_highlight(self.entry, T.card_edge(T.LINE, T.CARD))
        self.entry.bind("<Return>", lambda e: self._on_enter())
        self.btn = T.Btn(self._top, "筛选", self._on_enter, "primary")
        self.btn.pack(side="left", padx=(10, 0))

        # 条件下拉（两种模式共用；按方向推荐时用来二次收窄）
        self.bar = U.WrapRow(cb, gap=10, rowgap=6, bg=T.CARD)
        self.bar.pack(fill="x", pady=(8, 0))

        def _pair(text, opts, value="", width=8):
            f = tk.Frame(self.bar, bg=T.CARD)
            tk.Label(f, text=text, bg=T.CARD, fg=T.TXT3,
                     font=T.T_CAPTION()).pack(side="left", padx=(0, 5))
            combo = _Combo(f, value, opts, lambda v: self._on_filter(),
                           width=width, bg=T.CARD)
            combo.btn.pack(side="left")
            self.bar.add(f)
            return combo

        self.cb_ccf = _pair("CCF", _CCF_OPTS, width=8)
        self.cb_type = _pair("类型", _TYPE_OPTS, width=8)
        self.cb_cty = _pair("地区", self._country_opts(), width=8)
        self.cb_field = _pair("方向", self._field_opts(), width=9)

        self.quick = tk.Frame(cb, bg=T.CARD)
        self.quick.pack(fill="x", pady=(8, 0))
        self._quick_chips = []
        self._render_quick()

        # 结论行：结果数 + 口径 + 平铺/列表
        self.meta_row = tk.Frame(self, bg=T.BG)
        self.meta_row.pack(fill="x", padx=T.PAD, pady=(2, 4))
        self.meta_right = tk.Frame(self.meta_row, bg=T.BG)
        self.meta_right.pack(side="right")
        self.meta_lbl = tk.Label(self.meta_row, text="", bg=T.BG, fg=T.TXT3,
                                 font=T.T_CAPTION(), anchor="w", justify="left")
        self.meta_lbl.pack(side="left", fill="x", expand=True)

        def _wrap(_e=None):
            w = self.meta_lbl.winfo_width()
            if w > 80:
                self.meta_lbl.configure(wraplength=w - 4)
        self.meta_lbl.bind("<Configure>", _wrap)

        # 2026-11-20：方向→期刊会议只铺到 12 个大类，其余 13 类匹配出来只有
        # 15 条。这行平时是空的（不占高），只有那 13 类才出字，见 _match_note。
        self.note_lbl = tk.Label(self, text="", bg=T.BG, fg=T.TXT4,
                                 font=T.T_CAPTION(), anchor="w", justify="left")
        self.note_lbl.pack(fill="x", padx=T.PAD)

        def _wrap_note(_e=None):
            w = self.note_lbl.winfo_width()
            if w > 80:
                self.note_lbl.configure(wraplength=w - 4)
        self.note_lbl.bind("<Configure>", _wrap_note)

        tk.Label(self.meta_right, text="CCF 2026 · 不含影响因子", bg=T.BG,
                 fg=T.TXT4, font=T.T_CAPTION()).pack(side="left", padx=(0, 8))
        self.layout_seg = UK.Segmented(
            self.meta_right, [("grid", "平铺"), ("list", "列表")],
            value=self.layout, command=self._set_layout, bg=T.BG)
        self.layout_seg.pack(side="left")

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        body.grid_columnconfigure(0, weight=3, uniform="venue")
        body.grid_columnconfigure(1, weight=2, uniform="venue", minsize=T.sp(300))
        body.grid_rowconfigure(0, weight=1)

        self.card = T.Card(body, pad=8)
        self.card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.scroll = T.ScrollArea(self.card.body, bg=T.CARD)
        self.scroll.pack(fill="both", expand=True)

        self.detail = T.Card(body, pad=14)
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.detail_box = T.ScrollArea(self.detail.body, bg=T.CARD)
        self.detail_box.pack(fill="both", expand=True)
        self._render_detail(None)

    def _country_opts(self):
        have = {}
        for v in self.venues.values():
            have[v.get("country_cn") or "其他"] = True
        opts = [("全部地区", "")]
        for k in ("美国", "欧洲", "国际", "英国", "德国", "荷兰", "中国"):
            if k in have:
                opts.append((k, k))
        for k in sorted(have):
            if k not in dict(opts):
                opts.append((k, k))
        return opts

    def _field_opts(self):
        have = {}
        for v in self.venues.values():
            have[v.get("field_cn") or "其他"] = True
        opts = [("全部方向", "")]
        for cn in sorted(have):
            opts.append((cn, cn))
        return opts

    def _render_quick(self):
        for w in list(self.quick.winfo_children()):
            w.destroy()
        self._quick_chips = []
        ccf, tp = self.cb_ccf.value, self.cb_type.value
        items = [("全部", None, None, not ccf and not tp),
                 ("CCF-A", "ccf", "A", ccf == "A"),
                 ("CCF-B", "ccf", "B", ccf == "B"),
                 ("CCF-C", "ccf", "C", ccf == "C"),
                 ("未收录", "ccf", "-", ccf == "-"),
                 ("只看会议", "type", "会议", tp == "会议"),
                 ("只看期刊", "type", "期刊", tp == "期刊")]
        for text, kind, val, on in items:
            chip = UK.Chip(self.quick, text, active=on, font=T.T_CAPTION(),
                           command=lambda _k=kind, _v=val: self._quick_set(_k, _v))
            chip.pack(side="left", padx=(2 if not self._quick_chips else 0, 6))
            self._quick_chips.append(chip)

    def _quick_set(self, kind, val):
        if kind == "ccf":
            self.cb_ccf.set("" if self.cb_ccf.value == val else val)
        elif kind == "type":
            self.cb_type.set("" if self.cb_type.value == val else val)
        else:
            self.cb_ccf.set("")
            self.cb_type.set("")
        self._on_filter()

    def set_mode(self, mode):
        if mode not in ("filter", "match"):
            return
        self._mode_text[self.mode] = self.entry.get()
        self.mode = mode
        try:
            self.tabs.set_value(mode)
        except Exception:
            pass
        rec = (mode == "match")
        self._entry_lbl.config(text="研究方向" if rec else "搜索名称 / 简介")
        self.btn.config(text="匹配 venue" if rec else "筛选")
        self.entry.delete(0, "end")
        self.entry.insert(0, self._mode_text.get(mode, ""))
        self.meta_lbl.config(fg=T.TXT3)
        # 切回「全部」时把兜底说明收掉，免得它挂在筛选结果上面讲匹配的事
        try:
            if not rec:
                self.note_lbl.config(text="")
            else:
                self.note_lbl.config(text=self._match_note())
        except Exception:
            pass
        if rec:
            ctx = getattr(self, "_match_ctx", None)
            txt = self.entry.get().strip()
            if ctx and txt and ctx[0] == txt and getattr(self, "_match_rows", None):
                self.rows = [v for v in self._match_rows if self._pass(v)]
                self.sel = -1
                self._paint_meta(self._match_meta_text(self.rows))
                self.render(self.rows)
                if self.rows:
                    self.select(0)
                else:
                    self._render_detail(None)
            else:
                self._show_rec_empty()
        else:
            self._apply_filter()

    def _on_enter(self):
        if self.mode == "match":
            self.search()
        else:
            self._apply_filter()

    def _on_filter(self):
        try:
            self._render_quick()
        except Exception:
            pass
        if self.mode == "filter":
            self._apply_filter()
        else:
            self._refilter_match()

    # ---------------------------------------------------------------- 筛选
    def _query(self):
        return (self.entry.get() if self.mode == "filter" else "").strip().lower()

    def _pass(self, v):
        """一条 venue 是否通过当前硬条件。"""
        ccf = self.cb_ccf.value
        if ccf == "-":
            if v.get("ccf"):
                return False
        elif ccf and v.get("ccf") != ccf:
            return False
        tp = self.cb_type.value
        if tp and v.get("type") != tp:
            return False
        cty = self.cb_cty.value
        if cty and (v.get("country_cn") or "") != cty:
            return False
        fl = self.cb_field.value
        if fl and (v.get("field_cn") or "") != fl:
            return False
        q = self._query()
        if q:
            blob = " ".join(str(v.get(k) or "") for k in
                            ("name", "intro", "field_cn", "country_cn", "label"))
            if q not in blob.lower():
                return False
        return True

    def _sorted(self, rows):
        how = "ccf"
        _rank = {"A": 0, "B": 1, "C": 2, "": 3}
        if how == "name":
            return sorted(rows, key=lambda v: (v.get("name") or "").lower())
        if how == "field":
            return sorted(rows, key=lambda v: ((v.get("field_cn") or ""),
                                               _rank.get(v.get("ccf") or "", 3),
                                               (v.get("name") or "").lower()))
        return sorted(rows, key=lambda v: (_rank.get(v.get("ccf") or "", 3),
                                           (v.get("field_cn") or ""),
                                           (v.get("name") or "").lower()))

    def _apply_filter(self):
        rows = [v for v in self.venues.values() if self._pass(v)]
        rows = self._sorted(rows)
        self.rows = rows
        self.sel = -1
        cond = self._cond_text()
        head = "找到 %s 个 venue" % len(rows)
        if cond:
            head += " · " + cond
        q = self.entry.get().strip() if self.mode == "filter" else ""
        if q:
            head += " · 「%s」" % q
        self.meta_lbl.config(fg=T.TXT3)
        self._paint_meta(head)
        self.render(rows, head)
        if rows:
            self.select(0)
        else:
            self._render_detail(None)
            self._show_empty(
                "没有符合条件的 venue",
                "放宽条件，或清空看全部 %d 个。" % len(self.venues),
                cta="清除条件", cta_cmd=self.reset_filter)

    def _cond_text(self):
        parts = []
        if self.cb_ccf.value:
            parts.append("CCF-" + self.cb_ccf.value if self.cb_ccf.value != "-"
                         else "未收录")
        if self.cb_type.value:
            parts.append("只看" + self.cb_type.value)
        if self.cb_cty.value:
            parts.append(self.cb_cty.value)
        if self.cb_field.value:
            parts.append(self.cb_field.value)
        return " · ".join(parts)

    def _refilter_match(self):
        """「按方向推荐」之后再改条件：保留匹配分，只过滤。"""
        keep = [v for v in self.rows if self._pass(v)]
        keep = self._sorted(keep)
        self.rows = keep
        self.sel = -1
        head = self._match_meta_text(keep)
        if keep:
            self._paint_meta(head)
            self.render(keep, head)
            self.select(0)
        else:
            self._paint_meta("匹配结果里没有符合这些条件的 venue")
            self.render([], "")
            self._render_detail(None)
            self._show_empty(
                "匹配结果里没有剩下的",
                "推荐有结果，是叠加条件把它筛空了。\n清除后回到完整推荐。",
                cta="清除条件", cta_cmd=self.reset_filter)

    def reset_filter(self):
        self.cb_ccf.set("")
        self.cb_type.set("")
        self.cb_cty.set("")
        self.cb_field.set("")
        self._on_filter()

    # ---------------------------------------------------------------- 匹配
    def search(self, preset=None):
        if self.mode != "match":
            self.set_mode("match")
        text = (preset or self.entry.get()).strip()
        if not text:
            self.app.toast("请输入研究方向", T.WARN)
            return
        if preset:
            self.entry.delete(0, "end")
            self.entry.insert(0, preset)
        self.btn.config(text="匹配中…")

        def work():
            try:
                cat, field, conf = kb.infer_category_field(text)
                rels = kb.load_research_relations()
                pk = kb.field_profile(cat, field, rels) if (cat and field) else ""
                prof = (rels.get("profiles") or {}).get(pk, {})
                scen = (prof.get("scenarios") or [""])[0]
                meth = prof.get("methods", [])[:3]
                task = prof.get("tasks", [])[:2]
                mod = prof.get("modalities", [])[:2]
                rows = kb.recommend_venues(cat, field, scen, meth, task, mod, top=40)
                self.app.post(lambda: self._apply_match(text, cat, field, conf, rows))
            except Exception as exc:
                self.app.post(lambda e=exc: self._fail(e))
        threading.Thread(target=work, daemon=True).start()

    def set_context(self, cat, field):
        self.set_mode("match")
        self.entry.delete(0, "end")
        self.entry.insert(0, field)
        self.after(60, self.search)

    def _fail(self, exc):
        self.btn.config(text="匹配 venue")
        self.app.toast("匹配失败：" + str(exc), T.ERR)

    def _match_meta_text(self, rows):
        ctx = getattr(self, "_match_ctx", None)
        if ctx:
            text, cat, field, conf = ctx
            if cat and field:
                head = "按「%s」推荐 %d 个 · %s" % (text, len(rows), field)
            else:
                head = "按「%s」尽力匹配 %d 个 · 未识别学科" % (text, len(rows))
        else:
            head = "按方向推荐 %d 个 venue" % len(rows)
        cond = self._cond_text()
        if cond:
            head += " · " + cond
        return head

    def _match_note(self):
        """方向→期刊会议推不准的大类，补一句说明，别让人以为数据缺了。

        目前只有「应用领域」命中：它下面列的是医疗 / 教育 / 金融这类落地场景，
        没有块级 venue 表，问到「医疗影像」时推荐会退回全局热门。
        其余 24 个大类都有块级表，不出这行字。
        """
        ctx = getattr(self, "_match_ctx", None)
        if not ctx:
            return ""
        _text, cat, field, _conf = ctx
        if not cat or cat not in getattr(self, "_cov", set()):
            return ""
        where = "「%s」" % cat if not field else "「%s」（%s 类）" % (field, cat)
        return ("%s是应用场景、不是学科方向，还没登记对应的期刊会议，"
                "这里只能按大类兜底、容易退成热门会场。换成学科说法"
                "（比如「医学图像分割」「脑机接口」）能推得更准，"
                "也可以切回「全部」按 CCF 等级和方向筛选。" % where)

    def _apply_match(self, text, cat, field, conf, rows):
        """把 kb 的推荐结果和 venue_meta 合并；同名 venue 去重。

        去重靠 `self.alias`：venue_rules.json 里同一个 venue 的两种写法
        （TRO / T-RO、PoPETs / PETS、ATC / USENIX ATC）会被映射到规范名，
        否则列表里同一条会出现两次。
        """
        self.btn.config(text="匹配 venue")
        merged, seen = [], set()
        for r in (rows or []):
            nm = (r.get("name") or "").strip()
            canon = self.alias.get(nm, nm)
            if not canon or canon in seen:
                continue
            seen.add(canon)
            m = dict(self.venues.get(canon) or self.venues.get(nm) or {})
            base_intro = m.get("intro") or ""
            m.update({k: v for k, v in r.items() if v not in (None, "", [])})
            if base_intro:
                m["intro"] = base_intro
            m["name"] = canon
            merged.append(m)
        self._match_ctx = (text, cat, field, conf)
        self.rows = merged
        self._match_rows = merged
        self.meta_lbl.config(fg=T.OK if (cat and field) else T.WARN)
        self._refilter_match()
        try:
            self.note_lbl.config(text=self._match_note())
        except Exception:
            pass
        if not merged:
            self._show_empty(
                "这个方向没匹配到 venue",
                "换个更常见的名词再试，或切回「全部」。")

    # ---------------------------------------------------------------- 渲染
    def _paint_meta(self, text):
        self.meta_lbl.config(text=text or "")

    def _clear_scroll(self, token=None):
        try:
            if getattr(self, "_lazy", None) is not None:
                self._lazy.destroy()
        except Exception:
            pass
        self._lazy = None
        self.scroll._lazy = None
        self._grid_frames = []
        self._grid_host = None
        self._row_bars = {}
        self.scroll.clear()

    def render(self, rows, head=""):
        self._grid_token += 1
        token = self._grid_token
        self._clear_scroll(token)
        if not rows:
            return
        if self.layout == "grid":
            self._render_grid(rows, token)
        else:
            self._render_list(rows)

    # ---- 平铺卡片（分批建，首屏不等全部 126 张）
    def _render_grid(self, rows, token):
        host = tk.Frame(self.scroll.inner, bg=T.CARD)
        host.pack(fill="x")
        self._grid_host = host
        self._grid_rows = rows
        self._grid_next = 0
        self._grid_fill(token, self._grid_chunk)

    def _grid_fill(self, token, n):
        if token != self._grid_token or self._grid_host is None:
            return
        rows = self._grid_rows
        end = min(len(rows), self._grid_next + n)
        for i in range(self._grid_next, end):
            self._grid_frames.append(self._venue_card(self._grid_host, rows[i], i))
        self._grid_next = end
        self._flow(self._grid_host, self._grid_frames,
                   min_card=T.sp(200), max_cols=3)
        try:
            self.scroll._on_inner()
        except Exception:
            pass
        if end < len(rows):
            self.after(20, lambda: self._grid_fill(token, self._grid_chunk * 2))

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
                    uniform=("vflow" if i < cols else ""))
            for i, f in enumerate(frames):
                r, c = divmod(i, cols)
                f.grid_configure(row=r, column=c, sticky="nsew",
                                 padx=(0 if c == 0 else 8, 0),
                                 pady=(0 if r == 0 else 8, 0))
        host.bind("<Configure>", layout)
        self._flow_layout = layout
        layout()

    def _ccf_badge(self, parent, ccf, bg):
        if ccf in ("A", "B", "C"):
            col = {"A": T.OK, "B": T.ACCENT, "C": T.TXT3}[ccf]
            return tk.Label(parent, text="CCF-" + ccf, bg=T.tint(col, 0.12, bg),
                            fg=col, font=T.M(8, True), padx=6)
        return tk.Label(parent, text="目录外", bg=T.tint(T.TXT4, 0.10, bg),
                        fg=T.TXT4, font=T.T_CAPTION(), padx=6)

    def _venue_card(self, parent, v, idx):
        bg = T.CARD_HI
        card = tk.Frame(parent, bg=bg, cursor="hand2", highlightthickness=1,
                        highlightbackground=T.LINE_SOFT, highlightcolor=T.LINE_SOFT)
        inner = tk.Frame(card, bg=bg)
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        foot = tk.Frame(inner, bg=bg)
        foot.pack(side="bottom", fill="x", pady=(8, 0))
        tk.Frame(foot, bg=T.LINE_SOFT, height=1).pack(fill="x", pady=(0, 6))
        frow = tk.Frame(foot, bg=bg)
        frow.pack(fill="x")
        tk.Label(frow, text="详情 →", bg=bg, fg=T.ACCENT,
                 font=T.T_CAPTION()).pack(side="left")
        url, _lb, _kind = _link_of(self.venues, self.links,
                                   (v.get("name") or "").strip())
        if url:
            # 卡片上这一角只能放两个字：真官网写「官网」，DBLP 目录写
            # 「DBLP」。以前一律写「官网 ↗」，点进去只看到历年论文集，
            # 用户会以为被坑了。完整说明放在详情卡的链接区。
            link = tk.Label(frow, text=("DBLP ↗" if _kind in ("dblp", "search")
                                        else "官网 ↗"),
                            bg=bg, fg=T.TXT4, font=T.T_CAPTION(),
                            cursor="hand2")
            link.pack(side="right")
            link.bind("<Button-1>", lambda e, u=url: self.app.open_url(u))

        top = tk.Frame(inner, bg=bg)
        top.pack(fill="x")
        self._ccf_badge(top, v.get("ccf"), bg).pack(side="left")
        for key in ("type", "country_cn"):
            if v.get(key):
                tk.Label(top, text=v[key], bg=bg, fg=T.TXT4,
                         font=T.T_CAPTION()).pack(side="left", padx=(6, 0))

        name = v.get("name") or "—"
        _nm = tk.Label(inner, text=name, bg=bg, fg=T.TXT, font=T.T_LABEL(),
                       anchor="w", justify="left", wraplength=T.sp(220))
        _nm.pack(fill="x", pady=(5, 0))
        T.fill_wrap(_nm, pad=2)

        intro = (v.get("intro") or "").strip() or "暂无简介"
        if len(intro) > 66:
            intro = intro[:64] + "…"
        _in = tk.Label(inner, text=intro, bg=bg, fg=T.TXT3,
                       font=T.T_CAPTION(), anchor="w", justify="left",
                       wraplength=T.sp(220))
        _in.pack(fill="x", pady=(3, 0))
        T.fill_wrap(_in, pad=2)

        fl = v.get("field_cn")
        if fl:
            # 2026-11-20：领域标签要能折行。以前是裸 Label + anchor="w"，
            # 短标签（「软件工程」）看着没问题；但并入公开站数据后出现了
            # 复合领域（「数据库 / 数据挖掘 / 计算机科学理论」需要 338px），
            # 卡片只有 304px，整行被直接裁掉。这里与上面的名称/简介一致，
            # 也交给 T.fill_wrap 按卡片实际宽度折行。
            _fl = tk.Label(inner, text=fl, bg=T.tint(T.ACCENT, 0.10, bg),
                           fg=T.ACCENT, font=T.T_CAPTION(), padx=6, pady=1,
                           anchor="w", justify="left", wraplength=T.sp(220))
            _fl.pack(anchor="w", pady=(6, 0))
            T.fill_wrap(_fl, pad=2)

        self._bind_card(card, idx)
        return card

    def _bind_card(self, card, idx):
        def pick(_e):
            self.select(idx)
        def walk(w):
            w.bind("<Button-1>", pick)
            for c in w.winfo_children():
                if str(c.cget("cursor")) == "hand2" and c.winfo_class() == "Label":
                    continue
                walk(c)
        walk(card)

    # ---- 列表行（LazyList 虚拟化，固定行高）
    _ROW_H = None

    def _row_h(self):
        if VenuePage._ROW_H is None:
            VenuePage._ROW_H = T.sp(56)
        return VenuePage._ROW_H

    def _render_list(self, rows):
        self._setup_lazy()
        self._lazy.pack(fill="x")
        tk_ = self._lazy.reset(len(rows))
        self._lazy.set_count(len(rows))
        self.scroll.refresh()

    def _setup_lazy(self):
        if getattr(self, "_lazy", None) is None:
            self._lazy = U.LazyList(self.scroll, 0, self._build_row,
                                    row_h=self._row_h())
            self._lazy.bind("<Configure>", lambda e: self._lazy.fill(), add="+")
            try:
                self.scroll.canvas.bind("<Configure>",
                                        lambda e: self._lazy.fill(), add="+")
                self.scroll.canvas.bind("<MouseWheel>",
                                        lambda e: self._lazy.after(1, self._lazy.fill),
                                        add="+")
            except Exception:
                pass
            self.scroll.inner.bind(
                "<Configure>", lambda e: self._lazy.fill(), add="+")

    def _build_row(self, parent, i):
        if not (0 <= i < len(self.rows)):
            return None
        v = self.rows[i]
        bg = T.CARD
        f = tk.Frame(parent, bg=bg, cursor="hand2", height=self._row_h())
        self._row(f, v, i, _outside=False)
        return f

    def _row(self, parent, v, i, _outside=True):
        bg = T.CARD
        if _outside:
            f = tk.Frame(parent, bg=bg, cursor="hand2")
            f.pack(fill="x", pady=1)
        else:
            f = parent
        bar = tk.Frame(f, bg=(T.ACCENT if i == self.sel else bg), width=3)
        bar.pack(side="left", fill="y")
        self._row_bars[i] = bar
        holder = tk.Frame(f, bg=bg)
        holder.pack(side="left", fill="both", expand=True)
        tk.Frame(holder, bg=T.LINE_SOFT, height=1).pack(side="bottom", fill="x")

        try:
            cw = self.scroll.canvas.winfo_width()
        except Exception:
            cw = 500
        line = tk.Frame(holder, bg=bg)
        line.pack(fill="x", padx=10, pady=(6, 0))
        ccf = v.get("ccf")
        col = {"A": T.OK, "B": T.ACCENT, "C": T.TXT3}.get(ccf, T.TXT4)
        tk.Label(line, text=("CCF-" + ccf) if ccf in ("A", "B", "C") else "目录外",
                 bg=T.tint(col, 0.12, bg), fg=col, font=T.M(8, True),
                 padx=5).pack(side="left")
        n_lb = tk.Label(line, text=v.get("name") or "—", bg=bg, fg=T.TXT,
                        font=T.T_LABEL(), anchor="w")
        n_lb.pack(side="left", padx=(8, 0))
        _nm = _ellipsize(v.get("name") or "—", n_lb, max(90, cw - 260))
        if _nm != n_lb.cget("text"):
            n_lb.config(text=_nm)
        bits = " · ".join(x for x in (v.get("type"), v.get("country_cn"))
                          if x)
        if bits:
            tk.Label(line, text=bits, bg=bg, fg=T.TXT4,
                     font=T.T_CAPTION()).pack(side="left", padx=(8, 0))
        if v.get("score") is not None:
            tk.Label(line, text="匹配 %s" % v.get("score"), bg=bg, fg=T.OK,
                     font=T.M(8)).pack(side="right", padx=(0, 2))

        intro = (v.get("intro") or "").strip() or "点开看简介与官网"
        sub = tk.Label(holder, text=intro, bg=bg, fg=T.TXT3,
                       font=T.T_CAPTION(), anchor="w")
        sub.pack(fill="x", padx=10, pady=(1, 5))
        _in = _ellipsize(intro, sub, max(120, cw - 32))
        if _in != intro:
            sub.config(text=_in)

        def pick(_e, idx=i):
            self.select(idx)

        def hover(_e, on=True):
            try:
                nb = T.tint(T.ACCENT, 0.05, bg) if on else bg
                holder.config(bg=nb)
                line.config(bg=nb)
                n_lb.config(bg=nb)
                sub.config(bg=nb)
            except Exception:
                pass

        for w in (f, holder, line, sub, n_lb):
            w.bind("<Button-1>", pick)
            w.bind("<Enter>", lambda e: hover(True))
            w.bind("<Leave>", lambda e: hover(False))
            w.configure(cursor="hand2")
        url = (v.get("url") or "").strip()
        if url:
            for w in (f, holder, line, sub, n_lb):
                w.bind("<Double-Button-1>", lambda e, u=url: self.app.open_url(u))

    def _set_layout(self, value):
        if value == self.layout:
            return
        self.layout = value
        try:
            self.layout_seg.set_value(value)
        except Exception:
            pass
        if self._built and self.rows:
            self.render(self.rows)
            self.select(self.sel if 0 <= self.sel < len(self.rows) else 0)

    def select(self, i):
        if not (0 <= i < len(self.rows)):
            return
        self.sel = i
        if self.layout == "list":
            for j, b in getattr(self, "_row_bars", {}).items():
                try:
                    b.config(bg=(T.ACCENT if j == i else T.CARD))
                except Exception:
                    pass
        for j, f in enumerate(self._grid_frames):
            try:
                col = T.ACCENT if j == i else T.LINE_SOFT
                f.configure(highlightbackground=col, highlightcolor=col)
            except Exception:
                pass
        self._render_detail(self.rows[i], index=i)

    # ---------------------------------------------------------------- 空态
    def _show_rec_empty(self):
        self.rows = []
        self._paint_meta("输入方向后按类目与关键词推荐 venue")
        self._grid_token += 1
        self._clear_scroll()
        self._render_detail(None)
        self._show_empty(
            "先给一个方向",
            "输入一个方向，例如「三维重建」；只按关键词匹配，不预测录用。")

    def _show_empty(self, title, body, cta=None, cta_cmd=None):
        UK.EmptyPanel(
            self.scroll.inner, title, body, icon="search",
            height=T.sp(240), cta=cta, cta_cmd=cta_cmd).pack(
                fill="x", pady=(4, 0))
        try:
            self.scroll._on_inner()
        except Exception:
            pass

    # ---------------------------------------------------------------- 详情
    def _render_detail(self, v, index=-1):
        box = self.detail_box
        box.clear()
        inner = box.inner
        if not v:
            UK.EmptyPanel(
                inner, "选中一条查看详情",
                "点左侧任一条查看简介与官网。",
                icon="search", height=T.sp(190)).pack(fill="x")
            box.refresh()
            return

        bg = T.CARD
        UK.eyebrow(inner, "期刊会议 / VENUE PROFILE · CCF 2026", bg=bg).pack(
            fill="x")
        _t = tk.Label(inner, text=v.get("name") or "—", bg=bg, fg=T.TXT,
                      font=T.T_TITLE(), anchor="w", justify="left",
                      wraplength=T.sp(300))
        _t.pack(fill="x", pady=(6, 2))
        T.fill_wrap(_t, pad=4)

        row = U.WrapRow(inner, bg=bg)
        row.pack(fill="x", pady=(4, 2))
        ccf = v.get("ccf")
        col = {"A": T.OK, "B": T.ACCENT, "C": T.TXT3}.get(ccf, T.TXT4)
        row.add(tk.Label(row, text=("CCF-" + ccf) if ccf in ("A", "B", "C")
                         else "目录外", bg=T.tint(col, 0.12, bg), fg=col,
                         font=T.M(8, True), padx=6, pady=1))
        for key in ("type", "country_cn", "field_cn"):
            if v.get(key):
                row.add(tk.Label(row, text=v[key], bg=T.tint(T.ACCENT, 0.08, bg),
                                 fg=T.TXT2, font=T.T_CAPTION(), padx=6, pady=1))

        intro = (v.get("intro") or "").strip()
        if intro:
            self._para(inner, intro)
        else:
            self._para(inner, "这个 venue 还没有录入简介。", color=T.TXT4)

        reasons = v.get("reasons") or []
        if reasons:
            self._sec(inner, "为什么推荐它")
            self._para(inner, "、".join(str(r) for r in reasons))
        if v.get("score") is not None:
            self._para(inner,
                       "匹配分 %s：方向词与征稿 scope 的字面重合，只看收不收，"
                       "不代表录用概率。" % v.get("score"),
                       color=T.TXT3)

        url, _lb, _kind = _link_of(self.venues, self.links,
                                   (v.get("name") or "").strip())
        # 2026-11-20：小标题跟着链接类型走。701 条里只有 170 条是真官网，
        # 527 条是 DBLP 的历年目录；统称「官网」会让用户点进去找不到
        # 截稿日期，还以为软件给错了链接。
        if _kind == "official":
            self._sec(inner, "官网")
        elif _kind == "dblp":
            self._sec(inner, "论文集目录（DBLP）")
        elif _kind == "search":
            self._sec(inner, "入口（DBLP 检索）")
        else:
            self._sec(inner, "官网")
        if url:
            _base = _lb or ("打开官网" if _kind == "official" else "打开链接")
            link = tk.Label(inner, text=_base + _kind_tail(_kind) + " ↗",
                            bg=T.CARD_HI, fg=T.ACCENT, font=T.T_BODY_SM(),
                            anchor="w", cursor="hand2", padx=10, pady=6,
                            justify="left")
            link.pack(fill="x", padx=4, pady=(2, 4))
            link.bind("<Button-1>", lambda e, u=url: self.app.open_url(u))
            host = ""
            try:
                from urllib.parse import urlparse
                host = (urlparse(url).hostname or "").replace("www.", "")
            except Exception:
                pass
            if host:
                tk.Label(inner, text=host, bg=bg, fg=T.TXT4,
                         font=T.T_CAPTION(), anchor="w").pack(
                             fill="x", padx=6)
            if _kind in ("dblp", "search"):
                _d = tk.Label(
                    inner,
                    text=("这里只是 DBLP 记录的历年会议 / 期刊论文目录，"
                          "不含截稿日期、模板与版面费。投稿前请用 CCF 官网"
                          "或搜索引擎再确认一次当届主页。"
                          if _kind == "dblp" else
                          "这里只是 DBLP 站内检索结果，用来按名字找到这个会。"
                          "投稿信息请到 CCF 官网或搜索引擎再确认一次。"),
                    bg=bg, fg=T.TXT4, font=T.T_CAPTION(), anchor="w",
                    justify="left")
                _d.pack(fill="x", padx=6, pady=(2, 0))
                T.fill_wrap(_d, pad=8)
        else:
            self._para(inner, "没有收录官网地址。", color=T.TXT4)

        _tip = tk.Label(inner, text="截稿、模板、页数、版面费请以官网当次通知为准。",
                        bg=bg, fg=T.TXT4, font=T.T_CAPTION(), anchor="w",
                        justify="left")
        _tip.pack(fill="x", padx=6, pady=(8, 8))
        T.fill_wrap(_tip, pad=8)
        box.refresh()

    def _sec(self, parent, text):
        tk.Label(parent, text=text, bg=T.CARD, fg=T.TXT2, font=T.T_LABEL(),
                 anchor="w").pack(fill="x", padx=4, pady=(10, 2))

    def _para(self, parent, text, color=None):
        lb = tk.Label(parent, text=text, bg=T.CARD, fg=color or T.TXT2,
                      font=T.T_BODY_SM(), anchor="w", justify="left",
                      wraplength=T.sp(300))
        lb.pack(fill="x", padx=6, pady=(2, 0))
        T.fill_wrap(lb, pad=8)


class SettingsPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self._build()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.retry_btn = None
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        tk.Label(top, text="设置与数据", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE()).pack(side="left")
        cur = "暗色" if T.MODE == "dark" else "浅色"
        T.Btn(top, "切换主题 · %s" % cur, self.app.toggle_theme).pack(side="right")
        note = tk.Label(self, text="管理显示、路径与模型连接；配置和科研数据只存本机。",
                        bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w", justify="left")
        note.pack(fill="x", padx=T.PAD, pady=(0, 8))
        T.fill_wrap(note)

        # ScrollArea 必须先建：下面的分区都往 self.body 里塞。
        # （曾把「显示与字号」写在这里之前，_card() 找不到 self.body 直接崩）
        body = T.ScrollArea(self)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        self.body = body.inner
        self._scroll = body
        self._sections = {}

        # ---- 显示与字号（放在最上面：看不见 / 看着累是使用门槛，不是选项）
        c = self._card("显示与字号", "字太小看着累？四档可选，也可以按 Ctrl+= / Ctrl+-", open=True)
        _step_name = dict((k, n) for k, n, _f, _d in T.FONT_STEPS)
        row = U.WrapRow(c, bg=T.CARD, gap=6)
        row.pack(fill="x", pady=(2, 6))
        row.add(tk.Label(row, text="字号", bg=T.CARD, fg=T.TXT3,
                         font=T.T_CAPTION(), anchor="w"))
        for k, n, f, d in T.FONT_STEPS:
            on = (k == T.font_step()) and not self.app.font_auto()
            row.add(T.Btn(row, n, lambda _k=k: self.app.set_font_step(_k),
                          "primary" if on else "ghost"))
        auto_on = self.app.font_auto()
        row.add(T.Btn(row, "自动", self.app.set_font_auto,
                      "primary" if auto_on else "ghost"))
        T.para(c, "当前：%s（正文字号 ×%.2f%s）。档位只改字号与随之的间距，"
                  "不会把内容藏起来 —— 版面放不下时，页面会把次要信息收窄成更少的列。"
                  % (_step_name.get(T.font_step(), "标准"), T.font_scale(),
                     "，按屏幕自动适配" if auto_on else ""),
               color=T.TXT3, font=T.T_BODY_SM(), wrap_px=760, pady=(0, 4))
        T.para(c, "另外两件顺手的事：主题可切明暗（右上角的 ☾/☀）；"
                  "最小可点高度约 %d 像素，避免手抖点不中。"
               % T.hit_min(),
               color=T.TXT4, font=T.T_CAPTION(), wrap_px=760, pady=(0, 6))

        # 存储
        c = self._card("存储与路径", "知识库在哪、有多少篇", open=True)
        try:
            stats = kb.kb_stats()
        except Exception:
            stats = {}
        for k, v in (("知识库目录", str(kb.kb_root())),
                     ("新论文目录", str(kb.inbox_dir())),
                     ("监控程序目录", str(kb.HERE)),
                     ("知识库 PDF", "%s 篇  ·  txt %s 个" % (stats.get("total_pdf", "—"),
                                                          stats.get("total_txt", "—")))):
            self._kv(c, k, v)
        row = U.WrapRow(c, bg=T.CARD)
        row.pack(fill="x", pady=(8, 0))
        row.add(T.Btn(row, "打开知识库", lambda: self._open(kb.kb_root()),
                      "primary"))
        row.add(T.Btn(row, "打开新论文", lambda: self._open(kb.inbox_dir())))
        row.add(T.Btn(row, "打开监控目录", lambda: self._open(kb.HERE)))

        # 大模型（可选）
        self._build_llm()

        # 抓取
        c = self._card("arXiv 抓取", "抓取范围 · 检索词组 · 失败重试")
        try:
            cfg = kb.load_config()
        except Exception:
            cfg = {}
        self._kv(c, "抓取窗口", "近 %s 天" % cfg.get("days_back", "—"))
        self._kv(c, "每查询取", "%s 篇" % cfg.get("max_results_per_query", "—"))
        self._kv(c, "每轮最多下载", "%s 篇" % cfg.get("max_downloads", "—"))
        # 2026-11-15：Windows 计划任务 KB-Monitor-Update 已删除，
        # 抓取改为完全手动（文献库页的「抓取新论文」按钮）。
        # 这里不再显示「下次 09:00」，因为那是一个永远不会到来的时间。
        self._kv(c, "抓取方式", "手动 · 不注册系统计划任务")
        try:
            sched = KB.schedule_status()
        except Exception:
            sched = {}
        # 失败清单仍然有用：上一次手动抓取失败的那几篇在这里能重试
        n_fail = int(sched.get("failed") or 0)
        n_over = int(sched.get("over_limit") or 0)
        if n_fail or n_over:
            msg = "上次抓取（%s）有 %d 篇下载失败" % (sched.get("last_time") or "未知", n_fail)
            if n_over:
                msg += "，另有 %d 篇超过每轮上限没拉全文（下次运行会补）" % n_over
            lbl = tk.Label(c, text=msg, bg=T.CARD, fg=T.ERR, font=T.F(9),
                           anchor="w", justify="left", wraplength=760)
            lbl.pack(fill="x", pady=(4, 0))
            if n_fail:
                row = U.WrapRow(c, bg=T.CARD)
                row.pack(fill="x", pady=(6, 0))
                self.retry_btn = T.Btn(row, "重新下载失败的 %d 篇" % min(n_fail, 5),
                                       self._retry_failed, "primary")
                row.add(self.retry_btn)
                row.add(T.Btn(row, "打开失败清单",
                              lambda: self._open(KB.FAILURES_FILE)))
        else:
            tk.Label(c, text="上一次抓取没有失败记录。", bg=T.CARD, fg=T.TXT3,
                     font=T.F(9), anchor="w").pack(fill="x", pady=(4, 0))
        qs = cfg.get("queries", [])
        box = tk.Frame(c, bg=T.CARD)
        box.pack(fill="x", pady=(8, 0))
        tk.Label(box, text="检索词组（%d）" % len(qs), bg=T.CARD, fg=T.TXT3,
                 font=T.F(9, True), anchor="w").pack(fill="x")
        self.q_entry = tk.Entry(box, bg=T.CARD_HI, fg=T.TXT, insertbackground=T.ACCENT,
                                relief="flat", highlightbackground=T.LINE,
                                highlightthickness=1, font=T.F(9))
        self.q_entry.pack(fill="x", pady=(4, 4), ipady=5)
        row = U.WrapRow(box, bg=T.CARD)
        row.pack(fill="x")
        row.add(T.Btn(row, "添加检索词", self._add_query, "primary"))
        row.add(T.Btn(row, "编辑 config.json",
                      lambda: self._open(kb.CONFIG_FILE)))
        self.q_lbl = tk.Label(c, text="", bg=T.CARD, fg=T.TXT3, font=T.M(8), anchor="w",
                              justify="left", wraplength=760)
        self.q_lbl.pack(fill="x", pady=(6, 0))
        self._render_queries(qs)

        # 交接
        c = self._card("提示词与产出", "最近生成的文件")
        try:
            outs = kb.recent_research_outputs(8)
        except Exception:
            outs = []
        if not outs:
            tk.Label(c, text="还没有生成的提示词或报告。", bg=T.CARD, fg=T.TXT4,
                     font=T.F(9), anchor="w").pack(fill="x")
        for o in outs[:6]:
            # recent_research_outputs 返回的键是 "path"（不是 "file"）
            if isinstance(o, dict):
                p = o.get("path") or o.get("file") or ""
                kind = o.get("kind") or ""
                when = o.get("time") or ""
            else:
                p, kind, when = str(o), "", ""
            if not p:
                continue
            name = str(p).split("\\")[-1]
            head = ("%s  %s" % (kind, name)).strip() if kind else name
            txt = ("%s  ·  %s" % (head, when)).rstrip(" ·")
            f = tk.Frame(c, bg=T.CARD, cursor="hand2")
            f.pack(fill="x")
            lb = tk.Label(f, text="· " + txt, bg=T.CARD, fg=T.TXT2,
                          font=T.F(9), anchor="w")
            lb.pack(fill="x", pady=1)
            for w in (f, lb):
                w.bind("<Button-1>", lambda e, pp=p: self._open(pp))
        row = tk.Frame(c, bg=T.CARD)
        row.pack(fill="x", pady=(8, 0))
        T.Btn(row, "打开 exports 目录", lambda: self._open(kb.EXPORT_DIR),
              "primary").pack(anchor="w")

        # 关于
        c = self._card("关于", "版本与数据来源")
        tk.Label(c, text="塞莎特——题谱 · 科研选题知识库", bg=T.CARD, fg=T.TXT,
                 font=T.T_SECTION(), anchor="w").pack(fill="x")
        tk.Label(c,
                 text="面向高校师生的本地科研选题工作台。不联网也能用全部检索、"
                      "体检与匹配功能；数据只存本机。导师与 venue 匹配依据公开索引，"
                      "最终以院校官网与期刊官网为准。",
                 bg=T.CARD, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                 justify="left", wraplength=T.wrap(760)).pack(fill="x", pady=(4, 0))

        self._build_web()

    # ── 网页体验端 ────────────────────────────────────────
    def _build_web(self):
        """在设置里直接起停网页版，别让用户开命令行。

        体验端是只读的：选题 / 文献空白 / 导师 / 图谱 / 方法论。
        下载、密钥、个人画像一律不开——这些路由在 web_server.py 里
        根本没注册，前端改 URL 也只会拿到 403。
        """
        c = self._card("网页体验端（只读）", "在浏览器或手机上打开")
        tk.Label(c,
                 text="给同学试用时用。手机在同一 Wi-Fi 下扫码或输地址即可打开。\n"
                      "只开放：选题候选、文献空白、导师院校、方向图谱、科研方法论。\n"
                      "不开放：下载 PDF、大模型密钥、个人画像、本地文献全文检索、实时抓取。",
                 bg=T.CARD, fg=T.TXT3, font=T.F(9), anchor="w", justify="left",
                 wraplength=T.wrap(420)).pack(fill="x")

        self._web_status = tk.Label(c, text="", bg=T.CARD, fg=T.TXT2,
                                    font=T.F(10), anchor="w")
        self._web_status.pack(fill="x", pady=(8, 4))
        self._web_row = tk.Frame(c, bg=T.CARD)
        self._web_row.pack(fill="x")
        self._web_btn = T.Btn(self._web_row, "启动网页版", self._web_toggle, "primary")
        self._web_btn.pack(side="left")
        self._web_lan = T.Btn(self._web_row, "复制手机地址", self._web_copy, "ghost",
                              state="disabled")
        self._web_lan.pack(side="left", padx=(8, 0))
        self._web_qr_btn = T.Btn(self._web_row, "显示二维码", self._toggle_qr, "ghost",
                                 state="disabled")
        self._web_qr_btn.pack(side="left", padx=(8, 0))

        # 二维码：只在点了「显示二维码」之后才占位，平时不占屏幕
        self._qr_box = tk.Frame(c, bg=T.CARD)
        self._qr_canvas = tk.Canvas(self._qr_box, bg=T.CARD, highlightthickness=0,
                                    width=232, height=232)
        self._qr_hint = tk.Label(self._qr_box, text="", bg=T.CARD, fg=T.TXT3,
                                 font=T.F(8), anchor="w", justify="left",
                                 wraplength=T.wrap(300))
        self._qr_open = False
        self._qr_url = ""

        self._refresh_web()

    def _refresh_web(self):
        st = WS.status()
        if st.get("running"):
            self._web_status.config(text="运行中 · %s（%s）" % (st.get("url", ""),
                                                          st.get("lan_url", "")),
                                    fg=T.OK)
            self._web_btn.config_text("停止网页版")
            self._web_btn._cmd = self._web_toggle
            self._web_lan.config(state="normal")
            self._web_qr_btn.config(state="normal")
        else:
            self._web_status.config(text="未启动", fg=T.TXT3)
            self._web_btn.config_text("启动网页版")
            self._web_btn._cmd = self._web_toggle
            self._web_lan.config(state="disabled")
            self._web_qr_btn.config(state="disabled")
            self._qr_hide()

    # ── 二维码 ────────────────────────────────────────────
    def _toggle_qr(self):
        if self._qr_open:
            self._qr_hide()
        else:
            self._qr_show()

    def _qr_hide(self):
        self._qr_open = False
        try:
            self._qr_box.pack_forget()
            self._qr_canvas.delete("all")
        except Exception:
            pass
        try:
            self._web_qr_btn.config_text("显示二维码")
        except Exception:
            pass
        # 收起后内容变矮，滚动区要跟着缩小，否则底部会留一段空白
        self._refresh_scroll()

    def _refresh_scroll(self):
        """二维码展开/收起后重算滚动区。

        为什么必须显式调三步：
          1. ScrollArea 的 scrollregion 按 inner 的 `winfo_reqheight()` 算，
             而 pack/pack_forget 之后这个值要等下一次空闲测量才更新；
          2. Card 的高度又跟着 body 的请求高度变，需要再一轮才能传上去；
          3. 所以只调一次 refresh() 不够 —— 实测展开后 inner.reqheight 仍是
             1752（二维码 216px 完全没算进去），二维码落在滚动区外，
             **滚轮到底也看不到**（2026-11-13 踩过）。
        这里用「立即 + 60ms + 160ms」三次触发，让两级高度传递各自跑完。
        """
        def _bump():
            try:
                # 先让承载卡片的 Card 按新的 body 请求高度重算自身高度，
                # 再刷新滚动区（顺序反了的话滚动区按旧高度算，白算一次）。
                card = self._qr_box.master          # Card.body
                for _ in range(3):
                    if not getattr(card, "master", None):
                        break
                    card = card.master
                    if getattr(card, "is_card", False):
                        if hasattr(card, "sync_now"):
                            card.sync_now()
                        break
                sa = self.body.master.master          # inner → canvas → ScrollArea
                if hasattr(sa, "refresh"):
                    sa.refresh()
            except Exception:
                pass
        _bump()
        for ms in (60, 160):
            try:
                self.after(ms, _bump)
            except Exception:
                break

    def _qr_show(self):
        st = WS.status() or {}
        if not st.get("running"):
            return
        # 已安装 PWA 的手机必须走局域网地址，用 127.0.0.1 扫码等于扫自己
        url = st.get("lan_url") or st.get("url") or ""
        if not url:
            return
        self._qr_url = url
        self._qr_box.pack(fill="x", pady=(10, 0))
        self._qr_canvas.pack(side="left")
        self._qr_hint.pack(side="left", padx=(12, 0), anchor="n", pady=(8, 0))
        self._qr_canvas.delete("all")
        try:
            import qrtool
            mat, size = qrtool.build(url)
        except Exception as exc:
            self._qr_hint.config(text="生成二维码失败：%s\n可以把地址手动输入到手机浏览器。"
                                      % exc, fg=T.ERR)
            self._qr_open = True
            self._web_qr_btn.config_text("收起二维码")
            self._refresh_scroll()
            return
        # 画在 Canvas 上：Tk 没有图片缩放的稳定实现，直接按格子画最清楚
        cell = max(3, int(200 / size))
        pad = 8
        dim = size * cell + pad * 2
        self._qr_canvas.config(width=dim, height=dim)
        self._qr_canvas.create_rectangle(0, 0, dim, dim, fill="#FFFFFF", outline="")
        for y in range(size):
            x = 0
            while x < size:
                if mat[y][x]:
                    x0 = x
                    while x < size and mat[y][x]:
                        x += 1
                    self._qr_canvas.create_rectangle(
                        pad + x0 * cell, pad + y * cell,
                        pad + x * cell, pad + (y + 1) * cell,
                        fill="#061220", outline="")
                else:
                    x += 1
        self._qr_hint.config(
            text="手机连同一个 Wi-Fi，用相机扫这个码。\n\n%s\n\n"
                 "首次打开后可以「添加到主屏幕」，"
                 "以后像 App 一样点开。\n\n"
                 "注意：局域网是 http，浏览器不会装 Service Worker，"
                 "所以「离线可用」这一项在手机上不生效；"
                 "桌面或本机用 localhost/HTTPS 打开才完整。" % url,
            fg=T.TXT3)
        self._qr_open = True
        self._web_qr_btn.config_text("收起二维码")
        self._refresh_scroll()

    def _web_toggle(self):
        st = WS.status()
        if st.get("running"):
            WS.stop()
            self.app.toast("网页版已停止")
        else:
            ok, msg = WS.start()
            self.app.toast(msg, T.OK if ok else T.ERR)
        # Btn 是 Label 子类，没有 config(state) 的语义一致性，这里重画状态行
        self.app.root.after(200, self._refresh_web)
        self._refresh_web()

    def _web_copy(self):
        url = (WS.status() or {}).get("lan_url") or (WS.status() or {}).get("url") or ""
        if not url:
            return
        try:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(url)
            self.app.toast("已复制：" + url, T.OK)
        except Exception:
            self.app.toast("复制失败，手动记一下：" + url, T.WARN)

    # ── 大模型接入 ────────────────────────────────────────
    def reload(self):
        self._build()

    def _build_llm(self):
        cfg = L.load_config()
        c = self._card("大模型接入（可选）", "配了能改写检索式、总结论文、连续对话", open=True)
        T.para(c,
               "不接也能用全部功能。接了之后，「最新研究」可以自动把中文方向改写成"
               "更准的检索式，也能让模型总结论文走向、审阅候选选题。配好之后，"
               "创新点库里会出现「和模型继续聊」：就某一条选题来回追问，"
               "每一轮都会带上你画像里的方向与约束。「试对话」会连问两轮，"
               "确认多轮上下文和你自己的情况真的发出去了。"
               "密钥只写在本机 llm_config.json，不会上传。",
               color=T.TXT2, font=T.T_BODY_SM(), wrap_px=700, pady=(0, 10))

        # 服务商下拉
        row = tk.Frame(c, bg=T.CARD)
        row.pack(fill="x", pady=(0, 6))
        tk.Label(row, text="服务商", bg=T.CARD, fg=T.TXT3, font=T.F(9), width=8,
                 anchor="w").pack(side="left")
        names = ["（不使用）"] + [v["label"] for v in L.PROVIDERS.values()]
        self.llm_provider = tk.StringVar(value=self._provider_label(cfg))
        om = ttk.Combobox(row, textvariable=self.llm_provider, values=names,
                          state="readonly", font=T.F(9), width=28)
        om.pack(side="left", ipady=3)
        om.bind("<<ComboboxSelected>>", lambda e: self._llm_pick_provider())
        if cfg.get("provider") in L.PROVIDERS:
            note = L.PROVIDERS[cfg["provider"]].get("note", "")
            self.llm_note = tk.Label(c, text="  " + note, bg=T.CARD, fg=T.TXT4,
                                     font=T.F(9), anchor="w")
            self.llm_note.pack(fill="x", pady=(0, 6))

        # base_url / model / key
        self.llm_vars = {}
        for key_, label, ph in (("base_url", "接口地址", "https://api.deepseek.com/v1"),
                                ("model", "模型名", "deepseek-chat"),
                                ("api_key", "密钥", "sk-...（本机 Ollama 可留空）")):
            r = tk.Frame(c, bg=T.CARD)
            r.pack(fill="x", pady=(0, 4))
            tk.Label(r, text=label, bg=T.CARD, fg=T.TXT3, font=T.F(9), width=8,
                     anchor="w").pack(side="left")
            v = tk.StringVar(value=cfg.get(key_, ""))
            e = tk.Entry(r, textvariable=v, bg=T.CARD_HI, fg=T.TXT,
                         insertbackground=T.ACCENT, relief="flat",
                         highlightbackground=T.LINE, highlightthickness=1, font=T.F(9))
            e.pack(side="left", fill="x", expand=True, ipady=5)
            if key_ == "api_key":
                e.config(show="·")
                self.llm_key_entry = e
                tk.Checkbutton(r, text="显示", bg=T.CARD, fg=T.TXT3,
                               selectcolor=T.CARD_HI, activebackground=T.CARD,
                               activeforeground=T.TXT, font=T.F(9), bd=0,
                               command=self._llm_toggle_key).pack(side="left", padx=(6, 0))
            self.llm_vars[key_] = v

        # 开关 + 动作
        row = tk.Frame(c, bg=T.CARD)
        row.pack(fill="x", pady=(8, 0))
        self.llm_enabled = tk.BooleanVar(value=bool(cfg.get("enabled")))
        tk.Checkbutton(row, text="启用大模型增强", variable=self.llm_enabled,
                       bg=T.CARD, fg=T.TXT2, selectcolor=T.CARD_HI,
                       activebackground=T.CARD, activeforeground=T.TXT,
                       font=T.F(9), bd=0).pack(anchor="w", pady=(0, 6))
        # 四个按钮在大字号下放不进一行，交给折行容器
        brow = U.WrapRow(row, bg=T.CARD)
        brow.pack(fill="x")
        brow.add(T.Btn(brow, "保存", self._llm_save, "primary"))
        brow.add(T.Btn(brow, "测试连接", self._llm_test))
        brow.add(T.Btn(brow, "试对话", self._llm_chat_test))
        brow.add(T.Btn(brow, "清除密钥", self._llm_clear))

        self.llm_status = tk.Label(c, text=self._llm_status_text(cfg), bg=T.CARD,
                                   fg=T.TXT3, font=T.F(9), anchor="w",
                                   justify="left", wraplength=760)
        self.llm_status.pack(fill="x", pady=(4, 0))
        _llm_note = tk.Label(
            c,
            text="只用标准库实现，任何 OpenAI 兼容接口都能接；"
                 "国产模型里智谱 glm-4-flash 有免费额度，Ollama 完全离线。",
            bg=T.CARD, fg=T.TXT4, font=T.F(9), anchor="w", justify="left")
        _llm_note.pack(fill="x", pady=(2, 0))
        # 原来这条说明没设 wraplength：窗口窄到 1240 时它要 1006px 而只有
        # 944px，尾巴「Ollama 完全离线。」被直接切掉。交给 fill_wrap 跟着容器走。
        T.fill_wrap(_llm_note, pad=8)
        if cfg.get("provider") in L.PROVIDERS and L.PROVIDERS[cfg["provider"]].get("key_url"):
            u = L.PROVIDERS[cfg["provider"]]["key_url"]
            lb = tk.Label(c, text="去哪里拿密钥 → " + u, bg=T.CARD, fg=T.ACCENT,
                          font=T.F(9), anchor="w", cursor="hand2")
            lb.pack(fill="x", pady=(2, 0))
            lb.bind("<Button-1>", lambda e, uu=u: self.app.open_url(uu))

    def _provider_label(self, cfg):
        p = cfg.get("provider") or ""
        if p in L.PROVIDERS:
            return L.PROVIDERS[p]["label"]
        return "（不使用）"

    def _llm_pick_provider(self):
        """选服务商后自动填好 base_url 和模型名，省得用户翻文档。"""
        label = self.llm_provider.get()
        for pid, meta in L.PROVIDERS.items():
            if meta["label"] == label:
                self.llm_vars["base_url"].set(meta.get("base_url", ""))
                self.llm_vars["model"].set(meta.get("model", ""))
                cfg = L.load_config()
                cfg["provider"] = pid
                L.save_config(cfg)
                self.llm_status.config(fg=T.TXT3,
                                       text="已选择 %s。%s\n填好密钥后点「保存」，再点「测试连接」。"
                                            % (meta["label"], meta.get("note", "")))
                return
        cfg = L.load_config()
        cfg["provider"] = ""
        L.save_config(cfg)
        self.llm_vars["base_url"].set("")
        self.llm_vars["model"].set("")
        self.llm_status.config(fg=T.TXT3, text="未启用大模型，全部功能走本地逻辑。")

    def _llm_toggle_key(self):
        self.llm_key_entry.config(show="" if self.llm_key_entry.cget("show") else "·")

    def _llm_save(self):
        cfg = L.load_config()
        for k, v in self.llm_vars.items():
            cfg[k] = v.get().strip()
        cfg["enabled"] = bool(self.llm_enabled.get())
        L.save_config(cfg)
        ok = L.is_ready(cfg)
        self.llm_status.config(
            fg=T.OK if ok else T.WARN,
            text=("已保存，配置完整。" if ok else
                  "已保存，但还缺东西：需要接口地址、模型名，密钥（本机 Ollama 除外）。"))
        self.app.toast("大模型配置已保存", T.OK)

    def _llm_test(self):
        cfg = L.load_config()
        for k, v in self.llm_vars.items():
            cfg[k] = v.get().strip()
        cfg["enabled"] = True
        if not L.is_ready(cfg):
            self.llm_status.config(fg=T.WARN, text="配置不完整，先填接口地址和模型名。")
            return
        self.llm_status.config(fg=T.TXT3, text="正在连接…")
        self.app.toast("正在测试大模型连接…")

        def work():
            ok, msg = L.test_connection(cfg)
            self.app.post(lambda: self._llm_test_done(ok, msg))
        threading.Thread(target=work, daemon=True).start()

    def _llm_test_done(self, ok, msg):
        self.llm_status.config(fg=T.OK if ok else T.ERR, text=msg)
        self.app.toast("连接成功" if ok else "连接失败", T.OK if ok else T.ERR)

    def _llm_chat_test(self):
        """「试对话」：验证连续对话 + 画像注入这一整条链路能跑通。

        和「测试连接」的区别：连接测试只问一句「回复两个字：可用」，
        证明不了多轮上下文和画像段有没有真的发出去。这里问两轮，
        第二轮依赖第一轮说过的内容，模型答对才说明上下文确实带上了。
        """
        cfg = L.load_config()
        for k, v in self.llm_vars.items():
            cfg[k] = v.get().strip()
        cfg["enabled"] = True
        if not L.is_ready(cfg):
            self.llm_status.config(fg=T.WARN, text="配置不完整，先填接口地址和模型名。")
            return
        self.llm_status.config(fg=T.TXT3, text="正在试对话（两轮，约 10 秒）…")

        def work():
            import dialog as D
            t0 = time.time()
            ok1, a1 = D.reply([], "请只回答一个词：橘子的颜色。", cfg=cfg)
            if not ok1:
                return False, "第一轮失败：" + str(a1), ""
            turns = [{"role": "user", "content": "请只回答一个词：橘子的颜色。"},
                     {"role": "assistant", "content": a1}]
            ok2, a2 = D.reply(turns, "我刚才问的是什么水果？只回答水果名。", cfg=cfg)
            ms = int((time.time() - t0) * 1000)
            if not ok2:
                return False, "第二轮失败：%s\n第一轮答的是：%s" % (a2, a1), ""
            return True, "两轮都通（%d ms）\n第一轮：%s\n第二轮：%s" % (
                ms, str(a1).strip()[:60], str(a2).strip()[:60]), str(a1) + str(a2)

        def done(ok, msg, _raw):
            self.llm_status.config(fg=T.OK if ok else T.ERR, text=msg)
            self.app.toast("对话可用" if ok else "对话失败", T.OK if ok else T.ERR)

        def run():
            r = work()
            self.app.post(lambda: done(*r))
        threading.Thread(target=run, daemon=True).start()

    def _llm_clear(self):
        cfg = L.load_config()
        cfg["api_key"] = ""
        cfg["enabled"] = False
        L.save_config(cfg)
        self.llm_vars["api_key"].set("")
        self.llm_enabled.set(False)
        self.llm_status.config(fg=T.TXT3, text="密钥已清除，已切回本地逻辑。")
        self.app.toast("密钥已清除", T.OK)

    def _llm_status_text(self, cfg):
        st = L.status()
        if st["ready"]:
            return "当前：%s · %s · 密钥 %s%s" % (
                st["provider"] or "自定义", st["model"], st["key"] or "无",
                "  · 上次成功 " + st["last_ok"] if st["last_ok"] else "")
        if st["last_error"]:
            return "上次失败：" + st["last_error"]
        return "未配置。不配也能用，只是检索靠本地中文→英文词表。"

    def _card(self, title, sub="", open=False):
        """设置页的一个分区：默认收起，点标题展开。

        第 10 版：原来是五张卡片一路竖排到底，找「大模型接入」要滚两屏。
        收起后一屏能扫到全部分区名，找东西从「翻一遍」变成「扫一眼」。
        最常用的（存储与路径、大模型）默认展开，其余收起。
        """
        sec = U.Section(self.body, title, sub, bg=T.CARD, pad=14, open=open)
        sec.pack(fill="x", pady=(0, 10))
        # 分区开合会改变内容高度：滚动区必须重新量一遍，否则下半截被裁掉
        sec.on_resize = self._resync_scroll
        self._sections[title] = sec
        # 保持旧调用方不变：返回能往里放内容的容器
        return sec.body

    def _resync_scroll(self):
        sc = getattr(self, "_scroll", None)
        if sc is None:
            return
        try:
            sc.refresh()
        except Exception:
            pass
        try:
            self.after(60, sc.refresh)
        except Exception:
            pass

    def _open_section(self, title):
        """展开指定分区（供外部跳转用，比如「去配大模型」）。"""
        sec = self._sections.get(title)
        if sec is not None and not sec.expanded:
            sec.toggle(True)
        return sec

    def _kv(self, parent, k, v):
        # 键/值两列对齐（参考图的表格化写法）：键固定 12 字宽、值右对齐伸展，
        # 一眼能扫出「哪个值是哪一项的」，不用顺着冒号找。
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=k, bg=T.CARD, fg=T.TXT3, font=T.T_BODY_SM(), width=12,
                 anchor="w").pack(side="left")
        value = tk.Label(row, text=str(v), bg=T.CARD, fg=T.TXT2,
                         font=T.T_BODY_SM(), anchor="w", justify="left")
        value.config(width=1)
        value.pack(side="left", fill="x", expand=True)
        value.bind("<Configure>", lambda e: value.config(wraplength=max(1, e.width - 8)))

    def _render_queries(self, qs):
        txt = "\n".join(qs) or "（暂无）"
        self.q_lbl.config(text=txt)
        T.fill_wrap(self.q_lbl)

    def _add_query(self):
        q = self.q_entry.get().strip()
        if not q:
            self.app.toast("请输入检索词", T.WARN)
            return
        try:
            cfg = kb.load_config()
            qs = cfg.setdefault("queries", [])
            if q in qs:
                self.app.toast("已存在该检索词", T.WARN)
                return
            qs.append(q if ("all:" in q or " AND " in q.upper()) else "all:" + q)
            kb.CONFIG_FILE.write_text(kb.json.dumps(cfg, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
            self.q_entry.delete(0, "end")
            self._render_queries(qs)
            self.app.toast("已添加，下次抓取生效", T.OK)
        except Exception as exc:
            self.app.toast("添加失败：" + str(exc), T.ERR)

    def _open(self, p):
        try:
            kb.os.startfile(str(p))
        except Exception as exc:
            self.app.toast("打开失败：" + str(exc), T.ERR)

    def _retry_failed(self):
        """重试上次失败的下载。只重试真失败的，不重试「没有公开全文」的。"""
        self.retry_btn.config(state="disabled", text="重试中…")

        def work():
            try:
                return KB.retry_failed(limit=5)
            except Exception as exc:
                return {"tried": 0, "ok": 0, "still": [], "error": str(exc)}

        def done(r):
            if r.get("error"):
                self.app.toast("重试出错：" + r["error"], T.ERR)
            elif r.get("tried") == 0:
                self.app.toast("没有可重试的条目", T.TXT3)
            else:
                msg = "重试 %d 篇，成功 %d 篇" % (r["tried"], r["ok"])
                if r.get("still"):
                    msg += "，仍失败 %d 篇" % len(r["still"])
                self.app.toast(msg, T.OK if r["ok"] else T.WARN)
            try:
                self.app.mark_dirty("settings")
            except Exception:
                pass

        self.app.post(lambda: done(work()))


def _cat_covered(venues, alias):
    """返回「方向→期刊会议」推不准的大类，空集表示每一类都能按细分方向推。

    2026-11-20 实测：`research_taxonomy_comprehensive.json` 的 25 个大类里，
    24 类都登记了块级 `venues`（全部落在 701 条里，一条没丢），只有「应用领域」
    是空的 —— 它本来就不是学科块，列的是医疗 / 教育 / 金融这类落地场景，
    真推荐期刊也该按所属大类兜底。

    块级 venue 是**大类级**的：`kb.infer_category_field("三维重建")` 返回
    cat=计算机视觉、field=三维重建与神经渲染，推荐时按 大类+细分方向 打分，
    所以只要这个大类登记了 venue，任何细分方向都能落上去（实测三维重建出
    15 条、IEEE TVCG 排第一）。反过来说，「应用领域」没有块级 venue，
    问到「医疗影像」就只能空手或退回全局热门 —— 用户会以为数据缺了，
    所以这一处在页面上明说。
    """
    try:
        lib_path = HERE / "research_taxonomy_comprehensive.json"
        doc = json.loads(lib_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    cats = doc.get("categories")
    if not isinstance(cats, dict):
        return set()
    # 小类名 → 大类名（用小类的名字去搜时能对上哪个大类）
    sub_to_cat = {}
    for cat, body in cats.items():
        for s in ((body or {}).get("subs") or []):
            name = s.get("name") if isinstance(s, dict) else s
            if name:
                sub_to_cat[name] = cat
    # 「块里登记了 venue」且「有细分方向」的大类，才算铺到了细分方向
    seeded = set()
    for cat, body in cats.items():
        body = body or {}
        if (body.get("venues") or []) and (body.get("subs") or []):
            seeded.add(cat)
    missing = set(cats) - seeded
    # kb.infer_category_field 认出的是小类名，落到大类的这一层要能接住
    for sub, cat in sub_to_cat.items():
        if cat not in seeded:
            missing.add(cat)
    return missing