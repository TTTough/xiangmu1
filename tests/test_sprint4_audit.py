"""AC-14-01—AC-14-04：审计覆盖、前后值、不可改删、筛选分页与角色权限。"""
from __future__ import annotations

import html
import re
import sqlite3
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pytest

from conftest import make_booking
from sprint2_helpers import (
    get_seat_id,
    get_user_id,
    make_blacklist,
    make_reservation,
    make_violation,
)


def _admin_login(client, login_as):
    assert login_as(client, "900000001", "admin123").status_code == 200


def _sysadmin_login(client, login_as):
    assert login_as(client, "900000002", "sysadmin123").status_code == 200


def test_ac_14_01_required_management_operations_have_complete_audit(
    app, login_as, db_query, db_execute, create_user
):
    user_id = get_user_id(db_query)
    other_id = create_user("246003385", name="李小明")
    make_blacklist(
        db_query, db_execute, user_id=other_id, expires_at="2026-10-20 08:30:00"
    )
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "A-01"),
        status="待签到", start="09:00", end="11:00"
    )
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "A-02"),
        status="待生效", reservation_date="2026-10-17", start="09:00", end="11:00"
    )
    blacklist_id = db_query(
        "SELECT id FROM blacklists WHERE user_id=? AND status='生效中'", (other_id,)
    )[0]["id"]

    admin = app.test_client()
    _admin_login(admin, login_as)
    v3 = admin.post(
        f"/api/admin/seats/{get_seat_id(db_query, 'A-01')}/manual-violation",
        json={"reason": "现场违规占座"},
    )
    assert v3.status_code == 201
    disable = admin.post(
        f"/api/admin/seats/{get_seat_id(db_query, 'A-02')}/disable",
        json={"reason": "座椅损坏维修"},
    )
    assert disable.status_code == 200
    release = admin.post(
        f"/api/admin/blacklists/{blacklist_id}/release",
        json={"reason": "核实申诉成立，提前解除"},
    )
    assert release.status_code == 200

    sysadmin = app.test_client()
    _sysadmin_login(sysadmin, login_as)
    response = sysadmin.get("/api/system/audit-logs?page_size=100")
    assert response.status_code == 200
    logs = response.get_json()["logs"]
    by_action = {log["action"]: log for log in logs}
    for action in ("手动违约登记", "停用座位", "提前解除黑名单"):
        assert action in by_action
        log = by_action[action]
        assert log["actor_name"] == "自习室管理员"
        assert log["actor_role"].startswith("自习室管理员")
        assert log["target_type"] and log["target_id"]
        assert log["created_at"]
        assert log["before"] is not None and log["after"] is not None


def test_ac_14_02_parameter_change_shows_before_and_after(client, login_as):
    _sysadmin_login(client, login_as)
    update = client.put(
        "/api/system/rule-params/data_refresh_seconds", json={"value": 15}
    )
    assert update.status_code == 200
    assert update.get_json()["param"]["before"] == "10"
    assert update.get_json()["param"]["after"] == "15"

    response = client.get("/api/system/audit-logs", query_string={"action": "参数变更"})
    assert response.status_code == 200
    logs = response.get_json()["logs"]
    assert len(logs) == 1
    log = logs[0]
    assert log["before"]["value"] == "10"
    assert log["after"]["value"] == "15"

    page = client.get("/sysadmin/audit", query_string={"action": "参数变更"})
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "参数变更" in text
    assert "变更前" in text and "变更后" in text
    assert "data_refresh_seconds" in text
    assert "15" in text


