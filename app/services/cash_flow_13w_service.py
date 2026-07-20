"""Previsione deterministica di cassa a 13 settimane.

Il servizio legge solo fonti applicative tipizzate e restituisce aggregati.
Non prepara pagamenti, non crea movimenti e non modifica dati di business.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.routers.prima_nota_module.common import (
    COLLECTION_PRIMA_NOTA_BANCA,
    COLLECTION_PRIMA_NOTA_CASSA,
    ESCLUSIONI_PRIMA_NOTA,
    aggrega_saldo_prima_nota,
)


CENT = Decimal("0.01")
SCENARI = {
    "base": (Decimal("1.00"), Decimal("1.00")),
    "prudente": (Decimal("0.70"), Decimal("1.00")),
    "stress": (Decimal("0.40"), Decimal("1.10")),
}
STATI_CHIUSI = ("pagata", "pagato", "paid", "chiusa", "chiuso", "annullata", "annullato")


@dataclass(frozen=True)
class MovimentoPrevisto:
    fonte: str
    data: date
    importo: Decimal
    direzione: str
    scaduto: bool = False


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _decimal(doc: Dict[str, Any], fields: Iterable[str]) -> Optional[Decimal]:
    for field in fields:
        raw = doc.get(field)
        if raw in (None, ""):
            continue
        try:
            text = str(raw).strip()
            if "," in text:
                text = text.replace(".", "").replace(",", ".")
            value = Decimal(text).copy_abs()
            return value if value > 0 else None
        except (InvalidOperation, ValueError):
            continue
    return None


def _date(doc: Dict[str, Any], fields: Iterable[str]) -> Optional[date]:
    for field in fields:
        raw = doc.get(field)
        if raw in (None, ""):
            continue
        try:
            if isinstance(raw, datetime):
                return raw.date()
            if isinstance(raw, date):
                return raw
            return date.fromisoformat(str(raw)[:10])
        except (ValueError, TypeError):
            continue
    return None


def _aperto(doc: Dict[str, Any]) -> bool:
    stato = str(doc.get("stato") or doc.get("status") or "").lower()
    return not doc.get("pagato") and stato not in STATI_CHIUSI


async def _saldo_liquidita(db, riferimento: date) -> Decimal:
    query = {
        "status": {"$nin": ["deleted", "archived"]},
        **ESCLUSIONI_PRIMA_NOTA,
        "data": {"$gte": f"{riferimento.year}-01-01", "$lte": riferimento.isoformat()},
    }
    cassa = await aggrega_saldo_prima_nota(
        db, COLLECTION_PRIMA_NOTA_CASSA, query, anno=riferimento.year
    )
    banca = await aggrega_saldo_prima_nota(
        db, COLLECTION_PRIMA_NOTA_BANCA, query, anno=riferimento.year
    )
    return Decimal(str(cassa.get("saldo", 0))) + Decimal(str(banca.get("saldo", 0)))


async def _leggi_movimenti(
    db, riferimento: date, fine: date
) -> Tuple[List[MovimentoPrevisto], Dict[str, int]]:
    movimenti: List[MovimentoPrevisto] = []
    qualita = {
        "scadenze_fornitori_incluse": 0,
        "obblighi_inclusi": 0,
        "crediti_inclusi": 0,
        "senza_data_esclusi": 0,
        "senza_importo_esclusi": 0,
        "tipi_non_classificati_esclusi": 0,
    }

    scadenze = await db["scadenziario_fornitori"].find(
        {"pagato": {"$ne": True}, "stato": {"$nin": list(STATI_CHIUSI)}},
        {"_id": 0, "data_scadenza": 1, "importo_residuo": 1, "importo_rata": 1, "importo": 1},
    ).to_list(20000)
    for doc in scadenze:
        scadenza = _date(doc, ("data_scadenza",))
        importo = _decimal(doc, ("importo_residuo", "importo_rata", "importo"))
        if not scadenza:
            qualita["senza_data_esclusi"] += 1
        elif not importo:
            qualita["senza_importo_esclusi"] += 1
        elif scadenza <= fine:
            movimenti.append(MovimentoPrevisto("scadenziario_fornitori", scadenza, importo, "uscita", scadenza < riferimento))
            qualita["scadenze_fornitori_incluse"] += 1

    partite = await db["partite_aperte"].find(
        {"stato": {"$in": ["aperta", "parziale"]}},
        {"_id": 0, "tipo": 1, "data_scadenza": 1, "residuo": 1, "importo_originale": 1},
    ).to_list(20000)
    for doc in partite:
        tipo = str(doc.get("tipo") or "").lower()
        # Le fatture fornitore sono gia' rappresentate dallo scadenzario rateale.
        if tipo in {"fattura_fornitore", "nota_credito"}:
            continue
        if tipo == "pos_atteso":
            direzione = "entrata"
        elif tipo in {"f24", "stipendio", "altro"}:
            direzione = "uscita"
        else:
            qualita["tipi_non_classificati_esclusi"] += 1
            continue
        scadenza = _date(doc, ("data_scadenza",))
        importo = _decimal(doc, ("residuo", "importo_originale"))
        if not scadenza:
            qualita["senza_data_esclusi"] += 1
        elif not importo:
            qualita["senza_importo_esclusi"] += 1
        elif scadenza <= fine:
            movimenti.append(MovimentoPrevisto("partite_aperte", scadenza, importo, direzione, scadenza < riferimento))
            qualita["obblighi_inclusi"] += 1

    crediti = await db["fatture_emesse"].find(
        {"pagato": {"$ne": True}, "status": {"$nin": list(STATI_CHIUSI)}},
        {
            "_id": 0, "data_scadenza": 1, "due_date": 1, "scadenza": 1,
            "importo_residuo": 1, "residuo": 1, "totale": 1,
            "total_amount": 1, "importo_totale": 1,
        },
    ).to_list(20000)
    for doc in crediti:
        if not _aperto(doc):
            continue
        scadenza = _date(doc, ("data_scadenza", "due_date", "scadenza"))
        importo = _decimal(doc, ("importo_residuo", "residuo", "totale", "total_amount", "importo_totale"))
        if not scadenza:
            qualita["senza_data_esclusi"] += 1
        elif not importo:
            qualita["senza_importo_esclusi"] += 1
        elif scadenza <= fine:
            movimenti.append(MovimentoPrevisto("fatture_emesse", scadenza, importo, "entrata", scadenza < riferimento))
            qualita["crediti_inclusi"] += 1
    return movimenti, qualita


def _settimane(riferimento: date, movimenti: List[MovimentoPrevisto]) -> List[Dict[str, Any]]:
    settimane = []
    for indice in range(13):
        inizio = riferimento + timedelta(days=indice * 7)
        fine = inizio + timedelta(days=6)
        righe = [
            m for m in movimenti
            if (m.data < riferimento and indice == 0) or inizio <= m.data <= fine
        ]
        entrate = sum((m.importo for m in righe if m.direzione == "entrata"), Decimal("0"))
        uscite = sum((m.importo for m in righe if m.direzione == "uscita"), Decimal("0"))
        settimane.append({
            "settimana": indice + 1,
            "dal": inizio.isoformat(),
            "al": fine.isoformat(),
            "entrate_attese": entrate,
            "uscite_attese": uscite,
            "scaduti_riportati": sum(1 for m in righe if m.scaduto),
        })
    return settimane


def _anomalie_cash_flow(
    scenari: List[Dict[str, Any]], qualita: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Evidenze deterministiche: nessuna soglia economica inventata."""
    anomalie: List[Dict[str, Any]] = []
    base = next(s for s in scenari if s["nome"] == "base")
    stress = next(s for s in scenari if s["nome"] == "stress")

    scenario_negativo = base if base["saldo_minimo"] < 0 else (
        stress if stress["saldo_minimo"] < 0 else None
    )
    if scenario_negativo:
        prima_settimana = next(
            (r["settimana"] for r in scenario_negativo["settimane"] if r["saldo_finale"] < 0),
            None,
        )
        anomalie.append({
            "codice": "LIQUIDITA_BASE_NEGATIVA" if scenario_negativo["nome"] == "base"
            else "LIQUIDITA_STRESS_NEGATIVA",
            "severita": "alta" if scenario_negativo["nome"] == "base" else "attenzione",
            "titolo": "Liquidita negativa nello scenario " + scenario_negativo["nome"],
            "descrizione": "Il saldo previsto scende sotto zero; serve verifica umana prima di ogni azione.",
            "scenario": scenario_negativo["nome"],
            "settimana": prima_settimana,
            "saldo_minimo": scenario_negativo["saldo_minimo"],
        })

    if qualita["record_esclusi"]:
        anomalie.append({
            "codice": "DATI_INCOMPLETI",
            "severita": "attenzione",
            "titolo": "Previsione con dati esclusi",
            "descrizione": "Alcuni record non hanno data, importo o classificazione e non sono stati stimati.",
            "record_coinvolti": qualita["record_esclusi"],
        })

    scaduti = sum(
        riga.get("scaduti_riportati", 0) for riga in base["settimane"]
    )
    if scaduti:
        anomalie.append({
            "codice": "SCADENZE_ARRETRATE",
            "severita": "attenzione",
            "titolo": "Scadenze arretrate riportate",
            "descrizione": "Le scadenze gia decorse sono incluse nella prima settimana.",
            "record_coinvolti": scaduti,
        })
    return anomalie


