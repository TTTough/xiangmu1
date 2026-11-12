# -*- coding: utf-8 -*-
"""把任意 Markdown 转成 docx，复用 gen_srs.py 的排版逻辑。

用法：python gen_docx_any.py <输入.md> [输出.docx]
"""
import importlib.util
import pathlib
import sys

WORK = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("gs", WORK / "gen_srs.py")
gs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gs)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = pathlib.Path(sys.argv[1]).resolve()
    dst = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.with_suffix(".docx")
    if not src.exists():
        raise SystemExit("找不到 %s" % src)
    doc = gs.new_document()
    stats = {"tables": 0, "figures": []}
    gs.convert(src.read_text(encoding="utf-8"), doc, stats)
    doc.save(str(dst))
    print("[DOCX] %s  (%.1f KB，表格 %d 个，插图 %d 张)"
          % (dst.name, dst.stat().st_size / 1024, stats["tables"], len(stats["figures"])))


if __name__ == "__main__":
    main()
