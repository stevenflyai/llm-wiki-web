#!/bin/bash
# LLM Wiki Setup Script V0.1 by Steven Lian
# Usage: bash scripts/setup.sh

set -e

echo "=================================================="
echo " LLM Wiki Setup V0.1"
echo " by Steven Lian"
echo " Inspired by Andrej Karpathy's LLM Knowledge Base"
echo "=================================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WIKI_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Summary variables ────────────────────────────────────
SUMMARY_PYTHON=""
SUMMARY_BREW=""
SUMMARY_UV=""
SUMMARY_OLLAMA=""
SUMMARY_OBSIDIAN=""
SUMMARY_ENV=""
SUMMARY_APIKEY=""
SUMMARY_WARNINGS=()

# ── Check Python version ─────────────────────────────────
echo "🐍 Checking Python..."
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo "✓ Python version: $PYTHON_VERSION"
    SUMMARY_PYTHON="✓ Python $PYTHON_VERSION"
else
    echo "✗ python3 not found, please install Python 3.10+ first"
    exit 1
fi

# ── Check / Install Homebrew ──────────────────────────────
echo ""
echo "🍺 Checking Homebrew..."
if command -v brew &>/dev/null; then
    BREW_VERSION=$(brew --version 2>&1 | head -1)
    echo "✓ Homebrew installed: $BREW_VERSION"
    SUMMARY_BREW="✓ $BREW_VERSION"
else
    echo "  Homebrew not found, installing automatically..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Refresh PATH (different paths for Apple Silicon vs Intel)
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi

    if command -v brew &>/dev/null; then
        echo "✓ Homebrew installed: $(brew --version | head -1)"
        SUMMARY_BREW="✓ $(brew --version | head -1) (newly installed)"
    else
        echo "⚠️  Homebrew installation failed, please install manually: https://brew.sh"
        SUMMARY_BREW="⚠️  Homebrew install failed"
        SUMMARY_WARNINGS+=("Homebrew install failed, some components may not auto-install")
    fi
fi

# ── Check / Install uv ───────────────────────────────────
echo ""
echo "📦 Checking uv package manager..."
if command -v uv &>/dev/null; then
    UV_VERSION=$(uv --version 2>&1)
    echo "✓ uv installed: $UV_VERSION"
    SUMMARY_UV="✓ $UV_VERSION"
else
    echo "  uv not found, installing..."
    if command -v brew &>/dev/null; then
        echo "  Installing uv via Homebrew..."
        brew install uv && echo "✓ uv installed (via Homebrew)"
    else
        echo "  Installing uv via official script..."
        curl -LsSf https://astral.sh/uv/install.sh | sh && echo "✓ uv installed"
        # Refresh PATH (installer adds to ~/.local/bin)
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if ! command -v uv &>/dev/null; then
        echo "✗ uv installation failed, please install manually: https://docs.astral.sh/uv/"
        exit 1
    fi
    SUMMARY_UV="✓ $(uv --version) (newly installed)"
    echo "✓ uv ready: $(uv --version)"
fi

# ── Install Python dependencies via uv ───────────────────
echo ""
echo "📦 Installing Python dependencies via uv..."

# Core dependencies (required)
CORE_DEPS=(
    "openai"
    "anthropic"
    "rich"
    "fastapi"
    "uvicorn"
    "jinja2"
)

# Office / PDF extraction dependencies
EXTRACT_DEPS=(
    "markitdown"
)

# Optional PDF dependencies (recommended but not required)
OPTIONAL_DEPS=(
    "pymupdf4llm"
)

echo "  Installing core dependencies..."
uv pip install "${CORE_DEPS[@]}" --quiet 2>/dev/null && echo "  ✓ Core dependencies installed" || {
    echo "  Retrying with --system flag..."
    uv pip install --system "${CORE_DEPS[@]}" --quiet && echo "  ✓ Core dependencies installed"
}

