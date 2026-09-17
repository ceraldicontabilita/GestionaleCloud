# HACCP Ceraldi — Mappa DB/API (fonte di verità per field names)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

> Ultimo aggiornamento: 04/07/2026 v67 (7 tranche tracciabilità lotti + registro richiami)
> SEMPRE leggere questo file prima di scrivere query MongoDB o chiamate API.

---

## REGOLE CRITICHE
1. `ingredienti_dettaglio[].unita_misura` (NON `unita`) — confermato su tutti i doc
2. `data_scadenza` in `lotti` = formato `dd/mm/yyyy` — usare `parseData()` nel frontend
3. `fornitori.nome` = chiave principale (NON `id`)
4. `anomalie.data_segnalazione` = ISO `YYYY-MM-DD` per doc nuovi (v55+)
5. Mai usare `db.ricette.find({})` senza `{"_id": 0}` nella projection

---

## COLLECTIONS — FIELD NAMES VERIFICATI

### `ricette`
```
id (UUID str), nome, reparto, porzioni, note, foto_url
ingredienti[]              → array nomi ingredienti (semplice)
ingredienti_dettaglio[]    → [{nome, quantita, unita_misura, prodotto_dizionario_id, prezzo_kg, costo_calcolato}]
componenti[]               → BOM: [{tipo (ingrediente|sotto_ricetta), ref_id?, nome, quantita, unita_misura}]  ← aggiunto v57
costo_totale, costo_porzione, completezza
prezzo_vendita (float, opzionale)
allergeni[], allergeni_auto[]
pezzi_ricetta_base, ricetta_base_id, ricetta_base_nome
nutrizionale: {kcal, kj, grassi, saturi, carboidrati, zuccheri, fibre, proteine, sale}  ← aggiunto v56
updated_at, created_at
```

### `lotti`
```
id, fornitore, numero_lotto, data_produzione, data_scadenza
ingredienti_dettaglio[], allergeni[], allergeni_testo
lotti_componenti[]         → [{lotto_id, numero_lotto, nome, quantita_usata, unita}]  ← aggiunto v57
frigo_numero, stato, consumato, data_consumo, quantita, unita_misura
lotti_scalati[], created_at
costo_pezzo                 → se il lotto viene da produzione (usato per valore_economico)
posizione                   → {tipo (frigo|congelatore|abbattitore|banco|magazzino), numero,
                                nome, reparto, operatore_id, operatore_nome, quantita,
                                data_ora}  ← aggiunto v67 (Tranche 0). Costruito da `frigo_numero`
                                dove possibile; frigo_numero RESTA scritto in parallelo per
                                retrocompatibilità con tutto il codice esistente — non fidarsi
                                SOLO di `posizione`, molti lotti vecchi non ce l'hanno.
scadenza_abbattuto, mesi_abbattuto     → scadenza calcolata per il ramo abbattitore negativo
data_scadenza_pre_congelamento, congelato_il  → ← v67, scritti da POST /lotti/{id}/congela
motivo_smaltimento, data_smaltimento          → ← v67, scritti da PATCH /lotti/{id}/smalti
abbattimento                 → {inizio, fine, ore_effettive, esito}, solo lotti pesce
NON persistiti (calcolati SOLO in risposta, mai salvati su DB):
  stato_scadenza  → {colore (verde|giallo|arancione|rosso|grigio), label, giorni_alla_scadenza}
  valore_economico → costo_pezzo × quantita, None se costo_pezzo assente (mai inventato)
  (vedi backend/servizi/lotto_arricchimento_service.py — unico punto di calcolo)
```

### `movimenti_lotto`  ← nuova collection v67 (Tranche 0)
```
id, lotto_id, numero_lotto, tipo_evento (creazione|spostamento|uso|banco|
  recupero|congelamento|smaltimento|spostamento_massivo_anomalia|
  rientro_invenduto|recall)
posizione_da, posizione_a    → stesso shape di lotti.posizione, o null
quantita, operatore_id, operatore_nome, motivo
azione_correttiva_haccp      → stringa o null
documento_collegato          → {tipo: "anomalia"|"richiamo"|"vendita_banco", id} o null
data_ora
```
Unico punto di scrittura: `backend/servizi/movimenti_lotto_service.py::registra_movimento()`.
Mai scrivere direttamente su questa collection da un router.

