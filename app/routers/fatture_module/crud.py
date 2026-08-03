"""
Fatture Module - CRUD e Visualizzazione fatture.
"""
from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import base64
import calendar
import re

from app.database import Database
from .common import COL_FORNITORI, COL_FATTURE_RICEVUTE, COL_DETTAGLIO_RIGHE, COL_ALLEGATI, logger
from .helpers import generate_invoice_html


def _safe_year(value: Any) -> Optional[int]:
    """Estrae l'anno (int) da una data in formato datetime/ISO/'YYYY-MM-DD'.
    Ritorna None se il valore è vuoto o non parsabile."""
    if not value:
        return None
    if hasattr(value, "year"):
        try:
            return int(value.year)
        except Exception:
            return None
    s = str(value).strip()
    if len(s) >= 4 and s[:4].isdigit():
        try:
            return int(s[:4])
        except ValueError:
            return None
    return None


def _normalizza_da_invoices(doc: dict) -> dict:
    """Mappa un documento della collection `invoices` nel formato unificato archivio.

    NOTA: in `invoices` convivono due schemi — quello inglese (upload XML,
    Drive: total_amount/invoice_number/...) e quello italiano scritto da
    fatture_module/import_xml.py (importo_totale/numero_documento/...).
    Ogni campo va letto con entrambi i nomi, altrimenti i documenti
    dell'altro schema appaiono con importo 0 e colonne vuote."""
    try:
        importo_totale = float(doc.get("total_amount") or doc.get("importo_totale") or 0)
    except (ValueError, TypeError):
        importo_totale = 0.0
    try:
        imponibile = float(doc.get("taxable_amount") or doc.get("imponibile") or 0)
    except (ValueError, TypeError):
        imponibile = 0.0
    try:
        iva = float(doc.get("vat_amount") or doc.get("iva") or 0)
    except (ValueError, TypeError):
        iva = 0.0
    if not imponibile and importo_totale > 0:
        imponibile = round(importo_totale / 1.22, 2)
        iva = round(importo_totale - imponibile, 2)

    stato_raw = doc.get("stato", "importata")
    pagato = bool(
        doc.get("pagato")
        or stato_raw in ("pagata", "paid")
        or doc.get("payment_status") == "paid"
    )
    created_at = doc.get("imported_at")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

    data_doc = doc.get("invoice_date") or doc.get("data_documento")
    return {
        "id": doc.get("id", ""),
        "numero_documento": doc.get("invoice_number") or doc.get("numero_documento"),
        "tipo_documento": doc.get("tipo_documento") or doc.get("document_type") or "TD01",
        "tipo_documento_desc": doc.get("tipo_documento_desc") or "",
        "data_documento": data_doc,
        "importo_totale": importo_totale,
        "imponibile": imponibile,
        "iva": iva,
        "fornitore_ragione_sociale": (doc.get("supplier_name")
                                      or doc.get("cedente_denominazione")
                                      or doc.get("fornitore_ragione_sociale")),
        "fornitore_partita_iva": doc.get("supplier_vat") or doc.get("fornitore_partita_iva"),
        "stato": "pagata" if pagato else stato_raw,
        "metodo_pagamento": doc.get("payment_method") or doc.get("metodo_pagamento"),
        "metodo_pagamento_effettivo": doc.get("payment_method") or doc.get("metodo_pagamento"),
        "pagato": pagato,
        "riconciliato": bool(doc.get("riconciliato")),
        "prima_nota_cassa_id": doc.get("prima_nota_cassa_id"),
        "prima_nota_banca_id": doc.get("prima_nota_banca_id"),
        "has_pdf": False,
        "email_associata": doc.get("email_from"),
        "anno": doc.get("anno") or _safe_year(data_doc),
        "created_at": created_at,
        "data_pagamento": doc.get("data_pagamento"),
        "fonte": doc.get("fonte", "aruba_pec"),
        "_xml_filename": doc.get("xml_filename"),   # usato solo per dedup
    }


def _normalizza_da_fatture_passive(doc: dict) -> dict:
    """Mappa un documento della collection `fatture_passive` nel formato unificato archivio."""
    try:
        importo_totale = float(doc.get("importo_totale") or 0)
    except (ValueError, TypeError):
        importo_totale = 0.0
    try:
        imponibile = float(doc.get("imponibile") or 0)
    except (ValueError, TypeError):
        imponibile = 0.0
    try:
        iva = float(doc.get("iva") or 0)
    except (ValueError, TypeError):
        iva = 0.0
    if not imponibile and importo_totale > 0:
        imponibile = round(importo_totale / 1.22, 2)
        iva = round(importo_totale - imponibile, 2)

    stato_raw = doc.get("stato", "da_confermare")
    pagato = bool(doc.get("pagato") or stato_raw == "pagata")
    created_at = doc.get("created_at")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

    return {
        "id": doc.get("dedup_key", ""),
        "numero_documento": doc.get("numero"),
        "tipo_documento": doc.get("tipo_documento") or "TD01",
        "tipo_documento_desc": doc.get("tipo_documento_desc") or "",
        "data_documento": doc.get("data"),
        "importo_totale": importo_totale,
        "imponibile": imponibile,
        "iva": iva,
        "fornitore_ragione_sociale": doc.get("fornitore_denominazione"),
        "fornitore_partita_iva": doc.get("fornitore_piva"),
        "stato": "pagata" if pagato else stato_raw,
        "metodo_pagamento": doc.get("metodo_pagamento"),
        "metodo_pagamento_effettivo": doc.get("metodo_pagamento"),
        "pagato": pagato,
        "riconciliato": bool(doc.get("riconciliato")),
        "prima_nota_cassa_id": doc.get("prima_nota_cassa_id"),
        "prima_nota_banca_id": doc.get("prima_nota_banca_id"),
        "has_pdf": False,
        "email_associata": None,
        "anno": doc.get("anno") or _safe_year(doc.get("data")),
        "created_at": created_at,
        "data_pagamento": doc.get("data_pagamento"),
        "fonte": doc.get("source", "pec_auto"),
        "_xml_filename": doc.get("xml_filename"),   # usato solo per dedup
    }


