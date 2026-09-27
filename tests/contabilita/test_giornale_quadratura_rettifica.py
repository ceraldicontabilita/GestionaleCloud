"""Audit 27/09/2026 — libro giornale: Dare = Avere, anno, protocollo, cancellate.

Punto 4: le scritture ``deleted: true`` non entrano in giornale, mastro e
bilancio di verifica; la manutenzione le elenca e le annota senza cancellarle.
Punto 5: ``registra_fattura`` non salva una scrittura squadrata (57 in
produzione) e ``_scrivi_movimento`` rifiuta ogni scrittura squadrata che non
sia uno storno; la manutenzione storna e registra di nuovo.
Punto 6: la data della fattura si legge anche da ``data_documento``/``data``;
senza data nessuna scrittura (19 erano nate con ``anno`` None).
Punto 12: il protocollo per anno e' unico anche con scritture concorrenti.
"""
import asyncio

import pytest

import app.services.registrazione_contabile as motore
from app.routers.accounting import contabilita_gestionale as cg
from app.services import manutenzione_giornale as manutenzione
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    return ClientArchivioMemoria()["test"]


def _fattura(id_, **extra):
    base = {
        "id": id_, "tipo_documento": "TD01",
        "total_amount": 122.0, "total_tax": 22.0, "iva_detraibile": 22.0,
        "imponibile": 100.0, "invoice_date": "2026-05-10",
        "invoice_number": f"N-{id_}", "supplier_name": "Fornitore Srl",
        "status": "active",
    }
    base.update(extra)
    return base


# ── Punto 5: Dare = Avere ─────────────────────────────────────────────────

def test_fattura_che_non_quadra_non_si_salva():
    db = _db()
    # imponibile 100 + IVA 22 = 122, ma il totale dice 124 (bollo fuori imponibile)
    esito = _run(motore.registra_fattura(db, _fattura("F1", total_amount=124.0)))
    assert esito["stato"] == "da_verificare"
    assert "non quadrata" in esito["motivo"]
    assert _run(db["movimenti_contabili"].count_documents({})) == 0


def test_fattura_che_quadra_si_registra_e_quadra():
    db = _db()
    esito = _run(motore.registra_fattura(db, _fattura("F1")))
    assert esito["stato"] == "registrato"
    mov = esito["movimento"]
    assert motore.scrittura_quadrata(mov["righe"])


def test_scrivi_movimento_rifiuta_scrittura_squadrata_ma_non_lo_storno():
    db = _db()
    squadrata = {
        "id": "M1", "tipo": "prova", "numero_registrazione": 1,
        "righe": [{"conto_codice": "05.01.01", "dare": 100, "avere": 0},
                  {"conto_codice": "02.01.01", "dare": 0, "avere": 90}],
        "totale_dare": 100, "totale_avere": 90,
    }
    with pytest.raises(motore.ScritturaNonQuadrata):
        _run(motore._scrivi_movimento(db, dict(squadrata), []))
    assert _run(db["movimenti_contabili"].count_documents({})) == 0
    # Lo storno di una scrittura storica squadrata e' il suo specchio: passa.
    _run(motore._scrivi_movimento(db, {**squadrata, "id": "S1", "storno_di": "M0"}, []))
    assert _run(db["movimenti_contabili"].count_documents({})) == 1


# ── Punto 6: data e anno ──────────────────────────────────────────────────

def test_data_letta_da_data_documento():
    db = _db()
    esito = _run(motore.registra_fattura(
        db, _fattura("F1", invoice_date=None, data_documento="2026-03-04")))
    assert esito["stato"] == "registrato"
    assert esito["movimento"]["anno"] == 2026
    assert esito["movimento"]["data"] == "2026-03-04"


def test_fattura_senza_nessuna_data_non_si_registra():
    db = _db()
    esito = _run(motore.registra_fattura(db, _fattura("F1", invoice_date=None)))
    assert esito["stato"] == "da_verificare"
    assert _run(db["movimenti_contabili"].count_documents({})) == 0


