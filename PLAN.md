# PLAN — Wiki 知识图谱 Web 视图

**当前 SPEC:** `docs/specs/active/wiki-graph-view.md`
**Started:** 2026-05-11
**Target completion:** 2026-05-12

---

## Layout note (deviation from SPEC literal paths)

SPEC names `app/routes/graph.py` / `llm_wiki/graph/build.py` / `llm/client.py`. The repo is still flat-`scripts/` (no `app/`, no `llm_wiki/`). The SPEC itself says "或等效位置"; this plan maps spec paths → real paths:

| SPEC path | Real path used |
|---|---|
| `app/routes/graph.py` | `scripts/graph_routes.py` (FastAPI `APIRouter`, included in `scripts/app.py`) |
| `llm_wiki/graph/build.py` | `scripts/graph_build.py` |
| `llm/client.py` (ADR-002) | `scripts/config.py::call_llm` (already the unified entry) |
| `app/static/graph/` | `scripts/static/graph/` (new mount at `/static/graph`) |
| `python -m llm_wiki.compile` (in empty-state page) | `python scripts/compile.py` |

A whole-repo restructure to match CLAUDE-DEV.md's aspirational layout is a separate, larger SPEC. This plan does **not** do that restructure.

Acceptance criteria satisfied at their semantic level: router module exists and is mounted, graph builder module exists and is called from compile, LLM calls go through the single unified entry.

---

## Phase 1: Test infrastructure

**目标:** `pytest` runnable. `ruff check` / `mypy` scoped to new files only.

**任务:**
- [ ] **P1-1** Create `pyproject.toml` with `[project]`, `[tool.pytest.ini_options]`, `[tool.ruff]`, `[tool.mypy]`. Mypy `files = ["scripts/graph_build.py", "scripts/graph_routes.py"]` so existing untyped modules don't block.
- [ ] **P1-2** Create `tests/` + `tests/__init__.py` (empty) + `tests/conftest.py` adding `scripts/` to `sys.path`.
- [ ] **P1-3** Install dev deps: `pip install pytest ruff mypy`. Run `pytest --collect-only` to verify discovery.
- [ ] **P1-4** Commit: `chore: add pytest/ruff/mypy config + tests/ scaffold`.

**完成定义:**
- [ ] `pytest` exits 0 (no tests, but collects cleanly)
- [ ] `ruff check pyproject.toml tests/` passes
- [ ] Commit landed

---

## Phase 2: Static graph build

**目标:** `scripts/graph_build.py::build_graph(wiki_dir) -> GraphData` parses `wiki/**/*.md` into nodes/edges/orphans/ghosts. Pure, no LLM.

### Task 2-1: link extraction

**Files:** Create `scripts/graph_build.py`. Test `tests/test_graph_links.py`.

- [ ] Write failing test `test_graph_links.py`:

```python
from graph_build import extract_wikilinks

def test_plain_link():
    assert extract_wikilinks("see [[Attention]]") == ["Attention"]

def test_alias_link():
    assert extract_wikilinks("[[Attention|注意力]]") == ["Attention"]

def test_heading_link():
    assert extract_wikilinks("[[Attention#origins]]") == ["Attention"]

def test_multiple():
    assert extract_wikilinks("[[A]] and [[B|b]] and [[C#x]]") == ["A", "B", "C"]

def test_code_block_skipped():
    md = "```\n[[not-a-link]]\n```\n[[real]]"
    assert extract_wikilinks(md) == ["real"]

def test_no_links():
    assert extract_wikilinks("plain text") == []
```

- [ ] Run: `pytest tests/test_graph_links.py -v` → FAIL (module not found).
- [ ] Implement in `scripts/graph_build.py`:

