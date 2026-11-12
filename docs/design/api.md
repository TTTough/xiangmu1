# v1.0 接口说明

基地址：`http://127.0.0.1:5012`。除 `/login` 外，JSON API 均依赖 Flask 会话 Cookie。

> v0.9 新增：管理员代创建预约、投诉驳回/确认关闭、黑名单直接加入/延期；以下权限说明继续适用：按 SRS 权限矩阵，系统管理员可使用资源维护、实时座位、座位历史、投诉/申诉、黑名单、评价隐藏、参数、审计与分析接口；手动违约登记与提前释放仍仅自习室管理员，系统管理员调用返回 403。
浏览器/客户端先 `POST /login`，后续请求携带 Cookie。权限在服务端校验。

## 1. 页面路由

| 方法 | 路径 | 允许角色 | 说明 | 对应需求 / AC |
|---|---|---|---|---|
| GET | `/` | 已登录 | 按角色跳转工作台 | FR-01 |
| GET/POST | `/login` | 公开 | 登录页 / 模拟 SSO | FR-01、AC-01-01、AC-01-02、AC-01-04 |
| POST | `/logout` | 已登录 | 退出并清空会话 | FR-01 |
| GET | `/student` | 学生 | 学生工作台；不呈现管理入口 | AC-01-01 |
| GET | `/seats` | 已登录 | 座位查询与预约页面 | FR-06、AC-06-01 |
| GET | `/reservations` | 学生 | 本人预约列表与取消入口 | FR-04、AC-04-01、AC-04-02 |
| GET | `/reservations/{id}/modify` | 学生 | 修改待生效预约表单 | FR-04、AC-04-07 |
| GET | `/usage` | 学生 | 签到 / 签退 | FR-04、AC-04-03—06 |
| GET | `/violations` | 学生 | 本人违约记录与申诉入口 | FR-05、AC-05-03、AC-05-04 |
| GET | `/credit` | 学生 | 信用状态、剩余解除时间与解除条件 | FR-10、AC-10-05 |
| GET | `/admin` | 自习室管理员 | 管理工作台和管理入口 | AC-01-02 |
| GET | `/admin/appeals` | 自习室管理员 | 申诉复核页 | AC-05-03、AC-05-07 |
| GET | `/admin/blacklists` | 自习室管理员 | 黑名单管理页 | AC-10-04 |
| GET | `/admin/maintenance` | 自习室管理员 | 手动触发维护扫描 | AC-05-01、AC-05-02、AC-10-03 |
| GET | `/admin/resources` | 自习室管理员 | 授权范围内资源维护 | FR-02、AC-02-01—04 |
| GET | `/admin/proxy-reservation` | 自习室管理员 | 管理员代创建预约 | FR-03、BR-22 |
| GET | `/admin/realtime` | 自习室管理员 | 实时座位视图与 V3 登记 | FR-07、AC-07-01—04 |
| GET | `/admin/seats/{id}/history` | 自习室管理员 | 座位历史记录 | AC-07-05 |
| GET | `/records` | 已登录 | 预约记录查询；按角色隔离并分页 | FR-06、AC-06-02—04 |
| GET | `/sysadmin` | 系统管理员 | 系统管理工作台 | FR-14 |
| GET | `/sysadmin/audit` | 系统管理员 | 审计日志查询、筛选与分页 | AC-14-01—04 |
| GET | `/sysadmin/params` | 系统管理员 | 规则参数配置 | FR-13、AC-13-01—04 |
| GET | `/sysadmin/users` | 系统管理员 | 用户查询 | FR-08、V1.6 |
| GET | `/sysadmin/assignments` | 系统管理员 | 管理员授权维护 | BR-21、V1.6 |
| GET | `/evaluations` | 学生 | 已完成预约评价入口 | FR-08、AC-08-01—04 |
| GET | `/complaints` | 学生 | 投诉提交、进度与复核对账 | FR-09、AC-09-01—06 |
| GET | `/admin/evaluations` | 自习室管理员 | 授权范围评价与隐藏 | AC-08-03 |
| GET | `/admin/complaints` | 自习室管理员 | 投诉受理与反馈 | AC-09-03 |
| GET | `/analytics` | 管理员/系统管理员/后勤 | 数据分析看板 | FR-11、AC-11-01—06 |
| GET | `/notifications` | 学生/自习室管理员 | 通知中心 | FR-12、AC-12-01—03 |

