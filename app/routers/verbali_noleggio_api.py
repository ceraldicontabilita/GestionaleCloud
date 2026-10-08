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
    # Stessa quietanza (stesso PDF) rimandata: il verbale non si riscrive, ma la nota e la
    # proposta di trattenuta si completano se mancavano (quietanza caricata prima che il
    # driver fosse assegnato); con tutto gia' al suo posto non nasce niente di nuovo.
    ripetuta = bool(impronta and verbale.get("quietanza_ricevuta") and verbale.get("quietanza_hash") == impronta)

    # La quietanza aggiunge una prova, non ne toglie: una prova documentale o bancaria
    # gia' presente non si perde rimandando i dati senza PDF, e lo stato sale a
    # «riconciliato» solo con documento E banca (stessa regola di
    # `applica_pagamento_a_verbale`).
    documentale = bool(
        impronta or verbale.get("pagato_documentalmente") is True or verbale.get("quietanza_ricevuta") is True
        or verbale.get("ricevuta_pagopa_id") or verbale.get("paypal_transaction_id")
    )
    banca = bool(verbale.get("banca_verificata") is True or verbale.get("movimento_banca_id"))
    if documentale and banca:
        stato, stato_pratica = "riconciliato", "RICONCILIATO_BANCA"
    elif documentale:
        stato, stato_pratica = "pagato", "PAGATO_DOCUMENTALE"
    else:
        stato, stato_pratica = "pagato_attesa_quietanza", "ATTESA_QUIETANZA"
    update = {
        "stato": stato,
        "stato_pratica": stato_pratica,
        "quietanza_ricevuta": bool(impronta or verbale.get("quietanza_ricevuta") is True),
        "pagato_documentalmente": documentale,
        "data_pagamento": data_pagamento,
        "metodo_pagamento": data.get("metodo", "bollettino_manuale"),
        # Importi come testo Decimal al centesimo (mai float binario).
        "importo_pagato": str(importo),
    }
    if impronta:
        update["quietanza_pdf"] = contenuto_b64
        update["quietanza_filename"] = data.get("filename", "quietanza.pdf")
        update["quietanza_hash"] = impronta

    if not ripetuta:
        await db[COLLECTION].update_one({"id": verbale_id}, {"$set": update})

    # Nota per il consulente e PROPOSTA di trattenuta (una per verbale): nascono solo a
    # verbale pagato **con quietanza** (PDF, importo certo), mai senza PDF ne' alla sola
    # assegnazione del driver; la conferma resta del titolare
    # (`proponi_trattenuta_verbale_pagato`, l'unico punto che le scrive).
    from app.services.trattenute_verbali_service import proponi_trattenuta_verbale_pagato

    proposta = await proponi_trattenuta_verbale_pagato(
        db, verbale if ripetuta else {**verbale, **update},
        importo_pagato=importo, data_pagamento=data_pagamento, fonte="upload_quietanza_manuale",
    )
    creato = bool(proposta["nota_creata"] or proposta["trattenuta_creata"])

    if ripetuta and not creato:
        return {"success": True, "duplicato": True,
                "message": f"Quietanza gia' caricata per il verbale {verbale.get('numero_verbale', '')}"}
    return {"success": True, "duplicato": False,
            "message": f"Quietanza caricata per verbale {verbale.get('numero_verbale','')}"}


# NB: la route /stats che era qui è stata rimossa: era shadowata al 100%
# dalla versione in verbali_noleggio.py (registrato prima sotto lo stesso
# prefisso) e non veniva mai raggiunta.
