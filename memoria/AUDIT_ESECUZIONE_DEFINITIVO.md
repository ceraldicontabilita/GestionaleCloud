# AUDIT ESECUZIONE DEFINITIVO — PROMPT_DEFINITIVO (luglio 2026)

> Deliverable §16 del PROMPT_DEFINITIVO. Fotografia finale dell'esecuzione:
> baseline, cosa è stato fatto, come è stato verificato, cosa resta.
> Aggiornato al 2026-07-13.

## 1. Baseline

- Commit baseline: `b9ff5c767cbef33c457b8cff091987b86a90c56f`
- Alla baseline: 1105 endpoint montati, 137 file router, 257 test verdi,
  build frontend Vite verde.

## 2. Stato finale

- **Commit dalla baseline**: 40+ (branch `claude/repo-restructure-review-z0gg7w`,
  allineato su `main` a ogni blocco).
- **File toccati**: 261 (+8785 / −1723 righe).
- **Endpoint montati**: 1106 (era 1105: rimosse route legacy doppie,
  aggiunte route canoniche; vedi §7 sotto).
- **Test**: **335 passed, 2 skipped** (baseline: 257 verdi — nessuna regressione,
  +78 test nuovi di regressione/guardia).
- **Build frontend**: verde (`npm run build`, Vite).
- **Mappe rigenerate** (2026-07-13): `scripts/genera_mappa.py` → 1106 endpoint,
  107 prefissi, copertura FE 639 chiamati + 76 esterni + 391 non chiamati dal FE;
  `scripts/genera_classificazione_endpoint.py` → memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md.

## 3. Bug corretti (FASE P0 — 12/12)

Dettaglio completo con test di regressione in `memoria/BUG_CORRETTI_2026-07.md`.
In sintesi: widget F24 doppio conteggio, auto-riconciliazione con filtro importi
sbagliato, verbali su campo fattura inesistente, stato assegno non valido,
salari senza esclusioni, e gli altri P0 censiti dall'audit — ognuno chiuso con
funzione dedicata + test (`tests/test_p0_*.py`).

## 4. Collection: canoniche e migrazioni

Fonti canoniche effettive (criterio §17.2):

| Dominio | Collection canonica | Migrazione (da eseguire al deploy se non già fatta) |
|---|---|---|
| Fatture ricevute | `invoices` | `python -m app.scripts.migra_fatture_passive_a_invoices --esegui` |
| Fatture emesse | `fatture_emesse` (scelta utente) | `python -m app.scripts.migra_invoices_emesse_a_fatture --esegui` |
| F24 | `f24_unificato` | `migra_f24_commercialista_a_unificato`, `migra_f24_unificato` |
| Dipendenti | `dipendenti` | `migra_employees_a_dipendenti`, `migra_staff_a_dipendenti` |
| Cedolini | `cedolini` | `migra_payslips_a_cedolini` |
| Contratti | `contratti` | `migra_employee_contracts_a_contratti` |
| Documenti | `documenti_classificati` (scelta utente) | `migra_documents_classified` |
| Fornitori | `suppliers` (+ metodo pagamento canonico) | `migra_metodo_pagamento_fornitori` |
| Estratto conto | `estratto_conto_movimenti` | — (già canonica) |
| Prima Nota | `prima_nota_cassa` / `prima_nota_banca` | — (già canoniche) |
| Mittenti | unificata su mittenti email | `migra_mittenti_attendibili_a_email` |

Tutte le migrazioni sono **non distruttive** (copiano/marcano, non cancellano
la sorgente) e idempotenti; i flussi vivi scrivono solo nelle canoniche.
Piano completo: `memoria/PIANO_MIGRAZIONE_COLLECTION.md`.

## 5. Motori unificati (una sola architettura contabile)

- **Saldo Prima Nota**: motore unico
  `app/routers/prima_nota_module/common.aggrega_saldo_prima_nota` usato da
  cassa, banca, stats (`get_saldo_finale`) e manutenzione
  (`recalculate_all_balances`) — §6.4 chiuso, esclusioni uniformi
  (deleted/archived + CATEGORIE_ESCLUSE), riporto anni precedenti identico ovunque.
