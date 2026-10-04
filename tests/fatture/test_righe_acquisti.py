from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.routers.righe_acquisti import _filtra, costruisci_righe


XML_CON_RIGA_COMPLETA = """<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica>
  <FatturaElettronicaHeader>
    <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>13397910962</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>Amazon Business EU</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
    <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>Ceraldi</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento><TipoDocumento>TD04</TipoDocumento><Divisa>EUR</Divisa><Data>2026-01-10</Data><Numero>IT63F2ABEC</Numero><ImportoTotaleDocumento>82.61</ImportoTotaleDocumento></DatiGeneraliDocumento>
      <DatiFattureCollegate><IdDocumento>IT53HH03ABEI</IdDocumento><Data>2025-12-16</Data></DatiFattureCollegate>
      <DatiOrdineAcquisto><IdDocumento>407-4144790-3445105</IdDocumento><Data>2025-12-11</Data></DatiOrdineAcquisto>
      <DatiContratto><IdDocumento>407-4144790-3445105</IdDocumento><Data>2025-12-11</Data></DatiContratto>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea><CodiceArticolo><CodiceTipo>ASIN</CodiceTipo><CodiceValore>B00TEST</CodiceValore></CodiceArticolo>
        <Descrizione>Pentola a pressione Lagostina</Descrizione><Quantita>1.00</Quantita><UnitaMisura>PZ</UnitaMisura><PrezzoUnitario>71.27</PrezzoUnitario>
        <ScontoMaggiorazione><Tipo>SC</Tipo><Percentuale>5.00</Percentuale></ScontoMaggiorazione><PrezzoTotale>67.71</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DettaglioLinee><NumeroLinea>2</NumeroLinea><Descrizione>Arrotondamento</Descrizione><Quantita>1</Quantita><PrezzoUnitario>0.02</PrezzoUnitario><PrezzoTotale>0.02</PrezzoTotale><AliquotaIVA>0</AliquotaIVA><Natura>N2.2</Natura></DettaglioLinee>
      <DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>67.73</ImponibileImporto><Imposta>14.90</Imposta></DatiRiepilogo>
    </DatiBeniServizi>
    <DatiPagamento><CondizioniPagamento>TP02</CondizioniPagamento><DettaglioPagamento><ModalitaPagamento>MP08</ModalitaPagamento><DataScadenzaPagamento>2026-01-10</DataScadenzaPagamento><ImportoPagamento>82.61</ImportoPagamento></DettaglioPagamento></DatiPagamento>
  </FatturaElettronicaBody>
</FatturaElettronica>"""


def _fattura(parsed, *, invoice_id, hash_value, tipo=None):
    return {
        "id": invoice_id,
        "invoice_number": parsed["invoice_number"],
        "invoice_date": parsed["invoice_date"],
        "tipo_documento": tipo or parsed["tipo_documento"],
        "supplier_name": parsed["supplier_name"],
        "supplier_vat": parsed["supplier_vat"],
        "total_amount": parsed["total_amount"],
        "divisa": parsed["divisa"],
        "linee": parsed["linee"],
        "pagamento_rate": parsed["pagamento_rate"],
        "dati_fatture_collegate": parsed["dati_fatture_collegate"],
        "dati_ordine_acquisto": parsed["dati_ordine_acquisto"],
        "content_hash": hash_value,
    }


def test_parser_conserva_codici_e_sconti_della_singola_riga():
    parsed = parse_fattura_xml(XML_CON_RIGA_COMPLETA)
    prima = parsed["linee"][0]
    assert prima["codici_articolo"] == [{"tipo": "ASIN", "valore": "B00TEST"}]
    assert prima["sconti_maggiorazioni"] == [{"tipo": "SC", "percentuale": "5.00"}]


def test_registro_td04_cerca_originale_in_un_altro_anno_e_non_nasconde_arrotondamento():
    parsed = parse_fattura_xml(XML_CON_RIGA_COMPLETA)
    nota = _fattura(
        parsed,
        invoice_id="nc-2026",
        hash_value="0CCEA6594829DBF721295560366E0617FCB1ABFF1DB66F99C7A5301BCE787DD3",
    )
    nota["dati_contratto"] = parsed["dati_contratto"]
    originale = {
        "id": "fattura-2025",
        "invoice_number": "IT53HH03ABEI",
        "invoice_date": "2025-12-16",
        "tipo_documento": "TD01",
        "supplier_name": "Amazon Business EU",
        "supplier_vat": "13397910962",
        "content_hash": "b" * 64,
        "linee": [{"numero_linea": "1", "descrizione": "Pentola a pressione Lagostina", "prezzo_totale": "67.71", "aliquota_iva": "22"}],
    }

    righe = costruisci_righe([nota, originale])
    righe_nota = [r for r in righe if r["fattura_id"] == "nc-2026"]

    assert len(righe_nota) == 2
    assert {r["imponibile"] for r in righe_nota} == {67.71, 0.02}
    assert all(r["nota_credito"]["stato"] == "trovata_da_collegare" for r in righe_nota)
    assert all(r["nota_credito"]["fattura_id"] == "fattura-2025" for r in righe_nota)
    assert all(r["contratti"] == ["407-4144790-3445105"] for r in righe_nota)
    assert all(
        r["hash_originale"] == "0CCEA6594829DBF721295560366E0617FCB1ABFF1DB66F99C7A5301BCE787DD3"
        for r in righe_nota
    )
    assert righe_nota[0]["classificazione"]["stato"] == "DA_VERIFICARE"
    assert righe_nota[0]["pagamenti_dichiarati"][0]["descrizione"] == "Carta di pagamento"


def test_registro_non_inventa_origine_e_filtra_righe_da_verificare():
    parsed = parse_fattura_xml(XML_CON_RIGA_COMPLETA)
    nota = _fattura(parsed, invoice_id="nc-sola", hash_value="c" * 64)
    righe = costruisci_righe([nota])

    assert all(r["nota_credito"]["stato"] == "da_recuperare" for r in righe)
    assert "IT53HH03ABEI" in righe[0]["nota_credito"]["messaggio"]
    filtrate = _filtra(
        righe, anno=2026, fornitore="Amazon", testo="407-4144790-3445105",
        natura="", conto="", metodo="MP08", stato_ai="DA_VERIFICARE", anomalie=True,
    )
    assert len(filtrate) == 2
