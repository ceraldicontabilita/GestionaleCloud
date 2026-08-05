"""
API Gestione IVA (SPECIFICA_IVA.md).

Fase 1: attribuzione del periodo IVA per competenza alle fatture di acquisto e
vista "IVA disponibile non ancora utilizzata".
Fase 3: liquidazioni IVA mensili PERSISTITE con stati e versioni, calcolo
anti-doppia-detrazione (§10-13), conferma che marca l'IVA come utilizzata,
riapertura e rettifica. Montato sotto /api/iva.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import logging
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import Database
from app.engines import iva_fatture
from app.engines import liquidazione_iva_engine as liq
from app.engines import riepilogo_iva_engine as riep
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

COLL = "invoices"
COLL_LIQ = "liquidazioni_iva"
COLL_MOV = "movimenti_iva_fattura"
# Note di credito: non sono acquisti detraibili in positivo
from app.constants.tipi_documento import TIPI_NOTA_CREDITO


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _iva_detraibile_fattura(doc: Dict[str, Any]) -> float:
    """Ritorna solo l'IVA la cui detraibilita' e' stata valutata.

    Il fallback sull'IVA esposta trasformava le fatture non classificate in
    credito pienamente detraibile. Un valore mancante resta quindi zero finche'
    il learning o una correzione fiscale non lo valorizzano esplicitamente.
    """
    return _float(doc.get("iva_detraibile"))


def _utente_autenticato(current_user: Any, legacy_utente: Optional[str] = None) -> str:
    """Usa l'identita JWT; il parametro legacy non puo sovrascriverla."""
    if isinstance(current_user, dict):
        return str(
            current_user.get("user_id")
            or current_user.get("email")
            or current_user.get("name")
            or "utente_autenticato"
        )
    return str(legacy_utente or "sistema")


def _iva_corrispettivo(doc: Dict[str, Any]) -> float:
    """IVA vendite dichiarata dal RT, con fallback per i record storici."""
    iva = _float(doc.get("totale_iva"))
    if abs(iva) >= 0.005:
        return iva
    riepilogo = doc.get("riepilogo_iva") or []
    iva_righe = sum(_float(r.get("imposta")) for r in riepilogo if isinstance(r, dict))
    if abs(iva_righe) >= 0.005:
        return iva_righe
    totale = _float(doc.get("totale") or doc.get("totale_complessivo"))
    return totale - (totale / 1.10) if totale > 0 else 0.0


async def _iva_vendite_corrispettivi(db, periodo: str) -> float:
    """Somma l'IVA vendite mensile dai corrispettivi attivi, senza doppioni."""
    docs = await db["corrispettivi"].find({
        "data": {"$regex": f"^{periodo}"},
        "entity_status": {"$ne": "deleted"},
        "status": {"$nin": ["deleted", "archived"]},
    }, {
        "_id": 0, "corrispettivo_key": 1, "data": 1,
        "matricola_rt": 1, "id_dispositivo": 1, "totale": 1,
        "totale_complessivo": 1, "totale_iva": 1, "riepilogo_iva": 1,
        "created_at": 1,
    }).to_list(10000)
    visti = set()
    totale_iva = 0.0
    for doc in sorted(docs, key=lambda d: d.get("created_at") or ""):
        chiave = (
            doc.get("corrispettivo_key")
            or f"{doc.get('data') or ''}|{doc.get('matricola_rt') or doc.get('id_dispositivo') or ''}|"
               f"{round(_float(doc.get('totale') or doc.get('totale_complessivo')), 2)}"
        )
        if chiave in visti:
            continue
        visti.add(chiave)
        totale_iva += _iva_corrispettivo(doc)
    return round(totale_iva, 2)


def _periodo_precedente(periodo: str) -> str:
    """'YYYY-MM' → mese precedente 'YYYY-MM'."""
    anno, mese = int(periodo[:4]), int(periodo[5:7])
    if mese == 1:
        return f"{anno - 1}-12"
    return f"{anno}-{mese - 1:02d}"


COLL_RICALC_LOG = "iva_ricalcolo_log"

# Campi che servono al motore IVA: si proietta solo questo, così si leggono
# DAVVERO tutte le fatture senza caricare i PDF/XML in base64 (che le
# renderebbero pesantissime) e senza mai troncare l'elenco.
_PROJ_RICALCOLO = {
    "invoice_date": 1, "data_documento": 1, "linee": 1,
    "data_ricezione_sdi": 1, "data_ricezione": 1, "created_at": 1,
    "data_registrazione": 1, "iva": 1, "total_iva": 1, "iva_totale": 1,
    "iva_utilizzata": 1, "periodo_iva_utilizzato": 1, "stato_detrazione_iva": 1,
    "periodo_iva_attribuito": 1, "regola_iva_applicata": 1, "tipo_documento": 1,
    "iva_detraibile": 1, "stato_classificazione": 1, "classificato_da": 1,
}


