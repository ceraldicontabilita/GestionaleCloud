"""
BUS EVENTI — Fase 2 della ristrutturazione (13/06/2026).
I router PUBBLICANO fatti accaduti,
gli handler REAGISCONO. Un fatto, un punto di pubblicazione, N reazioni
registrate qui — mai logica incrociata sparsa nei router.

Eventi del dominio Lotti:
  FATTURA_IMPORTATA      {numero, fornitore, righe}
  PRODUZIONE_REGISTRATA  {lotto_numero, ricetta, reparto, pezzi}
  LOTTO_CREATO           {numero, tipo}
  LOTTO_MOVIMENTO        {lotto_id, numero_lotto, tipo_evento}
  ORDINE_CONFERMATO      {ordine_id, fornitore}
  ORDINE_INVIATO         {ordine_id, fornitore, righe}
  STOCK_MOVIMENTATO      {prodotto, tipo, quantita, stock_dopo}

Uso:
  from app.lotti.eventi import publish
  await publish("FATTURA_IMPORTATA", {...})

Gli handler NON devono mai far fallire l'operazione principale: ogni handler
gira in try/except e logga l'errore senza propagarlo.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger("uvicorn.error")

_handlers: dict = defaultdict(list)


def subscribe(evento: str, handler):
    """Registra un handler async per un evento. Da chiamare in registra_handlers()."""
    _handlers[evento].append(handler)
    return handler


def on(evento: str):
    """Decoratore: @on("FATTURA_IMPORTATA")."""
    def deco(fn):
        return subscribe(evento, fn)
    return deco


async def publish(evento: str, payload: dict | None = None):
    """Pubblica un evento. Gli handler girano in sequenza, ognuno protetto:
    un handler rotto non blocca né l'operazione né gli altri handler."""
    payload = payload or {}
    payload.setdefault("_evento", evento)
    payload.setdefault("_quando", datetime.now(timezone.utc).isoformat())
    for h in _handlers.get(evento, []):
        try:
            await h(dict(payload))
        except Exception as e:  # mai propagare: il bus non rompe il lavoro vero
            logger.error("[eventi] handler %s su %s fallito: %s", getattr(h, "__name__", h), evento, e)


# ─────────────────────────────────────────────────────────────────────────────
#  HANDLER REGISTRATI (l'elenco completo delle reazioni vive QUI, in un posto)
# ─────────────────────────────────────────────────────────────────────────────

def registra_handlers():
    """Chiamata una volta allo startup (server.py). Import locali per evitare
    cicli di import."""
    from app.lotti.db import database as db

    @on("FATTURA_IMPORTATA")
    async def _log_fattura(p):
        await db.log_eventi.insert_one({
            "evento": "FATTURA_IMPORTATA", "quando": p["_quando"],
            "numero": p.get("numero", ""), "fornitore": p.get("fornitore", ""),
            "righe": p.get("righe", 0),
        })

    @on("FATTURA_IMPORTATA")
    async def _invalida_cruscotto(p):
        # il cruscotto in cache va rinfrescato: i KPI spesa/sotto-scorta cambiano
        from app.lotti.routers.supervisor_operativo import invalida_cache_cruscotto
        invalida_cache_cruscotto()

    @on("LOTTO_CREATO")
    async def _log_lotto(p):
        await db.log_eventi.insert_one({
            "evento": "LOTTO_CREATO", "quando": p["_quando"],
            "numero_lotto": p.get("numero_lotto", ""), "prodotto": p.get("prodotto", ""),
            "origine": p.get("origine", ""),
        })

    @on("LOTTO_CREATO")
    async def _invalida_cruscotto_lotto(p):
        from app.lotti.routers.supervisor_operativo import invalida_cache_cruscotto
        invalida_cache_cruscotto()

    @on("LOTTO_MOVIMENTO")
    async def _log_movimento_lotto(p):
        await db.log_eventi.insert_one({
            "evento": "LOTTO_MOVIMENTO", "quando": p["_quando"],
            "lotto_id": p.get("lotto_id", ""), "numero_lotto": p.get("numero_lotto", ""),
            "tipo_evento": p.get("tipo_evento", ""),
        })

    @on("PRODUZIONE_REGISTRATA")
    async def _log_produzione(p):
        await db.log_eventi.insert_one({
            "evento": "PRODUZIONE_REGISTRATA", "quando": p["_quando"],
            "lotto": p.get("lotto_numero", ""), "ricetta": p.get("ricetta", ""),
            "reparto": p.get("reparto", ""), "pezzi": p.get("pezzi", 0),
        })

    @on("ORDINE_INVIATO")
    async def _log_ordine(p):
        await db.log_eventi.insert_one({
            "evento": "ORDINE_INVIATO", "quando": p["_quando"],
            "ordine_id": p.get("ordine_id", ""), "fornitore": p.get("fornitore", ""),
        })

    @on("ORDINE_INVIATO")
    async def _invalida_cruscotto_ordini(p):
        from app.lotti.routers.supervisor_operativo import invalida_cache_cruscotto
        invalida_cache_cruscotto()

    @on("STOCK_MOVIMENTATO")
    async def _invalida_cruscotto_stock(p):
        from app.lotti.routers.supervisor_operativo import invalida_cache_cruscotto
        invalida_cache_cruscotto()

    logger.info("[eventi] handlers registrati: %s", {k: len(v) for k, v in _handlers.items()})
