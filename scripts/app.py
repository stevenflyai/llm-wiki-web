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
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

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
    check_content_gaps, extract_links,
)

# ── App setup ─────────────────────────────────────────────────────────────────
__version__ = "0.2"
__release_date__ = "2026-04-11"
__author__ = "Steven Lian"

app = FastAPI(title="LLM Wiki", version=__version__, docs_url="/docs")
templates = Jinja2Templates(directory=str(SCRIPTS_DIR / "templates"))

# Mount static assets (Cytoscape bundle + any future front-end vendor files)
from fastapi.staticfiles import StaticFiles
(SCRIPTS_DIR / "static").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(SCRIPTS_DIR / "static")), name="static")

# Knowledge-graph viewer routes (/graph + /graph/data.json)
from graph_routes import build_graph_router
app.include_router(build_graph_router(PROJECT_ROOT, SCRIPTS_DIR / "templates"))

FAVICON_SVG = """<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\"><rect width=\"64\" height=\"64\" rx=\"12\" fill=\"#0a0e1a\"/><path d=\"M16 18h22a10 10 0 0 1 0 20H16z\" fill=\"#00d4ff\"/><path d=\"M18 42h30v6H18z\" fill=\"#a78bfa\"/><path d=\"M24 25h14a3 3 0 0 1 0 6H24z\" fill=\"#0a0e1a\"/></svg>"""

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


_LLM_ENV_PREFIXES = (
    "ANTHROPIC_", "OPENAI_", "AZURE_OPENAI_", "CUSTOM_",
    "OLLAMA_", "LLM_PROVIDER", "LLM_TIMEOUT",
    "PDF_BACKEND", "PDF_WORKERS", "PDF_MAX_CHARS",
)


