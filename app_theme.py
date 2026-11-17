#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""选题智库 · 科研选题应用 —— 设计令牌与通用组件。

2026-11 重做：表面全部改成中性灰阶，层级靠亮度台阶 + 1px 描边，不靠投影；
品牌色只给「可点的」和「关键数字」，彩色留给有含义的状态（风险、语义标签、
图表数据）。明暗两套来自同一份 PALETTE，切一次全应用跟着变。

**改色不要改这个文件顶部的常量** —— 它们只是 design_tokens 的别名，
`set_theme_runtime()` 会原地重绑。

组件：
  Card      圆角卡片（用 Canvas 画圆角 + 内部 Frame 承载内容）
  Pill      状态胶囊
  Metric    指标块
  section_title 带标题的分区
  ScrollArea 可滚动容器
  Btn       轻量按钮
"""
import tkinter as tk

# 色彩单一事实来源：design_tokens.COLORS 同时供桌面端、网页端、移动端使用。
try:
    import design_tokens as _DT
    _C = _DT.COLORS
except Exception:                                    # 兜底：令牌文件缺失时用旧值
    _DT = None
    _C = {}

# ---------------------------------------------------------------- 颜色
BG        = _C.get("canvas", "#0b0d10")       # 应用底（近纯黑，内容才浮得起来）
SIDEBAR   = _C.get("surface_nav", "#101216")  # 侧边栏
# **CARD 比 BG 亮一档**（不是同色）。早先让卡片与页面同底、只靠 1px 细线
# 分隔，但深色下那一圈线在满屏卡片上等于「到处都是框」；改成底色差分层，
# 线只作辅助（表格行、真正的分隔），卡片本身默认不画描边。
CARD      = _C.get("surface_card", "#15181c") # 内容区底（比 BG 亮一档）
CARD_HI   = _C.get("surface_raised", "#1d2126")  # 悬浮卡片 / 输入框
OVERLAY   = _C.get("surface_overlay", "#22272d")
LINE      = _C.get("hairline", "#262b31")     # 分隔线（不再默认当卡片描边）
LINE_SOFT = _C.get("hairline_soft", "#1a1e22")

ACCENT    = _C.get("primary", "#2f81f7")      # 主色（唯一品牌色）
ACCENT_HI = _C.get("primary_hover", "#58a6ff")
ACCENT_D  = _C.get("primary_muted", "#1b3a5c")  # 主色暗底
OK        = _C.get("success", "#3fb950")      # 成功 / 正常
WARN      = _C.get("warning", "#d29922")      # 警告
ERR       = _C.get("danger", "#f85149")       # 危险
PURPLE    = _C.get("info", "#a371f7")         # 创新点
ORANGE    = _C.get("orange", "#db6d28")       # 高回报

TXT       = _C.get("ink", "#e8eaed")          # 主文字
TXT2      = _C.get("ink_secondary", "#b9bec5")  # 次要
TXT3      = _C.get("ink_tertiary", "#8c939b")   # 弱（说明性文字）
TXT4      = _C.get("ink_quaternary", "#7d848c")  # 占位/最弱（卡片上 ≥4.5:1）

_NAMES = ("BG", "SIDEBAR", "CARD", "CARD_HI", "OVERLAY", "LINE", "LINE_SOFT",
          "ACCENT", "ACCENT_HI", "ACCENT_D", "OK", "WARN", "ERR", "PURPLE",
          "ORANGE", "TXT", "TXT2", "TXT3", "TXT4")
_KEYS = {"BG": "canvas", "SIDEBAR": "surface_nav", "CARD": "canvas",
         "CARD_HI": "surface_raised", "OVERLAY": "surface_overlay",
         "LINE": "hairline", "LINE_SOFT": "hairline_soft",
         "ACCENT": "primary", "ACCENT_HI": "primary_hover",
         "ACCENT_D": "primary_muted", "OK": "success", "WARN": "warning",
         "ERR": "danger", "PURPLE": "info", "ORANGE": "orange",
         "TXT": "ink", "TXT2": "ink_secondary", "TXT3": "ink_tertiary",
         "TXT4": "ink_quaternary"}

# CARD 取哪个键：两套主题都取 surface_card，也就是「卡片比画布亮一档」。
#   深色 —— 画布 #0b0d10、卡片 #15181c，ΔL 够大，一条线都不用画就能分层；
#   浅色 —— 画布 #f4f5f7、卡片 #ffffff，白卡浮在灰底上同样不需要描边。
# 早先两种主题都取 "canvas"（卡片=画布），只能靠 1px 线区分，整页像到处是框。
_CARD_KEY = {"dark": "surface_card", "light": "surface_card"}

MODE = "dark"        # 当前生效的明暗；由 apply_mode() 改


def refresh_colors(mode=None):
    """把 design_tokens 的当前调色板重新绑到本模块的常量上。

    为什么必须重绑：二十来个页面模块都是 `from app_theme import CARD` 拿的
    值对象（字符串），切主题后它们手里的还是旧字符串。所以窗口重建时先调
    这个函数，再重建控件 —— 不是「热更新已存在的控件」，那样在 Tk 里到处
    漏改，远不如整窗重建可靠。
    """
    g = globals()
    _m = mode or MODE
    for name in _NAMES:
        key = _CARD_KEY.get(_m, _KEYS["CARD"]) if name == "CARD" else _KEYS[name]
        g[name] = _C.get(key, g.get(name))


def apply_mode(mode):
    """切换明/暗。返回实际生效的模式。调用方负责重建界面。"""
    global MODE
    if _DT is None:
        return MODE
    _DT.set_mode(mode)
    MODE = _DT.CURRENT
    # 先落 MODE 再刷新：CARD 取哪个键取决于当前模式，顺序反了就还是旧色。
    refresh_colors()
    return MODE


# ---------------------------------------------------------------- 字体
# 第 12 版：字体改为**运行时按实际安装情况挑选**，不再写死。
#
# 起因：原先写死等线（DengXian），但这台机器上根本没有装等线，
# `Microsoft YaHei`（非 UI 版）和 `SimHei` 也都没有 —— tkfont.families()
# 里只有 `Microsoft YaHei UI` 与 `Noto Sans SC`。Tk 对不存在的字体族
# **不报错、静默回退**，于是字形来自系统默认字体，字号却仍按等线的度量算，
# 笔画发灰、边缘毛糙，这就是「浅色下发虚」的真正来源。
#
# 现在按优先级挑第一个**真实存在**的，全都缺失时用 Tk 自身默认。
FONT_STACK = ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC",
              "Source Han Sans SC", "PingFang SC", "DengXian", "SimHei")
BASE = FONT_STACK[0]      # 由 pick_fonts() 在启动时改写
MONO = "Consolas"


def pick_fonts(root):
    """按实际安装的字体族确定 BASE 与 MONO。

    必须在创建 Tk 根窗口之后、建任何控件之前调用（families() 需要 root）。
    返回 (去掉了虚拟占位符的) 可用字体集合，便于日志排查。
    """
    global BASE, MONO
    try:
        from tkinter import font as _tkfont
        fams = set(_tkfont.families(root))
    except Exception:
        return set()
    # 以 "@" 开头的是竖排字体别名，不是真正的字体族，要排除
    fams = {f for f in fams if not f.startswith("@")}
    for f in FONT_STACK:
        if f in fams:
            BASE = f
            break
    for f in ("Consolas", "Cascadia Mono", "DejaVu Sans Mono",
              "JetBrains Mono", "Segoe UI"):
        if f in fams:
            MONO = f
            break
    return fams

# 字号一律用**像素**（Tk 中负值表示像素），不用 pt。
# 原因：Tk 会把 pt 乘上 tk scaling（本机是 1.333），
# 9pt 被渲染成 17px —— 非整数倍拉伸，笔画落在半个像素上，界面就发虚。
# 用负值直接指定像素高度，字形落在整数像素网格上，清晰锐利。
_SCALE = 1.0        # 由 set_scale() 按系统 DPI 设定


def set_scale(factor):
    """按系统缩放比例调整字号（100% → 1.0，125% → 1.25）。"""
    global _SCALE
    try:
        _SCALE = max(0.85, min(2.0, float(factor)))
    except Exception:
        _SCALE = 1.0


def px(pt):
    """把「设计稿上的 pt 数值」换算成该显示器上的整数像素。

    **最小 12px**：实测 9–11px 的中文在 125% 缩放下笔画粘连，
    是「界面看不清」的主因之一。辅助文字统一不低于 12px。

    系数 1.20（而非 1.34）：1.34 会让 19pt 标题涨到 32px，层级失衡；
    1.20 下正文 16–19px、标题 26px，比例更自然。
    """
    return -max(12, int(round(pt * 1.20 * _SCALE * _FS)))


def dpi_scale():
    """屏幕缩放比例（100% → 1.0，125% → 1.25）。

    **不能读 Tk 的 winfo_fpixels("1i")**：本进程没声明 DPI 感知，
    Tk 报上来的是逻辑 DPI（实测 95.976，即 1.0），而系统实际缩放是
    125%（注册表 AppliedDPI = 120）。用它算位图尺寸会把 32px 的图标
    当成 32 物理像素，实际该给 40。

    所以和 app_main._detect_scale() 一个来源：先读注册表 AppliedDPI，
    再退到 GetDpiForSystem，最后 1.0。
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Control Panel\Desktop\WindowMetrics") as k:
            applied, _ = winreg.QueryValueEx(k, "AppliedDPI")
            return max(1.0, float(applied) / 96.0)
    except Exception:
        pass
    try:
        import ctypes
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi:
            return max(1.0, float(dpi) / 96.0)
    except Exception:
        pass
    return 1.0


