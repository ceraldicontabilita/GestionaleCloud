"""Quote TFR maturate dalle buste paga, lette dal gestionale per la pagina TFR di HR.

L'handler ``app/handlers/tfr.handler_aggiorna_tfr`` scrive, a ogni cedolino
importato, una riga in ``tfr_accantonamenti`` **del gestionale** (dipendente,
anno, mese, ``quota``). L'archivio HR non le ha: senza questa lettura la
pagina TFR di HR mostrava zero per chi ha il TFR maturato solo dalle buste.

Il dipendente HR si aggancia a quello del gestionale per codice fiscale (o per
lo stesso ``id``), mai per nome. Un dato che non si puo' leggere e' ``None``
(«Dato non disponibile»), mai zero.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FONTE_MANUALE = "manuale"
FONTE_BUSTE = "buste"
FONTE_NESSUNA = "nessuna"

__all__ = ["FONTE_MANUALE", "FONTE_BUSTE", "FONTE_NESSUNA", "quote_tfr_da_buste", "tfr_con_fonte"]


def _cents(valore: Any) -> Optional[int]:
    if valore in (None, ""):
        return None
    try:
        return int((Decimal(str(valore)) * 100).quantize(Decimal("1")))
    except (ValueError, ArithmeticError):
        return None


async def quote_tfr_da_buste(db_gest, *, codice_fiscale: Optional[str],
                             dipendente_id: Optional[str],
                             anagrafiche: Optional[List[dict]] = None,
                             quote: Optional[List[dict]] = None) -> Dict[str, Any]:
    """Le quote mensili di ``tfr_accantonamenti`` del gestionale per un dipendente.

    Restituisce ``disponibile`` (la lettura e' riuscita), ``totale`` (``None`` se
    nessuna riga), le ``righe`` ordinate per anno e mese e gli id del gestionale
    usati. Una riga annuale senza ``mese`` (import manuale LUL del gestionale) non
    e' una quota da busta e resta fuori dal totale."""
    esito: Dict[str, Any] = {"disponibile": False, "totale": None, "righe": [],
                             "dipendenti_gestionale": [], "motivo": None}
    if db_gest is None:
        esito["motivo"] = "archivio gestionale non raggiungibile"
        return esito
    cf = str(codice_fiscale or "").strip().upper()
    try:
        filtro: Dict[str, Any] = {"$or": [{"id": dipendente_id}]} if dipendente_id else {"$or": []}
        if cf:
            filtro["$or"].append({"codice_fiscale": cf})
        if not filtro["$or"]:
            esito.update(disponibile=True, motivo="dipendente senza codice fiscale ne' id")
            return esito
        if anagrafiche is None:
            corrispondenti = await db_gest["dipendenti"].find(
                filtro, {"_id": 0, "id": 1, "codice_fiscale": 1}).to_list(50)
        else:
            corrispondenti = [d for d in anagrafiche if
                              (dipendente_id and str(d.get("id")) == str(dipendente_id)) or
                              (cf and str(d.get("codice_fiscale") or "").strip().upper() == cf)]
        ids = sorted({str(d.get("id")) for d in corrispondenti if d.get("id")})
        # anche le righe scritte direttamente con l'id HR (stesso id nei due archivi)
        if dipendente_id and dipendente_id not in ids:
            ids.append(dipendente_id)
        if quote is None:
            righe = await db_gest["tfr_accantonamenti"].find(
                {"dipendente_id": {"$in": ids}}, {"_id": 0}).to_list(1000)
        else:
            righe = [r for r in quote if str(r.get("dipendente_id")) in ids]
    except Exception as exc:  # noqa: BLE001 - la pagina dice che il dato manca, non inventa zero
        logger.warning("[TFR] quote da buste non lette per %s: %s: %s", cf or dipendente_id,
                       type(exc).__name__, exc)
        esito["motivo"] = f"{type(exc).__name__}: {exc}"
        return esito
    esito["disponibile"] = True
    esito["dipendenti_gestionale"] = ids
    mensili: List[Dict[str, Any]] = []
    for r in righe:
        if not r.get("mese"):
            continue
        quota = _cents(r.get("quota"))
        if quota is None:
            continue
        mensili.append({
            "id": r.get("id"), "anno": r.get("anno"), "mese": r.get("mese"),
            "quota": quota / 100, "lordo_base": r.get("lordo_base"),
            "source": r.get("source"), "periodo": f"{int(r['mese']):02d}/{r.get('anno')}",
        })
    mensili.sort(key=lambda a: (int(a.get("anno") or 0), int(a.get("mese") or 0)))
    esito["righe"] = mensili
    if mensili:
        esito["totale"] = sum(_cents(a["quota"]) for a in mensili) / 100
    return esito


def tfr_con_fonte(tfr_manuale: float, tfr_da_cedolini_hr: float, accantonamenti_hr: int,
                  buste: Dict[str, Any]) -> Dict[str, Any]:
    """Sceglie il TFR accantonato e dichiara da dove viene.

    Il valore manuale della scheda HR (import LUL o accantonamento registrato a
    mano, ``tfr_accantonato`` piu' ``progressivi.tfr_accantonato``) vince se c'e':
    si tiene **o** quello **o** la somma delle quote da buste, mai la somma dei
    due. Senza nessuno dei due il TFR e' ``None`` e la fonte ``nessuna``."""
    manuale_attivo = tfr_manuale > 0 or tfr_da_cedolini_hr > 0 or accantonamenti_hr > 0
    if manuale_attivo:
        return {"tfr_accantonato": round(tfr_manuale + tfr_da_cedolini_hr, 2), "tfr_fonte": FONTE_MANUALE}
    if buste.get("totale") is not None:
        return {"tfr_accantonato": round(float(buste["totale"]), 2), "tfr_fonte": FONTE_BUSTE}
    return {"tfr_accantonato": None, "tfr_fonte": FONTE_NESSUNA}
