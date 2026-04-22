# Ceraldi ERP — Scheda rapida

DB MongoDB: `Gestionale` · P.IVA: 04523831214 · aggiornato Apr 2026

## Stack

| Layer    | Tecnologia                                  |
|----------|---------------------------------------------|
| Frontend | React 18 + Vite → porta 3000                |
| Backend  | FastAPI + Motor (async) → porta 8001        |
| DB       | MongoDB Atlas (`Gestionale`, cluster0.vofh7iz) |
| Design   | Inline styles da `src/lib/utils.js` (no Tailwind, no Shadcn) |
| Schedule | APScheduler (PEC orario, Gmail 10 min)      |
| Servizi  | `app/services/` — event bus, alert, audit, deduplica, partite, riconciliazione |

## Collezioni canoniche

```
# Core business
invoices (~3856)                  → Fatture SDI TD01+TD04      [collection UNICA fatture passive]
fornitori (~268)                  → Anagrafica fornitori       [NON suppliers]
dipendenti (~30)                  → HR anagrafica              [NON employees]
cedolini (~916)                   → Buste paga Zucchetti v2
corrispettivi (~1051)             → UNICA fonte ricavi

# Contabilità
prima_nota_cassa (~1428)          → Prima nota cassa
prima_nota_banca (~1138)          → Prima nota banca
estratto_conto_movimenti (~4261)  → Movimenti bancari BPM      [collection UNICA]
f24_unificato (~83)               → Modelli F24                [NON f24_models]
assegni (~210)                    → Assegni emessi per carnet
scadenziario_fornitori (~903)     → Scadenze fornitori

# HR
bonifici_stipendi (~736)          → Bonifici stipendi
prima_nota_salari (~696)          → Movimenti stipendiali
presenze_mensili (~211)           → Da parser Libro Unico
quietanze_f24 (~303)              → Quietanze F24

# Magazzino
warehouse_inventory (~5372)       → Giacenze magazzino         [NON warehouse_stocks]
acquisti_prodotti (~15065)        → Storico acquisti
dizionario_prodotti (~112)        → Normalizzazione nomi

# Documenti
documents_inbox (~803)            → Staging documenti email
documenti_classificati (~1967)    → Classificati per tipo
documenti_non_associati (~285)    → Da associare manualmente

# Sistema relazionale (nuovo)
partite_aperte                    → Scadenziario materializzato
riconciliazioni_match             → Match riconciliazione N:M
audit_log                         → Log unificato cambi stato
alert_definitions                 → Catalogo 48 codici alert
alerts                            → Alert attivi/risolti

# Veicoli
verbali_noleggio (~165)           → Sanzioni stradali
veicoli_noleggio (~4)             → Flotta aziendale
```

## Route principali

```
/                       Dashboard
/fatture                Fatture ricevute
/fatture/corrispettivi  Corrispettivi giornalieri
/prima-nota             Cassa + Banca + Provvisori
/fornitori              Fornitori
/dipendenti             HR dipendenti
/cedolini               Buste paga (Per Mese / Per Dipendente)
/presenze               Calendario presenze + import PDF Libro Unico
/noleggio               Flotta + verbali + costi
/magazzino              Giacenze + inventario + ricerca
/riconciliazione        Riconciliazione bancaria unificata
/riconciliazione/assegni  Assegni per carnet
/contabilita            Piano conti · Bilancio · Verifica · Calendario fiscale
                        · Cespiti · Finanziaria · Chiusura · Budget · Mutui
/strumenti              Verifica coerenza · Commercialista · Pianificazione · Visure
/documenti              Archivio + Import documenti
/integrazioni           OpenAPI + InvoiceTronic + PagoPA
/admin                  Email + Parole chiave + Fatture + Sistema
```

## Servizi core (app/services/)

```
event_bus.py                → Dispatcher eventi sincrono tra moduli
alert_engine.py             → 48 codici alert con trigger e chiusura automatica
audit_logger.py             → Log unificato: chi/quando/cosa/da-dove-a-dove
deduplica.py                → Verifica duplicati: fatture, fornitori, cedolini, F24, movimenti
partite_aperte_engine.py    → Scadenziario materializzato (CRUD + ricerca per match)
riconciliazione_engine.py   → Scoring match 4 livelli: esatto → pattern → approssimato → debole
```

