# Chat 8 — FASE 3: Ricerca pagamento verbale multi-fonte

## Obiettivo
Dalla scheda verbale: bottone "🔍 Cerca pagamento" che cerca in cascata:
1. `paypal_transactions` (IUV / numero_verbale / targa+importo)
2. Gmail ricevute PagoPA (noreply-checkout@ricevute.pagopa.it, noreply_paytech@mooney.it, partenopay@ext.comune.napoli.it)
3. `estratto_conto_movimenti` SDD PayPal entro 120gg

Se trovato → aggiorna verbale (stato=pagato, importo, data, PSP, PDF allegato).

## File creati
- `app/services/verbali_iuv_extractor.py` — estrazione IUV da filename/PDF allegati.
- `app/services/verbali_pagamento_finder.py` — ricerca multi-fonte + `applica_pagamento_a_verbale`.

## File modificati
- `app/routers/verbali_noleggio_api.py` — aggiunti:
  - `POST /{verbale_id}/cerca-pagamento`
  - `GET /{verbale_id}/ricevuta-pdf`

## Dipendenze
- `pdfplumber` (nuova).

## Test di accettazione
1. `POST /api/verbali-noleggio/{id}/cerca-pagamento` su un verbale reale (es. `B25123609980`).
2. Verificare stato `pagato`, `fonte_riconciliazione`, `pdf_ricevuta_path`.
3. `GET /api/verbali-noleggio/{id}/ricevuta-pdf` → PDF.

## UI
- `DettaglioVerbale.jsx` → card "Stato Pagamento" con 3 stati (verde/giallo/rosso) e pulsante di ricerca.
