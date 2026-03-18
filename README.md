# FileFlow

FileFlow 是一个面向 Windows 的本地文件整理工具。当前仓库已经从 Phase 1 进入 Phase 2 过渡状态，具备这些能力：

- 应用目录初始化
- TOML 配置模板与读写
- 文件元信息提取与扩展名大类分类
- SQLite 数据库初始化
- `Typer` CLI
- 启发式分类 + rule cache + LLM 接口骨架
- `scan --execute` 实际移动
- `undo` / `history` 回滚与历史查看

## 快速开始

```powershell
python -m pip install -e .
fileflow init
fileflow source add "C:\Users\<you>\Downloads"
fileflow scan
```

## Web UI 与 API

FileFlow 现在包含一个基于 FastAPI 的后端和 Vue 3 的前端界面。

### 启动后端 API

```powershell
fileflow serve
```
默认运行在 `http://localhost:8000`。提供以下端点：
- `/health`: 健康检查
- `/status`: 系统状态与统计信息
- `/rules`: 规则列表与过滤
- `/history`: 移动历史记录
- `/corrections`: 用户反馈/修正记录
- `/scans`: 扫描日志

### 启动前端界面

```powershell
cd frontend
npm install
npm run dev
```
默认访问地址：`http://localhost:5173`。

开发模式下，Vite 会把 `/api/*` 自动代理到 `http://127.0.0.1:8000/*`。
如果你的后端不是跑在这个地址，可以在前端目录设置环境变量后再启动：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

## 当前命令

```powershell
fileflow init
fileflow source add "C:\path\to\folder"
fileflow config set sources.scan_recursive false
fileflow source remove "C:\path\to\folder"
fileflow source list
fileflow config show
fileflow config set general.dry_run false
fileflow status
fileflow scan
fileflow preview
fileflow scan --ai
fileflow scan --execute
fileflow undo
fileflow history
fileflow feedback apply 12 "文档/归档"
fileflow feedback list
fileflow rules
fileflow rules --type pattern
fileflow rules add-pattern "invoice_\\d+\\.txt" "文档/归档"
fileflow rules add-exact "salary_slip.pdf" "文档/财务"
fileflow rules add-type-dir ".exe" "Downloads" "安装包/开发工具"
fileflow rules delete 12
```

默认 `scan` 仍然是启发式模式；加上 `--ai` 后会尝试使用 rule cache + LLM 分类，并在失败时自动回退到启发式结果。

`preview` 是 `scan` 的显式预览别名，不会移动文件。

如果你想额外管理 `Documents`，但不处理其子文件夹内容，可以先关闭递归扫描：

```powershell
python -m fileflow.cli config set sources.scan_recursive false
python -m fileflow.cli source add "$HOME\\Documents"
```

这个开关当前对所有 source 全局生效。
