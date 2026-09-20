"""Una chiusura di cassa non è una fattura, e non è nemmeno un errore.

Il 20/09/2026, in `01_FATTURE_RICEVUTE/FATTURE/2026/Errori` su Drive c'erano
**19 chiusure RT** (tracciato COR10, radice `DatiCorrispettivi`). Il canale
fatture le leggeva come XML rotti — «FatturaElettronicaBody non trovato» — le
spediva in `Errori` e le rileggeva a ogni giro senza mai importarle. Con loro
erano fuori dai conti gli incassi del 25, 26 e 27 agosto 2026: il solo 27/08
vale 2.570,20 € (346 documenti commerciali, 655,70 contanti + 1.914,50
elettronico).

Il file si riconosce dal **contenuto**, mai dal nome: i file RT si chiamano
`<progressivo>_<piva>.xml`, cioè esattamente come certe fatture.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from app.routers.invoices import fatture_upload as fu_mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


# Una chiusura RT vera, ridotta ai soli elementi che il parser legge: è la
# giornata del 27/08/2026 letta da Drive (file 3602835794_04523831214.xml).
CHIUSURA_RT = """<?xml version="1.0" encoding="UTF-8"?><n1:DatiCorrispettivi \
xmlns:n1="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/corrispettivi/dati/v1.0" \
versione="COR10">
    <Trasmissione>
        <Progressivo>2627</Progressivo>
        <Formato>COR10</Formato>
        <Dispositivo><Tipo>RT</Tipo><IdDispositivo>99MEY026532</IdDispositivo></Dispositivo>
        <CodiceFiscaleEsercente>04523831214</CodiceFiscaleEsercente>
        <PIVAEsercente>04523831214</PIVAEsercente>
        <DataOraTrasmissione>2026-08-27T20:51:23+02:00</DataOraTrasmissione>
    </Trasmissione>
    <DataOraRilevazione>2026-08-27T20:50:47+02:00</DataOraRilevazione>
    <DatiRT>
        <Riepilogo>
            <IVA><AliquotaIVA>10.00</AliquotaIVA><Imposta>233.65</Imposta></IVA>
            <Ammontare>2336.55</Ammontare>
            <ImportoParziale>2336.55</ImportoParziale>
        </Riepilogo>
        <Totali>
            <NumeroDocCommerciali>346</NumeroDocCommerciali>
            <PagatoContanti>655.70</PagatoContanti>
            <PagatoElettronico>1914.50</PagatoElettronico>
        </Totali>
    </DatiRT>
</n1:DatiCorrispettivi>"""

FATTURA = """<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12">
  <FatturaElettronicaHeader><CedentePrestatore><DatiAnagrafici>
    <IdFiscaleIVA><IdCodice>01879020517</IdCodice></IdFiscaleIVA>
    <Anagrafica><Denominazione>RONDINELLA MARKET S.R.L.</Denominazione></Anagrafica>
  </DatiAnagrafici></CedentePrestatore></FatturaElettronicaHeader>
  <FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento>
    <TipoDocumento>TD01</TipoDocumento><Data>2026-09-01</Data><Numero>856</Numero>
  </DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody>
