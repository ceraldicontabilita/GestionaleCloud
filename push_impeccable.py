import asyncio, base64, httpx

GITHUB_TOKEN = "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"
REPO = "ceraldicontabilita/gestionale2"
BRANCH = "main"
BASE = "https://api.github.com"
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json", "X-GitHub-Api-Version": "2022-11-28"}

FILES = {
"PRODUCT.md": "# PRODUCT.md — Gestionale2 / Ceraldi Group SRL\n\n## Who\n\n**Product:** gestionale2 — ERP interno full-stack per Ceraldi Group SRL, Napoli.\n**Owner:** Enzo Ceraldi.\n**Users:** Team interno ~16 persone.\n\n## Strategic principles\n\n1. Densità controllata\n2. Gerarchia immediata — stato record leggibile a colpo d'occhio\n3. Azioni vicine ai dati\n4. Zero ambiguità cromatica — rosso=errore, verde=ok, oro=attenzione\n5. Feedback immediato entro 200ms\n6. Mobile-first per l'app — touch target 48px\n\n## Anti-patterns\n- Testo grigio su sfondo colorato\n- Card annidate in card\n- Gradienti purple/blue\n- Font Inter/Roboto/Arial\n- Border-radius > 8px su dati\n- Modale senza overlay\n",
"DESIGN.md": "# DESIGN.md — Gestionale2 Design System\n\n## Colors Web ERP\n--color-navy: oklch(20% 0.04 240)\n--color-gold: oklch(56% 0.12 75)\n--color-surface: oklch(98% 0.005 240)\n--color-ok: oklch(52% 0.14 145)\n--color-warn: oklch(62% 0.14 75)\n--color-error: oklch(50% 0.18 25)\n\n## Colors Mobile\n--mobile-viola: oklch(38% 0.18 285)\n--mobile-navy: oklch(18% 0.06 270)\n\n## Typography\nWeb: DM Sans (UI), DM Serif Display (heading), JetBrains Mono (numeri)\nMobile: Plus Jakarta Sans\n",
"frontend/src/styles/tokens.css": "@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500&display=swap');\n\n:root {\n  --color-navy: oklch(20% 0.04 240);\n  --color-gold: oklch(56% 0.12 75);\n  --color-gold-light: oklch(70% 0.10 75);\n  --color-surface: oklch(98% 0.005 240);\n  --color-surface-2: oklch(95% 0.008 240);\n  --color-border: oklch(88% 0.01 240);\n  --color-text: oklch(18% 0.02 240);\n  --color-text-muted: oklch(48% 0.015 240);\n  --color-ok: oklch(52% 0.14 145);\n  --color-warn: oklch(62% 0.14 75);\n  --color-error: oklch(50% 0.18 25);\n  --color-info: oklch(52% 0.12 240);\n  --mobile-viola: oklch(38% 0.18 285);\n  --mobile-navy: oklch(18% 0.06 270);\n  --mobile-surface: oklch(25% 0.05 275);\n  --mobile-text: oklch(96% 0.005 270);\n  --mobile-accent: oklch(72% 0.15 285);\n  --font-display: 'DM Serif Display', Georgia, serif;\n  --font-ui: 'DM Sans', system-ui, sans-serif;\n  --font-mono: 'JetBrains Mono', monospace;\n  --text-xs: 11px; --text-sm: 13px; --text-base: 15px;\n  --text-lg: 18px; --text-xl: 22px; --text-2xl: 28px;\n  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;\n  --space-6: 24px; --space-8: 32px; --space-12: 48px;\n  --cell-px: 12px; --cell-py: 8px;\n  --radius: 4px; --radius-md: 6px; --radius-lg: 8px;\n  --shadow-sm: 0 1px 2px oklch(0% 0 0 / 8%);\n  --shadow-md: 0 4px 12px oklch(0% 0 0 / 12%);\n  --shadow-xl: 0 16px 48px oklch(0% 0 0 / 20%);\n  --transition-fast: 100ms ease-out;\n  --transition-base: 200ms ease-out;\n  --transition-slow: 300ms ease-out;\n}\n\n*, *::before, *::after { box-sizing: border-box; }\nbody { font-family: var(--font-ui); font-size: var(--text-base); color: var(--color-text); background: var(--color-surface); -webkit-font-smoothing: antialiased; }\n.badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: var(--radius); font-size: var(--text-xs); font-weight: 600; white-space: nowrap; }\n.badge--ok { background: var(--color-ok); color: #fff; }\n.badge--error { background: var(--color-error); color: #fff; }\n.badge--warn { background: var(--color-warn); color: #fff; }\n.badge--draft { background: var(--color-border); color: var(--color-text-muted); }\n.btn { display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: var(--radius); font-family: var(--font-ui); font-size: var(--text-sm); font-weight: 700; cursor: pointer; border: 2px solid transparent; min-height: 36px; transition: background 100ms ease-out; }\n.btn--primary { background: var(--color-gold); color: var(--color-navy); border-color: var(--color-gold); }\n.btn--primary:hover { background: var(--color-gold-light); }\n.btn--secondary { background: transparent; color: var(--color-navy); border-color: var(--color-navy); }\n.btn--danger { background: var(--color-error); color: #fff; }\n.data-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }\n.data-table th { background: var(--color-navy); color: #fff; font-weight: 600; font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.5px; padding: var(--cell-py) var(--cell-px); text-align: left; }\n.data-table td { padding: var(--cell-py) var(--cell-px); border-bottom: 1px solid var(--color-border); }\n.data-table tr:hover td { background: var(--color-surface-2); }\n.data-table .amount { text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }\n.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(2px); display: flex; align-items: center; justify-content: center; z-index: 1000; }\n.modal-panel { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); box-shadow: var(--shadow-xl); min-width: 480px; max-width: 90vw; max-height: 90vh; overflow-y: auto; }\n",
}

async def get_head_sha(c):
    r = await c.get(f"{BASE}/repos/{REPO}/git/refs/heads/{BRANCH}", headers=HEADERS)
    r.raise_for_status(); return r.json()["object"]["sha"]

async def get_tree_sha(c, sha):
    r = await c.get(f"{BASE}/repos/{REPO}/git/commits/{sha}", headers=HEADERS)
    r.raise_for_status(); return r.json()["tree"]["sha"]

async def blob(c, content):
    r = await c.post(f"{BASE}/repos/{REPO}/git/blobs", headers=HEADERS, json={"content": content, "encoding": "utf-8"})
    r.raise_for_status(); return r.json()["sha"]

async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        head = await get_head_sha(c)
        tree_sha = await get_tree_sha(c, head)
        blobs = []
        for path, content in FILES.items():
            b = await blob(c, content)
            blobs.append({"path": path, "mode": "100644", "type": "blob", "sha": b})
            print(f"  ✅ {path}")
        r = await c.post(f"{BASE}/repos/{REPO}/git/trees", headers=HEADERS, json={"base_tree": tree_sha, "tree": blobs})
        r.raise_for_status(); new_tree = r.json()["sha"]
        r = await c.post(f"{BASE}/repos/{REPO}/git/commits", headers=HEADERS, json={"message": "[impeccable] Aggiunge design system", "tree": new_tree, "parents": [head], "author": {"name": "GestionaleAgent", "email": "agent@gestionale2.ai"}})
        r.raise_for_status(); new_sha = r.json()["sha"]
        r = await c.patch(f"{BASE}/repos/{REPO}/git/refs/heads/{BRANCH}", headers=HEADERS, json={"sha": new_sha})
        r.raise_for_status()
        print(f"\n✅ Commit: {new_sha[:7]}")

asyncio.run(main())
