"""
Ceraldi ERP v2 — MongoDB Atlas connection test
================================================
Install:   pip install pymongo python-dotenv
Run:       python mongodbExample.py

Set MONGODB_URI in .env or as environment variable before running.
Example .env:
    MONGODB_URI=mongodb+srv://Ceraldidatabase:LA_TUA_PASSWORD@cluster0.vofh7iz.mongodb.net/?appName=Cluster0
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from bson import ObjectId

# ─── 1. Load connection string from .env or environment ────
load_dotenv()
uri = os.getenv("MONGODB_URI")
if not uri:
    print("ERROR: MONGODB_URI not set. Create a .env file with your connection string.")
    sys.exit(1)

# Never print the full URI — it contains credentials
print(f"[1/6] Connecting to cluster: {uri.split('@')[1].split('/')[0] if '@' in uri else 'unknown'}...")

# ─── 2. Connect to MongoDB Atlas ──────────────────────────
try:
    client = MongoClient(uri, server_api=ServerApi("1"))
    client.admin.command("ping")
    print("[2/6] Connected to MongoDB Atlas successfully!")
except Exception as e:
    print(f"ERROR: Connection failed — {e}")
    sys.exit(1)

# ─── 3. Select database and collection ────────────────────
# Database: azienda_erp_db (same as Ceraldi ERP)
# Collection: dipendenti (MAI usare "employees")
db = client["azienda_erp_db"]
coll = db["_test_connection"]  # temporary test collection
print(f"[3/6] Using database: {db.name}, collection: {coll.name}")

# ─── 4. Insert 10 realistic documents ─────────────────────
# Simulating employee records for a bar/restaurant (HORECA)
base_date = datetime(2024, 1, 15)
test_docs = [
    {"nome": "Capezzuto", "cognome": "Alessandro", "ruolo": "barista", "stato": "attivo",
     "codice_fiscale": "CPZLSN90A01F839X", "stipendio": 1190.00, "created_at": base_date + timedelta(days=0)},
    {"nome": "Dias", "cognome": "Mahatelge Kris", "ruolo": "cameriere", "stato": "attivo",
     "codice_fiscale": "DSMMTL85B15Z404K", "stipendio": 1190.00, "created_at": base_date + timedelta(days=5)},
    {"nome": "D'Alma", "cognome": "Vincenzo", "ruolo": "lavapiatti", "stato": "cessato",
     "codice_fiscale": "DLMVCN59E09F839T", "stipendio": 0, "created_at": base_date + timedelta(days=10)},
    {"nome": "Rossi", "cognome": "Mario", "ruolo": "cuoco", "stato": "attivo",
     "codice_fiscale": "RSSMRA80C15F839H", "stipendio": 1450.00, "created_at": base_date + timedelta(days=15)},
    {"nome": "Esposito", "cognome": "Anna", "ruolo": "cassiera", "stato": "attivo",
     "codice_fiscale": "SPSNNA92D45F839L", "stipendio": 1100.00, "created_at": base_date + timedelta(days=20)},
    {"nome": "Bianchi", "cognome": "Luigi", "ruolo": "barista", "stato": "sospeso",
     "codice_fiscale": "BNCLGU88H10F839M", "stipendio": 1190.00, "created_at": base_date + timedelta(days=25)},
    {"nome": "Verdi", "cognome": "Francesca", "ruolo": "pasticciera", "stato": "attivo",
     "codice_fiscale": "VRDFNC95L50F839N", "stipendio": 1350.00, "created_at": base_date + timedelta(days=30)},
    {"nome": "Russo", "cognome": "Giuseppe", "ruolo": "pizzaiolo", "stato": "attivo",
     "codice_fiscale": "RSSGPP82M20F839P", "stipendio": 1500.00, "created_at": base_date + timedelta(days=35)},
    {"nome": "Ferrara", "cognome": "Carla", "ruolo": "cameriera", "stato": "cessato",
     "codice_fiscale": "FRRCRL90S55F839Q", "stipendio": 0, "created_at": base_date + timedelta(days=40)},
    {"nome": "Conte", "cognome": "Marco", "ruolo": "magazziniere", "stato": "attivo",
     "codice_fiscale": "CNTMRC87A01F839R", "stipendio": 1250.00, "created_at": base_date + timedelta(days=45)},
]

try:
    # Clean up any previous test data
    coll.delete_many({})
    result = coll.insert_many(test_docs)
    print(f"[4/6] Inserted {len(result.inserted_ids)} test documents")
except Exception as e:
    print(f"ERROR: Insert failed — {e}")
    sys.exit(1)

# ─── 5. Read 5 most recent documents by created_at ────────
try:
    print("\n[5/6] 5 most recent employees (sorted by created_at desc):")
    print("-" * 70)
    recent = coll.find().sort("created_at", -1).limit(5)
    saved_id = None
    for doc in recent:
        if saved_id is None:
            saved_id = doc["_id"]  # save first _id for step 6
        print(f"  {doc['cognome']:20s} {doc['nome']:15s} | {doc['ruolo']:12s} | {doc['stato']:8s} | {doc['created_at'].strftime('%d/%m/%Y')}")
except Exception as e:
    print(f"ERROR: Query failed — {e}")

# ─── 6. Read one document by _id ──────────────────────────
try:
    print(f"\n[6/6] Lookup by _id: {saved_id}")
    print("-" * 70)
    one = coll.find_one({"_id": saved_id})
    if one:
        for k, v in one.items():
            print(f"  {k}: {v}")
    else:
        print("  Document not found")
except Exception as e:
    print(f"ERROR: Lookup failed — {e}")

# ─── Cleanup ──────────────────────────────────────────────
coll.drop()  # remove test collection
client.close()
print("\nTest collection removed. Connection closed. All good!")
