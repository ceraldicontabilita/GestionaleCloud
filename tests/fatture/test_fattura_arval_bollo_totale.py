"""Regressione: il bollo fiscale da 2 euro non sostituisce il totale XML."""

from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.services.noleggio.parsers import (
    categorizza_spesa,
    estrai_numero_contratto,
    estrai_veicolo_strutturato,
)


ARVAL_LIKE_XML = """<?xml version="1.0" encoding="utf-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">
  <FatturaElettronicaHeader>
    <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>04911190488</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>FORNITORE NOLEGGIO TEST</Denominazione></Anagrafica></DatiAnagrafici><Sede><Indirizzo>Via Test</Indirizzo><CAP>00000</CAP><Comune>Test</Comune><Nazione>IT</Nazione></Sede></CedentePrestatore>
    <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>00000000000</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>CLIENTE TEST</Denominazione></Anagrafica></DatiAnagrafici><Sede><Indirizzo>Via Test</Indirizzo><CAP>00000</CAP><Comune>Test</Comune><Nazione>IT</Nazione></Sede></CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>2026-02-11</Data><Numero>TEST-BOLLO-001</Numero><DatiBollo><BolloVirtuale>SI</BolloVirtuale><ImportoBollo>2.00</ImportoBollo></DatiBollo><ImportoTotaleDocumento>163.56</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Rifatturazione Tasse automobilistiche Bollo/Superbollo</Descrizione><PrezzoUnitario>161.56</PrezzoUnitario><PrezzoTotale>161.56</PrezzoTotale><AliquotaIVA>0.00</AliquotaIVA><Natura>N1</Natura><AltriDatiGestionali><TipoDato>TARGA</TipoDato><RiferimentoTesto>GX037HJ BMW X1 Sdrive 18D X-Line Dct / 2026</RiferimentoTesto></AltriDatiGestionali><AltriDatiGestionali><TipoDato>Contratto</TipoDato><RiferimentoTesto>6074667</RiferimentoTesto></AltriDatiGestionali></DettaglioLinee>
      <DettaglioLinee><NumeroLinea>2</NumeroLinea><Descrizione>Imposta di bollo</Descrizione><PrezzoUnitario>2.00</PrezzoUnitario><PrezzoTotale>2.00</PrezzoTotale><AliquotaIVA>0.00</AliquotaIVA><Natura>N1</Natura></DettaglioLinee>
      <DatiRiepilogo><AliquotaIVA>0.00</AliquotaIVA><Natura>N1</Natura><ImponibileImporto>163.56</ImponibileImporto><Imposta>0.00</Imposta></DatiRiepilogo>
    </DatiBeniServizi>
    <DatiPagamento><CondizioniPagamento>TP02</CondizioniPagamento><DettaglioPagamento><ModalitaPagamento>MP20</ModalitaPagamento><ImportoPagamento>163.56</ImportoPagamento></DettaglioPagamento></DatiPagamento>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""


def test_totale_documento_non_diventa_importo_bollo_fiscale():
    parsed = parse_fattura_xml(ARVAL_LIKE_XML)

    assert parsed["invoice_number"] == "TEST-BOLLO-001"
    assert parsed["total_amount"] == 163.56
    assert parsed["imponibile"] == 163.56
    assert parsed["iva"] == 0.0
    assert parsed["somma_righe"] == 163.56
    assert parsed["totali_coerenti"] is True
    assert [riga["prezzo_totale"] for riga in parsed["linee"]] == ["161.56", "2.00"]


def test_bollo_fiscale_non_viene_classificato_come_canone():
    categoria, importo, metadata = categorizza_spesa("Imposta di bollo", 2.0, False)

    assert categoria == "costi_extra"
    assert importo == 2.0
    assert metadata["tipo_costo"] == "bollo_fiscale_fattura"


def test_fattura_bollo_arval_si_collega_al_veicolo_e_non_alla_riga_da_due_euro():
    xml = ARVAL_LIKE_XML.replace("TEST-BOLLO-001", "FT0014095324").replace(
        "2026-02-11", "2026-06-11"
    )
    parsed = parse_fattura_xml(xml)

    assert parsed["invoice_number"] == "FT0014095324"
    assert parsed["total_amount"] == 163.56
    assert estrai_numero_contratto(parsed) == "6074667"
    veicolo = estrai_veicolo_strutturato(parsed["linee"][0])
    assert veicolo["targa"] == "GX037HJ"
    assert veicolo["marca"] == "BMW"
