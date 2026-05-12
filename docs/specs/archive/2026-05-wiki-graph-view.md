# SPEC: Wiki 知识图谱 Web 视图

**Slug:** wiki-graph-view
**Created:** 2026-05-11
**Status:** Approved
**Owner:** Steven
**Related ADRs:** ADR-001 (no vector DB), ADR-004 (Markdown is DB), ADR-007 (Obsidian frontend), ADR-009 (FastAPI) — 并将新增一条 ADR（见 Design Notes）
**Related BACKLOG entry:** "Wiki 知识图谱 Web 视图"（2026-05-11 添加）

---

## Problem

目前 Wiki 的结构（文章之间的 `[[wikilinks]]` 关系、类别聚集、孤立条目、悬空引用）只能通过 Obsidian 的 graph view 观察。这带来两个痛点：

1. **分享困难。** Obsidian 是本地桌面软件（ADR-007），访客若想看到知识库的形状，必须安装 Obsidian 并打开 vault。对于打算公开分享的知识库，这形同于无。
2. **入口不统一。** 项目已有 FastAPI Web UI 承担 compile / query / lint 操作（ADR-009），但它是一个纯文字的控制面板，浏览者只能看任务输出，无法感知"这个知识库长什么样"。

触发条件：用户希望向他人展示知识库，意识到 Web UI 缺一个"一眼看懂整体结构"的入口。

## Goals

- G1: 在现有 FastAPI 应用中新增只读路由 `/graph`，任何能访问 Web UI 的人都能看到当前 Wiki 的图谱，无需安装 Obsidian。
- G2: 图谱必须能渲染三类关系：
  - 文章正文中的 `[[wikilinks]]`（实线边）
  - 文章 frontmatter `**相关文章**:` 字段里的链接（权重可区别于正文边）
  - 类别（concepts / tools / research / tutorials）作为节点颜色/聚簇，**不**渲染成成对边
- G3: 图谱页支持以下交互：点击节点打开文章、悬停显示 tooltip（标题 / 类别 / 最后更新）、按类别过滤、文本搜索聚焦。
- G4: 孤立文章（0 条边）与悬空链接（`[[不存在的文章]]`，渲染为 ghost 节点）可见，以便暴露知识空缺。
- G5: 图谱工件在每次 `compile` 结束时重新生成，落到 `output/graph/graph.json` + `output/graph/index.html`；`/graph` 路由读取这份工件。
- G6: 每篇文章附带 1 行 LLM 生成的 tagline 作为 tooltip 内容；**增量**生成，仅对新增/修改过的文章调用 LLM，缓存进 `graph.json`。

## Non-Goals

- ❌ 不做节点数量上限 / 虚拟化渲染。当前阶段 vault 规模远小于会让 Cytoscape 卡顿的量级；超过后作为后续 SPEC。
- ❌ 不把 `raw/` 下的原始资料渲染为叶子节点。图谱只看 `wiki/`，原始引用仍保留在文章内部。
- ❌ 不引入 embedding / 语义相似度推断边（坚守 ADR-001）。
- ❌ 不允许从 `/graph` 页面反向修改 wiki（拖拽改连线等）。编辑权仍属 Obsidian（ADR-007）。
- ❌ v1 不支持 OpenAI / DeepSeek / Ollama 的 tagline 生成测试矩阵（见 Provider Compatibility）。

## User Story

作为 Wiki 拥有者，我想打开浏览器访问 `/graph` 就能向访客展示我的知识库结构，点击任意节点就能直达对应文章，以便把 LLM 编译出来的知识以"可漫游的图"形式呈现给没有 Obsidian 的人。

## Acceptance Criteria