</p:FatturaElettronica>"""


# ── riconoscere ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("prefisso", ["", "n1:", "p:", "ns2:"])
def test_la_chiusura_rt_si_riconosce_con_qualunque_prefisso(prefisso):
    """Ogni registratore telematico scrive il namespace a modo suo."""
    xml = CHIUSURA_RT.replace("n1:DatiCorrispettivi", f"{prefisso}DatiCorrispettivi")
    assert fu_mod.e_chiusura_rt(xml) is True


def test_il_bom_non_nasconde_la_radice():
    assert fu_mod.e_chiusura_rt("﻿" + CHIUSURA_RT) is True


def test_una_fattura_non_e_una_chiusura():
    assert fu_mod.e_chiusura_rt(FATTURA) is False


def test_il_nome_del_file_non_c_entra():
    """I file RT si chiamano come certe fatture: decide il contenuto.

    `3602835794_04523831214.xml` è una chiusura, `IT01879020517_x.xml` una
    fattura, ma la forma del nome non distingue nulla.
    """
    assert fu_mod.e_chiusura_rt(FATTURA) is False
    assert fu_mod.e_chiusura_rt(CHIUSURA_RT) is True


# ── consegnare al motore giusto ───────────────────────────────────────────

def test_la_chiusura_va_ai_corrispettivi_e_non_agli_errori(monkeypatch):
    """Il caso reale: 19 file in `Errori` che nessun giro riusciva a lavorare."""
    consegnate = []

    async def finto_ingest(db, parsed, filename="", source="xml", **kw):
        consegnate.append({"parsed": parsed, "filename": filename, "source": source,
                           "update_if_exists": kw.get("update_if_exists")})
        return {"action": "created", "corrispettivo_id": "C-1",
                "data": parsed.get("data"), "totale": 2570.20}

    monkeypatch.setattr(
        "app.routers.invoices.corrispettivi_helpers.ingest_corrispettivo_parsed",
        finto_ingest,
    )

    def mai(_xml):
        raise AssertionError("una chiusura RT non deve passare dal parser fatture")

    monkeypatch.setattr(fu_mod, "parse_fattura_xml", mai)

    async def anno_attivo(_db):
        return 2026

    monkeypatch.setattr(
        "app.services.config_import.get_anno_importazione_attivo", anno_attivo)

    res = _run(fu_mod.process_xml_bytes(
        object(), CHIUSURA_RT.encode("utf-8"), "3602835794_04523831214.xml",
        source="google_drive", applica_filtro_anno=True,
    ))

    assert res["status"] == "chiusura_rt", "non è un errore: è un documento di un'altra sezione"
    assert res["importato"] is True
    assert res["data"] == "2026-08-27"
    assert len(consegnate) == 1, "il motore dei corrispettivi va chiamato una volta sola"
    # `source="xml"` non è un dettaglio: è quello che fa marcare il
    # corrispettivo `definitivo_xml` invece di lasciarlo provvisorio.
    assert consegnate[0]["source"] == "xml"
    assert consegnate[0]["update_if_exists"] is False, "mai sovrascrivere una giornata già chiusa"


def test_una_giornata_gia_in_archivio_non_si_riscrive(monkeypatch):
    """Idempotenza: il secondo giro deve dare `duplicate` e zero scritture."""
    async def finto_ingest(db, parsed, **kw):
        return {"action": "duplicate", "corrispettivo_id": "C-1", "data": parsed.get("data")}

    monkeypatch.setattr(
        "app.routers.invoices.corrispettivi_helpers.ingest_corrispettivo_parsed",
        finto_ingest,
    )

    res = _run(fu_mod.process_xml_bytes(
        object(), CHIUSURA_RT.encode("utf-8"), "x.xml", source="google_drive",
    ))

    assert res["status"] == "chiusura_rt"
    assert res["importato"] is False
    assert res["azione"] == "duplicate"


def test_senza_archivio_dice_che_cos_e_senza_scrivere():
    """Anteprima (test, validazione di un upload): si classifica, non si scrive."""
    res = _run(fu_mod.process_xml_bytes(
        None, CHIUSURA_RT.encode("utf-8"), "x.xml", source="xml_upload",
    ))
    assert res["status"] == "chiusura_rt"
    assert res["importato"] is False


def test_una_chiusura_illeggibile_resta_un_errore(monkeypatch):
    """Riconoscerla non vuol dire inghiottirla: un RT rotto va segnalato."""
    monkeypatch.setattr(
        "app.parsers.corrispettivi_parser.parse_corrispettivo_xml",
        lambda _xml: {"error": "Errore parsing XML: mismatched tag"},
    )
    res = _run(fu_mod.process_xml_bytes(
        object(), CHIUSURA_RT.encode("utf-8"), "rotto.xml", source="google_drive",
    ))
    assert res["status"] == "error"
    assert "chiusura RT" in res["error"]


# ── e i tre punti che smistano l'esito devono conoscerlo ──────────────────

def test_tutti_i_giri_drive_conoscono_lo_stato_nuovo():
    """Uno stato sconosciuto finisce nel ramo «errore»: il file andrebbe in
    `Errori` e lo rileggeremmo per sempre. È esattamente il guasto che ha
    tenuto 19 chiusure RT ferme per settimane, e la stessa trappola in cui
    `skipped_altro_anno` stava per cadere il 20/09/2026."""
    from app.services import drive_invoice_ingest

    sorgente = inspect.getsource(drive_invoice_ingest)
    # I tre punti: giro ogni 15 minuti, ricostruzione a lotti, ricostruzione completa
    assert sorgente.count('"chiusura_rt"') == 3, (
        "ogni punto che smista l'esito dell'import deve conoscere `chiusura_rt`"
    )
    # e deve contarle a parte, non confonderle con le fatture importate
    assert sorgente.count('"chiusure_rt"') >= 3


# ── le due trappole trovate rileggendo il diff ────────────────────────────

def test_una_fattura_che_nomina_i_corrispettivi_resta_una_fattura():
    """La fattura vince sempre sulla parola.

    Se bastasse trovare `DatiCorrispettivi` nel testo, una riga di fattura
    intitolata «Servizio DatiCorrispettivi» o un allegato dirotterebbe un
    COSTO dentro i RICAVI: il danno peggiore che questo codice possa fare.
    """
    insidiosa = FATTURA.replace(
        "<TipoDocumento>TD01</TipoDocumento>",
        "<TipoDocumento>TD01</TipoDocumento><Descrizione>"
        "Canone <n1:DatiCorrispettivi> telematici</Descrizione>",
    )
    assert fu_mod.e_chiusura_rt(insidiosa) is False


def test_una_chiusura_di_un_altro_anno_non_entra(monkeypatch):
    """«Solo l'anno attivo» vale per gli incassi come per i costi."""
    async def anno_attivo(_db):
        return 2026

    async def mai(*_a, **_k):
        raise AssertionError("una chiusura di un altro anno non deve essere registrata")

    monkeypatch.setattr(
        "app.services.config_import.get_anno_importazione_attivo", anno_attivo)
    monkeypatch.setattr(
        "app.routers.invoices.corrispettivi_helpers.ingest_corrispettivo_parsed", mai)

    vecchia = CHIUSURA_RT.replace("2026-08-27", "2024-08-27")
    res = _run(fu_mod.process_xml_bytes(
        object(), vecchia.encode("utf-8"), "vecchia.xml",
        source="google_drive", applica_filtro_anno=True,
    ))

    assert res["status"] == "chiusura_rt"
    assert res["importato"] is False
    assert res["anno"] == 2024 and res["anno_attivo"] == 2026


def test_senza_filtro_anno_una_chiusura_vecchia_entra(monkeypatch):
    """Upload manuale: se la carichi tu, la vuoi."""
    registrate = []

    async def finto_ingest(db, parsed, **kw):
        registrate.append(parsed.get("data"))
        return {"action": "created", "corrispettivo_id": "C-9", "data": parsed.get("data")}

    monkeypatch.setattr(
        "app.routers.invoices.corrispettivi_helpers.ingest_corrispettivo_parsed",
        finto_ingest,
    )
    vecchia = CHIUSURA_RT.replace("2026-08-27", "2024-08-27")
    res = _run(fu_mod.process_xml_bytes(
        object(), vecchia.encode("utf-8"), "vecchia.xml", source="xml_upload",
    ))
    assert res["importato"] is True
    assert registrate == ["2024-08-27"]
