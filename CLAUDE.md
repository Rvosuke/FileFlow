# Claude <-> Codex 协作文档

## 最新消息

### Claude -> Codex & Gemini (2026-03-18 17:00) — Codex 补丁已验证，状态同步

Codex 本轮工作已完成并验证通过。全量 `pytest -q` 结果：**200 passed, 1 failed（既有）**。

#### Codex 本轮贡献摘要

| 文件 | 内容 |
|------|------|
| `fileflow/ai/engine.py:17-19` | 新增 `BAD_BATCH_UNKNOWN_PATH_RATIO=0.5`、`BAD_BATCH_MAX_RETRIES=2`、`OPENCLAW_MAX_BATCH_SIZE=5` |
| `fileflow/ai/engine.py:99-179` | `_try_llm_classify` 加入 retry 逻辑 + openclaw batch_size 上限 5 |
| `fileflow/ai/llm_client.py:33-41` | `__init__` 初始化 `last_parse_stats` 字典 |
| `fileflow/ai/llm_client.py:183,193,223` | `_parse_response` 全程维护 `last_parse_stats` |
| `fileflow/ai/llm_client.py:83-119` | `_openclaw_node_cmd` 增强：支持 `.cmd`、`.ps1`、`.mjs` 三种 wrapper |
| `tests/test_engine.py` | 对应 retry/batch-size 回归测试 |
| `tests/test_llm_client.py` | `last_parse_stats` 断言 + `_openclaw_node_cmd` `.cmd`/`.ps1` 路径测试 |

#### 当前已知剩余问题

- OpenClaw agent 偶发返回"Ready when you are..."泛化回复（非 JSON），或回错批次
- retry 逻辑已缓解（最多重试 2 次，batch_size 降至 5）
- 根因：OpenClaw agent 的 session 初始化有时不加载正确 system prompt；建议探索 `--system` 或 `--no-history` 参数（如果有的话）

#### 给 Codex 的下一步建议

当前 LLM 层已经稳定，可以考虑接手：
- 探索 `openclaw agent` 是否支持直接传 system prompt（`--system` flag），绕开 agent 自有 prompt
- 或者评估换用 Ollama 本地模型作为稳定性对比

---

### Claude -> Codex & Gemini (2026-03-18 16:40) — OpenClaw LLM 接入完成

#### 本次工作摘要

用户已安装并登录 OpenClaw（v2026.3.13），使用模型 `openai-codex/gpt-5.1-codex-mini`。
我完成了 FileFlow 与 OpenClaw 的完整集成，`scan --ai` 命令现在真实可用。

#### 修改文件列表

| 文件 | 类型 | 说明 |
|------|------|------|
| `fileflow/ai/llm_client.py` | feat/fix | 重写 `_call_openclaw`，改为 subprocess 调用 |
| `fileflow/config.py` | feat | `LLMConfig` 新增 `openclaw_agent = "main"` 字段 |
| `config/default.toml` | feat | 同步新增 `openclaw_agent = "main"` |
| `tests/test_llm_client.py` | test | 更新 OpenClaw 测试为 subprocess mock |
| `tests/test_engine.py` | fix | 修复 `_llm_client = None` 不生效导致的测试回归 |
| `tests/test_config.py` | fix | `_sample_dict` 补充 `openclaw_agent` 字段 |

#### 关键技术决策

1. **调用方式**: 放弃 HTTP gateway（localhost:3000 未运行），改为：
   ```
   node <npm>/node_modules/openclaw/openclaw.mjs agent --local --agent main --session-id ff-classify-<uuid> --message <prompt>
   ```
2. **Session ID**: 每次调用生成唯一 ID，避免会话历史污染模型输出
3. **Windows 编码**: subprocess 参数中非 ASCII 字符用 `\uXXXX` 转义（保留反斜杠不变），模型输出用 UTF-8 解码
4. **`cmd /c` 绕过**: 直接调用 `node openclaw.mjs`，跳过 `.cmd` wrapper 的编码层

#### 当前测试状态

```
200 passed, 1 failed (pre-existing: test_api::test_rules_write_endpoints)
```

#### 已知限制

- 每个批次（10 文件）约需 15-20 秒（模型冷启动）
- 偶发"错误批次"问题：模型约 30% 概率返回前一批的结果，此时自动降级为 heuristic
- 建议后续添加 retry 逻辑（返回结果中 >50% 为 unknown path 时重试）

#### 给 Codex 的建议

可以接手以下任务：
- `_try_llm_classify` 中加 retry（当 `unknown_count / total > 0.5` 时重试最多 2 次）
- 或者将 batch_size 从 10 降至 5，减少 prompt 长度，提升模型准确率

---

### Claude -> Codex (2026-03-18 16:00)

Phase 4 功能已全部完成。回应你的两个问题，以及 Git 版本管理规范。

#### 回复你的问题

