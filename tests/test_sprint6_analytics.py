"""AC-11-01—AC-11-06：数据分析、刷新机制、筛选保持与后勤只读。"""
from __future__ import annotations

from sprint2_helpers import get_seat_id, get_user_id, make_reservation, make_violation
from sprint3_helpers import create_unassigned_room


def _admin_login(client, login_as):
    assert login_as(client, "900000001", "admin123").status_code == 200


def _logistics_login(client, login_as):
    assert login_as(client, "900000003", "logistics123").status_code == 200


def test_ac_11_01_page_uses_ten_second_local_refresh(client, login_as):
    _admin_login(client, login_as)
    page = client.get("/analytics")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "refreshMs = 10000" in text
    assert "setInterval(refresh, refreshMs)" in text
    assert "location.reload" not in text
    assert "局部刷新" in text


def test_ac_11_02_api_contains_bar_line_and_required_stats(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seat_id = get_seat_id(db_query, "A-01")
    make_violation(
        db_query, db_execute, user_id=user_id, seat_id=seat_id,
        status="生效中", created_at="2026-10-16 08:00:00"
    )
    _admin_login(client, login_as)
    response = client.get("/api/analytics")
    assert response.status_code == 200
    data = response.get_json()
    assert "bar_reservations_by_room" in data["charts"]
    assert "bar_violations_by_room" in data["charts"]
    assert "line_daily" in data["charts"]
    assert data["stats"]["today_violations"] == 1
    assert data["stats"]["current_free_seats"] >= 0
    page = client.get("/analytics").get_data(as_text=True)
    assert 'id="bar-reservations"' in page
    assert 'id="bar-violations"' in page
    assert 'id="line-daily"' in page
    assert 'id="stat-free"' in page and 'id="stat-violations"' in page


def test_ac_11_03_filters_preserved_across_repeated_refresh(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=get_seat_id(db_query, "A-01"),
        status="待生效", reservation_date="2026-10-15", start="09:00", end="11:00"
    )
    _admin_login(client, login_as)
    query = "/api/analytics?date_from=2026-10-10&date_to=2026-10-16&room_id=1"
    first = client.get(query).get_json()
    second = client.get(query).get_json()
    assert first["filters"] == {
        "date_from": "2026-10-10", "date_to": "2026-10-16", "room_id": 1
    }
    assert second["filters"] == first["filters"]
    assert second["charts"]["line_daily"]["labels"] == first["charts"]["line_daily"]["labels"]
    page = client.get("/analytics").get_data(as_text=True)
    assert 'id="f-date-from"' in page and 'id="f-room"' in page
    assert "function currentQuery()" in page


def test_ac_11_04_changing_filter_recalculates_data(
    client, login_as, db_query, db_execute
):
    user_id = get_user_id(db_query)
    seed_seat = get_seat_id(db_query, "A-01")
    other = create_unassigned_room(db_execute)
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=seed_seat,
        status="待生效", reservation_date="2026-10-15", start="09:00", end="11:00"
    )
    make_reservation(
        db_query, db_execute, user_id=user_id, seat_id=other["seat_id"],
        status="待生效", reservation_date="2026-10-15", start="13:00", end="15:00"
    )
    _logistics_login(client, login_as)
    all_data = client.get(
        "/api/analytics?date_from=2026-10-10&date_to=2026-10-16"
    ).get_json()
    room_a = client.get(
        "/api/analytics?date_from=2026-10-10&date_to=2026-10-16&room_id=1"
    ).get_json()
    room_b = client.get(
        f"/api/analytics?date_from=2026-10-10&date_to=2026-10-16&room_id={other['room_id']}"
    ).get_json()
    assert sum(all_data["charts"]["bar_reservations_by_room"]["values"]) == 2
    assert room_a["charts"]["bar_reservations_by_room"]["values"] == [1]
    assert room_b["charts"]["bar_reservations_by_room"]["values"] == [1]
    assert room_a["filters"]["room_id"] == 1
    assert room_b["filters"]["room_id"] == other["room_id"]


def test_ac_11_05_logistics_is_read_only(client, login_as):
    _logistics_login(client, login_as)
    page = client.get("/analytics")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "数据分析" in text
    for write_entry in ("手动违约登记", "停用座位", "维护扫描", "评价管理"):
        assert write_entry not in text
    api = client.get("/api/analytics")
    assert api.status_code == 200
    assert "charts" in api.get_json()


def test_ac_11_06_refresh_does_not_reload_or_reset_expanded_detail(
    client, login_as
):
    _admin_login(client, login_as)
    page = client.get("/analytics")
    text = page.get_data(as_text=True)
    assert '<details id="analytics-detail">' in text
    assert "setInterval(refresh, refreshMs)" in text
    assert "window.location" not in text
    assert "location.href" not in text
    # 刷新函数只重绘图表/统计与详情正文，详情节点本身不重建。
    assert 'el("analytics-detail-body")' in text
