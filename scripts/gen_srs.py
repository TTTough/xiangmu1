# -*- coding: utf-8 -*-
"""把需求规格说明书的 Markdown 转换为 Word（docx），并可选地通过 Word COM 导出 PDF。

用法：
    python gen_srs.py            # 只生成 docx
    python gen_srs.py --pdf      # 生成 docx 后再导出 PDF
"""
import pathlib
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

WORK = pathlib.Path(__file__).resolve().parent
ROOT = WORK.parent
FIG = ROOT / "figures"
STEM = "智慧自习室预约与管理系统-需求规格说明书"
MD = ROOT / (STEM + ".md")
DOCX = ROOT / (STEM + ".docx")
PDF = ROOT / (STEM + ".pdf")

CN_BODY = "宋体"
CN_HEAD = "黑体"
CN_QUOTE = "楷体"
EN_BODY = "Times New Roman"
EN_CODE = "Consolas"

SZ_BODY = 10.5          # 五号
SZ_TABLE = 9.0
SZ_TABLE_WIDE = 8.0     # 列很多的表格
SZ_CODE = 9.0
SZ_QUOTE = 10.0
SZ_CAPTION = 9.0

PAGE_W = 21.0           # A4
PAGE_H = 29.7
MARGIN = 2.4
USABLE_W = PAGE_W - MARGIN * 2
MAX_FIG_H = PAGE_H - MARGIN * 2 - 1.6   # 给图题与页脚留出空间

INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


# ---------------------------------------------------------------- 基础样式工具

def style_run(run, cn=CN_BODY, en=EN_BODY, size=SZ_BODY, bold=False, italic=False,
              color=None):
    run.font.name = en
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), cn)
    rFonts.set(qn("w:ascii"), en)
    rFonts.set(qn("w:hAnsi"), en)


def add_runs(p, text, cn=CN_BODY, size=SZ_BODY, bold=False, color=None):
    """按行内标记（**粗体**、`代码`）写入多个 run。"""
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            style_run(p.add_run(part[2:-2]), cn=cn, size=size, bold=True, color=color)
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            style_run(p.add_run(part[1:-1]), cn=EN_CODE, en=EN_CODE,
                      size=size - 0.5, color=color)
        else:
            style_run(p.add_run(part), cn=cn, size=size, bold=bold, color=color)


def spacing(p, before=0, after=4, line=1.25):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    return p


def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexcolor)
    tcPr.append(shd)


def add_page_number(paragraph):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, end):
        run._r.append(el)
    style_run(run, size=9, cn=CN_BODY)


# ---------------------------------------------------------------- 文档初始化

def new_document():
    doc = Document()
    for section in doc.sections:
        section.page_width = Cm(PAGE_W)
        section.page_height = Cm(PAGE_H)
        section.left_margin = Cm(MARGIN)
        section.right_margin = Cm(MARGIN)
        section.top_margin = Cm(MARGIN)
        section.bottom_margin = Cm(MARGIN)

    normal = doc.styles["Normal"]
    normal.font.name = EN_BODY
    normal.font.size = Pt(SZ_BODY)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CN_BODY)

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_page_number(footer)
    return doc


# ---------------------------------------------------------------- 块级元素

def add_heading(doc, text, level):
    sizes = {1: 16, 2: 14, 3: 12, 4: 10.5, 5: 10.5, 6: 10.5}
    size = sizes.get(level, 10.5)
    p = doc.add_paragraph()
    p.style = doc.styles["Heading %d" % min(level, 4)]
    spacing(p, before=(14 if level <= 2 else 10), after=(8 if level <= 2 else 5))
    # 清掉样式自带的默认 run
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    add_runs(p, text, cn=CN_HEAD, size=size, bold=True)
    for r in p.runs:
        r.font.color.rgb = RGBColor(0x1F, 0x1F, 0x1F)
    return p


def add_para(doc, text, indent_cm=0.0, first_line=None):
    p = doc.add_paragraph()
    spacing(p)
    if indent_cm:
        p.paragraph_format.left_indent = Cm(indent_cm)
    if first_line is not None:
        p.paragraph_format.first_line_indent = Cm(first_line)
    add_runs(p, text)
    return p


