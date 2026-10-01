"""Collaudo funzionale: la chiusura RT di una giornata, dall'XML ai registri.

Ogni test e' un'azione dell'utente (Documenti > Import, chiusura del terminale,
secondo import) e verifica il RISULTATO sui dati, secondo CLAUDE.md:

* in Prima Nota Cassa entra **solo la quota contanti**; il POS non muove contante;
* la quota POS diventa un credito verso il gestore in Prima Nota Banca solo
  dalla chiusura **reale del terminale** (mai dall'XML: decisione del 07/08/2026);
* il libro giornale quadra Dare = Avere e i ricavi sono all'**imponibile**;
* il secondo import della stessa fonte non scrive niente (`nuovi = 0`);
* due chiusure vere dello stesso giorno si sommano; una giornata senza
  documento la sostituisce il suo XML solo se i contanti coincidono al centesimo;
* il non riscosso e' la terza gamba del DARE solo se dichiarato **e** la somma
  torna al totale al centesimo, mai per differenza.
"""
from decimal import Decimal

from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed
from app.services.conto_economico_gestionale import ricavi_corrispettivi
from app.services.registrazione_contabile import registra_corrispettivo as registra_in_giornale
from app.services.scritture_contabili import registra_chiusura_pos_reale

from ._comune import (
    D, MATRICOLA, PIVA, Importatore, attive, importo_conto, istantanea, nuovo_db,
    parsed_chiusura, righe, run, somma, totali_scrittura, xml_chiusura,
)

GIORNO = "2026-09-10"


# ── scenario 1: una giornata, contanti 300 + POS 700 ────────────────────────

def test_xml_giornata_cassa_solo_contanti_e_giornale_quadrato(monkeypatch):
    db = nuovo_db("s1_xml")
    imp = Importatore(db, monkeypatch)

    esito = imp.importa("2700_04523831214.xml", xml_chiusura())

    assert esito["tipo_rilevato"] == "corrispettivo" and esito["imported"] == 1
    # Prima Nota Cassa: UNA entrata, la sola quota contanti.
    cassa = run(attive(db, "prima_nota_cassa"))
    assert [(r["tipo"], r["categoria"], D(r["importo"])) for r in cassa] == [
        ("entrata", "Corrispettivi", D("300.00"))]
    # Nessuna uscita POS dalla cassa e nessuna riga da 700 o da 1.000.
    assert not [r for r in cassa if r["tipo"] == "uscita"]
    # Senza chiusura reale del terminale la banca non riceve niente: la quota
    # POS dell'XML non e' un'attesa (l'XML non sa Numia da SumUp).
    assert run(attive(db, "prima_nota_banca")) == []
    (corr,) = run(attive(db, "corrispettivi"))
    assert corr["pos_stato"] == "attende_chiusura_pos_reale"
    assert corr["stato"] == "definitivo_xml" and corr["source"] == "xml"

    # Libro giornale: una scrittura quadrata, ricavi all'IMPONIBILE.
    (scrittura,) = run(attive(db, "movimenti_contabili"))
    dare, avere = totali_scrittura(scrittura)
    assert dare == avere == D("1000.00")
    assert importo_conto(scrittura, "04.01.02", "avere") == D("909.09")   # ricavi = imponibile
    assert importo_conto(scrittura, "02.03.01", "avere") == D("90.91")    # IVA a debito
    assert importo_conto(scrittura, "01.01.01", "dare") == D("300.00")    # cassa = contanti
    assert importo_conto(scrittura, "01.02.01", "dare") == D("0.00")      # nessun non riscosso
    assert D(scrittura["importo_totale"]) == D("1000.00")

    # Il conto economico legge l'imponibile, non il lordo.
    assert run(ricavi_corrispettivi(db, {"$gte": GIORNO, "$lte": GIORNO}))["imponibile"] == 909.09


