#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke-test the interactive direction expansion engine."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_widget():
    spec = importlib.util.spec_from_file_location(
        "kb_widget_expansion_test", HERE / "kb_widget.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 kb_widget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    kb = load_widget()
    examples = [
        "单目深度估计",
        "密码学与协议安全",
        "编译器优化与代码生成",
        "计算教育研究",
        "医学图像分析",
    ]
    failures = []
    counts = {}
    for direction in examples:
        for mode in kb.DIRECTION_MODES:
            rows = kb.expand_direction_candidates(direction, mode, 18)
            counts[mode] = counts.get(mode, 0) + len(rows)
            if not rows:
                failures.append([direction, mode, "empty"])
                continue
            titles = [row["title"] for row in rows]
            if len(titles) != len(set(titles)):
                failures.append([direction, mode, "duplicate titles"])
            for row in rows:
                for key in (
                    "title", "strategy", "reason", "relevance", "novelty",
                    "feasibility", "score", "category", "field", "questions",
                ):
                    if key not in row:
                        failures.append([direction, mode, "missing " + key])
                        break
                if not (0 <= row["relevance"] <= 100
                        and 0 <= row["novelty"] <= 100
                        and 0 <= row["feasibility"] <= 100
                        and 0 <= row["score"] <= 100):
                    failures.append([direction, mode, "score range"])
                    break
                if len(row.get("questions", [])) < 3:
                    failures.append([direction, mode, "questions"])
                    break
            prompt = kb.expanded_direction_prompt(
                direction, rows, rows[0])
            if "未经检索验证" not in prompt:
                failures.append([direction, mode, "prompt evidence guard"])

    result = {
        "passed": not failures,
        "examples": len(examples),
        "modes": list(kb.DIRECTION_MODES),
        "candidate_counts": counts,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
