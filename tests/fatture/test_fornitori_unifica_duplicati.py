"""Deduplica fornitori: certi, probabili, da decidere, fusione soft e giro idempotente.

Caso del titolare (01/10/2026): «TOP DISTRBUZIONE SRL» (con P.IVA, 1 fattura) e
«Top Distribuzione S.r.l.» (senza P.IVA, 0 fatture) comparivano due volte.
"""
import asyncio

import pytest

from app.services import fornitori_dedupe as dd
from app.services.piva_validazione import (
    chiave_confronto, esito_piva, luhn_italiano_ok, normalizza_piva, piva_valida, vista_piva,
)

PIVA_TOP = "07267610637"
PIVA_TIMAS = "07818970639"
PIVA_SUMUP_NL = "NL858187498B01"
PIVA_SUMUP_IE = "IE9813461A"


def _match(doc, filtro):
    for k, v in filtro.items():
        if k == "$or":
            if not any(_match(doc, f) for f in v):
                return False
            continue
        val = doc.get(k)
        if isinstance(v, dict):
            if "$exists" in v and (k in doc) != v["$exists"]:
                return False
            if "$in" in v and val not in v["$in"]:
                return False
        elif val != v:
            return False
    return True


class _Res:
    def __init__(self, n):
        self.modified_count = n


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _n):
        return self.docs


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, filtro=None, proj=None):
        return _Cursor([dict(d) for d in self.docs if _match(d, filtro or {})])

    async def find_one(self, filtro, *a, **k):
        for d in self.docs:
            if _match(d, filtro):
                return dict(d)
        return None

    async def update_many(self, filtro, update):
        n = 0
        for d in self.docs:
            if _match(d, filtro):
                d.update(update.get("$set", {}))
                n += 1
        return _Res(n)

    async def update_one(self, filtro, update, **_k):
        for d in self.docs:
            if _match(d, filtro):
                d.update(update.get("$set", {}))
                return _Res(1)
        return _Res(0)


class _Db:
    def __init__(self):
        self.c = {}

    def __getitem__(self, nome):
        return self.c.setdefault(nome, _Coll())

    async def list_collection_names(self):
        return list(self.c)


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


@pytest.fixture()
def db(monkeypatch):
    d = _Db()
    monkeypatch.setattr(dd.Database, "get_db", staticmethod(lambda: d))

    async def _no_cache():
        return None

    monkeypatch.setattr(dd, "_invalida_cache", _no_cache)
    return d


def _scenario(db):
    db["fornitori"].docs = [
        {"id": 115, "ragione_sociale": "Top Distribuzione S.r.l.", "created_at": "2026-04-22"},
        {"id": 120, "ragione_sociale": "TOP DISTRBUZIONE SRL", "partita_iva": PIVA_TOP,
         "iban": "IT60X0542811101000000123456", "metodo_pagamento": "bonifico"},
        {"id": "sumup-nl", "ragione_sociale": "SumUp Limited", "partita_iva": PIVA_SUMUP_NL},
        {"id": "sumup-ie", "ragione_sociale": "SumUp Limited", "partita_iva": PIVA_SUMUP_IE},
        {"id": 366, "ragione_sociale": "ENOTECA CONTE S.R.L."},
        {"id": 88, "ragione_sociale": "ENOTECA DANTE S.R.L.", "partita_iva": "07024451218"},
    ]
    db["invoices"].docs = [
        {"id": "f1", "supplier_id": "120", "cedente_piva": PIVA_TOP, "supplier_name": "TOP DISTRBUZIONE SRL"},
    ]


# ── validazione P.IVA ──────────────────────────────────────────────────────

def test_normalizza_e_chiave():
    assert normalizza_piva(" IT 07267610637 ") == PIVA_TOP
    assert chiave_confronto("IT" + PIVA_TOP) == chiave_confronto(PIVA_TOP)
    assert chiave_confronto("it00093830792") == chiave_confronto("93830792")


