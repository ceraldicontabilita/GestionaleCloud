"""Cartella unica Drive: smistatore di Documenti > Import, nessun doppione fra
gli originali (Cestino, mai eliminazione), errori col motivo, «vedi documento»
solo da ELABORATE."""
import asyncio
import hashlib

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import drive_cartella_unica as cu


def run(coro):
    return asyncio.run(coro)


class _Esegui:
    def __init__(self, valore):
        self.valore = valore

    def execute(self):
        return self.valore() if callable(self.valore) else self.valore


class _Http403(Exception):
    """Come googleapiclient HttpError: il file e' del titolare, non del service account."""

    class resp:
        status = 403


class _Http404(Exception):
    class resp:
        status = 404


class DriveFinto:
    """Drive in memoria: file con parent, md5, contenuto, cestino."""

    def __init__(self):
        self.file = {}
        self.cestinati = []
        self.cestino_vietato = False
        self.eliminati = []

    def aggiungi(self, fid, nome, contenuto, parent):
        self.file[fid] = {"id": fid, "name": nome, "contenuto": contenuto, "parent": parent,
                          "md5Checksum": hashlib.md5(contenuto).hexdigest(),
                          "mimeType": "application/pdf", "trashed": False}

    def files(self):
        return self

    def list(self, q, **_):
        parent = q.split("'")[1]
        trovati = [dict(f) for f in self.file.values() if f["parent"] == parent and not f["trashed"]]
        return _Esegui({"files": trovati})

    def update(self, fileId, addParents=None, removeParents=None, body=None, **_):
        def fai():
            f = self.file[fileId]
            if addParents:
                assert f["parent"] == removeParents
                f["parent"] = addParents
            if body and body.get("trashed"):
                if self.cestino_vietato:
                    raise _Http403()
                f["trashed"] = True
                self.cestinati.append(fileId)
            if body and body.get("description"):
                f["description"] = body["description"]
            return {"id": fileId}
        return _Esegui(fai)

    def delete(self, **_):  # pragma: no cover - non deve mai essere chiamato
        raise AssertionError("eliminazione permanente vietata")

    def get(self, fileId, **_):
        if fileId not in self.file:
            raise _Http404()
        f = self.file[fileId]
        return _Esegui({"name": f["name"], "mimeType": f["mimeType"], "trashed": f["trashed"]})


CARTELLE = {cu.INBOX: "inbox", cu.ARCHIVIO: "elaborate", cu.ERRORI: "errori",
            cu.DOPPIONI: "doppioni", cu.ARRETRATO: "arretrato"}


@pytest.fixture
def ambiente(monkeypatch):
    drive = DriveFinto()
    smistati = []
    esiti = {}

    async def smista(nome, contenuto, contesto, tipo=None):
        smistati.append((nome, contesto))
        return esiti.get(nome, {"success": True, "tipo_rilevato": "fattura_xml", "invoice_id": "inv-" + nome})

    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "radice")
    monkeypatch.setattr(cu, "_service", lambda: drive)
    monkeypatch.setattr(cu, "_cartelle", lambda service, root: dict(CARTELLE))
    monkeypatch.setattr(cu, "_smista", smista)

    async def rileva(nome, contenuto):
        return "fattura_xml"

    monkeypatch.setattr(cu, "_rileva", rileva)
    cu._azzera_cache()
    import app.services.drive_download as dd
    monkeypatch.setattr(dd, "scarica_bytes", lambda service, fid: drive.file[fid]["contenuto"])
    return drive, smistati, esiti


def test_spenta_senza_cartella(monkeypatch):
    monkeypatch.delenv("GOOGLE_DRIVE_DATI_FOLDER_ID", raising=False)
    assert cu.attivo() is False
    assert "saltato" in run(cu.giro(AsyncMongoMockClient()["t"]))


