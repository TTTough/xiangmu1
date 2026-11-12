"""AC-04-01、AC-04-02：开始前取消、开始后拒绝；审计与参数溯源基础。"""
from __future__ import annotations

from conftest import make_booking


def _create_booking(client, db_query):
    seat_id = db_query("SELECT id FROM seats WHERE code='A-01'")[0]["id"]
    response = client.post(
        "/api/reservations",
        json=make_booking(seat_id, "2026-10-17", "09:00", "11:00"),
    )
    assert response.status_code == 201
    return seat_id, response.get_json()["reservation"]["id"]


def test_ac_04_01_cancel_before_start_releases_seat_without_violation(
    client, login_as, db_query
):
    login_as(client)
    seat_id, reservation_id = _create_booking(client, db_query)

    response = client.post(f"/api/reservations/{reservation_id}/cancel")
    assert response.status_code == 200
    body = response.get_json()["reservation"]
    assert body["status"] == "已取消"
    assert body["violation_created"] is False

    stored = db_query(
        "SELECT status, cancelled_at FROM reservations WHERE id=?", (reservation_id,)
    )[0]
    assert stored["status"] == "已取消"
    assert stored["cancelled_at"] is not None
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "空闲"
    assert db_query("SELECT COUNT(*) AS n FROM violations")[0]["n"] == 0
    assert db_query(
        "SELECT result FROM audit_logs WHERE action='取消预约' ORDER BY id DESC LIMIT 1"
    )[0]["result"] == "成功"


def test_ac_04_02_cancel_after_start_rejected_and_state_unchanged(
    client, login_as, db_query, db_execute
):
    login_as(client)
    seat_id, reservation_id = _create_booking(client, db_query)

    # 模拟系统时间推进到预约开始后：预约单已由待生效推进为待签到。
    db_execute(
        """
        UPDATE reservations
           SET reservation_date='2026-10-16', start_time='08:00', end_time='10:00',
               status='待签到'
         WHERE id=?
        """,
        (reservation_id,),
    )

    response = client.post(f"/api/reservations/{reservation_id}/cancel")
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "CANCEL_WINDOW_CLOSED"
    assert "已过可取消时间" in error["message"]

    assert db_query(
        "SELECT status, cancelled_at FROM reservations WHERE id=?", (reservation_id,)
    )[0] == {"status": "待签到", "cancelled_at": None}
    assert db_query("SELECT status FROM seats WHERE id=?", (seat_id,))[0]["status"] == "已预约"


def test_audit_required_fields_for_sprint1_actions(client, login_as, db_query):
    """AC-14-01/AC-14-02 的字段基础：登录、预约、取消均含前后值与操作人。"""
    login_as(client)
    _seat_id, reservation_id = _create_booking(client, db_query)
    assert client.post(f"/api/reservations/{reservation_id}/cancel").status_code == 200

    rows = db_query(
        """
        SELECT action, actor_name, actor_role, target_type, target_id,
               before_json, after_json, result, created_at
          FROM audit_logs
         WHERE action IN ('登录', '提交预约', '取消预约')
         ORDER BY id
        """
    )
    actions = {row["action"] for row in rows}
    assert actions == {"登录", "提交预约", "取消预约"}
    for row in rows:
        assert row["actor_name"]
        assert row["actor_role"]
        assert row["target_type"]
        assert row["target_id"]
        assert row["before_json"] is not None
        assert row["after_json"] is not None
        assert row["result"]
        assert row["created_at"]


def test_rule_params_seeded_with_provenance(db_query):
    """附录 A 参数落库，保留来源性质、确认状态与关联规则。"""
    rows = db_query("SELECT * FROM rule_params ORDER BY param_no")
    assert len(rows) == 28
    assert [row["param_no"] for row in rows][0] == "P-01"
    assert [row["param_no"] for row in rows][-1] == "P-28"
    for row in rows:
        assert row["source_nature"]
        assert row["confirmation_status"]
        assert row["value"]
    by_key = {row["param_key"]: row for row in rows}
    assert by_key["max_active_reservations"]["value"] == "1"
    assert by_key["max_active_reservations"]["confirmation_status"] == "教学模拟已确认（2026-10-29）"
    assert by_key["login_lock_threshold"]["value"] == "5"
    assert by_key["lock_duration_minutes"]["value"] == "15"
