# Ceraldi ERP — Backlog operativo

Elenco ragionato delle cose da sistemare, per priorità di impatto sul lavoro quotidiano.
Ultimo aggiornamento: Apr 2026.

---

## 🔴 P0 — Problemi critici che falsano i numeri

### 1. Piano dei Conti non segue il filtro ANNO e non si popola da solo

Stato attuale (vedi `/contabilita#tab=piano-conti`):
- Quasi tutti i conti mostrano `€ 0,00` (Cassa, Banca c/c, IVA a credito, Magazzino merci, Debiti tributari…)
- `02.01.01 Debiti v/fornitori` mostra € 762.038,08 → è il cumulativo di tutti gli anni, NON l'anno selezionato in alto (2026)
- Il filtro ANNO del TopNav (2024/2025/2026) non agisce sul piano conti
- Il risultato è che il bilancio è inutilizzabile

**Cosa deve fare il piano conti:**

1. **Rispettare il filtro anno globale**: i saldi devono essere calcolati dinamicamente sulle operazioni dell'anno selezionato (`?anno=2025`)
2. **Popolarsi AUTOMATICAMENTE** a ogni nuova operazione in entrata:
   - Nuovo corrispettivo → movimento su `01.01.01 Cassa` (entrata) + `04.01.01 Ricavi vendita merce` + `02.03.01 IVA a debito`
   - Nuova fattura acquisto → movimento su `02.01.01 Debiti v/fornitori` + `03.xx Costo` + `01.04.01 IVA a credito`
   - Pagamento bonifico → movimento su `01.01.02 Banca c/c` + scarico `02.01.01 Debiti`
   - Pagamento contanti → movimento su `01.01.01 Cassa` + scarico `02.01.01 Debiti`
   - F24 → movimento su `01.01.02 Banca c/c` + scarico `02.02.01 Debiti tributari`
   - Stipendio dipendente → `01.01.02 Banca c/c` + `03.09 Costo personale`
   - Versamento contanti in banca → spostamento Cassa → Banca
   - Mutuo → `01.01.02 Banca c/c` + `02.04 Mutui passivi`
   - Cespite → `01.05 Immobilizzazioni` + `02.01.01 Debiti v/fornitori`

3. **Endpoint unico** `GET /api/piano-conti/saldi?anno=2025` che ricalcola tutto al volo aggregando da:
   - `corrispettivi`
   - `invoices` / `fatture_passive`
   - `prima_nota_cassa`
   - `prima_nota_banca`
   - `estratto_conto_movimenti`
   - `cedolini`
   - `assegni`
   - `f24_*`

4. **Mappatura causale → conto** salvata in `regole_categorizzazione` (già esiste la tab, ma va popolata)

5. **Cache**: i saldi per anno vanno cachati con TTL 5 min, invalidata automaticamente a ogni nuova scrittura su una collection rilevante

---

### 2. Associazione automatica documenti da Gmail

Stato attuale: i PDF scaricati da `ceraldigroupsrl@gmail.com` finiscono in `documents_inbox` o `documenti_non_associati`. **Non vengono collegati alle voci del gestionale.**

**Cosa deve fare:**

Per ogni email processata, in base al mittente (whitelist 14 mittenti già definita):
- **Cedolino** (Ferrantini / Marotta) → parser PDF → `cedolini` del dipendente CF estratto + link al PDF
- **F24** (Ferrantini / Marotta) → parser → `f24_unificato` con codice tributo, importo, scadenza + link al PDF + auto-match con movimento banca omonimo
- **Cartella esattoriale** (Agenzia Riscossione) → `documenti_non_associati` con tag "cartella" + scadenza
- **INPS comunica** → `documenti_non_associati` con tag "inps" + eventuale link a cedolino del mese
- **INAIL** → `documenti_non_associati` con tag "inail" + link a movimento banca F24
- **PagoPA verbali** (Comune Napoli) → `verbali_noleggio` con match targa + importo + link PDF
- **TARI** (Comune Napoli) → `documenti_non_associati` con scadenza auto
- **PayPal assistenza** → `documenti_non_associati` con tag "paypal" + match movimenti banca PayPal
- **Fornitori generici** → tentativo di match con `invoices` per P.IVA / numero / importo → se trovato, allega PDF alla fattura come ricevuta/ordine

**Nuova pagina `/documenti/associazioni`** con:
- Tab "Da associare" (documenti orfani)
- Tab "Associati" (con filtro per tipo)
- Azione "Associa manualmente a…" per i casi ambigui

**Endpoint `POST /api/documenti/auto-associa`** che rilancia il matcher su tutti i documenti orfani.

