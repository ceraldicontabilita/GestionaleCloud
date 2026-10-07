"""Acconto TFR: il motore contabile dell'acconto, usato dal router TFR HR.

Un acconto TFR scala il TFR accantonato del dipendente (``tfr_accantonato``,
nell'archivio HR dove vive la sua anagrafica) e scrive nel libro giornale
**del gestionale** una scrittura in partita doppia sui conti CEE ufficiali:
DARE 29.01.01 Fondo TFR, AVERE 39.07.05 Personale c/liquidazione.
Una correzione o l'eliminazione dell'acconto **storna** (``acconto_tfr_rettifica``,
gambe invertite se diminuisce), mai cancella la scrittura originale.

Il router (``app/hr/routers/tfr.py``, l'unico che scrive acconti) chiama
queste funzioni: non tiene conti, descrizioni o storni propri. I due archivi
restano parametri (``anagrafica``, ``giornale``) perche' sono davvero due.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from app.services.registrazione_contabile import (
    _C_FONDO_TFR,
    _C_PERSONALE_LIQUIDAZIONE,
    registra_scrittura_semplice,
    riga,
)

TIPO_SCRITTURA_ACCONTO = "acconto_tfr"
TIPO_SCRITTURA_RETTIFICA = "acconto_tfr_rettifica"

#: Conti dell'acconto TFR (piano CEE ufficiale): un posto solo.
CONTO_FONDO_TFR = _C_FONDO_TFR
CONTO_PERSONALE_LIQUIDAZIONE = _C_PERSONALE_LIQUIDAZIONE

__all__ = [
    "CONTO_FONDO_TFR", "CONTO_PERSONALE_LIQUIDAZIONE",
    "TIPO_SCRITTURA_ACCONTO", "TIPO_SCRITTURA_RETTIFICA",
    "registra_acconto_tfr", "correggi_importo_acconto_tfr", "ritira_acconto_tfr",
    "allinea_giornale_acconto_tfr",
]


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _scala_tfr(anagrafica, dipendente_id: str, delta: float) -> Optional[float]:
    """Sposta ``tfr_accantonato`` del dipendente di ``delta`` (negativo = acconto erogato).

    Un acconto non porta il fondo sotto zero; un ripristino lo rialza di quanto
    era stato scalato. Restituisce il nuovo valore, ``None`` se il dipendente manca."""
    dipendente = await anagrafica["dipendenti"].find_one({"id": dipendente_id})
    if not dipendente:
        return None
    attuale = float(dipendente.get("tfr_accantonato", 0) or 0)
    nuovo = attuale + float(delta)
    if delta < 0:
        nuovo = max(0.0, nuovo)
    nuovo = round(nuovo, 2)
    await anagrafica["dipendenti"].update_one({"id": dipendente_id}, {"$set": {"tfr_accantonato": nuovo}})
    return nuovo


async def registra_acconto_tfr(anagrafica, giornale, acconto: Dict[str, Any],
                               dipendente: Dict[str, Any]) -> Dict[str, Any]:
    """Acconto TFR appena inserito in ``acconti_dipendenti``: scala il fondo e scrive il giornale.

    Idempotente sull'``id`` dell'acconto: un secondo passaggio (retry sullo stesso
    POST) non crea una seconda scrittura."""
    importo = round(float(acconto.get("importo") or 0), 2)
    nome = dipendente.get("nome_completo", "")
    nuovo_tfr = await _scala_tfr(anagrafica, acconto["dipendente_id"], -importo)
    scrittura = await registra_scrittura_semplice(
        giornale,
        movimento={
            "id": str(uuid4()),
            "data": acconto.get("data"),
            "descrizione": f"Acconto TFR - {nome}",
            "tipo": TIPO_SCRITTURA_ACCONTO,
            "importo": importo,
            "dipendente_id": acconto["dipendente_id"],
            "note": acconto.get("note") or "",
            "acconto_id": acconto["id"],
            "created_at": acconto.get("created_at") or _ora(),
        },
        righe=[
            riga(CONTO_FONDO_TFR, dare=importo, descrizione="Acconto TFR"),
            riga(CONTO_PERSONALE_LIQUIDAZIONE, avere=importo,
                 descrizione=f"Debito v/dipendente per acconto TFR - {nome}"),
        ],
        chiave_naturale={"tipo": TIPO_SCRITTURA_ACCONTO, "acconto_id": acconto["id"]},
    )
    return {"tfr_accantonato": nuovo_tfr, "scrittura_id": scrittura.get("id"),
            "gia_presente": bool(scrittura.get("gia_presente"))}


async def allinea_giornale_acconto_tfr(giornale, acconto: Dict[str, Any], importo_nuovo: float) -> Optional[Dict[str, Any]]:
    """Porta il giornale a dire ``importo_nuovo`` per un acconto TFR gia' registrato.

    Una scrittura sbagliata si **storna**, non si cancella (CLAUDE.md, regola 8):
    l'acconto eliminato (``importo_nuovo = 0``) o corretto di importo lascia la
    scrittura originale e ne aggiunge una di rettifica per la differenza, con le
    gambe invertite se diminuisce. Se l'acconto non ha mai avuto la sua scrittura
    non se ne inventa una. Restituisce la rettifica scritta, ``None`` se non serviva."""
    scritture = await giornale["movimenti_contabili"].find(
        {"acconto_id": acconto["id"], "tipo": {"$in": [TIPO_SCRITTURA_ACCONTO, TIPO_SCRITTURA_RETTIFICA]}},
        {"_id": 0},
    ).to_list(100)
    if not any(m.get("tipo") == TIPO_SCRITTURA_ACCONTO for m in scritture):
        return None
    registrato = round(sum(float(m.get("importo_con_segno", m.get("importo")) or 0) for m in scritture), 2)
    delta = round(float(importo_nuovo) - registrato, 2)
    if delta == 0:
        return None
    imp = abs(delta)
    nome = acconto.get("dipendente_nome", "")
    gambe = [(CONTO_FONDO_TFR, "dare"), (CONTO_PERSONALE_LIQUIDAZIONE, "avere")]
    if delta < 0:
        gambe = [(CONTO_PERSONALE_LIQUIDAZIONE, "dare"), (CONTO_FONDO_TFR, "avere")]
    ora = _ora()
    return await registra_scrittura_semplice(
        giornale,
        movimento={
            "id": str(uuid4()), "data": ora[:10],
            "descrizione": f"Rettifica acconto TFR - {nome}",
            "tipo": TIPO_SCRITTURA_RETTIFICA, "importo": imp, "importo_con_segno": delta,
            "dipendente_id": acconto.get("dipendente_id"), "acconto_id": acconto["id"],
            "created_at": ora,
        },
        righe=[riga(conto, descrizione="Rettifica acconto TFR", **{lato: imp}) for conto, lato in gambe],
        chiave_naturale={"tipo": TIPO_SCRITTURA_RETTIFICA, "acconto_id": acconto["id"],
                         "progressivo": len(scritture)},
    )


async def correggi_importo_acconto_tfr(anagrafica, giornale, acconto: Dict[str, Any],
                                       nuovo_importo: float) -> Dict[str, Any]:
    """L'acconto cambia importo: il giornale si rettifica per la differenza e il
    fondo del dipendente torna indietro del vecchio importo e scende del nuovo."""
    vecchio = float(acconto.get("importo") or 0)
    nuovo = round(float(nuovo_importo), 2)
    rettifica = await allinea_giornale_acconto_tfr(giornale, acconto, nuovo)
    tfr = await _scala_tfr(anagrafica, acconto["dipendente_id"], vecchio - nuovo)
    return {"tfr_accantonato": tfr, "rettifica_id": (rettifica or {}).get("id")}


async def ritira_acconto_tfr(anagrafica, giornale, acconto: Dict[str, Any]) -> Dict[str, Any]:
    """L'acconto viene eliminato: storno pieno nel giornale e fondo ripristinato."""
    rettifica = await allinea_giornale_acconto_tfr(giornale, acconto, 0.0)
    tfr = await _scala_tfr(anagrafica, acconto["dipendente_id"], float(acconto.get("importo") or 0))
    return {"tfr_accantonato": tfr, "rettifica_id": (rettifica or {}).get("id")}
