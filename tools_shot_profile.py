#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""截「个人画像」页 —— 用临时画像数据，不动用户的 researcher_profile.json。

    python tools_shot_profile.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import profile_memory as PM  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="profcam_")
PM.PROFILE_FILE = __import__("pathlib").Path(os.path.join(_TMP, "researcher_profile.json"))

PM.set_identity(stage="硕士在读", school="东南大学",
                lab="智能视觉实验室", advisor="张老师",
                goal="投 ICIP / Signal Processing: Image Communication",
                resources="单卡 4090，跑得动 7B 多模态")
PM.set_state(urgency=82, interest=70, mood="焦虑")
PM.remember("红外小目标检测的候选方案要做消融，卡在 ROI 对齐的复现", tags=["卡住", "复现"])
PM.remember("导师要求下周组会汇报中期进展，PPT 还没开始", tags=["截止", "组会"])
PM.remember("看到 Mamba 在融合任务上的结果不错，以后可以试试", tags=["收藏", "以后"])
PM.bump_pref("fields", "红外小目标检测", 4)
PM.bump_pref("fields", "图像融合", 3)
PM.bump_pref("categories", "计算机视觉", 5)

import tkinter as tk  # noqa: E402
import app_theme as T  # noqa: E402
import tools_shot as TS  # noqa: E402


class FakeApp(object):
    def toast(self, *a, **k):
        pass

    def post(self, fn):
        fn()


def main():
    root = tk.Tk()
    root.title("个人画像验证")
    root.configure(bg=T.BG)
    root.geometry("1320x900")
    root.update()
    from page_profile import ProfilePage
    pg = ProfilePage(root, FakeApp())
    pg.pack(fill="both", expand=True)
    pg.reload()
    for _ in range(60):
        root.update()
    out = os.path.join(HERE, "screenshots", "30-profile.png")
    found = TS.find_window("个人画像验证", True)
    if found:
        TS.grab(found[0], found[2], out)
        print("saved:", out)
    else:
        print("window not found")
    root.destroy()


if __name__ == "__main__":
    main()