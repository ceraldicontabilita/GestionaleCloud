"""Collaudo funzionale: il credito POS aperto dall'XML senza chiusura del terminale.

Decisione del titolare (02/10/2026, n. 11): l'XML apre comunque il credito verso
il gestore per la sua quota elettronica, senza inventare il circuito (15.07,
«senza chiusura terminale», ``fonte_credito="xml"``); la chiusura del terminale lo
SOSTITUISCE se i totali coincidono al centesimo, altrimenti resta con la
differenza; l'accredito in banca al centesimo lo chiude; il reimport dell'XML non
scrive una seconda riga; il ricavo resta quello del corrispettivo.
"""
from app.routers import pos_corrispettivi_check as pc
from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed
from app.services.scritture_contabili import (
    FONTE_API, recupera_pos_storico_da_estratto, registra_chiusura_pos_reale,
    riconcilia_accredito_pos_ec,
)

from ._comune import (
    D, Importatore, attive, istantanea, nuovo_db, parsed_chiusura, righe, run, somma,
    xml_chiusura,
)

GIORNO = "2026-09-10"
CAUSALE_NUMIA = "INC.POS CARTE CREDIT - NUMIA-INTER DEL 10/09/26 PDV 3757283/00011"


def _crediti(db):
    return [r for r in run(attive(db, "prima_nota_banca")) if r.get("natura") == "credito_pos"]


def _da_xml(db):
    return [r for r in _crediti(db) if r.get("fonte_credito") == "xml"]


def _accredito(db, id_, importo, causale=CAUSALE_NUMIA, data="2026-09-11"):
    run(db["estratto_conto_movimenti"].insert_one({
        "id": id_, "data": data, "importo": importo, "tipo": "entrata",
        "descrizione_originale": causale}))
    return run(riconcilia_accredito_pos_ec(
        db, run(db["estratto_conto_movimenti"].find_one({"id": id_}))))


def _coerenza(db, monkeypatch):
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
    risultato = run(pc.controllo_incassi_due_fasi(
        data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50))
    return risultato["statistiche"], {g["data"]: g for g in risultato["giorni"]}


# ── 1. XML senza chiusura → credito da XML ──────────────────────────────────

def test_xml_senza_chiusura_apre_il_credito_senza_inventare_il_circuito(monkeypatch):
    db = nuovo_db("cx_apre")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())

    (credito,) = _crediti(db)
    assert D(credito["importo"]) == D("700.00")                       # pagato_elettronico dell'XML
    assert credito["fonte_credito"] == "xml" and credito["senza_chiusura_terminale"] is True
    assert credito["conto_contabile"] == "15.07"                      # gruppo: nessun circuito inventato
    assert credito["gestore"] == "pos_da_xml" and credito["circuito_noto"] is False
    assert credito["natura"] == "credito_pos" and credito["source"] == "trasferimento_pos"
    assert credito["expectation_status"] == "ATTESO" and credito["riconciliato"] is False
    assert credito["in_transito"] is True
    assert credito["stato_credito_xml"] == "senza_chiusura_terminale"
    (corr,) = run(attive(db, "corrispettivi"))
    assert credito["corrispettivo_id"] == corr["id"]
    assert corr["pos_stato"] == "attende_chiusura_pos_reale"          # il terminale manca ancora
    assert corr["credito_pos_xml_stato"] == "senza_chiusura_terminale"
    # Nessun ricavo in piu' e la cassa resta la sola quota contanti.
    assert [D(r["importo"]) for r in run(attive(db, "prima_nota_cassa"))] == [D("300.00")]
    assert len(run(attive(db, "movimenti_contabili"))) == 1


def test_una_chiusura_senza_elettronico_non_apre_nessun_credito(monkeypatch):
    db = nuovo_db("cx_zero")
    Importatore(db, monkeypatch).importa("2701.xml", xml_chiusura(
        progressivo="2701", contanti="1000.00", elettronico="0.00"))
    assert _crediti(db) == []