# ── Punto 12: protocollo unico per anno ───────────────────────────────────

def test_protocollo_unico_con_scritture_concorrenti():
    db = _db()
    # Numeri gia' assegnati restano (immutabili): si riparte dal massimo.
    _run(db["movimenti_contabili"].insert_one(
        {"id": "OLD", "anno": 2026, "numero_registrazione": 7, "righe": []}))

    async def scenario():
        return await asyncio.gather(*[
            motore.registra_fattura(db, _fattura(f"F{i}")) for i in range(12)
        ])

    esiti = _run(scenario())
    numeri = [e["movimento"]["numero_registrazione"] for e in esiti]
    assert len(set(numeri)) == 12
    assert min(numeri) == 8


def test_protocollo_salta_il_numero_gia_prenotato_da_altro_processo():
    db = _db()
    _run(db[motore.COLL_NUMERI_PROTOCOLLO].insert_one(
        {"id": "x", "anno": 2026, "numero": 1, "idempotency_key": "num:2026:1"}))
    assert _run(motore._prossimo_numero(db, 2026)) == 2
    assert _run(motore._prossimo_numero(db, 2026)) == 3
    assert _run(motore._prossimo_numero(db, 2025)) == 1


# ── Punti 5+6: manutenzione, storno e nuova registrazione ─────────────────

def _seed_rettifica(db):
    _run(db["invoices"].insert_one(_fattura("FQ")))
    _run(db["invoices"].insert_one(_fattura("FA", data_documento="2026-02-01", invoice_date=None)))
    _run(db["invoices"].insert_one(_fattura("FOK")))
    squadrata = {
        "id": "MQ", "tipo": "fattura_acquisto", "fattura_id": "FQ", "anno": 2026,
        "data": "2026-05-10", "numero_registrazione": 1, "stato": "registrato",
        "idempotency_key": "reg:fattura:FQ",
        "righe": [{"conto_codice": "05.01.01", "dare": 100, "avere": 0},
                  {"conto_codice": "01.04.01", "dare": 22, "avere": 0},
                  {"conto_codice": "02.01.01", "dare": 0, "avere": 124}],
    }
    senza_anno = {
        "id": "MA", "tipo": "fattura_acquisto", "fattura_id": "FA", "anno": None,
        "data": None, "numero_registrazione": 1, "stato": "registrato",
        "idempotency_key": "reg:fattura:FA",
        "righe": [{"conto_codice": "05.01.01", "dare": 100, "avere": 0},
                  {"conto_codice": "01.04.01", "dare": 22, "avere": 0},
                  {"conto_codice": "02.01.01", "dare": 0, "avere": 122}],
    }
    for m in (squadrata, senza_anno):
        _run(db["movimenti_contabili"].insert_one(m))
    _run(motore.registra_fattura(db, _fattura("FOK")))


def test_rettifica_dry_run_elenca_senza_scrivere():
    db = _db()
    _seed_rettifica(db)
    prima = _run(db["movimenti_contabili"].count_documents({}))
    esito = _run(manutenzione.rettifica_scritture_fatture(db))
    assert esito["dry_run"] is True
    assert esito["candidate"] == 2
    assert esito["non_quadrate"] == 1 and esito["senza_anno"] == 1
    assert {v["movimento_id"] for v in esito["dettaglio"]} == {"MQ", "MA"}
    assert _run(db["movimenti_contabili"].count_documents({})) == prima


