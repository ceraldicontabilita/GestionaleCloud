"""
Mittenti Attendibili — configurazione mittenti email/PEC per import automatico.
Collection: mittenti_attendibili
Prefix: /api/mittenti

Canali supportati: "pec" (Aruba PEC), "gmail" (Gmail ceraldigroupsrl)
Tipi documenti: fattura_xml, cedolino, f24, verbale, pagopa, inps, inail, paypal
"""
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
from typing import Optional

from app.database import get_database

router = APIRouter()


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# Mittenti di default (pre-caricati al primo avvio)
MITTENTI_DEFAULT = [
    # ── PEC ────────────────────────────────────────────────────────────────
    {
        "canale": "pec",
        "pattern": "@pec.fatturapa.it",
        "descrizione": "SDI — Sistema di Interscambio (fatture elettroniche)",
        "tipo_documento": "fattura_xml",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "pec",
        "pattern": "sdi@pec.fatturapa.it",
        "descrizione": "SDI — indirizzo diretto",
        "tipo_documento": "fattura_xml",
        "attivo": True,
        "builtin": True,
    },
    # ── Gmail ───────────────────────────────────────────────────────────────
    {
        "canale": "gmail",
        "pattern": "f.ferrantini@",
        "descrizione": "Commercialista Ferrantini — cedolini e comunicazioni",
        "tipo_documento": "cedolino",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "gmail",
        "pattern": "rosaria.marotta@",
        "descrizione": "Commercialista Marotta — cedolini e comunicazioni",
        "tipo_documento": "cedolino",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "gmail",
        "pattern": "partenopay@ext.comune.napoli.it",
        "descrizione": "PagoPA Napoli — verbali e tributi",
        "tipo_documento": "pagopa",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "gmail",
        "pattern": "inpscomunica@postacert.inps.gov.it",
        "descrizione": "INPS — comunicazioni (NON cedolini)",
        "tipo_documento": "inps",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "gmail",
        "pattern": "notifica.acc.campania@pec.agenziariscossione.gov.it",
        "descrizione": "Agenzia Riscossione Campania",
        "tipo_documento": "cartella_esattoriale",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "gmail",
        "pattern": "no_reply@agenziariscossione.gov.it",
        "descrizione": "Agenzia Riscossione — notifiche",
        "tipo_documento": "cartella_esattoriale",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "gmail",
        "pattern": "auto_napoli@massivo.pec.inail.it",
        "descrizione": "INAIL Napoli",
        "tipo_documento": "inail",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "gmail",
        "pattern": "assistenza@paypal.it",
        "descrizione": "PayPal — ricevute pagamenti",
        "tipo_documento": "paypal",
        "attivo": True,
        "builtin": True,
    },
    {
        "canale": "gmail",
        "pattern": "noreply-checkout@ricevute.pagopa.it",
        "descrizione": "PagoPA — ricevute verbali CdS",
        "tipo_documento": "pagopa",
        "attivo": True,
        "builtin": True,
    },
]

TIPO_LABELS = {
    "fattura_xml": "Fattura XML (SDI)",
    "cedolino": "Cedolino / Busta paga",
    "f24": "Modello F24",
    "verbale": "Verbale / Bollo auto",
    "pagopa": "PagoPA",
    "inps": "Comunicazione INPS",
    "inail": "Comunicazione INAIL",
    "paypal": "Ricevuta PayPal",
    "cartella_esattoriale": "Cartella esattoriale",
    "generico": "Documento generico",
}

CANALE_LABELS = {
    "pec": "PEC Aruba (fatturazioneceraldi@pec.it)",
    "gmail": "Gmail (ceraldigroupsrl@gmail.com)",
}


async def _ensure_defaults(db: AsyncIOMotorDatabase):
    """Inserisce i mittenti di default se la collection è vuota."""
    count = await db["mittenti_attendibili"].count_documents({})
    if count == 0:
        now = datetime.utcnow()
        docs = [{**m, "created_at": now, "updated_at": now} for m in MITTENTI_DEFAULT]
        await db["mittenti_attendibili"].insert_many(docs)
        await db["mittenti_attendibili"].create_index("pattern", unique=True)


@router.get("")
async def lista_mittenti(
    canale: Optional[str] = None,
    attivo: Optional[bool] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    await _ensure_defaults(db)
    filtro = {}
    if canale:
        filtro["canale"] = canale
    if attivo is not None:
        filtro["attivo"] = attivo
    cursor = db["mittenti_attendibili"].find(filtro).sort([("canale", 1), ("tipo_documento", 1)])
    items = [_oid(doc) async for doc in cursor]
    return {
        "items": items,
        "totale": len(items),
        "tipo_labels": TIPO_LABELS,
        "canale_labels": CANALE_LABELS,
    }


@router.post("")
async def crea_mittente(data: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    await _ensure_defaults(db)
    pattern = data.get("pattern", "").strip()
    if not pattern:
        raise HTTPException(400, "Campo 'pattern' obbligatorio")
    if not data.get("canale") in ("pec", "gmail"):
        raise HTTPException(400, "Campo 'canale' deve essere 'pec' o 'gmail'")

    existing = await db["mittenti_attendibili"].find_one({"pattern": pattern})
    if existing:
        raise HTTPException(409, f"Pattern '{pattern}' già presente")

    doc = {
        "canale": data["canale"],
        "pattern": pattern,
        "descrizione": data.get("descrizione", ""),
        "tipo_documento": data.get("tipo_documento", "generico"),
        "attivo": data.get("attivo", True),
        "builtin": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = await db["mittenti_attendibili"].insert_one(doc)
    return {"ok": True, "_id": str(result.inserted_id)}


@router.put("/{mid}")
async def aggiorna_mittente(mid: str, data: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["mittenti_attendibili"].find_one({"_id": ObjectId(mid)})
    if not doc:
        raise HTTPException(404, "Mittente non trovato")

    aggiornamenti = {"updated_at": datetime.utcnow()}
    for campo in ("descrizione", "tipo_documento", "attivo", "canale"):
        if campo in data:
            aggiornamenti[campo] = data[campo]
    # Pattern modificabile solo se non builtin
    if "pattern" in data and not doc.get("builtin"):
        aggiornamenti["pattern"] = data["pattern"].strip()

    await db["mittenti_attendibili"].update_one({"_id": ObjectId(mid)}, {"$set": aggiornamenti})
    return {"ok": True}


@router.delete("/{mid}")
async def elimina_mittente(mid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["mittenti_attendibili"].find_one({"_id": ObjectId(mid)})
    if not doc:
        raise HTTPException(404, "Mittente non trovato")
    if doc.get("builtin"):
        raise HTTPException(400, "I mittenti di sistema non possono essere eliminati, solo disattivati")
    await db["mittenti_attendibili"].delete_one({"_id": ObjectId(mid)})
    return {"ok": True}


@router.get("/check")
async def check_mittente(
    from_addr: str,
    canale: str = "pec",
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Verifica se un indirizzo email è attendibile."""
    await _ensure_defaults(db)
    from_lower = from_addr.lower()
    cursor = db["mittenti_attendibili"].find({"canale": canale, "attivo": True})
    async for m in cursor:
        if m["pattern"].lower() in from_lower:
            return {"attendibile": True, "mittente": _oid(m)}
    return {"attendibile": False}
