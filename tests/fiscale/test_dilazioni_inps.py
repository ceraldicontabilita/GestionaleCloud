"""La dilazione INPS letta dal piano e ogni rata legata alla sua quietanza.

Il testo e' quello vero di ``_5124776507_24-02-2026.pdf`` (PEC INPS
«Dilazione amministrativa» del 26/02/2026, in ``Allegato.zip``) come lo
estrae ``pdf_text_extraction``, ridotto alle righe che contano. Le quietanze
sono quelle di produzione: le quattro RC01 09/2025 del 2026 e, accanto, le
rate RC01 07/2025 della dilazione precedente, che non devono confondersi.
"""
import asyncio
import io
import zipfile

import pytest

from app.db_collections import COLL_QUIETANZE_F24
from app.routers import documenti
from app.routers import fiscal_control
from app.services import dilazioni_inps as di
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.mittenti import BUILTIN_MITTENTI

TESTO = """[PAGINA 1]
0,41
- Interessi di dilazione
- Debito per contributi:
- Sanzioni civili
136,57
4.974,00
64,02
Rif:
INPS.5100.24/02/2026.0175250
26/02/2026
Oggetto:
Accoglimento richiesta rateazione
Matricola
5124776507
Codice Fiscale
04523831214
Contribuente
S.R.L. CERALDI GROUP S.R.L.
Data della
24/02/2026
Gentile contribuente,
 domanda di rateazione è stata
Le comunico che la
accolta
 autorizzando l'estinzione del seguente
debito in
rate mensili:
4
Il versamento della prima rata di euro
1.293,00
versate mensilmente, entro 30 giorni  dalla  scadenza della  prima  rata,   sempre   a   mezzo  mod.      F24
compilato con la causale e i codici già utilizzati per il versamento della prima.
- TOTALE DEL DEBITO
5.175,00
[PAGINA 2]
Prospetto A) Piano di ammortamento
Data delibera di accoglimento
26/02/2026
[PAGINA 3]
Rif:
INPS.5100.24/02/2026.0175250
26/02/2026
Data
Piano di ammortamento
Numero rata
Quota capitale
Quota interessi
Totale rata
Data scadenza
1
1.279,30
13,69
1.293,00
08/03/2026
2
1.268,89
25,11
1.294,00
08/04/2026
3
1.277,21
16,79
1.294,00
08/05/2026
4
1.285,58
8,42
1.294,00
08/06/2026
NAPOLI
[PAGINA 5]
Modalità di pagamento
modello "F24"
nella "SEZIONE INPS", i seguenti dati:
09/2025
5100
  RC01
5124776507
1.293,00
09/2025
indicando,
"""

ISTANZA_2012 = """
ISTANZA E ATTO DI IMPEGNO PER IL PAGAMENTO DILAZIONATO DI CONTRIBUTI IN FASE AMMINISTRATIVA
Protocollo domanda: INPS.5100.21/11/2012.0258155
MATRICOLA: 5124776507
CHIEDE che gli sia concesso di pagare la somma di euro 14.267,00 mediante versamento in rate mensili
eguali e consecutive: RATE DA 2 A 24: 24
DI VOLERE CHIEDERE LA RATEAZIONE PER I SEGUENTI PERIODI:
Numero Inadempienza Periodo (mm/aaaa) Importo dovuto contributi euro Importo dovuto sanzioni euro
572 05/2012 1.484,00 0,00
573 06/2012 2.244,00 0,00
574 07/2012 3.419,00 0,00
575 08/2012 2.346,00 0,00
09/2012 1.961,00 0,00
10/2012 1.563,00 0,00
04/2012 800,00 0,00
03/2012 450,00 0,00
Totale da dilazionare Euro 14.267,00 Totale da dilazionare Euro 0,00
"""


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _q(id_, data, importo, protocollo, periodo="09/2025", periodo_raw="9 2025 9 2025", movimento=None):
    q = {
        "id": id_, "data_pagamento": data, "protocollo_telematico": protocollo, "saldo": importo,
        "codici_tributo": ["RC01"],
        "sezione_inps": [{
            "causale": "RC01", "matricola": "5124776507", "codice_sede": "5100",
            "periodo_riferimento": periodo, "periodo_raw": periodo_raw,
            "importo_debito": importo, "importo_debito_cents": round(importo * 100),
        }],
    }
    if movimento:
        q["riscontro_banca"] = {"stato": "RISCONTRATO_BANCA", "movimento_id": movimento}
    return q


