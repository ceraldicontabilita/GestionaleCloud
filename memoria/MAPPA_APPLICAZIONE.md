# CERALDI ERP — MAPPA APPLICAZIONE COMPLETA
## Aggiornata: 22 Aprile 2026 — Audit completo: Body(21), Modali(7), Router(2)

## ARCHITETTURA

**Stack**: FastAPI (Python) + Motor (async MongoDB) + React 18 + Vite
**DB**: MongoDB Atlas, cluster `cluster0.vofh7iz`, database `Gestionale`
**Repo**: github.com/ceraldicontabilita/gestionale2
**Deploy**: app.emergent.sh → impresasemplice.online
**Design system**: Navy #0f2744 + Oro #b8860b (definito in frontend/src/lib/utils.js)

## FLUSSO DATI PRINCIPALE

```
Email Aruba PEC → Download fatture XML/P7M → Parser XML → Collezione "invoices"
                                                        → Auto-routing cassa/banca
                                                        → Aggiornamento fornitore

Estratto Conto XLS → Parser → Collezione "estratto_conto_movimenti"
                            → Riconciliazione automatica con fatture

Corrispettivi XML → Parser → Collezione "corrispettivi"
                           → Auto-split contanti→cassa + POS→banca

Cedolini PDF → Parser Zucchetti → Collezione "cedolini"
                                → Collegamento dipendente
```

## COLLEZIONI MONGODB PRINCIPALI

| Collezione | Descrizione |
|---|---|
| `invoices` | Fatture ricevute (XML importate) |
| `suppliers` | Fornitori (anagrafiche) |
| `prima_nota_cassa` | Movimenti cassa |
| `prima_nota_banca` | Movimenti banca (manuali) |
| `estratto_conto_movimenti` | Movimenti estratto conto bancario |
| `corrispettivi` | Corrispettivi giornalieri |
| `cedolini` | Cedolini paga dipendenti |
| `dipendenti` | Anagrafica dipendenti |
| `presenze_giornaliere` | Presenze giornaliere |
| `f24_documenti` | Documenti F24 |
| `scadenziario` | Scadenze pagamenti |
| `assegni` | Gestione assegni |
| `cespiti` | Cespiti aziendali |
| `todo` | Task da fare |
| `partite_aperte` | Partite aperte (materializzate) |
| `alerts` | Alert sistema relazionale |
| `riconciliazioni_match` | Match riconciliazione |
| `audit_log` | Log audit |

## PAGINE E FUNZIONALITÀ

### 1. DASHBOARD (DashboardHub → Dashboard.jsx, 1916 righe)
**URL**: / o /dashboard
**Mostra**: KPI principali (ricavi, costi, IVA, utile), prossime scadenze, bilancio istantaneo
**Bottoni critici**:
- "Paga" nelle scadenze → apre modale → POST /api/fatture-ricevute/paga-manuale
  - BUG FIXATO: importo era €0,00 (campo non parsato come float)
  - BUG FIXATO: modale senza overlay click-to-close
- "Ricostruisci dati" → POST /api/fatture-ricevute/auto-ricostruisci-dati
- "Auto-riconcilia" → POST /api/batch/auto-riconcilia-tutto
**Endpoint GET**:
- /api/dashboard/bilancio-istantaneo?anno=X
- /api/scadenze/prossime?giorni=30&limit=8
- /api/email-download/statistiche
- /api/paghe/buste-paga?stato=DA_PAGARE
- /api/paghe/distinte-f24?stato=DA_PAGARE

### 2. FATTURE (FattureHub → include ArchivioFattureRicevute, Corrispettivi, IVA, ImportDocumenti)
**URL**: /fatture, /fatture/corrispettivi, /fatture/iva, /fatture/import

#### 2a. Archivio Fatture Ricevute (476 righe)
**Mostra**: lista fatture per fornitore, filtri
**Bottoni**: Paga manuale → POST /api/fatture-ricevute/paga-manuale

