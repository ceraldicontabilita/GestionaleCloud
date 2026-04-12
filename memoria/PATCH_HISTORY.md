# Storico Patch Applicate — Ceraldi ERP
> Patch della Chat 8 — Aprile 2026 | File originali in `claude-patches/` (ora archiviati)

---

## PATCH 1 — Fix Reload Continuo + Router Duplicati

**Cartella originale**: `claude-patches/chat-8-fix-reload-e-duplicati/`
**File modificati**: `frontend/src/main.jsx`, `app/main.py`
**Stato**: APPLICATA ✅

### Bug critico risolto: Loop reload infinito

**Causa**: `LearningMachine` usata nelle route React (righe 191-192 di `main.jsx`) ma non importata con `lazy()`. Generava `ReferenceError` a runtime → React Router rimontava tutto → loop infinito.

**Fix applicato** (`main.jsx`):
```js
// Aggiunta questa riga subito dopo l'import di TracciabilitaPage:
const LearningMachine = lazy(() => import("./pages/LearningMachine.jsx"));
```

### Bug medio risolto: Router duplicati in main.py

**Causa 1**: `settings_router` registrato due volte:
- Riga rimossa: `app.include_router(settings_router.router, prefix="/api", ...)`
- Riga mantenuta: `app.include_router(settings_router.router, prefix="/api/settings", ...)`

**Causa 2**: Router Tracciabilità registrati due volte:
- Primo blocco `# --- Tracciabilita HACCP ---` (22 router) → RIMOSSO
- Secondo blocco `_TR_ROUTERS` (43 router, più completo) → MANTENUTO

---

## PATCH 2 — Responsive Fix su Tutte le Pagine

**Cartella originale**: `claude-patches/chat-8-responsive-fix/`
**File modificati**: 9 file JSX + `styles.css`
**Stato**: APPLICATA ✅

### Pagine adattate

**ArchivioFattureRicevute.jsx**
- Mobile: tabella sostituita con card per ogni fattura (fornitore, data, numero, totale, bottoni Vedi/Cassa/Banca)
- Desktop: tabella originale mantenuta
- Rimossa colonna azioni con `minWidth: 280` che causava overflow

**Fornitori.jsx**
- Grid da `minmax(320px, 1fr)` → `1fr` su mobile (1 colonna)
- Padding ridotto su mobile

**Riconciliazione.jsx**
- Grid split da `minmax(300px)` → `1fr` su mobile
- `overflowX` aggiunto alle tabelle interne

**HRCedolini.jsx**
- `import useIsMobile` aggiunto (mancava)
- `overflowX` wrapper su tutte le tabelle

**HRDipendenti.jsx**
- `overflowX` wrapper sulla tabella dipendenti

**PrimaNota.jsx**
- Grid KPI `minmax` ridotti
- `minWidth` aggiunto alla tabella principale

**Dashboard.jsx, Corrispettivi.jsx**
- `overflowX` wrapper sulle tabelle

**styles.css — Fix globale mobile**
```css
@media (max-width: 768px) {
  table { min-width: 480px; }    /* tabelle scrollabili */
  td, th { padding: 8px; }       /* padding celle ridotto */
  /* Grid con minmax grandi forzate a 1 colonna */
}
```

---

## PATCH 3 — Mittenti Attendibili + Scheduler 50 Minuti

**Cartella originale**: `claude-patches/chat8-mittenti-scheduler/`
**File modificati**: `app/services/email_monitor_service.py`, `app/scheduler.py`
**Stato**: APPLICATA ✅

### Scheduler: da 10 minuti → 50 minuti

**File**: `app/services/email_monitor_service.py`

```python
# Prima:
async def monitor_loop(db, interval_seconds: int = 600):

# Dopo:
async def monitor_loop(db, interval_seconds: int = 3000):
```

### Mittenti whitelistati

Aggiunto script `seed_mittenti.py` per popolare `mittenti_email` nel DB con tutti i pattern autorizzati (Gmail + PEC):

**Gmail**: commercialista Marotta/Ferrantini (cedolini), INPS, INAIL, Agenzia Entrate/Riscossione, PagoPA, PayPal, società noleggio (Leasys, ALD, Arval), banche (BNL, BancoBPM, Nexi), Aruba (notifica nuova fattura).

**PEC**: SDI (sistema interscambio fatture), commercialisti via PEC, INPS PEC, AdE PEC, PagoPA PEC.

**Regola match**: `if pattern in from_addr.lower()` — contenimento stringa, case-insensitive.

**Mittenti esclusi intenzionalmente**: fornitori generici (le fatture arrivano via SDI, non direttamente), ABC Napoli, TIM.

---

## PATCH 4 — Tracciabilità: Rimozione iframe, Bottone Esterno + Sync Panel

**Cartella originale**: `claude-patches/chat8-tracciabilita/`
**File modificati**: `frontend/src/pages/TracciabilitaPage.jsx`
**Stato**: APPLICATA ✅

### Cambiamento

**Prima**: iframe che puntava a `/api/tracciabilita/` (mini-sito HACCP embedded)

**Dopo**: pagina semplice con:
- Bottone "Apri ceraldiapp.it" (nuova scheda)
- 4 stat card con stato sincronizzazione DB in tempo reale:
  - Ponte ERP: stato connessione
  - Produzioni oggi
  - Stato DB
  - Ultimo aggiornamento

**API usate** (già esistenti, nessuna modifica backend):
- `GET /api/erp/ponte/status` → connessione ponte + count fatture sync
- `GET /api/tr/produzioni/per-oggi` → produzioni odierne da ceraldiapp.it

**File NON modificati**: `app/main.py` (router tracciabilità rimane), `app/routers/erp_bridge.py` (ponte rimane), `frontend/src/main.jsx` (route rimane).

---

*Patch documentate: Aprile 2026*
