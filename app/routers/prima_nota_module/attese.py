"""
Fatture attese (annunciate dalle notifiche email Aruba).

Endpoint sotto /api/prima-nota:
  GET  /attese                → elenco attese non ancora riscontrate
  POST /attese/conferma       → registra l'ANTICIPO in prima nota (cassa/banca)
  POST /attese/scan           → lancia subito la scansione delle notifiche
  POST /attese/{id}/annulla   → scarta un'attesa (falso positivo/notifica doppia)

Registrazione (scelta utente "A2"): con metodo fornitore certo l'anticipo
viene registrato in automatico dallo scanner; qui resta la conferma
manuale per i casi misto/sconosciuto e la gestione delle attese. Il
movimento anticipato porta il flag anticipo_da_email e il riferimento
ATTESA-{id}; quando l'XML vero viene importato, riscontra_fattura_attesa
lo aggancia alla fattura senza creare doppioni.
"""
import logging
from datetime import datetime, timezone
from typing import Dict

from fastapi import Body, HTTPException, Query

from app.database import Database
from app.services.aruba_notifiche import COLL_ATTESE, registra_anticipo

logger = logging.getLogger(__name__)


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

    try:
        movimento = await registra_anticipo(db, attesa_id, metodo, fonte="ui_provvisori")
    except ValueError as e:
        codice = 409 if "già confermata" in str(e) else 400
        raise HTTPException(status_code=codice, detail=str(e))

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