### `produzione_consigliata_decisioni`  ← nuova collection v67 (Tranche 5)
```
id, data (YYYY-MM-DD, la data TARGET della produzione, non oggi)
prodotto (= ricetta_nome/prodotto_nome)
quantita_consigliata, quantita_decisa (null se stato=ignorato)
stato (accettato|modificato|ignorato)
operatore_nome, decisa_il
```
Upsert su (data, prodotto): un solo stato attivo per prodotto/giorno.

### `richiami_eseguiti`  ← nuova collection v67 (registro richiami, seguito Tranche 3)
```
id, ingrediente, filtri (stessi filtri di /lotti/recall/cerca)
lotti_coinvolti[]  → [{id, numero_lotto, prodotto, quantita, frigo_numero}] (snapshot al momento)
n_lotti, motivo, operatore_id, operatore_nome
stato (aperto|concluso), azione_correttiva
data_ora_apertura, data_ora_chiusura (null finché aperto)
```
Diversa da `lotti/recall/cerca` (solo ricerca, non persiste nulla): questa
collection è la registrazione FORMALE che un richiamo è stato eseguito.
Ogni lotto coinvolto riceve anche un evento `recall` in `movimenti_lotto`.

### `lotti_fornitori`
```
id, fornitore, prodotto_nome (NON prodotto!), prodotto_nome_norm
lotto_id_fornitore (NON lotto_id!), tipo_tracciabilita
data_scadenza, giorni_alla_scadenza, scaduto
quantita_originale, quantita_acquistata, quantita_disponibile
unita_misura, prezzo_unitario, fattura_ref, data_fattura
esaurito (bool), created_at
```

### `anomalie`
```
id (UUID str), data_segnalazione (YYYY-MM-DD per doc v55+, dd/mm/yyyy per vecchi)
attrezzatura, categoria, tipo, descrizione
stato (valori: "Aperta", "In corso", "Risolta", "Chiusa")
operatore_segnalazione, azione_correttiva, data_risoluzione, operatore_risoluzione
note, priorita (valori: "Alta", "Media", "Bassa" — case-sensitive!)
created_at, updated_at
```
⚠️ Check supervisore usa `stato nin ["Risolta","Chiusa","risolta","chiusa"]` (lowercase incluso per retrocompatibilità)

### `fatture`
```
id, fornitore, numero_fattura (può essere ""), data_fattura (ISO)
piva, importo_totale
prodotti[]: [{descrizione, codice, quantita, unita, prezzo_unitario, iva, totale, lotto, scadenza}]
xml_raw, created_at
```
⚠️ Dedup PEC: salta se `numero_fattura == ""` (v55 fix)

### `fornitori`
```
nome (chiave!), stato, escluso (bool), in_attesa (bool)
piva, indirizzo, telefono, email, note
num_fatture, ultima_fattura, first_seen, updated_at
stato_qualifica
```

### `prodotti_vendita`
```
id, nome, categoria, descrizione
ricetta_id (FK → ricette.id)
prezzo_vendita, costo_produzione, margine_percentuale, margine_euro
iva, prezzo_ivato, attivo, allergeni[]
immagine_url, acquaviva_id, codice_prodotto
pezzi_cartone, pezzi_per_ricetta, peso_pezzo_g
visibile_tablet (bool), visibile_ricette (bool)
fonte, fornitore, stagionale, stagione_note
created_at, updated_at
```

### `produzioni`
```
id, data (ISO), data_iso (ISO), ricetta_id, ricetta_nome
pezzi (int), moltiplicatore (float, default 1.0)
costo_totale, costo_pezzo
numero_lotto, lotti_fornitori_scalati[]
created_at
```

