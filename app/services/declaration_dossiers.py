"""Fascicolo annuale in lettura: originali distinti, stesso contribuente e anno.

Un invio puo' avere un frontespizio e molti quadri PDF separati. L'identificativo
della dichiarazione li unisce; l'anno di imposta riunisce gli invii nel fascicolo,
senza scegliere una versione vincente o sommare le dichiarazioni. Le quietanze
provengono dal registro unico, anche in assenza del modello F24.
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter
from collections import defaultdict
from datetime import date
from typing import Any

from app.db_collections import COLL_FISCAL_DOCUMENT_VERSIONS, COLL_FISCAL_PAGES
from app.constants.codici_ravvedimento import SANZIONI_RITENUTE_PER_CODICE
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
                          "withholding_rows": [dict(r) for k in ("st_righe", "sv_righe") for r in (doc.get("quadri") or {}).get(k) or []],
                          "tax_codes": sorted({str(r.get("codice_tributo")) for k in ("st_righe", "sv_righe") for r in (doc.get("quadri") or {}).get(k) or [] if r.get("codice_tributo")})})
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
        parsed_quadri = (doc.get("parsed_metadata") or {}).get("quadri") or {}
        withholding_rows = [dict(r) for k in ("st_righe", "sv_righe") for r in parsed_quadri.get(k) or []]
        originals.append({**_original(doc, identity, component=True), "document_type": kind,
                          "withholding_rows": withholding_rows,
                          "tax_codes": sorted({str(r["codice_tributo"]) for r in withholding_rows if r.get("codice_tributo")})})

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
        payments = reg.pagamenti_da_quietanze(by_cf.get(cf, []))
        for payment in payments:
            rows = [r for r in payment["_righe"] if r.get("codice") in dossier["tax_codes"] and _year(r.get("anno")) == year]
            if rows:
                dossier["quietanze"].append({k: v for k, v in payment.items() if not k.startswith("_")} | {
                    "tax_rows": rows, "link_reason": "Stesso contribuente, codice tributo e anno d'imposta",
                })
        if dossier["document_type"] == "MODELLO_770":
            dossier["withholding_check"] = reconcile_withholdings(dossier["originals"], payments)
            # Anche le quietanze dell'anno dei redditi precedente e quelle
            # delle sanzioni devono restare nel fascicolo quando provate dai
            # righi ST/SV, senza cambiare il loro riferimento stampato.
            attached = {p["chiave"]: p for p in dossier["quietanze"]}
            by_key = {p["chiave"]: p for p in payments}
            for group in dossier["withholding_check"]["groups"]:
                for link in [*group["payments"], *group["sanzioni"]]:
                    key = link["chiave"]
                    payment = by_key[key]
                    entry = attached.setdefault(key, {k: v for k, v in payment.items() if not k.startswith("_")} | {
                        "tax_rows": [], "link_reason": "Riscontro sui righi ST/SV della dichiarazione"})
                    row = link.get("receipt_row") or link.get("row")
                    if row not in entry["tax_rows"]:
                        entry["tax_rows"].append(row)
            dossier["quietanze"] = list(attached.values())
        dossier["quietanze"].sort(key=lambda p: (p.get("data") or "", p["chiave"]), reverse=True)
        dossier["receipt_count"] = len(dossier["quietanze"])


def _withholding_section(row):
    if str(row.get("rigo", "")).startswith("SV"):
        return "sezione_tributi_locali"
    return "sezione_regioni" if row.get("sezione") == "II" else "sezione_erario"


def _row_signature(row):
    return tuple(row.get(k) for k in ("sezione", "codice_tributo", "anno", "mese", "regione",
        "ritenute_operate_cents", "crediti_scomputo_cents", "importo_versato_cents", "interessi_cents",
        "data_versamento", "ravvedimento", "note"))


def _declared_withholdings(originals):
    """Una casella per invio/quadro/modulo/rigo, con tutti i PDF che la provano.

    Invii distinti restano distinti: non si presume che l'ultimo sostituisca
    tutto il precedente (il 770 puo' essere trasmesso in gestione separata).
    """
    cells = {}
    known_modules = defaultdict(set)
    for original in originals:
        for source in [original, *original.get("copies", [])]:
            for row in source.get("withholding_rows", []):
                if row.get("modulo"):
                    known_modules[(source.get("declaration_identifier") or source["id"], row.get("rigo"), _row_signature(row))].add(row["modulo"])
    for original in originals:
        for source in [original, *original.get("copies", [])]:
            for row in source.get("withholding_rows", []):
                invio = source.get("declaration_identifier") or source["id"]
                module = row.get("modulo")
                matches = known_modules.get((invio, row.get("rigo"), _row_signature(row)), set())
                if module is None and len(matches) == 1:
                    module = next(iter(matches))
                coordinate = (module, row.get("rigo")) if module else (
                    row.get("pagina"), row.get("rigo"), _row_signature(row))
                key = (invio, *coordinate)
                source_ref = {k: source.get(k) for k in ("id", "filename", "pdf_url", "declaration_identifier")}
                source_ref["page"] = row.get("pagina")
                if key not in cells:
                    cells[key] = {**row, "modulo": module, "submission": invio, "sources": [], "conflicting_source": False}
                elif _row_signature(cells[key]) != _row_signature(row):
                    cells[key]["conflicting_source"] = True
                cells[key]["sources"].append(source_ref)
    return list(cells.values())


def reconcile_withholdings(originals, payments):
    """Riscontro per riga dichiarata sul registro delle quietanze, senza F24.

    Solo stesso contribuente (filtrato dal chiamante), sezione, codice,
    anno e mese. Data/importo distinguono versamenti dello stesso periodo.
    Addizionali a saldo e recupero 1701 possono riferirsi ai redditi dell'anno
    precedente: in quel caso servono anche data esatta e totale esatto.
    Sanzioni e crediti non aumentano l'importo del tributo pagato.
    """
    from app.services.scadenzario_tributi import scadenza_da_regola

    groups = {}
    for row in _declared_withholdings(originals):
        tax_key = (_withholding_section(row), row.get("codice_tributo"), row.get("anno"), row.get("mese"))
        key = (row["submission"], *tax_key, row.get("data_versamento"), row.get("regione"))
        group = groups.setdefault(key, {"id": stable_id("withholding_check", *key), "submission": row["submission"],
            "sezione": tax_key[0], "codice": tax_key[1], "anno": tax_key[2], "mese": tax_key[3],
            "data_dichiarata": row.get("data_versamento"), "ente": row.get("regione"), "rows": []})
        group["rows"].append(row)
    result = []
    claims = defaultdict(list)
    for group in groups.values():
        rows = group["rows"]
        expected = [r.get("importo_versato_cents") for r in rows]
        total = sum(expected) if all(isinstance(n, int) for n in expected) else None
        by_date = defaultdict(list)
        prior_year = defaultdict(list)
        for payment in payments:
            for index, receipt_row in enumerate(payment.get("_righe", [])):
                if (receipt_row.get("sezione"), receipt_row.get("codice"), receipt_row.get("mese")) != (
                        group["sezione"], group["codice"], group["mese"]):
                    continue
                if group["ente"] and str(receipt_row.get("ente") or "").lstrip("0") != str(group["ente"]).lstrip("0"):
                    continue
                if int(receipt_row.get("importo_debito_cents") or 0) <= 0:
                    continue
                if receipt_row.get("anno") == group["anno"]:
                    by_date[payment.get("data")].append((payment, index, receipt_row))
                elif (group["anno"] and receipt_row.get("anno") == group["anno"] - 1
                      and (group["codice"] in {"3802", "3848"}
                           or (group["codice"] == "1701" and all("P" in (r.get("note") or "") for r in rows)))):
                    # Istruzioni AdE 770/2025, quadri ST/SV: il periodo della
                    # trattenuta non coincide sempre con l'anno del reddito F24.
                    # Non estendere ad altri codici né modificare l'anno fonte.
                    prior_year[payment.get("data")].append((payment, index, receipt_row))
        selected = by_date.get(group["data_dichiarata"], []) if group["data_dichiarata"] else []
        date_differs = False
        same_day_prior = prior_year.get(group["data_dichiarata"], []) if group["data_dichiarata"] else []
        if same_day_prior and sum(r["importo_debito_cents"] for _, _, r in [*selected, *same_day_prior]) == total:
            selected = [*selected, *same_day_prior]
        if not selected and total is not None:
            exact = [items for d, items in by_date.items() if d and sum(r["importo_debito_cents"] for _, _, r in items) == total]
            if len(exact) == 1:
                selected = exact[0]
                date_differs = True
        paid = sum(r["importo_debito_cents"] for _, _, r in selected) if selected else 0
        ravv_declared = any(r.get("ravvedimento") for r in rows)
        # Codici specifici delle sanzioni del sostituto. La sola presenza di
        # una sanzione IVA nello stesso F24 non ravvede le ritenute.
        sanctions = []
        for payment in payments:
            if not selected or payment.get("data") not in {p.get("data") for p, _, _ in selected}:
                continue
            for receipt_row in payment.get("_righe", []):
                if (receipt_row.get("codice") in SANZIONI_RITENUTE_PER_CODICE.get(group["codice"], set())
                        and receipt_row.get("sezione") == group["sezione"]
                        and (receipt_row.get("anno"), receipt_row.get("mese")) in {
                            (r.get("anno"), r.get("mese")) for _, _, r in selected}
                        and (not group["ente"] or str(receipt_row.get("ente") or "").lstrip("0") == str(group["ente"]).lstrip("0"))
                        and receipt_row.get("importo_debito_cents", 0) > 0):
                    sanctions.append({"chiave": payment["chiave"], "row": receipt_row, "quietanze": payment["quietanze"], "data": payment["data"],
                                      "note": "Sanzione del codice/periodo; nessuna ripartizione arbitraria fra più ritenute."})
        warnings = []
        reference_years = sorted({r["anno"] for _, _, r in selected})
        if any(y != group["anno"] for y in reference_years):
            warnings.append(f"Trattenuta nel 770: {group['mese']:02d}/{group['anno']}; anno dei redditi in quietanza: "
                            + ", ".join(map(str, reference_years)) + ". Collegamento verificato per codice, mese, data e importo.")
        if date_differs:
            warnings.append("La data della quietanza differisce da quella dichiarata nel 770.")
        if ravv_declared and selected and not sanctions:
            warnings.append("Ravvedimento indicato nel 770; sanzione pertinente non individuata nelle quietanze.")
        if sanctions and not ravv_declared:
            warnings.append("Sanzione di ravvedimento presente; casella ravvedimento non marcata nel 770.")
        links = [{"chiave": p["chiave"], "data": p["data"], "protocollo": p.get("protocollo"),
                  "importo_cents": r["importo_debito_cents"], "quietanze": p["quietanze"], "receipt_row": r}
                 for p, _, r in selected]
        if not group["codice"] or not group["anno"] or not group["mese"] or total is None or any(r["conflicting_source"] for r in rows):
            state, label = "DA_VERIFICARE", "Dati della dichiarazione da verificare"
        elif selected and paid == total:
            state, label = ("PAGATO_RAVVEDIMENTO", "Pagato · ravvedimento") if ravv_declared or sanctions else ("PAGATO", "Pagato")
            scadenza, _ = scadenza_da_regola(group["sezione"], group["codice"], group["anno"], group["mese"])
            if not ravv_declared and not sanctions and scadenza and any(p.get("data") and date.fromisoformat(p["data"]) > scadenza for p, _, _ in selected):
                warnings.append("Pagamento dopo la scadenza ordinaria; ravvedimento da verificare.")
        elif selected:
            state, label = "IMPORTO_DIVERSO", "Importo quietanzato diverso dal 770"
        elif total == 0:
            state, label = "NESSUN_VERSAMENTO", "Nessun versamento dichiarato"
        elif by_date or prior_year:
            state, label = "DA_VERIFICARE", "Quietanze del periodo: abbinamento da verificare"
        else:
            state, label = "QUIETANZA_MANCANTE", "Pagamento non documentato · quietanza mancante"
        group.update({"stato": state, "stato_label": label, "dichiarato_cents": total,
            "quietanzato_cents": paid, "differenza_cents": paid - total if total is not None and selected else None,
            "ravvedimento_dichiarato": ravv_declared, "sanzioni": sanctions, "warnings": warnings,
            "payments": links, "candidates": [
                {"data": d, "importo_cents": sum(r["importo_debito_cents"] for _, _, r in items),
                 "anni_riferimento": sorted({r["anno"] for _, _, r in items}),
                 "quietanze": [q for p, _, _ in items for q in p["quietanze"]]}
                for d in sorted(set(by_date) | set(prior_year), key=lambda d: d or "")
                if (items := [item for item in [*by_date[d], *prior_year[d]] if item not in selected])]})
        for payment, index, _ in selected:
            claims[(payment["chiave"], index)].append(group)
        result.append(group)
    for owners in claims.values():
        if len(owners) > 1:
            for group in owners:
                group["stato"], group["stato_label"] = "DA_VERIFICARE", "Quietanza richiamata da più righe o invii"
    result.sort(key=lambda g: (g["submission"], g["codice"] or "", g["anno"] or 0, g["mese"] or 0, g["data_dichiarata"] or ""))
    return {"groups": result, "declared_rows": sum(len(g["rows"]) for g in result),
            "counts": dict(Counter(g["stato"] for g in result)), "basis": "quietanze_per_codice_periodo_importo_data"}


async def list_annual_dossiers(db, *, company_id: str, year: int | None = None,
                              declaration_type: str | None = None) -> dict[str, Any]:
    query = {"company_id": company_id, "document_type": {"$in": sorted(DECLARATION_TYPES)}}
    if declaration_type:
        query["document_type"] = declaration_type
    documents = await db["fiscal_documents"].find(query, {"_id": 0, "pdf_data": 0}).to_list(10000)
    documents = [d for d in documents if d.get("entity_status") != "deleted"]
    ids = [d["id"] for d in documents]
    versions, pages, components, receipts = await asyncio.gather(
        db[COLL_FISCAL_DOCUMENT_VERSIONS].find({"company_id": company_id, "document_id": {"$in": ids}}, {"_id": 0}).to_list(10000),
        db[COLL_FISCAL_PAGES].find({"company_id": company_id, "document_id": {"$in": ids}, "page_number": {"$lte": 3}}, {"_id": 0, "layout_words": 0}).to_list(30000),
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
