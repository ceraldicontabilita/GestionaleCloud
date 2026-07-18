"""
MOTORE UNICO DI SCRITTURA CONTABILE — Fase A (decisione utente 18/07/2026:
"subito, per gradi").

Ogni movimento di Prima Nota deve nascere da qui: un solo punto che valida
e scrive, così le regole del modello non possono divergere tra i flussi.
La migrazione è graduale: i writer storici vengono portati qui uno alla
volta (primo: corrispettivi/POS) e un test-guardia vieta di aggiungerne
di nuovi altrove.

MODELLO POS (decisione utente 18/07/2026, conferma dell'audit):
- CASSA entrata  = totale corrispettivo del giorno (contanti + POS);
- CASSA uscita "POS Verso Banca" = la CHIUSURA MANUALE serale del
  terminale ("quello che esce dal terminale è il vero incasso POS");
  fallback: elettronico XML quando la chiusura non è stata trascritta;
- BANCA entrata  = l'ACCREDITO REALE dell'estratto conto (data e importo
  della banca, per circuito), MAI una riga sintetica alla data del
  corrispettivo. L'XML resta il confronto fiscale (Coerenza POS).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REGISTRI = {"cassa": "prima_nota_cassa", "banca": "prima_nota_banca"}


class ScritturaNonValida(ValueError):
    pass


def _valida(mov: Dict[str, Any]) -> None:
    data = str(mov.get("data") or "")
    if len(data) < 10 or data[4] != "-":
        raise ScritturaNonValida(f"data non valida: {data!r}")
    if float(mov.get("importo") or 0) <= 0:
        raise ScritturaNonValida(f"importo non positivo: {mov.get('importo')!r}")
    if mov.get("tipo") not in ("entrata", "uscita"):
        raise ScritturaNonValida(f"tipo non valido: {mov.get('tipo')!r}")
    if not mov.get("categoria"):
        raise ScritturaNonValida("categoria mancante")
    if not mov.get("source"):
        raise ScritturaNonValida("source mancante (tracciabilità obbligatoria)")


async def scrivi_movimento(db, registro: str, mov: Dict[str, Any]) -> str:
    """Unico punto di INSERT nei registri di Prima Nota: valida e scrive.
    Ritorna l'id del movimento creato."""
    if registro not in REGISTRI:
        raise ScritturaNonValida(f"registro sconosciuto: {registro}")
    _valida(mov)
    doc = dict(mov)
    doc.setdefault("id", str(uuid.uuid4()))
    doc["importo"] = round(float(doc["importo"]), 2)
    doc.setdefault("amount", doc["importo"])
    doc.setdefault("date", doc["data"])
    doc.setdefault("type", doc["tipo"])
    doc.setdefault("category", doc["categoria"])
    doc.setdefault("description", doc.get("descrizione", ""))
    doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    await db[REGISTRI[registro]].insert_one(dict(doc))
    return doc["id"]


async def _leggi_tutti(cursor, n: int = 100):
    """Compat: cursori Motor reali (async for) e fake dei test (to_list)."""
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(n)
    return [c async for c in cursor]


async def chiusura_pos_del_giorno(db, data: str) -> Optional[float]:
    """Chiusura manuale serale del terminale POS per il giorno (se trascritta)."""
    tot = 0.0
    trovata = False
    try:
        for c in await _leggi_tutti(db["chiusure_pos_manuali"].find(
                {"data": data}, {"_id": 0, "importo": 1, "totale": 1})):
            trovata = True
            tot += float(c.get("importo") or c.get("totale") or 0)
        if not trovata:
            # fallback storico: chiusure importate in prima_nota_banca con
            # source import_manuale_pos (vecchio flusso pos.xlsx)
            for c in await _leggi_tutti(db["prima_nota_banca"].find(
                    {"data": data, "source": "import_manuale_pos"},
                    {"_id": 0, "importo": 1})):
                trovata = True
                tot += float(c.get("importo") or 0)
    except AttributeError:
        return None  # backend/fake senza le collezioni delle chiusure
    return round(tot, 2) if trovata and tot > 0 else None


