"""Produzione immediata al banco: una vendita per lotto anche dopo un retry."""

import asyncio
from types import SimpleNamespace

from pymongo.errors import DuplicateKeyError

from app.lotti.routers import lotti_produzione
from app.lotti.servizi import vendita_banco_service


class VenditeInMemoria:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        key = doc.get("_id")
        if key in self.docs:
            raise DuplicateKeyError("vendita già registrata")
        self.docs[key] = dict(doc)

    async def find_one(self, filtro, _projection=None):
        doc = self.docs.get(filtro["_id"])
        return {k: v for k, v in doc.items() if k != "_id"} if doc else None


def test_vendita_banco_dello_stesso_lotto_non_si_duplica(monkeypatch):
    vendite = VenditeInMemoria()
    monkeypatch.setattr(vendita_banco_service, "db", SimpleNamespace(vendite_banco=vendite))

    async def scenario():
        lotto = {"id": "lotto-1", "numero_lotto": "B-001"}
        ricetta = {"nome": "Babà", "reparto": "pasticceria", "foto_url": "/foto/baba"}
        args = (lotto, ricetta, "ricetta-1", 12, "2026-09-21", "dip-1", "Operatore")
        prima = await lotti_produzione._registra_banco_da_produzione(*args)
        seconda = await lotti_produzione._registra_banco_da_produzione(*args)
        assert prima == seconda
        assert len(vendite.docs) == 1
        assert prima["lotto_id"] == "lotto-1"
        assert prima["reparto"] == "pasticceria"
        assert prima["operatore_id"] == "dip-1"
        assert prima["pezzi_prodotti"] == 12

    asyncio.run(scenario())


def test_retry_completa_banco_senza_riprodurre_lotto(monkeypatch):
    lotto = {"id": "lotto-1", "numero_lotto": "B-001", "quantita": 12}
    operazione = {
        "lotto_creato": lotto, "destinazione": "banco",
        "parametri_banco": {
            "ricetta_id": "ricetta-1", "pezzi": 12,
            "data_produzione": "2026-09-21",
            "operatore_id": "dip-1", "operatore_nome": "Operatore",
        },
    }

    class Operazioni:
        async def insert_one(self, _doc):
            raise DuplicateKeyError("operazione già avviata")

        async def find_one(self, _filtro):
            return operazione

        async def update_one(self, _filtro, aggiornamento):
            operazione.update(aggiornamento["$set"])

    class Ricette:
        async def find_one(self, filtro, _projection):
            assert filtro == {"id": "ricetta-1"}
            return {"id": "ricetta-1", "nome": "Babà", "reparto": "pasticceria"}

    monkeypatch.setattr(lotti_produzione, "db", SimpleNamespace(
        operazioni_idempotenti=Operazioni(), ricette=Ricette()))
    chiamate = []

    async def registra_banco(*args):
        chiamate.append(args)
        return {"id": "vendita-1", "lotto_id": "lotto-1"}

    monkeypatch.setattr(lotti_produzione, "_registra_banco_da_produzione", registra_banco)

    async def scenario():
        risultato = await lotti_produzione.registra_produzione_e_crea_lotto(
            ricetta_id="ricetta-1", pezzi=999, pezzi_base=12,
            costo_totale=0, data_produzione="2026-09-22", frigo_numero=None,
            lotti_componenti_json=None, operatore_id="altro", operatore_nome="Altro",
            data_scadenza=None, memorizza_durata=False,
            operation_id="stessa-operazione", destinazione="banco",
        )
        assert risultato["id"] == "lotto-1"
        assert risultato["vendita_banco"]["id"] == "vendita-1"
        assert chiamate[0][3:] == (12, "2026-09-21", "dip-1", "Operatore")
        secondo = await lotti_produzione.registra_produzione_e_crea_lotto(
            ricetta_id="ricetta-1", pezzi=999, pezzi_base=12,
            costo_totale=0, data_produzione="2026-09-22", frigo_numero=None,
            lotti_componenti_json=None, operatore_id="altro", operatore_nome="Altro",
            data_scadenza=None, memorizza_durata=False,
            operation_id="stessa-operazione", destinazione="banco",
        )
        assert secondo == risultato
        assert len(chiamate) == 1

    asyncio.run(scenario())
