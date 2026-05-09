# DECISIONS — Architecture Decision Records (ADR)

> 项目的"宪法"。每条 ADR 记录一个架构决策的**为什么**。
>
> **铁律:**
> 1. 一条 ADR 只记一个决策
> 2. 编号永不复用
> 3. **不修改老 ADR**,只新增 ADR 来推翻(在新 ADR 写 "Supersedes ADR-XXX",在老 ADR 把 Status 改为 "Superseded by ADR-YYY")
> 4. 决策的**当时**就写,不要事后补
> 5. 一条 ADR 控制在一页 A4 内,超过通常意味着应该拆

---

## ADR 索引

| #     | 标题                                              | 状态     | 日期       |
|-------|---------------------------------------------------|----------|------------|
| 001   | 不使用向量数据库                                   | Accepted | 2026-04-05 |
| 002   | model_provider 是一等抽象                          | Accepted | 2026-05-09 |
| 003   | PDF 提取：4 引擎 fallback 链                       | Accepted | 2026-05-09 |
| 004   | Markdown 是唯一数据库                              | Accepted | 2026-05-09 |
| 005   | Web UI 长任务用 SSE streaming，不用轮询            | Accepted | 2026-05-09 |
| 006   | LLM Provider 配置走环境变量                        | Accepted | 2026-05-09 |
| 007   | Obsidian 作为 wiki 前端，不自研编辑器              | Accepted | 2026-05-09 |
| 008   | 使用 uv 而非 poetry / pip                          | Accepted | 2026-05-09 |
| 009   | Web 框架选 FastAPI 而非 Flask                      | Accepted | 2026-05-09 |
| 010   | 自实现 .env 解析器，不依赖 python-dotenv           | Accepted | 2026-05-09 |
| 011   | PDF 大文件截断策略：取头 70% + 尾 30%             | Accepted | 2026-05-09 |

---

## ADR-001: 不使用向量数据库,LLM 直接编译 Markdown

**Date:** 2026-04-05
**Status:** Accepted

**Context:**
个人知识库需要支持语义查询。传统方案是 RAG + 向量库
(ChromaDB / Pinecone / pgvector)。但本项目灵感来自
Karpathy 的 "LLMs as compilers" 理念,核心主张是用 LLM 一次性
编译知识,而非每次查询都做向量检索。

**Decision:**
不引入向量数据库。所有内容编译为结构化 Markdown,
查询时让 LLM 直接读取相关文件。

**Consequences:**
- (+) 知识库完全人类可读、可手动编辑
- (+) 无需维护 embedding 模型一致性
- (+) 可直接用 git 版本控制,完整 diff
- (+) 与 Obsidian 等编辑器零摩擦集成
- (−) 大型 vault 查询会消耗更多 token
- (−) 跨多文件的精确召回不如向量搜索

**Alternatives considered:**
- ChromaDB + 自动 embedding:放弃,破坏可读性原则
- 混合方案 (Markdown + 可选 embedding 索引):放弃,复杂度过高,违反 "files only" 简洁性
- pgvector:放弃,引入数据库依赖

**Related:** _(关联的 SPEC 或后续 ADR)_

---

## ADR-002: model_provider 是一等抽象，业务代码不得硬编码 provider 分支

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
项目需要同时支持 OpenAI、Anthropic、Azure OpenAI、DeepSeek、Ollama 等多个 LLM provider。
如果在 compile.py / query.py / app.py 各自判断 provider 并调用不同 SDK，任何新增 provider
都需要改多处业务代码，且调用方式差异（messages 格式、response 取值）极易引入 bug。

**Decision:**
将 provider 抽象集中在 `scripts/config.py` 的 `LLMConfig` + `make_client()` + `call_llm()` 三件套。
业务脚本只调用 `call_llm(client, client_type, cfg, system, user)`，不感知底层 provider。

