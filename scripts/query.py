#!/usr/bin/env python3
"""
LLM Wiki 查询脚本 (query.py)
==============================
从编译好的 wiki 中检索信息，回答问题。

用法：
    python query.py "什么是注意力机制？"
    python query.py --interactive                # 交互式对话模式
    python query.py --save "解释Transformer"     # 保存到 output/queries/
    python query.py --ollama "你的问题"          # 使用本地 Ollama
    python query.py --model claude-opus-4-6 "问题"  # 指定模型

配置：
    编辑项目根目录的 .env 文件即可，支持 OpenAI、Anthropic、Ollama 及
    任意 OpenAI 兼容服务（DeepSeek、通义千问等）。详见 .env.example。

依赖：
    pip install openai anthropic rich
"""

__version__ = "0.2"
__release_date__ = "2026-04-11"
__author__ = "Steven Lian"

import os
import sys
import argparse
import re
from datetime import datetime
from pathlib import Path

# 加载 .env 并引入统一配置
sys.path.insert(0, str(Path(__file__).parent))
from config import setup as cfg_setup, call_llm as cfg_call_llm

try:
    from rich.console import Console
    from rich.markdown import Markdown
    console = Console()
    RICH = True
except ImportError:
    RICH = False
    class Console:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, *args, **kwargs): print("─" * 50)
    console = Console()

WIKI_ROOT = Path(__file__).parent.parent
WIKI_DIR = WIKI_ROOT / "wiki"
OUTPUT_DIR = WIKI_ROOT / "output" / "queries"
INDEX_FILE = WIKI_DIR / "INDEX.md"


# ── Wiki 检索 ─────────────────────────────────────────────────────────────
def load_index() -> str:
    """加载 INDEX.md 内容"""
    if INDEX_FILE.exists():
        return INDEX_FILE.read_text(encoding="utf-8")
    return "（INDEX.md 不存在）"


def _tokenize_query(query: str) -> list[str]:
    """将查询拆分为关键词列表，同时处理中文和英文混合文本。
    例如 "什么是Harness？" → ["什么是harness？", "什么", "是", "harness"]
    """
    query_lower = query.lower()
    # 空格分词（英文/混合）
    words = query_lower.split()
    # 额外提取：从中文文本中分离出英文单词和中文字符
    extra = re.findall(r'[a-z][a-z0-9_-]+', query_lower)  # 英文词（≥2字符）
    extra += re.findall(r'[\u4e00-\u9fff]+', query_lower)  # 连续中文片段
    for w in extra:
        if w not in words:
            words.append(w)
    return words


def find_relevant_articles(query: str, max_articles: int = 5) -> list[tuple[Path, str]]:
    """根据查询词找到相关 wiki 文章（基于关键词打分）"""
    words = _tokenize_query(query)
    scored = []

    for wiki_file in WIKI_DIR.rglob("*.md"):
        if wiki_file.name in ["INDEX.md", "LOG.md"]:
            continue
        try:
            content = wiki_file.read_text(encoding="utf-8")
            score = 0
            stem_lower = wiki_file.stem.lower()
            content_lower = content.lower()
            for word in words:
                if word in stem_lower:
                    score += 10
                count = content_lower.count(word)
                if count > 0:
                    score += count
            if score > 0:
                scored.append((wiki_file, content, score))
        except Exception:
            pass

    scored.sort(key=lambda x: x[2], reverse=True)
    return [(f, c) for f, c, _ in scored[:max_articles]]


def build_context(articles: list[tuple[Path, str]]) -> str:
    """构建查询上下文（每篇文章截取前 2000 字符）"""
    if not articles:
        return "（未找到相关 wiki 文章）"

    parts = []
    for wiki_file, content in articles:
        parts.append(f"## 来自：{wiki_file.stem}\n\n{content[:2000]}")
    return "\n\n---\n\n".join(parts)


