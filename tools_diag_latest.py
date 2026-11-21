#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最新研究页的离线合成数据回归与状态截图。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tools_isolate  # noqa: E402

tools_isolate.ALLOW_REAL.discard("llm_bridge.CONFIG_FILE")
_ISO = tools_isolate.isolate()

import app_main  # noqa: E402
import tools_shot as SHOT  # noqa: E402

OUT = os.path.join(HERE, "screenshots", "new")
os.makedirs(OUT, exist_ok=True)
W, H = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1240, 800)
TAG = sys.argv[3] if len(sys.argv) > 3 else "l"


def pump(app, n=12, dt=0.1):
    for _ in range(n):
        app.update()
        time.sleep(dt)


def snap(app, name, title="塞莎特——题谱"):
    app.update()
    time.sleep(0.5)
    app.update()
    hit = SHOT.find_window(title, True)
    if not hit:
        print("  [shot] no window")
        return
    hwnd, _t, r, _a = hit
    SHOT.grab(hwnd, r, os.path.join(OUT, name + ".png"))
    print("  [shot]", name)


TITLES = [
    "Infrared Small Target Detection via Multi-scale Contrast Enhancement and Attention Guidance",
    "Mamba-based Feature Fusion for Multi-modal Infrared and Visible Image Registration",
    "Diffusion Priors for Low-light Image Enhancement in UAV Thermal Imaging",
    "A Survey of Event Camera based Semantic Segmentation for Autonomous Driving",
    "Cross-domain Generalization of Remote Sensing Detectors under Sensor Shift",
    "轻量化红外小目标检测网络：结构重参数化与蒸馏的联合设计",
    "Zero-shot Nighttime Pedestrian Detection with Vision-Language Alignment",
    "Revisiting Non-local Attention for Tiny Object Segmentation in Aerial Scenes",
    "Uncertainty-aware Fusion of SAR and Optical Imagery for Flood Mapping",
    "Self-supervised Pretraining for Thermal Infrared Tracking",
    "Efficient Token Pruning in Multimodal Large Language Models for Visual Question Answering",
    "Cooperative Perception with V2X Communication: A Benchmark and New Baselines",
    "Learning Deformable Templates for Few-shot Infrared Target Recognition",
    "Spectral-spatial Tensor Decomposition for Hyperspectral Anomaly Detection",
    "Domain-adaptive Distillation for Real-time Infrared Small Target Detection on Edge Devices",
    "Benchmarking Foundation Models on Infrared Small Target Datasets",
]
AUTHORS = [
    ["Wei Zhang", "Yan Li", "Hao Chen"],
    ["Ming Sun", "Qian Wang"],
    ["Rui Zhao"],
    ["Jia Liu", "Tao Wu", "Xin He", "Fang Zhou"],
    ["Chen Yu", "Bo Li"],
]
VENUES = ["IEEE TIP", "CVPR 2026", "IEEE TGRS", "", "Pattern Recognition",
          "AAAI 2026", "IEEE TCSVT"]
SOURCES = ["arxiv", "openalex", "europepmc"]


def mk_papers(n=16):
    papers = []
    for i in range(n):
        mon = 10 if i < 7 else 9
        day = 28 - i if i < 7 else 30 - (i - 7)
        pub = "2026-%02d-%02d" % (mon, max(1, day))
        src = SOURCES[i % 3]
        au = AUTHORS[i % len(AUTHORS)]
        p = {
            "title": TITLES[i % len(TITLES)],
            "authors": au,
            "published": pub,
            "source": src,
            "also_in": (["openalex"] if src == "arxiv" and i % 4 == 0
                        else (["arxiv"] if src != "arxiv" and i % 5 == 0 else [])),
            "venue": VENUES[i % len(VENUES)],
            "cited": (i * 3) if i % 3 == 0 else 0,
            "doi": ("10.1109/TIP.2026.%06d" % (100000 + i)) if i % 2 == 0 else "",
            "abstract": (
                "Infrared small target detection remains challenging because targets "
                "occupy only a few pixels and are easily confused with clutter. "
                "We propose a multi-scale contrast enhancement module combined with an "
                "attention-guided refinement branch, and evaluate on NUAA-SIRST and "
                "IRSTD-1k under cross-dataset protocols. " * (1 + i % 3)),
            "url": ("https://arxiv.org/abs/2601.%05d" % (10000 + i)),
        }
        if i % 6 == 5:
            p["url"] = "https://doi.org/" + p["doi"] if p["doi"] else ""
        papers.append(p)
    return papers


