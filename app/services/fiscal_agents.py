"""Controlli e dossier deterministici: l'AI non diventa fonte fiscale."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.db_collections import COLL_FISCAL_DOCUMENTS, COLL_TAX_COLLECTION_CLAIMS, COLL_TAX_OBLIGATIONS
from app.services.fiscal_domain import sha256_bytes


class FiscalControlAgent:
    @staticmethod
    def review(*, obligations: list[dict], claims: list[dict]) -> list[dict[str, Any]]:
        findings = []
        for item in claims:
            if item.get("residual_cents") == 0 and not item.get("payment_evidence"):
                findings.append({"severity": "warning", "code": "ZERO_WITHOUT_PAYMENT_EVIDENCE", "entity_id": item.get("collection_number"), "message": "Residuo zero senza prova di pagamento."})
            if item.get("business_status") in {"DA_VERIFICARE", "CONTESTATA"}:
                findings.append({"severity": "warning", "code": "COLLECTION_REVIEW_REQUIRED", "entity_id": item.get("collection_number"), "message": "Lo stato portale non chiude la verifica sostanziale."})
        for item in obligations:
            if not item.get("evidence_ids") and not item.get("source_evidence_ids"):
                findings.append({"severity": "warning", "code": "OBLIGATION_WITHOUT_EVIDENCE", "entity_id": item.get("id"), "message": "Obbligo privo di prova documentale."})
        return findings


class AdvisorBriefGenerator:
    @staticmethod
    def build(*, company_id: str, obligations: list[dict], claims: list[dict], findings: list[dict]) -> dict:
        return {
            "company_id": company_id,
            "title": "Dossier di revisione fiscale",
            "scope": "Bozza interna: richiede validazione del consulente",
            "counts": {"obligations": len(obligations), "collection_claims": len(claims), "findings": len(findings)},
            "questions": [finding["message"] for finding in findings],
            "automatic_submission": False,
            "disclaimer": "Nessun invio eseguito. Documenti e regole versionate restano le fonti.",
        }


def buildTaxReviewDossier(brief: dict[str, Any], findings: list[dict[str, Any]]) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    _, height = A4
    y = height - 55
    pdf.setTitle(brief["title"])
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(45, y, brief["title"])
    y -= 25
    pdf.setFont("Helvetica", 9)
    for line in (brief["scope"], f"Azienda: {brief['company_id']}", brief["disclaimer"]):
        pdf.drawString(45, y, line[:110]); y -= 15
    y -= 8
    for finding in findings or [{"code": "NO_FINDINGS", "message": "Nessuna anomalia deterministica rilevata."}]:
        if y < 65:
            pdf.showPage(); y = height - 55; pdf.setFont("Helvetica", 9)
        pdf.drawString(50, y, f"- {finding['code']}: {finding['message']}"[:115]); y -= 15
    pdf.save()
    return output.getvalue()


async def load_review_data(db, company_id: str) -> tuple[list[dict], list[dict]]:
    obligations = await db[COLL_TAX_OBLIGATIONS].find({"company_id": company_id}, {"_id": 0}).to_list(5000)
    claims = await db[COLL_TAX_COLLECTION_CLAIMS].find({"company_id": company_id}, {"_id": 0}).to_list(5000)
    return obligations, claims


async def buildTaxEvidencePackage(db, *, company_id: str) -> bytes:
    obligations, claims = await load_review_data(db, company_id)
    findings = FiscalControlAgent.review(obligations=obligations, claims=claims)
    brief = AdvisorBriefGenerator.build(company_id=company_id, obligations=obligations, claims=claims, findings=findings)
    dossier = buildTaxReviewDossier(brief, findings)
    output = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dossier_revisione.pdf", dossier)
        manifest.append({"name": "dossier_revisione.pdf", "sha256": sha256_bytes(dossier), "generated": True})
        archive.writestr("brief_consulente_BOZZA.json", json.dumps(brief, ensure_ascii=False, indent=2))
        documents = await db[COLL_FISCAL_DOCUMENTS].find({"company_id": company_id}, {"_id": 0}).to_list(5000)
        for document in documents:
            inbox_id = (document.get("metadata") or {}).get("documents_inbox_id")
            query = {"id": inbox_id} if inbox_id else {"company_id": company_id, "fiscal_document_id": document.get("id")}
            source = await db["documents_inbox"].find_one(query, {"_id": 0, "filename": 1, "pdf_data": 1})
            if not source or not source.get("pdf_data"):
                continue
            content = base64.b64decode(source["pdf_data"])
            name = f"documenti/{document['id']}.pdf"
            archive.writestr(name, content)
            manifest.append({"name": name, "sha256": sha256_bytes(content), "generated": False})
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("BOZZA_RICHIESTA_RIESAME.txt", "BOZZA NON INVIATA. Verificare e approvare manualmente.\n")
    return output.getvalue()
