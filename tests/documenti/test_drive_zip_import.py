"""Import di uno ZIP grande da Drive: lettura a intervalli di byte, cursore riprendibile, nessun doppione."""
import asyncio
import io
import zipfile

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import drive_cartella_unica as cu
from app.services import drive_zip_import as dz


def _run(coro):
    return asyncio.run(coro)


def _zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("2020/F24_1.pdf", b"%PDF-uno " + b"x" * 500)
        z.writestr("2020/F24_2.pdf", b"%PDF-due " + b"y" * 500)
        z.writestr("2020/note.txt", b"non e' un formato ammesso")
        z.writestr("2021/LIPE.pdf", b"%PDF-tre " + b"z" * 500)
        z.writestr("2021/dentro.zip", b"PK-annidato")
        z.writestr("2021/rotta.pdf", b"%PDF-rotta")
        z.writestr("__MACOSX/2020/._F24_1.pdf", b"metadati")
    return buffer.getvalue()


def _archivio(monkeypatch, contenuto: bytes):
    monkeypatch.setattr(dz, "BLOCCO_BYTE", 128)
    richieste = []

    def fetch(inizio, fine):
        richieste.append((inizio, fine))
        return contenuto[inizio:fine + 1]

    return zipfile.ZipFile(dz.FileDriveARange(fetch, len(contenuto))), richieste


def _smista_finto(monkeypatch, esiti):
    chiamate = []

    async def smista(nome, dati, contesto):
        chiamate.append((nome, contesto["archive_path"]))
        if nome == "rotta.pdf":
            raise RuntimeError("PDF guasto")
        return esiti[nome]

    monkeypatch.setattr(cu, "_smista", smista)
    return chiamate


ESITI = {
    "F24_1.pdf": {"success": True, "duplicate": False},
    "F24_2.pdf": {"success": True, "duplicate": True},
    "LIPE.pdf": {"success": False, "tipo_rilevato": "non_riconosciuto"},
}


def test_lo_zip_si_legge_a_blocchi_senza_scaricarlo_intero(monkeypatch):
    contenuto = _zip()
    archivio, richieste = _archivio(monkeypatch, contenuto)

    dati = archivio.read("2021/LIPE.pdf")

    assert dati.startswith(b"%PDF-tre")
    # Indice in fondo + i blocchi della sola voce letta: non l'intero file.
    assert sum(fine - inizio + 1 for inizio, fine in richieste) < len(contenuto)


def test_anteprima_conta_le_voci_senza_importare(monkeypatch):
    archivio, _ = _archivio(monkeypatch, _zip())

    esito = _run(dz.anteprima(archivio))

    assert esito["dry_run"] is True and esito["voci"] == 6
    assert esito["da_importare"] == 4 and esito["per_formato"] == {".pdf": 4}
    assert set(esito["saltate_per_motivo"]) == {
        "formato che l'import non legge", "archivio annidato: non si apre"}


def test_elabora_a_lotti_riprende_dal_cursore_e_non_rifa_le_voci(monkeypatch):
    db = AsyncMongoMockClient()["zip"]
    archivio, _ = _archivio(monkeypatch, _zip())
    chiamate = _smista_finto(monkeypatch, ESITI)

    primo = _run(dz.elabora(db, "file-id-1", archivio, nome_zip="M.zip", limite=2))
    assert primo["completato"] is False and primo["indice"] == 2

    secondo = _run(dz.elabora(db, "file-id-1", archivio, nome_zip="M.zip"))

    assert secondo["completato"] is True and secondo["indice"] == 6
    assert [n for n, _p in chiamate] == ["F24_1.pdf", "F24_2.pdf", "LIPE.pdf", "rotta.pdf"]
    assert secondo["contatori"] == {
        "importati": 1, "gia_presenti": 1, "non_riconosciuti": 1, "saltati": 2, "errori": 1}
    salvato = _run(db["sistema_stato"].find_one({"chiave": "import_zip_drive:file-id-1"}))
    assert salvato["stato"] == "completato" and salvato["non_riconosciuti"][0]["percorso"] == "2021/LIPE.pdf"
    assert salvato["errori"][0]["percorso"] == "2021/rotta.pdf"


def test_secondo_passaggio_completo_non_rielabora_niente(monkeypatch):
    db = AsyncMongoMockClient()["zip"]
    archivio, _ = _archivio(monkeypatch, _zip())
    chiamate = _smista_finto(monkeypatch, ESITI)
    _run(dz.elabora(db, "file-id-2", archivio, nome_zip="M.zip"))
    prima = len(chiamate)

    ancora = _run(dz.elabora(db, "file-id-2", archivio, nome_zip="M.zip"))

    assert len(chiamate) == prima and ancora["completato"] is True


