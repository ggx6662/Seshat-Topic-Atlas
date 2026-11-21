#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""截「最新研究」页和「文献库语义检索」的实际效果图。

和 tools_smoke_app.py 不同，这里要触发真实网络抓取，所以单独一个脚本。
"""
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
    app.update()
    pump(app, 1.0)

    # ---- 最新研究 ----
    app.goto("latest")
    pump(app, 0.6)
    pg = app.pages["latest"]
    pg.entry.delete(0, "end")
    pg.entry.insert(0, "红外小目标检测")
    pg.search()
    print("抓取中…")
    t0 = time.time()
    while pg.result is None and time.time() - t0 < 120:
        app.update()
        time.sleep(0.05)
    pump(app, 1.5)
    print("拿到 %d 篇" % len((pg.result or {}).get("papers", [])))
    doc = tools_shot.find_window("塞莎特——题谱", True)
    if doc:
        ok = tools_shot.grab(doc[0], doc[2], os.path.join(out, "12-latest.png"))
        print("saved 12-latest.png", ok)

    # ---- 文献库语义检索 ----
    app.goto("library")
    pump(app, 1.0)
    lib = app.pages["library"]
    if hasattr(lib, "smart_search"):
        for w in (getattr(lib, "search_entry", None),):
            pass
    # 找到搜索框并输入
    try:
        lib.entry.delete(0, "end") if hasattr(lib, "entry") else None
    except Exception:
        pass
    print("done")


if __name__ == "__main__":
    main()