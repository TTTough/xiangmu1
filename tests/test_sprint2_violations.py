"""AC-05-01—AC-05-07：自动违约、判重、申诉成立/不成立与黑名单阈值。"""
from __future__ import annotations

import json
import threading
import time

from app import start_scheduler
from sprint2_helpers import (
    get_seat_id,
    get_user_id,
    make_checkin,
    make_reservation,
    make_violation,
    set_user_count,
)


def _admin_login(client, login_as):
    response = login_as(client, "900000001", "admin123")
    assert response.status_code == 200


def test_ac_05_01_scan_generates_v1_and_releases_seat(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="08:00", end="10:00"
    )
    _admin_login(client, login_as)

    response = client.post("/api/admin/scan")
    assert response.status_code == 200
    assert response.get_json()["scan"]["v1_created"] == 1

    reservation = db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]
    assert reservation["status"] == "已违约"
    violation = db_query(
        "SELECT violation_type, status FROM violations WHERE reservation_id=?",
        (reservation_id,),
    )[0]
    assert violation == {"violation_type": "V1 未签到", "status": "生效中"}
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 1
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND notification_type='违约记录'",
        (user_id,),
    )[0]["n"] == 1


def test_sprint2_scheduler_runs_scan_automatically(app, db_query, db_execute):
    """后台线程首轮即执行维护扫描，失败后可按 P-15 周期重试。"""
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="08:00", end="10:00"
    )
    stop = threading.Event()
    thread = start_scheduler(app, stop_event=stop)
    assert thread is not None and thread.is_alive()
    try:
        deadline = time.time() + 3
        while time.time() < deadline:
            if db_query(
                "SELECT status FROM reservations WHERE id=?", (reservation_id,)
            )[0]["status"] == "已违约":
                break
            time.sleep(0.05)
        assert db_query(
            "SELECT status FROM reservations WHERE id=?", (reservation_id,)
        )[0]["status"] == "已违约"
        assert db_query(
            "SELECT COUNT(*) AS n FROM violations WHERE reservation_id=?",
            (reservation_id,),
        )[0]["n"] == 1
    finally:
        stop.set()
        thread.join(timeout=3)
    assert not thread.is_alive()


def test_ac_05_02_scan_generates_v2_for_unchecked_out_usage(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="使用中", start="08:00", end="08:20"
    )
    make_checkin(db_execute, reservation_id, "2026-10-16 08:05:00")
    _admin_login(client, login_as)

    response = client.post("/api/admin/scan")
    assert response.status_code == 200
    assert response.get_json()["scan"]["v2_created"] == 1
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "已违约"
    assert db_query(
        "SELECT violation_type FROM violations WHERE reservation_id=?",
        (reservation_id,),
    )[0]["violation_type"] == "V2 未签退"
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"


def test_ac_05_03_appeal_approved_reverses_and_audits(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    violation_id = make_violation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        created_at="2026-10-15 08:30:00"
    )
    set_user_count(db_execute, user_id, 1)
    assert login_as(client).status_code == 200

    appeal = client.post(
        f"/api/violations/{violation_id}/appeal",
        json={"reason": "签到设备故障，已按时到场"},
    )
    assert appeal.status_code == 200
    assert appeal.get_json()["violation"]["status"] == "申诉中"

    admin_client = client.application.test_client()
    _admin_login(admin_client, login_as)
    decision = admin_client.post(
        f"/api/admin/violations/{violation_id}/appeal",
        json={"decision": "成立", "conclusion": "核实签到设备故障，申诉成立"},
    )
    assert decision.status_code == 200
    body = decision.get_json()["violation"]
    assert body["status"] == "申诉成立已撤销"
    assert body["effective_violation_count"] == 0

    record = db_query(
        "SELECT status, appeal_conclusion, appeal_judged_by FROM violations WHERE id=?",
        (violation_id,),
    )[0]
    assert record["status"] == "申诉成立已撤销"
    assert record["appeal_conclusion"] == "核实签到设备故障，申诉成立"
    assert record["appeal_judged_by"] is not None
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 0
    audit = db_query(
        """
        SELECT actor_name, after_json FROM audit_logs
         WHERE action='申诉复核' ORDER BY id DESC LIMIT 1
        """
    )[0]
    assert audit["actor_name"] == "自习室管理员"
    assert json.loads(audit["after_json"])["appeal_conclusion"] == "核实签到设备故障，申诉成立"