def load_bitmap(path, logical_px):
    """把一个 PNG 预缩成「正好等于设备像素」的 Tk 图像。

    **为什么必须自己缩**：Tk 的 `PhotoImage(file=...)` 不做任何重采样 ——
    图多少像素就贴多少像素。125% 缩放下侧栏要 32 逻辑像素 = 40 物理像素，
    直接塞 32px 的图，Tk 会按原始像素摆上去，图形只占方框的 80%，
    看着比旁边的文字小一号；塞 128px 的图又会被裁掉大半。

    所以母图一律做大（logo 用 128px），显示前按 `logical_px * dpi_scale()`
    用 LANCZOS 缩到目标尺寸，得到边缘干净、与文字同高的位图。

    没有 PIL 时退回原文件（略大略小，但不至于没有图标）。
    """
    from pathlib import Path
    p = Path(str(path))
    target = max(8, int(round(float(logical_px) * dpi_scale())))
    try:
        from PIL import Image, ImageTk
        im = Image.open(str(p)).convert("RGBA")
        if im.size != (target, target):
            im = im.resize((target, target), Image.LANCZOS)
        return ImageTk.PhotoImage(im)
    except Exception:
        import tkinter as _tk
        return _tk.PhotoImage(file=str(p))


def wrap(base_px, extra=0):
    """文字换行宽度随字号缩放。

    硬编码 wraplength 在字号放大后会导致文字被截断（如「所自选」）。
    所有用到固定宽度的 Label 都应改用 wrap(设计稿宽度)。

    **注意**：这个函数会**乘以** _SCALE 与字号倍率。它适合「文字变大了，
    换行也该更宽一点」的场景。如果目的是「不要超出这一栏」，不能用它 ——
    容器宽度是固定的，乘完会超出被裁掉（科研方法论右栏就是这么被切的）。
    那种场景用 `fill_wrap()`。

    档位放大后这里会算出超过窗口宽度的值，所以用 `_MAXW` 兜一层：
    `App` 建好后把真实内容宽度写进来。宁可提前折行，也不让文字跑到屏幕外。
    """
    return max(80, min(_MAXW[0], int(round((base_px + extra) * _SCALE * _FS))))


_MAXW = [1 << 20]


def set_maxw(px):
    """告诉 wrap() 内容区实际有多宽（超过它就没有意义了）。"""
    try:
        _MAXW[0] = max(200, int(px))
    except Exception:
        _MAXW[0] = 1 << 20


def fill_wrap(label, pad=24):
    """让一个 Label 的 wraplength 跟随它**实际父容器**的宽度。

    适用场景：文字放在按 grid/pack 分栏的容器里，容器宽度由布局决定、
    不随 DPI 缩放变化；这时用 wrap() 算出来的宽度会超出容器被裁掉。

    **pad 要像真实内边距那样给**：Tk 排版时 Label 会把自己的左右各 padx
    打进去再折行，所以可用宽度是「容器宽 - 2×padx」，而父容器的 <Configure>
    是那个容器的外宽。只按「容器宽 - 一个 pad」留余量不够 —— 期刊会议右栏
    （容器 396、Label 各 padx=6）就出现过一个「准」字被挤到第二行，
    因为 wrap 算出来是 396-8=388，实际只能用 396-12=384。
    所以这里取 `pad + 8` 作为安全余量，代价只是右边缘多留几个像素。
    """
    try:
        owner = label.master
        margin = pad + 8
        def _sync(e=None, _o=owner, _l=label, _m=margin):
            try:
                w = _o.winfo_width()
                if w > 60:
                    _l.configure(wraplength=max(80, w - _m))
            except Exception:
                pass
        owner.bind("<Configure>", _sync, add="+")
        _sync()
        return label
    except Exception:
        return label


def gap(base_px):
    """间距随字号缩放，保持视觉节奏一致。"""
    return max(2, int(round(base_px * _SCALE * _FS)))


# --------------------------------------------------------------- 字号档位
# 面向 20–60 岁的使用者：20 岁的人觉得 15px 刚好，55 岁的人看同字号要凑近。
# 与其让所有人共用一个字号，不如给四档，默认「标准」。
#
# 每一档只影响**字号与随之变化的间距**，不重排布局：档位真把版面挤爆时，
# 页面自己要「让位」（见 ui_parts / 各页的紧凑分支），而不是让字被裁掉。
FONT_STEPS = (
    # (键, 名称, 倍率, 说明)
    ("normal", "标准", 1.00, "设计基准字号（正文 15px）"),
    ("large", "大", 1.15, "正文约 17px，24 英寸屏或 125% 缩放下更舒服"),
    ("xlarge", "特大", 1.30, "正文约 20px，长时间连看几小时不累"),
    ("huge", "超特大", 1.50, "正文约 23px，老花 / 远视 / 坐得离屏幕远"),
)
_FS = 1.00                 # 由 set_font_step() 设定
FONT_STEP = "normal"


def _step_params(key):
    for k, _n, f, _d in FONT_STEPS:
        if k == key:
            return f
    return 1.00


def set_font_step(key):
    """切换字号档位。要在**建控件之前**调用（Tk 没有 CSS 变量）。

    返回实际生效的键；认不出的键退回 normal。
    """
    global _FS, FONT_STEP
    if key not in [s[0] for s in FONT_STEPS]:
        key = "normal"
    FONT_STEP = key
    _FS = _step_params(key)
    return key


def font_step():
    return FONT_STEP


def font_scale():
    """当前字号相对设计基准的倍率（间距、最小尺寸都该乘它）。"""
    return _FS


def sp(base_px):
    """随字号档位缩放的间距（不含系统 DPI —— 那部分已由几何换算处理）。"""
    return max(1, int(round(base_px * _FS)))


def hit_min():
    """最小可点高度。鼠标不是唯一输入方式，手抖、触屏都要求按钮别太小。"""
    return max(30, int(round(30 * _FS)))


# 语义化字号：全部用像素单位，层级固定，避免各页面随手写死字号
SIZE_TITAL = 20       # 页面大标题
SIZE_H1 = 15
SIZE_H2 = 12
SIZE_BODY = 11
SIZE_SMALL = 10
SIZE_TINY = 9


def F(size=10, bold=False):
    """兼容旧写法：把 pt 数值映射到 6 档语义字号。

    历史上各页面随手写了 F(7) 到 F(21) 共 10 种字号，
    没有层级、也不能保证最小可读尺寸。现在统一映射：
        7/8/9   → caption  14px
        10      → body_sm  15px
        11/12   → body     16px
        13/15   → section  18px
        16 以上 → title    22px / display 30px
    """
    if size <= 9:
        base = 14
    elif size == 10:
        base = 15
    elif size <= 12:
        base = 16
    elif size <= 15:
        base = 18
    elif size <= 18:
        base = 22
    else:
        base = 30
    px_size = -max(13, int(round(base * _SCALE * _FS)))
    return (BASE, px_size, "bold") if bold else (BASE, px_size)


