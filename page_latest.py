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
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.result = None
        self._busy = False
        self._dl_btns = {}
        self._dl_state = {}
        self._batch = None
        self._build()

    def _build(self):
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        tk.Label(top, text=PAGE_HINT, bg=T.BG, fg=T.TXT4,
                 font=T.F(9)).pack(side="left")
        # 第 8 版简化：首屏只留「输入方向 + 抓取」。
        # 原来这一块是四行：常用方向 5 个按钮 / 方向框 + 清空 / 来源 3 个复选框
        # + 范围下拉 / 说明行，而紧接着的空态卡里又摆了一遍前 3 个方向按钮——
        # 同一批方向一屏出现两次。现在默认值本来就对的选项（来源全选、范围
        # 6 个月）收进「更多设置」，需要时再展开。
        # 三个按钮原来挂在提示语那一行的右边（提示语短、附近全空着），
        # 字号一大就整块被剪掉；改挂到输入框这一行，右侧先 pack 固定，再让输入框 expand。
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=T.PAD, pady=(0, 4))
        T.Btn(bar, "清空", self._clear_entry, "ghost").pack(side="right",
                                                           padx=(6, 0))
        self.btn = T.Btn(bar, "抓取", self.search, "primary")
        self.btn.pack(side="right", padx=(6, 0))
        # 大模型总结按钮：没配置时也显示，点了告诉用户去设置页配
        self.ai_btn = T.Btn(bar, "AI 总结", self.explain)
        self.ai_btn.pack(side="right", padx=(6, 0))
        # 批量下载：一篇篇点太慢，但一次全下又会把 arXiv 拖垮，
        # 所以给个「下载前 5 篇」——上限写死，不做成输入框骗人
        self.dl_all_btn = T.Btn(bar, "下载前 5 篇", self.download_top)
        self.dl_all_btn.pack(side="right", padx=(6, 0))
        self.dl_all_btn.config(state="disabled", fg=T.TXT4, cursor="arrow")
        self.entry = tk.Entry(bar, bg=T.CARD, fg=T.TXT, insertbackground=T.ACCENT,
                              relief="flat", highlightbackground=T.LINE,
                              highlightthickness=1, font=T.T_BODY())
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        try:
            import app_suggest
            app_suggest.attach(self.entry)
        except Exception as exc:
            print("联想词挂载失败:", exc)
        self.entry.bind("<Return>", lambda e: self.search())

        # 常用方向 + 更多设置：折行容器，字号放大后自动换行
        qrow = tk.Frame(self, bg=T.BG)
        qrow.pack(fill="x", padx=T.PAD, pady=(0, 4))
        self._more_open = False
        self._adv_btn = T.Btn(qrow, "更多设置", self._toggle_adv, "ghost")
        self._adv_btn.pack(side="right", padx=(6, 0))
        self._quick_row = U.WrapRow(qrow, bg=T.BG)
        self._quick_row.pack(side="left", fill="x", expand=True)
        for t in QUICK:
            self._quick_row.add(
                T.Btn(self._quick_row, t, lambda x=t: self._quick(x), "ghost"))

        # 折叠区：来源 / 范围。默认值是对的，所以默认不展开。
        self.adv = tk.Frame(self, bg=T.BG)
        tk.Label(self.adv, text="来源", bg=T.BG, fg=T.TXT3,
                 font=T.T_CAPTION()).pack(side="left", padx=(0, 8))
        self.src_vars = {}
        for s in PS.ALL_SOURCES:
            v = tk.BooleanVar(value=True)
            self.src_vars[s] = v
            cb = tk.Checkbutton(self.adv, text=PS.SOURCE_LABEL[s], variable=v,
                                bg=T.BG, fg=T.TXT2, selectcolor=T.CARD,
                                activebackground=T.BG, activeforeground=T.TXT,
                                font=T.T_CAPTION(), bd=0, highlightthickness=0)
            cb.pack(side="left", padx=(0, 10))
        tk.Label(self.adv, text="范围", bg=T.BG, fg=T.TXT3,
                 font=T.T_CAPTION()).pack(side="left", padx=(8, 6))
        self.days = tk.StringVar(value="最近 6 个月")
        om = tk.OptionMenu(self.adv, self.days, "最近 1 个月", "最近 3 个月",
                           "最近 6 个月", "最近 1 年")
        om.config(bg=T.CARD, fg=T.TXT, activebackground=T.CARD_HI,
                  highlightthickness=1, highlightbackground=T.LINE,
                  relief="flat", font=T.T_CAPTION(), width=10)
        om.pack(side="left")

        self.summary = tk.Label(self, text="输入一个研究方向，点「抓取」。",
                                bg=T.BG, fg=T.TXT3, font=T.T_CAPTION(), anchor="w")
        self.summary.pack(fill="x", padx=T.PAD + 4, pady=(0, 6))

        self.box = T.ScrollArea(self, bg=T.BG)
        self.box.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        self._build_empty()

    def _build_empty(self):
        """没抓取前的空态。

        原来这里是「怎么用」三步教程 + 「不想输字？」两块卡，加起来占了
        大半个屏幕，而用户真正需要的只有一句「现在该点哪里」。
        现在改成：一句引导 + 直接能点的方向按钮 + 一个主按钮，
        教程收进 ? 里按需展开。
        """
        for w in self.box.inner.winfo_children():
            w.destroy()
        wrap = tk.Frame(self.box.inner, bg=T.BG)
        wrap.pack(fill="x")

        card = T.Card(wrap, pad=16)
        card.pack(fill="x")
        # 第 8 版：上面那一行已经有这批方向按钮了，这里再摆一遍等于
        # 同一屏两处入口。空态只说「下一步点哪」，并给一条去选题工坊的出路。
        tk.Label(card.body, text="在上面输入方向按回车，或者点一个常用方向，就会去抓最近发表。",
                 bg=T.CARD, fg=T.TXT2, font=T.T_BODY(), anchor="w", justify="left",
                 wraplength=T.wrap(560)).pack(fill="x", pady=(2, 4))
        tk.Label(card.body,
                 text="抓取会联网请求 arXiv / OpenAlex / Europe PMC，结果缓存 6 小时；"
                      "没有网络时这一页用不了，其余页面不受影响。",
                 bg=T.CARD, fg=T.TXT4, font=T.T_CAPTION(), anchor="w", justify="left",
                 wraplength=T.wrap(560)).pack(fill="x", pady=(0, 4))
        # 快捷去向：把读者从「看一篇」引到「扒一批」（第 10 版）。
        # 这一页最常见的需求其实是「这周这个方向出了什么」，而不是逐篇读；
        # 给他一条明确的下一步，比让他自己去侧栏找「文献库」快。
        nxt = tk.Frame(card.body, bg=T.CARD)
        nxt.pack(fill="x", pady=(6, 0))
        tk.Label(nxt, text="抓到的论文可以直接进库，之后到「文献库」里统一搜。",
                 bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(), anchor="w").pack(side="left")
        T.Btn(nxt, "去文献库", lambda: self.app.goto("library"), "ghost").pack(side="left", padx=(8, 0))
        self.box.refresh()

    def _toggle_adv(self):
        """来源 / 范围 的显隐。默认收起：三个来源全选、范围 6 个月本来就是对的选择。"""
        if self._more_open:
            self.adv.pack_forget()
            self._adv_btn.config(text="更多设置")
        else:
            self.adv.pack(fill="x", padx=T.PAD, pady=(0, 4),
                          after=self.entry.master)
            self._adv_btn.config(text="收起设置")
        self._more_open = not self._more_open

    def _go(self, t):
        self._quick(t)

    # ---------------------------------------------------------- 交互
    def _quick(self, t):
        self.entry.delete(0, "end")
        self.entry.insert(0, t)
        self.search()

    def _clear_entry(self):
        self.entry.delete(0, "end")
        self.entry.focus_set()
        if not self._busy:
            self._build_empty()
            self.summary.config(text="输入一个研究方向，点「抓取」。", fg=T.TXT3)

    def _days_back(self):
        return {"最近 1 个月": 30, "最近 3 个月": 90,
                "最近 6 个月": 180, "最近 1 年": 365}.get(self.days.get(), 180)

    def search(self):
        if self._busy:
            return
        d = (self.entry.get() or "").strip()
        if not d:
            self.summary.config(text="先输入一个方向名，比如「红外小目标检测」。", fg=T.WARN)
            return
        srcs = tuple(s for s, v in self.src_vars.items() if v.get())
        if not srcs:
            self.summary.config(text="至少选一个来源。", fg=T.WARN)
            return
        self._busy = True
        self.btn.config(state="disabled", text="抓取中…")
        self.summary.config(text="正在从 %d 个源抓取「%s」…" % (len(srcs), d),
                            fg=T.TXT3)
        self._clear()
        self._hint_box = None
        days = self._days_back()
        threading.Thread(target=self._work, args=(d, srcs, days), daemon=True).start()

    def _work(self, d, srcs, days):
        try:
            r = PS.fetch_all(d, sources=srcs, limit=25, days_back=days)
            # 0 篇时，如果配了大模型，让它改写检索式再试一次。
            # 本地词表只有 200 多条，遇到组合词（「事件相机语义分割」）常常拼不对；
            # 但模型也可能给出错式子，所以**必须**先验证再抓。
            if not (r.get("papers")) and L.is_ready():
                q = L.rewrite_query(d)
                if q and _valid_arxiv_query(q):
                    r2 = PS.fetch_all(d, sources=srcs, limit=25, days_back=days,
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
        d = (self.entry.get() or "").strip()
        self.ai_btn.config(state="disabled", text="思考中…")
        self.summary.config(text="正在让大模型读这 %d 篇论文的标题…" % len(papers),
                            fg=T.TXT3)

        def work():
            txt = L.explain_direction(d, papers)
            self.app.post(lambda: self._explain_done(txt))
        threading.Thread(target=work, daemon=True).start()

    def _explain_done(self, txt):
        self.ai_btn.config(state="normal", text="AI 总结这批论文")
        if not txt:
            self.summary.config(text="大模型没有返回内容，检查设置里的连接是否正常。",
                                fg=T.WARN)
            return
        self.summary.config(text="「%s」· 大模型解读，需要你自己判断"
                                % (self.entry.get() or "").strip(), fg=T.TXT3)
        # 插到列表最前面
        card = T.Card(self.box.inner, pad=12)
        card.pack(fill="x", pady=(0, 10))
        top = tk.Frame(card.body, bg=T.CARD)
        top.pack(fill="x")
        tk.Label(top, text="AI 读出来的技术走向", bg=T.CARD, fg=T.ACCENT,
                 font=T.F(10, True), anchor="w").pack(side="left")
        tk.Label(top, text="由大模型生成 · 引用前请核对原文", bg=T.CARD, fg=T.TXT4,
                 font=T.F(8), anchor="e").pack(side="right")
        tk.Label(card.body, text=txt, bg=T.CARD, fg=T.TXT2, font=T.F(9),
                 anchor="w", justify="left", wraplength=T.wrap(820)).pack(
                     fill="x", pady=(6, 0))
        card.lift()
        self.box.refresh()

    def _done(self, d, r, err):
        self._busy = False
        self.btn.config(state="normal", text="抓取")
        if err is not None:
            self.summary.config(text="抓取出错：%s" % err, fg=T.ERR)
            kb._log_exc(type(err), err, err.__traceback__)
            return
        self.result = r
        self._render(d, r)

    def _clear(self):
        for w in self.box.inner.winfo_children():
            w.destroy()
        self.box.refresh()

    # ---------------------------------------------------------- 渲染
    def _render(self, d, r):
        papers = r.get("papers") or []
        by = r.get("by_source") or {}
        errs = r.get("errors") or []
        # 每批新结果都重置下载按钮表：旧按钮随旧卡片一起被销毁了，
        # 留着会指向已经 destroy 的控件，点一下就是 TclError
        self._dl_btns = {}
        self._dl_state = {}
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
                        if L.is_ready() else "，或在设置里接上大模型让它改写检索式"),
                fg=T.WARN)
            self.box.refresh()
            return

        latest = papers[0].get("published") or ""
        # 摘要行：拿了多少、最新是哪天、各源分布
        src_txt = "  ".join("%s %d" % (PS.SOURCE_LABEL.get(s, s), n)
                            for s, n in by.items())
        msg = ("「%s」共 %d 篇（去重后），最新 %s　·　%s"
               % (d, len(papers), latest, src_txt))
        if r.get("cached"):
            msg += "　·　缓存"
        self.summary.config(text=msg, fg=T.TXT3)
        # 大模型改写过检索式时要明说，否则用户不知道这次查的是什么
        if r.get("llm_query"):
            tk.Label(self.box.inner,
                     text="本地词表没匹配到，已改用大模型改写的检索式：\n" + r["llm_query"],
                     bg=T.BG, fg=T.PURPLE, font=T.F(9), anchor="w",
                     justify="left", wraplength=T.wrap(900)).pack(fill="x", pady=(0, 8))
        if errs:
            # 失败的源单独一行，红字，不藏
            box = tk.Frame(self.box.inner, bg=T.BG)
            box.pack(fill="x", pady=(0, 8))
            for s, e in errs:
                tk.Label(box, text="⚠ %s 抓取失败：%s" % (PS.SOURCE_LABEL.get(s, s), _short(e, 90)),
                         bg=T.BG, fg=T.WARN, font=T.F(9),
                         anchor="w", justify="left",
                         wraplength=T.wrap(900)).pack(fill="x")

        # 按月份分组，让"最近"这件事看得见
        cur_month = None
        for p in papers:
            mon = (p.get("published") or "")[:7]
            if mon != cur_month:
                cur_month = mon
                tk.Label(self.box.inner, text=mon or "日期未知", bg=T.BG, fg=T.TXT4,
                         font=T.F(9, True), anchor="w").pack(fill="x", pady=(10, 4))
            self._row(p)
        # 列表底部给一条「接下来做什么」。用户抓完 25 篇一眼扫完，
        # 最常做的是两件事：全下进库、或者回工坊用这个方向出题。
        tail = tk.Frame(self.box.inner, bg=T.BG)
        tail.pack(fill="x", pady=(6, 4))
        tk.Label(tail, text="看完之后：", bg=T.BG, fg=T.TXT3,
                 font=T.T_CAPTION()).pack(side="left", padx=(2, 8))
        T.Btn(tail, "用这个方向去选题工坊",
              lambda: self._go_topic(d), "ghost").pack(side="left", padx=(0, 6))
        T.Btn(tail, "到文献库搜索",
              lambda: self.app.goto("library"), "ghost").pack(side="left")
        self.box.refresh()

    def _go_topic(self, d):
        """带着方向跳到选题工坊，并顺手生成一版候选。

        换页再手动粘一次方向是这个功能以前最烦的地方 ——
        用户刚看完别人在做什么，下一步想知道自己能做什么。
        """
        try:
            pg = self.app.page("topic")
            pg.entry.delete(0, "end")
            pg.entry.insert(0, d or "")
            self.app.goto("topic")
            self.app.toast("已带入方向，点「生成候选」即可（或按回车）", T.OK)
        except Exception as exc:
            print("跳转选题工坊失败:", exc)

    def _row(self, p):
        card = T.Card(self.box.inner, pad=10)
        card.pack(fill="x", pady=(0, 6))
        head = tk.Frame(card.body, bg=T.CARD)
        head.pack(fill="x")
        # 右侧固定列先 pack，避免长标题把标签挤出去
        tk.Label(head, text=p.get("published") or "", bg=T.CARD, fg=T.TXT4,
                 font=T.F(8)).pack(side="right", padx=(8, 0))
        src = p.get("source") or ""
        also = p.get("also_in") or []
        badge = PS.SOURCE_LABEL.get(src, src)
        if also:
            badge += " +" + "/".join(PS.SOURCE_LABEL.get(a, a) for a in also)
        tk.Label(head, text=badge, bg=T.CARD, fg=T.ACCENT,
                 font=T.F(8, True)).pack(side="right", padx=(8, 0))
        doi = p.get("doi") or ""
        if doi:
            tk.Label(head, text="DOI", bg=T.CARD, fg=T.TXT3,
                     font=T.F(8)).pack(side="right")
        tk.Label(head, text=_short(p.get("title"), 110), bg=T.CARD, fg=T.TXT,
                 font=T.F(10, True), anchor="w", justify="left").pack(
                     side="left", fill="x", expand=True)

        meta = []
        if p.get("venue"):
            meta.append(_short(p["venue"], 46))
        au = p.get("authors") or []
        if au:
            meta.append(_short(", ".join(au[:3]) + (" 等" if len(au) > 3 else ""), 60))
        if p.get("cited"):
            meta.append("被引 %d" % p["cited"])
        if meta:
            tk.Label(card.body, text=" · ".join(meta), bg=T.CARD, fg=T.TXT3,
                     font=T.F(8), anchor="w", justify="left",
                     wraplength=T.wrap(820)).pack(fill="x", pady=(2, 0))

        ab = (p.get("abstract") or "").strip()
        if ab:
            tk.Label(card.body, text=_short(ab, 230), bg=T.CARD, fg=T.TXT2,
                     font=T.F(9), anchor="w", justify="left",
                     wraplength=T.wrap(820)).pack(fill="x", pady=(3, 0))

        # 动作条（第 10 版）：四个按钮降成三层。
        # 用户看一篇论文时心里只有一个问题「我要不要把它留下」，
        # 所以「下载到知识库」是主按钮；「打开原文 / 复制标题」是次要动作，
        # 「存为已有工作」是另一种留下方式（不占磁盘，进台账）。
        acts = tk.Frame(card.body, bg=T.CARD)
        acts.pack(fill="x", pady=(5, 0))
        url = p.get("url") or ""
        has_pdf = bool(KB.pdf_candidates(p))
        b = T.Btn(acts, "下载到知识库" if has_pdf else "无公开全文",
                  lambda p=p: self._download(p), "ok" if has_pdf else "ghost")
        if not has_pdf:
            b.config(state="disabled", fg=T.TXT4, cursor="arrow")
        b.pack(side="left", padx=(0, 6))
        self._dl_btns[id(p)] = b
        T.Btn(acts, "存为已有工作",
              lambda p=p: self._save(p)).pack(side="left", padx=(0, 6))
        more = T.Btn(acts, "更多 ▾", None, "ghost")
        more.pack(side="left")
        # 用 set_command 而不是 config(command=...)：T.Btn 是 Label 子类，
        # Label 没有 -command 选项，会抛 unknown option "-command" 把整页打断。
        more.set_command(lambda p=p, u=url, m=more: self._row_menu(m, p, u))

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

    # ------------------------------------------------------------ 下载到知识库

    def _dl_dir(self):
        """下载目标目录。

        默认按 KB 既有规矩进「新论文/YYYY-MM-DD」，不替用户归类——
        猜错分类比放收件箱更麻烦，收件箱有速览和日志兜着。
        设置里若指定了固定目录（cfg["download_dir"]），就用它。
        """
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
        d = (self.entry.get() or "").strip()
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
        d = (self.entry.get() or "").strip()
        self.dl_all_btn.config(state="disabled", text="下载中…")
        self.summary.config(text="正在批量下载 %d 篇到%s…" % (len(todo), where), fg=T.TXT3)

        def on_one(p, r):
            self.app.post(lambda: self._dl_done(p, r))

        def on_done(summary, results):
            def fin():
                self._batch = None
                n_ok = summary.get("ok") or 0
                n_skip = summary.get("skipped") or 0
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
                          "direction": (self.entry.get() or "").strip(),
                          "added": time.strftime("%Y-%m-%d %H:%M"),
                          "kind": "external"})
            kb.save_research_memory(mem)
            self.app.toast("已存进创新点库（标记为已有工作）", T.OK)
            # 记住「你在盯这个方向」——只描述事实，不打情绪标签，
            # classify() 会把它归为日常类，平静时不影响排序。
            try:
                import profile_hooks as PH
                dir_ = (self.entry.get() or "").strip()
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

    def reload(self):
        pass