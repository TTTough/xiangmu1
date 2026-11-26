"""Sprint 3 测试辅助：自习室授权范围与资源构造。"""
from __future__ import annotations


def get_room_id(db_query, code="R-N1-101"):
    return db_query("SELECT id FROM rooms WHERE code=?", (code,))[0]["id"]


def create_unassigned_room(db_execute, suffix="B", open_from="08:00", open_to="22:00"):
    """直接构造一个未授权给现有管理员的自习室、区域与座位。"""
    room_id = db_execute(
        """
        INSERT INTO rooms
            (code, name, building, floor, location, open_from, open_to,
             status, note, created_at)
        VALUES (?, ?, '校外楼', '1 层', '测试位置', ?, ?, '开放', 'Sprint 3 测试',
                '2026-10-16 08:30:00')
        """,
        (f"R-OTHER-{suffix}", f"未授权自习室 {suffix}", open_from, open_to),
    )
    zone_id = db_execute(
        """
        INSERT INTO zones (room_id, code, name, zone_type, sort_order)
        VALUES (?, ?, ?, '静音区', 1)
        """,
        (room_id, f"Z-O-{suffix}", f"未授权区域 {suffix}"),
    )
    seat_id = db_execute(
        """
        INSERT INTO seats
            (code, room_id, zone_id, seat_type, status, position, is_bookable, created_at)
        VALUES (?, ?, ?, '普通', '空闲', '测试座位', 1, '2026-10-16 08:30:00')
        """,
        (f"O-{suffix}-01", room_id, zone_id),
    )
    return {"room_id": int(room_id), "zone_id": int(zone_id), "seat_id": int(seat_id)}
