# Patch Chat 7 — Riconciliazione Stipendi

## File contenuti

| File patch | Destinazione reale |
|---|---|
| `estratto_conto.py` | `app/routers/estratto_conto.py` |
| `EstrattoConto.jsx` | `frontend/src/pages/EstrattoConto.jsx` |

## Cosa cambia

### `estratto_conto.py`
- **Aggiunto** `GET /api/estratto-conto/stipendi` — lista movimenti con categoria
  `bonifico_uscita` o `stipendio`, arricchiti con dati cedolino se già riconciliati.
  Parametri: `anno`, `mese`, `riconciliato`.
- **Aggiunto** `POST /api/estratto-conto/riconcilia-stipendi` — riconcilia movimenti
  stipendio con cedolini tramite doppia strategia (match per nome dipendente estratto
  dalla descrizione + match per importo univoco nel mese). Ritorna lista `non_trovati`.
- **Costante** `CATEGORIE_STIPENDIO = {"bonifico_uscita", "stipendio"}` — fix del bug
  principale: il parser classifica i bonifici come `bonifico_uscita` ma il vecchio
  endpoint `/riconcilia` cercava solo categoria `stipendio` → zero match.
- Endpoint esistenti invariati.

### `EstrattoConto.jsx`
Pagina completamente riscritta. Da `UploadPage` generico a pagina con 3 tab:
- **Tab Saldo** — 3 KPI: saldo netto, entrate, uscite
- **Tab Stipendi** — 4 KPI + tabella movimenti stipendio con stato riconciliazione,
  pulsante "Riconcilia ora" con risultato inline, dettaglio espandibile per riga
- **Tab Movimenti** — tabella completa con filtri categoria/data/riconciliato + upload PDF

## Come applicare
1. Copia `estratto_conto.py` → `app/routers/estratto_conto.py`
2. Copia `EstrattoConto.jsx` → `frontend/src/pages/EstrattoConto.jsx`
3. Riavvia backend (supervisor restart backend)
4. Riavvia frontend se necessario

## Dipendenze
Nessuna nuova dipendenza. Usa collezioni esistenti: `estratto_conto_movimenti`,
`cedolini`, `dipendenti`.
