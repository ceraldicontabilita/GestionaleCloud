"""«Questo fornitore e' sempre per cassa dal 01/01/2025»: il metodo del fornitore vale nel tempo.

Il metodo di pagamento si legge solo dall'anagrafica fornitore e da oggi ha una
data: `metodo_pagamento_dal` (ISO nel database, gg/mm/aaaa in pagina), la
stessa che lo storico `storico_metodi_pagamento` gia' registrava e che ogni
salvataggio della scheda riportava a oggi. Le fatture con data dal giorno «dal»
in poi seguono quel metodo.

Qui non c'e' un motore nuovo: per la Cassa si chiama **la stessa conferma di
Prima Nota** (`conferma_fattura_provvisoria`, con le sue guardie: gia' pagata,
esclusa, pagamento parziale, rate XML) che il titolare userebbe fattura per
fattura. La sua parola («sempre cassa») e' l'approvazione esplicita che quella
conferma richiede.

Regole che restano:
- una fattura gia' pagata **in banca o con assegno** (prova bancaria) non si
  tocca mai: si elenca come conflitto e decide il titolare;
- una cassa d'ufficio `metodo_fornitore_assente_provvisorio` non prova nulla
  (la riga non conta, la fattura resta aperta se non c'e' altro);
- note di credito, fatture estere, rate multiple e pagamenti parziali si
  elencano e non si forzano;
- niente scadenze fornitore, niente default inventati;
- `dry_run` per difetto; il secondo giro trova zero da chiudere.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from fastapi import HTTPException

from app.constants.tipi_documento import TIPI_NOTA_CREDITO
from app.services.stato_pagamento_fattura import e_pagata

logger = logging.getLogger(__name__)

CHIAVE_STATO = "metodo_fornitore_dal:"
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_IN_CORSO: set = set()

CAMPI_FATTURA = {
    "_id": 0, "id": 1, "invoice_key": 1, "invoice_number": 1, "invoice_date": 1,
    "total_amount": 1, "importo_totale": 1, "tipo_documento": 1, "supplier_name": 1,
    "supplier_vat": 1, "cedente_piva": 1, "fornitore_partita_iva": 1,
    "stato": 1, "stato_pagamento": 1, "payment_status": 1, "pagato": 1, "paid": 1,
    "prima_nota_id": 1, "prima_nota_tipo": 1, "prima_nota_banca_id": 1,
    "prima_nota_cassa_id": 1, "esclusa_da_cassa_banca": 1, "pagamento_rate": 1,
    "importo_ritenuta": 1, "stato_finanziario": 1, "estera": 1, "fattura_estera": 1,
    "metodo_pagamento": 1, "in_attesa_riscontro_banca": 1, "assegni_collegati": 1,
    "metodo_pagamento_effettivo": 1, "metodo_pagamento_previsto": 1,
}


def _piva(fornitore: Dict[str, Any]) -> str:
    from app.services.magazzino_fornitore import normalizza_piva

    for campo in ("partita_iva", "piva", "vat_number", "vat"):
        v = normalizza_piva(fornitore.get(campo))
        if v:
            return v
    return ""


def _dichiarata_altrove(f: Dict[str, Any]) -> str:
    """Motivo se la fattura ha gia' un altro destino dichiarato (banca, assegno): il titolare
    ha detto come e' stata pagata e il metodo del fornitore non lo scavalca."""
    if any(isinstance(a, dict) for a in (f.get("assegni_collegati") or [])):
        return "assegno collegato: segue il registro assegni"
    # La riga di Banca che l'import scrive da sola per un fornitore a bonifico (`provvisorio`, in attesa
    # dell'estratto) non e' una dichiarazione: su una fattura che nessuno ha detto pagata non conta.
    # Conta `prima_nota_tipo=banca` solo se qualcosa dice che la fattura e' stata pagata.
    pagata_dichiarata = e_pagata(f)
    if (((str(f.get("prima_nota_tipo") or "").lower() == "banca" or f.get("prima_nota_banca_id"))
            and pagata_dichiarata)
            or f.get("in_attesa_riscontro_banca")
            or str(f.get("stato_pagamento") or "").lower() == "in_attesa_banca"
            or str(f.get("stato_finanziario") or "").lower().startswith("pagata_dichiarata")):
        return "dichiarata in banca: attende l'estratto conto, non si sposta in Cassa"
    return ""


