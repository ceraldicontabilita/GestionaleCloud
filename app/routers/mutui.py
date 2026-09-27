"""
Router FastAPI per i MUTUI
==========================

Endpoints:
- GET /api/mutui - Lista dei mutui (dai piani di ammortamento importati)
- GET /api/mutui/{mutuo_id} - Dettaglio mutuo
- GET /api/mutui/statistiche/dashboard - Statistiche generali
- POST /api/mutui/riconcilia - Stato del riscontro rate ↔ banca
- GET /api/mutui/{mutuo_id}/rate - Rate del mutuo

Audit 27/09/2026 (punto 11): il router leggeva la collezione ``mutui``, che
in produzione non esiste. Il piano vero lo scrive l'import documentale
(``services/mutui_document_import.py``, Documenti > Import) in
``mutui_piani_documentali``: un solo sistema, letto qui e dalla proiezione
bancaria che divide la rata in capitale e interessi. Le vecchie scritture a
mano su ``mutui`` (crea, modifica, elimina, riconcilia a mano) scrivevano
dove nessuno leggeva e sono state tolte.

Il riscontro di una rata con la banca non si fa piu' qui: la rata addebitata
entra in Prima Nota Banca dalla proiezione bancaria (``proiezione_bancaria``:
numero del mutuo e scadenza nella causale, mai l'importo). Questo router la
legge soltanto: una rata «Pagata» sul piano senza quella riga resta da
riscontrare, non si inventa il movimento.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging

from fastapi import APIRouter, HTTPException, Query

from app.database import Database

router = APIRouter(tags=["Mutui"])
logger = logging.getLogger(__name__)

COLL_PIANI = "mutui_piani_documentali"
COLL_PRIMA_NOTA_BANCA = "prima_nota_banca"

_PROIEZIONE_PIANO = {"_id": 0}
_PROIEZIONE_RATA_BANCA = {
    "_id": 0, "id": 1, "data": 1, "importo": 1, "numero_mutuo": 1, "rata_scadenza": 1,
    "tipo_classificazione_contabile": 1, "movimento_bancario_id": 1, "status": 1,
    "entity_status": 1,
}


def get_db():
    """Get database instance"""
    return Database.get_db()


def _cifre_mutuo(numero: Any) -> str:
    """Stessa identita' del mutuo della proiezione bancaria (delibera sul
    piano, «1788 4851906» in causale)."""
    from app.services.proiezione_bancaria import _cifre_mutuo as cifre

    return cifre(numero)


def _data_gma(valore: Any) -> str:
    from app.services.proiezione_bancaria import _data_gma as data_gma

    return data_gma(valore)


def _data(valore: Any) -> Optional[datetime]:
    testo = str(valore or "")[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(testo, formato)
        except ValueError:
            continue
    return None


async def _piani_correnti(db) -> List[Dict[str, Any]]:
    """Un piano per delibera: l'import tiene una riga per PDF (chiave
    delibera + SHA-256), quindi lo stesso mutuo puo' avere piu' versioni del
    piano. Vale la piu' recente."""
    piani = await db[COLL_PIANI].find({}, _PROIEZIONE_PIANO).to_list(None)
    per_delibera: Dict[str, Dict[str, Any]] = {}
    for piano in piani:
        delibera = str(piano.get("numero_delibera") or "").strip()
        if not delibera or not piano.get("rate"):
            continue
        attuale = per_delibera.get(delibera)
        if attuale is None or str(piano.get("updated_at") or "") > str(attuale.get("updated_at") or ""):
            per_delibera[delibera] = piano
    return [per_delibera[k] for k in sorted(per_delibera)]


async def _rate_in_banca(db) -> Dict[tuple, Dict[str, Any]]:
    """Rate addebitate in banca, per (cifre del mutuo, scadenza gg/mm/aaaa)."""
    righe = await db[COLL_PRIMA_NOTA_BANCA].find(
        {"tipo_classificazione_contabile": "rata_mutuo"}, _PROIEZIONE_RATA_BANCA,
    ).to_list(None)
    per_rata: Dict[tuple, Dict[str, Any]] = {}
    for riga in righe:
        if riga.get("status") in ("deleted", "archived") or riga.get("entity_status") == "deleted":
            continue
        chiave = (_cifre_mutuo(riga.get("numero_mutuo")), _data_gma(riga.get("rata_scadenza")))
        per_rata.setdefault(chiave, riga)
    return per_rata


