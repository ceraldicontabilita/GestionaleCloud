"""Collega alle ricette le illustrazioni AI versionate nel repository.

Ogni revisione di un'immagine viene applicata una sola volta. In questo modo
il primo rilascio puo' sostituire una foto esistente richiesta dal titolare,
ma un caricamento manuale successivo non viene sovrascritto a ogni riavvio.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Awaitable, Callable, Optional


ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "ricette_generate"

# Nome ricetta esatto -> asset. Aggiungere qui ogni nuova tranche approvata.
ILLUSTRAZIONI_GENERATE = (
    ("Bagna Curitiba", "bagna_curitiba.webp"),
    ("CURITIBA", "curitiba.webp"),
    ("Tramezzino al Prosciutto", "tramezzino_al_prosciutto.webp"),
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


async def collega_illustrazioni_generate(
    db,
    sincronizza_menu: Optional[Callable[[str], Awaitable[dict]]] = None,
    manifest=ILLUSTRAZIONI_GENERATE,
) -> dict:
    """Importa gli asset nella raccolta foto e li collega senza doppioni.

    Una ricetta deve corrispondere in modo univoco per nome. Se manca o se il
    nome e' ambiguo, l'asset resta in attesa e verra' ritentato al deploy
    successivo. Il marcatore include l'hash del file: una nuova revisione della
    stessa immagine viene quindi applicata una volta, mentre i riavvii non
    riscrivono il database.
    """
    esito = {
        "collegate": [],
        "gia_applicate": [],
        "in_attesa": [],
        "errori_menu": [],
    }
    now = datetime.now(timezone.utc).isoformat()

    for nome, filename in manifest:
        path = ASSET_DIR / filename
        if not path.is_file():
            esito["in_attesa"].append({"nome": nome, "motivo": "asset assente"})
            continue

        contenuto = path.read_bytes()
        sha256 = hashlib.sha256(contenuto).hexdigest()
        slug = _slug(nome)
        mime = "image/webp" if path.suffix.casefold() == ".webp" else "image/png"
        stato_key = f"foto_ricetta_ai:{slug}:{sha256[:16]}"
        if await db.sistema_stato.find_one({"chiave": stato_key}, {"_id": 1}):
            esito["gia_applicate"].append(nome)
            continue

        candidati = await db.ricette.find(
            {"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
            {"_id": 0, "id": 1, "nome": 1},
        ).to_list(2)
        if len(candidati) != 1:
            motivo = "ricetta assente" if not candidati else "nome ricetta ambiguo"
            esito["in_attesa"].append({"nome": nome, "motivo": motivo})
            continue

        ricetta_id = candidati[0]["id"]
        foto_id = f"ricetta_ai_{slug}_{sha256[:16]}"
        await db.foto_files.update_one(
            {"_id": foto_id},
            {"$set": {
                "_id": foto_id,
                "mime": mime,
                "data": contenuto,
                "ricetta_id": ricetta_id,
                "versione": sha256[:16],
                "fonte": "illustrazione_ai",
                "sha256": sha256,
                "filename": filename,
                "updated_at": now,
            }},
            upsert=True,
        )
        foto_url = f"/api/foto/{foto_id}?v={sha256[:16]}"
        await db.ricette.update_one(
            {"id": ricetta_id},
            {"$set": {
                "foto_url": foto_url,
                "foto_id": foto_id,
                "foto_filename": filename,
                "foto_content_type": mime,
                "foto_sha256": sha256,
                "foto_source": "illustrazione_ai",
            }},
        )

        menu_sync = {"esito": "non_richiesto"}
        if sincronizza_menu is not None:
            menu_sync = await sincronizza_menu(ricetta_id)
            if menu_sync.get("esito") == "errore":
                esito["errori_menu"].append({"nome": nome, "menu_sync": menu_sync})
                continue

        await db.sistema_stato.update_one(
            {"chiave": stato_key},
            {"$set": {
                "chiave": stato_key,
                "nome_ricetta": candidati[0]["nome"],
                "ricetta_id": ricetta_id,
                "foto_id": foto_id,
                "sha256": sha256,
                "menu_sync": menu_sync,
                "quando": now,
            }},
            upsert=True,
        )
        esito["collegate"].append({
            "nome": candidati[0]["nome"],
            "ricetta_id": ricetta_id,
            "foto_url": foto_url,
            "sha256": sha256,
        })

    return esito
