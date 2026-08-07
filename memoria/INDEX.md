# Ceraldi ERP — Scheda rapida

DB MongoDB: `Gestionale` · P.IVA 04523831214 · riscritta 07/08/2026
(le regole vincolanti stanno in `CLAUDE.md`; qui i fatti tecnici).

## Stack

| Layer    | Tecnologia |
|----------|------------|
| Frontend | React 18 + Vite (inline styles da `src/lib/utils.js`, no Tailwind) |
| Backend  | FastAPI + Motor (async) |
| DB       | MongoDB Atlas (`Gestionale`) |
| Deploy   | Render, servizio `GestionaleCloud`, autoDeploy da `main` |
| Schedule | APScheduler (Drive/email ogni ora) |

## Documenti di riferimento (tutti vivi, il resto è in git)

| File | Cosa contiene |
|---|---|
| `CLAUDE.md` | Regole vincolanti in vigore |
| `LOGICA_FUNZIONAMENTO.md` (root) | Comportamento del sistema per gli utenti |
| `PIANO_CONTI_UFFICIALE_CERALDI.md` | Piano dei conti CEE del commercialista |
| `SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md` | Fonte di verità paghe/fisco |
| `SPECIFICA_IVA.md` | Attribuzione per competenza e liquidazioni |
| `FORNITORI_REGOLA_CANONICA.md` | Anagrafica fornitori |
| `LOGICA_LIBRO_MASTRO.md` | Libro giornale/mastro |
| `LOGICA_OPERATIVA.md` | Dettaglio funzionale operativo |
| `DRIVE_ESTRATTI_CONTO.md` | Cartella unica estratti conto |
| `DISASTER_RECOVERY_MONGODB.md` | Ripristino DB |
| `BACKLOG.md` | Lavoro pendente reale |
| `MAPPA_MODULI.md` / `MAPPA_COLLEZIONI.md` | Mappa narrativa moduli e collezioni |

**Generati dagli script, verificati dalla CI — mai a mano:**
`MAPPA_ROUTER.md`, `MAPPA_ENDPOINT_COMPLETA.md` (→ `scripts/genera_mappa.py`),
`ENDPOINT_CLASSIFICAZIONE_FINALE.md` (→ `genera_classificazione_endpoint.py`),
`AUDIT_FRONTEND_DEAD_CODE.md` (→ `audit_frontend_dead_code.py`),
`AUDIT_STATIC_REPORT.md` (→ `audit_static.py`).

## Collezioni canoniche

```
invoices (~3856)                  → Fatture SDI TD01+TD04      [UNICA fatture passive]
fornitori (~268)                  → Anagrafica fornitori       [NON suppliers]
dipendenti (~30)                  → HR anagrafica              [NON employees]
cedolini (~916)                   → Buste paga Zucchetti v2
corrispettivi (~1051)             → UNICA fonte ricavi
prima_nota_cassa / prima_nota_banca
estratto_conto_movimenti (~4261)  → Movimenti bancari          [UNICA]
f24_unificato (~83)               → Modelli F24                [NON f24_models]
assegni (~210)                    → Assegni per carnet
scadenziario_fornitori (~903)     → Scadenze fornitori
chiusure_pos_manuali              → POS reale per giorno/gestore
sumup_transactions / sumup_payouts→ Circuito SumUp da API
warehouse_inventory (~5372)       → Giacenze                   [NON warehouse_stocks]
documents_inbox / documenti_classificati / documenti_non_associati
partite_aperte · riconciliazioni_match · audit_log · alerts
verbali_noleggio (~165) · veicoli_noleggio (~4)
```

## Route principali

```
/                dashboard          /prima-nota      cassa+banca+provvisori
/fatture         fatture ricevute   /riconciliazione riconciliazione unificata
/fornitori       fornitori          /contabilita     piano conti · bilancio · IVA
/noleggio        flotta+verbali     /magazzino       giacenze
/documenti       archivio+import    /admin           email · SumUp · sistema
```

## Servizi core (app/services/)

```
scritture_contabili.py   → MOTORE UNICO Prima Nota (mai insert diretti)
conti_pos.py             → circuiti POS → conti (Numia/SumUp/PayPal)
sumup_sync.py / sumup_payout.py → circuito SumUp
stato_coerenza_pos.py    → catene di controllo POS indipendenti
classificazione_estratti.py → fonte dei documenti in cartella unica
dedup_causali_ec.py      → doppioni EC da causali prefissate
event_bus.py · alert_engine.py · audit_logger.py · deduplica.py
partite_aperte_engine.py · riconciliazione_engine.py
```

## Regole tecniche (da non dimenticare)

1. Nomi collezioni SEMPRE da `app/db_collections.py`, mai stringhe.
2. Ricavi SOLO da `corrispettivi`; le `invoices` sono costi.
3. Note credito TD04 → importo negativo.
4. Metodo pagamento fattura: dal FORNITORE (anagrafica), mai dall'XML SDI;
   il metodo REALE del pagamento è `_metodo_reale()` (fatture_module/crud).
5. IMAP sempre dentro `asyncio.to_thread()`.
6. Settings: il file `.env` ha priorità sull'ambiente OS (intenzionale —
   ricordarlo quando "le variabili su Render non arrivano").
7. Ogni CRUD significativo chiama `propagate_event()`.
8. Alert solo dal catalogo di `alert_engine.py`.
9. Design: `src/lib/utils.js` unica fonte (navy #0f2744, oro #b8860b).
10. HACCP rimosso (app esterna Tracciabilità); HR nell'app AppDipendenti.

## Mittenti email autorizzati

| Mittente | Tipo | Destinazione |
|---|---|---|
| `grazia.studioferrantini@email.it` | Cedolino/F24 | `cedolini` |
| `rosaria.marotta@email.it` | F24 | `cedolini` |
| `f.ferrantini@email.it` | Cedolino/F24 | `cedolini` |
| `ricevuta.pagaonline@agenziariscossione.gov.it` | Cartella | `documenti_non_associati` |
| `notifica.acc.campania@pec.agenziariscossione.gov.it` | Cartella | `documenti_non_associati` |
| `no_reply@agenziariscossione.gov.it` | Cartella | `documenti_non_associati` |
| `inpscomunica@postacert.inps.gov.it` | INPS | `documenti_non_associati` |
| `auto_napoli@massivo.pec.inail.it` | INAIL | `documenti_non_associati` |
| `partenopay@ext.comune.napoli.it` | PagoPA | `verbali` |
| `noreply-checkout@ricevute.pagopa.it` | PagoPA | `documenti_non_associati` |
| `tari.avvisibonari@pec.comune.napoli.it` | TARI | `documenti_non_associati` |
| `entrate.tari-tares-tarsu@pec.comune.napoli.it` | TARI | `documenti_non_associati` |
| `assistenza@paypal.it` | PayPal | `documenti_non_associati` |
| `@pec.fatturapa.it` (PEC) | Fattura XML SDI | `invoices` |

Fatture SOLO da Drive/PEC, mai da Gmail. Corrispettivi: solo XML del
registratore telematico.