#### 2b. Corrispettivi (355 righe)
**Mostra**: corrispettivi giornalieri con split contanti/POS
**Bottoni**: Elimina → DELETE /api/corrispettivi/{id}
  - BUG FIXATO: mancava window.confirm

#### 2c. IVA (286 righe)
**Mostra**: confronto IVA mensile con saldo progressivo anno
**Colonne**: Mese, IVA Debito, N.Corr, IVA Credito, N.Fatt, Saldo Mese, Riporto, Saldo Anno, Stato
**BUG FIXATO**: saldo progressivo anno con riporto credito/debito mese precedente
**Bottoni**: Export PDF trimestrale, Export PDF annuale

#### 2d. Import Documenti (701 righe)
**Upload**: drag-and-drop multi-file
**Bottoni**: Upload Auto → POST /api/documenti/upload-auto
  - Classifica automatica: fattura XML, corrispettivo, F24, CU, generico
  - BUG FIXATO: file .p7m non venivano riconosciuti

### 3. FORNITORI (FornitoriHub → Fornitori.jsx, 2450 righe)
**URL**: /fornitori
**Mostra**: lista fornitori con avatar, P.IVA, fatture count, totale, metodo pagamento
**Bottoni critici**:
- Click fornitore → apre dettaglio con tab
- "Estratto Fatture" → modale con tabella fatture
  - Colonne: Data, Numero, Imponibile, IVA, Importo, Metodo, Stato, AZIONI
  - BUG FIXATO: Imponibile e IVA erano €0,00 (campi non restituiti dal backend)
  - BUG FIXATO: bottoni Cassa/Banca davano errore 502 (Body mancante)
  - BUG FIXATO: modale non si chiudeva (mancava overlay click + stopPropagation)
- "Nuovo Fornitore" → POST /api/suppliers
- "Aggiorna OpenAPI" → POST /api/openapi-imprese/aggiorna-bulk
- "Backfill Autoroute" → POST /api/fatture-ricevute/backfill-autoroute
- "Schede Tecniche" → POST /api/schede-tecniche/cerca

### 4. PRIMA NOTA (PrimaNotaHub → PrimaNota.jsx, 1781 righe)
**URL**: /prima-nota, /prima-nota/cassa, /prima-nota/banca
**Mostra**: movimenti cassa e banca con saldo progressivo per riga
**KPI Cassa**: Entrate, Uscite, Saldo Cassa anno (BUG FIXATO: rimosso Saldo Cumulativo -485K)
**KPI Banca**: Entrate, Uscite, Saldo Anno, Riporto Anni Prec., Saldo Cumulativo
**Bottoni**:
- Nuovo movimento → POST /api/prima-nota/cassa o /api/prima-nota/banca
- Sposta cassa↔banca → POST /api/prima-nota/sposta-movimento
- Conferma provvisori → POST /api/prima-nota/provvisori/conferma
- Import estratto conto → POST /api/estratto-conto-movimenti/import
- Elimina → DELETE con conferma
- Registra pagamento → POST /api/pagamenti/registra

### 5. DIPENDENTI (HRDipendenti.jsx, 925 righe)
**URL**: /dipendenti
**Mostra**: lista dipendenti con tab per dettaglio (Cedolini, Movimenti, Giustificativi)
**Tab Cedolini**: carica cedolini per dipendente da /api/cedolini/dipendente/{id}
**Tab Movimenti**: cerca bonifici in /api/archivio-bonifici/transfers?beneficiario=NOME
**ENDPOINT NUOVO**: GET /api/dipendenti/{id}/fascicolo?anno=2026
  - Match stipendi banca con 3 strategie (IBAN, nome, importo)
  - Arricchimento anagrafica da cedolini
  - Presenze collegate per CF + cognome

### 6. CEDOLINI (HRCedolini.jsx, 603 righe)
**URL**: /cedolini
**Mostra**: cedolini raggruppati per mese, con totale netto/lordo
**Bottoni**: Import da Gmail → POST /api/cedolini/import-gmail?since_days=180

