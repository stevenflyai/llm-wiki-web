#!/usr/bin/env python3
__version__ = "0.1"
__author__ = "Steven Lian"
"""
LLM Wiki 编译脚本 (compile.py)
===============================
读取 raw/ 目录中的新文档，使用 LLM 将其编译进 wiki/。
支持格式：.md  .txt  .pdf

用法：
    python compile.py                      # 编译所有新文件（含 PDF）
    python compile.py --file raw/paper.pdf # 编译指定 PDF
    python compile.py --all                # 强制重新编译所有文件
    python compile.py --dry-run            # 预览但不实际写入
    python compile.py --pdf-backend pymupdf4llm  # 指定 PDF 提取引擎

PDF 提取引擎（按优先级自动选择，也可手动指定）：
    pymupdf4llm  — 最佳质量，保留表格/公式结构（推荐）
    markitdown   — 微软出品，通用性强
    pdfminer     — 纯文本提取，无额外依赖风险
    pypdf        — 轻量级备选

安装（任选其一即可）：
    pip install pymupdf4llm      # 推荐
    pip install markitdown
    pip install pdfminer.six
    pip install pypdf

依赖：
    pip install openai anthropic rich

配置：
    编辑项目根目录的 .env 文件即可，无需设置环境变量。
    支持 OpenAI、Anthropic、Ollama、以及任意 OpenAI 兼容服务（DeepSeek 等）。
    详见 .env.example。
"""

import os
import json
import re
import sys
import argparse
import hashlib
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

# 加载 .env 并引入统一配置
sys.path.insert(0, str(Path(__file__).parent))
from config import setup as cfg_setup, call_llm as cfg_call_llm, LLMConfig, make_client

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    class Console:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, *args, **kwargs): print("─" * 50)
    console = Console()

# ── 配置 ──────────────────────────────────────────────────────────────────
WIKI_ROOT = Path(__file__).parent.parent
RAW_DIR = WIKI_ROOT / "raw"
WIKI_DIR = WIKI_ROOT / "wiki"
META_DIR = WIKI_ROOT / "_meta"
STATE_FILE = META_DIR / "compile_state.json"
LOG_FILE = WIKI_DIR / "LOG.md"
INDEX_FILE = WIKI_DIR / "INDEX.md"

# 支持的文件格式
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".pptx", ".ppt", ".docx", ".doc"}

# PDF 提取的最大字符数（可在 .env 中通过 PDF_MAX_CHARS 覆盖）
PDF_MAX_CHARS = int(os.environ.get("PDF_MAX_CHARS", "24000"))


# ── PDF 提取 ──────────────────────────────────────────────────────────────
def detect_pdf_backend() -> Optional[str]:
    """按优先级检测可用的 PDF 提取引擎"""
    backends = [
        ("pymupdf4llm", "pymupdf4llm"),
        ("markitdown",  "markitdown"),
        ("pdfminer",    "pdfminer.high_level"),
        ("pypdf",       "pypdf"),
    ]
    for name, module in backends:
        try:
            __import__(module)
            return name
        except Exception:
            # 捕获所有异常：ImportError（未安装）以及包自身的兼容性崩溃
            # 例如 markitdown 在 NumPy 2.x 环境下导入 pandas 会抛 AttributeError
            continue
    return None


def extract_pdf_pymupdf4llm(pdf_path: Path) -> str:
    """使用 pymupdf4llm 提取（最高质量，保留表格/数学公式结构）"""
    import pymupdf4llm
    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    return md_text


def extract_pdf_markitdown(pdf_path: Path) -> str:
    """使用 markitdown 提取（微软出品，通用性强）"""
    from markitdown import MarkItDown
    md = MarkItDown()
    result = md.convert(str(pdf_path))
    return result.text_content


def extract_pdf_pdfminer(pdf_path: Path) -> str:
    """使用 pdfminer.six 提取纯文本"""
    from pdfminer.high_level import extract_text
    return extract_text(str(pdf_path))


def extract_pdf_pypdf(pdf_path: Path) -> str:
    """使用 pypdf 提取纯文本（轻量备选）"""
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"--- 第 {i+1} 页 ---\n{text}")
    return "\n\n".join(pages)


