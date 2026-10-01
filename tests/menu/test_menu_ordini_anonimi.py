"""Menu: un ordine anonimo e' sempre del cliente e non pagato; «cassa» e «pagato»
li dichiara solo chi ha la sessione dello staff."""
import asyncio

from app.menu.models.order_models import OrderCreate, OrderItem
from app.menu.routes import order_routes


class _Tabella:
    def __init__(self, righe):
        self.righe = righe

    def insert(self, riga):
        self.righe.append(riga)
        return self

    def execute(self):
        return self


class _Supabase:
    def __init__(self):
        self.righe = []

    def table(self, nome):
        assert nome == "menu_orders"
        return _Tabella(self.righe)


def _payload():
    return OrderCreate(items=[OrderItem(name="Caffe", price="1,20", quantity=1)],
                       source="cassa", paid=True, payment_method="contanti")


def _crea(monkeypatch, esito_token):
    finto = _Supabase()
    monkeypatch.setattr(order_routes, "supabase", finto)

    async def _verifica(authorization):
        if isinstance(esito_token, Exception):
            raise esito_token
        return esito_token

    monkeypatch.setattr(order_routes, "verify_token", _verifica)
    asyncio.run(order_routes.create_order(_payload(), authorization="Bearer x"))
    return finto.righe[0]


def test_anonimo_non_puo_dichiarare_cassa_ne_pagato(monkeypatch):
    from fastapi import HTTPException

    riga = _crea(monkeypatch, HTTPException(status_code=401, detail="Invalid authorization header"))
    assert riga["source"] == "cliente" and riga["paid"] is False


def test_un_guasto_nella_verifica_non_promuove_a_staff(monkeypatch):
    riga = _crea(monkeypatch, RuntimeError("db giu'"))
    assert riga["source"] == "cliente" and riga["paid"] is False


def test_lo_staff_con_sessione_valida_conserva_cassa_e_pagato(monkeypatch):
    riga = _crea(monkeypatch, "titolare")
    assert riga["source"] == "cassa" and riga["paid"] is True
