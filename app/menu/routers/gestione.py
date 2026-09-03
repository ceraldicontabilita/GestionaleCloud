"""Gestione del menu (``admin`` e ``operatore``): catalogo, sale, QR/WiFi,
immagini, backup. Ripristino e migrazione: solo ``admin``."""
import asyncio
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.menu import catalogo, ordini, storage as st
from app.menu.auth import nome_utente, require_menu_admin, require_menu_gestione
from app.menu.models import (
    CategoryCreate, CategoryUpdate, ProductCreate, ProductUpdate, QRCodeConfigUpdate,
    SalaCreate, SalaUpdate, SubcategoryCreate, SubcategoryUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_IMMAGINE_BYTES = 10 * 1024 * 1024
TIPI_IMMAGINE = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _non_nulli(model) -> Dict[str, Any]:
    dati = model.model_dump(exclude_none=True)
    if not dati:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nessun dato da aggiornare")
    return dati


# ------------------------------------------------------------------ catalogo

@router.get("/prodotti", summary="Tutti i prodotti in elenco piatto")
async def prodotti():
    lista = await catalogo.prodotti_piatti()
    return {"products": lista, "total": len(lista)}


@router.post("/categorie", status_code=status.HTTP_201_CREATED)
async def crea_categoria(payload: CategoryCreate):
    return await catalogo.crea_categoria(payload.model_dump())


@router.put("/categorie/{categoria_id}")
async def aggiorna_categoria(categoria_id: int, payload: CategoryUpdate):
    doc = await catalogo.aggiorna_categoria(categoria_id, _non_nulli(payload))
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoria non trovata")
    return doc


@router.delete("/categorie/{categoria_id}", summary="Elimina categoria, sottocategorie e prodotti")
async def elimina_categoria(categoria_id: int):
    if not await catalogo.elimina_categoria(categoria_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoria non trovata")
    return {"success": True}


@router.post("/sottocategorie", status_code=status.HTTP_201_CREATED)
async def crea_sottocategoria(payload: SubcategoryCreate):
    doc = await catalogo.crea_sottocategoria(payload.model_dump())
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoria non trovata")
    return doc


@router.put("/sottocategorie/{sotto_id}")
async def aggiorna_sottocategoria(sotto_id: int, payload: SubcategoryUpdate):
    doc = await catalogo.aggiorna_sottocategoria(sotto_id, _non_nulli(payload))
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sottocategoria non trovata")
    return doc


@router.delete("/sottocategorie/{sotto_id}", summary="Elimina sottocategoria e prodotti")
async def elimina_sottocategoria(sotto_id: int):
    if not await catalogo.elimina_sottocategoria(sotto_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sottocategoria non trovata")
    return {"success": True}


@router.post("/prodotti", status_code=status.HTTP_201_CREATED)
async def crea_prodotto(payload: ProductCreate):
    doc = await catalogo.crea_prodotto(payload.model_dump())
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sottocategoria non trovata")
    return doc


@router.put("/prodotti/{prodotto_id}")
async def aggiorna_prodotto(prodotto_id: int, payload: ProductUpdate, subcategory_id: Optional[int] = None):
    dati = payload.model_dump(exclude_none=True)
    if subcategory_id is not None:
        dati["subcategory_id"] = subcategory_id
    if not dati:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nessun dato da aggiornare")
    doc = await catalogo.aggiorna_prodotto(prodotto_id, dati)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prodotto o sottocategoria non trovati")
    return doc


@router.delete("/prodotti/{prodotto_id}")
async def elimina_prodotto(prodotto_id: int):
    if not await catalogo.elimina_prodotto(prodotto_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prodotto non trovato")
    return {"success": True}


# ------------------------------------------------------------------ sale

@router.post("/sale", status_code=status.HTTP_201_CREATED)
async def crea_sala(payload: SalaCreate):
    adesso = st.adesso()
    doc = dict(payload.model_dump(), id=st.nuovo_id(), created_at=adesso, updated_at=adesso)
    return await st.inserisci(st.COLL_SALE, doc)


@router.put("/sale/{sala_id}")
async def aggiorna_sala(sala_id: str, payload: SalaUpdate):
    valori = dict(payload.model_dump(exclude_none=True), updated_at=st.adesso())
    doc = await st.aggiorna(st.COLL_SALE, {"id": sala_id}, valori)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sala non trovata")
    return doc


@router.delete("/sale/{sala_id}")
async def elimina_sala(sala_id: str):
    if not await st.elimina(st.COLL_SALE, {"id": sala_id}):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sala non trovata")
    return {"success": True}


# ------------------------------------------------------------------ QR code / WiFi

async def _config_qr() -> Dict[str, Any]:
    doc = await st.uno(st.COLL_QRCODE, {"id": st.ID_CONFIG_QR})
    if doc:
        return doc
    return {"id": st.ID_CONFIG_QR, "menu_url": "", "wifi": {"ssid": "", "password": "", "security": "WPA", "hidden": False}, "updated_at": None}


@router.get("/qrcode/config", summary="Configurazione QR menu e WiFi (con password: solo gestione)")
async def leggi_config_qr():
    return await _config_qr()


@router.put("/qrcode/config")
async def aggiorna_config_qr(payload: QRCodeConfigUpdate, utente=Depends(require_menu_gestione)):
    attuale = await _config_qr()
    if payload.menu_url is not None:
        attuale["menu_url"] = payload.menu_url.strip()
    if payload.wifi is not None:
        attuale["wifi"] = payload.wifi.model_dump()
    attuale["updated_at"] = st.adesso()
    attuale["updated_by"] = nome_utente(utente)
    await st.elimina(st.COLL_QRCODE, {"id": st.ID_CONFIG_QR})
    doc = await st.inserisci(st.COLL_QRCODE, attuale)
    return {"success": True, "config": doc}


# ------------------------------------------------------------------ immagini

@router.post("/immagini", status_code=status.HTTP_201_CREATED, summary="Carica un'immagine (deduplicata per contenuto)")
async def carica_immagine(file: UploadFile = File(...)):
    filename = os.path.basename(file.filename or "immagine")
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or ""
    if content_type not in TIPI_IMMAGINE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Formato non ammesso: usa JPG, PNG, WEBP o GIF")
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File vuoto")
    if len(content) > MAX_IMMAGINE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Immagine oltre 10 MB")
    doc = await st.salva_immagine(content, filename, content_type)
    return {"success": True, **doc}


@router.get("/immagini", summary="Immagini caricate")
async def elenco_immagini():
    docs = await st.tutti(st.COLL_IMMAGINI)
    docs.sort(key=lambda d: str(d.get("uploaded_at") or ""), reverse=True)
    return {"images": docs}


@router.delete("/immagini/{immagine_id}")
async def elimina_immagine(immagine_id: str):
    if not await st.elimina_immagine(immagine_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Immagine non trovata")
    return {"success": True}


# ------------------------------------------------------------------ backup

@router.get("/backup/esporta", summary="Esporta tutto il menu in JSON (con le immagini)")
async def esporta_backup():
    dati = await st.esporta_backup()
    nome = f"menu_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    return JSONResponse(content=dati, headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.post("/backup/ripristina", summary="Ripristina il menu da un backup JSON (solo admin)")
async def ripristina_backup(payload: Dict[str, Any] = Body(...), utente=Depends(require_menu_admin)):
    if payload.get("formato") != st.FORMATO_BACKUP:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Il file non e' un backup del menu di GestionaleCloud")
    esito = await st.ripristina_backup(payload)
    logger.info("Backup menu ripristinato da %s: %s", nome_utente(utente), esito)
    return {"success": True, "ripristinato": esito}


# ------------------------------------------------------------------ stato dati e migrazione

@router.get("/stato-dati", summary="Conteggi delle collezioni del menu")
async def stato_dati():
    return await st.stato_dati()


_jobs: Dict[str, Dict[str, Any]] = {}


async def _esegui_migrazione(job_id: str, dry_run: bool, con_immagini: bool) -> None:
    from app.menu.migrazione_menu import migra

    job = _jobs[job_id]
    job["status"] = "running"

    def _progress(nome: str, n: int) -> None:
        job["avanzamento"][nome] = n

    try:
        job["esito"] = await migra(
            os.environ["MENU_SUPABASE_URL"], os.environ["MENU_SUPABASE_KEY"],
            dry_run=dry_run, con_immagini=con_immagini, progress=_progress,
        )
        job["status"] = "done" if job["esito"]["coincide"] else "mismatch"
    except Exception as exc:
        logger.exception("Migrazione Menu fallita")
        job["status"] = "failed"
        job["errore"] = str(exc)[:500]
    finally:
        job["finito_il"] = datetime.now(timezone.utc).isoformat()


@router.post("/migrazione-menu", summary="Importa i dati dal vecchio Supabase dell'app Menu (solo admin)")
async def avvia_migrazione(payload: Dict[str, Any] = Body(default={}), utente=Depends(require_menu_admin)):
    if not (os.environ.get("MENU_SUPABASE_URL") and os.environ.get("MENU_SUPABASE_KEY")):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "MENU_SUPABASE_URL / MENU_SUPABASE_KEY non configurate su Render")
    if any(j["status"] == "running" for j in _jobs.values()):
        raise HTTPException(status.HTTP_409_CONFLICT, "Una migrazione e' gia' in corso")
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "id": job_id, "status": "queued", "dry_run": bool(payload.get("dry_run", False)),
        "con_immagini": bool(payload.get("con_immagini", True)),
        "avanzamento": {}, "avviato_il": datetime.now(timezone.utc).isoformat(), "avviato_da": nome_utente(utente),
    }
    asyncio.create_task(_esegui_migrazione(job_id, _jobs[job_id]["dry_run"], _jobs[job_id]["con_immagini"]))
    return _jobs[job_id]


@router.get("/migrazione-menu/{job_id}", summary="Stato di una migrazione")
async def stato_migrazione(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Migrazione non trovata")
    return job