def extract_pdf_text(pdf_path: Path, backend: Optional[str] = None) -> tuple[str, str]:
    """
    从 PDF 提取文本，返回 (提取内容, 使用的引擎名称)。
    backend 为 None 时自动选择最佳引擎。
    """
    chosen = backend or os.environ.get("PDF_BACKEND") or detect_pdf_backend()

    if chosen is None:
        raise RuntimeError(
            "未找到可用的 PDF 提取引擎。\n"
            "请安装其中一个：\n"
            "  pip install pymupdf4llm   （推荐）\n"
            "  pip install markitdown\n"
            "  pip install pdfminer.six\n"
            "  pip install pypdf"
        )

    extractors = {
        "pymupdf4llm": extract_pdf_pymupdf4llm,
        "markitdown":  extract_pdf_markitdown,
        "pdfminer":    extract_pdf_pdfminer,
        "pypdf":       extract_pdf_pypdf,
    }

    if chosen not in extractors:
        raise ValueError(f"未知引擎：{chosen}，可选：{list(extractors)}")

    try:
        text = extractors[chosen](pdf_path)
        return text, chosen
    except Exception as e:
        # 自动降级到下一个可用引擎
        fallback_order = ["pymupdf4llm", "markitdown", "pdfminer", "pypdf"]
        start = fallback_order.index(chosen) + 1 if chosen in fallback_order else 0
        for fallback in fallback_order[start:]:
            if fallback == chosen:
                continue
            try:
                __import__(fallback if fallback != "pdfminer" else "pdfminer.high_level")
                console.print(f"  [yellow]⚠ {chosen} 失败，自动降级到 {fallback}[/yellow]")
                text = extractors[fallback](pdf_path)
                return text, fallback
            except Exception:
                # 同样兜住兼容性崩溃，继续尝试下一个引擎
                continue
        raise RuntimeError(f"所有 PDF 提取引擎均失败。最后错误：{e}") from e


def is_scanned_pdf(text: str, threshold: int = 100) -> bool:
    """
    判断是否为扫描版（图片）PDF。
    启发式判断：提取到的文字极少时视为扫描版。
    """
    return len(text.strip()) < threshold


def pdf_to_markdown(pdf_path: Path, backend: Optional[str] = None) -> tuple[str, dict]:
    """
    将 PDF 转换为适合 LLM 处理的 Markdown 文本。
    返回 (markdown文本, 元信息字典)
    """
    console.print(f"  [dim]提取 PDF 内容...[/dim]")

    text, used_backend = extract_pdf_text(pdf_path, backend)

    # 检查是否为扫描版 PDF
    if is_scanned_pdf(text):
        console.print(f"  [yellow]⚠ 检测到扫描版 PDF（文字极少），文本提取质量可能较低[/yellow]")
        console.print(f"  [dim]建议：使用 OCR 工具（如 tesseract）预处理后再放入 raw/[/dim]")

    # 截断超长内容，保留前后各一部分（论文摘要通常在开头，结论在末尾）
    meta = {
        "backend": used_backend,
        "original_chars": len(text),
        "is_scanned": is_scanned_pdf(text),
    }

    if len(text) > PDF_MAX_CHARS:
        # 保留前 2/3 + 后 1/3，覆盖摘要/引言和结论
        front = int(PDF_MAX_CHARS * 0.7)
        back  = PDF_MAX_CHARS - front
        truncated = text[:front] + f"\n\n... [内容过长，已截断，原文共 {len(text)} 字符] ...\n\n" + text[-back:]
        meta["truncated"] = True
        meta["truncated_chars"] = PDF_MAX_CHARS
        console.print(f"  [dim]内容较长（{len(text):,} 字符），已截取 {PDF_MAX_CHARS:,} 字符发送给 LLM[/dim]")
    else:
        truncated = text
        meta["truncated"] = False

    console.print(f"  [green]✓ PDF 提取完成（引擎：{used_backend}，{len(text):,} 字符）[/green]")
    return truncated, meta


# ── Office 文档提取（PPT / DOC）───────────────────────────────────────────
OFFICE_EXTENSIONS = {".pptx", ".ppt", ".docx", ".doc"}