def test_smista_sposta_e_registra(ambiente):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("f1", "fattura.xml", b"<xml>1</xml>", "inbox")
    drive.aggiungi("f2", "ignoto.pdf", b"%PDF ignoto", "inbox")
    drive.aggiungi("f3", "gia.xml", b"<xml>3</xml>", "inbox")
    esiti["ignoto.pdf"] = {"success": True, "tipo_rilevato": "non_riconosciuto"}
    esiti["gia.xml"] = {"success": False, "duplicate": True, "tipo_rilevato": "fattura_xml"}

    esito = run(cu.giro(db))
    assert (esito["letti"], esito["elaborati"], esito["errori"]) == (3, 2, 1)
    # Lo smistatore riceve l'id Drive e l'impronta come provenienza.
    assert smistati[0][1]["drive_file_id"] == "f1"
    assert smistati[0][1]["source_sha256"] == hashlib.sha256(b"<xml>1</xml>").hexdigest()
    assert drive.file["f1"]["parent"] == "elaborate"
    assert drive.file["f3"]["parent"] == "elaborate"  # gia' registrato: archivio, non errore
    assert drive.file["f2"]["parent"] == "errori"
    assert "non riconosciuto" in drive.file["f2"]["description"]
    riga = run(db[cu.REGISTRO].find_one({"id": "f1"}))
    assert riga["cartella"] == cu.ARCHIVIO and riga["riferimenti"] == {"invoice_id": "inv-fattura.xml"}
    assert run(db[cu.REGISTRO].find_one({"id": "f3"}))["gia_presente"] is True


def test_copia_identica_va_nel_cestino_stesso_md5_byte_diversi_no(ambiente, monkeypatch):
    drive, smistati, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("orig", "a.pdf", b"%PDF uguale", "elaborate")
    drive.aggiungi("copia", "a (1).pdf", b"%PDF uguale", "inbox")
    drive.aggiungi("falso", "b.pdf", b"%PDF diverso", "inbox")
    # md5 forzato uguale su byte diversi: non e' un doppione.
    drive.file["falso"]["md5Checksum"] = drive.file["orig"]["md5Checksum"]

    esito = run(cu.giro(db))
    assert esito["doppioni_cestinati"] == 1
    assert drive.cestinati == ["copia"] and drive.eliminati == []
    assert run(db[cu.REGISTRO].find_one({"id": "copia"}))["duplicato_di"] == "orig"
    assert [n for n, _ in smistati] == ["b.pdf"]
    assert drive.file["falso"]["parent"] == "elaborate"


def test_due_copie_nella_stessa_coda(ambiente):
    drive, smistati, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("x1", "c.pdf", b"%PDF c", "inbox")
    drive.aggiungi("x2", "c copia.pdf", b"%PDF c", "inbox")
    esito = run(cu.giro(db))
    assert esito["elaborati"] == 1 and esito["doppioni_cestinati"] == 1
    assert len(smistati) == 1


def test_eccezione_manda_in_errori_col_motivo(ambiente, monkeypatch):
    drive, _, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("e1", "rotto.pdf", b"%PDF rotto", "inbox")

    async def esplode(nome, contenuto, contesto, tipo=None):
        raise ValueError("pagina illeggibile")

    monkeypatch.setattr(cu, "_smista", esplode)
    esito = run(cu.giro(db))
    assert esito["errori"] == 1 and drive.file["e1"]["parent"] == "errori"
    assert "ValueError" in run(db[cu.REGISTRO].find_one({"id": "e1"}))["motivo"]
    stato = run(db.sistema_stato.find_one({"chiave": cu.CHIAVE_STATO}))
    assert stato["last_result"]["errori"] == 1


def test_originale_solo_da_elaborate(ambiente):
    drive, _, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("ok", "buono.pdf", b"%PDF buono", "inbox")
    drive.aggiungi("ko", "cattivo.pdf", b"%PDF cattivo", "inbox")
    esiti["cattivo.pdf"] = {"success": False, "message": "F24 senza righe"}
    run(cu.giro(db))

    aperto = run(cu.originale(db, drive_file_id="ok"))
    assert aperto["contenuto"] == b"%PDF buono" and aperto["nome"] == "buono.pdf"
    per_impronta = run(cu.originale(db, sha256=hashlib.sha256(b"%PDF buono").hexdigest().upper()))
    assert per_impronta["contenuto"] == b"%PDF buono"
    # in ERRORI: per id si apre (il titolare lo vede per decidere), per impronta no
    fermo = run(cu.originale(db, drive_file_id="ko"))
    assert fermo["contenuto"] == b"%PDF cattivo" and fermo["nome"] == "cattivo.pdf"
    assert run(cu.originale(db, sha256=hashlib.sha256(b"%PDF cattivo").hexdigest().upper())) is None
    assert run(cu.originale(db, drive_file_id="sconosciuto")) is None
    assert run(cu.originale(db)) is None


def test_esito_del_risultato():
    assert cu.esito_del_risultato({"success": True}) == (cu.ARCHIVIO, "")
    assert cu.esito_del_risultato({"duplicate": True}) == (cu.ARCHIVIO, "")
    assert cu.esito_del_risultato({"success": False, "message": "boh"}) == (cu.ERRORI, "boh")
    assert cu.esito_del_risultato({"success": False})[1] == "registrazione non riuscita"


