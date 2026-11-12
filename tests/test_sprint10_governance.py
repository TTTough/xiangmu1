"""Sprint 10：用户信息、授权维护、阈值提醒、统计导出。"""
from __future__ import annotations

from sprint2_helpers import get_seat_id, get_user_id, make_reservation


def _login(client, login_as, student_no="246003384", password="student123"):
    response = login_as(client, student_no, password)
    assert response.status_code == 200, response.get_data(as_text=True)
    return client


def _sysadmin(app, login_as):
    return _login(app.test_client(), login_as, "900000002", "sysadmin123")


def _admin(app, login_as):
    return _login(app.test_client(), login_as, "900000001", "admin123")


def _student(app, login_as, student_no="246003384"):
    return _login(app.test_client(), login_as, student_no, "student123")


def _create_room_with_seat(sysadmin, code="R-GOV-2", seat_code="GOV-01"):
    room = sysadmin.post(
        "/api/admin/rooms",
        json={
            "code": code,
            "name": f"治理测试自习室 {code}",
            "building": "图书馆",
            "floor": "5 层",
            "open_from": "08:00",
            "open_to": "22:00",
            "status": "开放",
        },
    )
    assert room.status_code == 201, room.get_data(as_text=True)
    room_id = room.get_json()["room"]["id"]
    zone = sysadmin.post(
        f"/api/admin/rooms/{room_id}/zones",
        json={"code": "ZG", "name": "治理区", "zone_type": "静音区", "sort_order": 1},
    )
    assert zone.status_code == 201
    zone_id = zone.get_json()["zone"]["id"]
    seat = sysadmin.post(
        f"/api/admin/zones/{zone_id}/seats",
        json={"code": seat_code, "seat_type": "普通", "position": "测试"},
    )
    assert seat.status_code == 201
    return room_id, seat.get_json()["seat"]["id"], seat_code


# ---------------------------------------------------------------- 用户信息

def test_student_updates_own_contact_and_audits(app, login_as, db_query):
    student = _student(app, login_as)
    response = student.put("/api/me/contact", json={"contact": "new@example.edu"})
    assert response.status_code == 200
    assert response.get_json()["user"]["contact"] == "new@example.edu"
    assert db_query(
        "SELECT contact FROM users WHERE student_no='246003384'"
    )[0]["contact"] == "new@example.edu"
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='修改联系方式'"
    )[0]["n"] == 1


def test_contact_endpoint_rejects_immutable_fields(app, login_as, db_query):
    student = _student(app, login_as)
    response = student.put(
        "/api/me/contact",
        json={"contact": "x@example.edu", "student_no": "999999999"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "IMMUTABLE_FIELD"
    assert db_query(
        "SELECT student_no FROM users WHERE id=?", (get_user_id(db_query),)
    )[0]["student_no"] == "246003384"


def test_sysadmin_queries_users_with_masked_contact(app, login_as):
    sysadmin = _sysadmin(app, login_as)
    response = sysadmin.get("/api/system/users")
    assert response.status_code == 200
    data = response.get_json()
    assert data["pagination"]["total"] >= 4
    target = next(item for item in data["items"] if item["student_no"] == "246003384")
    assert target["contact_masked"] == "st***@example.edu"
    assert "contact" not in target
    page = sysadmin.get("/sysadmin/users")
    assert page.status_code == 200


def test_user_query_forbidden_for_admin_and_student(app, login_as):
    assert _admin(app, login_as).get("/api/system/users").status_code == 403
    assert _student(app, login_as).get("/api/system/users").status_code == 403


# ---------------------------------------------------------------- 授权维护

def test_grant_revoke_controls_resource_visibility(app, login_as, db_query):
    sysadmin = _sysadmin(app, login_as)
    admin = _admin(app, login_as)
    room_id, _seat_id, _seat_code = _create_room_with_seat(sysadmin)

    before = admin.get("/api/admin/resources").get_json()["rooms"]
    assert all(room["id"] != room_id for room in before)

    grant = sysadmin.post(
        "/api/system/admin-room-assignments",
        json={"admin_student_no": "900000001", "room_id": room_id},
    )
    assert grant.status_code == 201
    after = admin.get("/api/admin/resources").get_json()["rooms"]
    assert any(room["id"] == room_id for room in after)
    assert admin.get(f"/api/admin/realtime?room_id={room_id}").status_code == 200

    revoke = sysadmin.post(
        "/api/system/admin-room-assignments/revoke",
        json={"admin_student_no": "900000001", "room_id": room_id},
    )
    assert revoke.status_code == 200
    assert admin.get(f"/api/admin/realtime?room_id={room_id}").status_code == 403


def test_cross_room_access_forbidden_before_grant(app, login_as):
    sysadmin = _sysadmin(app, login_as)
    admin = _admin(app, login_as)
    room_id, _seat_id, _seat_code = _create_room_with_seat(sysadmin, "R-GOV-3", "GOV-03")
    assert admin.get(f"/api/admin/realtime?room_id={room_id}").status_code == 403
    assert admin.get(f"/api/admin/resources").status_code == 200


def test_assignment_grant_revoke_audited(app, login_as, db_query):
    sysadmin = _sysadmin(app, login_as)
    room_id, _seat_id, _seat_code = _create_room_with_seat(sysadmin, "R-GOV-4", "GOV-04")
    sysadmin.post(
        "/api/system/admin-room-assignments",
        json={"admin_student_no": "900000001", "room_id": room_id},
    )
    sysadmin.post(
        "/api/system/admin-room-assignments/revoke",
        json={"admin_student_no": "900000001", "room_id": room_id},
    )
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='授予管理员授权'"
    )[0]["n"] == 1
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='撤销管理员授权'"
    )[0]["n"] == 1


