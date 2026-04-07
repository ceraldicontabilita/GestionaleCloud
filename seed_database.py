"""
Ceraldi ERP v2 — Seed Database
================================
Popola il DB con dipendenti reali e pignoramenti D'Alma.

Esegui: python seed_database.py
Richiede: pip install pymongo dnspython
"""
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime

URI = "mongodb+srv://Ceraldidatabase:MEVMrFgTzywJTaTG@cluster0.vofh7iz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "azienda_erp_db"

print("Connecting to MongoDB Atlas...")
client = MongoClient(URI, server_api=ServerApi("1"))
client.admin.command("ping")
print("Connected!\n")

db = client[DB_NAME]

# ══════════════════════════════════════════════════
# DIPENDENTI
# ══════════════════════════════════════════════════
dipendenti = [
    {
        "nome": "Alessandro",
        "cognome": "Capezzuto",
        "codice_fiscale": "CPZLSN90A01F839X",
        "stato": "attivo",
        "ruolo": "barista",
        "iban": "IT86C0514203419CC1186038905",
        "importo_stipendio": 1190.00,
        "pignoramenti": [],
        "created_at": datetime(2023, 1, 15),
        "updated_at": datetime.utcnow(),
    },
    {
        "nome": "Mahatelge Kris",
        "cognome": "Dias",
        "codice_fiscale": "DSMMTL85B15Z404K",
        "stato": "attivo",
        "ruolo": "cameriere",
        "iban": "IT42K3608105138211526811539",
        "importo_stipendio": 1190.00,
        "pignoramenti": [],
        "created_at": datetime(2023, 3, 1),
        "updated_at": datetime.utcnow(),
    },
    {
        "nome": "Vincenzo",
        "cognome": "D'Alma",
        "codice_fiscale": "DLMVCN59E09F839T",
        "stato": "cessato",
        "data_cessazione": "2023-06-30",
        "ruolo": "lavapiatti",
        "iban": "",
        "importo_stipendio": 0,
        "pignoramenti": [
            {
                "id": "pig-001",
                "numero_documento": "20220002093620903043020",
                "data_documento": "15/12/2022",
                "ente_creditore": "municipia",
                "debitore_nome": "D'ALMA VINCENZO",
                "debitore_cf": "DLMVCN59E09F839T",
                "importo": 471.28,
                "targa": "BA782XR",
                "anno_riferimento": "2013",
                "ingiunzione": "334076493055",
                "pec_destinazione": "rcrc-affarilegali@pec.it",
                "stato": "cessato_rapporto",
                "dichiarazione_pdf_path": "",
                "ricevuta_pec_path": "",
                "created_at": datetime(2022, 12, 15).isoformat(),
            },
            {
                "id": "pig-002",
                "numero_documento": "20230002128201049032555",
                "data_documento": "06/12/2023",
                "ente_creditore": "municipia",
                "debitore_nome": "D'ALMA VINCENZO",
                "debitore_cf": "DLMVCN59E09F839T",
                "importo": 492.47,
                "targa": "BA782XR",
                "anno_riferimento": "2015",
                "ingiunzione": "534150439863",
                "pec_destinazione": "rcrc-affarilegali@pec.it",
                "stato": "cessato_rapporto",
                "dichiarazione_pdf_path": "",
                "ricevuta_pec_path": "",
                "created_at": datetime(2023, 12, 6).isoformat(),
            },
            {
                "id": "pig-003",
                "numero_documento": "20240002155481097266515",
                "data_documento": "28/10/2024",
                "ente_creditore": "municipia",
                "debitore_nome": "D'ALMA VINCENZO",
                "debitore_cf": "DLMVCN59E09F839T",
                "importo": 503.19,
                "targa": "BA782XR",
                "anno_riferimento": "2016",
                "ingiunzione": "634211222727",
                "pec_destinazione": "rcrc-affarilegali@pec.it",
                "stato": "cessato_rapporto",
                "dichiarazione_pdf_path": "",
                "ricevuta_pec_path": "",
                "created_at": datetime(2024, 10, 28).isoformat(),
            },
        ],
        "created_at": datetime(2020, 9, 1),
        "updated_at": datetime.utcnow(),
    },
]