- **Piano dei conti**: SOLO quello UFFICIALE CEE del bilancio del commercialista
  (231 conti, `app/services/piano_conti_ufficiale.py`); ogni altro schema
  (operativo puntato, numerico) è convertito con
  `app/services/mapping_piano_conti.OPERATIVO_A_UFFICIALE`. Bilancio espone
  `voci_ufficiali` (SP + CE). Regola vincolante in CLAUDE.md e
  `memoria/PIANO_CONTI_UFFICIALE_CERALDI.md`.
- **F24/paghe/fisco**: motori `app/engines/tributi_engine.py` e
  `fiscale_engine.py` secondo `memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md`
  (saldo F24 mai auto-deducibile, RC01 = periodo precedente, quietanza orfana
  = alert bloccante, mai ricostruzione automatica del modello).
- **Analisi motori concorrenti**: `memoria/ANALISI_MOTORI_CONTABILI.md`.

## 6. Sicurezza (FASE P2)

- **Modello di autenticazione**: middleware globale
  `app/middleware/authentication.py` (montato in `app/main.py`): ogni `/api/*`
  richiede JWT (Bearer o cookie `access_token` con rinnovo scorrevole) salvo
  allowlist esplicita e minimale (health, login/setup, webhook WhatsApp con
  verify_token Meta, ponte ERP con secret, pagine legali, docs, SEO).
  L'allowlist è **congelata da test** con set-equality
  (`tests/test_sicurezza_auth.py::TestAllowlistCongelata`): ogni nuovo path
  pubblico fa fallire la suite. Ruoli admin/operatore/sola-lettura applicati
  nel middleware stesso.
- **13 endpoint distruttivi** (reset/cleanup/reimport/backfill/migra) marcati
  Admin-only con `Depends(get_current_admin_user)` + test sulla route table
  reale (`tests/test_p2_admin_guards.py`).
- **§12.7 download/viewer**: tutti gli endpoint PDF usati dai viewer sono sotto
  `/api/*` e fuori allowlist → protetti dal middleware; gli iframe funzionano
  via cookie di sessione (stessa origine). Verbale PayPal usa blob-fetch
  autenticato.
- Niente segreti nei log; fail-fast produzione opt-in (`SECRET_KEY_REQUIRED=true`);
  rate-limit login; CORS ristretto via env.

## 7. Endpoint: eliminati e mantenuti

- **Classificazione completa**: `memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md`
  (rigenerata 2026-07-13): 1106 endpoint → 650 tenere, 437 verificare
  (per lo più interni/legacy senza chiamante FE, nessuno eliminato senza
  verifica dei chiamanti non-frontend), 19 admin-only.
- **Eliminati** (con verifica chiamanti = zero): route legacy doppie di
  `public_api.py` per invoices/suppliers GET (vincevano per ordine di
  registrazione su quelle canoniche), `/fornitori/metodi-pagamento` e
  `/fornitori/import-metodi-da-fatture` (zero chiamanti + default vietato),
  modulo morto `referential_integrity.py`, dominio HACCP completo.
- **Mantenuti con motivo**: endpoint "verificare" restano montati perché il
  criterio §17.5 vieta eliminazioni senza controllo dei chiamanti esterni
  (app esterna sullo stesso DB, integrazioni). Elenco e motivazioni nel file
  di classificazione.

## 8. Frontend

- **Primitive**: 79 `alert()` → toast sonner; 16 `confirm()` → `useConfirm()`
  (ConfirmDialog); `window.prompt` PIN → dialog in-app (Utenti.jsx);
  `window.open` documentali → `DocumentViewerModal` (F24, documenti non
  associati, ricevuta PagoPA, verbale PayPal blob); 7 `window.open` legittimi
  mantenuti (export/stampa/navigazione). Checklist:
  `memoria/AUDIT_PRIMITIVE_FRONTEND.md`.
- **Viewer canonico**: `DocumentViewerModal` (censimento completo:
  `memoria/AUDIT_VIEWER_DOCUMENTI.md`).
- **Matrice funzionale** Route→Pagina→API→Router→Collection→Test:
  `memoria/MATRICE_FUNZIONALE_FINALE.md`.

## 9. Verifica criteri di accettazione (§17)

