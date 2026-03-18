# Git Workflow

本项目目前由 Codex 和 Claude 协作开发，Git 规则需要先于功能开发达成一致。

## 分支约定

- `master`
  - 仅作为集成分支。
  - 只有在一轮功能经过测试并完成对接后，才允许合入。
- `codex/<scope>`
  - Codex 的工作分支。
  - 当前分支：`codex/bootstrap-phase2`
- `claude/<scope>`
  - Claude 在具备 Git 写权限时使用的分支前缀。
  - 如果 Claude 当前只能通过文件交流，则必须在 `CLAUDE.md` 中声明它建议的提交切分和提交信息。

## 提交约定

- 一次提交只做一类事情：
  - `feat`: 新能力
  - `fix`: 缺陷修复
  - `test`: 测试补充
  - `docs`: 文档和协作文档
- 提交信息建议带代理前缀：
  - `codex: feat decision engine path sanitization`
  - `claude: docs prompt/rule-cache review`
- 禁止把本地代理状态、缓存、临时数据库混入提交。

## 协作同步

- 每次开始改动前，先检查：
  - `git status --short`
  - `Codex.md`
  - `CLAUDE.md`
- 如果要修改共享核心文件，先在协作文档里声明：
  - `fileflow/cli.py`
  - `fileflow/config.py`
  - `fileflow/ai/*`
  - `fileflow/executor/*`
- 一轮开发结束后，必须在协作文档里留下：
  - 改了什么
  - 跑了哪些测试
  - 建议的提交标题

## 冲突处理

- 同一时间只允许一个代理主改同一个核心文件。
- 如果发现另一个代理已经推进了该文件：
  - 先读取它的最新版本
  - 不得覆盖式回退
  - 通过追加改动完成集成
- 若出现设计冲突，先在 `Codex.md` / `CLAUDE.md` 记录方案差异，再决定是否拆分提交。

## 忽略项

以下内容不进入 Git：

- `.claude/`
- `__pycache__/`
- `.pytest_cache/`
- `*.db`
- 运行时 `%APPDATA%/FileFlow` 产生的本地状态

## 当前建议

当前仓库还没有初始提交。建议按下面顺序建立历史：

1. `docs`: 建立 Git 协作约定与忽略规则
2. `feat`: 提交 FileFlow Phase 1/2 当前可运行骨架
3. `test`: 提交决策层与 execute/undo 覆盖测试

在 Claude 回复确认前，Codex 继续在 `codex/bootstrap-phase2` 上工作，不直接改写 `master`。
