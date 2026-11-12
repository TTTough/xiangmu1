# -*- coding: utf-8 -*-
"""V1.1 交付自检：编号存在性、AC 闭合、权限矩阵闭合、附录闭合、图表一致、三版一致。"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MD = ROOT / "智慧自习室预约与管理系统-需求规格说明书.md"
DOCX = ROOT / "智慧自习室预约与管理系统-需求规格说明书.docx"
PDF = ROOT / "智慧自习室预约与管理系统-需求规格说明书.pdf"
FIG = ROOT / "figures"

text = MD.read_text(encoding="utf-8")
lines = text.split("\n")
problems = []

DEFS = {
    "G":   r"^\|\s*G-(\d+)\s*\|",
    "M":   r"^\|\s*M-(\d+)\s*\|",
    "SH":  r"^\|\s*SH-(\d+)\s*\|",
    "R":   r"^\|\s*R-(\d+)\s*\|",
    "FR":  r"^###\s+4\.\d+\s+FR-(\d+)",
    "US":  r"^\|\s*US-(\d+)\s*\|",
    "UC":  r"^\|\s*UC-(\d+)\s*\|",
    "BR":  r"^\|\s*BR-(\d+)\s*\|",
    "ST":  r"^\|\s*ST-(\d+)\s*\|",
    "DM":  r"^\|\s*DM-(\d+)\s*\|",
    "NFR": r"^\|\s*NFR-(\d+)\s*\|",
    "EX":  r"^\|\s*EX-(\d+)\s*\|",
    "P":   r"^\|\s*P-(\d+)\s*\|",
    "Q":   r"^\|\s*Q-(\d+)\s*\|",
    "SM":  r"^###\s+7\.\d+\s+SM-(\d+)",
}

print("=" * 78)
print("自检 1：编号存在性（全文出现的编号必须都有定义位置）")
print("=" * 78)
defined = {}
for key, pat in DEFS.items():
    rx = re.compile(pat, re.M)
    ns = sorted(set(int(m.group(1)) for m in rx.finditer(text)))
    defined[key] = ns
    expect = list(range(1, max(ns) + 1)) if ns else []
    gaps = [n for n in expect if n not in ns]
    dup = [n for n in set(ns) if ns.count(n) > 1]
    status = "连续" if not gaps else "缺 %s" % gaps
    if dup:
        status += "；重复 %s" % dup
    if gaps or dup:
        problems.append("%s 定义不完整：%s" % (key, status))
    print("  %-4s 定义 %2d 个，范围 1—%d，%s" % (key, len(ns), max(ns) if ns else 0, status))

# AC 单独处理（两级编号）
ac_defs = sorted(set("AC-%s-%s" % (a, b) for a, b in
                    re.findall(r"^\|\s*AC-(\d+)-(\d+)\s*\|", text, re.M)))
print("  AC   定义 %2d 条，编号 %s … %s" % (len(ac_defs), ac_defs[0], ac_defs[-1]))

print()
print("  -- 引用闭环（全文引用是否有定义）--")
for key in ("G", "M", "SH", "R", "FR", "US", "UC", "BR", "ST", "DM", "NFR", "EX", "P", "Q", "SM"):
    used = set(int(x) for x in re.findall(r"\b%s-(\d+)" % key, text))
    unknown = sorted(used - set(defined[key]))
    if unknown:
        problems.append("%s 存在未定义引用：%s" % (key, unknown))
        print("  %-4s ✗ 未定义引用：%s" % (key, unknown))
    else:
        print("  %-4s ✓ 闭环（被引用 %d 个）" % (key, len(used)))

ac_used = set(re.findall(r"\bAC-\d{2}-\d{2}\b", text))
ac_unknown = sorted(ac_used - set(ac_defs))
if ac_unknown:
    problems.append("AC 存在未定义引用：%s" % ac_unknown)
    print("  AC   ✗ 未定义引用：%s" % ac_unknown)
else:
    print("  AC   ✓ 闭环（被引用 %d 条）" % len(ac_used))

print()
print("=" * 78)
print("自检 2：ST 引用明细（供逐条语义核对）")
print("=" * 78)
st_def = {}
for ln in lines:
    m = re.match(r"^\|\s*(ST-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", ln)
    if m:
        st_def[m.group(1)] = (m.group(2), m.group(3))
st_refs = []
for i, ln in enumerate(lines, 1):
    if re.match(r"^\|\s*ST-\d+\s*\|", ln):
        continue
    hits = re.findall(r"\bST-\d+\b", ln)
    if hits:
        st_refs.append((i, hits, ln.strip()[:110]))
print("  ST 定义 %d 条；出现 ST 引用的非定义行 %d 行。" % (len(st_def), len(st_refs)))
print("  ST 定义一览（编号｜当前状态｜触发事件）：")
for k in sorted(st_def, key=lambda x: int(x[3:])):
    print("    %-6s %s｜%s" % (k, st_def[k][0], st_def[k][1]))

print()
print("=" * 78)
print("自检 3：AC 闭合（FR 的验收标准列 vs 第 13 章 AC 定义）")
print("=" * 78)
# FR 表的验收标准列
fr_ac = {}
for m in re.finditer(r"^###\s+4\.\d+\s+FR-(\d+)([\s\S]*?)(?=^###\s+4\.\d+|^---)", text, re.M):
    frn = int(m.group(1))
    body = m.group(2)
    mm = re.search(r"\|\s*验收标准\s*\|\s*([^|]+)\|", body)
    if mm:
        fr_ac[frn] = mm.group(1).strip()
# 第 13 章的 AC 定义（按 FR 分组）
ac_by_fr = {}
for a in ac_defs:
    grp = int(a.split("-")[1])
    ac_by_fr.setdefault(grp, []).append(a)
ok = True
for frn in sorted(fr_ac):
    listed = fr_ac[frn]
    nums = set(re.findall(r"AC-\d{2}-\d{2}", listed))
    rng = re.findall(r"AC-(\d+)-(\d+)\s*至\s*AC-(\d+)-(\d+)", listed)
    if rng:
        g, s, _, e = (int(x) for x in rng[0])
        nums |= {"AC-%02d-%02d" % (g, k) for k in range(s, e + 1)}
    actual = set(ac_by_fr.get(frn, []))
    miss = sorted(actual - nums)
    extra = sorted(nums - actual)
    flag = "✓" if not miss and not extra else "✗"
    if miss or extra:
        ok = False
        problems.append("FR-%02d 验收标准列与第 13 章不一致：缺 %s；多 %s" % (frn, miss, extra))
    print("  %s FR-%02d：列示 %-26s 定义 %d 条 %s" % (
        flag, frn, listed, len(actual),
        "" if not (miss or extra) else "缺%s 多%s" % (miss, extra)))
# FR 与 AC 分组是否一致
for grp, acs in sorted(ac_by_fr.items()):
    if grp != 1 and grp > 14:
        problems.append("AC-%02d-* 分组越界" % grp)
print("  说明：AC 编号首段对应 FR 序号，除 FR-01 外各 FR 的 AC 均由第 13 章对应分节定义。")

print()
print("=" * 78)
print("自检 4：权限矩阵闭合（每行的关联需求是否有效，写操作是否都有 FR 归属）")
print("=" * 78)
perm_block = re.search(r"## 10 权限矩阵([\s\S]*?)\*\*矩阵说明\*\*", text)
perm_rows = re.findall(
    r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$",
    perm_block.group(1), re.M)
print("  矩阵共 %d 行：" % len(perm_rows))
fr_covered = set()
for r in perm_rows:
    need = r[6].strip()
    frs = re.findall(r"FR-\d+", need)
    for f in frs:
        fr_covered.add(int(f[3:]))
    if not frs and not need:
        problems.append("权限矩阵第 %s 行缺少关联需求" % r[0])
    print("    %-3s %-24s %s" % (r[0], r[1].strip()[:24], need))
all_fr = set(defined["FR"])
write_fr = {1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14}   # 含写入类操作的 FR
uncovered = sorted(all_fr - fr_covered)
print("  未被矩阵覆盖的 FR：%s（查询类 FR 若无写操作属正常）" % (uncovered or "无"))
if uncovered:
    problems.append("权限矩阵未覆盖 FR：%s" % uncovered)

print()
print("=" * 78)
print("自检 5：附录闭合（附录 A 的对应问题 ↔ 附录 B 的影响规则）")
print("=" * 78)
apx_a = {m[0]: m[1:] for m in re.findall(
    r"^\|\s*(P-\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", text, re.M)}
apx_b = {m[0]: m[1:] for m in re.findall(
    r"^\|\s*(Q-\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", text, re.M)}
print("  附录 A 收录 %d 个参数；附录 B 收录 %d 个问题。" % (len(apx_a), len(apx_b)))
a_to_q, b_to_p = {}, {}
for p, v in apx_a.items():
    q = v[6].strip()
    if q in ("—", ""):
        continue
    if q not in apx_b:
        problems.append("%s 的对应问题 %s 未在附录 B 定义" % (p, q))
    a_to_q.setdefault(q, []).append(p)
    print("    %-5s → %-5s  (%s)" % (p, q, v[0].strip()))
for q, v in apx_b.items():
    refs = re.findall(r"P-\d+", v[1])
    for p in refs:
        if p not in apx_a:
            problems.append("%s 引用了不存在的 %s" % (q, p))
        b_to_p.setdefault(p, []).append(q)
no_q = sorted(p for p, v in apx_a.items() if v[6].strip() in ("—", ""))
print("  无对应问题的参数：%s" % (no_q or "无（P-14 的「—」表示已确认，不属待确认）"))
# 正文数值是否都进了附录 A
nfr_vals = re.findall(r"^\|\s*(NFR-\d+)\s*\|\s*([^|]*)\|[^|]*\|([^|]*)\|", text, re.M)
for nid, attr, req in nfr_vals:
    has_num = re.search(r"\d", req)
    cited = nid in " ".join(v[2] for v in apx_a.values())
    if has_num and not cited:
        problems.append("%s 含具体数值但未收录进附录 A" % nid)
print("  NFR 数值收录检查：%d 条含数值的 NFR 已核对。" % len(nfr_vals))

print()
print("=" * 78)
print("自检 6：图表一致（md 中的 FIG 标记 vs figures/ 文件）")
print("=" * 78)
figs = re.findall(r"<!--\s*FIG:([^\s>]+?)\s*-->", text)
files = sorted(p.stem for p in FIG.glob("*.mmd"))
print("  md 引用图 %d 张；figures 目录 .mmd %d 个。" % (len(figs), len(files)))
miss_f = [f for f in figs if f not in files]
miss_m = [f for f in files if f not in figs]
if miss_f:
    problems.append("md 引用了不存在的图源：%s" % miss_f)
if miss_m:
    problems.append("figures 存在未被 md 引用的图源：%s" % miss_m)
for f in figs:
    trio = [(FIG / (f + ext)).exists() for ext in (".mmd", ".svg", ".png")]
    if not all(trio):
        problems.append("图 %s 缺少 mmd/svg/png 中的部分文件" % f)
print("  md 引用：%s" % "、".join(figs))
print("  三件套齐全：%s" % ("是" if all(all((FIG / (f + e)).exists() for e in (".mmd", ".svg", ".png")) for f in figs) else "否"))

print()
print("=" * 78)
print("自检 7：三版一致（md / docx / pdf）")
print("=" * 78)
import pymupdf
d = pymupdf.open(str(PDF))
print("  md      %8.1f KB，%d 行，标题 %d 个，表格 %d 个" % (
    MD.stat().st_size / 1024, len(lines), len(re.findall(r"^#", text, re.M)),
    len(re.findall(r"^\|[\s:|-]+\|\s*$", text, re.M))))
print("  docx    %8.1f KB，插图 %d 张" % (
    DOCX.stat().st_size / 1024, len(figs)))
print("  pdf     %8.1f KB，%d 页" % (PDF.stat().st_size / 1024, d.page_count))
# PDF 中图注核对：以图编号为准（文档图注名称与文件名用词可能不同，编号必须一致）
missing_cap, name_mismatch = [], []
for f in figs:
    m = re.match(r"^([A-Z]+-\d+)-(.+)$", f)
    code = m.group(1)
    if not any(d[i].search_for("图 " + code) for i in range(d.page_count)):
        missing_cap.append(code)
    # 图清单中的图名称应与正文图注一致
    mm = re.search(r"^\|\s*%s\s*\|\s*([^|]+?)\s*\|" % re.escape(code), text, re.M)
    if not mm:
        name_mismatch.append("%s 未出现在图清单" % code)
        continue
    listed = mm.group(1).strip()
    if not re.search(r"图\s*%s\s*%s" % (re.escape(code), re.escape(listed)), text):
        name_mismatch.append("%s 图清单名称「%s」与正文图注不一致" % (code, listed))
if missing_cap:
    problems.append("PDF 中未找到图编号：%s" % missing_cap)
if name_mismatch:
    problems.append("图清单与图注名称不一致：%s" % name_mismatch)
print("  PDF 图注核对：13 个图编号%s。" % ("全部可在 PDF 中检索到" if not missing_cap else "缺失 " + str(missing_cap)))
print("  图清单与图注名称一致性：%s。" % ("一致" if not name_mismatch else name_mismatch))
pg_marker = [i + 1 for i in range(d.page_count) if d[i].search_for("文档修订记录")]
print("  PDF 结构核对：修订记录位于第 %s 页；目录位于第 %s 页。" % (
    pg_marker or "?",
    [i + 1 for i in range(d.page_count) if d[i].search_for("图清单")] or "?"))

print()
print("=" * 78)
if problems:
    print("发现 %d 项问题：" % len(problems))
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print("全部自检通过。")
