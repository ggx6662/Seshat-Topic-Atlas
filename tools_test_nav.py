# -*- coding: utf-8 -*-
"""导航历史测试：页面跳进去必须能退回来。

只测 App 的历史栈逻辑，不打开窗口全部页面（快）。
干跑三个场景：
  1. 顺序跳 5 页，一路后退能回到起点
  2. 后退后再跳新页，前进栈必须被截断（不能前进到"已放弃的分支"）
  3. 同一页重复 goto 不产生重复历史条目
"""
import sys

import tkinter as tk

sys.path.insert(0, ".")
import app_main  # noqa: E402

OK = [0]
BAD = []


def check(name, cond, detail=""):
    if cond:
        OK[0] += 1
        print("  [ok]  ", name)
    else:
        BAD.append(name)
        print("  [FAIL]", name, detail)


def main():
    root = tk.Tk()
    root.withdraw()
    app = app_main.App()
    app._record_off = True

    # ---- 1. 顺序跳，逐级后退
    app.history = []
    app.hist_pos = -1
    for k in ("home", "topic", "mentor", "venue", "library"):
        app.goto(k)
    check("跳转后位置在末页", app.hist_pos == 4, "%r" % (app.history,))
    check("栈里是 5 条", len(app.history) == 5)
    seen = []
    for _ in range(4):
        app.nav_back()
        seen.append(app.current)
    check("连退 4 次回到 home", app.current == "home", "-> %r" % seen)
    check("回到起点后不能再退", app.hist_pos == 0)

    # ---- 2. 后退后跳新页，前进栈截断
    app.nav_forward()
    check("前进一次到 topic", app.current == "topic", app.current)
    app.goto("gap")
    check("新跳转后 history 被截断", len(app.history) == 3, "%r" % (app.history,))
    check("不能再前进到被放弃的分支", app.hist_pos == len(app.history) - 1)

    # ---- 3. 同页重复 goto 不重复记账
    n0 = len(app.history)
    app.goto("gap")
    app.goto("gap")
    check("同页重复 goto 不产生重复条目", len(app.history) == n0, "%d vs %d" % (len(app.history), n0))

    # ---- 4. 面包屑有内容
    app.goto("mentor")
    txt = app.crumb.cget("text")
    check("面包屑非空且含页名", "导师与院校" in txt, txt)

    root.destroy()
    print("\n==== 结果 ====")
    print("通过 %d / 失败 %d" % (OK[0], len(BAD)))
    for b in BAD:
        print("  -", b)
    return 0 if not BAD else 1


if __name__ == "__main__":
    sys.exit(main())