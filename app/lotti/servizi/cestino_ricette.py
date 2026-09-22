"""Archivio e ripristino delle ricette operative, con ID e storia conservati."""

from datetime import datetime, timezone
import uuid


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def archivia_ricetta(db, ricetta: dict, *, attore: str, motivo: str, **metadati) -> bool:
    """Conserva la copia prima della rimozione dalla raccolta operativa."""
    voce = {
        "id": str(uuid.uuid4()),
        "ricetta_id": ricetta["id"],
        "ricetta": dict(ricetta),
        "eliminata_at": _ora(),
        "eliminata_da": attore,
        "motivo": motivo,
        **metadati,
    }
    await db.ricette_cestino.insert_one(voce)
    eliminata = await db.ricette.delete_one({"id": ricetta["id"]})
    if eliminata.deleted_count:
        return True
    await db.ricette_cestino.delete_one({"id": voce["id"]})
    return False


async def elenca_cestino(db) -> list[dict]:
    voci = await db.ricette_cestino.find(
        {"ripristinata_at": {"$exists": False}}, {"_id": 0}
    ).to_list(5000)
    voci.sort(key=lambda voce: voce.get("eliminata_at") or "", reverse=True)
    return [{
        "id": voce.get("id"),
        "ricetta_id": voce.get("ricetta_id"),
        "nome": (voce.get("ricetta") or {}).get("nome"),
        "foto_url": (voce.get("ricetta") or {}).get("foto_url"),
        "eliminata_at": voce.get("eliminata_at"),
        "eliminata_da": voce.get("eliminata_da"),
        "motivo": voce.get("motivo"),
        "unita_in": voce.get("unita_in"),
    } for voce in voci]


async def ripristina_ricetta(db, voce_id: str, *, attore: str) -> tuple[str, str | None]:
    """Ripristina la stessa identità, senza cambiare storici o lotti collegati."""
    voce = await db.ricette_cestino.find_one({"id": voce_id}, {"_id": 0})
    if not voce:
        return "non_trovata", None
    ricetta = voce.get("ricetta") or {}
    ricetta_id = ricetta.get("id")
    if not ricetta_id:
        return "copia_incompleta", None
    if voce.get("ripristinata_at"):
        return "gia_ripristinata", ricetta_id
    if await db.ricette.find_one({"id": ricetta_id}, {"_id": 1}):
        return "id_occupato", ricetta_id
    base_id = ricetta.get("ricetta_base_id")
    if base_id and not await db.ricette.find_one({"id": base_id}, {"_id": 1}):
        return "base_assente", ricetta_id
    await db.ricette.insert_one(dict(ricetta))
    await db.ricette_cestino.update_one({"id": voce_id}, {"$set": {
        "ripristinata_at": _ora(), "ripristinata_da": attore,
    }})
    return "ripristinata", ricetta_id
