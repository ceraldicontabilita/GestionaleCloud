# DIARIO — Ceraldi ERP
## Aggiornato: Chat 8 — 10 aprile 2026

---

## CHAT 8 — Fix reload continuo + responsive completo

### CAUSA ROOT REALE del reload continuo (trovata da Emergent dopo i fix iniziali)

isMobile usato dentro sub-componenti definiti FUORI dall'export default:
- TabAnagrafica, TabCedolini, TabMovimenti, TabGiustificativi (in HRDipendenti.jsx)
- PrimaNotaDesktop, EditMovimentoModal (in PrimaNota.jsx)
- SupplierModal (in Fornitori.jsx)
- DocumentRow (in DocumentiDaRivedere.jsx)

Questi sub-componenti usavano isMobile ma non avevano il proprio useIsMobile().
Ogni mount lanciava ReferenceError: isMobile is not defined -> ErrorBoundary -> loop reload.

Fix Emergent: useIsMobile() aggiunto in ogni sub-componente + reset corretto al cambio dipendente (key + visitedTabs reset).

### Fix miei (patch chat-8)
- LearningMachine non importata in main.jsx (ReferenceError addizionale)
- Router tracciabilita duplicati in main.py rimossi
- settings_router doppio rimosso

### Responsive
- ArchivioFattureRicevute: vista mobile a card
- Fornitori: grid 1 colonna su mobile
- minWidth fissi rimossi (700/800/900/1000/1400px) da tutte le tabelle
- styles.css: CSS globale mobile

### Stato finale VERIFICATO
- HR funziona: Lesina Angela carica con tutti i dati
- 5 tab (Anagrafica, Contratti, Cedolini, Movimenti, Giustificativi) visibili
- Zero crash, zero reload
- Build OK, backend healthy

---

## TODO Chat 9
- Testare altre pagine su mobile
- PIN dipendenti, Tablet Cucina -> ceraldiapp.it
- Verificare riconciliazione cedolini estratto conto
