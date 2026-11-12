"""Sprint 11：预约修改（AC-04-07/08），含跨自习室与并发。"""
from __future__ import annotations

import threading
from datetime import datetime

import db
from app import ApiError, create_reservation, modify_reservation
from sprint2_helpers import get_seat_id, get_user_id, make_reservation


def _login(client, login_as, student_no="246003384", password="student123"):
    response = login_as(client, student_no, password)
    assert response.status_code == 200, response.get_data(as_text=True)
    return client


def _sysadmin(app, login_as):
    return _login(app.test_client(), login_as, "900000002", "sysadmin123")


def _create_room(sysadmin, code, status="开放", seat_code="M-01"):
    room = sysadmin.post(
        "/api/admin/rooms",
        json={
            "code": code,
            "name": f"修改测试自习室 {code}",
            "building": "图书馆",
            "floor": "6 层",
            "open_from": "08:00",
            "open_to": "22:00",
            "status": status,
        },
    )
    assert room.status_code == 201, room.get_data(as_text=True)
    room_id = room.get_json()["room"]["id"]
    zone = sysadmin.post(
        f"/api/admin/rooms/{room_id}/zones",
        json={"code": "ZM", "name": "修改区", "zone_type": "静音区", "sort_order": 1},
    )
    assert zone.status_code == 201
    zone_id = zone.get_json()["zone"]["id"]
    seat = sysadmin.post(
        f"/api/admin/zones/{zone_id}/seats",
        json={"code": seat_code, "seat_type": "普通", "position": "测试"},
    )
    assert seat.status_code == 201
    return room_id, zone_id, seat.get_json()["seat"]["id"]


def _create_booking(client, seat_id, date="2026-10-17", start="09:00", end="11:00"):
    response = client.post(
        "/api/reservations",
        json={
            "seat_id": seat_id,
            "reservation_date": date,
            "start_time": start,
            "end_time": end,
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["reservation"]


def _payload(room_id, zone_id, seat_id, date="2026-10-17", start="13:00", end="15:00"):
    return {
        "date": date,
        "from": start,
        "to": end,
        "room_id": room_id,
        "zone_id": zone_id,
        "seat_id": seat_id,
    }


def test_ac_04_07_cross_room_modify_success(app, login_as, db_query, db_execute):
    sysadmin = _sysadmin(app, login_as)
    student = _login(app.test_client(), login_as)
    room2, zone2, seat2 = _create_room(sysadmin, "R-MOD-2", seat_code="M-02")
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    before_seat = get_seat_id(db_query, "A-01")

    response = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room2, zone2, seat2),
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    updated = response.get_json()["reservation"]
    assert updated["reservation_no"] == booking["reservation_no"]
    assert updated["seat_id"] == seat2
    assert updated["modify_count"] == 1
    assert updated["modified_at"]

    old = db_query("SELECT status FROM seats WHERE id=?", (before_seat,))[0]
    new = db_query("SELECT status FROM seats WHERE id=?", (seat2,))[0]
    assert old["status"] == "空闲"
    assert new["status"] == "已预约"
    stored = db_query(
        "SELECT seat_id, room_id, zone_id, modify_count FROM reservations WHERE id=?",
        (booking["id"],),
    )[0]
    assert stored["seat_id"] == seat2
    assert stored["room_id"] == room2
    assert stored["zone_id"] == zone2
    assert stored["modify_count"] == 1

    audit = db_query(
        "SELECT before_json, after_json FROM audit_logs WHERE action='修改预约' ORDER BY id DESC"
    )[0]
    assert "A-01" in audit["before_json"]
    assert "M-02" in audit["after_json"]
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND title='预约修改成功'",
        (get_user_id(db_query),),
    )[0]["n"] == 1


