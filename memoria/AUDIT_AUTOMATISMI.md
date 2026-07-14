# AUDIT AUTOMATISMI — cosa gira davvero da solo, cosa no

Data: 2026-07-14. Richiesta utente: dopo aver trovato che la scansione notifiche
Aruba (fatture attese/provvisorie) era scritta nel codice ma non collegata a
nessun trigger automatico, verificare lo stesso per tutte le altre sezioni.

**Metodo**: per ogni automatismo dichiarato nel codice/documentazione, verifico
se è effettivamente registrato in `app/scheduler.py::start_scheduler()` (l'unico
punto avviato all'avvio dell'app — confermato in `app/main.py::lifespan`) o
agganciato a un evento reale (event_bus); altrimenti controllo se almeno una
pagina UI lo richiama manualmente. **Solo lettura di codice**: nessuna modifica
applicata in questo giro. Non ho accesso al database di produzione da questo
ambiente (localhost:27017 irraggiungibile): dove serve sapere "è configurato
qualcosa in una collection" lo segnalo come da verificare con te.

## Legenda stato
- ✅ **OK-automatico**: schedulato o agganciato a un evento reale.
- 🔵 **OK-manuale-per-scelta**: nessun automatismo, ma è la scelta corretta (azione delicata/una tantum) o c'è un bottone UI a disposizione.
- 🟠 **DORMIENTE**: il codice lo farebbe, ma nessun trigger reale lo esegue mai.
- ⚪ **DA VERIFICARE CON TE**: la risposta dipende da un dato che non vedo da qui (es. configurazione in una collection).

## Matrice