def extract_office_text(file_path: Path) -> tuple[str, dict]:
    """
    使用 markitdown 提取 Office 文档（PPTX/PPT/DOCX/DOC）为 Markdown。
    返回 (markdown文本, 元信息字典)
    """
    console.print(f"  [dim]提取 Office 文档内容...[/dim]")
    try:
        from markitdown import MarkItDown
    except ImportError:
        raise RuntimeError(
            "需要 markitdown 来处理 Office 文档。\n"
            "请安装：pip install markitdown"
        )

    md = MarkItDown()
    result = md.convert(str(file_path))
    text = result.text_content

    meta = {
        "backend": "markitdown",
        "original_chars": len(text),
        "file_type": file_path.suffix.lower(),
    }

    max_chars = int(os.environ.get("PDF_MAX_CHARS", "240000"))
    if len(text) > max_chars:
        front = int(max_chars * 0.7)
        back = max_chars - front
        text = text[:front] + f"\n\n... [内容过长，已截断，原文共 {len(text)} 字符] ...\n\n" + text[-back:]
        meta["truncated"] = True
        console.print(f"  [dim]内容较长（{meta['original_chars']:,} 字符），已截取 {max_chars:,} 字符[/dim]")
    else:
        meta["truncated"] = False

    console.print(f"  [green]✓ Office 文档提取完成（{meta['original_chars']:,} 字符）[/green]")
    return text, meta


# ── LLM 调用（委托给 config.py）──────────────────────────────────────────
def call_llm(client, client_type: str, model_or_cfg, system_prompt: str, user_prompt: str) -> str:
    """
    统一调用入口。model_or_cfg 可传 LLMConfig 对象或字符串模型名（向下兼容）。
    """
    if isinstance(model_or_cfg, LLMConfig):
        return cfg_call_llm(client, client_type, model_or_cfg, system_prompt, user_prompt)
    # 向下兼容：传入字符串时构造临时 cfg
    from config import LLMConfig as _Cfg
    tmp = _Cfg()
    tmp.model = model_or_cfg
    return cfg_call_llm(client, client_type, tmp, system_prompt, user_prompt)


# ── 状态管理（基于文件哈希，自动检测修改）────────────────────────────────
def file_hash(path: Path) -> str:
    """计算文件的 MD5 哈希（用于判断文件是否变化）"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state() -> dict:
    """加载编译状态"""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
        # 兼容旧版（路径列表 → 哈希字典）
        if isinstance(state.get("processed_files"), list):
            state["processed_files"] = {p: "" for p in state["processed_files"]}
        return state
    return {
        "last_compile": None,
        "processed_files": {},   # { "raw/xxx.pdf": "md5hash" }
        "total_wiki_articles": 0,
        "total_raw_files": 0,
        "wiki_word_count": 0,
    }


def save_state(state: dict):
    """保存编译状态"""
    META_DIR.mkdir(exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def needs_compile(raw_file: Path, processed: dict) -> bool:
    """
    判断文件是否需要编译：
    - 从未处理过  → True
    - 内容已变化（哈希不同）→ True
    - 已处理且未变化 → False
    """
    key = str(raw_file)
    if key not in processed:
        return True
    stored_hash = processed[key]
    if not stored_hash:          # 旧版兼容：无哈希值，强制重新编译一次
        return True
    return file_hash(raw_file) != stored_hash


# ── Wiki 操作 ─────────────────────────────────────────────────────────────
def get_wiki_articles() -> list[Path]:
    """获取所有 wiki 文章路径"""
    return list(WIKI_DIR.rglob("*.md"))


def find_best_wiki_file(concept: str, wiki_dir: Path) -> Optional[Path]:
    """根据概念名找到最匹配的 wiki 文件"""
    for p in wiki_dir.rglob("*.md"):
        if concept in p.stem or p.stem in concept:
            return p
    return None


def update_index(new_article_path: Path, summary: str):
    """更新 INDEX.md 中的条目"""
    if not INDEX_FILE.exists():
        return

    # 简单追加到对应分类
    category = new_article_path.parent.name
    article_name = new_article_path.stem
    today = datetime.now().strftime("%Y-%m-%d")

    with open(INDEX_FILE, "a") as f:
        f.write(f"\n| [[{article_name}]] | {summary[:50]}... | {today} |\n")

    console.print(f"  [green]✓ INDEX.md 已更新[/green]")


def append_log(message: str):
    """在 LOG.md 追加记录"""
    if not LOG_FILE.exists():
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(LOG_FILE, "a") as f:
        f.write(f"\n### [{timestamp}] COMPILE — {message}\n")


# ── LLM 错误处理 ──────────────────────────────────────────────────────────
def _handle_llm_error(e: Exception) -> None:
    """将 LLM API 连接/认证错误转换为用户友好的提示"""
    msg = str(e)
    if "Connection refused" in msg or "ConnectError" in msg or "ConnectionError" in msg:
        console.print("[red]✗ 无法连接到 LLM 服务[/red]")
        console.print("  [yellow]当前使用 Ollama，但本地服务未启动。[/yellow]")
        console.print("  请选择以下任一方式：")
        console.print("  [bold]① 启动 Ollama：[/bold]  ollama serve")
        console.print("  [bold]② 配置 API Key：[/bold] 编辑 .env，填入 ANTHROPIC_API_KEY 或 OPENAI_API_KEY")
    elif "401" in msg or "Unauthorized" in msg or "authentication" in msg.lower():
        console.print("[red]✗ API Key 认证失败[/red]")
        console.print("  请检查 .env 中的 API Key 是否正确")
    elif "429" in msg or "rate_limit" in msg.lower():
        console.print("[red]✗ API 速率限制，请稍后重试[/red]")
    else:
        console.print(f"[red]✗ LLM 调用失败：{e}[/red]")


def preflight_check(client, client_type: str, cfg) -> bool:
    """
    启动前用一个极短的请求验证 LLM 连接是否正常。
    返回 True 表示连接正常，False 表示失败（已打印错误原因）。
    """
    console.print("[dim]验证 LLM 连接...[/dim]", end=" ")
    try:
        result = cfg_call_llm(client, client_type, cfg, "你是助手。", "回复 OK，不要其他内容。",
                              max_tokens=10)
        console.print("[green]✓[/green]")
        return True
    except Exception as e:
        console.print("[red]✗[/red]")
        _handle_llm_error(e)
        return False


# ── 编译逻辑 ──────────────────────────────────────────────────────────────
COMPILE_SYSTEM_PROMPT = """你是一个专业的知识编译器，负责将原始文档编译成结构化的 Wiki 文章。