QUIETANZE = [
    _q("q1", "2026-03-06", 1293.0, "26030610521841350/000001", movimento="m-0309"),
    _q("q2", "2026-04-08", 1294.0, "26030611002055014/000001", movimento="m-0408"),
    _q("q3", "2026-05-08", 1294.0, "26030611052447118/000001", movimento="m-0508"),
    _q("q4", "2026-06-08", 1294.0, "26030611101369313/000001", movimento="m-0608"),
    # la dilazione del 2025: stessa matricola e causale, periodo 07/2025
    _q("v1", "2025-09-22", 1472.0, "25091635173869622/000001", "07/2025", "7 2025 7 2025"),
]
PIANO = di.leggi_piano(TESTO)


def test_riconosce_e_legge_il_piano_vero():
    assert di.riconosci(TESTO)
    assert (PIANO["rif"], PIANO["codice_sede"], PIANO["causale"], PIANO["matricola"]) == (
        "INPS.5100.24/02/2026.0175250", "5100", "RC01", "5124776507")
    assert (PIANO["periodo_da"], PIANO["periodo_a"]) == ("09/2025", "09/2025")
    assert (PIANO["data_domanda"], PIANO["data_delibera"]) == ("2026-02-24", "2026-02-26")
    assert [(r["numero"], r["importo_cents"], r["scadenza"]) for r in PIANO["rate"]] == [
        (1, 129300, "2026-03-08"), (2, 129400, "2026-04-08"),
        (3, 129400, "2026-05-08"), (4, 129400, "2026-06-08")]
    assert PIANO["rate"][1]["quota_interessi_cents"] == 2511
    assert PIANO["quadra"] and PIANO["totale_debito_cents"] == PIANO["somma_rate_cents"] == 517500
    assert PIANO["mancanti"] == []


def test_l_istanza_2012_non_diventa_un_accoglimento_o_un_pagamento():
    assert di.riconosci_istanza(ISTANZA_2012)
    assert not di.riconosci(ISTANZA_2012)
    istanza = di.leggi_istanza(ISTANZA_2012)
    assert (istanza["rif"], istanza["matricola"], istanza["data_domanda"]) == (
        "INPS.5100.21/11/2012.0258155", "5124776507", "2012-11-21")
    assert (istanza["periodo_da"], istanza["periodo_a"]) == ("03/2012", "10/2012")
    assert [r["periodo"] for r in istanza["periodi"]] == [
        "03/2012", "04/2012", "05/2012", "06/2012", "07/2012", "08/2012", "09/2012", "10/2012"]
    assert istanza["totale_richiesto_cents"] == istanza["somma_periodi_cents"] == 1_426_700
    assert istanza["quadra"] and istanza["mancanti"] == []


def test_l_istanza_resta_da_verificare_finche_non_arriva_l_accoglimento():
    db = ClientArchivioMemoria()["istanza-inps-2012"]
    istanza = di.leggi_istanza(ISTANZA_2012)
    iid = _run(di.deposita_istanza(db, istanza, documento_id="doc-i", filename="istanza.pdf", sha256="sha"))
    salvata = _run(db[di.COLL_ISTANZE_DILAZIONI_INPS].find_one({"id": iid}))
    assert salvata["stato_richiesta"] == "PRESENTATA_DA_VERIFICARE"
    assert salvata.get("dilazione_id") is None


def test_la_situazione_fiscale_espone_i_periodi_senza_dichiararli_pagati(monkeypatch):
    db = ClientArchivioMemoria()["situazione-fiscale-istanza-inps-2012"]
    istanza = di.leggi_istanza(ISTANZA_2012)
    _run(di.deposita_istanza(db, istanza, documento_id="doc-i", filename="istanza.pdf", sha256="sha"))
    monkeypatch.setattr(fiscal_control.Database, "get_db", classmethod(lambda _cls: db))
    payload = _run(fiscal_control.dilazioni_inps(_admin={}))
    assert payload["total"] == 1
    assert payload["items"][0]["stato_richiesta"] == "PRESENTATA_DA_VERIFICARE"
    assert payload["items"][0]["periodi"][0]["periodo"] == "03/2012"
    assert "pagamento" in payload["regola"]


