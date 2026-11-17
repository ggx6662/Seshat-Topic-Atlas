"""从 arXiv OAI-PMH 按时间窗口抓 CS 全量元数据。

为什么不用 arXiv API 分页
------------------------
实测 `start + max_results > 10000` 必定 HTTP 500，按季度切窗口又慢到 120 秒/页。
OAI-PMH 的 ListRecords 能**一次请求拿完一个日期窗口的全部记录**，
再用 resumptionToken 续页，是拿全量唯一现实的路。

关键事实（都实测过）
--------------------
* 集名是顶级的：`cs` / `math` / `q-bio`，**不是** `cs.CV`，写 `set=cs.CV` 报 `Set does not exist`。
* `datestamp` 是「最后更新时间」，不是首次提交时间。所以一篇 2010 年的论文若
  2025 年被更新过，会落在 2025 年的窗口里。**不漏，但时间归属可能偏后**。
  对「这个方向全世界做过没有」这个问题没有影响。
* 单个窗口（2024-01-01~02）57 万字节 / 571 条 / 约 50 秒。窗口越大越慢，
  7 天窗口通常 1 次就够，偶尔需要 resumptionToken 续 1~2 次。

输出
----
`G:\\kb-vector\\arxiv_cs\\<from>_<until>.jsonl`，每行一条：

    {"id","created","updated","title","abstract","authors","categories","doi"}

增量与断点：已存在的窗口文件直接跳过，所以中断后重跑只补缺的窗口。

用法
----
    python oai_fetch.py --days 3650 --step 7
    python oai_fetch.py --days 3650 --step 7 --set cs --out G:\kb-vector\arxiv_cs
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://export.arxiv.org/oai2"
UA = "kb-vector/1.0 (research topic workbench; contact: local)"

# 单个窗口连续失败多少次就放弃这个窗口（网络抖动容忍）
MAX_RETRY = 4
# 相邻请求之间的最小间隔。OAI 对频率比 API 宽松，但节奏太快会 503。
GAP = 3.0


def _get(params, timeout=180):
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(MAX_RETRY):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last = "HTTP %s" % exc.code
            # 503 是限流，退避要长
            wait = (attempt + 1) * (30 if exc.code == 503 else 8)
        except Exception as exc:
            last = "%s: %s" % (type(exc).__name__, exc)
            wait = (attempt + 1) * 8
        time.sleep(wait)
    raise RuntimeError("OAI 请求失败（%s）：%s" % (last, url[:200]))


def _texts(chunk, tag):
    return re.findall(r"<%s>(.*?)</%s>" % (tag, tag), chunk, re.S)


def _one(chunk, tag):
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), chunk, re.S)
    return m.group(1) if m else ""


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&quot;", '"').replace("&apos;", "'").replace("&#39;", "'")
    return re.sub(r"\s+", " ", s).strip()


def parse_records(xml):
    """把一批 <record> 解析成 dict 列表。删除了的条目（status=deleted）直接跳过。"""
    out = []
    for chunk in re.findall(r"<record>(.*?)</record>", xml, re.S):
        if re.search(r'status\s*=\s*["\']deleted', chunk):
            continue
        meta_m = re.search(r"<metadata>(.*?)</metadata>", chunk, re.S)
        if not meta_m:
            continue
        meta = meta_m.group(1)
        aid = _clean(_one(meta, "id"))
        if not aid:
            continue
        title = _clean(_one(meta, "title"))
        abstract = _clean(_one(meta, "abstract"))
        if not title and not abstract:
            continue
        authors = []
        for a in re.findall(r"<author>(.*?)</author>", meta, re.S):
            kn = _clean(_one(a, "keyname"))
            fn = _clean(_one(a, "forenames"))
            nm = ("%s %s" % (fn, kn)).strip()
            if nm:
                authors.append(nm)
        out.append({
            "id": aid,
            "created": _clean(_one(meta, "created")),
            "updated": _clean(_one(meta, "updated")),
            "title": title,
            "abstract": abstract,
            "authors": authors[:12],
            "categories": _clean(_one(meta, "categories")),
            "doi": _clean(_one(meta, "doi")),
        })
    return out


def fetch_window(setname, d0, d1, log=None):
    """抓 [d0, d1] 这个窗口的全部记录。自动跟随 resumptionToken。"""
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "arXiv",
        "from": d0.isoformat(),
        "until": d1.isoformat(),
    }
    if setname:
        params["set"] = setname
    rows = []
    page = 0
    while True:
        page += 1
        xml = _get(params)
        if "<error" in xml[:2000]:
            raise RuntimeError("OAI 返回错误：" + _clean(xml)[:200])
        rows.extend(parse_records(xml))
        tok = re.search(r"<resumptionToken[^>]*>([^<]+)</resumptionToken>", xml)
        if not tok:
            break
        if log and page % 5 == 0:
            log("    · 续页 %d，累计 %d 条" % (page, len(rows)))
        params = {"verb": "ListRecords", "resumptionToken": tok.group(1).strip()}
        time.sleep(GAP)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3650, help="向前覆盖多少天")
    ap.add_argument("--step", type=int, default=7, help="每个窗口多少天")
    ap.add_argument("--set", default="cs", help="OAI 集名（cs/math/q-bio…，空串表示全部）")
    ap.add_argument("--out", default=r"G:\kb-vector\arxiv_cs")
    ap.add_argument("--until", default="", help="停止日期 YYYY-MM-DD，默认今天")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    end = dt.date.fromisoformat(args.until) if args.until else dt.date.today()
    start = end - dt.timedelta(days=args.days)

    windows = []
    d = start
    while d <= end:
        d1 = min(d + dt.timedelta(days=args.step - 1), end)
        windows.append((d, d1))
        d = d1 + dt.timedelta(days=1)

    total = 0
    done = 0
    t_all = time.time()
    print("窗口 %d 个（%s ~ %s，每窗 %d 天，集 %r）"
          % (len(windows), start, end, args.step, args.set), flush=True)

    for d0, d1 in windows:
        fp = out_dir / ("%s_%s.jsonl" % (d0.isoformat(), d1.isoformat()))
        if fp.exists():
            done += 1
            with open(fp, "r", encoding="utf-8") as f:
                n = sum(1 for _ in f)
            total += n
            continue
        t0 = time.time()
        try:
            rows = fetch_window(args.set, d0, d1, log=print)
        except Exception as exc:
            print("  ✗ %s~%s 失败：%s" % (d0, d1, exc), flush=True)
            time.sleep(20)
            continue
        tmp = fp.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, fp)
        total += len(rows)
        done += 1
        el = time.time() - t_all
        print("  ✓ %s~%s  %5d 条  %4.1fs  累计 %7d 条  已用 %.0f 分钟  (%.0f%%)"
              % (d0, d1, len(rows), time.time() - t0, total, el / 60,
                 100.0 * done / max(1, len(windows))), flush=True)
        time.sleep(GAP)

    print("完成：%d 个窗口，累计 %d 条，用时 %.1f 分钟"
          % (done, total, (time.time() - t_all) / 60), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())