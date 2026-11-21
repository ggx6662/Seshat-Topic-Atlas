# -*- coding: utf-8 -*-
"""截设置页底部的「网页体验端」卡片（含二维码）。

要点（踩过的坑都写在注释里）：
  · 配置要显示真实值（7 天 / 8 条检索词），所以 kb_widget.CONFIG_FILE
    被 tools_isolate 的 ALLOW_REAL 白名单放行，不隔离；其余用户数据照旧隔离。
  · **必须先 `_qr_show()` 再滚动**。反过来做的话，二维码 216px 高插进来
    会把内容撑高，之前算好的位置就不在目标处了。
  · 窗口别开太高：`1360x1500` 超出了 1080p 屏幕可用高度，Windows 会把窗口
    截断到屏幕高度，PrintWindow 抓到的下半截就是空白 —— 二维码明明在可视区
    （rooty=934 < Canvas 底 1174）却拍不到，2026-11-13 实测踩过。
    真正的解法是按 Canvas 可视高度算比例 moveto，而不是把窗口拉高。
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import kb_widget  # noqa: E402,F401  必须在 isolate 之前 import，__orig__ 才会记录原始路径
import tools_isolate  # noqa: E402

ISO = tools_isolate.isolate()

import tools_shot  # noqa: E402
import web_server as W  # noqa: E402
from app_main import App  # noqa: E402

PORT = 8901
ok, msg = W.start(port=PORT)
print("服务：", msg)
if not ok:
    sys.exit(1)

root = App()
root.geometry("1360x980+30+20")          # 不超过 1080p 可用高度
for _ in range(40):
    root.update()
root.goto("settings")
for _ in range(40):
    root.update()

pg = root.pages["settings"]
print("配置路径：", kb_widget.CONFIG_FILE)
print("抓取窗口：", kb_widget.load_config().get("days_back"))

# ① 先展开二维码（会插入 ~216px 高的内容）
pg._qr_show()
# 必须「边等真实时间边 pump」：Card 的高度同步走 after(16) 防抖，
# 纯粹空转 root.update() 时 Tk 的定时器来不及到期，卡片就一直停在旧高度，
# 二维码被画到卡片外面（2026-11-13 实测）。
for _ in range(30):
    root.update()
    time.sleep(0.02)
print("二维码格子数：", len(pg._qr_canvas.find_all()) - 1)
card = pg._qr_box.master.master.master
print("卡片高：", card.winfo_height(), "（展开前约 212，展开后应约 438）")

canvas = None
w = pg.body
while w is not None:
    if w.winfo_class() == "Canvas":
        canvas = w
        break
    w = w.master
if canvas is None:
    print("没找到 canvas")
    sys.exit(1)

# ② 精确滚到「二维码完整可见」：目标 = 让二维码底边落在可视区下方留 20px 处
inner = canvas.nametowidget(canvas.itemcget(canvas.find_all()[0], "window"))
qr = pg._qr_canvas
qr_bottom = qr.winfo_rooty() - inner.winfo_rooty() + qr.winfo_height()
vis = canvas.winfo_height()
total = max(inner.winfo_reqheight(), 1)
frac = max(0.0, min(1.0, (qr_bottom + 20 - vis) / float(total)))
canvas.yview_moveto(frac)
for _ in range(25):
    root.update()
    time.sleep(0.02)
print("二维码底=%d 可视高=%d 内容高=%d → yview=%s" % (qr_bottom, vis, total, canvas.yview()))

time.sleep(0.6)
for _ in range(10):
    root.update()

hwnd, title, rect, _area = tools_shot.find_window("塞莎特——题谱", True)
print("窗口：", title)
out = os.path.join(HERE, "screenshots", "16-settings-qr.png")
tools_shot.grab(hwnd, rect, out)
print("已保存", out, os.path.getsize(out), "bytes")

W.stop()
root.destroy()
tools_isolate.cleanup(ISO.get("__tmp__"))