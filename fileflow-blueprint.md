# FileFlow — AI 本地文件自动管理系统

## 项目蓝图 v1.0

> 专为强迫症打造的本地文件智能整理工具
> Windows · Python · OpenClaw + LLM · CLI-first

---

## 一、项目定位

FileFlow 是一个运行在本地的文件自动整理系统。它监控用户指定的"混乱"文件夹（如下载目录、桌面），借助大模型理解文件的语义（不仅仅按扩展名分类），自动将文件归类到结构化的目标目录中。

**核心差异化**：不是简单的 `if .pdf then move to /PDF`，而是让 AI 理解"这个 PDF 是发票、还是论文、还是合同"，然后做出人类强迫症级别的整理。

---

## 二、技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 语言 | Python 3.11+ | 生态成熟，Windows 兼容好 |
| LLM 接入 | OpenClaw | 支持 OAuth 登录获取 Claude/GPT 访问权；支持本地 Ollama 回退 |
| 文件监控 | watchdog | 跨平台文件系统事件监听 |
| 数据存储 | SQLite | 零配置，单文件数据库 |
| CLI 框架 | Click / Typer | 命令行交互 |
| Web 后端 | FastAPI | 后期 Web 面板用 |
| Web 前端 | Vue 3 / 纯 HTML | 轻量面板 |
| 配置管理 | TOML | 人类可读的配置文件 |
| 打包 | PyInstaller | 打包为 Windows 可执行文件 |

---

## 三、系统架构

### 3.1 目录结构

```
fileflow/
├── fileflow/                   # 主包
│   ├── __init__.py
│   ├── cli.py                  # CLI 入口（Typer）
│   ├── config.py               # 配置管理（TOML 读写）
│   ├── watcher.py              # 文件监控引擎（watchdog）
│   ├── scanner.py              # 定时全量扫描器
│   ├── analyzer/               # 分析层
│   │   ├── __init__.py
│   │   ├── meta.py             # 元信息提取（名称/类型/大小/日期）
│   │   ├── content.py          # 内容摘要（文本前 500 字、PDF 标题页等）
│   │   ├── dedup.py            # 文件去重（SHA-256 哈希）
│   │   └── classifier.py       # 文件类型初步分类（按扩展名分大类）
│   ├── ai/                     # AI 决策层
│   │   ├── __init__.py
│   │   ├── llm_client.py       # LLM 抽象层（OpenClaw / Ollama / 直连 API）
│   │   ├── prompts.py          # Prompt 模板管理
│   │   ├── decision.py         # 分类决策引擎
│   │   └── rule_cache.py       # 规则缓存（已知分类直接走规则不调 API）
│   ├── executor/               # 执行层
│   │   ├── __init__.py
│   │   ├── mover.py            # 文件移动 + 原位置快捷方式
│   │   ├── rollback.py         # 回滚引擎
│   │   └── dry_run.py          # 预览模式
│   ├── learning/               # 学习层
│   │   ├── __init__.py
│   │   ├── feedback.py         # 用户修正记录
│   │   └── rules.py            # 规则库管理
│   ├── db/                     # 数据层
│   │   ├── __init__.py
│   │   ├── models.py           # SQLite 表结构（SQLAlchemy / 原生）
│   │   └── operations.py       # 数据库操作
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── shortcut.py         # Windows 快捷方式创建（.lnk）
│       └── logger.py           # 日志配置
├── config/
│   └── default.toml            # 默认配置模板
├── tests/                      # 测试
│   ├── test_analyzer.py
│   ├── test_decision.py
│   └── test_executor.py
├── pyproject.toml              # 项目配置
└── README.md
```

### 3.2 核心数据流

```
[源文件夹] ──watchdog事件──▶ [分析层] ──文件摘要──▶ [决策层]
                                                      │
                                          ┌───规则缓存命中──▶ 直接返回分类
                                          │
                                          └───缓存未命中──▶ 调用LLM ──▶ 返回分类
                                                                          │
                                                               ▼
                                                          [执行层]
                                                      移动文件 + 创建快捷方式
                                                      写入操作日志（可回滚）
                                                               │
                                                               ▼
                                                          [学习层]
                                                      缓存本次分类规则
                                                      等待用户反馈修正
```

---

## 四、核心模块详细设计

