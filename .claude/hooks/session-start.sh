#!/bin/bash
# SessionStart hook for Claude Code on the web.
# Installs backend (Python) and frontend (Node) dependencies so that tests,
# linters and the dev server work inside the ephemeral web container.
#
# Synchronous (no async block): the session waits until dependencies are ready,
# which avoids race conditions where Claude runs tests/linters before install.
set -euo pipefail

# Only run inside Claude Code on the web (remote). No-op for local sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT"

echo "[session-start] Installing backend (Python) dependencies..."
# Use an isolated virtualenv: the container's system Python mixes Debian-managed
# packages that conflict with the pinned versions in backend/requirements.txt.
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r backend/requirements.txt

# Persist the virtualenv for the whole session so pytest/python/flake8/black/
# mypy resolve from it without needing to activate manually.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$ROOT/.venv\""
    echo "export PATH=\"$ROOT/.venv/bin:\$PATH\""
  } >> "$CLAUDE_ENV_FILE"
fi

echo "[session-start] Installing frontend (Node) dependencies..."
# NOTE: the project standardises on yarn (see README), and yarn.lock remains the
# source of truth in the repo. However yarn 1's bundled HTTP client aborts on
# large package tarballs through the sandbox network proxy, so it cannot install
# reliably here. We therefore use npm purely as an ephemeral installer inside the
# web container. The generated package-lock.json is git-ignored and never
# committed, so it does not interfere with the yarn workflow.
cd "$ROOT/frontend"
npm install --no-audit --no-fund

echo "[session-start] Dependencies installed."
