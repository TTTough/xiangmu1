"""AC-08-01—AC-08-04：评价真实使用、重复拒绝、隐藏与聚合。"""
from __future__ import annotations

from sprint2_helpers import get_seat_id, get_user_id, make_reservation


def _completed_reservation(db_query, db_execute, user_id, seat_id, date="2026-10-15"):
    return make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="已完成", reservation_date=date, start="08:00", end="10:00"
    )


def test_ac_08_01_evaluation_requires_real_completed_use(
    client, login_as, db_query
):
    login_as(client)
    seat_id = get_seat_id(db_query, "A-01")
    response = client.post(
        "/api/evaluations",
        json={"target_type": "座位", "target_id": seat_id, "rating": 5, "comment": "不错"},
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "REAL_USE_REQUIRED"
    assert db_query("SELECT COUNT(*) AS n FROM evaluations")[0]["n"] == 0


def test_ac_08_02_duplicate_evaluation_rejected(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query, "A-01")
    _completed_reservation(db_query, db_execute, user_id, seat_id)
    login_as(client)

    first = client.post(
        "/api/evaluations",
        json={"target_type": "座位", "target_id": seat_id, "rating": 5, "comment": "很好"},
    )
    assert first.status_code == 201
    original_id = first.get_json()["evaluation"]["id"]

    second = client.post(
        "/api/evaluations",
        json={"target_type": "座位", "target_id": seat_id, "rating": 1, "comment": "改差评"},
    )
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "ALREADY_EVALUATED"
    stored = db_query("SELECT id, rating, comment FROM evaluations WHERE id=?", (original_id,))[0]
    assert stored == {"id": original_id, "rating": 5, "comment": "很好"}


def test_ac_08_03_hide_requires_reason_and_audits(
    app, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query, "A-01")
    _completed_reservation(db_query, db_execute, user_id, seat_id)
    student = app.test_client()
    admin = app.test_client()
    login_as(student)
    evaluation = student.post(
        "/api/evaluations",
        json={"target_type": "座位", "target_id": seat_id, "rating": 2, "comment": "环境嘈杂"},
    ).get_json()["evaluation"]
    assert login_as(admin, "900000001", "admin123").status_code == 200

    no_reason = admin.post(f"/api/admin/evaluations/{evaluation['id']}/hide", json={})
    assert no_reason.status_code == 400
    assert db_query(
        "SELECT hidden FROM evaluations WHERE id=?", (evaluation["id"],)
    )[0]["hidden"] == 0

    hidden = admin.post(
        f"/api/admin/evaluations/{evaluation['id']}/hide",
        json={"reason": "包含不文明用语"},
    )
    assert hidden.status_code == 200
    stored = db_query(
        "SELECT hidden, hidden_reason, hidden_by FROM evaluations WHERE id=?",
        (evaluation["id"],),
    )[0]
    assert stored["hidden"] == 1
    assert stored["hidden_reason"] == "包含不文明用语"
    assert stored["hidden_by"] is not None
    audit = db_query(
        "SELECT actor_name, after_json FROM audit_logs WHERE action='隐藏评价' ORDER BY id DESC LIMIT 1"
    )[0]
    assert audit["actor_name"] == "自习室管理员"
    assert "包含不文明用语" in audit["after_json"]


def test_ac_08_04_average_excludes_hidden(client, login_as, db_query, db_execute, create_user):
    user1 = get_user_id(db_query)
    user2 = create_user("246003385", name="李小明")
    user3 = create_user("246003386", name="王小红")
    seat_id = get_seat_id(db_query, "A-01")
    for user_id in (user1, user2, user3):
        _completed_reservation(db_query, db_execute, user_id, seat_id)
    evaluations = [(user1, 5, 0), (user2, 4, 0), (user3, 1, 1)]
    for index, (user_id, rating, hidden) in enumerate(evaluations, start=1):
        db_execute(
            """
            INSERT INTO evaluations
                (evaluation_no, user_id, target_type, target_id, rating,
                 comment, submitted_at, hidden, hidden_reason, hidden_at)
            VALUES (?, ?, '座位', ?, ?, ?, '2026-10-15 10:00:00', ?, ?, ?)
            """,
            (
                f"E-TEST-{index}", user_id, seat_id, rating, f"评分{rating}", hidden,
                "违规内容" if hidden else None,
                "2026-10-15 11:00:00" if hidden else None,
            ),
        )
    login_as(client)
    response = client.get(
        "/api/evaluations/summary",
        query_string={"target_type": "座位", "target_id": seat_id},
    )
    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["evaluation_count"] == 2
    assert summary["average_rating"] == 4.5
    assert summary["target_label"] == "A-01"
