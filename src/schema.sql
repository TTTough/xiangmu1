-- 智慧自习室预约与管理系统 v0.11（S11）数据库结构
-- 对应 SRS V1.3：DM-01—DM-13；FR-01—FR-14。
-- 本版在基础结构上增加规则参数范围、预约修改、投诉房间范围等字段。
-- 本版使用全新独立数据库，不做跨版本迁移。
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_no          TEXT    NOT NULL UNIQUE,
    name                TEXT    NOT NULL,
    department          TEXT,
    contact             TEXT,
    role                TEXT    NOT NULL CHECK (role IN ('student', 'admin', 'sysadmin', 'logistics')),
    password_hash       TEXT    NOT NULL,
    -- 正常／黑名单／锁定：沿用 DM-04 的可展示账号状态。
    -- 锁定只限制登录；解锁时恢复 pre_lock_status，避免覆盖黑名单状态。
    account_status      TEXT    NOT NULL DEFAULT '正常' CHECK (account_status IN ('正常', '黑名单', '锁定')),
    pre_lock_status     TEXT,
    failed_login_count  INTEGER NOT NULL DEFAULT 0,
    locked_until        TEXT,
    blacklist_until     TEXT,
    -- DM-04 / DM-07：仅「生效中」「申诉中」记录参与有效违约计数。
    effective_violation_count INTEGER NOT NULL DEFAULT 0 CHECK (effective_violation_count >= 0),
    created_at          TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS rooms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    building    TEXT    NOT NULL,
    floor       TEXT    NOT NULL,
    location    TEXT,
    open_from   TEXT    NOT NULL,
    open_to     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT '开放' CHECK (status IN ('开放', '关闭')),
    note        TEXT,
    created_at  TEXT    NOT NULL,
    CHECK (open_to > open_from)
);

CREATE TABLE IF NOT EXISTS zones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id     INTEGER NOT NULL REFERENCES rooms(id),
    code        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    zone_type   TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (room_id, code),
    UNIQUE (room_id, name)
);

-- 管理员被授权的自习室范围（BR-21，权限矩阵第 15、16、17、18 行）。
CREATE TABLE IF NOT EXISTS admin_room_assignments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL REFERENCES users(id),
    room_id       INTEGER NOT NULL REFERENCES rooms(id),
    created_at    TEXT    NOT NULL,
    UNIQUE (admin_user_id, room_id)
);
CREATE INDEX IF NOT EXISTS idx_admin_room_user ON admin_room_assignments(admin_user_id);

CREATE TABLE IF NOT EXISTS seats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT    NOT NULL UNIQUE,
    room_id      INTEGER NOT NULL REFERENCES rooms(id),
    zone_id      INTEGER NOT NULL REFERENCES zones(id),
    seat_type    TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT '空闲' CHECK (status IN ('空闲', '已预约', '使用中', '停用')),
    position     TEXT,
    is_bookable  INTEGER NOT NULL DEFAULT 1 CHECK (is_bookable IN (0, 1)),
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seats_room_zone ON seats(room_id, zone_id);
CREATE INDEX IF NOT EXISTS idx_seats_type ON seats(seat_type);

