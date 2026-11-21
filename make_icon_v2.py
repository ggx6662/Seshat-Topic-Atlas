#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：应用图标统一由 `make_logo.py` 生成。

历史版本在这里单独画「550W」大字标，和侧栏、网页 PWA 各用一套样子。
现在三端共用同一枚六边形节点标记，保留这个文件名只是为了让旧文档和
快捷方式里的命令还能跑。
"""
from make_logo import main

if __name__ == "__main__":
    main()
