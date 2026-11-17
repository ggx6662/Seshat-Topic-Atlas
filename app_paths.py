# -*- coding: utf-8 -*-
"""路径解析：一套代码，两种运行形态。

    开发态（python app_main.py）    打包态（知识库助手.exe / PyInstaller onedir）

    HERE  = 源码目录                RES  = sys._MEIPASS（只读资源，退出即删）
                                    DATA = exe 所在目录（可写，用户数据）

改造前所有模块都写 `HERE = Path(__file__).parent` 然后读数据、写数据。打包后
`__file__` 指向临时解压目录，这会导致两个致命问题：

1. **只读资源找不到** —— PyInstaller 把 .json 解压到 `sys._MEIPASS`，
   而 `__file__.parent` 指向的是 `_MEIPASS` 下的字节码目录，不是数据目录。
2. **用户数据被清空** —— `research_memory.json`、`researcher_profile.json`、
   `llm_config.json` 写进 `_MEIPASS`，程序一退出整个目录被删，用户存的选题
   和 API Key 全部消失。

所以这里把路径分成三类，不允许混用：

    RES   只读。数据文件，打包后在 _MEIPASS 里。
    DATA  可写。用户数据 + 缓存，打包后在 exe 旁边。用户换电脑只需拷 exe 目录。
    KB    外部。知识库 PDF 目录，永远是用户自己的路径，从 config.json 读。

**开发态下 RES == DATA == HERE**，行为和改造前完全一致，现有测试不受影响。
"""
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

# ---- 只读资源目录 -----------------------------------------------------------
if FROZEN:
    RES = Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
else:
    RES = Path(__file__).resolve().parent

# ---- 可写数据目录 -----------------------------------------------------------
if FROZEN:
    # exe 旁边放数据，卸载即删干净，也方便用户备份/迁移。
    # 不用 %APPDATA%：这个应用本来就是「绿色便携」定位，数据跟着程序走更直观。
    DATA = Path(sys.executable).resolve().parent
else:
    DATA = RES

# README 里所有路径都以 HERE 表述，保留这个别名让开发态脚本不用改。
HERE = DATA

# ---- 关键修复：只读资源在打包后可能和 DATA 不在同一层 ------------------------
# 用 PyInstaller onedir 时 _MEIPASS 是 _internal/，数据在那里；
# 用 onefile 时 _MEIPASS 是临时目录。两种情况 RES 都指向数据所在目录，
# 所以下面这个 helper 只是为了在 RES 里找不到时退回 DATA（用户手工放了新数据）。
def res(name):
    """取一个只读资源文件的路径。RES 里没有就退回 DATA（开发态二者相同）。"""
    p = RES / name
    if p.exists():
        return p
    return DATA / name


def data(name):
    """取一个可写文件/目录的路径。始终在 DATA 下，绝不落在 _MEIPASS。"""
    return DATA / name


def ensure_data():
    """打包态第一次启动时，把 RES 里缺少的可写文件拷一份到 DATA。

    只拷白名单里的文件，不碰索引缓存（.cache_advisors.json 会自动重建）。
    """
    if not FROZEN:
        return []
    made = []
    for name in ("config.json", "widget_settings.json", "research_memory.json",
                 "researcher_profile.json", "assistant_memory.json"):
        dst = DATA / name
        src = RES / name
        if not dst.exists() and src.exists():
            try:
                dst.write_bytes(src.read_bytes())
                made.append(name)
            except Exception:
                pass
    return made


def describe():
    return {"frozen": FROZEN, "res": str(RES), "data": str(DATA)}