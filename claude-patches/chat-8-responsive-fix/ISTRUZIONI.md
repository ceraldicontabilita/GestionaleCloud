# Patch chat-8 — Fix responsive tutte le pagine

## File da sostituire

| File patch | Destinazione |
|---|---|
| ArchivioFattureRicevute.jsx | frontend/src/pages/ArchivioFattureRicevute.jsx |
| Fornitori.jsx | frontend/src/pages/Fornitori.jsx |
| Riconciliazione.jsx | frontend/src/pages/Riconciliazione.jsx |
| HRCedolini.jsx | frontend/src/pages/hr/HRCedolini.jsx |
| HRDipendenti.jsx | frontend/src/pages/hr/HRDipendenti.jsx |
| PrimaNota.jsx | frontend/src/pages/PrimaNota.jsx |
| Dashboard.jsx | frontend/src/pages/Dashboard.jsx |
| Corrispettivi.jsx | frontend/src/pages/Corrispettivi.jsx |
| styles.css | frontend/src/styles.css |

## Cosa è stato fixato

### ArchivioFattureRicevute (pagina fatture — screenshot 2)
- Su mobile: tabella sostituita con **card per ogni fattura** (fornitore, data, numero, totale, bottoni Vedi/Cassa/Banca)
- Su desktop: tabella originale mantenuta
- Rimossa la colonna azioni con minWidth:280 che causava overflow

### Fornitori (screenshot 1 - lista fornitori)
- Grid da `minmax(320px, 1fr)` → `1fr` su mobile (1 colonna)
- Padding pagina ridotto su mobile

### Riconciliazione
- Grid split da `minmax(300px)` → `1fr` su mobile
- overflowX aggiunto alle tabelle interne
- statsGrid con minmax ridotto

### HRCedolini
- Import useIsMobile aggiunto (mancava)
- overflowX wrapper su tutte le tabelle

### HRDipendenti
- overflowX wrapper sulla tabella dipendenti

### PrimaNota
- Grid KPI minmax ridotti
- minWidth aggiunto alla tabella principale

### Dashboard, Corrispettivi
- overflowX wrapper sulle tabelle
- minWidth grids ridotti

### styles.css (fix GLOBALE)
- CSS globale `@media (max-width: 768px)` aggiunto:
  - Tutte le tabelle con `min-width: 480px` (scrollabili)
  - Padding celle ridotto (8px invece di 12px)
  - Bottoni azioni compatti
  - Grid con minmax grandi forzate a 1 colonna

## Comandi dopo applicazione
```
cd frontend && npm run build
supervisorctl restart all
```
