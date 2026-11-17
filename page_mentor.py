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


class MentorPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.rows = []
        self.ctx = {}
        self._all = []
        self._build()
        self.after(120, self._load_index)

    def _build(self):
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        self._hint = U.Hint(top, MENTOR_HELP, summary="数据来源与限制", bg=T.BG)
        self._hint.pack(side="left", fill="x", expand=True)
        self.coverage = tk.Label(top, text="索引加载中…", bg=T.BG, fg=T.TXT3,
                                 font=T.T_BODY_SM())
        self.coverage.pack(side="right")

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=T.PAD, pady=(2, 6))
        tk.Label(bar, text="研究内容", bg=T.BG, fg=T.TXT3, font=T.F(9)).pack(side="left", padx=(0, 8))
        self.entry = tk.Entry(bar, bg=T.CARD, fg=T.TXT, insertbackground=T.ACCENT,
                              relief="flat", highlightbackground=T.LINE,
                              highlightthickness=1, font=T.F(10))
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", lambda e: self.search())
        try:
            import app_suggest
            app_suggest.attach(self.entry)
        except Exception as exc:
            print("联想词挂载失败:", exc)
        tk.Label(bar, text="地区", bg=T.BG, fg=T.TXT3, font=T.F(9)).pack(side="left", padx=(10, 6))
        self.province = tk.StringVar(value="全部")
        self.pm = tk.OptionMenu(bar, self.province, "全部")
        self.pm.config(bg=T.CARD, fg=T.TXT, activebackground=T.ACCENT_D, activeforeground=T.ACCENT,
                       relief="flat", bd=0, highlightthickness=0,
                       font=T.T_BODY_SM(), width=6)
        self.pm["menu"].config(bg=T.CARD, fg=T.TXT, activebackground=T.ACCENT_D,
                               activeforeground=T.ACCENT, bd=0,
                               font=T.T_BODY_SM())
        self.pm.pack(side="left", padx=(0, 10))
        self.btn = T.Btn(bar, "匹配导师", self.search, "primary")
        self.btn.pack(side="left")

        # 默认不写任何提示：识别结果出来前这一行是空的，占位交给下方空态卡。
        # 原来这里有一句「输入研究内容后回车，系统会自动识别……」，与空态卡
        # 的第二行重复，且长期占着一行高度（搜完也还在）。
        self.ctx_lbl = tk.Label(self, text="", bg=T.BG, fg=T.TXT3,
                                font=T.T_BODY_SM(), anchor="w")
        self.ctx_lbl.pack(fill="x", padx=T.PAD + 8, pady=(0, 2))
        # 覆盖进度：如实告诉用户索引走到哪一步了，避免把「没查到」误当成「没有人」
        self.progress_lbl = tk.Label(self, text="", bg=T.BG, fg=T.TXT3,
                                     font=T.T_CAPTION(), anchor="w")
        self.progress_lbl.pack(fill="x", padx=T.PAD + 8, pady=(0, 8))

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        self.body = body

        # 图表条：结果出来之前是一句解释，不占版面。
        # 结果出来后就地替换成「真实覆盖 / 匹配度分布 / 院校分布」三张卡。
        self.vis = tk.Frame(body, bg=T.BG)
        self.vis.pack(fill="x")
        self._clear_vis()

        # 外层卡片：有空态时整张卡片收起（否则 fill="both", expand=True 会把
        # 空态卡顶到屏幕最底部，上空着一大块黑），有结果时再铺满。
        self.card = T.Card(body, pad=10)
        self.scroll = T.ScrollArea(self.card.body, bg=T.CARD)
        self.scroll.pack(fill="both", expand=True)
        self._empty("示例：单目深度估计 / 红外小目标检测 / 联邦学习隐私保护 / 蛋白质结构预测")

    def _vis_placeholder(self):
        self._clear_vis()

    def _clear_vis(self):
        for w in self.vis.winfo_children():
            w.destroy()

    # ------------------------------------------------------------ 图表
    def _render_vis(self):
        """一行文字说明「覆盖 / 匹配度 / 院校」，不铺成三栏。

        「本方向真实人数」「本批命中」这两个数，看一次就够了，常驻要占掉
        搜索框下面整整三行；改成一行折叠，点开才铺成三栏。
        """
        self._clear_vis()
        rows = self.rows or []
        if not rows:
            self._vis_placeholder()
            return

        n = len(rows)
        cat = (self.ctx or {}).get("cat") or ""
        field = (self.ctx or {}).get("field") or ""
        scores = [int(r.get("score") or 0) for r in rows]
        top = max(scores) if scores else 0

        try:
            real, real_all = advisor_index.field_count(field) if field else (0, 0)
        except Exception:
            real, real_all = 0, 0

        # 判断「这 60 条里有多少是真做这个方向的」：
        # 完全没有方向标签的行，就是大类兜底进来的。
        truly = 0
        for r in rows:
            adv = r.get("advisor") or {}
            fs = adv.get("fields") or []
            if field and (field in fs or any(field in f or f in field for f in fs)):
                truly += 1

        avg = sum(scores) / float(n) if n else 0
        med = sorted(scores)[n // 2] if scores else 0
        if field:
            cov_hint = ("本方向画像完整的学者共 %d 位；含未补全在内的全部 %d 位。"
                        % (real, real_all))
        else:
            cov_hint = "未能识别到具体方向，按通用关键词匹配，不统计覆盖。"

        # 一行摘要：本批命中 · 匹配度中位 · 院校数；点开才铺三栏。
        low = sum(1 for sc in scores if sc < 30)
        cnt = {}
        for r in rows:
            adv = r.get("advisor") or {}
            inst = adv.get("institution") or "未知"
            cnt[inst] = cnt.get(inst, 0) + 1
        fold = U.FoldMetrics(
            self.vis,
            [("本批命中", "%d 位" % n,
              "其中 %d 位带该方向标签，%d 位来自大类兜底。" % (truly, max(0, n - truly))),
             ("匹配度中位", "%d 分" % med,
              "最高 %d 分 · 平均 %.1f 分。低于 30 分基本只代表「学科大类相同」。"
              % (top, avg)),
             ("院校", "%d 所" % len(cnt),
              "最多的一所 %d 位。" % (max(cnt.values()) if cnt else 0)),
             ("本方向真实人数", ("%d" % real) if field else "—", cov_hint)],
            bg=T.BG, cols=4)
        fold.pack(fill="x")
        self._fold = fold

        # 下面这一段是「锦上添花」的说明文字：任何一处出错都不该让整页
        # 报错（0.9 秒内连切两页 + 大字号时抢过几何）。包一层兜底。
        try:
            self._render_vis_lines(rows, scores, cnt, low, field, real, n, top, avg)
        except Exception as exc:
            print("[mentor] 统计文字渲染失败：%r" % (exc,))
        try:
            self.scroll.refresh()
        except Exception:
            pass

    def _render_vis_lines(self, rows, scores, cnt, low, field, real, n, top, avg):
        if scores:
            tk.Label(self.vis,
                     text="匹配度分布：低于 30 分 %d 位（%.0f%%），30–69 分 %d 位，"
                          "70 分及以上 %d 位。低于 30 分基本只代表「学科大类相同」。"
                          % (low, 100.0 * low / len(scores),
                             sum(1 for sc in scores if 30 <= sc < 70),
                             sum(1 for sc in scores if sc >= 70)),
                     bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                     justify="left").pack(fill="x", pady=(6, 0))

        # 院校分布：只列前 6 所 + 一句集中度结论（同校扎堆时条形图所有条等长，读不出东西）
        ranked = sorted(cnt.items(), key=lambda kv: -kv[1])[:6]
        if cnt:
            names = []
            for inst, k in ranked:
                try:
                    zh = kb.institution_zh(inst) or inst
                except Exception:
                    zh = inst
                names.append("%s %d" % (zh, k))
            n_inst = len(cnt)
            top_k = ranked[0][1] if ranked else 0
            conc = "共来自 %d 所院校，最多的一所 %d 位。" % (n_inst, top_k)
            if n_inst >= n * 0.7:
                conc += "各校基本一人一位，说明这个方向是分散的，不是某校垄断。"
            else:
                conc += "头部分布较集中，注意别只盯着排名前几的学校。"
            tk.Label(self.vis, text="院校分布：" + " · ".join(names) + "。" + conc,
                     bg=T.BG, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                     justify="left").pack(fill="x", pady=(2, 0))

    def _empty(self, text):
        """空态：一张随内容收缩的引导卡，不再是「一整屏空框里飘一行灰字」。

        2026-11 第 7 版：原来空态把「示例：单目深度估计 / …」写进全高滚动区，
        截图里就是一整屏黑框顶上一行小字 —— 空态本身不该占满一屏。
        """
        self.scroll.clear()
        self.scroll.pack_forget()
        if self.card.winfo_ismapped():
            self.card.pack_forget()
        card = getattr(self, "_empty_card", None)
        if card is None:
            self._empty_card = card = T.Card(self.body, pad=14, fill_y=False)
            box = tk.Frame(card.body, bg=T.CARD)
            box.pack(fill="x")
            tk.Label(box, text="输入一个研究方向，看看谁在做", bg=T.CARD, fg=T.TXT,
                     font=T.T_BODY(), anchor="w").pack(fill="x", pady=(0, 4))
            tk.Label(box, text="点下面任意一个试试，或者在上面的输入框里写你自己的方向。",
                     bg=T.CARD, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                     justify="left", wraplength=T.sp(560)).pack(fill="x", pady=(0, 8))
            # 示例按钮：超大字下 4 个一行放不下 → 折行容器
            chips = U.WrapRow(box, bg=T.CARD)
            chips.pack(fill="x")
            for ex in ("单目深度估计", "红外小目标检测", "联邦学习隐私保护",
                       "蛋白质结构预测"):
                chips.add(T.Btn(chips, ex, lambda t=ex: self._try_example(t)))
        if not card.winfo_ismapped():
            card.pack(fill="x", pady=(8, 0))
        try:
            card.sync_now()
        except Exception:
            pass

    def _show_list(self):
        """有结果时切回「卡片 + 滚动区」的全高布局。"""
        card = getattr(self, "_empty_card", None)
        if card is not None and card.winfo_ismapped():
            card.pack_forget()
        if not self.scroll.winfo_ismapped():
            self.card.pack(fill="both", expand=True, pady=(8, 0))
            self.scroll.pack(fill="both", expand=True)

    def _try_example(self, text):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.search()

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
                if z not in seen:
                    seen.add(z)
                    zh.append(z)
            st = advisor_index.stats()
            self.app.post(lambda: self._fill(adv, zh, st))
        threading.Thread(target=work, daemon=True).start()

    def _fill(self, adv, provs, st=None):
        self._all = adv
        menu = self.pm["menu"]
        menu.delete(0, "end")
        for p in ["全部"] + provs:
            menu.add_command(label=p, command=lambda v=p: self.province.set(v))
        st = st or {}
        total_inst = st.get("institutions", 0)
        complete = st.get("complete_advisors", 0)
        txt = "可推荐学者 %d 位 · %d 所院校 · %d 个地区" % (
            complete or st.get("advisors", len(adv)), total_inst, len(provs))
        self.coverage.config(text=txt)
        covered = st.get("covered_institutions", 0)
        catalog = st.get("catalog_institutions", 0)
        # 只在**索引没跑完**时说话。「只推荐画像完整的学者」这一口径已经由
        # 右上角的「可推荐学者 N 位」和页面说明（?）承担，覆盖满 100% 时
        # 这行长期挂着一句重复的话，只是噪音。
        if catalog and covered < catalog:
            self.progress_lbl.config(
                text="索引仍在扩充：已覆盖 %d / %d 所院校，未覆盖的院校里可能还有人。"
                     % (covered, catalog),
                fg=T.WARN)
        else:
            self.progress_lbl.config(text="")

    # ------------------------------------------------------------ 检索
    def search(self, preset=None):
        text = (preset or self.entry.get()).strip()
        if not text:
            self.app.toast("请输入研究内容", T.WARN)
            return
        if preset:
            self.entry.delete(0, "end")
            self.entry.insert(0, preset)
        self.btn.config(text="匹配中…")
        prov = self.province.get()

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
                # 查人名不算（那不是研究方向），所以只放在方向匹配这条路径里。
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
                    "system", "learning", "neural", "image")
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
        import threading
        threading.Thread(target=work, daemon=True).start()

    def _apply_name(self, text, hits, prov):
        self.btn.config(text="匹配导师")
        # 精确同名优先，其次引用量高的
        hits.sort(key=lambda h: (-h["score"], -(h.get("cited") or 0)))
        self.rows = hits
        self.ctx = dict(text=text, cat="", field="")
        if hits:
            self.ctx_lbl.config(
                text="按姓名查找「%s」：命中 %d 位 · 地区 %s" % (text, len(hits), prov),
                fg=T.OK)
        else:
            self.ctx_lbl.config(text="按姓名查找「%s」：未找到" % text, fg=T.WARN)
        self._render()

    def _fail(self, exc):
        self.btn.config(text="匹配导师")
        self.app.toast("匹配失败：" + str(exc), T.ERR)

    def _apply(self, text, cat, field, conf, rows, prov):
        self.btn.config(text="匹配导师")
        self.rows = rows or []
        self.ctx = dict(text=text, cat=cat, field=field)
        head = ("%s   →   %s / %s · 置信度 %d%%" % (text, cat, field, conf)) if (cat and field) \
            else ("%s   →   未识别学科目录，按通用关键词匹配" % text)
        self.ctx_lbl.config(text=head + "   ·   地区 %s   ·   命中 %d 位" % (prov, len(self.rows)),
                            fg=T.OK if (cat and field) else T.WARN)
        self._render()

    def set_context(self, cat, field):
        """由「方向图谱」跳转进来时预填方向。"""
        self.entry.delete(0, "end")
        self.entry.insert(0, field)
        # 用命名方法而不是 lambda：窗口在 60ms 内被销毁时，
        # Tk 会报 invalid command name "…<lambda>"（截图脚本踩过）。
        self.after(60, self._search_now)

    def _search_now(self):
        try:
            if self.winfo_exists():
                self.search()
        except Exception:
            pass

    def _render(self):
        self.scroll.clear()
        self._render_vis()
        if not self.rows:
            self._empty("没有命中。换一个更常见的方向描述，或在「方向图谱」里选定领域后点「推荐导师」。")
            return
        self._show_list()
        bar = tk.Frame(self.scroll.inner, bg=T.CARD)
        bar.pack(fill="x", padx=2, pady=(2, 6))
        # 表头就是一行淡色小字（参考图的列头：数字右对齐、说明靠左），
        # 不再用粗体当区块标题。
        tk.Label(bar, text="匹配结果（按匹配度排序，点击打开主页）", bg=T.CARD, fg=T.TXT3,
                 font=T.T_CAPTION()).pack(side="left")
        T.Btn(bar, "复制清单", self._copy_list).pack(side="right", padx=(0, 6))
        T.Btn(bar, "导出 Excel/CSV", self.export_csv, "primary").pack(side="right", padx=(0, 6))
        for a in self.rows:
            self._row(a)
        self._after_build()

    def _after_build(self):
        """内容重建后重新量一次高度，否则 Canvas 会停在高度变化前的尺寸。"""
        self.update_idletasks()
        self.scroll._on_inner()
        self.after(30, self.scroll._on_inner)

    def _row(self, a):
        adv = a.get("advisor", {})
        inst = adv.get("institution", "")
        zh = kb.institution_zh(inst) or ""
        prov = kb.province_zh(adv.get("province", "")) or ""
        score = a.get("score", 0)
        bg = T.CARD_HI
        f = tk.Frame(self.scroll.inner, bg=bg, cursor="hand2")
        f.pack(fill="x", pady=2)
        top = tk.Frame(f, bg=bg)
        top.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(top, text=adv.get("name", "—"), bg=bg, fg=T.TXT,
                 font=T.F(10, True)).pack(side="left")
        col = T.OK if score >= 70 else (T.WARN if score >= 50 else T.TXT3)
        tk.Label(top, text="  %d 分" % score, bg=bg, fg=col,
                 font=T.M(8, True)).pack(side="left")
        # 学术影响力：引用量是排序的次要依据，也让用户判断「这个人是不是主力研究者」
        cited = a.get("cited") or adv.get("cited_by_count") or 0
        if cited:
            tk.Label(top, text="  引用 " + _fmt_cited(cited), bg=bg, fg=T.TXT4,
                     font=T.M(8)).pack(side="left")
        if prov:
            tk.Label(top, text=prov, bg=bg, fg=T.TXT4, font=T.F(8)).pack(side="right", padx=(0, 6))
        # 中英文名一起显示：中文名便于快速识别，英文名便于官网检索核验。
        # 没有中文名时只显示英文，不再重复拼一遍。
        zh_inst = zh if (zh and zh != inst) else ""
        if zh_inst:
            shown = "%s（%s）" % (zh_inst, inst)
        else:
            shown = inst
        line2 = "  ·  ".join(x for x in (shown, adv.get("lab", "")) if x)
        tk.Label(f, text=line2, bg=bg, fg=T.TXT2, font=T.F(9), anchor="w",
                 justify="left", wraplength=760).pack(fill="x", padx=10)
        fields = adv.get("fields") or []
        kw = adv.get("keywords") or []
        meta = "  ".join([("[" + x + "]") for x in fields[:4]] + list(kw[:3]))
        if meta:
            tk.Label(f, text=meta, bg=bg, fg=T.TXT4, font=T.F(8), anchor="w",
                     wraplength=T.wrap(760), justify="left").pack(fill="x", padx=10)
        # 匹配依据：让用户能判断「为什么推荐他」，而不是只给一个分数
        if a.get("reasons"):
            reason_txt = "匹配依据：" + "、".join(a["reasons"])[:80]
            color = T.WARN if any("关联弱" in r for r in a["reasons"]) else T.ACCENT
            tk.Label(f, text=reason_txt, bg=bg, fg=color,
                     font=T.F(8), anchor="w").pack(fill="x", padx=10, pady=(2, 8))
        else:
            tk.Frame(f, bg=bg, height=6).pack(fill="x")
        # 点击行为：优先打开可核验的**唯一身份**页面，而不是搜索引擎。
        #   ORCID 记录 → 该学者的权威作品列表（53% 的学者有）
        #   个人主页 → 其次
        #   都没有 → 用院校 + 姓名做检索（兜底，准确性最低）
        orcid = (adv.get("orcid") or "").strip()
        homepage = (adv.get("url") or adv.get("homepage") or "").strip()
        if orcid:
            target = orcid if orcid.startswith("http") else "https://orcid.org/" + orcid
            f.bind("<Button-1>", lambda e, u=target: self.app.open_url(u))
            self._tip(f, "点击打开 ORCID 作品记录")
        elif homepage:
            f.bind("<Button-1>", lambda e, u=homepage: self.app.open_url(u))
            self._tip(f, "点击打开个人主页")
        else:
            f.bind("<Button-1>", lambda e, q=(zh or inst): self.app.open_url(
                "https://www.bing.com/search?q=" + kb.quote_plus(q + " " + adv.get("name", ""))))
            self._tip(f, "无 ORCID/主页，点击按院校+姓名检索")

    def _tip(self, widget, text):
        """轻量提示：鼠标停留时在状态栏显示，不弹窗打扰。"""
        widget.bind("<Enter>", lambda e: self.app.toast(text, T.TXT3))

    def _copy_list(self):
        lines = []
        for a in self.rows:
            adv = a.get("advisor", {})
            inst = adv.get("institution", "")
            lines.append("%s · %s（%s）· %s 分 / %s" % (
                adv.get("name", ""), kb.institution_zh(inst) or inst, inst,
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
                "院校": kb.institution_zh(inst) or "",
                "英文校名": inst,
                "省份": kb.province_zh(adv.get("province", "")) or "",
                "研究方向": "、".join((adv.get("fields") or [])[:5]),
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