---

## 🟠 P1 — Tab della pagina Contabilità da completare

### 3. Mutui — `/contabilita#tab=mutui` senza dati

Stato attuale: pagina vuota.

**Cosa serve:**
- Collection `mutui` con schema: {id, istituto, importo_iniziale, durata_anni, tasso, rata_mensile, data_inizio, data_fine, rate_totali, rate_pagate, saldo_residuo}
- UI: tabella con i mutui attivi + scheda dettaglio
- Auto-rilevamento rate: ogni movimento banca che contiene "RATA MUTUO" / "ADD. MUTUO" viene associato al mutuo corrispondente
- Piano ammortamento calcolato (quota capitale vs interessi)
- Link alle causali contabili (`03.xx Interessi passivi`, `02.04 Mutui passivi`)

### 4. Budget — `/contabilita#tab=budget` senza dati

Stato attuale: pagina vuota.

**Cosa serve:**
- Collection `budget_voci` con {anno, mese, categoria, importo_previsto, importo_effettivo}
- UI: griglia 12 mesi × categorie (ricavi / costi / utili)
- Il "previsto" è a compilazione manuale o copiato dall'anno precedente +/− %
- L'"effettivo" arriva automaticamente dalle operazioni dell'anno (corrispettivi, invoices, prima_nota)
- Scostamento (previsto − effettivo) con semaforo verde/giallo/rosso
- Grafico mensile previsto vs effettivo

### 5. Chiusura esercizio — `/contabilita#tab=chiusura` dati incompleti

Stato attuale: alcuni numeri ci sono, ma mancano voci.

**Cosa serve:**
- Ratei e risconti (attivi e passivi): collection `ratei_risconti`
- Rimanenze finali di magazzino: attualmente prese da `warehouse_stocks` ma il valore non è rivalutato
- TFR maturato dell'anno: somma dei `tfr_mese` dei cedolini per dipendente
- Ammortamenti cespiti: collegato al tab Cespiti
- Quadratura attivo = passivo + patrimonio
- Stampa bilancio CE + SP pronto per commercialista

### 6. Finanziaria — `/contabilita#tab=finanziaria` sezione incompleta

Stato attuale: alcune voci, ma sezione incompleta.

**Cosa serve (chiarimento):**
- Cosa deve mostrare questa tab? Indici finanziari? Cashflow? Analisi liquidità?
- → DOMANDA PER TE: cosa ti aspetti di vedere in "Finanziaria"?
- Finché non chiari, ipotizzo: ROE, ROI, indice liquidità, rapporto debiti/patrimonio, durata media crediti/debiti, rotazione magazzino

### 7. Cespiti — `/contabilita#tab=cespiti` non funziona

Stato attuale: pagina rotta (errore o bianca).

**Cosa serve:**
- Collection `cespiti` con {id, descrizione, categoria, fornitore_piva, fattura_id, data_acquisto, costo_storico, aliquota_ammortamento, fondo_ammortamento, valore_residuo, stato (attivo/dismesso)}
- UI: lista cespiti + scheda dettaglio con piano ammortamento pluriennale
- Auto-rilevamento: quando arriva una fattura con riga > 516 € e categoria "attrezzature" / "mobili" / "impianti", propone creazione cespite
- Ammortamento fiscale: applica aliquota ministeriale (es. attrezzature 15%, mobili 12%, autovetture 25%)
- Rivalutazione / dismissione con causale e data

### 8. Controllo mensile — `/contabilita#tab=controllo` errori

Stato attuale: pagina ha errori, mancano "POS banca" e "Diff.".

**Cosa serve:**
- Riga per ogni mese dell'anno con: Ricavi · Costi · IVA deb. · IVA cred. · Saldo IVA · F24 pagato · **POS banca** · **Diff.**
- POS banca = accrediti POS dal giorno X+1 visti in `estratto_conto_movimenti` (causali "ACCR. POS" / "INCASSO CARTE")
- Diff. = (incasso POS lato corrispettivi) − (accredito POS lato banca) → mostra se il POS del giorno X è arrivato in banca il giorno X+1
- Semaforo su ogni riga se i numeri quadrano o no

---

## 🟡 P2 — Assegni (già analizzato, pronto per implementazione)

### 9. Auto-matcher assegni ↔ fatture (livelli 1-4)

Logica documentata in `/app/memoria/LOGICA_OPERATIVA.md` sezione Assegni.

