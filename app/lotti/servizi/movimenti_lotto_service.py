"""
SERVIZIO MOVIMENTI LOTTO — unico punto di scrittura per il registro
movimenti/posizione di un lotto (Tranche 0, HACCP features 04/07/2026).

Prima d'ora la posizione di un lotto (frigo/abbattitore/banco/magazzino)
era SOLO un concetto frontend (`destinazione` in ModalRegistraLotto.jsx),
mai scritta su db.lotti in forma strutturata: l'unico segnale persistito
era `frigo_numero` (stringa libera), e non esisteva alcuno storico degli
spostamenti (chi, quando, da dove, a dove, quanto, perché).

Questo modulo introduce:
  - `movimenti_lotto`: collection di audit trail, un documento per evento
    (creazione, spostamento, uso, banco, recupero, congelamento,
    smaltimento, spostamento massivo da anomalia).
  - `posizione` strutturata: {tipo, numero, nome, reparto, operatore_id,
    operatore_nome, quantita, data_ora} — sostituisce concettualmente
    `frigo_numero`, che resta scritto in parallelo per retrocompatibilità
    con tutto il codice esistente (LottiList, ModalRegistraLotto, stampa,
    supervisor_operativo, anomalie).

Nessun altro modulo deve scrivere direttamente su db.movimenti_lotto:
sempre da qui, come già `crea_lotto`/`scala_lotti_fornitori_per_ricetta`
per i rispettivi domini.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.lotti.db import database as db

TIPI_POSIZIONE = ("frigo", "congelatore", "abbattitore", "banco", "magazzino")

# Eventi noti (informativo — non impedisce stringhe custom per casi futuri)
TIPI_EVENTO = (
    "creazione",
    "spostamento",
    "uso",
    "banco",
    "recupero",
    "congelamento",
    "smaltimento",
    "spostamento_massivo_anomalia",
    "rientro_invenduto",
    "recall",
)


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def costruisci_posizione(
    tipo: str,
    numero: str = "",
    nome: str = "",
    reparto: str = "",
    operatore_id: str = "",
    operatore_nome: str = "",
    quantita: Optional[float] = None,
) -> Optional[dict]:
    """Costruisce l'oggetto posizione strutturato. Ritorna None se non c'è
    abbastanza informazione per essere utile (nessun tipo/numero)."""
    tipo = (tipo or "").strip().lower()
    numero = str(numero or "").strip()
    if not tipo and not numero:
        return None
    if tipo not in TIPI_POSIZIONE:
        tipo = "frigo" if numero else ""
    return {
        "tipo": tipo,
        "numero": numero,
        "nome": (nome or numero or "").strip(),
        "reparto": (reparto or "").strip(),
        "operatore_id": operatore_id or "",
        "operatore_nome": operatore_nome or "",
        "quantita": quantita,
        "data_ora": _adesso(),
    }


async def registra_movimento(
    lotto_id: str,
    tipo_evento: str,
    *,
    numero_lotto: str = "",
    posizione_da: Optional[dict] = None,
    posizione_a: Optional[dict] = None,
    quantita: Optional[float] = None,
    operatore_id: str = "",
    operatore_nome: str = "",
    motivo: str = "",
    azione_correttiva_haccp: Optional[str] = None,
    documento_collegato: Optional[dict] = None,
) -> dict:
    """Registra UN evento nel registro movimenti del lotto. Sola scrittura
    additiva: non modifica mai `db.lotti` (quello resta compito del
    chiamante, es. aggiornare `frigo_numero`/`posizione` sul lotto)."""
    doc = {
        "id": str(uuid.uuid4()),
        "lotto_id": lotto_id,
        "numero_lotto": numero_lotto or "",
        "tipo_evento": tipo_evento,
        "posizione_da": posizione_da,
        "posizione_a": posizione_a,
        "quantita": quantita,
        "operatore_id": operatore_id or "",
        "operatore_nome": operatore_nome or "",
        "motivo": motivo or "",
        "azione_correttiva_haccp": azione_correttiva_haccp,
        "documento_collegato": documento_collegato,
        "data_ora": _adesso(),
    }
    await db.movimenti_lotto.insert_one(dict(doc))
    doc.pop("_id", None)

    from app.lotti.eventi import publish
    await publish("LOTTO_MOVIMENTO", {
        "lotto_id": lotto_id,
        "numero_lotto": doc["numero_lotto"],
        "tipo_evento": tipo_evento,
    })
    return doc


async def cronologia_lotto(lotto_id: str) -> list:
    """Storico movimenti di un lotto, in ordine cronologico crescente."""
    return await db.movimenti_lotto.find(
        {"lotto_id": lotto_id}, {"_id": 0}
    ).sort("data_ora", 1).to_list(500)
