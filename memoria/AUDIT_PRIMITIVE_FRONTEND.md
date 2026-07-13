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

## `confirm(` — 36 occorrenze
- `pages/Admin.jsx` : righe 1195
- `pages/ArchivioBonifici.jsx` : righe 242, 366, 430
- `pages/BatchReprocessing.jsx` : righe 294, 309, 321
- `pages/BudgetPrevisionale.jsx` : righe 154
- `pages/ChiusuraEsercizio.jsx` : righe 85, 117
- `pages/Corrispettivi.jsx` : righe 86
- `pages/Fornitori.jsx` : righe 1392, 1415, 1440, 2889, 2923
- `pages/GestioneAssegni.jsx` : righe 402
- `pages/GestioneCespiti.jsx` : righe 329
- `pages/ImpostazioniF24Email.jsx` : righe 399
- `pages/LearningMachine.jsx` : righe 290
- `pages/NoleggioAuto.jsx` : righe 246
- `pages/PianoDeiConti.jsx` : righe 157
- `pages/PrimaNota.jsx` : righe 285, 367, 533, 913
- `pages/PuliziaPrimaNota.jsx` : righe 64, 101, 145
- `pages/RiconciliazionePaypal.jsx` : righe 236
- `pages/RiconciliazioneUnificata.jsx` : righe 458, 2111, 2216
- `pages/Scadenze.jsx` : righe 132
- `pages/Utenti.jsx` : righe 89
- `pages/VerbaliRiconciliazione.jsx` : righe 150

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