**Consequences:**
- (+) 新增 provider 只改 config.py 一处
- (+) 业务代码保持简洁，无 if/elif provider 分支
- (+) CLI `--ollama` 等覆盖参数统一由 `apply_cli_overrides()` 处理
- (−) config.py 成为单点复杂文件，provider 兼容逻辑集中于此
- (−) Anthropic 与 OpenAI SDK 的 response 结构差异仍需在 call_llm 内处理

**Alternatives considered:**
- 每个脚本各自写 provider 判断：放弃，维护成本随 provider 数量线性增长
- 引入 LiteLLM 统一适配层：待补充（原因待 Steven 补充）

**Related:** ADR-006

---

## ADR-003: PDF 提取采用 4 引擎 fallback 链，不收敛到单一引擎

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
PDF 质量差异极大：学术论文有复杂表格/公式，扫描件几乎无文本层，部分 PDF 会触发特定库的 bug。
没有一个引擎能覆盖所有情况。

**Decision:**
按优先级 pymupdf4llm → markitdown → pdfminer → pypdf 依次尝试，任一引擎抛异常则静默切换下一个。
`detect_pdf_backend()` 在启动时探测可用引擎，也可通过 `--pdf-backend` / `PDF_BACKEND` 环境变量手动指定。

**Consequences:**
- (+) 单个库安装失败或崩溃不影响整体功能
- (+) 用户可按需只安装部分引擎，降低依赖体积
- (+) 对 markitdown 的 NumPy 2.x 兼容性问题等有自动规避
- (−) 同一文件在不同环境可能由不同引擎处理，输出质量不一致
- (−) fallback 静默发生，用户不易察觉实际使用了哪个引擎（日志有记录）

**Alternatives considered:**
- 只用 pymupdf4llm：放弃，部分环境安装困难，且不处理 markitdown 支持的 DOCX/PPTX
- 让用户必须指定引擎：放弃，提升了上手门槛

**Related:** ADR-011

---

## ADR-004: Markdown 是唯一数据库，不引入 SQLite 或 JSON sidecar

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
Wiki 文章需要存储结构化元数据（category、last_updated、related_articles、source）。
可选方案包括：在 Markdown frontmatter 里存、另建 SQLite、维护 JSON 索引文件。

**Decision:**
元数据嵌入每篇 Markdown 文章的 frontmatter（`**类别**:`、`**最后更新**:` 等粗体字段），
唯一的状态文件是 `_meta/compile_state.json`（仅用于增量编译，不做查询索引）。
不引入数据库。

**Consequences:**
- (+) 每篇文章自包含，可独立移动/删除，无孤立记录
- (+) git diff 完整展示所有变更，包括元数据
- (+) 与 Obsidian 零摩擦，直接打开目录即用
- (−) 跨文章聚合查询（如"列出所有 concepts 类文章"）需要遍历文件系统
- (−) _meta/compile_state.json 与实际文件状态可能失步（需 --all 重建）

**Alternatives considered:**
- SQLite 存元数据 + 文章内容：放弃，破坏"files only"原则，无法直接用 Obsidian
- JSON 全局索引文件（INDEX.json）：放弃，与 Markdown INDEX.md 重复维护

**Related:** ADR-001

---

## ADR-005: Web UI 长任务（编译/健康检查）使用 SSE streaming，不用轮询

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
编译操作可能耗时数分钟（大型 PDF、多文件并发）。如果用同步 HTTP 请求，浏览器会超时；
如果用轮询，需要服务端维护任务状态和 job ID，增加复杂度。

**Decision:**
编译和健康检查接口返回 `StreamingResponse(media_type="text/event-stream")`。
后台用 `threading.Thread` 跑实际工作，通过 `asyncio.Queue` 将进度消息推到 SSE 流。
前端用 `EventSource` 接收，无需额外 WebSocket 或轮询逻辑。

**Consequences:**
- (+) 实时进度反馈，无超时风险
- (+) 服务端无需维护任务状态，连接断开即结束
- (+) 前端实现简单，浏览器原生支持 EventSource
- (−) SSE 是单向流，前端无法发送中断信号（无法实现"取消编译"）
- (−) 同时只允许一个编译任务（`_compile_lock` 互斥锁），并发请求会排队

