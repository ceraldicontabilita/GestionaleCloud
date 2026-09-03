"""
Router: fornitori_anagrafica
Gestione contatti fornitori: email commerciale + cellulare/WhatsApp
- Auto-import dai file XML fatture (quando disponibili)
- Import lista fornitori da collection invoices
- CRUD manuale per email e cellulare
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import os, re, xml.etree.ElementTree as ET, logging
from datetime import datetime, timezone

from app.lotti.db import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fornitori-anagrafica", tags=["Anagrafica Fornitori"])

# ── Modelli ──────────────────────────────────────────────────────────────────


class ContattoFornitore(BaseModel):
    nome: str
    email: Optional[str] = ""
    cellulare: Optional[str] = ""
    note: Optional[str] = ""
    email_verificata: Optional[bool] = False
    rivendita_colazione: Optional[bool] = False
    rivendita_senza_glutine: Optional[bool] = False
    # ── Scheda estesa (03/07/2026): più dati = più qualità estraibile per
    # ordini e ricette. Tutti opzionali, compilabili a mano un po' alla volta.
    pec: Optional[str] = ""
    sito_web: Optional[str] = ""            # usato anche per cercare schede tecniche prodotti
    referente: Optional[str] = ""           # agente/commerciale di riferimento
    telefono_fisso: Optional[str] = ""
    giorni_consegna: Optional[str] = ""     # es. "lunedì e giovedì"
    giorni_chiusura: Optional[str] = ""     # es. "agosto 10-20, domenica" — per anticipare/raddoppiare gli ordini
    ordine_minimo: Optional[str] = ""       # es. "150 € / 10 colli"
    condizioni_pagamento: Optional[str] = ""  # es. "RiBa 30gg fine mese"
    metodo_pagamento: Optional[str] = ""
    certificazioni: Optional[str] = ""      # es. "BIO, IGP, MSC"
    giorni_consegna_settimana: Optional[List[int]] = Field(default_factory=list)
    lead_time_giorni: Optional[int] = 1
    ora_limite_ordine: Optional[str] = ""
    procedura_ordini_attiva: Optional[bool] = True
    chiusure_programmate: Optional[List[dict]] = Field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_phone(raw: str) -> str:
    """Normalizza numero di telefono: rimuove spazi, trattini, aggiunge +39 se mancante."""
    if not raw:
        return ""
    digits = re.sub(r"[\s\-\(\)\.]", "", raw)
    # Rimuovi prefisso 0039 se presente
    if digits.startswith("0039"):
        digits = "+39" + digits[4:]
    elif digits.startswith("39") and len(digits) > 10:
        digits = "+" + digits
    elif digits.startswith("0") and not digits.startswith("00"):
        digits = "+39" + digits
    return digits


def _whatsapp_number(raw: str) -> str:
    """Converte numero in formato WhatsApp (solo cifre, senza +)."""
    n = _normalize_phone(raw)
    return re.sub(r"[^\d]", "", n)


def _estrai_contatti_da_xml_string(xml_content: str) -> dict:
    """Estrae email e telefono del FORNITORE dal blocco CedentePrestatore della
    fattura PA. Ignora l'email del committente (CessionarioCommittente) e la
    PEC/Codice di trasmissione (DatiTrasmissione), che NON sono l'email del fornitore."""
    out = {"email": "", "telefono": ""}
    if not xml_content:
        return out
    try:
        if isinstance(xml_content, bytes):
            xml_content = xml_content.decode("utf-8", "ignore")
        root = ET.fromstring(xml_content)

        def localname(el):
            return el.tag.split("}")[-1] if "}" in el.tag else el.tag

        # Trova il nodo CedentePrestatore (il fornitore)
        cedente = None
        for el in root.iter():
            if localname(el) == "CedentePrestatore":
                cedente = el
                break
        scope = cedente if cedente is not None else root
        for el in scope.iter():
            tag = localname(el)
            if tag == "Email" and not out["email"]:
                out["email"] = (el.text or "").strip()
            if tag == "Telefono" and not out["telefono"]:
                out["telefono"] = (el.text or "").strip()
    except Exception as e:
        logger.debug(f"Errore parsing xml_raw: {e}")
    return out