def M(size=9, bold=False):
    """等宽字体：只在「需要对齐比较」的地方用（分数、引用量、编号）。"""
    base = 14 if size <= 9 else (15 if size == 10 else 16 if size <= 12 else 18)
    px_size = -max(13, int(round(base * _SCALE * _FS)))
    return (MONO, px_size, "bold") if bold else (MONO, px_size)


# 明确的语义化令牌（新代码优先用这些）
def T_DISPLAY():
    return (BASE, -max(22, int(round(30 * _SCALE * _FS))), "bold")


def T_TITLE():
    return (BASE, -max(18, int(round(22 * _SCALE * _FS))), "bold")


def T_SECTION():
    return (BASE, -max(16, int(round(18 * _SCALE * _FS))), "bold")


def T_BODY():
    return (BASE, -max(16, int(round(16 * _SCALE * _FS))))


def T_BODY_SM():
    return (BASE, -max(15, int(round(15 * _SCALE * _FS))))


def T_CAPTION():
    return (BASE, -max(14, int(round(14 * _SCALE * _FS))))


def T_LABEL():
    return (BASE, -max(14, int(round(14 * _SCALE * _FS))), "bold")


def T_METRIC(bold=True):
    size = -max(20, int(round(26 * _SCALE * _FS)))
    return (MONO, size, "bold") if bold else (MONO, size)


# ---------------------------------------------------------------- 尺寸
PAD      = 16
# 2026-11 第 7 版：参考图（运维控制台）用 12px 圆角。
# 6 太方正像老式 Windows 控件，10 又像气泡；12 是「现代控制台」的手感。
RADIUS   = 12
# 侧栏从 216 收到 200：参考图的侧栏是窄柱，条目只有一行字 + 一个小圆点。
# 留 200 刚好放下最长的「科研方法论」五个字（15px 约 75px）+ 圆点 + 内边距。
SIDEBAR_W = 200

TITLE_MAIN = ("知识库助手", "选题智库")


# ================================================================ 组件
def hex_to_rgb(c):
    c = (c or "#000000").lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(t):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in t)


def mix(fg, bg, ratio):
    """把 fg 按 ratio 混进 bg（0=纯 bg，1=纯 fg）。用来做「同色系浅底」。"""
    a, b = hex_to_rgb(fg), hex_to_rgb(bg)
    return rgb_to_hex([a[i] * ratio + b[i] * (1 - ratio) for i in range(3)])


def tint(color, ratio=0.16, bg=None):
    """同色系浅底：标签、胶囊用。深色模式下把颜色压暗铺底。"""
    return mix(color, bg or CARD, ratio)


class _Themed(object):
    """记下自己用过的颜色，切主题时按语义重算，而不是猜。"""
    def _remember(self, **kw):
        self._theme_map = dict(kw)

    def _restyle(self):
        m = getattr(self, "_theme_map", None)
        if not m:
            return
        args = {}
        for opt, (color, kind) in m.items():
            args[opt] = _resolve(color, kind)
        try:
            self.configure(**args)
        except Exception:
            pass


_BG_KINDS = {"canvas": BG, "card": CARD, "raised": CARD_HI}


def _resolve(color, kind):
    """kind 用于「以谁为底做混合」：tint:x 表示与 x 混 16%。"""
    if kind and kind.startswith("tint:"):
        base = _BG_KINDS.get(kind[5:], CARD)
        return tint(color, 0.16, base)
    return color

