# GestionaleCloud + Obsidian

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Specifiche per usare Obsidian come livello di conoscenza navigabile del GestionaleCloud senza trasformarlo nel registro operativo o contabile.

## Decisione architetturale

- **GestionaleCloud** governa stati, autorizzazioni, associazioni e processi.
- **Drive e Google Sheets** conservano documenti originali e registri operativi canonici con identificatori stabili.
- **Obsidian** riceve una proiezione ricostruibile in Markdown: relazioni, cronologie, procedure, eccezioni e conoscenza.
- **Agenti e automazioni** possono cercare e riassumere il vault, ma non possono confermare pagamenti o associazioni ambigue tramite una semplice modifica Markdown.

## Obiettivi

1. Ricerca unica per azienda, codice fiscale, targa, driver, fattura, F24, verbale, pratica o documento.
2. Navigazione bidirezionale fra soggetti, documenti, eventi e prove.
3. Dossier automatici per aziende, fornitori, clienti, dipendenti, veicoli, immobili ed enti.
4. Timeline leggibili che spieghino cosa è successo e con quali fonti.
5. Dashboard delle eccezioni: documenti mancanti, scadenze, associazioni ambigue e job falliti.
6. Manuale operativo e registro delle decisioni sempre collegati alle pagine del Gestionale.

## Contenuto della specifica

- [ARCHITETTURA.md](ARCHITETTURA.md): componenti, flussi e responsabilità.
- [MAPPA_COLLEGAMENTI.md](MAPPA_COLLEGAMENTI.md): cosa collegare in ogni area aziendale.
- [MODELLO_NOTE.md](MODELLO_NOTE.md): identificatori, proprietà e modelli Markdown.
- [SICUREZZA_E_GOVERNANCE.md](SICUREZZA_E_GOVERNANCE.md): accessi, dati sensibili e limiti.
- [PIANO_IMPLEMENTAZIONE.md](PIANO_IMPLEMENTAZIONE.md): fasi, test e criteri di accettazione.
- [PROMPT_IMPLEMENTAZIONE.md](PROMPT_IMPLEMENTAZIONE.md): prompt operativo pronto per un agente di sviluppo.
- [`templates/`](templates): esempi di note da generare.

## Funzioni Obsidian rilevanti

- Note locali in Markdown e collegamenti fra note.
- Graph per esplorare relazioni.
- Canvas per rappresentare processi e dossier.
- URI `obsidian://` per aprire note e ricerche dal Gestionale.
- CLI per leggere, scrivere, cercare e automatizzare il vault.
- Headless Sync per sincronizzare un vault da un server.
- Web Clipper per acquisire normativa e fonti ufficiali.

Fonti ufficiali:

- https://obsidian.md/
- https://obsidian.md/cli
- https://obsidian.md/canvas
- https://obsidian.md/clipper
- https://help.obsidian.md/Extending%2BObsidian/Obsidian%2BURI

## Fuori ambito

- Usare Obsidian come libro contabile o database transazionale.
- Confermare pagamenti, fatture, driver o movimenti bancari modificando una nota.
- Copiare indiscriminatamente tutti i PDF nel vault.
- Pubblicare dati fiscali, bancari, personali o PEC con Obsidian Publish.
- Installare plugin comunitari nel vault privato senza valutazione di sicurezza.
