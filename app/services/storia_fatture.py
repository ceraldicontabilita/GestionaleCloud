"""Storia della fattura — registro cronologico che SOPRAVVIVE all'azzeramento.

Ogni fattura ha una CHIAVE STABILE (`invoice_key` = numero + P.IVA + data): la
sua storia (operazioni in ordine cronologico + stato derivato corrente) è
salvata nella collezione `storia_fatture`, SEPARATA da `invoices`.

Perché serve: i dati "dietro" la fattura (come/quando è stata pagata, in quale
liquidazione IVA è entrata, cosa è sospeso/non registrato, a cosa è collegata,
il centro di costo) NON stanno nell'XML — nascono da operazioni nel gestionale.
Azzerando `invoices` andrebbero persi. Tenendoli qui, keyed by invoice_key:

  - azzerare `invoices` non tocca la storia;
  - al reimport dello stesso XML, la fattura viene RICONOSCIUTA per invoice_key
    e il suo stato derivato viene RIAPPLICATO → la scrittura si ricrea "al
    posto giusto", senza rifare tutto a mano.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLL = "storia_fatture"

# Campi DERIVATI: non vengono dall'XML ma da operazioni nel gestionale.
# Sono ciò che si vuole preservare e ripristinare al reimport.
CAMPI_DERIVATI = (
    # Pagamento / Prima Nota
    "status", "stato_pagamento", "metodo_pagamento", "pagata", "pagato",
    "data_pagamento", "prima_nota_id", "prima_nota_cassa_id", "prima_nota_banca_id",
    "prima_nota_registrata",
    # IVA (competenza, utilizzo, liquidazione)
    "periodo_iva_attribuito", "periodo_iva_utilizzato", "iva_utilizzata",
    "stato_detrazione_iva", "liquidazione_id", "regola_iva_applicata",
    "data_ricezione", "data_trasmissione_sdi",
    # Centro di costo (classificazione)
    "centro_costo", "centro_costo_id", "centro_costo_nome", "classificazione_fonte",
    # Riconciliazioni / collegamenti
    "riconciliato", "riconciliato_quietanza", "estratto_conto_id",
    "movimento_bancario_id", "nota_credito_di", "sostituisce_fattura_id",
    # Stato "sospeso / non registrato"
    "sospesa", "note",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identita_da(invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Dati anagrafici stabili per riconoscere la fattura anche dopo il reimport."""
    return {
        "invoice_number": invoice.get("invoice_number") or invoice.get("numero_fattura"),
        "supplier_vat": invoice.get("supplier_vat") or invoice.get("cedente_piva"),
        "supplier_name": invoice.get("supplier_name") or invoice.get("cedente_denominazione"),
        "invoice_date": invoice.get("invoice_date") or invoice.get("data_fattura"),
        "total_amount": invoice.get("total_amount") or invoice.get("importo_totale"),
    }


def stato_derivato(invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae dalla fattura i soli campi derivati valorizzati."""
    out: Dict[str, Any] = {}
    for k in CAMPI_DERIVATI:
        v = invoice.get(k)
        if v not in (None, "", []):
            out[k] = v
    return out


async def registra(db, invoice_key: str, tipo: str, dettaglio: str = "",
                    patch: Optional[Dict[str, Any]] = None,
                    identita: Optional[Dict[str, Any]] = None) -> None:
    """Appende un'operazione allo storico della fattura (upsert per invoice_key)
    e aggiorna lo `stato_corrente` (merge del patch). Best-effort: non solleva."""
    if not invoice_key:
        return
    try:
        now = _now()
        doc = await db[COLL].find_one({"invoice_key": invoice_key})
        op = {"tipo": tipo, "dettaglio": dettaglio, "quando": now}
        if patch:
            op["patch"] = patch
        if not doc:
            op["seq"] = 1
            await db[COLL].insert_one({
                "invoice_key": invoice_key,
                "identita": identita or {},
                "operazioni": [op],
                "stato_corrente": dict(patch or {}),
                "created_at": now,
                "updated_at": now,
            })
        else:
            op["seq"] = len(doc.get("operazioni", [])) + 1
            stato = dict(doc.get("stato_corrente") or {})
            if patch:
                stato.update(patch)
            set_fields = {"stato_corrente": stato, "updated_at": now}
            if identita and not doc.get("identita"):
                set_fields["identita"] = identita
            await db[COLL].update_one(
                {"invoice_key": invoice_key},
                {"$push": {"operazioni": op}, "$set": set_fields},
            )
    except Exception:
        logger.exception(f"storia_fatture.registra fallita per {invoice_key}")


async def registra_snapshot(db, invoice: Dict[str, Any], tipo: str = "snapshot",
                            dettaglio: str = "Stato registrato") -> None:
    """Registra lo stato derivato CORRENTE della fattura come operazione. Usato
    prima dell'azzeramento per non perdere nulla."""
    key = invoice.get("invoice_key")
    if not key:
        return
    await registra(db, key, tipo, dettaglio,
                   patch=stato_derivato(invoice), identita=identita_da(invoice))


async def storia(db, invoice_key: str) -> Optional[Dict[str, Any]]:
    """Ritorna il documento di storia (operazioni + stato_corrente) o None."""
    if not invoice_key:
        return None
    return await db[COLL].find_one({"invoice_key": invoice_key}, {"_id": 0})


async def ripristina_stato(db, invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Se esiste una storia per questa fattura (reimport dopo azzeramento),
    riapplica lo stato derivato salvato al documento appena importato.
    Ritorna il patch applicato (vuoto se niente da ripristinare)."""
    key = invoice.get("invoice_key")
    st = await storia(db, key)
    if not st:
        # Prima volta che vediamo questa fattura: apri lo storico.
        await registra(db, key, "importata", "Prima importazione",
                       identita=identita_da(invoice))
        return {}
    patch = {k: v for k, v in (st.get("stato_corrente") or {}).items()
             if k in CAMPI_DERIVATI}
    if patch:
        try:
            await db["invoices"].update_one({"id": invoice.get("id")}, {"$set": patch})
            invoice.update(patch)
        except Exception:
            logger.exception(f"storia_fatture.ripristina_stato update fallito {key}")
    await registra(db, key, "reimportata",
                   f"Reimportata: ripristinati {len(patch)} campi derivati dallo storico",
                   identita=identita_da(invoice))
    return patch