- [ ] `app/routes/graph.py` 新模块，挂到 `app/main.py`；`GET /graph` 返回 200 + HTML
- [ ] `GET /graph/data.json` 返回 `output/graph/graph.json` 的内容（JSON API）
- [ ] 图谱构建模块 `llm_wiki/graph.py`（或等效位置）可被 `scripts/compile.py` 在编译末尾调用，产出 `output/graph/graph.json` + `output/graph/index.html`
- [ ] 图谱构建是纯静态解析：从 `wiki/*.md` 提取 `[[wikilinks]]`、`**相关文章**:`、`**类别**:`、`**最后更新**:` 四个字段
- [ ] 边类型至少包含：`body_link`（来自正文 `[[]]`）、`related`（来自 frontmatter）；类别不产生边而是节点颜色
- [ ] 孤立节点出现在图中（可识别的单独簇/角落）；悬空 `[[X]]` 链接渲染为 ghost 节点（视觉上与实节点区分，例如虚线）
- [ ] 节点 tooltip 展示：标题 / 类别 / 最后更新日期 / tagline（若已生成）
- [ ] 交互：点击节点 → 跳转到对应文章的 Web UI 渲染视图；类别 legend 可切换可见性；搜索框输入字符能高亮匹配节点及其一跳邻域
- [ ] Tagline 生成走 `llm/client.py` 统一入口（ADR-002），不直接 import provider SDK
- [ ] Tagline 增量缓存：`graph.json` 为每篇文章存 `{ tagline, source_mtime }`；compile 时只对 mtime 变化的文章重算
- [ ] `--no-enrich` CLI flag 跳过 tagline 生成（用于 CI / 无 key 环境）
- [ ] `/graph` 在 `output/graph/graph.json` 不存在时，渲染空状态页，文案提示运行 `python -m llm_wiki.compile`；**不**回 500，**不**懒加载重建
- [ ] 单元测试：link-extraction（覆盖 `[[A]]` / `[[A|alias]]` / `[[A#heading]]`）
- [ ] 单元测试：`related_articles` frontmatter 解析（正常 / 缺失 / 格式错误）
- [ ] 集成测试：`tests/fixtures/vault_graph/` 下的小 vault → 跑 graph 构建 → 断言 `graph.json` 的 nodes / edges / orphans / ghosts
- [ ] Provider 矩阵：tagline 生成在 Anthropic 与 Azure AI Foundry 下有测试覆盖（cassette/fixture，不打真实 API）
- [ ] `mypy` `ruff check` 通过
- [ ] CHANGELOG.md `[Unreleased]` 追加条目
- [ ] DECISIONS.md 追加新 ADR（见 Design Notes）
- [ ] 运行时 CLAUDE.md **无需**同步（本功能不改 wiki schema；只新增 `output/graph/` 子目录，属临时输出）

---

## Provider Compatibility

Tagline 生成（G6）依赖 LLM。图谱本身（G1–G5）是纯静态解析，不受 provider 影响。v1 仅在下列 provider 下需测试覆盖 tagline 生成：

- [ ] OpenAI (gpt-4o, gpt-5) — **Non-Goal v1**（见下）
- [x] Anthropic (Claude Opus / Sonnet)
- [x] Azure AI Foundry
- [ ] DeepSeek — **Non-Goal v1**
- [ ] Ollama (Gemma 4, Llama 3.1) — **Non-Goal v1**

未选 provider 的原因：v1 聚焦 Steven 当前实际使用的 Anthropic + Azure 两条管线，先验证 tagline 质量与成本；其余 provider 留到 tagline 功能稳定后补齐测试矩阵，不在代码层面禁用它们（`call_llm()` 的抽象天然支持）。

---

## Wiki Schema Impact

- [ ] 是否改变 wiki 文章 frontmatter？**否。** 只读消费既有 `**类别**:` / `**最后更新**:` / `**相关文章**:`。
- [ ] 是否改变 INDEX.md 结构？**否。**
- [ ] 是否改变 LOG.md 格式？**否。** 但 compile 末尾应在 LOG.md 追加一行 `graph rebuilt (N nodes, M edges)` —— 这是 LOG.md 既有"记录重要操作"语义，不算格式变化。
- [ ] 是否引入新目录？**是（但不是 wiki/ 内）。** 新增 `output/graph/`，与既有 `output/queries/` / `output/slides/` / `output/charts/` 同级。属于临时输出，不影响运行时契约。
- [ ] 是否影响 `_meta/compile_state.json` schema？**否。** Tagline 缓存存在 `graph.json` 里，与 compile_state.json 无关。

迁移说明：无。首次 compile 自动产出 `output/graph/` 目录。

---

## Design Notes

### 架构图

```
scripts/compile.py
     └─(末尾调用)─> llm_wiki/graph/build.py
                          │
                          ├─ 解析 wiki/**/*.md → 静态节点/边
                          ├─ 读取已有 output/graph/graph.json 做 tagline 缓存命中
                          ├─ 对 mtime 变化的节点调用 llm/client.py 生成 tagline
                          └─ 写出 output/graph/graph.json + index.html

app/main.py
     └─ app/routes/graph.py
             ├─ GET /graph          → 渲染 HTML shell（含 cytoscape.js 引用）
             ├─ GET /graph/data.json → 回读 output/graph/graph.json
             └─ 若文件缺失 → 空状态页，不 500、不重建
```

### 数据模型（graph.json）

```json
{
  "generated_at": "2026-05-11T14:22:00Z",
  "nodes": [
    {
      "id": "concepts/attention.md",
      "title": "Attention 机制",
      "category": "concepts",
      "last_updated": "2026-05-03",
      "tagline": "自注意力如何让 token 关注彼此。",
      "source_mtime": 1715400000.0,
      "orphan": false,
      "ghost": false
    }
  ],
  "edges": [
    { "source": "concepts/attention.md", "target": "concepts/transformer.md", "kind": "body_link" },
    { "source": "concepts/transformer.md", "target": "tools/flash-attention.md", "kind": "related" }
  ]
}
```

