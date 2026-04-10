"""
Router Schede Tecniche Prodotti
- Legge le fatture XML per estrarre prodotti del fornitore
- Cerca sul web le schede tecniche ufficiali (PDF)
- Scansiona email Gmail per allegati PDF dei fornitori
- Scarica e archivia i PDF in MongoDB
- Associa al fornitore corretto
"""
import os
import re
import uuid
import email
import asyncio
import imaplib
import logging
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.database import Database
from emergentintegrations.llm.chat import LlmChat, UserMessage
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schede-tecniche", tags=["Schede Tecniche"])

EMERGENT_KEY  = os.environ.get("EMERGENT_LLM_KEY", "")
IMAP_HOST     = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_USER     = os.environ.get("IMAP_USER", "")
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "")
XML_DIR       = Path("/app/app/uploads/pec_xml")

# ── Namespace FatturaPA ──────────────────────────────────────────────────────

def _find_tag(root, tag: str):
    """Cerca un tag ignorando il namespace."""
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local == tag:
            yield el


def _extract_products_from_xml(xml_path: Path) -> List[str]:
    """Estrae le descrizioni prodotti da una fattura XML FatturaPA."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        products = []
        for el in _find_tag(root, "Descrizione"):
            desc = (el.text or "").strip()
            if desc and len(desc) > 3:
                skip_kw = ["spese", "cauzioni", "iva", "sconto", "acconto", "trasporto",
                           "imballaggi", "contributo", "servizio", "noleggio", "fitto",
                           "provvigioni", "rimborso", "anticipo"]
                if not any(kw in desc.lower() for kw in skip_kw):
                    products.append(desc)
        return list(dict.fromkeys(products))
    except Exception as e:
        logger.warning(f"Errore parsing XML {xml_path}: {e}")
        return []


async def _find_xml_for_fornitore(db, fornitore) -> List[Path]:
    """Trova i file XML per un fornitore tramite le fatture passive."""
    piva = (fornitore.get("partita_iva") or fornitore.get("piva") or "").strip()
    nome = (fornitore.get("nome") or fornitore.get("ragione_sociale") or fornitore.get("denominazione") or "").strip()

    # Cerca fatture passive associate a questo fornitore (per P.IVA o nome)
    or_clauses = []
    if piva:
        or_clauses.append({"fornitore_piva": piva})
    if nome:
        or_clauses.append({"fornitore_denominazione": {"$regex": re.escape(nome[:25]), "$options": "i"}})

    if not or_clauses:
        return []

    fatture = await db["fatture_passive"].find(
        {"$or": or_clauses} if len(or_clauses) > 1 else or_clauses[0],
        {"_id": 0, "xml_filename": 1}
    ).limit(20).to_list(20)

    paths = []
    for f in fatture:
        fname = f.get("xml_filename")
        if fname:
            # I file sono salvati come `{hash}_{xml_filename}` in pec_xml
            matches = list(XML_DIR.glob(f"*{fname}"))
            paths.extend(matches)

    # Fallback: cerca per P.IVA nel nome del file XML (es. "IT04104640612" per piva "04104640612")
    if not paths and piva:
        paths = list(XML_DIR.glob(f"*{piva}*"))

    return list(dict.fromkeys(paths))[:50]


def _extract_cedente_from_xml(xml_path: Path) -> dict:
    """
    Estrae i dati del CedentePrestatore (fornitore) da un file XML FatturaPA.
    Ritorna un dizionario con: ragione_sociale, partita_iva, codice_fiscale,
    indirizzo, cap, comune, provincia, telefono, email
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Trova il blocco CedentePrestatore
        cedente = None
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == "CedentePrestatore":
                cedente = el
                break

        if cedente is None:
            return {}

        # Estrai tutti i campi testo del blocco
        dati: dict = {}
        for child in cedente.iter():
            local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child.text and child.text.strip():
                dati[local] = child.text.strip()

        result: dict = {}

        # Nome azienda
        if dati.get("Denominazione"):
            result["ragione_sociale"] = dati["Denominazione"]
            result["nome"] = dati["Denominazione"]
        elif dati.get("Nome") and dati.get("Cognome"):
            result["ragione_sociale"] = f"{dati['Cognome']} {dati['Nome']}"
            result["nome"] = result["ragione_sociale"]

        # P.IVA / CF
        if dati.get("IdCodice"):
            result["partita_iva"] = dati["IdCodice"]
        if dati.get("CodiceFiscale"):
            result["codice_fiscale"] = dati["CodiceFiscale"]

        # Indirizzo
        if dati.get("Indirizzo"):
            result["indirizzo"] = dati["Indirizzo"]
        if dati.get("CAP"):
            result["cap"] = dati["CAP"]
        if dati.get("Comune"):
            result["comune"] = dati["Comune"]
        if dati.get("Provincia"):
            result["provincia"] = dati["Provincia"]

        # Contatti
        if dati.get("Telefono"):
            result["telefono"] = dati["Telefono"]
        if dati.get("Email"):
            result["email"] = dati["Email"]

        return result

    except Exception as e:
        logger.warning(f"Errore estrazione cedente da {xml_path}: {e}")
        return {}


