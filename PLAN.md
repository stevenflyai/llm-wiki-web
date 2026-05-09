# PLAN — 当前活跃执行计划

> **同一时刻只能有一份活跃 PLAN。**
> 切换功能时,要么删除此文件,要么把内容移到 `docs/specs/active/<feature>/PLAN.md`。
>
> 此文件由 SPEC 拆解而来,粒度细到"一段可独立测试的工作单元"。

---

**当前 SPEC:** _(填写 docs/specs/active/ 下的文件名)_
**SPEC link:** `docs/specs/active/xxx.md`
**Started:** YYYY-MM-DD
**Target completion:** YYYY-MM-DD

---

## Phase 1: [阶段名,例如 "Schema 与基础数据结构"]

**目标:** 一句话说明此阶段交付什么

**任务:**
- [ ] 任务 1 — 描述。验证方式:`pytest tests/xxx.py -k yyy`
- [ ] 任务 2 — 描述

**完成定义:**
- [ ] 单元测试通过
- [ ] `mypy` 无新增错误
- [ ] 代码已 commit

---

## Phase 2: [阶段名]

**目标:**

**任务:**
- [ ] _(待填充)_

**完成定义:**
- [ ] _(待填充)_

---

## Phase 3: [阶段名]

**目标:**

**任务:**
- [ ] _(待填充)_

---

## 注解 (Annotation cycle)

> 在 Plan Mode 下让 Claude Code 起草本文件后,
> 在此处或上面的任务行下用 `> NOTE:` 添加你的修正。
> 然后让 Claude 用守卫短语 "address all notes, don't implement yet" 修订。
> 重复直到无歧义,再开始执行。

示例:
> NOTE: Phase 1 任务 2 应使用 rapidfuzz,不是 fuzzywuzzy
> NOTE: 跨阶段假设错误,Phase 3 必须在 Phase 2 之前完成