# ================================================================ 组件
class Card(tk.Frame):
    """真正的圆角卡片：外层 Canvas 画带描边的圆角，内部 Frame 放内容。

    用法：
        c = Card(parent)
        c.pack(fill="x")
        tk.Label(c.body, text="hi").pack()
    """

    def __init__(self, parent, bg=None, border=None, radius=None, pad=0, height=None,
                 fill_y=None, stretch=False, **kw):
        """stretch：让卡片宽度跟随父容器给的宽度，而不是报 1px 最小宽。

        默认 False（canvas.config(width=1)），因为大多数页面把卡片放在
        按比例分配的 grid 列里，报真实请求宽度会把窗口撑大（2026-11-14
        文献库 5 张指标卡把窗口顶到 1962px 那次）。但在 `pack(fill="x")`
        的场景（总览卡片流）里，1px 请求宽度会让四列卡片的圆角按不同的
        settle 时机画，出现「有的卡齐边、有的卡斜边」。
        """
        wkw = kw.pop("width", None)
        # 关键：默认值必须在**建控件时**从模块全局取，不能写进函数签名。
        # 写成 `bg=CARD, border=LINE` 的话，这两个字符串在 import 时就绑定死了，
        # 之后 apply_mode("light") 只改了模块变量，旧卡片仍拿着深色的 LINE，
        # 浅色主题下就是一圈 #30363d 的黑框（2026-11-15 用户反馈的真 bug）。
        if bg is None:
            bg = CARD
        if border is None:
            border = LINE
        if radius is None:
            radius = RADIUS
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0)
        # 显式 width 用于 grid 里会被「按内容收缩」的场景（默认 1，见下）
        if wkw is not None:
            self.config(width=wkw)
        self.is_card = True
        # 记住「是不是用默认色建的」：切主题重建窗口时新控件会拿到新默认值，
        # 但同一窗口内若中途改了调色板（测试或预览），旧控件仍拿着旧字符串，
        # 这里至少让 Card 自己的底色能跟着 BG 走。
        self._bg_default = bg is CARD
        self._bg_at_build = bg
        self.bg_color = bg
        self.border = border
        self.radius = radius
        self._fixed_h = height
        # fill_y：卡片高度是否由外部（grid sticky=ns / pack expand）决定。
        # None = 交给后面 pack()/grid() 的调用方式推断（原有行为）；
        # 显式 False 用于「卡片装在 sticky=new 的格子里」——那时
        # 外层 Frame 的高度来自 Canvas 的请求高度，而 Canvas 又按 body
        # 请求高度算，两边互为因果，卡片会停在 1px 高（真踩过）。
        self._fill_y = bool(fill_y) if fill_y is not None else False
        self._fill_y_pinned = fill_y is not None
        self._syncing = False
        self._jit = None
        self._last_h = None
        self._last_size = None
        # 宽度 / 高度分开记：拖窗口时宽度每帧都变，但高度往往不变。
        # 合成一个 _last_size 会导致每帧都改 body 高度、重建圆角形状（见 _sync）。
        self._last_w = None
        self._last_h_px = None
        self._stretch = bool(stretch)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        if wkw is None and not self._stretch:
            # Frame 的请求宽度默认是 1px。在 pack 里无所谓（fill/handle 决定），
            # 但在 grid 的按比例列里，Tk 会按「请求宽度」分配，卡片就被压成
            # 一条细线 —— 真踩过。1px 的请求宽度不影响任何已有布局，
            # 却能让 grid 正常按列分配。
            self.config(width=1)
        self.canvas.pack(fill="both", expand=True)
        # Canvas 还要单独压住请求宽度：Frame 默认 width=1 只代表 Frame 自己，
        # Canvas 会按**内部窗口**的请求宽度上报（body 有多宽它就多宽）。
        # 2026-11-14 实测：文献库 5 个指标卡各报 378px，把窗口撑到 1962px，
        # 右边半屏被推出屏幕外 —— 实测每张卡的计算列宽只有 218px。
        # 高度仍由 _sync 主动设置，这里只管宽度。
        if not self._stretch:
            self.canvas.config(width=1)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(pad, pad, anchor="nw", window=self.body)
        self._pad = pad
        self._shape = None
        self.body.bind("<Configure>", self._request_sync)
        self.canvas.bind("<Configure>", self._request_sync)
        # Card 自身（外层 Frame）变高变宽时也必须重新同步 —— 之前只监听
        # body 和 canvas，而 grid sticky="nsew" 拉伸的正是外层 Frame，
        # canvas 被撑高后 _sync 又会把 canvas 改回内容高度，两头打架。
        self.bind("<Configure>", self._request_sync)
        # 首次真正显示到屏幕上时补一次强制结算：pack/grid 的分配发生在
        # 创建之后，而 <Configure> 走 180ms 防抖，卡片可能整个生命周期
        # 都停在首帧那个 1px 形状上（总览卡片流就是这个现象）。
        self._booted = False
        self.bind("<Map>", self._on_map)

    def _on_map(self, _e=None):
        if self._booted:
            return
        self._booted = True
        # 用 after_idle 而不是 after(24)：卡片刚被 map 出来时尺寸已经是
        # 最终值，只需要等这一轮 idle 把布局算完就能结算。after(24) 会在
        # 每次 update() 都被后续 Configure 顶掉（见 _request_sync 的防抖）。
        self.after_idle(self.sync_now)

    def _request_sync(self, _e=None):
        """Configure 会连环触发，改尺寸又会引起新的 Configure。

        2026-11-15 缩放卡顿（实测 483ms/帧 → 124ms/帧）：拖动窗口时
        <Configure> 每帧都来，卡片里的换行文字跟着重排，body 请求高度在
        394/298/271 之间来回跳，每次改高度又要让 130 多个控件重新布局。

        现在的策略是**防抖**而不是节流：
          - 每来一个 Configure 就把计时器往后推（180ms 静默才真正结算）；
          - 期间不做任何几何计算，连圆角都不重画 —— 重画圆角要删一组
            多边形再建一组，拖动时画面本来就在变，肉眼看不出圆角是旧的；
          - 松手后一次性把高度、宽度、圆角和 body 尺寸全部定稿。
        15:39 之前的版本是 after(16) 节流，拖动时每 16ms 就结算一次，
        等于每帧都付一遍重新布局的钱。sync_now() 仍可强制立刻结算，
        「点开二维码」这类由代码主动触发的高度变化不受影响。
        """
        if self._jit:
            try:
                self.after_cancel(self._jit)
            except Exception:
                pass
        # 兜底：形状一次都没画过时不能等 180ms —— 卡片在密集布局（总览
        # 卡片流一次建 10 张）里 Configure 持续不断，180ms 静默期永远到不来，
        # 结果就是整张卡没有圆角、宽度还停在 body 请求宽度上。给首帧 16ms。
        self._jit = self.after(16 if self._shape is None else 180,
                               self._run_settle)

    def _run_sync(self):
        self._jit = None
        try:
            self._sync()
        except Exception:
            pass

    def _run_settle(self):
        """拖动结束后的一次性定稿：这时尺寸已稳定，改高度不会再引起连锁重排。"""
        self._jit = None
        try:
            self._sync(settle=True)
        except Exception:
            pass

    def sync_now(self):
        """立即按当前 body 请求高度重算卡片高度，跳过那层 16ms 防抖。

        为什么需要：`_sync` 平时靠 body/canvas/自身的 Configure 事件触发，
        但**用 pack/pack_forget 往 body 里加控件时，body 的实际高度不一定变**
        （父容器先按旧尺寸分配），Configure 就不触发 —— 卡片永远停在旧高度，
        新加的内容被画到卡片外看不见。
        2026-11-13 实测：设置页点开「显示二维码」，body 请求高度 184→410，
        Card 一直是 212，二维码整体落在卡片下方被裁掉。
        调用方在改完 body 内容后主动调一次即可。
        """
        if self._jit:
            try:
                self.after_cancel(self._jit)
            except Exception:
                pass
            self._jit = None
        try:
            self._sync()
        except Exception:
            pass

    def destroy(self):
        """取消挂起的定时器，否则窗口销毁后 after 回调会报
        invalid command name "…_run_sync"。"""
        try:
            if self._jit:
                self.after_cancel(self._jit)
                self._jit = None
        except Exception:
            pass
        super().destroy()

    def _sync(self, settle=False):
        if getattr(self, "_syncing", False):
            return
        # settle=False：拖动窗口时的中间帧 —— 只重绘圆角，**不动高度**。
        # 拖动时卡片里的换行文字每帧都在重排，此时去读 body 的请求高度并
        # 写回去，等于每帧都让整棵子树重新布局一遍（实测一帧 230ms）。
        # settle=True：180ms 内没有新事件（用户松手了）才真正定稿高度。
        # 切主题后（同一窗口）旧卡片还拿着旧颜色字符串，卡片底色跟着 CARD 走。
        # 不能只判“默认色”：page_venue 等页显式传了 LINE 做描边，底色以 CARD/NavArea 的形式进来；
        # 它们在浅色下也应该是白底。只管“底色与当前 BG/CARD 都不一致”的情况。
        stale = getattr(self, "_bg_at_build", None)
        if stale is not None and self.bg_color == stale and stale != CARD:
            self.bg_color = CARD
            for w in (self, self.canvas, self.body):
                try:
                    w.configure(bg=CARD)
                except Exception:
                    pass
        self._syncing = True
        try:
            # self（Card 外层 Frame）的高度由 grid/pack 决定；canvas 是它的子控件，
            # 只要把 canvas 设成同样高度就能铺满，不再反过来影响布局 —— 单向，安全。
            box_w = self.winfo_width()
            box_h = self.winfo_height()
            # 取两者较大值：首帧 pack 还没分配时 box_w 是 1，而 canvas 已经
            # 拿到 parent 给的宽度（或反过来）。原来二选一会漏掉后到的那一个，
            # 总览卡片流里的卡片就停在 1px 宽，只剩一条竖边（2026-11-15 实测）。
            cur_w = max(box_w, self.canvas.winfo_width())
            if self._fill_y and box_h > 1:
                h = box_h
            elif settle or self._last_h_px is None:
                h = self.body.winfo_reqheight() + self._pad * 2
            else:
                # 中间帧：沿用上次定稿的高度，不去读 reqheight（读它不贵，
                # 贵的是随后把新高度写进 canvas/body 引起的连锁重排）。
                h = self._last_h_px
            if self._fixed_h:
                h = self._fixed_h
            # 横向宽度**只由父容器决定**，不跟随 body 的请求宽度。
            # 原来写的是 max(cur_w, body请求宽度+pad*2)：canvas 只会变宽、
            # 不会变窄，一旦 body 里放了个请求宽度偏大的控件（图表按最长
            # 标签实测出 378px），canvas 就撑到 378 —— 而卡片本身只有 360，
            # 内容直接伸出卡片右缘被裁掉，数字整列看不见。
            # 纵向仍然按内容走（见下面 h 的计算），文字多的卡照样会变高。
            if cur_w > 1:
                w = cur_w
            else:
                w = max(1, self.body.winfo_reqwidth() + self._pad * 2)
            h = max(h, 1)
            if str(h) != self._last_h and (settle or self._fill_y):
                self._last_h = str(h)
                # 拖动中间帧（settle=False）不写高度：这两个 configure 会改变
                # Card 外层 Frame 的尺寸，父容器随即重排所有兄弟控件，
                # 一帧 230ms 基本都花在这里。等松手后由 _run_settle 一次定稿。
                self.canvas.configure(height=h)
                # Card 这个外层 Frame 自己也要跟着变高，否则 pack 仍按旧请求
                # 高度分配，canvas 撑大了但外层没长——内容被裁在卡片外。
                # 2026-11-13 实测：设置页点开「显示二维码」后 body 请求高度
                # 从 184 涨到 410，Card 却一直停在 212，二维码被画在卡片下方看不见。
                # 只在「非 fill_y」时设：fill_y 时高度由父容器决定，反过来设会把布局顶坏。
                if not self._fill_y:
                    try:
                        if str(self.cget("height")) != str(h):
                            self.configure(height=h)
                    except Exception:
                        pass
            # 2026-11-15 缩放卡顿：窗口一拖，w 每帧都在变，所以 `_last_size != (w, h)`
            # 每帧都为真，于是每帧都要 itemconfigure 宽度 + 改 body 高度 +
            # 删了圆角形状再重画一遍。改 body 高度又会触发 body 的 <Configure>，
            # 回头再叫 _request_sync —— 一帧 236ms，其中约 170ms 花在这条链上。
            # 拆成三把锁：宽度变了只改窗口宽度；高度变了才动 body 高度；形状只在宽度变了才重画。
            win_w = max(1, w - self._pad * 2)
            if self._last_w != win_w:
                self._last_w = win_w
                self.canvas.itemconfigure(self._win, width=win_w)
            if self._last_h_px != h:
                # 拖动中间帧（settle=False）只记数、不真写：一旦在这里把
                # _last_h_px 更新掉，松手后 _run_settle 会以为「高度没变」而跳过，
                # 卡片高度就永远停在拖动开始时的旧值（真踩过：settle 前后
                # last_h 394->394 纹丝不动，因为缓存早就被中间帧写掉了）。
                if not (settle or self._fill_y):
                    return
                self._last_h_px = h
                # 纵向填充时，内部 body 也要铺满，否则里面的滚动区拿不到高度。
                # **注意**：canvas 窗口的 height 只在窗口没有自身请求尺寸时
                # 才起作用；body 里只要有内容，create_window 的 height 就被
                # 内容高度覆盖（实测 card 高 700，body 仍 23px）。
                # 所以必须先给 body 一个显式 geometry 高度，窗口才会照做。
                if self._fill_y:
                    bh = max(1, h - self._pad * 2)
                    self.canvas.itemconfigure(self._win, height=bh)
                    self.body.config(height=bh)
                else:
                    self.canvas.itemconfigure(self._win, height=0)
                    self.body.config(height=0)
            if self._last_size != (w, h):
                self._last_size = (w, h)
                if self._shape:
                    for _i in (self._shape if isinstance(self._shape, (list, tuple))
                               else [self._shape]):
                        self.canvas.delete(_i)
                # 2026-11-15 第二次重做：浅色主题下**不画描边**，靠底色分层。
                # 用户反馈「重做的边框太丑了」—— 之前的双多边形方案虽然四边
                # 都画出来了，但光滑多边形被 Tk 反锯齿后占 2 行设备像素，
                # 一整圈就是 2px 的中灰框，在 125% 缩放下更糊。
                # 规则抽到 card_outline()：浅色返回 None（只填充），深色返回描边色。
                edge = card_outline(self.border, self.bg_color)
                self._shape = _round_rect(self.canvas, 0, 0, w, h, self.radius,
                                          fill=self.bg_color, outline=edge,
                                          width=1)
                # 形状可能是一组（外圈 + 内圈），全部压到底层
                if isinstance(self._shape, (list, tuple)):
                    for _i in self._shape:
                        self.canvas.tag_lower(_i)
                else:
                    self.canvas.tag_lower(self._shape)
        finally:
            self._syncing = False

    def pack(self, **kw):
        if not self._fill_y_pinned:
            self._fill_y = bool(kw.get("expand")) or str(kw.get("fill", "")).find("both") >= 0
        return super().pack(**kw)

    def grid(self, **kw):
        if not self._fill_y_pinned:
            self._fill_y = kw.get("sticky") in ("nsew", "ns", "nesw", "nswe")
        return super().grid(**kw)


