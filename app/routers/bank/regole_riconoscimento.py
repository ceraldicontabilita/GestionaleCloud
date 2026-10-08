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
    carica_regole,
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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


_CAMPI_IMPORTO_VERBALE = ("importo_verificato", "importo", "totale")
_LIMITE_CANDIDATI = 8


def _candidati_per_importo(righe, cents: int, tipo: str, campi, etichetta, rotta) -> List[Dict[str, Any]]:
    """Documenti con lo stesso importo al centesimo: solo candidati, mai un collegamento."""
    from app.services.payment_invoice_matching import money_cents

    trovati = []
    for r in righe:
        valore = next((r.get(c) for c in campi if r.get(c) not in (None, "")), None)
        if money_cents(valore) != cents:
            continue
        ident = str(r.get("id") or r.get("_id") or "")
        if ident:
            trovati.append({"tipo": tipo, "id": ident, "etichetta": etichetta(r), "rotta": rotta(ident)})
    return trovati[:_LIMITE_CANDIDATI]


@router.get("/proposte/{movimento_id}")
@handle_errors
async def proposte_per_movimento(
    movimento_id: str,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Che cos'e' questo movimento? Lettura del motore unico e candidati documentali.

    Sola lettura: non scrive niente e non collega niente (nessuna entita' si associa per
    solo importo). Il collegamento si fa in «Classifica e collega» (indice operazioni).
    """
    from app.services.nexi_carta import _periodo_addebito, is_addebito_nexi
    from app.services.payment_invoice_matching import money_cents
    from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE

    db = Database.get_db()
    mov = await db["estratto_conto_movimenti"].find_one(
        {"$or": [{"id": movimento_id}, {"_id": movimento_id}]}, {"_id": 0})
    if not mov:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    causale = mov.get("descrizione_originale") or mov.get("descrizione") or ""
    esito = categorizza_movimento_bancario(causale, mov.get("importo") or 0, regole=await carica_regole(db))
    cents = money_cents(abs(float(mov.get("importo") or 0)))
    data_mov = str(mov.get("data") or mov.get("data_contabile") or "")[:10]

    nexi = None
    if is_addebito_nexi(mov):
        nexi = {"periodo_spese": _periodo_addebito(data_mov), "riconciliato": bool(mov.get("nexi_riconciliato")),
                "nota": ("Quadra con l'estratto Nexi del periodo." if mov.get("nexi_riconciliato")
                         else "Addebito mensile della carta: si riscontra con l'estratto Nexi del periodo "
                              "(se manca, va caricato in Documenti > Import).")}

    candidati: List[Dict[str, Any]] = []
    if cents:
        verbali = await db["verbali_noleggio"].find({}, {"_id": 0, "id": 1, "numero_verbale": 1, "numero": 1,
            "targa": 1, "veicolo_targa": 1, "importo_verificato": 1, "importo": 1, "totale": 1}).to_list(5000)
        cartelle = await db["cartelle_pagamento"].find({}, {"_id": 0, "id": 1, "numero_cartella": 1,
            "ente_creditore": 1, "totale": 1}).to_list(2000)
        fatture = await db["invoices"].find(FILTRO_NON_PAGATE, {"_id": 0, "id": 1, "supplier_name": 1,
            "invoice_number": 1, "total_amount": 1}).to_list(5000)
        candidati += _candidati_per_importo(
            verbali, cents, "verbale", _CAMPI_IMPORTO_VERBALE,
            lambda r: f"Verbale {r.get('numero_verbale') or r.get('numero') or 'senza numero'} - {r.get('targa') or r.get('veicolo_targa') or 'targa n.d.'}",
            lambda i: "/verbali-noleggio")
        candidati += _candidati_per_importo(
            cartelle, cents, "cartella", ("totale",),
            lambda r: f"Cartella {r.get('numero_cartella')} - {r.get('ente_creditore') or 'ente n.d.'}",
            lambda i: "/riconciliazione/pagopa")
        candidati += _candidati_per_importo(
            fatture, cents, "fattura", ("total_amount",),
            lambda r: f"Fattura {r.get('invoice_number') or 's.n.'} - {r.get('supplier_name') or 'fornitore n.d.'} (non pagata)",
            lambda i: f"/fatture?invoice_id={i}")
    return {
        "movimento": {"id": movimento_id, "data": data_mov, "descrizione": causale, "importo_cents": cents},
        "riconoscimento": {"categoria": esito.categoria, "motivo": esito.motivo, "ambiguo": bool(esito.ambiguo)},
        "nexi": nexi,
        "candidati": candidati,
        "classifica": f"/riconciliazione/banca?movimento={movimento_id}",
        "avviso": "Candidati per importo al centesimo: nessun collegamento e' applicato da qui.",
    }


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
