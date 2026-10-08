"""Riepilogo di Cassa e corrispettivi XML per la pagina Controllo mensile.

La pagina scaricava ogni movimento di Cassa e ogni corrispettivo del periodo
(``limit=10000``) solo per sommarli per mese o per giorno. Le stesse somme si
fanno qui, sulle stesse righe che la pagina leggeva (``filtro_saldo_prima_nota``
per la Cassa, i corrispettivi non eliminati per l'XML), e al browser arrivano
solo i totali: dodici mesi, oppure i giorni di un mese col dettaglio dei
versamenti.

Regole (le stesse che stavano in ``ControlloMensile.jsx``):

- corrispettivi in Cassa = entrate di categoria «Corrispettivi» o da
  ``excel_corrispettivi``;
- versamento = uscita di categoria o descrizione che contiene «versamento»,
  sommata in valore assoluto;
- saldo Cassa del periodo = entrate − uscite;
- in Cassa entra solo la quota contanti dell'XML: la differenza e' contanti
  XML − corrispettivi in Cassa, e non si calcola (``None``) se anche un solo
  XML del periodo non dichiara i contanti;
- non riscosso e ammontare annulli contano solo i valori positivi.
"""
from __future__ import annotations

import calendar
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.database import Database

from .common import COLLECTION_PRIMA_NOTA_CASSA, filtro_saldo_prima_nota

_CENTESIMO = Decimal("0.01")
_NUMERO_INIZIALE = re.compile(r"^\s*[-+]?(\d+(\.\d*)?|\.\d+)")


def numero(valore: Any) -> Optional[Decimal]:
    """Il valore come lo leggeva ``parseFloat``: ``None`` se non e' un numero."""
    if valore is None or isinstance(valore, bool):
        return None
    if isinstance(valore, (int, float, Decimal)):
        try:
            d = Decimal(str(valore))
        except InvalidOperation:
            return None
        return d if d.is_finite() else None
    trovato = _NUMERO_INIZIALE.match(str(valore))
    return Decimal(trovato.group(0).strip()) if trovato else None


def _n(valore: Any) -> Decimal:
    return numero(valore) or Decimal("0")


def _intero(valore: Any) -> int:
    return int(_n(valore))


def _euro(valore: Decimal) -> float:
    return float(valore.quantize(_CENTESIMO))


def e_versamento(movimento: Dict[str, Any]) -> bool:
    categoria = str(movimento.get("categoria") or "")
    descrizione = str(movimento.get("descrizione") or "")
    return movimento.get("tipo") == "uscita" and (
        categoria == "Versamento"
        or "versamento" in categoria.lower()
        or "versamento" in descrizione.lower()
    )


def e_corrispettivo_in_cassa(movimento: Dict[str, Any]) -> bool:
    return movimento.get("tipo") == "entrata" and (
        movimento.get("categoria") == "Corrispettivi"
        or movimento.get("source") == "excel_corrispettivi"
    )


def somma_cassa(movimenti: List[Dict[str, Any]]) -> Dict[str, Any]:
    corrispettivi = versamenti = entrate = uscite = Decimal("0")
    for m in movimenti:
        importo = _n(m.get("importo"))
        if e_corrispettivo_in_cassa(m):
            corrispettivi += importo
        if e_versamento(m):
            versamenti += abs(importo)
        if m.get("tipo") == "entrata":
            entrate += importo
        elif m.get("tipo") == "uscita":
            uscite += importo
    return {
        "corrispettivi": corrispettivi, "versamenti": versamenti,
        "entrate": entrate, "uscite": uscite, "movimenti": len(movimenti),
    }


def somma_corrispettivi(righe: List[Dict[str, Any]]) -> Dict[str, Any]:
    totale = contanti = non_riscosso = annulli_importo = Decimal("0")
    senza_contanti = documenti = annulli = non_riscosso_n = annulli_importo_n = 0
    for c in righe:
        totale += _n(c.get("totale"))
        documenti += _intero(c.get("numero_documenti"))
        annulli += _intero(c.get("annulli"))
        contante = c.get("pagato_contanti")
        valore = None if contante in (None, "") else numero(contante)
        if valore is None:
            senza_contanti += 1
        else:
            contanti += valore
        nr = _n(c.get("pagato_non_riscosso"))
        if nr > 0:
            non_riscosso += nr
            non_riscosso_n += 1
        aa = _n(c.get("totale_ammontare_annulli"))
        if aa > 0:
            annulli_importo += aa
            annulli_importo_n += 1
    return {
        "totale": totale, "contanti": contanti, "senza_contanti": senza_contanti,
        "numero_documenti": documenti, "annulli": annulli,
        "non_riscosso": non_riscosso, "non_riscosso_count": non_riscosso_n,
        "ammontare_annulli": annulli_importo, "ammontare_annulli_count": annulli_importo_n,
        "righe": len(righe),
    }


