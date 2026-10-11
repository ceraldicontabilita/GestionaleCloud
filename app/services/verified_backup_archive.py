"""Backup binari verificati nell'archivio persistente condiviso dei domini."""

import base64
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


class BackupNonPersistente(RuntimeError):
    pass


async def salva_file(
    nome,
    percorso,
    riepilogo,
    *,
    store,
    namespace,
    part_bytes=3 * 1024 * 1024,
    richiedi_persistenza=True,
):
    if richiedi_persistenza and not store.persistent:
        raise BackupNonPersistente("Archivio persistente non disponibile")
    parti, caricate = [], []
    h = hashlib.sha256()
    try:
        with open(percorso, "rb") as f:
            for indice, dati in enumerate(iter(lambda: f.read(part_bytes), b"")):
                digest = hashlib.sha256(dati).hexdigest()
                key = f"{namespace}-backup:{nome}:{indice:04d}:sha256:{digest}"
                await store.put(key, base64.b64encode(dati).decode("ascii"))
                caricate.append(key)
                letto = await store.get(key)
                if (
                    letto is None
                    or hashlib.sha256(
                        base64.b64decode(letto, validate=True)
                    ).hexdigest()
                    != digest
                ):
                    raise BackupNonPersistente(f"Parte {indice} riletta diversa")
                h.update(dati)
                parti.append({"chiave": key, "sha256": digest, "bytes": len(dati)})
        manifest_key = f"{namespace}-backup-manifest:{nome}"
        manifesto = {
            **riepilogo,
            "nome": nome,
            "namespace": namespace,
            "sha256": h.hexdigest(),
            "bytes": Path(percorso).stat().st_size,
            "parti": parti,
            "verificato": True,
            "verificato_at": datetime.now(timezone.utc).isoformat(),
        }
        await store.put(
            manifest_key,
            base64.b64encode(json.dumps(manifesto, ensure_ascii=False).encode()).decode(
                "ascii"
            ),
        )
        caricate.append(manifest_key)
        letto = await store.get(manifest_key)
        if (
            letto is None
            or json.loads(base64.b64decode(letto, validate=True)) != manifesto
        ):
            raise BackupNonPersistente("Manifesto riletto diverso")
        return manifesto
    except Exception:
        if caricate:
            await store.delete(caricate)
        raise


async def ricomponi_file(manifesto, destinazione, *, store):
    h = hashlib.sha256()
    try:
        with open(destinazione, "wb") as f:
            for p in manifesto.get("parti") or []:
                letto = await store.get(p["chiave"])
                if letto is None:
                    raise BackupNonPersistente("Parte del backup mancante")
                dati = base64.b64decode(letto, validate=True)
                if hashlib.sha256(dati).hexdigest() != p["sha256"]:
                    raise BackupNonPersistente("Parte del backup alterata")
                h.update(dati)
                f.write(dati)
        if h.hexdigest() != manifesto.get("sha256"):
            raise BackupNonPersistente("Impronta del file ricomposto diversa")
        return destinazione
    except Exception:
        Path(destinazione).unlink(missing_ok=True)
        raise


async def elimina_file(manifesto, *, store, namespace):
    return await store.delete(
        [p["chiave"] for p in manifesto.get("parti") or []]
        + [f'{namespace}-backup-manifest:{manifesto["nome"]}']
    )
