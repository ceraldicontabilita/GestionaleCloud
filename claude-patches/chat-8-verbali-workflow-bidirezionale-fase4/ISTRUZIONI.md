# Chat 8 — FASE 4: Workflow bidirezionale verbali (Gmail + Trigger XML + Alert 5gg)

## Punto fondamentale
**NO PEC Aruba IMAP diretto**. Solo Gmail (le PEC arrivano già inoltrate).

Trigger A: email verbale ricevuta → scanner Gmail crea/aggiorna `verbali_noleggio`.
Trigger B: fattura XML ARVAL/Leasys → il parser estrae numeri verbale e crea scheda parziale (stato `notifica_attesa`).

## File creati
- `app/services/verbali_gmail_scanner.py` — scan Gmail + parse email + save allegati + parse PDF avviso digitale.
- `app/services/verbali_fattura_linker.py` — `cerca_fattura_per_verbale`, `collega_verbali_a_fatture`.
- `app/services/verbali_fattura_trigger.py` — `processa_fattura_per_verbali` (trigger B).
- `app/routers/alert_verbali.py` — endpoint `GET /api/alert-verbali/scadenza-imminente`, `/contatore`.
- `scripts/popola_verbali_retroattivo.py` — ripopolamento storico.
- `scripts/popola_paypal_account_id.py` — mapping retroattivo fornitori ↔ PayPal account.

## File modificati
- `app/routers/fatture_module/import_xml.py` — hook `processa_fattura_per_verbali` post-insert.
- `app/router_registry.py` — registra `alert_verbali` router.
- `app/scheduler.py` — job `scan_gmail_verbali` ogni 30 min, `link_verbali_fatture` ogni 60 min.
- `app/routers/verbali_noleggio_api.py` — aggiunti `POST /scan-gmail`, `POST /riconcilia-completo`.

## Dipendenze
- `pdfplumber`, `reportlab` (installate da fasi 2/3).

## Test di accettazione (verbale `B25123609980`)
1. `POST /api/paypal-api/sync` 2025-01-01 → 2026-04-30.
2. `POST /api/verbali-noleggio/scan-gmail?days_back=120`.
3. `POST /api/verbali-noleggio/riconcilia-completo`.
4. `GET /api/alert-verbali/contatore`.

Atteso: `verbali_noleggio.findOne({numero_verbale:"B25123609980"}).stato == "pagato"` con `psp`, `metodo_pagamento`, `pdf_ricevuta_path` popolati.

## UI
- `DettaglioVerbale.jsx` → banner scadenza 5gg, sezione "Date Chiave", sezione "Fattura ARVAL associata".
- Dashboard principale → widget `GET /api/alert-verbali/contatore`, badge rosso se >0.