def test_chiusura_terminale_apre_il_credito_pos_in_banca_senza_toccare_la_cassa(monkeypatch):
    db = nuovo_db("s1_pos")
    imp = Importatore(db, monkeypatch)
    imp.importa("2700_04523831214.xml", xml_chiusura())
    cassa_prima = run(attive(db, "prima_nota_cassa"))

    chiusura = run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))

    assert chiusura["success"] and D(chiusura["importo"]) == D("700.00")
    banca = run(attive(db, "prima_nota_banca"))
    assert len(banca) == 1
    credito = banca[0]
    assert (credito["tipo"], credito["categoria"], credito["source"]) == (
        "entrata", "Corrispettivi POS", "trasferimento_pos")
    assert D(credito["importo"]) == D("700.00")
    # E' un'ATTESA bancaria: ne' riconciliata ne' liquidita' gia' arrivata.
    assert credito["expectation_status"] == "ATTESO" and credito["riconciliato"] is False
    assert credito["in_transito"] is True
    assert credito["trasferimento_id"] == credito["operation_id"]
    # La cassa resta la sola quota contanti: il terminale non la riscrive.
    cassa_dopo = run(attive(db, "prima_nota_cassa"))
    assert [(r["id"], D(r["importo"])) for r in cassa_dopo] == [(r["id"], D(r["importo"])) for r in cassa_prima]
    assert D(cassa_dopo[0]["importo"]) == D("300.00")
    # Il giornale non e' toccato dalla chiusura del terminale.
    assert len(run(attive(db, "movimenti_contabili"))) == 1


def test_chiusura_terminale_prima_dell_xml_da_lo_stesso_risultato(monkeypatch):
    db = nuovo_db("s1_ordine")
    imp = Importatore(db, monkeypatch)
    run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))   # serale, prima dell'XML

    imp.importa("2700_04523831214.xml", xml_chiusura())

    (credito,) = run(attive(db, "prima_nota_banca"))
    assert D(credito["importo"]) == D("700.00") and credito["expectation_status"] == "ATTESO"
    (cassa,) = run(attive(db, "prima_nota_cassa"))
    assert D(cassa["importo"]) == D("300.00")


def test_secondo_import_dello_stesso_xml_non_scrive_niente(monkeypatch):
    db = nuovo_db("s1_secondo")
    imp = Importatore(db, monkeypatch)
    imp.importa("2700_04523831214.xml", xml_chiusura())
    run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))
    prima = run(istantanea(db))

    secondo = imp.importa("2700_04523831214.xml", xml_chiusura())
    terzo = imp.importa("copia_2700.xml", xml_chiusura())      # altro nome, stesso contenuto

    assert secondo["imported"] == 0 and secondo["duplicate"] is True
    assert terzo["imported"] == 0 and terzo["duplicate"] is True
    assert run(istantanea(db)) == prima       # stessi id in tutti i registri: nessuna riga nuova o rimpiazzata


def test_reimport_forzato_non_perde_la_riconciliazione_del_pos(monkeypatch):
    """`POST /corrispettivi/upload-xml` ha `force_update=True` per difetto: il
    reimport rigenera le righe di Prima Nota. Il credito POS nasce dal
    terminale e il suo accredito in banca e' gia' stato provato: non puo'
    tornare «ATTESO» ne' lasciare l'estratto conto «riconciliato» verso una
    riga sparita."""
    from app.services.scritture_contabili import riconcilia_accredito_pos_ec

    db = nuovo_db("s1_forzato")
    parsed = parsed_chiusura()
    run(ingest_corrispettivo_parsed(db, parsed, "a.xml", "xml"))
    run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))
    run(db["estratto_conto_movimenti"].insert_one({
        "id": "ec-1", "data": "2026-09-11", "importo": 700.0,
        "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 10/09/26 PDV 1"}))
    assert run(riconcilia_accredito_pos_ec(
        db, run(db["estratto_conto_movimenti"].find_one({"id": "ec-1"}))))
    (credito,) = run(attive(db, "prima_nota_banca"))
    assert credito["riconciliato"] is True and credito["expectation_status"] == "SODDISFATTO"

    esito = run(ingest_corrispettivo_parsed(db, parsed, "a.xml", "xml", update_if_exists=True))

    assert esito["action"] == "updated"
    (dopo,) = run(attive(db, "prima_nota_banca"))
    assert dopo["id"] == credito["id"]                           # la stessa riga, non una rigenerata
    assert dopo["riconciliato"] is True and dopo["expectation_status"] == "SODDISFATTO"
    assert D(dopo["accreditato_ec"]) == D("700.00")
    assert len(run(attive(db, "movimenti_contabili"))) == 1      # e nessuna scrittura nuova
    (cassa,) = run(attive(db, "prima_nota_cassa"))
    assert D(cassa["importo"]) == D("300.00")


# ── scenario 3: due chiusure, giornata senza documento ──────────────────────