echo "  Installing document extraction dependencies..."
uv pip install "${EXTRACT_DEPS[@]}" --quiet 2>/dev/null && echo "  ✓ Extraction dependencies installed" || \
    uv pip install --system "${EXTRACT_DEPS[@]}" --quiet && echo "  ✓ Extraction dependencies installed"

echo "  Installing optional PDF dependency (pymupdf4llm)..."
uv pip install "${OPTIONAL_DEPS[@]}" --quiet 2>/dev/null && echo "  ✓ pymupdf4llm installed" || \
    uv pip install --system "${OPTIONAL_DEPS[@]}" --quiet 2>/dev/null && echo "  ✓ pymupdf4llm installed" || \
    echo "  ⚠️  pymupdf4llm install failed (optional, markitdown will be used as fallback PDF engine)"

echo ""
echo "  Installed packages:"
uv pip list 2>/dev/null | grep -iE "openai|anthropic|rich|fastapi|uvicorn|jinja2|markitdown|pymupdf" || \
    uv pip list --system 2>/dev/null | grep -iE "openai|anthropic|rich|fastapi|uvicorn|jinja2|markitdown|pymupdf"

# ── Ollama model selection and pull function ─────────────
OLLAMA_MODELS=("llama3.1:8b" "gemma4:e2b" "gemma4:e4b")

_select_and_pull_model() {
    echo ""
    echo "  Available models:"
    echo "    1) llama3.1:8b   (~4.7 GB, Meta Llama)"
    echo "    2) gemma4:e2b    (~4 GB, Google Gemma 4)"
    echo "    3) gemma4:e4b    (~9.6 GB, Google Gemma 4)"
    echo "    0) Skip, download later"
    echo ""
    printf "  Select a model to download [1/2/3/0]: "
    read -r _model_choice
    case "$_model_choice" in
        1)
            echo "  Downloading llama3.1:8b..."
            ollama pull llama3.1:8b && echo "✓ llama3.1:8b downloaded" || echo "⚠️  Download failed"
            ;;
        2)
            echo "  Downloading gemma4:e2b..."
            ollama pull gemma4:e2b && echo "✓ gemma4:e2b downloaded" || echo "⚠️  Download failed"
            ;;
        3)
            echo "  Downloading gemma4:e4b..."
            ollama pull gemma4:e4b && echo "✓ gemma4:e4b downloaded" || echo "⚠️  Download failed"
            ;;
        *)
            echo "  Skipped. You can run later: ollama pull <model-name>"
            ;;
    esac
}

# ── Check Ollama ─────────────────────────────────────────
echo ""
echo "🦙 Checking Ollama..."
if command -v ollama &> /dev/null; then
    OLLAMA_VERSION=$(ollama --version 2>/dev/null || echo "installed")
    echo "✓ Ollama installed: $OLLAMA_VERSION"
    SUMMARY_OLLAMA="✓ Ollama $OLLAMA_VERSION"

    OLLAMA_RUNNING=false
    if ollama list &>/dev/null; then
        OLLAMA_RUNNING=true
    fi

    if $OLLAMA_RUNNING; then
        # Check if any recommended model is already present
        _has_model=false
        for _m in "${OLLAMA_MODELS[@]}"; do
            if ollama list 2>/dev/null | grep -q "$_m"; then
                echo "✓ Model $_m is ready"
                _has_model=true
            fi
        done
        if ! $_has_model; then
            echo "  No recommended model found. Download one now? (y/N)"
            read -r _pull_reply
            if [[ "$_pull_reply" =~ ^[Yy]$ ]]; then
                _select_and_pull_model
            fi
        fi
    else
        echo "  Ollama service not running, starting in background..."
        ollama serve &>/dev/null &
        sleep 3
        if ollama list &>/dev/null; then
            echo "✓ Ollama service started"
        else
            echo "⚠️  Ollama service failed to start, please run manually: ollama serve"
        fi
    fi
