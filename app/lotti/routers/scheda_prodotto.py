"""Scheda prodotto: tutta la catena del piatto sotto un solo ID prodotto (PRD-000123).

piatto -> prezzo -> reparto -> ingredienti -> allergeni -> varianti -> aggiunte/rimozioni
-> costo ingredienti -> food cost -> disponibilita' -> foto -> valori nutrizionali
-> vendita sala -> vendita delivery -> QR.

Non e' un motore nuovo: ogni anello legge quello che c'e' gia' (food cost e margine della
ricetta, ``verifica_disponibilita_ricetta`` sui lotti, ``get_nutrizionali``, il ponte Menu per
codice e indirizzo). Un anello che non si sa calcolare e' ``None`` col motivo, mai un valore plausibile.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.lotti.auth import require_admin
from app.lotti.db import database as db
from app.lotti.servizi import menu_bridge
from app.menu.qr_prodotto import CANALI, codice_valido, url_prodotto

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Scheda prodotto"])


def _decimale(valore: Any) -> Optional[Decimal]:
    try:
        d = Decimal(str(valore).replace(",", ".").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return d if d.is_finite() else None


def _euro(valore: Optional[Decimal]) -> Optional[str]:
    return None if valore is None else f"{valore.quantize(Decimal('0.01'))}"


def costo_e_food_cost(ricetta: dict) -> dict:
    """Costo ingredienti e food cost, dagli stessi campi di ``/ricette-prezzi``: mai ricalcolati qui."""
    porzioni = _decimale(ricetta.get("porzioni")) or Decimal(1)
    totale = _decimale(ricetta.get("costo_totale"))
    banco = _decimale(ricetta.get("prezzo_vendita"))
    costo_porzione = (totale / max(porzioni, Decimal(1))) if totale and totale > 0 else None
    food_cost = (costo_porzione / banco * 100) if costo_porzione and banco and banco > 0 else None
    return {
        "costo_totale": _euro(totale if totale and totale > 0 else None),
        "costo_porzione": _euro(costo_porzione),
        "food_cost_percentuale": None if food_cost is None else f"{food_cost.quantize(Decimal('0.1'))}",
        "base": "prezzo al banco",
        "motivo": None if food_cost is not None else "serve il costo degli ingredienti e il prezzo al banco",
    }


async def _disponibilita(ricetta_id: str, esaurito: bool) -> dict:
    try:
        from app.lotti.routers.saima_ricettari import VerificaDisponibilitaPayload, verifica_disponibilita_ricetta

        esito = await verifica_disponibilita_ricetta(ricetta_id, VerificaDisponibilitaPayload())
        senza = [r["ingrediente"] for r in esito.get("righe", []) if r.get("stato") == "da_acquistare"]
        return {"esaurito": esaurito, "ingredienti_in_giacenza": bool(esito.get("realizzabile_subito")),
                "ingredienti_mancanti": senza, "motivo": None}
    except Exception as exc:  # noqa: BLE001 - un anello non letto non ferma la scheda
        logger.warning("Scheda prodotto: disponibilita' non letta (%s: %s)", type(exc).__name__, exc)
        return {"esaurito": esaurito, "ingredienti_in_giacenza": None, "ingredienti_mancanti": [],
                "motivo": "giacenza non leggibile"}


async def _nutrizionali(ricetta_id: str) -> dict:
    try:
        from app.lotti.routers.ricette import get_nutrizionali

        n = await get_nutrizionali(ricetta_id)
        return {"per_porzione": n.get("per_porzione"), "per_100g": n.get("per_100g"),
                "ingredienti_coperti": n.get("ingredienti_coperti"), "ingredienti_totali": n.get("ingredienti_totali"),
                "nota": n.get("nota"), "motivo": None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scheda prodotto: valori nutrizionali non letti (%s: %s)", type(exc).__name__, exc)
        return {"per_porzione": None, "per_100g": None, "motivo": "valori non calcolabili"}


async def costruisci_scheda(ricetta: dict) -> dict:
    ricetta_id = ricetta["id"]
    try:
        codici = await menu_bridge.codici_prodotti_ricette()
        url_menu = await menu_bridge.url_menu_pubblico()
        motivo_menu = None
    except Exception as exc:  # noqa: BLE001 - Menu non raggiungibile o non configurato
        logger.warning("Scheda prodotto: Menu non letto (%s: %s)", type(exc).__name__, exc)
        codici, url_menu, motivo_menu = {}, None, "Menu non raggiungibile"
    codice = codici.get(ricetta_id)
    varianti = await db.ricette.find({"ricetta_base_id": ricetta_id}, {"_id": 0, "id": 1, "nome": 1}).to_list(200)

    def indirizzo(canale: Optional[str]) -> Optional[str]:
        return url_prodotto(url_menu, codice, canale) if codice else None

    scheda_vendita = menu_bridge.scheda_vendita_da_ricetta(ricetta)
    return {
        "codice_prodotto": codice,
        "piatto": {"id": ricetta_id, "nome": ricetta.get("nome")},
        "prezzo": {"banco": _euro(_decimale(ricetta.get("prezzo_vendita"))),
                   "tavolo": _euro(_decimale(ricetta.get("prezzo_tavolo")))},
        "reparto": ricetta.get("reparto"),
        "ingredienti": [{"nome": i.get("nome"), "quantita": i.get("quantita"),
                         "unita_misura": i.get("unita_misura") or i.get("unita")}
                        for i in ricetta.get("ingredienti_dettaglio") or []],
        "allergeni": menu_bridge.allergeni_da_pubblicare(ricetta),
        "varianti": [{"id": v["id"], "nome": v.get("nome"), "codice_prodotto": codici.get(v["id"])} for v in varianti],
        "aggiunte": [{"nome": a["nome"], "prezzo": _euro(Decimal(a["prezzo_centesimi"]) / 100)}
                     for a in scheda_vendita["aggiunte"]],
        "rimozioni": scheda_vendita["rimozioni"],
        "costo_ingredienti_e_food_cost": costo_e_food_cost(ricetta),
        "disponibilita": await _disponibilita(ricetta_id, ricetta.get("esaurito") is True),
        "foto": ricetta.get("foto_url") or None,
        "valori_nutrizionali": await _nutrizionali(ricetta_id),
        "vendita": {"sala": scheda_vendita["vendita_sala"], "delivery": scheda_vendita["vendita_delivery"]},
        "qr": {"scheda": indirizzo(None), "sala": indirizzo("sala"), "delivery": indirizzo("delivery"),
               "motivo": motivo_menu or (None if url_menu else "indirizzo pubblico del menu non ancora scelto")},
    }


@router.get("/prodotti/{riferimento}/scheda")
async def scheda_prodotto(riferimento: str, _admin=Depends(require_admin)):
    """``riferimento`` = ID prodotto (``PRD-000123``) o id della ricetta."""
    ricetta_id = riferimento
    if codice_valido(riferimento):
        try:
            ricetta_id = await menu_bridge.ricetta_di_codice(riferimento) or ""
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Menu digitale non raggiungibile: {type(exc).__name__}") from exc
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0}) if ricetta_id else None
    if not ricetta:
        raise HTTPException(404, "Prodotto non trovato")
    return await costruisci_scheda(ricetta)