def test_due_chiusure_vere_dello_stesso_giorno_si_sommano(monkeypatch):
    db = nuovo_db("s3_due")
    imp = Importatore(db, monkeypatch)
    prima = xml_chiusura(data="2026-09-06", progressivo="2637", contanti="132.30",
                         elettronico="465.10", imponibile="543.09", imposta="54.31")
    seconda = xml_chiusura(data="2026-09-06", progressivo="2638", contanti="400.00",
                           elettronico="1199.50", imponibile="1454.09", imposta="145.41")
    imp.importa("2637.xml", prima)
    imp.importa("2638.xml", seconda)
    ancora = imp.importa("2638_bis.xml", seconda)

    assert ancora["duplicate"] is True
    righe_corr = run(attive(db, "corrispettivi"))
    assert len(righe_corr) == 2
    assert somma(r["totale"] for r in righe_corr) == D("2196.90")
    # Cassa: le DUE quote contanti, la seconda non cancella la prima.
    cassa = run(attive(db, "prima_nota_cassa"))
    assert sorted(D(r["importo"]) for r in cassa) == [D("132.30"), D("400.00")]
    # Giornale: una scrittura quadrata per chiusura; ricavi = somma degli imponibili.
    scritture = run(attive(db, "movimenti_contabili"))
    assert len(scritture) == 2
    for s in scritture:
        dare, avere = totali_scrittura(s)
        assert dare == avere
    assert somma(importo_conto(s, "04.01.02", "avere") for s in scritture) == D("1997.18")
    assert run(ricavi_corrispettivi(db, {"$gte": "2026-09-06", "$lte": "2026-09-06"}))["imponibile"] == 1997.18


def _storica(**campi):
    """La giornata come l'archivio legacy la conserva: niente progressivo,
    matricola o chiave XML."""
    base = {"id": "606", "data": GIORNO, "totale": 1000.0, "pagato_contanti": 300.0,
            "pagato_elettronico": 700.0, "totale_imponibile": 909.09, "totale_iva": 90.91,
            "status": "DA_VERIFICARE", "fonte": "legacy_staging_2026"}
    base.update(campi)
    return base


async def _con_storica(db, storica):
    from app.routers.invoices.corrispettivi_helpers import (
        _create_prima_nota_movements, _registra_in_partita_doppia,
    )

    await db["corrispettivi"].insert_one(dict(storica))
    await _create_prima_nota_movements(db, storica)
    await _registra_in_partita_doppia(db, storica)


def test_xml_sostituisce_la_giornata_senza_documento_se_i_contanti_coincidono(monkeypatch):
    db = nuovo_db("s3_storica")
    run(_con_storica(db, _storica()))
    imp = Importatore(db, monkeypatch)

    imp.importa("2700.xml", xml_chiusura())

    attivi = run(attive(db, "corrispettivi"))
    assert len(attivi) == 1 and attivi[0]["source"] == "xml"
    vecchia = run(righe(db, "corrispettivi", {"id": "606"}))[0]
    assert vecchia["status"] == "deleted" and vecchia["sostituito_da"] == attivi[0]["id"]
    # Contanti una volta sola, non 600.
    cassa = run(attive(db, "prima_nota_cassa"))
    assert [D(r["importo"]) for r in cassa] == [D("300.00")]
    # Giornale: la scrittura della storica e' STORNATA (non cancellata), resta la nuova.
    tutte = run(righe(db, "movimenti_contabili"))
    assert sorted(m["tipo"] for m in tutte) == ["corrispettivo", "corrispettivo", "storno_corrispettivo"]
    # Il giornale somma TUTTE le scritture: storica e storno si annullano, resta la nuova.
    def netto(conto, lato_pos, lato_neg):
        return (somma(importo_conto(m, conto, lato_pos) for m in tutte)
                - somma(importo_conto(m, conto, lato_neg) for m in tutte))

    assert netto("04.01.02", "avere", "dare") == D("909.09")      # ricavi contati una volta
    assert netto("02.03.01", "avere", "dare") == D("90.91")       # IVA a debito una volta
    assert netto("01.01.01", "dare", "avere") == D("300.00")      # cassa una volta
    attiva = [m for m in tutte if m["tipo"] == "corrispettivo" and m.get("stato") != "stornato"]
    assert len(attiva) == 1 and attiva[0]["corrispettivo_id"] == attivi[0]["id"]


