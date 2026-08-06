"""A6 — Copertura cespiti e chiusura esercizio (scrivono stato contabile).

Test di caratterizzazione della logica fiscale:
- classify_asset: esclusioni, keyword→categoria, fallback prezzo ≥ 2000€
- calcolo ammortamenti: primo anno quota dimezzata (prassi fiscale), anni
  successivi quota piena, cap al valore residuo, skip anni già ammortizzati
- verifica preliminare chiusura: fatture non contabilizzate = problema bloccante
- esegui chiusura: conferma obbligatoria + guardia doppia chiusura (409)
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers import cespiti as cespiti_mod
from app.routers import chiusura_esercizio as chiusura_mod
from app.routers.cespiti import classify_asset


# ---------- fake db minimale ----------

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def skip(self, n):
        return self

    def limit(self, n):
        return self

    async def to_list(self, n=None):
        return list(self._docs)


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.inserted = []

    def find(self, query=None, projection=None):
        return _Cursor(self.docs)

    async def find_one(self, query=None, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in (query or {}).items()
                   if not isinstance(v, dict)):
                return d
        return None

    async def count_documents(self, query=None):
        return len(self.docs)

    def aggregate(self, pipeline):
        return _Cursor(self.docs)

    async def insert_one(self, doc):
        self.inserted.append(doc)
        self.docs.append(doc)


class _Db:
    def __init__(self, colls):
        self._colls = colls

    def __getitem__(self, name):
        return self._colls.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


async def _async_value(value):
    return value


def _patch_db(monkeypatch, module, colls):
    db = _Db(colls)
    monkeypatch.setattr(module.Database, "get_db", staticmethod(lambda: db))
    return db


# ---------- classify_asset ----------

def test_classify_asset_keyword_categoria():
    assert classify_asset("Forno elettrico ventilato", 3500) == "forni"
    assert classify_asset("Abbattitore di temperatura", 4000) == "frigoriferi"
    assert classify_asset("Notebook per ufficio", 900) == "macchine_ufficio"


def test_classify_asset_esclusioni_vincono():
    # keyword di categoria presente ma il bene è escluso (consumo/servizio)
    assert classify_asset("Noleggio forno a piastra", 5000) is None
    assert classify_asset("Caffè in grani Kimbo", 2500) is None


def test_classify_asset_fallback_prezzo():
    # nessuna keyword primaria: sopra 2000€ scatta il fallback attrezzature
    assert classify_asset("Cappa aspirante inox", 2500) == "attrezzature"
    assert classify_asset("Cappa aspirante inox", 500) is None
    assert classify_asset("Merce varia", 9999) is None


def test_coefficienti_gruppo_xix_ufficiali():
    categorie = cespiti_mod.CATEGORIE_CESPITI
    assert categorie["mobili_arredi"]["coefficiente"] == 10
    assert categorie["attrezzature"]["coefficiente"] == 25
    assert categorie["impianti_generici"]["coefficiente"] == 8
    assert categorie["impianti_cucina"]["coefficiente"] == 12
    assert categorie["macchine_ufficio"]["coefficiente"] == 20


def test_calcolo_non_supera_massimo_fiscale_categoria(monkeypatch):
    cespite = _cespite(anno_acquisto=2025, coeff=12)
    cespite["categoria"] = "mobili_arredi"  # massimo ufficiale 10%
    _patch_db(monkeypatch, cespiti_mod, {"cespiti": _Coll([cespite])})

    result = _run(cespiti_mod.calcola_ammortamenti_anno(2025))

    assert result["ammortamenti"][0]["coefficiente_applicato"] == 10
    assert result["ammortamenti"][0]["quota_anno"] == 50.0


def test_bene_immateriale_non_applica_dimezzamento_articolo_102(monkeypatch):
    cespite = _cespite(anno_acquisto=2025, valore=3000.0, coeff=33.33)
    cespite["categoria"] = "software"
    _patch_db(monkeypatch, cespiti_mod, {"cespiti": _Coll([cespite])})

    result = _run(cespiti_mod.calcola_ammortamenti_anno(2025))

    assert result["ammortamenti"][0]["quota_anno"] == 999.9


# ---------- calcolo ammortamenti ----------

def _cespite(anno_acquisto=2025, valore=1000.0, coeff=20, fondo=0.0, piano=None):
    return {
        "id": "c1", "descrizione": "Computer", "categoria": "macchine_ufficio",
        "stato": "attivo", "ammortamento_completato": False,
        "valore_acquisto": valore, "coefficiente_ammortamento": coeff,
        "fondo_ammortamento": fondo, "anno_acquisto": anno_acquisto,
        "data_entrata_funzione": f"{anno_acquisto}-01-01",
        "piano_ammortamento": piano or [],
    }


def test_ammortamento_primo_anno_dimezzato(monkeypatch):
    _patch_db(monkeypatch, cespiti_mod, {"cespiti": _Coll([_cespite(anno_acquisto=2025)])})
    r = _run(cespiti_mod.calcola_ammortamenti_anno(2025))
    assert r["num_cespiti"] == 1
    # 1000 * 20% = 200 → primo anno dimezzato = 100
    assert r["ammortamenti"][0]["quota_anno"] == 100.0
    assert r["ammortamenti"][0]["primo_anno"] is True


def test_ammortamento_anni_successivi_quota_piena(monkeypatch):
    _patch_db(monkeypatch, cespiti_mod,
              {"cespiti": _Coll([_cespite(anno_acquisto=2024, fondo=100.0)])})
    r = _run(cespiti_mod.calcola_ammortamenti_anno(2026))
    assert r["ammortamenti"][0]["quota_anno"] == 200.0
    assert r["ammortamenti"][0]["primo_anno"] is False


def test_ammortamento_cap_al_residuo(monkeypatch):
    # fondo 950 su 1000: la quota piena (200) va limitata al residuo (50)
    _patch_db(monkeypatch, cespiti_mod,
              {"cespiti": _Coll([_cespite(anno_acquisto=2023, fondo=950.0)])})
    r = _run(cespiti_mod.calcola_ammortamenti_anno(2026))
    assert r["ammortamenti"][0]["quota_anno"] == 50.0
    assert r["ammortamenti"][0]["completato"] is True


def test_ammortamento_skip_anno_gia_registrato(monkeypatch):
    _patch_db(monkeypatch, cespiti_mod,
              {"cespiti": _Coll([_cespite(piano=[{"anno": 2026, "quota": 200.0}])])})
    r = _run(cespiti_mod.calcola_ammortamenti_anno(2026))
    assert r["num_cespiti"] == 0
    assert r["totale_ammortamenti"] == 0


# ---------- chiusura esercizio ----------

class _CollCount(_Coll):
    """count_documents parametrico per query (chiavi ordinate)."""
    def __init__(self, count_map=None, default=0):
        super().__init__([])
        self.count_map = count_map or {}
        self.default = default

    async def count_documents(self, query=None):
        chiave = tuple(sorted((query or {}).keys()))
        return self.count_map.get(chiave, self.default)


def _registro(*, fatture=0, corrispettivi=0, scritture=10, quadratura=True):
    return {
        "fonte": "movimenti_contabili",
        "quadratura": quadratura,
        "totali": {"dare": 100.0, "avere": 100.0, "sbilancio": 0.0},
        "qualita_registro": {
            "registro_valido": quadratura,
            "scritture_sbilanciate": 0 if quadratura else 1,
            "scritture_senza_righe": 0,
            "righe_non_numeriche": 0,
            "righe_senza_conto": 0,
        },
        "completezza_registro": {
            "scritture_registrate": scritture,
            "fatture_da_registrare": fatture,
            "corrispettivi_da_registrare": corrispettivi,
            "documenti_da_registrare": fatture + corrispettivi,
            "completo": fatture == 0 and corrispettivi == 0 and quadratura,
        },
        "conti": [],
    }


def test_verifica_preliminare_fatture_non_contabilizzate_bloccano(monkeypatch):
    colls = {
        "invoices": _CollCount(default=3),   # 3 fatture non contabilizzate
        "corrispettivi": _Coll([]),
        "cedolini": _CollCount(default=1),
        "prima_nota_salari": _CollCount(default=1),
        "tfr_accantonamenti": _Coll([{"anno": 2026}]),
        "cespiti": _CollCount(default=0),
        "estratto_conto_movimenti": _CollCount(default=10),
    }
    _patch_db(monkeypatch, chiusura_mod, colls)
    monkeypatch.setattr(
        chiusura_mod, "_bilancio_verifica_da_registro",
        lambda db, anno, dettaglio: _async_value(_registro(fatture=3)),
    )
    r = _run(chiusura_mod.verifica_preliminare_chiusura(2025))
    assert r["pronto_per_chiusura"] is False
    assert any(p["tipo"] == "fatture_non_contabilizzate" for p in r["problemi_bloccanti"])
    assert r["step_successivo"] == "risolvere_problemi"


def test_verifica_preliminare_tutto_ok(monkeypatch):
    corrisp = [{"_id": f"{m:02d}"} for m in range(1, 13)]  # 12 mesi registrati
    colls = {
        "invoices": _CollCount(default=0),
        "corrispettivi": _Coll(corrisp),
        "cedolini": _CollCount(default=12),
        "prima_nota_salari": _CollCount(default=12),
        "tfr_accantonamenti": _Coll([{"anno": 2025}]),
        "cespiti": _CollCount(default=0),
        "estratto_conto_movimenti": _CollCount(count_map={
            ("data", "status"): 100,
            ("data", "riconciliato", "status"): 0,
        }),
    }
    _patch_db(monkeypatch, chiusura_mod, colls)
    monkeypatch.setattr(
        chiusura_mod, "_bilancio_verifica_da_registro",
        lambda db, anno, dettaglio: _async_value(_registro()),
    )
    r = _run(chiusura_mod.verifica_preliminare_chiusura(2025))
    assert r["pronto_per_chiusura"] is True
    assert r["problemi_bloccanti"] == []
    assert r["step_successivo"] == "bilancino_verifica"


def test_esegui_chiusura_richiede_conferma(monkeypatch):
    _patch_db(monkeypatch, chiusura_mod, {})
    with pytest.raises(HTTPException) as exc:
        _run(chiusura_mod.esegui_chiusura_esercizio(
            chiusura_mod.ChiusuraEsercizioInput(anno=2026, conferma_scritture=False)))
    assert exc.value.status_code == 400


def test_esegui_chiusura_guardia_doppia_chiusura(monkeypatch):
    """A6: senza guardia, la seconda chiusura duplicherebbe il movimento
    di risultato d'esercizio."""
    colls = {"chiusure_esercizio": _Coll([
        {"id": "ch-1", "anno": 2026, "created_at": "2027-01-05T10:00:00"}
    ])}
    _patch_db(monkeypatch, chiusura_mod, colls)
    with pytest.raises(HTTPException) as exc:
        _run(chiusura_mod.esegui_chiusura_esercizio(
            chiusura_mod.ChiusuraEsercizioInput(
                anno=2026,
                conferma_scritture=True,
                conferma_quadrature=True,
                conferma_testo="CHIUDI 2026",
            )))
    assert exc.value.status_code == 409
    assert "già chiuso" in exc.value.detail