def test_luhn_e_valida():
    assert luhn_italiano_ok(PIVA_TOP) and piva_valida(PIVA_TOP)
    assert not luhn_italiano_ok("07267610638")
    assert piva_valida(PIVA_SUMUP_IE) and piva_valida("DE814584193")
    assert not piva_valida("") and not piva_valida("123")


def test_esito_piva_codici():
    assert esito_piva(PIVA_TOP) is None
    assert esito_piva("07267610638")["codici"] == ["checksum"]
    assert esito_piva("1234567890")["codici"] == ["lunghezza"]
    assert esito_piva("RSSMRA80A01H501U")["codici"] == ["uguale_cf_persona"]
    assert esito_piva("821186462B01")["codici"] == ["formato"]
    assert esito_piva(PIVA_SUMUP_IE, nazione="IT")["codici"] == ["estera_come_italiana"]
    assert esito_piva(PIVA_SUMUP_IE, nazione="IE") is None
    assert esito_piva("", fatture=0) is None
    assert esito_piva("", fatture=3)["codici"] == ["assente_con_fatture"]
    v = vista_piva({"partita_iva": "", "fatture_count": 2})
    assert v["piva_da_verificare"] is True and v["piva_motivo"]


# ── classificazione ────────────────────────────────────────────────────────

def test_classifica_certi_per_piva_anche_con_prefisso_e_zeri():
    recs = [
        {"id": "a", "ragione_sociale": "Rossi Srl", "partita_iva": PIVA_TOP, "iban": "x"},
        {"id": "b", "ragione_sociale": "Bianchi", "partita_iva": "IT" + PIVA_TOP},
    ]
    cl = dd.classifica(recs)
    assert cl["totali"]["certi"] == 1
    assert cl["certi"][0]["vincente"]["id"] == "a"


def test_classifica_probabile_con_refuso_e_nessuna_fusione_a_rischio():
    recs = [
        {"id": 115, "ragione_sociale": "Top Distribuzione S.r.l."},
        {"id": 120, "ragione_sociale": "TOP DISTRBUZIONE SRL", "partita_iva": PIVA_TOP},
        {"id": "n", "ragione_sociale": "SumUp Limited", "partita_iva": PIVA_SUMUP_NL},
        {"id": "i", "ragione_sociale": "SumUp Limited", "partita_iva": PIVA_SUMUP_IE},
        {"id": 366, "ragione_sociale": "ENOTECA CONTE S.R.L."},
        {"id": 88, "ragione_sociale": "ENOTECA DANTE S.R.L.", "partita_iva": "07024451218"},
    ]
    cl = dd.classifica(recs)
    assert [(p["perdente"]["id"], p["vincente"]["id"]) for p in cl["probabili"]] == [(115, 120)]
    assert cl["totali"]["certi"] == 0
    # ENOTECA CONTE / DANTE: nome solo simile -> da decidere, mai fusione automatica
    assert any({f["id"] for f in g["fornitori"]} == {366, 88} for g in cl["da_decidere"])
    # le due SumUp (P.IVA diverse) non compaiono da nessuna parte
    visti = {p["perdente"]["id"] for p in cl["probabili"]} | {f["id"] for g in cl["da_decidere"] for f in g["fornitori"]}
    assert "n" not in visti and "i" not in visti


def test_classifica_stesso_cf_con_piva_diverse_va_da_decidere():
    recs = [
        {"id": "a", "ragione_sociale": "Uno", "partita_iva": PIVA_TOP, "codice_fiscale": "RSSMRA80A01H501U"},
        {"id": "b", "ragione_sociale": "Due", "partita_iva": PIVA_TIMAS, "codice_fiscale": "RSSMRA80A01H501U"},
    ]
    cl = dd.classifica(recs)
    assert cl["totali"]["certi"] == 0 and cl["totali"]["da_decidere"] == 1


def test_classifica_ambiguo_due_candidati_non_si_fonde():
    recs = [
        {"id": 1, "ragione_sociale": "Alfa Beta"},
        {"id": 2, "ragione_sociale": "Alfa Beta", "partita_iva": PIVA_TOP},
        {"id": 3, "ragione_sociale": "Alfa Beta Gamma", "partita_iva": PIVA_TIMAS},
    ]
    cl = dd.classifica(recs)
    assert cl["probabili"] == []


