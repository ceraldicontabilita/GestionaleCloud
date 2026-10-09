"""Il report fatture del titolare dice come ha pagato: diventa Prima Nota.

Il titolare aggiunge al report «Fatture ricevute» il metodo con cui ha pagato
ogni fattura e il numero dell'assegno. Questi test provano che:
- la cassa dichiarata diventa la riga vera, riusando quella d'ufficio;
- la cassa d'ufficio si storna se il titolare ha pagato in banca;
- due fatture pagate con lo stesso assegno si collegano al suo addebito;
- una fattura non pagata o pagata con SumUp non entra in cassa;
- il metodo del fornitore si ricava (uno solo → quello, piu' → misto);
- il secondo giro non registra niente (idempotenza).
"""
import asyncio
import io

import pandas as pd
import pytest

from app.database import Database
from app.services import fatture_report_ae as report_ae
from app.services import pagamenti_dichiarati_titolare as pagamenti
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.prima_nota_integrity import (
    fatture_senza_pagamento_contabile_confermato,
)

SIRO = "04104640612"
KIMBO = "01238591216"
LEASYS = "06714021000"
VANDE = "02644480994"


def _riga(numero, piva, fornitore, data, totale, metodo, pagamenti_col="Pagata",
          assegno="", carta="", nome_file=None):
    return {
        "Numero": numero,
        "Nome file": nome_file or f"IT{piva}_{numero.replace('/', '')}.xml",
        "ID SdI": "",
        "Data documento": data,
        "metodo di pagamento canonico": metodo,
        "carta di credito": carta,
        "assegno numero ": assegno,
        "Fornitore": fornitore,
        "P.IVA": piva,
        "Metodo di pagamento": "MP01 - Contanti",
        "Totale documento": totale,
        "Netto a pagare": totale,
        "Pagamenti": pagamenti_col,
        "Data pagamento": "",
    }


def _xlsx(righe) -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(righe).to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def _fattura(fid, numero, piva, fornitore, data, totale, **extra):
    return {
        "id": fid, "invoice_number": numero, "supplier_vat": piva,
        "supplier_name": fornitore, "invoice_date": data, "total_amount": totale,
        "tipo_documento": "TD01", "status": "imported", "stato_import": "attivo",
        "filename": f"IT{piva}_{numero.replace('/', '')}.xml", **extra,
    }


RIGHE = [
    _riga("2/838", SIRO, "SIRO S.R.L.", "2026-02-10", 145.09, "cassa"),
    _riga("1/778", SIRO, "SIRO S.R.L.", "2026-02-12", 18.15, "ASSEGNO", assegno="334-07"),
    _riga("2/1485", SIRO, "SIRO S.R.L.", "2026-02-12", 121.37, "assegno", assegno="334-07"),
    _riga("L-1", LEASYS, "Leasys Italia S.p.A", "2026-03-01", 1119.48, "banca"),
    _riga("K-9", KIMBO, "KIMBO S.P.A.", "2026-03-02", 249.49, "cassa",
          pagamenti_col="Non pagata"),
    _riga("V-1", VANDE, "Vandemoortele Europe NV", "2026-03-03", 306.06, "sumup"),
    _riga("V-2", VANDE, "Vandemoortele Europe NV", "2026-03-04", 40.00, "banca",
          carta="CARTA DI CREDITO"),
    _riga("K-10", KIMBO, "KIMBO S.P.A.", "2026-03-05", 99.00, "cassa"),
]