def add_bullet(doc, text, ordered=False, num=""):
    p = doc.add_paragraph()
    spacing(p, after=2)
    p.paragraph_format.left_indent = Cm(0.75)
    p.paragraph_format.first_line_indent = Cm(-0.55)
    prefix = num + " " if ordered else "• "
    style_run(p.add_run(prefix), cn=CN_BODY, size=SZ_BODY)
    add_runs(p, text)
    return p


def add_quote(doc, text):
    p = doc.add_paragraph()
    spacing(p, before=2, after=4)
    p.paragraph_format.left_indent = Cm(0.6)
    add_runs(p, text, cn=CN_QUOTE, size=SZ_QUOTE)
    for r in p.runs:
        r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    return p


def add_code(doc, block_lines):
    p = doc.add_paragraph()
    spacing(p, before=2, after=4, line=1.0)
    p.paragraph_format.left_indent = Cm(0.6)
    style_run(p.add_run("\n".join(block_lines)), cn=EN_CODE, en=EN_CODE, size=SZ_CODE)
    return p


def add_hr(doc):
    p = doc.add_paragraph()
    spacing(p, before=2, after=2)
    pPr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "BFBFBF")
    borders.append(bottom)
    pPr.append(borders)
    return p


def add_figure(doc, name):
    png = FIG / (name + ".png")
    if not png.exists():
        add_para(doc, "［图形文件缺失：%s.png］" % name)
        return
    w_px, h_px = Image.open(png).size
    width_cm = USABLE_W
    if width_cm * h_px / w_px > MAX_FIG_H:
        width_cm = MAX_FIG_H * w_px / h_px
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    spacing(p, before=6, after=2, line=1.0)
    p.add_run().add_picture(str(png), width=Cm(width_cm))
    if width_cm < USABLE_W - 0.2 or h_px / w_px > 2.0:
        note = doc.add_paragraph()
        note.alignment = WD_ALIGN_PARAGRAPH.CENTER
        spacing(note, after=8)
        style_run(note.add_run(
            "（本图尺寸较大，清晰版本见 figures/%s.svg 与 figures/%s.png）" % (name, name)),
            cn=CN_QUOTE, size=8)


# ---------------------------------------------------------------- 表格

def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


SEP_RE = re.compile(r"^\|[\s:|-]+\|?$")


def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def cant_split(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))


