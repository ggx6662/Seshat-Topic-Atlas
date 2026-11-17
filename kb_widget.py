#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库助手·桌面小部件：常驻桌面的原生挂件（Tkinter，零依赖）。

形态与网页版不同：
  无边框玻璃卡片，默认贴在桌面（像壁纸上的挂件），
  不会被任务栏占位；右键菜单可切换“始终置顶”，可拖动位置。

用法:
  pythonw kb_widget.py        # 日常启动（桌面快捷方式走这里）
  python  kb_widget.py        # 调试模式（有控制台输出）
"""
import datetime
import ctypes
import concurrent.futures
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import simpledialog
from pathlib import Path
from urllib.parse import quote_plus

HERE = Path(__file__).resolve().parent
try:
    import app_paths as _AP
    _RES = _AP.res        # 只读资源：打包后在 _MEIPASS
    _DATA = _AP.data      # 可写数据：打包后在 exe 旁边
except Exception:         # 单独跑构建脚本/测试时退回旧行为
    _RES = lambda n: HERE / n
    _DATA = lambda n: HERE / n
CONFIG_FILE = _DATA("config.json")
KBSCAN = _RES("kbscan.py")
DASHBOARD = _RES("dashboard.py")
TASK_NAME = "KB-Monitor-Update"
LOCK_PORT = 8766
ICON = _RES("kb_widget_v2.ico")
ICON_PNG = _RES("kb_widget_v2.png")
EXPORT_DIR = _DATA("exports")
MEMORY_FILE = _DATA("assistant_memory.json")
RESEARCH_MEMORY = _DATA("research_memory.json")
DIRECTION_LIBRARY = _RES("directions_library.json")
RESEARCH_TAXONOMY = _RES("research_taxonomy.json")
RESEARCH_RELATIONS = _RES("research_relations.json")
RESEARCH_EXTENDED = _RES("research_taxonomy_extended.json")
RESEARCH_COMPREHENSIVE = _RES("research_taxonomy_comprehensive.json")
ADVISOR_DIRECTORY = _RES("advisor_directory.json")
GENERATED_ADVISORS = _RES("advisor_directory_generated.json")
INSTITUTIONS_CN = _RES("institutions_cn.json")
INSTITUTION_LOCALIZATION = _RES("institution_localization.json")
VENUE_RULES = _RES("venue_rules.json")
VENUE_LINKS = _RES("venue_links.json")
DIRECTION_ALIASES = _RES("direction_aliases.json")
PROMPT_DIR = EXPORT_DIR / "prompts"
_ADVISOR_CACHE = {"signature": None, "rows": None}
_ADVISOR_CACHE_LOCK = threading.Lock()
_LOCALIZATION_CACHE = {"signature": None, "data": None}
_LOCALIZATION_CACHE_LOCK = threading.Lock()
RESEARCH_SUGGESTIONS = {
    "rgb-t": [
        "事件相机与 RGB-T 融合", "深度/几何先验融合", "语言引导多模态检测",
        "开放词汇 RGB-T 检测", "低光与夜间鲁棒性", "跨域泛化",
        "频域融合与轻量化", "Mamba/状态空间融合",
    ],
    "mamba": [
        "视觉 Mamba 与跨模态状态空间", "长序列融合效率", "Mamba 蒸馏与剪枝",
        "频域-Mamba 混合架构", "Mamba 的可解释性与理论分析",
    ],
    "红外": [
        "低光/夜间检测", "红外小目标与远距离检测", "红外-可见光配准",
        "对抗鲁棒性", "无人机与遥感应用",
    ],
    "医学": [
        "多模态医学影像分割", "小样本与自监督", "医学可解释性", "跨中心域泛化",
    ],
    "跟踪": [
        "RGB-T 跟踪", "长时跟踪", "语言引导跟踪", "事件相机跟踪",
    ],
}
GENERIC_DIRECTIONS = [
    "跨模态对齐", "开放词汇检测", "域泛化", "轻量化与实时部署",
    "自监督/少样本", "可解释性", "新型传感器融合", "Benchmark 与评测体系",
]
DIRECTION_TERMS = {
    "红外": "infrared",
    "可见光": "visible",
    "热成像": "thermal",
    "目标检测": "object detection",
    "检测": "detection",
    "多模态": "multimodal",
    "跨模态": "cross-modal",
    "融合": "fusion",
    "跟踪": "tracking",
    "分割": "segmentation",
    "医学": "medical",
    "医疗": "medical",
    "遥感": "remote sensing",
    "无人机": "UAV",
    "扩散": "diffusion",
    "频域": "frequency domain",
    "频率": "frequency",
    "小目标": "small object",
    "单目": "monocular",
    "双目": "stereo",
    "深度估计": "depth estimation",
    "三维重建": "3D reconstruction",
    "神经渲染": "neural rendering",
    "新视角合成": "novel view synthesis",
    "点云": "point cloud",
    "位姿估计": "pose estimation",
    "场景理解": "scene understanding",
    "立体视觉": "stereo vision",
    "视觉里程计": "visual odometry",
    "SLAM": "SLAM",
    "图像": "image",
    "视频": "video",
    "生成": "generation",
    "状态空间": "state space",
    "mamba": "mamba",
    "rgb-t": "RGB-T",
    "rgb-ir": "RGB-IR",
    "孪生": "siamese",
}
CATEGORY_HINTS = [
    ("track", "Track"), ("跟踪", "Track"),
    ("mamba", "Mamba多模态"), ("多模态", "Mamba多模态"),
    ("rgb-t", "Mamba多模态"), ("rgb-ir", "Mamba多模态"), ("融合", "Mamba多模态"),
    ("医学", "医学"), ("医疗", "医学"), ("medical", "医学"),
    ("扩散", "扩散模型"), ("diffusion", "扩散模型"),
    ("aaai", "AAAI"), ("cvpr", "CVPR"), ("iccv", "ICCV"), ("iclr", "ICLR"),
]
ERR = "#ff6f91"
WARN = "#ffd166"
ARXIV_ABS_URL = "https://arxiv.org/abs/"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_BAT = STARTUP_DIR / "知识库助手-开机启动.bat"

ACCENT = "#6be7ff"
BG = "#031826"
CARD = "#08344a"
LINE = "#1b6b8a"
TXT = "#e6faff"
MUT = "#a3c9d8"
OKC = "#43ffc9"
MONO = ("Consolas", 9)
FONT = ("Microsoft YaHei UI", 10)
FONT_S = ("Microsoft YaHei UI", 10)
FONT_XS = ("Microsoft YaHei UI", 9)
_CACHE = {}


def _cached(key, ttl, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def _hidden_kwargs():
    if os.name != "nt":
        return {}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
    except Exception:
        return {"creationflags": 0x08000000}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            "startupinfo": si}


def _pythonw_exe():
    r = Path(sys.executable)
    if r.name.lower() == "python.exe":
        alt = r.with_name("pythonw.exe")
        if alt.exists():
            r = alt
    return str(r)


def _decode_bytes(raw):
    if not raw:
        return ""
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _enable_dpi():
    if os.name != "nt":
        return
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _scan_inventory():
    kb = kb_root()
    inv = {"pdf_total": 0, "txt_total": 0, "cat_counts": {},
           "files": [], "pdfs": [], "pdf_index": {}}
    if not kb.exists():
        return inv
    for root, _dirs, names in os.walk(kb):
        rootp = Path(root)
        for name in names:
            p = rootp / name
            try:
                st = p.stat()
            except Exception:
                continue
            low = name.lower()
            try:
                rel = p.relative_to(kb).parts
            except Exception:
                rel = (name,)
            cat = rel[0] if len(rel) > 1 else "根目录"
            if low.endswith(".pdf"):
                inv["pdf_total"] += 1
                inv["cat_counts"][cat] = inv["cat_counts"].get(cat, 0) + 1
                inv["pdfs"].append((st.st_mtime, st.st_size, p))
                m = re.search(r"(\d{4})_(\d{4,6})(v\d+)?", p.stem)
                if m:
                    base = m.group(1) + "_" + m.group(2)
                    inv["pdf_index"].setdefault(base, p)
                    if m.group(3):
                        inv["pdf_index"].setdefault(base + m.group(3), p)
            elif low.endswith(".txt"):
                inv["txt_total"] += 1
            if low.endswith((".pdf", ".md", ".txt")):
                inv["files"].append((st.st_mtime, st.st_size, p))
    inv["files"].sort(key=lambda x: x[0], reverse=True)
    inv["pdfs"].sort(key=lambda x: x[0], reverse=True)
    return inv


def _inventory():
    return _cached("inventory", 300, _scan_inventory)


def load_config():
    try:
        return json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def kb_root():
    cfg = load_config()
    return Path(cfg.get("kb_path", r"G:\相关内容\AuthorKit27\知识库"))


def inbox_dir():
    return kb_root() / load_config().get("inbox_dir", "新论文")


def task_status():
    return _cached("task_status", 300, _task_status_raw)


def _task_status_raw():
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/FO", "LIST", "/V", "/TN", TASK_NAME],
            capture_output=True, timeout=20, **_hidden_kwargs(),
        )
        raw = proc.stdout
    except Exception:
        return {"name": TASK_NAME, "status": "查询失败", "next_run": "未知"}
    text = ""
    for enc in ("utf-16", "utf-8", "gbk"):
        try:
            candidate = raw.decode(enc)
            if "Status" in candidate or "状态" in candidate or "TaskName" in candidate:
                text = candidate
                break
        except Exception:
            continue
    if not text:
        text = raw.decode("utf-8", "replace")
    text = text.replace("\x00", "").replace("：", ":")
    info = {"name": TASK_NAME, "status": "未注册", "next_run": "未设置"}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key in ("Status", "状态", "计划任务状态"):
            info["status"] = val
        elif key in ("Next Run Time", "下次运行时间"):
            info["next_run"] = val
    return info


def kb_stats():
    return _cached("kb_stats", 300, _kb_stats_raw)


def _kb_stats_raw():
    inv = _inventory()
    return {"total_pdf": inv["pdf_total"], "total_txt": inv["txt_total"]}


def seen_count():
    f = _DATA("seen_ids.json")
    if not f.exists():
        return 0
    try:
        return len(json.loads(f.read_text(encoding="utf-8")))
    except Exception:
        return 0


def latest_digest_data():
    d = inbox_dir()
    if not d.exists():
        return None
    files = sorted(d.glob("新论文速览-*.md"),
                   key=lambda x: x.stat().st_mtime, reverse=True)
    if not files:
        return None
    newest_scan = None
    for index, path in enumerate(files):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        entries, cur = [], None
        for ln in text.splitlines():
            s = ln.strip()
            if s.startswith("## "):
                if cur:
                    entries.append(cur)
                cur = {"title": s[3:], "arxiv": "", "lines": []}
            elif cur:
                if s.lower().startswith("- arxiv:"):
                    m = re.search(r"(?:abs/|pdf/)([\d.]+)", s)
                    if m:
                        cur["arxiv"] = m.group(1)
                cur["lines"].append(s)
        if cur:
            entries.append(cur)
        if index == 0:
            newest_scan = {"file": path.name, "entries": len(entries)}
        if entries:
            return {
                "file": path.name,
                "path": str(path),
                "entries": entries,
                "latest_scan": newest_scan,
            }
    return {
        "file": files[0].name,
        "path": str(files[0]),
        "entries": [],
        "latest_scan": newest_scan,
    }


def find_pdf_by_arxiv(arxiv_id):
    token = arxiv_id.replace(".", "_")
    idx = _inventory()["pdf_index"]
    if token in idx:
        return idx[token]
    base = re.sub(r"v\d+$", "", token)
    return idx.get(base)


def kb_categories():
    return _cached("kb_categories", 300, _kb_categories_raw)


def _kb_categories_raw():
    out = []
    kb = kb_root()
    for name, n in _inventory()["cat_counts"].items():
        if not n:
            continue
        label = "未分类(根目录)" if name == "根目录" else name
        path = kb if name == "根目录" else kb / name
        out.append({"name": label, "count": n, "path": str(path)})
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


def changelog_tail(n=6):
    log = inbox_dir() / "更新日志.md"
    if not log.exists():
        return []
    lines = [ln for ln in log.read_text(encoding="utf-8-sig", errors="replace").splitlines() if ln.strip()]
    return lines[-n:]


def load_settings():
    f = _DATA("widget_settings.json")
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_settings(data):
    (_DATA("widget_settings.json")).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _log_exc(exc_type, exc, tb):
    try:
        import traceback
        with open(str(_DATA("last_error.log")), "a", encoding="utf-8") as fh:
            fh.write("\n" + datetime.datetime.now().isoformat() + " "
                     + getattr(exc_type, "__name__", "Error") + ": " + str(exc) + "\n")
            traceback.print_exception(exc_type, exc, tb, file=fh)
    except Exception:
        pass


def recent_pdfs(days=14, limit=6):
    return _cached("recent_pdfs_%s_%s" % (days, limit), 300,
                   lambda: _recent_pdfs_raw(days, limit))


def _recent_pdfs_raw(days=14, limit=6):
    kb = kb_root()
    if not kb.exists():
        return []
    now = datetime.datetime.now().timestamp()
    out = []
    for mtime, size, p in _inventory()["pdfs"]:
        if now - mtime <= days * 86400:
            mt = datetime.datetime.fromtimestamp(mtime)
            try:
                rel = p.relative_to(kb).parts
            except Exception:
                rel = (p.name,)
            cat = rel[0] if len(rel) > 1 else "根目录"
            out.append({"name": p.name, "date": mt.strftime("%m-%d"),
                        "cat": cat, "path": str(p), "mt": mt})
    return out[:limit]


def recent_files(limit=6):
    return _cached("recent_files_%s" % (limit,), 180,
                   lambda: _recent_files_raw(limit))


def _recent_files_raw(limit=6):
    kb = kb_root()
    if not kb.exists():
        return []
    out = []
    for mtime, size, p in _inventory()["files"][:limit]:
        mt = datetime.datetime.fromtimestamp(mtime)
        try:
            rel = p.relative_to(kb).parts
        except Exception:
            rel = (p.name,)
        cat = rel[0] if len(rel) > 1 else "根目录"
        out.append({"name": p.name, "date": mt.strftime("%m-%d %H:%M"),
                    "cat": cat, "path": str(p), "mt": mt})
    return out


def search_kb(kw, limit=10):
    kb = kb_root()
    if not kb.exists():
        return []
    out = []
    seen = set()
    low = kw.lower()
    for p in kb.rglob("*.pdf"):
        if low in p.name.lower() or low in p.stem.lower():
            cat = p.parent.name if p.parent != kb else "根目录"
            out.append({"name": p.name, "cat": cat, "path": str(p)})
            seen.add(str(p))
    for pattern in ("*.md", "*.txt"):
        for p in kb.rglob(pattern):
            if str(p) in seen:
                continue
            hit = low in p.name.lower()
            if not hit:
                try:
                    if p.stat().st_size <= 2 * 1024 * 1024:
                        hit = low in p.read_text(encoding="utf-8", errors="ignore").lower()
                except Exception:
                    hit = False
            if hit:
                cat = p.parent.name if p.parent != kb else "根目录"
                out.append({"name": p.name, "cat": cat, "path": str(p)})
                seen.add(str(p))
    return out[:limit]


def today_inbox_pdfs():
    return _cached("today_inbox", 120, _today_inbox_raw)


def _today_inbox_raw():
    d = inbox_dir() / datetime.date.today().isoformat()
    if not d.exists():
        return 0
    return sum(1 for p in d.glob("*.pdf"))


def _arxiv_code(text):
    m = re.search(r"(\d{4})[._](\d{4,6})", text)
    return (m.group(1) + "." + m.group(2)) if m else ""


def _emit(progress, stage, pct=None, detail=""):
    if progress:
        try:
            progress(stage, pct, detail)
        except Exception:
            pass


def run_preview(days=None, progress=None):
    _emit(progress, "并行查询 arXiv", 10, "8 条检索式")
    import kbscan
    cfg = kbscan.load_config(str(CONFIG_FILE))
    window = days if days is not None else cfg.get("days_back", 7)
    per_query = cfg.get("max_results_per_query", 8)
    queries = list(cfg.get("queries", []))
    seen = kbscan.load_seen(_DATA("seen_ids.json"))
    cutoff = (datetime.date.today() - datetime.timedelta(days=window)).isoformat()

    def fetch(query):
        try:
            xml = kbscan.api_query(query, per_query, timeout=12)
            return kbscan.parse_entries(xml), ""
        except Exception as exc:
            return [], str(exc)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, q) for q in queries]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    candidates, seen_ids, errors = [], set(), []
    for entries, err in results:
        if err:
            errors.append(err)
            continue
        for e in entries:
            if e["id"] in seen or e["id"] in seen_ids:
                continue
            if e["published"] < cutoff:
                continue
            if not kbscan.relevant(e, cfg):
                continue
            seen_ids.add(e["id"])
            candidates.append(e)
    candidates.sort(key=lambda x: x["published"], reverse=True)
    _emit(progress, "筛选候选", 75, str(len(candidates)) + " 篇命中")

    lines = [
        "抓取预演（近 " + str(window) + " 天，不下载）",
        "候选: " + str(len(candidates)) + " 篇 · 查询成功 "
        + str(len(queries) - len(errors)) + "/" + str(len(queries)),
    ]
    actions = {}
    for i, e in enumerate(candidates[:20], 1):
        lines.append(str(i) + ". " + e["published"] + " | " + e["title"])
        url = kbscan.ARXIV_ABS.format(e["id"])
        actions[len(lines) - 1] = ("open_url", url)
        lines.append("    " + url)
    if not candidates and not errors:
        lines.append("没有通过过滤的新论文。")
    if errors:
        lines.append("")
        lines.append("查询失败 " + str(len(errors)) + " 条（网络不可达或超时）")
    _emit(progress, "预演完成", 100, "候选 " + str(len(candidates)) + " 篇")
    return lines, actions


def export_papers_xlsx(progress=None):
    _emit(progress, "扫描知识库", 10, "")
    inv = _inventory()
    kb = kb_root()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    rows = []
    for mtime, size, p in inv["pdfs"]:
        try:
            rel = p.relative_to(kb)
        except Exception:
            rel = Path(p.name)
        parts = rel.parts
        cat = parts[0] if len(parts) > 1 else "根目录"
        rows.append({"cat": cat, "name": p.name, "rel": str(rel),
                     "mb": round(size / 1048576.0, 2),
                     "mtime": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                     "arxiv": _arxiv_code(p.stem)})
    rows.sort(key=lambda r: (r["cat"], r["name"].lower()))
    _emit(progress, "写入 Excel", 60, str(len(rows)) + " 篇")
    try:
        from openpyxl import Workbook
    except Exception:
        import csv
        path = EXPORT_DIR / ("论文清单-" + stamp + ".csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["分类", "文件名", "相对路径", "大小(MB)", "修改时间", "arXiv"])
            for r in rows:
                w.writerow([r["cat"], r["name"], r["rel"], r["mb"], r["mtime"], r["arxiv"]])
        return path
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = "论文清单"
    ws.append(["分类", "文件名", "相对路径", "大小(MB)", "修改时间", "arXiv"])
    for r in rows:
        ws.append([r["cat"], r["name"], r["rel"], r["mb"], r["mtime"], r["arxiv"]])
    head_font = Font(bold=True, color="E6FAFF")
    head_fill = PatternFill("solid", fgColor="08344A")
    for cell in ws[1]:
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for letter, width in (("A", 16), ("B", 55), ("C", 60), ("D", 10), ("E", 18), ("F", 14)):
        ws.column_dimensions[letter].width = width
    ws2 = wb.create_sheet("分类统计")
    ws2.append(["分类", "数量"])
    counts = {}
    for r in rows:
        counts[r["cat"]] = counts.get(r["cat"], 0) + 1
    for name in sorted(counts, key=lambda x: (-counts[x], x)):
        ws2.append([name, counts[name]])
    for cell in ws2[1]:
        cell.font = head_font
        cell.fill = head_fill
    ws2.column_dimensions["A"].width = 22
    ws2.column_dimensions["B"].width = 10
    path = EXPORT_DIR / ("论文清单-" + stamp + ".xlsx")
    wb.save(path)
    _emit(progress, "导出完成", 100, path.name)
    return path


def health_check(progress=None):
    _emit(progress, "扫描与查重", 10, "")
    inv = _inventory()
    kb = kb_root()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = inv["pdfs"]
    groups = {}
    for _mtime, _size, p in pdfs:
        code = _arxiv_code(p.stem)
        key = code or re.sub(r"[^a-z0-9]+", "", p.stem.lower())[:90]
        groups.setdefault(key, []).append(p)
    dups = {k: v for k, v in groups.items() if len(v) > 1}
    inbox = inbox_dir()
    inbox_pdfs = [p for _m, _s, p in pdfs if inbox in p.parents]
    missing_txt = [p for p in inbox_pdfs if not p.with_suffix(".txt").exists()]
    idx_path = kb / "索引.md"
    index_text = ""
    if idx_path.exists():
        try:
            index_text = idx_path.read_text(encoding="utf-8-sig", errors="ignore").lower()
        except Exception:
            pass
    unindexed = []
    for _m, _s, p in pdfs:
        code = _arxiv_code(p.stem)
        key = code.lower() if code else p.stem[:32].lower()
        if key and key not in index_text:
            unindexed.append(p)
    big = [p for _m, size, p in pdfs if size > 25 * 1024 * 1024]
    empty = []
    if kb.exists():
        for d in kb.iterdir():
            if d.is_dir() and not any(x.is_file() for x in d.iterdir()):
                empty.append(d)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    report = EXPORT_DIR / ("知识库体检-" + stamp + ".md")
    lines = [
        "# 知识库体检报告 " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "",
        "- PDF 总数: " + str(len(pdfs)),
        "- 重复论文组: " + str(len(dups)),
        "- 新论文缺首页 txt: " + str(len(missing_txt)),
        "- 索引未收录: " + str(len(unindexed)),
        "- 超大 PDF(>25MB): " + str(len(big)),
        "- 空分类目录: " + str(len(empty)),
        "",
        "## 重复论文",
    ]
    if dups:
        for key, items in list(dups.items())[:40]:
            lines.append("- " + key + ": " + " | ".join(x.name for x in items))
    else:
        lines.append("- 无")
    lines += ["", "## 新论文缺首页 txt", ""]
    lines += ["- " + str(p) for p in missing_txt[:80]] or ["- 无"]
    lines += ["", "## 索引未收录（前 120 条）", ""]
    lines += ["- " + str(p.relative_to(kb)) for p in unindexed[:120]] or ["- 无"]
    lines += ["", "## 超大 PDF", ""]
    lines += ["- " + str(p.relative_to(kb)) for p in big[:40]] or ["- 无"]
    lines += ["", "## 空分类目录", ""]
    lines += ["- " + d.name for d in empty] or ["- 无"]
    report.write_text("\n".join(lines), encoding="utf-8-sig")
    _emit(progress, "生成报告", 90, report.name)
    summary = [
        "知识库体检完成",
        "PDF " + str(len(pdfs)) + " | 重复 " + str(len(dups)) + " 组 | 缺 txt "
        + str(len(missing_txt)) + " | 未收录 " + str(len(unindexed))
        + " | 超大 " + str(len(big)),
        "报告: " + report.name,
    ]
    return report, summary


def weekly_brief(days=7, progress=None):
    _emit(progress, "统计最近 " + str(days) + " 天", 20, "")
    inv = _inventory()
    kb = kb_root()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - days * 86400
    new_pdfs = [(m, s, p) for m, s, p in inv["pdfs"] if m >= cutoff]
    new_files = [(m, s, p) for m, s, p in inv["files"] if m >= cutoff]
    counts = {}
    for _m, _s, p in new_pdfs:
        try:
            parts = p.relative_to(kb).parts
        except Exception:
            parts = (p.name,)
        cat = parts[0] if len(parts) > 1 else "根目录"
        counts[cat] = counts.get(cat, 0) + 1
    digest = latest_digest_data()
    ts = task_status()
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    report = EXPORT_DIR / ("周报-" + stamp + ".md")
    lines = [
        "# 知识库周报 " + datetime.datetime.now().strftime("%Y-%m-%d"),
        "",
        "- 统计窗口: 最近 " + str(days) + " 天",
        "- 新增 PDF: " + str(len(new_pdfs)),
        "- 变动文件: " + str(len(new_files)),
        "- 知识库总量: " + str(inv["pdf_total"]) + " 篇 PDF",
        "- 下一步定时抓取: " + str(ts.get("next_run", "未知")),
        "",
        "## 分类新增",
    ]
    if counts:
        for name in sorted(counts, key=lambda x: (-counts[x], x)):
            lines.append("- " + name + ": " + str(counts[name]))
    else:
        lines.append("- 本周暂无新增")
    lines += ["", "## 最新速览"]
    if digest and digest["entries"]:
        for e in digest["entries"][:8]:
            lines.append("- " + e["title"])
    else:
        lines.append("- 暂无新速览")
    lines += ["", "## 最近变动文件"]
    for m, _s, p in new_files[:15]:
        lines.append("- " + datetime.datetime.fromtimestamp(m).strftime("%m-%d %H:%M")
                     + " | " + p.name)
    report.write_text("\n".join(lines), encoding="utf-8-sig")
    _emit(progress, "周报完成", 100, report.name)
    summary = [
        "周报已生成",
        "新增 PDF " + str(len(new_pdfs)) + " | 变动文件 " + str(len(new_files)),
        "文件: " + report.name,
    ]
    return report, summary


def load_memory():
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"mappings": {}, "history": []}


def save_memory(mem):
    try:
        mem = dict(mem)
        mem["history"] = mem.get("history", [])[-50:]
        MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass


def _translate_direction(direction):
    d = direction.lower()
    tokens = []

    def add(token):
        token = token.strip()
        if not token:
            return
        low = token.lower()
        for existing in tokens:
            if low == existing.lower() or low in existing.lower().split():
                return
        tokens.append(token)

    for zh, en in DIRECTION_TERMS.items():
        if zh.lower() in d:
            add(en)
    try:
        taxonomy = load_research_taxonomy()
    except Exception:
        taxonomy = {"categories": {}}
    low_direction = direction.lower()
    for entry in taxonomy.get("categories", {}).values():
        for sub in entry.get("subs", []):
            name = (sub.get("name") or "").strip()
            aliases = [a for a in sub.get("aliases", []) if a]
            matched = bool(name and name.lower() in low_direction)
            matched = matched or any(a.lower() in low_direction for a in aliases)
            if matched:
                for keyword in sub.get("keywords", [])[:4]:
                    add(keyword)
    for word in re.findall(r"[A-Za-z][A-Za-z0-9\-]+", direction):
        if word.lower() not in ("paper", "papers", "latest", "recent",
                                "download", "find", "new"):
            add(word)
    if not tokens:
        tokens = [direction.strip()]
    return tokens[:6]


def _build_arxiv_query(tokens):
    parts = []
    for tok in tokens:
        if " " in tok or "-" in tok:
            parts.append('all:"' + tok + '"')
        else:
            parts.append("all:" + tok)
    return " AND ".join(parts)


def _entry_matches_tokens(entry, tokens):
    hay = (entry["title"] + " " + entry["summary"]).lower()
    for tok in tokens:
        words = [w for w in re.split(r"[^a-z0-9\-]+", tok.lower()) if w]
        if not words or not any(w in hay for w in words):
            return False
    return True


def _resolve_category(direction, text, mem):
    cats = [c["name"] for c in kb_categories()
            if c["name"] != "未分类(根目录)"]
    low = text.lower()
    m = re.search(r"(?:放到|归到|分类到|存入|保存到|放进)\s*([^\s，。,.]+)", text)
    if m:
        raw = m.group(1)
        match = next((c for c in cats if c == raw), None)
        return (match or raw), True
    for c in sorted(cats, key=len, reverse=True):
        if c.lower() in low:
            return c, True
    maps = mem.get("mappings", {})
    if direction in maps:
        return maps[direction], False
    for key, cat in sorted(maps.items(), key=lambda kv: -len(kv[0])):
        if key and key in direction:
            return cat, False
    for kw, cat in CATEGORY_HINTS:
        if kw in direction.lower():
            return cat, False
    return "", False


def parse_smart_command(text):
    t = text.strip()
    low = t.lower()
    if not re.search(r"(下载|抓取|获取|找|收集)", t):
        return None
    if not re.search(r"(论文|paper|篇)", low):
        return None
    if re.fullmatch(r"\s*(抓取|下载|扫描)\s*\d+\s*(?:篇|papers?)?\s*(?:论文|papers?)?\s*", t):
        return None
    if re.fullmatch(r"\s*(抓取|下载|扫描)\s*\d+\s*天\s*", t):
        return None
    m = re.search(r"(\d+)\s*(?:篇|papers?)", low)
    if not m:
        m = re.search(r"(?:下载|抓取|获取|找|收集)\s*(\d+)", t)
    count = int(m.group(1)) if m else 10
    count = max(1, min(count, 50))
    m = re.search(r"最近\s*(\d+)\s*天", t)
    days = int(m.group(1)) if m else None
    mem = load_memory()
    s = re.sub(r"(?:放到|归到|分类到|存入|保存到|放进)[^，。,.]+", " ", t)
    s = re.sub(r"最近\s*\d+\s*天|最新的?|最近的?|相关(?:的)?|方向的?|领域(?:的)?", " ", s)
    s = re.sub(r"(?:下载|抓取|获取|找|收集|帮我|我想要|我要|请)", " ", s)
    s = re.sub(r"\d+\s*(?:篇|papers?|天)", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(?:的\s*)?(?:论文|papers?)", " ", s, flags=re.I)
    s = re.sub(r"[\s，。,.：:；;、]+", " ", s).strip()
    s = re.sub(r"^(关于|有关)", "", s).strip()
    s = re.sub(r"的$", "", s).strip()
    if s in ("什么", "什么方向", "任意", "任意方向", "任何方向", "随便",
             "最新方向", ""):
        s = "多模态目标检测"
    direction = s
    tokens = _translate_direction(direction)
    unknown = all(all(ord(ch) < 128 for ch in tok) is False for tok in tokens)
    category, explicit = _resolve_category(direction, t, mem)
    return {
        "raw": text,
        "direction": direction,
        "tokens": tokens,
        "query": _build_arxiv_query(tokens),
        "count": count,
        "days": days,
        "category": category,
        "explicit_category": explicit,
        "unknown": unknown,
    }


def smart_fetch(spec, download=True, progress=None):
    import kbscan
    cfg = kbscan.load_config(str(CONFIG_FILE))
    days = spec.get("days")
    cutoff = ((datetime.date.today() - datetime.timedelta(days=days)).isoformat()
              if days else None)
    seen = kbscan.load_seen(_DATA("seen_ids.json"))
    per_query = min(60, max(12, spec["count"] * 4))
    _emit(progress, "查询 arXiv", 5, spec["query"])
    xml = kbscan.api_query(spec["query"], per_query,
                           timeout=cfg.get("query_timeout", 20))
    entries = kbscan.parse_entries(xml)
    _emit(progress, "筛选候选", 20, str(len(entries)) + " 条结果")
    candidates, picked = [], set()
    for e in entries:
        if e["id"] in seen or e["id"] in picked:
            continue
        if cutoff and e["published"] < cutoff:
            continue
        if not _entry_matches_tokens(e, spec["tokens"]):
            continue
        picked.add(e["id"])
        candidates.append(e)
    candidates.sort(key=lambda x: x["published"], reverse=True)
    _emit(progress, "命中候选", 25, str(len(candidates)) + " 篇")
    if not download:
        return {"candidates": candidates[:spec["count"]], "total": len(candidates),
                "query": spec["query"]}

    if spec["category"]:
        target = kb_root() / spec["category"]
    else:
        target = inbox_dir() / datetime.date.today().isoformat()
    target.mkdir(parents=True, exist_ok=True)
    downloaded, failed = [], []
    targets = candidates[:spec["count"]]
    total = max(1, len(targets))
    for idx, e in enumerate(targets, 1):
        base = 25 + 65.0 * (idx - 1) / total
        span = 65.0 / total
        _emit(progress, "下载 " + str(idx) + "/" + str(len(targets)),
              int(base), e["title"][:60])
        last = {"pct": -1}

        def on_bytes(got, total_bytes, frac, entry=e, start=base, width=span,
                     number=idx, state=last):
            overall = start + width * (frac if frac is not None else 0.5)
            pct = int(min(94, max(0, overall)))
            if pct == state["pct"]:
                return
            state["pct"] = pct
            if total_bytes:
                detail = ("%.1f/%.1f MB · " % (got / 1048576.0,
                                               total_bytes / 1048576.0))
            else:
                detail = ("%.1f MB · " % (got / 1048576.0))
            _emit(progress, "下载 " + str(number) + "/" + str(len(targets)),
                  pct, detail + entry["title"][:45])

        try:
            pdf = kbscan.download_pdf_stream(e, target, progress=on_bytes)
            text, engine = kbscan.extract_first_page(pdf)
            if text:
                pdf.with_suffix(".txt").write_text(text, encoding="utf-8")
            e["text_engine"] = engine
            downloaded.append(e)
            _emit(progress, "已保存 " + str(idx) + "/" + str(len(targets)),
                  int(min(95, base + span)), pdf.name[:70])
        except Exception as exc:
            failed.append((e["id"], str(exc)))
    if downloaded:
        kbscan.save_seen(_DATA("seen_ids.json"),
                         seen | {e["id"] for e in downloaded})

    digest_path = ""
    if downloaded:
        now = datetime.datetime.now()
        lines = [
            "# 智能抓取速览 " + now.strftime("%Y-%m-%d %H:%M"),
            "",
            "> 方向: " + spec["direction"] + " | 分类: "
            + (spec["category"] or "新论文/日期") + " | 查询: " + spec["query"],
            "",
        ]
        for i, e in enumerate(downloaded, 1):
            lines += [
                "## " + str(i) + ". " + e["title"],
                "- arXiv: " + kbscan.ARXIV_ABS.format(e["id"]),
                "- 日期: " + e["published"],
                "- 作者: " + ", ".join(e["authors"][:6]),
                "- 摘要: " + e["summary"][:500],
                "",
            ]
        digest = inbox_dir() / ("新论文速览-" + now.strftime("%Y-%m-%d_%H%M") + ".md")
        digest.write_text("\n".join(lines), encoding="utf-8-sig")
        digest_path = str(digest)
        kbscan.append_changelog(inbox_dir(), now.date().isoformat(), downloaded)
    _emit(progress, "写入速览与记忆", 95, target.name)

    mem = load_memory()
    if spec["explicit_category"] and spec["category"]:
        mem.setdefault("mappings", {})[spec["direction"]] = spec["category"]
    mem.setdefault("history", []).append({
        "time": datetime.datetime.now().isoformat(timespec="minutes"),
        "command": spec["raw"],
        "direction": spec["direction"],
        "query": spec["query"],
        "category": spec["category"],
        "count": spec["count"],
        "downloaded": len(downloaded),
        "ids": [e["id"] for e in downloaded],
    })
    save_memory(mem)
    _emit(progress, "智能下载完成", 100, "下载 " + str(len(downloaded)) + " 篇")
    return {"downloaded": downloaded, "failed": failed, "target": str(target),
            "digest": digest_path, "candidates": len(candidates),
            "query": spec["query"], "category": spec["category"]}


def load_research_memory():
    try:
        return json.loads(RESEARCH_MEMORY.read_text(encoding="utf-8"))
    except Exception:
        return {"directions": [], "ideas": [], "handoffs": []}


def save_research_memory(mem):
    try:
        mem["directions"] = mem.get("directions", [])[-50:]
        mem["ideas"] = mem.get("ideas", [])[-100:]
        mem["handoffs"] = mem.get("handoffs", [])[-50:]
        RESEARCH_MEMORY.write_text(json.dumps(mem, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    except Exception:
        pass


def knowledge_overview(progress=None):
    _emit(progress, "汇总分类与索引", 10, "")
    inv = _inventory()
    kb = kb_root()
    cats = kb_categories()
    digest = latest_digest_data()
    cutoff = time.time() - 30 * 86400
    recent = [(m, s, p) for m, s, p in inv["pdfs"] if m >= cutoff]
    summary_files = []
    summary_dir = kb / "分类总结"
    if summary_dir.exists():
        for f in sorted(summary_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8-sig", errors="ignore")
            except Exception:
                text = ""
            headings = [ln.strip() for ln in text.splitlines() if ln.startswith("#")][:5]
            summary_files.append((f.name, headings, f.stat().st_size))
    idx_path = kb / "索引.md"
    index_text = ""
    if idx_path.exists():
        try:
            index_text = idx_path.read_text(encoding="utf-8-sig", errors="ignore").lower()
        except Exception:
            pass
    unindexed = 0
    for _m, _s, p in inv["pdfs"]:
        code = _arxiv_code(p.stem)
        key = code.lower() if code else p.stem[:32].lower()
        if key and key not in index_text:
            unindexed += 1
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    report = EXPORT_DIR / ("科研知识总览-" + stamp + ".md")
    lines = [
        "# 科研知识总览 " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "",
        "## 知识库规模",
        "- PDF: " + str(inv["pdf_total"]) + " 篇",
        "- 首页文本: " + str(inv["txt_total"]) + " 个",
        "- 分类数: " + str(len(cats)),
        "- 索引未收录: " + str(unindexed) + " 篇",
        "- 最近 30 天新增: " + str(len(recent)) + " 篇",
        "",
        "## 分类分布",
    ]
    for c in cats:
        lines.append("- " + c["name"] + ": " + str(c["count"]) + " 篇")
    lines += ["", "## 最近 30 天新增（最多 20 条）", ""]
    if recent:
        for m, _s, p in sorted(recent, key=lambda x: x[0], reverse=True)[:20]:
            lines.append("- " + datetime.datetime.fromtimestamp(m).strftime("%m-%d")
                         + " | " + p.name)
    else:
        lines.append("- 暂无")
    lines += ["", "## 最新速览", ""]
    if digest and digest["entries"]:
        for e in digest["entries"][:12]:
            lines.append("- " + e["title"] + " | arXiv " + (e["arxiv"] or "未知"))
    else:
        lines.append("- 暂无速览条目")
    lines += ["", "## 分类总结文件", ""]
    if summary_files:
        for name, headings, size in summary_files:
            lines.append("- " + name + " (" + str(size) + " bytes)")
            for h in headings:
                lines.append("  - " + h)
    else:
        lines.append("- 暂无")
    lines += ["", "## 下一步建议", "",
              "- 用「方向拓展」生成深挖任务，交给 deep-research / ccf-literature-searcher",
              "- 用「创新点库」评估机制与应用场景，交给 ccf-idea-optimizer / reviewer",
              "- 更新索引与分类总结时保持只追加、不改旧条目"]
    report.write_text("\n".join(lines), encoding="utf-8-sig")
    _emit(progress, "知识总览完成", 100, report.name)
    summary = [
        "科研知识总览已生成",
        "PDF " + str(inv["pdf_total"]) + " | 分类 " + str(len(cats))
        + " | 近30天新增 " + str(len(recent)) + " | 未收录 " + str(unindexed),
        "报告: " + report.name,
    ]
    return report, summary


DIRECTION_MODES = ("自动混合", "稳健邻接", "跨领域迁移", "高风险高回报")


def _direction_questions(strategy):
    if strategy == "跨领域迁移":
        return [
            "目标领域的核心假设迁移到当前问题后，哪些仍然成立、哪些必须修改？",
            "跨域增益来自新的信息增量，还是仅来自更大模型或更多数据？",
            "需要哪些统一数据集、强 baseline 和消融，才能证明它不是简单拼接？",
        ]
    if strategy == "高风险高回报":
        return [
            "拟定义的新问题、新范式或新评测协议是否足够独立、重要且可复现？",
            "如果主假设失败，最小的替代路径和可交付结果是什么？",
            "第一阶段最小验证实验、成功阈值与停止条件分别是什么？",
        ]
    return [
        "相对现有工作的真实增益来自哪个机制，如何通过消融把增益分离出来？",
        "该方向在哪些数据、场景或噪声条件下最容易失效？",
        "能否提出一个可证伪的关键假设，并用最小实验快速支持或否定？",
    ]


def _field_entry(taxonomy, category, field):
    for sub in taxonomy.get("categories", {}).get(category, {}).get("subs", []):
        if sub.get("name") == field:
            return sub
    return {"name": field, "aliases": [], "keywords": []}


def _direction_terms(direction, sub):
    text = " ".join([
        direction,
        " ".join(sub.get("aliases", [])),
        " ".join(sub.get("keywords", [])),
    ]).lower()
    return {token for token in re.split(r"[^a-z0-9\u4e00-\u9fff+\-]+", text)
            if len(token) >= 2}


def _related_fields_for_direction(direction, category, field, limit=8):
    taxonomy = load_research_taxonomy()
    relations = load_research_relations()
    base = _field_entry(taxonomy, category, field)
    ref = _direction_terms(direction, base)
    profile_key = field_profile(category, field, relations)
    related_categories = relations.get("category_related", {}).get(category, [])
    if not related_categories:
        profile = relations.get("profiles", {}).get(profile_key, {})
        candidates = [
            name for name, mapping in relations.get("category_profiles", {}).items()
            if profile_key in mapping.values() and name != category
        ]
        related_categories = candidates[:4]
    by_category = {}
    for related_category in related_categories:
        rows = []
        for sub in taxonomy.get("categories", {}).get(related_category, {}).get("subs", []):
            terms = {token.lower() for token in
                     sub.get("aliases", []) + sub.get("keywords", [])}
            overlap = len(ref & terms)
            target_profile = field_profile(related_category, sub.get("name", ""), relations)
            profile_bonus = 2 if target_profile == profile_key else 0
            rows.append((overlap + profile_bonus, related_category, sub))
        rows.sort(key=lambda row: (-row[0], row[2].get("name", "")))
        if rows:
            by_category[related_category] = rows

    selected = []
    depth = 0
    while len(selected) < limit:
        added = False
        for related_category in related_categories:
            rows = by_category.get(related_category, [])
            if depth < len(rows):
                selected.append(rows[depth])
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        depth += 1
    return selected


def expand_direction_candidates(direction, mode="自动混合", limit=18):
    direction = (direction or "").strip()
    if not direction:
        return []
    taxonomy = load_research_taxonomy()
    relations = load_research_relations()
    category, field, confidence = infer_category_field(direction)
    if category and field:
        profile_key = field_profile(category, field, relations)
        profile = relations.get("profiles", {}).get(profile_key, {})
    else:
        profile_key, profile = "ml_method", {}

    candidates = []
    seen = set()

    def add(title, strategy, reason, relevance, novelty, feasibility,
            target_category=None, target_field=None):
        title = re.sub(r"\s+", " ", title).strip()
        if not title or title in seen:
            return
        seen.add(title)
        total = round(0.45 * relevance + 0.30 * novelty + 0.25 * feasibility)
        candidates.append({
            "title": title,
            "strategy": strategy,
            "reason": reason,
            "relevance": int(relevance),
            "novelty": int(novelty),
            "feasibility": int(feasibility),
            "score": int(total),
            "category": target_category or category,
            "field": target_field or field,
            "base_category": category,
            "base_field": field,
            "base_confidence": confidence,
            "profile": profile_key,
            "questions": _direction_questions(strategy),
        })

    include_stable = mode in ("自动混合", "稳健邻接")
    include_cross = mode in ("自动混合", "跨领域迁移")
    include_bold = mode in ("自动混合", "高风险高回报")

    if include_stable:
        low = direction.lower()
        stable = []
        for key, items in RESEARCH_SUGGESTIONS.items():
            if key in low:
                stable.extend(items)
        stable.extend(GENERIC_DIRECTIONS)
        for index, suggestion in enumerate(stable):
            if suggestion.startswith("开放词汇"):
                title = direction + "的开放词汇扩展"
            elif suggestion == "域泛化":
                title = "跨域泛化条件下的" + direction
            elif suggestion.startswith("Benchmark"):
                title = direction + "的统一评测基准与失败分析"
            elif suggestion.startswith("轻量化"):
                title = direction + "的轻量化与实时部署"
            else:
                title = suggestion + "驱动的" + direction + "改进"
            add(title, "稳健邻接",
                "与基础方向共享任务、数据或评价协议，适合作为第一阶段的低风险增量。",
                90 - min(12, index), 45 + min(25, index * 3),
                88 - min(18, index * 2))

    if include_cross:
        for index, (_overlap, related_category, sub) in enumerate(
                _related_fields_for_direction(direction, category, field, limit=8)):
            target_field = sub.get("name", "")
            add("融合" + target_field + "机制的" + direction,
                "跨领域迁移",
                "把“" + target_field + "”的机制迁移到当前问题；需要证明信息增量和可归因增益。",
                72 - min(12, index), 72 + min(18, index * 2),
                68 - min(20, index * 2),
                related_category, target_field)
        methods = list(profile.get("methods", []))[:3]
        scenarios = list(profile.get("scenarios", []))[:2]
        for index, method in enumerate(methods):
            add("基于" + method + "的" + direction + "新机制",
                "跨领域迁移",
                "方法迁移能形成清晰的技术差异，但需要与领域内原生方法做强对比。",
                74 - index * 3, 74 + index * 4, 67 - index * 4)
        for index, scenario in enumerate(scenarios):
            add("面向" + scenario + "真实约束的" + direction,
                "跨领域迁移",
                "真实场景会引入分布漂移、成本与时延约束，是应用型创新的直接入口。",
                76 - index * 3, 70 + index * 4, 64 - index * 5)

    if include_bold:
        bold_templates = (
            direction + "的新任务定义与可复现评测协议",
            "从离线 benchmark 到真实开放环境的" + direction + "持续演化",
            direction + "的因果机制与反事实鲁棒性",
            "世界模型驱动的" + direction + "闭环推理",
            "硬件—算法协同约束下的" + direction + "极限部署",
            "自进化智能体框架中的" + direction + "长期学习",
        )
        for index, title in enumerate(bold_templates):
            add(title, "高风险高回报",
                "可能形成新问题、新范式或新评测协议，但需要先验证定义是否成立以及最小实验是否可做。",
                52 - min(12, index * 2), 92 - min(12, index * 2),
                46 - min(15, index * 3))

    candidates.sort(key=lambda item: (
        -item["score"], -item["novelty"], -item["feasibility"], item["title"]))
    return candidates[:max(1, limit)]


def direction_suggestions(direction):
    return [item["title"] for item in
            expand_direction_candidates(direction, "自动混合", 12)]


def save_prompt(kind, text):
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = PROMPT_DIR / (kind + "-" + stamp + ".md")
    path.write_text(text, encoding="utf-8-sig")
    return path


def direction_prompt(direction, suggestions):
    cats = ", ".join(c["name"] + "(" + str(c["count"]) + ")" for c in kb_categories())
    queries = "\n".join("- " + q for q in load_config().get("queries", []))
    sugg = "\n".join("- " + s for s in suggestions)
    return (
        "【研究方向拓展任务】\n"
        "方向: " + direction + "\n"
        "知识库: " + str(kb_root()) + "\n"
        "现有分类: " + cats + "\n"
        "现有检索词:\n" + queries + "\n\n"
        "本地候选拓展方向:\n" + sugg + "\n\n"
        "请调用 deep-research / nature-academic-search / ccf-literature-searcher / supervisor-agent，"
        "完成以下工作：\n"
        "1) 梳理该方向近 2 年关键进展与代表工作，逐条给出可核验引用；\n"
        "2) 给出 5 个可拓展子方向，逐项说明动机、已有证据、竞争程度、可行性和风险；\n"
        "3) 对照知识库现有分类与论文，指出重叠、空白和可迁移方法；\n"
        "4) 提出 3 个可执行研究问题，并给出最小可行实验（数据、baseline、指标、消融）；\n"
        "5) 输出 Markdown，追加到知识库/分类总结/方向拓展-" + datetime.date.today().isoformat() + ".md，"
        "不要修改旧条目。"
    )


def expanded_direction_prompt(direction, candidates, selected=None, context=""):
    """交接提示词：把候选池交给一个能联网检索的 AI 去核验。

    `context` 是可选的「我的情况」段（由 prompt_context.block 生成）。
    不给时整段不出现 —— 这段决定了 AI 给的实验预算、时间安排是否对得上
    一个真实在读的学生，而不是对一个抽象用户。"""
    cats = ", ".join(c["name"] + "(" + str(c["count"]) + ")"
                     for c in kb_categories())
    candidate_lines = []
    for index, item in enumerate(candidates, 1):
        candidate_lines.append(
            str(index) + ". " + item["title"]
            + " | " + item["strategy"]
            + " | 相关 " + str(item["relevance"])
            + " / 新颖 " + str(item["novelty"])
            + " / 可行 " + str(item["feasibility"])
            + " | " + item["reason"]
        )
    priority = ""
    if selected:
        priority = (
            "\n优先评估候选: " + selected["title"]
            + "\n候选所在领域: " + (selected.get("category") or "待识别")
            + " / " + (selected.get("field") or "待识别")
            + "\n需要验证的关键问题:\n"
            + "\n".join("- " + question for question in selected.get("questions", []))
            + "\n"
        )
    return (
        "【方向拓展与验证任务】\n"
        "基础方向: " + direction + "\n"
        "知识库: " + str(kb_root()) + "\n"
        "现有分类: " + cats + "\n"
        "当前检索式:\n"
        + "\n".join("- " + q for q in load_config().get("queries", []))
        + "\n\n本地候选池（启发式生成，不是已验证结论）:\n"
        + "\n".join(candidate_lines)
        + "\n"
        + priority
        + context
        + "\n请调用 deep-research、nature-academic-search、ccf-literature-searcher、"
          "ccf-idea-reviewer 和 ccf-experiment-designer，完成：\n"
          "1) 对基础方向做近两年的证据地图，只引用能够核验的真实论文；\n"
          "2) 验证本地候选池，删除过空泛、已被充分覆盖或不可行的条目，并说明依据；\n"
          "3) 重新给出不超过 5 个候选，分别评估相关性、新颖性、竞争强度、可行性和主要风险；\n"
          "4) 对优先候选写出可证伪假设、与现有工作的最小可归因差异、必要 baseline 和负结果判据；\n"
          "5) 对优先候选给出一个最小可行实验：数据、划分、指标、消融、预算与停止条件；\n"
          "6) 给出最终建议：继续、缩小范围、换题或停止，并说明决定性证据；\n"
          "7) 输出 Markdown 报告；未经检索验证的内容必须明确标为假设。"
    )


IDEA_TYPES = (
    "结构创新", "方法创新", "范式创新",
    "应用创新", "系统创新", "评测创新",
)
IDEA_STAGES = (
    "0 原始想法", "1 问题候选", "2 机制假设",
    "3 最小实验", "4 投稿候选", "已放弃",
)
IDEA_MECHANISMS = (
    "未指定", "算法与算子", "优化与求解", "表示与建模",
    "训练策略", "目标函数与损失", "推理与决策",
    "跨模态与跨域迁移", "数据利用", "不确定性与可信",
    "效率约束", "多任务与协同", "科学约束驱动",
)
IDEA_EVIDENCE_TYPES = (
    "未指定", "理论分析", "消融归因", "强 Baseline",
    "跨域/跨数据集", "效率与部署", "真实场景验证",
    "新 Benchmark/评测协议",
)
IDEA_RISK_TYPES = (
    "未指定", "新颖性风险", "机制风险", "数据风险",
    "竞争风险", "工程风险", "评测效度风险",
)


def _keyword_score(text, groups):
    score = 0
    matched = []
    for label, keywords, weight in groups:
        hits = [word for word in keywords if word.lower() in text]
        if hits:
            score += weight * min(2, len(hits))
            matched.append(label)
    return score, matched


def idea_type_scores(title, desc):
    text = (title + " " + desc).lower()
    signals = {
        "结构创新": [
            ("模块/架构", ["模块", "架构", "连接", "融合", "主干", "attention", "module"], 3),
        ],
        "方法创新": [
            ("算法/训练", ["算法", "损失", "优化", "训练", "推理", "约束", "loss", "optimization"], 3),
        ],
        "范式创新": [
            ("新问题/新协议", ["新问题", "新任务", "新范式", "定义", "协议", "problem formulation"], 5),
        ],
        "应用创新": [
            ("场景/用户", ["场景", "用户", "临床", "工业", "部署", "需求", "application"], 3),
        ],
        "系统创新": [
            ("系统/资源", ["系统", "平台", "时延", "吞吐", "资源", "可靠性", "端到端", "system"], 4),
        ],
        "评测创新": [
            ("指标/基准", ["评测", "指标", "基准", "数据集", "benchmark", "metric", "偏差"], 5),
        ],
    }
    scores = {}
    reasons = {}
    for idea_type, groups in signals.items():
        score, matched = _keyword_score(text, groups)
        scores[idea_type] = min(100, 20 + score * 8)
        reasons[idea_type] = matched
    return scores, reasons


def evaluate_idea_local(idea):
    title = (idea.get("title") or "").strip()
    desc = (idea.get("desc") or "").strip()
    text = (title + " " + desc).lower()
    chosen_type = idea.get("type") or infer_innovation_type(title, desc)
    mechanism_type = idea.get("mechanism_type") or "未指定"
    evidence_type = idea.get("evidence_type") or "未指定"
    risk_type = idea.get("risk_type") or "未指定"
    type_scores, type_reasons = idea_type_scores(title, desc)
    recommended_type = max(type_scores, key=type_scores.get)
    type_fit = type_scores.get(chosen_type, 20)

    value_score, value_hits = _keyword_score(text, [
        ("真实需求", ["需求", "痛点", "失败", "成本", "效率", "准确率", "鲁棒", "临床", "工业"], 9),
        ("可量化目标", ["提升", "降低", "减少", "加快", "指标", "百分比", "latency"], 7),
    ])
    novelty_score, novelty_hits = _keyword_score(text, [
        ("新问题/新协议", ["新问题", "新任务", "新范式", "新协议", "重新定义"], 12),
        ("新机制", ["机制", "因果", "反事实", "新框架", "新约束", "first"], 8),
        ("跨域迁移", ["跨域", "跨模态", "迁移", "统一", "联合建模"], 6),
    ])
    mechanism_score, mechanism_hits = _keyword_score(text, [
        ("作用机制", ["因为", "从而", "机制", "通过", "约束", "目标函数", "信息流"], 9),
        ("可检验差异", ["相比", "baseline", "对照", "消融", "归因", "可证伪"], 8),
    ])
    evidence_score, evidence_hits = _keyword_score(text, [
        ("数据", ["数据集", "数据", "划分", "dataset", "test set"], 7),
        ("baseline", ["baseline", "强基线", "现有方法", "对照"], 8),
        ("指标", ["指标", "metric", "miou", "ap", "accuracy", "f1"], 7),
        ("消融", ["消融", "ablation", "负结果", "失败案例"], 7),
    ])
    feasibility_score, feasibility_hits = _keyword_score(text, [
        ("资源可估算", ["单卡", "gpu", "算力", "预算", "训练时间", "推理时间"], 6),
        ("阶段计划", ["第一步", "最小实验", "里程碑", "两阶段", "先验证"], 7),
        ("风险预案", ["停止条件", "替代方案", "失败则", "降级方案"], 5),
    ])

    value = min(100, 35 + value_score + (10 if idea.get("domain") else 0)
                + min(15, len(desc) // 30))
    novelty = min(100, 32 + novelty_score
                  + (10 if chosen_type in ("范式创新", "评测创新") else 0))
    mechanism = min(100, 25 + mechanism_score
                    + (8 if len(desc) >= 100 else 0))
    evidence = min(100, 18 + evidence_score)
    feasibility = min(100, 42 + feasibility_score
                      + (8 if idea.get("category") and idea.get("field") else 0)
                      + (6 if idea.get("domain") else 0))
    if mechanism_type != "未指定":
        mechanism = min(100, mechanism + 10)
        feasibility_hits = list(feasibility_hits) + ["已标注二级机制"]
    if evidence_type != "未指定":
        evidence = min(100, evidence + 10)
        feasibility_hits = list(feasibility_hits) + ["已指定目标证据"]
    total = round(
        0.22 * value + 0.22 * novelty + 0.22 * mechanism
        + 0.18 * evidence + 0.16 * feasibility
    )

    gaps = []
    if "baseline" not in text and "对照" not in text and "现有方法" not in text:
        gaps.append("缺少明确的最强 baseline 或对照设置")
    if not any(word in text for word in ("数据", "dataset", "划分")):
        gaps.append("未说明数据来源、划分或评测集")
    if not any(word in text for word in ("指标", "metric", "ap", "miou", "accuracy", "f1")):
        gaps.append("未定义主指标与失败指标")
    if not any(word in text for word in ("消融", "ablation", "归因")):
        gaps.append("未说明如何通过消融证明机制可归因")
    if len(desc) < 60:
        gaps.append("描述过短，问题、机制和预期差异还不够具体")
    if type_scores.get(recommended_type, 0) >= type_fit + 16:
        gaps.append("创新类型可能标注不准：更像“" + recommended_type + "”")
    if chosen_type in ("应用创新", "系统创新"):
        if not any(word in text for word in ("成本", "时延", "资源", "部署", "吞吐")):
            gaps.append("应用/系统创新缺少成本、时延或部署约束")
    if chosen_type == "结构创新" and not any(
            word in text for word in ("信息流", "连接", "模块", "消融")):
        gaps.append("结构创新缺少模块连接关系与必要性说明")
    if chosen_type == "方法创新" and not any(
            word in text for word in ("机制", "假设", "目标函数", "算法")):
        gaps.append("方法创新缺少可检验的作用机制")
    if chosen_type == "范式创新" and not any(
            word in text for word in ("定义", "协议", "benchmark", "评测")):
        gaps.append("范式创新缺少问题定义或评测协议")
    if chosen_type == "评测创新" and not any(
            word in text for word in ("偏差", "盲区", "失效", "有效性", "一致性")):
        gaps.append("评测创新缺少现有指标盲区或效度分析")
    if mechanism_type == "未指定":
        gaps.append("尚未选择二级机制，无法区分创新到底改了什么")
    if evidence_type == "未指定":
        gaps.append("尚未指定最有说服力的证据类型")
    risk_prompts = {
        "新颖性风险": "主要风险是已有工作已覆盖；先做近两年检索和近邻工作对比。",
        "机制风险": "主要风险是机制不成立；先做可证伪假设和负结果判据。",
        "数据风险": "主要风险是数据偏差或泄漏；先检查划分、来源和跨集泛化。",
        "竞争风险": "主要风险是竞争激烈；先找最近邻工作和可区分的评价切片。",
        "工程风险": "主要风险是成本或部署不可行；先测资源、时延和故障恢复。",
        "评测效度风险": "主要风险是指标没测到目标能力；先验证指标敏感性和盲区。",
    }
    if risk_type in risk_prompts:
        gaps.append(risk_prompts[risk_type])

    if total >= 74 and evidence >= 55 and mechanism >= 55:
        stage = "4 投稿候选"
    elif evidence >= 42 and mechanism >= 42:
        stage = "3 最小实验"
    elif mechanism >= 34:
        stage = "2 机制假设"
    elif value >= 42 and novelty >= 40:
        stage = "1 问题候选"
    else:
        stage = "0 原始想法"

    if total < 40 or "创新类型可能标注不准" in " ".join(gaps):
        decision = "先重做问题定义与创新类型"
    elif evidence < 35:
        decision = "先补证据与 baseline，再决定投入"
    elif mechanism < 40:
        decision = "先补可检验机制与归因实验"
    elif total >= 72 and evidence >= 52:
        decision = "可进入最小实验或完整选题体检"
    else:
        decision = "保留为候选，先缩小问题范围"

    type_actions = {
        "结构创新": [
            "画出模块与信息流图，说明每个新增连接的不可替代性",
            "对每个新增模块、连接和融合位置分别消融",
            "与相同 backbone、相同训练预算的强 baseline 对齐",
        ],
        "方法创新": [
            "写出可证伪假设：什么变化会带来什么可测结果",
            "给出目标函数/训练/推理层面的最小机制差异",
            "设计失败案例、负结果和机制归因实验",
        ],
        "范式创新": [
            "给出正式的问题定义、输入输出和适用范围",
            "设计可复现的数据构建与评测协议",
            "证明新问题不是已有问题的改名",
        ],
        "应用创新": [
            "明确真实用户、场景约束和现有方案的具体失败点",
            "构建领域数据闭环并量化部署收益",
            "给出误差成本、人工介入和回滚方案",
        ],
        "系统创新": [
            "给出端到端 workload、时延、吞吐和资源预算",
            "与强工程 baseline 做同等硬件预算对比",
            "检查可靠性、可观测性和故障恢复",
        ],
        "评测创新": [
            "证明现有指标遗漏了什么能力或失败切片",
            "设计盲评、一致性、鲁棒性和效度验证",
            "公开构建协议并给出可复现 benchmark",
        ],
    }
    next_actions = list(type_actions.get(chosen_type, []))
    next_actions.extend([
        "补齐数据、baseline、主指标、消融和失败判据",
        "先做最小可行实验，再决定是否扩大投入",
    ])
    strengths = []
    for label, hits in (
        ("价值线索", value_hits), ("新颖性线索", novelty_hits),
        ("机制线索", mechanism_hits), ("证据线索", evidence_hits),
        ("可行性线索", feasibility_hits),
    ):
        if hits:
            strengths.append(label + ": " + "、".join(hits))

    return {
        "total": int(total),
        "stage": stage,
        "decision": decision,
        "mechanism_type": mechanism_type,
        "evidence_type": evidence_type,
        "risk_type": risk_type,
        "scores": {
            "价值": int(value), "新颖性": int(novelty),
            "机制清晰度": int(mechanism), "证据准备度": int(evidence),
            "可行性": int(feasibility), "类型匹配": int(type_fit),
        },
        "recommended_type": recommended_type,
        "type_reasons": type_reasons,
        "strengths": strengths,
        "gaps": gaps,
        "next_actions": next_actions[:5],
    }


def idea_prompt(idea, mode="apply"):
    itype = idea.get("type", "方法创新")
    assessment = evaluate_idea_local(idea)
    type_guide = {
        "结构创新": "重点检查模块/连接/架构差异、必要性与消融；避免只做模块堆叠。",
        "方法创新": "重点检查算法/损失/训练/推理机制的理论或经验依据，以及与 baseline 的可归因差异。",
        "范式创新": "重点检查是否提出新问题、新任务或新评测协议，是否值得建立 dataset/benchmark。",
        "应用创新": "重点检查真实场景约束、数据闭环、部署成本与用户价值，避免只是在标准集上换场景。",
        "系统创新": "重点检查端到端系统设计、资源/延迟/可靠性权衡、工程可复现性与真实负载。",
        "评测创新": "重点检查指标是否真正测量目标能力、是否揭示现有 benchmark 的盲区与偏差。",
    }.get(itype, "请判断该创新点属于结构、方法、范式、应用、系统还是评测创新，并说明理由。")
    base = (
        "【创新点任务】\n"
        "大类: " + idea.get("category", "未分类") + "\n"
        "研究领域: " + idea.get("field", "未分类") + "\n"
        "创新类型: " + itype + "\n"
        "二级机制: " + (idea.get("mechanism_type") or "未指定") + "\n"
        "目标证据: " + (idea.get("evidence_type") or "未指定") + "\n"
        "主要风险: " + (idea.get("risk_type") or "未指定") + "\n"
        "类型要求: " + type_guide + "\n"
        "标题: " + idea.get("title", "") + "\n"
        "描述: " + idea.get("desc", "") + "\n"
        "应用场景: " + idea.get("domain", "未填写") + "\n"
        "知识库: " + str(kb_root()) + "\n"
        "\n本地预筛（仅用于发现问题，不是评审结论）:\n"
        "- 当前阶段: " + assessment["stage"] + "\n"
        "- 本地建议动作: " + assessment["decision"] + "\n"
        "- 综合分: " + str(assessment["total"]) + "\n"
        "- 维度分: " + " / ".join(
            key + " " + str(value)
            for key, value in assessment["scores"].items()) + "\n"
        "- 自动判断更像: " + assessment["recommended_type"] + "\n"
        "- 已识别线索: "
        + ("；".join(assessment["strengths"]) or "不足") + "\n"
        "- 主要缺口:\n"
        + "\n".join("- " + gap for gap in assessment["gaps"])
        + "\n- 下一步检查:\n"
        + "\n".join("- " + action for action in assessment["next_actions"])
        + "\n- 证据约束: 本地分数只检查表述结构；论文、竞争强度和创新性判断"
          "必须真实检索，不得编造引用或把预筛当成结论。\n"
    )
    if mode == "review":
        return base + (
            "\n请调用 supervisor-agent Stage 1 与 ccf-idea-reviewer，进行选题体检：\n"
            "1) 先判断创新类型标注是否准确；如不准确，给出更合适的类型和理由；\n"
            "2) 按该领域要求检查价值、新颖性、机制完整性、证据充分性、可行性与风险；\n"
            "3) 找出最致命的 3 个问题，并给出可修复路径；\n"
            "4) 给出 Accept / Accept with Revisions / Reject 的建议与理由；\n"
            "5) 给出下一步最小验证实验。"
        )
    return base + (
        "\n请调用 ccf-idea-optimizer / ccf-idea-reviewer / ccf-experiment-designer，完成创新点应用评估：\n"
        "1) 先判断该创新属于结构/方法/范式/应用/系统/评测中的哪一类，检查类型标注是否合理；\n"
        "2) 按类型要求评估机制、比较对象与最小区分实验；\n"
        "3) 给出 3 个具体应用场景，说明为什么适配、现有痛点与预期收益；\n"
        "4) 每个场景给出 baseline、数据集、指标、消融和最小可行实验；\n"
        "5) 分析与知识库现有工作的差异、可迁移模块和潜在风险；\n"
        "6) 生成一段可写入论文 Introduction 的创新点表述（避免夸大）。"
    )


def idea_review_prompt(idea, depth="完整选题体检"):
    assessment = evaluate_idea_local(idea)
    focus = {
        "快速预筛": (
            "用 10 分钟 desk-reject 视角完成快速预筛：\n"
            "1) 先用一句话复述问题、机制和预期差异；\n"
            "2) 找出最可能致命的 3 个问题；\n"
            "3) 判断是否值得投入一个最小验证实验；\n"
            "4) 输出继续 / 缩小范围 / 换机制 / 停止，并说明决定性证据。"
        ),
        "最小实验设计": (
            "只关注最小可证伪实验：\n"
            "1) 给出一个可证伪主假设和最多两个替代假设；\n"
            "2) 指定数据、划分、最强 baseline、主指标、失败指标；\n"
            "3) 给出必须做的消融、负结果判据、预算与停止条件；\n"
            "4) 估计一周或两周内能否得到可解释结果；\n"
            "5) 输出实验表格和逐步执行清单。"
        ),
        "完整选题体检": (
            "执行完整选题体检：\n"
            "1) 核验创新类型与二级机制是否匹配；\n"
            "2) 检查问题价值、已有证据、近邻工作和真实新颖性；\n"
            "3) 检查机制是否完整、可归因、可被负结果否定；\n"
            "4) 检查 baseline、数据、指标、消融、统计显著性和失败切片；\n"
            "5) 检查可行性、工程成本、伦理与部署风险；\n"
            "6) 给出三个最致命问题及修复路径；\n"
            "7) 输出继续 / 缩小范围 / 换机制 / 重做问题 / 停止。"
        ),
    }.get(depth, "执行完整选题体检。")
    return (
        "【独立选题体检任务】\n"
        "标题: " + idea.get("title", "") + "\n"
        "描述: " + idea.get("desc", "") + "\n"
        "目录: " + (idea.get("category") or "未分类")
        + " / " + (idea.get("field") or "未分类") + "\n"
        "一级类型: " + (idea.get("type") or "方法创新") + "\n"
        "二级机制: " + (idea.get("mechanism_type") or "未指定") + "\n"
        "目标证据: " + (idea.get("evidence_type") or "未指定") + "\n"
        "主要风险: " + (idea.get("risk_type") or "未指定") + "\n"
        "应用场景: " + (idea.get("domain") or "未填写") + "\n\n"
        "本地预筛（只用于定位问题，不是评审结论）:\n"
        "- 阶段: " + assessment["stage"] + "\n"
        "- 综合分: " + str(assessment["total"]) + "\n"
        "- 建议动作: " + assessment["decision"] + "\n"
        "- 分数: " + " / ".join(
            key + " " + str(value)
            for key, value in assessment["scores"].items()) + "\n"
        "- 主要缺口:\n"
        + "\n".join("- " + gap for gap in assessment["gaps"])
        + "\n\n" + focus + "\n\n"
        "请调用 ccf-idea-reviewer、ccf-idea-optimizer 与 ccf-experiment-designer。"
        "所有工作引用必须真实可核验，无法验证的判断明确标为假设。"
    )


def infer_innovation_type(title, desc):
    text = (title + " " + desc).lower()
    if any(k in text for k in ("新任务", "新问题", "新范式", "benchmark", "评测体系", "定义")):
        return "范式创新"
    if any(k in text for k in ("评测", "指标", "evaluation", "metric")):
        return "评测创新"
    if any(k in text for k in ("系统", "平台", "部署", "工程", "system", "deploy")):
        return "系统创新"
    if any(k in text for k in ("应用", "场景", "落地", "application")):
        return "应用创新"
    if any(k in text for k in ("架构", "模块", "连接", "结构", "网络设计", "architecture")):
        return "结构创新"
    return "方法创新"


def load_direction_library():
    try:
        data = json.loads(DIRECTION_LIBRARY.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    mem = load_research_memory()
    for cat, subs in mem.get("custom_directions", {}).items():
        if cat not in data:
            data[cat] = {"venues": [], "subs": []}
        existing = {s.get("name") for s in data[cat].get("subs", [])}
        for sub in subs:
            if sub.get("name") and sub["name"] not in existing:
                data[cat].setdefault("subs", []).append(sub)
                existing.add(sub["name"])
    for path in (RESEARCH_EXTENDED, RESEARCH_COMPREHENSIVE):
        try:
            ext = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            ext = {}
        for cat, entry in ext.get("categories", {}).items():
            if cat not in data:
                data[cat] = {"venues": [], "subs": []}
            for venue in entry.get("venues", []):
                if venue not in data[cat].setdefault("venues", []):
                    data[cat]["venues"].append(venue)
            existing = {s.get("name") for s in data[cat].get("subs", [])}
            for sub in entry.get("subs", []):
                if sub.get("name") and sub["name"] not in existing:
                    data[cat].setdefault("subs", []).append(sub)
                    existing.add(sub["name"])
    return data


def load_research_taxonomy():
    try:
        extra = json.loads(RESEARCH_TAXONOMY.read_text(encoding="utf-8"))
    except Exception:
        extra = {}
    try:
        ext = json.loads(RESEARCH_EXTENDED.read_text(encoding="utf-8"))
    except Exception:
        ext = {}
    try:
        comp = json.loads(RESEARCH_COMPREHENSIVE.read_text(encoding="utf-8"))
    except Exception:
        comp = {}
    def merged(base, more):
        out = list(base)
        names = {x.get("name") for x in out}
        for item in more:
            if item.get("name") and item["name"] not in names:
                out.append(item)
                names.add(item["name"])
        return out
    return {
        "categories": load_direction_library(),
        "scenarios": merged(merged(extra.get("scenarios", []), ext.get("scenarios", [])),
                            comp.get("scenarios", [])),
        "methods": merged(merged(extra.get("methods", []), ext.get("methods", [])),
                          comp.get("methods", [])),
        "tasks": merged(merged(extra.get("tasks", []), ext.get("tasks", [])),
                        comp.get("tasks", [])),
        "modalities": merged(merged(extra.get("modalities", []), ext.get("modalities", [])),
                             comp.get("modalities", [])),
        "sources": merged(merged(extra.get("sources", []), ext.get("sources", [])),
                          comp.get("sources", [])),
    }


def load_research_relations():
    try:
        data = json.loads(RESEARCH_RELATIONS.read_text(encoding="utf-8"))
    except Exception:
        data = {"profiles": {}, "category_profiles": {}}
    try:
        ext = json.loads(RESEARCH_EXTENDED.read_text(encoding="utf-8"))
    except Exception:
        ext = {}
    try:
        comp = json.loads(RESEARCH_COMPREHENSIVE.read_text(encoding="utf-8"))
    except Exception:
        comp = {}
    rel = ext.get("relations", {})
    for cat, mapping in rel.get("category_profiles", {}).items():
        data.setdefault("category_profiles", {}).setdefault(cat, {}).update(mapping)
    for key, profile in rel.get("profiles", {}).items():
        data.setdefault("profiles", {})[key] = profile
    for cat, mapping in comp.get("category_profiles", {}).items():
        data.setdefault("category_profiles", {}).setdefault(cat, {}).update(mapping)
    for key, profile in comp.get("profiles", {}).items():
        data.setdefault("profiles", {})[key] = profile
    data.setdefault("category_default_profiles", {}).update(
        comp.get("category_default_profiles", {}))
    data.setdefault("category_related", {}).update(
        comp.get("category_related", {}))
    data.setdefault("thin_categories", []).extend(
        name for name in comp.get("thin_categories", [])
        if name not in data.get("thin_categories", []))
    return data


def field_profile(category, field, relations):
    explicit = (relations.get("category_profiles", {})
                .get(category, {})
                .get(field))
    if explicit:
        return explicit
    return (relations.get("category_default_profiles", {})
            .get(category, "ml_method"))


def evaluate_combo(profile_key, selections, relations):
    profile = relations.get("profiles", {}).get(profile_key, {})
    importance = profile.get("importance", {})
    dims = (("scenario", "scenarios", "场景"),
            ("method", "methods", "方法"),
            ("task", "tasks", "任务"),
            ("modality", "modalities", "模态"))
    total, weight_sum, weak = 0.0, 0.0, []
    for key, profile_key_name, label in dims:
        weight = float(importance.get(key, 0.5))
        strong = set(profile.get(profile_key_name, []))
        names = selections.get(key, [])
        if names:
            strengths = []
            for name in names:
                if name in strong:
                    strengths.append(2.0)
                else:
                    strengths.append(0.5)
                    weak.append(label + ": " + name)
            strength = max(strengths)
        else:
            strength = 1.0 if weight < 0.55 else 0.25
        total += weight * (strength / 2.0)
        weight_sum += weight
    score = round(100 * total / weight_sum) if weight_sum else 0
    strong_axes = [label for key, _pk, label in dims
                   if float(importance.get(key, 0)) >= 0.6]
    return {"score": score, "weak": weak,
            "profile": profile.get("label", profile_key),
            "importance": importance, "strong_axes": strong_axes}


def load_advisors():
    try:
        signature = (
            ADVISOR_DIRECTORY.stat().st_mtime_ns,
            GENERATED_ADVISORS.stat().st_mtime_ns,
        )
    except OSError:
        signature = (0, 0)
    with _ADVISOR_CACHE_LOCK:
        if _ADVISOR_CACHE["signature"] == signature:
            return _ADVISOR_CACHE["rows"]
    curated = []
    try:
        data = json.loads(ADVISOR_DIRECTORY.read_text(encoding="utf-8"))
        curated = data.get("advisors", [])
    except Exception:
        pass
    generated = []
    try:
        data = json.loads(GENERATED_ADVISORS.read_text(encoding="utf-8"))
        generated = data.get("advisors", [])
    except Exception:
        pass
    merged, names = [], set()
    for advisor in curated + generated:
        name = (advisor.get("name") or "").strip().lower()
        if not name or name in names:
            continue
        names.add(name)
        merged.append(advisor)
    with _ADVISOR_CACHE_LOCK:
        _ADVISOR_CACHE["signature"] = signature
        _ADVISOR_CACHE["rows"] = merged
    return merged


def load_institutions_cn():
    try:
        data = json.loads(INSTITUTIONS_CN.read_text(encoding="utf-8"))
        return data.get("institutions", [])
    except Exception:
        return []


def load_institution_localization():
    try:
        signature = INSTITUTION_LOCALIZATION.stat().st_mtime_ns
    except OSError:
        signature = 0
    with _LOCALIZATION_CACHE_LOCK:
        if _LOCALIZATION_CACHE["signature"] == signature:
            return _LOCALIZATION_CACHE["data"]
    try:
        data = json.loads(INSTITUTION_LOCALIZATION.read_text(encoding="utf-8"))
    except Exception:
        data = {"institutions": {}, "provinces": {}}
    with _LOCALIZATION_CACHE_LOCK:
        _LOCALIZATION_CACHE["signature"] = signature
        _LOCALIZATION_CACHE["data"] = data
    return data


def institution_zh(name):
    name = (name or "").strip()
    if not name:
        return "未知机构"
    entry = load_institution_localization().get("institutions", {}).get(name, {})
    return entry.get("zh") or name


def province_zh(name):
    name = (name or "").strip()
    if not name:
        return ""
    return load_institution_localization().get("provinces", {}).get(name, name)


def run_advisor_update(institutions=400, authors=30, progress=None):
    _emit(progress, "更新全国院校索引", 10, "OpenAlex CN education")
    cmd = [_pythonw_exe(), "-X", "utf8", str(HERE / "build_advisor_index.py"),
           "--institutions", str(institutions), "--authors", str(authors),
           "--min-works", "5", "--workers", "8"]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    _emit(progress, "抓取研究型院校作者", 30,
          "目标 " + str(institutions) + " 所院校，每所最多 " + str(authors) + " 位")
    proc = subprocess.run(cmd, capture_output=True, timeout=60 * 45,
                          env=env, **_hidden_kwargs())
    if proc.returncode != 0:
        raise RuntimeError(_decode_bytes(proc.stderr)[-500:])
    _emit(progress, "写入导师索引", 90, "")
    try:
        gen = json.loads(GENERATED_ADVISORS.read_text(encoding="utf-8"))
        inst = json.loads(INSTITUTIONS_CN.read_text(encoding="utf-8"))
    except Exception:
        gen, inst = {}, {}
    result = {"institutions": inst.get("count", 0),
              "advisors": gen.get("advisor_count", 0),
              "selected_institutions": gen.get("institution_count", 0)}
    _emit(progress, "导师索引更新完成", 100,
          str(result["advisors"]) + " 位 / " + str(result["institutions"]) + " 所院校")
    return result


def _institution_urls():
    out = {s.get("name"): s.get("url", "")
           for s in load_research_taxonomy()["sources"]}
    for institution in load_institutions_cn():
        name = institution.get("name", "")
        homepage = institution.get("homepage", "")
        if name and homepage:
            out[name] = homepage
    return out


def _recommend_tokens(category, field, scenario, methods, tasks, modalities):
    tokens = [category, field, scenario] + list(methods) + list(tasks) + list(modalities)
    out, seen = [], set()
    for token in tokens:
        token = (token or "").strip()
        if token and token.lower() not in seen:
            seen.add(token.lower())
            out.append(token)
    return out


def recommend_advisors(category, field, scenario, methods, tasks, modalities,
                       top=8, province=None):
    advisors = load_advisors()
    related = load_research_relations()
    related_links = related.get("category_related", {})
    thin_category = category in set(related.get("thin_categories", []))
    related_categories = set(related_links.get(category, []))
    sources = {s.get("name"): s for s in load_research_taxonomy()["sources"]}
    tokens = _recommend_tokens(category, field, scenario, methods, tasks, modalities)
    results = []
    for advisor in advisors:
        if province and province != "全部省份":
            if not advisor.get("province") or advisor.get("province") != province:
                continue
        score = 0
        reasons = []
        advisor_categories = set(advisor.get("categories", []))
        advisor_categories.add(advisor.get("category", ""))
        if category in advisor_categories and not thin_category:
            score += 20
            reasons.append("大类匹配")
        elif advisor_categories & related_categories:
            score += 18
            match = next(iter(sorted(advisor_categories & related_categories)))
            reasons.append("相近大类: " + match)
        fields = advisor.get("fields", [])
        if field in fields:
            score += 35
            reasons.append("领域匹配")
        elif any(field and (field in f or f in field) for f in fields):
            score += 18
            reasons.append("领域相近")
        hay = " ".join(fields + advisor.get("keywords", [])).lower()
        hits = 0
        for token in tokens:
            low = token.lower()
            if low and low in hay:
                score += 4
                hits += 1
                if len(reasons) < 5:
                    reasons.append(token)
        source = sources.get(advisor.get("institution"), {})
        area_hay = source.get("areas", "").lower()
        if any(token.lower() in area_hay for token in tokens if token):
            score += 6
            reasons.append("机构方向匹配")
        if score >= 18:
            results.append({"advisor": advisor, "score": min(99, score),
                            "reasons": reasons[:6]})
    results.sort(key=lambda x: (-x["score"], x["advisor"].get("name", "")))
    return results[:top]


def recommend_institutions(category, field, scenario, methods, tasks, modalities,
                           top=6, province=None):
    advisors = recommend_advisors(category, field, scenario, methods, tasks,
                                  modalities, top=100, province=province)
    sources = load_research_taxonomy()["sources"]
    by = {}
    for item in advisors:
        inst = item["advisor"].get("institution", "")
        if not inst:
            continue
        entry = by.setdefault(inst, {"institution": inst, "best": 0,
                                     "scores": [], "names": [], "fields": []})
        entry["best"] = max(entry["best"], item["score"])
        entry["scores"].append(item["score"])
        entry["names"].append(item["advisor"].get("name", ""))
        entry["fields"].extend(item["advisor"].get("fields", []))
    tokens = _recommend_tokens(category, field, scenario, methods, tasks, modalities)
    rows = []
    source_map = {s.get("name"): s for s in sources}
    cn_institutions = load_institutions_cn()
    candidates = []
    for inst in cn_institutions:
        if province and province != "全部省份" and inst.get("region") != province:
            continue
        candidates.append({"name": inst.get("name", ""), "url": inst.get("homepage", ""),
                           "areas": " ".join(inst.get("topics", [])),
                           "province": inst.get("region", ""), "city": inst.get("city", "")})
    known = {c["name"] for c in candidates}
    for source in sources:
        if source.get("name") not in known:
            if province and province != "全部省份":
                continue
            candidates.append({"name": source.get("name", ""), "url": source.get("url", ""),
                               "areas": source.get("areas", ""),
                               "province": "", "city": ""})
    for candidate in candidates:
        name = candidate["name"]
        entry = by.get(name, {"best": 0, "scores": [], "names": [], "fields": []})
        area_hay = candidate.get("areas", "").lower()
        hits = sum(1 for token in tokens if token and token.lower() in area_hay)
        score = min(99, entry["best"] + min(12, len(entry["scores"]) * 3) + hits * 2)
        if score >= 18:
            areas_zh = []
            for field_name in entry.get("fields", []):
                if field_name and field_name not in areas_zh:
                    areas_zh.append(field_name)
            institution_url = candidate.get("url", "")
            if not institution_url:
                institution_url = (
                    "https://www.bing.com/search?q="
                    + quote_plus(institution_zh(name) + " 官网")
                )
            rows.append({"institution": name,
                         "institution_zh": institution_zh(name),
                         "score": score,
                         "best_advisors": entry["names"][:3],
                         "url": institution_url,
                         "areas": candidate.get("areas", ""),
                         "areas_zh": "、".join(areas_zh[:6]),
                         "province": candidate.get("province", ""),
                         "province_zh": province_zh(candidate.get("province", "")),
                         "city": candidate.get("city", "")})
    rows.sort(key=lambda x: (-x["score"], x["institution"]))
    return rows[:top]


def load_venue_rules():
    try:
        return json.loads(VENUE_RULES.read_text(encoding="utf-8")).get("rules", [])
    except Exception:
        return []


def venue_link(name, venue_type=""):
    try:
        links = json.loads(VENUE_LINKS.read_text(encoding="utf-8")).get("links", {})
    except Exception:
        links = {}
    configured = links.get(name, {})
    if configured.get("url"):
        return configured["url"], configured.get(
            "label", ("官方主页" if venue_type else "官方页面"))
    query = quote_plus(name)
    kind = "会议" if venue_type == "会议" else "期刊/会议"
    return (f"https://dblp.org/search?q={query}",
            f"{name}（DBLP {kind}检索）")


def load_direction_aliases():
    try:
        return json.loads(DIRECTION_ALIASES.read_text(encoding="utf-8")).get("aliases", [])
    except Exception:
        return []


def _alias_hit(term, low):
    term = (term or "").strip().lower()
    if not term:
        return False
    if all(ord(ch) < 128 for ch in term) and len(term) <= 3:
        return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", low) is not None
    return term in low


def recommend_venues(category, field, scenario, methods, tasks, modalities,
                     top=8):
    text = " ".join([category or "", field or "", scenario or ""]
                     + list(methods) + list(tasks) + list(modalities)).lower()
    venues = {}
    library = load_direction_library()
    for name in library.get(category, {}).get("venues", []):
        venues[name] = {"name": name, "type": "", "score": 1,
                        "reasons": ["领域主 venue"]}
    for rule in load_venue_rules():
        matched = [m for m in rule.get("match", []) if m.lower() in text]
        if not matched:
            continue
        priority = max(0, int(rule.get("priority", 0)))
        for item in rule.get("venues", []):
            name = item.get("name", "")
            if not name:
                continue
            entry = venues.setdefault(name, {"name": name, "type": item.get("type", ""),
                                              "score": 0, "reasons": []})
            entry["score"] += 2 + min(3, len(matched)) + priority * 3
            entry["type"] = entry.get("type") or item.get("type", "")
            reason = item.get("reason", "")
            if reason and reason not in entry["reasons"]:
                entry["reasons"].append(reason)
    rows = sorted(venues.values(), key=lambda x: (-x["score"], x["name"]))
    for row in rows:
        url, label = venue_link(row["name"], row.get("type", ""))
        row["url"] = url
        row["link_label"] = label
    return rows[:top]


def infer_category_field(text):
    # 统一成字符串：函数后半段有多处直接对 text 做 in / 拼接运算，
    # 传入 None 会抛 "argument of type 'NoneType' is not iterable"。
    # 这些入参来自界面输入框，理论上不该是 None，但防御一下成本很低。
    text = text if isinstance(text, str) else ("" if text is None else str(text))
    taxonomy = load_research_taxonomy()
    low = text.lower()
    exact = []
    for cat, entry in taxonomy["categories"].items():
        for sub in entry.get("subs", []):
            name = (sub.get("name") or "").strip()
            if name and name.lower() in low:
                exact.append((len(name), cat, name))
    if exact:
        _length, cat, name = max(exact, key=lambda row: row[0])
        return cat, name, min(99, 82 + _length * 2)
    best_alias, best_len = None, 0
    for entry in load_direction_aliases():
        for term in entry.get("terms", []):
            if _alias_hit(term, low) and len(term) > best_len:
                best_alias, best_len = entry, len(term)
    if best_alias:
        return (best_alias.get("category", ""), best_alias.get("field", ""),
                min(99, 80 + best_len * 2))
    translated = [t.lower() for t in _translate_direction(text or "")]
    best_score, best_cat, best_field = 0, "人工智能", "多模态学习"
    for cat, entry in taxonomy["categories"].items():
        cat_bonus = 3 if cat.lower() in low else 0
        for sub in entry.get("subs", []):
            score = cat_bonus
            name = sub.get("name", "")
            if name and name in text:
                score += 12
            for alias in sub.get("aliases", []):
                if alias and alias.lower() in low:
                    score += 15
            keywords = [k.lower() for k in sub.get("keywords", [])]
            for kw in keywords:
                if kw and kw in low:
                    score += 5
            for token in translated:
                if token and any(token in kw for kw in keywords):
                    score += 2
            if score > best_score:
                best_score, best_cat, best_field = score, cat, name
    if best_score == 0:
        return "", "", 0
    confidence = min(99, best_score * 5)
    return best_cat, best_field, confidence


def taxonomy_prompt(category, field, field_entry, venues, scenario,
                    methods, tasks, modalities, sources, relation=None):
    keywords = ", ".join(field_entry.get("keywords", []))
    method_text = ", ".join(methods) if methods else "待定（请给出候选方法对比）"
    task_text = ", ".join(tasks) if tasks else "待定（请给出候选任务对比）"
    modality_text = ", ".join(modalities) if modalities else "待定（请根据场景选择）"
    source_text = ", ".join(s["name"] for s in sources)
    queries = "\n".join("- " + q for q in load_config().get("queries", []))
    relation_text = ""
    if relation:
        relation_text = (
            "关系画像: " + relation.get("profile", "未判定") + "\n"
            "组合相关度: " + str(relation.get("score", 0)) + "%\n"
            "强相关轴: " + (" / ".join(relation.get("strong_axes", [])) or "无") + "\n"
            "弱相关/探索项: " + (" / ".join(relation.get("weak", [])) or "无") + "\n"
        )
    return (
        "【多维科研方向调研任务】\n"
        "大类: " + category + "\n"
        "研究领域: " + field + "\n"
        "领域关键词: " + keywords + "\n"
        "应用场景: " + (scenario or "通用") + "\n"
        "候选方法: " + method_text + "\n"
        "候选任务: " + task_text + "\n"
        "数据模态: " + modality_text + "\n"
        "目标会议/期刊: " + (", ".join(venues) if venues else "领域主流 venue") + "\n"
        "我的研究背景: RGB-T 多模态目标检测、跨模态融合、频域/Mamba 方法\n"
        "知识库: " + str(kb_root()) + "\n"
        "现有检索词:\n" + queries + "\n"
        "参考方向体系: " + source_text + "\n\n"
        + relation_text + "\n"
        "请调用 deep-research / nature-academic-search / ccf-literature-searcher / "
        "ccf-literature-monitor / supervisor-agent / ccf-idea-optimizer / "
        "ccf-idea-reviewer / ccf-experiment-designer，完成：\n"
        "1) 近 3 年进展：按领域、场景、任务、方法四轴梳理，并给出可核验引用；\n"
        "2) 研究地图：列出“方法 × 场景 × 任务 × 模态”的机会矩阵，标出拥挤区与空白区；\n"
        "3) 关键瓶颈：数据、评测、部署、鲁棒性、可解释性、伦理与安全；\n"
        "4) 5 个可执行方向：每个给出新颖性、价值、可行性、风险评分及 4 周最小验证；\n"
        "5) 2-3 个创新点：机制、与现有工作差异、失败模式；\n"
        "6) 实验设计：数据集、baseline、指标、消融、算力预算；\n"
        "7) 投稿定位：目标 venue 与匹配理由；\n"
        "8) 与知识库现有论文的重叠、空白和可迁移模块；\n"
        "9) 输出 Markdown 报告 + 方向矩阵图（Mermaid/表格）+ 执行计划。\n"
        "注意：弱相关/探索项只能作为探索性组合，不得当作核心动机；"
        "若相关度低于 60%，先说明该组合是否成立，再决定是否继续。\n"
        "保存到 知识库/分类总结/方向调研-" + category + "-" + field + "-"
        + datetime.date.today().isoformat() + ".md，只追加、不改旧条目。"
    )


def add_custom_direction(category, name, keywords):
    mem = load_research_memory()
    custom = mem.setdefault("custom_directions", {})
    custom.setdefault(category, []).append({"name": name, "keywords": keywords})
    save_research_memory(mem)


def direction_library_prompt(category, name, entry, venues):
    keywords = ", ".join(entry.get("keywords", []))
    venue_text = ", ".join(venues) if venues else "领域内主流会议/期刊"
    queries = "\n".join("- " + q for q in load_config().get("queries", []))
    return (
        "【科研方向调研任务】\n"
        "大类: " + category + "\n"
        "小类: " + name + "\n"
        "关键词: " + keywords + "\n"
        "目标会议/期刊: " + venue_text + "\n"
        "我的研究背景: RGB-T 多模态目标检测、跨模态融合与频域/Mamba 方法\n"
        "知识库: " + str(kb_root()) + "\n"
        "现有检索词:\n" + queries + "\n\n"
        "请调用 deep-research / nature-academic-search / ccf-literature-searcher / "
        "ccf-literature-monitor / supervisor-agent / ccf-idea-optimizer / ccf-idea-reviewer / "
        "ccf-experiment-designer，完成一份可执行的方向调研：\n"
        "1) 近 3 年关键进展：按问题、方法、数据、评测组织，逐条给出可核验引用；\n"
        "2) MECE 研究版图：列出主要技术路线及代表工作；\n"
        "3) 瓶颈与开放问题：说明证据与仍未解决的矛盾；\n"
        "4) 5 个可执行研究方向：按新颖性、价值、可行性、风险评分，并给出与现有知识库的关系；\n"
        "5) 2-3 个创新点草案：机制、差异化、最小验证实验；\n"
        "6) 实验设计：数据集、baseline、指标、消融、算力预算；\n"
        "7) 投稿定位：目标会议/期刊与匹配理由；\n"
        "8) 输出一份 Markdown 报告 + 方向地图（Mermaid 或表格） + 4 周执行计划。\n"
        "保存到 知识库/分类总结/方向调研-" + category + "-" + name + "-"
        + datetime.date.today().isoformat() + ".md，只追加、不改旧条目。"
    )


def recent_research_outputs(limit=6):
    kb = kb_root()
    dirs = [EXPORT_DIR, EXPORT_DIR / "prompts", kb / "分类总结"]
    items, seen = [], set()
    for folder in dirs:
        if not folder.exists():
            continue
        for p in folder.glob("*.md"):
            try:
                mt = p.stat().st_mtime
            except Exception:
                continue
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            name = p.name
            if name.startswith("科研知识总览"):
                kind = "知识总览"
            elif name.startswith("方向拓展"):
                kind = "方向拓展"
            elif name.startswith("创新点应用"):
                kind = "创新点应用"
            elif name.startswith("选题体检"):
                kind = "选题体检"
            elif name.startswith("知识库体检"):
                kind = "知识库体检"
            elif name.startswith("周报"):
                kind = "周报"
            elif p.parent.name == "分类总结":
                kind = "分类总结"
            else:
                kind = "科研文件"
            items.append({"kind": kind, "title": p.stem, "path": str(p),
                          "mtime": mt,
                          "time": datetime.datetime.fromtimestamp(mt).strftime("%m-%d %H:%M")})
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]


class W:
    CLOCK_FORMATS = (
        ("%m月%d日 %H:%M", True),
        ("%m月%d日 %H:%M:%S", True),
        ("%Y-%m-%d %H:%M", True),
        ("%Y-%m-%d %H:%M:%S", True),
        ("%H:%M", False),
        ("%H:%M:%S", False),
    )

    def __init__(self, root):
        self.root = root
        self.scanning = False
        self.lock_sock = None
        self.settings = load_settings()
        self.pinned = bool(self.settings.get("pinned", False))
        self.digest_actions = []
        self.log_actions = []
        self.cmd_until = datetime.datetime.now()
        self.cmd_history = list(self.settings.get("cmd_history", []))[-30:]
        self.cmd_h_idx = None
        self._blink_on = False
        self._snap_q = queue.Queue()
        self._scan_q = queue.Queue()
        self._report_q = queue.Queue()
        self._progress_q = queue.Queue()
        self._progress_job = None
        self._tool_running = False
        self.clock_i = int(self.settings.get("clock_fmt", 0)) % len(self.CLOCK_FORMATS)
        self._single_instance()
        try:
            self.scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        except Exception:
            self.scale = 1.0

        root.overrideredirect(True)
        root.withdraw()
        root.attributes("-topmost", self.pinned)
        root.configure(bg=BG)
        self._build()
        self.root.after(60, self.refresh)
        self.root.after(60000, self._tick)
        self._blink_sys()
        self.root.after(20, self._show_boot)
        self.root.after(120, self._poll_queues)
        self._clock()

    def _single_instance(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", LOCK_PORT))
            s.listen(1)
            self.lock_sock = s
        except OSError:
            try:
                c = socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=2)
                c.close()
            except Exception:
                try:
                    with open(str(_DATA("last_error.log")), "a", encoding="utf-8") as fh:
                        fh.write(datetime.datetime.now().isoformat()
                                 + " 启动失败: 端口被占用且无法唤醒已有实例\n")
                except Exception:
                    pass
            sys.exit(0)
        threading.Thread(target=self._lock_server, daemon=True).start()

    def _lock_server(self):
        while True:
            try:
                conn, _ = self.lock_sock.accept()
                conn.close()
            except OSError:
                break
            try:
                self.root.after(0, self._flash_front)
            except tk.TclError:
                break

    def _flash_front(self):
        if getattr(self, "_boot_win", None) is not None:
            return
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(800, lambda: self.root.attributes("-topmost", self.pinned))
        except tk.TclError:
            self._reveal_main()

    def _build(self):
        root = self.root
        root.minsize(int(520 * getattr(self, "scale", 1.0)), 0)
        root.configure(bg=LINE)
        shell = tk.Frame(root, bg=BG)
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        self.secs = {}

        hdr = tk.Frame(shell, bg=CARD, height=44, cursor="fleur")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        try:
            self.icon_photo = tk.PhotoImage(file=str(ICON_PNG))
            title = tk.Label(hdr, image=self.icon_photo, text=" 知识库终端",
                             bg=CARD, fg=ACCENT, compound="left",
                             font=("Microsoft YaHei UI", 12, "bold"))
        except Exception:
            title = tk.Label(hdr, text="◆ 知识库终端", bg=CARD, fg=ACCENT,
                             font=("Microsoft YaHei UI", 12, "bold"))
        title.pack(side="left", padx=12)
        self.sys_lbl = tk.Label(hdr, text="● SYS.ON", bg=CARD, fg=OKC,
                                font=("Consolas", 8))
        self.new_lbl = tk.Label(hdr, text="", bg=CARD, fg=OKC,
                                font=("Consolas", 8, "bold"))
        self.time_lbl = tk.Label(hdr, text="", bg=CARD, fg=MUT, font=MONO,
                                 cursor="hand2")
        close = tk.Label(hdr, text="  ✕  ", bg=CARD, fg=MUT, font=FONT_S, cursor="hand2")
        min_btn = tk.Label(hdr, text="  —  ", bg=CARD, fg=MUT, font=FONT_S, cursor="hand2")
        close.pack(side="right")
        min_btn.pack(side="right")
        self.time_lbl.pack(side="right", padx=(0, 10))
        self.new_lbl.pack(side="right", padx=(0, 6))
        self.sys_lbl.pack(side="right", padx=(0, 8))
        close.bind("<Button-1>", lambda e: self._quit())
        min_btn.bind("<Button-1>", lambda e: self._minimize())
        self.time_lbl.bind("<Button-1>", self._cycle_clock)
        for wdg in (hdr, title):
            wdg.bind("<Button-1>", self._drag_start)
            wdg.bind("<B1-Motion>", self._drag_move)
            wdg.bind("<ButtonRelease-1>", lambda e: self._save_pos())
        accent_bar = tk.Frame(shell, bg=ACCENT, height=2)
        accent_bar.pack(fill="x")

        strip = tk.Frame(shell, bg=CARD)
        strip.pack(fill="x")
        tk.Label(strip, text=" SYS 550W v3.5 · KB ONLINE · UPLINK OK ",
                 bg=CARD, fg=MUT, font=("Consolas", 8)).pack(side="left")
        self.sync_lbl = tk.Label(strip, text="SYNC --:--:--", bg=CARD, fg=MUT,
                                 font=("Consolas", 8))
        self.sync_lbl.pack(side="right", padx=(0, 10))
        tk.Label(strip, text="量子链路正常", bg=CARD, fg=OKC,
                 font=("Consolas", 8)).pack(side="right", padx=(0, 12))

        stats = tk.Frame(shell, bg=BG)
        stats.pack(fill="x", padx=14, pady=(10, 0))
        self.stat_frames = {}
        names = [("pdf", "知识库 PDF"), ("seen", "已跟踪论文"),
                 ("queries", "检索词组"), ("task", "下次抓取")]
        for i, (key, label) in enumerate(names):
            f = tk.Frame(stats, bg=CARD, highlightbackground=LINE, highlightthickness=1)
            f.grid(row=i // 2, column=i % 2, sticky="nsew", padx=5, pady=5)
            tk.Label(f, text=label, bg=CARD, fg=MUT, font=FONT_XS).pack(anchor="w", padx=10, pady=(7, 0))
            v = tk.Label(f, text="—", bg=CARD, fg=ACCENT,
                         font=("Consolas", 13, "bold"), anchor="w")
            v.pack(fill="x", padx=10, pady=(0, 7))
            self.stat_frames[key] = v
        stats.grid_columnconfigure(0, weight=1)
        stats.grid_columnconfigure(1, weight=1)

        sec_cats = self._make_section(shell, "cats", "论文分类", "[ ARCHIVE / FILE SYSTEM ]", True)
        self.cat_holder = sec_cats["body"]
        self.cat_holder.grid_columnconfigure(0, weight=1)
        self.cat_holder.grid_columnconfigure(1, weight=1)

        sec_dig = self._make_section(shell, "digest", "最新速览", "[ INBOX / READY ]", False)
        self.digest = tk.Text(sec_dig["body"], height=7, wrap="word", bg=CARD, fg=TXT,
                              insertbackground=TXT, relief="flat",
                              highlightbackground=LINE, highlightthickness=1,
                              font=FONT_S, padx=12, pady=10, spacing1=2,
                              spacing3=2, state="disabled")
        self.digest.tag_config("paper", foreground=ACCENT,
                               font=("Microsoft YaHei UI", 10, "bold"))
        self.digest.tag_config("meta", foreground=MUT, font=FONT_XS)
        self.digest.tag_config("dim", foreground=MUT, font=FONT_XS)
        self.digest.bind("<Button-1>", self._digest_click)
        self.digest.bind("<MouseWheel>", lambda e: self._on_wheel(e, self.digest))
        self.digest.pack(fill="x", padx=12, pady=(0, 6))

        sec_log = self._make_section(shell, "log", "指令输出", "[ TERMINAL / RECENT ]", False)
        self.log = tk.Text(sec_log["body"], height=5, wrap="word", bg=CARD, fg=MUT,
                           relief="flat", highlightbackground=LINE, highlightthickness=1,
                           font=FONT_XS, padx=12, pady=8, spacing1=2,
                           spacing3=2, state="disabled")
        self.log.tag_config("meta", foreground=ACCENT, font=FONT_XS)
        self.log.tag_config("dim", foreground=MUT, font=FONT_XS)
        self.log.bind("<Button-1>", self._log_click)
        self.log.bind("<MouseWheel>", lambda e: self._on_wheel(e, self.log))
        self.log.pack(fill="x", padx=12, pady=(0, 6))

        sec_res = self._make_section(shell, "research", "科研工作台", "[ RESEARCH / IDEAS ]", False)
        res_grid = tk.Frame(sec_res["body"], bg=BG)
        res_grid.pack(fill="x", padx=10, pady=(0, 6))
        res_grid.grid_columnconfigure(0, weight=1)
        res_grid.grid_columnconfigure(1, weight=1)
        for i, (label, cmd) in enumerate((
                ("知识总览", self.run_research_overview),
                ("方向拓展", lambda: self.open_direction_dialog()),
                ("方向库", self.open_direction_library),
                ("导师推荐", self.open_advisor_dialog),
                ("期刊会议", self.open_venue_dialog),
                ("创新点库", self.open_ideas_dialog),
                ("选题体检", lambda: self.open_ideas_dialog("review")),
                ("覆盖审计", self.run_direction_audit))):
            b = self._btn(res_grid, label, cmd, accent=(i == 0))
            b.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=3)

        self.status = tk.StringVar(value="> 系统就绪 · 点击分区标题展开/收起 · 右键打开更多功能")
        self.status_lbl = tk.Label(shell, textvariable=self.status, bg=BG, fg=MUT,
                                   font=FONT_XS, anchor="w", wraplength=430,
                                   justify="left")
        self.status_lbl.pack(fill="x", padx=14, pady=(6, 2))
        self.status.trace_add("write", lambda *a: self._status_color())

        self.progress_frame = tk.Frame(shell, bg=BG)
        self.progress_lbl = tk.Label(self.progress_frame, text="", bg=BG, fg=ACCENT,
                                     font=FONT_XS, anchor="w", wraplength=520,
                                     justify="left")
        self.progress_lbl.pack(fill="x")
        track = tk.Frame(self.progress_frame, bg=LINE, height=8)
        track.pack(fill="x", pady=(3, 0))
        track.pack_propagate(False)
        self.progress_fill = tk.Frame(track, bg=ACCENT)
        self.progress_fill.place(x=0, y=0, relwidth=0, relheight=1)

        btns = tk.Frame(shell, bg=BG)
        self.btns_frame = btns
        btns.pack(fill="x", padx=14, pady=(4, 6))
        self.scan_btn = self._btn(btns, "立即抓取", self.start_scan, accent=True)
        self.scan_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._btn(btns, "新论文", lambda: self.open_dir("inbox")).pack(side="left", fill="x", expand=True, padx=4)
        self._btn(btns, "知识库", lambda: self.open_dir("kb")).pack(side="left", fill="x", expand=True, padx=4)
        self._btn(btns, "刷新", lambda: self.refresh(force=True)).pack(side="left", fill="x", expand=True, padx=(4, 0))

        cmd_row = tk.Frame(shell, bg=BG)
        cmd_row.pack(fill="x", padx=14, pady=(0, 6))
        self.cmd_entry = tk.Entry(cmd_row, bg=CARD, fg=TXT, insertbackground=TXT,
                                  relief="flat", highlightbackground=LINE,
                                  highlightthickness=1, font=FONT_S)
        self.cmd_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.cmd_entry.bind("<Return>", lambda e: self.send_command())
        self.cmd_entry.bind("<Control-Return>", lambda e: self.send_command())
        self.cmd_entry.bind("<Escape>", lambda e: self.cmd_entry.delete(0, "end"))
        self.cmd_entry.bind("<Up>", self._hist_prev)
        self.cmd_entry.bind("<Down>", self._hist_next)
        self.cmd_entry.bind("<FocusIn>", self._entry_focus_in)
        self.cmd_entry.bind("<FocusOut>", self._entry_focus_out)
        self._cmd_placeholder = "输入指令：下载10篇红外目标检测论文 / 搜索 mamba"
        self.cmd_entry.insert(0, self._cmd_placeholder)
        self.cmd_entry.config(fg=MUT)
        self._btn(cmd_row, "发送", self.send_command, accent=True).pack(side="left", padx=(6, 0))

        chips = tk.Frame(shell, bg=BG)
        chips.pack(fill="x", padx=14, pady=(0, 8))
        for text, cmd in (("检索词", "keywords"), ("帮助", "帮助"), ("统计", "统计"),
                          ("抓取", "抓取"), ("清空", "清空")):
            def go(t=cmd):
                if t == "keywords":
                    self.open_keywords()
                else:
                    self.send_command(t)
            tk.Button(chips, text=text, command=go,
                      bg=CARD, fg=MUT, activebackground=LINE, activeforeground=TXT,
                      relief="flat", bd=0, font=FONT_XS, cursor="hand2",
                      padx=10, pady=2).pack(side="left", padx=(0, 6))
        self.tools_btn = tk.Button(chips, text="工具 ▾", command=self._open_tools_menu,
                                   bg=CARD, fg=ACCENT, activebackground=LINE,
                                   activeforeground=TXT, relief="flat", bd=0,
                                   font=FONT_XS, cursor="hand2", padx=10, pady=2)
        self.tools_btn.pack(side="left", padx=(0, 6))

        self.menu = tk.Menu(root, tearoff=0, bg=CARD, fg=TXT,
                            activebackground=ACCENT, activeforeground="#0e1420", bd=0)
        self.menu.add_command(label="始终置顶（当前: 关）", command=self.toggle_pin)
        self.menu.add_separator()
        self.menu.add_command(label="打开新论文目录", command=lambda: self.open_dir("inbox"))
        self.menu.add_command(label="打开知识库目录", command=lambda: self.open_dir("kb"))
        self.menu.add_command(label="打开监控目录", command=lambda: self.open_dir("monitor"))
        self.menu.add_separator()
        self.menu.add_command(label="打开网页版（备用）", command=self.open_web)
        self.menu.add_separator()
        self.menu.add_command(label="检索词管理（关键词捕捉）", command=self.open_keywords)
        self.menu.add_command(label="指令帮助", command=lambda: self.send_command("帮助"))
        self.menu.add_command(label="开机自启（当前: " + ("开" if STARTUP_BAT.exists() else "关") + "）",
                              command=self._toggle_autostart)
        self.menu.add_separator()
        self.menu.add_command(label="智能下载（自然语言）", command=self.focus_smart_input)
        self.menu.add_command(label="查看迭代记忆", command=lambda: self.send_command("记忆"))
        self.menu.add_separator()
        research_menu = tk.Menu(self.menu, tearoff=0, bg=CARD, fg=TXT,
                                activebackground=ACCENT, activeforeground=BG, bd=0)
        research_menu.add_command(label="知识总览", command=self.run_research_overview)
        research_menu.add_command(label="方向拓展", command=lambda: self.open_direction_dialog())
        research_menu.add_command(label="方向库（大类/小类）", command=self.open_direction_library)
        research_menu.add_command(label="导师/院校推荐", command=self.open_advisor_dialog)
        research_menu.add_command(label="期刊/会议推荐", command=self.open_venue_dialog)
        research_menu.add_command(label="创新点库", command=self.open_ideas_dialog)
        research_menu.add_command(label="选题体检", command=lambda: self.open_ideas_dialog("review"))
        research_menu.add_command(label="计算机方向覆盖审计", command=self.run_direction_audit)
        self.menu.add_cascade(label="科研工作台", menu=research_menu)
        self.menu.add_separator()
        self.menu.add_command(label="抓取预演（不下载）", command=lambda: self.start_preview())
        self.menu.add_command(label="导出论文清单（Excel）", command=self.export_papers)
        self.menu.add_command(label="知识库体检", command=self.run_health)
        self.menu.add_command(label="生成周报", command=self.make_weekly)
        self.menu.add_separator()
        self.menu.add_command(label="折叠全部 / 展开全部", command=self._toggle_all_secs)
        self.menu.add_command(label="最小化到桌面", command=self._minimize)
        self.menu.add_command(label="退出知识库助手", command=self._quit)
        root.bind("<Button-3>", self._popup)
        foot = tk.Frame(shell, bg=BG)
        foot.pack(fill="x", pady=(0, 7))
        tk.Label(foot, text="# 550W ENGINE ONLINE · v3.5", bg=BG, fg=MUT,
                 font=("Consolas", 8)).pack(side="left", padx=(14, 0))
        tk.Label(foot, text="LINK ▸ 量子链路 · OK", bg=BG, fg=OKC,
                 font=("Consolas", 8)).pack(side="right", padx=(0, 14))

    def _make_section(self, parent, key, cn, en, default_open):
        state = bool(self.settings.get("secs", {}).get(key, default_open))
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="x")
        hdr = tk.Frame(wrap, bg=CARD, cursor="hand2",
                       highlightbackground=LINE, highlightthickness=1)
        hdr.pack(fill="x", padx=10, pady=(8, 5))
        arrow = tk.Label(hdr, text="▼ " if state else "▶ ", bg=CARD, fg=ACCENT,
                         font=("Consolas", 10, "bold"))
        arrow.pack(side="left", padx=(10, 2))
        tk.Label(hdr, text=cn, bg=CARD, fg=TXT,
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        tk.Label(hdr, text="  " + en, bg=CARD, fg=MUT,
                 font=("Consolas", 8)).pack(side="left", pady=(2, 0))
        hint = tk.Label(hdr, text="点击收起" if state else "点击展开", bg=CARD,
                        fg=MUT, font=("Microsoft YaHei UI", 8))
        hint.pack(side="right", padx=(0, 10))
        body = tk.Frame(wrap, bg=BG)
        if state:
            body.pack(fill="x")
        sec = {"key": key, "state": state, "body": body, "arrow": arrow,
               "hint": hint}
        self.secs[key] = sec
        for wdg in (hdr,) + tuple(hdr.winfo_children()):
            wdg.bind("<Button-1>", lambda e, k=key: self._toggle_sec(k))

        def _hov_in(_e, w=hdr):
            for x in (w,) + tuple(w.winfo_children()):
                x.config(bg="#0a3448")

        def _hov_out(_e, w=hdr):
            for x in (w,) + tuple(w.winfo_children()):
                x.config(bg=CARD)

        hdr.bind("<Enter>", _hov_in)
        hdr.bind("<Leave>", _hov_out)

        return {"wrap": wrap, "body": body}

    def _toggle_sec(self, key):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        sec = self.secs[key]
        self._set_sec_state(key, not sec["state"])
        secs = dict(self.settings.get("secs", {}))
        secs[key] = sec["state"]
        self.settings["secs"] = secs
        if key == "cats" and sec["state"]:
            self._render_categories(getattr(self, "_cat_data", None), force=True)
        self._save_settings_soon()
        self._keep_pos(x, y)

    def _blink_sys(self):
        try:
            self._blink_on = not self._blink_on
            dot = "●" if self._blink_on else "○"
            self.sys_lbl.config(text=dot + " SYS.ON")
        except tk.TclError:
            return
        self.root.after(900, self._blink_sys)

    def _restore_pos(self):
        pos = self.settings.get("pos")
        if isinstance(pos, dict):
            try:
                x = int(pos.get("x", 0))
                y = int(pos.get("y", 0))
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                w = self.root.winfo_width() or 430
                h = self.root.winfo_height() or 520
                x = max(0, min(x, sw - w - 20))
                y = max(0, min(y, sh - h - 20))
                self.root.geometry("+{}+{}".format(x, y))
                return
            except Exception:
                pass
        self._place_bottom_right()

    def _save_pos(self):
        try:
            self.settings["pos"] = {
                "x": self.root.winfo_x(),
                "y": self.root.winfo_y(),
            }
            self._save_settings_soon()
        except Exception:
            pass

    def _save_settings_soon(self):
        job = getattr(self, "_save_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        try:
            self._save_job = self.root.after(350, self._flush_settings)
        except tk.TclError:
            self._flush_settings()

    def _flush_settings(self):
        self._save_job = None
        try:
            save_settings(self.settings)
        except Exception:
            pass

    def _quit(self):
        try:
            self.settings["pos"] = {"x": self.root.winfo_x(),
                                    "y": self.root.winfo_y()}
        except Exception:
            pass
        self._flush_settings()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _set_sec_state(self, key, open_state):
        sec = self.secs[key]
        if sec["state"] == open_state:
            return
        if open_state:
            sec["body"].pack(fill="x")
            sec["arrow"].config(text="▼ ")
            sec["hint"].config(text="点击收起")
        else:
            sec["body"].pack_forget()
            sec["arrow"].config(text="▶ ")
            sec["hint"].config(text="点击展开")
        sec["state"] = open_state

    def _minimize(self):
        self._save_pos()
        try:
            self.root.withdraw()
        except tk.TclError:
            pass

    def _hist_prev(self, e=None):
        if not self.cmd_history:
            return "break"
        if self.cmd_h_idx is None:
            self.cmd_h_idx = len(self.cmd_history) - 1
        else:
            self.cmd_h_idx = max(0, self.cmd_h_idx - 1)
        self.cmd_entry.delete(0, "end")
        self.cmd_entry.insert(0, self.cmd_history[self.cmd_h_idx])
        return "break"

    def _hist_next(self, e=None):
        if self.cmd_h_idx is None:
            return "break"
        self.cmd_h_idx += 1
        if self.cmd_h_idx >= len(self.cmd_history):
            self.cmd_h_idx = None
            self.cmd_entry.delete(0, "end")
        else:
            self.cmd_entry.delete(0, "end")
            self.cmd_entry.insert(0, self.cmd_history[self.cmd_h_idx])
        return "break"

    def _entry_focus_in(self, e=None):
        if self.cmd_entry.get() == getattr(self, "_cmd_placeholder", ""):
            self.cmd_entry.delete(0, "end")
            self.cmd_entry.config(fg=TXT)

    def _entry_focus_out(self, e=None):
        if not self.cmd_entry.get().strip():
            self.cmd_entry.delete(0, "end")
            self.cmd_entry.insert(0, getattr(self, "_cmd_placeholder", ""))
            self.cmd_entry.config(fg=MUT)

    def _toggle_all_secs(self):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        want_open = not all(s["state"] for s in self.secs.values())
        for key in list(self.secs.keys()):
            self._set_sec_state(key, want_open)
        if want_open:
            self._render_categories(getattr(self, "_cat_data", None), force=True)
        self.settings["secs"] = {k: want_open for k in self.secs}
        self._save_settings_soon()
        self._keep_pos(x, y)

    def _on_wheel(self, e, wdg):
        try:
            delta = -1 * (e.delta // 120) if e.delta else (1 if e.num == 4 else -1)
            wdg.yview_scroll(delta, "units")
        except tk.TclError:
            pass
        return "break"

    def _status_color(self):
        try:
            v = self.status.get()
            if v.startswith("✔") or v.startswith("已") or "完成" in v or "正常" in v:
                c = OKC
            elif v.startswith("⚠"):
                c = WARN
            elif v.startswith("✘") or "失败" in v or "超时" in v or "异常" in v:
                c = ERR
            elif v.startswith("●") or "抓取" in v or "开始" in v or "转交" in v:
                c = ACCENT
            else:
                c = MUT
            self.status_lbl.config(fg=c)
        except tk.TclError:
            pass

    def _autostart_label(self):
        return "开机自启（当前: 开）" if STARTUP_BAT.exists() else "开机自启（当前: 关）"

    def _toggle_autostart(self):
        try:
            if STARTUP_BAT.exists():
                STARTUP_BAT.unlink()
                self.status.set("已关闭开机自启：下次开机不再自动启动")
            else:
                STARTUP_DIR.mkdir(parents=True, exist_ok=True)
                STARTUP_BAT.write_text(
                    '@echo off\r\nstart "" "' + self._runner() + '" "'
                    + str(HERE / "kb_widget.py") + '"\r\n',
                    encoding="ascii")
                self.status.set("已开启开机自启：登录后自动启动知识库助手")
        except Exception as exc:
            self.status.set("开机自启设置失败: " + str(exc))
        self._refresh_menu_labels()

    def _refresh_menu_labels(self):
        try:
            n = self.menu.index("end")
            for i in range(n):
                if self.menu.type(i) != "command":
                    continue
                lbl = self.menu.entrycget(i, "label")
                if str(lbl).startswith("始终置顶（当前:"):
                    self.menu.entryconfig(i, label="始终置顶（当前: 开）" if self.pinned else "始终置顶（当前: 关）")
                elif str(lbl).startswith("开机自启（当前:"):
                    self.menu.entryconfig(i, label=self._autostart_label())
        except tk.TclError:
            pass

    def _show_boot(self):
        try:
            b = tk.Toplevel(self.root)
            b.overrideredirect(True)
            b.configure(bg="#000000")
            try:
                b.attributes("-topmost", True)
            except tk.TclError:
                pass
            ww, wh = 360, 150
            sw, sh = b.winfo_screenwidth(), b.winfo_screenheight()
            b.geometry("%dx%d+%d+%d" % (ww, wh, (sw - ww) // 2, (sh - wh) // 2))
            tk.Label(b, text="550W", bg="black", fg=ACCENT,
                     font=("Consolas", 34, "bold")).pack(pady=(16, 0))
            tk.Label(b, text="KNOWLEDGE ARCHIVE TERMINAL · v3.5",
                     bg="black", fg=TXT, font=("Consolas", 9)).pack()
            self._boot_bar = tk.Label(b, text="", bg="black", fg=OKC,
                                      font=("Consolas", 11))
            self._boot_bar.pack(pady=(16, 0))
            tk.Label(b, text="CLICK / ANY KEY TO SKIP", bg="black", fg=MUT,
                     font=("Consolas", 8)).pack(pady=(6, 0))
            b.bind("<Key>", lambda e: self._boot_done())
            b.bind("<Button-1>", lambda e: self._boot_done())
            self._boot_win = b
            self._boot_i = 0
            self._boot_tick()
        except tk.TclError:
            pass

    def _boot_done(self):
        try:
            b = getattr(self, "_boot_win", None)
            if b and b.winfo_exists():
                b.destroy()
        except tk.TclError:
            pass
        self._boot_win = None
        self._reveal_main()

    def _boot_tick(self):
        try:
            if not getattr(self, "_boot_win", None) or not self._boot_win.winfo_exists():
                self._boot_done()
                return
            self._boot_i += 1
            n = min(20, self._boot_i * 2)
            self._boot_bar.config(text="LOADING " + "▓" * min(20, n))
            if self._boot_i >= 12:
                self._boot_done()
                return
            self._boot_win.after(50, self._boot_tick)
        except tk.TclError:
            self._boot_win = None
            self._reveal_main()

    def _reveal_main(self):
        if getattr(self, "_revealed", False):
            return
        self._revealed = True
        try:
            self.root.attributes("-alpha", 0.0)
            self.root.deiconify()
            self.root.update_idletasks()
            self._restore_pos()
            self.root.lift()
        except tk.TclError:
            pass
        self._fade_in()

    def _fade_in(self):
        self._fade_step = 0

        def step():
            try:
                self._fade_step += 1
                a = min(1.0, 0.1 + 0.9 * (self._fade_step / 5.0))
                self.root.attributes("-alpha", a)
            except tk.TclError:
                return
            if self._fade_step < 5:
                self.root.after(15, step)

        step()

    def _btn(self, parent, text, cmd, accent=False):
        color = ACCENT if accent else TXT
        return tk.Button(parent, text=text, command=cmd, bg=CARD, fg=color,
                         activebackground=LINE, activeforeground=TXT,
                         relief="flat", bd=0, font=FONT_S, cursor="hand2",
                         padx=8, pady=4)

    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry("+{}+{}".format(e.x_root - self._dx, e.y_root - self._dy))

    def _popup(self, e):
        self._refresh_menu_labels()
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _place_bottom_right(self):
        self.root.update_idletasks()
        w = self.root.winfo_width() or 430
        h = self.root.winfo_height() or 800
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry("+{}+{}".format(max(0, sw - w - 28), max(0, sh - h - 28)))

    def _keep_pos(self, x, y):
        def apply():
            try:
                w = self.root.winfo_width() or 430
                h = self.root.winfo_height() or 520
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                nx = max(0, min(int(x), sw - w - 20))
                ny = max(0, min(int(y), sh - h - 20))
                self.root.geometry("+{}+{}".format(nx, ny))
                self.settings["pos"] = {"x": nx, "y": ny}
                self._save_settings_soon()
            except tk.TclError:
                pass
        try:
            self.root.after_idle(apply)
        except tk.TclError:
            pass

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.root.attributes("-topmost", self.pinned)
        self.settings["pinned"] = self.pinned
        save_settings(self.settings)
        self.status.set("已切换：始终置顶" if self.pinned else "已切换：贴在桌面上（像壁纸挂件）")

    def _set_text(self, wdg, text):
        wdg.config(state="normal")
        wdg.delete("1.0", "end")
        wdg.insert("1.0", text)
        wdg.config(state="disabled")

    def _clock(self):
        try:
            now = datetime.datetime.now()
            fmt, with_wd = self.CLOCK_FORMATS[self.clock_i]
            text = now.strftime(fmt)
            if with_wd:
                weekdays = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
                text += " " + weekdays[now.weekday()]
            self.time_lbl.config(text=text)
        except tk.TclError:
            return
        self.root.after(1000, self._clock)

    def _cycle_clock(self, e=None):
        self.clock_i = (self.clock_i + 1) % len(self.CLOCK_FORMATS)
        self.settings["clock_fmt"] = self.clock_i
        save_settings(self.settings)
        self._clock()
        self.status.set("时间格式已切换（继续点击可再切换）")

    def _runner(self):
        return _pythonw_exe()

    def open_keywords(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("550W · 检索词管理")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.geometry("+%d+%d" % (self.root.winfo_x() + 40, self.root.winfo_y() + 50))
        tk.Label(dlg, text="◆ 检索词 / 抓取捕捉规则", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(dlg, text="抓取时按这些查询式在 arXiv 捕捉新论文。普通关键词会自动包装成 all:关键词；"
                           "也支持完整查询式（包含 all: 或 AND）。",
                 bg=BG, fg=MUT, font=FONT_XS, justify="left", wraplength=390).pack(anchor="w", padx=12)
        box = tk.Frame(dlg, bg=BG)
        box.pack(fill="both", expand=True, padx=12, pady=(8, 4))
        sb = tk.Scrollbar(box)
        lb = tk.Listbox(box, width=56, height=8, bg=CARD, fg=TXT,
                        selectbackground=LINE, selectforeground=ACCENT,
                        relief="flat", highlightbackground=LINE,
                        highlightthickness=1, font=FONT_S, yscrollcommand=sb.set)
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        tk.Label(dlg, text="新增关键词 / 完整查询式：", bg=BG, fg=MUT,
                 font=FONT_XS).pack(anchor="w", padx=12)
        e_row = tk.Frame(dlg, bg=BG)
        e_row.pack(fill="x", padx=12, pady=(2, 6))
        entry = tk.Entry(e_row, bg=CARD, fg=TXT, insertbackground=TXT,
                         relief="flat", highlightbackground=LINE,
                         highlightthickness=1, font=FONT_S)
        entry.pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(e_row, text="添加", command=lambda: self._kw_add(lb, entry, dlg),
                  bg=CARD, fg=ACCENT, activebackground=LINE, activeforeground=TXT,
                  relief="flat", bd=0, font=FONT_S, cursor="hand2", padx=10).pack(side="left", padx=(6, 0))
        entry.bind("<Return>", lambda _e: self._kw_add(lb, entry, dlg))
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=12, pady=(0, 4))
        tk.Button(btns, text="删除选中", command=lambda: self._kw_del(lb, dlg),
                  bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                  relief="flat", bd=0, font=FONT_S, cursor="hand2", padx=10).pack(side="left", padx=(0, 8))
        tk.Button(btns, text="立即抓取", command=lambda: (dlg.destroy(), self.start_scan()),
                  bg=CARD, fg=OKC, activebackground=LINE, activeforeground=TXT,
                  relief="flat", bd=0, font=FONT_S, cursor="hand2", padx=10).pack(side="left", padx=(0, 8))
        tk.Button(btns, text="关闭", command=dlg.destroy,
                  bg=CARD, fg=MUT, activebackground=LINE, activeforeground=TXT,
                  relief="flat", bd=0, font=FONT_S, cursor="hand2", padx=10).pack(side="left")
        stl = tk.Label(dlg, text="", bg=BG, fg=MUT, font=FONT_XS, anchor="w")
        stl.pack(fill="x", padx=12, pady=(0, 10))
        dlg.status_lbl = stl
        self._kw_refresh(lb, dlg)
        dlg.grab_set()

    def _kw_refresh(self, lb, dlg):
        lb.delete(0, "end")
        for q in load_config().get("queries", []):
            lb.insert("end", q)
        self._kw_stat(dlg, "共 " + str(lb.size()) + " 条检索词，抓取时逐条查询 arXiv。")

    def _kw_stat(self, dlg, msg):
        try:
            dlg.status_lbl.config(text=msg)
        except Exception:
            pass

    def _kw_add(self, lb, entry, dlg):
        kw = entry.get().strip()
        if not kw:
            self._kw_stat(dlg, "请输入关键词")
            return
        cfg = load_config()
        q = kw if ("all:" in kw or " AND " in kw.upper()) else "all:" + kw
        qs = cfg.setdefault("queries", [])
        if q in qs:
            self._kw_stat(dlg, "已存在: " + q)
            return
        qs.append(q)
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        self._kw_refresh(lb, dlg)
        entry.delete(0, "end")
        self._kw_stat(dlg, "已添加: " + q)

    def _kw_del(self, lb, dlg):
        sel = lb.curselection()
        if not sel:
            self._kw_stat(dlg, "请先选中要删除的检索词")
            return
        cfg = load_config()
        qs = cfg.get("queries", [])
        idx = sel[0]
        if 0 <= idx < len(qs):
            removed = qs.pop(idx)
            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            self._kw_refresh(lb, dlg)
            self._kw_stat(dlg, "已删除: " + removed)

    def _render_log(self, items=None):
        if int(self.log.cget("height")) != 5:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.log.config(height=5)
            self._keep_pos(x, y)
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log_actions = []
        if items is None:
            items = recent_files(6)
        if items:
            self.log.insert("end", "最近文件变动（点击打开）\n", ("meta",))
            for it in items:
                self.log_actions.append(("open_file", it["path"]))
                name = it["name"]
                if len(name) > 36:
                    name = name[:33] + "…"
                self.log.insert("end", it["date"] + " [" + it["cat"] + "] " + name + "\n",
                                ("act:%d" % (len(self.log_actions) - 1),))
        else:
            self.log.insert("end", "暂无文件变动", ("dim",))
        self.log.config(state="disabled")

    def _log_click(self, e):
        try:
            idx = self.log.index("@%d,%d" % (e.x, e.y))
            for t in self.log.tag_names(idx):
                if t.startswith("act:"):
                    i = int(t[4:])
                    kind, path = self.log_actions[i]
                    if kind == "open_file":
                        p = Path(path)
                        if p.exists():
                            os.startfile(str(p))
                            self.status.set("已打开: " + p.name)
                    elif kind == "open_url":
                        webbrowser.open(path)
                        self.status.set("已在浏览器打开 arXiv 页面")
                    return
        except Exception as exc:
            self.status.set("打开失败: " + str(exc))

    def send_command(self, text=None):
        if text is None:
            text = self.cmd_entry.get().strip()
            self.cmd_entry.delete(0, "end")
            if text == getattr(self, "_cmd_placeholder", None):
                text = ""
            self._entry_focus_out()
        if not text:
            return
        if not self.cmd_history or self.cmd_history[-1] != text:
            self.cmd_history.append(text)
        self.cmd_history = self.cmd_history[-30:]
        self.settings["cmd_history"] = self.cmd_history
        save_settings(self.settings)
        self.cmd_h_idx = None
        self._exec_command(text)

    def _show_cmd_output(self, lines, actions=None, tall=False, append=False):
        self.cmd_until = datetime.datetime.now() + datetime.timedelta(minutes=5)
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.log.config(state="normal", height=(10 if tall else 5))
        if not append:
            self.log.delete("1.0", "end")
            self.log_actions = []
        elif self.log_actions:
            self.log.insert("end", "\n")
        actions = actions or {}
        for i, ln in enumerate(lines):
            if i in actions:
                self.log_actions.append(actions[i])
                self.log.insert("end", ln + "\n",
                                ("act:%d" % (len(self.log_actions) - 1),))
            else:
                self.log.insert("end", ln + "\n", ("dim",))
        self.log.config(state="disabled")
        self._keep_pos(x, y)

    def _exec_command(self, text):
        low = text.strip().lower()
        if low in ("帮助", "help", "?", "？"):
            self._show_cmd_output([
                "可用指令：",
                "  抓取 [N天/N篇]    扫描 arXiv 新论文，可指定数量",
                "  智能: 下载最新的10篇红外目标检测论文，放到Mamba多模态",
                "  记忆 / 记住 方向=分类 / 忘记 方向",
                "  总览              生成科研知识总览",
                "  方向 <方向>       方向拓展并生成 Codex 提示词",
                "  方向库            按计算机大类/小类选择并生成调研提示词",
                "  导师 / 院校推荐   按方向匹配导师和机构",
                "  期刊 <方向> / 会议 <方向>   推荐期刊与会议",
                "  期刊会议             打开期刊/会议查询窗口",
                "  创新点 / 选题     创新点库 / 选题体检",
                "  预演 [N天]       只列候选、不下载",
                "  导出             导出论文清单 Excel",
                "  体检             重复/缺txt/未索引检查",
                "  周报             生成本地周报",
                "  统计              查看知识库与分类统计",
                "  搜索 关键词       检索 PDF 文件名与 Markdown 内容",
                "  打开 新论文/知识库/监控/分类名",
                "  打开 索引/速览     打开知识库索引或最新速览文件",
                "  最新              打开最近入库的一篇 PDF",
                "  添加检索词 词语   加入抓取查询",
                "  检索词           打开关键词捕捉窗口（下方按钮）",
                "  转交 任务描述     复制上下文，粘贴给 Codex",
                "  清空              恢复显示最近文件变动",
                "  置顶 / 最小化 / 关于   系统快捷操作",
                "",
                "快捷键: ↑/↓ 历史指令 · Esc 清空 · Ctrl+Enter 发送",
                "顶栏拖动=移动 · —=最小化 · 右键=高级菜单",
            ])
            return
        if low.startswith("清空"):
            self.cmd_until = datetime.datetime.now()
            self._render_log()
            self.status.set("已恢复显示最近文件变动")
            return
        if low in ("记忆", "memory"):
            mem = load_memory()
            maps = mem.get("mappings", {})
            hist = mem.get("history", [])
            lines = ["迭代记忆", "方向 → 分类："]
            if maps:
                for k, v in maps.items():
                    lines.append("  " + k + " → " + v)
            else:
                lines.append("  （暂无，用「记住 方向=分类」添加）")
            lines.append("最近智能抓取：")
            if hist:
                for h in hist[-6:][::-1]:
                    lines.append("  " + h.get("time", "") + " | " + h.get("direction", "")
                                 + " → " + (h.get("category") or "新论文")
                                 + " | 下载 " + str(h.get("downloaded", 0)))
            else:
                lines.append("  （暂无）")
            self._show_cmd_output(lines, [], tall=True)
            return
        if low.startswith("记住"):
            m = re.search(r"记住\s*[:：]?\s*(.+?)\s*(?:=|＝|→|->)\s*(.+)$", text)
            if not m:
                self._show_cmd_output(["用法: 记住 方向=分类，例如：记住 红外=医学"], [])
                return
            d, c = m.group(1).strip(), m.group(2).strip()
            mem = load_memory()
            mem.setdefault("mappings", {})[d] = c
            save_memory(mem)
            self._show_cmd_output(["已记住：" + d + " → " + c], [])
            self.status.set("✔ 记忆已更新")
            return
        if low.startswith("忘记"):
            key = text[2:].strip()
            mem = load_memory()
            maps = mem.setdefault("mappings", {})
            if key in maps:
                del maps[key]
                save_memory(mem)
                self._show_cmd_output(["已忘记：" + key], [])
            else:
                self._show_cmd_output(["没有找到映射：" + key], [])
            return
        if low in ("总览", "知识总览"):
            self.run_research_overview()
            return
        if low in ("导师", "推荐导师", "院校推荐", "导师推荐"):
            self.open_advisor_dialog()
            return
        if low in ("期刊会议", "期刊/会议"):
            self.open_venue_dialog()
            return
        if low.startswith(("期刊", "会议", "venue")):
            target = re.sub(r"^(期刊|会议|venue)\s*", "", text).strip()
            if not target:
                self.open_venue_dialog()
                return
            cat, field, _conf = infer_category_field(target)
            if not cat or not field:
                self._show_cmd_output(["未识别该方向，请到方向库手动选择领域。"], [])
                return
            tokens = _translate_direction(target)
            rels = load_research_relations()
            profile_key = field_profile(cat, field, rels)
            profile = rels.get("profiles", {}).get(profile_key, {})
            scen = profile.get("scenarios", [])[:1]
            meth = tokens + [m for m in profile.get("methods", [])[:2] if m not in tokens]
            task = profile.get("tasks", [])[:2]
            mod = profile.get("modalities", [])[:2]
            relation = evaluate_combo(profile_key,
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, rels)
            self.show_venue_recommendations(cat, field, scen[0] if scen else "",
                                            meth, task, mod, relation)
            return
        if low in ("方向库", "方向选择", "方向分类"):
            self.open_direction_library()
            return
        if low.startswith("方向"):
            self.open_direction_dialog(text[2:].strip())
            return
        if low in ("创新点", "创新点库"):
            self.open_ideas_dialog()
            return
        if low in ("选题", "选题体检"):
            self.open_ideas_dialog("review")
            return
        if low.startswith("搜索"):
            kw = text[2:].strip()
            if not kw:
                self._show_cmd_output(["用法: 搜索 关键词，例如：搜索 mamba"], [])
                return
            hits = search_kb(kw)
            if not hits:
                self._show_cmd_output(["未找到与「" + kw + "」匹配的 PDF。"], [])
                return
            actions = {}
            lines = ["搜索「" + kw + "」命中 " + str(len(hits)) + " 条（点击打开）："]
            for i, h in enumerate(hits):
                actions[i + 1] = ("open_file", h["path"])
                name = h["name"]
                if len(name) > 38:
                    name = name[:35] + "…"
                lines.append("[" + h["cat"] + "] " + name)
            self._show_cmd_output(lines, actions)
            self.status.set("搜索「" + kw + "」命中 " + str(len(hits)) + " 条")
            return
        if low.startswith("统计"):
            cfg = load_config()
            stats = kb_stats()
            lines = ["知识库统计：",
                     "  PDF 总数: " + str(stats["total_pdf"]) + " | 已跟踪 arXiv: " + str(seen_count()),
                     "  检索词组: " + str(len(cfg.get("queries", []))) +
                     " | 抓取窗口: 近 " + str(cfg.get("days_back", 7)) + " 天",
                     "分类明细:"]
            for c in kb_categories():
                lines.append("  " + c["name"] + "  " + str(c["count"]) + " 篇")
            self._show_cmd_output(lines)
            return
        if low.startswith("打开"):
            target = text[2:].strip()
            if not target:
                self._show_cmd_output(["用法: 打开 新论文 / 知识库 / 监控 / 索引 / 速览 / 分类名"], [])
                return
            tl = target.lower()
            if "新论文" in tl or "inbox" in tl:
                self.open_dir("inbox")
            elif "知识库" in tl or tl == "kb":
                self.open_dir("kb")
            elif "监控" in tl or "monitor" in tl:
                self.open_dir("monitor")
            elif "网页" in tl:
                self.open_web()
            elif "索引" in tl:
                p = kb_root() / "索引.md"
                if p.exists():
                    os.startfile(str(p))
                    self.status.set("已打开: 索引.md")
                else:
                    self.status.set("未找到 索引.md")
            elif "速览" in tl:
                data = latest_digest_data()
                if data:
                    os.startfile(data["path"])
                    self.status.set("已打开: " + data["file"])
                else:
                    self.status.set("暂无速览文件")
            else:
                for c in kb_categories():
                    if target in c["name"] or c["name"] in target:
                        self.open_dir_path(c["path"])
                        self.status.set("已打开分类: " + c["name"])
                        return
                self._show_cmd_output([
                    "没有叫「" + target + "」的分类。",
                    "现有分类: " + " / ".join(c["name"] for c in kb_categories()),
                ], [])
            return
        spec = parse_smart_command(text)
        if spec:
            self.start_smart_fetch(spec)
            return
        if low.startswith("抓取") or low.startswith("扫描"):
            if self.scanning:
                self._show_cmd_output(["已有抓取任务在运行，请稍候…"], [])
                return
            m_days = re.search(r"(\d+)\s*天", text)
            m_cnt = re.search(r"(\d+)\s*(?:篇|paper)", text, re.I)
            if not m_cnt:
                m_cnt = re.search(r"抓取\s*(\d+)\s*$", text)
            days = int(m_days.group(1)) if m_days else None
            max_dl = int(m_cnt.group(1)) if m_cnt else None
            desc = "开始抓取 arXiv 新论文（"
            desc += ("近 " + str(days) + " 天") if days else "默认时间窗口"
            if max_dl:
                desc += "，最多 " + str(max_dl) + " 篇"
            desc += "）… 完成后自动刷新。"
            self._show_cmd_output([desc], [])
            self.start_scan(days, max_dl)
            return
        if low.startswith("添加检索词") or low.startswith("添加关键词"):
            rest = text.split(" ", 1)[1].strip() if " " in text else ""
            if not rest:
                self._show_cmd_output(["用法: 添加检索词 词语，例如：添加检索词 mamba"], [])
                return
            cfg = load_config()
            q = rest if ("all:" in rest or " AND " in rest.upper()) else "all:" + rest
            qs = cfg.setdefault("queries", [])
            if q in qs:
                self._show_cmd_output(["该检索词已存在: " + q], [])
                return
            qs.append(q)
            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            self._show_cmd_output([
                "已添加检索词: " + q,
                "下次抓取会包含它；也可打开监控目录直接编辑 config.json。"], [])
            return
        if low.startswith("转交"):
            task = text.split(" ", 1)[1].strip() if " " in text else ""
            cfg = load_config()
            prompt = (
                "【知识库助手转交任务】\n"
                "任务: " + (task or "（未填写，请补充任务描述）") + "\n"
                "知识库路径: " + str(kb_root()) + "\n"
                "新论文目录: " + str(inbox_dir()) + "\n"
                "当前检索词: " + "; ".join(cfg.get("queries", [])) + "\n"
                "请按知识库既有索引与分类规则处理，只追加、不改老条目。"
            )
            self._clip_copy(prompt)
            self._show_cmd_output([
                "已把任务上下文复制到剪贴板。",
                "打开 Codex 对话直接粘贴发送即可。",
                "任务摘要: " + (task[:50] if task else "未填写")], [])
            return
        if low in ("置顶", "pin", "top"):
            self.toggle_pin()
            return
        if low in ("最小化", "min"):
            self._minimize()
            return
        if low in ("关于", "about", "版本", "version", "v"):
            cfg = load_config()
            ts = task_status()
            self._show_cmd_output([
                "550W·知识库助手 v3.5",
                "监控目录: " + str(HERE),
                "知识库: " + str(kb_root()),
                "检索词组: " + str(len(cfg.get("queries", []))) + " 条",
                "抓取窗口: 近 " + str(cfg.get("days_back", 7)) + " 天",
                "定时任务: " + ts.get("status", "未知") + " · 下次 " + ts.get("next_run", "未知"),
            ])
            return
        if low in ("最新", "latest", "最新论文"):
            pdfs = recent_pdfs(3650, 1)
            if pdfs:
                os.startfile(pdfs[0]["path"])
                self.status.set("已打开最新入库: " + pdfs[0]["name"])
            else:
                self.status.set("知识库中暂无 PDF")
            return
        if low.startswith(("预演", "预览", "dry")):
            m = re.search(r"(\d+)\s*天", text)
            self.start_preview(int(m.group(1)) if m else None)
            return
        if low in ("导出", "导出清单", "excel"):
            self.export_papers()
            return
        if low in ("体检", "知识库体检", "检查"):
            self.run_health()
            return
        if low in ("周报", "简报", "weekly"):
            self.make_weekly()
            return
        self._show_cmd_output([
            "没有理解「" + text + "」。",
            "输入「帮助」查看可用指令。"], [])

    def _clip_copy(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            pass

    def _render_digest(self, data=None):
        if data is None:
            data = latest_digest_data()
        self.digest.config(state="normal")
        self.digest.delete("1.0", "end")
        self.digest_actions = []
        if not data:
            self.digest.insert("1.0", "暂无速览记录。", ("meta",))
            self._append_research_outputs()
            self.digest.config(state="disabled")
            return
        self.digest_actions.append(("open_file", data["path"]))
        self.digest.insert(
            "end",
            "速览 " + data["file"] + " · " + str(len(data["entries"])) + " 篇",
            ("meta", "act:0"),
        )
        latest_scan = data.get("latest_scan") or {}
        if (latest_scan.get("entries") == 0
                and latest_scan.get("file") != data.get("file")):
            self.digest.insert(
                "end",
                "\n最近一次扫描新增 0 篇，当前显示最近一次有效速览",
                ("dim",),
            )
        if data["entries"]:
            used = 0
            local_paths = set()
            for e in data["entries"]:
                if used > 800:
                    self.digest.insert("end", "\n……更多见速览文件（点击顶部文件名）", ("meta",))
                    break
                pdf = find_pdf_by_arxiv(e["arxiv"]) if e["arxiv"] else None
                if pdf and pdf.exists():
                    action = ("open_file", str(pdf))
                    prefix = "[本地] "
                    local_paths.add(str(pdf))
                elif e["arxiv"]:
                    action = ("open_url", ARXIV_ABS_URL + e["arxiv"])
                    prefix = "[arXiv] "
                else:
                    action = ("open_file", data["path"])
                    prefix = ""
                self.digest_actions.append(action)
                tag = ("paper", "act:%d" % (len(self.digest_actions) - 1))
                self.digest.insert("end", "\n\n" + prefix + e["title"], tag)
                used += len(e["title"])
                for ln in e["lines"]:
                    self.digest.insert("end", "\n  " + ln, ("dim",))
                    used += len(ln)
            extra = [it for it in recent_pdfs(14, 5)
                     if it["path"] not in local_paths][:3]
            if extra:
                self.digest.insert("end", "\n\n最近入库（未进入当前速览）", ("meta",))
                for it in extra:
                    self.digest_actions.append(("open_file", it["path"]))
                    tag = ("paper", "act:%d" % (len(self.digest_actions) - 1))
                    name = it["name"]
                    if len(name) > 36:
                        name = name[:33] + "…"
                    self.digest.insert(
                        "end", "\n" + it["date"] + " [" + it["cat"] + "] " + name,
                        tag,
                    )
        else:
            items = recent_pdfs(14, 5)
            if items:
                self.digest.insert("end", "\n\n最近 14 天入库（速览暂无新论文，点击打开）", ("dim",))
                for it in items:
                    self.digest_actions.append(("open_file", it["path"]))
                    tag = ("paper", "act:%d" % (len(self.digest_actions) - 1))
                    name = it["name"]
                    if len(name) > 36:
                        name = name[:33] + "…"
                    self.digest.insert("end", "\n" + it["date"] + " [" + it["cat"] + "] " + name, tag)
            else:
                self.digest_actions.append(("action_scan", "", ""))
                self.digest.insert("end", "\n\n（近 14 天没有新入库 PDF）", ("dim",))
                self.digest.insert("end", "\n▶ 立即抓取 arXiv 新论文",
                                   ("paper", "act:%d" % (len(self.digest_actions) - 1)))
                self.digest_actions.append(("open_dir", str(kb_root()), ""))
                self.digest.insert("end", "\n▶ 打开知识库（浏览全部论文）",
                                   ("paper", "act:%d" % (len(self.digest_actions) - 1)))
        self._append_research_outputs()
        self.digest.insert("end", "\n")
        self.digest.config(state="disabled")

    def _append_research_outputs(self):
        outputs = recent_research_outputs(6)
        if not outputs:
            return
        self.digest.insert("end", "\n\n── 科研产出（点击打开） ──", ("meta",))
        for out in outputs:
            self.digest_actions.append(("open_file", out["path"]))
            tag = ("paper", "act:%d" % (len(self.digest_actions) - 1))
            title = out["title"]
            if len(title) > 44:
                title = title[:41] + "…"
            self.digest.insert("end", "\n[" + out["kind"] + "] " + title
                               + "  ·  " + out["time"], tag)

    def _render_categories(self, cats=None, force=False):
        if cats is None:
            cats = kb_categories()
        cats = cats[:10]
        self._cat_data = cats
        if not force and not self.secs.get("cats", {}).get("state", True):
            return
        sig = [(c["name"], c["count"]) for c in cats]
        if sig == getattr(self, "_cat_sig", None):
            return
        self._cat_sig = sig
        for child in self.cat_holder.winfo_children():
            child.destroy()
        if not cats:
            self._mk_cat(0, 0, "暂无子分类", 0, str(kb_root()))
            return
        for i, it in enumerate(cats):
            self._mk_cat(i % 2, i // 2, it["name"], it["count"], it["path"])

    def _mk_cat(self, col, row, name, count, path):
        f = tk.Frame(self.cat_holder, bg=CARD, highlightbackground=LINE,
                     highlightthickness=1, cursor="hand2")
        f.grid(row=row, column=col, sticky="nsew", padx=3, pady=2)
        tk.Label(f, text=name, bg=CARD, fg=TXT, font=FONT_XS,
                 anchor="w").pack(side="left", padx=8, pady=4)
        tk.Label(f, text=str(count), bg=CARD, fg=ACCENT,
                 font=("Consolas", 9, "bold")).pack(side="right", padx=8, pady=4)
        for wdg in (f,) + tuple(f.winfo_children()):
            wdg.bind("<Button-1>", lambda e, p=path: self.open_dir_path(p))

        def on_enter(e, w=f):
            for x in (w,) + tuple(w.winfo_children()):
                x.configure(bg=LINE)

        def on_leave(e, w=f):
            for x in (w,) + tuple(w.winfo_children()):
                x.configure(bg=CARD)

        f.bind("<Enter>", on_enter)
        f.bind("<Leave>", on_leave)

    def open_dir_path(self, path):
        try:
            p = Path(path)
            p.mkdir(parents=True, exist_ok=True)
            os.startfile(str(p))
            self.status.set("已打开: " + p.name)
        except Exception as exc:
            self.status.set("打开失败: " + str(exc))

    def _digest_click(self, e):
        try:
            idx = self.digest.index("@%d,%d" % (e.x, e.y))
            for t in self.digest.tag_names(idx):
                if t.startswith("act:"):
                    i = int(t[4:])
                    kind, path = self.digest_actions[i]
                    if kind == "open_file":
                        p = Path(path)
                        if p.exists():
                            os.startfile(str(p))
                            self.status.set("已打开: " + p.name)
                        else:
                            self.status.set("文件不存在: " + str(p))
                    elif kind == "open_url":
                        webbrowser.open(path)
                        self.status.set("本地 PDF 未找到，已打开 arXiv 页面")
                    elif kind == "action_scan":
                        self.status.set("● 开始抓取 arXiv 新论文…")
                        self.start_scan()
                    elif kind == "open_dir":
                        os.startfile(path)
                        self.status.set("已打开: " + Path(path).name)
                    return
        except Exception as exc:
            self.status.set("打开失败: " + str(exc))

    def refresh(self, force=False):
        if getattr(self, "_refreshing", False):
            return
        self._refreshing = True
        threading.Thread(target=lambda: self._refresh_worker(force), daemon=True).start()

    def _refresh_worker(self, force=False):
        try:
            if force:
                _CACHE.clear()
            snap = {
                "stats": kb_stats(),
                "cats": kb_categories(),
                "recents": recent_files(6),
                "ts": task_status(),
                "digest": latest_digest_data(),
                "new_n": today_inbox_pdfs(),
                "error": "",
            }
        except Exception as exc:
            snap = {"error": str(exc)}
        self._snap_q.put(snap)

    def _apply_snapshot(self, snap):
        self._refreshing = False
        if snap.get("error"):
            try:
                self.status.set("刷新失败: " + snap["error"])
            except tk.TclError:
                pass
            return
        try:
            stats = snap["stats"]
            self.stat_frames["pdf"].config(text=str(stats["total_pdf"]))
            self.stat_frames["seen"].config(text=str(seen_count()))
            self.stat_frames["queries"].config(
                text=str(len(load_config().get("queries", []))))
            nxt = snap["ts"].get("next_run", "未知")
            if len(nxt) > 19:
                nxt = nxt[:19]
            self.stat_frames["task"].config(text=nxt)
            try:
                self.sync_lbl.config(text="SYNC " + datetime.datetime.now().strftime("%H:%M:%S"))
            except tk.TclError:
                pass
            new_n = snap.get("new_n", 0)
            self.new_lbl.config(text=(" NEW " + str(new_n) + " ") if new_n else "")
            self._render_digest(snap.get("digest"))
            self._render_categories(snap.get("cats"))
            if datetime.datetime.now() >= self.cmd_until:
                self._render_log(snap.get("recents"))
        except Exception as exc:
            try:
                self.status.set("刷新失败: " + str(exc))
            except tk.TclError:
                pass

    def _tick(self):
        self.refresh()
        self.root.after(60000, self._tick)

    def _poll_queues(self):
        try:
            while True:
                stage, pct, detail = self._progress_q.get_nowait()
                self._apply_progress(stage, pct, detail)
        except queue.Empty:
            pass
        try:
            while True:
                snap = self._snap_q.get_nowait()
                self._apply_snapshot(snap)
        except queue.Empty:
            pass
        try:
            while True:
                status = self._scan_q.get_nowait()
                self._scan_done(status)
        except queue.Empty:
            pass
        try:
            while True:
                kind, payload = self._report_q.get_nowait()
                self._tool_done(kind, payload)
        except queue.Empty:
            pass
        try:
            delay = 60 if (getattr(self, "_tool_running", False)
                           or getattr(self, "scanning", False)) else 120
            self.root.after(delay, self._poll_queues)
        except tk.TclError:
            pass

    def run_research_overview(self):
        self._run_tool("overview", "科研知识总览",
                       lambda progress: knowledge_overview(progress))

    def _copy_prompt(self, kind, prompt):
        path = save_prompt(kind, prompt)
        self._clip_copy(prompt)
        mem = load_research_memory()
        mem.setdefault("handoffs", []).append({
            "time": datetime.datetime.now().isoformat(timespec="minutes"),
            "kind": kind,
            "file": str(path),
        })
        save_research_memory(mem)
        self._ensure_log_open()
        self._show_cmd_output([
            "提示词已复制到剪贴板",
            "打开 Codex 对话，粘贴发送即可（会调用相应科研 skill）",
            "已保存: " + path.name,
        ], {2: ("open_file", str(path))}, tall=True)
        self.status.set("✔ 提示词已复制，粘贴给 Codex")
        self._ensure_digest_open()
        self.refresh(force=True)
        return path

    def open_direction_dialog(self, initial=""):
        dlg = tk.Toplevel(self.root)
        dlg.title("科研工作台 · 方向拓展")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry("1040x720+%d+%d" % (
            max(20, self.root.winfo_x() - 120),
            max(20, self.root.winfo_y() + 20),
        ))
        tk.Label(dlg, text="◆ 方向拓展与可行性预筛", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(
                     anchor="w", padx=14, pady=(12, 2))
        tk.Label(
            dlg,
            text="本地先按稳健邻接、跨域迁移和高风险高回报三类生成候选；"
                 "选中候选后可继续查导师、查 venue、存创新点或生成验证提示词。",
            bg=BG, fg=MUT, font=FONT_XS, wraplength=1000, justify="left",
        ).pack(anchor="w", padx=14)
        entry = tk.Entry(dlg, bg=CARD, fg=TXT, insertbackground=TXT,
                         relief="flat", highlightbackground=LINE,
                         highlightthickness=1, font=FONT_S)
        entry.pack(fill="x", padx=14, pady=(8, 5), ipady=5)
        entry.insert(0, initial)

        controls = tk.Frame(dlg, bg=BG)
        controls.pack(fill="x", padx=14, pady=(0, 5))
        mode_var = tk.StringVar(value=DIRECTION_MODES[0])
        sort_var = tk.StringVar(value="综合优先")
        tk.Label(controls, text="拓展策略", bg=BG, fg=MUT,
                 font=FONT_XS).pack(side="left")
        mode_menu = tk.OptionMenu(controls, mode_var, *DIRECTION_MODES)
        mode_menu.config(bg=CARD, fg=TXT, activebackground=LINE,
                         activeforeground=TXT, relief="flat", bd=0,
                         highlightthickness=0, font=FONT_XS)
        mode_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                 activeforeground=TXT, bd=0)
        mode_menu.pack(side="left", padx=(6, 16))
        tk.Label(controls, text="排序", bg=BG, fg=MUT,
                 font=FONT_XS).pack(side="left")
        sort_menu = tk.OptionMenu(
            controls, sort_var, "综合优先", "新颖性优先", "可行性优先", "相关性优先")
        sort_menu.config(bg=CARD, fg=TXT, activebackground=LINE,
                         activeforeground=TXT, relief="flat", bd=0,
                         highlightthickness=0, font=FONT_XS)
        sort_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                 activeforeground=TXT, bd=0)
        sort_menu.pack(side="left", padx=(6, 0))
        meta = tk.Label(dlg, text="", bg=BG, fg=OKC, font=FONT_XS, anchor="w")
        meta.pack(fill="x", padx=14, pady=(2, 4))

        body = tk.Frame(dlg, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 4))
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        tk.Label(left, text="候选方向（分数为本地预筛，不是结论）", bg=BG,
                 fg=MUT, font=FONT_XS).pack(anchor="w")
        tk.Label(right, text="候选详情与验证问题", bg=BG,
                 fg=MUT, font=FONT_XS).pack(anchor="w")
        list_sb = tk.Scrollbar(left)
        cand_lb = tk.Listbox(
            left, height=20, width=54, bg=CARD, fg=TXT,
            selectbackground=LINE, selectforeground=ACCENT,
            relief="flat", highlightbackground=LINE, highlightthickness=1,
            font=FONT_XS, yscrollcommand=list_sb.set, exportselection=False,
        )
        list_sb.config(command=cand_lb.yview)
        list_sb.pack(side="right", fill="y")
        cand_lb.pack(side="left", fill="both", expand=True)
        details = tk.Text(
            right, height=20, wrap="word", bg=CARD, fg=TXT,
            relief="flat", highlightbackground=LINE, highlightthickness=1,
            font=FONT_XS, padx=10, pady=8, spacing1=2, spacing3=2,
        )
        details.pack(fill="both", expand=True)
        details.tag_config("h", foreground=ACCENT,
                           font=("Microsoft YaHei UI", 10, "bold"))
        details.tag_config("warn", foreground=WARN)
        details.tag_config("muted", foreground=MUT)
        details.config(state="disabled")
        status = tk.Label(dlg, text="", bg=BG, fg=MUT, font=FONT_XS, anchor="w")
        status.pack(fill="x", padx=14, pady=(2, 0))
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))

        rows_state = {"rows": [], "selected": None}

        def current_direction():
            return entry.get().strip()

        def update_meta():
            direction = current_direction()
            if not direction:
                meta.config(text="请输入研究方向")
                return
            category, field, confidence = infer_category_field(direction)
            if category and field:
                relations = load_research_relations()
                profile_key = field_profile(category, field, relations)
                profile = relations.get("profiles", {}).get(profile_key, {})
                label = (category + " / " + field + " · 置信度 "
                         + str(confidence) + "% · 画像 "
                         + profile.get("label", profile_key))
                related = relations.get("category_related", {}).get(category, [])
                if related:
                    label += " · 关联大类: " + "、".join(related[:3])
            else:
                label = "未稳定识别目录；仍会生成通用候选，建议到方向库手动校正"
            meta.config(text=label)

        def selected_candidate():
            sel = cand_lb.curselection()
            if not sel or sel[0] >= len(rows_state["rows"]):
                return None
            return rows_state["rows"][sel[0]]

        def show_candidate(_event=None):
            item = selected_candidate()
            if not item:
                return
            rows_state["selected"] = item
            details.config(state="normal")
            details.delete("1.0", "end")
            details.insert("end", item["title"] + "\n", ("h",))
            details.insert(
                "end",
                "\n策略: " + item["strategy"]
                + "\n预筛分数: 综合 " + str(item["score"])
                + " | 相关 " + str(item["relevance"])
                + " | 新颖 " + str(item["novelty"])
                + " | 可行 " + str(item["feasibility"])
                + "\n目录: " + (item.get("category") or "待识别")
                + " / " + (item.get("field") or "待识别")
                + "\n\n为什么会产生这个候选:\n" + item["reason"] + "\n",
                ("muted",),
            )
            details.insert("end", "\n先验证这三个问题:\n", ("h",))
            for index, question in enumerate(item.get("questions", []), 1):
                details.insert("end", str(index) + ". " + question + "\n")
            details.insert(
                "end",
                "\n注意: 分数只用于本地预筛；方向是否值得做，必须经过文献证据和最小实验验证。",
                ("warn",),
            )
            details.config(state="disabled")

        def refresh_candidates(*_args):
            direction = current_direction()
            if not direction:
                cand_lb.delete(0, "end")
                rows_state["rows"] = []
                show_candidate()
                update_meta()
                return
            update_meta()
            rows = expand_direction_candidates(direction, mode_var.get(), 24)
            sort_mode = sort_var.get()
            if sort_mode == "新颖性优先":
                rows.sort(key=lambda x: (-x["novelty"], -x["score"], x["title"]))
            elif sort_mode == "可行性优先":
                rows.sort(key=lambda x: (-x["feasibility"], -x["score"], x["title"]))
            elif sort_mode == "相关性优先":
                rows.sort(key=lambda x: (-x["relevance"], -x["score"], x["title"]))
            rows_state["rows"] = rows
            cand_lb.delete(0, "end")
            badge = {"稳健邻接": "稳", "跨领域迁移": "跨", "高风险高回报": "险"}
            for index, item in enumerate(rows):
                title = item["title"]
                if len(title) > 38:
                    title = title[:35] + "…"
                cand_lb.insert(
                    "end",
                    "[" + badge.get(item["strategy"], "?") + "] "
                    + str(item["score"]) + " | " + title,
                )
                color = (OKC if item["strategy"] == "稳健邻接"
                         else ACCENT if item["strategy"] == "跨领域迁移" else WARN)
                cand_lb.itemconfig(index, fg=color)
            if rows:
                cand_lb.selection_set(0)
                cand_lb.activate(0)
                show_candidate()
            else:
                rows_state["selected"] = None
            status.config(text="已生成 " + str(len(rows)) + " 个候选")

        refresh_job = {"id": None}

        def schedule_refresh(_event=None):
            try:
                if refresh_job["id"]:
                    dlg.after_cancel(refresh_job["id"])
            except tk.TclError:
                pass
            refresh_job["id"] = dlg.after(260, refresh_candidates)

        def selected_or_base():
            item = selected_candidate()
            direction = current_direction()
            if item:
                return item, item.get("category") or "", item.get("field") or ""
            category, field, _confidence = infer_category_field(direction)
            return None, category, field

        def recommend_advisors_for_selected():
            item, category, field = selected_or_base()
            direction = item["title"] if item else current_direction()
            if not direction:
                status.config(text="请先选择候选方向")
                return
            tokens = _translate_direction(direction)
            self.show_advisor_recommendations(
                category, field or direction, "", tokens, [], [])

        def recommend_venues_for_selected():
            item, category, field = selected_or_base()
            direction = item["title"] if item else current_direction()
            if not category or not field:
                category, field, _confidence = infer_category_field(direction)
            if not category or not field:
                status.config(text="未识别候选目录，请先在方向库手动选择")
                return
            relations = load_research_relations()
            profile_key = field_profile(category, field, relations)
            profile = relations.get("profiles", {}).get(profile_key, {})
            scenario = (profile.get("scenarios") or [""])[0]
            methods = _translate_direction(direction)
            methods += [name for name in profile.get("methods", [])[:2]
                        if name not in methods]
            tasks = profile.get("tasks", [])[:2]
            modalities = profile.get("modalities", [])[:2]
            relation = evaluate_combo(profile_key, {
                "scenario": [scenario] if scenario else [],
                "method": methods,
                "task": tasks,
                "modality": modalities,
            }, relations)
            self.show_venue_recommendations(
                category, field, scenario, methods, tasks, modalities, relation)

        def save_selected_idea():
            item = selected_candidate()
            if not item:
                status.config(text="请先选择一个候选方向")
                return
            idea_type = infer_innovation_type(item["title"], item["reason"])
            mem = load_research_memory()
            mem.setdefault("ideas", []).append({
                "time": datetime.datetime.now().isoformat(timespec="minutes"),
                "category": item.get("category") or "",
                "field": item.get("field") or "",
                "type": idea_type,
                "title": item["title"],
                "domain": item["strategy"],
                "desc": item["reason"] + "\n关键验证问题: "
                        + "；".join(item.get("questions", [])),
            })
            save_research_memory(mem)
            status.config(text="✔ 已存入创新点库，可继续做选题体检")

        def copy_research_prompt():
            direction = current_direction()
            if not direction:
                status.config(text="请输入研究方向")
                return
            rows = rows_state["rows"]
            if not rows:
                rows = expand_direction_candidates(direction, mode_var.get(), 24)
            selected = selected_candidate()
            prompt = expanded_direction_prompt(direction, rows, selected)
            mem = load_research_memory()
            mem.setdefault("directions", []).append({
                "time": datetime.datetime.now().isoformat(timespec="minutes"),
                "direction": direction,
                "mode": mode_var.get(),
                "candidates": rows,
                "selected": selected,
            })
            save_research_memory(mem)
            self._copy_prompt("方向拓展", prompt)

        def continue_with_selected():
            item = selected_candidate()
            if not item:
                status.config(text="请先选择一个候选方向")
                return
            entry.delete(0, "end")
            entry.insert(0, item["title"])
            refresh_candidates()
            status.config(text="已把候选设为新的基础方向，可继续做下一层拓展")

        entry.bind("<KeyRelease>", schedule_refresh)
        entry.bind("<Return>", lambda e: refresh_candidates())
        mode_var.trace_add("write", lambda *a: refresh_candidates())
        sort_var.trace_add("write", lambda *a: refresh_candidates())
        cand_lb.bind("<<ListboxSelect>>", show_candidate)
        cand_lb.bind("<Double-Button-1>", lambda e: continue_with_selected())

        self._btn(btns, "重新生成", refresh_candidates).pack(side="left")
        self._btn(btns, "导师/院校", recommend_advisors_for_selected).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "期刊/会议", recommend_venues_for_selected).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "存为创新点", save_selected_idea).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "以此再拓展", continue_with_selected).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "复制验证提示词", copy_research_prompt,
                  accent=True).pack(side="left", padx=(8, 0))
        self._btn(btns, "关闭", dlg.destroy).pack(side="left", padx=(8, 0))
        refresh_candidates()

    def open_direction_library(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("科研工作台 · 方向库")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry("980x820+%d+%d" % (self.root.winfo_x() + 20, self.root.winfo_y() + 20))
        taxonomy = load_research_taxonomy()
        relations = load_research_relations()
        library = taxonomy["categories"]
        field_count = sum(len(entry.get("subs", [])) for entry in library.values())
        tk.Label(dlg, text="◆ 计算机科研方向与场景库", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Label(dlg, text=f"{len(library)} 个大类 × {field_count} 个研究领域 · "
                           "依据 ACM/IEEE CS2023、CCF 与公开出版主题映射，"
                           "再组合应用场景、方法、任务和模态。",
                 bg=BG, fg=MUT, font=FONT_XS, wraplength=940, justify="left").pack(anchor="w", padx=14)
        body = tk.Frame(dlg, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(8, 4))
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        tk.Label(left, text="大类", bg=BG, fg=MUT, font=FONT_XS).pack(anchor="w")
        tk.Label(right, text="小类", bg=BG, fg=MUT, font=FONT_XS).pack(anchor="w")
        cat_sb = tk.Scrollbar(left)
        cat_lb = tk.Listbox(left, height=14, bg=CARD, fg=TXT, selectbackground=LINE,
                            selectforeground=ACCENT, relief="flat",
                            highlightbackground=LINE, highlightthickness=1,
                            font=FONT_XS, yscrollcommand=cat_sb.set)
        cat_sb.config(command=cat_lb.yview)
        cat_sb.pack(side="right", fill="y")
        cat_lb.pack(side="left", fill="both", expand=True)
        sub_sb = tk.Scrollbar(right)
        sub_lb = tk.Listbox(right, height=14, bg=CARD, fg=TXT, selectbackground=LINE,
                            selectforeground=ACCENT, relief="flat",
                            highlightbackground=LINE, highlightthickness=1,
                            font=FONT_XS, yscrollcommand=sub_sb.set)
        sub_sb.config(command=sub_lb.yview)
        sub_sb.pack(side="right", fill="y")
        sub_lb.pack(side="left", fill="both", expand=True)

        dims = tk.Frame(dlg, bg=BG)
        dims.pack(fill="x", padx=10, pady=(6, 2))

        def make_dim_list(title, multi=False):
            frame = tk.Frame(dims, bg=BG)
            frame.pack(side="left", fill="both", expand=True, padx=4)
            tk.Label(frame, text=title, bg=BG, fg=MUT, font=FONT_XS).pack(anchor="w")
            sb = tk.Scrollbar(frame)
            lb = tk.Listbox(frame, height=5, bg=CARD, fg=TXT, selectbackground=LINE,
                            selectforeground=ACCENT, relief="flat",
                            highlightbackground=LINE, highlightthickness=1,
                            font=FONT_XS, exportselection=False,
                            selectmode="extended" if multi else "browse",
                            yscrollcommand=sb.set)
            sb.config(command=lb.yview)
            sb.pack(side="right", fill="y")
            lb.pack(side="left", fill="both", expand=True)
            return lb

        scenario_lb = make_dim_list("应用场景")
        method_lb = make_dim_list("方法（可多选）", True)
        task_lb = make_dim_list("任务（可多选）", True)
        modality_lb = make_dim_list("模态（可多选）", True)
        tk.Label(dlg, text="参考高校/机构: Stanford · MIT CSAIL · CMU · Berkeley · Oxford · ETH · "
                           "清华 · 北大 · 浙大 · HKUST · NUS · Toronto · MPI-IS · MSRA",
                 bg=BG, fg=MUT, font=("Consolas", 7)).pack(anchor="w", padx=14)
        relation_label = tk.Label(dlg, text="组合相关度: —", bg=BG, fg=WARN,
                                  font=FONT_XS, anchor="w")
        relation_label.pack(fill="x", padx=14)
        preview = tk.Text(dlg, height=5, wrap="word", bg=CARD, fg=TXT,
                          relief="flat", highlightbackground=LINE, highlightthickness=1,
                          font=FONT_XS, padx=10, pady=8)
        preview.pack(fill="x", padx=14)
        status = tk.Label(dlg, text="", bg=BG, fg=MUT, font=FONT_XS, anchor="w")
        status.pack(fill="x", padx=14)
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))
        cats = sorted(library.keys())
        scenarios = taxonomy["scenarios"]
        methods = taxonomy["methods"]
        tasks = taxonomy["tasks"]
        modalities = taxonomy["modalities"]

        dim_specs = (
            ("scenario", scenario_lb, scenarios, "scenarios"),
            ("method", method_lb, methods, "methods"),
            ("task", task_lb, tasks, "tasks"),
            ("modality", modality_lb, modalities, "modalities"),
        )

        def fill_dim(lb, items, strong=None):
            strong = strong or set()
            lb.delete(0, "end")
            for it in items:
                name = it.get("name", "")
                lb.insert("end", ("★ " if name in strong else "○ ") + name)
        current = {"cat": "", "sub": None, "profile": "ml_method"}

        def refresh_cats():
            cat_lb.delete(0, "end")
            for c in cats:
                cat_lb.insert("end", c)

        def selected_names(lb, items):
            return [items[i].get("name", "") for i in lb.curselection()
                    if i < len(items)]

        def reset_dims_neutral():
            for _key, lb, items, _pkey in dim_specs:
                lb.delete(0, "end")
                lb.selection_clear(0, "end")
                for i, it in enumerate(items):
                    lb.insert("end", "○ " + it.get("name", ""))
                    lb.itemconfig(i, fg=MUT)
            relation_label.config(text="组合相关度: — · 选择研究领域后自动推荐", fg=MUT)

        def refresh_dimension_marks():
            sub = current.get("sub")
            cat = current.get("cat")
            if not sub:
                reset_dims_neutral()
                return
            profile_key = field_profile(cat, sub.get("name", ""), relations)
            current["profile"] = profile_key
            profile = relations.get("profiles", {}).get(profile_key, {})
            importance = profile.get("importance", {})
            caps = {"scenarios": 1, "methods": 2, "tasks": 2, "modalities": 2}
            for key, lb, items, pkey in dim_specs:
                strong = set(profile.get(pkey, []))
                lb.delete(0, "end")
                lb.selection_clear(0, "end")
                count = 0
                for i, it in enumerate(items):
                    name = it.get("name", "")
                    core = name in strong
                    lb.insert("end", ("★ " if core else "○ ") + name)
                    lb.itemconfig(i, fg=ACCENT if core else MUT)
                    if core and count < caps[pkey] and float(importance.get(key, 0)) >= 0.45:
                        lb.selection_set(i)
                        count += 1
            update_preview()

        def update_preview(*_args):
            sub = current.get("sub")
            cat = current.get("cat") or "未选择大类"
            scen = selected_names(scenario_lb, scenarios)
            meth = selected_names(method_lb, methods)
            task = selected_names(task_lb, tasks)
            mod = selected_names(modality_lb, modalities)
            relation = evaluate_combo(current.get("profile", "ml_method"),
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, relations)
            preview.config(state="normal")
            preview.delete("1.0", "end")
            if not sub:
                preview.insert("1.0", "大类: " + cat
                               + "\n请选择研究领域；场景/方法/任务/模态可按需多选。")
                relation_label.config(text="组合相关度: — · 选择研究领域后自动推荐", fg=MUT)
            else:
                venue_rows = recommend_venues(cat, sub.get("name", ""),
                                              scen[0] if scen else "",
                                              meth, task, mod, top=6)
                venues = [v["name"] for v in venue_rows]
                preview.insert("1.0",
                    "大类: " + cat + "\n研究领域: " + sub.get("name", "")
                    + "\n领域关键词: " + ", ".join(sub.get("keywords", []))
                    + "\n应用场景: " + (" / ".join(scen) or "通用")
                    + "\n方法: " + (" / ".join(meth) or "待定")
                    + "\n任务: " + (" / ".join(task) or "待定")
                    + "\n模态: " + (" / ".join(mod) or "待定")
                    + "\n推荐 venue: " + (", ".join(venues) or "领域主流")
                    + "\n关系画像: " + relation["profile"]
                    + "\n组合相关度: " + str(relation["score"]) + "%"
                    + ("\n弱相关项: " + " / ".join(relation["weak"])
                       if relation["weak"] else ""))
                label = ("画像: " + relation["profile"] + " · 相关度: "
                         + str(relation["score"]) + "%")
                if relation["strong_axes"]:
                    label += " · 强轴: " + "/".join(relation["strong_axes"])
                if relation["weak"]:
                    label += " · 弱项 " + str(len(relation["weak"])) + " 个"
                color = (OKC if relation["score"] >= 75
                         else WARN if relation["score"] >= 55 else ERR)
                relation_label.config(text=label, fg=color)
            preview.config(state="disabled")

        def on_cat(_e=None):
            sel = cat_lb.curselection()
            if not sel:
                return
            cat = cats[sel[0]]
            current["cat"] = cat
            current["sub"] = None
            subs = library.get(cat, {}).get("subs", [])
            sub_lb.delete(0, "end")
            for s in subs:
                sub_lb.insert("end", s.get("name", ""))
            reset_dims_neutral()
            update_preview()

        def on_sub(_e=None):
            sel = sub_lb.curselection()
            if not sel:
                return
            cat = current["cat"]
            subs = library.get(cat, {}).get("subs", [])
            sub = subs[sel[0]]
            current["sub"] = sub
            refresh_dimension_marks()

        def generate():
            sub = current.get("sub")
            if not sub:
                status.config(text="请先选择一个小类")
                return
            cat = current["cat"]
            scen = selected_names(scenario_lb, scenarios)
            meth = selected_names(method_lb, methods)
            task = selected_names(task_lb, tasks)
            mod = selected_names(modality_lb, modalities)
            venues = [v["name"] for v in recommend_venues(
                cat, sub.get("name", ""), scen[0] if scen else "",
                meth, task, mod, top=8)]
            relation = evaluate_combo(current.get("profile", "ml_method"),
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, relations)
            if relation["score"] < 40:
                status.config(text="✘ 组合相关度过低（" + str(relation["score"])
                              + "%），请先按推荐组合调整")
                return
            prompt = taxonomy_prompt(cat, sub.get("name", ""), sub, venues,
                                     scen[0] if scen else "通用",
                                     meth, task, mod, taxonomy["sources"],
                                     relation=relation)
            mem = load_research_memory()
            mem.setdefault("directions", []).append({
                "time": datetime.datetime.now().isoformat(timespec="minutes"),
                "category": cat, "direction": sub.get("name", ""),
                "scenario": scen, "methods": meth, "tasks": task,
                "modalities": mod, "suggestions": sub.get("keywords", []),
                "relation_profile": relation["profile"],
                "relation_score": relation["score"],
            })
            save_research_memory(mem)
            self._copy_prompt("多维方向调研", prompt)
            status.config(text="✔ 提示词已复制（相关度 " + str(relation["score"]) + "%）")

        def show_recommendations():
            sub = current.get("sub")
            if not sub:
                status.config(text="请先选择研究领域")
                return
            cat = current["cat"]
            scen = selected_names(scenario_lb, scenarios)
            meth = selected_names(method_lb, methods)
            task = selected_names(task_lb, tasks)
            mod = selected_names(modality_lb, modalities)
            relation = evaluate_combo(current.get("profile", "ml_method"),
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, relations)
            self.show_advisor_recommendations(cat, sub.get("name", ""),
                                              scen[0] if scen else "",
                                              meth, task, mod, relation)

        def show_venues():
            sub = current.get("sub")
            if not sub:
                status.config(text="请先选择研究领域")
                return
            cat = current["cat"]
            scen = selected_names(scenario_lb, scenarios)
            meth = selected_names(method_lb, methods)
            task = selected_names(task_lb, tasks)
            mod = selected_names(modality_lb, modalities)
            relation = evaluate_combo(current.get("profile", "ml_method"),
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, relations)
            self.show_venue_recommendations(cat, sub.get("name", ""),
                                            scen[0] if scen else "",
                                            meth, task, mod, relation)

        def add_custom():
            cat = current.get("cat") or simpledialog.askstring(
                "自定义方向", "输入大类（可直接新建）：", parent=dlg) or "自定义"
            name = simpledialog.askstring("自定义方向", "输入小类名称：", parent=dlg)
            if not name:
                return
            kw = simpledialog.askstring("自定义方向", "英文关键词（逗号分隔，可留空）：",
                                        parent=dlg) or ""
            keywords = [x.strip() for x in kw.split(",") if x.strip()]
            add_custom_direction(cat, name.strip(), keywords)
            nonlocal library, taxonomy
            taxonomy = load_research_taxonomy()
            library = taxonomy["categories"]
            cats[:] = sorted(library.keys())
            refresh_cats()
            try:
                idx = cats.index(cat)
                cat_lb.selection_set(idx)
                on_cat()
                names = [s.get("name") for s in library[cat].get("subs", [])]
                if name in names:
                    j = names.index(name)
                    sub_lb.selection_set(j)
                    on_sub()
            except Exception:
                pass
            status.config(text="✔ 已添加自定义方向")

        def open_config():
            try:
                os.startfile(str(DIRECTION_LIBRARY))
                os.startfile(str(RESEARCH_TAXONOMY))
            except Exception as exc:
                status.config(text="打开失败: " + str(exc))

        cat_lb.bind("<<ListboxSelect>>", on_cat)
        sub_lb.bind("<<ListboxSelect>>", on_sub)
        for lb in (scenario_lb, method_lb, task_lb, modality_lb):
            lb.bind("<<ListboxSelect>>", update_preview)
        self._btn(btns, "按推荐组合", refresh_dimension_marks).pack(side="left")
        self._btn(btns, "推荐导师/院校", show_recommendations).pack(side="left", padx=(8, 0))
        self._btn(btns, "推荐期刊/会议", show_venues).pack(side="left", padx=(8, 0))
        self._btn(btns, "生成并复制提示词", generate, accent=True).pack(side="left")
        self._btn(btns, "添加自定义方向", add_custom).pack(side="left", padx=(8, 0))
        self._btn(btns, "打开配置（方向+维度）", open_config).pack(side="left", padx=(8, 0))
        self._btn(btns, "关闭", dlg.destroy).pack(side="left", padx=(8, 0))
        refresh_cats()
        reset_dims_neutral()

    def run_direction_audit(self):
        self.status.set("> 正在逐条审计全部计算机方向，请稍候…")
        script = HERE / "test_direction_coverage.py"
        report = EXPORT_DIR / "direction_coverage_report.md"

        def work():
            try:
                proc = subprocess.run(
                    [_pythonw_exe(), "-X", "utf8", str(script)],
                    capture_output=True,
                    timeout=180,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    **_hidden_kwargs(),
                )
                if proc.returncode != 0:
                    detail = _decode_bytes(proc.stdout or proc.stderr)[-300:]
                    self.root.after(0, lambda: self.status.set(
                        "✘ 方向覆盖审计发现缺口: " + detail))
                    return
                self.root.after(0, lambda: self.status.set("✔ 全部方向审计通过，正在打开报告"))
                self.root.after(0, lambda: os.startfile(str(report)))
            except Exception as exc:
                self.root.after(0, lambda: self.status.set("✘ 方向审计失败: " + str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def show_advisor_recommendations(self, category, field, scenario,
                                     methods, tasks, modalities, relation=None,
                                     province=None):
        advisors = recommend_advisors(category, field, scenario, methods,
                                      tasks, modalities, top=8, province=province)
        institutions = recommend_institutions(category, field, scenario, methods,
                                              tasks, modalities, top=6, province=province)
        urls = _institution_urls()
        dlg = tk.Toplevel(self.root)
        dlg.title("科研工作台 · 导师与院校推荐")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry("880x660+%d+%d" % (self.root.winfo_x() + 40, self.root.winfo_y() + 40))
        tk.Label(dlg, text="◆ 导师与院校推荐", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        combo = category + " / " + field
        if scenario:
            combo += "  ·  " + scenario
        if relation:
            combo += "  ·  相关度 " + str(relation.get("score", 0)) + "%"
        tk.Label(dlg, text=combo, bg=BG, fg=MUT, font=FONT_XS,
                 wraplength=840, justify="left").pack(anchor="w", padx=14)
        body = tk.Frame(dlg, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(8, 4))
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        tk.Label(left, text="导师/课题组（匹配度）", bg=BG, fg=MUT,
                 font=FONT_XS).pack(anchor="w")
        tk.Label(right, text="院校/机构（匹配度）", bg=BG, fg=MUT,
                 font=FONT_XS).pack(anchor="w")
        adv_sb = tk.Scrollbar(left)
        adv_lb = tk.Listbox(left, height=11, bg=CARD, fg=TXT, selectbackground=LINE,
                            selectforeground=ACCENT, relief="flat",
                            highlightbackground=LINE, highlightthickness=1,
                            font=FONT_XS, yscrollcommand=adv_sb.set)
        adv_sb.config(command=adv_lb.yview)
        adv_sb.pack(side="right", fill="y")
        adv_lb.pack(side="left", fill="both", expand=True)
        inst_sb = tk.Scrollbar(right)
        inst_lb = tk.Listbox(right, height=11, bg=CARD, fg=TXT, selectbackground=LINE,
                             selectforeground=ACCENT, relief="flat",
                             highlightbackground=LINE, highlightthickness=1,
                             font=FONT_XS, yscrollcommand=inst_sb.set)
        inst_sb.config(command=inst_lb.yview)
        inst_sb.pack(side="right", fill="y")
        inst_lb.pack(side="left", fill="both", expand=True)
        details = tk.Text(dlg, height=7, wrap="word", bg=CARD, fg=TXT,
                          relief="flat", highlightbackground=LINE, highlightthickness=1,
                          font=FONT_XS, padx=10, pady=8)
        details.pack(fill="x", padx=14)
        details.config(state="disabled")
        details.tag_config("link", foreground=ACCENT, underline=True)
        state = {"advisor": None, "institution": None, "url": "", "link_label": ""}

        def advisor_link(a):
            homepage = (a.get("homepage") or "").strip()
            if homepage.startswith(("http://", "https://")):
                return homepage, "打开导师个人主页"
            institution_url = urls.get(a.get("institution", ""), "")
            if institution_url:
                return institution_url, "打开所属院校官网"
            query = quote_plus(
                (a.get("name", "") + " " + a.get("institution", "")).strip())
            return (f"https://dblp.org/search?q={query}",
                    "DBLP 作者检索")

        def open_state_link(_event=None):
            url = state.get("url", "")
            if url:
                webbrowser.open(url)
            else:
                self.status.set("没有可打开的链接，请按机构官网核验")

        for item in advisors:
            a = item["advisor"]
            url, _label = advisor_link(a)
            adv_lb.insert("end", str(item["score"]) + " | " + a.get("name", "")
                          + " · " + institution_zh(a.get("institution", ""))
                          + ("  ↗" if url else ""))
        for item in institutions:
            inst_lb.insert("end", str(item["score"]) + " | "
                           + item.get("institution_zh", item.get("institution", ""))
                           + ("  ↗" if item.get("url") else ""))

        def show_advisor(_e=None):
            sel = adv_lb.curselection()
            if not sel:
                return
            item = advisors[sel[0]]
            a = item["advisor"]
            state["advisor"] = a
            state["institution"] = None
            url, link_label = advisor_link(a)
            state["url"] = url
            state["link_label"] = link_label
            details.config(state="normal")
            details.delete("1.0", "end")
            details.insert("1.0", "导师: " + a.get("name", "")
                           + "\n机构: " + institution_zh(a.get("institution", ""))
                           + "\n英文原名: " + a.get("institution", "")
                           + "\n课题组: " + a.get("lab", "")
                           + "\n领域: " + " / ".join(a.get("fields", []))
                           + "\n关键词: " + ", ".join(a.get("keywords", []))
                           + "\n匹配理由: " + " / ".join(item.get("reasons", [])))
            if url:
                details.insert("end", "\n↗ " + link_label, ("link",))
            else:
                details.insert("end", "\n暂无直接链接，请按机构官网核验")
            details.config(state="disabled")

        def show_institution(_e=None):
            sel = inst_lb.curselection()
            if not sel:
                return
            item = institutions[sel[0]]
            state["institution"] = item
            state["advisor"] = None
            state["url"] = item.get("url", "")
            state["link_label"] = "打开院校官网"
            details.config(state="normal")
            details.delete("1.0", "end")
            details.insert("1.0", "机构: "
                           + item.get("institution_zh", item.get("institution", ""))
                           + "\n英文原名: " + item.get("institution", "")
                           + "\n匹配度: " + str(item.get("score", 0)) + "%"
                           + "\n代表导师: " + " / ".join(item.get("best_advisors", []))
                           + "\n研究领域: "
                           + (item.get("areas_zh") or "以该校公开主题为准"))
            if item.get("url"):
                details.insert("end", "\n↗ 打开院校官网", ("link",))
            else:
                details.insert("end", "\n暂无官网链接，请按机构名称检索核验")
            details.config(state="disabled")

        def open_page():
            open_state_link()

        def copy_list():
            lines = ["导师与院校推荐", "方向: " + combo, "", "导师/课题组:"]
            for item in advisors:
                a = item["advisor"]
                advisor_url, _label = advisor_link(a)
                lines.append("- " + str(item["score"]) + " | " + a.get("name", "")
                             + " | " + institution_zh(a.get("institution", ""))
                             + "（" + a.get("institution", "") + "）"
                             + " | " + a.get("lab", "")
                             + " | " + " / ".join(item.get("reasons", []))
                             + (" | " + advisor_url if advisor_url else ""))
            lines.append("")
            lines.append("院校/机构:")
            for item in institutions:
                lines.append("- " + str(item["score"]) + " | "
                             + item.get("institution_zh", item.get("institution", ""))
                             + "（" + item.get("institution", "") + "）"
                             + " | " + " / ".join(item.get("best_advisors", []))
                             + (" | " + item.get("url", "")
                                if item.get("url") else ""))
            lines.append("")
            lines.append("说明: 基于公开研究方向匹配，不代表招生名额或导师意愿；请以官网核验。")
            self._clip_copy("\n".join(lines))
            self.status.set("✔ 推荐清单已复制")

        adv_lb.bind("<<ListboxSelect>>", show_advisor)
        inst_lb.bind("<<ListboxSelect>>", show_institution)
        details.tag_bind("link", "<Button-1>", open_state_link)
        adv_lb.bind("<Double-Button-1>", lambda e: (show_advisor(), open_state_link()))
        inst_lb.bind("<Double-Button-1>", lambda e: (show_institution(), open_state_link()))
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))
        self._btn(btns, "打开已选链接", open_page, accent=True).pack(side="left")
        self._btn(btns, "复制推荐清单", copy_list).pack(side="left", padx=(8, 0))
        self._btn(btns, "关闭", dlg.destroy).pack(side="left", padx=(8, 0))
        tk.Label(dlg, text="基于公开研究方向匹配；不代表招生名额、导师意愿或最新隶属关系，请以机构官网核验。",
                 bg=BG, fg=MUT, font=("Consolas", 7)).pack(anchor="w", padx=14, pady=(0, 8))
        if not advisors and not institutions:
            details.config(state="normal")
            details.insert("1.0", "暂无匹配结果，请调整领域或维度。")
            details.config(state="disabled")

    def show_venue_recommendations(self, category, field, scenario,
                                   methods, tasks, modalities, relation=None):
        rows = recommend_venues(category, field, scenario, methods, tasks,
                                modalities, top=10)
        dlg = tk.Toplevel(self.root)
        dlg.title("科研工作台 · 期刊/会议推荐")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry("720x540+%d+%d" % (self.root.winfo_x() + 60, self.root.winfo_y() + 60))
        tk.Label(dlg, text="◆ 期刊/会议推荐", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        combo = (category or "未分类") + " / " + (field or "未分类")
        if scenario:
            combo += " · " + scenario
        if relation:
            combo += " · 方向相关度 " + str(relation.get("score", 0)) + "%"
        tk.Label(dlg, text=combo, bg=BG, fg=MUT, font=FONT_XS,
                 wraplength=680, justify="left").pack(anchor="w", padx=14)
        box = tk.Frame(dlg, bg=BG)
        box.pack(fill="both", expand=True, padx=14, pady=(8, 4))
        sb = tk.Scrollbar(box)
        lb = tk.Listbox(box, height=10, bg=CARD, fg=TXT, selectbackground=LINE,
                        selectforeground=ACCENT, relief="flat",
                        highlightbackground=LINE, highlightthickness=1,
                        font=FONT_XS, yscrollcommand=sb.set)
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        details = tk.Text(dlg, height=6, wrap="word", bg=CARD, fg=TXT,
                          relief="flat", highlightbackground=LINE, highlightthickness=1,
                          font=FONT_XS, padx=10, pady=8)
        details.pack(fill="x", padx=14)
        details.config(state="disabled")
        details.tag_config("link", foreground=ACCENT, underline=True)
        state = {"venue": None, "url": ""}
        for v in rows:
            lb.insert("end", str(v.get("score", 0)) + " | " + v.get("name", "")
                      + " | " + v.get("type", "") + "  ↗")

        def on_select(_e=None):
            sel = lb.curselection()
            if not sel:
                return
            v = rows[sel[0]]
            state["venue"] = v
            state["url"] = v.get("url", "")
            details.config(state="normal")
            details.delete("1.0", "end")
            details.insert("1.0", "名称: " + v.get("name", "")
                           + "\n类型: " + v.get("type", "")
                           + "\n匹配理由: " + " / ".join(v.get("reasons", []))
                           + "\n请以官方 CFP/期刊 scope 为准。")
            if state["url"]:
                details.insert(
                    "end",
                    "\n↗ " + v.get("link_label", "打开官方页面"),
                    ("link",),
                )
            details.config(state="disabled")

        def open_selected():
            if state["url"]:
                webbrowser.open(state["url"])
            else:
                self.status.set("该期刊/会议暂无可用链接")

        def copy_list():
            lines = ["期刊/会议推荐", "方向: " + combo, ""]
            for v in rows:
                lines.append("- " + v.get("name", "") + " | " + v.get("type", "")
                             + " | " + " / ".join(v.get("reasons", []))
                             + " | " + v.get("url", ""))
            lines.append("")
            lines.append("请以官方 CFP/期刊 scope 核验。")
            self._clip_copy("\n".join(lines))
            self.status.set("✔ 期刊/会议推荐已复制")

        lb.bind("<<ListboxSelect>>", on_select)
        details.tag_bind("link", "<Button-1>", lambda e: open_selected())
        lb.bind("<Double-Button-1>", lambda e: (on_select(), open_selected()))
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))
        self._btn(btns, "打开已选链接", open_selected, accent=True).pack(side="left")
        self._btn(btns, "复制推荐清单", copy_list).pack(side="left", padx=(8, 0))
        self._btn(btns, "关闭", dlg.destroy).pack(side="left", padx=(8, 0))
        tk.Label(dlg, text="venue 匹配基于领域、场景、方法与任务；不代表投稿录用判断。",
                 bg=BG, fg=MUT, font=("Consolas", 7)).pack(anchor="w", padx=14, pady=(0, 8))
        if not rows:
            details.config(state="normal")
            details.insert("1.0", "暂无匹配 venue，请调整方向或维度。")
            details.config(state="disabled")

    def open_venue_dialog(self):
        taxonomy = load_research_taxonomy()
        relations = load_research_relations()
        mem = load_research_memory()
        stored = mem.get("profile", {})
        cats = sorted(taxonomy["categories"].keys())
        cat_var = tk.StringVar(value=stored.get("category") or (cats[0] if cats else "人工智能"))
        field_var = tk.StringVar(value=stored.get("field") or "多模态学习")
        dlg = tk.Toplevel(self.root)
        dlg.title("科研工作台 · 期刊/会议推荐")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry("740x560+%d+%d" % (self.root.winfo_x() + 60, self.root.winfo_y() + 50))
        tk.Label(dlg, text="◆ 期刊/会议推荐", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Label(dlg, text="输入研究方向/内容，自动识别领域后匹配会议与期刊；已覆盖领域主 venue 和方向专项规则。",
                 bg=BG, fg=MUT, font=FONT_XS, wraplength=700, justify="left").pack(anchor="w", padx=14)
        text = tk.Text(dlg, height=5, wrap="word", bg=CARD, fg=TXT,
                       relief="flat", highlightbackground=LINE, highlightthickness=1,
                       font=FONT_XS, padx=10, pady=8)
        text.pack(fill="x", padx=14, pady=(8, 6))
        text.insert("1.0", stored.get("text") or
                    "RGB-T 多模态目标检测、跨模态融合、频域/Mamba 方法。")
        opts = tk.Frame(dlg, bg=BG)
        opts.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(opts, text="大类", bg=BG, fg=MUT, font=FONT_XS).grid(row=0, column=0, sticky="w")
        cat_menu = tk.OptionMenu(opts, cat_var, *cats)
        cat_menu.config(bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                        relief="flat", bd=0, highlightthickness=0, font=FONT_XS)
        cat_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                activeforeground=TXT, bd=0)
        cat_menu.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        tk.Label(opts, text="研究领域", bg=BG, fg=MUT, font=FONT_XS).grid(row=1, column=0, sticky="w")
        field_menu = tk.OptionMenu(opts, field_var, "")
        field_menu.config(bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                          relief="flat", bd=0, highlightthickness=0, font=FONT_XS)
        field_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                  activeforeground=TXT, bd=0)
        field_menu.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        opts.grid_columnconfigure(1, weight=1)

        def update_fields(*_args):
            cat = cat_var.get()
            names = [s.get("name", "") for s in taxonomy["categories"].get(cat, {}).get("subs", [])]
            menu = field_menu["menu"]
            menu.delete(0, "end")
            for name in names:
                menu.add_command(label=name, command=lambda v=name: field_var.set(v))
            if field_var.get() not in names:
                field_var.set(names[0] if names else "未分类")

        cat_var.trace_add("write", lambda *a: update_fields())
        update_fields()
        status = tk.Label(dlg, text="", bg=BG, fg=MUT, font=FONT_XS, anchor="w")
        status.pack(fill="x", padx=14, pady=(2, 2))
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))

        def auto_detect():
            content = text.get("1.0", "end").strip()
            if not content:
                status.config(text="请先输入研究方向或内容")
                return
            cat, field, confidence = infer_category_field(content)
            if not cat or not field:
                status.config(text="未识别这个方向。请手动选择大类/领域，或在方向库补充")
                return
            cat_var.set(cat)
            update_fields()
            field_var.set(field)
            status.config(text="✔ 识别为 " + cat + " / " + field
                          + "（置信度 " + str(confidence) + "%）")

        def save_profile():
            content = text.get("1.0", "end").strip()
            if not content:
                status.config(text="请输入研究内容")
                return
            mem = load_research_memory()
            mem["profile"] = {"text": content, "category": cat_var.get(),
                              "field": field_var.get(),
                              "updated": datetime.datetime.now().isoformat(timespec="minutes")}
            save_research_memory(mem)
            status.config(text="✔ 研究画像已保存")

        def find():
            content = text.get("1.0", "end").strip()
            if not content:
                status.config(text="请输入研究方向或内容")
                return
            cat = cat_var.get()
            field = field_var.get()
            if not field or field == "未分类":
                cat, field, _conf = infer_category_field(content)
                if not cat or not field:
                    status.config(text="未识别这个方向，请先手动选择领域")
                    return
                cat_var.set(cat)
                update_fields()
                field_var.set(field)
            tokens = _translate_direction(content)
            profile_key = field_profile(cat, field, relations)
            profile = relations.get("profiles", {}).get(profile_key, {})
            scen = profile.get("scenarios", [])[:1]
            meth = tokens + [m for m in profile.get("methods", [])[:2] if m not in tokens]
            task = profile.get("tasks", [])[:2]
            mod = profile.get("modalities", [])[:2]
            relation = evaluate_combo(profile_key,
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, relations)
            mem = load_research_memory()
            mem["profile"] = {"text": content, "category": cat, "field": field,
                              "updated": datetime.datetime.now().isoformat(timespec="minutes")}
            save_research_memory(mem)
            self.show_venue_recommendations(cat, field, scen[0] if scen else "",
                                            meth, task, mod, relation)
            status.config(text="✔ 已生成期刊/会议推荐（画像已保存）")

        self._btn(btns, "自动识别方向", auto_detect).pack(side="left")
        self._btn(btns, "查找期刊/会议", find, accent=True).pack(side="left", padx=(8, 0))
        self._btn(btns, "保存研究画像", save_profile).pack(side="left", padx=(8, 0))
        self._btn(btns, "关闭", dlg.destroy).pack(side="left", padx=(8, 0))
        tk.Label(dlg, text="推荐基于方向/场景/方法与任务；请以官方 CFP 与期刊 scope 为准。",
                 bg=BG, fg=MUT, font=("Consolas", 7)).pack(anchor="w", padx=14, pady=(0, 8))

    def open_advisor_dialog(self):
        taxonomy = load_research_taxonomy()
        relations = load_research_relations()
        mem = load_research_memory()
        stored = mem.get("profile", {})
        cats = sorted(taxonomy["categories"].keys())
        cat_var = tk.StringVar(value=stored.get("category") or (cats[0] if cats else "人工智能"))
        field_var = tk.StringVar(value=stored.get("field") or "多模态学习")
        dlg = tk.Toplevel(self.root)
        dlg.title("科研工作台 · 导师/院校推荐")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry("760x600+%d+%d" % (self.root.winfo_x() + 50, self.root.winfo_y() + 40))
        tk.Label(dlg, text="◆ 导师/院校推荐", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Label(dlg, text="输入你的研究方向/内容，自动识别领域后匹配导师与院校；画像会保存在 research_memory.json。",
                 bg=BG, fg=MUT, font=FONT_XS, wraplength=720, justify="left").pack(anchor="w", padx=14)
        cn_institutions = load_institutions_cn()
        provinces = sorted({i.get("region") for i in cn_institutions if i.get("region")})
        province_pairs = [(name, province_zh(name)) for name in provinces]
        province_labels = [label for _name, label in province_pairs]
        coverage_label = tk.Label(
            dlg,
            text="索引: " + str(len(load_advisors())) + " 位研究者 / "
            + str(len(cn_institutions)) + " 所院校 / " + str(len(provinces))
            + " 个省级地区（含 OpenAlex 公开索引）",
            bg=BG, fg=OKC, font=FONT_XS, anchor="w")
        coverage_label.pack(fill="x", padx=14, pady=(2, 0))
        self._advisor_coverage_label = coverage_label
        text = tk.Text(dlg, height=5, wrap="word", bg=CARD, fg=TXT,
                       relief="flat", highlightbackground=LINE, highlightthickness=1,
                       font=FONT_XS, padx=10, pady=8)
        text.pack(fill="x", padx=14, pady=(8, 6))
        text.insert("1.0", stored.get("text") or
                    "RGB-T 多模态目标检测、跨模态融合、频域/Mamba 方法，关注小目标与鲁棒性。")
        opts = tk.Frame(dlg, bg=BG)
        opts.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(opts, text="大类", bg=BG, fg=MUT, font=FONT_XS).grid(row=0, column=0, sticky="w")
        cat_menu = tk.OptionMenu(opts, cat_var, *cats)
        cat_menu.config(bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                        relief="flat", bd=0, highlightthickness=0, font=FONT_XS)
        cat_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                activeforeground=TXT, bd=0)
        cat_menu.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        tk.Label(opts, text="研究领域", bg=BG, fg=MUT, font=FONT_XS).grid(row=1, column=0, sticky="w")
        field_menu = tk.OptionMenu(opts, field_var, "")
        field_menu.config(bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                          relief="flat", bd=0, highlightthickness=0, font=FONT_XS)
        field_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                  activeforeground=TXT, bd=0)
        field_menu.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        province_var = tk.StringVar(value="全部省份")
        tk.Label(opts, text="省份", bg=BG, fg=MUT, font=FONT_XS).grid(row=2, column=0, sticky="w")
        province_menu = tk.OptionMenu(opts, province_var, *(["全部省份"] + province_labels))
        province_menu.config(bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                             relief="flat", bd=0, highlightthickness=0, font=FONT_XS)
        province_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                     activeforeground=TXT, bd=0)
        province_menu.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=2)
        opts.grid_columnconfigure(1, weight=1)

        def update_fields(*_args):
            cat = cat_var.get()
            names = [s.get("name", "") for s in taxonomy["categories"].get(cat, {}).get("subs", [])]
            menu = field_menu["menu"]
            menu.delete(0, "end")
            for name in names:
                menu.add_command(label=name, command=lambda v=name: field_var.set(v))
            if field_var.get() not in names:
                field_var.set(names[0] if names else "未分类")

        cat_var.trace_add("write", lambda *a: update_fields())
        update_fields()
        status = tk.Label(dlg, text="", bg=BG, fg=MUT, font=FONT_XS, anchor="w")
        status.pack(fill="x", padx=14, pady=(2, 2))
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))

        def auto_detect():
            content = text.get("1.0", "end").strip()
            if not content:
                status.config(text="请先输入研究方向或内容")
                return
            cat, field, confidence = infer_category_field(content)
            if not cat or not field:
                status.config(text="未识别这个方向。请手动选择大类/领域，或在方向库中补充")
                return
            cat_var.set(cat)
            update_fields()
            field_var.set(field)
            status.config(text="✔ 识别为 " + cat + " / " + field
                          + "（置信度 " + str(confidence) + "%）")

        def save_profile():
            content = text.get("1.0", "end").strip()
            if not content:
                status.config(text="请输入研究内容")
                return
            mem = load_research_memory()
            mem["profile"] = {"text": content, "category": cat_var.get(),
                              "field": field_var.get(),
                              "updated": datetime.datetime.now().isoformat(timespec="minutes")}
            save_research_memory(mem)
            status.config(text="✔ 研究画像已保存")

        def find():
            content = text.get("1.0", "end").strip()
            if not content:
                status.config(text="请输入研究方向或内容")
                return
            cat = cat_var.get()
            field = field_var.get()
            if not field or field == "未分类":
                cat, field, _conf = infer_category_field(content)
                if not cat or not field:
                    status.config(text="未识别这个方向。请先手动选择大类/研究领域")
                    return
                cat_var.set(cat)
                update_fields()
                field_var.set(field)
            if not field or field == "未分类":
                status.config(text="请选择研究领域后再查找")
                return
            tokens = _translate_direction(content)
            profile_key = field_profile(cat, field, relations)
            profile = relations.get("profiles", {}).get(profile_key, {})
            scen = profile.get("scenarios", [])[:1]
            meth = tokens + [m for m in profile.get("methods", [])[:2] if m not in tokens]
            task = profile.get("tasks", [])[:2]
            mod = profile.get("modalities", [])[:2]
            relation = evaluate_combo(profile_key,
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, relations)
            mem = load_research_memory()
            mem["profile"] = {"text": content, "category": cat, "field": field,
                              "updated": datetime.datetime.now().isoformat(timespec="minutes")}
            save_research_memory(mem)
            selected_province = province_var.get()
            province_value = next(
                (name for name, label in province_pairs if label == selected_province),
                "全部省份",
            )
            self.show_advisor_recommendations(cat, field, scen[0] if scen else "",
                                              meth, task, mod, relation,
                                              province=province_value)
            status.config(text="✔ 已生成推荐（画像已保存）")

        def find_venues():
            content = text.get("1.0", "end").strip()
            if not content:
                status.config(text="请输入研究方向或内容")
                return
            cat = cat_var.get()
            field = field_var.get()
            if not field or field == "未分类":
                cat, field, _conf = infer_category_field(content)
                if not cat or not field:
                    status.config(text="未识别这个方向，请先手动选择领域")
                    return
                cat_var.set(cat)
                update_fields()
                field_var.set(field)
            tokens = _translate_direction(content)
            profile_key = field_profile(cat, field, relations)
            profile = relations.get("profiles", {}).get(profile_key, {})
            scen = profile.get("scenarios", [])[:1]
            meth = tokens + [m for m in profile.get("methods", [])[:2] if m not in tokens]
            task = profile.get("tasks", [])[:2]
            mod = profile.get("modalities", [])[:2]
            relation = evaluate_combo(profile_key,
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, relations)
            self.show_venue_recommendations(cat, field, scen[0] if scen else "",
                                            meth, task, mod, relation)
            status.config(text="✔ 已生成期刊/会议推荐")

        def update_index():
            self._run_tool("advisor_update", "更新全国导师索引",
                           lambda progress: run_advisor_update(400, 30, progress))
            status.config(text="● 后台更新中（约数分钟），完成后显示结果")

        self._btn(btns, "自动识别方向", auto_detect).pack(side="left")
        self._btn(btns, "查找导师/院校", find, accent=True).pack(side="left", padx=(8, 0))
        self._btn(btns, "推荐期刊/会议", find_venues).pack(side="left", padx=(8, 0))
        self._btn(btns, "保存研究画像", save_profile).pack(side="left", padx=(8, 0))
        self._btn(btns, "更新全国导师库", update_index).pack(side="left", padx=(8, 0))
        self._btn(btns, "关闭", dlg.destroy).pack(side="left", padx=(8, 0))
        tk.Label(dlg, text="推荐基于公开研究方向匹配，不代表招生名额或导师意愿；请以机构官网核验。",
                 bg=BG, fg=MUT, font=("Consolas", 7)).pack(anchor="w", padx=14, pady=(0, 8))

    def open_ideas_dialog(self, mode="apply"):
        if mode == "review":
            self.open_idea_review_dialog()
        else:
            self.open_idea_library_dialog()

    def open_idea_library_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("科研工作台 · 创新点组合管理")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry("1100x780+%d+%d" % (
            max(20, self.root.winfo_x() - 160),
            max(20, self.root.winfo_y() + 10),
        ))
        tk.Label(dlg, text="◆ 创新点库 · 组合管理与阶段推进", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(
                     anchor="w", padx=14, pady=(12, 2))
        tk.Label(
            dlg,
            text="这里管理创新点组合：编辑、筛选、标注阶段与二级机制、查相关工作；"
                 "需要独立判断时再送入“选题体检”。",
            bg=BG, fg=MUT, font=FONT_XS, wraplength=1060, justify="left",
        ).pack(anchor="w", padx=14)
        taxonomy = load_research_taxonomy()
        relations = load_research_relations()
        cats = sorted(taxonomy["categories"].keys())
        cat_var = tk.StringVar(value=cats[0] if cats else "未分类")
        field_var = tk.StringVar(value="")
        type_var = tk.StringVar(value="方法创新")
        stage_var = tk.StringVar(value=IDEA_STAGES[0])
        mechanism_var = tk.StringVar(value=IDEA_MECHANISMS[0])
        evidence_var = tk.StringVar(value=IDEA_EVIDENCE_TYPES[0])
        risk_var = tk.StringVar(value=IDEA_RISK_TYPES[0])
        filter_var = tk.StringVar(value="全部类型")
        stage_filter_var = tk.StringVar(value="全部阶段")
        ideas = load_research_memory().get("ideas", [])
        selected_id = {"value": None}
        filtered = {"rows": []}

        body = tk.Frame(dlg, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(8, 4))
        left = tk.Frame(body, bg=BG, width=370)
        left.pack(side="left", fill="both", padx=(0, 10))
        left.pack_propagate(False)
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="我的创新点", bg=BG, fg=MUT,
                 font=FONT_XS).pack(anchor="w")
        search_e = tk.Entry(left, bg=CARD, fg=TXT, insertbackground=TXT,
                            relief="flat", highlightbackground=LINE,
                            highlightthickness=1, font=FONT_XS)
        search_e.pack(fill="x", pady=(3, 5), ipady=4)
        search_e.insert(0, "搜索标题、描述、大类或领域")
        search_e.config(fg=MUT)
        filters = tk.Frame(left, bg=BG)
        filters.pack(fill="x", pady=(0, 5))
        type_filter = tk.OptionMenu(filters, filter_var, "全部类型", *IDEA_TYPES)
        stage_filter = tk.OptionMenu(
            filters, stage_filter_var, "全部阶段", *IDEA_STAGES)
        for menu in (type_filter, stage_filter):
            menu.config(bg=CARD, fg=TXT, activebackground=LINE,
                        activeforeground=TXT, relief="flat", bd=0,
                        highlightthickness=0, font=FONT_XS)
            menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                activeforeground=TXT, bd=0)
        type_filter.pack(side="left", fill="x", expand=True, padx=(0, 4))
        stage_filter.pack(side="left", fill="x", expand=True, padx=(4, 0))
        idea_sb = tk.Scrollbar(left)
        idea_lb = tk.Listbox(
            left, height=24, bg=CARD, fg=TXT, selectbackground=LINE,
            selectforeground=ACCENT, relief="flat",
            highlightbackground=LINE, highlightthickness=1,
            font=FONT_XS, yscrollcommand=idea_sb.set, exportselection=False,
        )
        idea_sb.config(command=idea_lb.yview)
        idea_sb.pack(side="right", fill="y")
        idea_lb.pack(side="left", fill="both", expand=True)
        list_count = tk.Label(left, text="", bg=BG, fg=MUT,
                              font=FONT_XS, anchor="w")
        list_count.pack(fill="x", pady=(3, 0))

        form = tk.Frame(right, bg=BG)
        form.pack(fill="x")
        tk.Label(form, text="大类", bg=BG, fg=MUT,
                 font=FONT_XS).grid(row=0, column=0, sticky="w")
        cat_menu = tk.OptionMenu(form, cat_var, *cats)
        cat_menu.config(bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                        relief="flat", bd=0, highlightthickness=0, font=FONT_XS)
        cat_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                activeforeground=TXT, bd=0)
        cat_menu.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        tk.Label(form, text="研究领域", bg=BG, fg=MUT, font=FONT_XS).grid(row=1, column=0, sticky="w")
        field_menu = tk.OptionMenu(form, field_var, "")
        field_menu.config(bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                          relief="flat", bd=0, highlightthickness=0, font=FONT_XS)
        field_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                  activeforeground=TXT, bd=0)
        field_menu.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        tk.Label(form, text="创新类型", bg=BG, fg=MUT, font=FONT_XS).grid(row=2, column=0, sticky="w")
        type_menu = tk.OptionMenu(form, type_var, "结构创新", "方法创新", "范式创新",
                                  "应用创新", "系统创新", "评测创新")
        type_menu.config(bg=CARD, fg=TXT, activebackground=LINE, activeforeground=TXT,
                         relief="flat", bd=0, highlightthickness=0, font=FONT_XS)
        type_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                 activeforeground=TXT, bd=0)
        type_menu.grid(row=2, column=1, sticky="ew", padx=(8, 4), pady=2)
        tk.Label(form, text="阶段", bg=BG, fg=MUT,
                 font=FONT_XS).grid(row=2, column=2, sticky="w", padx=(4, 0))
        stage_menu = tk.OptionMenu(form, stage_var, *IDEA_STAGES)
        stage_menu.config(bg=CARD, fg=TXT, activebackground=LINE,
                          activeforeground=TXT, relief="flat", bd=0,
                          highlightthickness=0, font=FONT_XS)
        stage_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                  activeforeground=TXT, bd=0)
        stage_menu.grid(row=2, column=3, sticky="ew", padx=(4, 0), pady=2)
        tk.Label(form, text="二级机制", bg=BG, fg=MUT,
                 font=FONT_XS).grid(row=3, column=0, sticky="w")
        mechanism_menu = tk.OptionMenu(form, mechanism_var, *IDEA_MECHANISMS)
        tk.Label(form, text="目标证据", bg=BG, fg=MUT,
                 font=FONT_XS).grid(row=3, column=2, sticky="w", padx=(8, 0))
        evidence_menu = tk.OptionMenu(form, evidence_var, *IDEA_EVIDENCE_TYPES)
        tk.Label(form, text="主要风险", bg=BG, fg=MUT,
                 font=FONT_XS).grid(row=3, column=4, sticky="w", padx=(8, 0))
        risk_menu = tk.OptionMenu(form, risk_var, *IDEA_RISK_TYPES)
        for widget, column in (
                (mechanism_menu, 1), (evidence_menu, 3), (risk_menu, 5)):
            widget.config(bg=CARD, fg=TXT, activebackground=LINE,
                          activeforeground=TXT, relief="flat", bd=0,
                          highlightthickness=0, font=FONT_XS)
            widget["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                  activeforeground=TXT, bd=0)
            widget.grid(row=3, column=column, sticky="ew",
                        padx=(4, 0), pady=2)
        tk.Label(form, text="标题", bg=BG, fg=MUT,
                 font=FONT_XS).grid(row=4, column=0, sticky="w")
        title_e = tk.Entry(form, bg=CARD, fg=TXT, insertbackground=TXT,
                           relief="flat", highlightbackground=LINE,
                           highlightthickness=1, font=FONT_XS)
        title_e.grid(row=4, column=1, columnspan=5, sticky="ew",
                     padx=(8, 0), pady=2, ipady=4)
        tk.Label(form, text="场景", bg=BG, fg=MUT,
                 font=FONT_XS).grid(row=5, column=0, sticky="w")
        domain_e = tk.Entry(form, bg=CARD, fg=TXT, insertbackground=TXT,
                            relief="flat", highlightbackground=LINE,
                            highlightthickness=1, font=FONT_XS)
        domain_e.grid(row=5, column=1, columnspan=5, sticky="ew",
                      padx=(8, 0), pady=2, ipady=4)
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(3, weight=1)
        form.grid_columnconfigure(5, weight=1)
        tk.Label(form, text="描述", bg=BG, fg=MUT,
                 font=FONT_XS).grid(row=6, column=0, sticky="nw")
        desc_t = tk.Text(form, height=6, bg=CARD, fg=TXT, insertbackground=TXT,
                         relief="flat", highlightbackground=LINE, highlightthickness=1,
                         font=FONT_XS, padx=8, pady=6)
        desc_t.grid(row=6, column=1, columnspan=5, sticky="ew",
                    padx=(8, 0), pady=2)
        tk.Label(right, text="本地诊断（不是最终评审结论）", bg=BG, fg=MUT,
                 font=FONT_XS).pack(anchor="w", pady=(6, 2))
        diagnosis = tk.Text(
            right, height=13, wrap="word", bg=CARD, fg=TXT,
            relief="flat", highlightbackground=LINE, highlightthickness=1,
            font=FONT_XS, padx=10, pady=8, spacing1=2, spacing3=2,
        )
        diagnosis.pack(fill="both", expand=True)
        diagnosis.tag_config("h", foreground=ACCENT,
                             font=("Microsoft YaHei UI", 10, "bold"))
        diagnosis.tag_config("warn", foreground=WARN)
        diagnosis.tag_config("muted", foreground=MUT)
        diagnosis.tag_config("ok", foreground=OKC)
        diagnosis.config(state="disabled")

        def update_fields(*_args):
            cat = cat_var.get()
            names = [s.get("name", "") for s in taxonomy["categories"].get(cat, {}).get("subs", [])]
            menu = field_menu["menu"]
            menu.delete(0, "end")
            for name in names:
                menu.add_command(label=name, command=lambda v=name: field_var.set(v))
            field_var.set(names[0] if names else "未分类")

        cat_var.trace_add("write", lambda *a: update_fields())
        update_fields()
        status = tk.Label(dlg, text="", bg=BG, fg=MUT, font=FONT_XS, anchor="w")
        status.pack(fill="x", padx=14)
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))

        def idea_stage(it):
            return it.get("stage") or evaluate_idea_local(it)["stage"]

        def refresh_list(select_id=None):
            query = search_e.get().strip()
            if query == "搜索标题、描述、大类或领域":
                query = ""
            type_filter_value = filter_var.get()
            stage_filter_value = stage_filter_var.get()
            rows = []
            for it in ideas:
                stage = idea_stage(it)
                hay = " ".join([
                    it.get("title", ""), it.get("desc", ""),
                    it.get("category", ""), it.get("field", ""),
                ]).lower()
                if query and query.lower() not in hay:
                    continue
                if (type_filter_value != "全部类型"
                        and it.get("type") != type_filter_value):
                    continue
                if (stage_filter_value != "全部阶段"
                        and stage != stage_filter_value):
                    continue
                rows.append(it)
            filtered["rows"] = rows
            idea_lb.delete(0, "end")
            for index, it in enumerate(rows):
                assessment = evaluate_idea_local(it)
                stage = idea_stage(it)
                short_stage = stage.split()[0]
                title = it.get("title", "(未命名)")
                if len(title) > 27:
                    title = title[:24] + "…"
                idea_lb.insert(
                    "end",
                    "[L" + short_stage + " " + str(assessment["total"]) + "] "
                    + (it.get("type") or "方法创新")
                    + ("/" + it["mechanism_type"]
                       if it.get("mechanism_type")
                       and it.get("mechanism_type") != "未指定" else "")
                    + " | " + title,
                )
                if stage == "已放弃":
                    idea_lb.itemconfig(index, fg=MUT)
                elif assessment["total"] >= 70:
                    idea_lb.itemconfig(index, fg=OKC)
            list_count.config(text="显示 " + str(len(rows)) + " / "
                                   + str(len(ideas)) + " 条")
            if select_id:
                for index, it in enumerate(rows):
                    if it.get("id") == select_id:
                        idea_lb.selection_set(index)
                        idea_lb.activate(index)
                        on_select()
                        break

        def current_idea(require_content=True):
            title = title_e.get().strip()
            desc = desc_t.get("1.0", "end").strip()
            domain = domain_e.get().strip()
            category = cat_var.get().strip()
            field = field_var.get().strip()
            itype = type_var.get().strip()
            if require_content and (not title or not desc):
                status.config(text="请至少填写标题和描述")
                return None
            row = {
                "title": title, "desc": desc, "domain": domain,
                "category": category, "field": field, "type": itype,
                "stage": stage_var.get(),
                "mechanism_type": mechanism_var.get(),
                "evidence_type": evidence_var.get(),
                "risk_type": risk_var.get(),
            }
            if selected_id["value"]:
                row["id"] = selected_id["value"]
                old = next((x for x in ideas if x.get("id") == selected_id["value"]), {})
                if old.get("created"):
                    row["created"] = old["created"]
            return row

        def diagnose(update_stage=False, show_status=False):
            item = current_idea(require_content=False)
            assessment = evaluate_idea_local(item)
            if update_stage and not selected_id["value"] and stage_var.get() != "已放弃":
                stage_var.set(assessment["stage"])
            diagnosis.config(state="normal")
            diagnosis.delete("1.0", "end")
            diagnosis.insert(
                "end",
                "阶段: " + assessment["stage"]
                + "  ·  综合 " + str(assessment["total"])
                + "  ·  " + assessment["decision"] + "\n",
                ("h",),
            )
            diagnosis.insert(
                "end",
                "类型: " + type_var.get()
                + "  ·  类型匹配 " + str(assessment["scores"]["类型匹配"])
                + "  ·  更像 " + assessment["recommended_type"] + "\n",
            )
            diagnosis.insert(
                "end",
                "价值 " + str(assessment["scores"]["价值"])
                + " | 新颖 " + str(assessment["scores"]["新颖性"])
                + " | 机制 " + str(assessment["scores"]["机制清晰度"])
                + " | 证据 " + str(assessment["scores"]["证据准备度"])
                + " | 可行 " + str(assessment["scores"]["可行性"]) + "\n",
                ("muted",),
            )
            diagnosis.insert(
                "end",
                "机制: " + mechanism_var.get()
                + " | 证据: " + evidence_var.get()
                + " | 风险: " + risk_var.get() + "\n",
                ("muted",),
            )
            diagnosis.insert("end", "\n已有线索\n", ("h",))
            if assessment["strengths"]:
                for strength in assessment["strengths"]:
                    diagnosis.insert("end", "✓ " + strength + "\n", ("ok",))
            else:
                diagnosis.insert("end", "尚未识别到足够的具体线索。\n", ("warn",))
            diagnosis.insert("end", "\n主要缺口\n", ("h",))
            if assessment["gaps"]:
                for gap in assessment["gaps"]:
                    diagnosis.insert("end", "! " + gap + "\n", ("warn",))
            else:
                diagnosis.insert("end", "未发现基础结构缺口，但仍需真实文献与实验核验。\n")
            diagnosis.insert("end", "\n下一步\n", ("h",))
            for action in assessment["next_actions"]:
                diagnosis.insert("end", "→ " + action + "\n")
            diagnosis.insert(
                "end",
                "\n说明: 该诊断只检查表述是否具备可验证结构，不证明新颖性或正确性。",
                ("muted",),
            )
            diagnosis.config(state="disabled")
            if show_status:
                status.config(
                    text="本地诊断: " + assessment["stage"]
                    + " · " + str(assessment["total"]) + " 分")
            return assessment

        def on_select(_e=None):
            sel = idea_lb.curselection()
            if not sel or sel[0] >= len(filtered["rows"]):
                return
            it = filtered["rows"][sel[0]]
            selected_id["value"] = it.get("id")
            cat = it.get("category") or (cats[0] if cats else "未分类")
            cat_var.set(cat)
            update_fields()
            field_var.set(it.get("field") or field_var.get())
            type_var.set(it.get("type") or "方法创新")
            stage_var.set(idea_stage(it))
            mechanism_var.set(it.get("mechanism_type") or "未指定")
            evidence_var.set(it.get("evidence_type") or "未指定")
            risk_var.set(it.get("risk_type") or "未指定")
            title_e.delete(0, "end")
            title_e.insert(0, it.get("title", ""))
            domain_e.delete(0, "end")
            domain_e.insert(0, it.get("domain", ""))
            desc_t.delete("1.0", "end")
            desc_t.insert("1.0", it.get("desc", ""))
            status.config(text="已载入创新点；保存会更新当前记录")
            diagnose()

        def new_idea():
            selected_id["value"] = None
            idea_lb.selection_clear(0, "end")
            title_e.delete(0, "end")
            domain_e.delete(0, "end")
            desc_t.delete("1.0", "end")
            type_var.set("方法创新")
            stage_var.set(IDEA_STAGES[0])
            mechanism_var.set("未指定")
            evidence_var.set("未指定")
            risk_var.set("未指定")
            status.config(text="已新建空白创新点")
            diagnose()

        def save_idea(duplicate=False):
            it = current_idea()
            if not it:
                return
            assessment = evaluate_idea_local(it)
            it["local_assessment"] = assessment
            it["updated"] = datetime.datetime.now().isoformat(timespec="minutes")
            if selected_id["value"] and not duplicate:
                target = next((x for x in ideas
                               if x.get("id") == selected_id["value"]), None)
                if target is not None:
                    target.update(it)
                else:
                    selected_id["value"] = None
            if not selected_id["value"] or duplicate:
                it["id"] = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
                it["created"] = datetime.datetime.now().isoformat(timespec="minutes")
                ideas.append(it)
                selected_id["value"] = it["id"]
            mem = load_research_memory()
            mem["ideas"] = ideas
            save_research_memory(mem)
            refresh_list(selected_id["value"])
            status.config(text=("✔ 已保存副本" if duplicate else "✔ 已保存/更新创新点"))

        def delete_idea():
            if not selected_id["value"]:
                status.config(text="请先选择要删除的创新点")
                return
            target = next((x for x in ideas
                           if x.get("id") == selected_id["value"]), None)
            if target is None:
                return
            ideas.remove(target)
            mem = load_research_memory()
            mem["ideas"] = ideas
            save_research_memory(mem)
            selected_id["value"] = None
            refresh_list()
            new_idea()
            status.config(text="已删除: " + target.get("title", ""))

        def send_to_review():
            it = current_idea()
            if not it:
                return
            save_idea()
            if selected_id["value"]:
                self.open_idea_review_dialog(selected_id["value"])
                status.config(text="已送入独立选题体检台")

        def recommend_for_idea():
            it = current_idea()
            if not it:
                return
            profile_key = field_profile(it["category"], it["field"], relations)
            profile = relations.get("profiles", {}).get(profile_key, {})
            scen = profile.get("scenarios", [])[:1]
            meth = profile.get("methods", [])[:2]
            task = profile.get("tasks", [])[:2]
            mod = profile.get("modalities", [])[:2]
            relation = evaluate_combo(profile_key,
                                      {"scenario": scen, "method": meth,
                                       "task": task, "modality": mod}, relations)
            self.show_advisor_recommendations(it["category"], it["field"],
                                              scen[0] if scen else "",
                                              meth, task, mod, relation)

        def recommend_venues_for_idea():
            it = current_idea()
            if not it:
                return
            profile_key = field_profile(it["category"], it["field"], relations)
            profile = relations.get("profiles", {}).get(profile_key, {})
            scenario = (profile.get("scenarios") or [""])[0]
            methods = profile.get("methods", [])[:2]
            tasks = profile.get("tasks", [])[:2]
            modalities = profile.get("modalities", [])[:2]
            relation = evaluate_combo(profile_key, {
                "scenario": [scenario] if scenario else [],
                "method": methods, "task": tasks, "modality": modalities,
            }, relations)
            self.show_venue_recommendations(
                it["category"], it["field"], scenario,
                methods, tasks, modalities, relation)

        def auto_type():
            item = current_idea(require_content=False)
            assessment = evaluate_idea_local(item)
            type_var.set(assessment["recommended_type"])
            diagnose(show_status=True)
            status.config(text="类型已建议为: " + assessment["recommended_type"])

        def search_related_work():
            item = current_idea()
            if not item:
                return
            query = " ".join([
                item.get("title", ""), item.get("field", ""),
                item.get("domain", ""),
            ]).strip()
            webbrowser.open("https://dblp.org/search?q=" + quote_plus(query))
            status.config(text="已在浏览器打开 DBLP 相关工作检索")

        def continue_as_direction():
            item = current_idea()
            if not item:
                return
            self.open_direction_dialog(item["title"])
            status.config(text="已把创新点标题带入方向拓展")

        def search_focus_in(_e=None):
            if search_e.get() == "搜索标题、描述、大类或领域":
                search_e.delete(0, "end")
                search_e.config(fg=TXT)

        def search_focus_out(_e=None):
            if not search_e.get().strip():
                search_e.insert(0, "搜索标题、描述、大类或领域")
                search_e.config(fg=MUT)

        diagnose_job = {"id": None}

        def schedule_diagnose(_e=None):
            try:
                if diagnose_job["id"]:
                    dlg.after_cancel(diagnose_job["id"])
            except tk.TclError:
                pass
            diagnose_job["id"] = dlg.after(250, lambda: diagnose())

        search_e.bind("<FocusIn>", search_focus_in)
        search_e.bind("<FocusOut>", search_focus_out)
        search_e.bind("<KeyRelease>", lambda e: refresh_list())
        filter_var.trace_add("write", lambda *a: refresh_list())
        stage_filter_var.trace_add("write", lambda *a: refresh_list())
        idea_lb.bind("<<ListboxSelect>>", on_select)
        for widget in (title_e, domain_e, desc_t):
            widget.bind("<KeyRelease>", schedule_diagnose)
        type_var.trace_add("write", lambda *a: schedule_diagnose())
        mechanism_var.trace_add("write", lambda *a: schedule_diagnose())
        evidence_var.trace_add("write", lambda *a: schedule_diagnose())
        risk_var.trace_add("write", lambda *a: schedule_diagnose())

        self._btn(btns, "新建", new_idea).pack(side="left")
        self._btn(btns, "保存/更新", save_idea, accent=True).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "另存副本", lambda: save_idea(duplicate=True)).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "删除", delete_idea).pack(side="left", padx=(8, 0))
        self._btn(btns, "自动判定类型", auto_type).pack(side="left", padx=(8, 0))
        self._btn(btns, "查相关工作", search_related_work).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "继续拓展", continue_as_direction).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "导师/院校", recommend_for_idea).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "期刊/会议", recommend_venues_for_idea).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "送入选题体检", send_to_review,
                  accent=True).pack(side="left", padx=(8, 0))
        self._btn(btns, "关闭", dlg.destroy).pack(side="left", padx=(8, 0))
        refresh_list()
        diagnose()

    def open_idea_review_dialog(self, focus_id=None):
        ideas = load_research_memory().get("ideas", [])
        dlg = tk.Toplevel(self.root)
        dlg.title("科研工作台 · 独立选题体检")
        try:
            dlg.iconbitmap(str(ICON))
        except Exception:
            pass
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.geometry("1040x740+%d+%d" % (
            max(20, self.root.winfo_x() - 130),
            max(20, self.root.winfo_y() + 20),
        ))
        tk.Label(dlg, text="◆ 选题体检 · 独立研究决策台", bg=BG, fg=ACCENT,
                 font=("Microsoft YaHei UI", 11, "bold")).pack(
                     anchor="w", padx=14, pady=(12, 2))
        tk.Label(
            dlg,
            text="只做判断，不承担创新点编辑。检查问题价值、类型匹配、近邻竞争、"
                 "机制、证据、风险和最小实验可行性。",
            bg=BG, fg=MUT, font=FONT_XS, wraplength=1000, justify="left",
        ).pack(anchor="w", padx=14)

        selector = tk.Frame(dlg, bg=BG)
        selector.pack(fill="x", padx=14, pady=(8, 4))
        tk.Label(selector, text="待审查创新点", bg=BG, fg=MUT,
                 font=FONT_XS).pack(side="left")
        options = ["临时输入"] + [
            (it.get("title") or "(未命名)") for it in ideas
        ]
        choice_var = tk.StringVar(value=options[0])
        choice_menu = tk.OptionMenu(selector, choice_var, *options)
        choice_menu.config(bg=CARD, fg=TXT, activebackground=LINE,
                           activeforeground=TXT, relief="flat", bd=0,
                           highlightthickness=0, font=FONT_XS)
        choice_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                   activeforeground=TXT, bd=0)
        choice_menu.pack(side="left", fill="x", expand=True,
                         padx=(8, 16))
        tk.Label(selector, text="审查深度", bg=BG, fg=MUT,
                 font=FONT_XS).pack(side="left")
        depth_var = tk.StringVar(value="完整选题体检")
        depth_menu = tk.OptionMenu(
            selector, depth_var, "快速预筛", "完整选题体检", "最小实验设计")
        depth_menu.config(bg=CARD, fg=TXT, activebackground=LINE,
                          activeforeground=TXT, relief="flat", bd=0,
                          highlightthickness=0, font=FONT_XS)
        depth_menu["menu"].config(bg=CARD, fg=TXT, activebackground=LINE,
                                  activeforeground=TXT, bd=0)
        depth_menu.pack(side="left", padx=(8, 0))

        body = tk.Frame(dlg, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(4, 4))
        left = tk.Frame(body, bg=BG, width=390)
        left.pack(side="left", fill="both", padx=(0, 10))
        left.pack_propagate(False)
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="待审查内容", bg=BG, fg=MUT,
                 font=FONT_XS).pack(anchor="w")
        title_e = tk.Entry(left, bg=CARD, fg=TXT, insertbackground=TXT,
                           relief="flat", highlightbackground=LINE,
                           highlightthickness=1, font=FONT_S)
        title_e.pack(fill="x", pady=(3, 5), ipady=5)
        desc_t = tk.Text(left, height=10, wrap="word", bg=CARD, fg=TXT,
                         insertbackground=TXT, relief="flat",
                         highlightbackground=LINE, highlightthickness=1,
                         font=FONT_XS, padx=8, pady=7)
        desc_t.pack(fill="both", expand=True)
        meta = tk.Label(left, text="选择库中创新点，或直接粘贴一个临时想法。",
                        bg=BG, fg=MUT, font=FONT_XS, anchor="w",
                        wraplength=370, justify="left")
        meta.pack(fill="x", pady=(5, 0))
        tk.Label(right, text="本地决策报告", bg=BG, fg=MUT,
                 font=FONT_XS).pack(anchor="w")
        report = tk.Text(
            right, height=27, wrap="word", bg=CARD, fg=TXT,
            relief="flat", highlightbackground=LINE, highlightthickness=1,
            font=FONT_XS, padx=10, pady=9, spacing1=2, spacing3=2,
        )
        report.pack(fill="both", expand=True, pady=(3, 0))
        report.tag_config("h", foreground=ACCENT,
                          font=("Microsoft YaHei UI", 11, "bold"))
        report.tag_config("ok", foreground=OKC)
        report.tag_config("warn", foreground=WARN)
        report.tag_config("bad", foreground=ERR)
        report.tag_config("muted", foreground=MUT)
        report.config(state="disabled")
        status = tk.Label(dlg, text="", bg=BG, fg=MUT,
                          font=FONT_XS, anchor="w")
        status.pack(fill="x", padx=14, pady=(2, 0))
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(4, 12))
        current = {"idea": None, "assessment": None}

        def selected_index():
            label = choice_var.get()
            try:
                return options.index(label) - 1
            except ValueError:
                return -1

        def load_selected(_event=None):
            index = selected_index()
            if index < 0 or index >= len(ideas):
                title_e.delete(0, "end")
                desc_t.delete("1.0", "end")
                meta.config(text="临时输入模式；不会自动写回创新点库。")
                current["idea"] = None
                current["assessment"] = None
                return
            it = ideas[index]
            title_e.delete(0, "end")
            title_e.insert(0, it.get("title", ""))
            desc_t.delete("1.0", "end")
            desc_t.insert("1.0", it.get("desc", ""))
            meta.config(
                text="库中记录: " + (it.get("category") or "未分类")
                + " / " + (it.get("field") or "未分类")
                + " · 类型 " + (it.get("type") or "未指定")
                + " · 机制 " + (it.get("mechanism_type") or "未指定")
                + " · 证据 " + (it.get("evidence_type") or "未指定"),
            )
            analyze()

        def compose_idea():
            title = title_e.get().strip()
            desc = desc_t.get("1.0", "end").strip()
            if not title or not desc:
                status.config(text="请至少填写标题和描述")
                return None
            index = selected_index()
            base = dict(ideas[index]) if 0 <= index < len(ideas) else {}
            base.update({"title": title, "desc": desc})
            if not base.get("category") or not base.get("field"):
                category, field, _confidence = infer_category_field(
                    title + " " + desc)
                base["category"] = category
                base["field"] = field
            if not base.get("type"):
                base["type"] = infer_innovation_type(title, desc)
            base.setdefault("mechanism_type", "未指定")
            base.setdefault("evidence_type", "未指定")
            base.setdefault("risk_type", "未指定")
            return base

        def analyze():
            idea = compose_idea()
            if not idea:
                return
            current["idea"] = idea
            assessment = evaluate_idea_local(idea)
            current["assessment"] = assessment
            report.config(state="normal")
            report.delete("1.0", "end")
            report.insert("end", assessment["decision"] + "\n", ("h",))
            report.insert(
                "end",
                "阶段 " + assessment["stage"]
                + "  ·  综合 " + str(assessment["total"])
                + "  ·  审查深度 " + depth_var.get() + "\n",
                ("muted",),
            )
            report.insert(
                "end",
                "类型 " + (idea.get("type") or "未指定")
                + " · 机制 " + idea.get("mechanism_type", "未指定")
                + " · 证据 " + idea.get("evidence_type", "未指定")
                + " · 风险 " + idea.get("risk_type", "未指定") + "\n\n",
            )
            report.insert("end", "评分矩阵\n", ("h",))
            for key, value in assessment["scores"].items():
                bar = "█" * max(1, int(value / 10)) + "░" * max(0, 10 - int(value / 10))
                tag = "ok" if value >= 70 else "warn" if value >= 45 else "bad"
                report.insert("end", key + "  " + bar + "  " + str(value) + "\n", (tag,))
            report.insert("end", "\n已有支持\n", ("h",))
            if assessment["strengths"]:
                for item in assessment["strengths"]:
                    report.insert("end", "✓ " + item + "\n", ("ok",))
            else:
                report.insert("end", "没有识别到足够的具体证据结构。\n", ("bad",))
            report.insert("end", "\n审查缺口\n", ("h",))
            if assessment["gaps"]:
                for item in assessment["gaps"]:
                    report.insert("end", "! " + item + "\n", ("warn",))
            else:
                report.insert("end", "基础结构完整，但尚不能证明创新性。\n")
            report.insert("end", "\n下一步行动\n", ("h",))
            for item in assessment["next_actions"]:
                report.insert("end", "→ " + item + "\n")
            report.insert(
                "end",
                "\n本页只做本地预筛；正式结论必须经过真实文献、实验和评审。",
                ("muted",),
            )
            report.config(state="disabled")
            status.config(text="体检完成: " + assessment["decision"])
            meta.config(
                text="目录: " + (idea.get("category") or "未识别")
                + " / " + (idea.get("field") or "未识别")
                + " · 本地结论只用于决定下一步，不代表录用判断。",
            )

        def save_review():
            idea = compose_idea()
            if not idea:
                return
            assessment = evaluate_idea_local(idea)
            index = selected_index()
            mem = load_research_memory()
            rows = mem.setdefault("ideas", [])
            if 0 <= index < len(rows):
                rows[index].setdefault("reviews", []).append({
                    "time": datetime.datetime.now().isoformat(timespec="minutes"),
                    "depth": depth_var.get(),
                    "assessment": assessment,
                })
            else:
                idea["id"] = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
                idea["created"] = datetime.datetime.now().isoformat(timespec="minutes")
                idea["stage"] = assessment["stage"]
                idea["reviews"] = [{
                    "time": datetime.datetime.now().isoformat(timespec="minutes"),
                    "depth": depth_var.get(),
                    "assessment": assessment,
                }]
                rows.append(idea)
            save_research_memory(mem)
            status.config(text="✔ 审查结论已保存")

        def copy_prompt():
            idea = compose_idea()
            if not idea:
                return
            prompt = idea_review_prompt(idea, depth_var.get())
            self._copy_prompt("选题体检", prompt)
            status.config(text="✔ 选题体检提示词已复制")

        def related_work():
            idea = compose_idea()
            if not idea:
                return
            query = " ".join([
                idea.get("title", ""), idea.get("field", ""),
                idea.get("domain", ""),
            ]).strip()
            webbrowser.open("https://dblp.org/search?q=" + quote_plus(query))
            status.config(text="已打开 DBLP 近邻工作检索")

        def advisor_lookup():
            idea = compose_idea()
            if not idea:
                return
            category = idea.get("category") or ""
            field = idea.get("field") or idea["title"]
            tokens = _translate_direction(idea["title"] + " " + idea["desc"])
            self.show_advisor_recommendations(
                category, field, idea.get("domain", ""), tokens, [], [])

        def venue_lookup():
            idea = compose_idea()
            if not idea:
                return
            category = idea.get("category") or ""
            field = idea.get("field") or idea["title"]
            relations = load_research_relations()
            profile_key = field_profile(category, field, relations)
            profile = relations.get("profiles", {}).get(profile_key, {})
            scenario = (profile.get("scenarios") or [idea.get("domain", "")])[0]
            methods = profile.get("methods", [])[:2]
            tasks = profile.get("tasks", [])[:2]
            modalities = profile.get("modalities", [])[:2]
            relation = evaluate_combo(profile_key, {
                "scenario": [scenario] if scenario else [],
                "method": methods, "task": tasks, "modality": modalities,
            }, relations)
            self.show_venue_recommendations(
                category, field, scenario, methods, tasks, modalities, relation)

        def open_library():
            self.open_idea_library_dialog()

        choice_var.trace_add("write", lambda *a: load_selected())
        title_e.bind("<KeyRelease>", lambda e: analyze())
        desc_t.bind("<KeyRelease>", lambda e: analyze())
        depth_var.trace_add("write", lambda *a: analyze())

        self._btn(btns, "重新体检", analyze, accent=True).pack(side="left")
        self._btn(btns, "保存审查结论", save_review).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "复制体检提示词", copy_prompt).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "查相关工作", related_work).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "导师/院校", advisor_lookup).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "期刊/会议", venue_lookup).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "打开创新点库", open_library).pack(
            side="left", padx=(8, 0))
        self._btn(btns, "关闭", dlg.destroy).pack(side="left", padx=(8, 0))

        if focus_id:
            for index, idea in enumerate(ideas):
                if idea.get("id") == focus_id:
                    choice_var.set(options[index + 1])
                    break
        else:
            load_selected()

    def _open_tools_menu(self):
        m = getattr(self, "_tools_menu", None)
        if m is None:
            m = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TXT,
                        activebackground=ACCENT, activeforeground=BG, bd=0)
            m.add_command(label="智能下载（自然语言）", command=self.focus_smart_input)
            m.add_command(label="查看迭代记忆", command=lambda: self.send_command("记忆"))
            m.add_separator()
            m.add_command(label="方向库（大类/小类）", command=self.open_direction_library)
            m.add_command(label="导师/院校推荐", command=self.open_advisor_dialog)
            m.add_command(label="期刊/会议推荐", command=self.open_venue_dialog)
            m.add_command(label="科研知识总览", command=self.run_research_overview)
            m.add_command(label="创新点库", command=self.open_ideas_dialog)
            m.add_separator()
            m.add_command(label="抓取预演（不下载）", command=lambda: self.start_preview())
            m.add_command(label="导出论文清单（Excel）", command=self.export_papers)
            m.add_command(label="知识库体检", command=self.run_health)
            m.add_command(label="生成周报", command=self.make_weekly)
            self._tools_menu = m
        try:
            x = self.tools_btn.winfo_rootx()
            y = self.tools_btn.winfo_rooty() + self.tools_btn.winfo_height()
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _ensure_log_open(self):
        if not self.secs["log"]["state"]:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self._set_sec_state("log", True)
            secs = dict(self.settings.get("secs", {}))
            secs["log"] = True
            self.settings["secs"] = secs
            self._save_settings_soon()
            self._keep_pos(x, y)

    def _ensure_digest_open(self):
        if not self.secs["digest"]["state"]:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self._set_sec_state("digest", True)
            secs = dict(self.settings.get("secs", {}))
            secs["digest"] = True
            self.settings["secs"] = secs
            self._save_settings_soon()
            self._keep_pos(x, y)

    def _begin_progress(self, label):
        job = getattr(self, "_progress_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._progress_job = None
        self._prog_last_stage = ""
        self._prog_last_log_pct = -1
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.progress_lbl.config(text="● " + label, fg=ACCENT)
        self._set_progress(0)
        if not self.progress_frame.winfo_ismapped():
            self.progress_frame.pack(fill="x", padx=14, pady=(0, 5),
                                     before=self.btns_frame)
        self._ensure_log_open()
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        self._append_progress("=== " + time.strftime("%H:%M:%S") + "  " + label + " ===")
        self._keep_pos(x, y)

    def _set_progress(self, pct):
        try:
            val = max(0.0, min(100.0, float(pct)))
            self.progress_fill.place_configure(relwidth=val / 100.0)
        except (tk.TclError, ValueError):
            pass

    def _apply_progress(self, stage, pct, detail):
        try:
            text = stage
            if pct is not None:
                self._set_progress(pct)
                text += "  " + str(int(pct)) + "%"
            if detail:
                text += " · " + detail
            self.progress_lbl.config(text=text[:160])
            line = stage
            if pct is not None:
                line += " " + str(int(pct)) + "%"
            if detail:
                line += " · " + detail
            stage_changed = stage != getattr(self, "_prog_last_stage", "")
            threshold = (pct is None or pct >= 100
                         or int(pct) - getattr(self, "_prog_last_log_pct", -1) >= 5)
            if stage_changed or threshold:
                self._prog_last_stage = stage
                if pct is not None:
                    self._prog_last_log_pct = int(pct)
                self._append_progress(line)
        except tk.TclError:
            pass

    def _append_progress(self, line):
        try:
            self.log.config(state="normal")
            self.log.insert("end", time.strftime("%H:%M:%S") + "  " + line + "\n",
                            ("dim",))
            if int(self.log.index("end-1c").split(".")[0]) > 400:
                self.log.delete("1.0", "100.0")
            self.log.see("end")
            self.log.config(state="disabled")
        except tk.TclError:
            pass

    def _end_progress(self, text, ok=True, color=None):
        try:
            self._set_progress(100)
            self.progress_lbl.config(text=text, fg=(color or (OKC if ok else ERR)))
            self._append_progress(text)
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self._keep_pos(x, y)
            self._progress_job = self.root.after(8000, self._hide_progress)
        except tk.TclError:
            pass

    def _hide_progress(self):
        self._progress_job = None
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.progress_frame.pack_forget()
            self._keep_pos(x, y)
        except tk.TclError:
            pass

    def _run_tool(self, kind, label, fn):
        if getattr(self, "_tool_running", False):
            self.status.set("已有工具任务在运行，请稍候…")
            return
        self._tool_running = True
        self.status.set("● " + label + "…")
        self._begin_progress(label)

        def worker():
            try:
                payload = fn(lambda stage, pct, detail: self._progress_q.put((stage, pct, detail)))
            except Exception as exc:
                payload = exc
            self._report_q.put((kind, payload))

        threading.Thread(target=worker, daemon=True).start()

    def start_preview(self, days=None):
        self._run_tool("preview", "抓取预演（不下载）",
                       lambda progress: run_preview(days, progress))

    def focus_smart_input(self):
        try:
            self.cmd_entry.focus_set()
            self.cmd_entry.delete(0, "end")
            self.cmd_entry.insert(0, "下载最新的10篇红外目标检测论文，放到Mamba多模态")
            self.cmd_entry.config(fg=TXT)
            self.cmd_entry.icursor("end")
        except tk.TclError:
            pass

    def start_smart_fetch(self, spec):
        if spec.get("unknown"):
            self._ensure_log_open()
            self._show_cmd_output([
                "未识别方向词：" + spec["direction"],
                "可用词：红外 / 目标检测 / 多模态 / 融合 / 跟踪 / 医学 / 分割 / 扩散 / 遥感 / 无人机 / Mamba",
                "也可以先设置映射：记住 " + spec["direction"] + "=某个分类",
            ], [], tall=True)
            self.status.set("⚠ 未识别方向词，未执行")
            return
        plan = [
            "智能抓取计划",
            "方向: " + spec["direction"],
            "arXiv 查询: " + spec["query"],
            "数量: 最多 " + str(spec["count"]) + " 篇",
            "分类: " + (spec["category"] or "新论文/日期"),
            "窗口: " + ("最近 " + str(spec["days"]) + " 天" if spec.get("days")
                       else "不限时间（取最新）"),
        ]
        self._ensure_log_open()
        self._show_cmd_output(plan, [], tall=True)
        self._run_tool("smart", "智能下载 " + spec["direction"],
                       lambda progress: smart_fetch(spec, True, progress))

    def export_papers(self):
        def job(progress):
            path = export_papers_xlsx(progress)
            return path, ["论文清单已导出", "文件: " + path.name,
                          "共 " + str(len(_inventory()["pdfs"])) + " 篇 PDF"]
        self._run_tool("export", "导出论文清单", job)

    def run_health(self):
        self._run_tool("health", "知识库体检",
                       lambda progress: health_check(progress))

    def make_weekly(self):
        self._run_tool("weekly", "生成周报",
                       lambda progress: weekly_brief(7, progress))

    def _tool_done(self, kind, payload):
        self._tool_running = False
        if isinstance(payload, Exception):
            self._ensure_log_open()
            self._show_cmd_output(["工具执行失败: " + str(payload)], [], tall=True,
                                  append=True)
            self._end_progress("✘ 工具执行失败", False)
            self.status.set("✘ 工具执行失败: " + str(payload))
            return
        if kind == "advisor_update":
            res = payload
            insts = load_institutions_cn()
            provinces = len({i.get("region") for i in insts if i.get("region")})
            lines = [
                "全国导师索引更新完成",
                "导师/研究者: " + str(res.get("advisors", 0)) + " 位",
                "院校/机构: " + str(res.get("institutions", 0)) + " 所",
                "省级地区: " + str(provinces) + " 个",
                "本次更新院校: " + str(res.get("selected_institutions", 0)) + " 所",
                "来源: OpenAlex 公开出版数据；导师身份/招生状态需官网核验。",
            ]
            self._ensure_log_open()
            self._show_cmd_output(lines, [], tall=True, append=True)
            self.status.set("✔ 全国导师索引已更新")
            try:
                if getattr(self, "_advisor_coverage_label", None):
                    self._advisor_coverage_label.config(
                        text="索引: " + str(len(load_advisors())) + " 位研究者 / "
                        + str(len(insts)) + " 所院校 / " + str(provinces)
                        + " 个省级地区（含 OpenAlex 公开索引）")
            except tk.TclError:
                pass
            self._end_progress("✔ 全国导师索引已更新", True)
            return
        if kind == "preview":
            lines, actions = payload
            self._ensure_log_open()
            self._show_cmd_output(lines, actions, tall=True, append=True)
            self._end_progress("✔ 预演完成", True)
            self.status.set("✔ 预演完成（未下载），点击候选行打开 arXiv")
            return
        if kind == "smart":
            res = payload
            lines = ["智能下载结果", "查询: " + res["query"],
                     "候选: " + str(res["candidates"])]
            if res["downloaded"]:
                lines.append("已下载: " + str(len(res["downloaded"])) + " 篇")
                lines.append("归档: " + res["target"])
                for e in res["downloaded"][:10]:
                    lines.append("- " + e["title"])
                if res.get("digest"):
                    lines.append("速览: " + Path(res["digest"]).name)
            else:
                lines.append("没有可下载的新论文（已见/时间窗口/关键词过滤）")
            if res.get("failed"):
                lines.append("下载失败: " + str(len(res["failed"])))
            actions = {}
            if res.get("digest"):
                actions[len(lines)] = ("open_file", res["digest"])
                lines.append("▸ 打开速览")
            actions[len(lines)] = ("open_file", res["target"])
            lines.append("▸ 打开归档目录")
            self._ensure_log_open()
            self._show_cmd_output(lines, actions, tall=True, append=True)
            if res["downloaded"]:
                self.status.set("✔ 已下载 " + str(len(res["downloaded"])) + " 篇 → "
                                + Path(res["target"]).name)
                self._end_progress("✔ 已下载 " + str(len(res["downloaded"])) + " 篇", True)
            else:
                self.status.set("⚠ 智能下载：未找到可下载论文")
                self._end_progress("⚠ 智能下载：无匹配论文", False, color=WARN)
            self.refresh(force=True)
            return
        path, summary = payload
        self._ensure_log_open()
        actions = {len(summary): ("open_file", str(path))}
        self._show_cmd_output(summary + ["▸ 点击打开生成的文件"], actions,
                              tall=True, append=True)
        self.status.set("✔ " + summary[0] + ": " + path.name)
        self._ensure_digest_open()
        self.refresh(force=True)
        self._end_progress("✔ " + summary[0], True)

    def open_dir(self, target):
        try:
            cfg = load_config()
            kb = Path(cfg.get("kb_path", r"G:\相关内容\AuthorKit27\知识库"))
            if target == "kb":
                p = kb
            elif target == "inbox":
                p = kb / cfg.get("inbox_dir", "新论文")
            else:
                p = HERE
            p.mkdir(parents=True, exist_ok=True)
            os.startfile(str(p))
        except Exception as exc:
            self.status.set("打开失败: " + str(exc))

    def open_web(self):
        try:
            subprocess.Popen([self._runner(), str(DASHBOARD)], cwd=str(HERE),
                             **_hidden_kwargs())
            self.status.set("网页版已启动（备用面板 127.0.0.1:8765）")
        except Exception as exc:
            self.status.set("网页版启动失败: " + str(exc))

    def start_scan(self, days=None, max_downloads=None):
        if self.scanning:
            return
        self.scanning = True
        self.scan_btn.config(state=tk.DISABLED)
        self.status.set("● 正在抓取 arXiv 新论文（约 1-3 分钟）…")
        self._begin_progress("抓取 arXiv")
        self._progress_q.put(("启动 kbscan", 5, "并行查询与下载中…"))
        threading.Thread(target=lambda: self._scan_worker(days, max_downloads),
                         daemon=True).start()

    def _scan_worker(self, days=None, max_downloads=None):
        cfg = load_config()
        if days is None:
            days = cfg.get("days_back", 7)
        cmd = [self._runner(), "-X", "utf8", "-u", str(KBSCAN), "--days", str(days)]
        if max_downloads:
            cmd += ["--max-downloads", str(max_downloads)]
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60 * 30,
                                  env=env, **_hidden_kwargs())
            out = _decode_bytes(proc.stdout)
            err = _decode_bytes(proc.stderr)
            combined = out + ("\n" + err if err.strip() and err.strip() not in out else "")
            lines = [ln for ln in combined.splitlines() if ln.strip()]
            tail = "\n".join(lines[-8:]) if lines else "完成（本轮无新增）"
            fails = sum(1 for ln in lines if "QUERY FAIL" in ln)
            total_q = max(1, len(cfg.get("queries", [])))
            if fails >= total_q:
                status = "✘ 抓取失败：arXiv 查询全部超时/不可达\n" + tail
            elif fails:
                status = "⚠ 部分查询失败（" + str(fails) + "/" + str(total_q) + "）\n" + tail
            else:
                status = "✔ 抓取完成\n" + tail
        except subprocess.TimeoutExpired:
            status = "✘ 抓取超时（30 分钟），请缩小窗口或稍后重试"
        except Exception as exc:
            status = "✘ 抓取失败: " + str(exc)
        self._scan_q.put(status)

    def _scan_done(self, status):
        try:
            self.scanning = False
            self.scan_btn.config(state=tk.NORMAL)
            self.status.set(status)
            first = status.splitlines()[0] if status else "抓取完成"
            color = WARN if first.startswith("⚠") else (ERR if first.startswith("✘") else OKC)
            self._end_progress(first, not first.startswith("✘"), color=color)
            self.refresh(force=True)
        except tk.TclError:
            pass


def run_widget():
    _enable_dpi()
    sys.excepthook = _log_exc
    try:
        root = tk.Tk()
        root.title("知识库助手")
        try:
            root.iconbitmap(str(ICON))
        except Exception:
            pass
        root.report_callback_exception = _log_exc
        W(root)
        root.mainloop()
    except Exception:
        _log_exc(*sys.exc_info())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_widget())