def get_llm():
    """Lazy-init LLM client. Auto-reloads if .env has changed."""
    global _llm_client, _llm_client_type, _llm_cfg
    if _llm_client is None or _env_changed():
        # Snapshot LLM-related env vars, clear them, reload from .env, then
        # restore any non-LLM vars that were accidentally caught.
        saved = {k: v for k, v in os.environ.items()
                 if k.startswith(_LLM_ENV_PREFIXES)}
        for key in saved:
            del os.environ[key]
        from config import _load_dotenv, _PROJECT_ROOT
        _load_dotenv(_PROJECT_ROOT / ".env")
        _llm_client, _llm_client_type, _llm_cfg = cfg_setup()
    return _llm_client, _llm_client_type, _llm_cfg


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


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
    # Validate path stays within WIKI_DIR (prevent path traversal)
    wiki_root = WIKI_DIR.resolve()
    target = (WIKI_DIR / category / f"{name}.md").resolve()
    if not str(target).startswith(str(wiki_root) + os.sep) and target != wiki_root:
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    if not target.exists():
        # Search for partial match within the resolved category dir
        cat_dir = (WIKI_DIR / category).resolve()
        if str(cat_dir).startswith(str(wiki_root) + os.sep) and cat_dir.is_dir():
            for md_file in cat_dir.glob("*.md"):
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
    failed = state.get("failed_files", {})

    files = []
    for ext in SUPPORTED_EXTENSIONS:
        for f in RAW_DIR.rglob(f"*{ext}"):
            key = str(f)
            if key in processed:
                status = "modified" if needs_compile(f, processed) else "compiled"
            elif key in failed:
                # Failed before: show "failed" unless file content changed (then "modified")
                stored_hash = failed[key].get("hash", "")
                if stored_hash and file_hash(f) != stored_hash:
                    status = "modified"
                else:
                    status = "failed"
            else:
                status = "new"

            entry = {
                "name": f.name,
                "path": str(f.relative_to(PROJECT_ROOT)),
                "size": f.stat().st_size,
                "status": status,
                "category": f.parent.name,
            }
            if status == "failed":
                entry["error"] = failed[key].get("error", "Unknown error")
                entry["failed_at"] = failed[key].get("timestamp", "")
            files.append(entry)

    # Sort: new first, then failed, then modified, then compiled
    status_order = {"new": 0, "failed": 1, "modified": 2, "compiled": 3}
    files.sort(key=lambda x: (status_order.get(x["status"], 9), x["name"]))
    return {
        "files": files,
        "total": len(files),
        "pending": sum(1 for f in files if f["status"] in ("new", "modified")),
        "failed": sum(1 for f in files if f["status"] == "failed"),
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
        queue: asyncio.Queue = asyncio.Queue()

        def _emit(data: dict):
            """Thread-safe: put SSE message into the async queue."""
            queue.put_nowait(data)

        def _compile_worker():
            """Run all blocking compile work in a thread."""
            try:
                _emit({'type': 'log', 'message': 'Initializing LLM client...'})
                client, client_type, cfg = get_llm()

                state = load_state()
                processed = state.get("processed_files", {})
                failed_files: dict = state.get("failed_files", {})
                existing_wiki = [p.stem for p in get_wiki_articles()]

                raw_files = []
                for ext in SUPPORTED_EXTENSIONS:
                    raw_files.extend(RAW_DIR.rglob(f"*{ext}"))
                raw_files = sorted(raw_files)

                files_to_compile = [f for f in raw_files if needs_compile(f, processed, failed_files)]

                effective_backend = detect_pdf_backend()
                if not effective_backend:
                    files_to_compile = [f for f in files_to_compile if f.suffix.lower() != ".pdf"]

                if not files_to_compile:
                    # Still refresh the graph artifact in case wiki/ was edited directly
                    try:
                        from graph_build import run_graph_build
                        graph = run_graph_build(
                            WIKI_DIR, PROJECT_ROOT / "output" / "graph",
                            client=client, client_type=client_type, cfg=cfg,
                            call_llm=cfg_call_llm, no_enrich=False,
                        )
                        _emit({'type': 'log',
                               'message': f'Graph rebuilt: {len(graph.nodes)} nodes, {len(graph.edges)} edges'})
                    except Exception as exc:
                        _emit({'type': 'log', 'message': f'graph rebuild failed: {exc}'})
                    _emit({'type': 'complete', 'message': 'No new files to compile. All files are up to date.', 'compiled': 0})
                    return

                total = len(files_to_compile)
                _emit({'type': 'log', 'message': f'Found {total} file(s) to compile'})

                pdf_list = [f for f in files_to_compile if f.suffix.lower() == ".pdf"]
                pdf_cache = {}
                if pdf_list:
                    _emit({'type': 'log', 'message': f'Extracting text from {len(pdf_list)} PDF(s)...'})
                    pdf_cache = prefetch_pdfs(pdf_list, effective_backend, cfg.pdf_workers)
                    _emit({'type': 'log', 'message': 'PDF extraction complete'})

                compiled = 0
                failed = 0
                for i, raw_file in enumerate(files_to_compile, 1):
                    fname = raw_file.name
                    _emit({'type': 'progress', 'current': i, 'total': total, 'file': fname, 'message': f'[{i}/{total}] Compiling {fname}...'})

                    result, error = compile_file(
                        raw_file, client, client_type, cfg, existing_wiki,
                        dry_run=False,
                        pdf_backend=effective_backend,
                        pdf_cache=pdf_cache,
                    )

                    if result:
                        processed[str(raw_file)] = file_hash(raw_file)
                        failed_files.pop(str(raw_file), None)
                        compiled += 1
                        existing_wiki.append(result.stem)
                        _emit({'type': 'log', 'message': f'  -> {result.stem}'})
                    else:
                        failed += 1
                        failed_files[str(raw_file)] = {
                            "error": error or "Unknown error",
                            "hash": file_hash(raw_file),
                            "timestamp": datetime.now().isoformat(),
                        }
                        _emit({'type': 'log', 'message': f'  -> Failed: {error or "Unknown error"}'})

                state["processed_files"] = processed
                state["failed_files"] = failed_files
                if compiled > 0 or failed > 0:
                    state["last_compile"] = datetime.now().isoformat()
                    state["total_raw_files"] = len(raw_files)
                    state["total_wiki_articles"] = len(get_wiki_articles())
                save_state(state)
                if compiled > 0:
                    append_log(f"Web compile: {compiled} articles (failed: {failed})")

                # ── Regenerate knowledge graph artifact ──
                try:
                    from graph_build import run_graph_build

                    def _on_tagline_fail(node_id: str, exc: Exception) -> None:
                        _emit({'type': 'log', 'message': f'tagline failed {node_id}: {exc}'})

                    graph = run_graph_build(
                        WIKI_DIR,
                        PROJECT_ROOT / "output" / "graph",
                        client=client,
                        client_type=client_type,
                        cfg=cfg,
                        call_llm=cfg_call_llm,
                        no_enrich=False,
                        on_tagline_failure=_on_tagline_fail,
                    )
                    append_log(f"graph rebuilt ({len(graph.nodes)} nodes, {len(graph.edges)} edges)")
                    _emit({'type': 'log',
                           'message': f'Graph rebuilt: {len(graph.nodes)} nodes, {len(graph.edges)} edges'})
                except Exception as exc:
                    _emit({'type': 'log', 'message': f'graph rebuild failed: {exc}'})

                _emit({'type': 'complete', 'message': f'Done! Compiled {compiled} article(s), failed {failed}', 'compiled': compiled, 'failed': failed})

            except BaseException as e:
                # Catch BaseException (not just Exception) so SystemExit/KeyboardInterrupt
                # from misbehaving callees (e.g. SDKs that sys.exit on ImportError)
                # still surface as a UI error rather than tearing the SSE stream.
                msg = str(e) or e.__class__.__name__
                _emit({'type': 'error', 'message': msg})
            finally:
                _emit(None)  # sentinel to signal completion

        # Start blocking work in a background thread
        task = asyncio.get_event_loop().run_in_executor(None, _compile_worker)

        try:
            while True:
                data = await queue.get()
                if data is None:
                    break
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            _compile_running = False
            await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/compile/retry")
async def compile_retry():
    """Clear failed state so files can be recompiled."""
    state = load_state()
    cleared = len(state.get("failed_files", {}))
    state["failed_files"] = {}
    save_state(state)
    return {"cleared": cleared, "message": f"Cleared {cleared} failed file(s). Click Compile to retry."}


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


# ── API: Query ────────────────────────────────────────────────────────────────
@app.post("/api/query")
async def query_api(body: QueryRequest):
    """Query the wiki knowledge base."""
    question = body.question.strip()
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
    safe_q = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff._-]', '_', question[:30]).strip('_')
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


