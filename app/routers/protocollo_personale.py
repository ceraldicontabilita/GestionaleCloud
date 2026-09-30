"""Protocollo personale e familiare (MINI-07). Solo amministratore.

Import del registro xlsx da Drive (simulazione per difetto, in sottofondo, stato
in ``sistema_stato``), ricerca AND con snippet e ponte informativo. Nessun
endpoint scrive in contabilita'; nessuno cancella: ``rimuovi`` marca la riga.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.database import Database
from app.services import protocollo_personale as servizio
from app.utils.dependencies import get_current_admin_user

router = APIRouter(dependencies=[Depends(get_current_admin_user)])

MAX_PDF_BYTE = 30 * 1024 * 1024
STATO_PER_CODICE = {"NON_TROVATO": 404, "IMPRONTA_DIVERSA": 422, "TESTO_ASSENTE": 422, "SHA256_ASSENTE": 422}


def _errore(stato: int, codice: str, messaggio: str, dettagli: Optional[Dict[str, Any]] = None) -> HTTPException:
    return HTTPException(status_code=stato, detail={"code": codice, "message": messaggio, "details": dettagli or {}})


def _attore(admin: Dict[str, Any]) -> str:
    return str(admin.get("email") or admin.get("id") or "admin")


def _o_errore(esito: Dict[str, Any]) -> Dict[str, Any]:
    if not esito["success"]:
        raise _errore(STATO_PER_CODICE.get(esito["code"], 400), esito["code"], esito["message"])
    return esito


class Rimozione(BaseModel):
    motivo: str = Field(..., min_length=3, max_length=300)


@router.get("", summary="Cerca nel protocollo: tutte le parole (AND), senza accenti, piu' recenti per primi")
async def cerca(
    q: Optional[str] = Query(None, max_length=200, description="es. «tari enzo 2023», «cosap 2019», una targa"),
    anno: Optional[int] = Query(None, ge=1900, le=2100),
    tipo_documento: Optional[str] = Query(None, max_length=80),
    ambito: Optional[str] = Query(None, description="personale_familiare | aziendale | da_verificare"),
    includi_rimossi: bool = Query(False),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    return await servizio.cerca(Database.get_db(), q=q, anno=anno, tipo_documento=tipo_documento, ambito=ambito,
                                includi_rimossi=includi_rimossi, limit=limit, offset=offset)


@router.post("/import", summary="Importa il registro xlsx da Drive (in sottofondo; simulazione per difetto)")
async def importa(
    file_id: str = Query(..., min_length=10, max_length=120, description="Id Drive dell'xlsx"),
    dry_run: bool = Query(True, description="True = conta soltanto (simulazione)"),
) -> Dict[str, Any]:
    return await servizio.avvia(Database.get_db(), file_id, dry_run=dry_run)


@router.get("/import/stato", summary="Esito dell'ultimo import e dell'ultima simulazione")
async def stato_import() -> Dict[str, Any]:
    return await servizio.stato(Database.get_db())


@router.get("/{anno}/{progressivo}/collegati", summary="Documenti della contabilita' collegati (sola lettura)")
async def collegati(anno: int, progressivo: int) -> Dict[str, Any]:
    riga = await servizio.dettaglio(Database.get_db(), f"{anno}/{progressivo}")
    if riga is None:
        raise _errore(404, "NON_TROVATO", "protocollo non trovato", {"numero": f"{anno}/{progressivo}"})
    return riga["collegati"]


@router.post("/{anno}/{progressivo}/rimuovi", summary="Segna il protocollo come rimosso (mai cancellato)")
async def rimuovi(anno: int, progressivo: int, corpo: Rimozione,
                  admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    return _o_errore(await servizio.segna_rimosso(Database.get_db(), f"{anno}/{progressivo}", corpo.motivo,
                                                  attore=_attore(admin)))


@router.post("/{anno}/{progressivo}/ripristina", summary="Riporta in archivio un protocollo rimosso")
async def ripristina(anno: int, progressivo: int,
                     admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    return _o_errore(await servizio.ripristina(Database.get_db(), f"{anno}/{progressivo}", attore=_attore(admin)))


@router.post("/{anno}/{progressivo}/testo",
             summary="Aggancia il testo del PDF originale (solo se l'SHA-256 e' quello registrato)")
async def aggancia_testo(anno: int, progressivo: int, file: UploadFile = File(...)) -> Dict[str, Any]:
    contenuto = await file.read(MAX_PDF_BYTE + 1)
    if len(contenuto) > MAX_PDF_BYTE:
        raise _errore(413, "FILE_TROPPO_GRANDE", "il PDF supera il limite", {"limite_byte": MAX_PDF_BYTE})
    return _o_errore(await servizio.allega_testo_pdf(Database.get_db(), f"{anno}/{progressivo}", contenuto))


@router.get("/{anno}/{progressivo}", summary="Dettaglio di un protocollo, con i documenti collegati")
async def dettaglio(anno: int, progressivo: int) -> Dict[str, Any]:
    riga = await servizio.dettaglio(Database.get_db(), f"{anno}/{progressivo}")
    if riga is None:
        raise _errore(404, "NON_TROVATO", "protocollo non trovato", {"numero": f"{anno}/{progressivo}"})
    return riga