def test_bilancino_non_inventa_risultato_con_registro_incompleto(monkeypatch):
    _patch_db(monkeypatch, chiusura_mod, {})
    monkeypatch.setattr(
        chiusura_mod, "_bilancio_verifica_da_registro",
        lambda db, anno, dettaglio: _async_value(_registro(fatture=12)),
    )

    r = _run(chiusura_mod.get_bilancino_verifica(2025))

    assert r["disponibile"] is False
    assert r["bilancino"] is None
    assert r["registro"]["completezza"]["fatture_da_registrare"] == 12


def test_bilancino_deriva_solo_dai_conti_economici_del_registro(monkeypatch):
    _patch_db(monkeypatch, chiusura_mod, {})
    registro = _registro()
    registro["conti"] = [
        {"codice": "04.01.02", "nome": "Ricavi", "tipo": "ricavo", "dare": 10, "avere": 1010},
        {"codice": "05.01.01", "nome": "Acquisti", "tipo": "costo", "dare": 600, "avere": 25},
        {"codice": "01.01.02", "nome": "Banca", "tipo": "attivo", "dare": 400, "avere": 0},
    ]
    monkeypatch.setattr(
        chiusura_mod, "_bilancio_verifica_da_registro",
        lambda db, anno, dettaglio: _async_value(registro),
    )

    r = _run(chiusura_mod.get_bilancino_verifica(2025))

    assert r["disponibile"] is True
    assert r["bilancino"]["ricavi"]["totale"] == 1000
    assert r["bilancino"]["costi"]["totale"] == 575
    assert r["bilancino"]["risultato"]["utile_perdita"] == 425


