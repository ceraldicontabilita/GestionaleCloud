# AUDIT FRONTEND DEAD CODE — GestionaleCloud

> Generato da `scripts/audit_frontend_dead_code.py` seguendo il grafo di import reale a partire da `main.jsx`/`App.jsx`/`navigation.config.js` (import statici, `import()` dinamici, `lazy(() => import(...))`, re-export `export {X} from`/`export * from`).
> NON modificare a mano: rilancia lo script.

**Totale file analizzati:** 152

| Classificazione | File |
|---|---:|
| ENTRYPOINT | 3 |
| ROUTE_ATTIVA | 30 |
| COMPONENTE_USATO | 80 |
| MODALE_USATO | 4 |
| HOOK_USATO | 3 |
| TEST_ONLY | 9 |
| DINAMICO_DA_VERIFICARE | 23 |
| ORFANO_ELIMINABILE | 0 |

## ORFANO_ELIMINABILE — candidati eliminazione

Nessun import statico o dinamico risolvibile li raggiunge da `main.jsx`/`App.jsx`/`navigation.config.js`, e il nome del file non compare altrove nel codice (safety net anti falso-positivo). Decisione conservativa (§7): NON eliminare in blocco — verificare uno per uno, poi `yarn build && yarn lint` dopo ogni piccolo gruppo.

_Nessuno._

## DINAMICO_DA_VERIFICARE

Non raggiunti dal grafo di import statico, ma il nome del file compare altrove nel codice (possibile riferimento dinamico/stringa) oppure il file stesso usa un `import()` con template literal non risolvibile staticamente. Verificare manualmente prima di decidere.

| File |
|---|
| `frontend/src/components/AgentiPanel.jsx` |
| `frontend/src/components/NotificationBell.jsx` |
| `frontend/src/components/ui/avatar.jsx` |
| `frontend/src/components/ui/checkbox.jsx` |
| `frontend/src/components/ui/command.jsx` |
| `frontend/src/components/ui/dialog.jsx` |
| `frontend/src/components/ui/drawer.jsx` |
| `frontend/src/components/ui/form.jsx` |
| `frontend/src/components/ui/label.jsx` |
| `frontend/src/components/ui/popover.jsx` |
| `frontend/src/components/ui/progress.jsx` |
| `frontend/src/components/ui/sheet.jsx` |
| `frontend/src/components/ui/switch.jsx` |
| `frontend/src/components/ui/table.jsx` |
| `frontend/src/components/ui/textarea.jsx` |
| `frontend/src/components/ui/toast.jsx` |
| `frontend/src/components/ui/toaster.jsx` |
| `frontend/src/components/ui/toggle.jsx` |
| `frontend/src/components/ui/tooltip.jsx` |
| `frontend/src/hooks/use-toast.js` |
| `frontend/src/hooks/usePrimaNota.js` |
| `frontend/src/stores/primaNotaStore.js` |
| `frontend/src/test/setup.js` |

## Dettaglio completo

