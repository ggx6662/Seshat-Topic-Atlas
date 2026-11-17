#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「最新研究」里看到的论文直接拉进本地知识库。

为什么单独一层，而不复用 kb_widget.smart_fetch：
  smart_fetch 是「按检索式批量抓 arXiv 新论文」的定时任务，它自己查 arXiv、
  自己按日期过滤、自己决定下载几篇。而这里的场景是**用户指着某一篇说我要它**——
  可能来自 arXiv，也可能来自 OpenAlex（那就得用 open_access 的直链），
  还可能是 Europe PMC 里没有公开 PDF 的。两者的输入、去重口径、失败处理都不一样。
  只有底层动作是共用的：kbscan.download_pdf_stream（流式 + 半包校验）
  和 kbscan.extract_first_page（首页文本）。

设计约定：
  · 只追加不覆盖。同名文件已存在就跳过，不静默改写成 xxx(1).pdf。
  · 三种去重口径都做：按 arXiv ID（文件名尾部）、按文件大小、按标题规范化。
    只按文件名去重会重复下载同名不同 ID 的论文，也会漏掉用户手动改名后的重复。
  · 失败必须说清楚原因（没有公开 PDF / 超大小 / 不完整 / 网络错），
    不能像旧代码那样把异常吞掉返回 None 当成「查无此人」。
  · 默认落到 config.json 的 inbox_dir 下按日期分目录（YYYY-MM-DD），
    因为新论文还没人工归类；classify_dir() 只在用户明确指定分类时才用。
  · 全程不写 research_memory.json，只写 kb_root() 下的文件。
