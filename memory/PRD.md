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
6. Prima Nota (cash and bank ledger)
7. F24 (tax payments)
8. Corrispettivi (daily receipts)
9. Magazzino (warehouse)
10. Dipendenti/Presenze (HR, attendance, payslips)
11. Fisco/IVA (tax calculations)

## What's Been Implemented

### Session 1 (Previous)
- Critical accounting fixes (Bilancio, Veicoli)
- F24 data source correction (quietanze_f24)
- Invoice data enrichment (imponibile, IVA fields)
- Corrispettivi matricola fix
- Magazzino module overhaul + maintenance products
- Auto-refresh removal across pages (Dashboard, Documenti)
- Invoice view improvements, "Mark as Paid" button
- Dashboard POS calendar removal
- Page crash fixes (Strumenti, Integrazioni)

### Session 2 (Feb 25, 2026)
- **Fatture table headers**: Fixed white text to dark (#1e293b on #f1f5f9)
- **Cespiti auto-scan**: POST /api/cespiti/scan-fatture - extracts 21 assets (€60,124.58)
- **Volume Affari CORRECTED**: fatturato = corrispettivi only (€31,395.51). Fatture ricevute are COSTS, not revenue. Fatture emesse already in corrispettivi.
- **Bilancio Istantaneo**: Fixed invoice query to use anno field. Corrispettivi count fixed.
- **Contabilità Hub**: Piano dei Conti computes real saldi from invoices/corrispettivi
- **Prima Nota Cassa**: Fixed datetime vs string date type mismatch - now uses anno field
- **Dipendenti/Presenze**: Fixed to load 35 real employees from dipendenti collection
- **Auto-refresh FULLY removed**: useData.js refetchInterval, NotificheScadenze 30-min interval
- **Component cleanup**: Removed 20 unused components/pages

## Key Business Logic
- **Volume Affari** = corrispettivi ONLY (fatture emesse are included in corrispettivi as scontrini)
- **Fatture ricevute** (invoices collection) = COSTS/PURCHASES, not revenue
- **Cespiti** auto-extracted from dettaglio_righe_fatture using keyword classification

## Key API Endpoints
- GET /api/gestione-riservata/volume-affari-reale?anno=2026 → fatturato=corrispettivi
- GET /api/dashboard/bilancio-istantaneo?anno=2026 → ricavi/costi/iva
- GET /api/prima-nota/cassa?anno=2026 → cash movements (5 records)
- GET /api/prima-nota/banca?anno=2026 → bank movements (161 records)
- GET /api/employees?limit=200 → 35 real employees from dipendenti collection
- GET /api/cespiti/?attivi=true → 21 auto-extracted assets
- POST /api/cespiti/scan-fatture → scan XML invoices for assets
- GET /api/piano-conti/ → chart of accounts with computed saldi
- GET /api/piano-conti/bilancio → full balance sheet

## Key Database Collections
- invoices: 74 docs (fatture RICEVUTE = COSTS, fields: anno, importo_totale, importo_imponibile, importo_iva)
- corrispettivi: 1051 docs (REVENUE, fields: data string "YYYY-MM-DD", totale)
- cespiti: 21 docs (auto-populated from dettaglio_righe_fatture)
- prima_nota_cassa: 5 docs (fields: data datetime, anno int, tipo, importo)
- prima_nota_banca: 1581 docs
- estratto_conto_movimenti: 4261 docs
- dipendenti: 35 docs (employees)
- presenze: 20957 docs (attendance records)
- cedolini: payslips
- dettaglio_righe_fatture: 11192 docs (invoice line items from XML)

## Pending Issues
- P1: Imposte page - user reported "mancano calcoli" (needs clarification)
- P2: Improve E2E test coverage

## Collections Mapping
- Collections.EMPLOYEES = "dipendenti" (changed from "employees")
