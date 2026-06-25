---
name: run-gestionale
description: Build, launch, and screenshot the GestionaleCloud frontend (Vite + React ERP). Use when asked to run, start, serve, preview, or screenshot the app — especially to check the mobile/responsive layout at a phone viewport. Drives the running app with a headless-Chromium driver.
---

# Run GestionaleCloud (frontend)

GestionaleCloud is a Vite + React ERP. This skill launches the **frontend dev
server** and drives it with a headless Chromium **driver** to take screenshots
at a mobile or desktop viewport — the primary use is inspecting the responsive
layout that can't be seen from a headless container otherwise.

All paths below are relative to the **repo root** (`<root>/`). The driver lives
at `.claude/skills/run-gestionale/driver.mjs`.

> The frontend renders the **login screen** with no backend. To screenshot the
> **authenticated** inner pages (dashboard, dipendenti, cedolini, prima-nota…)
> run the local mock backend below — no real MongoDB needed — and drive the PIN
> login with `--pin 141574`.

## Prerequisites

Node deps are installed by the SessionStart hook (or `cd frontend && yarn install`).
The driver additionally needs `playwright-core`, which is **not** a project
dependency — install it ephemerally (don't commit it to `package.json`):

```bash
cd frontend && npm install --no-save --no-audit --no-fund playwright-core
```

Chromium itself is pre-installed at `$PLAYWRIGHT_BROWSERS_PATH` (`/opt/pw-browsers`);
the driver finds it automatically. Do **not** run `playwright install`.

For the **authenticated** flow, the mock backend needs an in-memory Mongo:

```bash
.venv/bin/pip install mongomock_motor mongomock
```

## Run (agent path) — the driver

1. Start the dev server (background) and wait for it to listen on `:3000`:

```bash
cd frontend && yarn dev > /tmp/vite.log 2>&1 &
until curl -sf -o /dev/null http://localhost:3000/; do sleep 1; done
```

2. From the **repo root**, drive it with the screenshot driver:

```bash
# Mobile (iPhone-12 viewport: 390x844, DPR 3, touch), full page:
node .claude/skills/run-gestionale/driver.mjs / --device mobile --full --out mobile-home.png

# Desktop (1440x900):
node .claude/skills/run-gestionale/driver.mjs / --device desktop --out desktop-home.png
```

The driver prints `OK <device> <url> -> <out>` and writes the PNG. Then **open
the PNG and look at it** — a blank or error page means you're not done.

Driver options:

| Option | Meaning | Default |
|---|---|---|
| `<path>` (1st arg) | route to open, e.g. `/` or `/dashboard` | required |
| `--device mobile\|desktop` | viewport preset | `mobile` |
| `--full` | full-page screenshot (not just viewport) | viewport only |
| `--out <file>` | output PNG path (relative to cwd) | `shot.png` |
| `--base <url>` | dev-server base | `http://localhost:3000` |
| `--pin <digits>` | type a 6-digit PIN on the login screen, then submit | none |
| `--wait <ms>` | settle time before the shot | `800` |

## Run authenticated (inner pages)

To reach pages behind the login, also start the **mock backend** (in-memory
Mongo, seeds an admin user) and log in with the admin PIN `141574`:

```bash
# 1. mock backend on :8001 (the dev server proxies /api to it)
.venv/bin/python .claude/skills/run-gestionale/mock_backend.py &
until curl -sf -o /dev/null http://localhost:8001/api/ping; do sleep 1; done

# 2. dev server on :3000 (if not already running)
( cd frontend && yarn dev > /tmp/vite.log 2>&1 & )
until curl -sf -o /dev/null http://localhost:3000/; do sleep 1; done

# 3. screenshot an authenticated route at mobile viewport
node .claude/skills/run-gestionale/driver.mjs /dipendenti --device mobile --pin 141574 --out dipendenti.png
node .claude/skills/run-gestionale/driver.mjs /cedolini   --device mobile --pin 141574 --out cedolini.png
```

Data will be empty (the mock DB has no records), but every page's layout and
chrome render exactly as on a real device — enough to audit responsiveness.

## Run (human path)

`cd frontend && yarn dev` then open `http://localhost:3000/` in a real browser.
Useless in a headless container — use the driver above instead.

## Test

```bash
# Backend test suite (the real one — 32 tests), from repo root:
.venv/bin/python -m pytest tests/ -q
# Frontend production build sanity check:
cd frontend && yarn build
```

## Gotchas

- **Always use the driver's device emulation for mobile checks, not a raw
  `chrome --screenshot --window-size=...`.** The raw path renders the page at
  desktop width scaled down, so cards/containers appear to overflow the phone
  viewport when they actually don't. The driver sets `isMobile`/`hasTouch`/DPR
  so the layout matches a real phone.
- **`playwright-core` resolves from `frontend/node_modules`, not the skill
  folder.** The driver computes the repo root from its own path and `require`s
  it from there — so it must stay at `.claude/skills/run-gestionale/driver.mjs`
  (3 levels under the repo root). If you move it, fix `REPO_ROOT` inside.
- **Authenticated pages need the mock backend running.** `--pin` types the
  admin PIN `141574` (POST `/api/auth/pin-login`). Without `mock_backend.py` up
  it fails and you stay on login. The driver also stubs `GET /api/auth/verify`
  in the browser so a hard navigation to a guarded route doesn't bounce back to
  login — the app re-checks the token on every page load.
- **The app uses a data-router that ignores manual `history.pushState`.** So the
  driver navigates to inner routes with a **hard reload** (`page.goto`) after
  login, not client-side — which is why the verify stub above is needed.
- **PIN tokens only pass `/api/auth/verify` when `SECRET_KEY` matches.** `auth.py`
  (jwt verify) and the unified settings secret both read `SECRET_KEY` from the
  environment; if it is unset they diverge and verify 401s. `mock_backend.py`
  exports one ephemeral random value for both, so verify returns 200 locally. In
  production both read the same `SECRET_KEY` env var.
- **Chromium prints harmless `CreatePlatformSocket()` / `handshake failed`
  errors** to stderr when the backend proxy target (`:8001`) is down. The
  screenshot still succeeds; ignore them.
- **`yarn dev` runs with HMR/WS disabled** (see `vite.config.js`) — the server
  stays up but won't hot-reload; restart it after editing source.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot find package 'playwright-core'` | Run the Prerequisites install line in `frontend/`. |
| `could not find Chromium under PLAYWRIGHT_BROWSERS_PATH` | Confirm `/opt/pw-browsers/chromium-*/chrome-linux/chrome` exists; the env var is set in this container. |
| Driver exits with code 2 (navigation/timeout) | Make sure the dev server answered `http://localhost:3000/` (the `until curl` loop) before running the driver. |
| Screenshot is the login screen when you wanted an inner page | Expected without the backend — see Gotchas. |
