# 使用指南

本目录存放系统运行与使用相关说明：

- `run.md`：启动、演示账号与演示路径。
- `launcher.md`：Windows 双击启动器（`启动系统.bat`）的环境、步骤与故障处理。
- `environment.md`：运行环境、依赖、端口与故障处理。
- `open-questions.md`：实现期需求缺口与待确认事项（历史记录）。

源码与测试位于仓库根目录的 `src/`、`tests/`；启动命令：

```powershell
cd src
python -m pip install -r requirements.txt
python app.py
```

默认端口 5012，入口 <http://127.0.0.1:5012/>。
