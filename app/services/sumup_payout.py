"""Accrediti (payout) SumUp e commissioni.

SumUp accredita il NETTO: trattiene le commissioni prima di versare. Nexi/Numia
fa il contrario, accredita il lordo e fattura le commissioni a parte. E' questa
asimmetria che rende necessaria una scrittura di costo dedicata: senza, il
trasferimento POS da 100 non quadrerebbe mai con un accredito da 98 e
resterebbe per sempre "da verificare".

Il legame corretto e' ``molte transazioni -> un payout -> un movimento
bancario``. Un payout puo' contenere piu' giornate, quindi non va MAI
attribuito a un giorno solo perche' l'importo somiglia: la prova primaria e'
il ``payout_id`` presente sulle transazioni.

Regola invariabile: l'accredito non e' un ricavo. Il ricavo e' gia' nel
corrispettivo XML; qui si chiude un credito e si registra un costo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.services.scritture_contabili import _scrivi_se_assente
from app.services.sumup_sync import (
    GESTORE,
    TIPO_CHARGEBACK,
    TIPO_RIMBORSO,
    TIPO_VENDITA,
    STATI_ESCLUSI,
    STATO_VALIDO,
    giorno_locale,
)

logger = logging.getLogger(__name__)

COLL_PAYOUT = "sumup_payouts"

# Piano dei conti CEE ufficiale (regola vincolante utente).
CONTO_COMMISSIONI = "75.01.07"
CATEGORIA_COMMISSIONI = "Commissioni e spese bancarie"
CONTO_SUMUP = "SUMUP"

# Sotto questa soglia la differenza e' arrotondamento, non commissione.
TOLLERANZA = 0.01


def _importo(valore: Any) -> float:
    try:
        return round(float(valore or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def normalizza_payout(grezzo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Riduce un payout ai campi che servono, o lo scarta se inutilizzabile."""
    if not isinstance(grezzo, dict):
        return None
    payout_id = (
        grezzo.get("id")
        or grezzo.get("payout_id")
        or grezzo.get("transaction_code")
        or grezzo.get("reference")
    )
    if not payout_id:
        return None
    istante = grezzo.get("date") or grezzo.get("timestamp") or grezzo.get("created_at")
    try:
        data = giorno_locale(istante)
    except (ValueError, TypeError):
        return None
    return {
        "payout_id": str(payout_id),
        "data": data,
        "netto": round(abs(_importo(grezzo.get("amount"))), 2),
        "valuta": str(grezzo.get("currency") or "EUR").upper(),
        "stato": str(grezzo.get("status") or "").strip().upper(),
        "riferimento": str(grezzo.get("reference") or ""),
    }


def componenti_del_payout(transazioni: Iterable[Dict[str, Any]],
                          payout_id: str) -> Dict[str, Any]:
    """Cosa contiene davvero il payout, letto dalle transazioni collegate."""
    righe = [
        t for t in transazioni
        if isinstance(t, dict)
        and str(t.get("payout_id") or "") == str(payout_id)
        and t.get("stato") not in STATI_ESCLUSI
    ]
    vendite = round(sum(
        t.get("importo") or 0.0 for t in righe
        if t.get("tipo") == TIPO_VENDITA and t.get("stato") == STATO_VALIDO), 2)
    rimborsi = round(sum(
        t.get("importo") or 0.0 for t in righe
        if t.get("tipo") == TIPO_RIMBORSO), 2)
    chargeback = round(sum(
        t.get("importo") or 0.0 for t in righe
        if t.get("tipo") == TIPO_CHARGEBACK), 2)
    giorni = sorted({t.get("data") for t in righe if t.get("data")})
    return {
        "vendite": vendite,
        "rimborsi": rimborsi,
        "chargeback": chargeback,
        "giorni": giorni,
        "transazioni": len(righe),
    }


def calcola_commissione(*, vendite: float, rimborsi: float, chargeback: float,
                        netto: float, rettifiche: float = 0.0) -> float:
    """Commissione trattenuta = lordo incassato - quanto e' stato versato.

    ``accredito atteso = vendite - rimborsi - commissioni - chargeback +-
    rettifiche``, quindi la commissione e' cio' che resta invertendo la
    formula. Puo' risultare negativa solo se le rettifiche sono a favore
    dell'esercente: in quel caso non e' un costo e va esaminata a mano.
    """
    lordo = round(vendite - rimborsi - chargeback + rettifiche, 2)
    return round(lordo - netto, 2)


