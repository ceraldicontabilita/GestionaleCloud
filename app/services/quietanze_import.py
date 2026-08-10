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
COLL_F24_COMMERCIALISTA = "f24_unificato"  # unificato 13/07/2026
COLL_F24_ALERTS = "f24_riconciliazione_alerts"
COLL_CALENDARIO = "calendario_fiscale"

# Codici ravvedimento da escludere dal confronto tributi — fonte unica condivisa.
from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.services.accounting_relation_writers import record_f24_receipt_link
from app.services.f24_payment_evidence import patch_quietanza_associata
from app.services.f24_canonico import normalizza_righe_tributo

# Codici tributo → tipo di scadenza del calendario fiscale (app/routers/
# fiscalita_italiana.py::genera_scadenze_anno). Servono a segnare COMPLETATA
# la scadenza corrispondente quando arriva la quietanza dell'Agenzia Entrate.
CODICI_RITENUTE = {'1001', '1002', '1012', '1040', '1627', '3802', '3847', '3848'}
CODICI_IVA_MENSILE = {f'60{m:02d}' for m in range(1, 13)}  # 6001..6012


def _tipo_scadenza_da_codice(codice: str) -> str:
    """Mappa un codice tributo / causale F24 al tipo di scadenza del calendario.
    Ritorna 'RITENUTE' | 'IVA' | 'INPS' | '' (ignoto)."""
    c = (codice or '').strip().upper()
    if c in CODICI_RITENUTE:
        return 'RITENUTE'
    if c in CODICI_IVA_MENSILE:
        return 'IVA'
    # INPS: causali DM10 (contributi correnti), Cxx (gestione separata), 5100.
    # RC01 è regolarizzazione di periodo precedente (specifica F24): NON marca
    # la scadenza del mese corrente.
    if c == 'RC01':
        return ''
    if c.startswith('DM') or c == '5100' or (len(c) == 3 and c.startswith('C')):
        return 'INPS'
    return ''


async def _marca_scadenze_calendario(db, f24: dict, data_pagamento: str, quietanza_id: str) -> list:
    """Segna COMPLETATE nel calendario fiscale le scadenze pagate da questo F24.

    Approccio conservativo e reversibile (rispetta la specifica F24):
      - considera solo i tributi PRINCIPALI del F24 (ravvedimenti/RC01 esclusi);
      - dai codici ricava i TIPI coinvolti (ritenute/IVA/INPS);
      - usa la DATA DI PAGAMENTO della quietanza (dato certo dell'Agenzia
        Entrate) come mese di versamento: per ritenute/INPS la scadenza ha
        `data` = 16 di quel mese; per l'IVA la scadenza è di competenza del
        mese precedente (versamento il 16 del mese dopo);
      - marca solo scadenze non già completate; salva quietanza_id/f24_id per
        tracciabilità e reversibilità.
    Non tocca nulla se manca la data di pagamento o se il calendario non ha la
    scadenza (es. anno non ancora generato)."""
    if not data_pagamento or len(str(data_pagamento)) < 7:
        return []
    try:
        anno_pag = int(str(data_pagamento)[:4])
        mese_pag = int(str(data_pagamento)[5:7])
    except (ValueError, TypeError):
        return []

    tipi = set()
    for t in estrai_tributi_dettaglio(f24):
        if t['codice'] in CODICI_RAVVEDIMENTO:
            continue
        tipo = _tipo_scadenza_da_codice(t['codice'])
        if tipo:
            tipi.add(tipo)

    marcate = []
    for tipo in tipi:
        if tipo == 'RITENUTE':
            sid = f"ritenute_{anno_pag}_{mese_pag:02d}"
        elif tipo == 'INPS':
            sid = f"inps_{anno_pag}_{mese_pag:02d}"
        elif tipo == 'IVA':
            # Versamento il 16 del mese successivo alla competenza:
            # competenza = mese di pagamento - 1.
            mese_comp = mese_pag - 1 if mese_pag > 1 else 12
            anno_comp = anno_pag if mese_pag > 1 else anno_pag - 1
            sid = f"iva_liq_{anno_comp}_{mese_comp:02d}"
        else:
            continue
        res = await db[COLL_CALENDARIO].update_one(
            {"id": sid, "completato": {"$ne": True}},
            {"$set": {
                "completato": True,
                "data_completamento": data_pagamento,
                "completato_da": "quietanza_f24",
                "quietanza_id": quietanza_id,
                "f24_id": f24.get("id"),
            }},
        )
        if res.modified_count:
            marcate.append(sid)
    if marcate:
        logger.info(f"Quietanza {quietanza_id}: scadenze calendario completate: {marcate}")
    return marcate


