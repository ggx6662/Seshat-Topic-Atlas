#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""截「设置页的大模型接入区」。不需要真实 key。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app_main      # noqa: E402
import tools_shot    # noqa: E402


def pump(app, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.update()
        time.sleep(0.02)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "screenshots"
    os.makedirs(out, exist_ok=True)
    app = app_main.App()
    pump(app, 1.0)
    app.goto("settings")
    pump(app, 1.2)
    doc = tools_shot.find_window("塞莎特——题谱", True)
    if not doc:
        print("窗口没找到")
        return
    ok = tools_shot.grab(doc[0], doc[2], os.path.join(out, "13-settings.png"))
    print("saved 13-settings.png", ok)


if __name__ == "__main__":
    main()