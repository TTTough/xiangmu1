# -*- coding: utf-8 -*-
"""2026-10-29 交付自检：7 项。"""
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
s, a, b, c, e7 = (p.read_text(encoding="utf-8") for p in (S, A, B, C, E7))
P = []

# ---------------------------------------------------------------- 1
print("=" * 76)
print("自检 1：标记清理与走查口径")
print("=" * 76)
for nm, txt in (("SRS", s), ("材料 A", a), ("材料 B", b), ("00-附件清单", c), ("E-07", e7)):
    n = txt.count("〔待组员确认〕")
    print("  %-12s 〔待组员确认〕 %d 处" % (nm, n))
    if n:
        P.append("%s 仍残留 %d 处〔待组员确认〕" % (nm, n))
a23 = a[a.find("### A.2.3"):a.find("### A.3")]
print("  A.2.3 内「待开展」：%d 处" % a23.count("待开展"))
if "待开展" in a23:
    P.append("A.2.3 仍含「待开展」")
cross = "未开展" in a
print("  交叉走查表述：%s" % ("仍为「未开展」" if "未开展（本组未邀请其他组参与交叉走查）" in a else "见下"))
if "未开展（本组未邀请其他组参与交叉走查）" not in a:
    P.append("交叉走查表述被改动")
for nm, txt in (("SRS", s), ("材料 A", a), ("材料 B", b)):
    if "教学模拟尚未开展" in txt or "教学模拟确认未开展" in txt:
        P.append("%s 仍含「教学模拟未开展」表述" % nm)

# ---------------------------------------------------------------- 2
print()
print("=" * 76)
print("自检 2：SRS 附录 A 的 15 行 / 附录 B 的 B.1 / A.2.3 的 8 条，逐条一致")
print("=" * 76)
# 附录 A
apxA = {}
for ln in s.split("\n"):
    if ln.startswith("| P-"):
        cells = [x.strip() for x in ln.split("|")]
        if len(cells) > 6:
            apxA[cells[1]] = cells[6]
CONFIRM = ["P-%02d" % i for i in range(1, 14)] + ["P-20", "P-21"]
okA = [k for k in CONFIRM if "教学模拟已确认（2026-10-29）" in apxA.get(k, "")]
print("  附录 A：15 行中标记「教学模拟已确认（2026-10-29）」的共 %d 行" % len(okA))
if len(okA) != 15:
    P.append("附录 A 标记行数 %d，期望 15：缺 %s" % (len(okA), [k for k in CONFIRM if k not in okA]))
others = [k for k, v in apxA.items() if k not in CONFIRM and ("待确认" not in v and "团队已复核" not in v)]
print("  附录 A：非确认范围的行仍为「待确认」：%s" % ("是" if not others else "异常 %s" % others))
if others:
    P.append("附录 A 有非范围条目被误标：%s" % others)

# 附录 B B.1
b1 = s[s.find("### B.1 教学模拟确认结论"):s.find("## 附录 C")]
rows_b1 = re.findall(r"^\|\s*(T-\d{2})（[^|]*\|", b1, re.M)
print("  附录 B 的 B.1：%d 条议题行 %s" % (len(rows_b1), rows_b1))
if rows_b1 != ["T-%02d" % i for i in range(1, 9)]:
    P.append("B.1 议题行不完整：%s" % rows_b1)
if "Q-01 与 Q-09 保持「待确认」" not in b1:
    P.append("B.1 未声明 Q-01／Q-09 仍待确认")

# A.2.3
rows_a = re.findall(r"^\|\s*(T-\d{2})\s*\|", a23, re.M)
print("  A.2.3：%d 条议题行 %s" % (len(rows_a), rows_a))
if rows_a != ["T-%02d" % i for i in range(1, 9)]:
    P.append("A.2.3 议题行不完整：%s" % rows_a)
# E-07
rows_e = re.findall(r"^\|\s*(T-\d{2})\s*\|", e7, re.M)
print("  E-07：%d 条议题行" % len(rows_e))
if rows_e != ["T-%02d" % i for i in range(1, 9)]:
    P.append("E-07 议题行不完整：%s" % rows_e)
# 三处结论文字一致性：抽取每行的「结论」列（第 6 列）比对
def concl(txt):
    out = {}
    for ln in txt.split("\n"):
        if ln.startswith("| T-"):
            cells = [x.strip() for x in ln.split("|")]
            if len(cells) >= 8:
                out[cells[1]] = cells[6]
    return out
ca, ce = concl(a23), concl(e7)
diff = [k for k in ca if k in ce and ca[k] != ce[k]]
print("  A.2.3 与 E-07 的结论列逐条一致：%s" % ("是" if not diff else "否 %s" % diff))
if diff:
    P.append("A.2.3 与 E-07 结论不一致：%s" % diff)

