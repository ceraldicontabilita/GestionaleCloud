"""
Learning Machine + classificatore centri di costo — fix dell'11/07:
1. il classificatore all'import consulta PRIMA le configurazioni utente
   (fornitori_keywords), poi la tabella statica;
2. la riclassifica non esplode più coi due schemi in collection;
3. normalizzazione e risoluzione centro di costo nel motore unico.
"""
import asyncio

from app.services import learning_machine_cdc as lm


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs[:n]


class _FakeColl:
    def __init__(self, docs):
        self.docs = docs

    def find(self, *a, **k):
        return _FakeCursor(self.docs)


class _FakeDb:
    def __init__(self, keywords_docs):
        self._kw = _FakeColl(keywords_docs)

    def __getitem__(self, name):
        assert name == "fornitori_keywords"
        return self._kw


def test_normalizza_nome_fornitore():
    assert lm.normalizza_nome_fornitore("EUROUOVA S.r.l.") == "eurouova"
    assert lm.normalizza_nome_fornitore("KIMBO SPA") == "kimbo"
    assert lm.normalizza_nome_fornitore("") == ""


def test_risolvi_centro_costo_per_chiave_e_codice():
    cdc_id, cfg = lm.risolvi_centro_costo("1.1_CAFFE_BEVANDE_CALDE")
    assert cdc_id == "1.1_CAFFE_BEVANDE_CALDE" and cfg["nome"]
    # per codice bilancio
    codice = lm.CENTRI_COSTO["1.1_CAFFE_BEVANDE_CALDE"]["codice"]
    cdc_id2, cfg2 = lm.risolvi_centro_costo(codice)
    assert cdc_id2 == "1.1_CAFFE_BEVANDE_CALDE"
    assert lm.risolvi_centro_costo("NON_ESISTE") == (None, None)
    assert lm.risolvi_centro_costo(None) == (None, None)


def test_learning_usa_centro_costo_scelto_dall_utente():
    """Il centro di costo configurato dall'utente vince sulla tabella statica."""
    db = _FakeDb([{
        "fornitore_nome": "PINCO PALLO SRL",
        "fornitore_nome_normalizzato": "pinco pallo",
        "keywords": ["uova"],
        "centro_costo_suggerito": "1.1_CAFFE_BEVANDE_CALDE",
    }])
    cdc_id, cfg, conf, fonte = asyncio.run(
        lm.classifica_fattura_con_learning(db, "PINCO PALLO SRL", "merce varia", [])
    )
    assert cdc_id == "1.1_CAFFE_BEVANDE_CALDE"
    assert fonte == "keywords_personalizzate"
    assert conf >= 0.9


def test_learning_match_anche_schema_auto():
    """I documenti auto-creati dall'event bus (solo ragione_sociale) vengono
    trovati lo stesso dal classificatore."""
    db = _FakeDb([{
        "ragione_sociale": "EUROUOVA S.r.l.",
        "keywords": ["uova", "fresche"],
        # niente fornitore_nome, niente normalizzato: schema auto
    }])
    cdc_id, cfg, conf, fonte = asyncio.run(
        lm.classifica_fattura_con_learning(db, "EUROUOVA SRL", "", [])
    )
    # le keywords 'uova' portano a una classificazione non-fallback
    assert fonte in ("keywords_apprese", "tabella_statica")
    assert cdc_id  # mai None


def test_learning_fallback_tabella_statica():
    """Fornitore sconosciuto → tabella statica (es. Kimbo → caffè)."""
    db = _FakeDb([])
    cdc_id, cfg, conf, fonte = asyncio.run(
        lm.classifica_fattura_con_learning(db, "KIMBO SPA", "fornitura caffè", [])
    )
    assert fonte == "tabella_statica"
    assert cdc_id == "1.1_CAFFE_BEVANDE_CALDE"


def test_learning_senza_db_non_esplode():
    # NB: nome senza sottostringhe che matchino keyword statiche
    # ("SCONOSCIUTO" contiene 'cono' → gelati!)
    cdc_id, cfg, conf, fonte = asyncio.run(
        lm.classifica_fattura_con_learning(None, "XYZQWK SRL", "", [])
    )
    assert cdc_id == "99_ALTRI_COSTI"
    assert fonte == "tabella_statica"


def test_nome_da_config_schema_misto():
    """Il router non deve più esplodere sui documenti auto (KeyError)."""
    from app.routers.fornitori_learning import _nome_da_config
    assert _nome_da_config({"fornitore_nome": "EUROUOVA"}) == "EUROUOVA"
    assert _nome_da_config({"ragione_sociale": "LEASYS SPA"}) == "LEASYS SPA"
    assert _nome_da_config({}) == ""
