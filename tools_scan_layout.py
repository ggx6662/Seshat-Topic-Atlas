"""扫全部页面的「看得见的毛病」：文字被裁、跑出滚动区。

用法（隔离环境，不碰真实数据）：

    D:\\miniconda3\\python.exe tools_scan_layout.py 1440 900
    D:\\miniconda3\\python.exe tools_scan_layout.py 1240 800

为什么要有这个脚本：Tk 的 Label 没有省略号，文字放不下就直接被裁掉
（侧栏「塞莎特——题」少了「谱」就是这么来的），界面上不报任何错。
靠人眼一页一页找不可靠，所以这里把每个文字控件的「请求尺寸」和
「实际尺寸」逐个对一遍 —— 请求 > 实际就说明有字没显示出来。

两类检查：
  1. 裁字/裁高：Label 的 reqwidth > width（或 reqheight > height）。
  2. 越界：控件右边缘超出它最近的滚动区的 canvas 可视宽度。

输出按页面分组，最后一行汇总。有问题时退出码 1，可直接串进回归脚本。
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PAGES = ["home", "topic", "gap", "latest", "ideas", "skills", "mentor",
         "venue", "materials", "library", "map", "plan", "profile",
         "settings"]


def _is_text(w):
    """只检查真的在显示文字的控件。"""
    import tkinter as tk
    if isinstance(w, tk.Entry):
        return False
    if not isinstance(w, (tk.Label, tk.Button, tk.Checkbutton,
                          tk.Radiobutton, tk.Menubutton)):
        return False
    try:
        return bool(str(w.cget("text")))
    except Exception:
        return False


def _text_of(w, limit=30):
    try:
        t = str(w.cget("text"))
    except Exception:
        return "?"
    t = t.replace("\n", "⏎")
    return t if len(t) <= limit else t[:limit] + "…"


def _path(w, root, depth=5):
    """给个「Frame/Frame/Label」式的短路径，方便定位到具体容器。"""
    parts = []
    cur = w
    for _ in range(depth):
        if cur is root or cur is None:
            break
        parts.append(cur.winfo_class())
        cur = cur.master
    return "/".join(reversed(parts))


def _walk(w, depth=0):
    if depth > 14:
        return
    for c in w.winfo_children():
        yield c
        yield from _walk(c, depth + 1)


def _check(w, page_root):
    """返回这个控件的问题列表（通常 0 或 1 条）。"""
    import app_theme as T
    out = []
    if not w.winfo_ismapped():
        return out
    ww, wh = w.winfo_width(), w.winfo_height()
    if ww <= 1 or wh <= 1:
        return out
    if _is_text(w):
        rw = w.winfo_reqwidth()
        if rw - ww >= 3:
            out.append("裁字 [%s] 「%s」 需要%d 只有%d"
                       % (_path(w, page_root), _text_of(w), rw, ww))
        elif "\n" not in _text_of(w):
            rh = w.winfo_reqheight()
            if rh - wh >= 3:
                out.append("裁高 [%s] 「%s」 需要%d 只有%d"
                           % (_path(w, page_root), _text_of(w), rh, wh))
    # 越界：控件右边缘超出最近的滚动区 canvas。
    # canvas 宽度是 1 说明这一屏还没布局（空状态提示常见），此时量不出
    # 真实可视宽度，任何越界结论都不可信 —— 直接跳过，避免误报。
    cur = w.master
    while cur is not None and not isinstance(cur, T.ScrollArea):
        cur = cur.master
    if isinstance(cur, T.ScrollArea) and _is_text(w):
        cv = cur.canvas
        if cv.winfo_width() > 60 and \
                w.winfo_rootx() + ww > cv.winfo_rootx() + cv.winfo_width() + 2:
            out.append("越界 [%s] 「%s」 右缘%d > 可视%d"
                       % (_path(w, page_root), _text_of(w),
                          w.winfo_rootx() + ww - cv.winfo_rootx(),
                          cv.winfo_width()))
    return out


def _menu_weight(key):
    """某个页面大概要占多少个原生 Menu（OptionMenu 一个就吃一个 HMENU）。

    Windows 上 Tk 的菜单句柄回收不及时，同一进程里建过太多页面就会撞
    `No more menus can be allocated`。把重的页排前面，能在干净的进程里把它们量完。
    这里只是排序用的权重，不追求精确，按源码里出现的 OptionMenu 数量估。
    """
    guess = {"profile": 12, "topic": 2, "latest": 1, "plan": 2, "map": 1,
             "mentor": 1, "venue": 2, "library": 1, "materials": 1,
             "ideas": 1, "skills": 1, "gap": 1, "home": 0, "settings": 0}
    return guess.get(key, 0)


def main():
    import tools_isolate
    tools_isolate.ALLOW_REAL.discard("llm_bridge.CONFIG_FILE")
    tools_isolate.isolate()

    import app_main
    W = int(sys.argv[1]) if len(sys.argv) > 1 else 1440
    H = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    app = app_main.App()
    app.geometry("%dx%d" % (W, H))
    app.update()
    time.sleep(1.0)
    app.update()

    total = 0
    try:
        # 逐页构建 + 测量 + **扫描完立刻销毁**。
        # 2026-11-20：以前是「先把 14 页都建出来」再逐页测，页全活着时
        # page_profile 的 tk.OptionMenu 一共要分配几十个原生 Menu，
        # Tk 会抛 `_tkinter.TclError: No more menus can be allocated.`
        # 直接崩在最后一页。一次只留一页就不会撞上限。
        #
        # 2026-11-20 第二次修正：即使逐页销毁也不够。Tk 在 Windows 上给每个
        # OptionMenu 分配的是原生 HMENU 句柄，`destroy()` 之后这批句柄不会
        # 立刻归还给系统，而 page_profile 一次要建十来个 OptionMenu。
        # 扫到它时前面的页已经把句柄耗得七七八八，仍是同一个报错。
        # 所以把**面板 OptionMenu 最多的页排在最先**，让它在最干净的进程里建：
        # 顺序按「每页 OptionMenu 个数」降序，值相等时保持原顺序。
        order = sorted(PAGES, key=lambda k: -_menu_weight(k))
        for p in order:
            app.goto(p)
            app.update()
            time.sleep(0.18)
            app.update()
            page = app.page(p)
            found = []
            for w in _walk(page):
                try:
                    found.extend(_check(w, page))
                except Exception:
                    pass
            if found:
                print("\n=== %s (%d) ===" % (p, len(found)))
                for line in found:
                    print("  " + line)
                total += len(found)
            # 测完就把这页拆掉，释放它占的原生资源（Menu 等）
            try:
                if p != order[-1] and str(p) in app.pages:
                    dead = app.pages.pop(str(p))
                    dead.destroy()
                    app.update()
            except Exception:
                pass
    finally:
        print("\n合计问题 %d 处（%dx%d）" % (total, W, H))
        app.destroy()
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())