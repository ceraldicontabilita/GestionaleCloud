"""Fascicolo annuale in lettura: originali distinti, stesso contribuente e anno.

Un invio puo' avere un frontespizio e molti quadri PDF separati. L'identificativo
della dichiarazione li unisce; l'anno di imposta riunisce gli invii nel fascicolo,
senza scegliere una versione vincente o sommare le dichiarazioni. Le quietanze
provengono dal registro unico, anche in assenza del modello F24.
"""
from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from typing import Any

from app.services.declaration_registry import DECLARATION_TYPES, TAX_CODES
from app.services.fiscal_domain import stable_id
from app.services import f24_controllo_incrociato as reg
from app.services.originale_documento import url_originale

_IDENT = re.compile(r"(?<!\d)(\d{11})\s*-\s*(\d{7})(?!\d)")
_SUBJECT = re.compile(r"Soggetto:\s*([^\n]*?)\(\s*([A-Z0-9]{11,16})\s*\)", re.I)
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def _printed_taxpayer(text, company_id):
    # Ricevute AdE: il contribuente e' distinto dal rappresentante e
    # dall'intermediario, che possono avere altri codici fiscali nello stesso PDF.
    m = re.search(r"(?:DATI\s+RELATIVI\s+AL\s+CONTRIBUENTE|DATI\s+DELLA\s+SOCIETA['’]\s+O\s+ENTE|DATI\s+RICALCOLATI)"
                  r"(?:(?!DATI RELATIVI AL DICHIARANTE).){0,160}?Codice\s+fiscale\s*:?\s*([A-Z0-9]{11,16})\b", text, re.I | re.S)
    if m:
        return m[1].upper()
    # Nei modelli a caselle (LIPE/IVA/IRAP) ogni cifra puo' essere una riga.
    # Il tenant NON basta: richiediamo il suo CF stampato almeno due volte
    # nelle caselle di un modello con contribuente, codice fiscale e P.IVA.
    if re.fullmatch(r"\d{11}", str(company_id or "")) and all(
            re.search(p, text, re.I) for p in (r"CONTRIBUENTE", r"CODICE\s+FISCALE", r"PARTITA\s+IVA")):
        printed = r"(?<![A-Z0-9])" + r"\s*".join(company_id) + r"(?![A-Z0-9])"
        if len(re.findall(printed, text, re.I)) >= 2:
            return company_id
    return None


def _year(value):
    m = _YEAR.search(str(value or ""))
    return int(m[1]) if m else None


def _ident(value):
    m = _IDENT.search(str(value or ""))
    return f"{m[1]}-{m[2]}" if m else None


