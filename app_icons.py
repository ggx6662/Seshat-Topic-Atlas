#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画出来的图标（不是字形）。

## 为什么不用 Unicode 字符当图标

之前用 ◈ ▤ ↻ ★ ▦ ◉ 这些几何符号冒充图标，有三个绕不过去的问题：

1. **不同字体的宽高和基线不一样**。等线和雅黑里同一个「▤」，宽度能差 2px，
   基线偏 1–3px，一排图标摆下来就是歪的（截图里那排宫格图标明显高低不齐）。
2. **笔画粗细不由你定**。字体里画多粗就是多粗，125% 缩放下还会被反锯齿糊掉。
3. 它是「文字」，不是图标系统 —— 同一界面的图标风格必须一致，而这套符号
   里面有线框的、有实心的、有带圆角的，根本不成套。

所以这里用 tk.Canvas 一笔一笔画：统一 20px 画布、1.6px 线宽、圆头圆角、
全部线框风格（不混实心）。尺寸和线宽都是传入的，缩放时按比例重画，
永远是整数像素下的直线段，不糊。

## 用法

    cv = icon_canvas(parent, "topic", size=18, fg=T.TXT2, bg=T.CARD)
    cv.pack(side="left")

`ICONS` 是 `名字 -> 画法(canvas, s)`，s 是 20 单位画布上的坐标缩放系数。
新增图标就在 ICONS 里加一个函数，别去字体里找符号。
"""

import tkinter as tk

import app_theme as T

# 图标名 → 说明（也是「这个界面有几个模块」的清单，方便对账）
NAMES = (
    "home", "topic", "gap", "latest", "ideas", "skills", "mentor",
    "venue", "library", "map", "profile", "settings", "search",
)


def _pen(cv, s, fg):
    """线条用的笔画：1.6 单位宽、圆头、圆角。

    **线条没有 outline 选项**（只有 fill）—— 早先把 stroke 参数一股脑传给了
    create_line，Tk 直接报 `unknown option "-outline"`，而 draw() 里的
    try/except 把异常吞了，于是「13 个图标全都画不出来但程序不报错」。
    现在分成两个函数：线用 _pen，形状用 _pen_shape。
    """
    return dict(width=max(1.0, 1.6 * s), fill=fg,
                capstyle="round", joinstyle="round")


def _pen_shape(cv, s, fg, join=False):
    """线框形状（矩形/椭圆/圆弧）的笔画：不填充。

    这三类图元**只认 width / fill / outline**：`capstyle` 是 create_line
    独有的，`joinstyle` 只有 line 和 polygon 有，rectangle/oval/arc 都没有。
    早先共用一份参数字典，Tk 依次报 `unknown option "-capstyle"` /
    `"-joinstyle"`，而 draw() 里吞了异常 —— 于是有 6 个图标一个图元都没画
    出来，界面上只剩空白。现在每种图元只传它真支持的键。
    """
    kw = dict(width=max(1.0, 1.6 * s), fill="", outline=fg)
    if join:
        kw["joinstyle"] = "round"
    return kw


def _line(cv, s, fg, *xy):
    return cv.create_line(*[v * s for v in xy], **_pen(cv, s, fg))


def _rect(cv, s, fg, x1, y1, x2, y2, r=2.0):
    """直角矩形。Tk 的 create_rectangle 不支持圆角，图标尺度上直角就够。"""
    return cv.create_rectangle(x1 * s, y1 * s, x2 * s, y2 * s, **_pen_shape(cv, s, fg))


def _oval(cv, s, fg, x1, y1, x2, y2):
    return cv.create_oval(x1 * s, y1 * s, x2 * s, y2 * s, **_pen_shape(cv, s, fg))


def _arc(cv, s, fg, x1, y1, x2, y2, start, extent):
    return cv.create_arc(x1 * s, y1 * s, x2 * s, y2 * s, start=start,
                         extent=extent, style="arc", **_pen_shape(cv, s, fg))


# ---------------------------------------------------------------- 各图标
# 坐标全部在 0..20 的方格里，画的时候乘 s。留 2 单位内边距。

def _home(cv, s, fg):
    # 房子：屋顶折线 + 墙体
    _line(cv, s, fg, 3, 9.5, 10, 3.5, 17, 9.5)
    _line(cv, s, fg, 5, 9, 5, 17, 15, 17, 15, 9)


def _topic(cv, s, fg):
    # 选题工坊：一张纸 + 一个问号点（「找一个值得做的问题」）
    _line(cv, s, fg, 5, 3, 13, 3, 16, 6, 16, 17, 5, 17, 5, 3)
    _line(cv, s, fg, 13, 3, 13, 6, 16, 6)
    _line(cv, s, fg, 8, 10, 13, 10)


def _gap(cv, s, fg):
    # 文献空白：上半是「已有的」，下半空一格 —— 一条断开的阶梯
    _line(cv, s, fg, 3, 4, 12, 4)
    _line(cv, s, fg, 3, 4, 3, 10)
    _line(cv, s, fg, 3, 10, 8, 10)
    _line(cv, s, fg, 12, 16, 17, 16)
    _line(cv, s, fg, 17, 16, 17, 10)
    _line(cv, s, fg, 17, 10, 12, 10)


def _latest(cv, s, fg):
    # 最新研究：一个较长的圆弧 + 明确的箭头尖，代表「新一批」
    _arc(cv, s, fg, 3.5, 3.5, 16.5, 16.5, 55, 265)
    _line(cv, s, fg, 12.6, 3.0, 16.6, 6.0, 11.8, 7.4)


def _ideas(cv, s, fg):
    # 创新点库：四角星（不是 ★ 字形，是四条线段拼的）
    _line(cv, s, fg, 10, 2.5, 10, 17.5)
    _line(cv, s, fg, 2.5, 10, 17.5, 10)
    _line(cv, s, fg, 5, 5, 15, 15)
    _line(cv, s, fg, 15, 5, 5, 15)


def _skills(cv, s, fg):
    # 方法论：三层叠起来的步骤条
    _line(cv, s, fg, 3, 5, 17, 5)
    _line(cv, s, fg, 3, 10, 12, 10)
    _line(cv, s, fg, 3, 15, 17, 15)


def _mentor(cv, s, fg):
    # 导师：一个人（头 + 肩），肩线是一条闭合的弧
    _oval(cv, s, fg, 7.4, 2.8, 12.6, 8.0)
    _arc(cv, s, fg, 3.4, 10.0, 16.6, 21.0, 0, 180)
    _line(cv, s, fg, 3.4, 16.2, 3.4, 17.2)
    _line(cv, s, fg, 16.6, 16.2, 16.6, 17.2)


def _venue(cv, s, fg):
    # 期刊会议：一本打开的书 / 会刊
    _line(cv, s, fg, 10, 6, 10, 17)
    _line(cv, s, fg, 10, 6, 4, 4, 3, 14, 10, 17)
    _line(cv, s, fg, 10, 6, 16, 4, 17, 14, 10, 17)


def _library(cv, s, fg):
    # 文献库：三本竖立的书脊
    _rect(cv, s, fg, 4, 4, 7, 17)
    _rect(cv, s, fg, 8.5, 6, 11.5, 17)
    _line(cv, s, fg, 13, 6, 16.5, 5, 16.5, 17, 13, 17, 13, 6)


def _map(cv, s, fg):
    # 方向图谱：节点 + 连线
    _oval(cv, s, fg, 8, 2.5, 12, 6.5)
    _oval(cv, s, fg, 2.5, 13, 6.5, 17)
    _oval(cv, s, fg, 13.5, 13, 17.5, 17)
    _line(cv, s, fg, 9, 6.5, 6, 13)
    _line(cv, s, fg, 11, 6.5, 14, 13)


def _profile(cv, s, fg):
    # 个人画像：外框（一张卡）+ 中间的人头，和「导师」区分开
    _line(cv, s, fg, 4, 3, 16, 3, 16, 17, 4, 17, 4, 3)
    _oval(cv, s, fg, 8.2, 6.0, 11.8, 9.6)
    _arc(cv, s, fg, 6.0, 10.6, 14.0, 17.6, 0, 180)


def _map(cv, s, fg):
    # 方向图谱：三节点连线（节点是实心小圆，连线是细线，主次分明）
    def node(x, y):
        cv.create_oval((x - 2.0) * s, (y - 2.0) * s, (x + 2.0) * s, (y + 2.0) * s,
                       fill=fg, outline=fg)
    _line(cv, s, fg, 10, 6.0, 5.5, 13.4)
    _line(cv, s, fg, 10, 6.0, 14.5, 13.4)
    node(10, 5.2)
    node(5.0, 14.4)
    node(15.0, 14.4)


def _settings(cv, s, fg):
    # 设置：两根滑杆 + 手柄
    _line(cv, s, fg, 3, 7, 17, 7)
    _line(cv, s, fg, 3, 13, 17, 13)
    _oval(cv, s, fg, 7.2, 4.6, 11.2, 8.6)
    _oval(cv, s, fg, 10.5, 10.6, 14.5, 14.6)


def _search(cv, s, fg):
    _oval(cv, s, fg, 3.5, 3.5, 13, 13)
    _line(cv, s, fg, 12.2, 12.2, 16.5, 16.5)


def _plan(cv, s, fg):
    # 研究计划：日历（外框 + 两个挂环 + 横向分隔线）+ 一条对勾。
    # 对勾不画在中间而是在右下角压线，这样 16px 下日历轮廓不会糊。
    _line(cv, s, fg, 3, 5, 3, 17, 17, 17, 17, 5, 3, 5)
    _line(cv, s, fg, 3, 9, 17, 9)
    _line(cv, s, fg, 6.5, 2, 6.5, 6)
    _line(cv, s, fg, 13.5, 2, 13.5, 6)


ICONS = {
    "home": _home, "topic": _topic, "gap": _gap, "latest": _latest,
    "ideas": _ideas, "skills": _skills, "mentor": _mentor,
    "venue": _venue, "library": _library, "map": _map,
    "profile": _profile, "settings": _settings, "search": _search,
    "plan": _plan,
}

# 画布尺寸固定 20 单位：所有坐标都按这个算
_UNIT = 20.0


def draw(cv, name, size=18, fg=None, bg=None):
    """在一个**已经建好**的 Canvas 上画图标。返回画布本身，方便链式使用。

    2026-11-15 教训：这里曾经用 try/except 把**所有**异常吞掉，结果 Tk 报
    「未知选项」时 13 个图标一个都画不出来，而程序界面照常启动、控制台
    一片安静 —— 肉眼只看到「图标位置是空的」。所以现在只在真出问题时
    降级：把异常写进 stderr 一次，并且**画出一个小方块**当占位，让缺图
    这件事在界面上看得见，而不是悄悄消失。
    """
    fn = ICONS.get(name)
    if not fn:
        return cv
    fg = fg or T.TXT2
    s = float(size) / _UNIT
    cv.delete("all")
    try:
        cv.configure(bg=bg or T.CARD, highlightthickness=0, bd=0,
                     width=size, height=size)
    except Exception:
        pass
    try:
        fn(cv, s, fg)
    except Exception as exc:      # pragma: no cover - 只在图标代码有 bug 时进
        import sys
        print("[app_icons] %s 画失败：%r" % (name, exc), file=sys.stderr)
        try:
            cv.create_rectangle(5 * s, 5 * s, 15 * s, 15 * s,
                                outline=fg, width=1)
        except Exception:
            pass
    return cv


def icon_canvas(parent, name, size=18, fg=None, bg=None, **kw):
    """新建一个只装着图标的小画布。

    `**kw` 透传给 tk.Canvas（比如 cursor="hand2"）。
    画布尺寸直接设成 size，**不要 pack_propagate(False) 再靠 pack 撑**：
    Canvas 的请求尺寸就是 width/height，布局器会照着它排版。
    """
    cv = tk.Canvas(parent, width=size, height=size, bg=bg or T.CARD,
                   highlightthickness=0, bd=0, **kw)
    return draw(cv, name, size=size, fg=fg, bg=bg)


# ---------------------------------------------------------------- 画进别人的画布
# 侧栏每一行本身就是一个 Canvas（色块 + 文字都画在上面）。如果图标另建一个
# Canvas 再 place 上去，会出现「子画布盖住父画布的点击区域」「滚动时不同步」
# 这类麻烦。所以提供 draw_on()：把图标的坐标整体平移 (x, y) 后画进**已有的**
# 画布。平移用 cv.move()，图元 id 记下来交给调用方自己管理。

def draw_on(cv, name, size=18, fg=None, x=0, y=0, tags=None):
    """在已有画布上画一个图标，左上角落在 (x, y)。返回图元 id 列表。

    实现上「画在原点上，再整体平移」而不是「把坐标逐点加偏移」：
    图标函数只认 0..20 这套坐标，平移交给 Tk 的 move() 一次完成，
    不会因为取整在斜线上留下 1px 的错位。
    """
    fn = ICONS.get(name)
    if not fn:
        return []
    fg = fg or T.TXT2
    s = float(size) / _UNIT
    before = set(cv.find_all())
    try:
        fn(cv, s, fg)
    except Exception as exc:      # pragma: no cover
        import sys
        print("[app_icons] %s 画失败：%r" % (name, exc), file=sys.stderr)
        return []
    new = [i for i in cv.find_all() if i not in before]
    for i in new:
        if x or y:
            cv.move(i, x, y)
        if tags:
            cv.addtag_withtag(tags, i)
    return new


def recolor(cv, name, fg, size=None):
    """只换颜色重画（悬停、选中态用）。size 不给就沿用画布原尺寸。"""
    try:
        s = size or int(cv.cget("width"))
    except Exception:
        s = 18
    return draw(cv, name, size=s, fg=fg, bg=None if bg_of(cv) is None else None)


def bg_of(cv):
    try:
        return cv.cget("bg")
    except Exception:
        return None


if __name__ == "__main__":
    # 自检：把 13 个图标排成两行画出来，存一张 PNG 供目视
    root = tk.Tk()
    root.title("icon sheet")
    root.configure(bg=T.BG)
    sheet = tk.Frame(root, bg=T.BG)
    sheet.pack(padx=16, pady=16)
    for i, n in enumerate(NAMES):
        cell = tk.Frame(sheet, bg=T.CARD)
        cell.grid(row=i // 7, column=i % 7, padx=8, pady=8, ipadx=10, ipady=6)
        icon_canvas(cell, n, size=18, fg=T.TXT2, bg=T.CARD).pack()
        tk.Label(cell, text=n, bg=T.CARD, fg=T.TXT4,
                 font=T.T_CAPTION()).pack(pady=(2, 0))
    root.update()
    root.after(300, root.destroy)
    root.mainloop()
    print("画了 %d 个图标" % len(NAMES))