def result(papers):
    by = {"arxiv": 0, "openalex": 0, "europepmc": 0}
    for p in papers:
        by[p["source"]] = by.get(p["source"], 0) + 1
    return {"papers": papers, "by_source": by,
            "errors": [("europepmc", "HTTP 503 Service Unavailable (retry later)")]
            if papers else [("arxiv", "timed out"), ("openalex", "timed out")]}


def main():
    app = app_main.App()
    app.geometry("%dx%d+0+0" % (W, H))
    pump(app, 10)
    app.goto("latest")
    pg = app.page("latest")
    pump(app, 12)
    snap(app, TAG + "1-empty")
    print("[diag] pages", pg.box.winfo_geometry(),
          "detail", pg.detail_box.winfo_geometry())

    pg.entry.delete(0, "end")
    pg.entry.insert(0, "红外小目标检测")
    pg.entry.config(fg=__import__("app_theme").TXT)
    pg._active_quick = "红外小目标检测"
    pg._render_quick()
    app.update()
    papers = mk_papers()
    pg._done("红外小目标检测", result(papers), None)
    pump(app, 14)
    snap(app, TAG + "2-result")
    print("[diag] summary", pg.summary.cget("text"))
    print("[diag] rows", len(pg._frames), "sel", pg._sel,
          "scroll", pg.box.winfo_geometry(),
          "detail", pg.detail_box.winfo_geometry())
    f0 = pg._frames.get(0)
    if f0:
        print("[diag] row0", f0[0].winfo_geometry())

    pg.select(3)
    pump(app, 6)
    snap(app, TAG + "3-select-long")

    pg.select(5)
    pump(app, 6)
    snap(app, TAG + "4-select-nopdf")
    print("[diag] detail children", len(pg.detail_box.inner.winfo_children()))

    pg._toggle_adv()
    pump(app, 8)
    snap(app, TAG + "5-adv")
    pg._toggle_adv()
    pump(app, 4)

    pg._done("zzzz-no-such", result([]), None)
    pump(app, 8)
    snap(app, TAG + "6-none")
    print("[diag] empty summary", pg.summary.cget("text"))

    pg._clear_entry()
    pump(app, 4)
    assert pg.result is None
    assert pg.ai_btn.cget("state") == "disabled"
    assert pg.dl_all_btn.cget("state") == "disabled"
    assert pg.entry.cget("fg") == __import__("app_theme").TXT
    snap(app, TAG + "7-reset")

    pg._done("红外小目标检测", result(papers), None)
    pg.entry.delete(0, "end")
    pg.entry.insert(0, "尚未抓取的新方向")
    pg._save(papers[0])
    import kb_widget as kb
    assert kb.load_research_memory()["ideas"][-1]["direction"] == "红外小目标检测"
    pg.select(2)
    pg.detail_box.canvas.yview_moveto(1)
    pg.select(0)
    pump(app, 4)
    assert pg.detail_box.canvas.yview()[0] == 0
    before = pg.box.winfo_height()
    pg._explain_done("合成总结，仅用于布局测试。\n" * 100)
    pump(app, 6)
    assert pg.box.winfo_height() >= before - 70
    assert pg._child_win.winfo_ismapped()
    snap(app, TAG + "8-ai-long", "AI 总结")
    pg._child_win.destroy()
    pg._go_topic()
    pump(app, 4)
    assert app.page("topic").entry.get() == "红外小目标检测"
    app.goto("latest")
    pg._clear()
    pg._done("另一方向", None, RuntimeError("合成网络失败"))
    pump(app, 4)
    assert pg.result is None
    assert pg.dl_all_btn.cget("state") == "disabled"
    snap(app, TAG + "9-error")
    print("[diag] reset / scroll / AI / navigation / failure assertions passed")
    app.destroy()
    tools_isolate.cleanup(_ISO.get("__tmp__"))


if __name__ == "__main__":
    main()