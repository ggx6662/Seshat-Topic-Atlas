# -*- coding: utf-8 -*-
"""从文件名里的 arXiv 编号反查官方标题，覆盖疑似脏的标题。

`paper_meta` 没存 arxiv id，但文件名常带 `YYMM_NNNNNvN`（如 2610_22434v1）。
arXiv 官方 API 一次可以查多个 id，返回的是干净标题 —— 比从 PDF 前几页
正则抽标题可靠得多（PDF 是双栏排版，抽成一行后没有可靠分隔符）。

只覆盖「疑似脏」的记录，干净的保持原样（避免把真标题换成另一个真标题）。
"""
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

P = "paper_meta.json"
API = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}

# 文件名里的 arXiv 编号：2610_22434v1 / 2610.22434v1 / 2403_15432
ID_RX = re.compile(r"(?<!\d)(\d{4})[_\-.](\d{4,5})(?:v\d+)?(?!\d)")


def arxiv_id(path):
    for chunk in reversed(re.split(r"[\\/]", path)):
        m = ID_RX.search(chunk)
        if m:
            return "%s.%s" % (m.group(1), m.group(2))
    return None


def is_dirty(t):
    """疑似脏：过长 / 含上标数字 / 含邮箱 / 小写开头 / 词太少。"""
    t = (t or "").strip()
    if not t:
        return True
    if len(t) > 150:
        return True
    if re.search(r"[A-Za-z]@|https?://|doi\.org", t, re.I):
        return True
    if re.search(r"[A-Z][a-z]+\d", t):
        return True
    if t[0].islower() or len(t.split()) < 4:
        return True
    return False


def fetch(ids):
    """一次最多 40 个 id，返回 {id: title}。"""
    out = {}
    for i in range(0, len(ids), 40):
        batch = ids[i:i + 40]
        url = "%s?%s" % (API, urllib.parse.urlencode(
            {"id_list": ",".join(batch), "max_results": len(batch)}))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kb-vector/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                xml = r.read()
        except Exception as exc:
            print("  批次失败 %d: %r" % (i, exc), file=sys.stderr)
            time.sleep(3)
            continue
        root = ET.fromstring(xml)
        for e in root.findall("a:entry", NS):
            iu = (e.find("a:id", NS).text or "").strip()
            m = re.search(r"abs/([\d.]+)v?\d*$", iu)
            tt = e.find("a:title", NS)
            if m and tt is not None:
                out[m.group(1).rstrip("v")] = " ".join((tt.text or "").split())
        time.sleep(3)          # arXiv API 要求 3 秒一次
    return out


def main():
    d = json.load(io.open(P, encoding="utf-8"))
    ps = d["papers"]
    need = {}
    for path, v in ps.items():
        if not is_dirty(v.get("title")):
            continue
        aid = arxiv_id(path)
        if aid:
            need[path] = aid
    print("疑似脏且能从文件名认出 arXiv 编号:", len(need))
    if not need:
        return
    got = fetch(sorted(set(need.values())))
    print("arXiv 返回:", len(got))
    n = 0
    for path, aid in need.items():
        t = got.get(aid)
        if t and len(t) >= 10:
            ps[path]["title"] = t
            ps[path]["title_src"] = "arxiv"
            n += 1
            if n <= 8:
                print("  %s -> %s" % (aid, t[:80]))
    json.dump(d, io.open(P, "w", encoding="utf-8"), ensure_ascii=False,
              separators=(",", ":"))
    print("覆盖:", n)


if __name__ == "__main__":
    main()