def test_rotte_di_giro_e_stato_riservate_all_admin():
    from app.routers.documenti import router
    from app.utils.ruoli import richiedi_admin

    per_percorso = {(r.path, tuple(r.methods)): r for r in router.routes}
    for percorso, metodo in (("/cartella-unica/giro", "POST"), ("/cartella-unica/stato", "GET")):
        rotta = per_percorso[(percorso, (metodo,))]
        assert richiedi_admin in [d.call for d in rotta.dependant.dependencies]


def test_tipo_ignoto_non_entra_in_documents_inbox(monkeypatch):
    import app.routers.documenti as documenti

    chiamato = []

    async def upload(**_):
        chiamato.append(1)
        return {"success": True}

    monkeypatch.setattr(documenti, "detect_document_type", lambda nome, contenuto: "auto")
    monkeypatch.setattr(documenti, "upload_documento_automatico", upload)
    esito = run(cu._smista("x.bin", b"???", {}))
    assert esito["tipo_rilevato"] == "non_riconosciuto" and not chiamato
    assert cu.esito_del_risultato(esito)[0] == cu.ERRORI


def test_cestino_vietato_la_copia_va_in_doppioni_non_in_errori(ambiente):
    drive, smistati, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.cestino_vietato = True
    drive.aggiungi("orig", "a.xml", b"<xml>a</xml>", "elaborate")
    drive.aggiungi("copia", "a copia.xml", b"<xml>a</xml>", "inbox")
    esito = run(cu.giro(db))
    assert esito["doppioni_cestinati"] == 1 and esito["errori"] == 0
    assert drive.file["copia"]["parent"] == "doppioni" and not smistati
    assert "copia identica di orig" in drive.file["copia"]["description"]
    riga = run(db[cu.REGISTRO].find_one({"id": "copia"}))
    assert riga["cartella"] == cu.DOPPIONI and riga["duplicato_di"] == "orig"
    assert run(cu.originale(db, drive_file_id="copia")) is None


def test_file_riportato_a_mano_in_da_elaborare_non_e_copia_di_se_stesso(ambiente):
    """Il titolare sposta a mano un XML da ELABORATE a DA ELABORARE per rileggerlo
    (archivio azzerato): la cache dell'archivio lo elenca ancora, ma il giro non
    deve cestinarlo come copia di se stesso. Si rilegge e torna in ELABORATE."""
    drive, smistati, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("f1", "fattura.xml", b"<xml>1</xml>", "inbox")
    run(cu.giro(db))                       # elaborato: ora sta in ELABORATE e nella cache md5
    assert drive.file["f1"]["parent"] == "elaborate" and len(smistati) == 1
    drive.file["f1"]["parent"] = "inbox"   # spostato a mano dal titolare
    esito = run(cu.giro(db))
    assert esito["doppioni_cestinati"] == 0 and esito["elaborati"] == 1
    assert not drive.cestinati and drive.file["f1"]["parent"] == "elaborate"
    assert len(smistati) == 2
    riga = run(db[cu.REGISTRO].find_one({"id": "f1"}))
    assert riga["cartella"] == cu.ARCHIVIO and riga["esito"] == "elaborato"


def test_originale_sparito_da_drive_diventa_rimosso(ambiente):
    drive, _, _ = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("f1", "a.xml", b"<xml>1</xml>", "inbox")
    drive.aggiungi("f2", "b.xml", b"<xml>2</xml>", "inbox")
    run(cu.giro(db))
    del drive.file["f1"]                  # eliminato a mano dal titolare
    drive.file["f2"]["trashed"] = True    # messo nel Cestino
    for fid in ("f1", "f2"):
        assert run(cu.originale(db, drive_file_id=fid)) is None
        riga = run(db[cu.REGISTRO].find_one({"id": fid}))
        assert riga["cartella"] == "RIMOSSO" and riga["rimosso_il"]


def test_credenziale_provata_sulla_radice_della_cartella_unica(monkeypatch):
    """Lo smistatore non dipende dalla cartella di un canale (es. fatture)."""
    from app.services import drive_credential_probe

    provate = []

    def finta_probe(folder_id):
        provate.append(folder_id)
        return None, "nessun accesso"

    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "radice-unica")
    monkeypatch.setattr(drive_credential_probe, "load_credentials_for_folder", finta_probe)
    with pytest.raises(RuntimeError):
        cu._service()
    assert provate == ["radice-unica"]


