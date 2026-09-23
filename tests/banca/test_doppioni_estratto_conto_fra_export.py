"""Lo stesso conto BPM esportato due volte con parole diverse non si raddoppia.

Il 23/09/2026 il CSV «Elenco entrate/uscite» ha reimportato gennaio–agosto,
gia' presente dal vecchio archivio: la banca scrive la categoria davanti
(«INC.POS CARTE CREDIT - …») e l'assegno come «PRELIEVO ASSEGNO … NUM:».
1.185 righe doppie, Prima Nota Banca e stipendi HR contati due volte.
"""
import asyncio

import pytest

from app.routers.bank import estratto_conto as modulo
from app.services import doppioni_estratto_conto as doppioni
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

BANCA = "05034 - BANCO BPM S.P.A."
FILE = doppioni.IMPORT_AUTORIZZATI[0]


def _vecchio(i, data, importo, descrizione, banca="BPM"):
    return {"id": f"old-{i}", "data": data, "importo": importo, "tipo": "uscita" if importo < 0 else "entrata",
            "descrizione": descrizione, "descrizione_originale": descrizione,
            "banca": banca, "fonte": "legacy_staging_2026"}


def _nuovo(i, data, importo, descrizione, file=FILE):
    return {"id": f"EC-new-{i}", "data": data, "importo": abs(importo),
            "tipo": "uscita" if importo < 0 else "entrata",
            "descrizione": descrizione, "descrizione_originale": descrizione,
            "banca": BANCA, "source_filename": file}


# ── accoppiamento ─────────────────────────────────────────────────────────

def test_prefisso_di_categoria_non_rende_diverso_il_movimento():
    coppie = doppioni.accoppia(
        [_nuovo(1, "2026-04-16", 0.01, "INC.POS CARTE CREDIT - REMUNERAZIONE DCC 03/26 PER PDV: 3757283/00012")],
        [_vecchio(1, "2026-04-16", 0.01, "REMUNERAZIONE DCC 03/26 PER PDV: 3757283/00012")],
    )
    assert [(n["id"], o["id"]) for n, o in coppie] == [("EC-new-1", "old-1")]


def test_stesso_assegno_scritto_in_due_modi_e_uno_solo():
    coppie = doppioni.accoppia(
        [_nuovo(1, "2026-01-07", -644.21, "PRELIEVO ASSEGNO - DM 03069 CRA: 01505649400103 NUM: 0208770635")],
        [_vecchio(1, "2026-01-07", -644.21, "VOSTRO ASSEGNO N. 0208770635")],
    )
    assert len(coppie) == 1


def test_due_assegni_con_numeri_diversi_non_si_accoppiano_mai():
    coppie = doppioni.accoppia(
        [_nuovo(1, "2026-01-07", -500.00, "PRELIEVO ASSEGNO - NUM: 0208770999")],
        [_vecchio(1, "2026-01-07", -500.00, "VOSTRO ASSEGNO N. 0208770635")],
    )
    assert coppie == []


def test_il_movimento_in_piu_nello_stesso_giorno_resta_nuovo():
    """Tre commissioni da 1,10 nell'archivio, quattro nel CSV: una e' vera."""
    vecchi = [_vecchio(i, "2026-01-07", -1.10, f"NS RIF. MB0B9711{i} SPESE E COMM.") for i in range(3)]
    nuovi = [_nuovo(i, "2026-01-07", -1.10, f"COMM.SU BONIFICI - NS RIF. MB0B9711{i} SPESE E COMM.")
             for i in range(4)]
    coppie = doppioni.accoppia(nuovi, vecchi)
    assert len(coppie) == 3
    assert {o["id"] for _, o in coppie} == {"old-0", "old-1", "old-2"}


def test_stesso_giorno_e_importo_vince_il_riferimento_della_banca():
    """Collaudo API Banco BPM ↔ CSV del 23/09/2026: in ordine le due
    commissioni da 1,10 del 14/08 finivano incrociate."""
    vecchi = [
        _vecchio(1, "2026-08-14", -1.10, "COMM.SU BONIFICI - RIF.MBVT40187878 COMM.BON. TELEMATICO SCT/IST"),
        _vecchio(2, "2026-08-14", -1.10, "COMM.SU BONIFICI - RIF.MBVT40188610 COMM.BON. TELEMATICO SCT/IST"),
    ]
    nuovi = [
        _nuovo(1, "2026-08-14", -1.10, "COMM.SU BONIFICI - RIF.MBVT40188610 COMM.BON. TELEMATICO SCT/ IST"),
        _nuovo(2, "2026-08-14", -1.10, "COMM.SU BONIFICI - RIF.MBVT40187878 COMM.BON. TELEMATICO SCT/ IST"),
    ]
    coppie = doppioni.accoppia(nuovi, vecchi)
    assert sorted((n["id"], o["id"]) for n, o in coppie) == [("EC-new-1", "old-2"), ("EC-new-2", "old-1")]


