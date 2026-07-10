"""Pulizia Drive fatture per anno: estrazione anno documento e ID cartella."""
from app.services.drive_pulizia import anno_da_contenuto, estrai_id_cartella


def test_estrai_id_cartella_da_url():
    url = "https://drive.google.com/drive/u/2/folders/1n2tW3JQP3QMHd5AbjR4HfLlbpDjskWnv"
    assert estrai_id_cartella(url) == "1n2tW3JQP3QMHd5AbjR4HfLlbpDjskWnv"
    assert estrai_id_cartella("  abc123  ") == "abc123"
    assert estrai_id_cartella("") == ""


def test_anno_da_dati_generali_documento():
    xml = (
        b"<FatturaElettronica><FatturaElettronicaBody><DatiGenerali>"
        b"<DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento>"
        b"<Data>2024-05-12</Data><Numero>77</Numero></DatiGeneraliDocumento>"
        b"<DatiFattureCollegate><Data>2023-12-01</Data></DatiFattureCollegate>"
        b"</DatiGenerali></FatturaElettronicaBody></FatturaElettronica>"
    )
    # Vince la data del DOCUMENTO, non quella delle fatture collegate
    assert anno_da_contenuto(xml) == 2024


def test_anno_fallback_data_unica():
    xml = b"<root><Data>2023-01-31</Data><Data>2023-06-30</Data></root>"
    assert anno_da_contenuto(xml) == 2023


def test_anno_non_determinabile():
    # Date discordanti senza DatiGeneraliDocumento → nessuna decisione
    xml = b"<root><Data>2023-01-31</Data><Data>2024-06-30</Data></root>"
    assert anno_da_contenuto(xml) is None
    assert anno_da_contenuto(b"") is None
    assert anno_da_contenuto(b"binario senza date") is None


def test_anno_dentro_p7m_binario():
    # Un .p7m contiene l'XML in chiaro dentro la busta binaria
    p7m = b"\x30\x82\x04binhead" + (
        b"<DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento>"
        b"<Data>2025-02-08</Data></DatiGeneraliDocumento>"
    ) + b"\x00\x01firma"
    assert anno_da_contenuto(p7m) == 2025
