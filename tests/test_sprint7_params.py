"""AC-13-01—AC-13-04：参数配置、范围校验、审计与历史不回溯。"""
from __future__ import annotations

from datetime import datetime

from sprint2_helpers import (
    get_seat_id,
    get_user_id,
    make_reservation,
    make_violation,
    set_user_count,
)


def _sysadmin_login(client, login_as):
    assert login_as(client, "900000002", "sysadmin123").status_code == 200


def _admin_login(client, login_as):
    assert login_as(client, "900000001", "admin123").status_code == 200


def test_ac_13_01_updated_checkin_window_takes_effect(
    app, login_as, db_query, db_execute, clock
):
    sysadmin = app.test_client()
    _sysadmin_login(sysadmin, login_as)
    update = sysadmin.put(
        "/api/system/rule-params/checkin_late_minutes", json={"value": 25}
    )
    assert update.status_code == 200
    assert update.get_json()["param"]["after"] == "25"
    assert db_query(
        "SELECT value FROM rule_params WHERE param_key='checkin_late_minutes'"
    )[0]["value"] == "25"

    clock.value = datetime(2026, 10, 16, 8, 18, 0)
    student = app.test_client()
    assert login_as(student).status_code == 200
    reservation_id = make_reservation(
        db_query, db_execute, user_id=get_user_id(db_query),
        seat_id=get_seat_id(db_query, "A-01"),
        status="待签到", start="08:00", end="10:00"
    )
    response = student.post(
        f"/api/reservations/{reservation_id}/checkin",
        json={"seat_code": "A-01", "method": "座位编号"},
    )
    assert response.status_code == 200
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "使用中"
    assert db_query(
        "SELECT COUNT(*) AS n FROM checkins WHERE reservation_id=?", (reservation_id,)
    )[0]["n"] == 1
    page = sysadmin.get("/sysadmin/params")
    assert page.status_code == 200
    assert "规则参数配置" in page.get_data(as_text=True)


def test_ac_13_02_out_of_range_rejected_and_original_kept(
    client, login_as, db_query
):
    _sysadmin_login(client, login_as)
    response = client.put(
        "/api/system/rule-params/data_refresh_seconds", json={"value": 999}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "PARAM_OUT_OF_RANGE"
    assert "5.0—60.0" in response.get_json()["error"]["message"]
    assert db_query(
        "SELECT value FROM rule_params WHERE param_key='data_refresh_seconds'"
    )[0]["value"] == "10"


def test_ac_13_03_parameter_change_audit_has_before_after(client, login_as, db_query):
    _sysadmin_login(client, login_as)
    update = client.put(
        "/api/system/rule-params/blacklist_threshold", json={"value": 4}
    )
    assert update.status_code == 200
    response = client.get(
        "/api/system/audit-logs", query_string={"action": "参数变更"}
    )
    assert response.status_code == 200
    log = response.get_json()["logs"][0]
    assert log["actor_name"] == "系统管理员"
    assert log["target_id"] == "blacklist_threshold"
    assert log["before"]["value"] == "3"
    assert log["after"]["value"] == "4"
    assert log["created_at"]
    page = client.get("/sysadmin/audit", query_string={"action": "参数变更"})
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "blacklist_threshold" in text
    assert "变更前" in text and "变更后" in text


def test_ac_13_04_parameter_change_does_not_retroactively_apply(
    app, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    set_user_count(db_execute, user_id, 1)
    violation_id = make_violation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "A-01"),
        status="生效中", created_at="2026-10-15 08:00:00"
    )

    sysadmin = app.test_client()
    _sysadmin_login(sysadmin, login_as)
    update = sysadmin.put(
        "/api/system/rule-params/blacklist_threshold", json={"value": 1}
    )
    assert update.status_code == 200
    # 参数变更不会追溯处理历史违约记录。
    assert db_query(
        "SELECT status FROM violations WHERE id=?", (violation_id,)
    )[0]["status"] == "生效中"
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 1
    assert db_query("SELECT COUNT(*) AS n FROM blacklists")[0]["n"] == 0

    # 变更之后产生的新判定按新阈值执行。
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "B-01"),
        status="待签到", start="08:00", end="10:00"
    )
    admin = app.test_client()
    _admin_login(admin, login_as)
    scan = admin.post("/api/admin/scan")
    assert scan.status_code == 200
    assert scan.get_json()["scan"]["v1_created"] == 1
    assert db_query(
        "SELECT effective_violation_count FROM users WHERE id=?", (user_id,)
    )[0]["effective_violation_count"] == 2
    assert db_query(
        "SELECT COUNT(*) AS n FROM blacklists WHERE user_id=? AND status='生效中'",
        (user_id,),
    )[0]["n"] == 1
