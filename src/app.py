"""智慧自习室预约与管理系统 v1.0 — 最终版应用入口。

S1：FR-01 登录与会话、FR-03 预约主链路、FR-04 取消预约、FR-06 座位查询。
S2：FR-04 签到/签退、FR-05 自动违约与申诉、FR-10 黑名单与信用状态。
S3：FR-02 资源维护、FR-07 实时座位、V3 手动违约与历史记录。
S4：FR-06 记录查询分页与数据隔离、FR-14 审计日志查询/筛选/分页与不可改删。
S5：FR-08 评价管理、FR-09 投诉与反馈闭环。
S6：FR-11 数据分析与 10 秒局部刷新、FR-12 通知中心。
S7：FR-13 参数配置、范围校验、变更审计与全量回归。
S8：架构基线对齐（sysadmin 权限、P-15 范围、参数生效点、Q-33/34/35）。
S9：参数补种、投诉关闭路径、黑名单直接加入/延期、管理员代创建。
S10：用户信息、授权维护、阈值提醒、CSV 统计导出。
S11：预约修改（允许跨自习室、每条最多一次）。
所有权限和业务规则均在服务端校验（BR-21、NFR-07）。
"""
from __future__ import annotations

import csv
import io
import json
import math
import sqlite3
import threading
import time as time_module
import uuid
from datetime import date as date_cls
from datetime import datetime, time as time_cls, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

import db
from config import Config, ROLE_LABELS, PARAM_EFFECT_POINTS
from seed import seed_database

ACTIVE_STATUSES = ("待生效", "待签到", "使用中")
CHECKIN_METHODS = ("二维码", "座位编号")
SYSTEM_ACTOR_NAME = "系统定时任务"
SYSTEM_ACTOR_ROLE = "系统"
HOME_ENDPOINT = {
    "student": "student_home",
    "admin": "admin_home",
    "sysadmin": "sysadmin_home",
    "logistics": "analytics_page",
}


class ApiError(Exception):
    """可安全展示给调用方的业务/权限错误（NFR-17）。"""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def wants_json() -> bool:
    return (
        request.path.startswith("/api/")
        or request.is_json
        or request.accept_mimetypes.best == "application/json"
    )


def get_now() -> datetime:
    """统一服务端时钟；测试通过 NOW_PROVIDER 注入假时间（NFR-18）。"""
    from flask import current_app

    provider = current_app.config.get("NOW_PROVIDER")
    value = provider() if provider else datetime.now()
    return value.replace(microsecond=0)


def fmt_dt(value: datetime) -> str:
    return value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def parse_date(value: str) -> date_cls:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_hm(value: str) -> time_cls:
    normalized = str(value).strip()
    if len(normalized) == 5 and normalized[2] == ":":
        try:
            return datetime.strptime(normalized, "%H:%M").time()
        except ValueError:
            pass
    raise ValueError("时间格式应为 HH:MM")


def hm_text(value: time_cls) -> str:
    return value.strftime("%H:%M")


def combine(date_text: str, time_text: time_cls) -> datetime:
    return datetime.combine(parse_date(date_text), time_text)


def minutes_between(start: time_cls, end: time_cls) -> int:
    return int((datetime.combine(date_cls.min, end) - datetime.combine(date_cls.min, start)).total_seconds() // 60)


def minutes_until(now: datetime, future: datetime) -> int:
    return max(0, math.ceil((future - now).total_seconds() / 60))


def public_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "student_no": row["student_no"],
        "name": row["name"],
        "department": row["department"],
        "role": row["role"],
        "role_label": ROLE_LABELS.get(row["role"], row["role"]),
        "account_status": row["account_status"],
        "failed_login_count": row["failed_login_count"],
        "locked_until": row["locked_until"],
        "blacklist_until": row["blacklist_until"],
        "effective_violation_count": row["effective_violation_count"],
    }


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def mask_name(name: str | None) -> str:
    """姓名脱敏：保留首字符，其余以 * 代替（NFR-09、AC-07-01、AC-07-05）。"""
    if not name:
        return "—"
    if len(name) <= 1:
        return name + "*"
    return name[0] + "*" * (len(name) - 1)


def mask_student_no(student_no: str | None) -> str:
    if not student_no:
        return "—"
    if len(student_no) <= 6:
        return student_no[0] + "*" * (len(student_no) - 1)
    return student_no[:3] + "*" * (len(student_no) - 6) + student_no[-3:]


def mask_contact(contact: str | None) -> str:
    """手机号/邮箱脱敏（NFR-09、AC-09-06）。"""
    if not contact:
        return "—"
    if "@" in contact:
        local, domain = contact.split("@", 1)
        visible = local[:2] if len(local) > 2 else local[:1]
        return f"{visible}***@{domain}"
    if len(contact) >= 7:
        return contact[:3] + "****" + contact[-4:]
    return contact[0] + "*" * max(1, len(contact) - 1)


def admin_room_ids(conn: sqlite3.Connection, admin_user_id: int) -> list[int]:
    """当前管理员被授权的自习室范围；系统管理员按权限矩阵覆盖全部自习室。"""
    role_row = conn.execute(
        "SELECT role FROM users WHERE id=?", (admin_user_id,)
    ).fetchone()
    if role_row is not None and role_row["role"] == "sysadmin":
        return [
            int(row["id"])
            for row in conn.execute("SELECT id FROM rooms ORDER BY id").fetchall()
        ]
    return [
        int(row["room_id"])
        for row in conn.execute(
            "SELECT room_id FROM admin_room_assignments WHERE admin_user_id=?",
            (admin_user_id,),
        ).fetchall()
    ]


def require_room_access(conn: sqlite3.Connection, admin: sqlite3.Row, room_id: int) -> None:
    """未授权自习室一律拒绝；系统管理员按权限矩阵可维护全部自习室。"""
    if admin["role"] == "sysadmin":
        return
    allowed = admin_room_ids(conn, int(admin["id"]))
    if room_id not in allowed:
        raise ApiError(
            403,
            "ROOM_FORBIDDEN",
            f"越权：管理员未被授权维护自习室 #{room_id}（BR-21、NFR-07）",
        )


