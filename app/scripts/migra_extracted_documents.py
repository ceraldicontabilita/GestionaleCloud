"""Migrazione non distruttiva P1 §5.8 — consolida l'archivio degli upload AI
manuali `extracted_documents` nella collezione CANONICA `documenti_classificati`
(scelta utente), con `fonte="upload_ai"`.

I nuovi upload di /api/document-ai/extract e /extract-base64 scrivono già nella
canonica; questo script porta lo storico. La lettura del tab "Classificati AI"
fonde canonica+legacy finché la migrazione non è stata eseguita, quindi l'app
funziona identica prima e dopo.

NB: i documenti del flusso "da rivedere" di ai_parser (campo `status`) NON
vengono toccati: quel flusso resta sulla sua collezione.

`extracted_documents` NON viene cancellata (resta come archivio). Idempotente:
dedup per filename.

Uso:
    python -m app.scripts.migra_extracted_documents          # dry-run
    python -m app.scripts.migra_extracted_documents --esegui # applica
"""
import asyncio
import sys

from app.database import Database

LEGACY = "extracted_documents"
CANONICA = "documenti_classificati"


def _mappa(doc: dict) -> dict:
    d = {k: v for k, v in doc.items() if k != "_id"}
    d.setdefault("fonte", "upload_ai")
    d.setdefault("categoria", d.get("document_type"))
    d.setdefault("has_pdf", bool(d.get("file_base64")))
    d.setdefault("processato", True)
    return d


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    # Solo il flusso upload AI (il flusso "da rivedere" di ai_parser usa `status`)
    docs = await db[LEGACY].find({"status": {"$exists": False}}).to_list(100000)
    migrati = 0
    gia_presenti = 0
    for doc in docs:
        filename = doc.get("filename")
        if filename and await db[CANONICA].find_one(
                {"fonte": "upload_ai", "filename": filename}, {"_id": 1}):
            gia_presenti += 1
            continue
        if esegui:
            await db[CANONICA].insert_one(_mappa(doc))
        migrati += 1
    return {"trovati": len(docs), "da_migrare": migrati,
            "gia_presenti": gia_presenti, "applicato": bool(esegui)}


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect()
    r = await migra(esegui)
    print(f"{LEGACY} -> {CANONICA}: {r['da_migrare']} da migrare, "
          f"{r['gia_presenti']} già presenti (su {r['trovati']}), "
          f"applicato={r['applicato']} (legacy NON cancellata)")


if __name__ == "__main__":
    asyncio.run(_main())
