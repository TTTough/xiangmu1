"""AC-01-01—AC-01-04：登录、角色入口、越权拒绝、账号锁定。"""
from __future__ import annotations

from conftest import make_booking


def test_ac_01_01_student_login_enters_student_workspace(client, login_as):
    response = login_as(client)
    assert response.status_code == 200
    body = response.get_json()
    assert body["user"]["role"] == "student"
    assert body["user"]["account_status"] == "正常"

    page = client.get("/student")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "学生工作台" in text
    assert "data-admin-menu" not in text
    assert ">/admin<" not in text

    me = client.get("/api/me").get_json()
    assert me["user"]["student_no"] == "246003384"
    assert me["user"]["role"] == "student"


def test_ac_01_02_admin_login_shows_management_entries(client, login_as):
    response = login_as(client, "900000001", "admin123")
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == "admin"

    page = client.get("/admin")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    for menu_name in ("座位资源维护", "实时座位视图", "投诉处理", "黑名单管理"):
        assert menu_name in text
    assert "data-admin-menu" in text


def test_ac_01_03_student_admin_request_rejected_without_changes(
    client, login_as, db_query
):
    login_as(client)
    before_counts = {
        table: db_query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        for table in ("reservations", "violations", "audit_logs", "seats")
    }
    before_seat = db_query("SELECT status FROM seats WHERE code='A-01'")[0]["status"]

    response = client.post(
        "/api/admin/manual-violation",
        json={"seat_id": 1, "reason": "越权尝试"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "FORBIDDEN"

    page = client.get("/admin")
    assert page.status_code == 403
    assert "越权" in page.get_data(as_text=True)

    after_counts = {
        table: db_query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        for table in ("reservations", "violations", "audit_logs", "seats")
    }
    assert after_counts == before_counts
    assert db_query("SELECT status FROM seats WHERE code='A-01'")[0]["status"] == before_seat


def test_ac_01_04_login_lock_expiry_and_existing_reservation(
    client, login_as, db_query, clock, app
):
    assert login_as(client).status_code == 200
    seat_id = db_query("SELECT id FROM seats WHERE code='A-01'")[0]["id"]
    booking = client.post(
        "/api/reservations",
        json=make_booking(seat_id, "2026-10-17", "09:00", "11:00"),
    )
    assert booking.status_code == 201
    reservation_id = booking.get_json()["reservation"]["id"]

    client.post("/logout")
    for attempt in range(1, 6):
        response = login_as(client, password="wrong-password")
    assert attempt == 5
    assert response.status_code == 423
    assert response.get_json()["error"]["code"] == "ACCOUNT_LOCKED"

    user = db_query(
        "SELECT account_status, failed_login_count, locked_until FROM users "
        "WHERE student_no='246003384'"
    )[0]
    assert user["account_status"] == "锁定"
    assert user["failed_login_count"] == 5
    assert user["locked_until"] is not None

    locked_attempt = login_as(client)
    assert locked_attempt.status_code == 423
    assert locked_attempt.get_json()["remaining_minutes"] >= 1

    # 锁定不影响已有预约：预约与座位状态均保持。
    reservation = db_query(
        "SELECT status, seat_id FROM reservations WHERE id=?", (reservation_id,)
    )[0]
    assert reservation["status"] == "待生效"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "已预约"

    clock.advance(minutes=16)
    recovered = login_as(client)
    assert recovered.status_code == 200
    user = db_query(
        "SELECT account_status, failed_login_count, locked_until FROM users "
        "WHERE student_no='246003384'"
    )[0]
    assert user == {
        "account_status": "正常",
        "failed_login_count": 0,
        "locked_until": None,
    }
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "待生效"