def riga_periodo(movimenti: List[Dict[str, Any]], corrispettivi: List[Dict[str, Any]]) -> Dict[str, Any]:
    cassa = somma_cassa(movimenti)
    xml = somma_corrispettivi(corrispettivi)
    differenza = None if xml["senza_contanti"] > 0 else xml["contanti"] - cassa["corrispettivi"]
    return {
        "corrispettivi_xml": _euro(xml["totale"]),
        "contanti_xml": _euro(xml["contanti"]),
        "xml_senza_contanti": xml["senza_contanti"],
        "documenti_commerciali": xml["numero_documenti"],
        "annulli": xml["annulli"],
        "pagato_non_riscosso": _euro(xml["non_riscosso"]),
        "pagato_non_riscosso_count": xml["non_riscosso_count"],
        "ammontare_annulli": _euro(xml["ammontare_annulli"]),
        "ammontare_annulli_count": xml["ammontare_annulli_count"],
        "corrispettivi_cassa": _euro(cassa["corrispettivi"]),
        "differenza_contanti": None if differenza is None else _euro(differenza),
        "versamenti": _euro(cassa["versamenti"]),
        "entrate_cassa": _euro(cassa["entrate"]),
        "uscite_cassa": _euro(cassa["uscite"]),
        "saldo_cassa": _euro(cassa["entrate"] - cassa["uscite"]),
        "movimenti_cassa": cassa["movimenti"],
        "righe_xml": xml["righe"],
    }


async def _leggi(db, data_da: str, data_a: str):
    query_cassa = filtro_saldo_prima_nota(COLLECTION_PRIMA_NOTA_CASSA)
    query_cassa["data"] = {"$gte": data_da, "$lte": data_a}
    proiezione_cassa = {"_id": 0, "id": 1, "data": 1, "tipo": 1, "importo": 1,
                        "categoria": 1, "source": 1, "descrizione": 1}
    cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(query_cassa, proiezione_cassa).to_list(None)
    query_xml = {
        "entity_status": {"$ne": "deleted"},
        "status": {"$nin": ["deleted", "archived"]},
        "data": {"$gte": data_da, "$lte": data_a},
    }
    proiezione_xml = {"_id": 0, "data": 1, "totale": 1, "pagato_contanti": 1,
                      "numero_documenti": 1, "annulli": 1, "pagato_non_riscosso": 1,
                      "totale_ammontare_annulli": 1}
    corrispettivi = await db["corrispettivi"].find(query_xml, proiezione_xml).to_list(None)
    return cassa, corrispettivi


async def riepilogo_controllo_mensile(anno: int, mese: Optional[int] = None) -> Dict[str, Any]:
    """Totali per mese dell'anno, o per giorno del mese se ``mese`` e' dato."""
    if not 2000 <= int(anno) <= 2100:
        raise HTTPException(400, "Anno non valido")
    if mese is not None and not 1 <= int(mese) <= 12:
        raise HTTPException(400, "Mese non valido")
    db = Database.get_db()
    if mese is None:
        data_da, data_a = f"{anno}-01-01", f"{anno}-12-31"
        periodi = [f"{anno}-{m:02d}" for m in range(1, 13)]
    else:
        ultimo = calendar.monthrange(int(anno), int(mese))[1]
        data_da, data_a = f"{anno}-{mese:02d}-01", f"{anno}-{mese:02d}-{ultimo:02d}"
        periodi = [f"{anno}-{mese:02d}-{g:02d}" for g in range(1, ultimo + 1)]
    cassa, corrispettivi = await _leggi(db, data_da, data_a)

    def del_periodo(righe, periodo):
        if mese is None:
            return [r for r in righe if str(r.get("data") or "").startswith(periodo)]
        return [r for r in righe if str(r.get("data") or "") == periodo]

    risposta: Dict[str, Any] = {
        "anno": int(anno),
        "mese": int(mese) if mese is not None else None,
        "periodi": [
            {"periodo": p, **riga_periodo(del_periodo(cassa, p), del_periodo(corrispettivi, p))}
            for p in periodi
        ],
        # Totale del periodo richiesto: sulle stesse righe, non sommando i mesi.
        "totale": riga_periodo(
            [r for r in cassa if any(str(r.get("data") or "").startswith(p) for p in periodi)],
            [r for r in corrispettivi if any(str(r.get("data") or "").startswith(p) for p in periodi)],
        ),
    }
    if mese is not None:
        risposta["versamenti_dettaglio"] = sorted(
            ({"id": m.get("id"), "data": m.get("data"), "descrizione": m.get("descrizione"),
              "categoria": m.get("categoria"), "importo": m.get("importo")}
             for m in cassa if e_versamento(m)),
            key=lambda m: str(m.get("data") or ""), reverse=True,
        )
    return risposta
