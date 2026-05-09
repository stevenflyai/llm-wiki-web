# LLM Wiki 项目配置文件 (CLAUDE.md / AGENTS.md)

> 本文件是 Karpathy LLM Wiki 模式的核心配置，供 Claude Code / Codex 等 LLM Agent 读取。
> 每次启动新会话时，请先阅读此文件，然后阅读 `wiki/INDEX.md`。

---

## 项目概述

本项目是一个 **LLM 驱动的个人知识库**，灵感来自 Andrej Karpathy 的 LLM Knowledge Base 模式。

核心理念：
- LLM 作为"编译器"，将原始资料（`raw/`）编译成结构化的 Wiki（`wiki/`）
- Wiki 是"活的"知识库，会不断更新和自我修复
- 使用 Obsidian 作为前端界面，方便浏览和导航

---

## 目录结构

```
llm-wiki/
├── CLAUDE.md          # 本文件：项目配置与规则（Agent 必读）
├── raw/               # 原始资料（人工添加，不由 LLM 编辑）
│   ├── papers/        # 学术论文（.pdf 或转换后的 .md）
│   ├── articles/      # 文章、博客（.md）
│   ├── repos/         # 代码仓库笔记（.md）
│   └── images/        # 图片资源
├── wiki/              # LLM 编译生成的结构化 Wiki（主要由 LLM 维护）
│   ├── INDEX.md       # 所有 Wiki 文章的主索引（必须保持最新）
│   ├── LOG.md         # Wiki 演化日志（记录每次重要操作）
│   ├── concepts/      # 核心概念文章
│   ├── tools/         # 工具和框架文章
│   ├── research/      # 研究进展文章
│   └── tutorials/     # 教程和实践指南
├── output/            # 查询结果、幻灯片、图表（临时输出）
│   ├── queries/       # Q&A 查询结果
│   ├── slides/        # Marp 幻灯片
│   └── charts/        # Matplotlib 图表
├── _meta/             # 元数据、编译状态
│   └── compile_state.json
└── scripts/           # 辅助脚本
    ├── compile.py     # 编译脚本
    ├── query.py       # 查询脚本
    └── lint.py        # 健康检查脚本
```

---

## 会话启动协议

每次开始新会话时，按以下顺序操作：

1. **读取本文件** (`CLAUDE.md`) — 了解项目规则
2. **读取** `wiki/INDEX.md` — 了解现有知识库内容
3. **读取** `wiki/LOG.md` — 了解最近的变更历史
4. **确认任务** — 根据用户指令执行相应操作

---

## Wiki 文章规范

### 文章结构模板

每篇 Wiki 文章必须遵循以下格式：

```markdown
# [文章标题]

**类别**: [concepts/tools/research/tutorials]
**最后更新**: YYYY-MM-DD
**相关文章**: [[文章A]], [[文章B]]
**原始来源**: [来源文件名或URL]

---

## 概述
[2-3句话的简明摘要]

## 核心内容
[详细内容，使用小节组织]

### 子节1
...

### 子节2
...

## 关键要点
- 要点1
- 要点2
- 要点3

## 延伸阅读
- [[相关文章1]]
- [[相关文章2]]

## 原始来源引用
- `raw/papers/xxx.md` — 第X页
- `raw/articles/xxx.md`
```

### 反向链接规范

使用 Obsidian 双链格式 `[[文章名]]` 进行内部链接。
每篇文章的"相关文章"字段必须保持最新。

---

## 操作命令

### 编译操作 (Compile)
**触发词**: "编译"、"compile"、"更新 wiki"
**操作**:
1. 读取 `raw/` 下所有未处理的文件（检查 `_meta/compile_state.json`）
2. 对每个新文件：提取关键概念，更新或创建对应的 wiki 文章
3. 更新 `wiki/INDEX.md` 中的条目
4. 在 `wiki/LOG.md` 中记录本次编译
5. 更新 `_meta/compile_state.json`

### 查询操作 (Query)
**触发词**: "查询"、"问"、"query"、"解释"
**操作**:
1. 读取 `wiki/INDEX.md` 定位相关文章
2. 读取相关 wiki 文章
3. 综合信息生成回答
4. 将回答保存到 `output/queries/YYYYMMDD_[主题].md`

### 健康检查 (Lint)
**触发词**: "检查"、"lint"、"健康检查"、"health check"
**操作**:
1. 检查所有 wiki 文章的反向链接是否有效
2. 检查 INDEX.md 是否包含所有文章
3. 识别孤立文章（没有被任何文章引用）
4. 识别知识空缺（概念被提及但没有文章）
5. 生成健康报告保存到 `output/queries/lint_YYYYMMDD.md`

### 增强操作 (Enhance)
**触发词**: "增强"、"enhance"、"深化"
**操作**:
1. 选择需要深化的文章
2. 基于现有 wiki 内容添加更多细节、示例、联系
3. 确保与其他文章的链接完整

---

## LLM 行为规范

1. **永远不要直接编辑 `raw/` 目录** — 这是人工管理的输入区域
2. **Wiki 文章以增量方式更新** — 不要删除已有内容，只做追加和完善
3. **保持一致的术语** — 同一概念始终使用相同名称
4. **交叉引用** — 每次提到其他 wiki 中已有的概念时，使用 `[[]]` 链接
5. **引用来源** — 每个事实都应能追溯到 `raw/` 中的来源
6. **LOG.md 必须更新** — 每次重要操作后在 LOG.md 记录时间戳和操作摘要
7. **INDEX.md 必须同步** — 新建文章后立即更新 INDEX.md

---

## 知识领域定义

本知识库聚焦于以下领域（可根据实际需要扩展）：

- **大型语言模型 (LLM)** — 架构、训练、对齐、推理
- **AI Agent** — 规划、工具使用、多 Agent 系统
- **机器学习基础** — 优化、正则化、评估
- **AI 工具生态** — 框架、API、部署方案
- **研究前沿** — 最新论文、突破、趋势

---

## 元数据格式 (_meta/compile_state.json)

```json
{
  "last_compile": "YYYY-MM-DDTHH:MM:SS",
  "processed_files": ["raw/papers/xxx.md", ...],
  "total_wiki_articles": 0,
  "total_raw_files": 0,
  "wiki_word_count": 0
}
```

---

*本文件由项目初始化脚本自动生成，可由人工和 LLM 协作维护。*
*最后更新: 2025-04-05*
