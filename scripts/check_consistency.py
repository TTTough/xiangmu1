# -*- coding: utf-8 -*-
"""提交前一致性修订自检（8 项）。"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = pathlib.Path(r"C:\Users\14407\Desktop\作业\软件工程")
A = R / "智慧自习室预约与管理系统-需求分析质量验证报告.md"
C = R / "附件" / "00-附件清单.md"
PNG = "2584c7110a1ba40974fec84d0503a7e3.png"
a = A.read_text(encoding="utf-8")
c = C.read_text(encoding="utf-8")
P = []

# ---------------------------------------------------------------- 1
print("=" * 76)
print("自检 1：材料 A 封面")
print("=" * 76)
d = [ln for ln in a.split("\n") if ln.startswith("| 报告日期 |")]
v = [ln for ln in a.split("\n") if ln.startswith("| 依据文档 |")]
print("  %s" % (d[0] if d else "未找到"))
print("  %s" % (v[0] if v else "未找到"))
if not (d and "2026-10-29" in d[0]):
    P.append("封面报告日期不是 2026-10-29")
if not (v and "V1.3" in v[0]):
    P.append("封面依据文档不是 V1.3")
a1 = a[a.find("## A.1"):a.find("## A.2")]
print("  与 A.1 一致：A.1 提交日期 %s，SRS 版本 %s" % (
    "✓ 2026-10-29" if "2026-10-29" in a1 else "✗",
    "✓ V1.3" if "SRS-ZXSS-V1.3" in a1 else "✗"))

# ---------------------------------------------------------------- 2
print()
print("=" * 76)
print("自检 2：7 处「当前依据版本」均为 V1.3")
print("=" * 76)
SPOTS = [
    ("A.2 开头", "逐条沿用需求规格说明书 V1.3 第 6 章与附录 A"),
    ("A.2 统计口径", "需求规格说明书 V1.3 共 25 条业务规则"),
    ("A.3 开头", "需求规格说明书 V1.3 共提交 **13 张图模型**"),
    ("A.4.1", "需求规格说明书 V1.3 第 7 章已提供完整的状态转换说明表"),
    ("A.4.3", "需求规格说明书 V1.3 中以「目标状态及业务结果」列为「—」标记"),
    ("A.5.0", "走查依据统一为**需求规格说明书 V1.3**"),
    ("A.7 检查范围", "需求规格说明书 V1.0 → V1.1 → V1.2 → V1.3 的修订过程"),
]
for nm, s in SPOTS:
    ok = s in a
    print("  %-14s %s" % (nm, "✓" if ok else "✗"))
    if not ok:
        P.append("%s 未改为 V1.3" % nm)

# ---------------------------------------------------------------- 3
print()
print("=" * 76)
print("自检 3：材料 A 中剩余「V1.2」逐条列出并确认属历史表述")
print("=" * 76)
HIST_HINT = ["定稿", "补齐", "V1.2 三版同步保留", "V1.2 重排后", "V1.2 第 28 行", "→ V1.3 的修订过程",
             "V1.2 第 29、30 行", "V1.2 交付验收", "已新增（V1.2"]
left = []
for i, ln in enumerate(a.split("\n"), 1):
    if "V1.2" in ln:
        left.append((i, ln.strip()))
print("  剩余 %d 处：" % len(left))
for i, ln in left:
    is_hist = any(h in ln for h in HIST_HINT)
    print("    第 %-4d 行 %s" % (i, ("[历史] " if is_hist else "[需核查] ") + ln[:96]))
    if not is_hist:
        P.append("第 %d 行的 V1.2 可能仍属当前依据：%s" % (i, ln[:80]))
# A.7 检查范围那行现在应含 V1.3 且仍含 V1.2（历史链），需单独确认
a7line = [ln for ln in a.split("\n") if ln.startswith("- 检查范围及依据版本：")]
print("  A.7 检查范围行：%s" % ("✓ 含 → V1.3" if a7line and "→ V1.3" in a7line[0] else "✗"))

# ---------------------------------------------------------------- 4
print()
print("=" * 76)
print("自检 4：浏览器版本")
print("=" * 76)
br = [ln for ln in a.split("\n") if ln.startswith("| 浏览器 |")]
print("  %s" % (br[0] if br else "未找到"))
if not (br and "155.0.4283.45（正式版本）（64 位）" in br[0]):
    P.append("浏览器版本未按预期填写")
n_placeholder = a.count("版本号（待填）")
print("  全文「版本号（待填）」：%d 处" % n_placeholder)
if n_placeholder:
    P.append("仍存在「版本号（待填）」%d 处" % n_placeholder)

# ---------------------------------------------------------------- 5
print()
print("=" * 76)
print("自检 5：A.6.5 统计与 AC-02-04 口径")
print("=" * 76)
a65 = a[a.find("### A.6.5"):a.find("## A.7")]
nums = re.search(r"\| 完整覆盖 \| (\d+) \|", a65)
part = re.search(r"\| 部分覆盖 \| (\d+) \|", a65)
none_ = re.search(r"\| 无系统截图证据 \| (\d+) \|", a65)
tot = re.search(r"\| SRS 验收标准总数 \| (\d+) \|", a65)
print("  统计：%s = %s + %s + %s" % (tot.group(1), nums.group(1), part.group(1), none_.group(1)))
if int(nums.group(1)) + int(part.group(1)) + int(none_.group(1)) != int(tot.group(1)) or int(tot.group(1)) != 68:
    P.append("A.6.5 统计不是 68 = 26 + 2 + 40")
note = "注：AC-02-04 由 PV-27 演示了「停用座位不可预约」，但「停用后自动取消未来预约并通知」未实现，故不单独计入部分覆盖，仍归入未覆盖清单。"
print("  AC-02-04 口径说明：%s" % ("✓ 已补" if note in a65 else "✗"))
if note not in a65:
    P.append("A.6.5 缺少 AC-02-04 口径说明")
# 部分覆盖仍只有 2 条
print("  部分覆盖仍为 %s 条：%s" % (part.group(1), "✓" if part.group(1) == "2" else "✗"))

# ---------------------------------------------------------------- 6
print()
print("=" * 76)
print("自检 6：00-清单的数量表述")
print("=" * 76)
n9 = c.count("9 份")
n10 = c.count("10 项材料")
print("  「9 份」：%d 处（期望 0）" % n9)
print("  「10 项材料」：%d 处（期望 2）" % n10)
if n9:
    P.append("00-清单仍有「9 份」%d 处" % n9)
if n10 != 2:
    P.append("00-清单「10 项材料」为 %d 处，期望 2" % n10)
if "除 E-07b 签名页仅提供 PDF 外" not in c or "除 E-07b 仅 PDF 外" not in c:
    P.append("00-清单缺少 E-07b 仅 PDF 的说明")
else:
    print("  E-07b 仅 PDF 的说明（开头段＋目录树注释）：✓ 两处均在")
arch_row = [ln for ln in c.split("\n") if ln.startswith("| `_work\\archive\\` 中的旧模板三版")]
print("  archive 行补注：%s" % ("✓" if arch_row and PNG in arch_row[0] else "✗"))
if not (arch_row and PNG in arch_row[0]):
    P.append("archive 行未补注 PNG 文件名")

# ---------------------------------------------------------------- 7
print()
print("=" * 76)
print("自检 7：根目录 PNG 已移入 _work\\archive\\")
print("=" * 76)
root_png, arch_png = R / PNG, R / "_work" / "archive" / PNG
print("  根目录存在：%s（应为否）" % ("是" if root_png.exists() else "否"))
print("  archive 存在：%s（应为是）" % ("是" if arch_png.exists() else "否"))
if root_png.exists():
    P.append("根目录仍存在该 PNG")
if not arch_png.exists():
    P.append("archive 下缺少该 PNG")
print("  archive 现有文件 %d 个" % len(list((R / '_work' / 'archive').iterdir())))

# ---------------------------------------------------------------- 8
print()
print("=" * 76)
print("自检 8：docx／pdf 中可检索到 A.6.5、V1.3、浏览器版本号")
print("=" * 76)
import docx
import pymupdf
for tag, md in (("材料 A", A), ("00-清单", C)):
    dx, pf = md.with_suffix(".docx"), md.with_suffix(".pdf")
    dtxt = "\n".join(p.text for p in docx.Document(str(dx)).paragraphs)
    for tb in docx.Document(str(dx)).tables:
        for row in tb.rows:
            for cell in row.cells:
                dtxt += "\n" + cell.text
    ptxt = "".join(pymupdf.open(str(pf))[i].get_text() for i in range(pymupdf.open(str(pf)).page_count))
    checks = ["A.6.5", "V1.3"] + (["155.0.4283.45"] if tag == "材料 A" else [])
    for k in checks:
        okd, okp = k in dtxt, k in ptxt
        print("  %-7s %-14s docx %s ｜ pdf %s" % (tag, k, "✓" if okd else "✗", "✓" if okp else "✗"))
        if not (okd and okp):
            P.append("%s 的 docx/pdf 缺「%s」" % (tag, k))
    # 时间戳
    mt = md.stat().st_mtime
    print("  %-7s 时间戳：md %s ｜ docx %s ｜ pdf %s" % (
        tag,
        "✓ 最早" if mt <= dx.stat().st_mtime and mt <= pf.stat().st_mtime else "✗",
        "✓" if dx.stat().st_mtime >= mt else "✗",
        "✓ 最新" if pf.stat().st_mtime >= dx.stat().st_mtime else "✗"))
    if not (mt <= dx.stat().st_mtime <= pf.stat().st_mtime):
        P.append("%s 的导出时间顺序异常" % tag)

print()
print("=" * 76)
if P:
    print("发现 %d 项问题：" % len(P))
    for x in P:
        print("  - " + x)
    sys.exit(1)
print("全部 8 项自检通过。")
