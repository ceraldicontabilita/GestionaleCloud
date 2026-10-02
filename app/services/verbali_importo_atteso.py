"""Importo atteso di un verbale: ridotto nei 5 giorni dalla notifica, poi ordinario.

Decisione del titolare (02/10/2026): passati 5 giorni dalla **data di notifica**
(quella della PEC, `notifiche_pec_verbali.py`) l'importo atteso del verbale passa
da solo all'importo ordinario, se il verbale lo porta (`importo_ordinario`, letto
dal PDF da `verbali_document_import.leggi_documento_verbale`). Il ridotto resta
nello storico del verbale e nel campo `importo_ridotto`; l'alert dice «scaduti i
5 giorni: importo ordinario».

Regole:
* la notifica vale solo se provata dalla PEC (`data_notifica_fonte == "pec"`): una
  data nata dalla ricezione di una mail non fa partire i termini;
* un verbale gia' pagato, chiuso o in quarantena non cambia (`e_chiuso`);
* senza importo ordinario letto non si inventa niente (`ordinario_non_letto`);
* idempotente: il marcatore `importo_atteso_fonte` ferma il secondo giro;
* importi in `Decimal` al centesimo; sul record `importo` resta il numero che
  tutti i motori confrontano con `amounts_equal_to_cent`, piu' `importo_centesimi`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from app.constants.stati_verbale import e_chiuso
from app.services.notifiche_pec_verbali import GIORNI_PAGAMENTO_RIDOTTO

logger = logging.getLogger(__name__)

COLLECTION = "verbali_noleggio"
CODICE_ALERT = "VERBALE_IMPORTO_ORDINARIO"
FONTE_ORDINARIO = "ordinario_dopo_5_giorni"
FILTRO_CANDIDATI: Dict[str, Any] = {
    "data_notifica_fonte": "pec",
    "importo_ordinario": {"$nin": [None, ""]},
    "importo_atteso_fonte": {"$ne": FONTE_ORDINARIO},
}

__all__ = [
    "CODICE_ALERT",
    "FONTE_ORDINARIO",
    "decimale",
    "valuta_importo_atteso",
    "applica_importo_ordinario",
    "aggiorna_importi_attesi",
]


def decimale(valore: Any) -> Optional[Decimal]:
    """Un importo come `Decimal` al centesimo; `None` se vuoto o illeggibile."""
    if valore in (None, "") or isinstance(valore, bool):
        return None
    try:
        return Decimal(str(valore)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _gg_mm_aaaa(giorno: date) -> str:
    return giorno.strftime("%d/%m/%Y")


def valuta_importo_atteso(verbale: Dict[str, Any], oggi: Optional[date] = None) -> Dict[str, Any]:
    """Dice se e perche' l'atteso di questo verbale passa all'ordinario. Non scrive.

    Ritorna ``{"applicare": bool, "motivo": str, ...}``; con ``applicare`` anche
    `ordinario`, `ridotto` (Decimal), `scadenza_ridotto` e `data_notifica`.
    """
    oggi = oggi or datetime.now(timezone.utc).date()
    if e_chiuso(verbale.get("stato")) or verbale.get("importo_pagato") not in (None, ""):
        return {"applicare": False, "motivo": "verbale_chiuso_o_pagato"}
    if verbale.get("importo_atteso_fonte") == FONTE_ORDINARIO:
        return {"applicare": False, "motivo": "gia_ordinario"}
    if verbale.get("data_notifica_fonte") != "pec" or not verbale.get("data_notifica"):
        return {"applicare": False, "motivo": "notifica_non_provata_da_pec"}
    try:
        notifica = date.fromisoformat(str(verbale["data_notifica"])[:10])
    except ValueError:
        return {"applicare": False, "motivo": "data_notifica_illeggibile"}
    ordinario = decimale(verbale.get("importo_ordinario"))
    if ordinario is None or ordinario <= 0:
        return {"applicare": False, "motivo": "ordinario_non_letto"}
    scadenza = notifica + timedelta(days=GIORNI_PAGAMENTO_RIDOTTO)
    if oggi <= scadenza:
        return {"applicare": False, "motivo": "entro_i_5_giorni", "scadenza_ridotto": scadenza.isoformat()}
    ridotto = decimale(verbale.get("importo_ridotto"))
    if ridotto is None:
        ridotto = decimale(verbale.get("importo"))
    return {
        "applicare": True, "motivo": "scaduti_i_5_giorni",
        "ordinario": ordinario, "ridotto": ridotto,
        "scadenza_ridotto": scadenza.isoformat(), "data_notifica": notifica.isoformat(),
    }


async def applica_importo_ordinario(db, verbale: Dict[str, Any], oggi: Optional[date] = None) -> Dict[str, Any]:
    """Scrive l'importo ordinario come atteso e apre l'alert. Idempotente."""
    esito = valuta_importo_atteso(verbale, oggi)
    if not esito["applicare"]:
        return esito
    ordinario: Decimal = esito["ordinario"]
    ridotto: Optional[Decimal] = esito["ridotto"]
    adesso = datetime.now(timezone.utc).isoformat()
    notifica = date.fromisoformat(esito["data_notifica"])
    scadenza = date.fromisoformat(esito["scadenza_ridotto"])
    motivo = (
        f"scaduti i {GIORNI_PAGAMENTO_RIDOTTO} giorni dalla notifica PEC del {_gg_mm_aaaa(notifica)}: "
        f"importo ordinario {ordinario} €"
        + (f" (ridotto {ridotto} € fino al {_gg_mm_aaaa(scadenza)})" if ridotto is not None else "")
    )
    storico: List[Dict[str, Any]] = [dict(v) for v in (verbale.get("storico") or []) if isinstance(v, dict)]
    storico.append({
        "tipo": "importo_atteso_ordinario",
        "data": adesso,
        "importo_prima": str(ridotto) if ridotto is not None else None,
        "importo_dopo": str(ordinario),
        "motivo": motivo,
    })
    campi = {
        "importo": float(ordinario),
        "importo_centesimi": int(ordinario * 100),
        "importo_atteso": str(ordinario),
        "importo_atteso_fonte": FONTE_ORDINARIO,
        "importo_atteso_dal": (scadenza + timedelta(days=1)).isoformat(),
        "importo_ridotto": float(ridotto) if ridotto is not None else verbale.get("importo_ridotto"),
        "importo_ridotto_scaduto_il": scadenza.isoformat(),
        "storico": storico,
        "updated_at": adesso,
    }
    # Claim sul marcatore: due giri insieme non scrivono due righe di storico.
    res = await db[COLLECTION].update_one(
        {"id": verbale["id"], "importo_atteso_fonte": {"$ne": FONTE_ORDINARIO}}, {"$set": campi},
    )
    if not res.modified_count:
        return {"applicare": False, "motivo": "gia_ordinario"}
    from app.services.alert_engine import genera_alert

    await genera_alert(
        CODICE_ALERT, str(verbale["id"]), COLLECTION,
        f"Verbale {verbale.get('numero_verbale') or verbale['id']}: {motivo}",
        db,
        extra={
            "numero_verbale": verbale.get("numero_verbale"), "targa": verbale.get("targa"),
            "importo_ordinario": str(ordinario),
            "importo_ridotto": str(ridotto) if ridotto is not None else None,
            "data_notifica": notifica.isoformat(), "scadenza_ridotto": scadenza.isoformat(),
        },
    )
    return {**esito, "scritto": True, "motivo_testo": motivo}


async def aggiorna_importi_attesi(db, oggi: Optional[date] = None, limite: int = 2000) -> Dict[str, Any]:
    """Giro giornaliero (job `verbali_notifications`) e all'arrivo della PEC.

    Legge solo i candidati (notifica PEC, ordinario letto, non ancora applicato) e
    chiude l'alert dei verbali nel frattempo pagati o chiusi. Secondo giro: 0.
    """
    esito = {"letti": 0, "aggiornati": 0, "saltati": {}, "alert_chiusi": 0}
    verbali = await db[COLLECTION].find(
        FILTRO_CANDIDATI, {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0},
    ).to_list(limite)
    for verbale in verbali:
        esito["letti"] += 1
        try:
            risultato = await applica_importo_ordinario(db, verbale, oggi)
        except Exception as exc:  # noqa: BLE001 - un verbale guasto non ferma il giro
            logger.warning("Importo atteso del verbale %s non aggiornato: %s: %s",
                           verbale.get("id"), type(exc).__name__, exc)
            esito["saltati"]["errore"] = esito["saltati"].get("errore", 0) + 1
            continue
        if risultato.get("scritto"):
            esito["aggiornati"] += 1
        else:
            motivo = risultato.get("motivo", "altro")
            esito["saltati"][motivo] = esito["saltati"].get(motivo, 0) + 1
    # Un verbale pagato o chiuso non chiede piu' l'ordinario: il suo alert si chiude.
    from app.services.alert_engine import COLL_ALERTS, STATO_ALERT_APERTO, risolvi_alert

    aperti = await db[COLL_ALERTS].find(
        {"codice": CODICE_ALERT, "stato": STATO_ALERT_APERTO}, {"_id": 0, "entita_id": 1},
    ).to_list(limite)
    for alert in aperti:
        verbale = await db[COLLECTION].find_one({"id": alert.get("entita_id")}, {"_id": 0, "stato": 1, "importo_pagato": 1})
        if verbale is None or e_chiuso(verbale.get("stato")) or verbale.get("importo_pagato") not in (None, ""):
            esito["alert_chiusi"] += await risolvi_alert(CODICE_ALERT, alert["entita_id"], db, "verbale_pagato_o_chiuso")
    return esito