### 新 ADR（待起草，与本 SPEC 同时落地）

**ADR-012: Wiki 知识图谱是基于 `[[wikilinks]]` 的静态衍生物，不做语义推断**

- Context：Obsidian 已提供 graph view（ADR-007），本项目新增 `/graph` 是为了给无 Obsidian 的访客提供公开可浏览的结构视图。需要明确"图从哪里来"。
- Decision：节点来源于 `wiki/**/*.md`；边只有两类——正文 `[[wikilinks]]` 与 frontmatter `**相关文章**:`；类别作为着色，不做成对边。禁止引入 embedding / LLM-ranked 边。Tagline 是节点属性，不是边。
- Consequences：(+) 规则确定性高、可 diff、可 lint；(+) 坚守 ADR-001（无向量化）；(−) 无法发现未显式链接的潜在关联，需由用户在文章里手动加 `[[link]]`。
- Related：ADR-001, ADR-004, ADR-007。

---

## Failure Modes

| 失败场景 | 处理方式 |
|---|---|
| `output/graph/graph.json` 不存在（首次使用 / 未 compile） | `/graph` 渲染空状态页，文案 "Graph not yet built. Run `python -m llm_wiki.compile` to generate."；HTTP 200 |
| `graph.json` 存在但 JSON 损坏 | 路由日志 structlog `error="graph_json_parse_failed"`；渲染空状态页；不 500 |
| Cytoscape CDN 不可达 | 本地 bundle `cytoscape.min.js` 至 `app/static/graph/`，不依赖外网 |
| Wiki 文章 frontmatter 格式错误（缺"类别"字段） | 节点仍加入图，`category` 置 `unknown`，以灰色渲染；不中断 build |
| `[[link]]` 指向不存在文章 | ghost 节点 + 虚线边；不中断 build |
| Tagline 生成 provider 报错 / 超时 | 单篇失败记录到 LOG.md，该节点 `tagline: null`；build 继续；下次 compile 再试 |
| `--no-enrich` 指定 | 跳过所有 LLM 调用；已有缓存 tagline 保留不清空 |
| compile 并发多次触发 | graph build 放在 compile 尾部，沿用既有 `_compile_lock`（ADR-005）的串行保证 |
| 图规模过大（≥ N 节点）致页面卡 | v1 不处理，列入 Out of Scope；后续 SPEC 加虚拟化/分级 |

---

## Test Strategy

- **单元测试：**
  - `tests/test_graph_links.py`：link-extraction 函数给定 fixture 文本，验证 `[[A]]` / `[[A|alias]]` / `[[A#heading]]` 三种形式都正确产出目标 id
  - `tests/test_graph_frontmatter.py`：`**相关文章**:` 行解析器处理正常 / 缺失 / 格式错误三种情况
- **集成测试：**
  - `tests/fixtures/vault_graph/` 下构造一个约 5 篇文章的小 vault（含 1 个孤立、1 个悬空链接、跨类别链接各 1），跑 graph build，断言 `graph.json` 的 nodes 数、edges 数、`orphan=true` 节点 id、`ghost=true` 节点 id
  - Tagline 生成用 cassette / fixture replay（Anthropic + Azure 各一份），断言生成内容写入 graph.json 且 mtime 未变时不再调用
  - **不**测真实 LLM API，不测真实网络
- **手动测试（合入前一次）：**
  - 用实际 vault 跑一次 `python -m llm_wiki.compile`，浏览器打开 `/graph`，用鼠标验证点击 / 悬停 / 过滤 / 搜索四类交互
  - 刻意删掉 `output/graph/graph.json`，验证空状态页
- **覆盖缺口（已知）：**
  - **没有** `GET /graph` 的 TestClient 冒烟测试。手动验证兜底。若后续 CI 担心路由注册漏挂，再补。

---

## Open Questions

_(无 —— Approved 的前置条件满足)_

---

## Out of Scope

以下明确推到后续版本（已同步到 BACKLOG 心态，暂未列入 BACKLOG.md，待 Approved 后补）：

- 节点数量上限与虚拟化渲染（规模问题）
- `raw/` 下原始资料作为叶子节点
- LLM 推断的语义边 / 聚类
- Git 历史时间轴动画（知识库演化可视化）
- `/graph` 反向编辑（拖拽连线 / 删除节点）
- Edge rationale（LLM 解释每条边为什么存在）
- OpenAI / DeepSeek / Ollama tagline 测试矩阵（代码不阻塞，仅测试覆盖延后）

---

## Approval Log

- 2026-05-11: Drafted (in `docs/specs/draft/`)
- 2026-05-11: Approved (moved to `docs/specs/approved/`)