def test_scrittura_chiusura_generata_e_quadrata(monkeypatch):
    colls = {"chiusure_esercizio": _Coll([])}
    _patch_db(monkeypatch, chiusura_mod, colls)
    monkeypatch.setattr(
        chiusura_mod, "verifica_preliminare_chiusura",
        lambda anno: _async_value({"pronto_per_chiusura": True, "problemi_bloccanti": []}),
    )
    bilancino = {
        "disponibile": True,
        "fonte": "movimenti_contabili",
        "registro": {"quadratura": True},
        "bilancino": {
            "ricavi": {"totale": 1000, "conti": [
                {"codice": "04.01.02", "nome": "Ricavi", "tipo": "ricavo", "dare": 0, "avere": 1000},
            ]},
            "costi": {"totale": 600, "conti": [
                {"codice": "05.01.01", "nome": "Acquisti", "tipo": "costo", "dare": 600, "avere": 0},
            ]},
            "risultato": {"utile_perdita": 400, "tipo": "utile", "margine_percentuale": 40},
        },
    }
    monkeypatch.setattr(
        chiusura_mod, "get_bilancino_verifica",
        lambda anno: _async_value(bilancino),
    )
    cattura = {}

    async def registra(db, movimento, righe, chiave):
        cattura["righe"] = righe
        cattura["chiave"] = chiave
        return {"id": "mov-chiusura", "gia_presente": False}

    monkeypatch.setattr(chiusura_mod, "registra_scrittura_semplice", registra)
    r = _run(chiusura_mod.esegui_chiusura_esercizio(
        chiusura_mod.ChiusuraEsercizioInput(
            anno=2025,
            conferma_scritture=True,
            conferma_quadrature=True,
            conferma_testo="CHIUDI 2025",
        )
    ))

    assert r["movimento_contabile_id"] == "mov-chiusura"
    assert sum(x["dare"] for x in cattura["righe"]) == sum(x["avere"] for x in cattura["righe"])
    assert cattura["chiave"] == {"tipo": "chiusura_esercizio", "anno": 2025}
    assert any(x["conto_codice"] == "03.03.01" and x["avere"] == 400 for x in cattura["righe"])
