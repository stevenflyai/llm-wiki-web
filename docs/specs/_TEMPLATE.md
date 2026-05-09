# SPEC: [功能名]

**Slug:** feature-slug
**Created:** YYYY-MM-DD
**Status:** Draft <!-- Draft | Approved | Active | Done | Archived -->
**Owner:** Steven
**Related ADRs:** _(填写编号,如 ADR-002)_
**Related BACKLOG entry:** _(原想法在 BACKLOG.md 里的描述)_

---

## Problem

为什么需要这个功能?触发条件是什么?当前痛点是什么?

## Goals

必须达到的行为或可验证指标。**这一节是验收的核心。**

- 目标 1
- 目标 2

## Non-Goals

明确不做的事。这一节防止 scope creep 和与现有 ADR 冲突。

- 不做 X (违反 ADR-001)
- 不做 Y (留给后续版本)

## User Story

作为 [角色],我想 [操作],以便 [价值]。

例:
> 作为知识库使用者,我想运行 dedup 命令检测重复 wiki 文章,
> 以便保持 INDEX.md 简洁、避免信息冗余。

## Acceptance Criteria

完成此 SPEC 的硬性条件。**勾完才算 Done。**

- [ ] CLI: `python -m llm_wiki.xxx --vault ./vault [args]` 可执行
- [ ] 输出文件位置和格式符合规范
- [ ] 测试覆盖三种典型场景(成功 / 边界 / 错误)
- [ ] `mypy` `ruff check` 通过
- [ ] CHANGELOG.md `[Unreleased]` 已追加条目
- [ ] 如有架构决策,DECISIONS.md 已新增 ADR
- [ ] 如有 schema 变化,运行时 CLAUDE.md 已同步

---

## Provider Compatibility

本功能在哪些 LLM provider 下需要工作?**所有勾选项都必须有测试覆盖。**

- [ ] OpenAI (gpt-4o, gpt-5)
- [ ] Anthropic (Claude Opus / Sonnet)
- [ ] Azure AI Foundry
- [ ] DeepSeek
- [ ] Ollama (本地: Gemma 4, Llama 3.1)

如果某 provider 不支持,在 Non-Goals 显式说明原因。

---

## Wiki Schema Impact

> 这是本项目独有的 section。任何改动 wiki 内容/格式的功能都要填。

- [ ] 是否改变 wiki 文章 frontmatter? **是 → 需同步更新运行时 CLAUDE.md**
- [ ] 是否改变 INDEX.md 结构? **是 → 需同步**
- [ ] 是否改变 LOG.md 格式? **是 → 需同步**
- [ ] 是否引入新目录(如 wiki/xxx/)? **是 → 需同步**
- [ ] 是否影响 `_meta/compile_state.json` schema? **是 → 需提供迁移脚本**

迁移说明(如果有):

---

## Design Notes

简单功能此节可省略。
跨 3+ 模块或引入新抽象时,引用 `docs/design/<name>.md`。

```
[组件 A] --(调用)--> [组件 B]
                         |
                         v
                    [新组件 C]
```

---

## Failure Modes

可能出错的地方以及处理策略。

| 失败场景 | 处理方式 |
|---|---|
| LLM 超时 | 重试 3 次后 fail,记录到 LOG.md |
| 文件冲突 | 不自动覆盖,生成 .conflict 文件等待人工处理 |
| Provider quota 耗尽 | fail-fast,提示切换 provider |

---

## Test Strategy

- **单元测试:** 哪些函数 / 哪些场景
- **集成测试:** 是否需要真 LLM 调用?(默认: mock,用 cassette/fixture)
- **手动测试:** 用 fixtures 里的 vault 跑一次端到端

---

## Open Questions

> Approved 之前必须清空此节。每个问题要么有答案,要么进 Non-Goals。

- ❓ 待回答的问题 1
- ❓ 待回答的问题 2

---

## Out of Scope

显式标记后续版本再做的事。这是 BACKLOG 候选。

- 后续可能做的扩展 1 → 加回 BACKLOG.md

---

## Approval Log

记录 SPEC 状态流转的时间戳。文件**移动**到对应目录时同时记录。

- YYYY-MM-DD: Drafted (in `docs/specs/draft/`)
- YYYY-MM-DD: Approved (moved to `docs/specs/approved/`)
- YYYY-MM-DD: Started (moved to `docs/specs/active/`)
- YYYY-MM-DD: Completed (moved to `docs/specs/archive/YYYY-MM-<slug>.md`)
