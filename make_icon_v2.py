#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""550W 知识库助手图标 v2：大字标 + 极简描边，小尺寸优先可读。"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_DIR = Path(r"C:\Windows\Fonts")
BG = (3, 24, 38, 255)
BORDER = (107, 231, 255, 200)
TXT = (230, 250, 255, 255)
GLOW = (107, 231, 255, 255)
DOT = (67, 255, 201, 255)


def _font(px):
    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"):
        p = FONT_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), px)
    return ImageFont.load_default(size=px)


def make(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = max(2, int(size * 0.22))
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)
    bw = max(1, int(size * 0.035))
    d.rounded_rectangle([bw // 2, bw // 2, size - 1 - bw // 2, size - 1 - bw // 2],
                        radius=radius, outline=BORDER, width=bw)

    if size <= 24:
        label = "W"
    elif size <= 40:
        label = "550"
    else:
        label = "550W"
    max_w = size * (0.52 if label == "W" else 0.80)
    max_h = size * 0.46
    px = max(7, int(max_h))
    while px > 6:
        font = _font(px)
        box = d.textbbox((0, 0), label, font=font)
        if box[2] - box[0] <= max_w and box[3] - box[1] <= max_h:
            break
        px -= 1
    font = _font(px)
    box = d.textbbox((0, 0), label, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = (size - tw) / 2 - box[0]
    y = (size - th) / 2 - box[1] + (size * 0.02 if size > 24 else 0)
    stroke = max(1, int(size * 0.018)) if size >= 32 else 0
    d.text((x, y), label, font=font, fill=TXT,
           stroke_width=stroke, stroke_fill=GLOW)

    rad = max(2, int(size * 0.065))
    cx, cy = size - rad - int(size * 0.12), rad + int(size * 0.12)
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=DOT,
              outline=BG, width=max(1, size // 48))
    return img


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make(s) for s in sizes]
    ico = HERE / "kb_widget_v2.ico"
    imgs[0].save(ico, format="ICO", sizes=[(s, s) for s in sizes],
                 append_images=imgs[1:])
    make(48).save(HERE / "kb_widget_v2.png")
    make(256).save(HERE / "kb_widget_v2_preview.png")
    print("icon ok: " + str(ico))


if __name__ == "__main__":
    main()