def test_i_file_sciolti_nella_radice_passano_dallo_smistatore(ambiente):
    """La radice e' il calderone: i file li' si smistano come quelli in DA ELABORARE."""
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("r1", "estratto.pdf", b"%PDF estratto", "radice")
    drive.aggiungi("r2", "desktop.ini", b"[.ShellClassInfo]", "radice")
    drive.aggiungi("i1", "fattura.xml", b"<xml>i1</xml>", "inbox")
    esiti["desktop.ini"] = {"success": True, "tipo_rilevato": "non_riconosciuto"}

    esito = run(cu.giro(db))
    assert (esito["letti"], esito["elaborati"], esito["errori"]) == (3, 2, 1)
    assert smistati[0][0] == "fattura.xml"  # gli XML passano davanti ai PDF
    assert drive.file["r1"]["parent"] == "elaborate"
    assert drive.file["r2"]["parent"] == "errori"
    assert drive.file["i1"]["parent"] == "elaborate"
    # Secondo giro: la radice e' vuota, niente da rileggere.
    assert run(cu.giro(db))["letti"] == 0


def test_import_in_pausa_senza_togliere_la_cartella(monkeypatch):
    """La pausa ferma lo smistatore ma lascia la cartella: la simulazione e le
    credenziali la usano ancora."""
    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "radice")
    monkeypatch.setenv("DRIVE_CARTELLA_UNICA_IMPORT", "false")
    assert cu.radice() == "radice" and cu.attivo() is False
    esito = run(cu.giro(AsyncMongoMockClient()["t"]))
    assert "pausa" in esito["saltato"]
    monkeypatch.setenv("DRIVE_CARTELLA_UNICA_IMPORT", "true")
    assert cu.attivo() is True


def test_prima_la_radice_poi_da_elaborare_e_gli_xml_in_testa(ambiente, monkeypatch):
    """26/09/2026: fatture e chiusure RT messe nella radice restavano dietro
    centinaia di PDF, e il tetto per giro non le raggiungeva mai."""
    drive, smistati, _ = ambiente
    monkeypatch.setenv("DRIVE_CARTELLA_UNICA_BATCH", "3")
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("i1", "bonifico-inbox.pdf", b"%PDF i1", "inbox")
    drive.aggiungi("r1", "bonifico-1.pdf", b"%PDF r1", "radice")
    drive.aggiungi("r2", "bonifico-2.pdf", b"%PDF r2", "radice")
    drive.aggiungi("i2", "IT01234567890_abc.xml", b"<xml>i2</xml>", "inbox")
    drive.aggiungi("r3", "3611930537_04523831214.xml", b"<xml>r3</xml>", "radice")
    drive.aggiungi("r4", "IT_vecchia_2023.xml", b"<xml>r4</xml>", "radice")
    drive.file["r4"]["createdTime"] = "2023-01-10T00:00:00Z"
    drive.file["r3"]["createdTime"] = "2026-09-26T16:22:52Z"
    drive.file["i2"]["createdTime"] = "2026-09-26T16:41:02Z"

    run(cu.giro(db))
    # l'XML caricato per ultimo per primo; il vecchio del 2023 dopo
    assert [n for n, _ in smistati] == [
        "IT01234567890_abc.xml", "3611930537_04523831214.xml", "IT_vecchia_2023.xml"]
    run(cu.giro(db))
    # poi i PDF: prima la radice, poi DA ELABORARE
    assert [n for n, _ in smistati][3:] == ["bonifico-1.pdf", "bonifico-2.pdf", "bonifico-inbox.pdf"]


# ── Arretrato degli estratti conto (titolare: dal 2025, l'anno prima per riconciliare) ──

def _smista_estratto(monkeypatch, anno, tipo="estratto_conto_nexi"):
    import app.routers.documenti as documenti
    import app.services.classificazione_estratti as cls

    chiamato = []

    async def upload(**_):
        chiamato.append(1)
        return {"success": True, "tipo_rilevato": tipo}

    monkeypatch.setattr(documenti, "detect_document_type", lambda nome, contenuto: tipo)
    monkeypatch.setattr(documenti, "upload_documento_automatico", upload)
    monkeypatch.setattr(cls, "anno_documento", lambda nome, contenuto: anno)
    return run(cu._smista("Estratto_Conto.pdf", b"%PDF", {})), chiamato


