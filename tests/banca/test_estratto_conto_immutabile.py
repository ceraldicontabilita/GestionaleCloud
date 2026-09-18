"""Audit 16/07/2026 — rischio grave di perdita dell'origine documentale:
"Sposta in Cassa" copiava un movimento dell'estratto conto in cassa e
CANCELLAVA l'originale; "Elimina" sulla vista Banca cancellava la riga
dell'estratto conto. L'estratto conto è il documento bancario originale e
deve essere IMMUTABILE: le due operazioni ora marcano la riga come esclusa
dalla vista (escluso_da_vista_banca) senza mai eliminarla."""
import asyncio

from app.routers.prima_nota_module import manutenzione as mod_man
from app.routers.prima_nota_module import banca as mod_banca


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                d.update(update.get("$set", {}))

    async def delete_one(self, query, *a, **k):
        raise AssertionError("delete_one su estratto_conto_movimenti: VIETATO (immutabile)")


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Coll())


def test_sposta_in_cassa_non_cancella_l_originale_ec(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mod_man.Database, "get_db", staticmethod(lambda: db))
    db["estratto_conto_movimenti"].docs = [
        {"id": "ec-1", "data": "2026-03-01", "tipo": "uscita", "importo": 150.0,
         "descrizione": "PRELIEVO SPORTELLO"},
    ]

    anteprima = _run(mod_man.sposta_movimento(mod_man.SpostaMovimentoRequest(
        movimento_id="ec-1", da="banca", a="cassa")))
    assert anteprima["preview"] is True
    assert db["prima_nota_cassa"].docs == []
    assert "escluso_da_vista_banca" not in db["estratto_conto_movimenti"].docs[0]

    esito = _run(mod_man.sposta_movimento(mod_man.SpostaMovimentoRequest(
        movimento_id="ec-1", da="banca", a="cassa", conferma=True,
        motivo="riclassificazione approvata dall'operatore")))

    assert esito["success"] is True
    # copia creata in cassa
    assert len(db["prima_nota_cassa"].docs) == 1
    # ORIGINALE ANCORA PRESENTE nell'estratto conto, solo marcato
    originale = db["estratto_conto_movimenti"].docs[0]
    assert originale["id"] == "ec-1"
    assert originale["escluso_da_vista_banca"] is True
    assert originale["spostato_in"] == "cassa"


def test_elimina_da_vista_banca_non_cancella_l_originale_ec(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mod_banca.Database, "get_db", staticmethod(lambda: db))
    db["estratto_conto_movimenti"].docs = [
        {"id": "ec-2", "data": "2026-03-02", "tipo": "entrata", "importo": 80.0},
    ]

    esito = _run(mod_banca.delete_movimento_banca(movimento_id="ec-2", force=False))

    assert esito["success"] is True
    originale = db["estratto_conto_movimenti"].docs[0]
    assert originale["id"] == "ec-2"  # mai eliminato
    assert originale["escluso_da_vista_banca"] is True


def test_sposta_da_cassa_richiede_motivo_e_preview_non_scrive(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mod_man.Database, "get_db", staticmethod(lambda: db))
    db["prima_nota_cassa"].docs = [{
        "id": "cassa-1", "data": "2026-03-03", "tipo": "uscita",
        "importo": 40.0, "fattura_id": "F1",
    }]

    preview = _run(mod_man.sposta_movimento(mod_man.SpostaMovimentoRequest(
        movimento_id="cassa-1", da="cassa", a="banca")))
    assert preview["preview"] is True
    assert len(db["prima_nota_banca"].docs) == 0
    assert len(db["prima_nota_cassa"].docs) == 1

    try:
        _run(mod_man.sposta_movimento(mod_man.SpostaMovimentoRequest(
            movimento_id="cassa-1", da="cassa", a="banca", conferma=True)))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("una riclassificazione senza motivo deve essere rifiutata")
