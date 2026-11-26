"""v0.8 基线对齐：sysadmin 权限、P-15 范围、参数生效点、Q-33/34/35 行为。"""
from __future__ import annotations

from pathlib import Path

from config import Config, PARAM_EFFECT_POINTS
from sprint2_helpers import get_seat_id, get_user_id, make_blacklist, make_violation
from sprint3_helpers import get_room_id


def _login(client, login_as, student_no, password):
    response = login_as(client, student_no, password)
    assert response.status_code == 200, response.get_data(as_text=True)
    return client


def test_sysadmin_permissions_match_matrix_and_forbidden_actions(
    app, login_as, db_query
):
    sysadmin = _login(app.test_client(), login_as, "900000002", "sysadmin123")
    seat_id = get_seat_id(db_query, "A-01")

    # 页面：资源、实时、申诉、黑名单、评价、投诉、座位历史
    for path in (
        "/admin/resources",
        "/admin/realtime",
        "/admin/appeals",
        "/admin/blacklists",
        "/admin/evaluations",
        "/admin/complaints",
        f"/admin/seats/{seat_id}/history",
    ):
        assert sysadmin.get(path).status_code == 200, path

    # API：资源、实时、历史、分析、参数、审计
    for path in (
        "/api/admin/resources",
        "/api/admin/realtime",
        f"/api/admin/seats/{seat_id}/history",
        "/api/analytics",
        "/api/system/rule-params",
        "/api/system/audit-logs",
    ):
        assert sysadmin.get(path).status_code == 200, path

    # 权限矩阵第 15 行：系统管理员可新增自习室，并看到全部自习室
    created = sysadmin.post(
        "/api/admin/rooms",
        json={
            "code": "R-SYS-8F",
            "name": "系统管理员测试自习室",
            "building": "图书馆",
            "floor": "8 层",
            "open_from": "08:00",
            "open_to": "22:00",
            "status": "开放",
        },
    )
    assert created.status_code == 201
    room_id = created.get_json()["room"]["id"]
    resources = sysadmin.get("/api/admin/resources").get_json()["rooms"]
    assert any(room["id"] == room_id for room in resources)
    assert any(room["code"] == "R-N1-101" for room in resources)

    # 权限矩阵第 16 行：停用 / 恢复
    seat_b = get_seat_id(db_query, "A-02")
    assert sysadmin.post(
        f"/api/admin/seats/{seat_b}/disable", json={"reason": "基线对齐测试停用"}
    ).status_code == 200
    assert sysadmin.post(
        f"/api/admin/seats/{seat_b}/restore", json={"reason": "基线对齐测试恢复"}
    ).status_code == 200

    # 实时页面：系统管理员不呈现 V3 / 提前释放入口，管理员仍呈现
    sysadmin_page = sysadmin.get("/admin/realtime").get_data(as_text=True)
    assert "V3 手动违约登记" not in sysadmin_page
    assert "提前释放当前预约" not in sysadmin_page
    admin_client = _login(app.test_client(), login_as, "900000001", "admin123")
    admin_page = admin_client.get("/admin/realtime").get_data(as_text=True)
    assert "V3 手动违约登记" in admin_page
    assert "提前释放当前预约" in admin_page

    # 权限矩阵第 18 行：手动违约禁止
    forbidden_v3 = sysadmin.post(
        f"/api/admin/seats/{seat_id}/manual-violation",
        json={"reason": "系统管理员不应登记 V3"},
    )
    assert forbidden_v3.status_code == 403

    # 权限矩阵第 29 行：提前释放禁止
    forbidden_release = sysadmin.post(
        "/api/admin/reservations/1/release",
        json={"reason": "系统管理员不应提前释放"},
    )
    assert forbidden_release.status_code == 403


