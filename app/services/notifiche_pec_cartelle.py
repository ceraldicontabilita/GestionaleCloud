"""La data di notifica di una cartella di pagamento, dalla PEC che la notifica.

L'Agenzia delle Entrate-Riscossione notifica la cartella per PEC: la busta di Legalmail porta
l'oggetto «POSTA CERTIFICATA: Notifica cartella di pagamento n. 07120260127882548002 Codice
Fiscale …», il giorno e l'ora della trasmissione («Il giorno 24/09/2026 alle ore 11:06:23
(+0200) il messaggio … e' stato inviato da notifica.acc.campania@pec.agenziariscossione…») e
in allegato la cartella (`071-CRT-…-07120260127882548002-signed.pdf`).

Il PDF della cartella non dice quando e' stata notificata, e da quel giorno corrono i 60 giorni
per pagare: la data sta solo nella PEC. Qui la si legge e la si mette sulla cartella.

Regole:

* l'identita' e' il **numero della cartella** (20 cifre, le stesse dell'id `cartella:<numero>`),
  mai l'importo o il nome del file;
* la data e' quella scritta nella PEC (ora italiana), conservata con il messaggio che la prova;
* **arriva in qualunque ordine**: se la cartella non c'e' ancora, la notifica resta in
  `cartelle_notifiche_pec` e si applica appena la cartella viene registrata; se c'e' gia', si
  applica subito;
* la parola gia' data dal titolare non si sovrascrive: una data diversa resta annotata
  (`notifica_pec_diversa`) perche' la decida lui;
* la mail non si sposta ne' si cancella, e non si marca letta.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.services.cartelle_pagamento import COLL as COLL_CARTELLE, scadenza_da_notifica

COLL_NOTIFICHE = "cartelle_notifiche_pec"

_RE_OGGETTO = re.compile(r"NOTIFICA\s+CARTELLA\s+DI\s+PAGAMENTO\s+N\.?\s*(\d{20})\b", re.IGNORECASE)
_RE_GIORNO = re.compile(
    r"IL\s+GIORNO\s+(\d{2})/(\d{2})/(\d{4})\s+ALLE\s+ORE\s+(\d{2}:\d{2}:\d{2})\s*\(([+-]\d{4})\)",
    re.IGNORECASE,
)
_RE_MITTENTE = re.compile(r"inviato\s+da\s+\"([^\"]+)\"", re.IGNORECASE)


def e_notifica_cartella(oggetto: str) -> bool:
    """L'oggetto di una PEC che notifica una cartella (con o senza «POSTA CERTIFICATA:»)."""
    return bool(_RE_OGGETTO.search(oggetto or ""))


def leggi_notifica(oggetto: str, corpo: str) -> Optional[Dict[str, Any]]:
    """Numero della cartella e data della notifica; ``None`` se manca uno dei due (mai indovinati)."""
    numero = _RE_OGGETTO.search(oggetto or "")
    giorno = _RE_GIORNO.search(corpo or "")
    if not numero or not giorno:
        return None
    gg, mm, aaaa, ora, fuso = giorno.groups()
    try:
        datetime(int(aaaa), int(mm), int(gg))
    except ValueError:
        return None
    mittente = _RE_MITTENTE.search(corpo or "")
    return {
        "numero": numero.group(1),
        "data_notifica": f"{aaaa}-{mm}-{gg}",
        "ora": ora, "fuso": fuso,
        "mittente_originale": mittente.group(1).strip().lower() if mittente else None,
    }


async def applica_notifica(db, notifica: Dict[str, Any]) -> Dict[str, Any]:
    """Mette la data sulla cartella con quel numero, se c'e' e se non ne ha gia' una diversa."""
    cartella_id = f"cartella:{notifica['numero']}"
    cartella = await db[COLL_CARTELLE].find_one({"id": cartella_id}, {"_id": 0, "id": 1, "data_notifica": 1})
    if not cartella:
        return {"stato": "in_attesa_della_cartella", "cartella_id": cartella_id}
    ora = datetime.now(timezone.utc).isoformat()
    prova = {"data": notifica["data_notifica"], "ora": notifica.get("ora"),
             "messaggio": notifica.get("messaggio"), "mittente": notifica.get("mittente_originale")}
    attuale = cartella.get("data_notifica")
    if attuale and attuale != notifica["data_notifica"]:
        # Una data diversa gia' scritta (dal titolare): non si sovrascrive, si segnala.
        await db[COLL_CARTELLE].update_one({"id": cartella_id}, {"$set": {
            "notifica_pec": prova, "notifica_pec_diversa": True, "updated_at": ora}})
        return {"stato": "data_diversa_da_decidere", "cartella_id": cartella_id, "data_presente": attuale}
    await db[COLL_CARTELLE].update_one({"id": cartella_id}, {"$set": {
        "data_notifica": notifica["data_notifica"],
        "scadenza": scadenza_da_notifica(notifica["data_notifica"]),
        "scadenza_nota": "60 giorni dalla notifica per PEC, salvo festivita'",
        "data_notifica_fonte": "pec", "notifica_pec": prova, "notifica_pec_diversa": False,
        "updated_at": ora}})
    return {"stato": "applicata", "cartella_id": cartella_id}


async def registra_notifica_email(db, oggetto: str, corpo: str, *, messaggio_id: Optional[str] = None) -> Dict[str, Any]:
    """Una PEC di notifica letta dalla posta: si conserva (idempotente) e si applica alla cartella."""
    notifica = leggi_notifica(oggetto, corpo)
    if not notifica:
        return {"stato": "non_letta"}
    chiave = hashlib.sha256(f"{notifica['numero']}|{notifica['data_notifica']}|{notifica['ora']}".encode()).hexdigest()
    notifica["messaggio"] = messaggio_id
    gia = await db[COLL_NOTIFICHE].find_one({"id": chiave}, {"_id": 0, "id": 1})
    if not gia:
        await db[COLL_NOTIFICHE].insert_one({
            "id": chiave, **notifica, "oggetto": (oggetto or "")[:300],
            "registrata_il": datetime.now(timezone.utc).isoformat()})
    esito = await applica_notifica(db, notifica)
    return {**esito, "numero": notifica["numero"], "data_notifica": notifica["data_notifica"], "nuova": not gia}


async def applica_notifiche_in_attesa(db, cartella_id: str) -> Optional[Dict[str, Any]]:
    """Alla registrazione di una cartella: se la sua PEC era gia' arrivata, la data si mette adesso."""
    numero = str(cartella_id).split(":", 1)[-1]
    notifica = await db[COLL_NOTIFICHE].find_one({"numero": numero}, {"_id": 0}, sort=[("data_notifica", 1)])
    return await applica_notifica(db, notifica) if notifica else None
