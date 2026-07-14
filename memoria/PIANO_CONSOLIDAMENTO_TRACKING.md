# PIANO RESIDUO — Indice di avanzamento

> Documento vivo. Sostituisce la prima versione (14/07/2026, basata sul
> report esterno) con il `PIANO_RESIDUO_AGGIORNATO_GESTIONALECLOUD.md`
> fornito dall'utente lo stesso giorno — più preciso perché pinnato a un
> commit e perché distingue nettamente il già-fatto dal residuo reale.
> Va aggiornato ad ogni operazione: l'utente deve poter leggere "operazione
> N di 19" e sapere cosa resta.

**Commit di riferimento del piano:** `16dcc570` (poi `0eb3f73` con la prima
versione di questo tracking — nessuna attività di codice tra i due).

## Regola di aggiornamento (vincolante, dal documento dell'utente)

Quando un'attività è completata:
1. rimuoverla da "Attività residue";
2. aggiungerla a "Completate dopo il 14/07/2026" con commit, file
   modificati, test, risultato;
3. rigenerare le mappe (`scripts/genera_mappa.py`,
   `scripts/genera_classificazione_endpoint.py`);
4. nessuna duplicazione tra fatto e da fare.

Le voci in **NON RIPETERE** non vanno mai riproposte come domande né
rilavorate da zero.

## Stato di avanzamento

**Operazioni residue aperte: 19 di 19.** Prossima operazione: **#1**
(rigenerare tutti gli inventari sullo stesso commit + test di coerenza).

---

## NON RIPETERE — già completate, non richiedere di nuovo

- fornitori canonici su `fornitori`, non `suppliers`;
- dipendenti canonici su `dipendenti`, non `employees`;
- cedolini canonici su `cedolini`;
- F24 canonici su `f24_unificato`;
- estratto conto canonico su `estratto_conto_movimenti`;
- fatture passive canoniche su `invoices`;
- rimozione del dominio HACCP operativo;
- rimozione contratti di lavoro e libretti sanitari dal dominio dipendenti;
- riduzione del router dipendenti;
- motore IVA (regola del 15 e anti-doppia-detrazione);
- motore F24/tributi e fiscale;
- quietanza senza F24 con alert bloccante;
- gestione DM10/RC01 e possibile doppio pagamento;
- viewer documentale canonico (`DocumentViewerModal`);
- sostituzione della maggior parte di `alert`/`confirm`/`prompt`/`window.open`;
- middleware globale di autenticazione;
- protezione endpoint distruttivi;
- saldo Prima Nota tramite motore unico;
- Piano dei Conti ufficiale con mapping;
- i 12 bug P0 (coperti da test);
- rimozione Emergent e codice morto già censito;
- pipeline Fatture Estere (AI + coda di verifica + rating);
- audit atomico e mappe aggiornate al 14/07/2026.

Su queste voci: solo verifica di assenza regressioni, mai ricostruzione.

---

## Attività residue (19 operazioni)

### P0 — allineamento e verità unica dei report

**1. ⛔ Rigenerare tutti gli inventari sullo stesso commit + test anti-mismatch**
```
python scripts/genera_mappa.py
python scripts/genera_classificazione_endpoint.py
```
Rigenerare insieme `MAPPA_ROUTER.md`, `MAPPA_ENDPOINT_COMPLETA.md`,
`MAPPA_COLLEZIONI.md`, `ENDPOINT_CLASSIFICAZIONE_FINALE.md`,
`AUDIT_ATOMICO_APPLICAZIONE.md`. Aggiungere un test che fallisca se i
totali non coincidono. Sicura, non tocca produzione — può partire subito.

### P1 — eliminazione endpoint realmente inutili

Route table corrente: ~1059 endpoint. Ogni gruppo è ❓ decisione utente
prima di smontare (impatto produzione):

**2. ❓ `/api/batch/*`** (6 endpoint, nessun chiamante noto)
**3. ❓ `/api/cedolini/*`** (drive/status, drive/quadratura, {id}/pdf — `drive/sync` resta, usato da scheduler)
**4. ❓ `/api/dati-provvisori/*`** (upload-xml, sposta-banca, sposta-cassa, delete — `riconcilia-estratto-conto` resta, scheduler)
**5. ❓ `/api/exports/*`** (8 endpoint incl. `suppliers`)
**6. ❓ `/api/paghe/*`** (import-distinte-bpm, import-f24, import-libro-unico — verificare uso interno da `documenti.py` prima di decidere)
**7. ❓ `/api/pos-accredito/*`** (5 endpoint, candidato forte: sostituito da `pos_corrispettivi_check`)
**8. ❓ `/api/realtime/*`** (status — verificare se il websocket è realmente usato)
**9. ❓ `/api/report-pdf/*`** (magazzino incoerente con rimozione HACCP)
**10. ❓ `/api/trattenute-verbali/*`** e gruppo verbali_noleggio/verbali_riconciliazione

