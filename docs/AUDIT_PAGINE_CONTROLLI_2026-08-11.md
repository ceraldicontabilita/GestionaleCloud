# Audit pagine e controlli UI — 2026-08-11

Questo documento censisce le superfici già verificate nel branch `audit/consolidamento-erp-2026-08-11`.

Legenda decisioni: **TENERE**, **AUTOMATIZZARE**, **SPOSTARE**, **ACCORPARE**, **ELIMINARE**.

## DocumentiHub

| Controllo / funzione | Cosa fa | Decisione | Stato |
|---|---|---|---|
| Carica documenti | Apre `ImportDocumenti`, unico ingresso utente per file/ZIP | TENERE | CANONICO |
| Archivio documenti | Apre archivio dei documenti acquisiti | TENERE | CANONICO |
| Sincronizza Drive | Chiamava `POST /api/documenti/drive/sync` | AUTOMATIZZARE | RIMOSSO; sync all'apertura |
| Catalogo cartelle Drive | Mostra cartelle censite e parser disponibili | TENERE come informazione | ATTIVO |

**Classificazione pagina:** MANTENERE. È il punto unico di ingresso e archivio documentale.

## RiconciliazioneHub

| Controllo / sezione | Cosa fa | Decisione | Stato |
|---|---|---|---|
| Riconciliazione | Vista centrale di riconciliazione bancaria | TENERE | ATTIVO |
| Movimenti Banca | Consulta/verifica movimenti bancari | SPOSTARE qui da Strumenti | APPLICATO |
| F24 | Gestione/riconciliazione F24 | ACCORPARE nell'hub | GIÀ HUB |
| PagoPA | Associa ricevute PagoPA ai movimenti bancari | SPOSTARE qui da Integrazioni | APPLICATO |
| Bonifici | Archivio/disposizioni e associazioni bonifici | ACCORPARE nell'hub | GIÀ HUB |
| Assegni | Gestione assegni e riscontro | ACCORPARE nell'hub | GIÀ HUB |
| PayPal | Riconciliazione transazioni PayPal | ACCORPARE nell'hub | GIÀ HUB |
| Coerenza POS | Controlli incassi/POS | ACCORPARE nell'hub | GIÀ HUB |

**Classificazione pagina:** MANTENERE come unica area Banca/Riconciliazione. Le sottosezioni non sono pagine primarie.

## GestionePagoPA

| Controllo | Cosa fa | Decisione | Stato |
|---|---|---|---|
| Aggiorna | Riesegue `fetchStats()` e `fetchRicevute()` | ELIMINARE | DA APPLICARE: i dati vengono già caricati all'apertura |
| Auto-Associa | Chiama `POST /api/pagopa/auto-associa` | AUTOMATIZZARE solo se backend garantisce match univoci | DA AUDIT BACKEND |
| Ricerca | Filtra ricevute per identificativo/beneficiario | TENERE | ATTIVO |
| Filtro stato | Filtra associate/non associate | TENERE | ATTIVO |
| Visualizza documento | Apre ricevuta/documento | TENERE | ATTIVO |

**Classificazione pagina:** TRASFORMARE IN TAB di Riconciliazione. Spostamento applicato.

## StrumentiHub

| Controllo / sezione | Cosa fa | Decisione | Stato |
|---|---|---|---|
| Verifica Coerenza | Controlli trasversali | TENERE | ATTIVO |
| Movimenti Banca | Consultazione movimenti | SPOSTARE in Riconciliazione | RIMOSSO DA STRUMENTI |
| Commercialista | Preparazione/invio materiale amministrativo | TENERE | ATTIVO |
| Pianificazione | Agenda interna | DA VALUTARE contro Scadenze | AUDIT APERTO |
| Visure | Richieste/archivio visure | TENERE oppure spostare in Integrazioni | AUDIT APERTO |

**Classificazione pagina:** MANTENERE ridotta; evitare che diventi il cassetto universale delle funzioni senza una casa.

## FattureHub

| Controllo / sezione | Cosa fa | Decisione | Stato |
|---|---|---|---|
| Archivio fatture | Consulta fatture ricevute | TENERE | ATTIVO |
| Corrispettivi | Gestione corrispettivi | ACCORPARE come tab | GIÀ HUB |

**Classificazione pagina:** MANTENERE. Corrispettivi non è una pagina primaria autonoma.

## PrimaNotaHub

| Controllo / sezione | Cosa fa | Decisione | Stato |
|---|---|---|---|
| Prima Nota | Registro operativo | TENERE | ATTIVO |
| Pulizia Prima Nota | Manutenzione duplicati/incoerenze | ACCORPARE come strumento interno | GIÀ INTERNO |

**Classificazione pagina:** MANTENERE. Pulizia non va esposta come pagina primaria.

## CedoliniSalari