def test_sysadmin_can_accept_complaint_and_release_blacklist(
    app, login_as, db_query, db_execute
):
    student = _login(app.test_client(), login_as, "246003384", "student123")
    complaint = student.post(
        "/api/complaints",
        json={
            "object_type": "座位或自习室",
            "object_ref": "A-01",
            "complaint_type": "环境问题",
            "content": "基线对齐测试投诉。",
        },
    )
    assert complaint.status_code == 201
    complaint_id = complaint.get_json()["complaint"]["id"]

    sysadmin = _login(app.test_client(), login_as, "900000002", "sysadmin123")
    assert sysadmin.post(
        f"/api/admin/complaints/{complaint_id}/accept"
    ).status_code == 200
    assert sysadmin.post(
        f"/api/admin/complaints/{complaint_id}/feedback",
        json={"feedback": "已由系统管理员完成基线对齐测试反馈。"},
    ).status_code == 200

    user_id = get_user_id(db_query)
    blacklist_id = make_blacklist(db_query, db_execute, user_id=user_id)
    release = sysadmin.post(
        f"/api/admin/blacklists/{blacklist_id}/release",
        json={"reason": "基线对齐测试解除"},
    )
    assert release.status_code == 200
    assert release.get_json()["blacklist"]["blacklist_status"] == "已解除"


def test_sysadmin_can_adjudicate_appeal(app, login_as, db_query, db_execute):
    user_id = get_user_id(db_query)
    violation_id = make_violation(
        db_query,
        db_execute,
        user_id=user_id,
        seat_id=get_seat_id(db_query, "A-01"),
        status="申诉中",
        appeal_reason="基线对齐测试申诉",
        appeal_at="2026-10-16 09:00:00",
    )
    sysadmin = _login(app.test_client(), login_as, "900000002", "sysadmin123")
    response = sysadmin.post(
        f"/api/admin/violations/{violation_id}/appeal",
        json={"decision": "成立", "conclusion": "基线对齐测试复核成立"},
    )
    assert response.status_code == 200
    assert response.get_json()["violation"]["status"] == "申诉成立已撤销"