## 2. JSON API

| 方法 | 路径 | 允许角色 | 说明 | 对应 AC |
|---|---|---|---|---|
| POST | `/login` | 公开 | JSON 登录；使用 JSON 请求体时返回 JSON | AC-01-01、AC-01-02、AC-01-04 |
| GET | `/api/me` | 已登录 | 当前用户、角色和账号状态 | FR-01 |
| GET | `/api/seats` | 已登录 | 多条件查询座位并标注可用性 | AC-06-01 |
| POST | `/api/reservations` | 学生 | 创建预约，事务内校验并写入 | AC-03-01—AC-03-05 |
| POST | `/api/admin/reservations` | 自习室管理员 | 管理员代创建预约（指定学生、原因必填） | FR-03、BR-22 |
| GET | `/api/reservations` | 已登录 | 分页查询预约记录，按角色数据隔离 | AC-06-02—04 |
| GET | `/api/reservations/my` | 学生 | 查询本人预约 | FR-06、NFR-07 |
| PUT | `/api/reservations/{id}` | 学生 | 修改待生效预约（跨自习室、最多一次） | AC-04-07、AC-04-08 |
| POST | `/api/reservations/{id}/cancel` | 学生 | 开始前取消预约 | AC-04-01、AC-04-02 |
| POST | `/api/reservations/{id}/checkin` | 学生 | 窗口内签到 | AC-04-03、AC-04-04、AC-04-06 |
| POST | `/api/reservations/{id}/checkout` | 学生 | 签退并记录实际时长 | AC-04-05 |
| POST | `/api/violations/{id}/appeal` | 学生 | 在申诉期内发起申诉 | AC-05-03、AC-05-04 |
| GET | `/api/credit` | 学生 | 本人信用状态 | AC-10-05 |
| POST | `/api/admin/violations/{id}/appeal` | 自习室管理员 | 判定申诉成立 / 不成立 | AC-05-03、AC-05-07 |
| POST | `/api/admin/blacklists/{id}/release` | 自习室管理员 | 提前解除黑名单（原因必填） | AC-10-04 |
| POST | `/api/admin/blacklists` | 管理员、系统管理员 | 直接加入黑名单（原因/期限必填） | AC-10、ST-20 |
| POST | `/api/admin/blacklists/{id}/extend` | 管理员、系统管理员 | 延长黑名单期限（原因/期限必填） | AC-10、ST-21 |
| POST | `/api/admin/scan` | 自习室管理员 | 手动触发维护扫描 | AC-05-01、AC-05-02、AC-10-03 |
| GET | `/api/admin/resources` | 自习室管理员 | 授权范围内的三级资源结构 | FR-02、AC-02-01 |
| POST | `/api/admin/rooms` | 自习室管理员 | 新增自习室并授权本人 | FR-02 |
| POST | `/api/admin/rooms/{id}/zones` | 自习室管理员 | 新增区域（校验自习室授权） | AC-02-01、AC-02-03 |
| POST | `/api/admin/zones/{id}/seats` | 自习室管理员 | 新增座位（校验区域所属自习室授权） | AC-02-01 |
| POST | `/api/admin/seats/{id}/disable` | 自习室管理员 | 停用座位并自动取消未来预约 | AC-02-04 |
| POST | `/api/admin/seats/{id}/restore` | 自习室管理员 | 恢复停用座位 | ST-09、BR-22 |
| POST | `/api/admin/seats/{id}/status` | 已登录（显式拒绝） | 直接改写座位状态一律 403 | AC-02-02、BR-02 |
| GET | `/api/admin/realtime` | 自习室管理员 | 实时座位矩阵、脱敏使用者与预约时段 | AC-07-01 |
| POST | `/api/admin/seats/{id}/manual-violation` | 自习室管理员 | 现场 V3 违约登记 | AC-07-02、AC-07-03、AC-07-04 |
| POST | `/api/admin/reservations/{id}/release` | 自习室管理员 | 提前释放座位/取消预约（原因必填） | AC-07-06 |
| GET | `/api/admin/seats/{id}/history` | 自习室管理员 | 座位历史（使用者脱敏） | AC-07-05 |
| POST | `/api/admin/manual-violation` | 自习室管理员 | 兼容旧路径；返回 410 指向座位级接口 | — |
| GET | `/api/system/audit-logs` | 系统管理员 | 审计日志筛选与分页 | AC-14-01—04 |
| GET | `/api/system/rule-params` | 系统管理员 | 参数当前值、范围、来源与状态 | AC-13-01—03 |
| GET | `/api/system/users` | 系统管理员 | 查询用户（联系方式脱敏） | FR-08、V1.6 |
| GET | `/api/system/admin-room-assignments` | 系统管理员 | 授权列表 | BR-21、V1.6 |
| POST | `/api/system/admin-room-assignments` | 系统管理员 | 授予授权 | BR-21、V1.6 |
| POST | `/api/system/admin-room-assignments/revoke` | 系统管理员 | 撤销授权 | BR-21、V1.6 |
| PUT | `/api/system/rule-params/{key}` | 系统管理员 | 参数更新、范围校验与变更审计 | AC-13-01—04 |
| PUT/PATCH/DELETE | `/api/system/audit-logs/{id}` | 已登录（显式拒绝） | 审计日志不可修改/删除，返回 403 | AC-14-03 |
| POST | `/api/evaluations` | 学生 | 提交评价（真实使用+去重） | AC-08-01、AC-08-02 |
| GET | `/api/evaluations/summary` | 已登录 | 评价平均分与条数（排除隐藏） | AC-08-04 |
| POST | `/api/admin/evaluations/{id}/hide` | 自习室管理员 | 填写理由隐藏评价 | AC-08-03 |
| POST | `/api/complaints` | 学生 | 提交投诉 | AC-09-01、AC-09-02 |
| GET | `/api/complaints/{id}` | 学生本人/管理员 | 投诉详情与脱敏信息 | AC-09-06 |
| POST | `/api/complaints/{id}/review` | 学生 | 申请复核一次 | AC-09-04 |
| POST | `/api/complaints/{id}/confirm` | 学生 | 确认反馈并关闭 | AC-09-05、ST-27 |
| POST | `/api/admin/complaints/{id}/accept` | 自习室管理员 | 受理投诉 | AC-09-03 |
| POST | `/api/admin/complaints/{id}/feedback` | 自习室管理员 | 提交反馈 | AC-09-03 |
| POST | `/api/admin/complaints/{id}/reject` | 管理员、系统管理员 | 驳回并关闭投诉（原因必填） | AC-09-03、ST-25 |
| GET | `/api/analytics` | 管理员/系统管理员/后勤 | 图表与统计数值 | AC-11-01—06 |
| GET | `/api/analytics/export` | 管理员/系统管理员/后勤 | 导出统计 CSV | FR-11、V1.6 |
| GET | `/api/notifications` | 学生/自习室管理员 | 本人通知分类与分页 | AC-12-01—03 |
| POST | `/api/notifications/{id}/read` | 学生/自习室管理员 | 标记本人通知已读 | AC-12-02 |
| PUT | `/api/me/contact` | 已登录 | 修改本人联系方式 | FR-08、V1.6 |
| DELETE | `/api/notifications/{id}` | 已登录（显式拒绝） | 通知不可删除，返回 403 | AC-12-02 |

