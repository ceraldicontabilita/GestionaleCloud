"""Read-only adapters for the shared MiniHR dossier. No imports or DB writes.

The existing posizione_dipendente service remains the accounting authority.
Site records, corrections and private PDFs never enter this adapter or git.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from app.hr.services.stato_rapporto import data_iso
from app.services import posizione_dipendente as pos

CORE_VERSION = "1.0.0"
START_MONTH = "2022-12"


def money_cents(value):
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
        return int((number * 100).quantize(Decimal("1"))) if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def calendar_month(year, month):
    try:
        year, month = int(year), int(month)
        month = {13: 12, 14: 6}.get(month, month)
        return date(year, month, 1).strftime("%Y-%m")
    except (ValueError, TypeError, OverflowError):
        return ""


def ident(value):
    return quote(str(value), safe="")


def roster_item(employee):
    return {"id": employee["id"], "name": employee.get("nome_completo") or
            " ".join(str(employee.get(k) or "") for k in ("cognome", "nome")).strip() or "Identità da verificare"}


def relationship_events(employee, documents):
    """Use explicit dates, never infer employment from amount or first payslip.

    The legacy end-date field has mixed last-day/decorrenza semantics: it is
    deliberately not converted to a verified cessation. The exact document
    remains accessible; subsequent payroll is not automatically suppressed.
    """
    start = data_iso(employee.get("data_assunzione"))
    if not start:
        return [], ["Data di assunzione non presente: rapporto da accertare."]
    events = [{"kind": "assunzione", "start": start, "effective": start,
               "verified": True, "label": "Data assunzione registrata in anagrafica",
               "source": "Anagrafica GestionaleCloud", "relationshipId": employee["id"] + "|" + start}]
    notices = ["Rapporti storici e riassunzioni da validare sui documenti; le date anagrafiche non provano da sole tutti gli intervalli."]
    # Do not keep an old open-ended relationship active past a recorded end
    # whose exact date semantics have not yet been validated.
    end = next((data_iso(employee.get(k)) for k in
                ("data_fine_rapporto", "data_cessazione", "data_dimissione", "data_cessazione_prevista")
                if data_iso(employee.get(k))), None)
    if end:
        events[0]["end"] = end
        notices.append("Cessazione registrata al " + end + ": verificare decorrenza sul documento. Nessuna cessazione presunta.")
    elif employee.get("attivo") is False or employee.get("stato") in ("cessato", "dimesso", "inattivo"):
        events = []
        notices.append("Rapporto indicato cessato senza data certa: nessun mese presunto in forza.")
    return events, notices


async def dossier(db, employee):
    dip_id = employee["id"]
    movements = await pos.carica_movimenti(db, dip_id)
    slips, payments = [], []
    for n, movement in enumerate(movements["registro"]):
        link = movement.get("link") or {}
        comp = movement.get("competenza")
        month = calendar_month(*comp) if comp else str(movement.get("data") or "")[:7]
        base = {"id": f"{movement.get('fonte')}:{link.get('cedolino_id') or link.get('key') or link.get('bonifico_da_associare_id') or n}",
                "type": movement.get("descrizione") or movement.get("tipo"), "month": month}
        if movement.get("tipo") == "busta":
            kind = {13: "Tredicesima", 14: "Quattordicesima"}.get(comp[1], "Ordinario") if comp else "Ordinario"
            slips.append({**base, "type": kind, "amountCents": money_cents(movement.get("dare")),
                          "url": f"/hr/api/cedolini/{ident(link['cedolino_id'])}/download" if link.get("cedolino_id") else "",
                          "counted": movement.get("dare") is not None, "isPayslip": True,
                          "documentConflict": bool(movement.get("avviso"))})
        elif movement.get("dare") is not None:
            slips.append({**base, "isPayslip": False, "amountCents": money_cents(movement["dare"]), "counted": True, "url": ""})
        if movement.get("avere") is not None:
            url = ""
            if link.get("key"):
                url = f"/hr/api/dipendenti-cloud/paghe/pagamento-esito/{ident(link['key'])}/pdf"
            elif link.get("bonifico_da_associare_id"):
                url = f"/hr/api/dipendenti-cloud/bonifici-da-associare/{ident(link['bonifico_da_associare_id'])}/pdf"
            payments.append({**base, "date": movement.get("data"), "amountCents": money_cents(movement["avere"]),
                             "reference": movement.get("descrizione"), "counted": True, "url": url})
    # Whitelist fields: never expose file_data, signatures, PINs or auth data.
    raw_docs = await db.documenti_cloud.find({"dipendente_id": dip_id},
        {"_id": 0, "id": 1, "titolo": 1, "tipo": 1, "competenza": 1, "anno": 1, "mese": 1}).to_list(2000)
    documents = [{"id": d["id"], "type": d.get("tipo") or "Documento", "label": d.get("titolo") or "Documento",
                  "month": str(d.get("competenza") or calendar_month(d.get("anno"), d.get("mese")))[:7],
                  "isPayslip": False, "url": f"/hr/api/dipendenti-cloud/documenti/{ident(d['id'])}/file"}
                 for d in raw_docs if d.get("id")]
    events, notices = relationship_events(employee, documents)
    undated = [d for d in documents if len(d["month"]) != 7]
    if undated:
        notices.append(f"{len(undated)} documenti senza competenza certa: consultabili sotto, non assegnati a un mese usando la data di caricamento.")
    out = {**roster_item(employee), "events": events, "slips": slips, "payments": payments,
           "documents": documents, "excludedYears": []}
    return {"schemaVersion": 1, "coreVersion": CORE_VERSION, "mode": "read-only", "employee": out,
            "companyFiscalCode": str(employee.get("datore_codice_fiscale") or employee.get("azienda_codice_fiscale") or ""),
            "undatedDocuments": undated,
            "notices": ["Fonte: solo archivi GestionaleCloud. Nessuna fusione con Site e nessuna applicazione implicita delle sue esclusioni.",
                        "Importi dal motore Posizione dipendente esistente. TFR autonomi e bonus restano nelle rispettive sezioni e non vengono sommati al saldo paghe.",
                        "Il saldo parte da zero nel periodo selezionato; non è un saldo di apertura certificato."] + notices}


async def company_f24(db, fiscal_code):
    """Read the main ERP register, not a second HR copy; no fascicolo builder."""
    from app.db_collections import COLL_F24
    from app.services.f24_controllo_incrociato import righe_modello, modello_attivo
    from app.services.f24_payment_evidence import stato_evidenza_pagamento
    from app.services.originale_documento import url_originale

    fields = {"_id": 0, "pdf_data": 0, "file_data": 0}
    records = await db[COLL_F24].find({"$or": [{"codice_fiscale": fiscal_code},
        {"dati_generali.codice_fiscale": fiscal_code}], "status": {"$ne": "eliminato"}}, fields).to_list(5000)
    rows, seen = [], set()
    for record in records:
        cf = str(record.get("codice_fiscale") or (record.get("dati_generali") or {}).get("codice_fiscale") or "").strip().upper()
        if cf != fiscal_code or not record.get("id") or record["id"] in seen or not modello_attivo(record):
            continue
        seen.add(record["id"])
        lines = righe_modello(record)
        # Keep annual and unclear periods visible. No allocation by due date.
        lines = [r for r in lines if not r.get("anno") or r["anno"] > 2022 or
                 r["anno"] == 2022 and (not r.get("mese") or r["mese"] == 12)]
        if not lines:
            continue
        evidence = stato_evidenza_pagamento(record)
        rows.append({"id": record["id"], "url": url_originale("f24", record["id"]), "lines": lines,
                     "evidence": {k: evidence.get(k) for k in ("stato", "verificato_banca", "versato_documentalmente", "quietanza_presente")}})
    return {"mode": "read-only", "fiscalCode": fiscal_code, "documents": rows,
            "notice": "F24 aziendali dal registro fiscale esistente: non attribuiti al singolo dipendente e mai aggiunti al suo saldo. Periodi annuali o incerti restano da verificare; quietanza e banca sono prove distinte."}
