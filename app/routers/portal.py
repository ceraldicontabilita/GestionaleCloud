"""Portal router - Portal/invitation functionality + Portale Dipendenti."""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any
import logging
import uuid
import hashlib
import base64
import random
import string
from datetime import datetime, timezone, timedelta

from app.utils.dependencies import get_current_user
from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


# ===== PORTALE DIPENDENTI =====

@router.post("/collega-google")
async def collega_google_dipendente(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Collega un Google Account a un dipendente tramite codice di invito.
    Il dipendente accede con Google e inserisce il codice ricevuto via email.
    """
    db = Database.get_db()
    email_google = data.get("email_google", "").lower().strip()
    codice_invito = data.get("codice_invito", "").strip().upper()

    if not email_google or not codice_invito:
        raise HTTPException(400, "Email Google e codice invito obbligatori")

    invito = await db["portal_inviti"].find_one({
        "codice": codice_invito,
        "usato": {"$ne": True},
        "scadenza": {"$gte": datetime.now(timezone.utc).isoformat()}
    })
    if not invito:
        raise HTTPException(400, "Codice invito non valido o scaduto")

    await db["dipendenti"].update_one(
        {"id": invito["dipendente_id"]},
        {"$set": {
            "google_email": email_google,
            "portale_registrato": True,
            "portale_primo_accesso": datetime.now(timezone.utc).isoformat()
        }}
    )
    await db["portal_inviti"].update_one(
        {"codice": codice_invito},
        {"$set": {
            "usato": True,
            "usato_at": datetime.now(timezone.utc).isoformat(),
            "google_email": email_google
        }}
    )
    return {"message": "Account collegato con successo"}


@router.post("/genera-invito/{dipendente_id}")
async def genera_invito_dipendente(dipendente_id: str) -> Dict[str, Any]:
    """
    Genera codice invito per un dipendente.
    Chiamato dal datore dopo aver creato l'anagrafica.
    """
    db = Database.get_db()
    dip = await db["dipendenti"].find_one({"id": dipendente_id}, {"_id": 0})
    if not dip:
        raise HTTPException(404, "Dipendente non trovato")

    codice = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    scadenza = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    await db["portal_inviti"].insert_one({
        "id": str(uuid.uuid4()),
        "dipendente_id": dipendente_id,
        "dipendente_nome": dip.get("nome_completo", ""),
        "codice": codice,
        "scadenza": scadenza,
        "usato": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    email = dip.get("email", "")
    email_inviata = False
    if email:
        try:
            from app.services.email_sender import invia_email
            await invia_email(
                to=email,
                subject="Accesso al portale dipendenti Ceraldi Group",
                body=(
                    f"Ciao {dip.get('nome_completo', '')},\n\n"
                    f"Puoi accedere al tuo spazio personale sul gestionale.\n\n"
                    f"Codice di accesso: {codice}\n"
                    f"Il codice scade il {scadenza[:10]}.\n\n"
                    f"Accedi con il tuo account Google e inserisci questo codice."
                )
            )
            email_inviata = True
        except Exception as e:
            logger.warning(f"Email invito non inviata: {e}")

    await db["dipendenti"].update_one(
        {"id": dipendente_id},
        {"$set": {
            "portale_invitato": True,
            "portale_invito_inviato": datetime.now(timezone.utc).isoformat()
        }}
    )
    return {"codice": codice, "scadenza": scadenza, "email_inviata": email_inviata}


@router.get("/portale/cedolini")
async def get_miei_cedolini(current_user=Depends(get_current_user)):
    """Cedolini del dipendente loggato (filtrati per google_email)."""
    db = Database.get_db()
    dip = await db["dipendenti"].find_one(
        {"google_email": current_user["email"]}, {"_id": 0}
    )
    if not dip:
        raise HTTPException(403, "Utente non collegato a nessun dipendente")
    cedolini = await db["cedolini"].find(
        {"$or": [
            {"dipendente_id": dip["id"]},
            {"codice_fiscale": dip.get("codice_fiscale")}
        ]},
        {"_id": 0, "pdf_data": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(36)
    return cedolini


@router.get("/portale/cedolini/{cedolino_id}/pdf")
async def scarica_mio_cedolino(cedolino_id: str, current_user=Depends(get_current_user)):
    """Scarica il PDF di un cedolino (solo il proprio)."""
    from fastapi.responses import Response
    db = Database.get_db()
    dip = await db["dipendenti"].find_one({"google_email": current_user["email"]})
    if not dip:
        raise HTTPException(403, "Accesso negato")
    cedolino = await db["cedolini"].find_one({
        "id": cedolino_id,
        "$or": [
            {"dipendente_id": dip["id"]},
            {"codice_fiscale": dip.get("codice_fiscale")}
        ]
    })
    if not cedolino:
        raise HTTPException(404, "Cedolino non trovato o non autorizzato")
    pdf_bytes = base64.b64decode(cedolino["pdf_data"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cedolino_{cedolino_id}.pdf"}
    )


@router.get("/portale/contratti")
async def get_miei_contratti(current_user=Depends(get_current_user)):
    """Contratti del dipendente loggato."""
    db = Database.get_db()
    dip = await db["dipendenti"].find_one(
        {"google_email": current_user["email"]}, {"_id": 0}
    )
    if not dip:
        raise HTTPException(403, "Accesso negato")
    contratti = await db["employee_contracts"].find(
        {"dipendente_id": dip["id"]},
        {"_id": 0, "pdf_data": 0}
    ).to_list(20)
    return contratti


@router.post("/portale/firma/{documento_id}")
async def firma_documento(
    documento_id: str,
    request: Request,
    current_user=Depends(get_current_user)
):
    """
    Firma Elettronica Semplice (FES) conforme art.3 eIDAS.
    Registra: nome_digitato validato, timestamp, IP, user-agent, hash documento,
    tempo_lettura, doppio checkbox, certificato hash univoco.
    """
    db = Database.get_db()

    # Leggi body JSON dalla request
    try:
        body = await request.json()
    except Exception:
        body = {}

    nome_digitato = (body.get("nome_digitato") or "").strip()
    checkbox_lettura = body.get("checkbox_lettura", False)
    checkbox_accettazione = body.get("checkbox_accettazione", False)
    scroll_completato = body.get("scroll_completato", False)
    tempo_lettura_secondi = int(body.get("tempo_lettura_secondi", 0))
    firma_canvas_base64 = (body.get("firma_canvas_base64") or "").strip()

    # --- Validazioni obbligatorie ---
    if not checkbox_lettura or not checkbox_accettazione:
        raise HTTPException(422, "Devi spuntare entrambe le caselle di conferma lettura e accettazione")
    if not scroll_completato:
        raise HTTPException(422, "Devi leggere il documento fino in fondo prima di firmarlo")
    if not nome_digitato:
        raise HTTPException(422, "Devi digitare il tuo nome e cognome completo per firmare")
    if tempo_lettura_secondi < 5:
        raise HTTPException(422, "Tempo di lettura insufficiente. Leggi il documento con attenzione")
    if not firma_canvas_base64 or len(firma_canvas_base64) < 100:
        raise HTTPException(422, "La firma disegnata è obbligatoria e non può essere vuota")

    # --- Carica dipendente tramite google_email ---
    dip = await db["dipendenti"].find_one(
        {"google_email": current_user["email"]}, {"_id": 0}
    )
    if not dip:
        # Fallback su collection dipendenti
        dip = await db["dipendenti"].find_one(
            {"google_email": current_user["email"]}, {"_id": 0}
        )
    if not dip:
        raise HTTPException(403, "Accesso negato: utente non collegato a nessun dipendente")

    # --- Valida il nome digitato (match fuzzy nome+cognome) ---
    nome_dip = dip.get("nome_completo") or f"{dip.get('nome','').strip()} {dip.get('cognome','').strip()}".strip()
    try:
        from thefuzz import fuzz
        score = fuzz.token_sort_ratio(nome_digitato.lower(), nome_dip.lower())
        if score < 75:
            raise HTTPException(
                422,
                f"Il nome digitato non corrisponde al tuo nome registrato. "
                f"Digita esattamente: {nome_dip}"
            )
    except ImportError:
        # Senza fuzz: match case-insensitive semplice
        if nome_digitato.lower() != nome_dip.lower():
            raise HTTPException(422, f"Digita esattamente: {nome_dip}")

    # --- Carica documento ---
    doc = await db["employee_contracts"].find_one({"id": documento_id})
    if not doc or doc.get("dipendente_id") != dip["id"]:
        raise HTTPException(404, "Documento non trovato o non autorizzato")
    if doc.get("firmato"):
        raise HTTPException(409, "Documento già firmato in precedenza")

    # --- Genera hash del documento e certificato firma ---
    pdf_b64 = doc.get("pdf_data", "")
    pdf_bytes = base64.b64decode(pdf_b64) if pdf_b64 else b""
    hash_documento = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else hashlib.sha256(documento_id.encode()).hexdigest()

    timestamp_firma = datetime.now(timezone.utc).isoformat()
    ip_firma = request.client.host if request.client else "N/D"

    # Hash univoco della firma: doc_id + email + timestamp + nome_digitato
    hash_firma = hashlib.sha256(
        f"{documento_id}|{current_user['email']}|{timestamp_firma}|{nome_digitato}".encode()
    ).hexdigest()

    firma = {
        "id": str(uuid.uuid4()),
        "dipendente_id": dip["id"],
        "dipendente_email": current_user["email"],
        "dipendente_nome_sistema": nome_dip,
        "nome_digitato_dalla_firma": nome_digitato,
        "documento_id": documento_id,
        "documento_tipo": doc.get("tipo", "Contratto"),
        "hash_documento": hash_documento,
        "hash_firma": hash_firma,
        "firma_timestamp": timestamp_firma,
        "firma_ip": ip_firma,
        "firma_user_agent": request.headers.get("user-agent", "")[:300],
        "firma_canvas_base64": firma_canvas_base64,
        "scroll_completato": scroll_completato,
        "tempo_lettura_secondi": tempo_lettura_secondi,
        "checkbox_lettura": True,
        "checkbox_accettazione": True,
        "accettazione_testuale": (
            f"Io sottoscritto/a {nome_digitato} dichiaro di aver letto "
            f"integralmente e di accettare tutte le clausole del documento "
            f"'{doc.get('tipo','Contratto')}' in data {timestamp_firma[:10]}."
        ),
        "valida": True,
        "created_at": timestamp_firma,
    }
    await db["documenti_firmati"].insert_one({k: v for k, v in firma.items() if k != "_id"})

    await db["employee_contracts"].update_one(
        {"id": documento_id},
        {"$set": {
            "firmato": True,
            "firma_id": firma["id"],
            "firmato_at": timestamp_firma,
            "firma_ip": ip_firma,
            "hash_firma": hash_firma,
        }}
    )

    # Notifica all'admin
    try:
        await db["agenti_segnalazioni"].insert_one({
            "id": str(uuid.uuid4()),
            "agente": "PortaleDipendente",
            "tipo": "info",
            "titolo": f"Contratto firmato — {nome_dip}",
            "descrizione": (
                f"{nome_dip} ha firmato il documento '{doc.get('tipo','')}' "
                f"il {timestamp_firma[:10]} alle {timestamp_firma[11:16]} UTC. "
                f"IP: {ip_firma}. Hash firma: {hash_firma[:16]}..."
            ),
            "letta": False,
            "risolta": False,
            "dati_riferimento": {
                "dipendente_id": dip["id"],
                "documento_id": documento_id,
                "hash_firma": hash_firma
            },
            "created_at": timestamp_firma
        })
    except Exception:
        pass

    return {
        "message": "Documento firmato con successo",
        "firma_id": firma["id"],
        "hash_firma": hash_firma,
        "timestamp": timestamp_firma,
        "certificato": {
            "firmato_da": nome_dip,
            "email": current_user["email"],
            "documento": doc.get("tipo", "Contratto"),
            "data_firma": timestamp_firma[:10],
            "ora_firma": timestamp_firma[11:16] + " UTC",
            "ip": ip_firma,
            "hash_documento": hash_documento[:32] + "...",
            "hash_firma": hash_firma,
            "valida_art3_eidas": True,
        }
    }