def test_l_accoglimento_si_collega_solo_con_coordinate_documentali_esatte():
    db = ClientArchivioMemoria()["istanza-inps-collegamento"]
    istanza = di.leggi_istanza(ISTANZA_2012)
    iid = _run(di.deposita_istanza(db, istanza, documento_id="doc-i", filename="istanza.pdf", sha256="sha"))
    _run(db[di.COLL_DILAZIONI_INPS].insert_one({
        "id": "dilazione-inps-2012", "rif": "INPS.5100.ACCOLTA",
        "matricola": "5124776507", "data_domanda": "2012-11-21", "data_delibera": "2012-12-01",
        "periodo_da": "03/2012", "periodo_a": "10/2012", "piano": [],
    }))
    _run(di.collega_istanze(db))
    salvata = _run(db[di.COLL_ISTANZE_DILAZIONI_INPS].find_one({"id": iid}))
    assert (salvata["stato_richiesta"], salvata["dilazione_id"]) == ("ACCOLTA", "dilazione-inps-2012")

    _run(db[di.COLL_DILAZIONI_INPS].insert_one({
        "id": "piano-ambiguo", "matricola": "5124776507", "data_domanda": "2012-11-21",
        "data_delibera": "2012-12-02", "periodo_da": "03/2012", "periodo_a": "10/2012", "piano": [],
    }))
    _run(di.collega_istanze(db))
    ambigua = _run(db[di.COLL_ISTANZE_DILAZIONI_INPS].find_one({"id": iid}))
    assert ambigua["stato_richiesta"] == "PRESENTATA_DA_VERIFICARE"
    assert ambigua["dilazione_id"] is None
    assert len(ambigua["candidati_accoglimento"]) == 2


def test_l_import_lo_classifica_come_dilazione_non_come_f24(monkeypatch):
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_a, **_k: TESTO.upper())
    assert documenti.detect_document_type("_5124776507_24-02-2026.pdf", b"%PDF-1.4 finto") == di.TIPO


def test_l_import_classifica_l_istanza_senza_chiamarla_piano(monkeypatch):
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_a, **_k: ISTANZA_2012.upper())
    assert documenti.detect_document_type("DichiarazioneDilazioni.pdf", b"%PDF-1.4 finto") == di.TIPO_ISTANZA


def test_una_lettera_senza_piano_non_e_una_dilazione():
    assert not di.riconosci(TESTO.replace("Piano di ammortamento", "Prospetto"))


def test_un_piano_che_non_quadra_non_abbina_niente():
    piano = di.leggi_piano(TESTO.replace("5.175,00", "5.176,00"))
    assert not piano["quadra"]
    esito = di.abbina_rate(piano, QUIETANZE, oggi="2026-09-27")
    assert all(r["stato"] != di.RATA_PAGATA for r in esito["rate"])


def test_ogni_rata_prende_la_sua_quietanza_e_il_suo_addebito():
    esito = di.abbina_rate(PIANO, QUIETANZE, oggi="2026-09-27")
    assert [(r["numero"], r["stato"], r["quietanza_ids"], r["movimento_id"]) for r in esito["rate"]] == [
        (1, "PAGATA", ["q1"], "m-0309"), (2, "PAGATA", ["q2"], "m-0408"),
        (3, "PAGATA", ["q3"], "m-0508"), (4, "PAGATA", ["q4"], "m-0608")]
    assert esito["stato"] == "SALDATA" and esito["residuo_cents"] == 0
    assert esito["pagamenti_non_previsti"] == []  # la rata 07/2025 non e' di questo piano


def test_due_copie_della_stessa_quietanza_sono_un_pagamento_solo():
    copia = {**QUIETANZE[1], "id": "q2-copia"}
    esito = di.abbina_rate(PIANO, QUIETANZE + [copia], oggi="2026-09-27")
    assert esito["rate"][1]["quietanza_ids"] == ["q2", "q2-copia"]
    assert esito["rate"][2]["quietanza_ids"] == ["q3"]


def test_cassetto_senza_protocollo_e_quietanza_sono_la_stessa_rata():
    from copy import deepcopy

    quietanza = {**QUIETANZE[1], "codice_fiscale": "04523831214"}
    copia = {**deepcopy(quietanza), "id": "cassetto", "protocollo_telematico": ""}
    riga = copia["sezione_inps"][0]
    riga.pop("periodo_raw")
    riga.update(periodo_da="09/2025", periodo_a="09/2025")
    for documenti in ([quietanza, copia], [copia, quietanza]):
        esito = di.abbina_rate(PIANO, documenti, oggi="2026-10-13")
        assert esito["rate_pagate"] == 1
        assert esito["rate"][1]["quietanza_ids"] == ["cassetto", "q2"]
        assert esito["pagamenti_non_previsti"] == []


