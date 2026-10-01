"""Notifiche PEC dei verbali: la prova di quando l'atto e' stato notificato.

La PEC della Polizia Locale porta la copia conforme del verbale e la relata di
notifica. La data della PEC e' la **data di notifica**: da li' partono i termini
di pagamento ridotto (5 giorni) e di ricorso (30 giorni Giudice di Pace, 60
giorni Prefetto). Qui non nasce un secondo verbale: la notifica si **aggancia al
verbale che ha lo stesso numero** (letto dalla copia conforme, mai dal nome file);
se quel verbale non esiste ancora resta in coda «da agganciare» sull'allegato.
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLL_ALLEGATI = "verbali_email_attachments"
GIORNI_PAGAMENTO_RIDOTTO = 5
GIORNI_GIUDICE_DI_PACE = 30
GIORNI_PREFETTO = 60

_UPEC_RE = re.compile(r"\[upec(\d+)\]", re.I)
_ATTO_RE = re.compile(r"Atto\s+(\d+)\s+del\s+(\d{2}/\d{2}/\d{4})", re.I)
_PER_CONTO_RE = re.compile(r"Per conto di:\s*([^\s\"<>]+@[^\s\"<>]+)", re.I)
_NUMERO_COPIA_RE = re.compile(
    r"Verbale\s+n\.?\s*([A-Z]\d{8,14})\b(?:\s*-\s*cronologico)?(?:\s+Registro\s+n\.?\s*(\d+))?"
    r"(?:\s+data\s+verbale\s+(\d{2}/\d{2}/\d{4}))?",
    re.I,
)


def _un_solo_spazio(valore: Any) -> str:
    return re.sub(r"\s+", " ", str(valore or "")).strip()


def _data_iso(valore: Any) -> Optional[str]:
    """Data della PEC come giorno ISO; vuoto se non leggibile (mai «oggi»)."""
    testo = str(valore or "").strip()
    if not testo:
        return None
    try:
        return parsedate_to_datetime(testo).date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(testo.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def metadati_notifica(oggetto: Any, mittente: Any, data_email: Any) -> Dict[str, Any]:
    """Identita' della notifica: id PEC dall'oggetto, ente dal «Per conto di»."""
    oggetto_pulito = _un_solo_spazio(oggetto)
    upec = _UPEC_RE.search(oggetto_pulito)
    atto = _ATTO_RE.search(oggetto_pulito)
    per_conto = _PER_CONTO_RE.search(str(mittente or ""))
    return {
        "upec_id": upec.group(1) if upec else None,
        "numero_registro": atto.group(1) if atto else None,
        "data_atto": atto.group(2) if atto else None,
        "ente_mittente": per_conto.group(1).lower() if per_conto else None,
        "data_notifica": _data_iso(data_email),
        "oggetto": oggetto_pulito,
    }


def scadenze_da_notifica(data_notifica: Optional[str]) -> Dict[str, str]:
    """Termini dalla notifica; senza data di notifica non si inventa nulla."""
    if not data_notifica:
        return {}
    try:
        giorno = date.fromisoformat(str(data_notifica)[:10])
    except ValueError:
        return {}
    return {
        "pagamento_ridotto": (giorno + timedelta(days=GIORNI_PAGAMENTO_RIDOTTO)).isoformat(),
        "ricorso_giudice_di_pace": (giorno + timedelta(days=GIORNI_GIUDICE_DI_PACE)).isoformat(),
        "ricorso_prefetto": (giorno + timedelta(days=GIORNI_PREFETTO)).isoformat(),
    }


def numero_da_copia_conforme(testo: str) -> Dict[str, Optional[str]]:
    """«Verbale n. A24110662140 - cronologico Registro n. … data verbale …»."""
    trovato = _NUMERO_COPIA_RE.search(testo or "")
    if not trovato:
        return {"numero_verbale": None, "numero_registro": None, "data_verbale": None}
    return {
        "numero_verbale": trovato.group(1).upper(),
        "numero_registro": trovato.group(2),
        "data_verbale": trovato.group(3),
    }


async def registra_notifica_pec(
    db, verbale: Dict[str, Any], notifica: Dict[str, Any], allegati: List[Dict[str, Any]],
) -> bool:
    """Scrive la notifica sul verbale, idempotente per id PEC. True se cambia qualcosa."""
    chiave = notifica.get("upec_id") or notifica.get("oggetto")
    esistenti = [dict(n) for n in (verbale.get("notifiche_pec") or []) if isinstance(n, dict)]
    voce = {
        "upec_id": notifica.get("upec_id"),
        "data_notifica": notifica.get("data_notifica"),
        "ente_mittente": notifica.get("ente_mittente"),
        "numero_registro": notifica.get("numero_registro"),
        "oggetto": notifica.get("oggetto"),
        "scadenze": scadenze_da_notifica(notifica.get("data_notifica")),
        "allegati": [
            {"id": a.get("id"), "filename": a.get("filename"), "hash": a.get("pdf_hash")}
            for a in allegati
        ],
    }
    voce = {k: v for k, v in voce.items() if v not in (None, "", [], {})}
    altre = [n for n in esistenti if (n.get("upec_id") or n.get("oggetto")) != chiave]
    campi: Dict[str, Any] = {
        "notifiche_pec": altre + [voce],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    prima = None
    if notifica.get("data_notifica"):
        # La PEC e' la prova della notifica: i termini contano dalla **prima** PEC
        # (una seconda non li sposta) e `data_notifica` e' quella data, anche se il
        # verbale ne portava un'altra nata dalla ricezione di una mail.
        prima = min(
            [n.get("data_notifica") for n in altre + [voce] if n.get("data_notifica")],
            default=notifica["data_notifica"],
        )
        campi["data_notifica"] = prima
        campi["data_notifica_fonte"] = "pec"
        campi["scadenze_ricorso"] = scadenze_da_notifica(prima)
        # La decisione «pagare ridotto» ha la sua scadenza: parte dalla notifica.
        ridotto = campi["scadenze_ricorso"].get("pagamento_ridotto")
        incorporate = [dict(a) for a in (verbale.get("workflow_expectations") or []) if isinstance(a, dict)]
        for attesa in incorporate:
            if attesa.get("expectation_type") == "DECISIONE_VERBALE" and ridotto:
                attesa["discount_deadline"] = ridotto
        if incorporate:
            campi["workflow_expectations"] = incorporate
    gia_allineata = (
        any((n.get("upec_id") or n.get("oggetto")) == chiave and n == voce for n in esistenti)
        and (prima is None or (
            verbale.get("data_notifica") == prima
            and (verbale.get("scadenze_ricorso") or {}) == campi.get("scadenze_ricorso")
            and all(
                a.get("discount_deadline") == campi["scadenze_ricorso"].get("pagamento_ridotto")
                for a in (verbale.get("workflow_expectations") or [])
                if isinstance(a, dict) and a.get("expectation_type") == "DECISIONE_VERBALE"
            )
        ))
    )
    if gia_allineata:
        return False
    await db["verbali_noleggio"].update_one({"id": verbale["id"]}, {"$set": campi})
    if prima:
        await db["workflow_expectations"].update_one(
            {"id": f"verbale:{verbale['id']}:DECISIONE_VERBALE"},
            {"$set": {"discount_deadline": campi["scadenze_ricorso"].get("pagamento_ridotto")}},
        )
    return True


async def _verbale_per_numero(db, numero: str) -> Optional[Dict[str, Any]]:
    """Il verbale vero con quel numero: mai le righe nate dalla sola PEC (`VERB-…`)."""
    candidati = await db["verbali_noleggio"].find(
        {"numero_verbale": numero}, {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    ).to_list(10)
    # Una riga in quarantena non e' un verbale (e' un numero di fattura letto come verbale):
    # non conta per l'unicita' e non riceve la notifica.
    veri = [v for v in candidati
            if v.get("id") and v.get("source") != "gmail_scan"
            and str(v.get("stato") or "").lower() != "quarantena"]
    return veri[0] if len(veri) == 1 else None


async def aggancia_notifiche_pec(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Aggancia le notifiche PEC in archivio ai verbali con lo stesso numero.

    Legge la copia conforme di ogni notifica, ne ricava il numero verbale e lo
    cerca fra i verbali veri. Senza verbale l'allegato resta «da_agganciare» con
    il numero letto: nessun verbale nuovo, nessuna cancellazione.
    """
    from app.services.verbali_document_import import _extract_text

    esito = {"dry_run": dry_run, "notifiche": 0, "agganciate": 0, "gia_agganciate": 0,
             "da_agganciare": 0, "senza_numero": 0, "errori": 0, "elenco_da_agganciare": []}
    righe = await db[COLL_ALLEGATI].find(
        {}, {"_id": 0, "pdf_data": 0}
    ).to_list(5000)
    gruppi: Dict[str, List[Dict[str, Any]]] = {}
    for riga in righe:
        meta = metadati_notifica(riga.get("email_subject"), riga.get("email_from"), riga.get("email_date"))
        if not meta["upec_id"]:
            continue
        gruppi.setdefault(meta["upec_id"], []).append({**riga, "_meta": meta})

    for upec, allegati in gruppi.items():
        esito["notifiche"] += 1
        meta = allegati[0]["_meta"]
        numero = None
        try:
            for allegato in sorted(allegati, key=lambda a: "COPIACONFORME" not in str(a.get("filename", "")).upper()):
                completo = await db[COLL_ALLEGATI].find_one({"id": allegato["id"]}, {"_id": 0, "pdf_data": 1})
                if not completo or not completo.get("pdf_data"):
                    continue
                testo = _extract_text(base64.b64decode(completo["pdf_data"]))
                numero = numero_da_copia_conforme(testo)["numero_verbale"]
                if numero:
                    break
        except Exception as exc:
            logger.warning("Notifica PEC %s non leggibile: %s: %s", upec, type(exc).__name__, exc)
            esito["errori"] += 1
            continue
        if not numero:
            esito["senza_numero"] += 1
            continue
        verbale = await _verbale_per_numero(db, numero)
        if not verbale:
            esito["da_agganciare"] += 1
            esito["elenco_da_agganciare"].append({"upec_id": upec, "numero_verbale": numero})
            if not dry_run:
                for allegato in allegati:
                    await db[COLL_ALLEGATI].update_one(
                        {"id": allegato["id"]},
                        {"$set": {"notifica_stato": "da_agganciare", "numero_verbale_letto": numero}},
                    )
            continue
        if dry_run:
            esito["agganciate"] += 1
            continue
        cambiato = await registra_notifica_pec(db, verbale, meta, allegati)
        esito["agganciate" if cambiato else "gia_agganciate"] += 1
        for allegato in allegati:
            await db[COLL_ALLEGATI].update_one(
                {"id": allegato["id"]},
                {"$set": {"notifica_stato": "agganciata", "numero_verbale_letto": numero,
                          "documento_associato_id": verbale["id"],
                          "documento_associato_collection": "verbali_noleggio",
                          "associato": True}},
            )
    esito["elenco_da_agganciare"] = esito["elenco_da_agganciare"][:100]
    return esito
