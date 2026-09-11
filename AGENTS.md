# Istruzioni Codex — GestionaleCloud

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-11
storage_architecture: supabase-runtime-drive-originals
-->

Queste istruzioni valgono per l'intero repository.

## Autorità e avvio

- Lavora esclusivamente sul repository canonico `ceraldicontabilita/GestionaleCloud`
  e sincronizza `origin/main` prima di intervenire.
- Leggi `PROMPT_MASTER.md`, `CLAUDE.md`, `PRODUCT.md`, `DESIGN.md`,
  `LOGICA_FUNZIONAMENTO.md` e `docs/AI_GOVERNANCE.md` prima di modificare il prodotto.
- Applica sempre `docs/REGOLA_FISSA_ATTESE.md`: il fatto owner crea obblighi e
  attese; le prove future possono solo soddisfarli o lasciarli da verificare.
- Per cedolini, salari e bonifici applica integralmente
  `docs/PROMPT_CEDOLINI_NETTO_DRIVE_SALARI.md`.
- Codice, test, configurazione corrente e dati sorgente verificabili prevalgono
  su report, ZIP, documentazione obsoleta o checkout storici.
- Preserva modifiche locali non pertinenti e non inserire segreti o dati
  personali nel repository.

## Architettura dati corrente

- `Supabase` è il registro operativo strutturato del GestionaleCloud.
- `Google Drive` conserva gli originali documentali e le prove sorgente.
- `Google Sheets` non deve essere introdotto in nuovi flussi applicativi. Il
  runtime Sheets esistente è compatibilità transitoria/rollback e va eliminato
  solo dopo verifica di equivalenza dati e test di regressione.
- Una risposta HTTP, un PDF, una riga importata o una proposta AI non diventano
  automaticamente una prova contabile. La semantica della fonte prevale sulla
  comodità del collegamento.

## Metodo AI per audit e refactoring

- Usa i prompt versionati sotto `prompts/` come contratti di lavoro, non prompt
  improvvisati nella chat.
- Ogni audit deve distinguere almeno: `verificato`, `probabile`, `non verificato`
  e citare file, funzione, endpoint o test che sostiene la conclusione.
- Prima di modificare una funzione censisci chiamanti, persistenza, effetti
  collaterali, autorizzazioni e test esistenti.
- Non creare nuove pagine, modali, endpoint, tabelle o servizi se una funzione
  equivalente esiste già. Prima cercala nel repository e verifica che sia usata.
- Refactoring strutturale e modifica funzionale devono essere separati quando
  possibile. Ogni intervento deve avere un criterio di accettazione osservabile.
- Vietato mascherare funzioni incomplete con dati finti, fallback silenziosi,
  mock permanenti o successi simulati.

## Regole inderogabili per cedolini e salari

- Google Drive è l'archivio canonico dei PDF; gli indici devono usare link
  Drive stabili e mai percorsi locali Windows.
- Il netto pagabile proviene soltanto dalla cella graficamente associata a
  `TOTALE NETTO`, `NETTO DEL MESE` o a un'etichetta equivalente verificata.
- Non usare come netto detrazioni, competenze, trattenute, imponibili, TFR,
  arrotondamenti, `ARR. PREC.`, `ARR. ATTUALE` o l'importo nel filename.
- Se il netto è vuoto, il valore resta nullo. Non inferire zero e non scegliere
  il numero più vicino.
- Soltanto lo stato `NETTO_VERIFICATO_DA_CEDOLINO` alimenta automaticamente
  la Prima Nota salari (`/api/prima-nota-salari`, riconciliazione stipendi)
  e i bonifici da assegnare. La pagina `/salari` non esiste più (03/09/2026):
  i cedolini si consultano nell'app HR a `/hr`.
- Una riga salariale indica un importo dovuto, non prova un pagamento. Pagato e
  riconciliato richiedono evidenza bancaria reale e relazione auditabile.
- Un duplicato certo richiede hash identico. Nome, dipendente, mese e importo
  uguali non autorizzano da soli eliminazione o cestinamento.
- Prima di trasmettere dati retributivi personali al gestionale live, mostra
  conteggi e impatto e richiedi conferma esplicita dell'utente.

## Implementazione e pubblicazione

- Riusa pagine, router, servizi, registri Supabase e viewer esistenti; non creare
  pipeline o archivi paralleli.
- Ogni scrittura deve essere idempotente, tracciabile e coperta da test sui casi
  positivo, nullo, ambiguo, multipagina ed errore parser.
- Le RPC Supabase privilegiate devono avere autenticazione applicativa esplicita,
  `search_path` fissato e privilegi minimi. Non rimuovere controlli di accesso
  per far passare una chiamata.
- Prima del push controlla il diff e aggiorna l'inventario Markdown tramite
  `scripts/refresh_markdown_docs.py` quando aggiungi documentazione.
- Prima di dichiarare il lavoro live verifica test, build, CI, commit distribuito
  e comportamento reale dell'endpoint o della pagina interessata.
