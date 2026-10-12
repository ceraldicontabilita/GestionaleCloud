"""Sostituzione esplicita di una delega: originali conservati, un solo debito."""

from datetime import datetime, timezone
from app.services.f24_doppioni import attivo
from app.services.f24_controllo_incrociato import righe_modello, data_versamento_modello
from app.services.f24_canonico import chiave_f24


def stessi_debiti(a, b):
    def firma(doc):
        cf = (
            (
                doc.get("codice_fiscale")
                or (doc.get("dati_generali") or {}).get("codice_fiscale")
                or ""
            )
            .strip()
            .upper()
        )
        righe = sorted(
            (
                r["sezione"] or "",
                r["codice"],
                r["mese"] or "",
                r["anno"] or "",
                r["ente"],
                r["matricola"],
                r["rateazione"],
                r["acconto"],
                r["saldo"],
                r["importo_debito_cents"],
            )
            for r in righe_modello(doc)
            if r["importo_debito_cents"] > 0
        )
        return cf, data_versamento_modello(doc), righe

    fa, fb = firma(a), firma(b)
    return bool(fa[0] and fa[1] and fa[2] and fa == fb)


def firma_obblighi(doc):
    """Identita' delle posizioni fiscali senza importi: indizio, non prova."""
    cf = str(doc.get("codice_fiscale") or (doc.get("dati_generali") or {}).get("codice_fiscale") or "").strip().upper()
    righe = tuple(sorted((r["sezione"] or "", r["codice"], r["mese"] or "", r["anno"] or "",
                          r["ente"], r["matricola"], r["rateazione"], r["acconto"], r["saldo"])
                         for r in righe_modello(doc) if r["importo_debito_cents"] > 0))
    return cf, data_versamento_modello(doc), righe


def stessi_obblighi(a, b):
    fa, fb = firma_obblighi(a), firma_obblighi(b)
    return bool(fa[0] and fa[1] and fa[2] and fa == fb)


def ha_pagamento(doc):
    return bool(doc.get("movimento_bancario_id") or doc.get("allocazioni_banca") or
                doc.get("quietanza_id") or doc.get("quietanza_ids") or doc.get("pagato") or
                doc.get("data_pagamento_effettivo") or str(doc.get("stato_pagamento") or "").upper() == "PAGATO")


async def sostituisci_versione(db, precedente_id, vigente_id, *, actor,
                              conferma_importi_discordanti=False, motivo=None):
    if precedente_id == vigente_id:
        raise ValueError("La versione sostitutiva deve essere diversa")
    async with db.transaction():
        precedente = await db["f24_unificato"].find_one({"id": precedente_id})
        vigente = await db["f24_unificato"].find_one({"id": vigente_id})
        if not precedente or not vigente or not attivo(vigente):
            raise ValueError("Versioni F24 non disponibili")
        if precedente.get("sostituito_da_f24_id") == vigente_id:
            return {"success": True, "gia_sostituito": True}
        if conferma_importi_discordanti and not (motivo and motivo.strip()):
            raise ValueError("Indicare il motivo della scelta fra versioni discordanti")
        stessa_delega = (stessi_obblighi(precedente, vigente) if conferma_importi_discordanti
                         else stessi_debiti(precedente, vigente))
        if not attivo(precedente) or not stessa_delega:
            raise ValueError(
                "Contribuente, scadenza e righe a debito devono coincidere; non basta il mese"
            )
        if ha_pagamento(precedente):
            raise ValueError(
                "La versione precedente ha evidenze di pagamento: occorre verificare i collegamenti"
            )
        now = datetime.now(timezone.utc).isoformat()
        await db["f24_unificato"].update_one(
            {"id": precedente_id},
            {
                "$set": {
                    "status": "eliminato",
                    "entity_status": "deleted",
                    "stato_prima_della_quarantena": precedente.get("status"),
                    "motivo_quarantena": "versione_sostituita_confermata",
                    "sostituito": True,
                    "sostituito_da_f24_id": vigente_id,
                    "quarantena_il": now,
                    "confermato_da": actor,
                    "decisione_versione": {
                        "tipo": "scelta_utente_importi_discordanti" if conferma_importi_discordanti else "stessi_debiti",
                        "motivo": motivo or "Stessi debiti, versione sostitutiva confermata",
                        "actor": actor, "at": now, "vigente_id": vigente_id,
                    },
                }
            },
        )
        key = chiave_f24(vigente)
        await db["f24_unificato"].update_one(
            {"id": vigente_id},
            {
                "$set": {
                    "sostituisce_f24_id": precedente_id,
                    "f24_dedup_key": key,
                    "idempotency_key": f"f24:{key}",
                    "updated_at": now,
                }
            },
        )
        # Annullamento dell'obbligo duplicato, mai un pagamento fittizio.
        await db["partite_aperte"].update_many(
            {
                "documento_id": precedente_id,
                "tipo": "f24",
                "stato": {"$in": ["aperta", "da_verificare"]},
            },
            {
                "$set": {
                    "stato": "annullata",
                    "entity_status": "deleted",
                    "sostituito_da_f24_id": vigente_id,
                    "motivo_annullamento": "versione_f24_sostituita",
                    "updated_at": now,
                }
            },
        )
        await db["alerts"].update_many(
            {"entita_id": precedente_id},
            {
                "$set": {
                    "stato": "risolto",
                    "risolto": True,
                    "resolved_at": now,
                    "resolved_by": "versione_f24_sostituita",
                    "sostituito_da_f24_id": vigente_id,
                }
            },
        )
        await db["f24_riconciliazione_alerts"].update_many(
            {"f24_id": precedente_id},
            {
                "$set": {
                    "status": "resolved",
                    "resolved_at": now,
                    "resolved_by": "versione_f24_sostituita",
                }
            },
        )
    return {"success": True, "precedente_id": precedente_id, "vigente_id": vigente_id}
