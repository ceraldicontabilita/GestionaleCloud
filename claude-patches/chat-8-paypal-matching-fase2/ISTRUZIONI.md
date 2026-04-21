# Chat 8 — FASE 2: Matching fatture ↔ PayPal + PDF ricevute

## Obiettivo
- Match esatto invoices ↔ paypal_transactions tramite `paypal_account_id` (con fallback per importo+nome).
- Download PDF ricevute PagoPA da Gmail → `/app/uploads/paypal_ricevute/`.
- Generazione PDF sintetico per transazioni PayPal commerciali.
- Endpoint unificato `/api/paypal-api/riconcilia`.
- Allineamento paypal_transactions ↔ estratto_conto_movimenti (flag `riconciliato_con_estratto_banca`).

## File creati
- `app/services/paypal_pdf_fetcher.py` — fetch ricevuta PagoPA da Gmail + generatore PDF sintetico.

## File modificati
- `app/services/paypal_riconciliazione.py` — aggiunte `match_fornitore_by_paypal_id`, `riconcilia_multe_pagopa`, `collega_a_estratto_conto`; inserita strategia primaria `paypal_account_id` in `riconcilia_pagamenti_paypal`.
- `app/routers/paypal_api.py` — aggiunti endpoint `POST /riconcilia`, `GET /ricevuta-pdf/{transaction_id}`.

## Dipendenze
- `reportlab` (nuova).

## Endpoint
- `POST /api/paypal-api/riconcilia` body `{start_date, end_date}` → riconciliazione unificata multe+fatture+banca.
- `GET /api/paypal-api/ricevuta-pdf/{transaction_id}` → scarica/genera PDF ricevuta.

## Test di accettazione
1. Sync: `POST /api/paypal-api/sync` body `{"start_date":"2025-09-01","end_date":"2025-09-30"}`.
2. Popolamento: `python -m scripts.popola_paypal_account_id`.
3. Riconciliazione: `POST /api/paypal-api/riconcilia` → verificare output `{multe_pagopa, fatture, banca}`.
4. Scarica ricevuta: `GET /api/paypal-api/ricevuta-pdf/<tx_id>`.
