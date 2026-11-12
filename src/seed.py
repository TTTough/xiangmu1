"""演示数据初始化：1 个自习室、3 个区域、10 个座位、学生/管理员各 1 个账号。

演示开放时间 08:00—22:00 沿用现有原型的演示数据；SRS 未规定具体场馆开放时间，
已在 docs/open-questions.md 记录，不视为业务规则。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from werkzeug.security import generate_password_hash

import db
from config import RULE_PARAM_DEFAULTS

STUDENT_ACCOUNT = {
    "student_no": "246003384",
    "password": "student123",
    "name": "杨子涵",
    "department": "计算机学院",
    "contact": "student@example.edu",
}
ADMIN_ACCOUNT = {
    "student_no": "900000001",
    "password": "admin123",
    "name": "自习室管理员",
    "department": "图书馆",
    "contact": "admin@example.edu",
}
SYSADMIN_ACCOUNT = {
    "student_no": "900000002",
    "password": "sysadmin123",
    "name": "系统管理员",
    "department": "信息化中心",
    "contact": "sysadmin@example.edu",
}
LOGISTICS_ACCOUNT = {
    "student_no": "900000003",
    "password": "logistics123",
    "name": "后勤管理员",
    "department": "后勤保障处",
    "contact": "logistics@example.edu",
}


def _iso_now(now: datetime | None = None) -> str:
    return (now or datetime.now()).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


@lru_cache(maxsize=4)
def _demo_password_hash(password: str) -> str:
    """演示账号密码哈希缓存，避免每个测试临时库重复进行昂贵哈希。"""
    return generate_password_hash(password, method="pbkdf2:sha256")



def _seed_missing_rule_params(conn: sqlite3.Connection, created_at: str) -> int:
    """逐项补种缺失的规则参数；已有 param_key 一律不覆盖。返回补种数量。"""
    inserted = 0
    with db.immediate_transaction(conn):
        for item in RULE_PARAM_DEFAULTS:
            exists = conn.execute(
                "SELECT 1 FROM rule_params WHERE param_key=?", (item["param_key"],)
            ).fetchone()
            if exists is not None:
                continue
            conn.execute(
                """
                INSERT INTO rule_params
                    (param_no, param_key, name, value, default_value, value_type,
                     min_value, max_value, unit, range_text, description, source_nature,
                     confirmation_status, suggested_confirmer, related_rule,
                     related_question, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["param_no"],
                    item["param_key"],
                    item["name"],
                    item["value"],
                    item["default_value"],
                    item["value_type"],
                    item["min_value"],
                    item["max_value"],
                    item["unit"],
                    item["range_text"],
                    item["description"],
                    item["source_nature"],
                    item["confirmation_status"],
                    item["suggested_confirmer"],
                    item["related_rule"],
                    item["related_question"],
                    created_at,
                ),
            )
            inserted += 1
    return inserted


