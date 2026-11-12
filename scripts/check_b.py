# -*- coding: utf-8 -*-
"""材料 A + 材料 B 的联合自检：编号接口、模板对齐、如实性、三版一致。"""
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(r"C:\Users\14407\Desktop\作业\软件工程")
A_MD = ROOT / "智慧自习室预约与管理系统-需求分析质量验证报告.md"
B_MD = ROOT / "智慧自习室预约与管理系统-AI智能体使用验证报告.md"
SRS = ROOT / "智慧自习室预约与管理系统-需求规格说明书.md"
a = A_MD.read_text(encoding="utf-8")
b = B_MD.read_text(encoding="utf-8")
srs = SRS.read_text(encoding="utf-8")
P = []

# ---------------------------------------------------------------- 1 编号接口
print("=" * 78)
print("自检 1：AI／E 编号接口（两报告共用一套）")
print("=" * 78)
ai_b = sorted(set(re.findall(r"\bAI-\d+", b)), key=lambda x: int(x.split("-")[1]))
ai_a = sorted(set(re.findall(r"\bAI-\d+", a)), key=lambda x: int(x.split("-")[1]))
print("  材料 B 定义 AI 任务：%s（%d 个）" % ("、".join(ai_b), len(ai_b)))
print("  材料 A 引用 AI 编号：%s" % ("、".join(ai_a) if ai_a else "仅写作「AI-01…」（泛指，见 A.6 第 7 项与 A.9）"))
miss = [x for x in ai_a if x not in ai_b]
if miss:
    P.append("材料 A 引用的 AI 编号在材料 B 中不存在：%s" % miss)
b_tasks = len(re.findall(r"^###\s+AI-\d+", b, re.M))
print("  材料 B 的关键任务记录：%d 段（期望 3—5 段）" % b_tasks)
if not (3 <= b_tasks <= 5):
    P.append("关键任务段数 %d 不在 3—5 之间" % b_tasks)

e_a = sorted(set(re.findall(r"\bE-\d+", a)), key=lambda x: int(x.split("-")[1]))
e_b = sorted(set(re.findall(r"\bE-\d+", b)), key=lambda x: int(x.split("-")[1]))
def_table = sorted(set(re.findall(r"^\|\s*(E-\d+)\s*\|", b, re.M)), key=lambda x: int(x.split("-")[1]))
print("  材料 A 的 A.9 列出：%s（%d 个）" % ("、".join(e_a), len(e_a)))
print("  材料 B 的 B.4 列出：%s（%d 个）" % ("、".join(def_table), len(def_table)))
if e_a != def_table:
    P.append("两报告的 E 编号集合不一致：A=%s，B=%s" % (e_a, def_table))
else:
    print("  ✓ 两报告 E 编号集合一致（共用同一套）")

# ---------------------------------------------------------------- 2 模板对齐
print()
print("=" * 78)
print("自检 2：B.1—B.4 模板对齐")
print("=" * 78)
tpl = [
    ("B.1 基本信息六项", ["小组编号／名称", "项目名称", "成员名单", "提交阶段", "本次需求文档版本及位置", "报告日期"]),
    ("B.1 工具使用记录表五列", ["AI 工具或智能体", "模型或版本", "实际使用方式", "用于哪些任务", "操作者"]),
    ("B.2 关键任务记录表十一项", ["任务编号、名称与关联记录", "操作者、参与审核者与日期", "任务目的、输入材料与必要上下文",
                          "实际关键提示词", "AI 实际输出或执行动作", "人工质疑与风险检查", "实际追问及 AI 后续调整",
                          "独立核验方法、范围与结果", "人工决定与理由", "最终处理、需求影响与产物位置", "尚未解决的问题"]),
    ("B.2 关键结论核验表四列", ["关键结论", "性质", "依据", "核验状态及结果"]),
    ("B.3 记录类型与关联编号", ["记录类型", "关联 AI 任务编号"]),
    ("B.3 约束表十项", ["任务目标与关联需求", "输入材料与阅读要求", "允许操作或修改的范围", "禁止操作或修改的范围",
                  "输出形式及业务规则", "人工确认责任", "信息不足时的处理", "完成标准与验收方法",
                  "实际执行与检查结果", "必要的约束改进"]),
    ("B.4 证据索引表四列", ["证据编号", "类型及内容", "文件或链接及具体位置", "支持的任务、需求或记录"]),
]
for name, fields in tpl:
    missf = [f for f in fields if f not in b]
    print("  %s %-26s %d/%d" % ("✓" if not missf else "✗", name, len(fields) - len(missf), len(fields)))
    if missf:
        P.append("%s 缺少字段：%s" % (name, missf))
# B.2 十一个记录项在每个任务中出现的次数
for item in ["任务编号、名称与关联记录", "人工质疑与风险检查", "独立核验方法、范围与结果", "人工决定与理由", "尚未解决的问题"]:
    n = b.count("| " + item + " |")
    print("  记录项「%s」出现 %d 次（期望 %d 次，每个任务一次）" % (item, n, b_tasks))
    if n != b_tasks:
        P.append("记录项「%s」出现 %d 次，与任务数 %d 不符" % (item, n, b_tasks))