def test_stato_dice_mai_avviato_e_poi_l_avanzamento(monkeypatch):
    db = AsyncMongoMockClient()["zip"]
    assert _run(dz.stato(db, "file-id-3")) == {"stato": "mai_avviato"}
    archivio, _ = _archivio(monkeypatch, _zip())
    _smista_finto(monkeypatch, ESITI)

    _run(dz.elabora(db, "file-id-3", archivio, nome_zip="M.zip", limite=1))

    stato = _run(dz.stato(db, "file-id-3"))
    assert stato["stato"] == "in_corso" and stato["indice"] == 1 and stato["voci"] == 6


FILE_DRIVE = [
    {"id": "f1", "name": "F24_1.pdf", "mimeType": "application/pdf", "size": "500", "percorso": "MINI/02/2021/F24_1.pdf"},
    {"id": "f2", "name": "F24_2.pdf", "mimeType": "application/pdf", "size": "500", "percorso": "MINI/02/2021/F24_2.pdf"},
    {"id": "f3", "name": "LIPE.pdf", "mimeType": "application/pdf", "size": "500", "percorso": "MINI/05/LIPE.pdf"},
    {"id": "f4", "name": "script.py", "mimeType": "text/x-python", "size": "10", "percorso": "MINI/script.py"},
    {"id": "f5", "name": "note", "mimeType": "application/vnd.google-apps.document", "percorso": "MINI/note"},
]


def _drive_finto(monkeypatch):
    from app.services import drive_download

    letti = []

    async def scarica(file_id, md5=None):
        letti.append(file_id)
        return b"%PDF-" + file_id.encode()

    monkeypatch.setattr(drive_download, "scarica_originale", scarica)
    return letti


def test_anteprima_cartella_conta_e_dice_cosa_salta():
    esito = dz.anteprima_cartella(FILE_DRIVE)

    assert esito["dry_run"] is True and esito["voci"] == 5 and esito["da_importare"] == 3
    assert set(esito["saltate_per_motivo"]) == {
        "formato che l'import non legge", "documento Google: non e' un file"}


def test_cartella_si_importa_in_sola_lettura_e_riprende(monkeypatch):
    db = AsyncMongoMockClient()["cartella"]
    letti = _drive_finto(monkeypatch)
    chiamate = _smista_finto(monkeypatch, {
        "F24_1.pdf": {"success": True, "duplicate": False},
        "F24_2.pdf": {"success": True, "duplicate": True},
        "LIPE.pdf": {"success": False, "tipo_rilevato": "non_riconosciuto"},
    })

    primo = _run(dz.elabora_cartella(db, "cart-1", FILE_DRIVE, nome="MINI", limite=2))
    assert primo["completato"] is False and primo["indice"] == 2
    secondo = _run(dz.elabora_cartella(db, "cart-1", FILE_DRIVE, nome="MINI"))

    assert secondo["completato"] is True
    # Alla pausa dopo 2 file, f3 era gia' in lettura anticipata: si rilegge (una lettura in piu').
    assert sorted(set(letti)) == ["f1", "f2", "f3"]
    assert [p for _n, p in chiamate] == [
        "MINI/02/2021/F24_1.pdf", "MINI/02/2021/F24_2.pdf", "MINI/05/LIPE.pdf"]
    assert secondo["contatori"] == {
        "importati": 1, "gia_presenti": 1, "non_riconosciuti": 1, "saltati": 2, "errori": 0}


def test_cartella_completata_si_ricontrolla_e_i_file_gia_entrati_non_si_riscrivono(monkeypatch):
    db = AsyncMongoMockClient()["cartella2"]
    _drive_finto(monkeypatch)
    _smista_finto(monkeypatch, {
        "F24_1.pdf": {"success": True, "duplicate": False},
        "F24_2.pdf": {"success": True, "duplicate": False},
        "LIPE.pdf": {"success": True, "duplicate": False},
    })
    _run(dz.elabora_cartella(db, "cart-2", FILE_DRIVE, nome="MINI"))
    _smista_finto(monkeypatch, {n: {"success": True, "duplicate": True}
                                for n in ("F24_1.pdf", "F24_2.pdf", "LIPE.pdf")})

    secondo = _run(dz.elabora_cartella(db, "cart-2", FILE_DRIVE, nome="MINI"))

    assert secondo["contatori"]["importati"] == 0 and secondo["contatori"]["gia_presenti"] == 3


