"""Invoices Emesse router - Issued invoices."""
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from fastapi.responses import HTMLResponse
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user
from app.utils.ruoli import richiedi_admin

logger = logging.getLogger(__name__)
router = APIRouter()

# Mappa campo canonico (italiano) -> alternative osservate nel codice
# (inglesi/legacy). Il router non ha mai avuto uno schema: chiunque scrive
# qui può usare nomi diversi, e i lettori contabili (IVA a debito, bilancio,
# dashboard, piano conti) fanno fallback manuali e incoerenti — imponibile/
# iva in alcuni lettori non hanno fallback inglese, rischio di IVA a debito
# sottostimata silenziosamente per un documento con solo taxable_amount/vat.
# Piano residuo op.16 (PIANO_CONSOLIDAMENTO_TRACKING.md, in cronologia git): qui si
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


# Liste leggere: il testo XML resta fuori e si legge per id (download, vista).
_SENZA_XML = {"_id": 0, "xml_raw": 0, "righe": 0}


@router.get("", summary="Fatture emesse, piu' recenti prima")
async def get_invoices_emesse(
    anno: Optional[int] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Elenco con il riepilogo delle pastiglie: quante, per quanto, quante
    agganciate al corrispettivo e quante aspettano una scelta."""
    db = Database.get_db()
    filtro: Dict[str, Any] = {"anno": anno} if anno else {}
    fatture = await db["fatture_emesse"].find(filtro, _SENZA_XML).to_list(5000)
    fatture.sort(key=lambda f: (str(f.get("data_fattura") or f.get("date") or ""),
                                str(f.get("numero_fattura") or "")), reverse=True)
    per_stato: Dict[str, int] = {}
    for f in fatture:
        chiave = (f.get("corrispettivo") or {}).get("stato") or "ATTESO"
        per_stato[chiave] = per_stato.get(chiave, 0) + 1
    totale = sum(float(f.get("totale") or 0) for f in fatture)
    return {"fatture": fatture, "riepilogo": {
        "numero": len(fatture), "totale": round(totale, 2), "per_stato": per_stato}}


@router.get("/clienti", summary="Anagrafica clienti")
async def get_clienti(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    from app.services.fatture_emesse import COLL_CLIENTI

    db = Database.get_db()
    clienti = await db[COLL_CLIENTI].find({}, {"_id": 0}).to_list(5000)
    clienti.sort(key=lambda c: str(c.get("denominazione") or "").upper())
    fatture = await db["fatture_emesse"].find(
        {}, {"_id": 0, "cliente_id": 1, "totale": 1}).to_list(5000)
    per_cliente: Dict[str, Dict[str, float]] = {}
    for f in fatture:
        voce = per_cliente.setdefault(f.get("cliente_id") or "", {"fatture": 0, "totale": 0.0})
        voce["fatture"] += 1
        voce["totale"] += float(f.get("totale") or 0)
    for c in clienti:
        voce = per_cliente.get(c.get("id"), {"fatture": 0, "totale": 0.0})
        c["fatture"] = int(voce["fatture"])
        c["totale_fatturato"] = round(voce["totale"], 2)
    return {"clienti": clienti, "numero": len(clienti)}


@router.post("/riallinea", summary="Rete: passive sbagliate e agganci aperti")
async def riallinea_fatture_emesse(
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    from app.services.fatture_emesse import riallinea

    return await riallinea(Database.get_db())


async def _fattura_con_xml(invoice_id: str) -> Dict[str, Any]:
    db = Database.get_db()
    fattura = await db["fatture_emesse"].find_one({"id": invoice_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura emessa non trovata")
    if not fattura.get("xml_raw"):
        raise HTTPException(status_code=404, detail="Questa fattura non ha l'XML originale in archivio")
    return fattura


def _nome_file(fattura: Dict[str, Any], estensione: str) -> str:
    import re

    numero = re.sub(r"[^A-Za-z0-9._-]+", "-", str(fattura.get("numero_fattura") or "")).strip("-")
    return f"fattura_emessa_{numero or 'senza-numero'}_{fattura.get('data_fattura') or ''}.{estensione}"


@router.get("/{invoice_id}/vista", summary="La fattura leggibile (foglio ASSO)")
async def vista_fattura_emessa(
    invoice_id: str = Path(...),
    scarica: bool = Query(False),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    from app.routers.fatture_module.crud import html_fattura_da_xml

    fattura = await _fattura_con_xml(invoice_id)
    html = html_fattura_da_xml(fattura["xml_raw"].encode("utf-8"), 0, invoice_id)
    if not html:
        raise HTTPException(status_code=422, detail="XML non trasformabile: scarica l'originale")
    intestazioni = ({"Content-Disposition": f'attachment; filename="{_nome_file(fattura, "html")}"'}
                    if scarica else None)
    return HTMLResponse(content=html, headers=intestazioni)


@router.get("/{invoice_id}/corrispettivi-vicini", summary="Candidati per la scelta a mano")
async def corrispettivi_vicini(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """I corrispettivi da tre giorni prima a tre dopo il giorno dello scontrino."""
    from datetime import date, timedelta
    from app.services.fatture_emesse import corrispettivi_del_giorno

    db = Database.get_db()
    fattura = await db["fatture_emesse"].find_one({"id": invoice_id}, _SENZA_XML)
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura emessa non trovata")
    giorno = (fattura.get("scontrino") or {}).get("data") or fattura.get("data_fattura")
    try:
        centro = date.fromisoformat(str(giorno)[:10])
    except ValueError:
        return {"giorno": giorno, "corrispettivi": []}
    trovati: List[Dict[str, Any]] = []
    for scarto in range(-3, 4):
        trovati += await corrispettivi_del_giorno(db, (centro + timedelta(days=scarto)).isoformat())
    return {"giorno": giorno, "corrispettivi": trovati}


@router.post("/{invoice_id}/corrispettivo", summary="Il titolare sceglie il corrispettivo")
async def scegli_corrispettivo_fattura(
    invoice_id: str = Path(...),
    corpo: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    from app.services.fatture_emesse import scegli_corrispettivo

    esito = await scegli_corrispettivo(Database.get_db(), invoice_id, str(corpo.get("corrispettivo_id") or ""))
    if not esito.get("success"):
        raise HTTPException(status_code=404, detail=esito.get("errore"))
    return esito


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