# AC → 测试 → 页面映射表（v1.0）

- 对应 SRS：V1.7（70 条 AC）
- 测试框架：pytest；运行命令：`python -m pytest -q`
- 当前结果：**128 passed**，70/70 AC 均有自动化测试
- 测试路径均相对 `tests/`

| AC | 测试文件::测试用例 | 页面 / 入口 |
|---|---|---|
| AC-01-01 | `test_auth.py::test_ac_01_01_student_login_enters_student_workspace` | `/student`、`/login` |
| AC-01-02 | `test_auth.py::test_ac_01_02_admin_login_shows_management_entries` | `/admin`、`/login` |
| AC-01-03 | `test_auth.py::test_ac_01_03_student_admin_request_rejected_without_changes` | `/admin`、`/api/admin/manual-violation` |
| AC-01-04 | `test_auth.py::test_ac_01_04_login_lock_expiry_and_existing_reservation` | `/login` |
| AC-02-01 | `test_sprint3_resources.py::test_ac_02_01_create_zone_and_seat_under_authorized_room` | `/admin/resources` |
| AC-02-02 | `test_sprint3_resources.py::test_ac_02_02_direct_seat_status_write_forbidden_for_all_roles` | `/admin/resources`、`/api/admin/seats/{id}/status` |
| AC-02-03 | `test_sprint3_resources.py::test_ac_02_03_cross_room_zone_creation_rejected` | `/admin/resources` |
| AC-02-04 | `test_sprint3_resources.py::test_ac_02_04_disable_seat_cancels_future_reservation_without_violation` | `/admin/resources` |
| AC-03-01 | `test_reservation.py::test_ac_03_01_create_reservation_updates_seat_notifies_and_audits` | `/seats` |
| AC-03-02 | `test_reservation.py::test_ac_03_02_blacklist_rejects_reservation_without_side_effects` | `/seats` |
| AC-03-03 | `test_reservation.py::test_ac_03_03_second_active_reservation_rejected` | `/seats` |
| AC-03-04 | `test_reservation.py::test_ac_03_04_duration_and_advance_days_rejected` | `/seats` |
| AC-03-05 | `test_reservation.py::test_ac_03_05_concurrent_booking_only_one_succeeds` | `/seats` |
| AC-04-01 | `test_cancel.py::test_ac_04_01_cancel_before_start_releases_seat_without_violation` | `/reservations` |
| AC-04-02 | `test_cancel.py::test_ac_04_02_cancel_after_start_rejected_and_state_unchanged` | `/reservations` |
| AC-04-03 | `test_sprint2_usage.py::test_ac_04_03_checkin_within_window` | `/usage` |
| AC-04-04 | `test_sprint2_usage.py::test_ac_04_04_checkin_before_window_rejected` | `/usage` |
| AC-04-05 | `test_sprint2_usage.py::test_ac_04_05_checkout_records_actual_duration` | `/usage` |
| AC-04-06 | `test_sprint2_usage.py::test_ac_04_06_checkin_wrong_seat_rejected` | `/usage` |
| AC-04-07 | `test_sprint11_modify.py::test_ac_04_07_cross_room_modify_success`<br>`test_sprint11_modify.py::test_ac_04_07_same_room_modify_success` | `/reservations`、`/reservations/{id}/modify` |
| AC-04-08 | `test_sprint11_modify.py::test_ac_04_08_target_conflict_rejected_and_original_unchanged` 等 | `/reservations/{id}/modify` |
| AC-05-01 | `test_sprint2_violations.py::test_ac_05_01_scan_generates_v1_and_releases_seat` | `/admin/maintenance` |
| AC-05-02 | `test_sprint2_violations.py::test_ac_05_02_scan_generates_v2_for_unchecked_out_usage` | `/admin/maintenance` |
| AC-05-03 | `test_sprint2_violations.py::test_ac_05_03_appeal_approved_reverses_and_audits` | `/violations`、`/admin/appeals` |
| AC-05-04 | `test_sprint2_violations.py::test_ac_05_04_appeal_after_deadline_rejected`<br>`test_sprint2_violations.py::test_ac_05_04_already_appealed_record_cannot_appeal_again` | `/violations` |
| AC-05-05 | `test_sprint2_violations.py::test_ac_05_05_new_violation_at_threshold_enters_blacklist` | `/admin/maintenance`、`/credit` |
| AC-05-06 | `test_sprint2_violations.py::test_ac_05_06_rescan_does_not_duplicate_violation` | `/admin/maintenance` |
| AC-05-07 | `test_sprint2_violations.py::test_ac_05_07_appeal_rejected_stays_effective` | `/admin/appeals` |
| AC-06-01 | `test_seats.py::test_ac_06_01_filter_multiple_rooms_and_annotate_availability` | `/seats` |
| AC-06-02 | `test_sprint4_records.py::test_ac_06_02_student_only_sees_own_reservations` | `/records` |
| AC-06-03 | `test_sprint4_records.py::test_ac_06_03_admin_only_sees_authorized_room_records` | `/records` |
| AC-06-04 | `test_sprint4_records.py::test_ac_06_04_pagination_preserves_filters` | `/records` |
| AC-07-01 | `test_sprint3_realtime.py::test_ac_07_01_realtime_view_masks_occupant_and_shows_slot` | `/admin/realtime` |
| AC-07-02 | `test_sprint3_realtime.py::test_ac_07_02_manual_violation_without_reason_rejected` | `/admin/realtime` |
| AC-07-03 | `test_sprint3_realtime.py::test_ac_07_03_manual_violation_creates_v3_releases_and_notifies` | `/admin/realtime` |
| AC-07-04 | `test_sprint3_realtime.py::test_ac_07_04_manual_violation_on_unauthorized_room_rejected` | `/admin/realtime` |
| AC-07-05 | `test_sprint3_realtime.py::test_ac_07_05_seat_history_masks_user_and_shows_usage` | `/admin/seats/{id}/history` |
| AC-07-06 | `test_sprint3_realtime.py::test_ac_07_06_release_reservation_requires_reason_and_notifies` | `/admin/realtime` |
| AC-08-01 | `test_sprint5_evaluations.py::test_ac_08_01_evaluation_requires_real_completed_use` | `/evaluations` |
| AC-08-02 | `test_sprint5_evaluations.py::test_ac_08_02_duplicate_evaluation_rejected` | `/evaluations` |
| AC-08-03 | `test_sprint5_evaluations.py::test_ac_08_03_hide_requires_reason_and_audits` | `/admin/evaluations` |
| AC-08-04 | `test_sprint5_evaluations.py::test_ac_08_04_average_excludes_hidden` | `/evaluations`、`/api/evaluations/summary` |
| AC-09-01 | `test_sprint5_complaints.py::test_ac_09_01_student_submits_complaint_and_admin_notified` | `/complaints`、`/admin/complaints` |
| AC-09-02 | `test_sprint5_complaints.py::test_ac_09_02_unauthenticated_complaint_rejected` | `/complaints` |
| AC-09-03 | `test_sprint5_complaints.py::test_ac_09_03_admin_accepts_and_feedback_visible_to_student` | `/complaints`、`/admin/complaints` |
| AC-09-04 | `test_sprint5_complaints.py::test_ac_09_04_review_only_once` | `/complaints` |
| AC-09-05 | `test_sprint5_complaints.py::test_ac_09_05_timeout_auto_closes_and_notifies` | `/admin/maintenance`、`/complaints` |
| AC-09-06 | `test_sprint5_complaints.py::test_ac_09_06_complained_student_masked_for_complainant` | `/complaints` |
| AC-10-01 | `test_sprint2_blacklist.py::test_ac_10_01_threshold_triggers_blacklist_and_notice` | `/admin/maintenance`、`/credit` |
| AC-10-02 | `test_sprint2_blacklist.py::test_ac_10_02_blacklisted_student_cannot_create_reservation` | `/seats` |
| AC-10-03 | `test_sprint2_blacklist.py::test_ac_10_03_expired_blacklist_restored_by_scan` | `/admin/maintenance`、`/credit` |
| AC-10-04 | `test_sprint2_blacklist.py::test_ac_10_04_admin_release_requires_reason_and_audits` | `/admin/blacklists` |
| AC-10-05 | `test_sprint2_blacklist.py::test_ac_10_05_credit_status_shows_remaining_and_conditions` | `/credit` |
| AC-11-01 | `test_sprint6_analytics.py::test_ac_11_01_page_uses_ten_second_local_refresh` | `/analytics` |
| AC-11-02 | `test_sprint6_analytics.py::test_ac_11_02_api_contains_bar_line_and_required_stats` | `/analytics` |
| AC-11-03 | `test_sprint6_analytics.py::test_ac_11_03_filters_preserved_across_repeated_refresh` | `/analytics` |
| AC-11-04 | `test_sprint6_analytics.py::test_ac_11_04_changing_filter_recalculates_data` | `/analytics` |
| AC-11-05 | `test_sprint6_analytics.py::test_ac_11_05_logistics_is_read_only` | `/analytics` |
| AC-11-06 | `test_sprint6_analytics.py::test_ac_11_06_refresh_does_not_reload_or_reset_expanded_detail` | `/analytics` |
| AC-12-01 | `test_sprint6_notifications.py::test_ac_12_01_events_create_categorized_notifications` | `/notifications` |
| AC-12-02 | `test_sprint6_notifications.py::test_ac_12_02_notifications_can_be_read_but_not_deleted` | `/notifications` |
| AC-12-03 | `test_sprint6_notifications.py::test_ac_12_03_notification_list_includes_delivery_record` | `/notifications` |
| AC-13-01 | `test_sprint7_params.py::test_ac_13_01_updated_checkin_window_takes_effect` | `/sysadmin/params`、`/usage` |
| AC-13-02 | `test_sprint7_params.py::test_ac_13_02_out_of_range_rejected_and_original_kept` | `/sysadmin/params` |
| AC-13-03 | `test_sprint7_params.py::test_ac_13_03_parameter_change_audit_has_before_after` | `/sysadmin/params`、`/sysadmin/audit` |
| AC-13-04 | `test_sprint7_params.py::test_ac_13_04_parameter_change_does_not_retroactively_apply` | `/sysadmin/params`、`/admin/maintenance` |
| AC-14-01 | `test_sprint4_audit.py::test_ac_14_01_required_management_operations_have_complete_audit` | `/sysadmin/audit` |
| AC-14-02 | `test_sprint4_audit.py::test_ac_14_02_parameter_change_shows_before_and_after` | `/sysadmin/audit`、`/sysadmin/params` |
| AC-14-03 | `test_sprint4_audit.py::test_ac_14_03_audit_update_or_delete_rejected` | `/sysadmin/audit` |
| AC-14-04 | `test_sprint4_audit.py::test_ac_14_04_audit_filter_and_pagination` | `/sysadmin/audit` |

