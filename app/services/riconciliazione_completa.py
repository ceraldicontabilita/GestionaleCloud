"""
Riconciliazione Completa — Ceraldi ERP
========================================
Riconcilia documenti Gmail con estratto conto bancario:
- PagoPA (avvisi pagamento Comune di Napoli)
- Cartelle Agenzia Entrate
- Cartelle Agenzia Riscossione (ADER)
- TARI (tassa rifiuti)
- Confronto POS corrispettivi vs inserimento manuale
"""
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Abbinamento documento → movimento bancario
#
# Le tre riconciliazioni qui sotto cercavano il PRIMO movimento che conteneva una
# parola generica («pagopa», «riscossione», «TARI») e lo legavano a OGNI
# documento, senza guardare l'importo (estratto dall'oggetto e mai usato) e
# riusando lo stesso movimento per tutti: documenti segnati «riconciliati» con
# un pagamento che non era il loro. Ora un documento si lega a un movimento solo
# se il movimento e' uno, identificato dal numero (IUV / cartella) oppure
# dall'importo esatto fra quelli della parola chiave, e non e' gia' usato.
# ─────────────────────────────────────────────────────────────────────────────

_IMPORTO = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+[.,]\d{2})")


def _importo_documento(doc: dict) -> float | None:
    for campo in ("importo", "importo_totale", "importo_da_pagare"):
        valore = doc.get(campo)
        try:
            if valore not in (None, ""):
                return round(abs(float(valore)), 2)
        except (TypeError, ValueError):
            pass
    testo = f"{doc.get('email_subject') or ''} {doc.get('filename') or ''}"
    trovato = _IMPORTO.search(testo)
    if not trovato:
        return None
    grezzo = trovato.group(1)
    grezzo = grezzo.replace(".", "").replace(",", ".") if "," in grezzo else grezzo
    try:
        return round(abs(float(grezzo)), 2)
    except ValueError:
        return None


async def _movimenti_gia_usati(db) -> set:
    usati = set()
    for coll in ("documenti_non_associati", "cartelle_email_attachments"):
        async for d in db[coll].find(
            {"riconciliato": True, "movimento_banca_id": {"$nin": [None, ""]}},
            {"_id": 0, "movimento_banca_id": 1},
        ):
            usati.add(d["movimento_banca_id"])
    return usati


async def _abbina_movimento(db, *, identificativo: str | None, importo: float | None,
                            parole: str, usati: set, solo_uscite: bool = True) -> tuple[dict | None, str]:
    """Il movimento del documento, oppure (None, motivo). Mai il primo a caso."""
    base = {"tipo": "uscita"} if solo_uscite else {}
    candidati = []
    if identificativo:
        candidati = await db["estratto_conto_movimenti"].find(
            {**base, "descrizione": {"$regex": re.escape(identificativo), "$options": "i"}}, {"_id": 0}
        ).to_list(20)
    if not candidati and importo is not None:
        per_parola = await db["estratto_conto_movimenti"].find(
            {**base, "descrizione": {"$regex": parole, "$options": "i"}}, {"_id": 0}
        ).to_list(1000)
        candidati = [m for m in per_parola if abs(abs(float(m.get("importo") or 0)) - importo) < 0.01]
    candidati = [m for m in candidati if m.get("id") and m["id"] not in usati]
    if not identificativo and importo is None:
        return None, "senza_riferimenti"
    if not candidati:
        return None, "non_trovato"
    if len(candidati) > 1:
        return None, "ambiguo"
    return candidati[0], "ok"


async def _riconcilia_documenti(db, docs, *, parole: str, estrai_id, etichetta: str) -> Dict[str, Any]:
    stats = {"analizzati": len(docs), "riconciliati": 0, "non_trovati": 0, "ambigui": 0, "senza_riferimenti": 0}
    usati = await _movimenti_gia_usati(db)
    for doc in docs:
        mov, esito = await _abbina_movimento(
            db, identificativo=estrai_id(doc), importo=_importo_documento(doc), parole=parole, usati=usati
        )
        if not mov:
            stats["ambigui" if esito == "ambiguo" else "senza_riferimenti" if esito == "senza_riferimenti" else "non_trovati"] += 1
            continue
        coll = "cartelle_email_attachments" if doc.get("_da_cartelle") else "documenti_non_associati"
        await db[coll].update_one(
            {"id": doc["id"]},
            {"$set": {
                "riconciliato": True,
                "riconciliato_con": "estratto_conto",
                "movimento_banca_id": mov.get("id"),
                "data_pagamento": mov.get("data_contabile"),
                "importo_pagato": abs(float(mov.get("importo", 0))),
            }},
        )
        usati.add(mov["id"])
        stats["riconciliati"] += 1
    logger.info(f"[{etichetta}] {stats}")
    return stats


