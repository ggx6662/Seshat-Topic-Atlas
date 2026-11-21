# -*- coding: utf-8 -*-
"""生成三端共用的品牌图标：圆角棕底 + 奶白六边形节点。

造型与 Web 版 `competition/site/assets/favicon.svg` 是同一枚标记，只是
按图标尺寸做了两档简化：

  · 32px 及以上：描边六边形 + 三个节点 + 金色中心，细节完整；
  · 28px 及以下：改画实心六边形 + 深色中心点。细描边在 16px 上不足
    一个整像素，缩小后会碎成一圈灰点；实心轮廓仍是同一个剪影，任务栏
    和侧栏里能认出来。

输出：
  透明底 logo_1024/512/256/128/64/48/32/24/16.png
  白底衬 win{256,128,64,48,32,24,16}.png + kb_widget_v2.ico
  48px kb_widget_v2.png
  网页 PWA icon-{512,192,48}.png + icon-maskable.png
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
WEB = HERE / "web_static"

BROWN = (110, 79, 54)
CREAM = (248, 239, 223)
GOLD = (232, 201, 138)
PLATE = (246, 239, 227)

SS = 8


def _superellipse(cx, cy, a, b, n=4.0, steps=720):
    pts = []
    e = 2.0 / n
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        ct, st = math.cos(t), math.sin(t)
        pts.append((cx + math.copysign(abs(ct) ** e, ct) * a,
                    cy + math.copysign(abs(st) ** e, st) * b))
    return pts


def _hex_points(cx, cy, r):
    """尖顶六边形，比例对齐 favicon 的 36×36 坐标。"""
    return [
        (cx, cy - r),
        (cx + r * 0.866, cy - r * 0.5),
        (cx + r * 0.866, cy + r * 0.5),
        (cx, cy + r),
        (cx - r * 0.866, cy + r * 0.5),
        (cx - r * 0.866, cy - r * 0.5),
    ]


def draw_mark(S, plate=False):
    W = S * SS
    k = float(SS)
    out = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)

    if plate:
        d.polygon(_superellipse(W / 2, W / 2, W / 2, W / 2), fill=PLATE + (255,))
        inset = W * 0.085
    else:
        inset = 0.0

    half = W / 2 - inset
    d.polygon(_superellipse(W / 2, W / 2, half, half), fill=BROWN + (255,))

    cx = cy = W / 2.0
    r = half * 0.62
    hexpts = _hex_points(cx, cy, r)
    detailed = S >= 32

    if detailed:
        stroke = max(2.0 * k, half * 0.115)
        d.line(hexpts + [hexpts[0]], fill=CREAM + (255,), width=int(round(stroke)),
               joint="curve")
        node = half * 0.075
        for i in (1, 5, 3):
            px, py = hexpts[i]
            d.ellipse([px - node, py - node, px + node, py + node], fill=CREAM + (255,))
        dot = half * 0.150
        d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=GOLD + (255,))
    else:
        d.polygon(hexpts, fill=CREAM + (255,))
        dot = half * 0.175
        d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=BROWN + (255,))

    return out.resize((S, S), Image.LANCZOS)


def main():
    sizes = (1024, 512, 256, 128, 64, 48, 32, 24, 16)
    for s in sizes:
        draw_mark(s).save(HERE / ("logo_%d.png" % s))

    win_sizes = (256, 128, 64, 48, 32, 24, 16)
    frames = []
    for s in win_sizes:
        im = draw_mark(s, plate=True)
        im.save(HERE / ("win%d.png" % s))
        frames.append(im)
    frames[0].save(HERE / "kb_widget_v2.ico", format="ICO",
                   sizes=[(s, s) for s in win_sizes], append_images=frames[1:])
    draw_mark(48).save(HERE / "kb_widget_v2.png")

    WEB.mkdir(exist_ok=True)
    draw_mark(512).save(WEB / "icon-512.png")
    draw_mark(192).save(WEB / "icon-192.png")
    draw_mark(48).save(WEB / "icon-48.png")
    draw_mark(512).save(WEB / "icon-maskable.png")
    print("品牌图标已生成：logo_*.png / win*.png / kb_widget_v2.ico / web_static/icon-*.png")


if __name__ == "__main__":
    main()
