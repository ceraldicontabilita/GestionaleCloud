"""
Scadenze e Notifiche Router - Sistema alert per scadenze fiscali e pagamenti

Gestisce:
- Scadenze IVA mensili e confronto con F24 ricevuti
- Scadenze per tributo e periodo dal calendario fiscale canonico
- Le fatture fornitore NON hanno scadenza (decide il titolare quando pagarle)
- Notifiche personalizzate
"""

from fastapi import APIRouter, Query, HTTPException, Path as PathParam
from typing import Annotated, Dict, Any, Optional, Literal
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.services.scadenze_unificate import carica_scadenze, seleziona, oggi_roma, cents
from datetime import datetime, date, timedelta, timezone
from app.database import Database
import logging
import uuid
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

async def _iva_acquisti_ufficiale(db, periodo: str) -> Dict[str, Any]:
    """IVA acquisti detraibile del periodo 'YYYY-MM' secondo il motore
    ufficiale di liquidazione (la specifica del titolare (non è nel repository: vale il codice) §10-11), la stessa
    logica usata da POST /api/iva/liquidazioni/calcola — non una terza
    formula parallela.

    Bug corretto 15/07/2026: prima questa pagina sommava semplicemente
    `iva` di TUTTE le fatture ricevute/emesse nel mese, senza escludere
    quelle già utilizzate in una liquidazione precedente (doppio conteggio
    quando una fattura di fine mese viene attribuita al mese prima per la
    regola del giorno 15), le note di credito, o i documenti annullati —
    poteva mostrare un "IVA da versare" diverso da quello confermato nella
    pagina Gestione IVA.

    Se per il periodo esiste già una liquidazione CONFERMATA/TRASMESSA,
    ritorna il suo valore definitivo (fonte="liquidazione_confermata");
    altrimenti calcola una STIMA live con le stesse regole di selezione,
    mai persistita (fonte="stima" — il numero definitivo nasce solo
    confermando la liquidazione dalla pagina Gestione IVA).
    """
    from app.routers.iva import _fatture_del_periodo, COLL_LIQ
    from app.engines import liquidazione_iva_engine as liq

    confermata = await db[COLL_LIQ].find_one(
        {"periodo": periodo, "stato": {"$in": [liq.CONFERMATA, liq.TRASMESSA]}},
        sort=[("versione", -1)],
    )
    if confermata:
        return {
            "iva_acquisti": round(float(confermata.get("iva_acquisti") or 0), 2),
            "fonte": "liquidazione_confermata",
        }

    fatture = await _fatture_del_periodo(db, periodo)
    incluse, _escluse = liq.seleziona_fatture_per_liquidazione(fatture, periodo)
    # Le note di credito riducono l'IVA detraibile (segno negativo).
    iva_acquisti = liq.calcola_totali(incluse)["iva_acquisti"]
    return {"iva_acquisti": iva_acquisti, "fonte": "stima"}


# Anno di scadenza: una competenza di dicembre compare a gennaio successivo.
Anno = Annotated[Optional[int], Query(ge=2000, le=2100)]
Mese = Annotated[Optional[int], Query(ge=1, le=12)]
Stato = Literal["aperte", "scadute", "chiuse", "da_verificare", "tutte"]


async def conta_f24_da_pagare(db, limite_30: str) -> int:
    """Modelli distinti aperti, dalle righe fiscali e dalle prove di pagamento."""
    limite = date.fromisoformat(limite_30)
    projection = await carica_scadenze(db, limite.year)
    return len(
        {
            fid
            for row in projection["righe"]
            if not row.get("completata")
            and row.get("data")
            and row["data"] <= limite_30
            for fid in row.get("f24_ids", [])
        }
    )


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
@router.get("/tutte")
@handle_errors
async def get_tutte_scadenze(
    anno: Anno = None,
    mese: Mese = None,
    tipo: Annotated[Optional[str], Query(pattern=r"^[A-Z0-9_]{1,60}$")] = None,
    include_passate: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    stato: Optional[Stato] = None,
) -> Dict[str, Any]:
    """Una proiezione per lista, riepiloghi e documenti. Nessuna scrittura."""
    oggi = oggi_roma()
    anno = anno or oggi.year
    projection = await carica_scadenze(Database.get_db(), anno, oggi)
    rows, stats = seleziona(
        projection,
        anno=anno,
        oggi=oggi,
        mese=mese,
        tipo=tipo,
        stato=stato,
        include_chiuse=include_passate or stato == "tutte",
    )
    return {
        "scadenze": rows[offset : offset + limit],
        "totale": len(rows),
        "pagination": {"offset": offset, "limit": limit},
        "statistiche": stats,
        "anno": anno,
        "data_riferimento": oggi.isoformat(),
        "tipi": sorted({r["tipo"] for r in projection["righe"]} | {"CUSTOM"}),
        **{
            k: projection[k]
            for k in ("segnalazioni", "documenti_da_verificare", "documenti_periodo")
        },
    }