| Area | Automatismo dichiarato | Dove nel codice | Trigger reale trovato | Stato | Nota |
|---|---|---|---|---|---|
| Email/Aruba | Notifiche Aruba → fatture attese/provvisorie | `services/aruba_notifiche.py` | Job `aruba_notifiche_scan`, ogni ora | ✅ | Fix di ieri |
| Email/Documenti | **Fatture ESTERE via email → parsing XML vero** | `services/email_monitor_service.py::sync_email_documents` (tipo_documento="fattura_xml" per mittente attendibile) | Nessuno (raggiungibile solo da `run_full_sync`, mai schedulato) | 🟠 + ⚪ | Deliberatamente escluso ieri dal job Aruba (comportamento diverso). Serve sapere se hai già mittenti esteri configurati in `mittenti_email` prima di schedularlo (altrimenti il job non farebbe nulla) |
| Email/Documenti | Import fatture/cedolini/corrispettivi/quietanze/documenti fiscali da Drive | `services/drive_*_ingest.py` | 5 job orari + quadrature domenicali | ✅ | — |
| Email | Scan verbali CdS + link a fatture | `services/verbali_gmail_scanner.py` | Job ogni 30/60 min | ✅ | — |
| Email | Gmail full scan multi-cartella (F24/cedolini/verbali/quietanze PDF) | `services/email_full_download.py` | Job orario | ✅ | Regola esplicita nel codice: le fatture NON si scaricano da qui (solo PEC/import manuale) — coerente coi due punti sopra |
| PayPal | Recupero fatture mancanti dalla posta | `paypal_statements.py::auto_cerca_gmail` | Job giornaliero 5:30 + dentro `automazioni_prima_nota` (30 min) | ✅ | — |
| PayPal | Auto-associazione transazioni | `paypal_statements.py::auto_associa_transazioni` | Dentro `automazioni_prima_nota`, ogni 30 min | ✅ | — |
| Prima Nota | Riconciliazione automatica con estratto conto | `services/riconciliazione_bancaria.py` | Dentro `automazioni_prima_nota`, ogni 30 min | ✅ | — |
| Prima Nota | Corrispettivi→cassa, provvisori→cassa/banca, dedup fatture | `prima_nota_module/sync.py` | Dentro `automazioni_prima_nota`, ogni 30 min | ✅ | — |
| F24 | Matching automatico quietanza↔F24 | `services/drive_quietanze_ingest.py::sync` | Job orario (`drive_quietanze_ingest`) | ✅ | Matching incluso nell'ingest, non un job separato |
| F24 | Controllo scadenze + alert (2 varianti) | `f24_scadenze_check`, `f24_scadenze_check_pm` | Job giornalieri (mattina/pomeriggio) | ✅ | — |
| F24 | Verifica trattenute retroattive | — | Job dedicato | ✅ | — |
| IVA | Calcolo/liquidazione mensile | `engines/liquidazione_iva_engine.py` | Nessuno — solo `POST /api/iva/liquidazioni/calcola` su richiesta utente | 🔵 | Coerente con la specifica: la liquidazione è un atto che l'utente conferma, non va bene farla "da sola" senza controllo — **ma nessun promemoria avvisa se un mese non è stato liquidato** (vedi sotto) |
| IVA | Rilevazione anomalie (`rileva_anomalie`) | `engines/riepilogo_iva_engine.py` | Nessuno — calcolata solo quando qualcuno apre `GET /api/iva/anomalie`, zero collegamento all'alert_engine | 🟠 | Se nessuno apre la pagina IVA, un'anomalia (es. doppia detrazione, periodo mancante) resta invisibile finché non la cerchi tu |
| Contabilità | Ammortamenti cespiti (calcolo + registrazione annuale) | `routers/cespiti.py::registra_ammortamenti_anno` | Nessuno | 🔵 | Manuale per scelta (azione contabile una tantum/anno) — ok se hai un promemoria tuo, altrimenti rischio di dimenticarlo |
| Contabilità | TFR: accantonamento annuale (`calcola-batch`) | `routers/tfr.py` | Nessuno | 🔵 | Stesso discorso: azione annuale, oggi 100% manuale |
| Contabilità | Chiusura esercizio (verifica preliminare + esegui chiusura) | `routers/chiusura_esercizio.py` | Nessuno | 🔵 | Corretto che sia manuale (richiede supervisione umana): nessuna azione consigliata |
| Fornitori | Rilevazione fornitori duplicati (stessa P.IVA) | — | Job dedicato, genera alert | ✅ | — |
| Fornitori | Controllo regolarità canoni noleggio | — | Job giornaliero 7:45 | ✅ | — |
| Documenti | Classificazione automatica documenti_inbox → documenti_classificati | `documents_inbox_classify.py` | Chiamata dalla pipeline di import, non un job separato | ✅ | Succede in linea quando arriva il documento, corretto così |
| Learning Machine | Classificazione automatica costi (F24/fatture) | `services/learning_machine*.py` | Chiamata in linea da ogni import (non un job separato) | ✅ | — |
| Dipendenti | Libretti sanitari: controllo scadenze + generazione da dipendenti | `employees/dipendenti.py` (`libretti-sanitari/scadenze`, `/genera-da-dipendenti`) | Nessuno schedulato, **e nessuna pagina frontend li chiama** | 🟠 | Il più "orfano" di tutti: manca sia l'automatismo sia il bottone manuale — oggi questi endpoint sono irraggiungibili anche a mano dall'utente |
| Scadenze generali | Partite aperte, POS+calendario | `check_scadenze_partite_task`, `controllo_pos_calendario_task` | Job giornalieri 7:00/7:30 | ✅ | — |

## Riepilogo per priorità

**🟠 Dormienti trovati (3), da tua conferma prima di agire — nessuno toccato**:
1. **Fatture estere via email** — meccanismo di parsing pronto, manca sia la schedulazione sia (forse) la configurazione dei mittenti e la pagina per gestirli.
2. **Anomalie IVA** — calcolate solo su richiesta, mai segnalate proattivamente.
3. **Libretti sanitari scadenze** — nessun trigger, nemmeno un pulsante in UI.

**🔵 Manuali per scelta (cespiti/ammortamenti, TFR annuale, chiusura esercizio)**: corretto che restino un'azione deliberata dell'utente; segnalo solo che oggi non c'è nemmeno un promemoria "è ora di farlo" — se lo vuoi, è un'aggiunta leggera (un alert, non un'automazione).

## Non toccato in questo giro (fuori standard, da audit dedicato se vuoi)
- Impostazioni/canali specifici per singolo cliente (WhatsApp, PagoPA) non riverificati riga per riga: il pattern è lo stesso (job vs endpoint orfano), stessa metodologia applicabile su richiesta.