def test_giro_configurato_e_spento_senza_variabile(monkeypatch):
    monkeypatch.delenv("DRIVE_IMPORT_CARTELLE_ID", raising=False)
    db = AsyncMongoMockClient()["cartella3"]

    assert _run(dz.importa_cartelle_configurate(db)) == {"saltato": "nessuna cartella configurata"}


def test_cartella_legge_in_anticipo_ma_scrive_uno_alla_volta(monkeypatch):
    """Le letture partono insieme, il riconoscimento no: due copie non si superano."""
    from app.services import drive_download

    file_drive = [
        {"id": f"g{i}", "name": f"F{i}.pdf", "mimeType": "application/pdf",
         "size": "1000", "percorso": f"M/F{i}.pdf"}
        for i in range(6)
    ]
    in_volo = {"letture": 0, "max_letture": 0, "smista": 0, "max_smista": 0}

    async def scarica(file_id, md5=None):
        in_volo["letture"] += 1
        in_volo["max_letture"] = max(in_volo["max_letture"], in_volo["letture"])
        await asyncio.sleep(0.01)
        in_volo["letture"] -= 1
        return b"%PDF-" + file_id.encode()

    async def smista(nome, dati, contesto):
        in_volo["smista"] += 1
        in_volo["max_smista"] = max(in_volo["max_smista"], in_volo["smista"])
        await asyncio.sleep(0.001)
        in_volo["smista"] -= 1
        return {"success": True, "duplicate": False}

    monkeypatch.setattr(drive_download, "scarica_originale", scarica)
    monkeypatch.setattr(cu, "_smista", smista)
    db = AsyncMongoMockClient()["parallelo"]

    esito = _run(dz.elabora_cartella(db, "cart-p", file_drive, nome="M"))

    assert esito["completato"] is True and esito["contatori"]["importati"] == 6
    assert in_volo["max_letture"] > 1
    assert in_volo["max_smista"] == 1


def test_file_grande_non_si_anticipa(monkeypatch):
    from app.services import drive_download

    letti = []

    async def scarica(file_id, md5=None):
        letti.append(file_id)
        return b"%PDF-x"

    monkeypatch.setattr(drive_download, "scarica_originale", scarica)
    _smista_finto(monkeypatch, {"G.pdf": {"success": True, "duplicate": False}})
    grande = [{"id": "big", "name": "G.pdf", "mimeType": "application/pdf",
               "size": str(dz.PREFETCH_MAX_BYTE + 1), "percorso": "M/G.pdf"}]
    db = AsyncMongoMockClient()["parallelo2"]

    voci = dz._voci_da_cartella(grande)
    assert voci[0].byte > dz.PREFETCH_MAX_BYTE

    esito = _run(dz.elabora_cartella(db, "cart-g", grande, nome="M"))
    assert esito["contatori"]["importati"] == 1 and letti == ["big"]


def test_ripasso_errori_una_volta_sola_per_versione_dei_lettori(monkeypatch):
    from app.services import drive_download

    file_drive = [
        {"id": f"r{i}", "name": f"F{i}.pdf", "mimeType": "application/pdf",
         "size": "100", "percorso": f"M/F{i}.pdf"}
        for i in range(3)
    ]
    chiamate = []

    async def scarica(file_id, md5=None):
        return b"%PDF-" + file_id.encode()

    monkeypatch.setattr(drive_download, "scarica_originale", scarica)
    stato = {"F1.pdf": {"success": False, "message": "F24 non quadrato"}}

    async def smista(nome, dati, contesto):
        chiamate.append(nome)
        return stato.get(nome, {"success": True, "duplicate": False})

    monkeypatch.setattr(cu, "_smista", smista)
    db = AsyncMongoMockClient()["ripasso"]

    primo = _run(dz.elabora_cartella(db, "cart-r", file_drive, nome="M"))
    assert primo["contatori"]["errori"] == 1 and chiamate == ["F0.pdf", "F1.pdf", "F2.pdf"]

    # Il lettore e' stato corretto: al giro dopo il file in errore si rilegge, una volta.
    stato.clear()
    dz_salvato = _run(db["sistema_stato"].find_one({"chiave": "import_zip_drive:cart-r"}))
    assert dz_salvato["stato"] == "completato"
    _run(db["sistema_stato"].update_one(
        {"chiave": "import_zip_drive:cart-r"}, {"$set": {"stato": "in_corso", "indice": 3}}))
    chiamate.clear()
    secondo = _run(dz.elabora_cartella(db, "cart-r", file_drive, nome="M"))

    assert chiamate == ["F1.pdf"]
    assert secondo["contatori"]["errori"] == 0 and secondo["contatori"]["importati"] == 3

    chiamate.clear()
    _run(db["sistema_stato"].update_one(
        {"chiave": "import_zip_drive:cart-r"}, {"$set": {"stato": "in_corso", "indice": 3}}))
    _run(dz.elabora_cartella(db, "cart-r", file_drive, nome="M"))
    assert chiamate == []


