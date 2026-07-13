# Audit §13.1 — primitive browser da sostituire (frontend)
> Deliverable FASE P2 §13.1. NON sostituire in blocco: ogni occorrenza va valutata
> (toast per alert informativi, dialog per confirm, DocumentViewerModal per window.open
> di documenti; lasciare window.open legittimi verso URL esterni).

## `alert(` — ✅ COMPLETATO (0 residue)
Tutti gli alert() convertiti in toast sonner (toast.success/error/warning/info),
una pagina alla volta con build verificata: GestioneAssegni (20), Fornitori (18),
Admin (17), GestioneCespiti (9), PrimaNotaSalariTab (6), ExportButton (4),
PrimaNotaComponents (2), VerificaMovimentiBanca (1), BatchReprocessing (1).
Restano confirm()/prompt()/window.open() (sezioni sotto).

## `confirm(` — ✅ COMPLETATO (0 residue)
Tutti i confirm()/window.confirm() nativi convertiti nel ConfirmDialog canonico
(useConfirm, provider già montato in main.jsx), con title/message/variant
(danger per azioni distruttive, warning per operazioni di massa): Fornitori (5),
PuliziaPrimaNota (3), BatchReprocessing (3), Admin (1), Utenti (1),
BudgetPrevisionale (1), VerbaliRiconciliazione (1). PrimaNota.jsx usava già il pattern.

## `prompt(` — ✅ COMPLETATO (0 residue)
Unico sito reale (cambio PIN in Utenti.jsx) sostituito con dialog in-app
(input numerico, Enter/Escape, validazione 4-12 cifre). Gli altri match erano
PWA install (deferredPrompt.prompt(), legittimo) e un commento.

## `window.open(` — ✅ RIVISTI TUTTI (6 convertiti, 7 legittimi)
**Convertiti a DocumentViewerModal (viewer canonico §8, niente nuova scheda):**
- RiconciliazioneUnificata F24Tab: PDF F24 (pdf_url e file_path)
- RiconciliazioneUnificata DocumentiTab: PDF documenti non associati
- GestionePagoPA: PDF ricevuta PagoPA
- PaypalTransactionDetailModal: PDF verbale (blob, revoca URL alla chiusura)

**Legittimi, tenuti così (export/download/stampa/navigazione deliberata):**
- Commercialista.jsx:1021 — export Excel (download)
- Bilancio.jsx (2) — export PDF bilancio e confronto (download)
- ArchivioBonifici.jsx (2) — export CSV/Excel + download ZIP
- Fornitori.jsx — finestra di stampa (window.open('', '_blank') per print)
- VerbaliRiconciliazione.jsx:805 — apertura verbale in nuova scheda (route interna, scelta UX)
- PaypalTransactionDetailModal.jsx:457 — fallback apertura fattura quando onOpenInvoice non è fornito