# ── 2. arriva la chiusura uguale → una riga sola, quella del terminale ──────

def test_la_chiusura_uguale_al_centesimo_sostituisce_il_credito_da_xml(monkeypatch):
    db = nuovo_db("cx_sostituisce")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())
    (da_xml,) = _da_xml(db)

    esito = run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))

    assert esito["credito_xml"]["stato"] == "sostituito_da_chiusura_terminale"
    assert esito["credito_xml"]["differenza"] == 0
    (credito,) = _crediti(db)                                         # UNA riga attiva
    assert credito["gestore"] == "numia" and credito["conto_contabile"] == "15.07.01"
    assert credito.get("fonte_credito") != "xml" and credito["id"] != da_xml["id"]
    assert credito["expectation_status"] == "ATTESO"
    # La riga dell'XML resta per l'audit, ritirata e con il rimando.
    ritirata = run(righe(db, "prima_nota_banca", {"id": da_xml["id"]}))[0]
    assert ritirata["status"] == "archived" and ritirata["sostituito_da"] == credito["id"]
    assert ritirata["deleted_reason"] == "sostituito_da_chiusura_terminale"
    assert ritirata["expectation_status"] == "SUPERATO"
    (corr,) = run(attive(db, "corrispettivi"))
    assert corr["credito_pos_xml_stato"] == "sostituito_da_chiusura_terminale"
    assert corr["pos_stato"] == "pos_reale_disponibile"
    # Il totale dei crediti POS della giornata e' 700, non 1.400.
    assert somma(r["importo"] for r in _crediti(db)) == D("700.00")


def test_due_circuiti_che_sommano_l_xml_lo_sostituiscono_quando_arriva_il_secondo(monkeypatch):
    """Numia 500 + SumUp 200 = XML 700: al primo terminale la differenza e' in
    vista, al secondo l'XML e' sostituito e restano i due crediti per circuito."""
    db = nuovo_db("cx_due_circuiti")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())

    primo = run(registra_chiusura_pos_reale(db, GIORNO, 500.0, gestore="numia"))
    assert primo["credito_xml"]["stato"] == "differenza_con_chiusura_terminale"
    assert D(primo["credito_xml"]["differenza"]) == D("-200.00")
    assert len(_da_xml(db)) == 1

    secondo = run(registra_chiusura_pos_reale(db, GIORNO, 200.0, gestore="sumup", fonte=FONTE_API))
    assert secondo["credito_xml"]["stato"] == "sostituito_da_chiusura_terminale"
    assert _da_xml(db) == []
    assert sorted((r["gestore"], D(r["importo"])) for r in _crediti(db)) == [
        ("numia", D("500.00")), ("sumup", D("200.00"))]


# ── 3. chiusura diversa → il credito resta e la differenza e' segnalata ─────

def test_la_chiusura_diversa_non_sostituisce_e_segnala_la_differenza(monkeypatch):
    db = nuovo_db("cx_differenza")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())

    esito = run(registra_chiusura_pos_reale(db, GIORNO, 650.0, gestore="numia"))

    assert esito["credito_xml"]["stato"] == "differenza_con_chiusura_terminale"
    assert D(esito["credito_xml"]["differenza"]) == D("-50.00")
    (da_xml,) = _da_xml(db)
    assert D(da_xml["differenza_terminale"]) == D("-50.00") and D(da_xml["importo_terminale"]) == D("650.00")
    assert da_xml["stato_credito_xml"] == "differenza_con_chiusura_terminale"
    assert da_xml.get("status") != "archived"                          # resta
    (corr,) = run(attive(db, "corrispettivi"))
    assert corr["credito_pos_xml_stato"] == "differenza_con_chiusura_terminale"
    assert D(corr["credito_pos_xml_differenza"]) == D("-50.00")
    # La Coerenza POS la mette in vista.
    stats, giorni = _coerenza(db, monkeypatch)
    voce = giorni[GIORNO]["credito_pos_da_xml"]
    assert voce["stato"] == "differenza_con_chiusura_terminale"
    assert D(voce["importo"]) == D("700.00") and D(voce["differenza_terminale"]) == D("-50.00")
    assert stats["fase2_crediti_xml_aperti"] == 1 and stats["fase2_crediti_xml_differenza_terminale"] == 1
    # Il terminale, quando c'e', e' l'attesa che l'accredito chiude: non l'XML.
    assert _accredito(db, "ec-1", 650.0) is True
    terminale = next(r for r in _crediti(db) if r["gestore"] == "numia")
    assert terminale["riconciliato"] is True
    assert _da_xml(db)[0]["riconciliato"] is False