def test_ac_05_04_appeal_after_deadline_rejected(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    violation_id = make_violation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        created_at="2026-10-10 08:30:00"
    )
    set_user_count(db_execute, user_id, 1)
    assert login_as(client).status_code == 200

    response = client.post(
        f"/api/violations/{violation_id}/appeal", json={"reason": "补提交"}
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "APPEAL_WINDOW_CLOSED"
    assert db_query("SELECT status FROM violations WHERE id=?", (violation_id,))[0]["status"] == "生效中"
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 1


def test_ac_05_04_already_appealed_record_cannot_appeal_again(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    violation_id = make_violation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="申诉中", appeal_reason="首次申诉理由",
        appeal_at="2026-10-16 08:30:00"
    )
    set_user_count(db_execute, user_id, 1)
    assert login_as(client).status_code == 200

    response = client.post(
        f"/api/violations/{violation_id}/appeal", json={"reason": "再次申诉"}
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "NOT_APPEALABLE"
    assert db_query("SELECT status FROM violations WHERE id=?", (violation_id,))[0]["status"] == "申诉中"
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 1


def test_ac_05_05_new_violation_at_threshold_enters_blacklist(
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

    response = client.post("/api/admin/scan")
    assert response.status_code == 200
    assert response.get_json()["scan"]["v1_created"] == 1

    user = db_query(
        "SELECT account_status, effective_violation_count, blacklist_until "
        "FROM users WHERE id=?",
        (user_id,),
    )[0]
    assert user["account_status"] == "黑名单"
    assert user["effective_violation_count"] == 3
    assert user["blacklist_until"] is not None
    record = db_query(
        "SELECT status, expires_at FROM blacklists WHERE user_id=?", (user_id,)
    )[0]
    assert record["status"] == "生效中"
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND notification_type='黑名单状态'",
        (user_id,),
    )[0]["n"] == 1


def test_ac_05_06_rescan_does_not_duplicate_violation(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    reservation_id = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="待签到", start="08:00", end="10:00"
    )
    _admin_login(client, login_as)

    first = client.post("/api/admin/scan").get_json()["scan"]
    second = client.post("/api/admin/scan").get_json()["scan"]
    assert first["v1_created"] == 1
    assert second["v1_created"] == 0
    assert db_query(
        "SELECT COUNT(*) AS n FROM violations WHERE reservation_id=?",
        (reservation_id,),
    )[0]["n"] == 1
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 1


def test_ac_05_07_appeal_rejected_stays_effective(client, login_as, db_query, db_execute):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query)
    violation_id = make_violation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="申诉中", appeal_reason="对判定有异议",
        appeal_at="2026-10-16 08:30:00"
    )
    set_user_count(db_execute, user_id, 1)
    _admin_login(client, login_as)

    response = client.post(
        f"/api/admin/violations/{violation_id}/appeal",
        json={"decision": "不成立", "conclusion": "核实后维持原判定"},
    )
    assert response.status_code == 200
    assert response.get_json()["violation"]["status"] == "申诉不成立已终结"
    assert db_query("SELECT status FROM violations WHERE id=?", (violation_id,))[0]["status"] == "申诉不成立已终结"
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 1
    audit = db_query(
        "SELECT actor_name, after_json FROM audit_logs WHERE action='申诉复核' ORDER BY id DESC LIMIT 1"
    )[0]
    assert audit["actor_name"] == "自习室管理员"
    after = json.loads(audit["after_json"])
    assert after["decision"] == "不成立"
    assert after["appeal_conclusion"] == "核实后维持原判定"
