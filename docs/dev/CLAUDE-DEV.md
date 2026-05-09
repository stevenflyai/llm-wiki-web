# LLM Wiki — 项目开发契约 (for Claude Code)

> **这份文档与项目根目录的 `CLAUDE.md` 是不同的契约!**
>
> - 根目录 `CLAUDE.md` = **运行时编译器契约**,告诉 LLM agent 怎么 compile/query/lint wiki 内容
> - 本文档 = **项目开发契约**,告诉 Claude Code 怎么改 Python 代码、写 SPEC、维护项目
>
> 如果你是 Claude Code 来改代码的,先读这份。

---

## 入口指南

每次 Claude Code 新会话开始,按此顺序读取:

1. **本文件** (`docs/dev/CLAUDE-DEV.md`) — 开发规则
2. **`DECISIONS.md`** — 已有架构决策,改代码不能违反
3. **`PLAN.md`** (如果存在) — 当前正在做的事
4. **`docs/specs/active/`** — 当前活跃的 SPEC

不需要读:
- `CLAUDE.md` (那是运行时契约,你不是运行时)
- `wiki/`、`raw/` (那是用户内容,不是代码)

---

## WHAT — 项目快照

`llm-wiki-web`:个人知识库,把 LLM 当编译器,不用 RAG。

**Stack:**
- Python 3.11+ / FastAPI / Pydantic v2
- 多 LLM provider: OpenAI / Anthropic / Azure AI Foundry / DeepSeek / Ollama
- PDF 提取: 4 引擎 fallback (pypdf / pdfplumber / pymupdf / OCR)
- 前端: FastAPI 模板 + Obsidian (vault 直接被 Obsidian 打开)

**核心脚本:**
- `scripts/compile.py` — `raw/` → `wiki/`
- `scripts/query.py` — wiki 自然语言查询
- `scripts/lint.py` — 健康检查

---

## WHY — 不可触碰的设计红线

**改这些之前必须先 supersede 对应 ADR。**

- 不引入向量数据库 (ADR-001)
- `model_provider` 是一等抽象,业务代码不得 `if provider == "xxx"` (见 ADR-002)
- Markdown 是数据库,不引入 SQLite/JSON sidecar
- PDF 提取保持 4 引擎 fallback,不收敛到单一引擎
- Web UI 保持 streaming,不改成轮询
- Provider 配置走环境变量,不写进代码

---

## HOW — 命令与工作流

```bash
# 安装依赖
uv sync                              # 优先使用 uv

# 跑核心脚本
python -m llm_wiki.compile  --vault ./vault --provider anthropic
python -m llm_wiki.query    --vault ./vault "question"
python -m llm_wiki.lint     --vault ./vault --fix

# Web UI
uvicorn app.main:app --reload --port 8000

# 测试
pytest                               # 全套(慢)
pytest tests/test_compile.py -k pdf  # 单测,开发时优先用这个
ruff check . && ruff format --check .
mypy llm_wiki/
```

### 工作流纪律

- 开发时跑单测,不跑全套
- 完成前必须 `mypy` + `ruff` 通过
- 写到 `vault/` 只能通过测试 fixture,不能碰真实用户 vault
- 长任务走 `app/jobs/`,不阻塞 request handler

---

## Code Style

- Python 3.11+ 语法: `match`、`|` unions、`Self`
- 公共函数必须类型注解;跨边界数据用 Pydantic model
- 异常: 只抛 `llm_wiki/errors.py` 里的具体异常,禁用 `except Exception`
- 日志: 用 `structlog`,不用 `print`;key 用 snake_case
- 路径: `pathlib.Path`,禁用字符串拼接
- LLM 调用: 必须走 `llm/client.py`,禁止业务代码直接 import provider SDK

---

## 新功能工作流

详见 `docs/specs/README.md`。简版:

1. 想法 → `BACKLOG.md`
2. 决定要做 → 复制 `docs/specs/_TEMPLATE.md` 到 `docs/specs/draft/<slug>.md`,用 AskUserQuestion 面试用户填充
3. Open Questions 清空 → `git mv` 到 `approved/`
4. 决定开始 → `git mv` 到 `active/`,Plan Mode 生成 `PLAN.md`,注解循环
5. 实现期间产生新决策 → 追加 ADR 到 `DECISIONS.md`(永不修改老 ADR)
6. Acceptance Criteria 全勾 → 追加 `CHANGELOG.md`,`git mv` 到 `archive/YYYY-MM-<slug>.md`,清空 `PLAN.md`

---

## Session Retros

会话结束前,问:**"你在这次会话学到了什么?"**

把答案分门别类:

| 类型 | 去向 |
|---|---|
| 项目级约定 (例:所有 LLM 调用走缓存) | 本文件 |
| 架构选择 (例:换了相似度算法) | DECISIONS.md (新 ADR) |
| 可复用工作流 | `.claude/commands/` |
| Wiki 内容/格式约定 | 根目录 `CLAUDE.md` (运行时契约) |
| 项目特定 bug 模式 | `docs/lessons.md` |

**保持本文件 < 200 行。如果它在膨胀,说明有内容应该去别处。**

---

## 反模式 (踩过坑)

- ❌ 在业务代码里 `if provider == "openai"` (违反 ADR-002)
- ❌ 测试调真实 LLM API
- ❌ 提交 `vault/` 内容 (gitignored)
- ❌ 修改老 ADR (只能新增 supersede)
- ❌ "看起来跑通了" 就宣布完成 (Acceptance Criteria 没勾完不算完)
- ❌ 跨功能 PR 顺手 reformat 无关文件
