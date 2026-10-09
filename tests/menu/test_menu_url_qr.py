"""QR del menu clienti: una sola fonte, l'indirizzo pubblico salvato.

Convivevano due sistemi: la pagina admin costruiva il QR dal dominio da cui si
apriva l'amministrazione, mentre `menu_qrcode_config.menu_url` (con il suo
generatore PNG lato server) non lo leggeva nessuno. Resta il secondo come dato,
il QR si disegna nel browser da quel valore.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.menu.models.qrcode_models import MenuUrlUpdate
from app.menu.routes import qrcode_routes as module


class _Query:
    def __init__(self, tabella, op, dati=None):
        self.tabella, self.op, self.dati, self.filtri = tabella, op, dati, {}

    def select(self, *_a):
        return self

    def eq(self, campo, valore):
        self.filtri[campo] = valore
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        righe = self.tabella.righe
        if self.op == "select":
            data = [dict(r) for r in righe if all(r.get(k) == v for k, v in self.filtri.items())]
        elif self.op == "update":
            data = []
            for r in righe:
                if all(r.get(k) == v for k, v in self.filtri.items()):
                    r.update(self.dati)
                    data.append(dict(r))
        else:
            righe.append(dict(self.dati))
            data = [dict(self.dati)]
        return type("Esito", (), {"data": data})()


class _Tabella:
    def __init__(self, righe):
        self.righe = righe

    def select(self, *_a):
        return _Query(self, "select")

    def update(self, dati):
        return _Query(self, "update", dati)

    def insert(self, dati):
        return _Query(self, "insert", dati)


class _Supabase:
    def __init__(self, righe):
        self.tabella = _Tabella(righe)

    def table(self, nome):
        assert nome == "menu_qrcode_config"
        return self.tabella


RIGA = {
    "id": "qrcode_config",
    "menu_url": "https://impresasemplice.online/menu/",
    "wifi": {"ssid": "rete", "password": "segreto-di-prova", "security": "WPA"},
    "updated_at": "2026-09-05T14:33:57",
}


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("ingresso,atteso", [
    ("https://impresasemplice.online/menu/", "https://impresasemplice.online/menu/"),
    ("  https://gestionalecloud.onrender.com/menu  ", "https://gestionalecloud.onrender.com/menu/"),
])
def test_indirizzo_canonico(ingresso, atteso):
    assert module.normalizza_menu_url(ingresso) == atteso


@pytest.mark.parametrize("ingresso", [
    "", "#", "http://impresasemplice.online/menu/", "https:///menu/",
    "https://impresasemplice.online/", "https://impresasemplice.online/menu/admin",
    "https://impresasemplice.online/menu/?tavolo=3", "javascript:alert(1)",
])
def test_indirizzo_non_valido_rifiutato(ingresso):
    with pytest.raises(HTTPException) as exc:
        module.normalizza_menu_url(ingresso)
    assert exc.value.status_code == 400


def test_lettura_pubblica_solo_indirizzo(monkeypatch):
    monkeypatch.setattr(module, "supabase", _Supabase([dict(RIGA)]))
    esito = run(module.leggi_menu_url())
    assert esito["url"] == "https://impresasemplice.online/menu/"
    assert "wifi" not in esito and "segreto-di-prova" not in repr(esito)


def test_senza_riga_nessun_indirizzo_inventato(monkeypatch):
    righe = []
    monkeypatch.setattr(module, "supabase", _Supabase(righe))
    assert run(module.leggi_menu_url())["url"] is None
    # La lettura non scrive: prima creava una riga con un ripiego inventato.
    assert righe == []


def test_aggiornamento_conserva_il_wifi(monkeypatch):
    righe = [dict(RIGA)]
    monkeypatch.setattr(module, "supabase", _Supabase(righe))
    esito = run(module.aggiorna_menu_url(MenuUrlUpdate(url="https://gestionalecloud.onrender.com/menu"), username="admin"))
    assert esito["url"] == "https://gestionalecloud.onrender.com/menu/"
    assert righe[0]["menu_url"] == "https://gestionalecloud.onrender.com/menu/"
    assert righe[0]["wifi"]["password"] == "segreto-di-prova"
    assert righe[0]["updated_by"] == "admin"


def test_aggiornamento_senza_riga_la_crea(monkeypatch):
    righe = []
    monkeypatch.setattr(module, "supabase", _Supabase(righe))
    run(module.aggiorna_menu_url(MenuUrlUpdate(url="https://impresasemplice.online/menu/"), username="admin"))
    assert righe[0]["id"] == "qrcode_config"
    assert righe[0]["menu_url"] == "https://impresasemplice.online/menu/"


def test_scrittura_solo_per_amministratore():
    from fastapi.routing import APIRoute

    rotte = {(r.path, tuple(sorted(r.methods))): r for r in module.router.routes if isinstance(r, APIRoute)}
    put = rotte[("/api/qrcode/menu-url", ("PUT",))]
    assert any(d.call is module.verify_token for d in put.dependant.dependencies)


def test_il_secondo_sistema_non_esiste_piu():
    percorsi = {getattr(r, "path", "") for r in module.router.routes}
    assert "/api/qrcode/config" not in percorsi
    assert "/api/qrcode/generate/menu" not in percorsi
