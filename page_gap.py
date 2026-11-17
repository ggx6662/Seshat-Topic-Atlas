#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文献空白页：从你手上的论文里找「还没人做」的组合。

原来的创新点是「基础方向 + 策略词」拼出来的模板，
18 个候选的理由和验证问题完全一样。这一页换了逻辑：

  依据你自己知识库里的 343 篇论文，统计
    · 哪些方法 × 任务已经被做烂（有 20 篇以上）
    · 哪些组合在库里从没出现过，但两边都活跃 → 潜在空白
  每条结论都标出依据的文献数量，不编造。

空白不等于创新——它也可能是「本来就不该做」。页面明确提示需要人工判断。
"""
import re
import threading
import tkinter as tk


import app_theme as T
from ui_parts import WrapRow   # 会自动折行的按钮排
import kb_widget as kb
import profile_memory as PM
import research_gap as G
import topic_constraint
import ui_parts as U
_card_head = T.card_head

PAGE_HINT = "从本地 343 篇论文里找还没人做的组合"

# 展开后的完整说明。写成「怎么读」而不是「功能列表」——
# 用户真正会犯的错是把「本地库里没有」当成「学界没人做」。
GAP_HELP = (
    "这一页回答一个问题：在你收藏的这批论文里，哪些「方法 × 任务」和「模态 × 失效场景」"
    "的组合还是空的。\n\n"
    "怎么读：\n"
    "  1. 左边「左栏顶部」是按方法归并的密度，一行一个方法，后面跟着它最常配的任务和篇数。"
    "数字大 = 这条路已经被做透，不要从这儿开始。\n"
    "  2. 右边「问题维度空白」通常比方法组合更值得做，因为它对应真实的失败现场"
    "（比如医学场景下的小目标、低照度下的遮挡）。\n"
    "  3. 每条空白都会再拿去 arXiv 全库 53.8 万篇核实一次，结果标成"
    "「真空白 / 稀疏 / 拥挤」三档。没核到的条目会写「还没轮到」，那不是结论。\n"
    "  4. 底部「你做不做得动」会拿你在个人画像里填的算力、期限去套这条空白；"
    "没填就不显示，不会瞎猜。\n\n"
    "**重要限制**：本地 343 篇是「你收藏了什么」，不是学界现状。"
    "所以每条结论都要配合右侧的全库数字一起看，单独看「本地 0 篇」会严重误判。"
    "空白也不等于创新 —— 有些组合本来就是不该做的。"
)


def _cn_num(n):
    """8000 写 8,000，让「全库 603 篇」一眼读得出来，不用数位数。"""
    try:
        return "{:,}".format(int(n))
    except Exception:
        return str(n)


def _gap_wrap(owner, pad=30):
    """条目文字的换行宽度 = 它所在容器（row）的实际宽度 − pad。

    原来这里写死 `T.wrap(430)`：设计稿 430px × 字号倍率。字号调到「超特大」
    时算出 645px，而卡片在窄窗口里可能只有 500px —— 每条结论的尾巴都被
    卡片边缘齐齐切掉（2026-11 截图：「库里从没同时出现过的组合；空白不」）。
    容器还没布局（宽度=1）时退回 T.wrap()，至少不会算出 80px 的窄条。
    """
    try:
        w = owner.winfo_width()
    except Exception:
        w = 0
    if w > 200:
        return max(160, w - pad)
    return T.wrap(430)


def _tag(head, c):
    """右侧「全库 603 篇」色块。三档配色和结论一一对应，扫一眼就知道该不该做。"""
    fg, bg = {"真空白": ("#0B2410", T.OK),
              "稀疏": ("#2A1F00", T.WARN),
              "拥挤": ("#2A0A0A", T.ERR)}.get(c["level"], (T.TXT3, T.BG))
    tk.Label(head, text="全库 %s 篇" % _cn_num(c["count"]), bg=bg, fg=fg,
             font=T.M(8, True)).pack(side="right", padx=(6, 8))


def _modal_line(row, c):
    """「该场景在全库有 4451 篇」—— 先证明这个场景真有人做，再说它缺某类研究。

    没有这一行，用户无法判断「医学下的小目标没人做」是因为真机会，
    还是因为我们本地库太小。数字放在最前面，是为了让它先于结论被看见。
    """
    n = c.get("modal_count")
    if not n:
        return
    tk.Label(row, text="该场景在全库 %s 篇文献里是活跃赛道 —— 空白是场景内的细分缺口，"
                       "不是场景本身没人做" % _cn_num(n),
             bg=T.CARD_HI, fg=T.TXT4, font=T.F(8), anchor="w", justify="left",
             wraplength=_gap_wrap(row, 30)).pack(fill="x", padx=10, pady=(0, 2))


def _check_line(row, c):
    """条目下方的核实结论。拥挤时不写红字警告，只降成灰 —— 红字满屏反而没人看。"""
    color = {"真空白": T.OK, "稀疏": T.WARN, "拥挤": T.TXT4}.get(c["level"], T.TXT3)
    tk.Label(row, text="全库核实 · %s · %s" % (c["level"], c["note"]),
             bg=T.CARD_HI, fg=color, font=T.F(8), anchor="w", justify="left",
             wraplength=_gap_wrap(row, 30)).pack(fill="x", padx=10, pady=(0, 7))


def _fit_line(row, cons, angle_key, title, check=None):
    """「你做不做得动」——把硬条件套到这条空白上。

    空白页和选题工坊的区别：工坊里的候选自带 angle_key / kind，
    空白页只有「方法 × 任务」或「模态 × 问题」这种原始条目。
    所以这里先把空白映射成一个最小候选（title + 猜出来的角度），
    再交给 `topic_constraint.check` —— 复用同一套判据，
    不要在这一页另写一份「算力够不够」的逻辑，两套口径必然打架。

    没有填硬条件时返回 None（不占版面）。

    `check` 是这条空白的全库核实结论（可不给）。给了并且是「稀疏/真空白」时，
    把 block 降成 warn —— 道理是：一片基本没人的地，起步阶段不需要按
    「这个问题做透要多少钱」来估，先做一个最小验证就能判断值不值得继续。
    把小样本、三维这类角度一律判死，等于替用户放弃一个真实存在的机会。
    """
    if not cons or not any(cons.get(k) for k in ("compute", "months", "style")):
        return None
    probe = {"title": title or "", "angle_key": angle_key or ""}
    try:
        r = topic_constraint.check(probe, cons)
    except Exception:
        return None
    if r.get("level") == "ok" or not r.get("reasons"):
        return None
    lvl = "block" if r["level"] == "block" else "warn"
    open_field = bool(check) and check.get("level") in ("真空白", "稀疏")
    if lvl == "block" and open_field:
        lvl = "warn"
        head = "按你填的条件：做全套吃力，可以先做最小验证"
    else:
        head = "按你填的条件：这条做不完" if lvl == "block" else "按你填的条件：要挑做法"
    col = T.ERR if lvl == "block" else T.WARN
    # 窄栏里「你填的是「无算力」」会被断成「「无 / 算力」」—— Tk 只在空格和汉字边界换行，
    # 引号里的词一旦跨行，读者会以为填错了。
    # 踩坑：U+00A0 在 Tk 的中文换行规则里同样算可断点，不顶用；
    # 中文本来就不需要空格，直接把引号内的空格去掉最稳。
    detail = r["reasons"][0][1]
    if "：" in detail:
        # 「这条至少需要「单卡消费级」档算力，你填的是「无算力」：剪枝/蒸馏本身便宜…」
        # 冒号后面是一整句解释，在 430px 的栏里必然折成两行 —— 只留前半句。
        detail = detail.split("：", 1)[0]
    # 前半句里的「你填的是「无算力」」与上面的 head 重复（head 已经说了「按你填的条件」），
    # 压成「要 X 档算力，你填的是 Y」，一句话读完
    m = re.search(r"至少需要「([^」]*)」档算力，你填的是「([^」]*)」", detail)
    if m:
        detail = "要「%s」档算力，你填的是「%s」" % (m.group(1), m.group(2))
    detail = re.sub(r"「([^」]*)」",
                    lambda mm: "「" + mm.group(1).replace(" ", "") + "」", detail)
    tk.Label(row, text="%s —— %s" % (head, detail),
             bg=T.CARD_HI, fg=col, font=T.F(8), anchor="w", justify="left",
             wraplength=_gap_wrap(row, 30)).pack(fill="x", padx=10, pady=(0, 6))


# 空白条目的「角度」怎么猜：方法/问题名里出现这些词就映射到角度 key。
# 不做就不给结论 —— 猜错比不给更糟，用户会照着错结论准备资源。
_GAP_ANGLE_HINT = (
    ("小样本", "小样本"), ("少样本", "小样本"), ("few-shot", "小样本"),
    ("零样本", "开放词汇"), ("开放词汇", "开放词汇"), ("open-vocab", "开放词汇"),
    ("跨域", "跨域泛化"), ("域适应", "跨域泛化"), ("domain", "跨域泛化"),
    ("轻量", "轻量化"), ("蒸馏", "轻量化"), ("剪枝", "轻量化"),
    ("自监督", "自监督"), ("对比学习", "自监督"), ("无监督", "自监督"),
    ("扩散", "扩散"), ("diffusion", "扩散"),
    ("多模态", "多模态"), ("跨模态", "多模态"),
    ("三维", "三维"), ("3d", "三维"), ("点云", "三维"),
    ("事件相机", "事件相机"), ("跟踪", "跟踪"), ("视频", "视频"),
    ("分割", "分割"), ("可解释", "可解释"), ("鲁棒", "鲁棒"),
    ("对抗", "鲁棒"), ("评测", "评测"), ("基准", "评测"),
    ("多尺度", "多尺度"),
)


def _guess_angle(*parts):
    """从空白条目的文字里猜一个角度 key；猜不出返回空串。"""
    blob = " ".join([str(p or "") for p in parts]).lower()
    for key, angle in _GAP_ANGLE_HINT:
        if key.lower() in blob:
            return angle
    return ""


class GapPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.data = None
        self._has_issue = False
        # 硬条件（算力/周期/风格/禁忌）只在渲染时读一次，
        # 不在每条空白里重复读盘 —— 一页几十条，读几十次没必要
        try:
            self._cons = PM.constraints()
        except Exception:
            self._cons = {}
        self._build()
        self.after(120, lambda: self.analyze(None))

    def _build(self):
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=T.PAD, pady=(4, 8))
        # 说明文字默认收成一行，点 ? 才展开 —— 这一页的第一屏应该留给结论
        self._hint = U.Hint(top, GAP_HELP, summary="怎么读这一页", bg=T.BG)
        self._hint.pack(side="left", fill="x", expand=True)

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=T.PAD, pady=(0, 6))
        # 「重新分析」放这一行最右：它和输入框是一组动作，而页头那行
        # 只剩说明文字，字号一大按钮就会把说明挤成一条缝。
        T.Btn(bar, "重新分析", lambda: self.analyze(self._current_kw()),
              "primary").pack(side="right", padx=(8, 0))
        tk.Label(bar, text="聚焦方向", bg=T.BG, fg=T.TXT3,
                 font=T.F(9)).pack(side="left", padx=(0, 8))
        self.entry = tk.Entry(bar, bg=T.CARD, fg=T.TXT, insertbackground=T.ACCENT,
                              relief="flat", highlightbackground=T.LINE,
                              highlightthickness=1, font=T.F(10))
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", lambda e: self.analyze(self._current_kw()))
        try:
            import app_suggest
            app_suggest.attach(self.entry, on_commit=lambda t: self.analyze(t))
        except Exception as exc:
            print("联想词挂载失败:", exc)
        # 快捷词 + 全库：字号放大后放不下要能折行，否则「全库」被剪掉
        # 快捷词单独占一行（原来挤在输入框右边，字号一大就折成瀑布）
        self._quick_row = U.WrapRow(self, bg=T.BG)
        self._quick_row.pack(fill="x", padx=T.PAD, pady=(0, 6))
        for t in ("红外", "Mamba", "融合", "小目标", "医学"):
            self._quick_row.add(
                T.Btn(self._quick_row, t, lambda x=t: self._quick(x)))
        self._quick_row.add(
            T.Btn(self._quick_row, "全库", lambda: self._quick("")))

        # wraplength 不能用 T.wrap(固定像素)：1.5 倍字号下它算成 1543px，
        # 比窗口还宽，整页被顶出可视区（实测 reqw 1583 vs 可用 1078）。
        # 改成跟随父容器宽度。
        self.summary = tk.Label(self, text="正在分析本地文献…", bg=T.BG, fg=T.TXT3,
                                font=T.F(9), anchor="w", justify="left")
        self.summary.pack(fill="x", padx=T.PAD + 4, pady=(0, 8))
        T.fill_wrap(self.summary, pad=60)
        # 全库核实的进度条独占一行：塞进 summary 那行会被挤掉半句
        self.check_note = tk.Label(self, text="", bg=T.BG, fg=T.WARN,
                                   font=T.F(8), anchor="w", justify="left",
                                   wraplength=T.wrap(900))

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD, pady=(0, 14))
        # 第 10 版：两栏不再强制等高撑满。原来 grid_rowconfigure(0, weight=1)
        # + sticky="nsew" 让两块卡片一路顶到窗口底，内容少的右栏下方留一大片空；
        # 现在卡片高度随内容，滚动区给一个可视下限。
        # uniform="c" 会强制两栏等宽，宽的那栏把整页请求宽度顶上去；
        # 去掉 uniform 按内容分：左边组合多、右边空白短。
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)

        # 左：已密集
        left = T.Card(body, pad=12, fill_y=False)
        left.grid(row=0, column=0, sticky="new", padx=(0, 10))
        _card_head(left.body, "已经做得很密", "这些组合文献很多，再做需要明确的差异化理由")
# 方法 × 任务密度：用文字行代替热力矩阵
        # （2026-11-15 用户要求「可视化表去除」—— 7×5 的色块网格要
        #  你记住行列标签才能读，换成「方法 → 任务(n)」反而更快，
        #  而且下面的 combos 列表本来就是同一份数据）
        self.matrix = tk.Frame(left.body, bg=T.CARD)
        self.matrix.pack(fill="x", pady=(0, 8))
        self.combo_box = T.ScrollArea(left.body, bg=T.CARD, height=300)
        self.combo_box.pack(fill="both", expand=True)

        # 右：空白
        right = T.Card(body, pad=12, fill_y=False)
        right.grid(row=0, column=1, sticky="new")
        _card_head(right.body, "潜在空白", "空白不一定是机会，要看证据再判断")
        # 两个页签：方法组合 / 问题维度。原来两块塞进同一根滚动条，
        # 「问题维度空白」那组的组标题落在视口之外，读起来像方法组合的下一节。
        self._tab = ["combo"]
        self._tabs = U.WrapRow(right.body, bg=T.CARD)
        self._tabs.pack(fill="x", pady=(0, 6))
        self._tab_btns = {}
        for key, label in (("combo", "方法组合"), ("issue", "问题维度")):
            b = T.Btn(self._tabs, label, lambda k=key: self._switch_tab(k), "ghost")
            self._tabs.add(b)
            self._tab_btns[key] = b
        # 导语默认不显示，点页签旁的「?」才展开（第 16 版）
        self._hint_on = False
        _row = tk.Frame(right.body, bg=T.CARD)
        _row.pack(fill="x", pady=(0, 4))
        self._tab_hint = tk.Label(_row, text="", bg=T.CARD, fg=T.TXT3,
                                  font=T.T_CAPTION(), anchor="w", justify="left")
        self._hint_btn = T.Btn(_row, "?", self._toggle_tab_hint, "ghost")
        self._hint_btn.pack(side="right", padx=(6, 0))
        # 「?」按钮在收起时几乎看不出来是个按钮，直接在它左边放一句常驻提示，
        # 免得用户不知道这里可以点（2026-11-16 截图里它就孤零零挂在右上角）。
        self._hint_cue = tk.Label(_row, text="这一页怎么读", bg=T.CARD,
                                  fg=T.TXT4 if hasattr(T, "TXT4") else T.TXT3,
                                  font=T.T_CAPTION(), anchor="e")
        self._hint_cue.pack(side="right", padx=(0, 2))
        self.gap_box = T.ScrollArea(right.body, bg=T.CARD, height=420)
        self.gap_box.pack(fill="both", expand=True)
        self.issue_box = T.ScrollArea(right.body, bg=T.CARD, height=420)

    _TAB_TEXT = {
        "combo": "库里同时出现的「方法 × 任务」计数；没同时出现过的就算潜在空白。",
        "issue": "某类场景活跃、但某个具体失效场景几乎没人研究；这类更贴近真实失败现场。",
    }

    def _toggle_tab_hint(self):
        self._hint_on = not getattr(self, "_hint_on", False)
        try:
            if self._hint_on:
                self._tab_hint.pack(side="left", fill="x", expand=True)
                T.fill_wrap(self._tab_hint, pad=8)
                self._hint_btn.config(text="收起")
                self._hint_cue.pack_forget()
            else:
                self._tab_hint.pack_forget()
                self._hint_btn.config(text="?")
                self._hint_cue.pack(side="right", padx=(0, 2),
                                    before=self._hint_btn)
            T.resync(self._tab_hint)
        except Exception as exc:
            print("[gap] 导语开合失败：%r" % (exc,))

    def _switch_tab(self, key, force=False):
        if key == self._tab[0] and not force:
            return
        self._tab = [key]
        for k, b in self._tab_btns.items():
            b.set_kind("primary" if k == key else "ghost")
        try:
            self._tab_hint.config(text=self._TAB_TEXT.get(key, ""))
            # 切页签时若导语是收起的，保持收起（不因为切换而突然展开）
            if not getattr(self, "_hint_on", False):
                self._tab_hint.pack_forget()
                self._hint_btn.config(text="?")
                self._hint_cue.pack(side="right", padx=(0, 2),
                                    before=self._hint_btn)
        except Exception:
            pass
        if key == "issue":
            self.gap_box.pack_forget()
            self.issue_box.pack(fill="both", expand=True)
            try:
                self.issue_box.refresh()
            except Exception:
                pass
        else:
            self.issue_box.pack_forget()
            self.gap_box.pack(fill="both", expand=True)
            try:
                self.gap_box.refresh()
            except Exception:
                pass

    def _current_kw(self):
        return self.entry.get().strip()

    def _quick(self, kw):
        self.entry.delete(0, "end")
        self.entry.insert(0, kw)
        self.analyze(kw)

    def analyze(self, keyword):
        self.summary.config(text="正在分析本地文献…", fg=T.TXT3)
        self.check_note.pack_forget()

        def work():
            try:
                data = G.analyze(keyword or None)
            except Exception as exc:
                self.app.post(lambda e=exc: self.summary.config(
                    text="分析失败：" + str(e), fg=T.ERR))
                return
            # 认真分析某个方向的空白 = 这个方向对你重要，比「看了一眼」强
            try:
                import profile_hooks as PH
                if keyword:
                    PH.see_field(keyword, source="文献空白")
            except Exception:
                pass
            self.app.post(lambda: self._apply(data))
            # 全库核实要把 53.8 万篇正文读进内存（约 30 秒），先出本地结论、
            # 再补核实，用户不用干等。
            checked = G.global_check(data) or []
            if checked:
                self.app.post(lambda c=checked: self._apply_check(c))
        threading.Thread(target=work, daemon=True).start()

    def _apply_check(self, checked):
        self.check_note.pack_forget()
        if self.data is not None:
            self.data["global_check"] = checked
        self.gap_box.clear()
        self._render_issue_gaps((self.data or {}).get("issue_gaps", []),
                                self.gap_box.inner)
        self._render_gaps((self.data or {}).get("gaps", []), self.data or {})
        self.gap_box.refresh()

    def _apply(self, data):
        self.data = data
        # 每次重算都重读硬条件：用户可能刚在「个人画像」里改完再切回来，
        # 缓存住不刷新的话这一页会一直按旧条件给结论
        try:
            self._cons = PM.constraints()
        except Exception:
            self._cons = {}
        scope = data.get("scope", "")
        total = data.get("total", 0)
        self.combo_box.clear()
        self.gap_box.clear()
        try:
            self.issue_box.clear()
        except Exception:
            pass
        if not total:
            self.summary.config(text=data.get("notes", ["没有匹配文献"])[0], fg=T.WARN)
            self._render_matrix({})
            self.combo_box.refresh()
            self.gap_box.refresh()
            return
        m = data.get("methods", [])[:3]
        t = data.get("tasks", [])[:3]
        bits = ["范围「%s」共 %d 篇" % (scope, total)]
        if m:
            bits.append("主要方法：" + "、".join("%s(%d)" % (a, b) for a, b in m))
        if t:
            bits.append("主要任务：" + "、".join("%s(%d)" % (a, b) for a, b in t))
        self.summary.config(text="  ·  ".join(bits), fg=T.OK)
        self._render_matrix(data)
        self._render_combos(data.get("combos", []))
        # 两组空白各占一个页签：方法组合 / 问题维度。
        self._has_issue = bool(data.get("issue_gaps"))
        self._render_issue_gaps(data.get("issue_gaps", []), self.issue_box.inner)
        self._render_gaps(data.get("gaps", []), data)
        # 默认落在「有结论」的那一页：问题维度有内容就先给问题维度
        want = "issue" if self._has_issue else "combo"
        self._tab = [None]
        self._switch_tab(want)
        self.combo_box.refresh()
        self.gap_box.refresh()
        try:
            self.issue_box.refresh()
        except Exception:
            pass
        # 已有核实结论就别白等 —— 只有本轮没带过来的才去查
        if not data.get("global_check") and data.get("gaps"):
            self.check_note.config(
                text="正在拿 arXiv 全库核实这些空白（首次约 20 秒）…")
            self.check_note.pack(fill="x", pady=(0, 6))

    def _render_matrix(self, data):
        """方法 × 任务密度：每个方法一行，列出它在你库里最密的任务。

        原来这里是 Heatmap 色块。它的问题是要同时记住行、列标签才能读，
        而这页真正要回答的是「哪个方法配哪个任务已经被做烂了」——
        一行一句比网格直接得多。
        """
        for w in self.matrix.winfo_children():
            w.destroy()
        try:
            pair = {}
            for cb in data.get("combos") or []:
                pair[(cb["method"], cb["task"])] = cb["count"]
            if not pair:
                return
            msum = {}
            for (m, _t), n in pair.items():
                msum[m] = msum.get(m, 0) + n
            rows = [m for m, _ in sorted(msum.items(), key=lambda kv: -kv[1])][:5]
            for m in rows:
                cells = sorted(((t, n) for (mm, t), n in pair.items() if mm == m),
                               key=lambda kv: -kv[1])[:5]
                line = "%s（共 %d 篇）→ " % (m, msum[m]) + " · ".join(
                    "%s %d" % (t, n) for t, n in cells)
                lb = tk.Label(self.matrix, text=line, bg=T.CARD, fg=T.TXT3,
                              font=T.T_BODY_SM(), anchor="w", justify="left")
                lb.pack(fill="x", pady=(0, 2))
                T.fill_wrap(lb, pad=8)
        except Exception:
            pass

    def _render_issue_gaps(self, issue_gaps, box):
        """问题维度空白：某模态活跃，但某个具体失效场景几乎没人研究。

        这类空白往往比「方法组合」更值得做——它对应真实的失败现场。
        全库核实过的条目排前面，没核实的排后面；条目按 kind 对齐，
        避免把核实结果错挂到另一条空白上。
        """
        if not issue_gaps:
            return
        # 页签已经写了「问题维度」，这里不再重复打二级标题（第 16 版）。
        checks = {(c.get("modal"), c.get("issue")): c
                  for c in ((self.data or {}).get("global_check") or [])
                  if c.get("kind") == "issue"}
        # 核实过的排前面（用户最该先看的是「全库确实少」的那几条），
        # 未核实/未通过模态门槛的排后面，并明确说为什么没有结论。
        rows = []
        for g in issue_gaps:
            c = checks.get((g["modal"], g["issue"]))
            rows.append((0 if c else 1, c, g))
        rows.sort(key=lambda r: r[0])
        # 「还没轮到核实」这句话对每张未核实的卡片都是同一句，逐张重复会盖过
        # 真正有信息量的内容（场景有多少篇、为什么值得做）。所以只在第一张
        # 未核实的卡片下注一次，其余留白。
        pending_noted = False
        for _, c, g in rows:
            # 卡片内不再套色块：参考图的层级靠「底色台阶 + 极淡分隔线」，
            # 一屏十来个 CARD_HI 方块又变成了另一种「到处都是框」。
            row = tk.Frame(box, bg=T.CARD)
            row.pack(fill="x", pady=0)
            T.hsep(row, color=T.LINE_SOFT)
            head = tk.Frame(row, bg=T.CARD)
            head.pack(fill="x", padx=2, pady=(6, 0))
            # 先 pack 右侧固定列，再让左侧文本 expand —— 反了会把按钮挤出可视区
            T.Btn(head, "存为创新点", lambda e, gg=g, cc=c: self.save_issue_gap(gg, cc),
                  "ok").pack(side="right", padx=(6, 0))
            if c:
                _tag(head, c)
            # 标题独占一行并可折行：右栏只有 420px，再让按钮挤在同一行，
            # 「医学场景下的小目标问题」会被压成两行、且压住下面的说明。
            _t = tk.Label(head, text="%s 场景下的%s问题" % (g["modal"], g["issue"]),
                          bg=T.CARD, fg=T.TXT, font=T.T_BODY(), anchor="w",
                          justify="left")
            _t.pack(side="left", fill="x", expand=True)
            T.fill_wrap(_t, pad=4)
            _why = tk.Label(row, text=g["why"], bg=T.CARD, fg=T.TXT3,
                            font=T.T_BODY_SM(), anchor="w", justify="left")
            _why.pack(fill="x", padx=2, pady=(2, 4))
            T.fill_wrap(_why, pad=30)
            if c:
                _modal_line(row, c)
                _check_line(row, c)
            elif self.data and self.data.get("global_check") is not None and not pending_noted:
                pending_noted = True
                # 核实还没跑到这条时不写「量级不够」——那等于替系统下了个它没足够数据下的结论。
                # 医学场景在全库 4,451 篇里是活跃赛道，写「量级不够」会误导用户放弃。
                _pn = tk.Label(row, text="全库核实：排在后面的几条这次还没轮到（先当线索看，不是结论）",
                               bg=T.CARD, fg=T.TXT4, font=T.T_BODY_SM(), anchor="w",
                               justify="left")
                _pn.pack(fill="x", padx=2, pady=(0, 6))
                # pad 要留够 Label 自己的 padx：实测 396 宽的容器里 label 占
                # 344，pad=30 会让「（」单独掉到第二行。
                T.fill_wrap(_pn, pad=6)
            # 硬条件放最后一行：先看「有没有人做」，再问「你做不做得动」
            _fit_line(row, self._cons, _guess_angle(g["modal"], g["issue"]),
                      "%s场景下%s问题的检测方法" % (g["modal"], g["issue"]), c)

    def save_issue_gap(self, g, c=None):
        idea = {
            "title": "%s场景下%s问题的检测方法" % (g["modal"], g["issue"]),
            "desc": ("背景：%s。\n拟研究：针对该失效场景设计专门的处理思路，"
                     "重点验证它是否真的解决了这个场景，而不是整体指标略微提升。\n"
                     "需要补：该场景的评测子集、最强 baseline 在该子集上的表现、"
                     "失败判据、以及为什么通用方法在这里不够。"
                     % g["why"]),
            "type": "应用创新",
            "source": "文献空白分析",
        }
        if c:
            idea["desc"] = ("%s\n\n证据：本地库「%s」%d 篇、「%s」%d 篇，同时出现 0 篇\n"
                            "全库核实：arXiv 53.8 万篇里「%s」%s 篇（%s）"
                            % (idea["desc"], g["modal"], g.get("mn_count", 0),
                               g["issue"], g.get("issue_count", 0),
                               c.get("query") or "", _cn_num(c["count"]), c["note"]))
            idea["evidence"] = {"query": c.get("query"), "global_count": c["count"],
                                "level": c["level"], "kind": "issue"}
        mem = kb.load_research_memory()
        idea["time"] = kb.datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
        mem.setdefault("ideas", []).append(idea)
        kb.save_research_memory(mem)
        self.app.toast("已存入创新点库：" + idea["title"][:24], T.OK)
        self.app.mark_dirty("ideas")

    def _render_combos(self, combos):
        self.combo_box.clear()
        if not combos:
            tk.Label(self.combo_box.inner, text="库里暂时没有重复出现的组合。",
                     bg=T.CARD, fg=T.TXT4, font=T.F(9)).pack(pady=20, padx=8)
            return
        for c in combos:
            # 行样式与右栏一致：淡分隔线 + 文字，数量用「篇」小字贴右，
            # 不用整块亮黄底 —— 一列十来块黄底比数据本身还显眼。
            row = tk.Frame(self.combo_box.inner, bg=T.CARD)
            row.pack(fill="x", pady=0)
            T.hsep(row, color=T.LINE_SOFT)
            head = tk.Frame(row, bg=T.CARD)
            head.pack(fill="x", padx=2, pady=(6, 0))
            tk.Label(head, text="%d 篇" % c["count"], bg=T.CARD, fg=T.WARN,
                     font=T.T_BODY_SM()).pack(side="right")
            tk.Label(head, text="%s × %s" % (c["method"], c["task"]), bg=T.CARD,
                     fg=T.TXT, font=T.T_BODY()).pack(side="left")
            if c.get("examples"):
                tk.Label(row, text="例：" + "；".join(e[:38] for e in c["examples"]),
                         bg=T.CARD, fg=T.TXT4, font=T.T_BODY_SM(), anchor="w",
                         justify="left", wraplength=_gap_wrap(row, 30)).pack(fill="x", padx=2,
                                                              pady=(2, 6))

    def _render_gaps(self, gaps, data):
        box = self.gap_box.inner
        # 与问题维度那边共用「还没轮到核实」只提示一次的口径
        pending_noted = False
        notes = data.get("notes") or []
        for n in notes:
            # 硬编码深黄底在浅色主题下变成一块脏黄，改用 tint 跟随主题
            _warn_bg = T.tint(T.WARN, 0.14, T.CARD)
            warn = tk.Frame(box, bg=_warn_bg)
            warn.pack(fill="x", pady=(0, 6))
            _wl = tk.Label(warn, text="⚠ " + n, bg=_warn_bg, fg=T.WARN,
                           font=T.T_BODY_SM(), anchor="w", justify="left")
            _wl.pack(fill="x", padx=10, pady=5)
            T.fill_wrap(_wl, pad=22)
        if not gaps:
            tk.Label(box, text="在当前范围里没有发现明显空白。"
                               "可以换一个更具体的方向词，或先补充文献。",
                     bg=T.CARD, fg=T.TXT3, font=T.T_BODY_SM(), justify="left",
                     anchor="w").pack(pady=20, padx=8, fill="x")
            return
        if self._has_issue:
            tk.Label(box, text="库里从没同时出现过", bg=T.CARD, fg=T.TXT3,
                     font=T.T_CAPTION(), anchor="w").pack(fill="x", pady=(10, 3))
        # 本地库 343 篇 ≠ 学界现状。先给一句总则，下面的每条再挂自己的核实结论。
        # global_check 里同时有两种 kind（method/issue），这里只挑方法组合那部分，
        # 否则 issue 条目没有 method 键会 KeyError。
        checks = {("%s|%s" % (c.get("method"), c.get("task"))): c
                  for c in (data.get("global_check") or [])
                  if c.get("kind") == "method"}
        if checks:
            _tick = tk.Label(box, text="本地库 343 篇只是「你收藏了什么」，不等于学界现状；"
                                       "下面每条都把组合拿到 arXiv 全库 53.8 万篇核实过",
                             bg=T.CARD, fg=T.TXT3, font=T.T_CAPTION(),
                             anchor="w", justify="left")
            _tick.pack(fill="x", pady=(0, 4))
            T.fill_wrap(_tick, pad=26)
        for g in gaps:
            c = checks.get("%s|%s" % (g["method"], g["task"]))
            # 与「问题维度空白」用同一套行样式：淡分隔线 + 文字行，不再套灰底方块
            row = tk.Frame(box, bg=T.CARD)
            row.pack(fill="x", pady=0)
            T.hsep(row, color=T.LINE_SOFT)
            head = tk.Frame(row, bg=T.CARD)
            head.pack(fill="x", padx=2, pady=(6, 0))
            # 先 pack 右侧固定列，再让左侧文本 expand —— 反了会把按钮挤出可视区
            T.Btn(head, "存为创新点", lambda e, gg=g, cc=c: self.save_gap(gg, cc),
                  "ok").pack(side="right", padx=(6, 0))
            if c:
                _tag(head, c)
            tk.Label(head, text="%s × %s" % (g["method"], g["task"]), bg=T.CARD,
                     fg=T.TXT, font=T.T_BODY()).pack(side="left")
            _why = tk.Label(row, text=g["why"], bg=T.CARD, fg=T.TXT3,
                            font=T.T_BODY_SM(), anchor="w", justify="left")
            _why.pack(fill="x", padx=2, pady=(2, 4))
            T.fill_wrap(_why, pad=6)
            if c:
                _check_line(row, c)
            elif data.get("global_check") is not None and not pending_noted:
                # 和问题维度那边同一句道理：核实没跑到只提一次，别占满右栏。
                pending_noted = True
                _pn = tk.Label(row, text="全库核实：排在后面的几条这次还没轮到（点右上角「重新分析」会重新核一遍）",
                               bg=T.CARD, fg=T.TXT4, font=T.T_BODY_SM(), anchor="w",
                               justify="left")
                _pn.pack(fill="x", padx=2, pady=(0, 6))
                T.fill_wrap(_pn, pad=6)
            _fit_line(row, self._cons, _guess_angle(g["method"], g["task"]),
                      "%s × %s" % (g["method"], g["task"]), c)

    def _evidence_block(self, g, c):
        """把「本地库篇数」和「全库篇数」放在一起，替用户判断这个空白值不值得做。

        只报「本地 0 篇」会误导：本地库是收藏夹，不是学界现状。
        全库核实过之后才能说这条到底是不是真机会。
        """
        if c.get("kind") == "issue":
            return ("证据：本地库「%s」%d 篇、「%s」%d 篇，同时出现 0 篇\n"
                    "全库核实：arXiv 53.8 万篇里「%s」%s 篇（%s）"
                    % (g["modal"], g.get("mn_count", 0),
                       g["issue"], g.get("issue_count", 0),
                       c.get("query"), _cn_num(c["count"]), c["note"]))
        return ("证据：本地库「%s」%d 篇、「%s」%d 篇，同时出现 0 篇\n"
                "全库核实：arXiv 53.8 万篇里「%s」%s 篇（%s）"
                % (g["method"], g.get("m_count", 0),
                   g["task"], g.get("t_count", 0),
                   c.get("query") or "%s %s" % (g["method"], g["task"]),
                   _cn_num(c["count"]), c["note"]))

    def save_gap(self, gap, c=None):
        idea = G.gap_to_idea(gap)
        if c:
            # 证据行必须跟着创新点走 —— 离开这一页就没人记得「全库只有 83 篇」还是「868 篇」
            idea["desc"] = "%s\n\n%s" % (idea["desc"], self._evidence_block(gap, c))
            idea["evidence"] = {
                "query": c.get("query"), "global_count": c["count"],
                "level": c["level"], "local_method": gap.get("m_count", 0),
                "local_task": gap.get("t_count", 0),
            }
        mem = kb.load_research_memory()
        ideas = mem.setdefault("ideas", [])
        idea["time"] = kb.datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
        idea["type"] = idea.get("type") or "方法创新"
        ideas.append(idea)
        kb.save_research_memory(mem)
        self.app.toast("已存入创新点库：" + idea["title"][:24], T.OK)
        self.app.mark_dirty("ideas")