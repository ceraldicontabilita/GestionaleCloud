"""GC-02h, strada A: le registrazioni HACCP senza firma verificata si segnano.

Decisione del titolare del 24/09/2026: segnare, non cancellare. Il valore
originale resta intatto; il documento riceve il campo `non_attendibili` e
stampe e schede mostrano «n.a.», fuori dai conteggi di conformita'.

Tutto su un database di prova in memoria (mongomock-motor).
"""
import asyncio
import copy

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import haccp_attendibilita as ha


def run(coro):
    return asyncio.run(coro)


ANNO = 2025
MESE = 3

FIRMA_OK = {"firma_verificata": True, "operatore": "Pocci Salvatore", "dipendente_id": "hr-7"}


def _temperature_doc(collezione_numero: str):
    """Una scheda con ogni forma di casella trovata in produzione."""
    return {
        "id": f"t-{collezione_numero}",
        "anno": ANNO,
        collezione_numero: 1,
        "temp_min": 0.0,
        "temp_max": 4.0,
        "temperature": {
            str(MESE): {
                "1": 2.7,                                                   # numero semplice
                "2": {"temp": 3.1, "operatore": "x", "auto": True,          # sorteggiata 2026
                      "soglie": {"min": 0, "max": 4}},
                "3": {"is_manutenzione": True, "is_chiuso": False,          # fermo inventato
                      "is_non_usato": False, "temp": None},
                "4": {"is_non_usato": True, "is_chiuso": False,
                      "is_manutenzione": False, "temp": None},
                "5": {"is_sanificazione": True, "sanificazione_eseguita": True,
                      "temp": None, "operatore": "x"},
                "6": {"is_chiuso": True, "is_manutenzione": False,          # chiusura dichiarata
                      "is_non_usato": False, "temp": None, "motivo": "Chiuso"},
                "7": {"non_rilevato": True, "auto": True, "temp": None,     # onestamente vuota
                      "motivo": "server spento"},
                "8": {"stato": "da_rilevare", "temp": None,                 # casella aperta
                      "operatore_id": "hr-7"},
                "9": {"temp": 3.4, **FIRMA_OK},                             # firmata
                "10": 9.9,                                                  # numero fuori soglia
            }
        },
    }


def _scheda_sanificazione():
    return {
        "id": "s-1",
        "anno": ANNO,
        "mese": MESE,
        "registrazioni": {
            "Pavimentazione": {"1": "X", "2": "x", "3": "N/D", "4": "X", "5": ""},
            "Deposito": {"1": {"1": "X", "2": "X"}},  # valore annidato anomalo
        },
        "firme": {"Pavimentazione": {"4": {"valore": "X", **FIRMA_OK}}},
    }


def _apparecchi():
    return {
        "id": "a-1",
        "anno": ANNO,
        "registrazioni_frigoriferi": {
            "1": [
                {"data": f"05/{MESE:02d}/{ANNO}", "giorno": 5, "mese": MESE, "eseguita": True,
                 "operatore": "designato", "prodotto": "Detergente", "note": ""},
                {"data": f"15/{MESE:02d}/{ANNO}", "giorno": 15, "mese": MESE, "eseguita": False,
                 "operatore": "designato", "prodotto": "", "note": ""},
                {"data": f"20/{MESE:02d}/{ANNO}", "giorno": 20, "mese": MESE, "eseguita": True,
                 "prodotto": "Sgrassatore", **FIRMA_OK},
            ]
        },
        "registrazioni_congelatori": {
            "2": [{"data": f"07/{MESE:02d}/{ANNO}", "giorno": 7, "mese": MESE, "eseguita": True,
                   "operatore": "designato", "prodotto": "Detergente", "note": ""}],
        },
    }