async def _prepara(db):
    for f in (
        _fattura("f-siro-cassa", "2/838", SIRO, "SIRO S.R.L.", "2026-02-10", 145.09,
                 prima_nota_cassa_id="pn-ufficio-1", prima_nota_tipo="cassa_provvisoria"),
        _fattura("f-siro-a1", "1/778", SIRO, "SIRO S.R.L.", "2026-02-12", 18.15),
        _fattura("f-siro-a2", "2/1485", SIRO, "SIRO S.R.L.", "2026-02-12", 121.37),
        _fattura("f-leasys", "L-1", LEASYS, "Leasys Italia S.p.A", "2026-03-01", 1119.48,
                 prima_nota_cassa_id="pn-ufficio-2"),
        _fattura("f-kimbo", "K-9", KIMBO, "KIMBO S.P.A.", "2026-03-02", 249.49),
        _fattura("f-vande", "V-1", VANDE, "Vandemoortele Europe NV", "2026-03-03", 306.06),
        _fattura("f-vande-carta", "V-2", VANDE, "Vandemoortele Europe NV", "2026-03-04", 40.00),
        # Copia archiviata dalla dedup: non deve ricevere il pagamento.
        _fattura("f-siro-cassa-archiviata", "2/838", SIRO, "SIRO S.R.L.", "2026-02-10",
                 145.09, status="archived", filename="copia.xml"),
    ):
        await db["invoices"].insert_one(f)
    for pn_id, fid, importo in (("pn-ufficio-1", "f-siro-cassa", 145.09),
                                ("pn-ufficio-2", "f-leasys", 1119.48)):
        await db["prima_nota_cassa"].insert_one({
            "id": pn_id, "fattura_id": fid, "riferimento": f"FATT-{fid}",
            "importo": importo, "tipo": "uscita", "data": "2026-02-10",
            "source": "metodo_fornitore_assente_provvisorio", "provvisorio": True,
            "stato": "DA_VERIFICARE", "canonico": False,
        })
    for nome, piva in (("SIRO S.R.L.", SIRO), ("Leasys Italia S.p.A", LEASYS),
                       ("KIMBO S.P.A.", KIMBO), ("Vandemoortele Europe NV", VANDE)):
        await db["fornitori"].insert_one({
            "id": f"forn-{piva}", "ragione_sociale": nome, "partita_iva": piva,
        })
    # L'assegno 0208770334 da 139,52 = 18,15 + 121,37 e' gia' in banca.
    movimento = {
        "id": "ec-assegno-334", "data": "2026-02-20", "tipo": "uscita",
        "importo": -139.52, "causale": "VOSTRO ASSEGNO N. 0208770334",
        "descrizione": "VOSTRO ASSEGNO N. 0208770334", "riconciliato": True,
        "assegno_numero": "0208770334",
    }
    await db["estratto_conto_movimenti"].insert_one(dict(movimento))
    # Un altro assegno con le stesse cifre finali ma importo diverso: non e' lui.
    await db["estratto_conto_movimenti"].insert_one({
        **{k: v for k, v in movimento.items() if k != "_id"}, "id": "ec-assegno-altro", "importo": -50.0,
        "causale": "VOSTRO ASSEGNO N. 0208761334",
        "descrizione": "VOSTRO ASSEGNO N. 0208761334", "assegno_numero": "0208761334",
    })
    await db["assegni"].insert_one({
        "id": "ass-334", "numero": "0208770334", "importo": 139.52,
        "stato": "incassato", "data": "2026-02-20", "data_incasso": "2026-02-20",
        "movimento_id": "ec-assegno-334",
        "movimento_estratto_conto_id": "ec-assegno-334",
        "evidenza_bancaria_ufficiale": True, "incassato_confermato_banca": True,
    })


@pytest.fixture()
def db(monkeypatch):
    database = ClientArchivioMemoria()["test_pagamenti_dichiarati"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: database))
    return database


def _importa_e_applica(db):
    async def scenario():
        await _prepara(db)
        esito_import = await report_ae.importa_report_fatture_ricevute(
            db, _xlsx(RIGHE), "fatture_pagate_2026.xlsx",
        )
        primo = await pagamenti.applica_pagamenti_dichiarati(db)
        secondo = await pagamenti.applica_pagamenti_dichiarati(db)
        return esito_import, primo, secondo
    return asyncio.run(scenario())


def test_normalizza_le_parole_del_titolare():
    n = pagamenti.normalizza_metodo_titolare
    assert n("ASSEGNO") == "assegno"
    assert n("cassa") == "cassa"
    assert n("banca", "CARTA DI CREDITO") == "carta"
    assert n("sumup") == "sumup"
    assert n("paypal") == "paypal"
    assert n("") == ""
    assert pagamenti.cifre_assegno("334-07") == "334"
    assert pagamenti.cifre_assegno(481.0) == "481"
    assert pagamenti.cifre_assegno("9486") == "9486"
    assert pagamenti.cifre_assegno("7") == ""


def test_metodo_fornitore_da_quelli_dichiarati():
    assert pagamenti.metodo_fornitore({"cassa"}) == "cassa"
    assert pagamenti.metodo_fornitore({"assegno", "banca", "carta"}) == "banca"
    assert pagamenti.metodo_fornitore({"cassa", "assegno"}) == "misto"
    assert pagamenti.metodo_fornitore(set()) == ""


def test_import_conserva_le_colonne_del_titolare(db):
    esito, _, _ = _importa_e_applica(db)
    assert esito["pagamenti_dichiarati"] == len(RIGHE)
    righe = asyncio.run(db["fatture_report_ae"].find({}, {"_id": 0}).to_list(100))
    per_numero = {r["numero_fattura"]: r for r in righe}
    assert per_numero["1/778"]["assegno_numero_titolare"] == "334-07"
    assert per_numero["V-2"]["metodo_pagamento_titolare"] == "carta"
    assert per_numero["K-9"]["pagata_titolare"] is False
    # L'aggancio va alla fattura attiva, mai alla copia archiviata.
    assert per_numero["2/838"]["invoice_id"] == "f-siro-cassa"


def test_cassa_dichiarata_conferma_la_riga_d_ufficio_senza_duplicarla(db):
    _, primo, _ = _importa_e_applica(db)
    righe = asyncio.run(db["prima_nota_cassa"].find(
        {"fattura_id": "f-siro-cassa"}, {"_id": 0}).to_list(10))
    assert len(righe) == 1
    riga = righe[0]
    assert riga["id"] == "pn-ufficio-1"
    assert riga["source"] == "conferma_provvisori"
    assert riga["provvisorio"] is False
    assert "stato" not in riga
    fattura = asyncio.run(db["invoices"].find_one({"id": "f-siro-cassa"}))
    assert fattura["stato_pagamento"] == "pagata"
    assert fattura["data_pagamento"] == "2026-02-10"
    assert primo["conteggi"]["registrata"] >= 1