| File | Classificazione | Importato da (n. file) |
|---|---|---:|
| `frontend/src/App.jsx` | ENTRYPOINT | 1 |
| `frontend/src/api.js` | COMPONENTE_USATO | 79 |
| `frontend/src/components/AgentiPanel.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ChatIntelligente.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/CopyLinkButton.jsx` | COMPONENTE_USATO | 5 |
| `frontend/src/components/DocumentViewerModal.jsx` | MODALE_USATO | 8 |
| `frontend/src/components/ErrorBoundary.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/components/ExportButton.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/F24EmailSync.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/InstallAppButton.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ModalFattura.jsx` | MODALE_USATO | 9 |
| `frontend/src/components/NotificationBell.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/PageLayout.jsx` | COMPONENTE_USATO | 42 |
| `frontend/src/components/PaypalTransactionDetailModal.jsx` | MODALE_USATO | 1 |
| `frontend/src/components/Portal.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/UploadStatusBar.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/Badge.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/Button.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/components/ds/Card.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/HubTabs.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/Input.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/ListaAdattiva.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/PageHeader.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/components/ds/PageLoader.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/Select.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/StatCard.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/Table.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/components/ds/Tabs.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ds/index.js` | COMPONENTE_USATO | 57 |
| `frontend/src/components/layout/TopNav.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ui/ConfirmDialog.jsx` | MODALE_USATO | 23 |
| `frontend/src/components/ui/alert.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ui/avatar.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/badge.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ui/button.jsx` | COMPONENTE_USATO | 3 |
| `frontend/src/components/ui/card.jsx` | COMPONENTE_USATO | 3 |
| `frontend/src/components/ui/checkbox.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/command.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/dialog.jsx` | DINAMICO_DA_VERIFICARE | 1 |
| `frontend/src/components/ui/drawer.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/form.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/input.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/components/ui/label.jsx` | DINAMICO_DA_VERIFICARE | 1 |
| `frontend/src/components/ui/popover.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/progress.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/select.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ui/sheet.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/sonner.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/components/ui/switch.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/table.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/tabs.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/components/ui/textarea.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/toast.jsx` | DINAMICO_DA_VERIFICARE | 1 |
| `frontend/src/components/ui/toaster.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/toggle.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/components/ui/tooltip.jsx` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/contexts/AnnoContext.jsx` | COMPONENTE_USATO | 48 |
| `frontend/src/contexts/AuthContext.jsx` | COMPONENTE_USATO | 7 |
| `frontend/src/contexts/AuthContext.test.jsx` | TEST_ONLY | 0 |
| `frontend/src/contexts/UploadContext.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/hooks/use-toast.js` | DINAMICO_DA_VERIFICARE | 1 |
| `frontend/src/hooks/useData.js` | HOOK_USATO | 1 |
| `frontend/src/hooks/useHashState.js` | HOOK_USATO | 8 |
| `frontend/src/hooks/usePrimaNota.js` | DINAMICO_DA_VERIFICARE | 0 |
| `frontend/src/hooks/useWebSocket.js` | HOOK_USATO | 1 |
| `frontend/src/lib/queryClient.js` | COMPONENTE_USATO | 2 |
| `frontend/src/lib/utils.js` | COMPONENTE_USATO | 99 |
| `frontend/src/lib/utils.test.js` | TEST_ONLY | 0 |
| `frontend/src/main.jsx` | ENTRYPOINT | 0 |
| `frontend/src/navigation.config.js` | ENTRYPOINT | 0 |
| `frontend/src/pages/Admin.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Agenti.jsx` | ROUTE_ATTIVA | 2 |
| `frontend/src/pages/Agenti.test.jsx` | TEST_ONLY | 0 |
| `frontend/src/pages/ArchivioBonifici.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/ArchivioFattureRicevute.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/BatchProcessor.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/BatchReprocessing.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Bilancio.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/BilancioVerifica.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/BudgetPrevisionale.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/CalendarioFiscale.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/CedoliniSalari.jsx` | ROUTE_ATTIVA | 2 |
| `frontend/src/pages/CedoliniSalari.test.jsx` | TEST_ONLY | 0 |
| `frontend/src/pages/ChiusuraEsercizio.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/CoerenzaPOSCorrispettivi.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/pages/CoerenzaPOSCorrispettivi.test.jsx` | TEST_ONLY | 0 |
| `frontend/src/pages/Commercialista.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/ContabilitaAvanzata.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/ControlloMensile.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Corrispettivi.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Dashboard.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/DashboardRelazionale.jsx` | ROUTE_ATTIVA | 2 |
| `frontend/src/pages/DatiProvvisoriPage.jsx` | ROUTE_ATTIVA | 2 |
| `frontend/src/pages/DettaglioVerbale.jsx` | ROUTE_ATTIVA | 2 |
| `frontend/src/pages/DettaglioVerbale.test.jsx` | TEST_ONLY | 0 |
| `frontend/src/pages/Documenti.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/FattureEstereVerifica.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/FinanziamentoSoci.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Finanziaria.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Fornitori.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/GestioneAssegni.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/pages/GestioneAssegni.test.jsx` | TEST_ONLY | 0 |
| `frontend/src/pages/GestioneCespiti.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/GestioneIVA.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/GestionePagoPA.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/GestioneRiservata.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/ImportDocumenti.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/pages/ImportDocumenti.test.jsx` | TEST_ONLY | 0 |
| `frontend/src/pages/ImpostazioniAI.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/ImpostazioniF24Email.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/InserimentoRapido.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/IntegrazioniOpenAPI.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/LearningMachine.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/LearningMachineUniversale.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/LibroGiornale.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Login.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/MFAAdmin.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/MappaGestionale.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/MittentiEmail.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Mutui.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/NoleggioAuto.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/PaginaNonTrovata.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/Pianificazione.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/PianoDeiConti.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/PrevisioniAcquisti.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/PrimaNota.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/pages/PrimaNota.test.jsx` | TEST_ONLY | 0 |
| `frontend/src/pages/PuliziaPrimaNota.jsx` | ROUTE_ATTIVA | 2 |
| `frontend/src/pages/RegoleCategorizzazione.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/RiconciliazionePaypal.jsx` | COMPONENTE_USATO | 2 |
| `frontend/src/pages/RiconciliazioneUnificata.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Ritenute.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/Scadenze.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/Utenti.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/UtileObiettivo.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/VerbaliRiconciliazione.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/VerificaCoerenza.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/VerificaMovimentiBanca.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/Visure.jsx` | COMPONENTE_USATO | 1 |
| `frontend/src/pages/hub/AdminHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/ContabilitaHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/DashboardHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/DocumentiHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/FattureHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/FornitoriHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/IntegrazioniHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/PrimaNotaHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/RiconciliazioneHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/StrumentiHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/pages/hub/VeicoliHub.jsx` | ROUTE_ATTIVA | 1 |
| `frontend/src/stores/primaNotaStore.js` | DINAMICO_DA_VERIFICARE | 1 |
| `frontend/src/test/setup.js` | DINAMICO_DA_VERIFICARE | 0 |