## 额外非 AC 专项测试（6 条）

| 测试 | 目的 |
|---|---|
| `test_cancel.py::test_audit_required_fields_for_sprint1_actions` | 审计字段基础 |
| `test_cancel.py::test_rule_params_seeded_with_provenance` | 参数来源/确认状态落库 |
| `test_sprint2_violations.py::test_sprint2_scheduler_runs_scan_automatically` | 后台扫描线程 |
| `test_sprint4_audit.py::test_audit_endpoints_are_sysadmin_only` | 审计访问权限 |
| `test_sprint4_audit.py::test_all_existing_operations_are_audited` | 全操作审计覆盖 |
| 上述 68 行中 AC-05-04 额外分支 | 再次申诉分支 |

> 说明：部分测试覆盖多个 AC；本表按每个 AC 至少一条映射列出。v1.0 总测试数 128 = v0.10 的 117 条 + 11 条 S11 测试；AC 总数 70。

## v0.8 基线对齐补充测试（不新增 AC）

| 覆盖点 | 测试 | 关联 |
|---|---|---|
| sysadmin 按权限矩阵访问；手动违约与提前释放 403 | `test_sprint8_baseline.py::test_sysadmin_permissions_match_matrix_and_forbidden_actions` | 权限矩阵第 15—30 行 |
| sysadmin 受理投诉、解除黑名单 | `test_sprint8_baseline.py::test_sysadmin_can_accept_complaint_and_release_blacklist` | AC-09-03、AC-10-04 |
| sysadmin 审核违约申诉 | `test_sprint8_baseline.py::test_sysadmin_can_adjudicate_appeal` | AC-05-03、AC-05-07 |
| P-15 范围为 10—60 秒，61 被拒、60 可保存 | `test_sprint8_baseline.py::test_p15_range_is_10_to_60_and_page_synced` | AC-13-02、NFR-03 |
| 28 项参数标注生效点/未接入 | `test_sprint8_baseline.py::test_parameter_effect_annotations_cover_all_28` | AC-13-01（仅已接入参数） |
| Q-33 座位状态仅展示，不同时段仍可预约 | `test_sprint8_baseline.py::test_q33_seat_status_is_display_only_and_slot_conflict_rules` | AC-03-01、AC-06-01 |
| Q-34 签到窗口起点推进待签到 | `test_sprint8_baseline.py::test_q34_scan_promotes_at_checkin_window_start` | AC-04-03、AC-05-01 |
| Q-35 同一预约单只生成一条违约 | `test_sprint8_baseline.py::test_q35_single_violation_no_v1_v2_double_record` | AC-05-01、AC-05-06 |
| v0.8 独立端口与数据库 | `test_sprint8_baseline.py::test_v08_uses_independent_port_and_database` | 版本基线 |

