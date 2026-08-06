"""
CARTA DI CREDITO NEXI (richiesta utente 18/07/2026).

Le singole spese con carta di credito NON compaiono mai nell'estratto
conto bancario: arriva solo l'ADDEBITO MENSILE Nexi (riga con "NEXI" nella
causale). Quindi:

1. quando in estratto conto BANCARIO compare un addebito Nexi, il sistema
   controlla di avere lo STATEMENT CARTA Nexi del periodo; se manca genera
   l'alert "Estratto conto Nexi mancante" che chiede di allegarlo;
2. quando lo statement carta c'è, l'addebito mensile si riconcilia con la
   somma delle operazioni della carta di quel periodo (tolleranza 0,01€);
   se non quadra → alert dedicato.

Riusa la pipeline PDF già esistente (`app.parsers.estratto_conto_nexi_parser`,
già collegata al download email in `email_monitor_service.py` /
`documenti.py:sync_estratti_conto`): stesse collezioni, stesso schema —
`estratto_conto_nexi` (un doc per statement caricato) e le singole
operazioni carta dentro `estratto_conto_movimenti` con `tipo="carta_credito"`.
Questo endpoint aggiunge solo la via MANUALE (allegare da Prima Nota
quando l'email non è arrivata) più il controllo di quadratura.
"""
import logging
import re
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COLL_ESTRATTI = "estratto_conto_nexi"
COLL_MOVIMENTI = "estratto_conto_movimenti"

# Riconoscimento dell'addebito mensile Nexi nella riga di BANCA (non delle
# singole spese carta, che vivono con tipo="carta_credito"/banca="Nexi").
_RE_NEXI = re.compile(r"\bNEXI\b|CARTASI|CARTA\s+SI\b", re.IGNORECASE)

_TOLLERANZA = 0.01


def _descr(doc: Dict[str, Any]) -> str:
    return doc.get("descrizione_originale") or doc.get("descrizione") or ""


