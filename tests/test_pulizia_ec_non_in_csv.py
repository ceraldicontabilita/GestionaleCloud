"""Il confronto CSV segnala anomalie senza mutare la fonte bancaria."""
import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile

from app.routers.bank.estratto_conto import pulizia_movimenti_non_in_csv


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return self._docs


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.deleted = []
        self.updated = []

    def find(self, query=None, *a, **k):
        query = query or {}
        out = []
        for d in self.docs:
            ok = True
            for key, cond in query.items():
                v = d.get(key)
                if isinstance(cond, dict):
                    if "$gte" in cond and not (v is not None and v >= cond["$gte"]):
                        ok = False
                    if "$lte" in cond and not (v is not None and v <= cond["$lte"]):
                        ok = False
                    if "$in" in cond and v not in cond["$in"]:
                        ok = False
                    if "$nin" in cond and v in cond["$nin"]:
                        ok = False
                elif v != cond:
                    ok = False
            if ok:
                out.append(dict(d))
        return _Cursor(out)

    async def update_one(self, filtro, update):
        self.updated.append((filtro, update))

    async def update_many(self, filtro, update):
        self.updated.append((filtro, update))

        class R:
            modified_count = 0
        return R()

    async def delete_many(self, filtro):
        self.deleted.append(filtro)


class _Db:
    def __init__(self, colls):
        self.colls = colls

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _upload(testo: str) -> UploadFile:
    return UploadFile(filename="ec.csv", file=io.BytesIO(testo.encode("utf-8")))


CSV_ENTRATE = (
    'Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag\n'
    'CERALDI;03/04/2026;03/04/2026;BPM;5462;632,5;EUR;INC.POS CARTE CREDIT - NUMIA;Ricavi - Incasso tramite POS;\n'
    'CERALDI;05/04/2026;05/04/2026;BPM;5462;100;EUR;VERSAMENTO CONTANTI;Ricavi - Deposito contanti;\n'
)


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _prepara_db(monkeypatch):
    ec = _Coll([
        # presente nel CSV → resta
        {"id": "E1", "data": "2026-04-03", "importo": 632.5, "tipo": "entrata",
         "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA"},
        # entrata NON nel CSV → da eliminare
        {"id": "E2", "data": "2026-04-04", "importo": 50.0, "tipo": "entrata",
         "descrizione_originale": "ACCREDITO FANTASMA", "riconciliato": True},
        # USCITA nell'intervallo: il CSV ha solo entrate → mai toccata
        {"id": "E3", "data": "2026-04-03", "importo": 400.0, "tipo": "uscita",
         "descrizione_originale": "VS.DISP. FAVORE Parisi Antonio"},
        # estratto PAYPAL nella stessa collezione: mai toccato dall'export BPM
        {"id": "E4", "data": "2026-04-03", "importo": 6.1, "tipo": "entrata",
         "banca": "PayPal (Europe) S.à r.l et Cie, S.C.A.",
         "descrizione_originale": "Bonifico bancario sul conto PayPal - ID: X"},
    ])
    import app.routers.bank.estratto_conto as mod
    db = _Db({"estratto_conto_movimenti": ec,
              "prima_nota_banca": _Coll([{"id": "PN1", "estratto_conto_id": "E2",
                                          "fattura_id": "F1", "status": "attivo"}]),
              "prima_nota_cassa": _Coll(),
              "invoices": _Coll()})
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    return db


def test_dry_run_conta_senza_eliminare(monkeypatch):
    db = _prepara_db(monkeypatch)
    r = _run(pulizia_movimenti_non_in_csv(file=_upload(CSV_ENTRATE), dry_run=True, _admin={}))
    assert r["anomalie_non_presenti_nel_csv"] == 1
    assert r["sola_lettura"] is True
    assert r["movimenti_modificati"] == 0
    assert r["collegamenti_modificati"] == 0
    assert r["esclusi_altra_banca_o_paypal"] == 1
    assert r["segni_nel_csv"] == {"entrate": True, "uscite": False}
    assert r["mancanti_nel_db_da_importare"] == 1  # il versamento del 05/04
    assert not db.colls["estratto_conto_movimenti"].deleted


def test_apply_e_bloccato_e_non_modifica_fonti(monkeypatch):
    db = _prepara_db(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _run(pulizia_movimenti_non_in_csv(file=_upload(CSV_ENTRATE), dry_run=False, _admin={}))
    assert exc.value.status_code == 409
    assert not db.colls["estratto_conto_movimenti"].deleted
    assert not db.colls["prima_nota_banca"].updated
    assert not db.colls["invoices"].updated
