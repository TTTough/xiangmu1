# -*- coding: utf-8 -*-
"""把 figures/*.mmd 渲染为 SVG 和 PNG。

链路：Mermaid.js 在 Edge 无头模式中渲染 -> dump-dom 取内联 SVG -> 再用 Edge 截图得到高倍 PNG。
不依赖 node/npm/mermaid-cli。
"""
import html
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

WORK = pathlib.Path(__file__).resolve().parent
ROOT = WORK.parent
FIG = ROOT / "figures"
MERMAID = WORK / "mermaid.min.js"

PAD = 16

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>t</title>
<style>
  html,body{{margin:0;background:#ffffff;}}
  body{{padding:{pad}px;font-family:"Microsoft YaHei","Segoe UI",sans-serif;}}
  .mermaid{{display:inline-block;font-family:"Microsoft YaHei","Segoe UI",sans-serif;}}
  .mermaid > svg{{display:block;}}
</style>
<script src="{mermaid}"></script>
</head><body>
<div class="mermaid">{code}</div>
<script>
  mermaid.initialize({{startOnLoad:true,theme:"default",securityLevel:"loose",
    fontFamily:'"Microsoft YaHei","Segoe UI",sans-serif',
    flowchart:{{htmlLabels:true,useMaxWidth:false,curve:"basis"}},
    sequence:{{useMaxWidth:false}},gantt:{{useMaxWidth:false}}}});
</script>
</body></html>
"""


def find_edge():
    for p in EDGE_CANDIDATES:
        if pathlib.Path(p).exists():
            return p
    raise SystemExit("找不到 Edge/Chrome 可执行文件")


def run_edge(edge, url, extra, profile):
    cmd = [edge, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           "--disable-extensions", "--user-data-dir=" + profile, "--virtual-time-budget=20000"]
    cmd += extra + [url]
    r = subprocess.run(cmd, capture_output=True, timeout=180)
    return r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def svg_of(dom):
    m = re.search(r"<svg[\s\S]*?</svg>", dom)
    return m.group(0) if m else None


SHOT = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html,body{{margin:0;background:#ffffff;}}
  body{{padding:{pad}px;font-family:"Microsoft YaHei","Segoe UI",sans-serif;}}
</style></head>
<body>{svg}</body></html>
"""


def svg_size(svg):
    vb = re.search(r'viewBox="([\d.\-eE]+)\s+([\d.\-eE]+)\s+([\d.\-eE]+)\s+([\d.\-eE]+)"', svg)
    if vb:
        return float(vb.group(3)), float(vb.group(4))
    w = re.search(r'width="([\d.]+)', svg)
    h = re.search(r'height="([\d.]+)', svg)
    if w and h:
        return float(w.group(1)), float(h.group(1))
    return 1200.0, 800.0


def resize_svg(svg, w, h):
    """把根 <svg> 标签定死为 w x h 像素并去掉响应式 max-width。

    只在根标签的属性上动手：根标签通常只有 width="100%"，若直接对全文做
    count=1 的 height 替换，会误改文档里第一个元素（例如第一个 <rect>）的高度。
    """
    m = re.match(r'<svg\b[^>]*>', svg)
    if not m:
        return svg
    tag = re.sub(r'max-width:\s*[^;"]*;?', '', m.group(0))
    if re.search(r'\swidth="', tag):
        tag = re.sub(r'\swidth="[^"]*"', ' width="%d"' % round(w), tag, count=1)
    else:
        tag = tag.replace("<svg", '<svg width="%d"' % round(w), 1)
    if re.search(r'\sheight="', tag):
        tag = re.sub(r'\sheight="[^"]*"', ' height="%d"' % round(h), tag, count=1)
    else:
        tag = tag.replace("<svg", '<svg height="%d"' % round(h), 1)
    return tag + svg[m.end():]


def render_one(edge, src_path, scale=2):
    code = src_path.read_text(encoding="utf-8")
    page = PAGE.format(mermaid=MERMAID.as_uri(), code=html.escape(code), pad=PAD)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mmd_"))
    try:
        page_file = tmp / "page.html"
        page_file.write_text(page, encoding="utf-8")
        profile = str(tmp / "prof")
        dom, err = run_edge(edge, page_file.as_uri(), ["--dump-dom"], profile)
        svg = svg_of(dom)
        if not svg:
            tail = (err or dom)[-1200:]
            return False, "未取到 SVG；输出尾部：\n" + tail

        w, h = svg_size(svg)

        svg_out = src_path.with_suffix(".svg")
        header = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<!-- 由 _work/render_mmd.py 从 %s 渲染生成 -->\n' % src_path.name)
        svg_out.write_text(header + resize_svg(svg, w, h), encoding="utf-8")

        # 截图：内联 SVG 按 scale 倍尺寸矢量渲染，避免 <img> 引入时隐藏测量元素显形
        sw, sh = int(round(w * scale)), int(round(h * scale))
        shot_file = tmp / "shot.html"
        shot_file.write_text(SHOT.format(pad=PAD, svg=resize_svg(svg, sw, sh)), encoding="utf-8")
        png_out = src_path.with_suffix(".png")
        if png_out.exists():
            png_out.unlink()
        run_edge(edge, shot_file.as_uri(),
                 ["--screenshot=" + str(png_out),
                  "--window-size=%d,%d" % (sw + PAD * 2, sh + PAD * 2)], profile)
        if not png_out.exists():
            return False, "svg 已生成，但截图失败"
        return True, "SVG %dx%d，PNG %dx%d" % (round(w), round(h), sw + PAD * 2, sh + PAD * 2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    FIG.mkdir(exist_ok=True)
    names = sys.argv[1:]
    targets = [FIG / n for n in names] if names else sorted(FIG.glob("*.mmd"))
    if not targets:
        raise SystemExit("figures/ 下没有 .mmd 文件")
    edge = find_edge()
    bad = 0
    for t in targets:
        if not t.exists():
            print("[缺失] %s" % t.name)
            bad += 1
            continue
        ok, msg = render_one(edge, t)
        print(("[成功] " if ok else "[失败] ") + t.name + "  " + msg)
        if not ok:
            bad += 1
    print("完成：%d/%d" % (len(targets) - bad, len(targets)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