```python
"""Graph build: parse wiki/**/*.md into nodes/edges/orphans/ghosts."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Literal

_WIKILINK_RE = re.compile(r"\[\[([^\]\n]+?)\]\]")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _strip_code(md: str) -> str:
    md = _FENCE_RE.sub("", md)
    md = _INLINE_CODE_RE.sub("", md)
    return md


def extract_wikilinks(content: str) -> list[str]:
    cleaned = _strip_code(content)
    targets: list[str] = []
    for match in _WIKILINK_RE.finditer(cleaned):
        raw = match.group(1).strip()
        # [[Target|alias]] -> Target;  [[Target#heading]] -> Target
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            targets.append(target)
    return targets
```

- [ ] Run: `pytest tests/test_graph_links.py -v` → PASS.
- [ ] Commit: `feat(graph): extract wikilinks from article body`.

### Task 2-2: frontmatter parsing

**Files:** `scripts/graph_build.py` (extend). Test `tests/test_graph_frontmatter.py`.

- [ ] Write failing test:

```python
from graph_build import parse_metadata

def test_full_metadata():
    md = """# Title

**类别**: concepts
**最后更新**: 2026-05-03
**相关文章**: [[Transformer]], [[FlashAttention|FA]]
**原始来源**: raw/papers/foo.md

## body
"""
    meta = parse_metadata(md)
    assert meta.category == "concepts"
    assert meta.last_updated == "2026-05-03"
    assert meta.related == ["Transformer", "FlashAttention"]

def test_missing_related():
    md = "# T\n\n**类别**: tools\n**最后更新**: 2026-05-01\n"
    meta = parse_metadata(md)
    assert meta.related == []
    assert meta.category == "tools"

def test_missing_category():
    md = "# T\n\n**最后更新**: 2026-05-01\n"
    meta = parse_metadata(md)
    assert meta.category == "unknown"

def test_malformed_related():
    md = "# T\n\n**相关文章**: not-a-link\n"
    meta = parse_metadata(md)
    assert meta.related == []
```

- [ ] Run: `pytest tests/test_graph_frontmatter.py -v` → FAIL.
- [ ] Extend `scripts/graph_build.py`:

```python
@dataclass
class ArticleMetadata:
    category: str = "unknown"
    last_updated: str = ""
    related: list[str] = field(default_factory=list)


_CATEGORY_RE = re.compile(r"^\*\*类别\*\*:\s*(\S.*?)\s*$", re.MULTILINE)
_UPDATED_RE = re.compile(r"^\*\*最后更新\*\*:\s*(\S.*?)\s*$", re.MULTILINE)
_RELATED_RE = re.compile(r"^\*\*相关文章\*\*:\s*(.*?)\s*$", re.MULTILINE)


def parse_metadata(content: str) -> ArticleMetadata:
    meta = ArticleMetadata()
    if m := _CATEGORY_RE.search(content):
        meta.category = m.group(1).strip() or "unknown"
    if m := _UPDATED_RE.search(content):
        meta.last_updated = m.group(1).strip()
    if m := _RELATED_RE.search(content):
        line = m.group(1)
        meta.related = extract_wikilinks(line)
    return meta
```

- [ ] Run: `pytest tests/test_graph_frontmatter.py -v` → PASS.
- [ ] Commit: `feat(graph): parse article frontmatter (category / updated / related)`.

### Task 2-3: build_graph core

**Files:** `scripts/graph_build.py` (extend). Test `tests/test_graph_build.py`, fixture `tests/fixtures/vault_graph/`.

- [ ] Create fixture vault — 5 articles:

```
tests/fixtures/vault_graph/
  concepts/
    attention.md        # links [[transformer]], related [[flash-attention]]
    transformer.md      # links [[attention]], [[ghost-target]]   ← ghost
  tools/
    flash-attention.md  # related [[attention]]
  tutorials/
    isolated.md         # no links, no related → orphan
  research/
    scaling-laws.md     # links [[transformer]]
```

Each article body:

