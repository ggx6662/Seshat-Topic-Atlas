#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 conda 环境备份，生成「删除与重建指南」。

回答一个问题：这些环境删了之后，重装靠谱吗？

判定维度
--------
1. 是否有 CUDA/torch（重装最易失败的依赖）
2. 是否有 pip 包（需要联网逐个下载）
3. 是否有特殊源（清华镜像、pytorch 源等）
4. 最后安装变更时间（闲置多久）
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

BACKUP = Path(r"F:\env-backup")
ENVS = Path(r"D:\Anaconda3\envs")


def parse_yml(p):
    """粗略解析 conda yml（不依赖 pyyaml）。"""
    text = p.read_text(encoding="utf-8", errors="ignore")
    info = {
        "name": p.stem,
        "channels": [],
        "conda_pkgs": [],
        "pip_pkgs": [],
        "has_cuda": False,
        "has_torch": False,
        "has_python": False,
        "special_channel": False,
    }
    in_pip = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- ") and not line.startswith("    "):
            if "pip:" in s:
                in_pip = True
                continue
            pkg = s[2:].strip()
            if pkg.startswith("http"):
                info["channels"].append(pkg)
                info["special_channel"] = True
                continue
            info["conda_pkgs"].append(pkg)
        elif line.startswith("    - "):
            info["pip_pkgs"].append(s[2:].strip())
    joined = " ".join(info["conda_pkgs"] + info["pip_pkgs"]).lower()
    info["has_cuda"] = ("cuda" in joined) or ("cudatoolkit" in joined) or ("nvidia" in joined)
    info["has_torch"] = "torch" in joined or "pytorch" in joined
    info["has_python"] = any(x.startswith("python=") for x in info["conda_pkgs"])
    info["special_channel"] = info["special_channel"] or any(
        "tuna" in c or "pytorch" in c or "nvidia" in c for c in info["channels"])
    return info


def size_of(env):
    p = ENVS / env
    if not p.exists():
        return 0.0
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / (1024 ** 3)


def last_change(env):
    h = ENVS / env / "conda-meta" / "history"
    try:
        return datetime.fromtimestamp(h.stat().st_mtime)
    except OSError:
        return None


def difficulty(info):
    """重建难度：低 / 中 / 高。"""
    score = 0
    if info["has_cuda"]:
        score += 2
    if info["has_torch"]:
        score += 1
    if len(info["pip_pkgs"]) > 50:
        score += 2
    elif len(info["pip_pkgs"]) > 20:
        score += 1
    if info["special_channel"]:
        score += 1
    if score >= 4:
        return "高"
    if score >= 2:
        return "中"
    return "低"


def main():
    rows = []
    for p in sorted(BACKUP.glob("*.yml")):
        info = parse_yml(p)
        env = p.stem
        gb = size_of(env)
        lc = last_change(env)
        days = (datetime.now() - lc).days if lc else -1
        rows.append({
            "环境": env,
            "GB": round(gb, 2),
            "最后变更": lc.strftime("%Y-%m-%d") if lc else "未知",
            "闲置天数": days,
            "conda包": len(info["conda_pkgs"]),
            "pip包": len(info["pip_pkgs"]),
            "CUDA": "是" if info["has_cuda"] else "",
            "重建难度": difficulty(info),
            "yml": str(p),
        })

    out = BACKUP / "环境清单.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    rows.sort(key=lambda r: (-r["闲置天数"], -r["GB"]))
    print("%-18s %6s %-11s %5s %6s %5s %5s %6s" % (
        "环境", "GB", "最后变更", "闲置", "conda", "pip", "CUDA", "重建"))
    print("-" * 74)
    for r in rows:
        print("%-18s %6.2f %-11s %4d天 %6d %5d %5s %6s" % (
            r["环境"], r["GB"], r["最后变更"], r["闲置天数"],
            r["conda包"], r["pip包"], r["CUDA"], r["重建难度"]))

    total = sum(r["GB"] for r in rows)
    old = [r for r in rows if r["闲置天数"] > 300]
    print("-" * 74)
    print("环境总数 %d | 总计 %.2f GB" % (len(rows), total))
    print("闲置超 300 天: %d 个，合计 %.2f GB" % (len(old), sum(r["GB"] for r in old)))
    print("清单已存: %s" % out)


if __name__ == "__main__":
    main()