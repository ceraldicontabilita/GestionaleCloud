"""
Handler Estratto Conto — reagisce a estratto_conto.importato.
Abbina automaticamente solo le fatture con evidenza forte. F24, cedolini e
corrispettivi POS restano proposte per i rispettivi motori canonici.

Soglie di confidenza:
  > 90% → abbinamento automatico + scrittura prima nota
  60-90% → propone abbinamento, aspetta conferma
  < 60%  → movimento resta "da abbinare"
"""
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from app.services.scritture_contabili import scrivi_movimento

logger = logging.getLogger(__name__)

# Scelta utente (10/07/2026): "solo importo esatto ±0,01 €" — il matching
# automatico propone solo corrispondenze quasi perfette sull'importo; tutto
# il resto resta riconciliazione manuale.
TOLLERANZA_IMPORTO = 0.01      # solo importo esatto (±1 centesimo)
TOLLERANZA_GIORNI  = 30        # finestra temporale per il match
SOGLIA_AUTO        = 0.90      # sopra questa soglia abbina in automatico
SOGLIA_PROPOSTA    = 0.60      # sopra questa soglia propone all'utente


async def _salva_proposta(
    db,
    *,
    tipo: str,
    movimento_id: str,
    documento_id: str,
    dati: Dict[str, Any],
) -> None:
    """Crea una proposta idempotente senza modificare i documenti sorgente."""
    proposal_id = f"{tipo}:{movimento_id}:{documento_id}"
    await db["operazioni_da_confermare"].update_one(
        {"id": proposal_id},
        {"$setOnInsert": {
            "id": proposal_id,
            "tipo": tipo,
            "movimento_id": movimento_id,
            "documento_id": documento_id,
            "stato": "da_confermare",
            "richiede_conferma": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **dati,
        }},
        upsert=True,
    )


def _nome_presente_nella_causale(nome: str, causale: str) -> bool:
    """Richiede tutti i token significativi del dipendente nella causale."""
    stop = {"SIG", "SIGRA", "DIPENDENTE", "STIPENDIO", "SALARIO"}
    token_nome = [
        token for token in re.sub(r"[^A-Z0-9]+", " ", (nome or "").upper()).split()
        if len(token) >= 3 and token not in stop
    ]
    token_causale = set(re.sub(r"[^A-Z0-9]+", " ", (causale or "").upper()).split())
    return bool(token_nome) and all(token in token_causale for token in token_nome)