你的任务是：
1. 读取原始文档的内容
2. 提取核心概念、关键信息、重要细节
3. 生成一篇结构清晰的 Markdown Wiki 文章

Wiki 文章格式要求：
- 标题（# 标题）
- 元信息（类别、最后更新、相关文章、原始来源）
- 概述（2-3句话）
- 核心内容（使用 ## 和 ### 组织）
- 关键要点（bullet points）
- 延伸阅读（相关 wiki 文章链接，使用 [[文章名]] 格式）
- 原始来源引用

语言：中文为主，专业术语保留英文
风格：百科全书式，客观准确，结构清晰"""


def compile_file(raw_file: Path, client, client_type: str, model: str,
                 existing_wiki: list[str], dry_run: bool = False,
                 pdf_backend: Optional[str] = None,
                 pdf_cache: Optional[dict] = None) -> Optional[Path]:
    """编译单个原始文件（.md / .txt / .pdf / .pptx / .docx 等）为 wiki 文章"""
    suffix = raw_file.suffix.lower()
    console.print(f"[bold blue]编译：[/bold blue]{raw_file.name}  [dim]({suffix})[/dim]")

    # ── 根据文件类型提取内容 ──────────────────────────────────────────────
    pdf_meta = {}
    if suffix == ".pdf":
        # 优先使用预提取缓存（并行阶段已提取好）
        if pdf_cache and raw_file in pdf_cache:
            content, pdf_meta = pdf_cache[raw_file]
            console.print(f"  [dim]使用预提取缓存[/dim]")
        else:
            try:
                content, pdf_meta = pdf_to_markdown(raw_file, backend=pdf_backend)
            except RuntimeError as e:
                console.print(f"  [red]PDF 提取失败：{e}[/red]")
                return None
    elif suffix in OFFICE_EXTENSIONS:
        try:
            content, pdf_meta = extract_office_text(raw_file)
        except RuntimeError as e:
            console.print(f"  [red]Office 文档提取失败：{e}[/red]")
            return None
    else:
        try:
            content = raw_file.read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"  [red]读取失败：{e}[/red]")
            return None

    if len(content.strip()) < 50:
        console.print(f"  [yellow]内容太短，跳过[/yellow]")
        return None

    # 确定目标类别
    category_prompt = f"""
