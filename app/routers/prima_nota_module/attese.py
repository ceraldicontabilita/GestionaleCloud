"""
Fatture attese (annunciate dalle notifiche email Aruba).

Endpoint sotto /api/prima-nota:
  GET  /attese                → elenco attese non ancora riscontrate
  POST /attese/conferma       → registra l'ANTICIPO in prima nota (cassa/banca)
  POST /attese/scan           → lancia subito la scansione delle notifiche
  POST /attese/{id}/annulla   → scarta un'attesa (falso positivo/notifica doppia)

La conferma è la stessa filosofia dei Provvisori: il sistema suggerisce
(metodo del fornitore, motore unico), l'utente decide. Il movimento
anticipato porta il flag anticipo_da_email e il riferimento ATTESA-{id};
quando l'XML vero viene importato, riscontra_fattura_attesa lo aggancia
alla fattura senza creare doppioni.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import Body, HTTPException, Query

from app.database import Database
from app.services.aruba_notifiche import COLL_ATTESE

logger = logging.getLogger(__name__)

COLLECTION_PER_METODO = {"cassa": "prima_nota_cassa", "banca": "prima_nota_banca"}


async def lista_fatture_attese(anno: int = Query(None)) -> Dict:
    """Attese in corso (in_attesa_xml / da_verificare / confermata_anticipo)
    più le ultime riscontrate, per dare riscontro visivo che il giro funziona."""
    db = Database.get_db()
    query = {"stato": {"$in": ["in_attesa_xml", "da_verificare", "confermata_anticipo"]}}
    if anno:
        query["email_date"] = {"$regex": f"^{anno}"}
    attese = await db[COLL_ATTESE].find(
        query, {"_id": 0, "email_estratto": 0}
    ).sort("email_date", -1).to_list(200)

    riscontrate = await db[COLL_ATTESE].find(
        {"stato": "riscontrata"}, {"_id": 0, "email_estratto": 0}
    ).sort("riscontrata_at", -1).to_list(10)

    return {"attese": attese, "ultime_riscontrate": riscontrate,
            "totale_in_attesa": len(attese)}


async def conferma_fattura_attesa(data: Dict = Body(...)) -> Dict:
    """Registra in prima nota l'anticipo di una fattura annunciata.

    Body: {"attesa_id": "...", "metodo": "cassa"|"banca"}
    Atomico: il claim sull'attesa (stato in_attesa_xml → confermata_anticipo)
    impedisce il doppio click. Quando arriverà l'XML il movimento viene
    agganciato alla fattura vera (mai due movimenti).
    """
    db = Database.get_db()
    attesa_id = (data.get("attesa_id") or "").strip()
    metodo = (data.get("metodo") or "").strip().lower()
    if not attesa_id:
        raise HTTPException(status_code=400, detail="attesa_id obbligatorio")
    if metodo not in COLLECTION_PER_METODO:
        raise HTTPException(status_code=400, detail="metodo deve essere 'cassa' o 'banca'")

    now = datetime.now(timezone.utc).isoformat()
    movimento_id = str(uuid.uuid4())
    collection = COLLECTION_PER_METODO[metodo]

    # Claim atomico: solo un chiamante può confermare l'attesa
    attesa = await db[COLL_ATTESE].find_one_and_update(
        {"id": attesa_id, "stato": {"$in": ["in_attesa_xml", "da_verificare"]},
         "prima_nota_id": None},
        {"$set": {"stato": "confermata_anticipo", "metodo_confermato": metodo,
                  "prima_nota_id": movimento_id, "prima_nota_collection": collection,
                  "confermata_at": now}},
    )
    if not attesa:
        raise HTTPException(
            status_code=409,
            detail="Attesa già confermata, riscontrata o inesistente",
        )

    importo = float(attesa.get("importo") or 0)
    if importo <= 0:
        # Rollback del claim: senza importo non si registra niente
        await db[COLL_ATTESE].update_one(
            {"id": attesa_id},
            {"$set": {"stato": attesa.get("stato", "da_verificare"),
                      "prima_nota_id": None, "prima_nota_collection": None}},
        )
        raise HTTPException(status_code=400, detail="Attesa senza importo: completala prima")

    numero = attesa.get("numero_fattura") or "?"
    fornitore = (attesa.get("fornitore_nome") or "Fornitore")[:40]
    movimento = {
        "id": movimento_id,
        "data": attesa.get("data_documento") or (attesa.get("email_date") or now)[:10],
        "tipo": "uscita",
        "categoria": "Pagamento fornitore",
        "importo": importo,
        "descrizione": f"Pagamento fattura {numero} - {fornitore} (annunciata da email, XML in arrivo)",
        "riferimento": f"ATTESA-{attesa_id}",
        "numero_fattura": numero,
        "fornitore_piva": attesa.get("fornitore_piva"),
        "fattura_id": None,
        "fattura_attesa_id": attesa_id,
        "anticipo_da_email": True,
        "source": "fattura_attesa_email",
        "created_at": now,
    }
    await db[collection].insert_one(movimento.copy())
    movimento.pop("_id", None)

    # Audit
    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            "prima_nota", "conferma_attesa_email", attesa_id, COLL_ATTESE, db,
            nuovo_stato={"metodo": metodo, "importo": importo,
                         "numero_fattura": numero, "movimento_id": movimento_id},
            fonte="ui_provvisori",
            dettaglio=f"Anticipo fattura {numero} registrato in {metodo} da notifica email",
        )
    except Exception:
        logger.debug("Audit conferma attesa non registrato")

    return {"success": True, "movimento": movimento,
            "message": f"Anticipo registrato in {metodo}: verrà agganciato all'XML quando arriva"}


async def scan_notifiche_ora(giorni: int = Query(None)) -> Dict:
    """Lancia subito la scansione delle notifiche Aruba (di norma gira da sola
    col monitor email)."""
    db = Database.get_db()
    from app.services.aruba_notifiche import scan_notifiche_aruba, controlla_attese_scadute
    esito = await scan_notifiche_aruba(db, giorni=giorni)
    scadute = await controlla_attese_scadute(db)
    return {**esito, "attese_scadute": scadute}


async def annulla_fattura_attesa(attesa_id: str) -> Dict:
    """Scarta un'attesa (notifica doppia, fattura non nostra, ecc.).

    Se era stato registrato l'anticipo, il movimento NON viene toccato:
    va rimosso a mano dalla prima nota (scelta esplicita dell'utente).
    """
    db = Database.get_db()
    attesa = await db[COLL_ATTESE].find_one_and_update(
        {"id": attesa_id, "stato": {"$in": ["in_attesa_xml", "da_verificare", "confermata_anticipo"]}},
        {"$set": {"stato": "annullata",
                  "annullata_at": datetime.now(timezone.utc).isoformat()}},
    )
    if not attesa:
        raise HTTPException(status_code=404, detail="Attesa non trovata o già chiusa")
    avviso = None
    if attesa.get("prima_nota_id"):
        avviso = (
            f"L'anticipo in prima nota (movimento {attesa['prima_nota_id']}) "
            f"NON è stato cancellato: rimuovilo a mano se non serve"
        )
    return {"success": True, "avviso": avviso}