def _score_match(movimento: Dict, fattura: Dict) -> float:
    """
    Calcola score 0-1 tra un movimento bancario e una fattura.
    Considera importo, fornitore e data.
    """
    if (movimento.get("tipo") or "").lower() != "uscita":
        return 0.0

    score = 0.0

    imp_mov = abs(float(movimento.get("importo", 0)))
    imp_fatt = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)

    if imp_mov <= 0 or imp_fatt <= 0:
        return 0.0

    # Match importo (peso 60%) — FILTRO DURO: solo importo esatto ±0,01 €
    # (scelta utente 10/07/2026), qualunque cosa dica la descrizione.
    importi_ammessi = [imp_fatt]
    if fattura.get("importo_residuo") is not None:
        importi_ammessi.append(float(fattura.get("importo_residuo") or 0))
    importi_ammessi.extend(
        float(rata.get("importo") or 0)
        for rata in fattura.get("pagamento_rate") or []
        if isinstance(rata, dict)
    )
    if any(
        valore > 0 and abs(imp_mov - valore) <= TOLLERANZA_IMPORTO
        for valore in importi_ammessi
    ):
        score += 0.60
    else:
        return 0.0  # importo diverso, scarta subito

    # Identita' obbligatoria: importo+data da soli generano falsi positivi
    # (es. accredito NUMIA da 24,40 scambiato per fattura Leasys).
    desc = " ".join(str(movimento.get(k) or "") for k in (
        "descrizione", "description", "descrizione_originale", "causale", "beneficiario"
    )).upper()
    forn = (fattura.get("cedente_denominazione") or
            fattura.get("fornitore_ragione_sociale") or
            fattura.get("supplier_name") or "").upper()
    stop = {"SRL", "SPA", "SNC", "SAS", "SOCIETA", "UNIPERSONALE", "ITALIA"}
    parole = [
        p for p in re.sub(r"[^A-Z0-9]+", " ", forn).split()
        if len(p) >= 4 and p not in stop
    ]
    match_fornitore = any(parola in desc for parola in parole[:6])

    numero = (fattura.get("numero_fattura") or fattura.get("numero_documento")
              or fattura.get("invoice_number") or "")
    from app.services.payment_invoice_matching import invoice_reference_in_text
    match_numero = invoice_reference_in_text(numero, desc)
    # Regola contabile unica: importo e fornitore non bastano, anche se la
    # data coincide e la candidata e' una sola. Il numero fattura deve essere
    # esplicitamente leggibile nella causale; in caso contrario non si crea
    # neppure una proposta automatica da questo motore legacy.
    if not (match_fornitore and match_numero):
        return 0.0
    score += 0.30

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
                # Un F24 puo' contenere piu' tributi (es. IVA + 1040): il
                # totale bancario non identifica codice e periodo. Il motore
                # legacy crea soltanto proposte, senza marcare nulla pagato.
                try:
                    candidati_f24 = await db["f24_unificato"].find({
                        "totale_debito": {
                            "$gte": importo - TOLLERANZA_IMPORTO,
                            "$lte": importo + TOLLERANZA_IMPORTO
                        },
                        "riconciliato_banca": {"$ne": True}
                    }).limit(20).to_list(20)
                    for candidato in candidati_f24:
                        candidato_id = str(candidato.get("id") or candidato.get("_id"))
                        await _salva_proposta(
                            db,
                            tipo="abbinamento_f24_estratto_conto",
                            movimento_id=mov_id,
                            documento_id=candidato_id,
                            dati={
                                "f24_id": candidato_id,
                                "importo_movimento": importo,
                                "importo_f24": float(candidato.get("totale_debito") or 0),
                                "confidenza": 0.50,
                                "criterio": "solo_importo_documento_multi_tributo",
                            },
                        )
                    if candidati_f24:
                        proposti += len(candidati_f24)
                    else:
                        non_abbinati += 1
                except Exception as e:
                    logger.debug(f"[HandlerEstrattoC] F24 match errore: {e}")
                    non_abbinati += 1
                continue

            # Check stipendio dalla descrizione
            is_stipendio = any(kw in desc for kw in
                               ["STIP", "SALARIO", "BONIFICO DIPENDENTE",
                                "YOUBUSINESS", "YOU BUSINESS"])
            if is_stipendio:
                candidati_salario = [
                    ced for ced in cedolini_aperti
                    if abs(importo - float(ced.get("importo", 0))) <= TOLLERANZA_IMPORTO
                ]
                for ced in candidati_salario:
                    ced_id = str(ced.get("id"))
                    identita_presente = _nome_presente_nella_causale(
                        str(ced.get("nome_dipendente") or ""), desc
                    )
                    await _salva_proposta(
                        db,
                        tipo="abbinamento_stipendio_estratto_conto",
                        movimento_id=mov_id,
                        documento_id=ced_id,
                        dati={
                            "salario_id": ced_id,
                            "dipendente_id": ced.get("dipendente_id"),
                            "importo_movimento": importo,
                            "importo_salario": float(ced.get("importo") or 0),
                            "identita_dipendente_presente": identita_presente,
                            "confidenza": 0.75 if identita_presente else 0.45,
                            "criterio": "proposta_importo_identita_periodo_da_confermare",
                        },
                    )
                if candidati_salario:
                    proposti += len(candidati_salario)
                else:
                    non_abbinati += 1
                continue

            # Match con fatture
            best_score = 0.0
            best_fattura = None
            candidati_auto = 0
            for fatt in fatture_aperte:
                s = _score_match(mov, fatt)
                if s >= SOGLIA_AUTO:
                    candidati_auto += 1
                if s > best_score:
                    best_score = s
                    best_fattura = fatt

            if best_fattura and best_score >= SOGLIA_AUTO and candidati_auto == 1:
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
                await scrivi_movimento(db, "banca", {
                    "id": str(uuid.uuid4()),
                    "fattura_id":  best_fattura["id"],
                    "movimento_id": mov_id,
                    "estratto_conto_id": mov_id,
                    "movimento_bancario_id": mov_id,
                    "data":   (mov.get("data") or "")[:10],
                    "tipo":   "uscita",
                    "importo": importo,
                    "descrizione": (f"Pagamento fattura "
                                    f"{best_fattura.get('numero_documento') or best_fattura.get('invoice_number', '')} "
                                    f"- {best_fattura.get('fornitore_ragione_sociale') or best_fattura.get('supplier_name', '')}"),
                    "categoria": "Fatture",
                    "source": "estratto_conto_auto",
                    "confidenza": best_score,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                await db["estratto_conto_movimenti"].update_one(
                    {"id": mov_id, "$or": [
                        {"fattura_id": {"$exists": False}},
                        {"fattura_id": None},
                        {"fattura_id": best_fattura["id"]},
                    ]},
                    {"$set": {
                        "riconciliato": True,
                        "abbinato": True,
                        "tipo_abbinamento": "fattura",
                        "documento_id": best_fattura["id"],
                        "fattura_id": best_fattura["id"],
                        "confidenza": best_score,
                    }},
                )
                # Chiudi scadenza
                await db["scadenziario_fornitori"].update_one(
                    {"fattura_id": best_fattura["id"], "pagato": {"$ne": True}},
                    {"$set": {"pagato": True, "data_pagamento": (mov.get("data") or "")[:10]}}
                )
                auto_abbinati += 1
                prima_nota_scritti += 1

            elif best_fattura and best_score >= SOGLIA_PROPOSTA and candidati_auto <= 1:
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

                    candidati_pos = await db["corrispettivi"].find({
                        "data": {"$gte": data_min, "$lte": data_max},
                        "totale": {
                            "$gte": importo - 1.0,
                            "$lte": importo + 1.0,
                        },
                        "riconciliato": {"$ne": True},
                    }).limit(20).to_list(20)
                    for corr in candidati_pos:
                        corr_id = str(corr.get("id") or corr.get("_id"))
                        await _salva_proposta(
                            db,
                            tipo="abbinamento_pos_estratto_conto",
                            movimento_id=mov_id,
                            documento_id=corr_id,
                            dati={
                                "corrispettivo_id": corr_id,
                                "importo_movimento": importo,
                                "importo_corrispettivo": float(corr.get("totale") or 0),
                                "confidenza": 0.55,
                                "criterio": "proposta_pos_chiusura_netto_accredito_da_confermare",
                            },
                        )
                    if candidati_pos:
                        proposti += len(candidati_pos)
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