def _mutuo_da_piano(piano: Dict[str, Any], in_banca: Dict[tuple, Dict[str, Any]]) -> Dict[str, Any]:
    """Il piano documentale nella forma che la pagina Mutui legge."""
    delibera = str(piano.get("numero_delibera"))
    cifre = _cifre_mutuo(delibera)
    rate = []
    for rata in sorted(piano.get("rate") or [], key=lambda r: int(r.get("numero_rata") or 0)):
        riga_banca = in_banca.get((cifre, _data_gma(rata.get("data_scadenza"))))
        rate.append({
            **rata,
            "riconciliata": bool(riga_banca),
            "movimento_bancario_id": (riga_banca or {}).get("movimento_bancario_id"),
            "prima_nota_banca_id": (riga_banca or {}).get("id"),
            "data_pagamento_effettivo": (riga_banca or {}).get("data"),
        })

    def _somma(campo: str, pagate: bool) -> float:
        return round(sum(
            float(r.get(campo) or 0) for r in rate if (r.get("stato") == "Pagata") == pagate
        ), 2)

    rate_pagate = sum(1 for r in rate if r.get("stato") == "Pagata")
    rate_da_pagare = sum(1 for r in rate if r.get("stato") == "Da pagare")
    rate_riconciliate = sum(1 for r in rate if r.get("stato") == "Pagata" and r["riconciliata"])
    prossima = next((r for r in rate if r.get("stato") == "Da pagare"), None)
    return {
        "mutuo_id": f"mutuo_{delibera}",
        "nome": piano.get("nome") or f"Mutuo {piano.get('tipo_finanziamento') or delibera}",
        "tipo_finanziamento": piano.get("tipo_finanziamento"),
        "numero_delibera": delibera,
        "banca": piano.get("banca"),
        "intestatario": piano.get("intestatario"),
        "importo_accordato": round(float(piano.get("importo_accordato") or 0), 2),
        "rate": rate,
        "totale_rate": len(rate),
        "rate_pagate": rate_pagate,
        "rate_da_pagare": rate_da_pagare,
        "rate_residue_dichiarate": piano.get("rate_residue_dichiarate"),
        "totale_pagato_capitale": _somma("quota_capitale", True),
        "totale_pagato_interessi": _somma("quota_interessi", True),
        "totale_pagato": _somma("importo_totale", True),
        "debito_residuo_capitale": _somma("quota_capitale", False),
        "debito_residuo_interessi": _somma("quota_interessi", False),
        "debito_residuo_totale": _somma("importo_totale", False),
        "prossima_data_scadenza": (prossima or {}).get("data_scadenza"),
        "prossimo_importo": (prossima or {}).get("importo_totale"),
        "rate_riconciliate": rate_riconciliate,
        "rate_non_riconciliate": rate_pagate - rate_riconciliate,
        "percentuale_riconciliazione": (
            round(rate_riconciliate / rate_pagate * 100, 2) if rate_pagate else 0.0
        ),
        "file_piano_ammortamento": piano.get("filename"),
        "sha256": piano.get("sha256"),
        "fonte": COLL_PIANI,
        "updated_at": piano.get("updated_at"),
    }


async def _mutui(db) -> List[Dict[str, Any]]:
    piani = await _piani_correnti(db)
    if not piani:
        return []
    in_banca = await _rate_in_banca(db)
    return [_mutuo_da_piano(piano, in_banca) for piano in piani]


async def _mutuo(db, mutuo_id: str) -> Dict[str, Any]:
    for mutuo in await _mutui(db):
        if mutuo["mutuo_id"] == mutuo_id:
            return mutuo
    raise HTTPException(status_code=404, detail=f"Mutuo {mutuo_id} non trovato")


# ============================================================================
# ENDPOINTS LISTA E DETTAGLIO
# ============================================================================

