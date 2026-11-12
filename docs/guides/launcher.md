# Windows 双击启动器说明

仓库根目录的 `启动系统.bat` 是**本机启动器**：它只在运行它的人自己的 Windows 电脑上执行，负责切换到 `src`、检查 Python、安装依赖、启动 Flask 服务并打开浏览器。它不是部署在 GitHub 上的服务，GitHub 网页预览、Codespaces、Linux 与 macOS 都无法直接运行它。

## 1 适用环境与前置条件

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（64 位） |
| Python | 3.13，安装时勾选 **Add Python to PATH** |
| 网络 | 首次运行需要联网安装依赖（Flask、pytest） |
| 磁盘 | 项目目录 + 约 30 MB 依赖 |
| 端口 | 5012（本机回环地址，不对外网开放） |

依赖清单见 `src/requirements.txt`（`Flask>=3.0,<4`、`pytest>=8,<10`）。

## 2 双击运行步骤

1. 用 `git clone https://github.com/TTTough/xiangmu1.git` 获取代码，或在 GitHub 页面点 **Code → Download ZIP** 后解压。
2. 确认解压后的目录里同时存在 `启动系统.bat`、`src\app.py`、`src\requirements.txt`。
3. 双击 `启动系统.bat`。脚本依次执行：
   - 切换到 `src` 目录；
   - 检查 `src\app.py` 是否存在；
   - 检查 `python` 是否在 PATH；
   - `python -m pip install -q -r requirements.txt`；
   - 检查 5012 端口是否空闲；
   - 启动 `python app.py`，2 秒后用浏览器打开 <http://127.0.0.1:5012/>。
4. 首次启动会自动建库（`src/data/app.db`）并写入演示数据：1 个自习室、3 个区域、10 个座位、28 项规则参数与四个测试账号。
5. 停止服务：在命令行窗口按 **Ctrl+C**，或直接关闭窗口。

测试账号见根目录 `README.md` 的“测试账号”表。

## 3 常见故障处理

### 3.1 端口 5012 被占用

脚本会提示「端口 5012 已被占用」。查找并结束占用进程：

```bat
netstat -ano | findstr ":5012"
taskkill /F /PID <上一步最后一列的 PID>
```

也可以先关闭之前没有退出的 Python 窗口；确认没有占用后重新双击 `启动系统.bat`。

### 3.2 提示未找到 Python（Python 未加入 PATH）

1. 安装 Python 3.13 时勾选 **Add Python to PATH**；已装但漏勾，可重新运行安装程序选择 Modify。
2. 在命令行验证：

```bat
python --version
```

3. 若仍提示未找到，可暂时在 PATH 中加入 Python 安装目录（例如 `%LOCALAPPDATA%\Programs\Python\Python313\`），或改用 README 的“快速启动”手动执行命令。

### 3.3 依赖安装失败

- 检查网络与代理；`pip install` 报超时或证书错误时，可换用镜像源：

```bat
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

- 若提示缺少 `pip`：`python -m ensurepip --upgrade` 后重试。
- 依赖装到错误解释器（例如公司环境有多个 Python）时，用 `where python` 确认实际路径，或改用虚拟环境：

```bat
cd src
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

## 4 重置演示数据

演示数据库是本地文件 `src/data/app.db`（连同可能存在的 `app.db-wal`、`app.db-shm`），不随仓库提交。

1. 先停止服务。
2. 删除这三个文件：

```bat
cd src\data
del app.db app.db-wal app.db-shm
```

3. 重新双击 `启动系统.bat`。启动时 `schema.sql` 会重建表结构，`seed.py` 会重新写入默认自习室、座位、规则参数和测试账号。

## 5 说明

- `启动系统.bat` 只做本机启动，不构成对外服务；它绑定 `127.0.0.1:5012`，其他机器无法访问。
- 在非 Windows 环境（Linux、macOS、Codespaces）请手动执行 `cd src && python -m pip install -r requirements.txt && python app.py`。
- 业务代码与测试不受本脚本影响；`cd src && python -m pytest -q` 的基线为 128 passed。
