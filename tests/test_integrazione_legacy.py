"""15/09/2026: l'archivio legacy_staging (CeraldiFatture + modulo presenze) va
nei registri vivi: fatture/chiusure 2024-25, versamenti, acconti e
timbrature in HR, ordini storici in Lotti. Idempotente, mai indovinato."""
import asyncio

from app.services import integrazione_legacy as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs)


class _Coll:
    def __init__(self):
        self.docs = []

    def _match(self, q):
        return [d for d in self.docs if all(d.get(k) == v for k, v in (q or {}).items())]

    async def find_one(self, q=None, *a, **k):
        m = self._match(q)
        return dict(m[0]) if m else None

    def find(self, q=None, *a, **k):
        return _Cursor([dict(d) for d in self._match(q)])

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd, upsert=False, *a, **k):
        m = self._match(q)
        if not m and upsert:
            nuovo = dict(q)
            nuovo.update(upd.get("$setOnInsert", {}))
            self.docs.append(nuovo)
            m = [nuovo]
        for d in m:
            d.update(upd.get("$set", {}))


class _Db:
    def __init__(self):
        self.c = {}

    def __getitem__(self, n):
        return self.c.setdefault(n, _Coll())

    def __getattr__(self, n):
        if n.startswith("_") or n == "c":
            raise AttributeError(n)
        return self[n]


class _Con:
    def __init__(self, tabelle):
        self.tabelle = tabelle

    async def fetch(self, sql):
        tab = sql.split('legacy_staging."')[1].split('"')[0]
        return [{"row_hash": f"h-{tab}-{i}", "row_data": r} for i, r in enumerate(self.tabelle.get(tab, []))]

    async def close(self):
        pass


def test_fattura_e_chiusura_legacy_hanno_la_forma_dei_documenti_2026():
    f = mod.doc_fattura_legacy({"id": 1786135885803, "data": "2025-12-29", "numero": "FEP 72_25", "importo": 12200.0,
                                "fornitore": "A 2000", "totale_imponibile": 10000.0, "totale_imposta": 2200.0}, "hash1")
    assert f["anno"] == 2025 and f["fonte"] == "legacy_staging_2025" and f["legacy_row_hash"] == "hash1"
    assert f["importo_totale"] == 12200.0 and f["imponibile"] == 10000.0 and f["totale_iva"] == 2200.0
    assert f["evidence_status"] == "DA_VERIFICARE" and f["_id"] == "1786135885803"
    assert mod.doc_fattura_legacy({"id": 1, "data": ""}, "h") is None

    c = mod.doc_chiusura_legacy({"id": 394, "data": "2025-10-16", "pos": 2243.94, "cassa": 775.4,
                                 "iva10": 2744.85, "totale_corrispettivi": 3019.34, "incassato": 3019.34}, "hash2")
    assert (c["anno"], c["mese"]) == (2025, 10) and c["totale"] == 3019.34
    assert c["imponibile10"] == 2744.85 and c["iva10"] == 274.49 and c["totale_iva"] == 274.49
    assert c["pagato_contanti"] == 775.4 and c["pagato_elettronico"] == 2243.94
    assert c["status"] == "DA_VERIFICARE" and c["legacy_source_id"] == "394"


def test_competenza_acconto_e_ora_roma():
    assert mod.competenza_acconto({"causale": "acconto_13", "data": "2025-12-31", "modalita": "contanti"}) == (2025, 13)
    assert mod.competenza_acconto({"causale": "acconto_14", "data": "2026-08-08", "modalita": "contanti"}) == (2026, 14)
    assert mod.competenza_acconto({"causale": "stipendio", "data": "2026-08-02", "modalita": None}) == (2026, 8)
    assert mod.competenza_acconto({"causale": "stipendio", "data": "2026-07-31", "modalita": "bonifico"}) is None
    assert mod.competenza_acconto({"causale": "acconto_tfr", "data": "2026-07-31", "modalita": "contanti"}) is None
    assert mod.ora_roma("2026-07-19T04:55:00+00:00")[0] == "06:55"
    assert mod.ora_roma(None) == (None, None)


