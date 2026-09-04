"""Allinea la vista salari al registro canonico dei cedolini.

Il cedolino parsato (e, quando disponibile, il suo PDF) e' la fonte dei dati
di competenza. La prima nota conserva invece lo stato dei pagamenti: durante
il riallineamento quei campi non vengono mai cancellati o ricreati.
"""

from __future__ import annotations

import base64
import calendar
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import fitz

from app.parsers.busta_paga_multi_template import _detect_tipo_cedolino
from app.services.salari_periodo import filtro_periodo_prima_nota

logger = logging.getLogger(__name__)

TIPI_CEDOLINO = {
    "mensile", "tredicesima", "quattordicesima", "acconto",
    "sospensione", "solo_trattenute",
}


def _tipo_normalizzato(value: Any) -> str:
    tipo = str(value or "mensile").strip().lower()
    return tipo if tipo in TIPI_CEDOLINO else "mensile"


def _tipo_dal_pdf(pdf_data: Any) -> Optional[str]:
    """Legge soltanto le prime pagine, senza conservare testo estratto."""
    if not pdf_data:
        return None
    try:
        raw = base64.b64decode(pdf_data, validate=False)
        document = fitz.open(stream=raw, filetype="pdf")
        try:
            testo = "\n".join(
                document[index].get_text("text")
                for index in range(min(len(document), 3))
            )
        finally:
            document.close()
        return _detect_tipo_cedolino(testo)
    except Exception:
        logger.debug("Tipo cedolino non rilevabile dal PDF", exc_info=True)
        return None


def _chiave(cedolino: Dict[str, Any], tipo: str) -> Optional[Tuple[str, int, int, str]]:
    cf = str(cedolino.get("codice_fiscale") or "").strip().upper()
    try:
        mese = int(cedolino.get("mese"))
        anno = int(cedolino.get("anno"))
    except (TypeError, ValueError):
        return None
    if not cf or not 1 <= mese <= 12 or anno < 2018:
        return None
    return cf, anno, mese, tipo


