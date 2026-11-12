"""AC-12-01—AC-12-03：通知事件覆盖、不可删除与送达记录。"""
from __future__ import annotations

import sqlite3

import pytest

from conftest import make_booking
from sprint2_helpers import (
    get_seat_id,
    get_user_id,
    make_reservation,
    set_user_count,
)


def _admin_login(client, login_as):
    assert login_as(client, "900000001", "admin123").status_code == 200


def _create_complaint(client, student_no="246003385"):
    return client.post(
        "/api/complaints",
        json={
            "object_type": "其他用户",
            "complained_student_no": student_no,
            "complaint_type": "占座纠纷",
            "content": "通知事件测试投诉",
        },
    )


def test_ac_12_01_events_create_categorized_notifications(
    app, login_as, db_query, db_execute, create_user
):
    create_user("246003385", name="李小明")
    student = app.test_client()
    admin = app.test_client()
    assert login_as(student).status_code == 200
    user_id = get_user_id(db_query)

    # 预约成功通知
    created = student.post(
        "/api/reservations",
        json=make_booking(get_seat_id(db_query, "A-03"), "2026-10-17", "09:00", "11:00"),
    )
    assert created.status_code == 201

    # 预约开始/签到截止提醒 + 违约通知 + 黑名单通知
    set_user_count(db_execute, user_id, 2)
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "A-04"),
        status="待生效", start="08:30", end="10:30"
    )
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "B-01"),
        status="待签到", start="08:00", end="10:00"
    )
    _admin_login(admin, login_as)
    scan = admin.post("/api/admin/scan")
    assert scan.status_code == 200

    # 投诉反馈通知
    complaint = _create_complaint(student)
    assert complaint.status_code == 201
    complaint_id = complaint.get_json()["complaint"]["id"]
    assert admin.post(f"/api/admin/complaints/{complaint_id}/accept", json={}).status_code == 200
    assert admin.post(
        f"/api/admin/complaints/{complaint_id}/feedback",
        json={"feedback": "已核实并处理"},
    ).status_code == 200

    notifications = student.get("/api/notifications?page_size=100").get_json()["notifications"]
    types = {item["notification_type"] for item in notifications}
    assert {"预约成功", "预约提醒", "签到提醒", "违约记录", "黑名单状态", "投诉进度"}.issubset(types)
    assert all(item["delivery_result"] == "系统内消息已送达" for item in notifications)


def test_ac_12_02_notifications_can_be_read_but_not_deleted(
    client, login_as, db_query, db_execute
):
    assert login_as(client).status_code == 200
    created = client.post(
        "/api/reservations",
        json=make_booking(get_seat_id(db_query, "A-01"), "2026-10-17", "09:00", "11:00"),
    )
    assert created.status_code == 201
    notification = client.get("/api/notifications?page_size=20").get_json()["notifications"][0]
    notification_id = notification["id"]

    marked = client.post(f"/api/notifications/{notification_id}/read")
    assert marked.status_code == 200
    assert marked.get_json()["notification"]["is_read"] is True
    assert db_query(
        "SELECT read_at FROM notifications WHERE id=?", (notification_id,)
    )[0]["read_at"] is not None

    delete_response = client.delete(f"/api/notifications/{notification_id}")
    assert delete_response.status_code == 403
    assert delete_response.get_json()["error"]["code"] == "NOTIFICATION_IMMUTABLE"
    assert db_query(
        "SELECT COUNT(*) AS n FROM notifications WHERE id=?", (notification_id,)
    )[0]["n"] == 1
    with pytest.raises(sqlite3.IntegrityError):
        db_execute("DELETE FROM notifications WHERE id=?", (notification_id,))


def test_ac_12_03_notification_list_includes_delivery_record(client, login_as, db_query):
    assert login_as(client).status_code == 200
    assert client.post(
        "/api/reservations",
        json=make_booking(get_seat_id(db_query, "A-01"), "2026-10-17", "09:00", "11:00"),
    ).status_code == 201
    response = client.get("/api/notifications")
    assert response.status_code == 200
    item = response.get_json()["notifications"][0]
    assert item["created_at"] == "2026-10-16 08:30:00"
    assert item["delivery_result"] == "系统内消息已送达"
    assert item["is_read"] is False