# ── LLM 查询 ──────────────────────────────────────────────────────────────
QUERY_SYSTEM_PROMPT = """你是一个基于 LLM Wiki 知识库的智能助手。

你有权访问一个结构化的 Markdown Wiki 知识库，包含关于 LLM（大型语言模型）的深度技术文章。

回答规则：
1. 优先基于提供的 Wiki 内容回答，不要编造信息
2. 如果 Wiki 中没有相关信息，明确说明，并基于自身知识简要回答
3. 在回答中引用 Wiki 文章名，格式：参见[[文章名]]
4. 回答要准确、结构清晰、便于理解
5. 使用中文回答，专业术语保留英文

输出格式：
- 使用 Markdown 格式
- 重要概念加粗
- 代码用代码块
- 必要时使用表格对比"""


def query_wiki(question: str, client, client_type: str, cfg,
               save: bool = False) -> str:
    """查询 wiki 并返回答案"""
    articles = find_relevant_articles(question)
    context  = build_context(articles)

    article_names = [f.stem for f, _ in articles]
    console.print(f"\n[dim]参考文章：{', '.join(article_names) if article_names else '无'}[/dim]")

    user_prompt = f"""问题：{question}

相关 Wiki 内容：
{context}

请基于以上内容回答问题。"""

    answer = cfg_call_llm(client, client_type, cfg, QUERY_SYSTEM_PROMPT, user_prompt,
                          max_tokens=2048)

    # 保存到文件
    if save:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        safe_q = re.sub(r'[<>:"/\\|?*\s]', '_', question[:30])
        output_file = OUTPUT_DIR / f"{timestamp}_{safe_q}.md"
        output_file.write_text(
            f"# 查询：{question}\n\n"
            f"**时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"**模型**：{cfg.provider} / {cfg.model}\n"
            f"**参考文章**：{', '.join(article_names)}\n\n"
            f"---\n\n{answer}",
            encoding="utf-8"
        )
        console.print(f"\n[dim]答案已保存：{output_file.relative_to(WIKI_ROOT)}[/dim]")

    return answer


# ── 主程序 ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="LLM Wiki 查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python query.py "什么是注意力机制？"
  python query.py --interactive
  python query.py --save --model gpt-4o "解释Transformer架构"
  python query.py --ollama "介绍强化学习"
        """
    )
    parser.add_argument("question", nargs="?", help="要查询的问题")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="交互式对话模式")
    parser.add_argument("--save", "-s", action="store_true",
                        help="将答案保存到 output/queries/ 目录")
    parser.add_argument("--model", type=str, default=None,
                        help="LLM 模型名（默认读取 .env / 环境变量）")
    parser.add_argument("--ollama", action="store_true",
                        help="使用本地 Ollama（无需 API Key）")
    args = parser.parse_args()

    console.rule("[bold]LLM Wiki 查询系统[/bold]")

    # 从 .env 加载配置，应用 CLI 覆盖
    client, client_type, cfg = cfg_setup(
        use_ollama=args.ollama,
        model=args.model,
    )
    console.print(f"[dim]{cfg.summary()}[/dim]")

    wiki_count = len(list(WIKI_DIR.rglob("*.md")))
    console.print(f"\n知识库：[bold]{wiki_count}[/bold] 篇文章\n")

    if args.interactive:
        console.print("进入交互式模式（输入 'exit' 或 Ctrl+C 退出）\n")
        while True:
            try:
                question = input("你的问题：").strip()
                if not question:
                    continue
                if question.lower() in ["exit", "quit", "q", "退出"]:
                    break

                answer = query_wiki(question, client, client_type, cfg, save=args.save)
                console.print("\n")
                if RICH:
                    try:
                        console.print(Markdown(answer))
                    except Exception:
                        console.print(answer)
                else:
                    console.print(answer)
                console.print()

            except KeyboardInterrupt:
                console.print("\n[dim]再见！[/dim]")
                break

    elif args.question:
        answer = query_wiki(args.question, client, client_type, cfg, save=args.save)
        console.print()
        if RICH:
            try:
                console.print(Markdown(answer))
            except Exception:
                console.print(answer)
        else:
            console.print(answer)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
