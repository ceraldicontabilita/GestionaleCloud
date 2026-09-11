from pathlib import Path
import re


def replace_once(path, old, new, label):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Preview: four evidence states, never confidence=1 merely because type != auto.
path = Path("app/services/document_import_preview.py")
text = path.read_text(encoding="utf-8")
anchor = "TOKEN_TTL_SECONDS = 30 * 60\n\n\n"
helper = '''TOKEN_TTL_SECONDS = 30 * 60

EVIDENCE_STATUSES = {"verificato", "probabile", "non_verificato", "conflitto"}


def _preview_evidence_state(
    document_type: str, parsed: dict[str, Any], validation: dict[str, Any],
    blocking_errors: list[str],
) -> tuple[str, float, str]:
    """Return evidence status without promoting recognition into certainty."""
    if blocking_errors:
        return "conflitto", 0.0, "parser_o_validazione_in_conflitto"
    if document_type == "auto":
        return "non_verificato", 0.0, "tipo_documento_non_dimostrato"

    parsed = parsed if isinstance(parsed, dict) else {}
    explicit = str(parsed.get("evidence_status") or "").strip().lower()
    if explicit in EVIDENCE_STATUSES:
        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 1.0 if explicit == "verificato" else 0.85
        return explicit, max(0.0, min(float(confidence), 1.0)), "stato_probatorio_esplicito_parser"

    if parsed.get("requires_review") is True:
        return "non_verificato", 0.4, "parser_richiede_revisione"

    if document_type in {"f24", "quietanza_f24"} and validation.get("saldo_quadrato") is True:
        return "verificato", 1.0, "f24_quadrato_da_parser_specialistico"

    if parsed:
        return "probabile", 0.85, "parser_specialistico_senza_validazione_probatoria_completa"
    return "probabile", 0.65, "tipo_riconosciuto_da_confermare"


'''
if anchor not in text:
    raise SystemExit("preview helper anchor missing")
