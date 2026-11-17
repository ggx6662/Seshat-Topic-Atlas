#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""选题结构诊断的统一渲染组件（三处共用：选题工坊 / 创新点库 / 总览）。

设计原则：
  * 不显示「XX 分」。分数会让人误以为得到了客观评估，而这里做的只是
    「这句话里有没有交代 baseline」这类结构核查。
  * 显示「已具备 / 缺失」清单，每条缺失都带一个可执行的修复建议。
  * 阶段是一个档位，不是分数；旁边始终写清它代表什么。
"""
import tkinter as tk

import app_theme as T
import research_diagnose as RD

STAGE_COLOR = {
    0: T.ERR,
    1: T.WARN,
    2: T.EXTRA if hasattr(T, "EXTRA") else T.ACCENT,
    3: T.OK,
    4: T.PURPLE,
}


def stage_color(stage):
    return STAGE_COLOR.get(RD.stage_rank(stage), T.TXT3)


def stage_badge(parent, stage, big=False):
    """阶段徽章：数字档位 + 文字说明，不显示分数。"""
    rank = RD.stage_rank(stage)
    col = stage_color(stage)
    box = tk.Frame(parent, bg=parent.cget("bg"))
    tk.Label(box, text=" %d " % rank, bg=col, fg="#061220",
             font=T.M(12 if big else 9, True)).pack(side="left")
    label = str(stage)[2:].strip() if len(str(stage)) > 2 and str(stage)[1] == " " else str(stage)
    tk.Label(box, text="  " + label, bg=parent.cget("bg"), fg=col,
             font=T.F(11 if big else 9, True)).pack(side="left")
    return box


def coverage_bar(parent, passed, total):
    """结构完成度：这是「填了几项」，不是「好不好」。

    进度条占用可伸缩空间，右侧数字固定宽度，避免字号放大后挤出版面。
    """
    row = tk.Frame(parent, bg=parent.cget("bg"))
    tk.Label(row, text="结构完整度", bg=row.cget("bg"), fg=T.TXT3,
             font=T.F(8)).pack(side="left")
    pct = (passed / float(total)) if total else 0
    col = T.OK if pct >= 0.78 else (T.WARN if pct >= 0.45 else T.ERR)
    # 数字先 pack 到右侧，保证不被进度条挤走
    tk.Label(row, text="%d/%d 项" % (passed, total), bg=row.cget("bg"), fg=col,
             font=T.M(8), width=6, anchor="e").pack(side="right")
    track = tk.Frame(row, bg=T.LINE_SOFT, height=8)
    track.pack(side="left", fill="x", expand=True, padx=(T.gap(6), T.gap(6)))
    track.pack_propagate(False)
    tk.Frame(track, bg=col).place(x=0, y=0, relwidth=pct, relheight=1)
    return row


def render(parent, idea, compact=False, wrap=480):
    """把诊断结果画进 parent。返回诊断字典，方便调用方复用。"""
    res = RD.diagnose(idea)
    bg = parent.cget("bg")

    head = tk.Frame(parent, bg=bg)
    head.pack(fill="x", pady=(0, 4))
    stage_badge(head, res["stage"]).pack(side="left")
    tk.Label(head, text="  " + res["stage_hint"], bg=bg, fg=T.TXT3,
             font=T.F(8)).pack(side="left")

    coverage_bar(parent, res["count"]["passed"], res["count"]["total"]).pack(fill="x",
                                                                            pady=(2, 6))

    for w in res["warnings"]:
        box = tk.Frame(parent, bg="#3A2A10")
        box.pack(fill="x", pady=(0, 4))
        tk.Label(box, text="⚠", bg="#3A2A10", fg=T.WARN, font=T.F(9)).pack(
            side="left", padx=(8, 4), anchor="n", pady=5)
        tk.Label(box, text=w, bg="#3A2A10", fg=T.WARN, font=T.F(8), anchor="w",
                 justify="left", wraplength=wrap - 40).pack(side="left", fill="x",
                                                            expand=True, pady=5,
                                                            padx=(0, 8))

    if res["passed"]:
        tk.Label(parent, text="已具备（可被第三方核查）", bg=bg, fg=T.OK,
                 font=T.F(9, True), anchor="w").pack(fill="x", pady=(2, 2))
        for p in res["passed"]:
            _row(parent, "✓", p["label"], p["why"], T.OK, wrap)

    if res["missing"]:
        tk.Label(parent, text="尚未交代", bg=bg, fg=T.WARN,
                 font=T.F(9, True), anchor="w").pack(fill="x", pady=(8, 2))
        limit = 4 if compact else len(res["missing"])
        for m in res["missing"][:limit]:
            _row(parent, "✗", m["label"], "→ " + m["fix"], T.TXT2, wrap)
        if len(res["missing"]) > limit:
            tk.Label(parent, text="  还有 %d 项…" % (len(res["missing"]) - limit),
                     bg=bg, fg=T.TXT4, font=T.F(8), anchor="w").pack(fill="x")

    if not compact and res["next"]:
        tk.Label(parent, text="下一步", bg=bg, fg=T.ACCENT, font=T.F(9, True),
                 anchor="w").pack(fill="x", pady=(10, 2))
        for n in res["next"]:
            _row(parent, "·", "", n, T.TXT2, wrap, show_label=False)

    return res


def _row(parent, mark, label, detail, color, wrap, show_label=True):
    bg = parent.cget("bg")
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=1)
    tk.Label(row, text=mark, bg=bg, fg=color, font=T.F(9)).pack(side="left",
                                                              padx=(2, 5), anchor="n")
    text = (label + "  " if show_label and label else "") + (detail or "")
    tk.Label(row, text=text, bg=bg, fg=color if show_label else T.TXT2, font=T.F(9),
             anchor="w", justify="left",
             wraplength=max(160, wrap - 30)).pack(side="left", fill="x", expand=True)


def summary_line(idea):
    """一行摘要，用于列表：档位 + 缺失项数。"""
    res = RD.diagnose(idea)
    return {
        "stage": res["stage"],
        "rank": RD.stage_rank(res["stage"]),
        "passed": res["count"]["passed"],
        "total": res["count"]["total"],
        "missing_n": len(res["missing"]),
        "res": res,
    }