### 2.1 登录

请求：

```http
POST /login
Content-Type: application/json

{"student_no":"246003384","password":"student123"}
```

成功（200）：

```json
{
  "message": "登录成功",
  "user": {
    "id": 1,
    "student_no": "246003384",
    "name": "杨子涵",
    "role": "student",
    "role_label": "学生（R-01）",
    "account_status": "正常"
  },
  "redirect": "/student"
}
```

锁定（423）：

```json
{
  "error": {
    "code": "ACCOUNT_LOCKED",
    "message": "账号处于锁定期间，拒绝登录；剩余解锁时间约 15 分钟"
  },
  "remaining_minutes": 15,
  "locked_until": "2026-10-16 08:45:00"
}
```

其他错误码：`INVALID_CREDENTIALS`（401）、`MISSING_FIELD`（400）。
连续失败阈值、锁定时长从 `rule_params` 的 P-20、P-21 读取。

### 2.2 座位查询

```http
GET /api/seats?building=图书馆&zone_type=静音区&date=2026-10-17&start=09:00&end=11:00&seat_type=带电源
Cookie: session=...
```

查询参数：

| 参数 | 必填 | 说明 |
|---|---|---|
| `building` | 否 | 楼栋，精确匹配 |
| `room_id` | 否 | 自习室 ID |
| `zone_id` | 否 | 区域 ID |
| `zone_type` | 否 | 区域类型，如“静音区”“讨论区”“电源区” |
| `seat_type` | 否 | 普通 / 带电源 / 靠窗 / 隔断 |
| `date` | 否 | `YYYY-MM-DD`；提供后计算当日空档 |
| `start`、`end` | 否 | `HH:MM`，必须同时提供且依赖 `date` |
| `only_available` | 否 | `1` 时只返回符合条件且可约的座位 |

