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
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any
import logging

from app.database import Database
from app.utils.dependencies import get_current_admin_user
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


def _errore(status: int, code: str, message: str, **details: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, "details": details})


def _importo_pagato(valore: Any) -> Decimal:
    """Importo pagato come Decimal al centesimo; assente o non valido e' un errore, mai 0."""
    if valore in (None, "") or isinstance(valore, bool):
        raise _errore(400, "IMPORTO_OBBLIGATORIO", "importo_pagato obbligatorio")
    try:
        testo = str(valore).strip().replace("EUR", "").replace("€", "").replace(" ", "")
        if "," in testo:
            testo = testo.replace(".", "").replace(",", ".")
        importo = Decimal(testo)
    except InvalidOperation as exc:
        raise _errore(400, "IMPORTO_NON_VALIDO", "importo_pagato non e' un importo", valore=str(valore)) from exc
    if not importo.is_finite() or importo <= 0 or importo != importo.quantize(Decimal("0.01")):
        raise _errore(400, "IMPORTO_NON_VALIDO", "importo_pagato deve essere positivo, al centesimo", valore=str(valore))
    return importo


def _data_pagamento_iso(valore: Any) -> str:
    testo = str(valore or "").strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(testo[:10], formato).date().isoformat()
        except ValueError:
            continue
    raise _errore(400, "DATA_PAGAMENTO_NON_VALIDA", "data_pagamento: gg/mm/aaaa o aaaa-mm-gg", valore=testo)


@router.post("/{verbale_id}/upload-quietanza")
@handle_errors
async def upload_quietanza_verbale(
    verbale_id: str,
    data: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Upload manuale della quietanza/bollettino di un verbale (solo admin).

    Accetta: pdf_base64, importo_pagato (obbligatorio, al centesimo), data_pagamento
    (obbligatoria), metodo. L'importo deve coincidere con quello del verbale: se
    differisce e' un 409, mai un pagamento registrato a meta'. Con il PDF il verbale
    e' «pagato» (prova documentale), senza resta «pagato_attesa_quietanza». Il
    secondo invio della stessa quietanza (stesso hash) non duplica nulla: niente
    seconda nota presenze, niente seconda proposta di trattenuta.
    """
    from app.services.payment_invoice_matching import amounts_equal_to_cent

    db = Database.get_db()
    verbale = await db[COLLECTION].find_one({"id": verbale_id})
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")

    importo = _importo_pagato(data.get("importo_pagato"))
    data_pagamento = _data_pagamento_iso(data.get("data_pagamento"))
    if verbale.get("importo") not in (None, "") and not amounts_equal_to_cent(verbale.get("importo"), importo):
        raise _errore(409, "IMPORTO_DIVERSO_DAL_VERBALE",
                      "L'importo pagato non coincide con quello del verbale",
                      importo_pagato=str(importo), importo_verbale=str(verbale.get("importo")))

    contenuto_b64 = data.get("pdf_base64")
    impronta = None
    if contenuto_b64:
        import base64
        import hashlib
        from app.utils.upload_validation import verifica_pdf_reale
        try:
            contenuto = base64.b64decode(contenuto_b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise _errore(400, "PDF_NON_VALIDO", "pdf_base64 non e' base64") from exc
        verifica_pdf_reale(contenuto, data.get("filename", "quietanza.pdf"))
        impronta = hashlib.sha256(contenuto).hexdigest()
        if verbale.get("quietanza_ricevuta") and verbale.get("quietanza_hash") == impronta:
            return {"success": True, "duplicato": True,
                    "message": f"Quietanza gia' caricata per il verbale {verbale.get('numero_verbale', '')}"}

    update = {
        "stato": "pagato" if impronta else "pagato_attesa_quietanza",
        "quietanza_ricevuta": bool(impronta),
        "pagato_documentalmente": bool(impronta),
        "data_pagamento": data_pagamento,
        "metodo_pagamento": data.get("metodo", "bollettino_manuale"),
        # Importi come testo Decimal al centesimo (mai float binario).
        "importo_pagato": str(importo),
    }
    if impronta:
        update["quietanza_pdf"] = contenuto_b64
        update["quietanza_filename"] = data.get("filename", "quietanza.pdf")
        update["quietanza_hash"] = impronta

    await db[COLLECTION].update_one({"id": verbale_id}, {"$set": update})

    # Crea nota presenze per consulente del lavoro (una per verbale)
    driver_id = verbale.get("driver_id") or verbale.get("driver_cf")
    if driver_id:
        from datetime import timezone
        dt = datetime.now(timezone.utc)
        mese_nota = dt.month + 1 if dt.month < 12 else 1
        anno_nota = dt.year if dt.month < 12 else dt.year + 1

        nota_id = f"nota_trattenuta_verbale_{verbale_id}"
        await db["note_presenze_consulente"].update_one(
            {"id": nota_id},
            {"$set": {
                "id": nota_id,
                "dipendente_id": driver_id,
                "dipendente_nome": verbale.get("driver", ""),
                "tipo": "trattenuta_verbale",
                "mese": mese_nota,
                "anno": anno_nota,
                "importo": str(importo),
                "descrizione": f"TRATTENUTA VERBALE {verbale.get('numero_verbale','')} - Targa {verbale.get('targa','')} - Pagato {data_pagamento}",
                "evidenza": True,
                "verbale_id": verbale_id,
            }, "$setOnInsert": {"inviato_consulente": False, "created_at": dt.isoformat()}},
            upsert=True,
        )

        # Anche in trattenute_dipendenti: PROPOSTA di trattenuta con il ciclo di vita
        # completo (proposta -> confermata -> comunicata -> ...), una per verbale.
        gia = await db["trattenute_dipendenti"].find_one(
            {"verbale_id": verbale_id, "tipo": "verbale_multa"}, {"_id": 0, "id": 1})
        if not gia:
            from app.services.trattenute_verbali_service import costruisci_trattenuta_da_verbale
            verbale_aggiornato = {**verbale, **update}
            trattenuta = await costruisci_trattenuta_da_verbale(
                db, verbale_aggiornato,
                data_pagamento=data_pagamento,
                importo_pagato=float(importo),
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

    return {"success": True, "duplicato": False,
            "message": f"Quietanza caricata per verbale {verbale.get('numero_verbale','')}"}


# NB: la route /stats che era qui è stata rimossa: era shadowata al 100%
# dalla versione in verbali_noleggio.py (registrato prima sotto lo stesso
# prefisso) e non veniva mai raggiunta.
