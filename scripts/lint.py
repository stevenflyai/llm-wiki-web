#!/usr/bin/env python3
"""
LLM Wiki 健康检查脚本 (lint.py)
===================================
扫描 wiki/ 目录，检查链接有效性、孤立文章、知识空缺等问题。

用法：
    python lint.py              # 运行完整健康检查
    python lint.py --fix        # 自动修复可修复的问题
    python lint.py --report     # 生成报告文件到 output/queries/

依赖：
    pip install rich
"""

__version__ = "0.1"
__author__ = "Steven Lian"

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    console = Console()
    RICH = True
except ImportError:
    class Console:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, *args): print("─" * 60)
    console = Console()
    RICH = False

WIKI_ROOT = Path(__file__).parent.parent
WIKI_DIR = WIKI_ROOT / "wiki"
OUTPUT_DIR = WIKI_ROOT / "output" / "queries"
INDEX_FILE = WIKI_DIR / "INDEX.md"
LOG_FILE = WIKI_DIR / "LOG.md"


def extract_links(content: str) -> list[str]:
    """提取文章中的 [[链接]]"""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def load_all_articles() -> dict[str, tuple[Path, str]]:
    """加载所有 wiki 文章 {文章名: (路径, 内容)}"""
    articles = {}
    for p in WIKI_DIR.rglob("*.md"):
        if p.name in ["INDEX.md", "LOG.md"]:
            continue
        try:
            content = p.read_text(encoding="utf-8")
            articles[p.stem] = (p, content)
        except Exception:
            pass
    return articles


def check_broken_links(articles: dict) -> list[dict]:
    """检查无效的 [[链接]]"""
    issues = []
    for article_name, (path, content) in articles.items():
        links = extract_links(content)
        for link in links:
            # 去掉管道符后的别名，如 [[文章名|显示名]] → 文章名
            target = link.split('|')[0].strip()
            if target not in articles and target not in ["INDEX.md", "LOG.md"]:
                issues.append({
                    "type": "broken_link",
                    "article": article_name,
                    "link": target,
                    "path": path
                })
    return issues


def check_orphan_articles(articles: dict) -> list[str]:
    """找到没有被任何文章引用的孤立文章"""
    referenced = set()
    for article_name, (path, content) in articles.items():
        links = extract_links(content)
        for link in links:
            referenced.add(link.split('|')[0].strip())

    # 检查 INDEX.md 中的引用
    if INDEX_FILE.exists():
        index_links = extract_links(INDEX_FILE.read_text(encoding="utf-8"))
        for link in index_links:
            referenced.add(link.split('|')[0].strip())

    orphans = []
    for name in articles:
        if name not in referenced:
            orphans.append(name)
    return orphans


def _has_metadata_field(content: str, field_name: str) -> bool:
    """检查文章是否包含指定元数据字段（兼容多种格式）。
    例如 field_name="类别" 匹配: **类别**, **类别：**, **类别**:, | 类别 |, | **类别** |
    """
    patterns = [
        f"**{field_name}**",     # **类别**
        f"**{field_name}：**",   # **类别：**（中文冒号在bold内）
        f"**{field_name}:**",    # **类别:**（英文冒号在bold内）
    ]
    return any(p in content for p in patterns)


def check_missing_metadata(articles: dict) -> list[dict]:
    """检查缺少必要元数据的文章"""
    issues = []
    required_fields = ["类别", "最后更新", "相关文章"]

    for article_name, (path, content) in articles.items():
        missing = []
        for field in required_fields:
            if not _has_metadata_field(content, field):
                missing.append(f"**{field}**")
        if missing:
            issues.append({
                "article": article_name,
                "missing": missing,
                "path": path
            })
    return issues


def check_knowledge_gaps(articles: dict) -> list[str]:
    """找到被引用但没有对应文章的知识空缺"""
    all_links = set()
    for article_name, (path, content) in articles.items():
        links = extract_links(content)
        for link in links:
            all_links.add(link.split('|')[0].strip())

    gaps = []
    for link in all_links:
        if link not in articles and link not in ["INDEX", "LOG"]:
            gaps.append(link)
    return gaps


def check_index_coverage(articles: dict) -> list[str]:
    """检查 INDEX.md 中未收录的文章"""
    if not INDEX_FILE.exists():
        return list(articles.keys())

    index_content = INDEX_FILE.read_text(encoding="utf-8")
    index_links = set(extract_links(index_content))

    uncovered = []
    for name in articles:
        if name not in index_links:
            uncovered.append(name)
    return uncovered


