"""「默认收起，要用时再展开」的几个界面零件。

为什么要做成零件
----------------
用户的原话是要让界面更简洁、「点开什么的时候才把这些东西展示与说明」。
这件事如果每个页面各写一遍，会出现三种不一致：展开状态在切页后丢失、
有的地方展开有的直接常驻、展开后卡片不变高（`Card` 不会自己长高，
这是踩过的坑）。

所以统一成三个零件，所有页面共用同一套行为：

  Hint(parent, text)       一行弱提示，点「?」展开成完整说明
  FoldMetrics(parent, items) 指标卡默认压成一行，点开才铺成格子
  EmptyState(parent, ...)  空态：一句引导 + 一个主按钮

共同的约定
  · 默认收起，**主按钮用来做正事**，帮助文字永远不抢主按钮的位置
  · 展开/收起后调 `Card.sync_now()` + `ScrollArea.refresh()`，
    否则卡片高度停在旧值，展开的内容会被裁掉（`app_theme.Card` 的历史 bug）
  · 状态记在实例上，切页回来时由页面自己决定是否保留（默认不保留）
"""
import tkinter as tk

import app_theme as T


class LazyList(tk.Frame):
    """边滚边建的长列表。

    为什么需要它
    ------------
    文献库 345 行、期刊会议 126 行、导师 60 行，都是一次性把全部行建出来。
    每行 6 个 Label、每建一个都要往诊断列表里塞一条记录（Tk 的 `_tkinter.call`
    在 venv 下叠加了 Python 调用栈），实测期刊会议首屏 1.4 秒、文献库 0.9 秒，
    而且**全部行常驻**，页面切回来再切回去还要重建一遍。

    这里的做法：行全部由 `build(parent, index)` 生成并立刻 `pack_forget()`
    （Tk 不会给 forget 的控件算几何），只按滚动位置把可见的 ±BUFFER 行 pack 出来。
    滚过 300 行也只同时存在 ~25 个控件，滚动条位置按行数换算，不用真实高度。

    需要配合 `T.ScrollArea.use_own_scroll = True` 使用：由这里接管
    scrollbar 的 command 与 canvas 的 yscrollcommand。
    """

    SPACER = 30000          # 一根撑高条，10 万行也够
    BUFFER = 4              # 视口上下各多建几行，滚动时不会露白

    def __init__(self, scroll, count=0, build=None, row_h=None, bg=None):
        tk.Frame.__init__(self, scroll.inner, bg=bg or T.CARD)
        self.scroll = scroll
        self.count = int(count or 0)
        self.build = build
        self.row_h = int(row_h or T.sp(26))
        self.bg = bg or T.CARD
        self._slots = []        # 每行的宿主 Frame（已建好、多数处于 forget 状态）
        self._built = 0         # 已经建到第几行（从 0 连续建）
        self._order = []        # 当前 pack 出来的顺序，用于 pack(before=)
        self.token = 0          # 重建时递增，作废旧的回调
        self._job = None
        # 先占一块「一屏高」的位置，让外层 ScrollArea 的 canvas 有真实高度
        # （否则 fill() 读到 winfo_height()==1，只建 4 行，首屏一片空白）。
        self.configure(height=max(1, self.row_h * 12))
        self.pack(fill="x")
        self.after(20, self.fill)
        self._spacer = tk.Frame(self, height=self.SPACER, bg=self.bg)
        self._spacer.pack(fill="x")
        self._spacer.pack_forget()
        scroll._lazy = self
        try:
            scroll.vsb.configure(command=self._yview)
        except Exception:
            pass

    # ---------------------------------------------------------------- 对外
    def reset(self, count):
        self.token += 1
        for f in self._slots:
            try:
                f.destroy()
            except Exception:
                pass
        self._slots = []
        self._order = []
        self._built = 0
        self.count = int(count or 0)
        try:
            self._spacer.pack_forget()
        except Exception:
            pass
        return self.token

    def set_count(self, count):
        self.count = int(count or 0)
        self.fill()

    def row(self, i):
        """取第 i 行已建好的宿主 Frame（没建过返回 None）。"""
        if 0 <= i < len(self._slots):
            f = self._slots[i]
            return f if f is not None else None
        return None

    def visible_index(self, y_frac):
        """把滚动比例换算成行号（顶行）。"""
        if not self.count:
            return 0
        return max(0, min(self.count - 1, int(self.count * float(y_frac or 0.0))))

    # ---------------------------------------------------------------- 内部
    def alive(self):
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def _need(self, total):
        """建到 total 行（连续，不跳过，保证 before= 的兄弟链完整）。"""
        if not callable(self.build):
            return
        tok = self.token
        while self._built < total and self._built < self.count:
            if tok != self.token:      # 期间被 reset 了，放弃
                return
            try:
                f = self.build(self, self._built)
            except Exception as exc:
                print("[lazy] 第 %d 行建失败：%r" % (self._built, exc))
                f = None
            if f is None:
                f = tk.Frame(self, bg=self.bg, height=self.row_h)
            f.pack(fill="x")
            f.pack_forget()
            self._slots.append(f)
            self._built += 1

    def _pack_window(self, lo, hi):
        want = list(range(lo, hi))
        wantset = set(want)
        for i, f in enumerate(self._slots):
            if i in wantset or not (lo <= i < hi):
                continue
            if f.winfo_manager():
                f.pack_forget()
        prev = None
        for i in want:
            f = self._slots[i]
            if not f.winfo_manager():
                if prev is None:
                    f.pack(fill="x", before=self._first_child())
                else:
                    f.pack(fill="x", after=prev)
            prev = f

    def _first_child(self):
        for c in self.pack_slaves():
            if c is not self._spacer:
                return c
        return None

    def _yview(self, *args):
        """接手滚动条命令。

        moveto：按比例换行号，顶部那一行直接对齐到视口顶（比真实像素更准也不会抖）；
        scroll：单位滚动按行数换算。
        """
        cv = self.scroll.canvas
        if args and args[0] == "moveto":
            try:
                frac = float(args[1])
            except (TypeError, ValueError):
                return
            if self.count:
                idx = self.visible_index(frac)
                self._need(min(self.count, idx + 40))
                try:
                    cv.yview_moveto(idx * self.row_h / float(self._scrolled()))
                except Exception:
                    pass
                self.fill()
            else:
                cv.yview_moveto(frac)
            return
        if args and args[0] == "scroll":
            try:
                n = int(args[1])
            except (IndexError, TypeError, ValueError):
                n = 0
            if args[2:] and args[-1] == "pages":
                cv.yview_scroll(n * 8, "units")
            else:
                cv.yview_scroll(n * 3, "units")
            return
        cv.yview(*args)

    def _scrolled(self):
        """虚拟总高（行数 × 行高）。撑高条也按这个高度撑，两处必须同源，
        否则 moveto 按行号算出来的比例会与滚动条位置对不上。"""
        return max(1, self.count * self.row_h)

    def fill(self):
        """按当前滚动位置补建/隐藏行。滚动与尺寸变化都会调到这里，带 16ms 合并。"""
        if self._job is not None or not self.alive():
            return
        self._job = self.after(16, self._do_fill)

    def _do_fill(self):
        self._job = None
        if not self.alive():          # 外层 ScrollArea.clear() 已经把容器销毁了
            return
        try:
            cv = self.scroll.canvas
            top = float(cv.yview()[0])
            vis_h = cv.winfo_height() or 600
            if not self.count:
                return
            first = self.visible_index(top)
            n_rows = max(4, int(vis_h / float(self.row_h)) + 1)
            lo = max(0, first - self.BUFFER)
            hi = min(self.count, first + n_rows + self.BUFFER)
            self._need(hi)
            if hi < self.count:
                self._spacer.pack(fill="x")
                self._spacer.configure(height=max(1, (self.count - hi) * self.row_h))
                # 撑高条垫在最后：让 canvas 的 scrollregion 保持在「全列表那么高」
                try:
                    self._spacer.pack_configure(after=self._slots[self._built - 1])
                except Exception:
                    pass
            else:
                self._spacer.pack_forget()
            self._pack_window(lo, hi)
            cv.configure(scrollregion=(0, 0, cv.winfo_width() or 1,
                                       max(vis_h, self._scrolled())))
        except Exception as exc:
            print("[lazy] fill 失败：%r" % (exc,))