def document_identity(document: dict, text: str = "") -> dict:
    """Anno fiscale letto prima del nome file, mai la data della mail/invio."""
    quadri = document.get("quadri") or {}
    meta = document.get("source_metadata") or {}
    parsed = document.get("parsed_metadata") or {}
    name = str(document.get("filename") or "")
    kind = document.get("document_type")
    subject = _SUBJECT.search(text)
    cf = str((subject[2] if subject else None) or parsed.get("codice_fiscale")
             or meta.get("taxpayer_id") or document.get("codice_fiscale") or "").strip().upper()
    if not cf:
        cf = _printed_taxpayer(text, document.get("company_id")) or ""
    ident = _ident(quadri.get("identificativo") or parsed.get("identificativo_dichiarazione"))
    if not ident:
        evidence = re.search(r"Identificativo\s+dichiarazione\s*:\s*(\d{11}\s*-\s*\d{7})", text, re.I)
        ident = _ident(evidence[1] if evidence else name)
    tax_year = _year(quadri.get("anno_imposta") or parsed.get("anno_imposta") or meta.get("tax_year"))
    if tax_year is None:
        printed_year = re.search(r"(?:per\s+l['’]anno\s+d['’]imposta|periodo\s+d['’]imposta\s+dal\s+\d{2}/\d{2}/)\s*((?:19|20)\d{2})", text, re.I)
        tax_year = int(printed_year[1]) if printed_year else None
    if tax_year is None and kind == "LIPE" and re.search(r"Anno\s+di\s+imposta", text, re.I):
        # Anno nelle quattro caselle della copertina, distinto dalla data
        # d'impegno (giorno/mese/anno in blocchi) e dalle cifre del CF.
        without_cf = re.sub(r"\s*".join(cf), "", text) if cf else text
        printed_years = {int("".join(m)) for m in re.findall(
            r"(?m)^\s*(2)\s*\n\s*(0)\s*\n\s*(\d)\s*\n\s*(\d)\s*$", without_cf)}
        if len(printed_years) == 1:
            tax_year = printed_years.pop()
    if tax_year is None:
        explicit = re.search(r"(?:imposta|Modello\s+770\s*-\s*Anno)[_\s-]+((?:19|20)\d{2})", name, re.I)
        tax_year = int(explicit[1]) if explicit else None
    # Le stampe AdE del 770 riportano «Anno 2023» per il modello 770/2024.
    if tax_year is None and kind == "MODELLO_770" and ident:
        m = re.search(r"\bAnno\s+((?:19|20)\d{2})\b", text)
        tax_year = int(m[1]) if m else None
    model = re.search(r"(?:770|760|IVA|IRAP|REDDITI(?:\s*SC)?|UNICO|LIPE(?:_PRECOMPILATA)?)[_\s/-]+((?:19|20)\d{2})(?!\d)", name, re.I)
    model_year = _year(meta.get("filing_year")) or (int(model[1]) if model else None)
    if tax_year is None and model_year:
        tax_year = model_year if kind == "LIPE" else model_year - 1
    if model_year is None and tax_year:
        model_year = tax_year if kind == "LIPE" else tax_year + 1
    # Il CF nel nome AdE e' quello del dichiarante, non dell'intermediario.
    if not cf:
        m = re.search(r"_T\d+_([A-Z0-9]{11,16})(?:\s*\(\d+\))?\.pdf$", name, re.I)
        cf = m[1].upper() if m else ""
    return {"taxpayer_id": cf or None, "taxpayer_name": subject[1].strip() if subject else None,
            "declaration_identifier": ident, "tax_year": tax_year, "model_year": model_year,
            "filed_at": quadri.get("data_presentazione") or parsed.get("data_presentazione")}


def _original(doc, identity, version=None, *, component=False):
    version = version or {}
    parsed = doc.get("parsed_metadata") or {}
    name = str(doc.get("filename") or "")
    quadro = parsed.get("quadro")
    modulo = parsed.get("modulo")
    if not quadro:
        m = re.search(r"Quadro[_\s]+([A-Z]{2})(?:[_\s]+modulo[_\s]*(\d+))?", name, re.I)
        if m:
            quadro, modulo = m[1].upper(), int(m[2]) if m[2] else None
    role = "Frontespizio" if "frontespizio" in name.lower() else (
        f"Quadro {quadro}" + (f" · modulo {modulo}" if modulo else "") if quadro else "Dichiarazione / allegato")
    return {"id": doc["id"], "filename": name, "role": role,
            "pdf_url": url_originale("documento" if component else "documento_fiscale", doc["id"]),
            "sha256": version.get("sha256") or doc.get("sha256") or doc.get("file_hash"),
            "page_count": version.get("page_count") or doc.get("page_count"),
            "drive_file_id": doc.get("drive_file_id") or (doc.get("source_metadata") or {}).get("drive_file_id"),
            **identity}


