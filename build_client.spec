# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：知识库助手 客户端打包。

用 onedir 而不是 onefile，理由是数据量：

    onefile   每次启动把 42MB 数据解压到临时目录 —— 实测冷启动 6~9 秒，
              而且每次退出都重来一遍。用户双击图标等十秒，体验很差。
    onedir    数据就摆在 _internal/ 里，启动即读，冷启动 ~2 秒。

数据文件分成两侧：

    datas        → _internal/（只读，由 app_paths.RES 读取）
    可写文件      → 不打包进 datas，由 app_paths.ensure_data() 首次启动时
                    从 _internal/ 拷到 exe 旁边（app_paths.DATA）

构建：python -m PyInstaller build_client.spec --noconfirm --clean
"""
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

# 注意：spec 文件由 PyInstaller 以 exec() 执行，**没有 __file__**。
# 必须用 PyInstaller 注入的 SPECPATH 全局变量（就是 spec 所在目录）。
HERE = SPECPATH

# ---- 只读资源：必须随包发出去 ------------------------------------------------
READONLY = [
    "directions_library.json",
    "direction_aliases.json",
    "research_taxonomy.json",
    "research_taxonomy_extended.json",
    "research_taxonomy_comprehensive.json",
    "research_relations.json",
    "venue_rules.json",
    "venue_links.json",
    "institutions_cn.json",
    "institution_localization.json",
    "advisor_directory.json",
    "advisor_directory_full.json",
    "advisor_directory_generated.json",
    "advisor_arxiv.json",
    "paper_meta.json",
    "pdf_text_index.json",
    "config.example.json",
    "widget_settings.json",
    "web_static",          # 网页版前端（目录）
    "logo_128.png",        # 侧栏品牌标记（显示前由 app_theme 预缩）
    "logo_48.png",
    "logo_32.png",
]

datas = []
missing = []
for name in READONLY:
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        missing.append(name)
        continue
    if os.path.isdir(p):
        datas.append((p, name))
    else:
        datas.append((p, "."))

if missing:
    print("[build_client] 缺文件，已跳过：%s" % ", ".join(missing))

# 素材库数据与竞赛站共用一份快照，单独放进 site_data/（app_paths.RES 读取）
for _name in ("materials.json",):
    _p = os.path.join(HERE, "competition", "site", "data", _name)
    if os.path.exists(_p):
        datas.append((_p, "site_data"))
    else:
        print("[build_client] 缺素材库数据：%s" % _name)

# 打包后首次启动要拷一份到 exe 旁边的「可写文件」
SEED = ["config.json", "widget_settings.json"]
for name in SEED:
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        datas.append((p, "seed"))

# ---- 隐藏导入：这些模块是用 importlib / 动态名导入的，静态分析抓不到 ----------
hiddenimports = [
    "kbscan", "kb_download", "paper_sources", "arxiv_latest", "semantic_search",
    "meta_index", "fulltext", "paper_meta", "build_paper_meta",
    "profile_memory", "llm_bridge", "topic_gen", "topic_neighbors",
    "research_gap", "research_diagnose", "research_skills", "name_match",
    "check_profile", "app_charts", "app_diagnose_view",
    "app_paths", "web_server", "app_widgets",
]
# 注意：venue_rules 是数据文件（venue_rules.json），不是模块，放这里会报
# "Hidden import 'venue_rules' not found"。它在 READONLY 里。
# pdf 解析库是运行时才 import 的（pdfplumber / fitz 二选一）
for mod in ("pdfplumber", "fitz", "pypdf"):
    try:
        __import__(mod)
        hiddenimports.append(mod)
    except Exception:
        pass

# ---- 排除：这些不是运行时依赖，打进去只会让包变大 ---------------------------
# 实测：不排除时产物 559MB，其中 torch_cpu.dll 一项就 241MB。
# 这些库全是「顺带」被拉进来的（某个 hook / 隐藏导入扫到了 site-packages），
# 这个应用一个都不用：
#   torch / onnxruntime  —— 语义检索用的是 sklearn 的 TF-IDF + SVD，不跑神经网络
#   PIL                  —— 界面全是 Tk Canvas 绘制，不加载图片
#   sympy / pandas 等    —— torch 和 sklearn 的可选依赖
EXCLUDE = [
    "torch", "torchvision", "torchaudio", "onnxruntime", "onnx",
    "PIL", "Pillow", "cv2", "sympy",
    "matplotlib", "scipy", "pandas", "IPython", "notebook", "jupyter",
    "pytest", "setuptools", "pip", "wheel", "PyInstaller",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "test", "unittest", "pydoc_data",
]

a = Analysis(
    ["app_main.py"],
    pathex=[HERE],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDE,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="知识库助手",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX 会让杀毒软件误报，收益也不大
    console=False,             # GUI 程序，不要黑窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(HERE, "kb_widget_v2.ico")
    if os.path.exists(os.path.join(HERE, "kb_widget_v2.ico")) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="知识库助手",
)