### 4.1 配置文件 (`config/default.toml`)

```toml
[general]
target_root = "D:/Organized"        # 整理后的目标根目录
dry_run = true                      # 默认开启预览模式（安全第一）
create_shortcut = true              # 移动后在原位置创建快捷方式
scan_interval_minutes = 30          # 定时扫描间隔
log_level = "INFO"

[sources]
# 用户添加的源文件夹列表
paths = [
    "C:/Users/你的用户名/Downloads",
    "C:/Users/你的用户名/Desktop",
]

# 排除规则
exclude_patterns = [
    "*.tmp", "*.crdownload", "Thumbs.db", "desktop.ini",
    ".git/**", "node_modules/**", "__pycache__/**",
]

# 文件大小过滤
min_file_size_kb = 1                # 忽略 < 1KB 的文件
max_file_size_mb = 5120             # 忽略 > 5GB 的文件

[llm]
provider = "openclaw"               # openclaw / ollama / openai / claude
# OpenClaw 会通过自身的 OAuth 和配置管理 API 访问
# 以下为 Ollama 本地回退配置
ollama_model = "qwen3:8b"
ollama_url = "http://localhost:11434"

# LLM 调用控制
max_tokens = 500
temperature = 0.1                   # 低温度 = 更确定的分类
batch_size = 10                     # 一次请求中包含的文件数

[categories]
# 预定义的顶层分类（AI 可在此基础上细分子目录）
top_level = [
    "文档",        # docx, pdf, ppt, md, txt
    "代码项目",    # 按项目名或语言归类
    "图片与设计",  # 按来源或主题归类
    "安装包",      # exe, msi, 按软件名归类
    "压缩包",      # zip, rar, 7z
    "视频音频",    # mp4, mp3, mkv
    "其他",        # 未能分类的文件
]

# AI 可以创建的最大目录深度
max_depth = 3                       # 如: 文档/工作/2024年报告

[safety]
# 保护路径 — 永远不会被移动或修改的目录
protected_paths = [
    "C:/Windows",
    "C:/Program Files",
]
# 操作日志保留天数
log_retention_days = 90
```

### 4.2 文件分析器 (`analyzer/`)

```python
# analyzer/meta.py — 元信息提取
@dataclass
class FileMeta:
    path: Path                  # 原始完整路径
    name: str                   # 文件名（不含扩展名）
    extension: str              # 扩展名（小写）
    size_bytes: int             # 文件大小
    created_at: datetime        # 创建时间
    modified_at: datetime       # 最后修改时间
    parent_dir: str             # 所在父目录名
    sha256: str                 # 文件哈希（去重用）
    mime_type: str              # MIME 类型
    content_preview: str        # 内容预览（前 500 字或空）
    broad_category: str         # 初步大类：document/code/image/installer/archive/media

# analyzer/content.py — 内容摘要策略
PREVIEW_STRATEGIES = {
    "document": extract_text_preview,     # docx/pdf/md → 前500字
    "code":     extract_code_header,      # .py/.js → 前20行 + import列表
    "image":    extract_image_exif,       # 图片 → EXIF + 尺寸
    "archive":  extract_archive_listing,  # zip/rar → 文件列表
    "installer": extract_installer_info,  # exe → 版本信息/签名
}
```

### 4.3 AI 决策引擎 (`ai/`)

#### Prompt 设计（核心）

```python
# ai/prompts.py
CLASSIFY_PROMPT = """
你是一个文件整理助手。根据以下文件信息，决定它应该被归类到哪个目录。

## 可用的顶层分类
{top_level_categories}

## 已有的目录结构（供参考，你可以建议新的子目录）
{existing_tree}

## 待分类文件
{file_info_batch}

## 规则
1. 返回 JSON 格式，每个文件一条记录
2. target_path 是相对于目标根目录的路径，如 "文档/工作/会议纪要"
3. 如果多个文件属于同一个项目/主题，归到同一个子目录
4. 文件名如果有明显的日期信息，可以加入年份子目录
5. confidence 为 0-1 的置信度，低于 0.6 时建议人工确认
6. 如果文件看起来是临时文件或垃圾文件，标记 action 为 "skip"

## 输出格式
```json
[
  {{
    "original_path": "...",
    "target_path": "文档/工作/会议纪要",
    "suggested_rename": null,
    "confidence": 0.85,
    "action": "move",
    "reason": "文件名包含meeting_notes，内容为会议纪要"
  }}
]
```
"""
```

