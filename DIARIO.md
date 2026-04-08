# Ceraldi ERP — Diario di sviluppo
> Aggiornato automaticamente ad ogni cambio chat Claude.
> Questo file è la memoria permanente del progetto — leggilo all'inizio di ogni nuova chat.

---

## Identità progetto

| Campo | Valore |
|-------|--------|
| Azienda | Ceraldi Group SRL |
| P.IVA | 04523831214 |
| AZIENDA_ID MongoDB | b0295759-35ce-4b34-a6b4-f01b883234ad |
| Repo | github.com/ceraldicontabilita/gestionale2 (branch main) |
| Frontend | React 18 + Vite — porta :3000 |
| Backend | FastAPI + Motor — porta :8001 |
| Database | MongoDB Atlas — cluster0.vofh7iz — db=Gestionale |
| PEC | fatturazioneceraldi@pec.it (Aruba) |
| Gmail | ceraldigroupsrl@gmail.com |
| Supabase | tvnrymgeyilhpkawhgjy (EU) |

---

## Persone

| Nome | CF | Ruolo | Dove nel gestionale |
|------|----|-------|---------------------|
| Ceraldi Group SRL | 04523831214 | Azienda | tutto il gestionale |
| Ceraldi Michele | CRLMHL50R01F352F | **Familiare** | tributi_privati, f24_privati, pagina /privati |
| Ceraldi Antonietta | CRLNNT75M55F352C | **Familiare** | tributi_privati, pagina /privati |

**Regola assoluta:** dati anagrafici familiari solo in MongoDB (collection `privati_anagrafica`) e in `app/privati_config.py`. Mai hardcoded altrove.

---

## Dipendenti attivi

| Nome | Stipendio | IBAN |
|------|-----------|------|
| Capezzuto Alessandro | €1.190 | IT86C0514203419CC1186038905 |
| Dias Mahatelge Kris | €1.190 | IT42K3608105138211526811539 |
| D'Alma Vincenzo | CESSATO | 3 pignoramenti Municipia (bollo BA782XR) €1.466,94 |

Banca aziendale: Banco BPM c/c 00005462 — IBAN IT13X0503403406000000005462

---

## Stack tecnico — regole assolute

- Collection MongoDB: `dipendenti` (MAI "employees"), `fornitori` (MAI "suppliers")
- IMAP sempre in `asyncio.to_thread()`
- CSS inline via `frontend/src/lib/utils.js` — MAI Tailwind, MAI Shadcn
- Icone: solo `lucide-react`
- Tab interni: `useState`, non `navigate()`
- Mai file alias/wrapper — correggere sempre l'import originale
- Dati privati familiari: sempre da `app/privati_config.py`

---

## Design System

File: `frontend/src/lib/utils.js`

```
Font: Plus Jakarta Sans
primary:    #5D29C7   primaryBg: #EDE7FF
bg:         #F0F4FA   card:      #FFFFFF
sidebar:    #1E1B4B   text:      #1A1A2E
border:     #E8ECF0   textMuted: #6B7280
success:    #00B884   successBg: #E6F9F4
warning:    #FF9800   warningBg: #FFF3E0
danger:     #F44336   dangerBg:  #FEECEB
info:       #2196F3   infoBg:    #E3F2FD
```

Card: `borderRadius:16`, shadow viola 7%.
Btn primary: gradiente `#5D29C7→#7C4DDD`, shadow viola.
Table `th`: uppercase 11px. Badge: `borderRadius:20`.

Import sempre: `import { s, colors, shadow, formatEuro, font } from '../lib/utils'`

---

## Moduli costruiti (per chat)

### Chat 1–2 — Fondamenta
- Setup repo, FastAPI, MongoDB Atlas, React 18 + Vite
- Router dipendenti, pignoramenti, seed database
- GitHub Action per deploy

### Chat 3 — Design system + Cedolini + Presenze
- `frontend/src/lib/utils.js` — design system MaterialM (commit 9ed601f)
- Parser PDF Zucchetti cedolini (`app/parsers/cedolino_zucchetti.py`)
- Parser presenze Aut.301 (`app/parsers/presenze_zucchetti.py`)
- `frontend/src/pages/DettaglioDipendente.jsx` — 3 tab: Info / Pignoramenti / Presenze
- `frontend/src/components/TabPresenze.jsx` — calendario mensile + KPI

### Chat 4 — Fiscale + Tributi + Fornitori + Learning Machine

#### Viewer Fatture XML
- XSL AssoSoftware (`app/static/FoglioStileAssoSoftware.xsl`) — foglio stile SDI ufficiale
- Endpoint `GET /api/fatture/{id}/html` — render HTML con xsltproc
- `frontend/src/components/VisFattura.jsx` — drawer slide-in con iframe

