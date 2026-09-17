"""Regola utente 18/07/2026: i file tecnici del circuito PEC/SDI
(daticert.xml, metadati *_MT_*.xml, ricevute postacert) e le fatture SDI
grezze (IT..._XXXXX.xml/.p7m) non devono comparire in 'Scarica Documenti
da Email': le fatture vivono in `invoices` (pipeline dedicata), il resto
è trasporto e non è mai un documento per l'utente."""
from app.services.email_document_downloader import (
    FILE_FATTURA_SDI_RE,
    FILE_TECNICI_PEC_RE,
    categorize_document,
    is_relevant_email_document,
)


def test_file_tecnici_pec_riconosciuti():
    tecnici = [
        "daticert.xml",
        "DATICERT.XML",
        "postacert.eml",
        "smime.p7s",
        "IT15539261006_176X9_MT_001.xml",
        "IT07135891211_JUF1T_MT_001.xml.p7m",
    ]
    for nome in tecnici:
        assert FILE_TECNICI_PEC_RE.search(nome), nome


def test_fatture_sdi_riconosciute():
    fatture = [
        "IT07135891211_JUF1T.xml.p7m",
        "IT15539261006_176X9.xml",
        "IT01234567890_AB1CD.XML.P7M",
    ]
    for nome in fatture:
        assert FILE_FATTURA_SDI_RE.match(nome), nome


def test_documenti_veri_non_toccati():
    legittimi = [
        "Stampa modello F24 Scadenza 07-2026 (7).pdf",
        "Riepilogo Paghe - 2026-07-09T150413.251.pdf",
        "Libro unico - 2026-07-09T150849.123.pdf",
        "VSPVCN67T26F839P - 2025.pdf",
        "fattura_fornitore_estero.pdf",
        "estratto_conto_giugno.xlsx",
        "cartella_esattoriale.pdf",
    ]
    for nome in legittimi:
        assert not FILE_TECNICI_PEC_RE.search(nome), nome
        assert not FILE_FATTURA_SDI_RE.match(nome), nome


def test_email_accetta_solo_documenti_amministrativi_riconosciuti():
    assert not is_relevant_email_document({"filename": "foto-menu.pdf", "category": "altro"})
    assert is_relevant_email_document({
        "filename": "IT07135891211_JUF1T.xml.p7m", "category": "altro",
    })
    assert is_relevant_email_document({"filename": "Avviso.pdf", "category": "avviso_bonario"})


def test_classificazione_email_non_confonde_inps_e_quietanza_con_f24_generico():
    assert categorize_document("contributi_INPS_giugno.pdf") == "contributi_inps"
    assert categorize_document("ricevuta_f24.pdf") == "quietanza"
    assert categorize_document("allegato.pdf", subject="Comunicazione di irregolarita") == "avviso_bonario"