def test_banca_dichiarata_storna_la_cassa_d_ufficio_e_va_in_prima_nota_banca(db):
    _importa_e_applica(db)
    riga = asyncio.run(db["prima_nota_cassa"].find_one({"id": "pn-ufficio-2"}))
    assert riga["status"] == "deleted"
    assert riga["deleted_reason"].endswith("pagata_con_banca")
    fattura = asyncio.run(db["invoices"].find_one({"id": "f-leasys"}))
    # Pagata per il titolare, in attesa del movimento che lo provi.
    assert fattura["pagato"] is True
    assert fattura["stato_pagamento"] == "pagata"
    assert fattura["in_attesa_riscontro_banca"] is True
    assert fattura["metodo_pagamento_dichiarato"] == "banca"
    righe = asyncio.run(db["prima_nota_banca"].find(
        {"fattura_id": "f-leasys", "status": {"$nin": ["deleted", "archived"]}},
        {"_id": 0}).to_list(10))
    # Una sola riga, anche dopo il secondo giro.
    assert len(righe) == 1
    assert righe[0]["dichiarato_titolare"] is True
    assert righe[0]["importo"] == 1119.48
    assert fattura["prima_nota_banca_id"] == righe[0]["id"]
    # Non e' una prova bancaria: per i motori resta da riscontrare.
    assert asyncio.run(fatture_senza_pagamento_contabile_confermato(db, [fattura]))


def test_il_movimento_bancario_sostituisce_la_riga_dichiarata(db):
    from app.routers.prima_nota_module.sync import registra_pagamento_fattura

    _importa_e_applica(db)

    async def arriva_il_bonifico():
        await db["estratto_conto_movimenti"].insert_one({
            "id": "ec-leasys", "data": "2026-03-10", "tipo": "uscita",
            "importo": -1119.48, "descrizione": "SDD LEASYS ITALIA",
        })
        fattura = await db["invoices"].find_one({"id": "f-leasys"}, {"_id": 0})
        return await registra_pagamento_fattura(
            fattura, "banca", source="test",
            movimento_bancario={"id": "ec-leasys", "data": "2026-03-10"},
        )

    esito = asyncio.run(arriva_il_bonifico())
    assert esito["duplicato"] is False
    attive = asyncio.run(db["prima_nota_banca"].find(
        {"fattura_id": "f-leasys", "status": {"$nin": ["deleted", "archived"]}},
        {"_id": 0}).to_list(10))
    assert [r["id"] for r in attive] == [esito["banca"]]
    assert attive[0]["estratto_conto_id"] == "ec-leasys"
    # La riga nuova porta conto di tesoreria e contropartita CEE.
    assert attive[0]["conto_contabile"] == "19.01.01"
    assert attive[0]["conto_contropartita"] == "33.03.01"
    fattura = asyncio.run(db["invoices"].find_one({"id": "f-leasys"}))
    assert fattura["in_attesa_riscontro_banca"] is False
    assert not asyncio.run(fatture_senza_pagamento_contabile_confermato(db, [fattura]))
    # Il giro successivo la chiude (esito definitivo), senza riscriverla.
    giro = asyncio.run(pagamenti.applica_pagamenti_dichiarati(db, solo_pendenti=True))
    assert giro["conteggi"]["gia_pagata"] == 1


def test_un_pagamento_parziale_riduce_la_riga_dichiarata():
    from app.services.prima_nota_integrity import assorbi_righe_dichiarate

    database = ClientArchivioMemoria()["test_assorbi_parziale"]

    async def scenario():
        await database["invoices"].insert_one({"id": "f1", "in_attesa_riscontro_banca": True})
        await database["prima_nota_banca"].insert_one({
            "id": "dich", "fattura_id": "f1", "importo": 300.0,
            "dichiarato_titolare": True, "tipo": "uscita",
        })
        toccate = await assorbi_righe_dichiarate(
            database, {"f1": 100.0}, sostituita_da="prova-1", movimento_id="ec-1",
        )
        dopo_prima = await database["prima_nota_banca"].find_one({"id": "dich"})
        fattura_dopo_prima = await database["invoices"].find_one({"id": "f1"})
        await assorbi_righe_dichiarate(
            database, {"f1": 200.0}, sostituita_da="prova-2", movimento_id="ec-2",
        )
        return (toccate, dopo_prima, fattura_dopo_prima,
                await database["prima_nota_banca"].find_one({"id": "dich"}),
                await database["invoices"].find_one({"id": "f1"}))

    toccate, parziale, fattura_parziale, finale, fattura = asyncio.run(scenario())
    assert toccate == 1
    assert parziale["importo"] == 200.0 and parziale.get("status") != "deleted"
    assert fattura_parziale["in_attesa_riscontro_banca"] is True
    assert finale["status"] == "deleted" and finale["sostituita_da"] == "prova-2"
    assert fattura["in_attesa_riscontro_banca"] is False


