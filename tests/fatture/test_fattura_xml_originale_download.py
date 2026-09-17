"""Richiesta utente 19/07/2026: "io ho bisogno di vedere sempre l'originale
la fattura così come arriva altrimenti non potrei mai vedere se c'è un
errore" — prima non esisteva nessun modo di scaricare/vedere il testo XML
grezzo di una fattura, nemmeno quando era salvato nel database, e il
modale "vedi fattura" poteva mostrare silenziosamente un riepilogo
ricostruito senza segnalarlo.

Copre: app.routers.fatture_module.crud.download_xml_originale (nuovo
endpoint) e il banner di avviso in generate_invoice_html quando si mostra
il fallback ricostruito invece dell'originale."""
import asyncio
import tempfile
import os

import pytest
from fastapi import HTTPException

from app.routers.fatture_module import crud as crud_mod
from app.routers.fatture_module.helpers import generate_invoice_html


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _patch_db(monkeypatch, db):
    monkeypatch.setattr(crud_mod.Database, "get_db", staticmethod(lambda: db))


def test_download_xml_originale_404_se_fattura_non_esiste(monkeypatch):
    _patch_db(monkeypatch, _FakeDb())

    with pytest.raises(HTTPException) as exc:
        _run(crud_mod.download_xml_originale("non-esiste"))
    assert exc.value.status_code == 404
    assert "non trovata" in exc.value.detail.lower()


def test_download_xml_originale_404_se_xml_non_salvato(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [{"id": "fatt-1", "invoice_number": "20"}]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(crud_mod.download_xml_originale("fatt-1"))
    assert exc.value.status_code == 404
    assert "non disponibile" in exc.value.detail.lower()


def test_download_xml_originale_ritorna_i_bytes_xml_raw(monkeypatch):
    xml_content = "<FatturaElettronica><FatturaElettronicaBody/></FatturaElettronica>"
    db = _FakeDb()
    db["invoices"].docs = [{"id": "fatt-1", "invoice_number": "20", "xml_raw": xml_content}]
    _patch_db(monkeypatch, db)

    res = _run(crud_mod.download_xml_originale("fatt-1"))

    assert res.body.decode("utf-8") == xml_content
    assert res.media_type == "application/xml"
    assert "fattura_20.xml" in res.headers["content-disposition"]


def test_download_xml_originale_normalizza_dichiarazione_encoding_a_utf8(monkeypatch):
    """Review Codex su PR #71 (4° giro): xml_raw è salvato come stringa
    Python già decodificata (può provenire da un file non-UTF-8) e qui
    viene sempre ri-codificato in UTF-8 per la risposta HTTP. Se la
    dichiarazione XML originale dicesse ancora "ISO-8859-1", i bytes
    serviti (UTF-8) e la dichiarazione sarebbero incoerenti — un lettore
    XML che si fida della dichiarazione produrrebbe mojibake su testo
    accentato (fornitore/descrizioni). La dichiarazione va sempre allineata
    ai bytes realmente serviti."""
    xml_content = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        '<FatturaElettronica><FatturaElettronicaBody>'
        '<Denominazione>Società Àccentata</Denominazione>'
        '</FatturaElettronicaBody></FatturaElettronica>'
    )
    db = _FakeDb()
    db["invoices"].docs = [{"id": "fatt-1", "invoice_number": "20", "xml_raw": xml_content}]
    _patch_db(monkeypatch, db)

    res = _run(crud_mod.download_xml_originale("fatt-1"))

    assert b'encoding="ISO-8859-1"' not in res.body
    assert b'encoding="UTF-8"' in res.body
    # I bytes devono essere realmente decodificabili come UTF-8 (coerenti
    # con quanto dichiarato) e col testo accentato intatto.
    assert "Società Àccentata" in res.body.decode("utf-8")


def test_download_xml_originale_fattura_soft_deleted_da_404(monkeypatch):
    """Review Codex su PR #71 (3° giro): get_fattura_dettaglio tratta una
    fattura con status/entity_status 'deleted' come inesistente — il nuovo
    endpoint XML deve avere la stessa regola, altrimenti una fattura
    cancellata dall'utente resta scaricabile a chi conosce/indovina l'id."""
    xml_content = "<FatturaElettronica><FatturaElettronicaBody/></FatturaElettronica>"
    db = _FakeDb()
    db["invoices"].docs = [{
        "id": "fatt-1", "invoice_number": "20", "xml_raw": xml_content,
        "status": "deleted",
    }]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(crud_mod.download_xml_originale("fatt-1"))
    assert exc.value.status_code == 404


