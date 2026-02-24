# Ceraldi ERP - Product Requirements Document

## Overview
Sistema ERP completo per la gestione aziendale di Ceraldi Caffè, clonato dal repository OpenClaw-3.0 e personalizzato secondo le specifiche del cliente.

## Problem Statement
L'utente ha richiesto di ricreare un sistema ERP con:
1. Layout con navigazione in alto (TOP-NAV) invece della sidebar
2. Connessione a MongoDB Atlas con dati reali
3. Nessuna autenticazione (da reimplementare al deployment)
4. UI compatta per ridurre lo scrolling

## Tech Stack
- **Frontend**: React 18 + Vite + TailwindCSS
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB Atlas (azienda_erp_db)
- **Process Manager**: Supervisor

## Core Features

### ✅ Implemented (Feb 24, 2026)

#### 1. Top Navigation Layout (P0 - COMPLETED)
- Navigazione primaria in alto (#daeafc, 54px)
- Tab secondari contestuali (#edf4fd, 42px)
- Dropdown menus per gruppi: Fatture, Banca, Fisco, HR, Altro
- Mobile bottom navigation per schermi < 768px
- Brand "CG Ceraldi ERP" con logo
- Anno selector integrato (2026)

#### 2. Database Integration (COMPLETED)
- Connessione a MongoDB Atlas funzionante
- 316+ fornitori
- 3000+ fatture
- 2000+ cedolini
- 120+ F24
- 1051 corrispettivi

#### 3. Moduli Funzionanti
- Dashboard operativa
- Gestione Fornitori (316 records)
- HR/Dipendenti (anagrafica, cedolini, presenze, TFR)
- Ciclo Passivo (fatture ricevute)
- Prima Nota (cassa e banca)
- Riconciliazione bancaria
- F24 e tributi
- Bilancio
- Magazzino
- Scadenze

### ✅ Completed (Additional - Feb 24, 2026)

#### Filtro Anno Verificato
- Tutti i moduli principali usano correttamente `useAnnoGlobale()`
- Pagine verificate: Fatture, Cedolini, F24, Presenze, Prima Nota
- Il selector anno (2026) nella top-nav aggiorna tutte le pagine
- I fornitori e dipendenti non filtrano per anno (entità permanenti)

#### API Routing Verificato
- Frontend usa correttamente `/api/suppliers` (inglese)
- Nessun alias temporaneo trovato nel backend
- Routing consistente tra frontend e backend

### 📋 Backlog

#### P2 - Future

#### P2 - Future
- Re-implementazione autenticazione (richiesta al deployment)
- Testing E2E completo di tutti i moduli
- Ottimizzazione performance query MongoDB

## Architecture

```
/app
├── backend/           # FastAPI server (port 8001)
│   ├── app/
│   │   ├── main.py    # Entrypoint
│   │   ├── routers/   # API endpoints
│   │   └── database/  # MongoDB collections
│   └── .env           # MONGO_URL, DB_NAME
│
└── frontend/          # React + Vite (port 3000)
    ├── src/
    │   ├── App.jsx    # Main layout (TopNav)
    │   ├── components/
    │   │   └── layout/
    │   │       ├── TopNav.jsx
    │   │       └── SecondaryTabs.jsx
    │   ├── pages/     # Page components
    │   └── styles/
    │       └── topnav.css
    └── .env           # REACT_APP_BACKEND_URL
```

## API Routes
- `/api/suppliers` - Fornitori
- `/api/hr/employees` - Dipendenti
- `/api/invoices` - Fatture
- `/api/f24` - F24 e tributi
- `/api/health` - Health check

## Design System
Based on `layout-A-topnav.html`:
- Primary: #1a40b5
- Primary Light: #daeafc
- Secondary: #b3d2f5
- Text: #0d1829
- Text Muted: #7a9ab8
- Success: #16a34a
- Warning: #d97706
- Error: #dc2626

## Testing
- Backend: 100% pass rate
- Frontend: 100% pass rate
- Test reports: `/app/test_reports/iteration_1.json`
- Filtro anno: Verificato su tutte le pagine principali
- API routing: Verificato consistente

## Known Issues
- Chat toggle può sovrapporsi al menu mobile (LOW priority)

## Changelog
- **2026-02-24**: Implementato layout top-navigation
- **2026-02-24**: Rimosso layout sidebar
- **2026-02-24**: Test E2E completati con successo
- **2026-02-24**: Verificato filtro anno su tutti i moduli
- **2026-02-24**: Verificato API routing consistente
- **2026-02-24**: Fix filtro anno in fatture-ricevute (aggiunto supporto campo `anno` e `data_fattura`)
- **2026-02-24**: Rimossi titoli duplicati nelle pagine (Ciclo Passivo, Prima Nota, Gestione Assegni)
- **2026-02-24**: Rimossi menu collassabili da SectionPage
- **2026-02-24**: Rimossi tab duplicati dai file Hub
- **2026-02-24**: TopNav refactoring: link diretti (no dropdown tranne Altro)
- **2026-02-24**: Anno selector con etichetta "ANNO"
- **2026-02-24**: Test E2E iteration_2: 100% backend, 100% frontend
