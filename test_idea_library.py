#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke-test the local innovation readiness diagnosis."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main() -> int:
    spec = importlib.util.spec_from_file_location(
        "kb_widget_idea_test", HERE / "kb_widget.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 kb_widget.py")
    kb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kb)

    cases = [
        {
            "name": "vague",
            "idea": {
                "title": "让模型效果更好",
                "desc": "增加一个模块提升性能。",
                "type": "结构创新",
                "category": "计算机视觉",
                "field": "目标检测",
                "domain": "",
            },
            "min_gaps": 4,
        },
        {
            "name": "structured",
            "idea": {
                "title": "频域与状态空间双路径融合",
                "desc": "通过频域约束和状态空间信息流融合多模态特征；"
                        "相比强 baseline 使用固定数据划分、AP 主指标、"
                        "模块级消融和失败案例证明增益来源。",
                "type": "结构创新",
                "mechanism_type": "表示与建模",
                "evidence_type": "消融归因",
                "risk_type": "竞争风险",
                "category": "计算机视觉",
                "field": "单目与双目深度估计",
                "domain": "夜间自动驾驶",
            },
            "min_gaps": 0,
        },
        {
            "name": "paradigm",
            "idea": {
                "title": "面向开放失败模式的新 benchmark",
                "desc": "重新定义问题与新评测协议，加入盲评、一致性检查、"
                        "失败切片和可复现的数据划分。",
                "type": "范式创新",
                "category": "计算机视觉",
                "field": "红外与低光视觉",
                "domain": "全天候感知",
            },
            "min_gaps": 2,
        },
    ]
    failures = []
    results = []
    for case in cases:
        assessment = kb.evaluate_idea_local(case["idea"])
        prompt = kb.idea_prompt(case["idea"], "review")
        if len(assessment["gaps"]) < case["min_gaps"]:
            failures.append([case["name"], "too few gaps"])
        if len(assessment["next_actions"]) < 3:
            failures.append([case["name"], "too few actions"])
        if "证据约束" not in prompt or "不得编造引用" not in prompt:
            failures.append([case["name"], "missing evidence guard"])
        results.append({
            "case": case["name"],
            "total": assessment["total"],
            "stage": assessment["stage"],
            "recommended_type": assessment["recommended_type"],
            "gaps": len(assessment["gaps"]),
        })

    if results[0]["stage"] != "0 原始想法":
        failures.append(["vague", "stage should be 0"])
    if results[2]["recommended_type"] != "范式创新":
        failures.append(["paradigm", "type detection"])
    if results[1]["total"] < results[0]["total"]:
        failures.append(["structured", "score should exceed vague idea"])
    mechanisms = kb.IDEA_MECHANISMS
    evidence_types = kb.IDEA_EVIDENCE_TYPES
    risk_types = kb.IDEA_RISK_TYPES
    if len(mechanisms) < 10 or len(evidence_types) < 7 or len(risk_types) < 6:
        failures.append(["taxonomy", "secondary dimensions too small"])
    review_prompt = kb.idea_review_prompt(cases[1]["idea"], "最小实验设计")
    if "预算与停止条件" not in review_prompt or "不得" not in kb.idea_prompt(
            cases[1]["idea"], "review"):
        failures.append(["review_prompt", "missing experiment/evidence guard"])

    payload = {
        "passed": not failures,
        "cases": results,
        "secondary_dimensions": {
            "mechanisms": len(mechanisms),
            "evidence_types": len(evidence_types),
            "risk_types": len(risk_types),
        },
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
