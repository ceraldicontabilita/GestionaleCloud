# Procedure Operative — Ceraldi ERP
> Flusso di lavoro contabile mensile | Aggiornato: Aprile 2026 | P.IVA: 04523831214

---

## PROCEDURA MENSILE STANDARD

### FASE 1: Import Documenti Fiscali

**1.1 Download Fatture PEC (automatico ogni ora)**
- Lo scheduler scarica automaticamente le fatture da Aruba PEC (`fatturazioneceraldi@pec.it`)
- Controlla: INBOX + INBOX.lette
- Deduplicazione automatica via hash MD5
- In caso di problemi: `POST /api/email-download/pec/download-fatture-sync?since_days=30`

**1.2 Import manuale XML (se necessario)**
- Pagina: Documenti → Import
- Formati accettati: `.xml`, `.p7m`, `.zip`
- Verifica anti-duplicato automatica

**1.3 Import Estratto Conto Banca**
- Scarica CSV da portale BPM (formato: separatore `;`, encoding UTF-8-BOM)
- Upload in: Prima Nota → Banca → Import CSV
- Tempo atteso: ~2.5 secondi per file completo
- Endpoint: `POST /api/bank/import-estratto-conto`

**1.4 Import Corrispettivi RT**
- I file XML arrivano automaticamente dal Registratore Telematico
- In caso di import manuale: Documenti → Import XML Corrispettivi

---

### FASE 2: Verifica e Classificazione

**2.1 Fatture da rivedere**
- Sezione: Documenti → Da Rivedere
- Verificare: fornitore abbinato correttamente, centro di costo assegnato, IVA detraibile calcolata
- Se fornitore mancante: compilare IBAN e metodo pagamento nell'anagrafica fornitore

**2.2 Corrispondenza totali**
- Verificare che la somma delle righe = totale documento (le fatture con anomalia vengono segnalate automaticamente)

---

### FASE 3: Riconciliazione Banca

**3.1 Abbinamenti automatici**
Il sistema abbina automaticamente:
- Fatture ↔ Bonifici (importo ±2%, fornitore nella descrizione)
- F24 ↔ Banca (codice tributo, importo, data 16 ±3gg)
- Stipendi ↔ Banca (IBAN dipendente, importo esatto, data ±5gg)
- Rate Mutuo ↔ Banca (importo ±€1, data ±7gg)
- POS ↔ Corrispettivi (importo ±€5, data attesa accredito)

**3.2 Abbinamenti manuali (confidenza <60%)**
- I movimenti non abbinati restano in "Da abbinare"
- Abbinare manualmente selezionando il documento corrispondente

**3.3 Verifiche specifiche**
- Verbali noleggio auto ↔ Banca: cercate le società (Leasys, ALD, Arval) nei movimenti
- PagoPA ↔ Banca: avvisi Gmail abbinati ai movimenti bancari
- Cartelle Agenzia Entrate ↔ Banca: confronto con F24 già pagati
- Cartelle Agenzia Riscossione ↔ Banca
- TARI ↔ Banca

---

### FASE 4: Corrispettivi e Cassa

**4.1 Verifica corrispondenza POS**
- Confronto incasso POS da corrispettivi XML vs accredito banca
- Regola tempi accredito:
  - Lun–Gio: accredito il giorno lavorativo successivo
  - Ven–Dom: accredito il lunedì successivo
- Evidenziare discrepanze (potenziale elemento per sanzioni)

**4.2 Saldo cassa**
```
Saldo Cassa = PagatoContanti - Uscite Contanti
```
I pagamenti elettronici (POS) NON sono cassa — vanno in banca.

---

### FASE 5: IVA Trimestrale

**Calcolo liquidazione:**
```
IVA a debito  = SUM(corrispettivi.totale_iva) per trimestre
IVA a credito = SUM(invoices.iva_detraibile) per trimestre
Liquidazione  = IVA a debito − IVA a credito
```

**Se positiva**: versamento tramite F24 (codice tributo 6001) entro il 16 del mese successivo al trimestre.