@pytest.fixture()
def db(monkeypatch):
    import app.lotti.azienda as azienda
    import app.lotti.routers.haccp_attendibilita as router
    import app.lotti.routers.report_haccp as report
    import app.lotti.routers.sanificazione as san
    import app.lotti.routers.temperature_negative as neg
    import app.lotti.routers.temperature_positive as pos

    database = AsyncMongoMockClient()["Lotti_Test_GC02h"]
    for modulo in (pos, neg, san, report, router, azienda):
        monkeypatch.setattr(modulo, "db", database, raising=False)
    run(database.temperature_positive.insert_one(_temperature_doc("frigorifero_numero")))
    run(database.temperature_negative.insert_one(_temperature_doc("congelatore_numero")))
    run(database.sanificazione_schede.insert_one(_scheda_sanificazione()))
    run(database.sanificazione_apparecchi.insert_one(_apparecchi()))
    return database


def _senza_segno(doc):
    doc = copy.deepcopy(doc)
    doc.pop("_id", None)
    doc.pop(ha.CAMPO, None)
    return doc


async def _istantanea(database):
    out = {}
    for c in ha.COLLEZIONI:
        out[c] = [_senza_segno(d) for d in await getattr(database, c).find({}).to_list(None)]
    return out


# ── regola ──────────────────────────────────────────────────────────────────


def test_ogni_categoria_della_tabella_si_segna():
    celle = ha.celle_da_segnare("temperature_positive", _temperature_doc("frigorifero_numero"))
    assert celle == {str(MESE): ["1", "2", "3", "4", "5", "10"]}

    celle = ha.celle_da_segnare(ha.SCHEDE, _scheda_sanificazione())
    assert celle == {"Pavimentazione": ["1", "2"]}

    celle = ha.celle_da_segnare(ha.APPARECCHI, _apparecchi())
    assert celle == {
        "registrazioni_frigoriferi": {"1": [f"{MESE}-5", f"{MESE}-15"]},
        "registrazioni_congelatori": {"2": [f"{MESE}-7"]},
    }


def test_categorie_da_non_toccare():
    for v in (
        {"is_chiuso": True, "temp": None},
        {"non_rilevato": True, "temp": None},
        {"stato": "da_rilevare", "temp": None},
        {"temp": 3.0, "firma_verificata": True},
        "N/D", None, "",
    ):
        assert not ha.da_segnare_temperatura(v), v
    # una firma «quasi» vera non vale: solo il booleano True
    assert ha.da_segnare_temperatura({"temp": 3.0, "firma_verificata": "true"})
    assert not ha.da_segnare_scheda("N/D", None)
    assert not ha.da_segnare_scheda("X", FIRMA_OK)
    assert not ha.da_segnare_apparecchio({"eseguita": True, **FIRMA_OK})


def test_anteprima_conta_per_categoria_e_riporta_le_anomalie(db):
    esito = run(ha.anteprima(db))
    cat = {k: v["da_segnare"] for k, v in esito["per_categoria"].items()}
    assert cat == {
        ha.CAT_VALORE_SEMPLICE: 4,        # 2 per scheda (1 e 10), due schede
        ha.CAT_TEMP_SENZA_FIRMA: 2,
        ha.CAT_FERMO_INVENTATO: 4,
        ha.CAT_SANIF_IN_TEMPERATURE: 2,
        ha.CAT_SCHEDA_X: 2,
        ha.CAT_APPARECCHIO: 3,
    }
    assert esito["totale_da_segnare"] == 17
    assert esito["totale_gia_segnati"] == 0
    assert esito["non_toccati"] == {
        ha.NT_CHIUSO: 2, ha.NT_NON_RILEVATO: 2, ha.NT_CASELLA_APERTA: 2,
        ha.NT_FIRMATO: 4, ha.NT_ND: 1,
    }
    assert [a["motivo"] for a in esito["anomalie"]] == ["valore annidato nella casella"]
    assert esito["per_collezione"]["temperature_positive"][str(ANNO)][ha.CAT_VALORE_SEMPLICE] == {
        "da_segnare": 2, "gia_segnati": 0}


