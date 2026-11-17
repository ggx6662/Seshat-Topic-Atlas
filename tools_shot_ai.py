# -*- coding: utf-8 -*-
"""截图选题工坊与创新点库，确认 AI 按钮就位、布局没被挤坏。

不触发真实 LLM 调用（没配 key 时点 AI 只会 toast + 跳设置页）。
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


def shot(app, out, name):
    doc = tools_shot.find_window("知识库助手", True)
    if not doc:
        print("窗口没找到")
        return
    ok = tools_shot.grab(doc[0], doc[2], os.path.join(out, name))
    print("saved", name, ok)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "screenshots"
    os.makedirs(out, exist_ok=True)
    app = app_main.App()
    pump(app, 1.0)

    app.goto("topic")
    pump(app, 0.5)
    tp = app.pages["topic"]
    tp.entry.delete(0, "end")
    tp.entry.insert(0, "红外小目标检测")
    tp.generate()
    t0 = time.time()
    while not tp.cands and time.time() - t0 < 60:
        app.update()
        time.sleep(0.05)
    pump(app, 1.5)
    print("候选", len(tp.cands))
    shot(app, out, "14-topic-ai.png")

    app.goto("ideas")
    pump(app, 1.2)
    shot(app, out, "15-ideas-ai.png")


if __name__ == "__main__":
    main()