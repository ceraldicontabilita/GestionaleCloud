"""Un quadro del 770 caricato da solo si aggancia al suo 770, non resta «da classificare».

Il testo e' quello vero di «02_Quadro_ST_modulo_1.pdf» (stampa AdE del 770
2019 di Ceraldi Group), ridotto alle righe che contano.
"""
import asyncio

from app.routers import documenti
from app.services import componenti_770 as c770

TESTO_ST = (
    "Data: 10/08/2026 - Ore: 05:00:16 - Utente: 04523831214 Soggetto: CERALDI GROUP S.R.L. "
    "( 04523831214 ) Identificativo dichiarazione: 10523651165 - 0000002 del 3/12/2020\n"
    "CODICE FISCALE 04523831214\nQUADRO ST\n"
    "Ritenute operate, trattenute per assistenza fiscale, e imposte sostitutive Mod. N.\n"
    "01 2019 997,24 997,24\n1001 18 02 2019\n"
)


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    def find(self, _query, _projection=None):
        return self

    async def to_list(self, _n):
        return list(self.docs)


class _Db(dict):
    def __getitem__(self, name):
        return _Coll(self.get(name, []))


def test_riconosce_il_quadro_st_del_770():
    assert c770.quadro("02_Quadro_ST_modulo_1 (dup1).pdf", TESTO_ST) == "ST"
    assert c770.quadro("02_Quadro_ST_modulo_1__3.pdf", TESTO_ST) == "ST"
    assert c770.identificativo(TESTO_ST) == "10523651165-0000002"


def test_non_scambia_altri_documenti_per_un_quadro_770():
    # la dichiarazione intera non si chiama «Quadro …»
    assert c770.quadro("Modello 770 - Anno 2019 - 10523651165-0000002.pdf", TESTO_ST) is None
    # un quadro di Redditi non e' del 770
    assert c770.quadro("05_Quadro_RN.pdf", TESTO_ST.replace("QUADRO ST", "QUADRO RN")) is None
    # nome e testo devono dire lo stesso quadro
    assert c770.quadro("02_Quadro_SV.pdf", TESTO_ST) is None
    # senza identificativo della dichiarazione non c'e' prova
    assert c770.quadro("02_Quadro_ST.pdf", "QUADRO ST\nRitenute operate") is None


def test_aggancia_solo_il_770_con_lo_stesso_identificativo():
    db = _Db({"fiscal_documents": [
        {"id": "D-2019", "filename": "Modello 770 - Anno 2019 - 10523651165-0000002.pdf"},
        {"id": "D-2019-B", "filename": "Modello 770 - Anno 2019 - 12454715919-0000009.pdf"},
        {"id": "D-2020", "filename": "770_2020_imposta_2019_T201203105236511652.pdf"},
    ]})
    meta = asyncio.run(c770.metadati(db, filename="02_Quadro_ST_modulo_1 (dup1).pdf", testo=TESTO_ST))
    assert meta["dichiarazione_id"] == "D-2019"
    assert meta["stato_aggancio"] == "AGGANCIATO"
    assert meta["quadro"] == "ST" and meta["modulo"] == 1
    assert meta["obligation_status"] == "NON_APPLICABILE"


def test_senza_il_770_intero_resta_conservato_e_da_verificare():
    meta = asyncio.run(c770.metadati(_Db(), filename="02_Quadro_ST_modulo_1.pdf", testo=TESTO_ST))
    assert meta["dichiarazione_id"] is None
    assert meta["stato_aggancio"] == "DICHIARAZIONE_INTERA_MANCANTE"


def test_l_import_lo_classifica_come_quadro_del_770(monkeypatch):
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_a, **_k: TESTO_ST)
    tipo = documenti.detect_document_type("02_Quadro_ST_modulo_1 (dup1).pdf", b"%PDF-1.6 finto")
    assert tipo == "componente_770"