def test_estratto_dell_arretrato_resta_fermo_in_arretrato(monkeypatch):
    monkeypatch.delenv("DRIVE_ESTRATTI_ANNO_MINIMO", raising=False)
    esito, chiamato = _smista_estratto(monkeypatch, 2024)
    assert not chiamato, "un estratto 2024 non si registra"
    assert esito["arretrato"] is True and esito["anno"] == 2024 and esito["anno_minimo"] == 2025
    cartella, motivo = cu.esito_del_risultato(esito)
    assert cartella == cu.ARRETRATO and "2024" in motivo


@pytest.mark.parametrize("anno", [2025, 2026, None])
def test_estratto_dell_anno_o_senza_anno_passa(monkeypatch, anno):
    monkeypatch.delenv("DRIVE_ESTRATTI_ANNO_MINIMO", raising=False)
    esito, chiamato = _smista_estratto(monkeypatch, anno)
    assert chiamato and esito["success"] is True


def test_soglia_zero_sblocca_l_arretrato(monkeypatch):
    monkeypatch.setenv("DRIVE_ESTRATTI_ANNO_MINIMO", "0")
    esito, chiamato = _smista_estratto(monkeypatch, 2019, tipo="pos_terminal")
    assert chiamato and esito["success"] is True


def test_il_filtro_vale_solo_per_gli_estratti(monkeypatch):
    monkeypatch.delenv("DRIVE_ESTRATTI_ANNO_MINIMO", raising=False)
    esito, chiamato = _smista_estratto(monkeypatch, 2024, tipo="fattura")
    assert chiamato and not esito.get("arretrato")


def test_nel_giro_l_arretrato_va_in_arretrato_non_in_errori(ambiente):
    drive, _smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("e1", "EC agosto 2024.pdf", b"%PDF 2024", "inbox")
    esiti["EC agosto 2024.pdf"] = {"success": False, "tipo_rilevato": "estratto_conto",
                                   "arretrato": True, "anno": 2024, "anno_minimo": 2026}

    esito = run(cu.giro(db))
    assert (esito["arretrati"], esito["errori"], esito["elaborati"]) == (1, 0, 0)
    assert drive.file["e1"]["parent"] == "arretrato"
    riga = run(db[cu.REGISTRO].find_one({"id": "e1"}))
    assert riga["esito"] == "arretrato" and riga["cartella"] == cu.ARRETRATO


def test_gli_estratti_conto_passano_davanti_a_buste_xml_e_pdf():
    """28/09/2026: gli estratti ufficiali BPM del 2025 erano sciolti nella
    radice dietro oltre cinquemila file, e senza di loro stipendi e PayPal
    restavano da riconciliare."""
    coda = [
        {"name": "bonifico.pdf"},
        {"name": "IT01234567890_abc.xml", "createdTime": "2026-09-26T00:00:00Z"},
        {"name": "Estratto conto corrente_30-09-2025.pdf"},
        {"name": "LUL_2026_08.pdf"},
        {"name": "ElencoEntrateUsciteAndamento.csv"},
        {"name": "Estratto_Conto (3).pdf"},
    ]
    assert [f["name"] for f in cu.ordina_coda(coda)] == [
        "Estratto conto corrente_30-09-2025.pdf",
        "Estratto_Conto (3).pdf",
        "LUL_2026_08.pdf",
        "IT01234567890_abc.xml",
        "bonifico.pdf",
        "ElencoEntrateUsciteAndamento.csv",
    ]


def test_quietanza_mutuo_riconosciuta_prima_della_guardia_busta_paga():
    """La quietanza di rata ha la colonna «totale netto» come una busta paga:
    il nome della banca («Mutui - …») e l'intestazione «MUTUI: QUIETANZA»
    la portano al modulo mutui, non nell'arretrato."""
    from app.services.classificazione_estratti import route_da_nome, route_da_testo

    assert route_da_nome("Mutui - Quietanza di pagamento_08-09-2026_100,00.pdf") == "mutuo"
    testo = ("MUTUI: QUIETANZA DI PAGAMENTO\nFinanziamento n. 1/0000000001\n"
             "RATA N. 001 SCADENTE IL 24/08/2026\nDATA CONTABILE VALUTA TOTALE NETTO\n")
    assert route_da_testo(testo) == "mutuo"
    assert route_da_testo("CEDOLINO\nTOTALE NETTO 1.000,00") is None


# --- Velocita': download in anticipo, con tetti, nell'ordine della coda ---