def group_annual_dossiers(documents, components, pages, versions):
    """Proiezione pura. Nessuna scrittura contabile o rimozione di originali."""
    texts = defaultdict(list)
    by_version = {v["id"]: v for v in versions}
    current_versions = {d["id"]: d.get("current_version_id") for d in documents}
    for p in pages:
        if current_versions.get(p.get("document_id")) not in (None, p.get("version_id")):
            continue
        texts[p.get("document_id")].append((p.get("page_number") or 0, p.get("text") or ""))
    originals = []
    for doc in documents:
        identity = document_identity(doc, "\n".join(t for _, t in sorted(texts[doc["id"]])))
        originals.append({**_original(doc, identity, by_version.get(doc.get("current_version_id"))),
                          "document_type": doc["document_type"],
                          "tax_codes": sorted({str(r.get("codice_tributo")) for r in (doc.get("quadri") or {}).get("st_righe") or [] if r.get("codice_tributo")})})
    # Un quadro puo' non riportare l'anno; lo eredita solo dall'identificativo
    # esatto, e soltanto se tutti gli originali con quell'id concordano.
    by_ident = defaultdict(list)
    for doc in originals:
        if doc["declaration_identifier"]:
            by_ident[(doc["document_type"], doc["declaration_identifier"])].append(doc)
    for group in by_ident.values():
        for key in ("taxpayer_id", "taxpayer_name", "tax_year", "model_year"):
            known = {d[key] for d in group if d.get(key)}
            if len(known) == 1:
                for d in group:
                    if not d.get(key):
                        d[key] = next(iter(known))
    unlinked = []
    for doc in components:
        identity = document_identity(doc)
        kind = (doc.get("parsed_metadata") or {}).get("declaration_type") or "MODELLO_770"
        matches = by_ident.get((kind, identity["declaration_identifier"]), [])
        owners = {(m["taxpayer_id"], m["tax_year"]) for m in matches if m["taxpayer_id"] and m["tax_year"]}
        if len(owners) == 1:
            cf, year = next(iter(owners))
            if identity["taxpayer_id"] not in (None, cf) or identity["tax_year"] not in (None, year):
                unlinked.append(_original(doc, identity, component=True))
                continue
            parent = next(m for m in matches if m["taxpayer_id"] == cf and m["tax_year"] == year)
            identity = {**identity, **{k: parent[k] for k in ("taxpayer_id", "taxpayer_name", "tax_year", "model_year")}}
        elif matches or not identity["taxpayer_id"] or not identity["tax_year"]:
            unlinked.append(_original(doc, identity, component=True))
            continue
        originals.append({**_original(doc, identity, component=True), "document_type": kind, "tax_codes": []})

    groups = {}
    for original in originals:
        cf, year, kind = original["taxpayer_id"], original["tax_year"], original["document_type"]
        # Senza identita' fiscale non si accorpano file diversi ne' quietanze.
        key = (kind, cf or original["id"], year or original["id"])
        dossier = groups.setdefault(key, {
            "id": stable_id("declaration_dossier", *key), "document_type": kind,
            "taxpayer_id": cf, "taxpayer_name": original.get("taxpayer_name"), "tax_year": year,
            "originals": [], "quietanze": [], "tax_codes": set(TAX_CODES.get(kind, set())),
            "requires_review": not cf or not year,
        })
        dossier["tax_codes"].update(original.pop("tax_codes", []))
        dossier["originals"].append(original)
    result = []
    for dossier in groups.values():
        # Solo byte identici si presentano come copie. Mai deduplicare per anno,
        # nome o identificativo: ST modulo 1 e modulo 2 sono file diversi.
        unique = {}
        for original in sorted(dossier["originals"], key=lambda d: (d["role"] != "Frontespizio", d["filename"], d["id"])):
            key = (original.get("sha256") or original.get("drive_file_id") or original["id"])
            if key in unique:
                unique[key].setdefault("copies", []).append(original)
            else:
                unique[key] = original
        dossier["originals"] = list(unique.values())
        dossier["original_count"] = len(unique)
        dossier["submission_count"] = len({o["declaration_identifier"] or o["id"] for o in unique.values()})
        dossier["model_years"] = sorted({o["model_year"] for o in unique.values() if o["model_year"]})
        dossier["tax_codes"] = sorted(dossier["tax_codes"])
        dossier["filename"] = " · ".join(o["filename"] for o in unique.values())
        result.append(dossier)
    result.sort(key=lambda d: (d["tax_year"] or 0, d["document_type"], d["taxpayer_id"] or ""), reverse=True)
    return result, unlinked


