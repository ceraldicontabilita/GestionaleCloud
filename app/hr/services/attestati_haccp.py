"""Attestati di formazione alimentarista (HACCP) dei dipendenti.

Un solo servizio per HR e Lotti. L'attestato è un documento del dipendente
(`documenti_cloud`, tipo ``attestato_haccp``): lo vede lui nel portale e
l'amministratore da HR e da Lotti.

Un PDF con più attestati si divide pagina per pagina e **ogni pagina si
riconosce dal contenuto** (nome e cognome scritti nell'attestato, data del
corso, ore), mai dal nome del file. L'abbinamento al dipendente richiede una
sola persona compatibile: con zero o più candidati la pagina resta da
assegnare e la sceglie il titolare. Stesso contenuto (SHA-256) o stesso
dipendente con la stessa data di corso = già presente, mai un secondo
documento. Nessun dato inventato: numero attestato e scadenza non si leggono
dall'OCR (il numero è scritto a mano) e restano vuoti.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.hr.database import Database

logger = logging.getLogger(__name__)

COLL = "documenti_cloud"
COLL_DIPENDENTI = "dipendenti"
TIPO = "attestato_haccp"
CATEGORIA = "ATTESTATO_HACCP"
LABEL = "Attestato formazione alimentarista (HACCP)"
ENTE = "T. & C. Company S.r.l."
MAX_PAGINE = 60
MAX_BYTES = 12 * 1024 * 1024


def _solo_lettere(testo: str) -> str:
    n = unicodedata.normalize("NFKD", str(testo or ""))
    n = "".join(c for c in n if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", n.lower())


def _compatto(testo: str) -> str:
    """Testo senza spazi e senza accenti: l'OCR incolla le parole."""
    n = unicodedata.normalize("NFKD", str(testo or ""))
    n = "".join(c for c in n if not unicodedata.combining(c))
    return re.sub(r"\s+", "", n.lower())


def dividi_pdf(contenuto: bytes) -> List[bytes]:
    """Una pagina = un PDF."""
    import fitz

    pagine: List[bytes] = []
    with fitz.open(stream=contenuto, filetype="pdf") as documento:
        if documento.page_count > MAX_PAGINE:
            raise ValueError(f"Il PDF ha {documento.page_count} pagine: il massimo è {MAX_PAGINE}")
        for indice in range(documento.page_count):
            singola = fitz.open()
            singola.insert_pdf(documento, from_page=indice, to_page=indice)
            pagine.append(singola.tobytes(garbage=3, deflate=True))
            singola.close()
    return pagine


def testo_pagine(pagine: List[bytes]) -> List[str]:
    """Testo di ogni pagina: livello testo se c'è, altrimenti OCR (un motore per volta)."""
    import fitz

    testi: List[str] = []
    da_leggere: List[int] = []
    for i, pagina in enumerate(pagine):
        with fitz.open(stream=pagina, filetype="pdf") as d:
            t = d[0].get_text() or ""
        testi.append(t)
        if len(_compatto(t)) < 40:
            da_leggere.append(i)
    if da_leggere:
        import numpy as np
        from PIL import Image

        from app.services.ocr_locale import motore

        with motore() as engine:
            for i in da_leggere:
                with fitz.open(stream=pagine[i], filetype="pdf") as d:
                    pixmap = d[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                immagine = np.array(Image.open(io.BytesIO(pixmap.tobytes("png"))))
                risultato, _ = engine(immagine)
                righe = sorted(
                    (sum(p[1] for p in riquadro) / 4, min(p[0] for p in riquadro), str(testo))
                    for riquadro, testo, _c in (risultato or [])
                    if str(testo).strip()
                )
                # righe per altezza (tolleranza 12 px a 2x), poi da sinistra a destra
                gruppi: List[List[tuple]] = []
                for riga in righe:
                    if gruppi and abs(gruppi[-1][0][0] - riga[0]) <= 12:
                        gruppi[-1].append(riga)
                    else:
                        gruppi.append([riga])
                testi[i] = "\n".join(" ".join(t for _y, _x, t in sorted(g, key=lambda v: v[1])) for g in gruppi)
    return testi


def leggi_attestato(testo: str) -> Dict[str, Any]:
    """Nome, cognome, data del corso e ore dal contenuto della pagina."""
    esito: Dict[str, Any] = {"nome": None, "cognome": None, "data_attestato": None, "ore_corso": None}
    compatto = _compatto(testo)
    m = re.search(r"nome(.{2,40}?)cognome(.{2,40}?)nat[a-z]{1,4}\d{1,2}/\d{1,2}/\d{4}", compatto)
    if m:
        esito["nome"], esito["cognome"] = m.group(1), m.group(2)
    m = re.search(r"luogoedata[^\n]*?(\d{1,2})/(\d{1,2})/(\d{4})", compatto)
    if m:
        g, me, a = (int(x) for x in m.groups())
        try:
            esito["data_attestato"] = datetime(a, me, g).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"duratadiore(\d{1,3})", compatto)
    if m:
        esito["ore_corso"] = int(m.group(1))
    return esito