def test_simulazione_non_scrive(db):
    prima = run(db.temperature_positive.find_one({"id": "t-frigorifero_numero"}))
    esito = run(ha.segna(db, {"id": "admin", "nome": "Titolare"}, dry_run=True))
    assert esito["caselle_segnate"] == 17
    assert esito["documenti_modificati"] == 0
    dopo = run(db.temperature_positive.find_one({"id": "t-frigorifero_numero"}))
    assert dopo == prima
    assert run(db.haccp_attendibilita_log.count_documents({})) == 0


def test_segna_senza_toccare_i_valori_ed_e_idempotente(db):
    prima = run(_istantanea(db))
    esito = run(ha.segna(db, {"id": "admin", "nome": "Titolare"}, dry_run=False))
    assert esito["caselle_segnate"] == 17
    assert esito["documenti_modificati"] == 4
    # i valori sono identici: cambia solo il campo del segno
    assert run(_istantanea(db)) == prima

    doc = run(db.temperature_positive.find_one({"id": "t-frigorifero_numero"}))
    segno = doc[ha.CAMPO]
    assert segno["regola"] == ha.REGOLA
    assert segno["segnato_da"] == {"id": "admin", "nome": "Titolare"}
    assert segno["celle"] == {str(MESE): ["1", "2", "3", "4", "5", "10"]}
    assert run(db.haccp_attendibilita_log.count_documents({})) == 1

    # seconda esecuzione: zero modifiche, e l'anteprima dice «gia' segnati»
    di_nuovo = run(ha.segna(db, {"id": "admin", "nome": "Titolare"}, dry_run=False))
    assert di_nuovo["caselle_segnate"] == 0
    assert di_nuovo["documenti_modificati"] == 0
    ant = run(ha.anteprima(db))
    assert ant["totale_da_segnare"] == 0
    assert ant["totale_gia_segnati"] == 17


def test_rilevazione_firmata_successiva_non_e_piu_na(db, monkeypatch):
    import app.lotti.auth as auth
    from app.lotti.routers import temperature_positive as pos

    run(ha.segna(db, {"id": "admin", "nome": "Titolare"}, dry_run=False))
    doc = run(db.temperature_positive.find_one({"id": "t-frigorifero_numero"}))
    assert ha.e_non_attendibile(doc, (MESE, 1), doc["temperature"][str(MESE)]["1"])

    monkeypatch.setattr(auth, "request_actor", lambda _r: {
        "id": "hr-7", "nome": "Pocci Salvatore", "ruolo": "operatore", "via": "pin"})
    run(pos.registra_temperatura(ANNO, 1, MESE, 1, temperatura=3.0, operatore="", pin="",
                                 note="", azione_correttiva="", request=object()))
    doc = run(db.temperature_positive.find_one({"id": "t-frigorifero_numero"}))
    nuovo = doc["temperature"][str(MESE)]["1"]
    assert nuovo["firma_verificata"] is True
    assert not ha.e_non_attendibile(doc, (MESE, 1), nuovo)
    # il segno resta nel documento come storia; il vecchio valore sta in `sostituisce`
    assert "1" in doc[ha.CAMPO]["celle"][str(MESE)]
    assert nuovo["sostituisce"][0]["valore"] == 2.7


def test_chiavi_mese_giorno_tolleranti():
    doc = {ha.CAMPO: {"celle": {"3": ["5"]}}}
    assert ha.e_non_attendibile(doc, ("03", "05"), 2.0)
    assert ha.e_non_attendibile(doc, (3, 5), 2.0)
    assert not ha.e_non_attendibile(doc, (3, 6), 2.0)
    assert not ha.e_non_attendibile({}, (3, 5), 2.0)


# ── report mensile ─────────────────────────────────────────────────────────


