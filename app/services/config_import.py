"""Anno di importazione attivo — impostazione GLOBALE (richiesta utente
14/07/2026: "puoi mettere in qualche parte un selettore dove selezioni
l'anno che voglio importare?", un solo selettore condiviso, non uno per
canale).

Governa il filtro anno applicato SOLO ai canali di import automatico che
lo supportano oggi (Drive fatture, Drive corrispettivi): i documenti con
data nell'anno attivo entrano nel flusso contabile attivo (Prima Nota,
scadenzario, alert, magazzino); gli altri anni vengono archiviati per
sola consultazione. Non tocca l'upload manuale via UI, né AnnoContext.jsx
(che è solo un filtro di visualizzazione lato frontend, indipendente).

Persistito in `sistema_stato` (stessa collection già usata per lo stato
dei sync Drive) così sopravvive a riavvii/deploy — un parametro simile a
GOOGLE_DRIVE_FATTURE_FOLDER_ID ma che deve poter cambiare da UI senza
un redeploy.
"""
from datetime import datetime, timezone
from typing import Any, Dict

_CHIAVE = "config_import_anno_attivo"


async def get_anno_importazione_attivo(db) -> int:
    """Anno attivo per l'import automatico. Default: anno solare corrente
    se non è mai stato impostato esplicitamente."""
    doc = await db["sistema_stato"].find_one({"chiave": _CHIAVE}, {"_id": 0})
    if doc and isinstance(doc.get("anno"), int):
        return doc["anno"]
    return datetime.now(timezone.utc).year


async def set_anno_importazione_attivo(db, anno: int) -> Dict[str, Any]:
    if not isinstance(anno, int) or anno < 2000 or anno > 2100:
        raise ValueError("Anno non valido")
    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _CHIAVE},
        {"$set": {"anno": anno, "updated_at": now}},
        upsert=True,
    )
    return {"anno": anno, "updated_at": now}