async def get_archivio_fatture(
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None),
    fornitore_piva: Optional[str] = Query(None),
    fornitore_nome: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(default=200, le=6000),
    skip: int = Query(default=0)
) -> Dict[str, Any]:
    """
    Archivio Fatture Ricevute — legge da ENTRAMBE le collection:
      - invoices (111 doc: fatture XML da Aruba PEC, schema inglese)
      - fatture_passive (73 doc: formato gestionale, schema italiano)
    I risultati vengono unificati, deduplicati per xml_filename e ordinati per data.
    Gli insert/upsert da upload XML restano su fatture_passive (invariati).
    """
    db = Database.get_db()

    # ── Costruisci filtri per `invoices` ─────────────────────────────────────
    # Bug corretto 15/07/2026: una fattura "eliminata" da DELETE /api/fatture/{id}
    # è di norma un soft-delete (CascadeOperations.delete_fattura_cascade imposta
    # status/entity_status="deleted"), ma questa query non escludeva mai quello
    # stato — una fattura "eliminata" poteva ricomparire qui nonostante il
    # messaggio di conferma dicesse che l'eliminazione è irreversibile.
    q_inv: dict = {"entity_status": {"$ne": "deleted"}, "status": {"$ne": "deleted"}}
    if anno:
        # I doc di import_xml (schema italiano) non hanno `anno` né `invoice_date`:
        # filtra su entrambi gli schemi usando $and per non collidere con gli
        # $or di ricerca/fornitore più sotto.
        q_inv.setdefault("$and", []).append({"$or": [
            {"anno": anno},
            {"data_documento": {"$regex": f"^{anno}"}},
            # Fatture da Drive/bulk (schema inglese) importate prima del
            # backfill di `anno`: hanno solo invoice_date.
            {"invoice_date": {"$regex": f"^{anno}"}},
        ]})
        if mese:
            mese_str = str(mese).zfill(2)
            last_day = calendar.monthrange(anno, mese)[1]
            intervallo = {
                "$gte": f"{anno}-{mese_str}-01",
                "$lte": f"{anno}-{mese_str}-{last_day:02d}"
            }
            q_inv["$and"].append({"$or": [
                {"invoice_date": intervallo},
                {"data_documento": intervallo},
            ]})
    if fornitore_piva:
        q_inv["supplier_vat"] = {"$regex": fornitore_piva.strip(), "$options": "i"}
    if fornitore_nome:
        q_inv["$or"] = [
            {"supplier_name": {"$regex": fornitore_nome.strip(), "$options": "i"}},
            {"cedente_denominazione": {"$regex": fornitore_nome.strip(), "$options": "i"}}
        ]
    if stato:
        # I doc di `invoices` usano DUE schemi: stato/pagato (it) e status (en).
        # Il filtro deve coprirli entrambi, altrimenti "Importate" è sempre
        # vuoto e "Pagate" perde le fatture marcate solo con status="paid".
        if stato in ("pagata", "paid"):
            q_inv.setdefault("$and", []).append({"$or": [
                {"stato": {"$in": ["pagata", "paid"]}},
                {"status": "paid"},
                {"pagato": True},
                {"stato_pagamento": "pagata"},
            ]})
        elif stato in ("importata", "imported"):
            q_inv.setdefault("$and", []).append({
                "stato": {"$nin": ["pagata", "paid"]},
                "status": {"$ne": "paid"},
                "pagato": {"$ne": True},
                "stato_pagamento": {"$ne": "pagata"},
            })
        elif stato == "anomala":
            q_inv.setdefault("$and", []).append({"$or": [
                {"$and": [
                    {"$or": [{"total_amount": {"$lte": 0}}, {"total_amount": {"$exists": False}}]},
                    {"$or": [{"importo_totale": {"$lte": 0}}, {"importo_totale": {"$exists": False}}]},
                ]},
                {"$and": [
                    {"invoice_number": {"$in": [None, ""]}},
                    {"numero_documento": {"$in": [None, ""]}},
                ]},
            ]})
        else:
            q_inv["stato"] = stato
    if search:
        q_inv["$or"] = [
            {"invoice_number": {"$regex": search, "$options": "i"}},
            {"supplier_name": {"$regex": search, "$options": "i"}},
            {"supplier_vat": {"$regex": search, "$options": "i"}},
        ]

    # ── Consolidamento §5.4: `fatture_passive` migrata in `invoices`. La lettura
    #    a due sorgenti (con dedup runtime) è stata rimossa: si legge SOLO la
    #    canonica `invoices`. I filtri q_fp restano solo per non rompere codice a
    #    valle ma non vengono più usati per interrogare la legacy.
    q_fp: dict = {}
    if anno:
        q_fp["anno"] = anno
        if mese:
            mese_str = str(mese).zfill(2)
            last_day = calendar.monthrange(anno, mese)[1]
            q_fp["data"] = {
                "$gte": f"{anno}-{mese_str}-01",
                "$lte": f"{anno}-{mese_str}-{last_day:02d}"
            }
    if fornitore_piva:
        q_fp["fornitore_piva"] = {"$regex": fornitore_piva.strip(), "$options": "i"}
    if fornitore_nome:
        q_fp["fornitore_denominazione"] = {"$regex": fornitore_nome.strip(), "$options": "i"}
    if stato:
        q_fp["stato"] = stato
    if search:
        q_fp["$or"] = [
            {"numero": {"$regex": search, "$options": "i"}},
            {"fornitore_denominazione": {"$regex": search, "$options": "i"}},
            {"fornitore_piva": {"$regex": search, "$options": "i"}},
        ]

    # ── Legge SOLO la collezione canonica `invoices` (§5.4) ──────────────────
    docs_inv_raw = await db["invoices"].find(q_inv, {"_id": 0}).sort("invoice_date", -1).to_list(6000)

    # ── Normalizza ────────────────────────────────────────────────────────────
    normalized_inv = [_normalizza_da_invoices(d) for d in docs_inv_raw]
    normalized_fp = []  # nessuna seconda sorgente: fatture_passive è consolidata in invoices

    # ── Unisci e ordina per data_documento decrescente ────────────────────────
    all_fatture = normalized_inv + normalized_fp

    # ── Dedup di CONTENUTO: stessa fattura importata più volte da canali
    # diversi (stesso numero + P.IVA + data + importo). Tiene il documento
    # "migliore" (con prima nota / pagato), nasconde i doppioni.
    def _chiave_contenuto(f: dict):
        numero = str(f.get("numero_documento") or "").strip().upper()
        piva = str(f.get("fornitore_partita_iva") or "").strip()
        if not numero or not piva:
            return None  # dati incompleti: non deduplicare
        return (numero, piva, str(f.get("data_documento") or "")[:10],
                round(float(f.get("importo_totale") or 0), 2))

    visti: dict = {}
    unici = []
    for f in all_fatture:
        k = _chiave_contenuto(f)
        if k is None:
            unici.append(f)
            continue
        if k not in visti:
            visti[k] = f
            unici.append(f)
        else:
            cur = visti[k]
            f_ha_pn = bool(f.get("prima_nota_cassa_id") or f.get("prima_nota_banca_id") or f.get("pagato"))
            cur_ha_pn = bool(cur.get("prima_nota_cassa_id") or cur.get("prima_nota_banca_id") or cur.get("pagato"))
            if f_ha_pn and not cur_ha_pn:
                # sostituisci il doc mostrato con quello collegato alla prima nota
                idx = unici.index(cur)
                unici[idx] = f
                visti[k] = f
    all_fatture = unici
    all_fatture.sort(
        key=lambda f: f.get("data_documento") or "",
        reverse=True
    )

    # Rimuovi il campo interno di dedup prima di rispondere
    for f in all_fatture:
        f.pop("_xml_filename", None)

    # ── Arricchisci con metodo_pagamento DEL FORNITORE ────────────────────────
    # Legge l'anagrafica fornitori per P.IVA e popola `fornitore_metodo_pagamento`.
    # Così il frontend può decidere di mostrare un solo bottone (Cassa o Banca)
    # quando il fornitore ha un metodo predefinito.
    # NOTE: nel doc fattura il campo P.IVA è `supplier_vat` (campi standard
    # FatturaPA importati). `fornitore_partita_iva` non esiste, era un bug.
    pive = list({
        (f.get("supplier_vat") or f.get("fornitore_partita_iva") or "").strip()
        for f in all_fatture
        if (f.get("supplier_vat") or f.get("fornitore_partita_iva"))
    })
    if pive:
        fornitori_docs = await db["fornitori"].find(
            {"$or": [
                {"partita_iva": {"$in": pive}},
                {"piva": {"$in": pive}},
                {"vat_number": {"$in": pive}},
            ]},
            {"_id": 0, "partita_iva": 1, "piva": 1, "vat_number": 1,
             "metodo_pagamento": 1, "metodo_pagamento_predefinito": 1, "ragione_sociale": 1}
        ).to_list(len(pive) * 3 + 10)
        # MOTORE UNICO: il metodo esposto al frontend è quello CANONICO
        # (cassa/banca/misto) del motore prima nota — prima si mandava il
        # valore grezzo (es. 'da_configurare' in metodo_pagamento_predefinito)
        # e il badge in Fatture diceva "senza metodo" mentre Fornitori
        # mostrava Banca: incoerenza segnalata dall'utente il 10/07.
        from app.engines.prima_nota_engine import normalizza_metodo_pagamento
        map_metodo = {}
        map_nome = {}
        for fdoc in fornitori_docs:
            # `metodo_pagamento` è il valore canonico e modificabile dalla
            # scheda Fornitori. Il campo `metodo_pagamento_predefinito` è
            # legacy e deve essere usato soltanto come fallback: altrimenti
            # un vecchio valore "cassa" continua a prevalere su "misto".
            metodo = (
                normalizza_metodo_pagamento(fdoc.get("metodo_pagamento"))
                or normalizza_metodo_pagamento(fdoc.get("metodo_pagamento_predefinito"))
                or ""
            )
            for key in (fdoc.get("partita_iva"), fdoc.get("piva"), fdoc.get("vat_number")):
                piva = (key or "").strip()
                if not piva:
                    continue
                # Un doppione del fornitore SENZA metodo non deve cancellare
                # il metodo del record buono con la stessa P.IVA
                if metodo or piva not in map_metodo:
                    map_metodo[piva] = metodo
                if fdoc.get("ragione_sociale") and piva not in map_nome:
                    map_nome[piva] = fdoc["ragione_sociale"]
        for f in all_fatture:
            piva = (f.get("supplier_vat") or f.get("fornitore_partita_iva") or "").strip()
            f["fornitore_metodo_pagamento"] = map_metodo.get(piva, "")
            # Se il nome fornitore non era stato salvato sulla fattura (es. persona
            # fisica non gestita dal vecchio parser), recuperalo dall'anagrafica.
            if not (f.get("fornitore_ragione_sociale") or "").strip() and piva in map_nome:
                f["fornitore_ragione_sociale"] = map_nome[piva]

    total = len(all_fatture)

    # Applica paginazione
    paginated = all_fatture[skip: skip + limit]

    return {"fatture": paginated, "total": total, "limit": limit, "skip": skip}