def test_ac_04_07_same_room_modify_success(app, login_as, db_query):
    student = _login(app.test_client(), login_as)
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    room_id = db_query("SELECT room_id FROM seats WHERE code='A-01'")[0]["room_id"]
    zone_id = db_query("SELECT zone_id FROM seats WHERE code='A-02'")[0]["zone_id"]
    seat2 = get_seat_id(db_query, "A-02")
    response = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room_id, zone_id, seat2, date="2026-10-17", start="09:00", end="11:00"),
    )
    assert response.status_code == 200
    assert response.get_json()["reservation"]["seat_id"] == seat2
    assert db_query("SELECT status FROM seats WHERE code='A-01'")[0]["status"] == "空闲"
    assert db_query("SELECT status FROM seats WHERE code='A-02'")[0]["status"] == "已预约"


def test_ac_04_08_target_conflict_rejected_and_original_unchanged(
    app, login_as, db_query, create_user
):
    student = _login(app.test_client(), login_as)
    create_user("246003385", name="目标占用者")
    other = _login(app.test_client(), login_as, "246003385")
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    target_seat = get_seat_id(db_query, "B-01")
    room_id = db_query("SELECT room_id FROM seats WHERE id=?", (target_seat,))[0]["room_id"]
    zone_id = db_query("SELECT zone_id FROM seats WHERE id=?", (target_seat,))[0]["zone_id"]
    _create_booking(other, target_seat, start="13:00", end="15:00")

    response = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room_id, zone_id, target_seat),
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "SEAT_TIME_CONFLICT"
    stored = db_query("SELECT seat_id, status FROM reservations WHERE id=?", (booking["id"],))[0]
    assert stored["seat_id"] == get_seat_id(db_query, "A-01")
    assert stored["status"] == "待生效"


def test_ac_04_08_closed_room_rejected(app, login_as, db_query):
    sysadmin = _sysadmin(app, login_as)
    student = _login(app.test_client(), login_as)
    room2, zone2, seat2 = _create_room(sysadmin, "R-MOD-CLOSED", status="关闭")
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    response = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room2, zone2, seat2),
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ROOM_CLOSED"


def test_ac_04_08_disabled_seat_rejected(app, login_as, db_query):
    sysadmin = _sysadmin(app, login_as)
    student = _login(app.test_client(), login_as)
    room2, zone2, seat2 = _create_room(sysadmin, "R-MOD-DIS", seat_code="M-DIS")
    sysadmin.post(f"/api/admin/seats/{seat2}/disable", json={"reason": "测试停用"})
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    response = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room2, zone2, seat2),
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "SEAT_DISABLED"


def test_ac_04_08_modify_limit(app, login_as, db_query):
    student = _login(app.test_client(), login_as)
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    room_id = db_query("SELECT room_id FROM seats WHERE code='A-02'")[0]["room_id"]
    zone_id = db_query("SELECT zone_id FROM seats WHERE code='A-02'")[0]["zone_id"]
    first = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room_id, zone_id, get_seat_id(db_query, "A-02"), start="09:00", end="11:00"),
    )
    assert first.status_code == 200
    second = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room_id, zone_id, get_seat_id(db_query, "A-03"), start="09:00", end="11:00"),
    )
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "MODIFY_LIMIT"


def test_ac_04_08_after_start_rejected(app, login_as, db_query, clock):
    student = _login(app.test_client(), login_as)
    booking = _create_booking(student, get_seat_id(db_query, "A-01"), start="08:00", end="10:00")
    clock.value = datetime(2026, 10, 17, 8, 1, 0)
    student = _login(app.test_client(), login_as)
    room_id = db_query("SELECT room_id FROM seats WHERE code='A-02'")[0]["room_id"]
    zone_id = db_query("SELECT zone_id FROM seats WHERE code='A-02'")[0]["zone_id"]
    response = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room_id, zone_id, get_seat_id(db_query, "A-02"), start="09:00", end="11:00"),
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "MODIFY_WINDOW_CLOSED"


def test_ac_04_08_invalid_duration_and_advance_rejected(app, login_as, db_query):
    student = _login(app.test_client(), login_as)
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    room_id = db_query("SELECT room_id FROM seats WHERE code='A-02'")[0]["room_id"]
    zone_id = db_query("SELECT zone_id FROM seats WHERE code='A-02'")[0]["zone_id"]
    too_long = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room_id, zone_id, get_seat_id(db_query, "A-02"), start="08:00", end="14:00"),
    )
    assert too_long.status_code == 409
    assert too_long.get_json()["error"]["code"] == "DURATION_OUT_OF_RANGE"
    too_far = student.put(
        f"/api/reservations/{booking['id']}",
        json=_payload(room_id, zone_id, get_seat_id(db_query, "A-02"), date="2026-10-30"),
    )
    assert too_far.status_code == 409
    assert too_far.get_json()["error"]["code"] == "ADVANCE_LIMIT"