响应示例（节选）：

```json
{
  "count": 1,
  "seats": [
    {
      "id": 1,
      "code": "A-01",
      "seat_type": "带电源",
      "current_status": "空闲",
      "is_bookable": true,
      "room": {"name": "图书馆三层自习室", "building": "图书馆", "open_from": "08:00", "open_to": "22:00", "status": "开放"},
      "zone": {"name": "静音区", "type": "静音区"},
      "available_for_slot": true,
      "available_slots": [{"start": "08:00", "end": "22:00"}]
    }
  ],
  "note": "current_status 是座位当前展示状态；available_for_slot 是所查日期/时段是否可预约；available_slots 是所查日期内的连续空档。"
}
```

`current_status` 取当前座位展示状态；跨日期、非所查时段是否可约请以 `available_for_slot` 为准（相关展示口径见 `open-questions.md`）。

### 2.3 创建预约

```http
POST /api/reservations
Content-Type: application/json
Cookie: session=...

{
  "seat_id": 1,
  "reservation_date": "2026-10-17",
  "start_time": "09:00",
  "end_time": "11:00"
}
```

成功（201）：

```json
{
  "message": "预约成功",
  "reservation": {
    "id": 1,
    "reservation_no": "RS20261017-4F2A1B",
    "seat_id": 1,
    "seat_code": "A-01",
    "reservation_date": "2026-10-17",
    "start_time": "09:00",
    "end_time": "11:00",
    "status": "待生效",
    "source": "学生自助",
    "seat_status": "已预约",
    "notification": {"type": "预约成功", "delivery_result": "系统内消息已送达"}
  }
}
```

规则拒绝（409）：

| 错误码 | 含义 | 对应规则 |
|---|---|---|
| `BLACKLISTED` | 黑名单期间禁止新预约 | BR-13、AC-03-02 |
| `ACTIVE_RESERVATION_LIMIT` | 达到同时有效预约上限 | BR-04、AC-03-03 |
| `DURATION_OUT_OF_RANGE` | 时长不在 [30, 240] 分钟 | BR-05、AC-03-04 |
| `ADVANCE_LIMIT` | 超过提前 7 天 | BR-06、AC-03-04 |
| `OUTSIDE_OPEN_HOURS` | 时段超出开放时间 | BR-03 |
| `SEAT_DISABLED` | 座位停用 | BR-23、ST-10 |
| `SEAT_TIME_CONFLICT` | 同时段已被占用（含并发） | AC-03-05、NFR-05 |

其他：`START_IN_PAST`（409）、`INVALID_TIME_RANGE`（400）、`SEAT_NOT_FOUND`（404）、`FORBIDDEN`（403，非学生角色）。失败请求不创建预约单、不改变座位状态，但会写入一条拒绝审计。

### 2.4 取消预约

```http
POST /api/reservations/1/cancel
Cookie: session=...
```

成功（200）：

```json
{
  "message": "取消成功",
  "reservation": {
    "id": 1,
    "reservation_no": "RS20261017-4F2A1B",
    "status": "已取消",
    "seat_code": "A-01",
    "seat_status": "空闲",
    "cancelled_at": "2026-10-16 08:31:00",
    "violation_created": false
  }
}
```

