"""
Router per Verbali Noleggio - Endpoint dettaglio e gestione completa.
"""
# Endpoint rimossi il 14/07/2026 (piano residuo op.10, zero chiamanti verificati):
# alert-pagamenti, associa-driver, bulk-assegna-pagamento, lista, note-consulente,
# riconcilia-completo (route; il servizio sottostante resta vivo via scheduler),
# scan-gmail (route; il servizio sottostante resta vivo via scheduler),
# {verbale_id} PUT, cerca-pagamento, ricevuta-pdf — codice conservato nella
# cronologia git. upload-quietanza NON rimosso: caso incerto, lasciato montato
# per prudenza su decisione utente.
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION = "verbali_noleggio"


# Il dettaglio verbale vive esclusivamente in verbali_noleggio.py.
# La vecchia seconda route /dettaglio/{numero_verbale:path} è stata rimossa
# in Fase 0B: dipendeva dall'ordine di registrazione e duplicava la logica.

# NB: la route /pdf/{numero_verbale} che era qui è stata rimossa: era
# shadowata al 100% dalla versione equivalente in verbali_noleggio.py
# (registrato prima sotto lo stesso prefisso) e non veniva mai raggiunta.


@router.post("/{verbale_id}/upload-quietanza")
@handle_errors
async def upload_quietanza_verbale(verbale_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Upload manuale della quietanza/bollettino per un verbale.
    Accetta: pdf_base64, importo_pagato, data_pagamento, metodo.
    """
    db = Database.get_db()

    verbale = await db[COLLECTION].find_one({"id": verbale_id})
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")

    update = {
        "stato": "pagato",
        "quietanza_ricevuta": True,
        "data_pagamento": data.get("data_pagamento"),
        "metodo_pagamento": data.get("metodo", "bollettino_manuale"),
        "importo_pagato": float(data.get("importo_pagato", 0)),
    }

    if data.get("pdf_base64"):
        update["quietanza_pdf"] = data["pdf_base64"]
        update["quietanza_filename"] = data.get("filename", "quietanza.pdf")

    await db[COLLECTION].update_one({"id": verbale_id}, {"$set": update})

    # Crea nota presenze per consulente del lavoro
    driver_id = verbale.get("driver_id") or verbale.get("driver_cf")
    if driver_id:
        from datetime import datetime, timezone
        dt = datetime.now(timezone.utc)
        mese_nota = dt.month + 1 if dt.month < 12 else 1
        anno_nota = dt.year if dt.month < 12 else dt.year + 1

        nota = {
            "id": str(__import__("uuid").uuid4()),
            "dipendente_id": driver_id,
            "dipendente_nome": verbale.get("driver", ""),
            "tipo": "trattenuta_verbale",
            "mese": mese_nota,
            "anno": anno_nota,
            "importo": float(data.get("importo_pagato", 0)),
            "descrizione": f"TRATTENUTA VERBALE {verbale.get('numero_verbale','')} - Targa {verbale.get('targa','')} - Pagato {data.get('data_pagamento','')}",
            "evidenza": True,
            "inviato_consulente": False,
            "verbale_id": verbale_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db["note_presenze_consulente"].insert_one(nota)

        # Anche in trattenute_dipendenti: PROPOSTA di trattenuta con il
        # ciclo di vita completo (proposta → confermata → comunicata → ...).
        from app.services.trattenute_verbali_service import costruisci_trattenuta_da_verbale
        verbale_aggiornato = {**verbale, **update}
        trattenuta = await costruisci_trattenuta_da_verbale(
            db, verbale_aggiornato,
            data_pagamento=data.get("data_pagamento"),
            importo_pagato=float(data.get("importo_pagato", 0)),
            fonte="upload_quietanza_manuale",
        )
        await db["trattenute_dipendenti"].insert_one(trattenuta)

        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="trattenute_verbali", azione="proposta_creata",
            entita_id=trattenuta["id"], entita_collection="trattenute_dipendenti",
            db=db, nuovo_stato={"stato": trattenuta["stato"]},
            fonte="upload_quietanza_manuale",
            dettaglio=(
                f"Proposta trattenuta per verbale {verbale.get('numero_verbale','')} "
                f"— €{trattenuta['importo_da_recuperare']:.2f}, "
                f"cedolino suggerito {trattenuta['mese_cedolino_suggerito']}"
            ),
        )

    return {"success": True, "message": f"Quietanza caricata per verbale {verbale.get('numero_verbale','')}"}


# NB: la route /stats che era qui è stata rimossa: era shadowata al 100%
# dalla versione in verbali_noleggio.py (registrato prima sotto lo stesso
# prefisso) e non veniva mai raggiunta.
