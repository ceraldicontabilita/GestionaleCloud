"""
test_estrai_xml_p7m.py
───────────────────────
Regression per il bug trovato il 06/07/2026 su una fattura .xml.p7m firmata
(Villa Sandi, prosecco): _estrai_xml (fatture.py) restituiva il BINARIO firmato
intero quando "FatturaElettronica" capitava nei primi 400 byte (busta DER
piccola → l'XML inizia subito), e il parser falliva con "not well-formed,
line 1". Ora i p7m passano sempre per _carve che ritaglia il blocco XML.
Nessuna fattura reale nel repo: si usano p7m SINTETICI con la stessa struttura.
"""
import xml.etree.ElementTree as ET

from app.lotti.routers.fatture import _estrai_xml

_XML = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<p:FatturaElettronica xmlns:p='x' versione='FPR12'>"
    b"<FatturaElettronicaBody><DatiGenerali/></FatturaElettronicaBody>"
    b"</p:FatturaElettronica>"
)


def test_p7m_der_con_xml_precoce_viene_ritagliato():
    # busta DER "piccola" (l'XML entra nei primi 400 byte) + coda firma binaria
    p7m = b"\x30\x82\x24\x12\x06\x09" + _XML + b"\x00\x82\x0a\xff\xde\xad\xbe\xef"
    out = _estrai_xml(p7m)
    assert out[:5] == b"<?xml", "deve ritagliare l'XML, non restituire il binario"
    root = ET.fromstring(out)  # non deve sollevare
    assert root.tag.endswith("FatturaElettronica")


def test_p7m_grande_prima_dellxml():
    # busta con molto binario prima dell'XML (>400 byte): già gestita prima,
    # deve restare gestita
    p7m = b"\x30\x82" + b"\x00" * 500 + _XML + b"\x00\x82\xff"
    out = _estrai_xml(p7m)
    assert out[:5] == b"<?xml"
    ET.fromstring(out)


def test_xml_grezzo_con_dichiarazione_invariato():
    assert _estrai_xml(_XML) == _XML


def test_xml_grezzo_senza_dichiarazione_invariato():
    plain = b"<p:FatturaElettronica xmlns:p='x'><a>1</a></p:FatturaElettronica>"
    assert _estrai_xml(plain) == plain