def test_ac_04_08_other_student_and_bad_status_rejected(
    app, login_as, db_query, db_execute, create_user
):
    student = _login(app.test_client(), login_as)
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    create_user("246003385", name="另一学生")
    other = _login(app.test_client(), login_as, "246003385")
    target_payload = _payload(
        db_query("SELECT room_id FROM seats WHERE code='A-01'")[0]["room_id"],
        db_query("SELECT zone_id FROM seats WHERE code='A-02'")[0]["zone_id"],
        get_seat_id(db_query, "A-02"),
        start="09:00", end="11:00",
    )
    assert other.put(
        f"/api/reservations/{booking['id']}", json=target_payload
    ).status_code == 403

    waiting_id = make_reservation(
        db_query, db_execute, user_id=get_user_id(db_query),
        seat_id=get_seat_id(db_query, "B-01"), status="待签到",
        start="09:00", end="11:00",
    )
    response = student.put(
        f"/api/reservations/{waiting_id}", json=target_payload
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "NOT_MODIFIABLE_STATUS"


def test_modify_page_renders(app, login_as, db_query):
    student = _login(app.test_client(), login_as)
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    page = student.get(f"/reservations/{booking['id']}/modify")
    assert page.status_code == 200
    assert "修改预约" in page.get_data(as_text=True)


def test_concurrent_modify_and_create_only_one_succeeds(
    app, login_as, db_query, db_execute, create_user
):
    create_user("246003385", name="并发学生")
    student = _login(app.test_client(), login_as)
    booking = _create_booking(student, get_seat_id(db_query, "A-01"))
    target_seat = get_seat_id(db_query, "C-01")
    room_id = db_query("SELECT room_id FROM seats WHERE id=?", (target_seat,))[0]["room_id"]
    zone_id = db_query("SELECT zone_id FROM seats WHERE id=?", (target_seat,))[0]["zone_id"]
    user1 = get_user_id(db_query)
    user2 = get_user_id(db_query, "246003385")
    barrier = threading.Barrier(2)
    results: list[tuple[str, str]] = []
    lock = threading.Lock()

    def do_modify():
        with app.app_context():
            with app.test_request_context("/", method="PUT", json={}):
                user = db.get_db().execute("SELECT * FROM users WHERE id=?", (user1,)).fetchone()
                barrier.wait()
                try:
                    modify_reservation(user, booking["id"], _payload(room_id, zone_id, target_seat))
                    with lock:
                        results.append(("modify", "ok"))
                except ApiError as exc:
                    with lock:
                        results.append(("modify", exc.code))

    def do_create():
        with app.app_context():
            with app.test_request_context("/", method="POST", json={}):
                user = db.get_db().execute("SELECT * FROM users WHERE id=?", (user2,)).fetchone()
                barrier.wait()
                try:
                    create_reservation(
                        user,
                        {
                            "seat_id": target_seat,
                            "reservation_date": "2026-10-17",
                            "start_time": "13:00",
                            "end_time": "15:00",
                        },
                    )
                    with lock:
                        results.append(("create", "ok"))
                except ApiError as exc:
                    with lock:
                        results.append(("create", exc.code))

    threads = [threading.Thread(target=do_modify), threading.Thread(target=do_create)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(1 for _, status in results if status == "ok") == 1, results
    assert any(status == "SEAT_TIME_CONFLICT" for _, status in results), results
    count = db_query(
        "SELECT COUNT(*) AS n FROM reservations WHERE seat_id=? AND reservation_date='2026-10-17' "
        "AND status IN ('待生效','待签到','使用中')",
        (target_seat,),
    )[0]["n"]
    assert count == 1
