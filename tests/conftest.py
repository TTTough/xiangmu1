"""pytest 公共夹具：独立临时数据库、假时钟、账号与查询辅助。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(SRC), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app import create_app  # noqa: E402
from db import connect_database  # noqa: E402


class FakeClock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, minutes: int = 0, days: int = 0) -> datetime:
        self.value = self.value + timedelta(minutes=minutes, days=days)
        return self.value


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 10, 16, 8, 30, 0))


@pytest.fixture
def app(tmp_path, clock):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test-app.db"),
            "SECRET_KEY": "test-secret",
            "NOW_PROVIDER": clock,
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_query(app):
    def _query(sql: str, params=()):
        conn = connect_database(app.config["DATABASE"])
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    return _query


@pytest.fixture
def db_execute(app):
    def _execute(sql: str, params=()):
        conn = connect_database(app.config["DATABASE"])
        try:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid
        finally:
            conn.close()

    return _execute


@pytest.fixture
def login_as(app):
    def _login(client, student_no="246003384", password="student123"):
        return client.post(
            "/login",
            json={"student_no": student_no, "password": password},
            headers={"Accept": "application/json"},
        )

    return _login


@pytest.fixture
def create_user(db_execute):
    def _create(
        student_no: str,
        name: str = "第二位学生",
        password: str = "student123",
        role: str = "student",
        account_status: str = "正常",
    ) -> int:
        password_hash = generate_password_hash(password, method="pbkdf2:sha256")
        return int(
            db_execute(
                """
                INSERT INTO users
                    (student_no, name, department, contact, role, password_hash,
                     account_status, failed_login_count, created_at)
                VALUES (?, ?, '计算机学院', 'test@example.edu', ?, ?, ?, 0,
                        '2026-10-16 08:30:00')
                """,
                (student_no, name, role, password_hash, account_status),
            )
        )

    return _create


def make_booking(seat_id: int, date_text: str = "2026-10-17", start: str = "09:00", end: str = "11:00"):
    return {
        "seat_id": seat_id,
        "reservation_date": date_text,
        "start_time": start,
        "end_time": end,
    }
