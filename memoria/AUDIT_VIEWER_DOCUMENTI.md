# AUDIT VIEWER DOCUMENTI — censimento punti di visualizzazione (§8.6)

Data: 2026-07-13 — aggiornamento verificato 2026-07-20
Ambito: frontend React/Vite (`frontend/src`) — tutti i punti in cui si
visualizzano documenti (PDF / XML / HTML fattura / immagini) e come vengono
aperti. Metodo: grep su `window.open`, `<iframe`, `<object`, `<embed`,
`DocumentViewerModal`, `pdfViewer`, `viewer`, `target="_blank"`,
`createObjectURL`, con deduplica e lettura del contesto di ogni occorrenza.

---

## 1. Componente canonico: `frontend/src/components/DocumentViewerModal.jsx`

È l'UNICO componente autorizzato per il "Vedi Documento" in-page
(PROMPT_DEFINITIVO §8.2). Modale full-screen (overlay `position:fixed inset:0`,
card `height:90vh`, `maxWidth` 960 di default) con: Chiudi, Scarica (se
`onDownload`), Schermo intero, Zoom +/−, Adatta larghezza, Adatta pagina,
scroll interno, touch/pinch, blocco scroll body, focus trap, ESC, aria-label,
ritorno focus al pulsante di origine. L'unico `<iframe>` di tutto il frontend
è al suo interno (riga 303); non esistono `<object>` né `<embed>`.

Props:

| Prop | Significato |
|---|---|
| `title` | titolo header (es. "📄 Fattura 123") |
| `subtitle` | riga secondaria opzionale |
| `documentType` | tipo logico: `fattura_html\|fattura_pdf\|cedolino\|f24\|quietanza\|estratto_conto\|documento_fiscale\|allegato_email\|verbale\|pagopa\|pdf` (default `pdf`) |
| `src` | URL diretto per l'iframe, già pronto |
| `fetchUrl` | alternativa a `src`: l'URL viene scaricato come **blob autenticato** tramite il client axios `api` (`api.get(fetchUrl, {responseType:'blob'})` → `createObjectURL`, revocato alla chiusura; gestisce errore 502/504 con messaggio) |
| `mimeType` | tipo del blob per `fetchUrl` (default `application/pdf`) |
| `onClose` | callback di chiusura |
| `onDownload` | se presente mostra il pulsante "📥 Scarica" |
| `maxWidth` | larghezza massima del modale (default 960) |
| `testIdPrefix` | prefisso `data-testid` (default `document-viewer`) |

Due modalità di autenticazione:
- **`src`** → iframe stessa-origine: l'iframe manda il **cookie di sessione**
  `access_token` verificato dal middleware globale
  `app/middleware/authentication.py` (riga 136: `request.cookies.get("access_token")`).
  Funziona solo con path relativi `/api/*` o URL blob già creati.
- **`fetchUrl`** → **blob-fetch autenticato** via client axios: per endpoint
  che non si possono mettere direttamente in un iframe.

Wrapper canonico: `frontend/src/components/ModalFattura.jsx` — wrapper sottile
su DocumentViewerModal con `src=/api/fatture-ricevute/fattura/{id}/view-assoinvoice`
(fattura elettronica resa in HTML stile AssoInvoice), props `fatturaId`,
`numero`, `onClose`.

---

## 2. Censimento completo

### 2.1 Viewer in-page (DocumentViewerModal diretto o via ModalFattura)

