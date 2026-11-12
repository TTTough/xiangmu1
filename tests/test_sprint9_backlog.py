"""Sprint 9：参数补种、投诉关闭路径、黑名单直接加入/延期、管理员代创建。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from app import create_app
from sprint2_helpers import get_seat_id, get_user_id


def _login(client, login_as, student_no="246003384", password="student123"):
    response = login_as(client, student_no, password)
    assert response.status_code == 200, response.get_data(as_text=True)
    return client


def _admin(app, login_as):
    return _login(app.test_client(), login_as, "900000001", "admin123")


def _sysadmin(app, login_as):
    return _login(app.test_client(), login_as, "900000002", "sysadmin123")


def _student(app, login_as, student_no="246003384"):
    return _login(app.test_client(), login_as, student_no, "student123")


def _submit_complaint(client, content="Sprint 9 投诉"):
    response = client.post(
        "/api/complaints",
        json={
            "object_type": "座位或自习室",
            "object_ref": "A-01",
            "complaint_type": "环境问题",
            "content": content,
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["complaint"]["id"]


def _proxy_payload(seat_id, student_no="246003384", reason="学生无法自行操作"):
    return {
        "student_no": student_no,
        "seat_id": seat_id,
        "reservation_date": "2026-10-17",
        "start_time": "09:00",
        "end_time": "11:00",
        "reason": reason,
    }


# ---------------------------------------------------------------- ADR-06 补种

def test_adr06_seed_replenishes_missing_params_without_overwrite(tmp_path):
    database = str(tmp_path / "old.db")
    config = {
        "TESTING": True,
        "DATABASE": database,
        "SECRET_KEY": "test",
        "ENABLE_SCHEDULER": False,
    }
    create_app(config)
    conn = sqlite3.connect(database)
    try:
        conn.execute("DELETE FROM rule_params WHERE param_no='P-10'")
        conn.execute("UPDATE rule_params SET value='2' WHERE param_no='P-01'")
        conn.commit()
    finally:
        conn.close()

    create_app(config)
    conn = sqlite3.connect(database)
    try:
        count = conn.execute("SELECT COUNT(*) FROM rule_params").fetchone()[0]
        p10 = conn.execute(
            "SELECT value FROM rule_params WHERE param_no='P-10'"
        ).fetchone()
        p01 = conn.execute(
            "SELECT value FROM rule_params WHERE param_no='P-01'"
        ).fetchone()
    finally:
        conn.close()
    assert count == 28
    assert p10 is not None and p10[0] == "2"
    assert p01 is not None and p01[0] == "2"


# ---------------------------------------------------------------- 管理员代创建

def test_admin_proxy_creates_for_student_and_audits(app, login_as, db_query):
    admin = _admin(app, login_as)
    response = admin.post(
        "/api/admin/reservations", json=_proxy_payload(get_seat_id(db_query, "A-01"))
    )
    assert response.status_code == 201
    reservation = response.get_json()["reservation"]
    assert reservation["source"] == "管理员代创建"
    assert reservation["admin_reason"] == "学生无法自行操作"
    assert reservation["student_no"] == "246003384"

    row = db_query(
        "SELECT source, created_by, admin_reason FROM reservations WHERE id=?",
        (reservation["id"],),
    )[0]
    assert row["source"] == "管理员代创建"
    assert row["created_by"] == get_user_id(db_query, "900000001")
    assert row["admin_reason"] == "学生无法自行操作"
    audit = db_query(
        "SELECT * FROM audit_logs WHERE action='管理员代创建预约' ORDER BY id DESC"
    )
    assert audit and audit[0]["target_id"] == reservation["reservation_no"]


def test_proxy_reservation_visible_only_to_target_student(
    app, login_as, db_query, create_user
):
    admin = _admin(app, login_as)
    response = admin.post(
        "/api/admin/reservations", json=_proxy_payload(get_seat_id(db_query, "A-01"))
    )
    assert response.status_code == 201
    reservation_no = response.get_json()["reservation"]["reservation_no"]

    target = _student(app, login_as, "246003384")
    my = target.get("/api/reservations/my").get_json()["reservations"]
    assert any(item["reservation_no"] == reservation_no for item in my)

    create_user("246003385", name="另一学生")
    other = _student(app, login_as, "246003385")
    other_my = other.get("/api/reservations/my").get_json()["reservations"]
    assert all(item["reservation_no"] != reservation_no for item in other_my)


def test_admin_proxy_requires_reason(app, login_as, db_query):
    admin = _admin(app, login_as)
    payload = _proxy_payload(get_seat_id(db_query, "A-01"), reason="")
    response = admin.post("/api/admin/reservations", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MISSING_FIELD"


def test_admin_proxy_forbidden_for_sysadmin_and_student(app, login_as, db_query):
    payload = _proxy_payload(get_seat_id(db_query, "A-01"))
    assert _sysadmin(app, login_as).post(
        "/api/admin/reservations", json=payload
    ).status_code == 403
    assert _student(app, login_as).post(
        "/api/admin/reservations", json=payload
    ).status_code == 403


# ---------------------------------------------------------------- 投诉关闭路径

def test_complaint_reject_closes_and_notifies(app, login_as, db_query):
    student = _student(app, login_as)
    complaint_id = _submit_complaint(student)
    admin = _admin(app, login_as)
    response = admin.post(
        f"/api/admin/complaints/{complaint_id}/reject",
        json={"reason": "经核实内容不成立"},
    )
    assert response.status_code == 200
    complaint = response.get_json()["complaint"]
    assert complaint["status"] == "已关闭"
    assert complaint["close_reason"] == "经核实内容不成立"
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='投诉驳回'"
    )[0]["n"] == 1
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND title='投诉已关闭'",
        (get_user_id(db_query),),
    )[0]["n"] == 1

    again = admin.post(
        f"/api/admin/complaints/{complaint_id}/reject",
        json={"reason": "重复驳回"},
    )
    assert again.status_code == 409


def test_complaint_reject_requires_reason_and_allows_sysadmin(app, login_as):
    student = _student(app, login_as)
    complaint_id = _submit_complaint(student)
    sysadmin = _sysadmin(app, login_as)
    missing = sysadmin.post(
        f"/api/admin/complaints/{complaint_id}/reject", json={"reason": ""}
    )
    assert missing.status_code == 400
    ok = sysadmin.post(
        f"/api/admin/complaints/{complaint_id}/reject",
        json={"reason": "系统管理员核实重复投诉"},
    )
    assert ok.status_code == 200
    assert ok.get_json()["complaint"]["status"] == "已关闭"


def test_complaint_confirm_closes_and_audits(app, login_as, db_query):
    student = _student(app, login_as)
    complaint_id = _submit_complaint(student)
    admin = _admin(app, login_as)
    assert admin.post(f"/api/admin/complaints/{complaint_id}/accept").status_code == 200
    assert admin.post(
        f"/api/admin/complaints/{complaint_id}/feedback",
        json={"feedback": "已处理并反馈"},
    ).status_code == 200

    response = student.post(f"/api/complaints/{complaint_id}/confirm")
    assert response.status_code == 200
    complaint = response.get_json()["complaint"]
    assert complaint["status"] == "已关闭"
    assert complaint["close_reason"] == "投诉人确认反馈"
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='投诉确认关闭'"
    )[0]["n"] == 1
    again = student.post(f"/api/complaints/{complaint_id}/confirm")
    assert again.status_code == 409


def test_complaint_confirm_only_owner(app, login_as, db_query, create_user):
    student = _student(app, login_as)
    complaint_id = _submit_complaint(student)
    admin = _admin(app, login_as)
    admin.post(f"/api/admin/complaints/{complaint_id}/accept")
    admin.post(
        f"/api/admin/complaints/{complaint_id}/feedback",
        json={"feedback": "已反馈"},
    )
    create_user("246003385", name="非投诉人")
    other = _student(app, login_as, "246003385")
    assert other.post(f"/api/complaints/{complaint_id}/confirm").status_code == 403


# ---------------------------------------------------------------- 黑名单直接加入/延期

def test_blacklist_direct_add_and_extend(app, login_as, db_query, create_user, clock):
    create_user("246003385", name="黑名单学生")
    admin = _admin(app, login_as)
    added = admin.post(
        "/api/admin/blacklists",
        json={"student_no": "246003385", "reason": "现场严重违规", "days": 10},
    )
    assert added.status_code == 201
    record = added.get_json()["blacklist"]
    old_expiry = datetime.strptime(record["expires_at"], "%Y-%m-%d %H:%M:%S")
    assert record["status"] == "生效中"
    assert (old_expiry - clock.value).days == 10
    assert db_query(
        "SELECT account_status FROM users WHERE student_no='246003385'"
    )[0]["account_status"] == "黑名单"
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='管理员加入黑名单'"
    )[0]["n"] == 1

    extended = admin.post(
        f"/api/admin/blacklists/{record['id']}/extend",
        json={"reason": "违规事实加重", "days": 5},
    )
    assert extended.status_code == 200
    body = extended.get_json()["blacklist"]
    new_expiry = datetime.strptime(body["expires_at"], "%Y-%m-%d %H:%M:%S")
    assert new_expiry == old_expiry + timedelta(days=5)
    assert db_query(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action='黑名单延期'"
    )[0]["n"] == 1
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND title='黑名单生效通知'",
        (get_user_id(db_query, "246003385"),),
    )[0]["n"] == 1


def test_blacklist_direct_add_requires_days_and_reason(app, login_as, create_user):
    create_user("246003385", name="黑名单学生")
    admin = _admin(app, login_as)
    no_days = admin.post(
        "/api/admin/blacklists",
        json={"student_no": "246003385", "reason": "违规"},
    )
    assert no_days.status_code == 400
    assert no_days.get_json()["error"]["code"] == "MISSING_FIELD"
    no_reason = admin.post(
        "/api/admin/blacklists",
        json={"student_no": "246003385", "days": 7},
    )
    assert no_reason.status_code == 400


def test_sysadmin_can_add_and_extend_blacklist(app, login_as, create_user):
    create_user("246003386", name="系统管理员操作学生")
    sysadmin = _sysadmin(app, login_as)
    added = sysadmin.post(
        "/api/admin/blacklists",
        json={"student_no": "246003386", "reason": "矩阵第 21 行", "days": 3},
    )
    assert added.status_code == 201
    record = added.get_json()["blacklist"]
    extended = sysadmin.post(
        f"/api/admin/blacklists/{record['id']}/extend",
        json={"reason": "延长测试", "days": 2},
    )
    assert extended.status_code == 200


def test_blacklist_duplicate_active_rejected(app, login_as, create_user):
    create_user("246003385", name="黑名单学生")
    admin = _admin(app, login_as)
    payload = {"student_no": "246003385", "reason": "首次加入", "days": 7}
    assert admin.post("/api/admin/blacklists", json=payload).status_code == 201
    duplicate = admin.post("/api/admin/blacklists", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "BLACKLIST_ALREADY_ACTIVE"


def test_blacklist_extend_requires_reason_and_active(app, login_as, create_user):
    create_user("246003385", name="黑名单学生")
    admin = _admin(app, login_as)
    added = admin.post(
        "/api/admin/blacklists",
        json={"student_no": "246003385", "reason": "首次加入", "days": 5},
    )
    assert added.status_code == 201
    record = added.get_json()["blacklist"]
    missing = admin.post(
        f"/api/admin/blacklists/{record['id']}/extend", json={"days": 3}
    )
    assert missing.status_code == 400
    assert admin.post(
        f"/api/admin/blacklists/{record['id']}/release",
        json={"reason": "提前解除"},
    ).status_code == 200
    closed = admin.post(
        f"/api/admin/blacklists/{record['id']}/extend",
        json={"reason": "解除后延期", "days": 3},
    )
    assert closed.status_code == 409
    assert closed.get_json()["error"]["code"] == "BLACKLIST_NOT_ACTIVE"


def test_admin_proxy_reuses_student_validation(app, login_as, db_query):
    admin = _admin(app, login_as)
    too_long = _proxy_payload(get_seat_id(db_query, "A-01"))
    too_long["end_time"] = "15:00"
    response = admin.post("/api/admin/reservations", json=too_long)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "DURATION_OUT_OF_RANGE"

    added = admin.post(
        "/api/admin/blacklists",
        json={"student_no": "246003384", "reason": "测试黑名单代创建", "days": 3},
    )
    assert added.status_code == 201
    blocked = admin.post(
        "/api/admin/reservations", json=_proxy_payload(get_seat_id(db_query, "A-02"))
    )
    assert blocked.status_code == 409
    assert blocked.get_json()["error"]["code"] == "BLACKLISTED"


def test_complaint_confirm_notifies_admin(app, login_as, db_query):
    student = _student(app, login_as)
    complaint_id = _submit_complaint(student)
    admin = _admin(app, login_as)
    admin.post(f"/api/admin/complaints/{complaint_id}/accept")
    admin.post(
        f"/api/admin/complaints/{complaint_id}/feedback",
        json={"feedback": "已处理"},
    )
    assert student.post(f"/api/complaints/{complaint_id}/confirm").status_code == 200
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND title='投诉已确认关闭'",
        (get_user_id(db_query, "900000001"),),
    )[0]["n"] == 1
