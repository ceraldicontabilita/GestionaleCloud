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


def test_banca_dichiarata_storna_la_cassa_d_ufficio_e_aspetta_la_banca(db):
    _importa_e_applica(db)
    riga = asyncio.run(db["prima_nota_cassa"].find_one({"id": "pn-ufficio-2"}))
    assert riga["status"] == "deleted"
    assert riga["deleted_reason"].endswith("pagata_con_banca")
    fattura = asyncio.run(db["invoices"].find_one({"id": "f-leasys"}))
    assert fattura["stato_finanziario"] == "aperta_in_attesa_banca"
    assert fattura["metodo_pagamento_dichiarato"] == "banca"
    assert fattura.get("pagato") is False
    # Nessuna riga banca senza estratto conto.
    assert asyncio.run(db["prima_nota_banca"].find_one({"fattura_id": "f-leasys"})) is None


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
    # Ripassa anche le due in attesa della banca (Leasys e la carta):
    # senza movimento restano in attesa, senza scritture nuove.
    assert giro["conteggi"] == {"registrata": 1, "in_attesa_banca": 2}
    riga = asyncio.run(db["prima_nota_cassa"].find_one({"fattura_id": "f-kimbo-10"}))
    assert riga["importo"] == 99.0


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
