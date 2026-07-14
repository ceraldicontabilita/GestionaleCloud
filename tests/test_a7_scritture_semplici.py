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

    def _match(self, d, query):
        for k, v in query.items():
            if isinstance(v, dict):
                if v.get("$exists") and k not in d:
                    return False
            elif d.get(k) != v:
                # {"anno": None} deve intercettare sia i doc senza `anno`
                # sia quelli con `anno: None`, come in Mongo reale.
                return False
        return True

    async def find_one(self, query, projection=None, sort=None):
        candidati = [d for d in self.docs if self._match(d, query)]
        if sort:
            campo, direzione = sort[0]
            candidati = sorted([d for d in candidati if campo in d],
                               key=lambda d: d[campo], reverse=(direzione == -1))
        return candidati[0] if candidati else None

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


def test_protocollo_si_azzera_a_ogni_anno():
    """Scelta utente 2026-07-14: il protocollo riparte da 1 a ogni anno
    solare, come nella prassi dei registri contabili (non un contatore
    globale che continua a crescere tra un anno e l'altro)."""
    db = _Db()
    d1_2025 = _run(_scrittura_tfr(db, anno=2025, dip="d1"))
    d2_2025 = _run(_scrittura_tfr(db, anno=2025, dip="d2"))
    d1_2026 = _run(_scrittura_tfr(db, anno=2026, dip="d1"))
    d2_2026 = _run(_scrittura_tfr(db, anno=2026, dip="d2"))
    assert d1_2025["numero_registrazione"] == 1
    assert d2_2025["numero_registrazione"] == 2
    assert d1_2026["numero_registrazione"] == 1  # riparte da 1, non da 3
    assert d2_2026["numero_registrazione"] == 2


def test_protocollo_anno_derivato_dalla_data_se_assente():
    """registra_scrittura_semplice deduce l'anno da data_documento/data
    quando il chiamante non lo passa esplicitamente nel movimento."""
    db = _Db()
    doc = _run(rc.registra_scrittura_semplice(
        db,
        movimento={"data": "2027-03-15", "tipo": "test_senza_anno"},
        righe=[rc.riga(rc._C_TFR_COSTO, dare=10.0),
               rc.riga(rc._C_TFR_DEBITO, avere=10.0)],
        chiave_naturale={"tipo": "test_senza_anno"},
    ))
    salvato = db[rc.COLL_MOVIMENTI].docs[0]
    assert salvato["anno"] == 2027
    assert doc["numero_registrazione"] == 1
    # un'altra scrittura nel 2027 continua la stessa sequenza
    doc2 = _run(rc.registra_scrittura_semplice(
        db,
        movimento={"data": "2027-06-01", "tipo": "test_senza_anno_2"},
        righe=[rc.riga(rc._C_TFR_COSTO, dare=5.0),
               rc.riga(rc._C_TFR_DEBITO, avere=5.0)],
        chiave_naturale={"tipo": "test_senza_anno_2"},
    ))
    assert doc2["numero_registrazione"] == 2


def test_nessun_aggiornamento_saldi():
    """A7: le scritture semplici NON toccano piano_conti (niente doppio conteggio)."""
    db = _Db()
    _run(_scrittura_tfr(db))
    assert rc.COLL_PIANO_CONTI not in db or db[rc.COLL_PIANO_CONTI].docs == []


def test_ammortamento_in_partita_doppia():
    """A7 (scelta utente): DARE costo ammortamento / AVERE fondo (01.05.01→41)."""
    db = _Db()
    imp = 500.0
    doc = _run(rc.registra_scrittura_semplice(
        db,
        movimento={"data": "2026-12-31", "tipo": "ammortamento",
                   "importo": imp, "anno": 2026, "num_cespiti": 3},
        righe=[rc.riga(rc._C_AMMORTAMENTO, dare=imp),
               rc.riga(rc._C_FONDO_AMMORTAMENTO, avere=imp)],
        chiave_naturale={"tipo": "ammortamento", "anno": 2026},
    ))
    salvato = db[rc.COLL_MOVIMENTI].docs[0]
    conti = {r["conto_codice"] for r in salvato["righe"]}
    assert conti == {"05.04.01", "01.05.01"}
    assert salvato["num_cespiti"] == 3
    assert doc["totale_dare"] == doc["totale_avere"] == imp
    # idempotente per anno: una seconda registrazione non duplica
    doc2 = _run(rc.registra_scrittura_semplice(
        db, movimento={"tipo": "ammortamento"}, righe=[],
        chiave_naturale={"tipo": "ammortamento", "anno": 2026}))
    assert doc2["gia_presente"] is True


def test_fondo_ammortamento_mappato_ufficiale():
    """Il nuovo conto 01.05.01 esiste nel piano operativo ed è mappato al 41."""
    from app.services.mapping_piano_conti import OPERATIVO_A_UFFICIALE
    from app.routers.accounting.piano_conti import STRUTTURA_BASE
    codici_attivo = {c["codice"] for c in STRUTTURA_BASE["attivo"]["conti_tipici"]}
    assert "01.05.01" in codici_attivo
    assert OPERATIVO_A_UFFICIALE["01.05.01"] == "41"
