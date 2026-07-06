import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SCHEDULE = {
    "FiscaleSentinella": 600,    # ogni 10 minuti
    "LearningCervello": 3600,     # ogni ora
}


async def run_agenti(db):
    from dateutil.parser import parse as parse_date
    from app.agents.fiscale_sentinella import FiscaleSentinella
    from app.agents.learning_brain import LearningCervello

    ora = datetime.now(timezone.utc)
    mappa = {
        "FiscaleSentinella": FiscaleSentinella,
        "LearningCervello": LearningCervello,
    }

    for nome, intervallo in SCHEDULE.items():
        try:
            stato = await db["agenti_stato"].find_one({"agente": nome})
            ultima = stato.get("ultima_esecuzione") if stato else None
            deve_girare = True
            if ultima:
                diff = (ora - parse_date(ultima)).total_seconds()
                deve_girare = diff >= intervallo
            if deve_girare:
                agente = mappa[nome]()
                await agente.run(db)
                await db["agenti_stato"].update_one(
                    {"agente": nome},
                    {"$set": {
                        "ultima_esecuzione": ora.isoformat(),
                        "stato": "completato",
                        "ultimo_errore": None
                    }},
                    upsert=True
                )
                logger.info(f"Agente {nome} completato")
        except Exception as e:
            logger.error(f"Agente {nome}: {e}")
            await db["agenti_stato"].update_one(
                {"agente": nome},
                {"$set": {"stato": "errore", "ultimo_errore": str(e)}},
                upsert=True
            )
