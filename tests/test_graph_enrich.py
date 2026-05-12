"""Unit tests for tagline enrichment + cache + --no-enrich + failure isolation."""
from __future__ import annotations

from graph_build import GraphData, GraphNode, enrich_taglines


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []


def _record_call_llm(calls_sink: list[str]):
    def _call(client, client_type, cfg, system, user, *, max_tokens=0):
        calls_sink.append(user)
        return f"TAGLINE::{user[:20]}"
    return _call


def _make_graph(nodes: list[GraphNode]) -> GraphData:
    return GraphData(generated_at="", nodes=nodes, edges=[])


def test_enrich_skips_cached_nodes() -> None:
    prior = {
        "concepts/a.md": {"tagline": "老的 tagline", "source_mtime": 100.0},
    }
    nodes = [
        GraphNode(id="concepts/a.md", title="a", category="concepts",
                  last_updated="2026-05-01", source_mtime=100.0),
        GraphNode(id="concepts/b.md", title="b", category="concepts",
                  last_updated="2026-05-01", source_mtime=200.0),
    ]
    g = _make_graph(nodes)
    client = _FakeClient()
    sink: list[str] = []
    enrich_taglines(
        g, prior,
        article_bodies={"concepts/a.md": "body a", "concepts/b.md": "body b"},
        client=client, client_type="fake", cfg=None,
        call_llm=_record_call_llm(sink),
    )
    by_id = {n.id: n for n in g.nodes}
    assert by_id["concepts/a.md"].tagline == "老的 tagline"
    assert by_id["concepts/b.md"].tagline.startswith("TAGLINE::")
    assert len(sink) == 1  # only b hit the LLM


def test_enrich_refreshes_on_mtime_change() -> None:
    prior = {
        "concepts/a.md": {"tagline": "stale", "source_mtime": 100.0},
    }
    nodes = [
        GraphNode(id="concepts/a.md", title="a", category="concepts",
                  last_updated="2026-05-01", source_mtime=101.0),  # bumped
    ]
    g = _make_graph(nodes)
    sink: list[str] = []
    enrich_taglines(
        g, prior,
        article_bodies={"concepts/a.md": "body a"},
        client=_FakeClient(), client_type="fake", cfg=None,
        call_llm=_record_call_llm(sink),
    )
    assert g.nodes[0].tagline.startswith("TAGLINE::")
    assert len(sink) == 1


def test_no_enrich_flag_skips_all_llm_calls() -> None:
    nodes = [
        GraphNode(id="x.md", title="x", category="concepts",
                  last_updated="", source_mtime=1.0),
    ]
    g = _make_graph(nodes)
    sink: list[str] = []
    enrich_taglines(
        g, prior_cache={},
        article_bodies={"x.md": "body"},
        client=_FakeClient(), client_type="fake", cfg=None,
        call_llm=_record_call_llm(sink),
        no_enrich=True,
    )
    assert g.nodes[0].tagline is None
    assert sink == []


def test_no_enrich_preserves_existing_cache() -> None:
    prior = {"x.md": {"tagline": "cached", "source_mtime": 0.5}}
    nodes = [
        GraphNode(id="x.md", title="x", category="concepts",
                  last_updated="", source_mtime=1.0),  # mtime differs
    ]
    g = _make_graph(nodes)
    enrich_taglines(
        g, prior,
        article_bodies={"x.md": "body"},
        client=_FakeClient(), client_type="fake", cfg=None,
        call_llm=_record_call_llm([]),
        no_enrich=True,
    )
    assert g.nodes[0].tagline == "cached"


def test_ghost_nodes_never_get_tagline() -> None:
    nodes = [
        GraphNode(id="ghost.md", title="ghost", category="ghost",
                  last_updated="", source_mtime=None, ghost=True),
    ]
    g = _make_graph(nodes)
    sink: list[str] = []
    enrich_taglines(
        g, prior_cache={},
        article_bodies={},
        client=_FakeClient(), client_type="fake", cfg=None,
        call_llm=_record_call_llm(sink),
    )
    assert g.nodes[0].tagline is None
    assert sink == []


def test_llm_failure_leaves_tagline_null_and_invokes_on_failure() -> None:
    def boom(*a, **k):
        raise RuntimeError("provider exploded")

    failures: list[tuple[str, Exception]] = []
    nodes = [
        GraphNode(id="x.md", title="x", category="concepts",
                  last_updated="", source_mtime=1.0),
    ]
    g = _make_graph(nodes)
    enrich_taglines(
        g, prior_cache={},
        article_bodies={"x.md": "body"},
        client=_FakeClient(), client_type="fake", cfg=None,
        call_llm=boom,
        on_failure=lambda nid, exc: failures.append((nid, exc)),
    )
    assert g.nodes[0].tagline is None
    assert len(failures) == 1
    assert failures[0][0] == "x.md"
    assert isinstance(failures[0][1], RuntimeError)


def test_empty_llm_response_coerces_to_none() -> None:
    def empty(*a, **k):
        return "   "
    nodes = [
        GraphNode(id="x.md", title="x", category="concepts",
                  last_updated="", source_mtime=1.0),
    ]
    g = _make_graph(nodes)
    enrich_taglines(
        g, prior_cache={},
        article_bodies={"x.md": "body"},
        client=_FakeClient(), client_type="fake", cfg=None,
        call_llm=empty,
    )
    assert g.nodes[0].tagline is None
