# Ceraldi ERP — PRD

## Problema Originale
Applicazione ERP full-stack (React + FastAPI + MongoDB Atlas) per Ceraldi Caffè.
Aggiornamenti richiesti dall'utente tramite file CERALDI_MASTER_ZIP.zip e ISTRUZIONI_CORRETTE_V2.md.

## Regole Fondamentali
- **Design system**: solo CSS inline con le costanti di `lib/utils.js`. Vietati Shadcn e Tailwind per le pagine gestionale.
- **Lingua**: rispondere SEMPRE in italiano.
- **DB**: MongoDB Atlas (`azienda_erp_db`) via `MONGO_URL` dal backend `.env`.
- **Backend script**: NON eliminare `/app/backend/server.py` (punto di avvio Supervisor).

## Architettura
```
/app
├── app/
│   ├── main.py                         # Router registrations
│   ├── routers/
│   │   ├── cucina/                     # Ricette, FoodCost, ProdottiVendita, OrdiniFornitori
│   │   ├── invoices/corrispettivi.py   # Corrispettivi telematici
│   │   ├── prima_nota_module/          # Prima Nota (Cassa + Banca)
│   │   ├── suppliers_module/           # Anagrafica Fornitori
│   │   ├── fatture_module/             # Fatture Ricevute
│   │   └── ciclo_passivo_integrato.py  # Import XML → Magazzino → PN → Scadenziario
├── frontend/src/
│   ├── main.jsx                        # React Router routes
│   ├── lib/utils.js                    # Design system (COLORS, STYLES, button, badge, ecc.)
│   ├── pages/
│   │   ├── Dashboard.jsx               # Dashboard principale (no widget cucina)
│   │   ├── hub/FattureHub.jsx          # Hub fatture (ArchivioContent | CorrispettiviContent)
│   │   ├── Corrispettivi.jsx           # Pagina corrispettivi (stato vuoto se no dati)
│   │   ├── CicloPassivoAdmin.jsx       # Import XML/PEC + Fatture importate
│   │   ├── hub/CicloPassivoHub.jsx     # Redirect → /ciclo-passivo/import
│   │   ├── RicettarioAdmin.jsx         # Gestione ricette cucina
│   │   ├── FoodCostAdmin.jsx           # Gestione food cost
│   │   ├── CatalogoOrdini.jsx          # Catalogo ordini cucina
│   │   └── ProdottiVendita.jsx         # Prodotti vendita
│   └── components/layout/
│       ├── TopNav.jsx                  # Navigazione principale
│       └── SecondaryTabs.jsx           # Tab secondari per sezione (es. /fatture → 4 tab)
```

## Cosa è stato implementato

### Sessioni precedenti (completato)
- Eliminazione 34 file stub inutili dal backend
- Creazione router cucina: ricette.py, food_cost.py, prodotti_vendita.py, ordini_fornitori.py
- Creazione UI: RicettarioAdmin, FoodCostAdmin, CatalogoOrdini, ProdottiVendita
- Integrazione tab "Bozze" in OrdiniFornitori
- Fix Prima Nota: errore 422 "Sposta movimento", deduplicazione Banca, query Cassa
- Fix Anagrafica Fornitori: piva vs partita_iva, card "Senza nome", filtro fatture
- Popolamento automatico form Anagrafica da XML
- Rimozione sezione Riconciliazione Unificata, /fatture/import, /previsioni-acquisti

### Sessione corrente (completato)
- **Corrispettivi**: rimosso documento stub vuoto dal DB → pagina mostra correttamente stato vuoto
- **FattureHub.jsx**: rimossi tab colorati ridondanti (già fatto in sessione precedente, verificato)
- **SecondaryTabs**: aggiunto 4° tab "Import XML" (→ /ciclo-passivo/import) nella sezione Fatture
- **CicloPassivoHub.jsx**: ora redireziona correttamente a /ciclo-passivo/import
- **Widget Cucina Dashboard**: RIMOSSO (su richiesta utente — gestionale non include più tracciabilità/ricette)

## Backlog / Task futuri
- **P2**: Integrazione Email IMAP — bloccata per App Password Gmail non valida (ceraldigroupsr@gmail.com)
- **P3**: Auth backend con Cookies HTTP-Only
- **P3**: Verifica Portale.jsx (già controllato: non usa Shadcn/Tailwind → OK)

## Key API Endpoints
- `GET /api/corrispettivi?anno=YYYY` — lista corrispettivi
- `GET /api/fatture-ricevute/archivio` — archivio fatture ricevute
- `POST /api/ciclo-passivo/import-integrato` — import singolo XML
- `POST /api/ciclo-passivo/import-integrato-batch` — import batch XML
- `GET /api/cucina/ricette/stats` — statistiche ricette
- `GET /api/cucina/ordini-fornitori/bozze/count` — conteggio bozze ordini
- `POST /api/prima-nota/cassa` / `/banca` — movimenti prima nota
