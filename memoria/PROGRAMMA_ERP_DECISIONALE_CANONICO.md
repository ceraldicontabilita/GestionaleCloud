# Programma ERP decisionale canonico

Ultimo aggiornamento: 2026-07-20

## Obiettivo vincolante

Evolvere Impresa Semplice in un ERP decisionale autonomo supervisionato,
operativo e verificabile. L'AI osserva, spiega e propone; puo' eseguire in
autonomia soltanto operazioni L2 a basso rischio, reversibili e ammesse da una
policy deterministica. Pagamenti, invii fiscali, scritture contabili rilevanti,
cancellazioni e operazioni economiche o legali richiedono sempre una persona.

## Decisioni architetturali già confermate

- Database operativo: MongoDB Atlas del progetto **Impresa Semplice**.
- Nessuna migrazione a PostgreSQL e nessuna migrazione verso altri progetti
  Atlas senza una nuova decisione esplicita.
- L'app MongoDB App Services `gestionale-data-api-mjhiwwp` non e' un componente
  del gestionale corrente: non ha sorgenti dati, funzioni o trigger collegati.
  Resta inutilizzata e non viene cancellata automaticamente.
- Backend e frontend esistenti restano il sistema di riferimento; le evoluzioni
  sono incrementali, reversibili e coperte da test.
- Nessun segreto deve essere scritto in chat, log, file o repository.

## Livelli di autonomia

| Livello | Significato | Stato operativo |
|---|---|---|
| L0 | Osservazione senza modifiche | consentito |
| L1 | Raccomandazione spiegata | consentito |
| L2 | Azione limitata, reversibile, basso rischio e sopra soglia | disabilitata come esecuzione; solo `ready_l2` in shadow mode |
| L3 | Approvazione umana obbligatoria | consentita come proposta, mai esecuzione automatica |
| L4 | Azione vietata | bloccata dalla policy |

La classificazione L0-L4 del motore decisionale AI e' distinta dagli omonimi
livelli tecnici eventualmente usati da singoli algoritmi storici di matching.

## Stato del programma

### Fase 1 — Audit e stabilizzazione

- [x] Mappa tecnica e funzionale del gestionale.
- [x] Audit delle rotte e delle pagine.
- [x] Audit mobile/desktop e viewer documentale.
- [x] Verifica backup e ripristino MongoDB con prova DR temporanea.
- [x] Test distruttivi eseguiti esclusivamente su database isolato.
- [x] Verifica che `gestionale-data-api-mjhiwwp` non sia usata.

### Fase 2 — Sicurezza e qualità di base

- [x] Guardie amministrative sugli endpoint distruttivi censiti.
- [x] Test frontend, backend e CI riproducibili.
- [x] Collaudo E2E isolato per conferme e permessi.
- [ ] Rotazione della credenziale MongoDB precedentemente esposta, da completare
  manualmente sulle dashboard Atlas e Render senza mostrare il valore.
- [x] Rate limiting globale e lockout dedicato sui login.
- [x] Cookie HttpOnly/SameSite=Lax/Secure in produzione, incluso il rinnovo.
- [x] Revoca JWT al logout con registro TTL e verifica fail-closed su HTTP,
  verifica sessione e WebSocket.
- [ ] Token CSRF esplicito da valutare soltanto per eventuali integrazioni
  future che richiedano cookie cross-site; oggi SameSite=Lax blocca le
  scritture cross-site basate sul cookie.
- [ ] MFA per amministratori e approvatori.

### Fase 3 — Fondazione decisionale supervisionata

- [x] Record strutturato `ai_decisions`.
- [x] Cronologia append-only `ai_decision_events`.
- [x] Policy deterministica L0-L4 fail-closed.
- [x] Soglie configurabili per confidenza e impatto L2.
- [x] Approvazione e rifiuto riservati agli amministratori.
- [x] Divieto di auto-approvazione dell'agente.
- [x] Interruttore globale delle automazioni.
- [x] Modalità shadow: nessun executor di azioni di business.
- [x] Pagina Decisioni con spiegazione, rischio, confidenza e impatto.
- [ ] Pulsante Modifica proposta con nuova versione tracciata.
- [ ] Vista completa delle fonti autorizzate e della cronologia.
- [ ] Executor tipizzato L2, ancora vietato finché le metriche non sono accettate.