# Il foglio ASSO è disegnato a larghezza FISSA (#fattura-elettronica ha
# min-width:800px e le tabelle sono a 800px): un min-width vince su max-width,
# quindi non si può "refloware" senza rompere il layout. Su mobile lo si fa
# quindi rientrare dicendo al browser che la pagina è larga ~820px: il browser
# la rimpicciolisce per farla stare nello schermo (adattivo a ogni telefono),
# mantenendo intatto l'impaginato. Su desktop il viewport è ininfluente.
_META_SCALE_TO_FIT = (
    "<meta name='viewport' content='width=820'>"
    "<style>html,body{margin:0!important;padding:0!important;min-width:820px!important;}"
    "body{display:flex!important;justify-content:center!important;align-items:flex-start!important;}"
    "#fattura-container,#fattura-elettronica{width:800px!important;max-width:800px!important;"
    "margin-left:auto!important;margin-right:auto!important;flex:0 0 800px!important;}"
    "img{max-width:100%;height:auto;}</style>"
)

# Per l'HTML di fallback (semplice, non a 800px fissi): reflow classico.
_META_REFLOW = (
    "<meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=5'>"
    "<style>"
    "html{-webkit-text-size-adjust:100%;}"
    "*,*::before,*::after{box-sizing:border-box;}"
    "body{margin:0!important;padding:10px!important;max-width:100%;overflow-x:auto;}"
    "img{max-width:100%;height:auto;}"
    "table{max-width:100%!important;border-collapse:collapse;}"
    "td,th{word-break:break-word;overflow-wrap:anywhere;}"
    "</style>"
)


