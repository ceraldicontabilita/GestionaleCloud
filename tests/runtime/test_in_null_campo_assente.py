"""`$in` con None vale anche per il campo assente, come `$eq: None` e Mongo.

`{"ricevuta_pagopa_id": {"$in": [None, ""]}}` («non ancora collegato»)
escludeva le righe che il campo non l'hanno mai avuto: nessuna ricevuta
PagoPA trovava il suo movimento, e il cruscotto non ne contava nessuno."""
from app.services.archivio_documenti_memoria import matches_filter, prepara_filtro


def test_in_con_none_comprende_il_campo_assente():
    filtro = {"collegato": {"$in": [None, ""]}}
    assert matches_filter({"id": 1}, filtro)
    assert matches_filter({"id": 1, "collegato": None}, filtro)
    assert matches_filter({"id": 1, "collegato": ""}, filtro)
    assert not matches_filter({"id": 1, "collegato": "R-1"}, filtro)
    assert matches_filter({"id": 1}, prepara_filtro(filtro))


def test_in_senza_none_non_comprende_il_campo_assente():
    assert not matches_filter({"id": 1}, {"stato": {"$in": ["aperto", "parziale"]}})
    # `$nin` resta speculare: None escluso esclude anche il campo assente
    assert not matches_filter({"id": 1}, {"stato": {"$nin": [None, ""]}})
