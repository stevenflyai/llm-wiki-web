"""FastAPI router for the read-only knowledge-graph viewer.

GET /graph            → HTML page (always 200, shows empty state if no data)
GET /graph/data.json  → JSON artifact from output/graph/graph.json (404 if missing,
                        500 with logged error if corrupt)

The graph artifact itself is produced by scripts/graph_build.py at the end of every
compile; this module is strictly a read-only consumer.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

__all__ = ["build_graph_router"]

log = logging.getLogger(__name__)


def build_graph_router(project_root: Path, templates_dir: Path) -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory=str(templates_dir))
    graph_json = project_root / "output" / "graph" / "graph.json"

    @router.get("/graph", response_class=HTMLResponse)
    async def graph_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="graph.html",
            context={"graph_exists": graph_json.exists()},
        )

    @router.get("/graph/data.json")
    async def graph_data() -> JSONResponse:
        if not graph_json.exists():
            return JSONResponse({"error": "graph_not_built"}, status_code=404)
        try:
            payload = json.loads(graph_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            log.error("graph_json_parse_failed: %s", exc)
            return JSONResponse({"error": "graph_json_parse_failed"}, status_code=500)
        return JSONResponse(payload)

    return router
