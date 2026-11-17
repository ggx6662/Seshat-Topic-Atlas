#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三端共用的设计令牌 —— 单一事实来源。

## 为什么要有这个文件

桌面端（Tk）和网页端（CSS）以前的配色是**两套完全不同的体系**：

    Tk   BG #061220  CARD #0C2135  ACCENT #6BE7FF   （深海军蓝 + 青）
    CSS  BG #0d1117  CARD #161b22  ACCENT #58a6ff   （GitHub 灰蓝）

放在一起看就是两个产品。用户要求「区别三种形态，但不要差异过大」，
所以色彩、字号档位、间距、圆角必须来自同一份定义；**分化的只能是密度和交互形态**。

## 三端怎么分化（差异只在这三个维度）

| 维度 | 客户端 (Tk) | 网页版 | 移动端 |
|---|---|---|---|
| 密度 | 紧凑，信息优先 | 舒展，多列并排 | 单列，触控优先 |
| 导航 | 左侧常驻竖栏 | 顶部横排 | 顶部横滑 + 渐隐 |
| 字号基准 | 13/15/17/21/28 px | 同左，但行高更大 | 同左，正文 16px 保底 |

**不变的部分**（这才是「不像两个产品」的原因）：
色彩令牌、字号档位、圆角、语义色、卡片描边方式、等宽数字。

## 用法

