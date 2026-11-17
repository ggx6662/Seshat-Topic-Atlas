# -*- coding: utf-8 -*-
"""生成 PWA 图标。

为什么不用第三方图标库：整个项目零前端依赖，图标也只有三个尺寸。
用 Tk 的 PhotoImage 画不了抗锯齿圆角，所以这里用 Pillow —— 但**只在构建期用**，
不写进运行时依赖（打包 EXE 时 PIL 是 EXCLUDED 的）。如果没有 Pillow，
退化成纯色方块 + 文字，功能不受影响。

设计：深海军蓝底 + 青色圆角方块轮廓 + 「KB」两个字母，与客户端侧边栏 logo 同构。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "web_static")

try:
    sys.path.insert(0, HERE)
    import design_tokens as D
    BG = D.COLORS["canvas"]
    ACCENT = D.COLORS["primary"]
    ACCENT_DIM = D.COLORS["primary_muted"]
    INK = D.COLORS["ink"]
except Exception:
    BG, ACCENT, ACCENT_DIM, INK = "#061220", "#6BE7FF", "#0E4B63", "#EDF8FF"


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def draw(size, maskable=False):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (size, size), hex2rgb(BG) + (255,))
    d = ImageDraw.Draw(img)
    # maskable 图标要留 20% 安全边距，否则被系统裁成圆形时内容会被切掉
    inset = int(size * 0.20) if maskable else int(size * 0.10)
    r = int((size - inset * 2) * 0.22)
    d.rounded_rectangle([inset, inset, size - inset, size - inset],
                        radius=r, fill=hex2rgb(ACCENT_DIM) + (255,),
                        outline=hex2rgb(ACCENT) + (255,), width=max(2, size // 84))

    # 「550W」竖排太小，改用 KB 两个字母 + 一条底线，小尺寸下仍可辨认
    txt = "KB"
    fs = int(size * 0.34)
    font = None
    for name in ("msyhbd.ttc", "msyh.ttc", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, fs)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    box = d.textbbox((0, 0), txt, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.text(((size - tw) / 2 - box[0], (size - th) / 2 - box[1] - size * 0.02),
           txt, font=font, fill=hex2rgb(INK) + (255,))
    # 底部一条青色短线，呼应界面的强调色
    lw = int(size * 0.26)
    ly = size / 2 + th / 2 + size * 0.10
    d.rounded_rectangle([(size - lw) / 2, ly, (size + lw) / 2, ly + max(2, size // 64)],
                        radius=size // 64, fill=hex2rgb(ACCENT) + (255,))
    return img


def main():
    try:
        import PIL  # noqa: F401
    except Exception:
        print("没有 Pillow，跳过图标生成（PWA 仍可用，只是浏览器不显示自定义图标）")
        return 1
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png")):
        p = os.path.join(OUT, name)
        draw(size).save(p, "PNG", optimize=True)
        print("%s  %d bytes" % (name, os.path.getsize(p)))
    p = os.path.join(OUT, "icon-maskable.png")
    draw(512, maskable=True).save(p, "PNG", optimize=True)
    print("icon-maskable.png  %d bytes" % os.path.getsize(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())