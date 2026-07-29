#!/usr/bin/env bash
#
# TimeLogger installer
# ---------------------
# Sets up TimeLogger on a fresh machine so you can run it with a single alias,
# per the README. Safe to re-run: the shell alias is written inside an idempotent
# marker block, so running this again updates rather than duplicates it.
#
# What it does:
#   1. Checks prerequisites (git, python >= 3.10, uv).
#   2. Creates the virtual environment and installs dependencies via `uv sync`.
#   3. Creates .env from .env.example if it doesn't exist (and reminds you to edit it).
#   4. Installs/refreshes a shell alias that runs the script from anywhere.
#
# Usage:
#   ./install.sh [--command NAME] [--rc PATH] [--no-alias]
#
#   --command NAME   Name of the alias/command to create (default: logtime).
#   --rc PATH        Shell rc file to modify (default: auto-detected, e.g. ~/.bashrc).
#   --no-alias       Do everything except touch the shell rc file.
#
set -euo pipefail

# --- Configuration / arguments ------------------------------------------------

COMMAND_NAME="logtime"
RC_FILE=""
INSTALL_ALIAS=1

# Resolve the directory this script lives in (the project root), regardless of CWD.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="${PROJECT_DIR}/app/time_logger.py"

MARKER_BEGIN="# >>> TimeLogger alias >>>"
MARKER_END="# <<< TimeLogger alias <<<"

info()  { printf '\033[0;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[0;32m  ✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[0;33m  !\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[0;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --command) COMMAND_NAME="${2:?--command needs a value}"; shift 2 ;;
        --command=*) COMMAND_NAME="${1#*=}"; shift ;;
        --rc) RC_FILE="${2:?--rc needs a value}"; shift 2 ;;
        --rc=*) RC_FILE="${1#*=}"; shift ;;
        --no-alias) INSTALL_ALIAS=0; shift ;;
        -h|--help)
            grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'
            exit 0 ;;
        *) die "Unknown argument: $1 (try --help)" ;;
    esac
done

# --- 1. Prerequisites ---------------------------------------------------------

info "Checking prerequisites"

command -v git >/dev/null 2>&1 || die "git is not installed. Install git and re-run."
ok "git found"

if command -v uv >/dev/null 2>&1; then
    ok "uv found ($(uv --version 2>/dev/null || echo 'version unknown'))"
else
    die "uv is not installed. Install it from https://docs.astral.sh/uv/ and re-run."
fi

# Python >= 3.10. uv can manage Python itself, so treat a missing system python as a warning.
PY_BIN="$(command -v python3 || command -v python || true)"
if [ -n "$PY_BIN" ]; then
    PY_VER="$("$PY_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
    if "$PY_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)' 2>/dev/null; then
        ok "python ${PY_VER} found"
    else
        warn "system python is ${PY_VER} (< 3.10); uv will fetch a suitable Python during sync"
    fi
else
    warn "no system python found; uv will fetch a suitable Python during sync"
fi

[ -f "$SCRIPT_PATH" ] || die "Expected script not found at ${SCRIPT_PATH}. Run this from inside the cloned repo."

# --- 2. Virtual environment + dependencies ------------------------------------

info "Creating virtual environment and installing dependencies"
(
    cd "$PROJECT_DIR"
    uv sync
)
ok "Dependencies installed into ${PROJECT_DIR}/.venv"

# --- 3. .env file -------------------------------------------------------------

info "Checking configuration (.env)"
if [ -f "${PROJECT_DIR}/.env" ]; then
    ok ".env already exists — leaving it untouched"
elif [ -f "${PROJECT_DIR}/.env.example" ]; then
    cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
    ok "Created .env from .env.example"
    warn "Edit ${PROJECT_DIR}/.env and fill in your JIRA email, API token, and download dir."
else
    warn "No .env.example found; skipping .env creation."
fi

# --- 4. Shell alias -----------------------------------------------------------

if [ "$INSTALL_ALIAS" -eq 0 ]; then
    info "Skipping alias installation (--no-alias)"
else
    # Auto-detect the rc file from the login shell if not provided.
    if [ -z "$RC_FILE" ]; then
        case "$(basename "${SHELL:-bash}")" in
            zsh)  RC_FILE="${HOME}/.zshrc" ;;
            bash) RC_FILE="${HOME}/.bashrc" ;;
            *)    RC_FILE="${HOME}/.bashrc" ;;
        esac
    fi

    info "Installing '${COMMAND_NAME}' alias into ${RC_FILE}"
    touch "$RC_FILE"

    # Remove any previous TimeLogger block so re-running stays idempotent.
    if grep -qF "$MARKER_BEGIN" "$RC_FILE"; then
        tmp="$(mktemp)"
        sed "/$(printf '%s' "$MARKER_BEGIN" | sed 's/[.[\*^$/]/\\&/g')/,/$(printf '%s' "$MARKER_END" | sed 's/[.[\*^$/]/\\&/g')/d" \
            "$RC_FILE" > "$tmp"
        mv "$tmp" "$RC_FILE"
        ok "Replaced existing TimeLogger alias block"
    fi

    {
        printf '%s\n' "$MARKER_BEGIN"
        printf '# Added by TimeLogger install.sh\n'
        printf '%s() {\n' "$COMMAND_NAME"
        printf '    uv run --project "%s" "%s" "$@"\n' "$PROJECT_DIR" "$SCRIPT_PATH"
        printf '}\n'
        printf '%s\n' "$MARKER_END"
    } >> "$RC_FILE"

    ok "Alias '${COMMAND_NAME}' installed"
fi

# --- Done ---------------------------------------------------------------------

info "Installation complete"
echo
echo "  Next steps:"
if [ "$INSTALL_ALIAS" -eq 0 ]; then
    echo "    • Run the tool with:  uv run --project \"${PROJECT_DIR}\" \"${SCRIPT_PATH}\""
else
    echo "    • Reload your shell:  source \"${RC_FILE}\""
    echo "    • Then run:           ${COMMAND_NAME}"
fi
if [ -f "${PROJECT_DIR}/.env" ]; then
    echo "    • Make sure ${PROJECT_DIR}/.env has your JIRA credentials and download dir."
fi
echo