def _rendi_fattura_responsive(html_str: str) -> str:
    """Inserisce il viewport giusto nell'HTML della fattura perché stia nello
    schermo del telefono. Se è il foglio ASSO a larghezza fissa (800px) usa lo
    "scale-to-fit" (rimpicciolisce mantenendo il layout); altrimenti il reflow."""
    if not html_str:
        return html_str
    lower = html_str.lower()
    fisso_800 = ("fattura-elettronica" in lower
                 or "min-width: 800px" in lower or "min-width:800px" in lower)
    meta = _META_SCALE_TO_FIT if fisso_800 else _META_REFLOW

    if "<head" in lower:
        idx = lower.find("<head")
        chiusura = html_str.find(">", idx)
        if chiusura != -1:
            return html_str[:chiusura + 1] + meta + html_str[chiusura + 1:]
    if "<html" in lower:
        idx = lower.find("<html")
        chiusura = html_str.find(">", idx)
        if chiusura != -1:
            return (html_str[:chiusura + 1] + "<head>" + meta + "</head>"
                    + html_str[chiusura + 1:])
    return (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        + meta + "</head><body>" + html_str + "</body></html>"
    )


async def storia_fattura(fattura_id: str) -> Dict[str, Any]:
    """Storia cronologica della fattura: tutte le operazioni registrate dietro
    di essa (importata, pagata, IVA, riconciliazioni, snapshot pre-azzeramento…)
    e lo stato derivato corrente. Sopravvive all'azzeramento (chiave invoice_key)."""
    from app.services import storia_fatture as _storia
    db = Database.get_db()
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0, "invoice_key": 1,
                                                                 "invoice_number": 1})
    if not fattura:
        fattura = await db[COL_FATTURE_RICEVUTE].find_one(
            {"id": fattura_id}, {"_id": 0, "invoice_key": 1, "invoice_number": 1})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    key = fattura.get("invoice_key")
    st = await _storia.storia(db, key) if key else None
    return {
        "fattura_id": fattura_id,
        "invoice_key": key,
        "operazioni": (st or {}).get("operazioni", []),
        "stato_corrente": (st or {}).get("stato_corrente", {}),
        "ha_storia": bool(st),
    }


