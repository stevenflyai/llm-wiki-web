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

---

## [0.5] — 2026-05-12

### Added
- `/graph` route: interactive Cytoscape view of the wiki knowledge graph. Nodes are wiki articles (colored by category), edges are `[[wikilinks]]` in body (solid) and `**相关文章**:` frontmatter (dashed). Dangling links surface as ghost nodes; articles with no connections render as orphans. Supports hover tooltips, category legend filtering, and text-search highlighting. See ADR-012, SPEC wiki-graph-view.
- `scripts/graph_build.py`: static graph builder invoked at the end of every compile (CLI + SSE). Writes `output/graph/graph.json` with an LLM-generated 1-liner tagline per node. Taglines are incrementally cached by `source_mtime` — unchanged articles skip the LLM entirely.
- `--no-enrich` flag on `scripts/compile.py` skips all LLM tagline calls (CI / no-key environments). Existing cached taglines are preserved.
- Test infrastructure: `tests/` directory, `pyproject.toml` with pytest / ruff / mypy config, fixture vault under `tests/fixtures/vault_graph/`.

### Changed
- `scripts/app.py` now mounts `/static` and includes a `graph_routes` router.
- `/graph` view UX overhaul: switched layout from `cose` to `fcose` with `nodeDimensionsIncludeLabels: true` so node-spacing accounts for label geometry (resolves heavy label overlap on dense clusters). Labels render Obsidian-style — light text (`#d8dde6`) with thick outline, wrapping at 110px, all nodes labeled by default; top-degree hubs get a brighter, larger label for hierarchy. Added bottom-right zoom controls (`+` / `−` / `⊡`) with smooth animated transitions. Vendored `cytoscape-fcose` + `cose-base` + `layout-base` under `scripts/static/graph/`. Falls back to tuned `cose` parameters if the extension fails to load. See SPEC wiki-graph-view.

### Fixed
- _(尚无)_

---

## [0.1.0] — YYYY-MM-DD

### Added
- 初始项目结构 (raw/ wiki/ output/ scripts/)
- compile.py / query.py / lint.py 三件套
- 多 provider 支持 (OpenAI, Anthropic, Azure, Ollama)。See ADR-002.
- 不引入向量数据库。See ADR-001.
