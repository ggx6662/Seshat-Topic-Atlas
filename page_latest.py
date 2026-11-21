#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最新研究页：按方向从 arXiv / OpenAlex / Europe PMC 抓最近发表的论文。

为什么需要这一页：
    选题工坊给的是「方向 × 角度」的候选，文献空白给的是「库里还没人做的
    组合」——两者都只看**你手上已有的 343 篇**。外面的世界在做什么，界面里
    一直缺一块。这一页补上：输入方向 → 三源并发抓取 → 去重排序 → 看到最近
    一个月这个方向在发生什么。

    抓到的论文可以直接：
        · 存进创新点库（作为「已有工作」的证据）
        · 下载 PDF 进本地知识库
        · 复制标题去 Google Scholar / arXiv 细看

诚实表达：
    · 每个源单独显示拿了几条，失败的源如实标出来，不吞错误
    · 抓取到的最新日期直接显示——如果最新是两个月前，就是两个月前，
      不写成"最近更新"糊弄
    · 明确标注"这是自动抓取的清单，不是综述"
"""
import re
import threading
import time
import tkinter as tk
import webbrowser

import app_theme as T
import kb_download as KB
import kb_widget as kb
import llm_bridge as L
import paper_sources as PS
import ui_kit as UK
import ui_parts as U

PAGE_HINT = "按方向抓取最近发表 · arXiv / OpenAlex / Europe PMC 三源"

QUICK = ("红外小目标检测", "图像融合", "Mamba", "扩散模型", "多模态大模型")


def _short(t, n):
    t = t or ""
    return t if len(t) <= n else t[:n - 1] + "…"


_LLM_Q_OK = re.compile(r"^\s*[\(\[]?\s*(abs:|all:|ti:|cat:|au:)", re.I)


def _valid_arxiv_query(q):
    """验证大模型给的检索式，别让一句解释文字直接当查询发出去。

    模型很爱输出「好的，检索式如下：abs:...」这种带前缀的话，
    直接塞进 arXiv API 会返回空或者报错。宁可不用也不要出错。
    """
    q = (q or "").strip()
    if not q or len(q) > 500:
        return False
    if not _LLM_Q_OK.match(q):
        return False
    if q.count("(") != q.count(")"):
        return False
    return True


class LatestPage(tk.Frame):
    ROW_H = None

    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.result = None
        self._papers = []
        self._sel = -1
        self._frames = {}
        self._empty = None
        self._busy = False
        self._dl_btns = {}
        self._dl_state = {}
        self._batch = None
        self._active_quick = ""
        self._query_id = 0
        self._direction = ""
        self._build()

    # ------------------------------------------------------------ 布局
    def _build(self):
        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=T.PAD, pady=(4, 0))
        acts = tk.Frame(head, bg=T.BG)
        acts.pack(side="right")
        self.ai_btn = T.Btn(acts, "AI 总结", self.explain)
        self.ai_btn.pack(side="left", padx=(6, 0))
        self.dl_all_btn = T.Btn(acts, "下载前 5 篇", self.download_top)
        self.dl_all_btn.pack(side="left", padx=(6, 0))
        self.dl_all_btn.config(state="disabled", fg=T.TXT4, cursor="arrow")
        T.Btn(acts, "选题工坊", self._go_topic).pack(side="left", padx=(6, 0))
        self.ai_btn.config(state="disabled")
        tk.Label(head, text="最新研究", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE(), anchor="w").pack(side="left")

        cap = tk.Label(self,
                       text="按方向抓最近发表：三源并发、跨源去重；失败的源会如实标出。",
                       bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                       justify="left")
        cap.pack(fill="x", padx=T.PAD, pady=(2, 0))
        T.fill_wrap(cap, pad=4)

        # ---- 筛选卡：输入行 + 常用方向
        fcard = T.Card(self, fill_y=False, pad=10)
        fcard.pack(fill="x", padx=T.PAD, pady=(6, 6))
        fbody = fcard.body
        self._fbody = fbody
        srch = tk.Frame(fbody, bg=T.CARD)
        srch.pack(fill="x")
        self.clear_btn = T.Btn(srch, "清空", self._clear_entry)
        self.clear_btn.pack(side="right", padx=(6, 0))
        self.btn = T.Btn(srch, "抓取", self.search, "primary")
        self.btn.pack(side="right", padx=(8, 0))
        self.entry = tk.Entry(srch, bg=T.CARD_HI, fg=T.TXT,
                              insertbackground=T.ACCENT, relief="flat",
                              font=T.T_BODY())
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        T.fix_highlight(self.entry, T.card_edge(T.LINE, T.CARD))
        self._ph = "输入研究方向，如「红外小目标检测」"
        self.entry.insert(0, self._ph)
        self.entry.config(fg=T.TXT4)
        self.entry.bind("<FocusIn>", self._ph_in)
        self.entry.bind("<FocusOut>", self._ph_out)
        self.entry.bind("<Return>", lambda e: self.search())
        try:
            import app_suggest
            app_suggest.attach(self.entry)
        except Exception as exc:
            print("联想词挂载失败:", exc)

        qrow = tk.Frame(fbody, bg=T.CARD)
        qrow.pack(fill="x", pady=(8, 0))
        self._adv_btn = T.Btn(qrow, "更多设置", self._toggle_adv, "ghost")
        self._adv_btn.pack(side="right")
        self._quick_wrap = tk.Frame(qrow, bg=T.CARD)
        self._quick_wrap.pack(side="left", fill="x", expand=True)
        self._quick_row = None
        self._render_quick()

        # 折叠区：来源 / 范围。默认值是对的，所以默认不展开。
        self.adv = tk.Frame(fbody, bg=T.CARD)
        self._more_open = False
        tk.Label(self.adv, text="来源", bg=T.CARD, fg=T.TXT3,
                 font=T.T_CAPTION()).pack(side="left", padx=(0, 8))
        self.src_vars = {}
        for s in PS.ALL_SOURCES:
            v = tk.BooleanVar(value=True)
            self.src_vars[s] = v
            cb = tk.Checkbutton(self.adv, text=PS.SOURCE_LABEL[s], variable=v,
                                bg=T.CARD, fg=T.TXT2, selectcolor=T.CARD_HI,
                                activebackground=T.CARD,
                                activeforeground=T.TXT,
                                font=T.T_CAPTION(), bd=0,
                                highlightthickness=0)
            cb.pack(side="left", padx=(0, 10))
        tk.Label(self.adv, text="范围", bg=T.CARD, fg=T.TXT3,
                 font=T.T_CAPTION()).pack(side="left", padx=(8, 6))
        self.days = tk.StringVar(value="最近 6 个月")
        om = tk.OptionMenu(self.adv, self.days, "最近 1 个月", "最近 3 个月",
                           "最近 6 个月", "最近 1 年")
        om.config(bg=T.CARD_HI, fg=T.TXT, activebackground=T.CARD_HI,
                  highlightthickness=1, highlightbackground=T.LINE,
                  relief="flat", font=T.T_CAPTION(), width=10)
        om.pack(side="left")

        # ---- 结论行（网页版的 search-meta：数字跟着这次查询走）
        meta = tk.Frame(self, bg=T.BG)
        meta.pack(fill="x", padx=T.PAD, pady=(0, 4))
        self.summary = tk.Label(meta, text="输入研究方向，点「抓取」或选一个常用方向。",
                                bg=T.BG, fg=T.TXT3, font=T.T_CAPTION(),
                                anchor="w", justify="left")
        self.summary.pack(side="left", fill="x", expand=True)
        T.fill_wrap(self.summary, pad=8)

        self.ai_host = tk.Frame(self, bg=T.BG)
        self.ai_host.pack(fill="x")
        self.notice_host = tk.Frame(self, bg=T.BG)
        self.notice_host.pack(fill="x", padx=T.PAD)

        # ---- 左列表 + 右详情
        body = tk.Frame(self, bg=T.BG)
        self._body = body
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        body.grid_columnconfigure(0, weight=3, uniform="latbody")
        body.grid_columnconfigure(1, weight=2, uniform="latbody",
                                  minsize=T.sp(300))
        body.grid_rowconfigure(0, weight=1)

        lcard = T.Card(body, pad=0)
        lcard.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        hrow = tk.Frame(lcard.body, bg=T.CARD)
        hrow.pack(fill="x", pady=(2, 0))
        tk.Label(hrow, text="论文", bg=T.CARD, fg=T.TXT4,
                 font=T.T_CAPTION(), anchor="w").pack(side="left",
                                                      padx=(12, 0))
        tk.Label(hrow, text="来源 · 日期", bg=T.CARD, fg=T.TXT4,
                 font=T.T_CAPTION(), anchor="e").pack(side="right",
                                                      padx=(0, 14))
        tk.Frame(lcard.body, bg=T.LINE_SOFT, height=1).pack(
            fill="x", pady=(4, 0))
        self.box = T.ScrollArea(lcard.body, bg=T.CARD)
        self.box.pack(fill="both", expand=True)

        dcard = T.Card(body, pad=14)
        dcard.grid(row=0, column=1, sticky="nsew")
        # 动作条固定在详情卡底部，摘要再长也不会把「下载 / 存进库」挤出视口
        self._detail_foot = tk.Frame(dcard.body, bg=T.CARD)
        self._detail_foot.pack(side="bottom", fill="x", pady=(8, 0))
        self.detail_box = T.ScrollArea(dcard.body, bg=T.CARD)
        self.detail_box.pack(fill="both", expand=True)

        self._render_list()
        self._render_detail(None)

    def _render_quick(self):
        if self._quick_row is not None:
            try:
                self._quick_row.destroy()
            except Exception:
                pass
        self._quick_row = U.WrapRow(self._quick_wrap, gap=6, rowgap=6,
                                    bg=T.CARD)
        self._quick_row.pack(side="left", fill="x", expand=True)
        for t in QUICK:
            self._quick_row.add(UK.Chip(
                self._quick_row, t, active=(t == self._active_quick),
                command=lambda x=t: self._quick(x), bg=T.CARD,
                height=T.sp(26), font=T.T_CAPTION()))

    def _toggle_adv(self):
        """来源 / 范围 的显隐；默认收起，默认值本来就是对的。"""
        if self._more_open:
            self.adv.pack_forget()
            self._adv_btn.config(text="更多设置")
        else:
            self.adv.pack(fill="x", pady=(8, 0), after=self._quick_wrap.master)
            self._adv_btn.config(text="收起设置")
        self._more_open = not self._more_open

    # ---------------------------------------------------------- 交互
    def _ph_in(self, _e=None):
        if self.entry.get() == self._ph:
            self.entry.delete(0, "end")
            self.entry.config(fg=T.TXT)

    def _ph_out(self, _e=None):
        if not self.entry.get().strip():
            self.entry.insert(0, self._ph)
            self.entry.config(fg=T.TXT4)

    def _text(self):
        txt = self.entry.get()
        return "" if txt == self._ph else (txt or "").strip()

    def _quick(self, t):
        self._active_quick = t
        # 胶囊会在自己的点击回调里被替换，延后一帧重建，避免销毁正在响应的控件
        self.after(0, self._render_quick)
        self.entry.delete(0, "end")
        self.entry.insert(0, t)
        self.entry.config(fg=T.TXT)
        self.search()

    def _go_topic(self):
        direction = self._direction or self._text()
        page = self.app.page("topic")
        if direction:
            page.entry.delete(0, "end")
            page.entry.insert(0, direction)
            page.entry.config(fg=T.TXT)
        self.app.goto("topic")

    def _clear_entry(self):
        if self._busy:
            return
        self.entry.delete(0, "end")
        self.entry.config(fg=T.TXT)
        self.entry.focus_set()
        self._active_quick = ""
        self._render_quick()
        if not self._busy:
            self.result = None
            self._clear()
            self.summary.config(
                text="输入研究方向，点「抓取」或选一个常用方向。", fg=T.TXT3)

    def _days_back(self):
        return {"最近 1 个月": 30, "最近 3 个月": 90,
                "最近 6 个月": 180, "最近 1 年": 365}.get(self.days.get(), 180)

    def search(self):
        if self._busy:
            return
        d = self._text()
        if not d:
            self.summary.config(text="先输入一个方向名，比如「红外小目标检测」。",
                                fg=T.WARN)
            return
        srcs = tuple(s for s, v in self.src_vars.items() if v.get())
        if not srcs:
            self.summary.config(text="至少选一个来源。", fg=T.WARN)
            return
        self._busy = True
        self.btn.config(state="disabled", text="抓取中…")
        self.clear_btn.config(state="disabled")
        self.summary.config(text="正在从 %d 个源抓取「%s」…" % (len(srcs), d),
                            fg=T.TXT3)
        self._clear()
        days = self._days_back()
        threading.Thread(target=self._work, args=(d, srcs, days),
                         daemon=True).start()

    def _work(self, d, srcs, days):
        try:
            r = PS.fetch_all(d, sources=srcs, limit=25, days_back=days)
            # 0 篇时，如果配了大模型，让它改写检索式再试一次。
            # 本地词表只有 200 多条，遇到组合词（「事件相机语义分割」）常常拼不对；
            # 但模型也可能给出错式子，所以**必须**先验证再抓。
            if not (r.get("papers")) and L.is_ready():
                q = L.rewrite_query(d)
                if q and _valid_arxiv_query(q):
                    r2 = PS.fetch_all(d, sources=srcs, limit=25,
                                      days_back=days,
                                      use_cache=False, override_query=q)
                    if r2.get("papers"):
                        r2["llm_query"] = q
                        r = r2
            self.app.post(lambda: self._done(d, r, None))
        except Exception as exc:
            err = exc
            self.app.post(lambda: self._done(d, None, err))

    def explain(self):
        """让大模型读这批论文标题，写技术走向。"""
        papers = ((self.result or {}).get("papers") or [])
        if not papers:
            self.app.toast("先抓一批论文，再让 AI 总结", T.WARN)
            return
        if not L.is_ready():
            self.app.toast("还没配置大模型，去「设置与数据」里填一下", T.WARN)
            try:
                self.app.goto("settings")
            except Exception:
                pass
            return
        d = self._direction
        query_id = self._query_id
        self.ai_btn.config(state="disabled", text="思考中…")
        self.summary.config(text="正在让大模型读这 %d 篇论文的标题…" % len(papers),
                            fg=T.TXT3)

        def work():
            txt = L.explain_direction(d, papers)
            self.app.post(lambda: self._explain_done(txt)
                          if query_id == self._query_id else None)
        threading.Thread(target=work, daemon=True).start()

    def _explain_done(self, txt):
        self.ai_btn.config(state="normal", text="AI 总结")
        if not txt:
            self.summary.config(text="大模型没有返回内容，检查设置里的连接是否正常。",
                                fg=T.WARN)
            return
        self.summary.config(text="「%s」· 大模型解读，需要你自己判断"
                                % self._direction, fg=T.TXT3)
        for w in self.ai_host.winfo_children():
            w.destroy()
        T.Btn(self.ai_host, "查看 AI 总结", lambda: self._show_explanation(txt)).pack(
            anchor="w", padx=T.PAD, pady=(0, 6))
        self._show_explanation(txt)

    def _show_explanation(self, text):
        T.close_child(self)
        win = T.child_window(self, "AI 总结", "760x580")
        self._child_win = win
        tk.Label(win, text="技术走向", bg=T.BG, fg=T.TXT,
                 font=T.T_PAGE_TITLE()).pack(anchor="w", padx=18, pady=(14, 2))
        note = tk.Label(win, text="由大模型生成；仅基于这批标题，引用前请核对原文。",
                        bg=T.BG, fg=T.TXT3, font=T.T_CAPTION(), justify="left")
        note.pack(fill="x", padx=18, pady=(0, 10))
        T.fill_wrap(note)
        footer = U.WrapRow(win, bg=T.BG)
        footer.pack(side="bottom", fill="x", padx=18, pady=12)
        footer.add(T.Btn(footer, "复制总结", lambda: self._copy(text)))
        footer.add(T.Btn(footer, "关闭", win.destroy, "primary"))
        card = T.Card(win, pad=12)
        card.pack(fill="both", expand=True, padx=18)
        scroll = T.ScrollArea(card.body, bg=T.CARD)
        scroll.pack(fill="both", expand=True)
        lb = tk.Label(scroll.inner, text=text, bg=T.CARD, fg=T.TXT2,
                      font=T.T_BODY_SM(), anchor="w", justify="left")
        lb.pack(fill="x")
        T.fill_wrap(lb)
        scroll.refresh()

    def _done(self, d, r, err):
        self._busy = False
        self.btn.config(state="normal", text="抓取")
        self.clear_btn.config(state="normal")
        if err is not None:
            self.result = None
            self._empty = ("抓取未完成", "检查网络和来源设置后重新抓取。")
            self._render_list()
            self.summary.config(text="抓取出错：%s" % err, fg=T.ERR)
            kb._log_exc(type(err), err, err.__traceback__)
            return
        self.result = r
        self._render(d, r)

    def _clear(self):
        self._query_id += 1
        self.result = None
        self._direction = ""
        self.ai_btn.config(state="disabled", text="AI 总结")
        self.dl_all_btn.config(state="disabled", text="下载前 5 篇", fg=T.TXT4)
        T.close_child(self)
        for host in (self.box.inner, self.notice_host, self.ai_host):
            for w in host.winfo_children():
                w.destroy()
        self.box.refresh()
        self._papers = []
        self._sel = -1
        self._frames = {}
        self._dl_btns = {}
        self._empty = None
        self._render_list()
        self._render_detail(None)

    # ---------------------------------------------------------- 渲染
    def _row_h(self):
        if LatestPage.ROW_H is None:
            LatestPage.ROW_H = T.sp(58)
        return LatestPage.ROW_H

    def _render_list(self):
        for w in self.box.inner.winfo_children():
            w.destroy()
        self._frames = {}
        self._sel = -1
        if not self._papers:
            title, body = self._empty or (
                "输入方向开始抓取",
                "或点一个常用方向；抓到后可下载 PDF、存进创新点库。")
            UK.EmptyPanel(self.box.inner, title, body, icon="search",
                          bg=T.CARD, height=220).pack(fill="x", pady=(6, 0))
            self.box.refresh()
            return
        for i, p in enumerate(self._papers):
            self._row(i, p)
        self.box.refresh()
        self.box.scroll_to_top()

    def _row(self, i, p):
        f = tk.Frame(self.box.inner, bg=T.CARD, cursor="hand2",
                     height=self._row_h())
        f.pack(fill="x")
        f.pack_propagate(False)
        bar = tk.Frame(f, bg=T.CARD, width=3)
        bar.pack(side="left", fill="y")
        right = tk.Frame(f, bg=T.CARD, width=T.sp(118))
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        mid = tk.Frame(f, bg=T.CARD)
        mid.pack(side="left", fill="both", expand=True, padx=(8, 6),
                 pady=T.sp(6))

        title = p.get("title") or "—"
        tl = tk.Label(mid, text=_short(title, 120), bg=T.CARD, fg=T.TXT,
                      font=T.T_LABEL(), anchor="w")
        tl.pack(fill="x")
        tl.bind("<Configure>", lambda e, w=tl, t=title: self._fit_text(w, t))

        badge = self._badge(p, short=True)
        meta = []
        if p.get("venue"):
            meta.append(_short(p["venue"], 34))
        au = p.get("authors") or []
        if au:
            meta.append(_short(", ".join(au[:2])
                               + (" 等" if len(au) > 2 else ""), 40))
        if p.get("cited"):
            meta.append("被引 %d" % p["cited"])
        ml = tk.Label(mid, text=" · ".join(meta) or "作者与会议未标注",
                      bg=T.CARD, fg=T.TXT3, font=T.F(9), anchor="w")
        ml.pack(fill="x", pady=(1, 0))
        ml.bind("<Configure>",
                lambda e, w=ml, t=(" · ".join(meta) or "作者与会议未标注"):
                self._fit_text(w, t))

        stack = tk.Frame(right, bg=T.CARD)
        stack.place(relx=1.0, rely=0.5, anchor="e")
        tk.Label(stack, text=p.get("published") or "—", bg=T.CARD,
                 fg=T.TXT3, font=T.F(8), anchor="e").pack(
                     side="top", anchor="e")
        tk.Label(stack, text=badge, bg=T.CARD, fg=T.ACCENT,
                 font=T.F(7, True), anchor="e").pack(side="top", anchor="e")

        line = tk.Frame(f, bg=T.LINE_SOFT, height=1)
        line.place(relx=0, rely=1.0, relwidth=1, anchor="sw")
        parts = [f, mid, tl, ml, right, stack, bar, line]
        parts.extend(stack.winfo_children())
        self._frames[i] = (f, parts, line, bar)

        def pick(_e, idx=i):
            self.select(idx)

        for w in parts:
            w.bind("<Button-1>", pick)

        def hover(on):
            f._hover = on
            self._style(i)

        for w in (f, mid, tl, ml, right, stack):
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", lambda e: hover(False), add="+")
        self._style(i)

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
        sel = (i == self._sel)
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
        if not (0 <= i < len(self._papers)):
            return
        old = self._sel
        self._sel = i
        if old != i:
            self._style(old)
        self._style(i)
        self._render_detail(self._papers[i])

    def _render(self, d, r):
        papers = r.get("papers") or []
        by = r.get("by_source") or {}
        self._papers = papers
        self._direction = d
        self._dl_btns = {}
        self.ai_btn.config(state="normal" if papers else "disabled", text="AI 总结")
        n_pdf = sum(1 for p in papers if KB.pdf_candidates(p))
        self.dl_all_btn.config(
            state="normal" if n_pdf else "disabled",
            text="下载前 %d 篇" % min(5, n_pdf) if n_pdf else "无可下载全文",
            fg=T.TXT2 if n_pdf else T.TXT4,
            cursor="hand2" if n_pdf else "arrow")

        if not papers:
            self.summary.config(
                text="「%s」没有抓到论文。可能是方向名太细，换个更常见的中文说法试试%s。"
                     % (d, "（大模型改写的式子也没命中）"
                        if L.is_ready() else "，或在设置里连上大模型让它改写检索式"),
                fg=T.WARN)
            self._empty = ("没有抓到论文",
                           "换个更常见的中文说法，或检查上方失败的来源。")
            self._render_notice(r)
            self._render_list()
            self._render_detail(None)
            return

        latest = papers[0].get("published") or "—"
        hit = sum(1 for s, n in by.items() if n)

        src_txt = " · ".join("%s %d" % (PS.SOURCE_LABEL.get(s, s), n)
                             for s, n in by.items())
        msg = "「%s」共 %d 篇（去重后） · 最新 %s" % (d, len(papers), latest)
        if src_txt:
            msg += " · " + src_txt
        msg += " · %d / %d 源 · 范围 %s" % (
            hit, len(PS.ALL_SOURCES), self.days.get().replace("最近 ", ""))
        if r.get("cached"):
            msg += " · 缓存"
        self.summary.config(text=msg, fg=T.TXT3)

        # 失败源与改写检索式：单独一条安静提示，不吞错误
        self._render_notice(r)
        self._render_list()
        if papers:
            self.select(0)
        else:
            self._render_detail(None)

    def _render_notice(self, r):
        for w in self.notice_host.winfo_children():
            w.destroy()
        notices = []
        if r.get("llm_query"):
            notices.append(("本地词表没匹配到，已改用大模型改写的检索式："
                            + r["llm_query"], T.PURPLE))
        for s, e in (r.get("errors") or []):
            notices.append(("⚠ %s 抓取失败：%s"
                            % (PS.SOURCE_LABEL.get(s, s), _short(e, 90)),
                            T.WARN))
        for txt, fg in notices:
            lb = tk.Label(self.notice_host, text=txt, bg=T.BG, fg=fg,
                          font=T.T_CAPTION(), anchor="w", justify="left")
            lb.pack(fill="x")
            T.fill_wrap(lb, pad=6)

    # ------------------------------------------------------------ 详情
    def _sec(self, parent, text):
        tk.Label(parent, text=text, bg=T.CARD, fg=T.TXT2, font=T.T_LABEL(),
                 anchor="w").pack(fill="x", padx=4, pady=(10, 2))

    def _para(self, parent, text, color=None):
        lb = tk.Label(parent, text=text, bg=T.CARD, fg=color or T.TXT2,
                      font=T.T_BODY_SM(), anchor="w", justify="left")
        lb.pack(fill="x", padx=6)
        T.fill_wrap(lb, pad=8)

    def _kv(self, parent, label, value, link=None):
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x", padx=6, pady=(2, 0))
        tk.Label(row, text=label, bg=T.CARD, fg=T.TXT4,
                 font=T.T_CAPTION(), width=6, anchor="w").pack(side="left")
        fg = T.ACCENT if link else T.TXT2
        lb = tk.Label(row, text=value, bg=T.CARD, fg=fg, font=T.T_BODY_SM(),
                      anchor="w", justify="left",
                      cursor="hand2" if link else "")
        lb.config(width=1)
        lb.pack(side="left", fill="x", expand=True)
        lb.bind("<Configure>", lambda e: lb.config(wraplength=max(1, e.width - 8)))
        if link:
            lb.bind("<Button-1>", lambda e, u=link: self.app.open_url(u))

    @staticmethod
    def _badge(p, short=False):
        """来源徽标。列表右栏窄，多源命中只给 +N，避免压到标题。"""
        src = p.get("source") or ""
        also = p.get("also_in") or []
        b = PS.SOURCE_LABEL.get(src, src)
        if also:
            if short:
                b += " +%d" % len(also)
            else:
                b += " +" + "/".join(PS.SOURCE_LABEL.get(a, a) for a in also)
        return b

    def _render_detail(self, p):
        for w in self.detail_box.inner.winfo_children():
            w.destroy()
        for w in self._detail_foot.winfo_children():
            w.destroy()
        self._dl_btns = {}
        inner = self.detail_box.inner
        if not p:
            UK.EmptyPanel(inner, "选中一篇论文",
                          "看摘要、作者、下载入口与原文链接。",
                          icon="search", bg=T.CARD, height=210).pack(
                              fill="x", pady=(4, 0))
            self.detail_box.refresh()
            return

        UK.eyebrow(inner, "最新研究 / PAPER", "03").pack(
            fill="x", padx=4, pady=(2, 6))
        title = p.get("title") or "—"
        tl = tk.Label(inner, text=title, bg=T.CARD, fg=T.TXT,
                      font=T.T_SECTION(), anchor="w", justify="left")
        tl.pack(fill="x", padx=4)
        T.fill_wrap(tl, pad=6)

        badge = self._badge(p)
        bits = [badge]
        if p.get("published"):
            bits.append(p["published"])
        if p.get("venue"):
            bits.append(_short(p["venue"], 40))
        if p.get("cited"):
            bits.append("被引 %d" % p["cited"])
        ml = tk.Label(inner, text=" · ".join(bits), bg=T.CARD, fg=T.TXT3,
                      font=T.T_CAPTION(), anchor="w", justify="left")
        ml.pack(fill="x", padx=4, pady=(2, 8))
        T.fill_wrap(ml, pad=6)

        tk.Frame(self._detail_foot, bg=T.LINE_SOFT, height=1).pack(
            fill="x", pady=(0, 8))
        acts = U.WrapRow(self._detail_foot, gap=6, rowgap=6, bg=T.CARD)
        acts.pack(fill="x")
        has_pdf = bool(KB.pdf_candidates(p))
        b = T.Btn(acts, "下载 PDF" if has_pdf else "无公开全文",
                  lambda p=p: self._download(p), "primary" if has_pdf else "ghost")
        if not has_pdf:
            b.config(state="disabled", fg=T.TXT4, cursor="arrow")
        acts.add(b)
        self._dl_btns[id(p)] = b
        st = self._dl_state.get(id(p))
        if st == "done":
            b.config(text="重新下载")
        elif st == "fail":
            b.config(text="重试下载")
        elif st == "busy":
            b.config(state="disabled", text="下载中…")
        acts.add(T.Btn(acts, "存为已有工作", lambda p=p: self._save(p)))
        more = T.Btn(acts, "更多 ▾", None, "ghost")
        acts.add(more)
        more.set_command(lambda p=p, m=more: self._row_menu(m, p, p.get("url") or ""))

        ab = (p.get("abstract") or "").strip()
        if ab:
            self._sec(inner, "摘要")
            self._para(inner, ab)

        self._sec(inner, "信息")
        au = p.get("authors") or []
        if au:
            self._kv(inner, "作者", ", ".join(au))
        if p.get("venue"):
            self._kv(inner, "发表", p["venue"])
        if p.get("doi"):
            self._kv(inner, "DOI", p["doi"])
        url = p.get("url") or ""
        if url:
            self._kv(inner, "链接", "打开原文 ↗", link=url)
        self._kv(inner, "来源", badge)

        tip = tk.Label(inner, text="这是自动抓取的清单，不是综述；引用前请核对原文。",
                       bg=T.CARD, fg=T.TXT4, font=T.T_CAPTION(),
                       anchor="w", justify="left")
        tip.pack(fill="x", padx=4, pady=(12, 4))
        T.fill_wrap(tip, pad=6)
        self.detail_box.refresh()
        self.detail_box.scroll_to_top()

    # ------------------------------------------------------------ 动作
    def _open(self, url):
        try:
            webbrowser.open(url)
        except Exception as exc:
            self.app.toast("打不开链接：%s" % exc, T.ERR)

    def _row_menu(self, anchor, p, url):
        """行内「更多 ▾」：打开原文 / 复制标题 / 复制链接。"""
        try:
            m = tk.Menu(self, tearoff=0, bg=T.CARD, fg=T.TXT,
                        activebackground=T.ACCENT_D, activeforeground=T.ACCENT,
                        bd=0, relief="flat", font=T.T_BODY_SM())
            if url:
                m.add_command(label="打开原文", command=lambda: self._open(url))
                m.add_command(label="复制链接", command=lambda: self._copy(url))
            m.add_command(label="复制标题",
                          command=lambda: self._copy(p.get("title") or ""))
            ab = (p.get("abstract") or "").strip()
            if ab:
                m.add_command(label="复制摘要", command=lambda: self._copy(ab))
            m.tk_popup(anchor.winfo_rootx(),
                       anchor.winfo_rooty() + anchor.winfo_height() + 2)
        except Exception as exc:
            print("弹出菜单失败:", exc)

    def _dl_dir(self):
        """下载目标目录：设置里指定了固定目录就用它，否则进今天的收件箱。"""
        try:
            cfg = kb.load_config()
        except Exception:
            cfg = {}
        want = (cfg.get("download_dir") or "").strip()
        if want:
            return want, "设置里指定的「%s」" % want
        return None, "今天的收件箱"

    def _download(self, p):
        if id(p) in self._dl_state and self._dl_state[id(p)] == "busy":
            return
        btn = self._dl_btns.get(id(p))
        if btn is not None:
            self._dl_state[id(p)] = "busy"
            btn.config(state="disabled", text="下载中…")
        out_dir, where = self._dl_dir()
        d = self._direction
        self.summary.config(text="正在下载「%s」到%s…" % (_short(p.get("title"), 40), where),
                            fg=T.TXT3)

        def work():
            try:
                r = KB.download(p, out_dir=out_dir, direction=d)
            except Exception as exc:      # 后台线程绝不能静默死掉，否则按钮永远「下载中…」
                r = {"ok": False, "path": "", "bytes": 0, "source": "",
                     "txt": False, "skipped": False,
                     "reason": "下载线程出错：%s" % exc}
            self.app.post(lambda: self._dl_done(p, r))

        threading.Thread(target=work, daemon=True).start()

    def _dl_done(self, p, r):
        key = id(p)
        btn = self._dl_btns.get(key)
        if r.get("skipped"):
            self._dl_state[key] = "done"
            if btn is not None:
                btn.config(state="normal", text="已在库里", fg=T.TXT4)
            self.summary.config(text="«%s» %s" % (_short(p.get("title"), 36), r["reason"]),
                                fg=T.TXT3)
            self.app.toast(r["reason"], T.TXT3)
        elif r.get("ok"):
            self._dl_state[key] = "done"
            if btn is not None:
                btn.config(state="normal", text="重新下载")
            size = "%.1f MB" % (r.get("bytes", 0) / 1048576.0)
            self.summary.config(
                text="已下载 «%s» %s · %s%s" % (
                    _short(p.get("title"), 36), size, r["reason"],
                    " · 已生成首页文本" if r.get("txt") else ""),
                fg=T.OK)
            self.app.toast("已存进知识库：%s" % size, T.OK)
            try:
                import profile_hooks as PH
                PH.note("下载论文进知识库：%s" % (p.get("title") or "")[:70],
                        tags=["入库"], kind="daily",
                        ref=(p.get("title") or "")[:80], source="最新研究")
            except Exception:
                pass
        else:
            self._dl_state[key] = "fail"
            if btn is not None:
                btn.config(state="normal", text="重试下载")
            self.summary.config(text="下载失败：「%s」→ %s"
                                     % (_short(p.get("title"), 32), r.get("reason") or "未知原因"),
                                fg=T.ERR)
            self.app.toast("下载失败，原因见上方", T.ERR)

    def download_top(self, n=5):
        """批量下载当前结果里最有希望的几篇。"""
        if self._batch is not None:
            self.app.toast("上一批还在下载", T.WARN)
            return
        papers = (self.result or {}).get("papers") or []
        todo = [p for p in papers if KB.pdf_candidates(p)][:n]
        if not todo:
            self.app.toast("这批里没有可下载的公开全文", T.WARN)
            return
        out_dir, where = self._dl_dir()
        d = self._direction
        self.dl_all_btn.config(state="disabled", text="下载中…")
        self.summary.config(text="正在批量下载 %d 篇到%s…" % (len(todo), where), fg=T.TXT3)

        def on_one(p, r):
            self.app.post(lambda: self._dl_done(p, r))

        def on_done(summary, results):
            def fin():
                self._batch = None
                # 恢复按钮时必须跟 _render 里的口径一致，不能写死「下载前 5 篇」
                avail = sum(1 for p in ((self.result or {}).get("papers") or [])
                            if KB.pdf_candidates(p))
                self.dl_all_btn.config(
                    state="normal" if avail else "disabled",
                    text=("下载前 %d 篇" % min(5, avail)) if avail else "无可下载全文")
                if summary.get("cancelled"):
                    txt, fg = "批量下载已取消：成功 %d / 已在库 %d" % (
                        summary["ok"], summary["skipped"]), T.WARN
                else:
                    txt = "批量下载完成：成功 %d 篇 · 已在库 %d 篇 · 失败 %d 篇" % (
                        summary["ok"], summary["skipped"], summary["fail"])
                    fg = T.OK if not summary["fail"] else T.WARN
                    if summary["fail"]:
                        first = [r for r in results if not r.get("ok")
                                 and not r.get("skipped")]
                        if first:
                            txt += "（如：%s）" % _short(first[0].get("reason"), 50)
                self.summary.config(text=txt, fg=fg)
            self.app.post(fin)

        self._batch = KB.Batch(todo, out_dir=out_dir, on_one=on_one,
                               on_done=on_done, direction=d).start()

    def _copy(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.app.toast("标题已复制", T.OK)
        except Exception as exc:
            self.app.toast("复制失败：%s" % exc, T.ERR)

    def _save(self, p):
        """存进创新点库当「已有工作」。

        注意：这是**外部抓来的**论文，不是用户自己的。存进去时标题前缀
        【已有工作】并把来源写进描述，免得以后分不清哪些是自己想的。
        用户私有数据走 kb.save_research_memory，不覆写整个文件。
        """
        try:
            mem = kb.load_research_memory()
            ideas = mem.setdefault("ideas", [])
            title = p.get("title") or ""
            if any((i.get("title") or "").endswith(title) for i in ideas):
                self.app.toast("这条已经在创新点库里了", T.WARN)
                return
            desc = "来源：%s　%s\n作者：%s\n链接：%s" % (
                PS.SOURCE_LABEL.get(p.get("source"), p.get("source")),
                p.get("published") or "", ", ".join((p.get("authors") or [])[:5]),
                p.get("url") or "")
            if p.get("abstract"):
                desc += "\n\n" + p["abstract"][:400]
            ideas.append({"title": "【已有工作】" + title,
                          "desc": desc,
                          "direction": self._direction,
                          "added": time.strftime("%Y-%m-%d %H:%M"),
                          "kind": "external"})
            kb.save_research_memory(mem)
            self.app.toast("已存进创新点库（标记为已有工作）", T.OK)
            try:
                import profile_hooks as PH
                dir_ = self._direction
                if dir_:
                    PH.see_field(dir_, source="最新研究")
                PH.note("收藏了论文：%s" % title[:80],
                        tags=[t for t in ["收藏", dir_] if t],
                        kind="daily", ref=title.strip()[:80], source="最新研究")
            except Exception:
                pass
            if "ideas" in self.app.pages and hasattr(self.app.pages["ideas"], "reload"):
                self.app.pages["ideas"].reload()
        except Exception as exc:
            self.app.toast("保存失败：%s" % exc, T.ERR)
            kb._log_exc(type(exc), exc, exc.__traceback__)

    def prefill(self, direction):
        """从别的页面跳过来时带着方向。"""
        self.entry.delete(0, "end")
        self.entry.insert(0, direction or "")
        self.entry.config(fg=T.TXT if direction else T.TXT4)
        if not direction:
            self._ph_out()

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

    def reload(self):
        pass