### `dizionario_prodotti`
```
id, nome_normalizzato, nome_originale, fornitore, data_fattura
peso_confezione, unita_confezione
prezzo_confezione, prezzo_kg
quantita_disponibile_kg, quantita_totale_kg, quantita_usata_kg
ultimo_aggiornamento
aliases[]       ← nomi commerciali da fatture (lowercase, auto-popolati a ogni import XML)
nome_canonico   ← nome normalizzato AI (propagato da nome_mapping.nome_canc)
nome_display    ← campo calcolato in risposta API (= nome_canonico se esiste, altrimenti nome_normalizzato)
```

---

## ENDPOINT CRITICI — PATH ESATTI

```
# LOTTI PRODUZIONE
GET  /api/lotti                                    → lista (stato/consumato/data_consumo normalizzati)
POST /api/registra-produzione-lotto?...&lotti_componenti_json=[]  → con tracciabilità componenti  ← v57
GET  /api/lotti/recall/cerca?ingrediente=X         → recall (param: ingrediente, NON q)
DELETE /api/lotti/{id}                             → elimina lotto

# RICETTE & FOOD COST
GET  /api/ricette                                  → lista 86 ricette
GET  /api/food-cost/calcola/{id}                   → calcola food cost ricetta
POST /api/food-cost/aggiorna-ingredienti-ricetta   → salva ingredienti_dettaglio
POST /api/food-cost/aggiorna-allergeni-ricetta     → salva allergeni + nutrizionale
POST /api/food-cost/calcola-nutrizionale/{id}      → calcola USDA → salva ricette.nutrizionale
GET  /api/food-cost/nutrizionale/{id}              → legge valori nutrizionali salvati
GET  /api/food-cost/registro-allergeni             → matrice allergeni × ricette
POST /api/food-cost/salva-porzioni-ricetta?ricetta_id=X&porzioni_base=N
PUT  /api/ricette/{id}/prezzo-vendita?prezzo=X     → aggiorna prezzo vendita
GET  /api/ricette/{id}/bom?porzioni=N              → BOM esploso (ingredienti_esplosi[], struttura[], e_composita)  ← v57
PATCH /api/ricette/{id}                            → aggiorna campi parziali: componenti, nome, porzioni, prezzo_vendita  ← v57

# FATTURE & PEC
GET  /api/fatture                                  → lista fatture
POST /api/fatture/importa-xml                      → importa XML manuale (NON /api/importa-xml)
GET  /api/fatture/{id}/visualizza                  → HTML fattura (NON /api/fattura/{id})
POST /api/pec/import?only_unread=false&force_reimport=true  → import PEC (force_reimport: ignora dedup)
GET  /api/pec/status                               → stato connessione PEC
GET  /api/pec/anteprima?max_messages=20            → anteprima email (NON /api/pec/preview)

# PRODOTTI VENDITA
GET  /api/prodotti-vendita/                        → catalogo 449 prodotti
POST /api/prodotti-vendita/sync-da-ricette         → sync costi (NON /sync)
PUT  /api/prodotti-vendita/{id}/prezzo             → aggiorna prezzo

# ANOMALIE
GET  /api/anomalie/lista                           → lista (NON GET /api/anomalie)
POST /api/anomalie/registra                        → registra (alias di POST /api/anomalie/)
PUT  /api/anomalie/{id}                            → aggiorna stato/azione

# SUPERVISOR
GET  /api/supervisor/stato                         → controlli giornalieri + alert
GET  /api/supervisor/sommario                      → riepilogo

# LOTTI FORNITORI
GET  /api/lotti-fornitori?limit=N                  → con limit per evitare payload overload

# ALTRI
GET  /api/attrezzature/                            → frigo + congelatori (dinamici)
POST /api/fornitori/{nome}/auto-qualifica          → auto-qualifica fornitore

# TRACCIABILITÀ LOTTI v67 (7 tranche 04/07/2026 — vedi STATO.md per il dettaglio di ogni tranche)
GET  /api/lotti/cosa-usare-oggi                    → lotti attivi ordinati per semaforo scadenza + valore economico
GET  /api/lotti/{id}/scheda-completa               → gemello digitale: lotto + cronologia + ricetta + fornitori + abbattimento
GET  /api/lotti/{id}/movimenti                     → registro movimenti grezzo del lotto
POST /api/lotti/{id}/sposta-posizione?tipo=X&numero=X       → sposta un lotto tra posizioni
POST /api/lotti/{id}/congela?numero=X                       → sposta in congelatore + ricalcola scadenza da abbattitore
POST /api/lotti/{id}/recupera?quantita=X                    → recupero per riuso in nuova produzione
POST /api/anomalie/{id}/sposta-lotti-massivo                → sposta in blocco i lotti di un'attrezzatura in anomalia
GET  /api/anomalie/{id}/lotti-attuali                        → query LIVE (non lo snapshot lotti_coinvolti, spesso superato)
POST /api/lotti/recall/esegui                                → registra FORMALMENTE un richiamo eseguito (≠ /recall/cerca, solo ricerca)
GET  /api/lotti/recall/eseguiti                               → registro richiami eseguiti
PATCH /api/lotti/recall/eseguiti/{id}/concludi?azione_correttiva=X
GET  /api/dashboard-economica/riepilogo?mese=YYYY-MM         → valore lotti, spreco, margini, fornitori
GET  /api/produzione-consigliata?data=YYYY-MM-DD             → suggerimenti (default: domani)
POST /api/produzione-consigliata/decisione                   → accetta/modifica/ignora un suggerimento
GET  /api/ricerca-globale?q=X                                 → lotti+ricette+fornitori+materie prime+attrezzature
```

