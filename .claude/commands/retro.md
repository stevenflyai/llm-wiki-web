# /retro — 会话结束的复盘归档

End-of-session retro. Sort what was learned into the right home.

## Step 1: Ask the user

> 这次会话有哪些值得保留的发现?分别属于哪一类?

## Step 2: Categorize

For each learning, classify and propose where it goes:

| 类型 | 去向 |
|---|---|
| 项目级开发约定 | `docs/dev/CLAUDE-DEV.md` |
| 架构决策 | `DECISIONS.md` (新 ADR,永不改老的) |
| 可复用工作流 | `.claude/commands/<name>.md` |
| Wiki 内容/格式规则 | 根目录 `CLAUDE.md` (运行时契约) |
| Bug + fix 模式 | `docs/lessons.md` |
| 已完成 SPEC 的事实 | `CHANGELOG.md` 的 `[Unreleased]` |

## Step 3: Propose, don't auto-commit

Show the user the proposed change for each file, **diff-style**.
Wait for approval before applying.

## Step 4: Check sizes

After applying:
- 如果 `docs/dev/CLAUDE-DEV.md` 超过 200 行 → 警告用户拆分
- 如果 `DECISIONS.md` 出现修改老 ADR 的尝试 → 拒绝,提示用 supersede
- 如果 `BACKLOG.md` 超过 50 项 → 建议清理一遍

## Step 5: PLAN.md state

如果 SPEC 还没完成,确认 `PLAN.md` 反映了真实进度。
如果 SPEC 已完成,确认:
- [ ] CHANGELOG 已追加
- [ ] SPEC 文件已 `git mv` 到 `archive/YYYY-MM-<slug>.md`
- [ ] `PLAN.md` 已清空或归档到 `archive/<slug>/PLAN.md`