def test_cartella_completata_con_lettori_nuovi_ripassa_solo_gli_errori(monkeypatch):
    """Nuova versione dei lettori: si rileggono gli errori, non l'intera cartella."""
    from app.services import drive_download

    file_drive = [
        {"id": f"c{i}", "name": f"F{i}.pdf", "mimeType": "application/pdf",
         "size": "100", "percorso": f"M/F{i}.pdf"}
        for i in range(4)
    ]

    async def scarica(file_id, md5=None):
        return b"%PDF-" + file_id.encode()

    monkeypatch.setattr(drive_download, "scarica_originale", scarica)
    chiamate = []
    stato = {"F2.pdf": {"success": False, "message": "F24 non quadrato"}}

    async def smista(nome, dati, contesto):
        chiamate.append(nome)
        return stato.get(nome, {"success": True, "duplicate": False})

    monkeypatch.setattr(cu, "_smista", smista)
    db = AsyncMongoMockClient()["ripasso3"]
    _run(dz.elabora_cartella(db, "cart-c", file_drive, nome="M"))
    stato.clear()
    chiamate.clear()

    secondo = _run(dz.elabora_cartella(db, "cart-c", file_drive, nome="M"))
    assert chiamate == ["F2.pdf"]
    assert secondo["contatori"]["errori"] == 0


def test_ripasso_riprende_dopo_un_riavvio_senza_rifare_i_file_gia_riletti(monkeypatch):
    """Il ripasso e' lento e un deploy lo interrompe: l'avanzamento si salva ogni 10 file."""
    from app.services import drive_download

    class Interruzione(BaseException):
        pass

    file_drive = [
        {"id": f"k{i}", "name": f"F{i:02d}.pdf", "mimeType": "application/pdf",
         "size": "100", "percorso": f"M/F{i:02d}.pdf"}
        for i in range(25)
    ]

    async def scarica(file_id, md5=None):
        return b"%PDF-" + file_id.encode()

    monkeypatch.setattr(drive_download, "scarica_originale", scarica)
    chiamate = []
    fase = {"ripasso": False, "interrompi_dopo": None}

    async def smista(nome, dati, contesto):
        chiamate.append(nome)
        if not fase["ripasso"]:
            return {"success": False, "message": "F24 non quadrato"}
        if fase["interrompi_dopo"] is not None and len(chiamate) > fase["interrompi_dopo"]:
            raise Interruzione()
        return {"success": True, "duplicate": False}

    monkeypatch.setattr(cu, "_smista", smista)
    db = AsyncMongoMockClient()["ripasso2"]
    _run(dz.elabora_cartella(db, "cart-k", file_drive, nome="M"))
    assert len(chiamate) == 25

    # Il lettore e' stato corretto; il servizio viene fermato a meta' del ripasso (dopo 13 file).
    fase["ripasso"] = True
    fase["interrompi_dopo"] = 13
    chiamate.clear()
    _run(db["sistema_stato"].update_one(
        {"chiave": "import_zip_drive:cart-k"}, {"$set": {"stato": "in_corso", "indice": 25}}))
    with pytest.raises(Interruzione):
        _run(dz.elabora_cartella(db, "cart-k", file_drive, nome="M"))
    salvato = _run(db["sistema_stato"].find_one({"chiave": "import_zip_drive:cart-k"}))
    assert len(salvato["ripasso_restanti"]) == 15 and salvato.get("versione_ripasso") != dz.VERSIONE_RIPASSO

    # Al riavvio riprende dai 15 rimasti, non da 25.
    fase["interrompi_dopo"] = None
    chiamate.clear()
    finale = _run(dz.elabora_cartella(db, "cart-k", file_drive, nome="M"))

    assert len(chiamate) == 15
    assert finale["contatori"]["errori"] == 0
    salvato = _run(db["sistema_stato"].find_one({"chiave": "import_zip_drive:cart-k"}))
    assert salvato["versione_ripasso"] == dz.VERSIONE_RIPASSO and salvato["ripasso_restanti"] == []
