"""Migrazione una tantum delle foto canoniche dei prodotti napoletani."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from starlette.datastructures import Headers, UploadFile

from app.lotti.db import database as db


VERSIONE = "rst-0508at-20260922"
CHIAVE_STATO = "migrazione_foto_napoletane"
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "ricette_generate" / "napoletani_canonici"
MAPPATURA = ASSET_DIR / "mappatura.json"


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def migra_foto_napoletane(database: Any = None) -> dict:
    """Carica per ID esatto, riprende dopo errori e non usa nomi o fuzzy match."""
    if database is None:
        database = db
    stato = await database.sistema_stato.find_one(
        {"chiave": CHIAVE_STATO}, {"_id": 0}
    )
    if stato and stato.get("versione") == VERSIONE and stato.get("stato") == "completata":
        return {
            "versione": VERSIONE,
            "stato": "completata",
            "gia_completata": True,
            "caricate": int(stato.get("caricate") or 0),
        }

    mapping = json.loads(MAPPATURA.read_text(encoding="utf-8"))
    if not isinstance(mapping, list) or not mapping:
        raise RuntimeError("Mappatura foto napoletane assente o non valida")
    await database.sistema_stato.update_one(
        {"chiave": CHIAVE_STATO},
        {"$set": {
            "chiave": CHIAVE_STATO,
            "versione": VERSIONE,
            "stato": "in_corso",
            "avviata_il": _adesso(),
            "totale": len(mapping),
        }},
        upsert=True,
    )

    from app.lotti.routers import ricette
    caricate: list[dict] = []
    gia_presenti: list[str] = []
    errori: list[dict] = []
    for voce in mapping:
        ricetta_id = str(voce.get("id") or "").strip()
        percorso = Path(str(voce.get("file") or ""))
        if not percorso.is_absolute():
            percorso = Path(__file__).resolve().parents[3] / percorso
        try:
            contenuto = percorso.read_bytes()
            digest = hashlib.sha256(contenuto).hexdigest()
            esistente = await database.ricette.find_one(
                {"id": ricetta_id},
                {"_id": 0, "foto_sha256": 1, "foto_source": 1},
            )
            if not esistente:
                raise RuntimeError("Ricetta operativa non trovata")
            if (
                esistente.get("foto_sha256") == digest
                and esistente.get("foto_source") == "catalogo_napoletano_verificato"
            ):
                menu_sync = await ricette._sincronizza_menu(ricetta_id)
                if (menu_sync or {}).get("esito") in {"errore", "non_configurato", None}:
                    raise RuntimeError(
                        "Sincronizzazione Menu non completata: "
                        f"{(menu_sync or {}).get('errore') or (menu_sync or {}).get('esito')}"
                    )
                gia_presenti.append(ricetta_id)
                continue
            file = UploadFile(
                io.BytesIO(contenuto),
                filename=percorso.name,
                headers=Headers({"content-type": "image/png"}),
            )
            esito = await ricette.upload_foto(
                ricetta_id,
                file,
                "catalogo_napoletano_verificato",
                True,
            )
            if esito.get("foto_sha256") != digest:
                raise RuntimeError("Hash salvato diverso dall'asset canonico")
            menu_sync = esito.get("menu_sync") or {}
            if menu_sync.get("esito") in {"errore", "non_configurato", None}:
                raise RuntimeError(
                    "Sincronizzazione Menu non completata: "
                    f"{menu_sync.get('errore') or menu_sync.get('esito')}"
                )
            caricate.append({
                "id": ricetta_id,
                "sha256": digest,
                "foto_url": esito.get("foto_url"),
                "backup_id": esito.get("backup_id"),
                "foto_precedente_cestinata": esito.get("foto_precedente_cestinata"),
                "menu_sync": menu_sync.get("esito"),
            })
        except Exception as exc:
            errori.append({"id": ricetta_id, "errore": f"{type(exc).__name__}: {exc}"})
        await database.sistema_stato.update_one(
            {"chiave": CHIAVE_STATO},
            {"$set": {
                "aggiornata_il": _adesso(),
                "caricate": len(caricate),
                "gia_presenti": len(gia_presenti),
                "errori": errori,
                "ultimo_id": ricetta_id,
            }},
        )

    finale = {
        "chiave": CHIAVE_STATO,
        "versione": VERSIONE,
        "stato": "completata" if not errori else "errore",
        "completata_il": _adesso() if not errori else None,
        "totale": len(mapping),
        "caricate": len(caricate),
        "gia_presenti": len(gia_presenti),
        "errori": errori,
        "dettaglio": caricate,
    }
    await database.sistema_stato.update_one(
        {"chiave": CHIAVE_STATO}, {"$set": finale}, upsert=True
    )
    return finale