### Fase 4 — Agenti specializzati, uno alla volta

Ordine di attivazione in shadow mode:

1. [x] Tesoreria — primo nucleo shadow su scadenze scadute e orizzonte 30 giorni,
   con soli aggregati minimizzati e senza strumenti di pagamento.
   - [ ] Estendere a saldi, banche, POS, PayPal, assegni e bonifici.
2. [ ] Contabile — quadrature, prima nota e scritture suggerite.
3. [ ] Fiscale — IVA, F24, ritenute e pacchetto commercialista.
4. [ ] CFO — cash flow a 13 settimane e scenari.
   - [x] Motore deterministico CF13W-001 con saldi canonici, rate fornitori,
     obblighi e crediti dotati di scadenza.
   - [x] Scenari base, prudente e stress, copertura dati ed esclusioni visibili.
   - [x] Agente `CashFlow13WShadow`: sola proposta L1/L3, nessuna disposizione.
   - [ ] Estendere le entrate attese a POS e PayPal solo dopo aver materializzato
     date di accredito affidabili e anti-duplicazione.
5. [ ] Acquisti — prezzi, fornitori e riordino suggerito.
6. [ ] Crediti — aging e bozze di sollecito, mai inviate senza approvazione.
7. [ ] Compliance — permessi, tracciabilità e documenti mancanti.

Ogni agente usa servizi applicativi tipizzati; non accede direttamente alle
collection per compiere azioni operative. L'attivazione di un agente richiede
unit test, test dei permessi, dati incompleti/contraddittori, indisponibilità dei
servizi esterni e un periodo misurato in shadow mode.

### Fase 5 — Flussi ERP prioritari

- [x] Caso fatture XML rateizzate: scadenze multiple idempotenti, blocco del
  falso pagamento unico e proposta N assegni verso una fattura (PR #73).
- [ ] Consolidare riconciliazione certa/ambigua e idempotenza concorrente.
- [ ] Duplicati fatture prima della contabilizzazione.
- [ ] F24 e disposizioni di pagamento preparate ma mai eseguite dall'AI.
- [ ] Stato e autore di ogni approvazione visibili nel flusso operativo.
- [ ] Rollback applicativo delle future azioni L2.

### Fase 6 — Autonomia L2 controllata

L'esecuzione L2 resta disabilitata fino a quando, per il singolo caso d'uso:

- il periodo shadow ha dati sufficienti;
- precisione, falsi positivi e impatti sono misurati;
- non esistono ambiguità o dati mancanti;
- rollback e idempotenza sono provati;
- l'amministratore approva esplicitamente regola, soglia e ambito;
- l'interruttore globale e l'audit sono verificati in E2E.

## Prossimo ordine operativo

1. Completare e pubblicare la fondazione decisionale della Fase 3.
2. Preparare una procedura separata e controllata per correggere gli eventuali
   dati storici rateizzati; nessun dato reale viene corretto automaticamente.
3. Estendere l'Agente Tesoreria shadow alle fonti bancarie e ai canali di incasso.
4. [x] Implementare il primo cash flow a 13 settimane dopo la qualità delle scadenze.
5. Estendere la copertura di incassi e obblighi senza stimare dati mancanti.
6. Completare MFA e la verifica delle future esigenze CSRF prima di abilitare qualsiasi L2.

## Regola di avanzamento

Ogni blocco viene implementato, collaudato, registrato e pubblicato su `main`
solo se i test pertinenti sono verdi. Un errore blocca il blocco corrente, non
autorizza scorciatoie e non modifica i vincoli di sicurezza.
