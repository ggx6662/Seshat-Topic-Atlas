#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入框联想下拉层 —— 把 autocomplete.suggest() 挂到任意 tk.Entry 上。

设计要点（都是踩过的坑）
------------------------
1. **用 Toplevel 而不是在页面里塞一个 Frame**：检索框有的在 ScrollArea 里、
   有的在 Canvas 上，塞进去会被裁掉，还会把下面的内容顶下去。
   独立 Toplevel 加 `overrideredirect(1)` 贴住输入框底部，不占布局。
2. **键盘优先级**：上下键、回车、Esc 必须 bind 在 Entry 上并 `return "break"`，
   否则回车会被 Entry 原来的 `<Return>` 绑定抢走（检索框全都绑了回车触发检索）。
3. **防抖 120ms**：每敲一个字都查 1964 条词表，快是快但会有掉帧感，
   而且在中文输入法组字过程中会疯狂触发。
4. **输入法组字期间不弹**：Windows 中文输入法敲拼音时 Entry 里是拼音字母，
   这时候弹出来的候选全是英文词，很干扰。用 `<Key>` 的 keysym 里带
   `??` 或者直接检测字符串是否为纯 ASCII 来判断 —— 这里用最简单可靠的：
   组字时 Tk 会收到 `<KeyPress>` 但 `event.keysym` 为空或 `??`。
