# Automazioni Pianificate — Ceraldi ERP
> Cosa manca, cosa già esiste nel codice, e cosa deve fare ogni automazione
> Aggiornato: Aprile 2026

---

## 1. PRIMA NOTA AUTOMATICA SENZA CONFERMA MANUALE (Priorità P1)

### Problema
Quando una fattura viene importata, la Prima Nota viene "preparata" ma non scritta. L'utente deve cliccare "Conferma pagamento" per ogni fattura — collo di bottiglia con 30+ fatture.

### Codice già esistente
- `app/routers/prima_nota_module/sync.py` → `registra_pagamento_fattura()`: determina cassa o banca, costruisce il movimento
- `app/routers/sync_relazionale.py` → `sync_fattura_to_prima_nota()`

### Cosa implementare
**Flusso corretto:**
1. Fattura importata → stato `provvisoria`, nessuna scrittura
2. Estratto conto importato → matching automatico trova la fattura
3. Confidenza >90% → **scrittura automatica** in Prima Nota
4. Fattura aggiornata: `pagato: true`, `data_pagamento`, `riconciliato: true`

**Scrittura Prima Nota Banca:**
```json
{
  "tipo": "uscita",
  "importo": "fattura.importo_totale",
  "descrizione": "Pagamento fattura {numero} - {fornitore}",
  "categoria": "Fornitori",
  "riferimento": "fattura.id",
  "data": "data_addebito_estratto_conto"
}
```

**Endpoint trigger:** `POST /api/prima-nota/auto-da-riconciliazione`

---

## 2. PIANO DEI CONTI CLICCABILE — PARTITARIO PER CONTO (Priorità P2)

### Problema
Il Piano dei Conti mostra la lista dei conti ma cliccandoci non succede nulla.

### Codice già esistente
- `app/routers/chart_of_accounts.py` → CRUD conti
- `app/repositories/chart_repository.py`
- Drawer già presente (aprile 2026): `GET /api/piano-conti/conto/{codice}/movimenti?limit=40&anno=2026`

### Cosa aggiungere — backend
Endpoint: `GET /api/piano-conti/{account_id}/partitario`

Risposta: lista movimenti con `data`, `tipo`, `importo`, `descrizione`, `documento_id`, `saldo_progressivo`, `totale_dare`, `totale_avere`, `saldo`, grafici mensili.

La query aggrega da: `prima_nota_banca`, `prima_nota_cassa`, `prima_nota_salari`, `invoices` filtrate per `centro_costo_id`.

### Cosa aggiungere — frontend
In `PianoDeiConti.jsx`: ogni conto clicabile → drawer con movimenti, totali, grafico mensile, link ai documenti.

---

## 3. SCHEDA FORNITORE COMPLETA (Priorità P2)

### Problema
Lista fornitori mostra nome, P.IVA, metodo pagamento. Cliccando non si vede nulla di aggregato.

### Endpoint da aggiungere
`GET /api/suppliers/{fornitore_id}/scheda`

Risposta aggregata:
```json
{
  "anagrafica": { "ragione_sociale", "piva", "iban", "metodo_pagamento" },
  "fatture": [ lista fatture ordinate per data ],
  "totale_fatturato": 45200.00,
  "totale_pagato": 38000.00,
  "totale_da_pagare": 7200.00,
  "scadenze_aperte": [ lista scadenze ],
  "pattern_pagamento": { "tipo": "mensile", "avg_days": 30 },
  "ultima_fattura": "2025-03-10",
  "categorie_acquisto": ["Alimentari", "Packaging"]
}
```

### Frontend
Click sul fornitore → scheda con: KPI (fatturato/pagato/da pagare), tabella fatture cliccabili, scadenze aperte, pattern pagamento, grafico mensile acquisti.

---

## 4. DETTAGLIO FATTURA COMPLETO (Priorità P2)

### Problema
La lista fatture non ha un dettaglio con righe, PDF, movimenti collegati.

### Endpoint da aggiungere
`GET /api/fatture-ricevute/{fattura_id}/dettaglio`

Risposta: tutti i campi fattura + righe dettaglio + allegato PDF (disponibilità) + movimenti Prima Nota collegati + movimento bancario abbinato + scadenza + carichi magazzino + eventuale nota di credito.

### Frontend
Pagina `/fatture/{id}` con tab: Righe, Contabilità, Magazzino, PDF inline, bottone "Segna come pagata".

---

## 5. FASCICOLO DIPENDENTE (Priorità P2)

### Problema
La lista dipendenti mostra solo dati anagrafici. Non c'è storico completo.

### Endpoint da aggiungere
`GET /api/dipendenti/{dipendente_id}/fascicolo`

Risposta aggregata:
```json
{
  "anagrafica": { "nome", "cf", "iban", "data_assunzione", "paga_base" },
  "cedolini": [ storico mensile con netto/lordo/ferie ],
  "tfr": { "accantonato_totale": 8240.00, "per_anno": {...} },
  "progressivi_anno_corrente": { "irpef": 1140.00, "inps": 567.00 },
  "stipendi_erogati": [ con data_bonifico e importo ]
}
```

### Frontend
Click dipendente → fascicolo con: timeline cedolini (barre mensili), saldi ferie/ROL, TFR maturato, storico bonifici abbinati, giustificativi anno corrente.

---

## 6. RISPOSTA AUTOMATICA "AVVISO BONARIO GIÀ PAGATO?" (Priorità P1)

