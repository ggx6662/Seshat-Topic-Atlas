"""清洗 ORCID 导出里的标题字段。

背景
----
`competition/site/data/papers.json` 的 title 直接来自 ORCID 的发表记录，
有些作者把自己的标题字段填成了富文本（`<i>`、`<sub>`、`<p style=...>`），
甚至有把整段 HTML 贴进去的（`<div> <div> <span>…</span> </div> </div>`）。
另外个别标题里带 HTML 实体（`&lt;bold&gt;`、`&amp;`）。

这些字段直接渲染到网页和 README 截图里就变成：

    <div> <div> <span>A New Social Contract: How an AI Sovereign Wealth Fund…

清洗规则（顺序很重要，2026-11-21 第一版在这里翻过车）
--------
1. 反复 `html.unescape` 直到不再变化（实体可能嵌套，`&amp;lt;` → `&lt;` → `<`）；
2. 把标签**原地**换成空串，而不是换成空格 —— 换成空格会把
   `<sub>y</sub>` 变成 `R y`、`<i>n</i>-Particle` 变成 `n -Particle`；
3. 但 `a</b><i>b` 这种「两个真词被标签分开」的情况，空串会让它们粘成 `ab`，
   所以只有**标签前面紧邻字母或数字、且标签后面也紧邻字母或数字**时，
   才在该处补一个空格；
4. 括号内/外的多余空档（`( Adansonia`、`L.  )`）压掉；
5. 压平连续空白、去首尾空白；
6. 清完为空就退回原值，绝不产生空标题。

用法
----
    python tools_clean_titles.py --dry      # 只看会改什么，不写文件
    python tools_clean_titles.py            # 写回 papers.json（自动备份 .pre-titleclean）

`sync_from_site.py` 会调用 `clean_papers_file()`，所以同步一次也会顺带清好。
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPERS = HERE / "competition" / "site" / "data" / "papers.json"
PAPERS_DIST = HERE / "competition" / "site" / "dist" / "data" / "papers.json"

_TAG = re.compile(r"<[a-zA-Z/][^<>]{0,199}>")
_STRAY_LT = re.compile(r"[<>]")
_WS = re.compile(r"\s+")
_ENTITY = re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#x[0-9a-fA-F]{1,6});")
# `<` 后面紧跟字母或斜杠才算标签开头；这样 `0<α<2`、`a<b` 不会被当成 HTML
_LOOKS_LIKE_TAG = re.compile(r"<[a-zA-Z/][^<>]{0,199}>")
_MARKUP_HINT = re.compile(r"[<>]|&(?:amp|lt|gt|quot|apos|nbsp|#\d+|#x[0-9a-fA-F]+);")


def _drop_tag(match: re.Match) -> str:
    """把单个标签换成「必要时一个空格」。

    只有标签两边都是词字符时才补空格，避免 `n-Particle` → `n -Particle` 这种误伤。
    """
    text = match.string
    before = text[match.start() - 1] if match.start() else ""
    after = text[match.end()] if match.end() < len(text) else ""
    if before.isalnum() and after.isalnum():
        return " "
    return ""


def _squeeze_parens(text: str) -> str:
    """压掉括号里侧贴着的多余空格：`( Adansonia` → `(Adansonia`。"""
    out = re.sub(r"\(\s+", "(", text)
    out = re.sub(r"\s+\)", ")", out)
    out = re.sub(r"\s+([,;:.\]])", r"\1", out)
    return out


def _to_plain(text: str) -> str:
    """把标签换成纯文本，重点是别在错误的地方留下空格。

    判断一个标签该变成什么，看它**原来**卡在什么之间：

      前一个字符 → 标签 → 后一个字符        结果
      ─────────────────────────────────────────────
      字母数字      标签       字母数字       一个空格（`a</b><i>b` → `a b`）
      其它任何情况  标签       其它任何情况   直接删除

    但「字母数字—标签—字母数字」里有一类不该补空格：上下标。
    `R<sub>y</sub>`、`<i>L</i><sub>1</sub>` 中间的那个标签，左右都贴着字母数字，
    可它们本来就是同一个记号。判据是「这个标签对本身是上下标标签
    （sub/sup）、或者是紧挨着上下标的一段行内标签」—— 这类直接删除。

    先按**原始**文本定位每个标签，再统一拼接，避免边删边判导致位置错乱。
    """
    spans = [(m.start(), m.end()) for m in _TAG.finditer(text)]
    if not spans:
        return text

    # 哪些标签属于「上下标字样」：sub/sup 本身，或与它们紧邻的其它行内标签
    scripty: set[int] = set()
    for idx, (s, e) in enumerate(spans):
        name = text[s:e].lstrip("<").lstrip("/").split()[0].rstrip(">").split("=")[0].lower()
        if name in ("sub", "sup"):
            scripty.add(idx)
    for idx in list(scripty):
        for j in range(idx + 1, len(spans)):
            if spans[j][0] != spans[j - 1][1]:
                break
            scripty.add(j)
        for j in range(idx - 1, -1, -1):
            if spans[j][1] != spans[j + 1][0]:
                break
            scripty.add(j)

    out = []
    prev = 0
    for idx, (s, e) in enumerate(spans):
        out.append(text[prev:s])
        before = text[s - 1] if s else ""
        after = text[e] if e < len(text) else ""
        if idx not in scripty and before.isalnum() and after.isalnum():
            out.append(" ")
        prev = e
    out.append(text[prev:])
    return "".join(out)


def clean_title(text: str) -> str:
    """把一条标题清洗成纯文本。已经干净的原样返回。"""
    if not isinstance(text, str) or not text:
        return text
    out = text
    # 实体可能嵌套两三层：&amp;lt;bold&amp;gt; → &lt;bold&gt; → <bold> → bold
    for _ in range(4):
        nxt = html.unescape(out)
        if nxt == out:
            break
        out = nxt

    if "<" in out or ">" in out:
        out = _to_plain(out)
        out = _squeeze_parens(out)

    out = _WS.sub(" ", out).strip()
    return out or text


def is_dirty(text: str) -> bool:
    """标题里有没有真正的 HTML 标签或实体。

    只认「像标签的尖括号」：`<` 后面跟字母或 `/` 才算，所以数学表达式
    `0<α<2`、`a<b` 不会被误判成需要清洗。
    """
    if not isinstance(text, str):
        return False
    return bool(_LOOKS_LIKE_TAG.search(text) or _ENTITY.search(text))


def _items(doc):
    return doc if isinstance(doc, list) else (doc.get("papers") or [])


def clean_papers_file(path: Path | None = None, dry: bool = False,
                      backup_suffix: str = ".pre-titleclean") -> dict:
    """清洗一个 papers.json。返回 {total, dirty, changed, samples, written}。"""
    path = Path(path or PAPERS)
    if not path.exists():
        return {"total": 0, "dirty": 0, "changed": 0, "samples": [],
                "written": False, "path": str(path)}

    doc = json.loads(path.read_text(encoding="utf-8"))
    items = _items(doc)
    total = len(items)
    dirty = 0
    changed = 0
    samples: list[tuple[str, str]] = []

    for rec in items:
        if not isinstance(rec, dict):
            continue
        old = rec.get("title")
        if not is_dirty(old):
            continue
        dirty += 1
        new = clean_title(old)
        if new != old:
            changed += 1
            if len(samples) < 6:
                samples.append((old, new))
            rec["title"] = new

    written = False
    if changed and not dry:
        if backup_suffix and path.exists():
            shutil.copy2(path, str(path) + backup_suffix)
        raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        path.write_text(raw, encoding="utf-8")
        written = True

    return {"total": total, "dirty": dirty, "changed": changed,
            "samples": samples, "written": written, "path": str(path)}


def is_dirty_file(path: Path) -> bool:
    """粗略判断文件里还剩不剩带标签的标题。"""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return False
    return any(is_dirty(r.get("title")) for r in _items(doc) if isinstance(r, dict))


def sync_dist(src: Path | None = None) -> bool:
    """把源 papers.json 复制到 dist，让两边一致。返回是否复制。"""
    src = Path(src or PAPERS)
    if not src.exists() or not PAPERS_DIST.parent.exists():
        return False
    shutil.copy2(src, PAPERS_DIST)
    return True


def main(argv: list[str]) -> int:
    dry = "--dry" in argv
    print("清洗 ORCID 标题字段%s" % ("（dry run，不写文件）" if dry else ""))
    r = clean_papers_file(dry=dry)
    print("  %s" % r["path"])
    print("  共 %d 条，带标记 %d 条，实际改写 %d 条，%s"
          % (r["total"], r["dirty"], r["changed"],
             "已写回" if r["written"] else ("dry run 未写" if dry else "无需改写")))
    for old, new in r["samples"]:
        print("    - %s" % old[:90])
        print("    + %s" % new[:90])
    if r["written"] and sync_dist():
        print("  已同步到 dist/data/papers.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))