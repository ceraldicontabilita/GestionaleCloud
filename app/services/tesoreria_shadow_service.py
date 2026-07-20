"""Lettura tipizzata e deterministica dei dati per l'agente Tesoreria.

Il servizio non modifica alcuna collection e non espone strumenti di pagamento.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from app.routers.prima_nota_module.common import (
    ESCLUSIONI_PRIMA_NOTA,
    aggrega_saldo_prima_nota,
)
from app.services.pos_evidence import (
    _e_accredito_pos_numia_con_giorno,
    _giorno_operazione_pos,
)


@dataclass(frozen=True)
class FasciaScadenze:
    count: int
    total: str
    first_due_date: Optional[str]
    last_due_date: Optional[str]


@dataclass(frozen=True)
class Liquidita:
    cassa: str
    banca: str
    totale: str
    saldo_cassa_manuale: bool
    saldo_banca_manuale: bool


@dataclass(frozen=True)
class AggregatoOperativo:
    count: int
    total: str


@dataclass(frozen=True)
class EvidenzePos:
    attesa_giorni: int
    giorni_chiusura: int
    totale_chiusure: str
    giorni_con_evidenza_banca: int
    totale_accrediti_banca: str
    giorni_senza_evidenza_banca: int
    giorni_importo_non_coerente: int


@dataclass(frozen=True)
class TesoreriaSnapshot:
    reference_date: str
    horizon_days: int
    overdue: FasciaScadenze
    upcoming: FasciaScadenze
    liquidity: Liquidita
    pos: EvidenzePos
    pending_checks: Dict[str, AggregatoOperativo]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _importo(doc: Dict[str, Any]) -> Decimal:
    raw = doc.get("importo_residuo")
    if raw is None:
        raw = doc.get("importo_rata")
    if raw is None:
        raw = doc.get("importo")
    if raw is None:
        raw = doc.get("amount")
    if raw is None:
        raw = doc.get("totale", 0)
    try:
        testo = str(raw or 0).strip()
        if "," in testo:
            testo = testo.replace(".", "").replace(",", ".")
        return abs(Decimal(testo))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fascia(docs: List[Dict[str, Any]]) -> FasciaScadenze:
    date_valide = sorted(str(d.get("data_scadenza")) for d in docs if d.get("data_scadenza"))
    totale = sum((_importo(doc) for doc in docs), Decimal("0"))
    return FasciaScadenze(
        count=len(docs),
        total=f"{totale.quantize(Decimal('0.01'))}",
        first_due_date=date_valide[0] if date_valide else None,
        last_due_date=date_valide[-1] if date_valide else None,
    )


def _giorno_pos_banca(descrizione: str) -> Optional[str]:
    if not _e_accredito_pos_numia_con_giorno(descrizione):
        return None
    return _giorno_operazione_pos(descrizione, "")


def _aggregato(docs: List[Dict[str, Any]]) -> AggregatoOperativo:
    totale = sum((_importo(doc) for doc in docs), Decimal("0"))
    return AggregatoOperativo(
        count=len(docs),
        total=f"{totale.quantize(Decimal('0.01'))}",
    )


async def _liquidita(db, riferimento: date) -> Liquidita:
    anno = riferimento.year
    query = {
        "status": {"$nin": ["deleted", "archived"]},
        **ESCLUSIONI_PRIMA_NOTA,
        "$or": [
            {
                "anno": anno,
                "data": {"$gte": f"{anno}-01-01", "$lte": riferimento.isoformat()},
            },
            {
                "anno": {"$in": [None, ""]},
                "data": {"$gte": f"{anno}-01-01", "$lte": riferimento.isoformat()},
            },
            {
                "anno": {"$exists": False},
                "data": {"$gte": f"{anno}-01-01", "$lte": riferimento.isoformat()},
            },
        ],
    }
    cassa = await aggrega_saldo_prima_nota(db, "prima_nota_cassa", query, anno=anno)
    banca = await aggrega_saldo_prima_nota(db, "prima_nota_banca", query, anno=anno)
    saldo_cassa = Decimal(str(cassa["saldo"]))
    saldo_banca = Decimal(str(banca["saldo"]))
    return Liquidita(
        cassa=f"{saldo_cassa.quantize(Decimal('0.01'))}",
        banca=f"{saldo_banca.quantize(Decimal('0.01'))}",
        totale=f"{(saldo_cassa + saldo_banca).quantize(Decimal('0.01'))}",
        saldo_cassa_manuale=bool(cassa["saldo_iniziale_manuale"]),
        saldo_banca_manuale=bool(banca["saldo_iniziale_manuale"]),
    )


async def _evidenze_pos(db, riferimento: date, attesa_giorni: int) -> EvidenzePos:
    inizio = f"{riferimento.year}-01-01"
    fine = riferimento.isoformat()
    chiusure = await db["chiusure_pos_manuali"].find(
        {"data": {"$gte": inizio, "$lte": fine}},
        {"_id": 0, "data": 1, "importo": 1, "totale": 1, "source": 1},
    ).to_list(10000)
    manuali: Dict[str, Decimal] = {}
    override: Dict[str, Decimal] = {}
    for doc in chiusure:
        raw_data = doc.get("data")
        data_doc = raw_data.strftime("%Y-%m-%d") if isinstance(raw_data, datetime) else str(raw_data or "")[:10]
        if not data_doc:
            continue
        importo = _importo(doc)
        if doc.get("source") == "inserimento_manuale_terminale":
            override[data_doc] = importo
        else:
            manuali[data_doc] = manuali.get(data_doc, Decimal("0")) + importo
    manuali.update(override)

    movimenti = await db["estratto_conto_movimenti"].find(
        {
            "data": {"$gte": inizio, "$lte": fine},
            "importo": {"$gt": 0},
            "$or": [
                {"descrizione_originale": {"$regex": "NUMIA", "$options": "i"}},
                {"descrizione": {"$regex": "NUMIA", "$options": "i"}},
            ],
        },
        {"_id": 0, "importo": 1, "amount": 1, "descrizione": 1, "descrizione_originale": 1},
    ).to_list(10000)
    accrediti: Dict[str, Decimal] = {}
    for doc in movimenti:
        giorno = _giorno_pos_banca(doc.get("descrizione_originale") or doc.get("descrizione") or "")
        if giorno and inizio <= giorno <= fine:
            accrediti[giorno] = accrediti.get(giorno, Decimal("0")) + _importo(doc)

    limite_attesa = (riferimento - timedelta(days=attesa_giorni)).isoformat()
    confrontabili = {giorno for giorno in manuali if giorno <= limite_attesa}
    senza_evidenza = confrontabili - set(accrediti)
    non_coerenti = {
        giorno for giorno in confrontabili & set(accrediti)
        if manuali[giorno].quantize(Decimal("0.01")) != accrediti[giorno].quantize(Decimal("0.01"))
    }
    return EvidenzePos(
        attesa_giorni=attesa_giorni,
        giorni_chiusura=len(manuali),
        totale_chiusure=f"{sum(manuali.values(), Decimal('0')).quantize(Decimal('0.01'))}",
        giorni_con_evidenza_banca=len(set(manuali) & set(accrediti)),
        totale_accrediti_banca=f"{sum(accrediti.values(), Decimal('0')).quantize(Decimal('0.01'))}",
        giorni_senza_evidenza_banca=len(senza_evidenza),
        giorni_importo_non_coerente=len(non_coerenti),
    )


async def leggi_snapshot_tesoreria(
    db,
    reference_date: Optional[date] = None,
    horizon_days: int = 30,
    pos_wait_days: int = 7,
) -> TesoreriaSnapshot:
    """Restituisce soli aggregati di scadenze aperte, senza dati personali."""
    oggi = reference_date or date.today()
    fine = oggi + timedelta(days=horizon_days)
    base = {
        "pagato": {"$ne": True},
        "stato": {"$nin": ["pagata", "pagato", "chiusa", "annullata"]},
    }
    projection = {
        "_id": 0,
        "data_scadenza": 1,
        "importo_residuo": 1,
        "importo_rata": 1,
        "importo": 1,
    }
    overdue = await db["scadenziario_fornitori"].find(
        {**base, "data_scadenza": {"$lt": oggi.isoformat()}}, projection
    ).sort("data_scadenza", 1).to_list(10000)
    upcoming = await db["scadenziario_fornitori"].find(
        {**base, "data_scadenza": {"$gte": oggi.isoformat(), "$lte": fine.isoformat()}},
        projection,
    ).sort("data_scadenza", 1).to_list(10000)
    assegni = await db["assegni"].find(
        {"stato": {"$nin": ["incassato", "annullato"]}, "confermato": {"$ne": True}},
        {"_id": 0, "importo": 1},
    ).to_list(10000)
    bonifici = await db["bonifici_transfers"].find(
        {"riconciliato": {"$ne": True}}, {"_id": 0, "importo": 1}
    ).to_list(10000)
    paypal = await db["paypal_transactions"].find(
        {"importo": {"$lt": 0}, "riconciliato_con_estratto_banca": {"$ne": True}},
        {"_id": 0, "importo": 1},
    ).to_list(10000)
    return TesoreriaSnapshot(
        reference_date=oggi.isoformat(),
        horizon_days=horizon_days,
        overdue=_fascia(overdue),
        upcoming=_fascia(upcoming),
        liquidity=await _liquidita(db, oggi),
        pos=await _evidenze_pos(db, oggi, pos_wait_days),
        pending_checks={
            "assegni": _aggregato(assegni),
            "bonifici": _aggregato(bonifici),
            "paypal": _aggregato(paypal),
        },
    )
