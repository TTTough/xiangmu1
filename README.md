# 智慧自习室预约与管理系统

《软件工程》课程项目。系统面向高校自习室，提供座位查询、预约与修改、签到签退、违约与申诉、黑名单、投诉评价、数据分析、通知与规则参数配置。

**最终版：v1.0　端口：5012　AC：70 / 70　测试：128 passed**

## 小组

| 成员 | 角色 |
|---|---|
| 应雨挺 | 组长 / 基线维护人 |
| 方与皓 | 模块负责人 |
| 周俊楠 | 交叉审查人 |
| 杨子涵 | 业务确认人 |

## 从 GitHub 获取并运行

1. 获取代码：`git clone https://github.com/TTTough/xiangmu1.git`，或在 GitHub 页面点 **Code → Download ZIP** 后解压。
2. 把项目解压到本地任意目录（路径含中文也可以）。
3. 双击根目录的 `启动系统.bat`。
4. 前置条件：**Windows**（10/11）+ **Python 3.13**，安装 Python 时勾选 *Add Python to PATH*。
5. 首次运行会自动执行 `pip install -r requirements.txt`，并在 `src/data/app.db` 生成演示数据库（已有数据不会被覆盖）。
6. 浏览器自动打开 `http://127.0.0.1:5012/`；停止服务按 **Ctrl+C** 或直接关闭命令行窗口。
7. GitHub 网页预览、Codespaces、Linux 与 macOS **不能**直接运行这个 `.bat`；这些环境请按下方“快速启动”手动执行命令。

双击启动失败（Python 未加 PATH、端口 5012 被占用、依赖安装失败、想重置演示数据）时，见 [docs/guides/launcher.md](docs/guides/launcher.md)。

## 快速启动

Windows 用户可直接双击仓库根目录的 `启动系统.bat`，脚本会自动进入 `src`、安装依赖、打开浏览器并启动 5012。

```powershell
cd src
python -m pip install -r requirements.txt
python -m pytest -q      # 128 passed
python app.py            # http://127.0.0.1:5012
```

## 测试账号

| 角色 | 账号 | 密码 | 入口 |
|---|---|---|---|
| 学生 R-01 | 246003384 | student123 | `/student` |
| 自习室管理员 R-02 | 900000001 | admin123 | `/admin` |
| 系统管理员 R-03 | 900000002 | sysadmin123 | `/sysadmin` |
| 后勤 R-04 | 900000003 | logistics123 | `/analytics` |

## 文档索引

| 文档 | 路径 |
|---|---|
| 当前需求 SRS V1.7 | `docs/requirements/SRS-V1.7.md` / `.docx` / `.pdf` |
| 历史需求 SRS V1.0—V1.6 | `docs/requirements/history/` |
| 材料 A 需求分析质量验证报告 | `docs/reports/材料A-需求分析质量验证报告.md` / `.docx` / `.pdf` |
| 材料 B AI 智能体使用验证报告 | `docs/reports/材料B-AI智能体使用验证报告.md` / `.docx` / `.pdf` |
| 历史材料说明 | `docs/reports/历史材料说明.md` |
| 架构讨论稿 | `docs/architecture/软件架构设计方案_讨论稿.md` |
| 架构基线版 | `docs/architecture/软件架构设计方案_基线版.md` |
| 架构确认与决策记录 | `docs/architecture/架构确认与决策记录.md` |
| 基线索引 | `docs/architecture/基线索引.md` |
| Q/ADR 回填表 | `docs/architecture/Q与ADR决策回填表.md`、`Q与ADR决策回填表_已填版.md` |
| 接口与关键设计 | `docs/design/接口与关键设计说明书.md`、`docs/design/api.md` |
| 分阶段计划 | `docs/plans/分阶段实现与测试计划.md` |
| AC 映射 | `docs/plans/AC-mapping.md` |
| 任务卡 | `docs/tasks/任务卡.md` |
| 验证证据 | `docs/evidence/`（含 `stage-acceptance-S11.md`、`ADR-06-and-Q24-verification.md`） |
| 版本历史 | `docs/evidence/version-history.md` |
| 启动/环境/问题指南 | `docs/guides/` |
| 附件总清单 | `assets/attachments/00-附件清单.md` / `.docx` / `.pdf` |

## 目录结构

