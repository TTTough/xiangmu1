"""AC-06-02—AC-06-04：预约记录数据隔离、授权范围与筛选分页。"""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlparse

from sprint2_helpers import get_seat_id, get_user_id, make_reservation
from sprint3_helpers import create_unassigned_room


def _admin_login(client, login_as):
    assert login_as(client, "900000001", "admin123").status_code == 200


def test_ac_06_02_student_only_sees_own_reservations(
    client, login_as, db_query, db_execute, create_user
):
    student_id = get_user_id(db_query)
    other_id = create_user("246003385", name="李小明")
    make_reservation(
        db_query, db_execute, user_id=student_id, seat_id=get_seat_id(db_query, "A-01"),
        status="待生效", reservation_date="2026-10-17", start="09:00", end="11:00"
    )
    other_reservation_id = make_reservation(
        db_query, db_execute, user_id=other_id, seat_id=get_seat_id(db_query, "A-02"),
        status="待生效", reservation_date="2026-10-17", start="13:00", end="15:00"
    )
    other_no = db_query(
        "SELECT reservation_no FROM reservations WHERE id=?", (other_reservation_id,)
    )[0]["reservation_no"]
    assert login_as(client).status_code == 200

    response = client.get("/api/reservations?page_size=50")
    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["reservation_no"] != other_no
    assert all(item["student_name_masked"].startswith("杨") for item in body["items"])


def test_ac_06_03_admin_only_sees_authorized_room_records(
    client, login_as, db_query, db_execute
):
    student_id = get_user_id(db_query)
    seed_room = db_query("SELECT id FROM rooms WHERE code='R-LIB-3F'")[0]["id"]
    other = create_unassigned_room(db_execute)
    make_reservation(
        db_query, db_execute, user_id=student_id, seat_id=get_seat_id(db_query, "A-01"),
        status="待生效", reservation_date="2026-10-17", start="09:00", end="11:00"
    )
    make_reservation(
        db_query, db_execute, user_id=student_id, seat_id=other["seat_id"],
        status="待生效", reservation_date="2026-10-17", start="13:00", end="15:00"
    )
    _admin_login(client, login_as)

    response = client.get("/api/reservations?page_size=50")
    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["room_id"] == seed_room
    assert all(item["room_id"] == seed_room for item in body["items"])
    assert body["items"][0]["room_name"] == "图书馆三层自习室"


def test_ac_06_04_pagination_preserves_filters(client, login_as, db_query, db_execute):
    student_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query, "A-01")
    for day in range(1, 14):
        make_reservation(
            db_query, db_execute, user_id=student_id, seat_id=seat_id,
            status="待生效", reservation_date=f"2026-11-{day:02d}",
            start="09:00", end="11:00"
        )
    assert login_as(client).status_code == 200
    query = (
        "/api/reservations?status=%E5%BE%85%E7%94%9F%E6%95%88"
        "&date_from=2026-11-01&date_to=2026-11-30&page=2&page_size=5"
    )
    response = client.get(query)
    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"] == {
        "page": 2,
        "page_size": 5,
        "total": 13,
        "total_pages": 3,
        "has_prev": True,
        "has_next": True,
    }
    assert len(body["items"]) == 5
    assert all(item["status"] == "待生效" for item in body["items"])
    assert all("2026-11-01" <= item["reservation_date"] <= "2026-11-30" for item in body["items"])

    page = client.get(
        "/records?status=%E5%BE%85%E7%94%9F%E6%95%88"
        "&date_from=2026-11-01&date_to=2026-11-30&page=2&page_size=5"
    )
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    next_link = re.search(r'href="([^"]*page=3[^"]*)"', text)
    assert next_link is not None
    parsed = urlparse(html.unescape(next_link.group(1)))
    query_args = parse_qs(parsed.query)
    assert query_args["status"] == ["待生效"]
    assert query_args["date_from"] == ["2026-11-01"]
    assert query_args["date_to"] == ["2026-11-30"]
    assert query_args["page_size"] == ["5"]