#### 决策流程

```python
# ai/decision.py
class DecisionEngine:
    def classify(self, files: list[FileMeta]) -> list[ClassifyResult]:
        results = []
        uncached = []

        # 第一步：查规则缓存
        for f in files:
            cached = self.rule_cache.lookup(f)
            if cached and cached.confidence >= 0.8:
                results.append(cached)
            else:
                uncached.append(f)

        # 第二步：批量调用 LLM（减少 API 调用次数）
        if uncached:
            batches = chunk(uncached, batch_size=10)
            for batch in batches:
                llm_results = self.llm_client.classify(batch)
                results.extend(llm_results)

                # 第三步：将高置信度结果存入规则缓存
                for r in llm_results:
                    if r.confidence >= 0.8:
                        self.rule_cache.store(r)

        return results
```

#### 规则缓存策略

```python
# ai/rule_cache.py — 三级缓存
class RuleCache:
    """
    Level 1: 精确匹配 — 文件名完全相同（如每月的"工资条.pdf"）
    Level 2: 模式匹配 — 文件名匹配正则（如 "meeting_*_2024.docx"）
    Level 3: 类型+目录匹配 — 同扩展名+同来源目录（如 Downloads下的所有.exe）
    """
    def lookup(self, file: FileMeta) -> Optional[ClassifyResult]:
        # 依次尝试三级缓存
        for level in [self._exact, self._pattern, self._type_dir]:
            result = level(file)
            if result:
                return result
        return None
```

### 4.4 执行引擎 (`executor/`)

```python
# executor/mover.py
class FileMover:
    def execute(self, plan: ClassifyResult, dry_run: bool = False) -> MoveRecord:
        record = MoveRecord(
            source=plan.original_path,
            target=plan.target_path,
            timestamp=datetime.now(),
        )

        if dry_run:
            record.status = "preview"
            return record

        # 1. 确保目标目录存在
        target_dir = self.target_root / plan.target_path
        target_dir.mkdir(parents=True, exist_ok=True)

        # 2. 处理文件名冲突
        final_name = self._resolve_conflict(target_dir, plan)

        # 3. 移动文件
        final_path = target_dir / final_name
        shutil.move(str(plan.original_path), str(final_path))

        # 4. 在原位置创建快捷方式
        if self.config.create_shortcut:
            create_windows_shortcut(
                shortcut_path=plan.original_path.with_suffix('.lnk'),
                target_path=final_path,
            )

        # 5. 记录操作日志（用于回滚）
        record.final_path = final_path
        record.status = "completed"
        self.db.save_move_record(record)

        return record

# executor/rollback.py
class RollbackEngine:
    def undo_last(self, n: int = 1):
        """回滚最近 n 次操作"""
        records = self.db.get_recent_moves(n)
        for record in reversed(records):
            # 移回原位
            shutil.move(str(record.final_path), str(record.source))
            # 删除快捷方式
            shortcut = record.source.with_suffix('.lnk')
            if shortcut.exists():
                shortcut.unlink()
            record.status = "rolled_back"
            self.db.update_record(record)
```

### 4.5 Windows 快捷方式 (`utils/shortcut.py`)

```python
# 使用 win32com 创建 .lnk 快捷方式
import win32com.client

def create_windows_shortcut(shortcut_path: Path, target_path: Path):
    """在原文件位置创建指向新位置的快捷方式"""
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.WorkingDirectory = str(target_path.parent)
    shortcut.Description = f"FileFlow: moved to {target_path.parent}"
    shortcut.save()
```

### 4.6 数据库结构 (`db/models.py`)

