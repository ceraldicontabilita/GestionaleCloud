---
name: ceraldi-erp
description: |
  Sistema di controllo intelligente per il gestionale Ceraldi ERP (Ceraldi Group SRL).
  USA QUESTA SKILL ogni volta che lavori su codice, dati o analisi del Ceraldi ERP.
  Contiene regole operative, pattern appresi, codici tributo, logica di business.
  Si auto-aggiorna ad ogni chat con nuove regole apprese.
---

# Ceraldi ERP — Skill operativa

## Contesto sistema
- Stack: FastAPI + Motor + MongoDB Atlas · React 18 + Vite · Supervisor :3000/:8001
- Repo: `ceraldicontabilita/gestionale2` branch main
- DB: cluster0.vofh7iz · db=Gestionale · utente=Ceraldidatabase
- AZIENDA_ID: `b0295759-35ce-4b34-a6b4-f01b883234ad`
- CF Azienda: 04523831214 (Ceraldi Group SRL)

## Regole di sviluppo assolute
- Collections: `dipendenti` (mai "employees"), `fornitori` (mai "suppliers"), `cedolini`
- IMAP sempre in `asyncio.to_thread()`
- CSS inline via `lib/utils.js` — no Tailwind, no Shadcn
- Icone: solo `lucide-react`
- Tab interni: `useState`, non `navigate()`
- Mai file alias/wrapper — correggere sempre l'import nel file originale

## Persone fisiche note
- Ceraldi Michele: CF `CRLMHL50R01F352F` — **familiare** (non titolare) — nato 01/10/1950 Mondragone CE
- Ceraldi Antonietta: CF `CRLNNT75M55F352C` — familiare — nata 15/08/1975 Mondragone

## Codici tributo appresi (F24)

### Erario
| Codice | Descrizione |
|--------|-------------|
| 1001 | Ritenute IRPEF dipendenti (scad. 16 mese succ.) |
| 1012 | Ritenute TFR/cessazione rapporto |
| 1040 | Ritenute lavoro autonomo |
| 1627 | 2° acconto IRES |
| 1631 | Credito IRES in compensazione |
| 1668 | Interessi ravvedimento |
| 1701 | Add. regionale IRPEF (usato come credito) |
| 1703 | Add. comunale IRPEF saldo (credito) |
| 1704 | Add. comunale IRPEF (credito) |
| 1712 | Add. regionale IRPEF saldo |
| 1713 | Ravvedimento add. regionale |
| 1990 | IRES sostitutiva |
| 1991 | IRES interessi |
| 2001 | IVA |
| 2003 | IVA mensile |
| 6001-6012 | IVA mensile per mese (6001=gen, 6007=lug, ecc.) |
| 6099 | Credito IVA in compensazione |
| 7085 | Tassa bollatura libri sociali |
| 8904 | Imposta bollo ravvedimento |
| 8906 | Sanzione ravvedimento tributi erario |
| 8907 | Sanzione ravvedimento IRAP |
| 8908 | Sanzione ravvedimento add. regionale |
| 8918 | Bollo libri sociali |
| 8947 | Interessi ravvedimento add. regionale |
| 8948 | Interessi ravvedimento ritenute |
| 8949 | Interessi ravvedimento add. comunale |
| 9001 | Somme avviso bonario art.36-bis (con Codice Atto) |
| 9002 | Somme avviso bonario art.36-bis IVA |

### INPS
| Codice | Descrizione |
|--------|-------------|
| DM10 | Contributi dipendenti (scad. 16 mese succ.) |
| CXX | Sede INPS Napoli (80143NAPOLI) |
| RC01 | Rateazione/concordato INPS |
| COS | Contributo solidarietà (matricola 888888888888) |
| GPJA | Gestione separata professionisti |

### Regioni (Campania = 05)
| Codice | Descrizione |
|--------|-------------|
| 3800 | IRAP saldo |
| 3801 | IRAP saldo |
| 3802 | IRAP mensile/trimestrale |
| 3805 | IRAP 1° acconto |
| 3813 | IRAP 2° acconto |
| 3796 | IRAP credito compensazione |
| 8950 | IRAP interessi ravvedimento |
| 8907 | IRAP sanzione ravvedimento |

### Tributi locali Napoli (ente F839)
| Codice | Descrizione |
|--------|-------------|
| 3847 | IMU acconto |
| 3848 | IMU saldo |
| 3918 | IMU fabbricati altri |
| 8952 | IMU interessi ravvedimento |
| 1671 | Credito tributi locali compensazione |
| 3944 | TARI — Tassa Rifiuti (sezione EL) |
| TEFA | Tributo Provinciale Ambientale (5% TARI) |

### Codici tipicamente credito (segno negativo in compensazione)
`{1701, 1703, 1704, 1631, 3796, 3797, 6099, 1671}`

## Regole fiscali implementate