# ── API: Analytics ────────────────────────────────────────────────────────────
@app.get("/api/analytics/density")
async def analytics_density():
    """Knowledge density: article count per category and topic."""
    items = []
    for md_file in WIKI_DIR.rglob("*.md"):
        if md_file.name in ("INDEX.md", "LOG.md"):
            continue
        category = md_file.parent.name
        if category == "wiki":
            category = "other"
        items.append({"category": category, "topic": md_file.stem, "count": 1})
    cat_summary = dict(Counter(r["category"] for r in items))
    return {"items": items, "category_summary": cat_summary}


@app.get("/api/analytics/timeline")
async def analytics_timeline():
    """Compile history: article creation dates by category."""
    raw_items = []
    for md_file in WIKI_DIR.rglob("*.md"):
        if md_file.name in ("INDEX.md", "LOG.md"):
            continue
        category = md_file.parent.name
        if category == "wiki":
            category = "other"
        mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
        raw_items.append((mtime.strftime("%Y-%m-%d"), category))
    agg = Counter(raw_items)
    timeline = [{"date": k[0], "category": k[1], "count": v} for k, v in agg.items()]
    timeline.sort(key=lambda x: x["date"])
    return {"items": timeline}


@app.get("/api/analytics/citations")
async def analytics_citations():
    """Citation network: in-degree and out-degree for each article."""
    articles = load_all_articles()
    out_links = {}
    in_links = defaultdict(list)
    for name, (path, content) in articles.items():
        links = extract_links(content)
        targets = list(set(link.split('|')[0].strip() for link in links))
        out_links[name] = targets
        for t in targets:
            in_links[t].append(name)
    results = []
    for name in articles:
        results.append({
            "article": name,
            "in_degree": len(in_links.get(name, [])),
            "out_degree": len(out_links.get(name, [])),
            "links": out_links.get(name, []),
        })
    results.sort(key=lambda x: x["in_degree"], reverse=True)
    return {"items": results}


@app.get("/api/health/gaps")
async def health_gaps(min_articles: int = 3):
    """Active knowledge gap prompts."""
    articles = load_all_articles()
    if not articles:
        return {"items": [], "min_articles": min_articles}
    gaps = check_content_gaps(articles, min_articles)
    return {"items": gaps, "min_articles": min_articles}


# ── API: Config info ──────────────────────────────────────────────────────────
@app.get("/api/config")
async def get_config():
    """Get current LLM configuration."""
    _, _, cfg = get_llm()
    key_hint = f"...{cfg.api_key[-4:]}" if len(cfg.api_key) > 4 else "(local)"
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "api_key_hint": key_hint,
        "version": __version__,
        "release_date": __release_date__,
        "author": __author__,
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"\n  LLM Wiki Web App v{__version__}")
    print(f"  by {__author__}")
    print(f"  http://localhost:8000\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