| Pagina/Componente | Pulsante/Azione | Documento | Componente usato | Come autentica | Mobile/Desktop | Stato/Correzione |
|---|---|---|---|---|---|---|
| `pages/PrimaNota.jsx` (1826, 3056) | Bottone "Fattura"/👁️ su movimento | Fattura elettronica (HTML ASSO) | ModalFattura → DocumentViewerModal | Cookie sessione (src `/api/fatture-ricevute/.../view-assoinvoice`) | Entrambi | OK canonico |
| `pages/ArchivioFattureRicevute.jsx` (801) | "Vedi" su riga fattura | Fattura elettronica | ModalFattura | Cookie sessione (src stessa origine) | Entrambi | OK canonico |
| `pages/Fornitori.jsx` (2259) | Fattura da estratto fornitore | Fattura elettronica | ModalFattura | Cookie sessione | Entrambi | OK canonico |
| `pages/Scadenze.jsx` (1061) | 👁️ "Visualizza Dettagli Fattura" | Fattura elettronica | ModalFattura | Cookie sessione | Entrambi | OK canonico |
| `pages/ArchivioBonifici.jsx` (1583) | Fattura associata al bonifico | Fattura elettronica | ModalFattura | Cookie sessione | Entrambi | OK canonico |
| `pages/RiconciliazionePaypal.jsx` (1342) | "Vedi" fattura dal dettaglio transazione (`onOpenInvoice`) | Fattura elettronica | ModalFattura | Cookie sessione | Entrambi | OK canonico |
| `pages/NoleggioAuto.jsx` (1927) | Fattura canone noleggio | Fattura elettronica | ModalFattura | Cookie sessione | Entrambi | OK canonico |
| `pages/GestioneAssegni.jsx` (3085) | Fattura associata ad assegno | Fattura elettronica | ModalFattura | Cookie sessione | Entrambi | OK canonico |
| `pages/Documenti.jsx` (1626) | "Vedi" documento archivio | PDF documento archiviato | DocumentViewerModal (`fetchUrl`) | Blob autenticato (`fetchUrl` + axios), con `onDownload` | Entrambi | OK canonico |
| `pages/Documenti.jsx` (1571–1586) | "Vedi" documento estratto AI (`file_base64`) | PDF documento AI | DocumentViewerModal (ma vedi nota) | Blob da base64 già in memoria | Entrambi | RESIDUO: il blob `pdfUrl` creato non viene passato al viewer, che usa `fetchUrl` con `selectedPdfDoc.id` (per i doc AI l'id è `_id` → fetch potenzialmente errato; blob mai usato né revocato). Correzione: passare `src={selectedPdfDoc.pdfUrl}` quando presente e revocarlo su close |
| `pages/RiconciliazioneUnificata.jsx` (2149, tab F24) | "👁️ Vedi PDF" su F24 | PDF F24 | DocumentViewerModal | Cookie sessione (src `f.pdf_url` oppure `/api/download/{file_path}`, path relativi `/api/*`) | Entrambi | OK canonico (convertito sessione 2026-07) |
| `pages/RiconciliazioneUnificata.jsx` (2567, tab Documenti) | "Vedi PDF" documento non associato | PDF documento | DocumentViewerModal | Cookie sessione (src `/api/documenti-non-associati/pdf/{id}`) | Entrambi | OK canonico (convertito sessione 2026-07) |
| `pages/GestionePagoPA.jsx` (743) | 👁️ su ricevuta | Ricevuta PagoPA (PDF) | DocumentViewerModal | Cookie sessione (src `/api/pagopa/ricevute/{id}/pdf`) | Entrambi | OK canonico (convertito sessione 2026-07) |
| `components/PaypalTransactionDetailModal.jsx` (587) | "Vedi PDF" verbale noleggio | Verbale (PDF) | DocumentViewerModal | Blob autenticato (axios → base64 → blob → `src`; blob revocato su close) | Entrambi | OK canonico (convertito sessione 2026-07) |
| `components/InvoiceXMLViewer.jsx` | (wrapper legacy) | Fattura elettronica | delega a ModalFattura | Cookie sessione | — | Nessun utilizzo trovato nel codice: codice morto, valutare rimozione |

### 2.2 `window.open` (8 occorrenze, tutte giustificate)

| Pagina/Componente | Pulsante/Azione | Documento | Componente usato | Come autentica | Mobile/Desktop | Stato/Correzione |
|---|---|---|---|---|---|---|
| `pages/ArchivioBonifici.jsx` (266) | Export CSV/Excel | Export scaricato | window.open | Cookie sessione (stessa origine) | Entrambi | Legittimo (export scaricato) |
| `pages/ArchivioBonifici.jsx` (274) | Download ZIP per anno | ZIP scaricato | window.open | Cookie sessione | Entrambi | Legittimo (download) |
| `pages/Fornitori.jsx` (3015) | 🖨️ Stampa estratto fatture | HTML da stampare | window.open('') + `print()` | Nessuna (contenuto già in pagina) | Desktop (stampa) | Legittimo (stampa) |
| `pages/Bilancio.jsx` (470) | Export PDF bilancio | PDF scaricato | window.open | Cookie sessione | Entrambi | Legittimo (export PDF) |
| `pages/Bilancio.jsx` (485) | Export PDF confronto anni | PDF scaricato | window.open | Cookie sessione | Entrambi | Legittimo (export PDF) |
| `pages/Commercialista.jsx` (1021) | 📊 Export Excel Commercialista | Excel scaricato | window.open | Cookie sessione | Entrambi | Legittimo (export Excel) |
| `pages/VerbaliRiconciliazione.jsx` (805) | "📄 Dettaglio" verbale | Pagina interna `/verbali-noleggio/{n}` | window.open (rotta SPA) | Cookie sessione | Entrambi | Legittimo (navigazione interna in nuova scheda) |
| `components/PaypalTransactionDetailModal.jsx` (458) | Badge "Vedi" fattura di altro anno | Fattura elettronica | window.open (solo se `onOpenInvoice` assente) | Cookie sessione | Entrambi | Legittimo (fallback fattura in nuova scheda; il chiamante RiconciliazionePaypal passa `onOpenInvoice` → viewer canonico) |

### 2.3 Link `<a target="_blank">` su documenti

| Pagina/Componente | Pulsante/Azione | Documento | Componente usato | Come autentica | Mobile/Desktop | Stato/Correzione |
|---|---|---|---|---|---|---|
| `pages/Scadenze.jsx` (827) | Link 🔗 accanto al 👁️ canonico | Fattura elettronica | link nuova scheda | Cookie sessione | Entrambi | Legittimo (affordance secondaria "apri in scheda", il canale primario 👁️ è già canonico); opzionale rimuoverlo |
| `pages/Scadenze.jsx` (1136) | "📄 Vedi" dentro il modal "Paga" | Fattura elettronica | link nuova scheda | Cookie sessione | Entrambi | RESIDUO: convertire a ModalFattura (già importato nella pagina) |
| `pages/PrimaNota.jsx` (2784) | "Bonifico" su movimento | PDF bonifico (`/api/archivio-bonifici/transfers/{id}/pdf`) | link nuova scheda | Cookie sessione | Entrambi | RESIDUO: convertire a DocumentViewerModal (src relativo già pronto) |
| `pages/PrimaNota.jsx` (2806) | "📄 F24" su movimento | PDF F24 (`/api/f24/{id}`) | link nuova scheda | Cookie sessione | Entrambi | RESIDUO: convertire a DocumentViewerModal |
| `pages/PrimaNota.jsx` (2828) | "Corrispettivo" su movimento | Vista corrispettivo XML (`/api/corrispettivi/...`) | link nuova scheda | Cookie sessione | Entrambi | RESIDUO: convertire a DocumentViewerModal |
| `pages/DettaglioVerbale.jsx` (111) | "Apri" su PDF del verbale | PDF verbale/quietanza | link nuova scheda (`pdf.url`) | Cookie sessione (se url relativo) | Entrambi | RESIDUO/RISCHIO: il backend (`app/routers/verbali_noleggio.py` 625-646, `verbali_noleggio_api.py` 80-97) NON valorizza mai `url` → quasi sempre compare solo il Badge "Disponibile" senza apertura. Correzione: usare `/api/verbali-noleggio/pdf/{numero}` + DocumentViewerModal come fa PaypalTransactionDetailModal |
| `pages/GestionePagoPA.jsx` (715) | 📥 su ricevuta | PDF ricevuta (`?download=true`) | link nuova scheda | Cookie sessione | Entrambi | Legittimo (download; il "vedi" è già canonico) |
| `pages/DocumentiFiscali.jsx` (161) | "Scarica" | Documento fiscale (`download_url` = `/api/documenti/documento/{id}/download`) | link nuova scheda | Cookie sessione | Entrambi | Legittimo (download) |
| `components/ChatIntelligente.jsx` (419) | Link 📎 allegato in risposta chat | Documento citato (`download_url` `/api/*`) | link nuova scheda | Cookie sessione | Entrambi | Legittimo (download); opzionale in futuro aprire nel viewer canonico |
| `pages/IntegrazioniOpenAPI.jsx` (309) | Download XBRL completato | File XBRL (`/api/openapi/xbrl/download/{id}`) | link nuova scheda | Cookie sessione | Entrambi | Legittimo (download) |
| `pages/hub/VeicoliHub.jsx` (84) | Export PDF costi noleggio | PDF scaricato | link nuova scheda | Cookie sessione | Entrambi | Legittimo (export PDF) |
| `pages/RiconciliazionePaypal.jsx` (875), `components/PaypalTransactionDetailModal.jsx` (544) | Link email Gmail associata | Email su Gmail | link esterno | Nessuna (URL esterno Google) | Entrambi | Legittimo (risorsa esterna, non visualizzabile in-page) |

Nota: `App.jsx` (129), `components/layout/TopNav.jsx` (195, 271) e
`pages/MappaGestionale.jsx` (427) aprono link esterni di navigazione (non
documenti) — fuori ambito, legittimi.

### 2.4 Download via blob (`createObjectURL` + `<a download>` programmato)

Tutti pattern di **export scaricato** (blob autenticato via axios, click su
link `download`, nessuna visualizzazione): `pages/RegoleCategorizzazione.jsx`
(68), `components/ExportButton.jsx` (66), `pages/ContabilitaAvanzata.jsx`
(222), `pages/Documenti.jsx` (435, `handleDownloadFile`), `pages/PrimaNota.jsx`
(403), `pages/BilancioVerifica.jsx` (140), `pages/BudgetPrevisionale.jsx`
(208), `components/prima-nota/PrimaNotaSalariTab.jsx` (178). Stato: tutti
**legittimi** (download, non viewer).

---

## 3. Contesto verificato — conversioni sessione 2026-07

Confermato da git log (`9799b2fc` "Unifica pattern Vedi Documento nel motore
condiviso DocumentViewerModal", `4d118c42` "FASE P1 §8: DocumentViewerModal
canonico con tutte le funzioni obbligatorie", `7347cfa3` "FASE P2 §13.1:
dialog PIN + window.open documenti su DocumentViewerModal", `2a63d289`
schermo intero + blocco scroll) e dal codice attuale:

- **F24 e Documenti in `RiconciliazioneUnificata.jsx`** → convertiti al viewer
  canonico (righe 2149 e 2567). ✔
- **Ricevuta PagoPA in `GestionePagoPA.jsx`** → convertita (riga 743). ✔
- **Verbale PayPal in `PaypalTransactionDetailModal.jsx`** → convertito con
  blob (base64 → blob → src, revoca su close, riga 587). ✔
- Restano **8 `window.open`** nel frontend, tutti giustificati (5 export
  scaricati, 1 stampa, 1 navigazione interna, 1 fallback fattura in nuova
  scheda) — coerente con la stima "~7 legittimi" della sessione.
- Tutti gli `src` dei viewer sono **path relativi `/api/*`** protetti dal
  middleware globale `app/middleware/authentication.py` con **cookie
  `access_token`** (verificato: riga 136 legge il cookie), oppure blob URL
  locali creati da risposte axios autenticate.

---

## 4. Viewport di test richiesti

Il viewer va verificato su questi viewport (larghezza×altezza):

- 320×568 (iPhone SE 1ª gen)
- 360×800 (Android compatto)
- 390×844 (iPhone 12/13/14)
- 412×915 (Android grande)
- 768×1024 (tablet portrait)
- 1024×768 (tablet landscape)
- 1366×768 (laptop)
- 1920×1080 (desktop)

`DocumentViewerModal` è **full-screen responsive**: overlay `fixed inset:0`
con padding 12, card `width:100%` fino a `maxWidth` e `height:90vh`, toolbar
con `flexWrap`, scroll interno `-webkit-overflow-scrolling:touch` e
`touch-action:pinch-zoom` — si adatta a tutti i viewport sopra senza scroll
orizzontale della pagina.

---

## 5. Residui / Rischi

Aggiornamento 2026-07-20: i residui applicativi elencati sotto sono stati
ricontrollati sul codice corrente e chiusi:

- `Documenti.jsx` usa già `src={selectedPdfDoc.pdfUrl}` e revoca il blob;
- `PrimaNota.jsx` apre il corrispettivo nel `DocumentViewerModal`;
- `Scadenze.jsx` usa soltanto `ModalFattura`, anche dal dialog di pagamento;
- `DettaglioVerbale.jsx` scarica il base64 autenticato per indice, crea un blob
  locale, lo apre nel viewer canonico e lo revoca alla chiusura;
- `InvoiceXMLViewer.jsx` non esiste più nel codice corrente;
- test frontend dedicato: `DettaglioVerbale.test.jsx`.

L'audit layout automatico legge ora tutte le rotte statiche da `main.jsx` e
verifica anche che, su mobile, nessun `button`/`[role="button"]` visibile abbia
un target inferiore a 36×36 px. Esito reale: 84 rotte verdi su mobile e desktop.

La lista storica seguente resta conservata come tracciabilità della baseline
del 13/07; non rappresenta più lo stato corrente.

1. **`pages/Documenti.jsx` tab documenti AI (1571-1586 vs 1626)** — bug
   residuo: il blob creato da `file_base64` (`pdfUrl`) non viene mai passato
   al viewer, che usa `fetchUrl` con `selectedPdfDoc.id`; i documenti AI sono
   identificati da `_id`, quindi il fetch può andare su
   `/api/documenti/documento/undefined/download` (errore) e il blob non viene
   mai revocato (leak). Correzione: `src={selectedPdfDoc.pdfUrl}` quando
   presente + `URL.revokeObjectURL` su close.
2. **`pages/PrimaNota.jsx` 2784/2806/2828** — bonifico PDF, F24 e
   corrispettivo aperti in nuova scheda con `<a target="_blank">`: convertire
   al viewer canonico (gli URL sono già path relativi `/api/*`).
3. **`pages/Scadenze.jsx` 1136** — "📄 Vedi" fattura nel modal Paga apre nuova
   scheda: convertire a ModalFattura (già importato).
4. **`pages/DettaglioVerbale.jsx` 111** — `pdf.url` non è mai valorizzato dai
   router backend: il pulsante "Apri" di fatto non compare (solo Badge
   "Disponibile") e comunque aprirebbe una nuova scheda. Correzione: endpoint
   `/api/verbali-noleggio/pdf/{numero}` + DocumentViewerModal (pattern già
   usato in PaypalTransactionDetailModal).
5. **`components/InvoiceXMLViewer.jsx`** — wrapper legacy senza alcun
   utilizzo: rimuovere per evitare divergenza futura.
6. Minore: `pages/Scadenze.jsx` 827 duplica il canale canonico con un link in
   nuova scheda — accettabile come affordance secondaria, valutare rimozione
   per coerenza.
