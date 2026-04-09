# DIARIO.md — Ceraldi ERP gestionale2

## Chat 4 — Fix bug, 2 tab mancanti, push backend

### Fix applicati
- App.jsx: route mancanti tributi, alert-fiscali, fornitori, f24-privati
- TopNav.jsx: import duplicati, Building2 mancante
- tributi.py: import PRIVATI_CF/CF_AZIENDA mancante
- main.py: prefix doppio su tributi e f24_privati

---

## Chat 5 — 3 pagine HACCP nel gestionale2

### Pagine create e pushate
Le 3 pagine leggono le API di `ceraldiapp.it` (repo tracciabilita).
Prima di costruire: letti tutti e 4 i router backend (temperature_positive, temperature_negative, sanificazione, disinfestazione).

**frontend/src/pages/TemperatureHACCP.jsx**
- Tab interno: Frigoriferi (+) e Congelatori (−)
- Chiama GET `/temperature-positive/scheda/{anno}/{n}` e `/temperature-negative/scheda/{anno}/{n}` per tutti i 12 apparecchi
- Griglia: giorni come righe, apparecchi come colonne
- Legge stati speciali: is_chiuso 🚫, is_manutenzione 🔧, is_non_usato ⏸
- Badge "fuori range" se temp > max o < min
- CSS inline con design system utils.js

**frontend/src/pages/SanificazioneHACCP.jsx**
- Tab "Attrezzature": griglia mensile toggle X, pulsanti "marca tutto giorno N" → POST `/giorno-completo`, salva bulk → PUT `/scheda/{anno}/{mese}`
- Tab "Apparecchi Refrigeranti": read-only, griglia frigo+congelatori con ✓/✗ per sanificazioni ogni 7-10 giorni

**frontend/src/pages/DisinfestazioneHACCP.jsx**
- Intervento mensile: card + pulsante "Registra/Modifica" → POST `/registra-intervento/{anno}/{mese}`
- Cards frigoriferi/congelatori cliccabili → modal → POST `/registra-monitoraggio/{anno}/{mese}`
- Riepilogo annuale: griglia 12 mesi, click mese per navigare
- Ditta: ANTHIRAT CONTROL S.R.L., giorno fisso 15

### Modifiche a file esistenti
- App.jsx: aggiunte 3 route `/haccp/temperature`, `/haccp/sanificazione`, `/haccp/disinfestazione`
- TopNav.jsx: aggiunti 3 link 🌡️ Temp, ✨ Sanif., 🐀 Disinfest. con icone Thermometer, Sparkles, Bug

### Commit pushati (Chat 5)
- 63030da — feat: aggiunte 3 route HACCP in App.jsx
- 9ee8358 — feat: aggiunti 3 link HACCP in TopNav
- 66ec17d — feat: TemperatureHACCP.jsx
- 1d12ece — feat: SanificazioneHACCP.jsx
- 7648ce3 — feat: DisinfestazioneHACCP.jsx

---

## Chat 5 — continua: DashboardHACCP

### Pagina aggiunta
**frontend/src/pages/DashboardHACCP.jsx**
Adattamento fedele di DashboardView.jsx del repo tracciabilita.

**API chiamate (tutte su ceraldiapp.it):**
- GET /produzioni/per-oggi → pezziProdPast, pezziProdCucina per reparto
- GET /vendita-banco/oggi → aperte/chiuse, venduti/invenduti per reparto
- GET /lotti?limit=300 → filtra scadenza ≤ 7 giorni, max 10 lotti
- GET /acquaviva/magazzino-congelatore → saldo congelatore semilavorati Vandemoortele
- GET /chiusure/giorno-non-produttivo/oggi → stato toggle produttivo/riposo
- POST /chiusure/giorno-non-produttivo/oggi → setta stato
- PATCH /lotti/{id}/consuma → marca lotto come consumato (con confirm window)

