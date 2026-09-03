"""
test_audit_tranche6.py — AUDIT_IMPORT_DATABASE (tranche 6, 24/07/2026).

Tutto su MONGO DI PROVA (mongomock-motor, DB "Gestionale_Test"): nessuna
connessione di rete, MAI il database di produzione `Gestionale`.

Copre:
  1. Import fatture XML: contatori ricevuti/salvati, dedup per riga
     (lotti_fornitori), record incompleti scartati con errore segnalato.
  2. Catena relazionale: fattura → lotti_fornitori (fattura_ref) → consumo
     FIFO (storico_utilizzi.lotto_produzione) → lotto di produzione
     (crea_lotto + movimenti_lotto) → manda-al-banco (vendite_banco).
  3. Scheduler temperature (AUTOMATICHE): generazione giornaliera,
     deduplicazione (secondo giro non sovrascrive), valori SEMPRE entro le
     soglie della scheda (fix clamp congelatori), soglie congelate nel record.
  4. Anomalie temperature: un fuori-soglia NON sparisce se le soglie vengono
     cambiate retroattivamente (fix soglie congelate).
  5. Registri/stampe generati DAVVERO e confrontati col DB: report HACCP
     mensile (giorni mancanti = "N/D — Dato non disponibile", mai righe
     saltate), registro lotti mensile/annuale/CSV, registro lotti ASL
     (niente troncamento a 2000), export sanificazione.
"""
import os
os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")  # SOLO db di prova

import asyncio
from datetime import datetime, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def dbmock(monkeypatch):
    """Mongo FINTO per tutti i router/servizi (stessa fixture di
    test_e2e_flussi.py): qualunque modulo con attributo `db` viene puntato su
    Gestionale_Test. Bus eventi disattivato."""
    import importlib, pkgutil
    import app.lotti.routers as routers  # noqa
    cli = AsyncMongoMockClient()
    db = cli["Gestionale_Test"]
    for m in pkgutil.iter_modules(routers.__path__):
        try:
            mod = importlib.import_module(f"app.lotti.routers.{m.name}")
        except Exception:
            continue
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", db, raising=False)
    import app.lotti.db as dbmod
    monkeypatch.setattr(dbmod, "database", db, raising=False)
    import app.lotti.eventi as eventi
    async def _pub(*a, **k):
        return None

    monkeypatch.setattr(eventi, "publish", _pub, raising=False)
    try:
        import app.lotti.servizi as servizi
        for m in pkgutil.iter_modules(servizi.__path__):
            try:
                mod = importlib.import_module(f"app.lotti.servizi.{m.name}")
            except Exception:
                continue
            if hasattr(mod, "db"):
                monkeypatch.setattr(mod, "db", db, raising=False)
    except Exception:
        pass
    # azienda.py (intestazioni stampe) usa un suo `db`
    import app.lotti.azienda as azienda
    monkeypatch.setattr(azienda, "db", db, raising=False)
    return db


# ── XML fattura di prova (2 righe, una descrizione vuota opzionale) ─────────
def _xml_fattura(numero="123/A", piva="01234567890", data="2026-07-01",
                 righe=None):
    if righe is None:
        righe = [("FARINA 00 SACCO KG 25", "4.00", "KG", "20.00", "80.00"),
                 ("ZUCCHERO SEMOLATO KG 10", "2.00", "KG", "10.00", "20.00")]
    dettagli = ""
    for i, (desc, qta, um, pu, tot) in enumerate(righe, 1):
        dettagli += f"""<DettaglioLinee>
    <NumeroLinea>{i}</NumeroLinea>
    <Descrizione>{desc}</Descrizione>
    <Quantita>{qta}</Quantita>
    <UnitaMisura>{um}</UnitaMisura>
    <PrezzoUnitario>{pu}</PrezzoUnitario>
    <PrezzoTotale>{tot}</PrezzoTotale>
   </DettaglioLinee>"""
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<p:FatturaElettronica xmlns:p='x' versione='FPR12'>
 <FatturaElettronicaHeader>
  <CedentePrestatore>
   <DatiAnagrafici>
    <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{piva}</IdCodice></IdFiscaleIVA>
    <Anagrafica><Denominazione>MOLINO TEST SRL</Denominazione></Anagrafica>
   </DatiAnagrafici>
  </CedentePrestatore>
 </FatturaElettronicaHeader>
 <FatturaElettronicaBody>
  <DatiGenerali><DatiGeneraliDocumento>
    <Numero>{numero}</Numero><Data>{data}</Data>
    <ImportoTotaleDocumento>100.00</ImportoTotaleDocumento>
  </DatiGeneraliDocumento></DatiGenerali>
  <DatiBeniServizi>
   {dettagli}
  </DatiBeniServizi>
 </FatturaElettronicaBody>