# ── fusione ────────────────────────────────────────────────────────────────

def test_merge_riassegna_conserva_e_non_cancella(db):
    db["fornitori"].docs = [
        {"id": 120, "ragione_sociale": "TOP DISTRBUZIONE SRL", "partita_iva": PIVA_TOP, "iban": "IT1"},
        {"id": 115, "ragione_sociale": "Top Distribuzione S.r.l.", "iban": "IT2", "note": "nota"},
    ]
    db["invoices"].docs = [{"id": "f", "supplier_id": "115"}, {"id": "g", "supplier_id": 115}]
    db["scadenziario_fornitori"].docs = [{"id": "s", "fornitore_id": 115}]
    db["fornitori_keywords"].docs = [{"id": "k", "fornitore_id": "115"}]
    res = _run(dd.merge_fornitori(120, 115, motivo="test"))
    assert res["success"] and res["stats_migrazione"]["fatture_migrate"] == 2
    assert [d["supplier_id"] for d in db["invoices"].docs] == [120, 120]
    assert db["scadenziario_fornitori"].docs[0]["fornitore_id"] == 120
    assert db["fornitori_keywords"].docs[0]["fornitore_id"] == 120
    vincente = next(d for d in db["fornitori"].docs if d["id"] == 120)
    perdente = next(d for d in db["fornitori"].docs if d["id"] == 115)
    assert len(db["fornitori"].docs) == 2  # niente cancellazione
    assert perdente["merged_into"] == 120 and perdente["status"] == "unificato"
    assert vincente["id_precedenti"] == ["115"]
    assert "Top Distribuzione S.r.l." in vincente["alias"] or vincente["alias"] == []
    assert vincente["iban"] == "IT1" and vincente["iban_alternativi"] == ["IT2"]
    assert vincente["note"] == "nota"
    assert vincente["storico_fusioni"][0]["conflitti"][0]["campo"] == "iban"
    with pytest.raises(ValueError):
        _run(dd.merge_fornitori(120, 115))  # gia' unificato


def test_merge_certo_svuota_la_piva_del_perdente_ma_la_conserva(db):
    db["fornitori"].docs = [
        {"id": "a", "ragione_sociale": "Rossi Srl", "partita_iva": PIVA_TOP, "iban": "IT1"},
        {"id": "b", "ragione_sociale": "Rossi S.r.l.", "partita_iva": "IT" + PIVA_TOP, "piva": "IT" + PIVA_TOP},
    ]
    db["prima_nota_cassa"].docs = [{"id": "p", "fornitore_piva": "IT" + PIVA_TOP}]
    _run(dd.merge_fornitori("a", "b", motivo="test"))
    b = next(d for d in db["fornitori"].docs if d["id"] == "b")
    assert b["partita_iva"] == "" and b["piva"] == "" and b["piva_unificata"] == PIVA_TOP
    assert db["prima_nota_cassa"].docs[0]["fornitore_piva"] == PIVA_TOP


def test_merge_rifiuta_due_piva_valide_diverse_e_hard_delete(db):
    db["fornitori"].docs = [
        {"id": "a", "ragione_sociale": "SumUp Limited", "partita_iva": PIVA_SUMUP_NL},
        {"id": "b", "ragione_sociale": "SumUp Limited", "partita_iva": PIVA_SUMUP_IE},
    ]
    with pytest.raises(ValueError, match="diverse"):
        _run(dd.merge_fornitori("a", "b"))
    with pytest.raises(ValueError, match="soft"):
        _run(dd.merge_fornitori("a", "b", soft=False))
    assert all("merged_into" not in d for d in db["fornitori"].docs)


# ── P.IVA dalle fatture, orfane, giro ──────────────────────────────────────