def _resync(widget):
    """展开/收起后让宿主卡片和滚动区重新量一次高度。

    `Card` 只在 body 的 Configure 变化时重算，而 pack/pack_forget 往 body 里
    加减控件**不一定**改变 body 的实际高度 → 卡片停在旧高度，新内容被裁掉。
    所以要主动 sync_now()。
    """
    w = widget
    while w is not None:
        try:
            if getattr(w, "is_card", False) and hasattr(w, "sync_now"):
                w.sync_now()
                break
        except Exception:
            pass
        w = w.master
    w = widget
    while w is not None:
        try:
            if isinstance(w, T.ScrollArea):
                w.refresh()
                break
        except Exception:
            pass
        w = w.master


class Hint(tk.Frame):
    """默认只有一行弱提示；点「?」展开成完整说明，再点收起。

    设计取舍：**不用悬停**。悬停提示在触屏和远程桌面下拿不到，
    而这里的说明往往有三四行，压在别的内容上反而更乱。
    """

    def __init__(self, parent, text, summary="", bg=None, width=None, pad=(0, 4)):
        self._bg = bg or T.BG
        super().__init__(parent, bg=self._bg)
        self._full = ""
        self._open = False
        self._wrap = width or T.wrap(760)
        self._row = tk.Frame(self, bg=self._bg)
        self._row.pack(fill="x", pady=pad)
        self._lbl = tk.Label(self._row, text=summary or "说明", bg=self._bg,
                             fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                             justify="left", wraplength=self._wrap)
        self._lbl.pack(side="left")
        self._btn = tk.Label(self._row, text="?", bg=self._bg, fg=T.TXT3,
                             font=T.T_LABEL(), cursor="hand2", padx=6)
        self._btn.pack(side="left", padx=(6, 0))
        self._btn.bind("<Button-1>", lambda e: self.toggle())
        self._detail = tk.Label(self, text="", bg=self._bg, fg=T.TXT2,
                                font=T.T_BODY_SM(), anchor="w", justify="left",
                                wraplength=self._wrap)
        if text:
            self.set(text, summary)

    def set(self, text, summary=""):
        self._full = str(text or "").strip()
        if summary:
            self._lbl.config(text=summary)
        # 没有详细说明时把「?」藏起来，不要留一个点了没反应的按钮
        if self._full:
            self._btn.pack(side="left", padx=(6, 0))
        else:
            self._btn.pack_forget()
            self._close_detail()
        if self._open and self._full:
            self._detail.config(text=self._full)

    def toggle(self):
        if not self._full:
            return
        if self._open:
            self._close_detail()
        else:
            self._open = True
            self._detail.config(text=self._full)
            self._detail.pack(fill="x", padx=(0, 0), pady=(0, 4))
            self._btn.config(text="?", fg=T.ACCENT)
        _resync(self)

    def _close_detail(self):
        self._open = False
        self._detail.pack_forget()
        try:
            self._btn.config(fg=T.TXT3)
        except Exception:
            pass

    @property
    def expanded(self):
        return self._open