def test_giornata_senza_documento_con_contanti_diversi_non_si_sostituisce_in_silenzio(monkeypatch):
    """Solo i contanti al centesimo provano che e' la stessa chiusura: con 299,99
    la riga storica resta (il totale non basta, e la sola data nemmeno)."""
    db = nuovo_db("s3_diversa")
    run(_con_storica(db, _storica(pagato_contanti=299.99, pagato_elettronico=700.01)))
    imp = Importatore(db, monkeypatch)

    imp.importa("2700.xml", xml_chiusura())

    vecchia = run(righe(db, "corrispettivi", {"id": "606"}))[0]
    assert vecchia["status"] == "DA_VERIFICARE" and "sostituito_da" not in vecchia


def test_il_pos_della_giornata_senza_documento_passa_alla_chiusura_che_la_sostituisce(monkeypatch):
    """La giornata storica aveva il suo credito POS (dal terminale): quando l'XML
    la sostituisce il credito non puo' sparire dalla Prima Nota Banca."""
    db = nuovo_db("s3_pos_storica")
    run(_con_storica(db, _storica()))
    run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))
    imp = Importatore(db, monkeypatch)

    imp.importa("2700.xml", xml_chiusura())

    (nuova,) = run(attive(db, "corrispettivi"))
    banca = run(attive(db, "prima_nota_banca"))
    assert [(D(r["importo"]), r["source"]) for r in banca] == [(D("700.00"), "trasferimento_pos")]
    assert banca[0]["corrispettivo_id"] == nuova["id"]
    assert banca[0]["expectation_status"] == "ATTESO"


# ── scenario 4: non riscosso ────────────────────────────────────────────────

def _parsed_non_riscosso(*, contanti, elettronico, non_riscosso, totale):
    return {
        "corrispettivo_key": f"{PIVA}_{GIORNO}_{MATRICOLA}_2701", "data": GIORNO,
        "matricola_rt": MATRICOLA, "numero_documento": "2701", "partita_iva": PIVA,
        "pagato_contanti": contanti, "pagato_elettronico": elettronico,
        "pagato_non_riscosso": non_riscosso, "totale": totale,
        "totale_imponibile": 909.09, "totale_iva": 90.91, "numero_documenti": 12,
    }


def test_non_riscosso_dichiarato_e_terza_gamba_del_dare_sui_crediti():
    db = nuovo_db("s4_ok")
    esito = run(ingest_corrispettivo_parsed(db, _parsed_non_riscosso(
        contanti=300.0, elettronico=600.0, non_riscosso=100.0, totale=1000.0), "a.xml", "xml"))

    assert esito["action"] == "created"
    # Cassa: SOLO i contanti. Il non riscosso non e' denaro.
    assert [D(r["importo"]) for r in run(attive(db, "prima_nota_cassa"))] == [D("300.00")]
    (s,) = run(attive(db, "movimenti_contabili"))
    dare, avere = totali_scrittura(s)
    assert dare == avere == D("1000.00")
    assert importo_conto(s, "01.01.01", "dare") == D("300.00")
    assert importo_conto(s, "01.02.01", "dare") == D("100.00")       # crediti v/clienti
    assert importo_conto(s, "04.01.02", "avere") == D("909.09")      # il ricavo c'e' tutto


def test_non_riscosso_che_non_fa_il_totale_scarta_la_giornata_con_il_motivo():
    """Cassa 300 + POS 600 + non riscosso 50 = 950 su un totale di 1.000: lo scarto
    di 50 non si inventa come non riscosso. Mai per differenza."""
    db = nuovo_db("s4_scarto")
    run(ingest_corrispettivo_parsed(db, _parsed_non_riscosso(
        contanti=300.0, elettronico=600.0, non_riscosso=50.0, totale=1000.0), "a.xml", "xml"))

    assert run(attive(db, "movimenti_contabili")) == []          # fuori dal giornale
    (corr,) = run(attive(db, "corrispettivi"))
    esito = corr["registrazione_contabile_esito"]
    assert esito["stato"] == "da_verificare"
    assert "non quadrata" in esito["motivo"]                      # il perche' e' scritto sul documento
    assert not corr.get("registrato_contabilita")


def test_scarto_senza_nessuna_voce_dichiarata_si_scarta():
    """Contanti + POS = 900 su un totale di 1.000, nessun non riscosso dichiarato:
    quei 100 non si caricano ne' sulla cassa ne' sui crediti."""
    db = nuovo_db("s4_senza_voce")
    run(ingest_corrispettivo_parsed(db, _parsed_non_riscosso(
        contanti=300.0, elettronico=600.0, non_riscosso=0.0, totale=1000.0), "a.xml", "xml"))

    assert run(attive(db, "movimenti_contabili")) == []
    (corr,) = run(attive(db, "corrispettivi"))
    assert corr["registrazione_contabile_esito"]["stato"] == "da_verificare"


