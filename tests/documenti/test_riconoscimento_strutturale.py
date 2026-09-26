"""Riconoscimento dalla struttura del documento: cedolino Zucchetti, contabile di bonifico."""
import asyncio
import io

from fastapi import UploadFile

from app.routers import documenti
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

# Frammento anonimo del livello testo Zucchetti: gli spazi diventano «s».
TESTO_ZUCCHETTI = (
    "COGNOMESESNOME PERIODOSDISRETRIBUZIONE CODICESFISCALE VOCISVARIABILISDELSMESE "
    "TOTALESTRATTENUTE TOTALESCOMPETENZE NETTOSDELSMESE ZUCCHETTI SPA"
)


def test_busta_zucchetti_con_nome_da_persona_e_un_cedolino(monkeypatch):
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_: TESTO_ZUCCHETTI)
    for nome in ("Rossi Mario - Aprile 2024 - Variante 2.pdf", "ROSSI_MARIO_2026_05_ABCD1234.pdf"):
        assert documenti.detect_document_type(nome, b"%PDF-1.4") == "cedolino"


def test_busta_con_spazi_normali_resta_riconosciuta(monkeypatch):
    monkeypatch.setattr(
        documenti, "_pdf_text_for_detection",
        lambda *_: "PERIODO DI RETRIBUZIONE TOTALE COMPETENZE TOTALE TRATTENUTE NETTO DEL MESE",
    )
    assert documenti.detect_document_type("documento.pdf", b"%PDF-1.4") == "cedolino"


def test_una_sola_casella_non_basta(monkeypatch):
    monkeypatch.setattr(
        documenti, "_pdf_text_for_detection",
        lambda *_: "REGOLAMENTO INTERNO AZIENDALE: IL NETTO DEL MESE SI PAGA ENTRO IL 10",
    )
    assert documenti.detect_document_type("regolamento.pdf", b"%PDF-1.4") == "auto"


def _upload_cedolino(monkeypatch, dati_lul):
    async def scenario():
        db = ClientArchivioMemoria()["cedolino_zucchetti"]
        monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
        monkeypatch.setattr("app.utils.upload_validation.verifica_pdf_reale", lambda *_: None)
        monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_: TESTO_ZUCCHETTI)

        async def lul(file, aggiorna_esistenti=True):
            return {"success": True, "message": "Workflow LUL completato", "data": dati_lul}

        monkeypatch.setattr("app.services.libro_unico_workflow.import_libro_unico", lul)
        upload = UploadFile(filename="Rossi Mario - Aprile 2024.pdf", file=io.BytesIO(b"%PDF-1.4"))
        return await documenti.upload_documento_automatico(file=upload)

    return asyncio.run(scenario())


def test_cedolino_senza_buste_lette_non_e_importato(monkeypatch):
    # ``totale_dipendenti`` sono pagine divise per due: non prova una lettura.
    esito = _upload_cedolino(monkeypatch, {"totale_dipendenti": 1, "buste_importate": 0,
                                           "buste_aggiornate": 0})
    assert esito["success"] is False and esito["imported"] == 0
    assert "nessuna" in esito["message"]


def test_cedolino_con_busta_scritta_e_importato(monkeypatch):
    esito = _upload_cedolino(monkeypatch, {"totale_dipendenti": 1, "buste_importate": 1,
                                           "buste_aggiornate": 0})
    assert esito["success"] is True and esito["imported"] == 1


def test_contabile_bonifico_con_banca_del_beneficiario_non_e_un_estratto(monkeypatch):
    monkeypatch.setattr(
        documenti, "_pdf_text_for_detection",
        lambda *_: ("REGISTRIAMO A VOSTRO DEBITO A FAVORE DI: IL SEGUENTE BONIFICO "
                    "IMPORTO EUR 1.100,00 BANCA NAZIONALE DEL LAVORO S.P.A. IBAN BENEFICIARIO"),
    )
    assert documenti.detect_document_type("Rossi Mario_28-12-2021_EUR1100_00.pdf", b"%PDF") == "bonifici"