## v0.9 S9 补充测试（不新增 AC）

| 覆盖点 | 测试 | 关联 |
|---|---|---|
| 旧库缺失 rule_params 逐项补种、不覆盖已有值 | `test_sprint9_backlog.py::test_adr06_seed_replenishes_missing_params_without_overwrite` | ADR-06 |
| 管理员代创建、来源/原因/审计 | `test_sprint9_backlog.py::test_admin_proxy_creates_for_student_and_audits` | FR-03、AC-03-01—05、BR-22 |
| 代创建仅目标学生可见 | `test_sprint9_backlog.py::test_proxy_reservation_visible_only_to_target_student` | FR-06、NFR-07 |
| 代创建必填原因、sysadmin/学生 403 | `test_sprint9_backlog.py::test_admin_proxy_requires_reason`、`test_admin_proxy_forbidden_for_sysadmin_and_student` | 权限矩阵第 4 行 |
| 投诉驳回关闭（ST-25）与审计/通知 | `test_sprint9_backlog.py::test_complaint_reject_closes_and_notifies` 等 | AC-09-03、ST-25 |
| 投诉人确认关闭（ST-27）与审计/通知 | `test_sprint9_backlog.py::test_complaint_confirm_closes_and_audits` 等 | AC-09-05、ST-27 |
| 黑名单直接加入（ST-20）与延期（ST-21） | `test_sprint9_backlog.py::test_blacklist_direct_add_and_extend` 等 | AC-10、ST-20/21 |
| sysadmin 黑名单加入/延期与投诉驳回 | `test_sprint9_backlog.py::test_sysadmin_can_add_and_extend_blacklist`、`test_complaint_reject_requires_reason_and_allows_sysadmin` | 权限矩阵第 20/21 行 |
| 代创建复用学生校验（时长/黑名单） | `test_sprint9_backlog.py::test_admin_proxy_reuses_student_validation` | AC-03-02/04 |