| # | Criterio | Esito |
|---|---|---|
| 1 | 12 bug di correttezza chiusi | ✅ 12/12 con test (`memoria/BUG_CORRETTI_2026-07.md`) |
| 2 | Collection canoniche effettive | ✅ vedi §4 (migrazioni idempotenti al deploy) |
| 3 | Nessun flusso vivo scrive in legacy | ✅ scritture convogliate sulle canoniche |
| 4 | Endpoint classificati | ✅ 1106/1106 in ENDPOINT_CLASSIFICAZIONE_FINALE.md |
| 5 | Nessuna eliminazione senza controllo chiamanti | ✅ eliminati solo con zero chiamanti verificati |
| 6 | Niente motori contabili concorrenti | ✅ piano conti CEE unico + mapping; motori tributi/fiscale unici |
| 7 | Saldi Prima Nota su un solo engine | ✅ aggrega_saldo_prima_nota ovunque (§6.4) |
| 8 | Viewer su tutti i viewport | ✅ DocumentViewerModal responsive full-screen (AUDIT_VIEWER_DOCUMENTI.md) |
| 9 | Fatture/cedolini/F24/quietanze visibili integralmente | ✅ viewer canonico con fit-schermo |
| 10 | IVA mai detratta due volte | ✅ liquidazioni persistite con stati/versioni + test scenario |
| 11 | DM10/RC01 mai sommati due volte | ✅ tributi_engine + test regressione |
| 12 | Quietanza senza F24 → alert | ✅ stato QUIETANZA_PRESENTE_F24_MANCANTE bloccante + test |
| 13 | Distruttive Admin-only e tracciate | ✅ 13 endpoint con guardia + audit log + test route table |
| 14 | Job sopravvivono a restart | ✅ job state persistito (P0.10) |
| 15 | Build frontend verde | ✅ 2026-07-13 |
| 16 | Backend avviabile | ✅ boot verificato dalle mappe (route table runtime) |
| 17 | Test ≥ baseline 257 | ✅ 335 passed, 2 skipped |
| 18 | Mappe rigenerate e coerenti | ✅ genera_mappa + classificazione (2026-07-13) |
| 19 | Tutto committato su main | ✅ push finale branch + main a chiusura |

## 10. Rischi residui e decisioni richieste all'utente

1. **`/api/v1` (API key esterne)**: oggi richiede ANCHE il JWT (non è in
   allowlist) → canale di fatto spento verso l'esterno. Non aperto di
   iniziativa: `/api/v1/keys/generate` non ha altra auth propria, whitelistarlo
   permetterebbe a chiunque di generare chiavi. **Decidere**: (a) lasciare
   spento; (b) whitelistare `/api/v1/` DOPO aver protetto keys/generate
   (admin-only); (c) rimuovere il canale.
2. **§6.7 PayPal**: 2 router + 6 service da consolidare — rinviato a sessione
   dedicata (area intrecciata, rischio regressione).
3. **22 `to_list(100000)`/N+1** censiti in `memoria/AUDIT_PERFORMANCE_N1.md`:
   da valutare uno a uno (molte sono aggregazioni finanziarie non troncabili).
4. **Armonizzazione campi fatture emesse** (numero/data doppioni EN/IT):
   documentata, non forzata per non rompere l'app esterna sullo stesso DB.
5. **Migrazioni al deploy**: gli script `python -m app.scripts.migra_* --esegui`
   vanno lanciati in produzione (sono idempotenti e non distruttivi).
6. **Refactor endpoint verbali** FE-wired: rinviato (usato dal frontend).

## 11. Indice deliverable (§16)

| File | Contenuto |
|---|---|
| `memoria/AUDIT_ESECUZIONE_DEFINITIVO.md` | questo file |
| `memoria/MATRICE_FUNZIONALE_FINALE.md` | matrice Route→…→Test per i 13 moduli |
| `memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md` | classificazione 1106 endpoint |
| `memoria/AUDIT_VIEWER_DOCUMENTI.md` | censimento viewer documentale |
| `memoria/PIANO_MIGRAZIONE_COLLECTION.md` | piano collection canoniche |
| `memoria/BUG_CORRETTI_2026-07.md` | 12 bug P0 con test |
| `memoria/REPORT_SESSIONE_RISTRUTTURAZIONE.md` | report complessivo per l'utente |
| `memoria/PIANO_CONTI_UFFICIALE_CERALDI.md` | piano conti CEE ufficiale |
| `memoria/AUDIT_PRIMITIVE_FRONTEND.md` | alert/confirm/prompt/window.open |
| `memoria/AUDIT_PERFORMANCE_N1.md` | to_list/N+1 residui |
| `memoria/ANALISI_MOTORI_CONTABILI.md` | analisi motori concorrenti |
