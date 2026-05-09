# docs/design/

架构设计文档。**只在跨 3+ 模块或引入新抽象时才写。**

## 什么时候需要 design 文档?

需要写:
- 新的核心抽象 (例如 `model_provider` 抽象层)
- 跨多个模块的数据流 (例如 compile → wiki → query 的端到端流程)
- 引入复杂依赖关系 (例如 4 引擎 PDF fallback 链)

不需要写:
- 单个函数的实现
- 简单的 CLI 工具
- bug fix

## 命名约定

主题清晰的名词短语,kebab-case:
```
provider-abstraction.md
compile-pipeline.md
web-ui-streaming-architecture.md
```

如果有图,放在同名目录或同级:
```
design/compile-pipeline.md
design/compile-pipeline.png
```

## 推荐结构

```markdown
# [设计标题]

**Created:** YYYY-MM-DD
**Related ADRs:** ADR-XXX
**Related SPECs:** specs/xxx.md

## Context
为什么需要这个设计?

## Components
有哪些组件,各自职责。

## Data Flow
数据如何流转。可用 ASCII 图、Mermaid 图、或外部图片。

## Key Decisions
关键设计选择,引用对应 ADR。

## Trade-offs
此设计的代价是什么?
```