def _norm_item(x):
    """把 (label, value) / (label, value, hint) / label 统一成三元组。"""
    if isinstance(x, str):
        return (x, "", "")
    x = tuple(x)
    if len(x) == 1:
        return (x[0], "", "")
    if len(x) == 2:
        return (x[0], x[1], "")
    return (x[0], x[1], x[2])


class FoldMetrics(tk.Frame):
    """指标卡默认压成一行文字，点「展开」才铺成格子。

    为什么：文献库有 5 张指标卡、导师页有 3 张，全部常驻要占掉整整一屏，
    而这些数字看一次就够了，平时并不需要一直盯着。压成一行之后
    第一屏能多放十几条真正的内容。
    """

    def __init__(self, parent, items, bg=None, cols=4, summary_fmt=None, pad=(0, 6)):
        self._bg = bg or T.BG
        super().__init__(parent, bg=self._bg)
        self._items = [_norm_item(x) for x in (items or [])]   # [(label, value, hint)]
        self._vals = {}
        self._cols = max(1, int(cols))
        self._summary_fmt = summary_fmt
        self._open = False
        self._row = tk.Frame(self, bg=self._bg)
        self._row.pack(fill="x", pady=pad)
        self._summary = tk.Label(self._row, text="", bg=self._bg, fg=T.TXT2,
                                 font=T.T_BODY_SM(), anchor="w", justify="left",
                                 wraplength=T.wrap(640))
        self._btn = tk.Label(self._row, text="展开", bg=self._bg, fg=T.ACCENT,
                             font=T.T_CAPTION(), cursor="hand2", padx=6)
        # 先 pack 右侧固定按钮再让摘要 expand，否则长摘要会把按钮挤出可视区
        self._btn.pack(side="right")
        self._summary.pack(side="left", fill="x", expand=True)
        self._btn.bind("<Button-1>", lambda e: self.toggle())
        self._grid = tk.Frame(self, bg=self._bg)
        self._render_summary()

    def set_values(self, values):
        """values: {label: text} —— 只更新数字，不重建控件。"""
        self._vals.update({str(k): str(v) for k, v in (values or {}).items()})
        self._render_summary()
        if self._open:
            self._build_grid()

    def values(self):
        """当前各项的值 {label: text}，供测试与调用方读取。"""
        return dict(self._vals)

    def _render_summary(self):
        parts, pending = [], False
        for label, value, _hint in self._items:
            v = self._vals.get(label)
            if v in (None, ""):
                pending = True
                continue
            parts.append("%s %s" % (label, v))
        if parts:
            txt = "  ·  ".join(parts)
        else:
            # 一项值都没有时不要留一条空白行——调用方会随后 set_values
            txt = "数据加载中…" if pending else ""
        self._summary.config(text=txt)
        # 「展开」只在一行装不下时才有意义：5 项指标在 1320 宽的窗口里
        # 一行就放得下，还挂个展开按钮只会让人以为漏了东西（实测右栏空了
        # 半屏，按钮孤零零飘在右下角）。
        if txt and len(txt) <= 68:
            self._btn.pack_forget()
        elif not self._btn.winfo_ismapped():
            self._btn.pack(side="right")

    def toggle(self):
        if self._open:
            self._open = False
            self._grid.pack_forget()
            self._btn.config(text="展开")
        else:
            self._open = True
            self._build_grid()
            self._grid.pack(fill="x", pady=(0, 6))
            self._btn.config(text="收起")
        _resync(self)

    def _build_grid(self):
        for w in self._grid.winfo_children():
            w.destroy()
        for i, (label, _v, hint) in enumerate(self._items):
            r, c = divmod(i, self._cols)
            cell = T.Card(self._grid, pad=10)
            cell.grid(row=r, column=c, sticky="nsew", padx=(0, 8), pady=(0, 8))
            self._grid.columnconfigure(c, weight=1)
            tk.Label(cell.body, text=label, bg=T.CARD, fg=T.TXT3,
                     font=T.T_CAPTION(), anchor="w").pack(fill="x")
            tk.Label(cell.body, text=self._vals.get(label, "—"), bg=T.CARD, fg=T.TXT,
                     font=T.T_METRIC(), anchor="w").pack(fill="x")
            if hint:
                tk.Label(cell.body, text=hint, bg=T.CARD, fg=T.TXT4,
                         font=T.T_CAPTION(), anchor="w", justify="left",
                         wraplength=T.wrap(150)).pack(fill="x")

    @property
    def expanded(self):
        return self._open


