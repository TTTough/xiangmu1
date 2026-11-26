"""应用配置与规则参数默认值。

业务数值不在路由中硬编码：config.py 保存附录 A 的默认值与来源元数据，
启动时由 seed.py 写入 rule_params 表，运行时一律从数据库读取。
对应：FR-13、NFR-12；附录 A P-01—P-28。
"""
from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("ZXSS_SECRET_KEY", "zxss-dev-only-change-before-production")
    DATABASE = str(BASE_DIR / "data" / "app.db")
    HOST = "127.0.0.1"
    PORT = 5012
    TESTING = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    JSON_AS_ASCII = False
    # 由 __main__ 启动；扫描间隔仍从 rule_params 的 P-15 读取。
    ENABLE_SCHEDULER = True
    # 由 create_app 注入；测试可替换为假时钟（NFR-18）。
    NOW_PROVIDER = None


ROLE_LABELS = {
    "student": "学生",
    "admin": "自习室管理员",
    "sysadmin": "系统管理员",
    "logistics": "后勤/场馆管理部门",
}


def _p(no, key, name, value, value_type, unit, source, status, rule, question,
       confirmer="—", range_text="SRS 附录 A 未规定取值范围"):
    """构造一条附录 A 参数元数据（默认值 = 本 Sprint 采纳值）。"""
    return {
        "param_no": no,
        "param_key": key,
        "name": name,
        "value": str(value),
        "default_value": str(value),
        "value_type": value_type,
        "unit": unit,
        "range_text": range_text,
        "description": f"{no} {name}；关联 {rule}",
        "source_nature": source,
        "confirmation_status": status,
        "suggested_confirmer": confirmer,
        "related_rule": rule,
        "related_question": question,
    }


# 附录 A P-01—P-28，来源性质与确认状态照录 SRS；教学模拟确认不等于真实业务方确认。
RULE_PARAM_DEFAULTS = [
    _p("P-01", "max_active_reservations", "同时有效预约上限", 1, "int", "个",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-04", "Q-01", "模拟自习室管理员",
       "正整数"),
    _p("P-02", "min_duration_minutes", "单次预约时长下限", 30, "int", "分钟",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-05", "Q-02", "模拟自习室管理员",
       "正整数且小于上限"),
    _p("P-03", "max_duration_minutes", "单次预约时长上限", 240, "int", "分钟",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-05", "Q-02", "模拟自习室管理员",
       "正整数且大于下限"),
    _p("P-04", "advance_booking_days", "可提前预约天数", 7, "int", "天",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-06", "Q-03", "模拟自习室管理员",
       "非负整数"),
    _p("P-05", "checkin_early_minutes", "签到窗口提前量", 15, "int", "分钟",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-07", "Q-04", "模拟自习室管理员",
       "非负整数"),
    _p("P-06", "checkin_late_minutes", "签到窗口延后量", 15, "int", "分钟",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-07", "Q-04", "模拟自习室管理员",
       "非负整数"),
    _p("P-07", "blacklist_threshold", "黑名单触发违约次数", 3, "int", "次",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-12", "Q-09", "模拟自习室管理员",
       "正整数"),
    _p("P-08", "blacklist_days", "黑名单期限", 7, "int", "天",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-12", "Q-09", "模拟自习室管理员",
       "正整数"),
    _p("P-09", "appeal_days", "违约申诉期", 3, "int", "自然日",
       "分析推导", "教学模拟已确认（2026-10-29）", "BR-14", "Q-16", "模拟自习室管理员",
       "非负整数"),
    _p("P-10", "complaint_accept_workdays", "投诉受理时限", 2, "int", "工作日",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-16", "Q-17", "模拟自习室管理员",
       "非负整数"),
    _p("P-11", "complaint_feedback_workdays", "投诉反馈时限", 3, "int", "工作日",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-16", "Q-17", "模拟自习室管理员",
       "非负整数"),
    _p("P-12", "complaint_review_days", "复核申请期", 3, "int", "自然日",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-17", "Q-17", "模拟自习室管理员",
       "非负整数"),
    _p("P-13", "complaint_auto_close_days", "投诉自动关闭时限", 3, "int", "自然日",
       "AI 候选", "教学模拟已确认（2026-10-29）", "ST-28", "Q-17", "模拟自习室管理员",
       "非负整数"),
    _p("P-14", "data_refresh_seconds", "数据刷新间隔", 10, "int", "秒",
       "原始资料", "团队已复核", "BR-20", "—", "—", "正整数"),
    _p("P-15", "violation_scan_seconds", "违约判定扫描间隔", 60, "int", "秒",
       "AI 候选", "待确认", "NFR-03", "Q-18", "模拟系统管理员", "正整数"),
    _p("P-16", "cancellation_threshold_minutes", "距开始时间不足的取消限制阈值",
       30, "int", "分钟", "AI 候选", "待确认", "BR-10", "Q-07", "模拟自习室管理员",
       "非负整数"),
    _p("P-17", "session_idle_minutes", "会话空闲超时", 30, "int", "分钟",
       "AI 候选", "待确认", "NFR-08", "Q-19", "模拟系统管理员", "正整数"),
    _p("P-18", "max_concurrent_users", "并发在线用户数", 500, "int", "人",
       "AI 候选", "待确认", "NFR-04", "Q-20", "模拟系统管理员", "正整数"),
    _p("P-19", "retention_years", "数据与日志保留期限", 2, "int", "年",
       "AI 候选", "待确认", "NFR-14", "Q-21", "模拟系统管理员", "正整数"),
    _p("P-20", "login_lock_threshold", "连续登录失败锁定阈值", 5, "int", "次",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-25", "Q-19", "模拟系统管理员",
       "正整数"),
    _p("P-21", "lock_duration_minutes", "账号锁定时长", 15, "int", "分钟",
       "AI 候选", "教学模拟已确认（2026-10-29）", "BR-25", "Q-19", "模拟系统管理员",
       "正整数"),
    _p("P-22", "query_response_seconds", "常规查询响应时间上限", 2, "int", "秒",
       "AI 候选", "待确认", "NFR-02", "Q-20", "模拟系统管理员", "正数"),
    _p("P-23", "availability_target_percent", "服务可用率目标", 99.5, "float", "%",
       "AI 候选", "待确认", "NFR-06", "Q-20", "模拟系统管理员", "0—100"),
    _p("P-24", "backup_frequency_hours", "数据备份频率", 24, "int", "小时",
       "AI 候选", "待确认", "NFR-15", "Q-21", "模拟系统管理员", "正整数"),
    _p("P-25", "rto_hours", "恢复时间目标", 4, "int", "小时",
       "AI 候选", "待确认", "NFR-15", "Q-21", "模拟系统管理员", "非负整数"),
    _p("P-26", "rpo_hours", "恢复点目标", 24, "int", "小时",
       "AI 候选", "待确认", "NFR-15", "Q-21", "模拟系统管理员", "非负整数"),
    _p("P-27", "max_booking_steps", "预约主流程操作步数上限", 3, "int", "步",
       "AI 候选", "待确认", "NFR-10", "Q-22", "模拟自习室管理员", "正整数"),
    _p("P-28", "max_checkin_methods", "签到方式数量上限", 2, "int", "种",
       "AI 候选", "待确认", "NFR-10", "Q-22", "模拟自习室管理员", "正整数"),
]