```markdown
# Attention

**类别**: concepts
**最后更新**: 2026-05-03
**相关文章**: [[flash-attention]]

See [[transformer]] for the larger architecture.
```

(Repeat pattern for the rest — keep them minimal but honor the frontmatter template.)

- [ ] Write failing test:

```python
from pathlib import Path
from graph_build import build_graph

FIXTURE = Path(__file__).parent / "fixtures" / "vault_graph"

def test_build_graph_shapes():
    g = build_graph(FIXTURE)
    ids = {n.id for n in g.nodes}
    assert "concepts/attention.md" in ids
    assert "concepts/ghost-target.md" in ids  # ghost materialised
    ghost = next(n for n in g.nodes if n.id == "concepts/ghost-target.md")
    assert ghost.ghost is True
    orphan_ids = {n.id for n in g.nodes if n.orphan}
    assert "tutorials/isolated.md" in orphan_ids

def test_edge_kinds():
    g = build_graph(FIXTURE)
    kinds = {(e.source, e.target, e.kind) for e in g.edges}
    assert ("concepts/attention.md", "concepts/transformer.md", "body_link") in kinds
    assert ("concepts/attention.md", "tools/flash-attention.md", "related") in kinds
```

- [ ] Run: FAIL.
- [ ] Implement:

```python
@dataclass
class GraphNode:
    id: str
    title: str
    category: str
    last_updated: str
    tagline: str | None = None
    source_mtime: float | None = None
    orphan: bool = False
    ghost: bool = False


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: Literal["body_link", "related"]


@dataclass
class GraphData:
    generated_at: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


def _resolve_target(raw_target: str, stem_to_id: dict[str, str]) -> str:
    """[[flash-attention]] → 'tools/flash-attention.md' if known, else 'unknown/flash-attention.md'."""
    key = raw_target.strip().lower()
    if key in stem_to_id:
        return stem_to_id[key]
    return f"unknown/{raw_target.strip()}.md"


def build_graph(wiki_dir: Path) -> GraphData:
    from datetime import datetime, timezone

    articles: dict[str, tuple[Path, str, ArticleMetadata]] = {}
    stem_to_id: dict[str, str] = {}

    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.name in ("INDEX.md", "LOG.md"):
            continue
        rel = md_file.relative_to(wiki_dir).as_posix()
        content = md_file.read_text(encoding="utf-8")
        meta = parse_metadata(content)
        articles[rel] = (md_file, content, meta)
        stem_to_id[md_file.stem.lower()] = rel

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    referenced: set[str] = set()

    for node_id, (path, content, meta) in articles.items():
        nodes[node_id] = GraphNode(
            id=node_id,
            title=path.stem,
            category=meta.category,
            last_updated=meta.last_updated,
            source_mtime=path.stat().st_mtime,
        )
        for raw in extract_wikilinks(content):
            tgt = _resolve_target(raw, stem_to_id)
            edges.append(GraphEdge(source=node_id, target=tgt, kind="body_link"))
            referenced.add(tgt)
            referenced.add(node_id)
        for raw in meta.related:
            tgt = _resolve_target(raw, stem_to_id)
            edges.append(GraphEdge(source=node_id, target=tgt, kind="related"))
            referenced.add(tgt)
            referenced.add(node_id)

    # Materialise ghost nodes for targets that aren't real articles
    for edge in edges:
        if edge.target not in nodes:
            nodes[edge.target] = GraphNode(
                id=edge.target,
                title=Path(edge.target).stem,
                category="ghost",
                last_updated="",
                ghost=True,
            )

    # Mark orphans
    for node_id, node in nodes.items():
        if node.ghost:
            continue
        if node_id not in referenced:
            # no outbound + no inbound
            node.orphan = True

    return GraphData(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        nodes=list(nodes.values()),
        edges=edges,
    )
```

- [ ] Run: `pytest tests/test_graph_build.py -v` → PASS.
- [ ] Commit: `feat(graph): build_graph produces nodes/edges/orphans/ghosts`.