开始后取消（409）：`CANCEL_WINDOW_CLOSED`，预约与座位状态保持（AC-04-02）。
非本人预约：403 `FORBIDDEN`；不存在：404；状态不可取消：409 `NOT_CANCELLABLE`。

### 2.5 签到

```http
POST /api/reservations/1/checkin
Content-Type: application/json

{"seat_code":"A-01","method":"二维码"}
```

成功（200）：

```json
{
  "message": "签到成功",
  "checkin": {
    "reservation_id": 1,
    "reservation_no": "RS20261017-4F2A1B",
    "reservation_status": "使用中",
    "seat_code": "A-01",
    "seat_status": "使用中",
    "checkin_at": "2026-10-16 08:30:00",
    "method": "二维码",
    "window": {"start": "08:15", "end": "08:45"}
  }
}
```

错误码：`CHECKIN_WINDOW_NOT_STARTED`（409，早于签到窗口）、`CHECKIN_WINDOW_CLOSED`（409，超过签到截止）、`SEAT_MISMATCH`（409，座位号不一致）、`NOT_CHECKINABLE`（409，状态不是待签到）、`INVALID_CHECKIN_METHOD`（400）。失败时状态与签到记录不变。对应 AC-04-03、AC-04-04、AC-04-06。

### 2.6 签退

```http
POST /api/reservations/1/checkout
Cookie: session=...
```

成功（200）返回预约单变为「已完成」、座位释放、`checkout_at` 与 `actual_minutes`。对应 AC-04-05。
错误：`NOT_USING`、`CHECKIN_MISSING`、`CHECKOUT_AFTER_END`（409）。

### 2.7 维护扫描

```http
POST /api/admin/scan
Cookie: session=...
```

仅管理员。返回：

```json
{
  "message": "扫描完成",
  "scan": {
    "promoted_to_checkin": 0,
    "v1_created": 1,
    "v2_created": 0,
    "blacklists_expired": 0
  },
  "at": "2026-10-16 08:30:00"
}
```

扫描在单一事务内执行：黑名单到期恢复、待生效→待签到、V1/V2 自动违约、达到阈值时的黑名单生效。同一预约单同一违约类型由数据库唯一索引兜底，不重复生成。对应 AC-05-01、AC-05-02、AC-05-06、AC-10-01、AC-10-03。后台定时线程调用同一服务。

### 2.8 学生申诉

```http
POST /api/violations/1/appeal
Content-Type: application/json

{"reason":"签到设备故障，已按时到场"}
```

成功（200）：记录状态变为「申诉中」；仅本人、状态「生效中」且距生成时间不超过 P-09 的 3 个自然日可提交。
错误：`NOT_APPEALABLE`（409）、`APPEAL_WINDOW_CLOSED`（409）、`FORBIDDEN`（403）。对应 AC-05-03、AC-05-04。

### 2.9 管理员申诉复核

```http
POST /api/admin/violations/1/appeal
Content-Type: application/json

{"decision":"成立","conclusion":"核实签到设备故障，申诉成立"}
```

`decision` 接受「成立」「不成立」（也兼容 `approve` / `reject`），`conclusion` 必填。

- 成立：记录→「申诉成立已撤销」，有效违约计数回退；若低于阈值，生效中黑名单可自动解除。
- 不成立：记录→「申诉不成立已终结」，计数保持。

对应 AC-05-03、AC-05-07；管理员、结论与前后状态写入审计日志。

### 2.10 信用状态

```http
GET /api/credit
Cookie: session=...
```

返回：

```json
{
  "credit": {
    "account_status": "黑名单",
    "is_blacklisted": true,
    "effective_violation_count": 3,
    "blacklist_threshold": 3,
    "blacklist_until": "2026-10-20 08:30:00",
    "remaining_minutes": 5760,
    "release_conditions": ["黑名单期限届满后由系统自动解除", "..."],
    "active_blacklist_record": {"id": 1, "reason": "有效违约累计达到 3 次"}
  }
}
```

对应 AC-10-05。黑名单期间预约接口返回 409 `BLACKLISTED`（AC-10-02）。

### 2.11 管理员提前解除黑名单

```http
POST /api/admin/blacklists/1/release
Content-Type: application/json

{"reason":"学生提交设备故障证明，经核实提前解除"}
```