def test_complaint_scope_follows_room_assignment(app, login_as):
    sysadmin = _sysadmin(app, login_as)
    admin = _admin(app, login_as)
    room_id, _seat_id, seat_code = _create_room_with_seat(sysadmin, "R-GOV-5", "GOV-05")
    student = _student(app, login_as)
    complaint = student.post(
        "/api/complaints",
        json={
            "object_type": "座位或自习室",
            "object_ref": seat_code,
            "complaint_type": "环境问题",
            "content": "治理测试投诉",
        },
    )
    assert complaint.status_code == 201
    complaint_id = complaint.get_json()["complaint"]["id"]

    assert admin.post(f"/api/admin/complaints/{complaint_id}/accept").status_code == 403
    grant = sysadmin.post(
        "/api/system/admin-room-assignments",
        json={"admin_student_no": "900000001", "room_id": room_id},
    )
    assert grant.status_code == 201
    assert admin.post(f"/api/admin/complaints/{complaint_id}/accept").status_code == 200


# ---------------------------------------------------------------- 阈值提醒

def test_near_blacklist_reminder_sent_once_then_blacklist(
    app, login_as, db_query, db_execute, clock
):
    sysadmin = _sysadmin(app, login_as)
    admin = _admin(app, login_as)
    update = sysadmin.put(
        "/api/system/rule-params/blacklist_threshold", json={"value": 2}
    )
    assert update.status_code == 200
    user_id = get_user_id(db_query)
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "A-01"),
        status="待签到", start="08:00", end="10:00",
    )
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "A-02"),
        status="待签到", start="08:00", end="10:00",
    )
    scan = admin.post("/api/admin/scan")
    assert scan.status_code == 200
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND title='接近黑名单阈值'",
        (user_id,),
    )[0]["n"] == 1
    assert db_query(
        "SELECT account_status FROM users WHERE id=?", (user_id,)
    )[0]["account_status"] == "黑名单"

    admin.post("/api/admin/scan")
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND title='接近黑名单阈值'",
        (user_id,),
    )[0]["n"] == 1


# ---------------------------------------------------------------- 统计导出

def _export_data(client, **params):
    return client.get("/api/analytics/export", query_string=params)


def test_admin_exports_csv_without_personal_info(app, login_as, db_query):
    admin = _admin(app, login_as)
    student = _student(app, login_as)
    seat_id = get_seat_id(db_query, "A-01")
    assert student.post(
        "/api/reservations",
        json={
            "seat_id": seat_id,
            "reservation_date": "2026-10-16",
            "start_time": "09:00",
            "end_time": "11:00",
        },
    ).status_code == 201
    response = _export_data(
        admin, date_from="2026-10-10", date_to="2026-10-16"
    )
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    text = response.get_data(as_text=True)
    assert "自习室,预约量,违约量" in text
    assert "杨子涵" not in text
    assert "246003384" not in text
    assert "example.edu" not in text
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='统计导出'"
    )[0]["n"] == 1


def test_sysadmin_and_logistics_can_export(app, login_as):
    params = {"date_from": "2026-10-10", "date_to": "2026-10-16"}
    assert _export_data(_sysadmin(app, login_as), **params).status_code == 200
    logistics = _login(app.test_client(), login_as, "900000003", "logistics123")
    assert _export_data(logistics, **params).status_code == 200


def test_student_cannot_export(app, login_as):
    response = _export_data(
        _student(app, login_as), date_from="2026-10-10", date_to="2026-10-16"
    )
    assert response.status_code == 403


def test_export_room_filter_and_scope(app, login_as, db_query):
    sysadmin = _sysadmin(app, login_as)
    admin = _admin(app, login_as)
    room_id, _seat_id, _seat_code = _create_room_with_seat(sysadmin, "R-GOV-6", "GOV-06")
    # 管理员未授权该自习室，按该室导出应被拒绝。
    response = _export_data(
        admin,
        date_from="2026-10-10",
        date_to="2026-10-16",
        room_id=room_id,
    )
    assert response.status_code == 403
    sysadmin_export = _export_data(
        sysadmin, date_from="2026-10-10", date_to="2026-10-16", room_id=room_id
    )
    assert sysadmin_export.status_code == 200


def test_sysadmin_user_query_filters_and_pagination(app, login_as):
    sysadmin = _sysadmin(app, login_as)
    response = sysadmin.get(
        "/api/system/users", query_string={"role": "student", "page_size": 1}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["role"] == "student"
    assert data["pagination"]["page_size"] == 1
    assert data["pagination"]["total"] >= 1


def test_assignment_duplicate_rejected(app, login_as):
    sysadmin = _sysadmin(app, login_as)
    room_id, _seat_id, _seat_code = _create_room_with_seat(sysadmin, "R-GOV-7", "GOV-07")
    payload = {"admin_student_no": "900000001", "room_id": room_id}
    assert sysadmin.post("/api/system/admin-room-assignments", json=payload).status_code == 201
    duplicate = sysadmin.post("/api/system/admin-room-assignments", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "ASSIGNMENT_EXISTS"


def test_contact_requires_non_empty(app, login_as):
    student = _student(app, login_as)
    response = student.put("/api/me/contact", json={"contact": "  "})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MISSING_FIELD"


def test_assignments_page_renders(app, login_as):
    sysadmin = _sysadmin(app, login_as)
    page = sysadmin.get("/sysadmin/assignments")
    assert page.status_code == 200
    assert "管理员授权维护" in page.get_data(as_text=True)


def test_export_contains_stats_rows(app, login_as):
    admin = _admin(app, login_as)
    response = _export_data(admin, date_from="2026-10-10", date_to="2026-10-16")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "统计指标,数值" in text
    assert "当前空闲座位" in text
