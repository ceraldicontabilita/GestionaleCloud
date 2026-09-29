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

    async def smista(nome, contenuto, contesto):
        smistati.append((nome, contesto))
        return esiti.get(nome, {"success": True, "tipo_rilevato": "fattura_xml", "invoice_id": "inv-" + nome})

    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "radice")
    monkeypatch.setattr(cu, "_service", lambda: drive)
    monkeypatch.setattr(cu, "_cartelle", lambda service, root: dict(CARTELLE))
    monkeypatch.setattr(cu, "_smista", smista)
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

    async def esplode(nome, contenuto, contesto):
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
    assert run(cu.originale(db, drive_file_id="ko")) is None  # in ERRORI
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
