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


def test_l_import_lo_classifica_come_dilazione_non_come_f24(monkeypatch):
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_a, **_k: TESTO.upper())
    assert documenti.detect_document_type("_5124776507_24-02-2026.pdf", b"%PDF-1.4 finto") == di.TIPO


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
