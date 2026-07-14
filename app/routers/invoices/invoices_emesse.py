"""Invoices Emesse router - Issued invoices."""
from fastapi import APIRouter, Body, Depends, Path, status
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Mappa campo canonico (italiano) -> alternative osservate nel codice
# (inglesi/legacy). Il router non ha mai avuto uno schema: chiunque scrive
# qui può usare nomi diversi, e i lettori contabili (IVA a debito, bilancio,
# dashboard, piano conti) fanno fallback manuali e incoerenti — imponibile/
# iva in alcuni lettori non hanno fallback inglese, rischio di IVA a debito
# sottostimata silenziosamente per un documento con solo taxable_amount/vat.
# Piano residuo op.16 (memoria/PIANO_CONSOLIDAMENTO_TRACKING.md): qui si
# normalizzano SOLO le nuove scritture, senza migrare i documenti già in
# produzione (richiede verifica dati reali, fuori scope senza accesso DB).
_MAPPA_CAMPI_CANONICI = {
    "numero_fattura": ("number", "numero", "invoice_number"),
    "data_fattura": ("date", "invoice_date", "data_emissione", "data_documento"),
    "cliente": ("customer", "client", "cliente_denominazione"),
    "imponibile": ("taxable_amount", "totale_imponibile"),
    "iva": ("vat", "totale_iva"),
    "totale": ("total_amount", "importo_totale"),
}


def normalizza_fattura_emessa(data: Dict[str, Any]) -> Dict[str, Any]:
    """Riempie i campi canonici italiani da eventuali alternative in
    ingresso, senza rimuovere i campi originali (retrocompatibilità con i
    lettori esistenti che controllano entrambi i nomi)."""
    out = dict(data)
    for canonico, alternative in _MAPPA_CAMPI_CANONICI.items():
        if out.get(canonico) in (None, ""):
            for alt in alternative:
                if out.get(alt) not in (None, ""):
                    out[canonico] = out[alt]
                    break
    return out


@router.get(
    "",
    summary="Get issued invoices"
)
async def get_invoices_emesse(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get list of issued invoices."""
    db = Database.get_db()
    invoices = await db["fatture_emesse"].find({}, {"_id": 0}).sort("date", -1).to_list(500)
    return invoices


@router.get(
    "/{invoice_id}",
    summary="Get issued invoice"
)
async def get_invoice_emessa(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get a specific issued invoice."""
    db = Database.get_db()
    invoice = await db["fatture_emesse"].find_one({"id": invoice_id}, {"_id": 0})
    return invoice or {}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create issued invoice"
)
async def create_invoice_emessa(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Create an issued invoice."""
    db = Database.get_db()
    data = normalizza_fattura_emessa(data)
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    data["user_id"] = current_user["user_id"]
    await db["fatture_emesse"].insert_one(data.copy())
    return {"message": "Invoice created", "id": data["id"]}


@router.delete(
    "/{invoice_id}",
    summary="Delete issued invoice"
)
async def delete_invoice_emessa(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Delete an issued invoice."""
    db = Database.get_db()
    await db["fatture_emesse"].delete_one({"id": invoice_id})
    return {"message": "Invoice deleted"}