@router.get("/prossime")
@handle_errors
async def get_prossime_scadenze(
    giorni: Annotated[int, Query(ge=1, le=366)] = 30,
    limit: Annotated[int, Query(ge=1, le=500)] = 10,
) -> Dict[str, Any]:
    oggi = oggi_roma()
    end = oggi + timedelta(days=giorni)
    rows = []
    for year in range(oggi.year, end.year + 1):
        projection = await carica_scadenze(Database.get_db(), year, oggi)
        rows.extend(
            r
            for r in projection["righe"]
            if not r.get("completata")
            and r.get("data")
            and oggi.isoformat() <= r["data"] <= end.isoformat()
        )
    rows.sort(key=lambda r: (r["data"], r["id"]))
    return {
        "scadenze": rows[:limit],
        "totale": len(rows),
        "prossima_scadenza": rows[0] if rows else None,
    }


@router.get("/iva-mensile/{anno}")
@handle_errors
async def get_scadenze_iva_mensile(
    anno: Annotated[int, PathParam(ge=2000, le=2100)],
) -> Dict[str, Any]:
    """
    Ottiene le scadenze IVA mensili per un anno.
    Per regime IVA mensile: versamento entro il 16 del mese successivo.
    """
    db = Database.get_db()
    from app.services.iva_liquidation_query import euros, get_iva_period_snapshot

    scadenze_mensili = []

    for mese in range(1, 13):
        snapshot = await get_iva_period_snapshot(db, anno=anno, mese=mese)

        # IVA Credito (fatture) — motore ufficiale di liquidazione, vedi
        # _iva_acquisti_ufficiale.
        mesi_nomi = [
            "",
            "Gennaio",
            "Febbraio",
            "Marzo",
            "Aprile",
            "Maggio",
            "Giugno",
            "Luglio",
            "Agosto",
            "Settembre",
            "Ottobre",
            "Novembre",
            "Dicembre",
        ]

        scadenze_mensili.append(
            {
                "mese": mese,
                "mese_nome": mesi_nomi[mese],
                "periodo": f"{mesi_nomi[mese]} {anno}",
                "data_scadenza": snapshot["scadenza_legale"],
                "scadenza_nominale": snapshot["scadenza_nominale"],
                "scadenza_legale": snapshot["scadenza_legale"],
                "iva_debito": snapshot.get("iva_vendite"),
                "iva_debito_cents": snapshot.get("iva_vendite_cents"),
                "iva_credito": snapshot.get("iva_acquisti"),
                "iva_credito_cents": snapshot.get("iva_acquisti_cents"),
                "saldo": snapshot.get("saldo"),
                "saldo_cents": snapshot.get("saldo_cents"),
                "da_versare": bool(
                    snapshot.get("saldo_cents") is not None
                    and snapshot["saldo_cents"] > 0
                ),
                "importo_versamento": snapshot.get("debito_periodo"),
                "importo_versamento_cents": snapshot.get("debito_periodo_cents"),
                "a_credito": snapshot.get("credito_periodo"),
                "a_credito_cents": snapshot.get("credito_periodo_cents"),
                "stato": (
                    snapshot["stato_calcolo"]
                    if snapshot["stato_calcolo"] in ("NON_CALCOLATO", "DATI_MANCANTI")
                    else (
                        "da_versare"
                        if (snapshot.get("saldo_cents") or 0) > 0
                        else "a_credito"
                    )
                ),
                "attendibile": snapshot.get("attendibile"),
                "motivi": snapshot.get("motivi") or [],
                "giorni_senza_corrispettivo": snapshot.get("giorni_senza_corrispettivo")
                or [],
                "giorni_con_corrispettivo": snapshot.get("giorni_con_corrispettivo"),
                "giorni_mese": snapshot.get("giorni_mese"),
                "giorni_mancanti": _giorni_mancanti(snapshot["scadenza_legale"]),
                "fonte": (
                    "stima"
                    if snapshot["fonte"] == "calcolo_canonico"
                    else snapshot["fonte"]
                ),
                "fonte_calcolo": snapshot["fonte_calcolo"],
                "conteggi": snapshot["conteggi"],
            }
        )

    calcolate = [s for s in scadenze_mensili if s["saldo_cents"] is not None]
    totale_da_versare_cents = sum(s["importo_versamento_cents"] or 0 for s in calcolate)
    totale_a_credito_cents = sum(s["a_credito_cents"] or 0 for s in calcolate)

    # Il motore ha già applicato il credito del periodo precedente.
    # Il debito mensile non è una somma cumulativa dei debiti dei mesi passati.
    for s in scadenze_mensili:
        value = s["importo_versamento_cents"]
        s["da_versare_effettivo"] = value is not None and value > 0
        s["importo_versamento_effettivo_cents"] = value
        s["importo_versamento_effettivo"] = euros(value) if value is not None else None
        s["saldo_progressivo"] = None
        s["saldo_progressivo_cents"] = None

    return {
        "anno": anno,
        "regime": "mensile",
        "scadenze": scadenze_mensili,
        "totale_da_versare": euros(totale_da_versare_cents),
        "totale_da_versare_cents": totale_da_versare_cents,
        "totale_a_credito": euros(totale_a_credito_cents),
        "totale_a_credito_cents": totale_a_credito_cents,
        "saldo_annuale": euros(totale_da_versare_cents - totale_a_credito_cents),
        "saldo_annuale_cents": totale_da_versare_cents - totale_a_credito_cents,
        "saldo_progressivo": None,
        "saldo_progressivo_cents": None,
        "periodi_non_disponibili": 12 - len(calcolate),
        "fonte_calcolo": "iva_liquidation_query_v1",
    }


