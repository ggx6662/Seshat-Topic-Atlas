# -*- coding: utf-8 -*-
"""文献库检索截图：本地库 / arXiv 全库语义 / 多词交集三条路各截一张。

    python tools_shot_search.py

注意：会往 search_log.json 里写几条测试查询 —— 这是设计如此（截图要展示
「你搜过什么」这类真实内容时必须有记录），但为避免污染用户真实频率统计，
脚本结束时会把新增的条目删回去。
"""
import json
import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app_theme as T  # noqa: E402
import search_log  # noqa: E402
import tools_shot as TS  # noqa: E402

SNAP = os.path.join(HERE, "screenshots")
SL = os.path.join(HERE, "search_log.json")


class FakeApp(object):
    def __init__(self):
        self.toast_text = ""
        self._jobs = []

    def post(self, fn):
        self._jobs.append(fn)

    def pump(self):
        while self._jobs:
            fn = self._jobs.pop(0)
            fn()

    def toast(self, msg, color=None):
        self.toast_text = msg

    def mark_dirty(self, key=None):
        pass

    def goto(self, key, **kw):
        pass


def pump_for(root, app, sec, stop=None):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        app.pump()
        if stop is not None and stop():
            return True
        time.sleep(0.02)
    return False


def snap(root, name):
    for _ in range(20):
        root.update()
        time.sleep(0.02)
    found = TS.find_window("检索截图", True)
    if not found:
        print("window not found")
        return None
    path = os.path.join(SNAP, "%s.png" % name)
    TS.grab(found[0], found[2], path)
    print("saved:", path)
    return path


def main():
    os.makedirs(SNAP, exist_ok=True)
    before = None
    if os.path.exists(SL):
        before = open(SL, encoding="utf-8").read()

    root = tk.Tk()
    root.title("检索截图")
    root.configure(bg=T.BG)
    root.geometry("1320x900+20+10")
    root.update()
    app = FakeApp()
    import page_library
    page = page_library.LibraryPage(root, app)
    page.pack(fill="both", expand=True)
    pump_for(root, app, 20, stop=lambda: bool(getattr(page, "rows", None)))

    # ① 本地库：语义检索
    page.entry.delete(0, "end")
    page.entry.insert(0, "红外小目标漏检")
    page.smart_search()
    pump_for(root, app, 20, stop=lambda: getattr(page, "_mode", "") == "search")
    snap(root, "search-1-local")

    # ② arXiv 全库语义检索
    page.entry.delete(0, "end")
    page.entry.insert(0, "红外小目标检测")
    page.vector_search()
    pump_for(root, app, 120,
             stop=lambda: "索引" in page.count_lbl.cget("text") or
             "Top" in page.count_lbl.cget("text") or
             "失败" in page.count_lbl.cget("text"))
    snap(root, "search-2-vector")

    # ③ 多词交集检索
    page.entry.delete(0, "end")
    page.entry.insert(0, "去雾 图像 -restoration")
    page.and_search()
    pump_for(root, app, 180,
             stop=lambda: "命中" in page.count_lbl.cget("text") or
             "失败" in page.count_lbl.cget("text"))
    snap(root, "search-3-and")

    page.destroy()
    root.update()
    root.destroy()

    # 还原日志：截图不该改变用户的真实使用频率
    if before is None:
        try:
            os.remove(SL)
        except OSError:
            pass
    else:
        with open(SL, "w", encoding="utf-8") as f:
            f.write(before)
    print("search_log restored")


if __name__ == "__main__":
    main()