def card_edge(border=None, bg=None):
    """描边色。2026-11-15 第二次重做：**浅色主题下不再画描边**。

    原因：Canvas 上的光滑多边形会被 Tk 反锯齿，1px 的线实际占 2 行设备像素，
    两条边叠起来就是一整圈 2px 的中灰框 —— 用户的原话是「重做的边框太丑了」。
    在 125% 缩放下这个效果只会更明显，因为它永远落在半像素上。

    现在的分层策略不靠线，靠底色：
      浅色：页面白底 → 卡片 #fbfbfc（几乎看不出的暖白），靠色差而不是靠框；
      深色：卡片 #1c1d1f 比画布 #17181a 亮一档，本来就不需要线。

    两张卡挨着放时（首页左右两栏）会露出 1px 的间隙，页底色进来正好当分隔。
    需要「框住」的地方（输入框、表头）仍用 fix_highlight，那是原生控件画的，
    直角、单像素、不带反锯齿。
    """
    b = border if border is not None else LINE
    g = bg if bg is not None else CARD
    if MODE == "dark":
        return b
    return mix(b, g, 0.25)


def card_outline(border=None, bg=None):
    """卡片描边色；不需要描边时返回 None。

    深色：不画。第 7 版起深色的层级由底色台阶承担（canvas #0b0d10 <
    nav #101216 < card #15181c < raised #1d2126），台阶拉得够开，多张卡并排
    也不会糊成一片；再画 1px 就是用户反复说的「到处是黑框」。

    **浅色也不再画（第 13 版）**。原以为浅色白卡需要一圈细线才不「融进底色」，
    但 `_round_rect` 是把描边拆成「外圈色多边形 + 内圈填充多边形」两块**实心**
    形状画的，Tk 反锯齿让外圈实际占 2 行设备像素；125% 缩放下再糊一层，
    效果不是「细线」而是**一整块中灰的厚框**（用户反馈的「边框像灰块」）。
    实测截图像素：卡边从 x=216 起连续整片 (220,222,228)。

    现在浅色同样靠底色分层：画布已压到 #eff0f3、卡片是 #ffffff，
    亮度差约 7%，边界本来就看得出来，不需要线来补。
    `border=` 显式传入的（输入框、表头）仍照旧画。
    """
    if MODE == "dark":
        return None
    # 2026-11-15 第三次修正：这里**曾经**写成 `return border or None`，
    # 想保留「显式传 border 的调用方仍画框」。但 Card.__init__ 的默认值
    # 就是 border=LINE，等于所有没显式指定 border 的卡片都会走进那条分支，
    # 于是浅色下照样画出外圈灰多边形。
    # 实测证据（_tmp_findbox2.py）：卡 Canvas 里有两个多边形，
    #   内圈 fill=#ffffff bbox=(1,1)-(326,134)
    #   外圈 fill=#dcdee4 bbox=(-1,-1)-(328,136)
    # 外圈每边比内圈多 1 个**逻辑**像素，125% 缩放下放大成 2–3 个设备像素，
    # 再经 smooth=True 抗锯齿扩散，最终在屏幕上就是一圈约 10px 的灰带。
    # 所以浅色一律不画，没有例外；需要「框住」的控件请用 fix_highlight()。
    return None


def fix_highlight(widget, color):
    """给 tk.Frame/Entry 这类控件设描边时**必须同时设 highlightcolor**。

    这是 Windows 上一个很容易漏的坑：`highlightthickness=1` 时，
    没聚焦的控件用 `highlightbackground`，但 Tk 的默认 `highlightcolor`
    是系统色名 `SystemWindowFrame`，在浅色主题下渲染成一条 (217,223,229)
    的实心灰线，**和任何主题色都对不上**（2026-11-15 用户反馈的「黑框」，
    实际就是它 + 卡片自身描边叠出来的双线，不是 Card 画的）。
    把两者设成同一个颜色，聚焦态就不会突变。
    """
    try:
        widget.configure(highlightbackground=color, highlightcolor=color,
                         highlightthickness=1)
    except Exception:
        pass
    return widget


def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """圆角矩形：拆成「外圈描边色」+「内圈填充色」两个实心多边形。

    为什么不用 `create_polygon(width=1, outline=...)`：Tk 把描边**居中画在
    路径两侧**，而路径正好压在坐标 0 和 w 上，靠外那半个像素直接落到画布外。
    2026-11-15 实测：浅色卡片顶边第 0/1 行是纯白 255，右边却有 182 灰线
    —— 上下左边整圈没画出来，只剩一侧，看着就是「框残缺 / 一道黑框」。
    改成两个实心形状后，边框宽度完全落在画布内，任何主题、任何尺寸都对。
    """
    fill = kw.get("fill")
    outline = kw.get("outline")
    width = max(1.0, float(kw.get("width") or 1))
    if not outline or outline == fill:
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return [canvas.create_polygon(pts, smooth=True, fill=fill,
                                      outline=fill, width=0)]
    # 外圈从「画布外 1px」开始画，保证上下左右四条边都完整落在画布内：
    # 若从 0 开始，Tk 的光滑多边形会把边缘压在半像素上，反锯齿后与背景同色。
    o1x, o1y, o2x, o2y = x1 - 1, y1 - 1, x2 + 1, y2 + 1
    outer = [o1x + r, o1y, o2x - r, o1y, o2x, o1y, o2x, o1y + r, o2x, o2y - r,
             o2x, o2y, o2x - r, o2y, o1x + r, o2y, o1x, o2y, o1x, o2y - r,
             o1x, o1y + r, o1x, o1y]
    # 内圈整体往里收 1px：这样第 0 行/列保留的是外圈色。
    ix1, iy1 = x1 + width, y1 + width
    ix2, iy2 = x2 - width, y2 - width
    ir = max(0.5, r - width)
    inner = [ix1 + ir, iy1, ix2 - ir, iy1, ix2, iy1, ix2, iy1 + ir, ix2, iy2 - ir,
             ix2, iy2, ix2 - ir, iy2, ix1 + ir, iy2, ix1, iy2, ix1, iy2 - ir,
             ix1, iy1 + ir, ix1, iy1]
    ids = [canvas.create_polygon(outer, smooth=True, fill=outline,
                                 outline=outline, width=0)]
    if fill:
        ids.append(canvas.create_polygon(inner, smooth=True, fill=fill,
                                         outline=fill, width=0))
    return ids