class EmptyState(tk.Frame):
    """空态：一句引导 + 一个主按钮。

    原来最新研究页的「怎么用」三步教程占了半屏，而用户真正需要的只是
    「我现在该点哪里」。教程可以保留，但要收进 `Hint` 里按需展开。
    """

    def __init__(self, parent, title, hint="", action=None, action_text="",
                 extra=None, bg=None):
        self._bg = bg or T.CARD
        # 方向图谱/方法论这类三栏页，右栏空着时最怕「一整片黑 + 中间一行字」，
        # 像页面坏了。所以整块收在左上角、标题用 TXT3，看着像系统在等输入。
        super().__init__(parent, bg=self._bg, padx=14, pady=14)
        # 用 grid 而不是 pack：被放进 expand=True 的容器时，pack 会把整块
        # 垂直居中，空态就飘到了一大片空白中间（方向图谱右栏踩过）。
        self.grid_columnconfigure(0, weight=1)
        self._row = 0
        self._add(
            tk.Label(self, text=title, bg=self._bg, fg=T.TXT3,
                     font=T.T_BODY_SM(), anchor="w", justify="left",
                     wraplength=T.wrap(560)), pady=(0, 6))
        if hint:
            # 引导语本身就短，直接铺开显示；教程类长文字在调用方就用 Hint 收起来
            self._add(
                tk.Label(self, text=hint, bg=self._bg, fg=T.TXT3,
                         font=T.T_BODY_SM(), anchor="w", justify="left",
                         wraplength=T.wrap(480)), pady=(0, 10))
            self._hint = None
        else:
            self._hint = None
        if action and action_text:
            self._add(T.Btn(self, action_text, action, "primary"))
        if extra:
            # extra 既可以是「往我这里塞控件」的回调，也可以是
            # (文案, 回调) 二元组 —— 后者在计划页用：空态除了主按钮（用推荐
            # 阶段起步）还需要一个次等出口（直接加一条待办），两个都摆成
            # primary 按钮会分不清哪个是默认动作。
            if isinstance(extra, (tuple, list)) and len(extra) == 2:
                label, cmd = extra
                self._add(T.Btn(self, str(label), cmd, "ghost"))
            else:
                extra(self)
        # 最后一行用 spacer 顶住剩余空间，整块永远贴在上方（不要改回
