"""AC-03-01—AC-03-05：预约主链路、规则拒绝与并发唯一。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

from conftest import make_booking


def test_ac_03_01_create_reservation_updates_seat_notifies_and_audits(
    client, login_as, db_query
):
    login_as(client)
    seat_id = db_query("SELECT id FROM seats WHERE code='A-01'")[0]["id"]
    response = client.post(
        "/api/reservations",
        json=make_booking(seat_id, "2026-10-17", "09:00", "11:00"),
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 201
    reservation = response.get_json()["reservation"]
    assert reservation["status"] == "待生效"
    assert reservation["seat_code"] == "A-01"
    assert reservation["notification"]["delivery_result"] == "系统内消息已送达"

    stored = db_query(
        "SELECT status, source FROM reservations WHERE id=?", (reservation["id"],)
    )[0]
    assert stored == {"status": "待生效", "source": "学生自助"}
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "已预约"
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=("
        "SELECT id FROM users WHERE student_no='246003384')"
    )[0]["n"] == 1
    audit = db_query(
        "SELECT action, result, before_json, after_json, actor_name, actor_role "
        "FROM audit_logs WHERE action='提交预约' ORDER BY id DESC LIMIT 1"
    )[0]
    assert audit["result"] == "成功"
    assert audit["actor_name"] == "杨子涵"
    assert audit["actor_role"].startswith("学生")
    assert audit["before_json"] and audit["after_json"]


def test_ac_03_02_blacklist_rejects_reservation_without_side_effects(
    client, login_as, db_query, db_execute
):
    user = db_query("SELECT id FROM users WHERE student_no='246003384'")[0]
    db_execute(
        """
        UPDATE users SET account_status='黑名单',
                         blacklist_until='2026-10-23 08:30:00'
         WHERE id=?
        """,
        (user["id"],),
    )
    db_execute(
        """
        INSERT INTO blacklists
            (user_id, reason, source, effective_at, expires_at, status, created_at)
        VALUES (?, '累计违约达阈值', '自动', '2026-10-16 08:30:00',
                '2026-10-23 08:30:00', '生效中', '2026-10-16 08:30:00')
        """,
        (user["id"],),
    )
    assert login_as(client).status_code == 200
    seat_id = db_query("SELECT id FROM seats WHERE code='A-01'")[0]["id"]

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


def test_ac_03_03_second_active_reservation_rejected(
    client, login_as, db_query
):
    login_as(client)
    seat_a = db_query("SELECT id FROM seats WHERE code='A-01'")[0]["id"]
    seat_b = db_query("SELECT id FROM seats WHERE code='A-02'")[0]["id"]

    first = client.post(
        "/api/reservations", json=make_booking(seat_a, "2026-10-17", "09:00", "11:00")
    )
    assert first.status_code == 201

    second = client.post(
        "/api/reservations", json=make_booking(seat_b, "2026-10-17", "13:00", "15:00")
    )
    assert second.status_code == 409
    error = second.get_json()["error"]
    assert error["code"] == "ACTIVE_RESERVATION_LIMIT"
    assert "上限 1 个" in error["message"]
    assert db_query("SELECT COUNT(*) AS n FROM reservations")[0]["n"] == 1
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_b,))[0]["status"] == "空闲"


def test_ac_03_04_duration_and_advance_days_rejected(client, login_as, db_query):
    login_as(client)
    seat_id = db_query("SELECT id FROM seats WHERE code='A-01'")[0]["id"]

    too_long = client.post(
        "/api/reservations",
        json=make_booking(seat_id, "2026-10-17", "10:00", "16:00"),
    )
    assert too_long.status_code == 409
    assert too_long.get_json()["error"]["code"] == "DURATION_OUT_OF_RANGE"
    assert "30—240 分钟" in too_long.get_json()["error"]["message"]

    too_early = client.post(
        "/api/reservations",
        json=make_booking(seat_id, "2026-10-26", "09:00", "11:00"),
    )
    assert too_early.status_code == 409
    assert too_early.get_json()["error"]["code"] == "ADVANCE_LIMIT"
    assert "最多可提前 7 天" in too_early.get_json()["error"]["message"]

    assert db_query("SELECT COUNT(*) AS n FROM reservations")[0]["n"] == 0
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"


def test_ac_03_05_concurrent_booking_only_one_succeeds(
    app, login_as, create_user, db_query
):
    create_user("246003385", name="并发学生")
    seat_id = db_query("SELECT id FROM seats WHERE code='A-01'")[0]["id"]
    payload = make_booking(seat_id, "2026-10-17", "09:00", "11:00")

    first_client = app.test_client()
    second_client = app.test_client()
    assert login_as(first_client).status_code == 200
    assert login_as(second_client, "246003385").status_code == 200

    barrier = threading.Barrier(2)

    def submit(test_client):
        barrier.wait(timeout=10)
        response = test_client.post(
            "/api/reservations",
            json=payload,
            headers={"Accept": "application/json"},
        )
        return response.status_code, response.get_json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, (first_client, second_client)))

    statuses = sorted(item[0] for item in results)
    assert statuses == [201, 409]
    failure = next(body for status, body in results if status == 409)
    assert failure["error"]["code"] == "SEAT_TIME_CONFLICT"
    active = db_query(
        """
        SELECT COUNT(*) AS n FROM reservations
         WHERE seat_id=? AND reservation_date='2026-10-17'
           AND status IN ('待生效', '待签到', '使用中')
        """,
        (seat_id,),
    )[0]["n"]
    assert active == 1
