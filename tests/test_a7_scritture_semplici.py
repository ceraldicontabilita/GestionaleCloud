"""A7 — Scritture semplici in partita doppia sul motore unico §6.1.

Eventi non-documentali (TFR accantonamento/liquidazione/acconti) registrati in
`movimenti_contabili` con righe DARE/AVERE bilanciate, idempotenza per chiave
naturale, numero di registrazione progressivo e SENZA aggiornamento saldi
(il bilancio aggrega dai documenti sorgente: i saldi qui farebbero doppio conteggio).
"""
import asyncio

import pytest

from app.services import registrazione_contabile as rc


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None, sort=None):
        if sort:
            campo, direzione = sort[0]
            docs = sorted([d for d in self.docs if campo in d],
                          key=lambda d: d[campo], reverse=(direzione == -1))
            return docs[0] if docs else None
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()
                   if not isinstance(v, dict)):
                if all(k in d for k, v in query.items()
                       if isinstance(v, dict) and v.get("$exists")):
                    return d
        return None

    async def insert_one(self, doc):
        self.docs.append(doc)


class _Db(dict):
    def __missing__(self, k):
        self[k] = _Coll()
        return self[k]


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _scrittura_tfr(db, anno=2026, dip="d1", importo=1000.0):
    return rc.registra_scrittura_semplice(
        db,
        movimento={"data": f"{anno}-12-31", "tipo": "tfr_accantonamento",
                   "importo": importo, "dipendente_id": dip, "anno": anno,
                   "dettaglio": {"quota_annuale": importo}},
        righe=[rc.riga(rc._C_TFR_COSTO, dare=importo),
               rc.riga(rc._C_TFR_DEBITO, avere=importo)],
        chiave_naturale={"tipo": "tfr_accantonamento",
                         "dipendente_id": dip, "anno": anno},
    )


def test_scrittura_bilanciata_e_campi_preservati():
    db = _Db()
    doc = _run(_scrittura_tfr(db))
    assert doc["gia_presente"] is False
    assert doc["totale_dare"] == doc["totale_avere"] == 1000.0
    # campi del movimento originale preservati (lettori esistenti invariati)
    salvato = db[rc.COLL_MOVIMENTI].docs[0]
    assert salvato["tipo"] == "tfr_accantonamento"
    assert salvato["importo"] == 1000.0
    assert salvato["dettaglio"] == {"quota_annuale": 1000.0}
    # righe in partita doppia sui conti ESISTENTI del piano operativo
    conti = {r["conto_codice"] for r in salvato["righe"]}
    assert conti == {"05.03.03", "02.04.01"}
    assert salvato["numero_registrazione"] == 1


def test_idempotenza_per_chiave_naturale():
    db = _Db()
    _run(_scrittura_tfr(db))
    doc2 = _run(_scrittura_tfr(db))
    assert doc2["gia_presente"] is True
    assert len(db[rc.COLL_MOVIMENTI].docs) == 1


def test_scrittura_sbilanciata_rifiutata():
    db = _Db()
    with pytest.raises(ValueError):
        _run(rc.registra_scrittura_semplice(
            db,
            movimento={"tipo": "test"},
            righe=[rc.riga(rc._C_TFR_COSTO, dare=100.0),
                   rc.riga(rc._C_TFR_DEBITO, avere=90.0)],
            chiave_naturale={"tipo": "test"},
        ))
    assert len(db[rc.COLL_MOVIMENTI].docs) == 0


def test_numero_registrazione_progressivo():
    db = _Db()
    _run(_scrittura_tfr(db, dip="d1"))
    doc2 = _run(_scrittura_tfr(db, dip="d2"))
    assert doc2["numero_registrazione"] == 2


def test_nessun_aggiornamento_saldi():
    """A7: le scritture semplici NON toccano piano_conti (niente doppio conteggio)."""
    db = _Db()
    _run(_scrittura_tfr(db))
    assert rc.COLL_PIANO_CONTI not in db or db[rc.COLL_PIANO_CONTI].docs == []