def _euro(valore: Any) -> Decimal:
    """Importo in euro al centesimo, mai float in mezzo ai conti."""
    try:
        return abs(Decimal(str(valore if valore not in (None, "") else 0))).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _riga(f: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    return {"id": f.get("id"), "numero": f.get("invoice_number"),
            "data": str(f.get("invoice_date") or "")[:10],
            "valuta": "EUR",
            "importo": float(_euro(f.get("total_amount") or f.get("importo_totale"))),
            **extra}


async def _fatture_dal(db, fornitore: Dict[str, Any], dal: str) -> List[Dict[str, Any]]:
    from app.database import Collections
    from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA

    piva = _piva(fornitore)
    varianti = [piva, f"IT{piva}"]
    righe = await db[Collections.INVOICES].find(
        {"$and": [FILTRO_FATTURA_ATTIVA, {"$or": [
            {"supplier_vat": {"$in": varianti}},
            {"cedente_piva": {"$in": varianti}},
            {"fornitore_partita_iva": {"$in": varianti}},
        ]}]},
        CAMPI_FATTURA,
    ).to_list(20000)
    scelte = [f for f in righe if str(f.get("invoice_date") or "")[:10] >= dal]
    scelte.sort(key=lambda f: (str(f.get("invoice_date") or ""), str(f.get("invoice_number") or "")))
    return scelte


def leggi_regola(fornitore: Dict[str, Any]) -> Dict[str, Any]:
    """Metodo e data «dal» del fornitore, oppure il motivo per cui non si puo' applicare."""
    from app.engines.prima_nota_engine import normalizza_metodo_pagamento

    metodo = normalizza_metodo_pagamento(fornitore.get("metodo_pagamento"))
    dal = str(fornitore.get("metodo_pagamento_dal") or "")[:10]
    if metodo != "cassa":
        raise HTTPException(
            status_code=409,
            detail=("Si applica solo il metodo Cassa: per la Banca serve una riga reale "
                    "dell'estratto conto per ogni fattura, mai il solo metodo del fornitore."))
    if not _ISO.fullmatch(dal):
        raise HTTPException(status_code=409, detail="Imposta «Metodo valido dal» sulla scheda fornitore.")
    return {"metodo": metodo, "dal": dal}


async def piano(db, fornitore: Dict[str, Any]) -> Dict[str, Any]:
    """Sola lettura: quali fatture il metodo chiuderebbe e quali no, col perche'."""
    from app.services.prima_nota_integrity import (
        fatture_senza_pagamento_contabile_confermato, trova_movimento_prima_nota_attivo,
    )
    from app.services.stato_pagamento_fattura import e_pagata

    regola = leggi_regola(fornitore)
    fatture = await _fatture_dal(db, fornitore, regola["dal"])
    esclusa_fornitore = bool(fornitore.get("esclude_cassa_banca") or fornitore.get("cessato"))
    aperte = await fatture_senza_pagamento_contabile_confermato(db, fatture)
    residuo_per_id = {str(a.get("id")): a for a in aperte}
    esito: Dict[str, Any] = {
        "fornitore": fornitore.get("ragione_sociale") or fornitore.get("denominazione"),
        "partita_iva": _piva(fornitore), "metodo": regola["metodo"], "dal": regola["dal"],
        "fatture_dal": len(fatture),
        "da_chiudere_in_cassa": [], "gia_in_cassa": [], "conflitto_banca_o_assegno": [],
        "non_forzate": [], "pagate_senza_riga": [],
    }
    for f in fatture:
        aperta = residuo_per_id.get(str(f.get("id")))
        tipo = str(f.get("prima_nota_tipo") or "").lower()
        if aperta is None:
            # chiusa: dove? La riga di Prima Nota attiva lo dice (anche quando il
            # campo sulla fattura manca: assegno riscontrato dall'estratto conto).
            movimento = await trova_movimento_prima_nota_attivo(db, f)
            collezione = (movimento or {}).get("collection")
            if collezione == "prima_nota_banca" or tipo == "banca":
                esito["conflitto_banca_o_assegno"].append(_riga(
                    f, motivo="pagata con prova in banca o assegno: non si sposta in Cassa"))
            elif collezione == "prima_nota_cassa" or tipo == "cassa":
                esito["gia_in_cassa"].append(_riga(f))
            else:
                esito["pagate_senza_riga"].append(_riga(
                    f, motivo="segnata pagata ma senza riga di Prima Nota che lo provi"))
            continue
        altrove = _dichiarata_altrove(f)
        if altrove:
            esito["conflitto_banca_o_assegno"].append(_riga(f, motivo=altrove))
        elif esclusa_fornitore or f.get("esclusa_da_cassa_banca"):
            esito["non_forzate"].append(_riga(f, motivo="esclusa da Cassa e Banca"))
        elif str(f.get("tipo_documento") or "").upper() in TIPI_NOTA_CREDITO:
            esito["non_forzate"].append(_riga(f, motivo="nota di credito: la decide il titolare"))
        elif f.get("estera") or f.get("fattura_estera"):
            esito["non_forzate"].append(_riga(f, motivo="fattura estera: da verificare"))
        elif len([r for r in (f.get("pagamento_rate") or []) if isinstance(r, dict)]) > 1:
            esito["non_forzate"].append(_riga(f, motivo="rate XML multiple: servono i singoli pagamenti"))
        elif float(aperta.get("_importo_pagato_confermato") or 0) > 0.01:
            esito["non_forzate"].append(_riga(f, motivo="gia' pagata in parte: il residuo vuole la banca"))
        else:
            residuo = aperta.get("_importo_residuo")
            esito["da_chiudere_in_cassa"].append(_riga(
                f, residuo=float(_euro(residuo)) if residuo is not None else _riga(f)["importo"],
                segnata_pagata_da_un_campo=bool(e_pagata(f))))
    esito["residuo_da_chiudere"] = float(
        sum((_euro(r["residuo"]) for r in esito["da_chiudere_in_cassa"]), Decimal("0.00")))
    return esito


async def _scrivi_stato(db, chiave: str, campi: Dict[str, Any]) -> None:
    await db["sistema_stato"].update_one(
        {"chiave": chiave}, {"$set": {"chiave": chiave, **campi}}, upsert=True)


async def stato(db, fornitore: Dict[str, Any]) -> Dict[str, Any]:
    return await db["sistema_stato"].find_one(
        {"chiave": CHIAVE_STATO + _piva(fornitore)}, {"_id": 0}) or {"stato": "mai_eseguito"}


async def _esegui(db, fornitore: Dict[str, Any], chiave: str) -> None:
    from app.routers.prima_nota_module.sync import conferma_fattura_provvisoria

    inizio = datetime.now(timezone.utc).isoformat()
    esiti: List[Dict[str, Any]] = []
    try:
        cosa = await piano(db, fornitore)
        await _scrivi_stato(db, chiave, {"stato": "in_corso", "iniziato_at": inizio,
                                         "da_chiudere": len(cosa["da_chiudere_in_cassa"])})
        for riga in cosa["da_chiudere_in_cassa"]:
            try:
                await conferma_fattura_provvisoria({
                    "fattura_id": riga["id"], "metodo": "cassa",
                    # la parola del titolare («sempre cassa dal ...») e' l'approvazione
                    "approva_metodo_fattura": True,
                })
                esiti.append({**riga, "esito": "registrata_in_cassa"})
            except HTTPException as exc:
                esiti.append({**riga, "esito": "rifiutata", "motivo": str(exc.detail)})
            except Exception as exc:  # noqa: BLE001 - una fattura rotta non ferma le altre
                logger.exception("[metodo_dal] fattura %s non registrata", riga.get("id"))
                esiti.append({**riga, "esito": "errore", "motivo": type(exc).__name__})
        await _scrivi_stato(db, chiave, {
            "stato": "completato", "terminato_at": datetime.now(timezone.utc).isoformat(),
            "registrate": sum(1 for e in esiti if e["esito"] == "registrata_in_cassa"),
            "scartate": sum(1 for e in esiti if e["esito"] != "registrata_in_cassa"),
            "esiti": esiti[:200],
        })
    except Exception as exc:  # noqa: BLE001 - il motivo si scrive
        logger.exception("[metodo_dal] giro fallito")
        await _scrivi_stato(db, chiave, {"stato": "errore",
                                         "errore": f"{type(exc).__name__}: {exc}"[:300]})
    finally:
        _IN_CORSO.discard(chiave)


async def applica(db, fornitore: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """`dry_run` (difetto): elenco e residui. Altrimenti parte in background, una volta sola."""
    if dry_run:
        return {"dry_run": True, **await piano(db, fornitore)}
    chiave = CHIAVE_STATO + _piva(fornitore)
    if chiave in _IN_CORSO:
        raise HTTPException(status_code=409, detail="Un giro per questo fornitore e' gia' in corso")
    leggi_regola(fornitore)  # rifiuta subito Banca / data mancante
    _IN_CORSO.add(chiave)
    asyncio.create_task(_esegui(db, fornitore, chiave))
    return {"dry_run": False, "avviato": True, "stato_url": "applica-metodo-dal/stato"}