```sql
-- 文件移动记录（核心表）
CREATE TABLE move_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,           -- 原始路径
    target_path TEXT NOT NULL,           -- 目标路径
    file_hash   TEXT,                    -- SHA-256
    file_size   INTEGER,
    category    TEXT,                    -- 分类标签
    confidence  REAL,                    -- AI 置信度
    reason      TEXT,                    -- AI 给出的理由
    status      TEXT DEFAULT 'completed', -- completed/rolled_back/preview
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 分类规则缓存
CREATE TABLE rule_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_type  TEXT NOT NULL,           -- exact/pattern/type_dir
    match_key   TEXT NOT NULL,           -- 匹配键
    target_path TEXT NOT NULL,           -- 分类目标
    confidence  REAL,
    hit_count   INTEGER DEFAULT 1,       -- 命中次数
    last_hit    TIMESTAMP,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 用户修正记录
CREATE TABLE corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    move_record_id  INTEGER REFERENCES move_records(id),
    original_target TEXT NOT NULL,       -- AI 原始分类
    corrected_target TEXT NOT NULL,      -- 用户修正后的分类
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 扫描记录
CREATE TABLE scan_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path     TEXT NOT NULL,
    files_found     INTEGER,
    files_moved     INTEGER,
    files_skipped   INTEGER,
    files_cached    INTEGER,             -- 命中缓存的数量
    llm_calls       INTEGER,             -- API 调用次数
    duration_ms     INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 五、CLI 命令设计

```bash
# 初始化配置
fileflow init

# 添加/移除源文件夹
fileflow source add "C:/Users/xxx/Downloads"
fileflow source remove "C:/Users/xxx/Desktop"
fileflow source list

# 扫描并整理（核心命令）
fileflow scan                       # 扫描所有源文件夹（默认 dry-run）
fileflow scan --execute             # 实际执行移动
fileflow scan --path "D:/某目录"     # 扫描指定目录
fileflow scan --type document       # 只扫描文档类

# 预览整理方案
fileflow preview                    # 展示 dry-run 结果表格

# 回滚
fileflow undo                       # 撤销上一次操作
fileflow undo --last 5              # 撤销最近 5 次
fileflow undo --all                 # 撤销今天所有操作

# 查看状态
fileflow status                     # 显示统计摘要
fileflow history                    # 显示操作历史
fileflow rules                      # 显示已学习的规则

# 后台监控
fileflow watch                      # 启动实时监控（前台）
fileflow watch --daemon             # 后台守护进程

# 配置
fileflow config show                # 显示当前配置
fileflow config edit                # 用编辑器打开配置文件
fileflow config set general.dry_run false
```

### CLI 输出示例

```
$ fileflow scan

📂 扫描中... 找到 23 个新文件

┌──────────────────────────────┬────────────────────────────┬──────────┬────────────┐
│ 原始文件                      │ 建议归类到                  │ 置信度    │ 来源       │
├──────────────────────────────┼────────────────────────────┼──────────┼────────────┤
│ meeting_0315.docx            │ 文档/工作/会议纪要           │ 0.92 ✅  │ AI 分类    │
│ invoice_202403.pdf           │ 文档/财务/发票              │ 0.88 ✅  │ AI 分类    │
│ photo_2024_spring.jpg        │ 图片与设计/生活照片/2024     │ 0.75 ⚠️ │ AI 分类    │
│ VSCodeSetup-1.87.exe         │ 安装包/开发工具              │ 0.95 ✅  │ 规则缓存   │
│ project-frontend.zip         │ 压缩包/项目归档              │ 0.70 ⚠️ │ AI 分类    │
│ random_temp.tmp              │ （跳过 — 临时文件）          │ -        │ 排除规则   │
└──────────────────────────────┴────────────────────────────┴──────────┴────────────┘

📊 摘要: 22 个可整理 | 1 个跳过 | 17 命中缓存 | 5 次 LLM 调用
⚠️  2 个低置信度文件需要确认