def _coda(n, size=10):
    return [{"id": f"f{i}", "name": f"f{i}.xml", "size": str(size)} for i in range(n)]


def test_precarica_rispetta_i_tetti_di_parallelismo_e_byte():
    volo = {"ora": 0, "max": 0, "byte": 0, "byte_max": 0}

    async def scarica(f):
        volo["ora"] += 1
        volo["byte"] += 10
        volo["max"] = max(volo["max"], volo["ora"])
        volo["byte_max"] = max(volo["byte_max"], volo["byte"])
        await asyncio.sleep(0.01)
        volo["ora"] -= 1
        return b"x" * 10

    async def prova():
        visti = []
        async for f, contenuto in cu.precarica_in_ordine(_coda(20), scarica, paralleli=3, byte_max=25):
            visti.append(f["id"])
            await asyncio.sleep(0.005)
            volo["byte"] -= 10
        return visti

    visti = run(prova())
    assert visti == [f"f{i}" for i in range(20)]  # ordine di priorita' conservato
    assert volo["max"] <= 3
    assert volo["byte_max"] <= 30  # tetto 25 byte: al piu' 2 file da 10 + quello in consumo


def test_precarica_file_piu_grande_del_tetto_passa_da_solo_senza_stallo():
    async def scarica(f):
        return b"x"

    async def prova():
        return [f["id"] async for f, _ in cu.precarica_in_ordine(
            _coda(5, size=1000), scarica, paralleli=4, byte_max=10)]

    assert run(asyncio.wait_for(prova(), 5)) == [f"f{i}" for i in range(5)]


def test_un_download_che_fallisce_non_blocca_gli_altri():
    async def scarica(f):
        if f["id"] == "f1":
            raise ConnectionResetError("caduta")
        return b"ok"

    async def prova():
        return [(f["id"], c) async for f, c in cu.precarica_in_ordine(
            _coda(4), scarica, paralleli=2, byte_max=1000)]

    r = run(prova())
    assert [i for i, _ in r] == ["f0", "f1", "f2", "f3"]
    assert isinstance(r[1][1], ConnectionResetError) and r[2][1] == b"ok" and r[3][1] == b"ok"


def test_giro_parallelo_errore_di_un_file_va_in_errori_e_gli_altri_passano(ambiente, monkeypatch):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    for i in range(6):
        drive.aggiungi(f"x{i}", f"a{i}.xml", f"<xml>{i}</xml>".encode(), "inbox")
    import app.services.drive_download as dd
    vero = dd.scarica_bytes

    def scarica(service, fid):
        if fid == "x2":
            raise ConnectionResetError("caduta")
        return vero(service, fid)

    monkeypatch.setattr(dd, "scarica_bytes", scarica)
    esito = run(cu.giro(db))
    assert (esito["letti"], esito["elaborati"], esito["errori"]) == (6, 5, 1)
    assert drive.file["x2"]["parent"] == "errori"
    assert sorted(n for n, _ in smistati) == ["a0.xml", "a1.xml", "a3.xml", "a4.xml", "a5.xml"]


def test_secondo_giro_non_rielabora_niente(ambiente):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    for i in range(4):
        drive.aggiungi(f"y{i}", f"b{i}.xml", f"<xml>{i}</xml>".encode(), "inbox")
    assert run(cu.giro(db))["elaborati"] == 4
    seconda = run(cu.giro(db))
    assert seconda["letti"] == 0 and seconda["elaborati"] == 0 and len(smistati) == 4


# --- Velocita' 2: backoff, cache dell'archivio, tipo letto una volta sola ---

class _Http(Exception):
    def __init__(self, stato, testo=""):
        super().__init__(testo or f"HttpError {stato}")
        self.resp = type("R", (), {"status": stato})()


def test_riprova_con_backoff_su_429_e_5xx_poi_riesce(monkeypatch):
    import app.services.drive_download as dd

    attese = []
    monkeypatch.setattr(dd, "_dormi", attese.append)
    stati = iter([429, 503, None])

    def fn():
        s = next(stati)
        if s:
            raise _Http(s)
        return "ok"

    assert dd.riprova(fn) == "ok"
    assert len(attese) == 2 and attese[1] > attese[0]  # crescente: 1 s, 2 s (con un po' di casualita')


