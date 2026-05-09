# docs/specs/

功能规格 (SPEC) 文件,按状态分目录管理。**用文件移动表示状态变化**,不靠改 status 字段。

## 状态机

```
   ┌─────────┐    ┌──────────┐    ┌────────┐    ┌─────────┐
   │  draft  │───>│ approved │───>│ active │───>│ archive │
   └─────────┘    └──────────┘    └────────┘    └─────────┘
       想法在写       讨论通过       正在实现      已完成归档
```

## 各目录用途

### `_TEMPLATE.md`
SPEC 模板。新建 SPEC 时:
```bash
cp docs/specs/_TEMPLATE.md docs/specs/draft/<feature-slug>.md
```

### `draft/`
正在起草、还有 Open Questions 没回答的 SPEC。可以同时存在多份。
**进入 approved 的条件:** Open Questions 清空,Provider Compatibility 与 Wiki Schema Impact 已勾选。

### `approved/`
已经讨论清楚但还没开始实现的 SPEC。这是"队列"。
**进入 active 的条件:** 你决定开始这个功能,且当前没有其他 active 的 SPEC。

### `active/`
**当前正在实现的 SPEC,通常只有 1 份(最多 2 份)。**
对应根目录的 `PLAN.md` 是这份 SPEC 拆出来的执行计划。
**进入 archive 的条件:** Acceptance Criteria 全部勾选,CHANGELOG 已追加。

### `archive/`
已完成的 SPEC,文件名加 `YYYY-MM-` 前缀方便排序:
```
archive/2026-04-pdf-fallback.md
archive/2026-05-dedup-compiler.md
```

## 命名约定

- slug 用 kebab-case,2-4 个词:`dedup-compiler.md`、`web-ui-streaming.md`
- 不要在文件名里塞版本号或状态(那是 git 和目录的事)
- 归档时**前面加 `YYYY-MM-` 前缀**

## 常用 git 命令

```bash
# 新建 SPEC
cp docs/specs/_TEMPLATE.md docs/specs/draft/dedup-compiler.md

# Approve (draft → approved)
git mv docs/specs/draft/dedup-compiler.md docs/specs/approved/

# Start (approved → active)
git mv docs/specs/approved/dedup-compiler.md docs/specs/active/

# Archive (active → archive,加日期前缀)
git mv docs/specs/active/dedup-compiler.md docs/specs/archive/2026-05-dedup-compiler.md
```
