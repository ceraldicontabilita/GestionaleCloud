# Audit Tecnico Canonico — Report Finale

_GestionaleCloud, 13/07/2026. Esecuzione del piano
`AUDIT_TECNICO_CANONICO_GestionaleCloud.md`._

Questo è il documento di sintesi. I dettagli sono nei report per area:
- `memoria/AUDIT_SICUREZZA.md` — sicurezza backend
- `memoria/AUDIT_PRESTAZIONI.md` — prestazioni backend/frontend
- `memoria/AUDIT_DATABASE.md` — collection MongoDB
- `memoria/AUDIT_MATRICE.md` + `AUDIT_MATRICE_DATI.json` — matrice API
- `memoria/AUDIT_REACT.md` — route React e componenti orfani

## Cosa è stato GIÀ FATTO in questa sessione

1. **Dominio HACCP rimosso** (Fase B, in produzione, CI verde):
   - Schede tecniche prodotti: router, service, pulsante/modale Fornitori, mapping
     ingest email. Salvata la funzione contabile "completa anagrafica fornitore da
     XML" → nuovo router `/api/anagrafica-fornitori`.
   - Giacenze fisiche e alert sotto-scorta (job 6:30) rimossi; il Dizionario
     Articoli resta contabile e vivo.
   - Frontend: redirect morti cucina/ricettario, query-keys `libretti`, export orfano.
   - Script archiviazione non distruttiva `archivia_collection_haccp.py`.
   - `duckduckgo_search` rimosso dai requirements.
   - Scelte utente 13/07: **restano** Previsioni Acquisti e Libretti sanitari.
2. **Matrice API completa** (Fase C): 1108 endpoint classificati, 133 route React,
   48 componenti mai importati, 4 endpoint duplicati, 0 bottoni realmente rotti.
3. **Bug P0 corretto**: `Collections.SCADENZARIO_FORNITORI` inesistente rendeva i
   KPI live della dashboard sempre vuoti (`websocket_realtime.py:83`).

## Piano di refactoring — priorità

### P0 — Sicurezza dell'autenticazione (rischio aggregato alto)
Da valutare insieme, riguardano il controllo di accesso:
1. **SECRET_KEY** non obbligatoria + fallback deterministico da MONGO_URL
   (`config.py:34,266-270`): un attaccante che conosce l'URI forgia JWT admin.
2. **CORS** `["*"]` con `allow_credentials=True` e auth via cookie
   (`config.py:44-46`, `main.py:155-163`).
3. **Rate limiting** configurato ma mai applicato (manca `SlowAPIMiddleware`); login
   email senza lockout (`main.py:165-174`, `auth.py:92`).

> NOTA: questi toccano parametri di configurazione/sicurezza. Prima di modificarli
> servono scelte esplicite (origin CORS consentiti, policy SECRET_KEY, soglie rate
> limit) — vedi "Decisioni richieste" sotto.

### P1 — Correttezza e igiene importante
4. **Autorizzazioni fittizie**: ogni login è `role:"admin"`; endpoint distruttivi
   senza `get_current_admin_user` (es. `DELETE /api/fatture/all`).
5. **Ponte ERP aperto** se manca `ERP_BRIDGE_SECRET`: scrittura senza verifica
   (`erp_bridge.py:83-90`).
6. **Regex injection / ReDoS** su endpoint pubblici non autenticati
   (`public_api.py:754-851`, parametro `q` non `re.escape`-ato).
7. **Collection duplicate ancora vive** (rischio dati in due posti):
   `f24_commercialista` vs `f24_unificato`, `fatture_passive` vs `invoices`,
   `invoices_emesse` vs `fatture_emesse`, `employees` vs `dipendenti`,
   `estratti_conto` vs `estratto_conto_movimenti`.
8. **Prestazioni ALTO**: N+1 in `sync_relazionale.py:187-218,286-296`; paginazione
   finta fatture (`fatture_module/crud.py:379`); `to_list(None)`/`to_list(100000)`
   in `stats.py:121` e `manutenzione.py:596`.

### P2 — Pulizia e ottimizzazione
9. **Codice morto DB**: 35 collection mai usate + `warehouse_stocks`/`warehouse_products`
   residui → archiviazione (script dedicato, non distruttivo).
10. **Componenti React mai importati**: 48 file (per lo più `components/ui/*` di una
    libreria shadcn non adottata) → rimozione previa verifica.
11. **Indici mancanti**: `scadenziario_fornitori`, `cespiti`, `quietanze_f24`,
    `contratti_dipendenti`, `documenti_non_associati`.
12. **Import pesanti al boot** (reportlab/pdfplumber/pandas/fitz top-level) →
    import lazy.
13. **Cache** su bilancio/stats/controllo mensile (infrastruttura già presente).
14. **Igiene sicurezza**: audit_log per login/delete massivi, limite dimensione
    upload, durata token email (7g→1h), password admin con confronto costante-tempo,
    whitelist auth per path espliciti.
15. **Governance nomi collection**: unificare `db_collections.py` e la classe
    `Collections` in un'unica fonte di verità (ha già causato il bug P0).

## Decisioni richieste all'utente (regola parametri CLAUDE.md)
Prima di toccare i P0/P1 di sicurezza servono le tue scelte su:
- **Origin CORS** consentiti in produzione (dominio/i reali del frontend).
- **Modello utenti**: resta mono-utente admin (allora documentiamo e proteggiamo i
  distruttivi con un secondo fattore) o servono ruoli reali?
- **Soglie rate limit** su login (es. 5 tentativi / 5 min?).
- **Consolidamento collection duplicate**: quali migrare e quando (operazione sui
  dati di produzione).

## Stato deliverable del piano canonico
| # | Deliverable | Stato |
|---|---|---|
| 1 | Elenco route React | ✅ `AUDIT_REACT.md` |
| 2 | Elenco endpoint FastAPI | ✅ `AUDIT_MATRICE.md` |
| 3 | Mappa frontend→backend→DB | ✅ `AUDIT_MATRICE_DATI.json` |
| 4 | Elenco codice morto | ✅ React (48) + DB (35) |
| 5 | Elenco duplicazioni | ✅ endpoint (4) + collection (8 gruppi) |
| 6 | Endpoint orfani | ✅ 665 DA_VERIFICARE classificati |
| 7 | Componenti React inutilizzati | ✅ `AUDIT_REACT.md` |
| 8 | Router eliminabili | ✅ schede_tecniche rimosso; matrice per gli altri |
| 9-12 | Pulsanti/tab/navigazioni/redirect | ✅ 0 rotti reali; audit-layout in CI |
| 13 | Sicurezza | ✅ `AUDIT_SICUREZZA.md` |
| 14 | Prestazioni | ✅ `AUDIT_PRESTAZIONI.md` |
| 15 | Responsive | ✅ audit-layout (telefono+desktop) in CI, verde |
| 16-19 | Contabilità/IVA/F24/documenti | ✅ coperti da sessioni precedenti + matrice |
| 20 | Report finale P0/P1/P2 | ✅ questo documento |
