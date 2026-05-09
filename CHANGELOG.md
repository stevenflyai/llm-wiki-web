# CHANGELOG

> 已发布功能的事实记录。遵循 [Keep a Changelog](https://keepachangelog.com/) 格式。
>
> **维护规则:**
> - 每次合并 PR / 完成 SPEC 时追加到 `[Unreleased]`
> - 发版时把 `[Unreleased]` 改为版本号 + 日期,新建空的 `[Unreleased]`
> - 引用相关 ADR 和 SPEC,方便回溯"为什么"

类型: `Added` `Changed` `Deprecated` `Removed` `Fixed` `Security`

---

## [Unreleased]

### Added
- _(尚无)_

### Changed
- _(尚无)_

### Fixed
- _(尚无)_

---

## [0.1.0] — YYYY-MM-DD

### Added
- 初始项目结构 (raw/ wiki/ output/ scripts/)
- compile.py / query.py / lint.py 三件套
- 多 provider 支持 (OpenAI, Anthropic, Azure, Ollama)。See ADR-002.
- 不引入向量数据库。See ADR-001.
