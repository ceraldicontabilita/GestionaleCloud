"""Ponte Lotti -> Menu digitale (app/lotti/servizi/menu_bridge.py + agganci in
app/lotti/routers/ricette.py).

Richiesta del titolare: "quando aggiungo un prodotto in Lotti fai in modo che
lo aggiungi anche in Menu con le stesse immagini e scelgo io se far comparire
nel menu pubblico". Nessuna rete: il client Supabase del Menu e' un finto in
memoria (tabelle + Storage) e l'archivio Lotti e' mongomock.
"""
import asyncio
import io

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from starlette.datastructures import Headers

from app.lotti.servizi import menu_bridge


def run(coro):
    return asyncio.run(coro)


# ---------- client Supabase finto (PostgREST + Storage) ----------

class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, tabelle, nome):
        self.tabelle, self.nome = tabelle, nome
        self.op, self.filtri, self.payload = "select", [], None
        self._order, self._limit = None, None

    def select(self, *_):
        self.op = "select"
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, colonna, valore):
        self.filtri.append((colonna, valore))
        return self

    def order(self, colonna, desc=False):
        self._order = (colonna, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        righe = self.tabelle.setdefault(self.nome, [])
        trovate = [r for r in righe if all(r.get(c) == v for c, v in self.filtri)]
        if self.op == "select":
            if self._order:
                trovate.sort(key=lambda r: r[self._order[0]], reverse=self._order[1])
            if self._limit:
                trovate = trovate[: self._limit]
            return _Res([dict(r) for r in trovate])
        if self.op == "insert":
            nuove = self.payload if isinstance(self.payload, list) else [self.payload]
            righe.extend(dict(r) for r in nuove)
            return _Res(list(nuove))
        if self.op == "update":
            for r in trovate:
                r.update(self.payload)
            return _Res([dict(r) for r in trovate])
        if self.op == "delete":
            for r in trovate:
                righe.remove(r)
            return _Res(trovate)
        raise AssertionError(self.op)


class _Bucket:
    def __init__(self, registro, nome):
        self.registro, self.nome = registro, nome

    def upload(self, percorso, contenuto, opzioni):
        self.registro.append({"bucket": self.nome, "path": percorso, "data": contenuto, "opzioni": opzioni})

    def get_public_url(self, percorso):
        return f"https://storage.test/object/public/{self.nome}/{percorso}"


class _Storage:
    def __init__(self, registro):
        self.registro = registro

    def from_(self, bucket):
        return _Bucket(self.registro, bucket)


class _FakeSupabase:
    def __init__(self):
        self.tabelle = {}
        self.upload = []
        self.storage = _Storage(self.upload)

    def table(self, nome):
        return _Query(self.tabelle, nome)


class _SupabaseRotto:
    """Qualunque accesso esplode: simula il Menu irraggiungibile."""

    def table(self, nome):
        raise ConnectionError("Menu irraggiungibile")

    @property
    def storage(self):
        raise ConnectionError("Menu irraggiungibile")


@pytest.fixture
def ambiente(monkeypatch):
    import app.lotti.routers.ricette as ricette

    monkeypatch.setenv("MENU_SUPABASE_URL", "https://menu.test.supabase.co")
    finto = _FakeSupabase()
    monkeypatch.setattr(menu_bridge, "supabase", finto)
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette, "db", database)
    return ricette, database, finto


def _payload(**extra):
    base = dict(
        nome="Babà al rum",
        reparto="pasticceria",
        prezzo_vendita=3.5,
        descrizione="Babà classico napoletano",
        ingredienti=["Farina", "Latte", "Uova", "Rum"],
        ingredienti_dettaglio=[
            {"nome": "Farina", "quantita": 500, "unita_misura": "g"},
            {"nome": "Latte", "quantita": 200, "unita_misura": "ml"},
            {"nome": "Uova", "quantita": 4, "unita_misura": "pz"},
        ],
    )
    base.update(extra)
    return base


def _file_png(contenuto=b"\x89PNG-finto"):
    return UploadFile(
        file=io.BytesIO(contenuto), filename="foto.png",
        headers=Headers({"content-type": "image/png"}),
    )


# ---------- trasformazioni pure ----------

def test_mappa_allergeni_riduce_ai_14_id_del_menu():
    assert menu_bridge.mappa_allergeni(
        ["Glutine", "Latte", "Uova", "Frutta a guscio", "Anidride solforosa", "Vegano", "glutine"]
    ) == ["gluten", "milk", "eggs", "nuts", "sulphites"]
    assert menu_bridge.mappa_allergeni(None) == []