### Task 2-4: serialisation

- [ ] Add `graph_to_json(graph: GraphData) -> str` using `dataclasses.asdict` + `json.dumps(..., ensure_ascii=False, indent=2)`. Add a 1-liner test that roundtrips.
- [ ] Commit: `feat(graph): serialise GraphData to JSON`.

---

## Phase 3: Tagline enrichment

**目标:** Incrementally LLM-generate a 1-line tagline per node, cached by `source_mtime`, via `config.call_llm`. `--no-enrich` skips all LLM calls.

### Task 3-1: enrich function with cache

**Files:** `scripts/graph_build.py` (extend). Test `tests/test_graph_enrich.py`.

- [ ] Write failing test (fake LLM):

```python
from graph_build import GraphData, GraphNode, enrich_taglines

class FakeClient:
    def __init__(self):
        self.calls = []

def fake_call(client, client_type, cfg, system, user, *, max_tokens=0):
    client.calls.append(user)
    return f"TAGLINE[{user[:20]}]"

def test_enrich_skips_cached(monkeypatch):
    prior = {
        "concepts/a.md": {"tagline": "old", "source_mtime": 100.0},
    }
    now_nodes = [
        GraphNode(id="concepts/a.md", title="a", category="concepts",
                  last_updated="2026-05-01", source_mtime=100.0),  # unchanged
        GraphNode(id="concepts/b.md", title="b", category="concepts",
                  last_updated="2026-05-01", source_mtime=200.0),  # new
    ]
    g = GraphData(generated_at="", nodes=now_nodes, edges=[])
    client = FakeClient()
    article_bodies = {"concepts/a.md": "body a", "concepts/b.md": "body b"}
    enrich_taglines(g, prior, article_bodies, client, "fake", cfg=None,
                    call_llm=fake_call)
    by_id = {n.id: n for n in g.nodes}
    assert by_id["concepts/a.md"].tagline == "old"
    assert by_id["concepts/b.md"].tagline.startswith("TAGLINE[")
    assert len(client.calls) == 1  # only b

def test_no_enrich_flag(monkeypatch):
    nodes = [GraphNode(id="x.md", title="x", category="concepts",
                       last_updated="", source_mtime=1.0)]
    g = GraphData(generated_at="", nodes=nodes, edges=[])
    client = FakeClient()
    enrich_taglines(g, {}, {"x.md": "body"}, client, "fake", cfg=None,
                    call_llm=fake_call, no_enrich=True)
    assert g.nodes[0].tagline is None
    assert client.calls == []

def test_llm_failure_leaves_null(monkeypatch):
    def boom(*a, **k): raise RuntimeError("nope")
    nodes = [GraphNode(id="x.md", title="x", category="concepts",
                       last_updated="", source_mtime=1.0)]
    g = GraphData(generated_at="", nodes=nodes, edges=[])
    enrich_taglines(g, {}, {"x.md": "body"}, FakeClient(), "fake", cfg=None,
                    call_llm=boom)
    assert g.nodes[0].tagline is None  # build continues
```

- [ ] Run: FAIL.
- [ ] Implement:

