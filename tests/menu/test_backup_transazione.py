import asyncio
import pytest
from app.services.blob_store import MemoryBlobStore
from app.services.verified_backup_archive import (
    salva_file,
    ricomponi_file,
    BackupNonPersistente,
)


class Persistent(MemoryBlobStore):
    persistent = True


def test_parte_corrotto_non_lascia_file_ripristinabile(tmp_path):
    async def scenario():
        src = tmp_path / "src"
        src.write_bytes(b"contenuto originale")
        store = Persistent()
        m = await salva_file(
            "backup", str(src), {}, store=store, namespace="menu", part_bytes=5
        )
        store._data[m["parti"][0]["chiave"]] = "Y29ycm90dG8="
        dest = tmp_path / "restored"
        with pytest.raises(BackupNonPersistente):
            await ricomponi_file(m, str(dest), store=store)
        assert not dest.exists()

    asyncio.run(scenario())
