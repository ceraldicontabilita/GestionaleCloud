"""Controlli incrociati: segnalano, non correggono, e non rinascono se ignorati."""
import asyncio
from datetime import date

from app.services import controlli_incrociati as ci
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

OGGI = date(2026, 9, 28)


def _run(coro):
    return asyncio.run(coro)


def _fattura(fid, numero, totale, fornitore, piva, data="2026-09-10"):
    return {"id": fid, "invoice_number": numero, "total_amount": totale, "supplier_name": fornitore,
            "supplier_vat": piva, "invoice_date": data, "status": "imported", "tipo_documento": "TD01"}


def test_stesso_soggetto_regge_troncamenti_inversioni_e_titoli():
    assert ci.beneficiario_della_causale(
        "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MBVT40187878/00110410 FAVORE Rosaria Marotta "
        "NOTPROVIDE - Rosaria Marotta fattura FPR 31/26") == "Rosaria Marotta"
    assert ci.stesso_soggetto("FABIANA CIERVO", "CIERVO FABIANA")
    assert ci.stesso_soggetto("ING. PUMA GIULIANO", "giuliano puma")
    assert ci.stesso_soggetto("L. MORELLI E FIGLIO", "L.MORELLI E FIGLIO S.R.L.")
    assert ci.stesso_soggetto("EDILIZIA SANTAMARIA IMPORT EXPORT S", "EDILIZIA SANTAMARIA IMPORT EXPORT SRL")
    assert not ci.stesso_soggetto("Mario Rossi", "Timas Ascensori S.r.l.")
    assert not ci.stesso_soggetto("Alfa Srl", "Beta Srl")


def test_giro_completo_segnala_e_non_riapre_gli_ignorati():
    async def scenario():
        db = ClientArchivioMemoria()["controlli_incrociati"]
        await db["invoices"].insert_many([
            _fattura("f1", "31/26", 500.0, "ROSARIA MAROTTA", "01111111111"),
            _fattura("f2", "77", 300.0, "TIMAS ASCENSORI SRL", "02222222222"),
            *[_fattura(f"a{i}", f"A{i}", 50.0, "AMAZON", "03333333333", data=f"2026-0{i}-05")
              for i in range(1, 8)],
            _fattura("big", "BIG", 401.0, "AMAZON", "03333333333", data="2026-09-20"),
        ])
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "m1", "data": "2026-09-12", "importo": -500.0, "fattura_id": "f1",
             "descrizione_originale": "VOSTRA DISPOSIZIONE FAVORE Rosaria Marotta NOTPROVIDE - fattura 31/26"},
            {"id": "m2", "data": "2026-09-12", "importo": -300.0, "fattura_id": "f2",
             "descrizione_originale": "VOSTRA DISPOSIZIONE FAVORE Mario Rossi NOTPROVIDE - saldo"},
        ])
        await db["prima_nota_banca"].insert_many([
            {"id": "p1", "fattura_id": "f2", "importo": -300.0, "data": "2026-09-12", "source": "riconciliazione"},
            {"id": "p2", "fattura_id": "f2", "importo": -300.0, "data": "2026-09-14", "source": "riconciliazione"},
            {"id": "p3", "fattura_id": "f1", "importo": -500.0, "data": "2026-09-12", "source": "riconciliazione"},
            {"id": "p4", "fattura_id": "f1", "importo": -500.0, "data": "2026-09-01", "source": "x", "status": "deleted"},
        ])
        primo = await ci.esegui_controlli(db, oggi=OGGI)
        alert = await db["alerts"].find({}, {"_id": 0}).to_list(None)
        codici = sorted((a["codice"], a["entita_id"]) for a in alert)
        # Il titolare ignora l'anomalia Amazon: al giro dopo non rinasce.
        await db["alerts"].update_one({"codice": "FAT_IMPORTO_ANOMALO"}, {"$set": {"stato": "ignorato"}})
        secondo = await ci.esegui_controlli(db, oggi=OGGI)
        return primo, codici, secondo

    primo, codici, secondo = _run(scenario())
    assert ("BNK_BENEFICIARIO_DIVERSO", "m2:f2") in codici
    assert not any(c == "BNK_BENEFICIARIO_DIVERSO" and e.startswith("m1") for c, e in codici)
    assert ("FAT_PAGATA_DUE_VOLTE", "f2") in codici
    assert ("FAT_PAGATA_DUE_VOLTE", "f1") not in codici
    assert ("FAT_IMPORTO_ANOMALO", "big") in codici
    assert primo["nuovi_alert"] >= 3
    assert secondo["nuovi_alert"] == 0


