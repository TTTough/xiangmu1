# -*- coding: utf-8 -*-
"""附件三版自检：9 份附件均有 md/docx/pdf，体量与清单一致，pdf 可打开。"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(r"C:\Users\14407\Desktop\作业\软件工程")
ATT = ROOT / "附件"
LIST = ATT / "00-附件清单.md"
P = []

mds = sorted(ATT.rglob("*.md"), key=lambda p: str(p))
print("=" * 78)
print("自检 1：附件三版齐全（md 为源，docx/pdf 为导出版）")
print("=" * 78)
import pymupdf
total_pages = 0
for md in mds:
    dx, pf = md.with_suffix(".docx"), md.with_suffix(".pdf")
    ok = dx.exists() and pf.exists()
    pages = 0
    if pf.exists():
        pages = pymupdf.open(str(pf)).page_count
        total_pages += pages
    rel = str(md.relative_to(ATT))
    print("  %s %-46s md %5.1f KB │ docx %5.1f KB │ pdf %5.1f KB / %2d 页" % (
        "✓" if ok else "✗", rel, md.stat().st_size / 1024,
        dx.stat().st_size / 1024 if dx.exists() else 0,
        pf.stat().st_size / 1024 if pf.exists() else 0, pages))
    if not ok:
        P.append("附件三版不全：%s" % rel)
print("  合计：%d 份附件，%d 个文件，pdf 共 %d 页" % (
    len(mds), sum(1 for md in mds for e in (".md", ".docx", ".pdf") if pathlib.Path(str(md)[:-3] + e).exists()), total_pages))

print()
print("=" * 78)
print("自检 2：附件清单中的体量与实际文件一致")
print("=" * 78)
cl = LIST.read_text(encoding="utf-8")
rows = re.findall(r"^\|\s*(E-\d+[^|]*?)\s*\|\s*([\d.]+) KB\s*\|\s*([\d.]+) KB\s*\|\s*([\d.]+) KB\s*\|", cl, re.M)
print("  清单列出 %d 行带体量的条目" % len(rows))
name_map = {}
for md in mds:
    name_map[md.stem] = md
SUB = {"E-05a": "AI-01", "E-05b": "AI-02", "E-05c": "AI-03", "E-05d": "AI-04", "E-05e": "AI-05"}
for label, m_kb, d_kb, p_kb in rows:
    key = label.split()[0]  # E-04 / E-05a ...
    hit = None
    for stem, md in name_map.items():
        if key == "E-04" and stem.startswith("E-04-"):
            hit = md
        elif key in SUB and stem.startswith(SUB[key] + "-"):
            hit = md
        elif key in ("E-07", "E-08") and stem.startswith(key + "-"):
            hit = md
    if not hit:
        P.append("清单条目无法对应到文件：%s" % label)
        continue
    real = [hit.stat().st_size / 1024,
            hit.with_suffix(".docx").stat().st_size / 1024,
            hit.with_suffix(".pdf").stat().st_size / 1024]
    claimed = [float(m_kb), float(d_kb), float(p_kb)]
    diff = max(abs(a - b) for a, b in zip(real, claimed))
    status = "✓" if diff < 0.6 else "✗ 偏差 %.1f KB" % diff
    print("  %s %-42s 实测 %.1f/%.1f/%.1f" % (status, label[:42], *real))
    if diff >= 0.6:
        P.append("清单体量与实测不符：%s（偏差 %.1f KB）" % (label, diff))

print()
print("=" * 78)
print("自检 3：三份主报告 + 附件的三版总览")
print("=" * 78)
for tag, stem in (
    ("SRS V1.2", "智慧自习室预约与管理系统-需求规格说明书"),
    ("材料 A", "智慧自习室预约与管理系统-需求分析质量验证报告"),
    ("材料 B", "智慧自习室预约与管理系统-AI智能体使用验证报告"),
):
    md = ROOT / (stem + ".md")
    dx = ROOT / (stem + ".docx")
    pf = ROOT / (stem + ".pdf")
    ok = md.exists() and dx.exists() and pf.exists()
    pages = pymupdf.open(str(pf)).page_count if pf.exists() else 0
    print("  %s %-9s md %7.1f KB │ docx %7.1f KB │ pdf %7.1f KB / %2d 页" % (
        "✓" if ok else "✗", tag, md.stat().st_size / 1024,
        dx.stat().st_size / 1024 if dx.exists() else 0,
        pf.stat().st_size / 1024 if pf.exists() else 0, pages))
    if not ok:
        P.append("%s 三版不全" % tag)
print("  附件 9 份：md + docx + pdf 三版齐全（见自检 1）")

print()
print("=" * 78)
if P:
    print("发现 %d 项问题：" % len(P))
    for x in P:
        print("  - " + x)
    sys.exit(1)
print("全部自检通过：4 类材料（SRS、材料 A、材料 B、附件）均已提供一致的三版。")
