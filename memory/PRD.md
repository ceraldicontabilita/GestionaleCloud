# PRD — Ceraldi ERP (Gestionale Aziendale)

## Problema Originale
ERP full-stack (React + FastAPI + MongoDB) con gravi problemi di stabilità:
- Loop di reload infiniti dell'UI
- Bottoni di pagamento inattivi / non aggiornano lo stato
- Polling aggressivo in background (email ogni 10min) che saturava l'event loop
- Scheduler IMAP bloccante su thread asyncio principale

## Stack Tecnico
- Frontend: React 18 + Vite + React Query (4 file) + axios
- Backend: FastAPI (Python) + Motor (MongoDB async driver)
- DB: MongoDB Atlas `azienda_erp_db`
- Design System: CSS inline via `lib/utils.js` (VIETATO Tailwind/Shadcn nelle pagine gestionali)
- WebSocket: FastAPI WebSocket + manager custom (`websocket_manager.py`)

## Architettura Principale
```
/app
├── app/
│   ├── main.py                         (scheduler DISABILITATO - IMAP sincrono)
│   ├── scheduler.py                    (+ notify_data_change() x3 task)
│   ├── routers/
│   │   ├── websocket_realtime.py       (endpoint /ws/notifications, /ws/dashboard)
│   │   ├── fatture_module/
│   │   │   ├── crud.py                 (fix: campo pagato non hardcodato)
│   │   │   └── pagamento.py            (fix: bug auto-riconciliazione banca)
│   │   └── cucina/                     (ricette, food_cost, prodotti_vendita, ordini_fornitori)
│   └── services/
│       ├── websocket_manager.py        (ConnectionManager, notify_data_change)
│       └── email_monitor_service.py    (DISABILITATO - credenziali IMAP sincrono)
└── frontend/src/
    ├── main.jsx                        (StrictMode RIMOSSO)
    ├── App.jsx                         (+ useWebSocketNotifications() al root)
    ├── hooks/useWebSocket.js           (RISCRITTO - WebSocket reale + backoff)
    ├── lib/queryClient.js              (refetchOnWindowFocus: true)
    ├── lib/utils.js                    (SORGENTE UNICA stili inline)
    ├── components/layout/TopNav.jsx    (RISCRITTO - nessun polling)
    └── pages/ (RicettarioAdmin, FoodCostAdmin, CatalogoOrdini, ProdottiVendita)
```

## Cosa è Stato Implementato

### Fix Stabilità (sessioni precedenti)
- ✅ Rimosso `<React.StrictMode>` (doppio render)  
- ✅ Rimosso polling TopNav ogni 60s (setInterval rimosso)
- ✅ Disabilitato IMAP monitor e scheduler (bloccavano event loop asyncio)
- ✅ Fix MongoDB proiezione `pagato` hardcodato a False
- ✅ Fix bug auto-riconciliazione Banca in pagamento.py
- ✅ /app/backend/tests/ chmod 555 (impedisce restart loop uvicorn)

### WebSocket Real-time (questa sessione - Apr 2026)
- ✅ `useWebSocket.js` riscritto con vera connessione WS + backoff esponenziale (max 8 retry)
- ✅ Ping keepalive ogni 45s (server timeout 60s)
- ✅ Su `data_change`: emette CustomEvent("data-refresh") + invalida React Query cache
- ✅ App.jsx monta `useWebSocketNotifications()` a root level
- ✅ queryClient.js: `refetchOnWindowFocus: true`
- ✅ vite.config.js: `ws: true` per proxy WebSocket in development
- ✅ scheduler.py: 3 task aggiornati con `notify_data_change()` calls
- ✅ 1 connessione WebSocket attiva verificata (`/api/realtime/status`)

### Fix Bug HR - cedolini.py (questa sessione - Apr 2026)
- ✅ Bug critico: l'endpoint `/api/cedolini/dipendente/{id}` cercava in collection `employees` (31 doc, senza campo `id`) invece di `dipendenti` (34 doc) → fix con fallback
- ✅ `GestioneDipendentiUnificata.jsx`: rimossi TEAM tab duplicati (Paghe/TFR), Presenze Team → "Batch Presenze"
- ✅ SecondaryTabs: "Anagrafica" rinominato "Dipendenti" (elimina duplicazione visiva)
- ✅ `GestioneDipendentiUnificata.jsx` ridisegnata: da 14 tab in 2 righe incoerenti → **5 tab Dipendente + 6 tab Team** in riga unica coerente con lib/utils.js
- ✅ Rimossi tab con API 404 (`storico-ore`, `saldo-ferie` globali)
- ✅ Nuovo tab `movimenti` unifica Bonifici + Acconti per dipendente
- ✅ Styling tab con COLORS.primary, separatori sezione, no emoji

### Immagini Tracciabilità (questa sessione - Apr 2026)
- ✅ Generate immagini AI per: Arancini Mix, Cipolline Siciliane, Iris Siciliane, Panzarotti
- ✅ Salvate in `/app/app/static/tracciabilita/uploads/`
- ✅ Aggiornato DB per 5 prodotti: Mix arancini, Cipolline, Iris, Panzarotti, Cornetto Classico
- ✅ RicettarioAdmin.jsx, FoodCostAdmin.jsx, CatalogoOrdini.jsx, ProdottiVendita.jsx
- ✅ Routers backend: /api/cucina/ricette, /food-cost/*, /prodotti-vendita/*, /ordini-fornitori/*
- ✅ CucinaHub.jsx aggiornato, main.jsx routing configurato

## Regole Design (ASSOLUTE)
- SOLO CSS inline via costanti `lib/utils.js` (COLORS, STYLES, SPACING)
- VIETATO: Shadcn/UI, classi Tailwind nelle pagine gestionali

## Credenziali Email (già in .env)
- IMAP: `ceraldigroupsrl@gmail.com` / App Password: `nugg fttp swvx djqd`
- Aruba PEC: password in .env (ARUBA_PEC_PASSWORD)
- Scheduler DISABILITATO: imaplib è sincrono, blocca event loop. Serve run_in_executor()

## Backlog Priorità

### P0 — Completato (Apr 2026)
- ✅ Import Gmail Cedolini sicuro — `asyncio.to_thread()` in `/api/cedolini/import-gmail`
- ✅ HRCedolini.jsx aggiornata: chiama `/api/cedolini`, pulsante "Importa da Gmail"
- ✅ 271 cedolini da Gmail già presenti in DB, aggiornati con mese/anno da filename

### P1 — Importante
- Riabilitazione sicura scheduler email con `asyncio.run_in_executor()` per wrappare imaplib
- Fix IMAP: wrap `fetch_aruba_invoices` e `VerbaliEmailScanner` in ThreadPoolExecutor
- Implementazione Ciclo Passivo (ISTRUZIONI_CICLO_PASSIVO.md)

### P2 — Medio
- Widget Cucina in DashboardHub.jsx (Passo 7 istruzioni V2)
- Portale.jsx: verifica/rimozione Shadcn/Tailwind rimasto
- Auth backend: Cookies HTTP-Only

### P3 — Bassa Priorità
- Google Auth Portale verifica end-to-end
