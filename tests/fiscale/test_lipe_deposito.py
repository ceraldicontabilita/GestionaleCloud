"""Le LIPE lette entrano in una collezione sola, e solo se quadrano.

Due regole che valgono piu' del resto:

- un periodo la cui aritmetica del modulo non torna **non viene depositato**:
  una lettura non affidabile non puo' diventare una fonte fiscale;
- una comunicazione **ritrasmessa** (protocollo piu' alto) sostituisce la
  precedente sullo stesso periodo, e una piu' vecchia non la sovrascrive.
"""
import asyncio

import pytest

from app.services import lipe_deposito as mod


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Collezione:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.scritture = []

    async def find_one(self, filtro, proj=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in filtro.items()):
                return dict(doc)
        return None

    async def update_one(self, filtro, aggiornamento, upsert=False):
        self.scritture.append((filtro, aggiornamento))
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in filtro.items()):
                doc.update(aggiornamento["$set"])
                return None
        self.docs.append(dict(aggiornamento["$set"]))
        return None


class _Db:
    def __init__(self, lipe=None):
        self.collezioni = {mod.COLL_LIPE: _Collezione(lipe)}

    def __getitem__(self, nome):
        return self.collezioni.setdefault(nome, _Collezione())


def _letto(periodi):
    return {"anno": "2026", "periodi": periodi, "periodi_letti": len(periodi)}


MARZO_BUONO = {
    "pagina": 4, "mese": "03", "periodo": "2026-03",
    "iva_esigibile": 6131.26, "iva_detratta": 6396.64,
    "iva_da_versare_o_credito": 18324.30,
    "iva_da_versare_o_credito_segno": "credito", "quadratura_ok": True,
}


# ── Il nome del file ──────────────────────────────────────────────────────

@pytest.mark.parametrize("nome,atteso", [
    ("LIPE_2026_407141844.pdf", 407141844),
    ("LIPE_2024_358048737.pdf", 358048737),
    ("lipe 2021 296015657.PDF", 296015657),
    ("qualcosa.pdf", None),
    (None, None),
])
def test_il_protocollo_si_ricava_dal_nome(nome, atteso):
    assert mod.protocollo_da_nome(nome) == atteso


@pytest.mark.parametrize("nome,atteso", [
    ("LIPE_2026_407141844.pdf", True), ("lipe.pdf", True),
    ("F24 iva gennaio.pdf", False), ("", False), (None, False),
])
def test_riconosce_una_lipe_dal_nome(nome, atteso):
    assert mod.e_una_lipe(nome) is atteso


# ── Il deposito ───────────────────────────────────────────────────────────

def test_un_periodo_che_quadra_viene_depositato(monkeypatch):
    monkeypatch.setattr(mod, "parse_lipe", lambda _b: _letto([MARZO_BUONO]))
    db = _Db()

    esito = _run(mod.deposita_lipe(
        db, b"pdf", nome_file="LIPE_2026_407141844.pdf", origine="test", dry_run=False))

    assert esito["depositati"] == ["2026-03"]
    salvato = db[mod.COLL_LIPE].docs[0]
    assert salvato["iva_detratta"] == 6396.64
    assert salvato["protocollo"] == 407141844
    assert "pagina" not in salvato


def test_un_periodo_che_non_quadra_non_entra(monkeypatch):
    """La lettura non e' affidabile: non puo' diventare una fonte fiscale."""
    rotto = dict(MARZO_BUONO, quadratura_ok=False)
    monkeypatch.setattr(mod, "parse_lipe", lambda _b: _letto([rotto]))
    db = _Db()

    esito = _run(mod.deposita_lipe(
        db, b"pdf", nome_file="LIPE_2026_1.pdf", origine="test", dry_run=False))

    assert esito["depositati"] == []
    assert esito["scartati"] == [
        {"periodo": "2026-03", "motivo": "l'aritmetica del modulo non torna"}
    ]
    assert db[mod.COLL_LIPE].scritture == []


def test_un_periodo_senza_data_non_entra(monkeypatch):
    senza = dict(MARZO_BUONO, periodo=None)
    monkeypatch.setattr(mod, "parse_lipe", lambda _b: _letto([senza]))
    db = _Db()

    esito = _run(mod.deposita_lipe(
        db, b"pdf", nome_file="LIPE.pdf", origine="test", dry_run=False))

    assert esito["depositati"] == [] and len(esito["scartati"]) == 1


def test_in_dry_run_non_si_scrive(monkeypatch):
    monkeypatch.setattr(mod, "parse_lipe", lambda _b: _letto([MARZO_BUONO]))
    db = _Db()

    esito = _run(mod.deposita_lipe(
        db, b"pdf", nome_file="LIPE_2026_1.pdf", origine="test", dry_run=True))

    assert esito["depositati"] == ["2026-03"]
    assert db[mod.COLL_LIPE].scritture == []


# ── Ritrasmissioni ────────────────────────────────────────────────────────

def test_una_ritrasmissione_sostituisce_la_precedente(monkeypatch):
    monkeypatch.setattr(mod, "parse_lipe", lambda _b: _letto([
        dict(MARZO_BUONO, iva_detratta=9999.99)]))
    db = _Db([{"periodo": "2026-03", "protocollo": 100, "iva_detratta": 6396.64}])

    esito = _run(mod.deposita_lipe(
        db, b"pdf", nome_file="LIPE_2026_200.pdf", origine="test", dry_run=False))

    assert esito["depositati"] == ["2026-03"]
    assert db[mod.COLL_LIPE].docs[0]["iva_detratta"] == 9999.99


def test_una_comunicazione_piu_vecchia_non_sovrascrive(monkeypatch):
    monkeypatch.setattr(mod, "parse_lipe", lambda _b: _letto([
        dict(MARZO_BUONO, iva_detratta=1.0)]))
    db = _Db([{"periodo": "2026-03", "protocollo": 500, "iva_detratta": 6396.64}])

    esito = _run(mod.deposita_lipe(
        db, b"pdf", nome_file="LIPE_2026_100.pdf", origine="test", dry_run=False))

    assert esito["ignorati_perche_superati"] == ["2026-03"]
    assert db[mod.COLL_LIPE].docs[0]["iva_detratta"] == 6396.64


def test_rileggere_la_stessa_lipe_non_duplica(monkeypatch):
    monkeypatch.setattr(mod, "parse_lipe", lambda _b: _letto([MARZO_BUONO]))
    db = _Db()

    for _ in range(3):
        _run(mod.deposita_lipe(db, b"pdf", nome_file="LIPE_2026_407141844.pdf",
                               origine="test", dry_run=False))

    assert len(db[mod.COLL_LIPE].docs) == 1
