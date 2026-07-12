"""
Quietanza F24 dell'Agenzia Entrate → segna COMPLETATE le scadenze del
calendario fiscale (richiesta utente 12/07/2026).

Verifica la mappatura codice-tributo → tipo-scadenza e la marcatura idempotente
e reversibile su `calendario_fiscale`, con la logica di periodo corretta:
ritenute/INPS sul mese di versamento (= mese pagamento), IVA sul mese di
competenza (mese pagamento - 1).
"""
import asyncio

from app.services import quietanze_import as qi


def test_mappa_codice_tributo_a_tipo_scadenza():
    assert qi._tipo_scadenza_da_codice('1040') == 'RITENUTE'
    assert qi._tipo_scadenza_da_codice('1001') == 'RITENUTE'
    assert qi._tipo_scadenza_da_codice('6001') == 'IVA'
    assert qi._tipo_scadenza_da_codice('6012') == 'IVA'
    assert qi._tipo_scadenza_da_codice('DM10') == 'INPS'
    assert qi._tipo_scadenza_da_codice('C10') == 'INPS'
    # RC01 = regolarizzazione periodo precedente: NON marca il mese corrente
    assert qi._tipo_scadenza_da_codice('RC01') == ''
    # codice ignoto
    assert qi._tipo_scadenza_da_codice('9999') == ''
    assert qi._tipo_scadenza_da_codice('') == ''


class _FakeCalendario:
    def __init__(self, docs):
        self.docs = docs  # lista di dict con 'id' e 'completato'

    async def update_one(self, filtro, update):
        class _Res:
            modified_count = 0
        res = _Res()
        for d in self.docs:
            if d.get('id') != filtro.get('id'):
                continue
            # filtro completato $ne True
            ne = filtro.get('completato', {})
            if isinstance(ne, dict) and '$ne' in ne and d.get('completato') == ne['$ne']:
                continue
            d.update(update['$set'])
            res.modified_count = 1
            break
        return res


class _FakeDb:
    def __init__(self, docs):
        self._cal = _FakeCalendario(docs)

    def __getitem__(self, name):
        assert name == qi.COLL_CALENDARIO
        return self._cal


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _f24(tributi):
    """Costruisce un F24 fittizio con i tributi dati (codice, sezione)."""
    doc = {"id": "F24X", "sezione_erario": [], "sezione_inps": []}
    for cod in tributi:
        if cod.upper().startswith(('DM', 'C', 'RC')) and not cod.isdigit():
            doc["sezione_inps"].append({"causale": cod, "periodo_riferimento": "", "importo_debito": 100})
        else:
            doc["sezione_erario"].append({"codice_tributo": cod, "periodo_riferimento": "", "importo_debito": 100})
    return doc


def test_marca_ritenute_e_inps_sul_mese_di_pagamento():
    docs = [
        {"id": "ritenute_2026_02", "completato": False},
        {"id": "inps_2026_02", "completato": False},
        {"id": "ritenute_2026_03", "completato": False},  # altro mese: non toccare
    ]
    f24 = _f24(['1040', 'DM10'])
    marcate = _run(qi._marca_scadenze_calendario(_FakeDb(docs), f24, "2026-02-16", "Q1"))
    assert set(marcate) == {"ritenute_2026_02", "inps_2026_02"}
    assert docs[0]["completato"] is True and docs[0]["completato_da"] == "quietanza_f24"
    assert docs[1]["completato"] is True
    assert docs[2]["completato"] is False  # marzo intatto


def test_marca_iva_sul_mese_di_competenza():
    # IVA pagata il 16/02 → competenza gennaio → iva_liq_2026_01
    docs = [{"id": "iva_liq_2026_01", "completato": False}]
    f24 = _f24(['6001'])
    marcate = _run(qi._marca_scadenze_calendario(_FakeDb(docs), f24, "2026-02-16", "Q2"))
    assert marcate == ["iva_liq_2026_01"]
    assert docs[0]["completato"] is True


def test_iva_gennaio_competenza_dicembre_anno_precedente():
    # IVA pagata il 16/01/2026 → competenza dicembre 2025 → iva_liq_2025_12
    docs = [{"id": "iva_liq_2025_12", "completato": False}]
    marcate = _run(qi._marca_scadenze_calendario(_FakeDb(docs), _f24(['6012']), "2026-01-16", "Q3"))
    assert marcate == ["iva_liq_2025_12"]


def test_rc01_non_marca_nulla():
    docs = [{"id": "inps_2026_02", "completato": False}]
    marcate = _run(qi._marca_scadenze_calendario(_FakeDb(docs), _f24(['RC01']), "2026-02-16", "Q4"))
    assert marcate == []
    assert docs[0]["completato"] is False


def test_non_ritocca_scadenza_gia_completata():
    docs = [{"id": "ritenute_2026_02", "completato": True}]
    marcate = _run(qi._marca_scadenze_calendario(_FakeDb(docs), _f24(['1040']), "2026-02-16", "Q5"))
    assert marcate == []  # già completata, modified_count 0


def test_senza_data_pagamento_non_marca():
    docs = [{"id": "ritenute_2026_02", "completato": False}]
    marcate = _run(qi._marca_scadenze_calendario(_FakeDb(docs), _f24(['1040']), "", "Q6"))
    assert marcate == []
    assert docs[0]["completato"] is False
