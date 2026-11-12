"""SQLite 访问、初始化与通用事务/审计工具。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from flask import current_app, g


SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect_database(database_path: str) -> sqlite3.Connection:
    """建立独立连接；isolation_level=None 便于显式 BEGIN IMMEDIATE。"""
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def get_db() -> sqlite3.Connection:
    """当前请求/应用上下文内的数据库连接。"""
    if "db" not in g:
        g.db = connect_database(current_app.config["DATABASE"])
    return g.db


def close_db(_exception: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(database_path: str | None = None) -> None:
    """建库并应用 schema；可重复调用（IF NOT EXISTS）。"""
    path = database_path or current_app.config["DATABASE"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect_database(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)


@contextmanager
def immediate_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """显式写事务；并发预约由 SQLite 写锁串行化（NFR-05）。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def get_rule_param(conn: sqlite3.Connection, param_key: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM rule_params WHERE param_key = ?", (param_key,)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"缺少规则参数：{param_key}")
    return row


def get_rule_int(conn: sqlite3.Connection, param_key: str) -> int:
    return int(float(get_rule_param(conn, param_key)["value"]))


def get_rule_float(conn: sqlite3.Connection, param_key: str) -> float:
    return float(get_rule_param(conn, param_key)["value"])


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def write_audit(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int | None,
    actor_name: str,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: str,
    before: Any,
    after: Any,
    result: str,
    created_at: str,
    ip_address: str | None = None,
) -> None:
    """写入 DM-13 审计日志（AC-14-01、AC-14-02 的字段基础）。"""
    conn.execute(
        """
        INSERT INTO audit_logs
            (actor_user_id, actor_name, actor_role, action, target_type, target_id,
             before_json, after_json, result, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor_user_id,
            actor_name,
            actor_role,
            action,
            target_type,
            target_id,
            json_text(before),
            json_text(after),
            result,
            ip_address,
            created_at,
        ),
    )
