# -*- coding: utf-8 -*-
"""按场景批量截取原型页面，生成 PV-01—PV-20 的走查证据图。

用法：python shoot_prototype.py [PV 编号...]     不带参数则全部重截。
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
WORK = pathlib.Path(__file__).resolve().parent
ROOT = WORK.parent
PAGE = ROOT / "prototype" / "index.html"
SHOTS = ROOT / "prototype" / "shots"

# PV 编号 → (文件名后缀, URL 查询串)
SCENES = [
    ("PV-01", "座位查询-四态与脱敏", "view=student&tab=seat&seed=1"),
    ("PV-02", "预约成功-ST-01", "view=student&tab=seat&seed=1&do=reserve"),
    ("PV-03", "超出预约上限被拒-BR-04", "view=student&tab=seat&seed=7&do=reserve"),
    ("PV-04", "黑名单拒绝预约-BR-13", "view=student&tab=seat&seed=14&do=reserve"),
    ("PV-05", "窗口内签到成功-ST-03", "view=student&tab=ci&seed=8&do=checkin"),
    ("PV-06", "超窗签到被拒-ST-16", "view=student&tab=ci&seed=9&do=checkin"),
    ("PV-07", "签退成功-ST-06", "view=student&tab=my&seed=10&do=checkout"),
    ("PV-08", "管理员实时座位视图", "view=admin&seed=1"),
    ("PV-09", "手动违约未填原因被拒-BR-22", "view=admin&seed=11&sel=A-02&reason=&do=violate"),
    ("PV-10", "手动违约登记成功-ST-31", "view=admin&seed=12&sel=A-01&reason=%E6%9C%AA%E9%A2%84%E7%BA%A6%E5%8D%A0%E7%94%A8%E5%BA%A7%E4%BD%8D&do=violate"),
    ("PV-11", "取消预约超时被拒-ST-12", "view=student&tab=my&seed=13&do=cancel"),
    ("PV-12", "提前释放座位-ST-13", "view=admin&seed=12&sel=A-01&reason=%E9%97%AD%E9%A6%86%E6%B8%85%E5%9C%BA&do=release"),
    ("PV-13", "连续登录失败达阈值锁定-ST-32", "view=student&tab=login&seed=2&do=login-fail"),
    ("PV-14", "锁定期间登录被拒-ST-34", "view=student&tab=login&seed=3&do=login-ok"),
    ("PV-15", "锁定期满自动恢复-ST-33", "view=student&tab=login&seed=3&do=lock-expire"),
    ("PV-16", "发起违约申诉-ST-35", "view=student&tab=appeal&seed=4&apReason=%E7%AD%BE%E5%88%B0%E8%AE%BE%E5%A4%87%E6%95%85%E9%9A%9C&do=appeal"),
    ("PV-17", "申诉成立并回退计数-ST-36", "view=admin&seed=5&do=judge-ok"),
    ("PV-18", "申诉不成立-ST-37", "view=admin&seed=5&do=judge-no"),
]


def shoot(tag, desc, query):
    out = SHOTS / ("%s-%s.png" % (tag, desc))
    if out.exists():
        out.unlink()
    tmp = tempfile.mkdtemp(prefix="shot_")
    try:
        cmd = [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
               "--disable-extensions", "--user-data-dir=" + tmp,
               "--virtual-time-budget=12000",
               "--window-size=1280,1080",
               "--screenshot=" + str(out),
               PAGE.as_uri() + "?" + query]
        subprocess.run(cmd, capture_output=True, timeout=180)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not out.exists():
        return False
    return True


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    want = set(sys.argv[1:])
    ok = bad = 0
    for tag, desc, query in SCENES:
        if want and tag not in want:
            continue
        if shoot(tag, desc, query):
            print("[成功] %s-%s.png" % (tag, desc))
            ok += 1
        else:
            print("[失败] %s-%s.png" % (tag, desc))
            bad += 1
    print("截图完成：%d 张成功，%d 张失败" % (ok, bad))


if __name__ == "__main__":
    main()
