# Istruzioni Copilot/Codex — GestionaleCloud

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

Queste istruzioni valgono per il repository canonico
`ceraldicontabilita/GestionaleCloud`, branch operativo `main`, distribuito su
`https://impresasemplice.online` tramite Render.

## Prima di modificare

- Leggere `CLAUDE.md`, `PRODUCT.md`, `DESIGN.md` e
  `LOGICA_FUNZIONAMENTO.md`.
- Trattare codice, test e configurazione corrente come autorità; i report
  datati sono fotografie storiche.
- Non includere nel commit modifiche locali non pertinenti.
- Non inserire segreti, ID privati o credenziali nel repository.

## Architettura dati

- Destinazione operativa: Google Drive per gli originali e un registro Google
  Sheets/Excel collegato a Drive per dati normalizzati, progressivi, hash,
  provenienza e relazioni.
- Le cartelle canoniche comprendono `REGISTRO DATI`, `PARTENOPAY`,
  `CODICI TRIBUTO`, `QUIETANZE` e `DICHIARAZIONI`.
- Ogni record deve avere identità canonica e provenienza. Gli import devono
  essere idempotenti: prima si calcola l'identità, poi si inserisce o aggiorna.
- Non deduplicare per solo importo. Usare identificativi esterni, hash del
  contenuto e chiavi normalizzate coerenti col dominio.
  - legacy DB è stato rimosso e non è più supportato: non usare variabili, script o dipendenze legacy DB nel codice o nella configurazione. `DATA_BACKEND` va impostato su `sheets` e la produzione deve indicare esplicitamente il registro o la cartella Drive del ledger.
- Telegram è l'unico canale operativo di alert. WhatsApp non va registrato né
  reintrodotto come fallback.
- Obsidian è solo un layer consultivo di conoscenza; non persiste dati ERP.

## Contabilità e riconciliazione

- Fattura, quietanza, movimento bancario e registrazione contabile sono fatti
  distinti, collegati dallo stesso ID operazione quando appartengono allo
  stesso evento.
- `pagato` richiede una prova identificabile; in caso ambiguo mostrare i
  candidati e `Scegli fattura`, senza associazione definitiva automatica.
- Un versamento contanti crea due lati collegati: uscita Cassa ed entrata
  Banca. Il riscontro dell'estratto conto riconcilia, non duplica.
- I POS attesi sono separati dagli accrediti bancari effettivi.
- Importi e date non bastano da soli a provare l'identità di un'operazione.

## Backend

- Python/FastAPI asincrono; non bloccare il loop con I/O sincrono pesante.
- Riutilizzare servizi e router esistenti; non duplicare logica di parsing,
  matching o persistenza.
- Gli endpoint di scrittura devono essere autenticati, validare input e
  restituire esiti espliciti.
- Errori di integrazione esterna devono fallire in modo osservabile e senza
  perdita di dati.

## Frontend

- React 18 + Vite. Usare componenti condivisi e i token in
  `frontend/src/lib/utils.js`.
- Non introdurre Tailwind o palette parallele.
- Ogni contatore/allerta deve aprire l'elenco sottostante.
- Evitare plance di pulsanti di manutenzione: i flussi normali devono essere
  automatici e idempotenti.
- Rispettare le regole di `DESIGN.md` per tabelle, modali, stati, accessibilità
  e responsività.

## Verifica minima

- Eseguire i test backend interessati e l'intera suite quando sostenibile.
- Eseguire test e build frontend per modifiche UI.
- Rigenerare gli artefatti documentali solo con lo script indicato nel loro
  header.
- Prima della pubblicazione controllare diff e file staged; dopo il push
  verificare CI, commit distribuito e comportamento reale della pagina.
# Autorità normativa

Prima di modificare il repository leggere `PROMPT_MASTER.md`: contiene in un
solo documento regole, divieti, fonti, pagine, variabili, router ed endpoint.
