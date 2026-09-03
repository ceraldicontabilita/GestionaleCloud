"""
test_prezzi_da_fatture.py
──────────────────────────
Regression test per applica_prezzo_da_fatture (routers/utils.py), il motore
UNICO che aggancia ai cataloghi (Saima/MePA/Acquaviva/Alfa/catalogo forno:
Bindi, Il Pasticcere, Tre Marie) prezzo e quantità realmente pagati in
fattura XML. Richiesta Enzo 03/07/2026: "quando ricevi una fattura devi
importare il prezzo e l'eventuale quantità nei cataloghi corrispondenti,
così sfogliando si vede che quel prodotto è già stato comprato".
Funzione pura: nessuna rete/DB.
"""
from app.lotti.routers.utils import applica_prezzo_da_fatture


def _prodotti():
    return [
        {"nome": "Cornetto Elite All'albicocca"},
        {"nome": "Gran Croissant Davì"},
        {"nome": "Muffin Mirtilli"},
    ]


def test_match_esatto_imposta_prezzo_quantita_e_flag():
    prezzi = {"cornetto elite all'albicocca": {"prezzo": 42.5, "quantita": 3, "data": "2026-06-01"}}
    out = applica_prezzo_da_fatture(_prodotti(), prezzi)
    comprato = out[0]
    assert comprato["gia_acquistato"] is True
    assert comprato["prezzo_listino"] == 42.5
    assert comprato["prezzo_fattura"] == 42.5
    assert comprato["prezzo_fattura_fonte"] == "fattura_xml"
    assert comprato["quantita_ultima_fattura"] == 3
    assert comprato["prezzo_fattura_data"] == "2026-06-01"


def test_non_comprati_restano_senza_prezzo():
    prezzi = {"cornetto elite all'albicocca": {"prezzo": 42.5, "quantita": 3, "data": "2026-06-01"}}
    out = applica_prezzo_da_fatture(_prodotti(), prezzi)
    for prod in out[1:]:
        assert prod["gia_acquistato"] is False
        assert prod["prezzo_listino"] == 0
        assert "quantita_ultima_fattura" not in prod  # mai inventata


def test_nessuna_fattura_nessun_acquistato():
    out = applica_prezzo_da_fatture(_prodotti(), {})
    assert all(p["gia_acquistato"] is False for p in out)
    assert all(p["prezzo_listino"] == 0 for p in out)


def test_match_fuzzy_richiede_forte_sovrapposizione():
    # "vassoio stella" NON deve matchare "stella di natale" (bug storico
    # dei match per sottostringa: vassoio -> Tè). Jaccard/coverage bassi.
    prezzi = {"vassoio stella trasparente": {"prezzo": 5.0, "quantita": 1, "data": "2026-01-01"}}
    out = applica_prezzo_da_fatture([{"nome": "Torta Stella di Natale al cioccolato"}], prezzi)
    assert out[0]["gia_acquistato"] is False


def test_match_fuzzy_su_nome_quasi_identico():
    # stesso prodotto scritto con piccole differenze (ordine/punteggiatura)
    prezzi = {"croissant gran davi": {"prezzo": 31.2, "quantita": 2, "data": "2026-05-10"}}
    out = applica_prezzo_da_fatture([{"nome": "Gran Croissant Davì"}], prezzi)
    assert out[0]["gia_acquistato"] is True
    assert out[0]["prezzo_listino"] == 31.2
    assert out[0]["quantita_ultima_fattura"] == 2


def test_match_per_codice_articolo_vince_anche_con_nome_diverso():
    # In fattura la descrizione può essere abbreviata/diversa dal catalogo:
    # il CodiceArticolo del fornitore è lo stesso → match deterministico.
    prezzi = {
        "tiramisu pist. monop. ct10": {"prezzo": 38.9, "quantita": 2, "data": "2026-06-20"},
        "codart::1656": {"prezzo": 38.9, "quantita": 2, "data": "2026-06-20"},
    }
    out = applica_prezzo_da_fatture(
        [{"nome": "Tiramisù Pistacchio", "codice_articolo": "1656"}], prezzi)
    assert out[0]["gia_acquistato"] is True
    assert out[0]["prezzo_listino"] == 38.9


