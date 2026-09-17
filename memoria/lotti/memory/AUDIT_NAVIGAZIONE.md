# AUDIT NAVIGAZIONE — fase 2 ristrutturazione (24/07/2026)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Architettura (COMPLETATO e VERIFICATO da build + 13 test)
- Fonte unica della navigazione: `frontend/src/config/navigation.js`
  (PRIMARY_TABS max 5: Oggi, Produzione, Tracciabilità, Magazzino, Acquisti;
  SECONDARY_TABS raggruppati per sezione; HACCP_TABS; VALID_TABS).
- Titoli/intestazioni: `config/pageMeta.js` (PAGE_NAMES → document.title e
  breadcrumb; PAGE_META → PageHeader; TAB_HEADER_PROPRIO).
- Permessi di navigazione: `config/permissions.js` (ADMIN_TABS, puoAprireTab).
- Hash router: `hooks/useAppNavigation.js` (tab iniziale, alias storici
  #ricettario/#food_cost → ricette, guardia admin sul tasto Indietro,
  titolo pagina sempre allineato all'hash).
- Registro pagine → componenti: `router/pages.jsx` (unico switch).
- Layout: `layouts/AppLayout.jsx` (header+nav+cornice), `layouts/KioskLayout.jsx`
  (tablet, sessioni PIN 10min magazzino / 2min cambio reparto).
- App.js: 906 → 315 righe (solo init, stato condiviso, provider, router).
- Nessuna pagina eliminata: confronto automatico degli id pre/post = identico.
- Test: `src/__tests__/navigazione.test.js` (13 test: integrità registro,
  menu per ruolo, alias hash, fallback, max 5 voci primarie).

## Menu "Altro" (COMPLETATO)
Gruppi: Produzione e scorte / Acquisti e vendita / Analisi / Amministrazione /
Supporto (le voci HACCP hanno il loro dropdown dedicato in header — scelta
storica dell'app mantenuta; il gruppo "Configurazione" chiesto dal piano è
dentro Amministrazione: Configurazione, Backoffice, Collaudi…).

## Mobile (PARZIALMENTE VERIFICATO)
- Verificato NEL CODICE: barra principale ≤5 voci; header senza sovrapposizioni
  (fix 23/07: sottotitolo nascosto <640px, bottoni icona-sola); tabelle strette
  già convertite a card nelle pagine operative; tastierino magazzino; modali
  centrati (Richiedi merce) e conferme sopra ogni modale (z-9500); tasto
  Indietro sincronizzato via hashchange (con guardia admin).
- NON VERIFICATO VISIVAMENTE a 360/390/768/1024 px: il Chromium del sandbox
  non può caricare l'app (rete in uscita bloccata). DA FARE: giro visivo di
  Enzo da telefono/tablet sulle pagine principali; ogni difetto segnalato con
  screenshot viene corretto puntualmente.
- NOTA STRUTTURALE: la nav bar orizzontale è NASCOSTA da App.css per scelta
  del titolare (navigazione = card della Home). I 5 tab primari valgono per
  titoli/ordinamento e per un eventuale ripristino della barra.

## Pagina "Oggi" (COMPLETATO)
"Cosa devo fare oggi" in testa con voci navigabili: alert critici HACCP,
lotti scaduti, lotti da usare con urgenza, produzioni previste oggi, ordini
inviati (merce da ricevere → Ricezione merce), sotto scorta, ordini in bozza,
produzione da decidere per domani. KPI economici spostati SOTTO le
"Operazioni di oggi". Ogni voce porta alla pagina interessata.
RISCHIO RESIDUO (basso): il deep-link porta alla pagina, non sempre al
singolo record (dipende dai filtri della pagina di destinazione).

## Ricerca universale (COMPLETATO backend+frontend, NON collaudata live)
- Backend: /ricerca-globale ora copre lotti (incl. GEL-/PESR- via numero),
  ricette, fornitori, materie prime, attrezzature, FATTURE, ORDINI, PRODUZIONI.
- Nuovo GET /ricerca-globale/lotto/{id}: origine (fornitori/fatture),
  quantità, consumo, residuo, scadenza, destinazione, stato, allergeni.
- Frontend: risultati per categoria + scheda lotto espandibile con
  «Apri nei Lotti». Logica di ricerca NON duplicata (un solo endpoint).
- DA FARE: collaudo live da parte di Enzo (sandbox senza accesso al backend).
