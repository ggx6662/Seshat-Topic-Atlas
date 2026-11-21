"""把「功能说明手册.md」转成 Word 文档。

只处理本手册实际用到的 Markdown 子集：
标题、段落、无序/有序列表、表格、代码块、引用块、行内 **粗体** / `代码` / 链接。

用法：python make_handbook_docx.py
"""

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

HERE = Path(__file__).resolve().parent
# 手册正文已归档到 docs/origin/，产物跟它放一起，不再弄脏仓库根目录
SRC = HERE / "docs" / "origin" / "功能说明手册-2026-11-15.md"
OUT = HERE / "docs" / "origin" / "功能说明手册-2026-11-15.docx"

CN = "微软雅黑"
MONO = "Consolas"
INK = RGBColor(0x1A, 0x1A, 0x1A)
INK2 = RGBColor(0x55, 0x5F, 0x6B)
ACCENT = RGBColor(0x0B, 0x63, 0x72)
CODE_BG = "F2F4F7"


def set_cn_font(run, name=CN, size=None, bold=None, color=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def shade(cell_or_par, hex_fill):
    el = cell_or_par._element
    pr = el.get_or_add_tcPr() if hasattr(el, "get_or_add_tcPr") else el.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    pr.append(shd)


INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def add_inline(par, text, size=10.5, color=INK):
    """把 **粗体**、`代码`、[文字](链接) 写进段落。"""
    pos = 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            r = par.add_run(text[pos:m.start()])
            set_cn_font(r, size=size, color=color)
        tok = m.group(0)
        if tok.startswith("**"):
            r = par.add_run(tok[2:-2])
            set_cn_font(r, size=size, bold=True, color=color)
        elif tok.startswith("`"):
            r = par.add_run(tok[1:-1])
            set_cn_font(r, MONO, size=size - 0.5, color=ACCENT)
        else:
            label = tok[1:tok.index("]")]
            href = tok[tok.index("(") + 1:-1]
            if href.startswith("#"):
                r = par.add_run(label)
                set_cn_font(r, size=size, color=color)
            else:
                r = par.add_run(label + "（" + href + "）")
                set_cn_font(r, size=size - 0.5, color=INK2)
        pos = m.end()
    if pos < len(text):
        r = par.add_run(text[pos:])
        set_cn_font(r, size=size, color=color)


def kill_borders(table):
    tbl = table._tbl
    pr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + edge)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "D8DEE6")
        borders.append(e)
    pr.append(borders)


def force_width(table, width_cm, cols):
    table.autofit = False
    for row in table.rows:
        for cell in row.cells:
            cell.width = Cm(width_cm / max(1, cols))


def add_table(doc, rows):
    cols = len(rows[0])
    # 第一列/第二列内容通常更长，简单按内容长度分配宽度
    lens = [0] * cols
    for r in rows:
        for i, c in enumerate(r):
            lens[i] = max(lens[i], len(c))
    total = sum(lens) or 1
    usable = 16.4
    table = doc.add_table(rows=0, cols=cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    kill_borders(table)
    for ri, r in enumerate(rows):
        cells = table.add_row().cells
        for ci in range(cols):
            cell = cells[ci]
            cell.width = Cm(usable * lens[ci] / total)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            txt = r[ci] if ci < len(r) else ""
            add_inline(p, txt, size=9.5, color=INK)
            if ri == 0:
                for run in p.runs:
                    run.font.bold = True
                shade(cell, "EAF1F4")
            elif ri % 2 == 0:
                shade(cell, "FAFBFC")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    _ = cols


def add_code(doc, lines):
    for i, ln in enumerate(lines):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = Pt(4 if i == 0 else 0)
        pf.space_after = Pt(4 if i == len(lines) - 1 else 0)
        pf.left_indent = Cm(0.4)
        pf.line_spacing = 1.0
        r = p.add_run(ln if ln else " ")
        set_cn_font(r, MONO, size=9, color=RGBColor(0x22, 0x22, 0x22))
        shade(p, CODE_BG)


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def convert():
    text = SRC.read_text(encoding="utf-8")
    doc = Document()

    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.2)
    sec.right_margin = Cm(2.2)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = CN
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CN)

    lines = text.splitlines()
    i = 0
    n = len(lines)
    in_toc = False
    while i < n:
        raw = lines[i]
        line = raw.rstrip()

        if not line.strip():
            i += 1
            continue

        # 分隔线
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            ppr = p._element.get_or_add_pPr()
            bdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "4")
            bottom.set(qn("w:space"), "1")
            bottom.set(qn("w:color"), "D8DEE6")
            bdr.append(bottom)
            ppr.append(bdr)
            i += 1
            continue

        # 代码块
        if line.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            add_code(doc, buf)
            continue

        # 表格
        if line.lstrip().startswith("|"):
            block = []
            while i < n and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            rows = [split_row(b) for b in block if not re.match(r"^\s*\|[\s:|-]+\|\s*$", b)]
            if rows:
                add_table(doc, rows)
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if level == 1:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(6)
                p.paragraph_format.space_after = Pt(10)
                add_inline(p, title, size=22, color=INK)
                for r in p.runs:
                    r.font.bold = True
                i += 1
                continue
            if title == "目录":
                in_toc = True
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.space_before = Pt(16 if level == 2 else 10)
            pf.space_after = Pt(6 if level == 2 else 4)
            pf.keep_with_next = True
            add_inline(p, title, size=15 if level == 2 else 12, color=ACCENT)
            for r in p.runs:
                r.font.bold = True
            i += 1
            continue

        # 引用
        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip()[1:].strip())
                i += 1
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = Cm(0.6)
            pf.space_before = Pt(6)
            pf.space_after = Pt(6)
            add_inline(p, "  ".join(x for x in buf if x), size=10, color=INK2)
            shade(p, "F5F7FA")
            continue

        # 列表
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            indent = len(m.group(1))
            bullet = m.group(2)
            body = m.group(3)
            p = doc.add_paragraph(style="List Bullet" if bullet in "-*" else "List Number")
            pf = p.paragraph_format
            pf.left_indent = Cm(0.7 + indent * 0.45)
            pf.space_before = Pt(1)
            pf.space_after = Pt(1)
            if in_toc:
                body = body.split("](#")[0] if "](" in body else body
                body = re.sub(r"^\[|\]$", "", body)
            add_inline(p, body, size=10.5)
            i += 1
            continue

        # 普通段落
        in_toc = False
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = Pt(3)
        pf.space_after = Pt(3)
        pf.line_spacing = 1.35
        add_inline(p, line.strip(), size=10.5)
        i += 1

    doc.save(OUT)
    return OUT


def verify(path):
    d = Document(path)
    paras = [p.text for p in d.paragraphs if p.text.strip()]
    tables = len(d.tables)
    print("paragraphs:", len(paras))
    print("tables:", tables)
    head = paras[:3]
    print("head:", " | ".join(head))
    joined = "\n".join(paras)
    for key in ("功能说明手册", "选题工坊", "文献空白", "已知限制总表", "复核清单",
                "数据文件：哪个文件管什么", "大模型接入"):
        print(("  OK  " if key in joined else "  MISS"), key)


if __name__ == "__main__":
    out = convert()
    print("saved:", out)
    verify(out)
    sys.exit(0)