# AC-13-02：SRS 附录 A 未给统一取值范围，以下为可校验的实现默认区间；
# 来源与确认状态不变，范围待业务方确认（见 docs/open-questions.md OQ-33）。
RULE_PARAM_RANGES = {
    "P-01": (1, 2),
    "P-02": (15, 120),
    "P-03": (60, 480),
    "P-04": (1, 30),
    "P-05": (0, 60),
    "P-06": (0, 60),
    "P-07": (1, 10),
    "P-08": (1, 30),
    "P-09": (1, 30),
    "P-10": (1, 10),
    "P-11": (1, 15),
    "P-12": (1, 30),
    "P-13": (1, 30),
    "P-14": (5, 60),
    "P-15": (10, 60),
    "P-16": (0, 120),
    "P-17": (5, 120),
    "P-18": (1, 10000),
    "P-19": (1, 10),
    "P-20": (1, 10),
    "P-21": (1, 120),
    "P-22": (1, 10),
    "P-23": (90, 100),
    "P-24": (1, 168),
    "P-25": (1, 24),
    "P-26": (1, 72),
    "P-27": (1, 10),
    "P-28": (1, 2),
}

for _item in RULE_PARAM_DEFAULTS:
    _low, _high = RULE_PARAM_RANGES[_item["param_no"]]
    _item["min_value"] = _low
    _item["max_value"] = _high
    _item["range_text"] = f"{_low}—{_high} {_item['unit'] or ''}".strip()

RULE_PARAM_BY_KEY = {item["param_key"]: item for item in RULE_PARAM_DEFAULTS}

# v0.8 基线对齐：参数生效点。仅列已接入运行时判定的参数；未列出的统一标“未接入”。
# 该映射用于参数页展示与 AC-13-01 的宣称范围，不改变参数值本身。
PARAM_EFFECT_POINTS = {
    "max_active_reservations": "创建预约：同时有效预约上限校验",
    "min_duration_minutes": "创建预约：单次时长下限校验",
    "max_duration_minutes": "创建预约：单次时长上限校验",
    "advance_booking_days": "创建预约：提前预约天数校验",
    "checkin_early_minutes": "签到窗口起点与待签到推进",
    "checkin_late_minutes": "签到截止时刻与 V1 违约判定",
    "blacklist_threshold": "违约后黑名单触发与申诉回退重算",
    "blacklist_days": "黑名单期限与到期解除",
    "appeal_days": "学生违约申诉期判定",
    "complaint_auto_close_days": "投诉反馈后自动关闭",
    "data_refresh_seconds": "数据分析页局部刷新间隔",
    "violation_scan_seconds": "后台维护扫描周期",
    "session_idle_minutes": "会话空闲失效判定",
    "login_lock_threshold": "登录失败锁定阈值",
    "lock_duration_minutes": "账号锁定时长",
}

