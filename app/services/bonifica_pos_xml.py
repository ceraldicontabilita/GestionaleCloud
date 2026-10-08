"""Bonifica dei trasferimenti POS ricavati dall'XML.

Fino al 07/08/2026 il motore, in assenza della chiusura del terminale, usava
l'elettronico XML come ripiego e scriveva righe tipo::

    POS 2026-08-03 -> Banca (da XML)   1.629,50

Quelle righe hanno un importo FISCALE, non operativo, e non appartengono a
nessun circuito: nessun accredito puo' riconciliarle, perche' Numia versa su
Banco BPM e SumUp sulla Mastercard. Restano aperte per sempre.

Cosa fa questa bonifica, e cosa NON fa:

- archivia le sole contropartite monetarie POS inventate dall'XML, conservando
  importo e provenienza nello storico di audit ma togliendole dai registri
  operativi e dai saldi;
- **non inventa il dato mancante.** Se il POS reale non c'e', la giornata
  resta segnalata senza importo POS: sara' la chiusura Numia o l'API SumUp a
  creare la scrittura corretta, passando dal motore unico;
- dove il dato reale esiste gia', rigenera le righe distinte per circuito.

L'analisi e' sempre in sola lettura: l'applicazione va chiesta esplicitamente.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Le righe nate dal ripiego XML portano questa fonte. La descrizione "(da XML)"
# e' solo il sintomo leggibile: la fonte e' il dato su cui si filtra.
FONTE_XML = "xml"
MOTIVO = "pos_da_xml_non_attendibile"


async def _leggi(cursore, n: int = 100000) -> List[Dict[str, Any]]:
    if hasattr(cursore, "to_list"):
        return await cursore.to_list(n)
    return [d async for d in cursore]


def _query(anno: Optional[int], registro: str) -> Dict[str, Any]:
    query: Dict[str, Any] = {
        "quota_pos_fonte": FONTE_XML,
        "status": {"$nin": ["deleted", "archived"]},
    }
    # Alcune vecchie ENTRATE Corrispettivi portano lo stesso metadato. Il
    # ricavo fiscale non va mai archiviato: limitiamo la bonifica alle sole
    # contropartite monetarie POS.
    if registro == "prima_nota_cassa":
        query.update({
            "tipo": "uscita",
            "$or": [
                {"categoria": {"$regex": "POS", "$options": "i"}},
                {"category": {"$regex": "POS", "$options": "i"}},
                {"source": {"$in": ["corrispettivo_import",
                                      "conferma_corrispettivo_manuale"]}},
            ],
        })
    else:
        query["$or"] = [
            {"categoria": "Corrispettivi POS"},
            {"category": "Corrispettivi POS"},
            {"source": {"$in": ["trasferimento_pos", "corrispettivo_pos",
                                  "chiusura_pos_mobile"]}},
        ]
    if anno:
        query["data"] = {"$regex": f"^{int(anno)}-"}
    return query


async def analizza(db, anno: Optional[int] = None) -> Dict[str, Any]:
    """Quante e quali righe POS derivano dall'XML. Sola lettura.

    Distingue le giornate che hanno gia' il POS reale (si sistemano da sole al
    prossimo riallineamento) da quelle che restano scoperte e vanno inserite a
    mano o attese dall'API.
    """
    from app.services.scritture_contabili import pos_reale_del_giorno

    cassa = await _leggi(db["prima_nota_cassa"].find(
        _query(anno, "prima_nota_cassa"), {"_id": 0}))
    banca = await _leggi(db["prima_nota_banca"].find(
        _query(anno, "prima_nota_banca"), {"_id": 0}))

    giornate: Dict[str, Dict[str, Any]] = {}
    for riga in cassa + banca:
        data = str(riga.get("data") or "")[:10]
        if not data:
            continue
        voce = giornate.setdefault(data, {
            "data": data, "importo_xml": 0.0,
            "righe_cassa": 0, "righe_banca": 0,
        })
        if riga in cassa:
            voce["righe_cassa"] += 1
            voce["importo_xml"] = round(float(riga.get("importo") or 0), 2)
        else:
            voce["righe_banca"] += 1

    coperte, scoperte = [], []
    for data in sorted(giornate):
        reale = await pos_reale_del_giorno(db, data)
        voce = giornate[data]
        voce["pos_reale"] = reale["totale_pos_reale"]
        voce["per_circuito"] = reale["per_circuito"]
        (coperte if reale["disponibile"] else scoperte).append(voce)

    return {
        "anno": anno,
        "giornate_totali": len(giornate),
        "righe_cassa": len(cassa),
        "righe_banca": len(banca),
        "importo_totale": round(sum(g["importo_xml"] for g in giornate.values()), 2),
        # Hanno gia' il dato vero: al prossimo riallineamento si correggono.
        "gia_coperte_dal_pos_reale": coperte,
        # Nessuna fonte reale: vanno inserite a mano o attese dall'API.
        "senza_pos_reale": scoperte,
    }


async def _applica_legacy(db, anno: Optional[int] = None,
                         actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Marca le righe da XML come non attendibili, senza cancellarle.

    Le giornate scoperte tornano in ``attende_chiusura_pos_reale``, cosi' la
    Coerenza POS le mostra fra quelle da completare invece di darle per buone.
    """
    esito = await analizza(db, anno)
    now = datetime.now(timezone.utc).isoformat()
    actor = actor or {}
    marcatura = {
        "$set": {
            "pos_fonte_attendibile": False,
            "bonifica_motivo": MOTIVO,
            "bonifica_at": now,
            "bonifica_by": actor.get("sub") or actor.get("user_id") or "sistema",
        }
    }

    aggiornate = 0
    for registro in ("prima_nota_cassa", "prima_nota_banca"):
        risultato = await db[registro].update_many(
            _query(anno, registro), marcatura
        )
        aggiornate += getattr(risultato, "modified_count", 0) or 0

    # Solo le giornate senza dato reale tornano "in attesa": quelle coperte
    # verranno corrette dal riallineamento e non vanno allarmate.
    giorni_scoperti = [g["data"] for g in esito["senza_pos_reale"]]
    if giorni_scoperti:
        await db["corrispettivi"].update_many(
            {"data": {"$in": giorni_scoperti}},
            {"$set": {"pos_stato": "attende_chiusura_pos_reale",
                      "pos_bonifica_at": now}},
        )

    # La riga NON viene mai tolta: la giornata deve comparire sempre in Prima
    # Nota, anche quando il valore reale manca. Il dato puo' mancare per
    # ragioni ordinarie — negozio chiuso, chiusura serale saltata, terminale
    # che consolida in ritardo secondo il calendario di accredito — e far
    # sparire la riga nasconderebbe proprio la giornata da controllare.
    # Resta quindi visibile e dichiarata PROVVISORIA, con l'importo XML come
    # valore di lavoro e non come verita' operativa.
    provvisorie = 0
    if giorni_scoperti:
        for registro in ("prima_nota_cassa", "prima_nota_banca"):
            risultato = await db[registro].update_many(
                {**_query(anno, registro), "data": {"$in": giorni_scoperti}},
                {"$set": {"pos_stato": "attende_chiusura_pos_reale",
                          "importo_provvisorio": True}},
            )
            provvisorie += getattr(risultato, "modified_count", 0) or 0

    return {
        **esito,
        "righe_marcate": aggiornate,
        "righe_provvisorie": provvisorie,
        "righe_archiviate": 0,   # per contratto: la riga resta sempre
        "giornate_riportate_in_attesa": len(giorni_scoperti),
        "cancellazioni": 0,   # per contratto: archivia, non elimina
    }


