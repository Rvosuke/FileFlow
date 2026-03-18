# Git Workflow

本项目目前由 Codex、Claude 和 Gemini 协作开发，Git 规则需要先于功能开发达成一致。

## 分支约定

- `master`
  - 仅作为集成分支。
  - 只有在一轮功能经过测试并完成对接后，才允许合入。
- `codex/<scope>`
  - Codex 的工作分支。
  - 当前活跃分支示例：`codex/learning-feedback`
- `claude/<scope>`
  - Claude 在具备 Git 写权限时使用的分支前缀。
  - 如果 Claude 当前只能通过文件交流，则必须在 `CLAUDE.md` 中声明它建议的提交切分和提交信息。
- `gemini/<scope>`
  - Gemini 在具备 Git 写权限时使用的分支前缀。
  - 如果 Gemini 当前只能通过文件交流，则必须在 `Gemini.md` 中声明它建议的提交切分和提交信息。

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
- 安装新依赖、初始化新子项目或生成大量产物前，先确认 `.gitignore` 已覆盖对应缓存和构建目录。

## 协作同步

- 每次开始改动前，先检查：
  - `git status --short`
  - `INBOX.md`
  - `Codex.md`
  - `CLAUDE.md`
  - `Gemini.md`
- `INBOX.md`
  - 实时短消息通道
  - 用于当前轮次的状态同步、阻塞、锁文件、对账
  - 由于没有 push 通知，双方必须主动轮询
- `Codex.md` / `CLAUDE.md` / `Gemini.md`
  - 长文档通道
  - 用于阶段总结、设计意见、提交建议
- 代理间正式对接只使用：
  - `INBOX.md` -> 实时交流
  - `Codex.md` -> Codex 给工作中的 Claude
  - `CLAUDE.md` -> 工作中的 Claude 给 Codex
  - `Gemini.md` -> Gemini 的长文档协作入口
- 不使用 `claude -p` 之类的无上下文子助手做正式项目协商；它的输出不能视为项目内正式决定。
- 强制轮询检查点：
  - 开始一轮工作前先读 `INBOX.md`
  - 修改共享核心文件前先读 `INBOX.md`
  - 每次补丁后先读 `INBOX.md`
  - 长命令/测试前后先读 `INBOX.md`
  - 连续工作超过 2 分钟，先暂停并读 `INBOX.md`
- 紧急消息约定：
  - 标题含 `[NEED-REPLY]` 表示接收方必须先回执，再继续当前任务
- 实时短消息统一使用四段式：
  - `Done`
  - `Next`
  - `Blocker`
  - `Locked Files`
- 如果要修改共享核心文件，先在协作文档里声明：
  - `fileflow/cli.py`
  - `fileflow/config.py`
  - `fileflow/ai/*`
  - `fileflow/executor/*`
- 锁文件格式固定为：
  - `LOCK <path> <eta>`
  - `RELEASE <path> <commit-or-status>`
- 合并到 `main` 后必须同步：
  - merge commit
  - 当前分支
  - `main` 是否已全量测试通过
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

## 角色分工

- Codex
  - 负责 backend / API / contract / 关键集成修复
- Claude
  - 负责测试补齐、合并对账、主线集成
  - 当前默认唯一执行 `main` 合并的人
- Gemini
  - 负责 frontend / docs / 包装层体验

以上分工不是永久冻结，但未重新协商前按此执行，避免三人同时进入同一层。

## 忽略项

以下内容不进入 Git：

- `INBOX.md`
- `.claude/`
- `__pycache__/`
- `.pytest_cache/`
- `*.db`
- 运行时 `%APPDATA%/FileFlow` 产生的本地状态

## 当前实践

- `main` 保持可集成状态
- Codex 在 `codex/learning-feedback` 上继续推进 learning / feedback / CLI 补全
- Claude 负责补 executor / dedup / watcher 测试，并在合适时机协助合并回 `main`
- `INBOX.md` 只做运行时通信，不进 Git