Non eliminare mai: scheduler Drive cedolini, parser F24/Libro Unico usati
internamente, webhook, Chat, API esterne documentate, endpoint manutentivi
ancora necessari.

### P1 — altre attività

**11. ⛔ Audit reale frontend inutilizzato** — creare
`scripts/audit_frontend_dead_code.py` + `memoria/AUDIT_FRONTEND_DEAD_CODE.md`
(entry point `main.jsx`/`App.jsx`/`navigation.config.js`, classificazioni
ENTRYPOINT/ROUTE_ATTIVA/COMPONENTE_USATO/MODALE_USATO/HOOK_USATO/TEST_ONLY/
DINAMICO_DA_VERIFICARE/ORFANO_ELIMINABILE). Eliminare solo gli
`ORFANO_ELIMINABILE`, con `yarn build && yarn lint` dopo ogni gruppo.

**12. ⛔ Completare l'adozione di `app/db_collections.py`** — trovare le
stringhe collection ancora hardcoded, sostituirle con le costanti,
trasformare `database.py::Collections` in alias o eliminarla, aggiungere
un test statico anti-hardcode. Non riaprire le decisioni fornitori/
dipendenti/cedolini/invoices/f24_unificato (già chiuse).

**13. ⛔ Verificare le migrazioni realmente eseguite in produzione** — per
ognuna delle collection canoniche (`fornitori`, `dipendenti`, `cedolini`,
`invoices`, `f24_unificato`, `estratto_conto_movimenti`,
`documenti_classificati`) controllare nel DB di produzione: sorgente,
destinazione, documenti copiati, duplicati, errori, scritture legacy dopo
la migrazione. Produrre `memoria/VERIFICA_MIGRAZIONI_PRODUZIONE.md`.
Nota: richiede accesso al DB di produzione — non eseguire nuove
migrazioni scrivendo dati, solo verificare lo stato.

**14. ❓ PayPal** — unificare 2 router, service paralleli, mapping
fornitore, import statement/API, stati, riconciliazione, idempotenza.

**15. ❓ Verbali** — architettura unica (ingest/CRUD/riconciliazione/
trattenute) con schema e collection canonici.

**16. ⛔ Fatture emesse** — armonizzare campi italiano/inglese duplicati
con DTO canonico + adapter di migrazione, senza rompere l'app esterna.

**17. 🟡 Prestazioni — query N+1/`to_list` ancora aperte** —
`memoria/AUDIT_PERFORMANCE_N1.md` le censisce già (23 query, 1 corretta).
Per ognuna: misurare, classificare interattivo/report, sostituire con
aggregation/cursor/`$in`/`bulk_write` dove è un'API interattiva,
paginazione reale, soglie di durata. Priorità: sincronizzazione
relazionale, fatture, estratto conto, Prima Nota, documenti, scheduler.

**18. 🟡 Viewer — certificazione dinamica finale** — `DocumentViewerModal`
esiste già (non ricostruire). Manca la certificazione automatizzata sugli
8 tipi documento (fattura ASSO HTML, fattura PDF, cedolino, F24, quietanza,
PagoPA, verbale, documento non associato) × 8 viewport (320×568 → 1920×1080),
verificando fit/zoom/fullscreen/download/scroll/chiusura/focus/
autorizzazione/rotazione.

### P2 — CI obbligatoria su main

**19. 🟡 CI completa e gate deploy** — esistono già `audit-static.yml`,
`smoke-runtime.yml`, `audit-layout.yml`, `verifica-produzione.yml`. Mancano
come blocking check: `backend-tests`, `frontend-lint`,
`route-map-consistency` (vedi #1), `endpoint-classification`,
`frontend-dead-code` (vedi #11), `security-tests`, `viewer-e2e` (vedi #18).
Il deploy Render deve dipendere dal verde di questi check.

---

## Completate dopo il 14/07/2026

_(nessuna ancora — questo tracking è stato appena adottato)_