**Funzionalità:**
- Toggle "Giorno Produttivo / Giorno di Riposo"
- 3 link rapidi tablet (rosticceria, pasticceria, vendita) → ceraldiapp.it
- Alert lotti in scadenza prossimi 7 giorni con bottone consuma
- Griglia 3 colonne × 6 righe (prodotti, al banco, in frigo, venduti, incasso pot., costo invenduto)
- Popup magazzino semilavorati (entrate/uscite/saldo Vandemoortele)
- Dettaglio banco espandibile al click su riga venduti
- KPI archivio (link a ceraldiapp.it)
- Lista produzioni di oggi

**Modifiche file esistenti:**
- App.jsx: route /haccp/dashboard
- TopNav.jsx: link 📊 Dashboard + import LayoutDashboard

---

## Chat 6 — 2026-04-08

### Nuovi router backend

**app/routers/omaggi_acquaviva.py** — GET /api/omaggi-acquaviva
- Calcola omaggi Acquaviva (1 ogni N cartoni, default 10) con progressivo cumulativo tra ordini
- Usa fatture_passive: campo fornitore_denominazione, linee[].prezzo_unitario=0 = omaggi
- Estrae pezzi/cartone dalla descrizione (regex 35G 4.95KG o 6X80G)

**app/routers/ordini.py** — CRUD ordini fornitori
- GET /api/ordini/prezzi/{nome_prodotto} — comparazione prezzi da fatture_passive (fuzzy matching)
- POST/GET/PUT/DELETE /api/ordini — collection ordini_ceraldi
- GET /api/ordini/{id}/testo-invio?fornitore=X — genera testo email + WhatsApp

### Nuove pagine frontend

- OrdiniFornitore.jsx → /ordini — catalogo ceraldiapp.it + CRUD locale
- ScontiMerce.jsx → /sconti-merce — ceraldiapp.it + tab Omaggi locale
- TemperatureHACCP.jsx → /haccp/temperature
- SanificazioneHACCP.jsx → /haccp/sanificazione
- DisinfestazioneHACCP.jsx → /haccp/disinfestazione
- DashboardHACCP.jsx → /haccp/dashboard

### Audit completo — 7 bug fixati

1. [CRITICO] f24.py /alert-duplicati — NameError includi_scartati: aggiunto Query(False)
2. [CRITICO] ordini.py route conflict — verificato: /prezzi/{nome} gia prima di /{id} OK
3. [MEDIO]   fatture.py upsert fornitori — struttura flat → anagrafica nested (anagrafica.piva)
4. [MEDIO]   fornitori.py import-xml — numero_fattura→numero, piva_fornitore→fornitore_piva
5. [BASSO]   fornitori.py /pagamento — query fornitore_id (inesistente) → fornitore_piva
6. [BASSO]   alert_fiscali.py — db.get_collection() → db['avvisi_bonari']
7. [BASSO]   distinte.py — riconcilia su iban → iban_cedolino con fallback

### Campi reali confermati

fatture_passive: fornitore_denominazione, fornitore_piva, numero, data, anno,
  importo_totale, imponibile, iva, causale, linee[], riepilogo_iva, pagamenti,
  dedup_key, stato, source.
  linee[]: descrizione, quantita, unita_misura, prezzo_unitario, prezzo_totale, aliquota_iva

fornitori: azienda_id, anagrafica.{ragione_sociale,piva,codice_fiscale,pec,regime_fiscale,sede},
  schede_tecniche, prodotti[], storico_prezzi[], pagamento, stato

dipendenti: codice_fiscale, nome, cognome, stato, iban_cedolino (NON iban),
  paga_base, livello, ferie_saldo_gg, permessi_saldo_ore,
  progressivi.{anno}.{imp_inps,imp_irpef,irpef_pagata,imp_inail},
  tfr.{anno}.{fondo_31_12,quota_anno,rivalutazione}, pignoramenti[]

### TODO prossima chat
- Portare rinomina inline colonne frigo/congelatore (da TemperaturePositiveView originale)
- Testare omaggi Acquaviva con fatture reali
- Verificare riconciliazione cedolini con estratto conto

---

## Chat 6 — continua: Audit completo codebase + OrdiniFornitore + ScontiMerce Omaggi