def test_download_xml_originale_fattura_entity_status_deleted_da_404(monkeypatch):
    xml_content = "<FatturaElettronica><FatturaElettronicaBody/></FatturaElettronica>"
    db = _FakeDb()
    db["invoices"].docs = [{
        "id": "fatt-1", "invoice_number": "20", "xml_raw": xml_content,
        "entity_status": "deleted",
    }]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(crud_mod.download_xml_originale("fatt-1"))
    assert exc.value.status_code == 404


def test_download_xml_originale_sanitizza_numero_fattura_nel_filename(monkeypatch):
    """Review Codex su PR #71 (3° giro): un numero fattura con CR/LF o
    virgolette (dato che arriva dall'XML, in linea di principio
    attaccante-controllabile) non deve finire grezzo nell'header
    Content-Disposition."""
    xml_content = "<FatturaElettronica><FatturaElettronicaBody/></FatturaElettronica>"
    db = _FakeDb()
    db["invoices"].docs = [{
        "id": "fatt-1",
        "invoice_number": 'evil"\r\nX-Injected: yes',
        "xml_raw": xml_content,
    }]
    _patch_db(monkeypatch, db)

    res = _run(crud_mod.download_xml_originale("fatt-1"))

    disposition = res.headers["content-disposition"]
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert disposition.count('"') == 2  # solo le due virgolette del filename="...", nessuna iniettata
    assert "evil" in disposition


def test_download_xml_originale_p7m_binario_non_estraibile_da_404_non_binario(monkeypatch):
    """Review Codex su PR #71: se il .p7m è una busta CMS/PKCS#7 binaria
    senza XML embedded trovabile (né in chiaro né rilanciando il parser
    CMS), il download NON deve servire i bytes binari grezzi come se
    fossero application/xml (file .xml illeggibile) — deve fallire con un
    404 chiaro."""
    with tempfile.NamedTemporaryFile(suffix=".xml.p7m", delete=False) as f:
        f.write(b"\x00\x01\x02BUSTA-BINARIA-NON-XML\xff\xfe\xfd")
        path = f.name
    try:
        db = _FakeDb()
        db["invoices"].docs = [{"id": "fatt-1", "invoice_number": "20", "xml_file_path": path}]
        _patch_db(monkeypatch, db)

        with pytest.raises(HTTPException) as exc:
            _run(crud_mod.download_xml_originale("fatt-1"))
        assert exc.value.status_code == 404
        assert "non disponibile" in exc.value.detail.lower()
    finally:
        os.unlink(path)


def test_download_xml_originale_p7m_con_xml_embedded_lo_estrae(monkeypatch):
    xml_content = (
        b'<?xml version="1.0"?><FatturaElettronica><FatturaElettronicaBody/></FatturaElettronica>'
    )
    with tempfile.NamedTemporaryFile(suffix=".xml.p7m", delete=False) as f:
        f.write(b"\x00\x01busta-non-cms-ma-xml-in-chiaro" + xml_content + b"\x00trailer")
        path = f.name
    try:
        db = _FakeDb()
        db["invoices"].docs = [{"id": "fatt-1", "invoice_number": "20", "xml_file_path": path}]
        _patch_db(monkeypatch, db)

        res = _run(crud_mod.download_xml_originale("fatt-1"))

        assert res.body == xml_content
    finally:
        os.unlink(path)