CREATE TABLE IF NOT EXISTS reservations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_no    TEXT    NOT NULL UNIQUE,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    seat_id           INTEGER NOT NULL REFERENCES seats(id),
    room_id           INTEGER NOT NULL REFERENCES rooms(id),
    zone_id           INTEGER NOT NULL REFERENCES zones(id),
    reservation_date  TEXT    NOT NULL,
    start_time        TEXT    NOT NULL,
    end_time          TEXT    NOT NULL,
    status            TEXT    NOT NULL DEFAULT '待生效'
                      CHECK (status IN ('待生效', '待签到', '使用中', '已完成', '已取消', '已违约')),
    source            TEXT    NOT NULL DEFAULT '学生自助' CHECK (source IN ('学生自助', '管理员代创建')),
    created_by        INTEGER REFERENCES users(id),
    admin_reason      TEXT,
    modify_count      INTEGER NOT NULL DEFAULT 0 CHECK (modify_count >= 0),
    modified_at       TEXT,
    created_at        TEXT    NOT NULL,
    cancelled_at      TEXT,
    cancel_reason     TEXT,
    CHECK (end_time > start_time)
);
CREATE INDEX IF NOT EXISTS idx_reservations_seat_date
    ON reservations(seat_id, reservation_date, status, start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_reservations_user_status
    ON reservations(user_id, status);
CREATE INDEX IF NOT EXISTS idx_reservations_room
    ON reservations(room_id, reservation_date);

CREATE TABLE IF NOT EXISTS checkins (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id INTEGER NOT NULL UNIQUE REFERENCES reservations(id),
    checkin_at     TEXT    NOT NULL,
    method         TEXT    NOT NULL,
    checkout_at    TEXT,
    actual_minutes INTEGER,
    CHECK (actual_minutes IS NULL OR actual_minutes >= 0)
);

CREATE TABLE IF NOT EXISTS violations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    violation_no        TEXT    NOT NULL UNIQUE,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    reservation_id      INTEGER REFERENCES reservations(id),
    seat_id             INTEGER NOT NULL REFERENCES seats(id),
    violation_type      TEXT    NOT NULL CHECK (violation_type IN ('V1 未签到', 'V2 未签退', 'V3 管理员手动登记')),
    occurred_at         TEXT    NOT NULL,
    basis               TEXT    NOT NULL,
    result              TEXT,
    status              TEXT    NOT NULL DEFAULT '生效中'
                        CHECK (status IN ('生效中', '申诉中', '申诉成立已撤销', '申诉不成立已终结')),
    appeal_reason       TEXT,
    appeal_at           TEXT,
    appeal_conclusion   TEXT,
    appeal_judged_at    TEXT,
    appeal_judged_by    INTEGER REFERENCES users(id),
    registered_by       INTEGER REFERENCES users(id),
    created_at          TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_violations_user_status ON violations(user_id, status);
-- BR-11：同一预约单同一违约事实不重复生成记录（V1/V2）。
CREATE UNIQUE INDEX IF NOT EXISTS uq_violations_reservation_type
    ON violations(reservation_id, violation_type)
    WHERE reservation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS blacklists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    reason          TEXT    NOT NULL,
    source          TEXT    NOT NULL CHECK (source IN ('自动', '管理员')),
    effective_at    TEXT    NOT NULL,
    expires_at      TEXT    NOT NULL,
    released_at     TEXT,
    release_reason  TEXT,
    status          TEXT    NOT NULL DEFAULT '生效中' CHECK (status IN ('生效中', '已解除', '已到期')),
    created_by      INTEGER REFERENCES users(id),
    created_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blacklists_user_status ON blacklists(user_id, status, expires_at);

-- DM-11 的最小实现：预约成功、违约、黑名单、申诉结果通知；外部通道与完整 FR-12 不在本版范围。
CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    notification_type TEXT  NOT NULL,
    title           TEXT    NOT NULL,
    content         TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    read_at         TEXT,
    delivery_result TEXT    NOT NULL DEFAULT '系统内消息已送达',
    event_key       TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_event_key
    ON notifications(event_key) WHERE event_key IS NOT NULL;

-- AC-12-02：通知只可标记已读，不可删除。
CREATE TRIGGER IF NOT EXISTS trg_notifications_no_delete
BEFORE DELETE ON notifications
BEGIN
    SELECT RAISE(ABORT, 'NOTIFICATION_IMMUTABLE');
END;

-- DM-08 评价：同一学生对同一对象仅一条；隐藏评价不计入平均分。
CREATE TABLE IF NOT EXISTS evaluations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_no   TEXT    NOT NULL UNIQUE,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    target_type     TEXT    NOT NULL CHECK (target_type IN ('座位', '自习室')),
    target_id       INTEGER NOT NULL,
    rating          INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    submitted_at    TEXT    NOT NULL,
    hidden          INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
    hidden_reason   TEXT,
    hidden_by       INTEGER REFERENCES users(id),
    hidden_at       TEXT,
    UNIQUE (user_id, target_type, target_id)
);
CREATE INDEX IF NOT EXISTS idx_evaluations_target
    ON evaluations(target_type, target_id, hidden);

