# -*- coding: utf-8 -*-
"""截图单个页面（依次打开多个页面各截一张）。

    python tools_shot_pages.py gap tutorial
"""
import importlib
import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app_theme as T  # noqa: E402
import tools_shot as TS  # noqa: E402


class FakeApp(object):
    def __init__(self, root):
        self.root = root
        self.toast_text = ""
        self.dirty = set()
        self._jobs = []

    def post(self, fn):
        """真 App.post 是把回调丢进队列、由 after(50) 轮询取出来在主线程跑；
        这里直接排队，等主循环 update() 时再执行 —— 在 explore=True 时就会

        Tcl_AsyncDelete: async handler deleted by the wrong thread。
        """
        self._jobs.append(fn)

    def pump(self):
        while self._jobs:
            fn = self._jobs.pop(0)
            try:
                fn()
            except Exception as exc:
                print("post error:", exc)

    def toast(self, msg, color=None):
        self.toast_text = msg

    def mark_dirty(self, key=None):
        self.dirty.add(key)

    def goto(self, key, **kw):
        pass


def main(keys):
    root = tk.Tk()
    root.title("页面截图")
    root.configure(bg=T.BG)
    root.geometry("1320x900+20+10")
    root.update()
    app = FakeApp(root)
    out = []
    for key in keys:
        page = None
        if key in ("gap", "gap-constraint"):
            # gap-constraint 带一份「无算力 + 3 个月」的临时画像，
            # 专门看空白条目下面那行「你做不做得动」；不碰真实画像文件
            if key == "gap-constraint":
                import profile_memory as PM3
                import tempfile as _tf
                from pathlib import Path as _P
                _tmp3 = _tf.mkdtemp(prefix="kbshot-gap-")
                PM3.PROFILE_FILE = _P(_tmp3) / "researcher_profile.json"
                PM3._cache["mtime"] = None
                PM3._cache["data"] = None
                PM3.set_constraints(compute="无算力", months="3 个月内",
                                    style="偏工程", avoid=[])
            import page_gap
            page = page_gap.GapPage(root, app)
        elif key == "profile":
            import page_profile
            page = page_profile.ProfilePage(root, app)
        elif key in ("topic", "topic-fusion", "topic-constraint"):
            # 带一份「时间紧 + 焦虑」的画像，专门看候选卡的排序理由与详情面板换行
            import profile_memory as PM
            import tempfile
            from pathlib import Path
            _tmp = tempfile.mkdtemp(prefix="kbshot-topic-")
            PM.PROFILE_FILE = Path(_tmp) / "researcher_profile.json"
            PM._cache["mtime"] = None
            PM._cache["data"] = None
            PM.set_identity(school="东南大学", lab="智能视觉实验室",
                            advisor="张老师", goal="三个月内投一篇 CV 会议")
            PM.set_state(urgency=95, interest=80, mood="焦虑")
            PM.remember("离投稿只剩两周，改投退路还没想好", tags=["截止"])
            import page_topic
            page = page_topic.TopicPage(root, app)
        elif key == "latest":
            import page_latest
            page = page_latest.LatestPage(root, app)
        elif key == "mentor":
            import page_mentor
            page = page_mentor.MentorPage(root, app)
        elif key == "library":
            import page_library
            page = page_library.LibraryPage(root, app)
        if page is None:
            print("unknown page:", key)
            continue
        page.pack(fill="both", expand=True)
        import time as _t
        deadline = _t.time() + 25
        while _t.time() < deadline:
            root.update()
            app.pump()
            if getattr(page, "data", None) is not None:
                break
            _t.sleep(0.05)
        if key == "topic":
            # 触发一次生成，再点第一个候选，让详情面板把「排序依据」画出来
            try:
                page.entry.delete(0, "end")
                page.entry.insert(0, "红外小目标检测")
                page.generate()
                deadline = _t.time() + 40
                while _t.time() < deadline:
                    root.update()
                    app.pump()
                    if getattr(page, "cands", None):
                        break
                    _t.sleep(0.05)
                if getattr(page, "cands", None):
                    # 新颖性核查在生成之后才跑，8 条要二十多秒。
                    # 不等等就直接截图，详情面板只会显示「这条没有核查」，
                    # 等于这个功能在截图里不存在。
                    nv_deadline = _t.time() + 120
                    while _t.time() < nv_deadline:
                        root.update()
                        app.pump()
                        done = sum(1 for c in page.cands
                                   if (c.get("nov") or {}).get("level"))
                        if done >= min(3, len(page.cands)):
                            break
                        _t.sleep(0.1)
                    page._render_cands()
                    page.select(0)
            except Exception as exc:
                print("topic trigger failed:", exc)
        if key == "topic-fusion":
            # 跨领域模式：A 红外小目标检测 × B 扩散模型 × C 医学影像
            try:
                page.entry.delete(0, "end")
                page.entry.insert(0, "红外小目标检测")
                if not page._fuse_open:
                    page._toggle_fuse()
                page.entry_b.insert(0, "扩散模型")
                page.entry_c.insert(0, "医学影像")
                page.generate()
                deadline = _t.time() + 60
                while _t.time() < deadline:
                    root.update()
                    app.pump()
                    if getattr(page, "cands", None):
                        break
                    _t.sleep(0.05)
                if getattr(page, "cands", None):
                    page.select(0)
            except Exception as exc:
                print("topic-fusion trigger failed:", exc)
        if key == "topic-constraint":
            # 硬条件与候选的冲突：填「单卡消费级 + 3 个月」，看重实验的候选怎么被标出来
            try:
                import profile_memory as PM2
                PM2.set_constraints(compute="单卡消费级", months="3 个月内",
                                    style="偏工程", avoid=["云"])
                page.entry.delete(0, "end")
                page.entry.insert(0, "红外小目标检测")
                page.generate()
                deadline = _t.time() + 60
                while _t.time() < deadline:
                    root.update()
                    app.pump()
                    if getattr(page, "cands", None):
                        break
                    _t.sleep(0.05)
                idx = [i for i, c in enumerate(getattr(page, "cands", []) or [])
                       if (c.get("cfit") or {}).get("level") != "ok"]
                if idx:
                    page.select(idx[0])
            except Exception as exc:
                print("topic-constraint trigger failed:", exc)
        if key == "latest":
            # 真抓一批，好把「下载到知识库 / 下载前 N 篇」两个按钮截进画面；
            # 只抓取不下载，绝不往用户真实知识库里写文件
            try:
                page.entry.delete(0, "end")
                page.entry.insert(0, "事件相机语义分割")
                page.search()
                deadline = _t.time() + 60
                while _t.time() < deadline:
                    root.update()
                    app.pump()
                    if (getattr(page, "result", None) or {}).get("papers"):
                        break
                    _t.sleep(0.05)
            except Exception as exc:
                print("latest trigger failed:", exc)
        if key == "mentor":
            # 用「单目深度估计」—— 库里只有 3 位，最能把「兜底填满」暴露出来
            try:
                page.entry.delete(0, "end")
                page.entry.insert(0, os.environ.get("SHOT_MENTOR_Q", "单目深度估计"))
                page.search()
                deadline = _t.time() + 60
                while _t.time() < deadline:
                    root.update()
                    app.pump()
                    if getattr(page, "rows", None):
                        break
                    _t.sleep(0.05)
            except Exception as exc:
                print("mentor trigger failed:", exc)
        if key == "library":
            try:
                deadline = _t.time() + 30
                while _t.time() < deadline:
                    root.update()
                    app.pump()
                    if getattr(page, "rows", None):
                        break
                    _t.sleep(0.05)
            except Exception as exc:
                print("library trigger failed:", exc)
        if key in ("gap", "gap-constraint"):
            # 全库核实是异步的（首次读 53.8 万篇正文约 20-30 秒），
            # 不等它的话截出来只有本地结论，看不到核实那一行
            try:
                deadline = _t.time() + 150
                while _t.time() < deadline:
                    root.update()
                    app.pump()
                    d = getattr(page, "data", None) or {}
                    if d.get("global_check"):
                        break
                    _t.sleep(0.1)
                d = getattr(page, "data", None) or {}
                print("gap global_check rows:", len(d.get("global_check") or []),
                      "gaps:", len(d.get("gaps") or []),
                      "issue_gaps:", len(d.get("issue_gaps") or []))
            except Exception as exc:
                print("gap check wait failed:", exc)
        for _ in range(30):
            root.update()
            app.pump()
        path = os.path.join(HERE, "screenshots", "page-%s.png" % key)
        found = TS.find_window("页面截图", True)
        if found:
            TS.grab(found[0], found[2], path)
            out.append(path)
            print("saved:", path)
        page.destroy()
        root.update()
    root.destroy()
    return out


if __name__ == "__main__":
    args = sys.argv[1:] or ["gap"]
    main(args)