def require_seat_access(
    conn: sqlite3.Connection, admin: sqlite3.Row, seat_id: int
) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT s.*, z.name AS zone_name, r.name AS room_name, r.status AS room_status
          FROM seats s
          JOIN zones z ON z.id = s.zone_id
          JOIN rooms r ON r.id = s.room_id
         WHERE s.id = ?
        """,
        (seat_id,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "SEAT_NOT_FOUND", "座位不存在")
    require_room_access(conn, admin, int(row["room_id"]))
    return row


def _unauthorized(message: str = "请先登录后再访问"):
    if wants_json():
        return jsonify({"error": {"code": "UNAUTHORIZED", "message": message}}), 401
    flash(message, "error")
    return redirect(url_for("login", next=request.path))


def _forbidden(message: str):
    if wants_json():
        return jsonify({"error": {"code": "FORBIDDEN", "message": message}}), 403
    return (
        render_template(
            "error.html",
            status_code=403,
            title="越权访问",
            message=message,
        ),
        403,
    )


def _session_authenticated():
    """校验会话存在与空闲超时；成功时刷新活动时间。"""
    if g.get("user") is None:
        return _unauthorized()
    last_active = session.get("last_active_at")
    now = get_now()
    idle_minutes = db.get_rule_int(db.get_db(), "session_idle_minutes")
    if last_active:
        try:
            last_dt = datetime.fromisoformat(last_active)
        except ValueError:
            last_dt = None
        if last_dt is not None and (now - last_dt).total_seconds() > idle_minutes * 60:
            session.clear()
            g.user = None
            return _unauthorized(f"会话已因连续 {idle_minutes} 分钟无操作失效，请重新登录")
    session["last_active_at"] = fmt_dt(now)
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        failure = _session_authenticated()
        if failure is not None:
            return failure
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            failure = _session_authenticated()
            if failure is not None:
                return failure
            if g.user["role"] not in roles:
                expected = "、".join(role_label(role) for role in roles)
                return _forbidden(f"越权：该操作仅限 {expected}；本次请求未产生任何数据变更（BR-21）")
            return view(*args, **kwargs)

        return wrapped

    return decorator


def home_for_role(role: str) -> str:
    return url_for(HOME_ENDPOINT.get(role, "student_home"))


# ---------------------------------------------------------------------------
# 认证：FR-01 / BR-25 / ST-32—ST-34
# ---------------------------------------------------------------------------


def authenticate_user(student_no: str, password: str, ip_address: str | None) -> dict:
    """执行模拟 SSO 认证、锁定判定和登录审计。

    对应 AC-01-01、AC-01-04；BR-25、ST-32、ST-33、ST-34。
    锁定按账号判定，不影响已有预约与签到签退。
    """
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)

    with db.immediate_transaction(conn):
        row = conn.execute(
            "SELECT * FROM users WHERE student_no = ?", (student_no,)
        ).fetchone()
        if row is None:
            db.write_audit(
                conn,
                actor_user_id=None,
                actor_name=student_no,
                actor_role="—",
                action="登录",
                target_type="账号",
                target_id=student_no,
                before=None,
                after=None,
                result="失败：账号不存在",
                created_at=now_s,
                ip_address=ip_address,
            )
            return {
                "ok": False,
                "status": 401,
                "code": "INVALID_CREDENTIALS",
                "message": "学号或密码错误",
            }

        uid = int(row["id"])
        audit_role = role_label(row["role"])

        # ST-34：锁定期内拒绝登录，提示剩余时间；不建立会话。
        if row["account_status"] == "锁定":
            locked_until = parse_dt(row["locked_until"]) if row["locked_until"] else None
            if locked_until is not None and now < locked_until:
                remaining = minutes_until(now, locked_until)
                db.write_audit(
                    conn,
                    actor_user_id=uid,
                    actor_name=row["name"],
                    actor_role=audit_role,
                    action="登录",
                    target_type="账号",
                    target_id=row["student_no"],
                    before={"account_status": "锁定", "locked_until": row["locked_until"]},
                    after={"account_status": "锁定", "locked_until": row["locked_until"]},
                    result=f"拒绝：锁定中，剩余约 {remaining} 分钟",
                    created_at=now_s,
                    ip_address=ip_address,
                )
                return {
                    "ok": False,
                    "status": 423,
                    "code": "ACCOUNT_LOCKED",
                    "message": f"账号处于锁定期间，拒绝登录；剩余解锁时间约 {remaining} 分钟",
                    "remaining_minutes": remaining,
                    "locked_until": row["locked_until"],
                }

            # ST-33：锁定期满自动恢复，并恢复锁定前的账号状态（避免覆盖黑名单）。
            restored = row["pre_lock_status"] or "正常"
            previous_status = row["account_status"]
            conn.execute(
                """
                UPDATE users
                   SET account_status = ?, pre_lock_status = NULL, locked_until = NULL,
                       failed_login_count = 0
                 WHERE id = ?
                """,
                (restored, uid),
            )
            db.write_audit(
                conn,
                actor_user_id=uid,
                actor_name=row["name"],
                actor_role=audit_role,
                action="账号自动解锁",
                target_type="账号",
                target_id=row["student_no"],
                before={"account_status": previous_status, "failed_login_count": row["failed_login_count"]},
                after={"account_status": restored, "failed_login_count": 0},
                result="成功：锁定期限届满",
                created_at=now_s,
                ip_address=ip_address,
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

        if not check_password_hash(row["password_hash"], password):
            failed_count = int(row["failed_login_count"]) + 1
            threshold = db.get_rule_int(conn, "login_lock_threshold")
            lock_minutes = db.get_rule_int(conn, "lock_duration_minutes")
            before = {
                "failed_login_count": row["failed_login_count"],
                "account_status": row["account_status"],
            }
            if failed_count >= threshold:
                previous_status = row["account_status"]
                pre_lock_status = (
                    previous_status if previous_status in ("正常", "黑名单") else "正常"
                )
                locked_until = now + timedelta(minutes=lock_minutes)
                conn.execute(
                    """
                    UPDATE users
                       SET account_status = '锁定', pre_lock_status = ?,
                           failed_login_count = ?, locked_until = ?
                     WHERE id = ?
                    """,
                    (pre_lock_status, failed_count, fmt_dt(locked_until), uid),
                )
                db.write_audit(
                    conn,
                    actor_user_id=uid,
                    actor_name=row["name"],
                    actor_role=audit_role,
                    action="登录",
                    target_type="账号",
                    target_id=row["student_no"],
                    before=before,
                    after={
                        "failed_login_count": failed_count,
                        "account_status": "锁定",
                        "locked_until": fmt_dt(locked_until),
                    },
                    result=f"失败：连续失败 {failed_count} 次，达到阈值，账号锁定",
                    created_at=now_s,
                    ip_address=ip_address,
                )
                return {
                    "ok": False,
                    "status": 423,
                    "code": "ACCOUNT_LOCKED",
                    "message": (
                        f"凭证校验失败，连续失败次数达 {failed_count} 次（阈值 {threshold} 次），"
                        f"账号转入「锁定」，自动解锁时间 {fmt_dt(locked_until)}"
                    ),
                    "remaining_minutes": lock_minutes,
                    "locked_until": fmt_dt(locked_until),
                }

            conn.execute(
                "UPDATE users SET failed_login_count = ? WHERE id = ?",
                (failed_count, uid),
            )
            db.write_audit(
                conn,
                actor_user_id=uid,
                actor_name=row["name"],
                actor_role=audit_role,
                action="登录",
                target_type="账号",
                target_id=row["student_no"],
                before=before,
                after={
                    "failed_login_count": failed_count,
                    "account_status": row["account_status"],
                },
                result=f"失败：凭证错误，累计 {failed_count} / {threshold}",
                created_at=now_s,
                ip_address=ip_address,
            )
            return {
                "ok": False,
                "status": 401,
                "code": "INVALID_CREDENTIALS",
                "message": (
                    f"学号或密码错误；连续失败 {failed_count} / {threshold}，"
                    "未达阈值时账号状态保持不变"
                ),
            }

        # 成功登录：清零连续失败计数，锁定状态此前已按 ST-33 恢复。
        db.write_audit(
            conn,
            actor_user_id=uid,
            actor_name=row["name"],
            actor_role=audit_role,
            action="登录",
            target_type="账号",
            target_id=row["student_no"],
            before={
                "failed_login_count": row["failed_login_count"],
                "account_status": row["account_status"],
            },
            after={"failed_login_count": 0, "account_status": row["account_status"]},
            result="成功",
            created_at=now_s,
            ip_address=ip_address,
        )
        conn.execute(
            "UPDATE users SET failed_login_count = 0, locked_until = NULL WHERE id = ?",
            (uid,),
        )
        return {"ok": True, "user": public_user(row)}


# ---------------------------------------------------------------------------
# 座位查询：FR-06 / AC-06-01
# ---------------------------------------------------------------------------


def _optional_int_arg(name: str) -> int | None:
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError:
        raise ApiError(400, "INVALID_FILTER", f"筛选参数 {name} 必须为整数")


def _free_time_ranges(
    open_from: time_cls,
    open_to: time_cls,
    reservations: list[sqlite3.Row],
) -> list[dict]:
    """把某座位某日的空档拆成连续可预约区间。"""
    cursor = open_from
    result: list[dict] = []
    for reservation in sorted(reservations, key=lambda item: item["start_time"]):
        try:
            start = parse_hm(reservation["start_time"])
            end = parse_hm(reservation["end_time"])
        except ValueError:
            continue
        if end <= cursor:
            continue
        if start > cursor:
            result.append({"start": hm_text(cursor), "end": hm_text(min(start, open_to))})
        cursor = max(cursor, end)
        if cursor >= open_to:
            break
    if cursor < open_to:
        result.append({"start": hm_text(cursor), "end": hm_text(open_to)})
    return [item for item in result if item["start"] < item["end"]]


def query_seats(filters: dict) -> list[dict]:
    """按楼栋、自习室、区域、日期、时段、座位类型查询座位（AC-06-01）。"""
    conn = db.get_db()
    clauses = ["1 = 1"]
    params: list[object] = []
    if filters.get("building"):
        clauses.append("r.building = ?")
        params.append(filters["building"])
    if filters.get("room_id") is not None:
        clauses.append("r.id = ?")
        params.append(filters["room_id"])
    if filters.get("zone_id") is not None:
        clauses.append("z.id = ?")
        params.append(filters["zone_id"])
    if filters.get("zone_type"):
        clauses.append("z.zone_type = ?")
        params.append(filters["zone_type"])
    if filters.get("seat_type"):
        clauses.append("s.seat_type = ?")
        params.append(filters["seat_type"])

    rows = conn.execute(
        f"""
        SELECT s.*, z.name AS zone_name, z.zone_type AS zone_type,
               z.code AS zone_code, z.sort_order AS zone_sort,
               r.name AS room_name, r.building, r.floor, r.open_from, r.open_to,
               r.status AS room_status
          FROM seats s
          JOIN zones z ON z.id = s.zone_id
          JOIN rooms r ON r.id = s.room_id
         WHERE {' AND '.join(clauses)}
         ORDER BY r.building, r.name, z.sort_order, s.code
        """,
        params,
    ).fetchall()

    reservations_by_seat: dict[int, list[sqlite3.Row]] = {}
    if filters.get("date"):
        for reservation in conn.execute(
            """
            SELECT seat_id, start_time, end_time
              FROM reservations
             WHERE reservation_date = ?
               AND status IN ('待生效', '待签到', '使用中')
             ORDER BY start_time
            """,
            (filters["date"],),
        ).fetchall():
            reservations_by_seat.setdefault(int(reservation["seat_id"]), []).append(reservation)

    slot_start = filters.get("start_time")
    slot_end = filters.get("end_time")
    slot_checked = bool(slot_start and slot_end)
    output: list[dict] = []
    for row in rows:
        seat_enabled = row["status"] != "停用" and bool(row["is_bookable"])
        open_from = parse_hm(row["open_from"])
        open_to = parse_hm(row["open_to"])
        reservations = reservations_by_seat.get(int(row["id"]), [])
        available_slots = (
            _free_time_ranges(open_from, open_to, reservations) if seat_enabled else []
        )

        available_for_slot = None
        if slot_checked:
            start = parse_hm(slot_start)
            end = parse_hm(slot_end)
            available_for_slot = (
                seat_enabled
                and row["room_status"] == "开放"
                and open_from <= start < end <= open_to
                and not any(
                    parse_hm(item["start_time"]) < end
                    and start < parse_hm(item["end_time"])
                    for item in reservations
                )
            )
            if available_for_slot is None:
                available_for_slot = False

        if filters.get("only_available"):
            if slot_checked and not available_for_slot:
                continue
            if not slot_checked and not (seat_enabled and row["status"] == "空闲"):
                continue

        output.append(
            {
                "id": row["id"],
                "code": row["code"],
                "seat_type": row["seat_type"],
                "position": row["position"],
                "current_status": row["status"],
                "is_bookable": bool(row["is_bookable"]),
                "room": {
                    "id": row["room_id"],
                    "name": row["room_name"],
                    "building": row["building"],
                    "floor": row["floor"],
                    "open_from": row["open_from"],
                    "open_to": row["open_to"],
                    "status": row["room_status"],
                },
                "zone": {
                    "id": row["zone_id"],
                    "code": row["zone_code"],
                    "name": row["zone_name"],
                    "type": row["zone_type"],
                },
                "available_for_slot": available_for_slot,
                "available_slots": available_slots,
            }
        )
    return output


# ---------------------------------------------------------------------------
# 预约：FR-03 / AC-03-01—AC-03-05
# ---------------------------------------------------------------------------


def _payload_dict() -> dict:
    return request.get_json(silent=True) or request.form.to_dict(flat=True) or {}


def _required_text(data: dict, *names: str) -> str:
    for name in names:
        value = data.get(name)
        if value not in (None, ""):
            return str(value).strip()
    raise ApiError(400, "MISSING_FIELD", f"缺少必填字段：{names[0]}")


def _seat_snapshot(row: sqlite3.Row) -> dict:
    return {
        "seat_id": row["id"],
        "seat_code": row["code"],
        "seat_status": row["status"],
    }


def create_reservation(
    user: sqlite3.Row,
    data: dict,
    *,
    actor: sqlite3.Row | None = None,
    source: str = "学生自助",
    reason: str | None = None,
) -> dict:
    """创建预约的事务内校验与写入（AC-03-01—05、NFR-05）。

    校验顺序：账号状态 → 有效预约上限 → 时长/时间/开放时间/提前天数 →
    座位状态与时段冲突。并发写入使用 BEGIN IMMEDIATE，并由数据库触发器兜底。
    """
    conn = db.get_db()
    actor = actor or user
    now = get_now()
    now_s = fmt_dt(now)

    seat_raw = _required_text(data, "seat_id")
    try:
        seat_id = int(seat_raw)
    except ValueError:
        raise ApiError(400, "INVALID_FIELD", "seat_id 必须为整数")

    with db.immediate_transaction(conn):
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        if user_row is None:
            raise ApiError(401, "UNAUTHORIZED", "登录账号不存在，请重新登录")

        # BR-13：黑名单禁止新预约；教学模拟确认 Q-05 仅禁止新建，不影响已有预约。
        active_blacklist = conn.execute(
            """
            SELECT * FROM blacklists
             WHERE user_id = ? AND status = '生效中' AND expires_at > ?
             ORDER BY expires_at DESC LIMIT 1
            """,
            (user_row["id"], now_s),
        ).fetchone()
        if user_row["account_status"] == "黑名单" or active_blacklist is not None:
            until_text = (
                active_blacklist["expires_at"]
                if active_blacklist is not None
                else user_row["blacklist_until"]
            )
            remaining_text = ""
            if until_text:
                try:
                    remaining_text = f"，剩余解除时间约 {minutes_until(now, parse_dt(until_text))} 分钟"
                except ValueError:
                    remaining_text = ""
            raise ApiError(
                409,
                "BLACKLISTED",
                f"账号处于黑名单期间，禁止发起新预约{remaining_text}（BR-13）",
            )

        # BR-04：同时有效预约上限；上限从 rule_params 读取，不在路由硬编码。
        max_active = db.get_rule_int(conn, "max_active_reservations")
        active_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM reservations
             WHERE user_id = ? AND status IN ('待生效', '待签到', '使用中')
            """,
            (user_row["id"],),
        ).fetchone()["n"]
        if active_count >= max_active:
            raise ApiError(
                409,
                "ACTIVE_RESERVATION_LIMIT",
                f"当前已持有 {active_count} 条有效预约，达到上限 {max_active} 个（BR-04）",
            )

        date_text = _required_text(data, "reservation_date", "date")
        start_text = _required_text(data, "start_time", "start")
        end_text = _required_text(data, "end_time", "end")
        try:
            reservation_date = parse_date(date_text)
            start_time = parse_hm(start_text)
            end_time = parse_hm(end_text)
        except ValueError as exc:
            raise ApiError(400, "INVALID_TIME", str(exc))

        start_dt = datetime.combine(reservation_date, start_time)
        end_dt = datetime.combine(reservation_date, end_time)
        if end_dt <= start_dt:
            raise ApiError(400, "INVALID_TIME_RANGE", "结束时刻必须晚于开始时刻（BR-05）")
        if start_dt < now:
            raise ApiError(409, "START_IN_PAST", "预约开始时刻不得早于服务端当前时间")

        min_duration = db.get_rule_int(conn, "min_duration_minutes")
        max_duration = db.get_rule_int(conn, "max_duration_minutes")
        duration = minutes_between(start_time, end_time)
        if duration < min_duration or duration > max_duration:
            raise ApiError(
                409,
                "DURATION_OUT_OF_RANGE",
                f"单次预约时长须在 {min_duration}—{max_duration} 分钟之间，当前 {duration} 分钟（BR-05）",
            )

        seat_row = conn.execute(
            """
            SELECT s.*, z.name AS zone_name, z.zone_type,
                   r.name AS room_name, r.building, r.floor,
                   r.open_from, r.open_to, r.status AS room_status
              FROM seats s
              JOIN zones z ON z.id = s.zone_id
              JOIN rooms r ON r.id = s.room_id
             WHERE s.id = ?
            """,
            (seat_id,),
        ).fetchone()
        if seat_row is None:
            raise ApiError(404, "SEAT_NOT_FOUND", "目标座位不存在")

        open_from = parse_hm(seat_row["open_from"])
        open_to = parse_hm(seat_row["open_to"])
        if seat_row["room_status"] != "开放":
            raise ApiError(409, "ROOM_CLOSED", "目标自习室当前未开放（BR-03）")
        if start_time < open_from or end_time > open_to:
            raise ApiError(
                409,
                "OUTSIDE_OPEN_HOURS",
                f"所选时段超出开放时间 {seat_row['open_from']}—{seat_row['open_to']}（BR-03）",
            )

        advance_days = db.get_rule_int(conn, "advance_booking_days")
        days_ahead = (reservation_date - now.date()).days
        if days_ahead > advance_days:
            raise ApiError(
                409,
                "ADVANCE_LIMIT",
                f"最多可提前 {advance_days} 天预约，当前选择提前 {days_ahead} 天（BR-06）",
            )

        if seat_row["status"] == "停用" or not bool(seat_row["is_bookable"]):
            raise ApiError(409, "SEAT_DISABLED", "该座位处于停用状态，暂不可预约（BR-23、ST-10）")

        conflict = conn.execute(
            """
            SELECT id FROM reservations
             WHERE seat_id = ? AND reservation_date = ?
               AND status IN ('待生效', '待签到', '使用中')
               AND start_time < ? AND ? < end_time
             LIMIT 1
            """,
            (seat_id, date_text, end_text, start_text),
        ).fetchone()
        if conflict is not None:
            raise ApiError(
                409,
                "SEAT_TIME_CONFLICT",
                "座位状态已变化：该座位在所选时段已被预约，请刷新可选列表（AC-03-05）",
            )

        reservation_no = (
            "RS" + reservation_date.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
        )
        before_seat_status = seat_row["status"]
        try:
            cursor = conn.execute(
                """
                INSERT INTO reservations
                    (reservation_no, user_id, seat_id, room_id, zone_id,
                     reservation_date, start_time, end_time, status, source,
                     created_by, admin_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '待生效', ?, ?, ?, ?)
                """,
                (
                    reservation_no,
                    user_row["id"],
                    seat_id,
                    seat_row["room_id"],
                    seat_row["zone_id"],
                    date_text,
                    hm_text(start_time),
                    hm_text(end_time),
                    source,
                    actor["id"],
                    reason,
                    now_s,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "SEAT_TIME_CONFLICT" in str(exc):
                raise ApiError(
                    409,
                    "SEAT_TIME_CONFLICT",
                    "座位状态已变化：该座位在所选时段已被预约，请刷新可选列表（AC-03-05）",
                )
            raise

        reservation_id = int(cursor.lastrowid)
        new_seat_status = "已预约" if before_seat_status == "空闲" else before_seat_status
        if new_seat_status != before_seat_status:
            conn.execute("UPDATE seats SET status = ? WHERE id = ?", (new_seat_status, seat_id))

        early = db.get_rule_int(conn, "checkin_early_minutes")
        late = db.get_rule_int(conn, "checkin_late_minutes")
        checkin_start = (start_dt - timedelta(minutes=early)).strftime("%H:%M")
        checkin_end = (start_dt + timedelta(minutes=late)).strftime("%H:%M")
        notification_content = (
            f"预约单 {reservation_no} 已创建：{seat_row['room_name']} {seat_row['code']}，"
            f"{date_text} {hm_text(start_time)}—{hm_text(end_time)}；"
            f"签到窗口 {checkin_start}—{checkin_end}。"
        )
        notification_cursor = conn.execute(
            """
            INSERT INTO notifications
                (user_id, notification_type, title, content, created_at, delivery_result)
            VALUES (?, '预约成功', '预约成功通知', ?, ?, '系统内消息已送达')
            """,
            (user_row["id"], notification_content, now_s),
        )

        db.write_audit(
            conn,
            actor_user_id=actor["id"],
            actor_name=actor["name"],
            actor_role=role_label(actor["role"]),
            action=(
                "管理员代创建预约" if source == "管理员代创建" else "提交预约"
            ),
            target_type="预约单",
            target_id=reservation_no,
            before={"reservation": None, "seat_status": before_seat_status},
            after={
                "reservation_no": reservation_no,
                "status": "待生效",
                "seat_id": seat_id,
                "seat_status": new_seat_status,
                "reservation_date": date_text,
                "start_time": hm_text(start_time),
                "end_time": hm_text(end_time),
                "source": source,
                "created_by": actor["id"],
                "target_student_no": user_row["student_no"],
                "reason": reason,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )

        return {
            "id": reservation_id,
            "reservation_no": reservation_no,
            "seat_id": seat_id,
            "seat_code": seat_row["code"],
            "room_name": seat_row["room_name"],
            "zone_name": seat_row["zone_name"],
            "reservation_date": date_text,
            "start_time": hm_text(start_time),
            "end_time": hm_text(end_time),
            "status": "待生效",
            "source": source,
            "admin_reason": reason,
            "seat_status": new_seat_status,
            "notification": {
                "id": int(notification_cursor.lastrowid),
                "type": "预约成功",
                "title": "预约成功通知",
                "content": notification_content,
                "delivery_result": "系统内消息已送达",
            },
        }



def admin_create_reservation(admin: sqlite3.Row, data: dict) -> dict:
    """管理员代学生创建预约：复用学生预约校验，记录来源与原因（FR-03、BR-22）。"""
    student_no = _required_text(data, "student_no")
    reason = _required_text(data, "reason")
    conn = db.get_db()
    target = conn.execute(
        "SELECT * FROM users WHERE student_no=? AND role='student'", (student_no,)
    ).fetchone()
    if target is None:
        raise ApiError(404, "STUDENT_NOT_FOUND", "被代创建的学生不存在")
    result = create_reservation(
        target, data, actor=admin, source="管理员代创建", reason=reason
    )
    result["student_no"] = target["student_no"]
    result["admin_reason"] = reason
    return result


def record_reservation_failure(
    user: sqlite3.Row,
    data: dict,
    error: ApiError,
    *,
    actor: sqlite3.Row | None = None,
    action: str = "提交预约",
) -> None:
    """预约失败也写审计，保证无副作用但可追溯（FR-14）。"""
    conn = db.get_db()
    actor = actor or user
    now_s = fmt_dt(get_now())
    target_id = str(data.get("seat_id", "未知"))
    try:
        with db.immediate_transaction(conn):
            db.write_audit(
                conn,
                actor_user_id=actor["id"],
                actor_name=actor["name"],
                actor_role=role_label(actor["role"]),
                action=action,
                target_type="座位",
                target_id=target_id,
                before={"reservation": None},
                after={"reservation": None},
                result=f"拒绝：{error.message}",
                created_at=now_s,
                ip_address=request.remote_addr,
            )
    except sqlite3.Error:
        # 审计失败不覆盖原始业务拒绝原因；错误已由应用日志/响应体现。
        pass


# ---------------------------------------------------------------------------
# 取消预约：FR-04 / AC-04-01、AC-04-02
# ---------------------------------------------------------------------------


def reservation_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "reservation_no": row["reservation_no"],
        "seat_id": row["seat_id"],
        "seat_code": row["seat_code"] if "seat_code" in row.keys() else None,
        "room_name": row["room_name"] if "room_name" in row.keys() else None,
        "reservation_date": row["reservation_date"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "status": row["status"],
        "source": row["source"],
        "admin_reason": (
            row["admin_reason"] if "admin_reason" in row.keys() else None
        ),
        "modify_count": (
            row["modify_count"] if "modify_count" in row.keys() else 0
        ),
        "modified_at": (
            row["modified_at"] if "modified_at" in row.keys() else None
        ),
        "created_at": row["created_at"],
        "cancelled_at": row["cancelled_at"],
    }


def list_my_reservations(user_id: int) -> list[dict]:
    conn = db.get_db()
    rows = conn.execute(
        """
        SELECT r.*, s.code AS seat_code, ro.name AS room_name
          FROM reservations r
          JOIN seats s ON s.id = r.seat_id
          JOIN rooms ro ON ro.id = r.room_id
         WHERE r.user_id = ?
         ORDER BY r.reservation_date DESC, r.start_time DESC, r.id DESC
        """,
        (user_id,),
    ).fetchall()
    return [reservation_row_to_dict(row) for row in rows]



def modify_reservation(user: sqlite3.Row, reservation_id: int, data: dict) -> dict:
    """学生修改待生效预约：最多一次，允许跨自习室（FR-04、AC-04-07/08）。"""
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    date_text = _required_text(data, "date", "reservation_date")
    start_text = _required_text(data, "from", "start_time")
    end_text = _required_text(data, "to", "end_time")
    try:
        room_id = int(_required_text(data, "room_id"))
        zone_id = int(_required_text(data, "zone_id"))
        seat_id = int(_required_text(data, "seat_id"))
        reservation_date = parse_date(date_text)
        start_time = parse_hm(start_text)
        end_time = parse_hm(end_text)
    except (ValueError, TypeError):
        raise ApiError(400, "INVALID_FIELD", "日期、时段或资源编号格式不正确")
    start_dt = datetime.combine(reservation_date, start_time)
    end_dt = datetime.combine(reservation_date, end_time)
    if end_dt <= start_dt:
        raise ApiError(400, "INVALID_TIME_RANGE", "结束时刻必须晚于开始时刻")

    with db.immediate_transaction(conn):
        row = conn.execute(
            """
            SELECT r.*, s.code AS old_seat_code, ro.name AS old_room_name,
                   z.name AS old_zone_name
              FROM reservations r
              JOIN seats s ON s.id=r.seat_id
              JOIN rooms ro ON ro.id=r.room_id
              JOIN zones z ON z.id=r.zone_id
             WHERE r.id=?
            """,
            (reservation_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "RESERVATION_NOT_FOUND", "预约单不存在")
        if int(row["user_id"]) != int(user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能修改本人的预约（NFR-07）")
        if row["status"] != "待生效":
            raise ApiError(409, "NOT_MODIFIABLE_STATUS", "仅待生效预约可修改")
        old_start = datetime.combine(
            parse_date(row["reservation_date"]), parse_hm(row["start_time"])
        )
        if now >= old_start:
            raise ApiError(409, "MODIFY_WINDOW_CLOSED", "预约已开始，不可修改")
        if int(row["modify_count"]) >= 1:
            raise ApiError(409, "MODIFY_LIMIT", "每条预约最多修改一次")

        active_blacklist = conn.execute(
            """
            SELECT 1 FROM blacklists
             WHERE user_id=? AND status='生效中' AND expires_at > ?
            """,
            (user["id"], now_s),
        ).fetchone()
        if active_blacklist is not None:
            raise ApiError(409, "BLACKLISTED", "账号处于黑名单期间，不可修改预约")

        max_active = db.get_rule_int(conn, "max_active_reservations")
        active_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM reservations
             WHERE user_id=? AND id<>? AND status IN ('待生效','待签到','使用中')
            """,
            (user["id"], reservation_id),
        ).fetchone()["n"]
        if active_count >= max_active:
            raise ApiError(409, "ACTIVE_RESERVATION_LIMIT", "修改后将超出同时有效预约上限")

        min_duration = db.get_rule_int(conn, "min_duration_minutes")
        max_duration = db.get_rule_int(conn, "max_duration_minutes")
        duration = minutes_between(start_time, end_time)
        if duration < min_duration or duration > max_duration:
            raise ApiError(
                409, "DURATION_OUT_OF_RANGE",
                f"单次预约时长须在 {min_duration}—{max_duration} 分钟之间",
            )
        if start_dt < now:
            raise ApiError(409, "START_IN_PAST", "预约开始时刻不得早于当前时间")
        advance_days = db.get_rule_int(conn, "advance_booking_days")
        if (reservation_date - now.date()).days > advance_days:
            raise ApiError(409, "ADVANCE_LIMIT", f"最多可提前 {advance_days} 天预约")

        target = conn.execute(
            """
            SELECT s.*, z.room_id AS zone_room_id, ro.status AS room_status,
                   ro.open_from, ro.open_to, ro.name AS room_name, z.name AS zone_name
              FROM seats s
              JOIN zones z ON z.id=s.zone_id
              JOIN rooms ro ON ro.id=s.room_id
             WHERE s.id=?
            """,
            (seat_id,),
        ).fetchone()
        if target is None:
            raise ApiError(404, "SEAT_NOT_FOUND", "目标座位不存在")
        if int(target["room_id"]) != room_id or int(target["zone_id"]) != zone_id:
            raise ApiError(400, "TARGET_MISMATCH", "目标座位不属于所选自习室/区域")
        if target["room_status"] != "开放":
            raise ApiError(409, "ROOM_CLOSED", "目标自习室当前未开放")
        if target["status"] == "停用" or not bool(target["is_bookable"]):
            raise ApiError(409, "SEAT_DISABLED", "目标座位处于停用状态")
        open_from = parse_hm(target["open_from"])
        open_to = parse_hm(target["open_to"])
        if start_time < open_from or end_time > open_to:
            raise ApiError(409, "OUTSIDE_OPEN_HOURS", "所选时段超出目标自习室开放时间")

        conflict = conn.execute(
            """
            SELECT id FROM reservations
             WHERE seat_id=? AND reservation_date=? AND id<>?
               AND status IN ('待生效','待签到','使用中')
               AND start_time < ? AND ? < end_time
             LIMIT 1
            """,
            (seat_id, date_text, reservation_id, end_text, start_text),
        ).fetchone()
        if conflict is not None:
            raise ApiError(409, "SEAT_TIME_CONFLICT", "目标座位在该时段已被预约")

        before = {
            "room_id": row["room_id"],
            "room_name": row["old_room_name"],
            "zone_id": row["zone_id"],
            "zone_name": row["old_zone_name"],
            "seat_id": row["seat_id"],
            "seat_code": row["old_seat_code"],
            "date": row["reservation_date"],
            "from": row["start_time"],
            "to": row["end_time"],
        }
        try:
            conn.execute(
                """
                UPDATE reservations
                   SET seat_id=?, room_id=?, zone_id=?, reservation_date=?,
                       start_time=?, end_time=?, modify_count=modify_count+1,
                       modified_at=?
                 WHERE id=?
                """,
                (
                    seat_id, room_id, zone_id, date_text,
                    hm_text(start_time), hm_text(end_time), now_s, reservation_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "SEAT_TIME_CONFLICT" in str(exc):
                raise ApiError(409, "SEAT_TIME_CONFLICT", "目标座位在该时段已被预约")
            raise

        recalculate_seat_status(conn, int(row["seat_id"]))
        if seat_id != int(row["seat_id"]):
            recalculate_seat_status(conn, seat_id)

        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="修改预约",
            target_type="预约单",
            target_id=row["reservation_no"],
            before=before,
            after={
                "room_id": room_id,
                "room_name": target["room_name"],
                "zone_id": zone_id,
                "zone_name": target["zone_name"],
                "seat_id": seat_id,
                "seat_code": target["code"],
                "date": date_text,
                "from": hm_text(start_time),
                "to": hm_text(end_time),
                "modify_count": int(row["modify_count"]) + 1,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        notify_user(
            conn,
            user["id"],
            "预约变更",
            "预约修改成功",
            f"预约单 {row['reservation_no']} 已修改为 {target['room_name']} "
            f"{target['code']}，{date_text} {hm_text(start_time)}—{hm_text(end_time)}。",
            now_s,
        )
        updated = conn.execute(
            """
            SELECT r.*, s.code AS seat_code, ro.name AS room_name
              FROM reservations r JOIN seats s ON s.id=r.seat_id
              JOIN rooms ro ON ro.id=r.room_id WHERE r.id=?
            """,
            (reservation_id,),
        ).fetchone()
        result = reservation_row_to_dict(updated)
        result["previous"] = before
        return result


def cancel_reservation(user: sqlite3.Row, reservation_id: int) -> dict:
    """取消本人且尚未开始的预约；开始后拒绝（AC-04-01、AC-04-02）。"""
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    with db.immediate_transaction(conn):
        row = conn.execute(
            """
            SELECT r.*, s.code AS seat_code, s.status AS seat_status,
                   s.is_bookable AS seat_bookable, ro.name AS room_name
              FROM reservations r
              JOIN seats s ON s.id = r.seat_id
              JOIN rooms ro ON ro.id = r.room_id
             WHERE r.id = ?
            """,
            (reservation_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "RESERVATION_NOT_FOUND", "预约单不存在")
        if int(row["user_id"]) != int(user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能取消本人的预约（NFR-07）")
        if row["status"] not in ("待生效", "待签到"):
            raise ApiError(
                409,
                "NOT_CANCELLABLE",
                f"预约单当前状态为「{row['status']}」，不可取消",
            )

        start_dt = datetime.combine(
            parse_date(row["reservation_date"]), parse_hm(row["start_time"])
        )
        if now >= start_dt:
            raise ApiError(
                409,
                "CANCEL_WINDOW_CLOSED",
                f"已过可取消时间：预约开始时刻为 {row['reservation_date']} {row['start_time']}（BR-10）",
            )

        conn.execute(
            """
            UPDATE reservations
               SET status = '已取消', cancelled_at = ?, cancel_reason = '学生主动取消'
             WHERE id = ?
            """,
            (now_s, reservation_id),
        )
        remaining = conn.execute(
            """
            SELECT COUNT(*) AS n FROM reservations
             WHERE seat_id = ? AND id <> ?
               AND status IN ('待生效', '待签到', '使用中')
            """,
            (row["seat_id"], reservation_id),
        ).fetchone()["n"]
        if row["seat_status"] != "停用":
            new_seat_status = "已预约" if remaining else "空闲"
            conn.execute(
                "UPDATE seats SET status = ? WHERE id = ?",
                (new_seat_status, row["seat_id"]),
            )
        else:
            new_seat_status = "停用"

        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="取消预约",
            target_type="预约单",
            target_id=row["reservation_no"],
            before={
                "reservation_status": row["status"],
                "seat_status": row["seat_status"],
            },
            after={
                "reservation_status": "已取消",
                "seat_status": new_seat_status,
                "cancelled_at": now_s,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": reservation_id,
            "reservation_no": row["reservation_no"],
            "status": "已取消",
            "seat_id": row["seat_id"],
            "seat_code": row["seat_code"],
            "seat_status": new_seat_status,
            "cancelled_at": now_s,
            "violation_created": False,
        }


def record_cancel_failure(user: sqlite3.Row, reservation_id: int, error: ApiError) -> None:
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    try:
        with db.immediate_transaction(conn):
            db.write_audit(
                conn,
                actor_user_id=user["id"],
                actor_name=user["name"],
                actor_role=role_label(user["role"]),
                action="取消预约",
                target_type="预约单",
                target_id=str(reservation_id),
                before={"reservation_status": None},
                after={"reservation_status": None},
                result=f"拒绝：{error.message}",
                created_at=now_s,
                ip_address=request.remote_addr,
            )
    except sqlite3.Error:
        pass


# ---------------------------------------------------------------------------
# Sprint 2：签到、签退、自动违约、申诉、黑名单
# FR-04、FR-05、FR-10；AC-04-03—06、AC-05-01—07、AC-10-01—05
# ---------------------------------------------------------------------------


def notify_user(
    conn: sqlite3.Connection,
    user_id: int,
    notification_type: str,
    title: str,
    content: str,
    now_s: str,
    event_key: str | None = None,
) -> int:
    """写入系统内通知（DM-11；AC-03-01、AC-05-05、AC-10-01、AC-10-03、AC-12-01）。

    event_key 用于提醒类通知去重；相同事件键只写一次。
    """
    if event_key is not None:
        existing = conn.execute(
            "SELECT id FROM notifications WHERE event_key=?", (event_key,)
        ).fetchone()
        if existing is not None:
            return int(existing["id"])
    cursor = conn.execute(
        """
        INSERT INTO notifications
            (user_id, notification_type, title, content, created_at,
             delivery_result, event_key)
        VALUES (?, ?, ?, ?, ?, '系统内消息已送达', ?)
        """,
        (user_id, notification_type, title, content, now_s, event_key),
    )
    return int(cursor.lastrowid)


def recalculate_seat_status(conn: sqlite3.Connection, seat_id: int) -> str:
    """根据该座位当前有效预约推导座位展示状态（BR-02、SM-01）。"""
    seat = conn.execute("SELECT status FROM seats WHERE id = ?", (seat_id,)).fetchone()
    if seat is None:
        raise ApiError(404, "SEAT_NOT_FOUND", "座位不存在")
    if seat["status"] == "停用":
        return "停用"
    rows = conn.execute(
        """
        SELECT status FROM reservations
         WHERE seat_id = ? AND status IN ('待生效', '待签到', '使用中')
        """,
        (seat_id,),
    ).fetchall()
    statuses = [row["status"] for row in rows]
    if "使用中" in statuses:
        new_status = "使用中"
    elif statuses:
        new_status = "已预约"
    else:
        new_status = "空闲"
    if new_status != seat["status"]:
        conn.execute("UPDATE seats SET status = ? WHERE id = ?", (new_status, seat_id))
    return new_status


def _reservation_with_seat(conn: sqlite3.Connection, reservation_id: int) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT r.*, s.code AS seat_code, s.status AS seat_status,
               s.is_bookable AS seat_bookable, ro.name AS room_name
          FROM reservations r
          JOIN seats s ON s.id = r.seat_id
          JOIN rooms ro ON ro.id = r.room_id
         WHERE r.id = ?
        """,
        (reservation_id,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "RESERVATION_NOT_FOUND", "预约单不存在")
    return row


def checkin_reservation(user: sqlite3.Row, reservation_id: int, data: dict) -> dict:
    """签到：窗口内将预约与座位置为「使用中」（AC-04-03—04、AC-04-06）。

    BR-07、ST-03、ST-14、ST-16。早于窗口、晚于窗口或座位号不一致均拒绝，
    且除系统状态推进外不改变预约状态、不写签到记录。
    """
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    seat_code = _required_text(data, "seat_code", "code")
    method = str(data.get("method") or "座位编号").strip()
    if method not in CHECKIN_METHODS:
        raise ApiError(400, "INVALID_CHECKIN_METHOD", "签到方式仅支持二维码或座位编号")

    with db.immediate_transaction(conn):
        row = _reservation_with_seat(conn, reservation_id)
        if int(row["user_id"]) != int(user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能签到本人的预约（NFR-07）")

        early = db.get_rule_int(conn, "checkin_early_minutes")
        late = db.get_rule_int(conn, "checkin_late_minutes")
        start_dt = datetime.combine(
            parse_date(row["reservation_date"]), parse_hm(row["start_time"])
        )
        window_start = start_dt - timedelta(minutes=early)
        window_end = start_dt + timedelta(minutes=late)

        status = row["status"]
        if status == "待生效" and window_start <= now <= window_end:
            # ST-11：到达可签到阶段后由系统推进为「待签到」。
            conn.execute("UPDATE reservations SET status='待签到' WHERE id=?", (reservation_id,))
            status = "待签到"
        if status != "待签到":
            raise ApiError(
                409,
                "NOT_CHECKINABLE",
                f"预约单当前状态为「{status}」，不可签到（ST-16）",
            )
        if now < window_start:
            raise ApiError(
                409,
                "CHECKIN_WINDOW_NOT_STARTED",
                f"早于签到窗口开始时间 {window_start.strftime('%H:%M')}（BR-07、ST-16）",
            )
        if now > window_end:
            raise ApiError(
                409,
                "CHECKIN_WINDOW_CLOSED",
                f"已超过签到截止时间 {window_end.strftime('%H:%M')}，不得签到；"
                "系统将按 V1 未签到处理（BR-08、ST-16）",
            )
        if seat_code != row["seat_code"]:
            raise ApiError(
                409,
                "SEAT_MISMATCH",
                f"所扫/输入座位号 {seat_code} 与预约单座位 {row['seat_code']} 不一致（ST-16）",
            )

        before_status = row["status"]
        cursor = conn.execute(
            """
            INSERT INTO checkins (reservation_id, checkin_at, method)
            VALUES (?, ?, ?)
            """,
            (reservation_id, now_s, method),
        )
        conn.execute("UPDATE reservations SET status='使用中' WHERE id=?", (reservation_id,))
        conn.execute("UPDATE seats SET status='使用中' WHERE id=?", (row["seat_id"],))
        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="签到",
            target_type="预约单",
            target_id=row["reservation_no"],
            before={"reservation_status": before_status, "seat_status": row["seat_status"]},
            after={
                "reservation_status": "使用中",
                "seat_status": "使用中",
                "checkin_at": now_s,
                "method": method,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "checkin_id": int(cursor.lastrowid),
            "reservation_id": reservation_id,
            "reservation_no": row["reservation_no"],
            "reservation_status": "使用中",
            "seat_code": row["seat_code"],
            "seat_status": "使用中",
            "checkin_at": now_s,
            "method": method,
            "window": {
                "start": window_start.strftime("%H:%M"),
                "end": window_end.strftime("%H:%M"),
            },
        }


def checkout_reservation(user: sqlite3.Row, reservation_id: int) -> dict:
    """签退：记录实际使用时长并释放座位（AC-04-05、ST-06、ST-17）。"""
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    with db.immediate_transaction(conn):
        row = conn.execute(
            """
            SELECT r.*, s.code AS seat_code, s.status AS seat_status,
                   c.id AS checkin_id, c.checkin_at
              FROM reservations r
              JOIN seats s ON s.id = r.seat_id
              LEFT JOIN checkins c ON c.reservation_id = r.id
             WHERE r.id = ?
            """,
            (reservation_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "RESERVATION_NOT_FOUND", "预约单不存在")
        if int(row["user_id"]) != int(user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能签退本人的预约（NFR-07）")
        if row["status"] != "使用中":
            raise ApiError(409, "NOT_USING", f"预约单当前状态为「{row['status']}」，不可签退")
        if row["checkin_at"] is None:
            raise ApiError(409, "CHECKIN_MISSING", "预约单缺少签到记录，无法签退")

        end_dt = datetime.combine(
            parse_date(row["reservation_date"]), parse_hm(row["end_time"])
        )
        if now > end_dt:
            raise ApiError(
                409,
                "CHECKOUT_AFTER_END",
                f"已超过预约结束时刻 {row['end_time']}，将按 V2 未签退由系统处理（BR-09）",
            )
        actual_minutes = max(
            0, int((now - parse_dt(row["checkin_at"])).total_seconds() // 60)
        )
        conn.execute(
            "UPDATE checkins SET checkout_at = ?, actual_minutes = ? WHERE reservation_id = ?",
            (now_s, actual_minutes, reservation_id),
        )
        conn.execute("UPDATE reservations SET status='已完成' WHERE id=?", (reservation_id,))
        new_seat_status = recalculate_seat_status(conn, row["seat_id"])
        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="签退",
            target_type="预约单",
            target_id=row["reservation_no"],
            before={"reservation_status": "使用中", "seat_status": row["seat_status"]},
            after={
                "reservation_status": "已完成",
                "seat_status": new_seat_status,
                "checkout_at": now_s,
                "actual_minutes": actual_minutes,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "reservation_id": reservation_id,
            "reservation_no": row["reservation_no"],
            "reservation_status": "已完成",
            "seat_code": row["seat_code"],
            "seat_status": new_seat_status,
            "checkout_at": now_s,
            "actual_minutes": actual_minutes,
        }


def _send_blacklist_notice(
    conn: sqlite3.Connection,
    user_id: int,
    title: str,
    content: str,
    now_s: str,
) -> None:
    notify_user(conn, user_id, "黑名单状态", title, content, now_s)


def maybe_apply_blacklist(
    conn: sqlite3.Connection, user_id: int, now_s: str
) -> dict | None:
    """有效违约累计达到阈值时自动加入黑名单（AC-05-05、AC-10-01、BR-12、ST-19）。"""
    now = parse_dt(now_s)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        return None
    threshold = db.get_rule_int(conn, "blacklist_threshold")
    active = conn.execute(
        """
        SELECT * FROM blacklists
         WHERE user_id = ? AND status = '生效中' AND expires_at > ?
         ORDER BY expires_at DESC LIMIT 1
        """,
        (user_id, now_s),
    ).fetchone()
    if int(user["effective_violation_count"]) < threshold or active is not None:
        return None

    days = db.get_rule_int(conn, "blacklist_days")
    expires_at = fmt_dt(now + timedelta(days=days))
    cursor = conn.execute(
        """
        INSERT INTO blacklists
            (user_id, reason, source, effective_at, expires_at, status, created_at)
        VALUES (?, ?, '自动', ?, ?, '生效中', ?)
        """,
        (
            user_id,
            f"有效违约累计达到 {threshold} 次",
            now_s,
            expires_at,
            now_s,
        ),
    )
    if user["account_status"] == "锁定":
        conn.execute(
            """
            UPDATE users SET pre_lock_status='黑名单', blacklist_until=?
             WHERE id=?
            """,
            (expires_at, user_id),
        )
    else:
        conn.execute(
            "UPDATE users SET account_status='黑名单', blacklist_until=? WHERE id=?",
            (expires_at, user_id),
        )
    content = (
        f"有效违约累计达到 {threshold} 次，账号进入黑名单；"
        f"黑名单期限至 {expires_at}。期间禁止发起新预约，已有预约可继续签到签退。"
    )
    _send_blacklist_notice(conn, user_id, "黑名单生效通知", content, now_s)
    db.write_audit(
        conn,
        actor_user_id=None,
        actor_name=SYSTEM_ACTOR_NAME,
        actor_role=SYSTEM_ACTOR_ROLE,
        action="黑名单生效",
        target_type="账号",
        target_id=user["student_no"],
        before={
            "account_status": user["account_status"],
            "effective_violation_count": user["effective_violation_count"],
        },
        after={
            "account_status": "黑名单" if user["account_status"] != "锁定" else "锁定（黑名单待生效）",
            "effective_violation_count": user["effective_violation_count"],
            "blacklist_until": expires_at,
        },
        result="成功：达到黑名单阈值",
        created_at=now_s,
    )
    return {
        "id": int(cursor.lastrowid),
        "expires_at": expires_at,
        "threshold": threshold,
    }


def expire_blacklists(conn: sqlite3.Connection, now_s: str) -> int:
    """黑名单期限届满自动恢复账号（AC-10-03、ST-21）。"""
    rows = conn.execute(
        """
        SELECT b.*, u.student_no, u.name AS user_name, u.account_status,
               u.pre_lock_status
          FROM blacklists b
          JOIN users u ON u.id = b.user_id
         WHERE b.status = '生效中' AND b.expires_at <= ?
        """,
        (now_s,),
    ).fetchall()
    count = 0
    for row in rows:
        conn.execute(
            """
            UPDATE blacklists
               SET status='已到期', released_at=?, release_reason='期限届满自动解除'
             WHERE id=?
            """,
            (now_s, row["id"]),
        )
        other_active = conn.execute(
            """
            SELECT COUNT(*) AS n FROM blacklists
             WHERE user_id=? AND id<>? AND status='生效中' AND expires_at > ?
            """,
            (row["user_id"], row["id"], now_s),
        ).fetchone()["n"]
        new_status = row["account_status"]
        if not other_active:
            if row["account_status"] == "锁定":
                conn.execute(
                    """
                    UPDATE users
                       SET pre_lock_status=CASE WHEN pre_lock_status='黑名单' THEN '正常'
                                                ELSE pre_lock_status END,
                           blacklist_until=NULL
                     WHERE id=?
                    """,
                    (row["user_id"],),
                )
                new_status = "锁定"
            else:
                conn.execute(
                    "UPDATE users SET account_status='正常', blacklist_until=NULL WHERE id=?",
                    (row["user_id"],),
                )
                new_status = "正常"
        notify_user(
            conn,
            row["user_id"],
            "黑名单状态",
            "黑名单解除通知",
            f"黑名单期限届满，账号预约权限已恢复；当前账号状态：{new_status}。",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=None,
            actor_name=SYSTEM_ACTOR_NAME,
            actor_role=SYSTEM_ACTOR_ROLE,
            action="黑名单自动解除",
            target_type="账号",
            target_id=row["student_no"],
            before={"account_status": row["account_status"], "blacklist_id": row["id"]},
            after={"account_status": new_status, "record_status": "已到期"},
            result="成功：期限届满",
            created_at=now_s,
        )
        count += 1
    return count


def _create_auto_violation(
    conn: sqlite3.Connection,
    reservation: sqlite3.Row,
    violation_type: str,
    basis: str,
    now: datetime,
    now_s: str,
) -> dict | None:
    """生成一条 V1/V2 违约记录；同一预约同一类型只生成一次（BR-11、AC-05-06）。"""
    existing = conn.execute(
        """
        SELECT id FROM violations
         WHERE reservation_id=? AND violation_type=?
        """,
        (reservation["id"], violation_type),
    ).fetchone()
    if existing is not None:
        return None

    violation_no = (
        "V" + now.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:5].upper()
    )
    user = conn.execute(
        "SELECT * FROM users WHERE id=?", (reservation["user_id"],)
    ).fetchone()
    before_seat_status = reservation["seat_status"]
    before_count = int(user["effective_violation_count"])
    cursor = conn.execute(
        """
        INSERT INTO violations
            (violation_no, user_id, reservation_id, seat_id, violation_type,
             occurred_at, basis, result, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, '已记违约并释放座位', '生效中', ?)
        """,
        (
            violation_no,
            reservation["user_id"],
            reservation["id"],
            reservation["seat_id"],
            violation_type,
            now_s,
            basis,
            now_s,
        ),
    )
    conn.execute("UPDATE reservations SET status='已违约' WHERE id=?", (reservation["id"],))
    new_seat_status = recalculate_seat_status(conn, reservation["seat_id"])
    new_count = before_count + 1
    conn.execute(
        "UPDATE users SET effective_violation_count=? WHERE id=?",
        (new_count, reservation["user_id"]),
    )
    threshold = db.get_rule_int(conn, "blacklist_threshold")
    if threshold >= 2 and new_count == threshold - 1:
        reminder_key = f"user:{reservation['user_id']}:near_blacklist:{threshold}"
        if conn.execute(
            "SELECT 1 FROM notifications WHERE event_key=?", (reminder_key,)
        ).fetchone() is None:
            notify_user(
                conn,
                reservation["user_id"],
                "黑名单提醒",
                "接近黑名单阈值",
                f"当前有效违约 {new_count} 次，达到黑名单阈值（{threshold} 次）前仅剩 1 次。",
                now_s,
                event_key=reminder_key,
            )
    notify_user(
        conn,
        reservation["user_id"],
        "违约记录",
        "违约记录生成通知",
        (
            f"预约单 {reservation['reservation_no']} 生成 {violation_type} 违约记录；"
            f"座位 {reservation['seat_code']} 已释放。当前有效违约次数：{new_count}。"
        ),
        now_s,
    )
    db.write_audit(
        conn,
        actor_user_id=None,
        actor_name=SYSTEM_ACTOR_NAME,
        actor_role=SYSTEM_ACTOR_ROLE,
        action="自动违约判定",
        target_type="违约记录",
        target_id=violation_no,
        before={
            "reservation_status": reservation["status"],
            "seat_status": before_seat_status,
            "effective_violation_count": before_count,
        },
        after={
            "violation_type": violation_type,
            "violation_status": "生效中",
            "reservation_status": "已违约",
            "seat_status": new_seat_status,
            "effective_violation_count": new_count,
        },
        result="成功",
        created_at=now_s,
    )
    blacklist = maybe_apply_blacklist(conn, reservation["user_id"], now_s)
    return {
        "id": int(cursor.lastrowid),
        "violation_no": violation_no,
        "type": violation_type,
        "effective_violation_count": new_count,
        "seat_status": new_seat_status,
        "blacklist": blacklist,
    }


def run_maintenance_scan(
    conn: sqlite3.Connection | None = None, now: datetime | None = None
) -> dict:
    """执行一次维护扫描：预约状态推进、V1/V2 违约、黑名单到期。

    AC-05-01、AC-05-02、AC-05-06、AC-10-03；可由定时线程或管理员手动触发。
    """
    if conn is None:
        conn = db.get_db()
    now = now or get_now()
    now_s = fmt_dt(now)
    counts = {
        "promoted_to_checkin": 0,
        "v1_created": 0,
        "v2_created": 0,
        "blacklists_expired": 0,
        "complaints_auto_closed": 0,
        "reminders_created": 0,
    }
    with db.immediate_transaction(conn):
        # 先处理已到期黑名单与超时投诉，确保后续状态读取最新。
        counts["blacklists_expired"] = expire_blacklists(conn, now_s)
        counts["complaints_auto_closed"] = auto_close_complaints(conn, now_s)

        early = db.get_rule_int(conn, "checkin_early_minutes")
        late = db.get_rule_int(conn, "checkin_late_minutes")

        # ST-11：到达签到窗口起点后，待生效 → 待签到。
        for row in conn.execute(
            "SELECT * FROM reservations WHERE status='待生效'"
        ).fetchall():
            start_dt = datetime.combine(
                parse_date(row["reservation_date"]), parse_hm(row["start_time"])
            )
            window_start = start_dt - timedelta(minutes=early)
            if now >= window_start:
                conn.execute(
                    "UPDATE reservations SET status='待签到' WHERE id=?", (row["id"],)
                )
                counts["promoted_to_checkin"] += 1
                reminder_key = f"reservation:{row['id']}:start_reminder"
                if conn.execute(
                    "SELECT 1 FROM notifications WHERE event_key=?", (reminder_key,)
                ).fetchone() is None:
                    notify_user(
                        conn,
                        row["user_id"],
                        "预约提醒",
                        "预约即将开始",
                        (
                            f"预约单 {row['reservation_no']} 即将开始："
                            f"{row['reservation_date']} {row['start_time']}—{row['end_time']}。"
                            "请按时签到。"
                        ),
                        now_s,
                        event_key=reminder_key,
                    )
                    counts["reminders_created"] += 1

        # 签到截止前提醒：进入预约开始时刻后、截止时刻前，每个预约仅提醒一次。
        for row in conn.execute(
            """
            SELECT r.*, s.code AS seat_code
              FROM reservations r JOIN seats s ON s.id=r.seat_id
             WHERE r.status='待签到'
            """
        ).fetchall():
            start_dt = datetime.combine(
                parse_date(row["reservation_date"]), parse_hm(row["start_time"])
            )
            deadline = start_dt + timedelta(minutes=late)
            if not (start_dt <= now < deadline):
                continue
            reminder_key = f"reservation:{row['id']}:checkin_deadline"
            if conn.execute(
                "SELECT 1 FROM notifications WHERE event_key=?", (reminder_key,)
            ).fetchone() is not None:
                continue
            remaining = max(1, math.ceil((deadline - now).total_seconds() / 60))
            notify_user(
                conn,
                row["user_id"],
                "签到提醒",
                "签到即将截止",
                (
                    f"预约单 {row['reservation_no']}（座位 {row['seat_code']}）"
                    f"签到将在约 {remaining} 分钟后截止，请尽快完成签到。"
                ),
                now_s,
                event_key=reminder_key,
            )
            counts["reminders_created"] += 1

        # V1：超过签到截止时刻仍未签到。
        v1_rows = conn.execute(
            """
            SELECT r.*, s.code AS seat_code, s.status AS seat_status
              FROM reservations r
              JOIN seats s ON s.id = r.seat_id
             WHERE r.status = '待签到'
            """
        ).fetchall()
        for row in v1_rows:
            start_dt = datetime.combine(
                parse_date(row["reservation_date"]), parse_hm(row["start_time"])
            )
            deadline = start_dt + timedelta(minutes=late)
            if now <= deadline:
                continue
            checked = conn.execute(
                "SELECT 1 FROM checkins WHERE reservation_id=?", (row["id"],)
            ).fetchone()
            if checked is not None:
                continue
            created = _create_auto_violation(
                conn,
                row,
                "V1 未签到",
                f"超过签到截止时刻 {deadline.strftime('%H:%M')} 仍未签到（BR-08）",
                now,
                now_s,
            )
            if created is not None:
                counts["v1_created"] += 1

        # V2：超过预约结束时刻仍未签退。
        v2_rows = conn.execute(
            """
            SELECT r.*, s.code AS seat_code, s.status AS seat_status
              FROM reservations r
              JOIN seats s ON s.id = r.seat_id
             WHERE r.status = '使用中'
            """
        ).fetchall()
        for row in v2_rows:
            end_dt = datetime.combine(
                parse_date(row["reservation_date"]), parse_hm(row["end_time"])
            )
            if now <= end_dt:
                continue
            created = _create_auto_violation(
                conn,
                row,
                "V2 未签退",
                f"超过预约结束时刻 {row['end_time']} 仍未签退（BR-09）",
                now,
                now_s,
            )
            if created is not None:
                counts["v2_created"] += 1
    return counts


def submit_violation_appeal(
    user: sqlite3.Row, violation_id: int, data: dict
) -> dict:
    """学生在申诉期内对本人「生效中」记录发起申诉（AC-05-03 前半、BR-14、ST-35）。"""
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    reason = _required_text(data, "reason")
    with db.immediate_transaction(conn):
        row = conn.execute("SELECT * FROM violations WHERE id=?", (violation_id,)).fetchone()
        if row is None:
            raise ApiError(404, "VIOLATION_NOT_FOUND", "违约记录不存在")
        if int(row["user_id"]) != int(user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能申诉本人的违约记录（NFR-07）")
        if row["status"] != "生效中":
            raise ApiError(409, "NOT_APPEALABLE", f"记录当前状态为「{row['status']}」，不可申诉")
        appeal_days = db.get_rule_int(conn, "appeal_days")
        created_at = parse_dt(row["created_at"])
        if now > created_at + timedelta(days=appeal_days):
            raise ApiError(
                409,
                "APPEAL_WINDOW_CLOSED",
                f"距记录生成已超过申诉期 {appeal_days} 个自然日，拒绝申诉（BR-14、ST-38）",
            )
        conn.execute(
            """
            UPDATE violations
               SET status='申诉中', appeal_reason=?, appeal_at=?
             WHERE id=?
            """,
            (reason, now_s, violation_id),
        )
        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="提交申诉",
            target_type="违约记录",
            target_id=row["violation_no"],
            before={"status": row["status"], "appeal_reason": row["appeal_reason"]},
            after={"status": "申诉中", "appeal_reason": reason, "appeal_at": now_s},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": violation_id,
            "violation_no": row["violation_no"],
            "status": "申诉中",
            "appeal_reason": reason,
            "appeal_at": now_s,
        }


def _lift_blacklist_after_recount(
    conn: sqlite3.Connection,
    user_id: int,
    threshold: int,
    now_s: str,
) -> str | None:
    """申诉成立回退计数后，若低于阈值则解除生效中黑名单（ST-36、ST-22）。"""
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None or int(user["effective_violation_count"]) >= threshold:
        return None
    active = conn.execute(
        """
        SELECT * FROM blacklists
         WHERE user_id=? AND status='生效中' AND expires_at > ?
         ORDER BY expires_at DESC LIMIT 1
        """,
        (user_id, now_s),
    ).fetchone()
    if active is None:
        return None
    conn.execute(
        """
        UPDATE blacklists
           SET status='已解除', released_at=?,
               release_reason='申诉成立，有效违约计数回退至阈值以下'
         WHERE id=?
        """,
        (now_s, active["id"]),
    )
    new_status = user["account_status"]
    if user["account_status"] == "锁定":
        conn.execute(
            """
            UPDATE users
               SET pre_lock_status=CASE WHEN pre_lock_status='黑名单' THEN '正常'
                                        ELSE pre_lock_status END,
                   blacklist_until=NULL
             WHERE id=?
            """,
            (user_id,),
        )
    else:
        conn.execute(
            "UPDATE users SET account_status='正常', blacklist_until=NULL WHERE id=?",
            (user_id,),
        )
        new_status = "正常"
    notify_user(
        conn,
        user_id,
        "黑名单状态",
        "黑名单解除通知",
        "申诉成立，有效违约计数回退至阈值以下，黑名单已解除。",
        now_s,
    )
    db.write_audit(
        conn,
        actor_user_id=None,
        actor_name=SYSTEM_ACTOR_NAME,
        actor_role=SYSTEM_ACTOR_ROLE,
        action="申诉成立解除黑名单",
        target_type="账号",
        target_id=user["student_no"],
        before={"account_status": user["account_status"], "blacklist_id": active["id"]},
        after={"account_status": new_status, "record_status": "已解除"},
        result="成功：计数低于阈值",
        created_at=now_s,
    )
    return new_status


def adjudicate_appeal(admin: sqlite3.Row, violation_id: int, data: dict) -> dict:
    """管理员审核申诉：成立撤销并回退计数，不成立保持有效（AC-05-03、AC-05-07）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    decision_raw = str(data.get("decision") or "").strip()
    conclusion = _required_text(data, "conclusion")
    decision_map = {
        "成立": "成立",
        "approve": "成立",
        "approved": "成立",
        "不成立": "不成立",
        "reject": "不成立",
        "rejected": "不成立",
    }
    decision = decision_map.get(decision_raw.lower(), decision_map.get(decision_raw))
    if decision is None:
        raise ApiError(400, "INVALID_DECISION", "decision 只能为「成立」或「不成立」")

    with db.immediate_transaction(conn):
        row = conn.execute(
            """
            SELECT v.*, u.student_no, u.name AS user_name,
                   u.effective_violation_count
              FROM violations v
              JOIN users u ON u.id = v.user_id
             WHERE v.id=?
            """,
            (violation_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "VIOLATION_NOT_FOUND", "违约记录不存在")
        if row["status"] != "申诉中":
            raise ApiError(409, "NOT_IN_APPEAL", f"记录当前状态为「{row['status']}」，无需复核")

        before = {
            "status": row["status"],
            "effective_violation_count": row["effective_violation_count"],
            "appeal_reason": row["appeal_reason"],
        }
        new_count = int(row["effective_violation_count"])
        if decision == "成立":
            new_count = max(0, new_count - 1)
            conn.execute(
                """
                UPDATE violations
                   SET status='申诉成立已撤销', appeal_conclusion=?,
                       appeal_judged_at=?, appeal_judged_by=?, result='申诉成立，撤销记录'
                 WHERE id=?
                """,
                (conclusion, now_s, admin["id"], violation_id),
            )
            conn.execute(
                "UPDATE users SET effective_violation_count=? WHERE id=?",
                (new_count, row["user_id"]),
            )
            threshold = db.get_rule_int(conn, "blacklist_threshold")
            _lift_blacklist_after_recount(conn, row["user_id"], threshold, now_s)
            result_message = "成功：申诉成立，记录撤销并回退计数"
            notice_title = "申诉结果：成立"
        else:
            conn.execute(
                """
                UPDATE violations
                   SET status='申诉不成立已终结', appeal_conclusion=?,
                       appeal_judged_at=?, appeal_judged_by=?
                 WHERE id=?
                """,
                (conclusion, now_s, admin["id"], violation_id),
            )
            result_message = "成功：申诉不成立，记录保持有效"
            notice_title = "申诉结果：不成立"

        notify_user(
            conn,
            row["user_id"],
            "申诉结果",
            notice_title,
            f"违约记录 {row['violation_no']} 的申诉结论：{conclusion}；当前有效违约次数：{new_count}。",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="申诉复核",
            target_type="违约记录",
            target_id=row["violation_no"],
            before=before,
            after={
                "status": "申诉成立已撤销" if decision == "成立" else "申诉不成立已终结",
                "decision": decision,
                "appeal_conclusion": conclusion,
                "effective_violation_count": new_count,
            },
            result=result_message,
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": violation_id,
            "violation_no": row["violation_no"],
            "decision": decision,
            "status": "申诉成立已撤销" if decision == "成立" else "申诉不成立已终结",
            "effective_violation_count": new_count,
            "conclusion": conclusion,
        }


def release_blacklist(admin: sqlite3.Row, blacklist_id: int, data: dict) -> dict:
    """管理员提前解除黑名单，原因必填并留痕（AC-10-04、BR-22、ST-22）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    reason = _required_text(data, "reason")
    with db.immediate_transaction(conn):
        row = conn.execute(
            """
            SELECT b.*, u.student_no, u.name AS user_name, u.account_status
              FROM blacklists b
              JOIN users u ON u.id=b.user_id
             WHERE b.id=?
            """,
            (blacklist_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "BLACKLIST_NOT_FOUND", "黑名单记录不存在")
        if row["status"] != "生效中":
            raise ApiError(409, "BLACKLIST_NOT_ACTIVE", f"黑名单记录当前状态为「{row['status']}」")
        conn.execute(
            """
            UPDATE blacklists
               SET status='已解除', released_at=?, release_reason=?
             WHERE id=?
            """,
            (now_s, reason, blacklist_id),
        )
        other_active = conn.execute(
            """
            SELECT COUNT(*) AS n FROM blacklists
             WHERE user_id=? AND id<>? AND status='生效中' AND expires_at > ?
            """,
            (row["user_id"], blacklist_id, now_s),
        ).fetchone()["n"]
        new_status = row["account_status"]
        if not other_active:
            if row["account_status"] == "锁定":
                conn.execute(
                    """
                    UPDATE users
                       SET pre_lock_status=CASE WHEN pre_lock_status='黑名单' THEN '正常'
                                                ELSE pre_lock_status END,
                           blacklist_until=NULL
                     WHERE id=?
                    """,
                    (row["user_id"],),
                )
                new_status = "锁定"
            else:
                conn.execute(
                    "UPDATE users SET account_status='正常', blacklist_until=NULL WHERE id=?",
                    (row["user_id"],),
                )
                new_status = "正常"
        notify_user(
            conn,
            row["user_id"],
            "黑名单状态",
            "黑名单解除通知",
            f"管理员已提前解除黑名单，原因：{reason}。当前账号状态：{new_status}。",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="提前解除黑名单",
            target_type="账号",
            target_id=row["student_no"],
            before={"blacklist_status": row["status"], "account_status": row["account_status"]},
            after={
                "blacklist_status": "已解除",
                "account_status": new_status,
                "release_reason": reason,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": blacklist_id,
            "student_no": row["student_no"],
            "blacklist_status": "已解除",
            "account_status": new_status,
            "released_at": now_s,
            "release_reason": reason,
        }



def _blacklist_days(data: dict) -> int:
    raw = data.get("days")
    if raw in (None, ""):
        raise ApiError(400, "MISSING_FIELD", "缺少必填字段：days")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise ApiError(400, "INVALID_FIELD", "days 必须为正整数")
    if days < 1 or days > 365:
        raise ApiError(400, "INVALID_FIELD", "days 必须在 1—365 天之间")
    return days


def add_blacklist(admin: sqlite3.Row, data: dict) -> dict:
    """管理员直接加入黑名单，填写原因与期限（ST-20、BR-22）。"""
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    student_no = _required_text(data, "student_no")
    reason = _required_text(data, "reason")
    days = _blacklist_days(data)
    with db.immediate_transaction(conn):
        user = conn.execute(
            "SELECT * FROM users WHERE student_no=? AND role='student'", (student_no,)
        ).fetchone()
        if user is None:
            raise ApiError(404, "STUDENT_NOT_FOUND", "学生不存在")
        active = conn.execute(
            """
            SELECT id FROM blacklists
             WHERE user_id=? AND status='生效中' AND expires_at > ?
            """,
            (user["id"], now_s),
        ).fetchone()
        if active is not None:
            raise ApiError(409, "BLACKLIST_ALREADY_ACTIVE", "该学生已有生效中的黑名单记录")
        expires_at = fmt_dt(now + timedelta(days=days))
        cursor = conn.execute(
            """
            INSERT INTO blacklists
                (user_id, reason, source, effective_at, expires_at, status, created_by, created_at)
            VALUES (?, ?, '管理员', ?, ?, '生效中', ?, ?)
            """,
            (user["id"], reason, now_s, expires_at, admin["id"], now_s),
        )
        if user["account_status"] == "锁定":
            conn.execute(
                "UPDATE users SET pre_lock_status='黑名单', blacklist_until=? WHERE id=?",
                (expires_at, user["id"]),
            )
        else:
            conn.execute(
                "UPDATE users SET account_status='黑名单', blacklist_until=? WHERE id=?",
                (expires_at, user["id"]),
            )
        notify_user(
            conn,
            user["id"],
            "黑名单状态",
            "黑名单生效通知",
            f"管理员已将账号加入黑名单，期限至 {expires_at}；原因：{reason}。",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="管理员加入黑名单",
            target_type="账号",
            target_id=student_no,
            before={"account_status": user["account_status"], "blacklist_until": user["blacklist_until"]},
            after={"account_status": "黑名单", "blacklist_until": expires_at, "reason": reason, "days": days},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": int(cursor.lastrowid),
            "student_no": student_no,
            "reason": reason,
            "effective_at": now_s,
            "expires_at": expires_at,
            "days": days,
            "status": "生效中",
        }


def extend_blacklist(admin: sqlite3.Row, blacklist_id: int, data: dict) -> dict:
    """管理员延长黑名单期限，填写原因与延长期限（ST-21、BR-22）。"""
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    reason = _required_text(data, "reason")
    days = _blacklist_days(data)
    with db.immediate_transaction(conn):
        row = conn.execute(
            """
            SELECT b.*, u.student_no, u.name AS user_name, u.account_status
              FROM blacklists b JOIN users u ON u.id=b.user_id
             WHERE b.id=?
            """,
            (blacklist_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "BLACKLIST_NOT_FOUND", "黑名单记录不存在")
        if row["status"] != "生效中":
            raise ApiError(409, "BLACKLIST_NOT_ACTIVE", f"黑名单记录当前状态为「{row['status']}」")
        current_expiry = parse_dt(row["expires_at"])
        base = max(now, current_expiry)
        new_expiry = fmt_dt(base + timedelta(days=days))
        conn.execute(
            "UPDATE blacklists SET expires_at=? WHERE id=?", (new_expiry, blacklist_id)
        )
        if row["account_status"] == "锁定":
            conn.execute(
                "UPDATE users SET pre_lock_status='黑名单', blacklist_until=? WHERE id=?",
                (new_expiry, row["user_id"]),
            )
        else:
            conn.execute(
                "UPDATE users SET account_status='黑名单', blacklist_until=? WHERE id=?",
                (new_expiry, row["user_id"]),
            )
        notify_user(
            conn,
            row["user_id"],
            "黑名单状态",
            "黑名单延期通知",
            f"黑名单期限已延长 {days} 天，至 {new_expiry}；原因：{reason}。",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="黑名单延期",
            target_type="账号",
            target_id=row["student_no"],
            before={"expires_at": row["expires_at"], "account_status": row["account_status"]},
            after={"expires_at": new_expiry, "days": days, "reason": reason},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": blacklist_id,
            "student_no": row["student_no"],
            "previous_expires_at": row["expires_at"],
            "expires_at": new_expiry,
            "days": days,
            "reason": reason,
            "status": "生效中",
        }



def update_my_contact(user: sqlite3.Row, data: dict) -> dict:
    """学生/用户修改本人联系方式；学号与姓名不可改（FR-08、V1.6）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    for field in ("student_no", "name", "role", "account_status"):
        if field in data:
            raise ApiError(400, "IMMUTABLE_FIELD", f"{field} 不允许在本接口修改")
    contact = _required_text(data, "contact")
    if not contact:
        raise ApiError(400, "MISSING_FIELD", "缺少必填字段：contact")
    if len(contact) > 100:
        raise ApiError(400, "INVALID_FIELD", "联系方式长度不能超过 100")
    with db.immediate_transaction(conn):
        row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        conn.execute(
            "UPDATE users SET contact=? WHERE id=?", (contact, user["id"])
        )
        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="修改联系方式",
            target_type="账号",
            target_id=row["student_no"],
            before={"contact_masked": mask_contact(row["contact"])},
            after={"contact_masked": mask_contact(contact)},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
    return {"id": user["id"], "student_no": row["student_no"], "contact": contact}


def list_users_for_sysadmin(filters: dict) -> dict:
    """系统管理员查询用户；联系方式脱敏（FR-08、权限矩阵第 26 行）。"""
    conn = db.get_db()
    clauses = []
    params = []
    if filters.get("student_no"):
        clauses.append("student_no LIKE ?")
        params.append(f"%{filters['student_no']}%")
    if filters.get("name"):
        clauses.append("name LIKE ?")
        params.append(f"%{filters['name']}%")
    if filters.get("role"):
        clauses.append("role=?")
        params.append(filters["role"])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    page = int(filters.get("page") or 1)
    page_size = int(filters.get("page_size") or 20)
    total = conn.execute(f"SELECT COUNT(*) AS n FROM users{where}", params).fetchone()["n"]
    rows = conn.execute(
        f"SELECT * FROM users{where} ORDER BY role, student_no LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = [
        {
            "id": row["id"],
            "student_no": row["student_no"],
            "name": row["name"],
            "department": row["department"],
            "role": row["role"],
            "account_status": row["account_status"],
            "effective_violation_count": row["effective_violation_count"],
            "contact_masked": mask_contact(row["contact"]),
        }
        for row in rows
    ]
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if total else 0,
        },
    }


def admin_assignment_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT a.id, a.admin_user_id, a.room_id, a.created_at,
               u.student_no AS admin_student_no, u.name AS admin_name,
               r.code AS room_code, r.name AS room_name
          FROM admin_room_assignments a
          JOIN users u ON u.id=a.admin_user_id
          JOIN rooms r ON r.id=a.room_id
         ORDER BY u.student_no, r.code
        """
    ).fetchall()
    return [dict(row) for row in rows]


def grant_admin_room(admin: sqlite3.Row, data: dict) -> dict:
    """系统管理员授予管理员—自习室授权（BR-21、V1.6）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    admin_no = _required_text(data, "admin_student_no")
    try:
        room_id = int(_required_text(data, "room_id"))
    except ValueError:
        raise ApiError(400, "INVALID_FIELD", "room_id 必须为整数")
    with db.immediate_transaction(conn):
        target = conn.execute(
            "SELECT * FROM users WHERE student_no=? AND role='admin'", (admin_no,)
        ).fetchone()
        if target is None:
            raise ApiError(404, "ADMIN_NOT_FOUND", "自习室管理员不存在")
        room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        if room is None:
            raise ApiError(404, "ROOM_NOT_FOUND", "自习室不存在")
        existing = conn.execute(
            "SELECT id FROM admin_room_assignments WHERE admin_user_id=? AND room_id=?",
            (target["id"], room_id),
        ).fetchone()
        if existing is not None:
            raise ApiError(409, "ASSIGNMENT_EXISTS", "该管理员已拥有此自习室授权")
        cursor = conn.execute(
            "INSERT INTO admin_room_assignments (admin_user_id, room_id, created_at) VALUES (?, ?, ?)",
            (target["id"], room_id, now_s),
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="授予管理员授权",
            target_type="管理员授权",
            target_id=f"{admin_no}/{room['code']}",
            before=None,
            after={"admin_student_no": admin_no, "room_id": room_id, "room_code": room["code"]},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": int(cursor.lastrowid),
            "admin_student_no": admin_no,
            "room_id": room_id,
            "room_code": room["code"],
            "room_name": room["name"],
        }


def revoke_admin_room(admin: sqlite3.Row, data: dict) -> dict:
    """系统管理员撤销管理员—自习室授权（BR-21、V1.6）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    admin_no = _required_text(data, "admin_student_no")
    try:
        room_id = int(_required_text(data, "room_id"))
    except ValueError:
        raise ApiError(400, "INVALID_FIELD", "room_id 必须为整数")
    with db.immediate_transaction(conn):
        target = conn.execute(
            "SELECT * FROM users WHERE student_no=? AND role='admin'", (admin_no,)
        ).fetchone()
        if target is None:
            raise ApiError(404, "ADMIN_NOT_FOUND", "自习室管理员不存在")
        room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        if room is None:
            raise ApiError(404, "ROOM_NOT_FOUND", "自习室不存在")
        existing = conn.execute(
            "SELECT id FROM admin_room_assignments WHERE admin_user_id=? AND room_id=?",
            (target["id"], room_id),
        ).fetchone()
        if existing is None:
            raise ApiError(404, "ASSIGNMENT_NOT_FOUND", "授权记录不存在")
        conn.execute("DELETE FROM admin_room_assignments WHERE id=?", (existing["id"],))
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="撤销管理员授权",
            target_type="管理员授权",
            target_id=f"{admin_no}/{room['code']}",
            before={"admin_student_no": admin_no, "room_id": room_id, "room_code": room["code"]},
            after=None,
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {"admin_student_no": admin_no, "room_id": room_id, "room_code": room["code"]}


def credit_summary(conn: sqlite3.Connection, user_id: int) -> dict:
    """学生本人信用状态、剩余解除时间与解除条件（AC-10-05、FR-10）。"""
    now = get_now()
    now_s = fmt_dt(now)
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "登录账号不存在")
    active = conn.execute(
        """
        SELECT * FROM blacklists
         WHERE user_id=? AND status='生效中' AND expires_at > ?
         ORDER BY expires_at DESC LIMIT 1
        """,
        (user_id, now_s),
    ).fetchone()
    threshold = db.get_rule_int(conn, "blacklist_threshold")
    remaining_minutes = None
    expires_at = None
    if active is not None:
        expires_at = active["expires_at"]
        remaining_minutes = minutes_until(now, parse_dt(expires_at))
    return {
        "account_status": user["account_status"],
        "is_blacklisted": active is not None or user["account_status"] == "黑名单",
        "effective_violation_count": user["effective_violation_count"],
        "blacklist_threshold": threshold,
        "blacklist_until": expires_at or user["blacklist_until"],
        "remaining_minutes": remaining_minutes,
        "release_conditions": [
            "黑名单期限届满后由系统自动解除",
            "对导致黑名单的违约记录申诉成立并回退计数后可提前解除",
            "管理员核实特殊情况后可填写原因并提前解除",
        ],
        "active_blacklist_record": dict(active) if active is not None else None,
    }


# ---------------------------------------------------------------------------
# Sprint 3：资源维护、实时座位、V3 手动违约、座位历史
# FR-02、FR-07；AC-02-01—04、AC-07-01—06
# ---------------------------------------------------------------------------


def get_admin_rooms(conn: sqlite3.Connection, admin_user_id: int) -> list[sqlite3.Row]:
    role_row = conn.execute(
        "SELECT role FROM users WHERE id=?", (admin_user_id,)
    ).fetchone()
    if role_row is not None and role_row["role"] == "sysadmin":
        return conn.execute(
            "SELECT * FROM rooms ORDER BY building, name, id"
        ).fetchall()
    return conn.execute(
        """
        SELECT r.* FROM rooms r
          JOIN admin_room_assignments a ON a.room_id = r.id
         WHERE a.admin_user_id = ?
         ORDER BY r.building, r.name, r.id
        """,
        (admin_user_id,),
    ).fetchall()


def resources_snapshot(conn: sqlite3.Connection, admin: sqlite3.Row) -> dict:
    """返回当前管理员授权范围内的自习室—区域—座位三级资源（FR-02）。"""
    rooms = get_admin_rooms(conn, int(admin["id"]))
    output = []
    for room in rooms:
        zones = conn.execute(
            "SELECT * FROM zones WHERE room_id=? ORDER BY sort_order, id",
            (room["id"],),
        ).fetchall()
        zone_output = []
        for zone in zones:
            seats = conn.execute(
                "SELECT * FROM seats WHERE zone_id=? ORDER BY code",
                (zone["id"],),
            ).fetchall()
            zone_output.append({**dict(zone), "seats": [dict(seat) for seat in seats]})
        output.append({**dict(room), "zones": zone_output})
    return {"rooms": output}


def create_room(admin: sqlite3.Row, data: dict) -> dict:
    """新增自习室并授权给当前管理员（FR-02、权限矩阵第 15 行）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    code = _required_text(data, "code")
    name = _required_text(data, "name")
    building = _required_text(data, "building")
    floor = _required_text(data, "floor")
    open_from_text = _required_text(data, "open_from")
    open_to_text = _required_text(data, "open_to")
    try:
        open_from = parse_hm(open_from_text)
        open_to = parse_hm(open_to_text)
    except ValueError as exc:
        raise ApiError(400, "INVALID_TIME", str(exc))
    if open_to <= open_from:
        raise ApiError(400, "INVALID_TIME_RANGE", "关闭时间必须晚于开放时间")
    status = str(data.get("status") or "开放").strip()
    if status not in ("开放", "关闭"):
        raise ApiError(400, "INVALID_STATUS", "自习室状态只能为开放或关闭")

    with db.immediate_transaction(conn):
        try:
            cursor = conn.execute(
                """
                INSERT INTO rooms
                    (code, name, building, floor, location, open_from, open_to,
                     status, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    name,
                    building,
                    floor,
                    str(data.get("location") or "").strip() or None,
                    hm_text(open_from),
                    hm_text(open_to),
                    status,
                    str(data.get("note") or "").strip() or None,
                    now_s,
                ),
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, "ROOM_CODE_EXISTS", f"自习室编号 {code} 已存在")
        room_id = int(cursor.lastrowid)
        if admin["role"] != "sysadmin":
            conn.execute(
                """
                INSERT INTO admin_room_assignments (admin_user_id, room_id, created_at)
                VALUES (?, ?, ?)
                """,
                (admin["id"], room_id, now_s),
            )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="新增自习室",
            target_type="自习室",
            target_id=code,
            before=None,
            after={
                "code": code,
                "name": name,
                "building": building,
                "floor": floor,
                "open_from": hm_text(open_from),
                "open_to": hm_text(open_to),
                "status": status,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": room_id,
            "code": code,
            "name": name,
            "building": building,
            "floor": floor,
            "open_from": hm_text(open_from),
            "open_to": hm_text(open_to),
            "status": status,
        }


def create_zone(admin: sqlite3.Row, room_id: int, data: dict) -> dict:
    """在授权自习室下新增区域（AC-02-01、BR-01）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    code = _required_text(data, "code")
    name = _required_text(data, "name")
    zone_type = _required_text(data, "zone_type")
    try:
        sort_order = int(data.get("sort_order") or 0)
    except (TypeError, ValueError):
        raise ApiError(400, "INVALID_SORT_ORDER", "sort_order 必须为整数")

    with db.immediate_transaction(conn):
        room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
        if room is None:
            raise ApiError(404, "ROOM_NOT_FOUND", "自习室不存在")
        require_room_access(conn, admin, room_id)
        try:
            cursor = conn.execute(
                """
                INSERT INTO zones (room_id, code, name, zone_type, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (room_id, code, name, zone_type, sort_order),
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, "ZONE_EXISTS", "同一自习室内区域编号或名称重复")
        zone_id = int(cursor.lastrowid)
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="新增区域",
            target_type="区域",
            target_id=f"{room['code']}/{code}",
            before=None,
            after={
                "room_id": room_id,
                "code": code,
                "name": name,
                "zone_type": zone_type,
                "sort_order": sort_order,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": zone_id,
            "room_id": room_id,
            "code": code,
            "name": name,
            "zone_type": zone_type,
            "sort_order": sort_order,
        }


def create_seat(admin: sqlite3.Row, zone_id: int, data: dict) -> dict:
    """在授权区域下新增座位（AC-02-01、BR-01）；初始状态固定为空闲。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    code = _required_text(data, "code")
    seat_type = _required_text(data, "seat_type")
    position = str(data.get("position") or "").strip() or None

    with db.immediate_transaction(conn):
        zone = conn.execute(
            """
            SELECT z.*, r.name AS room_name, r.code AS room_code
              FROM zones z JOIN rooms r ON r.id=z.room_id WHERE z.id=?
            """,
            (zone_id,),
        ).fetchone()
        if zone is None:
            raise ApiError(404, "ZONE_NOT_FOUND", "区域不存在")
        require_room_access(conn, admin, int(zone["room_id"]))
        try:
            cursor = conn.execute(
                """
                INSERT INTO seats
                    (code, room_id, zone_id, seat_type, status, position,
                     is_bookable, created_at)
                VALUES (?, ?, ?, ?, '空闲', ?, 1, ?)
                """,
                (code, zone["room_id"], zone_id, seat_type, position, now_s),
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, "SEAT_CODE_EXISTS", f"座位编号 {code} 已存在")
        seat_id = int(cursor.lastrowid)
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="新增座位",
            target_type="座位",
            target_id=code,
            before=None,
            after={
                "seat_id": seat_id,
                "room_id": zone["room_id"],
                "zone_id": zone_id,
                "code": code,
                "seat_type": seat_type,
                "position": position,
                "status": "空闲",
                "is_bookable": True,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": seat_id,
            "room_id": zone["room_id"],
            "zone_id": zone_id,
            "code": code,
            "seat_type": seat_type,
            "position": position,
            "status": "空闲",
            "is_bookable": True,
        }


def disable_seat(admin: sqlite3.Row, seat_id: int, data: dict) -> dict:
    """停用座位并取消未来有效预约，不记违约（AC-02-04、ST-08、BR-23）。"""
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    reason = _required_text(data, "reason")
    with db.immediate_transaction(conn):
        seat = require_seat_access(conn, admin, seat_id)
        if seat["status"] == "停用":
            raise ApiError(409, "SEAT_ALREADY_DISABLED", "该座位已处于停用状态")
        before_status = seat["status"]
        before_bookable = bool(seat["is_bookable"])
        future_reservations = conn.execute(
            """
            SELECT r.*, u.name AS user_name
              FROM reservations r
              JOIN users u ON u.id=r.user_id
             WHERE r.seat_id = ? AND r.status IN ('待生效', '待签到')
             ORDER BY r.reservation_date, r.start_time
            """,
            (seat_id,),
        ).fetchall()
        canceled = []
        for reservation in future_reservations:
            start_dt = datetime.combine(
                parse_date(reservation["reservation_date"]),
                parse_hm(reservation["start_time"]),
            )
            if start_dt <= now:
                continue
            conn.execute(
                """
                UPDATE reservations
                   SET status='已取消', cancelled_at=?,
                       cancel_reason=?
                 WHERE id=?
                """,
                (now_s, f"座位停用：{reason}", reservation["id"]),
            )
            notify_user(
                conn,
                reservation["user_id"],
                "预约变更",
                "预约已取消通知",
                (
                    f"因座位 {seat['code']} 停用，预约单 {reservation['reservation_no']} 已自动取消；"
                    f"取消不记违约。原因：{reason}。"
                ),
                now_s,
            )
            db.write_audit(
                conn,
                actor_user_id=admin["id"],
                actor_name=admin["name"],
                actor_role=role_label(admin["role"]),
                action="座位停用自动取消预约",
                target_type="预约单",
                target_id=reservation["reservation_no"],
                before={"reservation_status": reservation["status"]},
                after={"reservation_status": "已取消", "cancel_reason": f"座位停用：{reason}"},
                result="成功：不记违约",
                created_at=now_s,
                ip_address=request.remote_addr,
            )
            canceled.append(reservation["reservation_no"])

        conn.execute(
            "UPDATE seats SET status='停用', is_bookable=0 WHERE id=?", (seat_id,)
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="停用座位",
            target_type="座位",
            target_id=seat["code"],
            before={"status": before_status, "is_bookable": before_bookable},
            after={
                "status": "停用",
                "is_bookable": False,
                "reason": reason,
                "cancelled_reservations": canceled,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "seat_id": seat_id,
            "seat_code": seat["code"],
            "status": "停用",
            "is_bookable": False,
            "reason": reason,
            "cancelled_reservations": canceled,
        }


def restore_seat(admin: sqlite3.Row, seat_id: int, data: dict) -> dict:
    """恢复停用座位，必须填写恢复说明（ST-09、BR-22）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    reason = _required_text(data, "reason")
    with db.immediate_transaction(conn):
        seat = require_seat_access(conn, admin, seat_id)
        if seat["status"] != "停用":
            raise ApiError(409, "SEAT_NOT_DISABLED", "该座位当前不是停用状态")
        conn.execute(
            "UPDATE seats SET status='空闲', is_bookable=1 WHERE id=?", (seat_id,)
        )
        new_status = recalculate_seat_status(conn, seat_id)
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="恢复座位",
            target_type="座位",
            target_id=seat["code"],
            before={"status": "停用", "is_bookable": bool(seat["is_bookable"])},
            after={"status": new_status, "is_bookable": True, "reason": reason},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "seat_id": seat_id,
            "seat_code": seat["code"],
            "status": new_status,
            "is_bookable": True,
            "reason": reason,
        }


def admin_release_reservation(
    admin: sqlite3.Row, reservation_id: int, data: dict
) -> dict:
    """管理员提前释放座位/取消预约，原因必填（AC-07-06、ST-13、BR-22）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    reason = _required_text(data, "reason")
    with db.immediate_transaction(conn):
        row = conn.execute(
            """
            SELECT r.*, s.code AS seat_code, s.status AS seat_status,
                   ro.name AS room_name, u.name AS user_name
              FROM reservations r
              JOIN seats s ON s.id=r.seat_id
              JOIN rooms ro ON ro.id=r.room_id
              JOIN users u ON u.id=r.user_id
             WHERE r.id=?
            """,
            (reservation_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "RESERVATION_NOT_FOUND", "预约单不存在")
        require_room_access(conn, admin, int(row["room_id"]))
        if row["status"] not in ACTIVE_STATUSES:
            raise ApiError(409, "RESERVATION_NOT_ACTIVE", f"预约单当前状态为「{row['status']}」，不可释放")
        conn.execute(
            """
            UPDATE reservations
               SET status='已取消', cancelled_at=?, cancel_reason=?
             WHERE id=?
            """,
            (now_s, f"管理员提前释放：{reason}", reservation_id),
        )
        new_seat_status = recalculate_seat_status(conn, row["seat_id"])
        notify_user(
            conn,
            row["user_id"],
            "预约变更",
            "预约已取消通知",
            (
                f"预约单 {row['reservation_no']} 已被管理员提前释放；原因：{reason}。"
                "如有异议可联系自习室管理员。"
            ),
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="提前释放座位",
            target_type="预约单",
            target_id=row["reservation_no"],
            before={
                "reservation_status": row["status"],
                "seat_status": row["seat_status"],
            },
            after={
                "reservation_status": "已取消",
                "seat_status": new_seat_status,
                "reason": reason,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "reservation_id": reservation_id,
            "reservation_no": row["reservation_no"],
            "status": "已取消",
            "seat_id": row["seat_id"],
            "seat_code": row["seat_code"],
            "seat_status": new_seat_status,
            "reason": reason,
            "cancelled_at": now_s,
        }


def manual_violation(admin: sqlite3.Row, seat_id: int, data: dict) -> dict:
    """管理员现场登记 V3 违约并释放座位（AC-07-02、AC-07-03、ST-31）。"""
    conn = db.get_db()
    now = get_now()
    now_s = fmt_dt(now)
    reason = _required_text(data, "reason")
    student_no = str(data.get("student_no") or "").strip()
    with db.immediate_transaction(conn):
        seat = require_seat_access(conn, admin, seat_id)
        active_reservation = conn.execute(
            """
            SELECT r.*, u.name AS user_name, u.student_no
              FROM reservations r
              JOIN users u ON u.id=r.user_id
             WHERE r.seat_id = ?
               AND r.status IN ('待生效', '待签到', '使用中')
             ORDER BY CASE r.status WHEN '使用中' THEN 0 WHEN '待签到' THEN 1 ELSE 2 END,
                      r.start_time
             LIMIT 1
            """,
            (seat_id,),
        ).fetchone()
        if active_reservation is not None:
            if student_no and student_no != active_reservation["student_no"]:
                raise ApiError(409, "STUDENT_MISMATCH", "指定学号与该座位当前有效预约的学生不一致")
            target_user = conn.execute(
                "SELECT * FROM users WHERE id=?", (active_reservation["user_id"],)
            ).fetchone()
        else:
            if not student_no:
                raise ApiError(
                    400,
                    "STUDENT_REQUIRED",
                    "该座位没有有效预约，现场登记 V3 违约时必须提供被登记学生学号",
                )
            target_user = conn.execute(
                "SELECT * FROM users WHERE student_no=? AND role='student'", (student_no,)
            ).fetchone()
            if target_user is None:
                raise ApiError(404, "STUDENT_NOT_FOUND", "被登记学生不存在")

        if active_reservation is not None:
            duplicate = conn.execute(
                """
                SELECT id FROM violations
                 WHERE reservation_id=? AND violation_type='V3 管理员手动登记'
                """,
                (active_reservation["id"],),
            ).fetchone()
            if duplicate is not None:
                raise ApiError(409, "DUPLICATE_VIOLATION", "该预约单已存在 V3 手动违约记录")

        before_seat_status = seat["status"]
        before_count = int(target_user["effective_violation_count"])
        violation_no = (
            "V3" + now.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:5].upper()
        )
        cursor = conn.execute(
            """
            INSERT INTO violations
                (violation_no, user_id, reservation_id, seat_id, violation_type,
                 occurred_at, basis, result, status, registered_by, created_at)
            VALUES (?, ?, ?, ?, 'V3 管理员手动登记', ?, ?, '已记 V3 违约并释放座位',
                    '生效中', ?, ?)
            """,
            (
                violation_no,
                target_user["id"],
                active_reservation["id"] if active_reservation is not None else None,
                seat_id,
                now_s,
                f"管理员现场登记：{reason}",
                admin["id"],
                now_s,
            ),
        )
        reservation_status = None
        if active_reservation is not None:
            reservation_status = active_reservation["status"]
            conn.execute(
                "UPDATE reservations SET status='已违约' WHERE id=?",
                (active_reservation["id"],),
            )
            recalculate_seat_status(conn, seat_id)
        new_count = before_count + 1
        conn.execute(
            "UPDATE users SET effective_violation_count=? WHERE id=?",
            (new_count, target_user["id"]),
        )
        notify_user(
            conn,
            target_user["id"],
            "违约记录",
            "违约记录生成通知",
            (
                f"管理员登记 V3 违约：座位 {seat['code']}；原因：{reason}。"
                f"当前有效违约次数：{new_count}。"
            ),
            now_s,
        )
        blacklist = maybe_apply_blacklist(conn, int(target_user["id"]), now_s)
        after_seat_status = conn.execute(
            "SELECT status FROM seats WHERE id=?", (seat_id,)
        ).fetchone()["status"]
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="手动违约登记",
            target_type="违约记录",
            target_id=violation_no,
            before={
                "seat_status": before_seat_status,
                "reservation_status": reservation_status,
                "effective_violation_count": before_count,
            },
            after={
                "violation_type": "V3 管理员手动登记",
                "seat_status": after_seat_status,
                "reservation_status": "已违约" if active_reservation is not None else None,
                "effective_violation_count": new_count,
                "reason": reason,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": int(cursor.lastrowid),
            "violation_no": violation_no,
            "violation_type": "V3 管理员手动登记",
            "student_no": target_user["student_no"],
            "seat_code": seat["code"],
            "seat_status": after_seat_status,
            "effective_violation_count": new_count,
            "reason": reason,
            "blacklist": blacklist,
        }


def realtime_snapshot(conn: sqlite3.Connection, admin: sqlite3.Row, room_id: int | None) -> dict:
    """管理员实时座位视图（AC-07-01）。仅返回授权自习室，使用者脱敏。"""
    rooms = get_admin_rooms(conn, int(admin["id"]))
    if not rooms:
        raise ApiError(403, "ROOM_FORBIDDEN", "当前管理员没有任何被授权的自习室")
    if room_id is None:
        room_id = int(rooms[0]["id"])
    require_room_access(conn, admin, room_id)
    room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if room is None:
        raise ApiError(404, "ROOM_NOT_FOUND", "自习室不存在")

    active_rows = conn.execute(
        """
        SELECT r.*, u.name AS user_name, u.student_no
          FROM reservations r
          JOIN users u ON u.id=r.user_id
         WHERE r.room_id=?
           AND r.status IN ('待生效', '待签到', '使用中')
         ORDER BY CASE r.status WHEN '使用中' THEN 0 WHEN '待签到' THEN 1 ELSE 2 END,
                  r.reservation_date, r.start_time
        """,
        (room_id,),
    ).fetchall()
    by_seat: dict[int, list[sqlite3.Row]] = {}
    for row in active_rows:
        by_seat.setdefault(int(row["seat_id"]), []).append(row)

    zones = []
    for zone in conn.execute(
        "SELECT * FROM zones WHERE room_id=? ORDER BY sort_order, id", (room_id,)
    ).fetchall():
        seat_output = []
        for seat in conn.execute(
            "SELECT * FROM seats WHERE zone_id=? ORDER BY code", (zone["id"],)
        ).fetchall():
            active = by_seat.get(int(seat["id"]), [])
            reservation = active[0] if active else None
            occupant = None
            if reservation is not None and reservation["status"] == "使用中":
                occupant = {
                    "name_masked": mask_name(reservation["user_name"]),
                    "student_no_masked": mask_student_no(reservation["student_no"]),
                }
            seat_output.append(
                {
                    **dict(seat),
                    "status": seat["status"],
                    "current_occupant": occupant,
                    "reservation": (
                        {
                            "reservation_id": reservation["id"],
                            "reservation_no": reservation["reservation_no"],
                            "date": reservation["reservation_date"],
                            "start_time": reservation["start_time"],
                            "end_time": reservation["end_time"],
                            "status": reservation["status"],
                            "name_masked": mask_name(reservation["user_name"]),
                        }
                        if reservation is not None
                        else None
                    ),
                }
            )
        zones.append({**dict(zone), "seats": seat_output})
    return {
        "room": dict(room),
        "rooms": [dict(item) for item in rooms],
        "zones": zones,
        "refreshed_at": fmt_dt(get_now()),
    }


def seat_history(conn: sqlite3.Connection, admin: sqlite3.Row, seat_id: int) -> dict:
    """座位历史使用/预约记录，使用者脱敏（AC-07-05、FR-07）。"""
    seat = require_seat_access(conn, admin, seat_id)
    rows = conn.execute(
        """
        SELECT r.*, u.name AS user_name, u.student_no,
               c.checkin_at, c.method, c.checkout_at, c.actual_minutes
          FROM reservations r
          JOIN users u ON u.id=r.user_id
          LEFT JOIN checkins c ON c.reservation_id=r.id
         WHERE r.seat_id=?
         ORDER BY r.reservation_date DESC, r.start_time DESC, r.id DESC
        """,
        (seat_id,),
    ).fetchall()
    history = []
    for row in rows:
        violation_rows = conn.execute(
            """
            SELECT violation_no, violation_type, status, occurred_at
              FROM violations WHERE reservation_id=? ORDER BY id
            """,
            (row["id"],),
        ).fetchall()
        history.append(
            {
                "reservation_id": row["id"],
                "reservation_no": row["reservation_no"],
                "date": row["reservation_date"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "status": row["status"],
                "user_masked": mask_name(row["user_name"]),
                "student_no_masked": mask_student_no(row["student_no"]),
                "checkin_at": row["checkin_at"],
                "checkin_method": row["method"],
                "checkout_at": row["checkout_at"],
                "actual_minutes": row["actual_minutes"],
                "violations": [dict(item) for item in violation_rows],
            }
        )
    return {
        "seat": {
            "id": seat["id"],
            "code": seat["code"],
            "status": seat["status"],
            "seat_type": seat["seat_type"],
            "position": seat["position"],
            "room_id": seat["room_id"],
            "room_name": seat["room_name"],
            "zone_id": seat["zone_id"],
            "zone_name": seat["zone_name"],
        },
        "history": history,
    }


# ---------------------------------------------------------------------------
# Sprint 4：记录查询分页与审计日志
# FR-06、FR-14；AC-06-02—04、AC-14-01—04
# ---------------------------------------------------------------------------


def _positive_int_arg(name: str, default: int, maximum: int = 100) -> int:
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, "INVALID_PAGINATION", f"{name} 必须为正整数")
    if value < 1 or value > maximum:
        raise ApiError(400, "INVALID_PAGINATION", f"{name} 必须在 1—{maximum} 之间")
    return value


def record_query_args() -> dict:
    """读取预约记录筛选与分页参数（AC-06-02—04）。"""
    date_from = request.args.get("date_from", "").strip() or None
    date_to = request.args.get("date_to", "").strip() or None
    status = request.args.get("status", "").strip() or None
    room_id = _optional_int_arg("room_id")
    allowed_statuses = ("待生效", "待签到", "使用中", "已完成", "已取消", "已违约")
    if status and status not in allowed_statuses:
        raise ApiError(400, "INVALID_STATUS", "status 取值不合法")
    for label, value in (("date_from", date_from), ("date_to", date_to)):
        if value:
            try:
                parse_date(value)
            except ValueError:
                raise ApiError(400, "INVALID_DATE", f"{label} 格式应为 YYYY-MM-DD")
    if date_from and date_to and date_from > date_to:
        raise ApiError(400, "INVALID_DATE_RANGE", "date_from 不能晚于 date_to")
    return {
        "date_from": date_from,
        "date_to": date_to,
        "status": status,
        "room_id": room_id,
        "page": _positive_int_arg("page", 1, 100000),
        "page_size": _positive_int_arg("page_size", 10),
    }


def query_reservations_scoped(user: sqlite3.Row, filters: dict) -> dict:
    """按角色数据范围查询预约记录并分页（AC-06-02、AC-06-03、AC-06-04）。

    R-01 仅本人；R-02 仅授权自习室；R-03/R-04 只读全量。
    """
    conn = db.get_db()
    clauses = ["1=1"]
    params: list[object] = []
    role = user["role"]
    if role == "student":
        clauses.append("r.user_id = ?")
        params.append(user["id"])
    elif role == "admin":
        clauses.append(
            "r.room_id IN (SELECT room_id FROM admin_room_assignments WHERE admin_user_id = ?)"
        )
        params.append(user["id"])
    elif role not in ("sysadmin", "logistics"):
        clauses.append("1=0")
    if filters.get("date_from"):
        clauses.append("r.reservation_date >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("r.reservation_date <= ?")
        params.append(filters["date_to"])
    if filters.get("status"):
        clauses.append("r.status = ?")
        params.append(filters["status"])
    if filters.get("room_id") is not None:
        clauses.append("r.room_id = ?")
        params.append(filters["room_id"])
    where = " AND ".join(clauses)

    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM reservations r WHERE {where}", params
    ).fetchone()["n"]
    page = int(filters["page"])
    page_size = int(filters["page_size"])
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        SELECT r.*, s.code AS seat_code, ro.name AS room_name, ro.building,
               u.name AS user_name, u.student_no
          FROM reservations r
          JOIN seats s ON s.id = r.seat_id
          JOIN rooms ro ON ro.id = r.room_id
          JOIN users u ON u.id = r.user_id
         WHERE {where}
         ORDER BY r.reservation_date DESC, r.start_time DESC, r.id DESC
         LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()
    items = [
        {
            "id": row["id"],
            "reservation_no": row["reservation_no"],
            "reservation_date": row["reservation_date"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "status": row["status"],
            "source": row["source"],
            "admin_reason": row["admin_reason"],
            "room_id": row["room_id"],
            "room_name": row["room_name"],
            "building": row["building"],
            "seat_code": row["seat_code"],
            "student_name_masked": mask_name(row["user_name"]),
            "student_no_masked": mask_student_no(row["student_no"]),
            "created_at": row["created_at"],
            "cancelled_at": row["cancelled_at"],
        }
        for row in rows
    ]
    total_pages = math.ceil(total / page_size) if total else 0
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        },
        "filters": {
            "date_from": filters.get("date_from"),
            "date_to": filters.get("date_to"),
            "status": filters.get("status"),
            "room_id": filters.get("room_id"),
        },
    }


def _safe_json(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def audit_query_args() -> dict:
    """读取审计日志筛选与分页参数（AC-14-04）。"""
    date_from = request.args.get("date_from", "").strip() or None
    date_to = request.args.get("date_to", "").strip() or None
    for label, value in (("date_from", date_from), ("date_to", date_to)):
        if value:
            try:
                parse_date(value)
            except ValueError:
                raise ApiError(400, "INVALID_DATE", f"{label} 格式应为 YYYY-MM-DD")
    if date_from and date_to and date_from > date_to:
        raise ApiError(400, "INVALID_DATE_RANGE", "date_from 不能晚于 date_to")
    return {
        "actor": request.args.get("actor", "").strip() or None,
        "action": request.args.get("action", "").strip() or None,
        "target": request.args.get("target", "").strip() or None,
        "date_from": date_from,
        "date_to": date_to,
        "page": _positive_int_arg("page", 1, 100000),
        "page_size": _positive_int_arg("page_size", 20),
    }


def query_audit_logs(filters: dict) -> dict:
    """按操作人、操作类型、目标、时间区间筛选审计日志并分页（AC-14-04）。"""
    conn = db.get_db()
    clauses = ["1=1"]
    params: list[object] = []
    if filters.get("actor"):
        clauses.append("actor_name LIKE ?")
        params.append(f"%{filters['actor']}%")
    if filters.get("action"):
        clauses.append("action = ?")
        params.append(filters["action"])
    if filters.get("target"):
        clauses.append("(target_type LIKE ? OR target_id LIKE ?)")
        target_like = f"%{filters['target']}%"
        params.extend([target_like, target_like])
    if filters.get("date_from"):
        clauses.append("created_at >= ?")
        params.append(f"{filters['date_from']} 00:00:00")
    if filters.get("date_to"):
        clauses.append("created_at <= ?")
        params.append(f"{filters['date_to']} 23:59:59")
    where = " AND ".join(clauses)
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM audit_logs WHERE {where}", params
    ).fetchone()["n"]
    page = int(filters["page"])
    page_size = int(filters["page_size"])
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        SELECT * FROM audit_logs WHERE {where}
         ORDER BY created_at DESC, id DESC
         LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()
    items = []
    for row in rows:
        before = _safe_json(row["before_json"])
        after = _safe_json(row["after_json"])
        items.append(
            {
                "id": row["id"],
                "actor_user_id": row["actor_user_id"],
                "actor_name": row["actor_name"],
                "actor_role": row["actor_role"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "before": before,
                "after": after,
                "before_text": json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True)
                if before is not None
                else "null",
                "after_text": json.dumps(after, ensure_ascii=False, indent=2, sort_keys=True)
                if after is not None
                else "null",
                "result": row["result"],
                "ip_address": row["ip_address"],
                "created_at": row["created_at"],
            }
        )
    total_pages = math.ceil(total / page_size) if total else 0
    return {
        "logs": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        },
        "filters": {
            "actor": filters.get("actor"),
            "action": filters.get("action"),
            "target": filters.get("target"),
            "date_from": filters.get("date_from"),
            "date_to": filters.get("date_to"),
        },
    }


def list_rule_params(conn: sqlite3.Connection) -> list[dict]:
    """返回全部规则参数及当前值、默认值、范围和确认状态（AC-13-01—03）。"""
    rows = conn.execute("SELECT * FROM rule_params ORDER BY param_no").fetchall()
    return [
        {
            "param_no": row["param_no"],
            "param_key": row["param_key"],
            "name": row["name"],
            "value": row["value"],
            "default_value": row["default_value"],
            "value_type": row["value_type"],
            "min_value": row["min_value"],
            "max_value": row["max_value"],
            "unit": row["unit"],
            "range_text": row["range_text"],
            "description": row["description"],
            "source_nature": row["source_nature"],
            "confirmation_status": row["confirmation_status"],
            "effect_status": (
                "已接入" if row["param_key"] in PARAM_EFFECT_POINTS else "未接入"
            ),
            "effect_point": PARAM_EFFECT_POINTS.get(row["param_key"], "未接入"),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def update_rule_param(admin: sqlite3.Row, param_key: str, data: dict) -> dict:
    """参数更新：类型与范围校验、即时生效并写变更审计（AC-13-01—04）。

    参数变更不回溯修改已生成的业务记录；历史判定继续使用当时结果。
    """
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    value_raw = data.get("value")
    if value_raw in (None, ""):
        raise ApiError(400, "MISSING_FIELD", "缺少必填字段：value")
    with db.immediate_transaction(conn):
        row = conn.execute(
            "SELECT * FROM rule_params WHERE param_key=?", (param_key,)
        ).fetchone()
        if row is None:
            raise ApiError(404, "PARAM_NOT_FOUND", "规则参数不存在")
        if row["value_type"] == "int":
            try:
                normalized = str(int(value_raw))
            except (TypeError, ValueError):
                raise ApiError(400, "INVALID_PARAM_VALUE", "该参数必须为整数")
        elif row["value_type"] == "float":
            try:
                normalized = str(float(value_raw))
            except (TypeError, ValueError):
                raise ApiError(400, "INVALID_PARAM_VALUE", "该参数必须为数值")
        elif row["value_type"] == "bool":
            normalized = "1" if str(value_raw).lower() in ("1", "true", "yes") else "0"
        else:
            normalized = str(value_raw).strip()

        min_value = row["min_value"]
        max_value = row["max_value"]
        unit = row["unit"] or ""
        try:
            numeric_value = float(normalized)
        except (TypeError, ValueError):
            numeric_value = None
        if numeric_value is not None and (
            (min_value is not None and numeric_value < float(min_value))
            or (max_value is not None and numeric_value > float(max_value))
        ):
            raise ApiError(
                400,
                "PARAM_OUT_OF_RANGE",
                f"{row['name']} 必须在 {min_value}—{max_value} {unit} 范围内，"
                f"当前值 {normalized}{unit} 不在范围内（AC-13-02）",
            )
        conn.execute(
            "UPDATE rule_params SET value=?, updated_by=?, updated_at=? WHERE param_key=?",
            (normalized, admin["id"], now_s, param_key),
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="参数变更",
            target_type="规则参数",
            target_id=param_key,
            before={
                "value": row["value"],
                "default_value": row["default_value"],
                "range": f"{min_value}—{max_value}",
            },
            after={
                "value": normalized,
                "range": f"{min_value}—{max_value}",
                "unit": unit,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "param_key": param_key,
            "param_no": row["param_no"],
            "name": row["name"],
            "before": row["value"],
            "after": normalized,
            "min_value": min_value,
            "max_value": max_value,
            "unit": unit,
            "updated_at": now_s,
        }


# ---------------------------------------------------------------------------
# Sprint 5：评价与投诉
# FR-08、FR-09；AC-08-01—04、AC-09-01—06
# ---------------------------------------------------------------------------


def _resolve_evaluation_target(
    conn: sqlite3.Connection, target_type: str, target_id: int
) -> dict:
    if target_type == "座位":
        row = conn.execute(
            """
            SELECT s.id, s.code AS label, s.room_id
              FROM seats s WHERE s.id=?
            """,
            (target_id,),
        ).fetchone()
    elif target_type == "自习室":
        row = conn.execute(
            "SELECT id, name AS label, id AS room_id FROM rooms WHERE id=?",
            (target_id,),
        ).fetchone()
    else:
        raise ApiError(400, "INVALID_TARGET_TYPE", "评价对象类型只能为「座位」或「自习室」")
    if row is None:
        raise ApiError(404, "TARGET_NOT_FOUND", "评价对象不存在")
    return {"target_type": target_type, "target_id": target_id, "label": row["label"], "room_id": row["room_id"]}


def _has_completed_usage(
    conn: sqlite3.Connection, user_id: int, target_type: str, target_id: int
) -> bool:
    if target_type == "座位":
        row = conn.execute(
            """
            SELECT 1 FROM reservations
             WHERE user_id=? AND seat_id=? AND status='已完成' LIMIT 1
            """,
            (user_id, target_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT 1 FROM reservations
             WHERE user_id=? AND room_id=? AND status='已完成' LIMIT 1
            """,
            (user_id, target_id),
        ).fetchone()
    return row is not None


def evaluation_summary(conn: sqlite3.Connection, target_type: str, target_id: int) -> dict:
    """评价聚合：隐藏评价不计入平均分与条数（AC-08-04、BR-19）。"""
    target = _resolve_evaluation_target(conn, target_type, target_id)
    row = conn.execute(
        """
        SELECT COUNT(*) AS n, AVG(rating) AS avg_rating
          FROM evaluations
         WHERE target_type=? AND target_id=? AND hidden=0
        """,
        (target_type, target_id),
    ).fetchone()
    return {
        "target_type": target_type,
        "target_id": target_id,
        "target_label": target["label"],
        "average_rating": round(float(row["avg_rating"]), 2) if row["avg_rating"] is not None else 0,
        "evaluation_count": int(row["n"]),
    }


def submit_evaluation(user: sqlite3.Row, data: dict) -> dict:
    """学生提交评价，须存在真实使用关系且同一对象仅一次（AC-08-01、AC-08-02）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    target_type = _required_text(data, "target_type")
    try:
        target_id = int(_required_text(data, "target_id"))
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        raise ApiError(400, "INVALID_EVALUATION", "target_id 与 rating 必须为整数")
    if rating < 1 or rating > 5:
        raise ApiError(400, "INVALID_RATING", "评分必须为 1—5 的整数")
    comment = str(data.get("comment") or "").strip() or None

    with db.immediate_transaction(conn):
        target = _resolve_evaluation_target(conn, target_type, target_id)
        if not _has_completed_usage(conn, int(user["id"]), target_type, target_id):
            raise ApiError(
                409,
                "REAL_USE_REQUIRED",
                "提交评价前须在该座位/自习室存在已完成的预约（BR-18、AC-08-01）",
            )
        existing = conn.execute(
            """
            SELECT id FROM evaluations
             WHERE user_id=? AND target_type=? AND target_id=?
            """,
            (user["id"], target_type, target_id),
        ).fetchone()
        if existing is not None:
            raise ApiError(409, "ALREADY_EVALUATED", "已评价过该对象，不可重复提交（AC-08-02）")
        evaluation_no = "E" + now_s.replace("-", "").replace(":", "").replace(" ", "")[:14] + "-" + uuid.uuid4().hex[:5].upper()
        cursor = conn.execute(
            """
            INSERT INTO evaluations
                (evaluation_no, user_id, target_type, target_id, rating,
                 comment, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (evaluation_no, user["id"], target_type, target_id, rating, comment, now_s),
        )
        evaluation_id = int(cursor.lastrowid)
        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="提交评价",
            target_type="评价",
            target_id=evaluation_no,
            before=None,
            after={
                "target_type": target_type,
                "target_id": target_id,
                "target_label": target["label"],
                "rating": rating,
                "comment": comment,
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        summary = evaluation_summary(conn, target_type, target_id)
        return {
            "id": evaluation_id,
            "evaluation_no": evaluation_no,
            "target_type": target_type,
            "target_id": target_id,
            "target_label": target["label"],
            "rating": rating,
            "comment": comment,
            "submitted_at": now_s,
            "summary": summary,
        }


def hide_evaluation(admin: sqlite3.Row, evaluation_id: int, data: dict) -> dict:
    """管理员隐藏违规评价，理由必填，隐藏后不计入平均分（AC-08-03、BR-19）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    reason = _required_text(data, "reason")
    with db.immediate_transaction(conn):
        row = conn.execute("SELECT * FROM evaluations WHERE id=?", (evaluation_id,)).fetchone()
        if row is None:
            raise ApiError(404, "EVALUATION_NOT_FOUND", "评价不存在")
        if row["hidden"]:
            raise ApiError(409, "EVALUATION_ALREADY_HIDDEN", "该评价已被隐藏")
        if row["target_type"] == "座位":
            require_seat_access(conn, admin, int(row["target_id"]))
        else:
            require_room_access(conn, admin, int(row["target_id"]))
        conn.execute(
            """
            UPDATE evaluations
               SET hidden=1, hidden_reason=?, hidden_by=?, hidden_at=?
             WHERE id=?
            """,
            (reason, admin["id"], now_s, evaluation_id),
        )
        summary = evaluation_summary(conn, row["target_type"], row["target_id"])
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="隐藏评价",
            target_type="评价",
            target_id=row["evaluation_no"],
            before={"hidden": False},
            after={
                "hidden": True,
                "hidden_reason": reason,
                "target_type": row["target_type"],
                "target_id": row["target_id"],
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return {
            "id": evaluation_id,
            "hidden": True,
            "hidden_reason": reason,
            "summary": summary,
        }


def _evaluation_admin_rows(conn: sqlite3.Connection, admin: sqlite3.Row) -> list[dict]:
    allowed_rooms = set(admin_room_ids(conn, int(admin["id"])))
    rows = conn.execute(
        """
        SELECT e.*, u.name AS user_name, u.student_no
          FROM evaluations e JOIN users u ON u.id=e.user_id
         ORDER BY e.submitted_at DESC, e.id DESC
        """
    ).fetchall()
    output = []
    for row in rows:
        if row["target_type"] == "座位":
            seat = conn.execute("SELECT room_id FROM seats WHERE id=?", (row["target_id"],)).fetchone()
            if seat is None or int(seat["room_id"]) not in allowed_rooms:
                continue
            target_label = conn.execute(
                "SELECT code FROM seats WHERE id=?", (row["target_id"],)
            ).fetchone()["code"]
        else:
            if int(row["target_id"]) not in allowed_rooms:
                continue
            target_label = conn.execute(
                "SELECT name FROM rooms WHERE id=?", (row["target_id"],)
            ).fetchone()["name"]
        output.append(
            {
                **dict(row),
                "target_label": target_label,
                "user_name_masked": mask_name(row["user_name"]),
                "student_no_masked": mask_student_no(row["student_no"]),
            }
        )
    return output


def _complaint_row(conn: sqlite3.Connection, complaint_id: int) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT c.*, u.name AS complainant_name, u.student_no AS complainant_no,
               cu.name AS complained_name, cu.student_no AS complained_no,
               cu.contact AS complained_contact
          FROM complaints c
          JOIN users u ON u.id=c.complainant_id
          LEFT JOIN users cu ON cu.id=c.complained_user_id
         WHERE c.id=?
        """,
        (complaint_id,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "COMPLAINT_NOT_FOUND", "投诉单不存在")
    return row


def _complaint_dict(row: sqlite3.Row, viewer: sqlite3.Row) -> dict:
    complained = None
    if row["complained_user_id"] is not None:
        complained = {
            "name_masked": mask_name(row["complained_name"]),
            "student_no_masked": mask_student_no(row["complained_no"]),
            "contact_masked": mask_contact(row["complained_contact"]),
        }
    return {
        "id": row["id"],
        "complaint_no": row["complaint_no"],
        "object_type": row["object_type"],
        "object_ref": row["object_ref"],
        "room_id": row["room_id"] if "room_id" in row.keys() else None,
        "complaint_type": row["complaint_type"],
        "content": row["content"],
        "evidence_attachment": row["evidence_attachment"],
        "status": row["status"],
        "complainant_name_masked": mask_name(row["complainant_name"]),
        "complainant_no_masked": mask_student_no(row["complainant_no"]),
        "complained_user": complained,
        "feedback": row["feedback"],
        "accepted_at": row["accepted_at"],
        "feedback_at": row["feedback_at"],
        "closed_at": row["closed_at"],
        "close_reason": row["close_reason"],
        "review_used": bool(row["review_used"]),
        "can_review": (
            int(viewer["id"]) == int(row["complainant_id"])
            and row["status"] == "已回复"
            and not bool(row["review_used"])
        ),
        "created_at": row["created_at"],
    }



def _resolve_complaint_room(conn: sqlite3.Connection, object_ref: str | None) -> int | None:
    """尽量把投诉对象描述解析到自习室，用于管理员授权范围过滤。"""
    if not object_ref:
        return None
    seat = conn.execute(
        "SELECT room_id FROM seats WHERE code=?", (object_ref,)
    ).fetchone()
    if seat is not None:
        return int(seat["room_id"])
    room = conn.execute(
        "SELECT id FROM rooms WHERE name=? OR code=?", (object_ref, object_ref)
    ).fetchone()
    return int(room["id"]) if room is not None else None


def require_complaint_access(
    conn: sqlite3.Connection, admin: sqlite3.Row, complaint: sqlite3.Row
) -> None:
    """管理员只能处理其授权自习室的投诉；系统管理员不受限。"""
    if admin["role"] == "sysadmin":
        return
    room_id = complaint["room_id"] if "room_id" in complaint.keys() else None
    if room_id is None:
        # 无法解析到具体自习室的投诉不做房间级过滤，保持历史行为。
        return
    require_room_access(conn, admin, int(room_id))


def create_complaint(user: sqlite3.Row, data: dict) -> dict:
    """学生实名提交投诉（AC-09-01、AC-09-02、BR-15；被投诉人脱敏）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    object_type = _required_text(data, "object_type")
    if object_type not in ("座位或自习室", "其他用户", "管理员"):
        raise ApiError(400, "INVALID_OBJECT_TYPE", "投诉对象类型不合法")
    complaint_type = _required_text(data, "complaint_type")
    content = _required_text(data, "content")
    object_ref = str(data.get("object_ref") or "").strip() or None
    evidence = str(data.get("evidence_attachment") or "").strip() or None
    complained_user_id = None
    room_id = _resolve_complaint_room(conn, object_ref)
    with db.immediate_transaction(conn):
        if object_type == "其他用户":
            student_no = _required_text(data, "complained_student_no")
            target = conn.execute(
                "SELECT id FROM users WHERE student_no=? AND role='student'", (student_no,)
            ).fetchone()
            if target is None:
                raise ApiError(404, "COMPLAINED_USER_NOT_FOUND", "被投诉学生不存在")
            complained_user_id = int(target["id"])
        complaint_no = "C" + now_s.replace("-", "").replace(":", "").replace(" ", "")[:14] + "-" + uuid.uuid4().hex[:5].upper()
        cursor = conn.execute(
            """
            INSERT INTO complaints
                (complaint_no, complainant_id, object_type, object_ref, room_id,
                 complained_user_id, complaint_type, content, evidence_attachment,
                 status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '待受理', ?)
            """,
            (
                complaint_no,
                user["id"],
                object_type,
                object_ref,
                room_id,
                complained_user_id,
                complaint_type,
                content,
                evidence,
                now_s,
            ),
        )
        complaint_id = int(cursor.lastrowid)
        for admin in conn.execute("SELECT id FROM users WHERE role='admin'").fetchall():
            notify_user(
                conn,
                admin["id"],
                "投诉受理",
                "新投诉待受理",
                f"投诉单 {complaint_no} 已提交，请及时受理（{complaint_type}）。",
                now_s,
            )
        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="提交投诉",
            target_type="投诉单",
            target_id=complaint_no,
            before=None,
            after={
                "object_type": object_type,
                "complaint_type": complaint_type,
                "status": "待受理",
            },
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        row = _complaint_row(conn, complaint_id)
        return _complaint_dict(row, user)


def get_complaint_for_viewer(viewer: sqlite3.Row, complaint_id: int) -> dict:
    conn = db.get_db()
    row = _complaint_row(conn, complaint_id)
    if viewer["role"] == "student" and int(row["complainant_id"]) != int(viewer["id"]):
        raise ApiError(403, "FORBIDDEN", "越权：只能查看本人投诉（NFR-07）")
    if viewer["role"] == "admin":
        require_complaint_access(conn, viewer, row)
    return _complaint_dict(row, viewer)


def list_complaints_for_student(user_id: int) -> list[dict]:
    conn = db.get_db()
    rows = conn.execute(
        "SELECT id FROM complaints WHERE complainant_id=? ORDER BY created_at DESC, id DESC",
        (user_id,),
    ).fetchall()
    viewer = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return [_complaint_dict(_complaint_row(conn, row["id"]), viewer) for row in rows]


def list_complaints_for_admin(admin: sqlite3.Row) -> list[dict]:
    conn = db.get_db()
    if admin["role"] == "sysadmin":
        rows = conn.execute(
            """
            SELECT id FROM complaints
             ORDER BY CASE status WHEN '待受理' THEN 0 WHEN '处理中' THEN 1 ELSE 2 END,
                      created_at DESC
            """
        ).fetchall()
    else:
        room_ids = admin_room_ids(conn, int(admin["id"]))
        if not room_ids:
            return []
        placeholders = ",".join("?" for _ in room_ids)
        rows = conn.execute(
            f"""
            SELECT id FROM complaints
             WHERE (room_id IS NULL OR room_id IN ({placeholders}))
             ORDER BY CASE status WHEN '待受理' THEN 0 WHEN '处理中' THEN 1 ELSE 2 END,
                      created_at DESC
            """,
            room_ids,
        ).fetchall()
    return [_complaint_dict(_complaint_row(conn, row["id"]), admin) for row in rows]


def accept_complaint(admin: sqlite3.Row, complaint_id: int) -> dict:
    """管理员受理投诉：待受理→处理中（AC-09-03、ST-24）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    with db.immediate_transaction(conn):
        row = _complaint_row(conn, complaint_id)
        require_complaint_access(conn, admin, row)
        if row["status"] != "待受理":
            raise ApiError(409, "INVALID_COMPLAINT_STATUS", f"投诉单当前状态为「{row['status']}」")
        conn.execute(
            """
            UPDATE complaints SET status='处理中', handler_id=?, accepted_at=?
             WHERE id=?
            """,
            (admin["id"], now_s, complaint_id),
        )
        notify_user(
            conn,
            row["complainant_id"],
            "投诉进度",
            "投诉已受理",
            f"投诉单 {row['complaint_no']} 已被受理，处理人：{admin['name']}。",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="受理投诉",
            target_type="投诉单",
            target_id=row["complaint_no"],
            before={"status": row["status"]},
            after={"status": "处理中", "handler_id": admin["id"]},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return _complaint_dict(_complaint_row(conn, complaint_id), admin)


def feedback_complaint(admin: sqlite3.Row, complaint_id: int, data: dict) -> dict:
    """管理员提交投诉反馈：处理中→已回复，并通知投诉人（AC-09-03）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    feedback = _required_text(data, "feedback")
    with db.immediate_transaction(conn):
        row = _complaint_row(conn, complaint_id)
        require_complaint_access(conn, admin, row)
        if row["status"] != "处理中":
            raise ApiError(409, "INVALID_COMPLAINT_STATUS", f"投诉单当前状态为「{row['status']}」")
        conn.execute(
            """
            UPDATE complaints SET status='已回复', feedback=?, feedback_at=?
             WHERE id=?
            """,
            (feedback, now_s, complaint_id),
        )
        notify_user(
            conn,
            row["complainant_id"],
            "投诉进度",
            "投诉反馈已提交",
            f"投诉单 {row['complaint_no']} 已有反馈：{feedback}",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="投诉反馈",
            target_type="投诉单",
            target_id=row["complaint_no"],
            before={"status": row["status"], "feedback": row["feedback"]},
            after={"status": "已回复", "feedback": feedback},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return _complaint_dict(_complaint_row(conn, complaint_id), admin)



def reject_complaint(admin: sqlite3.Row, complaint_id: int, data: dict) -> dict:
    """管理员判定投诉不成立/重复：待受理→已关闭（ST-25、BR-22）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    reason = _required_text(data, "reason")
    with db.immediate_transaction(conn):
        row = _complaint_row(conn, complaint_id)
        require_complaint_access(conn, admin, row)
        if row["status"] != "待受理":
            raise ApiError(409, "INVALID_COMPLAINT_STATUS", f"投诉单当前状态为「{row['status']}」")
        conn.execute(
            """
            UPDATE complaints
               SET status='已关闭', handler_id=?, closed_at=?, close_reason=?
             WHERE id=?
            """,
            (admin["id"], now_s, reason, complaint_id),
        )
        notify_user(
            conn,
            row["complainant_id"],
            "投诉进度",
            "投诉已关闭",
            f"投诉单 {row['complaint_no']} 经核实不成立或重复，已关闭。原因：{reason}",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=admin["id"],
            actor_name=admin["name"],
            actor_role=role_label(admin["role"]),
            action="投诉驳回",
            target_type="投诉单",
            target_id=row["complaint_no"],
            before={"status": row["status"]},
            after={"status": "已关闭", "close_reason": reason},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return _complaint_dict(_complaint_row(conn, complaint_id), admin)


def confirm_complaint(user: sqlite3.Row, complaint_id: int) -> dict:
    """投诉人确认反馈：已回复→已关闭（ST-27）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    with db.immediate_transaction(conn):
        row = _complaint_row(conn, complaint_id)
        if int(row["complainant_id"]) != int(user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能确认本人的投诉（NFR-07）")
        if row["status"] != "已回复":
            raise ApiError(409, "INVALID_COMPLAINT_STATUS", f"投诉单当前状态为「{row['status']}」")
        conn.execute(
            """
            UPDATE complaints
               SET status='已关闭', closed_at=?, close_reason='投诉人确认反馈'
             WHERE id=?
            """,
            (now_s, complaint_id),
        )
        for admin in conn.execute("SELECT id FROM users WHERE role='admin'").fetchall():
            notify_user(
                conn,
                admin["id"],
                "投诉进度",
                "投诉已确认关闭",
                f"投诉单 {row['complaint_no']} 已由投诉人确认反馈并关闭。",
                now_s,
            )
        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="投诉确认关闭",
            target_type="投诉单",
            target_id=row["complaint_no"],
            before={"status": row["status"]},
            after={"status": "已关闭", "close_reason": "投诉人确认反馈"},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return _complaint_dict(_complaint_row(conn, complaint_id), user)


def request_complaint_review(user: sqlite3.Row, complaint_id: int) -> dict:
    """投诉人申请复核一次：已回复→处理中（AC-09-04、BR-17、ST-29）。"""
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    with db.immediate_transaction(conn):
        row = _complaint_row(conn, complaint_id)
        if int(row["complainant_id"]) != int(user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能复核本人的投诉（NFR-07）")
        if row["status"] != "已回复":
            raise ApiError(409, "INVALID_COMPLAINT_STATUS", f"投诉单当前状态为「{row['status']}」")
        if row["review_used"]:
            raise ApiError(409, "REVIEW_ALREADY_USED", "该投诉已申请过复核，仅允许一次（BR-17）")
        conn.execute(
            """
            UPDATE complaints
               SET status='处理中', review_used=1, review_requested_at=?
             WHERE id=?
            """,
            (now_s, complaint_id),
        )
        for admin in conn.execute("SELECT id FROM users WHERE role='admin'").fetchall():
            notify_user(
                conn,
                admin["id"],
                "投诉进度",
                "投诉复核申请",
                f"投诉单 {row['complaint_no']} 的投诉人申请复核，请重新处理。",
                now_s,
            )
        db.write_audit(
            conn,
            actor_user_id=user["id"],
            actor_name=user["name"],
            actor_role=role_label(user["role"]),
            action="投诉复核申请",
            target_type="投诉单",
            target_id=row["complaint_no"],
            before={"status": row["status"], "review_used": False},
            after={"status": "处理中", "review_used": True},
            result="成功",
            created_at=now_s,
            ip_address=request.remote_addr,
        )
        return _complaint_dict(_complaint_row(conn, complaint_id), user)


def auto_close_complaints(conn: sqlite3.Connection, now_s: str) -> int:
    """超过反馈确认时限且未复核的投诉自动关闭（AC-09-05、ST-28、P-13）。"""
    now = parse_dt(now_s)
    days = db.get_rule_int(conn, "complaint_auto_close_days")
    rows = conn.execute(
        "SELECT * FROM complaints WHERE status='已回复' AND feedback_at IS NOT NULL"
    ).fetchall()
    count = 0
    for row in rows:
        due = parse_dt(row["feedback_at"]) + timedelta(days=days)
        if now < due:
            continue
        conn.execute(
            """
            UPDATE complaints
               SET status='已关闭', closed_at=?, close_reason='反馈后超时未确认，系统自动关闭'
             WHERE id=?
            """,
            (now_s, row["id"]),
        )
        notify_user(
            conn,
            row["complainant_id"],
            "投诉进度",
            "投诉已自动关闭",
            f"投诉单 {row['complaint_no']} 超过确认时限，已由系统自动关闭。",
            now_s,
        )
        db.write_audit(
            conn,
            actor_user_id=None,
            actor_name=SYSTEM_ACTOR_NAME,
            actor_role=SYSTEM_ACTOR_ROLE,
            action="投诉自动关闭",
            target_type="投诉单",
            target_id=row["complaint_no"],
            before={"status": row["status"], "feedback_at": row["feedback_at"]},
            after={"status": "已关闭", "close_reason": "反馈后超时未确认，系统自动关闭"},
            result="成功",
            created_at=now_s,
        )
        count += 1
    return count


# ---------------------------------------------------------------------------
# Sprint 6：数据分析与通知中心
# FR-11、FR-12；AC-11-01—06、AC-12-01—03
# ---------------------------------------------------------------------------


def analytics_query_args() -> dict:
    now_date = get_now().date()
    date_from = request.args.get("date_from", "").strip() or (now_date - timedelta(days=6)).isoformat()
    date_to = request.args.get("date_to", "").strip() or now_date.isoformat()
    try:
        start = parse_date(date_from)
        end = parse_date(date_to)
    except ValueError:
        raise ApiError(400, "INVALID_DATE", "date_from/date_to 格式应为 YYYY-MM-DD")
    if start > end:
        raise ApiError(400, "INVALID_DATE_RANGE", "date_from 不能晚于 date_to")
    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "room_id": _optional_int_arg("room_id"),
    }


def analytics_data(user: sqlite3.Row, filters: dict) -> dict:
    """统计图表与统计数值（AC-11-01—06、FR-11）。"""
    conn = db.get_db()
    now = get_now()
    if user["role"] == "admin":
        allowed_room_ids = admin_room_ids(conn, int(user["id"]))
        if filters.get("room_id") is not None and filters["room_id"] not in allowed_room_ids:
            raise ApiError(403, "ROOM_FORBIDDEN", "越权：只能查看被授权自习室的统计（AC-11-05）")
    else:
        allowed_room_ids = [
            int(row["id"]) for row in conn.execute("SELECT id FROM rooms ORDER BY id").fetchall()
        ]
    selected_room_id = filters.get("room_id")
    room_ids = [selected_room_id] if selected_room_id is not None else allowed_room_ids
    rooms = []
    if room_ids:
        room_rows = conn.execute(
            f"SELECT id, name FROM rooms WHERE id IN ({','.join('?' for _ in room_ids)}) ORDER BY id",
            room_ids,
        ).fetchall()
        if selected_room_id is not None and not room_rows:
            raise ApiError(404, "ROOM_NOT_FOUND", "自习室不存在")
        rooms = [dict(row) for row in room_rows]
        room_ids = [item["id"] for item in rooms]
    room_placeholders = ",".join("?" for _ in room_ids)
    date_from = filters["date_from"]
    date_to = filters["date_to"]

    reservation_by_room = {room_id: 0 for room_id in room_ids}
    violation_by_room = {room_id: 0 for room_id in room_ids}
    line_reservations = {}
    line_violations = {}
    if room_ids:
        for row in conn.execute(
            f"""
            SELECT room_id, COUNT(*) AS n FROM reservations
             WHERE reservation_date BETWEEN ? AND ?
               AND room_id IN ({room_placeholders})
             GROUP BY room_id
            """,
            [date_from, date_to, *room_ids],
        ).fetchall():
            reservation_by_room[int(row["room_id"])] = int(row["n"])
        for row in conn.execute(
            f"""
            SELECT s.room_id, COUNT(*) AS n
              FROM violations v JOIN seats s ON s.id=v.seat_id
             WHERE substr(v.occurred_at, 1, 10) BETWEEN ? AND ?
               AND s.room_id IN ({room_placeholders})
             GROUP BY s.room_id
            """,
            [date_from, date_to, *room_ids],
        ).fetchall():
            violation_by_room[int(row["room_id"])] = int(row["n"])
        for row in conn.execute(
            f"""
            SELECT reservation_date AS d, COUNT(*) AS n FROM reservations
             WHERE reservation_date BETWEEN ? AND ?
               AND room_id IN ({room_placeholders})
             GROUP BY reservation_date
            """,
            [date_from, date_to, *room_ids],
        ).fetchall():
            line_reservations[row["d"]] = int(row["n"])
        for row in conn.execute(
            f"""
            SELECT substr(v.occurred_at, 1, 10) AS d, COUNT(*) AS n
              FROM violations v JOIN seats s ON s.id=v.seat_id
             WHERE substr(v.occurred_at, 1, 10) BETWEEN ? AND ?
               AND s.room_id IN ({room_placeholders})
             GROUP BY substr(v.occurred_at, 1, 10)
            """,
            [date_from, date_to, *room_ids],
        ).fetchall():
            line_violations[row["d"]] = int(row["n"])

    start = parse_date(date_from)
    end = parse_date(date_to)
    day_labels = []
    cursor = start
    while cursor <= end:
        day_labels.append(cursor.isoformat())
        cursor += timedelta(days=1)

    if room_ids:
        free_seats = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM seats
             WHERE room_id IN ({room_placeholders}) AND status='空闲' AND is_bookable=1
            """,
            room_ids,
        ).fetchone()["n"]
        occupied_seats = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM seats
             WHERE room_id IN ({room_placeholders}) AND status='使用中'
            """,
            room_ids,
        ).fetchone()["n"]
        today_reservations = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM reservations
             WHERE reservation_date=? AND room_id IN ({room_placeholders})
            """,
            [now.date().isoformat(), *room_ids],
        ).fetchone()["n"]
        today_violations = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM violations v
              JOIN seats s ON s.id=v.seat_id
             WHERE substr(v.occurred_at, 1, 10)=? AND s.room_id IN ({room_placeholders})
            """,
            [now.date().isoformat(), *room_ids],
        ).fetchone()["n"]
    else:
        free_seats = 0
        occupied_seats = 0
        today_reservations = 0
        today_violations = 0

    pending_complaints = conn.execute(
        "SELECT COUNT(*) AS n FROM complaints WHERE status='待受理'"
    ).fetchone()["n"]
    active_blacklists = conn.execute(
        "SELECT COUNT(*) AS n FROM blacklists WHERE status='生效中' AND expires_at > ?",
        (fmt_dt(now),),
    ).fetchone()["n"]

    return {
        "filters": {
            "date_from": date_from,
            "date_to": date_to,
            "room_id": selected_room_id,
        },
        "rooms": rooms,
        "charts": {
            "bar_reservations_by_room": {
                "labels": [room["name"] for room in rooms],
                "values": [reservation_by_room[room["id"]] for room in rooms],
            },
            "bar_violations_by_room": {
                "labels": [room["name"] for room in rooms],
                "values": [violation_by_room[room["id"]] for room in rooms],
            },
            "line_daily": {
                "labels": day_labels,
                "reservations": [line_reservations.get(day, 0) for day in day_labels],
                "violations": [line_violations.get(day, 0) for day in day_labels],
            },
            "refresh_seconds": db.get_rule_int(conn, "data_refresh_seconds"),
        },
        "stats": {
            "current_free_seats": int(free_seats),
            "current_occupied_seats": int(occupied_seats),
            "today_reservations": int(today_reservations),
            "today_violations": int(today_violations),
            "pending_complaints": int(pending_complaints),
            "active_blacklists": int(active_blacklists),
        },
        "refreshed_at": fmt_dt(now),
    }



def analytics_export_csv(user: sqlite3.Row, filters: dict) -> str:
    """按日期/自习室筛选生成 CSV，仅统计值，不含个人信息（FR-11、V1.6）。"""
    data = analytics_data(user, filters)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["日期范围", data["filters"]["date_from"], data["filters"]["date_to"]]
    )
    writer.writerow(["自习室", "预约量", "违约量"])
    labels = data["charts"]["bar_reservations_by_room"]["labels"]
    reservations = data["charts"]["bar_reservations_by_room"]["values"]
    violations = data["charts"]["bar_violations_by_room"]["values"]
    for label, reservation_count, violation_count in zip(labels, reservations, violations):
        writer.writerow([label, reservation_count, violation_count])
    writer.writerow([])
    writer.writerow(["统计指标", "数值"])
    stats = data["stats"]
    for label, key in (
        ("当前空闲座位", "current_free_seats"),
        ("当前使用中座位", "current_occupied_seats"),
        ("今日预约数", "today_reservations"),
        ("今日违约数", "today_violations"),
        ("待受理投诉", "pending_complaints"),
        ("生效中黑名单", "active_blacklists"),
    ):
        writer.writerow([label, stats[key]])
    writer.writerow(["导出时间", data["refreshed_at"]])
    return out.getvalue()


def notifications_query_args() -> dict:
    category = request.args.get("category", "").strip() or None
    read_status = request.args.get("read_status", "").strip() or None
    if read_status not in (None, "", "read", "unread"):
        raise ApiError(400, "INVALID_READ_STATUS", "read_status 只能为 read 或 unread")
    return {
        "category": category,
        "read_status": read_status or None,
        "page": _positive_int_arg("page", 1, 100000),
        "page_size": _positive_int_arg("page_size", 20),
    }


def query_notifications(user: sqlite3.Row, filters: dict) -> dict:
    """本人通知列表与送达记录（AC-12-01—03）。"""
    conn = db.get_db()
    clauses = ["user_id=?"]
    params: list[object] = [user["id"]]
    if filters.get("category"):
        clauses.append("notification_type=?")
        params.append(filters["category"])
    if filters.get("read_status") == "read":
        clauses.append("read_at IS NOT NULL")
    elif filters.get("read_status") == "unread":
        clauses.append("read_at IS NULL")
    where = " AND ".join(clauses)
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM notifications WHERE {where}", params
    ).fetchone()["n"]
    page = int(filters["page"])
    page_size = int(filters["page_size"])
    rows = conn.execute(
        f"""
        SELECT * FROM notifications WHERE {where}
         ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    categories = [
        row["notification_type"]
        for row in conn.execute(
            "SELECT DISTINCT notification_type FROM notifications WHERE user_id=? ORDER BY notification_type",
            (user["id"],),
        ).fetchall()
    ]
    items = [
        {
            "id": row["id"],
            "notification_type": row["notification_type"],
            "title": row["title"],
            "content": row["content"],
            "created_at": row["created_at"],
            "read_at": row["read_at"],
            "is_read": row["read_at"] is not None,
            "delivery_result": row["delivery_result"],
            "event_key": row["event_key"],
        }
        for row in rows
    ]
    total_pages = math.ceil(total / page_size) if total else 0
    return {
        "notifications": items,
        "categories": categories,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        },
    }


def mark_notification_read(user: sqlite3.Row, notification_id: int) -> dict:
    conn = db.get_db()
    now_s = fmt_dt(get_now())
    with db.immediate_transaction(conn):
        row = conn.execute(
            "SELECT * FROM notifications WHERE id=?", (notification_id,)
        ).fetchone()
        if row is None:
            raise ApiError(404, "NOTIFICATION_NOT_FOUND", "通知不存在")
        if int(row["user_id"]) != int(user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能标记本人通知")
        if row["read_at"] is None:
            conn.execute(
                "UPDATE notifications SET read_at=? WHERE id=?", (now_s, notification_id)
            )
            read_at = now_s
        else:
            read_at = row["read_at"]
        return {
            "id": notification_id,
            "is_read": True,
            "read_at": read_at,
            "delivery_result": row["delivery_result"],
        }


# ---------------------------------------------------------------------------
# 页面与 API 路由
# ---------------------------------------------------------------------------


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config.get("NOW_PROVIDER") is None:
        app.config["NOW_PROVIDER"] = lambda: datetime.now()
    app.json.ensure_ascii = False
    db.init_app(app)

    with app.app_context():
        db.init_db()
        seed_database(now=app.config["NOW_PROVIDER"]())

    @app.before_request
    def load_current_user():
        g.user = None
        if request.endpoint == "static":
            return
        user_id = session.get("user_id")
        if user_id is None:
            return
        row = db.get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            session.clear()
        else:
            g.user = row

    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "role_labels": ROLE_LABELS,
        }

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        if wants_json():
            return (
                jsonify({"error": {"code": error.code, "message": error.message}}),
                error.status,
            )
        return (
            render_template(
                "error.html",
                status_code=error.status,
                title="请求未完成",
                message=error.message,
            ),
            error.status,
        )

    @app.errorhandler(404)
    def not_found(_error):
        if wants_json():
            return jsonify({"error": {"code": "NOT_FOUND", "message": "资源不存在"}}), 404
        return render_template("error.html", status_code=404, title="页面不存在", message="请求的页面不存在"), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        if wants_json():
            return jsonify({"error": {"code": "METHOD_NOT_ALLOWED", "message": "请求方法不允许"}}), 405
        return render_template("error.html", status_code=405, title="方法不允许", message="请求方法不允许"), 405

    @app.errorhandler(500)
    def internal_error(_error):
        if wants_json():
            return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "服务器处理失败，请稍后重试"}}), 500
        return render_template("error.html", status_code=500, title="服务器错误", message="服务器处理失败，请稍后重试"), 500

    @app.get("/")
    def index():
        """登录后按角色进入工作台（FR-01、AC-01-01、AC-01-02）。"""
        if g.user is None:
            return redirect(url_for("login"))
        return redirect(home_for_role(g.user["role"]))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """模拟 SSO 登录；会话与锁定判定（AC-01-01、AC-01-02、AC-01-04）。"""
        if request.method == "GET":
            if g.user is not None:
                return redirect(home_for_role(g.user["role"]))
            return render_template("login.html")

        data = request.get_json(silent=True) if request.is_json else request.form
        data = data or {}
        student_no = str(data.get("student_no") or data.get("username") or "").strip()
        password = str(data.get("password") or "")
        if not student_no or not password:
            message = "学号与密码均为必填项"
            if request.is_json:
                return jsonify({"error": {"code": "MISSING_FIELD", "message": message}}), 400
            flash(message, "error")
            return render_template("login.html"), 400

        result = authenticate_user(student_no, password, request.remote_addr)
        if not result["ok"]:
            if request.is_json:
                payload = {
                    "error": {"code": result["code"], "message": result["message"]},
                }
                if "remaining_minutes" in result:
                    payload["remaining_minutes"] = result["remaining_minutes"]
                if "locked_until" in result:
                    payload["locked_until"] = result["locked_until"]
                return jsonify(payload), result["status"]
            flash(result["message"], "error")
            return render_template("login.html"), result["status"]

        session.clear()
        session.permanent = True
        session["user_id"] = result["user"]["id"]
        session["role"] = result["user"]["role"]
        session["last_active_at"] = fmt_dt(get_now())
        if request.is_json:
            return jsonify(
                {
                    "message": "登录成功",
                    "user": result["user"],
                    "redirect": home_for_role(result["user"]["role"]),
                }
            )
        return redirect(home_for_role(result["user"]["role"]))

    @app.post("/logout")
    def logout():
        session.clear()
        if wants_json():
            return jsonify({"message": "已退出登录"})
        flash("已退出登录", "info")
        return redirect(url_for("login"))

    @app.get("/student")
    @role_required("student")
    def student_home():
        """学生工作台；只呈现学生入口（AC-01-01）。"""
        conn = db.get_db()
        active_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM reservations
             WHERE user_id = ? AND status IN ('待生效', '待签到', '使用中')
            """,
            (g.user["id"],),
        ).fetchone()["n"]
        notifications = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (g.user["id"],),
        ).fetchall()
        return render_template(
            "student_home.html",
            active_count=active_count,
            notifications=notifications,
        )

    @app.get("/seats")
    @login_required
    def seats_page():
        """座位查询页；所有已登录角色可读（权限矩阵第 3 行）。"""
        conn = db.get_db()
        rooms = conn.execute("SELECT * FROM rooms WHERE status = '开放' ORDER BY id").fetchall()
        zones = conn.execute(
            """
            SELECT z.*, r.name AS room_name FROM zones z
              JOIN rooms r ON r.id = z.room_id ORDER BY r.id, z.sort_order
            """
        ).fetchall()
        default_date = (get_now().date() + timedelta(days=1)).isoformat()
        return render_template(
            "seats.html",
            rooms=rooms,
            zones=zones,
            default_date=default_date,
            can_book=g.user["role"] == "student",
        )


    @app.get("/reservations/<int:reservation_id>/modify")
    @role_required("student")
    def reservation_modify_page(reservation_id: int):
        """学生修改待生效预约页面（FR-04、AC-04-07/08）。"""
        conn = db.get_db()
        row = conn.execute(
            """
            SELECT r.*, s.code AS seat_code, ro.name AS room_name,
                   z.name AS zone_name
              FROM reservations r JOIN seats s ON s.id=r.seat_id
              JOIN rooms ro ON ro.id=r.room_id
              JOIN zones z ON z.id=r.zone_id
             WHERE r.id=?
            """,
            (reservation_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "RESERVATION_NOT_FOUND", "预约单不存在")
        if int(row["user_id"]) != int(g.user["id"]):
            raise ApiError(403, "FORBIDDEN", "越权：只能修改本人的预约")
        rooms = conn.execute(
            "SELECT id, code, name FROM rooms WHERE status='开放' ORDER BY code"
        ).fetchall()
        zones = conn.execute(
            "SELECT id, room_id, code, name FROM zones ORDER BY room_id, sort_order, id"
        ).fetchall()
        seats = conn.execute(
            """
            SELECT id, room_id, zone_id, code, seat_type, status, is_bookable
              FROM seats ORDER BY room_id, zone_id, code
            """
        ).fetchall()
        return render_template(
            "reservation_modify.html",
            reservation=row,
            rooms=[dict(item) for item in rooms],
            zones=[dict(item) for item in zones],
            seats=[dict(item) for item in seats],
        )

    @app.get("/reservations")
    @role_required("student")
    def reservations_page():
        """学生本人预约列表与取消入口（FR-06、FR-04）。"""
        return render_template(
            "reservations.html",
            reservations=list_my_reservations(g.user["id"]),
        )

    @app.get("/usage")
    @role_required("student")
    def usage_page():
        """学生签到/签退页（FR-04、AC-04-03—06）。"""
        conn = db.get_db()
        now = get_now()
        early = db.get_rule_int(conn, "checkin_early_minutes")
        late = db.get_rule_int(conn, "checkin_late_minutes")
        rows = conn.execute(
            """
            SELECT r.*, s.code AS seat_code, ro.name AS room_name,
                   c.checkin_at, c.method AS checkin_method, c.checkout_at
              FROM reservations r
              JOIN seats s ON s.id = r.seat_id
              JOIN rooms ro ON ro.id = r.room_id
              LEFT JOIN checkins c ON c.reservation_id = r.id
             WHERE r.user_id = ? AND r.status IN ('待签到', '使用中')
             ORDER BY r.reservation_date, r.start_time
            """,
            (g.user["id"],),
        ).fetchall()
        items = []
        for row in rows:
            start_dt = datetime.combine(
                parse_date(row["reservation_date"]), parse_hm(row["start_time"])
            )
            item = dict(row)
            item["window_start"] = (start_dt - timedelta(minutes=early)).strftime("%H:%M")
            item["window_end"] = (start_dt + timedelta(minutes=late)).strftime("%H:%M")
            item["checkin_enabled"] = (
                row["status"] == "待签到"
                and start_dt - timedelta(minutes=early) <= now <= start_dt + timedelta(minutes=late)
            )
            items.append(item)
        return render_template("usage.html", items=items, now_text=fmt_dt(now))

    @app.get("/violations")
    @role_required("student")
    def violations_page():
        """学生违约记录与申诉入口（FR-05、AC-05-03、AC-05-04）。"""
        conn = db.get_db()
        rows = conn.execute(
            """
            SELECT v.*, s.code AS seat_code
              FROM violations v
              JOIN seats s ON s.id = v.seat_id
             WHERE v.user_id = ?
             ORDER BY v.created_at DESC, v.id DESC
            """,
            (g.user["id"],),
        ).fetchall()
        return render_template(
            "violations.html",
            violations=rows,
            appeal_days=db.get_rule_int(conn, "appeal_days"),
        )

    @app.get("/credit")
    @role_required("student")
    def credit_page():
        """学生本人信用状态页（AC-10-05、FR-10）。"""
        return render_template(
            "credit.html", credit=credit_summary(db.get_db(), g.user["id"])
        )

    @app.get("/admin")
    @role_required("admin")
    def admin_home():
        """管理员工作台；呈现管理入口（AC-01-02）及 Sprint 2 已开放能力。"""
        conn = db.get_db()
        seat_count = conn.execute("SELECT COUNT(*) AS n FROM seats").fetchone()["n"]
        pending_appeals = conn.execute(
            "SELECT COUNT(*) AS n FROM violations WHERE status='申诉中'"
        ).fetchone()["n"]
        active_blacklists = conn.execute(
            """
            SELECT COUNT(*) AS n FROM blacklists
             WHERE status='生效中' AND expires_at > ?
            """,
            (fmt_dt(get_now()),),
        ).fetchone()["n"]
        return render_template(
            "admin_home.html",
            seat_count=seat_count,
            pending_appeals=pending_appeals,
            active_blacklists=active_blacklists,
        )

    @app.get("/admin/appeals")
    @role_required("admin", "sysadmin")
    def admin_appeals_page():
        """管理员申诉复核页（AC-05-03、AC-05-07）。"""
        conn = db.get_db()
        rows = conn.execute(
            """
            SELECT v.*, u.student_no, u.name AS user_name, s.code AS seat_code
              FROM violations v
              JOIN users u ON u.id=v.user_id
              JOIN seats s ON s.id=v.seat_id
             WHERE v.status='申诉中'
             ORDER BY v.appeal_at, v.id
            """
        ).fetchall()
        return render_template("admin_appeals.html", appeals=rows)

    @app.get("/admin/blacklists")
    @role_required("admin", "sysadmin")
    def admin_blacklists_page():
        """管理员黑名单管理页（AC-10-04、FR-10）。"""
        conn = db.get_db()
        rows = conn.execute(
            """
            SELECT b.*, u.student_no, u.name AS user_name, u.account_status,
                   u.effective_violation_count
              FROM blacklists b
              JOIN users u ON u.id=b.user_id
             ORDER BY b.status='生效中' DESC, b.expires_at DESC, b.id DESC
            """
        ).fetchall()
        return render_template("admin_blacklists.html", blacklists=rows)

    @app.get("/admin/maintenance")
    @role_required("admin")
    def admin_maintenance_page():
        """管理员手动触发维护扫描；同一服务由后台定时线程周期性执行。"""
        conn = db.get_db()
        return render_template(
            "admin_maintenance.html",
            scan_seconds=db.get_rule_int(conn, "violation_scan_seconds"),
            now_text=fmt_dt(get_now()),
        )

    @app.get("/admin/resources")
    @role_required("admin", "sysadmin")
    def admin_resources_page():
        """管理员资源维护页（FR-02、AC-02-01—04）。"""
        return render_template(
            "admin_resources.html",
            resources=resources_snapshot(db.get_db(), g.user)["rooms"],
        )

    @app.get("/admin/proxy-reservation")
    @role_required("admin")
    def admin_proxy_reservation_page():
        """管理员代学生创建预约页面（FR-03、BR-22）。"""
        return render_template(
            "admin_proxy_reservation.html",
            default_date=(get_now().date() + timedelta(days=1)).isoformat(),
        )

    @app.get("/admin/realtime")
    @role_required("admin", "sysadmin")
    def admin_realtime_page():
        """实时座位视图页（FR-07、AC-07-01）。"""
        conn = db.get_db()
        rooms = get_admin_rooms(conn, int(g.user["id"]))
        room_id_raw = request.args.get("room_id")
        room_id = None
        if room_id_raw:
            try:
                room_id = int(room_id_raw)
            except ValueError:
                raise ApiError(400, "INVALID_FILTER", "room_id 必须为整数")
        if not rooms:
            raise ApiError(403, "ROOM_FORBIDDEN", "当前管理员没有任何被授权的自习室")
        if room_id is None:
            room_id = int(rooms[0]["id"])
        require_room_access(conn, g.user, room_id)
        return render_template(
            "admin_realtime.html",
            rooms=rooms,
            selected_room_id=room_id,
        )

    @app.get("/admin/seats/<int:seat_id>/history")
    @role_required("admin", "sysadmin")
    def admin_seat_history_page(seat_id: int):
        """座位历史记录页（AC-07-05）。"""
        return render_template(
            "seat_history.html",
            data=seat_history(db.get_db(), g.user, seat_id),
        )

    @app.get("/sysadmin")
    @role_required("sysadmin")
    def sysadmin_home():
        """系统管理员工作台（FR-14、AC-14-01—04）。"""
        conn = db.get_db()
        audit_count = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"]
        return render_template("sysadmin_home.html", audit_count=audit_count)

    @app.get("/sysadmin/audit")
    @role_required("sysadmin")
    def sysadmin_audit_page():
        """审计日志查询页，筛选与分页参数在翻页后保持（AC-14-01—04）。"""
        filters = audit_query_args()
        data = query_audit_logs(filters)
        page = data["pagination"]["page"]
        query_args = request.args.to_dict(flat=True)
        prev_url = None
        next_url = None
        if data["pagination"]["has_prev"]:
            args = {**query_args, "page": page - 1}
            prev_url = url_for("sysadmin_audit_page", **args)
        if data["pagination"]["has_next"]:
            args = {**query_args, "page": page + 1}
            next_url = url_for("sysadmin_audit_page", **args)
        return render_template(
            "audit_logs.html",
            data=data,
            filters=filters,
            prev_url=prev_url,
            next_url=next_url,
        )


    @app.get("/sysadmin/users")
    @role_required("sysadmin")
    def sysadmin_users_page():
        """系统管理员用户查询页（FR-08、V1.6）。"""
        return render_template("sysadmin_users.html")

    @app.get("/sysadmin/assignments")
    @role_required("sysadmin")
    def sysadmin_assignments_page():
        """管理员—自习室授权维护页（BR-21、V1.6）。"""
        conn = db.get_db()
        admins = conn.execute(
            "SELECT id, student_no, name FROM users WHERE role='admin' ORDER BY student_no"
        ).fetchall()
        rooms = conn.execute("SELECT id, code, name FROM rooms ORDER BY code").fetchall()
        return render_template(
            "sysadmin_assignments.html",
            admins=admins,
            rooms=rooms,
            assignments=admin_assignment_rows(conn),
        )

    @app.get("/sysadmin/params")
    @role_required("sysadmin")
    def sysadmin_params_page():
        """规则参数配置页；显示默认值、取值范围、来源与确认状态（AC-13-01—04）。"""
        return render_template(
            "parameter_config.html",
            params=list_rule_params(db.get_db()),
        )

    @app.get("/records")
    @login_required
    def records_page():
        """预约记录查询页；按角色数据范围与筛选分页（AC-06-02—04）。"""
        filters = record_query_args()
        data = query_reservations_scoped(g.user, filters)
        conn = db.get_db()
        if g.user["role"] == "admin":
            rooms = get_admin_rooms(conn, int(g.user["id"]))
        else:
            rooms = conn.execute("SELECT * FROM rooms ORDER BY id").fetchall()
        page = data["pagination"]["page"]
        query_args = request.args.to_dict(flat=True)
        prev_url = None
        next_url = None
        if data["pagination"]["has_prev"]:
            args = {**query_args, "page": page - 1}
            prev_url = url_for("records_page", **args)
        if data["pagination"]["has_next"]:
            args = {**query_args, "page": page + 1}
            next_url = url_for("records_page", **args)
        return render_template(
            "records.html",
            data=data,
            filters=filters,
            rooms=rooms,
            prev_url=prev_url,
            next_url=next_url,
        )

    @app.get("/evaluations")
    @role_required("student")
    def evaluations_page():
        """学生评价页：仅列出本人已完成预约可评价的对象（FR-08）。"""
        conn = db.get_db()
        rows = conn.execute(
            """
            SELECT r.id AS reservation_id, r.reservation_date, r.start_time, r.end_time,
                   s.id AS seat_id, s.code AS seat_code,
                   ro.id AS room_id, ro.name AS room_name,
                   EXISTS(SELECT 1 FROM evaluations e
                           WHERE e.user_id=? AND e.target_type='座位' AND e.target_id=s.id)
                       AS seat_evaluated,
                   EXISTS(SELECT 1 FROM evaluations e
                           WHERE e.user_id=? AND e.target_type='自习室' AND e.target_id=ro.id)
                       AS room_evaluated
              FROM reservations r
              JOIN seats s ON s.id=r.seat_id
              JOIN rooms ro ON ro.id=r.room_id
             WHERE r.user_id=? AND r.status='已完成'
             ORDER BY r.reservation_date DESC, r.start_time DESC
            """,
            (g.user["id"], g.user["id"], g.user["id"]),
        ).fetchall()
        return render_template("evaluations.html", completed=rows)

    @app.get("/admin/evaluations")
    @role_required("admin", "sysadmin")
    def admin_evaluations_page():
        """管理员评价管理页：查看授权对象评价并填写理由隐藏（AC-08-03）。"""
        return render_template(
            "admin_evaluations.html",
            evaluations=_evaluation_admin_rows(db.get_db(), g.user),
        )

    @app.get("/complaints")
    @role_required("student")
    def complaints_page():
        """学生投诉与反馈页（FR-09、AC-09-01—06）。"""
        return render_template(
            "complaints.html",
            complaints=list_complaints_for_student(g.user["id"]),
        )

    @app.get("/admin/complaints")
    @role_required("admin", "sysadmin")
    def admin_complaints_page():
        """管理员投诉处理页（FR-09、AC-09-03）。"""
        return render_template(
            "admin_complaints.html",
            complaints=list_complaints_for_admin(g.user),
        )

    @app.get("/analytics")
    @role_required("admin", "sysadmin", "logistics")
    def analytics_page():
        """数据分析页面；10 秒局部刷新且保留筛选（FR-11、AC-11-01—06）。"""
        conn = db.get_db()
        if g.user["role"] == "admin":
            rooms = get_admin_rooms(conn, int(g.user["id"]))
        else:
            rooms = conn.execute("SELECT * FROM rooms ORDER BY id").fetchall()
        today = get_now().date()
        return render_template(
            "analytics.html",
            rooms=rooms,
            default_date_from=(today - timedelta(days=6)).isoformat(),
            default_date_to=today.isoformat(),
        )

    @app.get("/notifications")
    @role_required("student", "admin")
    def notifications_page():
        """通知中心；分类筛选、标记已读、不可删除（FR-12、AC-12-01—03）。"""
        return render_template("notifications.html")

    @app.get("/api/me")
    @login_required
    def api_me():
        return jsonify({"user": public_user(g.user)})


    @app.put("/api/me/contact")
    @login_required
    def api_update_my_contact():
        """修改本人联系方式；学号/姓名不可改（FR-08、V1.6）。"""
        return jsonify({"message": "联系方式已更新", "user": update_my_contact(g.user, _payload_dict())})

    @app.get("/api/seats")
    @login_required
    def api_seats():
        """座位查询 API（FR-06、AC-06-01）。"""
        date_text = request.args.get("date", "").strip() or None
        start_text = request.args.get("start", "").strip() or None
        end_text = request.args.get("end", "").strip() or None
        if date_text:
            try:
                parse_date(date_text)
            except ValueError:
                raise ApiError(400, "INVALID_DATE", "date 格式应为 YYYY-MM-DD")
        if bool(start_text) != bool(end_text):
            raise ApiError(400, "INVALID_TIME_RANGE", "start 与 end 必须同时提供")
        if start_text and not date_text:
            raise ApiError(400, "MISSING_DATE", "按时段查询时必须同时提供 date")
        if start_text:
            try:
                start_time = parse_hm(start_text)
                end_time = parse_hm(end_text)
            except ValueError as exc:
                raise ApiError(400, "INVALID_TIME", str(exc))
            if end_time <= start_time:
                raise ApiError(400, "INVALID_TIME_RANGE", "end 必须晚于 start")

        filters = {
            "building": request.args.get("building", "").strip() or None,
            "room_id": _optional_int_arg("room_id"),
            "zone_id": _optional_int_arg("zone_id"),
            "zone_type": request.args.get("zone_type", "").strip() or None,
            "seat_type": request.args.get("seat_type", "").strip() or None,
            "date": date_text,
            "start_time": start_text,
            "end_time": end_text,
            "only_available": request.args.get("only_available", "").lower()
            in ("1", "true", "yes"),
        }
        seats = query_seats(filters)
        return jsonify(
            {
                "filters": filters,
                "count": len(seats),
                "seats": seats,
                "note": (
                    "current_status 是座位当前展示状态；available_for_slot 是所查日期/时段"
                    "是否可预约；available_slots 是所查日期内的连续空档。"
                ),
            }
        )

    @app.post("/api/reservations")
    @role_required("student")
    def api_create_reservation():
        """提交预约；仅学生角色可用（FR-03、AC-03-01—05）。"""
        data = _payload_dict()
        try:
            reservation = create_reservation(g.user, data)
        except ApiError as error:
            record_reservation_failure(g.user, data, error)
            raise
        return jsonify({"message": "预约成功", "reservation": reservation}), 201


    @app.post("/api/admin/reservations")
    @role_required("admin")
    def api_admin_create_reservation():
        """管理员代学生创建预约，复用学生预约校验（FR-03、BR-22）。"""
        data = _payload_dict()
        try:
            reservation = admin_create_reservation(g.user, data)
        except ApiError as error:
            record_reservation_failure(
                g.user, data, error, actor=g.user, action="管理员代创建预约"
            )
            raise
        return jsonify({"message": "代创建预约成功", "reservation": reservation}), 201

    @app.get("/api/reservations")
    @login_required
    def api_query_reservations():
        """分页查询预约记录，按角色隔离数据（AC-06-02—04）。"""
        filters = record_query_args()
        return jsonify(query_reservations_scoped(g.user, filters))

    @app.get("/api/reservations/my")
    @role_required("student")
    def api_my_reservations():
        """仅返回本人预约（FR-06、NFR-07）。"""
        return jsonify({"reservations": list_my_reservations(g.user["id"])})


    @app.put("/api/reservations/<int:reservation_id>")
    @role_required("student")
    def api_modify_reservation(reservation_id: int):
        """修改本人待生效预约，最多一次、允许跨自习室（FR-04、AC-04-07/08）。"""
        return jsonify(
            {
                "message": "预约修改成功",
                "reservation": modify_reservation(g.user, reservation_id, _payload_dict()),
            }
        )

    @app.post("/api/reservations/<int:reservation_id>/cancel")
    @role_required("student")
    def api_cancel_reservation(reservation_id: int):
        """取消本人预约；开始后拒绝（AC-04-01、AC-04-02）。"""
        try:
            result = cancel_reservation(g.user, reservation_id)
        except ApiError as error:
            record_cancel_failure(g.user, reservation_id, error)
            raise
        return jsonify({"message": "取消成功", "reservation": result})

    @app.post("/api/reservations/<int:reservation_id>/checkin")
    @role_required("student")
    def api_checkin(reservation_id: int):
        """学生签到（FR-04、AC-04-03、AC-04-04、AC-04-06）。"""
        result = checkin_reservation(g.user, reservation_id, _payload_dict())
        return jsonify({"message": "签到成功", "checkin": result})

    @app.post("/api/reservations/<int:reservation_id>/checkout")
    @role_required("student")
    def api_checkout(reservation_id: int):
        """学生签退（FR-04、AC-04-05）。"""
        result = checkout_reservation(g.user, reservation_id)
        return jsonify({"message": "签退成功", "checkout": result})

    @app.post("/api/violations/<int:violation_id>/appeal")
    @role_required("student")
    def api_submit_appeal(violation_id: int):
        """学生发起违约申诉（FR-05、AC-05-03、AC-05-04）。"""
        result = submit_violation_appeal(g.user, violation_id, _payload_dict())
        return jsonify({"message": "申诉已提交", "violation": result})

    @app.get("/api/credit")
    @role_required("student")
    def api_credit():
        """学生本人信用状态（FR-10、AC-10-05）。"""
        return jsonify({"credit": credit_summary(db.get_db(), g.user["id"])})

    @app.post("/api/admin/violations/<int:violation_id>/appeal")
    @role_required("admin", "sysadmin")
    def api_admin_adjudicate_appeal(violation_id: int):
        """管理员审核申诉（FR-05、AC-05-03、AC-05-07）。"""
        result = adjudicate_appeal(g.user, violation_id, _payload_dict())
        return jsonify({"message": "申诉复核完成", "violation": result})

    @app.post("/api/admin/blacklists/<int:blacklist_id>/release")
    @role_required("admin", "sysadmin")
    def api_admin_release_blacklist(blacklist_id: int):
        """管理员提前解除黑名单，原因必填（FR-10、AC-10-04）。"""
        result = release_blacklist(g.user, blacklist_id, _payload_dict())
        return jsonify({"message": "黑名单已解除", "blacklist": result})


    @app.post("/api/admin/blacklists")
    @role_required("admin", "sysadmin")
    def api_admin_add_blacklist():
        """管理员直接加入黑名单（ST-20）。"""
        return jsonify({"message": "已加入黑名单", "blacklist": add_blacklist(g.user, _payload_dict())}), 201

    @app.post("/api/admin/blacklists/<int:blacklist_id>/extend")
    @role_required("admin", "sysadmin")
    def api_admin_extend_blacklist(blacklist_id: int):
        """管理员延长黑名单期限（ST-21）。"""
        return jsonify({"message": "黑名单已延期", "blacklist": extend_blacklist(g.user, blacklist_id, _payload_dict())})

    @app.post("/api/admin/scan")
    @role_required("admin")
    def api_admin_scan():
        """手动触发维护扫描（自动违约、签到状态推进、黑名单到期）。"""
        counts = run_maintenance_scan()
        return jsonify({"message": "扫描完成", "scan": counts, "at": fmt_dt(get_now())})

    @app.get("/api/admin/resources")
    @role_required("admin", "sysadmin")
    def api_admin_resources():
        """授权范围内的自习室—区域—座位结构（FR-02）。"""
        return jsonify(resources_snapshot(db.get_db(), g.user))

    @app.post("/api/admin/rooms")
    @role_required("admin", "sysadmin")
    def api_admin_create_room():
        """新增自习室（FR-02、权限矩阵第 15 行）。"""
        return jsonify({"message": "自习室创建成功", "room": create_room(g.user, _payload_dict())}), 201

    @app.post("/api/admin/rooms/<int:room_id>/zones")
    @role_required("admin", "sysadmin")
    def api_admin_create_zone(room_id: int):
        """在授权自习室下新增区域（AC-02-01、AC-02-03）。"""
        return jsonify({"message": "区域创建成功", "zone": create_zone(g.user, room_id, _payload_dict())}), 201

    @app.post("/api/admin/zones/<int:zone_id>/seats")
    @role_required("admin", "sysadmin")
    def api_admin_create_seat(zone_id: int):
        """在授权区域下新增座位（AC-02-01）。"""
        return jsonify({"message": "座位创建成功", "seat": create_seat(g.user, zone_id, _payload_dict())}), 201

    @app.post("/api/admin/seats/<int:seat_id>/disable")
    @role_required("admin", "sysadmin")
    def api_admin_disable_seat(seat_id: int):
        """停用座位并取消未来预约（AC-02-04、BR-23）。"""
        return jsonify({"message": "座位已停用", "seat": disable_seat(g.user, seat_id, _payload_dict())})

    @app.post("/api/admin/seats/<int:seat_id>/restore")
    @role_required("admin", "sysadmin")
    def api_admin_restore_seat(seat_id: int):
        """恢复停用座位（ST-09、BR-22）。"""
        return jsonify({"message": "座位已恢复", "seat": restore_seat(g.user, seat_id, _payload_dict())})

    @app.post("/api/admin/seats/<int:seat_id>/status")
    @login_required
    def api_direct_seat_status_forbidden(seat_id: int):
        """显式拒绝任何角色直接改写座位状态（AC-02-02、BR-02、权限矩阵第 31 行）。"""
        return (
            jsonify(
                {
                    "error": {
                        "code": "DIRECT_STATUS_WRITE_FORBIDDEN",
                        "message": "座位状态只能由预约、签到、签退、违约或管理员停用/恢复流程驱动，禁止手工直接改写（BR-02）",
                    },
                    "seat_id": seat_id,
                }
            ),
            403,
        )

    @app.get("/api/admin/realtime")
    @role_required("admin", "sysadmin")
    def api_admin_realtime():
        """实时座位矩阵（AC-07-01、FR-07）。"""
        room_id_raw = request.args.get("room_id")
        room_id = None
        if room_id_raw:
            try:
                room_id = int(room_id_raw)
            except ValueError:
                raise ApiError(400, "INVALID_FILTER", "room_id 必须为整数")
        return jsonify(realtime_snapshot(db.get_db(), g.user, room_id))

    @app.post("/api/admin/seats/<int:seat_id>/manual-violation")
    @role_required("admin")
    def api_admin_manual_violation(seat_id: int):
        """管理员现场登记 V3 违约（AC-07-02、AC-07-03、AC-07-04）。"""
        return jsonify(
            {"message": "V3 违约登记成功", "violation": manual_violation(g.user, seat_id, _payload_dict())}
        ), 201

    @app.post("/api/admin/reservations/<int:reservation_id>/release")
    @role_required("admin")
    def api_admin_release_reservation(reservation_id: int):
        """管理员提前释放座位/取消预约（AC-07-06）。"""
        return jsonify(
            {
                "message": "预约已提前释放",
                "reservation": admin_release_reservation(
                    g.user, reservation_id, _payload_dict()
                ),
            }
        )

    @app.get("/api/admin/seats/<int:seat_id>/history")
    @role_required("admin", "sysadmin")
    def api_admin_seat_history(seat_id: int):
        """座位历史使用与预约记录（AC-07-05）。"""
        return jsonify(seat_history(db.get_db(), g.user, seat_id))

    @app.post("/api/evaluations")
    @role_required("student")
    def api_submit_evaluation():
        """学生提交评价（FR-08、AC-08-01、AC-08-02）。"""
        return jsonify({"message": "评价提交成功", "evaluation": submit_evaluation(g.user, _payload_dict())}), 201

    @app.get("/api/evaluations/summary")
    @login_required
    def api_evaluation_summary():
        """评价平均分与条数，隐藏评价不计入（AC-08-04）。"""
        target_type = (request.args.get("target_type") or "").strip()
        target_id_raw = request.args.get("target_id", "").strip()
        try:
            target_id = int(target_id_raw)
        except ValueError:
            raise ApiError(400, "INVALID_FIELD", "target_id 必须为整数")
        return jsonify({"summary": evaluation_summary(db.get_db(), target_type, target_id)})

    @app.post("/api/admin/evaluations/<int:evaluation_id>/hide")
    @role_required("admin", "sysadmin")
    def api_admin_hide_evaluation(evaluation_id: int):
        """管理员填写理由隐藏评价（AC-08-03）。"""
        return jsonify({"message": "评价已隐藏", "evaluation": hide_evaluation(g.user, evaluation_id, _payload_dict())})

    @app.post("/api/complaints")
    @role_required("student")
    def api_create_complaint():
        """学生实名提交投诉（AC-09-01、AC-09-02）。"""
        return jsonify({"message": "投诉已提交", "complaint": create_complaint(g.user, _payload_dict())}), 201

    @app.get("/api/complaints/<int:complaint_id>")
    @login_required
    def api_get_complaint(complaint_id: int):
        """查看投诉详情；仅投诉本人或管理员（AC-09-06）。"""
        return jsonify({"complaint": get_complaint_for_viewer(g.user, complaint_id)})

    @app.post("/api/complaints/<int:complaint_id>/review")
    @role_required("student")
    def api_review_complaint(complaint_id: int):
        """投诉人申请复核一次（AC-09-04）。"""
        return jsonify({"message": "复核申请已提交", "complaint": request_complaint_review(g.user, complaint_id)})


    @app.post("/api/complaints/<int:complaint_id>/confirm")
    @role_required("student")
    def api_confirm_complaint(complaint_id: int):
        """投诉人确认反馈并关闭（ST-27）。"""
        return jsonify({"message": "投诉已确认关闭", "complaint": confirm_complaint(g.user, complaint_id)})

    @app.post("/api/admin/complaints/<int:complaint_id>/accept")
    @role_required("admin", "sysadmin")
    def api_admin_accept_complaint(complaint_id: int):
        """管理员受理投诉（AC-09-03 前半）。"""
        return jsonify({"message": "投诉已受理", "complaint": accept_complaint(g.user, complaint_id)})

    @app.post("/api/admin/complaints/<int:complaint_id>/feedback")
    @role_required("admin", "sysadmin")
    def api_admin_feedback_complaint(complaint_id: int):
        """管理员提交投诉反馈（AC-09-03 后半）。"""
        return jsonify({"message": "反馈已提交", "complaint": feedback_complaint(g.user, complaint_id, _payload_dict())})


    @app.post("/api/admin/complaints/<int:complaint_id>/reject")
    @role_required("admin", "sysadmin")
    def api_admin_reject_complaint(complaint_id: int):
        """管理员判定投诉不成立/重复并关闭（ST-25）。"""
        return jsonify({"message": "投诉已关闭", "complaint": reject_complaint(g.user, complaint_id, _payload_dict())})


    @app.get("/api/analytics/export")
    @role_required("admin", "sysadmin", "logistics")
    def api_analytics_export():
        """导出统计 CSV；角色范围同分析页，不含个人信息（FR-11、V1.6）。"""
        filters = analytics_query_args()
        content = analytics_export_csv(g.user, filters)
        conn = db.get_db()
        now_s = fmt_dt(get_now())
        with db.immediate_transaction(conn):
            db.write_audit(
                conn,
                actor_user_id=g.user["id"],
                actor_name=g.user["name"],
                actor_role=role_label(g.user["role"]),
                action="统计导出",
                target_type="统计报表",
                target_id=f"{filters['date_from']}~{filters['date_to']}",
                before=None,
                after={
                    "date_from": filters["date_from"],
                    "date_to": filters["date_to"],
                    "room_id": filters.get("room_id"),
                },
                result="成功",
                created_at=now_s,
                ip_address=request.remote_addr,
            )
        filename = f"analytics_{filters['date_from']}_{filters['date_to']}.csv"
        return Response(
            "\ufeff" + content,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.get("/api/analytics")
    @role_required("admin", "sysadmin", "logistics")
    def api_analytics():
        """柱状图、折线图与统计数值数据（AC-11-01—06）。"""
        filters = analytics_query_args()
        return jsonify(analytics_data(g.user, filters))

    @app.get("/api/notifications")
    @role_required("student", "admin")
    def api_notifications():
        """本人通知列表，支持分类、已读状态与分页（AC-12-01—03）。"""
        filters = notifications_query_args()
        return jsonify(query_notifications(g.user, filters))

    @app.post("/api/notifications/<int:notification_id>/read")
    @role_required("student", "admin")
    def api_read_notification(notification_id: int):
        """标记本人通知已读（AC-12-02）。"""
        return jsonify({"message": "通知已标记为已读", "notification": mark_notification_read(g.user, notification_id)})

    @app.route("/api/notifications/<int:notification_id>", methods=["DELETE"])
    @login_required
    def api_delete_notification_forbidden(notification_id: int):
        """通知不可删除（AC-12-02、DM-11）。"""
        return (
            jsonify(
                {
                    "error": {
                        "code": "NOTIFICATION_IMMUTABLE",
                        "message": "通知只可标记已读，不可删除（DM-11、AC-12-02）",
                    },
                    "notification_id": notification_id,
                }
            ),
            403,
        )


    @app.get("/api/system/users")
    @role_required("sysadmin")
    def api_system_users():
        """系统管理员查询用户；联系方式脱敏（FR-08、V1.6）。"""
        filters = {
            "student_no": request.args.get("student_no", "").strip() or None,
            "name": request.args.get("name", "").strip() or None,
            "role": request.args.get("role", "").strip() or None,
            "page": _positive_int_arg("page", 1, 100000),
            "page_size": _positive_int_arg("page_size", 20, 100),
        }
        return jsonify(list_users_for_sysadmin(filters))

    @app.get("/api/system/admin-room-assignments")
    @role_required("sysadmin")
    def api_admin_assignments():
        """管理员—自习室授权列表（BR-21、V1.6）。"""
        return jsonify({"assignments": admin_assignment_rows(db.get_db())})

    @app.post("/api/system/admin-room-assignments")
    @role_required("sysadmin")
    def api_grant_admin_assignment():
        """授予管理员—自习室授权（BR-21、V1.6）。"""
        return jsonify({"message": "授权已授予", "assignment": grant_admin_room(g.user, _payload_dict())}), 201

    @app.post("/api/system/admin-room-assignments/revoke")
    @role_required("sysadmin")
    def api_revoke_admin_assignment():
        """撤销管理员—自习室授权（BR-21、V1.6）。"""
        return jsonify({"message": "授权已撤销", "assignment": revoke_admin_room(g.user, _payload_dict())})

    @app.get("/api/system/audit-logs")
    @role_required("sysadmin")
    def api_system_audit_logs():
        """系统管理员查询审计日志（AC-14-01—04）。"""
        filters = audit_query_args()
        return jsonify(query_audit_logs(filters))

    @app.get("/api/system/rule-params")
    @role_required("sysadmin")
    def api_system_rule_params():
        """全部规则参数及范围元数据（AC-13-01—04）。"""
        return jsonify({"params": list_rule_params(db.get_db())})

    @app.put("/api/system/rule-params/<param_key>")
    @role_required("sysadmin")
    def api_system_update_rule_param(param_key: str):
        """参数更新：类型/范围校验、即时生效、写参数变更审计（AC-13-01—04）。"""
        return jsonify({"message": "参数已更新", "param": update_rule_param(g.user, param_key, _payload_dict())})

    @app.route("/api/system/audit-logs/<int:log_id>", methods=["PUT", "PATCH", "DELETE"])
    @login_required
    def api_system_audit_logs_immutable(log_id: int):
        """任何角色尝试修改或删除审计日志均被拒绝（AC-14-03、BR-24）。"""
        return (
            jsonify(
                {
                    "error": {
                        "code": "AUDIT_LOG_IMMUTABLE",
                        "message": "审计日志只可查询，不可修改或删除（BR-24、AC-14-03）",
                    },
                    "log_id": log_id,
                }
            ),
            403,
        )

    @app.post("/api/admin/manual-violation")
    @role_required("admin")
    def api_admin_manual_violation_placeholder():
        """兼容 v0.1 路径的管理端点；真实 V3 登记使用座位级接口。"""
        raise ApiError(
            410,
            "USE_SEAT_ENDPOINT",
            "请使用 POST /api/admin/seats/{seat_id}/manual-violation 登记 V3 违约",
        )

    return app


def start_scheduler(
    app: Flask, stop_event: threading.Event | None = None
) -> threading.Thread | None:
    """启动守护线程周期执行维护扫描；间隔读取 P-15（NFR-03）。

    AC-05-01/02、AC-10-03 的自动路径；管理员也可通过 POST /api/admin/scan 手动触发。
    每轮单独打开应用上下文并关闭数据库连接，避免守护线程长期占用文件句柄。
    """
    if not app.config.get("ENABLE_SCHEDULER", True):
        return None

    def worker() -> None:
        while stop_event is None or not stop_event.is_set():
            interval = 60
            try:
                with app.app_context():
                    conn = db.get_db()
                    interval = db.get_rule_int(conn, "violation_scan_seconds")
                    result = run_maintenance_scan(conn)
                    app.logger.info("维护扫描完成：%s", result)
            except Exception:  # 定时任务失败不得终止进程
                app.logger.exception("维护扫描失败，将在下一周期重试")
            wait_seconds = max(1, interval)
            if stop_event is not None:
                if stop_event.wait(wait_seconds):
                    break
            else:
                time_module.sleep(wait_seconds)

    thread = threading.Thread(target=worker, name="zxss-maintenance", daemon=True)
    thread.start()
    app.extensions["maintenance_thread"] = thread
    return thread


app = create_app()


if __name__ == "__main__":
    # 每个版本使用独立端口与独立数据库（版本管理规则第 6、7 条）。
    start_scheduler(app)
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=False)