async def sincronizza_prima_nota_da_cedolini(
    db,
    *,
    anno_minimo: int = 2018,
) -> Dict[str, int]:
    """Crea le righe mancanti e corregge quelle collegate al PDF.

    L'operazione e' idempotente. I documenti storici restano in ``cedolini``;
    la prima nota viene creata soltanto dal periodo contabile operativo
    centralizzato in ``salari_periodo``. Nessuna riga di pagamento viene
    eliminata da questa funzione.
    """
    periodo_contabile = filtro_periodo_prima_nota()
    cedolini = await db["cedolini"].find(
        periodo_contabile,
        {
            "_id": 0, "id": 1, "dipendente_id": 1,
            "nome_dipendente": 1, "codice_fiscale": 1,
            "mese": 1, "anno": 1, "tipo_cedolino": 1,
            "netto": 1, "netto_mese": 1, "pdf_disponibile": 1,
            "updated_at": 1,
        },
    ).to_list(20000)

    # Un solo documento autorevole per identita' logica. In caso di reimport
    # preferiamo quello che contiene il PDF e poi il piu' recente.
    canonici: Dict[Tuple[str, int, int, str], Dict[str, Any]] = {}
    tipi_corretti: Dict[str, str] = {}
    ignorati = 0
    for cedolino in cedolini:
        tipo_archiviato = _tipo_normalizzato(cedolino.get("tipo_cedolino"))
        # Il base64 puo' essere voluminoso: viene caricato un documento alla
        # volta e non rimane nella lista in memoria.
        pdf_doc = None
        if cedolino.get("id"):
            pdf_doc = await db["cedolini"].find_one(
                {"id": cedolino["id"]}, {"_id": 0, "pdf_data": 1}
            )
        tipo_pdf = _tipo_dal_pdf((pdf_doc or {}).get("pdf_data"))
        cedolino["_pdf_presente"] = bool((pdf_doc or {}).get("pdf_data"))
        tipo = tipo_pdf or tipo_archiviato
        key = _chiave(cedolino, tipo)
        if not key:
            ignorati += 1
            continue
        if cedolino.get("id") and tipo != tipo_archiviato:
            tipi_corretti[str(cedolino["id"])] = tipo
        precedente = canonici.get(key)
        rank = (bool(cedolino.get("_pdf_presente")), str(cedolino.get("updated_at") or ""))
        old_rank = (
            bool((precedente or {}).get("_pdf_presente")),
            str((precedente or {}).get("updated_at") or ""),
        )
        if precedente is None or rank > old_rank:
            canonici[key] = cedolino

    now = datetime.now(timezone.utc).isoformat()
    for cedolino_id, tipo in tipi_corretti.items():
        await db["cedolini"].update_one(
            {"id": cedolino_id},
            {"$set": {
                "tipo_cedolino": tipo,
                "tipo_cedolino_riletto_da_pdf": True,
                "updated_at": now,
            }},
        )

    # Mai far coincidere una nuova busta con una copia gia' marcata duplicata
    # dalla bonifica (PR 14, audit 03/09/2026 §5).
    from app.services.scritture_contabili import FILTRO_MOVIMENTO_ATTIVO
    from app.services.prima_nota_salari_chiave import (
        carica_indice_dipendenti,
        risolvi_codice_fiscale,
    )

    pn_rows = await db["prima_nota_salari"].find(
        {**periodo_contabile, **FILTRO_MOVIMENTO_ATTIVO}, {"_id": 0}
    ).to_list(20000)
    per_cedolino = {
        str(row.get("cedolino_id")): row
        for row in pn_rows if row.get("cedolino_id")
    }
    # PR 14 (audit 03/09/2026 §5): il canale import Excel/indice cedolini
    # Drive non scrive il codice fiscale sulla riga. Senza risolverlo dal
    # nome (anagrafica, match univoco), questo sync non riconosce la busta
    # gia' creata da quel canale e ne crea una seconda con lo stesso netto —
    # causa verificata dei doppioni di Ceraldi Valerio/Vincenzo 05/2026.
    indice_dipendenti = await carica_indice_dipendenti(db)
    per_chiave: Dict[Tuple[str, int, int, str], Dict[str, Any]] = {}
    for row in pn_rows:
        cf_risolto = str(row.get("codice_fiscale") or "").strip().upper() or (
            risolvi_codice_fiscale(row, indice_dipendenti)
        )
        row_per_chiave = {**row, "codice_fiscale": cf_risolto} if cf_risolto else row
        key = _chiave(row_per_chiave, _tipo_normalizzato(row.get("tipo_cedolino")))
        if key and key not in per_chiave:
            per_chiave[key] = row

    creati = aggiornati = invariati = 0
    usati = set()
    for key, cedolino in canonici.items():
        cf, anno, mese, tipo = key
        cedolino_id = str(cedolino.get("id") or "")
        salario = per_cedolino.get(cedolino_id) if cedolino_id else None
        if salario is None:
            candidato = per_chiave.get(key)
            if candidato and candidato.get("id") not in usati:
                salario = candidato
        nome = str(cedolino.get("nome_dipendente") or "").strip()
        netto = float(cedolino.get("netto_mese") or cedolino.get("netto") or 0)
        if not nome or netto <= 0:
            ignorati += 1
            continue

        ultimo_giorno = calendar.monthrange(anno, mese)[1]
        autorevoli = {
            "cedolino_id": cedolino.get("id"),
            "dipendente_id": cedolino.get("dipendente_id"),
            "dipendente": nome.upper(),
            "dipendente_nome": nome,
            "codice_fiscale": cf,
            "data": f"{anno:04d}-{mese:02d}-{ultimo_giorno:02d}",
            "mese": mese,
            "anno": anno,
            "importo_busta": netto,
            "tipo": "stipendio",
            "tipo_cedolino": tipo,
            "descrizione": f"Stipendio {nome} - {mese:02d}/{anno}",
            "updated_at": now,
        }
        if salario:
            usati.add(salario.get("id"))
            modificato = any(salario.get(k) != v for k, v in autorevoli.items())
            if modificato:
                await db["prima_nota_salari"].update_one(
                    {"id": salario.get("id")}, {"$set": autorevoli}
                )
                aggiornati += 1
            else:
                invariati += 1
            continue

        pn_id = str(uuid.uuid4())
        nuovo = {
            "id": pn_id,
            **autorevoli,
            "importo_bonifico": 0,
            "saldo": -netto,
            "progressivo": 0,
            "riconciliato": False,
            "source": "cedolino_sync",
            "created_at": now,
        }
        await db["prima_nota_salari"].insert_one(dict(nuovo))
        per_cedolino[cedolino_id] = nuovo
        per_chiave[key] = nuovo
        usati.add(pn_id)
        creati += 1

    return {
        "cedolini_esaminati": len(cedolini),
        "identita_canoniche": len(canonici),
        "tipi_corretti_da_pdf": len(tipi_corretti),
        "prima_nota_creata": creati,
        "prima_nota_aggiornata": aggiornati,
        "prima_nota_invariata": invariati,
        "ignorati": ignorati,
    }
