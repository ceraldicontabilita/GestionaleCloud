"""
SERVIZIO LOTTI — unico punto di scrittura per la CREAZIONE di un lotto.
Fase 2 della ristrutturazione (13/06/2026).

Prima esistevano 5 punti di insert su db.lotti (lotti.py ×3, lotti_produzione.py
×2, gelati.py) ognuno con una FORMA DIVERSA del documento: chi scriveva
`numero_lotto`, chi `numero`; chi `prodotto`, chi `nome`; chi `esaurito`, chi
`stato`. Le viste a valle (dashboard, supervisore, magazzino) leggevano campi
che a volte non c'erano. Ora tutti passano da crea_lotto():
  - id e created_at garantiti
  - campi canonici sempre presenti (stato, esaurito, numero_lotto, prodotto)
  - UN evento LOTTO_CREATO pubblicato sul bus
  - inserimento UNA volta sola

I router NON chiamano più db.lotti.insert_one direttamente.

Tranche 0 (04/07/2026, HACCP features): oltre ai campi canonici, crea_lotto
ora costruisce anche la `posizione` strutturata (tipo/numero/nome/reparto/
operatore/quantità/data_ora) a partire dal solo `frigo_numero` storico, e
registra il primo evento nel registro movimenti (vedi
servizi/movimenti_lotto_service.py). `frigo_numero` resta scritto come
prima: nessun chiamante esistente va toccato.
"""
import logging
import uuid
from datetime import datetime, timezone

from app.lotti.db import database as db

_LOG = logging.getLogger("uvicorn.error")


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _determina_tipo_posizione(nome_o_numero: str) -> str:
    """Cerca in attrezzature_config se il nome/numero corrisponde a un frigo
    o un congelatore già censito. Prima di questa modifica `frigo_numero`
    era un'unica stringa libera usata per ENTRAMBI (vedi ModalRegistraLotto),
    quindi il default onesto per un nome sconosciuto resta 'frigo'."""
    if not nome_o_numero:
        return ""
    doc = await db.attrezzature_config.find_one(
        {"nome": nome_o_numero, "attivo": {"$ne": False}}, {"_id": 0, "tipo": 1}
    )
    return doc.get("tipo", "frigo") if doc else "frigo"


def _normalizza(doc: dict) -> dict:
    """Garantisce i campi canonici senza distruggere quelli specifici di dominio.
    Allinea i sinonimi storici così le viste a valle leggono sempre lo stesso campo."""
    d = dict(doc)
    d.setdefault("id", str(uuid.uuid4()))
    d.setdefault("created_at", _adesso())

    # Sinonimi → canonico (mantengo anche l'originale per retro-compatibilità)
    numero = d.get("numero_lotto") or d.get("numero") or d.get("codice_lotto") or ""
    if numero:
        d.setdefault("numero_lotto", numero)
    prodotto = d.get("prodotto") or d.get("nome") or d.get("descrizione") or ""
    if prodotto:
        d.setdefault("prodotto", prodotto)

    # Stato di consumo: storicamente `esaurito` (bool) o `stato` (stringa).
    # Canonico: entrambi coerenti.
    if "stato" not in d:
        d["stato"] = "smaltito" if d.get("esaurito") else "attivo"
    if "esaurito" not in d:
        d["esaurito"] = d.get("stato") == "smaltito"
    return d


async def crea_lotto(doc: dict, *, origine: str = "manuale") -> dict:
    """Crea UN lotto. `origine` descrive da dove nasce (manuale, produzione,
    ricezione, gelato) e finisce nell'evento per tracciabilità.
    Ritorna il documento pulito (senza _id)."""
    lotto = _normalizza(doc)
    lotto.setdefault("origine", origine)

    from app.lotti.servizi.movimenti_lotto_service import costruisci_posizione

    posizione = lotto.get("posizione")
    frigo_numero = lotto.get("frigo_numero") or ""
    if not posizione and frigo_numero:
        tipo = await _determina_tipo_posizione(frigo_numero)
        posizione = costruisci_posizione(
            tipo=tipo,
            numero=frigo_numero,
            nome=frigo_numero,
            reparto=lotto.get("reparto", ""),
            operatore_id=lotto.get("operatore_id", ""),
            operatore_nome=lotto.get("operatore_nome", ""),
            quantita=lotto.get("quantita"),
        )
    if posizione:
        lotto["posizione"] = posizione

    await db.lotti.insert_one(dict(lotto))
    lotto.pop("_id", None)

    # Evento sul bus: handler centralizzati (log, invalidazione cache) reagiscono.
    from app.lotti.eventi import publish
    await publish("LOTTO_CREATO", {
        "id": lotto["id"],
        "numero_lotto": lotto.get("numero_lotto", ""),
        "prodotto": lotto.get("prodotto", ""),
        "origine": origine,
        "data_scadenza": lotto.get("data_scadenza", ""),
    })

    # Registro movimenti: mai bloccare la creazione del lotto se questo fallisce.
    try:
        from app.lotti.servizi.movimenti_lotto_service import registra_movimento
        await registra_movimento(
            lotto["id"],
            "creazione",
            numero_lotto=lotto.get("numero_lotto", ""),
            posizione_a=posizione,
            quantita=lotto.get("quantita"),
            operatore_id=lotto.get("operatore_id", ""),
            operatore_nome=lotto.get("operatore_nome", ""),
            motivo=f"Lotto creato (origine: {origine})",
        )
    except Exception:
        _LOG.exception("[lotti_service] registrazione movimento creazione fallita (non bloccante)")

    return lotto
