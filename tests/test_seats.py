"""AC-06-01：座位多条件筛选与当前状态/可预约时段标注。"""
from __future__ import annotations

from conftest import make_booking


def test_ac_06_01_filter_multiple_rooms_and_annotate_availability(
    client, login_as, db_execute
):
    room_id = db_execute(
        """
        INSERT INTO rooms
            (code, name, building, floor, location, open_from, open_to,
             status, note, created_at)
        VALUES ('R-JG-2F', '经管楼二层自习室', '经管楼', '2 层', '东侧',
                '08:00', '22:00', '开放', 'AC-06-01 测试夹具', '2026-10-16 08:30:00')
        """
    )
    zone_id = db_execute(
        """
        INSERT INTO zones (room_id, code, name, zone_type, sort_order)
        VALUES (?, 'Z-JG-1', '经管讨论区', '讨论区', 1)
        """,
        (room_id,),
    )
    target_seat_id = db_execute(
        """
        INSERT INTO seats
            (code, room_id, zone_id, seat_type, status, position, is_bookable, created_at)
        VALUES ('J-01', ?, ?, '靠窗', '空闲', '窗边 1 号', 1, '2026-10-16 08:30:00')
        """,
        (room_id, zone_id),
    )
    db_execute(
        """
        INSERT INTO seats
            (code, room_id, zone_id, seat_type, status, position, is_bookable, created_at)
        VALUES ('J-02', ?, ?, '普通', '空闲', '中间 1 号', 1, '2026-10-16 08:30:00')
        """,
        (room_id, zone_id),
    )

    assert login_as(client).status_code == 200
    url = (
        "/api/seats?building=经管楼&zone_type=讨论区"
        "&date=2026-10-17&start=09:00&end=11:00&seat_type=靠窗"
    )
    response = client.get(url)
    assert response.status_code == 200
    body = response.get_json()
    assert body["count"] == 1
    seat = body["seats"][0]
    assert seat["code"] == "J-01"
    assert seat["current_status"] == "空闲"
    assert seat["available_for_slot"] is True
    assert any(
        item["start"] == "08:00" and item["end"] == "22:00"
        for item in seat["available_slots"]
    )

    booked = client.post(
        "/api/reservations",
        json=make_booking(target_seat_id, "2026-10-17", "09:00", "11:00"),
    )
    assert booked.status_code == 201

    after = client.get(url).get_json()
    assert after["count"] == 1
    assert after["seats"][0]["current_status"] == "已预约"
    assert after["seats"][0]["available_for_slot"] is False
    assert all(
        not (item["start"] < "11:00" and "09:00" < item["end"])
        for item in after["seats"][0]["available_slots"]
    )
