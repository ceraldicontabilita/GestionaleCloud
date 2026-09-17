# PIANO REFACTOR — inventario file grandi (24/07/2026)

Legenda stato: [FATTO] in questa fase · [DA FARE] fasi successive.
Rischio: BASSO = pezzi già separati nello stesso file · MEDIO = stato
condiviso da districare · ALTO = effetti/logica intrecciati.

## Frontend (righe → responsabilità → split proposto → rischio)
1. [FATTO] App.js — 906→315. Split eseguito: config/navigation+pageMeta+
   permissions, hooks/useAppNavigation, layouts/AppLayout+KioskLayout,
   router/AppRouter+pages. Comportamento invariato (build ok).
2. [FATTO] BackofficeView.jsx — 1616→835→400 (25/07/2026). Estratti:
   backoffice/FormRicetta.jsx (854), backoffice/TabProdotti.jsx (273: con
   RowProdotto e PannelloSoglieSuggerite), backoffice/TabFornitori.jsx (180:
   con RowFornitore e BADGE_STATO), backoffice/toastBackoffice.js (15, prima
   duplicato). Markup 1:1. BONUS: nell'estrazione TabProdotti restava senza
   gli import di withToken e getOperatoreNome — la build NON se ne accorge
   (sono warning), sarebbe stato un crash a runtime come i due trovati in
   FornitoriList: aggiunti e verificati aprendo davvero la pagina sul rig.
3. [FATTO] FornitoriList.jsx — 1337→1199→394 (25/07/2026). Estratti:
   fornitori/SchedaAnagraficaModal.jsx (411: modale con ContattiCard,
   RegistroRicetteCard, QualitaRicetteCard, RimanenzeCard — stato nel
   genitore, solo props), fornitori/TrackerColliOmaggio.jsx (270, puro),
   fornitori/RegistroQualificaPanel.jsx (112, autonomo),
   fornitori/NoteRicevimento.jsx (64), fornitori/utilsFornitori.js (22).
   BONUS: corretti 2 crash latenti dall'estrazione di fase 2 —
   SchedeRicevimentoPanel usava BADGE_TIPO/NoteRicevimento senza import
   (ReferenceError all'apertura del registro ricevimento) e
   fornitori/FattureList usava FileText/Eye/Printer senza import (crash
   dello storico fatture nella scheda anagrafica). Verificato con
   screenshot prima/dopo sul rig locale: lista identica, modale e registro
   ora funzionanti, zero errori JS in pagina.
4. [FATTO] LottiList.jsx — 1184→681 (25/07/2026). Estratti:
   lotti/uiLotti.jsx (68: Button/Input/Badge/Modal; Card NON riscritta, si
   riusa shared/Card che era identica), utils/allergeni.js (38: le due
   costanti dei 14 allergeni + helper allergeniDaTesto con la stessa logica
   di prima), lotti/ModalDettaglioLotto.jsx (223), lotti/
   ModalRecallIngrediente.jsx (124), lotti/ModaliLotto.jsx (155: Report
   HACCP + Registro ASL + Genera Lotto). Confronto prima/dopo su rig
   locale: 10 screenshot, 7 identici al byte e 3 con differenze di solo
   1-2px di scorrimento (verificate a video: stesso contenuto), zero
   errori JS. DA SEGNALARE A ENZO (non toccato): il modale "Genera Nuovo
   Lotto" è IRRAGGIUNGIBILE — `showForm` non viene mai messo a true, in
   tutta l'app non esiste più un bottone che lo apra. Codice conservato
   così com'era in attesa della sua decisione (bottone da ripristinare o
   flusso ormai solo da tablet).
5. [FATTO in parte] tablet/ModalRegistraLotto.jsx — 1059→940 (25/07/2026).
   Estratti i due blocchi DAVVERO isolabili: registraLotto/SelettoreQuantita
   (54) e registraLotto/SelettorePosizione (97, destinazione + menu
   frigo/congelatore). Lo STATO è rimasto tutto nel modale: con ref, effetti,
   farciture, giacenza, colazione e idempotenza intrecciati, spostarlo
   sarebbe rischio puro senza guadagno. DA FARE (solo se servirà toccarli):
   blocco giacenza/farciture e step BOM.
   VERIFICA fatta: modale identico al pixel (unica differenza il progressivo
   del lotto, che avanza a ogni prova), PARAMETRI della chiamata di
   registrazione identici prima/dopo, zero errori JS.
   NOTA: il rig non può completare la registrazione (mongomock non implementa
   arrayFilters — limite noto): il collaudo end-to-end vero lo fa Enzo dal
   tablet dopo il deploy.
6. [DA FARE] VenditaBancoView 973 (SprechiView, Statistiche — BASSO);
   ColazioneAcquavivaView 832 (ALTO); OrdiniView 789 (MEDIO);
   CatalogoFornitoreView 780 (BASSO); GelatiView 775 (BASSO).

## Backend
1. [DA FARE] food_cost.py 3550 — 4 aree: dizionario / confronto prezzi /
   costing / allergeni+nutrizionale. Rischio MEDIO (helper condivisi).
2. [—] magazzino_bar_seed.py 2893 — solo dati (non urgente).
3. [DA FARE] ricette.py 2507 — CRUD / import-export / foto / tracciabilità.
4. [DA FARE] lotti_produzione.py 2124 — rischio ALTO (mutazioni lotto con
   effetti collaterali FIFO): rimandare finché non servono modifiche lì.
5. [DA FARE] fatture.py 1649, fornitori.py 1494, supervisor_operativo.py
   1314, ingredienti.py 1188, normalizzazione.py 1186, magazzino_bar.py 1157
   — tutti MEDIO, split per area funzionale.

## Regola di ingaggio per gli split futuri
Mai cambio di comportamento nello stesso commit dello spostamento; build +
test puri prima e dopo; un file per commit; collaudo live della pagina
toccata prima di dichiarare chiuso.
