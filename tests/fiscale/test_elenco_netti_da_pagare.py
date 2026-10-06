import asyncio

from app.services import elenchi_netti
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


class _Coll:
    def __init__(self, righe):
        self.righe = righe

    def find(self, *_a, **_k):
        righe = self.righe

        class _It:
            def __aiter__(self):
                async def g():
                    for r in righe:
                        yield r
                return g()
        return _It()


class _HR:
    def __init__(self, paghe):
        self.paghe_mensili = _Coll(paghe)


def test_stipendi_da_pagare_per_nome_completo_e_al_centesimo():
    db = ClientArchivioMemoria()["t_netti"]
    asyncio.run(db["elenchi_netti"].insert_one({
        "id": "e1", "stato": "canonica", "mese": 6, "anno": 2026, "totale_cents": 150000, "filename": "x.pdf",
        "ripartizioni": [{"tipo_pagamento": "Bonifico", "righe": [
            {"cod_dip": "0000001", "nome": "ROSSI MARIO", "importo_cents": 100000, "iban": "IT60X0542811101000000123456"},
            {"cod_dip": "0000002", "nome": "BIANCHI ANNA", "importo_cents": 50000, "iban": None},
        ]}]}))
    indici = {"cf": {}, "nome": {"rossi mario": {"id": "d1"}}, "cogn": {}}
    hr = _HR([{"dipendente_id": "d1", "bonifico_importo": 1000.0, "acconti": []}])
    esito = asyncio.run(elenchi_netti.stipendi_da_pagare(db, hr, indici))
    r = {x["nome"]: x for x in esito["righe"]}
    assert r["ROSSI MARIO"]["stato"] == "pagato" and r["ROSSI MARIO"]["iban"].startswith("IT60") and "…" in r["ROSSI MARIO"]["iban"]
    assert r["BIANCHI ANNA"]["stato"] == "da_associare"
