#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — MeetAssist launcher
#
# What this script does:
#   1. Creates a Python virtual environment (.venv/) if it doesn't exist
#   2. Installs / upgrades all pip dependencies into the venv
#   3. Installs system libraries (portaudio, tkinter) on first run if needed
#   4. Copies .env.example → .env if no .env exists yet
#   5. Activates the venv and starts main.py
#
# Usage:
#   bash run.sh            # normal launch
#   bash run.sh --reset    # delete venv and reinstall everything
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="python3"
PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
REQ_FILE="$SCRIPT_DIR/requirements.txt"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[MeetAssist]${RESET} $*"; }
success() { echo -e "${GREEN}[MeetAssist]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[MeetAssist]${RESET} $*"; }
error()   { echo -e "${RED}[MeetAssist] ERROR:${RESET} $*" >&2; }

echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD} ✦  MeetAssist — AI Meeting Assistant${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# ── --reset flag ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--reset" ]]; then
    warn "--reset flag detected. Removing existing virtual environment…"
    rm -rf "$VENV_DIR"
    success "Virtual environment removed. Rebuilding from scratch."
fi

# ── System dependency check (Linux only, first run) ───────────────────────────
_SYSLIBS_MARKER="$VENV_DIR/.syslibs_installed"
if [[ ! -f "$_SYSLIBS_MARKER" ]] && [[ "$(uname -s)" == "Linux" ]]; then
    info "Checking system libraries…"

    _MISSING=()
    python3 -c "import tkinter" 2>/dev/null || _MISSING+=("python3-tk")
    pkg-config --exists portaudio-2.0 2>/dev/null || \
        dpkg -s portaudio19-dev &>/dev/null 2>&1 || _MISSING+=("portaudio19-dev")

    if [[ ${#_MISSING[@]} -gt 0 ]]; then
        warn "Missing system libraries: ${_MISSING[*]}"
        warn "Attempting to install via apt-get (sudo required)…"
        if sudo apt-get install -y "${_MISSING[@]}"; then
            success "System libraries installed."
        else
            error "Could not install system libraries automatically."
            error "Please run manually: sudo apt-get install -y ${_MISSING[*]}"
            exit 1
        fi
    else
        info "System libraries already present."
    fi
    touch "$_SYSLIBS_MARKER" 2>/dev/null || true
fi

# ── Create virtual environment ────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment at .venv/ …"
    $PYTHON -m venv "$VENV_DIR"
    success "Virtual environment created."
else
    info "Using existing virtual environment at .venv/"
fi

# ── Install / sync Python dependencies ────────────────────────────────────────
_DEPS_MARKER="$VENV_DIR/.deps_installed"
_REQ_HASH=""
if command -v md5sum &>/dev/null; then
    _REQ_HASH="$(md5sum "$REQ_FILE" 2>/dev/null | awk '{print $1}')"
elif command -v md5 &>/dev/null; then
    _REQ_HASH="$(md5 -q "$REQ_FILE" 2>/dev/null)"
fi

_PREV_HASH=""
[[ -f "$_DEPS_MARKER" ]] && _PREV_HASH="$(cat "$_DEPS_MARKER")"

if [[ "$_REQ_HASH" != "$_PREV_HASH" ]]; then
    info "Installing/updating Python dependencies…"
    "$PIP" install --upgrade pip --quiet
    "$PIP" install -r "$REQ_FILE" --quiet
    echo "$_REQ_HASH" > "$_DEPS_MARKER"
    success "Dependencies installed."
else
    info "Dependencies up to date."
fi

# ── .env file handling ────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        success "Created .env from .env.example"
        echo ""
        warn "┌──────────────────────────────────────────────────────┐"
        warn "│  ACTION REQUIRED                                      │"
        warn "│  Edit .env and set your OPENAI_API_KEY before launch  │"
        warn "└──────────────────────────────────────────────────────┘"
        echo ""
        # Open the .env file in the default editor if interactive
        if [[ -t 1 ]]; then
            read -r -p "Open .env in editor now? [y/N] " REPLY
            if [[ "$REPLY" =~ ^[Yy]$ ]]; then
                "${EDITOR:-nano}" "$ENV_FILE"
            fi
        fi
    else
        warn ".env.example not found — .env not created. Using config.json or setup dialog."
    fi
else
    info ".env file found."
fi

# ── Validate API key is set ───────────────────────────────────────────────────
_API_KEY="${OPENAI_API_KEY:-}"
if [[ -z "$_API_KEY" ]] && [[ -f "$ENV_FILE" ]]; then
    # Try to extract from .env directly for this shell (dotenv doesn't auto-load in bash)
    _API_KEY="$(grep -E '^OPENAI_API_KEY=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '"'\'' ')"
fi

if [[ -z "$_API_KEY" ]] || [[ "$_API_KEY" == "sk-..." ]]; then
    warn "OPENAI_API_KEY is not set or still has the placeholder value."
    warn "The app's setup dialog will ask for it on first launch."
fi

# ── Create app data directory ──────────────────────────────────────────────────
mkdir -p "$HOME/.meetassist"

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
info "Launching MeetAssist…"
info "Hotkeys: Ctrl+Shift+H (toggle)  Ctrl+Shift+A (ask)  Ctrl+Shift+Q (quit)"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""

# Export env vars from .env into this shell so the Python process inherits them
if [[ -f "$ENV_FILE" ]]; then
    set -a  # auto-export all variables defined below
    # shellcheck disable=SC1090
    source "$ENV_FILE" 2>/dev/null || true
    set +a
fi

cd "$SCRIPT_DIR"
exec "$PYTHON_VENV" main.py "$@"