原因必填；成功（200）后记录变为「已解除」，账号恢复「正常」，通知学生并写审计日志（AC-10-04）。
未填原因：400 `MISSING_FIELD`；记录非生效中：409 `BLACKLIST_NOT_ACTIVE`。

### 2.12 资源维护

所有资源接口仅限自习室管理员，并按 `admin_room_assignments` 校验授权范围。

```http
POST /api/admin/rooms
{"code":"R-LIB-4F","name":"图书馆四层自习室","building":"图书馆","floor":"4 层","open_from":"08:00","open_to":"22:00","status":"开放"}
```

新增区域：

```http
POST /api/admin/rooms/1/zones
{"code":"Z9","name":"考试专区","zone_type":"静音区","sort_order":9}
```

新增座位：

```http
POST /api/admin/zones/1/seats
{"code":"D-01","seat_type":"靠窗","position":"第 1 排"}
```

成功分别返回 201。未授权自习室返回 403 `ROOM_FORBIDDEN`；编号重复返回 409。新增座位的初始状态固定为「空闲」，不接受状态字段。

停用 / 恢复座位：

```http
POST /api/admin/seats/1/disable
{"reason":"座椅损坏，维修停用"}

POST /api/admin/seats/1/restore
{"reason":"维修完成，恢复开放"}
```

停用会取消该座位开始时刻在未来的待生效/待签到预约并通知学生，不生成违约；恢复后重新可预约。原因必填。对应 AC-02-01—04。

直接改写座位状态：

```http
POST /api/admin/seats/1/status
{"status":"停用"}
```

任何已登录角色均返回 403 `DIRECT_STATUS_WRITE_FORBIDDEN`，座位状态不变（AC-02-02、BR-02）。

### 2.13 实时座位视图

```http
GET /api/admin/realtime?room_id=1
Cookie: session=...
```

响应包含授权自习室列表、选中自习室的区域与座位。每个座位含 `status`、`current_occupant`（仅使用中，姓名/学号脱敏）、`reservation`（预约单号、时段、状态、脱敏姓名）。未授权自习室返回 403。对应 AC-07-01。

### 2.14 V3 管理员手动违约

```http
POST /api/admin/seats/1/manual-violation
{"reason":"现场长时间占座且拒绝出示预约信息","student_no":"246003384"}
```

- 有有效预约时从预约取得学生，`student_no` 可省略；无有效预约时必须提供被登记学生学号。
- 原因必填（AC-07-02）；生成 `V3 管理员手动登记` 记录，座位释放，预约置「已违约」，学生收到通知，操作与前后状态写入审计（AC-07-03）。
- 目标座位不属于管理员授权自习室时返回 403 `ROOM_FORBIDDEN`，无数据变更（AC-07-04）。
- 同一预约单已有 V3 时返回 409 `DUPLICATE_VIOLATION`。

### 2.15 管理员提前释放预约

```http
POST /api/admin/reservations/1/release
{"reason":"现场需要临时改为考场"}
```

原因必填；成功（200）预约变「已取消」、座位释放、学生收到通知、写审计（AC-07-06）。未填原因返回 400；非有效预约返回 409。

### 2.16 座位历史

```http
GET /api/admin/seats/1/history
```

返回该座位的历次预约：日期/时段、预约状态、脱敏姓名/学号、签到方式与时间、签退时间与实际使用分钟数、关联违约记录。对应 AC-07-05。未授权自习室的座位返回 403。

### 2.17 管理权限占位接口

`POST /api/admin/manual-violation` 保留为兼容旧路径，返回 410 `USE_SEAT_ENDPOINT`；请使用座位级 V3 接口。

### 2.18 预约记录查询

```http
GET /api/reservations?date_from=2026-11-01&date_to=2026-11-30&status=待生效&room_id=1&page=2&page_size=5
Cookie: session=...
```

- 学生：仅本人记录（AC-06-02）。
- 自习室管理员：仅 `admin_room_assignments` 授权自习室记录（AC-06-03）。
- 系统管理员/后勤：全量只读。
- 筛选参数：`date_from`、`date_to`（YYYY-MM-DD）、`status`、`room_id`、`page`、`page_size`（1—100）。
- 响应含 `items`、`pagination`（page、page_size、total、total_pages、has_prev、has_next）和 `filters`；翻页请求携带同样参数即可保持筛选（AC-06-04）。
- 姓名与学号脱敏返回。