def attach_receipts(dossiers, receipts):
    """Stesso CF + codice tributo pertinente + anno di riferimento, non data di invio."""
    by_cf = defaultdict(list)
    for q in receipts:
        raw = q.get("documento") or {}
        cf = str(raw.get("codice_fiscale") or (raw.get("dati_generali") or {}).get("codice_fiscale") or "").strip().upper()
        if cf:
            by_cf[cf].append(q)
    for dossier in dossiers:
        cf, year = dossier["taxpayer_id"], dossier["tax_year"]
        if not cf or not year:
            continue
        # Filtrare prima per CF evita che lo stesso protocollo di invio di
        # contribuenti diversi venga confuso dal raggruppamento dei versamenti.
        for payment in reg.pagamenti_da_quietanze(by_cf.get(cf, [])):
            rows = [r for r in payment["_righe"] if r.get("codice") in dossier["tax_codes"] and _year(r.get("anno")) == year]
            if rows:
                dossier["quietanze"].append({k: v for k, v in payment.items() if not k.startswith("_")} | {
                    "tax_rows": rows, "link_reason": "Stesso contribuente, codice tributo e anno d'imposta",
                })
        dossier["quietanze"].sort(key=lambda p: (p.get("data") or "", p["chiave"]), reverse=True)
        dossier["receipt_count"] = len(dossier["quietanze"])


async def list_annual_dossiers(db, *, company_id: str, year: int | None = None,
                              declaration_type: str | None = None) -> dict[str, Any]:
    query = {"company_id": company_id, "document_type": {"$in": sorted(DECLARATION_TYPES)}}
    documents = await db["fiscal_documents"].find(query, {"_id": 0, "pdf_data": 0}).to_list(10000)
    documents = [d for d in documents if d.get("entity_status") != "deleted"]
    ids = [d["id"] for d in documents]
    versions, pages, components, receipts = await asyncio.gather(
        db["fiscal_document_versions"].find({"company_id": company_id, "document_id": {"$in": ids}}, {"_id": 0}).to_list(10000),
        db["fiscal_pages"].find({"company_id": company_id, "document_id": {"$in": ids}, "page_number": {"$lte": 3}}, {"_id": 0, "layout_words": 0}).to_list(30000),
        db["documents_inbox"].find({"document_type": {"$in": ["componente_770", "componente_dichiarazione"]},
                                   "$or": [{"company_id": company_id}, {"company_id": {"$exists": False}}]},
                                  {"_id": 0, "pdf_data": 0}).to_list(10000),
        reg.carica_quietanze(db),
    )
    dossiers, unlinked = group_annual_dossiers(documents, [d for d in components if d.get("entity_status") != "deleted"], pages, versions)
    # I vecchi documenti con classificazione/anno non provati restano apribili,
    # ma non diventano falsi fascicoli annuali o ricevono quietanze per supposizione.
    for dossier in dossiers:
        if dossier["requires_review"]:
            unlinked.extend(dossier["originals"])
    dossiers = [d for d in dossiers if not d["requires_review"]]
    years = sorted({d["tax_year"] for d in dossiers if d["tax_year"]}, reverse=True)
    dossiers = [d for d in dossiers if (not year or d["tax_year"] == year)
                and (not declaration_type or d["document_type"] == declaration_type)]
    attach_receipts(dossiers, receipts)
    return {"items": dossiers, "total": len(dossiers), "years": years, "year": year,
            "declaration_type": declaration_type, "unlinked_components": unlinked,
            "sources": {"canonical": "fiscal_documents", "fiscal_documents": len(documents)},
            "grouping": "taxpayer_declaration_type_tax_year"}
