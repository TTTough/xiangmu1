# 智慧自习室预约与管理系统

《软件工程》课程项目仓库。系统面向高校自习室，提供座位查询、预约、签到签退、违约与申诉、黑名单、投诉评价、数据分析和规则参数配置。

## 小组

| 成员 | 角色 |
|---|---|
| 应雨挺 | 组长 / 基线维护人 |
| 方与皓 | 模块负责人 |
| 周俊楠 | 交叉审查人 |
| 杨子涵 | 业务确认人 |

## 当前状态

- 当前候选版本：v0.11（最终版 v1.0 定版中）
- 需求基线：SRS V1.7（AC 70/70）
- 测试：128 passed（pytest）
- 技术栈：Python 3.13 + Flask 3 + SQLite + Jinja2

## 快速启动

```powershell
cd src
python -m pip install -r requirements.txt
python app.py
```

默认端口以 `src/config.py` 为准；当前开发版本为 5011。

## 测试账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 学生 | 246003384 | student123 |
| 自习室管理员 | 900000001 | admin123 |
| 系统管理员 | 900000002 | sysadmin123 |
| 后勤部门 | 900000003 | logistics123 |

## 目录结构

```text
.
├─ AGENTS.md                 AI 与本项目协作规则
├─ README.md                 本文件
├─ docs/
│  ├─ requirements/          需求规格说明书（SRS V1.7）
│  ├─ reports/               材料 A / 材料 B（需求阶段历史报告）
│  ├─ architecture/          架构讨论稿、基线版、决策记录、基线索引
│  ├─ design/                接口与关键设计说明书
│  ├─ plans/                 分阶段实现与测试计划
│  ├─ tasks/                 任务卡
│  └─ evidence/              测试、验收、确认与验证证据
├─ src/                      系统源码（Flask 应用）
├─ tests/                    自动化测试
└─ assets/
   ├─ figures/               图模型源文件与导出版
   ├─ prototype/             交互原型与截图
   └─ attachments/           课程提交附件
```

## 文档索引

| 文档 | 位置 |
|---|---|
| 需求规格说明书 | `docs/requirements/` |
| 材料 A / 材料 B | `docs/reports/` |
| 架构设计 | `docs/architecture/` |
| 接口与关键设计 | `docs/design/` |
| 阶段计划与测试 | `docs/plans/` |
| 任务卡 | `docs/tasks/` |
| 验证证据 | `docs/evidence/` |

## 说明

- 材料 A/B 是 2026-10-29 需求阶段的历史记录，引用 SRS V1.3 与 68 条 AC；当前需求与系统以 SRS V1.7 和 `src/` 为准。
- 系统不接入真实 SSO，未做压力测试与恢复演练（助教已确认演示口径）。
- 不提交数据库文件、缓存、密钥和课程资料原件。