def test_p15_range_is_10_to_60_and_page_synced(client, login_as):
    _login(client, login_as, "900000002", "sysadmin123")
    params = client.get("/api/system/rule-params").get_json()["params"]
    p15 = next(item for item in params if item["param_no"] == "P-15")
    assert p15["min_value"] == 10
    assert p15["max_value"] == 60
    assert p15["range_text"] == "10—60 秒"

    rejected = client.put(
        "/api/system/rule-params/violation_scan_seconds", json={"value": 61}
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["error"]["code"] == "PARAM_OUT_OF_RANGE"

    accepted = client.put(
        "/api/system/rule-params/violation_scan_seconds", json={"value": 60}
    )
    assert accepted.status_code == 200
    assert accepted.get_json()["param"]["after"] == "60"

    page = client.get("/sysadmin/params")
    assert page.status_code == 200
    assert "10—60 秒" in page.get_data(as_text=True)


def test_parameter_effect_annotations_cover_all_28(client, login_as):
    _login(client, login_as, "900000002", "sysadmin123")
    params = client.get("/api/system/rule-params").get_json()["params"]
    assert len(params) == 28
    assert len(PARAM_EFFECT_POINTS) == 15

    for item in params:
        assert item["effect_status"] in ("已接入", "未接入")
        assert item["effect_point"]

    wired = {item["param_key"] for item in params if item["effect_status"] == "已接入"}
    assert wired == set(PARAM_EFFECT_POINTS)
    unwired = {item["param_key"] for item in params if item["effect_status"] == "未接入"}
    assert {
        "complaint_accept_workdays",
        "complaint_feedback_workdays",
        "complaint_review_days",
        "cancellation_threshold_minutes",
        "max_concurrent_users",
        "retention_years",
        "query_response_seconds",
        "availability_target_percent",
        "backup_frequency_hours",
        "rto_hours",
        "rpo_hours",
        "max_booking_steps",
        "max_checkin_methods",
    } == unwired

    page = client.get("/sysadmin/params").get_data(as_text=True)
    assert "生效点" in page
    assert "未接入" in page
    assert "创建预约：同时有效预约上限校验" in page


def test_q33_seat_status_is_display_only_and_slot_conflict_rules(
    app, login_as, db_query, create_user
):
    seat_id = get_seat_id(db_query, "A-01")
    first = _login(app.test_client(), login_as, "246003384", "student123")
    created = first.post(
        "/api/reservations",
        json={
            "seat_id": seat_id,
            "reservation_date": "2026-10-17",
            "start_time": "09:00",
            "end_time": "11:00",
        },
    )
    assert created.status_code == 201
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "已预约"

    create_user("246003385", name="李小明")
    second = _login(app.test_client(), login_as, "246003385", "student123")
    later_slot = second.post(
        "/api/reservations",
        json={
            "seat_id": seat_id,
            "reservation_date": "2026-10-17",
            "start_time": "13:00",
            "end_time": "15:00",
        },
    )
    assert later_slot.status_code == 201
    assert db_query(
        "SELECT COUNT(*) AS n FROM reservations WHERE seat_id=?", (seat_id,)
    )[0]["n"] == 2


def test_q34_scan_promotes_at_checkin_window_start(
    app, login_as, db_query, clock
):
    student = _login(app.test_client(), login_as, "246003384", "student123")
    admin = _login(app.test_client(), login_as, "900000001", "admin123")
    seat_id = get_seat_id(db_query, "A-01")
    created = student.post(
        "/api/reservations",
        json={
            "seat_id": seat_id,
            "reservation_date": "2026-10-16",
            "start_time": "09:00",
            "end_time": "11:00",
        },
    )
    assert created.status_code == 201
    reservation_id = created.get_json()["reservation"]["id"]
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "待生效"

    clock.advance(minutes=15)  # 08:45，签到窗口起点
    scan = admin.post("/api/admin/scan")
    assert scan.status_code == 200
    assert scan.get_json()["scan"]["promoted_to_checkin"] >= 1
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "待签到"

    checkin = student.post(
        f"/api/reservations/{reservation_id}/checkin",
        json={"seat_code": "A-01", "method": "二维码"},
    )
    assert checkin.status_code == 200
    assert checkin.get_json()["checkin"]["reservation_status"] == "使用中"


def test_q35_single_violation_no_v1_v2_double_record(
    app, login_as, db_query, clock
):
    student = _login(app.test_client(), login_as, "246003384", "student123")
    admin = _login(app.test_client(), login_as, "900000001", "admin123")
    seat_id = get_seat_id(db_query, "A-01")
    created = student.post(
        "/api/reservations",
        json={
            "seat_id": seat_id,
            "reservation_date": "2026-10-16",
            "start_time": "09:00",
            "end_time": "10:00",
        },
    )
    assert created.status_code == 201
    reservation_id = created.get_json()["reservation"]["id"]

    clock.advance(minutes=46)  # 09:16，已过签到截止 09:15
    admin = _login(app.test_client(), login_as, "900000001", "admin123")
    first_scan = admin.post("/api/admin/scan")
    assert first_scan.status_code == 200
    assert first_scan.get_json()["scan"]["v1_created"] == 1
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "已违约"
    assert db_query("SELECT COUNT(*) AS n FROM violations")[0]["n"] == 1

    clock.advance(minutes=45)  # 10:01，已过预约结束时刻
    admin = _login(app.test_client(), login_as, "900000001", "admin123")
    second_scan = admin.post("/api/admin/scan")
    assert second_scan.status_code == 200
    assert second_scan.get_json()["scan"]["v2_created"] == 0
    assert db_query("SELECT COUNT(*) AS n FROM violations")[0]["n"] == 1
    assert db_query(
        "SELECT status FROM reservations WHERE id=?", (reservation_id,)
    )[0]["status"] == "已违约"


def test_v10_final_uses_independent_port_and_database(app):
    assert Config.PORT == 5012
    database = Path(Config.DATABASE)
    assert database.name == "app.db"
    assert database.parent.name == "data"
    assert database.parent.parent.name == "src"
    assert app.config["PORT"] == 5012