async def _ai_find_scheda(prodotto: str, fornitore_nome: str = "") -> dict:
    """
    Usa Claude AI per identificare brand, sito ufficiale e probabile URL della scheda tecnica PDF.
    Claude ha conoscenza dei brand alimentari italiani e può suggerire URL plausibili.
    """
    if not EMERGENT_KEY:
        return {"brand": None, "prodotto_pulito": prodotto,
                "url_pdf_probabile": None, "sito_ufficiale": None, "query_alternativa": prodotto}
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"scheda-{uuid.uuid4()}",
            system_message=(
                "Sei un esperto di prodotti alimentari italiani, normativa HACCP e schede tecniche. "
                "Conosci i principali brand alimentari italiani e i loro siti web ufficiali. "
                "Rispondi SOLO con JSON puro, nessun markdown."
            )
        ).with_model("anthropic", "claude-haiku-4-5")

        msg = UserMessage(text=(
            f"Prodotto da fattura italiana: '{prodotto}'\n"
            f"Fornitore: '{fornitore_nome}'\n\n"
            "Analizza questo prodotto e rispondi con JSON:\n"
            '{\n'
            '  "brand": "nome produttore/brand (es: Caputo, Molino Dallagiovanna, Papillon, null se sconosciuto)",\n'
            '  "prodotto_pulito": "nome prodotto senza codici, misure, abbreviazioni",\n'
            '  "sito_ufficiale": "dominio sito ufficiale del brand (es: caputo.it) o null",\n'
            '  "url_pdf_probabile": "URL plausibile del PDF della scheda tecnica sul sito ufficiale o null",\n'
            '  "percorso_tipico": "percorso tipico per trovare schede tecniche sul sito (es: /prodotti/schede-tecniche)",\n'
            '  "categorie_normativa": ["lista HACCP applicabili: allergeni, temperatura, ecc"]\n'
            '}'
        ))
        raw = await chat.send_message(msg)
        import json
        # Rimuovi markdown code blocks se presenti
        clean = re.sub(r"```json\s*|```\s*", "", raw).strip()
        # Rimuovi eventuale testo prima del primo {
        start = clean.find("{")
        end   = clean.rfind("}") + 1
        if start >= 0 and end > start:
            clean = clean[start:end]
        return json.loads(clean)
    except Exception as e:
        logger.warning(f"AI scheda ID fallita per '{prodotto}': {e}")
        return {"brand": None, "prodotto_pulito": prodotto,
                "url_pdf_probabile": None, "sito_ufficiale": None, "query_alternativa": prodotto}