@router.post("/ricalcola-attribuzione")
async def ricalcola_attribuzione(
    anno: Optional[int] = Query(None, description="Limita al singolo anno (opzionale). Vuoto = TUTTE le fatture"),
    utente: Optional[str] = Query(None, deprecated=True),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Calcola il PREGRESSO: rilegge DAVVERO tutte le fatture di acquisto (o di
    un anno) e ricalcola i campi IVA (periodo attribuito per competenza, regola,
    stato). Non tocca l'IVA già utilizzata in una liquidazione confermata.

    Ritorna un report verificabile (lette, modificate, invariate, attribuite,
    da verificare, già utilizzate + ripartizione per regola e per anno) e lo
    SALVA in `iva_ricalcolo_log`, così l'esito resta consultabile e non serve
    ripetere il calcolo per essere sicuri di cosa è stato letto."""
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if anno:
        query["$or"] = [
            {"invoice_date": {"$regex": f"^{anno}"}},
            {"data_documento": {"$regex": f"^{anno}"}},
        ]

    lette = modificate = invariate = 0
    con_periodo = da_verificare = gia_utilizzate = 0
    per_regola: Dict[str, int] = {}
    per_anno: Dict[str, int] = {}

    async for inv in db[COLL].find(query, _PROJ_RICALCOLO):
        lette += 1
        campi = iva_fatture.campi_iva_da_fattura(inv)

        # modificata solo se un campo IVA cambia davvero rispetto all'esistente
        cambia = any(inv.get(k) != v for k, v in campi.items())
        if cambia:
            await db[COLL].update_one({"_id": inv["_id"]}, {"$set": campi})
            modificate += 1
        else:
            invariate += 1

        periodo = campi.get("periodo_iva_attribuito")
        if campi.get("iva_utilizzata"):
            gia_utilizzate += 1
        if periodo:
            con_periodo += 1
            per_anno[periodo[:4]] = per_anno.get(periodo[:4], 0) + 1
        else:
            da_verificare += 1
        regola = campi.get("regola_iva_applicata") or "—"
        per_regola[regola] = per_regola.get(regola, 0) + 1

    report = {
        "id": str(uuid.uuid4()),
        "eseguito_il": datetime.utcnow().isoformat(),
        "eseguito_da": _utente_autenticato(current_user, utente),
        "filtro_anno": anno,
        "lette": lette,
        "modificate": modificate,
        "invariate": invariate,
        "con_periodo": con_periodo,
        "da_verificare": da_verificare,
        "gia_utilizzate": gia_utilizzate,
        "per_regola": per_regola,
        "per_anno": per_anno,
    }
    # Persistenza dell'esito (best-effort: non deve far fallire il calcolo).
    try:
        await db[COLL_RICALC_LOG].insert_one(dict(report))
    except Exception:
        pass

    return {"success": True, "esaminate": lette, "aggiornate": modificate, "report": report}


@router.get("/ricalcola-attribuzione/ultimo")
async def ultimo_ricalcolo() -> Dict[str, Any]:
    """Ultimo esito del 'Calcola pregresso' (persistito): resta visibile nella
    pagina così sai sempre quante fatture sono state lette e attribuite."""
    db = Database.get_db()
    doc = await db[COLL_RICALC_LOG].find_one({}, {"_id": 0}, sort=[("eseguito_il", -1)])
    return {"ultimo": doc}


@router.get("/fatture")
async def fatture_iva(
    periodo: Optional[str] = Query(None, description="Periodo IVA attribuito, 'YYYY-MM'"),
    anno: Optional[int] = Query(None),
    limit: int = Query(500, le=5000),
) -> Dict[str, Any]:
    """Elenco fatture con i dati IVA (periodo attribuito, regola, stato)."""
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if periodo:
        query["periodo_iva_attribuito"] = periodo
    elif anno:
        query["periodo_iva_attribuito"] = {"$regex": f"^{anno}"}

    proj = {
        "_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1,
        "data_documento": 1, "data_operazione": 1, "data_ricezione": 1,
        "data_registrazione": 1, "periodo_iva_attribuito": 1,
        "periodo_iva_utilizzato": 1, "regola_iva_applicata": 1,
        "iva": 1, "iva_detraibile": 1, "iva_utilizzata": 1,
        "stato_detrazione_iva": 1, "tipo_documento": 1,
    }
    docs = await db[COLL].find(query, proj).sort("data_documento", -1).to_list(limit)
    return {"fatture": docs, "totale": len(docs)}


@router.get("/fatture/non-utilizzate")
async def fatture_non_utilizzate(
    anno: Optional[int] = Query(None),
    limit: int = Query(1000, le=5000),
) -> Dict[str, Any]:
    """IVA disponibile NON ancora utilizzata (SPECIFICA_IVA.md §14): fatture
    con IVA detraibile > 0 non ancora inserita in alcuna liquidazione."""
    db = Database.get_db()
    query: Dict[str, Any] = {
        "iva_utilizzata": {"$ne": True},
        "tipo_documento": {"$nin": list(TIPI_NOTA_CREDITO)},
    }
    if anno:
        query["periodo_iva_attribuito"] = {"$regex": f"^{anno}"}

    proj = {
        "_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1,
        "data_documento": 1, "data_ricezione": 1, "periodo_iva_attribuito": 1,
        "regola_iva_applicata": 1, "iva": 1, "iva_detraibile": 1,
        "stato_detrazione_iva": 1,
    }
    docs = await db[COLL].find(query, proj).sort("periodo_iva_attribuito", 1).to_list(limit)
    docs = [
        d for d in docs
        if d.get("stato_detrazione_iva") in liq.STATI_DETRAZIONE_AMMESSI
        and _iva_detraibile_fattura(d) > 0
    ]
    totale_iva = round(sum(_iva_detraibile_fattura(d) for d in docs), 2)
    return {"fatture": docs, "totale": len(docs), "totale_iva_disponibile": totale_iva}


# ─── Liquidazioni IVA mensili (Fase 3) ──────────────────────────────────────

async def _fatture_del_periodo(db, periodo: str) -> List[Dict[str, Any]]:
    """Tutte le fatture attribuite al periodo (per selezione liquidazione)."""
    proj = {
        "_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1,
        "periodo_iva_attribuito": 1, "periodo_iva_utilizzato": 1,
        "iva": 1, "iva_detraibile": 1, "iva_utilizzata": 1,
        "stato_detrazione_iva": 1, "tipo_documento": 1,
        "annullata": 1, "duplicata": 1,
    }
    return await db[COLL].find({"periodo_iva_attribuito": periodo}, proj).to_list(5000)


async def _credito_precedente(db, periodo: str) -> float:
    """Credito IVA riportato dalla liquidazione confermata del mese precedente."""
    prev = _periodo_precedente(periodo)
    doc = await db[COLL_LIQ].find_one(
        {"periodo": prev, "stato": {"$in": [liq.CONFERMATA, liq.TRASMESSA]}},
        sort=[("versione", -1)],
    )
    if not doc:
        return 0.0
    return round(float(doc.get("credito_periodo") or 0), 2)


async def _componi_liquidazione(
    db, periodo: str, iva_vendite: float, versione: int, liq_id: str,
) -> Dict[str, Any]:
    """Costruisce (senza persistere) il documento liquidazione per il periodo."""
    fatture = await _fatture_del_periodo(db, periodo)
    incluse, escluse = liq.seleziona_fatture_per_liquidazione(fatture, periodo)
    credito_prec = await _credito_precedente(db, periodo)
    totali = liq.calcola_totali(incluse, iva_vendite, credito_prec)
    ora = datetime.utcnow().isoformat()
    return {
        "id": liq_id,
        "periodo": periodo,
        "versione": versione,
        "stato": liq.CALCOLATA,
        "iva_vendite": totali["iva_vendite"],
        "iva_acquisti": totali["iva_acquisti"],
        "credito_precedente": totali["credito_precedente"],
        "saldo": totali["saldo"],
        "debito_periodo": totali["debito_periodo"],
        "credito_periodo": totali["credito_periodo"],
        "fatture_incluse": [
            {
                "id": f.get("id"),
                "invoice_number": f.get("invoice_number"),
                "supplier_name": f.get("supplier_name"),
                "iva": round(_iva_detraibile_fattura(f), 2),
            }
            for f in incluse
        ],
        "fatture_escluse": escluse,
        "data_calcolo": ora,
        "data_conferma": None,
        "motivo_rettifica": None,
        "updated_at": ora,
    }


@router.post("/liquidazioni/calcola")
async def calcola_liquidazione(
    periodo: str = Query(..., description="Periodo mensile 'YYYY-MM'"),
    iva_vendite: Optional[float] = Query(
        None,
        description="Override eccezionale; se assente viene calcolata dai corrispettivi XML",
    ),
    motivo_override: Optional[str] = Query(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Calcola (o ricalcola) la liquidazione del periodo come BOZZA/CALCOLATA.

    NON marca l'IVA come utilizzata: quello avviene solo alla conferma. Se per
    il periodo esiste già una liquidazione CONFERMATA o TRASMESSA, il ricalcolo
    è bloccato: va prima riaperta (§12, una confermata non si sovrascrive)."""
    db = Database.get_db()

    try:
        datetime.strptime(periodo, "%Y-%m")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Periodo non valido: usare YYYY-MM") from exc
    if iva_vendite is not None and isinstance(current_user, dict) and not str(motivo_override or "").strip():
        raise HTTPException(status_code=422, detail="Motivazione obbligatoria per l'override IVA vendite")

    confermata = await db[COLL_LIQ].find_one(
        {"periodo": periodo, "stato": {"$in": [liq.CONFERMATA, liq.TRASMESSA]}}
    )
    if confermata:
        raise HTTPException(
            status_code=409,
            detail=f"Esiste già una liquidazione {confermata['stato']} per {periodo}. "
                   "Riaprila prima di ricalcolare.",
        )

    # Riusa la bozza di lavoro se già presente (nuova versione), altrimenti nuova.
    esistente = await db[COLL_LIQ].find_one(
        {"periodo": periodo, "stato": {"$nin": [liq.CONFERMATA, liq.TRASMESSA, liq.RETTIFICATA]}},
        sort=[("versione", -1)],
    )
    if esistente:
        liq_id = esistente["id"]
        versione = int(esistente.get("versione") or 1) + 1
    else:
        liq_id = str(uuid.uuid4())
        # Nuova versione = max esistente + 1 (tiene conto di storiche rettificate)
        ultima = await db[COLL_LIQ].find_one({"periodo": periodo}, sort=[("versione", -1)])
        versione = int(ultima.get("versione") or 0) + 1 if ultima else 1

    iva_vendite_calcolata = (
        await _iva_vendite_corrispettivi(db, periodo)
        if iva_vendite is None
        else round(float(iva_vendite), 2)
    )
    doc = await _componi_liquidazione(db, periodo, iva_vendite_calcolata, versione, liq_id)
    doc["iva_vendite_fonte"] = "corrispettivi_xml" if iva_vendite is None else "override_manuale"
    doc["calcolata_da"] = _utente_autenticato(current_user)
    doc["motivo_override_iva_vendite"] = str(motivo_override or "").strip() or None
    if esistente:
        doc["created_at"] = esistente.get("created_at") or doc["data_calcolo"]
    else:
        doc["created_at"] = doc["data_calcolo"]
    await db[COLL_LIQ].replace_one({"id": liq_id}, doc, upsert=True)
    doc.pop("_id", None)
    return {"success": True, "liquidazione": doc}


@router.post("/liquidazioni/{liq_id}/conferma")
async def conferma_liquidazione(
    liq_id: str,
    utente: Optional[str] = Query(None, deprecated=True),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Conferma la liquidazione: marca l'IVA delle fatture incluse come
    utilizzata (§10) impedendo la doppia detrazione (§11). Idempotente per
    fattura: se una fattura risulta già utilizzata altrove non viene ritoccata."""
    db = Database.get_db()
    doc = await db[COLL_LIQ].find_one({"id": liq_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Liquidazione non trovata")
    if doc.get("stato") in (liq.CONFERMATA, liq.TRASMESSA):
        raise HTTPException(status_code=409, detail="Liquidazione già confermata")

    periodo = doc["periodo"]
    actor = _utente_autenticato(current_user, utente)
    ora = datetime.utcnow().isoformat()
    fatture_incluse = [f for f in doc.get("fatture_incluse", []) if f.get("id")]
    ids = [f["id"] for f in fatture_incluse]

    correnti = await db[COLL].find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "iva_utilizzata": 1, "liquidazione_id": 1},
    ).to_list(max(len(ids), 1))
    per_id = {f.get("id"): f for f in correnti}
    mancanti = [fid for fid in ids if fid not in per_id]
    conflitti = [
        fid for fid in ids
        if per_id.get(fid, {}).get("iva_utilizzata") is True
        and per_id.get(fid, {}).get("liquidazione_id") != liq_id
    ]
    if mancanti or conflitti:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Liquidazione non confermata: il contenuto e cambiato dopo il calcolo",
                "fatture_mancanti": mancanti,
                "fatture_gia_utilizzate": conflitti,
            },
        )

    marcate = 0
    marcate_ids: List[str] = []
    operazione_id = str(uuid.uuid4())

    async def _annulla_conferma_parziale() -> None:
        """Compensa le scritture gia eseguite se la conferma non si completa."""
        if marcate_ids:
            await db[COLL].update_many(
                {"id": {"$in": marcate_ids}, "liquidazione_id": liq_id},
                {"$set": {
                    "iva_utilizzata": False,
                    "periodo_iva_utilizzato": None,
                    "liquidazione_id": None,
                    "importo_iva_utilizzato": 0,
                    "data_utilizzo_iva": None,
                    "stato_detrazione_iva": "DA_INSERIRE",
                    "disponibile_per_nuovo_calcolo": True,
                }},
            )
        await db[COLL_MOV].delete_many({"operazione_id": operazione_id})

    for f in doc.get("fatture_incluse", []):
        fid = f.get("id")
        if not fid:
            continue
        # Anti-doppia-detrazione: marca solo se NON già utilizzata.
        res = await db[COLL].update_one(
            {"id": fid, "iva_utilizzata": {"$ne": True}},
            {"$set": {
                "iva_utilizzata": True,
                "periodo_iva_utilizzato": periodo,
                "liquidazione_id": liq_id,
                "importo_iva_utilizzato": f.get("iva"),
                "data_utilizzo_iva": ora,
                "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE",
                "disponibile_per_nuovo_calcolo": False,
            }},
        )
        if res.modified_count:
            marcate += 1
            marcate_ids.append(fid)
            try:
                await db[COLL_MOV].insert_one({
                    "id": str(uuid.uuid4()),
                    "fattura_id": fid,
                    "tipo_movimento": liq.MOV_UTILIZZO,
                    "periodo": periodo,
                    "importo_iva": f.get("iva"),
                    "liquidazione_id": liq_id,
                    "motivazione": f"Conferma liquidazione {periodo}",
                    "created_at": ora,
                    "created_by": actor,
                    "operazione_id": operazione_id,
                })
            except Exception as exc:
                await _annulla_conferma_parziale()
                logger.exception("Conferma IVA annullata: movimento audit non salvato")
                raise HTTPException(
                    status_code=500,
                    detail="Liquidazione non confermata: scrittura audit non riuscita",
                ) from exc
            # STORIA: registra in quale dichiarazione/liquidazione IVA è entrata.
            try:
                _fk = await db[COLL].find_one({"id": fid}, {"_id": 0, "invoice_key": 1})
                _key = (_fk or {}).get("invoice_key")
                if _key:
                    from app.services import storia_fatture as _storia
                    await _storia.registra(
                        db, _key, "iva_in_liquidazione",
                        f"IVA inserita nella liquidazione {periodo} (€{f.get('iva')})",
                        patch={"iva_utilizzata": True, "periodo_iva_utilizzato": periodo,
                               "liquidazione_id": liq_id,
                               "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE"},
                    )
            except Exception:
                logger.exception(f"Storia: hook IVA liquidazione fallito per {fid}")
        else:
            await _annulla_conferma_parziale()
            raise HTTPException(
                status_code=409,
                detail="Liquidazione non confermata: modifica concorrente rilevata",
            )

    try:
        conferma_res = await db[COLL_LIQ].update_one(
            {"id": liq_id, "stato": {"$nin": [liq.CONFERMATA, liq.TRASMESSA]}},
            {"$set": {
                "stato": liq.CONFERMATA,
                "data_conferma": ora,
                "confermata_da": actor,
                "updated_at": ora,
            }},
        )
        if conferma_res.modified_count != 1:
            await _annulla_conferma_parziale()
            raise HTTPException(
                status_code=409,
                detail="Liquidazione non confermata: stato modificato durante l'operazione",
            )
    except HTTPException:
        raise
    except Exception as exc:
        await _annulla_conferma_parziale()
        logger.exception("Conferma IVA annullata: liquidazione non aggiornata")
        raise HTTPException(
            status_code=500,
            detail="Liquidazione non confermata: salvataggio finale non riuscito",
        ) from exc
    doc.update({"stato": liq.CONFERMATA, "data_conferma": ora})
    return {
        "success": True, "liquidazione": doc,
        "fatture_marcate": marcate, "fatture_gia_utilizzate": [],
    }


@router.post("/liquidazioni/{liq_id}/riapri")
async def riapri_liquidazione(
    liq_id: str,
    utente: Optional[str] = Query(None, deprecated=True),
    motivo: str = Query("Riapertura", description="Motivazione obbligatoria (§19)"),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Riapre una liquidazione confermata liberando l'IVA delle sue fatture
    (torna disponibile per un nuovo calcolo)."""
    db = Database.get_db()
    doc = await db[COLL_LIQ].find_one({"id": liq_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Liquidazione non trovata")
    if doc.get("stato") not in (liq.CONFERMATA, liq.TRASMESSA):
        raise HTTPException(status_code=409, detail="Solo una liquidazione confermata può essere riaperta")

    actor = _utente_autenticato(current_user, utente)
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=422, detail="La motivazione della riapertura e obbligatoria")
    liberate = await _libera_fatture(db, liq_id, doc["periodo"], actor, motivo.strip())
    ora = datetime.utcnow().isoformat()
    await db[COLL_LIQ].update_one(
        {"id": liq_id},
        {"$set": {"stato": liq.RIAPERTA, "motivo_rettifica": motivo.strip(),
                  "riaperta_da": actor, "updated_at": ora}},
    )
    doc.update({"stato": liq.RIAPERTA})
    return {"success": True, "liquidazione": doc, "fatture_liberate": liberate}


async def _libera_fatture(db, liq_id: str, periodo: str, utente: str, motivo: str) -> int:
    """Sgancia dalle fatture l'utilizzo IVA di questa liquidazione."""
    ora = datetime.utcnow().isoformat()
    liberate = 0
    async for inv in db[COLL].find({"liquidazione_id": liq_id}, {"_id": 0, "id": 1, "importo_iva_utilizzato": 1}):
        res = await db[COLL].update_one(
            {"id": inv["id"], "liquidazione_id": liq_id},
            {"$set": {
                "iva_utilizzata": False,
                "periodo_iva_utilizzato": None,
                "liquidazione_id": None,
                "importo_iva_utilizzato": 0,
                "data_utilizzo_iva": None,
                "stato_detrazione_iva": "DA_INSERIRE",
                "disponibile_per_nuovo_calcolo": True,
            }},
        )
        if res.modified_count:
            liberate += 1
            await db[COLL_MOV].insert_one({
                "id": str(uuid.uuid4()),
                "fattura_id": inv["id"],
                "tipo_movimento": liq.MOV_RETTIFICA,
                "periodo": periodo,
                "importo_iva": inv.get("importo_iva_utilizzato"),
                "liquidazione_id": liq_id,
                "motivazione": motivo,
                "created_at": ora,
                "created_by": utente,
            })
    return liberate


@router.post("/liquidazioni/{liq_id}/rettifica")
async def rettifica_liquidazione(
    liq_id: str,
    utente: Optional[str] = Query(None, deprecated=True),
    motivo: str = Query(..., description="Motivazione obbligatoria della rettifica (§19)"),
    iva_vendite: Optional[float] = Query(None),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Rettifica una liquidazione confermata: la marca RETTIFICATA, libera le
    sue fatture e produce una NUOVA versione ricalcolata (§13)."""
    db = Database.get_db()
    doc = await db[COLL_LIQ].find_one({"id": liq_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Liquidazione non trovata")
    if doc.get("stato") not in (liq.CONFERMATA, liq.TRASMESSA):
        raise HTTPException(status_code=409, detail="Solo una liquidazione confermata può essere rettificata")

    periodo = doc["periodo"]
    actor = _utente_autenticato(current_user, utente)
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=422, detail="La motivazione della rettifica e obbligatoria")
    await _libera_fatture(db, liq_id, periodo, actor, motivo.strip())
    ora = datetime.utcnow().isoformat()
    await db[COLL_LIQ].update_one(
        {"id": liq_id},
        {"$set": {"stato": liq.RETTIFICATA, "motivo_rettifica": motivo.strip(),
                   "rettificata_da": actor, "updated_at": ora}},
    )

    # Nuova versione ricalcolata (bozza di lavoro)
    nuovo_id = str(uuid.uuid4())
    ultima = await db[COLL_LIQ].find_one({"periodo": periodo}, sort=[("versione", -1)])
    versione = int(ultima.get("versione") or 0) + 1 if ultima else 1
    iva_vendite_calcolata = (
        await _iva_vendite_corrispettivi(db, periodo)
        if iva_vendite is None
        else round(float(iva_vendite), 2)
    )
    nuovo = await _componi_liquidazione(db, periodo, iva_vendite_calcolata, versione, nuovo_id)
    nuovo["created_at"] = ora
    nuovo["motivo_rettifica"] = motivo.strip()
    nuovo["iva_vendite_fonte"] = "corrispettivi_xml" if iva_vendite is None else "override_manuale"
    await db[COLL_LIQ].insert_one(nuovo)
    nuovo.pop("_id", None)
    return {"success": True, "rettificata": liq_id, "nuova_liquidazione": nuovo}


@router.get("/liquidazioni")
async def lista_liquidazioni(
    anno: Optional[int] = Query(None),
    limit: int = Query(200, le=2000),
) -> Dict[str, Any]:
    """Elenco liquidazioni (tutte le versioni), ordinate per periodo/versione."""
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if anno:
        query["periodo"] = {"$regex": f"^{anno}"}
    docs = await db[COLL_LIQ].find(query, {"_id": 0}).sort(
        [("periodo", -1), ("versione", -1)]
    ).to_list(limit)
    return {"liquidazioni": docs, "totale": len(docs)}


@router.get("/liquidazioni/{periodo}")
async def liquidazione_periodo(periodo: str) -> Dict[str, Any]:
    """Ultima versione della liquidazione del periodo + tutte le versioni."""
    db = Database.get_db()
    versioni = await db[COLL_LIQ].find({"periodo": periodo}, {"_id": 0}).sort(
        "versione", -1
    ).to_list(100)
    corrente = versioni[0] if versioni else None
    return {"periodo": periodo, "corrente": corrente, "versioni": versioni}


# ─── Riepilogo/calcolo annuale e anomalie (Fase 4) ──────────────────────────

async def _fatture_anno(db, anno: int) -> List[Dict[str, Any]]:
    proj = {
        "_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1,
        "data_documento": 1, "data_operazione": 1, "data_ricezione": 1,
        "periodo_iva_attribuito": 1, "periodo_iva_utilizzato": 1,
        "iva": 1, "iva_detraibile": 1, "iva_utilizzata": 1,
        "stato_detrazione_iva": 1, "tipo_documento": 1, "annullata": 1,
    }
    # Fatture attribuite all'anno + (P2-d) fatture DA_VERIFICARE con periodo
    # nullo la cui data (documento/ricezione) cade nell'anno: senza questo
    # ramo la categoria "IVA da verificare" del §16 non le contava mai.
    return await db[COLL].find(
        {"$or": [
            {"periodo_iva_attribuito": {"$regex": f"^{anno}"}},
            {"periodo_iva_attribuito": {"$in": [None, ""]},
             "stato_detrazione_iva": "DA_VERIFICARE",
             "$or": [
                 {"data_documento": {"$regex": f"^{anno}"}},
                 {"data_ricezione": {"$regex": f"^{anno}"}},
             ]},
        ]},
        proj,
    ).to_list(20000)


@router.get("/dashboard/{anno}/{mese}")
async def dashboard_iva_mensile(anno: int, mese: int) -> Dict[str, Any]:
    """Riquadri IVA del mese (§21): attribuita, ricevuta-ma-attribuita-al-mese-
    precedente, utilizzata, non utilizzata, rinviata, indetraibile, credito
    precedente, saldo e stato della liquidazione."""
    db = Database.get_db()
    periodo = f"{anno}-{mese:02d}"
    prev = _periodo_precedente(periodo)

    def _somma_iva(docs):
        return round(sum(_iva_detraibile_fattura(d) for d in docs), 2)

    proj = {"_id": 0, "iva": 1, "iva_detraibile": 1, "stato_detrazione_iva": 1}
    attribuite = await db[COLL].find({"periodo_iva_attribuito": periodo}, proj).to_list(20000)
    utilizzate = await db[COLL].find({"periodo_iva_utilizzato": periodo}, proj).to_list(20000)
    rinviate = await db[COLL].find(
        {"periodo_iva_attribuito": periodo, "stato_detrazione_iva": "RINVIATA"}, proj
    ).to_list(20000)
    indetraibili = await db[COLL].find(
        {"periodo_iva_attribuito": periodo, "stato_detrazione_iva": "INDETRAIBILE"}, proj
    ).to_list(20000)
    # ricevute NEL mese ma attribuite al mese PRECEDENTE (regola entro il 15)
    ricevute_attr_prec = await db[COLL].find(
        {"data_ricezione": {"$regex": f"^{periodo}"}, "periodo_iva_attribuito": prev}, proj
    ).to_list(20000)

    non_utilizzate = [
        d for d in attribuite
        if d.get("stato_detrazione_iva") in liq.STATI_DETRAZIONE_AMMESSI
    ]

    liq_doc = await db[COLL_LIQ].find_one({"periodo": periodo}, {"_id": 0}, sort=[("versione", -1)])
    iva_vendite_corr = await _iva_vendite_corrispettivi(db, periodo)
    from app.services.iva_f24_verifica import verifica_versamento_iva

    versamento = await verifica_versamento_iva(
        db,
        anno=anno,
        mese=mese,
        debito_liquidazione=(liq_doc or {}).get("debito_periodo"),
    )

    return {
        "periodo": periodo,
        "iva_acquisti_attribuita": _somma_iva(attribuite),
        "iva_ricevuta_attribuita_mese_precedente": _somma_iva(ricevute_attr_prec),
        "iva_utilizzata": _somma_iva(utilizzate),
        "iva_non_utilizzata": _somma_iva(non_utilizzate),
        "iva_rinviata": _somma_iva(rinviate),
        "iva_indetraibile": _somma_iva(indetraibili),
        "credito_precedente": (liq_doc or {}).get("credito_precedente", 0),
        "iva_vendite": (liq_doc or {}).get("iva_vendite", iva_vendite_corr),
        "iva_vendite_corrispettivi": iva_vendite_corr,
        "iva_vendite_fonte": (liq_doc or {}).get("iva_vendite_fonte", "corrispettivi_xml"),
        "saldo": (liq_doc or {}).get("saldo"),
        "stato_liquidazione": (liq_doc or {}).get("stato"),
        "versamento_iva": versamento,
    }


@router.get("/versamento/{anno}/{mese}")
async def verifica_versamento_iva_mensile(anno: int, mese: int) -> Dict[str, Any]:
    """Verifica F24 IVA, quietanza e prova bancaria del periodo mensile."""
    if mese not in range(1, 13):
        raise HTTPException(status_code=422, detail="Mese non valido")
    db = Database.get_db()
    periodo = f"{anno}-{mese:02d}"
    liq_doc = await db[COLL_LIQ].find_one(
        {"periodo": periodo}, {"_id": 0}, sort=[("versione", -1)]
    )
    from app.services.iva_f24_verifica import verifica_versamento_iva

    return await verifica_versamento_iva(
        db,
        anno=anno,
        mese=mese,
        debito_liquidazione=(liq_doc or {}).get("debito_periodo"),
    )


@router.get("/riepilogo-annuale/{anno}")
async def riepilogo_annuale(anno: int) -> Dict[str, Any]:
    """Riepilogo IVA dell'anno per categoria + calcolo annuale (§16-17)."""
    db = Database.get_db()
    fatture = await _fatture_anno(db, anno)
    liquidazioni = await db[COLL_LIQ].find(
        {"periodo": {"$regex": f"^{anno}"}, "stato": {"$in": [liq.CONFERMATA, liq.TRASMESSA]}},
        {"_id": 0},
    ).to_list(1000)
    return {
        "anno": anno,
        "categorie": riep.riepilogo_categorie(fatture),
        "calcolo_annuale": riep.calcolo_annuale(fatture, liquidazioni),
    }


@router.get("/anomalie")
async def anomalie_iva(
    anno: int = Query(...),
    mese_corrente: Optional[str] = Query(None, description="'YYYY-MM' per l'avviso 'non usata da mesi'"),
) -> Dict[str, Any]:
    """Controlli automatici (§18): anomalie bloccanti e di avviso sull'anno."""
    db = Database.get_db()
    fatture = await _fatture_anno(db, anno)
    res = riep.rileva_anomalie(fatture, mese_corrente)
    return {
        "anno": anno,
        "bloccanti": res["bloccanti"],
        "avvisi": res["avvisi"],
        "totale_bloccanti": len(res["bloccanti"]),
        "totale_avvisi": len(res["avvisi"]),
    }


# ─── Azioni manuali sulle fatture (Fase 4, §19) ─────────────────────────────

# Ogni azione richiede motivazione; l'IVA già utilizzata è protetta (va prima
# riaperta la liquidazione). Ogni cambio è tracciato (vecchio→nuovo + movimento).
async def _azione_stato_fattura(
    fid: str, nuovo_stato: str, tipo_movimento: str, motivo: str, utente: str,
    extra_set: Optional[Dict[str, Any]] = None, consenti_se_utilizzata: bool = False,
) -> Dict[str, Any]:
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=422, detail="La motivazione e obbligatoria")
    motivo = motivo.strip()
    db = Database.get_db()
    inv = await db[COLL].find_one({"id": fid}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if inv.get("iva_utilizzata") is True and not consenti_se_utilizzata:
        raise HTTPException(
            status_code=409,
            detail="IVA già utilizzata in una liquidazione: riapri la liquidazione prima di modificarla.",
        )
    ora = datetime.utcnow().isoformat()
    vecchio = inv.get("stato_detrazione_iva")
    campi = {"stato_detrazione_iva": nuovo_stato, "updated_at": ora}
    if extra_set:
        campi.update(extra_set)
    await db[COLL].update_one({"id": fid}, {"$set": campi})
    await db[COLL_MOV].insert_one({
        "id": str(uuid.uuid4()),
        "fattura_id": fid,
        "tipo_movimento": tipo_movimento,
        "periodo": campi.get("periodo_iva_attribuito") or inv.get("periodo_iva_attribuito"),
        "importo_iva": _iva_detraibile_fattura(inv),
        "liquidazione_id": None,
        "motivazione": motivo,
        "valore_precedente": vecchio,
        "valore_nuovo": nuovo_stato,
        "created_at": ora,
        "created_by": utente,
    })
    return {"success": True, "fattura_id": fid, "stato_precedente": vecchio, "stato_nuovo": nuovo_stato}


@router.post("/fatture/{fid}/escludi")
async def escludi_fattura(
    fid: str, motivo: str = Query(...), utente: Optional[str] = Query(None, deprecated=True),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    """Esclude manualmente l'IVA della fattura dal calcolo (§19)."""
    return await _azione_stato_fattura(
        fid, "ESCLUSA", liq.MOV_ESCLUSIONE, motivo, _utente_autenticato(current_user, utente),
        extra_set={"disponibile_per_nuovo_calcolo": False, "motivo_esclusione": motivo},
    )


@router.post("/fatture/{fid}/includi")
async def includi_fattura(
    fid: str, motivo: str = Query("Reinclusa manualmente"), utente: Optional[str] = Query(None, deprecated=True),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    """Reinserisce nel calcolo una fattura esclusa/rinviata (§19)."""
    return await _azione_stato_fattura(
        fid, "DA_INSERIRE", liq.MOV_ATTRIBUZIONE, motivo, _utente_autenticato(current_user, utente),
        extra_set={"disponibile_per_nuovo_calcolo": True, "motivo_esclusione": None},
    )


@router.post("/fatture/{fid}/rinvia")
async def rinvia_fattura(
    fid: str, motivo: str = Query(...), utente: Optional[str] = Query(None, deprecated=True),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    """Rinvia l'IVA a un periodo successivo (§19)."""
    return await _azione_stato_fattura(
        fid, "RINVIATA", liq.MOV_ESCLUSIONE, motivo, _utente_autenticato(current_user, utente),
        extra_set={"disponibile_per_nuovo_calcolo": True},
    )


@router.post("/fatture/{fid}/indetraibile")
async def indetraibile_fattura(
    fid: str, motivo: str = Query(...), utente: Optional[str] = Query(None, deprecated=True),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    """Segna l'IVA come indetraibile per natura/limitazione (§19)."""
    return await _azione_stato_fattura(
        fid, "INDETRAIBILE", liq.MOV_RETTIFICA, motivo, _utente_autenticato(current_user, utente),
        extra_set={"disponibile_per_nuovo_calcolo": False},
    )


@router.post("/fatture/{fid}/recupero-annuale")
async def recupero_annuale_fattura(
    fid: str, motivo: str = Query(...), utente: Optional[str] = Query(None, deprecated=True),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    """Segna l'IVA come recuperata nella dichiarazione annuale (§19)."""
    return await _azione_stato_fattura(
        fid, "RECUPERATA_IN_DICHIARAZIONE_ANNUALE", liq.MOV_RECUPERO_ANNUALE, motivo, _utente_autenticato(current_user, utente),
    )


@router.post("/fatture/{fid}/correggi-periodo")
async def correggi_periodo_fattura(
    fid: str, periodo: str = Query(..., description="Nuovo periodo 'YYYY-MM'"),
    motivo: str = Query(...), utente: Optional[str] = Query(None, deprecated=True),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    """Corregge manualmente il periodo IVA attribuito (§19)."""
    try:
        datetime.strptime(periodo, "%Y-%m")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Periodo non valido: usare YYYY-MM") from exc
    return await _azione_stato_fattura(
        fid, "DA_INSERIRE", liq.MOV_RETTIFICA, motivo, _utente_autenticato(current_user, utente),
        extra_set={"periodo_iva_attribuito": periodo, "regola_iva_applicata": "CORREZIONE_MANUALE"},
    )
