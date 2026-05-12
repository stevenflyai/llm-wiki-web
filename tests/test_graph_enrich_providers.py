"""Provider compatibility for tagline enrichment.

Tests both Anthropic and Azure AI Foundry shapes without hitting real APIs:
both providers go through config.call_llm(client, client_type, cfg, ...) —
ADR-002's unified entry — so we substitute a fake call_llm that branches on
client_type the same way the real one does.
"""
from __future__ import annotations

from graph_build import GraphData, GraphNode, enrich_taglines


def _fake_call_llm_routing(client, client_type, cfg, system, user, *, max_tokens):
    """Simulate the two provider paths without SDK deps."""
    if client_type == "anthropic":
        # real anthropic returns Message.content[0].text; real config.call_llm
        # collapses that to a str — we produce a str directly.
        return f"[anthropic-{max_tokens}] {user[:12]}"
    if client_type == "azure":
        # real azure returns choices[0].message.content
        return f"[azure-{max_tokens}] {user[:12]}"
    raise AssertionError(f"unexpected client_type: {client_type}")


def _node(nid: str, mtime: float) -> GraphNode:
    return GraphNode(
        id=nid, title=nid.split("/")[-1].removesuffix(".md"),
        category="concepts", last_updated="2026-05-01",
        source_mtime=mtime,
    )


def test_enrich_anthropic_path() -> None:
    g = GraphData(generated_at="", nodes=[_node("concepts/a.md", 1.0)], edges=[])
    enrich_taglines(
        g, prior_cache={},
        article_bodies={"concepts/a.md": "body a"},
        client=object(), client_type="anthropic", cfg=None,
        call_llm=_fake_call_llm_routing,
    )
    assert g.nodes[0].tagline is not None
    assert g.nodes[0].tagline.startswith("[anthropic-80]")
    assert g.nodes[0].source_mtime == 1.0


def test_enrich_azure_path() -> None:
    g = GraphData(generated_at="", nodes=[_node("concepts/a.md", 2.0)], edges=[])
    enrich_taglines(
        g, prior_cache={},
        article_bodies={"concepts/a.md": "body a"},
        client=object(), client_type="azure", cfg=None,
        call_llm=_fake_call_llm_routing,
    )
    assert g.nodes[0].tagline is not None
    assert g.nodes[0].tagline.startswith("[azure-80]")


def test_unchanged_mtime_hits_cache_on_both_providers() -> None:
    prior = {"concepts/a.md": {"tagline": "cached", "source_mtime": 7.0}}
    def make_spy(sink: list[str]):
        def spy(c, ct, cfg, s, u, *, max_tokens):  # pragma: no cover — we expect zero hits
            sink.append(ct)
            return "SHOULD_NOT_RUN"
        return spy

    for provider in ("anthropic", "azure"):
        g = GraphData(generated_at="", nodes=[_node("concepts/a.md", 7.0)], edges=[])
        sink: list[str] = []
        enrich_taglines(
            g, prior,
            article_bodies={"concepts/a.md": "body"},
            client=object(), client_type=provider, cfg=None,
            call_llm=make_spy(sink),
        )
        assert g.nodes[0].tagline == "cached"
        assert sink == [], f"provider={provider} should not have called LLM on cache hit"