### INPS — scadenza e DURC
- DM10/CXX: 16 del mese successivo al periodo
- Entro 120gg dalla scadenza: ravvedimento spontaneo (solo TUR=2,9%)
- Oltre 120gg: TUR+5,5% max 40%
- DURC irregolare da giorno 1 di ritardo
- Tolleranza appalti: <5% o <€100 non causa irregolarità
- Procedura: PEC con invito → 15gg (flessibile fino a 30gg fine istruttoria)

### Ritenute 1001
- Scadenza ordinaria: 16 mese successivo
- Termine ultimo penale: presentazione Modello 770 (31/10 anno succ.)
- Soglia penale: >€150.000/anno di ritenute *certificate* (CU)
- Sanzione amministrativa: 25% dell'importo non versato (post 01/09/2024)

### Compensazione F24
- IVA credito ≤€5.000: libera dal 1° gennaio anno succ.
- IVA credito >€5.000: dopo presentazione dichiarazione + 10gg
- Visto conformità obbligatorio >€5.000 (esonero ISA≥8: fino €50k, ISA≥9: fino €70k)
- Blocco compensazione orizzontale se ruoli scaduti >€50.000 (dal 01/01/2026)
- Tutti gli F24 con compensazione: solo canali telematici ADE (dal 01/07/2024)
- Limite annuo: €2.000.000

### Ravvedimento operoso (post 01/09/2024)
| Ritardo | Sanzione |
|---------|----------|
| ≤14gg | 0,08%/giorno |
| 15-30gg | 1,25% |
| 31-90gg | 1,39% |
| >90gg-1anno | 3,125% |
| >1anno | 3,75% |

### Avviso bonario 9001/9002
- Codice Atto = identificativo documento ADE correlato
- Cercare tra le fatture passive e gli avvisi in archivio
- Pagamento entro 30gg dalla notifica: no sanzioni extra
- Rateizzabile in 20 rate trimestrali

## Pattern appresi dai dati reali Ceraldi

### Ravvedimento IRAP integrativo (appreso da F24-I e F24-II)
- Stesso codice tributo, stesso anno, importi diversi con secondo > primo
- Il secondo ravvedimento copre il residuo con interessi ricalcolati sul maggior ritardo
- Classificazione corretta: RAVVEDIMENTO_INTEGRATIVO (non errore)

### Credito IRES 1631 (appreso dalle quietanze reali)
- Ceraldi ha usato credito IRES 2023 per compensare: 1001 nov/2024 €2.323,47 → solo €15,29 versati
- Il credito 1631 è stato usato massivamente per abbattere ritenute mensili

### TARI Napoli — struttura F24 semplificato
- Sezione: EL (Elementi Identificativi)
- Rate: 0101=unica, 0103=1^, 0203=2^, 0303=3^
- Componenti ARERA 2025: UR1=€0,10 + UR2=€1,50 + UR3=€6,00 = €7,60

## API Endpoints principali
```
/api/dipendenti      → gestione dipendenti
/api/cedolini        → cedolini (parser Zucchetti Aut.299/301)
/api/presenze        → presenze (parser Zucchetti Aut.301)
/api/f24             → F24 aziendali (upload, scarta, riconcilia)
/api/f24-privati     → F24 Ceraldi Michele
/api/quietanze       → quietanze ADE (upload, riconcilia con F24)
/api/fatture         → fatture XML SDI (viewer XSL)
/api/tributi         → TARI/IMU privati e aziendali
/api/alert-fiscali   → dashboard alert INPS/ritenute/avvisi
/api/learning        → learning machine (eventi, regole, pattern)
/api/prima-nota      → prima nota contabile
/api/tr              → tracciabilità alimenti (lotti, produzioni)
/api/cucina          → ordini cucina
/api/attendance      → presenze (modulo alternativo)
```

## Learning Machine — come funziona

Il sistema raccoglie eventi da ogni azione nel gestionale e li analizza con Claude API
per identificare pattern, anomalie e regole da aggiornare automaticamente.

### Collections MongoDB learning
- `learning_events`: ogni evento strutturato {tipo, payload, timestamp, modulo}
- `learning_regole`: regole attive aggiornabili senza deploy
- `learning_pattern`: pattern statistici appresi (frequenze, medie, soglie)
- `learning_feedback`: conferme/correzioni dell'utente (pollice su/giù)
- `learning_anomalie`: anomalie rilevate con score e stato

### Tipi di evento tracciati
- `f24_importato`: quando arriva un F24 (codici, importi, date)
- `quietanza_riconciliata`: match F24-quietanza riuscito/fallito
- `alert_confermato`: l'utente dice "sì, è un problema"
- `alert_ignorato`: l'utente dice "falso positivo"
- `codice_corretto`: utente cambia codice tributo → nuovo pattern
- `documento_scartato`: F24 scartato con motivo
- `anomalia_rilevata`: importo fuori range statistico

### Ciclo di apprendimento
1. Evento → `learning_events` (MongoDB)
2. Batch notturno → Claude analizza gli ultimi N eventi
3. Claude propone: nuove regole · aggiornamenti soglie · nuovi pattern
4. Sistema applica automaticamente se confidence >0,85
5. Utente può confermare/correggere dalla dashboard
6. Il feedback rafforza o indebolisce le regole future