else
    echo "⚠️  Ollama not installed"
    echo "  Ollama runs free local models, no API Key required."
    echo "  Install now? (y/N)"
    read -r _install_reply

    if [[ "$_install_reply" =~ ^[Yy]$ ]]; then
        case "$(uname -s)" in
            Darwin)
                if command -v brew &>/dev/null; then
                    brew install ollama && echo "✓ Ollama installed"
                else
                    curl -fsSL https://ollama.ai/install.sh | sh && echo "✓ Ollama installed"
                fi
                ;;
            Linux)
                curl -fsSL https://ollama.ai/install.sh | sh && echo "✓ Ollama installed"
                ;;
            *)
                echo "  ⚠️  Please visit https://ollama.ai to download and install manually"
                ;;
        esac

        if command -v ollama &>/dev/null; then
            ollama serve &>/dev/null &
            sleep 3
            echo "  Download a model? (y/N)"
            read -r _pull_reply
            if [[ "$_pull_reply" =~ ^[Yy]$ ]]; then
                _select_and_pull_model
            fi
        fi
    else
        echo "  Skipping Ollama. Please configure an API Key in .env."
        SUMMARY_OLLAMA="⚠️  Ollama skipped"
        SUMMARY_WARNINGS+=("Ollama not installed, local models unavailable")
    fi
fi
if [ -z "$SUMMARY_OLLAMA" ]; then
    if command -v ollama &>/dev/null; then
        SUMMARY_OLLAMA="✓ Ollama (newly installed)"
    else
        SUMMARY_OLLAMA="⚠️  Ollama install failed"
        SUMMARY_WARNINGS+=("Ollama installation failed")
    fi
fi

# ── Configure .env file ──────────────────────────────────
echo ""
echo "⚙️  Configuring .env file..."
if [ -f "$WIKI_ROOT/.env" ]; then
    echo "✓ .env already exists, skipping"
    SUMMARY_ENV="✓ .env exists"
else
    if [ -f "$WIKI_ROOT/.env.example" ]; then
        cp "$WIKI_ROOT/.env.example" "$WIKI_ROOT/.env"
        echo "✓ Created .env from .env.example"
        SUMMARY_ENV="✓ .env (from template)"
    else
        cat > "$WIKI_ROOT/.env" << 'EOF'
# LLM Wiki Configuration — fill in your API Key

# OpenAI
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o

# Anthropic
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-opus-4-6

# Custom OpenAI-compatible service
# CUSTOM_BASE_URL=https://api.deepseek.com/v1
# CUSTOM_API_KEY=sk-...
# CUSTOM_MODEL=deepseek-chat

# Ollama (local models, no API Key needed)
# OLLAMA_BASE_URL=http://localhost:11434/v1
# OLLAMA_MODEL=llama3.1:8b
EOF
        echo "✓ Generated .env template"
        SUMMARY_ENV="✓ .env (generated)"
    fi
    echo "  ⚠️  Please edit .env and fill in your API Key:"
    echo "     nano $WIKI_ROOT/.env"
fi

# ── Check API Key ────────────────────────────────────────
echo ""
echo "🔑 Checking API Key configuration..."
_has_env_key() {
    local val
    val=$(grep -E "^${1}=.+" "$WIKI_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" | tr -d "'")
    [ -n "$val" ]
}

if [ -n "$OPENAI_API_KEY" ] || _has_env_key "OPENAI_API_KEY"; then
    echo "✓ OpenAI API Key configured"
    SUMMARY_APIKEY="✓ OpenAI API Key"
elif [ -n "$ANTHROPIC_API_KEY" ] || _has_env_key "ANTHROPIC_API_KEY"; then
    echo "✓ Anthropic API Key configured"
    SUMMARY_APIKEY="✓ Anthropic API Key"
elif _has_env_key "CUSTOM_API_KEY"; then
    echo "✓ Custom API Key configured"
    SUMMARY_APIKEY="✓ Custom API Key"
else
    echo "⚠️  No API Key detected"
    echo "   Please edit .env to add an API Key, or use --ollama"
    SUMMARY_APIKEY="⚠️  No API Key"
    SUMMARY_WARNINGS+=("No API Key configured, edit .env or use Ollama local models")
fi

