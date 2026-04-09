# Patch Chat 7 — TODO residui (Temperature rinomina + Tablet Cucina)

## File contenuti

| File patch | Destinazione reale |
|---|---|
| `TemperatureHACCP.jsx` | `frontend/src/pages/TemperatureHACCP.jsx` |
| `TabletCucina.jsx` | `frontend/src/pages/TabletCucina.jsx` (NUOVO) |
| `App.jsx` | `frontend/src/App.jsx` |
| `TopNav.jsx` | `frontend/src/components/TopNav.jsx` |

## Cosa cambia

### TemperatureHACCP.jsx — Rinomina inline colonne
- Ogni intestazione colonna (frigo/congelatore) è ora cliccabile
- Click → campo input inline con conferma (Enter/✓) o annulla (Esc/✗)
- Il nuovo nome viene:
  1. Aggiornato immediatamente nell'UI
  2. Salvato in `localStorage` (`nomi_temperature-positive` / `nomi_temperature-negative`)
  3. Inviato via `PATCH /api/temperature-positive|negative/scheda/{anno}/{n}` a ceraldiapp.it
     (se l'API non supporta PATCH, rimane comunque in localStorage)
- Toast di conferma "✓ salvato" per 2.5 secondi
- Hint testuale sotto i filtri: "Clicca intestazione colonna per rinominare"

### TabletCucina.jsx — NUOVA PAGINA
- Route: `/tablet-cucina`
- 2 tab: Rosticceria e Pasticceria
- Chiama `GET https://ceraldiapp.it/api/tablet/{reparto}` per ciascun reparto
- Mostra: KPI (lotti attivi, produzioni oggi, operatori, pezzi), operatori in turno,
  tabella lotti attivi (con alert scadenza ≤3gg), tabella produzioni di oggi
- Auto-refresh ogni 60 secondi
- Pulsante "Apri Tablet" → apre ceraldiapp.it/#tablet/{reparto} in nuova finestra
- Gestisce errori di rete con messaggio chiaro + pulsante Riprova

### App.jsx
- Aggiunto import `TabletCucina`
- Aggiunta route `<Route path="/tablet-cucina" element={<TabletCucina />} />`

### TopNav.jsx
- Aggiunto link `📱 Tablet` → `/tablet-cucina` (icona `Tablet` da lucide-react)
- Fix: aggiunti import `ShoppingBag`, `Tag`, `Tablet` (mancavano nel TopNav originale)

## Come applicare
1. Copia `TemperatureHACCP.jsx` → `frontend/src/pages/TemperatureHACCP.jsx`
2. Copia `TabletCucina.jsx` → `frontend/src/pages/TabletCucina.jsx` (file nuovo)
3. Copia `App.jsx` → `frontend/src/App.jsx`
4. Copia `TopNav.jsx` → `frontend/src/components/TopNav.jsx`
5. Riavvia frontend

## Note
- Nessuna modifica al backend gestionale2
- Nessuna nuova dipendenza npm
- La rinomina usa localStorage come fallback se ceraldiapp.it non espone PATCH
- TabletCucina gestisce in modo robusto strutture JSON diverse da ceraldiapp.it
  (controlla campi alternativi: lotti/lotti_attivi, produzione_oggi/produzioni, ecc.)
