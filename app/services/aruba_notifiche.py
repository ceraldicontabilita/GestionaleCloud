"""
Notifiche fatture Aruba → Prima Nota anticipata ("fatture attese").
=================================================================

Quando arriva una fattura elettronica, Aruba manda una email di avviso da
noreply@fatturazioneelettronica.aruba.it con dentro mittente (fornitore),
numero fattura e importo. Questo servizio:

1. `scan_notifiche_aruba(db)` — legge via IMAP le notifiche recenti,
   estrae fornitore/numero/importo/data e salva una "fattura attesa"
   (collection `fatture_attese`). Le attese compaiono nei Provvisori
   come "in arrivo" con il suggerimento cassa/banca del fornitore
   (stesso motore prima nota di tutto il resto). NON crea movimenti da
   sola: la registrazione resta una conferma dell'utente, come per le
   fatture vere (regola: mai registrazione automatica).

2. `riscontra_fattura_attesa(db, invoice)` — chiamata dalla pipeline
   unica di import XML (process_fattura_to_db): quando l'XML vero
   arriva (Drive/email/upload) cerca l'attesa corrispondente per
   numero+importo e la marca "riscontrata". Se l'utente aveva già
   confermato l'anticipo, il movimento esistente viene AGGANCIATO alla
   fattura vera (fattura_id) e la fattura marcata registrata: MAI due
   movimenti per la stessa fattura.

3. `controlla_attese_scadute(db)` — attese annunciate ma senza XML dopo
   N giorni (env ARUBA_ATTESA_GIORNI_ALERT, default 3): prova prima la
   quadratura della cartella Drive "Elaborate" (così sappiamo GIÀ cosa
   cercare invece di confrontare tutto), poi se manca ancora genera
   l'alert FATTURA_ANNUNCIATA_NON_ARRIVATA con numero/fornitore/importo.

Vale solo dall'attivazione in avanti (la posta vecchia è stata
cancellata): il pregresso resta coperto dalla quadratura Drive.
"""
import asyncio
import email as email_lib
import imaplib
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.services._email_utils import extract_best_body
from app.utils.numeri_italiani import parse_importo_ita

logger = logging.getLogger(__name__)

COLL_ATTESE = "fatture_attese"
CANALE_MITTENTE = "aruba_notifiche"
PATTERN_MITTENTE_DEFAULT = "fatturazioneelettronica.aruba.it"
STATO_KEY_LAST_SCAN = "aruba_notifiche_last_scan"


# ---------------------------------------------------------------------------
# Parsing notifica (puro, testabile)
# ---------------------------------------------------------------------------

