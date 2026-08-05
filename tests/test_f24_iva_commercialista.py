import asyncio

from app.services.verifica_coerenza import VerificaCoerenza


class _Cursor:
    def __init__(self, docs): self.docs = docs
    async def to_list(self, limit): return list(self.docs[:limit])


class _Collection:
    def __init__(self, docs): self.docs = docs
    def find(self, *args, **kwargs): return _Cursor(self.docs)


class _Db:
    def __init__(self, docs): self.docs = docs
    def __getitem__(self, name): return _Collection(self.docs if name == "f24_unificato" else [])


def _run(coro):
    loop = asyncio.new_event_loop()
    try: return loop.run_until_complete(coro)
    finally: loop.close()


def test_iva_usa_solo_riga_mensile_anche_se_f24_contiene_1040():
    f24 = {
        "id": "F24-MARZO",
        "sezione_erario": [
            {"codice_tributo": "6003", "periodo_riferimento": "03/2026", "importo_debito": 1250},
            {"codice_tributo": "1040", "periodo_riferimento": "03/2026", "importo_debito": 490},
        ],
    }
    result = _run(VerificaCoerenza(_Db([f24])).trova_f24_iva_mensile(2026, 3))
    assert result["stato"] == "f24_ricevuto"
    assert result["codice_tributo"] == "6003"
    assert result["importo_f24"] == 1250
    assert result["f24_multi_tributo"] is True
    assert result["altri_codici_tributo"] == ["1040"]


def test_due_modelli_con_stessa_riga_iva_restano_ambigui():
    docs = [
        {"id": "A", "sezione_erario": [{"codice_tributo": "6003", "mese": "03", "anno": "2026", "importo_debito": 100}]},
        {"id": "B", "sezione_erario": [{"codice_tributo": "6003", "mese": "03", "anno": "2026", "importo_debito": 100}]},
    ]
    result = _run(VerificaCoerenza(_Db(docs)).trova_f24_iva_mensile(2026, 3))
    assert result["stato"] == "f24_ambiguo"
    assert result["importo_f24"] is None
