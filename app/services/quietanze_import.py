"""
Motore UNICO di import quietanze F24.

Usato da:
  - upload manuale multiplo (pagina F24, /api/f24/quietanze/upload-multiplo)
  - ingest da Google Drive (drive_quietanze_ingest)

Per ogni PDF: parsing (f24_parser.parse_quietanza_f24), dedup per impronta
md5 (`pdf_hash`), salvataggio in `quietanze_f24` e MATCHING AUTOMATICO con
gli F24 del commercialista (confronto per codice tributo + periodo +
importo, tolleranza €0.50, ravvedimenti esclusi dal confronto): match →
F24 segnato pagato; nessun match → alert.
"""
import base64
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

COLL_QUIETANZE = "quietanze_f24"
COLL_F24_COMMERCIALISTA = "f24_commercialista"
COLL_F24_ALERTS = "f24_riconciliazione_alerts"

# Codici ravvedimento da escludere dal confronto tributi
CODICI_RAVVEDIMENTO = {
    '8901', '8902', '8903', '8904', '8906', '8907', '8911',
    '1989', '1990', '1991', '1992', '1993', '1994',
    '1507', '1508', '1509', '1510', '1511', '1512',
}


def estrai_tributi_dettaglio(doc: dict) -> list:
    """Estrae lista tributi con codice, periodo, importo (quietanza o F24)."""
    tributi = []
    for sezione in ["sezione_erario", "sezione_regioni", "sezione_tributi_locali"]:
        for item in doc.get(sezione, []):
            codice = item.get("codice_tributo", "")
            if codice:
                tributi.append({
                    "codice": codice,
                    "periodo": item.get("periodo_riferimento", "").strip(),
                    "importo": float(item.get("importo_debito", 0) or item.get("importo", 0) or 0)
                })
    for item in doc.get("sezione_inps", []):
        causale = item.get("causale", "")
        if causale:
            tributi.append({
                "codice": causale,
                "periodo": item.get("periodo_riferimento", "").strip(),
                "importo": float(item.get("importo_debito", 0) or item.get("importo", 0) or 0)
            })
    return tributi


