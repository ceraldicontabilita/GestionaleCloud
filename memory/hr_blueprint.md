# MEMORIA SEZIONE HR - Prima della cancellazione
# Data: Aprile 2026
# File originale: GestioneDipendentiUnificata.jsx (2183 righe — CANCELLATO)

## STRUTTURA ROUTE (main.jsx)
- /dipendenti → GestioneDipendentiUnificata (CANCELLATA)
- /dipendenti/:tab → stessa pagina
- /presenze → DipendentiHub (presenze per dipendente)
- /cedolini → PagheHub (buste paga + F24 globali)
- /tfr → redirect a /dipendenti/tfr (ORA: si ricreerà /tfr diretto)

## SECONDARY TABS HR
- "Dipendenti" → /dipendenti
- "Cedolini" → /cedolini
- "Presenze" → /presenze
- "TFR" → /tfr

## API BACKEND USATE (tutte funzionanti ✓)
- GET  /api/dipendenti                          → lista dipendenti (34 doc, collection "dipendenti")
- GET  /api/dipendenti/{id}                     → singolo dipendente
- PUT  /api/dipendenti/{id}                     → salva anagrafica
- GET  /api/dipendenti/contratti?dipendente_id=  → contratti dipendente
- GET  /api/cedolini/dipendente/{id}?anno=       → cedolini per dipendente (FIX: usa collection "dipendenti")
- GET  /api/archivio-bonifici/transfers?beneficiario=  → bonifici per nome
- GET  /api/tfr/acconti/{id}                    → acconti TFR dipendente
- POST /api/tfr/acconti                          → nuovo acconto TFR
- PUT  /api/tfr/acconti/{id}                    → modifica acconto TFR
- DELETE /api/tfr/acconti/{id}                  → cancella acconto TFR
- GET  /api/giustificativi/dipendente/{id}/giustificativi → giustificativi dipendente
- GET  /api/giustificativi/dipendente/{id}/saldo-ferie    → saldo ferie
- GET  /api/attendance/richieste-pending         → richieste assenza in attesa
- PUT  /api/attendance/richiesta-assenza/{id}/approva   → approva richiesta
- PUT  /api/attendance/richiesta-assenza/{id}/rifiuta   → rifiuta richiesta
- POST /api/attendance/set-presenza              → inserisce presenza batch
- GET  /api/attendance/ore-lavorate/{id}?mese=&anno= → storico ore (funziona con ID)
- GET  /api/paghe/buste-paga?anno=               → buste paga globali (→ in /cedolini)
- GET  /api/paghe/distinte-f24?anno=             → distinte F24 (→ in /cedolini)
- GET  /api/noleggio/veicoli                    → lista veicoli (→ /veicoli/noleggio)
- POST /api/noleggio/veicoli                    → nuovo veicolo
- GET  /api/employees?limit=200                 → vecchia collection (31 doc) — usata in Presenze Batch, OK solo per presenze

## CAMPI DIPENDENTE (collection "dipendenti")
- id (UUID), nome, cognome, codice_fiscale, email, telefono
- mansione, livello, tipo_contratto, data_assunzione
- iban, banca, importo_mensile, importo_netto

## STRUTTURA DATI CEDOLINI (collection "cedolini")
- dipendente_id (UUID corrisponde a "dipendenti.id")
- dipendente_nome, anno (int o str), mese (int o str)
- lordo, netto, contributi, f24, pdf_url

## FUNZIONALITÀ DA REPLICARE NEL NUOVO DESIGN
1. Lista dipendenti (sidebar) con ricerca
2. Selezione dipendente → vista dettaglio con TAB:
   a. Anagrafica: nome, CF, mansione, contratto, IBAN — con bottone Modifica/Salva
   b. Contratti: lista contratti con date e importi
   c. Retribuzione: cedolini per anno (con selettore anno 2023/2024/2025/2026)
   d. Movimenti: bonifici + acconti TFR
   e. Giustificativi: permessi, ferie, malattie con saldo ferie
3. Vista team (SENZA tab separati - link ai propri hub):
   - Batch Presenze: griglia tutti i dipendenti × giorni del mese
   - Turni: gestione turni per mansione
   - Richieste pending: approva/rifiuta con badge contatore

## NOTE CRITICHE PER LA RICREAZIONE
- Collection corretta: "dipendenti" (non "employees")
- Design: SOLO CSS inline da lib/utils.js (COLORS, STYLES, SPACING) — NO Tailwind, NO Shadcn
- NO icone emoji nel codice
- Icone: lucide-react ONLY
- Nessun tab che duplica le SecondaryTabs (Cedolini, Presenze, TFR già hanno propri hub)
- Il selettore anno nella Retribuzione è necessario (anni cedolini: 2019-2026)
- Batch Presenze usa collection "employees" per i turni/presenze (31 doc) — normale