页面 `/records` 使用相同参数，上一页/下一页链接保留筛选条件。

### 2.19 审计日志查询

```http
GET /api/system/audit-logs?actor=自习室管理员&action=手动违约登记&target=违约记录&date_from=2026-10-01&date_to=2026-10-31&page=1&page_size=20
Cookie: session=...
```

仅系统管理员可访问，其他角色 403。`actor` 为姓名模糊匹配，`action` 为精确操作类型，`target` 匹配目标类型或目标编号；日期按自然日闭区间。响应：

```json
{
  "logs": [
    {
      "id": 1,
      "actor_name": "自习室管理员",
      "actor_role": "自习室管理员（R-02）",
      "action": "手动违约登记",
      "target_type": "违约记录",
      "target_id": "V3...",
      "before": {"seat_status": "已预约"},
      "after": {"seat_status": "空闲"},
      "before_text": "...",
      "after_text": "...",
      "result": "成功",
      "created_at": "2026-10-16 08:30:00"
    }
  ],
  "pagination": {"page": 1, "page_size": 20, "total": 1, "total_pages": 1, "has_prev": false, "has_next": false},
  "filters": {}
}
```

对应 AC-14-01（管理操作均留痕且字段完整）、AC-14-02（展示变更前后值）、AC-14-04（筛选与分页）。

### 2.20 规则参数配置

```http
GET /api/system/rule-params
```

仅系统管理员。返回全部 28 项参数的当前值、默认值、`min_value`/`max_value`、范围文本、单位、来源性质、确认状态与更新时间（AC-13-01—03）。

更新：

```http
PUT /api/system/rule-params/data_refresh_seconds
{"value": 15}
```

- 仅系统管理员；输入按 `value_type` 校验整数/浮点等类型，并检查 `min_value`—`max_value` 范围。
- 超出范围返回 400 `PARAM_OUT_OF_RANGE`，参数保持原值（AC-13-02）。
- 保存后即时生效，此后签到、扫描等判定读取新值（AC-13-01）。
- 每次成功变更写入审计，记录变更人、时间、参数键、变更前后值，并写入审计日志（AC-13-03、AC-14-02）。
- 参数变更不回溯修改已生成业务记录（AC-13-04）。
- SRS 附录 A 未统一给出数值范围，`min_value`/`max_value` 是当前可校验实现默认范围（见 open-questions OQ-33）。

### 2.21 审计不可修改/删除

```http
PUT /api/system/audit-logs/1
PATCH /api/system/audit-logs/1
DELETE /api/system/audit-logs/1
```

任何已登录角色均返回 403 `AUDIT_LOG_IMMUTABLE`，日志保持不变。数据库另有 `trg_audit_logs_no_update` 与 `trg_audit_logs_no_delete` 触发器兜底（AC-14-03、BR-24）。

### 2.22 评价

提交：

```http
POST /api/evaluations
Content-Type: application/json

{"target_type":"座位","target_id":1,"rating":5,"comment":"环境安静，电源可用"}
```

- 仅学生可提交；`target_type` 为「座位」或「自习室」，`rating` 为 1—5 整数。
- 必须存在该学生对该对象的已完成预约，否则 409 `REAL_USE_REQUIRED`（AC-08-01）。
- 同一学生对同一对象仅一条；重复提交返回 409 `ALREADY_EVALUATED`，原评价不变（AC-08-02）。
- 成功返回 201 与最新聚合。

摘要：

```http
GET /api/evaluations/summary?target_type=座位&target_id=1
```

返回 `average_rating` 与 `evaluation_count`，仅统计 `hidden=0` 的评价（AC-08-04）。

隐藏：

```http
POST /api/admin/evaluations/1/hide
{"reason":"包含不文明用语"}
```

仅管理员且目标在本人授权范围；理由必填。隐藏后不计入平均分/条数，写审计（AC-08-03）。

### 2.23 投诉

提交：