def _estrai_contatti_xml(xml_path: str) -> dict:
    """Legacy: estrae da file su disco (se esiste). Usa _estrai_contatti_da_xml_string."""
    if not xml_path or not os.path.exists(xml_path):
        return {"email": "", "telefono": ""}
    try:
        with open(xml_path, "rb") as f:
            return _estrai_contatti_da_xml_string(f.read())
    except Exception as e:
        logger.debug(f"Errore lettura XML {xml_path}: {e}")
        return {"email": "", "telefono": ""}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def lista_anagrafica():
    """Lista tutti i fornitori con email e cellulare salvati."""
    docs = await db.fornitori_anagrafica.find({}, {"_id": 0}).sort("nome", 1).to_list(500)
    return docs


@router.put("/{nome_fornitore}")
async def aggiorna_contatto(nome_fornitore: str, payload: ContattoFornitore):
    """Salva o aggiorna email e cellulare di un fornitore.
    Se email_verificata=True, l'import-da-fatture non sovrascriverà più l'email."""
    cel_norm = _normalize_phone(payload.cellulare or "")
    giorni_consegna = sorted({
        int(g) for g in (payload.giorni_consegna_settimana or [])
        if isinstance(g, int) and 0 <= int(g) <= 6
    })
    lead_time = max(0, min(int(payload.lead_time_giorni or 0), 30))
    chiusure = []
    for periodo in payload.chiusure_programmate or []:
        if not isinstance(periodo, dict):
            continue
        dal = str(periodo.get("dal") or "").strip()
        al = str(periodo.get("al") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dal) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", al) and dal <= al:
            chiusure.append({"dal": dal, "al": al, "motivo": str(periodo.get("motivo") or "").strip()})
    await db.fornitori_anagrafica.update_one(
        {"nome": nome_fornitore},
        {
            "$set": {
                "nome": nome_fornitore,
                "email": payload.email or "",
                "cellulare": cel_norm,
                "cellulare_raw": payload.cellulare or "",
                "note": payload.note or "",
                "email_verificata": bool(payload.email_verificata),
                "rivendita_colazione": bool(payload.rivendita_colazione),
                "rivendita_senza_glutine": bool(payload.rivendita_senza_glutine),
                "pec": (payload.pec or "").strip(),
                "sito_web": (payload.sito_web or "").strip(),
                "referente": (payload.referente or "").strip(),
                "telefono_fisso": (payload.telefono_fisso or "").strip(),
                "giorni_consegna": (payload.giorni_consegna or "").strip(),
                "giorni_chiusura": (payload.giorni_chiusura or "").strip(),
                "ordine_minimo": (payload.ordine_minimo or "").strip(),
                "condizioni_pagamento": (payload.condizioni_pagamento or "").strip(),
                "metodo_pagamento": (payload.metodo_pagamento or "").strip(),
                "certificazioni": (payload.certificazioni or "").strip(),
                "giorni_consegna_settimana": giorni_consegna,
                "lead_time_giorni": lead_time,
                "ora_limite_ordine": (payload.ora_limite_ordine or "").strip(),
                "procedura_ordini_attiva": bool(payload.procedura_ordini_attiva),
                "chiusure_programmate": chiusure,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "fonte": "manuale",
            }
        },
        upsert=True,
    )

    # Sync col registro fornitori_rivendita (che pilota i modali Colazione/Senza Glutine).
    try:
        import uuid as _uuid
        from app.lotti.routers.fornitori_rivendita import _ensure_seed
        await _ensure_seed()

        def _slug(s: str) -> str:
            return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "fornitore"

        coppie = (
            ("colazione", bool(payload.rivendita_colazione)),
            ("senza_glutine", bool(payload.rivendita_senza_glutine)),
        )
        for tipo, flag in coppie:
            entry = await db.fornitori_rivendita.find_one({"tipo": tipo, "match_fattura": nome_fornitore})
            if flag:
                if entry:
                    await db.fornitori_rivendita.update_one({"id": entry["id"]}, {"$set": {"attivo": True}})
                else:
                    await db.fornitori_rivendita.insert_one({
                        "id": str(_uuid.uuid4()),
                        "nome": nome_fornitore,
                        "fonte": _slug(nome_fornitore),
                        "tipo": tipo,
                        "match_fattura": nome_fornitore,
                        "attivo": True,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
            elif entry:
                await db.fornitori_rivendita.update_one({"id": entry["id"]}, {"$set": {"attivo": False}})
    except Exception:
        logger.debug("[fornitori-anagrafica] sync registro rivendita non bloccante")

    return {"success": True, "nome": nome_fornitore, "email_verificata": bool(payload.email_verificata)}


@router.get("/{nome_fornitore}")
async def get_contatto(nome_fornitore: str):
    """Recupera contatti di un fornitore."""
    doc = await db.fornitori_anagrafica.find_one({"nome": nome_fornitore}, {"_id": 0})
    if not doc:
        return {"nome": nome_fornitore, "email": "", "cellulare": ""}
    return doc


@router.post("/import-da-fatture")
async def import_da_fatture(sovrascrivi_sbagliate: bool = True):
    """
    Popola/aggiorna fornitori_anagrafica leggendo l'email del FORNITORE dal campo
    xml_raw delle fatture (collection fatture), dal nodo CedentePrestatore.
    Con sovrascrivi_sbagliate=True corregge anche le email palesemente errate
    già salvate (PEC, indirizzi SDI/fatturazione, email del committente Ceraldi).
    """
    result = {"importati": 0, "aggiornati": 0, "corretti": 0, "solo_nome": 0, "totale_fornitori": 0, "errori": []}

    # Email/domini da considerare NON validi come email commerciale del fornitore
    def email_sospetta(e: str) -> bool:
        e = (e or "").strip().lower()
        if not e or "@" not in e:
            return True
        cattive = ["legalmail.it", "pec.", "@pec", "sdi", "fatturapa", "documi.it",
                   "ceraldigroupsrl@gmail.com", "ceraldi"]
        return any(k in e for k in cattive)

    # Raggruppa le fatture per fornitore, tenendo un xml_raw per ciascuno
    fornitori_xml = {}
    async for f in db.fatture.find({}, {"_id": 0, "fornitore": 1, "xml_raw": 1}):
        nome = (f.get("fornitore") or "").strip()
        if not nome:
            continue
        if nome not in fornitori_xml and f.get("xml_raw"):
            fornitori_xml[nome] = f["xml_raw"]

    result["totale_fornitori"] = len(fornitori_xml)

    for nome, xml_raw in fornitori_xml.items():
        contatti = _estrai_contatti_da_xml_string(xml_raw)
        email_xml = contatti["email"].strip()
        tel_xml = contatti["telefono"].strip()
        # Non accettare come email del fornitore un indirizzo sospetto (PEC/SDI/committente)
        if email_sospetta(email_xml):
            email_xml = ""

        existing = await db.fornitori_anagrafica.find_one({"nome": nome}, {"_id": 0})
        if existing:
            update = {}
            cur = (existing.get("email") or "").strip()
            verificata = bool(existing.get("email_verificata"))
            # Se l'email è stata verificata a mano, è la fonte di verità: non toccarla mai
            if not verificata and email_xml and (not cur or (sovrascrivi_sbagliate and email_sospetta(cur))):
                update["email"] = email_xml
                if cur and email_sospetta(cur):
                    result["corretti"] += 1
            if not existing.get("cellulare") and tel_xml:
                update["cellulare"] = _normalize_phone(tel_xml)
                update["cellulare_raw"] = tel_xml
            if update:
                update["fonte_xml"] = True
                update["updated_at"] = datetime.now(timezone.utc).isoformat()
                await db.fornitori_anagrafica.update_one({"nome": nome}, {"$set": update})
                result["aggiornati"] += 1
        else:
            cel_norm = _normalize_phone(tel_xml) if tel_xml else ""
            await db.fornitori_anagrafica.insert_one({
                "nome": nome,
                "email": email_xml,
                "cellulare": cel_norm,
                "cellulare_raw": tel_xml,
                "note": "",
                "fonte": "xml" if email_xml else "fattura",
                "fonte_xml": bool(email_xml),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            if email_xml:
                result["importati"] += 1
            else:
                result["solo_nome"] += 1

    return {
        "success": True,
        "messaggio": f"{result['importati']} importati con email, {result['corretti']} email corrette, {result['aggiornati']} aggiornati, {result['solo_nome']} solo nome (email non in fattura)",
        **result,
    }


@router.get("/{nome_fornitore}/whatsapp-link")
async def whatsapp_link(nome_fornitore: str, messaggio: str = ""):
    """Genera il link WhatsApp per un fornitore."""
    doc = await db.fornitori_anagrafica.find_one({"nome": nome_fornitore}, {"_id": 0})
    if not doc or not doc.get("cellulare"):
        raise HTTPException(400, "Cellulare non configurato per questo fornitore")
    numero_wa = _whatsapp_number(doc["cellulare"])
    if not numero_wa:
        raise HTTPException(400, "Numero non valido")
    import urllib.parse

    link = f"https://wa.me/{numero_wa}?text={urllib.parse.quote(messaggio)}"
    return {"link": link, "numero": numero_wa}