# 给最后一行 set weight —— 那会把控件拉高并垂直居中，见 _spacer 的说明）。
        self._spacer()

    def _add(self, widget, pady=(0, 0)):
        # 按钮只占自己需要的宽度（sticky="w"），文字类控件才拉满一行。
        # 原来一律 sticky="new"，空态里的按钮被撑成一条横贯整页的紫色长条，
        # 看着像横幅广告而不是按钮（2026-11-15 计划页截图里就是这个现象）。
        fill = "w" if isinstance(widget, T.Btn) else "new"
        widget.grid(row=self._row, column=0, sticky=fill, pady=pady)
        self._row += 1

    def _spacer(self):
        """末尾放一个零高度占位行，把剩余空间全吃掉。

        为什么不是直接给最后一行 `grid_rowconfigure(weight=1)`：那样这一行
        自己的控件会被拉高，控件在其中垂直居中 —— 计划页空态只有 4 个控件时，
        整块被撑成一屏高，文字飘在下半屏中间，上半屏全空（2026-11-15 实测）。
        单独一行 spacer 不占内容高度，效果才是「贴左上」。
        """
        sp = tk.Frame(self, bg=self._bg, height=0)
        sp.grid(row=self._row, column=0, sticky="nsew")
        self.grid_rowconfigure(self._row, weight=1)


# ---------------------------------------------------------------- 可折叠分区
class Section(tk.Frame):
    """一张卡片 = 一个分区，默认收起，点标题展开。

    为什么需要：设置页原来五个卡片一路竖排（存储 / 大模型 / 抓取 / 提示词产出 /
    关于 / 网页体验），用户找「大模型接入」要滚两屏才知道它在哪。收起后
    一屏就能看见全部分区名，找东西从「翻一遍」变成「扫一眼」。

    与 `Hint` 的区别：`Hint` 收的是说明文字，主内容永远在；`Section` 收的是
    整块内容，用户明确点开才铺出来。

    用法（和普通 Card 一样用 body 往里放东西）::

        sec = Section(parent, "大模型接入", "可选 · 配了能改写检索式与对话")
        sec.pack(fill="x", pady=(0, 10))
        tk.Label(sec.body, text="……").pack(fill="x")

    `open=True` 让它一开始就展开（最常用的那个分区用它）。
    """

    def __init__(self, parent, title, sub="", bg=None, pad=12, open=False,
                 on_open=None):
        self._bg = bg or T.CARD
        super().__init__(parent, bg=self._bg)
        self.expanded = bool(open)
        self._on_open = on_open
        self._on_open_done = False

        self.card = T.Card(self, pad=pad, fill_y=False)
        self.card.pack(fill="x")
        body = self.card.body
        head = tk.Frame(body, bg=self._bg, cursor="hand2")
        head.pack(fill="x")
        self._arrow = tk.Label(head, text="▸" if not open else "▾", bg=self._bg,
                               fg=T.TXT3, font=T.T_BODY_SM(), width=2, anchor="w")
        self._arrow.pack(side="left")
        labels = tk.Frame(head, bg=self._bg, cursor="hand2")
        self._title_labels = labels
        labels.pack(side="left", fill="x", expand=True)
        title_label = tk.Label(labels, text=title, bg=self._bg, fg=T.TXT,
                               font=T.T_SECTION(), anchor="w", justify="left")
        title_label.pack(fill="x")
        T.fill_wrap(title_label)
        if sub:
            sub_label = tk.Label(labels, text=sub, bg=self._bg, fg=T.TXT3,
                                 font=T.T_CAPTION(), anchor="w", justify="left")
            sub_label.pack(fill="x", pady=(2, 0))
            T.fill_wrap(sub_label)
        for w in (head, self._arrow, labels) + tuple(labels.winfo_children()):
            try:
                w.bind("<Button-1>", lambda e: self.toggle())
                w.bind("<Enter>", lambda e: self._hover(True))
                w.bind("<Leave>", lambda e: self._hover(False))
            except Exception:
                pass

        self.body = tk.Frame(body, bg=self._bg)
        if open:
            self.body.pack(fill="x", pady=(8, 0))

    def _hover(self, on):
        try:
            col = T.TXT if on else T.TXT2
            self._title_labels.winfo_children()[0].config(fg=col)
        except Exception:
            pass

    def toggle(self, value=None):
        self.expanded = (not self.expanded) if value is None else bool(value)
        if self.expanded:
            self.body.pack(fill="x", pady=(8, 0))
            self._arrow.config(text="▾")
            if self._on_open and not self._on_open_done:
                self._on_open_done = True
                try:
                    self._on_open(self.body)
                except Exception as exc:
                    print("[Section] on_open 失败：%r" % (exc,))
        else:
            self.body.pack_forget()
            self._arrow.config(text="▸")
        _resync(self)
        # 分区挂在滚动区里时，展开/收起会改内容总高；只靠 _resync 有时
        # 量不出新高度（Card 的防抖还没跑完），所以再回调一次宿主。
        cb = getattr(self, "on_resize", None)
        if cb:
            try:
                cb()
            except Exception as exc:
                print("[Section] on_resize 失败：%r" % (exc,))
        return self.expanded