def test_non_riscosso_negativo_non_entra():
    db = nuovo_db("s4_negativo")
    corr = {"id": "c1", "data": GIORNO, "totale": 1000.0, "pagato_contanti": 1100.0,
            "pagato_elettronico": 0.0, "pagato_non_riscosso": -100.0,
            "totale_imponibile": 909.09, "totale_iva": 90.91}
    run(db["corrispettivi"].insert_one(dict(corr)))
    esito = run(registra_in_giornale(db, corr))
    assert esito["stato"] == "da_verificare" and "negativo" in esito["motivo"]
    assert run(attive(db, "movimenti_contabili")) == []


def test_xml_con_lordo_dei_riepiloghi_oltre_l_incassato_mai_registrato_sbilanciato(monkeypatch):
    """Il totale dell'XML e' l'INCASSATO (contanti + elettronico); se imponibile + IVA
    del riepilogo lo superano lo scarto resta fuori. Qualunque sia l'esito (giornata
    scartata con motivo, o registrata col non riscosso) il giornale non deve mai
    contenere una scrittura sbilanciata e il motivo deve stare sul documento."""
    db = nuovo_db("s4_xml_lordo")
    imp = Importatore(db, monkeypatch)
    imp.importa("2702.xml", xml_chiusura(progressivo="2702", imponibile="1000.00", imposta="100.00"))

    for s in run(attive(db, "movimenti_contabili")):
        dare, avere = totali_scrittura(s)
        assert dare == avere
    (corr,) = run(attive(db, "corrispettivi"))
    assert D(corr["pagato_non_riscosso"]) == D("100.00")
    if not run(attive(db, "movimenti_contabili")):
        assert corr["registrazione_contabile_esito"]["stato"] == "da_verificare"


def test_la_chiusura_del_terminale_dopo_la_sostituzione_si_aggancia_alla_giornata_viva(monkeypatch):
    """La giornata storica ritirata resta in archivio (`status: deleted`) per l'audit:
    il POS che arriva DOPO l'XML riguarda la chiusura viva, non la riga ritirata."""
    db = nuovo_db("s3_pos_dopo")
    run(_con_storica(db, _storica()))
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())
    (viva,) = run(attive(db, "corrispettivi"))

    run(registra_chiusura_pos_reale(db, GIORNO, 700.0, gestore="numia"))

    (credito,) = run(attive(db, "prima_nota_banca"))
    assert credito["corrispettivo_id"] == viva["id"]
    (viva_dopo,) = run(attive(db, "corrispettivi"))
    assert D(viva_dopo["pos_reale_serale"]) == D("700.00") and viva_dopo["pos_stato"] == "pos_reale_disponibile"
    ritirata = run(righe(db, "corrispettivi", {"id": "606"}))[0]
    assert "pos_reale_serale" not in ritirata                       # la riga ritirata non si tocca piu'


# ── chiusura manuale serale, poi l'XML ──────────────────────────────────────

def _manuale(db, monkeypatch, totale, pos):
    from app.database import Database
    from app.routers.invoices import corrispettivi as router_corr

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    return run(router_corr.inserisci_corrispettivo_manuale(
        {"data": GIORNO, "totale": totale, "pos_reale_serale": pos}))


