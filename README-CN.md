# LLM Wiki

> LLM 驱动的个人知识库 — 灵感来自 [Andrej Karpathy 的 LLM Knowledge Base](https://karpathy.ai) 模式。

LLM Wiki 将大型语言模型作为**知识编译器**：原始文档输入，结构化且交叉引用的 Markdown Wiki 文章输出。不需要向量数据库，不需要 Embedding — 只需文件、LLM 和 Obsidian。

---

## 为什么选择 LLM Wiki？

| | LLM Wiki | 传统 RAG |
|---|---|---|
| **存储方式** | 结构化 Markdown | 向量数据库 |
| **知识积累** | 支持 — Wiki 持续增长 | 不支持 — 无状态检索 |
| **透明度** | 完全可读 | 向量不透明 |
| **工程复杂度** | 低（文件 + LLM） | 高（Embedding、索引） |
| **交叉引用** | Obsidian `[[双链]]` | 隐式相似度 |

---

## 功能特性

- **编译** — 将 PDF、PPTX、DOCX、Markdown 转换为结构化的 Wiki 文章，自动生成摘要和交叉引用
- **查询** — 向知识库提问，LLM 从相关文章中综合生成回答
- **健康检查** — 检测断链、孤立文章、缺失元数据和知识空缺，生成健康评分
- **Web UI** — 基于 FastAPI 的 Web 界面，支持浏览、查询、编译和健康检查，实时 SSE 流式输出
- **Obsidian 集成** — 完整的 `[[双链]]` 支持，直接在 Obsidian 中打开 Wiki 目录
- **多 LLM 提供商** — 支持 OpenAI、Anthropic、Azure OpenAI、DeepSeek、Ollama（本地）及任何 OpenAI 兼容 API

---

## 快速开始

### 1. 安装

```bash
git clone <repo-url> llm-wiki && cd llm-wiki
bash scripts/setup.sh
```

安装脚本会自动配置：
- Homebrew（macOS，如未安装）
- `uv` 包管理器
- Python 依赖（openai、anthropic、rich、fastapi、uvicorn、jinja2、markitdown、pymupdf4llm）
- Ollama + 模型选择（llama3.1:8b / gemma4:e2b / gemma4:e4b）
- Obsidian（macOS，通过 Homebrew Cask）
- `.env` 配置模板

### 2. 配置

编辑 `.env`，至少添加一个 LLM 提供商：

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# 自定义 OpenAI 兼容服务（DeepSeek、通义千问、Moonshot 等）
CUSTOM_BASE_URL=https://api.deepseek.com/v1
CUSTOM_API_KEY=sk-...
CUSTOM_MODEL=deepseek-chat

# Azure OpenAI
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Ollama（本地模型，无需 API Key）
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.1:8b
```

提供商自动检测优先级：自定义 > Anthropic > Azure > OpenAI > Ollama。

### 3. 添加文档

将原始资料放入 `raw/` 目录：

```
raw/
├── papers/    # 学术论文（.pdf）
├── articles/  # 文章、博客（.md, .txt）
├── repos/     # 代码仓库笔记（.md）
└── images/    # 图片资源
```

**支持格式**：`.md` `.txt` `.pdf` `.pptx` `.ppt` `.docx` `.doc`

### 4. 编译

```bash
python3 scripts/compile.py                # 编译新文件
python3 scripts/compile.py --all          # 强制重新编译所有文件
python3 scripts/compile.py --file doc.pdf # 编译指定文件
python3 scripts/compile.py --dry-run      # 预览模式（不写入）
python3 scripts/compile.py --ollama       # 使用本地 Ollama
python3 scripts/compile.py --workers 8    # 并行 PDF 提取
```

### 5. 查询

```bash
python3 scripts/query.py "什么是注意力机制？"
python3 scripts/query.py --interactive            # 交互聊天模式
python3 scripts/query.py --save "解释 RLHF"       # 保存回答到 output/
python3 scripts/query.py --ollama "你的问题"       # 使用本地 Ollama
```

### 6. 健康检查

```bash
python3 scripts/lint.py              # 运行检查
python3 scripts/lint.py --report     # 生成详细报告
python3 scripts/lint.py --fix        # 自动修复可修复的问题
```

检查项：断裂的 `[[链接]]`、孤立文章、缺失元数据、知识空缺、INDEX 覆盖率。健康评分：100（满分）到 0（严重）。

### 7. Web UI

```bash
python3 scripts/app.py
# 打开 http://localhost:8000
```

面板：**浏览**（文章树 + Wiki 链接导航）| **查询**（LLM 问答）| **编译**（SSE 实时进度）| **健康**（一键检查 + 自动修复）| **关于**（配置信息）

---

## 目录结构

```
llm-wiki/
├── CLAUDE.md              # Agent 配置与规则
├── .env                   # LLM 提供商凭证
├── raw/                   # 原始资料（人工管理，LLM 不编辑）
│   ├── papers/
│   ├── articles/
│   ├── repos/
│   └── images/
├── wiki/                  # 编译后的知识库（LLM 维护）
│   ├── INDEX.md           # 所有文章的主索引
│   ├── LOG.md             # 演化日志
│   ├── concepts/          # 核心概念
│   ├── tools/             # 工具与框架
│   ├── research/          # 研究前沿
│   └── tutorials/         # 教程与实践
├── output/                # 生成的输出
│   ├── queries/           # 保存的问答结果
│   ├── slides/            # Marp 幻灯片
│   └── charts/            # Matplotlib 图表
├── _meta/                 # 编译状态追踪
│   └── compile_state.json
└── scripts/               # 核心工具
    ├── setup.sh           # 环境安装（中文版：setup-CN.sh）
    ├── compile.py         # 文档编译器
    ├── query.py           # 知识库查询
    ├── lint.py            # 健康检查
    ├── app.py             # Web UI（FastAPI）
    ├── config.py          # 统一 LLM 配置
    └── start.sh           # Web 应用启动器
```

---

## PDF 提取

多后端自动降级：

| 优先级 | 后端 | 优势 |
|---|---|---|
| 1 | pymupdf4llm | 最佳表格和公式支持 |
| 2 | markitdown | 广泛格式兼容 |
| 3 | pdfminer | 纯文本，最少依赖 |
| 4 | pypdf | 轻量降级方案 |

大型 PDF 自动分块处理（每次 LLM 请求最大 240KB）。扫描版 PDF 通过启发式方法检测。

---

## Wiki 文章格式

每篇编译后的文章遵循以下结构：

```markdown
# 文章标题

**类别**: concepts/tools/research/tutorials
**最后更新**: 2025-04-05
**相关文章**: [[文章A]], [[文章B]]
**原始来源**: source-file.pdf

---

## 概述
2-3 句简明摘要。

## 核心内容
详细内容，使用小节组织。

## 关键要点
- 要点 1
- 要点 2

## 延伸阅读
- [[相关文章]]

## 原始来源引用
- `raw/papers/source-file.pdf`
```

---

## Web API 接口

| 方法 | 端点 | 说明 |
|---|---|---|
| `GET` | `/api/articles` | 列出所有文章（按类别分组） |
| `GET` | `/api/articles/{category}/{name}` | 获取单篇文章内容 |
| `GET` | `/api/raw-files` | 列出原始文件及编译状态 |
| `POST` | `/api/compile` | 触发编译（SSE 流式输出） |
| `POST` | `/api/query` | 查询知识库 |
| `GET` | `/api/health` | 运行健康检查 |
| `POST` | `/api/health/fix` | 自动修复问题 |
| `GET` | `/api/config` | 显示当前 LLM 配置 |

---

## 配合 LLM Agent 使用

LLM Wiki 设计为与 AI 编程助手（Claude Code、Codex 等）协作使用。`CLAUDE.md` 文件为 Agent 提供：

- 项目规则与约定
- 会话启动协议
- Wiki 文章格式规范
- 操作命令（编译、查询、检查、增强）
- 行为准则

```bash
cd llm-wiki
claude  # 或你使用的 LLM Agent
# "编译 raw/ 中的新文件"
# "查询：什么是 RLHF？"
# "运行健康检查"
```

---

## License

MIT

---

*由 Steven Lian 创建 — 灵感来自 Andrej Karpathy 的 LLM Knowledge Base 模式。*
