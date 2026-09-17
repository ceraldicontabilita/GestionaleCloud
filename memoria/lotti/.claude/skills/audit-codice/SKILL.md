---
name: audit-codice
description: Audit completo del codice per errori e incoerenze reali (niente stile). Usare quando il titolare chiede "ricontrolla tutto il codice", "cerca errori", o dopo grosse modifiche. Riusabile su qualsiasi app del gruppo (Lotti, App dipendenti, Gestionale Cloud).
---

# Audit codice (metodo Ceraldi)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Fase meccanica (sempre per prima, economica e oggettiva)
1. Backend Python: `python -m compileall` + `pyflakes` su tutto; trattare come GRAVI:
   nomi non definiti, chiavi dict duplicate (es. `{"$ne": a, "$ne": b}` in query Mongo:
   il primo filtro va perso in silenzio → usare `$nin`), variabili in f-string inesistenti
   nei gestori except (crash proprio quando dovrebbero loggare).
2. Coerenza frontend↔backend: estrai TUTTE le chiamate axios/fetch (`${API}/...`) e
   confrontale con le rotte reali (prefix router + decorator): ogni chiamata orfana è
   un bottone che dà 404. Verifica anche il contrario (endpoint mai chiamati = candidati
   codice morto, MA attenzione a scheduler/agenti esterni/app che condividono il DB).
3. Collection DB: cerca nomi quasi-uguali (typo → scritture perse).

## Fase semantica (agenti revisori paralleli, SOLA LETTURA)
Lancia 3 revisori su aree distinte (es. ordini/riordini, prezzi/consumi/unità, frontend).
Ogni finding deve avere: file:riga, scenario concreto di fallimento (input → comportamento
sbagliato), gravità. SOLO finding verificati: se un sospetto non regge, si scarta.
Trappole ricorrenti trovate qui: date confrontate come stringhe in formati misti
(dd/mm/yyyy vs ISO), unità mischiate (PZ vs kg) nei confronti quantità, regex non
escapate con input utente, stati legacy non inclusi nei filtri, fallback che agganciano
il documento sbagliato, doppio-tap non atomico (claim con update_one condizionale).

## Chiusura
Correggi in tranche committabili, builda frontend+backend, aggiorna la memoria di
progetto (STATO.md), PR con CI verde, deploy, VERIFICA LIVE dell'endpoint/pagina toccati.