**Alternatives considered:**
- WebSocket：放弃，双向通信对此场景过度设计，且需要额外库
- 短轮询（前端每秒 GET /status）：放弃，需服务端 job 状态管理，代码更复杂
- 长轮询：放弃，与 SSE 复杂度相当但浏览器兼容性更差

**Related:** ADR-009

---

## ADR-006: LLM Provider 配置走环境变量（.env 文件），不硬编码

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
API key 不能进入版本控制。同一套代码需要在不同机器上用不同 provider（开发用 Ollama，
生产用 OpenAI）。需要一种零代码切换 provider 的机制。

**Decision:**
所有凭证和 provider 选择通过 `.env` 文件或 shell 环境变量注入。
`config.py` 启动时读取，shell 中已有的环境变量优先于 `.env`（不覆盖已有值）。
CLI 参数（如 `--ollama`）优先级最高，可在运行时临时覆盖。

**Consequences:**
- (+) `.env` 在 `.gitignore` 中，key 永不入库
- (+) 切换 provider 无需改代码，只改 `.env`
- (+) 支持 CI 环境通过 shell env var 注入，不依赖文件
- (−) 运行时配置错误（如 key 拼写错误）只在首次调用 LLM 时暴露，无启动时校验
- (−) 多个 provider 同时配置时，优先级规则（custom > anthropic > azure > openai > ollama）需要用户理解

**Alternatives considered:**
- YAML/TOML 配置文件：放弃，.env 是业界最广泛的凭证惯例，工具链支持更好
- 硬编码 provider：放弃，显然不可行

**Related:** ADR-002

---

## ADR-007: 使用 Obsidian 作为 wiki 前端，不自研编辑器

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
Wiki 需要一个可以浏览、搜索、编辑 Markdown 并支持 `[[backlink]]` 导航的界面。
自研 Markdown 编辑器工作量巨大；使用现有工具更符合"低工程复杂度"的原则。

**Decision:**
`wiki/` 目录直接作为 Obsidian vault 打开。Obsidian 负责编辑、`[[backlink]]` 渲染、图谱视图。
项目自带的 FastAPI Web UI 只做只读浏览 + LLM 操作（编译/查询/健康检查），不提供编辑功能。

**Consequences:**
- (+) 零开发成本获得完整 Markdown 编辑器、双链导航、图谱视图
- (+) Obsidian 插件生态可扩展（Dataview、Calendar 等）
- (+) 两套界面各司其职：Obsidian 编辑，Web UI 操作 LLM
- (−) 依赖 Obsidian（macOS/Windows/iOS 专属，Linux 支持有限）
- (−) Obsidian 是闭源商业软件，个人免费但团队收费

**Alternatives considered:**
- 自研 Web 编辑器（CodeMirror + Markdown preview）：放弃，工作量过大
- Logseq：原因待 Steven 补充
- 纯命令行（无 GUI 前端）：放弃，浏览体验差

**Related:** ADR-001, ADR-004

---

## ADR-008: ⭐ 使用 uv 作为包管理器，而非 poetry / pip

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
项目需要管理 Python 依赖并提供一键安装体验。可选方案有 pip、poetry、pdm、uv 等。
原因待 Steven 补充（为何在 v0.1 时选择 uv 而非更成熟的 poetry）。

**Decision:**
`scripts/setup.sh` 以 uv 作为唯一包管理器：自动安装 uv（若缺失），
用 `uv pip install` 安装依赖，不生成 lockfile（当前无 `uv.lock`）。

**Consequences:**
- (+) uv 安装速度显著快于 pip/poetry（Rust 实现）
- (+) 单一脚本（setup.sh）即可完成整个环境初始化
- (−) uv 相对较新，部分 CI 环境默认不含 uv
- (−) 目前未锁定依赖版本（无 uv.lock），跨机器可能安装不同版本

**Alternatives considered:**
- pip + requirements.txt：待补充
- poetry：待补充
- conda：放弃，体积过大，不适合轻量脚本项目

**Related:** _无_

---

