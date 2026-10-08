"""Anticipo TFR pagato dentro la busta: dalla voce letta all'acconto TFR, una volta sola.

La busta Zucchetti riporta l'anticipo come competenza (voce ``000081
Anticipazione T.F.R.``, tassata a parte) e il netto lo contiene gia': non c'e'
un bonifico a parte da cercare. Il lettore dei cedolini lo salva nei dati chiave
(``anticipo_tfr_busta``, ``anticipo_tfr_voce``); qui lo si porta nel motore degli
acconti TFR (``tfr_acconti``): scala ``tfr_accantonato`` e scrive nel giornale del
gestionale DARE 29.01.01 / AVERE 39.07.05.

Idempotenza: l'acconto ha un ``id`` che dipende solo da codice fiscale, periodo e
voce. Il motore scala il fondo a ogni chiamata, quindi si chiama **solo** se
l'acconto non porta ``tfr_registrato``; un secondo passaggio (stessa busta riletta,
copia, ricarica da scheda) non fa niente.
"""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COLL_ACCONTI = "acconti_dipendenti"
SORGENTE = "cedolino_anticipo_tfr"


def importo_it(testo: Any) -> Optional[Decimal]:
    """«1.800,00» -> Decimal('1800.00'); illeggibile o non positivo -> None, mai zero."""
    if testo in (None, ""):
        return None
    try:
        valore = Decimal(str(testo).strip().replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None
    return valore.quantize(Decimal("0.01")) if valore > 0 else None


def id_acconto(codice_fiscale: str, anno: int, mese: int, voce: str) -> str:
    return f"tfr-busta-{str(codice_fiscale).upper()}-{int(anno):04d}{int(mese):02d}-{voce}"


async def registra_anticipo_tfr_da_busta(db, *, codice_fiscale: str, anno: Any, mese: Any,
                                         importo: Any, voce: str = "000081") -> Dict[str, Any]:
    """Registra l'anticipo TFR di una busta col motore degli acconti. Mai un'eccezione muta.

    Esiti: ``registrato``, ``gia_registrato``, ``importo_illeggibile``,
    ``periodo_illeggibile``, ``dipendente_non_trovato``.
    """
    from app.services.tfr_acconti import registra_acconto_tfr

    cifre = importo_it(importo)
    if cifre is None:
        return {"esito": "importo_illeggibile"}
    try:
        anno_i, mese_i = int(anno), int(mese)
        if not (1 <= mese_i <= 12) or anno_i < 2000:
            raise ValueError("periodo fuori misura")
    except (TypeError, ValueError):
        return {"esito": "periodo_illeggibile"}

    cf = str(codice_fiscale or "").upper()
    dipendente = await db["dipendenti"].find_one({"codice_fiscale": cf}, {"_id": 0})
    if not dipendente or not dipendente.get("id"):
        return {"esito": "dipendente_non_trovato", "codice_fiscale": cf}

    chiave = id_acconto(cf, anno_i, mese_i, voce)
    esistente = await db[COLL_ACCONTI].find_one({"id": chiave}, {"_id": 0})
    if esistente and esistente.get("tfr_registrato"):
        return {"esito": "gia_registrato", "acconto_id": chiave}

    adesso = datetime.now(timezone.utc).isoformat()
    ultimo_giorno = calendar.monthrange(anno_i, mese_i)[1]
    acconto = esistente or {
        "id": chiave,
        "dipendente_id": dipendente["id"],
        "dipendente_nome": dipendente.get("nome_completo", ""),
        "tipo": "tfr",
        "importo": float(cifre),
        "data": f"{anno_i:04d}-{mese_i:02d}-{ultimo_giorno:02d}",
        "anno": anno_i,
        "mese": mese_i,
        "note": f"Anticipazione TFR in busta {mese_i:02d}/{anno_i} (voce {voce})",
        "natura_acconto": "su_pregresso",
        "tipo_bonifico": None,
        "scalato_su_anno_mese": f"{anno_i:04d}-{mese_i:02d}",
        "stato": "scalato_su_cedolino",
        "movimento_bancario_id": None,
        "riconciliato_il": None,
        "cedolino_id": None,
        "importo_scalato_effettivo": float(cifre),
        "source": SORGENTE,
        "created_at": adesso,
        "updated_at": adesso,
    }
    if not esistente:
        await db[COLL_ACCONTI].insert_one(dict(acconto))

    await registra_acconto_tfr(db, db, acconto, dipendente)
    await db[COLL_ACCONTI].update_one(
        {"id": chiave}, {"$set": {"tfr_registrato": True, "updated_at": adesso}})
    logger.info("[TFR-BUSTA] anticipo %s registrato per %s (%02d/%d)", cifre, cf[:6], mese_i, anno_i)
    return {"esito": "registrato", "acconto_id": chiave, "importo": str(cifre)}


async def registra_dalla_busta(db, ced: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Se la busta letta porta l'anticipo TFR lo registra; altrimenti None.

    Un guasto non ferma la scrittura della busta (e' gia' salvata): si dichiara nel
    log con il tipo dell'eccezione e la riga resta recuperabile dal ripasso notturno.
    """
    chiave = ced.get("dati_chiave") or {}
    if not chiave.get("anticipo_tfr_busta"):
        return None
    try:
        return await registra_anticipo_tfr_da_busta(
            db, codice_fiscale=ced.get("codice_fiscale"), anno=ced.get("anno"),
            mese=ced.get("mese"), importo=chiave["anticipo_tfr_busta"],
            voce=chiave.get("anticipo_tfr_voce") or "000081")
    except Exception as exc:  # noqa: BLE001 - la busta e' scritta, l'anticipo si riprova dal ripasso
        logger.warning("[TFR-BUSTA] anticipo della busta %s %s/%s non registrato: %s: %s",
                       str(ced.get("codice_fiscale"))[:6], ced.get("mese"), ced.get("anno"),
                       type(exc).__name__, exc)
        return {"esito": "errore", "motivo": f"{type(exc).__name__}: {exc}"}