def _xml_multi_body(numero_1, numero_2):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <p:FatturaElettronica xmlns:p="ns">
      <FatturaElettronicaHeader>
        <CedentePrestatore><DatiAnagrafici>
          <Anagrafica><Denominazione>FORNITORE TEST SRL</Denominazione></Anagrafica>
        </DatiAnagrafici></CedentePrestatore>
      </FatturaElettronicaHeader>
      <FatturaElettronicaBody>
        <DatiGenerali><DatiGeneraliDocumento><Numero>{numero_1}</Numero></DatiGeneraliDocumento></DatiGenerali>
      </FatturaElettronicaBody>
      <FatturaElettronicaBody>
        <DatiGenerali><DatiGeneraliDocumento><Numero>{numero_2}</Numero></DatiGeneraliDocumento></DatiGenerali>
      </FatturaElettronicaBody>
    </p:FatturaElettronica>"""


def test_view_fattura_assoinvoice_isola_solo_il_body_selezionato(monkeypatch):
    """Review Codex su PR #71 (4° giro): FoglioStileAssoSoftware.xsl itera
    TUTTI i <FatturaElettronicaBody> del file — se xml_raw è quello
    dell'intero file raggruppato (condiviso da più fatture tramite
    xml_body_index), aprire "vedi fattura" sulla SECONDA fattura di un file
    multi-body renderizzava anche la prima insieme ad essa. Il codice sotto
    test deve potare l'albero XML al solo body selezionato PRIMA di
    trasformarlo con l'XSL: qui si intercetta lxml.etree.XSLT con uno stub
    che ritorna l'albero (già potato) inalterato, per verificare la potatura
    senza dipendere dai dettagli di rendering del vero foglio di stile."""
    from lxml import etree as real_lxml_etree

    def _fake_xslt_ctor(xsl_doc):
        return lambda xml_doc: xml_doc  # nessuna trasformazione: ritorna l'albero (già potato)

    monkeypatch.setattr(real_lxml_etree, "XSLT", _fake_xslt_ctor)

    xml = _xml_multi_body("20", "21")
    db = _FakeDb()
    db["invoices"].docs = [{
        "id": "fatt-1", "invoice_number": "21", "xml_raw": xml,
        "xml_body_index": 1,
    }]
    _patch_db(monkeypatch, db)

    res = _run(crud_mod.view_fattura_assoinvoice("fatt-1"))

    html = res.body.decode("utf-8")
    assert "<Numero>21</Numero>" in html
    assert "<Numero>20</Numero>" not in html


def test_view_fattura_assoinvoice_body_index_0_isola_il_primo(monkeypatch):
    from lxml import etree as real_lxml_etree

    def _fake_xslt_ctor(xsl_doc):
        return lambda xml_doc: xml_doc

    monkeypatch.setattr(real_lxml_etree, "XSLT", _fake_xslt_ctor)

    xml = _xml_multi_body("20", "21")
    db = _FakeDb()
    db["invoices"].docs = [{
        "id": "fatt-1", "invoice_number": "20", "xml_raw": xml,
        "xml_body_index": 0,
    }]
    _patch_db(monkeypatch, db)

    res = _run(crud_mod.view_fattura_assoinvoice("fatt-1"))

    html = res.body.decode("utf-8")
    assert "<Numero>20</Numero>" in html
    assert "<Numero>21</Numero>" not in html


def test_view_fattura_assoinvoice_singolo_body_invariato(monkeypatch):
    """Con un solo body (caso normale, non raggruppato) non deve esserci
    nessuna potatura: il body unico resta intatto."""
    from lxml import etree as real_lxml_etree

    def _fake_xslt_ctor(xsl_doc):
        return lambda xml_doc: xml_doc

    monkeypatch.setattr(real_lxml_etree, "XSLT", _fake_xslt_ctor)

    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <FatturaElettronica>
      <FatturaElettronicaBody>
        <DatiGenerali><DatiGeneraliDocumento><Numero>42</Numero></DatiGeneraliDocumento></DatiGenerali>
      </FatturaElettronicaBody>
    </FatturaElettronica>"""
    db = _FakeDb()
    db["invoices"].docs = [{"id": "fatt-1", "invoice_number": "42", "xml_raw": xml}]
    _patch_db(monkeypatch, db)

    res = _run(crud_mod.view_fattura_assoinvoice("fatt-1"))

    assert "<Numero>42</Numero>" in res.body.decode("utf-8")


def test_generate_invoice_html_fallback_avvisa_che_non_e_loriginale():
    html = generate_invoice_html({"invoice_number": "20", "total_amount": 100.0}, [])

    assert "NON è il documento XML originale" in html


def test_html_assosoftware_viene_centrato_nel_visualizzatore():
    html = (
        "<html><head><title>Fattura</title></head><body>"
        "<div id='fattura-elettronica' style='min-width:800px'>documento</div>"
        "</body></html>"
    )

    responsive = crud_mod._rendi_fattura_responsive(html)

    assert "justify-content:center!important" in responsive
    assert "#fattura-container,#fattura-elettronica{width:800px!important" in responsive