def test_ac_14_03_audit_update_or_delete_rejected(client, login_as, db_query, db_execute):
    _sysadmin_login(client, login_as)
    log = db_query("SELECT id, result FROM audit_logs ORDER BY id LIMIT 1")[0]
    original_count = db_query("SELECT COUNT(*) AS n FROM audit_logs")[0]["n"]

    update_response = client.put(f"/api/system/audit-logs/{log['id']}", json={"result": "篡改"})
    assert update_response.status_code == 403
    assert update_response.get_json()["error"]["code"] == "AUDIT_LOG_IMMUTABLE"
    delete_response = client.delete(f"/api/system/audit-logs/{log['id']}")
    assert delete_response.status_code == 403
    assert delete_response.get_json()["error"]["code"] == "AUDIT_LOG_IMMUTABLE"
    assert db_query("SELECT COUNT(*) AS n FROM audit_logs")[0]["n"] == original_count
    assert db_query("SELECT result FROM audit_logs WHERE id=?", (log["id"],))[0]["result"] == log["result"]

    with pytest.raises(sqlite3.IntegrityError):
        db_execute("UPDATE audit_logs SET result='篡改' WHERE id=?", (log["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        db_execute("DELETE FROM audit_logs WHERE id=?", (log["id"],))


def test_ac_14_04_audit_filter_and_pagination(client, login_as, db_execute, db_query):
    for index in range(12):
        db_execute(
            """
            INSERT INTO audit_logs
                (actor_user_id, actor_name, actor_role, action, target_type,
                 target_id, before_json, after_json, result, ip_address, created_at)
            VALUES (NULL, '筛选测试', '系统', '手动违约登记', '座位', 'A-01',
                    '{"status":"使用中"}', '{"status":"空闲"}', '成功',
                    '127.0.0.1', ?)
            """,
            (f"2026-10-15 10:{index:02d}:00",),
        )
    _sysadmin_login(client, login_as)
    response = client.get(
        "/api/system/audit-logs",
        query_string={
            "actor": "筛选测试",
            "action": "手动违约登记",
            "target": "A-01",
            "date_from": "2026-10-15",
            "date_to": "2026-10-15",
            "page": 2,
            "page_size": 5,
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"]["total"] == 12
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["page_size"] == 5
    assert body["pagination"]["total_pages"] == 3
    assert len(body["logs"]) == 5
    assert all(log["actor_name"] == "筛选测试" for log in body["logs"])
    assert all(log["action"] == "手动违约登记" for log in body["logs"])

    page = client.get(
        "/sysadmin/audit",
        query_string={
            "actor": "筛选测试",
            "action": "手动违约登记",
            "target": "A-01",
            "date_from": "2026-10-15",
            "date_to": "2026-10-15",
            "page": 2,
            "page_size": 5,
        },
    )
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    next_link = re.search(r'href="([^"]*page=3[^"]*)"', text)
    assert next_link is not None
    parsed = urlparse(html.unescape(next_link.group(1)))
    query_args = parse_qs(parsed.query)
    assert query_args["actor"] == ["筛选测试"]
    assert query_args["action"] == ["手动违约登记"]
    assert query_args["target"] == ["A-01"]
    assert query_args["date_from"] == ["2026-10-15"]


def test_audit_endpoints_are_sysadmin_only(app, login_as):
    student = app.test_client()
    admin = app.test_client()
    assert login_as(student).status_code == 200
    _admin_login(admin, login_as)
    for test_client in (student, admin):
        api = test_client.get("/api/system/audit-logs")
        assert api.status_code == 403
        page = test_client.get("/sysadmin/audit")
        assert page.status_code == 403


def test_all_existing_operations_are_audited(
    app, login_as, db_query, db_execute, clock
):
    student = app.test_client()
    admin = app.test_client()
    sysadmin = app.test_client()
    assert login_as(student).status_code == 200
    user_id = get_user_id(db_query)

    # 预约 + 取消
    seat_a3 = get_seat_id(db_query, "A-03")
    create = student.post(
        "/api/reservations",
        json=make_booking(seat_a3, "2026-10-17", "09:00", "11:00"),
    )
    assert create.status_code == 201
    reservation_id = create.get_json()["reservation"]["id"]
    assert student.post(f"/api/reservations/{reservation_id}/cancel").status_code == 200

    # 签到 + 签退
    seat_a4 = get_seat_id(db_query, "A-04")
    checkin_reservation = make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_a4,
        status="待签到", start="08:30", end="10:30"
    )
    checkin = student.post(
        f"/api/reservations/{checkin_reservation}/checkin",
        json={"seat_code": "A-04", "method": "二维码"},
    )
    assert checkin.status_code == 200
    clock.value = datetime(2026, 10, 16, 9, 0, 0)
    assert student.post(f"/api/reservations/{checkin_reservation}/checkout").status_code == 200

    # 自动违约
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "B-01"),
        status="待签到", start="08:00", end="10:00"
    )
    _admin_login(admin, login_as)
    scan = admin.post("/api/admin/scan")
    assert scan.status_code == 200
    assert scan.get_json()["scan"]["v1_created"] == 1

    # 申诉 + 复核
    violation_id = make_violation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "B-01"),
        status="生效中", created_at="2026-10-16 09:00:00"
    )
    assert student.post(
        f"/api/violations/{violation_id}/appeal", json={"reason": "申诉审计测试"}
    ).status_code == 200
    assert admin.post(
        f"/api/admin/violations/{violation_id}/appeal",
        json={"decision": "不成立", "conclusion": "核实后维持"},
    ).status_code == 200

    # 停用座位
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "B-02"),
        status="待生效", reservation_date="2026-10-18", start="09:00", end="11:00"
    )
    assert admin.post(
        f"/api/admin/seats/{get_seat_id(db_query, 'B-02')}/disable",
        json={"reason": "审计覆盖测试停用"},
    ).status_code == 200

    # V3 手动违约
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "B-03"),
        status="待签到", start="09:00", end="11:00"
    )
    assert admin.post(
        f"/api/admin/seats/{get_seat_id(db_query, 'B-03')}/manual-violation",
        json={"reason": "审计覆盖测试 V3"},
    ).status_code == 201

    _sysadmin_login(sysadmin, login_as)
    logs = sysadmin.get("/api/system/audit-logs?page_size=100").get_json()["logs"]
    actions = {log["action"] for log in logs}
    required = {
        "登录",
        "提交预约",
        "取消预约",
        "签到",
        "签退",
        "自动违约判定",
        "提交申诉",
        "申诉复核",
        "停用座位",
        "手动违约登记",
    }
    assert required.issubset(actions)
    for log in logs:
        if log["action"] in required:
            assert log["before"] is not None and log["after"] is not None
