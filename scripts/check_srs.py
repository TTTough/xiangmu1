# -*- coding: utf-8 -*-
"""需求规格说明书自检：编号连续性、定义与引用闭环、追溯矩阵覆盖。"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MD = ROOT / "智慧自习室预约与管理系统-需求规格说明书.md"
text = MD.read_text(encoding="utf-8")
lines = text.split("\n")

# 各类编号的「定义处」正则（行首表格行或标题）
DEFS = {
    "FR":  r"^###\s+4\.\d+\s+FR-(\d+)",
    "US":  r"^\|\s*US-(\d+)\s*\|",
    "UC":  r"^\|\s*UC-(\d+)\s*\|",
    "BR":  r"^\|\s*BR-(\d+)\s*\|",
    "ST":  r"^\|\s*ST-(\d+)\s*\|",
    "NFR": r"^\|\s*NFR-(\d+)\s*\|",
    "EX":  r"^\|\s*EX-(\d+)\s*\|",
    "DM":  r"^\|\s*DM-(\d+)\s*\|",
    "P":   r"^\|\s*P-(\d+)\s*\|",
    "Q":   r"^\|\s*Q-(\d+)\s*\|",
    "AC":  r"^\|\s*AC-(\d+)-(\d+)\s*\|",
}

problems = []
defined = {}

for key, pat in DEFS.items():
    rx = re.compile(pat)
    found = []
    for ln in lines:
        m = rx.match(ln)
        if m:
            found.append("-".join(m.groups()) if key == "AC" else int(m.group(1)))
    defined[key] = found
    if key == "AC":
        nums = sorted(found)
    else:
        nums = sorted(found)
        if nums != list(range(1, len(nums) + 1)):
            # 允许不连续，但要报出缺口
            missing = [n for n in range(1, max(nums) + 1) if n not in nums]
            dup = [n for n in set(nums) if nums.count(n) > 1] if len(nums) != len(set(nums)) else []
            problems.append("%s 编号不连续：定义 %d 个，最大 %d，缺 %s%s"
                            % (key, len(nums), max(nums), missing, "，重复 %s" % dup if dup else ""))
    print("%-4s 定义 %2d 个：%s" % (key, len(nums), nums if len(nums) <= 40 else "%s…%s" % (nums[:3], nums[-3:])))

# 引用闭环：全文出现的编号必须都有定义
def refs(prefix, allow_sub=False):
    rx = re.compile(r"\b%s-(\d+)(?:-(\d+))?" % prefix)
    out = set()
    for m in rx.finditer(text):
        out.add(m.group(0))
    return out

for key in ("FR", "US", "UC", "BR", "ST", "NFR", "EX", "DM", "P", "Q"):
    used = refs(key)
    known = {"%s-%02d" % (key, n) for n in defined[key]}
    unknown = {u for u in used if u not in known}
    if unknown:
        problems.append("%s 存在未定义引用：%s" % (key, sorted(unknown)))
    else:
        print("%-4s 引用闭环 OK（%d 个被引用）" % (key, len(used)))

ac_used = {m.group(0) for m in re.finditer(r"\bAC-\d{2}-\d{2}\b", text)}
ac_known = {"AC-%s-%s" % tuple(d.split("-")) for d in defined["AC"]}
ac_unknown = ac_used - ac_known
if ac_unknown:
    problems.append("AC 存在未定义引用：%s" % sorted(ac_unknown))
else:
    print("AC   引用闭环 OK（%d 个被引用，%d 个定义）" % (len(ac_used), len(ac_known)))

# 追溯矩阵：每个 FR 必须关联 US 与 AC
matrix = re.search(r"### 14\.1 可追溯矩阵([\s\S]*?)### 14\.2", text)
if matrix:
    blk = matrix.group(1)
    for m in re.finditer(r"^\|\s*FR-(\d+)[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", blk, re.M):
        fr, goal, us, uc, br, st, ac = [g.strip() for g in m.groups()]
        name = "FR-%02d" % int(fr)
        for label, val in (("业务目标", goal), ("用户故事", us), ("用例", uc),
                           ("业务规则", br), ("验收标准", ac)):
            if not val or val == "—":
                problems.append("%s 在追溯矩阵中缺少%s" % (name, label))
    print("追溯矩阵：已检查 FR 行的关联完整性")

# 状态图与 ST 表对应
print()
for sm in ("SM-01", "SM-02", "SM-03", "SM-04"):
    seg = re.search(r"### 7\.\d+ %s([\s\S]*?)(?=### 7\.\d+ |## 8 )" % sm, text)
    if not seg:
        problems.append("找不到状态图 %s 的章节" % sm)
        continue
    body = seg.group(1)
    rows = sorted(set(int(x) for x in re.findall(r"^\|\s*ST-(\d+)\s*\|", body, re.M)))
    print("%-6s ST 表 %2d 条：%s" % (sm, len(rows), rows))

print()
if problems:
    print("发现 %d 个问题：" % len(problems))
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print("自检通过：编号连续、引用闭环、追溯矩阵无缺口。")
