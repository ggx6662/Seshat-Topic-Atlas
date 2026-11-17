#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KB-Monitor: 按研究方向定期抓取 arXiv 新论文（机械环节）。

AI 提炼环节由 ccf-literature-monitor / deep-research 处理：
读取本脚本生成的【新论文速览】md 与落库 PDF，再写入 索引.md / 分类总结。

用法:
  python kbscan.py --dry-run            # 只列出本周候选，不落库
  python kbscan.py                      # 抓候选 -> 下载 PDF -> 抽首页文本 -> 写速览+日志
  python kbscan.py --days 14 --max-downloads 8
"""
import argparse
import concurrent.futures
import datetime
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:
    import app_paths as _AP
    _RES = _AP.res        # 只读资源：打包后在 _MEIPASS
    _DATA = _AP.data      # 可写数据：打包后在 exe 旁边
except Exception:         # 单独跑构建脚本/测试时退回旧行为
    _RES = lambda n: HERE / n
    _DATA = lambda n: HERE / n
NS = {"a": "http://www.w3.org/2005/Atom"}
UA = {"User-Agent": "kb-monitor/0.1 (research-kb)"}
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_ABS = "https://arxiv.org/abs/{}"
ARXIV_PDF = "https://arxiv.org/pdf/{}"


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg.setdefault("kb_path", r"G:\相关内容\AuthorKit27\知识库")
    cfg.setdefault("inbox_dir", "新论文")
    cfg.setdefault("days_back", 7)
    cfg.setdefault("max_results_per_query", 8)
    cfg.setdefault("max_downloads", 6)
    cfg.setdefault("query_timeout", 20)
    cfg.setdefault("query_workers", 4)
    cfg.setdefault(
        "strict_domain_terms",
        ["rgb-t", "rgb-ir", "infrared", "thermal", "mamba", "cross-modal",
         "state space", "frequency", "multimodal", "hyperspectral", "uav", "drone"],
    )
    cfg.setdefault(
        "task_terms",
        ["detection", "fusion", "tracking", "segmentation", "classification",
         "recognition", "yolo"],
    )
    cfg.setdefault("queries", ["all:mamba AND all:RGB-T"])
    return cfg


def api_query(query, max_results, timeout=20):
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = ARXIV_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_entries(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for e in root.findall("a:entry", NS):
        def txt(tag):
            node = e.find(tag, NS)
            return (node.text or "").strip() if node is not None else ""
        aid = txt("a:id").rsplit("/abs/", 1)[-1].strip()
        title = re.sub(r"\s+", " ", txt("a:title"))
        published = txt("a:published")[:10]
        summary = re.sub(r"\s+", " ", txt("a:summary"))
        authors = [a.text.strip() for a in e.findall("a:author/a:name", NS)]
        if aid and title:
            out.append({
                "id": aid,
                "title": title,
                "published": published,
                "authors": authors,
                "summary": summary[:600],
            })
    return out


def relevant(entry, cfg):
    t = entry["title"].lower()
    domain_hit = any(term in t for term in cfg["strict_domain_terms"])
    task_hit = any(term in t for term in cfg["task_terms"])
    return domain_hit and task_hit


def load_seen(path):
    if path.exists():
        try:
            return set(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_seen(path, ids):
    path.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def download_pdf(entry, out_dir):
    url = ARXIV_PDF.format(entry["id"])
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as resp:
        clen = resp.headers.get("Content-Length")
        if clen and int(clen) > 25 * 1024 * 1024:
            raise ValueError("PDF too large (" + str(int(clen) // 1048576) + " MB), skipped")
        data = resp.read()
    pdf_path = out_dir / _pdf_filename(entry)
    pdf_path.write_bytes(data)
    return pdf_path


def _pdf_filename(entry):
    stem = (re.sub(r"[^\w\-]+", "_", entry["title"])[:70] + "_"
            + entry["id"].replace(".", "_"))
    return stem + ".pdf"


def download_pdf_stream(entry, out_dir, progress=None):
    url = ARXIV_PDF.format(entry["id"])
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        clen = resp.headers.get("Content-Length")
        total = int(clen) if clen else 0
        if total and total > 25 * 1024 * 1024:
            raise ValueError("PDF too large (" + str(total // 1048576) + " MB), skipped")
        pdf_path = out_dir / _pdf_filename(entry)
        part = pdf_path.with_suffix(".part")
        got, last_pct = 0, -1
        with open(part, "wb") as fh:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                if progress:
                    frac = (got / float(total)) if total else None
                    pct = int(frac * 100) if frac is not None else None
                    if pct is None or pct != last_pct:
                        last_pct = pct
                        try:
                            progress(got, total, frac)
                        except Exception:
                            pass
        if total and got != total:
            raise ValueError("incomplete PDF (" + str(got) + "/" + str(total) + " bytes)")
        part.replace(pdf_path)
        return pdf_path


def extract_first_page(pdf_path):
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        return text, "pdfplumber"
    except Exception:
        pass
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        text = doc[0].get_text("text") if doc.page_count > 0 else ""
        doc.close()
        return text, "pymupdf"
    except Exception:
        return "", "unavailable"


def write_digest(items, skipped, inbox):
    if not items:
        return None
    today = datetime.date.today().isoformat()
    lines = ["# 新论文速览 " + today, ""]
    lines.append("> 由 kbscan.py 自动抓取；AI 提炼请基于本文件 + PDF 全文，处理后追加到 索引.md / 分类总结，并把评审结论写进 更新日志.md。")
    lines.append("")
    lines.append("新增 " + str(len(items)) + " 篇（另有 " + str(skipped) + " 篇因超过下载上限未拉全文，见候选清单）。")
    lines.append("")
    for i, it in enumerate(items, 1):
        authors = ", ".join(it["authors"][:6])
        lines += [
            "## " + str(i) + ". " + it["title"],
            "- arXiv: " + ARXIV_ABS.format(it["id"]),
            "- 日期: " + it["published"],
            "- 作者: " + authors,
            "- 摘要: " + it["summary"][:500],
            "",
        ]
    digest = inbox / ("新论文速览-" + today + ".md")
    digest.write_text("\n".join(lines), encoding="utf-8-sig")
    return digest


def append_changelog(inbox, today, items):
    log = inbox / "更新日志.md"
    entry = ["", "## " + today, ""]
    for it in items:
        entry.append("- " + it["published"] + " | " + it["title"] + " | " + ARXIV_ABS.format(it["id"]))
    if log.exists():
        text = log.read_text(encoding="utf-8-sig").rstrip() + "\n" + "\n".join(entry)
    else:
        text = "# 新论文更新日志\n" + "\n".join(entry)
    log.write_text(text + "\n", encoding="utf-8-sig")


def main():
    ap = argparse.ArgumentParser(description="按研究方向抓取 arXiv 新论文")
    ap.add_argument("--config", default=str(_RES("config.json")))
    ap.add_argument("--days", type=int, default=None, help="覆盖 config.days_back")
    ap.add_argument("--max-downloads", type=int, default=None, help="覆盖 config.max_downloads")
    ap.add_argument("--out", default=None, help="覆盖收件目录（测试用）")
    ap.add_argument("--dry-run", action="store_true", help="只列候选，不落库")
    args = ap.parse_args()

    cfg = load_config(args.config)
    days = args.days if args.days is not None else cfg["days_back"]
    max_downloads = args.max_downloads if args.max_downloads is not None else cfg["max_downloads"]
    max_per_query = cfg["max_results_per_query"]
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    kb = Path(cfg["kb_path"])
    inbox = Path(args.out) if args.out else kb / cfg["inbox_dir"]
    seen_file = _DATA("seen_ids.json")
    seen = load_seen(seen_file)

    candidates, seen_ids = [], set()

    def fetch_one(q):
        last = None
        for _attempt in range(2):
            try:
                xml_text = api_query(q, max_per_query, timeout=cfg["query_timeout"])
                return q, parse_entries(xml_text), None
            except Exception as exc:
                last = exc
                time.sleep(1.0)
        return q, [], last

    workers = max(1, min(int(cfg["query_workers"]), len(cfg["queries"])))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_one, q) for q in cfg["queries"]]
        for fut in concurrent.futures.as_completed(futures):
            q, entries, err = fut.result()
            if err:
                print("QUERY FAIL: " + q + " -> " + str(err), file=sys.stderr)
                continue
            for e in entries:
                if e["id"] in seen or e["id"] in seen_ids:
                    continue
                if e["published"] < cutoff:
                    continue
                if not relevant(e, cfg):
                    continue
                seen_ids.add(e["id"])
                candidates.append(e)

    candidates.sort(key=lambda x: x["published"], reverse=True)
    print("== 候选（近 " + str(days) + " 天，标题命中）: " + str(len(candidates)) + " 篇 ==")
    for it in candidates:
        print("- " + it["published"] + " | " + it["title"] + " | " + ARXIV_ABS.format(it["id"]))

    if args.dry_run:
        print("DRY-RUN: 不落库。确认后去掉 --dry-run 即可执行抓取。")
        return 0

    today = datetime.date.today().isoformat()
    day_dir = inbox / today
    day_dir.mkdir(parents=True, exist_ok=True)
    downloaded, failed = [], []
    for it in candidates[:max_downloads]:
        try:
            pdf_path = download_pdf(it, day_dir)
            text, engine = extract_first_page(pdf_path)
            if text:
                (pdf_path.with_suffix(".txt")).write_text(text, encoding="utf-8")
            it["text_engine"] = engine
            downloaded.append(it)
            print("DL OK: " + it["id"] + " 首页文本=" + engine)
        except Exception as exc:
            # 失败要留痕：以前这里只 print 到 stderr，计划任务里根本没人看得到，
            # 而且失败条目仍会被记入 seen，等于「这篇以后永远不再尝试」
            failed.append({"id": it["id"], "title": it["title"],
                           "published": it["published"], "error": str(exc)})
            print("DL FAIL: " + it["id"] + " -> " + str(exc), file=sys.stderr)
    skipped = max(0, len(candidates) - max_downloads)

    digest = write_digest(downloaded, skipped, inbox)
    if downloaded:
        append_changelog(inbox, today, downloaded)
    if skipped:
        # 超过上限没拉的，也不进 seen —— 下次运行才有机会补上
        with open(_DATA("download_failures.json"), "w", encoding="utf-8") as fh:
            json.dump({"time": datetime.datetime.now().isoformat(timespec="minutes"),
                       "downloaded": len(downloaded), "failed": failed,
                       "over_limit": skipped,
                       "over_limit_ids": [it["id"] for it in candidates[max_downloads:]]},
                      fh, ensure_ascii=False, indent=2)
    elif failed:
        with open(_DATA("download_failures.json"), "w", encoding="utf-8") as fh:
            json.dump({"time": datetime.datetime.now().isoformat(timespec="minutes"),
                       "downloaded": len(downloaded), "failed": failed},
                      fh, ensure_ascii=False, indent=2)
    # 只记成功下载的。旧版这里写的是 seen | 全部候选，导致下载失败的论文
    # 也被标记为「见过」，第二天起就被永久跳过——真实数据里很难发现，
    # 因为速览里只会看到「今天没有新论文」。
    seen |= {it["id"] for it in downloaded}
    save_seen(seen_file, seen)
    print("完成: " + (str(digest) if digest else "本次无新增，未生成空速览"))
    if failed:
        print("失败 " + str(len(failed)) + " 篇（详见 download_failures.json）")
    print("说明: AI 提炼步骤请由 Codex 会话执行（提示词见 automation-prompt.md）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