async def _trova_fattura_e_xml_originale(fattura_id: str) -> tuple[Optional[dict], Optional[bytes]]:
    """Cerca la fattura e recupera l'XML FatturaPA originale (bytes, gia'
    ripulito dall'eventuale busta .p7m), se disponibile. Punto UNICO usato
    sia dalla vista renderizzata (view_fattura_assoinvoice) sia dal download
    del file grezzo (download_xml_originale) — cosi' le due viste concordano
    sempre su cosa sia "l'originale" di una fattura.

    1. Cerca la fattura in `invoices` (poi fallback COL_FATTURE_RICEVUTE / _id)
    2. Legge il file XML dal disco (gestisce .p7m estraendo l'XML interno)
       oppure, se il file non e' su disco, usa xml_raw/xml_content salvato
       nel documento Mongo.
    """
    import os
    from app.services.xml_invoice_processor import extract_xml_from_p7m

    db = Database.get_db()

    # ── Trova fattura ────────────────────────────────────────────────────────
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        # Fallback: cerca per _id (MongoDB ObjectId) — usato nei link frontend legacy
        try:
            from bson import ObjectId
            fattura = await db["invoices"].find_one({"_id": ObjectId(fattura_id)})
            if fattura:
                fattura.pop("_id", None)
        except Exception:
            pass
    if not fattura:
        return None, None
    if fattura.get("entity_status") == "deleted" or fattura.get("status") == "deleted":
        # Stesso bug del 15/07/2026 già corretto in get_fattura_dettaglio:
        # una fattura archiviata da DELETE /api/fatture/{id} deve comportarsi
        # come inesistente, anche per la vista renderizzata e per il
        # download dell'XML originale (bug reale, review Codex PR #71).
        return None, None

    xml_file_path = fattura.get("xml_file_path")
    # stringa XML se già estratta — nomi diversi a seconda della pipeline di import
    xml_raw_content = fattura.get("xml_raw") or fattura.get("xml_content")

    xml_bytes: bytes | None = None

    # ── Prova a leggere XML dal disco ────────────────────────────────────────
    if xml_file_path and os.path.exists(xml_file_path):
        with open(xml_file_path, "rb") as f:
            raw = f.read()

        filename = xml_file_path.lower()
        if filename.endswith(".p7m"):
            # Estrattore CMS/PKCS#7 condiviso con l'import (gestisce anche i P7M
            # binari DER, non solo quelli con XML embedded trovabile a byte-search).
            # Ritorna None se l'estrazione fallisce davvero — MAI la busta P7M
            # grezza come se fosse XML (bug reale: prima veniva servita come
            # download "fattura.xml" un blob binario illeggibile).
            xml_bytes = extract_xml_from_p7m(raw)
        else:
            xml_bytes = raw

    elif xml_raw_content:
        if isinstance(xml_raw_content, str):
            # xml_raw è salvato come stringa Python già decodificata in fase
            # di import (può provenire da un file non-UTF-8, es. ISO-8859-1
            # — vedi i tentativi di decodifica in process_xml_bytes). Qui
            # viene sempre ri-codificato in UTF-8 per la risposta HTTP: se
            # il testo contiene ancora la dichiarazione XML originale
            # (<?xml ... encoding="ISO-8859-1"?>), bytes e dichiarazione
            # non concorderebbero più — un lettore XML che si fida della
            # dichiarazione userebbe il codec sbagliato sui bytes UTF-8
            # (mojibake/rifiuto del file). Normalizza la dichiarazione a
            # UTF-8 prima di servire (bug reale, review Codex PR #71).
            xml_raw_content = re.sub(
                r'encoding\s*=\s*(["\'])[^"\']*\1', 'encoding="UTF-8"', xml_raw_content, count=1
            )
            xml_bytes = xml_raw_content.encode("utf-8")
        else:
            xml_bytes = xml_raw_content

    return fattura, xml_bytes


async def download_xml_originale(fattura_id: str) -> Response:
    """Scarica l'XML FatturaPA ORIGINALE della fattura, cosi' come arrivato
    (nessuna ricostruzione/riepilogo): richiesta esplicita utente 19/07/2026
    ("io ho bisogno di vedere sempre l'originale la fattura così come
    arriva altrimenti non potrei mai vedere se c'è un errore") — prima non
    esisteva nessun modo di scaricare/vedere il testo XML grezzo, nemmeno
    quando era salvato nel database.
    """
    fattura, xml_bytes = await _trova_fattura_e_xml_originale(fattura_id)
    if fattura is None:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if not xml_bytes:
        raise HTTPException(
            status_code=404,
            detail="XML originale non disponibile per questa fattura (non salvato in fase di import).",
        )

    numero = fattura.get("invoice_number") or fattura.get("numero_fattura") or fattura_id
    # Il numero fattura arriva dall'XML (attaccante-controllabile in linea di
    # principio, es. un file malformato/malevolo): CR/LF o virgolette non
    # neutralizzate finirebbero grezze nell'header Content-Disposition,
    # rischiando una risposta HTTP malformata/split (bug reale, review Codex
    # PR #71). Tiene solo caratteri filename-safe.
    numero_sicuro = re.sub(r'[^A-Za-z0-9._-]+', '-', str(numero)).strip('-') or "sconosciuto"
    nome_file = f"fattura_{numero_sicuro}.xml"
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{nome_file}"'},
    )


