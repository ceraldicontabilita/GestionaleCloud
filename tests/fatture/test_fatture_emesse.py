"""Fatture emesse: fuori dalle passive, agganciate al corrispettivo dello scontrino.

27/09/2026: le fatture che il bar emette dopo lo scontrino finivano fra le
fatture passive («FPR 7/26» era un acquisto con IVA a credito). Il titolare:
non aumentano le entrate, si collegano al corrispettivo del giorno.
"""
import asyncio
import io

from mongomock_motor import AsyncMongoMockClient

from app.routers.invoices.fatture_upload import process_xml_bytes
from app.services import fatture_emesse as fe


def run(coro):
    return asyncio.run(coro)


def _xml(numero="FPR 7/26", data="2026-07-20", cedente="04523831214",
         causale="fattura gia in corrispettivi per emissione scontino fiscale del giorno "
                 "10 Luglio 2026 numero 2586-0352, iva gia in corrispettivi"):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
 <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{cedente}</IdCodice></IdFiscaleIVA>
  <Anagrafica><Denominazione>Cedente</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
  <Sede><Indirizzo>Via A</Indirizzo><CAP>80100</CAP><Comune>Napoli</Comune><Nazione>IT</Nazione></Sede></CedentePrestatore>
 <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
  <Anagrafica><Denominazione>Cliente Prova</Denominazione></Anagrafica></DatiAnagrafici>
  <Sede><Indirizzo>Via B</Indirizzo><CAP>80100</CAP><Comune>Napoli</Comune><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
 <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa>
  <Data>{data}</Data><Numero>{numero}</Numero><ImportoTotaleDocumento>45.00</ImportoTotaleDocumento>
  <Causale>{causale}</Causale></DatiGeneraliDocumento></DatiGenerali>
 <DatiBeniServizi>
  <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>aperitivo</Descrizione><Quantita>3.00</Quantita>
   <PrezzoUnitario>13.63636364</PrezzoUnitario><PrezzoTotale>40.91</PrezzoTotale><AliquotaIVA>10.00</AliquotaIVA></DettaglioLinee>
  <DatiRiepilogo><AliquotaIVA>10.00</AliquotaIVA><ImponibileImporto>40.91</ImponibileImporto><Imposta>4.09</Imposta></DatiRiepilogo>
 </DatiBeniServizi>