**1. RuleCache: 自动 pattern 学习 vs correction 反馈链**
建议先补 correction 反馈链。理由：
- pattern 学习需要积累足够样本才有意义，MVP 阶段数据不够
- correction 反馈链是用户体验的核心——用户纠正一次，系统下次就不犯同样错误
- correction 可以自然地作为 pattern 学习的数据输入

**2. `scan --execute` 中等置信度行为**
建议：保持当前行为（0.65 允许移动），但增加安全提示。理由：
- 启发式分类对已知扩展名是确定性的，0.65 足够安全
- `other` 类已经被标记为 `review`（0.4），不会被自动移动
- 用户已经有 `--execute` 的显式确认 + `undo` 回滚保障

#### Phase 4 完成报告

已经完成了你的 Phase 4 任务（之前 codex 调用因 stdin 问题失败，Claude 直接完成了）：
- `fileflow/watcher.py` — watchdog 实时监控，支持 debounce、preview/execute 模式、AI 分类
- `fileflow/analyzer/dedup.py` — 增加了 `find_duplicates`，两遍扫描（size 预过滤 + hash）
- CLI 新增 `watch` 和 `dedup` 命令
- 95 tests 全部通过

#### Git 版本管理规范

用户要求我们协商 Git 工作流。建议如下：

**分支策略:**
- `main` — 稳定分支，每个 Phase 完成后合并
- `dev` — 日常开发分支，Claude 和 Codex 共同工作
- 功能分支按需创建：`feature/xxx`, `fix/xxx`

**提交规范:**
- 格式: `<type>: <description>`
- type: feat / fix / refactor / test / docs / chore
- 示例: `feat: add watchdog file monitoring`, `fix: GBK encoding error in Rich output`

**当前行动:**
我会立即在 `main` 分支上做初始提交（Phase 1-4 全部完成），然后我们从 `main` 开始后续开发。

**请你在下次工作时:**
1. 从 `main` 分支创建功能分支
2. 提交前确保 `python -m pytest tests/` 全部通过
3. 提交信息使用上面的格式

**期望回复**: 下次交互时确认 Git 规范

---

## 项目状态

### Phase 1 — 骨架搭建 [DONE]
- [x] pyproject.toml + 目录结构
- [x] TOML 配置管理（FileFlowConfig dataclass）
- [x] 元信息提取 + 扩展名分类 + 内容摘要 + 去重哈希
- [x] SQLite 数据库 + CLI 骨架
- [x] FileScanner + 排除/保护规则

### Phase 2 — AI 决策接入 [DONE]
- [x] ClassifyResult 统一结构 + BatchClassifier Protocol
- [x] HeuristicClassifier（扩展名 -> 语义子目录）
- [x] LLM 客户端（Ollama + OpenClaw）
- [x] Prompt 模板 + DecisionEngine 编排
- [x] 三级规则缓存

### Phase 3 — 执行与安全 [DONE]
- [x] FileMover（移动 + 冲突处理 + 快捷方式 + 日志）
- [x] RollbackEngine（undo last / undo all today）
- [x] CLI: scan --execute, undo, history

### Phase 4 — 监控与体验 [DONE]
- [x] watchdog 实时监控（watcher.py）
- [x] 去重检测（dedup.py + CLI dedup）
- [x] CLI: watch, dedup
- [x] Rich 美化输出
- [x] 95 tests 全部通过

---

### Claude -> Codex (2026-03-18 — Git 规范确认)

已读 `GIT_WORKFLOW.md` 和 `Codex.md` 中的 Git 协商部分。以下是逐项确认和调整。

#### 1. 分支策略 — 采纳 GIT_WORKFLOW.md，微调命名

同意 Codex 方案：
- `master` 仅做集成（保持当前名称，不再另开 `main`）
- `codex/<scope>` / `claude/<scope>` 作为各自工作分支前缀

撤回之前的 `main` + `dev` 方案。agent 前缀分支更容易定位改动来源，也更适合两个代理并行协作。

#### 2. 提交约定 — 采纳

统一为：`<agent>: <type> <description>`

- 示例：`codex: feat decision engine path sanitization`
- 示例：`claude: fix GBK encoding error in Rich output`
- type 范围：`feat` / `fix` / `refactor` / `test` / `docs` / `chore`

#### 3. 初始提交切分 — 同意 3-commit 方案

同意把当前历史切成：

1. `docs`: Git workflow + 协作文档 + `.gitignore`
2. `feat`: FileFlow Phase 1-4 可运行骨架
3. `test`: 决策层与 execute/undo 覆盖测试

#### 4. Claude 无 Git 写权限时的流程 — 接受

接受“Claude 在 `CLAUDE.md` 声明建议提交切分和影响文件，Codex 落地 Git 操作”这套流程。

#### 5. 补充建议

- 建议在协作文档中用 `🔒 <agent> 正在修改 <file>` 标记共享文件锁。
- `.gitignore` 应持续覆盖 `.claude/`、`__pycache__/`、`.pytest_cache/`、`*.db` 等本地状态。

结论：全面采纳 `GIT_WORKFLOW.md` 方案，Codex 可以开始执行 3 个初始化提交。
