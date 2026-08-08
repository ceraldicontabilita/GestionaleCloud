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

from app.services import conti_pos
from app.services.scritture_contabili import NATURA_CREDITO_POS, _scrivi_se_assente
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

# I codici del piano ufficiale stanno tutti in conti_pos: qui solo l'etichetta.
CATEGORIA_COMMISSIONI = "Commissioni e spese bancarie"

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
        "commissione_api": round(abs(_importo(grezzo.get("fee_total"))), 2),
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
    commissione_calcolata = calcola_commissione(
        vendite=componenti["vendite"],
        rimborsi=componenti["rimborsi"],
        chargeback=componenti["chargeback"],
        netto=payout["netto"],
    )
    # La fee restituita dal Financial Payout e' la fonte primaria. Il calcolo
    # inverso resta una quadratura indipendente e puo' differire di un centesimo
    # per gli arrotondamenti applicati alla singola transazione.
    commissione = (
        payout["commissione_api"]
        if payout.get("commissione_api") > 0
        else commissione_calcolata
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
        "commissione_calcolata": commissione_calcolata,
        "credito_coperto": round(
            componenti["vendite"] - componenti["rimborsi"]
            - componenti["chargeback"], 2
        ),
        "movimento_mastercard": payout["netto"],
        "tipo_record": "payout",
        "stato_riconciliazione": stato,
        "gestore": GESTORE,
        "conto_contabile": conti_pos.conto_accredito(GESTORE),
        "updated_at": now,
    }
    await db[COLL_PAYOUT].update_one(
        {"payout_id": payout_id},
        {"$set": documento, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    scrittura = {}
    if stato == "riconciliato":
        scrittura = await _scrittura_di_accredito(
            db, payout, componenti, commissione)

    aggiornati = await _chiudi_crediti(db, payout_id, componenti["giorni"],
                                       coperto=coperto, now=now)

    return {
        "success": True,
        "payout_id": payout_id,
        "data": payout["data"],
        "netto": payout["netto"],
        **componenti,
        "commissione": commissione,
        "commissione_calcolata": commissione_calcolata,
        "stato_riconciliazione": stato,
        "scrittura": scrittura,
        "crediti_chiusi": aggiornati,
        # Prova di quadratura richiesta: lordo = accredito + commissioni +
        # rimborsi/rettifiche.
        "quadra": abs(
            componenti["vendite"] - componenti["rimborsi"]
            - componenti["chargeback"] - payout["netto"] - commissione
        ) <= 0.05,
    }


async def registra_rettifica_payout(
    db, gruppo: Dict[str, Any], *,
    transazioni: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Registra una deduzione SumUp separata dal payout ordinario.

    Un rimborso/chargeback riduce la Mastercard e il credito gia' aperto dalle
    vendite. Non e' una commissione e non e' un nuovo ricavo. Le due righe
    contabili condividono lo stesso settlement id e sono idempotenti.
    """
    payout_id = str(gruppo.get("payout_id") or gruppo.get("reference") or "")
    data_payout = str(gruppo.get("date") or "")[:10]
    importo = round(abs(_importo(gruppo.get("deduction_amount"))), 2)
    if not payout_id or not data_payout or importo <= TOLLERANZA:
        return {"success": False, "motivo": "rettifica payout non interpretabile"}

    transazioni = [t for t in transazioni if isinstance(t, dict)]
    giorni = sorted({str(t.get("data") or "")[:10] for t in transazioni if t.get("data")})
    now = datetime.now(timezone.utc).isoformat()
    documento = {
        "payout_id": payout_id,
        "data": data_payout,
        "netto": round(-importo, 2),
        "movimento_mastercard": round(-importo, 2),
        "commissione": 0.0,
        "credito_coperto": round(-importo, 2),
        "giorni": giorni,
        "transazioni": len(transazioni),
        "tipo_record": "rettifica",
        "tipi": list(gruppo.get("tipi") or []),
        "stato": str(gruppo.get("status") or "").upper(),
        "stato_riconciliazione": (
            "rettifica_confermata" if giorni and gruppo.get("status") == "SUCCESSFUL"
            else "rettifica_da_verificare"
        ),
        "gestore": GESTORE,
        "conto_contabile": conti_pos.conto_accredito(GESTORE),
        "record_ids": list(gruppo.get("record_ids") or []),
        "updated_at": now,
    }
    await db[COLL_PAYOUT].update_one(
        {"payout_id": payout_id},
        {"$set": documento, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    settlement_id = f"sumup:{payout_id}"
    comune = {
        "data": data_payout,
        "settlement_id": settlement_id,
        "payout_id": payout_id,
        "gestore": GESTORE,
        "circuito": "SUMUP",
        "giorni_coperti": giorni,
    }
    credito = {
        **comune,
        "tipo": "entrata",
        "importo": importo,
        "categoria": "Crediti verso gestori incassi",
        "descrizione": f"Rettifica credito SumUp — {payout_id}",
        "source": "rettifica_credito_pos",
        "natura": NATURA_CREDITO_POS,
        "conto_contabile": conti_pos.conto_credito(GESTORE),
        "conto_nome": conti_pos.descrizione_conto(conti_pos.conto_credito(GESTORE)),
    }
    mastercard = {
        **comune,
        "tipo": "uscita",
        "importo": importo,
        "categoria": "Rettifiche POS",
        "descrizione": f"Deduzione SumUp su Mastercard — {payout_id}",
        "source": "rettifica_payout",
        "natura": "liquidita",
        "conto_contabile": conti_pos.conto_accredito(GESTORE),
        "conto_nome": conti_pos.descrizione_conto(conti_pos.conto_accredito(GESTORE)),
    }
    scritture = {}
    for ruolo, movimento in (("credito", credito), ("mastercard", mastercard)):
        identificativo, _ = await _scrivi_se_assente(
            db, "banca",
            {"settlement_id": settlement_id, "source": movimento["source"]},
            movimento,
        )
        scritture[ruolo] = identificativo
    return {
        "success": True,
        "payout_id": payout_id,
        "data": data_payout,
        "rettifica": importo,
        "giorni": giorni,
        "stato_riconciliazione": documento["stato_riconciliazione"],
        "scritture": scritture,
    }


async def _scrittura_di_accredito(db, payout: Dict[str, Any],
                                  componenti: Dict[str, Any],
                                  commissione: float) -> Dict[str, Any]:
    """Operazione composta: chiude il credito, accredita, imputa il costo.

    Tre righe legate dallo stesso ``settlement_id``, che devono quadrare fra
    loro::

        credito SumUp chiuso = accredito Mastercard + costi commissioni

    Nessun ricavo: il ricavo e' gia' nel corrispettivo XML. E nessun movimento
    su BPM: SumUp versa sulla Mastercard, che e' un conto a se'.
    """
    payout_id = payout["payout_id"]
    settlement_id = f"sumup:{payout_id}"
    giorni = ", ".join(conti_pos.data_italiana(g)
                       for g in componenti["giorni"])
    credito_chiuso = round(componenti["vendite"] - componenti["rimborsi"]
                           - componenti["chargeback"], 2)

    comune = {
        "data": payout["data"],
        "settlement_id": settlement_id,
        "payout_id": payout_id,
        "gestore": GESTORE,
        "circuito": "SUMUP",
        "giorni_coperti": componenti["giorni"],
    }
    righe = []

    if credito_chiuso > TOLLERANZA:
        righe.append(("credito", {
            **comune,
            "tipo": "uscita",
            "importo": credito_chiuso,
            "categoria": "Crediti verso gestori incassi",
            "descrizione": f"Chiusura credito SumUp — payout {payout_id} ({giorni})",
            "source": "chiusura_credito_pos",
            # Stessa natura della riga di apertura: cosi' il saldo del
            # credito si azzera da solo invece di restare aperto per sempre.
            "natura": NATURA_CREDITO_POS,
            "conto_contabile": conti_pos.conto_credito(GESTORE),
            "conto_nome": conti_pos.descrizione_conto(
                conti_pos.conto_credito(GESTORE)),
        }))

    if payout["netto"] > TOLLERANZA:
        righe.append(("accredito", {
            **comune,
            "tipo": "entrata",
            "importo": payout["netto"],
            "categoria": "Accrediti POS",
            "descrizione": f"Payout SumUp {payout_id}",
            "source": "accredito_payout",
            "natura": "liquidita",
            "conto_contabile": conti_pos.conto_accredito(GESTORE),
            "conto_nome": conti_pos.descrizione_conto(
                conti_pos.conto_accredito(GESTORE)),
        }))

    if commissione > TOLLERANZA:
        righe.append(("commissioni", {
            **comune,
            "tipo": "uscita",
            "importo": commissione,
            "categoria": CATEGORIA_COMMISSIONI,
            "descrizione": f"Commissioni SumUp — payout {payout_id} ({giorni})",
            "source": "commissioni_sumup",
            # Costo di conto economico, non un prelievo dalla Mastercard: la
            # trattenuta non e' mai transitata sul conto. Non appartiene
            # quindi a nessuna scheda di tesoreria.
            "natura": "costo",
            "conto_contabile": conti_pos.conto_commissioni(GESTORE),
            "conto_nome": conti_pos.descrizione_conto(
                conti_pos.conto_commissioni(GESTORE)),
        }))

    scritte: Dict[str, Any] = {"settlement_id": settlement_id}
    for ruolo, movimento in righe:
        # Idempotenza per ruolo: rilanciare la sincronizzazione non raddoppia
        # ne' l'accredito ne' il costo.
        identificativo, _ = await _scrivi_se_assente(
            db, "banca",
            {"settlement_id": settlement_id, "source": movimento["source"]},
            movimento,
        )
        scritte[ruolo] = identificativo

    scritte["quadra"] = abs(
        credito_chiuso - payout["netto"] - commissione) <= TOLLERANZA
    return scritte


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