</p:FatturaElettronica>""".encode()


def _upload(nome, contenuto):
    import io
    from starlette.datastructures import UploadFile
    return UploadFile(file=io.BytesIO(contenuto), filename=nome)


# ════════════════════════ 1. IMPORT: contatori e scarti ═════════════════════

def test_import_contatori_righe_e_dedup_per_riga(dbmock):
    import app.lotti.routers.fatture as fat
    ris = run(fat.importa_fattura_xml(files=[_upload("f.xml", _xml_fattura())]))
    assert ris["fatture_processate"] == 1
    assert ris["prodotti_trovati"] == 2
    assert ris["nuove_materie"] == 2, "una riga fattura = un lotto fornitore"
    assert run(dbmock.lotti_fornitori.count_documents({})) == 2

    # Re-import della STESSA fattura: nessun lotto fornitore in più
    run(fat.importa_fattura_xml(files=[_upload("f2.xml", _xml_fattura())]))
    assert run(dbmock.fatture.count_documents({})) == 1
    assert run(dbmock.lotti_fornitori.count_documents({})) == 2, \
        "dedup per riga (fattura_ref+fornitore+prodotto_nome) violata"

    # Collegamenti creati dall'import: listino e dizionario prodotti
    assert run(dbmock.listino_prodotti.count_documents({})) == 2
    diz = run(dbmock.dizionario_prodotti.find({}).to_list(50))
    assert diz, "l'import deve aggiornare dizionario_prodotti (giacenze/prezzi)"


def test_import_fattura_senza_fornitore_scartata_con_errore(dbmock):
    import app.lotti.routers.fatture as fat
    xml = _xml_fattura().replace(
        b"<Anagrafica><Denominazione>MOLINO TEST SRL</Denominazione></Anagrafica>", b"")
    ris = run(fat.importa_fattura_xml(files=[_upload("rotta.xml", xml)]))
    assert ris["fatture_processate"] == 0
    assert ris["errori"], "il file scartato deve comparire negli errori, non sparire"
    assert run(dbmock.fatture.count_documents({})) == 0
    assert run(dbmock.lotti_fornitori.count_documents({})) == 0


def test_import_file_non_xml_segnalato(dbmock):
    import app.lotti.routers.fatture as fat
    ris = run(fat.importa_fattura_xml(files=[_upload("x.xml", b"non sono xml")]))
    assert ris["fatture_processate"] == 0
    assert ris["errori"]


# ═════════════ 2. CATENA: fattura → FIFO → produzione → banco ═══════════════

def test_catena_completa_chiavi_reali(dbmock):
    import app.lotti.routers.fatture as fat
    import app.lotti.routers.lotti_produzione as lp
    from app.lotti.servizi.lotti_service import crea_lotto

    # 1) fattura → lotti_fornitori con fattura_ref
    run(fat.importa_fattura_xml(files=[_upload("f.xml", _xml_fattura(
        numero="777", righe=[("FARINA 00 SACCO KG 25", "10.00", "KG", "20.00", "200.00")]))]))
    lf = run(dbmock.lotti_fornitori.find_one({}))
    assert lf["fattura_ref"] == "777", "lotti_fornitori.fattura_ref deve puntare al numero fattura"

    # 2) consumo FIFO con numero lotto di produzione reale
    ricetta = {"nome": "Pane di prova",
               "ingredienti_dettaglio": [{"nome": "Farina 00", "quantita": 500,
                                          "unita_misura": "g"}]}
    esito = run(lp.scala_lotti_fornitori_per_ricetta(ricetta, 1, "PANE-001-10pz-24072026"))
    assert esito["lotti_scalati"], esito
    lf2 = run(dbmock.lotti_fornitori.find_one({}))
    assert lf2["storico_utilizzi"][0]["lotto_produzione"] == "PANE-001-10pz-24072026", \
        "l'anello lotto fornitore → lotto di produzione è storico_utilizzi[].lotto_produzione"

    # 3) lotto di produzione (unico punto di scrittura: servizi.lotti_service.crea_lotto)
    lotto = run(crea_lotto({
        "prodotto": "Pane di prova", "numero_lotto": "PANE-001-10pz-24072026",
        "quantita": 10, "unita_misura": "pz", "data_produzione": "24/07/2026",
        "data_scadenza": "26/07/2026", "frigo_numero": "Frigo 1",
        "lotti_fornitori": esito, "operatore_id": "op1", "operatore_nome": "Mario",
    }, origine="produzione"))
    mov = run(dbmock.movimenti_lotto.find({"lotto_id": lotto["id"]}).to_list(10))
    assert any(m["tipo_evento"] == "creazione" for m in mov), \
        "ogni lotto creato deve avere l'evento 'creazione' in movimenti_lotto"

    # 4) manda al banco → vendite_banco + movimento 'banco' collegati per chiave
    r = run(lp.manda_lotto_al_banco(lotto["id"], pezzi=4, reparto="pasticceria",
                                    operatore_id="op1", operatore_nome="Mario",
                                    operation_id=None))
    assert r["status"] == "ok"
    vend = run(dbmock.vendite_banco.find_one({}))
    assert vend["lotto_id"] == lotto["id"]
    assert vend["numero_lotto"] == "PANE-001-10pz-24072026"
    doc = run(dbmock.lotti.find_one({"id": lotto["id"]}))
    assert doc["quantita"] == 6
    mov2 = run(dbmock.movimenti_lotto.find({"lotto_id": lotto["id"],
                                            "tipo_evento": "banco"}).to_list(10))
    assert mov2 and mov2[0]["documento_collegato"]["tipo"] == "vendita_banco"
    assert mov2[0]["documento_collegato"]["id"] == vend["id"]


def test_registra_produzione_scrive_produzioni_e_lotto_collegati(dbmock):
    """Endpoint completo con ingrediente SCONOSCIUTO (niente scarico FIFO:
    l'update con array_filters non è supportato da mongomock — il ramo con
    scarico reale è coperto sopra chiamando le stesse funzioni interne)."""
    import app.lotti.routers.lotti_produzione as lp
    run(dbmock.ricette.insert_one({
        "id": "R1", "nome": "Torta di prova", "porzioni": 10,
        "ingredienti_dettaglio": [{"nome": "Polvere di unicorno", "quantita": 100,
                                   "unita_misura": "g"}]}))
    lotto = run(lp.registra_produzione_e_crea_lotto(
        ricetta_id="R1", pezzi=10, pezzi_base=10, costo_totale=5.0,
        data_produzione="2026-07-24", frigo_numero="Frigo 2",
        lotti_componenti_json=None, operatore_id="op1", operatore_nome="Mario",
        data_scadenza=None, memorizza_durata=False, operation_id=None))
    assert lotto.get("numero_lotto")
    prod = run(dbmock.produzioni.find_one({}))
    assert prod["numero_lotto"] == lotto["numero_lotto"], \
        "produzioni.numero_lotto deve combaciare con lotti.numero_lotto"
    assert prod["ricetta_id"] == "R1"
    assert prod["operatore_nome"] == "Mario", "ogni produzione dice CHI l'ha fatta"
    assert lotto["lotti_fornitori"]["ingredienti_non_trovati"] == ["Polvere di unicorno"]


# ═════════════ 3. SCHEDULER TEMPERATURE (automatiche) ═══════════════════════

def _seed_schede_temperature(dbmock, anno):
    run(dbmock.temperature_positive.insert_one({
        "id": "TP1", "anno": anno, "frigorifero_numero": 1,
        "frigorifero_nome": "Frigorifero N°1",
        "temperature": {str(m): {} for m in range(1, 13)},
        "temp_min": 0.0, "temp_max": 4.0}))
    # congelatore 8: base -17.5 nel generatore → caso critico del vecchio clamp
    run(dbmock.temperature_negative.insert_one({
        "id": "TN8", "anno": anno, "congelatore_numero": 8,
        "congelatore_nome": "Congelatore N°8",
        "temperature": {str(m): {} for m in range(1, 13)},
        "temp_min": -22.0, "temp_max": -18.0}))


def test_scheduler_temperature_genera_e_non_duplica(dbmock):
    from app.lotti.routers.haccp_auto import verifica_e_popola_oggi
    oggi = datetime.now(timezone.utc)
    _seed_schede_temperature(dbmock, oggi.year)

    r1 = run(verifica_e_popola_oggi())
    assert r1["generato"] is True
    tp = run(dbmock.temperature_positive.find_one({"id": "TP1"}))
    rec = tp["temperature"][str(oggi.month)][str(oggi.day)]
    assert rec["auto"] is True and rec["temp"] is not None

    # DEDUP: secondo giro nello stesso giorno → non tocca il dato esistente
    run(dbmock.temperature_positive.update_one(
        {"id": "TP1"},
        {"$set": {f"temperature.{oggi.month}.{oggi.day}.note": "SENTINELLA"}}))
    r2 = run(verifica_e_popola_oggi())
    assert r2["generato"] is False, "già compilato: il job non deve rigenerare"
    tp2 = run(dbmock.temperature_positive.find_one({"id": "TP1"}))
    assert tp2["temperature"][str(oggi.month)][str(oggi.day)]["note"] == "SENTINELLA"


def test_scheduler_temperature_sempre_entro_soglie_scheda(dbmock):
    """FIX audit: il vecchio clamp min(-15.0, …) generava letture automatiche
    SOPRA la soglia massima (-18 °C) per i congelatori con base -17.5/-18.3."""
    from app.lotti.routers.haccp_auto import verifica_e_popola_oggi
    oggi = datetime.now(timezone.utc)
    _seed_schede_temperature(dbmock, oggi.year)
    run(verifica_e_popola_oggi())

    tp = run(dbmock.temperature_positive.find_one({"id": "TP1"}))
    rec_p = tp["temperature"][str(oggi.month)][str(oggi.day)]
    assert 0.0 <= rec_p["temp"] <= 4.0
    assert rec_p["soglie"] == {"min": 0.0, "max": 4.0}
    assert rec_p["allarme"] is False

    tn = run(dbmock.temperature_negative.find_one({"id": "TN8"}))
    rec_n = tn["temperature"][str(oggi.month)][str(oggi.day)]
    assert -22.0 <= rec_n["temp"] <= -18.0, \
        f"lettura automatica fuori soglia: {rec_n['temp']} (max -18.0)"
    assert rec_n["soglie"] == {"min": -22.0, "max": -18.0}


# ═════ 4. ANOMALIE: mai cancellate da un cambio retroattivo di soglie ═══════

def test_allarme_non_sparisce_cambiando_le_soglie(dbmock):
    import app.lotti.routers.temperature_positive as tpos
    anno = 2026
    # registrazione FUORI soglia (6.5 °C con max 4.0) → allarme
    r = run(tpos.registra_temperatura(anno, 1, mese=7, giorno=10, temperatura=6.5,
                                      operatore="Mario", note="", azione_correttiva=""))
    assert r["allarme"] is True
    allarmi = run(tpos.get_allarmi(anno))
    assert len(allarmi) == 1 and allarmi[0]["temperatura"] == 6.5

    # l'admin ALLARGA le soglie a posteriori (0..10): l'anomalia storica RESTA
    run(tpos.configura_frigorifero(anno, 1, nome=None, temp_min=None,
                                   temp_max=10.0, _admin=None))
    allarmi2 = run(tpos.get_allarmi(anno))
    assert len(allarmi2) == 1, \
        "REGOLA TASSATIVA: l'anomalia non deve sparire cambiando le soglie retroattivamente"
    assert "4" in allarmi2[0]["range"], "il range mostrato è quello del momento della lettura"

    # e viceversa: una lettura CONFORME non diventa anomalia stringendo le soglie
    run(tpos.registra_temperatura(anno, 1, mese=7, giorno=11, temperatura=3.0,
                                  operatore="Mario", note="", azione_correttiva=""))
    run(tpos.configura_frigorifero(anno, 1, nome=None, temp_min=None,
                                   temp_max=2.0, _admin=None))
    allarmi3 = run(tpos.get_allarmi(anno))
    assert len(allarmi3) == 1, "la lettura 3.0 (conforme quando fu presa) non deve diventare anomalia"


def test_allarme_congelatore_congela_soglie(dbmock):
    import app.lotti.routers.temperature_negative as tneg
    anno = 2026
    r = run(tneg.registra_temperatura(anno, 1, mese=7, giorno=10, temperatura=-15.0,
                                      operatore="Mario", note=""))
    assert r["allarme"] is True
    run(tneg.configura_congelatore(anno, 1, nome=None, temp_min=None,
                                   temp_max=-10.0, _admin=None))
    assert len(run(tneg.get_allarmi(anno))) == 1


# ═════ 5. REGISTRI/STAMPE: generate davvero e confrontate col DB ════════════

def test_report_haccp_mensile_giorni_mancanti_e_righe_mai_saltate(dbmock):
    from app.lotti.routers.report_haccp import report_haccp_mensile
    anno, mese = 2026, 7  # luglio = 31 giorni
    run(dbmock.temperature_positive.insert_one({
        "id": "TP1", "anno": anno, "frigorifero_numero": 1,
        "frigorifero_nome": "Frigorifero N°1",
        "temp_min": 0.0, "temp_max": 4.0,
        "temperature": {"7": {
            "1": {"temp": 3.0, "soglie": {"min": 0.0, "max": 4.0}},
            "2": {"temp": 8.0, "soglie": {"min": 0.0, "max": 10.0}},  # conforme ALLORA
        }}}))
    # scheda SENZA alcuna rilevazione nel mese: la riga NON deve sparire
    run(dbmock.temperature_positive.insert_one({
        "id": "TP2", "anno": anno, "frigorifero_numero": 2,
        "frigorifero_nome": "Frigorifero N°2",
        "temp_min": 0.0, "temp_max": 4.0,
        "temperature": {"7": {}}}))

    html = run(report_haccp_mensile(anno=anno, mese=mese)).body.decode()

    assert "Frigorifero N°1" in html
    assert "Frigorifero N°2" in html, "apparecchio senza dati nel mese: riga SALTATA nella stampa"
    # giorni senza dato dichiarati, mai celle vuote: (31-2) + 31 = 60 celle N/D
    celle_nd = html.count('title="Dato non disponibile"')
    assert celle_nd == 60, f"attese 60 celle N/D, trovate {celle_nd}"
    assert "N/D = Dato non disponibile" in html
    # conteggio DB ↔ stampa: 2 rilevazioni totali
    assert "2 rilevazioni" in html
    # la lettura 8.0 era conforme con le soglie DEL MOMENTO (max 10): niente "ko"
    assert 'class="ko"' not in html


def test_report_haccp_mensile_febbraio_28_colonne(dbmock):
    from app.lotti.routers.report_haccp import report_haccp_mensile
    run(dbmock.temperature_positive.insert_one({
        "id": "TP1", "anno": 2026, "frigorifero_numero": 1,
        "frigorifero_nome": "Frigorifero N°1", "temp_min": 0.0, "temp_max": 4.0,
        "temperature": {"2": {"1": {"temp": 3.0}}}}))
    html = run(report_haccp_mensile(anno=2026, mese=2)).body.decode()
    # 2026 non bisestile: 28 giorni → 27 celle N/D (una rilevazione presente)
    assert html.count('title="Dato non disponibile"') == 27


def test_registro_lotti_mensile_html_e_csv_conteggi(dbmock):
    from app.lotti.routers.lotti_produzione import (get_registro_lotti_mensile,
                                          get_registro_lotti_csv,
                                          get_registro_lotti_annuale)
    lotti = [
        {"id": "L1", "numero_lotto": "PANE-001", "prodotto": "Pane",
         "data_produzione": "05/07/2026", "data_scadenza": "07/07/2026",
         "quantita": 10, "unita_misura": "pz", "created_at": "2026-07-05T08:00:00"},
        {"id": "L2", "numero_lotto": "TORTA-001", "prodotto": "Torta",
         "data_produzione": "2026-07-12", "data_scadenza": "2026-07-15",
         "quantita": 2, "unita_misura": "pz", "created_at": "2026-07-12T08:00:00"},
        {"id": "L3", "numero_lotto": "BABA-001", "prodotto": "Babà",
         "data_produzione": "20/07/2026", "data_scadenza": "23/07/2026",
         "quantita": 30, "unita_misura": "pz", "created_at": "2026-07-20T08:00:00"},
        {"id": "L4", "numero_lotto": "GIUGNO-001", "prodotto": "Sfoglia",
         "data_produzione": "10/06/2026", "data_scadenza": "12/06/2026",
         "quantita": 5, "unita_misura": "pz", "created_at": "2026-06-10T08:00:00"},
    ]
    run(dbmock.lotti.insert_many(lotti))

    html = run(get_registro_lotti_mensile(2026, 7)).body.decode()
    for n in ("PANE-001", "TORTA-001", "BABA-001"):
        assert n in html, f"lotto {n} presente nel DB ma assente dalla stampa"
    assert "GIUGNO-001" not in html
    assert ">3</div>" in html, "il totale stampato deve essere 3 (come nel DB)"

    csv = run(get_registro_lotti_csv(2026, 7)).body.decode("utf-8-sig")
    assert len([r for r in csv.strip().splitlines() if r]) == 1 + 3, \
        "CSV: intestazione + una riga per lotto del mese"

    annuale = run(get_registro_lotti_annuale(2026)).body.decode()
    for mese_nome in ("Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                      "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"):
        assert mese_nome in annuale, f"registro annuale: mese {mese_nome} saltato"
    assert "TOTALE ANNO" in annuale and ">4</td>" in annuale


def test_registro_lotti_asl_non_tronca_a_2000(dbmock):
    from app.lotti.routers.utils import genera_registro_lotti_asl
    docs = [{"id": f"L{i}", "numero_lotto": f"LOT-{i:04d}", "prodotto": "Pane",
             "data_produzione": "15/07/2026", "data_scadenza": "17/07/2026",
             "quantita": 1, "unita_misura": "pz",
             "created_at": f"2026-07-15T{i % 24:02d}:00:00"} for i in range(2300)]
    run(dbmock.lotti.insert_many(docs))
    html = run(genera_registro_lotti_asl(data_inizio="2026-07-01",
                                         data_fine="2026-07-31")).body.decode()
    assert ">2300</div>" in html, \
        "registro ASL troncato: nel DB ci sono 2300 lotti nel periodo, la stampa deve mostrarli tutti"


def test_export_sanificazione_tutte_le_righe(dbmock):
    from app.lotti.routers.sanificazione import (export_pdf_sanificazione,
                                       ATTREZZATURE_SANIFICAZIONE)
    run(dbmock.sanificazione_schede.insert_one({
        "anno": 2026, "mese": 7,
        "registrazioni": {ATTREZZATURE_SANIFICAZIONE[0]: {"1": "X", "2": "X"}},
        "operatore_responsabile": "Operatore Test"}))
    html = run(export_pdf_sanificazione(2026, 7)).body.decode()
    for attr in ATTREZZATURE_SANIFICAZIONE:
        assert attr in html, f"riga attrezzatura '{attr}' assente dalla stampa"
    assert html.count("class='check'") == 2, "2 sanificazioni nel DB → 2 celle X in stampa"