def Pill(parent, text, color=ACCENT, bg=None, small=True):
    """状态标签。同色系浅底 + 该色文字，1px 同色描边（GitHub 的 label 做法）。"""
    base = bg or CARD_HI
    fill = tint(color, 0.18, base)
    return tk.Label(parent, text=text, bg=fill, fg=color,
                    font=F(8), padx=7, pady=1, bd=0, highlightthickness=0)


class Metric(tk.Frame):
    def __init__(self, parent, label, value="—", color=None, unit="", hint=""):
        # 同上：默认色不能在签名里绑定，否则切主题后还是旧字符串。
        if color is None:
            color = ACCENT
        super().__init__(parent, bg=CARD)
        self.lbl = tk.Label(self, text=label, bg=CARD, fg=TXT3, font=F(9), anchor="w")
        self.lbl.pack(fill="x")
        row = tk.Frame(self, bg=CARD)
        row.pack(fill="x")
        self.val = tk.Label(row, text=value, bg=CARD, fg=color,
                            font=T_METRIC(), anchor="w")
        self.val.pack(side="left")
        self.unit = tk.Label(row, text=(" " + unit) if unit else "", bg=CARD,
                             fg=TXT3, font=F(9), anchor="w")
        self.unit.pack(side="left", pady=(6, 0))
        self.hint = tk.Label(self, text=hint, bg=CARD, fg=TXT4, font=F(8),
                             anchor="w", justify="left")
        # 说明文字限宽：不限的话 5 个指标排一行时，最长的「说明」决定整窗最小宽度
        # （实测文献库指标条把窗口撑到 1962px，右半屏被推出屏幕）。
        self.hint.pack(fill="x")
        self._hint_wrap = 0
        self.bind("<Configure>", self._fit_hint, add="+")

    def _fit_hint(self, ev=None):
        w = max(120, (ev.width if ev is not None else self.winfo_width()) - 8)
        if abs(w - self._hint_wrap) < 8:
            return
        self._hint_wrap = w
        try:
            self.hint.config(wraplength=w)
        except Exception:
            pass

    def set(self, value, hint=None, color=None):
        self.val.config(text=str(value))
        if hint is not None:
            self.hint.config(text=hint)
        if color:
            self.val.config(fg=color)


class ScrollArea(tk.Frame):
    """竖向滚动区。内容放在 .inner 里，宽度自动跟随。

    注意：Canvas 不会因为父容器变大而自动变高，所以这里监听父容器尺寸，
    主动让内部窗口至少铺满可视区域 —— 否则父容器撑开后下方会留一块空白。
    """

    def __init__(self, parent, bg=None, height=1):
        # 同上：不能把 BG 写进签名，否则切主题后滚动区还是旧底色。
        # height：可视高度的下限（px）。默认 1 = 完全由 pack/grid 决定，
        # 行为和以前一样；不给父容器撑高的场合（卡片 fill_y=False）必须显式传，
        # 否则 Canvas 请求高度是 1px，内容会被压成一条线。
        if bg is None:
            bg = BG
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, height=height)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                width=8, bd=0, relief="flat",
                                troughcolor=bg, bg=LINE_SOFT, activebackground=ACCENT_D)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        # 长列表（ui_parts.LazyList）接管滚动条后设成自己；
        # 接管期间不能再由 _fit_height / _update_region 覆盖 scrollregion。
        self._lazy = None
        # 滚动条默认不显示：Windows 的 tk.Scrollbar 是系统原生控件，bg 只能改槽，
        # 那根白色滑块（约 8×30px）盖在深色卡片上极其显眼且无法透明化。
        # 改成「鼠标进入才出现」：不占常驻空间，也不会让内容宽度随时抖动。
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.inner)
        self._bind_wheel(self.vsb)
        self._bg_at_build = bg
        self._bg_palette_at_build = BG
        self.bind("<Configure>", self._sync_theme, add="+")

    def _sync_theme(self, _e=None):
        """同一窗口内切了调色板（测试/预览）时，拿着旧字符串的滚动区会留下一整块深色背景。
        正常路径（app_main.apply_theme）是整窗重建，不会走到这；这里只做兜底。

        判断依据必须是「调色板里的 BG 变了没有」，不能用「bg 是不是等于 BG」：
        page_topic / page_ideas 等页面显式传 `bg=T.CARD`（卡片内滚动区），
        那样 stale 永远 != BG，<Configure> 一触发就把整块刷成画布色，
        在卡片中间挖出一个更暗的矩形 —— 2026-11-15 实测就是这个。
        """
        stale = getattr(self, "_bg_at_build", None)
        old_palette_bg = getattr(self, "_bg_palette_at_build", None)
        if stale is None or old_palette_bg == BG:
            return
        # 调色板换了：只有当初用的是「旧调色板的 BG」才跟着换，
        # 否则（显式给了 CARD 等）说明调用方有自己的底色，原样保留。
        follow = (stale == old_palette_bg)
        self._bg_palette_at_build = BG
        self._bg_at_build = BG if follow else stale
        if not follow:
            return
        for w in (self, self.canvas, self.inner, self.vsb):
            try:
                w.configure(bg=BG)
            except Exception:
                pass
        try:
            self.vsb.configure(troughcolor=BG)
        except Exception:
            pass

    def _bind_wheel(self, w):
        w.bind("<Enter>", self._enter, add="+")
        w.bind("<Leave>", self._leave, add="+")

    def _enter(self, _e=None):
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self._sync_scrollbar(True)

    def _leave(self, _e=None):
        self.canvas.unbind_all("<MouseWheel>")
        self._sync_scrollbar(False)

    def _sync_scrollbar(self, want_show):
        """内容真的溢出时才把滚动条挂出来，且只在鼠标悬停期间挂。"""
        try:
            vis = self.canvas.winfo_height()
            req = self.inner.winfo_reqheight()
            show = bool(want_show) and req > vis + 4 and vis > 20
            shown = bool(self.vsb.winfo_manager())
            if show and not shown:
                self.vsb.pack(side="right", fill="y")
            elif not show and shown:
                self.vsb.pack_forget()
        except Exception:
            pass

    def _wheel(self, e):
        try:
            if self.canvas.bbox("all") and \
                    self.canvas.bbox("all")[3] <= self.canvas.winfo_height():
                return
            self.canvas.yview_scroll(int(-e.delta / 120), "units")
        except Exception:
            pass

    def _on_inner(self, _e=None):
        self._update_region()

    def _update_region(self):
        """按 inner 的真实请求高度更新滚动区。

        为什么不用 `bbox("all")`：内容全由 pack 布局时，inner 自己会被
        压成可视高度，bbox 就只有一个空框 —— **多出来的内容滚不到**，
        看起来像「卡片只画了第一张」。这里直接用 reqheight 算。
        """
        try:
            if getattr(self, "_lazy", None) is not None:
                self._lazy.fill()
                return
            vis = self.canvas.winfo_height()
            req = self.inner.winfo_reqheight()
            self.canvas.configure(
                scrollregion=(0, 0, self.canvas.winfo_width(), max(vis, req, 1)))
        except Exception:
            pass

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=max(1, e.width))
        self._fit_height()

    def _fit_height(self):
        """内容不足一屏时撑满可视高度；超过一屏时保持自身高度并允许滚动。

        只能在 Canvas 尺寸变化时调用。**不要**在 inner 的 Configure 里调用，
        否则改高度→触发 Configure→再改高度会形成死循环（曾经真的卡死过）。
        """
        try:
            vis = self.canvas.winfo_height()
            req = self.inner.winfo_reqheight()
            want = max(vis, 1) if req <= vis else 0
            cur = int(float(self.canvas.itemcget(self._win, "height") or 0))
            if cur != want:
                self.canvas.itemconfigure(self._win, height=want)
            if getattr(self, "_lazy", None) is not None:
                self._lazy.fill()
            else:
                self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(),
                                                    max(vis, req, 1)))
        except Exception:
            pass

    def pack(self, **kw):
        """纵向填满时让 Canvas 跟随父容器高度。

        **不要**用 bind("<Configure>") 去改 Canvas 尺寸：那会与 pack 传播
        互相触发，Tk 在主循环里打转，表现为 update() 永不返回（真卡死过）。
        正确做法是把 ScrollArea 自身尺寸交给 pack，Canvas 走 fill="both"。
        """
        return super().pack(**kw)

    def grid(self, **kw):
        return super().grid(**kw)

    def clear(self):
        # 先一次拿走所有子控件、再逐个 destroy：原来边遍历边 destroy，
        # 每 destroy 一个 Tk 都要重排一次几何，252 行时这一句独占 0.38 秒。
        kids = list(self.inner.winfo_children())
        for w in kids:
            try:
                w.pack_forget()
            except Exception:
                pass
        for w in kids:
            try:
                w.destroy()
            except Exception:
                pass
        self._fit_height()

    def refresh(self, defer=False):
        """内容重建后调用，让滚动区重新测量高度。

        Tk 的 Canvas 不会因为内部 Frame 变高就自动撑开，
        必须显式更新 scrollregion 和内部窗口高度，否则新加的内容会挤在底部看不见。

        defer=True 时把测量推迟到空闲：批量添加几十个控件时，
        每次都立即测量会反复触发布局，反而更慢。
        """
        try:
            if defer:
                if getattr(self, "_refresh_job", None):
                    return
                def run():
                    self._refresh_job = None
                    self.refresh()
                self._refresh_job = self.after(40, run)
                return
            self._refresh_job = None
            if getattr(self, "_lazy", None) is not None:
                self._lazy.fill()
                return
            # 不调 update_idletasks()：它会强制同步完成所有子控件的布局，
            # 一次加了 80 行时这一句就占掉大半时间。
            # 直接更新 scrollregion，后续 Configure 事件会自然完成测量。
            self._update_region()
            self.after(30, self._update_region)
        except Exception:
            pass

    def scroll_to_top(self):
        self.canvas.yview_moveto(0)