async def _transazioni_del_payout(db, payout_id: str) -> List[Dict[str, Any]]:
    from app.services.sumup_sync import COLL_TRANSAZIONI

    cursore = db[COLL_TRANSAZIONI].find({"payout_id": str(payout_id)}, {"_id": 0})
    if hasattr(cursore, "to_list"):
        return await cursore.to_list(100000)
    return [t async for t in cursore]


async def registra_payout(db, grezzo: Dict[str, Any], *,
                          transazioni: Optional[Iterable[Dict[str, Any]]] = None,
                          actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Chiude i crediti POS coperti dal payout e registra la commissione.

    Esempio dell'utente: vendite 100, commissioni 2, accredito 98. Vengono
    scritti la chiusura del credito da 100 e il costo da 2. NON altri 98 di
    ricavo: quel denaro e' gia' stato registrato come corrispettivo.
    """
    payout = normalizza_payout(grezzo)
    if payout is None:
        return {"success": False, "motivo": "payout non interpretabile"}

    now = datetime.now(timezone.utc).isoformat()
    payout_id = payout["payout_id"]
    if transazioni is None:
        transazioni = await _transazioni_del_payout(db, payout_id)
    componenti = componenti_del_payout(transazioni, payout_id)
    commissione = calcola_commissione(
        vendite=componenti["vendite"],
        rimborsi=componenti["rimborsi"],
        chargeback=componenti["chargeback"],
        netto=payout["netto"],
    )

    # Senza transazioni collegate non si sa cosa copre l'accredito: agganciarlo
    # "per importo simile" e' proprio l'errore da evitare.
    coperto = bool(componenti["giorni"])
    stato = "riconciliato" if coperto else "payout_senza_transazioni"
    if coperto and abs(commissione) > max(payout["netto"] * 0.1, 5.0):
        # Una trattenuta anomala non va scritta a costo in automatico.
        stato = "commissioni_da_verificare"

    documento = {
        **payout,
        **componenti,
        "commissione": commissione,
        "stato_riconciliazione": stato,
        "gestore": GESTORE,
        "conto": CONTO_SUMUP,
        "updated_at": now,
    }
    await db[COLL_PAYOUT].update_one(
        {"payout_id": payout_id},
        {"$set": documento, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    movimento_commissioni = None
    if stato == "riconciliato" and commissione > TOLLERANZA:
        descrizione = (
            f"Commissioni POS SUMUP payout {payout_id} "
            f"({', '.join(componenti['giorni'])})"
        )
        movimento_commissioni, _ = await _scrivi_se_assente(
            db, "banca",
            # Idempotenza: un payout produce una sola scrittura di costo,
            # anche se la sincronizzazione viene rilanciata.
            {"source": "commissioni_sumup", "payout_id": payout_id},
            {
                "data": payout["data"],
                "tipo": "uscita",
                "importo": commissione,
                "categoria": CATEGORIA_COMMISSIONI,
                "conto_contabile": CONTO_COMMISSIONI,
                "descrizione": descrizione,
                "source": "commissioni_sumup",
                "gestore": GESTORE,
                "circuito": "SUMUP",
                "conto": CONTO_SUMUP,
                "payout_id": payout_id,
                "giorni_coperti": componenti["giorni"],
            },
        )

    aggiornati = await _chiudi_crediti(db, payout_id, componenti["giorni"],
                                       coperto=coperto, now=now)

    return {
        "success": True,
        "payout_id": payout_id,
        "data": payout["data"],
        "netto": payout["netto"],
        **componenti,
        "commissione": commissione,
        "stato_riconciliazione": stato,
        "movimento_commissioni_id": movimento_commissioni,
        "crediti_chiusi": aggiornati,
        # Prova di quadratura richiesta: lordo = accredito + commissioni +
        # rimborsi/rettifiche.
        "quadra": abs(
            componenti["vendite"] - componenti["rimborsi"]
            - componenti["chargeback"] - payout["netto"] - commissione
        ) <= TOLLERANZA,
    }


async def _chiudi_crediti(db, payout_id: str, giorni: List[str], *,
                          coperto: bool, now: str) -> int:
    """Marca come accreditati i trasferimenti SumUp dei giorni del payout.

    Non crea entrate: il denaro era gia' in Prima Nota come credito atteso,
    qui smette soltanto di essere "in transito".
    """
    if not coperto:
        return 0
    esito = await db["prima_nota_banca"].update_many(
        {
            "data": {"$in": giorni},
            "source": "trasferimento_pos",
            "gestore": GESTORE,
            "status": {"$nin": ["deleted", "archived"]},
        },
        {"$set": {
            "riconciliato": True,
            "in_transito": False,
            "stato_riconciliazione": "riconciliato",
            "payout_id": payout_id,
            "updated_at": now,
        }},
    )
    return getattr(esito, "modified_count", 0) or 0