def abbina_dipendente(letto: Dict[str, Any], dipendenti: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Un solo dipendente compatibile per nome E cognome, altrimenti candidati."""
    nome, cognome = _solo_lettere(letto.get("nome")), _solo_lettere(letto.get("cognome"))
    if len(nome) < 3 or len(cognome) < 3:
        return {"dipendente": None, "motivo": "nome_non_letto", "candidati": []}
    candidati = []
    for d in dipendenti:
        n, c = _solo_lettere(d.get("nome")), _solo_lettere(d.get("cognome"))
        if not n or not c:
            continue
        if (n.startswith(nome) or nome.startswith(n)) and (c.startswith(cognome) or cognome.startswith(c)):
            candidati.append(d)
    if len(candidati) == 1:
        return {"dipendente": candidati[0], "motivo": "abbinato", "candidati": []}
    return {
        "dipendente": None,
        "motivo": "nessun_dipendente" if not candidati else "dipendenti_ambigui",
        "candidati": candidati,
    }


async def elenco_dipendenti() -> List[Dict[str, Any]]:
    db = Database.get_db()
    righe = await db[COLL_DIPENDENTI].find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "stato": 1}).to_list(None)
    return [r for r in righe if r.get("id")]


def _nome_file(letto: Dict[str, Any], dip: Dict[str, Any]) -> str:
    cognome = re.sub(r"[^A-Za-z0-9]+", "_", str(dip.get("cognome") or "")).strip("_")
    nome = re.sub(r"[^A-Za-z0-9]+", "_", str(dip.get("nome") or "")).strip("_")
    return f"Attestato_alimentarista_{cognome}_{nome}_{letto.get('data_attestato') or 'senza_data'}.pdf"


def _titolo(letto: Dict[str, Any]) -> str:
    ore = f" (corso di {letto['ore_corso']} ore)" if letto.get("ore_corso") else ""
    return f"Attestato formazione alimentarista{ore}"


async def salva_attestato(
    dipendente_id: str, contenuto: bytes, letto: Dict[str, Any], *, nome_file: Optional[str] = None,
    mime: str = "application/pdf", fonte: str = "import_attestati_haccp", pagina: Optional[int] = None,
) -> Dict[str, Any]:
    """Allega l'attestato al dipendente. Idempotente: stesso SHA-256, o stessa data di corso."""
    db = Database.get_db()
    sha = hashlib.sha256(contenuto).hexdigest()
    esistenti = await db[COLL].find(
        {"dipendente_id": dipendente_id, "categoria": CATEGORIA}, {"_id": 0, "file_data": 0}
    ).to_list(200)
    for e in esistenti:
        if e.get("hash") == sha or (letto.get("data_attestato") and e.get("data_attestato") == letto["data_attestato"]):
            return {"esito": "gia_presente", "id": e.get("id")}
    dip = await db[COLL_DIPENDENTI].find_one({"id": dipendente_id}, {"_id": 0, "nome": 1, "cognome": 1, "nome_completo": 1})
    if not dip:
        return {"esito": "dipendente_non_trovato", "id": None}
    adesso = datetime.now(timezone.utc).isoformat()
    nome_file = nome_file or _nome_file(letto, dip)
    # Un solo documento, due viste: la cartella «Documenti» di HR (categoria, titolo,
    # filename, hash) e il portale del dipendente (tipo, label, nome_file, mime, caricato_*).
    doc = {
        "id": str(uuid.uuid4()),
        "dipendente_id": dipendente_id,
        "dipendente_nome": dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip(),
        "tipo": TIPO,
        "categoria": CATEGORIA,
        "label": LABEL,
        "titolo": _titolo(letto),
        "nome_file": nome_file,
        "filename": nome_file,
        "mime": mime,
        "dimensione": len(contenuto),
        "file_size": len(contenuto),
        "hash": sha,
        "file_data": base64.b64encode(contenuto).decode(),
        "caricato_da": "azienda",
        "caricato_il": adesso,
        "data_caricamento": adesso,
        "assegnato": True,
        "origine": fonte,
        "data_attestato": letto.get("data_attestato"),
        "ore_corso": letto.get("ore_corso"),
        "ente": ENTE,
        "pagina_origine": pagina,
    }
    await db[COLL].insert_one(doc)
    return {"esito": "nuovo", "id": doc["id"]}


async def importa_pdf(
    contenuto: bytes, *, dry_run: bool = True, assegnazioni: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Divide il PDF, legge ogni pagina e (se ``dry_run`` è falso) la allega al dipendente.

    ``assegnazioni``: {pagina (1-based, testo): id dipendente} per le pagine che il
    titolare ha scelto a mano.
    """
    import asyncio

    if not contenuto:
        raise ValueError("File vuoto")
    if len(contenuto) > 40 * 1024 * 1024:
        raise ValueError("File troppo grande (max 40 MB)")
    pagine = await asyncio.to_thread(dividi_pdf, contenuto)
    testi = await asyncio.to_thread(testo_pagine, pagine)
    dipendenti = await elenco_dipendenti()
    per_id = {d["id"]: d for d in dipendenti}
    righe: List[Dict[str, Any]] = []
    riepilogo = {"pagine": len(pagine), "nuovi": 0, "gia_presenti": 0, "da_assegnare": 0}
    for numero, (pdf, testo) in enumerate(zip(pagine, testi), start=1):
        letto = leggi_attestato(testo)
        scelto = (assegnazioni or {}).get(str(numero))
        if scelto:
            dip = per_id.get(scelto)
            abb = {"dipendente": dip, "motivo": "scelto_dal_titolare" if dip else "dipendente_non_trovato", "candidati": []}
        else:
            abb = abbina_dipendente(letto, dipendenti)
        dip = abb["dipendente"]
        riga = {
            "pagina": numero,
            "letto": {"nome": letto["nome"], "cognome": letto["cognome"],
                      "data_attestato": letto["data_attestato"], "ore_corso": letto["ore_corso"]},
            "dipendente_id": dip["id"] if dip else None,
            "dipendente": f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip() if dip else None,
            "stato_dipendente": dip.get("stato") if dip else None,
            "motivo": abb["motivo"],
            "candidati": [{"id": c["id"], "nome": f"{c.get('cognome', '')} {c.get('nome', '')}".strip()} for c in abb["candidati"]],
            "esito": None,
        }
        if not dip:
            riga["esito"] = "da_assegnare"
            riepilogo["da_assegnare"] += 1
        else:
            sha = hashlib.sha256(pdf).hexdigest()
            if dry_run:
                gia = await Database.get_db()[COLL].find(
                    {"dipendente_id": dip["id"], "categoria": CATEGORIA}, {"_id": 0, "file_data": 0}).to_list(200)
                presente = any(e.get("hash") == sha or (letto["data_attestato"] and e.get("data_attestato") == letto["data_attestato"]) for e in gia)
                riga["esito"] = "gia_presente" if presente else "nuovo"
            else:
                riga["esito"] = (await salva_attestato(dip["id"], pdf, letto, pagina=numero))["esito"]
            riepilogo["gia_presenti" if riga["esito"] == "gia_presente" else "nuovi"] += 1
        righe.append(riga)
    logger.info("[attestati_haccp] dry_run=%s pagine=%d nuovi=%d gia=%d da_assegnare=%d",
                dry_run, riepilogo["pagine"], riepilogo["nuovi"], riepilogo["gia_presenti"], riepilogo["da_assegnare"])
    return {"dry_run": dry_run, "riepilogo": riepilogo, "righe": righe}


async def lista_per_dipendente(dipendente_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Metadati degli attestati (mai il file), per dipendente."""
    filtro: Dict[str, Any] = {"categoria": CATEGORIA}
    if dipendente_id:
        filtro["dipendente_id"] = dipendente_id
    docs = await Database.get_db()[COLL].find(filtro, {"_id": 0, "file_data": 0}).to_list(None)
    per: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs:
        per.setdefault(d.get("dipendente_id"), []).append({
            k: d.get(k) for k in ("id", "titolo", "nome_file", "data_attestato", "ore_corso", "caricato_il", "dimensione")
        })
    return per


async def leggi_file(doc_id: str) -> Optional[Dict[str, Any]]:
    doc = await Database.get_db()[COLL].find_one({"id": doc_id, "categoria": CATEGORIA}, {"_id": 0})
    if not doc or not doc.get("file_data"):
        return None
    return {"nome_file": doc.get("nome_file") or "attestato.pdf", "mime": doc.get("mime") or "application/pdf",
            "contenuto": base64.b64decode(doc["file_data"])}
