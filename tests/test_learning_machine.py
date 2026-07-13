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


def test_fornitore_misto_classifica_dal_contenuto():
    """Amazon marcato MISTO: decide il contenuto della fattura, non il fornitore.
    Un mouse → piccole attrezzature (<516,46 €); contenuto ignoto → Altri costi."""
    db = _FakeDb([{
        "fornitore_nome": "Amazon Business EU S.a.r.l",
        "fornitore_nome_normalizzato": "amazon business eu s.a.r.l, sede secondaria",
        "keywords": [],
        "centro_costo_suggerito": lm.FORNITORE_MISTO,
    }])
    # Fattura con un mouse → 5.3 piccole attrezzature/beni < 516,46
    cdc_id, cfg, conf, fonte = asyncio.run(lm.classifica_fattura_con_learning(
        db, "Amazon Business EU S.a.r.l, Sede Secondaria",
        "", [{"descrizione": "Mouse wireless Logitech M185"}]
    ))
    assert fonte == "contenuto_fattura"
    assert cdc_id == "5.3_PICCOLE_ATTREZZATURE"
    # Fattura dal contenuto indecifrabile → resta Altri costi (da vedere a mano)
    cdc_id2, _, _, fonte2 = asyncio.run(lm.classifica_fattura_con_learning(
        db, "Amazon Business EU S.a.r.l, Sede Secondaria",
        "", [{"descrizione": "XKWZ-9931 QQ"}]
    ))
    assert fonte2 == "contenuto_fattura"
    assert cdc_id2 == "99_ALTRI_COSTI"


def test_nuovi_centri_cucina_e_beni_sotto_516():
    cdc_id, cfg = lm.risolvi_centro_costo("1.8_MATERIE_PRIME_CUCINA")
    assert cfg and cfg["nome"] == "Materie prime cucina"
    # cucina e pasticceria sono centri separati
    cdc_p, cfg_p = lm.risolvi_centro_costo("1.3_MATERIE_PRIME_PASTICCERIA")
    assert cdc_p != cdc_id
    # 5.3 ora è la voce dei beni sotto soglia
    _, cfg53 = lm.risolvi_centro_costo("5.3_PICCOLE_ATTREZZATURE")
    assert "516" in cfg53["nome"]
    # un contenuto cucina classifica su cucina
    cdc, cfgc, conf = lm.classifica_fattura_per_centro_costo(
        "", "", [{"descrizione": "passata di pomodoro e legumi"}])
    assert cdc == "1.8_MATERIE_PRIME_CUCINA"


def test_endpoint_classifica_da_contenuto_end_to_end(monkeypatch):
    """Percorso COMPLETO del bottone '🧠 Classifica dal contenuto XML':
    le fatture con righe chiare si classificano da sole, le ambigue restano."""
    from app.routers import fornitori_learning as router_mod
    from app.database import Database

    fatture = [
        {"_id": 1, "supplier_name": "FORNITORE A", "descrizione": "",
         "linee": [{"descrizione": "Farina 00 sacchi da 25kg e zucchero semolato"}]},
        {"_id": 2, "supplier_name": "FORNITORE B", "descrizione": "",
         "linee": [{"descrizione": "Passata di pomodoro e legumi in scatola"}]},
        {"_id": 3, "supplier_name": "AMAZON EU", "descrizione": "",
         "linee": [{"descrizione": "Mouse wireless e tastiera USB"}]},
        {"_id": 4, "supplier_name": "FORNITORE X", "descrizione": "",
         "linee": [{"descrizione": "XKWZ-9931 QQ rif. 4471"}]},  # ambigua
    ]

    class _Coll:
        def __init__(self, docs):
            self.docs = docs
            self.aggiornate = {}

        def find(self, *a, **k):
            class _Cur:
                def __init__(self, d):
                    self._d = d

                async def to_list(self, n):
                    return self._d[:n]
            return _Cur(self.docs)

        async def update_one(self, q, u, *a, **k):
            self.aggiornate[q["_id"]] = u["$set"]

    class _Db:
        def __init__(self):
            self.invoices = _Coll(fatture)
            self.keywords = _Coll([])

        def __getitem__(self, name):
            return self.invoices if name == "invoices" else self.keywords

    db = _Db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    esito = asyncio.run(router_mod.classifica_da_contenuto(soglia=0.3))

    assert esito["success"] and esito["esaminate"] == 4
    assert esito["classificate"] == 3 and esito["ambigue"] == 1
    assert db.invoices.aggiornate[1]["centro_costo_id"] == "1.3_MATERIE_PRIME_PASTICCERIA"
    assert db.invoices.aggiornate[2]["centro_costo_id"] == "1.8_MATERIE_PRIME_CUCINA"
    assert db.invoices.aggiornate[3]["centro_costo_id"] == "5.3_PICCOLE_ATTREZZATURE"
    assert 4 not in db.invoices.aggiornate  # l'ambigua NON viene toccata


