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

## `prompt(` — 3 occorrenze
- `components/InstallAppButton.jsx` : righe 51
- `pages/PrimaNota.jsx` : righe 1639
- `pages/Utenti.jsx` : righe 77

## `window.open(` — 13 occorrenze
- `components/PaypalTransactionDetailModal.jsx` : righe 164, 457
- `pages/ArchivioBonifici.jsx` : righe 266, 274
- `pages/Bilancio.jsx` : righe 470, 485
- `pages/Commercialista.jsx` : righe 1021
- `pages/Fornitori.jsx` : righe 3004
- `pages/GestionePagoPA.jsx` : righe 696
- `pages/RiconciliazioneUnificata.jsx` : righe 2107, 2109, 2173
- `pages/VerbaliRiconciliazione.jsx` : righe 801