---

## USDA NUTRITIONAL DB

File: `/app/backend/data/usda_nutrizionale.json`
- ~70 ingredienti comuni italiani (farine, grassi, latticini, uova, zuccheri, cioccolato, frutta secca, etc.)
- Struttura: `{nome, aliases[], per_100g: {kcal, kj, grassi, saturi, carboidrati, zuccheri, fibre, proteine, sale}}`
- Matching: alias esatto → alias parziale (case-insensitive, senza accenti)
- Campo unita riconosciute: g, gr, grammi, kg, chili, ml, cl, dl, l, lt, litri
- Unità non-peso (pz, n., cucchiai) → escluse dal calcolo nutrizionale
- Copertura tipica: 40-80% (brand-name ingredienti come "bonduelle" non trovati)

---

## BUG NOTI / GOTCHA

| Campo | Problema | Fix |
|-------|---------|-----|
| `ingredienti_dettaglio[].unita_misura` | Chiamato `unita` nel vecchio codice frontend | Usare `unita_misura` |
| `lotti.data_scadenza` | Formato `dd/mm/yyyy` | `parseData()` nel frontend |
| `anomalie.data_segnalazione` | Mix vecchi `dd/mm/yyyy` + nuovi ISO | Filtro per anno usa regex `^YYYY` |
| `fornitori` | Nessun campo `id`, chiave = `nome` | Query sempre per `nome` |
| `fatture.numero_fattura` | Può essere `""` | Non usare come dedup key se vuoto |
| `produzioni.moltiplicatore` | Default mancava → era None | Ora default=1.0 lato backend |
| `anomalie.lotti_coinvolti` (snapshot) | Regex sui primi 6 caratteri del nome attrezzatura (`attrezzatura[:6]`) in `registra_anomalia` — "Frigorifero N°2" e "Frigorifero N°9" si confondono (stesso prefisso "Frigor") | NON corretto nello snapshot storico (fuori scopo, dati passati). Il nuovo `GET /anomalie/{id}/lotti-attuali` (v67) usa match ESATTO sul nome intero: usare SEMPRE quello per azioni reali (es. spostamento massivo), mai fidarsi dello snapshot per operazioni, solo per un conteggio indicativo al momento della segnalazione |
| `lotti.posizione` vs `frigo_numero` | Due campi paralleli per lo stesso concetto (retrocompatibilità v67) | Scrivere SEMPRE entrambi quando si sposta un lotto (vedi `servizi/movimenti_lotto_service.py::costruisci_posizione`); il codice vecchio legge solo `frigo_numero`, il nuovo legge `posizione` |