```python
_TAGLINE_SYSTEM = (
    "You write a single Chinese sentence (≤ 30 characters) summarising a wiki article "
    "in plain, concrete language. No quotes, no trailing period required."
)


def enrich_taglines(
    graph: GraphData,
    prior_cache: dict[str, dict],
    article_bodies: dict[str, str],
    client: object,
    client_type: str,
    cfg: object,
    *,
    call_llm,  # callable (client, client_type, cfg, system, user, *, max_tokens)
    no_enrich: bool = False,
    on_failure=None,  # callable(node_id, exc) → None
) -> None:
    """In-place: set node.tagline. Skip unchanged mtime. Swallow per-node errors."""
    for node in graph.nodes:
        if node.ghost:
            continue
        cached = prior_cache.get(node.id)
        if (
            cached
            and cached.get("source_mtime") == node.source_mtime
            and cached.get("tagline")
        ):
            node.tagline = cached["tagline"]
            continue
        if no_enrich:
            if cached and cached.get("tagline"):
                node.tagline = cached["tagline"]
            continue
        body = article_bodies.get(node.id, "")
        user = f"文章标题: {node.title}\n\n文章正文:\n{body[:4000]}"
        try:
            node.tagline = call_llm(
                client, client_type, cfg,
                _TAGLINE_SYSTEM, user,
                max_tokens=80,
            ).strip()
        except Exception as exc:  # noqa: BLE001 — per-node isolation
            node.tagline = None
            if on_failure is not None:
                on_failure(node.id, exc)
```

- [ ] Run: PASS.
- [ ] Commit: `feat(graph): incremental tagline enrichment with mtime cache`.

### Task 3-2: load prior cache from existing graph.json

- [ ] Add `load_prior_cache(graph_json_path: Path) -> dict[str, dict]`: reads existing file, returns `{node.id: {tagline, source_mtime}}`. Returns `{}` on FileNotFoundError or json.JSONDecodeError.
- [ ] Unit-test both the happy path and the malformed-JSON path.
- [ ] Commit: `feat(graph): load tagline cache from prior graph.json`.

### Task 3-3: provider compatibility check (Anthropic + Azure)

**Files:** `tests/test_graph_enrich_providers.py`.

- [ ] Write provider-flavoured tests using fakes shaped like the two SDKs. Both go through `scripts/config.call_llm` with a client type string — the test passes a locally-defined fake `call_llm` that switches on `client_type` so we do **not** hit real SDKs or network:

```python
def fake_call_llm(client, client_type, cfg, system, user, *, max_tokens):
    if client_type == "anthropic":
        # mimic anthropic Message.content[0].text
        return f"[anthropic] {user[:12]}"
    if client_type == "azure":
        return f"[azure] {user[:12]}"
    raise AssertionError(client_type)

def test_enrich_anthropic(): ...
def test_enrich_azure(): ...
```

Both tests build a small GraphData, run `enrich_taglines` with `client_type="anthropic"` (then `"azure"`), assert the tagline starts with the expected prefix and that `source_mtime` is written through.

- [ ] Run: PASS.
- [ ] Commit: `test(graph): anthropic + azure tagline enrichment coverage`.

---

## Phase 4: Wire into compile

**目标:** End of `scripts/compile.py` and `scripts/app.py::compile_wiki` regenerates `output/graph/graph.json`. Respect `--no-enrich`. Append one `LOG.md` line.

### Task 4-1: run_graph_build helper

**Files:** `scripts/graph_build.py` (extend).

- [ ] Add:

```python
def run_graph_build(
    wiki_dir: Path,
    output_dir: Path,
    *,
    client=None,
    client_type: str = "",
    cfg=None,
    call_llm=None,
    no_enrich: bool = False,
    on_tagline_failure=None,
) -> GraphData:
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_json = output_dir / "graph.json"
    prior = load_prior_cache(graph_json)
    graph = build_graph(wiki_dir)
    article_bodies = {
        n.id: (wiki_dir / n.id).read_text(encoding="utf-8")
        for n in graph.nodes
        if not n.ghost and (wiki_dir / n.id).exists()
    }
    if client is not None and call_llm is not None:
        enrich_taglines(
            graph, prior, article_bodies, client, client_type, cfg,
            call_llm=call_llm, no_enrich=no_enrich,
            on_failure=on_tagline_failure,
        )
    graph_json.write_text(graph_to_json(graph), encoding="utf-8")
    return graph
```

- [ ] Write 1 integration test: fixture vault → call run_graph_build twice; second call should re-use cache (no LLM hit on unchanged nodes).
- [ ] Commit: `feat(graph): run_graph_build orchestrator with cache`.

