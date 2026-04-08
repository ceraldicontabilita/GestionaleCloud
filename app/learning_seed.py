"""
Regole iniziali per il sistema di apprendimento Ceraldi ERP.
Queste sono le regole "hardcoded" che possono essere poi modificate
dall'utente o da Claude via API.

Eseguire come script una tantum:
    python3 -m app.learning_seed
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

MONGO_URL = "mongodb+srv://Ceraldidatabase:PASSWORD@cluster0.vofh7iz.mongodb.net/"
AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"

REGOLE_INIZIALI = [
    {
        "nome": "INPS DM10 — scadenza 16 mese successivo",
        "descrizione": "I contributi DM10/CXX devono essere versati entro il 16 del mese successivo",
        "tipo": "scadenza_contributi",
        "condizione": {"codici": ["DM10", "CXX"], "giorni_scadenza": 16},
        "azione": {"alert": True, "livello": "danger", "nota": "DURC irregolare da giorno 1"},
        "priorita": 10,
        "confidence": 1.0,
        "origine": "normativa",
    },
    {
        "nome": "Ritenute 1001 — soglia penale €150k",
        "descrizione": "Accumulare più di €150.000 di ritenute non versate causa reato penale",
        "tipo": "soglia_penale",
        "condizione": {"codice": "1001", "soglia_euro": 150000},
        "azione": {"alert": True, "livello": "critical", "nota": "Art.10-bis DLgs 74/2000"},
        "priorita": 10,
        "confidence": 1.0,
        "origine": "normativa",
    },
    {
        "nome": "Compensazione — blocco ruoli >€50k",
        "descrizione": "Non è possibile compensare in F24 se ci sono ruoli scaduti >€50.000",
        "tipo": "blocco_compensazione",
        "condizione": {"soglia_ruoli": 50000},
        "azione": {"alert": True, "livello": "warning", "nota": "Dal 01/01/2026 soglia scesa da €100k"},
        "priorita": 8,
        "confidence": 1.0,
        "origine": "normativa",
    },
    {
        "nome": "Avviso bonario — cercare documento correlato",
        "descrizione": "Quando arriva un F24 con cod. 9001/9002, cercare il documento ADE corrispondente",
        "tipo": "avviso_bonario",
        "condizione": {"codici": ["9001", "9002"], "ha_codice_atto": True},
        "azione": {"cerca_in": ["fatture_passive", "avvisi_bonari"], "alert": True},
        "priorita": 9,
        "confidence": 1.0,
        "origine": "appreso",
    },
    {
        "nome": "Ravvedimento IRAP — pattern importi diversi",
        "descrizione": "Stesso codice IRAP, stesso anno, importi diversi = ravvedimento integrativo",
        "tipo": "classificazione_duplicati",
        "condizione": {"codice": "3800|3801|3802|3813", "stesso_anno": True, "importi_diversi": True},
        "azione": {"classifica_come": "RAVVEDIMENTO_INTEGRATIVO", "non_alert": True},
        "priorita": 7,
        "confidence": 0.95,
        "origine": "appreso",
    },
    {
        "nome": "TARI — avviso separato azienda/privato",
        "descrizione": "I documenti TARI intestati a persone fisiche vanno in pagina privata",
        "tipo": "routing_documento",
        "condizione": {"tipo_doc": "TARI", "cf_non_aziendale": True},
        "azione": {"route": "tributi_privati", "avvisa_utente": True},
        "priorita": 6,
        "confidence": 1.0,
        "origine": "manuale",
    },
]

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client["Gestionale"]
    for r in REGOLE_INIZIALI:
        r["attiva"] = True
        r["creata_il"] = datetime.utcnow()
        r["aggiornata_il"] = datetime.utcnow()
        r["aggiornata_da"] = "seed"
        r["hit_count"] = 0
        r["azienda_id"] = AZIENDA_ID
        await db["learning_regole"].update_one(
            {"nome": r["nome"]}, {"$setOnInsert": r}, upsert=True
        )
        print(f"✅ Regola: {r['nome']}")
    client.close()
    print(f"\n✅ {len(REGOLE_INIZIALI)} regole seed caricate")

if __name__ == "__main__":
    asyncio.run(main())
