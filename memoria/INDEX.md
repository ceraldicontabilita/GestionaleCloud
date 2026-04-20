# Ceraldi ERP — Scheda rapida

DB MongoDB: `Gestionale` · P.IVA: 04523831214 · aggiornato Apr 2026

## Stack

| Layer    | Tecnologia                                  |
|----------|---------------------------------------------|
| Frontend | React 18 + Vite → porta 3000                |
| Backend  | FastAPI + Motor (async) → porta 8001        |
| DB       | MongoDB Atlas (`Gestionale`)                |
| Design   | Inline styles da `src/lib/utils.js` (no Tailwind, no Shadcn) |
| Schedule | APScheduler (PEC orario, Gmail 10 min)      |

## Collezioni canoniche

```
dipendenti (30)                   → HR                    [NON employees]
cedolini (301)                    → Buste paga Zucchetti v2
presenze (290)                    → Presenze giornaliere
invoices (1.405)                  → Fatture SDI TD01+TD04
fornitori (245)                   → Anagrafica fornitori  [NON suppliers]
prima_nota_cassa (136)            → Prima nota cassa
prima_nota_banca (4.365)          → Prima nota banca
corrispettivi (54)                → UNICA fonte ricavi
estratto_conto_movimenti (8.839)  → Movimenti bancari BPM
assegni (220)                     → Assegni emessi
warehouse_stocks (496)            → Magazzino             [NON warehouse_inventory]
verbali_noleggio (165)            → Sanzioni stradali
veicoli_noleggio (4)              → Flotta aziendale
scadenziario_fornitori (185)      → Scadenze fornitori
piano_conti (30)                  → Piano dei conti
mittenti_attendibili (11)         → Filtri email
documents_inbox (32)              → Staging documenti email
f24_unificato (1)                 → Modelli F24
```

## Route principali

```
/                       Dashboard
/fatture                Fatture ricevute (1.405)
/fatture/corrispettivi  Corrispettivi giornalieri
/prima-nota             Cassa + Banca + Provvisori
/fornitori              Fornitori (245)
/dipendenti             HR dipendenti (30)
/cedolini               Buste paga (vista Per Mese / Per Dipendente)
/presenze               Calendario presenze + import PDF Libro Unico
/noleggio               Flotta + verbali + costi
/magazzino              Giacenze + inventario + ricerca
/riconciliazione        Riconciliazione bancaria unificata
/riconciliazione/assegni  Assegni per carnet
/contabilita            Piano conti + Bilancio + Verifica + Controllo mensile
                        + Calendario fiscale + Cespiti + Finanziaria
                        + Chiusura + Budget + Mutui + Contab. avanzata
/strumenti              Verifica coerenza + Commercialista + Pianificazione + Visure
/documenti              Archivio + Import documenti
/integrazioni           OpenAPI + InvoiceTronic + PagoPA
/admin                  Email + Parole chiave + Fatture + Sistema
```

## Regole critiche (da non dimenticare mai)

1. DB: `Gestionale` — NON `azienda_erp_db`
2. Fornitori: collection `fornitori` — NON `suppliers`
3. Magazzino: `warehouse_stocks` — NON `warehouse_inventory` (vuota)
4. Dipendenti: `dipendenti` — NON `employees`
5. Cedolini display: campo `nome_dipendente` — NON `dipendente_nome`
6. Note credito: TD04 → importo negativo + badge rosso
7. Ricavi: SOLO da `corrispettivi` — le `invoices` sono costi
8. IMAP: sempre dentro `asyncio.to_thread()`
9. Settings: `.env` ha priorità su OS env (intenzionale)
10. `backend/server.py`: non cancellare — è l'entry point di Supervisor
11. Metodo pagamento fattura: preso sempre dal fornitore, mai dall'XML SDI
12. PostCSS: plugin Tailwind disattivato, il design passa per `src/lib/utils.js`

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

# Pacchetti Python (allineare requirements.txt):
pip install <pkg> && pip freeze > /app/backend/requirements.txt

# Pacchetti Node (usa sempre yarn, mai npm):
cd /app/frontend && yarn add <pkg>
```

## Mittenti email autorizzati (14)

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

Per il dettaglio funzionale vedi `LOGICA_OPERATIVA.md`.
Per lo stato di progetto vedi `PRD.md`.
