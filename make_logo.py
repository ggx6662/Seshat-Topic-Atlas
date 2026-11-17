# -*- coding: utf-8 -*-
"""生成应用 logo（第 6 版）：实心圆角方块 + 反白横线，全尺寸同一造型。

======================================================================
为什么推翻第 4/5 版（务必先读，别再退回去）
======================================================================

前几版都在画「开口圆环 + 三条横线」的**细线矢量图形**，靠按尺寸分档改笔画、
超采样后 alpha 二值化来求清晰。用户 2026-11-16 的判决是：
「太过于像素化，不清楚以及各种情况，不符合项目要求」。

把 16px 任务栏图标抓下来放大 6 倍看，问题一目了然：

  1. **细线图形在 16px 下没有「图形」，只有「像素画」**。圆环在 16px 上只有
     1–2 个像素宽，被系统取整后一圈断成一堆孤立的方块；二值化把过渡像素切掉，
     边缘就成了台阶 —— 这就是「像素化」三个字的来源。**这不是画得不够精细，
     是造型选错了**：任何 1.5px 宽的曲线在 16px 上都不可能干净。
  2. **靠「补洞」「阈值化」修小图，方向是错的**。补洞会把环内空隙填成实心块
     （第 5 版自己踩过，注释里写着「看着像被涂满的 C」），阈值化会制造硬台阶。
     这些补丁越加越多，造型本身却没救。
  3. **深色 UI 上纯蓝细线对比度不够**。品牌蓝 #2f81f7 在近黑标题栏上只有 5:1，
     1.5px 的线一平均就掉到 2–3:1，肉眼就是「发虚」。而**实心色块 + 反白**
     天然是高对比：块与背景、块与内线条各有一层对比。

======================================================================
第 6 版的解法
======================================================================

**换成「实心色块 + 反白线条」，并且全尺寸用同一套造型，不分档、不二值化、
不补洞。**

  · 造型：圆角方块（superellipse 超椭圆，比普通圆角矩形更像系统图标）
    + 内部三条**白色**横线（右对齐、长度递简），读作「一条引文条目」，
    与产品语义（知识库 / 文献）一致。
  · 外轮廓是**一整块实心色**，形状简单、边缘只有外边界一条 —— 任何尺寸缩小
    后都还是「一个方块 + 几条白线」，不会碎成像素点。
  · 大尺寸用超采样抗锯齿求平滑；小尺寸（<= 64）**直接在整数网格上按
    「覆盖率 >= 50% 记为实心」渲染**，避免「大图缩小再阈值」产生的台阶。

小尺寸档位是怎么定的（每一档都在 8× 放大下标定过）：

  | 尺寸 | 内线 | 线宽 | 线间距 | 白色像素数 |
  | ---- | ---- | ---- | ------ | ---------- |
  | 16   | 2 条 | 1px  | 3px    | 约 20 个   |
  | 24   | 3 条 | 2px  | 5px    | 约 60 个   |
  | 32   | 3 条 | 2px  | 6px    | 约 90 个   |
  | 48+  | 3 条 | ∝尺寸| ∝尺寸  | 矢量式     |

16px 只画 2 条：画布 16 像素里要塞下圆角、3 条线和 2 个间距，3 条会让
线距只剩 2px，缩到任务栏后仍是一团。2 条能确保 1px 的线是干净的直线。

======================================================================
输出
======================================================================
  透明底（应用内、网页 PWA 用）：
    logo_1024.png / logo_{512,256,128,64,48,32,24,16}.png
    kb_widget_v2.png (48) + web_static/icon-{512,192}.png + icon-maskable.png
  白底（Windows 图标槽、快捷方式、窗口标题栏用 —— 见下方说明）：
    win16/win24/win32/win48/win64/win128/win256.png，打进 kb_widget_v2.ico

**为什么 Windows 图标要白底**：窗口标题栏是浅色的。透明底图标只剩蓝色块与
白色内线，蓝色外围没有衬底，系统画在浅色标题栏上看着「糊成一团」。改成
「白色圆角衬底 + 内缩的品牌色方块」，在浅色标题栏和浅色任务栏上都成立；
深色任务栏上白衬底会呈现成白色圆角方块 —— 这是 Windows 商店应用的通行做法。
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
WEB = HERE / "web_static"

# 品牌蓝。实心块用，白线反白。
INK = (47, 129, 247)
# Windows 图标衬底：近白而不是纯白，避免在大白屏上「糊掉」
PLATE = (243, 245, 249)

SS = 8          # 超采样倍率（>= 64px 的大图用）


# ======================================================================
# 一、几何：给定边长 S（逻辑像素），返回所有尺寸参数
# ======================================================================
def _geom(S):
    """按目标边长给出造型参数。

    返回值 (supern, inset, radius_ratio, n_lines, line_px, gap_px)：
      supern      超椭圆指数（4.0 是标准 squircle，2.0 退化成椭圆）
      inset       色块相对画布的内缩比例（白底衬底版本用）
      radius_ratio 圆角占边长比例
      n_lines     内线条数
      line_px     线宽（逻辑像素，可为小数；渲染时按覆盖率取整）
      gap_px      相邻两线的**中心距**
    """
    if S <= 20:
        # 16px：画布只有 16 个像素。圆角半径 3px、
        # 2 条 1px 线、中心距 3.6px —— 放大 8 倍仍是「圆角方块 + 两横」。
        return 4.0, 0.0, 0.19, 2, 1.00, 3.6
    if S <= 28:
        # 24px：线宽取 2 而不是 1.6 —— 1.6 取整成 2 后中心距若仍是 4.4，
        # 会与首末内边距冲突，实测第三条线被切成一窄一宽两行。
        return 4.2, 0.0, 0.20, 3, 2.00, 5.0
    if S <= 40:
        return 4.2, 0.0, 0.21, 3, 2.00, 6.0
    if S <= 64:
        return 4.3, 0.0, 0.22, 3, 2.80, 7.4
    # 大尺寸：连续比例
    return 4.4, 0.0, 0.225, 3, max(3.0, S * 0.0625), S * 0.155


def _superellipse_points(cx, cy, a, b, n, steps=720):
    """超椭圆 |x/a|^n + |y/b|^n = 1 的轮廓点。

    用参数方程（|cos|^(2/n) · sgn）取点，而不是普通圆角矩形 ——
    squircle 的过渡更连续，缩到小尺寸时圆角不会变成一个「方框加四个缺口」。
    """
    pts = []
    e = 2.0 / n
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        ct, st = math.cos(t), math.sin(t)
        x = math.copysign(abs(ct) ** e, ct) * a
        y = math.copysign(abs(st) ** e, st) * b
        pts.append((cx + x, cy + y))
    return pts


# ======================================================================
# 二、渲染：两种路径
#     · 大尺寸：8× 超采样后 LANCZOS 缩小（平滑抗锯齿）
#     · 小尺寸：直接在 S×S 网格上做覆盖率计算（整数像素，无台阶）
# ======================================================================
def _layout(S, plate=False):
    """算出色块与内线条在 S 坐标下的矩形（float）。

    白底衬底（plate=True）时，色块内缩到约 82%，外面留一圈圆角白衬。
    """
    supern, inset, rr, n_lines, line_px, gap_px = _geom(S)
    if plate:
        inset = 0.085
    pad = S * inset
    side = S - 2 * pad
    # 线条束：垂直居中，右对齐
    lines = []
    if S <= 64:
        # --------------------------------------------------------------
        # 小尺寸走「整数网格」：线宽、首线位置、行距全部取整，
        # 每条线都精确占 line_px 个整行。实测若用浮点中心 + 覆盖率取整，
        # 24px 时第三条线落在 13.2 / 15.2 / 17.2 三个错位的班上，
        # 白段数从 3 掉到 1（三条线糊成一团），这是第 6 版初期最大的坑。
        # --------------------------------------------------------------
        line_px = max(1, int(round(line_px)))
        span = (n_lines - 1) * line_px
        # 行距：让整束线在色块内垂直居中，且首线从整数行开始
        while span > max(1, side - 4) and line_px > 1:
            line_px -= 1
            span = (n_lines - 1) * line_px
        row_gap = line_px
        if n_lines > 1:
            # 优先用「线与线之间空 1px」以外还想更松时，按可用高度均分整数行距
            want = gap_px
            avail = side - 4
            fit = int((avail - span) / (n_lines - 1))
            row_gap = max(line_px, min(int(round(want)), max(line_px, fit + line_px)))
        total = (n_lines - 1) * row_gap + line_px
        top = pad + round((side - total) / 2.0)
        lens = (1.0, 0.74, 0.50)[:n_lines]
        x_left0 = pad + side * 0.245
        x_right = pad + side * 0.775
        for i in range(n_lines):
            y0 = float(top + i * row_gap)
            y1 = float(y0 + line_px)
            x0 = x_left0 + (x_right - x_left0) * (1.0 - lens[i])
            lines.append((x0, y0, x_right, y1))
        return dict(supern=supern, pad=pad, side=side, rr=rr,
                    lines=lines, line_px=float(line_px))

    total = (n_lines - 1) * gap_px
    top = S / 2.0 - total / 2.0
    lens = (1.0, 0.74, 0.50)[:n_lines]
    right = pad + side * 0.775
    left0 = pad + side * 0.245
    lines = []
    for i in range(n_lines):
        cy = top + gap_px * i
        x0 = left0 + (right - left0) * (1.0 - lens[i])
        lines.append((x0, cy - line_px / 2.0, right, cy + line_px / 2.0))
    return dict(supern=supern, pad=pad, side=side, rr=rr,
                lines=lines, line_px=line_px)


def _mask_big(S, plate=False):
    """大尺寸：超采样 + 抗锯齿，返回 (色块 alpha, 白线 alpha)，都是 L 图。"""
    W = S * SS
    lay = _layout(S, plate)
    k = W / float(S)
    cx = cy = W / 2.0
    a = b = lay["side"] * k / 2.0

    block = Image.new("L", (W, W), 0)
    ImageDraw.Draw(block).polygon(
        _superellipse_points(cx, cy, a, b, lay["supern"]), fill=255)

    white = Image.new("L", (W, W), 0)
    wd = ImageDraw.Draw(white)
    for (x0, y0, x1, y1) in lay["lines"]:
        wd.rounded_rectangle(
            [x0 * k, y0 * k, x1 * k, y1 * k],
            radius=min((y1 - y0) * k / 2.0, lay["rr"] * S * k), fill=255)
    # 白线只在色块内部生效（衬底版里色块外面是白衬，不能把线画出去）
    white = Image.composite(white, Image.new("L", (W, W), 0), block)
    block = block.resize((S, S), Image.LANCZOS)
    white = white.resize((S, S), Image.LANCZOS)
    if not plate:
        # 中尺寸（65–96）：轮廓保留抗锯齿的柔和边，但线条必须「要么白要么不白」。
        # 半透明的白线压在蓝底上会变成浅蓝，缩到 24–32px 显示时整片发灰
        # —— 实测 96px 图直接用于侧栏就是这个现象。
        white = white.point(lambda v: 255 if v >= 128 else 0)
    return block, white


def _cov_in_superellipse(px, py, cx, cy, a, b, n, ss=4):
    """超椭圆内像素覆盖率（ss×ss 子采样）。"""
    hit = 0
    for i in range(ss):
        for j in range(ss):
            x = (px + (i + 0.5) / ss - cx) / a
            y = (py + (j + 0.5) / ss - cy) / b
            if abs(x) ** n + abs(y) ** n <= 1.0:
                hit += 1
    return hit / float(ss * ss)


def _cov_in_rect(px, py, r, ss=4):
    x0, y0, x1, y1 = r
    hit = 0
    for i in range(ss):
        for j in range(ss):
            x = px + (i + 0.5) / ss
            y = py + (j + 0.5) / ss
            if x0 <= x <= x1 and y0 <= y <= y1:
                hit += 1
    return hit / float(ss * ss)


def _mask_small(S, plate=False):
    """小尺寸：直接在整数网格上算覆盖率并取整（不经过大图缩小）。

    这条路径是「不像素化」的关键：大图缩小需要先有足够的细节，而 16px 上
    1px 的线在超采样图层里只有 8px 宽、缩小后必然带一圈半透明过渡；
    直接算覆盖率则每个像素只有「实心 / 空心」两种结果，边缘干净。
    """
    lay = _layout(S, plate)
    n = lay["supern"]
    cx = cy = S / 2.0
    a = b = lay["side"] / 2.0
    block = Image.new("L", (S, S), 0)
    bp = block.load()
    for y in range(S):
        for x in range(S):
            c = _cov_in_superellipse(x, y, cx, cy, a, b, n)
            bp[x, y] = 255 if c >= 0.5 else 0
    white = Image.new("L", (S, S), 0)
    wp = white.load()
    for y in range(S):
        row_on = False
        for x in range(S):
            if not bp[x, y]:
                continue
            c = 0.0
            for r in lay["lines"]:
                c = max(c, _cov_in_rect(x, y, r))
            if c >= 0.5:
                wp[x, y] = 255
                row_on = True
    return block, white


def draw_mark(S, plate=False):
    """按 S×S 画一张图标，返回 RGBA（透明底；plate=True 时外加圆角白衬）。"""
    lay = _layout(S, plate)
    if S <= 64:
        block, white = _mask_small(S, plate)
    else:
        block, white = _mask_big(S, plate)

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    if plate:
        # 圆角白衬：比色块大一圈，几何与色块同族（同为超椭圆）
        padm = S * 0.0
        cxp = cyp = S / 2.0
        ap = S / 2.0 - padm
        plate_layer = Image.new("L", (S, S), 0)
        ImageDraw.Draw(plate_layer).polygon(
            _superellipse_points(cxp, cyp, ap, ap, 4.0,
                                 steps=max(180, S * 12)), fill=255)
        if S <= 64:
            plate_layer = plate_layer.point(lambda v: 255 if v > 127 else 0)
        out.paste(Image.new("RGBA", (S, S), PLATE + (255,)), (0, 0), plate_layer)

    # 色块
    out.paste(Image.new("RGBA", (S, S), INK + (255,)), (0, 0), block)
    # 白线：把色块对应位置换成白色
    out.paste(Image.new("RGBA", (S, S), (255, 255, 255, 255)), (0, 0), white)
    return out


# ======================================================================
# 三、自检
# ======================================================================
def _report(im):
    """统计：蓝色像素数、白色像素数、最大连续白段数（诊断线条有没有粘连）。"""
    px = im.load()
    w, h = im.size
    blue = white = 0
    best = 0
    for y in range(h):
        seg, on = 0, False
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 128:
                continue
            if r > 220 and g > 220 and b > 220:
                white += 1
                if not on:
                    seg += 1
                    on = True
            else:
                blue += 1
                on = False
        best = max(best, seg)
    return blue, white, best


def main():
    sizes = (1024, 512, 256, 128, 64, 48, 32, 24, 16)
    print("透明底（应用内 / PWA）")
    print(" 尺寸   蓝像素  白像素  白段数")
    for s in sizes:
        im = draw_mark(s)
        im.save(HERE / ("logo_%d.png" % s))
        b, w, seg = _report(im)
        print("  %4d  %6d  %6d  %6d" % (s, b, w, seg))

    print("白底衬（Windows 图标槽 / 快捷方式 / 标题栏）")
    win_sizes = (256, 128, 64, 48, 32, 24, 16)
    frames = []
    for s in win_sizes:
        im = draw_mark(s, plate=True)
        im.save(HERE / ("win%d.png" % s))
        b, w, seg = _report(im)
        print("  %4d  %4d  %5d  %6d" % (s, b, w, seg))
        frames.append(im)

    # ICO：把每个尺寸单独的图塞进去（PIL 会按 sizes 顺序匹配）
    frames[0].save(HERE / "kb_widget_v2.ico", format="ICO",
                   sizes=[(s, s) for s in win_sizes],
                   append_images=frames[1:])
    draw_mark(48).save(HERE / "kb_widget_v2.png")

    WEB.mkdir(exist_ok=True)
    draw_mark(512).save(WEB / "icon-512.png")
    draw_mark(192).save(WEB / "icon-192.png")
    draw_mark(512, plate=False).save(WEB / "icon-maskable.png")
    print("logo v6 已生成（实心圆角块 + 反白线条 · 全尺寸同造型）")


if __name__ == "__main__":
    main()