def test_chiusura_manuale_serale_poi_xml_non_raddoppia_cassa_e_conserva_il_pos(monkeypatch):
    """La sera il titolare scrive totale 1.000 e POS 700: cassa 300, credito POS 700,
    niente giornale (provvisorio). Il giorno dopo arriva l'XML: la stessa giornata diventa
    definitiva, i contanti restano 300 (una volta), il credito POS non cambia e il giornale
    registra la giornata una volta sola."""
    from app.services.scritture_contabili import riconcilia_accredito_pos_ec

    db = nuovo_db("s2_manuale_xml")
    imp = Importatore(db, monkeypatch)
    sera = _manuale(db, monkeypatch, 1000.0, 700.0)
    assert sera["stato"] == "provvisorio"
    assert [D(r["importo"]) for r in run(attive(db, "prima_nota_cassa"))] == [D("300.00")]
    (credito,) = run(attive(db, "prima_nota_banca"))
    assert D(credito["importo"]) == D("700.00")
    assert run(attive(db, "movimenti_contabili")) == []            # provvisorio: fuori dal giornale
    # L'accredito della banca arriva prima dell'XML e chiude il credito.
    run(db["estratto_conto_movimenti"].insert_one({
        "id": "ec-1", "data": "2026-09-11", "importo": 700.0,
        "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 10/09/26 PDV 1"}))
    assert run(riconcilia_accredito_pos_ec(db, run(db["estratto_conto_movimenti"].find_one({"id": "ec-1"}))))

    imp.importa("2700.xml", xml_chiusura())

    (corr,) = run(attive(db, "corrispettivi"))
    assert corr["id"] == sera["corrispettivo_id"] and corr["stato"] == "definitivo_xml"
    assert D(corr["totale_manuale"]) == D("1000.00")                # il dato serale resta come storico
    assert [D(r["importo"]) for r in run(attive(db, "prima_nota_cassa"))] == [D("300.00")]
    (credito_dopo,) = run(attive(db, "prima_nota_banca"))
    assert credito_dopo["id"] == credito["id"] and credito_dopo["riconciliato"] is True
    (scrittura,) = run(attive(db, "movimenti_contabili"))
    assert totali_scrittura(scrittura) == (D("1000.00"), D("1000.00"))


def test_xml_promuove_la_chiusura_manuale_anche_se_il_totale_serale_e_diverso(monkeypatch):
    """La sera si digita 1.010 (un errore di battitura, un resto), l'RT chiude a 1.000:
    e' la stessa giornata. Prima l'XML nasceva come SECONDA riga e in Prima Nota Cassa
    i contanti entravano due volte (310 manuali + 300 dell'XML)."""
    db = nuovo_db("s2_manuale_diversa")
    imp = Importatore(db, monkeypatch)
    sera = _manuale(db, monkeypatch, 1010.0, 700.0)
    assert [D(r["importo"]) for r in run(attive(db, "prima_nota_cassa"))] == [D("310.00")]

    imp.importa("2700.xml", xml_chiusura())                         # RT: contanti 300 + POS 700 = 1.000

    (corr,) = run(attive(db, "corrispettivi"))                      # UNA giornata, non due
    assert corr["id"] == sera["corrispettivo_id"] and corr["stato"] == "definitivo_xml"
    assert D(corr["totale"]) == D("1000.00") and D(corr["totale_manuale"]) == D("1010.00")
    cassa = run(attive(db, "prima_nota_cassa"))
    assert [D(r["importo"]) for r in cassa] == [D("300.00")]        # i contanti dell'RT, una volta
    (credito,) = run(attive(db, "prima_nota_banca"))
    assert D(credito["importo"]) == D("700.00")                     # il POS del terminale non cambia
    (scrittura,) = run(attive(db, "movimenti_contabili"))
    assert totali_scrittura(scrittura) == (D("1000.00"), D("1000.00"))


def test_una_chiusura_xml_vuota_non_promuove_la_chiusura_manuale(monkeypatch):
    db = nuovo_db("s2_manuale_vuota")
    imp = Importatore(db, monkeypatch)
    sera = _manuale(db, monkeypatch, 1010.0, 700.0)

    imp.importa("2701.xml", xml_chiusura(progressivo="2701", contanti="0.00", elettronico="0.00",
                                         imponibile="0.00", imposta="0.00", documenti_n=0))

    manuale = run(righe(db, "corrispettivi", {"id": sera["corrispettivo_id"]}))[0]
    assert manuale["stato"] == "provvisorio" and manuale["source"] == "manuale_serale"


def test_la_chiusura_manuale_su_una_giornata_gia_definitiva_e_rifiutata_anche_con_una_riga_ritirata(monkeypatch):
    """La giornata storica sostituita dall'XML resta `deleted` per l'audit: non deve far
    passare un inserimento manuale sopra il dato fiscale ne' farlo scrivere sulla riga morta."""
    import pytest
    from fastapi import HTTPException

    db = nuovo_db("s2_manuale_su_definitiva")
    run(_con_storica(db, _storica()))
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())      # ritira la storica 606
    prima = run(istantanea(db))

    with pytest.raises(HTTPException) as errore:
        _manuale(db, monkeypatch, 1010.0, 700.0)

    assert errore.value.status_code == 409
    assert run(istantanea(db)) == prima
    assert "totale_manuale" not in run(righe(db, "corrispettivi", {"id": "606"}))[0]
