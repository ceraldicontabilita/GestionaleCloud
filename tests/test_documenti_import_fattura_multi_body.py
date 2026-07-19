"""Review Codex su PR #71: app/routers/documenti.py ha una pipeline di
import fattura XML SEPARATA da process_xml_bytes (parse_fattura_xml +
process_fattura_to_db, usata dall'upload automatico "Documenti"). Il fix
multi-body fatto in process_xml_bytes non copriva questo secondo percorso:
un file FatturaPA che raggruppa più fatture caricato da qui perdeva
comunque silenziosamente tutte le fatture oltre la prima.

Copre: app.routers.documenti.upload_documento_automatico per il caso
multi-body (import di tutte le fatture del file, non solo la prima)."""
import asyncio
import io

from fastapi import UploadFile, HTTPException

from app.routers import documenti as documenti_mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeDb:
    def __getitem__(self, name):
        raise AssertionError(f"non atteso accesso diretto a db[{name!r}] in questo test")


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


def _body(numero, importo):
    return f"""
    <FatturaElettronicaBody>
      <DatiGenerali>
        <DatiGeneraliDocumento>
          <TipoDocumento>TD01</TipoDocumento>
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


def test_upload_automatico_importa_tutte_le_fatture_del_file_multi_body(monkeypatch):
    xml = _xml(_body("20", "1000.00"), _body("21", "2000.00")).encode("utf-8")
    upload = UploadFile(filename="raggruppata.xml", file=io.BytesIO(xml))

    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: _FakeDb()))

    importate = []
    xml_raw_ricevuti = []

    async def _fake_process_fattura_to_db(db, parsed, filename, xml_raw=None):
        importate.append(parsed["invoice_number"])
        xml_raw_ricevuti.append(xml_raw)
        return {"invoice_number": parsed["invoice_number"], "id": f"id-{parsed['invoice_number']}"}

    import app.routers.invoices.fatture_upload as fu_mod
    monkeypatch.setattr(fu_mod, "process_fattura_to_db", _fake_process_fattura_to_db)

    res = _run(documenti_mod.upload_documento_automatico(file=upload))

    assert res["imported"] == 2
    assert importate == ["20", "21"]
    assert "fatture aggiuntive" in res["message"]
    # Review Codex PR #71 (3° giro): xml_raw va passato per OGNI body, non
    # solo per il primo, altrimenti /xml-originale risulterebbe 404 sulle
    # fatture aggiuntive pur avendo l'xml_content ancora disponibile qui.
    assert all(xr is not None for xr in xml_raw_ricevuti)


def test_upload_automatico_body_extra_duplicato_non_blocca_il_primo(monkeypatch):
    """Se il body aggiuntivo è già presente (process_fattura_to_db solleva
    409), l'import del primo body non deve fallire — solo quello extra va
    ignorato come duplicato."""
    xml = _xml(_body("20", "1000.00"), _body("21", "2000.00")).encode("utf-8")
    upload = UploadFile(filename="raggruppata.xml", file=io.BytesIO(xml))

    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: _FakeDb()))

    async def _fake_process_fattura_to_db(db, parsed, filename, xml_raw=None):
        if parsed["invoice_number"] == "21":
            raise HTTPException(status_code=409, detail="Fattura duplicata")
        return {"invoice_number": parsed["invoice_number"], "id": "id-20"}

    import app.routers.invoices.fatture_upload as fu_mod
    monkeypatch.setattr(fu_mod, "process_fattura_to_db", _fake_process_fattura_to_db)

    res = _run(documenti_mod.upload_documento_automatico(file=upload))

    assert res["success"] is True
    assert res["imported"] == 1


def test_upload_automatico_primo_body_duplicato_secondo_nuovo_importa_comunque(monkeypatch):
    """Review Codex su PR #71 (3° giro): se è il PRIMO body ad essere già
    presente (409) ma il SECONDO è nuovo, il 409 sul primo non deve
    interrompere il ciclo prima di raggiungere gli altri body — la fattura
    nuova va importata comunque e riportata come successo."""
    xml = _xml(_body("20", "1000.00"), _body("21", "2000.00")).encode("utf-8")
    upload = UploadFile(filename="raggruppata.xml", file=io.BytesIO(xml))

    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: _FakeDb()))

    async def _fake_process_fattura_to_db(db, parsed, filename, xml_raw=None):
        if parsed["invoice_number"] == "20":
            raise HTTPException(status_code=409, detail="Fattura duplicata")
        return {"invoice_number": parsed["invoice_number"], "id": "id-21"}

    import app.routers.invoices.fatture_upload as fu_mod
    monkeypatch.setattr(fu_mod, "process_fattura_to_db", _fake_process_fattura_to_db)

    res = _run(documenti_mod.upload_documento_automatico(file=upload))

    assert res["success"] is True
    assert res["imported"] == 1
    assert res["message"].startswith("Fattura importata: 21")


def test_upload_automatico_tutti_duplicati_segnala_errore(monkeypatch):
    """Caso simmetrico: se OGNI body è già presente, il comportamento resta
    quello di oggi per un singolo duplicato (success=False, 409 propagato
    fino al gestore generico)."""
    xml = _xml(_body("20", "1000.00"), _body("21", "2000.00")).encode("utf-8")
    upload = UploadFile(filename="raggruppata.xml", file=io.BytesIO(xml))

    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: _FakeDb()))

    async def _fake_process_fattura_to_db(db, parsed, filename, xml_raw=None):
        raise HTTPException(status_code=409, detail=f"Fattura duplicata: {parsed['invoice_number']}")

    import app.routers.invoices.fatture_upload as fu_mod
    monkeypatch.setattr(fu_mod, "process_fattura_to_db", _fake_process_fattura_to_db)

    res = _run(documenti_mod.upload_documento_automatico(file=upload))

    assert res["success"] is False


def test_upload_automatico_decodifica_correttamente_xml_non_utf8(monkeypatch):
    """Review Codex su PR #71 (5° giro): xml_content veniva decodificato
    SOLO con content.decode('utf-8', errors='ignore') — su un file
    realmente non-UTF-8 (es. ISO-8859-1) con testo accentato, questo
    cancella silenziosamente i byte non validi invece di provare la
    decodifica giusta, corrompendo il testo che ora viene anche persistito
    come xml_raw e riservito da /xml-originale."""
    xml_str = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        '<FatturaElettronica><FatturaElettronicaHeader><CedentePrestatore>'
        '<DatiAnagrafici><Anagrafica><Denominazione>Società Àccentata</Denominazione>'
        '</Anagrafica></DatiAnagrafici></CedentePrestatore></FatturaElettronicaHeader>'
        '<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento>'
        '<TipoDocumento>TD01</TipoDocumento><Numero>1</Numero>'
        '<ImportoTotaleDocumento>100.00</ImportoTotaleDocumento>'
        '</DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody></FatturaElettronica>'
    )
    xml_bytes = xml_str.encode("iso-8859-1")
    upload = UploadFile(filename="fattura.xml", file=io.BytesIO(xml_bytes))

    monkeypatch.setattr(documenti_mod.Database, "get_db", staticmethod(lambda: _FakeDb()))

    xml_raw_ricevuto = {}

    async def _fake_process_fattura_to_db(db, parsed, filename, xml_raw=None):
        xml_raw_ricevuto["value"] = xml_raw
        return {"invoice_number": parsed["invoice_number"], "id": "id-1"}

    import app.routers.invoices.fatture_upload as fu_mod
    monkeypatch.setattr(fu_mod, "process_fattura_to_db", _fake_process_fattura_to_db)

    _run(documenti_mod.upload_documento_automatico(file=upload))

    assert "Società Àccentata" in xml_raw_ricevuto["value"]
