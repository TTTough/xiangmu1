# -*- coding: utf-8 -*-
"""PV-21—PV-30 批次自检（6 项）。"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = pathlib.Path(r"C:\Users\14407\Desktop\作业\软件工程")
A = R / "智慧自习室预约与管理系统-需求分析质量验证报告.md"
B = R / "智慧自习室预约与管理系统-AI智能体使用验证报告.md"
S = R / "智慧自习室预约与管理系统-需求规格说明书.md"
C = R / "附件" / "00-附件清单.md"
SHOTS = R / "prototype" / "shots"
a, b, s, c = (p.read_text(encoding="utf-8") for p in (A, B, S, C))
P = []

# ---------------------------------------------------------------- 1
print("=" * 76)
print("自检 1：PV 记录数 30、截图 29 张且均存在")
print("=" * 76)
a63 = a[a.find("### A.6.3"):a.find("### A.6.4")]
rows = re.findall(r"^\|\s*(PV-[\dab]+)", a63, re.M)
distinct = sorted({r.rstrip("ab") if r.endswith(("a", "b")) else r for r in rows},
                  key=lambda x: int(x.split("-")[1]))
print("  A.6.3 表格行 %d；去重后的记录 %d 条" % (len(rows), len(distinct)))
print("  记录编号：%s" % "、".join(distinct))
if len(distinct) != 30:
    P.append("PV 记录数为 %d，期望 30" % len(distinct))
want = ["PV-%02d" % i for i in range(1, 19)] + ["PV-%02d" % i for i in range(19, 21)] + \
       ["PV-%02d" % i for i in range(21, 31)]
if distinct != want:
    P.append("PV 编号集合不完整：%s" % [x for x in want if x not in distinct])
files = sorted(p.name for p in SHOTS.glob("*.png"))
print("  截图文件：%d 张" % len(files))
if len(files) != 29:
    P.append("截图文件为 %d 张，期望 29" % len(files))
# 表格里引用的证据文件都必须存在
refs = re.findall(r"shots\\(PV-[\w\-]+\.png)", a63)
missing = [f for f in refs if f not in files]
print("  表格引用的截图 %d 个，缺失 %s" % (len(set(refs)), missing or "无"))
if missing:
    P.append("表格引用了不存在的截图：%s" % missing)
# 未验证项
unv = [r for r in distinct if re.search(r"^\|\s*%s（.*未验证" % r, a63, re.M)]
print("  未验证记录：%s" % "、".join(unv))
if unv != ["PV-19", "PV-20"]:
    P.append("未验证记录应为 PV-19／PV-20，实际 %s" % unv)

# ---------------------------------------------------------------- 2
print()
print("=" * 76)
print("自检 2：A.6.1 第 5 项 / A.6.3 / A.6.5 的「未实现／未验证」表述一致")
print("=" * 76)
a61 = a[a.find("### A.6.1"):a.find("### A.6.2")]
a65 = a[a.find("### A.6.5"):a.find("## A.7")]
absent = [(n, t) for n, t in (("A.6.1", a61), ("A.6.3", a63), ("A.6.5", a65)) if "未实现" not in t and "未验证" not in t]
print("  三处均含「未实现／未验证」表述：%s" % ("✓" if not absent else "✗ %s" % [x[0] for x in absent]))
if absent:
    P.append("以下小节缺少未实现／未验证表述：%s" % [x[0] for x in absent])
# 关键缺失项在 A.6.1 与 A.6.5 都出现
KEY = ["评价", "投诉", "数据分析", "通知", "参数配置", "并发", "统一身份认证"]
for k in KEY:
    both = (k in a61) and (k in a65)
    print("  「%s」：A.6.1 %s ／ A.6.5 %s" % (k, "✓" if k in a61 else "✗", "✓" if k in a65 else "✗"))
    if not both:
        P.append("「%s」未在两处同时出现" % k)
# 不得把缺失写成通过
bad_pass = re.findall(r"PV-(?:19|20)[^\n]*通过", a63)
print("  PV-19／PV-20 未被写成「通过」：%s" % ("✓" if not bad_pass else "✗"))
if bad_pass:
    P.append("PV-19／PV-20 被写成通过")
if "不构成功能验证通过" not in a65:
    P.append("A.6.5 缺少「不构成功能验证通过」边界说明")

# ---------------------------------------------------------------- 3
print()
print("=" * 76)
print("自检 3：A.6.5 统计 68 = 26 + 2 + 40，分组条目合计 40")
print("=" * 76)
nums = re.search(r"\| 完整覆盖 \| (\d+) \|", a65)
part = re.search(r"\| 部分覆盖 \| (\d+) \|", a65)
none_ = re.search(r"\| 无系统截图证据 \| (\d+) \|", a65)
tot = re.search(r"\| SRS 验收标准总数 \| (\d+) \|", a65)
print("  统计表：%s = %s + %s + %s" % (tot.group(1), nums.group(1), part.group(1), none_.group(1)))
if int(nums.group(1)) + int(part.group(1)) + int(none_.group(1)) != int(tot.group(1)):
    P.append("覆盖统计不闭合")
ac_defs = set("AC-%s-%s" % (x, y) for x, y in re.findall(r"^\|\s*AC-(\d+)-(\d+)\s*\|", s, re.M))
print("  SRS 中 AC 定义数：%d" % len(ac_defs))
if len(ac_defs) != int(tot.group(1)):
    P.append("SRS 实际 AC 数 %d 与统计表 %s 不符" % (len(ac_defs), tot.group(1)))
# 分组表
grp = re.findall(r"^\|\s*(FR-\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", a65, re.M)
total = 0
for fr, n, ids in grp:
    expanded = set()
    for m in re.finditer(r"AC-(\d+)-(\d+)", ids):
        expanded.add("AC-%s-%s" % (m.group(1), m.group(2)))
    rng = re.findall(r"AC-(\d+)-(\d+)—AC-(\d+)-(\d+)", ids)
    for g1, s1, g2, e1 in rng:
        for k in range(int(s1), int(e1) + 1):
            expanded.add("AC-%s-%02d" % (g1, k))
    total += int(n)
    ok = len(expanded) >= int(n)
    print("  %-6s 声明 %d 条；编号展开 %d 个 %s" % (fr, int(n), len(expanded), "" if ok else "✗"))
print("  分组条数合计：%d" % total)
if total != 40:
    P.append("分组条数合计 %d，期望 40" % total)
if total != int(none_.group(1)):
    P.append("分组合计与统计表的「无系统截图证据」不一致")

# ---------------------------------------------------------------- 4
print()
print("=" * 76)
print("自检 4：E-02 在 A.9 / B.4 / 00 清单三处均为 29 张")
print("=" * 76)
for nm, txt in (("材料 A 的 A.9", a), ("材料 B 的 B.4", b), ("00-清单第 1 节", c)):
    row = [ln for ln in txt.split("\n") if ln.startswith("| E-02 ") or ln.startswith("| **E-02** ")]
    ok = bool(row) and "29 张" in row[0]
    print("  %-14s %s" % (nm, "✓ 29 张" if ok else "✗ %s" % (row[0][:60] if row else "未找到该行")))
    if not ok:
        P.append("%s 的 E-02 未写 29 张" % nm)

# ---------------------------------------------------------------- 5
print()
print("=" * 76)
print("自检 5：原型版本 v1.1 且注明新增 URL 测试参数")
print("=" * 76)
print("  A.6.1 版本行：%s" % ("✓ v1.1 + URL 参数" if "版本 v1.1" in a61 and "URL 测试参数" in a61 else "✗"))
if not ("版本 v1.1" in a61 and "URL 测试参数" in a61):
    P.append("A.6.1 未记为 v1.1 或未注明 URL 参数")
if re.search(r"\|\s*1\. \*\*原型名称、类型与版本\*\*[^\n]*v1\.0", a):
    P.append("A.6.1 仍写 v1.0")
print("  未残留 v1.0：%s" % ("✓" if not re.search(r"原型[^\n]*版本 v1\.0", a) else "✗"))

# ---------------------------------------------------------------- 6
print()
print("=" * 76)
print("自检 6：三版一致；无遗留「18 张」表述")
print("=" * 76)
import pymupdf
for tag, md, extra in (("材料 A", A, ""), ("材料 B", B, ""), ("00-清单", C, "")):
    dx, pf = md.with_suffix(".docx"), md.with_suffix(".pdf")
    tbl = len(re.findall(r"^\|[\s:|-]+\|\s*$", md.read_text(encoding="utf-8"), re.M))
    d = pymupdf.open(str(pf))
    print("  %-7s md %6.1f KB / %2d 表格 │ docx %6.1f KB │ pdf %7.1f KB / %2d 页" % (
        tag, md.stat().st_size / 1024, tbl, dx.stat().st_size / 1024,
        pf.stat().st_size / 1024, d.page_count))
    if not dx.exists() or not pf.exists():
        P.append("%s 三版不全" % tag)
    if "A.6.5" in md.read_text(encoding="utf-8") and "A.6.5" not in d[0].get_text() + "".join(d[i].get_text() for i in range(d.page_count)):
        P.append("%s 的 pdf 缺 A.6.5" % tag)
left18 = []
NL = chr(10)
for nm, txt in (("材料 A", a), ("材料 B", b), ("00-清单", c)):
    for k, ln in enumerate(txt.split(NL), 1):
        if "18 张" in ln:
            left18.append((nm, k, ln.strip()))


def ok18(line):
    return ("补充至 29 张" in line) or ("当时 18 张" in line) or ("共 18 张；PV-21—PV-30 共 11 张" in line)


print("  仍含「18 张」的行：%d 处" % len(left18))
for nm, k, line in left18:
    print("    %s:%d  %s%s" % (nm, k, line[:56], "  [已补注/分项统计]" if ok18(line) else "  ✗"))
cur = [x for x in left18 if not ok18(x[2])]
print("  其中已补注或属分项统计：%d 处；未处理：%d 处" % (len(left18) - len(cur), len(cur)))
if cur:
    P.append("仍有 %d 处「18 张」未补注：%s" % (len(cur), [(x[0], x[1]) for x in cur]))
print("  00-清单目录树与 E-02：%s" % ("✓ 已为 29 张" if "29 张" in c else "✗"))

print()
print("=" * 76)
if P:
    print("发现 %d 项问题：" % len(P))
    for x in P:
        print("  - " + x)
    sys.exit(1)
print("全部 6 项自检通过。")
