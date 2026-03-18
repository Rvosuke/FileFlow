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

## 当前命令

```powershell
fileflow init
fileflow source add "C:\path\to\folder"
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
```

默认 `scan` 仍然是启发式模式；加上 `--ai` 后会尝试使用 rule cache + LLM 分类，并在失败时自动回退到启发式结果。

`preview` 是 `scan` 的显式预览别名，不会移动文件。
