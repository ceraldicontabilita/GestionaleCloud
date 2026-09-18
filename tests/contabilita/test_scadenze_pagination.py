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
            tipo=None,
            include_passate=True,
            limit=1,
            offset=1,
        )
    )

    assert risultato["totale"] == 3
    assert [riga["id"] for riga in risultato["scadenze"]] == ["custom-1"]
    assert risultato["pagination"] == {"offset": 1, "limit": 1}


def test_scadenze_senza_mese_usa_tutto_e_solo_anno_selezionato(monkeypatch):
    rows = [
        {
            "id": "custom-2025",
            "data_scadenza": "2025-12-10",
            "descrizione": "Non appartiene all'anno",
            "completata": False,
        },
        {
            "id": "custom-2026",
            "data_scadenza": "2026-11-10",
            "descrizione": "Appartiene all'anno",
            "completata": False,
        },
    ]
    monkeypatch.setattr(
        scadenze.Database,
        "get_db",
        lambda: {"notifiche_scadenze": _Collection(rows)},
    )
    mesi_generati = []

    def genera_fiscali(anno, mese, _include_passate):
        mesi_generati.append((anno, mese))
        return []

    monkeypatch.setattr(scadenze, "_genera_scadenze_fiscali", genera_fiscali)

    async def nessuna_fattura(*_args, **_kwargs):
        return []

    monkeypatch.setattr(scadenze, "_get_fatture_in_scadenza", nessuna_fattura)

    risultato = asyncio.run(
        scadenze.get_tutte_scadenze(
            anno=2026,
            mese=None,
            tipo=None,
            include_passate=True,
            limit=50,
            offset=0,
        )
    )

    assert mesi_generati == [(2026, mese) for mese in range(1, 13)]
    assert [riga["id"] for riga in risultato["scadenze"]] == ["custom-2026"]


def test_scadenze_filtra_anche_le_personalizzate_per_mese_e_tipo(monkeypatch):
    rows = [
        {
            "id": "custom-iva-agosto",
            "data_scadenza": "2026-08-16",
            "tipo": "IVA",
            "descrizione": "IVA agosto",
            "completata": False,
        },
        {
            "id": "custom-f24-agosto",
            "data_scadenza": "2026-08-20",
            "tipo": "F24",
            "descrizione": "F24 agosto",
            "completata": False,
        },
        {
            "id": "custom-iva-settembre",
            "data_scadenza": "2026-09-16",
            "tipo": "IVA",
            "descrizione": "IVA settembre",
            "completata": False,
        },
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
            mese=8,
            tipo="IVA",
            include_passate=True,
            limit=50,
            offset=0,
        )
    )

    assert [riga["id"] for riga in risultato["scadenze"]] == ["custom-iva-agosto"]