# Etichette tipiche delle notifiche Aruba ("Mittente: ACME SRL",
# "Numero documento: 123/A", "Importo: 1.234,56 €"...). Pattern tolleranti:
# il formato esatto può variare tra template Aruba.
_RE_FORNITORE = re.compile(
    r"(?:mittente|cedente(?:/prestatore)?|fornitore|ragione sociale)\s*[:\-]\s*(.{3,90}?)\s*(?:$|\n)",
    re.IGNORECASE | re.MULTILINE,
)
_RE_NUMERO = re.compile(
    r"(?:numero(?:\s+(?:documento|fattura))?|fattura\s+(?:n|nr|num)\.?)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/\._]{0,29})",
    re.IGNORECASE,
)
_RE_IMPORTO = re.compile(
    r"(?:importo(?:\s+totale)?|totale(?:\s+documento)?)\s*[:\-]?\s*(?:€\s*)?([\d\.\s]+,\d{2}|\d+(?:\.\d{2})?)\s*(?:€|eur)?",
    re.IGNORECASE,
)
_RE_DATA = re.compile(
    r"(?:data(?:\s+(?:documento|fattura|emissione))?)\s*[:\-]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def _norm_data(raw: str) -> Optional[str]:
    """DD/MM/YYYY o YYYY-MM-DD → YYYY-MM-DD."""
    raw = (raw or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", raw)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def normalizza_numero_fattura(numero: str) -> str:
    """Normalizza il numero fattura per il confronto attesa ↔ XML.

    Maiuscolo, senza spazi; gli zeri iniziali di ogni blocco numerico
    vengono rimossi ("0000123/A" e "123/A" devono coincidere).
    """
    n = (numero or "").upper().strip()
    n = re.sub(r"\s+", "", n)
    n = re.sub(r"\b0+(\d)", r"\1", n)
    return n


def parse_notifica_aruba(subject: str, body: str) -> Dict[str, Any]:
    """Estrae fornitore, numero, importo e data da una notifica Aruba.

    Ritorna sempre un dict; i campi non trovati sono None. `completa` è
    True solo se numero e importo sono entrambi presenti (il minimo per
    un riscontro affidabile con l'XML).
    """
    testo = f"{subject or ''}\n{body or ''}"

    fornitore = None
    m = _RE_FORNITORE.search(testo)
    if m:
        fornitore = re.sub(r"\s+", " ", m.group(1)).strip(" .;,")
        # Scarta catture spazzatura (es. frammenti di URL o footer)
        if len(fornitore) < 3 or "http" in fornitore.lower():
            fornitore = None

    numero = None
    m = _RE_NUMERO.search(testo)
    if m:
        numero = m.group(1).strip(" .;,")

    importo = None
    m = _RE_IMPORTO.search(testo)
    if m:
        importo = parse_importo_ita(m.group(1), default=0.0)
        if importo <= 0:
            importo = None

    data_doc = None
    m = _RE_DATA.search(testo)
    if m:
        data_doc = _norm_data(m.group(1))

    return {
        "fornitore_nome": fornitore,
        "numero_fattura": numero,
        "numero_norm": normalizza_numero_fattura(numero) if numero else None,
        "importo": importo,
        "data_documento": data_doc,
        "completa": bool(numero and importo),
    }


# ---------------------------------------------------------------------------
# Credenziali e mittente
# ---------------------------------------------------------------------------

async def _get_gmail_credentials(db) -> Optional[Dict[str, str]]:
    """Stessa catena di risoluzione credenziali di email_monitor_service."""
    from app.config import settings

    email_user = None
    email_password = None
    imap_host = settings.IMAP_HOST or "imap.gmail.com"
    try:
        from app.utils.crypto import decrypt_credential
        gmail_cfg = await db["settings"].find_one({"chiave": "gmail"}, {"_id": 0})
        if gmail_cfg and gmail_cfg.get("gmail_app_password") and gmail_cfg.get("imap_user"):
            email_user = gmail_cfg["imap_user"]
            email_password = decrypt_credential(gmail_cfg["gmail_app_password"])
            imap_host = gmail_cfg.get("imap_host", imap_host)
    except Exception:
        pass
    if not email_user:
        email_user = settings.IMAP_USER or settings.EMAIL_USER
    if not email_password:
        email_password = settings.IMAP_PASSWORD or settings.EMAIL_PASSWORD
    if not email_user or not email_password:
        return None
    return {"user": email_user, "password": email_password, "host": imap_host}


async def _get_pattern_mittente(db) -> str:
    """Pattern del mittente notifiche, gestito in mittenti_email (canale
    dedicato, così l'utente lo vede e lo può cambiare da Admin). Se manca
    viene creato con il default Aruba."""
    m = await db["mittenti_email"].find_one(
        {"canale": CANALE_MITTENTE, "attivo": True}, {"_id": 0}
    )
    if m and m.get("pattern"):
        return m["pattern"].lower()
    await db["mittenti_email"].update_one(
        {"canale": CANALE_MITTENTE, "pattern": PATTERN_MITTENTE_DEFAULT},
        {"$setOnInsert": {
            "id": str(uuid.uuid4()),
            "canale": CANALE_MITTENTE,
            "pattern": PATTERN_MITTENTE_DEFAULT,
            "tipo_documento": "notifica_fattura",
            "descrizione": "Notifiche fattura ricevuta (Aruba) → fatture attese",
            "attivo": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return PATTERN_MITTENTE_DEFAULT


# ---------------------------------------------------------------------------
# Suggerimento destinazione (stesso motore del resto della Prima Nota)
# ---------------------------------------------------------------------------

async def _suggerimento_per_fornitore(db, nome: str) -> Dict[str, Any]:
    """Cerca il fornitore per nome e ritorna il suggerimento cassa/banca/
    sospesa dal metodo in anagrafica (motore unico prima_nota_engine)."""
    from app.routers.prima_nota_module.sync import classifica_metodo_fornitore

    if not nome:
        return {"suggerimento": "sospesa", "fornitore_id": None, "fornitore_piva": None}

    nome_up = nome.upper().strip()
    # Match tollerante: esatto, poi "inizia con", poi prime 2 parole significative
    fornitore = await db["fornitori"].find_one(
        {"ragione_sociale": {"$regex": f"^{re.escape(nome_up)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "partita_iva": 1, "piva": 1, "metodo_pagamento": 1},
    )
    if not fornitore:
        fornitore = await db["fornitori"].find_one(
            {"ragione_sociale": {"$regex": f"^{re.escape(nome_up[:20])}", "$options": "i"}},
            {"_id": 0, "id": 1, "partita_iva": 1, "piva": 1, "metodo_pagamento": 1},
        )
    if not fornitore:
        parole = [p for p in nome_up.split() if len(p) > 3][:2]
        if parole:
            rx = ".*".join(re.escape(p) for p in parole)
            fornitore = await db["fornitori"].find_one(
                {"ragione_sociale": {"$regex": rx, "$options": "i"}},
                {"_id": 0, "id": 1, "partita_iva": 1, "piva": 1, "metodo_pagamento": 1},
            )
    if not fornitore:
        return {"suggerimento": "sospesa", "fornitore_id": None, "fornitore_piva": None}
    return {
        "suggerimento": classifica_metodo_fornitore(fornitore.get("metodo_pagamento", "")),
        "fornitore_id": fornitore.get("id"),
        "fornitore_piva": fornitore.get("partita_iva") or fornitore.get("piva"),
    }


# ---------------------------------------------------------------------------
# Scan IMAP
# ---------------------------------------------------------------------------

def _fetch_notifiche_imap(creds: Dict[str, str], pattern: str, since: datetime) -> List[Dict[str, Any]]:
    """Scarica (sincrono, girato in thread) le notifiche dal mittente."""
    out: List[Dict[str, Any]] = []
    conn = imaplib.IMAP4_SSL(creds["host"])
    try:
        conn.login(creds["user"], creds["password"])
        conn.select("INBOX", readonly=True)
        since_str = since.strftime("%d-%b-%Y")
        status, data = conn.search(None, f'(FROM "{pattern}" SINCE "{since_str}")')
        if status != "OK" or not data or not data[0]:
            return out
        ids = data[0].split()
        # Sicurezza: al massimo 300 messaggi per ciclo
        for msg_id in ids[-300:]:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email_lib.message_from_bytes(msg_data[0][1])
            from app.services.email_document_downloader import decode_mime_header
            subject = decode_mime_header(msg.get("Subject", ""))
            message_id = (msg.get("Message-ID") or "").strip()
            date_hdr = msg.get("Date", "")
            try:
                email_dt = email_lib.utils.parsedate_to_datetime(date_hdr)
                email_date = email_dt.astimezone(timezone.utc).isoformat()
            except Exception:
                email_date = datetime.now(timezone.utc).isoformat()
            body = extract_best_body(msg)
            out.append({
                "message_id": message_id or f"uid-{msg_id.decode(errors='ignore')}-{date_hdr}",
                "subject": subject,
                "body": body,
                "email_date": email_date,
            })
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return out


async def scan_notifiche_aruba(db, giorni: Optional[int] = None) -> Dict[str, Any]:
    """Legge le notifiche Aruba recenti e aggiorna le fatture attese.

    Idempotente: dedup per Message-ID e per (numero_norm, importo).
    La finestra parte dall'ultimo scan riuscito (margine 1 giorno), mai
    dal passato remoto: la logica vale da oggi in avanti.
    """
    creds = await _get_gmail_credentials(db)
    if not creds:
        return {"success": False, "error": "Credenziali Gmail non configurate", "stats": {}}

    pattern = await _get_pattern_mittente(db)

    stato = await db["sistema_stato"].find_one({"chiave": STATO_KEY_LAST_SCAN}, {"_id": 0})
    now = datetime.now(timezone.utc)
    if giorni is not None:
        since = now - timedelta(days=max(1, giorni))
    elif stato and stato.get("valore"):
        try:
            since = datetime.fromisoformat(stato["valore"]) - timedelta(days=1)
        except ValueError:
            since = now - timedelta(days=3)
    else:
        # Prima attivazione: solo gli ultimi 3 giorni (da oggi in avanti,
        # il pregresso è coperto dalla quadratura Drive)
        since = now - timedelta(days=3)

    try:
        messaggi = await asyncio.to_thread(_fetch_notifiche_imap, creds, pattern, since)
    except Exception as e:
        logger.error(f"[Aruba] Errore IMAP: {e}")
        return {"success": False, "error": str(e), "stats": {}}

    nuove = 0
    gia_note = 0
    non_leggibili = 0

    for msg in messaggi:
        esiste = await db[COLL_ATTESE].find_one(
            {"message_id": msg["message_id"]}, {"_id": 0, "id": 1}
        )
        if esiste:
            gia_note += 1
            continue

        parsed = parse_notifica_aruba(msg["subject"], msg["body"])

        # Dedup anche per contenuto (stessa fattura annunciata due volte)
        if parsed["completa"]:
            dup = await db[COLL_ATTESE].find_one({
                "numero_norm": parsed["numero_norm"],
                "importo": {"$gte": parsed["importo"] - 0.01, "$lte": parsed["importo"] + 0.01},
            }, {"_id": 0, "id": 1})
            if dup:
                gia_note += 1
                continue

        sugg = await _suggerimento_per_fornitore(db, parsed.get("fornitore_nome") or "")

        attesa = {
            "id": str(uuid.uuid4()),
            "message_id": msg["message_id"],
            "email_subject": msg["subject"][:300],
            "email_date": msg["email_date"],
            "email_estratto": (msg["body"] or "")[:1500],
            "fornitore_nome": parsed.get("fornitore_nome"),
            "fornitore_id": sugg.get("fornitore_id"),
            "fornitore_piva": sugg.get("fornitore_piva"),
            "numero_fattura": parsed.get("numero_fattura"),
            "numero_norm": parsed.get("numero_norm"),
            "importo": parsed.get("importo"),
            "data_documento": parsed.get("data_documento"),
            "suggerimento": sugg.get("suggerimento", "sospesa"),
            "stato": "in_attesa_xml" if parsed["completa"] else "da_verificare",
            "prima_nota_id": None,
            "prima_nota_collection": None,
            "invoice_id": None,
            "fonte": "email_aruba",
            "created_at": now.isoformat(),
        }
        await db[COLL_ATTESE].insert_one(attesa)
        nuove += 1

        if not parsed["completa"]:
            non_leggibili += 1
            try:
                from app.services.alert_engine import genera_alert
                await genera_alert(
                    "EMAIL_ARUBA_NON_LEGGIBILE", attesa["id"], COLL_ATTESE,
                    f"Notifica Aruba non interpretabile ({msg['subject'][:80]}): "
                    f"apri l'attesa e completa numero/importo a mano",
                    db,
                )
            except Exception:
                logger.exception("Errore alert EMAIL_ARUBA_NON_LEGGIBILE")

    await db["sistema_stato"].update_one(
        {"chiave": STATO_KEY_LAST_SCAN},
        {"$set": {"valore": now.isoformat(), "updated_at": now.isoformat()}},
        upsert=True,
    )

    stats = {"new_invoices": nuove, "gia_note": gia_note,
             "non_leggibili": non_leggibili, "messaggi_letti": len(messaggi)}
    if nuove:
        logger.info(f"[Aruba] {nuove} fatture annunciate da email ({non_leggibili} da verificare)")
    return {"success": True, "stats": stats}


# ---------------------------------------------------------------------------
# Riscontro con l'XML vero (chiamato dalla pipeline unica di import)
# ---------------------------------------------------------------------------

async def riscontra_fattura_attesa(db, invoice: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Quando una fattura XML viene importata, cerca l'attesa corrispondente.

    Match: numero normalizzato uguale + importo entro ±0,01 € (se l'attesa
    ha l'importo). Se l'attesa era già stata confermata (movimento anticipato
    esistente), il movimento viene agganciato alla fattura vera e la fattura
    marcata registrata: è questo il lucchetto anti-doppione.
    """
    numero_norm = normalizza_numero_fattura(
        invoice.get("invoice_number") or invoice.get("numero_fattura") or ""
    )
    if not numero_norm:
        return None
    importo = float(invoice.get("total_amount") or invoice.get("importo_totale") or 0)

    candidati = await db[COLL_ATTESE].find(
        {"stato": {"$in": ["in_attesa_xml", "da_verificare", "confermata_anticipo"]},
         "numero_norm": numero_norm},
        {"_id": 0},
    ).to_list(20)

    attesa = None
    for c in candidati:
        imp_attesa = c.get("importo")
        if imp_attesa is None or abs(float(imp_attesa) - importo) <= 0.01:
            attesa = c
            break
    if not attesa:
        return None

    now = datetime.now(timezone.utc).isoformat()
    await db[COLL_ATTESE].update_one(
        {"id": attesa["id"]},
        {"$set": {"stato": "riscontrata", "invoice_id": invoice.get("id"),
                  "riscontrata_at": now}},
    )

    esito = {"attesa_id": attesa["id"], "anticipo_agganciato": False}

    # Se l'anticipo era già stato confermato in prima nota → aggancia il
    # movimento esistente alla fattura vera invece di lasciarne creare uno nuovo
    if attesa.get("prima_nota_id") and attesa.get("prima_nota_collection"):
        coll = attesa["prima_nota_collection"]
        fattura_id = invoice.get("id")
        await db[coll].update_one(
            {"id": attesa["prima_nota_id"]},
            {"$set": {
                "fattura_id": fattura_id,
                "riferimento": f"FATT-{fattura_id}",
                "numero_fattura": invoice.get("invoice_number") or attesa.get("numero_fattura"),
                "fornitore_piva": invoice.get("supplier_vat") or attesa.get("fornitore_piva"),
                "descrizione": (
                    f"Pagamento fattura {invoice.get('invoice_number', '?')} - "
                    f"{(invoice.get('supplier_name') or attesa.get('fornitore_nome') or '')[:40]}"
                ),
                "anticipo_da_email": True,
                "updated_at": now,
            }},
        )
        metodo = "cassa" if coll == "prima_nota_cassa" else "banca"
        await db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "prima_nota_id": attesa["prima_nota_id"],
                "pagato": True,
                "stato_pagamento": "pagata",
                "metodo_pagamento_effettivo": metodo,
                "data_pagamento": now[:10],
                "registrata_da": "anticipo_email_aruba",
            }},
        )
        esito["anticipo_agganciato"] = True
        logger.info(
            f"[Aruba] Fattura {invoice.get('invoice_number')} agganciata al "
            f"movimento anticipato {attesa['prima_nota_id']} ({metodo}) — nessun doppione"
        )

    return esito


# ---------------------------------------------------------------------------
# Attese scadute: prima cerca in Drive Elaborate, poi alert mirato
# ---------------------------------------------------------------------------

async def controlla_attese_scadute(db) -> Dict[str, Any]:
    """Attese senza XML dopo N giorni: prova la quadratura Elaborate
    (recupero mirato: sappiamo già cosa manca), poi alert per le superstiti."""
    giorni = int(os.environ.get("ARUBA_ATTESA_GIORNI_ALERT", "3") or 3)
    limite = (datetime.now(timezone.utc) - timedelta(days=giorni)).isoformat()

    scadute = await db[COLL_ATTESE].find(
        {"stato": {"$in": ["in_attesa_xml", "confermata_anticipo"]},
         "alert_generato": {"$ne": True},
         "created_at": {"$lt": limite}},
        {"_id": 0},
    ).to_list(100)
    if not scadute:
        return {"scadute": 0, "recuperate": 0}

    # Tentativo di recupero: ripassa la cartella Drive "Elaborate"
    # (idempotente). Se l'XML era lì, l'import scatena riscontra_fattura_attesa
    # e l'attesa esce da questa lista.
    try:
        from app.services.drive_invoice_ingest import verifica_quadratura_elaborate, is_configured
        if is_configured():
            await verifica_quadratura_elaborate(db)
    except Exception as e:
        logger.warning(f"[Aruba] Quadratura Elaborate non riuscita: {e}")

    ancora_scadute = await db[COLL_ATTESE].find(
        {"id": {"$in": [s["id"] for s in scadute]},
         "stato": {"$in": ["in_attesa_xml", "confermata_anticipo"]}},
        {"_id": 0},
    ).to_list(100)

    alert_creati = 0
    try:
        from app.services.alert_engine import genera_alert
        for a in ancora_scadute:
            await genera_alert(
                "FATTURA_ANNUNCIATA_NON_ARRIVATA", a["id"], COLL_ATTESE,
                f"Fattura {a.get('numero_fattura', '?')} di "
                f"{a.get('fornitore_nome', 'fornitore sconosciuto')} "
                f"({a.get('importo', 0):.2f} €) annunciata da email il "
                f"{(a.get('email_date') or '')[:10]} ma XML mai arrivato "
                f"(né da Drive/Elaborate né da email)",
                db,
            )
            await db[COLL_ATTESE].update_one(
                {"id": a["id"]}, {"$set": {"alert_generato": True}}
            )
            alert_creati += 1
    except Exception:
        logger.exception("Errore alert FATTURA_ANNUNCIATA_NON_ARRIVATA")

    return {"scadute": len(scadute),
            "recuperate": len(scadute) - len(ancora_scadute),
            "alert": alert_creati}
