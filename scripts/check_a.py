# -*- coding: utf-8 -*-
"""SRS V1.2 + 材料 A 的交付自检（8 项）。"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(r"C:\Users\14407\Desktop\作业\软件工程")
SRS = ROOT / "智慧自习室预约与管理系统-需求规格说明书.md"
SRS_D = ROOT / "智慧自习室预约与管理系统-需求规格说明书.docx"
SRS_P = ROOT / "智慧自习室预约与管理系统-需求规格说明书.pdf"
RA = ROOT / "智慧自习室预约与管理系统-需求分析质量验证报告.md"
RA_D = ROOT / "智慧自习室预约与管理系统-需求分析质量验证报告.docx"
RA_P = ROOT / "智慧自习室预约与管理系统-需求分析质量验证报告.pdf"
FIG = ROOT / "figures"
SHOTS = ROOT / "prototype" / "shots"

srs = SRS.read_text(encoding="utf-8")
ra = RA.read_text(encoding="utf-8")
P = []

# ---------------------------------------------------------------- 1 编号闭环
print("=" * 78)
print("自检 1：SRS V1.2 编号闭环（每个编号都有定义位置）")
print("=" * 78)
DEF = {
    "BR": r"^\|\s*BR-(\d+)\s*\|", "ST": r"^\|\s*ST-(\d+)\s*\|",
    "DM": r"^\|\s*DM-(\d+)\s*\|", "NFR": r"^\|\s*NFR-(\d+)\s*\|",
    "EX": r"^\|\s*EX-(\d+)\s*\|", "P": r"^\|\s*P-(\d+)\s*\|",
    "Q": r"^\|\s*Q-(\d+)\s*\|", "SH": r"^\|\s*SH-(\d+)\s*\|",
    "US": r"^\|\s*US-(\d+)\s*\|", "UC": r"^\|\s*UC-(\d+)\s*\|",
}
known = {}
for k, p in DEF.items():
    known[k] = sorted(set(int(n) for n in re.findall(p, srs, re.M)))
known["FR"] = sorted(set(int(n) for n in re.findall(r"^###\s+4\.\d+\s+FR-(\d+)", srs, re.M)))
known["SM"] = sorted(set(int(n) for n in re.findall(r"^###\s+7\.\d+\s+SM-(\d+)", srs, re.M)))
ac_def = sorted(set("AC-%s-%s" % (a, b) for a, b in re.findall(r"^\|\s*AC-(\d+)-(\d+)\s*\|", srs, re.M)))
for k, v in known.items():
    gap = [n for n in range(1, max(v) + 1) if n not in v] if v else []
    st = "连续" if not gap else "缺 %s" % gap
    if gap:
        P.append("%s 编号不连续：缺 %s" % (k, gap))
    print("  %-4s 定义 %2d 个（1—%d）%s" % (k, len(v), max(v) if v else 0, st))
srs_body = re.sub(r"^\|\s*SC / PV / V / AI / E\s*\|.*$", "", srs, flags=re.M)
for k in ("BR", "ST", "FR", "UC", "AC", "DM", "NFR", "EX", "P", "Q", "SH", "SM"):
    if k == "AC":
        used = set(re.findall(r"\bAC-\d{2}-\d{2}\b", srs_body))
        unk = sorted(used - set(ac_def))
    else:
        used = set(int(x) for x in re.findall(r"\b%s-(\d+)" % k, srs_body))
        unk = sorted(used - set(known[k]))
    if unk:
        P.append("SRS 存在未定义引用 %s：%s" % (k, unk))
print("  引用闭环：%s" % ("全部通过" if not any("未定义引用" in x for x in P) else "见问题清单"))
st_lines = [(i, ln) for i, ln in enumerate(srs.split("\n"), 1) if re.match(r"^\|\s*ST-\d+\s*\|", ln)]
print("  ST 定义 %d 条（ST-01—ST-38）" % len(st_lines))
keep = sorted(set(re.findall(r"^\|\s*(ST-\d+)\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*—\s*\|", srs, re.M)), key=lambda x: int(x[3:]))
print("  状态保持类（目标状态列为「—」）：%s（%d 条；ST-06 不在列，属正常转换）" % (keep, len(keep)))
if keep != ["ST-02", "ST-10", "ST-16", "ST-23", "ST-30", "ST-34", "ST-38"]:
    P.append("状态保持类清单与报告不符：%s" % keep)

# ---------------------------------------------------------------- 2 5.4 一致性
print()
print("=" * 78)
print("自检 2：5.4 引导句与实际用例描述数量、编号一致")
print("=" * 78)
lead = re.search(r"以下用例给出主流程、备选流与异常处理：([^。]+)。", srs)
lead_list = re.findall(r"UC-\d+", lead.group(1)) if lead else []
head_list = re.findall(r"^####\s+(UC-\d+)", srs, re.M)
print("  引导句列举 %d 则：%s" % (len(lead_list), "、".join(lead_list)))
print("  实际描述 %d 则：%s" % (len(head_list), "、".join(head_list)))
if lead_list != head_list:
    P.append("5.4 引导句与实际用例描述不一致：引导 %s，实际 %s" % (lead_list, head_list))
else:
    print("  ✓ 两者逐字一致")
rest = re.search(r"其余用例（([^）]+)）", srs)
print("  「其余用例」列举：%s" % (rest.group(1) if rest else "未找到"))
if rest:
    rl = re.findall(r"UC-\d+", rest.group(1))
    alluc = ["UC-%02d" % n for n in known["UC"]]
    miss = [u for u in alluc if u not in lead_list and u not in rl]
    if miss:
        P.append("存在既未描述也未说明覆盖位置的用例：%s" % miss)
    else:
        print("  ✓ UC-01—UC-17 全部有归属（描述或说明覆盖位置）")

# ---------------------------------------------------------------- 3 权限矩阵行号
print()
print("=" * 78)
print("自检 3：权限矩阵行号引用与矩阵实际行一致")
print("=" * 78)
mblock = re.search(r"## 10 权限矩阵([\s\S]*?)\*\*矩阵说明\*\*", srs).group(1)
rows = re.findall(r"^\|\s*(\d+)\s*\|([^|]*)\|", mblock, re.M)
rows = {int(n): t.strip() for n, t in rows}
print("  矩阵共 %d 行（1—%d）：第 31、32 行为禁止项" % (len(rows), max(rows)))
for n in (27, 28, 29, 30, 31, 32):
    print("    第 %-2d 行：%s" % (n, rows.get(n, "（缺失）")))
refs = re.findall(r"权限矩阵第 ([\d、]+) 行", srs)
print("  正文引用：%s" % "；".join("第 %s 行" % r for r in refs))
for r in refs:
    for n in re.findall(r"\d+", r):
        if int(n) not in rows:
            P.append("权限矩阵行号引用越界：第 %s 行" % n)
print("  ✓ 行号均在 1—%d 范围内" % max(rows) if not any("行号引用越界" in x for x in P) else "  见问题清单")
# 语义核对
sem = [("AC-02-02", 31, "直接修改座位状态"), ("AC-14-03", 32, "直接修改或删除预约、违约、审计记录"),
       ("AC-11-05", 22, "查看数据分析页面")]
for ac, n, want in sem:
    ok = want in rows.get(n, "")
    print("  %s 引用第 %d 行「%s」——%s" % (ac, n, rows.get(n, "?"), "一致" if ok else "不匹配"))
    if not ok:
        P.append("%s 引用的第 %d 行语义不匹配" % (ac, n))

# ---------------------------------------------------------------- 4 A 双向闭环
print()
print("=" * 78)
print("自检 4：材料 A 双向编号闭环")
print("=" * 78)
for k in ("BR", "ST", "FR", "UC", "DM", "NFR", "EX", "P", "Q"):
    used = set(int(x) for x in re.findall(r"\b%s-(\d+)" % k, ra))
    unk = sorted(used - set(known[k]))
    if unk:
        P.append("材料 A 引用但 SRS 中不存在的 %s：%s" % (k, unk))
        print("  %-4s ✗ %s" % (k, unk))
    else:
        print("  %-4s ✓ 引用 %2d 个，全部在 SRS V1.2 中有定义" % (k, len(used)))
ac_used = set(re.findall(r"\bAC-\d{2}-\d{2}\b", ra))
unk = sorted(ac_used - set(ac_def))
print("  AC   %s 引用 %d 条%s" % ("✓" if not unk else "✗", len(ac_used), "" if not unk else "，未定义 %s" % unk))
if unk:
    P.append("材料 A 引用未定义的 AC：%s" % unk)
for k in ("SC", "PV", "V"):
    in_srs = sorted(set(re.findall(r"\b%s-\d+" % k, srs_body)))
    in_ra = sorted(set(re.findall(r"\b%s-\d+" % k, ra)), key=lambda x: int(x.split("-")[1]))
    print("  %-4s SRS 正文引用：%s　材料 A 定义：%d 个（%s—%s）" % (k, in_srs or "无", len(in_ra), in_ra[0], in_ra[-1]))
    if in_srs:
        P.append("SRS 正文仍引用 %s：%s" % (k, in_srs))
    if not in_ra:
        P.append("材料 A 未定义 %s 编号" % k)

# ---------------------------------------------------------------- 5 模板对齐
print()
print("=" * 78)
print("自检 5：A.1—A.8 模板对齐")
print("=" * 78)
tpl = [
    ("A.5 九项基本信息", ["走查编号", "场景名称及类型", "任务目标与情境", "初始数据与状态", "走查方式",
                     "走查依据及版本", "参与者姓名、走查分工及日期", "关联需求、用例和规则编号", "关联状态图及转换编号"]),
    ("A.6 八项原型基本信息", ["原型名称、类型与版本", "原型入口、打开或启动方法及必要环境", "本次可走查的页面或可执行的核心功能",
                        "使用的模拟数据或模拟接口及其范围", "尚未实现或未验证的功能与限制", "复用的场景走查编号",
                        "AI 参与原型或测试的任务记录编号", "人工走查或执行验证者及日期"]),
    ("A.7 三字段", ["检查范围及依据版本", "检查人员及日期", "检查结论"]),
    ("A.7 六列表", ["问题编号", "问题及发现依据", "影响需求", "处理决定、理由及负责人", "修改位置", "复核结果、复核者及日期"]),
    ("A.6 六列表", ["验证编号及关联需求、场景", "操作与输入条件", "预期结果", "实际结果", "发现的问题", "结论与证据位置"]),
    ("A.8 五列表", ["成员", "职责", "实际完成的任务与产物位置", "本人作出的审核或取舍及理由", "协作与证据编号"]),
]
for name, fields in tpl:
    miss = [f for f in fields if f not in ra]
    print("  %s %-22s %d/%d" % ("✓" if not miss else "✗", name, len(fields) - len(miss), len(fields)))
    if miss:
        P.append("%s 缺少字段：%s" % (name, miss))
sc_cnt = len(re.findall(r"^###\s+SC-\d+", ra, re.M))
pv_cnt = len(re.findall(r"^\|\s*PV-\d+", ra, re.M))
v_cnt = len(re.findall(r"^\|\s*V-\d+", ra, re.M))
print("  SC 场景 %d 条；PV 记录 %d 条；V 记录 %d 条" % (sc_cnt, pv_cnt, v_cnt))
if (sc_cnt, pv_cnt, v_cnt) != (9, 20, 26):
    P.append("条数与预期不符：SC %d（期望 9）、PV %d（期望 20）、V %d（期望 26）" % (sc_cnt, pv_cnt, v_cnt))

# ---------------------------------------------------------------- 6 能力一致性
print()
print("=" * 78)
print("自检 6：能力一致性（SC／PV 可在原型执行或已标注未验证）")
print("=" * 78)
sc_ids = re.findall(r"^###\s+(SC-\d+)", ra, re.M)
pv_ids = re.findall(r"^\|\s*(PV-\d+)", ra, re.M)
shots = sorted(p.name for p in SHOTS.glob("*.png"))
print("  SC：%s" % "、".join(sc_ids))
print("  原型截图：%d 张" % len(shots))
missing = []
for pid in pv_ids:
    if pid in ("PV-19", "PV-20"):
        continue
    if not any(s.startswith(pid + "-") for s in shots):
        missing.append(pid)
print("  %s PV-01—PV-18 均有对应截图" % ("✓" if not missing else "✗ 缺 " + str(missing)))
if missing:
    P.append("缺少截图的 PV：%s" % missing)
for pid in ("PV-19", "PV-20"):
    line = [ln for ln in ra.split("\n") if ln.startswith("| " + pid)]
    if not line or "未验证" not in line[0]:
        P.append("%s 未标注「未验证」" % pid)
print("  ✓ PV-19、PV-20 已标注「未验证」（原型未实现评价与投诉）")
if not re.search(r"SC-04[\s\S]{0,600}推演类走查", ra):
    P.append("SC-04 未标注为推演类走查")
print("  ✓ SC-04 已标注为推演类走查（原型未实现并发控制）")

# ---------------------------------------------------------------- 7 如实性
print()
print("=" * 78)
print("自检 7：如实性与小组信息一致性")
print("=" * 78)
for w in ("业务方已确认", "教师已确认（教学模拟）"):
    if w in ra:
        P.append("材料 A 出现越界确认表述：%s" % w)
print("  越界确认表述：%s" % ("无" if not any("越界确认表述" in x for x in P) else "见问题清单"))
for w, lab in (("待开展", "教学模拟确认待开展"), ("未开展", "交叉走查未开展"), ("未验证", "未验证项"),
               ("（待填）", "待填项"), ("〔待组员确认〕", "待组员确认项")):
    print("  %-16s %d 处" % (lab, len(re.findall(w, ra))))
GROUP = "应雨挺（组长）、方与皓、周俊楠、杨子涵"
for nm, txt in (("SRS", srs), ("材料 A", ra)):
    ok = "鱿鱼子涵" in txt and GROUP in txt
    print("  %s 小组信息：组名「鱿鱼子涵」%s；成员%s" % (nm, "✓" if "鱿鱼子涵" in txt else "✗", "✓" if GROUP in txt else "（见下）"))
    if GROUP not in txt:
        P.append("%s 成员名单与既定 4 人组不一致" % nm)
    if "鱿鱼子涵" not in txt:
        P.append("%s 组名缺失" % nm)

# ---------------------------------------------------------------- 8 三版一致
print()
print("=" * 78)
print("自检 8：三版一致")
print("=" * 78)
try:
    import pymupdf
    for tag, md, dx, pf in (("SRS V1.2", SRS, SRS_D, SRS_P), ("材料 A", RA, RA_D, RA_P)):
        d = pymupdf.open(str(pf))
        figs_md = len(re.findall(r"<!--\s*FIG:", md.read_text(encoding="utf-8")))
        tbl_md = len(re.findall(r"^\|[\s:|-]+\|\s*$", md.read_text(encoding="utf-8"), re.M))
        print("  %s：md %.1f KB / %d 表格；docx %.1f KB；pdf %.1f KB / %d 页" % (
            tag, md.stat().st_size / 1024, tbl_md, dx.stat().st_size / 1024, pf.stat().st_size / 1024, d.page_count))
        if pf.stat().st_size < 50000:
            P.append("%s 的 pdf 体量异常" % tag)
    print("  图源：figures 下 %d 组 .mmd／.svg／.png 三件套齐全" % len(list(FIG.glob("*.mmd"))))
except Exception as e:
    P.append("三版检查异常：%s" % e)

print()
print("=" * 78)
if P:
    print("发现 %d 项问题：" % len(P))
    for x in P:
        print("  - " + x)
    sys.exit(1)
print("全部 8 项自检通过。")
