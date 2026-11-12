# -*- coding: utf-8 -*-
"""ADR-06 与 Q-24 的可复现验证脚本（不改 v0.8 业务代码）。

用法：python evidence/verify_adr06_q24.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V08 = ROOT / "system" / "v0.8"
sys.path.insert(0, str(V08))

from app import ApiError, create_app, create_reservation  # noqa: E402
import db  # noqa: E402


def _config(database: str) -> dict:
    return {
        "TESTING": True,
        "DATABASE": database,
        "SECRET_KEY": "evidence-only",
        "ENABLE_SCHEDULER": False,
    }


def _count_params(database: str) -> int:
    conn = sqlite3.connect(database)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM rule_params").fetchone()[0])
    finally:
        conn.close()


def adr06() -> bool:
    print("=== ADR-06 缺参数补种验证 ===")
    tmp = Path(tempfile.mkdtemp(prefix="adr06_"))
    database = str(tmp / "old.db")

    create_app(_config(database))
    before = _count_params(database)
    conn = sqlite3.connect(database)
    try:
        conn.execute("DELETE FROM rule_params WHERE param_no='P-10'")
        conn.commit()
    finally:
        conn.close()
    missing_before = _count_params(database)
    print(f"初始参数数：{before}")
    print(f"删除 P-10 后参数数：{missing_before}")

    create_app(_config(database))
    after = _count_params(database)
    conn = sqlite3.connect(database)
    try:
        has_p10 = conn.execute(
            "SELECT COUNT(*) FROM rule_params WHERE param_no='P-10'"
        ).fetchone()[0]
    finally:
        conn.close()
    print(f"以旧库再次启动后参数数：{after}")
    print(f"P-10 是否补种：{'是' if has_p10 else '否'}")
    ok = after == before and bool(has_p10)
    print(f"ADR-06 结论：{'通过' if ok else '未通过（未补种）'}\n")
    return ok


def q24() -> bool:
    print("=== Q-24 两连接并发预约验证 ===")
    tmp = Path(tempfile.mkdtemp(prefix="q24_"))
    database = str(tmp / "q24.db")
    app = create_app(_config(database))

    with app.app_context():
        conn = db.get_db()
        seat = conn.execute("SELECT * FROM seats WHERE code='A-01'").fetchone()
        seat_id = int(seat["id"])
        conn.execute(
            """
            INSERT INTO users
                (student_no, name, department, contact, role, password_hash,
                 account_status, failed_login_count, created_at)
            VALUES ('246003385', '并发测试学生', '计算机学院', 'test@example.edu',
                    'student', 'x', '正常', 0, '2026-11-12 00:00:00')
            """
        )
        user_ids = [
            int(row["id"])
            for row in conn.execute(
                "SELECT id FROM users WHERE student_no IN ('246003384','246003385') ORDER BY id"
            ).fetchall()
        ]

    now = datetime.now()
    date_text = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    barrier = threading.Barrier(2)
    results: list[tuple[str, str]] = []
    lock = threading.Lock()

    def worker(user_id: int) -> None:
        with app.app_context():
            with app.test_request_context("/api/reservations", method="POST", json={}):
                user = db.get_db().execute(
                    "SELECT * FROM users WHERE id=?", (user_id,)
                ).fetchone()
                payload = {
                    "seat_id": seat_id,
                    "reservation_date": date_text,
                    "start_time": "09:00",
                    "end_time": "11:00",
                }
                barrier.wait()
                try:
                    reservation = create_reservation(user, payload)
                    with lock:
                        results.append(("成功", reservation["reservation_no"]))
                except ApiError as exc:
                    with lock:
                        results.append((f"失败 {exc.status} {exc.code}", exc.message))

    threads = [threading.Thread(target=worker, args=(uid,)) for uid in user_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with app.app_context():
        count = db.get_db().execute(
            "SELECT COUNT(*) AS n FROM reservations WHERE seat_id=? AND reservation_date=?",
            (seat_id, date_text),
        ).fetchone()["n"]
    print(f"预约日期：{date_text} 09:00—11:00；座位：A-01")
    for status, detail in results:
        print(f"- {status}：{detail}")
    print(f"该座位该时段预约单数：{count}")
    ok = count == 1 and sum(1 for status, _ in results if status == "成功") == 1
    print(f"Q-24 结论：{'通过（仅 1 条成功）' if ok else '未通过'}\n")
    return ok


if __name__ == "__main__":
    adr_ok = adr06()
    q24_ok = q24()
    print("汇总：ADR-06=%s；Q-24=%s" % ("通过" if adr_ok else "未通过", "通过" if q24_ok else "未通过"))
    sys.exit(0 if (adr_ok and q24_ok) else 1)
