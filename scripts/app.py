#!/usr/bin/env python3
"""
LLM Wiki Web App (app.py)
==========================
FastAPI web interface for the LLM Wiki system.

Usage:
    python scripts/app.py
    # Opens at http://localhost:8000

Features:
    - Browse wiki articles with Markdown rendering
    - Query the knowledge base via LLM
    - Compile raw materials into wiki articles
    - Run health checks and auto-fix issues
"""

import asyncio
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# ── Path setup ────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPTS_DIR.parent
WIKI_DIR = PROJECT_ROOT / "wiki"
RAW_DIR = PROJECT_ROOT / "raw"
META_DIR = PROJECT_ROOT / "_meta"
STATE_FILE = META_DIR / "compile_state.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "queries"

# Add scripts to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))

from config import setup as cfg_setup, call_llm as cfg_call_llm, LLMConfig
from compile import (
    compile_file, load_state, save_state, needs_compile, file_hash,
    get_wiki_articles, prefetch_pdfs, detect_pdf_backend, preflight_check,
    SUPPORTED_EXTENSIONS, append_log,
)
from query import query_wiki, find_relevant_articles, build_context, QUERY_SYSTEM_PROMPT
from lint import (
    load_all_articles, check_broken_links, check_orphan_articles,
    check_missing_metadata, check_knowledge_gaps, check_index_coverage,
)

# ── App setup ─────────────────────────────────────────────────────────────────
__version__ = "0.1"
__author__ = "Steven Lian"

app = FastAPI(title="LLM Wiki", version=__version__, docs_url="/docs")
templates = Jinja2Templates(directory=str(SCRIPTS_DIR / "templates"))

# Global LLM client (lazy init, auto-refresh on .env change)
_llm_client = None
_llm_client_type = None
_llm_cfg = None
_env_mtime = 0.0  # track .env modification time

# Compile state
_compile_lock = threading.Lock()
_compile_running = False
_compile_logs: list[str] = []

_ENV_FILE = PROJECT_ROOT / ".env"


def _env_changed() -> bool:
    """Check if .env has been modified since last load."""
    global _env_mtime
    try:
        mtime = _ENV_FILE.stat().st_mtime
        if mtime != _env_mtime:
            _env_mtime = mtime
            return True
    except FileNotFoundError:
        pass
    return False


def get_llm():
    """Lazy-init LLM client. Auto-reloads if .env has changed."""
    global _llm_client, _llm_client_type, _llm_cfg
    if _llm_client is None or _env_changed():
        # Clear env cache so config.py re-reads .env
        for key in list(os.environ.keys()):
            if key.startswith(("ANTHROPIC_", "OPENAI_", "AZURE_OPENAI_", "CUSTOM_",
                               "OLLAMA_", "LLM_PROVIDER", "LLM_TIMEOUT",
                               "PDF_BACKEND", "PDF_WORKERS", "PDF_MAX_CHARS")):
                del os.environ[key]
        from config import _load_dotenv, _PROJECT_ROOT
        _load_dotenv(_PROJECT_ROOT / ".env")
        _llm_client, _llm_client_type, _llm_cfg = cfg_setup()
    return _llm_client, _llm_client_type, _llm_cfg


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── API: Articles ─────────────────────────────────────────────────────────────
@app.get("/api/articles")
async def list_articles():
    """List all wiki articles grouped by category."""
    categories = {}
    for md_file in WIKI_DIR.rglob("*.md"):
        if md_file.name in ("INDEX.md", "LOG.md"):
            continue
        category = md_file.parent.name
        if category == "wiki":
            category = "other"
        stat = md_file.stat()
        entry = {
            "name": md_file.stem,
            "category": category,
            "path": str(md_file.relative_to(PROJECT_ROOT)),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        }
        categories.setdefault(category, []).append(entry)

    # Sort articles within each category
    for cat in categories:
        categories[cat].sort(key=lambda x: x["name"])

    return {"categories": categories, "total": sum(len(v) for v in categories.values())}


