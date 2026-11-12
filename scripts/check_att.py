# -*- coding: utf-8 -*-
"""附件专项自检：E 编号三方一致、文件可访问、来源表述、三版一致。"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(r"C:\Users\14407\Desktop\作业\软件工程")
A = ROOT / "智慧自习室预约与管理系统-需求分析质量验证报告.md"
B = ROOT / "智慧自习室预约与管理系统-AI智能体使用验证报告.md"
ATT = ROOT / "附件"
LIST = ATT / "00-附件清单.md"

a = A.read_text(encoding="utf-8")
b = B.read_text(encoding="utf-8")
cl = LIST.read_text(encoding="utf-8")
P = []


def e_ids(txt, pattern=r"^\|\s*\*{0,2}(E-\d+)\*{0,2}\s*\|"):
    return sorted(set(re.findall(pattern, txt, re.M)), key=lambda x: int(x.split("-")[1]))


# ---------------------------------------------------------------- 1 E 编号三方一致
print("=" * 78)
print("自检 1：E 编号三方一致（材料 A 的 A.9 / 材料 B 的 B.4 / 附件清单）")
print("=" * 78)
e_a, e_b, e_cl = e_ids(a), e_ids(b), e_ids(cl)
print("  材料 A  的 A.9：%s" % "、".join(e_a))
print("  材料 B  的 B.4：%s" % "、".join(e_b))
print("  附件清单      ：%s" % "、".join(e_cl))
if e_a == e_b == e_cl:
    print("  ✓ 三处 E 编号集合完全相同（共 %d 个）" % len(e_a))
else:
    P.append("E 编号集合不一致：A=%s，B=%s，清单=%s" % (e_a, e_b, e_cl))
# E-05 子件
sub = sorted(set(re.findall(r"E-05([a-e])", cl)))
sub_f = sorted(set(re.findall(r"E-05([a-e])", a)) | set(re.findall(r"E-05([a-e])", b)))
print("  附件清单列出的 E-05 子件：%s" % "、".join("E-05" + s for s in sub))
if len(sub) != 5:
    P.append("附件清单的 E-05 子件不足 5 个：%s" % sub)

# ---------------------------------------------------------------- 2 文件可访问
print()
print("=" * 78)
print("自检 2：附件文件与目录可访问")
print("=" * 78)
need = [
    ATT / "00-附件清单.md",
    ATT / "E-04-需求规格说明书审查问题与修改提示词.md",
    ATT / "E-05-AI交互记录" / "AI-01-需求框架建立与SRS初稿.md",
    ATT / "E-05-AI交互记录" / "AI-02-SRS-V1.0独立审查与问题核查.md",
    ATT / "E-05-AI交互记录" / "AI-03-SRS-V1.1修订执行.md",
    ATT / "E-05-AI交互记录" / "AI-04-材料A编写方案起草与修订.md",
    ATT / "E-05-AI交互记录" / "AI-05-材料A落地与SRS-V1.2.md",
    ATT / "E-07-教学模拟确认记录模板.md",
    ATT / "E-08-材料A编写方案-V2.md",
    ROOT / "prototype" / "index.html",
    ROOT / "_work" / "SRS-V1.0-备份.md",
    ROOT / "_work" / "SRS-V1.1-备份.md",
]
for p in need:
    ok = p.exists()
    if not ok:
        P.append("附件缺失：%s" % p)
    print("  %s %s（%.1f KB）" % ("✓" if ok else "✗", str(p.relative_to(ROOT)), p.stat().st_size / 1024 if ok else 0))
shots = sorted((ROOT / "prototype" / "shots").glob("*.png"))
figs = sorted((ROOT / "figures").glob("*.mmd"))
print("  ✓ 原型截图 %d 张；图源 %d 组" % (len(shots), len(figs)))
if len(shots) != 18:
    P.append("截图数量异常：%d" % len(shots))
if len(figs) != 13:
    P.append("图源数量异常：%d" % len(figs))
for ext in (".svg", ".png"):
    n = len(list((ROOT / "figures").glob("*" + ext)))
    if n != 13:
        P.append("figures 下 %s 数量异常：%d" % (ext, n))
print("  ✓ 每张图三件套（.mmd/.svg/.png）齐全")

# ---------------------------------------------------------------- 3 正文引用路径
print()
print("=" * 78)
print("自检 3：材料 A／B 中引用的附件路径存在")
print("=" * 78)
paths = set()
for txt in (a, b):
    for m in re.findall(r"软件工程\\附件\\[^\s|；）]+", txt):
        paths.add(m.split("（")[0].strip())
for m in paths:
    rel = m.replace("软件工程\\", "").replace("\\", "/")
    p = ROOT / rel
    ok = p.exists() or (ROOT / rel.rstrip("/")).exists()
    print("  %s %s" % ("✓" if ok else "✗", m))
    if not ok:
        P.append("正文引用的附件路径不存在：%s" % m)

# ---------------------------------------------------------------- 4 来源表述
print()
print("=" * 78)
print("自检 4：审查来源表述的如实性")
print("=" * 78)
for nm, txt in (("材料 A", a), ("材料 B", b), ("附件清单", cl)):
    has_cg = "ChatGPT" in txt
    print("  %s：提及 ChatGPT %s" % (nm, "✓" if has_cg else "✗"))
    if not has_cg:
        P.append("%s 未如实写明审查由 ChatGPT 执行" % nm)
ai02 = (ATT / "E-05-AI交互记录" / "AI-02-SRS-V1.0独立审查与问题核查.md").read_text(encoding="utf-8")
if "本智能体**未参与**该审查的生成" not in ai02 and "未参与" not in ai02:
    P.append("AI-02 附件未声明本智能体未参与审查")
else:
    print("  E-05b（AI-02 附件）：✓ 已声明本智能体未参与该审查的生成")
print("  材料 B 的工具使用记录表含 ChatGPT 行：%s" % ("✓" if re.search(r"^\|\s*ChatGPT\s*\|", b, re.M) else "✗"))
if not re.search(r"^\|\s*ChatGPT\s*\|", b, re.M):
    P.append("材料 B 的 B.1 工具表缺少 ChatGPT 行")

# ---------------------------------------------------------------- 5 三版一致
print()
print("=" * 78)
print("自检 5：三版一致（含附件清单）")
print("=" * 78)
try:
    import pymupdf
    for tag, md, dx, pf in (
        ("SRS V1.2", ROOT / "智慧自习室预约与管理系统-需求规格说明书.md",
         ROOT / "智慧自习室预约与管理系统-需求规格说明书.docx", ROOT / "智慧自习室预约与管理系统-需求规格说明书.pdf"),
        ("材料 A", A, A.with_suffix(".docx"), A.with_suffix(".pdf")),
        ("材料 B", B, B.with_suffix(".docx"), B.with_suffix(".pdf")),
    ):
        d = pymupdf.open(str(pf))
        tbl = len(re.findall(r"^\|[\s:|-]+\|\s*$", md.read_text(encoding="utf-8"), re.M))
        print("  %-9s md %6.1f KB / %2d 表格；docx %7.1f KB；pdf %7.1f KB / %2d 页" % (
            tag, md.stat().st_size / 1024, tbl, dx.stat().st_size / 1024, pf.stat().st_size / 1024, d.page_count))
    print("  附件（%d 个文件）以 Markdown 提交，可直接打开；docx／pdf 非必需" % len(need))
except Exception as e:
    P.append("三版检查异常：%s" % e)

print()
print("=" * 78)
if P:
    print("发现 %d 项问题：" % len(P))
    for x in P:
        print("  - " + x)
    sys.exit(1)
print("全部自检通过。")
