"""AC-10-01—AC-10-05：黑名单自动生效、预约阻断、到期恢复、提前解除与信用展示。"""
from __future__ import annotations

import json

from conftest import make_booking
from sprint2_helpers import (
    get_seat_id,
    get_user_id,
    make_blacklist,
    make_checkin,
    make_reservation,
    set_user_count,
)


def _admin_login(client, login_as):
    response = login_as(client, "900000001", "admin123")
    assert response.status_code == 200


def test_ac_10_01_threshold_triggers_blacklist_and_notice(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    set_user_count(db_execute, user_id, 2)
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="08:00", end="10:00"
    )
    _admin_login(client, login_as)

    scan = client.post("/api/admin/scan").get_json()["scan"]
    assert scan["v1_created"] == 1
    user = db_query(
        "SELECT account_status, effective_violation_count, blacklist_until "
        "FROM users WHERE id=?",
        (user_id,),
    )[0]
    assert user["account_status"] == "黑名单"
    assert user["effective_violation_count"] == 3
    assert user["blacklist_until"] == "2026-10-23 08:30:00"
    assert db_query(
        "SELECT COUNT(*) AS n FROM blacklists WHERE user_id=? AND status='生效中'",
        (user_id,),
    )[0]["n"] == 1
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND title='黑名单生效通知'",
        (user_id,),
    )[0]["n"] == 1


def test_ac_10_02_blacklisted_student_cannot_create_reservation(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    make_blacklist(
        db_query, db_execute, user_id=user_id, expires_at="2026-10-20 08:30:00"
    )
    assert login_as(client).status_code == 200

    response = client.post(
        "/api/reservations",
        json=make_booking(seat_id, "2026-10-17", "09:00", "11:00"),
    )
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "BLACKLISTED"
    assert "剩余解除时间" in error["message"]
    assert db_query("SELECT COUNT(*) AS n FROM reservations")[0]["n"] == 0
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"


def test_ac_10_03_expired_blacklist_restored_by_scan(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    set_user_count(db_execute, user_id, 3)
    blacklist_id = make_blacklist(
        db_query, db_execute, user_id=user_id, expires_at="2026-10-16 08:00:00"
    )
    _admin_login(client, login_as)

    scan = client.post("/api/admin/scan").get_json()["scan"]
    assert scan["blacklists_expired"] == 1
    assert db_query(
        "SELECT status, release_reason FROM blacklists WHERE id=?", (blacklist_id,)
    )[0] == {"status": "已到期", "release_reason": "期限届满自动解除"}
    user = db_query(
        "SELECT account_status, blacklist_until FROM users WHERE id=?", (user_id,)
    )[0]
    assert user == {"account_status": "正常", "blacklist_until": None}
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND title='黑名单解除通知'",
        (user_id,),
    )[0]["n"] == 1
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='黑名单自动解除'"
    )[0]["n"] == 1


def test_ac_10_04_admin_release_requires_reason_and_audits(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    blacklist_id = make_blacklist(
        db_query, db_execute, user_id=user_id, expires_at="2026-10-20 08:30:00"
    )
    _admin_login(client, login_as)

    without_reason = client.post(f"/api/admin/blacklists/{blacklist_id}/release", json={})
    assert without_reason.status_code == 400
    assert without_reason.get_json()["error"]["code"] == "MISSING_FIELD"
    assert db_query(
        "SELECT status FROM blacklists WHERE id=?", (blacklist_id,)
    )[0]["status"] == "生效中"
    assert db_query(
        "SELECT account_status FROM users WHERE id=?", (user_id,)
    )[0]["account_status"] == "黑名单"

    released = client.post(
        f"/api/admin/blacklists/{blacklist_id}/release",
        json={"reason": "学生提交设备故障证明，经核实提前解除"},
    )
    assert released.status_code == 200
    body = released.get_json()["blacklist"]
    assert body["blacklist_status"] == "已解除"
    assert body["account_status"] == "正常"
    assert db_query(
        "SELECT account_status, blacklist_until FROM users WHERE id=?", (user_id,)
    )[0] == {"account_status": "正常", "blacklist_until": None}
    audit = db_query(
        """
        SELECT actor_name, actor_role, after_json FROM audit_logs
         WHERE action='提前解除黑名单' ORDER BY id DESC LIMIT 1
        """
    )[0]
    assert audit["actor_name"] == "自习室管理员"
    assert audit["actor_role"].startswith("自习室管理员")
    assert json.loads(audit["after_json"])["release_reason"] == "学生提交设备故障证明，经核实提前解除"


def test_ac_10_05_credit_status_shows_remaining_and_conditions(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    set_user_count(db_execute, user_id, 3)
    make_blacklist(
        db_query, db_execute, user_id=user_id, expires_at="2026-10-20 08:30:00"
    )
    assert login_as(client).status_code == 200

    response = client.get("/api/credit")
    assert response.status_code == 200
    credit = response.get_json()["credit"]
    assert credit["is_blacklisted"] is True
    assert credit["account_status"] == "黑名单"
    assert credit["effective_violation_count"] == 3
    assert credit["remaining_minutes"] == 5760
    assert credit["blacklist_until"] == "2026-10-20 08:30:00"
    assert credit["release_conditions"]
    assert credit["active_blacklist_record"]["id"] is not None

    page = client.get("/credit")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "剩余解除时间" in text
    assert "解除条件" in text
    assert "黑名单" in text