### 7. TFR (HRTFR.jsx, 214 righe)
**URL**: /tfr
**Mostra**: TFR accantonato per dipendente
**Bottoni**: Registra acconto → POST /api/tfr/acconti

### 8. PRESENZE (HRPresenze.jsx, 467 righe)
**URL**: /presenze
**Mostra**: libro unico, calendario presenze
**Bottoni**: Import PDF → POST /api/attendance/libro-unico/import-pdf

### 9. SCADENZE (Scadenze.jsx, 1010 righe)
**URL**: /scadenze
**Mostra**: calendario scadenze, scadenze IVA con progressivo, F24
**Bottoni**:
- Paga → POST /api/fatture-ricevute/paga-manuale (BUG FIXATO: importo €0,00)
- Crea scadenza → POST /api/scadenze/crea
- Elimina → DELETE /api/scadenze/{id} (BUG FIXATO: mancava confirm)
- Associa email → POST /api/email-scanner/associa

### 10. RICONCILIAZIONE (RiconciliazioneHub → include Riconciliazione, GestioneAssegni, RiconciliazionePaypal, RiconciliazioneUnificata)
**URL**: /riconciliazione

#### 10a. Riconciliazione (545 righe)
- Auto-riconcilia → POST /api/riconciliazione-auto/riconcilia-estratto-conto
- Manuale → POST /api/riconciliazione-fornitori/riconcilia-manuale

#### 10b. Gestione Assegni (2609 righe)
- Sync da EC → POST /api/assegni/sync-da-estratto-conto
- Auto-associa → POST /api/assegni/auto-associa
- Stampa carnet → jsPDF (funziona)

#### 10c. RiconciliazioneUnificata (1990 righe)
- Conferma multipla → POST /api/riconciliazione-intelligente/conferma-multipla
- Associa documenti → POST /api/documenti-non-associati/associa

### 11. CONTABILITÀ (ContabilitaHub → include Bilancio, BilancioVerifica, PianoDeiConti, GestioneCespiti, ControlloMensile, Finanziaria, BudgetPrevisionale, ChiusuraEsercizio, CentriCosto, UtileObiettivo, Mutui)
**URL**: /contabilita, /contabilita/bilancio, ecc.

### 12. MAGAZZINO (MagazzinoHub → include Magazzino, Inventario, RicercaProdotti, DizionarioArticoli, DizionarioProdotti)
**URL**: /magazzino

### 13. INSERIMENTO RAPIDO (InserimentoRapido.jsx, 903 righe)
**URL**: /rapido
**Bottoni**: Corrispettivo, Versamento banca, Apporto soci, Paga fattura, Acconto dipendente, Presenza
**Tutti → POST /api/rapido/...** (endpoint creato in questa sessione)

### 14. STRUMENTI (StrumentiHub → include VerificaCoerenza, Commercialista, EmailDownload, Visure, Pianificazione, MappaGestionale)
**URL**: /strumenti

### 15. INTEGRAZIONI (IntegrazioniHub → include IntegrazioniOpenAPI, GestioneInvoiceTronic, GestionePagoPA, RiconciliazionePaypal)
**URL**: /integrazioni

### 16. ADMIN (AdminHub → include Admin, BatchReprocessing)
**URL**: /admin

## BUG PATTERN COMUNI (aggiornato 22/04/2026)

