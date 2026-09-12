# AGENTS.md — lat3ncy-tvbox 仓库工作约定

本文件面向在本仓库工作的 AI 代理与协作者，记录**仓库结构、同步机制、清理边界**三类硬约束。
修改本文件前请先确认对应事实仍然成立。

---

## 1. 仓库定位

Ponyo TV 是面向 Android TV 的 TVBox 美化版本。本仓库同时承载：

| 目录 | 内容 | 是否入库 |
|:---|:---|:---|
| `android/` | App 完整 Gradle 源码 | 入库（构建产物除外） |
| `source-manager/` | 自动化源管理系统（Python + Node） | 入库 |
| `subscription/` | 订阅配置与发布产物 | 入库 |
| `docs/` | 设计文档与实施计划 | 入库 |
| `tools/` | 独立辅助脚本 | 部分入库 |
| `releases/` | APK 发行版 | **不入库**（`*.apk` 被忽略） |

---

## 2. 服务器与 GitHub 同步机制

### 2.1 核心约束

服务器生产目录 `/opt/ponyo-source-manager` 的**仓库根目录**，对应 GitHub 仓库的
`source-manager/` **子树**。两者路径层级不同，因此：

* 服务器**不能**直接 `git push origin main`（会把 `source-manager/` 内容推到仓库根）
* 服务器**不能**直接跟踪 `origin/main`（语义不匹配）

### 2.2 专用同步分支

为解决层级错配，使用专用子树分支：

```text
分支名: server-source-manager-sync
根目录: 即 source-manager/ 的内容
生成:   git subtree split --prefix=source-manager -b server-source-manager-sync
```

服务器 `main` 跟踪该分支：

```bash
git config remote.origin.fetch "+refs/heads/server-source-manager-sync:refs/remotes/origin/server-source-manager-sync"
git branch --set-upstream-to=origin/server-source-manager-sync main
```

### 2.3 网络现实

服务器直连 GitHub **不稳定**（`Failure when receiving data from the peer`），
完整仓库含大量二进制历史，`git fetch` 常超时。因此采用 **bundle 兜底通道**：

| 方式 | 体积 | 可靠性 |
|:---|:---|:---|
| 直连 `git fetch origin` | 完整历史 | 低（常超时） |
| bundle 传输 | **约 1.8 MB** | 高（推荐） |

### 2.4 标准同步流程

**本地 → 服务器**（服务器需要拉取最新代码时）：

```powershell
# 1. 本地重新生成子树分支
git subtree split --prefix=source-manager -b server-source-manager-sync

# 2. 推送到 GitHub
git push origin server-source-manager-sync --force

# 3. 生成 bundle 并传输
git bundle create .\work\srv-sync.bundle server-source-manager-sync
scp .\work\srv-sync.bundle jie:/tmp/srv-sync.bundle
```

```bash
# 4. 服务器拉取
/opt/ponyo-source-manager/scripts/sync.sh pull-bundle
```

**服务器 → 本地**（服务器有生产改动需要回传时）：

```bash
# 服务器提交后推送
cd /opt/ponyo-source-manager
git add -A && git commit -m "..."
/opt/ponyo-source-manager/scripts/sync.sh push
```

随后在本地重新执行 `git subtree split` 并推送，使 `main` 与专用分支保持一致。

### 2.5 服务器同步工具

`source-manager/scripts/sync.sh` 提供四个子命令：

| 命令 | 作用 |
|:---|:---|
| `sync.sh pull` | 从 GitHub 直连拉取（可能超时） |
| `sync.sh pull-bundle` | 从 `/tmp/srv-sync.bundle` 拉取（**推荐**） |
| `sync.sh status` | 查看同步状态与跟踪文件数 |
| `sync.sh push` | 推送服务器改动到 GitHub |

### 2.6 已知差异（有意保留）

以下差异是**设计选择**，不是待修复的缺陷：

* `config/live_candidates.json`：本地保留 3 个有效候选源，服务器为空数组
* `direct_parse.py`：本地保留非正片过滤逻辑（`_NON_FEATURE_RE` 等）
* `.gitignore`：根仓库与 `source-manager/.gitignore` 层级不同，各自独立

### 2.7 文件权限差异

服务器文件权限为 `755`，GitHub 为 `644`。这会导致 `git diff` 显示大量
`old mode 100755 / new mode 100644`，**内容零差异**。判断真实差异时使用：

```bash
git -c core.fileMode=false diff --name-only HEAD origin/server-source-manager-sync
```

服务器已设置 `core.fileMode=false` 以忽略该差异。

---

## 3. 语法检查约定

### 3.1 hipy 规则不是标准 Python

`source-manager/drpys/js/` 下的 `.py` 文件是 **hipy 框架规则**，使用
`@header({...})` 等非标准装饰器语法，由 hipy 运行时预处理。
标准 `ast.parse` 无法解析，**报错属预期行为，不得删除这些文件**。

典型示例：`source-manager/drpys/js/河马短剧 (1).py`

### 3.2 检查脚本

```powershell
python .\source-manager\scripts\check_syntax.py
```

该脚本排除以下路径：

* `.venv`、`__pycache__`、`.tmp`、`.staging`、`.pytest_cache`
* `drpys/js`（hipy 规则目录）

当前基线：**134 个 Python 文件全部通过**。

---

## 4. 清理边界

### 4.1 严禁删除

* `source-manager/drpys/js/` 下任何文件（含中文文件名与 `.py` 规则）
* `android/app/libs/` 下的 `.jar` / `.aar`（构建必需，`.gitignore` 有例外规则）
* `source-manager/tests/` 下的测试文件
* `docs/` 下的设计文档与计划

### 4.2 不入库内容

`.gitignore` 已覆盖以下类别，**不要**将其纳入版本控制：

* 构建产物：`*.apk`、`*.dex`、`*.class`、`build/`、`.gradle/`
* 签名密钥：`*.keystore`、`*.jks`
* 运行时数据：`source-manager/data/`、`reports/`、`logs/`
* 临时脚本：根目录 `*.py`、`tmp_*.py`、`patch_*.py`、`verify_*.py`
* 截图与 UI dump：`*.png`、`tools/*.xml`
* 本地工作区：`/work/`、`/server-edit/`

### 4.3 已入库但应清理的历史遗留

以下文件**已被 Git 跟踪**，`.gitignore` 规则对已跟踪文件无效，
需要显式 `git rm --cached` 才能移出版本控制：

* `tools/source-screening/tmp_*.py`（约 50 个一次性调试脚本）
* `docs/ui-audit/2026-08-10/`（34 个截图，约 16.9 MB）

清理前需确认这些内容不再被引用。

---

## 5. 提交约定

* 提交信息使用中文，格式：`<type>(<scope>): <描述>`
* 常用 type：`feat`、`fix`、`chore`、`docs`、`test`、`sync`、`refactor`
* 涉及服务器同步的提交使用 `sync(source-manager):` 前缀
* 提交前运行语法检查脚本确认无回归

---

## 6. 环境信息

| 项目 | 值 |
|:---|:---|
| 本地路径 | `C:\Users\Jie\Projects\lat3ncy-tvbox` |
| GitHub | `https://github.com/darkings/lat3ncy-tvbox.git` |
| 服务器路径 | `/opt/ponyo-source-manager` |
| SSH 别名 | `jie`（实际为 root） |
| Git 代理 | `http://127.0.0.1:7890`（已全局配置） |