# ── 4. accredito → credito chiuso ───────────────────────────────────────────

def test_l_accredito_al_centesimo_chiude_il_credito_da_xml(monkeypatch):
    db = nuovo_db("cx_accredito")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())

    assert _accredito(db, "ec-1", 700.0) is True

    (credito,) = _crediti(db)
    assert credito["fonte_credito"] == "xml" and credito["riconciliato"] is True
    assert credito["expectation_status"] == "SODDISFATTO" and D(credito["accreditato_ec"]) == D("700.00")
    ec = run(db["estratto_conto_movimenti"].find_one({"id": "ec-1"}, {"_id": 0}))
    assert ec["riconciliato"] is True and ec["tipo_riconciliazione"] == "accredito_pos_trasferimento"
    assert len(run(attive(db, "prima_nota_banca"))) == 1            # la banca non crea niente
    stats, giorni = _coerenza(db, monkeypatch)
    assert giorni[GIORNO]["credito_pos_da_xml"]["stato"] == "riconciliato"
    assert stats["fase2_crediti_xml_riconciliati"] == 1 and stats["fase2_crediti_xml_aperti"] == 0


def test_un_accredito_diverso_lascia_il_credito_da_xml_aperto_e_da_verificare(monkeypatch):
    db = nuovo_db("cx_accredito_diverso")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())

    assert _accredito(db, "ec-1", 699.0) is True

    (credito,) = _crediti(db)
    assert credito["riconciliato"] is False and credito["expectation_status"] != "SODDISFATTO"
    ec = run(db["estratto_conto_movimenti"].find_one({"id": "ec-1"}, {"_id": 0}))
    assert ec["riconciliato"] is False and ec["tipo_riconciliazione"] == "accredito_pos_non_quadrato"


def test_la_prova_bancaria_passa_al_terminale_che_sostituisce_il_credito_da_xml(monkeypatch):
    """Accredito prima del terminale: prova il credito da XML. Poi il terminale
    uguale lo sostituisce e EREDITA la prova: l'estratto non resta «riconciliato»
    verso una riga ritirata."""
    db = nuovo_db("cx_prova_passa")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())
    assert _accredito(db, "ec-1", 700.0) is True

    run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))

    (credito,) = _crediti(db)
    assert credito["gestore"] == "numia" and credito["riconciliato"] is True
    assert credito["expectation_status"] == "SODDISFATTO" and credito["estratto_conto_ids"] == ["ec-1"]
    ec = run(db["estratto_conto_movimenti"].find_one({"id": "ec-1"}, {"_id": 0}))
    assert ec["riconciliato"] is True and ec["dettagli_riconciliazione"]["prima_nota_id"] == credito["id"]


def test_il_ricollegamento_storico_chiude_il_credito_da_xml_letto_prima_dell_accredito(monkeypatch):
    db = nuovo_db("cx_storico")
    run(db["estratto_conto_movimenti"].insert_one({
        "id": "ec-1", "data": "2026-09-11", "importo": 700.0, "tipo": "entrata",
        "descrizione_originale": CAUSALE_NUMIA}))
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())

    esito = run(recupera_pos_storico_da_estratto(db, 2026))

    assert esito["componenti_bancarie_ricollegate"] == 1 and esito["creati"] == 0
    (credito,) = _crediti(db)
    assert credito["fonte_credito"] == "xml" and credito["riconciliato"] is True