## ADR-009: ⭐ Web 框架选 FastAPI，而非 Flask

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
项目需要一个 Python Web 框架来提供 REST API + SSE streaming + Jinja2 模板渲染。
原因待 Steven 补充（为何选 FastAPI 而非 Flask）。

**Decision:**
使用 FastAPI + uvicorn 作为 Web 层。用 Pydantic `BaseModel` 做请求体校验，
用 `StreamingResponse` 做 SSE。

**Consequences:**
- (+) 原生 async/await，与 asyncio.Queue 驱动的 SSE 天然契合
- (+) Pydantic 集成提供自动请求校验和文档（/docs）
- (+) 类型注解即文档，无需额外 swagger 配置
- (−) 比 Flask 重，启动略慢，对此规模项目感知不明显
- (−) async 生态要求开发者理解 async/await + threading 混用的边界

**Alternatives considered:**
- Flask：原因待 Steven 补充
- Starlette（不带 FastAPI）：放弃，FastAPI 在其上提供了足够的附加价值

**Related:** ADR-005

---

## ADR-010: ⭐ 自实现极简 .env 解析器，不依赖 python-dotenv

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
项目需要从 `.env` 文件读取配置。python-dotenv 是标准选择，但引入了一个外部依赖。
config.py 的 `_load_dotenv()` 函数（约 20 行）实现了同样功能：跳过注释行、
处理引号、不覆盖已有环境变量。

**Decision:**
在 `config.py` 内自实现极简 `.env` 解析器，不引入 python-dotenv 依赖。

**Consequences:**
- (+) 减少一个运行时依赖
- (+) 行为完全可控（特别是"已有 env var 不覆盖"语义）
- (−) 不支持 python-dotenv 的高级特性（变量引用 `${VAR}`、多行值、`.env.local` 叠加）
- (−) 边缘情况（特殊字符、Unicode key）未经充分测试

**Alternatives considered:**
- python-dotenv：放弃，为 20 行功能引入整个依赖过于重量
- 要求用户手动 `export` 环境变量：放弃，用户体验差

**Related:** ADR-006

---

## ADR-011: ⭐ PDF 大文件截断策略：取头部 70% + 尾部 30%，而非顺序分块

**Date:** 2026-05-09
**Status:** Accepted

**Context:**
大型 PDF 提取后文本量超过 LLM 单次请求的上限（`PDF_MAX_CHARS`，默认 24,000 字符）。
需要决定如何截取：顺序取前 N 字符、均匀分块多次调用，或启发式取头尾。

**Decision:**
超限时取前 70%（摘要/引言/正文主体）+ 后 30%（结论/参考）的截断策略，一次 LLM 调用完成。
实现位于 `compile.py` 的 `extract_pdf_text()` 和 `prefetch_pdfs()`。

**Consequences:**
- (+) 保持单次 LLM 调用，简单且成本可控
- (+) 学术论文的摘要（头部）和结论（尾部）通常是最有价值的部分
- (−) 中间章节内容（通常是方法细节）会丢失
- (−) 截断是静默的（日志有警告，但用户可能未注意）
- (−) 对叙事型文档（小说、报告）头尾价值不均等的假设不成立

**Alternatives considered:**
- 顺序取前 N 字符：放弃，丢失结论部分
- 多块并行调用 LLM 后合并：放弃，成本倍增，合并逻辑复杂
- 固定分块 + 摘要树（MapReduce）：放弃，原因待 Steven 补充

**Related:** ADR-003

---

<!--
后续 ADR 在此追加,使用以下模板:

## ADR-XXX: [简短标题]

**Date:** YYYY-MM-DD
**Status:** Accepted | Accepted | Deprecated | Superseded by ADR-XXX

**Context:**
决策的背景。当时面临什么问题?有哪些约束?

**Decision:**
我们决定怎么做。一两句话。

**Consequences:**
- (+) 正面后果
- (−) 负面后果或代价

**Alternatives considered:**
- 方案 A:为什么放弃
- 方案 B:为什么放弃

**Related:** SPEC xxx, ADR-XXX
-->