## v0.10 S10 补充测试（不新增 AC）

| 覆盖点 | 测试 | 关联 |
|---|---|---|
| 学生改本人联系方式；学号不可改 | `test_sprint10_governance.py::test_student_updates_own_contact_and_audits`、`test_contact_endpoint_rejects_immutable_fields` | FR-08、权限矩阵第 2 行 |
| 系统管理员查询用户；联系方式脱敏 | `test_sprint10_governance.py::test_sysadmin_queries_users_with_masked_contact` | FR-08、权限矩阵第 26 行 |
| 管理员/学生查询用户 403 | `test_sprint10_governance.py::test_user_query_forbidden_for_admin_and_student` | 权限矩阵第 26 行 |
| 授权授予后可见、撤权后 403、跨室 403 | `test_sprint10_governance.py::test_grant_revoke_controls_resource_visibility` 等 | BR-21、权限矩阵第 15/17 行 |
| 投诉范围随授权变化 | `test_sprint10_governance.py::test_complaint_scope_follows_room_assignment` | BR-21、FR-09 |
| 阈值减 1 提醒一次、入黑不重复 | `test_sprint10_governance.py::test_near_blacklist_reminder_sent_once_then_blacklist` | FR-12、AC-12 |
| CSV 导出四类角色与无个人信息 | `test_sprint10_governance.py::test_admin_exports_csv_without_personal_info` 等 | FR-11、AC-11 |
| 导出按房间范围过滤 | `test_sprint10_governance.py::test_export_room_filter_and_scope` | FR-11、权限矩阵第 23 行 |

## S11 补充测试（AC-04-07/08，v1.0 沿用）

| 覆盖点 | 测试 | 关联 |
|---|---|---|
| 跨室修改成功、单号不变、两室状态、审计/通知 | `test_sprint11_modify.py::test_ac_04_07_cross_room_modify_success` | AC-04-07 |
| 同室修改成功 | `test_sprint11_modify.py::test_ac_04_07_same_room_modify_success` | AC-04-07 |
| 目标冲突、关闭自习室、停用座位、超次、已开始、非法时长/提前天数 | `test_sprint11_modify.py::test_ac_04_08_*` | AC-04-08 |
| 他人修改 403、状态不允许 | `test_sprint11_modify.py::test_ac_04_08_other_student_and_bad_status_rejected` | AC-04-08、NFR-07 |
| 并发修改与新建抢同一座位仅 1 条成功 | `test_sprint11_modify.py::test_concurrent_modify_and_create_only_one_succeeds` | AC-04-07、NFR-05 |
| 修改页面可打开 | `test_sprint11_modify.py::test_modify_page_renders` | AC-04-07 |