def test_l_assegno_trovato_dopo_sostituisce_la_riga_dichiarata(db):
    async def scenario():
        await _prepara(db)
        # L'assegno 334 non e' ancora nell'estratto conto.
        assegno = await db["assegni"].find_one({"id": "ass-334"}, {"_id": 0})
        addebito = await db["estratto_conto_movimenti"].find_one(
            {"id": "ec-assegno-334"}, {"_id": 0})
        await db["assegni"].delete_one({"id": "ass-334"})
        await db["estratto_conto_movimenti"].delete_one({"id": "ec-assegno-334"})
        await report_ae.importa_report_fatture_ricevute(
            db, _xlsx(RIGHE), "fatture_pagate_2026.xlsx",
        )
        await pagamenti.applica_pagamenti_dichiarati(db)
        prima = await db["prima_nota_banca"].find(
            {"fattura_id": {"$in": ["f-siro-a1", "f-siro-a2"]},
             "status": {"$nin": ["deleted", "archived"]}}, {"_id": 0}).to_list(10)
        await db["assegni"].insert_one(assegno)
        await db["estratto_conto_movimenti"].insert_one(addebito)
        giro = await pagamenti.applica_pagamenti_dichiarati(db, solo_pendenti=True)
        dichiarate = await db["prima_nota_banca"].find(
            {"dichiarato_titolare": True, "fattura_id": {"$in": ["f-siro-a1", "f-siro-a2"]},
             "status": {"$nin": ["deleted", "archived"]}}, {"_id": 0}).to_list(10)
        fatture = await db["invoices"].find(
            {"id": {"$in": ["f-siro-a1", "f-siro-a2"]}}, {"_id": 0}).to_list(10)
        return prima, giro, dichiarate, fatture

    prima, giro, dichiarate, fatture = asyncio.run(scenario())
    assert sorted(r["importo"] for r in prima) == [18.15, 121.37]
    assert all(r["dichiarato_titolare"] for r in prima)
    assert giro["conteggi"].get("registrata") == 2
    assert dichiarate == []
    assert not asyncio.run(fatture_senza_pagamento_contabile_confermato(db, fatture))
    assert all(f["in_attesa_riscontro_banca"] is False for f in fatture)


def test_due_fatture_pagate_con_lo_stesso_assegno_vanno_sul_suo_addebito(db):
    _importa_e_applica(db)
    assegno = asyncio.run(db["assegni"].find_one({"id": "ass-334"}))
    collegate = {link["fattura_id"] for link in assegno["fatture_collegate"]}
    assert collegate == {"f-siro-a1", "f-siro-a2"}
    fatture = asyncio.run(db["invoices"].find(
        {"id": {"$in": ["f-siro-a1", "f-siro-a2"]}}, {"_id": 0}).to_list(10))
    assert not asyncio.run(fatture_senza_pagamento_contabile_confermato(db, fatture))


def test_non_pagata_e_sumup_non_entrano_in_cassa(db):
    _, primo, _ = _importa_e_applica(db)
    for fid in ("f-kimbo", "f-vande"):
        assert asyncio.run(db["prima_nota_cassa"].find_one({"fattura_id": fid})) is None
    vande = asyncio.run(db["invoices"].find_one({"id": "f-vande"}))
    assert vande["metodo_pagamento_dichiarato"] == "sumup"
    assert primo["conteggi"]["non_pagata"] == 1
    assert primo["conteggi"]["da_decidere"] == 1


def test_metodi_dei_fornitori_ricavati_dal_report(db):
    _importa_e_applica(db)
    metodo = {
        f["partita_iva"]: f.get("metodo_pagamento")
        for f in asyncio.run(db["fornitori"].find({}, {"_id": 0}).to_list(10))
    }
    assert metodo[SIRO] == "misto"        # cassa e assegni
    assert metodo[LEASYS] == "banca"
    assert metodo[KIMBO] == "cassa"       # anche la non pagata dice come paga
    assert metodo[VANDE] == "banca"       # SumUp e carta: mai contanti
    storico = asyncio.run(db["metodi_pagamento_storico"].find({}, {"_id": 0}).to_list(10))
    assert {s["attore"] for s in storico} == {"report_pagamenti_titolare"}


