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
