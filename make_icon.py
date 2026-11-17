#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成知识库助手的专属图标（雷达/文献检索风格）。

产物: kb_widget.ico（多尺寸）、kb_widget.png（48px，卡片标题用）
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ACCENT = (92, 225, 255, 255)
ACCENT_SOFT = (92, 225, 255, 70)
RING = (92, 225, 255, 90)
RING2 = (92, 225, 255, 140)
RING3 = (92, 225, 255, 190)
DOT = (56, 255, 200, 255)
FG = (217, 246, 255, 255)
BG = (2, 18, 28, 255)


def make(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1],
                        radius=int(size * 0.22), fill=BG)
    cx = cy = size / 2.0
    for k, color in ((0.34, RING), (0.56, RING2), (0.78, RING3)):
        rad = size * k
        d.arc([cx - rad, cy - rad, cx + rad, cy + rad],
              start=0, end=360, fill=color, width=max(1, int(size * 0.045)))
    rad0 = size * 0.38
    d.pieslice([cx - rad0, cy - rad0, cx + rad0, cy + rad0],
               start=-95, end=-10, fill=ACCENT_SOFT)
    ang = math.radians(25)
    px = cx + math.cos(ang) * size * 0.42
    py = cy + math.sin(ang) * size * 0.42
    r = max(1, size * 0.07)
    d.ellipse([px - r, py - r, px + r, py + r], fill=DOT)
    r0 = max(1, size * 0.08)
    d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], fill=FG)
    d.ellipse([cx - r0 * 0.45, cy - r0 * 0.45, cx + r0 * 0.45, cy + r0 * 0.45],
              fill=ACCENT)
    if size >= 32:
        try:
            from PIL import ImageFont
            font = ImageFont.load_default(size=int(size * 0.34))
            d.text((cx, cy + size * 0.10), "550W", font=font, fill=FG,
                   anchor="mm", stroke_width=max(1, int(size * 0.025)),
                   stroke_fill=ACCENT)
        except Exception:
            pass
    return img


def main():
    sizes = [16, 24, 32, 64, 128, 256]
    imgs = [make(s) for s in sizes]
    ico = HERE / "kb_widget.ico"
    imgs[0].save(ico, format="ICO", sizes=[(s, s) for s in sizes],
                 append_images=imgs[1:])
    png = HERE / "kb_widget.png"
    make(48).save(png)
    print("icon ok: " + str(ico))
    print("png ok: " + str(png))


if __name__ == "__main__":
    main()