def seed_database(conn: sqlite3.Connection | None = None, now: datetime | None = None) -> bool:
    """幂等写入演示数据；已有用户时不再覆盖。返回是否实际写入。"""
    own_connection = conn is None
    if own_connection:
        from flask import current_app

        conn = db.connect_database(current_app.config["DATABASE"])

    try:
        existing = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if existing:
            # 旧库：只补缺失参数，不覆盖已有值，也不重写用户/资源数据。
            return _seed_missing_rule_params(conn, _iso_now(now)) > 0

        created_at = _iso_now(now)
        with db.immediate_transaction(conn):
            teacher_hash = _demo_password_hash(ADMIN_ACCOUNT["password"])
            student_hash = _demo_password_hash(STUDENT_ACCOUNT["password"])
            sysadmin_hash = _demo_password_hash(SYSADMIN_ACCOUNT["password"])
            logistics_hash = _demo_password_hash(LOGISTICS_ACCOUNT["password"])
            conn.execute(
                """
                INSERT INTO users
                    (student_no, name, department, contact, role, password_hash,
                     account_status, failed_login_count, created_at)
                VALUES (?, ?, ?, ?, 'student', ?, '正常', 0, ?)
                """,
                (
                    STUDENT_ACCOUNT["student_no"],
                    STUDENT_ACCOUNT["name"],
                    STUDENT_ACCOUNT["department"],
                    STUDENT_ACCOUNT["contact"],
                    student_hash,
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO users
                    (student_no, name, department, contact, role, password_hash,
                     account_status, failed_login_count, created_at)
                VALUES (?, ?, ?, ?, 'admin', ?, '正常', 0, ?)
                """,
                (
                    ADMIN_ACCOUNT["student_no"],
                    ADMIN_ACCOUNT["name"],
                    ADMIN_ACCOUNT["department"],
                    ADMIN_ACCOUNT["contact"],
                    teacher_hash,
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO users
                    (student_no, name, department, contact, role, password_hash,
                     account_status, failed_login_count, created_at)
                VALUES (?, ?, ?, ?, 'sysadmin', ?, '正常', 0, ?)
                """,
                (
                    SYSADMIN_ACCOUNT["student_no"],
                    SYSADMIN_ACCOUNT["name"],
                    SYSADMIN_ACCOUNT["department"],
                    SYSADMIN_ACCOUNT["contact"],
                    sysadmin_hash,
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO users
                    (student_no, name, department, contact, role, password_hash,
                     account_status, failed_login_count, created_at)
                VALUES (?, ?, ?, ?, 'logistics', ?, '正常', 0, ?)
                """,
                (
                    LOGISTICS_ACCOUNT["student_no"],
                    LOGISTICS_ACCOUNT["name"],
                    LOGISTICS_ACCOUNT["department"],
                    LOGISTICS_ACCOUNT["contact"],
                    logistics_hash,
                    created_at,
                ),
            )

            conn.execute(
                """
                INSERT INTO rooms
                    (code, name, building, floor, location, open_from, open_to,
                     status, note, created_at)
                VALUES ('R-LIB-3F', '图书馆三层自习室', '图书馆', '3 层',
                        '图书馆三层东侧', '08:00', '22:00', '开放',
                        '演示数据；开放时间来自原型，非 SRS 业务规则', ?)
                """,
                (created_at,),
            )
            room_id = conn.execute("SELECT id FROM rooms WHERE code='R-LIB-3F'").fetchone()["id"]
            admin_id = conn.execute(
                "SELECT id FROM users WHERE student_no=?", (ADMIN_ACCOUNT["student_no"],)
            ).fetchone()["id"]
            conn.execute(
                """
                INSERT INTO admin_room_assignments (admin_user_id, room_id, created_at)
                VALUES (?, ?, ?)
                """,
                (admin_id, room_id, created_at),
            )

            zone_rows = [
                ("Z1", "静音区", "静音区", 1),
                ("Z2", "讨论区", "讨论区", 2),
                ("Z3", "电源区", "电源区", 3),
            ]
            zone_ids: dict[str, int] = {}
            for code, name, zone_type, sort_order in zone_rows:
                cur = conn.execute(
                    """
                    INSERT INTO zones (room_id, code, name, zone_type, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (room_id, code, name, zone_type, sort_order),
                )
                zone_ids[code] = int(cur.lastrowid)

            seat_rows = [
                ("A-01", "Z1", "带电源", "空闲", "靠门第 1 排", 1),
                ("A-02", "Z1", "普通", "空闲", "靠门第 2 排", 1),
                ("A-03", "Z1", "普通", "空闲", "靠窗第 3 排", 1),
                ("A-04", "Z1", "靠窗", "空闲", "靠窗第 4 排", 1),
                ("B-01", "Z2", "普通", "空闲", "讨论区第 1 桌", 1),
                ("B-02", "Z2", "普通", "空闲", "讨论区第 2 桌", 1),
                ("B-03", "Z2", "带电源", "空闲", "讨论区第 3 桌", 1),
                ("C-01", "Z3", "带电源", "空闲", "电源区第 1 排", 1),
                ("C-02", "Z3", "带电源", "空闲", "电源区第 2 排", 1),
                ("C-03", "Z3", "普通", "停用", "电源区角落", 0),
            ]
            for code, zone_code, seat_type, status, position, is_bookable in seat_rows:
                conn.execute(
                    """
                    INSERT INTO seats
                        (code, room_id, zone_id, seat_type, status, position,
                         is_bookable, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        room_id,
                        zone_ids[zone_code],
                        seat_type,
                        status,
                        position,
                        is_bookable,
                        created_at,
                    ),
                )

            for item in RULE_PARAM_DEFAULTS:
                conn.execute(
                    """
                    INSERT INTO rule_params
                        (param_no, param_key, name, value, default_value, value_type,
                         min_value, max_value, unit, range_text, description, source_nature,
                         confirmation_status, suggested_confirmer, related_rule,
                         related_question, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["param_no"],
                        item["param_key"],
                        item["name"],
                        item["value"],
                        item["default_value"],
                        item["value_type"],
                        item["min_value"],
                        item["max_value"],
                        item["unit"],
                        item["range_text"],
                        item["description"],
                        item["source_nature"],
                        item["confirmation_status"],
                        item["suggested_confirmer"],
                        item["related_rule"],
                        item["related_question"],
                        created_at,
                    ),
                )
        # 全新库已写入全部参数；这里仅作兜底，确保没有遗漏。
        _seed_missing_rule_params(conn, created_at)
        return True
    finally:
        if own_connection:
            conn.close()


if __name__ == "__main__":
    database = Path(__file__).resolve().parent / "data" / "app.db"
    db.init_db(str(database))
    conn = db.connect_database(str(database))
    inserted = seed_database(conn)
    conn.close()
    print(f"数据库：{database}")
    print("演示数据已写入。" if inserted else "已有数据，未重复写入。")
    print(f"学生：{STUDENT_ACCOUNT['student_no']} / {STUDENT_ACCOUNT['password']}")
    print(f"管理员：{ADMIN_ACCOUNT['student_no']} / {ADMIN_ACCOUNT['password']}")