# ---------------------------------------------------------------- 3
print()
print("=" * 76)
print("自检 3：E-07 新名称在 A.9 / B.4 / 00 清单四处同步")
print("=" * 76)
NEWNAME = "E-07-教学模拟确认记录.md"
OLDNAME = "E-07-教学模拟确认记录模板"
for nm, txt in (("材料 A 的 A.9", a), ("材料 B 的 B.4", b), ("00-清单表格", c)):
    has_new = NEWNAME in txt
    has_old = OLDNAME in txt
    print("  %-14s 新名 %s ｜ 旧名 %s" % (nm, "✓" if has_new else "✗", "✗ 残留" if has_old else "✓ 无"))
    if not has_new:
        P.append("%s 未使用 E-07 新名称" % nm)
    if has_old:
        P.append("%s 仍含旧模板名" % nm)
tree_ok = "E-07-教学模拟确认记录.md / .docx / .pdf" in c
print("  00-清单目录树        %s" % ("✓ 已改名" if tree_ok else "✗"))
if not tree_ok:
    P.append("00-清单目录树未改名")
vol_ok = "| E-07 教学模拟确认记录 | 5.3 KB | 40.5 KB | 262.0 KB |" in c
print("  00-清单体量对照表    %s" % ("✓ 已更新" if vol_ok else "✗"))
if not vol_ok:
    P.append("00-清单体量表未更新")
sec5 = "已归档为 E-07（教学模拟，2026-10-29）" in c and "已确认（见材料 A 的 A.8）" in c
print("  00-清单第 5 节       %s" % ("✓ 两行已更新" if sec5 else "✗"))
if not sec5:
    P.append("00-清单第 5 节未更新")
for f in ("附件/E-07-教学模拟确认记录.md", "附件/E-07-教学模拟确认记录.docx", "附件/E-07-教学模拟确认记录.pdf"):
    ex = (R / f).exists()
    print("  文件存在 %-42s %s" % (f, "✓" if ex else "✗"))
    if not ex:
        P.append("缺少文件 %s" % f)
arch = (R / "_work" / "archive" / "E-07-教学模拟确认记录模板.md").exists()
print("  旧模板已归档至 _work\\archive\\                %s" % ("✓" if arch else "✗"))
if not arch:
    P.append("旧模板未归档")

# ---------------------------------------------------------------- 4
print()
print("=" * 76)
print("自检 4：四人分工在 A.8 / A.5 / A.6.1 / A.7 / B.2 中互相一致")
print("=" * 76)
PEOPLE = ["应雨挺", "方与皓", "周俊楠", "杨子涵"]
a8 = a[a.find("## A.8"):a.find("## A.9")]
for p in PEOPLE:
    rows = len(re.findall(r"^\|\s*" + p, a8, re.M))
    print("  A.8 中 %-4s 行数 %d%s" % (p, rows, "" if rows == 1 else "  ✗"))
    if rows != 1:
        P.append("A.8 中 %s 有 %d 行" % (p, rows))
# A.5 参与者
print("  A.5 参与者行：%d 行，均为「方与皓（走查执行）、周俊楠（记录）、杨子涵（走查依据整理）」" %
      a.count("参与者姓名、走查分工及日期：方与皓（走查执行）"))
if a.count("参与者姓名、走查分工及日期：方与皓（走查执行）") != 9:
    P.append("A.5 参与者行不是 9 行")
# A.7 责任人分布
owner = {}
for ln in a.split("\n"):
    if ln.startswith("| V-"):
        cells = [x.strip() for x in ln.split("|")]
        if len(cells) > 4:
            m = re.search(r"负责人：([\u4e00-\u9fa5]{2,3})", cells[4])
            if m:
                owner.setdefault(m.group(1), []).append(cells[1])
print("  A.7 负责人分布：%s" % {k: len(v) for k, v in owner.items()})
exp = {"杨子涵": 18, "应雨挺": 1, "周俊楠": 4, "方与皓": 3}
for k, n in exp.items():
    if len(owner.get(k, [])) != n:
        P.append("A.7 负责人 %s 为 %d 条，期望 %d" % (k, len(owner.get(k, [])), n))
# B.2 操作者
b2 = b[b.find("## B.2"):b.find("## B.3")]
for p in PEOPLE:
    n = len(re.findall(p, b2))
    print("  B.2 中提及 %-4s %d 次" % (p, n))
if "周俊楠（审查执行）" not in b2 or "杨子涵（需求文档主笔）" not in b2:
    P.append("B.2 的操作者未按分工具名")
# 冲突检查：V-09 处理人应是应雨挺
v09 = [ln for ln in a.split("\n") if ln.startswith("| V-09")]
if v09 and "负责人：应雨挺" not in v09[0]:
    P.append("V-09 的处理人不是应雨挺")

