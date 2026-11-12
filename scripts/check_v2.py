# -*- coding: utf-8 -*-
"""材料A编写方案 V2 的自检：编号双向闭环 + 事实核对。"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
SRS = pathlib.Path(r"C:\Users\14407\Desktop\作业\软件工程\智慧自习室预约与管理系统-需求规格说明书.md")
FIG = SRS.parent / "figures"
PLAN = pathlib.Path(r"C:\Users\14407\Desktop\作业\chatgpt\材料A编写方案-V2.md")
srs = SRS.read_text(encoding="utf-8")
plan = PLAN.read_text(encoding="utf-8")
problems = []

DEF_PAT = {
    "BR": r"^\|\s*BR-(\d+)\s*\|",
    "ST": r"^\|\s*ST-(\d+)\s*\|",
    "DM": r"^\|\s*DM-(\d+)\s*\|",
    "NFR": r"^\|\s*NFR-(\d+)\s*\|",
    "EX": r"^\|\s*EX-(\d+)\s*\|",
    "P": r"^\|\s*P-(\d+)\s*\|",
    "Q": r"^\|\s*Q-(\d+)\s*\|",
    "SH": r"^\|\s*SH-(\d+)\s*\|",
    "US": r"^\|\s*US-(\d+)\s*\|",
    "UC": r"^\|\s*UC-(\d+)\s*\|",
}

print("=" * 76)
print("自检 2：编号双向闭环（正向 —— 方案引用的编号必须在 SRS V1.1 中存在）")
print("=" * 76)
known = {}
for k, p in DEF_PAT.items():
    known[k] = {"%s-%02d" % (k, int(n)) for n in re.findall(p, srs, re.M)}
known["FR"] = {"FR-%02d" % int(n) for n in re.findall(r"^###\s+4\.\d+\s+FR-(\d+)", srs, re.M)}
known["AC"] = {"AC-%s-%s" % (a, b) for a, b in re.findall(r"^\|\s*AC-(\d+)-(\d+)\s*\|", srs, re.M)}
known["SM"] = {"SM-%02d" % int(n) for n in re.findall(r"^###\s+7\.\d+\s+SM-(\d+)", srs, re.M)}

for k in sorted(known):
    used = set(re.findall(r"\b%s-\d+(?:-\d+)?" % k, plan))
    unknown = sorted(used - known[k])
    if unknown:
        problems.append("方案引用但 SRS V1.1 中不存在的 %s 编号：%s" % (k, unknown))
        print("  %-4s ✗ %s" % (k, unknown))
    else:
        print("  %-4s ✓ 方案引用 %2d 个，全部在 SRS V1.1 中有定义" % (k, len(used)))

print()
print("=" * 76)
print("自检 2（反向）：SRS V1.1 中引用的 SC／PV／V 编号必须能在材料 A 中找到")
print("=" * 76)
# 编号规则表里的「示例」列属于格式说明，不是正文引用，排除后再查
srs_body = re.sub(r"^\|\s*SC / PV / V / AI / E\s*\|.*$", "", srs, flags=re.M)
for k in ("SC", "PV", "V"):
    in_srs = sorted(set(re.findall(r"\b%s-\d+" % k, srs_body)))
    in_plan = sorted(set(re.findall(r"\b%s-\d+" % k, plan)))
    print("  %-4s SRS V1.1 正文引用：%s　方案中定义：%s" % (
        k, in_srs or "无（仅编号规则表的格式示例）",
        "%s…%s" % (in_plan[0], in_plan[-1]) if in_plan else "无"))
    if in_srs:
        problems.append("SRS V1.1 正文仍引用 %s 编号 %s（按 D1 应已改为引用报告）" % (k, in_srs))
    if not in_plan:
        problems.append("方案中未定义 %s 编号" % k)
rule_line = re.search(r"^\|\s*SC / PV / V / AI / E\s*\|.*$", srs, re.M)
print("  编号规则表中的格式示例行：%s" % (rule_line.group(0).strip()[:70] if rule_line else "无"))
print("  该行附有注解，说明这些前缀属于《学生需求分析与 AI 智能体使用验证报告》、本文档不展开其内容。")

print()
print("=" * 76)
print("自检 3：事实核对（方案声明 vs SRS V1.1 实测）")
print("=" * 76)
checks = [
    ("图数量 13 张", len(re.findall(r"<!--\s*FIG:", srs)), 13),
    ("figures 下 .mmd 组数 13", len(list(FIG.glob("*.mmd"))), 13),
    ("ST 最大编号 38", max(int(n) for n in re.findall(r"^\|\s*ST-(\d+)\s*\|", srs, re.M)), 38),
    ("ST 定义条数 38", len(re.findall(r"^\|\s*ST-\d+\s*\|", srs, re.M)), 38),
    ("BR 最大编号 25", max(int(n) for n in re.findall(r"^\|\s*BR-(\d+)\s*\|", srs, re.M)), 25),
    ("P 最大编号 28", max(int(n) for n in re.findall(r"^\|\s*P-(\d+)\s*\|", srs, re.M)), 28),
    ("Q 最大编号 22", max(int(n) for n in re.findall(r"^\|\s*Q-(\d+)\s*\|", srs, re.M)), 22),
    ("SM 图 5 张", len(re.findall(r"^###\s+7\.\d+\s+SM-", srs, re.M)), 5),
]
for name, got, want in checks:
    ok = got == want
    print("  %s %-26s 实测 %-4s 期望 %s" % ("✓" if ok else "✗", name, got, want))
    if not ok:
        problems.append("%s：实测 %s，期望 %s" % (name, got, want))

# 原始资料条数
mixed = [n for n in ["02", "08", "09"] if re.search(r"^\|\s*BR-%s\s*\|[^|]*\|[^|]*原始资料、分析推导" % n, srs, re.M)]
raw = re.findall(r"^\|\s*BR-(\d+)\s*\|[^|]*\|\s*(原始资料[^|]*?)\s*\|", srs, re.M)
print("  含「原始资料」标注的 BR：%s（其中混合标注 %d 条）" % ([r[0] for r in raw], len(mixed)))
if len(raw) != 7:
    problems.append("含原始资料标注的 BR 实测 %d 条，期望 7 条" % len(raw))

# 状态保持类：目标状态列为「—」（即该行是"拒绝／失败且状态不变"的记录）
keep = sorted(set(re.findall(r"^\|\s*(ST-\d+)\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*—\s*\|", srs, re.M)),
              key=lambda x: int(x[3:]))
print("  SRS V1.1 中「状态保持类」转换（目标状态列为「—」）：%s，共 %d 条" % (keep, len(keep)))
expect_keep = ["ST-02", "ST-10", "ST-16", "ST-23", "ST-30", "ST-34", "ST-38"]
if keep != sorted(expect_keep, key=lambda x: int(x[3:])):
    problems.append("状态保持类清单与方案不符：SRS 实测 %s，方案声明 %s" % (keep, expect_keep))

print()
print("=" * 76)
print("自检 4：如实性（不得出现编造的姓名、日期、确认结论）")
print("=" * 76)
bad_words = ["已确认（模拟", "业务方已确认", "教师已确认"]
hit = [w for w in bad_words if w in plan]
print("  越界确认表述：%s" % (hit or "无"))
if hit:
    problems.append("方案出现越界确认表述：%s" % hit)
undone = len(re.findall(r"未开展|待开展|未验证|（待填）", plan))
print("  已标注未开展／待开展／未验证／待填 的位置：%d 处" % undone)
if undone == 0:
    problems.append("方案未标注任何未开展或待填项")

print()
print("=" * 76)
print("自检 5：能力一致性（每条 SC／PV 是否可在原型上执行或已标注未验证）")
print("=" * 76)
sc = sorted(set(re.findall(r"\bSC-\d+", plan)))
pv = sorted(set(re.findall(r"\bPV-\d+", plan)))
print("  方案定义场景 %d 条：%s" % (len(sc), "、".join(sc)))
print("  方案定义验证项 %d 条：%s … %s" % (len(pv), pv[0], pv[-1]))
unverified = re.findall(r"\*\*未验证\*\*（原型未实现）", plan)
print("  标注为「未验证」的 PV 行：%d 条" % len(unverified))
print("  已声明原型新增「登录与锁定」「我的违约与申诉」两个页面（方案甲）")

print()
print("=" * 76)
if problems:
    print("发现 %d 项问题：" % len(problems))
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print("全部自检通过。")
