"""
Servizio Notifiche Scadenze F24 - Push Alert Proattivi

Controlla giornalmente le scadenze F24 imminenti e invia:
- Alert via Telegram (immediato)
- Alert via Email (riepilogo)
- Salva notifiche nel DB per il frontend (badge + campanella)

Livelli di urgenza:
- CRITICA: scadenza oggi o scaduta
- ALTA: scadenza entro 3 giorni
- MEDIA: scadenza entro 7 giorni
- BASSA: scadenza entro 15 giorni
"""

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List, Optional
import uuid

from app.database import Database

logger = logging.getLogger(__name__)

# Costanti
COLLECTION_F24 = "f24_unificato"
COLLECTION_ALERT = "alert_scadenze_f24"
COLLECTION_NOTIFICHE = "notifiche_scadenze"


def _calcola_urgenza(data_scadenza: date) -> Dict[str, Any]:
    """Calcola urgenza e giorni rimanenti per una scadenza."""
    oggi = date.today()
    giorni = (data_scadenza - oggi).days
    
    if giorni < 0:
        return {"livello": "SCADUTA", "giorni": giorni, "colore": "#7f1d1d", "emoji": "🚨"}
    elif giorni == 0:
        return {"livello": "CRITICA", "giorni": 0, "colore": "#dc2626", "emoji": "🔴"}
    elif giorni <= 3:
        return {"livello": "ALTA", "giorni": giorni, "colore": "#ea580c", "emoji": "🟠"}
    elif giorni <= 7:
        return {"livello": "MEDIA", "giorni": giorni, "colore": "#ca8a04", "emoji": "🟡"}
    elif giorni <= 15:
        return {"livello": "BASSA", "giorni": giorni, "colore": "#2563eb", "emoji": "🔵"}
    else:
        return {"livello": "OK", "giorni": giorni, "colore": "#16a34a", "emoji": "✅"}