def test_ordine_legacy_diventa_ordine_lotti_inviato():
    def totali(righe):
        return {"imponibile": sum(r["prezzo_ultimo"] * r["quantita"] for r in righe), "iva": 0.0, "totale": 0.0}
    o = mod.doc_ordine_legacy({"id": 1782116554099, "date": "22/06/2026, 10:22", "supplier": "Saima", "channel": "w",
                               "total": 101.33, "created_at": "2026-07-03T16:35:49+00:00",
                               "items": [{"qty": 1, "conf": "CT", "name": "TARTELLETTA", "price": 29.01},
                                         {"qty": 2, "conf": "KG", "name": "CREMA", "price": 11.02}]}, totali)
    assert o["id"] == "legacy-ord-1782116554099" and o["data_ordine"] == "2026-06-22"
    assert o["stato"] == "inviato_fornitori" and o["fornitore"] == "Saima"
    assert [r["nome"] for r in o["prodotti"]] == ["TARTELLETTA", "CREMA"] and o["prodotti"][1]["unita"] == "kg"
    assert o["totali"]["totale_legacy"] == 101.33
    assert mod.doc_ordine_legacy({"id": 5, "items": []}, totali) is None


def test_versamenti_in_prima_nota_cassa_e_banca_idempotenti():
    db = _Db()
    con = _Con({"versamenti": [{"id": 1776860500637, "data": "2026-04-22", "importo": 1400, "note": None},
                               {"id": 9, "data": "2026-03-30", "importo": 5000, "note": "Da estratto conto"},
                               {"id": 10, "data": "2026-01-01", "importo": 100, "deleted_at": "2026-02-01"}]})
    out = _run(mod.integra_versamenti(db, con))
    assert out["registrati"] == 2 and out["importo"] == 6400.0
    cassa = db["prima_nota_cassa"].docs
    banca = db["prima_nota_banca"].docs
    assert len(cassa) == 2 and len(banca) == 2
    assert {c["tipo"] for c in cassa} == {"uscita"} and {b["tipo"] for b in banca} == {"entrata"}
    assert cassa[0]["id"] == "legacy-vers-1776860500637" and banca[0]["movimento_cassa_id"] == cassa[0]["id"]
    assert cassa[0]["conto_contabile"] and banca[0]["conto_contabile"]
    assert "estratto conto" in banca[1]["descrizione"]
    out2 = _run(mod.integra_versamenti(db, con))
    assert out2["registrati"] == 0 and out2["gia_presenti"] == 2 and len(cassa) == 2


def test_fatture_e_chiusure_saltano_quelle_gia_migrate():
    db = _Db()
    _run(db["invoices"].insert_one({"id": 1, "legacy_row_hash": "h-fatture-0"}))
    _run(db["corrispettivi"].insert_one({"id": 77, "data": "2026-08-24"}))
    con = _Con({"fatture": [{"id": 1, "data": "2026-04-01", "importo": 35.11},
                            {"id": 2, "data": "2025-12-29", "importo": 12200.0}],
                "chiusure_giornaliere": [{"id": 647, "data": "2026-08-24", "totale_corrispettivi": 1851.71},
                                         {"id": 394, "data": "2025-10-16", "totale_corrispettivi": 3019.34, "cassa": 775.4, "pos": 2243.94}]})
    f = _run(mod.integra_fatture(db, con))
    c = _run(mod.integra_chiusure(db, con))
    assert (f["inserite"], f["gia_presenti"]) == (1, 1) and f["per_anno"] == {"2025": 1}
    assert (c["inserite"], c["gia_presenti"]) == (1, 1) and c["per_anno"] == {"2025": 1}
    assert _run(mod.integra_fatture(db, con))["inserite"] == 0


