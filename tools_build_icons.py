# -*- coding: utf-8 -*-
"""生成 PWA 图标（构建期工具）。

图标造型与桌面端、Web 版共用 `make_logo.draw_mark()`：棕底圆角方块 +
奶白六边形节点。以前这里单独画「KB」字母，导致同一枚产品在任务栏、
侧栏和手机桌面上是三个样子，别再分叉。

    python tools_build_icons.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "web_static")


def main():
    try:
        from make_logo import draw_mark
    except Exception as exc:
        print("没有 Pillow 或图标生成器不可用，跳过：%s" % exc)
        return 1
    os.makedirs(OUT, exist_ok=True)
    for size, name in ((512, "icon-512.png"), (192, "icon-192.png"), (48, "icon-48.png")):
        p = os.path.join(OUT, name)
        draw_mark(size).save(p, "PNG", optimize=True)
        print("%s  %d bytes" % (name, os.path.getsize(p)))
    p = os.path.join(OUT, "icon-maskable.png")
    draw_mark(512).save(p, "PNG", optimize=True)
    print("icon-maskable.png  %d bytes" % os.path.getsize(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
