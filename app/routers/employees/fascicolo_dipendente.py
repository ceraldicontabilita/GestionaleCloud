"""
Fascicolo Dipendente — Endpoint unificato v2
============================================
Fix critici:
- Usa Collections.EMPLOYEES invece di stringa "dipendenti"
- Match bonifici per IBAN (prioritario) poi per nome
- Normalizza tipo_contratto per scadenze
- Aggiunte: statistiche presenze mese corrente, progressivi ferie/permessi
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
import logging
import re

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dipendenti", tags=["Fascicolo Dipendente"])


@router.get("/{dipendente_id}/fascicolo")
async def fascicolo_dipendente(
    dipendente_id: str,
    anno: Optional[int] = Query(None, description="Anno (default: corrente)")
) -> Dict[str, Any]:
    """
    Fascicolo completo del dipendente: anagrafica + cedolini + stipendi banca +
    presenze + TFR + saldi + progressivi ferie. Un unico endpoint per la scheda.
    """
    db = Database.get_db()
    if not anno:
        anno = datetime.now().year

    # ── 1. ANAGRAFICA ──
    dip = await db[Collections.EMPLOYEES].find_one(
        {"$or": [{"id": dipendente_id}, {"codice_fiscale": dipendente_id}]},
        {"_id": 0}
    )
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    dip_id = dip.get("id", dipendente_id)
    cf = (dip.get("codice_fiscale") or "").upper().strip()
    nome = dip.get("nome", "")
    cognome = dip.get("cognome", "")
    nome_completo = dip.get("nome_completo") or f"{cognome} {nome}".strip()
    iban = dip.get("iban_cedolino") or dip.get("iban") or ""
    ibans = dip.get("ibans") or ([iban] if iban else [])

    # ── 2. CEDOLINI ──
    ced_query = {"$or": [{"dipendente_id": dip_id}]}
    if cf:
        ced_query["$or"].append({"codice_fiscale": cf})
    ced_query_anno = {"$and": [ced_query, {"$or": [{"anno": anno}, {"anno": str(anno)}]}]}

    cedolini = await db[Collections.PAYSLIPS].find(
        ced_query_anno, {"_id": 0, "pdf_data": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(500)

    totale_lordo = sum(float(c.get("lordo", 0) or 0) for c in cedolini)
    totale_netto = sum(float(c.get("netto", 0) or c.get("netto_mese", 0) or 0) for c in cedolini)
    totale_tfr = sum(float(c.get("tfr", 0) or c.get("tfr_mese", 0) or 0) for c in cedolini)

    # ── 3. STIPENDI DA BANCA — 3 strategie ──
    stipendi_banca = []
    seen_ids = set()

    # A: IBAN match
    for ib in ibans:
        if not ib or len(ib) < 10:
            continue
        ib_clean = ib.replace(" ", "").upper()
        # cerca ultimi 10 caratteri IBAN nell'archivio bonifici
        suffix = ib_clean[-10:]
        candidates = await db["estratto_conto_movimenti"].find(
            {"descrizione": {"$regex": re.escape(suffix), "$options": "i"}, "tipo": "uscita"},
            {"_id": 0}
        ).sort("data", -1).to_list(50)
        for c in candidates:
            if c.get("id") not in seen_ids:
                seen_ids.add(c.get("id"))
                c["match_tipo"] = "iban"
                stipendi_banca.append(c)

    # B: Nome in descrizione (fallback)
    if len(stipendi_banca) < 3 and nome_completo:
        parts = nome_completo.split()
        if len(parts) >= 2:
            pattern = f"{re.escape(parts[0])}.*{re.escape(parts[1])}"
            candidates = await db["estratto_conto_movimenti"].find(
                {"descrizione": {"$regex": pattern, "$options": "i"}, "tipo": "uscita"},
                {"_id": 0}
            ).sort("data", -1).to_list(30)
            for c in candidates:
                if c.get("id") not in seen_ids:
                    seen_ids.add(c.get("id"))
                    c["match_tipo"] = "nome"
                    stipendi_banca.append(c)

    # C: Archivio bonifici (strutturato)
    if nome_completo:
        parts = nome_completo.split()
        pattern = "|".join(re.escape(p) for p in parts if len(p) > 3)
        if pattern:
            try:
                transfers = await db["bonifici_transfers"].find(
                    {"$or": [
                        {"dipendente_id": dip_id},
                        {"beneficiario.nome": {"$regex": pattern, "$options": "i"}},
                    ]},
                    {"_id": 0}
                ).sort("data", -1).to_list(50)
                for c in transfers:
                    cid = c.get("id") or c.get("transaction_id")
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        c["match_tipo"] = "bonifici_arch"
                        stipendi_banca.append(c)
            except Exception as e:
                logger.warning(f"fascicolo: bonifici_transfers skip: {e}")

    stipendi_banca.sort(key=lambda x: x.get("data", ""), reverse=True)

    # ── 4. CONTRATTI ──
    contratti = await db["contratti_dipendenti"].find(
        {"dipendente_id": dip_id}, {"_id": 0}
    ).sort("data_inizio", -1).to_list(20)

    # ── 5. PRESENZE MESE CORRENTE ──
    oggi = datetime.now()
    presenze_mese = []
    try:
        presenze_mese = await db["presenze_giornaliere"].find(
            {
                "$or": [{"employee_id": dip_id}, {"codice_fiscale": cf}],
                "anno": oggi.year,
                "mese": oggi.month,
            },
            {"_id": 0}
        ).to_list(31)
    except Exception as e:
        logger.warning(f"fascicolo: presenze_giornaliere skip: {e}")

    # ── 6. ACCONTI TFR ──
    acconti_tfr = []
    try:
        acconti_tfr = await db["tfr_acconti"].find(
            {"dipendente_id": dip_id}, {"_id": 0}
        ).sort("data", -1).to_list(50)
    except Exception as e:
        logger.warning(f"fascicolo: tfr_acconti skip: {e}")

    # ── 7. PROGRESSIVI FERIE/PERMESSI ──
    progressivi = dip.get("progressivi", {})

    # ── 8. VERBALI ──
    verbali = []
    try:
        v_query = [{"dipendente_id": dip_id}]
        if cf:
            v_query.append({"codice_fiscale": cf})
        verbali = await db["verbali_autovelox"].find(
            {"$or": v_query}, {"_id": 0}
        ).sort("data_verbale", -1).to_list(50)
    except Exception as e:
        logger.warning(f"fascicolo: verbali_autovelox skip: {e}")

    # ── 9. GIUSTIFICATIVI ANNO ──
    giustificativi = []
    try:
        giustificativi = await db["giustificativi"].find(
            {"dipendente_id": dip_id, "anno": anno},
            {"_id": 0}
        ).sort("data_inizio", -1).to_list(200)
    except Exception as e:
        logger.warning(f"fascicolo: giustificativi skip: {e}")

    # ── RESPONSE ──
    return {
        "dipendente": dip,
        "anno": anno,
        "cedolini": cedolini,
        "totali_cedolini": {
            "lordo": totale_lordo,
            "netto": totale_netto,
            "tfr": totale_tfr,
            "count": len(cedolini),
        },
        "stipendi_banca": stipendi_banca[:30],
        "contratti": contratti,
        "presenze_mese": presenze_mese,
        "acconti_tfr": acconti_tfr,
        "progressivi": progressivi,
        "verbali": verbali,
        "giustificativi": giustificativi,
    }


@router.get("/{dipendente_id}/kpi")
async def kpi_dipendente(dipendente_id: str) -> Dict[str, Any]:
    """KPI rapidi per l'header della scheda dipendente."""
    db = Database.get_db()
    anno = datetime.now().year
    mese = datetime.now().month

    dip = await db[Collections.EMPLOYEES].find_one(
        {"$or": [{"id": dipendente_id}, {"codice_fiscale": dipendente_id}]},
        {"_id": 0, "id": 1, "progressivi": 1, "iban_cedolino": 1, "ibans": 1}
    )
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    dip_id = dip.get("id", dipendente_id)
    prog = dip.get("progressivi", {})

    # Ultimo cedolino
    ultimo_cedolino = await db[Collections.PAYSLIPS].find_one(
        {"dipendente_id": dip_id},
        {"_id": 0, "netto": 1, "lordo": 1, "mese": 1, "anno": 1},
        sort=[("anno", -1), ("mese", -1)]
    )

    # Contratti scaduti/in scadenza
    today_str = datetime.now().strftime("%Y-%m-%d")
    limit_str = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    contratto_alert = await db["contratti_dipendenti"].find_one({
        "dipendente_id": dip_id,
        "stato": "attivo",
        "data_fine": {"$lte": limit_str, "$gte": today_str}
    })

    return {
        "ferie_residue": prog.get("ferie_residue", 0),
        "permessi_residui": prog.get("permessi_residui", 0),
        "tfr_accantonato": prog.get("tfr_accantonato", 0),
        "ultimo_netto": ultimo_cedolino.get("netto") if ultimo_cedolino else None,
        "ultimo_cedolino_mese": f"{ultimo_cedolino.get('mese')}/{ultimo_cedolino.get('anno')}" if ultimo_cedolino else None,
        "contratto_in_scadenza": contratto_alert is not None,
        "contratto_scadenza_data": contratto_alert.get("data_fine") if contratto_alert else None,
    }
