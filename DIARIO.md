# DIARIO — Ceraldi ERP
## Aggiornato: Chat 8 — 10 aprile 2026

---

## CHAT 8 — Fix reload continuo + responsive completo

### BUG CRITICO risolto: reload continuo app
- Causa root: LearningMachine non importata in main.jsx -> ReferenceError -> loop reload
- Causa secondaria: 10 file usavano isMobile senza importare useIsMobile -> crash runtime
- Fix Emergent: HRDipendenti + VeicoliHub tab convertiti a display:none + visitedTabs

### Router duplicati in main.py rimossi
- Primo blocco tracciabilita HACCP (22 router duplicati)
- settings_router doppio su /api

### Responsive completo
- ArchivioFattureRicevute: vista mobile a card
- Fornitori: grid 1 colonna su mobile
- 10+ pagine: overflowX + minWidth fissi rimossi
- styles.css: CSS globale mobile

### Stato finale
Build OK, backend healthy, zero errori JS, dashboard mobile OK

---

## TODO Chat 9
- Testare pagine su mobile
- PIN dipendenti, Tablet Cucina -> ceraldiapp.it
- Verificare riconciliazione cedolini estratto conto
