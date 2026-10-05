import asyncio
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import ordini_hotel as servizio
from app.routers import colazioni


def test_endpoint_usa_catalogo_autorizzato_e_non_un_prezzo_del_browser(monkeypatch):
    db = AsyncMongoMockClient()["endpoint_ordini_hotel_test"]
    monkeypatch.setattr(servizio, "db", db)

    async def contesto(_sid, _token):
        return ({
            "interno:p1": {
                "chiave": "interno:p1", "origine": "produzione_interna",
                "nome": "Sfogliatella", "prezzo": 2.4, "allergeni": ["Glutine"],
            }
        }, {"struttura": {"nome": "Hotel Centro"}})

    monkeypatch.setattr(colazioni, "_contesto_ordine_albergatore", contesto)
    domani = servizio.prima_consegna_possibile()
    richiesta = colazioni.OrdineHotelRequest(
        sid="hotel-1", p="sessione-opaca", data_consegna=domani, ora_ritiro="07:00",
        righe=[colazioni.RigaOrdineHotel(chiave="interno:p1", quantita=4)],
        nota="mattina", idempotenza="req-1",
    )

    risposta = asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta))

    assert risposta["ok"] is True
    assert risposta["ordine"]["struttura_nome"] == "Hotel Centro"
    assert risposta["ordine"]["totale"] == 9.6
    assert risposta["ordine"]["righe"][0]["prezzo_unitario"] == 2.4


def test_endpoint_rifiuta_prodotto_non_assegnato(monkeypatch):
    db = AsyncMongoMockClient()["endpoint_ordini_hotel_negato_test"]
    monkeypatch.setattr(servizio, "db", db)

    async def contesto(_sid, _token):
        return ({}, {"struttura": {"nome": "Hotel Centro"}})

    monkeypatch.setattr(colazioni, "_contesto_ordine_albergatore", contesto)
    domani = servizio.prima_consegna_possibile()
    richiesta = colazioni.OrdineHotelRequest(
        sid="hotel-1", p="sessione-opaca", data_consegna=domani, ora_ritiro="07:00",
        righe=[colazioni.RigaOrdineHotel(chiave="interno:non-autorizzato", quantita=1)],
    )

    try:
        asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
        assert "non disponibile" in str(getattr(exc, "detail", ""))
    else:
        raise AssertionError("Il prodotto non assegnato doveva essere rifiutato")


def test_ordine_pagato_dal_borsellino_e_segnato_incassato_e_rifiutato_se_il_saldo_manca(monkeypatch):
    db = AsyncMongoMockClient()["endpoint_ordini_hotel_borsellino_test"]
    monkeypatch.setattr(servizio, "db", db)

    async def contesto(_sid, _token):
        return ({"interno:p1": {"chiave": "interno:p1", "origine": "produzione_interna",
                                "nome": "Sfogliatella", "prezzo": 2.4, "allergeni": []}},
                {"struttura": {"nome": "Hotel Centro"}})

    chiamate = []
    saldo = {"v": 100}

    async def rpc(fn, args):
        chiamate.append((fn, args["priferimento"], args["pimporto"]))
        if fn == "bb_ordine_prodotti_addebita" and float(args["pimporto"]) > saldo["v"]:
            return {"errore": "Saldo insufficiente: servono 9.60 €, disponibili 5 €"}
        return {"ok": True, "saldo": saldo["v"] - float(args["pimporto"])}

    monkeypatch.setattr(colazioni, "_contesto_ordine_albergatore", contesto)
    monkeypatch.setattr(colazioni, "_rpc_runtime_bb", rpc)

    def richiesta(idem):
        return colazioni.OrdineHotelRequest(
            sid="hotel-1", p="x", data_consegna=servizio.prima_consegna_possibile(), ora_ritiro="07:30",
            pagamento_metodo="borsellino",
            righe=[colazioni.RigaOrdineHotel(chiave="interno:p1", quantita=4)], idempotenza=idem)

    risposta = asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta("a")))
    assert risposta["ordine"]["pagamento"] == "incassato"
    assert risposta["ordine"]["pagamento_metodo"] == "borsellino"
    assert risposta["ordine"]["ora_ritiro"] == "07:30"
    assert risposta["saldo"] == 90.4
    assert chiamate == [("bb_ordine_prodotti_addebita", risposta["ordine"]["id"], "9.60")]

    # la stessa richiesta ripetuta non addebita due volte
    asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta("a")))
    assert len(chiamate) == 1

    saldo["v"] = 5
    try:
        asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta("b")))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
        assert "Saldo insufficiente" in str(exc.detail)
    else:
        raise AssertionError("Con saldo insufficiente l'ordine doveva essere rifiutato")
    assert asyncio.run(servizio.lista_ordini({"idempotenza": "b"})) == []