async def applica(db, anno: Optional[int] = None,
                  actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Esclude dai saldi il POS monetario inventato dall'XML.

    Le righe sono archiviate, non eliminate. Se esistono chiusure reali Numia
    o transazioni SumUp, il motore unico ricostruisce le contropartite separate
    per circuito; altrimenti la giornata resta in attesa senza importo fittizio.
    """
    esito = await analizza(db, anno)
    now = datetime.now(timezone.utc).isoformat()
    actor = actor or {}
    user_id = actor.get("sub") or actor.get("user_id") or "sistema"
    archivio = {"$set": {
        "pos_fonte_attendibile": False,
        "bonifica_motivo": MOTIVO,
        "bonifica_at": now,
        "bonifica_by": user_id,
        "status": "archived",
        "entity_status": "archived",
        "archived": True,
        "archived_reason": MOTIVO,
        "archived_at": now,
    }}

    archiviate = 0
    for registro in ("prima_nota_cassa", "prima_nota_banca"):
        risultato = await db[registro].update_many(
            _query(anno, registro), archivio)
        archiviate += getattr(risultato, "modified_count", 0) or 0

    giorni_scoperti = [g["data"] for g in esito["senza_pos_reale"]]
    if giorni_scoperti:
        await db["corrispettivi"].update_many(
            {"data": {"$in": giorni_scoperti}},
            {"$set": {"pos_stato": "attende_chiusura_pos_reale",
                      "pos_bonifica_at": now}},
        )

    from app.services.scritture_contabili import registra_corrispettivo
    ricostruite = 0
    for voce in esito["gia_coperte_dal_pos_reale"]:
        corr = await db["corrispettivi"].find_one(
            {"data": voce["data"]}, {"_id": 0})
        if corr:
            risultato = await registra_corrispettivo(db, corr)
            ricostruite += len(risultato.get("trasferimenti_pos") or {})

    if archiviate:
        await db["pos_bonifiche_audit"].insert_one({
            "tipo": "archiviazione_pos_monetario_da_xml",
            "anno": anno,
            "righe_archiviate": archiviate,
            "giornate": sorted({
                g["data"] for g in (
                    esito["gia_coperte_dal_pos_reale"] + esito["senza_pos_reale"]
                )
            }),
            "actor": user_id,
            "created_at": now,
        })

    return {
        **esito,
        "righe_marcate": archiviate,
        "righe_provvisorie": 0,
        "righe_archiviate": archiviate,
        "trasferimenti_reali_ricostruiti": ricostruite,
        "giornate_riportate_in_attesa": len(giorni_scoperti),
        "cancellazioni": 0,
    }


# --------------------------------------------------------------------------
# Normalizzazione delle descrizioni storiche
# --------------------------------------------------------------------------

# Le righe scritte prima del 07/08/2026 hanno la data ISO nella descrizione
# ("POS 2026-08-03 -> Banca") e due frecce diverse a seconda del percorso che
# le ha create. Sono testi letti da una persona: vanno in formato italiano.
_RE_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def descrizione_normalizzata(testo: Any) -> str:
    """Data italiana e freccia unica nelle descrizioni lette dall'utente."""
    normalizzato = _RE_DATA_ISO.sub(
        lambda m: f"{m.group(3)}/{m.group(2)}/{m.group(1)}", str(testo or ""))
    return normalizzato.replace("->", "→")


async def normalizza_descrizioni(db, anno: Optional[int] = None,
                                 applica: bool = False) -> Dict[str, Any]:
    """Riscrive le sole DESCRIZIONI storiche, senza toccare importi o date.

    E' una correzione di forma: nessun campo contabile viene modificato, solo
    il testo che compare in Prima Nota. Con ``applica=False`` (predefinito)
    non scrive nulla e restituisce un campione di cosa cambierebbe.
    """
    now = datetime.now(timezone.utc).isoformat()
    query: Dict[str, Any] = {"descrizione": {"$regex": r"\d{4}-\d{2}-\d{2}|->"}}
    if anno:
        query["data"] = {"$regex": f"^{int(anno)}-"}

    cambiate = 0
    esempi: List[Dict[str, str]] = []
    for registro in ("prima_nota_cassa", "prima_nota_banca"):
        for riga in await _leggi(db[registro].find(
                query, {"_id": 0, "id": 1, "descrizione": 1})):
            prima = str(riga.get("descrizione") or "")
            dopo = descrizione_normalizzata(prima)
            if dopo == prima:
                continue
            cambiate += 1
            if len(esempi) < 5:
                esempi.append({"prima": prima, "dopo": dopo})
            if applica:
                await db[registro].update_one(
                    {"id": riga.get("id")},
                    {"$set": {"descrizione": dopo, "description": dopo,
                              "descrizione_normalizzata_at": now}},
                )

    return {
        "anno": anno,
        "applicata": applica,
        "descrizioni_da_correggere" if not applica else "descrizioni_corrette": cambiate,
        "esempi": esempi,
    }