def _norm_data(raw: str) -> str:
    """Normalizza a YYYY-MM-DD. In estratto_conto_movimenti convivono righe
    più vecchie in formato italiano GG/MM/AAAA e quelle più recenti già ISO:
    senza normalizzare, il calcolo del periodo (mese precedente) falliva in
    silenzio sulle righe italiane (returned "")."""
    s = str(raw or "").strip()[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return s


def _data(doc: Dict[str, Any]) -> str:
    return _norm_data(doc.get("data_contabile") or doc.get("data") or "")


def _e_movimento_carta(doc: Dict[str, Any]) -> bool:
    """Vero se la riga è una singola spesa carta (non un movimento banca)."""
    return doc.get("tipo") == "carta_credito" or doc.get("banca") == "Nexi"


def is_addebito_nexi(doc: Dict[str, Any]) -> bool:
    """Vero se la riga è l'addebito mensile Nexi sul CONTO BANCARIO."""
    if _e_movimento_carta(doc):
        return False
    tipo = doc.get("tipo")
    if tipo == "entrata":
        return False
    if tipo is None and float(doc.get("importo") or 0) > 0:
        return False
    return bool(_RE_NEXI.search(_descr(doc)))


def _periodo_addebito(data_addebito: str) -> str:
    """L'addebito Nexi di inizio mese salda le spese del MESE PRECEDENTE."""
    try:
        anno, mese = int(data_addebito[:4]), int(data_addebito[5:7])
    except (ValueError, TypeError):
        return ""
    if mese == 1:
        return f"{anno - 1}-12"
    return f"{anno}-{mese - 1:02d}"


def _chiave_addebito(doc: Dict[str, Any]) -> tuple:
    """Identita' prudente dell'addebito mensile.

    Gli import legacy possono aver copiato la stessa riga con ID tecnici
    diversi. Data, importo, conto/carta e periodo restano invece uguali. Un
    conto o carta differenti impediscono l'accorpamento.
    """
    data = _data(doc)
    importo = round(abs(float(doc.get("importo") or 0)), 2)
    rapporto = str(
        doc.get("conto") or doc.get("iban") or doc.get("rapporto")
        or doc.get("numero_carta_ultime4") or doc.get("carta") or ""
    ).strip().upper()
    return (_periodo_addebito(data), data, importo, rapporto)


async def verifica_addebiti_nexi(db, anno: Optional[int] = None) -> Dict[str, Any]:
    """Trova gli addebiti Nexi in EC bancario e verifica statement carta + quadratura.

    Per ogni addebito: se non ci sono operazioni carta di quel periodo →
    alert ESTRATTO_NEXI_MANCANTE; se ci sono → confronto con la somma delle
    operazioni (alert NEXI_ADDEBITO_NON_QUADRA se non torna, risoluzione
    automatica degli alert quando tutto quadra).
    """
    from app.services.alert_engine import genera_alert, risolvi_alert

    stats = {
        "addebiti_trovati": 0,
        "estratti_mancanti": 0,
        "riconciliati": 0,
        "non_quadrano": 0,
        "duplicati_ignorati": 0,
        "dettagli": [],
    }
    addebiti_visti = set()

    # Nessun filtro anno lato query Mongo: estratto_conto_movimenti ha righe
    # più vecchie con data in formato italiano GG/MM/AAAA accanto a quelle
    # ISO — un range string $gte/$lte sul grezzo escluderebbe le prime
    # silenziosamente (bug trovato in produzione il 18/07/2026). Si filtra
    # dopo, sulla data normalizzata.
    async for doc in db[COLL_MOVIMENTI].find({}):
        if not is_addebito_nexi(doc):
            continue
        data_add = _data(doc)
        if anno and not data_add.startswith(f"{anno}-"):
            continue
        identita_addebito = _chiave_addebito(doc)
        if identita_addebito in addebiti_visti:
            stats["duplicati_ignorati"] += 1
            continue
        addebiti_visti.add(identita_addebito)
        stats["addebiti_trovati"] += 1
        importo = round(abs(float(doc.get("importo") or 0)), 2)
        periodo = _periodo_addebito(data_add)
        suffisso_conto = hashlib.sha1(str(identita_addebito[-1]).encode("utf-8")).hexdigest()[:8]
        chiave = f"nexi_{periodo}_{suffisso_conto}"
        chiave_legacy = f"nexi_{periodo}"
        # Le versioni precedenti usavano una chiave solo per periodo e hanno
        # lasciato alert ripetuti/obsoleti. Li chiudiamo prima di applicare la
        # chiave per conto, cosi' il widget mostra una sola segnalazione viva.
        await risolvi_alert("ESTRATTO_NEXI_MANCANTE", chiave_legacy, db)
        await risolvi_alert("NEXI_ADDEBITO_NON_QUADRA", chiave_legacy, db)
        dettaglio_row = {
            "data_addebito": data_add,
            "importo": importo,
            "periodo": periodo,
            "stato": None,
        }

        totale_carta = 0.0
        n_operazioni = 0
        async for m in db[COLL_MOVIMENTI].find({
            "$and": [
                {"$or": [{"tipo": "carta_credito"}, {"banca": "Nexi"}]},
                {"data": {"$gte": f"{periodo}-01", "$lte": f"{periodo}-31"}},
            ]
        }):
            # NETTO, non valore assoluto: gli accrediti/storni (importo
            # negativo, es. rimborsi Amazon) vanno SOTTRATTI dal totale
            # addebitato, non sommati — altrimenti un rimborso gonfia la
            # spesa invece di ridurla e la quadratura con l'addebito
            # bancario (che è già il netto) non torna mai (bug 18/07/2026,
            # visto sul primo estratto Nexi reale caricato dall'utente).
            totale_carta += float(m.get("importo") or 0)
            n_operazioni += 1
        totale_carta = round(totale_carta, 2)

        if n_operazioni == 0:
            stats["estratti_mancanti"] += 1
            dettaglio_row["stato"] = "estratto_mancante"
            await genera_alert(
                "ESTRATTO_NEXI_MANCANTE", chiave, COLL_ESTRATTI,
                f"Addebito Nexi di {importo:.2f}€ del {data_add}: manca lo "
                f"statement carta Nexi del periodo {periodo}. Il gestionale lo "
                f"cerca automaticamente nell'area Documenti/Drive Carte; usa "
                f"l'allegato manuale soltanto se il file non e' presente, per riconciliare "
                f"le operazioni della carta.",
                db,
                extra={"data_addebito": data_add, "importo": importo, "periodo": periodo},
            )
        else:
            await risolvi_alert("ESTRATTO_NEXI_MANCANTE", chiave, db)
            diff = round(importo - totale_carta, 2)
            dettaglio_row["totale_carta"] = totale_carta
            dettaglio_row["operazioni_carta"] = n_operazioni
            dettaglio_row["differenza"] = diff
            if abs(diff) <= _TOLLERANZA:
                stats["riconciliati"] += 1
                dettaglio_row["stato"] = "riconciliato"
                await risolvi_alert("NEXI_ADDEBITO_NON_QUADRA", chiave, db)
                await db[COLL_MOVIMENTI].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"nexi_riconciliato": True, "nexi_periodo": periodo}},
                )
            else:
                stats["non_quadrano"] += 1
                dettaglio_row["stato"] = "non_quadra"
                await genera_alert(
                    "NEXI_ADDEBITO_NON_QUADRA", chiave, COLL_ESTRATTI,
                    f"Addebito Nexi {importo:.2f}€ del {data_add} ≠ somma "
                    f"operazioni carta {totale_carta:.2f}€ ({n_operazioni} "
                    f"operazioni) del periodo {periodo} (Δ {diff:+.2f}€).",
                    db,
                    extra=dettaglio_row,
                )
        stats["dettagli"].append(dettaglio_row)

    return stats