"""
import tkinter as tk

import app_theme as T
import autocomplete

_OPEN = []  # 当前打开的联想框（SuggestBox），用于统一收起
_GLOBAL_BOUND = False


def close_all():
    """收起所有联想下拉。切页、点空白、窗口失焦时都要调用。"""
    for box in list(_OPEN):
        try:
            box.close()
        except Exception:
            pass

KIND_LABEL = {
    "combo": ("常用", T.ACCENT),
    "field": ("方向", T.OK),
    "alias": ("同义", T.PURPLE),
    "method": ("方法", T.WARN),
    "task": ("任务", T.WARN),
    "modal": ("模态", T.TXT3),
    "keyword": ("词表", T.TXT4),
    "en": ("英文", T.TXT4),
}


class SuggestBox(object):
    """把联想下拉挂到一个 Entry 上。

    用法：
        box = SuggestBox(entry, on_commit=None)
        box.bind()          # 绑定按键（构造时已自动绑）
        box.close()
    """

    def __init__(self, entry, on_commit=None, limit=8):
        self.entry = entry
        self.on_commit = on_commit
        self.limit = limit
        self.pop = None
        self.listbox = None
        self.items = []
        self._after = None
        self._active = -1
        self._suppress = False
        self._watch = None
        self._bind()
        _install_global(self.entry)

    def _root(self):
        return self.entry.winfo_toplevel()

    def _alive(self):
        try:
            return self.entry.winfo_exists() and self.entry.winfo_ismapped()
        except Exception:
            return False

    def _visible(self):
        try:
            return (self.pop is not None and self.pop.winfo_exists()
                    and self.pop.winfo_ismapped())
        except Exception:
            return False

    def _place(self, w, h):
        """把下拉贴在输入框下方；贴不到（输入框已隐藏/页面已换）就收起。"""
        if not self._alive():
            self.close()
            return
        try:
            root = self._root()
            # Windows 最大化时 state 是 "zoomed"，不能当成不可用
            if root.state() in ("iconic", "withdrawn"):
                self.close()
                return
            self.entry.update_idletasks()
            x = self.entry.winfo_rootx()
            y = self.entry.winfo_rooty() + self.entry.winfo_height()
            if y + h > self.entry.winfo_screenheight() - 40:
                y = max(0, self.entry.winfo_rooty() - h)
            self.pop.geometry("%dx%d+%d+%d" % (w, h, x, y))
        except Exception:
            self.close()

    # ------------------------------------------------------------ 事件绑定
    def _bind(self):
        e = self.entry
        e.bind("<KeyPress>", self._on_keypress, add="+")
        e.bind("<Key>", self._on_keypress, add="+")
        e.bind("<Down>", self._on_down, add="+")
        e.bind("<Up>", self._on_up, add="+")
        e.bind("<Return>", self._on_return, add="+")
        e.bind("<Escape>", self._on_escape, add="+")
        e.bind("<FocusOut>", self._on_focus_out, add="+")
        e.bind("<Button-1>", self._on_click, add="+")
        e.bind("<Unmap>", lambda _e: self.close(), add="+")
        e.bind("<Destroy>", lambda _e: self.close(), add="+")

    # ------------------------------------------------------------ 弹出/关闭
    def _popup(self):
        if self.pop is not None:
            return self.pop
        self.pop = tk.Toplevel(self.entry)
        self.pop.withdraw()
        self.pop.overrideredirect(True)
        try:
            # transient 已经保证浮层在主窗之上，且主窗最小化时一起收起；
            # 不再用 -topmost，否则切到别的应用时它还会压在最前面。
            self.pop.transient(self.entry.winfo_toplevel())
        except Exception:
            pass
        outer = tk.Frame(self.pop, bg=T.LINE, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(
            outer, activestyle="none", relief="flat", borderwidth=0,
            bg=T.CARD, fg=T.TXT, selectbackground=T.ACCENT,
            selectforeground=T.on_primary_fg(), font=T.F(9),
            highlightthickness=0, height=self.limit,
            exportselection=False, cursor="hand2")
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<ButtonRelease-1>", self._on_pick)
        self.listbox.bind("<Motion>", self._on_hover)
        return self.pop

    def close(self):
        if self._after:
            try:
                self.entry.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        if self._watch:
            try:
                self.entry.after_cancel(self._watch)
            except Exception:
                pass
            self._watch = None
        if self.pop is not None:
            try:
                self.pop.withdraw()
            except Exception:
                pass
        self._active = -1
        if self in _OPEN:
            _OPEN.remove(self)

    def _start_watch(self):
        """常驻巡检：页面切走、窗口最小化、输入框被销毁时，把浮层收掉。

        联想层是 overrideredirect + topmost 的独立窗口，不会跟着页面一起
        消失；以前只靠 Entry 的 FocusOut，点无焦点的画布/文字时焦点不转移，
        浮层就一直盖在新页面上（截图里「卡住」的那块就是这个）。
        """
        if self._watch:
            return
        try:
            self._watch = self.entry.after(500, self._tick)
        except Exception:
            self._watch = None

    def _tick(self):
        self._watch = None
        if not self._visible():
            return
        if not self._alive():
            self.close()
            return
        try:
            root = self._root()
            if root.state() in ("iconic", "withdrawn"):
                self.close()
                return
            if not root.winfo_viewable():
                self.close()
                return
        except Exception:
            self.close()
            return
        # 页面切换后输入框可能被 pack_forget，几何坐标还在但父容器不可见
        try:
            parent = self.entry.master
            while parent is not None and parent is not root:
                if not parent.winfo_ismapped():
                    self.close()
                    return
                parent = parent.master
        except Exception:
            pass
        self._place(self.pop.winfo_width(), self.pop.winfo_height())
        if self._visible():
            self._start_watch()

    # ------------------------------------------------------------ 显示
    def _show(self, items):
        self.items = items
        if not items:
            self.close()
            return
        pop = self._popup()
        lb = self.listbox
        lb.delete(0, "end")
        for it in items:
            label, _color = KIND_LABEL.get(it["kind"], ("", T.TXT4))
            text = "%-6s %s" % (label, it["text"])
            lb.insert("end", text)
            # 提示放第二段，用灰色 —— Listbox 不支持多色，只能靠分隔符区分
        # 宽度跟着输入框走，但至少 320px：检索框窄的时候候选词会被截断
        w = max(self.entry.winfo_width(), 320)
        h = min(len(items), self.limit) * 24 + 4
        self._place(w, h)
        if not self._alive():
            return
        try:
            pop.deiconify()
            pop.lift()
        except Exception:
            self.close()
            return
        if self not in _OPEN:
            _OPEN.append(self)
        self._start_watch()

    def _refresh(self):
        self._after = None
        try:
            q = self.entry.get()
        except Exception:
            return
        items = autocomplete.suggest(q, limit=self.limit)
        # 完全等于已输入内容时没必要弹（点中候选后重新触发就会这样）
        if len(items) == 1 and items[0]["text"] == q.strip():
            self.close()
            return
        self._active = -1
        self._show(items)

    # ------------------------------------------------------------ 按键
    def _on_keypress(self, event):
        # 输入法组字中（keysym 是 ?? 或空）不弹，否则中文还没上屏就跳英文候选
        ks = (event.keysym or "")
        if ks in ("??", "Unicode", "Process"):
            return
        if event.keysym in ("Down", "Up", "Return", "Escape", "Tab"):
            return
        if self._after:
            try:
                self.entry.after_cancel(self._after)
            except Exception:
                pass
        self._after = self.entry.after(120, self._refresh)

    def _on_click(self, _e):
        # 点进输入框也弹一次（空输入时给热门方向）
        if self._after:
            try:
                self.entry.after_cancel(self._after)
            except Exception:
                pass
        self._after = self.entry.after(60, self._refresh)

    def _on_down(self, _e):
        if not self.items or self.pop is None:
            return None
        self._active = (self._active + 1) % len(self.items)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(self._active)
        self.listbox.see(self._active)
        return "break"

    def _on_up(self, _e):
        if not self.items or self.pop is None:
            return None
        self._active = (self._active - 1) % len(self.items)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(self._active)
        self.listbox.see(self._active)
        return "break"

    def _on_return(self, _e):
        # 没在上/下选中任何一条时，回车要**透传**给原绑定去执行检索
        if self._active < 0 or self._active >= len(self.items):
            self.close()
            return None
        self._commit(self.items[self._active]["text"])
        return "break"

    def _on_escape(self, _e):
        if self.pop is None or not self.items:
            return None
        self.close()
        return "break"

    def _on_focus_out(self, _e):
        # 焦点移到别处就收起；但要等一下，否则点候选的 ButtonRelease 还没到就关了
        self.entry.after(150, self.close)

    def _on_hover(self, _e):
        idx = self.listbox.nearest(_e.y)
        if idx != self._active:
            self._active = idx
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(idx)

    def _on_pick(self, _e):
        idx = self.listbox.nearest(_e.y)
        if 0 <= idx < len(self.items):
            self._commit(self.items[idx]["text"])
        return "break"

    # ------------------------------------------------------------ 提交
    def _commit(self, choice):
        cur = ""
        try:
            cur = self.entry.get()
        except Exception:
            pass
        text = autocomplete.apply_choice(cur, choice)
        self._suppress = True
        try:
            self.entry.delete(0, "end")
            self.entry.insert(0, text)
            self.entry.icursor("end")
        finally:
            self._suppress = False
        self.close()
        if self.on_commit:
            try:
                self.on_commit(text)
            except Exception as exc:
                print("SuggestBox.on_commit 失败:", exc)


def _within(widget, container):
    try:
        w = widget
        while w is not None:
            if str(w) == str(container):
                return True
            w = getattr(w, "master", None)
    except Exception:
        pass
    return False


def _on_global_click(event):
    for box in list(_OPEN):
        if _within(event.widget, box.pop) or event.widget is box.entry:
            continue
        box.close()


def _on_global_wheel(_event):
    close_all()


def _install_global(entry):
    """每个进程只装一次：点空白、滚轮、主窗隐藏时统一收起浮层。"""
    global _GLOBAL_BOUND
    if _GLOBAL_BOUND:
        return
    _GLOBAL_BOUND = True
    try:
        root = entry.winfo_toplevel()
        root.bind_all("<Button-1>", _on_global_click, add="+")
        root.bind_all("<MouseWheel>", _on_global_wheel, add="+")
        root.bind_all("<Button-4>", _on_global_wheel, add="+")
        root.bind_all("<Button-5>", _on_global_wheel, add="+")
        root.bind("<Unmap>", lambda _e: close_all(), add="+")
        root.bind("<Destroy>", lambda _e: close_all(), add="+")
        root.bind("<Configure>", _on_root_configure, add="+")
    except Exception:
        pass


def _on_root_configure(_event):
    # 主窗移动/缩放/最大化后，把还开着的浮层重新贴回输入框下面。
    # 这里不能比较 event.widget 与 winfo_toplevel()：Tk 每次事件都会新建
    # widget 包装对象，`is` 永远不成立，于是最大化后浮层停在旧坐标（截图里
    # 左上角那块就是它）。Configure 只绑在主窗自身上，直接重排即可。
    for box in list(_OPEN):
        if not box._visible():
            continue
        try:
            box._place(box.pop.winfo_width(), box.pop.winfo_height())
        except Exception:
            box.close()


def attach(entry, on_commit=None, limit=8):
    """一行接入：返回 SuggestBox（调用方不用保存也行，Entry 上挂着的就是它）。"""
    box = SuggestBox(entry, on_commit=on_commit, limit=limit)
    try:
        entry._suggest_box = box
    except Exception:
        pass
    return box