def test_riprova_non_insiste_su_404_e_si_arrende_dopo_i_tentativi(monkeypatch):
    import app.services.drive_download as dd

    attese = []
    monkeypatch.setattr(dd, "_dormi", attese.append)
    chiamate = []

    def non_trovato():
        chiamate.append(1)
        raise _Http(404)

    with pytest.raises(_Http):
        dd.riprova(non_trovato)
    assert len(chiamate) == 1 and attese == []

    chiamate.clear()

    def sempre_503():
        chiamate.append(1)
        raise _Http(503)

    with pytest.raises(_Http):
        dd.riprova(sempre_503, tentativi=3)
    assert len(chiamate) == 3 and len(attese) == 2


def test_riprova_il_403_di_quota_ma_non_quello_di_permesso():
    import app.services.drive_download as dd

    assert dd.e_transitorio(_Http(403, "rateLimitExceeded")) is True
    assert dd.e_transitorio(_Http(403, "cannotAddParent")) is False
    assert dd.e_transitorio(ConnectionResetError("rete")) is True
    assert dd.e_transitorio(_Http(404)) is False


def test_secondo_giro_usa_la_cache_dell_archivio_e_non_rilegge_tutto(ambiente, monkeypatch):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("e0", "vecchio.xml", b"<xml>0</xml>", "elaborate")
    drive.aggiungi("f1", "uno.xml", b"<xml>1</xml>", "inbox")
    letti = []
    vero = drive.list

    def list_spia(q, **kw):
        letti.append(q)
        return vero(q, **kw)

    monkeypatch.setattr(drive, "list", list_spia)
    e1 = run(cu.giro(db))
    assert e1["archivio_da_cache"] is False and any(
        "'elaborate' in parents" in q and "createdTime >" not in q for q in letti)
    letti.clear()
    drive.aggiungi("f2", "due.xml", b"<xml>2</xml>", "inbox")
    e2 = run(cu.giro(db))
    assert e2["archivio_da_cache"] is True
    # ELABORATE: solo la richiesta dei file nuovi, mai l'elenco intero.
    q_arch = [q for q in letti if "'elaborate' in parents" in q]
    assert q_arch and all("createdTime >" in q for q in q_arch)
    assert e2["elaborati"] == 1 and drive.file["f2"]["parent"] == "elaborate"


def test_la_cache_conosce_gli_originali_appena_archiviati_e_cestina_la_copia(ambiente):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("f1", "uno.xml", b"<xml>1</xml>", "inbox")
    run(cu.giro(db))
    # Nuova copia identica dopo il primo giro: la trova senza rielencare ELABORATE.
    drive.aggiungi("f9", "uno (2).xml", b"<xml>1</xml>", "inbox")
    e = run(cu.giro(db))
    assert e["archivio_da_cache"] is True and e["doppioni_cestinati"] == 1
    assert "f9" in drive.cestinati and len(smistati) == 1


def test_candidato_sparito_dall_archivio_non_manda_il_file_in_errori(ambiente, monkeypatch):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("e0", "vecchio.xml", b"<xml>1</xml>", "elaborate")
    drive.aggiungi("f1", "uno.xml", b"<xml>1</xml>", "inbox")
    import app.services.drive_download as dd

    def scarica(service, fid):
        if fid == "e0":
            raise _Http(404)
        return drive.file[fid]["contenuto"]

    monkeypatch.setattr(dd, "scarica_bytes", scarica)
    e = run(cu.giro(db))
    # La copia in archivio non c'e' piu': il file si smista, non e' un errore.
    assert e["errori"] == 0 and e["elaborati"] == 1 and e["doppioni_cestinati"] == 0


def test_il_tipo_si_rileva_una_volta_sola_e_arriva_allo_smistatore(ambiente, monkeypatch):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("f1", "uno.xml", b"<xml>1</xml>", "inbox")
    drive.aggiungi("f2", "due.xml", b"<xml>2</xml>", "inbox")
    rilevati, passati = [], []

    async def rileva(nome, contenuto):
        rilevati.append(nome)
        return "fattura_xml"

    async def smista(nome, contenuto, contesto, tipo=None):
        passati.append((nome, tipo))
        return {"success": True, "tipo_rilevato": tipo}

    monkeypatch.setattr(cu, "_rileva", rileva)
    monkeypatch.setattr(cu, "_smista", smista)
    e = run(cu.giro(db))
    assert sorted(rilevati) == ["due.xml", "uno.xml"]  # una lettura per file, in anticipo
    assert sorted(passati) == [("due.xml", "fattura_xml"), ("uno.xml", "fattura_xml")]
    assert e["tempi_s"]["smista"] >= 0 and "attesa_precarico" in e["tempi_s"]  # strumentazione presente