def test_rettifica_storna_riregistra_ed_e_idempotente():
    db = _db()
    _seed_rettifica(db)
    esito = _run(manutenzione.rettifica_scritture_fatture(db, dry_run=False))
    assert esito["stornate"] == 2
    # FQ: la fattura in archivio quadra (122): nuova scrittura corretta.
    # FA: la data sta in data_documento: nuova scrittura con anno 2026.
    assert esito["esiti_riregistrazione"] == {"registrato": 2}

    movs = _run(db["movimenti_contabili"].find({}, {"_id": 0}).to_list(None))
    originali = {m["id"]: m for m in movs if m["id"] in {"MQ", "MA"}}
    assert all(m["stato"] == "stornato" for m in originali.values())
    # Mai cancellato: l'originale resta, con lo storno speculare.
    storni = [m for m in movs if m.get("storno_di") in {"MQ", "MA"}]
    assert len(storni) == 2
    nuove = [m for m in movs if m.get("tipo") == "fattura_acquisto"
             and m.get("fattura_id") in {"FQ", "FA"} and m.get("stato") == "registrato"]
    assert len(nuove) == 2
    assert all(m["anno"] == 2026 and motore.scrittura_quadrata(m["righe"]) for m in nuove)
    # La chiave naturale e' passata alla nuova scrittura.
    assert {m["idempotency_key"] for m in nuove} == {"reg:fattura:FQ", "reg:fattura:FA"}
    fq = _run(db["invoices"].find_one({"id": "FQ"}, {"_id": 0}))
    assert fq["registrata_contabilita"] is True

    # Su ogni conto l'originale e il suo storno si annullano.
    per_conto = {}
    for m in movs:
        if m["id"] in {"MQ"} or m.get("storno_di") == "MQ":
            for r in m["righe"]:
                per_conto[r["conto_codice"]] = per_conto.get(r["conto_codice"], 0) + r["dare"] - r["avere"]
    assert all(abs(v) < 0.005 for v in per_conto.values())

    # Secondo giro: nulla da fare, nessuna scrittura nuova.
    totale = len(movs)
    ancora = _run(manutenzione.rettifica_scritture_fatture(db, dry_run=False))
    assert ancora["candidate"] == 0 and ancora["stornate"] == 0
    assert _run(db["movimenti_contabili"].count_documents({})) == totale


def test_rettifica_fattura_ancora_squadrata_resta_da_verificare():
    db = _db()
    _seed_rettifica(db)
    # In archivio la fattura FQ ha davvero un totale che non torna.
    _run(db["invoices"].update_one({"id": "FQ"}, {"$set": {"total_amount": 124.0}}))
    esito = _run(manutenzione.rettifica_scritture_fatture(db, dry_run=False))
    assert esito["esiti_riregistrazione"].get("da_verificare") == 1
    fq = _run(db["invoices"].find_one({"id": "FQ"}, {"_id": 0}))
    assert fq["registrata_contabilita"] is False
    assert fq["registrazione_contabile_esito"]["stato"] == "da_verificare"
    # Il riallineamento del pregresso non la rimarca «registrata».
    gia, _ = _run(motore._gia_registrati(db))
    assert "FQ" not in gia


def test_rettifica_non_crea_una_terza_scrittura_se_ne_esiste_una_valida():
    db = _db()
    _run(db["invoices"].insert_one(_fattura("FD")))
    buona = _run(motore.registra_fattura(db, _fattura("FD")))["movimento"]
    _run(db["movimenti_contabili"].insert_one({
        "id": "MD", "tipo": "fattura_acquisto", "fattura_id": "FD", "anno": 2026,
        "data": "2026-05-10", "numero_registrazione": 99, "stato": "registrato",
        "righe": [{"conto_codice": "05.01.01", "dare": 100, "avere": 0},
                  {"conto_codice": "02.01.01", "dare": 0, "avere": 90}],
    }))
    esito = _run(manutenzione.rettifica_scritture_fatture(db, dry_run=False))
    assert esito["stornate"] == 1
    assert esito["esiti_riregistrazione"] == {"gia_registrato": 1}
    valide = _run(db["movimenti_contabili"].find(
        {"tipo": "fattura_acquisto", "fattura_id": "FD", "stato": {"$ne": "stornato"}},
        {"_id": 0, "id": 1}).to_list(None))
    assert [v["id"] for v in valide] == [buona["id"]]


