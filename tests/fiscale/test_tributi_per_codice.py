"""Tributi per codice e ritenute pagate dalla quietanza (casi reali 2026, anonimi)."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers import ritenute as rit_router
from app.services import tributi_per_codice as tributi


def run(coro):
    return asyncio.run(coro)


def _riga(codice, periodo, debito=0, credito=0):
    return {"codice_tributo": codice, "periodo_riferimento": periodo,
            "importo_debito_cents": debito, "importo_credito_cents": credito}


def _quietanza(id_, data, protocollo, erario=(), regioni=(), locali=(), **kw):
    righe = list(erario) + list(regioni) + list(locali)
    saldo = sum(r["importo_debito_cents"] - r["importo_credito_cents"] for r in righe)
    return {
        "id": id_, "data_pagamento": data, "protocollo_telematico": protocollo,
        "sezione_erario": list(erario), "sezione_regioni": list(regioni),
        "sezione_tributi_locali": list(locali), "sezione_inps": [],
        "totali": {"saldo_netto_cents": saldo}, "f24_associati": [], **kw,
    }


def _ritenuta(id_, fornitore, data_fattura, cents, numero="1"):
    periodo = data_fattura[:7]
    anno, mese = int(periodo[:4]), int(periodo[5:7]) + 1
    if mese == 13:
        anno, mese = anno + 1, 1
    return {"id": id_, "fattura_id": f"fatt-{id_}", "numero_fattura": numero, "fornitore": fornitore,
            "data_fattura": data_fattura, "periodo_ritenuta": periodo, "importo_cents": cents,
            "importo": f"{cents / 100:.2f}", "scadenza": f"{anno}-{mese:02d}-16"}


def _db(quietanze=(), f24=(), ritenute=()):
    db = AsyncMongoMockClient()["tributi"]
    if quietanze:
        run(db["quietanze_f24"].insert_many([dict(q) for q in quietanze]))
    if f24:
        run(db["f24_unificato"].insert_many([dict(f) for f in f24]))
    if ritenute:
        run(db["ritenute_acconto"].insert_many([dict(r) for r in ritenute]))
    return db


# Quietanza del 16/04/2026: tre parcelle di marzo pagate con due righe 1040
# (210 + 490) e, nella stessa delega, il ravvedimento di 02/2025 e 09/2025.
Q_APRILE = _quietanza("q-apr", "2026-04-16", "26041535212746370/000001", erario=[
    _riga("1040", "03/2026", 49000), _riga("1040", "09/2025", 22194), _riga("1040", "02/2025", 21430),
    _riga("1040", "03/2026", 21000), _riga("8948", "02/2025", 750), _riga("8948", "09/2025", 688),
], ravvedimento_di=["f24-originale"])
Q_LUGLIO = _quietanza("q-lug", "2026-07-21", "26072135472143961/000001", erario=[
    _riga("1040", "06/2026", 28400), _riga("8948", "06/2026", 200),
])
Q_COMPENSATA = _quietanza("q-comp", "2026-05-18", "26051510373019398/000001", erario=[
    _riga("9001", "2023", 39510), _riga("6099", "2025", 0, 39510),
])

RITENUTE_MARZO = [
    _ritenuta("r-marotta", "STUDIO A", "2026-03-04", 21000),
    _ritenuta("r-puma", "STUDIO B", "2026-03-20", 28000),
    _ritenuta("r-ferrantini", "STUDIO C", "2026-03-25", 21000),
]


def _voce(voci, codice, periodo):
    return next(v for v in voci if v["codice"] == codice and v["periodo"] == periodo)


def test_voci_in_ordine_di_codice_con_colonne_separate():
    db = _db([Q_APRILE, Q_LUGLIO, Q_COMPENSATA], ritenute=RITENUTE_MARZO)
    dati = run(tributi.carica_voci(db))
    voci = dati["voci"]
    codici = [v["codice"] for v in voci]
    assert codici == sorted(codici, key=lambda c: (0 if c.isdigit() else 1, c.zfill(6)))

    marzo = _voce(voci, "1040", "03/2026")
    # Stessa delega del ravvedimento ma periodo senza sanzione: pagamento ordinario.
    assert marzo["quietanza_cents"] == 70000 and marzo["ravvedimento_cents"] == 0
    assert marzo["atteso_cents"] == 70000 and marzo["residuo_cents"] == 0
    assert marzo["stato"] == tributi.PAGATO
    assert {d["tipo"] for d in marzo["documenti"]} == {"quietanza", "ritenuta"}

    feb25 = _voce(voci, "1040", "02/2025")
    assert feb25["ravvedimento_cents"] == 21430 and feb25["stato"] == tributi.RAVVEDUTO
    sanzione = _voce(voci, "8948", "02/2025")
    assert sanzione["natura"] == "sanzione" and sanzione["stato"] == tributi.SANZIONE

    credito = _voce(voci, "6099", "2025")
    assert credito["credito_cents"] == 39510 and credito["stato"] == tributi.CREDITO
    compensazione = next(d for d in credito["documenti"] if d["tipo"] == "credito")
    assert compensazione["compensato_con"] == [{"codice": "9001", "periodo": "2023", "importo_cents": 39510}]


def test_il_modello_del_commercialista_non_pagato_resta_da_pagare():
    f24 = {"id": "f24-ago", "status": "da_pagare", "dati_generali": {"data_versamento": "2026-09-16"},
           "sezione_erario": [_riga("1001", "08/2026", 120000)], "totali": {"saldo_netto_cents": 120000}}
    voci = run(tributi.carica_voci(_db(f24=[f24])))["voci"]
    voce = _voce(voci, "1001", "08/2026")
    assert voce["inviato_cents"] == 120000 and voce["residuo_cents"] == 120000
    assert voce["stato"] in (tributi.DA_PAGARE, tributi.SCADUTO)
    assert voce["documenti"][0]["tipo"] == "commercialista"


def test_la_ritenuta_senza_f24_e_attesa_e_resta_da_pagare():
    rit = _ritenuta("r-ago", "STUDIO A", "2026-08-10", 31000)
    voci = run(tributi.carica_voci(_db(ritenute=[rit])))["voci"]
    voce = _voce(voci, "1040", "08/2026")
    assert voce["atteso_cents"] == 31000 and voce["residuo_cents"] == 31000
    assert voce["stato"] in (tributi.ATTESO, tributi.SCADUTO)
    r = tributi.riepilogo(voci, stato="APERTO")
    assert r["totali"]["residuo_cents"] == 31000


def test_la_quietanza_paga_le_ritenute_aggregate_e_avvisa_una_volta(monkeypatch):
    inviati = []

    async def finto_telegram(testo, *a, **k):
        inviati.append(testo)
        return True

    import app.services.telegram_notifications as tg
    monkeypatch.setattr(tg, "send_notification", finto_telegram)
    monkeypatch.setattr(rit_router, "GIORNI_AVVISO_VERSAMENTO", 100000)
    db = _db([Q_APRILE, Q_LUGLIO], ritenute=RITENUTE_MARZO + [_ritenuta("r-giu", "STUDIO A", "2026-06-04", 28400)])

    run(rit_router.riconcilia_ritenute_esistenti(db))
    puma = run(db["ritenute_acconto"].find_one({"id": "r-puma"}))
    assert puma["stato_obbligazione"] == "VERSATA"
    assert puma["stato"] == "pagata_puntuale"
    assert puma["quietanza_protocollo"] == "26041535212746370/000001"
    assert puma["f24_associazione_tipo"] == "aggregata"
    giugno = run(db["ritenute_acconto"].find_one({"id": "r-giu"}))
    assert giugno["stato"] == "pagata_con_ravvedimento" and giugno["data_pagamento"] == "2026-07-21"
    assert len(inviati) == 4 and all("Ritenuta pagata" in t for t in inviati)
    assert "26072135472143961/000001" in giugno["avviso_versamento_testo"]

    # Il secondo giro non riavvisa.
    run(rit_router.riconcilia_ritenute_esistenti(db))
    assert len(inviati) == 4


def test_due_quietanze_candidate_non_scelgono():
    doppia = _quietanza("q-bis", "2026-07-22", "26072299999999999/000001", erario=[_riga("1040", "06/2026", 28400)])
    db = _db([Q_LUGLIO, doppia], ritenute=[_ritenuta("r-giu", "STUDIO A", "2026-06-04", 28400)])
    run(rit_router.riconcilia_ritenute_esistenti(db))
    r = run(db["ritenute_acconto"].find_one({"id": "r-giu"}))
    assert r["stato"] == "da_verificare_associazione_f24"
    assert r.get("stato_obbligazione") != "VERSATA"


def test_ritenuta_con_importo_versato_diverso_dalle_fatture_non_e_pagata():
    quietanza = _quietanza("q-x", "2026-04-16", "26041500000000000/000001",
                           erario=[_riga("1040", "03/2026", 50000)])
    ritenute = [_ritenuta("r1", "Prof A", "2026-03-04", 21000, "1"),
                _ritenuta("r2", "Prof B", "2026-03-20", 28000, "2")]

    voci = run(tributi.carica_voci(_db(quietanze=[quietanza], ritenute=ritenute)))["voci"]
    voce = next(v for v in voci if v["codice"] == "1040" and v["mese"] == 3)

    assert voce["stato"] == "NON_TORNA" and voce["scarto_cents"] == 1000
    assert voce["atteso_cents"] == 49000 and voce["pagato_cents"] == 50000


def test_1040_versato_senza_fatture_in_archivio_chiede_di_associarle():
    quietanza = _quietanza("q-y", "2026-04-16", "26041500000000001/000001",
                           erario=[_riga("1040", "09/2025", 22194)])

    voci = run(tributi.carica_voci(_db(quietanze=[quietanza])))["voci"]
    voce = next(v for v in voci if v["codice"] == "1040")

    assert voce["fatture_da_associare"] is True and voce["stato"] == "PAGATO"
