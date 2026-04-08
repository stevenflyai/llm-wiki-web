#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
uv run --with fastapi --with uvicorn --with jinja2 --with rich --with openai --with anthropic python scripts/app.py "$@"
