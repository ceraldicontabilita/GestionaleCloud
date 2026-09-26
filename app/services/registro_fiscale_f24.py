"""Righe tributo F24 per Situazione fiscale, lette dal registro unico F24.

Prima la pagina leggeva un indice Excel (``INDICE_DOCUMENTALE_DRIVE.xlsx``)
dentro la cartella del vecchio canale cedolini: smontata la cartella, ogni
scheda andava in errore «Credenziali Google Drive non disponibili». Qui non
c'e' un secondo registro: modelli, quietanze e addebiti vengono da
``f24_controllo_incrociato.carica_registro`` (una lettura sola) e lo stato di
ogni modello da ``prove_modello`` / ``_esito_da_prove``, gli stessi di
Piano tributi.

Modello e quietanza restano prove distinte: un modello F24 non prova il
pagamento, la quietanza lo documenta ma non sostituisce la banca.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.db_collections import COLL_QUIETANZE_F24
from app.services import f24_controllo_incrociato as reg

SOURCE_KIND_RIGA = "F24_REGISTRO_ROW"
QUIETANZA = "QUIETANZA_DOCUMENTALE_NON_PROVA_BANCARIA"
MODELLO = "MODELLO_F24_NON_PROVA_BANCARIA"


def _periodo(riga: Dict[str, Any]) -> str:
    if riga.get("periodo_riferimento"):
        return str(riga["periodo_riferimento"])
    return reg.etichetta_periodo({"mese": riga.get("mese"), "anno": riga.get("anno")}) if riga.get("anno") else ""


def _righe_documento(
    *, document_id: str, filename: str, data: Optional[str], protocollo: Optional[str],
    righe: List[Dict[str, Any]], quietanza: bool, source_role: str, evidence_reason: str,
    pdf_url: Optional[str], esito: Optional[str] = None, motivo: Optional[str] = None,
) -> List[Dict[str, Any]]:
    out = []
    for n, r in enumerate(righe, start=1):
        out.append({
            "id": f"{document_id}:{n}",
            "document_id": document_id,
            "ordinal": n,
            "source_kind": SOURCE_KIND_RIGA,
            "payment_year": data[:4] if data else None,
            "payment_date": data,
            "section": r.get("sezione"),
            "tax_code": r.get("codice"),
            "description": r.get("descrizione"),
            "reference_period": _periodo(r),
            "debit_amount": reg.euro(r.get("importo_debito_cents") or 0),
            "credit_amount": reg.euro(r.get("importo_credito_cents") or 0),
            "protocol": protocollo,
            "filename": filename,
            "evidence_state": QUIETANZA if quietanza else MODELLO,
            "source_role": source_role,
            "evidence_reason": evidence_reason,
            "payment_status": "DOCUMENTATO_DA_QUIETANZA" if quietanza else "MODELLO_F24_PRESENTE",
            "documentary_payment_status": "QUIETANZA_PRESENTE" if quietanza else "DA_VERIFICARE",
            "bank_status": "DA_VERIFICARE",
            "registro_esito": esito,
            "registro_motivo": motivo,
            "pdf_url": pdf_url,
        })
    return out


def righe_da_registro(registro: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Tutte le righe: prima dei modelli, poi delle quietanze che ne hanno."""
    righe: List[Dict[str, Any]] = []
    for f24 in registro["f24"]:
        fid = str(f24.get("id") or "")
        if not fid:
            continue
        prove = reg.prove_modello(f24, registro)
        esito, motivo = reg._esito_da_prove(prove)
        protocolli = sorted(reg.protocolli_modello(f24))
        righe.extend(_righe_documento(
            document_id=fid,
            filename=str(f24.get("file_name") or f24.get("filename") or ""),
            data=prove["data_versamento"],
            protocollo=protocolli[0] if protocolli else None,
            righe=reg.righe_modello(f24),
            quietanza=False,
            source_role="MODELLO_F24_COMMERCIALISTA",
            evidence_reason="REGISTRO_F24_MODELLO_NON_PROVA_PAGAMENTO",
            pdf_url=reg.PDF_F24_URL.format(f24_id=fid),
            esito=esito, motivo=motivo,
        ))
    for q in registro["quietanze"]:
        # Le quietanze in fiscal_documents non portano le righe tributo: si
        # contano nel riepilogo, non diventano righe inventate.
        if q.get("fonte") != COLL_QUIETANZE_F24 or not q.get("righe") or not q.get("id"):
            continue
        righe.extend(_righe_documento(
            document_id=str(q["id"]),
            filename=str(q.get("filename") or ""),
            data=q.get("data"),
            protocollo=q.get("protocollo_originale"),
            righe=q["righe"],
            quietanza=True,
            source_role="QUIETANZA_UFFICIALE_ADE",
            evidence_reason="QUIETANZA_CON_PROTOCOLLO" if q.get("protocollo") else "QUIETANZA_SENZA_PROTOCOLLO",
            pdf_url=None,
        ))
    righe.sort(key=lambda r: (str(r.get("payment_date") or ""), str(r.get("filename") or ""),
                              -int(r.get("ordinal") or 0)), reverse=True)
    return righe


def filtra_righe(
    righe: List[Dict[str, Any]], *, year: Optional[int] = None, tax_code: Optional[str] = None,
    document_id: Optional[str] = None, credits_only: bool = False,
) -> List[Dict[str, Any]]:
    codice = reg.normalizza_codice(tax_code) if tax_code else None
    return [
        r for r in righe
        if (not year or str(r.get("payment_year") or "") == str(year))
        and (not codice or r.get("tax_code") == codice)
        and (not document_id or r.get("document_id") == document_id)
        and (not credits_only or (r.get("credit_amount") or 0) > 0)
    ]


def obblighi(righe: List[Dict[str, Any]], status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Deleghe intere (righe a debito e a credito insieme) per stato.

    ``TO_PAY``: modelli che il registro dice ancora da pagare (niente
    quietanza, niente addebito) con saldo positivo. ``PAID_ON_TIME``: le
    deleghe documentate da quietanza.
    """
    per_documento: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in righe:
        per_documento[r["document_id"]].append(r)
    stato = str(status or "").strip().lower()
    scelti = set(per_documento)
    if stato in {"to_pay", "da_pagare"}:
        scelti = {
            doc for doc, rs in per_documento.items()
            if rs[0].get("registro_esito") == reg.ESITO_DA_PAGARE
            and sum((r.get("debit_amount") or 0) - (r.get("credit_amount") or 0) for r in rs) > 0
        }
    elif stato in {"paid_on_time", "documented", "quietanza_presente"}:
        scelti = {doc for doc, rs in per_documento.items() if rs[0].get("evidence_state") == QUIETANZA}
    return [r for r in righe if r["document_id"] in scelti]


def conteggi(registro: Dict[str, Any], righe: List[Dict[str, Any]], dichiarazioni: int) -> Dict[str, int]:
    documenti_quietanza = {r["document_id"] for r in righe if r["evidence_state"] == QUIETANZA}
    return {
        "f24_documents": len(registro["f24"]),
        "f24_rows": len(righe),
        "declarations": dichiarazioni,
        "tax_debit_rows": sum(1 for r in righe if (r.get("debit_amount") or 0) > 0),
        "documentary_payment_documents": len(documenti_quietanza),
        "quietanze_senza_righe": sum(
            1 for q in registro["quietanze"]
            if q.get("fonte") != COLL_QUIETANZE_F24 or not q.get("righe")
        ),
    }