async def registra_corrispettivo(db, corr_doc: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Scritture del corrispettivo giornaliero secondo il MODELLO POS.

    NON scrive mai la banca: l'entrata banca nasce solo dall'accredito
    reale dell'estratto conto (registra_accredito_pos_ec)."""
    data = corr_doc.get("data") or corr_doc.get("data_operazione") or ""
    contanti = float(corr_doc.get("pagato_contanti") or 0)
    elettronico = float(corr_doc.get("pagato_elettronico") or corr_doc.get("pagato_pos") or 0)
    totale = float(corr_doc.get("totale") or corr_doc.get("totale_complessivo")
                   or corr_doc.get("importo") or corr_doc.get("totale_giornaliero")
                   or (contanti + elettronico) or 0)
    if contanti == 0 and elettronico == 0 and totale > 0:
        contanti = totale

    anno = int(data[:4]) if data[:4].isdigit() else datetime.now().year
    mese = int(data[5:7]) if len(data) >= 7 and data[5:7].isdigit() else datetime.now().month
    matricola = corr_doc.get("matricola_rt") or corr_doc.get("id_dispositivo") or None

    esito: Dict[str, Optional[str]] = {
        "prima_nota_cassa_id": None,
        "prima_nota_cassa_uscita_pos_id": None,
        "prima_nota_banca_id": None,  # sempre None: la banca nasce dall'EC
    }
    if not data or totale <= 0:
        return esito

    # IDEMPOTENZA (stessa guardia storica, chiave data+matricola)
    gia = await db["prima_nota_cassa"].find_one({
        "data": data, "tipo": "entrata", "categoria": "Corrispettivi",
        "matricola_rt": matricola,
        "source": {"$in": ["corrispettivo_import", "corrispettivi_sync",
                            "corrispettivo_xml", "xml_import", "manuale_da_xml",
                            "corrispettivo_manuale"]},
    })
    if gia:
        esito["prima_nota_cassa_id"] = gia.get("id")
        esito["gia_esistente"] = True
        return esito

    esito["prima_nota_cassa_id"] = await scrivi_movimento(db, "cassa", {
        "corrispettivo_id": corr_doc.get("id"),
        "data": data, "tipo": "entrata", "importo": totale,
        "descrizione": f"Corrispettivi {data}",
        "categoria": "Corrispettivi", "source": "corrispettivo_import",
        "anno": anno, "mese": mese, "matricola_rt": matricola,
        "imponibile": round(float(corr_doc.get("totale_imponibile") or 0), 2),
        "iva": round(float(corr_doc.get("totale_iva") or 0), 2),
        "contanti": round(contanti, 2), "elettronico": round(elettronico, 2),
        "dettaglio": {"contanti": round(contanti, 2),
                      "elettronico": round(elettronico, 2),
                      "matricola_rt": corr_doc.get("matricola_rt", ""),
                      "numero_documenti": corr_doc.get("numero_documenti", 0)},
    })

    # USCITA POS: la chiusura manuale serale è il dato operativo vero;
    # l'elettronico XML è solo il fallback quando non è stata trascritta.
    chiusura = await chiusura_pos_del_giorno(db, data)
    quota_pos = chiusura if chiusura is not None else elettronico
    fonte_quota = "chiusura_manuale" if chiusura is not None else "xml"
    if quota_pos > 0:
        esito["prima_nota_cassa_uscita_pos_id"] = await scrivi_movimento(db, "cassa", {
            "corrispettivo_id": corr_doc.get("id"),
            "data": data, "tipo": "uscita", "importo": quota_pos,
            "descrizione": (f"POS {data} → Banca"
                            + (" (chiusura terminale)" if fonte_quota == "chiusura_manuale"
                               else " (da XML)")),
            "categoria": "POS Verso Banca", "source": "corrispettivo_import",
            "quota_pos_fonte": fonte_quota,
            "anno": anno, "mese": mese,
        })
    return esito


async def registra_accredito_pos_ec(db, mov_ec: Dict[str, Any]) -> Optional[str]:
    """BANCA entrata = accredito POS REALE dell'estratto conto.
    Idempotente per estratto_conto_id. Ritorna l'id creato o None."""
    from app.routers.pos_corrispettivi_check import _giorno_operazione_pos

    ec_id = mov_ec.get("id")
    if not ec_id:
        return None
    gia = await db["prima_nota_banca"].find_one(
        {"estratto_conto_id": ec_id, "status": {"$nin": ["deleted", "archived"]}},
        {"_id": 0, "id": 1})
    if gia:
        return None
    data_acc = (mov_ec.get("data") or "")[:10]
    descr = mov_ec.get("descrizione_originale") or mov_ec.get("descrizione") or ""
    giorno_vendita = _giorno_operazione_pos(descr, data_acc)
    pn_id = await scrivi_movimento(db, "banca", {
        "data": data_acc, "tipo": "entrata",
        "importo": abs(float(mov_ec.get("importo") or 0)),
        "descrizione": f"Accredito POS {descr[:60]}",
        "categoria": "Corrispettivi POS",
        "source": "ec_accredito_pos",
        "estratto_conto_id": ec_id,
        "giorno_vendita": giorno_vendita,
        "riconciliato": True,
        "anno": int(data_acc[:4]) if data_acc[:4].isdigit() else None,
        "mese": int(data_acc[5:7]) if len(data_acc) >= 7 and data_acc[5:7].isdigit() else None,
    })
    await db["estratto_conto_movimenti"].update_one(
        {"id": ec_id},
        {"$set": {"riconciliato": True,
                  "tipo_riconciliazione": "accredito_pos_prima_nota",
                  "dettagli_riconciliazione": {"prima_nota_id": pn_id}}})
    return pn_id


def query_accrediti_pos_ec(anno: int) -> Dict[str, Any]:
    """Filtro canonico per riconoscere gli accrediti POS nell'estratto conto."""
    return {
        "data": {"$regex": f"^{anno}"},
        "tipo": {"$ne": "uscita"},
        "$or": [
            {"categoria": {"$regex": "Incasso tramite POS", "$options": "i"}},
            {"descrizione_originale": {"$regex": "NUMIA|INC\\.POS|INCAS\\. TRAMITE P\\.O\\.S",
                                        "$options": "i"}},
        ],
    }