### Problema
Arriva un avviso bonario dall'Agenzia delle Entrate. Non si sa se è già stato pagato. Bisogna cercare a mano nell'archivio F24.

### Codice già esistente — Parser F24 (`app/parsers/f24_parser.py`)
Estrae da ogni F24:
- `scadenza`: data pagamento
- `codice_fiscale`: del contribuente
- `tributi_erario[]`: lista tributi con `codice_tributo` (es. 1001=IRPEF, 6001=IVA), `mese_riferimento`, `anno_riferimento`, `importo_debito`
- `totale_debito`, `saldo_finale`

### Endpoint da aggiungere
`GET /api/f24/verifica-tributo?codice_tributo=1001&anno=2024&mese=06`

Risposta:
```json
{
  "trovato": true,
  "f24_id": "...",
  "data_pagamento": "16/07/2024",
  "importo": 1240.00,
  "banca": "BANCO BPM",
  "movimento_bancario": { "data", "importo", "riconciliato": true }
}
```

`POST /api/f24/verifica-avviso` — riceve tipo tributo, anno, periodo, importo → risponde se già pagato.

### Frontend
In Strumenti: campo "Inserisci codice tributo e anno" → risposta immediata pagato/non pagato.

---

## 7. TFR AUTOMATICO DA CEDOLINO (Priorità P3)

### Problema
Il TFR viene aggiornato solo chiamando esplicitamente `/api/tfr/accantonamento`. L'import cedolino non lo aggiorna automaticamente.

### Codice già esistente
- Parser (tutti i formati) estraggono: `tfr_quota_mese`, TFR maturato totale
- `app/routers/tfr.py` → `registra_accantonamento_tfr()`: calcola quota (retribuzione/13.5), rivalutazione, aggiorna totale TFR dipendente

### Da implementare
Nel flusso di import cedolino, dopo il salvataggio: chiamata automatica a `registra_accantonamento_tfr()` con i dati del PDF. Verifica anti-duplicato prima di creare il record.

---

## 8. CONTROLLO IVA MENSILE AUTOMATICO (Priorità P3)

### Problema
Nessun controllo automatico verifica se la liquidazione IVA è corretta e se il versamento è stato fatto.

### Codice già esistente
- `app/routers/gestione_iva_speciale.py` → liquidazione IVA
- `app/routers/f24_tributi.py` → tributi per codice (6001 = IVA)
- Parser F24 estrae `tributi_erario` con codice 6001 e importo

### Da implementare
**Calcolo automatico mensile:**
1. Somma IVA su fatture passive del mese (IVA a credito)
2. Somma IVA su corrispettivi del mese (IVA a debito)
3. Calcola saldo da versare
4. Cerca nell'archivio F24 del mese il codice 6001 con importo compatibile
5. Se trovato → ✅ OK | Se non trovato → ⚠️ alert | Se importo diverso → 🔴 differenza

**Alert automatico:** se dopo il 16 del mese non si trova il versamento → alert urgente nella campanellina.

**Frontend:** tabella mese per mese con IVA debito/credito/da versare/versato (link all'F24).

---

## 9. NOTIFICHE PUSH SU TUTTI GLI EVENTI (Priorità P3)

### Codice già esistente
- `app/routers/websocket_realtime.py` → WebSocket attivo
- `app/services/websocket_manager.py` → `notify_data_change()` già chiamato dallo scheduler PEC
- `frontend/src/hooks/useWebSocket.js` → hook già presente

### Da estendere
Aggiungere notifiche per tutti gli eventi:
- Nuova fattura importata → numero e fornitore
- Cedolino importato → nome dipendente e mese
- Scadenza in arrivo (3 giorni prima) → importo e tipo
- F24 da pagare entro 2 giorni → alert rosso
- Avviso bonario ricevuto via email → notifica immediata
- Riconciliazione completata → numero fatture abbinate

---

## 10. ESTRATTO CONTO NEXI — COMPLETAMENTO PARSER (Priorità P3)

### Codice già esistente
- `app/parsers/estratto_conto_bnl_parser.py` → completo: IBAN, numero conto, periodo, saldo, movimenti
- `app/parsers/estratto_conto_nexi_parser.py` → parziale

### Da completare
1. Parser BNL → già completo, manca il trigger automatico matching
2. Upload estratto conto → parsing → matching con fatture (confidenza >85% → auto, 60-85% → proposta, <60% → da abbinare)
3. Tutto finisce in `prima_nota_banca` con riferimento al documento abbinato

---

## RIEPILOGO PRIORITÀ

| # | Automazione | Impatto | Priorità |
|---|---|---|---|
| 1 | Prima Nota automatica al pagamento confermato | Alta | P1 |
| 6 | Risposta "avviso bonario già pagato" | Alta | P1 |
| 2 | Piano dei Conti cliccabile + partitario | Media | P2 |
| 3 | Scheda fornitore completa | Media | P2 |
| 4 | Dettaglio fattura completo | Media | P2 |
| 5 | Fascicolo dipendente | Media | P2 |
| 7 | TFR automatico da cedolino | Media | P3 |
| 8 | Controllo IVA mensile automatico | Media | P3 |
| 9 | Notifiche push su tutti gli eventi | Media | P3 |
| 10 | Estratto conto → matching automatico completo | Media | P3 |

---

*Aggiornato: Aprile 2026*