def _parse_data_scadenza(f24: Dict) -> Optional[date]:
    """Estrae la data di scadenza da un F24."""
    # Prova vari campi
    for campo in ["scadenza", "data_scadenza", "data_versamento", "scadenza_stimata"]:
        val = f24.get(campo)
        if val:
            try:
                if isinstance(val, date):
                    return val
                if isinstance(val, datetime):
                    return val.date()
                if isinstance(val, str) and len(val) >= 10:
                    return datetime.strptime(val[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
    
    # Se non c'è data scadenza esplicita, usa il periodo
    periodo = f24.get("periodo", "")
    if periodo:
        try:
            # Formato: "01/2026" o "2026-01"
            if "/" in periodo:
                parts = periodo.split("/")
                mese = int(parts[0])
                anno = int(parts[1])
            elif "-" in periodo:
                parts = periodo.split("-")
                anno = int(parts[0])
                mese = int(parts[1])
            else:
                return None
            
            # Scadenza F24: 16 del mese successivo
            mese_scadenza = mese + 1
            anno_scadenza = anno
            if mese_scadenza > 12:
                mese_scadenza = 1
                anno_scadenza += 1
            
            return date(anno_scadenza, mese_scadenza, 16)
        except (ValueError, TypeError, IndexError):
            pass
    
    return None


async def controlla_scadenze_f24() -> Dict[str, Any]:
    """
    Controlla tutte le scadenze F24 e genera alert per quelle imminenti.
    Ritorna un riepilogo delle scadenze trovate.
    """
    db = Database.get_db()
    oggi = date.today()
    limite = oggi + timedelta(days=15)
    
    # Trova F24 non pagati
    f24_list = await db[COLLECTION_F24].find(
        {
            "stato": {"$nin": ["pagato", "annullato", "deleted"]},
        },
        {"_id": 0}
    ).to_list(500)
    
    scadenze_imminenti = []
    scadenze_scadute = []
    alert_generati = 0
    
    for f24 in f24_list:
        data_scadenza = _parse_data_scadenza(f24)
        if not data_scadenza:
            continue
        
        # Solo scadenze entro 15 giorni o già scadute (ma non oltre 30 giorni fa)
        if data_scadenza > limite:
            continue
        if data_scadenza < oggi - timedelta(days=30):
            continue
        
        urgenza = _calcola_urgenza(data_scadenza)
        importo = float(f24.get("importo_totale", 0) or f24.get("totale", 0) or 0)
        
        alert_data = {
            "f24_id": f24.get("id", str(uuid.uuid4())),
            "tipo": "SCADENZA_F24",
            "livello": urgenza["livello"],
            "giorni_rimanenti": urgenza["giorni"],
            "data_scadenza": data_scadenza.isoformat(),
            "importo": importo,
            "periodo": f24.get("periodo", ""),
            "descrizione": f24.get("descrizione") or f"F24 {f24.get('periodo', '')}",
            "codice_tributo": f24.get("codice_tributo", ""),
            "emoji": urgenza["emoji"],
            "colore": urgenza["colore"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "letto": False,
            "notificato_email": False,
            "notificato_telegram": False
        }
        
        if urgenza["giorni"] < 0:
            scadenze_scadute.append(alert_data)
        else:
            scadenze_imminenti.append(alert_data)
        
        # Salva/aggiorna alert nel DB (upsert per evitare duplicati)
        await db[COLLECTION_ALERT].update_one(
            {"f24_id": alert_data["f24_id"], "tipo": "SCADENZA_F24"},
            {"$set": alert_data},
            upsert=True
        )
        alert_generati += 1
    
    # Ordina per urgenza
    scadenze_imminenti.sort(key=lambda x: x["giorni_rimanenti"])
    scadenze_scadute.sort(key=lambda x: x["giorni_rimanenti"])
    
    return {
        "data_controllo": oggi.isoformat(),
        "scadenze_imminenti": scadenze_imminenti,
        "scadenze_scadute": scadenze_scadute,
        "totale_alert": alert_generati,
        "importo_totale_imminente": round(sum(s["importo"] for s in scadenze_imminenti), 2),
        "importo_totale_scaduto": round(sum(s["importo"] for s in scadenze_scadute), 2),
    }


async def invia_notifiche_scadenze() -> Dict[str, Any]:
    """
    Invia notifiche push (Telegram + Email) per scadenze F24 imminenti.
    Chiamata dal scheduler giornaliero.
    """
    db = Database.get_db()
    
    # Prima controlla le scadenze
    risultato = await controlla_scadenze_f24()
    
    tutte_scadenze = risultato["scadenze_scadute"] + risultato["scadenze_imminenti"]
    
    if not tutte_scadenze:
        logger.info("📅 [F24] Nessuna scadenza imminente")
        return {"notifiche_inviate": 0, "messaggio": "Nessuna scadenza imminente"}
    
    # Filtra solo quelle non ancora notificate oggi
    da_notificare = [s for s in tutte_scadenze if s["livello"] in ["SCADUTA", "CRITICA", "ALTA", "MEDIA"]]
    
    if not da_notificare:
        return {"notifiche_inviate": 0, "messaggio": "Tutte le scadenze già notificate o non urgenti"}
    
    notifiche_telegram = 0
    notifiche_email = 0
    
    # === TELEGRAM ===
    try:
        from app.services.telegram_notifications import is_configured, send_notification
        
        if is_configured():
            # Componi messaggio Telegram
            linee = ["📅 *SCADENZE F24 IN ARRIVO*\n"]
            
            for s in da_notificare:
                giorni = s["giorni_rimanenti"]
                importo = s["importo"]
                desc = s["descrizione"][:50]
                emoji = s["emoji"]
                
                if giorni < 0:
                    tempo = f"⚠️ SCADUTO da {abs(giorni)} giorni!"
                elif giorni == 0:
                    tempo = "🚨 SCADE OGGI!"
                elif giorni == 1:
                    tempo = "⏰ Scade DOMANI"
                else:
                    tempo = f"📆 Scade tra {giorni} giorni ({s['data_scadenza']})"
                
                linee.append(f"{emoji} *{desc}*")
                linee.append(f"   💰 €{importo:,.2f} - {tempo}")
                linee.append("")
            
            totale = sum(s["importo"] for s in da_notificare)
            linee.append(f"💰 *Totale da versare: €{totale:,.2f}*")
            linee.append(f"\n👉 Vai alla dashboard F24 per dettagli")
            
            messaggio = "\n".join(linee)
            
            await send_notification(messaggio)
            notifiche_telegram = len(da_notificare)
            logger.info(f"📱 [F24] Notifica Telegram inviata: {notifiche_telegram} scadenze")
    except Exception as e:
        logger.warning(f"📱 [F24] Errore notifica Telegram: {e}")
    
    # === EMAIL ===
    try:
        from app.services.email_service import EmailService
        
        email_service = EmailService()
        if email_service.is_configured:
            # Componi email HTML
            html = _build_email_scadenze_html(da_notificare)
            
            # Prendi email destinatario dalla config
            config = await db["configurazioni"].find_one(
                {"tipo": "notifiche_email"},
                {"_id": 0}
            )
            destinatario = None
            if config:
                destinatario = config.get("email_notifiche") or config.get("email")
            
            if not destinatario:
                # Prova con email admin
                admin = await db["users"].find_one({"role": "admin"}, {"email": 1})
                if admin:
                    destinatario = admin.get("email")
            
            if destinatario:
                n_scadenze = len(da_notificare)
                urgenti = len([s for s in da_notificare if s["livello"] in ["SCADUTA", "CRITICA"]])
                
                subject = f"⚠️ {n_scadenze} Scadenze F24"
                if urgenti > 0:
                    subject = f"🚨 {urgenti} F24 URGENTI + {n_scadenze - urgenti} in scadenza"
                
                sent = await email_service._send_email(destinatario, subject, html)
                if sent:
                    notifiche_email = len(da_notificare)
                    logger.info(f"📧 [F24] Email inviata a {destinatario}: {notifiche_email} scadenze")
    except Exception as e:
        logger.warning(f"📧 [F24] Errore notifica email: {e}")
    
    # Segna come notificate
    for s in da_notificare:
        update_fields = {}
        if notifiche_telegram > 0:
            update_fields["notificato_telegram"] = True
            update_fields["data_notifica_telegram"] = datetime.now(timezone.utc).isoformat()
        if notifiche_email > 0:
            update_fields["notificato_email"] = True
            update_fields["data_notifica_email"] = datetime.now(timezone.utc).isoformat()
        
        if update_fields:
            await db[COLLECTION_ALERT].update_one(
                {"f24_id": s["f24_id"], "tipo": "SCADENZA_F24"},
                {"$set": update_fields}
            )
    
    # Salva anche come notifiche generiche per il frontend (campanella)
    for s in da_notificare:
        if s["livello"] in ["SCADUTA", "CRITICA", "ALTA"]:
            await db[COLLECTION_NOTIFICHE].update_one(
                {"f24_id": s["f24_id"], "tipo": "SCADENZA_F24"},
                {"$set": {
                    "id": str(uuid.uuid4()),
                    "f24_id": s["f24_id"],
                    "tipo": "SCADENZA_F24",
                    "data_scadenza": s["data_scadenza"],
                    "descrizione": f"{s['emoji']} F24 {s['descrizione']} - €{s['importo']:,.2f}",
                    "importo": s["importo"],
                    "priorita": s["livello"].lower(),
                    "completata": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
    
    return {
        "notifiche_telegram": notifiche_telegram,
        "notifiche_email": notifiche_email,
        "scadenze_notificate": len(da_notificare),
        "dettaglio": [
            {
                "descrizione": s["descrizione"],
                "importo": s["importo"],
                "giorni": s["giorni_rimanenti"],
                "livello": s["livello"]
            }
            for s in da_notificare
        ]
    }


def _build_email_scadenze_html(scadenze: List[Dict]) -> str:
    """Costruisce email HTML con le scadenze F24."""
    
    righe = ""
    for s in scadenze:
        colore_bg = "#fff5f5" if s["livello"] in ["SCADUTA", "CRITICA"] else "#fffbeb" if s["livello"] == "ALTA" else "#f0fdf4"
        colore_testo = s["colore"]
        
        giorni = s["giorni_rimanenti"]
        if giorni < 0:
            tempo = f"<strong style='color:#991b1b'>SCADUTO da {abs(giorni)} giorni</strong>"
        elif giorni == 0:
            tempo = "<strong style='color:#dc2626'>SCADE OGGI</strong>"
        elif giorni == 1:
            tempo = "<strong style='color:#ea580c'>Scade DOMANI</strong>"
        else:
            tempo = f"Scade tra <strong>{giorni} giorni</strong> ({s['data_scadenza']})"
        
        righe += f"""
        <tr style="background:{colore_bg}">
            <td style="padding:12px;border-bottom:1px solid #e5e7eb">{s['emoji']} {s['descrizione']}</td>
            <td style="padding:12px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:bold">€{s['importo']:,.2f}</td>
            <td style="padding:12px;border-bottom:1px solid #e5e7eb">{tempo}</td>
            <td style="padding:12px;border-bottom:1px solid #e5e7eb;color:{colore_testo};font-weight:bold">{s['livello']}</td>
        </tr>
        """
    
    totale = sum(s["importo"] for s in scadenze)
    
    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px">
        <div style="background:#1e40af;color:white;padding:20px;border-radius:8px 8px 0 0">
            <h1 style="margin:0;font-size:22px">📅 Scadenze F24 - Riepilogo</h1>
            <p style="margin:5px 0 0;opacity:0.9">{datetime.now().strftime('%d/%m/%Y %H:%M')} - Ceraldi Group</p>
        </div>
        
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px">
            <p style="margin-top:0">Sono state rilevate <strong>{len(scadenze)} scadenze F24</strong> che richiedono attenzione:</p>
            
            <table style="width:100%;border-collapse:collapse;margin:15px 0">
                <thead>
                    <tr style="background:#f8fafc">
                        <th style="padding:10px;text-align:left;border-bottom:2px solid #e5e7eb">Descrizione</th>
                        <th style="padding:10px;text-align:right;border-bottom:2px solid #e5e7eb">Importo</th>
                        <th style="padding:10px;text-align:left;border-bottom:2px solid #e5e7eb">Scadenza</th>
                        <th style="padding:10px;text-align:left;border-bottom:2px solid #e5e7eb">Stato</th>
                    </tr>
                </thead>
                <tbody>
                    {righe}
                </tbody>
                <tfoot>
                    <tr style="background:#f1f5f9;font-weight:bold">
                        <td style="padding:12px">TOTALE</td>
                        <td style="padding:12px;text-align:right">€{totale:,.2f}</td>
                        <td colspan="2" style="padding:12px"></td>
                    </tr>
                </tfoot>
            </table>
            
            <p style="color:#6b7280;font-size:13px;margin-bottom:0">
                Questo è un alert automatico del sistema ERP Impresasempliceonline.<br/>
                Accedi alla dashboard F24 per i dettagli completi e procedere al pagamento.
            </p>
        </div>
    </body>
    </html>
    """