def test_fattura_arrivata_dopo_il_report_viene_chiusa_dal_giro_automatico(db):
    _, primo, secondo = _importa_e_applica(db)
    assert primo["conteggi"]["fattura_non_ancora_arrivata"] == 1  # K-10
    assert secondo["conteggi"].get("registrata", 0) == 0          # idempotente

    async def arriva():
        await db["invoices"].insert_one(
            _fattura("f-kimbo-10", "K-10", KIMBO, "KIMBO S.P.A.", "2026-03-05", 99.00))
        return await pagamenti.applica_pagamenti_dichiarati(db, solo_pendenti=True)

    giro = asyncio.run(arriva())
    # Ripassa anche le due in attesa della banca (Leasys e la carta): sono
    # gia' in Prima Nota Banca come dichiarate, e non si riscrivono.
    assert giro["conteggi"] == {"registrata": 1, "in_attesa_banca": 2}
    riga = asyncio.run(db["prima_nota_cassa"].find_one({"fattura_id": "f-kimbo-10"}))
    assert riga["importo"] == 99.0


def test_la_fattura_sparita_si_distingue_dall_xml_mai_arrivato_e_si_segnala(db):
    """La riga del report puntava a una fattura che `invoices` non ha piu':
    il giro la conta a parte, scrive UNA segnalazione e la espone nello stato."""
    async def scenario():
        await _prepara(db)
        await report_ae.importa_report_fatture_ricevute(db, _xlsx(RIGHE), "r.xlsx")
        # K-10 (XML mai arrivato) resta tale; la fattura di Leasys sparisce dall'archivio.
        await db["invoices"].delete_one({"id": "f-leasys"})
        primo = await pagamenti.applica_pagamenti_dichiarati(db)
        await db["sistema_stato"].update_one(
            {"chiave": pagamenti.CHIAVE_JOB},
            {"$set": {"chiave": pagamenti.CHIAVE_JOB, "stato": "completato"}}, upsert=True)
        stato = await pagamenti.stato(db)
        secondo = await pagamenti.applica_pagamenti_dichiarati(db, solo_pendenti=True)
        segnalazioni = await db["agenti_segnalazioni"].find(
            {"tipo": report_ae.TIPO_SEGNALAZIONE_FATTURE_SPARITE}, {"_id": 0}).to_list(10)
        riga = await db["fatture_report_ae"].find_one({"numero_fattura": "L-1"}, {"_id": 0})
        return primo, stato, secondo, segnalazioni, riga

    primo, stato, secondo, segnalazioni, riga = asyncio.run(scenario())
    assert primo["conteggi"]["fattura_non_ancora_arrivata"] == 2  # K-10 + Leasys
    assert primo["fatture_sparite"]["conteggio"] == 1
    motivi = {p["numero"]: p["motivo"] for p in primo["da_vedere"]}
    assert motivi["K-10"] == "XML non ancora nel gestionale"
    assert motivi["L-1"] == "fattura sparita da invoices (era f-leasys)"
    assert riga["fattura_sparita_id"] == "f-leasys" and riga["invoice_id"] is None
    assert riga["pagamento_applicato"]["stato"] == "fattura_non_ancora_arrivata"
    assert stato["fatture_sparite"]["conteggio"] == 1
    assert secondo["fatture_sparite"]["conteggio"] == 1
    assert len(segnalazioni) == 1 and segnalazioni[0]["occorrenze"] == 2
    assert segnalazioni[0]["risolta"] is False


def _esito(db, numero):
    return asyncio.run(db["fatture_report_ae"].find_one(
        {"numero_fattura": numero}, {"_id": 0}))


