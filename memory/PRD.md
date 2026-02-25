# Ceraldi ERP - Product Requirements Document

## Problem Statement
Full-stack Italian ERP application (React + FastAPI + MongoDB) for business management including invoicing, accounting, tax management, asset tracking, and financial reporting.

## Architecture
- **Frontend**: React (Vite), deployed on port 3000
- **Backend**: FastAPI, deployed on port 8001
- **Database**: MongoDB Atlas (azienda_erp_db)
- **Auth**: Disabled (no authentication required)

## Core Modules
1. Dashboard (fatture, bilancio, volume affari, imposte)
2. Fatture Ricevute (invoice management)
3. Cespiti (asset management with auto-XML scan)
4. Piano dei Conti (chart of accounts with real saldi)
5. Bilancio (balance sheet)
6. F24 (tax payments)
7. Corrispettivi (daily receipts)
8. Magazzino (warehouse)
9. Dipendenti/Veicoli (employees/vehicles)
10. Fisco/IVA (tax calculations)

## What's Been Implemented

### Session 1 (Previous)
- Critical accounting fixes (Bilancio, Veicoli)
- F24 data source correction (quietanze_f24)
- Invoice data enrichment (imponibile, IVA fields)
- Corrispettivi matricola fix
- Magazzino module overhaul + maintenance products
- Auto-refresh removal across all pages
- Invoice view improvements
- "Mark as Paid" button
- Dashboard POS calendar removal
- Page crash fixes (Strumenti, Integrazioni)

### Session 2 (Current - Feb 25, 2026)
- **Fatture table headers**: Fixed white text to dark text (#1e293b) on light background (#f1f5f9)
- **Cespiti auto-scan**: Created POST /api/cespiti/scan-fatture endpoint that extracts 21 assets from dettaglio_righe_fatture (€60,124.58 total). Added "Scan Fatture XML" button to frontend.
- **Volume Affari fix**: Fixed backend field names (importo_totale vs totale_fattura, corrispettivi data field vs anno). Now shows Fatturato €71,953.90 + Corrispettivi €31,395.51 = €103,349.41.
- **Bilancio Istantaneo fix**: Fixed invoice query to use `anno` field instead of `data_ricezione` regex. Corrispettivi count now shows 14 (was 0).
- **Contabilità Hub**: Updated Piano dei Conti to compute real saldi from invoices and corrispettivi data (Attivo €2.67M, Passivo €314K, Ricavi €2.43M).
- **React key fix**: Fixed duplicate key warning in fatture table.

## Pending/Known Issues
- P1: Imposte page - user reported "mancano calcoli" (needs clarification)
- P2: Dead code removal (old sidebar, unused components)
- P2: E2E test coverage improvement

## Key API Endpoints
- GET /api/fatture-ricevute/archivio/{anno}
- GET /api/gestione-riservata/volume-affari-reale?anno=2026
- GET /api/dashboard/bilancio-istantaneo?anno=2026
- GET /api/cespiti/?attivi=true
- POST /api/cespiti/scan-fatture?soglia_valore=200&dry_run=false
- GET /api/piano-conti/
- GET /api/piano-conti/bilancio
- GET /api/contabilita/calcolo-imposte?regione=campania&anno=2026

## Key Database Collections
- invoices: 74 documents (fields: anno, importo_totale, importo_imponibile, importo_iva)
- corrispettivi: 1051 documents (fields: data string "YYYY-MM-DD", totale)
- cespiti: 21 documents (auto-populated from dettaglio_righe_fatture)
- dettaglio_righe_fatture: 11,192 documents (invoice line items from XML)
- piano_conti: chart of accounts
- quietanze_f24: F24 tax payment receipts
