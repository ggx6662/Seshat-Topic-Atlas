#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深色主题下的 ttk 控件封装。

Tk 原生 Checkbutton 在 Windows 上使用系统主题绘制，深色背景里会变成白底大方块；
ttk + clam 主题可以完全接管绘制，所以勾选框统一走这里。
"""
import tkinter as tk
from tkinter import ttk

import app_theme as T

_style = None


def init(root):
    """在 App 创建后调用一次，注册深色 checkbox 样式。"""
    global _style
    if _style is not None:
        return _style
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure("Dark.TCheckbutton",
                 background=T.CARD, foreground=T.TXT3,
                 font=T.F(8), borderwidth=0, focusthickness=0,
                 indicatorbackground=T.LINE_SOFT,
                 indicatorforeground=T.TXT3,
                 indicatorrelief="flat",
                 upperbordercolor=T.LINE, lowerbordercolor=T.LINE,
                 background_=T.CARD, padding=(2, 1))
    st.map("Dark.TCheckbutton",
           background=[("active", T.CARD), ("selected", T.CARD)],
           foreground=[("selected", T.TXT), ("active", T.ACCENT)],
           indicatorbackground=[("selected", T.ACCENT_D), ("active", T.ACCENT_D)],
           indicatorforeground=[("selected", T.ACCENT)])
    _style = st
    return st


def check(parent, text, var, command=None, strong=False):
    """深色勾选框。strong=True 时用 ★ 高亮，表示与当前领域强相关。"""
    global _style
    root = parent.winfo_toplevel()
    if _style is None:
        init(root)
    cb = ttk.Checkbutton(parent, text=text, variable=var, command=command,
                         style="Dark.TCheckbutton", takefocus=0)
    if strong:
        cb.configure(style="Dark.TCheckbutton")
    return cb