</FatturaElettronicaBody>
</p:FatturaElettronica>""".encode("utf-8")


def _corrispettivo(db, cid, data, stato="imported"):
    run(db["corrispettivi"].insert_one({"id": cid, "data": data, "totale": 2444.3, "status": stato}))


def test_la_fattura_emessa_non_entra_fra_le_passive_e_si_aggancia_allo_scontrino():
    db = AsyncMongoMockClient()["t"]
    _corrispettivo(db, "corr-cancellato", "2026-07-10", stato="deleted")
    _corrispettivo(db, "corr-10-07", "2026-07-10")
    esito = run(process_xml_bytes(db, _xml(), "fattura.xml", source="test"))
    assert esito["status"] == "fattura_emessa"
    assert run(db["invoices"].count_documents({})) == 0
    f = run(db[fe.COLL].find_one({}, {"_id": 0}))
    assert f["numero_fattura"] == "FPR 7/26" and f["totale"] == 45.0
    assert f["incide_su_ricavi"] is False and f["gia_in_corrispettivi"] is True and f["pagato"] is True
    # Lo scontrino e' del 10/07, la fattura del 20/07: comanda lo scontrino.
    assert f["scontrino"] == {"data": "2026-07-10", "numero": "2586-0352", "fonte": "causale"}
    assert f["corrispettivo"]["stato"] == "SODDISFATTO"
    assert f["corrispettivo"]["corrispettivo_id"] == "corr-10-07"
    cliente = run(db[fe.COLL_CLIENTI].find_one({}, {"_id": 0}))
    assert cliente["id"] == "CLI-piva-01234567890" and cliente["denominazione"] == "Cliente Prova"


def test_il_secondo_import_non_crea_niente():
    db = AsyncMongoMockClient()["t"]
    run(process_xml_bytes(db, _xml(), "a.xml", source="test"))
    secondo = run(process_xml_bytes(db, _xml(), "copia.xml", source="test"))
    assert secondo["status"] == "fattura_emessa" and secondo["fattura_emessa_id"]
    assert run(db[fe.COLL].count_documents({})) == 1
    assert run(db[fe.COLL_CLIENTI].count_documents({})) == 1


def test_una_fattura_ricevuta_non_e_emessa():
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml

    parsed = parse_fattura_xml(_xml(cedente="09876543210").decode("utf-8"))
    assert fe.e_fattura_emessa(parsed) is False
    assert fe.e_fattura_emessa({"supplier_vat": "IT04523831214"}) is True


def test_due_corrispettivi_lo_stesso_giorno_si_sceglie_e_la_scelta_resta():
    db = AsyncMongoMockClient()["t"]
    _corrispettivo(db, "a", "2026-07-10")
    _corrispettivo(db, "b", "2026-07-10")
    run(process_xml_bytes(db, _xml(), "f.xml", source="test"))
    f = run(db[fe.COLL].find_one({}, {"_id": 0}))
    assert f["corrispettivo"]["stato"] == "DA_VERIFICARE"
    assert sorted(f["corrispettivo"]["candidati"]) == ["a", "b"]
    assert "corrispettivo_id" not in f["corrispettivo"]           # niente scelta inventata
    assert run(fe.scegli_corrispettivo(db, f["id"], "b"))["success"]
    run(fe.riallinea(db))
    f = run(db[fe.COLL].find_one({}, {"_id": 0}))
    assert f["corrispettivo"]["corrispettivo_id"] == "b" and f["corrispettivo"]["scelto_da_titolare"]


def test_il_corrispettivo_arrivato_dopo_si_aggancia_dal_giro():
    db = AsyncMongoMockClient()["t"]
    run(process_xml_bytes(db, _xml(causale="Prodotto gia scontrinato, iva gia in corrispettivi"),
                          "f.xml", source="test"))
    f = run(db[fe.COLL].find_one({}, {"_id": 0}))
    # Senza data nella causale vale la data della fattura.
    assert f["scontrino"]["fonte"] == "data_fattura"
    assert f["corrispettivo"]["stato"] == "ATTESO"
    _corrispettivo(db, "arrivato", "2026-07-20")
    assert run(fe.riallinea(db))["agganciate"] == 1
    f = run(db[fe.COLL].find_one({}, {"_id": 0}))
    assert f["corrispettivo"]["corrispettivo_id"] == "arrivato"


def test_quella_gia_finita_fra_le_passive_torna_emessa_con_lo_storno(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    run(db["invoices"].insert_one({
        "id": "inv-1", "supplier_vat": "04523831214", "invoice_number": "FPR 7/26",
        "status": "imported", "xml_raw": _xml().decode("utf-8"), "registrata_contabilita": True}))
    run(db["invoices"].insert_one({"id": "inv-altro", "supplier_vat": "09876543210", "status": "imported"}))
    run(db["partite_aperte"].insert_one({"id": "pa", "documento_id": "inv-1", "stato": "aperta", "residuo": 45.0}))
    run(db["scadenziario_fornitori"].insert_one({"id": "sc", "fattura_id": "inv-1", "status": "aperta"}))
    stornate = []

    async def storna(_db, fattura_id, motivo):
        stornate.append(fattura_id)
        return {"stato": "stornato"}

    monkeypatch.setattr("app.services.registrazione_contabile.storna_registrazione_fattura", storna)
    esito = run(fe.togli_dalle_passive(db))
    assert esito == {"spostate": ["FPR 7/26"], "errori": []}
    assert stornate == ["inv-1"]
    inv = run(db["invoices"].find_one({"id": "inv-1"}, {"_id": 0}))
    assert inv["status"] == "archived" and inv["deleted_reason"] == "fattura_emessa_non_passiva"
    assert run(db["invoices"].find_one({"id": "inv-altro"}, {"_id": 0}))["status"] == "imported"
    assert run(db["partite_aperte"].find_one({"id": "pa"}, {"_id": 0}))["stato"] == "chiusa"
    assert run(db["scadenziario_fornitori"].find_one({"id": "sc"}, {"_id": 0}))["status"] == "archived"
    assert run(db[fe.COLL].count_documents({})) == 1
    # Il giro dopo non trova piu' niente da spostare.
    assert run(fe.togli_dalle_passive(db))["spostate"] == []


def _report_clienti() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Codice cliente", "Tipo Cliente", "Indirizzo telematico", "Email", "PEC", "Telefono",
               "ID Paese", "Partita Iva", "Codice Fiscale", "Denominazione", "Nome", "Cognome"])
    ws.append([None, "B2B", "USAL8PV", "a@b.it", None, "081", "IT", "01234567890", "01234567890",
               '"CLIENTE PROVA S.R.L."', None, None])
    ws.append([None, "PA", "4B4QS8", None, None, None, None, None, "80017440639", "Ente", None, None])
    ws.append([None, "B2C", None, None, None, None, None, None, None, None, "Mario", "Rossi"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_report_clienti_crea_una_volta_e_non_inventa_identita():
    from app.routers.documenti import detect_document_type

    contenuto = _report_clienti()
    assert detect_document_type("ReportClienti.xlsx", contenuto) == "anagrafica_clienti"
    db = AsyncMongoMockClient()["t"]
    primo = run(fe.importa_report_clienti(db, contenuto, "ReportClienti.xlsx"))
    assert primo["nuovi"] == 2 and primo["senza_identita"] == 1
    cliente = run(db[fe.COLL_CLIENTI].find_one({"id": "CLI-piva-01234567890"}, {"_id": 0}))
    assert cliente["denominazione"] == "CLIENTE PROVA S.R.L." and cliente["codice_destinatario"] == "USAL8PV"
    secondo = run(fe.importa_report_clienti(db, contenuto, "ReportClienti.xlsx"))
    assert secondo["nuovi"] == 0 and secondo["gia_presenti"] == 2


def test_scontrino_dalla_causale():
    assert fe.scontrino_da_causale(["Scontrino fiscale numero 2561-0412 e pagato del 15-06-2026"]) == {
        "data": "2026-06-15", "numero": "2561-0412"}
    assert fe.scontrino_da_causale(["pagato il 08-05-2026\niva gia in corrispettivi"]) == {
        "data": "2026-05-08", "numero": None}
    assert fe.scontrino_da_causale(["nessuna data"]) == {"data": None, "numero": None}
