"""Unit tests for [[wikilink]] extraction."""
from __future__ import annotations

from graph_build import extract_wikilinks


def test_plain_link() -> None:
    assert extract_wikilinks("see [[Attention]]") == ["Attention"]


def test_alias_link() -> None:
    assert extract_wikilinks("[[Attention|注意力]]") == ["Attention"]


def test_heading_link() -> None:
    assert extract_wikilinks("[[Attention#origins]]") == ["Attention"]


def test_multiple_links() -> None:
    assert extract_wikilinks("[[A]] and [[B|b]] and [[C#x]]") == ["A", "B", "C"]


def test_fenced_code_block_ignored() -> None:
    md = "```\n[[not-a-link]]\n```\n[[real]]"
    assert extract_wikilinks(md) == ["real"]


def test_inline_code_ignored() -> None:
    assert extract_wikilinks("the syntax `[[X]]` is used — but [[Real]] is real") == ["Real"]


def test_no_links() -> None:
    assert extract_wikilinks("plain text") == []


def test_empty_link_skipped() -> None:
    assert extract_wikilinks("[[]]") == []


def test_link_with_trailing_space() -> None:
    assert extract_wikilinks("[[  Attention  ]]") == ["Attention"]