# ── 5. reimport dell'XML → nessuna seconda riga ─────────────────────────────

def test_il_reimport_dello_stesso_xml_non_apre_un_secondo_credito(monkeypatch):
    db = nuovo_db("cx_reimport")
    imp = Importatore(db, monkeypatch)
    imp.importa("2700.xml", xml_chiusura())
    prima = run(istantanea(db))

    secondo = imp.importa("2700.xml", xml_chiusura())
    terzo = imp.importa("copia.xml", xml_chiusura())

    assert secondo["imported"] == 0 and terzo["imported"] == 0
    assert run(istantanea(db)) == prima
    assert len(_da_xml(db)) == 1


def test_il_reimport_forzato_tiene_la_stessa_riga_e_la_sua_prova(monkeypatch):
    db = nuovo_db("cx_forzato")
    parsed = parsed_chiusura()
    run(ingest_corrispettivo_parsed(db, parsed, "a.xml", "xml"))
    (credito,) = _da_xml(db)
    assert _accredito(db, "ec-1", 700.0) is True

    esito = run(ingest_corrispettivo_parsed(db, parsed, "a.xml", "xml", update_if_exists=True))

    assert esito["action"] == "updated"
    (dopo,) = _crediti(db)
    assert dopo["id"] == credito["id"] and dopo["riconciliato"] is True
    assert len(run(attive(db, "movimenti_contabili"))) == 1


def test_dopo_la_sostituzione_il_reimport_non_riapre_il_credito_da_xml(monkeypatch):
    db = nuovo_db("cx_reimport_dopo")
    imp = Importatore(db, monkeypatch)
    imp.importa("2700.xml", xml_chiusura())
    run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))
    prima = run(istantanea(db, ("corrispettivi", "prima_nota_banca", "movimenti_contabili")))

    imp.importa("2700.xml", xml_chiusura())
    run(ingest_corrispettivo_parsed(db, parsed_chiusura(), "a.xml", "xml", update_if_exists=True))

    # Stessi id in banca (il reimport forzato rigenera solo la cassa): nessun
    # credito da XML riaperto accanto a quello del terminale.
    assert run(istantanea(db, ("corrispettivi", "prima_nota_banca", "movimenti_contabili"))) == prima
    assert _da_xml(db) == [] and len(_crediti(db)) == 1


# ── 6. Coerenza POS evidenzia le giornate con credito da XML non provato ────

def test_la_coerenza_pos_evidenzia_il_credito_da_xml_non_ancora_provato(monkeypatch):
    db = nuovo_db("cx_coerenza")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())

    stats, giorni = _coerenza(db, monkeypatch)

    voce = giorni[GIORNO]["credito_pos_da_xml"]
    assert voce["stato"] == "senza_chiusura_terminale" and voce["riconciliato"] is False
    assert D(voce["importo"]) == D("700.00") and D(voce["accreditato"]) == D("0.00")
    assert stats["fase2_crediti_xml_aperti"] == 1
    assert D(stats["fase2_crediti_xml_aperti_totale"]) == D("700.00")
    # Il POS reale resta assente: l'XML non e' una chiusura del terminale.
    assert giorni[GIORNO]["pos_manuale_presente"] is False
    assert giorni[GIORNO]["stato_accredito"] == "no_pos_manuale"

    run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))
    stats, giorni = _coerenza(db, monkeypatch)
    assert giorni[GIORNO]["credito_pos_da_xml"] is None               # sostituito: non e' piu' un'attesa
    assert stats["fase2_crediti_xml_aperti"] == 0