现有的 wiki 文章：{', '.join(existing_wiki[:20])}

根据以下文档内容，判断它应该属于哪个类别：
- concepts（核心概念）
- tools（工具和框架）
- research（研究前沿）
- tutorials（教程实践）

只回答一个词：concepts/tools/research/tutorials
文档开头：{content[:500]}
"""

    try:
        category = call_llm(client, client_type, model,
                            "你是分类助手，只输出类别名称，不要其他内容。",
                            category_prompt).strip().lower()
    except Exception as e:
        _handle_llm_error(e)
        return None

    if category not in ["concepts", "tools", "research", "tutorials"]:
        category = "concepts"

    # 构建文件类型提示（帮助 LLM 理解来源格式）
    pdf_hint = ""
    if suffix == ".pdf":
        backend_name = pdf_meta.get("backend", "unknown")
        scanned_warn = "\n⚠️ 注意：此 PDF 为扫描版，文字识别可能有误，请酌情处理。" if pdf_meta.get("is_scanned") else ""
        truncated_warn = f"\n⚠️ 注意：原文件共 {pdf_meta.get('original_chars', 0):,} 字符，已截取前后共 {PDF_MAX_CHARS:,} 字符。" if pdf_meta.get("truncated") else ""
        pdf_hint = f"\n[文件类型：PDF，提取引擎：{backend_name}{scanned_warn}{truncated_warn}]\n"
    elif suffix in OFFICE_EXTENSIONS:
        file_type = "PowerPoint" if suffix in (".pptx", ".ppt") else "Word"
        truncated_warn = f"\n⚠️ 注意：原文件共 {pdf_meta.get('original_chars', 0):,} 字符，已截取部分内容。" if pdf_meta.get("truncated") else ""
        pdf_hint = f"\n[文件类型：{file_type}，提取引擎：markitdown{truncated_warn}]\n"

    # 生成 wiki 文章
    user_prompt = f"""
原始文档文件名：{raw_file.name}{pdf_hint}
原始文档内容：
---
{content}
---

现有 wiki 文章（用于建立链接）：{', '.join(existing_wiki[:30])}

