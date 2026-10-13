import asyncio
from mongomock_motor import AsyncMongoMockClient
from app.lotti.routers import ordini_fornitori as ordini
from app.lotti.routers.ordini_fornitori import (
    _articolo_fattura_per_riga,
    _fornitore_unico_righe,
    _peso_kg_da_riga_ordine,
    _quantita_riga_ordine,
    _riga_con_prezzo_fattura,
)
from fastapi import HTTPException
import pytest


def test_aggiornamento_prezzo_aperto_calcola_confezione_iva_e_storico():
    riga = {"prodotto_id": "cat_saima-N031", "nome": "Crema nocciola", "unita": "13 KG",
            "prezzo_ultimo": 4.11, "iva_pct": 0}
    articolo = {"prezzo": 4.50, "unita_confezione": "KG", "iva_pct": 10}
    aggiornata, cambiata = _riga_con_prezzo_fattura(riga, articolo, "2026-10-13T06:30:00Z")
    assert cambiata is True
    assert aggiornata["prezzo_unitario_fattura"] == 4.50
    assert aggiornata["prezzo_ultimo"] == 58.50
    assert aggiornata["iva_pct"] == 10
    assert aggiornata["prezzo_precedente"] == 4.11
    assert aggiornata["storico_prezzi"][-1]["da"] == 4.11


def test_prezzo_invariato_non_crea_un_falso_aggiornamento():
    riga = {"nome": "Prodotto", "unita": "1 PZ", "prezzo_ultimo": 5, "iva_pct": 10}
    aggiornata, cambiata = _riga_con_prezzo_fattura(
        riga, {"prezzo": 5, "unita_confezione": "PZ", "iva_pct": 10}, "oggi")
    assert cambiata is False and aggiornata == riga


def test_collega_nomi_catalogo_fattura_solo_quando_univoci_e_compatibili():
    articoli = [
        {"id": "a1", "nome": "Farina da kg1 di mandorle pelate", "codice_articolo": "SAIMA 1069"},
        {"id": "a2", "nome": "Mezzelune di gelatina al limone kg 2", "codice_articolo": "SAIMA 1565"},
        {"id": "a3", "nome": "CARTA DA FORNO SILICONATA CM 60X40 PZ 500", "codice_articolo": "NOVACART 078"},
        {"id": "a4", "nome": "SAC A POCHE TRASPARENTI MONOUSO DA CM53 PZ 72", "codice_articolo": "NOVACART 050"},
    ]
    assert _articolo_fattura_per_riga(
        {"nome": "Farina Di Mandorle Pelate", "unita": "pz"}, articoli
    )["id"] == "a1"
    assert _articolo_fattura_per_riga(
        {"nome": "Mezzelune Limone Di Gelatina", "unita": "pz"}, articoli
    )["id"] == "a2"
    assert _articolo_fattura_per_riga(
        {"nome": "Carta Da Forno Cm 40X60", "unita": "cf 500 pz"}, articoli
    )["id"] == "a3"
    # Misura e numero pezzi diversi: nessuna associazione inventata.
    assert _articolo_fattura_per_riga(
        {"nome": "Sac A Poche Piccole Trasparenti H30 Cm", "unita": "cf 100 pz"}, articoli
    ) is None


def test_nome_generico_o_ambiguo_non_riceve_un_prezzo():
    articoli = [
        {"id": "v1", "nome": "PASSATA VISCIOLA LABO GARDEN FRUIT DA KG 12,5"},
        {"id": "v2", "nome": "VISCIOLATA PUGLIA DA KG 6,5"},
        {"id": "n1", "nome": "Essenza neroly bigarade gr 80"},
    ]
    assert _articolo_fattura_per_riga({"nome": "Ambrosio Visciola", "unita": "pz"}, articoli) is None
    assert _articolo_fattura_per_riga({"nome": "Ruffini Aroma Liquido Neroly", "unita": "pz"}, articoli) is None


def test_peso_cartone_moltiplica_numero_confezioni_per_kg():
    assert _peso_kg_da_riga_ordine({"unita": "ct 8 x 2 kg"}) == 16
    aggiornata, cambiata = _riga_con_prezzo_fattura(
        {"nome": "Scaglietta surrogato fondente", "unita": "ct 8 x 2 kg", "prezzo_ultimo": 0},
        {"prezzo": 7.775, "unita_confezione": "KG", "iva_pct": 10},
        "2026-10-13T06:30:00Z",
    )
    assert cambiata is True
    assert aggiornata["prezzo_ultimo"] == 124.4


def test_prodotti_catalogo_accettano_solo_confezioni_intere():
    riga = {"prodotto_id": "cat_glf-002", "quantita": 2, "unita": "13 kg"}
    assert _quantita_riga_ordine(riga) == 2
    with pytest.raises(HTTPException, match="confezioni intere"):
        _quantita_riga_ordine(riga, 2.5)
    assert _quantita_riga_ordine({"prodotto_id": "sfuso", "quantita": 0.5}) == 0.5


def test_fornitore_unico_ignora_maiuscole_punti_e_spazi_ma_non_nomi_diversi():
    assert _fornitore_unico_righe([
        {"fornitore": "SAIMA S.p.a."},
        {"fornitore": "SAIMA S.p.A"},
        {"fornitore": "  saima spa  "},
    ]) == "SAIMA S.p.a."
    assert _fornitore_unico_righe([
        {"fornitore": "SAIMA S.p.a."}, {"fornitore": "MEPA Alimentari"}
    ]) == ""
    assert _fornitore_unico_righe([{"fornitore": "DA ASSEGNARE"}]) == ""


def test_recupero_bozza_nel_carrello_e_annullamento_conservano_lo_storico(monkeypatch):
    async def scenario():
        database = AsyncMongoMockClient().lotti
        monkeypatch.setattr(ordini, "db", database)
        await database.ordini_fornitori.insert_one({"id": "o1", "stato": "bozza", "prodotti": [
            {"prodotto_id": "cat_saima-N031", "nome": "Crema", "fornitore": "SAIMA",
             "quantita": 2, "unita": "13 KG", "prezzo_ultimo": 53.43, "iva_pct": 10}]})
        recuperato = await ordini.riporta_ordine_al_carrello("o1", _admin=True)
        assert recuperato["righe"][0]["id"] == "saima-N031"
        assert (await database.ordini_fornitori.find_one({"id": "o1"}))["stato"] == "in_modifica"
        await ordini.elimina_ordine("o1", _admin=True)
        assert (await database.ordini_fornitori.find_one({"id": "o1"}))["stato"] == "annullato"
        assert await database.ordini_fornitori.count_documents({"id": "o1"}) == 1
    asyncio.run(scenario())
