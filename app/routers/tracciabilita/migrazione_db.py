from fastapi import APIRouter
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter(prefix="/migrazione", tags=["Migrazione"])

MONGO_URL = "mongodb+srv://Ceraldidatabase:Accesso1974.@cluster0.vofh7iz.mongodb.net/?appName=Cluster0"

COLLECTION_DA_NON_COPIARE = {
    "invoices","fornitori","suppliers","prima_nota_cassa","prima_nota_banca",
    "prima_nota_salari","cedolini","payslips","employees","dipendenti",
    "acquisti_prodotti","ricette","dizionario_prodotti","f24_unificato",
    "f24","estratto_conto_movimenti","ordini_fornitori","users","settings"
}

@router.get("/stato")
async def stato_migrazione():
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    src = client["haccp_ceraldi"]
    dst = client["azienda_erp_db"]
    colls_src = await src.list_collection_names()
    risultato = {}
    for c in colls_src:
        if c in COLLECTION_DA_NON_COPIARE:
            continue
        n_src = await src[c].count_documents({})
        n_dst = await dst[c].count_documents({}) if c in await dst.list_collection_names() else 0
        risultato[c] = {"sorgente": n_src, "destinazione": n_dst, "completata": n_dst >= n_src}
    client.close()
    return risultato

@router.post("/copia/{nome_collection}")
async def copia_collection(nome_collection: str, skip: int = 0, limit: int = 1000):
    if nome_collection in COLLECTION_DA_NON_COPIARE:
        return {"errore": "Collection protetta, non copiabile"}
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=20000)
    src = client["haccp_ceraldi"]
    dst = client["azienda_erp_db"]
    totale_src = await src[nome_collection].count_documents({})
    docs = await src[nome_collection].find({}).skip(skip).limit(limit).to_list(limit)
    if not docs:
        client.close()
        return {"collection": nome_collection, "inseriti": 0, "saltati": 0, "totale_src": totale_src, "fine": True}
    inseriti = 0
    saltati = 0
    from pymongo.errors import BulkWriteError
    try:
        result = await dst[nome_collection].insert_many(docs, ordered=False)
        inseriti = len(result.inserted_ids)
    except BulkWriteError as bwe:
        inseriti = bwe.details.get("nInserted", 0)
        saltati = len(docs) - inseriti
    except Exception as e:
        client.close()
        return {"errore": str(e)}
    client.close()
    fine = (skip + len(docs)) >= totale_src
    return {"collection": nome_collection, "inseriti": inseriti, "saltati": saltati,
            "totale_src": totale_src, "processati": skip + len(docs), "fine": fine}
