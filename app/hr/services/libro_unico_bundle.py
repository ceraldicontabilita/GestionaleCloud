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
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import fitz  # PyMuPDF

from app.hr.database import Collections


async def dividi_e_registra(db, pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """Divide il bundle, aggancia ogni pezzo al dipendente e salva il cedolino.

    Non duplica: se per quel dipendente esiste gia' un cedolino ordinario per lo
    stesso anno/mese, lo salta. I dipendenti senza pagina retributiva (solo
    presenze — gli amministratori) vengono segnalati, non registrati da qui.
    """
    # Usa il motore canonico: distingue piu' buste dello stesso dipendente,
    # conserva le continuazioni multipagina e legge il netto dalla sua cella.
    # Il vecchio raggruppamento solo per CF fondeva, per esempio, una 14a con
    # il cedolino ordinario o spezzava la seconda pagina con il netto.
    from app.services.cedolini_motore import leggi_pdf

    lettura = leggi_pdf(pdf_bytes)
    buste = lettura.get("buste") or []
    presenze = lettura.get("presenze") or []

    dipendenti = await db[Collections.EMPLOYEES].find(
        {}, {"_id": 0}).to_list(500)
    per_cf = {(d.get("codice_fiscale") or "").upper(): d for d in dipendenti if d.get("codice_fiscale")}

    esistenti = set()
    async for c in db[Collections.PAYSLIPS].find({}, {"_id": 0, "pdf_data": 0}):
        esistenti.add((c.get("dipendente_id"), c.get("anno"), c.get("mese"),
                       c.get("tipo_cedolino") or "ordinario"))

    adesso = datetime.now(timezone.utc).isoformat()
    inseriti, saltati, senza_paga, senza_anagrafica = [], [], [], []

    for busta in buste:
        cf = str(busta.get("codice_fiscale") or "").upper()
        if not cf:
            senza_paga.append({"codice_fiscale": None, "errore": "codice fiscale non letto"})
            continue
        if busta.get("netto") is None:
            senza_paga.append({
                "codice_fiscale": cf,
                "nome": busta.get("nome_dipendente"),
                "errore": "netto non leggibile",
            })
            continue

        dip = per_cf.get(cf)
        if not dip:
            senza_anagrafica.append({"codice_fiscale": cf, "nome": busta.get("nome_dipendente")})
            continue

        anno, mese = busta.get("anno"), busta.get("mese")
        tipo_gestionale = str(busta.get("tipo_cedolino") or "mensile").strip().lower()
        tipo = "ordinario" if tipo_gestionale in ("", "mensile") else tipo_gestionale
        if (dip["id"], anno, mese, tipo) in esistenti:
            saltati.append({"dipendente": dip["nome_completo"], "competenza": f"{anno}-{mese}"})
            continue

        pagina_da = int(busta.get("source_page_start") or 1)
        pagina_a = int(busta.get("source_page_end") or pagina_da)

        doc = {
            "id": str(uuid.uuid4()),
            "dipendente_id": dip["id"],
            "dipendente_nome": dip.get("nome_completo"),
            "nome_dipendente": dip.get("nome_completo"),
            "codice_fiscale": cf,
            "mese": mese, "anno": anno, "competenza": f"{anno}-{mese:02d}" if anno and mese else None,
            "tipo_cedolino": tipo,
            "filename": f"{filename} (pagine {pagina_da}-{pagina_a})" if filename else None,
            "pdf_data": busta.get("_pdf_data"),
            "netto": busta.get("netto"), "lordo": busta.get("lordo"),
            "trattenute": busta.get("totale_trattenute"),
            "competenze": busta.get("lordo"),
            "stato_netto": busta.get("stato_netto"),
            "livello": str(busta["livello"]) if busta.get("livello") else None,
            "retribuzione": busta.get("retribuzione") or {},
            "dati_chiave": busta.get("dati_chiave") or {},
            "source_page_start": pagina_da,
            "source_page_end": pagina_a,
            "source_document_pages": busta.get("source_document_pages"),
            "fonte": "libro_unico_bundle",
            "created_at": adesso,
        }
        doc = {k: v for k, v in doc.items() if v not in (None, {}, "")}
        await db[Collections.PAYSLIPS].insert_one(doc)
        esistenti.add((dip["id"], anno, mese, tipo))
        inseriti.append({"dipendente": dip["nome_completo"], "competenza": f"{anno}-{mese}",
                         "tipo_cedolino": tipo, "netto": busta.get("netto")})

    cf_con_busta = {str(b.get("codice_fiscale") or "").upper() for b in buste}
    presenze_senza_busta = {}
    for presenza in presenze:
        cf = str(presenza.get("codice_fiscale") or "").upper()
        if cf and cf not in cf_con_busta:
            presenze_senza_busta.setdefault(cf, {
                "codice_fiscale": cf,
                "nome": presenza.get("nome_dipendente"),
            })
    senza_paga.extend(presenze_senza_busta.values())

    documento = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pagine_totali = len(documento)
    finally:
        documento.close()
    cf_documento = cf_con_busta | {str(p.get("codice_fiscale") or "").upper() for p in presenze if p.get("codice_fiscale")}

    return {
        "pagine_totali": pagine_totali,
        "dipendenti_nel_documento": len(cf_documento),
        "inseriti": inseriti, "gia_presenti": saltati,
        "senza_pagina_retributiva": senza_paga,
        "senza_anagrafica": senza_anagrafica,
    }
