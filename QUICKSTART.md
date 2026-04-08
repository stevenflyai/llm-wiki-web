# LLM Wiki 快速开始

> 5 分钟搭建你的 AI 知识库。

---

## 第一步：安装环境

```bash
git clone <repo-url> llm-wiki
cd llm-wiki
bash scripts/setup.sh
```

安装脚本会自动完成以下工作：

| 组件 | 说明 |
|---|---|
| Homebrew | macOS 包管理器（如未安装会自动安装） |
| uv | Python 包管理器 |
| Python 依赖 | openai, anthropic, rich, fastapi, uvicorn, jinja2, markitdown, pymupdf4llm |
| Ollama | 本地免费模型（可选，支持 llama3.1:8b / gemma4:e2b / gemma4:e4b） |
| Obsidian | Markdown 知识库前端（可选） |

安装完成后会显示汇总报告，确认各组件状态。

---

## 第二步：配置 LLM

```bash
cp .env.example .env
nano .env    # 或用你喜欢的编辑器
```

只需配置**一个** LLM 提供商即可，取消对应行的注释并填入 API Key：

```bash
# 方案一：Anthropic Claude（推荐）
ANTHROPIC_API_KEY=sk-ant-你的Key
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# 方案二：OpenAI
OPENAI_API_KEY=sk-你的Key
OPENAI_MODEL=gpt-4o

# 方案三：DeepSeek / 通义千问等（OpenAI 兼容）
CUSTOM_BASE_URL=https://api.deepseek.com/v1
CUSTOM_API_KEY=sk-你的Key
CUSTOM_MODEL=deepseek-chat

# 方案四：Ollama 本地模型（无需 Key）
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.1:8b
```

自动检测优先级：自定义 > Anthropic > Azure > OpenAI > Ollama。

---

## 第三步：放入资料

将你的文档放入 `raw/` 目录：

```
raw/
├── papers/    ← 学术论文（.pdf）
├── articles/  ← 文章、笔记（.md .txt）
├── repos/     ← 代码仓库笔记（.md）
└── images/    ← 图片资源
```

**支持格式**：`.md` `.txt` `.pdf` `.pptx` `.ppt` `.docx` `.doc`

---

## 第四步：编译

将原始资料"编译"成结构化的 Wiki 文章：

```bash
python3 scripts/compile.py
```

编译器会：
1. 扫描 `raw/` 下所有未处理的文件
2. 提取内容（PDF 自动选择最佳引擎）
3. 调用 LLM 生成结构化 Wiki 文章
4. 写入 `wiki/` 并更新索引

更多选项：

```bash
python3 scripts/compile.py --all          # 强制重新编译所有文件
python3 scripts/compile.py --file xxx.pdf # 只编译指定文件
python3 scripts/compile.py --dry-run      # 预览模式，不写入文件
python3 scripts/compile.py --ollama       # 使用本地 Ollama 模型
python3 scripts/compile.py --workers 8    # 并行提取 PDF（加速）
```

---

## 第五步：查询

向知识库提问：

```bash
python3 scripts/query.py "什么是注意力机制？"
```

更多用法：

```bash
python3 scripts/query.py --interactive           # 交互聊天模式
python3 scripts/query.py --save "解释 RLHF"      # 保存回答到 output/queries/
python3 scripts/query.py --ollama "你的问题"      # 使用本地模型
python3 scripts/query.py --model gpt-4o "问题"   # 指定模型
```

---

## 第六步：健康检查

检查知识库的完整性：

```bash
python3 scripts/lint.py              # 运行检查并显示结果
python3 scripts/lint.py --report     # 生成详细 Markdown 报告
python3 scripts/lint.py --fix        # 自动修复可修复的问题
```

检查项包括：断裂的 `[[链接]]`、孤立文章、缺失元数据、知识空缺、INDEX 覆盖率。

---

## 第七步：Web UI

启动 Web 界面：

```bash
python3 scripts/app.py
# 或
bash scripts/start.sh
```

打开 http://localhost:8000 ，包含以下面板：

| 面板 | 功能 |
|---|---|
| **浏览** | 文章树导航，点击 Wiki 链接跳转 |
| **查询** | LLM 问答，显示来源文章 |
| **编译** | 实时编译进度（SSE 流式输出） |
| **健康** | 一键检查 + 自动修复 |
| **关于** | 当前 LLM 配置信息 |

---

## 日常工作流

```
添加新资料 → 编译 → 查询 → 检查质量
     ↓          ↓        ↓         ↓
  raw/     compile.py  query.py  lint.py
```

```bash
# 1. 放入新文件
cp ~/Downloads/new-paper.pdf raw/papers/

# 2. 编译
python3 scripts/compile.py

# 3. 查询
python3 scripts/query.py "这篇论文的核心贡献是什么？"

# 4. 检查
python3 scripts/lint.py --report

# 5. 在 Obsidian 或 Web UI 中浏览
python3 scripts/app.py
```

---

## 配合 LLM Agent 使用

LLM Wiki 天然适配 AI 编程助手（Claude Code、Codex 等）：

```bash
cd llm-wiki
claude   # 启动 Claude Code
```

然后直接用自然语言操作：

- "编译 raw/ 中的新文件"
- "查询：什么是 RLHF？"
- "运行健康检查"
- "增强 Transformer 文章，补充更多细节"

Agent 会自动读取 `CLAUDE.md` 了解项目规则。

---

## 目录速查

```
llm-wiki/
├── raw/          # 原始资料（你管理，LLM 不碰）
├── wiki/         # 编译后的知识库（LLM 维护）
│   ├── INDEX.md  # 文章主索引
│   └── LOG.md    # 变更日志
├── output/       # 查询结果、幻灯片等输出
├── _meta/        # 编译状态元数据
├── scripts/      # 所有工具脚本
└── .env          # LLM 配置（不要提交到 Git）
```

---

## 常见问题

**Q: 编译一篇 PDF 需要多久？**
取决于 LLM 响应速度，通常 2-5 分钟/篇。

**Q: 支持多大的 PDF？**
大型 PDF 会自动分块处理（每块最大 240KB），不限文件大小。

**Q: 可以用免费的本地模型吗？**
可以，安装 Ollama 后下载模型即可，无需 API Key。

**Q: 编译后的文章在哪里？**
在 `wiki/` 目录下，按类别分为 `concepts/`、`tools/`、`research/`、`tutorials/`。

**Q: 如何在 Obsidian 中查看？**
打开 Obsidian → 选择 `llm-wiki` 目录作为 Vault → 直接浏览。

---

*Created by Steven Lian*
