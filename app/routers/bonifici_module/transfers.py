"""
Bonifici Module - CRUD operazioni sui bonifici.
"""
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import io
import base64
import zipfile
import re as _re_zip

from app.database import Database, Collections
from app.db_collections import COLL_BONIFICI_TRANSFERS
from app.document_repository import metadata_projection
from .classification import classifica_destinazione_dipendente


async def list_transfers(
    job_id: Optional[str] = None,
    search: Optional[str] = None,
    ordinante: Optional[str] = None,
    beneficiario: Optional[str] = None,
    year: Optional[str] = None,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """Lista bonifici con filtri."""
    db = Database.get_db()
    
    query: Dict[str, Any] = {}
    if job_id:
        query['job_id'] = job_id
    
    import re as _re
    ands = []
    if search:
        safe_s = _re.escape(search)
        ands.append({'$or': [
            {'ordinante.nome': {'$regex': safe_s, '$options': 'i'}},
            {'beneficiario.nome': {'$regex': safe_s, '$options': 'i'}},
            {'causale': {'$regex': safe_s, '$options': 'i'}},
            {'cro_trn': {'$regex': safe_s, '$options': 'i'}},
            {'rif_interno': {'$regex': safe_s, '$options': 'i'}},
        ]})
    if ordinante:
        ands.append({'ordinante.nome': {'$regex': _re.escape(ordinante), '$options': 'i'}})
    if beneficiario:
        ands.append({'beneficiario.nome': {'$regex': _re.escape(beneficiario), '$options': 'i'}})
    if year:
        ands.append({'data': {'$regex': f'^{year}-'}})
    
    if ands:
        query['$and'] = ands
    
    transfers = await db.bonifici_transfers.find(
        query, metadata_projection(COLL_BONIFICI_TRANSFERS)
    ).sort('data', -1).to_list(limit)
    dipendenti = await db[Collections.EMPLOYEES].find(
        {}, {'_id': 0, 'id': 1, 'nome': 1, 'cognome': 1, 'nome_completo': 1, 'iban': 1}
    ).to_list(5000)
    for transfer in transfers:
        transfer.update(classifica_destinazione_dipendente(transfer, dipendenti))
    await _arricchisci_con_fattura(db, transfers)
    return transfers


def _centesimi(valore: Any) -> Optional[int]:
    from app.services.payment_invoice_matching import money_cents

    return money_cents(abs(float(valore))) if valore not in (None, "") else None


async def _arricchisci_con_fattura(db, transfers: List[Dict[str, Any]]) -> None:
    """Numero della fattura collegata e se il bonifico la salda o e' un acconto.

    L'esito si dice con i numeri della fattura (netto di ritenuta incluso), mai dedotto dal testo:
    ``intero`` = importo uguale al dovuto al centesimo, ``acconto`` = meno del dovuto,
    ``eccede`` = piu' del dovuto (da guardare). Un bonifico con la fattura gia' collegata non e' uno
    stipendio: la pagina non gli propone il periodo.
    """
    id_per_bonifico: Dict[str, List[str]] = {}
    for t in transfers:
        ids = [str(i) for i in (t.get("fattura_ids") or []) if i]
        for campo in ("fattura_id", "fattura_associata_id"):
            if t.get(campo) and str(t[campo]) not in ids:
                ids.append(str(t[campo]))
        if ids and t.get("fattura_associata"):
            id_per_bonifico[str(t.get("id"))] = ids
    if not id_per_bonifico:
        return
    tutti = sorted({i for ids in id_per_bonifico.values() for i in ids})
    candidati = tutti + [int(i) for i in tutti if i.isdigit()]
    fatture = {
        str(f.get("id")): f for f in await db[Collections.INVOICES].find(
            {"id": {"$in": candidati}},
            {"_id": 0, "id": 1, "invoice_number": 1, "total_amount": 1, "importo_ritenuta": 1, "supplier_name": 1},
        ).to_list(len(candidati) + 10)
    }
    for t in transfers:
        ids = id_per_bonifico.get(str(t.get("id")))
        if not ids:
            continue
        trovate = [fatture[i] for i in ids if i in fatture]
        if not trovate:
            continue
        t["fattura_numero"] = t.get("fattura_numero") or ", ".join(
            str(f.get("invoice_number") or "") for f in trovate if f.get("invoice_number"))
        t["fattura_id_prima"] = str(trovate[0].get("id"))
        if len(trovate) == 1:
            dovuto = _centesimi(trovate[0].get("total_amount"))
            ritenuta = _centesimi(trovate[0].get("importo_ritenuta")) or 0
            pagato = _centesimi(t.get("importo"))
            if dovuto is not None and pagato is not None:
                atteso = dovuto - ritenuta
                t["fattura_dovuto_cents"] = atteso
                t["fattura_esito"] = "intero" if pagato == atteso else ("acconto" if pagato < atteso else "eccede")


async def count_transfers(
    job_id: Optional[str] = None, anno: Optional[int] = None,
) -> Dict[str, int]:
    """Conta i bonifici, dell'anno se richiesto (la pagina manda `anno`:
    prima lo ignorava e il contatore diceva il totale di tutti gli anni)."""
    db = Database.get_db()
    query: Dict[str, Any] = {'job_id': job_id} if job_id else {}
    if anno:
        query['data'] = {'$regex': f'^{int(anno)}-'}
    count = await db.bonifici_transfers.count_documents(query)
    return {'count': count}


async def delete_transfer(transfer_id: str) -> Dict[str, bool]:
    """Elimina un bonifico."""
    db = Database.get_db()
    result = await db.bonifici_transfers.delete_one({'id': transfer_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Transfer not found')
    return {'deleted': True}


async def get_bonifico_pdf(transfer_id: str):
    """Alias: l'originale si apre da `/api/originale/bonifico/{id}` (DRV-04)."""
    from app.routers.originale import reindirizza_a_originale

    return reindirizza_a_originale("bonifico", transfer_id)


async def bulk_delete(job_id: Optional[str] = None) -> Dict[str, int]:
    """Elimina tutti i bonifici di un job."""
    db = Database.get_db()
    query = {'job_id': job_id} if job_id else {}
    result = await db.bonifici_transfers.delete_many(query)
    return {'deleted': result.deleted_count}


async def update_transfer(transfer_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiorna un bonifico."""
    db = Database.get_db()
    
    bonifico = await db.bonifici_transfers.find_one({"id": transfer_id})
    if not bonifico:
        raise HTTPException(status_code=404, detail="Bonifico non trovato")
    
    update_fields = {}
    allowed_fields = ["causale", "importo", "data", "note", "categoria", 
                      "salario_associato", "operazione_salario_id",
                      "fattura_associata", "fattura_id"]
    
    for field in allowed_fields:
        if field in data:
            update_fields[field] = data[field]
    
    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.bonifici_transfers.update_one({"id": transfer_id}, {"$set": update_fields})
    
    return {"success": True, "updated": list(update_fields.keys())}


async def download_zip_by_year(year: str) -> StreamingResponse:
    """Scarica uno ZIP con tutti i PDF originali dei bonifici di un anno."""
    db = Database.get_db()
    transfers = await db.bonifici_transfers.find(
        {'data': {'$regex': f'^{year}-'}},
        {'_id': 0, 'id': 1, 'data': 1, 'source_file': 1, 'pdf_data': 1, 'cro_trn': 1}
    ).to_list(10000)

    con_pdf = [t for t in transfers if t.get('pdf_data')]
    if not con_pdf:
        raise HTTPException(status_code=404, detail=f"Nessun PDF di bonifico disponibile per l'anno {year}")

    buf = io.BytesIO()
    used_names = set()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for t in con_pdf:
            try:
                pdf_bytes = base64.b64decode(t['pdf_data'])
            except Exception:
                continue
            base_name = t.get('source_file') or f"bonifico_{t.get('cro_trn') or t.get('id')}.pdf"
            base_name = _re_zip.sub(r'[^A-Za-z0-9._-]', '_', base_name)
            if not base_name.lower().endswith('.pdf'):
                base_name += '.pdf'
            name = base_name
            i = 1
            while name in used_names:
                name = f"{base_name.rsplit('.pdf', 1)[0]}_{i}.pdf"
                i += 1
            used_names.add(name)
            zf.writestr(name, pdf_bytes)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename=bonifici_{year}.zip'}
    )