# ---------------------------------------------------------------- 模块宫格
# 用户 2026-11-15 给了一张「科研导航站」的参考图：一行一行的图标宫格，
# 每格 = 图标 + 名称，下面再一张卡放另一组。他要的是同一个意思——
# 打开应用第一页就能看见「这个软件有哪几块」，每块点一下直接进去。
#
# 为什么不直接复用侧栏：侧栏是纵向列表，一屏最多 12 行，越往下越少人看；
# 宫格能一屏铺开全部模块，并且每格可以带一句「这一块是干什么的」。
_TILE_BG = "card"


class Tile(tk.Frame):
    """一个模块格子：图标 + 名称 + 一句说明 + 可选的角标数字。

    icon 传 app_icons 里的图标名（"topic" / "gap" …），由 _IconChip 画出来。
    **不再接受 Unicode 字形**：字体里的几何符号宽高和基线都不统一，一排下来
    高低不齐，而且粗细改不了（见 app_icons 模块头部的说明）。
    """

    def __init__(self, parent, icon, title, desc="", badge="", command=None,
                 bg=None, width=168, height=76):
        self._bg = bg or T.CARD
        # **不再固定宽高 + pack_propagate(False)**。
        # 固定 168px 时，瓦片在 4 列布局里比格子窄，右侧留白参差；而且
        # desc 的 wraplength 是构造时算死的，窗口一变宽，文字还在老位置断行
        # （截图上「角度不同/的候选」就是这么断的）。
        # 现在让瓦片跟着 grid 格子伸缩，靠 <Configure> 动态调 wraplength。
        super().__init__(parent, bg=self._bg, cursor="hand2")
        self.command = command
        self._icon_name = icon
        self._width_hint = width

        inner = tk.Frame(self, bg=self._bg)
        inner.pack(fill="both", expand=True, padx=12, pady=(10, 9))
        head = tk.Frame(inner, bg=self._bg)
        head.pack(fill="x")
        # 图标和标题在**自己这一行**，角标另起一行最右。
        # 原来三者挤在同一个 head 里：标题 pack(expand) + 角标 pack(side=right)
        # 时，Tk 会优先保证右侧的角标，把标题压到只能折行甚至被裁；
        # 而标题一折行，整格高度又跟着变，于是每格高度参差 —— 截图上
        # 就是这个观感（「科研方法论 7 套」那格比旁边高半行）。
        self.icon_cv = _IconChip(head, icon, self._bg)
        self.icon_cv.pack(side="left", padx=(0, 8))
        self.title_lb = tk.Label(head, text=title, bg=self._bg, fg=T.TXT,
                                 font=T.T_LABEL(), anchor="w",
                                 justify="left")
        self.title_lb.pack(side="left", fill="x", expand=True)
        self._desc_lb = None
        if desc:
            self._desc_lb = tk.Label(inner, text=desc, bg=self._bg, fg=T.TXT3,
                                     font=T.T_CAPTION(), anchor="w",
                                     justify="left",
                                     wraplength=max(80, width - 28))
            self._desc_lb.pack(fill="x", pady=(5, 0))
        self._badge_lb = tk.Label(inner, text=badge or " ", bg=self._bg,
                                  fg=T.TXT4, font=T.T_CAPTION(), anchor="w")
        # 角标**总是 pack**：没有角标时放一个空格，行高就一样了。
        # 用空串 "" 不行 —— Label 没有内容时请求高度会塌成 0，
        # 那一格比同排矮半行（实测第 4 格「创新点库」就矮了一截）。
        self._badge_lb.pack(anchor="w", pady=(3, 0))
        # 淡底 + 细边框，让每一格看起来是「一块可点的区域」而不是散落的文字。
        # 只有一条底边不够：4×3 排开时中线缺失，读起来像一整段文字流。
        # 用 LINE 而不是 LINE_SOFT：深色下 LINE_SOFT(#1a1e22) 离卡片色(#15181c)
        # 只差一档，环几乎看不见，网格还是糊成一片。
        self.configure(highlightthickness=1,
                       highlightbackground=T.LINE,
                       highlightcolor=T.LINE)
        # 用 1px Frame 而不是画边框：深色下卡片本身不描边（见 card_outline），
        # 单独给每格描一圈会立刻回到「满屏都是框」的老问题。
        # 放在 self 最底部、**不加 padx**：加 padx 会让线缩短，看起来像断掉的短线。
        # 2026-11-15：改用 Frame 的 highlight 环（见下），这条线已移除，
        # 否则每格会同时有「环 + 底线」两重边框。

        self.bind("<Configure>", self._on_resize)
        for w in (self, inner, head, self.title_lb):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._hover_on)
            w.bind("<Leave>", self._hover_off)

    def _paint_edge(self, hot=False):
        """描一圈极淡的边，悬停时换成亮一点的中性灰。

        用 highlight 环而不是画线：环只占 Frame 自带的 1px 高亮带，
        不用额外占位，也不会因为子控件重排而错位。
        """
        try:
            c = T.ACCENT if hot else T.LINE
            self.configure(highlightbackground=c, highlightcolor=c)
        except Exception:
            pass

    def _on_resize(self, event):
        """宽度变了就跟着改换行宽度 —— 否则文字永远按构造时的 168px 断行。"""
        if self._desc_lb is None:
            return
        want = max(80, event.width - 28)
        if str(want) != self._desc_lb.cget("wraplength"):
            self._desc_lb.configure(wraplength=want)

    def _click(self, _e=None):
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def _hover_on(self, _e=None):
        for w in self._walk():
            try:
                w.configure(bg=T.CARD_HI)
            except Exception:
                pass
        self._paint_edge(hot=True)
        try:
            self.icon_cv.repaint(T.CARD_HI, T.ACCENT)
        except Exception:
            pass

    def _hover_off(self, _e=None):
        for w in self._walk():
            try:
                w.configure(bg=self._bg)
            except Exception:
                pass
        self._paint_edge(hot=False)
        try:
            self.icon_cv.repaint(self._bg, T.TXT2)
        except Exception:
            pass

    def _walk(self):
        out = [self]
        for a in self.winfo_children():
            out.append(a)
            for b in a.winfo_children():
                out.append(b)
        return out


