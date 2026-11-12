"""AC-04-03—AC-04-06：签到、签退与座位号校验。"""
from __future__ import annotations

from datetime import datetime

from sprint2_helpers import get_seat_id, get_user_id, make_checkin, make_reservation


def test_ac_04_03_checkin_within_window(client, login_as, db_query, db_execute):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="08:30", end="10:30"
    )
    assert login_as(client).status_code == 200

    response = client.post(
        f"/api/reservations/{reservation_id}/checkin",
        json={"seat_code": "A-01", "method": "二维码"},
    )
    assert response.status_code == 200
    body = response.get_json()["checkin"]
    assert body["reservation_status"] == "使用中"
    assert body["seat_status"] == "使用中"
    assert body["method"] == "二维码"

    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "使用中"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "使用中"
    checkin = db_query(
        "SELECT method, checkin_at FROM checkins WHERE reservation_id=?", (reservation_id,)
    )[0]
    assert checkin == {"method": "二维码", "checkin_at": "2026-10-16 08:30:00"}
    assert db_query(
        "SELECT result FROM audit_logs WHERE action='签到' ORDER BY id DESC LIMIT 1"
    )[0]["result"] == "成功"


def test_ac_04_04_checkin_before_window_rejected(client, login_as, db_query, db_execute):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="09:00", end="11:00"
    )
    assert login_as(client).status_code == 200

    response = client.post(
        f"/api/reservations/{reservation_id}/checkin",
        json={"seat_code": "A-01", "method": "座位编号"},
    )
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "CHECKIN_WINDOW_NOT_STARTED"
    assert "08:45" in error["message"]
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "待签到"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "已预约"
    assert db_query("SELECT COUNT(*) AS n FROM checkins")[0]["n"] == 0


def test_ac_04_05_checkout_records_actual_duration(client, login_as, db_query, db_execute, clock):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="使用中", start="08:00", end="10:00"
    )
    make_checkin(db_execute, reservation_id, "2026-10-16 08:10:00", "二维码")
    clock.value = datetime(2026, 10, 16, 9, 0, 0)
    assert login_as(client).status_code == 200

    response = client.post(f"/api/reservations/{reservation_id}/checkout")
    assert response.status_code == 200
    body = response.get_json()["checkout"]
    assert body["reservation_status"] == "已完成"
    assert body["seat_status"] == "空闲"
    assert body["actual_minutes"] == 50

    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "已完成"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"
    checkin = db_query(
        "SELECT checkout_at, actual_minutes FROM checkins WHERE reservation_id=?",
        (reservation_id,),
    )[0]
    assert checkin == {"checkout_at": "2026-10-16 09:00:00", "actual_minutes": 50}


def test_ac_04_06_checkin_wrong_seat_rejected(client, login_as, db_query, db_execute):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="08:30", end="10:30"
    )
    assert login_as(client).status_code == 200

    response = client.post(
        f"/api/reservations/{reservation_id}/checkin",
        json={"seat_code": "B-01", "method": "座位编号"},
    )
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "SEAT_MISMATCH"
    assert "B-01" in error["message"] and "A-01" in error["message"]
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "待签到"
    assert db_query("SELECT COUNT(*) AS n FROM checkins")[0]["n"] == 0