def test_la_copia_ambigua_non_paga_una_terza_rata():
    prima = {**QUIETANZE[1], "codice_fiscale": "04523831214"}
    seconda = {**prima, "id": "seconda", "protocollo_telematico": "ALTRO/000001"}
    copia = {**prima, "id": "cassetto", "protocollo_telematico": ""}
    esito = di.abbina_rate(PIANO, [prima, seconda, copia], oggi="2026-10-13")
    assert esito["rate_pagate"] == 2
    assert esito["pagamenti_non_previsti"][0]["quietanza_ids"] == ["cassetto"]
    assert esito["pagamenti_non_previsti"][0]["da_verificare"]


def test_non_accorpa_la_sola_riga_inps_se_le_altre_righe_della_delega_cambiano():
    quietanza = {**QUIETANZE[1], "codice_fiscale": "04523831214"}
    copia = {**quietanza, "id": "cassetto", "protocollo_telematico": "",
             "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "2025",
                                  "importo_debito": 10, "importo_credito": 10}]}
    assert len(di.pagamenti_della_dilazione(PIANO, [quietanza, copia])) == 2
    assert di._firma_delega_pagata({**quietanza, "codice_fiscale": ""}) is None


def test_la_firma_della_quietanza_conserva_la_fine_del_periodo_inps():
    from copy import deepcopy

    quietanza = {**QUIETANZE[1], "codice_fiscale": "04523831214"}
    diversa = deepcopy(quietanza)
    diversa["sezione_inps"][0]["periodo_raw"] = "9 2025 10 2025"
    assert di._firma_delega_pagata(quietanza) != di._firma_delega_pagata(diversa)


def test_importo_diverso_o_versamento_prima_della_domanda_non_pagano_la_rata():
    diverso = _q("x", "2026-04-08", 1294.01, "26030611002055014/000001")
    prima = _q("y", "2026-02-20", 1293.0, "26022011002055014/000001")
    esito = di.abbina_rate(PIANO, [diverso, prima], oggi="2026-04-20")
    # l'importo diverso si affianca alla prima rata aperta, senza pagarla;
    # il versamento prima della domanda non e' della dilazione
    assert [r["stato"] for r in esito["rate"]] == [
        di.RATA_IMPORTO_DIVERSO, di.RATA_SCADUTA, di.RATA_DA_PAGARE, di.RATA_DA_PAGARE]
    assert esito["rate"][0]["versamento_diverso"]["differenza_cents"] == 101


def test_rata_pagata_dopo_la_scadenza_lo_dice():
    tardi = _q("t", "2026-03-20", 1293.0, "26032011002055014/000001")
    assert di.abbina_rate(PIANO, [tardi], oggi="2026-03-21")["rate"][0]["oltre_scadenza"] is True


def test_la_rata_versata_con_un_importo_diverso_resta_aperta_col_versamento_accanto():
    """Piano del 12/09/2025 (07/2025): 1.472 e poi 3 x 1.477; le quietanze
    di ottobre, novembre e dicembre 2025 sono da 1.472."""
    piano = {**PIANO, "periodo_da": "07/2025", "periodo_a": "07/2025", "data_domanda": "2025-09-10",
             "rate": [{"numero": 1, "importo_cents": 147200, "scadenza": "2025-09-22"}] + [
                 {"numero": n, "importo_cents": 147700, "scadenza": s}
                 for n, s in ((2, "2025-10-22"), (3, "2025-11-22"), (4, "2025-12-22"))],
             "totale_debito_cents": 590300}
    quietanze = [_q(f"v{n}", d, 1472.0, f"250916351{n}/000001", "07/2025", "7 2025 7 2025")
                 for n, d in enumerate(("2025-09-22", "2025-10-22", "2025-11-21", "2025-12-22"), 1)]
    esito = di.abbina_rate(piano, quietanze, oggi="2026-09-27")
    assert [r["stato"] for r in esito["rate"]] == [di.RATA_PAGATA] + [di.RATA_IMPORTO_DIVERSO] * 3
    assert esito["rate"][1]["versamento_diverso"]["differenza_cents"] == -500
    assert esito["rate"][3]["versamento_diverso"]["quietanza_ids"] == ["v4"]
    assert esito["stato"] == "IN_CORSO" and esito["pagamenti_non_previsti"] == []


