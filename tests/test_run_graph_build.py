"""End-to-end test for run_graph_build orchestrator: caches taglines between runs."""
from __future__ import annotations

import json
from pathlib import Path

from graph_build import run_graph_build

FIXTURE = Path(__file__).parent / "fixtures" / "vault_graph"


def test_run_graph_build_writes_graph_json_without_client(tmp_path: Path) -> None:
    out = tmp_path / "graph"
    run_graph_build(FIXTURE, out)
    path = out / "graph.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["nodes"]) >= 5  # 5 real articles + at least 1 ghost


def test_run_graph_build_reuses_cache_on_second_run(tmp_path: Path) -> None:
    out = tmp_path / "graph"
    call_log: list[str] = []

    def fake_call_llm(client, client_type, cfg, system, user, *, max_tokens):
        call_log.append(user)
        return f"tagline-{len(call_log)}"

    run_graph_build(
        FIXTURE, out,
        client=object(), client_type="anthropic", cfg=None,
        call_llm=fake_call_llm,
    )
    first_run_calls = len(call_log)
    assert first_run_calls > 0, "first run should enrich every non-ghost node"

    # Second run: no article mtimes changed → no LLM calls
    run_graph_build(
        FIXTURE, out,
        client=object(), client_type="anthropic", cfg=None,
        call_llm=fake_call_llm,
    )
    assert len(call_log) == first_run_calls, "second run should hit cache for all nodes"

    # Taglines are still present in the output
    data = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    real_nodes = [n for n in data["nodes"] if not n.get("ghost")]
    assert all(n["tagline"] is not None for n in real_nodes)


def test_no_enrich_skips_llm_even_with_client(tmp_path: Path) -> None:
    out = tmp_path / "graph"
    hits: list[str] = []

    def spy(*a, **k):  # pragma: no cover
        hits.append("called")
        return "tagline"

    run_graph_build(
        FIXTURE, out,
        client=object(), client_type="anthropic", cfg=None,
        call_llm=spy,
        no_enrich=True,
    )
    assert hits == []
    assert (out / "graph.json").exists()
