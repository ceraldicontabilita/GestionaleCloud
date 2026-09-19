"""Alert allergeni mancanti ed esclusioni dalla verifica
(app/menu/routes/allergeni_routes.py).

19/09/2026: "Collega a una ricetta" e' stato tolto dal Menu (la strada
ricetta -> prodotto la fa il ponte di Lotti) e al suo posto si esclude dalla
verifica chi allergeni da dichiarare non ne ha (whisky, distillati, bibite).

Il test che conta davvero e' l'ultimo: l'esclusione deve sopravvivere a una
sincronizzazione Qromo completa. La sync fa DELETE + INSERT di menu_products
con ``origine IS NULL`` e reinserisce solo le colonne di
``trasforma_catalogo``, quindi un flag scritto dentro menu_products sarebbe
perso. E' il motivo per cui le esclusioni stanno in una tabella separata,
chiavata sugli id Qromo che restano stabili tra un sync e l'altro.

Client Supabase sostituito da un finto in memoria, nessuna rete.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.menu import qromo_sync as qs
from app.menu.routes import allergeni_routes as ar
from tests.menu.test_menu_qromo_sync import HTML_QROMO


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
    assert esito["senza_allergeni"] == 3
    assert esito["esclusi"] == 0
    assert [p["name_it"] for p in esito["prodotti"]] == ["Brioche", "Lagavulin 16", "Talisker 10"]
    whisky = esito["prodotti"][1]
    assert whisky["categoria_nome"] == "Cantina"
    assert whisky["sottocategoria_nome"] == "Whisky"


# ---------- esclusione di un prodotto ----------

def test_prodotto_escluso_sparisce_dai_mancanti(tabelle):
    payload = ar.NuovaEsclusione(tipo="prodotto", riferimento_id=100, motivo="  ")
    esito = _run(ar.crea_esclusione(payload, username="admin"))
    assert esito["esito"] == "creata"
    # motivo facoltativo: i soli spazi non diventano un motivo
    assert esito["esclusione"]["motivo"] is None

    esito_mancanti = _run(ar.prodotti_senza_allergeni(_username="admin"))
    assert "Brioche" not in [p["name_it"] for p in esito_mancanti["prodotti"]]
    assert esito_mancanti["senza_allergeni"] == 2
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
    assert _nomi_mancanti() == ["Brioche", "Lagavulin 16", "Talisker 10"]
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


# ---------- il test che conta: la sync Qromo non deve cancellarle ----------

class _SorgenteFinta:
    def __init__(self, _sottodominio):
        pass

    async def chiudi(self):
        pass

    async def catalogo(self):
        return qs.catalogo_da_html(HTML_QROMO)


def test_l_esclusione_sopravvive_a_una_sync_qromo_completa(tabelle, monkeypatch):
    """Il prodotto 100 esiste sia prima sia dopo la sync (l'id Qromo e'
    stabile): la sync ricrea la riga senza allergeni, ma l'esclusione sta in
    un'altra tabella e resta, quindi il prodotto non ritorna nell'alert."""
    # HTML_QROMO produce il prodotto 100 "Espresso" nella sottocategoria 10
    # della categoria 1: gli stessi id della fixture.
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="prodotto", riferimento_id=100, motivo="Solo caffe'"),
        username="admin"))
    _run(ar.crea_esclusione(
        ar.NuovaEsclusione(tipo="sottocategoria", riferimento_id=20, motivo="Distillati"),
        username="admin"))
    assert _nomi_mancanti() == []

    # Sync Qromo vera e propria sulle stesse tabelle in memoria
    monkeypatch.setattr(qs, "supabase", ar.supabase)
    monkeypatch.setattr(qs, "SorgenteQromo", _SorgenteFinta)
    _run(qs.sincronizza(sottodominio="test", dry_run=False))

    # La sync ha davvero rifatto menu_products da zero
    prodotti = tabelle["menu_products"]
    assert [p["id"] for p in prodotti] == [100]
    assert prodotti[0]["name_it"] == "Espresso"
    assert prodotti[0]["allergens"] == ["gluten"]
    # ...e non ha toccato la tabella delle esclusioni
    assert len(tabelle["menu_allergeni_esclusioni"]) == 2

    # Il prodotto 100 torna con gli allergeni di Qromo, quindi non e'
    # mancante; ne aggiungo uno senza allergeni con lo stesso id per provare
    # che, se lo fosse, l'esclusione reggerebbe comunque.
    prodotti[0]["allergens"] = []
    assert _nomi_mancanti() == []
    esito = _run(ar.prodotti_senza_allergeni(_username="admin"))
    assert esito["esclusi"] == 1