def _numero(pattern: str):
    def estrai(doc: dict) -> str | None:
        trovato = re.search(pattern, doc.get("filename") or "")
        return trovato.group(1) if trovato else None
    return estrai


async def riconcilia_pagopa_con_banca(db) -> Dict[str, Any]:
    """Avvisi PagoPA (Comune di Napoli): per IUV, oppure per importo esatto."""
    docs = await db["documenti_non_associati"].find(
        {"categoria_mittente": "Comune di Napoli", "riconciliato": {"$ne": True}},
        {"_id": 0, "pdf_data": 0},
    ).to_list(200)
    return await _riconcilia_documenti(
        db, docs, parole="pagopa|partenopay|comune.*napol", estrai_id=_numero(r"(\d{15,18})"),
        etichetta="RICONCILIA-PAGOPA",
    )


async def riconcilia_cartelle_agenzia_entrate(db) -> Dict[str, Any]:
    """Cartelle Agenzia Entrate/Riscossione: per numero cartella, oppure per importo esatto."""
    docs = await db["documenti_non_associati"].find(
        {"categoria_mittente": "Agenzia Entrate", "riconciliato": {"$ne": True}},
        {"_id": 0, "pdf_data": 0},
    ).to_list(200)
    cartelle = await db["cartelle_email_attachments"].find(
        {"riconciliato": {"$ne": True}}, {"_id": 0, "pdf_data": 0}
    ).to_list(200)
    for c in cartelle:
        c["_da_cartelle"] = True
    return await _riconcilia_documenti(
        db, docs + cartelle, parole="agenzia.*entrate|agenzia.*riscossione|ADER|equitalia|riscossione",
        estrai_id=_numero(r"(\d{10,20})"), etichetta="RICONCILIA-ADER",
    )


async def riconcilia_tari_con_banca(db) -> Dict[str, Any]:
    """Avvisi TARI: per numero avviso, oppure per importo esatto."""
    docs = await db["documenti_non_associati"].find(
        {"$or": [
            {"filename": {"$regex": "tari|TARI", "$options": "i"}},
            {"email_subject": {"$regex": "tari|tassa rifiuti", "$options": "i"}},
        ], "riconciliato": {"$ne": True}},
        {"_id": 0, "pdf_data": 0},
    ).to_list(100)
    return await _riconcilia_documenti(
        db, docs, parole="TARI|tassa rifiuti|tributi locali", estrai_id=_numero(r"(\d{10,20})"),
        etichetta="RICONCILIA-TARI",
    )