text = text.replace(anchor, helper, 1)
old = '''    duplicates = await _duplicate_sources(db, sha256, md5)
    return {
        "success": not blocking_errors,
        "preview_only": True,
        "filename": filename,
        "document_type": document_type,
        "tipo_rilevato": document_type,
        "classification": {
            "document_type": document_type,
            "confidence": 1.0 if document_type != "auto" else 0.0,
            "reason": "classificatore_deterministico_upload_auto",
            "classifier_version": PARSER_VERSION,
        },
'''
new = '''    duplicates = await _duplicate_sources(db, sha256, md5)
    evidence_status, confidence, classification_reason = _preview_evidence_state(
        document_type, parsed, validation, blocking_errors
    )
    return {
        "success": not blocking_errors,
        "preview_only": True,
        "filename": filename,
        "document_type": document_type,
        "tipo_rilevato": document_type,
        "evidence_status": evidence_status,
        "classification": {
            "document_type": document_type,
            "evidence_status": evidence_status,
            "confidence": confidence,
            "reason": classification_reason,
            "classifier_version": PARSER_VERSION,
        },
'''
if text.count(old) != 1:
    raise SystemExit("preview classification block mismatch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 2) Archive contract: evidence status independent from operational status.
path = Path("app/routers/documenti.py")
text = path.read_text(encoding="utf-8")
anchor = '_ARCHIVE_STATUSES = {"nuovo", "processato", "errore"}\n'
helper = '''_ARCHIVE_STATUSES = {"nuovo", "processato", "errore"}
_EVIDENCE_STATUSES = {"verificato", "probabile", "non_verificato", "conflitto"}


def _archive_evidence_status(item: Dict[str, Any]) -> str:
    """Derive display status conservatively; legacy records are never auto-verified."""
    parsed = item.get("parsed_metadata") if isinstance(item.get("parsed_metadata"), dict) else {}
    classification = item.get("classification") if isinstance(item.get("classification"), dict) else {}
    for candidate in (
        item.get("evidence_status"),
        classification.get("evidence_status"),
        parsed.get("evidence_status"),
    ):
        normalized = str(candidate or "").strip().lower()
        if normalized in _EVIDENCE_STATUSES:
            return normalized

    if item.get("status") == "errore" or item.get("processing_error") or item.get("error"):
        return "conflitto"
    if parsed.get("requires_review") is True or classification.get("requires_review") is True:
        return "non_verificato"
    if (
        parsed
        and parsed.get("requires_review") is False
        and (parsed.get("parser_version") or item.get("parser_version"))
    ):
        return "probabile"
    if (
        classification
        and classification.get("requires_review") is False
        and isinstance(classification.get("confidence"), (int, float))
        and float(classification["confidence"]) >= 0.8
    ):
        return "probabile"
    return "non_verificato"
'''
if text.count(anchor) != 1:
    raise SystemExit("archive status anchor mismatch")
text = text.replace(anchor, helper, 1)
old = '    item["size_bytes"] = item.get("size_bytes") or item.get("file_size") or 0\n\n    anomalies: List[str] = []\n'
new = '    item["size_bytes"] = item.get("size_bytes") or item.get("file_size") or 0\n    item["evidence_status"] = _archive_evidence_status(item)\n\n    anomalies: List[str] = []\n'
if text.count(old) != 1:
    raise SystemExit("archive metadata insertion point mismatch")
text = text.replace(old, new, 1)
old = '''        "parsed_metadata": parsed_metadata,
        "obligation_status": parsed_metadata.get("obligation_status") or "APERTO",
'''
new = '''        "parsed_metadata": parsed_metadata,
        "evidence_status": (
            "probabile"
            if parsed_metadata and parsed_metadata.get("requires_review") is False
            else "non_verificato"
        ),
        "obligation_status": parsed_metadata.get("obligation_status") or "APERTO",
'''
if text.count(old) != 1:
    raise SystemExit("non-payment archive evidence insertion mismatch")
text = text.replace(old, new, 1)
old = '''            "status": "nuovo",
            "processed": False,
            "file_hash": file_hash,
'''
new = '''            "status": "nuovo",
            "processed": False,
            "evidence_status": "non_verificato",
            "file_hash": file_hash,
'''
if text.count(old) != 1:
    raise SystemExit("generic inbox evidence insertion mismatch")
text = text.replace(old, new, 1)
pattern = re.compile(
    r'@router\.post\("/ricategorizza-documenti"\)\n@handle_errors\nasync def ricategorizza_documenti\(\) -> Dict\[str, Any\]:\n.*?\n\n\n@router\.post\("/processa-tutti"\)',
    re.S,
)
replacement = '''@router.post("/ricategorizza-documenti", deprecated=True)
@handle_errors
async def ricategorizza_documenti() -> Dict[str, Any]:
    """Legacy filename-only reclassification is intentionally non-mutating.

    The filename is not evidence. Classification must pass through the canonical
    preview flow, which inspects content and binds SHA-256 + detected type to the
    human confirmation token.
    """
    return {
        "success": False,
        "deprecated": True,
        "mutated": 0,
        "ricategorizzati": 0,
        "evidence_status": "non_verificato",
        "message": (
            "Ricategorizzazione automatica dal solo nome file disattivata. "
            "Usare /api/documenti/upload-auto/preview e confermare il risultato."
        ),
    }


@router.post("/processa-tutti")'''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"legacy ricategorizza function replacement mismatch: {count}")
path.write_text(text, encoding="utf-8")


# 3) Fiscal archive records carry a conservative evidence status.
path = Path("app/services/fiscal_document_ingestion.py")
text = path.read_text(encoding="utf-8")
old = '''            "source": source,
            "source_metadata": source_metadata,
            "updated_at": now,
'''
new = '''            "source": source,
            "source_metadata": source_metadata,
            "evidence_status": "non_verificato" if classification["requires_review"] else "probabile",
            "updated_at": now,
'''
if text.count(old) != 1:
    raise SystemExit("fiscal document evidence insertion mismatch")