```text
.
├─ AGENTS.md                 AI 与项目协作规则
├─ README.md                 本文件
├─ docs/
│  ├─ requirements/          SRS V1.7 与历史版本
│  ├─ reports/               材料 A/B（历史记录）
│  ├─ architecture/          架构、决策、基线索引
│  ├─ design/                接口与关键设计
│  ├─ plans/                 阶段计划与 AC 映射
│  ├─ tasks/                 任务卡
│  ├─ evidence/              测试、验收与验证证据
│  ├─ guides/                启动、环境、问题指南
│  └─ ai-usage-log.md        AI 使用记录
├─ src/                      v1.0 最终版源码（Flask + SQLite）
├─ tests/                    128 条 pytest
├─ scripts/                  图渲染、文档转换与自检脚本
└─ assets/
   ├─ figures/               13 组 39 个图文件
   ├─ prototype/             原型与 29 张走查截图
   └─ attachments/           28 个附件文件
```

## 说明

- 材料 A/B 是 2026-10-29 需求阶段的历史记录，引用 SRS V1.3 与 68 条 AC；当前需求为 SRS V1.7、70 条 AC，未改写历史材料正文。
- 系统使用模拟 SSO，不接入真实统一身份认证；未做压测与恢复演练（助教确认演示验收口径）。
- 仓库不包含数据库文件、缓存、旧版本目录、课程资料 PDF 或旧 zip。

## 系统业务分工与成员工作

主责表示对该模块的需求核实、实现验收和测试证据负责；配合表示提供规则、权限或审查意见。代码由编程智能体辅助生成，最终核查与验收由对应成员承担。

| 模块 | 业务范围 | 主责 | 配合 |
|---|---|---|---|
| M1 认证与权限 | 登录、角色隔离、越权、账号锁定 | 应雨挺 | 杨子涵、周俊楠 |
| M2 资源与授权 | 自习室/区域/座位、停用恢复、管理员授权 | 应雨挺 | 方与皓、周俊楠 |
| M3 预约与修改 | 查询、预约、取消、跨室改期改座 | 方与皓 | 杨子涵、周俊楠 |
| M4 签到与违约 | 签到签退、自动违约、V1/V2/V3 | 方与皓 | 周俊楠、杨子涵 |
| M5 申诉与黑名单 | 申诉复核、计数、黑名单加入/延期/解除 | 方与皓 | 杨子涵、应雨挺 |
| M6 投诉与评价 | 投诉受理/反馈/复核/关闭、评价隐藏 | 方与皓 | 杨子涵、周俊楠 |
| M7 分析与通知 | 图表、10 秒刷新、通知、CSV 导出 | 周俊楠 | 方与皓、杨子涵 |
| M8 参数与审计 | 规则参数、范围校验、审计日志 | 应雨挺 | 方与皓、周俊楠 |
| M9 原型与图表 | 交互原型、PV 截图、13 张图 | 周俊楠 | 方与皓、杨子涵 |
| M10 需求与基线 | SRS、A/B、架构、Q/ADR、计划、Git | 杨子涵（需求）/ 应雨挺（架构、提交） | 全员 |

### 应雨挺（组长 / 基线维护人）
- 主责 M1 认证与权限、M2 资源授权、M8 参数与审计。
- 主持 3 次组内评审，对 26 条审查问题逐条作出“修改／保留／暂缓”决定。
- 审定权限矩阵，处理 R-13 的 sysadmin 权限修复。
- 主持 T-01—T-08 教学模拟确认会，维护 Q/ADR、基线索引、Git 分支、tag v1.0 与 Release。

### 杨子涵（业务确认人 / 需求主笔）
- 主责 M10 需求基线，以及 M1—M8 的业务规则与验收口径。
- 编写 SRS V0.1—V1.7：14 FR、25 BR、5 张状态图、38 个状态转换、13 个数据实体、18 条 NFR、13 个异常场景、70 条 AC。
- 主笔材料 A/B，组织 AI-01—AI-05 交互记录，记录 T-01—T-08 教学模拟确认。
- 将 SRS 从 V1.3 同步到 V1.7，完成 AC 68→70。

### 方与皓（模块负责人）
- 主责 M3 预约与修改、M4 签到与违约、M5 申诉与黑名单、M6 投诉与评价。
- 执行 SC-01/03/05/06/09 与权限 SC-02/07，抽查 PV 截图，处理 V-12/13/14。
- 核对 Q-33/34/35，验收 v0.9 投诉关闭/黑名单/代创建、v0.10 用户/授权/导出、v0.11 跨室修改。
- 检查预约事务、状态重算、权限和审计，参与最终 128 passed 与四角色验收。

### 周俊楠（交叉审查人 / 原型与可视化）
- 主责 M7 分析与通知、M9 原型与图表，并交叉审查 M1—M8。
- 实现 prototype/index.html，产出 29 张 PV 截图和 13 张图的 svg/png。
- 执行 AI-02 的 SRS V1.0 独立审查，处理 V-10/11/15/16。
- 核对权限、状态、文档路径、main/tag/Release 一致性，检查无 db、缓存和旧版本目录。