def test_nome_da_config_schema_misto():
    """Il router non deve più esplodere sui documenti auto (KeyError)."""
    from app.routers.fornitori_learning import _nome_da_config
    assert _nome_da_config({"fornitore_nome": "EUROUOVA"}) == "EUROUOVA"
    assert _nome_da_config({"ragione_sociale": "LEASYS SPA"}) == "LEASYS SPA"
    assert _nome_da_config({}) == ""


def test_latte_bar_vs_pasticceria_per_contenuto():
    """Regola utente: latte fresco/intero → Bar (1.1); parzialmente scremato e
    lunga conservazione (UHT) → Pasticceria (1.3). Latte generico → Bar.
    (Fornitore neutro: il nome fornitore entra nello scoring, quindi 'Latteria'
    conterrebbe 'latte' e falserebbe il test.)"""
    def cdc(desc):
        cid, _, _ = lm.classifica_fattura_per_centro_costo("Fornitore Generico Srl", desc)
        return cid
    assert cdc("Latte fresco intero 1L") == "1.1_CAFFE_BEVANDE_CALDE"
    assert cdc("Latte intero") == "1.1_CAFFE_BEVANDE_CALDE"
    assert cdc("Latte") == "1.1_CAFFE_BEVANDE_CALDE"
    assert cdc("Latte parzialmente scremato UHT 6x1L") == "1.3_MATERIE_PRIME_PASTICCERIA"
    assert cdc("Latte a lunga conservazione") == "1.3_MATERIE_PRIME_PASTICCERIA"


def test_panna_bar_vs_pasticceria_per_contenuto():
    """Regola utente (parallela al latte): panna fresca → Bar (1.1);
    UHT/vegetale/lunga conservazione → Pasticceria (1.3); panna generica →
    Pasticceria (materia prima, suo uso prevalente)."""
    def cdc(desc):
        cid, _, _ = lm.classifica_fattura_per_centro_costo("Fornitore Generico Srl", desc)
        return cid
    assert cdc("Panna fresca da montare 1L") == "1.1_CAFFE_BEVANDE_CALDE"
    assert cdc("Panna UHT 1L") == "1.3_MATERIE_PRIME_PASTICCERIA"
    assert cdc("Panna vegetale") == "1.3_MATERIE_PRIME_PASTICCERIA"
    assert cdc("Panna") == "1.3_MATERIE_PRIME_PASTICCERIA"


def test_descrizione_vince_su_nome_fornitore():
    """La descrizione pesa più del nome fornitore: una fattura di 'panna UHT' da
    un fornitore che si chiama 'Latteria …' va alla Pasticceria, non al Bar."""
    cid, cfg, _ = lm.classifica_fattura_per_centro_costo(
        "Latteria Sorrentina Srl", "Panna UHT 1L")
    assert cid == "1.3_MATERIE_PRIME_PASTICCERIA"
    # Il nome fornitore resta un indizio quando la descrizione non decide.
    cid2, _, _ = lm.classifica_fattura_per_centro_costo("Enel Energia SpA", "fornitura periodo")
    assert cid2 == "2.1_ENERGIA_ELETTRICA"


def test_uova_restano_pasticceria():
    def cdc(desc):
        cid, _, _ = lm.classifica_fattura_per_centro_costo("Fornitore Generico", desc)
        return cid
    assert cdc("Uovo pastorizzato 5kg") == "1.3_MATERIE_PRIME_PASTICCERIA"
    assert cdc("Uova fresche") == "1.3_MATERIE_PRIME_PASTICCERIA"


def test_settore_da_centro_dettaglio():
    assert lm.settore_di("1.1_CAFFE_BEVANDE_CALDE") == "CDC-01"
    assert lm.settore_di("1.3_MATERIE_PRIME_PASTICCERIA") == "CDC-02"
    assert lm.settore_di("1.5_GELATI_GRANITE") == "CDC-03"
    assert lm.settore_di("1.8_MATERIE_PRIME_CUCINA") == "CDC-04"
    assert lm.settore_di("4.0_PERSONALE") == "CDC-90"
    assert lm.settore_di("2.1_ENERGIA_ELETTRICA") == "CDC-99"
    assert lm.settore_di(None) == "CDC-99"
    assert lm.settore_di("codice_sconosciuto") == "CDC-99"
