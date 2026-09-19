"""Regole di riconoscimento IMPARATE per i movimenti bancari (19/09/2026).

Il titolare vede un movimento in estratto conto che il motore generico
(`app.services.categorizzazione_movimenti`) riconosce solo genericamente (es.
"Commissioni bancarie") e vuole dire esplicitamente a chi appartiene (es.
"questo e' di Nexi"). Questo router:

- crea la regola a partire dalla causale di un movimento reale scelto
  dall'utente (il pattern si estrae ripulendo riferimenti/date/importi
  variabili, `estrai_pattern_da_causale`) e la applica subito a quel
  movimento;
- lista ed elimina le regole salvate. Eliminare una regola non tocca i
  movimenti gia' assegnati da essa (vedi `app.services
  .regole_riconoscimento_banca`): smette solo di applicarsi ai prossimi.

L'applicazione ai PROSSIMI movimenti (import ed eventuale ricategorizzazione
massiva) passa dal motore unico in `app.services.categorizzazione_movimenti`
e da `app/routers/bank/estratto_conto.py`, non da qui.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import Database
from app.utils.dependencies import get_current_admin_user
from app.utils.error_handler import handle_errors
from app.services.categorizzazione_movimenti import categorizza_movimento_bancario
from app.services.regole_riconoscimento_banca import (
    crea_regola,
    elimina_regola,
    estrai_pattern_da_causale,
    lista_regole,
)

router = APIRouter()


def _nome_admin(admin: Dict[str, Any]) -> Optional[str]:
    return admin.get("email") or admin.get("name") or admin.get("user_id")


@router.get("")
@handle_errors
async def get_regole_riconoscimento(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> List[Dict[str, Any]]:
    """Elenco delle regole salvate, piu' recenti prima."""
    db = Database.get_db()
    return await lista_regole(db)


@router.post("/da-movimento/{movimento_id}")
@handle_errors
async def crea_regola_da_movimento(
    movimento_id: str,
    data: Dict[str, Any],
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Crea una regola dalla causale di un movimento reale e la applica subito
    a quel movimento; i prossimi movimenti con causale simile la useranno
    dal prossimo import (o dalla prossima ricategorizzazione).

    Corpo: ``entita_tipo`` ("fornitore" | "categoria"), ``entita_id`` /
    ``entita_nome`` (a chi si riferisce; per un fornitore, dall'anagrafica
    esistente ``GET /api/suppliers``), ``categoria`` (opzionale).
    """
    db = Database.get_db()
    movimento = await db["estratto_conto_movimenti"].find_one({"id": movimento_id}, {"_id": 0})
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento non trovato")

    causale = movimento.get("descrizione_originale") or movimento.get("descrizione") or ""
    pattern = estrai_pattern_da_causale(causale)
    if not pattern:
        raise HTTPException(
            status_code=400,
            detail="Il movimento non ha una causale da cui imparare un pattern",
        )

    try:
        regola = await crea_regola(
            db,
            pattern=pattern,
            entita_tipo=data.get("entita_tipo"),
            entita_id=data.get("entita_id"),
            entita_nome=data.get("entita_nome"),
            categoria=data.get("categoria"),
            creata_da=_nome_admin(_admin),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Applicata subito al movimento che l'ha originata: e' il motivo per cui
    # il titolare l'ha scelto, non ha senso fargli aspettare il prossimo import.
    esito = categorizza_movimento_bancario(causale, movimento.get("importo") or 0, regole=[regola])
    campi_movimento: Dict[str, Any] = {
        "categoria_auto": True,
        "categoria_auto_motivo": esito.motivo,
        "regola_riconoscimento_id": regola["id"],
    }
    if esito.categoria:
        campi_movimento["categoria"] = esito.categoria
    if esito.fornitore_id:
        campi_movimento["fornitore_id"] = esito.fornitore_id
        campi_movimento["fornitore"] = esito.fornitore_nome
    await db["estratto_conto_movimenti"].update_one({"id": movimento_id}, {"$set": campi_movimento})

    return {"success": True, "regola": regola, "movimento_aggiornato": campi_movimento}


@router.delete("/{regola_id}")
@handle_errors
async def elimina_regola_riconoscimento(
    regola_id: str,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Elimina la regola. I movimenti gia' categorizzati da essa restano
    come sono: nessun tocco retroattivo, smette solo di applicarsi ai
    prossimi movimenti."""
    db = Database.get_db()
    eliminata = await elimina_regola(db, regola_id)
    if not eliminata:
        raise HTTPException(status_code=404, detail="Regola non trovata")
    return {"success": True}