class _IconChip(tk.Frame):
    """图标 + 一点点留白。**不画色块底**。

    参考图里图标就是一条细线图形，没有「图标装在一个方块里」的底片 ——
    那种彩色方块底是另一套设计的语言（而且同一排 12 个方块会让宫格看着
    比实际更重）。这里只保留图形本身，颜色用弱色，悬停时换品牌色。
    """

    def __init__(self, parent, name, bg, size=18, fg=None):
        super().__init__(parent, bg=bg)
        import app_icons as I
        self._name = name
        self._size = size
        self._fg = fg or T.TXT2
        self.cv = I.icon_canvas(self, name, size=size, fg=self._fg, bg=bg,
                                cursor="hand2")
        self.cv.pack()
        for w in (self, self.cv):
            w.bind("<Button-1>", lambda e: self.event_generate("<Button-1>"))
            w.bind("<Enter>", lambda e: self.event_generate("<Enter>"))
            w.bind("<Leave>", lambda e: self.event_generate("<Leave>"))

    def repaint(self, bg, fg):
        import app_icons as I
        self.configure(bg=bg)
        I.draw(self.cv, self._name, size=self._size, fg=fg, bg=bg)


class TileGrid(tk.Frame):
    """把若干 Tile 排成响应式宫格：宽度够就多列，窄了自动减少列数。

    和 `app_main.HomePage._layout_stats` 同一个思路（按可用宽度选列数），
    但这里列数由格子最小宽度算出来，不用写死 4 / 2。
    """

    def __init__(self, parent, tiles, bg=None, min_w=176, gap=8, cols_max=4):
        self._bg = bg or T.BG
        super().__init__(parent, bg=self._bg)
        self._tiles = list(tiles)     # [(icon, title, desc, badge, cmd), ...]
        self._min_w = min_w
        self._gap = gap
        self._cols_max = cols_max
        self._cols = 0
        self._widgets = []
        self.bind("<Configure>", self._on_resize)
        self._layout(cols_max)
        # 建完立刻摆位置：_layout 只负责建控件，位置由 reflow 统一管，
        # 两条路径不会各写一套 padx/pady 的口径。
        self._cols = 0
        self.reflow(cols_max)

    def _on_resize(self, event):
        avail = max(0, event.width)
        if avail <= 0:
            return
        cols = int((avail + self._gap) // (self._min_w + self._gap))
        cols = max(1, min(self._cols_max, cols))
        if cols != self._cols:
            self.reflow(cols)

    def _layout(self, cols):
        """**只建一次**：首次把瓦片建出来（要重建时请先调 destroy_all）。

        原来这里在每次列数变化时 `destroy()` 全部瓦片再重建（11 个瓦片 =
        11 个 Canvas + 40 多个 Label + 一堆事件绑定），实测一次 318–710ms。
        而拖动窗口时列数会在 4/3/2 之间来回跳，于是每拖一帧就要付一次这个钱 ——
        这就是「缩放不流畅」的真正原因，不是绘制慢，是控件在被反复重建。
        """
        self._cols = cols
        for w in self._widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._widgets = []
        for i in range(self._cols_max):
            self.grid_columnconfigure(i, weight=1 if i < cols else 0)
            # uniform="col"：让每一列的宽度严格相等。不加的话 Tk 按各格
            # 请求宽度分配，而每格的说明文字长短不同，列宽就一大一小，
            # 空格子的右边缘排成锯齿 —— 这正是「粗糙」的来源。
            self.grid_columnconfigure(i, uniform="col")
        for i, (icon, title, desc, badge, cmd) in enumerate(self._tiles):
            t = Tile(self, icon, title, desc, badge, cmd, bg=T.CARD)
            self._widgets.append(t)

    def reflow(self, cols):
        """只改 grid 位置，不动控件本身 —— 缩放时走这条路（约 1ms）。"""
        if cols == self._cols:
            return
        self._cols = cols
        for i in range(self._cols_max):
            self.grid_columnconfigure(i, weight=1 if i < cols else 0)
        for i, t in enumerate(self._widgets):
            r, c = i // cols, i % cols
            if t.grid_info().get("row") == r and t.grid_info().get("column") == c:
                continue
            t.grid_configure(
                row=r, column=c, sticky="nsew",
                padx=(0 if c == 0 else self._gap, 0),
                pady=(0 if r == 0 else self._gap, 0))
        # 同一行里的格子等高：grid 里每行的高度默认取该行最高那一格，
        # sticky="nsew" 已经让它们都撑满，这里不用额外处理。

    def set_cols_immediate(self, cols):
        """首次布局用：建控件 + 摆位置一次做完（只在 __init__ 里调用）。"""
        self._cols = 0
        self.reflow(cols)
        for i, t in enumerate(self._widgets):
            r, c = i // cols, i % cols
            t.grid_configure(
                row=r, column=c, sticky="nsew",
                padx=(0 if c == 0 else self._gap, 0),
                pady=(0 if r == 0 else self._gap, 0))


class WrapRow(tk.Frame):
    """一排控件（通常是按钮）的容器：放不下就折到下一行。

    Tk 本身不折行 —— 横排一旦超宽，最右的控件被直接剪掉半截。
    字号调到「超特大」后每个按钮宽了 50%，2026-11 的截图里每页按钮组
    都断在右边。这里按每个控件的实际请求宽度手工排：
    一行放不下就 `row += 1`，并把这一行的最大高度记下来做行距。

    用法：
        r = T.row(card.body)          # 或 U.WrapRow(card.body)
        r.pack(fill="x")
        r.add(T.Btn(r, "保存", cmd, "primary"))
        r.add(T.Btn(r, "取消", cmd2))
    注意 `add()` 之后**不要**再 .pack()/.grid() —— 位置由本类决定。
    """

    def __init__(self, parent, padx=6, pady=0, gap=6, rowgap=4, bg=None):
        bg = bg or parent.cget("bg")
        tk.Frame.__init__(self, parent, bg=bg)
        self._gap, self._rowgap = gap, rowgap
        self._items = []
        self._last_w = -1
        self._cells = {}          # widget -> (行, 列)
        if padx or pady:
            self.configure(padx=0, pady=0)
        self.bind("<Configure>", self._flush, add="+")

    def add(self, widget, **kw):
        self._items.append(widget)
        self._flush(force=True)
        return widget

    def items(self):
        return list(self._items)

    def _flush(self, e=None, force=False):
        w = self.winfo_width()
        if w <= 1:
            return
        if not force and abs(w - self._last_w) < 8:
            return
        self._last_w = w
        # 用 place 手工定位：grid 的列宽是「各行同一列的最大值」，
        # 折行后这些列宽相加会把 WrapRow 自己的请求宽度撑到整行总和，
        # 嵌进按比例分栏时就会把另一栏挤扁。place 不参与请求宽度计算。
        plan = []
        x = y = rowh = 0
        for it in self._items:
            try:
                iw = it.winfo_reqwidth()
                ih = it.winfo_reqheight()
            except Exception:
                iw, ih = 90, 30
            if x and x + iw > w:
                x = 0
                y += rowh + self._rowgap
                rowh = 0
            plan.append((x, y, iw, ih))
            x += iw + self._gap
            rowh = max(rowh, ih)
        old = getattr(self, "_plan", [])
        self._plan = plan
        if not force and old == plan:
            return
        for it, (px, py, iw, ih) in zip(self._items, plan):
            it.place(x=px, y=py, width=iw, height=ih)
        self.configure(height=y + rowh)
        self._rows = 0
        prev = None
        for (_, ry, _, _) in plan:
            if ry != prev:
                self._rows += 1
                prev = ry


def btn_row(parent, widgets, **kw):
    """一句话把一个控件列表塞进折行容器：给改造已有代码用。"""
    r = WrapRow(parent, **kw)
    for w in widgets:
        r.add(w)
    return r
