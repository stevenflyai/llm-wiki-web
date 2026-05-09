# LLM Wiki — 工程文档模板包

把这一整套文件按相对路径放到你的 `llm-wiki-web` 仓库根目录,即可启动 SPEC + ADR 工作流。

## 文件清单

```
.
├── BACKLOG.md                          ← 想法池
├── DECISIONS.md                        ← ADR 累积
├── CHANGELOG.md                        ← 发版事实
├── PLAN.md                             ← 当前活跃执行计划
├── docs/
│   ├── dev/
│   │   └── CLAUDE-DEV.md               ← 给 Claude Code 读的开发契约
│   ├── design/
│   │   └── README.md                   ← 何时写 design 文档
│   └── specs/
│       ├── README.md                   ← SPEC 状态机说明
│       ├── _TEMPLATE.md                ← SPEC 模板(每次新功能复制它)
│       ├── draft/                      ← (空目录)
│       ├── approved/                   ← (空目录)
│       ├── active/                     ← (空目录)
│       └── archive/                    ← (空目录)
└── .claude/
    └── commands/
        ├── new-feature.md              ← /new-feature 自定义命令
        └── retro.md                    ← /retro 自定义命令
```

## 安装步骤

1. 解压(或复制)所有文件到 `llm-wiki-web/` 仓库根目录
2. **不要覆盖**根目录已有的 `CLAUDE.md`(那是运行时契约,保留)
3. 编辑两份你需要个性化的文件:
   - `DECISIONS.md` — 把已经事实存在的 ADR 写进去(向量库选择、provider 抽象等)
   - `BACKLOG.md` — 把脑子里现在想做的功能扔进去
4. 把 `docs/specs/draft/`、`approved/`、`active/`、`archive/` 这四个空目录用 `.gitkeep` 占位:
   ```bash
   touch docs/specs/{draft,approved,active,archive}/.gitkeep
   ```
5. Commit:
   ```bash
   git add BACKLOG.md DECISIONS.md CHANGELOG.md PLAN.md docs/ .claude/
   git commit -m "Add SPEC + ADR workflow scaffolding"
   ```

## 第一个新功能怎么走

```
1. 在 BACKLOG.md 写一行想法
2. 在 Claude Code 输入: /new-feature
3. 跟着面试,产出 docs/specs/draft/<slug>.md
4. /clear,审 SPEC,清空 Open Questions
5. git mv 到 docs/specs/approved/
6. 决定开干 → git mv 到 docs/specs/active/
7. /clear,新会话进 Plan Mode 生成 PLAN.md
8. 注解 PLAN.md,循环到无歧义
9. /clear,新会话开始 Phase 1 实现
10. 完成所有 Phase → 追加 CHANGELOG → git mv SPEC 到 archive/YYYY-MM-<slug>.md
11. 会话结束跑 /retro 归档学习
```

## 关键纪律(再强调一遍)

- **同一时刻只一份活跃 SPEC** (active/ 通常只 1 个文件)
- **同一时刻只一份 PLAN.md** (根目录)
- **ADR 永不修改**,推翻只能新增 supersede
- **CLAUDE-DEV.md < 200 行**,膨胀就拆
- **状态变化 = git mv**,不靠改字段

## 与已有 CLAUDE.md 的关系

```
llm-wiki-web/
├── CLAUDE.md              ← 你已有的:运行时编译器契约(不动)
└── docs/dev/CLAUDE-DEV.md ← 新加的:Claude Code 开发契约
```

两份文档不冲突。Claude Code 读 `docs/dev/CLAUDE-DEV.md`;运行时 LLM agent 读根目录 `CLAUDE.md`。