def test_match_codice_ignora_zeri_iniziali():
    # catalogo "0862" vs fattura "862" (o viceversa): stesso codice
    prezzi = {"codart::862": {"prezzo": 55.0, "quantita": 1, "data": "2026-06-01"}}
    out = applica_prezzo_da_fatture(
        [{"nome": "Gran Croissant Crema e Amarena", "codice_articolo": "0862"}], prezzi)
    assert out[0]["gia_acquistato"] is True
    assert out[0]["prezzo_listino"] == 55.0


def test_matcha_codici_vecchio_e_nuovo_vandemoortele():
    prezzi = {"codart::57216": {"prezzo": 48.27, "quantita": 1, "data": "2026-08-01"}}
    out = applica_prezzo_da_fatture([{
        "nome": "Croissant cannella",
        "codice_aqv_2025": "CR0072",
        "codice_aqv_2026": "57216",
    }], prezzi)
    assert out[0]["gia_acquistato"] is True
    assert out[0]["prezzo_fattura"] == 48.27


def test_alias_fattura_abbreviato_matcha_solo_il_prodotto_corretto():
    prezzi = {"aqv croi str pstch btr 95g 4.94kg": {"prezzo": 53.60, "quantita": 1, "data": "2026-08-01"}}
    prodotti = [
        {"nome": "Croissant nocciola burro 95g"},
        {"nome": "Croissant pistacchio burro 95g", "alias_fattura": ["AQV CROI STR PSTCH BTR 95G 4.94KG"]},
    ]
    out = applica_prezzo_da_fatture(prodotti, prezzi)
    assert out[0]["gia_acquistato"] is False
    assert out[1]["prezzo_fattura"] == 53.60


def test_fuzzy_non_riusa_la_stessa_riga_su_due_varianti():
    prezzi = {"croissant gran davi": {"prezzo": 31.2, "quantita": 2, "data": "2026-05-10"}}
    out = applica_prezzo_da_fatture([
        {"nome": "Gran Croissant Davì"},
        {"nome": "Gran Croissant Davì Pistacchio"},
    ], prezzi)
    assert sum(1 for p in out if p["gia_acquistato"]) == 1


def test_chiavi_codart_non_inquinano_il_fuzzy():
    # un prodotto SENZA codice non deve mai matchare per caso una chiave codart::
    prezzi = {"codart::1656": {"prezzo": 38.9, "quantita": 2, "data": "2026-06-20"}}
    out = applica_prezzo_da_fatture([{"nome": "Prodotto Qualunque Diverso"}], prezzi)
    assert out[0]["gia_acquistato"] is False


def test_parser_xml_estrae_codice_articolo():
    from app.lotti.routers.xml_helpers import parse_fattura_xml
    xml = b"""<?xml version="1.0"?>
    <FatturaElettronica>
      <CedentePrestatore><Denominazione>BINDI S.P.A.</Denominazione>
        <IdCodice>00123456789</IdCodice></CedentePrestatore>
      <Numero>42</Numero><Data>2026-06-20</Data>
      <DettaglioLinee>
        <CodiceArticolo><CodiceTipo>FOR</CodiceTipo><CodiceValore>1656</CodiceValore></CodiceArticolo>
        <Descrizione>TIRAMISU PISTACCHIO MONOPORZIONE</Descrizione>
        <Quantita>2.00</Quantita><PrezzoUnitario>38.90</PrezzoUnitario>
        <UnitaMisura>CT</UnitaMisura>
      </DettaglioLinee>
    </FatturaElettronica>"""
    dati = parse_fattura_xml(xml)
    assert len(dati["prodotti"]) == 1
    assert dati["prodotti"][0]["codice_articolo"] == "1656"
    assert dati["prodotti"][0]["descrizione"] == "TIRAMISU PISTACCHIO MONOPORZIONE"
