# Ceraldi ERP v2

Gestionale HORECA interno — Ceraldi Group S.R.L., Napoli
Stack: FastAPI + Motor + MongoDB Atlas (backend) · React 18 + Vite (frontend)
Supervisor su porte :3000 (frontend) e :8001 (backend)

---

## Setup

```bash
# Backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend && npm install && npm run dev
```

## MongoDB Atlas
- Cluster: cluster0.vofh7iz
- DB: Gestionale
- Utente: Ceraldidatabase

---

## Moduli attivi

### Contabilità aziendale
| Modulo | Route | Prefix API | Collection |
|--------|-------|------------|------------|
| Fatture passive | /fatture | /api/fatture | fatture_passive |
| F24 | /f24 | /api/f24 | f24 |
| Corrispettivi | /corrispettivi | /api/corrispettivi | corrispettivi |
| Estratto conto | /estratto-conto | /api/estratto-conto | estratto_conto_movimenti |
| Distinte stipendi | /distinte | /api/distinte | distinte_pagamento |
| Alert fiscali | /alert-fiscali | /api/alert-fiscali | f24, quietanze |
| Quietanze | /quietanze | /api/quietanze | quietanze |

### HR
| Modulo | Route | Prefix API | Collection |
|--------|-------|------------|------------|
| Dipendenti | /dipendenti | /api/dipendenti | dipendenti |
| Cedolini | /cedolini | /api/cedolini | cedolini |
| Presenze | /presenze | /api/presenze | presenze |

### Privati / familiari titolare
| Modulo | Route | Prefix API | Collection |
|--------|-------|------------|------------|
| F24 privati | /f24-privati | /api/f24-privati | f24_privati |
| Tributi locali | /tributi | /api/tributi | tributi_azienda, tributi_privati |
| Verbali CdS | /verbali | /api/verbali | verbali |

### Fornitori & Acquisti
| Modulo | Route | Prefix API | Collection |
|--------|-------|------------|------------|
| Fornitori | /fornitori | /api/fornitori | fornitori |
| Sconti merce | /sconti-merce | ceraldiapp.it/api/sconti-merce | — |
| Omaggi Acquaviva | (tab in sconti) | /api/omaggi-acquaviva | fatture_passive |
| Ordini fornitori | /ordini | /api/ordini + ceraldiapp.it | ordini_ceraldi |

### HACCP (dati su ceraldiapp.it)
| Modulo | Route | API |
|--------|-------|-----|
| Dashboard | /haccp/dashboard | ceraldiapp.it/api/* |
| Temperature | /haccp/temperature | ceraldiapp.it/api/temperature-positive|negative |
| Sanificazione | /haccp/sanificazione | ceraldiapp.it/api/sanificazione |
| Disinfestazione | /haccp/disinfestazione | ceraldiapp.it/api/disinfestazione |

---

## Collections MongoDB (Gestionale)

```
dipendenti          — anagrafica, stato, pignoramenti, cedolino aggregato
fornitori           — anagrafica nested, storico_prezzi, prodotti, pagamento
fatture_passive     — fornitore_denominazione, fornitore_piva, numero, data, linee[]
cedolini            — codice_fiscale, mese, anno, netto, progressivi
presenze            — codice_fiscale, mese, anno, giorni[], totali
estratto_conto_movimenti — chiave (MD5), importo, dare, avere, categoria
corrispettivi       — dedup_key, data, totale_corrispettivi
f24                 — azienda_id, scadenza, tributi_flat[], saldo_finale
f24_privati         — codice_fiscale (privati), scadenza, tributi_flat[]
tributi_azienda     — codice_fiscale CF_AZIENDA, tipo_tributo, rate[]
tributi_privati     — codice_fiscale familiare, tipo_tributo, rate[]
verbali             — tipo, pdf_filename, stato
distinte_pagamento  — numero_bonifici, bonifici[], totale
quietanze           — azienda_id, data_versamento, tributi_flat[]
ordini_ceraldi      — operatore, reparto, righe[], stato (bozza/approvato/inviato)
mittenti_attendibili — canale, pattern, tipo_documento, attivo
sync_log            — tipo, timestamp, inserite, duplicate
```

---

## Campi critici (NON sbagliare)

```python
# fatture_passive
"fornitore_denominazione"   # NON "cedente.denominazione"
"fornitore_piva"            # NON "piva_fornitore"
"numero"                    # NON "numero_fattura"
"linee[].prezzo_unitario"   # NON "prezzo"
"linee[].unita_misura"      # NON "unita"

# dipendenti
"iban_cedolino"             # NON "iban" (scritto da cedolini.py)
"progressivi.{anno}.imp_inps"  # struttura nested per anno

# fornitori
"anagrafica.ragione_sociale"   # NON "denominazione" flat
"anagrafica.piva"              # NON "partita_iva" flat
```

---

## Soggetti privati

- CERALDI Michele (CF: CRLMHL50R01F352F) — familiare titolare
- CERALDI Antonietta (CF: CRLNNT75M55F352C) — familiare titolare
- Entrambi → collection tributi_privati, pagina privata
- MAI in contabilità aziendale

---

## Architettura dual-app

Il gestionale2 coesiste con il repo `tracciabilita` (ceraldiapp.it):
- Le pagine HACCP e sconti nel gestionale2 chiamano ceraldiapp.it come API esterna
- ceraldiapp.it è DOWN → le pagine mostrano errore gracefully, non crashano
- Il catalogo ordini usa ceraldiapp.it/api/ordini-fornitori/prodotti-suggeriti
  (dizionario_prodotti precompilato da tracciabilita)
- La comparazione prezzi usa /api/ordini/prezzi/* (gestionale2 locale, da fatture_passive)

---

## Regole di sviluppo

- Collections: MAI rinominare (dipendenti NON employees, fornitori NON suppliers)
- IMAP sempre in asyncio.to_thread()
- CSS inline tramite lib/utils.js — NO Tailwind, NO Shadcn
- Icone: solo lucide-react
- Tab interni: useState, non navigate()
- Nessun file alias/wrapper: correggere l'import nel file originale
- PEC Aruba: imaps.pec.aruba.it porta 993, user fatturazioneceraldi@pec.it