async def confronta_pos_corrispettivi(db, anno: int = 2026) -> Dict[str, Any]:
    """
    Confronta il pagamento elettronico dei corrispettivi telematici
    con l'inserimento manuale serale dei POS.
    Evidenzia discrepanze per evitare sanzioni fiscali.
    
    Corrispettivo XML: campo 'pagato_elettronico' (dal registratore telematico)
    Inserimento manuale: movimenti Prima Nota Cassa con categoria 'POS'
    Estratto conto: accrediti POS dalla banca (INC.POS)
    """
    stats = {
        "giorni_analizzati": 0,
        "discrepanze": [],
        "totale_corrispettivo_pos": 0,
        "totale_manuale_pos": 0,
        "totale_banca_pos": 0,
        "differenza_corr_vs_manuale": 0,
        "differenza_corr_vs_banca": 0,
        "giorni_ok": 0,
        "giorni_discrepanza": 0,
    }
    
    # 1. Carica corrispettivi dell'anno
    corrispettivi = await db["corrispettivi"].find(
        {"anno": anno},
        {"_id": 0}
    ).sort("data", 1).to_list(400)
    
    # 2. Carica movimenti POS dalla Prima Nota Cassa
    pn_pos = await db["prima_nota_cassa"].find(
        {"categoria": {"$regex": "POS|pos|Elettronico", "$options": "i"},
         "data": {"$regex": f"^{anno}"}},
        {"_id": 0}
    ).to_list(400)
    
    # 3. Carica accrediti POS dalla banca
    banca_pos = await db["estratto_conto_movimenti"].find(
        {"descrizione": {"$regex": "INC.POS|POS CARTE|NUMIA|SUM UP|SATISPAY", "$options": "i"},
         "data_contabile": {"$regex": f"/{anno}$"}},
        {"_id": 0}
    ).to_list(1000)
    
    # Index per data
    manuale_per_data = {}
    for m in pn_pos:
        data = m.get("data", "")[:10]
        manuale_per_data[data] = manuale_per_data.get(data, 0) + float(m.get("importo", 0))
    
    banca_per_data = {}
    for b in banca_pos:
        data_raw = b.get("data_contabile", "")
        if "/" in data_raw:
            parts = data_raw.split("/")
            data = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else data_raw
        else:
            data = data_raw[:10]
        banca_per_data[data] = banca_per_data.get(data, 0) + float(b.get("importo", 0))
    
    # 4. Confronta giorno per giorno
    for corr in corrispettivi:
        data = corr.get("data", "")[:10]
        pos_corr = float(corr.get("pagato_elettronico", 0) or 0)
        pos_manuale = manuale_per_data.get(data, 0)
        pos_banca = banca_per_data.get(data, 0)
        
        stats["giorni_analizzati"] += 1
        stats["totale_corrispettivo_pos"] += pos_corr
        stats["totale_manuale_pos"] += pos_manuale
        stats["totale_banca_pos"] += pos_banca
        
        # Tolleranza: ±5€ per differenze di arrotondamento
        diff_manuale = abs(pos_corr - pos_manuale)
        diff_banca = abs(pos_corr - pos_banca)
        
        if diff_manuale > 5 or (diff_banca > 5 and pos_banca > 0):
            stats["giorni_discrepanza"] += 1
            stats["discrepanze"].append({
                "data": data,
                "corrispettivo_pos": round(pos_corr, 2),
                "manuale_pos": round(pos_manuale, 2),
                "banca_pos": round(pos_banca, 2),
                "differenza_corr_manuale": round(pos_corr - pos_manuale, 2),
                "differenza_corr_banca": round(pos_corr - pos_banca, 2),
                "alert": "⚠️ DISCREPANZA" if diff_manuale > 50 else "⚡ Lieve differenza",
            })
        else:
            stats["giorni_ok"] += 1
    
    stats["totale_corrispettivo_pos"] = round(stats["totale_corrispettivo_pos"], 2)
    stats["totale_manuale_pos"] = round(stats["totale_manuale_pos"], 2)
    stats["totale_banca_pos"] = round(stats["totale_banca_pos"], 2)
    stats["differenza_corr_vs_manuale"] = round(stats["totale_corrispettivo_pos"] - stats["totale_manuale_pos"], 2)
    stats["differenza_corr_vs_banca"] = round(stats["totale_corrispettivo_pos"] - stats["totale_banca_pos"], 2)
    
    logger.info(f"[CONFRONTO-POS] {stats['giorni_analizzati']} giorni, {stats['giorni_discrepanza']} discrepanze")
    return stats


async def riconciliazione_completa(db, anno: int = 2026) -> Dict[str, Any]:
    """Esegue TUTTE le riconciliazioni in sequenza."""
    risultati = {}
    
    risultati["pagopa"] = await riconcilia_pagopa_con_banca(db)
    risultati["agenzia_entrate"] = await riconcilia_cartelle_agenzia_entrate(db)
    risultati["tari"] = await riconcilia_tari_con_banca(db)
    risultati["confronto_pos"] = await confronta_pos_corrispettivi(db, anno)
    
    logger.info(f"[RICONCILIAZIONE-COMPLETA] {risultati}")
    return risultati