def generate_report(results: dict) -> str:
    """生成健康检查报告（Markdown 格式）"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_articles = results["total_articles"]

    lines = [
        f"# LLM Wiki 健康检查报告",
        f"",
        f"**检查时间**: {timestamp}",
        f"**总文章数**: {total_articles}",
        f"",
        f"---",
        f"",
        f"## 检查结果摘要",
        f"",
        f"| 检查项 | 状态 | 问题数 |",
        f"|--------|------|--------|",
        f"| 无效链接 | {'⚠️' if results['broken_links'] else '✅'} | {len(results['broken_links'])} |",
        f"| 孤立文章 | {'⚠️' if results['orphans'] else '✅'} | {len(results['orphans'])} |",
        f"| 缺少元数据 | {'⚠️' if results['missing_meta'] else '✅'} | {len(results['missing_meta'])} |",
        f"| 知识空缺 | {'ℹ️' if results['gaps'] else '✅'} | {len(results['gaps'])} |",
        f"| INDEX 未收录 | {'⚠️' if results['uncovered'] else '✅'} | {len(results['uncovered'])} |",
        f"",
    ]

    if results["broken_links"]:
        lines += [f"## ⚠️ 无效链接 ({len(results['broken_links'])} 个)", ""]
        for issue in results["broken_links"]:
            lines.append(f"- **{issue['article']}** 中引用了不存在的 `[[{issue['link']}]]`")
        lines.append("")

    if results["orphans"]:
        lines += [f"## ⚠️ 孤立文章 ({len(results['orphans'])} 个)", ""]
        for name in results["orphans"]:
            lines.append(f"- `{name}` — 没有任何文章引用此文章")
        lines.append("")

    if results["gaps"]:
        lines += [f"## ℹ️ 知识空缺 ({len(results['gaps'])} 个，建议新建这些文章)", ""]
        for gap in results["gaps"]:
            lines.append(f"- `[[{gap}]]` — 被引用但尚无对应文章")
        lines.append("")

    if results["missing_meta"]:
        lines += [f"## ⚠️ 缺少元数据 ({len(results['missing_meta'])} 个)", ""]
        for issue in results["missing_meta"]:
            lines.append(f"- **{issue['article']}** 缺少：{', '.join(issue['missing'])}")
        lines.append("")

    if results["uncovered"]:
        lines += [f"## ⚠️ INDEX 未收录 ({len(results['uncovered'])} 个)", ""]
        for name in results["uncovered"]:
            lines.append(f"- `[[{name}]]`")
        lines.append("")

    score = 100
    score -= len(results["broken_links"]) * 5
    score -= len(results["orphans"]) * 2
    score -= len(results["missing_meta"]) * 3
    score -= len(results["uncovered"]) * 2
    score = max(0, score)

    lines += [
        "---",
        "",
        f"## 健康评分",
        "",
        f"**总分：{score}/100**",
        "",
        f"{'🎉 知识库状态良好！' if score >= 90 else '⚠️ 建议修复以上问题以保持知识库质量'}",
        "",
        "*本报告由 LLM Wiki lint.py 自动生成*"
    ]

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM Wiki 健康检查")
    parser.add_argument("--report", "-r", action="store_true", help="保存报告到文件")
    parser.add_argument("--fix", action="store_true", help="自动修复可修复的问题")
    args = parser.parse_args()

    console.rule("[bold]LLM Wiki 健康检查[/bold]")

    # 加载所有文章
    articles = load_all_articles()
    console.print(f"\n扫描到 [bold]{len(articles)}[/bold] 篇 Wiki 文章\n")

    if not articles:
        console.print("[yellow]wiki/ 目录为空，请先运行 compile.py[/yellow]")
        return

    # 运行各项检查
    console.print("检查中...")
    broken_links = check_broken_links(articles)
    orphans = check_orphan_articles(articles)
    missing_meta = check_missing_metadata(articles)
    gaps = check_knowledge_gaps(articles)
    uncovered = check_index_coverage(articles)

    results = {
        "total_articles": len(articles),
        "broken_links": broken_links,
        "orphans": orphans,
        "missing_meta": missing_meta,
        "gaps": gaps,
        "uncovered": uncovered,
    }

    # 输出结果
    if RICH:
        table = Table(title="健康检查结果", box=box.ROUNDED)
        table.add_column("检查项", style="bold")
        table.add_column("状态")
        table.add_column("数量", justify="right")

        def status_icon(count): return "[green]✅ 通过[/green]" if count == 0 else "[yellow]⚠️ 问题[/yellow]"

        table.add_row("无效链接", status_icon(len(broken_links)), str(len(broken_links)))
        table.add_row("孤立文章", status_icon(len(orphans)), str(len(orphans)))
        table.add_row("缺少元数据", status_icon(len(missing_meta)), str(len(missing_meta)))
        table.add_row("知识空缺", "[blue]ℹ️ 建议[/blue]", str(len(gaps)))
        table.add_row("INDEX 未收录", status_icon(len(uncovered)), str(len(uncovered)))

        console.print(table)
    else:
        print(f"无效链接: {len(broken_links)}")
        print(f"孤立文章: {len(orphans)}")
        print(f"缺少元数据: {len(missing_meta)}")
        print(f"知识空缺: {len(gaps)}")
        print(f"INDEX 未收录: {len(uncovered)}")

    # 详细输出
    if broken_links:
        console.print(f"\n[bold red]无效链接详情：[/bold red]")
        for issue in broken_links[:10]:
            console.print(f"  {issue['article']} → [[{issue['link']}]]")

    if gaps:
        console.print(f"\n[bold blue]知识空缺（建议新建文章）：[/bold blue]")
        for gap in gaps[:10]:
            console.print(f"  [[{gap}]]")

    if orphans:
        console.print(f"\n[bold yellow]孤立文章：[/bold yellow]")
        for name in orphans[:10]:
            console.print(f"  {name}")

    # 生成报告
    if args.report:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        report_file = OUTPUT_DIR / f"lint_{timestamp}.md"
        report_content = generate_report(results)
        report_file.write_text(report_content, encoding="utf-8")
        console.print(f"\n[green]报告已保存：{report_file.relative_to(WIKI_ROOT)}[/green]")

    # 计算健康分
    score = 100 - len(broken_links) * 5 - len(orphans) * 2 - len(missing_meta) * 3 - len(uncovered) * 2
    score = max(0, score)

    console.rule()
    if score >= 90:
        console.print(f"\n[bold green]🎉 健康评分：{score}/100 — 知识库状态良好！[/bold green]")
    elif score >= 70:
        console.print(f"\n[bold yellow]⚠️  健康评分：{score}/100 — 建议修复上述问题[/bold yellow]")
    else:
        console.print(f"\n[bold red]❌ 健康评分：{score}/100 — 知识库需要维护[/bold red]")


if __name__ == "__main__":
    main()