# ── Punto 4: scritture cancellate ─────────────────────────────────────────

def _seed_cancellate(db):
    righe = [{"conto_codice": "05.01.01", "dare": 100, "avere": 0},
             {"conto_codice": "02.01.01", "dare": 0, "avere": 100}]
    for m in (
        {"id": "A", "tipo": "fattura_acquisto", "fattura_id": "F1", "anno": 2026,
         "data_documento": "2026-04-01", "numero_registrazione": 1, "righe": righe},
        {"id": "B", "tipo": "fattura_acquisto", "fattura_id": "F1", "anno": 2026,
         "data_documento": "2026-04-01", "numero_registrazione": 2, "righe": righe,
         "deleted": True},
        {"id": "C", "tipo": "fattura_acquisto", "fattura_id": "F9", "anno": 2026,
         "data_documento": "2026-04-02", "numero_registrazione": 3, "righe": righe,
         "status": "deleted"},
    ):
        _run(db["movimenti_contabili"].insert_one(m))


def test_giornale_mastro_e_bilancio_escludono_le_cancellate(monkeypatch):
    db = _db()
    _seed_cancellate(db)
    monkeypatch.setattr(cg.Database, "get_db", lambda: db)
    giornale = _run(cg.get_libro_giornale(data_da="2026-01-01", data_a="2026-12-31", limit=500))
    assert [s["id"] for s in giornale["scritture"]] == ["A"]
    mastro = _run(cg.get_libro_mastro(data_da="2026-01-01", data_a="2026-12-31"))
    costo = next(m for m in mastro["mastrini"] if m["conto"] == "05.01.01")
    assert costo["dare"] == 100
    bilancio = _run(cg._bilancio_verifica_da_registro(db, 2026, False))
    voce = next(v for v in bilancio["conti"] if v["codice"] == "05.01.01")
    assert voce["dare"] == 100
    assert bilancio["completezza_registro"]["scritture_registrate"] == 1


def test_censimento_cancellate_elenca_annota_e_non_cancella():
    db = _db()
    _seed_cancellate(db)
    simulazione = _run(manutenzione.censisci_scritture_cancellate(db))
    assert simulazione["scritture_cancellate"] == 2
    per_id = {v["movimento_id"]: v for v in simulazione["dettaglio"]}
    assert per_id["B"]["duplicato_di"] == "A"
    assert per_id["C"]["esito"] == "documento_senza_scrittura_attiva"
    assert simulazione["annotate"] == 0

    applicato = _run(manutenzione.censisci_scritture_cancellate(db, dry_run=False))
    assert applicato["annotate"] == 2
    b = _run(db["movimenti_contabili"].find_one({"id": "B"}, {"_id": 0}))
    assert b["deleted"] is True
    assert b["annullamento"]["esito"] == "annullata_come_doppione"
    assert _run(db["movimenti_contabili"].count_documents({})) == 3
    # Idempotente.
    assert _run(manutenzione.censisci_scritture_cancellate(db, dry_run=False))["annotate"] == 0


def test_scrittura_rifiutata_non_brucia_un_numero_di_protocollo():
    db = _db()
    righe_ok = [{"conto_codice": "05.01.01", "dare": 100, "avere": 0},
                {"conto_codice": "02.01.01", "dare": 0, "avere": 100}]
    squadrata = {
        "id": "M1", "tipo": "prova", "anno": 2026, "numero_registrazione": None,
        "righe": [{"conto_codice": "05.01.01", "dare": 100, "avere": 0},
                  {"conto_codice": "02.01.01", "dare": 0, "avere": 90}],
        "totale_dare": 100, "totale_avere": 90,
    }
    with pytest.raises(motore.ScritturaNonQuadrata):
        _run(motore._scrivi_movimento(db, dict(squadrata), []))
    mov = _run(motore._scrivi_movimento(db, {
        **squadrata, "id": "M2", "righe": righe_ok, "totale_avere": 100}, []))
    assert mov["numero_registrazione"] == 1
