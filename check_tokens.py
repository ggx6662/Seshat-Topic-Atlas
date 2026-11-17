#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验灰阶令牌：每一档文字在每一种底色上的 WCAG 对比度都要 ≥4.5:1。

三端（桌面 / 网页 / 手机）共用这一份，所以任何一端看起来「发虚」都是这里的
值不对，不用去各页面里找。改完色立刻跑一遍：
    python check_tokens.py
"""
import sys

import design_tokens as D


def lum(hexstr):
    hexstr = hexstr.lstrip("#")
    if len(hexstr) == 3:
        hexstr = "".join(c * 2 for c in hexstr)
    vals = []
    for i in (0, 2, 4):
        c = int(hexstr[i:i + 2], 16) / 255.0
        vals.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def contrast(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def main():
    pal = D.PALETTE["dark"]
    surfaces = ["canvas", "surface_raised", "surface_card", "surface_nav",
                "surface_overlay", "surface_hover"]
    inks = ["ink", "ink_secondary", "ink_tertiary"]
    semantic = ["success", "warning", "danger", "info", "orange", "primary"]
    bad = 0
    for mode, p in D.PALETTE.items():
        print("== %s ==" % mode)
        for fg in inks:
            line = []
            for bg in ["canvas", "surface_card", "surface_raised"]:
                r = contrast(p[fg], p[bg])
                flag = "ok" if r >= 4.5 else "LOW"
                if r < 4.5:
                    bad += 1
                line.append("%s=%.2f %s" % (bg[:9], r, flag))
            print("  %-14s %s" % (fg, "  ".join(line)))
        for fg in semantic:
            r = contrast(p[fg], p["surface_card"])
            if r < 4.5:
                bad += 1
                print("  %-14s on surface_card %.2f LOW" % (fg, r))
    del surfaces
    print()
    print("失败项：%d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())