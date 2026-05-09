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

| #     | 标题                              | 状态     | 日期       |
|-------|-----------------------------------|----------|------------|
| 001   | (示例) 不使用向量数据库            | Accepted | 2026-04-05 |

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

<!--
后续 ADR 在此追加,使用以下模板:

## ADR-XXX: [简短标题]

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-XXX

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
