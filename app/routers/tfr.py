"""TFR lato gestionale: proiezione in sola lettura del fondo per Gestione Cespiti.

Il motore TFR (accantonamento, liquidazione, acconti, scalatura in busta,
simulatore, calcolo lordo/netto) e' **uno solo** e vive in
``app/hr/routers/tfr.py``, montato su ``/hr/api/tfr``: HR possiede payroll e
TFR (CLAUDE.md §4, §64). Fino al 07/10/2026 questo file era una copia di
1.785 righe di quel router con 18 endpoint di scrittura mai chiamati da
nessuna pagina ERP, da nessun job e da nessun servizio: due writer dello
stesso fatto su due archivi, con correzioni applicate a un lato solo.

Restano qui soltanto le due letture che ``frontend/src/pages/GestioneCespiti.jsx``
chiama su ``/api/tfr``. Non sono un alias del lato HR perche' leggono un
archivio diverso: ``gestionale.dipendenti`` e ``gestionale.tfr_accantonamenti``,
dove il canale cedolini del gestionale (``app/handlers/tfr.py``) accumula
``tfr_maturato`` e una quota per mese. Gli id dipendente sono quelli del
gestionale, non quelli HR: la pagina ERP non puo' chiamare ``/hr/api/tfr``.
Il collegamento fra i due archivi (per codice fiscale) lo fa gia' il lato HR
con ``app/services/tfr_quote_buste.py``; una seconda copia qui non serve.

Costanti e lettura dell'acconto in busta sono re-export del canonico: un
solo valore, un solo lettore.
"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.database import Database
from app.hr.routers.tfr import (  # noqa: F401 - re-export del motore unico
    ALIQUOTA_TFR,
    RIVALUTAZIONE_FISSA,
    TFR_DIVISORE,
    _estrai_acconto_da_cedolino,
)
from app.utils.error_handler import handle_errors

router = APIRouter()


@router.get("/situazione/{dipendente_id}")
@handle_errors
async def get_situazione_tfr(dipendente_id: str) -> Dict[str, Any]:
    """Situazione TFR di un dipendente del gestionale: fondo, registro mese per
    mese degli accantonamenti e liquidazioni."""
    db = Database.get_db()

    dipendente = await db["dipendenti"].find_one({"id": dipendente_id}, {"_id": 0})
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    # Due canali alternativi, mai valorizzati insieme sullo stesso dipendente:
    # `tfr_accantonato` lo scrive solo l'import manuale Libro Unico;
    # `tfr_maturato` lo accumula il canale cedolini (handler_aggiorna_tfr).
    # Si usa quello popolato, non si sommano.
    tfr_manuale = float(dipendente.get("tfr_accantonato") or 0)
    tfr_da_cedolini = float(dipendente.get("tfr_maturato") or 0)
    tfr_accantonato = tfr_manuale if tfr_manuale > 0 else tfr_da_cedolini

    # Registro: il canale cedolini scrive un documento per (dipendente, mese,
    # anno) con "quota"; l'import manuale LUL uno annuale con "quota_annuale"
    # e senza "mese". Ordine anno/mese (le voci annuali in fondo all'anno);
    # "quota_mese" e "periodo" sono campi di presentazione, gli originali restano.
    accantonamenti_raw = await db["tfr_accantonamenti"].find(
        {"dipendente_id": dipendente_id}, {"_id": 0}
    ).sort([("anno", 1)]).to_list(500)
    accantonamenti = sorted(
        accantonamenti_raw,
        key=lambda a: (a.get("anno") or 0, a.get("mese") or 13),
    )
    for a in accantonamenti:
        a["quota_mese"] = round(float(a.get("quota") or 0) + float(a.get("quota_annuale") or 0), 2)
        a["periodo"] = (
            f"{int(a['mese']):02d}/{a['anno']}" if a.get("mese")
            else f"Anno {a.get('anno')} (import manuale)"
        )

    liquidazioni = await db["tfr_liquidazioni"].find(
        {"dipendente_id": dipendente_id}, {"_id": 0}
    ).sort("data", -1).to_list(100)
    totale_liquidato = sum(l.get("importo_lordo", 0) for l in liquidazioni)

    return {
        "dipendente_id": dipendente_id,
        "dipendente_nome": dipendente.get("nome_completo", ""),
        "tfr_accantonato": round(tfr_accantonato, 2),
        "tfr_disponibile": round(tfr_accantonato - totale_liquidato, 2),
        "totale_liquidato": round(totale_liquidato, 2),
        "num_accantonamenti": len(accantonamenti),
        "accantonamenti": accantonamenti,
        "liquidazioni": liquidazioni,
    }


@router.get("/riepilogo-aziendale")
@handle_errors
async def get_riepilogo_tfr_aziendale(anno: int = Query(None)) -> Dict[str, Any]:
    """Fondo TFR dei dipendenti attivi del gestionale, con accantonamenti e
    liquidazioni dell'anno: alimenta la scheda Fondo TFR di Gestione Cespiti."""
    db = Database.get_db()

    if not anno:
        anno = datetime.now().year

    # Campo canonico `stato` (non `status`). Per il fondo vale la stessa regola
    # della situazione: `tfr_accantonato` se popolato, altrimenti `tfr_maturato`.
    dipendenti = await db["dipendenti"].find(
        {"stato": {"$in": ["attivo", "active"]}},
        {"_id": 0, "id": 1, "nome_completo": 1, "tfr_accantonato": 1, "tfr_maturato": 1}
    ).to_list(1000)

    def _tfr_dipendente(d: Dict[str, Any]) -> float:
        accantonato = float(d.get("tfr_accantonato") or 0)
        return accantonato if accantonato > 0 else float(d.get("tfr_maturato") or 0)

    # Un documento ha sempre un solo schema ("quota" mensile oppure
    # "quota_annuale"/"totale_accantonamento" annuale): sommare entrambi con
    # $ifNull non conta due volte lo stesso record.
    accantonamenti_anno = await db["tfr_accantonamenti"].aggregate([
        {"$match": {"anno": anno}},
        {"$group": {
            "_id": None,
            "totale_quota": {"$sum": {"$add": [
                {"$ifNull": ["$quota_annuale", 0]},
                {"$ifNull": ["$quota", 0]},
            ]}},
            "totale_rivalutazione": {"$sum": {"$ifNull": ["$rivalutazione", 0]}},
            "totale_accantonato": {"$sum": {"$add": [
                {"$ifNull": ["$totale_accantonamento", 0]},
                {"$ifNull": ["$quota", 0]},
            ]}},
            "num_dipendenti": {"$sum": 1}
        }}
    ]).to_list(1)

    liquidazioni_anno = await db["tfr_liquidazioni"].aggregate([
        {"$match": {"data": {"$regex": f"^{anno}"}}},
        {"$group": {
            "_id": None,
            "totale_lordo": {"$sum": "$importo_lordo"},
            "totale_ritenute": {"$sum": "$ritenute"},
            "totale_netto": {"$sum": "$importo_netto"},
            "num_liquidazioni": {"$sum": 1}
        }}
    ]).to_list(1)

    totale_fondo = sum(_tfr_dipendente(d) for d in dipendenti)
    dettaglio_dipendenti = [
        {
            "dipendente_id": d["id"],
            "nome": d.get("nome_completo", ""),
            "tfr_accantonato": round(_tfr_dipendente(d), 2),
        }
        for d in dipendenti
        if _tfr_dipendente(d) > 0
    ]

    acc = accantonamenti_anno[0] if accantonamenti_anno else None
    liq = liquidazioni_anno[0] if liquidazioni_anno else None
    return {
        "anno": anno,
        "totale_fondo_tfr": round(totale_fondo, 2),
        "num_dipendenti_attivi": len(dipendenti),
        "accantonamenti_anno": {
            "totale_quota": round(acc["totale_quota"], 2) if acc else 0,
            "totale_rivalutazione": round(acc["totale_rivalutazione"], 2) if acc else 0,
            "totale_accantonato": round(acc["totale_accantonato"], 2) if acc else 0,
            "num_dipendenti": acc["num_dipendenti"] if acc else 0,
        },
        "liquidazioni_anno": {
            "totale_lordo": round(liq["totale_lordo"], 2) if liq else 0,
            "totale_ritenute": round(liq["totale_ritenute"], 2) if liq else 0,
            "totale_netto": round(liq["totale_netto"], 2) if liq else 0,
            "num_liquidazioni": liq["num_liquidazioni"] if liq else 0,
        },
        "dettaglio_dipendenti": sorted(dettaglio_dipendenti, key=lambda x: x["tfr_accantonato"], reverse=True),
    }