async def _cerca_pdf_su_sito(sito: str, prodotto_clean: str) -> Optional[str]:
    """Cerca PDF di scheda tecnica direttamente sul sito del brand tramite scraping."""
    if not sito:
        return None
    try:
        base_url = f"https://www.{sito}" if not sito.startswith("http") else sito
        async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"}) as client:
            # Prima prova homepage per capire la struttura
            try:
                resp = await client.get(base_url)
                if resp.status_code == 200:
                    # Cerca link PDF nella homepage
                    html = resp.text.lower()
                    import re as re2
                    pdf_links = re2.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', html, re2.IGNORECASE)
                    # Filtra per parole chiave
                    kw = prodotto_clean.lower().split()[:2]
                    for link in pdf_links:
                        if any(k in link.lower() for k in kw) or "scheda" in link.lower() or "technical" in link.lower():
                            if link.startswith("http"):
                                return link
                            return base_url.rstrip("/") + "/" + link.lstrip("/")
            except Exception:
                pass
        return None
    except Exception as e:
        logger.warning(f"Scraping sito {sito} fallito: {e}")
        return None


async def _download_pdf(url: str) -> Optional[bytes]:
    """Scarica un PDF da URL."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 (compatible; SchedeTecniche/1.0)"}) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) > 1000:
                ct = resp.headers.get("content-type", "")
                if "pdf" in ct.lower() or ".pdf" in url.lower():
                    return resp.content
    except Exception as e:
        logger.warning(f"Download PDF fallito da {url}: {e}")
    return None


def _scan_gmail_for_scheda(fornitore_nome: str, prodotto: str) -> Optional[bytes]:
    """
    Scansiona la casella Gmail alla ricerca di allegati PDF che
    potrebbero essere schede tecniche per il prodotto indicato.
    Cerca email con oggetto/mittente contenente il nome fornitore
    e allegati PDF con nome simile al prodotto.
    Ritorna i bytes del primo PDF trovato, oppure None.
    """
    if not IMAP_USER or not IMAP_PASSWORD:
        return None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, 993)
        mail.login(IMAP_USER, IMAP_PASSWORD)
        mail.select("INBOX")

        # Cerca email con parola chiave del fornitore o "scheda tecnica"
        parole = [
            fornitore_nome.split()[0][:12].upper(),  # prima parola nome fornitore
            "scheda tecnica",
            "technical sheet",
        ]
        pdf_trovato = None
        for parola in parole:
            status, msg_ids = mail.search(None, f'SUBJECT "{parola}"')
            if status != "OK":
                continue
            ids = msg_ids[0].split()[-20:]  # ultimi 20
            for mid in reversed(ids):
                _, msg_data = mail.fetch(mid, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                for part in msg.walk():
                    ctype = part.get_content_type()
                    fname = (part.get_filename() or "").lower()
                    if ctype == "application/pdf" or fname.endswith(".pdf"):
                        # Verifica somiglianza nome prodotto
                        parole_prod = [w.lower() for w in re.split(r"[\s_\-]+", prodotto) if len(w) > 3]
                        if any(p in fname for p in parole_prod) or not parole_prod:
                            pdf_trovato = part.get_payload(decode=True)
                            break
                if pdf_trovato:
                    break
            if pdf_trovato:
                break

        mail.logout()
        return pdf_trovato
    except Exception as e:
        logger.warning(f"Errore scansione Gmail per scheda tecnica: {e}")
        return None




@router.post("/popola-fornitore/{fornitore_id}")
async def popola_fornitore_da_xml(fornitore_id: str):
    """
    Legge tutti i file XML delle fatture del fornitore ed estrae i dati anagrafici
    dal blocco CedentePrestatore (telefono, email, indirizzo, comune, provincia...).
    Aggiorna SOLO i campi mancanti (non sovrascrive dati esistenti).
    """
    db = Database.get_db()

    fornitore = await db["fornitori"].find_one(
        {"$or": [{"id": fornitore_id}, {"partita_iva": fornitore_id}]},
        {"_id": 0}
    )
    if not fornitore:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    xml_paths = await _find_xml_for_fornitore(db, fornitore)
    if not xml_paths:
        return {"success": False, "message": "Nessun file XML trovato per questo fornitore", "dati": {}}

    dati_estratti: dict = {}
    for xml_path in xml_paths:
        cedente = _extract_cedente_from_xml(xml_path)
        # Prendi il primo valore non vuoto trovato per ogni campo
        for k, v in cedente.items():
            if k not in dati_estratti and v:
                dati_estratti[k] = v

    if not dati_estratti:
        return {"success": False, "message": "Nessun dato anagrafico trovato negli XML", "dati": {}}

    # Aggiorna solo i campi che mancano nel fornitore
    aggiornamenti = {}
    for campo, valore in dati_estratti.items():
        if not fornitore.get(campo) and valore:
            aggiornamenti[campo] = valore

    if aggiornamenti:
        aggiornamenti["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db["fornitori"].update_one(
            {"$or": [{"id": fornitore_id}, {"partita_iva": fornitore_id}]},
            {"$set": aggiornamenti}
        )

    return {
        "success": True,
        "dati_estratti": dati_estratti,
        "campi_aggiornati": list(aggiornamenti.keys()),
        "xml_letti": len(xml_paths),
        "message": f"Aggiornati {len(aggiornamenti)} campi da {len(xml_paths)} fatture XML"
    }


# ── ENDPOINT CERCA SCHEDE PER FORNITORE ─────────────────────────────────────

class RicercaRequest(BaseModel):
    fornitore_id: str
    prodotti_manuali: Optional[List[str]] = None


@router.post("/cerca")
async def cerca_schede_tecniche(req: RicercaRequest, background: BackgroundTasks):
    """
    Avvia la ricerca automatica schede tecniche per un fornitore.
    Legge fatture XML → estrae prodotti → cerca PDF → scarica → archivia.
    """
    db = Database.get_db()
    fornitore = await db["fornitori"].find_one(
        {"$or": [{"id": req.fornitore_id}, {"partita_iva": req.fornitore_id}]},
        {"_id": 0}
    )
    if not fornitore:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db["schede_tecniche_jobs"].insert_one({
        "job_id": job_id,
        "fornitore_id": req.fornitore_id,
        "fornitore_nome": fornitore.get("ragione_sociale") or fornitore.get("denominazione", ""),
        "stato": "in_corso",
        "prodotti_trovati": [],
        "schede_trovate": 0,
        "errori": [],
        "created_at": now,
        "updated_at": now,
    })

    background.add_task(_esegui_ricerca, db, job_id, fornitore, req.prodotti_manuali)

    return {"job_id": job_id, "stato": "avviato",
            "messaggio": "Ricerca avviata. Controlla lo stato con /job/{job_id}"}


async def _esegui_ricerca(db, job_id: str, fornitore: dict, prodotti_manuali):
    """Task background: esegue la ricerca completa."""
    fornitore_id = fornitore.get("id") or ""
    errori = []
    schede_trovate = 0

    try:
        # 1. Estrai prodotti dalle fatture XML
        if prodotti_manuali:
            prodotti = prodotti_manuali
        else:
            xml_paths = await _find_xml_for_fornitore(db, fornitore)
            prodotti = []
            for p in xml_paths:
                prodotti.extend(_extract_products_from_xml(p))
            prodotti = list(dict.fromkeys(prodotti))  # senza limite: tutti i prodotti dalle fatture

        await db["schede_tecniche_jobs"].update_one(
            {"job_id": job_id},
            {"$set": {"prodotti_trovati": prodotti, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

        if not prodotti:
            await db["schede_tecniche_jobs"].update_one(
                {"job_id": job_id},
                {"$set": {"stato": "completato_vuoto",
                          "messaggio": "Nessun prodotto trovato nelle fatture XML.",
                          "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            return

        # 2. Per ogni prodotto: cerca PDF (max 50)
        for prodotto in prodotti[:50]:
            try:
                # Controlla duplicati
                esistente = await db["schede_tecniche"].find_one({
                    "fornitore_id": fornitore_id,
                    "prodotto": {"$regex": re.escape(prodotto[:30]), "$options": "i"}
                })
                if esistente:
                    continue

                # Usa AI per identificare brand e trovare URL scheda tecnica
                fornitore_nome = fornitore.get("nome") or fornitore.get("ragione_sociale") or ""
                info = await _ai_find_scheda(prodotto, fornitore_nome)
                brand      = info.get("brand")
                nome_clean = info.get("prodotto_pulito") or prodotto
                sito       = info.get("sito_ufficiale")
                url_probabile = info.get("url_pdf_probabile")

                pdf_url = None

                # Prova 1: URL diretto suggerito da AI
                if url_probabile:
                    test_bytes = await _download_pdf(url_probabile)
                    if test_bytes:
                        pdf_url = url_probabile

                # Prova 2: scraping del sito ufficiale
                if not pdf_url and sito:
                    pdf_url = await _cerca_pdf_su_sito(sito, nome_clean)
                    if pdf_url:
                        test_bytes = await _download_pdf(pdf_url)
                        if not test_bytes:
                            pdf_url = None

                scheda: dict = {
                    "id": str(uuid.uuid4()),
                    "fornitore_id": fornitore_id,
                    "fornitore_nome": fornitore.get("nome") or fornitore.get("ragione_sociale", ""),
                    "prodotto": prodotto,
                    "prodotto_pulito": nome_clean,
                    "brand": brand,
                    "sito_ufficiale": sito,
                    "url_fonte": pdf_url or url_probabile,
                    "pdf_data": None,
                    "nome_file": None,
                    "dimensione_bytes": 0,
                    "stato": "non_trovato",
                    "fonte_tipo": "web",
                    "ai_analisi": {
                        "brand": brand,
                        "sito": sito,
                        "url_suggerito": url_probabile,
                        "categorie": info.get("categorie_normativa", [])
                    },
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                if pdf_url:
                    pdf_bytes = await _download_pdf(pdf_url)
                    if pdf_bytes:
                        from bson import Binary
                        scheda["pdf_data"] = Binary(pdf_bytes)
                        scheda["nome_file"] = pdf_url.split("/")[-1][:100] or f"{nome_clean[:40]}.pdf"
                        scheda["dimensione_bytes"] = len(pdf_bytes)
                        scheda["stato"] = "trovato"
                        schede_trovate += 1
                    else:
                        scheda["stato"] = "url_trovato"
                        scheda["nome_file"] = pdf_url.split("/")[-1][:100]
                elif url_probabile:
                    # URL suggerito ma non scaricabile — lo mostriamo comunque
                    scheda["stato"] = "url_suggerito"
                    scheda["url_fonte"] = url_probabile
                    scheda["nome_file"] = url_probabile.split("/")[-1][:100]

                # Prova 3: scansione email Gmail (inbox fornitore)
                if not pdf_url and IMAP_USER and IMAP_PASSWORD:
                    fornitore_nome_str = fornitore.get("ragione_sociale") or fornitore.get("nome", "")
                    # to_thread: la funzione IMAP è sincrona, NON deve bloccare l'event loop
                    gmail_pdf = await asyncio.to_thread(_scan_gmail_for_scheda, fornitore_nome_str, prodotto)
                    if gmail_pdf:
                        from bson import Binary
                        scheda["pdf_data"] = Binary(gmail_pdf)
                        scheda["nome_file"] = f"{nome_clean[:40]}_email.pdf"
                        scheda["dimensione_bytes"] = len(gmail_pdf)
                        scheda["stato"] = "trovato"
                        scheda["fonte_tipo"] = "email"
                        schede_trovate += 1
                        await db["schede_tecniche"].insert_one(scheda)
                        continue  # vai al prossimo prodotto

                await db["schede_tecniche"].insert_one(scheda)

            except Exception as e:
                errori.append(f"{prodotto[:50]}: {str(e)[:80]}")
                logger.error(f"Errore scheda per '{prodotto}': {e}")

        # 3. Aggiorna job completato
        await db["schede_tecniche_jobs"].update_one(
            {"job_id": job_id},
            {"$set": {
                "stato": "completato",
                "schede_trovate": schede_trovate,
                "errori": errori,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )

    except Exception as e:
        logger.error(f"Errore job {job_id}: {e}")
        await db["schede_tecniche_jobs"].update_one(
            {"job_id": job_id},
            {"$set": {"stato": "errore", "errori": [str(e)],
                      "updated_at": datetime.now(timezone.utc).isoformat()}}
        )


# ── GET: Schede per fornitore ────────────────────────────────────────────────

@router.get("/fornitore/{fornitore_id}")
async def get_schede_fornitore(fornitore_id: str):
    """
    Restituisce tutte le schede tecniche del fornitore già cercate (da DB)
    UNITE a tutti i prodotti trovati negli XML non ancora cercati (stato: non_cercato).
    """
    db = Database.get_db()

    # 1. Schede già in DB per questo fornitore
    schede_db = await db["schede_tecniche"].find(
        {"fornitore_id": fornitore_id},
        {"_id": 0, "pdf_data": 0}
    ).sort("created_at", -1).to_list(500)

    # 2. Tutti i prodotti dagli XML (senza limite)
    fornitore = await db["fornitori"].find_one(
        {"$or": [{"id": fornitore_id}, {"partita_iva": fornitore_id}]},
        {"_id": 0}
    )

    tutti_prodotti_xml: List[str] = []
    if fornitore:
        xml_paths = await _find_xml_for_fornitore(db, fornitore)
        for p in xml_paths:
            tutti_prodotti_xml.extend(_extract_products_from_xml(p))
        tutti_prodotti_xml = list(dict.fromkeys(tutti_prodotti_xml))  # dedup, senza limite

    # 3. Merge: mappa prodotto → scheda già cercata
    schede_by_prodotto = {}
    for s in schede_db:
        key = (s.get("prodotto") or "").lower().strip()
        if key:
            schede_by_prodotto[key] = s

    merged: List[dict] = []
    prodotti_già_inclusi = set()

    # Prima aggiungi tutte le schede già in DB (nell'ordine: trovate prima)
    for s in schede_db:
        merged.append(s)
        key = (s.get("prodotto") or "").lower().strip()
        prodotti_già_inclusi.add(key)

    # Poi aggiungi i prodotti XML non ancora cercati
    for prodotto in tutti_prodotti_xml:
        key = prodotto.lower().strip()
        if key and key not in prodotti_già_inclusi:
            merged.append({
                "prodotto": prodotto,
                "prodotto_pulito": prodotto,
                "stato": "non_cercato",
                "fornitore_id": fornitore_id,
            })
            prodotti_già_inclusi.add(key)

    job = await db["schede_tecniche_jobs"].find_one(
        {"fornitore_id": fornitore_id},
        {"_id": 0},
        sort=[("created_at", -1)]
    )

    return {
        "fornitore_id": fornitore_id,
        "schede": merged,
        "totale": len(merged),
        "trovate": sum(1 for s in schede_db if s.get("stato") in ("trovato", "url_trovato", "url_suggerito")),
        "da_cercare": len(merged) - len(schede_db),
        "job": job,
    }


@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    db = Database.get_db()
    job = await db["schede_tecniche_jobs"].find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    return job


@router.get("/download/{scheda_id}")
async def download_scheda(scheda_id: str):
    """Scarica il PDF di una scheda tecnica."""
    db = Database.get_db()
    scheda = await db["schede_tecniche"].find_one({"id": scheda_id})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")

    if scheda.get("pdf_data"):
        return Response(
            content=bytes(scheda["pdf_data"]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{scheda.get("nome_file", "scheda.pdf")}"'}
        )
    elif scheda.get("url_fonte"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=scheda["url_fonte"])
    else:
        raise HTTPException(status_code=404, detail="PDF non disponibile")


@router.delete("/{scheda_id}")
async def elimina_scheda(scheda_id: str):
    db = Database.get_db()
    r = await db["schede_tecniche"].delete_one({"id": scheda_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    return {"success": True}


@router.get("/prodotti/{fornitore_id}")
async def get_prodotti_fornitore(fornitore_id: str):
    """Restituisce i prodotti estratti dalle fatture XML per un fornitore."""
    db = Database.get_db()
    fornitore = await db["fornitori"].find_one(
        {"$or": [{"id": fornitore_id}, {"_id": fornitore_id}]},
        {"_id": 0}
    )
    if not fornitore:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    xml_paths = await _find_xml_for_fornitore(db, fornitore)
    prodotti = []
    for p in xml_paths:
        prodotti.extend(_extract_products_from_xml(p))

    return {
        "fornitore_id": fornitore_id,
        "prodotti": list(dict.fromkeys(prodotti))[:30],
        "fatture_xml_trovate": len(xml_paths),
    }
