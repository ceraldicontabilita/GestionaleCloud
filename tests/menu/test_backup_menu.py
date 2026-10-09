"""Backup del Menu: niente blocchi del server, niente ripristini alla cieca.

Prima: `tar` e `rm -rf` lanciati con subprocess dentro `async def` (server
fermo per tutti durante il backup) e, nel ripristino, tabelle svuotate PRIMA
di sapere se l'archivio si leggeva.
"""
import inspect
import io
import json
import tarfile

import pytest
from fastapi import HTTPException

from app.menu.routes import backup_routes as br


class _Tabella:
    def __init__(self, registro, nome):
        self.registro, self.nome = registro, nome

    def delete(self):
        self.registro.append(("delete", self.nome))
        return self

    def neq(self, *_):
        return self

    def insert(self, righe):
        self.registro.append(("insert", self.nome, len(righe)))
        return self

    def execute(self):
        return self


class _Supabase:
    def __init__(self):
        self.registro = []

    def table(self, nome):
        return _Tabella(self.registro, nome)


def _archivio(percorso, membri):
    with tarfile.open(percorso, "w:gz") as tar:
        for nome, contenuto in membri.items():
            dati = contenuto.encode()
            info = tarfile.TarInfo(nome)
            info.size = len(dati)
            tar.addfile(info, io.BytesIO(dati))


def test_endpoint_pesanti_non_bloccano_il_loop():
    assert not inspect.iscoroutinefunction(br.create_backup)
    assert not inspect.iscoroutinefunction(br.restore_backup)
    assert not hasattr(br, "subprocess")


@pytest.mark.parametrize("nome", ["../etc/passwd", "x.tar.gz", "ceraldi_backup_1.tar.gz"])
def test_nomi_arbitrari_rifiutati(nome):
    with pytest.raises(HTTPException) as e:
        br._file_backup(nome)
    assert e.value.status_code == 400


def test_archivio_illeggibile_non_cancella_niente(tmp_path, monkeypatch):
    finto = _Supabase()
    monkeypatch.setattr(br, "supabase", finto)
    monkeypatch.setattr(br, "BACKUP_DIR", tmp_path)
    nome = "ceraldi_backup_20260924_120000.tar.gz"
    (tmp_path / nome).write_bytes(b"non e' un tar")
    with pytest.raises(HTTPException) as e:
        br.restore_backup(nome, username="admin")
    assert e.value.status_code == 400
    assert finto.registro == []


def test_ripristino_ignora_percorsi_estranei(tmp_path, monkeypatch):
    finto = _Supabase()
    monkeypatch.setattr(br, "supabase", finto)
    monkeypatch.setattr(br, "BACKUP_DIR", tmp_path)
    nome = "ceraldi_backup_20260924_120000.tar.gz"
    _archivio(tmp_path / nome, {
        "ceraldi_backup_20260924_120000/menu_categories.json": json.dumps([{"id": 1}]),
        "../fuori.json": "[]",
        "ceraldi_backup_20260924_120000/tabella_estranea.json": "[]",
    })
    esito = br.restore_backup(nome, username="admin")
    assert esito["success"]
    assert ("insert", "menu_categories", 1) in finto.registro
    assert not (tmp_path.parent / "fuori.json").exists()