def test_copertura_estratti_mesi_mancanti_dal_primo_mese_della_fonte():
    async def scenario():
        db = ClientArchivioMemoria()["copertura"]
        await db["estratto_conto_movimenti"].insert_many(
            [{"id": f"b{m}", "data": f"2026-{m:02d}-10"} for m in (1, 2, 3, 5, 6, 7, 8)])
        await db["sumup_conto_movimenti"].insert_many(
            [{"id": "s1", "data": "2026-08-03"}])
        return await ci.copertura_estratti(db, oggi=OGGI)

    righe = {r["fonte"]: r for r in _run(scenario())}
    assert righe["bpm"]["mesi_mancanti"] == ["2026-04"]
    # SumUp esiste da agosto: prima non e' un buco; settembre non e' ancora chiuso.
    assert righe["sumup"]["mesi_mancanti"] == []
    assert righe["numia"]["mesi_mancanti"] == [] and righe["numia"]["dal"] is None
    assert righe["paypal"]["avvisa"] is False


def test_estratto_caricato_chiude_l_avviso_del_mese():
    async def scenario():
        db = ClientArchivioMemoria()["copertura_chiusura"]
        await db["estratto_conto_movimenti"].insert_many(
            [{"id": f"b{m}", "data": f"2026-{m:02d}-10"} for m in (1, 3)])
        primo = await ci.esegui_controlli(db, oggi=date(2026, 4, 15))
        await db["estratto_conto_movimenti"].insert_one({"id": "b2", "data": "2026-02-10"})
        secondo = await ci.esegui_controlli(db, oggi=date(2026, 4, 15))
        aperti = await db["alerts"].find({"stato": "aperto"}, {"_id": 0}).to_list(None)
        return primo, secondo, aperti

    primo, secondo, aperti = _run(scenario())
    assert primo["mesi_mancanti"]["bpm"] == ["2026-02"]
    assert secondo["alert_chiusi"] == 1
    assert not [a for a in aperti if a["codice"] == "ESTRATTO_MESE_MANCANTE"]


def test_rt_dimenticata_solo_in_mezzo_e_non_se_chiusa_col_giorno_dopo():
    async def scenario():
        db = ClientArchivioMemoria()["rt_dimenticata"]
        await db["corrispettivi"].insert_many([
            {"data": "2026-09-01", "pagato_elettronico": 100.0, "stato": "definitivo_xml"},
            # 02: nessuna chiusura (dimenticata). 03: chiusura normale.
            {"data": "2026-09-05", "pagato_elettronico": 200.0, "stato": "definitivo_xml"},
            # 04 senza chiusura ma coperto dalla chiusura del 05 (giorno dopo).
            {"data": "2026-09-03", "pagato_elettronico": 0.0, "pagato_contanti": 50.0,
             "stato": "definitivo_xml"},
            {"data": "2026-09-10", "pagato_elettronico": 80.0, "stato": "definitivo_xml"},
        ])
        await db["chiusure_pos_manuali"].insert_many([
            {"data": g, "importo": 70.0, "gestore": "sumup", "source": "api_sumup"}
            for g in ("2026-09-02", "2026-09-04", "2026-09-20")
        ])
        await db["chiusure_attivita"].insert_one(
            {"id": "c", "data_inizio": "2026-09-08", "data_fine": "2026-09-08"})
        await db["chiusure_pos_manuali"].insert_one(
            {"data": "2026-09-08", "importo": 10.0, "gestore": "sumup", "source": "api_sumup"})
        return await ci.controlla_rt_dimenticata(db, oggi=OGGI)

    giorni = [r["data"] for r in _run(scenario())]
    # 04 coperto dal 05, 08 chiusura dichiarata, 20 dopo l'ultimo corrispettivo (fonti ferme).
    assert giorni == ["2026-09-02"]
