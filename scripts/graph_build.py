"""Build a structural graph of the wiki: nodes, edges, orphans, ghosts.

Input:  wiki/**/*.md
Output: dict-shaped GraphData ready to serialise to JSON.

Pure static parsing — the LLM is only invoked later, in enrich_taglines(),
for the per-node 1-liner summary.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "ArticleMetadata",
    "GraphData",
    "GraphEdge",
    "GraphNode",
    "build_graph",
    "enrich_taglines",
    "extract_wikilinks",
    "graph_to_json",
    "load_prior_cache",
    "parse_metadata",
    "run_graph_build",
]

# ── Parsing helpers ────────────────────────────────────────────────────────────

_WIKILINK_RE = re.compile(r"\[\[([^\]\n]+?)\]\]")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _strip_code(md: str) -> str:
    md = _FENCE_RE.sub("", md)
    md = _INLINE_CODE_RE.sub("", md)
    return md


def extract_wikilinks(content: str) -> list[str]:
    """Return [[target]] names (stripped of |alias and #heading), ignoring code blocks."""
    cleaned = _strip_code(content)
    targets: list[str] = []
    for match in _WIKILINK_RE.finditer(cleaned):
        raw = match.group(1).strip()
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            targets.append(target)
    return targets


@dataclass
class ArticleMetadata:
    category: str = "unknown"
    last_updated: str = ""
    related: list[str] = field(default_factory=list)


_CATEGORY_RE = re.compile(r"^\*\*类别\*\*\s*:\s*(\S.*?)\s*$", re.MULTILINE)
_UPDATED_RE = re.compile(r"^\*\*最后更新\*\*\s*:\s*(\S.*?)\s*$", re.MULTILINE)
_RELATED_RE = re.compile(r"^\*\*相关文章\*\*\s*:\s*(.*?)\s*$", re.MULTILINE)


def parse_metadata(content: str) -> ArticleMetadata:
    """Pull the three frontmatter fields this graph cares about."""
    meta = ArticleMetadata()
    if m := _CATEGORY_RE.search(content):
        val = m.group(1).strip()
        # Strip surrounding brackets like [concepts/tools/...] from the template
        if val.startswith("[") and val.endswith("]"):
            val = val.strip("[]").split("/")[0].strip()
        meta.category = val or "unknown"
    if m := _UPDATED_RE.search(content):
        meta.last_updated = m.group(1).strip()
    if m := _RELATED_RE.search(content):
        # related is a single line of [[A]], [[B|b]], ... — reuse the link extractor
        meta.related = extract_wikilinks(m.group(1))
    return meta


# ── Graph data model ──────────────────────────────────────────────────────────


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


EdgeKind = Literal["body_link", "related"]


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: EdgeKind


@dataclass
class GraphData:
    generated_at: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


# ── Build ─────────────────────────────────────────────────────────────────────


def _resolve_target(raw_target: str, stem_to_id: dict[str, str]) -> str:
    """[[flash-attention]] → 'tools/flash-attention.md' if known, else 'unknown/…md' (ghost)."""
    key = raw_target.strip().lower()
    if key in stem_to_id:
        return stem_to_id[key]
    return f"unknown/{raw_target.strip()}.md"


_SKIP_NAMES = {"INDEX.md", "LOG.md"}


def build_graph(wiki_dir: Path) -> GraphData:
    articles: dict[str, tuple[Path, str, ArticleMetadata]] = {}
    stem_to_id: dict[str, str] = {}

    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.name in _SKIP_NAMES:
            continue
        rel = md_file.relative_to(wiki_dir).as_posix()
        content = md_file.read_text(encoding="utf-8")
        meta = parse_metadata(content)
        articles[rel] = (md_file, content, meta)
        stem_to_id[md_file.stem.lower()] = rel

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    edge_keys: set[tuple[str, str, str]] = set()
    referenced: set[str] = set()

    def _add_edge(source: str, target: str, kind: EdgeKind) -> None:
        if target == source:
            return  # self-link
        key = (source, target, kind)
        if key in edge_keys:
            return  # dedupe (source, target, kind); parallel body_link+related still allowed
        edge_keys.add(key)
        edges.append(GraphEdge(source=source, target=target, kind=kind))
        referenced.add(source)
        referenced.add(target)

    for node_id, (path, content, meta) in articles.items():
        title = _extract_title(content) or path.stem
        nodes[node_id] = GraphNode(
            id=node_id,
            title=title,
            category=meta.category,
            last_updated=meta.last_updated,
            source_mtime=path.stat().st_mtime,
        )
        for raw in extract_wikilinks(content):
            _add_edge(node_id, _resolve_target(raw, stem_to_id), "body_link")
        for raw in meta.related:
            _add_edge(node_id, _resolve_target(raw, stem_to_id), "related")

    # Materialise ghost nodes for edge targets that aren't real articles
    for edge in edges:
        if edge.target not in nodes:
            nodes[edge.target] = GraphNode(
                id=edge.target,
                title=Path(edge.target).stem,
                category="ghost",
                last_updated="",
                ghost=True,
            )

    # Mark orphans — real nodes that never appear as edge source or target
    for node_id, node in nodes.items():
        if node.ghost:
            continue
        if node_id not in referenced:
            node.orphan = True

    return GraphData(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        nodes=list(nodes.values()),
        edges=edges,
    )


_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _extract_title(content: str) -> str | None:
    if m := _TITLE_RE.search(content):
        return m.group(1).strip()
    return None


# ── Serialisation ─────────────────────────────────────────────────────────────


def graph_to_json(graph: GraphData) -> str:
    return json.dumps(asdict(graph), ensure_ascii=False, indent=2)


def load_prior_cache(graph_json_path: Path) -> dict[str, dict[str, Any]]:
    """Return {node_id: {tagline, source_mtime}} from a prior graph.json. Safe on missing/corrupt."""
    try:
        raw = graph_json_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    cache: dict[str, dict[str, Any]] = {}
    for node in data.get("nodes", []):
        nid = node.get("id")
        if not nid:
            continue
        cache[nid] = {
            "tagline": node.get("tagline"),
            "source_mtime": node.get("source_mtime"),
        }
    return cache


# ── Tagline enrichment ────────────────────────────────────────────────────────

_TAGLINE_SYSTEM = (
    "你用一句不超过 30 个汉字的中文概括一篇 wiki 文章，用具体、简明的语言，"
    "不要加引号、不要用句号结尾。"
)


CallLLM = Callable[..., str]


def enrich_taglines(
    graph: GraphData,
    prior_cache: dict[str, dict[str, Any]],
    article_bodies: dict[str, str],
    client: object,
    client_type: str,
    cfg: object,
    *,
    call_llm: CallLLM,
    no_enrich: bool = False,
    on_failure: Callable[[str, Exception], None] | None = None,
) -> None:
    """Populate node.tagline in place. Skip ghost nodes and cache hits (by source_mtime)."""
    for node in graph.nodes:
        if node.ghost:
            continue
        cached = prior_cache.get(node.id)
        if (
            cached is not None
            and cached.get("source_mtime") == node.source_mtime
            and cached.get("tagline")
        ):
            node.tagline = cached["tagline"]
            continue
        if no_enrich:
            # keep any pre-existing cached tagline even if mtime mismatched — never wipe
            if cached is not None and cached.get("tagline"):
                node.tagline = cached["tagline"]
            continue
        body = article_bodies.get(node.id, "")
        user_prompt = f"文章标题: {node.title}\n\n文章正文:\n{body[:4000]}"
        try:
            raw = call_llm(
                client, client_type, cfg,
                _TAGLINE_SYSTEM, user_prompt,
                max_tokens=80,
            )
            node.tagline = (raw or "").strip() or None
        except Exception as exc:  # noqa: BLE001 — per-node isolation, keep build going
            node.tagline = None
            if on_failure is not None:
                on_failure(node.id, exc)


# ── Orchestrator ──────────────────────────────────────────────────────────────


def run_graph_build(
    wiki_dir: Path,
    output_dir: Path,
    *,
    client: object | None = None,
    client_type: str = "",
    cfg: object | None = None,
    call_llm: CallLLM | None = None,
    no_enrich: bool = False,
    on_tagline_failure: Callable[[str, Exception], None] | None = None,
) -> GraphData:
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_json_path = output_dir / "graph.json"
    prior = load_prior_cache(graph_json_path)
    graph = build_graph(wiki_dir)

    if client is not None and call_llm is not None:
        article_bodies: dict[str, str] = {}
        for node in graph.nodes:
            if node.ghost:
                continue
            path = wiki_dir / node.id
            if path.exists():
                article_bodies[node.id] = path.read_text(encoding="utf-8")
        enrich_taglines(
            graph, prior, article_bodies, client, client_type, cfg,
            call_llm=call_llm,
            no_enrich=no_enrich,
            on_failure=on_tagline_failure,
        )
    elif no_enrich:
        # even with no client, carry forward prior cached taglines
        for node in graph.nodes:
            if node.ghost:
                continue
            cached = prior.get(node.id)
            if cached is not None and cached.get("tagline"):
                node.tagline = cached["tagline"]

    graph_json_path.write_text(graph_to_json(graph), encoding="utf-8")
    return graph
