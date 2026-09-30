"""
Router per gestione invio documenti al Commercialista.

Il periodo e' sempre un intervallo `dal`/`al` ISO (`pacchetto.intervallo_periodo`): le rotte
`/{anno}/{mese}` restano (mese=0 = anno intero) e accettano in piu' `?dal=&al=`.

Invio singolo (PDF costruito dal browser): Prima Nota Cassa, Carnet assegni, Fatture per cassa.
Pacchetto (`/pacchetto`, `/voce/...`, `/invia-pacchetto`): banca, PayPal, SumUp, bonifici,
corrispettivi, fatture ricevute, F24, stipendi e presenze HR, costruiti dal server e spediti in
UNA email; registro `commercialista_invii`, presenze nel registro unico di HR (`presenze_invii`).
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from calendar import monthrange
import logging
import base64

from app.constants.stati_assegno import STATI_DISPONIBILI
from app.database import Database
from app.services import commercialista_pacchetto as pacchetto
from app.utils.dependencies import get_current_admin_user
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Email commercialista di default
DEFAULT_COMMERCIALISTA_EMAIL = "rosaria.marotta@email.it"
MESI_NOMI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
             "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def _periodo(anno: int, mese: int) -> tuple[str, str]:
    if mese < 0 or mese > 12:
        raise HTTPException(status_code=400, detail="Mese deve essere tra 0 e 12")
    if mese == 0:
        return str(anno), f"Intero anno {anno}"
    return f"{anno}-{mese:02d}", f"{MESI_NOMI[mese]} {anno}"


def _intervallo(anno: Optional[int] = None, mese: Optional[int] = None,
                dal: Optional[str] = None, al: Optional[str] = None) -> pacchetto.Periodo:
    """Il periodo scelto in pagina: `dal`/`al` ISO oppure anno/mese (mese=0 = anno intero)."""
    try:
        return pacchetto.intervallo_periodo(anno, mese, dal, al)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def smtp_configurato() -> bool:
    """Lo stato mostrato in pagina e quello dell'invio sono la stessa domanda:
    `email_smtp.credenziali_smtp` (SMTP_* su Render, altrimenti la password
    per le app dell'account Gmail di `gmail_credentials`)."""
    from app.hr.services.email_smtp import credenziali_smtp

    return credenziali_smtp() is not None


def send_email_with_attachment(
    to_email: str,
    subject: str,
    html_body: str,
    attachment_data: Optional[bytes] = None,
    attachment_name: Optional[str] = None
) -> bool:
    """Invia un'email col PDF allegato dal punto unico di invio (`email_smtp`)."""
    from app.hr.services.email_smtp import credenziali_smtp, invia_email

    if credenziali_smtp() is None:
        logger.error("SMTP non configurato: né SMTP_* né la password per le app di Gmail")
        raise HTTPException(status_code=500, detail="Configurazione SMTP mancante")

    allegati = None
    if attachment_data and attachment_name:
        allegati = [(attachment_data, "application", "pdf", attachment_name)]
    try:
        invia_email(to_email, subject, html_body, allegati, html=True)
        logger.info("Email inviata a %s: %s", to_email, subject)
        return True
    except Exception as e:
        logger.error("Invio email a %s non riuscito: %s: %s", to_email, type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"Errore invio email: {type(e).__name__}") from e


@router.get("/config")
@handle_errors
async def get_commercialista_config() -> Dict[str, Any]:
    """Get commercialista configuration."""
    db = Database.get_db()
    
    # Try to get config from DB
    config = await db["commercialista_config"].find_one({}, {"_id": 0})
    
    if not config:
        config = {
            "email": DEFAULT_COMMERCIALISTA_EMAIL,
            "nome": "Dott.ssa Rosaria Marotta",
            "alert_giorni": 2,
            "invio_automatico": False
        }
    
    config["smtp_configured"] = smtp_configurato()
    
    return config


@router.put("/config")
@handle_errors
async def update_commercialista_config(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Update commercialista configuration."""
    db = Database.get_db()
    
    update_data = {
        "email": data.get("email", DEFAULT_COMMERCIALISTA_EMAIL),
        "nome": data.get("nome", ""),
        "alert_giorni": data.get("alert_giorni", 2),
        "invio_automatico": data.get("invio_automatico", False),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["commercialista_config"].update_one(
        {},
        {"$set": update_data},
        upsert=True
    )
    
    return {"success": True, "config": update_data}


@router.get("/prima-nota-cassa/{anno}/{mese}")
@handle_errors
async def get_prima_nota_cassa_mensile(anno: int, mese: int, dal: Optional[str] = None,
                                       al: Optional[str] = None) -> Dict[str, Any]:
    """Prima Nota Cassa del periodo: mese, anno intero (mese=0) o `dal`/`al` ISO."""
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)
    movements = await pacchetto.movimenti_cassa(db, p)
    totale_entrate, totale_uscite, _ = pacchetto._testata_movimenti(movements)
    return {
        "anno": anno,
        "mese": mese,
        "dal": p.dal,
        "al": p.al,
        "mese_nome": p.etichetta,
        "movimenti": movements,
        "totale_movimenti": len(movements),
        "totale_entrate": float(round(totale_entrate, 2)),
        "totale_uscite": float(round(totale_uscite, 2)),
        "saldo": float(round(totale_entrate - totale_uscite, 2)),
    }


# La lettura sta nel servizio del pacchetto (una sola per la pagina e per l'email).
fatture_pagate_in_cassa = pacchetto.fatture_pagate_in_cassa


@router.get("/fatture-cassa/{anno}/{mese}")
@handle_errors
async def get_fatture_pagate_cassa(anno: int, mese: int, dal: Optional[str] = None,
                                   al: Optional[str] = None) -> Dict[str, Any]:
    """Fatture pagate per cassa nel periodo (mese, anno intero con `mese=0`, o `dal`/`al`)."""
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)
    fatture = await fatture_pagate_in_cassa(db, p)
    totale = sum(f["importo_pagato_cassa"] for f in fatture)
    return {
        "anno": anno,
        "mese": mese,
        "dal": p.dal,
        "al": p.al,
        "mese_nome": p.etichetta,
        "fatture": fatture,
        "totale_fatture": len(fatture),
        "totale_importo": round(totale, 2),
        "fonte": "prima_nota_cassa",
    }


@router.get("/riepilogo/{anno}/{mese}")
@handle_errors
async def get_riepilogo_commercialista(anno: int, mese: int, dal: Optional[str] = None,
                                       al: Optional[str] = None) -> Dict[str, Any]:
    """Card source-backed per il periodo, senza trasformare proposte in pagamenti."""
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)
    periodo_nome = p.etichetta
    anno = int(p.dal[:4])

    movimenti_fatture = await db["prima_nota_banca"].find({
        **p.filtro("data"),
        "riconciliato": True,
        "$or": [
            {"categoria": {"$regex": "fattur", "$options": "i"}},
            {"fattura_id": {"$exists": True, "$ne": None}},
            {"invoice_id": {"$exists": True, "$ne": None}},
        ],
        "status": {"$nin": ["deleted", "archived"]},
    }, {"_id": 0, "fattura_id": 1, "invoice_id": 1, "numero_fattura": 1,
        "importo": 1, "amount": 1}).to_list(20000)
    fatture_keys = {
        str(m.get("fattura_id") or m.get("invoice_id") or m.get("numero_fattura") or "")
        for m in movimenti_fatture
        if m.get("fattura_id") or m.get("invoice_id") or m.get("numero_fattura")
    }
    totale_fatture_banca = round(sum(
        abs(float(m.get("importo") or m.get("amount") or 0)) for m in movimenti_fatture
    ), 2)

    cedolini = await db["cedolini"].find(
        {"anno": {"$in": [a for y in p.anni for a in (y, str(y))]},
         "entity_status": {"$ne": "deleted"}},
        {"_id": 0, "anno": 1, "mese": 1, "netto": 1, "netto_mese": 1},
    ).to_list(20000)
    mesi_periodo = set(p.mesi())

    def _mese_busta(c):
        try:
            return int(c.get("anno")), int(c.get("mese"))
        except (TypeError, ValueError):
            return None

    cedolini = [c for c in cedolini if _mese_busta(c) in mesi_periodo]
    totale_netto_cedolini = round(sum(
        float(c.get("netto") or c.get("netto_mese") or 0) for c in cedolini
    ), 2)

    commissioni = await db["pos_commissioni_giornaliere"].find(
        p.filtro("data"),
        {"_id": 0, "importo_lordo": 1, "importo_netto": 1,
         "commissioni": 1, "quadrato": 1},
    ).to_list(10000)

    from app.routers.iva import _fatture_anno, _iva_vendite_corrispettivi
    from app.engines import riepilogo_iva_engine as riep
    fatture_iva = await _fatture_anno(db, anno)
    categorie_iva = riep.riepilogo_categorie(fatture_iva)
    iva_credito_annuale = round(float(categorie_iva["disponibile"]["iva"] or 0), 2)
    iva_debito_annuale = round(sum(
        [await _iva_vendite_corrispettivi(db, f"{anno}-{month:02d}") for month in range(1, 13)]
    ), 2)

    return {
        "anno": anno,
        "mese": mese,
        "dal": p.dal,
        "al": p.al,
        "periodo_nome": periodo_nome,
        "fatture_banca": {
            "totale_fatture": len(fatture_keys),
            "totale_importo": totale_fatture_banca,
            "movimenti_riconciliati": len(movimenti_fatture),
        },
        "cedolini": {
            "totale_cedolini": len(cedolini),
            "totale_netto": totale_netto_cedolini,
        },
        "coerenza_pos": {
            "giorni": len(commissioni),
            "lordo": round(sum(float(c.get("importo_lordo") or 0) for c in commissioni), 2),
            "netto": round(sum(float(c.get("importo_netto") or 0) for c in commissioni), 2),
            "commissioni": round(sum(float(c.get("commissioni") or 0) for c in commissioni), 2),
            "giorni_non_quadrati": sum(1 for c in commissioni if c.get("quadrato") is False),
        },
        "iva_annuale": {
            "iva_credito": iva_credito_annuale,
            "iva_debito": iva_debito_annuale,
            "saldo": round(iva_debito_annuale - iva_credito_annuale, 2),
            "fatture_da_verificare": categorie_iva["da_verificare"]["conteggio"],
        },
    }


@router.post("/invia-prima-nota")
@handle_errors
async def invia_prima_nota_cassa(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Send Prima Nota Cassa via email with PDF attachment."""
    anno = data.get("anno")
    mese = data.get("mese")
    email = data.get("email", DEFAULT_COMMERCIALISTA_EMAIL)
    pdf_base64 = data.get("pdf_base64")  # PDF generated by frontend
    
    if not anno or not mese:
        raise HTTPException(status_code=400, detail="Anno e mese richiesti")
    
    mese_nome = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"][mese]
    
    # Get data for email body
    prima_nota_data = await get_prima_nota_cassa_mensile(anno, mese)
    
    subject = f"📒 Prima Nota Cassa - {mese_nome} {anno}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); color: white; padding: 20px;">
                <h1 style="margin: 0;">📒 Prima Nota Cassa</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">{mese_nome} {anno}</p>
            </div>
            
            <div style="padding: 20px;">
                <p>Gentile Commercialista,</p>
                <p>in allegato trova la Prima Nota Cassa relativa al mese di <strong>{mese_nome} {anno}</strong>.</p>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0 0 10px 0; color: #1e3a5f;">📊 Riepilogo</h3>
                    <table style="width: 100%;">
                        <tr>
                            <td style="padding: 5px 0;">Movimenti totali:</td>
                            <td style="padding: 5px 0; text-align: right; font-weight: bold;">{prima_nota_data['totale_movimenti']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 0; color: #4caf50;">Totale Entrate:</td>
                            <td style="padding: 5px 0; text-align: right; font-weight: bold; color: #4caf50;">€ {prima_nota_data['totale_entrate']:,.2f}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 0; color: #f44336;">Totale Uscite:</td>
                            <td style="padding: 5px 0; text-align: right; font-weight: bold; color: #f44336;">€ {prima_nota_data['totale_uscite']:,.2f}</td>
                        </tr>
                        <tr style="border-top: 2px solid #ddd;">
                            <td style="padding: 10px 0 5px 0; font-weight: bold;">Saldo:</td>
                            <td style="padding: 10px 0 5px 0; text-align: right; font-weight: bold; font-size: 18px; color: {'#4caf50' if prima_nota_data['saldo'] >= 0 else '#f44336'};">€ {prima_nota_data['saldo']:,.2f}</td>
                        </tr>
                    </table>
                </div>
                
                <p style="color: #666; font-size: 14px;">
                    Il documento PDF allegato contiene il dettaglio completo di tutti i movimenti.
                </p>
            </div>
            
            <div style="background: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666;">
                Ceraldi Group S.R.L. - ERP Azienda Semplice<br>
                Email generata automaticamente il {datetime.now().strftime('%d-%m-%Y alle %H:%M')}
            </div>
        </div>
    </body>
    </html>
    """
    
    # Decode PDF if provided
    pdf_bytes = None
    if pdf_base64:
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
        except Exception as e:
            logger.error(f"Error decoding PDF: {e}")
    
    filename = f"Prima_Nota_Cassa_{mese_nome}_{anno}.pdf"
    
    success = send_email_with_attachment(email, subject, html_body, pdf_bytes, filename)
    
    # Log the send
    db = Database.get_db()
    log_doc = {
        "tipo": "prima_nota_cassa",
        "anno": anno,
        "mese": mese,
        "email": email,
        "data_invio": datetime.now(timezone.utc).isoformat(),
        "success": success
    }
    await db["commercialista_log"].insert_one(log_doc.copy())
    
    return {
        "success": success,
        "message": f"Prima Nota Cassa {mese_nome} {anno} inviata a {email}"
    }


@router.post("/invia-carnet")
@handle_errors
async def invia_carnet(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Send Carnet assegni via email with PDF attachment."""
    carnet_id = data.get("carnet_id")
    email = data.get("email", DEFAULT_COMMERCIALISTA_EMAIL)
    pdf_base64 = data.get("pdf_base64")
    assegni_count = data.get("assegni_count", 0)
    totale_importo = data.get("totale_importo", 0)
    
    if not carnet_id:
        raise HTTPException(status_code=400, detail="carnet_id richiesto")
    
    subject = f"📝 Carnet Assegni - {carnet_id}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #4caf50 0%, #2e7d32 100%); color: white; padding: 20px;">
                <h1 style="margin: 0;">📝 Carnet Assegni</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">ID: {carnet_id}</p>
            </div>
            
            <div style="padding: 20px;">
                <p>Gentile Commercialista,</p>
                <p>in allegato trova il riepilogo del carnet assegni <strong>{carnet_id}</strong>.</p>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0 0 10px 0; color: #2e7d32;">📊 Riepilogo Carnet</h3>
                    <table style="width: 100%;">
                        <tr>
                            <td style="padding: 5px 0;">Numero Assegni:</td>
                            <td style="padding: 5px 0; text-align: right; font-weight: bold;">{assegni_count}</td>
                        </tr>
                        <tr style="border-top: 1px solid #ddd;">
                            <td style="padding: 10px 0 5px 0; font-weight: bold;">Totale Importo:</td>
                            <td style="padding: 10px 0 5px 0; text-align: right; font-weight: bold; font-size: 18px; color: #2e7d32;">€ {totale_importo:,.2f}</td>
                        </tr>
                    </table>
                </div>
                
                <p style="color: #666; font-size: 14px;">
                    Il documento PDF allegato contiene il dettaglio di tutti gli assegni del carnet.
                </p>
            </div>
            
            <div style="background: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666;">
                Ceraldi Group S.R.L. - ERP Azienda Semplice<br>
                Email generata automaticamente il {datetime.now().strftime('%d-%m-%Y alle %H:%M')}
            </div>
        </div>
    </body>
    </html>
    """
    
    pdf_bytes = None
    if pdf_base64:
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
        except Exception as e:
            logger.error(f"Error decoding PDF: {e}")
    
    filename = f"Carnet_Assegni_{carnet_id}.pdf"
    
    success = send_email_with_attachment(email, subject, html_body, pdf_bytes, filename)
    
    # Log the send
    db = Database.get_db()
    log_doc = {
        "tipo": "carnet_assegni",
        "carnet_id": carnet_id,
        "email": email,
        "data_invio": datetime.now(timezone.utc).isoformat(),
        "success": success
    }
    await db["commercialista_log"].insert_one(log_doc.copy())
    
    return {
        "success": success,
        "message": f"Carnet {carnet_id} inviato a {email}"
    }


@router.post("/invia-fatture-cassa")
@handle_errors
async def invia_fatture_cassa(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Send fatture pagate per cassa via email with PDF attachment."""
    anno = data.get("anno")
    mese = data.get("mese")
    email = data.get("email", DEFAULT_COMMERCIALISTA_EMAIL)
    pdf_base64 = data.get("pdf_base64")
    
    if not anno or not mese:
        raise HTTPException(status_code=400, detail="Anno e mese richiesti")
    
    mese_nome = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"][mese]
    
    # Get data for email body
    fatture_data = await get_fatture_pagate_cassa(anno, mese)
    
    subject = f"💵 Fatture Pagate per Cassa - {mese_nome} {anno}"
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <div style="background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%); color: white; padding: 20px;">
                <h1 style="margin: 0;">💵 Fatture Pagate per Cassa</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">{mese_nome} {anno}</p>
            </div>
            
            <div style="padding: 20px;">
                <p>Gentile Commercialista,</p>
                <p>in allegato trova l'elenco delle fatture pagate per cassa nel mese di <strong>{mese_nome} {anno}</strong>.</p>
                
                <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0 0 10px 0; color: #f57c00;">📊 Riepilogo</h3>
                    <table style="width: 100%;">
                        <tr>
                            <td style="padding: 5px 0;">Numero Fatture:</td>
                            <td style="padding: 5px 0; text-align: right; font-weight: bold;">{fatture_data['totale_fatture']}</td>
                        </tr>
                        <tr style="border-top: 1px solid #ffe0b2;">
                            <td style="padding: 10px 0 5px 0; font-weight: bold;">Totale:</td>
                            <td style="padding: 10px 0 5px 0; text-align: right; font-weight: bold; font-size: 18px; color: #f57c00;">€ {fatture_data['totale_importo']:,.2f}</td>
                        </tr>
                    </table>
                </div>
                
                <p style="color: #666; font-size: 14px;">
                    Il documento PDF allegato contiene il dettaglio di tutte le fatture.
                </p>
            </div>
            
            <div style="background: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666;">
                Ceraldi Group S.R.L. - ERP Azienda Semplice<br>
                Email generata automaticamente il {datetime.now().strftime('%d-%m-%Y alle %H:%M')}
            </div>
        </div>
    </body>
    </html>
    """
    
    pdf_bytes = None
    if pdf_base64:
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
        except Exception as e:
            logger.error(f"Error decoding PDF: {e}")
    
    filename = f"Fatture_Contanti_{mese_nome}_{anno}.pdf"
    
    success = send_email_with_attachment(email, subject, html_body, pdf_bytes, filename)
    
    # Log the send
    db = Database.get_db()
    log_doc = {
        "tipo": "fatture_cassa",
        "anno": anno,
        "mese": mese,
        "email": email,
        "data_invio": datetime.now(timezone.utc).isoformat(),
        "success": success
    }
    await db["commercialista_log"].insert_one(log_doc.copy())
    
    return {
        "success": success,
        "message": f"Fatture contanti {mese_nome} {anno} inviate a {email}"
    }


@router.get("/log")
@handle_errors
async def get_invio_log(limit: int = 50) -> Dict[str, Any]:
    """Get log of sent documents."""
    db = Database.get_db()
    
    cursor = db["commercialista_log"].find({}, {"_id": 0}).sort("data_invio", -1).limit(limit)
    log_entries = await cursor.to_list(limit)
    
    return {
        "log": log_entries,
        "totale": len(log_entries)
    }


@router.post("/segna-inviata")
@handle_errors
async def segna_prima_nota_inviata(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Segna manualmente la Prima Nota Cassa come inviata per un determinato mese/anno."""
    anno = data.get("anno")
    mese = data.get("mese")
    email = data.get("email", DEFAULT_COMMERCIALISTA_EMAIL)
    
    if not anno or not mese:
        raise HTTPException(status_code=400, detail="anno e mese sono obbligatori")
    
    db = Database.get_db()
    log_doc = {
        "tipo": "prima_nota_cassa",
        "anno": anno,
        "mese": mese,
        "email": email,
        "data_invio": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "note": "Segnata manualmente come inviata"
    }
    await db["commercialista_log"].insert_one(log_doc.copy())
    
    mese_nome = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"][mese]
    return {
        "success": True,
        "message": f"Prima Nota Cassa {mese_nome} {anno} segnata come inviata"
    }


@router.get("/alert-status")
@handle_errors
async def get_alert_status() -> Dict[str, Any]:
    """Check if there are pending documents to send (for alert)."""
    now = datetime.now(timezone.utc)
    current_month = now.month
    current_year = now.year
    
    # Previous month
    if current_month == 1:
        prev_month = 12
        prev_year = current_year - 1
    else:
        prev_month = current_month - 1
        prev_year = current_year
    
    # Check if we're within 2 days of the month end
    _, last_day = monthrange(prev_year, prev_month)
    deadline = datetime(current_year, current_month, 2, 23, 59, 59, tzinfo=timezone.utc)
    
    db = Database.get_db()
    
    # Check if prima nota was already sent for previous month
    prima_nota_sent = await db["commercialista_log"].find_one({
        "tipo": "prima_nota_cassa",
        "anno": prev_year,
        "mese": prev_month,
        "success": True
    })
    
    show_alert = now <= deadline and not prima_nota_sent
    
    mese_nome = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"][prev_month]
    
    return {
        "show_alert": show_alert,
        "mese_pendente": prev_month,
        "anno_pendente": prev_year,
        "mese_nome": mese_nome,
        "deadline": deadline.isoformat(),
        "prima_nota_inviata": prima_nota_sent is not None,
        "message": f"Ricordati di inviare la Prima Nota Cassa di {mese_nome} {prev_year} al commercialista!" if show_alert else None
    }


async def _get_prima_nota_banca_mensile(anno: int, mese: int, dal: Optional[str] = None,
                                        al: Optional[str] = None) -> Dict[str, Any]:
    """Prima Nota Banca del mese, stessa forma di get_prima_nota_cassa_mensile
    ma sulla collezione canonica prima_nota_banca (nessun fallback legacy:
    a differenza della cassa, per la banca esiste una sola collezione)."""
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)

    movements = await db["prima_nota_banca"].find(
        p.filtro("data"), {"_id": 0}).sort([("data", 1), ("categoria", 1)]).to_list(5000)

    totale_entrate = 0.0
    totale_uscite = 0.0
    for m in movements:
        tipo = (m.get("tipo") or "").lower()
        importo = float(m.get("importo") or 0)
        if tipo == "entrata":
            totale_entrate += abs(importo)
        else:
            totale_uscite += abs(importo)

    return {
        "movimenti": movements,
        "totale_entrate": round(totale_entrate, 2),
        "totale_uscite": round(totale_uscite, 2),
        "saldo": round(totale_entrate - totale_uscite, 2),
    }


async def _get_assegni_emessi_mensile(anno: int, mese: int, dal: Optional[str] = None,
                                      al: Optional[str] = None) -> list:
    """Assegni EMESSI (consegnati a un beneficiario, non i numeri ancora in
    bianco) con data di emissione nel mese: stato diverso da "vuoto"/
    "compilato" e data_emissione valorizzata nel periodo."""
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)

    return await db["assegni"].find({
        "stato": {"$nin": sorted(STATI_DISPONIBILI)},
        **p.filtro("data_emissione")
    }, {"_id": 0}).sort("data_emissione", 1).to_list(5000)


async def _get_fatture_estere_mensili(anno: int, mese: int, dal: Optional[str] = None,
                                      al: Optional[str] = None) -> list:
    """Fatture ESTERE ricevute via email nel mese (mai le fatture italiane,
    che arrivano sempre via SDI/XML): identificate dal source impostato da
    process_fattura_estera_pdf, l'unico punto che le crea (fatture_upload.py)."""
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)

    return await db["invoices"].find({
        "source": "email_gmail_estera",
        **p.filtro("invoice_date")
    }, {"_id": 0}).to_list(500)