@app.get("/api/articles/{category}/{name}")
async def get_article(category: str, name: str):
    """Get a single wiki article content."""
    # Try exact match first, then fuzzy
    target = WIKI_DIR / category / f"{name}.md"
    if not target.exists():
        # Search for partial match
        for md_file in (WIKI_DIR / category).glob("*.md"):
            if name.lower() in md_file.stem.lower():
                target = md_file
                break

    if not target.exists():
        return JSONResponse({"error": f"Article not found: {category}/{name}"}, status_code=404)

    content = target.read_text(encoding="utf-8")
    return {
        "name": target.stem,
        "category": category,
        "content": content,
        "path": str(target.relative_to(PROJECT_ROOT)),
        "modified": datetime.fromtimestamp(target.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
    }


# ── API: Raw files ────────────────────────────────────────────────────────────
@app.get("/api/raw-files")
async def list_raw_files():
    """List raw files with their compile status."""
    state = load_state()
    processed = state.get("processed_files", {})

    files = []
    for ext in SUPPORTED_EXTENSIONS:
        for f in RAW_DIR.rglob(f"*{ext}"):
            key = str(f)
            status = "compiled" if key in processed else "new"
            if key in processed and needs_compile(f, processed):
                status = "modified"
            files.append({
                "name": f.name,
                "path": str(f.relative_to(PROJECT_ROOT)),
                "size": f.stat().st_size,
                "status": status,
                "category": f.parent.name,
            })

    files.sort(key=lambda x: (x["status"] != "new", x["status"] != "modified", x["name"]))
    return {
        "files": files,
        "total": len(files),
        "pending": sum(1 for f in files if f["status"] in ("new", "modified")),
        "last_compile": state.get("last_compile"),
    }


# ── API: Compile ──────────────────────────────────────────────────────────────
@app.post("/api/compile")
async def compile_wiki():
    """Trigger compilation and stream progress via SSE."""
    global _compile_running

    if _compile_running:
        return JSONResponse({"error": "Compilation already in progress"}, status_code=409)

    async def event_stream():
        global _compile_running, _compile_logs
        _compile_running = True
        _compile_logs = []

        def log(msg: str):
            _compile_logs.append(msg)

        try:
            log("Initializing LLM client...")
            yield f"data: {json.dumps({'type': 'log', 'message': 'Initializing LLM client...'})}\n\n"

            client, client_type, cfg = get_llm()

            # Collect files to compile
            state = load_state()
            processed = state.get("processed_files", {})
            existing_wiki = [p.stem for p in get_wiki_articles()]

            raw_files = []
            for ext in SUPPORTED_EXTENSIONS:
                raw_files.extend(RAW_DIR.rglob(f"*{ext}"))
            raw_files = sorted(raw_files)

            files_to_compile = [f for f in raw_files if needs_compile(f, processed)]

            # Filter PDFs if no backend
            effective_backend = detect_pdf_backend()
            if not effective_backend:
                files_to_compile = [f for f in files_to_compile if f.suffix.lower() != ".pdf"]

            if not files_to_compile:
                yield f"data: {json.dumps({'type': 'complete', 'message': 'No new files to compile. All files are up to date.', 'compiled': 0})}\n\n"
                return

            total = len(files_to_compile)
            yield f"data: {json.dumps({'type': 'log', 'message': f'Found {total} file(s) to compile'})}\n\n"

            # Pre-extract PDFs
            pdf_list = [f for f in files_to_compile if f.suffix.lower() == ".pdf"]
            pdf_cache = {}
            if pdf_list:
                yield f"data: {json.dumps({'type': 'log', 'message': f'Extracting text from {len(pdf_list)} PDF(s)...'})}\n\n"
                pdf_cache = prefetch_pdfs(pdf_list, effective_backend, cfg.pdf_workers)
                yield f"data: {json.dumps({'type': 'log', 'message': 'PDF extraction complete'})}\n\n"

            # Compile each file
            compiled = 0
            failed = 0
            for i, raw_file in enumerate(files_to_compile, 1):
                fname = raw_file.name
                yield f"data: {json.dumps({'type': 'progress', 'current': i, 'total': total, 'file': fname, 'message': f'[{i}/{total}] Compiling {fname}...'})}\n\n"

                result = compile_file(
                    raw_file, client, client_type, cfg, existing_wiki,
                    dry_run=False,
                    pdf_backend=effective_backend,
                    pdf_cache=pdf_cache,
                )

                if result:
                    processed[str(raw_file)] = file_hash(raw_file)
                    compiled += 1
                    existing_wiki.append(result.stem)
                    yield f"data: {json.dumps({'type': 'log', 'message': f'  -> {result.stem}'})}\n\n"
                else:
                    failed += 1
                    yield f"data: {json.dumps({'type': 'log', 'message': f'  -> Failed to compile {fname}'})}\n\n"

            # Save state
            if compiled > 0:
                state["processed_files"] = processed
                state["last_compile"] = datetime.now().isoformat()
                state["total_raw_files"] = len(raw_files)
                state["total_wiki_articles"] = len(get_wiki_articles())
                save_state(state)
                append_log(f"Web compile: {compiled} articles (failed: {failed})")

            yield f"data: {json.dumps({'type': 'complete', 'message': f'Done! Compiled {compiled} article(s), failed {failed}', 'compiled': compiled, 'failed': failed})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            _compile_running = False

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── API: Query ────────────────────────────────────────────────────────────────
@app.post("/api/query")
async def query_api(request: Request):
    """Query the wiki knowledge base."""
    body = await request.json()
    question = body.get("question", "").strip()
    if not question:
        return JSONResponse({"error": "No question provided"}, status_code=400)

    client, client_type, cfg = get_llm()

    # Find relevant articles
    articles = find_relevant_articles(question)
    context = build_context(articles)
    article_names = [f.stem for f, _ in articles]

    user_prompt = f"""Question: {question}

Related Wiki content:
{context}

Please answer based on the above content."""

    try:
        answer = cfg_call_llm(client, client_type, cfg, QUERY_SYSTEM_PROMPT, user_prompt, max_tokens=2048)
    except Exception as e:
        return JSONResponse({"error": f"LLM error: {str(e)}"}, status_code=500)

    # Save query result
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe_q = re.sub(r'[<>:"/\\|?*\s]', '_', question[:30])
    output_file = OUTPUT_DIR / f"{timestamp}_{safe_q}.md"
    output_file.write_text(
        f"# Query: {question}\n\n"
        f"**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"**Model**: {cfg.provider} / {cfg.model}\n"
        f"**References**: {', '.join(article_names)}\n\n"
        f"---\n\n{answer}",
        encoding="utf-8"
    )

    return {
        "answer": answer,
        "references": article_names,
        "saved_to": str(output_file.relative_to(PROJECT_ROOT)),
    }


# ── API: Health ───────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    """Run health check on the wiki."""
    articles = load_all_articles()

    if not articles:
        return {"total_articles": 0, "score": 0, "message": "Wiki is empty"}

    broken_links = check_broken_links(articles)
    orphans = check_orphan_articles(articles)
    missing_meta = check_missing_metadata(articles)
    gaps = check_knowledge_gaps(articles)
    uncovered = check_index_coverage(articles)

    score = 100
    score -= len(broken_links) * 5
    score -= len(orphans) * 2
    score -= len(missing_meta) * 3
    score -= len(uncovered) * 2
    score = max(0, score)

    return {
        "total_articles": len(articles),
        "score": score,
        "checks": {
            "broken_links": {
                "count": len(broken_links),
                "items": [{"article": i["article"], "link": i["link"]} for i in broken_links],
            },
            "orphans": {
                "count": len(orphans),
                "items": orphans,
            },
            "missing_metadata": {
                "count": len(missing_meta),
                "items": [{"article": i["article"], "missing": i["missing"]} for i in missing_meta],
            },
            "knowledge_gaps": {
                "count": len(gaps),
                "items": gaps,
            },
            "uncovered_in_index": {
                "count": len(uncovered),
                "items": uncovered,
            },
        },
    }


@app.post("/api/health/fix")
async def health_fix():
    """Auto-fix common health issues."""
    articles = load_all_articles()
    if not articles:
        return {"fixed": 0, "message": "Wiki is empty"}

    fixes = []

    # Fix 1: Add missing metadata
    missing_meta = check_missing_metadata(articles)
    for issue in missing_meta:
        article_name = issue["article"]
        path = issue["path"]
        content = path.read_text(encoding="utf-8")
        missing = issue["missing"]

        # Check if there's a metadata table without bold formatting
        needs_bold = []
        for field in missing:
            # e.g. field = "**类别**", check if unbolded version exists
            plain = field.replace("**", "")
            if plain in content and field not in content:
                needs_bold.append((plain, field))

        if needs_bold:
            for plain, bold in needs_bold:
                # Replace in table context: "| 类别 |" -> "| **类别** |"
                content = content.replace(f"| {plain} |", f"| {bold} |")
            path.write_text(content, encoding="utf-8")
            fixes.append(f"Fixed metadata formatting in {article_name}: {[b for _, b in needs_bold]}")

    # Fix 2: Remove placeholder links like [[文章名]]
    broken_links = check_broken_links(articles)
    placeholder_patterns = ["文章名", "文章A", "文章B", "Article"]
    for issue in broken_links:
        link = issue["link"]
        if any(p in link for p in placeholder_patterns):
            path = issue["path"]
            content = path.read_text(encoding="utf-8")
            # Only remove if it's a standalone placeholder, not in code blocks
            old = f"[[{link}]]"
            if f"`{old}`" not in content:
                content = content.replace(old, link)
                path.write_text(content, encoding="utf-8")
                fixes.append(f"Removed placeholder link [[{link}]] in {issue['article']}")

    # Fix 3: Update INDEX.md coverage
    uncovered = check_index_coverage(articles)
    if uncovered:
        index_file = WIKI_DIR / "INDEX.md"
        if index_file.exists():
            with open(index_file, "a", encoding="utf-8") as f:
                for name in uncovered:
                    art_path, _ = articles[name]
                    category = art_path.parent.name
                    today = datetime.now().strftime("%Y-%m-%d")
                    f.write(f"\n| [[{name}]] | (auto-indexed) | {today} |")
            fixes.append(f"Added {len(uncovered)} article(s) to INDEX.md")

    return {
        "fixed": len(fixes),
        "details": fixes,
    }


# ── API: Config info ──────────────────────────────────────────────────────────
@app.get("/api/config")
async def get_config():
    """Get current LLM configuration."""
    _, _, cfg = get_llm()
    key_hint = f"...{cfg.api_key[-6:]}" if len(cfg.api_key) > 6 else "(local)"
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "api_key_hint": key_hint,
        "version": __version__,
        "author": __author__,
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"\n  LLM Wiki Web App v{__version__}")
    print(f"  by {__author__}")
    print(f"  http://localhost:8000\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