**Scadenze:**
- 1° Trimestre (gen–mar): versamento entro 16 maggio
- 2° Trimestre (apr–giu): versamento entro 16 agosto (proroga settembre)
- 3° Trimestre (lug–set): versamento entro 16 novembre
- 4° Trimestre (ott–dic): versamento entro 16 marzo dell'anno successivo

---

### FASE 6: F24 Mensile (16 di ogni mese)

**Tributi da versare ogni mese entro il 16:**
- IRPEF ritenute dipendenti (codice 1001)
- INPS quota dipendente (codice 1301)
- INPS quota azienda (codice 1303)
- Addizionale regionale IRPEF (codice 3802)
- Addizionale comunale IRPEF (codice 1030)

**Verifica pagamento:**
1. Sezione F24 → Archivio
2. Oppure `GET /api/f24/verifica-tributo?codice_tributo=1001&anno=2026&mese=04`

---

### FASE 7: HR Dipendenti

**7.1 Import cedolini mensili**
- Automatico da Gmail ogni 50 minuti (mittenti: commercialista Marotta, Studio Ferrantini)
- Import manuale: `POST /api/cedolini/import-gmail?since_days=30`
- Verifica abbinamento dipendente-cedolino

**7.2 Verifica stipendi erogati**
- Controllo che tutti i bonifici stipendi siano abbinati ai cedolini
- Sezione: HR → Cedolini → verifica colonna "Pagato"

**7.3 Dati anagrafica dipendenti**
Ogni dipendente deve avere:
- Nome, CF, mansione, livello, scatto contingenza
- Fine contratto, tipo contratto, numero matricola
- IBAN per accredito stipendio
- Cedolini con trattenute verbali aggiornati

**7.4 Aggiornamento TFR**
- Verificare accantonamento mensile in: HR → TFR
- Rivalutazione annua: 1.5% fisso + 75% ISTAT

---

### FASE 8: Verifica Finale

**Lista controlli:**
- [ ] Tutte le fatture importate e classificate
- [ ] Estratto conto importato e riconciliato
- [ ] Corrispettivi del mese completi
- [ ] Prima Nota Cassa e Banca aggiornate
- [ ] F24 del 16 versato e abbinato
- [ ] Cedolini importati e stipendi confermati
- [ ] TFR aggiornato
- [ ] Scadenziario fornitori verificato
- [ ] Saldo cassa e saldo banca corretti

---

## PROCEDURE SPECIFICHE

### Importare una fattura con nota di credito (TD04)
1. Importare normalmente il file XML della nota di credito
2. Il sistema cerca automaticamente la fattura originale per numero riferimento + P.IVA
3. Verifica che la fattura originale sia segnata con `ha_nota_credito: true`
4. Verifica che l'importo residuo sia corretto

### Verificare un avviso bonario dall'Agenzia delle Entrate
1. Sezione: Strumenti → Verifica F24
2. Inserire: codice tributo, anno, periodo
3. Il sistema risponde se l'importo è già stato versato (con data e movimento bancario abbinato)

### Aggiungere un nuovo fornitore manualmente
1. Sezione: Fornitori → Nuovo
2. Compilare: ragione sociale, P.IVA, metodo pagamento, IBAN (se bonifico)
3. Aggiorna dati da Camera di Commercio: bottone "Aggiorna da OpenAPI"

### Import massivo fatture PEC arretrate
```
POST /api/email-download/pec/download-fatture-sync?since_days=365
```
Recupera tutte le fatture degli ultimi 12 mesi. Richiede qualche minuto.

---

## CALENDARI

### Scadenzario mensile

| Data | Adempimento |
|---|---|
| Ogni 16 | F24 (IRPEF, INPS, addizionali) |
| Fine mese | Import estratto conto banca |
| Fine mese | Verifica corrispettivi completi |
| Fine mese | Cedolini importati e verificati |
| 16 marzo | Saldo IVA anno precedente |
| 30 giugno | Dichiarazione redditi |
| 30 novembre | Acconto imposte |

### Alert automatici del sistema
- 7 giorni alla scadenza → badge ROSSO nella campanellina
- 8–30 giorni alla scadenza → badge GIALLO
- Oltre 30 giorni → badge VERDE

---

*Aggiornato: Aprile 2026*
