"""
Handler Estratto Conto — reagisce a estratto_conto.importato
Abbina automaticamente i movimenti bancari alle fatture, cedolini e F24.

Soglie di confidenza:
  > 90% → abbinamento automatico + scrittura prima nota
  60-90% → propone abbinamento, aspetta conferma
  < 60%  → movimento resta "da abbinare"
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TOLLERANZA_IMPORTO = 2.00      # €2 di differenza accettata
TOLLERANZA_GIORNI  = 30        # finestra temporale per il match
SOGLIA_AUTO        = 0.90      # sopra questa soglia abbina in automatico
SOGLIA_PROPOSTA    = 0.60      # sopra questa soglia propone all'utente


def _score_match(movimento: Dict, fattura: Dict) -> float:
    """
    Calcola score 0-1 tra un movimento bancario e una fattura.
    Considera importo, fornitore e data.
    """
    score = 0.0

    imp_mov = abs(float(movimento.get("importo", 0)))
    imp_fatt = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)

    if imp_mov <= 0 or imp_fatt <= 0:
        return 0.0

    # Match importo (peso 60%)
    diff = abs(imp_mov - imp_fatt)
    if diff <= 0.01:
        score += 0.60
    elif diff <= TOLLERANZA_IMPORTO:
        score += 0.45
    elif diff / imp_fatt <= 0.02:   # entro il 2%
        score += 0.35
    else:
        return 0.0  # importo troppo diverso, scarta subito

    # Match fornitore nella descrizione (peso 30%)
    desc = (movimento.get("descrizione") or movimento.get("description") or "").upper()
    forn = (fattura.get("fornitore_ragione_sociale") or
            fattura.get("supplier_name") or "").upper()
    if forn and len(forn) >= 4:
        # Prendi le prime 8 lettere significative
        parole = [p for p in forn.split() if len(p) >= 4]
        for parola in parole[:3]:
            if parola[:6] in desc:
                score += 0.30
                break
        else:
            score += 0.05  # bonus piccolo se non trova

    # Match data (peso 10%)
    try:
        data_mov  = datetime.strptime(
            (movimento.get("data") or movimento.get("data_operazione") or "")[:10],
            "%Y-%m-%d"
        )
        data_fatt = datetime.strptime(
            (fattura.get("data_documento") or fattura.get("invoice_date") or "")[:10],
            "%Y-%m-%d"
        )
        delta = abs((data_mov - data_fatt).days)
        if delta <= 5:
            score += 0.10
        elif delta <= TOLLERANZA_GIORNI:
            score += 0.05
    except Exception:
        pass

    return min(score, 1.0)


async def handler_matching_estratto_conto(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Per ogni movimento dell'estratto conto importato:
    1. Cerca match con fatture non pagate (per uscite)
    2. Cerca match con cedolini non erogati (per uscite simili a stipendi)
    3. Cerca match con F24 (per uscite con causale F24/Tributi)
    4. Cerca match con corrispettivi POS/Nexi (per entrate)
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    movimenti: List[Dict] = payload.get("movimenti") or payload.get("transazioni") or []
    banca = payload.get("banca", "")

    if not movimenti:
        return {"skipped": True, "reason": "nessun movimento"}

    auto_abbinati  = 0
    proposti       = 0
    non_abbinati   = 0
    prima_nota_scritti = 0

    # Carica fatture non pagate per il periodo
    fatture_aperte = await db["invoices"].find(
        {"pagato": {"$ne": True}, "stato": {"$nin": ["annullata", "stornata"]}},
        {"_id": 0, "id": 1, "importo_totale": 1, "total_amount": 1,
         "data_documento": 1, "invoice_date": 1,
         "fornitore_ragione_sociale": 1, "supplier_name": 1,
         "numero_documento": 1, "invoice_number": 1,
         "metodo_pagamento": 1}
    ).to_list(2000)

    # Carica cedolini non erogati
    cedolini_aperti = await db["prima_nota_salari"].find(
        {"riconciliato": {"$ne": True}},
        {"_id": 0, "id": 1, "importo": 1, "nome_dipendente": 1,
         "data": 1, "dipendente_id": 1}
    ).to_list(500)

    for mov in movimenti:
        tipo = (mov.get("tipo") or "").lower()
        importo = float(mov.get("importo", 0))
        mov_id = mov.get("id") or str(uuid.uuid4())
        desc = (mov.get("descrizione") or mov.get("description") or "").upper()

        # ── Movimento in USCITA → cerca fattura da pagare ────────────────
        if tipo == "uscita" and importo > 0:

            # Check F24 dalla descrizione
            is_f24 = any(kw in desc for kw in ["F24", "TRIBUTI", "AGENZIA ENTRATE",
                                                 "IRPEF", "IVA", "INPS", "I24"])
            if is_f24:
                # Cerca F24 con importo simile nella finestra temporale
                try:
                    data_mov = mov.get("data") or mov.get("data_operazione") or ""
                    f24_match = await db["f24_unificato"].find_one({
                        "totale_debito": {
                            "$gte": importo - TOLLERANZA_IMPORTO,
                            "$lte": importo + TOLLERANZA_IMPORTO
                        },
                        "riconciliato_banca": {"$ne": True}
                    })
                    if f24_match:
                        await db["f24_unificato"].update_one(
                            {"_id": f24_match["_id"]},
                            {"$set": {
                                "riconciliato_banca": True,
                                "movimento_id": mov_id,
                                "data_addebito": data_mov,
                                "banca": banca,
                            }}
                        )
                        await db["estratto_conto_movimenti"].update_one(
                            {"id": mov_id},
                            {"$set": {
                                "abbinato": True,
                                "tipo_abbinamento": "f24",
                                "documento_id": f24_match.get("id"),
                                "confidenza": 0.95,
                            }}
                        )
                        auto_abbinati += 1
                        continue
                except Exception as e:
                    logger.debug(f"[HandlerEstrattoC] F24 match errore: {e}")

            # Check stipendio dalla descrizione
            is_stipendio = any(kw in desc for kw in
                               ["STIP", "SALARIO", "BONIFICO DIPENDENTE",
                                "YOUBUSINESS", "YOU BUSINESS"])
            if is_stipendio:
                for ced in cedolini_aperti:
                    imp_ced = float(ced.get("importo", 0))
                    diff = abs(importo - imp_ced)
                    if diff <= TOLLERANZA_IMPORTO:
                        await db["prima_nota_salari"].update_one(
                            {"id": ced["id"]},
                            {"$set": {
                                "riconciliato": True,
                                "movimento_id": mov_id,
                                "data_erogazione": mov.get("data"),
                                "banca": banca,
                            }}
                        )
                        await db["estratto_conto_movimenti"].update_one(
                            {"id": mov_id},
                            {"$set": {
                                "abbinato": True,
                                "tipo_abbinamento": "stipendio",
                                "documento_id": ced["id"],
                                "dipendente": ced.get("nome_dipendente"),
                                "confidenza": 0.92,
                            }}
                        )
                        auto_abbinati += 1
                        break
                else:
                    non_abbinati += 1
                continue

            # Match con fatture
            best_score = 0.0
            best_fattura = None
            for fatt in fatture_aperte:
                s = _score_match(mov, fatt)
                if s > best_score:
                    best_score = s
                    best_fattura = fatt

            if best_fattura and best_score >= SOGLIA_AUTO:
                # Abbinamento automatico
                await db["invoices"].update_one(
                    {"id": best_fattura["id"]},
                    {"$set": {
                        "pagato": True,
                        "data_pagamento": (mov.get("data") or
                                           mov.get("data_operazione") or "")[:10],
                        "riconciliato": True,
                        "movimento_bancario_id": mov_id,
                        "banca_addebito": banca,
                    }}
                )
                # Scrive in prima nota banca
                await db["prima_nota_banca"].insert_one({
                    "id": str(uuid.uuid4()),
                    "fattura_id":  best_fattura["id"],
                    "movimento_id": mov_id,
                    "data":   (mov.get("data") or "")[:10],
                    "tipo":   "uscita",
                    "importo": importo,
                    "descrizione": (f"Pagamento fattura "
                                    f"{best_fattura.get('numero_documento', '')} "
                                    f"- {best_fattura.get('fornitore_ragione_sociale', '')}"),
                    "categoria": "Fornitori",
                    "source": "estratto_conto_auto",
                    "confidenza": best_score,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                # Chiudi scadenza
                await db["scadenziario_fornitori"].update_one(
                    {"fattura_id": best_fattura["id"], "pagato": {"$ne": True}},
                    {"$set": {"pagato": True, "data_pagamento": (mov.get("data") or "")[:10]}}
                )
                auto_abbinati += 1
                prima_nota_scritti += 1

            elif best_fattura and best_score >= SOGLIA_PROPOSTA:
                # Propone abbinamento
                await db["operazioni_da_confermare"].insert_one({
                    "id": str(uuid.uuid4()),
                    "tipo": "abbinamento_estratto_conto",
                    "movimento_id": mov_id,
                    "fattura_id": best_fattura["id"],
                    "confidenza": best_score,
                    "importo_movimento": importo,
                    "importo_fattura": float(
                        best_fattura.get("importo_totale") or
                        best_fattura.get("total_amount") or 0
                    ),
                    "descrizione": (f"Possibile pagamento fattura "
                                    f"{best_fattura.get('numero_documento', '')}"),
                    "stato": "da_confermare",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                proposti += 1
            else:
                non_abbinati += 1

        # ── Movimento in ENTRATA → cerca match POS/corrispettivi ─────────
        elif tipo == "entrata" and importo > 0:
            is_pos = any(kw in desc for kw in
                         ["NEXI", "POS", "PAGAMENTI ELETTRONICI", "SUMUP",
                          "PAYPAL", "STRIPE"])
            if is_pos:
                try:
                    data_str = (mov.get("data") or mov.get("data_operazione") or "")[:10]
                    data_base = datetime.strptime(data_str, "%Y-%m-%d")
                    data_min  = (data_base - timedelta(days=3)).strftime("%Y-%m-%d")
                    data_max  = (data_base + timedelta(days=1)).strftime("%Y-%m-%d")

                    corr = await db["corrispettivi"].find_one({
                        "data": {"$gte": data_min, "$lte": data_max},
                        "totale": {
                            "$gte": importo - 1.0,
                            "$lte": importo + 1.0,
                        },
                        "riconciliato": {"$ne": True},
                    })
                    if corr:
                        await db["corrispettivi"].update_one(
                            {"_id": corr["_id"]},
                            {"$set": {
                                "riconciliato": True,
                                "movimento_id": mov_id,
                                "data_accredito": data_str,
                            }}
                        )
                        auto_abbinati += 1
                    else:
                        non_abbinati += 1
                except Exception:
                    non_abbinati += 1
            else:
                non_abbinati += 1

    logger.info(
        f"[HandlerEstrattoC] {banca}: "
        f"{auto_abbinati} auto | {proposti} proposti | {non_abbinati} non abbinati | "
        f"{prima_nota_scritti} prima nota scritti"
    )

    return {
        "auto_abbinati":       auto_abbinati,
        "proposti_conferma":   proposti,
        "non_abbinati":        non_abbinati,
        "prima_nota_scritti":  prima_nota_scritti,
        "totale_movimenti":    len(movimenti),
    }