```http
POST /api/complaints
Content-Type: application/json

{
  "object_type":"其他用户",
  "complained_student_no":"246003385",
  "complaint_type":"占座纠纷",
  "object_ref":"A-01",
  "content":"对方长时间放置物品但未使用座位。",
  "evidence_attachment":"现场照片.jpg"
}
```

- 仅登录学生可提交；`object_type` 为「座位或自习室」「其他用户」「管理员」。
- 「其他用户」必须提供被投诉学生学号；被投诉人姓名、学号、联系方式在投诉详情中脱敏（AC-09-06）。
- 成功创建状态「待受理」投诉单，并通知所有自习室管理员（AC-09-01）。未登录请求返回 401 且不创建记录（AC-09-02）。

管理员受理：

```http
POST /api/admin/complaints/1/accept
```

待受理→处理中，记录受理人与时间，通知投诉人。

管理员反馈：

```http
POST /api/admin/complaints/1/feedback
{"feedback":"已核实并提醒对方遵守座位使用规则。"}
```

处理中→已回复，反馈对学生可见，通知投诉人（AC-09-03）。

学生复核：

```http
POST /api/complaints/1/review
```

已回复→处理中，`review_used=1`；再次申请返回 409，仅允许一次（AC-09-04）。

查看详情：

```http
GET /api/complaints/1
```

仅投诉本人或管理员；返回状态、反馈、关闭原因与脱敏被投诉人信息（AC-09-06）。

超时关闭由维护扫描执行，扫描结果新增 `complaints_auto_closed` 计数；时限取 `rule_params.complaint_auto_close_days`（P-13，AC-09-05）。

### 2.24 数据分析

```http
GET /api/analytics?date_from=2026-10-10&date_to=2026-10-16&room_id=1
Cookie: session=...
```

允许自习室管理员（仅授权范围）、系统管理员、后勤部门。学生返回 403。响应含：

- `charts.bar_reservations_by_room`：柱状图数据；
- `charts.bar_violations_by_room`：违约柱状图数据；
- `charts.line_daily`：逐日预约量与违约量折线数据；
- `charts.refresh_seconds`：P-14 刷新间隔（10 秒）；
- `stats.current_free_seats`、`today_violations` 等统计数值；
- `filters`、`rooms`、`refreshed_at`。

`/analytics` 页面每 10 秒调用该接口局部更新，筛选条件、滚动位置和 `<details>` 展开状态保持不变（AC-11-01、AC-11-03、AC-11-06）。后勤账号为只读（AC-11-05）。

### 2.25 通知中心

```http
GET /api/notifications?category=预约提醒&read_status=unread&page=1&page_size=20
Cookie: session=...
```

仅学生/自习室管理员，且只能查询本人通知。响应 `notifications` 项包含：分类、标题、内容、`created_at`、`read_at`、`is_read`、`delivery_result`、`event_key`；另含 `categories` 与分页信息。

标记已读：

```http
POST /api/notifications/1/read
```

仅本人通知，写入 `read_at`。

删除通知：

```http
DELETE /api/notifications/1
```

返回 403 `NOTIFICATION_IMMUTABLE`；数据库触发器 `trg_notifications_no_delete` 兜底（AC-12-02）。

通知事件覆盖预约成功、预约即将开始、签到即将截止、违约、黑名单、申诉、投诉反馈、投诉自动关闭等；提醒由维护扫描按 `event_key` 去重，只发送一次（AC-12-01）。

## 3. 通用错误格式

```json
{"error": {"code": "ERROR_CODE", "message": "可理解的中文说明"}}
```

| HTTP 状态 | 典型含义 |
|---|---|
| 400 | 参数缺失或格式错误 |
| 401 | 未登录、会话失效、凭证错误 |
| 403 | 服务端角色/归属校验拒绝 |
| 404 | 资源不存在 |
| 409 | 业务规则冲突，状态不变 |
| 410 | 旧接口路径已迁移 |
| 423 | 账号锁定 |
| 501 | 本 Sprint 未实现的管理端点 |

审计字段：`actor_name`、`actor_role`、`action`、`target_type`、`target_id`、`before_json`、`after_json`、`result`、`created_at`，对应 DM-13 / AC-14-01、AC-14-02 的字段基础。
