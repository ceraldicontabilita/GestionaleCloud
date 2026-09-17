---
name: guida-operativa
description: Genera la guida operativa PDF dell'app, pagina per pagina e bottone per bottone, leggendola DAL CODICE (mai inventata). Usare quando il titolare chiede una guida stampabile, un manuale utente o la documentazione dei bottoni. Riusabile su qualsiasi app React/FastAPI del gruppo Ceraldi (Lotti, App dipendenti, Gestionale Cloud).
---

# Guida operativa dal codice (metodo Ceraldi)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Obiettivo: documento stampabile con, per OGNI pagina: titolo, indirizzo (#hash o route),
schede/sezioni nell'ordine reale, e tabella "Elemento → Cosa fa → Dove porta/API"
per ogni bottone/card. Le etichette citate devono essere ESATTAMENTE quelle nel JSX.

## Procedura
1. Mappa il routing (App.js / router): elenco pagine, deep-link, sezioni solo-admin.
2. Lancia 2-3 agenti di SOLA LETTURA in parallelo, ognuno su un gruppo di viste, con
   questo formato output: sezione `##` per pagina, tabella `| Elemento | Cosa fa | Dove porta/API |`.
   Imponi: fedeltà al codice, niente funzioni inventate, condizioni di visibilità esplicite.
3. Assembla: capitolo introduttivo (accesso/PIN/ruoli/navigazione) scritto a mano +
   inventari. Converti markdown→HTML (lib `markdown`, extension tables).
4. Stile stampa: A4, copertina brand, h1 con page-break, tabelle con header colorato
   (palette dell'app: per Ceraldi salvia #5b7a6b / crema #faf7f0, MAI blu/indigo/viola),
   footer con numero pagina.
5. PDF: chromium headless via playwright-core (`page.pdf`, printBackground, header/footer).
6. Pubblica il PDF in `frontend/public/guida/` (link fisso sull'app) + bottone di
   download nella pagina Guida. Consegna anche il file in chat.
7. A ogni modifica funzionale rilevante, AGGIORNA la guida e ripubblica.

## Regole di scrittura (dal titolare)
- Italiano, risultati prima delle spiegazioni, niente tecnicismi inutili.
- Ogni bottone deve dire anche QUALE chiamata al server esegue: serve per segnalare
  i bug in modo chirurgico ("bottone X della pagina Y").