| Controllo | Cosa fa | Decisione | Stato |
|---|---|---|---|
| Importa prospetto Excel in Documenti | Porta l'utente al flusso Import Documenti | ELIMINARE dalla pagina | DA APPLICARE |
| Importa cedolino in Documenti | Porta l'utente al flusso Import Documenti | ELIMINARE dalla pagina | DA APPLICARE |
| Importa bonifico in Documenti | Porta l'utente al flusso Import Documenti | ELIMINARE dalla pagina | DA APPLICARE |
| Upload legacy `/api/prima-nota-salari/import-bonifici` | Import diretto storico | ELIMINARE dall'interfaccia; mantenere backend solo se usato dalla pipeline | DA AUDIT |
| Upload allegato cedolino/bonifico su singola riga | Allega PDF direttamente al record | ELIMINARE dall'interfaccia dopo verifica pipeline centrale | DA AUDIT |
| Export AppDipendenti | Esporta PDF originali e registri | TENERE | ATTIVO |
| Anno | Filtro | TENERE | ATTIVO |
| Cerca dipendente | Filtro | TENERE | ATTIVO |
| Vedi cedolino | Apre PDF | TENERE | ATTIVO |
| Vedi bonifico | Apre PDF | TENERE | ATTIVO |
| Stato banca | Mostra riconciliato/da verificare | TENERE | ATTIVO |

**Classificazione pagina:** MANTENERE come consultazione, controllo e riconciliazione. Nessun ingresso documentale.

## ContabilitaHub

Oggi espone 15 sottosezioni. Il problema non è la route, ma la quantità di superfici mentali presentate all'utente.

| Sezioni attuali | Decisione proposta |
|---|---|
| Piano dei Conti | TENERE |
| Bilancio + Verifica Bilancio + Controllo Mensile | ACCORPARE in `Bilancio` con tab interni |
| Libro Giornale | TENERE |
| Calendario Fiscale | SPOSTARE/ACCORPARE con Scadenze |
| Cespiti | TENERE |
| Finanziaria + Mutui | ACCORPARE in `Finanza` |
| Chiusura Esercizio | TENERE, area protetta |
| Budget + Utile Obiettivo + Previsioni Acquisti | ACCORPARE in `Budget e Previsioni` |
| Contabilità Avanzata | DIAGNOSTICA/strumenti avanzati, non pagina quotidiana |
| Dati ISA | TENERE se operativo, altrimenti tab fiscale |

**Obiettivo dell'hub:** passare da 15 scelte visibili a circa 8 aree coerenti.

## AdminHub

| Controllo / sezione | Cosa fa | Decisione | Stato |
|---|---|---|---|
| Sistema | Amministrazione tecnica | TENERE | ATTIVO |
| Sicurezza MFA | Gestione MFA | TENERE | ATTIVO |
| Batch Processor | Catena automatica ordinaria; dichiara auto-run all'apertura | TENERE come diagnostica/stato | ATTIVO |
| Batch Reprocessing | Preview, dry-run e riprocessamento selettivo F24/Cedolini | ACCORPARE sotto Manutenzione Batch | DA PROGETTARE |

**Classificazione pagina:** MANTENERE come area tecnica riservata; non contare i batch come pagine operative quotidiane.

## IntegrazioniHub

| Controllo / sezione | Cosa fa | Decisione | Stato |
|---|---|---|---|
| OpenAPI | Servizio esterno | TENERE | ATTIVO |
| PagoPA | Riconcilia ricevute con banca | SPOSTARE in Riconciliazione | APPLICATO |
| Mittenti Email | Configurazione mittenti/autorizzazioni | TENERE | ATTIVO |

**Classificazione pagina:** MANTENERE per configurazioni/servizi esterni. PagoPA non appartiene più qui.

## App / navigazione

| Controllo / voce | Decisione | Stato |
|---|---|---|
| Popup F24EmailSync | ELIMINARE | RIMOSSO e componente cancellato |
| Assegni nel menu principale | ELIMINARE duplicazione | RIMOSSO |
| PayPal nel menu principale | ELIMINARE duplicazione | RIMOSSO |
| F24 nel menu principale | ELIMINARE duplicazione | RIMOSSO |
| Incassi POS nel menu principale | ELIMINARE duplicazione | RIMOSSO |
| Mappa Gestionale nel menu operativo | SPOSTARE in Diagnostica/Admin | RIMOSSO DAL MENU |

## Prossimi controlli obbligatori

1. `CedoliniSalari`: rimozione effettiva dei tre accessi Import e del codice upload non più necessario.
2. `GestionePagoPA`: eliminare `Aggiorna`; auditare `auto-associa` prima di renderlo automatico.
3. `RiconciliazionePaypal`: censire sync/import/manualità.
4. `ArchivioBonifici`: censire import/sync/associa/disassocia e distinguere disposizione da prova bancaria.
5. `Corrispettivi` + `CoerenzaPOSCorrispettivi`: eliminare import e sync manuali, mantenere controlli.
6. `VerificaMovimentiBanca`: eliminare import locale se presente; l'ingresso deve essere Documenti.
7. `GestioneCespiti` e `LibroGiornale`: rimuovere import locali.
8. `ContabilitaHub`: implementare accorpamenti solo dopo censimento dei controlli delle 15 sottosezioni.
