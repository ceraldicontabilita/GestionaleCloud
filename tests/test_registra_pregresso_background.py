"""16/09/2026: il recupero del pregresso in produzione (860 fatture + 183
corrispettivi) ricaricava il libro giornale a ogni documento (``find_one`` per
``fattura_id``, non indicizzato sul runtime Supabase = lettura completa) e
girava dentro la richiesta HTTP: timeout a catena su Supabase, 499/502 al
client, nessun modo di seguire l'esito. Ora i gia' registrati si leggono UNA
volta e non arrivano al motore, il giro parte in background con lock e
stato persistito in ``sistema_stato``.
"""
import asyncio

from app.services import registrazione_contabile as rc
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(nome):
    return MemorySheetsClient()[nome]


async def _semina(db):
    await db["invoices"].insert_many([
        {"id": "f-gia", "total_amount": 100.0, "iva": 0, "invoice_date": "2026-02-01",
         "xml_raw": "<xml>pesante</xml>"},
        {"id": "f-nuova", "total_amount": 50.0, "iva": 0, "invoice_date": "2026-02-02"},
    ])
    await db["corrispettivi"].insert_many([
        {"id": "c-gia", "data": "2026-02-01", "totale": 110.0, "stato": "definitivo_xml"},
        {"id": "c-nuovo", "data": "2026-02-02", "totale": 220.0, "stato": "definitivo_xml"},
    ])
    # Scritture gia' presenti nel libro giornale (es. fatte dall'import
    # automatico) ma documenti sorgente senza il flag: e' il caso reale del
    # 16/09 (flag perso nella ricostruzione del 14/09).
    await db["movimenti_contabili"].insert_many([
        {"id": "m1", "tipo": "fattura_acquisto", "fattura_id": "f-gia", "anno": 2026,
         "numero_registrazione": 1, "idempotency_key": "reg:fattura:f-gia"},
        {"id": "m2", "tipo": "corrispettivo", "corrispettivo_id": "c-gia", "anno": 2026,
         "numero_registrazione": 2, "idempotency_key": "reg:corrispettivo:c-gia"},
    ])


def test_i_gia_registrati_non_arrivano_al_motore(monkeypatch):
    db = _db("pregresso-skip")
    chiamate = {"fatture": [], "corrispettivi": []}
    vero_fattura, vero_corrispettivo = rc.registra_fattura, rc.registra_corrispettivo

    async def spia_fattura(db_, fattura, **kw):
        chiamate["fatture"].append(fattura["id"])
        return await vero_fattura(db_, fattura, **kw)

    async def spia_corrispettivo(db_, corr, **kw):
        chiamate["corrispettivi"].append(corr["id"])
        return await vero_corrispettivo(db_, corr, **kw)

    monkeypatch.setattr(rc, "registra_fattura", spia_fattura)
    monkeypatch.setattr(rc, "registra_corrispettivo", spia_corrispettivo)

    async def scenario():
        await _semina(db)
        esito = await rc.registra_pregresso(db, dry_run=False)
        scritture = await db["movimenti_contabili"].find({}).to_list(20)
        f_gia = await db["invoices"].find_one({"id": "f-gia"})
        c_gia = await db["corrispettivi"].find_one({"id": "c-gia"})
        secondo = await rc.registra_pregresso(db, dry_run=False)
        return esito, scritture, f_gia, c_gia, secondo

    esito, scritture, f_gia, c_gia, secondo = _run(scenario())

    # il motore e' stato chiamato solo per i documenti davvero mancanti
    assert chiamate == {"fatture": ["f-nuova"], "corrispettivi": ["c-nuovo"]}
    assert esito["registrate"] == 2 and esito["errori"] == []
    assert esito["fatture"]["esiti"] == {"gia_registrato": 1, "registrato": 1}
    assert esito["corrispettivi"]["esiti"] == {"gia_registrato": 1, "registrato": 1}
    assert len(scritture) == 4
    # il documento gia' registrato ma senza flag viene riallineato al motore
    assert esito["fatture"]["flag_riallineati"] == 1
    assert esito["corrispettivi"]["flag_riallineati"] == 1
    assert f_gia["registrata_contabilita"] is True and f_gia["movimento_contabile_id"] == "m1"
    assert c_gia["registrato_contabilita"] is True and c_gia["movimento_contabile_id"] == "m2"
    # al secondo giro non c'e' piu' nulla da riallineare ne' da registrare
    assert secondo["registrate"] == 0 and secondo["da_registrare"] == 0
    assert secondo["fatture"]["flag_riallineati"] == 0
    assert {s["idempotency_key"] for s in scritture} == {
        "reg:fattura:f-gia", "reg:fattura:f-nuova",
        "reg:corrispettivo:c-gia", "reg:corrispettivo:c-nuovo",
    }


