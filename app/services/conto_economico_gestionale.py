"""Mattoni comuni del conto economico gestionale: ricavi RT e costo del personale.

Un posto solo per tre decisioni che prima ogni pagina prendeva a modo suo
(Dashboard, Bilancio, Budget, Utile obiettivo, Chiusura d'esercizio):

1. **Quale corrispettivo vale.** Il soft-delete non ha un campo solo: accanto
   a ``entity_status = deleted`` convivono ``status`` ``deleted``,
   ``archived`` e ``archiviata`` (regola 13). Misurato il 27/09/2026: 30 righe
   di luglio avevano ``status: deleted`` con ``entity_status`` vuoto, e chi
   guardava solo il secondo contava luglio due volte.
2. **Quanto vale un corrispettivo in imponibile.** Gli XML recenti scrivono
   ``totale_imponibile``, lo storico ``imponibile`` (19 righe di agosto non
   hanno il primo). Il lordo ``totale`` non e' mai un ricavo: senza imponibile
   e senza IVA dichiarata la riga si **conta come non leggibile**, non si
   inventa un imponibile uguale al lordo.
3. **Quanto costa il personale.** Nessuna busta e nessuna riga di
   ``prima_nota_salari`` porta ``costo_azienda``: chi lo sommava otteneva 0 e
   la Dashboard mostrava un utile falso. Il dato vero e' il ``lordo`` delle
   buste (scritto da ``salari_unificati_v2.processa_cedolino_v2``, unico
   punto di scrittura dei cedolini). I contributi a carico dell'azienda non
   esistono sui dati: si dichiarano ``None`` col motivo, mai 0 e mai una
   percentuale stimata.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

#: Corrispettivo valido per ricavi, budget, chiusura e riepiloghi. ``$nin`` e
#: ``$ne`` su un campo assente passano: assente = valido (regola 11).
FILTRO_CORRISPETTIVI_VALIDI: Dict[str, Any] = {
    "entity_status": {"$ne": "deleted"},
    "status": {"$nin": ["deleted", "archived", "archiviata"]},
}

_PROIEZIONE_CORRISPETTIVO = {
    "_id": 0, "id": 1, "data": 1, "totale": 1, "totale_imponibile": 1,
    "imponibile": 1, "totale_iva": 1, "iva": 1,
}
_PROIEZIONE_BUSTA = {
    "_id": 0, "id": 1, "anno": 1, "mese": 1, "lordo": 1, "tfr_mese": 1, "tipo_cedolino": 1,
}

MOTIVO_CONTRIBUTI = (
    "Contributi a carico dell'azienda non disponibili: nessuna busta ne' "
    "riga salari riporta la quota datoriale. Il costo del personale "
    "esposto e' il solo lordo delle buste."
)


def _dec(valore: Any) -> Optional[Decimal]:
    if valore is None or valore == "":
        return None
    try:
        return Decimal(str(valore))
    except (InvalidOperation, ValueError):
        return None


def _euro(valore: Decimal) -> float:
    return float(valore.quantize(Decimal("0.01")))


def imponibile_corrispettivo(doc: Dict[str, Any]) -> Optional[Decimal]:
    """Imponibile di una chiusura RT, o None se il documento non lo dichiara.

    ``totale_imponibile`` (XML recenti) poi ``imponibile`` (storico), poi
    ``totale`` meno l'IVA **dichiarata**. Mai il lordo da solo.
    """
    for campo in ("totale_imponibile", "imponibile"):
        valore = _dec(doc.get(campo))
        if valore is not None and valore > 0:
            return valore
    totale = _dec(doc.get("totale"))
    iva = _dec(doc.get("totale_iva"))
    if iva is None:
        iva = _dec(doc.get("iva"))
    if totale is not None and totale == 0:
        return Decimal("0")
    if totale is not None and iva is not None:
        return totale - iva
    return None


def _iva_corrispettivo(doc: Dict[str, Any]) -> Decimal:
    iva = _dec(doc.get("totale_iva"))
    if iva is None:
        iva = _dec(doc.get("iva"))
    return iva or Decimal("0")


async def ricavi_corrispettivi(db, data: Dict[str, Any]) -> Dict[str, Any]:
    """Ricavi imponibili dei corrispettivi validi nell'intervallo ``data``.

    ``data`` e' il filtro Mongo sul campo ``data`` (es. ``{"$gte": .., "$lt": ..}``).
    ``per_mese`` serve al budget, che confronta mese per mese.
    """
    righe = await db["corrispettivi"].find(
        {**FILTRO_CORRISPETTIVI_VALIDI, "data": data}, _PROIEZIONE_CORRISPETTIVO,
    ).to_list(None)
    imponibile = Decimal("0")
    iva = Decimal("0")
    lordo = Decimal("0")
    per_mese: Dict[int, Decimal] = {}
    senza_imponibile: List[str] = []
    date_viste: List[str] = []
    for doc in righe:
        giorno = str(doc.get("data") or "")[:10]
        if giorno:
            date_viste.append(giorno)
        lordo += _dec(doc.get("totale")) or Decimal("0")
        iva += _iva_corrispettivo(doc)
        valore = imponibile_corrispettivo(doc)
        if valore is None:
            senza_imponibile.append(str(doc.get("id") or giorno))
            continue
        imponibile += valore
        try:
            mese = int(giorno[5:7])
        except ValueError:
            continue
        per_mese[mese] = per_mese.get(mese, Decimal("0")) + valore
    return {
        "imponibile": _euro(imponibile),
        "iva": _euro(iva),
        "lordo": _euro(lordo),
        "documenti": len(righe),
        "senza_imponibile": len(senza_imponibile),
        "senza_imponibile_id": senza_imponibile[:50],
        "dal": min(date_viste) if date_viste else None,
        "al": max(date_viste) if date_viste else None,
        "per_mese": {m: _euro(v) for m, v in sorted(per_mese.items())},
    }


def _mese_busta(busta: Dict[str, Any]) -> Optional[int]:
    try:
        return int(busta.get("mese"))
    except (TypeError, ValueError):
        return None


def riepiloga_buste(buste: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Costo del personale da un insieme di buste: lordo, conteggi e lacune.

    ``lordo`` e' None quando nessuna busta lo porta (nessuna busta, o tutte
    illeggibili): un periodo senza buste non costa zero, non lo sappiamo.
    Le buste senza lordo sono contate e rendono il dato incompleto.
    """
    buste = list(buste)
    totale = Decimal("0")
    con_lordo = 0
    tfr = Decimal("0")
    for busta in buste:
        # ``tfr_mese`` lo scrive salari_unificati_v2 con 0 come ripiego: solo
        # un valore positivo e' una quota letta dalla busta.
        quota_tfr = _dec(busta.get("tfr_mese"))
        if quota_tfr is not None and quota_tfr > 0:
            tfr += quota_tfr
        valore = _dec(busta.get("lordo"))
        if valore is None:
            continue
        totale += valore
        con_lordo += 1
    senza_lordo = len(buste) - con_lordo
    if not buste:
        motivo = "Nessuna busta paga registrata nel periodo"
    elif con_lordo == 0:
        motivo = "Nessuna busta del periodo riporta il lordo"
    elif senza_lordo:
        motivo = f"{senza_lordo} buste senza lordo: costo del personale parziale"
    else:
        motivo = None
    return {
        "lordo": _euro(totale) if con_lordo else None,
        "buste": len(buste),
        "buste_con_lordo": con_lordo,
        "buste_senza_lordo": senza_lordo,
        # Quota TFR letta dalle buste (None se nessuna la riporta): non entra
        # nel ``lordo``, che resta il costo del personale esposto ovunque.
        "tfr": _euro(tfr) if tfr > 0 else None,
        # La quota datoriale non esiste sui dati: dichiarata, mai stimata.
        "contributi": None,
        "contributi_motivo": MOTIVO_CONTRIBUTI,
        "incompleto": True,
        "motivo": motivo,
        "fonte": "cedolini.lordo",
    }


async def _buste_anno(db, anno: int) -> List[Dict[str, Any]]:
    # ``anno`` e' int nello scrittore canonico, stringa in qualche riga storica.
    return await db["cedolini"].find(
        {
            "anno": {"$in": [int(anno), str(anno)]},
            "entity_status": {"$ne": "deleted"},
            # una versione superata della stessa busta non e' un costo (`cedolini_versioni`)
            "status": {"$nin": ["deleted", "archived", "archiviata", "sostituito"]},
        },
        _PROIEZIONE_BUSTA,
    ).to_list(None)


async def costo_personale(db, anno: int, mese: Optional[int] = None) -> Dict[str, Any]:
    """Costo del personale dell'anno (o del mese): lordo delle buste."""
    buste = await _buste_anno(db, anno)
    if mese:
        buste = [b for b in buste if _mese_busta(b) == int(mese)]
    return riepiloga_buste(buste)


async def costo_personale_mensile(db, anno: int) -> Dict[int, Dict[str, Any]]:
    """Lo stesso riepilogo per ciascun mese, con una lettura sola."""
    buste = await _buste_anno(db, anno)
    return {
        m: riepiloga_buste(b for b in buste if _mese_busta(b) == m)
        for m in range(1, 13)
    }