### Task 4-2: CLI integration (`scripts/compile.py`)

- [ ] At end of main compile flow (after `save_state`), call `run_graph_build`. Add `--no-enrich` CLI flag (argparse). Import lazily to avoid circular.
- [ ] Append one line to `LOG.md`: `graph rebuilt ({N} nodes, {M} edges)` via existing `append_log`.
- [ ] Manual run: `python scripts/compile.py --no-enrich` → `output/graph/graph.json` exists, no LLM calls.
- [ ] Commit: `feat(compile): rebuild graph.json at end of compile`.

### Task 4-3: Web compile integration (`scripts/app.py`)

- [ ] After `save_state(state)` in `_compile_worker`, call `run_graph_build(WIKI_DIR, PROJECT_ROOT/"output"/"graph", client=client, client_type=client_type, cfg=cfg, call_llm=cfg_call_llm, on_tagline_failure=lambda nid, exc: _emit({'type':'log','message':f'tagline failed {nid}: {exc}'}))`.
- [ ] Emit a single `{'type':'log','message':'Graph rebuilt (N nodes, M edges)'}` event.
- [ ] Commit: `feat(app): regenerate graph at end of SSE compile`.

---

## Phase 5: Frontend + routes

**目标:** `/graph` and `/graph/data.json` serve the artifact with a Cytoscape page. Empty state when missing.

### Task 5-1: vendor Cytoscape

- [ ] `mkdir -p scripts/static/graph && curl -L -o scripts/static/graph/cytoscape.min.js https://cdn.jsdelivr.net/npm/cytoscape@3.28.1/dist/cytoscape.min.js`
- [ ] Verify file > 200 KB and starts with `/*!`.
- [ ] Commit: `chore: vendor cytoscape.js for /graph page`.

### Task 5-2: graph.html template

**Files:** `scripts/templates/graph.html` (new).

- [ ] Build a single-file template mirroring the existing `index.html` theme (`:root` palette, fonts, shell). Include:
  - Header with title, "back to /" link, search box, category-legend toggles (`concepts / tools / research / tutorials / ghost`).
  - Full-viewport `<div id="cy">` area.
  - Bottom-right empty-state overlay `<div id="empty">` (hidden by default).
  - `<script src="/static/graph/cytoscape.min.js"></script>` + inline `<script>` that:
    1. `fetch('/graph/data.json')` — on 204 or missing file, show empty state.
    2. Build Cytoscape from nodes/edges:
       - Node style by `category` (color map), ghost nodes `border-style: dashed`, low opacity, label prefixed `(ghost) `.
       - Edge style: `body_link` solid, `related` dashed.
       - Layout: `cose` with modest `idealEdgeLength`.
    3. On `tap` of non-ghost node → `window.location.href = '/article/' + data.id` (stub for now; may redirect to existing article viewer; fallback to `/#` + id).
    4. Mouseover → tooltip `title · category · last_updated · tagline`.
    5. Search input filters: nodes whose title contains query and their 1-hop neighbors are highlighted; rest dimmed.
    6. Legend checkboxes hide/show category groups.
- [ ] Commit: `feat(graph): graph.html + Cytoscape client`.

### Task 5-3: routes module

**Files:** `scripts/graph_routes.py` (new).

- [ ] Implement:

```python
"""GET /graph and /graph/data.json — read-only viewer for output/graph/graph.json."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

log = logging.getLogger(__name__)


def build_router(project_root: Path, templates_dir: Path) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory=str(templates_dir))
    graph_json = project_root / "output" / "graph" / "graph.json"

    @router.get("/graph", response_class=HTMLResponse)
    async def graph_page(request: Request):
        exists = graph_json.exists()
        return templates.TemplateResponse(
            request=request,
            name="graph.html",
            context={"graph_exists": exists},
        )

    @router.get("/graph/data.json")
    async def graph_data():
        if not graph_json.exists():
            return JSONResponse({"error": "graph_not_built"}, status_code=404)
        try:
            return JSONResponse(json.loads(graph_json.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            log.error("graph_json_parse_failed", exc_info=exc)
            return JSONResponse({"error": "graph_json_parse_failed"}, status_code=500)

    return router
```