async def view_fattura_assoinvoice(fattura_id: str) -> HTMLResponse:
    """
    Visualizza fattura nel formato ASSO Software (FoglioStileAssoSoftware.xsl).
    1. Cerca la fattura in `invoices` (poi fallback `indice_documenti`)
    2. Legge il file XML dal disco (gestisce .p7m estraendo l'XML interno)
    3. Applica la trasformazione XSLT con il foglio ASSO
    4. Restituisce l'HTML trasformato
    """
    import os
    from lxml import etree as LET

    fattura, xml_bytes = await _trova_fattura_e_xml_originale(fattura_id)
    if fattura is None:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    # ── Applica ASSO XSL se abbiamo l'XML ────────────────────────────────────
    if xml_bytes:
        try:
            xsl_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "static", "FoglioStileAssoSoftware.xsl",
            )
            xsl_doc = LET.parse(xsl_path)
            transform = LET.XSLT(xsl_doc)

            # Parse XML (tolera namespace con p7m cleanup)
            xml_doc = LET.fromstring(xml_bytes)

            # File multi-body: FoglioStileAssoSoftware.xsl itera TUTTI i
            # <FatturaElettronicaBody> del file — se xml_raw è quello
            # dell'intero file raggruppato (condiviso da più fatture, vedi
            # xml_body_index), aprire questa fattura renderizzerebbe anche
            # le altre fatture dello stesso file insieme a questa. Isola
            # SOLO il body di questa fattura prima di trasformare (bug
            # reale, review Codex PR #71).
            corpi = [el for el in xml_doc.iter()
                     if (el.tag.split('}')[-1] if '}' in el.tag else el.tag) == 'FatturaElettronicaBody']
            if len(corpi) > 1:
                indice = fattura.get("xml_body_index", 0)
                if not (0 <= indice < len(corpi)):
                    indice = 0
                for i, corpo in enumerate(corpi):
                    if i != indice:
                        corpo.getparent().remove(corpo)

            html_result = transform(xml_doc)
            html_str = LET.tostring(html_result, pretty_print=True, encoding="unicode")

            # Adatta l'HTML allo schermo (viewport + CSS responsive), sia che
            # l'XSL emetta <html> sia che no.
            html_str = _rendi_fattura_responsive(html_str)
            return HTMLResponse(content=html_str)
        except Exception as xsl_err:
            logger.warning(f"Errore XSLT per {fattura_id}: {xsl_err} — fallback HTML generico")

    # ── Fallback: HTML generico se XML non disponibile ────────────────────────
    # ATTENZIONE (richiesta utente 19/07/2026): questo NON è il documento
    # originale, è un riepilogo ricostruito con un sottoinsieme di campi —
    # generate_invoice_html() lo segnala esplicitamente nell'HTML, cosi'
    # l'utente sa sempre quando NON sta vedendo l'originale.
    db = Database.get_db()
    righe = await db[COL_DETTAGLIO_RIGHE].find({"fattura_id": fattura_id}, {"_id": 0}).to_list(1000)
    if not righe and fattura.get("linee"):
        righe = fattura.get("linee", [])
    html = generate_invoice_html(fattura, righe)
    return HTMLResponse(content=_rendi_fattura_responsive(html))


async def download_pdf_allegato(fattura_id: str, allegato_id: str) -> Response:
    """Download PDF allegato fattura."""
    db = Database.get_db()
    
    allegato = await db[COL_ALLEGATI].find_one({"id": allegato_id, "fattura_id": fattura_id})
    if not allegato:
        raise HTTPException(status_code=404, detail="Allegato non trovato")
    
    try:
        pdf_data = base64.b64decode(allegato["base64_data"])
    except Exception:
        raise HTTPException(status_code=500, detail="Errore decodifica PDF")
    
    filename = allegato.get("nome_file", f"allegato_{allegato_id}.pdf")
    
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


async def get_fattura_dettaglio(fattura_id: str) -> Dict[str, Any]:
    """Dettaglio singola fattura con righe e allegati."""
    db = Database.get_db()
    
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        try:
            from bson import ObjectId
            fattura = await db["invoices"].find_one({"_id": ObjectId(fattura_id)})
            if fattura:
                fattura.pop("_id", None)
        except Exception:
            pass
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if fattura.get("entity_status") == "deleted" or fattura.get("status") == "deleted":
        # Stesso bug del 15/07/2026: una fattura archiviata da DELETE
        # /api/fatture/{id} deve comportarsi come inesistente per l'utente,
        # non ricomparire nel dettaglio.
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    righe = await db[COL_DETTAGLIO_RIGHE].find({"fattura_id": fattura_id}, {"_id": 0}).to_list(1000)
    allegati = await db[COL_ALLEGATI].find({"fattura_id": fattura_id}, {"_id": 0, "base64_data": 0}).to_list(10)
    
    return {"fattura": fattura, "righe": righe, "allegati": allegati}