def test_un_esito_definitivo_senza_prova_si_ritira_con_storico_e_si_riapplica(db):
    """Il 06/10/2026 `invoices` e la Prima Nota sono state azzerate: gli esiti
    `registrata`/`da_decidere` del report restavano «fatti» per sempre e il
    giro non li ripassava piu'. L'esito orfano si ritira (storico, non
    cancellazione) e la riga torna applicabile; con la prova presente non si
    tocca; il secondo giro non ritira di nuovo; dry_run conta soltanto."""
    async def scenario():
        await _prepara(db)
        await report_ae.importa_report_fatture_ricevute(db, _xlsx(RIGHE), "r.xlsx")
        primo = await pagamenti.applica_pagamenti_dichiarati(db)
        integro = await pagamenti.ritira_esiti_orfani(db, dry_run=True)
        # Azzeramento: sparisce la fattura cassa con la sua riga di Prima Nota,
        # la fattura SumUp (da_decidere) e una delle due dell'assegno.
        for fid in ("f-siro-cassa", "f-vande", "f-siro-a1"):
            await db["invoices"].delete_one({"id": fid})
        await db["prima_nota_cassa"].delete_one({"id": "pn-ufficio-1"})
        prova = await pagamenti.applica_pagamenti_dichiarati(db, dry_run=True)
        riga_dopo_dry = await db["fatture_report_ae"].find_one(
            {"numero_fattura": "2/838"}, {"_id": 0})
        giro = await pagamenti.applica_pagamenti_dichiarati(db, solo_pendenti=True)
        secondo = await pagamenti.applica_pagamenti_dichiarati(db, solo_pendenti=True)
        return primo, integro, prova, riga_dopo_dry, giro, secondo

    primo, integro, prova, riga_dopo_dry, giro, secondo = asyncio.run(scenario())
    assert primo["esiti_ritirati"]["orfani"] == 0
    assert integro["orfani"] == 0 and integro["esaminati"] >= 4
    # Dry run: conta ma non scrive.
    assert prova["esiti_ritirati"] == {
        **prova["esiti_ritirati"], "orfani": 3, "ritirati": 0, "dry_run": True,
    }
    assert riga_dopo_dry["pagamento_applicato"]["stato"] == "registrata"
    assert "pagamento_applicato_storico" not in riga_dopo_dry
    # Giro vero: i tre orfani si ritirano, per stato e per metodo.
    ritirati = giro["esiti_ritirati"]
    assert ritirati["orfani"] == 3 and ritirati["ritirati"] == 3
    assert ritirati["per_stato"] == {"registrata": 2, "da_decidere": 1}
    assert ritirati["per_metodo"] == {"cassa": 1, "assegno": 1, "sumup": 1}
    assert ritirati["per_motivo"] == {"fattura_assente": 3}
    cassa = _esito(db, "2/838")
    assert cassa["pagamento_applicato"]["stato"] == "fattura_non_ancora_arrivata"
    # Lo stesso giro l'ha gia' ripassata: il motivo e' quello della fattura sparita.
    assert cassa["pagamento_applicato"]["motivo"] == "fattura sparita da invoices (era f-siro-cassa)"
    assert cassa["invoice_id"] is None and cassa["fattura_sparita_id"] == "f-siro-cassa"
    storico = cassa["pagamento_applicato_storico"]
    assert len(storico) == 1
    assert storico[0]["stato"] == "registrata"
    assert storico[0]["prima_nota_id"] == "pn-ufficio-1"
    assert storico[0]["ritirato_at"] and "non piu' presente" in storico[0]["motivo_ritiro"]
    assert "f-siro-cassa" in storico[0]["motivo_ritiro"]
    assert "pn-ufficio-1" in storico[0]["motivo_ritiro"]
    # La fattura dell'assegno rimasta in archivio tiene il suo esito.
    assert _esito(db, "2/1485")["pagamento_applicato"]["stato"] == "registrata"
    assert "pagamento_applicato_storico" not in _esito(db, "2/1485")
    # Secondo giro: niente da ritirare, lo storico non cresce.
    assert secondo["esiti_ritirati"]["orfani"] == 0
    assert len(_esito(db, "2/838")["pagamento_applicato_storico"]) == 1
    assert secondo["esiti_ritirati"]["esaminati"] == giro["esiti_ritirati"]["esaminati"] - 3

    # La fattura rientra dalla rilettura dell'XML con un id nuovo: il
    # pagamento dichiarato (cassa) si applica, riga di Prima Nota compresa.
    async def rientra():
        nuova = _fattura("f-siro-cassa-bis", "2/838", SIRO, "SIRO S.R.L.", "2026-02-10", 145.09)
        await db["invoices"].insert_one(dict(nuova))
        return await pagamenti.applica_pagamenti_dichiarati(db, solo_pendenti=True)

    giro_rientro = asyncio.run(rientra())
    assert giro_rientro["conteggi"]["registrata"] == 1
    riga_pn = asyncio.run(db["prima_nota_cassa"].find_one(
        {"fattura_id": "f-siro-cassa-bis", "status": {"$nin": ["deleted", "archived"]}}))
    assert riga_pn["importo"] == 145.09
    cassa = _esito(db, "2/838")
    assert cassa["pagamento_applicato"]["stato"] == "registrata"
    assert cassa["pagamento_applicato"]["prima_nota_id"] == riga_pn["id"]
    assert cassa["invoice_id"] == "f-siro-cassa-bis"
    assert len(cassa["pagamento_applicato_storico"]) == 1


def test_gia_pagata_con_fattura_sparita_si_ritira_e_lo_stato_la_conta(db):
    _importa_e_applica(db)  # il secondo giro completo marca 2/838 `gia_pagata`
    assert _esito(db, "2/838")["pagamento_applicato"]["stato"] == "gia_pagata"

    async def scenario():
        await db["invoices"].delete_one({"id": "f-siro-cassa"})
        await db["sistema_stato"].update_one(
            {"chiave": pagamenti.CHIAVE_JOB},
            {"$set": {"chiave": pagamenti.CHIAVE_JOB, "stato": "completato"}}, upsert=True)
        prima = await pagamenti.stato(db)
        giro = await pagamenti.applica_pagamenti_dichiarati(db, solo_pendenti=True)
        dopo = await pagamenti.stato(db)
        return prima, giro, dopo

    prima, giro, dopo = asyncio.run(scenario())
    assert prima["esiti_orfani"]["orfani"] == 1
    assert prima["esiti_orfani"]["per_stato"] == {"gia_pagata": 1}
    assert "ritirati" not in prima["esiti_orfani"]           # sola lettura
    assert giro["esiti_ritirati"]["per_stato"] == {"gia_pagata": 1}
    riga = _esito(db, "2/838")
    assert riga["pagamento_applicato"]["stato"] == "fattura_non_ancora_arrivata"
    assert riga["pagamento_applicato_storico"][0]["stato"] == "gia_pagata"
    assert dopo["esiti_orfani"]["orfani"] == 0


