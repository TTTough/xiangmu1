"""AC-09-01—AC-09-06：投诉提交、受理反馈、复核一次、超时关闭与脱敏。"""
from __future__ import annotations


def _admin_login(client, login_as):
    assert login_as(client, "900000001", "admin123").status_code == 200


def _submit_complaint(client, student_no="246003385"):
    return client.post(
        "/api/complaints",
        json={
            "object_type": "其他用户",
            "complained_student_no": student_no,
            "complaint_type": "占座纠纷",
            "object_ref": "A-01",
            "content": "对方长时间放置物品但未使用座位。",
            "evidence_attachment": "现场照片.jpg",
        },
    )


def _prepare_replied_complaint(app, login_as, db_query):
    student = app.test_client()
    admin = app.test_client()
    assert login_as(student).status_code == 200
    _admin_login(admin, login_as)
    complaint = _submit_complaint(student).get_json()["complaint"]
    accepted = admin.post(f"/api/admin/complaints/{complaint['id']}/accept", json={})
    assert accepted.status_code == 200
    feedback = admin.post(
        f"/api/admin/complaints/{complaint['id']}/feedback",
        json={"feedback": "已核实并提醒对方遵守座位使用规则。"},
    )
    assert feedback.status_code == 200
    return student, admin, complaint["id"]


def test_ac_09_01_student_submits_complaint_and_admin_notified(
    client, login_as, db_query, create_user
):
    create_user("246003385", name="李小明")
    assert login_as(client).status_code == 200
    response = _submit_complaint(client)
    assert response.status_code == 201
    complaint = response.get_json()["complaint"]
    assert complaint["status"] == "待受理"
    assert complaint["complained_user"]["name_masked"] == "李**"
    assert db_query(
        "SELECT status, complaint_type FROM complaints WHERE id=?", (complaint["id"],)
    )[0] == {"status": "待受理", "complaint_type": "占座纠纷"}
    admin_id = db_query("SELECT id FROM users WHERE student_no='900000001'")[0]["id"]
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND notification_type='投诉受理'",
        (admin_id,),
    )[0]["n"] == 1


def test_ac_09_02_unauthenticated_complaint_rejected(client, db_query):
    response = client.post(
        "/api/complaints",
        json={"object_type": "其他用户", "complaint_type": "测试", "content": "未登录"},
    )
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHORIZED"
    assert db_query("SELECT COUNT(*) AS n FROM complaints")[0]["n"] == 0


def test_ac_09_03_admin_accepts_and_feedback_visible_to_student(
    app, login_as, db_query, create_user
):
    create_user("246003385", name="李小明")
    student, admin, complaint_id = _prepare_replied_complaint(app, login_as, db_query)
    detail = student.get(f"/api/complaints/{complaint_id}")
    assert detail.status_code == 200
    complaint = detail.get_json()["complaint"]
    assert complaint["status"] == "已回复"
    assert complaint["feedback"] == "已核实并提醒对方遵守座位使用规则。"
    assert complaint["feedback_at"] is not None
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE user_id=(SELECT id FROM users WHERE student_no='246003384') "
        "AND notification_type='投诉进度'"
    )[0]["n"] >= 2


def test_ac_09_04_review_only_once(app, login_as, db_query, create_user):
    create_user("246003385", name="李小明")
    student, _admin, complaint_id = _prepare_replied_complaint(app, login_as, db_query)

    first = student.post(f"/api/complaints/{complaint_id}/review")
    assert first.status_code == 200
    complaint = first.get_json()["complaint"]
    assert complaint["status"] == "处理中"
    assert complaint["review_used"] is True

    second = student.post(f"/api/complaints/{complaint_id}/review")
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "INVALID_COMPLAINT_STATUS"


def test_ac_09_05_timeout_auto_closes_and_notifies(
    app, login_as, db_query, db_execute, create_user, clock
):
    create_user("246003385", name="李小明")
    _student, admin, complaint_id = _prepare_replied_complaint(app, login_as, db_query)
    db_execute(
        "UPDATE complaints SET feedback_at='2026-10-10 08:30:00' WHERE id=?",
        (complaint_id,),
    )
    scan = admin.post("/api/admin/scan")
    assert scan.status_code == 200
    assert scan.get_json()["scan"]["complaints_auto_closed"] == 1
    stored = db_query(
        "SELECT status, closed_at, close_reason FROM complaints WHERE id=?", (complaint_id,)
    )[0]
    assert stored["status"] == "已关闭"
    assert stored["closed_at"] is not None
    assert "自动关闭" in stored["close_reason"]
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE notification_type='投诉进度' AND title='投诉已自动关闭'"
    )[0]["n"] == 1


def test_ac_09_06_complained_student_masked_for_complainant(
    client, login_as, db_query, create_user
):
    create_user("246003385", name="李小明")
    assert login_as(client).status_code == 200
    complaint = _submit_complaint(client).get_json()["complaint"]
    detail = client.get(f"/api/complaints/{complaint['id']}")
    assert detail.status_code == 200
    complained = detail.get_json()["complaint"]["complained_user"]
    assert complained["name_masked"] == "李**"
    assert complained["student_no_masked"] == "246***385"
    assert complained["contact_masked"] == "te***@example.edu"
    body = detail.get_data(as_text=True)
    assert "李小明" not in body
    assert "test@example.edu" not in body
