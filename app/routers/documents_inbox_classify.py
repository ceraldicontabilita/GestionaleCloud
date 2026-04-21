"""
Auto-classificazione e auto-associazione dei documenti in documents_inbox.

Classifica i PDF/XML scaricati via Gmail/PEC in base a:
  1. Filename (pattern tipici: F24, cedolino, CU, CUD, verbale, …)
  2. Subject / mittente email
  3. Contenuto testuale del PDF (fallback, se estraibile)

Propaga i documenti alla collection corretta:
  - F24           -> crea record in `f24_tributi`, estraendo importo/scadenza se possibile
  - cedolino      -> associa al dipendente (match nome dal filename → hr_employees)
  - CUD/CU        -> associa al dipendente (anno + nome)
  - verbale       -> associa al verbale già esistente per numero
  - PEC notifiche -> tipo "pec_notifica" (rimane in inbox per consultazione)
  - contributi    -> tipo "contributi_inps"
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

from app.database import Database
from app.utils.error_handler import handle_errors


router = APIRouter(tags=["Documents Inbox"])

# ─────────────── REGEX + pattern di classificazione ───────────────

PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("f24",              re.compile(r"(^|[_\-\s])f24([_\-\s]|\.|$)|ricev.*f24|deleg.*pag", re.I)),
    # CU riconosciuta anche dal pattern "CodiceFiscale - AAAA - COGNOME NOME"
    ("cu",               re.compile(r"(^|[_\-\s])(cud|cu)[_\-\s]?\d{4}|certif.*unic|[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\s*[-_]\s*\d{4}", re.I)),
    ("cedolino",         re.compile(r"cedolin|busta[_\s\-]?paga|lul|paghe[_\-]?\d{4}", re.I)),
    ("verbale",          re.compile(r"verbale|pagopa|avviso[_\-\s]?pago|cda[_\-\s]?\d", re.I)),
    ("contributi_inps",  re.compile(r"inps|dm10|uniemens|contributi", re.I)),
    ("pec_notifica",     re.compile(r"relatapec|copiaconfor?mepec|postacer?t|daticert", re.I)),
    ("cartella_esattoriale", re.compile(r"cartella|esattor|riscoss|ader|agenzia.*entra", re.I)),
    ("bonifico",         re.compile(r"bonifico|sepa|contabil.*banc", re.I)),
    ("scontrino",        re.compile(r"scontr|corrispet|sc\d{3,}", re.I)),
    ("satispay",         re.compile(r"satispay|^sav\d|sav[_\-]\d|^rcp_sav", re.I)),
    ("fattura_servizi",  re.compile(r"mongodb.*atlas|aws[_\-\s].*invoic|google.*cloud|godaddy|namecheap", re.I)),
    ("fattura_estera",   re.compile(r"^invoice[_\-\s]|invoice_\w+_", re.I)),
    ("ricevuta_estera",  re.compile(r"^receipt[_\-\s]|receipt_\w+_", re.I)),
    ("estratto_conto",   re.compile(r"estratto[_\-\s]?conto|^estratto_|e\.c\.[_\-\s]|^ec[_\-\s]\d", re.I)),
    ("xml_sdi",          re.compile(r"^dc[_\-\s]?it[_\-\s]?|^it\d{11}_.*\.xml|_5010_|\.xml\.p7m$", re.I)),
    ("qr_pagamento",     re.compile(r"^qr[_\-\s]|qr.*code", re.I)),
    ("rimborso",         re.compile(r"rimbors|restituz", re.I)),
]


def classify_by_text(filename: str, subject: str = "", sender: str = "") -> Optional[str]:
    """Classifica un documento basandosi su filename + subject + sender."""
    haystack = f"{filename or ''} {subject or ''} {sender or ''}".lower()
    for category, pat in PATTERNS:
        if pat.search(haystack):
            return category
    return None


# ──────────────────── Helpers di estrazione ────────────────────

def _extract_pdf_text(pdf_bytes: bytes, max_pages: int = 3) -> str:
    """Estrae testo dalle prime pagine di un PDF. Empty string se non parsabile."""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        out = []
        for i, page in enumerate(reader.pages[:max_pages]):
            try:
                out.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                continue
        return "\n".join(out)
    except Exception:  # noqa: BLE001
        return ""


def _extract_importo(text: str) -> Optional[float]:
    """Cerca pattern di importo €NN,NN oppure 'TOTALE: NN.NN' nel testo."""
    patterns = [
        r"totale(?:\s+da\s+versare|\s+a\s+debito)?\s*[€:\s]*([\d\.]+,\d{2})",
        r"importo\s*[€:\s]*([\d\.]+,\d{2})",
        r"€\s*([\d\.]+,\d{2})",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(".", "").replace(",", "."))
            except ValueError:
                continue
    return None


def _extract_data_scadenza(text: str) -> Optional[str]:
    """Cerca pattern di data scadenza (DD/MM/YYYY)."""
    m = re.search(r"scaden\w*\s*[:\s]*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        parts = m.group(1).split("/")
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    if m:
        parts = m.group(1).split("/")
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return None


def _extract_codice_fiscale(filename: str, text: str = "") -> Optional[str]:
    """Cerca un codice fiscale italiano nel filename o nel testo."""
    hay = f"{filename or ''} {text or ''}"
    m = re.search(r"[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]", hay)
    return m.group(0) if m else None


def _extract_dipendente(db_employees: List[Dict[str, Any]], filename: str, text: str = "") -> Optional[Dict[str, Any]]:
    """Cerca il dipendente: prima via Codice Fiscale (esatto), poi via cognome nel filename/testo."""
    cf = _extract_codice_fiscale(filename, text)
    if cf:
        for emp in db_employees:
            emp_cf = (emp.get("codice_fiscale") or emp.get("fiscal_code") or "").upper().strip()
            if emp_cf and emp_cf == cf:
                return emp
    fn_lower = (filename or "").lower()
    txt_lower = (text or "").lower()
    hay = f"{fn_lower} {txt_lower}"
    best = None
    best_score = 0
    for emp in db_employees:
        cognome = (emp.get("cognome") or emp.get("surname") or "").lower().strip()
        nome = (emp.get("nome") or emp.get("name") or "").lower().strip()
        if len(cognome) < 3:
            continue
        score = 0
        if cognome in hay:
            score += 3
        if nome and nome in hay:
            score += 1
        if score > best_score:
            best_score = score
            best = emp
    return best if best_score >= 3 else None


# ──────────────────── ENDPOINTS ────────────────────

@router.post("/auto-classify")
@handle_errors
async def auto_classify(
    dry_run: bool = Query(False, description="Se True, restituisce l'esito senza scrivere"),
    solo_non_classificati: bool = Query(True, description="Classifica solo i docs senza categoria"),
) -> Dict[str, Any]:
    """
    Scansiona documents_inbox e:
      1. Assegna `categoria` e `tipo` in base a filename/subject/content
      2. Tenta l'auto-associazione (F24 → f24_tributi, cedolino → hr_employees, …)
    """
    db = Database.get_db()

    query: Dict[str, Any] = {}
    if solo_non_classificati:
        query = {"$or": [
            {"categoria": None},
            {"categoria": {"$exists": False}},
            {"categoria": ""},
        ]}

    docs = await db["documents_inbox"].find(query, {"_id": 0}).to_list(10000)
    # Preload dipendenti (la collection canonica si chiama 'dipendenti')
    employees = await db["dipendenti"].find({}, {
        "_id": 0, "id": 1, "cognome": 1, "nome": 1, "surname": 1, "name": 1,
        "codice_fiscale": 1, "fiscal_code": 1,
    }).to_list(5000)

    report = {
        "totali": len(docs),
        "classificati": {},
        "cedolini_associati": 0,
        "f24_creati": 0,
        "nessuna_categoria": 0,
        "errori": 0,
        "dry_run": dry_run,
    }

    for d in docs:
        filename = d.get("filename") or ""
        subject = d.get("subject") or ""
        sender = d.get("sender") or d.get("from") or ""

        categoria = classify_by_text(filename, subject, sender)
        if not categoria:
            report["nessuna_categoria"] += 1
            continue

        report["classificati"][categoria] = report["classificati"].get(categoria, 0) + 1

        # Try extract text from PDF
        text = ""
        pdf_data = d.get("pdf_data") or d.get("content")
        if pdf_data and isinstance(pdf_data, bytes):
            text = _extract_pdf_text(pdf_data)
        elif d.get("text"):
            text = d.get("text", "")

        update_fields: Dict[str, Any] = {
            "categoria": categoria,
            "auto_classified_at": datetime.now(timezone.utc).isoformat(),
        }

        # Auto-associazione per tipologia
        if categoria in ("cedolino", "cu"):
            emp = _extract_dipendente(employees, filename, text)
            if emp:
                update_fields["dipendente_id"] = emp.get("id")
                update_fields["dipendente_nominativo"] = f"{emp.get('cognome','')} {emp.get('nome','')}".strip()
                update_fields["codice_fiscale"] = emp.get("codice_fiscale") or emp.get("fiscal_code")
                report["cedolini_associati"] += 1
            else:
                # Tenta lettura CF anche quando il dipendente non è nel DB HR
                cf = _extract_codice_fiscale(filename, text)
                if cf:
                    update_fields["codice_fiscale"] = cf

        elif categoria == "f24":
            importo = _extract_importo(text) if text else None
            scadenza = _extract_data_scadenza(text) if text else None
            if importo:
                update_fields["importo"] = importo
            if scadenza:
                update_fields["data_scadenza"] = scadenza
            if importo and not dry_run:
                # Crea record in f24_tributi se non esiste già per (data_scadenza, importo)
                f24_key = {"data_scadenza": scadenza, "importo": importo}
                if scadenza and importo:
                    existing = await db["f24_tributi"].find_one(f24_key)
                    if not existing:
                        import uuid as _uuid
                        await db["f24_tributi"].insert_one({
                            "id": str(_uuid.uuid4()),
                            "data_scadenza": scadenza,
                            "importo": importo,
                            "origine": "documents_inbox_auto",
                            "documento_id": d.get("id"),
                            "stato": "da_verificare",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                        report["f24_creati"] += 1

        if dry_run:
            continue

        await db["documents_inbox"].update_one(
            {"id": d.get("id")} if d.get("id") else {"filename": filename},
            {"$set": update_fields},
        )

    return {"success": True, **report}


@router.get("/statistics")
@handle_errors
async def inbox_statistics() -> Dict[str, Any]:
    """Statistiche aggregate documents_inbox."""
    db = Database.get_db()
    totali = await db["documents_inbox"].count_documents({})
    senza_cat = await db["documents_inbox"].count_documents({"$or": [
        {"categoria": None}, {"categoria": ""}, {"categoria": {"$exists": False}}
    ]})
    per_cat: Dict[str, int] = {}
    async for r in db["documents_inbox"].aggregate([
        {"$group": {"_id": "$categoria", "c": {"$sum": 1}}},
    ]):
        per_cat[r["_id"] or "non_classificato"] = r["c"]
    cedolini_associati = await db["documents_inbox"].count_documents({
        "categoria": {"$in": ["cedolino", "cu"]}, "dipendente_id": {"$exists": True, "$ne": None}
    })
    return {
        "totali": totali,
        "non_classificati": senza_cat,
        "per_categoria": per_cat,
        "cedolini_associati_dipendente": cedolini_associati,
    }


@router.post("/import-dipendenti-from-cu")
@handle_errors
async def import_dipendenti_from_cu(
    dry_run: bool = Query(False, description="Preview senza scrivere"),
) -> Dict[str, Any]:
    """
    Popola la collection `dipendenti` dall'anagrafica contenuta nei filename
    delle Certificazioni Uniche (CU).

    Pattern filename supportato:
      '<CodiceFiscale> - <Anno> - <COGNOME NOME> (<CF>-<Progressivo>).pdf'
    Esempio: 'CLETTV65E05F839N - 2025 - CELIO OTTAVIO (CLETTV65E05F839N-0300022).pdf'
    """
    import uuid as _uuid
    db = Database.get_db()

    cu_docs = await db["documents_inbox"].find(
        {"categoria": "cu"}, {"_id": 0, "filename": 1}
    ).to_list(5000)

    # Indicizza dipendenti esistenti per CF
    existing = await db["dipendenti"].find({}, {"_id": 0, "id": 1, "codice_fiscale": 1}).to_list(5000)
    cf_set = {(e.get("codice_fiscale") or "").upper() for e in existing if e.get("codice_fiscale")}

    # Pattern di estrazione
    cu_pattern = re.compile(
        r"([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\s*-\s*(\d{4})\s*-\s*([A-Z][A-Z\s']+?)\s*\(",
        re.IGNORECASE,
    )

    nuovi: List[Dict[str, Any]] = []
    gia_presenti = 0
    non_riconosciuti: List[str] = []

    for d in cu_docs:
        fn = (d.get("filename") or "").replace("\n", " ").strip()
        m = cu_pattern.search(fn)
        if not m:
            non_riconosciuti.append(fn[:80])
            continue
        cf = m.group(1).upper()
        nome_completo_raw = m.group(3).strip()
        # Split cognome/nome: per codici fiscali italiani, in filename il cognome viene sempre prima
        # Gestione di cognomi composti: prendiamo la prima parola come cognome, il resto come nome
        # (approccio prudente — l'utente potrà correggere)
        parts = nome_completo_raw.split()
        if len(parts) >= 2:
            # Nomi composti: se la stringa è molto lunga (come "SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA"),
            # prendiamo la prima metà come cognome e la seconda come nome
            if len(parts) > 3:
                mid = len(parts) // 2
                cognome = " ".join(parts[:mid]).title()
                nome = " ".join(parts[mid:]).title()
            else:
                cognome = parts[0].title()
                nome = " ".join(parts[1:]).title()
        else:
            cognome = nome_completo_raw.title()
            nome = ""

        if cf in cf_set:
            gia_presenti += 1
            continue

        nuovi.append({
            "id": str(_uuid.uuid4()),
            "codice_fiscale": cf,
            "cognome": cognome,
            "nome": nome,
            "nome_completo": nome_completo_raw.title(),
            "stato": "attivo",
            "attivo": True,
            "fonte": "cu_auto_import",
            "anno_cu": int(m.group(2)),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cf_set.add(cf)

    if not dry_run and nuovi:
        await db["dipendenti"].insert_many([n.copy() for n in nuovi])

    return {
        "success": True,
        "dry_run": dry_run,
        "cu_analizzate": len(cu_docs),
        "dipendenti_creati": len(nuovi),
        "gia_presenti": gia_presenti,
        "non_riconosciuti": len(non_riconosciuti),
        "nuovi_preview": [
            {"codice_fiscale": n["codice_fiscale"], "nominativo": f"{n['cognome']} {n['nome']}"}
            for n in nuovi[:30]
        ],
        "filename_non_riconosciuti": non_riconosciuti[:10],
    }


@router.get("/cross-check-f24")
@handle_errors
async def cross_check_f24() -> Dict[str, Any]:
    """
    Confronta gli F24 rilevati in `documents_inbox` con la collection `f24_tributi`.

    Ritorna:
      - f24_matched: (importo, scadenza) trovati in entrambi
      - f24_only_inbox: nei PDF ma non in `f24_tributi` (da importare)
      - f24_only_tributi: in `f24_tributi` senza documento PDF (da rintracciare)
    """
    db = Database.get_db()

    inbox_f24 = await db["documents_inbox"].find(
        {"categoria": "f24"},
        {"_id": 0, "id": 1, "filename": 1, "importo": 1, "data_scadenza": 1,
         "totale_versato": 1, "data_pagamento": 1, "ragione_sociale": 1, "tributi": 1,
         "codice_fiscale": 1, "ai_parsed_data": 1},
    ).to_list(5000)

    tributi = await db["f24_tributi"].find(
        {}, {"_id": 0, "id": 1, "importo": 1, "data_scadenza": 1, "origine": 1}
    ).to_list(5000)

    def _key(r: Dict[str, Any], prefer_versamento: bool = False) -> Optional[Tuple[str, float]]:
        # Supporta sia la chiave (scadenza, importo) che (data_pagamento, totale_versato)
        if prefer_versamento:
            s = r.get("data_pagamento") or r.get("data_scadenza")
            i = r.get("totale_versato")
            if i is None:
                i = r.get("importo")
        else:
            s = r.get("data_scadenza") or r.get("data_pagamento")
            i = r.get("importo")
            if i is None:
                i = r.get("totale_versato")
        if not s or i is None:
            return None
        return (str(s)[:10], round(float(i), 2))

    trib_keys = {_key(t): t for t in tributi if _key(t)}
    inbox_keys = {_key(d, prefer_versamento=True): d for d in inbox_f24 if _key(d, prefer_versamento=True)}

    matched = [
        {"scadenza": k[0], "importo": k[1],
         "inbox_filename": inbox_keys[k].get("filename"),
         "tributo_id": trib_keys[k].get("id")}
        for k in set(inbox_keys) & set(trib_keys)
    ]
    only_inbox = [
        {"scadenza": k[0], "importo": k[1],
         "filename": inbox_keys[k].get("filename"),
         "doc_id": inbox_keys[k].get("id"),
         "ragione_sociale": inbox_keys[k].get("ragione_sociale"),
         "codice_fiscale": inbox_keys[k].get("codice_fiscale"),
         "tributi": [{"codice": t.get("codice_tributo"), "importo": t.get("importo_debito")}
                     for t in (inbox_keys[k].get("tributi") or [])]}
        for k in set(inbox_keys) - set(trib_keys)
    ]
    only_tributi = [
        {"scadenza": k[0], "importo": k[1], "tributo_id": trib_keys[k].get("id"),
         "origine": trib_keys[k].get("origine")}
        for k in set(trib_keys) - set(inbox_keys)
    ]

    return {
        "success": True,
        "f24_inbox_totali": len(inbox_f24),
        "f24_inbox_con_metadata": len(inbox_keys),
        "f24_tributi_totali": len(tributi),
        "matched": matched,
        "only_inbox": only_inbox,
        "only_tributi": only_tributi[:100],
        "counts": {
            "matched": len(matched),
            "only_inbox": len(only_inbox),
            "only_tributi": len(only_tributi),
        },
    }


@router.post("/import-f24-from-inbox")
@handle_errors
async def import_f24_from_inbox(
    dry_run: bool = Query(False, description="Preview senza scrivere"),
) -> Dict[str, Any]:
    """Importa in `f24_tributi` tutti gli F24 presenti in documents_inbox
    con AI-parsed data ma non ancora presenti nella collection principale.

    Per ogni F24: crea un record tributo per ciascuna riga tributo dell'F24.
    """
    import uuid as _uuid
    db = Database.get_db()

    inbox_f24 = await db["documents_inbox"].find(
        {"categoria": "f24", "totale_versato": {"$gt": 0}},
        {"_id": 0},
    ).to_list(5000)

    existing = await db["f24_tributi"].find(
        {}, {"_id": 0, "data_scadenza": 1, "importo": 1, "codice_tributo": 1}
    ).to_list(10000)
    existing_keys = set()
    for t in existing:
        s = str(t.get("data_scadenza") or "")[:10]
        i = round(float(t.get("importo") or 0), 2)
        c = str(t.get("codice_tributo") or "")
        existing_keys.add((s, i, c))

    nuovi: List[Dict[str, Any]] = []
    for d in inbox_f24:
        data_pag = str(d.get("data_pagamento") or "")[:10]
        tributi_rows = d.get("tributi") or []
        if not data_pag or not tributi_rows:
            continue

        for tr in tributi_rows:
            importo = float(tr.get("importo_debito") or 0) - float(tr.get("importo_credito") or 0)
            if importo <= 0:
                continue
            cod = str(tr.get("codice_tributo") or "")
            key = (data_pag, round(importo, 2), cod)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            nuovi.append({
                "id": str(_uuid.uuid4()),
                "data_scadenza": data_pag,
                "data_pagamento": data_pag,
                "importo": round(importo, 2),
                "codice_tributo": cod,
                "descrizione": tr.get("descrizione"),
                "rateazione": tr.get("rateazione"),
                "periodo_riferimento": tr.get("periodo_riferimento"),
                "codice_fiscale": d.get("codice_fiscale"),
                "ragione_sociale": d.get("ragione_sociale"),
                "origine": "documents_inbox_import",
                "documento_id": d.get("id"),
                "filename": d.get("filename"),
                "stato": "da_verificare",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    if not dry_run and nuovi:
        await db["f24_tributi"].insert_many([n.copy() for n in nuovi])

    return {
        "success": True,
        "dry_run": dry_run,
        "f24_analizzati": len(inbox_f24),
        "tributi_creati": len(nuovi),
        "nuovi_preview": [
            {"data_pagamento": n["data_pagamento"], "codice_tributo": n["codice_tributo"],
             "importo": n["importo"], "descrizione": n.get("descrizione")}
            for n in nuovi[:20]
        ],
    }
