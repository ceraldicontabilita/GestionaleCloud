"""Collaudo funzionale: fattura emessa dopo lo scontrino.

CLAUDE.md: «Fattura emessa = cedente e' la nostra P.IVA (`FISCAL_COMPANY_ID`),
da ogni ingresso: `fatture_emesse`, mai `invoices`. Fatta dopo lo scontrino:
**non aumenta ricavi, IVA ne' crediti**; si aggancia al corrispettivo del giorno
dello scontrino (dalla causale, se no data fattura) se unico; clienti per
P.IVA -> C.F.»
"""
from app.routers.invoices.fatture_upload import process_xml_bytes
from app.services import fatture_emesse as fe
from app.services.conto_economico_gestionale import ricavi_corrispettivi
from app.services.iva_liquidation_query import corrispettivi_periodo

from ._comune import PIVA, Importatore, attive, nuovo_db, righe, run, xml_chiusura

CAUSALE = ("fattura gia in corrispettivi per emissione scontino fiscale del giorno "
           "10 Luglio 2026 numero 2586-0352, iva gia in corrispettivi")


def _fattura(numero="FPR 7/26", data="2026-07-20", cedente=PIVA, causale=CAUSALE,
             cliente_piva="01234567890"):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader>
 <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{cedente}</IdCodice></IdFiscaleIVA>
  <Anagrafica><Denominazione>Cedente</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
  <Sede><Indirizzo>Via A</Indirizzo><CAP>80100</CAP><Comune>Napoli</Comune><Nazione>IT</Nazione></Sede></CedentePrestatore>
 <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{cliente_piva}</IdCodice></IdFiscaleIVA>
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


def _giornata_luglio(imp, giorno="2026-07-10", progressivo="2586"):
    imp.importa(f"{progressivo}.xml", xml_chiusura(data=giorno, progressivo=progressivo))


def _cifre(db):
    """Cio' che una fattura emessa NON deve muovere: ricavi, IVA a debito, giornale,
    Prima Nota, fatture passive, partite."""
    ricavi = run(ricavi_corrispettivi(db, {"$gte": "2026-07-01", "$lte": "2026-07-31"}))
    iva = run(corrispettivi_periodo(db, "2026-07"))
    return {
        "ricavi_imponibile": ricavi["imponibile"],
        "iva_vendite_cents": iva["iva_vendite_cents"],
        "giornale": len(run(righe(db, "movimenti_contabili"))),
        "cassa": len(run(righe(db, "prima_nota_cassa"))),
        "banca": len(run(righe(db, "prima_nota_banca"))),
        "passive": len(run(righe(db, "invoices"))),
        "partite": len(run(righe(db, "partite_aperte"))),
        "crediti": len(run(righe(db, "crediti"))),
    }


def test_fattura_emessa_non_muove_ricavi_iva_giornale_ne_crediti_e_si_aggancia_al_corrispettivo(monkeypatch):
    db = nuovo_db("s7_emessa")
    imp = Importatore(db, monkeypatch)
    _giornata_luglio(imp)
    (corr,) = run(attive(db, "corrispettivi"))
    prima = _cifre(db)
    assert prima["ricavi_imponibile"] == 909.09 and prima["giornale"] == 1

    esito = run(process_xml_bytes(db, _fattura(), "FPR_7_26.xml", source="email_gmail"))

    assert esito["status"] == "fattura_emessa"
    assert _cifre(db) == prima                        # nessun ricavo, IVA, scrittura o credito in piu'
    (f,) = run(righe(db, fe.COLL))
    assert f["incide_su_ricavi"] is False and f["gia_in_corrispettivi"] is True
    assert f["pagato"] is True and f["stato_pagamento"] == "pagata"       # non e' un credito
    # Si aggancia al corrispettivo del giorno dello SCONTRINO (10/07), non a quello della fattura (20/07).
    assert f["scontrino"] == {"data": "2026-07-10", "numero": "2586-0352", "fonte": "causale"}
    assert f["corrispettivo"]["stato"] == "SODDISFATTO"
    assert f["corrispettivo"]["corrispettivo_id"] == corr["id"]
    # Il cliente e' identificato per P.IVA.
    (cliente,) = run(righe(db, fe.COLL_CLIENTI))
    assert cliente["id"] == "CLI-piva-01234567890"


def test_la_stessa_fattura_emessa_dal_documenti_import_non_crea_niente_di_nuovo(monkeypatch):
    db = nuovo_db("s7_import")
    imp = Importatore(db, monkeypatch)
    _giornata_luglio(imp)

    primo = imp.importa("FPR_7_26.xml", _fattura())
    prima = _cifre(db)
    secondo = imp.importa("FPR_7_26_copia.xml", _fattura())

    assert primo["tipo_rilevato"] == "fattura_emessa" and primo["imported"] == 1
    assert secondo["duplicate"] is True and secondo["imported"] == 0
    assert _cifre(db) == prima
    assert len(run(righe(db, fe.COLL))) == 1 and len(run(righe(db, fe.COLL_CLIENTI))) == 1
    assert run(righe(db, "invoices")) == []                       # mai fra le passive


