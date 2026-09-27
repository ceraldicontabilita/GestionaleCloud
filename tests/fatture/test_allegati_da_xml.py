"""Il PDF che il fornitore allega dentro l'XML si legge dall'XML stesso."""
import base64

from app.routers.fatture_module.crud import allegati_da_xml

PDF = b"%PDF-1.4 cortesia"
XML = f"""<?xml version="1.0"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
 <FatturaElettronicaBody>
  <Allegati>
   <NomeAttachment>fattura_123.pdf</NomeAttachment>
   <FormatoAttachment>PDF</FormatoAttachment>
   <Attachment>{base64.b64encode(PDF).decode()}</Attachment>
  </Allegati>
  <Allegati><NomeAttachment>vuoto.pdf</NomeAttachment><Attachment></Attachment></Allegati>
 </FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def test_legge_gli_allegati_con_contenuto():
    allegati = allegati_da_xml(XML)
    assert [a["nome"] for a in allegati] == ["fattura_123.pdf"]
    assert allegati[0]["formato"] == "PDF" and allegati[0]["indice"] == 0
    assert base64.b64decode(allegati[0]["_base64"]) == PDF


def test_xml_rotto_non_fa_cadere_niente():
    assert allegati_da_xml(b"<non xml") == []
