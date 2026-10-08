import uuid
from datetime import datetime, timezone, date, timedelta
from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE


class LearningCervello:
    async def registra_azione(
        self, db, tipo: str, chiave: str,
        valore, categoria: str = "generico"
    ):
        await db["agenti_apprendimenti"].update_one(
            {"categoria": categoria, "chiave": chiave},
            {
                "$set": {
                    "valore": valore,
                    "ultima_conferma": datetime.now(timezone.utc).isoformat()
                },
                "$inc": {"occorrenze": 1},
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "agente_sorgente": "LearningCervello",
                    "confidenza": 0.5,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
        # Aumenta confidenza con occorrenze (max 1.0 a 10 occorrenze)
        await db["agenti_apprendimenti"].update_one(
            {"categoria": categoria, "chiave": chiave},
            [{"$set": {"confidenza": {"$min": [1.0, {"$divide": ["$occorrenze", 10]}]}}}]
        )

    async def suggerisci(self, db, categoria: str, chiave: str):
        p = await db["agenti_apprendimenti"].find_one({
            "categoria": categoria,
            "chiave": {"$regex": chiave[:10], "$options": "i"},
            "confidenza": {"$gte": 0.6}
        })
        return p.get("valore") if p else None

    async def run(self, db):
        await self._genera_suggerimenti(db)

    async def _genera_suggerimenti(self, db):
        sessanta_gg = (date.today() - timedelta(days=60)).isoformat()
        vecchie = await db["invoices"].count_documents({
            **FILTRO_NON_PAGATE,
            "created_at": {"$lt": sessanta_gg}
        })
        if vecchie > 0:
            esistente = await db["agenti_segnalazioni"].find_one({
                "agente": "LearningCervello",
                "titolo": {"$regex": "fatture non pagate"},
                "risolta": {"$ne": True}
            })
            if not esistente:
                from app.agents.notifier import crea_segnalazione
                await crea_segnalazione(
                    db, agente="LearningCervello", tipo="avviso",
                    titolo=f"{vecchie} fatture non pagate da oltre 60 giorni",
                    descrizione=(
                        f"Ci sono {vecchie} fatture passive con data superiore a 60 giorni "
                        f"che risultano non pagate. Possibile problema di riconciliazione. "
                        f"Verifica in Fatture → Non pagate → filtra per data."
                    ),
                    azione="Fatture → Non pagate → filtra > 60 giorni"
                )