def test_dry_run_non_legge_il_libro_giornale_e_non_scrive(monkeypatch):
    db = _db("pregresso-dry")

    async def mai(db_):
        raise AssertionError("il dry-run non deve caricare i gia' registrati")

    monkeypatch.setattr(rc, "_gia_registrati", mai)

    async def scenario():
        await _semina(db)
        esito = await rc.registra_pregresso(db, dry_run=True)
        return esito, await db["movimenti_contabili"].find({}).to_list(20)

    esito, scritture = _run(scenario())
    assert esito["dry_run"] is True and esito["da_registrare"] == 4 and esito["registrate"] == 0
    assert len(scritture) == 2


def test_avvio_in_background_non_duplica_e_persiste_lo_stato(monkeypatch):
    db = _db("pregresso-bg")
    release = asyncio.Event()
    vero = rc.registra_pregresso

    async def lento(db_, **kw):
        await release.wait()
        return await vero(db_, **kw)

    monkeypatch.setattr(rc, "registra_pregresso", lento)

    async def scenario():
        await _semina(db)
        assert rc.pregresso_in_corso() is False
        assert rc.avvia_pregresso_in_background(db) is True
        for _ in range(5):  # lascia partire il task e scrivere lo stato iniziale
            await asyncio.sleep(0)
        assert rc.pregresso_in_corso() is True
        assert rc.avvia_pregresso_in_background(db) is False
        durante = await rc.stato_pregresso(db)
        release.set()
        await rc._pregresso_task
        dopo = await rc.stato_pregresso(db)
        return durante, dopo

    durante, dopo = _run(scenario())
    assert durante["stato"] == "in_corso" and durante["in_corso"] is True
    assert dopo["stato"] == "completato" and dopo["in_corso"] is False
    assert dopo["risultato"]["registrate"] == 2
    assert dopo["terminato_at"] >= dopo["avviato_at"]


def test_avanzamento_viene_scritto_durante_il_giro():
    db = _db("pregresso-progresso")

    async def scenario():
        await db["invoices"].insert_many([
            {"id": f"f{i}", "total_amount": 10.0, "iva": 0, "invoice_date": "2026-03-01"}
            for i in range(rc._PROGRESSO_OGNI)
        ])
        letture = []

        async def progresso(fase, fatti, totale, registrati, errori):
            letture.append((fase, fatti, totale, registrati, errori))

        await rc.registra_pregresso(db, dry_run=False, on_progress=progresso)
        return letture

    letture = _run(scenario())
    assert letture == [("fatture", rc._PROGRESSO_OGNI, rc._PROGRESSO_OGNI, rc._PROGRESSO_OGNI, 0)]


def test_router_avvia_in_background_e_espone_lo_stato(monkeypatch):
    from app.routers.accounting import piano_conti as router_mod

    db = _db("pregresso-router")
    monkeypatch.setattr(router_mod.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(rc, "avvia_pregresso_in_background", lambda _db: True)

    avvio = _run(router_mod.registra_pregresso_contabilita(dry_run=False, _admin={}))
    assert avvio == {"status": "started", "message": "Registrazione del pregresso avviata"}

    monkeypatch.setattr(rc, "avvia_pregresso_in_background", lambda _db: False)
    secondo = _run(router_mod.registra_pregresso_contabilita(dry_run=False, _admin={}))
    assert secondo["status"] == "running"

    async def con_stato():
        await db["sistema_stato"].insert_one({
            "chiave": rc._STATO_KEY, "stato": "completato",
            "risultato": {"registrate": 7},
        })
        return await router_mod.stato_registra_pregresso(_admin={})

    stato = _run(con_stato())
    assert stato["stato"] == "completato" and stato["risultato"]["registrate"] == 7
    assert stato["in_corso"] is False and "chiave" not in stato