async def importa_estratto_nexi_pdf(
    db,
    filename: str,
    pdf_content: bytes,
    *,
    source: str = "upload_manuale_prima_nota",
    drive_file_id: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Allega manualmente uno statement carta Nexi (PDF) da Prima Nota,
    stessa pipeline/schema del download automatico via email."""
    import base64

    from app.parsers.estratto_conto_nexi_parser import parse_estratto_conto_nexi

    content_sha256 = hashlib.sha256(pdf_content).hexdigest()
    condizioni = [{"content_sha256": content_sha256}]
    if drive_file_id:
        condizioni.append({"drive_file_id": drive_file_id})
    existing = await db[COLL_ESTRATTI].find_one({"$or": condizioni}, {"_id": 0, "id": 1})
    if existing:
        return {
            "success": True,
            "duplicate": True,
            "estratto_id": existing.get("id"),
            "operazioni": 0,
            "totale_importo": 0,
        }

    result = parse_estratto_conto_nexi(pdf_content)
    if not result.get("success"):
        return {"success": False, "message": result.get("error", "Parsing PDF fallito")}

    transazioni = result.get("transazioni", [])
    if not transazioni:
        return {"success": False, "message": "Nessuna transazione riconosciuta nel PDF"}

    estratto_id = str(uuid.uuid4())
    await db[COLL_ESTRATTI].insert_one({
        "id": estratto_id,
        "filename": filename,
        "pdf_data": base64.b64encode(pdf_content).decode("utf-8"),
        "tipo": "nexi_carta",
        "metadata": result.get("metadata", {}),
        "totale_transazioni": len(transazioni),
        "import_date": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "drive_file_id": drive_file_id,
        "source_path": source_path,
        "content_sha256": content_sha256,
    })
    for idx, t in enumerate(transazioni):
        await db[COLL_MOVIMENTI].insert_one({
            "id": f"{estratto_id}_{idx}",
            "estratto_id": estratto_id,
            "data": t.get("data"),
            "descrizione": t.get("descrizione", ""),
            "importo": t.get("importo", 0),
            "tipo": "carta_credito",
            "banca": "Nexi",
            "categoria": t.get("categoria"),
            "riconciliato": False,
            "fattura_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    verifica = await verifica_addebiti_nexi(db)
    return {
        "success": True,
        "duplicate": False,
        "estratto_id": estratto_id,
        "operazioni": len(transazioni),
        "totale_importo": round(sum(t.get("importo") or 0 for t in transazioni), 2),
        "verifica": verifica,
    }