def hsep(parent, color=LINE, pad=(0, 0)):
    f = tk.Frame(parent, bg=color, height=1)
    f.pack(fill="x", pady=pad)
    return f


def section_title(parent, text, sub="", color=TXT):
    """区块标题。GitHub 的 section header：粗体一行 + 右侧弱色说明，下面一条细线。"""
    bg = parent.cget("bg")
    box = tk.Frame(parent, bg=bg)
    box.pack(fill="x", pady=(0, 6))
    tk.Label(box, text=text, bg=bg, fg=color,
             font=F(10, True), anchor="w").pack(side="left")
    if sub:
        tk.Label(box, text=sub, bg=bg, fg=TXT4,
                 font=F(8), anchor="w").pack(side="right", pady=(2, 0))
    return box


def resync(widget):
    """某个控件里加减了内容之后，通知外层容器重新量一次高度。

    Card 的高度靠 body 的 Configure 事件驱动 —— pack/pack_forget 往里加减
    控件时 body 自身的尺寸不一定变，Configure 就不触发，卡片会停在旧高度，
    新加的内容被裁掉（第 6 版二维码就栽在这上面）。
    这里一路向上找到最近的 Card / ScrollArea 并强制同步。
    """
    w = widget
    for _ in range(24):
        if w is None:
            break
        try:
            if getattr(w, "is_card", False):
                w.sync_now()
            elif w.__class__.__name__ == "ScrollArea":
                w.refresh()
        except Exception:
            pass
        try:
            w = w.master
        except Exception:
            break


def para(parent, text, color=None, font=None, wrap_px=700, bg=None, pady=(0, 0),
         padx=0):
    """一段多行说明文字：自动换行 + 统一行距。

    为什么单独做成函数：Tk 的 `Label` 没有行高选项，中文字形本身占满
    em 框，几行叠在一起时默认行距只有 1.0 倍 —— 密集段落看起来像糊成
    一块。这里用「容器 Frame + 按显示宽度切成多行 Label」来换行，每个
    Label 自己带 `pady=(0,3)`，等效于 1.25 倍行距。

    另一个坑（踩过）：Tk 在 text 里**有 `\\n` 但没设 wraplength** 时，
    按最长那行的自然宽度算请求宽度，被容器压窄后每行仍按单行高排版，
    导致几行文字**叠在一起**。所以这里一律不写 `\\n`，由显示宽度断行。
    """
    bg = bg or parent.cget("bg")
    box = tk.Frame(parent, bg=bg)
    box.pack(fill="x", pady=pady, padx=padx)
    lb = tk.Label(box, text=str(text), bg=bg, fg=color or TXT2,
                  font=font or T_BODY_SM(), anchor="w", justify="left",
                  wraplength=wrap(wrap_px))
    lb.pack(fill="x", pady=(0, 3))
    return lb


def row(parent, padx=6, pady=0, bg=None):
    """一排按钮的容器，放不下会自动折到下一行（实现见 ui_parts.WrapRow）。

    Tk 本身不会折行：横排一旦超宽，最右边的按钮被直接剪掉。
    字号调到「超特大」后每个按钮都宽了 50%，整页的按钮组都会断在右边。
    用法：
        r = T.row(card.body); r.pack(fill="x")
        r.add(T.Btn(r, "保存", ...))     # 不要 .pack()，交给 WrapRow 排
    """
    from ui_parts import WrapRow
    return WrapRow(parent, padx=padx, pady=pady, bg=bg)


def card_head(parent, title, sub="", bg=None):
    """卡片内部的抬头：淡灰小字 + 括号说明（参考图「标题（说明）」的写法）。

    2026-11 第 7 版：原来各页自己写 `T.F(11, True)` 的粗黑标题，一屏七八个
    大字卡头比正文还抢眼。现在统一成 `T_CAPTION()` /TXT3，括号里的说明用
    更弱的一档 —— 页面的层级由外壳的页头负责，卡片内部只需要「这是哪块」。
    """
    bg = bg or parent.cget("bg")
    box = tk.Frame(parent, bg=bg)
    box.pack(fill="x", pady=(0, 6))
    # 说明文字「跟随容器宽度」换行。原来是单行 Label：窗口一窄或字号一放大，
    # 「已经做得很密（这些组合文献很多，再做需要明确的差异化理由）」
    # 就被卡片右边缘齐齐切掉半句 —— 2026-11 超特大字号截图里就是这样。
    lb = tk.Label(box, text="%s（%s）" % (title, sub) if sub else title,
                  bg=bg, fg=TXT3, font=T_CAPTION(), anchor="w",
                  justify="left")
    lb.pack(side="left", fill="x", expand=True)
    if sub:
        fill_wrap(lb, pad=4)
    return box


def on_primary_fg():
    """主按钮 / 实心色块上的文字色。

    深色模式用画布底色（浅灰）压在亮品牌色上，浅色模式用纯白压在深品牌色上；
    两种情况都 ≥4.5:1，所以心情按钮之类的实心色块也直接复用它。
    """
    return BG if MODE == "dark" else "#ffffff"


def _btn_styles():
    """按钮四种外观的颜色规则，只此一份（构造与 set_kind 共用）。"""
    return {
        "ghost":   dict(bg=CARD_HI, fg=TXT2, abg=mix(TXT, CARD_HI, 0.14)),
        # 主按钮就是品牌色本身（GitHub 的绿按钮也是这么做的）。
        # 旧写法在浅色下用 ACCENT_D（#8cbcf9）做底 + 白字，对比度不足、看着像禁用。
        "primary": dict(bg=ACCENT, fg=on_primary_fg(), abg=ACCENT_HI),
        "danger":  dict(bg=tint(ERR, 0.20, CARD), fg=ERR, abg=tint(ERR, 0.30, CARD)),
        "ok":      dict(bg=tint(OK, 0.20, CARD), fg=OK, abg=tint(OK, 0.30, CARD)),
    }


def check_sel_bg():
    """勾选框选中时的底色：深色主题用品牌色，浅色主题用浅一档的 tint。

    原来 checked 状态写死成 DARKSEL（`#2b2d31`），浅色主题下勾选框会变成
    一块深灰方块，看着像另一个程序的控件。
    """
    if MODE == "dark":
        return ACCENT
    return ACCENT