def test_completa_piva_solo_se_unica(db):
    db["fornitori"].docs = [
        {"id": 10, "ragione_sociale": "ARUBA SPA"},
        {"id": 11, "ragione_sociale": "Doppia Srl"},
        {"id": 12, "ragione_sociale": "Rotta Srl"},
    ]
    db["invoices"].docs = [
        {"supplier_name": "ARUBA SPA", "cedente_piva": PIVA_TIMAS},
        {"supplier_name": "Doppia Srl", "cedente_piva": PIVA_TIMAS},
        {"supplier_name": "Doppia Srl", "cedente_piva": PIVA_TOP},
        {"supplier_name": "Rotta Srl", "cedente_piva": "07267610638"},  # checksum errato: non si usa
    ]
    esito = _run(dd.completa_piva_da_fatture(db))
    assert esito["completati"] == 1
    aruba = db["fornitori"].docs[0]
    assert aruba["partita_iva"] == PIVA_TIMAS and aruba["piva_fonte"] == "fatture"
    assert "partita_iva" not in db["fornitori"].docs[1] and "partita_iva" not in db["fornitori"].docs[2]


def test_riallinea_fatture_orfane_solo_se_piva_univoca(db):
    db["fornitori"].docs = [{"id": 120, "ragione_sociale": "Top", "partita_iva": PIVA_TOP}]
    db["invoices"].docs = [
        {"id": "a", "supplier_id": "sparito", "cedente_piva": PIVA_TOP},
        {"id": "b", "supplier_id": "altro-sparito", "cedente_piva": "99999999999"},
        {"id": "c", "supplier_id": 120, "cedente_piva": PIVA_TOP},
    ]
    esito = _run(dd.riallinea_fatture_orfane(db))
    assert esito["fatture_ripuntate"] == 1
    assert [d["supplier_id"] for d in db["invoices"].docs] == [120, "altro-sparito", 120]


def test_giro_unifica_e_secondo_giro_non_fa_niente(db):
    _scenario(db)
    primo = _run(dd.giro_unifica_fornitori())
    assert [(f["duplicate_id"], f["target_id"]) for f in primo["fusi"]] == [(115, 120)]
    assert primo["da_decidere"] == 1  # ENOTECA CONTE / DANTE
    perdente = next(d for d in db["fornitori"].docs if d["id"] == 115)
    assert perdente["merged_into"] == 120
    assert len(db["fornitori"].docs) == 6
    secondo = _run(dd.giro_unifica_fornitori())
    assert secondo["fusi"] == [] and secondo["piva_completate"] == 0 and secondo["fatture_ripuntate"] == 0
    assert secondo["da_decidere"] == 1


def test_giro_dry_run_non_scrive(db):
    _scenario(db)
    esito = _run(dd.giro_unifica_fornitori(dry_run=True))
    assert esito["fusi"][0]["dry_run"] is True
    assert all("merged_into" not in d for d in db["fornitori"].docs)


# ── prevenzione nell'import fatture ────────────────────────────────────────

def _fattura(vat, nome):
    return {"supplier_vat": vat, "supplier_name": nome, "cliente": {"partita_iva": "04523831214"},
            "fornitore": {"nazione": "IT"}}


def test_import_aggancia_la_stessa_piva_con_prefisso_e_ignora_gli_unificati(db):
    from app.routers.invoices.fatture_upload import ensure_supplier_exists

    db["fornitori"].docs = [
        {"id": "vecchio", "ragione_sociale": "TOP DISTRBUZIONE SRL", "partita_iva": PIVA_TOP,
         "merged_into": "nuovo", "status": "unificato"},
        {"_id": "n", "id": "nuovo", "ragione_sociale": "TOP DISTRBUZIONE SRL", "partita_iva": "IT" + PIVA_TOP},
    ]

    async def _insert(doc, session=None):
        raise AssertionError("non deve nascere un secondo fornitore")

    db["fornitori"].insert_one = _insert
    res = _run(ensure_supplier_exists(db, _fattura(PIVA_TOP, "TOP DISTRBUZIONE SRL")))
    assert res["supplier_exists"] is True and res["supplier_created"] is False
    assert res["supplier_id"] == "nuovo"
