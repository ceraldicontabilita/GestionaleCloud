"""Metodi di pagamento fornitore: elenco da compilare, importa, esporta.

Il motore sta in `services/metodi_pagamento_fornitori.py`; qui ci sono le
rotte. La scrittura e' admin e in `dry_run` per difetto: tocca l'anagrafica
di quasi duecento fornitori, e da li' dipende in quale registro finisce ogni
fattura.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.database import Database
from app.services import metodi_pagamento_fornitori as motore
from app.utils.dependencies import get_current_admin_user

router = APIRouter()


@router.get("/mancanti")
async def fornitori_senza_metodo() -> Dict[str, Any]:
    """Chi non ha ancora un metodo, dal piu' importante.

    L'ordine e' per numero di fatture: compilare il primo della lista sblocca
    piu' righe di Prima Nota di tutti gli altri messi insieme.
    """
    senza = await motore.mancanti(Database.get_db())
    return {
        "totale": len(senza),
        "fatture_bloccate": sum(r["fatture"] for r in senza),
        "metodi_ammessi": list(motore.METODI_AMMESSI),
        "fornitori": senza,
    }


@router.get("/esporta")
async def esporta_metodi() -> Dict[str, Any]:
    """I metodi come stanno adesso, nel formato del file versionato.

    Da salvare in `app/data/metodi_pagamento_fornitori.json`: e' la copia che
    sopravvive al database.
    """
    return await motore.esporta(Database.get_db())


@router.post("/importa")
async def importa_metodi(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    dry_run: bool = True,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Applica i metodi all'anagrafica: dal corpo della richiesta, o dal file.

    `dry_run=true` per difetto dice soltanto cosa cambierebbe. Un metodo vuoto
    non cancella quello gia' impostato, e un valore fuori dai tre ammessi viene
    rifiutato invece di entrare in archivio come parola libera.
    """
    esito = await motore.importa(
        Database.get_db(), payload, dry_run=dry_run,
        attore=str((_admin or {}).get("username") or "admin"),
    )
    if esito["metodi_rifiutati"] and not esito["applicati"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Nessun metodo applicato: "
                f"{len(esito['metodi_rifiutati'])} valori non ammessi. "
                f"Ammessi: {', '.join(motore.METODI_AMMESSI)}."
            ),
        )
    return esito


@router.get("/storico")
async def storico_metodi(limite: int = 200) -> Dict[str, Any]:
    """Chi ha cambiato cosa, e quando.

    Serve perche' la prima volta i metodi sono spariti senza lasciare traccia:
    non si e' potuto sapere ne' quando ne' per mano di quale processo.
    """
    if not isinstance(limite, int):
        limite = 200
    righe = await Database.get_db()[motore.COLLEZIONE_STORICO].find(
        {}, {"_id": 0}
    ).to_list(5000)
    righe.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return {"totale": len(righe), "modifiche": righe[:limite]}