@router.get("/completezza/{anno}/{mese}")
@handle_errors
async def completezza_pacchetto(anno: int, mese: int, dal: Optional[str] = None,
                                al: Optional[str] = None) -> Dict[str, Any]:
    """Chiusure RT, originali delle fatture ed estratto BPM del periodo."""
    from app.services.completezza_commercialista import completezza
    p = _intervallo(anno, mese, dal, al)
    return await completezza(Database.get_db(), anno, mese, dal=p.dal, al=p.al)


@router.get("/export-completo/{anno}/{mese}")
@handle_errors
async def export_dati_completi(anno: int, mese: int, dal: Optional[str] = None, al: Optional[str] = None):
    """
    Export mensile per commercialista in formato ZIP (richiesta utente
    15/07/2026, sostituisce la vecchia versione che includeva anche fatture/
    corrispettivi/riepilogo IVA/buste paga — dati che il commercialista
    riceve già da altre fonti, non da qui).

    Include SOLO:
    - Prima Nota Cassa e Prima Nota Banca del mese (CSV)
    - Assegni emessi nel mese (CSV)
    - PDF delle fatture ESTERE ricevute via email nel mese (allegati): le
      fatture italiane arrivano sempre via SDI/XML, non servono qui.
    - LEGGIMI_COMPLETEZZA.txt: chiusure RT, originali delle fatture ed estratto
      BPM del periodo, con quello che manca.
    """
    import zipfile
    import base64
    import csv
    from io import BytesIO, StringIO
    from fastapi.responses import StreamingResponse

    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)
    if dal or al:
        mese_str = f"{p.dal}_{p.al}"
    else:
        mese_str, _ = _periodo(anno, mese)

    zip_buffer = BytesIO()

    from app.services.completezza_commercialista import completezza, testo_leggimi
    try:
        leggimi = testo_leggimi(await completezza(db, anno, mese, dal=p.dal, al=p.al))
    except Exception as exc:  # noqa: BLE001 - il pacchetto si scarica comunque
        logger.warning("Completezza pacchetto %s non calcolata: %s: %s",
                       mese_str, type(exc).__name__, exc)
        leggimi = (f"Controllo di completezza non riuscito ({type(exc).__name__}): "
                   "chiusure RT, originali delle fatture ed estratto BPM vanno verificati a mano.\n")

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 0. Cosa manca, scritto in testa al pacchetto
        zf.writestr('LEGGIMI_COMPLETEZZA.txt', leggimi)

        # 1. PRIMA NOTA CASSA
        prima_nota_cassa = await get_prima_nota_cassa_mensile(anno, mese, dal, al)
        if prima_nota_cassa.get('movimenti'):
            csv_buffer = StringIO()
            writer = csv.writer(csv_buffer, delimiter=';')
            writer.writerow(['Data', 'Descrizione', 'Categoria', 'Entrata', 'Uscita', 'Tipo'])
            for m in prima_nota_cassa['movimenti']:
                importo = m.get('importo', 0)
                writer.writerow([
                    m.get('data', '')[:10],
                    m.get('descrizione', m.get('causale', '')),
                    m.get('categoria', ''),
                    importo if importo > 0 else '',
                    abs(importo) if importo < 0 else '',
                    m.get('tipo', '')
                ])
            zf.writestr(f'prima_nota_cassa_{mese_str}.csv', csv_buffer.getvalue())

        # 2. PRIMA NOTA BANCA
        prima_nota_banca = await _get_prima_nota_banca_mensile(anno, mese, dal, al)
        if prima_nota_banca.get('movimenti'):
            csv_buffer = StringIO()
            writer = csv.writer(csv_buffer, delimiter=';')
            writer.writerow(['Data', 'Descrizione', 'Categoria', 'Entrata', 'Uscita', 'Tipo'])
            for m in prima_nota_banca['movimenti']:
                importo = m.get('importo', 0)
                writer.writerow([
                    m.get('data', '')[:10],
                    m.get('descrizione', ''),
                    m.get('categoria', ''),
                    importo if importo > 0 else '',
                    abs(importo) if importo < 0 else '',
                    m.get('tipo', '')
                ])
            zf.writestr(f'prima_nota_banca_{mese_str}.csv', csv_buffer.getvalue())

        # 3. ASSEGNI EMESSI
        assegni = await _get_assegni_emessi_mensile(anno, mese, dal, al)
        if assegni:
            csv_buffer = StringIO()
            writer = csv.writer(csv_buffer, delimiter=';')
            writer.writerow(['Numero', 'Data Emissione', 'Beneficiario', 'Importo', 'Causale', 'Stato'])
            for a in assegni:
                writer.writerow([
                    a.get('numero', ''),
                    (a.get('data_emissione') or '')[:10],
                    a.get('beneficiario', ''),
                    a.get('importo', 0),
                    a.get('causale', ''),
                    a.get('stato', '')
                ])
            zf.writestr(f'assegni_emessi_{mese_str}.csv', csv_buffer.getvalue())

        # 4. FATTURE ESTERE (PDF allegati, non le fatture italiane via SDI)
        fatture_estere = await _get_fatture_estere_mensili(anno, mese, dal, al)
        for f in fatture_estere:
            documento_inbox_id = f.get("documento_inbox_id")
            if not documento_inbox_id:
                continue
            doc = await db["documents_inbox"].find_one(
                {"id": documento_inbox_id}, {"_id": 0, "pdf_data": 1, "filename": 1}
            )
            if not doc or not doc.get("pdf_data"):
                continue
            try:
                pdf_bytes = base64.b64decode(doc["pdf_data"])
            except Exception:
                continue
            nome_file = doc.get("filename") or f"{f.get('invoice_number', 'fattura')}.pdf"
            zf.writestr(f'fatture_estere/{nome_file}', pdf_bytes)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename=export_commercialista_{mese_str}.zip'}
    )


