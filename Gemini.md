# Gemini <-> Team

## 协作入口

- 实时短消息：`INBOX.md`
- 长文档总结：本文件

## 当前协议

1. 开始一轮工作前先读：
   - `INBOX.md`
   - `GIT_WORKFLOW.md`
   - 相关协作文档
2. 修改共享核心文件前，先在 `INBOX.md` 发锁消息
3. `[NEED-REPLY]` 消息需要优先回执
4. Git 分支前缀使用 `gemini/<scope>`

## 当前项目状态

- `main` 已包含：
  - feedback learning / preview / config edit
  - manual rules CRUD
- Codex 当前在推进：
  - FastAPI API skeleton (`fileflow/api/app.py`, `fileflow/cli.py` serve)
- Claude 当前在推进：
  - `tests/test_watcher.py`
  - `tests/test_rule_cache.py`
  - `tests/test_executor.py` / `tests/test_dedup.py` coverage

## Gemini 的工作清单

1. **[Web] 前端骨架搭建 (Vue 3 + Vite)**
   - 目标：在 `frontend/` 或 `web/` 下初始化项目。
   - 路由：`/health`, `/status`, `/rules`, `/history`, `/corrections`。
2. **[Core] 文件内容预览增强**
   - 目标：在 `fileflow/analyzer/content.py` 中实现摘要/预览提取，用于前端显示。
3. **[Docs/Chore] 完善项目 README.md 与打包调研**
   - 目标：更新文档以适应新 API 结构，调研 PyInstaller 打包方案。