- [ ] Commit: `feat(graph): /graph and /graph/data.json routes`.

### Task 5-4: mount into app.py + static

**Files:** `scripts/app.py` (modify).

- [ ] After `templates = Jinja2Templates(...)` add:

```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(SCRIPTS_DIR / "static")), name="static")

from graph_routes import build_router as build_graph_router
app.include_router(build_graph_router(PROJECT_ROOT, SCRIPTS_DIR / "templates"))
```

- [ ] Smoke check: `python scripts/app.py` → `curl -s http://127.0.0.1:8000/graph | head -5` returns HTML, `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/graph/data.json` returns 404 (no build yet) — **NOT 500**, **NOT 200** on missing file per spec. Acceptable: 200 with empty state in HTML (spec says "HTTP 200" for the `/graph` page with empty state; the JSON endpoint can 404).
- [ ] Commit: `feat(app): mount /graph router and /static`.

---

## Phase 6: ADR + CHANGELOG + cleanup

### Task 6-1: ADR-012

- [ ] Append to `DECISIONS.md`:

```markdown

---

## ADR-012: Wiki 知识图谱是基于 [[wikilinks]] 的静态衍生物，不做语义推断

**Date:** 2026-05-11
**Status:** Accepted

**Context:**
Obsidian 已提供 graph view（ADR-007）；`/graph` 路由是给无 Obsidian 的访客提供公开可浏览的结构视图。
需要明确"图从哪里来"，避免未来有人提议引入 embedding 推断边。

**Decision:**
节点来源于 `wiki/**/*.md`；边只有两类——正文 `[[wikilinks]]` 与 frontmatter `**相关文章**:`；
类别作为着色，不做成对边。禁止引入 embedding / LLM-ranked 边。Tagline 是节点属性，不是边。

**Consequences:**
- (+) 规则确定性高、可 diff、可 lint。
- (+) 坚守 ADR-001（无向量化）。
- (−) 无法发现未显式链接的潜在关联，需由用户在文章里手动加 `[[link]]`。

**Related:** ADR-001, ADR-004, ADR-007.
```

- [ ] Commit: `docs: ADR-012 static-derivation-only wiki graph`.

### Task 6-2: CHANGELOG

- [ ] Prepend to `CHANGELOG.md` under `## [Unreleased]`:

```markdown
### Added
- `/graph` route rendering an interactive Cytoscape view of the wiki knowledge graph (`[[wikilinks]]` + `related_articles`, coloured by category). Ghost nodes surface dangling links; orphans are visible.
- `scripts/graph_build.py` regenerates `output/graph/graph.json` at the end of every compile, with incremental LLM tagline enrichment cached by source mtime.
- `--no-enrich` flag on `scripts/compile.py` skips LLM tagline calls.
```

- [ ] Commit: `docs: CHANGELOG [Unreleased] — graph view`.

---

## Phase 7: Final checks

- [ ] `pytest -q` → all green
- [ ] `ruff check scripts/graph_build.py scripts/graph_routes.py tests/` → clean
- [ ] `mypy` (scoped to new files) → clean
- [ ] Manual: `python scripts/compile.py --no-enrich` (with empty wiki) → graph.json written with 0 nodes
- [ ] Manual: add one stub wiki article, re-run compile, `curl /graph/data.json` reflects it
- [ ] Manual: open `http://127.0.0.1:8000/graph`, verify empty-state fallback and legend toggles visually

---

## 注解 (Annotation cycle)

> If user annotates here before execution, address all notes and re-plan. Currently executing from this version.
