"""Bug reale segnalato dall'utente 19/07/2026 sulla fattura 20 di DI MASSA
DARIO & c. sas: il parser leggeva SOLO il primo <FatturaElettronicaBody> di
un file XML FatturaPA. Un file può contenere più fatture raggruppate sotto
lo stesso header/CedentePrestatore (caso reale per fatture differite
spedite insieme dallo stesso fornitore): ogni fattura oltre la prima
veniva persa silenziosamente (importo, righe, tutto).

Copre: fattura_elettronica_parser.parse_fattura_xml/parse_fattura_xml_multi
per il caso singolo body (invariato) e multi body (nuovo comportamento),
più il loro consumo in fatture_upload.process_xml_bytes."""
import asyncio

from app.parsers.fattura_elettronica_parser import parse_fattura_xml, parse_fattura_xml_multi
from app.routers.invoices import fatture_upload as fu_mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _header():
    return """
    <FatturaElettronicaHeader>
      <CedentePrestatore>
        <DatiAnagrafici>
          <IdFiscaleIVA><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
          <Anagrafica><Denominazione>FORNITORE TEST SRL</Denominazione></Anagrafica>
        </DatiAnagrafici>
      </CedentePrestatore>
      <CessionarioCommittente>
        <DatiAnagrafici>
          <IdFiscaleIVA><IdCodice>09876543210</IdCodice></IdFiscaleIVA>
        </DatiAnagrafici>
      </CessionarioCommittente>
    </FatturaElettronicaHeader>
    """


def _body(numero, importo, tipo_doc="TD24"):
    return f"""
    <FatturaElettronicaBody>
      <DatiGenerali>
        <DatiGeneraliDocumento>
          <TipoDocumento>{tipo_doc}</TipoDocumento>
          <Divisa>EUR</Divisa>
          <Data>2026-07-01</Data>
          <Numero>{numero}</Numero>
          <ImportoTotaleDocumento>{importo}</ImportoTotaleDocumento>
        </DatiGeneraliDocumento>
      </DatiGenerali>
      <DatiBeniServizi>
        <DettaglioLinee>
          <NumeroLinea>1</NumeroLinea>
          <Descrizione>Riga fattura {numero}</Descrizione>
          <PrezzoUnitario>{importo}</PrezzoUnitario>
          <PrezzoTotale>{importo}</PrezzoTotale>
          <AliquotaIVA>22.00</AliquotaIVA>
        </DettaglioLinee>
        <DatiRiepilogo>
          <AliquotaIVA>22.00</AliquotaIVA>
          <ImponibileImporto>{importo}</ImponibileImporto>
          <Imposta>0.00</Imposta>
        </DatiRiepilogo>
      </DatiBeniServizi>
    </FatturaElettronicaBody>
    """


def _xml(*bodies):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <p:FatturaElettronica xmlns:p="ns">
      {_header()}
      {"".join(bodies)}
    </p:FatturaElettronica>"""


def test_singolo_body_comportamento_invariato():
    xml = _xml(_body("20", "1000.00"))
    parsed = parse_fattura_xml(xml)

    assert parsed["invoice_number"] == "20"
    assert parsed["total_amount"] == 1000.00
    assert "multi_body_count" not in parsed
    assert "_altri_body" not in parsed


def test_multi_body_parse_fattura_xml_ritorna_solo_prima_ma_segnala_le_altre():
    xml = _xml(_body("20", "1000.00"), _body("21", "2000.00"))
    parsed = parse_fattura_xml(xml)

    assert parsed["invoice_number"] == "20"
    assert parsed["total_amount"] == 1000.00
    assert parsed["multi_body_count"] == 2
    assert len(parsed["_altri_body"]) == 1
    assert parsed["_altri_body"][0]["invoice_number"] == "21"
    assert parsed["_altri_body"][0]["total_amount"] == 2000.00


def test_multi_body_parse_fattura_xml_multi_ritorna_tutte():
    xml = _xml(_body("20", "1000.00"), _body("21", "2000.00"), _body("22", "3000.00"))
    risultati = parse_fattura_xml_multi(xml)

    assert len(risultati) == 3
    assert [r["invoice_number"] for r in risultati] == ["20", "21", "22"]
    assert [r["total_amount"] for r in risultati] == [1000.00, 2000.00, 3000.00]
    # Header (fornitore/cliente) condiviso correttamente da tutti i body
    for r in risultati:
        assert r["supplier_name"] == "FORNITORE TEST SRL"


def test_process_xml_bytes_importa_tutte_le_fatture_del_file_multi_body(monkeypatch):
    """Prima del fix: solo la prima fattura veniva importata, la seconda
    andava persa senza nessun errore/segnalazione."""
    xml = _xml(_body("20", "1000.00"), _body("21", "2000.00")).encode("utf-8")

    importate = []

    async def _fake_import(db, parsed, filename, source, xml_raw=None):
        importate.append(parsed["invoice_number"])
        return {"status": "imported", "invoice_number": parsed["invoice_number"]}

    monkeypatch.setattr(fu_mod, "import_parsed_invoice", _fake_import)

    res = _run(fu_mod.process_xml_bytes(None, xml, "raggruppata.xml", source="xml_upload"))

    assert res["status"] == "imported"
    assert res["invoice_number"] == "20"
    assert res["multi_body_xml"] is True
    assert len(res["altre_fatture_stesso_file"]) == 1
    assert res["altre_fatture_stesso_file"][0]["invoice_number"] == "21"
    assert importate == ["20", "21"]
