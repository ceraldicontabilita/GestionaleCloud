"""
Motore UNICO di import quietanze F24.

Usato da:
  - upload manuale multiplo (pagina F24, /api/f24/quietanze/upload-multiplo)
  - cartella unica Google Drive (via Documenti > Import)

Per ogni PDF: parsing (f24_parser.parse_quietanza_f24), dedup per impronta
SHA-256 (`pdf_hash`; l'MD5 resta in `pdf_hash_md5` solo per ritrovare la copia
identica su Drive, e per le righe scritte prima del passaggio a SHA-256,
che portano ancora l'MD5 in `pdf_hash`), salvataggio in `quietanze_f24` e
MATCHING AUTOMATICO con
gli F24 del commercialista (confronto per codice tributo + periodo +
importo esatto al centesimo e contribuente quando disponibile): match univoco →
F24 segnato pagato; nessun match → alert.
"""
import base64
import hashlib
import json
import logging
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.constants.canale_documento import canale_obbligatorio

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
    for tipo in sorted(tipi):
        anno_sid = anno_pag
        if tipo == 'RITENUTE':
            sid = f"ritenute_{anno_pag}_{mese_pag:02d}"
        elif tipo == 'INPS':
            sid = f"inps_{anno_pag}_{mese_pag:02d}"
        elif tipo == 'IVA':
            # Versamento il 16 del mese successivo alla competenza:
            # competenza = mese di pagamento - 1.
            mese_comp = mese_pag - 1 if mese_pag > 1 else 12
            anno_comp = anno_pag if mese_pag > 1 else anno_pag - 1
            anno_sid = anno_comp
            sid = f"iva_liq_{anno_comp}_{mese_comp:02d}"
        else:
            continue
        # Il calendario e' un modello generato in memoria (`genera_scadenze_anno`):
        # in archivio sta solo lo stato della scadenza, e la riga nasce qui alla
        # prima prova. Una scadenza gia' completata (a mano o da un'altra
        # quietanza) non si tocca.
        esistente = await db[COLL_CALENDARIO].find_one(
            {"id": sid, "anno": anno_sid}, {"_id": 0, "completato": 1})
        if esistente and esistente.get("completato"):
            continue
        res = await db[COLL_CALENDARIO].update_one(
            {"id": sid, "anno": anno_sid},
            {"$set": {
                "completato": True,
                "data_completamento": data_pagamento,
                "completato_da": "quietanza_f24",
                "quietanza_id": quietanza_id,
                "f24_id": f24.get("id"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        if res.modified_count or getattr(res, "upserted_id", None):
            marcate.append(sid)
    if marcate:
        logger.info(f"Quietanza {quietanza_id}: scadenze calendario completate: {marcate}")
    return marcate


def estrai_tributi_dettaglio(doc: dict) -> list:
    """Vista legacy basata sul normalizzatore fiscale canonico.

    Le righe INAIL si confrontano come «INAIL»: il modello F24 porta la
    causale («P») e la quietanza no, e con codici diversi lo stesso premio
    rendeva «non corrispondente» il modello di aprile 2026 (6.469,23 EUR).
    """
    return [
        {
            "codice": "INAIL" if row.get("section") == "INAIL" else row["tax_code"],
            "periodo": row["reference_period"] or "",
            "importo": row["debit_amount"],
            "importo_cents": row["debit_cents"],
        }
        for row in normalizza_righe_tributo(doc)
        if row["tax_code"] and row["debit_amount"] > 0
    ]


async def _riconcilia_quietanza_ader(
    db, *, content: bytes, filename: str, quietanza: dict,
) -> Dict[str, Any]:
    """Usa lo stesso motore di PagoPA/CBILL se la quietanza porta un ID AdeR."""
    from app.config import settings
    from app.services.fiscal_evidence import register_document
    from app.services.fiscal_payment_reconciliation import reconcile_fiscal_payment

    dg = quietanza.get("dati_generali") or {}
    document = await register_document(
        db, company_id=settings.FISCAL_COMPANY_ID, content=content,
        filename=filename, source=quietanza.get("fonte") or "quietanza_f24",
        source_ref=quietanza["id"], category="quietanza_f24",
    )
    return await reconcile_fiscal_payment(
        db, company_id=settings.FISCAL_COMPANY_ID,
        payment={
            "amount": quietanza.get("saldo"),
            "payment_date": quietanza.get("data_pagamento"),
            "identificativo_bolletta": (
                dg.get("identificativo_bolletta") or dg.get("codice_bolletta")
            ),
            "iuv": dg.get("iuv") or dg.get("identificativo_univoco_versamento"),
            "payment_module_code": (
                dg.get("payment_module_code") or dg.get("codice_modulo_pagamento")
            ),
            "cartella_number": dg.get("numero_cartella") or dg.get("cartella_number"),
            "protocollo_telematico": quietanza.get("protocollo_telematico"),
            "bank_verified": False,
        },
        source_type="QUIETANZA_F24", source_id=quietanza["id"],
        document_id=document.get("document_id"), version_id=document.get("id"),
    )


def _e_guscio_vuoto(quietanza: dict) -> bool:
    """Una «quietanza» salvata senza essere stata letta: niente protocollo, niente righe."""
    if str(quietanza.get("protocollo_telematico") or "").strip():
        return False
    if quietanza.get("status") == "eliminato":
        return False
    sezioni = ("sezione_erario", "sezione_inps", "sezione_regioni",
               "sezione_tributi_locali", "sezione_inail")
    return not any(quietanza.get(k) for k in sezioni)


async def trova_quietanza_per_impronta(db, *, sha256: str, md5: str | None = None) -> dict | None:
    """La quietanza con quel file: SHA-256 in `pdf_hash`, oppure (righe scritte prima
    del passaggio a SHA-256) l'MD5 in `pdf_hash` o in `pdf_hash_md5`."""
    condizioni = [{"pdf_hash": sha256}]
    if md5:
        condizioni += [{"pdf_hash": md5}, {"pdf_hash_md5": md5}]
    return await db[COLL_QUIETANZE].find_one({"$or": condizioni}, {"_id": 0})


async def promuovi_pdf_hash_sha256(db, quietanza: dict, *, sha256: str, md5: str) -> bool:
    """Una riga che porta ancora l'MD5 in `pdf_hash` passa a SHA-256, conservando
    l'MD5 in `pdf_hash_md5`. Chi ha gia' lo SHA-256 non si tocca."""
    if quietanza.get("pdf_hash") == sha256 and quietanza.get("pdf_hash_md5"):
        return False
    if quietanza.get("pdf_hash") not in (None, "", md5, sha256):
        return False  # un altro file: non e' la stessa impronta
    await db[COLL_QUIETANZE].update_one(
        {"id": quietanza["id"]},
        {"$set": {"pdf_hash": sha256, "pdf_hash_md5": md5,
                  "idempotency_key": f"quietanza_f24:{sha256}"}},
    )
    quietanza["pdf_hash"], quietanza["pdf_hash_md5"] = sha256, md5
    return True


def _firma_contenuto(parsed: dict, data_pagamento: Any, saldo: Any) -> str | None:
    """Impronta del contenuto fiscale: data, saldo e ogni riga (sezione, codice, periodo, importi)."""
    if not data_pagamento:
        return None
    righe = []
    for sezione in ("sezione_erario", "sezione_inps", "sezione_regioni",
                    "sezione_tributi_locali", "sezione_inail"):
        for r in parsed.get(sezione, []) or []:
            righe.append((
                sezione, str(r.get("codice_tributo") or r.get("causale") or r.get("codice_atto") or ""),
                str(r.get("periodo_raw") or r.get("periodo_riferimento") or ""),
                int(r.get("importo_debito_cents") or 0), int(r.get("importo_credito_cents") or 0),
            ))
    if not righe:
        return None
    dati = json.dumps([str(data_pagamento), saldo_cents({"saldo": saldo}), sorted(righe)])
    return "c1:" + hashlib.sha256(dati.encode()).hexdigest()


def _firma_righe(parsed: dict, saldo: Any) -> str | None:
    """Impronta di saldo e righe, SENZA data: lega la copia del Cassetto (senza data di
    pagamento) alla quietanza con la data, quando e' la stessa delega."""
    righe = []
    for sezione in ("sezione_erario", "sezione_inps", "sezione_regioni",
                    "sezione_tributi_locali", "sezione_inail"):
        for r in parsed.get(sezione, []) or []:
            righe.append((
                sezione, str(r.get("codice_tributo") or r.get("causale") or r.get("codice_atto") or ""),
                str(r.get("periodo_riferimento") or r.get("periodo_raw") or ""),
                int(r.get("importo_debito_cents") or 0), int(r.get("importo_credito_cents") or 0),
            ))
    if not righe:
        return None
    return "r1:" + hashlib.sha256(json.dumps([saldo_cents({"saldo": saldo}), sorted(righe)]).encode()).hexdigest()


def _quietanza_da_stampa_cassetto(content: bytes) -> dict | None:
    """Legge con il lettore dei modelli la stampa del Cassetto, che ha la forma del modello F24.

    Il lettore delle quietanze non ne trova le righe; il lettore dei modelli si': le righe e la
    quadratura sono le sue, la natura e' quella di una quietanza senza data di pagamento.
    """
    from app.services.parser_f24 import parse_f24_commercialista

    modello = parse_f24_commercialista(pdf_content=content)
    if not modello or modello.get("error"):
        return None
    dg = dict(modello.get("dati_generali") or {})
    dg.update({"natura_documento": "QUIETANZA_STAMPA_CASSETTO", "data_pagamento": None,
               "protocollo_telematico": ""})
    modello["dati_generali"] = dg
    return modello


async def importa_quietanza_bytes(
    db, content: bytes, filename: str, fonte: str = "upload_manuale",
    source_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Importa UNA quietanza PDF (bytes) con dedup e matching automatico.

    Ritorna un dict con:
      success, duplicate, quietanza_id, protocollo, saldo, data_pagamento,
      codici_tributo (conteggio), f24_matchati (lista), warning/error.
    """
    pdf_hash = hashlib.sha256(content).hexdigest()
    pdf_hash_md5 = hashlib.md5(content).hexdigest()  # noqa: S324 - solo per la copia identica su Drive
    source_metadata = dict(source_metadata or {})
    occurrence = {
        "source": fonte,
        "drive_file_id": source_metadata.get("drive_file_id"),
        "drive_parent_id": source_metadata.get("drive_parent_id"),
        "drive_path": source_metadata.get("drive_path"),
        "md5": pdf_hash_md5,
        "sha256": pdf_hash,
    }
    occurrence = {k: v for k, v in occurrence.items() if v not in (None, "")}

    # Dedup per impronta: la stessa quietanza (da Drive, email o upload)
    # non deve mai creare un doppione. Una riga scritta prima del passaggio a
    # SHA-256 porta l'MD5 in `pdf_hash`: si riconosce lo stesso e si promuove
    # (SHA-256 in `pdf_hash`, il vecchio valore in `pdf_hash_md5`).
    existing = await trova_quietanza_per_impronta(db, sha256=pdf_hash, md5=pdf_hash_md5)
    if existing:
        await promuovi_pdf_hash_sha256(db, existing, sha256=pdf_hash, md5=pdf_hash_md5)
    guscio = bool(existing) and _e_guscio_vuoto(existing)
    if existing and not guscio:
        await db[COLL_QUIETANZE].update_one(
            {"id": existing["id"]},
            {"$addToSet": {"source_occurrences": occurrence}},
        )
        ader = await _riconcilia_quietanza_ader(
            db, content=content, filename=filename, quietanza=existing,
        )
        return {"success": True, "duplicate": True,
                "quietanza_id": existing["id"], "filename": filename,
                "riconciliazione_ader": ader}

    try:
        from app.services.f24_parser import parse_quietanza_f24
        parsed = parse_quietanza_f24(pdf_content=content)
    except Exception as e:
        logger.error(f"Errore parsing quietanza {filename}: {e}")
        return {"success": False, "filename": filename, "error": f"Errore parsing: {e}"}

    if parsed and not parsed.get("error") and not normalizza_righe_tributo(parsed):
        from app.services.f24_parser import e_stampa_cassetto, extract_text_from_pdf

        if e_stampa_cassetto(extract_text_from_pdf(pdf_content=content)):
            parsed = _quietanza_da_stampa_cassetto(content) or parsed

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

    # Una ricevuta di mutuo o di bonifico passa la quadratura (zero righe, saldo
    # zero) ma non e' una quietanza F24: senza righe tributo non entra.
    righe_lette = normalizza_righe_tributo(parsed)
    if not any(r.get("tax_code") for r in righe_lette):
        logger.warning("Documento %s senza righe tributo: non e' una quietanza F24", filename)
        return {
            "success": False,
            "filename": filename,
            "error": "Nessuna riga tributo letta: non e' una quietanza F24",
            "stato_quietanza": "NON_QUIETANZA_F24",
        }

    dg = parsed.get("dati_generali", {})
    protocollo = dg.get("protocollo_telematico", "")
    saldo_quietanza = dg.get("saldo_delega", 0) or parsed.get("totali", {}).get("saldo_netto", 0)
    protocollo_condiviso: List[str] = []
    if str(protocollo or "").strip():
        # Stesso protocollo telematico e stesso saldo = stessa quietanza, anche
        # da un altro PDF. Con un saldo diverso e' un'altra delega uscita dallo
        # stesso PDF (il ravvedimento pagato lo stesso giorno): si importa e si
        # annota, perche' scartarla toglieva un pagamento vero.
        stesse = await db[COLL_QUIETANZE].find(
            {"protocollo_telematico": protocollo},
            {"_id": 0, "id": 1, "saldo": 1, "totali": 1, "dati_generali": 1},
        ).to_list(None)
        stessa = next((q for q in stesse if saldo_cents(q) == saldo_cents({"saldo": saldo_quietanza})), None)
        if stessa:
            await db[COLL_QUIETANZE].update_one(
                {"id": stessa["id"]}, {"$addToSet": {"source_occurrences": occurrence}},
            )
            return {"success": True, "duplicate": True, "quietanza_id": stessa["id"],
                    "filename": filename, "motivo": "stesso protocollo telematico e stesso saldo"}
        protocollo_condiviso = [q["id"] for q in stesse if q.get("id")]
    data_pagamento = dg.get("data_pagamento")
    codice_fiscale = dg.get("codice_fiscale", "")
    firma_contenuto = None
    firma_righe = None
    if not str(protocollo or "").strip():
        # La copia del Cassetto (righe e saldo, niente data) e la quietanza con la data
        # sono la stessa delega quando saldo e righe tornano al centesimo: l'abbinamento
        # parte all'arrivo del secondo pezzo, in qualunque ordine arrivino.
        firma_righe = _firma_righe(parsed, saldo_quietanza)
        if firma_righe:
            candidate = await db[COLL_QUIETANZE].find(
                {"saldo": saldo_quietanza, "protocollo_telematico": {"$in": ["", None]},
                 "status": {"$ne": "eliminato"}},
                {"_id": 0},
            ).to_list(50)
            # Due date diverse sono due pagamenti (anche con saldo e righe uguali): si abbina
            # solo se questo documento non ha la data, oppure e' la gemella a non averla.
            gemella = next((q for q in candidate
                            if (not guscio or q.get("id") != existing.get("id"))
                            and (not data_pagamento or not q.get("data_pagamento"))
                            and _firma_righe(q, q.get("saldo")) == firma_righe), None)
            if gemella and (not data_pagamento or gemella.get("data_pagamento")):
                # Gia' in archivio (con la data, o senza e nemmeno questa la porta): una sola.
                await db[COLL_QUIETANZE].update_one(
                    {"id": gemella["id"]}, {"$addToSet": {"source_occurrences": occurrence}},
                )
                return {"success": True, "duplicate": True, "quietanza_id": gemella["id"],
                        "filename": filename, "motivo": "stessa delega (saldo e righe uguali, senza protocollo)"}
            if gemella:
                # La gemella senza data riceve quella di questo documento: stesso id, stesse prove.
                existing, guscio = gemella, True
        # Senza protocollo (F24 del 2018-2019, modulo con i dati sovrapposti) la
        # delega e' il suo contenuto fiscale: data, saldo e righe. Stampata due
        # volte con PDF diversi e' una sola quietanza.
        firma_contenuto = _firma_contenuto(parsed, data_pagamento, saldo_quietanza)
        if firma_contenuto:
            stessa = await db[COLL_QUIETANZE].find_one(
                {"firma_contenuto": firma_contenuto}, {"_id": 0, "id": 1},
            )
            if stessa and not (guscio and stessa["id"] == existing["id"]):
                await db[COLL_QUIETANZE].update_one(
                    {"id": stessa["id"]}, {"$addToSet": {"source_occurrences": occurrence}},
                )
                if guscio:
                    # Il guscio vuoto e' la copia di una quietanza gia' letta: quarantena reversibile.
                    await db[COLL_QUIETANZE].update_one({"id": existing["id"]}, {"$set": {
                        "status": "eliminato", "motivo_quarantena": "stesso contenuto fiscale",
                        "doppione_di": stessa["id"],
                    }})
                return {"success": True, "duplicate": True, "quietanza_id": stessa["id"],
                        "filename": filename, "motivo": "stesso contenuto fiscale (senza protocollo)"}

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
        "pdf_hash": pdf_hash,
        "pdf_hash_md5": pdf_hash_md5,
        "idempotency_key": f"quietanza_f24:{pdf_hash}",
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
        "canale": canale_obbligatorio(fonte, drive_file_id=source_metadata.get("drive_file_id")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_occurrences": [occurrence],
    }
    if firma_contenuto:
        quietanza_doc["firma_contenuto"] = firma_contenuto
    if firma_righe:
        quietanza_doc["firma_righe"] = firma_righe
    if protocollo_condiviso:
        # Da confermare a vista: due deleghe col protocollo uguale e saldi diversi.
        quietanza_doc["protocollo_condiviso_con"] = protocollo_condiviso
    if source_metadata.get("drive_file_id"):
        quietanza_doc.update({
            "drive_file_id": source_metadata["drive_file_id"],
            "drive_parent_id": source_metadata.get("drive_parent_id"),
            "drive_path": source_metadata.get("drive_path"),
            "drive_md5": source_metadata.get("drive_md5") or pdf_hash_md5,
            "original_storage": "google_drive",
            "source_metadata": source_metadata,
        })
    else:
        quietanza_doc["pdf_data"] = base64.b64encode(content).decode("utf-8")
    if guscio:
        # Rileggo un guscio vuoto: stesso id e stessa provenienza, ora con i dati.
        file_id = existing["id"]
        quietanza_doc["id"] = file_id
        quietanza_doc["created_at"] = existing.get("created_at") or quietanza_doc["created_at"]
        quietanza_doc["source_occurrences"] = list(existing.get("source_occurrences") or []) + [occurrence]
        for chiave in ("drive_file_id", "drive_parent_id", "drive_path", "drive_md5",
                       "original_storage", "source_metadata", "fonte"):
            if existing.get(chiave) not in (None, ""):
                quietanza_doc[chiave] = existing[chiave]
        if existing.get("drive_file_id"):
            quietanza_doc.pop("pdf_data", None)
        await db[COLL_QUIETANZE].update_one({"id": file_id}, {"$set": quietanza_doc})
    else:
        await db[COLL_QUIETANZE].insert_one(quietanza_doc.copy())
    try:
        riconciliazione_ader = await _riconcilia_quietanza_ader(
            db, content=content, filename=filename, quietanza=quietanza_doc,
        )
    except Exception:
        logger.exception("Errore riconciliazione AdeR quietanza %s", file_id)
        riconciliazione_ader = {"matched": False, "reason": "errore_riconciliazione_ader"}

    # ── MATCHING AUTOMATICO CON F24 (v3) ─────────────────────────────────
    abbinamento = await abbina_quietanza_a_f24(db, quietanza_doc)
    f24_matchati = abbinamento["f24_matchati"]
    candidati_match = abbinamento["candidati"]
    f24_da_pagare_tutti = abbinamento["f24_esaminati"]

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
        "riconciliazione_ader": riconciliazione_ader,
    }
    # La quietanza e' una prova documentale distinta dal movimento banca. La
    # policy restituisce solo una proposta; nessuna scrittura definitiva viene
    # inserita dalla pipeline di import.
    try:
        from app.services.fiscal_accounting_policy import build_journal_proposal

        risultato["journal_proposal"] = build_journal_proposal(
            quietanza_doc,
            document_type="F24_QUIETANZA",
            evidence_state={
                "quietanza_validata": True,
                "pagato_documentalmente": True,
            },
            bank_state={"verified": False},
        )
    except Exception:
        logger.exception("Errore generazione journal proposal quietanza %s", file_id)
        risultato["journal_proposal"] = {
            "journal_proposal_status": "BLOCKED_REVIEW",
            "posting_allowed": False,
            "definitive_posting_created": False,
            "blockers": ["POLICY_CONTABILE_NON_DISPONIBILE"],
        }

    compensazione_totale = saldo_cents({"saldo": saldo_quietanza}) == 0 and bool(
        estrai_tributi_dettaglio(quietanza_doc))
    if not f24_matchati:
        # CASO 3 della specifica (la specifica del titolare (non è nel repository: vale il codice)):
        # esiste SOLO la quietanza → mai ricostruire l'F24 in automatico.
        # La quietanza resta registrata come prova di pagamento non associata
        # (stato dedicato) e nasce un alert bloccante che chiede il modello.
        # P2-I: distinguo "nessun F24 del soggetto" (vero Caso 3) da "un F24 del
        # soggetto esiste ma non combacia" (verificare importi/periodo).
        stato_senza_modello, _ = stato_quietanza_senza_modello(quietanza_doc, f24_da_pagare_tutti)
        if len(candidati_match) > 1:
            warning = "Più F24 coincidono al centesimo: associazione automatica sospesa."
            stato = "f24_ambiguo"
            stato_canonico = "QUIETANZA_PRESENTE_F24_AMBIGUO"
        elif stato_senza_modello == "f24_non_corrispondente":
            warning = "F24 presente ma non corrispondente: verificare importi/periodo/codici."
            stato = "f24_non_corrispondente"
            # stato canonico del prompt §9.3: F24 del soggetto esiste ma non combacia
            stato_canonico = "QUIETANZA_PRESENTE_F24_NON_CORRISPONDENTE"
        elif compensazione_totale:
            # Saldo zero: la quietanza e' gia' la prova completa (debiti pagati
            # coi crediti della stessa delega). Non si scarta e non si aspetta
            # alcun addebito in banca; il modello del commercialista e' utile
            # ma non blocca.
            warning = ("F24 a saldo zero: tributi pagati interamente in compensazione, "
                       "nessun addebito in banca atteso.")
            stato = "compensazione_totale"
            stato_canonico = "QUIETANZA_COMPENSAZIONE_TOTALE"
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
                "calcolo_fiscale_sospeso": stato != "compensazione_totale",
                "compensazione_totale": compensazione_totale,
            }},
        )
    if not f24_matchati and stato != "compensazione_totale":
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
    elif f24_matchati:
        await db[COLL_QUIETANZE].update_one(
            {"id": file_id},
            {"$set": {"stato_associazione": "associata", "calcolo_fiscale_sospeso": False,
                      "compensazione_totale": compensazione_totale}},
        )

    # Una quietanza con sanzioni da ravvedimento cerca subito l'F24 del
    # commercialista che ravvede (codici e periodi, mai l'importo).
    if any(t["codice"] in CODICI_RAVVEDIMENTO for t in estrai_tributi_dettaglio(quietanza_doc)):
        try:
            from app.services.f24_ravvedimento import collega_ravvedimenti

            esito_ravv = await collega_ravvedimenti(db)
            risultato["ravvedimento"] = {**esito_ravv["conteggi"], "scritti": esito_ravv["scritti"]}
        except Exception as exc:  # noqa: BLE001 - la quietanza resta importata
            logger.exception("Quietanza %s: F24 ravveduto non cercato (%s)", file_id, type(exc).__name__)
            risultato["ravvedimento"] = {"errore": type(exc).__name__}

    # La quietanza e' prova documentale sufficiente per le Ritenute anche
    # quando il modello del commercialista non c'e' (la ritenuta si paga col
    # 1040 della quietanza): si aggiornano adesso, e la ritenuta appena
    # versata manda l'avviso «pagata» con i riferimenti.
    try:
        from app.routers.ritenute import riconcilia_ritenute_esistenti

        risultato["ritenute_aggiornate"] = await riconcilia_ritenute_esistenti(db)
    except Exception as exc:  # noqa: BLE001 - la quietanza resta importata
        logger.exception("Quietanza %s: ritenute non aggiornate (%s)", file_id, type(exc).__name__)
        risultato["ritenute_aggiornate"] = {"errore": type(exc).__name__}

    # Scadenzario: la quietanza appena letta dice subito se il pagamento e'
    # nei termini, in ritardo, ravveduto.
    try:
        from app.services.scadenzario_tributi import aggiorna as aggiorna_scadenzario

        risultato["scadenzario"] = await aggiorna_scadenzario(db)
    except Exception as exc:  # noqa: BLE001 - la quietanza resta importata
        logger.exception("Quietanza %s: scadenzario non aggiornato (%s)", file_id, type(exc).__name__)
        risultato["scadenzario"] = {"errore": type(exc).__name__}

    # L'addebito I24 puo' essere gia' in banca: si cerca adesso, fra i soli
    # movimenti di pari importo, senza aspettare il giro dei 30 minuti.
    try:
        from app.services.f24_controllo_incrociato import riconcilia_f24_arrivato

        risultato["riscontro_banca"] = await riconcilia_f24_arrivato(db, saldo_quietanza)
    except Exception as exc:  # noqa: BLE001 - la quietanza resta importata
        logger.exception("Quietanza %s: addebito in banca non cercato (%s)", file_id, type(exc).__name__)
        risultato["riscontro_banca"] = {"errore": type(exc).__name__}

    return risultato


def saldo_cents(doc: dict) -> int:
    """Saldo del versamento in centesimi, da modello o quietanza; 0 se ignoto."""
    totali = doc.get("totali") or {}
    if totali.get("saldo_netto_cents") not in (None, ""):
        return int(totali["saldo_netto_cents"])
    for valore in (
        totali.get("saldo_netto"), doc.get("saldo"),
        (doc.get("dati_generali") or {}).get("saldo_delega"),
    ):
        if valore not in (None, ""):
            try:
                return int((Decimal(str(valore)) * 100).quantize(Decimal("1")))
            except (InvalidOperation, ValueError):
                continue
    return 0


def stato_quietanza_senza_modello(quietanza: dict, modelli: list) -> tuple:
    """«Non corrispondente» solo se c'e' un modello dello stesso contribuente
    con lo stesso saldo: e' quello da guardare. Altrimenti il modello manca, e
    la cosa da fare e' caricarlo. Prima bastava un qualunque F24 del
    contribuente, e 25 quietanze del 2026 senza modello risultavano
    «non corrispondenti» invece che «F24 mancante»."""
    dg = quietanza.get("dati_generali") or {}
    cf = str(quietanza.get("codice_fiscale") or dg.get("codice_fiscale") or "").strip().upper()
    saldo = saldo_cents(quietanza)
    for f24 in modelli:
        cf_f24 = str(
            (f24.get("dati_generali") or {}).get("codice_fiscale") or f24.get("codice_fiscale") or ""
        ).strip().upper()
        if saldo and saldo_cents(f24) == saldo and (not cf or not cf_f24 or cf == cf_f24):
            return ("f24_non_corrispondente", "QUIETANZA_PRESENTE_F24_NON_CORRISPONDENTE")
    return ("f24_mancante", "QUIETANZA_PRESENTE_F24_MANCANTE")


def _stato_banca_verificato(f24: dict) -> bool:
    return bool(
        f24.get("pagamento_verificato_banca")
        or str(f24.get("status") or "").lower() == "pagato"
    )


async def abbina_quietanza_a_f24(db, quietanza: dict) -> Dict[str, Any]:
    """Collega una quietanza al suo modello F24, se ce n'e' uno solo.

    Candidati: ogni F24 non eliminato **ancora senza quietanza**, qualunque sia
    il suo stato. Prima si guardavano solo i «da pagare»: un F24 gia'
    riscontrato in banca (aprile 2026, 6.469,23 EUR) non riceveva piu' la sua
    quietanza, e dalla tabella F24 si arrivava solo all'estratto conto. Il
    confronto e' esatto: codice, periodo e importo al centesimo di ogni riga,
    contribuente se noto; con due candidati non si collega niente.

    A un F24 gia' pagato in banca si aggiungono solo i campi della quietanza:
    ``patch_quietanza_associata`` lo riporterebbe «da verificare in banca».
    """
    file_id = quietanza["id"]
    dg = quietanza.get("dati_generali") or {}
    protocollo = quietanza.get("protocollo_telematico") or dg.get("protocollo_telematico") or ""
    data_pagamento = quietanza.get("data_pagamento") or dg.get("data_pagamento")
    saldo_quietanza = quietanza.get("saldo") or dg.get("saldo_delega") or 0
    cf_quietanza = str(quietanza.get("codice_fiscale") or dg.get("codice_fiscale") or "").strip().upper()

    tributi_quietanza = estrai_tributi_dettaglio(quietanza)
    # Righe come insieme di (codice, periodo, centesimi): lo stesso codice e
    # periodo puo' comparire piu' volte con importi diversi (3847 05/2026 per
    # 55,55 e 19,26 EUR, due righe comunali). Un dizionario per (codice,
    # periodo) teneva solo l'ultima e il modello di maggio 2026 risultava
    # «non corrispondente» pur coincidendo riga per riga.
    righe_quietanza = {
        (t["codice"], t["periodo"], t["importo_cents"]) for t in tributi_quietanza
    }
    saldo_q_cents = saldo_cents(quietanza)
    codici_ravv = []
    importo_ravv = 0
    for t in tributi_quietanza:
        if t["codice"] in CODICI_RAVVEDIMENTO:
            codici_ravv.append(t["codice"])
            importo_ravv += t["importo_cents"]

    esaminati = [
        f for f in await db[COLL_F24_COMMERCIALISTA].find(
            {}, {"_id": 0, "pdf_data": 0},
        ).to_list(5000)
        if not f.get("quietanza_id")
        and str(f.get("status") or "").lower() not in ("eliminato", "deleted", "archiviato")
    ]

    def _principali(f24: dict) -> list:
        return [
            item for item in estrai_tributi_dettaglio(f24)
            if item["codice"] not in CODICI_RAVVEDIMENTO
        ]

    def _combacia(f24: dict) -> bool:
        cf_f24 = str(
            (f24.get("dati_generali") or {}).get("codice_fiscale")
            or f24.get("codice_fiscale") or ""
        ).strip().upper()
        if cf_quietanza and cf_f24 and cf_quietanza != cf_f24:
            return False
        principali = _principali(f24)
        if not principali or not all(
            (item["codice"], item["periodo"], item["importo_cents"]) in righe_quietanza
            for item in principali
        ):
            return False
        # Il saldo chiude il confronto: righe uguali ma un saldo diverso non
        # sono lo stesso versamento. Con il ravvedimento la quietanza paga di
        # piu' (sanzioni e interessi), e il saldo non si confronta.
        saldo_f24 = saldo_cents(f24)
        return bool(codici_ravv) or not (saldo_f24 and saldo_q_cents) or saldo_f24 == saldo_q_cents

    candidati = [f for f in esaminati if _combacia(f)]
    esito: Dict[str, Any] = {
        "f24_matchati": [], "candidati": candidati, "f24_esaminati": esaminati,
    }
    if len(candidati) != 1:
        return esito

    f24 = candidati[0]
    principali = _principali(f24)
    campi_quietanza = patch_quietanza_associata(
        quietanza_id=file_id, protocollo=protocollo, data_quietanza=data_pagamento,
    )
    if _stato_banca_verificato(f24):
        campi_quietanza = {
            k: v for k, v in campi_quietanza.items()
            if k in ("quietanza_id", "protocollo_quietanza",
                     "data_pagamento_quietanza", "riconciliato_quietanza")
        }
    update_data = {
        **campi_quietanza,
        "match_tributi_trovati": len(principali),
        "match_tributi_totali": len(principali),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    is_ravveduto = len(codici_ravv) > 0
    if is_ravveduto:
        update_data["ravveduto"] = True
        update_data["importo_ravvedimento_cents"] = importo_ravv
        update_data["importo_ravvedimento"] = importo_ravv / 100
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
            matched_tributes=len(principali),
            total_tributes=len(principali),
        )
    except Exception:
        logger.exception(
            "Errore registrazione relazione quietanza %s / F24 %s", file_id, f24.get("id"),
        )
    # La quietanza dell'Agenzia e' la prova documentale del versamento: la
    # scadenza del calendario fiscale si segna completata con quella evidenza
    # (`completato_da=quietanza_f24`, distinta dalla conferma a mano e non
    # riapribile a mano). Il debito contabile resta aperto fino all'addebito.
    try:
        scadenze_completate = await _marca_scadenze_calendario(db, f24, data_pagamento, file_id)
    except Exception as exc:  # noqa: BLE001 - il collegamento quietanza-F24 resta scritto
        logger.exception("Quietanza %s: calendario fiscale non aggiornato (%s)", file_id, type(exc).__name__)
        scadenze_completate = []
    esito["f24_matchati"].append({
        "f24_id": f24["id"],
        "f24_filename": f24.get("file_name"),
        "importo_f24": (f24.get("totali") or {}).get("saldo_netto", 0),
        "importo_quietanza": saldo_quietanza,
        "tributi_matchati": f"{len(principali)}/{len(principali)}",
        "ravveduto": is_ravveduto,
        "importo_ravvedimento": importo_ravv / 100 if is_ravveduto else 0,
        "scadenze_completate": scadenze_completate,
    })
    return esito


async def ricollega_quietanze_orfane(db) -> Dict[str, Any]:
    """Ripassa le quietanze rimaste senza F24 (giro di riconciliazione).

    Un modello arrivato dopo la sua quietanza, o gia' pagato in banca quando
    la quietanza e' arrivata, si ricollega qui senza nessun comando a mano.
    """
    orfane = [
        q for q in await db[COLL_QUIETANZE].find(
            {"stato_associazione": {"$in": [
                "f24_mancante", "f24_non_corrispondente", "f24_ambiguo",
            ]}},
            {"_id": 0, "pdf_data": 0},
        ).to_list(2000)
        if not q.get("f24_associati")
    ]
    collegate = 0
    rietichettate = 0
    for quietanza in orfane:
        esito = await abbina_quietanza_a_f24(db, quietanza)
        if not esito["f24_matchati"]:
            # Lo stato dice cosa fare: caricare il modello o guardarne uno.
            if len(esito["candidati"]) > 1:
                continue
            stato, canonico = stato_quietanza_senza_modello(quietanza, esito["f24_esaminati"])
            if stato != quietanza.get("stato_associazione"):
                rietichettate += 1
                await db[COLL_QUIETANZE].update_one({"id": quietanza["id"]}, {"$set": {
                    "stato_associazione": stato, "stato_quietanza": canonico,
                }})
            continue
        collegate += 1
        # Come all'import riuscito: associata, e lo stato «F24 mancante» o
        # «non corrispondente» non vale piu'.
        await db[COLL_QUIETANZE].update_one({"id": quietanza["id"]}, {
            "$set": {"stato_associazione": "associata", "calcolo_fiscale_sospeso": False},
            "$unset": {"stato_quietanza": ""},
        })
        alert = await db[COLL_F24_ALERTS].find_one(
            {"tipo": "quietanza_senza_match", "quietanza_id": quietanza["id"],
             "status": "pending"},
            {"_id": 0, "id": 1},
        )
        if alert:
            await db[COLL_F24_ALERTS].update_one({"id": alert["id"]}, {"$set": {
                "status": "risolto",
                "risolto_at": datetime.now(timezone.utc).isoformat(),
                "risolto_da": "ricollega_quietanze_orfane",
            }})
    return {"orfane": len(orfane), "collegate": collegate, "rietichettate": rietichettate}


async def allinea_quietanze_saldo_zero(db) -> Dict[str, Any]:
    """Quietanze gia' importate a saldo zero con righe a debito: pagate in
    compensazione, non «F24 mancante». Solo per id, idempotente; chiude gli
    alert bloccanti «quietanza senza match» nati prima di questa regola."""
    docs = await db[COLL_QUIETANZE].find(
        {"stato_quietanza": {"$in": ["QUIETANZA_PRESENTE_F24_MANCANTE",
                                     "QUIETANZA_PRESENTE_F24_NON_CORRISPONDENTE"]}},
        {"_id": 0, "pdf_data": 0},
    ).to_list(5000)
    aggiornate = alert_chiusi = 0
    for q in docs:
        if saldo_cents(q) != 0 or not estrai_tributi_dettaglio(q):
            continue
        await db[COLL_QUIETANZE].update_one({"id": q["id"]}, {"$set": {
            "stato_associazione": "compensazione_totale",
            "stato_quietanza": "QUIETANZA_COMPENSAZIONE_TOTALE",
            "calcolo_fiscale_sospeso": False,
            "compensazione_totale": True,
        }})
        aggiornate += 1
        alert = await db[COLL_F24_ALERTS].find(
            {"quietanza_id": q["id"], "tipo": "quietanza_senza_match", "status": "pending"},
            {"_id": 0, "id": 1},
        ).to_list(20)
        for a in alert:
            await db[COLL_F24_ALERTS].update_one({"id": a["id"]}, {"$set": {
                "status": "resolved",
                "risolto_motivo": "F24 a saldo zero: pagato tutto in compensazione",
                "risolto_il": datetime.now(timezone.utc).isoformat(),
            }})
            alert_chiusi += 1
    return {"controllate": len(docs), "aggiornate": aggiornate, "alert_chiusi": alert_chiusi}
