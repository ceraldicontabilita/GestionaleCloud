import asyncio

from app.routers import scadenze


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return list(self.rows)


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, _query, _projection):
        return _Cursor(self.rows)


def test_scadenze_restituisce_la_pagina_richiesta_e_il_totale_reale(monkeypatch):
    rows = [
        {
            "id": f"custom-{indice}",
            "data_scadenza": f"2026-09-0{indice + 1}",
            "descrizione": f"Scadenza {indice}",
            "completata": False,
        }
        for indice in range(3)
    ]
    monkeypatch.setattr(
        scadenze.Database,
        "get_db",
        lambda: {"notifiche_scadenze": _Collection(rows)},
    )
    monkeypatch.setattr(scadenze, "_genera_scadenze_fiscali", lambda *_args: [])

    async def nessuna_fattura(*_args, **_kwargs):
        return []

    monkeypatch.setattr(scadenze, "_get_fatture_in_scadenza", nessuna_fattura)

    risultato = asyncio.run(
        scadenze.get_tutte_scadenze(
            anno=2026,
            mese=9,
            include_passate=True,
            limit=1,
            offset=1,
        )
    )

    assert risultato["totale"] == 3
    assert [riga["id"] for riga in risultato["scadenze"]] == ["custom-1"]
    assert risultato["pagination"] == {"offset": 1, "limit": 1}