# ── Verify directory structure ────────────────────────────
echo ""
echo "📁 Verifying directory structure..."
check_dir() {
    if [ -d "$WIKI_ROOT/$1" ]; then
        echo "  ✓ $1/"
    else
        mkdir -p "$WIKI_ROOT/$1"
        echo "  ✓ $1/ (created)"
    fi
}

check_dir "raw/papers"
check_dir "raw/articles"
check_dir "raw/repos"
check_dir "raw/images"
check_dir "wiki/concepts"
check_dir "wiki/tools"
check_dir "wiki/research"
check_dir "wiki/tutorials"
check_dir "output/queries"
check_dir "output/slides"
check_dir "output/charts"
check_dir "_meta"

# ── Check / Install Obsidian ──────────────────────────────
echo ""
echo "🔮 Checking Obsidian..."
if [ -d "/Applications/Obsidian.app" ]; then
    echo "✓ Obsidian installed"
    echo "  Open this wiki in Obsidian: select directory $WIKI_ROOT"
    SUMMARY_OBSIDIAN="✓ Obsidian installed"
else
    echo "  Obsidian not found, installing automatically..."
    if command -v brew &>/dev/null; then
        brew install --cask obsidian && {
            echo "✓ Obsidian installed"
            SUMMARY_OBSIDIAN="✓ Obsidian (newly installed)"
        } || {
            echo "⚠️  Obsidian installation failed, please download manually: https://obsidian.md"
            SUMMARY_OBSIDIAN="⚠️  Obsidian install failed"
            SUMMARY_WARNINGS+=("Obsidian install failed, download manually: https://obsidian.md")
        }
    else
        echo "⚠️  Homebrew not found, cannot auto-install Obsidian"
        echo "  Please download manually: https://obsidian.md"
        SUMMARY_OBSIDIAN="⚠️  Obsidian not installed (no Homebrew)"
        SUMMARY_WARNINGS+=("Obsidian not installed, download manually: https://obsidian.md")
    fi
fi

# ── Installation summary report ──────────────────────────
echo ""
echo "=================================================="
echo " 🎉 Setup complete! Here is the installation summary"
echo "=================================================="
echo ""
echo "┌──────────────────────────────────────────────────┐"
echo "│              📋 Installation Summary              │"
echo "├──────────────────────────────────────────────────┤"
echo "│  Component       Status                           │"
echo "├──────────────────────────────────────────────────┤"
printf "│  Python        %-34s│\n" "$SUMMARY_PYTHON"
printf "│  Homebrew      %-34s│\n" "$SUMMARY_BREW"
printf "│  uv            %-34s│\n" "$SUMMARY_UV"
printf "│  Ollama        %-34s│\n" "$SUMMARY_OLLAMA"
printf "│  Obsidian      %-34s│\n" "$SUMMARY_OBSIDIAN"
printf "│  .env config   %-34s│\n" "$SUMMARY_ENV"
printf "│  API Key       %-34s│\n" "$SUMMARY_APIKEY"
echo "├──────────────────────────────────────────────────┤"
echo "│  Directories   ✓ Verified                           │"
echo "│  Python deps   ✓ Installed                         │"
echo "└──────────────────────────────────────────────────┘"

if [ ${#SUMMARY_WARNINGS[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  Action required:"
    for warn in "${SUMMARY_WARNINGS[@]}"; do
        echo "  · $warn"
    done
fi

echo ""
echo "Quick start:"
echo "  1. Edit .env and fill in your API Key"
echo "  2. Put documents in raw/ (supports .md .txt .pdf .pptx .docx .ppt .doc)"
echo "  3. Compile:      python3 scripts/compile.py"
echo "  4. Query:        python3 scripts/query.py 'your question'"
echo "  5. Health check: python3 scripts/lint.py --report"
echo "  6. Web UI:       python3 scripts/app.py  →  http://localhost:8000"
echo "                   or: bash scripts/start.sh"
echo ""
echo "Package management: uv pip install <package>  /  uv pip list"
echo ""