async def calcola_cash_flow_13_settimane(
    db, reference_date: Optional[date] = None
) -> Dict[str, Any]:
    """Calcola tre scenari senza inferire date o importi mancanti."""
    riferimento = reference_date or date.today()
    fine = riferimento + timedelta(days=90)
    liquidita = await _saldo_liquidita(db, riferimento)
    movimenti, qualita = await _leggi_movimenti(db, riferimento, fine)
    settimane_base = _settimane(riferimento, movimenti)
    scenari = []
    for nome, (fattore_entrate, fattore_uscite) in SCENARI.items():
        saldo = liquidita
        righe = []
        minimo = saldo
        for base in settimane_base:
            entrate = base["entrate_attese"] * fattore_entrate
            uscite = base["uscite_attese"] * fattore_uscite
            saldo += entrate - uscite
            minimo = min(minimo, saldo)
            righe.append({
                **{k: v for k, v in base.items() if k not in {"entrate_attese", "uscite_attese"}},
                "entrate": _money(entrate),
                "uscite": _money(uscite),
                "saldo_finale": _money(saldo),
            })
        scenari.append({
            "nome": nome,
            "fattore_entrate": float(fattore_entrate),
            "fattore_uscite": float(fattore_uscite),
            "saldo_minimo": _money(minimo),
            "saldo_finale": _money(saldo),
            "settimane": righe,
        })
    inclusi = sum(qualita[k] for k in ("scadenze_fornitori_incluse", "obblighi_inclusi", "crediti_inclusi"))
    esclusi = qualita["senza_data_esclusi"] + qualita["senza_importo_esclusi"] + qualita["tipi_non_classificati_esclusi"]
    qualita_completa = {
        **qualita,
        "record_inclusi": inclusi,
        "record_esclusi": esclusi,
        "copertura_percentuale": round(inclusi * 100 / max(inclusi + esclusi, 1), 1),
    }
    return {
        "versione_regole": "CF13W-002",
        "data_riferimento": riferimento.isoformat(),
        "orizzonte_settimane": 13,
        "liquidita_iniziale": _money(liquidita),
        "scenari": scenari,
        "qualita_dati": qualita_completa,
        "anomalie": _anomalie_cash_flow(scenari, qualita_completa),
        "assunzioni": [
            "Le scadenze arretrate sono riportate nella prima settimana.",
            "Base: 100% entrate e 100% uscite; prudente: 70% entrate; stress: 40% entrate e 110% uscite.",
            "Documenti senza data o importo non sono stimati e restano esclusi.",
            "Le fatture fornitore in partite_aperte sono escluse per evitare duplicati con lo scadenzario rateale.",
        ],
        "sola_lettura": True,
    }
