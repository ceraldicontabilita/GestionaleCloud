#!/bin/bash
# SessionStart hook for Claude Code on the web.
# Installs backend (Python) and frontend (Node) dependencies so that tests,
# linters and the dev server work inside the ephemeral web container.
#
# Synchronous (no async block): the session waits until dependencies are ready,
# which avoids race conditions where Claude runs tests/linters before install.
#
# SessionStart fires on startup AND on resume/clear/compact, so every step is
# made idempotent and cheap-to-skip: a resume/compact must not re-install or
# re-append anything when the container already has the dependencies.
set -euo pipefail

# Only run inside Claude Code on the web (remote). No-op for local sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT"

# retry <max> <cmd...> — run cmd, retrying up to <max> times with linear backoff.
retry() {
  local max="$1"; shift
  local n=1
  until "$@"; do
    if [ "$n" -ge "$max" ]; then
      return 1
    fi
    echo "[session-start] attempt $n/$max failed; retrying in $((n * 2))s..." >&2
    sleep "$((n * 2))"
    n=$((n + 1))
  done
}

# ---- Backend: Python virtualenv + dependencies ----
# Isolated venv: the container's system Python mixes Debian-managed packages
# that conflict with the pinned versions in backend/requirements.txt.
echo "[session-start] Backend (Python) dependencies..."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
# Skip the (slow) reinstall on resume/compact when the venv is already usable.
if .venv/bin/python -c 'import fastapi, pytest' >/dev/null 2>&1; then
  echo "[session-start] Backend deps already present, skipping install."
else
  # Backend hosts the real test suite, so fail hard if it cannot install.
  retry 3 .venv/bin/python -m pip install --quiet --upgrade pip
  retry 3 .venv/bin/python -m pip install --quiet -r backend/requirements.txt
fi

# Persist the virtualenv for the whole session so pytest/python/flake8/black/
# mypy resolve from it. Append only once — guard against duplicate lines piling
# up across repeated SessionStart fires.
if [ -n "${CLAUDE_ENV_FILE:-}" ] && ! grep -qF "$ROOT/.venv/bin" "$CLAUDE_ENV_FILE" 2>/dev/null; then
  {
    echo "export VIRTUAL_ENV=\"$ROOT/.venv\""
    echo "export PATH=\"$ROOT/.venv/bin:\$PATH\""
  } >> "$CLAUDE_ENV_FILE"
fi

# ---- Frontend: Node dependencies ----
# NOTE: the project standardises on yarn (see README) and yarn.lock remains the
# source of truth in the repo. However yarn 1's bundled HTTP client aborts on
# large package tarballs through the sandbox network proxy, so it cannot install
# reliably here. We therefore use npm purely as an ephemeral installer inside the
# web container; the generated package-lock.json is git-ignored and never
# committed, so it does not interfere with the yarn workflow.
echo "[session-start] Frontend (Node) dependencies..."
cd "$ROOT/frontend"
if [ -d node_modules ]; then
  echo "[session-start] Frontend deps already present, skipping install."
elif retry 3 npm install --no-audit --no-fund; then
  echo "[session-start] Frontend deps installed."
else
  # Best-effort: the real test suite is the Python backend, so a flaky frontend
  # install must not abort session startup. Warn and continue.
  echo "[session-start] WARNING: frontend 'npm install' failed; run it manually in frontend/." >&2
fi

echo "[session-start] Dependencies ready."