1. **Body() mancante**: ✅ FIXATO 22/04/2026 — scan automatico su 215 router, fixati 21 file (accounting_extended, admin, bank_reconciliation, cash_register, config, buste_paga, shifts, staff, finanziaria, invoices_emesse, learning_machine_cdc, ocr_assegni, payroll, pianificazione, settings, warehouse/products, giustificativi, warehouse_main, invoices_main, distinte_bpm, document_ai). Tutti i router hanno Body importato e Body(...) sui parametri POST/PUT.
2. **Campi mancanti in response**: il backend non restituisce campi che il frontend mostra → €0,00 o vuoto. Verificare SEMPRE che i campi restituiti dal router corrispondano a quelli usati nel JSX.
3. **Modali senza overlay click-to-close**: ✅ FIXATO 22/04/2026 — fixati 7 file JSX: Fornitori (3 modali), VerbaliRiconciliazione, DizionarioArticoli, NoleggioAuto (2 modali), SaldiFeriePermessi. Pattern: overlay onClick={close} + contenuto onClick={e => e.stopPropagation()}.
4. **DELETE senza confirm**: ✅ OK — scan su 85 pagine JSX, nessun DELETE senza confirm trovato.
5. **Router non registrati**: ✅ FIXATO 22/04/2026 — timbrature.py (prefix /api/attendance) e email_f24.py (prefix /api/f24-email) aggiunti al router_registry.py. Scan completo: tutti gli altri file non registrati sono helper/common senza router.

## ROUTER REGISTRATI

Tutti i router sono in app/router_registry.py.
22 router erano mancanti e sono stati aggiunti in questa sessione.
I router usano prefix dinamici + add_api_route per le funzioni.

---

## VERIFICA SPECIFICHE OPERATIVE vs CODICE (22 Aprile 2026)

### ✅ IMPLEMENTATO E FUNZIONANTE:
1. **Fatture Ricevute**: parser XML, import P7M, deduplica hash, auto-routing cassa/banca, collegamento fornitore, alimentazione magazzino
2. **Fornitori**: creazione auto da fattura, deduplica P.IVA, metodo pagamento guida flusso, scheda con estratto fatture
3. **Prima Nota Cassa**: corrispettivi→cassa (solo contanti, POS separato), saldo anno
4. **Prima Nota Banca**: import estratto conto, classificazione, deduplica, collegamento fatture
5. **Cedolini**: parser Zucchetti (payslip_parser_v2), collegamento dipendente, TFR, import Gmail
6. **Dipendenti**: fascicolo completo con match stipendi (3 strategie), deduplica CF, arricchimento anagrafica
7. **F24**: import da documenti, scadenze, riconciliazione banca
8. **Documenti/Inbox**: upload auto, classificazione multi-tipo, deduplica hash
9. **Riconciliazione**: auto matching con scoring, conferma manuale, multipla
10. **Magazzino**: prodotti da fattura, dizionario articoli

### ⚠️ IMPLEMENTATO MA PARZIALE:
1. **Trasferimenti cassa↔banca**: endpoint `sposta-movimento` esiste ma non crea automaticamente il lato opposto
2. **POS→banca**: la quota POS crea partita attesa ma il match con accredito bancario non è robusto
3. **Alert engine**: servizio creato ma non ancora integrato nei router (nelle patch, da applicare)
4. **Event bus**: 20 handler definiti ma nelle patch, non ancora attivi in produzione
5. **Partite aperte**: engine creato ma nelle patch

### ❌ MANCA O DA IMPLEMENTARE:
1. **Netting note di credito**: TD04 viene riconosciuto ma il netting automatico con fatture collegate non è implementato
2. **Scoring completezza anagrafica dipendente**: il fascicolo c'è ma non c'è un punteggio di completezza visivo
3. **Audit trail modifiche anagrafiche**: non traccia chi/quando modifica un dipendente o fornitore
4. **Dashboard HR operativa**: manca dashboard dedicata HR con KPI dipendenti
5. **Merge duplicati fornitori guidato**: la deduplica trova i duplicati ma non c'è UI per il merge

### PARSER DISPONIBILI:
- `fattura_elettronica_parser.py` — XML FatturaPA
- `corrispettivi_parser.py` — XML corrispettivi
- `f24_parser.py` — modelli F24
- `payslip_parser_v2.py` — cedolini Zucchetti
- `busta_paga_multi_template.py` — multi-template
- `estratto_conto_bnl_parser.py` — BNL
- `estratto_conto_nexi_parser.py` — Nexi
- `paypal_msr_parser.py` — PayPal