---

## ENDPOINT STAMPA (v62)

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/stampa/lotto/{id_o_numero_lotto}` | HTML POS 80mm per `window.print()` — allergeni, ingredienti, tracciabilità. Unica fonte di verità. |

**File:** `/app/backend/routers/stampa.py`
Logica centralizzata: `ALLERGENI_KW`, `rileva_allergeni()`, `ordina_ingredienti()`, `build_pos_html()`

---

*Generato: Aprile 2026 v58 — integrare con PRD.md sezione 4 per schema completo*
*Aggiornato: v64 — Passo 2 (aliases[] + FIFO step-0) e Passo 3 (dropdown dedup per nome_display)*
*Aggiornato: v65 — Fix 1 (import-listino-pdf Acquaviva, bulk update), Fix 2 (ModalAlpha backdrop+close), Fix 3 (recall cliccabile), Fix 4 (manuale HACCP filtri date/sezioni), Fix 5 (processa-tutti-aliases endpoint)*
*Aggiornato: v66 — Fix 1 (PEC: rimosso Opzioni Import, 2 pulsanti, no File Non-Fattura), Fix 2 (Tablet banco no stampa), Fix 3 (xml_helpers Qt regex, fatture.py OK), Fix 4 (BulkPrezzi: tutti prodotti, sort, divider, state update), Fix 5 (tooltip Fornitori Esclusi)*
*Aggiornato: v67 (04/07/2026) — 7 tranche tracciabilità lotti (Scadenza intelligente, Produzione consigliata, Intelligenza operativa frigoriferi, Dashboard economica, Cronologia completa lotto, Miglioramenti UI, Gemello digitale del lotto) + registro richiami eseguiti. Nuove collection: `movimenti_lotto`, `produzione_consigliata_decisioni`, `richiami_eseguiti`. Nuovo campo `lotti.posizione` (parallelo a `frigo_numero`, non sostitutivo). Dettaglio completo di ogni tranche in STATO.md.*

## Struttura frontend dopo la fase 2 (24/07/2026)
- config/navigation.js — PRIMARY_TABS (5), SECONDARY_TABS (con `section`), HACCP_TABS, VALID_TABS
- config/pageMeta.js — PAGE_NAMES (document.title/breadcrumb), PAGE_META (PageHeader), TAB_HEADER_PROPRIO
- config/permissions.js — ADMIN_TABS, puoAprireTab(tabId, admin) — SOLO UX; la sicurezza vera è require_admin nel backend
- hooks/useAppNavigation.js — hash routing, alias #ricettario/#food_cost→ricette, guardia admin su Indietro
- router/AppRouter.jsx — kiosk (#tablet/…) vs app; router/pages.jsx — registro id→componente (unico switch)
- layouts/AppLayout.jsx (header+nav+cornice) · layouts/KioskLayout.jsx (sessioni PIN tablet)
- components/haccp/backoffice/FormRicetta.jsx — form ricetta estratto (default export)
- components/haccp/fornitori/FattureList.jsx — lista fatture fornitore estratta
- utils/conferma.js — conferma() E chiediTesto() (sostituto di window.prompt); ConfermaHost gestisce entrambi
- utils/apiError.js — traduce anche timeout/rete/401/403/5xx in messaggi comprensibili
- hooks/useInvioSingolo.js — anti doppio-invio standard per i form nuovi
- GOTCHA: la nav bar è nascosta da App.css (navigazione = card Home); i 5 tab primari alimentano titoli e config
- Backend: require_admin ora su 29 endpoint distruttivi (vedi memory/AUDIT_SICUREZZA.md) — un endpoint distruttivo NUOVO deve SEMPRE dichiararlo (test anti-regressione in tests/test_auth_permessi.py)
- Ricerca globale: /api/ricerca-globale copre anche fatture/ordini/produzioni; dettaglio lotto: /api/ricerca-globale/lotto/{id}