def estrai_tributi_dettaglio(doc: dict) -> list:
    """Vista legacy basata sul normalizzatore fiscale canonico."""
    return [
        {
            "codice": row["tax_code"],
            "periodo": row["reference_period"] or "",
            "importo": row["debit_amount"],
        }
        for row in normalizza_righe_tributo(doc)
        if row["tax_code"] and row["debit_amount"] > 0
    ]


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

    validation = parsed.get("validazione") or {}
    if not validation.get("saldo_quadrato"):
        difference = validation.get("differenza_saldo")
        logger.warning(
            "Quietanza %s non quadrata (differenza=%s): importazione sospesa",
            filename,
            difference,
        )
        return {
            "success": False,
            "filename": filename,
            "error": f"Saldo F24 non quadrato (differenza {difference})",
            "stato_quietanza": "PARSING_DA_VERIFICARE",
            "validazione": validation,
        }

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
        "validazione": validation,
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
            **patch_quietanza_associata(
                quietanza_id=file_id,
                protocollo=protocollo,
                data_quietanza=data_pagamento,
            ),
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
        try:
            await record_f24_receipt_link(
                db,
                f24=f24,
                receipt_id=file_id,
                protocol=protocollo,
                amount=saldo_quietanza,
                matched_tributes=tributi_trovati,
                total_tributes=len(tributi_f24_principali),
            )
        except Exception:
            logger.exception(
                "Errore registrazione relazione quietanza %s / F24 %s",
                file_id,
                f24.get("id"),
            )
        # La quietanza collega il documento, ma la scadenza diventa completata
        # solo dopo l'addebito bancario. Prima il calendario veniva chiuso qui,
        # creando falsi pagamenti.
        scadenze_completate = []
        f24_matchati.append({
            "f24_id": f24["id"],
            "f24_filename": f24.get("file_name"),
            "importo_f24": saldo_f24,
            "importo_quietanza": saldo_quietanza,
            "tributi_matchati": f"{tributi_trovati}/{len(tributi_f24_principali)}",
            "ravveduto": is_ravveduto,
            "importo_ravvedimento": round(importo_ravv, 2) if is_ravveduto else 0,
            "scadenze_completate": scadenze_completate,
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
        # CASO 3 della specifica (memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md):
        # esiste SOLO la quietanza → mai ricostruire l'F24 in automatico.
        # La quietanza resta registrata come prova di pagamento non associata
        # (stato dedicato) e nasce un alert bloccante che chiede il modello.
        # P2-I: distinguo "nessun F24 del soggetto" (vero Caso 3) da "un F24 del
        # soggetto esiste ma non combacia" (verificare importi/periodo).
        cf_norm = (codice_fiscale or "").strip().upper()
        esiste_f24_soggetto = bool(cf_norm) and any(
            (((f.get("dati_generali", {}) or {}).get("codice_fiscale") or f.get("codice_fiscale") or "")
             .strip().upper() == cf_norm)
            for f in f24_da_pagare
        )
        if esiste_f24_soggetto:
            warning = "F24 presente ma non corrispondente: verificare importi/periodo/codici."
            stato = "f24_non_corrispondente"
            # stato canonico del prompt §9.3: F24 del soggetto esiste ma non combacia
            stato_canonico = "QUIETANZA_PRESENTE_F24_NON_CORRISPONDENTE"
        else:
            warning = "F24 mancante — prego caricare il modello F24 corrispondente."
            stato = "f24_mancante"
            # stato canonico del prompt §9.3 (regola cardine: mai ricostruire l'F24)
            stato_canonico = "QUIETANZA_PRESENTE_F24_MANCANTE"
        risultato["warning"] = warning
        risultato["stato_quietanza"] = stato_canonico
        await db[COLL_QUIETANZE].update_one(
            {"id": file_id},
            {"$set": {
                "stato_associazione": stato,
                "stato_quietanza": stato_canonico,
                "calcolo_fiscale_sospeso": True,
            }},
        )
        alert = {
            "id": str(uuid.uuid4()),
            "tipo": "quietanza_senza_match",
            "bloccante": True,
            "quietanza_id": file_id,
            "message": (
                f"{warning} La quietanza {filename} (€{saldo_quietanza:.2f}) conferma il "
                f"pagamento ma senza il modello F24 corretto la classificazione di codici, "
                f"causali, crediti e periodi resta sospesa."
            ),
            "importo": saldo_quietanza,
            "protocollo": protocollo,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[COLL_F24_ALERTS].insert_one(alert.copy())
    else:
        await db[COLL_QUIETANZE].update_one(
            {"id": file_id},
            {"$set": {"stato_associazione": "associata", "calcolo_fiscale_sospeso": False}},
        )

        # La quietanza e' prova documentale sufficiente per Ritenute e IVA
        # anche se l'addebito bancario non e' ancora verificato. Ritenute
        # persiste lo stato: va quindi aggiornata nello stesso flusso di import,
        # senza richiedere un secondo clic nella pagina dedicata.
        try:
            from app.routers.ritenute import riconcilia_ritenute_esistenti

            risultato["ritenute_aggiornate"] = await riconcilia_ritenute_esistenti(db)
        except Exception:
            logger.exception("Errore aggiornamento ritenute dopo quietanza %s", file_id)
            risultato["ritenute_aggiornate"] = {"errore": True}

    return risultato
