"""Unit tests for frontmatter metadata parsing."""
from __future__ import annotations

from graph_build import parse_metadata


def test_full_metadata() -> None:
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


def test_missing_related() -> None:
    md = "# T\n\n**类别**: tools\n**最后更新**: 2026-05-01\n"
    meta = parse_metadata(md)
    assert meta.related == []
    assert meta.category == "tools"


def test_missing_category_defaults_to_unknown() -> None:
    md = "# T\n\n**最后更新**: 2026-05-01\n"
    meta = parse_metadata(md)
    assert meta.category == "unknown"


def test_malformed_related_line_yields_empty_list() -> None:
    md = "# T\n\n**相关文章**: not-a-link\n"
    meta = parse_metadata(md)
    assert meta.related == []


def test_template_placeholder_brackets_stripped() -> None:
    md = "# T\n\n**类别**: [concepts/tools]\n"
    meta = parse_metadata(md)
    assert meta.category == "concepts"


def test_empty_content() -> None:
    meta = parse_metadata("")
    assert meta.category == "unknown"
    assert meta.last_updated == ""
    assert meta.related == []
