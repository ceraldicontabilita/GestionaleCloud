"""Divide un Libro Unico multi-dipendente nei singoli cedolini e li registra.

Il consulente manda un unico PDF con tutti i dipendenti del mese: pagine di
presenze e pagine di elementi retributivi, una coppia per persona, riconosciute
dal codice fiscale che si ripete. Questo modulo raggruppa le pagine per CF,
ricostruisce un mini-PDF per ciascun dipendente e lo passa al parser gia'
verificato (`busta_paga_multi_template`), lo stesso usato per l'archivio
storico: stessi campi, stesso comportamento su netto e livello.

Le buste da amministratore (Ceraldi Valerio/Vincenzo/Antonietta) hanno solo la
pagina presenze, senza elementi retributivi: qui vengono segnalate e saltate,
non e' questo il documento da cui prendere il loro netto (arrivano gia'
riconciliate dalla cartella Drive "Cedolini Paga/Elaborate").
"""
import base64
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

from app.hr.database import Collections
from app.hr.parsers.busta_paga_multi_template import parse_busta_paga_from_bytes

_CF = re.compile(r"[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]")


def _pagine_per_dipendente(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """Raggruppa le pagine consecutive che condividono lo stesso codice fiscale."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    gruppi: List[Dict[str, Any]] = []
    corrente: Optional[str] = None
    for i in range(doc.page_count):
        testo = doc[i].get_text()
        m = _CF.search(testo)
        cf = m.group(0) if m else None
        if cf and cf != corrente:
            gruppi.append({"codice_fiscale": cf, "pagine": [i]})
            corrente = cf
        elif cf == corrente and gruppi:
            gruppi[-1]["pagine"].append(i)
        # pagine senza CF riconoscibile restano nel gruppo aperto (es. intestazioni)
        elif gruppi:
            gruppi[-1]["pagine"].append(i)

    for g in gruppi:
        sotto = fitz.open()
        sotto.insert_pdf(doc, from_page=g["pagine"][0], to_page=g["pagine"][-1])
        g["pdf_bytes"] = sotto.tobytes()
        sotto.close()
    doc.close()
    return gruppi


async def dividi_e_registra(db, pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """Divide il bundle, aggancia ogni pezzo al dipendente e salva il cedolino.

    Non duplica: se per quel dipendente esiste gia' un cedolino ordinario per lo
    stesso anno/mese, lo salta. I dipendenti senza pagina retributiva (solo
    presenze — gli amministratori) vengono segnalati, non registrati da qui.
    """
    gruppi = _pagine_per_dipendente(pdf_bytes)

    dipendenti = await db[Collections.EMPLOYEES].find(
        {}, {"_id": 0}).to_list(500)
    per_cf = {(d.get("codice_fiscale") or "").upper(): d for d in dipendenti if d.get("codice_fiscale")}

    esistenti = set()
    async for c in db[Collections.PAYSLIPS].find({}, {"_id": 0, "pdf_data": 0}):
        esistenti.add((c.get("dipendente_id"), c.get("anno"), c.get("mese"),
                       c.get("tipo_cedolino") or "ordinario"))

    adesso = datetime.now(timezone.utc).isoformat()
    inseriti, saltati, senza_paga, senza_anagrafica = [], [], [], []

    for g in gruppi:
        cf = g["codice_fiscale"]
        try:
            r = parse_busta_paga_from_bytes(g["pdf_bytes"])
        except Exception as e:
            senza_paga.append({"codice_fiscale": cf, "errore": str(e)})
            continue

        t = r.get("totali") or {}
        p = r.get("periodo") or {}
        d = r.get("dipendente") or {}
        if r.get("tipo_documento") == "foglio_presenze" or t.get("netto") is None:
            # Solo presenze, senza pagina di elementi retributivi (amministratori):
            # non c'e' un netto da registrare qui.
            senza_paga.append({"codice_fiscale": cf, "nome": d.get("nome_completo")})
            continue

        dip = per_cf.get(cf)
        if not dip:
            senza_anagrafica.append({"codice_fiscale": cf, "nome": d.get("nome_completo")})
            continue

        anno, mese = p.get("anno"), p.get("mese")
        tipo = r.get("tipo_cedolino") or "ordinario"
        if (dip["id"], anno, mese, tipo) in esistenti:
            saltati.append({"dipendente": dip["nome_completo"], "competenza": f"{anno}-{mese}"})
            continue

        doc = {
            "id": str(uuid.uuid4()),
            "dipendente_id": dip["id"],
            "dipendente_nome": dip.get("nome_completo"),
            "nome_dipendente": dip.get("nome_completo"),
            "codice_fiscale": cf,
            "mese": mese, "anno": anno, "competenza": f"{anno}-{mese:02d}" if anno and mese else None,
            "tipo_cedolino": tipo,
            "filename": f"{filename} (pagine {g['pagine'][0]+1}-{g['pagine'][-1]+1})" if filename else None,
            "pdf_data": base64.b64encode(g["pdf_bytes"]).decode("ascii"),
            "netto": t.get("netto"), "lordo": t.get("lordo"),
            "trattenute": t.get("trattenute"), "competenze": t.get("competenze"),
            "netto_ricostruito": t.get("netto_ricostruito"),
            "livello": str(d["livello"]) if d.get("livello") else None,
            "retribuzione": r.get("retribuzione") or {},
            "fonte": "libro_unico_bundle",
            "created_at": adesso,
        }
        doc = {k: v for k, v in doc.items() if v not in (None, {}, "")}
        await db[Collections.PAYSLIPS].insert_one(doc)
        esistenti.add((dip["id"], anno, mese, tipo))
        inseriti.append({"dipendente": dip["nome_completo"], "competenza": f"{anno}-{mese}",
                         "netto": t.get("netto")})

    return {
        "pagine_totali": sum(len(g["pagine"]) for g in gruppi),
        "dipendenti_nel_documento": len(gruppi),
        "inseriti": inseriti, "gia_presenti": saltati,
        "senza_pagina_retributiva": senza_paga,
        "senza_anagrafica": senza_anagrafica,
    }