def test_modulo_presenze_in_hr(monkeypatch):
    ricalcoli = []

    async def _ric(db_hr, dip_id, anno, mese):
        ricalcoli.append((dip_id, anno, mese))

    monkeypatch.setattr(mod, "_ricalcola", _ric)
    db = _Db()
    _run(db.dipendenti.insert_one({"id": "hr-tai", "nome": "Luigi", "cognome": "Taiano", "codice_fiscale": "TNALGU95L10F839Y", "nome_completo": "Taiano Luigi"}))
    _run(db.dipendenti.insert_one({"id": "hr-les", "nome": "Angela", "cognome": "Lesina", "codice_fiscale": "LSNNGL96H58F839P", "nome_completo": "Lesina Angela"}))
    _run(db.presenze_cloud.insert_one({"dipendente_id": "hr-tai", "data": "2026-08-20", "giustificativo": "F"}))
    con = _Con({
        "presenze_profili": [
            {"id": "p-tai", "nome": "Luigi", "cognome": "Taiano", "codice_fiscale": "TNALGU95L10F839Y", "attivo": True},
            {"id": "p-les", "nome": "Angela", "cognome": "Lesina", "codice_fiscale": "LSNNFL96H58F839P", "attivo": True},  # CF diverso: match per nome
            {"id": "p-str", "nome": "liliana", "cognome": "Strazzullo", "codice_fiscale": "STRLLN00D44F839G", "attivo": True,
             "data_nascita": "2000-04-04", "data_assunzione": "2025-11-17"},
            {"id": "p-mic", "nome": "Michele", "cognome": "Ceraldi", "codice_fiscale": None, "attivo": True},
        ],
        "presenze_acconti": [
            {"id": "a1", "dipendente_id": "p-tai", "data": "2026-07-15", "importo": 3600, "causale": "stipendio", "modalita": None},
            {"id": "a2", "dipendente_id": "p-tai", "data": "2026-08-08", "importo": 769.97, "causale": "acconto_14", "modalita": "contanti"},
            {"id": "a3", "dipendente_id": "p-les", "data": "2026-07-31", "importo": 677, "causale": "stipendio", "modalita": "bonifico"},
            {"id": "a4", "dipendente_id": "p-str", "data": "2026-08-04", "importo": 55, "causale": "stipendio", "modalita": "contanti"},
        ],
        "presenze_liquidazioni": [
            {"id": "l1", "dipendente_id": "p-les", "anno": 2026, "mese": 7, "contanti": 77, "bonifico": 1173, "liquidato_il": "2026-08-07T08:35:45+00:00"},
            {"id": "l2", "dipendente_id": "p-tai", "anno": 2026, "mese": 7, "contanti": None, "bonifico": 1493},
        ],
        "presenze": [
            {"id": "pr1", "dipendente_id": "p-tai", "data": "2026-07-19", "ts_entrata": "2026-07-19T04:55:00+00:00", "ts_uscita": "2026-07-19T13:00:00+00:00", "tipo_timbratura": "manuale_dip"},
            {"id": "pr2", "dipendente_id": "p-tai", "data": "2026-08-20", "ts_entrata": "2026-08-20T05:00:00+00:00", "ts_uscita": None},
            {"id": "pr3", "dipendente_id": "p-mic", "data": "2026-08-20", "ts_entrata": "2026-08-20T05:00:00+00:00"},
        ],
    })
    out = _run(mod.integra_presenze_hr(db, con))
    acc = out["acconti"]
    assert (acc["inseriti"], acc["saltati_bonifico_o_tfr"], acc["senza_dipendente"]) == (3, 1, 0)
    assert acc["importo"] == 4424.97
    paghe = {(p["dipendente_id"], p["anno"], p["mese"]): p for p in db.paghe_mensili.docs}
    assert paghe[("hr-tai", 2026, 7)]["acconti"][0]["importo"] == 3600
    assert paghe[("hr-tai", 2026, 14)]["acconti"][0]["legacy_id"] == "acc:a2"
    assert out["liquidazioni"]["saldi_contanti_inseriti"] == 1
    assert paghe[("hr-les", 2026, 7)]["acconti"][0]["importo"] == 77
    assert ("hr-les", 2026, 7) in ricalcoli and ("hr-tai", 2026, 14) in ricalcoli
    # Strazzullo non era in HR: creata (ha movimenti); Michele senza CF ne' omonimo: saltato
    assert out["anagrafiche_create"] == ["Strazzullo Liliana"]
    nuovo = next(d for d in db.dipendenti.docs if d["cognome"] == "Strazzullo")
    assert nuovo["stato"] == "attivo" and nuovo["lotti_operatore"] is False and nuovo["codice_fiscale"] == "STRLLN00D44F839G"
    assert out["profili_senza_match"] == {"p-mic": "Ceraldi Michele"}
    # timbrature: due record per pr1 (entrata/uscita a Roma), uno per pr2; pr3 senza dipendente
    tmb = db.timbrature.docs
    assert out["timbrature"]["inserite"] == 2 and out["timbrature"]["senza_dipendente"] == 1
    assert [t["tipo"] for t in tmb] == ["entrata", "uscita", "entrata"] and tmb[0]["ora"] == "06:55"
    # presenze_cloud: creata per il 19/07 (validata, 8h05), NON sovrascritta la ferie del 20/08
    p19 = _run(db.presenze_cloud.find_one({"dipendente_id": "hr-tai", "data": "2026-07-19"}))
    assert p19["validata"] is True and p19["ore_lavorate"] == 8.08 and p19["giustificativo"] == "P"
    p20 = _run(db.presenze_cloud.find_one({"dipendente_id": "hr-tai", "data": "2026-08-20"}))
    assert p20["giustificativo"] == "F" and out["timbrature"]["presenze_create"] == 1
    # secondo giro: niente doppioni
    out2 = _run(mod.integra_presenze_hr(db, con))
    assert out2["acconti"]["inseriti"] == 0 and out2["timbrature"]["inserite"] == 0 and out2["anagrafiche_create"] == []