text = text.replace(old, new, 1)
old = '''            "source": source,
            "source_metadata": source_metadata,
            "created_at": now,
        }
'''
new = '''            "source": source,
            "source_metadata": source_metadata,
            "evidence_status": "non_verificato" if classification["requires_review"] else "probabile",
            "created_at": now,
        }
'''
if text.count(old) != 1:
    raise SystemExit("fiscal inbox evidence insertion mismatch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 4) Document AI: extraction can be probable, never silently verified, and never writes operational ledgers directly.
path = Path("app/routers/document_ai.py")
text = path.read_text(encoding="utf-8")
anchor = "router = APIRouter()\n\n\n"
helper = '''router = APIRouter()


def _attach_ai_evidence_status(result):
    """Normalize AI output without treating model success as verified evidence."""
    payload = dict(result or {})
    structured = payload.get("structured_data") if isinstance(payload.get("structured_data"), dict) else {}
    if payload.get("error") or (structured and structured.get("success") is False and structured.get("error")):
        status = "conflitto"
    elif structured.get("success") and structured.get("data"):
        status = "probabile"
    else:
        status = "non_verificato"
    payload["evidence_status"] = status
    payload["review_required"] = status != "verificato"
    return payload


'''
if text.count(anchor) != 1:
    raise SystemExit("document_ai helper anchor mismatch")
text = text.replace(anchor, helper, 1)
old = '''        result = await process_document(
            file_data=content,
            filename=file.filename,
            document_type=document_type,
            model=model
        )

        # Salva nel DB se richiesto
'''
new = '''        result = await process_document(
            file_data=content,
            filename=file.filename,
            document_type=document_type,
            model=model
        )
        result = _attach_ai_evidence_status(result)

        # Salva nel DB se richiesto
'''
if text.count(old) != 1:
    raise SystemExit("document_ai extract result block mismatch")
text = text.replace(old, new, 1)
old = '''                "model_used": model,
                "file_base64": base64.b64encode(content).decode('utf-8'),
                "has_pdf": True,
                "processato": True,
'''
new = '''                "model_used": model,
                "file_base64": base64.b64encode(content).decode('utf-8'),
                "has_pdf": True,
                "evidence_status": result["evidence_status"],
                "review_required": True,
                "processato": True,
'''
if text.count(old) != 1:
    raise SystemExit("document_ai manual save evidence fields mismatch")
text = text.replace(old, new, 1)
old = '''            # Salva ANCHE nelle collection del gestionale
            from app.services.document_data_saver import save_extracted_data_to_gestionale
            source_info = {"filename": file.filename, "upload_type": "manual"}
            gestionale_result = await save_extracted_data_to_gestionale(
                db, result.get("structured_data", {}), source_info
            )
            result["gestionale_save"] = gestionale_result
'''
new = '''            # L'estrazione AI resta una proposta revisionabile. Non crea F24,
            # movimenti bancari, cedolini, fatture o altri fatti operativi.
            result["gestionale_save"] = {
                "status": "blocked_pending_review",
                "message": "Estrazione AI salvata per revisione; nessuna scrittura operativa automatica.",
            }
'''
if text.count(old) != 1:
    raise SystemExit("document_ai operational save block mismatch")
text = text.replace(old, new, 1)
old = '''        result = await process_document_from_base64(
            base64_data=base64_data,
            filename=filename,
            document_type=document_type,
            model=model
        )

        if save_to_db and result.get("structured_data", {}).get("success"):
'''
new = '''        result = await process_document_from_base64(
            base64_data=base64_data,
            filename=filename,
            document_type=document_type,
            model=model
        )
        result = _attach_ai_evidence_status(result)

        if save_to_db and result.get("structured_data", {}).get("success"):
'''
if text.count(old) != 1:
    raise SystemExit("document_ai base64 result block mismatch")
text = text.replace(old, new, 1)
old = '''                "model_used": model,
                "processato": True,
                "created_at": datetime.now(timezone.utc).isoformat()
'''
new = '''                "model_used": model,
                "evidence_status": result["evidence_status"],
                "review_required": True,
                "processato": True,
                "created_at": datetime.now(timezone.utc).isoformat()
'''
if text.count(old) != 1:
    raise SystemExit("document_ai base64 save evidence fields mismatch")
text = text.replace(old, new, 1)
old = '''        return {
            "filename": file.filename,
            "text": text,
            "text_length": len(text),
            "detected_type": doc_type,
            "ocr_used": "OCR" in text
        }
'''
new = '''        return {
            "filename": file.filename,
            "text": text,
            "text_length": len(text),
            "detected_type": doc_type,
            "ocr_used": "OCR" in text,
            "evidence_status": "non_verificato" if doc_type in (None, "generico") else "probabile",
            "review_required": True,
        }
'''
if text.count(old) != 1:
    raise SystemExit("document_ai text-only evidence block mismatch")
text = text.replace(old, new, 1)
old = '''        "model_used": 1,
        "created_at": 1
'''
new = '''        "model_used": 1,
        "evidence_status": 1,
        "review_required": 1,
        "created_at": 1
'''
if text.count(old) != 1:
    raise SystemExit("document_ai projection evidence fields mismatch")
text = text.replace(old, new, 1)
old = '''    result = await process_document_from_base64(
        base64_data=doc["pdf_base64"],
        filename=doc.get("filename", "documento.pdf"),
        document_type=doc_type,
        model=model
    )

    # Aggiorna il documento classificato con i dati estratti
'''
new = '''    result = await process_document_from_base64(
        base64_data=doc["pdf_base64"],
        filename=doc.get("filename", "documento.pdf"),
        document_type=doc_type,
        model=model
    )
    result = _attach_ai_evidence_status(result)

    # Aggiorna il documento classificato con i dati estratti
'''
if text.count(old) != 1:
    raise SystemExit("document_ai classified-email result block mismatch")
text = text.replace(old, new, 1)
old = '''                    "extraction_model": model,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "processed": True
'''
new = '''                    "extraction_model": model,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "evidence_status": result["evidence_status"],
                    "review_required": True,
                    "processed": True
'''
if text.count(old) != 1:
    raise SystemExit("document_ai classified-email evidence fields mismatch")
text = text.replace(old, new, 1)
old = '''        save_to_gestionale=save_to_gestionale,
        model=model
    )

    return result
'''
new = '''        save_to_gestionale=False,
        model=model
    )
    result["operational_write_blocked"] = True
    result["requested_save_to_gestionale"] = bool(save_to_gestionale)
    return result
'''
if text.count(old) != 1:
    raise SystemExit("document_ai bulk write block mismatch")
text = text.replace(old, new, 1)
old = '''        save_to_gestionale=True,
        model=model
    )

    return result
'''
new = '''        save_to_gestionale=False,
        model=model
    )
    result["operational_write_blocked"] = True
    result["message"] = "Riprocessamento AI completato come proposta; scritture operative bloccate in attesa di revisione."
    return result
'''
if text.count(old) != 1:
    raise SystemExit("document_ai reprocess write block mismatch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 5) Frontend import: show evidence status from the exact confirmed preview.
path = Path("frontend/src/pages/ImportDocumenti.jsx")
text = path.read_text(encoding="utf-8")
anchor = "const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));\n"
helper = '''const EVIDENCE_STATUS_META = {
  verificato: { label: 'Verificato', variant: 'success' },
  probabile: { label: 'Probabile', variant: 'info' },
  non_verificato: { label: 'Non verificato', variant: 'warning' },
  conflitto: { label: 'Conflitto', variant: 'danger' },
};

const evidenceMeta = status => EVIDENCE_STATUS_META[status] || EVIDENCE_STATUS_META.non_verificato;

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
'''
if text.count(anchor) != 1:
    raise SystemExit("ImportDocumenti evidence helper anchor mismatch")
text = text.replace(anchor, helper, 1)
old = '''          workflow: importData?.workflow,
          evidenceSummary: descriviProvaFiscale(importData),
          details: importData,
'''
new = '''          workflow: importData?.workflow,
          evidenceStatus: fileInfo.preview?.evidence_status || 'non_verificato',
          evidenceSummary: descriviProvaFiscale(importData),
          details: importData,
'''
if text.count(old) != 1:
    raise SystemExit("ImportDocumenti result evidence insertion mismatch")
text = text.replace(old, new, 1)
old = '''                  {f.tipo && <Badge variant={getTipoVariant(f.tipo)}>{getTipoLabel(f.tipo)}</Badge>}
                  {f.status === 'pending' && (
'''
new = '''                  {f.tipo && <Badge variant={getTipoVariant(f.tipo)}>{getTipoLabel(f.tipo)}</Badge>}
                  {f.preview?.evidence_status && (
                    <Badge variant={evidenceMeta(f.preview.evidence_status).variant}>
                      Evidenza: {evidenceMeta(f.preview.evidence_status).label}
                    </Badge>
                  )}
                  {f.status === 'pending' && (
'''
if text.count(old) != 1:
    raise SystemExit("ImportDocumenti preview badge insertion mismatch")
text = text.replace(old, new, 1)
old = '''                      {r.workflow && <Badge variant="info">{r.workflow}</Badge>}
                    </div>
'''
new = '''                      {r.workflow && <Badge variant="info">{r.workflow}</Badge>}
                      {r.evidenceStatus && (
                        <Badge variant={evidenceMeta(r.evidenceStatus).variant}>
                          Evidenza: {evidenceMeta(r.evidenceStatus).label}
                        </Badge>
                      )}
                    </div>
'''
if text.count(old) != 1:
    raise SystemExit("ImportDocumenti result badge insertion mismatch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 6) Frontend archive: display evidence separately from workflow status.
path = Path("frontend/src/pages/Documenti.jsx")
text = path.read_text(encoding="utf-8")
anchor = '''const STATUS_LABELS = {
  nuovo: { label: 'Da collegare', variant: 'warning' },
  processato: { label: 'Processato', variant: 'success' },
  errore: { label: 'Errore', variant: 'danger' },
};

'''
helper = anchor + '''const EVIDENCE_STATUS_LABELS = {
  verificato: { label: 'Verificato', variant: 'success' },
  probabile: { label: 'Probabile', variant: 'info' },
  non_verificato: { label: 'Non verificato', variant: 'warning' },
  conflitto: { label: 'Conflitto', variant: 'danger' },
};

'''
if text.count(anchor) != 1:
    raise SystemExit("Documenti evidence labels anchor mismatch")
text = text.replace(anchor, helper, 1)
old = '''                  const statusStyle = STATUS_LABELS[doc.status] || STATUS_LABELS.nuovo;
                  return (
                    <div style={{ display: 'grid', gap: 4 }}>
                      <Badge variant={statusStyle.variant}>{statusStyle.label}</Badge>
'''
new = '''                  const statusStyle = STATUS_LABELS[doc.status] || STATUS_LABELS.nuovo;
                  const evidenceStyle = EVIDENCE_STATUS_LABELS[doc.evidence_status]
                    || EVIDENCE_STATUS_LABELS.non_verificato;
                  return (
                    <div style={{ display: 'grid', gap: 4 }}>
                      <Badge variant={statusStyle.variant}>{statusStyle.label}</Badge>
                      <Badge variant={evidenceStyle.variant}>Evidenza: {evidenceStyle.label}</Badge>
'''
if text.count(old) != 1:
    raise SystemExit("Documenti archive evidence badge insertion mismatch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 7) Regression tests.
path = Path("tests/test_document_import_preview.py")
text = path.read_text(encoding="utf-8")
if "test_preview_tipo_riconosciuto_non_diventa_verificato_solo_per_il_tipo" not in text:
    text += '''


def test_preview_tipo_riconosciuto_non_diventa_verificato_solo_per_il_tipo(monkeypatch):
    import asyncio
    from app.services import document_import_preview as preview_service

    db = MemorySheetsClient()["document-preview-evidence-test"]
    monkeypatch.setattr(preview_service, "_specialist_preview", lambda *_: {})
    payload = asyncio.run(preview_service.build_import_preview(
        db, content=b"cedolino generico", filename="cedolino.pdf", document_type="cedolino"
    ))

    assert payload["evidence_status"] == "probabile"
    assert payload["classification"]["evidence_status"] == "probabile"
    assert payload["classification"]["confidence"] < 1.0


def test_preview_con_errore_di_validazione_e_conflitto():
    from app.services import document_import_preview as preview_service

    status, confidence, _ = preview_service._preview_evidence_state(
        "f24", {}, {"saldo_quadrato": False}, ["F24 non quadrato o non validato"]
    )
    assert status == "conflitto"
    assert confidence == 0.0
'''
path.write_text(text, encoding="utf-8")

path = Path("tests/test_documenti_archivio.py")
text = path.read_text(encoding="utf-8")
if "test_archivio_separa_stato_operativo_da_stato_evidenza" not in text:
    text += '''


def test_archivio_separa_stato_operativo_da_stato_evidenza(monkeypatch):
    db = _db(monkeypatch)
    _run(db.documents_inbox.insert_many([
        {
            "id": "legacy-processato", "filename": "fattura.pdf",
            "category": "fattura", "status": "processato", "processed": True,
            "processed_to": "fatture",
        },
        {
            "id": "esplicito", "filename": "f24.pdf",
            "category": "f24", "status": "processato", "processed": True,
            "processed_to": "f24_unificato", "evidence_status": "verificato",
        },
        {
            "id": "errore", "filename": "rotto.pdf",
            "category": "f24", "status": "errore", "processing_error": "parser fallito",
        },
    ]))

    result = _run(documenti.lista_documenti(
        categoria=None, status=None, anno=None, search=None, limit=50, skip=0
    ))
    by_id = {item["id"]: item for item in result["documents"]}
    assert by_id["legacy-processato"]["evidence_status"] == "non_verificato"
    assert by_id["esplicito"]["evidence_status"] == "verificato"
    assert by_id["errore"]["evidence_status"] == "conflitto"
'''
path.write_text(text, encoding="utf-8")

path = Path("tests/test_documenti_import_sicuro.py")
text = path.read_text(encoding="utf-8")
if "test_ricategorizzazione_legacy_da_filename_non_muta_documenti" not in text:
    text += '''


def test_ricategorizzazione_legacy_da_filename_non_muta_documenti(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["documenti-legacy-filename-disabled"]
        await db.documents_inbox.insert_one({
            "id": "legacy-1", "filename": "F24_IMPORTANTE.pdf",
            "category": "altro", "status": "nuovo", "processed": False,
        })
        monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))

        result = await documenti.ricategorizza_documenti()
        persisted = await db.documents_inbox.find_one({"id": "legacy-1"})

        assert result["deprecated"] is True
        assert result["mutated"] == 0
        assert result["evidence_status"] == "non_verificato"
        assert persisted["category"] == "altro"

    asyncio.run(scenario())
'''
path.write_text(text, encoding="utf-8")

path = Path("tests/test_document_ai_evidence_governance.py")
path.write_text('''from pathlib import Path

from app.routers import document_ai


def test_ai_success_is_probable_not_verified():
    result = document_ai._attach_ai_evidence_status({
        "structured_data": {"success": True, "data": {"totale": 10}}
    })
    assert result["evidence_status"] == "probabile"
    assert result["review_required"] is True


def test_ai_explicit_error_is_conflict():
    result = document_ai._attach_ai_evidence_status({
        "structured_data": {"success": False, "error": "schema non coerente"}
    })
    assert result["evidence_status"] == "conflitto"


def test_ai_router_non_scrive_piu_direttamente_nei_registri_operativi():
    source = Path("app/routers/document_ai.py").read_text(encoding="utf-8")
    assert "save_extracted_data_to_gestionale" not in source
    assert source.count("save_to_gestionale=False") >= 2
    assert "blocked_pending_review" in source
''', encoding="utf-8")

path = Path("frontend/src/pages/ImportDocumenti.test.jsx")
text = path.read_text(encoding="utf-8")
old = '''          duplicate: false,
          file: { sha256: 'a'.repeat(64) },
'''
new = '''          duplicate: false,
          evidence_status: 'probabile',
          file: { sha256: 'a'.repeat(64) },
'''
if text.count(old) != 1:
    raise SystemExit("ImportDocumenti test preview mock insertion mismatch")
text = text.replace(old, new, 1)
if "mostra lo stato di evidenza separato dal risultato operativo" not in text:
    insertion = '''
  it('mostra lo stato di evidenza separato dal risultato operativo', async () => {
    mockPreviewThenImport('fattura', {
      success: true, tipo_rilevato: 'fattura', imported: 1, message: 'Fattura importata',
    });
    render(<ImportDocumenti />);

    const xml = new File(['<FatturaElettronica />'], 'fattura.xml', { type: 'application/xml' });
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [xml] } });
    fireEvent.click(await screen.findByTestId('upload-btn'));
    expect((await screen.findAllByText('Evidenza: Probabile')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByTestId('upload-btn'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect((await screen.findAllByText('Evidenza: Probabile')).length).toBeGreaterThan(0);
  });
'''
    marker = "\n  it('non presenta come importato un duplicato restituito con HTTP 200', async () => {"
    if marker not in text:
        raise SystemExit("ImportDocumenti test insertion marker missing")
    text = text.replace(marker, insertion + marker, 1)
path.write_text(text, encoding="utf-8")