#### Modulo F24
- `app/parsers/f24_parser.py` — dizionario completo codici tributo
- `app/routers/f24.py` — upload, lista, scarta (motivo), ripristina, riconcilia, alert duplicati
- `app/routers/f24_privati.py` — F24 per Ceraldi Michele (collection separata)
- `frontend/src/pages/F24.jsx` — tab Lista / Importa / Alert / Scartati

**Codici tributo appresi dai dati reali Ceraldi:**

| Sezione | Codici principali |
|---------|-------------------|
| Erario | 1001, 1012, 1040, 1627, 1631, 1701, 1703, 1704, 1712, 1713, 6001-6012, 6099, 7085, 8904, 8906, 8907, 8947, 8948, 8949, 9001, 9002 |
| INPS | DM10, CXX (80143NAPOLI), RC01, COS (888888888888), GPJA |
| Regioni (05) | 3800, 3801, 3802, 3805, 3813, 3796, 8950 |
| Trib. Locali (F839) | 3847, 3848, 3944 (TARI), TEFA, 8952, 1671 |

Codici tipicamente credito: `{1701, 1703, 1704, 1631, 3796, 3797, 6099, 1671}`

#### Quietanze ADE
- `app/parsers/quietanza_parser.py` — protocollo telematico, tributi, avviso bonario
- `app/routers/quietanze.py` — upload, riconciliazione auto/manuale con F24
- Collection: `quietanze`
- Riconciliazione automatica: saldo ±€0,05 + data vicina

**12 quietanze reali analizzate (01/12/2025):**
- Q1: €5.498,79 — INPS+Erario dic/2024 con compensazioni 1627/1631/1703
- Q2: €1.633,04 — avviso bonario 9001 Codice Atto 05354492513
- Q3: €534,06 — IVA 6001 gen/2025
- Q4: €1.033,92 — IVA lug 6007 ravvedimento (8904+1991)
- Q5: €8.153,50 — INPS+INAIL+IMU gen/2025
- Q6: €838,66 — ritenute 1040+7085+8948
- Q7: €88,23 — ravvedimenti add.reg/com multi-anno + TFR
- Q8: €62,62 — IMU 3848 giu/2023 ravvedimento tardivo
- Q9: €1.891,09 — IRPEF+ravvedimenti+IRAP multi-anno
- Q10: €5.526,19 — INPS RC01+COS feb/2025
- Q11: €15,29 — 1001 nov/2024 quasi interamente compensato con 1631
- Q12: €7.876,27 — INPS+Erario+IMU mar/2025 (Codice B990 nuovo ente)

#### Alert Fiscali
- `app/routers/alert_fiscali.py` — INPS/DURC, ritenute 1001, avvisi bonari, F24 orfani
- `frontend/src/pages/AlertFiscali.jsx` — dashboard 5 KPI + tab per categoria

**Regole normative implementate:**

| Tributo | Scadenza | Sanzione ritardo | Note |
|---------|----------|------------------|------|
| INPS DM10/CXX | 16° mese succ. | TUR (2,9%) entro 120gg, poi +5,5% max 40% | DURC irregolare da giorno 1 |
| Ritenute 1001 | 16° mese succ. | 25% amm. + penale >€150k/anno | Termine penale: 770 (31/10 anno succ.) |
| IVA 6001-6012 | 16° mese succ. | Ravvedimento progressivo | Visto conformità >€5k |
| Avviso bonario 9001 | 30gg dalla notifica | Sanzioni extra se oltre | 20 rate trimestrali |
| Blocco compensazione | — | — | Ruoli scaduti >€50k dal 01/01/2026 |

#### Tributi Locali
- `app/parsers/tari_parser.py` — TARI/IMU Comune Napoli (codice 3944, TEFA, UR1/UR2/UR3 ARERA)
- `app/routers/tributi.py` — upload avvisi, routing auto privato/azienda, scadenze, paga rata
- `frontend/src/pages/TributiPrivati.jsx` — tab Scadenze / Upload / Privati / Azienda
- Collection: `tributi_azienda` (CF 04523831214), `tributi_privati` (altri CF)

**TARI 2025 analizzata — Ceraldi Antonietta:**
- Via Cavallerizza 46, p.T int.010, Napoli — 29 mq — Cat. 13
- Acconto totale €311,00 | Rate: unica 31/07, 1^ 16/07, 2^ 16/09, 3^ 17/11
- Saldo/conguaglio: 16/02/2026

#### Fornitori — Scheda modulare 5 tab
- `app/schemas/fornitore_schema.py` — schema MongoDB completo
- `app/parsers/fornitore_xml_parser.py` — estrae anagrafica+prodotti+prezzi da XML SDI
- `app/parsers/fornitore_scraper.py` — web scraping schede tecniche (CSS+schema.org+Claude fallback)
- `app/routers/fornitori.py` — 5 endpoint tab + import XML + scraping background