def test_codice_spezzato_da_uno_spazio_e_lo_stesso():
    api = _nuovo(1, "2026-07-02", 59.48, "BONIF. VS. FAVORE - BON.DA AMAZON PAYMENTS EUROPE S.C.A. AMAZON 1 "
                 "71-0500632-9988359 AMZN Mktp IT 2AD9AH9EL9S1C NR. BONIFICO SEPA: MB0B8325")
    altro = _vecchio(1, "2026-07-02", 59.48, "BONIF. VS. FAVORE - BON.DA AMAZON PAYMENTS EUROPE S.C.A. AMAZON - "
                     "171-0500632-9988359 AMZN Mktp IT 5LETHEEYYFCOQL92")
    giusto = _vecchio(2, "2026-07-02", 59.48, "BONIF. VS. FAVORE - BON.DA AMAZON PAYMENTS EUROPE S.C.A. AMAZON - "
                      "171-0500632-9988359 AMZN Mktp IT 2AD9AH9EL9S1C8CO")
    assert [(n["id"], o["id"]) for n, o in doppioni.accoppia([api], [altro, giusto])] == [("EC-new-1", "old-2")]
    paypal_api = _nuovo(2, "2026-08-17", 7.80, "BONIF. VS. FAVORE - BON.DA PayPal Europe S.a.r.l. et Cie S.C.A "
                        "YY W1052371461387/PAYPAL NR. BONIFICO SEPA: MB0B05044174")
    paypal_csv = _vecchio(3, "2026-08-17", 7.80, "BONIF. VS. FAVORE - BON.DA PayPal Europe S.a.r.l. et Cie S.C.A - "
                          "YYW1052371461387/PAYPAL")
    assert doppioni.stesso_riferimento(paypal_api, paypal_csv)


def test_numeri_di_sole_cifre_non_sono_un_riferimento():
    """Il numero d'ordine Amazon e le date li condividono operazioni diverse."""
    a = _vecchio(1, "2026-07-02", 59.48, "AMAZON 171-0500632-9988359 DEL 20/07/2026")
    b = _vecchio(2, "2026-07-02", 59.48, "AMAZON 171-0500632-9988359 DEL 20/07/2026 ALTRO")
    assert not doppioni.stesso_riferimento(a, b)


def test_segno_e_conto_diversi_non_si_accoppiano():
    carta = _vecchio(1, "2026-02-01", -30.00, "AMAZON", banca="Nexi")
    entrata = _vecchio(2, "2026-02-01", 30.00, "AMAZON")
    assert doppioni.accoppia([_nuovo(1, "2026-02-01", -30.00, "AMAZON")], [carta, entrata]) == []


# ── import: il CSV non raddoppia l'archivio ────────────────────────────────

INTESTAZIONE = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;"
                "Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag")


def _riga_csv(descrizione, importo, data):
    return (f"CERALDI GROUP S.R.L.;{data};{data};{BANCA};5462;"
            f"{importo};EUR;{descrizione};;")


class _File:
    skip_duplicate_repairs = True

    def __init__(self, contenuto, filename="ElencoEntrateUsciteAndamento.csv"):
        self.filename = filename
        self._contenuto = contenuto

    async def read(self):
        return self._contenuto


def test_import_csv_riconosce_i_movimenti_del_vecchio_archivio(monkeypatch):
    db = ClientArchivioMemoria()["import_fra_export"]
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db["estratto_conto_movimenti"].insert_one(
            _vecchio(1, "2026-04-16", 0.01, "REMUNERAZIONE DCC 03/26 PER PDV: 3757283/00012"))
        await db["estratto_conto_movimenti"].insert_one(
            _vecchio(2, "2026-01-07", -644.21, "VOSTRO ASSEGNO N. 0208770635"))
        csv = "\r\n".join([
            INTESTAZIONE,
            _riga_csv("INC.POS CARTE CREDIT - REMUNERAZIONE DCC 03/26 PER PDV: 3757283/00012",
                      "0,01", "16/04/2026"),
            _riga_csv("PRELIEVO ASSEGNO - DM 03069 NUM: 0208770635", "-644,21", "07/01/2026"),
            _riga_csv("VOSTRA DISPOSIZIONE - BONIFICO A ROSSI", "-250,00", "10/09/2026"),
        ]).encode("utf-8")
        esito = await modulo.import_estratto_conto(_File(csv))
        righe = await db["estratto_conto_movimenti"].find({}).to_list(100)
        return esito, righe

    esito, righe = asyncio.run(scenario())
    assert len(righe) == 3  # due vecchie + il solo bonifico di settembre
    assert esito["stats"]["nuovi"] == 1
    assert esito["stats"]["duplicati"] == 2


# ── pulizia dei doppioni gia' entrati ───────────────────────────────────────

