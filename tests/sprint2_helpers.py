"""Sprint 2 测试数据构造辅助（直接落库，聚焦端点行为）。"""
from __future__ import annotations

import uuid


def one(db_query, sql, params=()):
    rows = db_query(sql, params)
    assert rows, f"查询无结果：{sql}"
    return rows[0]


def get_user_id(db_query, student_no="246003384"):
    return one(db_query, "SELECT id FROM users WHERE student_no=?", (student_no,))["id"]


def get_seat_id(db_query, code="A-01"):
    return one(db_query, "SELECT id FROM seats WHERE code=?", (code,))["id"]


def make_reservation(
    db_query,
    db_execute,
    *,
    user_id,
    seat_id,
    status="待签到",
    reservation_date="2026-10-16",
    start="08:00",
    end="10:00",
):
    seat = one(
        db_query,
        "SELECT id, room_id, zone_id, code FROM seats WHERE id=?",
        (seat_id,),
    )
    reservation_no = "T-" + uuid.uuid4().hex[:12].upper()
    reservation_id = db_execute(
        """
        INSERT INTO reservations
            (reservation_no, user_id, seat_id, room_id, zone_id,
             reservation_date, start_time, end_time, status, source, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '学生自助', ?, '2026-10-16 08:00:00')
        """,
        (
            reservation_no,
            user_id,
            seat_id,
            seat["room_id"],
            seat["zone_id"],
            reservation_date,
            start,
            end,
            status,
            user_id,
        ),
    )
    seat_status = "使用中" if status == "使用中" else "已预约"
    db_execute("UPDATE seats SET status=? WHERE id=?", (seat_status, seat_id))
    return int(reservation_id)


def make_checkin(db_execute, reservation_id, checkin_at="2026-10-16 08:10:00", method="二维码"):
    return int(
        db_execute(
            """
            INSERT INTO checkins (reservation_id, checkin_at, method)
            VALUES (?, ?, ?)
            """,
            (reservation_id, checkin_at, method),
        )
    )


def make_violation(
    db_query,
    db_execute,
    *,
    user_id,
    seat_id,
    status="生效中",
    violation_type="V1 未签到",
    created_at="2026-10-16 08:30:00",
    reservation_id=None,
    appeal_reason=None,
    appeal_at=None,
    appeal_conclusion=None,
):
    violation_no = "TV-" + uuid.uuid4().hex[:10].upper()
    violation_id = db_execute(
        """
        INSERT INTO violations
            (violation_no, user_id, reservation_id, seat_id, violation_type,
             occurred_at, basis, result, status, appeal_reason, appeal_at,
             appeal_conclusion, created_at)
        VALUES (?, ?, ?, ?, ?, ?, '测试构造', '已记违约', ?, ?, ?, ?, ?)
        """,
        (
            violation_no,
            user_id,
            reservation_id,
            seat_id,
            violation_type,
            created_at,
            status,
            appeal_reason,
            appeal_at,
            appeal_conclusion,
            created_at,
        ),
    )
    return int(violation_id)


def set_user_count(db_execute, user_id, count):
    db_execute("UPDATE users SET effective_violation_count=? WHERE id=?", (count, user_id))


def make_blacklist(
    db_query,
    db_execute,
    *,
    user_id,
    expires_at="2026-10-20 08:30:00",
    status="生效中",
    reason="累计违约达阈值",
    source="自动",
):
    blacklist_id = db_execute(
        """
        INSERT INTO blacklists
            (user_id, reason, source, effective_at, expires_at, status, created_at)
        VALUES (?, ?, ?, '2026-10-13 08:30:00', ?, ?, '2026-10-13 08:30:00')
        """,
        (user_id, reason, source, expires_at, status),
    )
    if status == "生效中":
        db_execute(
            """
            UPDATE users SET account_status='黑名单', blacklist_until=?
             WHERE id=?
            """,
            (expires_at, user_id),
        )
    return int(blacklist_id)