def test_una_copia_probabile_non_viene_riconosciuta_in_anticipo(ambiente, monkeypatch):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("e0", "vecchio.xml", b"<xml>1</xml>", "elaborate")
    drive.aggiungi("f1", "copia.xml", b"<xml>1</xml>", "inbox")
    rilevati = []

    async def rileva(nome, contenuto):
        rilevati.append(nome)
        return "fattura_xml"

    monkeypatch.setattr(cu, "_rileva", rileva)
    e = run(cu.giro(db))
    assert e["doppioni_cestinati"] == 1 and rilevati == []


def test_un_guasto_passeggero_di_supabase_rimanda_il_file_e_poi_va_in_errori(ambiente):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("f1", "uno.xml", b"<xml>1</xml>", "inbox")
    esiti["uno.xml"] = {"success": False, "tipo_rilevato": "fattura_xml",
                        "message": "Errore durante l'importazione: Supabase RPC gc_upsert_documents fallita (HTTP 503)"}
    e = run(cu.giro(db))
    # Resta in DA ELABORARE: il guasto non e' del file.
    assert drive.file["f1"]["parent"] == "inbox" and e["rinviati"] == 1 and e["errori"] == 0
    run(cu.giro(db))
    assert drive.file["f1"]["parent"] == "inbox"
    e3 = run(cu.giro(db))  # terzo tentativo: non passa mai, vale come errore
    assert drive.file["f1"]["parent"] == "errori" and e3["errori"] == 1


def test_guasto_di_supabase_nel_registro_si_rimette_in_coda():
    assert cu.e_guasto_transitorio("SupabaseRPCError: Supabase RPC gc_upsert_documents fallita (HTTP 503): schema cache")
    assert cu.e_guasto_transitorio("Errore durante l'importazione: Supabase RPC gc_fetch_documents_exact fallita (HTTP 500)")
    assert not cu.e_guasto_transitorio("F24 non quadrato o non validato")
    assert not cu.e_guasto_transitorio("Supabase RPC x fallita (HTTP 400)")


def test_rimessa_in_coda_dei_guasti_di_supabase_ha_un_tetto(ambiente):
    drive, smistati, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    motivo = "Errore durante l'importazione: Supabase RPC gc_fetch_documents_exact fallita (HTTP 503)"
    drive.aggiungi("r1", "a.pdf", b"%PDF a", "errori")
    drive.aggiungi("r2", "b.pdf", b"%PDF b", "errori")
    run(db[cu.REGISTRO].insert_one({"id": "r1", "nome": "a.pdf", "cartella": cu.ERRORI, "motivo": motivo, "tipo": "x"}))
    run(db[cu.REGISTRO].insert_one({"id": "r2", "nome": "b.pdf", "cartella": cu.ERRORI, "motivo": motivo,
                                    "tipo": "x", "rinvii": cu.MAX_RINVII}))
    rimessi = run(cu.rimetti_in_coda_buste_gia_presenti(db, drive, dict(CARTELLE)))
    assert rimessi == 1 and drive.file["r1"]["parent"] == "inbox" and drive.file["r2"]["parent"] == "errori"


# ── svuotamento: collegamento al protocollo per drive_file_id ─────────────────

def _svuota_con_giri(monkeypatch, esiti, collegati=5):
    from app.services import drive_protocollo
    coda = list(esiti)
    chiamate = []

    async def giro(db):
        return coda.pop(0)

    async def collega(conn=None):
        chiamate.append(conn)
        return collegati

    monkeypatch.setattr(cu, "giro", giro)
    monkeypatch.setattr(drive_protocollo, "collega_per_drive_file_id", collega)
    monkeypatch.setattr(cu, "_svuotamento", {"in_corso": False})
    return run(cu.svuota(None, max_giri=5)), chiamate


def test_svuota_collega_il_protocollo_dopo_un_giro_con_file_elaborati(monkeypatch):
    totale, chiamate = _svuota_con_giri(monkeypatch, [{"letti": 2, "elaborati": 2, "restanti": 0}])
    assert totale["elaborati"] == 2 and totale["protocollo_collegati"] == 5
    assert chiamate == [None]                       # una volta, a fine svuotamento, con la propria connessione


def test_svuota_senza_file_elaborati_non_tocca_il_protocollo(monkeypatch):
    totale, chiamate = _svuota_con_giri(monkeypatch, [{"letti": 0, "elaborati": 0, "restanti": 0}])
    assert "protocollo_collegati" not in totale and chiamate == []