@pytest.fixture()
def archivio(monkeypatch):
    db = ClientArchivioMemoria()["pulizia_doppioni"]

    async def senza_hr():
        return None

    monkeypatch.setattr(
        "app.services.hr_pagamenti_deposito.carica_contesto_hr", senza_hr,
    )
    return db


def test_pulizia_mette_in_quarantena_e_storna_la_prima_nota(archivio):
    async def scenario():
        db = archivio
        await db["estratto_conto_movimenti"].insert_one(
            _vecchio(1, "2026-04-16", 0.01, "REMUNERAZIONE DCC 03/26 PER PDV: 3757283/00012"))
        await db["estratto_conto_movimenti"].insert_one(
            _nuovo(1, "2026-04-16", 0.01, "INC.POS CARTE CREDIT - REMUNERAZIONE DCC 03/26 PER PDV: 3757283/00012"))
        await db["estratto_conto_movimenti"].insert_one(
            _nuovo(2, "2026-09-10", -250.00, "VOSTRA DISPOSIZIONE - BONIFICO A ROSSI"))
        await db["prima_nota_banca"].insert_one({
            "id": "pn-doppia", "estratto_conto_id": "EC-new-1", "importo": 0.01,
            "source": "export_bancario_operativo",
        })
        await db["prima_nota_banca"].insert_one({
            "id": "pn-vera", "estratto_conto_id": "EC-new-2", "importo": 250.0,
        })
        anteprima = await doppioni.ripulisci_import(db, FILE, dry_run=True)
        fatto = await doppioni.ripulisci_import(db, FILE, dry_run=False)
        ancora = await doppioni.ripulisci_import(db, FILE, dry_run=False)
        ec = {r["id"] for r in await db["estratto_conto_movimenti"].find({}).to_list(10)}
        quarantena = await db["estratto_conto_movimenti_quarantena"].find({}).to_list(10)
        pn = {r["id"]: r for r in await db["prima_nota_banca"].find({}).to_list(10)}
        return anteprima, fatto, ancora, ec, quarantena, pn

    anteprima, fatto, ancora, ec, quarantena, pn = asyncio.run(scenario())
    assert anteprima["doppioni"] == 1 and anteprima["dry_run"] is True
    assert fatto["doppioni"] == 1 and fatto["movimenti_nuovi_veri"] == 1
    assert ec == {"old-1", "EC-new-2"}
    assert [q["duplicato_di"] for q in quarantena] == ["old-1"]
    assert pn["pn-doppia"]["status"] == "deleted"
    assert pn["pn-vera"].get("status") != "deleted"
    assert ancora["doppioni"] == 0  # idempotente


def test_pulizia_toglie_gli_esiti_stipendio_nati_dal_doppione(monkeypatch):
    from app.services import hr_pagamenti_deposito as hr

    db = ClientArchivioMemoria()["pulizia_hr"]
    db_hr = ClientArchivioMemoria()["pulizia_hr_hr"]
    ricalcolati = []

    async def contesto():
        esiti = await db_hr.pagamenti_esiti.find({}, {"_id": 0}).to_list(10)
        return hr.ContestoHR(db_hr, {}, esiti, set())

    async def ricalcola(ctx):
        ricalcolati.extend(sorted(ctx.periodi_toccati))

    monkeypatch.setattr(hr, "carica_contesto_hr", contesto)
    monkeypatch.setattr(hr, "_ricalcola_periodi", ricalcola)

    async def scenario():
        await db["estratto_conto_movimenti"].insert_one(
            _vecchio(1, "2026-01-12", -300.00, "VS.DISP. RIF. MB0B00058555 FAVORE ROSSI"))
        await db["estratto_conto_movimenti"].insert_one(
            _nuovo(1, "2026-01-12", -300.00, "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B00058555 FAVORE ROSSI"))
        await db_hr.pagamenti_esiti.insert_one({
            "id": "pe-vero", "key": "ecm:old-1", "dipendente_id": "d1", "mese": 1, "anno": 2026})
        await db_hr.pagamenti_esiti.insert_one({
            "id": "pe-doppio", "key": "ecm:EC-new-1", "dipendente_id": "d1", "mese": 1, "anno": 2026})
        await db_hr.bonifici_da_associare.insert_one({
            "id": "coda-doppia", "gestionale_movimento_id": "EC-new-1"})
        esito = await doppioni.ripulisci_import(db, FILE, dry_run=False)
        rimasti = [e["id"] for e in await db_hr.pagamenti_esiti.find({}).to_list(10)]
        coda = await db_hr.bonifici_da_associare.find({}).to_list(10)
        return esito, rimasti, coda

    esito, rimasti, coda = asyncio.run(scenario())
    assert esito["hr"] == {"esiti_stipendio": 1, "bonifici_da_associare": 1}
    assert rimasti == ["pe-vero"]
    assert coda == []
    assert ricalcolati == [("d1", 2026, 1)]
