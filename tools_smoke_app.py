#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试：逐页打开、跑核心流程、截图。用于交付前的自检。

用法:  python tools_smoke_app.py [输出目录]
不依赖 pyautogui：直接驱动 App 对象 + 延迟截图。
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app_main  # noqa: E402
import app_theme as T  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "screenshots")
os.makedirs(OUT, exist_ok=True)

result = {"ok": [], "fail": []}

import ctypes  # noqa: E402
import ctypes.wintypes as wt  # noqa: E402
import tools_shot as SHOT  # noqa: E402

WIN_W, WIN_H = 1240, 800

# 冒烟测试会真的写入「创新点库」，所以先重定向到临时文件，跑完再还原，
# 绝不污染用户的 research_memory.json。
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

import kb_widget as _kb  # noqa: E402

_real_memory = _kb.RESEARCH_MEMORY
_tmp_memory = os.path.join(tempfile.gettempdir(), "kb_smoke_research_memory.json")
shutil.copy(_real_memory, _tmp_memory)
_kb.RESEARCH_MEMORY = __import__("pathlib").Path(_tmp_memory)

# 画像也要隔离。MentorPage.search() 会 PM.bump_pref() + PM.remember()，
# 只隔内存文件的话，冒烟一跑真实目录就会多个 researcher_profile.json。
import tools_isolate  # noqa: E402

_ISO = tools_isolate.isolate()
_mem_before = tools_isolate.snapshot_memory()


def snap(app, name):
    app.update()
    time.sleep(0.5)
    app.update()
    hit = SHOT.find_window("知识库助手", True)
    path = os.path.join(OUT, name + ".png")
    if not hit:
        print("  [shot] 未找到窗口")
        return
    hwnd, _t, r, _a = hit
    SHOT.grab(hwnd, r, path)
    print("  [shot]", path, "%dx%d" % (r.right - r.left, r.bottom - r.top))


def step(name, fn):
    try:
        fn()
        result["ok"].append(name)
        print("  [ok]", name)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result["fail"].append((name, str(exc)))
        print("  [FAIL]", name, exc)


def main():
    app = app_main.App()
    app.geometry("%dx%d+0+0" % (WIN_W, WIN_H))
    app.update_idletasks()
    app.update()
    time.sleep(1.2)

    # 1 总览
    step("总览", lambda: (app.goto("home"), app.update(), snap(app, "01-home")))

    # 2 选题工坊：输入 → 生成候选 → 选中 → 截图
    def topic():
        app.goto("topic")
        pg = app.page("topic")
        pg.entry.delete(0, "end")
        pg.entry.insert(0, "红外小目标检测")
        pg.generate()
        for _ in range(60):
            app.update()
            time.sleep(0.1)
            if pg.cands:
                break
        assert pg.cands, "没有生成候选"
        pg.select(0)
        snap(app, "02-topic")
        result["cands"] = len(pg.cands)
    step("选题工坊", topic)

    # 3 存为创新点
    def save_idea():
        pg = app.page("topic")
        pg.save_idea()
        app.update()
    step("存为创新点", save_idea)

    # 4 创新点库
    def ideas():
        app.goto("ideas")
        pg = app.page("ideas")
        pg.reload()
        app.update()
        if pg.ideas:
            pg.select(0)
        snap(app, "03-ideas")
        result["ideas"] = len(pg.ideas)
    step("创新点库", ideas)

    # 5 方向图谱
    def dsmap():
        app.goto("map")
        pg = app.page("map")
        for _ in range(40):
            app.update()
            time.sleep(0.1)
            if pg.lib:
                break
        assert pg.lib, "方向库未加载"
        first = list(pg.lib)[1] if len(pg.lib) > 1 else list(pg.lib)[0]
        pg.pick_cat(first)
        subs = pg.lib[first].get("subs", [])
        assert subs, "大类没有子领域"
        pg.pick_field(subs[0]["name"])
        app.update()
        snap(app, "04-map")
        result["cats"] = len(pg.lib)
    step("方向图谱", dsmap)

    # 6 导师与院校
    def mentor():
        app.goto("mentor")
        pg = app.page("mentor")
        pg.search("单目深度估计")
        for _ in range(80):
            app.update()
            time.sleep(0.1)
            if pg.rows:
                break
        snap(app, "05-mentor")
        result["mentors"] = len(pg.rows)
        assert pg.rows, "导师匹配为空"
    step("导师与院校", mentor)

    # 7 期刊会议
    def venue():
        app.goto("venue")
        pg = app.page("venue")
        pg.search("三维重建")
        for _ in range(80):
            app.update()
            time.sleep(0.1)
            if pg.rows:
                break
        snap(app, "06-venue")
        result["venues"] = len(pg.rows)
        assert pg.rows, "venue 匹配为空"
    step("期刊会议", venue)

    # 8 文献库
    def library():
        app.goto("library")
        pg = app.page("library")
        for _ in range(100):
            app.update()
            time.sleep(0.1)
            if pg.rows:
                break
        assert pg.rows, "文献库为空"
        pg.filter_cat = pg.cats[0]["name"] if pg.cats else "全部"
        pg._render_cats()
        pg.apply_filter()
        snap(app, "07-library")
        result["pdfs"] = len(pg.rows)
    step("文献库", library)

    # 9 科研方法论
    def skills():
        app.goto("skills")
        pg = app.page("skills")
        pg.select(2)
        app.update()
        snap(app, "09-skills")
        # 提示词生成要能跑通
        pg.idea = {"title": "测试课题", "desc": "夜间巡查场景下小目标漏检率偏高，现有检测器在低对比度条件下退化。"}
        pg.prompt_plan()
        app.update()
        assert pg.idea, "课题未设置"
    step("科研方法论", skills)

    # 10 设置
    def settings():
        app.goto("settings")
        snap(app, "08-settings")
    step("设置与数据", settings)

    # 10 搜索
    def search():
        app.search.delete(0, "end")
        app.search.insert(0, "mamba")
        app.global_search()
        app.update()
    step("全局搜索", search)

    app.update()
    app.destroy()
    _kb.RESEARCH_MEMORY = _real_memory
    try:
        os.remove(_tmp_memory)
    except Exception:
        pass

    # 真实目录里不该冒出用户数据文件（跑了 12 个页面，其中导师页会写画像）
    leaked = tools_isolate.check_clean()
    for p in leaked:
        try:
            os.remove(p)
        except Exception:
            pass
    if leaked:
        result["fail"].append(("测试污染真实数据", ", ".join(leaked)))
    try:
        tools_isolate.assert_memory_untouched(_mem_before)
    except AssertionError as exc:
        result["fail"].append(("research_memory 被改动", str(exc)))
    tools_isolate.cleanup(_ISO.get("__tmp__"))

    print("\n==== 冒烟结果 ====")
    print("通过:", len(result["ok"]), "  失败:", len(result["fail"]))
    for n, e in result["fail"]:
        print("  FAIL", n, e)
    for k in ("cands", "ideas", "cats", "mentors", "venues", "pdfs"):
        if k in result:
            print("  %-8s %s" % (k, result[k]))
    return 1 if result["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())