@pytest.mark.parametrize("prezzo,atteso", [(3.5, "3.50€"), ("2", "2.00€"), (0, None), (None, None), ("", None), ("abc", None)])
def test_prezzo_menu_formato_del_seed(prezzo, atteso):
    assert menu_bridge.prezzo_menu(prezzo) == atteso


def test_percorso_storage_da_mime():
    assert menu_bridge.percorso_storage("ricetta_x_ab12", "image/png") == "lotti/ricetta_x_ab12.png"
    assert menu_bridge.percorso_storage("f", "image/jpeg") == "lotti/f.jpg"
    assert menu_bridge.percorso_storage("f", "image/webp") == "lotti/f.webp"


# ---------- creazione ricetta -> riga Menu ----------

def test_create_ricetta_pubblica_nel_menu_nascosta_per_default(ambiente):
    ricette, database, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload())))

    assert creata["menu_pubblico"] is False
    assert creata["menu_sync"]["esito"] == "pubblicato"
    assert creata["menu_sync"]["lotti_ref"] == f"ricetta:{creata['id']}"

    prodotti = finto.tabelle["menu_products"]
    assert len(prodotti) == 1
    riga = prodotti[0]
    assert riga["lotti_ref"] == f"ricetta:{creata['id']}"
    assert riga["origine"] == "lotti"
    assert riga["visible"] is False
    assert riga["name"] == riga["name_it"] == "Babà al rum"
    assert riga["price"] == "3.50€"
    assert riga["description_it"] == "Babà classico napoletano"
    assert set(riga["allergens"]) == {"gluten", "milk", "eggs"}
    assert riga["id"] >= menu_bridge.ID_MINIMO_LOTTI

    categorie = finto.tabelle["menu_categories"]
    assert [c["name_it"] for c in categorie] == ["Produzione Ceraldi"]
    assert categorie[0]["origine"] == "lotti"
    assert riga["category_id"] == categorie[0]["id"]

    sottocategorie = finto.tabelle["menu_subcategories"]
    assert [s["name_it"] for s in sottocategorie] == ["Pasticceria"]
    assert sottocategorie[0]["category_id"] == categorie[0]["id"]
    assert sottocategorie[0]["origine"] == "lotti"
    assert riga["subcategory_id"] == sottocategorie[0]["id"]

    # Salvata in Lotti con il flag
    salvata = run(database.ricette.find_one({"id": creata["id"]}))
    assert salvata["menu_pubblico"] is False


def test_create_ricetta_menu_pubblico_true_e_visibile(ambiente):
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(menu_pubblico=True, reparto="rosticceria"))))
    assert creata["menu_pubblico"] is True
    assert finto.tabelle["menu_products"][0]["visible"] is True
    assert [s["name_it"] for s in finto.tabelle["menu_subcategories"]] == ["Rosticceria"]


def test_seconda_ricetta_riusa_categoria_e_sottocategoria(ambiente):
    ricette, _, finto = ambiente
    run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Uno"))))
    run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Due"))))
    run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Tre", reparto="bar"))))
    assert len(finto.tabelle["menu_categories"]) == 1
    assert sorted(s["name_it"] for s in finto.tabelle["menu_subcategories"]) == ["Bar", "Pasticceria"]
    ids = [p["id"] for p in finto.tabelle["menu_products"]]
    assert len(set(ids)) == 3


# ---------- foto: stessa immagine su Storage del Menu ----------

def test_upload_foto_copia_immagine_nel_menu(ambiente):
    ricette, database, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload())))
    assert finto.tabelle["menu_products"][0]["image"] is None

    esito = run(ricette.upload_foto(creata["id"], _file_png()))
    foto_id = ricette._foto_id_da_url(esito["foto_url"])
    assert esito["menu_sync"]["esito"] == "aggiornato"

    assert len(finto.upload) == 1
    caricato = finto.upload[0]
    assert caricato["bucket"] == "menu-images"
    assert caricato["path"] == f"lotti/{foto_id}.png"
    assert caricato["data"] == b"\x89PNG-finto"
    assert caricato["opzioni"] == {"content-type": "image/png", "upsert": "true"}

    riga = finto.tabelle["menu_products"][0]
    assert riga["image"] == f"https://storage.test/object/public/menu-images/lotti/{foto_id}.png"
    assert esito["menu_sync"]["image"] == riga["image"]

    # Una modifica successiva NON ricarica la stessa foto
    run(ricette.aggiorna_campo_ricetta(creata["id"], {"note": "nuova nota"}))
    assert len(finto.upload) == 1
    assert finto.tabelle["menu_products"][0]["description_it"] == "Babà classico napoletano"  # le note/procedimento non vanno nel menu

    # Una nuova foto (nuovo foto_id) viene caricata e sostituisce l'immagine
    esito2 = run(ricette.upload_foto(creata["id"], _file_png(b"seconda")))
    foto_id2 = ricette._foto_id_da_url(esito2["foto_url"])
    assert foto_id2 != foto_id
    assert len(finto.upload) == 2
    assert finto.tabelle["menu_products"][0]["image"].endswith(f"/lotti/{foto_id2}.png")


