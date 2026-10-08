"""
Servizio Notifiche Telegram
============================

Invia notifiche push al telefono quando:
- Arrivano nuovi documenti dalla posta
- Vengono processate nuove fatture
- Ci sono operazioni da confermare
- Errori critici nel sistema

Configurazione in .env:
    TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxx
    TELEGRAM_CHAT_ID=123456789
"""

import os
import logging
import httpx
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Configurazione
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# URL API Telegram
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def is_configured() -> bool:
    """Verifica se Telegram è configurato."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


async def send_notification(
    message: str,
    parse_mode: str = "HTML",
    disable_notification: bool = False
) -> Dict[str, Any]:
    """
    Invia una notifica Telegram.
    
    Args:
        message: Testo del messaggio (supporta HTML)
        parse_mode: "HTML" o "Markdown"
        disable_notification: Se True, notifica silenziosa
    
    Returns:
        Dict con risultato invio
    """
    if not is_configured():
        logger.debug("Telegram non configurato, notifica saltata")
        return {"success": False, "error": "Telegram non configurato"}
    
    try:
        url = TELEGRAM_API_URL.format(token=TELEGRAM_BOT_TOKEN)
        
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            result = response.json()
            
            if result.get("ok"):
                logger.info("📱 Notifica Telegram inviata")
                return {"success": True, "message_id": result.get("result", {}).get("message_id")}
            else:
                logger.error(f"Errore Telegram: {result.get('description')}")
                return {"success": False, "error": result.get("description")}
                
    except Exception as e:
        logger.error(f"Errore invio Telegram: {e}")
        return {"success": False, "error": str(e)}


# ============== NOTIFICHE SPECIFICHE ==============

async def notifica_nuovi_documenti(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Notifica quando arrivano nuovi documenti dalla posta.
    """
    nuovi = stats.get("new_documents", 0)
    if nuovi == 0:
        return {"success": True, "skipped": "Nessun nuovo documento"}
    
    # Costruisci messaggio
    now = datetime.now().strftime("%H:%M")
    
    message = f"""📬 <b>Nuovi Documenti</b> ({now})

📄 <b>{nuovi}</b> nuovi documenti scaricati

"""
    
    # Dettagli per categoria se disponibili
    by_category = stats.get("by_category", {})
    if by_category:
        for cat, count in by_category.items():
            if count > 0:
                emoji = {
                    "f24": "📋",
                    "fattura": "🧾", 
                    "busta_paga": "💰",
                    "estratto_conto": "🏦",
                    "altro": "📄"
                }.get(cat, "📄")
                message += f"{emoji} {cat}: {count}\n"
    
    # Aggiungi info Aruba se presente
    aruba_nuove = stats.get("aruba_new", 0)
    if aruba_nuove > 0:
        message += f"\n🔔 <b>{aruba_nuove}</b> nuove fatture da Aruba (da confermare)"
    
    return await send_notification(message)


async def notifica_fatture_aruba(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Notifica quando arrivano notifiche fatture da Aruba.
    """
    nuove = stats.get("new_invoices", 0)
    if nuove == 0:
        return {"success": True, "skipped": "Nessuna nuova fattura Aruba"}
    
    now = datetime.now().strftime("%H:%M")
    totale_importo = stats.get("total_amount", 0)
    
    message = f"""🧾 <b>Nuove Fatture Aruba</b> ({now})

📥 <b>{nuove}</b> fatture in attesa di conferma
💶 Totale: <b>€ {totale_importo:,.2f}</b>

👉 Apri l'app per confermare Cassa/Banca"""
    
    return await send_notification(message)


async def notifica_operazione_confermata(
    operazione: Dict[str, Any],
    metodo: str
) -> Dict[str, Any]:
    """
    Notifica quando viene confermata un'operazione.
    """
    fornitore = operazione.get("fornitore", "N/A")
    importo = operazione.get("importo", 0)
    numero = operazione.get("numero_fattura", "N/A")
    
    emoji_metodo = "💵" if metodo == "cassa" else "🏦"
    
    message = f"""✅ <b>Operazione Confermata</b>

{emoji_metodo} Metodo: <b>{metodo.upper()}</b>
🏢 Fornitore: {fornitore}
📄 Fattura: {numero}
💶 Importo: <b>€ {importo:,.2f}</b>"""
    
    return await send_notification(message, disable_notification=True)


async def notifica_fattura_xml_caricata(
    fattura: Dict[str, Any],
    automazioni: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Notifica quando viene caricata una fattura XML.
    """
    fornitore = fattura.get("supplier_name", "N/A")
    numero = fattura.get("invoice_number", "N/A")
    importo = fattura.get("total_amount", 0)
    
    message = f"""📥 <b>Fattura XML Caricata</b>

🏢 {fornitore}
📄 N° {numero}
💶 € {importo:,.2f}"""
    
    # Info automazioni
    if automazioni:
        mag = automazioni.get("magazzino", {})
        op = automazioni.get("operazione", {})

        if mag.get("products_updated", 0) > 0:
            message += "\n📦 Magazzino aggiornato"
        if op.get("operazione_completata"):
            message += "\n✅ Operazione completata automaticamente"
    
    return await send_notification(message, disable_notification=True)


async def notifica_errore_critico(
    errore: str,
    contesto: str = None
) -> Dict[str, Any]:
    """
    Notifica per errori critici del sistema.
    """
    now = datetime.now().strftime("%H:%M")
    
    message = f"""⚠️ <b>ERRORE SISTEMA</b> ({now})

❌ {errore}"""
    
    if contesto:
        message += f"\n\n📍 Contesto: {contesto}"
    
    return await send_notification(message)


async def notifica_sync_completato(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Notifica riepilogo sync automatico (solo se ci sono novità).
    """
    email_sync = results.get("email_sync", {})
    aruba_sync = results.get("aruba_sync", {})
    
    nuovi_doc = email_sync.get("new_documents", 0)
    aruba_stats = aruba_sync.get("stats", {})
    nuove_aruba = aruba_stats.get("new_invoices", 0)
    
    # Se non c'è nulla di nuovo, non notificare
    if nuovi_doc == 0 and nuove_aruba == 0:
        return {"success": True, "skipped": "Nessuna novità"}
    
    now = datetime.now().strftime("%H:%M")
    
    message = f"""🔄 <b>Sync Completato</b> ({now})

"""
    
    if nuovi_doc > 0:
        message += f"📬 {nuovi_doc} nuovi documenti\n"
    
    if nuove_aruba > 0:
        message += f"🧾 {nuove_aruba} nuove fatture Aruba\n"
        message += "👉 <i>Da confermare Cassa/Banca</i>"
    
    return await send_notification(message)


# ============== TEST ==============

async def test_connection() -> Dict[str, Any]:
    """
    Testa la connessione Telegram inviando un messaggio di test.
    """
    if not is_configured():
        return {
            "success": False,
            "configured": False,
            "error": "Configura TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID in .env"
        }
    
    message = """✅ <b>Connessione OK!</b>

🤖 Bot configurato correttamente
📱 Riceverai notifiche per:
• Nuovi documenti email
• Fatture Aruba da confermare
• Aggiornamenti magazzino

<i>Sistema ERP Azienda in Cloud</i>"""
    
    result = await send_notification(message)
    result["configured"] = True
    
    return result