def test_il_periodo_a_si_legge_dal_testo_della_riga():
    """Piano del 2023 (RC01 02/2022-11/2022): la riga ha solo «2 2022 11 2022»."""
    piano = {**PIANO, "periodo_da": "02/2022", "periodo_a": "11/2022", "data_domanda": "2023-05-10",
             "rate": [{"numero": 1, "importo_cents": 71700, "scadenza": "2023-05-21"}],
             "totale_debito_cents": 71700}
    buona = _q("a", "2023-05-16", 717.0, "23051612362132402/000001", "02/2022", "2 2022 11 2022")
    altra = _q("b", "2023-05-17", 717.0, "23051712362132402/000001", "02/2022", "2 2022 12 2022")
    esito = di.abbina_rate(piano, [buona, altra], oggi="2023-06-01")
    assert esito["rate"][0]["quietanza_ids"] == ["a"] and esito["pagamenti_non_previsti"] == []


# ── scrittura ─────────────────────────────────────────────────────────────

def _db(quietanze):
    db = ClientArchivioMemoria()["gestionale_test"]

    async def _carica():
        for q in quietanze:
            await db[COLL_QUIETANZE_F24].insert_one(dict(q))
        await di.deposita_piano(db, PIANO, documento_id="doc-1", filename="piano.pdf", sha256="abc")
    _run(_carica())
    return db


def test_il_giro_scrive_le_rate_e_l_etichetta_sulle_quietanze_una_volta_sola():
    db = _db(QUIETANZE)
    esito = _run(di.collega_dilazioni(db, oggi="2026-09-27"))
    assert esito["scritti"]["dilazioni"] == 1 and esito["scritti"]["quietanze"] == 4

    dil = _run(db[di.COLL_DILAZIONI_INPS].find_one({"id": di.id_dilazione(PIANO)}))
    assert dil["stato"] == "SALDATA" and dil["rate_pagate"] == 4
    q3 = _run(db[COLL_QUIETANZE_F24].find_one({"id": "q3"}))
    assert (q3["dilazione_inps"]["rata"], q3["dilazione_inps"]["di"]) == (3, 4)
    assert "dilazione_inps" not in _run(db[COLL_QUIETANZE_F24].find_one({"id": "v1"}))

    secondo = _run(di.collega_dilazioni(db, oggi="2026-09-27"))
    assert secondo["scritti"] == {"dilazioni": 0, "quietanze": 0, "alert_aperti": 0, "alert_chiusi": 0}


def test_lo_stesso_piano_arrivato_due_volte_resta_una_riga():
    db = _db([])
    _run(di.deposita_piano(db, PIANO, documento_id="doc-2", filename="copia.pdf", sha256="abc"))
    assert len(_run(db[di.COLL_DILAZIONI_INPS].find({}).to_list(10))) == 1


def test_la_rata_scaduta_apre_un_alert_che_si_chiude_quando_arriva_la_quietanza():
    db = _db(QUIETANZE[:3])
    _run(di.collega_dilazioni(db, oggi="2026-09-27"))
    aperti = _run(db["alerts"].find({"codice": di.ALERT_RATA_NON_PAGATA}).to_list(10))
    assert len(aperti) == 1 and "rata 4/4" in aperti[0]["dettaglio"]

    _run(db[COLL_QUIETANZE_F24].insert_one(dict(QUIETANZE[3])))
    esito = _run(di.collega_dilazioni(db, oggi="2026-09-27"))
    assert esito["scritti"]["alert_chiusi"] == 1


def test_la_chiusura_in_blocco_lascia_aperti_gli_alert_delle_rate_non_pagate(monkeypatch):
    from app.constants.canale_documento import STATO_ALERT_APERTO
    db = _db([])
    _run(di.collega_dilazioni(db, oggi="2026-10-13"))
    for quietanza in QUIETANZE[:3]:
        _run(db[COLL_QUIETANZE_F24].insert_one(dict(quietanza)))
    chiamate = []
    update = db["alerts"].update_many
    async def registra(selector, patch):
        chiamate.append(selector)
        return await update(selector, patch)
    monkeypatch.setattr(db["alerts"], "update_many", registra)
    esito = _run(di.collega_dilazioni(db, oggi="2026-10-13"))
    assert esito["scritti"]["alert_chiusi"] == 3
    assert len(chiamate) == 1
    aperti = _run(db["alerts"].find({"stato": STATO_ALERT_APERTO}).to_list(10))
    assert len(aperti) == 1 and "rata 4/4" in aperti[0]["dettaglio"]


