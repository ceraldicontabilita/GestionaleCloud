#!/usr/bin/env node
// Driver for the GestionaleCloud frontend (Vite + React ERP).
// Launches the pre-installed Chromium (Playwright) against the running dev
// server and takes screenshots at a mobile or desktop viewport. Optionally
// logs in through the "Accesso rapido" PIN screen first.
//
// Usage:
//   node driver.mjs <path> [options]
//
// Options:
//   --device mobile|desktop   viewport preset (default: mobile = iPhone 12)
//   --full                    full-page screenshot (default: viewport only)
//   --out <file>              output PNG path (default: ./shot.png)
//   --base <url>              dev server base (default: http://localhost:3000)
//   --pin <digits>            type this PIN into "Accesso rapido" and submit
//   --wait <ms>              extra settle time before the shot (default: 800)
//
// Examples:
//   node driver.mjs / --device mobile --out mobile-home.png
//   node driver.mjs / --device desktop --full --out desktop-home.png
//   node driver.mjs /dashboard --pin 12345 --device mobile --out dash.png
//
// Exit codes: 0 ok, 1 bad args / launch failure, 2 navigation/timeout failure.

import { existsSync, readdirSync } from 'fs'
import { createRequire } from 'module'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

// The driver lives at <root>/.claude/skills/run-gestionale/driver.mjs, but
// playwright-core is installed in <root>/frontend/node_modules. Resolve it from
// there explicitly (ESM otherwise only walks up from the script's own folder).
const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const req = createRequire(join(REPO_ROOT, 'frontend', 'package.json'))
const { chromium } = req('playwright-core')

// --- locate the pre-installed Chromium (no download in this container) ---
function findChrome() {
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers'
  if (!existsSync(root)) return null
  const dir = readdirSync(root).find((d) => d.startsWith('chromium-') && !d.includes('headless'))
  if (!dir) return null
  const bin = `${root}/${dir}/chrome-linux/chrome`
  return existsSync(bin) ? bin : null
}

// --- parse argv ---
const args = process.argv.slice(2)
if (args.length === 0 || args[0].startsWith('--')) {
  console.error('usage: node driver.mjs <path> [--device mobile|desktop] [--full] [--out f.png] [--base url] [--pin 12345] [--wait ms]')
  process.exit(1)
}
const path = args[0]
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 && args[i + 1] ? args[i + 1] : def
}
const has = (name) => args.includes(`--${name}`)

const device = opt('device', 'mobile')
const out = opt('out', 'shot.png')
const base = opt('base', 'http://localhost:3000')
const pin = opt('pin', null)
const wait = parseInt(opt('wait', '800'), 10)
const fullPage = has('full')

const viewports = {
  mobile: { width: 390, height: 844, deviceScaleFactor: 3, isMobile: true, hasTouch: true },
  desktop: { width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
}
const vp = viewports[device]
if (!vp) {
  console.error(`unknown device "${device}" (use: mobile | desktop)`)
  process.exit(1)
}

const exe = findChrome()
if (!exe) {
  console.error('could not find Chromium under PLAYWRIGHT_BROWSERS_PATH (/opt/pw-browsers)')
  process.exit(1)
}

const url = base.replace(/\/$/, '') + (path.startsWith('/') ? path : '/' + path)

const browser = await chromium.launch({
  executablePath: exe,
  args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
})
try {
  const ctx = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: vp.deviceScaleFactor,
    isMobile: vp.isMobile,
    hasTouch: vp.hasTouch,
  })
  const page = await ctx.newPage()
  const goto = (u) =>
    page
      .goto(u, { waitUntil: 'networkidle', timeout: 30000 })
      // networkidle can hang if the backend proxy keeps polling; fall back.
      .catch(() => page.goto(u, { waitUntil: 'domcontentloaded', timeout: 30000 }))

  if (pin) {
    // Keep the session alive across hard navigations: the app re-validates the
    // token via GET /api/auth/verify on every page load and bounces to login if
    // it fails. Stub that response so reloads to guarded routes stay logged in.
    await ctx.route('**/api/auth/verify', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user: { id: 'driver', email: 'driver@local', name: 'Driver', role: 'admin' } }),
      })
    )
    // Authenticate on the root "Accesso rapido" PIN screen (writes the real JWT
    // into localStorage), then hard-navigate to the requested route.
    await goto(base.replace(/\/$/, '') + '/')
    await page.locator('input').first().click({ timeout: 5000 }).catch(() => {})
    for (const d of String(pin)) {
      await page.keyboard.type(d, { delay: 60 })
    }
    await page.getByText('Entra', { exact: false }).first().click({ timeout: 5000 }).catch(() => {})
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})
    if (path !== '/' && path !== '') await goto(url)
  } else {
    await goto(url)
  }

  await page.waitForTimeout(wait)
  await page.screenshot({ path: out, fullPage })
  console.log(`OK ${device} ${url} -> ${out}${fullPage ? ' (full page)' : ''}`)
} catch (err) {
  console.error('FAILED:', err.message)
  await browser.close()
  process.exit(2)
} finally {
  await browser.close().catch(() => {})
}