@router.get("/", summary="Lista tutti i mutui")
async def get_mutui(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Lista dei mutui con statistiche aggregate, dai piani importati."""
    mutui = await _mutui(get_db())
    pagina = mutui[skip:skip + limit]
    stats = {
        "totale_mutui": len(mutui),
        "importo_totale_accordato": round(sum(m["importo_accordato"] for m in mutui), 2),
        "debito_residuo_totale": round(sum(m["debito_residuo_totale"] for m in mutui), 2),
        "totale_pagato": round(sum(m["totale_pagato"] for m in mutui), 2),
        "rate_totali": sum(m["totale_rate"] for m in mutui),
        "rate_pagate": sum(m["rate_pagate"] for m in mutui),
        "rate_da_pagare": sum(m["rate_da_pagare"] for m in mutui),
    }
    return {
        "success": True,
        "data": pagina,
        "pagination": {"skip": skip, "limit": limit, "total": len(mutui)},
        "statistiche": stats,
    }


@router.get("", summary="Lista tutti i mutui", include_in_schema=False)
async def get_mutui_noslash(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Alias senza trailing slash per /api/mutui/"""
    return await get_mutui(skip=skip, limit=limit)


@router.get("/statistiche/dashboard", summary="Statistiche per dashboard")
async def get_statistiche_mutui():
    """Statistiche aggregate per la dashboard, dai piani importati."""
    mutui = await _mutui(get_db())
    accordato = round(sum(m["importo_accordato"] for m in mutui), 2)
    capitale_pagato = round(sum(m["totale_pagato_capitale"] for m in mutui), 2)
    rate_pagate = sum(m["rate_pagate"] for m in mutui)
    rate_riconciliate = sum(m["rate_riconciliate"] for m in mutui)

    oggi = datetime.now()
    prossime = []
    for mutuo in mutui:
        for rata in mutuo["rate"]:
            if rata.get("stato") != "Da pagare":
                continue
            scadenza = _data(rata.get("data_scadenza"))
            if scadenza is None:
                logger.warning("Rata %s del mutuo %s senza scadenza leggibile: %r",
                               rata.get("numero_rata"), mutuo["mutuo_id"], rata.get("data_scadenza"))
                continue
            if oggi <= scadenza <= oggi + timedelta(days=30):
                prossime.append((scadenza, {
                    "mutuo_id": mutuo["mutuo_id"],
                    "nome": mutuo.get("nome"),
                    "numero_rata": rata.get("numero_rata"),
                    "data_scadenza": rata.get("data_scadenza"),
                    "importo_totale": rata.get("importo_totale"),
                }))
    prossime.sort(key=lambda voce: voce[0])

    return {
        "success": True,
        "data": {
            "numero_mutui": len(mutui),
            "importo_totale_accordato": accordato,
            "debito_residuo_totale": round(sum(m["debito_residuo_totale"] for m in mutui), 2),
            "totale_pagato_capitale": capitale_pagato,
            "totale_pagato_interessi": round(sum(m["totale_pagato_interessi"] for m in mutui), 2),
            "totale_pagato": round(sum(m["totale_pagato"] for m in mutui), 2),
            "rate_totali": sum(m["totale_rate"] for m in mutui),
            "rate_pagate": rate_pagate,
            "rate_da_pagare": sum(m["rate_da_pagare"] for m in mutui),
            "rate_riconciliate": rate_riconciliate,
            "percentuale_completamento": (
                round(capitale_pagato / accordato * 100, 2) if accordato > 0 else 0
            ),
            "percentuale_riconciliazione": (
                round(rate_riconciliate / rate_pagate * 100, 2) if rate_pagate else 0
            ),
            "prossime_scadenze": [voce for _, voce in prossime[:10]],
        },
    }


@router.get("/{mutuo_id}", summary="Dettaglio mutuo")
async def get_mutuo_by_id(mutuo_id: str):
    """Dettaglio completo di un mutuo, rate comprese."""
    return {"success": True, "data": await _mutuo(get_db(), mutuo_id)}


@router.get("/{mutuo_id}/rate", summary="Rate del mutuo")
async def get_rate_mutuo(mutuo_id: str):
    """Tutte le rate di un mutuo."""
    mutuo = await _mutuo(get_db(), mutuo_id)
    return {
        "success": True,
        "data": {"mutuo_id": mutuo["mutuo_id"], "nome": mutuo.get("nome"), "rate": mutuo["rate"]},
    }


# ============================================================================
# RISCONTRO CON LA BANCA
# ============================================================================

@router.post("/riconcilia", summary="Riscontro rate mutui con la banca")
async def riconcilia_mutui_con_estratto_conto():
    """Stato del riscontro delle rate pagate con gli addebiti in banca.

    Non scrive nulla: l'addebito della rata entra in Prima Nota Banca dalla
    proiezione bancaria, per numero del mutuo e scadenza in causale. Qui si
    legge quali rate «Pagata» del piano hanno quella riga e quali no.
    """
    mutui = await _mutui(get_db())
    esito: Dict[str, Any] = {
        "totale_rate_processate": 0,
        "riconciliazioni_automatiche": 0,
        "riconciliazioni_manuali_richieste": 0,
        "dettagli": [],
    }
    for mutuo in mutui:
        for rata in mutuo["rate"]:
            if rata.get("stato") != "Pagata":
                continue
            esito["totale_rate_processate"] += 1
            voce = {
                "mutuo_id": mutuo["mutuo_id"],
                "mutuo_nome": mutuo.get("nome"),
                "rata_numero": rata.get("numero_rata"),
                "data_scadenza": rata.get("data_scadenza"),
                "importo": rata.get("importo_totale"),
            }
            if rata["riconciliata"]:
                esito["riconciliazioni_automatiche"] += 1
                voce.update({
                    "movimento_id": rata.get("movimento_bancario_id"),
                    "data_movimento": rata.get("data_pagamento_effettivo"),
                    "status": "riscontrata_in_banca",
                })
            else:
                esito["riconciliazioni_manuali_richieste"] += 1
                voce["status"] = "addebito_bancario_non_trovato"
            esito["dettagli"].append(voce)
    return {"success": True, "message": "Riscontro completato", "data": esito}