# ---------------------------------------------------------------- 5
print()
print("=" * 76)
print("自检 5：确认口径（业务方确认必带「教学模拟」，教师确认仍为未发生）")
print("=" * 76)
_all = a + b + s + e7
bad = []
for m in re.finditer(r"业务方已确认", _all):
    seg = _all[max(0, m.start() - 12):m.start() + 14]
    if "（教学模拟）" in seg:
        continue
    if "不代表真实业务方已确认" in _all[max(0, m.start() - 12):m.start() + 10]:
        continue
    if "**业务方已确认**／**教师已确认**" in _all[max(0, m.start() - 8):m.start() + 20]:
        continue
    bad.append(_all[max(0, m.start() - 20):m.start() + 20].replace(chr(10), " "))
print("  不带「（教学模拟）」且非否定／非定义表述的业务方已确认：%d 处" % len(bad))
for x in bad:
    print("    %s" % x)
if bad:
    P.append("存在不带（教学模拟）的业务方已确认 %d 处" % len(bad))
print("  A.2.3 表内「业务方已确认（教学模拟）」：%d 处（期望 8）" % a23.count("业务方已确认（教学模拟）"))
if a23.count("业务方已确认（教学模拟）") != 8:
    P.append("A.2.3 的确认状态行数不是 8")
if "教师确认 | **未发生**" not in b:
    P.append("材料 B 的教师确认未写「未发生」")
else:
    print("  材料 B 的教师确认：**未发生** ✓")
if "**已发生（教学模拟）**" not in b:
    P.append("材料 B 的业务方确认未标为「已发生（教学模拟）」")
else:
    print("  材料 B 的业务方确认：**已发生（教学模拟）** ✓")
if "不代表真实业务方或任课教师已经确认" not in s or "不代表真实业务方" not in e7:
    P.append("SRS 或 E-07 缺少「不代表真实业务方」声明")
else:
    print("  SRS 与 E-07 均含「不代表真实业务方」声明 ✓")

# ---------------------------------------------------------------- 6
print()
print("=" * 76)
print("自检 6：三版一致（表格行数与体量）")
print("=" * 76)
try:
    import pymupdf
    for tag, md in (("SRS V1.3", S), ("材料 A", A), ("材料 B", B), ("00-清单", C), ("E-07", E7)):
        dx, pf = md.with_suffix(".docx"), md.with_suffix(".pdf")
        tbl = len(re.findall(r"^\|[\s:|-]+\|\s*$", md.read_text(encoding="utf-8"), re.M))
        pg = pymupdf.open(str(pf)).page_count if pf.exists() else 0
        print("  %-9s md %6.1f KB / %2d 表格 │ docx %7.1f KB │ pdf %7.1f KB / %2d 页" % (
            tag, md.stat().st_size / 1024, tbl,
            dx.stat().st_size / 1024 if dx.exists() else 0,
            pf.stat().st_size / 1024 if pf.exists() else 0, pg))
        if not dx.exists() or not pf.exists():
            P.append("%s 三版不全" % tag)
    figs = len(re.findall(r"<!--\s*FIG:", s))
    print("  SRS 图序号：%d 张（figures 下 %d 组）" % (figs, len(list((R / "figures").glob("*.mmd")))))
    if figs != 13:
        P.append("SRS 图数量异常 %d" % figs)
except Exception as ex:
    P.append("三版检查异常：%s" % ex)

# ---------------------------------------------------------------- 7
print()
print("=" * 76)
print("自检 7：编号闭环（T / SC / PV / V）")
print("=" * 76)
for pre, lo, hi in (("T", 1, 8), ("SC", 1, 9), ("PV", 1, 20), ("V", 1, 26)):
    ids = set(x.group(1) for x in re.finditer(pre + r"-(\d{2})", a + b + e7 + s))
    want = {"%02d" % i for i in range(lo, hi + 1)}
    missing = sorted(want - ids)
    print("  %-3s 应存在 %2d 个（%s-%02d—%s-%02d）；缺失 %s" % (pre, hi, pre, lo, pre, hi, missing or "无"))
    if missing:
        P.append("%s 编号缺失：%s" % (pre, missing))
v_def = sorted(set(re.findall(r"^\|\s*(V-\d{2})\s*\|", a, re.M)))
print("  V 在材料 A 中有定义行 %d 条" % len(v_def))
if len(v_def) != 26:
    P.append("V 定义行 %d 条，期望 26" % len(v_def))

print()
print("=" * 76)
if P:
    print("发现 %d 项问题：" % len(P))
    for x in P:
        print("  - " + x)
    sys.exit(1)
print("全部 7 项自检通过。")
