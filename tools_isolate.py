#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把测试期间会写盘的「用户数据」全部重定向到临时目录。

## 为什么需要这个

2026-11-13 跑回归时发现真实目录里冒出一个 `researcher_profile.json`，里面
70 条记忆锚点、`preferences.fields = {"单目与双目深度估计": 12, "目标检测": 9.0}`。
不是测试脚本自己写的 —— 是 `MentorPage` 在 `search()` 里做了这件事：

```python
# page_mentor.py 第 313 行
import profile_memory as PM
PM.bump_pref("fields", field, delta=1, cap=12)
PM.remember("查了「%s」方向的导师（%d 位）" % (text, len(rows)), tags=["查导师"], ...)
```

这个行为本身是对的（「查过哪些方向就是你对什么感兴趣」），问题是
`tools_e2e_test.py` 建了真的 `MentorPage`、真的搜了一次导师，
而它只隔离了 `research_memory.json`，**没隔离画像**。

单独给每个测试脚本加 `PM.PROFILE_FILE = tmp/...` 治标不治本：
将来任何一个页面再加一处 `PM.remember()`，就又漏了。所以这里用一条
统一入口，在测任何界面之前先把所有「会被界面顺手写到」的文件指到临时目录。

## 用法

```python
import tools_isolate
_tmp = tools_isolate.isolate()      # 返回临时目录路径
...
tools_isolate.cleanup(_tmp)         # 结束时删掉
```

必须在 **import 任何页面模块之前** 调用 —— `profile_memory` 之类的模块
在 import 时就可能 `_ensure()` 建文件。
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 隔离用的临时目录（模块级）：即使某个模块在 isolate() 之后才被延迟 import，
# 也能靠这个目录把它接上。见 resolve() / attach()。
_TMP = None

# 被隔离的「用户数据」。键是模块名，值是模块里的路径常量名。
# 加新文件就在这里补一行，不用改每个测试脚本。
TARGETS = [
    ("kb_widget", "RESEARCH_MEMORY"),
    ("kb_widget", "SEEN_IDS"),
    ("kb_widget", "CONFIG_FILE"),
    ("profile_memory", "PROFILE_FILE"),
    ("profile_memory", "LOCK_FILE"),
    ("kb_download", "FAILURES_FILE"),
    ("kb_download", "SEEN_FILE"),
    ("llm_bridge", "CONFIG"),
    ("llm_bridge", "CONFIG_FILE"),
]

# 允许「留在真实位置」的项：测试与截图只读它、绝不写它。
# 典型用途：截图要展示真实配置（抓取窗口 7 天 / 8 条检索词），
# 隔离后 config.json 是个空文件，界面上全是「—」和「检索词组（0）」，
# 截出来的图与用户实际所见不符。加进这里的产品代码必须保证只读。
ALLOW_REAL = {
    "kb_widget.CONFIG_FILE",
    # 密钥打码这类行为只有在配置里有真密钥时才测得到：隔离后是空配置，
    # status()["key"] 恒为空串，断言「不含明文」永远成立但什么都没验证。
    # 本项只读（LLM 设置页在测试里不会真的点保存）。
    "llm_bridge.CONFIG_FILE",
}

# 由 isolate() 安装的 import 钩子记录：模块名 → [(attr, 临时路径)]
_PENDING = {}


def _install_hook():
    """装一个 import 钩子：模块被 import 时自动把 TARGETS 里的路径换掉。

    为什么需要：`page_latest._download()` 里是
    `import profile_memory as PM`（函数内延迟 import）。如果测试脚本只调一次
    `isolate()`，那时 `profile_memory` 还没进 sys.modules，TARGETS 就扫不到它，
    等界面真跑起来才 import，路径早已定型 —— 于是一条记忆被写进真实目录。
    2026-11-13 实测就是这样漏的。
    """
    if getattr(_install_hook, "_done", False):
        return
    _install_hook._done = True

    class _Finder:
        # meta_path 里的钩子：包一层 finder，模块加载后回调
        def __init__(self, inner):
            self._inner = inner

        def find_spec(self, name, path=None, target=None):
            spec = self._inner.find_spec(name, path, target)
            if spec and name in _PENDING and spec.loader is not None:
                loader = spec.loader
                orig_exec = getattr(loader, "exec_module", None)
                if orig_exec is not None:
                    def exec_module(module, _orig=orig_exec, _name=name):
                        _orig(module)
                        for attr, tmp_path in _PENDING.get(_name, []):
                            if "%s.%s" % (_name, attr) in ALLOW_REAL:
                                continue
                            if hasattr(module, attr):
                                try:
                                    setattr(module, attr, tmp_path)
                                except Exception:
                                    pass
                    loader.exec_module = exec_module
            return spec

    finder = _Finder(None)
    # 用 path_hook 不方便，这里直接包一层 sys.meta_path 尾部的 PathFinder
    for i, f in enumerate(sys.meta_path):
        if getattr(f, "__name__", "") in ("PathFinder", "FileFinder"):
            sys.meta_path[i] = _Finder(f)
            break