## Regole critiche (da non dimenticare mai)

1. DB: `Gestionale` — NON `azienda_erp_db`
2. Fornitori: collection `fornitori` — NON `suppliers`
3. Magazzino: `warehouse_inventory` — NON `warehouse_stocks` (deprecata, dati errati)
4. Dipendenti: `dipendenti` — NON `employees`
5. Cedolini display: campo `nome_dipendente` — NON `dipendente_nome`
6. Note credito: TD04 → importo negativo + badge rosso
7. Ricavi: SOLO da `corrispettivi` — le `invoices` sono costi
8. IMAP: sempre dentro `asyncio.to_thread()`
9. Settings: `.env` ha priorità su OS env (intenzionale)
10. `backend/server.py`: non cancellare — è l'entry point di Supervisor
11. Metodo pagamento fattura: preso sempre dal fornitore, mai dall'XML SDI
12. Nomi collezioni: importare SEMPRE da `app/db_collections.py` — mai stringhe hardcoded
13. Claude NON pusha su main — patch in `claude-patches/chat-N-descrizione/` + `ISTRUZIONI.md`
14. Ogni CRUD significativo chiama `propagate_event()` dal event bus
15. Alert: usare SOLO codici dal catalogo in `alert_engine.py` — mai alert "liberi"
16. Design: `src/lib/utils.js` unica fonte di verità — palette navy #0f2744 + accento oro #b8860b

## Comandi utili

```bash
# Riavviare i servizi
sudo supervisorctl restart backend
sudo supervisorctl restart frontend

# Log
tail -n 100 /var/log/supervisor/backend.err.log
tail -n 100 /var/log/supervisor/frontend.err.log

# Health check
curl -s http://localhost:8001/api/health

# Pacchetti Python:
pip install <pkg> && pip freeze > /app/backend/requirements.txt

# Pacchetti Node (usa sempre yarn, mai npm):
cd /app/frontend && yarn add <pkg>
```

## Mittenti email autorizzati

| Mittente                                              | Tipo doc          | Destinazione                  |
|-------------------------------------------------------|-------------------|-------------------------------|
| `grazia.studioferrantini@email.it`                    | Cedolino/F24      | `cedolini`                    |
| `rosaria.marotta@email.it`                            | F24               | `cedolini`                    |
| `f.ferrantini@email.it`                               | Cedolino/F24      | `cedolini`                    |
| `ricevuta.pagaonline@agenziariscossione.gov.it`       | Cartella          | `documenti_non_associati`     |
| `notifica.acc.campania@pec.agenziariscossione.gov.it` | Cartella          | `documenti_non_associati`     |
| `no_reply@agenziariscossione.gov.it`                  | Cartella          | `documenti_non_associati`     |
| `inpscomunica@postacert.inps.gov.it`                  | INPS              | `documenti_non_associati`     |
| `auto_napoli@massivo.pec.inail.it`                    | INAIL             | `documenti_non_associati`     |
| `partenopay@ext.comune.napoli.it`                     | PagoPA            | `verbali`                     |
| `noreply-checkout@ricevute.pagopa.it`                 | PagoPA            | `documenti_non_associati`     |
| `tari.avvisibonari@pec.comune.napoli.it`              | TARI              | `documenti_non_associati`     |
| `entrate.tari-tares-tarsu@pec.comune.napoli.it`       | TARI              | `documenti_non_associati`     |
| `assistenza@paypal.it`                                | PayPal            | `documenti_non_associati`     |
| `@pec.fatturapa.it` (PEC)                             | Fattura XML SDI   | `invoices` (parser XML)       |

NON attendibili da Gmail: ABC Napoli, TIM — le loro fatture arrivano come XML SDI dalla PEC.
Corrispettivi: SOLO import manuale XML dal registratore telematico, MAI da Gmail.

Per il dettaglio funzionale vedi `LOGICA_OPERATIVA.md`.
Per lo stato di progetto vedi `PRD.md`.