Regole confermate:
- Tolleranza: ±0,005 € (mezzo centesimo); oltre → prima nota provvisoria
- Max 4 rate per fattura, 1 assegno al mese, finestra max 4 mesi
- Quota cassa manuale per pagamenti misti (es. 3 assegni + resto in contanti)
- Stesso fornitore obbligatorio, stesso carnet per Livello 2

**Cosa costruire:**
- Endpoint `POST /api/assegni/auto-match`
- Helper `combinations_with_tolerance(items, target, tol=0.005, k_max=4)`
- Modello assegno aggiornato: `fatture_collegate: [{fattura_id, quota}]`, `quota_cassa_manuale`, `match_auto`, `stato (emesso|parzialmente_assegnato|assegnato|addebitato)`
- Modello fattura aggiornato: `assegni_collegati: [{assegno_id, quota}]`, `importo_pagato`, `stato_pagamento`
- UI pagina Assegni:
  - Pulsante "🤖 Auto-collega" con report 4 livelli
  - Tab "Da confermare" per match ambigui
  - Modal "Collega fatture" con quote editabili + campo quota cassa manuale
  - Filtro fatture = SOLO stesso fornitore dell'assegno
  - Validazione live: Σ quote = importo_assegno ± 0,005 €

---

## 🟢 P3 — Nice-to-have

### 10. Fornitori: pulsante bulk "Auto-conferma fatture"

Già creato l'endpoint `/api/fatture-ricevute/backfill-autoroute`. Manca solo il pulsante nella pagina `/fornitori` che lo lanci, così dopo aver configurato i metodi dei fornitori mancanti l'utente non usa curl.

### 11. Magazzino: indicatore "N fornitori attivi"

Mostra in alto quanti fornitori hanno `esclude_magazzino: false` (oggi 0). Cresce man mano che l'utente li riabilita.

### 12. Tema scuro opzionale

CSS variables già pronte in `index.css`. Toggle nel TopNav (~30 min).

### 13. PWA installabile

`manifest.json` + service worker + icone. First load già OK (220 KB gzipped).

### 14. Collection orfane da pulire

Già identificate (vedi messaggio precedente): `log_operatori`, `paypal_transactions`, `warehouse_inventory` vuote; duplicati `documents_inbox`, `documenti_non_associati`, attachments email, `verbali_noleggio`, `corrispettivi`. Backup prima, poi drop.

---

## 🧠 Nota architetturale importante

**MongoDB URL**: il cluster reale dove sono i dati è `cluster0.vofh7iz.mongodb.net` (Ceraldi), database `Gestionale`. NON è il cluster `customer-apps.zzr2e7` che Emergent propone come default. Quando si fa deploy, verificare sempre che `MONGO_URL` punti al cluster Ceraldi, altrimenti la produzione vede un DB vuoto.

---

## 📊 Roadmap suggerita (ordine di attacco)

| Step | Cosa | Effort | Impatto |
|---|---|---|---|
| 1 | Piano Conti auto-popolato + filtro anno | 3-4 h | 🔴 altissimo |
| 2 | Tab Controllo mensile (fix + POS/Diff) | 1-2 h | 🔴 alto |
| 3 | Cespiti (pagina funzionante + auto-rilevamento) | 2-3 h | 🟠 alto |
| 4 | Auto-associazione documenti Gmail | 3-4 h | 🟠 alto |
| 5 | Auto-matcher assegni (L1+L2+L3+L4) | 3-4 h | 🟠 alto |
| 6 | Mutui | 1-2 h | 🟡 medio |
| 7 | Budget | 2-3 h | 🟡 medio |
| 8 | Chiusura esercizio (completamento) | 2-3 h | 🟡 medio |
| 9 | Finanziaria (chiarimento + implementazione) | 2 h | 🟢 basso |
| 10 | P3 (bulk, PWA, tema scuro, cleanup) | 2 h | 🟢 basso |

**Totale stimato**: circa 22-30 ore di lavoro distribuite su più sessioni.

---

## ❓ Domande aperte per l'utente

1. **Tab Finanziaria**: cosa vuoi vedere esattamente? Indici (ROE, ROI, liquidità), cashflow previsionale, altro?
2. **Cespiti**: hai già un elenco cespiti altrove da importare, o partiamo da zero e li crei dall'archivio fatture?
3. **Budget**: vuoi partire dai dati 2024-2025 come base per il 2026?
4. **Mutui**: quanti mutui attivi hai? (importo + istituto + rata)
5. **Associazione documenti**: nel caso di email generica da fornitore (es. ordine via Gmail) vuoi che cerchi di legarla a una fattura già in archivio, o lasciarla "libera" in documenti_non_associati?
