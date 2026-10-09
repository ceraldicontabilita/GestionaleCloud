import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import consegna_hotel as ch
from app.lotti.servizi import ordini_hotel as oh

ORDINE = {
    "id": "OH-1", "struttura_id": "s1", "struttura_nome": "Hotel Prova", "stato": "pronto",
    "data_consegna": "2026-10-07", "ora_ritiro": "07:30", "totale": 6.0,
    "pagamento": "incassato", "pagamento_metodo": "borsellino", "nota": "Senza <fretta> & grazie",
    "righe": [{"nome": "Croissant Vuoto", "quantita": 4, "totale": 6.0, "allergeni": ["glutine"],
               "lotti_associati": [{"numero_lotto": "CROISSANT-VUOTO-20261007-100"}],
               "fatture_origine": [{"numero_fattura": "100", "data_fattura": "10/09/2026"}]}],
}


def test_pdf_valido_e_mail_mascherata():
    pdf = ch.costruisci_pdf(ORDINE, {"ragione_sociale": "Ceraldi Group", "indirizzo": "Napoli", "partita_iva": "1"})
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500
    assert ch.mascherata("vincenzo@gmail.com") == "vi***@gmail.com" and ch.mascherata("boh") == ""


def _prepara(monkeypatch, nome, email="alb@example.it"):
    db = AsyncMongoMockClient()[nome]
    for m in (ch, oh):
        monkeypatch.setattr(m, "db", db)
    inviati = []

    async def rpc(nome_rpc, args):
        return {"email": email}

    async def azienda():
        return {"ragione_sociale": "Ceraldi Group"}

    import app.hr.services.email_smtp as smtp
    import app.services.colazioni_notifiche as notif
    monkeypatch.setattr(notif, "_rpc_runtime", rpc)
    monkeypatch.setattr(smtp, "invia_email", lambda *a, **k: inviati.append(a))
    monkeypatch.setattr(ch, "get_azienda", azienda)
    return db, inviati


def test_consegna_segna_consegnato_e_invia_pdf(monkeypatch):
    db, inviati = _prepara(monkeypatch, "consegna_ok")

    async def prova():
        await db.ordini_hotel.insert_one(dict(ORDINE))
        e = await ch.consegna_e_invia("OH-1")
        assert e["email_inviata"] is True and e["a"] == "al***@example.it"
        assert e["ordine"]["stato"] == "consegnato" and e["ordine"]["consegna_pdf"]["inviato"] is True
        assert inviati[0][0] == "alb@example.it" and inviati[0][3][0][1:3] == ("application", "pdf")
        assert inviati[0][3][0][0].startswith(b"%PDF")
    asyncio.run(prova())


def test_senza_email_resta_consegnato_con_errore_leggibile(monkeypatch):
    db, inviati = _prepara(monkeypatch, "consegna_no_mail", email="")

    async def prova():
        await db.ordini_hotel.insert_one(dict(ORDINE))
        e = await ch.consegna_e_invia("OH-1")
        assert e["email_inviata"] is False and "email" in e["errore"] and not inviati
        assert e["ordine"]["stato"] == "consegnato"
        r = await ch.consegna_e_invia("OH-1", solo_pdf=True)  # rinvio: non cambia lo stato
        assert r["ordine"]["stato"] == "consegnato"
    asyncio.run(prova())
