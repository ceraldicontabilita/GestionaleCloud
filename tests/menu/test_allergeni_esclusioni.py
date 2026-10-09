"""Alert allergeni mancanti ed esclusioni dalla verifica
(app/menu/routes/allergeni_routes.py).

19/09/2026: "Collega a una ricetta" e' stato tolto dal Menu (la strada
ricetta -> prodotto la fa il ponte di Lotti) e al suo posto si esclude dalla
verifica chi allergeni da dichiarare non ne ha (whisky, distillati, bibite).

Il test che conta davvero e' l'ultimo: l'esclusione deve sopravvivere se la riga
del prodotto viene ricreata (stesso id), perche' sta in una tabella separata e
non in una colonna di menu_products.

Client Supabase sostituito da un finto in memoria, nessuna rete.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.menu.routes import allergeni_routes as ar


def _run(coro):
    return asyncio.run(coro)


class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    """Il minimo di PostgREST usato dai due moduli: select/insert/update/
    delete con filtri eq e il filtro ``is_`` della sync."""

    def __init__(self, tabelle, nome):
        self.tabelle, self.nome = tabelle, nome
        self.op, self.filtri, self.payload = "select", [], None
        self._is_null = None

    def select(self, *_):
        return self

    def eq(self, colonna, valore):
        self.filtri.append((colonna, valore))
        return self

    def is_(self, colonna, valore):
        assert valore == "null"
        self._is_null = colonna
        return self

    def insert(self, righe):
        self.op = "insert"
        self.payload = list(righe) if isinstance(righe, list) else [righe]
        return self

    def update(self, riga):
        self.op, self.payload = "update", riga
        return self

    def delete(self):
        self.op = "delete"
        return self

    def _corrispondono(self, riga):
        if not all(riga.get(c) == v for c, v in self.filtri):
            return False
        if self._is_null is not None and riga.get(self._is_null) is not None:
            return False
        return True

    def execute(self):
        righe = self.tabelle.setdefault(self.nome, [])
        if self.op == "insert":
            righe.extend(dict(r) for r in self.payload)
            return _Res([dict(r) for r in self.payload])
        trovate = [r for r in righe if self._corrispondono(r)]
        if self.op == "update":
            for r in trovate:
                r.update(self.payload)
            return _Res([dict(r) for r in trovate])
        if self.op == "delete":
            self.tabelle[self.nome] = [r for r in righe if not self._corrispondono(r)]
            return _Res([dict(r) for r in trovate])
        return _Res([dict(r) for r in trovate])


class _FakeSupabase:
    def __init__(self, tabelle):
        self.tabelle = tabelle

    def table(self, nome):
        return _Query(self.tabelle, nome)


def _prodotto(id_, nome, categoria=1, sottocategoria=10, allergens=None):
    return {
        "id": id_, "name_it": nome, "name": nome, "description_it": None,
        "category_id": categoria, "subcategory_id": sottocategoria,
        "allergens": allergens or [], "visible": True, "origine": None,
    }


@pytest.fixture
def tabelle(monkeypatch):
    dati = {
        "menu_categories": [
            {"id": 1, "name": "Bar", "name_it": "Bar", "origine": None},
            {"id": 2, "name": "Cellar", "name_it": "Cantina", "origine": None},
        ],
        "menu_subcategories": [
            {"id": 10, "category_id": 1, "name": "Coffee", "name_it": "Caffetteria", "origine": None},
            {"id": 20, "category_id": 2, "name": "Whisky", "name_it": "Whisky", "origine": None},
        ],
        "menu_products": [
            _prodotto(100, "Brioche"),
            _prodotto(101, "Cappuccino", allergens=["milk"]),
            _prodotto(200, "Lagavulin 16", categoria=2, sottocategoria=20),
            _prodotto(201, "Talisker 10", categoria=2, sottocategoria=20),
        ],
        "menu_allergeni_esclusioni": [],
    }
    monkeypatch.setattr(ar, "supabase", _FakeSupabase(dati))
    return dati


def _nomi_mancanti():
    return [p["name_it"] for p in _run(ar.prodotti_senza_allergeni(_username="admin"))["prodotti"]]


# ---------- elenco ----------

def test_mancanti_elenca_solo_chi_non_ha_allergeni_con_il_suo_reparto(tabelle):
    esito = _run(ar.prodotti_senza_allergeni(_username="admin"))
    assert esito["totale_prodotti"] == 4
    assert esito["senza_allergeni"] == 1
    assert esito["esclusi"] == 0
    assert [p["name_it"] for p in esito["prodotti"]] == ["Brioche"]
    assert esito["bevande_fuori_lista"] == 2
    assert esito["prodotti"][0]["sottocategoria_nome"] == "Caffetteria"


# ---------- esclusione di un prodotto ----------

def test_prodotto_escluso_sparisce_dai_mancanti(tabelle):
    payload = ar.NuovaEsclusione(tipo="prodotto", riferimento_id=100, motivo="  ")
    esito = _run(ar.crea_esclusione(payload, username="admin"))
    assert esito["esito"] == "creata"
    # motivo facoltativo: i soli spazi non diventano un motivo
    assert esito["esclusione"]["motivo"] is None

    esito_mancanti = _run(ar.prodotti_senza_allergeni(_username="admin"))
    assert "Brioche" not in [p["name_it"] for p in esito_mancanti["prodotti"]]
    assert esito_mancanti["senza_allergeni"] == 0
    assert esito_mancanti["esclusi"] == 1


def test_escludere_due_volte_aggiorna_il_motivo_senza_duplicare(tabelle):
    for motivo in ("Distillato", "Distillato o liquore"):
        _run(ar.crea_esclusione(
            ar.NuovaEsclusione(tipo="prodotto", riferimento_id=200, motivo=motivo),
            username="admin",
        ))
    righe = tabelle["menu_allergeni_esclusioni"]
    assert len(righe) == 1
    assert righe[0]["motivo"] == "Distillato o liquore"


def test_escludere_un_prodotto_inesistente_da_404(tabelle):
    with pytest.raises(HTTPException) as err:
        _run(ar.crea_esclusione(
            ar.NuovaEsclusione(tipo="prodotto", riferimento_id=999), username="admin"))
    assert err.value.status_code == 404


# ---------- esclusione di un reparto ----------

def test_sottocategoria_esclusa_fa_sparire_tutti_i_suoi_prodotti(tabelle):
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="sottocategoria", riferimento_id=20,
                           motivo="Distillati: nessuno dei 14 allergeni UE"),
        username="admin",
    ))
    esito = _run(ar.prodotti_senza_allergeni(_username="admin"))
    assert [p["name_it"] for p in esito["prodotti"]] == ["Brioche"]
    assert esito["esclusi"] == 2


def test_categoria_esclusa_fa_sparire_tutti_i_suoi_prodotti(tabelle):
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="categoria", riferimento_id=2), username="admin"))
    assert _nomi_mancanti() == ["Brioche"]


# ---------- revoca ----------

def test_revocare_l_esclusione_li_fa_ricomparire(tabelle):
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="categoria", riferimento_id=2), username="admin"))
    assert _nomi_mancanti() == ["Brioche"]

    esito = _run(ar.revoca_esclusione(tipo="categoria", riferimento_id=2, _username="admin"))
    assert esito["success"] is True
    assert _nomi_mancanti() == ["Brioche"]  # i liquori restano fuori dalla lista di lavoro
    assert tabelle["menu_allergeni_esclusioni"] == []


def test_revocare_un_esclusione_inesistente_da_404(tabelle):
    with pytest.raises(HTTPException) as err:
        _run(ar.revoca_esclusione(tipo="prodotto", riferimento_id=100, _username="admin"))
    assert err.value.status_code == 404


def test_elenco_esclusioni_porta_il_nome_di_cosa_e_escluso(tabelle):
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="sottocategoria", riferimento_id=20, motivo="Distillati"),
        username="admin"))
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="prodotto", riferimento_id=100), username="admin"))

    esito = _run(ar.elenco_esclusioni(_username="admin"))
    assert esito["totale"] == 2
    per_tipo = {v["tipo"]: v for v in esito["esclusioni"]}
    assert per_tipo["prodotto"]["nome"] == "Brioche"
    assert per_tipo["sottocategoria"]["nome"] == "Whisky"
    assert per_tipo["sottocategoria"]["motivo"] == "Distillati"
    assert per_tipo["prodotto"]["creato_da"] == "admin"


# ---------- il test che conta: la riga ricreata non perde l'esclusione ----------

def test_l_esclusione_sopravvive_se_il_prodotto_viene_ricreato(tabelle):
    """Il prodotto 100 viene ricreato con lo stesso id e senza allergeni: l'esclusione
    sta in un'altra tabella e resta, quindi il prodotto non ritorna nell'alert."""
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="prodotto", riferimento_id=100, motivo="Solo caffe'"),
        username="admin"))
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="sottocategoria", riferimento_id=20, motivo="Distillati"),
        username="admin"))
    assert _nomi_mancanti() == []

    prodotti = tabelle["menu_products"]
    ricreato = dict(next(p for p in prodotti if p["id"] == 100), allergens=[])
    prodotti[:] = [p for p in prodotti if p["id"] != 100] + [ricreato]
    assert len(tabelle["menu_allergeni_esclusioni"]) == 2
    assert _nomi_mancanti() == []
    esito = _run(ar.prodotti_senza_allergeni(_username="admin"))
    assert esito["esclusi"] >= 1
