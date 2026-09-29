"""Import di uno ZIP grande da Drive: lettura a intervalli di byte, cursore riprendibile, nessun doppione."""
import asyncio
import io
import zipfile

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
