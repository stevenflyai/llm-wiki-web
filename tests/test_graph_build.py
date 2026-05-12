"""Integration test: build_graph over a small fixture vault."""
from __future__ import annotations

import json
from pathlib import Path

from graph_build import build_graph, graph_to_json, load_prior_cache

FIXTURE = Path(__file__).parent / "fixtures" / "vault_graph"


def test_nodes_are_materialised_for_real_articles_and_ghosts() -> None:
    g = build_graph(FIXTURE)
    ids = {n.id for n in g.nodes}
    assert "concepts/attention.md" in ids
    assert "concepts/transformer.md" in ids
    assert "tools/flash-attention.md" in ids
    assert "tutorials/isolated.md" in ids
    assert "research/scaling-laws.md" in ids
    # ghost materialised from [[ghost-target]] in transformer.md
    assert "unknown/ghost-target.md" in ids


def test_ghost_flag_set_only_on_missing_targets() -> None:
    g = build_graph(FIXTURE)
    by_id = {n.id: n for n in g.nodes}
    assert by_id["unknown/ghost-target.md"].ghost is True
    assert by_id["concepts/attention.md"].ghost is False


def test_orphan_flag_set_on_isolated_articles_only() -> None:
    g = build_graph(FIXTURE)
    orphan_ids = {n.id for n in g.nodes if n.orphan}
    assert orphan_ids == {"tutorials/isolated.md"}


def test_edge_kinds() -> None:
    g = build_graph(FIXTURE)
    triples = {(e.source, e.target, e.kind) for e in g.edges}
    # body-link edge from attention → transformer
    assert ("concepts/attention.md", "concepts/transformer.md", "body_link") in triples
    # related edge from attention → flash-attention (frontmatter)
    assert ("concepts/attention.md", "tools/flash-attention.md", "related") in triples
    # ghost edge
    assert (
        "concepts/transformer.md",
        "unknown/ghost-target.md",
        "body_link",
    ) in triples


def test_category_coloring_data_present() -> None:
    g = build_graph(FIXTURE)
    by_id = {n.id: n for n in g.nodes}
    assert by_id["concepts/attention.md"].category == "concepts"
    assert by_id["tools/flash-attention.md"].category == "tools"
    assert by_id["research/scaling-laws.md"].category == "research"
    assert by_id["tutorials/isolated.md"].category == "tutorials"
    assert by_id["unknown/ghost-target.md"].category == "ghost"


def test_json_roundtrip(tmp_path: Path) -> None:
    g = build_graph(FIXTURE)
    out = tmp_path / "graph.json"
    out.write_text(graph_to_json(g), encoding="utf-8")
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert "nodes" in parsed and "edges" in parsed and "generated_at" in parsed
    assert len(parsed["nodes"]) == len(g.nodes)
    assert len(parsed["edges"]) == len(g.edges)


def test_load_prior_cache_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_prior_cache(tmp_path / "nope.json") == {}


def test_load_prior_cache_malformed_json_returns_empty(tmp_path: Path) -> None:
    bad = tmp_path / "graph.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_prior_cache(bad) == {}


def test_load_prior_cache_extracts_tagline_and_mtime(tmp_path: Path) -> None:
    good = tmp_path / "graph.json"
    good.write_text(
        json.dumps({
            "nodes": [
                {"id": "a.md", "tagline": "hello", "source_mtime": 10.5},
                {"id": "b.md", "tagline": None, "source_mtime": None},
            ],
        }),
        encoding="utf-8",
    )
    cache = load_prior_cache(good)
    assert cache["a.md"] == {"tagline": "hello", "source_mtime": 10.5}
    assert cache["b.md"]["tagline"] is None