def test_due_corrispettivi_lo_stesso_giorno_non_si_sceglie_da_soli(monkeypatch):
    """Due chiusure vere lo stesso giorno: la fattura resta da scegliere, niente di inventato."""
    db = nuovo_db("s7_due")
    imp = Importatore(db, monkeypatch)
    _giornata_luglio(imp, progressivo="2586")
    _giornata_luglio(imp, progressivo="2587")
    assert len(run(attive(db, "corrispettivi"))) == 2

    run(process_xml_bytes(db, _fattura(), "f.xml", source="test"))

    (f,) = run(righe(db, fe.COLL))
    assert f["corrispettivo"]["stato"] == "DA_VERIFICARE"
    assert len(f["corrispettivo"]["candidati"]) == 2
    assert "corrispettivo_id" not in f["corrispettivo"]


def test_corrispettivo_arrivato_dopo_la_fattura_si_aggancia_dal_giro(monkeypatch):
    db = nuovo_db("s7_dopo")
    imp = Importatore(db, monkeypatch)
    run(process_xml_bytes(db, _fattura(), "f.xml", source="test"))
    (f,) = run(righe(db, fe.COLL))
    assert f["corrispettivo"]["stato"] == "ATTESO"

    _giornata_luglio(imp)                                           # arriva l'XML del 10/07
    assert run(fe.riallinea(db))["agganciate"] == 1

    (f,) = run(righe(db, fe.COLL))
    (corr,) = run(attive(db, "corrispettivi"))
    assert f["corrispettivo"]["stato"] == "SODDISFATTO" and f["corrispettivo"]["corrispettivo_id"] == corr["id"]


def test_un_corrispettivo_ritirato_non_e_un_candidato(monkeypatch):
    """La giornata senza documento sostituita dall'XML (status deleted) non e' un secondo
    corrispettivo: la fattura si aggancia al solo XML."""
    db = nuovo_db("s7_ritirata")
    run(db["corrispettivi"].insert_one({"id": "vecchia", "data": "2026-07-10", "totale": 1000.0,
                                        "status": "deleted", "deleted_reason": "sostituita_da_chiusura_xml"}))
    imp = Importatore(db, monkeypatch)
    _giornata_luglio(imp)

    run(process_xml_bytes(db, _fattura(), "f.xml", source="test"))

    (f,) = run(righe(db, fe.COLL))
    (corr,) = run(attive(db, "corrispettivi"))
    assert f["corrispettivo"]["corrispettivo_id"] == corr["id"]


def test_la_scelta_del_titolare_vince_e_resta(monkeypatch):
    db = nuovo_db("s7_scelta")
    imp = Importatore(db, monkeypatch)
    _giornata_luglio(imp, progressivo="2586")
    _giornata_luglio(imp, progressivo="2587")
    run(process_xml_bytes(db, _fattura(), "f.xml", source="test"))
    (f,) = run(righe(db, fe.COLL))
    scelto = f["corrispettivo"]["candidati"][1]

    assert run(fe.scegli_corrispettivo(db, f["id"], scelto))["success"]
    run(fe.riallinea(db))

    (f,) = run(righe(db, fe.COLL))
    assert f["corrispettivo"]["corrispettivo_id"] == scelto and f["corrispettivo"]["scelto_da_titolare"] is True


def test_senza_data_nella_causale_vale_la_data_della_fattura(monkeypatch):
    db = nuovo_db("s7_data_fattura")
    imp = Importatore(db, monkeypatch)
    _giornata_luglio(imp, giorno="2026-07-20", progressivo="2600")

    run(process_xml_bytes(db, _fattura(causale="Prodotto gia scontrinato, iva gia in corrispettivi"),
                          "f.xml", source="test"))

    (f,) = run(righe(db, fe.COLL))
    assert f["scontrino"]["fonte"] == "data_fattura"
    assert f["corrispettivo"]["stato"] == "SODDISFATTO"


def test_una_fattura_ricevuta_resta_un_costo_e_non_e_toccata_dal_riconoscimento(monkeypatch):
    db = nuovo_db("s7_ricevuta")
    esito = run(process_xml_bytes(db, _fattura(cedente="09876543210"), "ricevuta.xml", source="test"))
    assert esito["status"] != "fattura_emessa"
    assert run(righe(db, fe.COLL)) == []
