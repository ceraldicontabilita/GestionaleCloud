"""
indici.py
---------
Crea gli indici MongoDB sulle collezioni più grandi e più interrogate.
Eseguito una volta allo startup (idempotente: create_index non duplica indici esistenti).

Motivazione: collezioni come lotti_fornitori (17k doc) venivano interrogate per
nome/fornitore senza indici, costringendo MongoDB a scorrere l'intera collezione
ad ogni ricerca (e ad ogni produzione, che cerca i lotti per ingrediente).
"""
import logging

logger = logging.getLogger(__name__)


async def crea_indici(db):
    """Crea gli indici utili in modo idempotente. Ogni indice è protetto da try/except
    così un singolo fallimento non blocca gli altri né lo startup."""
    # (collezione, lista di indici) — ogni indice è un campo singolo o una lista di tuple
    piano = {
        "lotti_fornitori": [
            "prodotto_nome_norm",   # usato dallo scarico produzione (FIFO per ingrediente)
            "nome_canonico",        # match FIFO per canonico (qualsiasi fornitore)
            "fornitore",
            "esaurito",
            [("esaurito", 1), ("quantita_disponibile", -1)],  # query composta dello scarico
            [("nome_canonico", 1), ("esaurito", 1), ("quantita_disponibile", -1)],  # scarico per canonico
            "data_scadenza",        # ordinamento FIFO
        ],
        "magazzino_bar_movimenti": ["prodotto_id", "tipo", "data"],
        "magazzino_bar_prodotti": ["categoria"],
        "sconti_merce": ["fornitore", "fattura_riferimento"],
        "fatture": ["fornitore", "numero_fattura", "data_fattura"],
        "corrispettivi": ["data"],
        "ordini_fornitori": ["stato", "data_ordine"],
        "dizionario_prodotti": ["nome_normalizzato"],
    }

    # ── Rubinetto a monte: elimina i documenti-fattura duplicati e impedisci che
    #    se ne creino altri. Chiave d'identità = (numero_fattura, piva).
    try:
        visti = {}
        doppi = []
        async for f in db.fatture.find({}, {"_id": 1, "numero_fattura": 1, "piva": 1, "fornitore": 1}):
            chiave = (
                str(f.get("numero_fattura") or "").strip().upper(),
                str(f.get("piva") or f.get("fornitore") or "").strip().upper(),
            )
            if chiave in visti:
                doppi.append(f["_id"])
            else:
                visti[chiave] = f["_id"]
        if doppi:
            res = await db.fatture.delete_many({"_id": {"$in": doppi}})
            logger.warning(f"[FATTURE] rimossi {res.deleted_count} documenti duplicati")
        # indice unique: blocca i futuri inserimenti doppi alla radice
        await db.fatture.create_index(
            [("numero_fattura", 1), ("piva", 1)], unique=True, name="uniq_numero_piva"
        )
        logger.info("[FATTURE] indice unique (numero_fattura, piva) attivo")
    except Exception as e:
        logger.warning(f"[FATTURE] dedup/unique: {e}")

    creati = 0
    for collezione, indici in piano.items():
        for idx in indici:
            try:
                await db[collezione].create_index(idx)
                creati += 1
            except Exception as e:
                logger.warning(f"[INDICI] {collezione} {idx}: {e}")
    logger.info(f"[INDICI] verificati/creati {creati} indici")
    return creati