# ---------- scelta del titolare: menu_pubblico -> visible ----------

def test_patch_menu_pubblico_aggiorna_visible(ambiente):
    ricette, database, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload())))
    assert finto.tabelle["menu_products"][0]["visible"] is False

    esito = run(ricette.aggiorna_campo_ricetta(creata["id"], {"menu_pubblico": True}))
    assert esito["aggiornato"] == {"menu_pubblico": True}
    assert esito["menu_sync"]["esito"] == "aggiornato"
    assert esito["menu_sync"]["visible"] is True
    assert len(finto.tabelle["menu_products"]) == 1
    assert finto.tabelle["menu_products"][0]["visible"] is True
    assert run(database.ricette.find_one({"id": creata["id"]}))["menu_pubblico"] is True

    run(ricette.aggiorna_campo_ricetta(creata["id"], {"menu_pubblico": False}))
    assert finto.tabelle["menu_products"][0]["visible"] is False


def test_put_senza_flag_conserva_la_scelta_e_aggiorna_nome_prezzo(ambiente):
    ricette, database, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(menu_pubblico=True))))

    aggiornata = run(ricette.update_ricetta(
        creata["id"], ricette.RicettaCreate(**_payload(nome="Babà grande", prezzo_vendita=4)), _admin={"nome": "Admin"},
    ))
    assert aggiornata["menu_pubblico"] is True
    assert aggiornata["menu_sync"]["esito"] == "aggiornato"
    riga = finto.tabelle["menu_products"][0]
    assert riga["name_it"] == "Babà grande"
    assert riga["price"] == "4.00€"
    assert riga["visible"] is True

    run(ricette.update_ricetta(
        creata["id"], ricette.RicettaCreate(**_payload(menu_pubblico=False)), _admin={"nome": "Admin"},
    ))
    assert finto.tabelle["menu_products"][0]["visible"] is False


def test_delete_ricetta_rimuove_la_riga_menu(ambiente):
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload())))
    esito = run(ricette.delete_ricetta(creata["id"], {"nome": "Admin"}))
    assert esito["menu_sync"] == {"esito": "rimosso", "lotti_ref": f"ricetta:{creata['id']}", "rimossi": 1}
    assert finto.tabelle["menu_products"] == []


# ---------- il ponte non blocca mai Lotti ----------

def test_menu_non_configurato_esito_e_endpoint_200(monkeypatch):
    import app.lotti.routers.ricette as ricette

    monkeypatch.delenv("MENU_SUPABASE_URL", raising=False)
    monkeypatch.setattr(menu_bridge, "supabase", _SupabaseRotto())
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette, "db", database)

    app = FastAPI()
    app.include_router(ricette.router, prefix="/api")
    client = TestClient(app)
    risposta = client.post("/api/ricette", json=_payload())
    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    assert corpo["menu_sync"]["esito"] == "non_configurato"
    assert corpo["menu_pubblico"] is False
    assert run(database.ricette.count_documents({})) == 1

    assert run(menu_bridge.rimuovi_prodotto_dal_menu("ricetta:x")) == {"esito": "non_configurato", "lotti_ref": "ricetta:x"}


def test_menu_irraggiungibile_non_blocca_la_ricetta(monkeypatch):
    import app.lotti.routers.ricette as ricette

    monkeypatch.setenv("MENU_SUPABASE_URL", "https://menu.test.supabase.co")
    monkeypatch.setattr(menu_bridge, "supabase", _SupabaseRotto())
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette, "db", database)

    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload())))
    assert creata["menu_sync"]["esito"] == "errore"
    assert "irraggiungibile" in creata["menu_sync"]["errore"]
    assert run(database.ricette.count_documents({"id": creata["id"]})) == 1

    esito = run(ricette.delete_ricetta(creata["id"], {"nome": "Admin"}))
    assert esito["menu_sync"]["esito"] == "errore"
    assert run(database.ricette.count_documents({})) == 0