桌面端 `app_theme.py` 在 import 时从这里取色；
网页端 `web_server.py` 把它注入到 `/api/theme`，`app.js` 在启动时套到 `:root` 上。
这样改一个值，三端一起变。
"""

# ---- 色彩：灰阶底 + 一个品牌色 -------------------------------------------
#
# 2026-11 版：用户定了「做成灰阶，只把品牌色给要点」。所以表面是中性灰
# （不带蓝、不带青），层级靠亮度台阶 + 1px 描边，不靠投影。
# 品牌色只出现在三种地方：可点的文字/按钮、当前选中的导航项、关键数字。
# 风险等级、图表数据、方法标签这些「有含义」的地方才用彩色。
#
# 三端都从这里取。网页端 `web_server.py` 把它注入成 CSS 变量。

def _hover(hexstr, step=10):
    """把某个表面按固定步长提亮，用于 hover 态 —— 手写容易跳色。"""
    h = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        v = min(255, int(h[i:i + 2], 16) + step)
        out.append("%02x" % v)
    return "#" + "".join(out)


def _build(base, ink_base):
    pal = {}
    pal.update(base)
    pal.update(ink_base)
    dark = base["canvas"] < "#800000"   # 粗略判深浅，只用来选描边方向
    step = 10 if dark else -10
    pal["surface_hover"] = _hover(base["surface_raised"], step)
    pal["surface_active"] = _hover(base["surface_card"], step - 4)
    return pal


# 灰阶（深浅两套）。刻意保持中性：RGB 三通道差值 ≤3，肉眼看不出色偏。
#
# 2026-11-15 第 7 版：用户给了一张运维控制台的参考图，要求「这种」。
# 参考图的关键是**画布比卡片深得多**（近纯黑页底 + 明显亮一档的卡片），
# 卡片无描边靠底色分层，侧栏再深一档并且和画布分得开。旧版的
# canvas #17181a / card #1c1d1f 只差一档（ΔL≈3%），整页糊成一片灰，
# 所以不得不靠 1px 描边补层级 —— 结果是「到处都是框」。
# 新版把三级拉开：canvas(最暗) < nav(微亮) < card(明显亮) < raised。
_GREY_DARK = {
    "canvas":          "#0b0d10",   # 页面底：近纯黑，内容区因此显得「浮起来」
    "surface_nav":     "#101216",   # 侧栏：比画布略亮，形成一条窄柱
    "surface_card":    "#15181c",   # 卡片：ΔL 明显，不用描边也分得开
    "surface_raised":  "#1d2126",   # 行内次级块、输入框、悬停
    "surface_overlay": "#22272d",   # 浮层、弹出
    "hairline":        "#262b31",   # 只在必须画线的地方用（表格行、分隔）
    "hairline_soft":   "#1a1e22",   # 极弱分隔
}
_GREY_DARK_INK = {
    "ink":             "#e8eaed",   # 主文字
    "ink_secondary":   "#b9bec5",
    "ink_tertiary":    "#8c939b",   # 说明、列头
    "ink_quaternary":  "#7d848c",   # 占位符：卡片上仍 ≥4.5:1
}

_GREY_LIGHT = {
    # 2026-11-15：画布从 #ffffff 改到 #f7f8f9。
    # 原因：画布和卡片都是纯白时，卡片完全「融进」页面，唯一能区分它们的是
    # 一圈描边 —— 而描边在 Canvas 上被反锯齿成 2px 灰框，用户说「太丑」。
    # 把画布压深一档、卡片保持纯白，层级就由底色差承担了，一条线都不用画。
    # 这是 GitHub / Linear / Notion 都在用的做法：内容区白，底灰。
    # 2026-11-15 第 11 版：参考图（Linear 式看板）的底是极浅的中性灰，
    # 卡片纯白浮在上面，侧栏和画布同色系、只差一两档。层级全靠底色差，
    # 一条描边都不画 —— 描边在 Canvas 上会被反锯齿成 2px 灰框。
    "canvas":          "#eff0f3",
    # 侧栏比画布深一档：浅色下白卡放在画布上，侧栏如果也接近白，
    # 整屏会连成一片（截图里侧栏与内容区几乎分不开）。
    "surface_nav":     "#e4e7ec",
    "surface_card":    "#ffffff",
    "surface_raised":  "#f5f6f8",
    "surface_overlay": "#ffffff",
    "hairline":        "#d6d9e0",
    "hairline_soft":   "#e8eaee",
}
_GREY_LIGHT_INK = {
    "ink":             "#1b1d21",
    "ink_secondary":   "#43474d",
    "ink_tertiary":    "#5c6169",
    "ink_quaternary":  "#5c6169",
}

# 语义色：两套各调一次，保证在自己那套底色上都 ≥4.5:1。
_SEM_DARK = {
    "primary":         "#2f81f7",   # 唯一的「可点」色
    "primary_hover":   "#58a6ff",
    "primary_muted":   "#1b3a5c",
    "success":         "#3fb950",
    "warning":         "#d29922",
    "danger":          "#f85149",
    "info":            "#a371f7",
    "orange":          "#db6d28",
}
_SEM_LIGHT = {
    # 参考图的强调色是紫色。白底上要 ≥4.5:1，所以取深一档的 #6d4bd8；
    # primary_muted 是选中块/徽章的浅紫底。
    "primary":         "#6d4bd8",
    "primary_hover":   "#5a3cc0",
    "primary_muted":   "#efecfd",
    "success":         "#1a7f37",
    "warning":         "#9a6700",
    "danger":          "#cf222e",
    "info":            "#8250df",
    "orange":          "#bc4c00",
}

PALETTE = {
    "dark": _build(_GREY_DARK, dict(_GREY_DARK_INK, **_SEM_DARK)),
    "light": _build(_GREY_LIGHT, dict(_GREY_LIGHT_INK, **_SEM_LIGHT)),
}

# 当前生效的一套。`app_theme.set_mode()` 切它之前会给所有控件重建配色，
# 这里只决定「下一次取色取哪一套」。
CURRENT = "dark"

# 兼容旧名字：其余二十来个模块都是 `from design_tokens import COLORS`，
# 直接绑到当前调色板，切主题后它们看到的是同一份 dict（原地更新）。
#
# **必须是 PALETTE["dark"] 的独立副本**，不能直接别名。早先写的是
# `COLORS = PALETTE[CURRENT]`，于是 COLORS 与 PALETTE["dark"] 是同一个对象：
# set_mode 里 `COLORS.clear()` 先清空了 PALETTE["dark"] 这个源头，切回深色
# 时拿到的就是空字典；即便不空，`update(PALETTE["light"])` 也会把深色那份
# 覆盖成浅色值 —— 来回切两次，两套调色板彻底串味。
COLORS = dict(PALETTE[CURRENT])

LEGACY_COLORS = {
    "canvas":          "#061220",   # 页面底
    "surface_nav":     "#08182A",   # 导航栏
    "surface_card":    "#0C2135",   # 卡片
    "surface_raised":  "#0E2539",   # 列表行、次级卡片
    "surface_overlay": "#10304A",   # 模态、悬浮层
    "hairline":        "#1B3A53",   # 描边
    "hairline_soft":   "#14304A",

    "primary":         "#6BE7FF",   # 唯一品牌色：只给「可点的」和「关键数字」
    "primary_hover":   "#8FEEFF",
    "primary_muted":   "#0E4B63",   # 青色按钮的底

    "ink":             "#EDF8FF",   # 主文字
    "ink_secondary":   "#B4CFE0",
    "ink_tertiary":    "#8AA8BF",
    "ink_quaternary":  "#7794AB",   # 最弱，卡片上仍 ≥4.5:1

    "success":         "#43FFC9",
    "warning":         "#FFD166",
    "danger":          "#FF6F91",
    "info":            "#B69CFF",   # 创新 / 方法论 / 跨领域
    "orange":          "#FFB37A",   # 高回报
}

# 语义色到 CSS 变量名的映射（网页端用）
CSS_VARS = {
    "canvas": "--bg",
    "surface_nav": "--nav",
    "surface_card": "--card",
    "surface_raised": "--card-hi",
    "surface_overlay": "--overlay",
    "surface_hover": "--card-hover",
    "hairline": "--line",
    "hairline_soft": "--line-soft",
    "primary": "--accent",
    "primary_hover": "--accent-hi",
    "primary_muted": "--accent-dim",
    "ink": "--txt",
    "ink_secondary": "--txt2",
    "ink_tertiary": "--txt3",
    "ink_quaternary": "--txt4",
    "success": "--ok",
    "warning": "--warn",
    "danger": "--err",
    "info": "--purple",
    "orange": "--orange",
}


def set_mode(mode):
    """切换调色板。**原地更新** COLORS，不要换 dict 对象 ——
    二十来个模块是 `from design_tokens import COLORS` 拿的引用。"""
    global CURRENT
    if mode not in PALETTE:
        mode = "dark"
    CURRENT = mode
    # 必须先拷一份再做任何清空动作：COLORS 在初始化时 `COLORS = PALETTE["dark"]`
    # 就是同一个 dict 对象，`COLORS.clear()` 会连源头一起清空，紧接着
    # `update(PALETTE["dark"])` 拿到的是刚被清空的空 dict —— 切回深色后整个
    # 调色板变空，界面全白/全黑。深拷一份即可避开这个自引用。
    src = dict(PALETTE[mode])
    COLORS.clear()
    COLORS.update(src)
    return COLORS

# ---- 字号 ----------------------------------------------------------------
# 只有 6 档。历史上各页面随手写过 F(7)…F(21) 共 10 种，没有层级也保证不了
# 最小可读尺寸。13px 是中文笔画不粘连的下限。
TYPE_SCALE = {
    "display": 28,    # 总览页问候语
    "title":   21,    # 页面标题
    "section": 17,    # 区块标题、卡片标题
    "body":    15,    # 正文
    "caption": 13,    # 说明、标签、注释（最小档）
    "metric":  24,    # 统计数字（等宽）
}

# ---- 尺寸 ----------------------------------------------------------------
RADIUS = {"xs": 4, "sm": 6, "md": 8, "lg": 10, "xl": 14}
SPACING = {"xxs": 4, "xs": 6, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}

# ---- 三端密度档 ----------------------------------------------------------
# 只影响「留白」和「单屏信息量」，不影响配色与字号档位。
DENSITY = {
    "client": {"pad": 16, "row_h": 34, "gap": 12, "line_h": 1.5, "columns": 1},
    "web":    {"pad": 24, "row_h": 42, "gap": 18, "line_h": 1.65, "columns": 2},
    "mobile": {"pad": 14, "row_h": 48, "gap": 14, "line_h": 1.75, "columns": 1},
}


def css_block(mode=None):
    """生成注入网页端的 CSS 变量块。传 mode 可以拿到另一套（明/暗）的变量，
    这样网页端能在地球按钮上直接切，不必重连。"""
    pal = PALETTE[mode or CURRENT]
    lines = [":root {"]
    for key, var in CSS_VARS.items():
        lines.append("  %s: %s;" % (var, pal[key]))
    lines.append("  --radius: %dpx;" % RADIUS["md"])
    lines.append("  --radius-sm: %dpx;" % RADIUS["sm"])
    lines.append("  --metric-font: 24px;")
    lines.append("  --display-font: 28px;")
    lines.append("  --title-font: 21px;")
    lines.append("  --section-font: 17px;")
    lines.append("  --body-font: 15px;")
    lines.append("  --caption-font: 13px;")
    lines.append("}")
    return "\n".join(lines)


def contrast(fg, bg):
    """WCAG 对比度。用来在改色之后立刻验证，而不是靠肉眼。"""
    def _lum(hexstr):
        hexstr = hexstr.lstrip("#")
        if len(hexstr) == 3:
            hexstr = "".join(c * 2 for c in hexstr)
        vals = []
        for i in (0, 2, 4):
            c = int(hexstr[i:i + 2], 16) / 255.0
            vals.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]

    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def audit():
    """自检：文字色在三种底色上的对比度都必须 ≥4.5:1。"""
    rows = []
    for fg_name in ("ink", "ink_secondary", "ink_tertiary", "ink_quaternary"):
        for bg_name in ("canvas", "surface_card", "surface_raised"):
            ratio = contrast(COLORS[fg_name], COLORS[bg_name])
            rows.append((fg_name, bg_name, ratio, ratio >= 4.5))
    return rows


if __name__ == "__main__":
    for fg, bg, ratio, ok in audit():
        print("%-16s on %-14s %5.2f:1  %s" % (fg, bg, ratio, "OK" if ok else "FAIL"))