async def importa_quietanza_bytes(
    db, content: bytes, filename: str, fonte: str = "upload_manuale"
) -> Dict[str, Any]:
    """Importa UNA quietanza PDF (bytes) con dedup e matching automatico.

    Ritorna un dict con:
      success, duplicate, quietanza_id, protocollo, saldo, data_pagamento,
      codici_tributo (conteggio), f24_matchati (lista), warning/error.
    """
    pdf_hash = hashlib.md5(content).hexdigest()

    # Dedup per impronta: la stessa quietanza (da Drive, email o upload)
    # non deve mai creare un doppione.
    existing = await db[COLL_QUIETANZE].find_one(
        {"pdf_hash": pdf_hash}, {"_id": 0, "id": 1}
    )
    if existing:
        return {"success": True, "duplicate": True,
                "quietanza_id": existing["id"], "filename": filename}

    try:
        from app.services.f24_parser import parse_quietanza_f24
        parsed = parse_quietanza_f24(pdf_content=content)
    except Exception as e:
        logger.error(f"Errore parsing quietanza {filename}: {e}")
        return {"success": False, "filename": filename, "error": f"Errore parsing: {e}"}

    if not parsed or (parsed.get("error")):
        return {"success": False, "filename": filename,
                "error": (parsed or {}).get("error", "Parsing fallito")}

    dg = parsed.get("dati_generali", {})
    protocollo = dg.get("protocollo_telematico", "")
    saldo_quietanza = dg.get("saldo_delega", 0) or parsed.get("totali", {}).get("saldo_netto", 0)
    data_pagamento = dg.get("data_pagamento")
    codice_fiscale = dg.get("codice_fiscale", "")

    codici_quietanza = set()
    for t in parsed.get("sezione_erario", []):
        if t.get("codice_tributo"):
            codici_quietanza.add(t["codice_tributo"])
    for t in parsed.get("sezione_inps", []):
        if t.get("causale"):
            codici_quietanza.add(t["causale"])
    for t in parsed.get("sezione_regioni", []):
        if t.get("codice_tributo"):
            codici_quietanza.add(t["codice_tributo"])
    for t in parsed.get("sezione_tributi_locali", []):
        if t.get("codice_tributo"):
            codici_quietanza.add(t["codice_tributo"])

    file_id = str(uuid.uuid4())
    quietanza_doc = {
        "id": file_id,
        "filename": filename,
        "pdf_data": base64.b64encode(content).decode("utf-8"),
        "pdf_hash": pdf_hash,
        "dati_generali": dg,
        "protocollo_telematico": protocollo,
        "data_pagamento": data_pagamento,
        "codice_fiscale": codice_fiscale,
        "saldo": saldo_quietanza,
        "sezione_erario": parsed.get("sezione_erario", []),
        "sezione_inps": parsed.get("sezione_inps", []),
        "sezione_regioni": parsed.get("sezione_regioni", []),
        "sezione_tributi_locali": parsed.get("sezione_tributi_locali", []),
        "sezione_inail": parsed.get("sezione_inail", []),
        "totali": parsed.get("totali", {}),
        "codici_tributo": list(codici_quietanza),
        "f24_associati": [],
        "fonte": fonte,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLL_QUIETANZE].insert_one(quietanza_doc.copy())

    # ── MATCHING AUTOMATICO CON F24 COMMERCIALISTA (v3) ──────────────────
    tributi_quietanza = estrai_tributi_dettaglio(parsed)
    quietanza_lookup = {}
    codici_ravv = []
    importo_ravv = 0.0
    for t in tributi_quietanza:
        quietanza_lookup[(t["codice"], t["periodo"])] = t["importo"]
        if t["codice"] in CODICI_RAVVEDIMENTO:
            codici_ravv.append(t["codice"])
            importo_ravv += t["importo"]

    f24_da_pagare = await db[COLL_F24_COMMERCIALISTA].find({
        "status": "da_pagare",
        "riconciliato": False
    }, {"_id": 0}).to_list(1000)

    f24_matchati = []
    for f24 in f24_da_pagare:
        tributi_f24 = estrai_tributi_dettaglio(f24)
        tributi_f24_principali = [t for t in tributi_f24 if t["codice"] not in CODICI_RAVVEDIMENTO]
        if not tributi_f24_principali:
            continue

        tributi_trovati = 0
        for t in tributi_f24_principali:
            key = (t["codice"], t["periodo"])
            if key in quietanza_lookup and abs(t["importo"] - quietanza_lookup[key]) <= 0.50:
                tributi_trovati += 1

        if tributi_trovati != len(tributi_f24_principali):
            continue

        # MATCH TROVATO
        saldo_f24 = f24.get("totali", {}).get("saldo_netto", 0)
        is_ravveduto = len(codici_ravv) > 0
        update_data = {
            "status": "pagato",
            "quietanza_id": file_id,
            "protocollo_quietanza": protocollo,
            "data_pagamento_quietanza": data_pagamento,
            "riconciliato_quietanza": True,
            "match_tributi_trovati": tributi_trovati,
            "match_tributi_totali": len(tributi_f24_principali),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if is_ravveduto:
            update_data["ravveduto"] = True
            update_data["importo_ravvedimento"] = round(importo_ravv, 2)
            update_data["codici_ravvedimento"] = codici_ravv

        await db[COLL_F24_COMMERCIALISTA].update_one({"id": f24["id"]}, {"$set": update_data})
        await db[COLL_QUIETANZE].update_one(
            {"id": file_id}, {"$push": {"f24_associati": f24["id"]}}
        )
        f24_matchati.append({
            "f24_id": f24["id"],
            "f24_filename": f24.get("file_name"),
            "importo_f24": saldo_f24,
            "importo_quietanza": saldo_quietanza,
            "tributi_matchati": f"{tributi_trovati}/{len(tributi_f24_principali)}",
            "ravveduto": is_ravveduto,
            "importo_ravvedimento": round(importo_ravv, 2) if is_ravveduto else 0,
        })
        break  # Un F24 per quietanza (one-to-one)

    risultato = {
        "success": True,
        "duplicate": False,
        "filename": filename,
        "quietanza_id": file_id,
        "protocollo": protocollo,
        "saldo": saldo_quietanza,
        "data_pagamento": data_pagamento,
        "codici_tributo": len(codici_quietanza),
        "f24_matchati": f24_matchati,
    }

    if not f24_matchati:
        risultato["warning"] = "Nessun F24 corrispondente trovato"
        alert = {
            "id": str(uuid.uuid4()),
            "tipo": "quietanza_senza_match",
            "quietanza_id": file_id,
            "message": f"Quietanza {filename} (€{saldo_quietanza:.2f}) non corrisponde a nessun F24 in attesa",
            "importo": saldo_quietanza,
            "protocollo": protocollo,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[COLL_F24_ALERTS].insert_one(alert.copy())

    return risultato
