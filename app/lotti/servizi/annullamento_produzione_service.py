"""Annullamento tracciato di una registrazione di produzione e del suo lotto."""

from datetime import datetime, timezone

from fastapi import HTTPException

from app.lotti.db import database as db
from app.lotti.servizi.annullamento_lotto_service import annulla_lotto


async def annulla_produzione(produzione_id: str, motivo: str, actor: dict) -> dict:
    produzione = await db.produzioni.find_one({"id": produzione_id})
    if not produzione:
        raise HTTPException(404, "Produzione non trovata")
    if produzione.get("stato") == "annullata":
        if produzione.get("motivo_annullamento") != motivo:
            raise HTTPException(409, "Produzione già annullata con un'altra motivazione")
        return {"ok": True, "produzione_id": produzione_id, "stato": "annullata"}

    numero_lotto = produzione.get("numero_lotto")
    if numero_lotto:
        lotto = await db.lotti.find_one({"numero_lotto": numero_lotto})
        if not lotto:
            raise HTTPException(409, "Lotto collegato assente: rettifica manuale necessaria")
        if lotto.get("stato") == "annullato" and lotto.get("motivo_annullamento") != motivo:
            raise HTTPException(409, "Lotto già annullato con altra motivazione")
        await annulla_lotto(lotto.get("id") or lotto.get("lotto_id"), motivo, actor)
    else:
        raise HTTPException(409, "Lotto non identificato: rettifica manuale necessaria")

    # Il lotto e la produzione restano nell'archivio. Le scorte dei fornitori non
    # vengono aumentate senza una rettifica comprovata; un retry non le duplica.
    await db.produzioni.update_one(
        {"id": produzione_id, "stato": {"$ne": "annullata"}},
        {"$set": {
            "stato": "annullata", "motivo_annullamento": motivo,
            "annullata_il": datetime.now(timezone.utc).isoformat(),
            "annullata_da_id": actor["id"], "annullata_da_nome": actor["nome"],
        }},
    )
    return {"ok": True, "produzione_id": produzione_id, "stato": "annullata"}