请生成一篇 Markdown Wiki 文章。
类别字段写：{category}
今天日期：{datetime.now().strftime("%Y-%m-%d")}
原始来源字段写文件名：{raw_file.name}
"""

    try:
        wiki_content = call_llm(client, client_type, model, COMPILE_SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        _handle_llm_error(e)
        return None

    if not wiki_content:
        console.print(f"  [red]LLM 返回空内容[/red]")
        return None

    # 提取文章标题
    title_match = re.search(r'^# (.+)$', wiki_content, re.MULTILINE)
    title = title_match.group(1) if title_match else raw_file.stem

    # 确定输出路径
    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
    output_dir = WIKI_DIR / category
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{safe_title}.md"

    if dry_run:
        console.print(f"  [yellow][DRY-RUN] 将写入：{output_file.relative_to(WIKI_ROOT)}[/yellow]")
        console.print(f"  内容预览：{wiki_content[:200]}...")
        return output_file

    # 写入文件
    output_file.write_text(wiki_content, encoding="utf-8")
    console.print(f"  [green]✓ 已写入：{output_file.relative_to(WIKI_ROOT)}[/green]")

    # 更新索引和日志
    summary = wiki_content.split('\n\n')[2][:100] if len(wiki_content.split('\n\n')) > 2 else title
    update_index(output_file, summary)

    return output_file


# ── 并行 PDF 预提取 ────────────────────────────────────────────────────────
def prefetch_pdfs(pdf_files: list[Path], backend: Optional[str],
                  workers: int) -> dict[Path, tuple[str, dict]]:
    """
    并行提取多个 PDF 的文字内容，返回 {路径: (markdown文本, 元信息)}。
    文字提取是 I/O 密集型操作，多线程可大幅缩短总耗时。
    LLM 调用依然串行（避免触发 API 速率限制）。
    """
    if not pdf_files:
        return {}

    results: dict[Path, tuple[str, dict]] = {}
    errors:  dict[Path, str] = {}

    console.print(f"\n[dim]并行提取 {len(pdf_files)} 个 PDF 文字内容（{workers} 线程）...[/dim]")

    def extract_one(p: Path):
        return p, pdf_to_markdown(p, backend=backend)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_one, p): p for p in pdf_files}
        done = 0
        for future in as_completed(futures):
            done += 1
            pdf_path = futures[future]
            try:
                _, (text, meta) = future.result()
                results[pdf_path] = (text, meta)
                console.print(f"  [{done}/{len(pdf_files)}] ✓ {pdf_path.name}")
            except Exception as e:
                errors[pdf_path] = str(e)
                console.print(f"  [{done}/{len(pdf_files)}] ✗ {pdf_path.name} — {e}")

    if errors:
        console.print(f"\n[yellow]{len(errors)} 个 PDF 提取失败，将在编译阶段跳过[/yellow]")

    return results


# ── 主程序 ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="LLM Wiki 编译脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python compile.py                        # 仅编译新增/修改的文件（增量）
  python compile.py --all                  # 强制重新编译所有文件
  python compile.py --file raw/paper.pdf   # 编译单个文件
  python compile.py --workers 8            # 用 8 线程并行提取 PDF 文字
  python compile.py --dry-run              # 预览将编译哪些文件，不写入
  python compile.py --pdf-backend pymupdf4llm  # 指定 PDF 提取引擎
        """
    )
    parser.add_argument("--file", type=str,
                        help="指定编译单个文件（支持 .md / .txt / .pdf）")
    parser.add_argument("--all", action="store_true",
                        help="强制重新编译所有文件（忽略哈希缓存）")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览将编译哪些文件，不实际写入")
    parser.add_argument("--model", type=str, default=None,
                        help="LLM 模型名（默认读取 .env / 环境变量）")
    parser.add_argument("--ollama", action="store_true",
                        help="使用本地 Ollama（无需 API Key）")
    parser.add_argument(
        "--pdf-backend",
        choices=["pymupdf4llm", "markitdown", "pdfminer", "pypdf"],
        default=None,
        help="指定 PDF 文字提取引擎（默认自动检测）"
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="并行提取 PDF 的线程数（默认 4，仅影响文字提取阶段）"
    )
    args = parser.parse_args()

    console.rule("[bold]LLM Wiki 编译器[/bold]")

    # ── 初始化 LLM 客户端（从 .env 读取配置）───────────────────────────
    client, client_type, cfg = cfg_setup(
        use_ollama=args.ollama,
        model=args.model,
        pdf_backend=args.pdf_backend,
        workers=args.workers,
    )
    console.print(f"[dim]{cfg.summary()}[/dim]")
    model = cfg   # 传给 compile_file 的 model 参数改为 cfg 对象

    # ── 预检：验证 LLM 连接（在处理文件前快速失败）──────────────────────
    if not preflight_check(client, client_type, cfg):
        sys.exit(1)

    # ── PDF 引擎状态 ─────────────────────────────────────────────────────
    pdf_backend = args.pdf_backend
    effective_backend = pdf_backend or detect_pdf_backend()
    if pdf_backend:
        console.print(f"PDF 引擎：[bold]{pdf_backend}[/bold] (手动指定)")
    elif effective_backend:
        console.print(f"PDF 引擎：[bold]{effective_backend}[/bold] (自动检测) | 并行线程：{args.workers}")
    else:
        console.print("PDF 引擎：[yellow]未安装，PDF 将被跳过[/yellow]  (pip install pymupdf4llm)")

    # ── 加载状态（哈希字典）──────────────────────────────────────────────
    state    = load_state()
    processed: dict = state.get("processed_files", {})   # {路径字符串: md5哈希}
    existing_wiki = [p.stem for p in get_wiki_articles()]

    # ── 收集 raw/ 下所有支持格式的文件 ───────────────────────────────────
    def collect_raw_files() -> list[Path]:
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(RAW_DIR.rglob(f"*{ext}"))
        return sorted(files)

    if args.file:
        target = Path(args.file)
        if target.suffix.lower() not in SUPPORTED_EXTENSIONS:
            console.print(f"[red]不支持的格式：{target.suffix}（支持：{SUPPORTED_EXTENSIONS}）[/red]")
            sys.exit(1)
        files_to_compile = [target]
    elif args.all:
        files_to_compile = collect_raw_files()
    else:
        # 增量模式：只处理「新增」或「内容已变化」的文件
        files_to_compile = [f for f in collect_raw_files() if needs_compile(f, processed)]

    # 无 PDF 引擎时过滤 PDF
    if not effective_backend:
        skipped_pdfs = [f for f in files_to_compile if f.suffix.lower() == ".pdf"]
        if skipped_pdfs:
            console.print(f"[yellow]跳过 {len(skipped_pdfs)} 个 PDF（未安装引擎）[/yellow]")
        files_to_compile = [f for f in files_to_compile if f.suffix.lower() != ".pdf"]

    if not files_to_compile:
        all_raw = collect_raw_files()
        console.print(f"\n[green]✓ 没有需要编译的文件[/green]")
        console.print(f"  raw/ 共 {len(all_raw)} 个文件，全部已是最新（基于内容哈希检测）")
        console.print(f"  直接将新 PDF 或文档放入 raw/ 目录，下次运行自动处理。")
        return

    # ── 统计并展示 ────────────────────────────────────────────────────────
    pdf_list  = [f for f in files_to_compile if f.suffix.lower() == ".pdf"]
    text_list = [f for f in files_to_compile if f.suffix.lower() != ".pdf"]
    parts = []
    if pdf_list:  parts.append(f"{len(pdf_list)} 个 PDF")
    if text_list: parts.append(f"{len(text_list)} 个文本")
    console.print(f"\n待编译：[bold]{len(files_to_compile)} 个文件[/bold]（{'、'.join(parts)}）\n")

    if args.dry_run:
        console.print("[yellow][DRY-RUN] 以下文件将被编译（不实际写入）：[/yellow]")
        for f in files_to_compile:
            status = "新增" if str(f) not in processed else "已修改"
            console.print(f"  [{status}] {f.relative_to(WIKI_ROOT)}")
        return

    # ── 阶段一：并行提取所有 PDF 文字（I/O 密集，多线程加速）────────────
    pdf_cache: dict[Path, tuple[str, dict]] = {}
    if pdf_list:
        pdf_cache = prefetch_pdfs(pdf_list, effective_backend, args.workers)

    # ── 阶段二：串行调用 LLM 编译（API 调用，避免触发速率限制）──────────
    console.print()
    compiled_count = 0
    failed_count   = 0

    for i, raw_file in enumerate(files_to_compile, 1):
        status = "新增" if str(raw_file) not in processed else "已修改"
        console.print(f"[{i}/{len(files_to_compile)}] [{status}] ", end="")

        result = compile_file(
            raw_file, client, client_type, model, existing_wiki,
            dry_run=False,
            pdf_backend=effective_backend,
            pdf_cache=pdf_cache,          # 传入预提取缓存
        )

        if result:
            # 编译成功：记录文件哈希
            processed[str(raw_file)] = file_hash(raw_file)
            compiled_count += 1
            existing_wiki.append(result.stem)
            # 每成功 3 篇就持久化一次状态（防止中途中断丢失进度）
            if compiled_count % 3 == 0:
                state["processed_files"] = processed
                save_state(state)
        else:
            failed_count += 1

    # ── 最终持久化状态 ────────────────────────────────────────────────────
    if compiled_count > 0:
        state["processed_files"]    = processed
        state["last_compile"]       = datetime.now().isoformat()
        state["total_raw_files"]    = len(collect_raw_files())
        state["total_wiki_articles"] = len(get_wiki_articles())
        save_state(state)
        append_log(f"编译 {compiled_count} 篇文章（PDF {len(pdf_list)} 篇，失败 {failed_count} 篇）")

    # ── 汇总输出 ──────────────────────────────────────────────────────────
    console.rule()
    console.print(f"\n[bold green]完成！[/bold green] 成功 {compiled_count} 篇", end="")
    if failed_count:
        console.print(f"  [red]失败 {failed_count} 篇[/red]", end="")
    console.print(f"\nWiki 总文章数：{len(get_wiki_articles())}")
    console.print(f"已追踪文件数：{len(processed)}（下次运行将自动跳过未变化的文件）")


if __name__ == "__main__":
    main()
