# Audit §13.1 — primitive browser da sostituire (frontend)
> Deliverable FASE P2 §13.1. NON sostituire in blocco: ogni occorrenza va valutata
> (toast per alert informativi, dialog per confirm, DocumentViewerModal per window.open
> di documenti; lasciare window.open legittimi verso URL esterni).

## `alert(` — 79 occorrenze
- `components/ExportButton.jsx` : righe 25, 75, 83, 125
- `components/prima-nota/PrimaNotaComponents.jsx` : righe 538, 542
- `components/prima-nota/PrimaNotaSalariTab.jsx` : righe 188, 194, 200, 203, 228, 231
- `pages/Admin.jsx` : righe 236, 245, 254, 256, 259, 274, 285, 349, 356, 365, 371, 382, 386, 395, 401, 1586, 1589
- `pages/BatchReprocessing.jsx` : righe 71
- `pages/Fornitori.jsx` : righe 261, 1331, 1349, 1366, 1380, 1404, 1447, 1461, 1496, 1501, 1506, 1537, 1547, 1557, 1582, 1608, 2908, 2942
- `pages/GestioneAssegni.jsx` : righe 218, 229, 238, 241, 269, 343, 374, 395, 414, 471, 490, 509, 536, 545, 561, 576, 593, 625, 891, 2198
- `pages/GestioneCespiti.jsx` : righe 252, 268, 275, 278, 287, 291, 295, 319, 339
- `pages/NoleggioAuto.jsx` : righe 1784
- `pages/VerificaMovimentiBanca.jsx` : righe 62

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
