# Ceraldi ERP - Product Requirements Document

## Descrizione
Applicazione ERP full-stack italiana (React + FastAPI + MongoDB) per gestione aziendale: fatturazione, contabilità, gestione fiscale, cespiti, e reportistica finanziaria.

## Architettura
- **Frontend**: React (Vite), porta 3000
- **Backend**: FastAPI, porta 8001
- **Database**: MongoDB Atlas (azienda_erp_db)
- **Auth**: Disabilitata

## Moduli principali
1. Dashboard (fatture, bilancio, volume affari, imposte)
2. Fatture Ricevute (gestione fatture)
3. Cespiti (gestione beni ammortizzabili con scan XML automatico)
4. Piano dei Conti (con saldi calcolati in tempo reale)
5. Bilancio (stato patrimoniale)
6. Prima Nota (cassa e banca)
7. F24 (pagamenti fiscali)
8. Corrispettivi (incassi giornalieri)
9. Magazzino (inventario)
10. Dipendenti/Presenze (HR, presenze, cedolini, ferie)
11. Fisco/IVA (calcoli fiscali)

## Logica aziendale chiave
- **Volume Affari** = SOLO corrispettivi (le fatture emesse sono GIA incluse nei corrispettivi come scontrini)
- **Fatture ricevute** (collezione invoices) = COSTI/ACQUISTI, NON ricavi
- **Cespiti** estratti automaticamente da dettaglio_righe_fatture con classificazione keyword

## Sessione 1 (Precedente)
- Fix contabilità critica (Bilancio, Veicoli)
- Correzione sorgente dati F24 (quietanze_f24)
- Arricchimento dati fatture (imponibile, IVA)
- Fix matricola corrispettivi
- Ristrutturazione modulo Magazzino + prodotti manutenzione
- Rimozione auto-refresh (Dashboard, Documenti)
- Miglioramenti vista fattura, pulsante "Segna come Pagata"
- Rimozione calendario POS, fix crash pagine

## Sessione 2 (25 Feb 2026)
- Fix intestazioni tabella fatture (testo scuro su sfondo chiaro)
- Auto-scan cespiti: POST /api/cespiti/scan-fatture (21 beni, €60.124,58)
- Volume Affari CORRETTO: fatturato = solo corrispettivi (€31.395,51)
- Bilancio Istantaneo: query fatture con campo anno, conteggio corrispettivi corretto
- Contabilità Hub: Piano dei Conti con saldi reali
- Prima Nota Cassa: fix mismatch tipo data (datetime vs string)
- Dipendenti/Presenze: 34 dipendenti reali dalla collezione dipendenti

## Sessione 3 (25 Feb 2026 - Corrente)
- **Route /attendance → /presenze**: Rinominata URL, aggiornati tutti i link
- **Dipendente duplicato unificato**: Orosco/Orozco Posligua → unico record con CF
- **Toggle "In carico"**: Aggiunto pulsante cliccabile nella tabella Anagrafica
- **Cedolini con dati reali**: PagheHub ora carica da /api/cedolini (14 buste per 2026)
- **Ferie - Elimina e Modifica**: Aggiunti pulsanti "Elimina richiesta" e "Modifica periodo"
- **Auto-refresh eliminato completamente**: useData.js refetchInterval, NotificheScadenze
- **Pulizia componenti**: Rimossi 20 file inutilizzati
- **Fix db["employees"] → db["dipendenti"]**: Corretto in tutti i router

## Endpoint API chiave
- GET /api/gestione-riservata/volume-affari-reale?anno=2026
- GET /api/dashboard/bilancio-istantaneo?anno=2026
- GET /api/prima-nota/cassa?anno=2026 → 5 movimenti
- GET /api/employees?limit=200 → 34 dipendenti reali
- GET /api/cedolini?anno=2026 → 14 cedolini
- GET /api/cespiti/?attivi=true → 21 cespiti
- POST /api/cespiti/scan-fatture → scan fatture XML
- DELETE /api/giustificativi/saldi-finali/{id}?anno=2026
- PUT /api/giustificativi/saldi-finali/{id}/periodo

## Collezioni DB chiave
- invoices: 74 (fatture RICEVUTE = COSTI)
- corrispettivi: 1051 (RICAVI)
- cespiti: 21 (auto-popolati)
- prima_nota_cassa: 5 (data: datetime, anno: int)
- dipendenti: 34 (dipendenti reali)
- presenze: 20957 (registri presenze)
- cedolini: 841 (buste paga, 14 per 2026)

## Problemi in sospeso
- P1: Pagina Imposte - "mancano calcoli" (necessita chiarimento)
- P2: Migliorare copertura test E2E
