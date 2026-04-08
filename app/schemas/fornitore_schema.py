"""
Schema MongoDB — Collection "fornitori" (Ceraldi ERP)
======================================================
REGOLA: collection si chiama "fornitori".
Ogni fornitore aggrega dati da 5 fonti:
  1. XML fatture elettroniche SDI (auto-popolamento anagrafica)
  2. Web scraping URL (schede tecniche prodotti)
  3. PDF caricati manualmente (documentazione tecnica)
  4. Aggregazione fatture XML (lista prodotti + listino)
  5. Configurazione manuale (metodo di pagamento)

Struttura documento MongoDB:
{
  "_id": ObjectId,
  "azienda_id": "b0295759-35ce-4b34-a6b4-f01b883234ad",

  # ── TAB 1: Anagrafica (auto da XML SDI) ─────────────────
  "anagrafica": {
    "ragione_sociale": "Mario Rossi SRL",
    "piva": "01234567890",
    "codice_fiscale": "01234567890",
    "codice_sdi": "ABC1234",                 # CodiceDestinatario
    "pec": "fornitore@pec.it",
    "regime_fiscale": "RF01",                # RegimeFiscale
    "sede": {
      "indirizzo": "Via Roma 1",
      "cap": "80100",
      "comune": "Napoli",
      "provincia": "NA",
      "nazione": "IT",
    },
    "prima_fattura_data": "2023-01-15",
    "ultima_fattura_data": "2025-03-10",
    "n_fatture_totali": 42,
    "estratto_da_xml": True,                 # sempre True se auto
    "updated_at": datetime,
  },

  # ── TAB 2: Schede tecniche & scraping ───────────────────
  "schede_tecniche": {
    "urls_scraping": [
      {
        "url": "https://fornitore.it/prodotto/123",
        "label": "Passata pomodoro 400g",
        "stato": "ok",                        # ok|errore|in_corso
        "ultimo_scraping": datetime,
        "selettori": {                        # selettori CSS/XPath salvati
          "prezzo": ".price",
          "ingredienti": "#ingredients",
          "peso": "[data-weight]",
          "pezzi_cartone": ".pcs-per-box",
        },
        "dati_estratti": {
          # Dati logistici
          "quantita_per_cartone": 12,
          "pezzi_per_cartone": 12,
          "peso_prodotto_g": 400,
          "peso_cartone_kg": 5.2,
          # Dati commerciali
          "prezzo_cartone": 18.50,
          "prezzo_unitario": 1.54,
          "valuta": "EUR",
          # Dati prodotto
          "ingredienti": "Pomodori pelati, sale",
          "allergeni": [],
          "codice_ean": "8001234567890",
          "immagini": ["https://fornitore.it/img/prod123.jpg"],
        },
      }
    ],
    "pdf_tecnici": [
      {
        "filename": "scheda_tecnica_passata.pdf",
        "path": "/uploads/fornitori/{id}/pdf/scheda_passata.pdf",
        "tipo": "scheda_tecnica",             # scheda_tecnica|certificato|listino
        "caricato_il": datetime,
        "generato_da_scraping": False,
      }
    ],
  },

  # ── TAB 3: Lista prodotti (aggregata da XML) ─────────────
  "prodotti": [
    {
      "codice_articolo": "PASS400",           # CodiceArticolo da XML
      "descrizione": "Passata di pomodoro 400g",
      "unita_misura": "PZ",
      "prima_acquisto": "2023-01-15",
      "ultimo_acquisto": "2025-03-10",
      "n_acquisti": 18,
      "quantita_totale_acquistata": 1440.0,
      "url_scheda": None,                     # link alla scheda tecnica
      "immagine": None,
    }
  ],

  # ── TAB 4: Listino prezzi (storico da XML) ───────────────
  "storico_prezzi": [
    {
      "codice_articolo": "PASS400",
      "descrizione": "Passata di pomodoro 400g",
      "storico": [
        {
          "data": "2023-01-15",
          "numero_fattura": "2023/001",
          "prezzo_unitario": 1.20,
          "quantita": 120,
          "sconto_pct": 0.0,
          "prezzo_netto": 1.20,
        },
        {
          "data": "2024-06-10",
          "numero_fattura": "2024/078",
          "prezzo_unitario": 1.35,
          "quantita": 100,
          "sconto_pct": 5.0,
          "prezzo_netto": 1.2825,
        },
      ],
      "prezzo_attuale": 1.35,
      "variazione_pct": 12.5,                 # rispetto al primo prezzo
      "trend": "crescita",                    # crescita|stabile|calo
    }
  ],

  # ── TAB 5: Metodo di pagamento ───────────────────────────
  "pagamento": {
    "metodo": "banca",                        # cassa|banca|carta|assegno
    "conto_banca": "Banco BPM c/c 00005462", # se metodo=banca
    "iban_fornitore": "IT60X0542811101000000123456",
    "termini_pagamento": "30gg",              # da XML FatturPA
    "note": "",
    "ereditato_automaticamente": True,        # ogni nuova fattura eredita
  },

  # ── Metadati gestione ────────────────────────────────────
  "created_at": datetime,
  "updated_at": datetime,
  "stato": "attivo",                          # attivo|inattivo|bloccato
  "note_interne": "",
  "tags": [],
}
"""