执行移动？ [y/N/e(编辑)]
```

---

## 六、MVP 开发路线图

### Phase 1 — 骨架搭建（第 1 周）

- [x] 项目初始化（pyproject.toml, 目录结构）
- [ ] 配置文件读写（TOML）
- [ ] 元信息提取器（meta.py）
- [ ] 文件类型初步分类器（按扩展名分大类）
- [ ] SQLite 数据库初始化 + 表结构
- [ ] CLI 骨架（`fileflow init`, `fileflow source add/list`）

### Phase 2 — AI 决策接入（第 2 周）

- [ ] LLM 抽象层（先支持 OpenClaw，回退到 Ollama）
- [ ] Prompt 模板设计与调试
- [ ] 批量分类逻辑
- [ ] 规则缓存（三级缓存）
- [ ] `fileflow scan` 实现（dry-run 模式）

### Phase 3 — 执行与安全（第 3 周）

- [ ] 文件移动引擎 + 冲突处理
- [ ] Windows 快捷方式创建
- [ ] 操作日志 + 回滚引擎
- [ ] `fileflow scan --execute` / `fileflow undo`
- [ ] 内容摘要器（文档类优先）

### Phase 4 — 监控与体验（第 4 周）

- [ ] watchdog 实时监控 (`fileflow watch`)
- [ ] 去重检测
- [ ] Rich 库美化 CLI 输出（表格、进度条、颜色）
- [ ] 用户修正反馈 → 规则更新
- [ ] 基础测试用例

### Future — Web 面板 & 进阶

- [ ] FastAPI 后端 API
- [ ] Vue 3 Web 面板（文件预览、拖拽修正、统计仪表盘）
- [ ] Windows 系统托盘（pystray）
- [ ] 图片 EXIF / OCR 分析
- [ ] 代码项目智能识别（检测 package.json, Cargo.toml 等）
- [ ] 安装包版本信息提取
- [ ] PyInstaller 打包为单文件 exe

---

## 七、关键设计原则

### 7.1 安全第一

- **默认 dry-run**：首次扫描永远只预览，不实际执行
- **操作可回滚**：每次移动都有完整日志，支持任意回滚
- **保护路径**：系统目录永远不会被扫描或修改
- **快捷方式兜底**：移动后原位置留快捷方式，不会"找不到文件"
- **文件名冲突**：自动添加 `_1`, `_2` 后缀，永不覆盖

### 7.2 成本控制

- **三级规则缓存**：大部分常见文件类型只需一次 LLM 调用，后续走缓存
- **批量请求**：一次 prompt 包含多个文件，减少 API 调用
- **低温度**：temperature=0.1 确保稳定一致的分类结果
- **渐进式学习**：系统越用越聪明，LLM 调用越来越少

### 7.3 强迫症友好

- **一致性**：相同类型的文件永远归到同一个目录
- **可读的目录名**：中文/英文均可，不用 hash 或 ID
- **层级合理**：最深 3 层，不会出现 `/文档/工作/项目/子项目/v2/最终版/` 这种灾难
- **整洁的日期结构**：按年份/月份子目录，不会一个文件夹里堆几千个文件

---

## 八、OpenClaw 集成方案

### 方案 A：作为 LLM 路由（推荐 MVP）

FileFlow 不直接管理 API Key，而是通过 OpenClaw 的 LLM 路由能力获取大模型访问：

```python
# ai/llm_client.py
class OpenClawClient:
    """通过 OpenClaw 的本地 gateway 发送 LLM 请求"""

    def __init__(self):
        # OpenClaw gateway 默认监听在本地
        self.base_url = "http://localhost:3000"

    async def classify(self, prompt: str) -> str:
        # 通过 OpenClaw 的消息 API 发送分类请求
        # OpenClaw 自动路由到用户配置的模型（Claude/GPT/本地）
        response = await self._send_message(prompt)
        return self._parse_json_response(response)
```

### 方案 B：独立 LLM 客户端（回退方案）

如果用户不想安装 OpenClaw，提供直连选项：

```python
class DirectLLMClient:
    """直接调用 Ollama 或 API"""

    PROVIDERS = {
        "ollama": OllamaProvider,     # 本地免费
        "openai": OpenAIProvider,     # 需要 API Key
        "claude": ClaudeProvider,     # 需要 API Key
    }
```

用户在配置文件中选择 provider，系统自动切换。

---

## 九、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| AI 分类错误导致文件找不到 | 高 | dry-run 默认开启 + 快捷方式 + 完整回滚 |
| LLM API 费用过高 | 中 | 三级缓存 + 批量请求 + 本地模型回退 |
| OpenClaw 未安装或不可用 | 中 | 自动降级到 Ollama 本地模型 |
| 大文件移动耗时 | 低 | 同分区用 rename（瞬时），跨分区用异步复制 |
| 文件被其他程序占用 | 中 | 检测文件锁，跳过并标记，下次重试 |
| 目录结构随时间膨胀 | 低 | 限制最大深度 + 定期报告目录统计 |
