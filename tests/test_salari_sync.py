import asyncio

from app.services import salari_sync


def _matches(row, query):
    for key, value in query.items():
        if key == "$or":
            if not any(_matches(row, alternativa) for alternativa in value):
                return False
            continue
        actual = row.get(key)
        if isinstance(value, dict):
            if "$gte" in value and (actual is None or actual < value["$gte"]):
                return False
            if "$gt" in value and (actual is None or actual <= value["$gt"]):
                return False
        elif actual != value:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]


class _Collection:
    def __init__(self, rows=None):
        self.rows = rows or []

    def find(self, query, projection=None):
        rows = [row for row in self.rows if _matches(row, query)]
        if projection:
            inclusi = {key for key, value in projection.items() if value}
            if inclusi:
                rows = [{key: value for key, value in row.items() if key in inclusi} for row in rows]
        return _Cursor(rows)

    async def find_one(self, query, projection=None):
        rows = [row for row in self.rows if _matches(row, query)]
        if not rows:
            return None
        row = dict(rows[0])
        if projection:
            inclusi = {key for key, value in projection.items() if value}
            if inclusi:
                row = {key: value for key, value in row.items() if key in inclusi}
        return row

    async def update_one(self, query, update, **_kwargs):
        for row in self.rows:
            if _matches(row, query):
                row.update(update.get("$set", {}))
                return

    async def insert_one(self, row):
        self.rows.append(dict(row))


class _Db:
    def __init__(self, cedolini, salari):
        self.collections = {
            "cedolini": _Collection(cedolini),
            "prima_nota_salari": _Collection(salari),
        }

    def __getitem__(self, name):
        return self.collections[name]


def test_sync_completa_solo_il_periodo_contabile_senza_toccare_pagamenti(monkeypatch):
    cedolini = [
        {"id": "ced-vincenzo", "dipendente_id": "dip-v", "nome_dipendente": "CERALDI VINCENZO",
         "codice_fiscale": "CFV", "mese": 12, "anno": 2025, "netto": 1000,
         "tipo_cedolino": "mensile", "pdf_data": "pdf"},
        {"id": "ced-valerio", "dipendente_id": "dip-l", "nome_dipendente": "CERALDI VALERIO",
         "codice_fiscale": "CFL", "mese": 1, "anno": 2026, "netto_mese": 1200,
         "tipo_cedolino": "tredicesima", "pdf_data": "pdf"},
        {"id": "ced-altra", "dipendente_id": "dip-a", "nome_dipendente": "ALTRA PERSONA",
         "codice_fiscale": "CFA", "mese": 2, "anno": 2026, "netto": 900,
         "tipo_cedolino": "mensile", "pdf_data": "pdf"},
        {"id": "ced-vecchio", "dipendente_id": "dip-x", "nome_dipendente": "FUORI PERIODO",
         "codice_fiscale": "CFX", "mese": 11, "anno": 2025, "netto": 800,
         "tipo_cedolino": "mensile", "pdf_data": "pdf"},
    ]
    salari = [{
        "id": "pn-valerio", "cedolino_id": "ced-valerio", "dipendente_id": "dip-l",
        "dipendente": "CERALDI VALERIO", "codice_fiscale": "CFL", "mese": 1,
        "anno": 2026, "tipo_cedolino": "tredicesima", "importo_busta": 1100,
        "importo_bonifico": 600, "pagamenti": [{"id": "pag-1"}], "riconciliato": True,
    }]
    db = _Db(cedolini, salari)
    monkeypatch.setattr(salari_sync, "_tipo_dal_pdf", lambda _pdf: "mensile")

    esito = asyncio.run(salari_sync.sincronizza_prima_nota_da_cedolini(db))

    assert esito["prima_nota_creata"] == 2
    assert esito["prima_nota_aggiornata"] == 1
    assert {r["dipendente"] for r in db["prima_nota_salari"].rows} == {
        "CERALDI VINCENZO", "CERALDI VALERIO", "ALTRA PERSONA",
    }
    valerio = next(r for r in db["prima_nota_salari"].rows if r["id"] == "pn-valerio")
    assert valerio["tipo_cedolino"] == "mensile"
    assert valerio["importo_busta"] == 1200
    assert valerio["importo_bonifico"] == 600
    assert valerio["pagamenti"] == [{"id": "pag-1"}]
    assert valerio["riconciliato"] is True
    assert all((r["anno"], r["mese"]) >= (2025, 12)
               for r in db["prima_nota_salari"].rows)


def test_sync_e_idempotente_e_conserva_mensilita_aggiuntive(monkeypatch):
    cedolini = [{
        "id": "ced-13", "dipendente_id": "dip-1", "nome_dipendente": "DIPENDENTE TEST",
        "codice_fiscale": "CFT", "mese": 12, "anno": 2025, "netto": 950,
        "tipo_cedolino": "tredicesima", "pdf_data": "pdf",
    }]
    db = _Db(cedolini, [])
    monkeypatch.setattr(salari_sync, "_tipo_dal_pdf", lambda _pdf: "tredicesima")

    primo = asyncio.run(salari_sync.sincronizza_prima_nota_da_cedolini(db))
    secondo = asyncio.run(salari_sync.sincronizza_prima_nota_da_cedolini(db))

    assert primo["prima_nota_creata"] == 1
    assert secondo["prima_nota_creata"] == 0
    assert len(db["prima_nota_salari"].rows) == 1
    assert db["prima_nota_salari"].rows[0]["tipo_cedolino"] == "tredicesima"