class NuovaScadenza(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    data_scadenza: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    descrizione: str = Field(min_length=1, max_length=2000)
    tipo: Literal[
        "CUSTOM",
        "FATTURA",
        "F24",
        "IVA",
        "INPS",
        "INAIL",
        "IMU",
        "IRES",
        "IRAP",
        "ALTRO",
    ] = "CUSTOM"
    importo: Optional[Decimal] = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    priorita: Literal["bassa", "media", "alta", "critica"] = "media"
    note: str = Field(default="", max_length=10000)

    @field_validator("data_scadenza")
    @classmethod
    def data_valida(cls, value):
        parsed = date.fromisoformat(value)
        if not 2000 <= parsed.year <= 2100:
            raise ValueError("Anno supportato: da 2000 a 2100")
        return parsed.isoformat()


@router.post("/crea")
@handle_errors
async def crea_notifica_scadenza(data: NuovaScadenza) -> Dict[str, Any]:
    """Il promemoria non registra un pagamento né crea una fattura."""
    notifica = {
        **data.model_dump(exclude={"importo"}),
        "id": str(uuid.uuid4()),
        "importo_cents": cents(data.importo),
        "importo": float(data.importo) if data.importo is not None else None,
        "completata": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await Database.get_db()["notifiche_scadenze"].insert_one(notifica.copy())
    return {"success": True, "notifica": notifica}


@router.put("/completa/{notifica_id}")
@handle_errors
async def completa_notifica(notifica_id: str) -> Dict[str, Any]:
    """Segna una notifica come completata."""
    db = Database.get_db()

    result = await db["notifiche_scadenze"].update_one(
        {"id": notifica_id},
        {
            "$set": {
                "completata": True,
                "completata_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notifica non trovata")

    return {"success": True, "message": "Notifica completata"}


@router.delete("/{notifica_id}")
@handle_errors
async def elimina_notifica(notifica_id: str) -> Dict[str, Any]:
    """Elimina una notifica personalizzata."""
    db = Database.get_db()

    result = await db["notifiche_scadenze"].delete_one({"id": notifica_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notifica non trovata")

    return {"success": True, "message": "Notifica eliminata"}


def _giorni_mancanti(data_str: str) -> Optional[int]:
    """Calcola giorni mancanti alla scadenza."""
    if not data_str:
        return None
    try:
        data = datetime.strptime(data_str[:10], "%Y-%m-%d").date()
        return (data - oggi_roma()).days
    except (ValueError, TypeError):
        return None


@router.get("/dashboard-widget")
@handle_errors
async def get_dashboard_scadenze(anno: Anno = None) -> Dict[str, Any]:
    oggi = oggi_roma()
    anno = anno or oggi.year
    projection = await carica_scadenze(Database.get_db(), anno, oggi)
    rows, stats = seleziona(projection, anno=anno, oggi=oggi)
    entro30 = [
        r
        for r in rows
        if r.get("giorni_mancanti") is not None and r["giorni_mancanti"] <= 30
    ]
    modelli = {fid for r in entro30 for fid in r.get("f24_ids", [])}
    return {
        "anno": anno,
        "totale_alert": stats["urgenti"],
        "statistiche": stats,
        "f24": {
            "da_pagare_30gg": len(modelli),
            "senza_data": sum(
                not r.get("data") for r in rows if r.get("source") == "tributo"
            ),
            "urgenza": "alta" if modelli else "bassa",
        },
        "fiscali": {"prossime": len(entro30), "dettaglio": entro30[:3]},
    }