def test_il_pdf_arrivato_viene_conservato_depositato_e_abbinato_subito():
    db = ClientArchivioMemoria()["gestionale_test"]
    _run(db[COLL_QUIETANZE_F24].insert_one(dict(QUIETANZE[0])))
    esito = _run(di.archivia_dilazione(db, filename="_5124776507_24-02-2026.pdf",
                                       content=b"%PDF-1.4 piano", testo=TESTO))
    assert esito["success"] and esito["dilazione_id"] == di.id_dilazione(PIANO)
    riga = _run(db["documents_inbox"].find_one({"id": esito["doc_id"]}))
    assert (riga["category"], riga["status"], riga["dilazione_id"]) == (di.TIPO, "archiviato", esito["dilazione_id"])
    q1 = _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))
    assert q1["dilazione_inps"]["rata"] == 1


# ── ingresso dalla posta ──────────────────────────────────────────────────

def _zip(voci):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for nome, dati in voci:
            z.writestr(nome, dati)
    return buffer.getvalue()


def test_dallo_zip_escono_solo_i_pdf():
    voci = di.pdf_da_zip(_zip([("_5124776507_24-02-2026.pdf", b"%PDF"), ("leggimi.txt", b"x")]))
    assert voci == [("_5124776507_24-02-2026.pdf", b"%PDF")]


def test_uno_zip_con_un_percorso_e_rifiutato():
    with pytest.raises(ValueError):
        di.pdf_da_zip(_zip([("../fuori.pdf", b"%PDF")]))


def test_la_pec_dell_inps_e_un_mittente_autorizzato_per_le_dilazioni():
    assert {"pattern": di.MITTENTE_PEC, "tipo_documento": di.TIPO} in [
        {k: m[k] for k in ("pattern", "tipo_documento")} for m in BUILTIN_MITTENTI]


# ── piano 14/02/2020: «12 rate» in lettera, 11 righe nel prospetto ─────────

TESTO_2020 = """Rif:
INPS.5100.14/02/2020.0079479
Oggetto: Accoglimento richiesta rateazione
Matricola 5124776507 Codice Fiscale 04523831214
Data della 14/02/2020 domanda di dilazione:
accolta autorizzando l'estinzione del seguente debito in rate mensili: 12
Il versamento della prima rata di euro 2.601,00 che costituisce accettazione del piano di 10 rate costanti
- TOTALE DEL DEBITO 15.721,00
Data delibera di accoglimento 20/02/2020
Piano di ammortamento
Numero rata Quota capitale Quota interessi Totale rata Data scadenza
1 2.560,66 40,34 2.601,00 01/03/2020
2 1.249,79 62,21 1.312,00 01/04/2020
3 1.255,88 56,12 1.312,00 01/05/2020
4 1.261,99 50,01 1.312,00 01/06/2020
5 1.268,14 43,86 1.312,00 01/07/2020
6 1.274,31 37,69 1.312,00 01/08/2020
7 1.280,52 31,48 1.312,00 01/09/2020
8 1.286,75 25,25 1.312,00 01/10/2020
9 1.293,02 18,98 1.312,00 01/11/2020
10 1.299,32 12,68 1.312,00 01/12/2020
11 1.305,64 6,36 1.312,00 01/01/2021
Modalita di pagamento modello "F24" nella "SEZIONE INPS", i seguenti dati:
10/2019 5100 RC01 5124776507 2.601,00 12/2019
"""


def test_il_totale_al_centesimo_fa_quadrare_anche_con_le_rate_dichiarate_diverse():
    piano = di.leggi_piano(TESTO_2020)
    assert piano["rif"] == "INPS.5100.14/02/2020.0079479" and len(piano["rate"]) == 11
    assert piano["numero_rate_dichiarato"] == 12
    assert piano["quadra"] and piano["somma_rate_cents"] == piano["totale_debito_cents"] == 1572100
    assert piano["avvertenze"] == ["rate dichiarate 12, lette 11"]
    # una rata in meno nel prospetto: la somma non torna e il piano non quadra
    monco = di.leggi_piano(TESTO_2020.replace("11 1.305,64 6,36 1.312,00 01/01/2021\n", ""))
    assert not monco["quadra"] and monco["avvertenze"] == ["rate dichiarate 12, lette 10"]


