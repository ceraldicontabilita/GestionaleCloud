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

> The backend (FastAPI on `:8001`) needs MongoDB and is **not** required for the
> frontend to render. Without it, the dev server still serves the app shell and
> the **login screen**; authenticated pages need the backend (see Gotchas).

## Prerequisites

Node deps are installed by the SessionStart hook (or `cd frontend && yarn install`).
The driver additionally needs `playwright-core`, which is **not** a project
dependency — install it ephemerally (don't commit it to `package.json`):

```bash
cd frontend && npm install --no-save --no-audit --no-fund playwright-core
```

Chromium itself is pre-installed at `$PLAYWRIGHT_BROWSERS_PATH` (`/opt/pw-browsers`);
the driver finds it automatically. Do **not** run `playwright install`.

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
- **Authenticated pages need the backend.** Login posts a 6-digit PIN to
  `/api` (proxied to `:8001`); with no FastAPI + MongoDB + seeded PIN, `--pin`
  fails with "PIN non valido" and you stay on the login screen. The driver
  still screenshots whatever rendered. To reach inner pages (dashboard, tables —
  where most responsive issues live), start the backend with a database first.
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