-- DM-09 投诉单：待受理→处理中→已回复→已关闭；复核最多一次。
CREATE TABLE IF NOT EXISTS complaints (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_no       TEXT    NOT NULL UNIQUE,
    complainant_id     INTEGER NOT NULL REFERENCES users(id),
    object_type        TEXT    NOT NULL
                       CHECK (object_type IN ('座位或自习室', '其他用户', '管理员')),
    object_ref         TEXT,
    room_id            INTEGER REFERENCES rooms(id),
    complained_user_id INTEGER REFERENCES users(id),
    complaint_type     TEXT    NOT NULL,
    content            TEXT    NOT NULL,
    evidence_attachment TEXT,
    status             TEXT    NOT NULL DEFAULT '待受理'
                       CHECK (status IN ('待受理', '处理中', '已回复', '已关闭')),
    handler_id         INTEGER REFERENCES users(id),
    accepted_at        TEXT,
    feedback           TEXT,
    feedback_at        TEXT,
    closed_at          TEXT,
    close_reason       TEXT,
    review_used        INTEGER NOT NULL DEFAULT 0 CHECK (review_used IN (0, 1)),
    review_requested_at TEXT,
    created_at         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status, created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_complainant ON complaints(complainant_id, created_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id   INTEGER REFERENCES users(id),
    actor_name      TEXT    NOT NULL,
    actor_role      TEXT    NOT NULL,
    action          TEXT    NOT NULL,
    target_type     TEXT    NOT NULL,
    target_id       TEXT    NOT NULL,
    before_json     TEXT,
    after_json      TEXT,
    result          TEXT    NOT NULL,
    ip_address      TEXT,
    created_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_actor_time ON audit_logs(actor_name, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action_time ON audit_logs(action, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_logs(target_type, target_id);

CREATE TABLE IF NOT EXISTS rule_params (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    param_no            TEXT    NOT NULL UNIQUE,
    param_key           TEXT    NOT NULL UNIQUE,
    name                TEXT    NOT NULL,
    value               TEXT    NOT NULL,
    default_value       TEXT    NOT NULL,
    value_type          TEXT    NOT NULL CHECK (value_type IN ('int', 'float', 'string', 'bool')),
    min_value           REAL,
    max_value           REAL,
    unit                TEXT,
    range_text          TEXT,
    description         TEXT,
    source_nature       TEXT    NOT NULL,
    confirmation_status TEXT    NOT NULL,
    suggested_confirmer TEXT,
    related_rule        TEXT,
    related_question    TEXT,
    updated_by          INTEGER REFERENCES users(id),
    updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_rule_params_key ON rule_params(param_key);

-- NFR-05：同一座位同一日期、同一时段的有效预约至多一条。
-- 应用层使用 BEGIN IMMEDIATE 串行化写入；触发器在数据库层提供等价唯一约束，
-- 防止两个并发事务都通过 SELECT 后重复写入。
CREATE TRIGGER IF NOT EXISTS trg_reservations_no_overlap_insert
BEFORE INSERT ON reservations
WHEN NEW.status IN ('待生效', '待签到', '使用中')
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM reservations r
        WHERE r.seat_id = NEW.seat_id
          AND r.reservation_date = NEW.reservation_date
          AND r.status IN ('待生效', '待签到', '使用中')
          AND r.start_time < NEW.end_time
          AND NEW.start_time < r.end_time
    ) THEN RAISE(ABORT, 'SEAT_TIME_CONFLICT') END;
END;

CREATE TRIGGER IF NOT EXISTS trg_reservations_no_overlap_update
BEFORE UPDATE OF seat_id, reservation_date, start_time, end_time, status ON reservations
WHEN NEW.status IN ('待生效', '待签到', '使用中')
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM reservations r
        WHERE r.id <> NEW.id
          AND r.seat_id = NEW.seat_id
          AND r.reservation_date = NEW.reservation_date
          AND r.status IN ('待生效', '待签到', '使用中')
          AND r.start_time < NEW.end_time
          AND NEW.start_time < r.end_time
    ) THEN RAISE(ABORT, 'SEAT_TIME_CONFLICT') END;
END;

-- BR-24：审计日志只可查询，不可修改或删除。
CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_update
BEFORE UPDATE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'AUDIT_LOG_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_delete
BEFORE DELETE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'AUDIT_LOG_IMMUTABLE');
END;
