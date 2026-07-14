"""Migrazione non distruttiva P1 §5.8 — consolida i documenti classificati dall'alias
inglese legacy `documents_classified` (pipeline email) nella canonica UNICA
`documenti_classificati` (stessa della Learning Machine), scelta dall'utente.

Mappa i campi email sullo schema canonico della Learning Machine (categoria/_key/
from/date/has_pdf/processato/created_at) mantenendo i campi propri del pipeline email
(tipo/filename/pdf_base64/gestionale_section/processed). Aggiunge `fonte="email_classifier"`.

`documents_classified` NON viene cancellata (archivio). Idempotente: dedup per
(subject + filename).

Uso:
    python -m app.scripts.migra_documents_classified          # dry-run
    python -m app.scripts.migra_documents_classified --esegui # applica
"""
import asyncio
import sys

from app.database import Database

LEGACY = "documents_classified"
CANONICA = "documenti_classificati"


def _mappa(doc: dict) -> dict:
    d = {k: v for k, v in doc.items() if k != "_id"}
    subject = d.get("subject", "")
    filename = d.get("filename", "")
    d.setdefault("fonte", "email_classifier")
    d.setdefault("_key", f"email_{subject[:50]}_{filename}")
    d.setdefault("categoria", d.get("tipo"))
    d.setdefault("from", d.get("sender"))
    d.setdefault("date", d.get("data_email"))
    d.setdefault("has_pdf", bool(d.get("pdf_base64")))
    d.setdefault("processato", bool(d.get("processed", False)))
    d.setdefault("created_at", d.get("data_inserimento"))
    return d


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    docs = await db[LEGACY].find({}).to_list(100000)
    migrati = 0
    gia_presenti = 0
    for doc in docs:
        subject = doc.get("subject")
        filename = doc.get("filename")
        chiave = {"subject": subject, "filename": filename}
        if await db[CANONICA].find_one(chiave, {"_id": 1}):
            gia_presenti += 1
            continue
        if esegui:
            await db[CANONICA].insert_one(_mappa(doc))
        migrati += 1
    return {"trovati": len(docs), "da_migrare": migrati,
            "gia_presenti": gia_presenti, "applicato": bool(esegui)}


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect_db()
    r = await migra(esegui)
    print(f"documents_classified -> {CANONICA}: {r['da_migrare']} da migrare, "
          f"{r['gia_presenti']} già presenti (su {r['trovati']}), "
          f"applicato={r['applicato']} (legacy NON cancellata)")


if __name__ == "__main__":
    asyncio.run(_main())