def test_annullo_ordine_pagato_dal_borsellino_rimborsa_prima_di_annullare(monkeypatch):
    db = AsyncMongoMockClient()["endpoint_ordini_hotel_annullo_test"]
    monkeypatch.setattr(servizio, "db", db)
    asyncio.run(db.ordini_hotel.insert_one({
        "id": "OH-1", "struttura_id": "hotel-1", "stato": "ricevuto", "totale": 9.6,
        "pagamento": "incassato", "pagamento_metodo": "borsellino", "audit": []}))
    chiamate = []

    async def rpc(fn, args):
        chiamate.append((fn, args["psid"], args["pimporto"], args["priferimento"]))
        return {"ok": True}

    monkeypatch.setattr(colazioni, "_rpc_runtime_bb", rpc)
    ordine = asyncio.run(colazioni.aggiorna_ordine_prodotti_titolare(
        "OH-1", colazioni.AggiornaOrdineHotelRequest(stato="annullato"), _admin={}))
    assert ordine["ordine"]["stato"] == "annullato"
    assert chiamate == [("bb_ordine_prodotti_rimborsa", "hotel-1", "9.60", "OH-1")]


def test_ordine_nuovo_avvisa_telegram_non_silenzioso_e_email_ma_la_ripetizione_no(monkeypatch):
    from app.services import colazioni_ordini_notifiche as notifiche

    db = AsyncMongoMockClient()["endpoint_ordini_hotel_avviso_test"]
    monkeypatch.setattr(servizio, "db", db)

    async def contesto(_sid, _token):
        return ({"interno:p1": {"chiave": "interno:p1", "origine": "produzione_interna",
                                "nome": "Sfogliatella", "prezzo": 2.4, "allergeni": []}},
                {"struttura": {"nome": "Hotel Centro"}})

    avvisi = []
    monkeypatch.setattr(colazioni, "_contesto_ordine_albergatore", contesto)
    monkeypatch.setattr(colazioni, "avvisa_in_background", lambda o: avvisi.append(o["id"]))

    def richiesta():
        return colazioni.OrdineHotelRequest(
            sid="hotel-1", p="x", data_consegna=servizio.prima_consegna_possibile(), ora_ritiro="07:00",
            righe=[colazioni.RigaOrdineHotel(chiave="interno:p1", quantita=2)], idempotenza="avviso-1")

    primo = asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta()))
    asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta()))
    assert avvisi == [primo["ordine"]["id"]]


def test_avviso_ordine_manda_telegram_con_push_e_email_al_bar_e_un_guasto_non_ferma_l_altro(monkeypatch):
    import asyncio as _a

    from app.services import colazioni_ordini_notifiche as n

    ordine = {"id": "OH-X1", "struttura_nome": "Hotel <enzo>", "data_consegna": "2026-10-07", "ora_ritiro": "07:00",
              "totale": 10.0, "pagamento_metodo": "borsellino", "nota": "reception",
              "righe": [{"nome": "Croissant", "quantita": 2, "totale": 5.0}]}
    inviati = {}

    async def telegram(testo, disable_notification=True, **k):
        inviati["telegram"] = (testo, disable_notification)
        return {"success": True}

    def posta(dest, oggetto, corpo, *a, **k):
        inviati["email"] = (dest, oggetto, corpo)

    async def dest():
        return "bar@esempio.it"

    monkeypatch.setattr(n, "is_configured", lambda: True)
    monkeypatch.setattr(n, "send_notification", telegram)
    monkeypatch.setattr(n, "_destinatario_bar", dest)
    import app.hr.services.email_smtp as smtp
    monkeypatch.setattr(smtp, "invia_email", posta)

    esito = _a.run(n.notifica_ordine_prodotti(ordine))
    assert esito == {"telegram": True, "email": True}
    testo, silenziosa = inviati["telegram"]
    assert silenziosa is False and "Hotel &lt;enzo&gt;" in testo and "PAGATO dal borsellino" in testo and "07/10/2026" in testo
    assert inviati["email"][0] == "bar@esempio.it" and "OH-X1" in inviati["email"][1] and "2× Croissant" in inviati["email"][2]

    async def telegram_ko(*a, **k):
        raise RuntimeError("rete")

    monkeypatch.setattr(n, "send_notification", telegram_ko)
    inviati.clear()
    esito = _a.run(n.notifica_ordine_prodotti(ordine))
    assert esito == {"telegram": False, "email": True} and "email" in inviati