# Insert
coll = db["dipendenti"]
coll.delete_many({})  # pulisci prima
result = coll.insert_many(dipendenti)
print(f"Inseriti {len(result.inserted_ids)} dipendenti:")
for d in dipendenti:
    pig_count = len(d.get("pignoramenti", []))
    pig_tot = sum(p["importo"] for p in d.get("pignoramenti", []))
    extra = f" | {pig_count} pignoramenti (€{pig_tot:.2f})" if pig_count else ""
    print(f"  {d['cognome']:15s} {d['nome']:20s} | {d['stato']:8s}{extra}")

# Create indexes
coll.create_index("codice_fiscale", unique=True, sparse=True)
coll.create_index("stato")
print("\nIndexes created on 'dipendenti'")

# ══════════════════════════════════════════════════
# CARTELLE ESATTORIALI (Ceraldi Group)
# ══════════════════════════════════════════════════
cartelle = [
    {
        "numero_cartella": "071 2021 00259828 44/000",
        "data": "2021-02-25",
        "ente": "Agenzia delle Entrate",
        "motivo": "Tardivo versamento UNICO/2014 anno 2013",
        "importo": 69.91,
        "stato": "pagata",
        "data_pagamento": "2022-03-10",
        "ricevuta": "IUV 80071050056259000",
    },
    {
        "numero_cartella": "071 2024 00571434 49/000",
        "data": "2024-02-10",
        "ente": "Agenzia delle Entrate",
        "motivo": "Controllo mod. 770/2019 — ritenute IRPEF non versate",
        "importo": 9384.52,
        "stato": "in_rateizzazione",
        "rata_mensile": 781.60,
        "ultimo_pagamento": "2025-10-17",
        "codice_cbill": "180071112083066417",
    },
]

coll_cart = db["cartelle_esattoriali"]
coll_cart.delete_many({})
coll_cart.insert_many(cartelle)
print(f"\nInserite {len(cartelle)} cartelle esattoriali")

# ══════════════════════════════════════════════════
# DATI AZIENDALI
# ══════════════════════════════════════════════════
azienda = {
    "ragione_sociale": "CERALDI GROUP S.R.L.",
    "partita_iva": "04523831214",
    "codice_fiscale": "04523831214",
    "indirizzo": "PIAZZA NAZIONALE 46, 80143 NAPOLI NA",
    "banca": "Banco BPM S.P.A.",
    "iban": "IT13X0503403406000000005462",
    "conto_corrente": "00005462",
    "mutuo": {
        "tipo": "Ipotecario fondiario surroga flessibile microimprese",
        "finanziamento": "1788/0005217466",
        "rata_mensile": 4602.66,
        "debito_residuo": 18234.08,
        "ultima_rata_pagata": "056 del 17/10/2025",
    },
    "pec": "fatturazioneceraldi@pec.it",
    "gmail": "ceraldigroupsrl@gmail.com",
}

db["azienda"].delete_many({})
db["azienda"].insert_one(azienda)
print(f"Dati aziendali inseriti")

# ══════════════════════════════════════════════════
# VERIFY
# ══════════════════════════════════════════════════
print("\n" + "=" * 50)
print("VERIFICA")
print("=" * 50)
for d in db["dipendenti"].find():
    print(f"\n{d['cognome']} {d['nome']} ({d['stato']})")
    for p in d.get("pignoramenti", []):
        print(f"  Pignoramento {p['id']}: €{p['importo']} - {p['stato']} - targa {p.get('targa','')}")

for c in db["cartelle_esattoriali"].find():
    print(f"\nCartella {c['numero_cartella']}: €{c['importo']} - {c['stato']}")

print(f"\nCollections nel DB: {db.list_collection_names()}")
client.close()
print("\nDone! Database popolato.")
