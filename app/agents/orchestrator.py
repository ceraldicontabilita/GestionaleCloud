import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SCHEDULE = {
    "FiscaleSentinella": 600,    # ogni 10 minuti
    "LearningCervello": 3600,     # ogni ora
    "TesoreriaShadow": 3600,      # ogni ora, solo osservazioni/proposte
    "CashFlow13WShadow": 21600,   # ogni 6 ore, previsione deterministica
    "ContabileShadow": 21600,     # ogni 6 ore, ultimo collaudo minimizzato
    "FiscaleShadow": 21600,       # ogni 6 ore, obblighi e completezza aggregati
    "AcquistiShadow": 86400,      # giornaliero, prezzi e concentrazione fornitori
    "CreditiShadow": 86400,       # giornaliero, aging e bozze mai inviate
    "ComplianceShadow": 86400,    # giornaliero, permessi/audit/documenti
}


async def run_agenti(db, agente_specifico: str = None):
    """Esegue gli agenti schedulati. Se 'agente_specifico' e' valorizzato
    (bottone 'Esegui ora' su una singola card), esegue SOLO quell'agente e
    ignora l'intervallo di schedulazione (e' una richiesta manuale esplicita
    dell'utente, non il giro automatico)."""
    from dateutil.parser import parse as parse_date
    from app.agents.decision_engine import automazioni_sospese
    from app.agents.fiscale_sentinella import FiscaleSentinella
    from app.agents.learning_brain import LearningCervello
    from app.agents.tesoreria_shadow import TesoreriaShadow
    from app.agents.cash_flow_shadow import CashFlow13WShadow
    from app.agents.contabile_shadow import ContabileShadow
    from app.agents.fiscale_shadow import FiscaleShadow
    from app.agents.acquisti_shadow import AcquistiShadow
    from app.agents.crediti_shadow import CreditiShadow
    from app.agents.compliance_shadow import ComplianceShadow

    if await automazioni_sospese(db):
        raise RuntimeError("Automazioni AI fermate dall'interruttore globale")

    ora = datetime.now(timezone.utc)
    mappa = {
        "FiscaleSentinella": FiscaleSentinella,
        "LearningCervello": LearningCervello,
        "TesoreriaShadow": TesoreriaShadow,
        "CashFlow13WShadow": CashFlow13WShadow,
        "ContabileShadow": ContabileShadow,
        "FiscaleShadow": FiscaleShadow,
        "AcquistiShadow": AcquistiShadow,
        "CreditiShadow": CreditiShadow,
        "ComplianceShadow": ComplianceShadow,
    }

    if agente_specifico and agente_specifico not in mappa:
        raise ValueError(f"Agente sconosciuto: {agente_specifico}")

    for nome, intervallo in SCHEDULE.items():
        if agente_specifico and nome != agente_specifico:
            continue
        try:
            stato = await db["agenti_stato"].find_one({"agente": nome})
            ultima = stato.get("ultima_esecuzione") if stato else None
            deve_girare = True
            if ultima and not agente_specifico:
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
            if agente_specifico:
                raise