| Tab | Fonte dati | Funzione |
|-----|-----------|---------|
| 1. Anagrafica | XML fatture SDI | Auto-popolamento RagSoc, PIVA, PEC, SDI, sede |
| 2. Schede tecniche | URL scraping + PDF | Logistici, commerciali, ingredienti, immagini |
| 3. Lista prodotti | Aggregazione XML | Tutti i prodotti acquistati con quantità e trend |
| 4. Listino prezzi | Storico XML | Evoluzione prezzo nel tempo per referenza |
| 5. Pagamento | Manuale | Banca/Cassa/Carta/Assegno — ereditato da nuove fatture |

**Scraper web — strategia:**
1. JSON-LD schema.org (fonte più affidabile)
2. Batteria selettori CSS comuni (e-commerce alimentare IT)
3. Regex testo libero (peso g/kg, pezzi/cartone, EAN-13)
4. Fallback Claude Haiku API (analisi semantica HTML)
5. Selettori salvati per riuso automatico (self-learning)

#### Learning Machine
- `app/privati_config.py` — **sorgente unica** CF familiari (routing documenti)
- `app/learning_hook.py` — helper universale eventi da qualsiasi router
- `app/routers/learning.py` — event collector, pattern z-score, anomalie, Claude API batch
- `app/learning_seed.py` — 6 regole normative iniziali
- `SKILL.md` (root repo) — knowledge base operativa per Claude

**Collections MongoDB Learning:**
- `learning_events` — ogni azione utente
- `learning_regole` — regole aggiornabili senza deploy
- `learning_pattern` — statistiche rolling (algoritmo Welford)
- `learning_feedback` — pollice su/giù utente
- `learning_anomalie` — anomalie con z-score e confidence

---

## API Endpoints completi

```
/api/dipendenti          → CRUD dipendenti + pignoramenti
/api/cedolini            → upload PDF Zucchetti, lista, dettaglio
/api/presenze            → upload Aut.301, calendario, KPI
/api/fatture             → fatture XML SDI + viewer HTML
/api/f24                 → F24 aziendali (upload/scarta/ripristina/riconcilia/alert)
/api/f24-privati         → F24 Ceraldi Michele
/api/quietanze           → quietanze ADE (upload/riconcilia)
/api/tributi             → TARI/IMU privati e aziendali
/api/alert-fiscali       → dashboard alert INPS/ritenute/avvisi/orfani
/api/fornitori           → scheda fornitore 5 tab + scraping
/api/learning            → learning machine (eventi/regole/pattern/anomalie)
/api/prima-nota          → prima nota contabile
/api/archivio-bonifici   → archivio bonifici
/api/estratto-conto-movimenti → EC bancario
/api/attendance          → presenze alternativo
/api/cucina              → ordini cucina
/api/tr                  → tracciabilità alimenti (lotti/produzioni/HACCP)
```

---

## Pattern appresi dai dati reali

### Ravvedimento IRAP integrativo
Due F24 con stesso codice IRAP+anno ma importi diversi (es. €6.000 + €6.060) = **RAVVEDIMENTO_INTEGRATIVO** — non è un errore. Il secondo ravvedimento copre il residuo con interessi ricalcolati sul maggior ritardo. Fonte: Fiscomania, confermato da web.

### Credito IRES 1631
Ceraldi usa massivamente il credito IRES 2023 per compensare le ritenute mensili. Q11: ritenuta €2.323,47 quasi interamente coperta da 1631 → saldo versato solo €15,29.

### Codice B990
Nuovo ente locale trovato in Q12 (oltre a F839=Napoli). Gestito nel parser.

### TARI F24 Semplificato — struttura rate
- `0101` = rata unica | `0103` = 1^/3 | `0203` = 2^/3 | `0303` = 3^/3

---

## Bug noti e fix applicati

| Bug | File | Fix |
|-----|------|-----|
| IMAP PEC hardcoded Gmail | aruba_automation.py riga 312 | `imaplib.IMAP4_SSL("imaps.pec.aruba.it", 993)` |
| Stesso bug possibile | aruba_pec_downloader.py | Verificare |

---

## Prossimi sviluppi suggeriti

- [ ] Frontend pagina `/fornitori` completa con 5 tab
- [ ] Frontend pagina `/learning-machine` dashboard ML
- [ ] Notifiche PEC automatiche per scadenze INPS imminenti
- [ ] Parser quietanze privati (F24 Ceraldi Michele)
- [ ] Integrazione ZES Campania (credito d'imposta investimenti)
- [ ] Verifica ravvedimento IRAP con commercialista Marotta
- [ ] Pagina `/privati` con anagrafica completa familiari

---

## Istruzione per Claude — inizio ogni nuova chat

1. Leggi questo file
2. Leggi i commit recenti: `GET https://api.github.com/repos/ceraldicontabilita/gestionale2/commits?per_page=10`
3. Aggiorna questo file a fine chat con tutto quello che è cambiato
4. Rispondi sempre in italiano

*Ultimo aggiornamento: Chat 4 — 08/04/2026*
