"""Regressioni COR10: ImportoParziale e' base fiscale, non totale ivato.

Fonte primaria: AdE, Allegato Tipi Dati per i Corrispettivi v7 giugno 2020,
campi 4.1.1.2, 4.1.4 e 4.1.6-14; copia integrale allegata a:
https://www.ordinefarmacistipadova.it/files/news/136_12357-unito.pdf, pp. 54-58.
I due importi reali del lotto 2023 sono riprodotti senza identificativi privati.
"""

import pytest

from app.parsers.corrispettivi_parser import parse_corrispettivo_xml
from tests.corrispettivi._comune import xml_chiusura


def _xml(riepiloghi, *, contanti="0.00", pos="0.00", altri_totali=""):
    return (
        '<DatiCorrispettivi versione="COR10"><Trasmissione>'
        '<Progressivo>1</Progressivo><Formato>COR10</Formato>'
        '<Dispositivo><Tipo>RT</Tipo><IdDispositivo>RT-TEST</IdDispositivo>'
        '</Dispositivo></Trasmissione><DataOraRilevazione>'
        '2026-10-06T21:00:00+02:00</DataOraRilevazione><DatiRT>'
        f'{riepiloghi}<Totali><NumeroDocCommerciali>1</NumeroDocCommerciali>'
        f'<PagatoContanti>{contanti}</PagatoContanti>'
        f'<PagatoElettronico>{pos}</PagatoElettronico>{altri_totali}'
        '</Totali></DatiRT></DatiCorrispettivi>'
    )


def _riepilogo(ammontare, parziale, imposta, *, altri="", regime=None):
    iva = regime if regime is not None else (
        f'<IVA><AliquotaIVA>10.00</AliquotaIVA><Imposta>{imposta}</Imposta></IVA>'
    )
    return (f'<Riepilogo>{iva}<Ammontare>{ammontare}</Ammontare>'
            f'<ImportoParziale>{parziale}</ImportoParziale>{altri}</Riepilogo>')


def test_13_giugno_2023_non_scarta_iva_stampata_come_differenza():
    parsed = parse_corrispettivo_xml(_xml(
        _riepilogo("3008.01", "3008.01", "300.80")
        + _riepilogo("0.98", "0.98", "0.22"), contanti="2213.51", pos="1096.50"))

    assert parsed["totale_imponibile"] == 3008.99
    assert parsed["totale_iva"] == 301.02
    assert parsed["lordo_riepiloghi"] == parsed["totale"] == 3310.01
    assert parsed["motivo_scarto"] is None
    assert parsed["pagato_non_riscosso"] == 0


def test_3_giugno_2023_lo_scarto_reale_3_80_non_diventa_credito():
    parsed = parse_corrispettivo_xml(_xml(
        _riepilogo("4194.18", "4194.18", "419.42"), contanti="3103.40", pos="1506.40"))

    assert parsed["lordo_riepiloghi"] == 4613.60
    assert parsed["totale"] == 4609.80
    assert round(parsed["lordo_riepiloghi"] - parsed["totale"], 2) == 3.80
    assert parsed["motivo_scarto"] == "non_riscosso_non_dichiarato"
    assert parsed["pagato_non_riscosso"] == 0


def test_resi_e_annulli_gia_esclusi_da_parziale_non_si_sottraggono_due_volte():
    parsed = parse_corrispettivo_xml(_xml(_riepilogo("140.00", "100.00", "10.00", altri=(
        '<TotaleAmmontareResi>25.00</TotaleAmmontareResi>'
        '<TotaleAmmontareAnnulli>15.00</TotaleAmmontareAnnulli>')), contanti="110.00"))

    assert parsed["totale_imponibile"] == 100.00
    assert parsed["riepilogo_iva"][0]["ammontare_xml"] == 140.00
    assert parsed["lordo_riepiloghi"] == 110.00
    assert parsed["motivo_scarto"] is None


@pytest.mark.parametrize("contanti,motivo", [("0.00", None),
    ("110.00", "non_riscosso_non_dichiarato")])