class Btn(tk.Label):
    """轻量按钮（Label 实现，保证配色可控）。"""

    def __init__(self, parent, text, cmd=None, kind="ghost", **kw):
        # 颜色按 token 算，不写死十六进制：切明暗后同一套规则自动成立。
        styles = _btn_styles()
        self._kind = kind
        s = styles.get(kind, styles["ghost"])
        hints = str(kw.get("state", "")) == "disabled"
        # 按钮重量默认比正文小一档，但 13px 在 125% 屏上已经是下限；
        # 可以用 font= 另传。
        super().__init__(parent, text=text, bg=s["bg"], fg=(TXT4 if hints else s["fg"]),
                         font=kw.get("font") or T_BODY_SM(),
                         padx=sp(12), pady=sp(4),
                         cursor=("arrow" if hints else "hand2"))
        self._abg, self._bg = s["abg"], s["bg"]
        self._fg0 = s["fg"]          # 记住原前景色，enable(False) 之后能还原
        self._cmd = cmd
        # tk.Label 的 state="disabled" 只是不让改文字，点了照样触发 <Button-1>。
        # 构造时就传了 disabled 的按钮，要把点击关掉、字变灰。
        if hints:
            self._cmd = None
        elif cmd:
            self.bind("<Button-1>", lambda e: self._cmd())
        self.bind("<Enter>", lambda e: self.config(bg=self._abg))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

    def invoke(self):
        """按代码触发一次点击（测试用；也与 tk.Button.invoke 语义一致）。"""
        if self._cmd:
            self._cmd()

    def set_command(self, cmd):
        """后置绑定回调。

        **不要用 `.config(command=...)`**：Btn 是 tk.Label 子类，Label 没有
        `-command` 选项，Tk 会抛 `unknown option "-command"`，而这个异常
        发生在页面渲染途中，直接把整页打断（最新研究页曾因此一页空白，
        测试里表现为「最新研究页有下载入口」失败）。
        """
        self._cmd = cmd
        try:
            self.unbind("<Button-1>")
        except Exception:
            pass
        if cmd:
            self.bind("<Button-1>", lambda e: self._cmd())

    def set_kind(self, kind):
        """切换按钮外观（ghost / primary / danger / ok）。

        不要用 `.config(kind=...)`：Btn 是 tk.Label 子类，没有 `-kind` 选项，
        Tk 会抛 `unknown option "-kind"`，异常发生在渲染途中会把整页打断。
        """
        styles = _btn_styles()
        if kind not in styles:
            return self._kind
        self._kind = kind
        s = styles[kind]
        self._abg, self._bg = s["abg"], s["bg"]
        self._fg0 = s["fg"]
        try:
            self.config(bg=self._bg, fg=self._fg0)
        except Exception:
            pass
        return kind

    def config_text(self, text):
        """改文案。Btn 是 Label 子类，没有 config(text=...) 的统一入口，
        这里给个明确的方法名，免得调用处写成 config(text=) 与 tk.Button 混淆。"""
        self.config(text=text)

    def enable(self, on=True):
        """启用/禁用。禁用时同时摘掉点击回调，否则「变灰但还能点」——
        用户以为没生效，其实已经执行了。"""
        self.config(cursor="hand2" if on else "arrow",
                    fg=self._fg0 if on else TXT4)
        if on:
            if self._cmd:
                self.bind("<Button-1>", lambda e: self._cmd())
        else:
            self.unbind("<Button-1>")


def child_window(parent, title, size="900x640", modal=False):
    """创建一个「跟着主窗口走」的二级窗口。

    为什么非要有这个函数：以前各处直接 `tk.Toplevel(self)`，五个窗口全都没有
    transient —— 结果是
      · 主窗口最小化后它们还漂在桌面上
      · 主窗口关掉它们还活着，任务管理器里有残留进程
      · 点主窗口时它们被压到下面，而不是跟着浮上来
      · 任务栏里各占一个格子
    用户说的「点进去产生新页面，然后回不去了」，主要就是这些窗口在捣乱。

    transient + 跟随协议 = 主窗口最小化/恢复/关闭时它一起走；Esc 关闭；
    如果 modal=True 还会 grab_set（挡住主窗口输入）。
    """
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=BG)
    win.geometry(size)
    win.minsize(420, 300)
    top = parent.winfo_toplevel()
    try:
        win.transient(top)
    except Exception:
        pass
    # 居中于主窗口，避免弹到屏幕角落
    try:
        top.update_idletasks()
        tx, ty = top.winfo_rootx(), top.winfo_rooty()
        tw, th = top.winfo_width(), top.winfo_height()
        parts = size.split("x")
        w = int(parts[0]) if len(parts) > 1 else 900
        h = int(parts[1]) if len(parts) > 1 else 640
        if tw > 100 and th > 100:
            win.geometry("+%d+%d" % (tx + max(0, (tw - w) // 2),
                                     ty + max(0, (th - h) // 3)))
    except Exception:
        pass
    win.bind("<Escape>", lambda e: win.destroy())
    if modal:
        try:
            win.grab_set()
        except Exception:
            pass
    try:
        win.focus_set()
    except Exception:
        pass
    return win


def close_child(parent, attr="_child_win"):
    """关掉页面记着的二级窗口（切页时调用，避免窗口跟着看不见的页面飘着）。"""
    win = getattr(parent, attr, None)
    if win is None:
        return
    try:
        if win.winfo_exists():
            win.destroy()
    except Exception:
        pass
    try:
        setattr(parent, attr, None)
    except Exception:
        pass


def ask_yes(parent, title, prompt):
    """确认框（替代 messagebox.askyesno，配色统一）。返回 True / False。

    为什么不用 messagebox：它跟应用配色完全不一致（白底、系统字体），
    弹出来像另一个程序；而且 ask_text 已经有了这套自绘对话框。
    """
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.configure(bg=BG)
    dlg.transient(parent.winfo_toplevel())
    dlg.resizable(False, False)
    result = {"v": False}
    tk.Label(dlg, text=prompt, bg=BG, fg=TXT2, font=F(10),
             wraplength=420, justify="left").pack(anchor="w", padx=22, pady=(20, 10))

    def yes(_=None):
        result["v"] = True
        dlg.destroy()

    def no(_=None):
        dlg.destroy()

    row = tk.Frame(dlg, bg=BG)
    row.pack(fill="x", padx=22, pady=(0, 16))
    Btn(row, "确定", yes, "danger").pack(side="right")
    Btn(row, "取消", no).pack(side="right", padx=(0, 8))
    dlg.bind("<Return>", yes)
    dlg.bind("<Escape>", no)
    try:
        dlg.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + 120
        dlg.geometry("+%d+%d" % (max(0, x), max(0, y)))
        dlg.grab_set()
        dlg.wait_window()
    except Exception:
        pass
    return result["v"]


def ask_text(parent, title, prompt, initial=""):
    """模态输入框（替代 simpledialog，配色统一）。返回字符串或 None。"""
    from tkinter import messagebox
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.configure(bg=BG)
    dlg.transient(parent.winfo_toplevel())
    dlg.resizable(False, False)
    result = {"v": None}
    tk.Label(dlg, text=prompt, bg=BG, fg=TXT2, font=F(10),
             wraplength=440, justify="left").pack(anchor="w", padx=20, pady=(18, 8))
    e = tk.Entry(dlg, width=46, bg=CARD, fg=TXT, insertbackground=TXT,
                 relief="flat", highlightbackground=LINE, highlightthickness=1,
                 font=F(10))
    e.pack(padx=20, ipady=6, fill="x")
    e.insert(0, initial or "")
    e.focus_set()
    e.select_range(0, "end")

    def ok(_=None):
        result["v"] = e.get().strip()
        dlg.destroy()

    def cancel(_=None):
        dlg.destroy()

    row = tk.Frame(dlg, bg=BG)
    row.pack(fill="x", padx=20, pady=14)
    Btn(row, "确定", ok, "primary").pack(side="right")
    Btn(row, "取消", cancel).pack(side="right", padx=(0, 8))
    e.bind("<Return>", ok)
    dlg.bind("<Escape>", cancel)
    try:
        dlg.grab_set()
        dlg.wait_window()
    except Exception:
        pass
    return result["v"]