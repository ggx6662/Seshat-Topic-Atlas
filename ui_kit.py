#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网页版同款组件。

赛事网页（competition/site）的界面语言是：圆角卡片 / 分段控件 / 计数标签 /
指标块 / 虚线空态 / 眉标 + 衬线大标题。桌面端原来每个页面各写各的灰框，
这里把这几样收成一套原语，页面只负责组合。

颜色仍全部取自 app_theme 的语义令牌，明暗切换后由整窗重建生效。
"""
import tkinter as tk
import tkinter.font as tkfont

import app_theme as T
import app_icons as I


def _measure(font):
    try:
        return tkfont.Font(font=font).measure
    except Exception:
        return lambda s: len(str(s)) * 8


def _card_bg(parent):
    try:
        return parent.cget("bg")
    except Exception:
        return T.CARD


# ---------------------------------------------------------------- 眉标 / 标题
def eyebrow(parent, text, num="", bg=None, color=None):
    """一行等宽眉标：左边小字，右边一个描边小圆号（对应网页的 01 / 02）。"""
    bg = bg or _card_bg(parent)
    row = tk.Frame(parent, bg=bg)
    lb = tk.Label(row, text=text, bg=bg, fg=color or T.TXT4,
                  font=T.T_EYEBROW(), anchor="w")
    lb.pack(side="left")
    if num:
        tk.Label(row, text=str(num), bg=bg, fg=T.TXT3, font=T.M(8),
                 padx=T.sp(5), pady=0).pack(side="right")
    return row


def hero(parent, title, lead="", kicker="", num="", bg=None):
    """英雄区文字块：眉标 + 衬线大标题 + 一段说明。返回容器 Frame。"""
    bg = bg or _card_bg(parent)
    box = tk.Frame(parent, bg=bg)
    if kicker:
        eyebrow(box, kicker, num, bg=bg).pack(fill="x")
    lb = tk.Label(box, text=title, bg=bg, fg=T.TXT, font=T.T_HERO(),
                  anchor="w", justify="left")
    lb.pack(fill="x", pady=(T.sp(8), T.sp(6)))
    T.fill_wrap(lb, pad=6)
    if lead:
        p = tk.Label(box, text=lead, bg=bg, fg=T.TXT2, font=T.T_BODY_SM(),
                     anchor="w", justify="left")
        p.pack(fill="x")
        T.fill_wrap(p, pad=6)
    return box


# ---------------------------------------------------------------- 计数标签
class Chip(tk.Canvas):
    """圆角标签。active=True 时是品牌色实底，对应网页里选中的分类。"""

    def __init__(self, parent, text, count=None, active=False, command=None,
                 bg=None, height=None, font=None):
        self._bg = bg or _card_bg(parent)
        self._text = str(text)
        self._count = None if count in (None, "") else str(count)
        self._active = bool(active)
        self._command = command
        self._font = font or T.T_BODY_SM()
        fm = _measure(self._font)
        self._h = height or T.sp(29)
        pad = T.sp(11)
        w = fm(self._text) + pad * 2
        if self._count:
            w += fm(self._count) + T.sp(9)
        super().__init__(parent, width=w, height=self._h, bg=self._bg,
                         highlightthickness=0, bd=0,
                         cursor=("hand2" if command else "arrow"))
        self._hover = False
        self._draw()
        if command:
            self.bind("<Button-1>", lambda e: self._command())
            self.bind("<Enter>", lambda e: self._set_hover(True))
            self.bind("<Leave>", lambda e: self._set_hover(False))

    def _set_hover(self, on):
        self._hover = on
        self._draw()

    def set_active(self, on):
        self._active = bool(on)
        self._draw()

    def set_text(self, text):
        self._text = str(text)
        fm = _measure(self._font)
        w = fm(self._text) + T.sp(11) * 2
        if self._count:
            w += fm(self._count) + T.sp(9)
        self.config(width=w)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = int(self.winfo_reqwidth()), self._h
        if self._active:
            fill, line = T.ACCENT, T.ACCENT
            fg = T.on_primary_fg()
            cg = T.mix(T.on_primary_fg(), T.ACCENT, 0.30)
        else:
            fill = T.tint(T.ACCENT, 0.16 if self._hover else 0.07, T.CARD)
            line = T.tint(T.ACCENT, 0.30 if self._hover else 0.16, T.CARD)
            fg, cg = T.TXT2, T.TXT4
        T._round_rect(self, 0.5, 0.5, w - 1.5, h - 1.5, h / 2.0,
                      fill=fill, outline=line)
        pad = T.sp(11)
        if self._count:
            cf = T.T_CAPTION()
            fm_c = _measure(cf)
            cw = fm_c(self._count)
            self.create_text(w - pad, h / 2.0, text=self._count, anchor="e",
                             fill=cg, font=cf)
            self.create_text(pad, h / 2.0, text=self._text, anchor="w",
                             fill=fg, font=self._font)
        else:
            self.create_text(w / 2.0, h / 2.0, text=self._text, anchor="center",
                             fill=fg, font=self._font)


# ---------------------------------------------------------------- 分段控件
class Segmented(tk.Canvas):
    """网页顶部的分段标签条（按方向推荐 / 全部学者 / 院校）。

    items: [(key, label)] 或 [(key, label, count)]
    """

    def __init__(self, parent, items, value=None, command=None, bg=None,
                 font=None):
        self._items = list(items)
        self._value = value or self._items[0][0]
        self._command = command
        self._bg = bg or _card_bg(parent)
        self._font = font or T.T_BODY_SM()
        self._pad = T.sp(12)
        self._widths = []
        self._measure_items()
        self._h = T.sp(36)
        total = sum(self._widths) + T.sp(3) * 2
        super().__init__(parent, width=total, height=self._h, bg=self._bg,
                         highlightthickness=0, bd=0)
        self._hover = None
        self._draw()
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))

    def _measure_items(self):
        fm = _measure(self._font)
        self._widths = []
        for it in self._items:
            n = fm(str(it[1]))
            if len(it) > 2 and it[2] not in (None, ""):
                n += fm(str(it[2])) + T.sp(6)
            self._widths.append(n + self._pad * 2)

    def set_items(self, items):
        """替换分段项（通常是计数加载完之后补上 N）。宽度重新量。"""
        self._items = list(items)
        if self._value not in [it[0] for it in self._items]:
            self._value = self._items[0][0]
        self._measure_items()
        self.configure(width=sum(self._widths) + T.sp(3) * 2)
        self._draw()

    def value(self):
        return self._value

    def set_value(self, v, notify=False):
        if v == self._value:
            return
        self._value = v
        self._draw()
        if notify and self._command:
            self._command(v)

    def _seg_at(self, x):
        px = T.sp(3)
        for it, w in zip(self._items, self._widths):
            if px <= x < px + w:
                return it[0]
            px += w
        return None

    def _click(self, e):
        key = self._seg_at(e.x)
        if key is not None and key != self._value:
            self.set_value(key, notify=True)

    def _motion(self, e):
        key = self._seg_at(e.x)
        self._set_hover(None if key == self._value else key)

    def _set_hover(self, key):
        if key == self._hover:
            return
        self._hover = key
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = int(self.winfo_reqwidth()), self._h
        T._round_rect(self, 0.5, 0.5, w - 1.5, h - 1.5, h / 2.0,
                      fill=T.CARD, outline=T.LINE)
        px = T.sp(3)
        for it, sw in zip(self._items, self._widths):
            key, lab = it[0], str(it[1])
            on = key == self._value
            if on:
                T._round_rect(self, px, 2.5, px + sw - 0.5, h - 2.5,
                              (h - 5) / 2.0, fill=T.OVERLAY,
                              outline=T.LINE)
            fg = T.TXT if on else (T.TXT2 if key == self._hover else T.TXT3)
            cf = T.T_CAPTION()
            fm = _measure(self._font)
            if len(it) > 2 and it[2] not in (None, ""):
                cnt = str(it[2])
                cw = _measure(cf)(cnt)
                inner_l = px + self._pad
                self.create_text(inner_l, h / 2.0, text=lab, anchor="w",
                                 fill=fg, font=T.T_BODY_SM() if on else self._font)
                self.create_text(inner_l + fm(lab) + T.sp(6), h / 2.0,
                                 text=cnt, anchor="w", fill=T.TXT4, font=cf)
                # 宽度不足时（超大字）右端会被裁，这里不再画
            else:
                self.create_text(px + sw / 2.0, h / 2.0, text=lab,
                                 anchor="center", fill=fg,
                                 font=T.T_BODY_SM() if on else self._font)
            px += sw


# ---------------------------------------------------------------- 指标块
class StatTile(T.Card):
    """网页版指标块：大号数字 + 一行说明。"""

    def __init__(self, parent, value, label, hint="", bg=None, pad=None):
        super().__init__(parent, bg=bg or T.CARD, border=T.LINE_SOFT,
                         radius=max(8, T.RADIUS - 2),
                         pad=pad if pad is not None else T.sp(12))
        self._val = tk.Label(self.body, text=str(value), bg=self.bg_color,
                             fg=T.TXT, font=T.T_METRIC(),
                             anchor="w", justify="left")
        self._val.pack(fill="x")
        self._lab = tk.Label(self.body, text=str(label), bg=self.bg_color,
                             fg=T.TXT3, font=T.T_CAPTION(), anchor="w",
                             justify="left")
        self._lab.pack(fill="x", pady=(T.sp(2), 0))
        self._hint = None
        if hint:
            self._hint = tk.Label(self.body, text=hint, bg=self.bg_color,
                                  fg=T.TXT4, font=T.T_CAPTION(), anchor="w",
                                  justify="left")
            self._hint.pack(fill="x", pady=(T.sp(2), 0))
            T.fill_wrap(self._hint, pad=6)

    def set(self, value, label=None, hint=None):
        self._val.config(text=str(value))
        if label is not None:
            self._lab.config(text=str(label))
        if hint is not None and self._hint is not None:
            self._hint.config(text=str(hint))


# ---------------------------------------------------------------- 虚线空态
class EmptyPanel(tk.Frame):
    """网页版空态：虚线圆角框 + 居中图标 + 标题 + 说明 + 可选按钮。"""

    def __init__(self, parent, title, body="", icon="search", cta=None,
                 cta_cmd=None, bg=None, height=None):
        bg = bg or _card_bg(parent)
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._h = height or T.sp(220)
        cv = tk.Canvas(self, bg=bg, height=self._h, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        self._cv = cv
        holder = tk.Frame(cv, bg=bg)
        self._holder = holder
        self._win = cv.create_window(0, 0, window=holder, anchor="center")

        ic = tk.Canvas(holder, width=T.sp(46), height=T.sp(46), bg=bg,
                       highlightthickness=0, bd=0)
        ic.pack(pady=(0, T.sp(8)))
        r = T.sp(23)
        ic.create_oval(1, 1, 2 * r - 1, 2 * r - 1,
                       fill=T.tint(T.ACCENT, 0.10, bg),
                       outline=T.tint(T.ACCENT, 0.22, bg))
        try:
            I.draw_on(ic, icon, size=T.sp(18), fg=T.ACCENT,
                      x=(2 * r - T.sp(18)) / 2, y=(2 * r - T.sp(18)) / 2)
        except Exception:
            pass
        self._title = tk.Label(holder, text=title, bg=bg, fg=T.TXT,
                               font=T.T_SECTION(), anchor="center",
                               justify="center")
        self._title.pack()
        if body:
            b = tk.Label(holder, text=body, bg=bg, fg=T.TXT3,
                         font=T.T_BODY_SM(), anchor="center", justify="center")
            b.pack(pady=(T.sp(6), 0))
            T.fill_wrap(b, pad=12)
        if cta:
            btn = T.Btn(holder, cta, cta_cmd, "primary")
            btn.pack(pady=(T.sp(14), 0))
        cv.bind("<Configure>", self._layout)
        self._shape = None

    def _layout(self, e):
        if self._shape:
            self._cv.delete(self._shape)
        try:
            # _round_rect 只画实心形状，虚线要自己走 create_line 路径
            r = T.sp(18)
            x1, y1, x2, y2 = 1.5, 1.5, e.width - 1.5, e.height - 1.5
            pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                   x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                   x1, y2, x1, y2 - r, x1, y1 + r, x1, y1, x1 + r, y1]
            self._shape = self._cv.create_line(
                pts, smooth=True, dash=(5, 4), fill=T.LINE,
                width=1, capstyle="round")
        except Exception:
            pass
        self._cv.coords(self._win, e.width / 2.0, e.height / 2.0)
        # 内容块宽度不超过容器，长说明在窄栏里折行
        self._cv.itemconfig(self._win, width=max(200, e.width - T.sp(48)))


# ---------------------------------------------------------------- 提示条
def info_note(parent, text, bg=None, title=""):
    """浅色提示条（对应网页的 CCF 分级说明那一块）。"""
    base = bg or _card_bg(parent)
    tint = T.tint(T.ACCENT, 0.06, base)
    c = T.Card(parent, bg=tint, border=T.tint(T.ACCENT, 0.18, base),
               radius=T.RADIUS, pad=T.sp(10))
    strip = tk.Frame(c.body, bg=tint)
    strip.pack(fill="x")
    ic = tk.Canvas(strip, width=T.sp(18), height=T.sp(18), bg=tint,
                   highlightthickness=0, bd=0)
    ic.pack(side="left", anchor="n", pady=(1, 0))
    ic.create_oval(1, 1, T.sp(17), T.sp(17),
                   fill=T.tint(T.ACCENT, 0.16, base), outline="")
    ic.create_text(T.sp(9), T.sp(9), text="i", fill=T.ACCENT,
                   font=T.M(8, True))
    body = tk.Frame(strip, bg=tint)
    body.pack(side="left", fill="x", expand=True, padx=(T.sp(8), 0))
    if title:
        tk.Label(body, text=title, bg=tint, fg=T.TXT2, font=T.T_LABEL(),
                 anchor="w").pack(fill="x")
    lb = tk.Label(body, text=text, bg=tint, fg=T.TXT3, font=T.T_BODY_SM(),
                  anchor="w", justify="left")
    lb.pack(fill="x", pady=(1 if title else 0, 0))
    T.fill_wrap(lb, pad=8)
    return c


# ---------------------------------------------------------------- 头像
class Avatar(tk.Canvas):
    """学者卡片的姓名缩写圆标。颜色按名字稳定取一档语义色。"""

    _PALETTE = ("ACCENT", "OK", "PURPLE", "ORANGE", "WARN")

    def __init__(self, parent, name, size=None, bg=None):
        bg = bg or _card_bg(parent)
        s = size or T.sp(38)
        super().__init__(parent, width=s, height=s, bg=bg,
                         highlightthickness=0, bd=0)
        self._s = s
        self._name = (name or "?").strip()
        self.delete("all")
        key = self._PALETTE[sum(ord(ch) for ch in self._name) % len(self._PALETTE)]
        col = getattr(T, key, T.ACCENT)
        self.create_oval(1, 1, s - 1, s - 1, fill=T.tint(col, 0.16, bg),
                         outline=T.tint(col, 0.30, bg))
        self.create_text(s / 2.0, s / 2.0, text=self._initials(),
                         fill=col, font=T.F(9, True))

    def _initials(self):
        parts = [p for p in self._name.replace("·", " ").split() if p]
        if not parts:
            return "?"
        if len(parts) >= 2:
            return (parts[0][:1] + parts[-1][:1]).upper()
        return parts[0][:2].upper()


class Combo(tk.Frame):
    """一个极简下拉框：Button + Toplevel 弹出列表。

    **为什么不用 tk.OptionMenu**：Windows 上每个 OptionMenu 都要向 Tk 申请一个
    原生 HMENU，而这个句柄在 `destroy()` 之后不会立刻归还。14 个页面里本来
    只有零星几个 OptionMenu，偏偏 page_profile 一页就要建十来个 —— 用户把
    侧栏挨个点一遍、再回到「我的画像」时，Tk 会直接抛
    `_tkinter.TclError: No more menus can be allocated.`，那一页就再也打不开
    （app.goto 把它吞成一条 toast 就返回了）。这里改成纯 Tk 控件叠出来的
    弹出层，一个原生菜单都不占。

    **为什么不用 ttk.Combobox**：它在深色主题下是系统原生控件，白底黑字完全
    融不进界面，125% 缩放下高度也对不齐。

    颜色全部取自 app_theme 的令牌，明暗切换后由整窗重建生效。

    options 接受两种写法：
      - [(显示文本, 取值), ...]      —— 显示与取值不同（如中文名 / 英文键）
      - ["选项一", "选项二", ...]    —— 显示即取值
    """

    def __init__(self, parent, value, options, on_change=None, width=1,
                 bg=None, font=None, swatch=None):
        super().__init__(parent, bg=bg or _card_bg(parent), bd=0,
                         highlightthickness=0)
        self._opts = [o if isinstance(o, (tuple, list)) else (o, o)
                      for o in (options or [])]
        self.value = value if value is not None else (
            self._opts[0][1] if self._opts else "")
        self.on_change = on_change
        self._bg = bg or _card_bg(parent)
        self._font = font or T.T_BODY_SM()
        self._width = width
        # swatch：给「主题选择」这类需要色块的场景留的钩子，传函数 value→颜色
        self._swatch = swatch
        self._pop = None
        self.btn = tk.Button(
            self, text=self.label(), bg=self._bg, fg=T.TXT,
            activebackground=T.CARD_HI, activeforeground=T.TXT,
            relief="flat", bd=0, font=self._font, cursor="hand2",
            anchor="w", padx=T.sp(8), pady=T.sp(6), width=width,
            highlightthickness=1,
            highlightbackground=T.card_edge(T.LINE, self._bg))
        try:
            self.btn.config(highlightcolor=T.card_edge(T.ACCENT, self._bg))
        except Exception:
            pass
        self.btn.config(command=self.popup)
        self.btn.pack(fill="x")

    # ---------------------------------------------------------------- 取值
    def label(self):
        for text, val in self._opts:
            if val == self.value:
                return text
        return str(self.value if self.value not in (None, "") else "—")

    def get(self):
        return self.value

    def set(self, value, notify=False):
        self.value = value
        try:
            self.btn.config(text=self.label())
        except Exception:
            pass
        if notify and self.on_change:
            try:
                self.on_change(value)
            except Exception:
                pass

    def options(self):
        return list(self._opts)

    def configure_values(self, options, keep=True):
        """换一批选项。keep=True 时尽量保留当前值。"""
        self._opts = [o if isinstance(o, (tuple, list)) else (o, o)
                      for o in (options or [])]
        vals = [v for _t, v in self._opts]
        if self.value not in vals:
            self.value = vals[0] if vals else ""
        self.btn.config(text=self.label())

    # ---------------------------------------------------------------- 弹出
    def _close(self, _e=None):
        if self._pop is not None:
            try:
                self._pop.destroy()
            except Exception:
                pass
            self._pop = None

    def popup(self):
        if self._pop is not None:
            self._close()
            return
        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=T.LINE)
        self._pop = win
        try:
            x = self.btn.winfo_rootx()
            y = self.btn.winfo_rooty() + self.btn.winfo_height() + 2
            win.geometry("+%d+%d" % (x, y))
        except Exception:
            pass
        box = tk.Frame(win, bg=T.CARD)
        box.pack(padx=1, pady=1)
        for text, val in self._opts:
            row = tk.Frame(box, bg=T.CARD)
            row.pack(fill="x")
            if self._swatch is not None:
                try:
                    col = self._swatch(val)
                except Exception:
                    col = None
                if col:
                    dot = tk.Frame(row, bg=col, width=T.sp(10), height=T.sp(10))
                    dot.pack(side="left", padx=(T.sp(10), 0))
                    dot.pack_propagate(False)
            fg = T.ACCENT if val == self.value else T.TXT2
            lb = tk.Label(row, text=text, bg=T.CARD, fg=fg, font=self._font,
                          anchor="w", padx=T.sp(12), pady=T.sp(5),
                          cursor="hand2")
            lb.pack(side="left", fill="x", expand=True)

            def pick(_e, v=val):
                self._close()
                self.set(v, notify=True)

            def hover(_e, w=row):
                w.config(bg=T.CARD_HI)
                for c in w.winfo_children():
                    try:
                        c.config(bg=T.CARD_HI)
                    except Exception:
                        pass

            def leave(_e, w=row):
                w.config(bg=T.CARD)
                for c in w.winfo_children():
                    try:
                        c.config(bg=T.CARD)
                    except Exception:
                        pass

            for w in (row, lb):
                w.bind("<Button-1>", pick)
                w.bind("<Enter>", hover)
                w.bind("<Leave>", leave)
        win.bind("<FocusOut>", lambda e: self._close())
        try:
            win.focus_force()
        except Exception:
            pass

    def destroy(self):
        self._close()
        super().destroy()


def divider(parent, bg=None, pady=(0, 0)):
    f = tk.Frame(parent, bg=T.LINE_SOFT, height=1)
    f.pack(fill="x", pady=pady)
    return f