def test_la_ripresa_deposita_il_piano_conservato_ma_mai_depositato(monkeypatch):
    db = ClientArchivioMemoria()["ripresa"]
    sha = "cc948d43283eb13c37bc8c07e78b443a8595633491b737fef66b8bc64489105c"
    asyncio.run(db["documents_inbox"].insert_one({
        "id": "inbox-2020", "document_type": di.TIPO, "status": "da_verificare", "sha256": sha,
        "filename": "dilazione 14-02-2020.pdf", "parsed_metadata": {"quadra": False, "rif": "INPS.5100.14/02/2020.0079479"},
    }))
    asyncio.run(db["documents_inbox"].insert_one({
        "id": "inbox-perso", "document_type": di.TIPO, "status": "da_verificare", "sha256": "0" * 64,
        "filename": "perso.pdf", "parsed_metadata": {},
    }))

    class _Originale:
        contenuto = b"%PDF finto"

    async def _apri(_db, impronta):
        if impronta == sha:
            return _Originale()
        from app.services.originale_documento import OriginaleNonDisponibile
        raise OriginaleNonDisponibile("Originale non disponibile", {"sha256": impronta})

    from app.services import originale_documento
    monkeypatch.setattr(originale_documento, "apri_per_impronta", _apri)
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_a, **_k: TESTO_2020)

    esito = asyncio.run(di.riprendi_da_verificare(db))
    assert (esito["candidati"], esito["depositati"], esito["originale_assente"]) == (2, 1, 1)
    dil = asyncio.run(db[di.COLL_DILAZIONI_INPS].find_one({"rif": "INPS.5100.14/02/2020.0079479"}, {"_id": 0}))
    assert dil and len(dil["piano"]) == 11 and dil["documento_id"] == "inbox-2020"
    inbox = asyncio.run(db["documents_inbox"].find_one({"id": "inbox-2020"}, {"_id": 0}))
    assert inbox["status"] == "archiviato" and inbox["dilazione_id"] == dil["id"]
    assert inbox["parsed_metadata"]["quadra"] is True and inbox["parsed_metadata"]["avvertenze"] == ["rate dichiarate 12, lette 11"]
    # il documento senza originale resta «da verificare» ma non si ritenta a ogni giro
    perso = asyncio.run(db["documents_inbox"].find_one({"id": "inbox-perso"}, {"_id": 0}))
    assert perso["status"] == "da_verificare" and perso["ripresa_v"] == di.RIPRESA_V
    assert asyncio.run(di.riprendi_da_verificare(db))["candidati"] == 0


def test_periodo_ridotto_richiede_piano_univoco_e_importo_esatto():
    piano = {**PIANO, 'periodo_da':'01/2025', 'periodo_a':'12/2025'}
    q = _q('ridotto', '2026-03-06', 1293, 'protocollo-ridotto', '01/2025', '1 2025 1 2025')
    # Senza confronto con tutti i piani non si presume la destinazione.
    assert di.abbina_rate(piano, [q])['rate_pagate'] == 0
    result = di.abbina_rate(piano, [q], piani=[piano])
    assert result['rate_pagate'] == 1 and result['rate'][0]['periodo_ridotto']['periodo_originale'] == ['01/2025','01/2025']
    ambiguo = {**piano, 'rif':'altro-piano'}
    assert di.abbina_rate(piano, [q], piani=[piano, ambiguo])['rate_pagate'] == 0
    esatto = {**ambiguo, 'periodo_da':'01/2025','periodo_a':'01/2025'}
    assert di.abbina_rate(piano, [q], piani=[piano, esatto])['rate_pagate'] == 0
    q['sezione_inps'][0]['importo_debito_cents'] = 129299
    assert di.abbina_rate(piano, [q], piani=[piano])['rate_pagate'] == 0


def test_pagamento_parziale_riduce_il_residuo_senza_chiudere_la_rata():
    piano = {**PIANO, 'rate':[{'numero':1,'importo_cents':147700,'scadenza':'2026-03-08'}]}
    q = _q('parziale', '2026-03-08', 1472, 'protocollo-parziale')
    result = di.abbina_rate(piano, [q])
    assert result['residuo_cents'] == 500
    assert result['rate_pagate'] == 0 and result['rate'][0]['stato'] == di.RATA_IMPORTO_DIVERSO
