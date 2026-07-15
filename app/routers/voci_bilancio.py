"""Voci di bilancio inserite manualmente — Capitale e riserve, immobilizzazioni
non tracciate da cespiti (saldi di apertura, avviamento, ecc.), e in generale
tutte le voci di uno stato patrimoniale che il sistema non può derivare da
prima nota/fatture/cedolini. Richiesta utente 15/07/2026: "posso inserire il
fondo di riserva legale... le immobilizzazioni materiali... immateriali...
tutte le voci che possono comporre un bilancio di esercizio".

Usa SOLO i codici del piano dei conti CEE ufficiale (regola vincolante
CLAUDE.md), ristretti alle voci di Stato Patrimoniale (macro-gruppi
Immobilizzazioni/Capitale e riserve/Risultati portati a nuovo) — non ha senso
inserire qui una voce di Conto Economico.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4

from app.database import Database
from app.utils.error_handler import handle_errors
from app.services.piano_conti_ufficiale import CONTI_UFFICIALI, sezione_di

router = APIRouter()

COLLECTION = "voci_bilancio_manuali"

# Macro-gruppi di Stato Patrimoniale che ha senso inserire a mano: le
# immobilizzazioni (immateriali/materiali/finanziarie, per saldi di apertura o
# voci non tracciate da cespiti/fatture XML) e il patrimonio netto (capitale,
# riserve, risultati portati a nuovo). Non i debiti/crediti/liquidità
# (calcolati da prima nota e fatture) né alcuna voce di Conto Economico.
MACRO_AMMESSI = {"03", "05", "07", "23", "25"}


class VoceBilancioInput(BaseModel):
    codice_cee: str
    importo: float
    anno: int
    note: Optional[str] = None


def _valida_codice(codice_cee: str) -> tuple:
    info = sezione_di(codice_cee)
    if not info or info[0] != "SP" or codice_cee[:2] not in MACRO_AMMESSI:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Codice CEE '{codice_cee}' non valido per una voce di bilancio manuale: "
                f"ammessi solo i macro-gruppi {sorted(MACRO_AMMESSI)} "
                "(immobilizzazioni, capitale e riserve, risultati portati a nuovo)."
            ),
        )
    return info


@router.get("/codici-disponibili")
@handle_errors
async def get_codici_disponibili() -> Dict[str, Any]:
    """Elenco dei codici CEE ufficiali inseribili qui, per popolare la Select in UI."""
    codici = [
        {"codice_cee": codice, "descrizione": descrizione, "macro": codice[:2]}
        for codice, descrizione in CONTI_UFFICIALI.items()
        if codice[:2] in MACRO_AMMESSI
    ]
    return {"codici": sorted(codici, key=lambda c: c["codice_cee"])}


@router.get("/{anno}")
@handle_errors
async def get_voci_bilancio(anno: int) -> Dict[str, Any]:
    db = Database.get_db()
    voci = await db[COLLECTION].find({"anno": anno}, {"_id": 0}).sort("codice_cee", 1).to_list(500)
    for v in voci:
        v["descrizione"] = CONTI_UFFICIALI.get(v["codice_cee"], v["codice_cee"])
        info = sezione_di(v["codice_cee"])
        v["gruppo"] = info[1] if info else None

    totale_immobilizzazioni = sum(v["importo"] for v in voci if v["codice_cee"][:2] in ("03", "05", "07"))
    totale_patrimonio_netto = sum(v["importo"] for v in voci if v["codice_cee"][:2] in ("23", "25"))

    return {
        "anno": anno,
        "voci": voci,
        "totale_immobilizzazioni": round(totale_immobilizzazioni, 2),
        "totale_patrimonio_netto": round(totale_patrimonio_netto, 2),
    }


@router.post("/")
@handle_errors
async def upsert_voce_bilancio(input_data: VoceBilancioInput) -> Dict[str, Any]:
    """Crea o aggiorna la voce per (codice_cee, anno) — una sola voce per
    codice/anno, coerente con come un bilancio ufficiale riporta un solo saldo
    per conto e per esercizio."""
    _valida_codice(input_data.codice_cee)
    db = Database.get_db()

    esistente = await db[COLLECTION].find_one(
        {"codice_cee": input_data.codice_cee, "anno": input_data.anno}
    )
    now = datetime.now(timezone.utc).isoformat()

    if esistente:
        await db[COLLECTION].update_one(
            {"id": esistente["id"]},
            {"$set": {
                "importo": input_data.importo,
                "note": input_data.note,
                "updated_at": now,
            }},
        )
        voce_id = esistente["id"]
    else:
        voce_id = str(uuid4())
        await db[COLLECTION].insert_one({
            "id": voce_id,
            "codice_cee": input_data.codice_cee,
            "anno": input_data.anno,
            "importo": input_data.importo,
            "note": input_data.note,
            "created_at": now,
            "updated_at": now,
        })

    return {"id": voce_id, "aggiornata": bool(esistente)}


@router.delete("/{voce_id}")
@handle_errors
async def delete_voce_bilancio(voce_id: str) -> Dict[str, Any]:
    db = Database.get_db()
    esito = await db[COLLECTION].delete_one({"id": voce_id})
    if esito.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Voce non trovata")
    return {"eliminata": True}
