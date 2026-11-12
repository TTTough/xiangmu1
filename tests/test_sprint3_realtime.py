"""AC-07-01—AC-07-06：实时座位、V3 手动违约、跨自习室拒绝与历史记录。"""
from __future__ import annotations

from sprint2_helpers import (
    get_seat_id,
    get_user_id,
    make_checkin,
    make_reservation,
    make_violation,
)
from sprint3_helpers import create_unassigned_room, get_room_id


def _admin_login(client, login_as):
    assert login_as(client, "900000001", "admin123").status_code == 200


def test_ac_07_01_realtime_view_masks_occupant_and_shows_slot(
    client, login_as, db_query, db_execute, create_user
):
    user_id = create_user("246003385", name="李小明")
    seat_id = get_seat_id(db_query, "A-01")
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="使用中", start="08:00", end="10:00"
    )
    make_checkin(db_execute, reservation_id, "2026-10-16 08:05:00")
    _admin_login(client, login_as)

    response = client.get(f"/api/admin/realtime?room_id={get_room_id(db_query)}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["room"]["name"] == "图书馆三层自习室"
    all_seats = [seat for zone in data["zones"] for seat in zone["seats"]]
    seat = next(item for item in all_seats if item["code"] == "A-01")
    assert seat["status"] == "使用中"
    assert seat["current_occupant"]["name_masked"] == "李**"
    assert seat["current_occupant"]["student_no_masked"] == "246***385"
    assert seat["reservation"]["start_time"] == "08:00"
    assert seat["reservation"]["end_time"] == "10:00"
    assert "李小明" not in response.get_data(as_text=True)

    page = client.get(f"/admin/realtime?room_id={get_room_id(db_query)}")
    assert page.status_code == 200
    assert "实时座位视图" in page.get_data(as_text=True)


def test_ac_07_02_manual_violation_without_reason_rejected(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query, "A-01")
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="09:00", end="11:00"
    )
    _admin_login(client, login_as)

    response = client.post(
        f"/api/admin/seats/{seat_id}/manual-violation", json={"reason": ""}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MISSING_FIELD"
    assert db_query("SELECT COUNT(*) AS n FROM violations")[0]["n"] == 0
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "待签到"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "已预约"


def test_ac_07_03_manual_violation_creates_v3_releases_and_notifies(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query, "A-01")
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="09:00", end="11:00"
    )
    _admin_login(client, login_as)

    response = client.post(
        f"/api/admin/seats/{seat_id}/manual-violation",
        json={"reason": "现场长时间占座且拒绝出示预约信息"},
    )
    assert response.status_code == 201
    body = response.get_json()["violation"]
    assert body["violation_type"] == "V3 管理员手动登记"
    assert body["seat_status"] == "空闲"
    assert body["effective_violation_count"] == 1

    violation = db_query(
        "SELECT violation_type, status, registered_by FROM violations WHERE reservation_id=?",
        (reservation_id,),
    )[0]
    assert violation["violation_type"] == "V3 管理员手动登记"
    assert violation["status"] == "生效中"
    assert violation["registered_by"] is not None
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "已违约"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 1
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND notification_type='违约记录'",
        (user_id,),
    )[0]["n"] == 1
    audit = db_query(
        "SELECT actor_name, before_json, after_json FROM audit_logs "
        "WHERE action='手动违约登记' ORDER BY id DESC LIMIT 1"
    )[0]
    assert audit["actor_name"] == "自习室管理员"
    assert audit["before_json"] and audit["after_json"]


def test_ac_07_04_manual_violation_on_unauthorized_room_rejected(
    client, login_as, db_query, db_execute
):
    other = create_unassigned_room(db_execute)
    _admin_login(client, login_as)
    response = client.post(
        f"/api/admin/seats/{other['seat_id']}/manual-violation",
        json={"reason": "越权登记"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "ROOM_FORBIDDEN"
    assert db_query("SELECT COUNT(*) AS n FROM violations")[0]["n"] == 0
    assert db_query(
        "SELECT status FROM seats WHERE id=?", (other["seat_id"],)
    )[0]["status"] == "空闲"


def test_ac_07_05_seat_history_masks_user_and_shows_usage(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query, "A-01")
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="已完成", reservation_date="2026-10-15", start="08:00", end="10:00"
    )
    db_execute(
        "INSERT INTO checkins (reservation_id, checkin_at, method, checkout_at, actual_minutes) "
        "VALUES (?, '2026-10-15 08:05:00', '二维码', '2026-10-15 10:00:00', 115)",
        (reservation_id,),
    )
    make_violation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        reservation_id=reservation_id, status="生效中", created_at="2026-10-15 10:00:00"
    )
    _admin_login(client, login_as)

    response = client.get(f"/api/admin/seats/{seat_id}/history")
    assert response.status_code == 200
    data = response.get_json()
    assert data["seat"]["code"] == "A-01"
    entry = data["history"][0]
    assert entry["user_masked"] == "杨**"
    assert entry["student_no_masked"] == "246***384"
    assert entry["checkin_at"] == "2026-10-15 08:05:00"
    assert entry["checkout_at"] == "2026-10-15 10:00:00"
    assert entry["actual_minutes"] == 115
    assert entry["violations"][0]["violation_type"] == "V1 未签到"
    assert "杨子涵" not in response.get_data(as_text=True)

    page = client.get(f"/admin/seats/{seat_id}/history")
    assert page.status_code == 200
    assert "座位历史记录" in page.get_data(as_text=True)


def test_ac_07_06_release_reservation_requires_reason_and_notifies(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query, "A-01")
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待生效", reservation_date="2026-10-17", start="09:00", end="11:00"
    )
    _admin_login(client, login_as)

    without_reason = client.post(
        f"/api/admin/reservations/{reservation_id}/release", json={"reason": ""}
    )
    assert without_reason.status_code == 400
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "待生效"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "已预约"

    released = client.post(
        f"/api/admin/reservations/{reservation_id}/release",
        json={"reason": "现场需要临时改为考场"},
    )
    assert released.status_code == 200
    body = released.get_json()["reservation"]
    assert body["status"] == "已取消"
    assert body["seat_status"] == "空闲"
    assert db_query(
        "SELECT status, cancel_reason FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "已取消"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND notification_type='预约变更'",
        (user_id,),
    )[0]["n"] == 1
    audit = db_query(
        "SELECT actor_name, after_json FROM audit_logs WHERE action='提前释放座位' ORDER BY id DESC LIMIT 1"
    )[0]
    assert audit["actor_name"] == "自习室管理员"
    assert "现场需要临时改为考场" in audit["after_json"]