def test_importo_parziale_zero_e_un_valore_fiscale_non_un_fallback(contanti, motivo):
    parsed = parse_corrispettivo_xml(_xml(_riepilogo("100.00", "0.00", "0.00",
        altri='<TotaleAmmontareAnnulli>100.00</TotaleAmmontareAnnulli>'), contanti=contanti))

    assert parsed["totale_imponibile"] == parsed["lordo_riepiloghi"] == 0
    assert parsed["motivo_scarto"] == motivo


def test_riepilogo_interamente_zero_non_permette_incassi_nonzero():
    parsed = parse_corrispettivo_xml(_xml(
        _riepilogo("0.00", "0.00", "0.00"), contanti="110.00"))

    assert parsed["lordo_riepiloghi"] == 0
    assert parsed["motivo_scarto"] == "non_riscosso_non_dichiarato"
    assert parsed["quadratura_pagamenti_status"] == "ERRORE"


def test_senza_ripartizione_pagamenti_la_quadratura_non_e_verificata():
    xml = ('<DatiCorrispettivi><DatiRT>'
           + _riepilogo("100.00", "100.00", "10.00")
           + '</DatiRT></DatiCorrispettivi>')
    parsed = parse_corrispettivo_xml(xml)

    assert parsed["quadratura_pagamenti_status"] == "NON_VERIFICABILE"
    assert parsed["motivo_scarto"] is None


@pytest.mark.parametrize("regime", ["<Natura>N4</Natura>",
    "<VentilazioneIVA>SI</VentilazioneIVA>"])
def test_natura_e_ventilazione_non_inventano_iva(regime):
    parsed = parse_corrispettivo_xml(_xml(
        _riepilogo("110.00", "110.00", "0.00", regime=regime), contanti="110.00"))

    assert parsed["lordo_riepiloghi"] == 110.00
    assert parsed["totale_iva"] == 0
    assert parsed["quadratura_iva_status"] == "NON_VERIFICABILE"
    assert parsed["motivo_scarto"] is None


@pytest.mark.parametrize("voce", ["NonRiscossoServizi", "NonRiscossoFatture",
    "NonRiscossoDCRaSSN", "NonRiscossoOmaggio", "BeniInSospeso", "TotaleDaFattureRT"])
def test_componenti_nette_del_riepilogo_richiedono_verifica_non_crediti_lordi(voce):
    parsed = parse_corrispettivo_xml(_xml(
        _riepilogo("120.00", "100.00", "10.00", altri=f'<{voce}>20.00</{voce}>'),
        contanti="110.00"))

    assert parsed["motivo_scarto"] == "componenti_fiscali_da_verificare"
    assert parsed["quadratura_pagamenti_status"] == "NON_VERIFICABILE"
    assert parsed["pagato_non_riscosso"] == 0
    assert parsed["componenti_fiscali_da_verificare"] == [
        {"voce": voce, "importo_cents": 2000, "blocco": "Riepilogo"}]


@pytest.mark.parametrize("voce", ["ScontoApagare", "PagatoTicket"])
def test_altri_pagamenti_dichiarati_restano_visibili_e_richiedono_mapping_contabile(voce):
    parsed = parse_corrispettivo_xml(_xml(_riepilogo("100.00", "100.00", "10.00"),
        contanti="100.00", altri_totali=f'<{voce}>10.00</{voce}>'))

    assert parsed["motivo_scarto"] == "componenti_fiscali_da_verificare"
    assert parsed["pagato_non_riscosso"] == 0
    assert parsed["componenti_fiscali_da_verificare"][0]["voce"] == voce


def test_non_riscosso_lordo_legacy_in_totali_resta_supportato():
    parsed = parse_corrispettivo_xml(xml_chiusura(
        imponibile="1000.00", imposta="100.00", non_riscosso_servizi="100.00"))

    assert parsed["motivo_scarto"] is None
    assert parsed["totale"] == 1100.00
    assert parsed["pagato_non_riscosso"] == 100.00


def test_legacy_senza_parziale_non_ricalcola_iva_assente():
    xml = xml_chiusura(imponibile="1000.00", imposta="", contanti="1000.00", elettronico="0.00")
    parsed = parse_corrispettivo_xml(xml)

    assert parsed["totale_iva"] == 0
    assert parsed["quadratura_iva_status"] == "NON_VERIFICABILE"
    assert parsed["motivo_scarto"] is None