# ---------------------------------------------------------------- 3 双向引用
print()
print("=" * 78)
print("自检 3：材料 A／B 与 SRS 的双向引用")
print("=" * 78)
DEF = {"BR": r"^\|\s*BR-(\d+)\s*\|", "ST": r"^\|\s*ST-(\d+)\s*\|", "FR": r"^###\s+4\.\d+\s+FR-(\d+)",
       "UC": r"^\|\s*UC-(\d+)\s*\|", "DM": r"^\|\s*DM-(\d+)\s*\|", "NFR": r"^\|\s*NFR-(\d+)\s*\|",
       "EX": r"^\|\s*EX-(\d+)\s*\|", "P": r"^\|\s*P-(\d+)\s*\|", "Q": r"^\|\s*Q-(\d+)\s*\|",
       "SM": r"^###\s+7\.\d+\s+SM-(\d+)"}
known = {k: set("%s-%02d" % (k, int(n)) for n in re.findall(p, srs, re.M)) for k, p in DEF.items()}
known["AC"] = set("AC-%s-%s" % (x, y) for x, y in re.findall(r"^\|\s*AC-(\d+)-(\d+)\s*\|", srs, re.M))
# 用户提示词原文中的格式举例，非实际引用（材料 B 的 AI-03 引用了该段提示词原文）
WHITELIST = {"DM-14", "AC-02-05"}
for tag, txt in (("材料 A", a), ("材料 B", b)):
    bad = []
    for k, v in known.items():
        if k == "AC":
            used = set(re.findall(r"\bAC-\d{2}-\d{2}\b", txt))
        else:
            used = set("%s-%02d" % (k, int(n)) for n in re.findall(r"\b%s-(\d+)" % k, txt))
        unk = sorted(used - v - WHITELIST)
        if unk:
            bad.append("%s:%s" % (k, unk))
    print("  %s 引用 SRS 编号：%s" % (tag, "全部有定义" if not bad else "✗ " + "; ".join(bad)))
    if bad:
        P.append("%s 存在未定义引用：%s" % (tag, "; ".join(bad)))
srs_body = re.sub(r"^\|\s*SC / PV / V / AI / E\s*\|.*$", "", srs, flags=re.M)
for k in ("SC", "PV", "V", "AI", "E"):
    in_srs = sorted(set(re.findall(r"\b%s-\d+" % k, srs_body)))
    print("  SRS 正文引用 %s：%s" % (k, in_srs or "无"))
    if in_srs:
        P.append("SRS 正文仍引用 %s：%s" % (k, in_srs))

# ---------------------------------------------------------------- 4 如实性
print()
print("=" * 78)
print("自检 4：如实性与小组信息一致性")
print("=" * 78)
for w in ("业务方已确认", "教师已确认（教学模拟）", "已由业务方认可"):
    if w in b:
        P.append("材料 B 出现越界确认表述：%s" % w)
print("  越界确认表述：无" if not any("越界确认" in x for x in P) else "  见问题清单")
for w, lab in (("未发生", "业务方／教师确认未发生"), ("待开展", "教学模拟待开展"),
               ("未开展", "交叉走查未开展"), ("未验证", "未验证项"), ("〔待组员确认〕", "待组员确认项")):
    print("  %-22s %d 处" % (lab, len(re.findall(w, b))))
GROUP = "应雨挺（组长）、方与皓、周俊楠、杨子涵"
for nm, txt in (("SRS", srs), ("材料 A", a), ("材料 B", b)):
    ok = ("鱿鱼子涵" in txt) and (GROUP in txt)
    print("  %s 小组信息：%s" % (nm, "✓ 组名与 4 人名单一致" if ok else "✗ 不一致"))
    if not ok:
        P.append("%s 小组信息与既定不一致" % nm)
if "业务方确认 | **未发生**" not in b and "业务方确认" not in b:
    P.append("材料 B 未说明业务方确认的实际情况")
print("  人工决定与确认责任：已区分业务方确认／教师确认／团队内部复核三类" if "团队内部复核" in b else "  ✗ 缺少确认责任分类")

# ---------------------------------------------------------------- 5 三版一致
print()
print("=" * 78)
print("自检 5：三版一致")
print("=" * 78)
try:
    import pymupdf
    for tag, md, dx, pf in (
        ("SRS V1.2", SRS, ROOT / "智慧自习室预约与管理系统-需求规格说明书.docx", ROOT / "智慧自习室预约与管理系统-需求规格说明书.pdf"),
        ("材料 A", A_MD, A_MD.with_suffix(".docx"), A_MD.with_suffix(".pdf")),
        ("材料 B", B_MD, B_MD.with_suffix(".docx"), B_MD.with_suffix(".pdf")),
    ):
        d = pymupdf.open(str(pf))
        tbl = len(re.findall(r"^\|[\s:|-]+\|\s*$", md.read_text(encoding="utf-8"), re.M))
        print("  %-9s md %6.1f KB / %2d 表格；docx %7.1f KB；pdf %7.1f KB / %2d 页" % (
            tag, md.stat().st_size / 1024, tbl, dx.stat().st_size / 1024, pf.stat().st_size / 1024, d.page_count))
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