def disp_len(s):
    """按显示宽度估算：中日韩全角字符算 2，其余算 1。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


MIN_COL_CM = 1.3

# 为 True 时，短标签列（如「修订人」）按内容取整到一行所需的宽度。
# 仅 SRS 生成时启用；gen_docx_any 保持 False，使其他文档版式不受影响。
FIT_SHORT_COLS = False
FIT_COL_HEADERS = {"修订人"}   # 只对指定列头的短标签列取整，避免影响其他表格版式
SHORT_COL_MAX_DISP = 16      # 最长单元格不超过 8 个汉字才取整
CM_PER_DISP = 0.185          # 半个汉字宽度（10.5pt 中文约 0.37cm）
CELL_PAD_CM = 0.55           # 单元格左右内边距 + 边框


def col_widths(header, body):
    """先给每列一个能容纳短内容的最小宽度，剩余宽度按各列平均内容量分配。

    单纯按比例分配会让 ST-01 这类编号列被压到一两个字宽而竖排。
    """
    ncols = len(header)
    min_w = min(MIN_COL_CM, USABLE_W / ncols)
    extra = max(USABLE_W - min_w * ncols, 0.0)
    weights = []
    for j in range(ncols):
        cells = [header[j]] + [r[j] if j < len(r) else "" for r in body]
        weights.append(max(sum(disp_len(c) for c in cells) / len(cells), 3.0))
    total = sum(weights)
    widths = [min_w + extra * w / total for w in weights]

    if FIT_SHORT_COLS:
        need = []
        for j in range(ncols):
            cells = [header[j]] + [r[j] if j < len(r) else "" for r in body]
            longest = max(disp_len(c) for c in cells) if cells else 0
            need.append(longest)
        fit = list(widths)
        for j in range(ncols):
            if header[j].strip() in FIT_COL_HEADERS and need[j] <= SHORT_COL_MAX_DISP:
                want = need[j] * CM_PER_DISP + CELL_PAD_CM
                if want > fit[j]:
                    fit[j] = want
        overflow = sum(fit) - USABLE_W
        if overflow > 0.05:
            # 从最长的列扣回，避免总宽超出页面
            order = sorted(range(ncols), key=lambda k: fit[k], reverse=True)
            for j in order:
                if overflow <= 0.05:
                    break
                spare = max(fit[j] - min_w, 0.0)
                take = min(spare, overflow)
                fit[j] -= take
                overflow -= take
        widths = fit
    return widths


def add_table(doc, rows):
    header = split_row(rows[0])
    body = [split_row(r) for r in rows[2:]]
    ncols = len(header)
    size = SZ_TABLE if ncols <= 6 else SZ_TABLE_WIDE

    t = doc.add_table(rows=1 + len(body), cols=ncols)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False

    def fill(cell, text, bold=False, fill_color=None, align_center=False):
        cell.text = ""
        p = cell.paragraphs[0]
        spacing(p, before=1, after=1, line=1.05)
        if align_center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_runs(p, text, cn=CN_BODY, size=size, bold=bold)
        if fill_color:
            shade(cell, fill_color)

    for j, h in enumerate(header):
        fill(t.cell(0, j), h, bold=True, fill_color="EDEDF7", align_center=True)
    for i, row in enumerate(body, start=1):
        for j in range(ncols):
            fill(t.cell(i, j), row[j] if j < len(row) else "")

    for j, w in enumerate(col_widths(header, body)):
        for row in t.rows:
            row.cells[j].width = Cm(w)

    repeat_header(t.rows[0])
    for row in t.rows:
        cant_split(row)

    doc.add_paragraph()
    return t


# ---------------------------------------------------------------- Markdown 解析

FIG_RE = re.compile(r"^<!--\s*FIG:([^\s>]+?)\s*-->$")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
UL_RE = re.compile(r"^[-*+]\s+(.*)$")
OL_RE = re.compile(r"^(\d+)\.\s+(.*)$")


def convert(md_text, doc, stats):
    lines = md_text.split("\n")
    i, pending_fig = 0, None
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()

        m = FIG_RE.match(s)
        if m:
            pending_fig = m.group(1)
            i += 1
            continue

        if s.startswith("```"):
            lang = s[3:].strip().lower()
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            if lang == "mermaid" and pending_fig:
                add_figure(doc, pending_fig)
                stats["figures"].append(pending_fig)
            elif pending_fig and lang == "mermaid":
                add_para(doc, "［缺少 FIG 标记，无法插入图形］")
            else:
                add_code(doc, block)
            pending_fig = None
            continue

        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            if len(rows) >= 2 and SEP_RE.match(rows[1]):
                add_table(doc, rows)
                stats["tables"] += 1
            else:
                add_para(doc, " ".join(rows))
            continue

        m = HEAD_RE.match(s)
        if m:
            add_heading(doc, m.group(2).strip(), len(m.group(1)))
            i += 1
            continue

        if s in ("---", "***", "___"):
            add_hr(doc)
            i += 1
            continue

        if s.startswith(">"):
            add_quote(doc, s.lstrip(">").strip())
            i += 1
            continue

        m = UL_RE.match(s)
        if m:
            add_bullet(doc, m.group(1))
            i += 1
            continue

        m = OL_RE.match(s)
        if m:
            add_bullet(doc, m.group(2), ordered=True, num=m.group(1) + ".")
            i += 1
            continue

        if not s:
            i += 1
            continue

        add_para(doc, s)
        i += 1


def to_pdf():
    import win32com.client
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(DOCX.resolve()), ReadOnly=False)
        d.SaveAs(str(PDF.resolve()), FileFormat=17)   # wdFormatPDF
        d.Close(False)
    finally:
        word.Quit()
    print("[PDF] %s  (%.1f KB)" % (PDF.name, PDF.stat().st_size / 1024))


def main():
    global FIT_SHORT_COLS
    FIT_SHORT_COLS = True
    if not MD.exists():
        raise SystemExit("找不到 %s" % MD)
    doc = new_document()
    stats = {"tables": 0, "figures": []}
    convert(MD.read_text(encoding="utf-8"), doc, stats)
    doc.save(str(DOCX))
    print("[DOCX] %s  (%.1f KB)" % (DOCX.name, DOCX.stat().st_size / 1024))
    print("       表格 %d 个；插图 %d 张：%s"
          % (stats["tables"], len(stats["figures"]), "、".join(stats["figures"])))
    if "--pdf" in sys.argv:
        to_pdf()


if __name__ == "__main__":
    main()
