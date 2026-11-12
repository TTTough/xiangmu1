# -*- coding: utf-8 -*-
"""收尾修订自检（7 项）。"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = pathlib.Path(r"C:\Users\14407\Desktop\作业\软件工程")
S = R / "智慧自习室预约与管理系统-需求规格说明书.md"
A = R / "智慧自习室预约与管理系统-需求分析质量验证报告.md"
B = R / "智慧自习室预约与管理系统-AI智能体使用验证报告.md"
C = R / "附件" / "00-附件清单.md"
E7 = R / "附件" / "E-07-教学模拟确认记录.md"
E7B = R / "附件" / "E-07b-签名页.pdf"
s, a, b, c, e = (p.read_text(encoding="utf-8") for p in (S, A, B, C, E7))
P = []

# ---------------------------------------------------------------- 1
print("=" * 76)
print("自检 1：Q-01／Q-09 四处表述一致且仍为「待确认」")
print("=" * 76)
NEED = {
    "上限 1 个": ["暂按同时有效预约上限 1 个执行", "确认前按上限 1 个执行", "按同时有效预约上限 1 个执行", "确认前分别按上限 1 个"],
    "永久累计": ["暂按永久累计执行（不清零、不滚动）", "确认前按永久累计执行", "按永久累计执行（不清零、不滚动）", "永久累计执行"],
}
# SRS 附录 B
for qid, key, kw in (("Q-01", "上限 1 个", "暂按同时有效预约上限 1 个执行"),
                     ("Q-09", "永久累计", "暂按永久累计执行（不清零、不滚动）；统计周期仍待确认")):
    row = [ln for ln in s.split("\n") if ln.startswith("| %s " % qid)]
    ok = bool(row) and kw in row[0]
    pend = "待确认" in (row[0] if row else "")
    print("  SRS 附录 B %s：口径 %s ｜ 仍标待确认 %s" % (qid, "✓" if ok else "✗", "✓" if pend else "✗"))
    if not ok:
        P.append("SRS %s 缺少执行口径「%s」" % (qid, kw))
    if not pend:
        P.append("SRS %s 未标注待确认" % qid)
# A.2.3
a23 = a[a.find("### A.2.3"):a.find("### A.3")]
print("  A.2.3 遗留事项三条：Q-01 %s ｜ Q-09 %s ｜ Q-16／Q-17 %s" % (
    "✓" if "确认前按上限 1 个执行" in a23 else "✗",
    "✓" if "确认前按永久累计执行" in a23 else "✗",
    "✓" if "寒暑假起止以校历为准" in a23 else "✗"))
for kw, tag in (("确认前按上限 1 个执行", "A.2.3 Q-01"), ("确认前按永久累计执行", "A.2.3 Q-09")):
    if kw not in a23:
        P.append("%s 缺少「%s」" % (tag, kw))
# A.2 表
for bid, kw in (("BR-04", "考试周是否放宽待 Q-01，确认前按 1 个执行"),
                ("BR-12", "统计周期待 Q-09，确认前按永久累计执行"),
                ("BR-16", "寒暑假起止以校历为准，实施阶段确定"),
                ("BR-17", "寒暑假起止以校历为准，实施阶段确定")):
    row = [ln for ln in a.split("\n") if ln.startswith("| %s " % bid)]
    ok = bool(row) and kw in row[0]
    print("  A.2 表 %s：%s「%s」" % (bid, "✓" if ok else "✗", kw[:16]))
    if not ok:
        P.append("A.2 的 %s 缺少「%s」" % (bid, kw))
# E-07
print("  E-07 §3：Q-01 %s ｜ Q-09 %s ｜ 待确认标注 %s" % (
    "✓" if "按同时有效预约上限 1 个执行" in e else "✗",
    "✓" if "按永久累计执行（不清零、不滚动）" in e else "✗",
    "✓" if e.count("**待确认**") >= 2 else "✗"))
if "按同时有效预约上限 1 个执行" not in e or "按永久累计执行（不清零、不滚动）" not in e:
    P.append("E-07 第 4 节遗留事项口径缺失")

# ---------------------------------------------------------------- 2
print()
print("=" * 76)
print("自检 2：Q-16／Q-17 的「可选上传」「寒暑假以校历为准」四处一致")
print("=" * 76)
places = {
    "SRS 附录 B Q-16": [ln for ln in s.split("\n") if ln.startswith("| Q-16 ")],
    "SRS 附录 B Q-17": [ln for ln in s.split("\n") if ln.startswith("| Q-17 ")],
    "SRS B.1 表": [s[s.find("### B.1 教学模拟确认结论"):s.find("## 附录 C")]],
    "SRS 术语表工作日": [ln for ln in s.split("\n") if ln.startswith("| 工作日 ")],
    "A.2.3": [a23],
    "E-07 §3": [e[e.find("## 3 遗留事项"):e.find("## 4 结论的适用范围")]],
}
for nm, blocks in places.items():
    txt = " ".join(blocks)
    has_opt = "可选上传" in txt
    has_cal = "以校历为准" in txt
    print("  %-18s 可选上传 %s ｜ 以校历为准 %s" % (nm, "✓" if has_opt else "—", "✓" if has_cal else "—"))
for nm in ("SRS 附录 B Q-16", "SRS B.1 表", "A.2.3", "E-07 §3"):
    txt = " ".join(places[nm])
    if "可选上传" not in txt:
        P.append("%s 缺少「可选上传」" % nm)
for nm in ("SRS 附录 B Q-17", "SRS B.1 表", "SRS 术语表工作日", "A.2.3", "E-07 §3"):
    txt = " ".join(places[nm])
    if "以校历为准" not in txt:
        P.append("%s 缺少「以校历为准」" % nm)

# ---------------------------------------------------------------- 3
print()
print("=" * 76)
print("自检 3：SRS 版本仍为 V1.3，修订记录含「同日补遗」，三版一致")
print("=" * 76)
v = re.search(r"\| 文档版本 \| (V[\d.]+) \|", s)
code = re.search(r"\| 文档编号 \| (SRS-ZXSS-V[\d.]+) \|", s)
print("  封面：%s ｜ %s" % (code.group(1), v.group(1)))
if v.group(1) != "V1.3" or code.group(1) != "SRS-ZXSS-V1.3":
    P.append("SRS 版本不是 V1.3")
rec = [ln for ln in s.split("\n") if ln.startswith("| V1.3 ")]
print("  修订记录 V1.3 含「同日补遗」：%s" % ("✓" if rec and "同日补遗" in rec[0] else "✗"))
if not (rec and "同日补遗" in rec[0]):
    P.append("修订记录缺「同日补遗」")
print("  未新增版本行（V1.4 不存在）：%s" % ("✓" if "| V1.4 " not in s else "✗"))
if "| V1.4 " in s:
    P.append("出现了 V1.4 版本行")

# ---------------------------------------------------------------- 4
print()
print("=" * 76)
print("自检 4：E-07b 在 A.9 / B.4 / 00 清单三处登记，PDF 可打开")
print("=" * 76)
for nm, txt in (("材料 A 的 A.9", a), ("材料 B 的 B.4", b), ("00-清单表格", c)):
    ok = "E-07b" in txt
    print("  %-14s 含 E-07b：%s" % (nm, "✓" if ok else "✗"))
    if not ok:
        P.append("%s 未登记 E-07b" % nm)
print("  00-清单目录树含 E-07b-签名页.pdf：%s" % ("✓" if "E-07b-签名页.pdf" in c else "✗"))
print("  00-清单体量表含 E-07b 行：%s" % ("✓" if "| E-07b 签名页 |" in c else "✗"))
if "| E-07b 签名页 |" not in c:
    P.append("体量表缺 E-07b 行")
if E7B.exists():
    import pymupdf
    d = pymupdf.open(str(E7B))
    pg = d.load_page(0)
    txt = pg.get_text()
    print("  E-07b PDF：%.1f KB / %d 页；含量表头 %s；含四人姓名 %s" % (
        E7B.stat().st_size / 1024, d.page_count,
        "✓" if "签名（本人手签）" in txt else "✗",
        "✓" if all(n in txt for n in ("应雨挺", "方与皓", "周俊楠", "杨子涵")) else "✗"))
    if d.page_count != 1:
        P.append("E-07b 不是单页")
    if "签名（本人手签）" not in txt:
        P.append("E-07b 表头不符")
else:
    P.append("E-07b PDF 不存在")

# ---------------------------------------------------------------- 5
print()
print("=" * 76)
print("自检 5：材料 B 的 AI-05 原文未改，仅末尾新增「后续衔接」")
print("=" * 76)
i0 = b.find("### AI-05")
i1 = b.find("### 人工决定与确认责任", i0)
blk = b[i0:i1]
old = (R / "_work" / "archive" / "B-补遗前.md").read_text(encoding="utf-8")
j0, j1 = old.find("### AI-05"), old.find("### 人工决定与确认责任", old.find("### AI-05"))
blk_old = old[j0:j1]
added = [ln for ln in blk.split("\n") if ln not in blk_old.split("\n")]
print("  AI-05 段新增行数：%d" % len(added))
for ln in added:
    print("    %s" % ln[:110])
add_row = [ln for ln in added if "后续衔接" in ln]
mod_row = [ln for ln in added if "尚未解决的问题" in ln]
print("  判定：新增行 %d（应为 1：后续衔接）；被补注行 %d（应为 1：尚未解决的问题，属第四节第 2 项要求）" % (len(add_row), len(mod_row)))
if len(add_row) != 1 or len(mod_row) != 1 or len(added) != 2:
    P.append("AI-05 段的改动超出「1 新增 + 1 补注」（新增 %d 行）" % len(added))
if not any("后续衔接" in ln and "本任务的产物为 SRS V1.2" in ln for ln in added):
    P.append("「后续衔接」内容不符")
print("  未新增 AI-06：%s" % ("✓" if "AI-06" not in b else "✗"))
if "AI-06" in b:
    P.append("出现了 AI-06")

# ---------------------------------------------------------------- 6
print()
print("=" * 76)
print("自检 6：无「待组员确认」残留；「教师确认」仍为未发生")
print("=" * 76)
for nm, txt in (("SRS", s), ("材料 A", a), ("材料 B", b), ("00-清单", c), ("E-07", e)):
    n = txt.count("待组员确认")
    print("  %-8s 待组员确认 %d 处" % (nm, n))
    if n:
        P.append("%s 残留待组员确认 %d 处" % (nm, n))
print("  材料 B 教师确认：%s" % ("**未发生** ✓" if "教师确认 | **未发生**" in b else "✗"))
if "教师确认 | **未发生**" not in b:
    P.append("材料 B 的教师确认不再是未发生")

# ---------------------------------------------------------------- 7
print()
print("=" * 76)
print("自检 7：编号未变")
print("=" * 76)
for pre, lo, hi in (("T", 1, 8), ("SC", 1, 9), ("PV", 1, 20), ("V", 1, 26)):
    ids = set(x.group(1) for x in re.finditer(pre + r"-(\d{2})", a + b + e + s))
    want = {"%02d" % i for i in range(lo, hi + 1)}
    miss = sorted(want - ids)
    print("  %-3s %s-%02d—%s-%02d 缺失 %s" % (pre, pre, lo, pre, hi, miss or "无"))
    if miss:
        P.append("%s 编号缺失 %s" % (pre, miss))
e_ids = sorted(set(re.findall(r"\bE-\d+b?\b", a + b + c)))
print("  E 编号：%s" % "、".join(e_ids))
if "E-07b" not in e_ids:
    P.append("E-07b 未出现在编号集合中")
ALLOW = set("E-%02d" % i for i in range(1, 11)) | {"E-05a", "E-05b", "E-05c", "E-05d", "E-05e", "E-07b"}
if any(x not in ALLOW for x in e_ids):
    P.append("出现非预期 E 编号：%s" % e_ids)

print()
print("=" * 76)
if P:
    print("发现 %d 项问题：" % len(P))
    for x in P:
        print("  - " + x)
    sys.exit(1)
print("全部 7 项自检通过。")