def test_riga_prima_nota_stornata_toglie_la_prova_all_esito_registrata(db):
    """Fattura ancora in archivio ma la riga di Prima Nota che l'esito cita
    non e' piu' attiva: l'esito `registrata` non e' piu' vero."""
    async def scenario():
        await _prepara(db)
        await report_ae.importa_report_fatture_ricevute(db, _xlsx(RIGHE), "r.xlsx")
        await pagamenti.applica_pagamenti_dichiarati(db)
        await db["prima_nota_cassa"].update_one(
            {"id": "pn-ufficio-1"}, {"$set": {"status": "deleted"}})
        return await pagamenti.ritira_esiti_orfani(db, dry_run=False)

    esito = asyncio.run(scenario())
    assert esito["orfani"] == 1 and esito["ritirati"] == 1
    assert esito["per_motivo"] == {"prima_nota_assente": 1}
    riga = _esito(db, "2/838")
    assert riga["pagamento_applicato"]["stato"] == "fattura_non_ancora_arrivata"
    assert riga["pagamento_applicato"]["esito_ritirato"] == "registrata"
    assert riga["pagamento_applicato"]["motivo"].startswith("esito ritirato: ")
    assert "pn-ufficio-1" in riga["pagamento_applicato_storico"][0]["motivo_ritiro"]


def test_l_arrivo_dell_xml_ritira_l_esito_orfano_senza_aspettare_il_giro(db):
    """La fattura rientra prima che il giro periodico sia passato: il ritiro
    avviene all'arrivo e il pagamento dichiarato si applica subito."""
    async def scenario():
        await _prepara(db)
        await report_ae.importa_report_fatture_ricevute(db, _xlsx(RIGHE), "r.xlsx")
        await pagamenti.applica_pagamenti_dichiarati(db)
        await db["invoices"].delete_one({"id": "f-siro-cassa"})
        await db["prima_nota_cassa"].delete_one({"id": "pn-ufficio-1"})
        nuova = _fattura("f-siro-cassa-bis", "2/838", SIRO, "SIRO S.R.L.", "2026-02-10", 145.09)
        await db["invoices"].insert_one(dict(nuova))
        esito = await pagamenti.applica_per_fattura_arrivata(db, nuova)
        return esito, await db["prima_nota_cassa"].find_one(
            {"fattura_id": "f-siro-cassa-bis", "status": {"$nin": ["deleted", "archived"]}})

    esito, riga_pn = asyncio.run(scenario())
    assert esito["applicate"] == 1
    assert riga_pn is not None and riga_pn["importo"] == 145.09
    riga = _esito(db, "2/838")
    assert riga["pagamento_applicato"]["stato"] == "registrata"
    assert riga["pagamento_applicato"]["prima_nota_id"] == riga_pn["id"]
    assert riga["invoice_id"] == "f-siro-cassa-bis"
    assert [s["stato"] for s in riga["pagamento_applicato_storico"]] == ["registrata"]
    # Le altre righe definitive dello stesso fornitore, con la prova, non si toccano.
    assert _esito(db, "2/1485")["pagamento_applicato"]["stato"] == "registrata"
    assert "pagamento_applicato_storico" not in _esito(db, "2/1485")


def test_la_cassa_d_ufficio_non_prova_un_pagamento():
    async def scenario():
        db = ClientArchivioMemoria()["test_cassa_ufficio"]
        await db["prima_nota_cassa"].insert_one({
            "id": "pn-1", "fattura_id": "f-1", "importo": 10.0,
            "source": "metodo_fornitore_assente_provvisorio",
        })
        fattura = {"id": "f-1", "total_amount": 10.0, "prima_nota_cassa_id": "pn-1"}
        return await fatture_senza_pagamento_contabile_confermato(db, [fattura])

    aperte = asyncio.run(scenario())
    assert [f["id"] for f in aperte] == ["f-1"]
    assert aperte[0]["_importo_residuo"] == 10.0


