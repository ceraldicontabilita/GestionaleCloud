"""13ª e 14ª salvate come «mensile»: il tipo si rilegge dal PDF, non si indovina.

Audit del 28/09/2026: 157 casi nei cedolini dell'ERP con lo stesso dipendente,
anno e mese e netti diversi. Il tipo lo dice la busta del PDF con lo stesso
codice fiscale, anno e netto al centesimo; finche' il titolare non dice di
applicare, il giro e' una simulazione.
"""
import asyncio
import base64

from app.constants.stati_netto import NETTO_VERIFICATO_DA_CEDOLINO
from app.services import cedolini_tipo_dal_pdf as tp
from app.services.archivio_documenti_memoria import ArchivioDocumenti

CF = "CPZLSN80A41F839Y"
MENSILE = {"codice_fiscale": CF, "anno": 2020, "mese": 7, "tipo_cedolino": "mensile",
           "netto": 1050.0, "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO}
QUATTORDICESIMA = {"codice_fiscale": CF, "anno": 2020, "mese": 7, "tipo_cedolino": "quattordicesima",
                   "netto": 324.0, "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO}


def _riga(id_, netto, tipo="mensile", mese=7):
    return {"id": id_, "codice_fiscale": CF.lower(), "anno": 2020, "mese": mese,
            "tipo_cedolino": tipo, "netto": netto, "netto_mese": netto}


def test_solo_i_gruppi_con_netti_diversi_si_rileggono():
    righe = [_riga("a", 1050.0), _riga("b", 324.0), _riga("c", 900.0, mese=8), _riga("d", 900.0, mese=8),
             {**_riga("e", 5.0), "tipo_cedolino": "copia_non_canonica"}]
    casi = tp.casi_da_rileggere(righe)
    assert list(casi) == [(CF, 2020, 7)]
    assert {d["id"] for d in casi[(CF, 2020, 7)]} == {"a", "b"}


def test_la_quattordicesima_si_riconosce_dal_netto_della_busta():
    esito = tp.tipo_dalla_busta(_riga("b", 324.0), [MENSILE, QUATTORDICESIMA])
    assert esito["esito"] == "da_riclassificare" and esito["tipo"] == "quattordicesima"
    assert esito["tipo_prima"] == "mensile"


def test_la_mensile_giusta_si_conferma():
    assert tp.tipo_dalla_busta(_riga("a", 1050.0), [MENSILE, QUATTORDICESIMA])["esito"] == "confermato"


def test_senza_busta_con_quel_netto_non_si_inventa():
    assert tp.tipo_dalla_busta(_riga("x", 777.0), [MENSILE, QUATTORDICESIMA])["esito"] == "non_ritrovata"


def test_un_netto_non_verificato_non_decide():
    busta = {**QUATTORDICESIMA, "stato_netto": "MULTIPLE_NETS_DA_VERIFICARE"}
    assert tp.tipo_dalla_busta(_riga("b", 324.0), [busta])["esito"] == "netto_non_verificato"


def test_due_buste_di_tipo_diverso_con_lo_stesso_netto_restano_ambigue():
    esito = tp.tipo_dalla_busta(_riga("b", 324.0), [QUATTORDICESIMA, {**QUATTORDICESIMA, "tipo_cedolino": "mensile"}])
    assert esito["esito"] == "ambigua"


def _scenario(monkeypatch, applica):
    db = ArchivioDocumenti()
    monkeypatch.setattr("app.services.cedolini_motore.leggi_pdf",
                        lambda pdf: {"buste": [MENSILE, QUATTORDICESIMA]})

    async def corri():
        pdf = base64.b64encode(b"%PDF-finto").decode()
        await db["cedolini"].insert_many([
            {**_riga("a", 1050.0), "pdf_data": pdf}, {**_riga("b", 324.0), "pdf_data": pdf},
        ])
        primo = await tp.giro(db, applica=applica)
        secondo = await tp.giro(db, applica=applica)
        b = await db["cedolini"].find_one({"id": "b"}, {"_id": 0, "pdf_data": 0})
        stato = await db["sistema_stato"].find_one({"chiave": tp.CHIAVE_STATO}, {"_id": 0})
        return primo, secondo, b, stato

    return asyncio.run(corri())


def test_in_simulazione_non_si_tocca_niente_e_il_rapporto_resta(monkeypatch):
    primo, secondo, b, stato = _scenario(monkeypatch, applica=False)
    assert primo["lette"] == 2 and secondo["lette"] == 0 and primo["simulazione"] is True
    assert b["tipo_cedolino"] == "mensile" and "tipo_cedolino_prima" not in b
    assert stato["conteggi"] == {"confermato": 1, "da_riclassificare": 1}
    assert [e["id"] for e in stato["esiti"]] == ["b"]


def test_applicando_la_riga_cambia_tipo_e_conserva_quello_di_prima(monkeypatch):
    _, _, b, _ = _scenario(monkeypatch, applica=True)
    assert b["tipo_cedolino"] == "quattordicesima"
    assert b["tipo_cedolino_prima"]["tipo"] == "mensile"


def test_il_verso_contrario_non_si_applica_da_solo(monkeypatch):
    """Solo mensile -> 13ª/14ª si applica (titolare, 28/09/2026): una 14ª che
    il PDF dice mensile resta com'e' e va nel rapporto da decidere."""
    db = ArchivioDocumenti()
    monkeypatch.setattr("app.services.cedolini_motore.leggi_pdf",
                        lambda pdf: {"buste": [MENSILE, QUATTORDICESIMA]})

    async def corri():
        pdf = base64.b64encode(b"%PDF-finto").decode()
        await db["cedolini"].insert_many([
            {**_riga("a", 1050.0, tipo="quattordicesima"), "pdf_data": pdf},
            {**_riga("b", 324.0), "pdf_data": pdf},
        ])
        await tp.giro(db, applica=True)
        a = await db["cedolini"].find_one({"id": "a"}, {"_id": 0, "pdf_data": 0})
        stato = await db["sistema_stato"].find_one({"chiave": tp.CHIAVE_STATO}, {"_id": 0})
        return a, stato

    a, stato = asyncio.run(corri())
    assert a["tipo_cedolino"] == "quattordicesima" and "tipo_cedolino_prima" not in a
    decisioni = {e["id"]: e["decisione"] for e in stato["esiti"]}
    assert decisioni == {"a": "da_decidere", "b": "applicata"}