"""
import datetime
import json
import re
import threading
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:
    import app_paths as _AP
    _RES = _AP.res        # 只读资源：打包后在 _MEIPASS
    _DATA = _AP.data      # 可写数据：打包后在 exe 旁边
except Exception:         # 单独跑构建脚本/测试时退回旧行为
    _RES = lambda n: HERE / n
    _DATA = lambda n: HERE / n
MAX_BYTES = 45 * 1024 * 1024
UA = {"User-Agent": "kb-monitor/0.2 (research-kb; personal)"}

# 知识库现有分类目录（会与 kb_root() 下真实存在的目录合并）
KNOWN_DIRS = ("AAAI", "CVPR", "ICCV", "ICLR", "ECCV", "NeurIPS", "TPAMI",
              "Mamba多模态", "Track", "扩散模型", "医学", "分类总结")

_ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")
_ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", re.I)
_HAS_ID_IN_NAME = re.compile(r"_(\d{4}_\d{4,5})(?:_v\d+)?\.pdf$", re.I)
# 目录名里的日期（收件箱按 YYYY-MM-DD 分目录），不算 arXiv ID
_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # 仅文档用，去重不再依赖目录


# ---------------------------------------------------------------- 记录归一化

def _arxiv_id(p):
    """从三源记录里抠出 arXiv ID；没有返回空串。

    arXiv 源有 arxiv_id 字段；OpenAlex / Europe PMC 只在 url / doi 里带。
    """
    aid = (p.get("arxiv_id") or "").strip()
    if aid:
        m = _ARXIV_ID.search(aid)
        return m.group(1) if m else aid
    for key in ("url", "doi", "oa"):
        v = (p.get(key) or "").strip()
        if not v:
            continue
        m = _ARXIV_URL.search(v)
        if m:
            mm = _ARXIV_ID.search(m.group(1))
            if mm:
                return mm.group(1)
    return ""


def _safe_stem(title, limit=70):
    """文件名安全化：保留中英数字与 _ -，其余压成下划线。

    中文标题要保留（用户直接看目录），不能像 kbscan._pdf_filename 那样
    用 \\w 之外的规则把中文字全部吃掉。
    """
    t = (title or "").strip()
    t = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", t)
    t = re.sub(r"\s+", "_", t)
    t = re.sub(r"_+", "_", t).strip("._ ")
    return (t or "untitled")[:limit]


def _pdf_name(p, aid):
    stem = _safe_stem(p.get("title"))
    return stem + ("_" + aid.replace(".", "_") if aid else "") + ".pdf"


def pdf_candidates(p):
    """按优先级列出可尝试的 PDF 地址。arXiv 最稳，其次 oa 直链。

    返回 [(url, note), ...]；空列表表示这条记录拿不到公开全文。
    """
    out = []
    aid = _arxiv_id(p)
    if aid:
        out.append(("https://arxiv.org/pdf/" + aid, "arXiv"))
    oa = (p.get("oa") or "").strip()
    if oa.startswith("http"):
        out.append((oa, "开放获取"))
    url = (p.get("url") or "").strip()
    if url.startswith("http") and "arxiv.org/abs/" in url:
        cand = "https://arxiv.org/pdf/" + url.rsplit("/", 1)[-1]
        if all(c[0] != cand for c in out):
            out.append((cand, "arXiv"))
    return out


# ---------------------------------------------------------------- 知识库状态

def kb_paths():
    """(知识库根, 收件箱)。与 kb_widget 共用同一份 config.json，避免两套口径。"""
    import kb_widget as kb
    root = kb.kb_root()
    return root, kb.inbox_dir()


def existing_index(root=None, extra=()):
    """扫一遍知识库已有的 PDF，建去重索引。

    extra: 额外要并入的目录（如本次批量下载的目标目录）。index() 自己会扫
    kb_root()，但测试/临时下载目录不在里面，不传就会重复下载同一篇。

    返回 {"ids": set, "sizes": set, "titles": set, "count": n}。
    """
    import meta_index
    root = root or kb_paths()[0]
    ids, sizes, titles = set(), set(), set()
    n = 0
    roots = [Path(root)] + [Path(x) for x in extra]
    # 「最新研究」页的下载目标目录名是 YYYY-MM-DD：那里的文件可能还没进
    # paper_meta.json 的索引，标题必须从文件名现场推断，否则同一篇会被反复下载
    from build_paper_meta import title_from_filename
    for base in roots:
        if not base.exists():
            continue
        for f in base.rglob("*.pdf"):
            try:
                sizes.add(f.stat().st_size)
            except OSError:
                pass
            m = _HAS_ID_IN_NAME.search(f.name)
            if m:
                ids.add(m.group(1).replace("_", "."))
            titles.add(_norm_title(f.stem))
            try:
                t = title_from_filename(f)
                if t:
                    titles.add(_norm_title(t))
            except Exception:
                pass
            n += 1
    # 已有索引里记过的标题也算（有些 PDF 文件名是会议编号，看不出标题）
    try:
        for path, mt in meta_index.all_meta().items():
            if mt.get("title"):
                titles.add(_norm_title(mt["title"]))
    except Exception:
        pass
    return {"ids": ids, "sizes": sizes, "titles": titles, "count": n}


def _norm_title(t):
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", t)
    return t[:120]


def already_have(p, idx):
    """返回判重原因（人类可读），已存在则返回非空串。"""
    aid = _arxiv_id(p)
    if aid and aid in idx["ids"]:
        return "已收录（arXiv %s）" % aid
    nt = _norm_title(p.get("title"))
    if nt and len(nt) >= 12:
        if nt in idx["titles"]:
            return "已收录（标题相同）"
        # 文件名会把标题截到 70 字符再加 ID，比较时允许前缀命中
        for t in idx["titles"]:
            if len(t) >= 40 and len(nt) >= 40 and (t.startswith(nt[:40]) or nt.startswith(t[:40])):
                return "已收录（标题前缀相同）"
    return ""


# ---------------------------------------------------------------- 分类建议

def list_dirs(root=None):
    """知识库下真实存在的分类目录。"""
    root = root or kb_paths()[0]
    dirs = []
    try:
        for d in sorted(root.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and d.name != "新论文":
                dirs.append(d.name)
    except Exception:
        pass
    return dirs


def suggest_dir(direction="", venue=""):
    """猜一个该放哪。猜不准就返回 ""（=进收件箱），不硬塞。

    规则只有两条，宁可少猜：会议名完全匹配优先；方向关键词命中已有目录次之。
    """
    v = (venue or "").upper()
    dirs = list_dirs()
    for d in dirs:
        if d.upper() == v and d.isupper():
            return d
    text = (direction or "").lower()
    hit = []
    for d in dirs:
        dl = d.lower()
        if dl and dl in text:
            hit.append(d)
        elif "扩散" in d and "diffusion" in text:
            hit.append(d)
        elif ("mamba" in d.lower() or "多模态" in d) and ("mamba" in text or "多模态" in text):
            hit.append(d)
        elif ("track" in dl or "跟踪" in d) and ("track" in text or "跟踪" in text):
            hit.append(d)
        elif ("医学" in d or "medical" in dl) and ("医学" in text or "medical" in text):
            hit.append(d)
    return hit[0] if hit else ""


# ------------------------------------------------------------ 定时抓取集成

FAILURES_FILE = _DATA("download_failures.json")
SEEN_FILE = _DATA("seen_ids.json")


def read_failures():
    """读上一次定时抓取的失败记录。没有就返回空结构。"""
    try:
        return json.loads(FAILURES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"time": "", "downloaded": 0, "failed": [], "over_limit": 0}


def retry_failed(limit=5, idx=None, progress=None):
    """把上次失败的条目重新拉一遍。

    只重试「当时真失败」的，不重试「没有公开全文」——后者再试多少次都一样，
    只会白耗时间。这个区分是失败上报要分清原因的直接理由。
    """
    rec = read_failures()
    items = [x for x in (rec.get("failed") or []) if x.get("id")][:limit]
    if not items:
        return {"tried": 0, "ok": 0, "still": []}
    if idx is None:
        idx = existing_index()
    ok, still = 0, []
    for i, it in enumerate(items, 1):
        if progress:
            try:
                progress(i, len(items), it.get("title") or "")
            except Exception:
                pass
        p = {"title": it.get("title") or "", "arxiv_id": it.get("id") or "",
             "source": "arxiv", "url": "https://arxiv.org/abs/" + (it.get("id") or ""),
             "published": it.get("published") or ""}
        r = download(p, idx=idx)
        if r["ok"] and not r["skipped"]:
            ok += 1
        elif not r["ok"]:
            still.append({"id": it["id"], "title": p["title"],
                          "published": p["published"], "error": r["reason"]})
    if not still:
        try:
            FAILURES_FILE.unlink(missing_ok=True)
        except Exception:
            pass
    else:
        rec["failed"] = still
        rec["time"] = datetime.datetime.now().isoformat(timespec="minutes")
        try:
            FAILURES_FILE.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        except Exception:
            pass
    return {"tried": len(items), "ok": ok, "still": still}


def seen_ids():
    """定时抓取线已经处理过的 arXiv ID（kbscan 写的那份）。"""
    try:
        import kbscan
        return kbscan.load_seen(SEEN_FILE)
    except Exception:
        return set()


SCHEDULED = False   # 2026-11-15：Windows 计划任务已删除，抓取改为手动


def schedule_status():
    """上次抓取失败 + 收件箱状态。定时抓取已在 2026-11-15 移除。

    以前这里每次都会 shell 调一次 `schtasks /Query`（超时 20 秒），
    现在用户明确不要定期抓取了，就没必要为一个已删除的任务付出这个代价——
    启动总览页时会调到这里。真要查任务状态，直接把 SCHEDULED 改成 True。
    """
    if SCHEDULED:
        try:
            import kb_widget as kb
            t = kb.task_status()
        except Exception:
            t = {"status": "未知", "next_run": "未知"}
    else:
        t = {"status": "已停用（手动抓取）", "next_run": "—"}
    rec = read_failures()
    st = stats()
    return {
        "task_status": t.get("status") or "未知",
        "next_run": t.get("next_run") or "未知",
        "last_time": rec.get("time") or "",
        "failed": len(rec.get("failed") or []),
        "over_limit": int(rec.get("over_limit") or 0),
        "pdf_total": st.get("pdf_total", 0),
        "added_7d": st.get("added_7d", 0),
    }


# ---------------------------------------------------------------- 下载

def _download_url(url, name, out_dir, progress=None):
    """流式下载到 .part，校验完整后原子改名。"""
    req = urllib.request.Request(url, headers=UA)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / name if out_dir.is_absolute() else (HERE / out_dir / name)
    part = pdf_path.with_suffix(".part")
    with urllib.request.urlopen(req, timeout=90) as resp:
        clen = resp.headers.get("Content-Length")
        total = int(clen) if clen else 0
        if total > MAX_BYTES:
            raise ValueError("PDF 太大（%d MB），已跳过" % (total // 1048576))
        got, last = 0, -1
        with open(part, "wb") as fh:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                if got > MAX_BYTES:
                    fh.close()
                    part.unlink(missing_ok=True)
                    raise ValueError("PDF 太大（超过 %d MB）" % (MAX_BYTES // 1048576))
                if progress:
                    pct = int(got * 100.0 / total) if total else -1
                    if pct != last:
                        last = pct
                        try:
                            progress(got, total, (got / float(total)) if total else None)
                        except Exception:
                            pass
    if got < 1024:
        part.unlink(missing_ok=True)
        raise ValueError("下载内容过小（%d 字节），可能不是 PDF" % got)
    if total and got != total:
        part.unlink(missing_ok=True)
        raise ValueError("下载不完整（%d/%d 字节）" % (got, total))
    # 有些开放获取链接返回的是 HTML 落地页而不是 PDF
    head = part.read_bytes()[:5] if part.stat().st_size > 5 else b""
    if head != b"%PDF-":
        part.unlink(missing_ok=True)
        raise ValueError("返回的不是 PDF（可能是网页）")
    part.replace(pdf_path)
    return pdf_path, got


def download(p, out_dir=None, idx=None, progress=None, direction="", extract_text=True):
    """下载一篇论文进知识库。返回结果 dict，从不抛异常。

    {"ok": bool, "path": str, "reason": str, "bytes": int, "source": str,
     "txt": bool, "skipped": bool}
    """
    res = {"ok": False, "path": "", "reason": "", "bytes": 0,
           "source": "", "txt": False, "skipped": False}
    try:
        if idx is None:
            idx = existing_index()
        why = already_have(p, idx)
        if why:
            res.update(ok=True, skipped=True, reason=why)
            return res
        cands = pdf_candidates(p)
        if not cands:
            # 按标题兜一层：OpenAlex 里没给 ID，但库里可能早就有这篇了，
            # 这时不该报「没有公开全文」，该报「你已经有了」
            nt = _norm_title(p.get("title"))
            if nt and len(nt) >= 12 and nt in idx["titles"]:
                res.update(ok=True, skipped=True, reason="已收录（标题相同）")
                return res
            res["reason"] = "这条没有公开全文（Europe PMC 多数如此），只能打开原文页"
            return res
        root = kb_paths()[0]
        if out_dir is None:
            out_dir = kb_paths()[1] / datetime.date.today().isoformat()
        else:
            out_dir = Path(out_dir)
            if not out_dir.is_absolute():
                # 相对路径按项目目录解释（测试与临时下载用），
                # 不要落到知识库里建出一个奇怪的分支目录
                out_dir = HERE / out_dir
        aid = _arxiv_id(p)
        name = _pdf_name(p, aid)
        errors = []
        for url, note in cands:
            try:
                path, size = _download_url(url, name, out_dir, progress)
            except Exception as exc:
                errors.append("%s: %s" % (note, exc))
                continue
            res.update(ok=True, path=str(path), bytes=size, source=note,
                       reason="来自" + note)
            if extract_text:
                try:
                    import kbscan
                    text, engine = kbscan.extract_first_page(path)
                    if text:
                        path.with_suffix(".txt").write_text(text, encoding="utf-8")
                        res["txt"] = True
                        res["reason"] += " · 首页文本 " + engine
                except Exception:
                    pass
            if aid:
                idx["ids"].add(aid)
            idx["titles"].add(_norm_title(p.get("title")))
            return res
        res["reason"] = "全部下载失败 → " + "；".join(errors)
        return res
    except Exception as exc:
        res["reason"] = "下载出错：%s" % exc
        return res


class Batch(object):
    """批量下载器：后台线程跑，逐篇回调，主线程拿到进度。

    用法：
        b = kb_download.Batch(papers, out_dir=None, on_one=cb, on_done=done)
        b.start(); b.cancel()

    out_dir 也可以传一个返回 Path 的 callable（每篇单独决定落到哪），
    最新研究页就用它让「会议名能对上 CVPR」的论文直接进 CVPR/。
    """

    def __init__(self, papers, out_dir=None, on_one=None, on_done=None,
                 direction="", limit=20, use_suggest=False, on_progress=None,
                 with_digest=False, first_offset=0):
        self.papers = list(papers or [])[:limit]
        self.out_dir = out_dir
        self.on_one = on_one
        self.on_done = on_done
        self.direction = direction
        # use_suggest=True 时先按会议名/方向猜分类目录（见 suggest_dir），
        # 猜不准仍回落到日期收件箱——不硬塞是这里的底线
        self.use_suggest = use_suggest
        self.on_progress = on_progress
        self.with_digest = with_digest
        self.first_offset = first_offset
        self._stop = threading.Event()
        self.results = []
        self.summary = {}
        self._th = None

    def cancel(self):
        self._stop.set()

    def start(self):
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()
        return self

    def _dir_for(self, p):
        base = self.out_dir() if callable(self.out_dir) else self.out_dir
        if self.use_suggest:
            cat = suggest_dir(self.direction, p.get("venue") or "")
            if cat:
                return kb_paths()[0] / cat
        return base

    def _run(self):
        ok = skip = fail = 0
        done_items = []
        total = max(1, len(self.papers))
        try:
            idx = existing_index()
        except Exception:
            idx = {"ids": set(), "sizes": set(), "titles": set(), "count": 0}
        for i, p in enumerate(self.papers):
            if self._stop.is_set():
                break
            if self.on_progress:
                try:
                    self.on_progress(i, total, p.get("title") or "")
                except Exception:
                    pass
            r = download(p, out_dir=self._dir_for(p), idx=idx, direction=self.direction)
            r["title"] = p.get("title", "")
            if r.get("ok") and not r.get("skipped"):
                done_items.append(p)
            self.results.append(r)
            if r["skipped"]:
                skip += 1
            elif r["ok"]:
                ok += 1
            else:
                fail += 1
            if self.on_one:
                try:
                    self.on_one(p, r)
                except Exception:
                    pass
        digest = ""
        if self.with_digest and done_items:
            try:
                digest = write_digest(done_items, self.direction, ok, skip, fail)
            except Exception:
                digest = ""
        summary = {"total": len(self.papers), "ok": ok, "skipped": skip,
                   "fail": fail, "cancelled": self._stop.is_set(),
                   "digest": digest}
        # 先记下来再回调：回调里要读 self._batch 判断是否结束，
        # 若在 on_done 之后才赋值，界面会看到「上一批还在下载」
        self.summary = summary
        if self.on_done:
            try:
                self.on_done(summary, self.results)
            except Exception:
                pass
        return summary


def write_digest(items, direction="", ok=0, skip=0, fail=0,
                 inbox=None, offset=0):
    """写一份「这批下载了什么」的速览 markdown 到收件箱。

    复用 kbscan 的格式约定（同样的标题层级、同样按日期命名），
    这样后续 AI 提炼流程不用区分它是定时抓的还是手动下的。
    已经写过同名文件就加序号，不覆盖——覆盖会丢掉当天更早那一批。
    """
    inbox = Path(inbox) if inbox else kb_paths()[1]
    inbox.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    lines = ["# 下载速览 " + now.strftime("%Y-%m-%d %H:%M"), ""]
    lines.append("> 方向: " + (direction or "未指定") +
                 " | 成功 " + str(ok) + " · 已在库 " + str(skip) +
                 " · 失败 " + str(fail))
    lines.append("")
    for i, p in enumerate(items, offset + 1):
        lines += [
            "## " + str(i) + ". " + (p.get("title") or ""),
            "- 来源: " + str(p.get("source") or "") +
            (" | " + str(p.get("venue")) if p.get("venue") else ""),
            "- 日期: " + str(p.get("published") or ""),
            "- 作者: " + ", ".join((p.get("authors") or [])[:6]),
            "- 链接: " + str(p.get("url") or p.get("doi") or ""),
            "- 摘要: " + (p.get("abstract") or "")[:400],
            "",
        ]
    base = inbox / ("下载速览-" + now.strftime("%Y-%m-%d_%H%M") + ".md")
    path = base
    n = 1
    while path.exists():
        n += 1
        path = inbox / ("下载速览-" + now.strftime("%Y-%m-%d_%H%M") + "-%d.md" % n)
    path.write_text("\n".join(lines), encoding="utf-8-sig")
    return str(path)


def stats(root=None):
    """知识库 PDF 总量与最近入库，给界面显示「联通状态」。"""
    root = root or kb_paths()[0]
    total, newest, week = 0, 0.0, 0
    today = datetime.date.today()
    if root.exists():
        for f in root.rglob("*.pdf"):
            total += 1
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            newest = max(newest, m)
            try:
                d = datetime.date.fromtimestamp(m)
                if (today - d).days <= 7:
                    week += 1
            except Exception:
                pass
    return {"root": str(root), "exists": root.exists(), "pdf_total": total,
            "added_7d": week,
            "newest": (datetime.datetime.fromtimestamp(newest).strftime("%Y-%m-%d")
                       if newest else "")}


if __name__ == "__main__":
    import sys
    s = stats()
    print(json.dumps(s, ensure_ascii=False, indent=2))
    print("分类目录:", list_dirs())
    print("已有 PDF 索引:", len(existing_index()["titles"]), "个标题")
    sys.exit(0)