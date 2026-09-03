"""
reclami_fornitori.py
--------------------
Gestione reclami e non conformità fornitori per HACCP.
Ogni ricezione merce respinta o non conforme genera automaticamente un reclamo.
I reclami si accumulano: se un fornitore supera la soglia, viene sospeso automaticamente.

Collection: reclami_fornitori
Stati: aperto → in_gestione → risolto | archiviato
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.lotti.db import database as db

router = APIRouter(prefix="/reclami-fornitori", tags=["reclami_fornitori"])
logger = logging.getLogger(__name__)

# ── Soglie sospensione automatica ─────────────────────────────────────────────
SOGLIA_SOSPENSIONE = 3  # reclami aperti negli ultimi N giorni
SOGLIA_GIORNI = 90  # finestra temporale
SOGLIA_CRITICA = 1  # un solo reclamo critico → sospensione immediata


class ReclameIn(BaseModel):
    fornitore_id: Optional[str] = None
    fornitore_nome: str
    prodotto: str
    tipo: str = (
        "non_conformita"  # non_conformita | merce_sbagliata | merce_danneggiata | prezzo_errato | ritardo_consegna
    )
    gravita: str = "media"  # bassa | media | alta | critica
    descrizione: str
    azione_richiesta: Optional[str] = ""
    ricezione_id: Optional[str] = None  # FK → ricezioni_merce.id
    foto_url: Optional[str] = None
    operatore: Optional[str] = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("")
async def crea_reclamo(payload: ReclameIn):
    """Crea un nuovo reclamo / segnalazione non conformità fornitore."""
    ora = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid.uuid4()),
        "fornitore_id": payload.fornitore_id or "",
        "fornitore_nome": payload.fornitore_nome,
        "prodotto": payload.prodotto,
        "tipo": payload.tipo,
        "gravita": payload.gravita,
        "descrizione": payload.descrizione,
        "azione_richiesta": payload.azione_richiesta or "",
        "ricezione_id": payload.ricezione_id,
        "foto_url": payload.foto_url,
        "operatore": payload.operatore or "",
        "stato": "aperto",
        "risposta_fornitore": "",
        "risolto_il": None,
        "creato_il": ora.isoformat(),
        "aggiornato_il": ora.isoformat(),
    }
    await db.reclami_fornitori.insert_one(doc)
    doc.pop("_id", None)

    # Aggiorna contatore reclami nel record fornitore
    await _aggiorna_contatore_fornitore(payload.fornitore_nome, payload.gravita)

    logger.info(f"[Reclamo] {payload.fornitore_nome} — {payload.tipo} ({payload.gravita})")
    return {"ok": True, "reclamo": doc}


@router.get("")
async def lista_reclami(
    fornitore: Optional[str] = None,
    stato: Optional[str] = None,
    gravita: Optional[str] = None,
    limit: int = 100,
):
    query = {}
    if fornitore:
        query["fornitore_nome"] = {"$regex": fornitore, "$options": "i"}
    if stato:
        query["stato"] = stato
    if gravita:
        query["gravita"] = gravita

    docs = (
        await db.reclami_fornitori.find(query, {"_id": 0})
        .sort("creato_il", -1)
        .limit(limit)
        .to_list(limit)
    )
    return {"reclami": docs, "totale": len(docs)}


@router.get("/statistiche/{fornitore_nome}")
async def statistiche_reclami_fornitore(fornitore_nome: str):
    """Storico reclami per un fornitore — usato nella qualifica."""
    giorni_90 = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    tutti = (
        await db.reclami_fornitori.find(
            {"fornitore_nome": {"$regex": fornitore_nome[:20], "$options": "i"}}, {"_id": 0}
        )
        .sort("creato_il", -1)
        .to_list(200)
    )

    recenti = [r for r in tutti if r.get("creato_il", "") >= giorni_90]
    critici = [r for r in recenti if r.get("gravita") == "critica"]
    aperti = [r for r in tutti if r.get("stato") == "aperto"]

    return {
        "fornitore": fornitore_nome,
        "totale": len(tutti),
        "ultimi_90gg": len(recenti),
        "critici_90gg": len(critici),
        "aperti": len(aperti),
        "rischio": (
            "alto"
            if len(critici) >= 1 or len(recenti) >= SOGLIA_SOSPENSIONE
            else "medio" if len(recenti) >= 2 else "basso"
        ),
        "ultimi": tutti[:5],
    }


@router.patch("/{reclamo_id}/stato")
async def aggiorna_stato_reclamo(
    reclamo_id: str,
    stato: str,
    risposta_fornitore: Optional[str] = None,
    operatore: Optional[str] = None,
):
    """Aggiorna stato del reclamo: aperto → in_gestione → risolto."""
    ora = datetime.now(timezone.utc)
    upd = {
        "stato": stato,
        "aggiornato_il": ora.isoformat(),
    }
    if risposta_fornitore is not None:
        upd["risposta_fornitore"] = risposta_fornitore
    if stato in ("risolto", "archiviato"):
        upd["risolto_il"] = ora.isoformat()
        if operatore:
            upd["risolto_da"] = operatore

    r = await db.reclami_fornitori.update_one({"id": reclamo_id}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "Reclamo non trovato")
    return {"ok": True, "stato": stato}


@router.get("/check-sospensione/{fornitore_nome}")
async def check_sospensione_automatica(fornitore_nome: str):
    """
    Controlla se un fornitore deve essere sospeso automaticamente.
    Regole: >= 3 reclami negli ultimi 90 giorni OPPURE 1 reclamo critico.
    """
    stats = await statistiche_reclami_fornitore(fornitore_nome)
    deve_sospendere = (
        stats["critici_90gg"] >= SOGLIA_CRITICA or stats["ultimi_90gg"] >= SOGLIA_SOSPENSIONE
    )

    if deve_sospendere:
        # Aggiorna stato qualifica fornitore
        motivo = (
            f"Sospensione automatica: {stats['critici_90gg']} reclami critici"
            if stats["critici_90gg"] >= 1
            else f"Sospensione automatica: {stats['ultimi_90gg']} reclami negli ultimi 90 giorni"
        )
        await db.fornitori_qualifica.update_one(
            {
                "$or": [
                    {"nome": {"$regex": fornitore_nome[:15], "$options": "i"}},
                    {"fornitore": {"$regex": fornitore_nome[:15], "$options": "i"}},
                ]
            },
            {
                "$set": {
                    "stato": "sospeso",
                    "motivo_sospensione": motivo,
                    "sospeso_il": datetime.now(timezone.utc).isoformat(),
                    "reclami_90gg": stats["ultimi_90gg"],
                }
            },
            upsert=False,
        )
        logger.warning(f"[Qualifica] {fornitore_nome} SOSPESO — {motivo}")

    return {
        "fornitore": fornitore_nome,
        "deve_sospendere": deve_sospendere,
        "statistiche": stats,
    }


# ── Helper ────────────────────────────────────────────────────────────────────


async def _aggiorna_contatore_fornitore(fornitore_nome: str, gravita: str):
    """Aggiorna il contatore reclami nel record fornitore e triggera check sospensione."""
    try:
        await db.fornitori_anagrafica.update_one(
            {"nome": {"$regex": fornitore_nome[:15], "$options": "i"}},
            {
                "$inc": {"reclami_totali": 1},
                "$set": {"ultimo_reclamo_il": datetime.now(timezone.utc).isoformat()},
            },
        )
        # Controlla sospensione automatica in background
        if gravita in ("critica", "alta"):
            await check_sospensione_automatica(fornitore_nome)
    except Exception as _e:
        logger.debug(f"[Reclamo] Aggiornamento fornitore fallito: {_e}")


async def crea_reclamo_da_ricezione(ricezione_doc: dict):
    """
    Chiamata automaticamente quando una ricezione viene registrata come NON conforme.
    Crea il reclamo e triggera il check sospensione.
    """
    gravita_map = {
        False: "alta",  # temperatura non conforme = alta
        True: "media",  # altri problemi = media
    }
    temp_ok = ricezione_doc.get("temperatura_conforme", True)
    imb_ok = ricezione_doc.get("imballaggio_integro", True)
    eth_ok = ricezione_doc.get("etichetta_conforme", True)

    if ricezione_doc.get("accettato", True) and ricezione_doc.get("conforme", True):
        return  # Ricezione ok, nessun reclamo

    tipo_problema = (
        "merce_danneggiata"
        if not imb_ok
        else (
            "non_conformita"
            if not temp_ok
            else "merce_sbagliata" if not eth_ok else "non_conformita"
        )
    )
    gravita = "alta" if not temp_ok else ("media" if not imb_ok else "bassa")

    problemi = []
    if not temp_ok:
        problemi.append(f"temperatura fuori range ({ricezione_doc.get('temperatura_ricezione')}°C)")
    if not imb_ok:
        problemi.append("imballaggio non integro")
    if not eth_ok:
        problemi.append("etichetta non conforme")
    if not ricezione_doc.get("accettato", True):
        problemi.append("merce respinta")

    payload = ReclameIn(
        fornitore_id=ricezione_doc.get("fornitore_id", ""),
        fornitore_nome=ricezione_doc.get("fornitore_nome", ""),
        prodotto=ricezione_doc.get("prodotto", ""),
        tipo=tipo_problema,
        gravita=gravita,
        descrizione=f"Ricezione non conforme: {', '.join(problemi)}. "
        + (ricezione_doc.get("azione_correttiva") or ""),
        azione_richiesta=ricezione_doc.get("azione_correttiva", ""),
        ricezione_id=ricezione_doc.get("id"),
        operatore=ricezione_doc.get("operatore", ""),
    )
    await crea_reclamo(payload)