async def update_fattura(fattura_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiorna una fattura."""
    db = Database.get_db()
    
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    update_fields = {}
    for field in ["pagato", "data_pagamento", "metodo_pagamento", "riconciliato", "note"]:
        if field in data:
            update_fields[field] = data[field]
    
    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[COL_FATTURE_RICEVUTE].update_one({"id": fattura_id}, {"$set": update_fields})
    
    return {"success": True, "updated": list(update_fields.keys())}


async def get_fornitori(
    search: Optional[str] = Query(None),
    con_fatture: bool = Query(default=False),
    limit: int = Query(default=100, le=500)
) -> Dict[str, Any]:
    """Lista fornitori con filtri."""
    db = Database.get_db()
    
    query = {}
    if search:
        query["$or"] = [
            {"ragione_sociale": {"$regex": search, "$options": "i"}},
            {"partita_iva": {"$regex": search, "$options": "i"}}
        ]
    if con_fatture:
        query["fatture_count"] = {"$gt": 0}
    
    fornitori = await db[COL_FORNITORI].find(query, {"_id": 0}).sort("ragione_sociale", 1).limit(limit).to_list(limit)
    return {"items": fornitori, "total": len(fornitori)}


async def get_statistiche(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    """
    Statistiche fatture ricevute — legge da `invoices` (collection principale).
    Tutti i 73 doc di fatture_passive sono già presenti in invoices (stesso xml_filename),
    quindi invoices è la fonte unica per evitare duplicati.
    """
    db = Database.get_db()

    # Filtro per anno (invoices ha campo `anno` numerico e `invoice_date` ISO;
    # i doc importati prima del backfill hanno solo invoice_date)
    query: dict = {}
    if anno:
        query["$or"] = [
            {"anno": anno},
            {"invoice_date": {"$regex": f"^{anno}"}},
        ]

    # Espressioni che coprono ENTRAMBI gli schemi campi di `invoices`
    _importo = {"$toDouble": {"$ifNull": ["$total_amount", {"$ifNull": ["$importo_totale", 0]}]}}
    _piva = {"$ifNull": ["$supplier_vat", {"$ifNull": ["$cedente_piva", ""]}]}
    _pagata = {"$cond": [{"$or": [
        {"$in": [{"$ifNull": ["$stato", ""]}, ["pagata", "paid"]]},
        {"$eq": [{"$ifNull": ["$status", ""]}, "paid"]},
        {"$eq": [{"$ifNull": ["$pagato", False]}, True]},
        {"$eq": [{"$ifNull": ["$stato_pagamento", ""]}, "pagata"]},
    ]}, 1, 0]}

    pipeline_inv = [
        {"$match": query},
        # Dedup di CONTENUTO (stessa chiave usata dalla lista archivio):
        # i doppioni non devono gonfiare i contatori mostrati sopra la tabella
        {"$group": {
            "_id": {
                "numero": {"$toUpper": {"$ifNull": ["$invoice_number", {"$ifNull": ["$numero_documento", ""]}]}},
                "piva": _piva,
                "data": {"$substrCP": [{"$ifNull": ["$invoice_date", {"$ifNull": ["$data_documento", ""]}]}, 0, 10]},
                "importo": {"$round": [_importo, 2]},
            },
            "importo": {"$first": _importo},
            "piva": {"$first": _piva},
            "pagata": {"$max": _pagata},
        }},
        {"$group": {
            "_id": None,
            "totale_fatture": {"$sum": 1},
            "importo_totale": {"$sum": "$importo"},
            "fornitori_unici": {"$addToSet": "$piva"},
            "pagate": {"$sum": "$pagata"},
            "importo_pagato": {"$sum": {"$cond": [{"$eq": ["$pagata", 1]}, "$importo", 0]}},
        }}
    ]
    result = await db["invoices"].aggregate(pipeline_inv).to_list(1)
    stats = result[0] if result else {}
    stats.pop("_id", None)

    # Anomale REALI (prima era 0 hardcoded): importo assente/≤0 o numero mancante
    anomale_cond = {"$or": [
        {"$and": [
            {"$or": [{"total_amount": {"$lte": 0}}, {"total_amount": {"$exists": False}}]},
            {"$or": [{"importo_totale": {"$lte": 0}}, {"importo_totale": {"$exists": False}}]},
        ]},
        {"$and": [
            {"invoice_number": {"$in": [None, ""]}},
            {"numero_documento": {"$in": [None, ""]}},
        ]},
    ]}
    try:
        anomale = await db["invoices"].count_documents(
            {"$and": [query, anomale_cond]} if query else anomale_cond)
    except Exception:
        anomale = 0

    totale = stats.get("totale_fatture", 0)
    importo = round(stats.get("importo_totale", 0), 2)
    fornitori = len([p for p in stats.get("fornitori_unici", []) if p])
    pagate = stats.get("pagate", 0)
    importo_pagato = round(stats.get("importo_pagato", 0), 2)
    da_pagare = totale - pagate
    importo_da_pagare = round(importo - importo_pagato, 2)

    return {
        "totale_fatture": totale,
        "importo_totale": importo,
        "totale_importo": importo,
        "pagate": pagate,
        "importo_pagato": importo_pagato,
        "da_pagare": da_pagare,
        "importo_da_pagare": importo_da_pagare,
        "fornitori_unici": fornitori,
        "fatture_anomale": anomale,
        "anno": anno,
    }


async def pulisci_duplicati_invoices() -> Dict[str, Any]:
    """Elimina dal DB le fatture DUPLICATE in `invoices` (stesso numero +
    P.IVA + data + importo, importate più volte da canali diversi).

    Per ogni gruppo tiene il documento "migliore" (collegato a prima nota /
    pagato, altrimenti il più vecchio) ed elimina gli altri, insieme agli
    eventuali movimenti di prima nota e scadenze generati dai doppioni.
    Eseguita anche in automatico dal job Automazioni (ogni 30 min).
    """
    db = Database.get_db()
    docs = await db["invoices"].find(
        {},
        {"_id": 0, "id": 1, "invoice_number": 1, "numero_documento": 1,
         "supplier_vat": 1, "cedente_piva": 1,
         "invoice_date": 1, "data_documento": 1,
         "total_amount": 1, "importo_totale": 1,
         "prima_nota_id": 1, "prima_nota_cassa_id": 1, "prima_nota_banca_id": 1,
         "pagato": 1, "stato_pagamento": 1, "created_at": 1},
    ).to_list(20000)

    gruppi: Dict[tuple, list] = {}
    for d in docs:
        numero = str(d.get("invoice_number") or d.get("numero_documento") or "").strip().upper()
        piva = str(d.get("supplier_vat") or d.get("cedente_piva") or "").strip()
        data = str(d.get("invoice_date") or d.get("data_documento") or "")[:10]
        try:
            imp = round(float(d.get("total_amount") or d.get("importo_totale") or 0), 2)
        except (ValueError, TypeError):
            imp = 0.0
        if not numero or not piva or not d.get("id"):
            continue
        gruppi.setdefault((numero, piva, data, imp), []).append(d)

    def _score(d: dict) -> tuple:
        ha_pn = bool(d.get("prima_nota_id") or d.get("prima_nota_cassa_id")
                     or d.get("prima_nota_banca_id"))
        pagata = bool(d.get("pagato") or d.get("stato_pagamento") == "pagata")
        # score più alto = da tenere; a parità vince il più vecchio
        return (int(ha_pn), int(pagata), -(len(str(d.get("created_at") or "")) and 0))

    ids_da_eliminare = []
    gruppi_duplicati = 0
    for k, gruppo in gruppi.items():
        if len(gruppo) < 2:
            continue
        gruppi_duplicati += 1
        gruppo.sort(key=lambda d: (_score(d), str(d.get("created_at") or "")), reverse=True)
        tenuta = gruppo[0]
        for doppione in gruppo[1:]:
            ids_da_eliminare.append(doppione["id"])

    eliminati_pn = 0
    if ids_da_eliminare:
        await db["invoices"].delete_many({"id": {"$in": ids_da_eliminare}})
        # Rimuovi anche i movimenti prima nota e le scadenze generati dai doppioni
        r1 = await db["prima_nota_cassa"].delete_many({"fattura_id": {"$in": ids_da_eliminare}})
        r2 = await db["prima_nota_banca"].delete_many({"fattura_id": {"$in": ids_da_eliminare}})
        await db["scadenziario_fornitori"].delete_many({"fattura_id": {"$in": ids_da_eliminare}})
        eliminati_pn = r1.deleted_count + r2.deleted_count

    return {
        "success": True,
        "gruppi_duplicati": gruppi_duplicati,
        "fatture_eliminate": len(ids_da_eliminare),
        "movimenti_prima_nota_eliminati": eliminati_pn,
    }


async def elimina_fatture_guscio_vuoto(
    dry_run: bool = Query(True, description="Solo conteggio"),
) -> Dict[str, Any]:
    """Segnalazione utente 18/07/2026: nell'anno 2024 restano '8 fatture'
    vuote (nessun numero, nessun fornitore, spesso senza campo id: per
    questo né l'eliminazione di massa né la selezione le agganciava).
    Sono gusci senza contenuto: si eliminano per _id."""
    db = Database.get_db()
    docs = await db["invoices"].find(
        {"$and": [
            {"$or": [{"invoice_number": {"$in": [None, ""]}},
                     {"invoice_number": {"$exists": False}}]},
            {"$or": [{"supplier_name": {"$in": [None, ""]}},
                     {"supplier_name": {"$exists": False}}]},
            {"$or": [{"xml_raw": {"$in": [None, ""]}},
                     {"xml_raw": {"$exists": False}}]},
            {"status": {"$nin": ["deleted", "archived"]}},
        ]},
        {"id": 1, "invoice_date": 1, "total_amount": 1},
    ).to_list(2000)

    esempi = [{"data": d.get("invoice_date"), "importo": d.get("total_amount"),
               "ha_id": bool(d.get("id"))} for d in docs[:10]]
    if not dry_run and docs:
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc).isoformat()
        for d in docs:
            await db["invoices"].update_one(
                {"_id": d["_id"]},
                {"$set": {"status": "deleted", "deleted": True,
                          "deleted_reason": "guscio_vuoto_senza_dati",
                          "deleted_at": now}})
    return {"dry_run": dry_run,
            "eliminate" if not dry_run else "da_eliminare": len(docs),
            "esempi": esempi}


async def elimina_fatture_anni_vecchi(
    dry_run: bool = Query(True, description="Solo conteggio"),
    anni: str = Query("2023,2024,2025", description="Anni da eliminare, separati da virgola"),
    definitivo: bool = Query(False, description="Elimina FISICAMENTE dal database (con backup)"),
) -> Dict[str, Any]:
    """Ordine utente (17-18/07/2026, ribadito): le fatture 2023/24/25 vanno
    eliminate TUTTE — 'dal database', non nascoste. Copre ogni schema
    (invoice_date, data_fattura legacy, campo anno) e con definitivo=true
    le rimuove fisicamente (incluse quelle già soft-delete, che le card
    dell'archivio continuavano a contare), dopo backup in una collection
    invoices_backup_*."""
    db = Database.get_db()
    lista_anni = [a.strip() for a in anni.split(",") if a.strip()]
    condizioni = []
    for a in lista_anni:
        condizioni += [{"invoice_date": {"$regex": f"^{a}"}},
                       {"data_fattura": {"$regex": f"^{a}"}},
                       {"anno": int(a)}]
    query: Dict[str, Any] = {"$or": condizioni}
    if not definitivo:
        query["status"] = {"$nin": ["deleted", "archived"]}

    docs = await db["invoices"].find(
        query,
        {"invoice_number": 1, "numero_fattura": 1, "supplier_name": 1,
         "fornitore_nome": 1, "invoice_date": 1, "data_fattura": 1, "status": 1},
    ).to_list(20000)

    esempi = [{"numero": d.get("invoice_number") or d.get("numero_fattura"),
               "fornitore": (d.get("supplier_name") or d.get("fornitore_nome") or "")[:30],
               "data": d.get("invoice_date") or d.get("data_fattura"),
               "gia_nascosta": d.get("status") == "deleted"} for d in docs[:10]]
    backup_collection = None
    if not dry_run and docs:
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc).isoformat()
        if definitivo:
            # backup completo, poi delete fisico
            backup_collection = f"invoices_backup_anni_vecchi_{_dt.now(_tz.utc).strftime('%Y%m%d_%H%M%S')}"
            completi = await db["invoices"].find(query).to_list(20000)
            if completi:
                for c in completi:
                    c["_backup_at"] = now
                await db[backup_collection].insert_many(completi)
            await db["invoices"].delete_many(query)
        else:
            for d in docs:
                await db["invoices"].update_one(
                    {"_id": d["_id"]},
                    {"$set": {"status": "deleted", "deleted": True,
                              "deleted_reason": "anno_vecchio_ordine_utente",
                              "deleted_at": now}})
    return {"dry_run": dry_run, "anni": lista_anni, "definitivo": definitivo,
            "eliminate" if not dry_run else "da_eliminare": len(docs),
            "backup_collection": backup_collection,
            "esempi": esempi}