def test_la_stessa_fattura_due_volte_nel_report_non_e_un_errore(db):
    """Il report AdE elenca a volte la stessa fattura come .xml e .xml.p7m."""
    async def scenario():
        await _prepara(db)
        doppia = dict(RIGHE[0], **{"Nome file": "IT_doppione.xml.p7m", "ID SdI": "999"})
        await report_ae.importa_report_fatture_ricevute(
            db, _xlsx(RIGHE + [doppia]), "report.xlsx",
        )
        return await pagamenti.applica_pagamenti_dichiarati(db)

    esito = asyncio.run(scenario())
    assert "errore" not in esito["conteggi"]
    righe = asyncio.run(db["prima_nota_cassa"].find(
        {"fattura_id": "f-siro-cassa", "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(10))
    assert len(righe) == 1


def test_giro_ucciso_da_un_riavvio_si_dichiara_interrotto():
    """Un deploy a meta' giro lasciava lo stato «in_corso» per sempre."""
    async def scenario():
        db = ClientArchivioMemoria()["test_stato_interrotto"]
        await db["sistema_stato"].insert_one({
            "chiave": pagamenti.CHIAVE_JOB, "stato": "in_corso",
            "iniziato_at": "2026-09-23T06:55:56+00:00",
        })
        return await pagamenti.stato(db)

    assert asyncio.run(scenario())["stato"] == "interrotto"


def test_numero_assegno_che_excel_ha_trasformato_in_data():
    # Caso reale (report del 25/09/2026): l'assegno 860 salvato come «1902-05-09».
    from datetime import datetime as dt
    assert pagamenti.cifre_assegno("1902-05-09 00:00:00") == "860"
    assert pagamenti.cifre_assegno(dt(1902, 5, 9)) == "860"
    assert pagamenti.cifre_assegno(pd.Timestamp("1902-05-09")) == "860"
    assert pagamenti.cifre_assegno("334-07") == "334"
    # una data vera non e' un numero d'assegno
    assert pagamenti.numero_da_data_excel("2026-04-21") == ""


A2000 = "07000000001"


def test_banca_con_numero_d_assegno_si_paga_con_quell_assegno(db):
    """FEP 39_26: il titolare scrive «BANCA» ma anche l'assegno 985-07."""
    from datetime import datetime as dt

    async def scenario():
        await db["invoices"].insert_one(_fattura(
            "f-fep39", "FEP 39_26", A2000, "A 2000 Costruzioni S.r.l", "2026-04-28", 9760.00))
        await db["invoices"].insert_one(_fattura(
            "f-dicosmo", "8659/07", "05000000002", "DI COSMO S.R.L.", "2026-04-21", 1123.73))
        for num, imp, data in (("0208770985", 9760.00, "2026-06-30"), ("0208770860", 1123.73, "2026-04-27")):
            await db["estratto_conto_movimenti"].insert_one({
                "id": f"ec-{num}", "data": data, "tipo": "uscita", "importo": -imp,
                "descrizione": f"VOSTRO ASSEGNO N. {num}", "causale": f"VOSTRO ASSEGNO N. {num}",
                "assegno_numero": num, "riconciliato": True,
            })
            await db["assegni"].insert_one({
                "id": f"ass-{num[-3:]}", "numero": num, "importo": imp, "stato": "incassato",
                "data": data, "data_incasso": data, "movimento_id": f"ec-{num}",
                "movimento_estratto_conto_id": f"ec-{num}",
                "evidenza_bancaria_ufficiale": True, "incassato_confermato_banca": True,
            })
        righe = [
            _riga("FEP 39_26", A2000, "A 2000 Costruzioni S.r.l", "2026-04-28", 9760.00,
                  "BANCA", assegno="985-07"),
            # Excel ha scritto l'assegno 860 come data.
            _riga("8659/07", "05000000002", "DI COSMO S.R.L.", "2026-04-21", 1123.73,
                  "ASSEGNO", assegno=dt(1902, 5, 9)),
        ]
        await report_ae.importa_report_fatture_ricevute(db, _xlsx(righe), "report.xlsx")
        salvata = await db[report_ae.COLLECTION_REPORT].find_one({"numero_fattura": "8659/07"})
        await pagamenti.applica_pagamenti_dichiarati(db)
        return (salvata, await db["assegni"].find_one({"id": "ass-985"}),
                await db["assegni"].find_one({"id": "ass-860"}))

    salvata, a985, a860 = asyncio.run(scenario())
    assert salvata["assegno_numero_titolare"] == "860"
    assert [l["fattura_id"] for l in a985["fatture_collegate"]] == ["f-fep39"]
    assert [l["fattura_id"] for l in a860["fatture_collegate"]] == ["f-dicosmo"]


def test_il_conto_della_riga_dichiarata_lo_dice_il_metodo():
    conto = pagamenti.conto_metodo_dichiarato
    assert conto("banca") == "19.01.01"
    assert conto("assegno") == "19.01.01"
    assert conto("sumup") == "19.01.05"
    assert conto("carta", "Carta SumUp") == "19.01.05"
    # PayPal e carta Nexi non hanno un conto di tesoreria: vuoto, mai BPM.
    assert conto("paypal") is None
    assert conto("carta") is None


def test_la_riga_dichiarata_nasce_sul_conto_del_metodo(db):
    _importa_e_applica(db)
    leasys = asyncio.run(db["prima_nota_banca"].find_one(
        {"fattura_id": "f-leasys", "status": {"$nin": ["deleted", "archived"]}}))
    assert leasys["conto_contabile"] == "19.01.01"
    carta = asyncio.run(db["prima_nota_banca"].find_one(
        {"fattura_id": "f-vande-carta", "status": {"$nin": ["deleted", "archived"]}}))
    assert carta["metodo_pagamento_dichiarato"] == "carta"
    assert carta["conto_contabile"] is None