@router.get("/export-excel/{anno}/{mese}")
@handle_errors
async def export_excel_commercialista(anno: int, mese: int, dal: Optional[str] = None,
                                      al: Optional[str] = None):
    """
    Export Excel mensile per commercialista.
    Include fogli separati per: fatture, corrispettivi, prima nota, IVA.
    Senza dettaglio deducibilità come richiesto.
    """
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    from openpyxl.utils import get_column_letter
    from fastapi.responses import StreamingResponse
    
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)
    mese_nome = p.etichetta
    
    # Stili
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="3f5a4e", end_color="3f5a4e", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    money_format = '#,##0.00 €'
    
    wb = Workbook()
    
    # === FOGLIO 1: FATTURE ACQUISTO ===
    ws_fatture = wb.active
    ws_fatture.title = "Fatture Acquisto"
    
    from app.constants.fattura_attiva import FILTRO_FATTURA_ATTIVA

    # Solo fatture attive: le copie archiviate raddoppiavano i totali.
    fatture = await db["invoices"].find({
        **p.filtro("invoice_date"), **FILTRO_FATTURA_ATTIVA,
    }, {"_id": 0, "xml_raw": 0, "xml_content": 0}).sort("invoice_date", 1).to_list(10000)
    
    headers_fatture = ['Data', 'N. Fattura', 'Fornitore', 'P.IVA Fornitore', 'Categoria', 
                       'Imponibile', 'IVA', 'Totale', 'Pagamento', 'Conto']
    
    for col, header in enumerate(headers_fatture, 1):
        cell = ws_fatture.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
    
    tot_imponibile = 0
    tot_iva = 0
    tot_iva_detraibile = 0
    tot_fatture = 0
    
    for row, f in enumerate(fatture, 2):
        imponibile = float(f.get('total_amount', 0) or 0) - float(f.get('total_tax', 0) or 0)
        iva = float(f.get('total_tax', 0) or 0)
        totale = float(f.get('total_amount', 0) or 0)
        
        tot_imponibile += imponibile
        tot_iva += iva
        tot_iva_detraibile += float(f.get('iva_detraibile', 0) or 0)
        tot_fatture += totale
        
        values = [
            f.get('invoice_date', '')[:10],
            f.get('invoice_number', ''),
            f.get('supplier_name', ''),
            f.get('supplier_vat', ''),
            f.get('categoria_contabile', '').replace('_', ' ').title(),
            imponibile,
            iva,
            totale,
            f.get('payment_method', f.get('metodo_pagamento', '')),
            f.get('conto_costo_codice', '')
        ]
        
        for col, value in enumerate(values, 1):
            cell = ws_fatture.cell(row=row, column=col, value=value)
            cell.border = border
            if col in [6, 7, 8]:
                cell.number_format = money_format
    
    # Riga totali
    row_tot = len(fatture) + 2
    ws_fatture.cell(row=row_tot, column=5, value="TOTALI:").font = Font(bold=True)
    ws_fatture.cell(row=row_tot, column=6, value=tot_imponibile).number_format = money_format
    ws_fatture.cell(row=row_tot, column=7, value=tot_iva).number_format = money_format
    ws_fatture.cell(row=row_tot, column=8, value=tot_fatture).number_format = money_format
    for col in [6, 7, 8]:
        ws_fatture.cell(row=row_tot, column=col).font = Font(bold=True)
    
    # Larghezza colonne
    for col in range(1, 11):
        ws_fatture.column_dimensions[get_column_letter(col)].width = 15 if col not in [3] else 30
    
    # === FOGLIO 2: CORRISPETTIVI ===
    ws_corr = wb.create_sheet("Corrispettivi")
    
    corrispettivi = await db["corrispettivi"].find({
        **p.filtro("data"),
        "status": {"$nin": ["deleted", "archived"]},
        "entity_status": {"$ne": "deleted"},
    }, {"_id": 0}).sort("data", 1).to_list(10000)
    
    headers_corr = ['Data', 'Totale', 'Contante', 'Elettronico', 'Chiusura N.', 'Note']
    
    for col, header in enumerate(headers_corr, 1):
        cell = ws_corr.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
    
    tot_corr = 0
    tot_contante = 0
    tot_elettr = 0
    
    for row, c in enumerate(corrispettivi, 2):
        totale = float(c.get('totale', 0) or 0)
        # Il campo vero e' `pagato_contanti` (plurale): il singolare non
        # esiste sui corrispettivi XML e la colonna restava a zero.
        contante = float(
            c.get('pagato_contanti') or c.get('pagato_contante') or c.get('pagato_cassa') or 0)
        elettr = float(c.get('pagato_elettronico', 0) or 0)
        
        tot_corr += totale
        tot_contante += contante
        tot_elettr += elettr
        
        values = [
            c.get('data', '')[:10],
            totale,
            contante,
            elettr,
            c.get('numero_chiusura', ''),
            c.get('note', '')
        ]
        
        for col, value in enumerate(values, 1):
            cell = ws_corr.cell(row=row, column=col, value=value)
            cell.border = border
            if col in [2, 3, 4]:
                cell.number_format = money_format
    
    # Totali corrispettivi
    row_tot = len(corrispettivi) + 2
    ws_corr.cell(row=row_tot, column=1, value="TOTALI:").font = Font(bold=True)
    ws_corr.cell(row=row_tot, column=2, value=tot_corr).number_format = money_format
    ws_corr.cell(row=row_tot, column=3, value=tot_contante).number_format = money_format
    ws_corr.cell(row=row_tot, column=4, value=tot_elettr).number_format = money_format
    
    for col in range(1, 7):
        ws_corr.column_dimensions[get_column_letter(col)].width = 15
    
    # === FOGLIO 3: PRIMA NOTA CASSA ===
    ws_pn = wb.create_sheet("Prima Nota Cassa")
    
    # Ordinamento: prima per data, poi per categoria (Corrispettivi prima di POS)
    prima_nota = await db["prima_nota_cassa"].find({
        **p.filtro("data")
    }, {"_id": 0}).sort([("data", 1), ("categoria", 1)]).to_list(10000)
    
    headers_pn = ['Data', 'Descrizione', 'Categoria', 'Tipo', 'Importo']
    
    for col, header in enumerate(headers_pn, 1):
        cell = ws_pn.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
    
    tot_entrate = 0
    tot_uscite = 0
    
    for row, pn in enumerate(prima_nota, 2):
        importo = float(pn.get('importo', 0) or 0)
        tipo = pn.get('tipo', 'uscita')
        
        if tipo == 'entrata':
            tot_entrate += importo
        else:
            tot_uscite += importo
        
        values = [
            pn.get('data', '')[:10],
            pn.get('descrizione', ''),
            pn.get('categoria', '').replace('_', ' ').title(),
            tipo.upper(),
            importo
        ]
        
        for col, value in enumerate(values, 1):
            cell = ws_pn.cell(row=row, column=col, value=value)
            cell.border = border
            if col == 5:
                cell.number_format = money_format
    
    # Totali prima nota
    row_tot = len(prima_nota) + 2
    ws_pn.cell(row=row_tot, column=3, value="TOTALE ENTRATE:").font = Font(bold=True)
    ws_pn.cell(row=row_tot, column=5, value=tot_entrate).number_format = money_format
    ws_pn.cell(row=row_tot + 1, column=3, value="TOTALE USCITE:").font = Font(bold=True)
    ws_pn.cell(row=row_tot + 1, column=5, value=tot_uscite).number_format = money_format
    ws_pn.cell(row=row_tot + 2, column=3, value="SALDO:").font = Font(bold=True, color="0000FF")
    ws_pn.cell(row=row_tot + 2, column=5, value=tot_entrate - tot_uscite).number_format = money_format
    
    ws_pn.column_dimensions['B'].width = 40
    for col in [1, 3, 4, 5]:
        ws_pn.column_dimensions[get_column_letter(col)].width = 15
    
    # === FOGLIO 4: RIEPILOGO IVA ===
    ws_iva = wb.create_sheet("Riepilogo IVA")
    
    headers_iva = ['Voce', 'Importo']
    for col, header in enumerate(headers_iva, 1):
        cell = ws_iva.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
    
    # IVA vendite (dai corrispettivi - assumiamo 10%)
    iva_vendite = tot_corr * 0.10 / 1.10
    
    iva_data = [
        ('IVA a debito (vendite)', iva_vendite),
        ('IVA a credito (acquisti)', tot_iva_detraibile),
        ('', ''),
        ('SALDO IVA', iva_vendite - tot_iva_detraibile)
    ]
    
    for row, (voce, importo) in enumerate(iva_data, 2):
        ws_iva.cell(row=row, column=1, value=voce).border = border
        if importo != '':
            cell = ws_iva.cell(row=row, column=2, value=importo)
            cell.number_format = money_format
            cell.border = border
        if voce == 'SALDO IVA':
            ws_iva.cell(row=row, column=1).font = Font(bold=True)
            ws_iva.cell(row=row, column=2).font = Font(bold=True)
            if importo > 0:
                ws_iva.cell(row=row, column=2).font = Font(bold=True, color="FF0000")
    
    ws_iva.column_dimensions['A'].width = 30
    ws_iva.column_dimensions['B'].width = 20
    
    # === FOGLIO 5: RIEPILOGO GENERALE ===
    ws_riep = wb.create_sheet("Riepilogo")
    
    ws_riep.cell(row=1, column=1, value=f"RIEPILOGO {mese_nome.upper()} {anno}").font = Font(bold=True, size=14)
    ws_riep.merge_cells('A1:B1')
    
    riepilogo = [
        ('', ''),
        ('FATTURE ACQUISTO', ''),
        ('  Numero fatture', len(fatture)),
        ('  Totale imponibile', tot_imponibile),
        ('  Totale IVA', tot_iva),
        ('  Totale fatture', tot_fatture),
        ('', ''),
        ('CORRISPETTIVI', ''),
        ('  Giorni registrati', len(corrispettivi)),
        ('  Totale incassato', tot_corr),
        ('  di cui contante', tot_contante),
        ('  di cui elettronico', tot_elettr),
        ('', ''),
        ('PRIMA NOTA CASSA', ''),
        ('  Totale entrate', tot_entrate),
        ('  Totale uscite', tot_uscite),
        ('  Saldo cassa', tot_entrate - tot_uscite),
        ('', ''),
        ('IVA', ''),
        ('  IVA a debito', iva_vendite),
        ('  IVA a credito', tot_iva_detraibile),
        ('  Saldo IVA', iva_vendite - tot_iva_detraibile)
    ]
    
    for row, (voce, valore) in enumerate(riepilogo, 3):
        cell_voce = ws_riep.cell(row=row, column=1, value=voce)
        if valore != '' and not voce.startswith('  '):
            cell_voce.font = Font(bold=True)
        if valore != '':
            cell_val = ws_riep.cell(row=row, column=2, value=valore)
            if isinstance(valore, (int, float)):
                cell_val.number_format = money_format if isinstance(valore, float) else '0'
    
    ws_riep.column_dimensions['A'].width = 25
    ws_riep.column_dimensions['B'].width = 18
    
    # Genera file
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    filename = f"contabilita_{mese_nome.lower()}_{anno}.xlsx"
    
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )



# ============================================
# EXPORT SCHEDULATO AUTOMATICO
# ============================================

@router.post("/schedula-export")
@handle_errors
async def schedula_export_mensile(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Schedula o esegue immediatamente l'invio del report mensile al commercialista.
    
    Body:
    - anno: int
    - mese: int (1-12)
    - email: str (opzionale, usa default se non specificato)
    - immediato: bool (se True, invia subito invece di schedulare)
    """
    db = Database.get_db()
    
    anno = data.get("anno", datetime.now().year)
    mese = data.get("mese", datetime.now().month)
    email = data.get("email")
    immediato = data.get("immediato", True)
    
    # Recupera config
    config = await db["commercialista_config"].find_one({}, {"_id": 0})
    if not email:
        email = config.get("email") if config else DEFAULT_COMMERCIALISTA_EMAIL
    
    MESI_NOMI = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 
                 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
    mese_nome = MESI_NOMI[mese - 1]
    
    if immediato:
        try:
            import io
            from openpyxl import Workbook
            from openpyxl.styles import Font
            from datetime import timezone
            
            # Genera il report Excel
            _, ultimo_giorno = monthrange(anno, mese)
            data_inizio = f"{anno}-{mese:02d}-01"
            data_fine = f"{anno}-{mese:02d}-{ultimo_giorno:02d}"
            
            # Raccogli dati
            fatture = await db["invoices"].find({
                "data_ricezione": {"$gte": data_inizio, "$lte": data_fine}
            }, {"_id": 0}).to_list(1000)
            
            corrispettivi = await db["corrispettivi"].find({
                "data": {"$gte": data_inizio, "$lte": data_fine}
            }, {"_id": 0}).to_list(100)
            
            prima_nota = await db["prima_nota_cassa"].find({
                "data": {"$gte": data_inizio, "$lte": data_fine}
            }, {"_id": 0}).to_list(1000)
            
            # Crea Excel semplificato
            wb = Workbook()
            ws = wb.active
            ws.title = "Riepilogo"
            
            # Titolo
            ws['A1'] = f"REPORT MENSILE - {mese_nome} {anno}"
            ws['A1'].font = Font(bold=True, size=14)
            ws.merge_cells('A1:D1')
            
            # Statistiche
            tot_fatture = sum(float(f.get("totale", 0) or 0) for f in fatture)
            tot_corr = sum(float(c.get("totale", 0) or 0) for c in corrispettivi)
            entrate = sum(float(m.get("importo", 0) or 0) for m in prima_nota if m.get("tipo") == "entrata")
            uscite = sum(abs(float(m.get("importo", 0) or 0)) for m in prima_nota if m.get("tipo") == "uscita")
            
            stats = [
                ("", ""),
                ("FATTURE ACQUISTO", ""),
                ("  Numero fatture", len(fatture)),
                ("  Totale fatture", f"€ {tot_fatture:,.2f}"),
                ("", ""),
                ("CORRISPETTIVI", ""),
                ("  Giorni registrati", len(corrispettivi)),
                ("  Totale incassato", f"€ {tot_corr:,.2f}"),
                ("", ""),
                ("PRIMA NOTA", ""),
                ("  Entrate", f"€ {entrate:,.2f}"),
                ("  Uscite", f"€ {uscite:,.2f}"),
                ("  Saldo", f"€ {entrate - uscite:,.2f}"),
            ]
            
            for idx, (label, value) in enumerate(stats, 3):
                ws.cell(row=idx, column=1, value=label)
                ws.cell(row=idx, column=2, value=value)
            
            # Genera bytes
            output = io.BytesIO()
            wb.save(output)
            excel_bytes = output.getvalue()
            
            # Invia email
            subject = f"📊 Report Contabile {mese_nome} {anno} - Azienda in Cloud"
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <h2>📊 Report Mensile - {mese_nome} {anno}</h2>
                <p>In allegato il report contabile mensile con:</p>
                <ul>
                    <li><strong>Fatture acquisto:</strong> {len(fatture)} documenti (€ {tot_fatture:,.2f})</li>
                    <li><strong>Corrispettivi:</strong> {len(corrispettivi)} giorni (€ {tot_corr:,.2f})</li>
                    <li><strong>Prima Nota:</strong> Entrate € {entrate:,.2f} / Uscite € {uscite:,.2f}</li>
                </ul>
                <p style="color: #666; font-size: 12px;">
                    Report generato automaticamente da Azienda in Cloud ERP<br>
                    Data invio: {datetime.now(timezone.utc).strftime('%d-%m-%Y %H:%M')}
                </p>
            </body>
            </html>
            """
            
            filename = f"report_{mese_nome.lower()}_{anno}.xlsx"
            
            send_email_with_attachment(
                to_email=email,
                subject=subject,
                html_body=html_body,
                attachment_data=excel_bytes,
                attachment_name=filename
            )
            
            # Salva log
            log_export_doc = {
                "tipo": "report_mensile",
                "anno": anno,
                "mese": mese,
                "email": email,
                "inviato_at": datetime.now(timezone.utc).isoformat(),
                "statistiche": {
                    "fatture": len(fatture),
                    "corrispettivi": len(corrispettivi),
                    "prima_nota": len(prima_nota)
                }
            }
            await db["export_log"].insert_one(log_export_doc.copy())
            
            return {
                "success": True,
                "message": f"Report {mese_nome} {anno} inviato a {email}",
                "email": email,
                "statistiche": {
                    "fatture": len(fatture),
                    "tot_fatture": tot_fatture,
                    "corrispettivi": len(corrispettivi),
                    "entrate": entrate,
                    "uscite": uscite
                }
            }
            
        except Exception as e:
            logger.error(f"Errore invio report: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    else:
        # Schedula per il futuro (salva in DB)
        scheduled_doc = {
            "tipo": "report_mensile",
            "anno": anno,
            "mese": mese,
            "email": email,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending"
        }
        await db["scheduled_exports"].insert_one(scheduled_doc.copy())
        
        return {
            "success": True,
            "message": f"Export schedulato per {mese_nome} {anno}",
            "scheduled": True
        }


@router.get("/export-log")
@handle_errors
async def get_export_log(limit: int = 20) -> Dict[str, Any]:
    """Recupera lo storico degli export inviati."""
    db = Database.get_db()
    
    logs = await db["export_log"].find(
        {},
        {"_id": 0}
    ).sort("inviato_at", -1).limit(limit).to_list(limit)
    
    return {
        "logs": logs,
        "total": await db["export_log"].count_documents({})
    }


# ---------------------------------------------------------------------------
# Pacchetto da inviare: periodo, voci, un'unica email con tutti gli allegati
# ---------------------------------------------------------------------------

COLLEZIONE_INVII = "commercialista_invii"

# Tipo del vecchio registro `commercialista_log` -> voce del pacchetto.
_TIPO_LOG_VOCE = {"prima_nota_cassa": "prima_nota_cassa", "fatture_cassa": "fatture_cassa",
                  "carnet_assegni": "carnet_assegni"}


def _voci_richieste(voci: Any) -> List[str]:
    """Le voci scelte, nell'ordine della pagina. 422 se vuote o sconosciute."""
    if not isinstance(voci, list) or not voci:
        raise HTTPException(status_code=422, detail="Scegli almeno un documento da inviare")
    ignote = [v for v in voci if v not in pacchetto.VOCI]
    if ignote:
        raise HTTPException(status_code=422, detail=f"Documento sconosciuto: {ignote[0]}")
    return [v for v in pacchetto.VOCI if v in voci]


def _opzioni(carnet_ids: Any = None, presenze_rinvia: bool = False) -> Dict[str, Any]:
    if isinstance(carnet_ids, str):
        carnet_ids = [c.strip() for c in carnet_ids.split(",") if c.strip()]
    return {"carnet_ids": [str(c) for c in (carnet_ids or [])], "presenze_rinvia": bool(presenze_rinvia)}


async def _destinatario(db, esplicito: Optional[str] = None) -> str:
    if esplicito and str(esplicito).strip():
        return str(esplicito).strip()
    config = await db["commercialista_config"].find_one({}, {"_id": 0, "email": 1}) or {}
    return config.get("email") or DEFAULT_COMMERCIALISTA_EMAIL


async def _ultimi_invii(db, p: pacchetto.Periodo) -> Dict[str, Dict[str, Any]]:
    """L'ultimo invio per voce il cui periodo tocca quello scelto (registro nuovo e vecchio)."""
    ultimi: Dict[str, Dict[str, Any]] = {}

    def _tiene(voce: str, quando: str, dal: str, al: str, destinatario: str) -> None:
        if not (dal <= p.al and al >= p.dal):
            return
        if voce not in ultimi or quando > ultimi[voce]["data"]:
            ultimi[voce] = {"data": quando, "dal": dal, "al": al, "destinatario": destinatario}

    invii = await db[COLLEZIONE_INVII].find(
        {"esito": "inviato"}, {"_id": 0, "created_at": 1, "dal": 1, "al": 1, "destinatario": 1,
                               "voci_inviate": 1}).sort([("created_at", -1)]).to_list(300)
    for i in invii:
        for voce in i.get("voci_inviate") or []:
            _tiene(voce, str(i.get("created_at") or ""), str(i.get("dal") or ""), str(i.get("al") or ""),
                   str(i.get("destinatario") or ""))
    vecchi = await db["commercialista_log"].find(
        {"success": True}, {"_id": 0, "tipo": 1, "anno": 1, "mese": 1, "email": 1, "data_invio": 1}
    ).sort([("data_invio", -1)]).to_list(200)
    for v in vecchi:
        voce = _TIPO_LOG_VOCE.get(v.get("tipo"))
        if not voce or not v.get("anno"):
            continue
        try:
            periodo_log = pacchetto.intervallo_periodo(int(v["anno"]), int(v.get("mese") or 0))
        except (TypeError, ValueError):
            continue
        _tiene(voce, str(v.get("data_invio") or ""), periodo_log.dal, periodo_log.al, str(v.get("email") or ""))
    return ultimi


@router.get("/pacchetto")
@handle_errors
async def get_pacchetto(anno: Optional[int] = None, mese: Optional[int] = None, dal: Optional[str] = None,
                        al: Optional[str] = None, carnet_ids: Optional[str] = None) -> Dict[str, Any]:
    """Stato di ogni documento del pacchetto per il periodo: conteggio, totale, pronto/incompleto/vuoto."""
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)
    voci = await pacchetto.costruisci_voci(db, list(pacchetto.VOCI), p, _opzioni(carnet_ids))
    ultimi = await _ultimi_invii(db, p)
    esito = []
    for v in voci:
        riga = pacchetto.riassunto(v)
        riga["ultimo_invio"] = ultimi.get(v["voce"])
        esito.append(riga)
    return {"periodo": {"dal": p.dal, "al": p.al, "etichetta": p.etichetta},
            "destinatario": await _destinatario(db), "smtp_configurato": smtp_configurato(),
            "voci": esito}


@router.get("/voce/{voce}")
@handle_errors
async def get_voce_pacchetto(voce: str, anno: Optional[int] = None, mese: Optional[int] = None,
                             dal: Optional[str] = None, al: Optional[str] = None,
                             carnet_ids: Optional[str] = None) -> Dict[str, Any]:
    """Il documento intero (sezioni con colonne e righe) di una voce del pacchetto."""
    _voci_richieste([voce])
    p = _intervallo(anno, mese, dal, al)
    return await pacchetto.costruisci_voce(Database.get_db(), voce, p, _opzioni(carnet_ids))


@router.get("/voce/{voce}/scarica")
@handle_errors
async def scarica_voce_pacchetto(voce: str, anno: Optional[int] = None, mese: Optional[int] = None,
                                 dal: Optional[str] = None, al: Optional[str] = None,
                                 carnet_ids: Optional[str] = None, rinvia: bool = False):
    """PDF di una voce (le presenze: PDF e CSV di HR, in ZIP se piu' mesi)."""
    import io
    import zipfile
    from fastapi.responses import Response

    _voci_richieste([voce])
    db = Database.get_db()
    p = _intervallo(anno, mese, dal, al)
    opz = _opzioni(carnet_ids, rinvia)
    costruita = await pacchetto.costruisci_voce(db, voce, p, opz)
    if costruita["stato"] in (pacchetto.STATO_NON_DISPONIBILE, pacchetto.STATO_VUOTO):
        raise HTTPException(status_code=404, detail=costruita["motivo"] or "Nessun dato nel periodo")
    if voce == "presenze":
        opz["presenze_rinvia"] = True  # scaricare non e' inviare: si scarica anche cio' che e' gia' partito
    allegati, _ = await pacchetto.allegati_voce(db, costruita, p, opz)
    if not allegati:
        raise HTTPException(status_code=404, detail="Nessun allegato da scaricare")
    if len(allegati) == 1:
        dati, principale, sotto, nome = allegati[0]
        return Response(content=dati, media_type=f"{principale}/{sotto}",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for dati, _principale, _sotto, nome in allegati:
            zf.writestr(nome, dati)
    return Response(content=buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="{pacchetto.nome_file(voce, p, "zip")}"'})


def _corpo_email(p: pacchetto.Periodo, esiti: List[Dict[str, Any]]) -> str:
    """Corpo HTML del pacchetto: periodo e, per ogni allegato, righe e totale."""
    from html import escape

    righe = "".join(
        f'<tr><td style="padding:6px 8px;border-bottom:1px solid #e6e3d9">{escape(e["titolo"])}</td>'
        f'<td style="padding:6px 8px;border-bottom:1px solid #e6e3d9;text-align:right">{e["conteggio"]}</td>'
        f'<td style="padding:6px 8px;border-bottom:1px solid #e6e3d9;text-align:right">'
        f'{escape(e["totale"] or "")}</td>'
        f'<td style="padding:6px 8px;border-bottom:1px solid #e6e3d9">{escape(e.get("nota") or "")}</td></tr>'
        for e in esiti if e["esito"] == "allegata")
    return (
        '<html><body style="font-family:Arial,sans-serif;background:#faf9f5;color:#141413;padding:20px">'
        '<div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e6e3d9">'
        '<div style="background:#3f5a4e;color:#ffffff;padding:16px 20px">'
        '<h2 style="margin:0">Documenti per il commercialista</h2>'
        f'<p style="margin:6px 0 0 0">Periodo: {escape(p.etichetta)} '
        f'({escape(pacchetto.it_data(p.dal))} - {escape(pacchetto.it_data(p.al))})</p></div>'
        '<div style="padding:20px"><p>Gentile Commercialista, in allegato trova i documenti del periodo.</p>'
        '<table style="width:100%;border-collapse:collapse;font-size:14px">'
        '<tr style="text-align:left;color:#7a776e"><th style="padding:6px 8px">Documento</th>'
        '<th style="padding:6px 8px;text-align:right">Righe</th>'
        '<th style="padding:6px 8px;text-align:right">Totale</th><th style="padding:6px 8px">Note</th></tr>'
        f'{righe}</table>'
        '<p style="color:#7a776e;font-size:13px">Il dettaglio di ogni documento e\' nel PDF allegato.</p></div>'
        '<div style="background:#f6f4ee;padding:12px;text-align:center;font-size:12px;color:#7a776e">'
        'Ceraldi Group S.R.L. - messaggio generato dal gestionale</div></div></body></html>'
    )


@router.post("/invia-pacchetto")
@handle_errors
async def invia_pacchetto(data: Dict[str, Any] = Body(...),
                          _admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Una sola email al commercialista con i documenti scelti, costruiti dal server.

    Corpo: `{dal, al}` (oppure `{anno, mese}`), `voci: [...]`, opzionali `carnet_ids`,
    `presenze_rinvia`, `email`. Ogni voce vuota o non disponibile e' saltata e lo dice; le presenze
    gia' inviate si rimandano solo con `presenze_rinvia`. Registro: `commercialista_invii`.
    """
    import asyncio
    import uuid

    from app.hr.services.email_smtp import credenziali_smtp, invia_email

    voci = _voci_richieste(data.get("voci"))
    db = Database.get_db()
    p = _intervallo(data.get("anno"), data.get("mese"), data.get("dal"), data.get("al"))
    opz = _opzioni(data.get("carnet_ids"), data.get("presenze_rinvia"))
    destinatario = await _destinatario(db, data.get("email"))
    if credenziali_smtp() is None:
        raise HTTPException(status_code=503, detail="Email non configurata: mancano le credenziali SMTP")

    costruite = await pacchetto.costruisci_voci(db, voci, p, opz)
    allegati: List[Any] = []
    esiti: List[Dict[str, Any]] = []
    presenze_mesi: List[Dict[str, Any]] = []
    for v in costruite:
        base = {"voce": v["voce"], "titolo": v["titolo"], "stato": v["stato"], "conteggio": v["conteggio"],
                "totale": v["totale"]}
        if v["stato"] in (pacchetto.STATO_VUOTO, pacchetto.STATO_NON_DISPONIBILE):
            esiti.append({**base, "esito": "saltata", "motivo": v["motivo"] or "Nessun dato nel periodo"})
            continue
        if v["voce"] == "presenze" and v["stato"] == pacchetto.STATO_GIA_INVIATO and not opz["presenze_rinvia"]:
            esiti.append({**base, "esito": "saltata",
                          "motivo": f"{v['motivo']}: per rimandarle serve la conferma «Rinvia»"})
            continue
        voce_allegati, extra = await pacchetto.allegati_voce(db, v, p, opz)
        if not voce_allegati:
            esiti.append({**base, "esito": "saltata", "motivo": "Nessun allegato da inviare"})
            continue
        allegati.extend(voce_allegati)
        presenze_mesi.extend(extra.get("presenze_mesi") or [])
        esiti.append({**base, "esito": "allegata", "file": [a[3] for a in voce_allegati],
                      "nota": v["motivo"] if v["stato"] == pacchetto.STATO_INCOMPLETO else ""})

    if not allegati:
        raise HTTPException(status_code=422, detail="Nessun documento da inviare: le voci scelte sono vuote "
                            "o non disponibili per il periodo")

    ora = datetime.now(timezone.utc).isoformat()
    registro = {"id": str(uuid.uuid4()), "dal": p.dal, "al": p.al, "periodo": p.etichetta,
                "voci": esiti, "voci_inviate": [e["voce"] for e in esiti if e["esito"] == "allegata"],
                "destinatario": destinatario, "created_at": ora}
    try:
        await asyncio.to_thread(
            invia_email, destinatario, f"Documenti per il commercialista - {p.etichetta}",
            _corpo_email(p, esiti), allegati, True)
    except Exception as exc:  # noqa: BLE001 - l'errore si registra e si riporta col solo nome del tipo
        logger.error("Invio del pacchetto a %s non riuscito: %s", destinatario, type(exc).__name__)
        await db[COLLEZIONE_INVII].insert_one({**registro, "esito": "errore", "errore": type(exc).__name__,
                                               "voci_inviate": []})
        raise HTTPException(status_code=502, detail=f"Invio email non riuscito ({type(exc).__name__})") from exc

    await db[COLLEZIONE_INVII].insert_one({**registro, "esito": "inviato"})
    # Registro unico delle presenze (lo legge anche la pagina Presenze di HR).
    if presenze_mesi:
        from app.hr.services.presenze_consulente import registra_invio

        for m in presenze_mesi:
            await registra_invio(m["anno"], m["mese"], destinatario, n_dipendenti=m["n_dipendenti"],
                                 con_pdf=True, origine="erp")
    # L'avviso «Prima Nota Cassa da inviare» legge ancora il vecchio registro: un mese intero lo chiude.
    if "prima_nota_cassa" in registro["voci_inviate"] and p.dal[:7] == p.al[:7] and p.dal[8:] == "01" \
            and p.al == pacchetto.intervallo_periodo(int(p.dal[:4]), int(p.dal[5:7])).al:
        await db["commercialista_log"].insert_one({
            "tipo": "prima_nota_cassa", "anno": int(p.dal[:4]), "mese": int(p.dal[5:7]),
            "email": destinatario, "data_invio": ora, "success": True, "note": "Inviata col pacchetto"})
    return {"success": True, "destinatario": destinatario, "periodo": p.etichetta, "allegati": len(allegati),
            "esiti": esiti, "invio_id": registro["id"],
            "message": f"{len(allegati)} allegati inviati a {destinatario}"}


@router.get("/invii")
@handle_errors
async def get_invii_pacchetto(limit: int = 30) -> Dict[str, Any]:
    """Gli ultimi invii del pacchetto (riusciti e falliti), dal piu' recente."""
    db = Database.get_db()
    limit = max(1, min(int(limit), 100))
    invii = await db[COLLEZIONE_INVII].find({}, {"_id": 0}).sort([("created_at", -1)]).to_list(limit)
    return {"invii": invii, "totale": len(invii)}