### Nuove pagine (create in Chat 6)

**frontend/src/pages/ScontiMerce.jsx** → /sconti-merce
- Viste: Lista sconti, Mensile, Per Fornitore, Omaggi AQV
- API ceraldiapp.it: /sconti-merce/* (lista, riepilogo, importa, valorizza)
- Tab Omaggi: chiama /api/omaggi-acquaviva (backend locale gestionale2)
- Filtro fornitori configurabile via localStorage (default: Acquaviva, Perfetti, Eureka, Kimbo)

**frontend/src/pages/OrdiniFornitore.jsx** → /ordini
- Vista Operatore: catalogo da ceraldiapp.it/api/ordini-fornitori/prodotti-suggeriti
- Comparazione prezzi: /api/ordini/prezzi/{nome} (gestionale2, fuzzy match fatture_passive)
- Modal prezzi: mostra tutti i fornitori ordinati per prezzo, marca il migliore
- Vista Admin: lista ordini con filtro stato, espansione per fornitore, approva/invia/completato
- Modal invio: genera testo email + WhatsApp, pulsanti "Apri in Mail" e "Apri WhatsApp"
- CRUD: collection ordini_ceraldi (non ordini_fornitori di ceraldiapp.it)

### Nuovi router backend (Chat 6)

**app/routers/omaggi_acquaviva.py**
- Endpoint: GET /api/omaggi-acquaviva?fornitore=acquaviva&soglia=10
- Query su fatture_passive con campo CORRETTO: fornitore_denominazione
- Righe prezzo=0 = omaggi; calcola pezzi/cartone da descrizione (regex)
- Progressivo cumulativo tra ordini: cartoni si accumulano cross-fattura
- Valore omaggio = pezzi x prezzo_pezzo_rif (da riga normale stessa fattura)

**app/routers/ordini.py**
- GET /api/ordini/prezzi/{nome_prodotto}: carica ultime 300 fatture, raggruppa per fornitore
  (max 4 fatture recenti ciascuno), fuzzy match parole chiave (score >= 0.4)
- POST/GET/PUT/DELETE /api/ordini → collection ordini_ceraldi
- GET /api/ordini/{id}/testo-invio → cerca email in fornitori.anagrafica.email/.pec
- Ordine route OK: /prezzi/{nome} dichiarato PRIMA di /{ordine_id} → no conflict

### 7 bug fixati (audit codebase completo)

| # | Gravita | File | Bug | Fix |
|---|---------|------|-----|-----|
| 1 | CRITICO | f24.py | /alert-duplicati crashava (NameError includi_scartati) | Aggiunto includi_scartati: bool = Query(False) |
| 2 | CRITICO | ordini.py | Route conflict /prezzi/{nome} vs /{id} | Verificato: ordine gia corretto |
| 3 | MEDIO | fatture.py | Upsert fornitori struttura flat (denominazione, partita_iva) | Riscritto con anagrafica.piva, anagrafica.ragione_sociale |
| 4 | MEDIO | fornitori.py | import-xml scriveva numero_fattura e piva_fornitore | Corretti in numero, fornitore_piva, fornitore_denominazione |
| 5 | BASSO | fornitori.py | /pagamento query su fornitore_id (inesistente in fatture_passive) | Usa fornitore_piva via lookup anagrafica.piva |
| 6 | BASSO | alert_fiscali.py | db.get_collection() non e API Motor valida | Cambiato in db["avvisi_bonari"] |
| 7 | BASSO | distinte.py | Riconcilia dipendenti su iban (non esiste) | Usa iban_cedolino con fallback su iban |

### Audit 25 endpoint ceraldiapp.it — tutti verificati

Verificato che tutti gli endpoint chiamati dalle 6 pagine HACCP+sconti esistono
realmente nel repo tracciabilita (25/25 OK):
- /temperature-positive|negative/scheda/{anno}/{n}
- /sanificazione/scheda/{anno}/{mese}, /attrezzature, /giorno-completo, /apparecchi/{anno}, /export-pdf
- /haccp/popola-sanificazione
- /disinfestazione/scheda-annuale, /registra-intervento, /registra-monitoraggio, /export-pdf
- /produzioni/per-oggi, /vendita-banco/oggi, /lotti, /acquaviva/magazzino-congelatore
- /chiusure/giorno-non-produttivo/oggi, /lotti/{id}/consuma
- /sconti-merce/* (lista, riepilogo/mensile, riepilogo/fornitori, prodotti-fornitore, importa, valorizza)
- /ordini-fornitori/prodotti-suggeriti

### Audit campi frontend (6 pagine create questa sessione)
Nessun campo MongoDB sbagliato trovato. Il campo "numero_fattura" in ScontiMerce.jsx
e omaggi_acquaviva.py e solo il nome nel JSON di risposta — il DB viene letto con fat.get("numero") (corretto).

### Rotte App.jsx e TopNav.jsx aggiornate
- /ordini → OrdiniFornitore (icona ShoppingBag)
- /sconti-merce → ScontiMerce (icona Tag)
- /haccp/dashboard → DashboardHACCP (icona LayoutDashboard)
- /haccp/temperature → TemperatureHACCP (icona Thermometer)
- /haccp/sanificazione → SanificazioneHACCP (icona Sparkles)
- /haccp/disinfestazione → DisinfestazioneHACCP (icona Bug)

### main.py — router registrati al 2026-04-08
health, import_hub, mittenti, dipendenti, fatture, cedolini,
estratto_conto, f24, f24_privati, corrispettivi, distinte, verbali,
presenze, quietanze, alert_fiscali, tributi, learning, fornitori,
omaggi_acquaviva, ordini

### TODO prossima chat (Chat 7)
- Portare rinomina inline colonne frigo/congelatore da TemperaturePositiveView originale
- Testare omaggi Acquaviva con fatture reali (ceraldiapp.it attualmente 500)
- Pagina tablet Cucina: operatori rosticceria/pasticceria → ceraldiapp.it/api/tablet/{reparto}
- Verificare riconciliazione cedolini con estratto conto (categoria "stipendio")

---

## Chat 7 — 2026-04-09

### Stato sistema al riavvio chat

**Questa chat è la Chat 7.** La prossima sarà Chat 8.

### Variabili di sistema complete (snapshot 2026-04-09)

#### Infrastruttura
- **Repo:** `github.com/ceraldicontabilita/gestionale2` branch `main`
- **Token GitHub:** `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`
- **Backend:** FastAPI + Motor, porta `:8001`, prefix `/api/...`
- **Frontend:** React 18 + Vite, porta `:3000`
- **Process manager:** Supervisor
- **DB:** MongoDB Atlas, cluster `cluster0.vofh7iz`, db=`Gestionale`, utente `Ceraldidatabase`
- **Supabase:** progetto EU `tvnrymgeyilhpkawhgjy`

#### Collections MongoDB
| Collection | Note |
|---|---|
| `dipendenti` | MAI "employees" |
| `fornitori` | MAI "suppliers" |
| `cedolini` | upsert per dipendente_id+anno+mese |
| `fatture_passive` | campi: fornitore_denominazione, fornitore_piva, numero, data, anno, importo_totale, linee[] |
| `ordini_ceraldi` | ordini interni gestionale2 |
| `tributi_privati` | Michele + Antonietta (familiari), MAI in contabilità aziendale |
| `lotti`, `lotti_fornitori`, `produzioni`, `ricette`, `dizionario_prodotti`, `ricezioni_merce`, `materie_prime` | Tracciabilità ceraldiapp.it |

#### Campi critici MongoDB
```
fatture_passive:
  fornitore_denominazione (NON cedente.denominazione)
  fornitore_piva (NON piva_fornitore)
  numero (NON numero_fattura)
  linee[].prezzo_unitario, linee[].unita_misura

dipendenti:
  iban_cedolino (NON iban)
  paga_base, livello, ferie_saldo_gg, permessi_saldo_ore
  progressivi.{anno}.{imp_inps,imp_irpef,irpef_pagata,imp_inail}
  tfr.{anno}.{fondo_31_12,quota_anno,rivalutazione}
  pignoramenti[]

fornitori:
  anagrafica.ragione_sociale
  anagrafica.piva (NON denominazione/partita_iva a livello flat)
  anagrafica.email, anagrafica.pec
```

#### Router backend attivi (main.py al 2026-04-08)
`health, import_hub, mittenti, dipendenti, fatture, cedolini,
estratto_conto, f24, f24_privati, corrispettivi, distinte, verbali,
presenze, quietanze, alert_fiscali, tributi, learning, fornitori,
omaggi_acquaviva, ordini`

#### Prefix API
`/api/dipendenti`, `/api/cedolini`, `/api/giustificativi`,
`/api/archivio-bonifici`, `/api/estratto-conto-movimenti`,
`/api/prima-nota`, `/api/f24`, `/api/attendance`, `/api/cucina`, `/api/tr`

#### Route frontend attive
`/dipendenti /fatture /cedolini /estratto-conto /f24 /f24-privati
/corrispettivi /tributi /fornitori /alert-fiscali /verbali /distinte
/presenze /sconti-merce /ordini
/haccp/dashboard /haccp/temperature /haccp/sanificazione /haccp/disinfestazione`

#### Design system
- File: `frontend/src/lib/utils.js`
- Font: Plus Jakarta Sans
- Colori: primary=#5D29C7, bg=#F0F4FA, card=#FFFFFF, sidebar=#1E1B4B
- success=#00B884, warning=#FF9800, danger=#F44336, info=#2196F3
- Card: radius=16, shadow viola
- Btn primary: gradiente viola
- Table th: uppercase 11px, Badge: radius=20
- MAI Tailwind, MAI Shadcn, MAI hardcoded

#### Regole di sviluppo assolute
- IMAP sempre in `asyncio.to_thread()`
- CSS inline tramite `lib/utils.js`
- Icone: solo `lucide-react`
- `SecondaryTabs`: link sempre a route reali, mai `Navigate` redirect
- Tab interni: `useState`, non `navigate()`
- Nessun file alias o wrapper — correggere sempre l'import nel file originale

#### PEC Aruba
- IMAP: `imaps.pec.aruba.it` porta 993, user `fatturazioneceraldi@pec.it`
- SMTP: `smtps.pec.aruba.it` porta 465
- Bug noto fixato: `aruba_automation.py` riga 312 aveva `imap.gmail.com` → corretto in `imaps.pec.aruba.it`

#### Gmail
- Account: `ceraldigroupsrl@gmail.com`
- SMTP porta 587 con TLS
- Da Gmail arrivano: SDI (@pec.fatturapa.it), cedolini Ferrantini+Marotta, PagoPA Napoli, INPS, INAIL, PayPal
- I corrispettivi arrivano SOLO via import manuale XML (dal registratore telematico)

#### Persone speciali
- **CERALDI Michele** (CF CRLMHL50R01F352F) → `tributi_privati`, MAI contabilità aziendale
- **Ceraldi Antonietta** (CF CRLNNT75M55F352C) → `tributi_privati`, MAI contabilità aziendale

#### API esterna ceraldiapp.it
HACCP e sconti usano ceraldiapp.it come API esterna. Ordini: catalogo da ceraldiapp.it, CRUD e prezzi da gestionale2 locale.

#### Modulo Tracciabilità (`/api/tr`)
Flusso: fattura XML → `lotti_fornitori` → `registra-produzione-lotto` (FIFO per scadenza) → scala qty → `db.lotti` + `db.produzioni`.
Registro HACCP: `/api/tr/registro-lotti/{anno}/{mese}`

### TODO Chat 7
1. Portare rinomina inline colonne frigo/congelatore da TemperaturePositiveView originale in TemperatureHACCP.jsx
2. Pagina tablet Cucina: GET ceraldiapp.it/api/tablet/{reparto} per operatori rosticceria/pasticceria
3. Testare omaggi Acquaviva con fatture reali
4. Verificare riconciliazione cedolini (categoria "stipendio" in estratto conto)

