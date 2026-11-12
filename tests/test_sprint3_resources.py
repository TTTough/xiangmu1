"""AC-02-01—AC-02-04：资源维护、直接状态改写拒绝、跨自习室授权与停用座位。"""
from __future__ import annotations

from conftest import make_booking
from sprint2_helpers import get_seat_id
from sprint3_helpers import create_unassigned_room, get_room_id


def _admin_login(client, login_as):
    assert login_as(client, "900000001", "admin123").status_code == 200


def test_ac_02_01_create_zone_and_seat_under_authorized_room(
    client, login_as, db_query
):
    _admin_login(client, login_as)
    room_id = get_room_id(db_query)

    zone_response = client.post(
        f"/api/admin/rooms/{room_id}/zones",
        json={"code": "Z9", "name": "考试专区", "zone_type": "静音区", "sort_order": 9},
    )
    assert zone_response.status_code == 201
    zone = zone_response.get_json()["zone"]
    assert zone["room_id"] == room_id

    seat_response = client.post(
        f"/api/admin/zones/{zone['id']}/seats",
        json={"code": "D-01", "seat_type": "靠窗", "position": "第 1 排"},
    )
    assert seat_response.status_code == 201
    seat = seat_response.get_json()["seat"]
    assert seat["room_id"] == room_id
    assert seat["zone_id"] == zone["id"]
    assert seat["status"] == "空闲"
    assert seat["is_bookable"] is True

    stored = db_query(
        "SELECT code, seat_type, status, is_bookable FROM seats WHERE id=?",
        (seat["id"],),
    )[0]
    assert stored == {
        "code": "D-01",
        "seat_type": "靠窗",
        "status": "空闲",
        "is_bookable": 1,
    }


def test_ac_02_02_direct_seat_status_write_forbidden_for_all_roles(
    app, login_as, db_query
):
    seat_id = get_seat_id(db_query, "A-01")
    student = app.test_client()
    admin = app.test_client()
    assert login_as(student).status_code == 200
    _admin_login(admin, login_as)

    for test_client in (student, admin):
        response = test_client.post(
            f"/api/admin/seats/{seat_id}/status", json={"status": "停用"}
        )
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "DIRECT_STATUS_WRITE_FORBIDDEN"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"


def test_ac_02_03_cross_room_zone_creation_rejected(
    client, login_as, db_query, db_execute
):
    other = create_unassigned_room(db_execute)
    _admin_login(client, login_as)

    response = client.post(
        f"/api/admin/rooms/{other['room_id']}/zones",
        json={"code": "Z-X", "name": "越权区域", "zone_type": "讨论区", "sort_order": 1},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "ROOM_FORBIDDEN"
    assert db_query(
        "SELECT COUNT(*) AS n FROM zones WHERE room_id=?", (other["room_id"],)
    )[0]["n"] == 1
    assert db_query(
        "SELECT COUNT(*) AS n FROM zones WHERE code='Z-X'"
    )[0]["n"] == 0


def test_ac_02_04_disable_seat_cancels_future_reservation_without_violation(
    app, login_as, db_query
):
    student = app.test_client()
    admin = app.test_client()
    assert login_as(student).status_code == 200
    _admin_login(admin, login_as)
    seat_id = get_seat_id(db_query, "A-02")
    booking = student.post(
        "/api/reservations",
        json=make_booking(seat_id, "2026-10-17", "09:00", "11:00"),
    )
    assert booking.status_code == 201
    reservation = booking.get_json()["reservation"]

    response = admin.post(
        f"/api/admin/seats/{seat_id}/disable",
        json={"reason": "座椅损坏，维修停用"},
    )
    assert response.status_code == 200
    body = response.get_json()["seat"]
    assert body["status"] == "停用"
    assert body["is_bookable"] is False
    assert reservation["reservation_no"] in body["cancelled_reservations"]

    seat = db_query(
        "SELECT status, is_bookable FROM seats WHERE id=?", (seat_id,)
    )[0]
    assert seat == {"status": "停用", "is_bookable": 0}
    stored = db_query(
        "SELECT status, cancel_reason FROM reservations WHERE id=?",
        (reservation["id"],),
    )[0]
    assert stored["status"] == "已取消"
    assert "座位停用" in stored["cancel_reason"]
    assert db_query("SELECT COUNT(*) AS n FROM violations")[0]["n"] == 0
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE notification_type='预约变更'"
    )[0]["n"] == 1
    audit = db_query(
        "SELECT actor_name, result FROM audit_logs WHERE action='停用座位' ORDER BY id DESC LIMIT 1"
    )[0]
    assert audit == {"actor_name": "自习室管理员", "result": "成功"}
