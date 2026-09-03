"""
Router dedup fornitori — gestione duplicati per P.IVA e record identici.

Due fornitori con stessa P.IVA sono lo stesso soggetto legale anche se scritti
diversamente (es. "Drink Up S.r.l." vs "DRINK UP SRL"). Questi endpoint trovano
i duplicati e permettono all'utente di fonderli da UI.

Fa parte del gruppo tag "Fornitori" — condivide prefix "/fornitori".
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from pydantic import BaseModel
import re as _re

from app.lotti.db import database as db

router = APIRouter(prefix="/fornitori", tags=["Fornitori"])


def _piva_norm(v) -> str:
    """P.IVA normalizzata per confronto: via spazi e prefisso paese 'IT'.
    'IT06626921214' e '06626921214' sono lo stesso soggetto."""
    p = _re.sub(r"\s+", "", str(v or "")).upper()
    return p[2:] if p.startswith("IT") and len(p) > 10 else p


def _nome_doc(d) -> str:
    """Nome del fornitore da QUALSIASI schema: HACCP usa `nome`, i record
    scritti dal gestionale Cloud usano `ragione_sociale`/`denominazione`."""
    return ((d.get("nome") or d.get("ragione_sociale") or d.get("denominazione") or "")
            .strip().strip('"').strip("'").strip())


def _piva_doc(d) -> str:
    """P.IVA da qualsiasi schema: HACCP usa `piva`, l'ERP `partita_iva`."""
    return _piva_norm(d.get("piva") or d.get("partita_iva") or "")


@router.get("/duplicati-per-piva")
async def lista_duplicati_piva():
    """Restituisce gruppi di fornitori che condividono la stessa P.IVA.
    Solo P.IVA con almeno 8 caratteri per escludere dati spuri tipo '03473'.
    FIX 23/07/2026 ("deduplica non funziona"): prima raggruppava SOLO sul
    campo `piva` e leggeva SOLO `nome` — ma metà dei record (quelli scritti
    dal gestionale Cloud sul DB condiviso) usano `partita_iva` e
    `ragione_sociale`/`denominazione`, e le P.IVA col prefisso "IT" non
    combaciavano mai: quei duplicati risultavano invisibili."""
    tutti = await db.fornitori.find({}, {"_id": 0}).to_list(5000)
    per_piva: dict = {}
    for d in tutti:
        p = _piva_doc(d)
        if p:
            per_piva.setdefault(p, []).append(d)

    gruppi = []
    for piva, docs in per_piva.items():
        if len(docs) < 2 or len(piva) < 8:
            continue
        varianti = []
        visti_nomi = set()
        for f in docs:
            nome = _nome_doc(f)
            if not nome or nome.lower() in visti_nomi:
                continue
            visti_nomi.add(nome.lower())
            num_fatt_reali = await db.fatture.count_documents(
                {"fornitore": {"$regex": f"^\\s*{_re.escape(nome)}\\s*$", "$options": "i"}}
            )
            varianti.append(
                {
                    "id": f.get("id", ""),
                    "nome": nome,
                    "num_fatture_reali": num_fatt_reali,
                    "ultima_fattura": f.get("ultima_fattura", ""),
                    "stato": f.get("stato", "attivo"),
                    "escluso": bool(f.get("escluso")),
                    "created_at": f.get("created_at", ""),
                    "updated_at": f.get("updated_at", ""),
                }
            )
        if len(varianti) < 2:
            continue
        varianti.sort(key=lambda v: (-v["num_fatture_reali"], v["nome"]))
        gruppi.append(
            {
                "piva": piva,
                "count": len(varianti),
                "varianti": varianti,
            }
        )
    gruppi.sort(key=lambda g: (-g["count"], -sum(v["num_fatture_reali"] for v in g["varianti"])))
    return {
        "totale_gruppi": len(gruppi),
        "gruppi": gruppi,
    }


class MergeRequest(BaseModel):
    keep_nome: str
    merge_nomi: list