def test_report_esclude_i_na_da_conteggi_e_percentuali(db):
    from app.lotti.routers import report_haccp

    run(ha.segna(db, {"id": "admin", "nome": "Titolare"}, dry_run=False))
    apps, flat = run(report_haccp.load_temperature(db.temperature_positive, ANNO, MESE, "positive"))
    # resta solo la rilevazione firmata del giorno 9
    assert [(r["giorno"], r["valore"]) for r in flat] == [("9", 3.4)]
    assert apps[0]["giorni"]["1"] == {"non_attendibile": True, "originale": 2.7}

    html = report_haccp.table_temperature(apps, ANNO, MESE, 0, 4)
    assert 'class="na"' in html and ">n.a.</td>" in html
    assert "100%<br><small>1/1</small>" in html  # 9,9 °C sorteggiato non fa «non conforme»
    assert "senza firma verificata, non attendibile" in html

    righe = run(report_haccp.load_sanificazioni(ANNO, MESE))
    na = {(r["area"], r["giorno"]) for r in righe if r["non_attendibile"]}
    assert ("Pavimentazione", "1") in na and ("Pavimentazione", "2") in na
    assert ("Pavimentazione", "4") not in na           # firmata
    assert ("Frigorifero 1", "5") in na
    assert ("Frigorifero 1", "20") not in na            # firmata

    pagina = run(report_haccp.report_haccp_mensile(anno=ANNO, mese=MESE)).body.decode()
    # Sanificazioni valide: Pavimentazione 4 e Frigorifero 1 del 20
    assert "<b>2</b><span>Sanificazioni</span>" in pagina
    assert ">n.a.</td>" in pagina


def test_report_senza_segni_non_cambia(db):
    """Prima della scrittura il report resta com'era: il segno fa la differenza."""
    from app.lotti.routers import report_haccp

    _apps, flat = run(report_haccp.load_temperature(db.temperature_positive, ANNO, MESE, "positive"))
    assert [r["giorno"] for r in flat] == ["1", "2", "9", "10"]
    righe = run(report_haccp.load_sanificazioni(ANNO, MESE))
    assert not any(r["non_attendibile"] for r in righe)


def test_stampa_scheda_sanificazione_mostra_na(db):
    from app.lotti.routers import sanificazione as san

    run(ha.segna(db, {"id": "admin", "nome": "Titolare"}, dry_run=False))
    # la stampa usa le aree standard: ne mettiamo una segnata
    run(db.sanificazione_schede.update_one(
        {"id": "s-1"},
        {"$set": {"registrazioni.Deposito": {"3": "X"},
                  "non_attendibili.celle.Deposito": ["3"]}},
    ))
    html = run(san.export_pdf_sanificazione(ANNO, MESE)).body.decode()
    assert "<td class='na' title='Registrazione senza firma verificata'>n.a.</td>" in html
    assert "non attendibile" in html


# ── router ─────────────────────────────────────────────────────────────────


def test_router_scrive_solo_con_conferma(db):
    from app.lotti.routers import haccp_attendibilita as router

    with pytest.raises(HTTPException) as exc:
        run(router.segna_non_attendibili(request=None, dry_run=False, conferma=""))
    assert exc.value.status_code == 400
    assert "non_attendibili" not in run(db.temperature_positive.find_one({"id": "t-frigorifero_numero"}))

    simulato = run(router.segna_non_attendibili(request=None, dry_run=True, conferma=""))
    assert simulato["dry_run"] is True and simulato["documenti_modificati"] == 0

    scritto = run(router.segna_non_attendibili(request=None, dry_run=False, conferma="SEGNA"))
    assert scritto["documenti_modificati"] == 4


def test_router_riservato_all_amministratore():
    from app.lotti.routers import haccp_attendibilita as router
    from app.lotti.auth import require_admin

    for route in router.router.routes:
        dipendenze = [d.call for d in route.dependant.dependencies]
        assert require_admin in dipendenze, route.path
