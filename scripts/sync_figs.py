# -*- coding: utf-8 -*-
"""从需求规格说明书的 Markdown 中抽取 Mermaid 源码到 figures/*.mmd。

约定：正文里每张图前有 `<!-- FIG:图编号-图名称 -->` 标记，紧随其后是一个 mermaid 代码块。
"""
import pathlib
import re
import sys

WORK = pathlib.Path(__file__).resolve().parent
ROOT = WORK.parent
FIG = ROOT / "figures"

FIG_RE = re.compile(r"<!--\s*FIG:([^\s>]+?)\s*-->\s*```mermaid\r?\n([\s\S]*?)```")


def main():
    md = ROOT / "智慧自习室预约与管理系统-需求规格说明书.md"
    text = md.read_text(encoding="utf-8")
    FIG.mkdir(exist_ok=True)

    found = FIG_RE.findall(text)
    if not found:
        raise SystemExit("未在 %s 中找到任何 FIG 标记" % md.name)

    names = []
    for name, code in found:
        code = code.strip() + "\n"
        path = FIG / (name + ".mmd")
        old = path.read_text(encoding="utf-8") if path.exists() else None
        path.write_text(code, encoding="utf-8")
        state = "更新" if old is not None and old != code else ("已存在" if old is not None else "新增")
        print("[%s] %s.mmd  (%d 行)" % (state, name, code.count("\n")))
        names.append(name)

    # 清理正文已删除、但 figures/ 还残留的 mmd
    orphans = [p for p in FIG.glob("*.mmd") if p.stem not in names]
    for p in orphans:
        print("[孤儿] %s.mmd（正文中已无对应图，未自动删除）" % p.stem)
    print("共 %d 张图" % len(names))


if __name__ == "__main__":
    main()