def isolate(prefix="kbtest_"):
    """把用户数据重定向到临时目录。返回字典：文件名 → 临时路径。

    返回的字典里 `__orig__` 键保存「隔离之前的原始路径」，
    方便调用方把真实文件复制到临时位置（否则会 FileNotFoundError：
    隔离后的路径是一个还不存在的临时文件）。
    """
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    global _TMP
    _TMP = tmp
    moved = {"__tmp__": tmp, "__orig__": {}}
    for mod_name, attr in TARGETS:
        if "%s.%s" % (mod_name, attr) in ALLOW_REAL:
            continue
        target = tmp / ("%s_%s" % (mod_name, attr.lower()))
        moved["%s.%s" % (mod_name, attr)] = target
        mod = sys.modules.get(mod_name)
        if mod is None:
            # 还没 import —— 预约，等它被 import 时由钩子替换
            _PENDING.setdefault(mod_name, []).append((attr, target))
            continue
        if not hasattr(mod, attr):
            continue
        try:
            moved["__orig__"]["%s.%s" % (mod_name, attr)] = Path(getattr(mod, attr))
        except Exception:
            pass
        try:
            setattr(mod, attr, target)
        except Exception:
            pass
    if _PENDING:
        _install_hook()
    # 无论有没有 _PENDING，都装上兜底守卫 —— 上面三种情况钩子都拦不住。
    _watch_after_import(None)
    return moved


def find_tmp():
    """返回当前隔离用的临时目录（找不到就现造一个）。"""
    for mod_name, attr in TARGETS:
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, attr):
            p = Path(getattr(mod, attr))
            if "kbtest_" in str(p) or "kbtest_" in str(p.parent):
                return p.parent if "/" in str(p) or "\\" in str(p) else p
    return None


def check_clean(preexisting=()):
    """返回「真实目录里出现了不该有的用户数据」清单。

    界面上任何一处 `PM.remember()` 都会写盘，测试跑完这个函数应该返回空列表。

    `preexisting`：**测试开始前就已经存在**的文件路径集合。它们不算泄漏 ——
    用户自己用软件时本来就会生成 researcher_profile.json，测试不该因为
    「这个文件本来就在」而判自己污染了数据（2026-11-15 就是这样误报的：
    真实文件其实是前后两次测试的迟到写入，第一次测试报错时把它删了，
    第二次跑的时候它又出现了）。
    """
    bad = []
    pre = set(str(x) for x in (preexisting or ()))
    # llm_config.json 不在此列：它现在装的是用户真实填的 API 密钥，
    # 属于产品的正常状态（ALLOW_REAL 只读它、绝不写）。要校验它没被测试改动，
    # 应该比对 mtime/内容，而不是「是否存在」。
    for name in ("researcher_profile.json", "download_failures.json"):
        p = HERE / name
        if p.exists() and str(p) not in pre:
            bad.append(str(p))
    return bad


def snapshot_memory():
    """记下 research_memory.json 的 (大小, mtime)，用于比对有没有被改。"""
    p = HERE / "research_memory.json"
    if not p.exists():
        return None
    st = p.stat()
    return (st.st_size, st.st_mtime)


def assert_memory_untouched(before, label="research_memory.json"):
    after = snapshot_memory()
    if before is not None and after != before:
        raise AssertionError("%s 被测试改动了：%r → %r" % (label, before, after))


def _watch_after_import(name):
    """兜底守卫：模块被 import 语句取用时，把路径从「真实位置」拨回临时目录。

    import 钩子只在模块**首次走 finder 加载**时生效。以下三种情况它拦不住：
      · 模块在 isolate() 之前就进了 sys.modules，之后又被重新 import（命中缓存）
      · 同一个进程里连续跑多个测试，`_install_hook` 的 _done 标记让钩子只装一次
      · 某个模块用了 importlib.reload 或动态 exec

    **只纠正指向真实目录的路径**。测试自己把 FAILURES_FILE 指到 TMP/x.json
    这种临时位置时必须放行 —— 否则守卫会把测试的定向设置改回隔离目录，
    这正是第一版守卫把「失败清单能写能读」测坏的原因（2026-11-13 实测）。
    """
    if getattr(_watch_after_import, "_done", False):
        return
    _watch_after_import._done = True

    import builtins
    _real_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        mod = _real_import(name, globals, locals, fromlist, level)
        if _TMP is None:
            return mod
        for mod_name, attr in TARGETS:
            if "%s.%s" % (mod_name, attr) in ALLOW_REAL:
                continue
            m = sys.modules.get(mod_name)
            if m is None or not hasattr(m, attr):
                continue
            try:
                cur = Path(getattr(m, attr)).resolve()
            except Exception:
                continue
            # 只处理「指向真实用户数据」的情况
            if cur.parent != HERE.resolve():
                continue
            try:
                setattr(m, attr, Path(_TMP) / ("%s_%s" % (mod_name, attr.lower())))
            except Exception:
                pass
        return mod

    builtins.__import__ = _guarded_import


def cleanup(tmp):
    if tmp is None:
        return
    try:
        shutil.rmtree(str(tmp), ignore_errors=True)
    except Exception:
        pass