@router.post("/merge")
async def merge_fornitori(payload: MergeRequest):
    """Unisce più fornitori duplicati in uno solo.
    - Trasferisce tutte le fatture dei duplicati al fornitore master
    - Elimina i record fornitori duplicati (solo se non ha P.IVA diversa)
    - Preserva la P.IVA del master
    """
    keep = (payload.keep_nome or "").strip()
    merge_nomi = [
        n.strip() for n in (payload.merge_nomi or []) if n and n.strip() and n.strip() != keep
    ]

    if not keep:
        raise HTTPException(400, "keep_nome obbligatorio")
    if not merge_nomi:
        raise HTTPException(400, "merge_nomi deve contenere almeno 1 nome diverso da keep_nome")

    def _q_nome(n):
        """Match su qualsiasi campo-nome (HACCP `nome` o ERP
        ragione_sociale/denominazione), case-insensitive."""
        rx = {"$regex": f"^\\s*{_re.escape(n)}\\s*$", "$options": "i"}
        return {"$or": [{"nome": rx}, {"ragione_sociale": rx}, {"denominazione": rx}]}

    master = await db.fornitori.find_one(_q_nome(keep), {"_id": 0})
    if not master:
        raise HTTPException(404, f"Fornitore master '{keep}' non trovato")

    piva_master = _piva_doc(master)

    fatture_aggiornate = 0
    fornitori_eliminati = 0
    dettaglio = []

    for nome_dup in merge_nomi:
        res = await db.fatture.update_many(
            {"fornitore": {"$regex": f"^\\s*{_re.escape(nome_dup)}\\s*$", "$options": "i"}},
            {"$set": {"fornitore": keep}},
        )
        fatture_aggiornate += res.modified_count

        dup = await db.fornitori.find_one(_q_nome(nome_dup), {"_id": 0})
        if dup:
            piva_dup = _piva_doc(dup)
            if piva_master and piva_dup and piva_master != piva_dup:
                dettaglio.append(
                    {
                        "nome": nome_dup,
                        "fatture_trasferite": res.modified_count,
                        "record_eliminato": False,
                        "motivo_skip": f"P.IVA diversa ({piva_dup}) — record NON eliminato per sicurezza",
                    }
                )
                continue
            update_master = {}
            if not master.get("piva") and piva_dup:
                update_master["piva"] = piva_dup
            for k in (
                "partita_iva",
                "codice_fiscale",
                "indirizzo",
                "comune",
                "cap",
                "provincia",
                "categoria",
            ):
                if not master.get(k) and dup.get(k):
                    update_master[k] = dup[k]

            # IMPORTANTE: elimina PRIMA il record duplicato, poi aggiorna il master.
            # Altrimenti l'indice unique su partita_iva genera DuplicateKeyError.
            del_res = await db.fornitori.delete_many(_q_nome(nome_dup))
            fornitori_eliminati += del_res.deleted_count

            if update_master:
                update_master["updated_at"] = datetime.now(timezone.utc).isoformat()
                try:
                    await db.fornitori.update_one(_q_nome(keep), {"$set": update_master})
                except Exception as _ue:
                    # Se l'update fallisce (conflitto), prova senza campi che potrebbero collidere
                    safe_update = {
                        k: v for k, v in update_master.items() if k not in ("partita_iva", "piva")
                    }
                    if safe_update:
                        await db.fornitori.update_one(_q_nome(keep), {"$set": safe_update})

            dettaglio.append(
                {
                    "nome": nome_dup,
                    "fatture_trasferite": res.modified_count,
                    "record_eliminato": True,
                    "campi_mergiati": list(update_master.keys()) if update_master else [],
                }
            )
        else:
            dettaglio.append(
                {
                    "nome": nome_dup,
                    "fatture_trasferite": res.modified_count,
                    "record_eliminato": False,
                    "motivo_skip": "Nessun record fornitori trovato (solo fatture riassegnate)",
                }
            )

    num_fatture_master = await db.fatture.count_documents(
        {"fornitore": {"$regex": f"^\\s*{_re.escape(keep)}\\s*$", "$options": "i"}}
    )
    await db.fornitori.update_one(
        _q_nome(keep),
        {
            "$set": {
                "num_fatture": num_fatture_master,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    return {
        "ok": True,
        "master": keep,
        "fatture_trasferite_totali": fatture_aggiornate,
        "fornitori_eliminati": fornitori_eliminati,
        "num_fatture_master_finale": num_fatture_master,
        "dettaglio": dettaglio,
    }


@router.post("/dedup-record-identici")
async def dedup_record_identici():
    """Elimina automaticamente record fornitori con nome E piva identici.
    Mantiene quello con più campi valorizzati (o quello più recente).
    """
    pipeline = [
        {
            "$group": {
                "_id": {"nome": "$nome", "piva": "$piva"},
                "count": {"$sum": 1},
                "docs": {"$push": "$$ROOT"},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
    ]
    eliminati = 0
    gruppi_processati = 0
    async for g in db.fornitori.aggregate(pipeline):
        docs = g["docs"]

        def score(d):
            return sum(1 for v in d.values() if v not in (None, "", False, 0, []))

        docs.sort(key=score, reverse=True)
        keep = docs[0]
        merged = {}
        for d in docs[1:]:
            if d.get("esclude_magazzino") and not keep.get("esclude_magazzino"):
                merged["esclude_magazzino"] = True
            if d.get("escluso") and not keep.get("escluso"):
                merged["escluso"] = True
        if merged:
            await db.fornitori.update_one({"_id": keep["_id"]}, {"$set": merged})
        for d in docs[1:]:
            await db.fornitori.delete_one({"_id": d["_id"]})
            eliminati += 1
        gruppi_processati += 1
    return {"ok": True, "gruppi_processati": gruppi_processati, "record_eliminati": eliminati}


@router.post("/auto-merge-normalizzati")
async def auto_merge_fornitori_normalizzati():
    """Fa automaticamente il merge di fornitori duplicati per P.IVA quando i nomi
    normalizzati (uppercase, senza punteggiatura, senza spazi multipli) sono identici.
    Es: "DRINK UP SRL" ≡ "Drink Up S.r.l." ≡ "DRINK UP S.R.L."
    NON unisce se i nomi rimangono diversi anche dopo normalizzazione.
    """
    import re as _re2

    def _norm(nome: str) -> str:
        n = (nome or "").upper().strip()
        n = _re2.sub(r"[.,\-_/\"']+", " ", n)
        n = _re2.sub(r"\s+", " ", n)
        n = _re2.sub(r"\bS\s*R\s*L\s*S?\b", "SRL", n)
        n = _re2.sub(r"\bS\s*P\s*A\b", "SPA", n)
        n = _re2.sub(r"\bS\s*N\s*C\b", "SNC", n)
        n = _re2.sub(r"\bS\s*A\s*S\b", "SAS", n)
        return n.strip()

    # Stessa estrazione multi-schema della lista duplicati (fix 23/07/2026):
    # P.IVA da piva/partita_iva (senza prefisso IT), nome da nome/
    # ragione_sociale/denominazione — prima metà dei duplicati era invisibile.
    tutti = await db.fornitori.find({}).to_list(5000)
    per_piva: dict = {}
    for d in tutti:
        p = _piva_doc(d)
        if p and len(p) >= 8:
            per_piva.setdefault(p, []).append(d)

    gruppi_merged = 0
    fatture_migrated = 0
    fornitori_removed = 0
    dettaglio = []

    for piva, docs in per_piva.items():
        if len(docs) < 2:
            continue
        per_norm: dict = {}
        for d in docs:
            nome = _nome_doc(d)
            if not nome:
                continue
            per_norm.setdefault(_norm(nome), []).append(d)

        for norm, lista in per_norm.items():
            if len(lista) < 2:
                continue
            fatt_counts = []
            for d in lista:
                cnt = await db.fatture.count_documents(
                    {
                        "fornitore": {
                            "$regex": f"^\\s*{_re.escape(_nome_doc(d))}\\s*$",
                            "$options": "i",
                        }
                    }
                )
                fatt_counts.append((cnt, d))
            fatt_counts.sort(key=lambda x: -x[0])
            master = fatt_counts[0][1]
            others = [d for _, d in fatt_counts[1:]]

            master_nome = _nome_doc(master)
            for o in others:
                o_nome = _nome_doc(o)
                if o_nome == master_nome:
                    await db.fornitori.delete_one({"_id": o["_id"]})
                    fornitori_removed += 1
                    continue
                upd = await db.fatture.update_many(
                    {"fornitore": {"$regex": f"^\\s*{_re.escape(o_nome)}\\s*$", "$options": "i"}},
                    {"$set": {"fornitore": master_nome}},
                )
                fatture_migrated += upd.modified_count
                await db.fornitori.delete_one({"_id": o["_id"]})
                fornitori_removed += 1
                dettaglio.append(
                    {
                        "piva": piva,
                        "master": master_nome,
                        "unito": o_nome,
                        "fatture_trasferite": upd.modified_count,
                    }
                )
            gruppi_merged += 1

    return {
        "ok": True,
        "gruppi_uniti_automaticamente": gruppi_merged,
        "fatture_riassegnate": fatture_migrated,
        "fornitori_eliminati": fornitori_removed,
        "dettaglio": dettaglio,
    }
